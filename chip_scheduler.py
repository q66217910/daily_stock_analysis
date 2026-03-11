# -*- coding: utf-8 -*-
"""
===================================
筹码分布定时任务调度器
===================================

职责：
1. 每天收盘后（默认15:30）定时获取筹码分布数据
2. 使用 akshare 获取筹码分布
3. 保存到 MySQL 数据库
4. 支持交易日历检查（仅在交易日执行）

使用方式：
    python chip_scheduler.py              # 正常运行（定时模式）
    python chip_scheduler.py --run-once   # 立即执行一次
    python chip_scheduler.py --debug      # 调试模式
    python chip_scheduler.py --stocks 000001,600519  # 指定股票
"""

import os
import sys
import argparse
import logging
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional, Dict

# 先配置环境
from dotenv import dotenv_values
from src.config import setup_env

_INITIAL_PROCESS_ENV = dict(os.environ)
setup_env()

# 代理配置
if os.getenv("GITHUB_ACTIONS") != "true" and os.getenv("USE_PROXY", "false").lower() == "true":
    proxy_host = os.getenv("PROXY_HOST", "127.0.0.1")
    proxy_port = os.getenv("PROXY_PORT", "10809")
    proxy_url = f"http://{proxy_host}:{proxy_port}"
    os.environ["http_proxy"] = proxy_url
    os.environ["https_proxy"] = proxy_url

from data_provider.akshare_fetcher import AkshareFetcher
from data_provider.base import canonical_stock_code, is_bse_code, is_st_stock, is_kc_cy_stock
from src.config import get_config, Config
from src.logging_config import setup_logging
from src.storage import DatabaseManager, get_db
from src.scheduler import run_with_schedule


logger = logging.getLogger(__name__)


def _get_active_env_path() -> Path:
    env_file = os.getenv("ENV_FILE")
    if env_file:
        return Path(env_file)
    return Path(__file__).resolve().parent / ".env"


def _read_active_env_values() -> Optional[dict]:
    env_path = _get_active_env_path()
    if not env_path.exists():
        return {}
    try:
        values = dotenv_values(env_path)
    except Exception as exc:
        logger.warning("读取配置文件 %s 失败，继续沿用当前环境变量: %s", env_path, exc)
        return None
    return {
        str(key): "" if value is None else str(value)
        for key, value in values.items()
        if key is not None
    }


_ACTIVE_ENV_FILE_VALUES = _read_active_env_values() or {}
_RUNTIME_ENV_FILE_KEYS = {
    key for key in _ACTIVE_ENV_FILE_VALUES
    if key not in _INITIAL_PROCESS_ENV
}


def _reload_env_file_values_preserving_overrides() -> None:
    """Refresh `.env`-managed env vars without clobbering process env overrides."""
    global _RUNTIME_ENV_FILE_KEYS

    latest_values = _read_active_env_values()
    if latest_values is None:
        return

    managed_keys = {
        key for key in latest_values
        if key not in _INITIAL_PROCESS_ENV
    }

    for key in _RUNTIME_ENV_FILE_KEYS - managed_keys:
        os.environ.pop(key, None)

    for key in managed_keys:
        os.environ[key] = latest_values[key]

    _RUNTIME_ENV_FILE_KEYS = managed_keys


def _reload_runtime_config() -> Config:
    """Reload config from the latest persisted `.env` values for scheduled runs."""
    _reload_env_file_values_preserving_overrides()
    Config.reset_instance()
    return get_config()


def get_all_a_stocks() -> List[Dict[str, str]]:
    """
    获取所有A股股票列表（从数据库tb_stock表）

    Returns:
        股票列表，每个元素包含 'code' 和 'name'
    """
    import pandas as pd

    try:
        logger.info("正在获取A股股票列表...")

        db = DatabaseManager.get_instance()
        logger.info("尝试从数据库 tb_stock 表获取股票列表...")

        # 使用 pandas 读取 SQL，最简单可靠
        sql = "SELECT dm, mc FROM tb_stock ORDER BY dm"
        df = pd.read_sql(sql, db._engine)

        logger.info(f"tb_stock 表共有 {len(df)} 条记录")

        # 保存股票名称映射
        stocks = []
        for _, row in df.iterrows():
            code = str(row['dm']).strip()
            name = str(row['mc']).strip() if pd.notna(row['mc']) else ''

            if is_st_stock(name):
                continue
            if is_kc_cy_stock(code):
                continue
            if is_bse_code(code):
                continue

            stocks.append({'code': code, 'name': name})

        if stocks:
            logger.info(f"从数据库 tb_stock 表获取到 {len(stocks)} 只股票")
        else:
            logger.warning("数据库查询成功，但没有符合条件的股票")
        return stocks

    except Exception as e:
        logger.exception(f"获取A股股票列表失败: {e}")
        return []


def is_trading_day(check_date: Optional[date] = None) -> bool:
    """
    检查是否为交易日

    Args:
        check_date: 要检查的日期（默认今天）

    Returns:
        True 表示是交易日，False 表示是非交易日
    """
    if check_date is None:
        check_date = date.today()

    try:
        from src.core.trading_calendar import get_open_markets_today
        open_markets = get_open_markets_today()
        # A股市场是否开市
        return 'cn' in open_markets
    except Exception as e:
        logger.warning(f"交易日历检查失败，默认按交易日处理: {e}")
        # 默认返回 True（交易日），避免因为日历问题错过数据获取
        return True


def fetch_and_save_chip_distribution(
    stock_code: str,
    db: Optional[DatabaseManager] = None,
    force: bool = False,
) -> bool:
    """
    获取并保存单只股票的筹码分布数据

    Args:
        stock_code: 股票代码
        db: 数据库管理器实例（可选）
        force: 是否强制更新，即使数据已存在

    Returns:
        是否成功保存
    """
    if db is None:
        db = get_db()

    # 规范化股票代码
    code = canonical_stock_code(stock_code)

    try:
        # 获取当前日期
        today = date.today()

        # 检查是否已存在数据（除非强制更新）
        if not force and db.has_chip_distribution(code, today):
            logger.info(f"筹码分布数据已存在，跳过: {code} {today}")
            return True

        # 使用 AkshareFetcher 获取筹码分布
        fetcher = AkshareFetcher()
        chip = fetcher.get_chip_distribution(code)

        if chip is None:
            logger.warning(f"获取筹码分布失败: {code}")
            return False

        # 获取当前价格用于生成筹码状态描述
        current_price = None
        try:
            quote = fetcher.get_realtime_quote(code)
            if quote and quote.price:
                current_price = quote.price
        except Exception as e:
            logger.debug(f"获取实时价格失败（不影响筹码分布保存）: {e}")

        # 生成筹码状态描述
        chip_status = None
        if hasattr(chip, 'get_chip_status') and current_price:
            chip_status = chip.get_chip_status(current_price)

        # 解析日期
        chip_date = today
        if chip.date:
            try:
                if isinstance(chip.date, str):
                    chip_date = datetime.strptime(chip.date, '%Y-%m-%d').date()
                elif isinstance(chip.date, datetime):
                    chip_date = chip.date.date()
            except Exception as e:
                logger.debug(f"解析筹码日期失败，使用今天: {e}")
                chip_date = today

        # 保存到数据库
        record = db.save_chip_distribution(
            code=code,
            chip_date=chip_date,
            source=getattr(chip, 'source', 'akshare'),
            profit_ratio=chip.profit_ratio,
            avg_cost=chip.avg_cost,
            cost_90_low=chip.cost_90_low,
            cost_90_high=chip.cost_90_high,
            concentration_90=chip.concentration_90,
            cost_70_low=chip.cost_70_low,
            cost_70_high=chip.cost_70_high,
            concentration_70=chip.concentration_70,
            chip_status=chip_status,
        )

        if record:
            logger.info(
                f"筹码分布保存成功: {code} {chip_date}, "
                f"获利比例={chip.profit_ratio:.2%}, "
                f"平均成本={chip.avg_cost}, "
                f"90%集中度={chip.concentration_90:.2%}"
            )
            return True
        else:
            logger.error(f"筹码分布保存失败: {code}")
            return False

    except Exception as e:
        logger.exception(f"获取/保存筹码分布异常: {code}, 错误: {e}")
        return False


def run_chip_distribution_task(
    stock_codes: Optional[List[str]] = None,
    force: bool = False,
    skip_trading_check: bool = False,
) -> None:
    """
    执行筹码分布获取任务

    Args:
        stock_codes: 股票代码列表（None 则获取所有A股）
        force: 是否强制更新，即使数据已存在
        skip_trading_check: 是否跳过交易日检查
    """
    logger.info("=" * 60)
    logger.info(f"筹码分布任务开始执行 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    try:
        # 交易日检查
        if not skip_trading_check:
            if not is_trading_day():
                logger.info("今日是非交易日，跳过筹码分布获取")
                return
            logger.info("今日是交易日，继续执行")

        # 获取配置
        config = get_config()

        # 确定要处理的股票列表
        stocks_to_process: List[Dict[str, str]] = []

        if stock_codes is not None:
            # 使用命令行指定的股票代码
            stocks_to_process = [{'code': code, 'name': ''} for code in stock_codes]
        else:
            # 获取所有A股（过滤北交所和ST）
            stocks_to_process = get_all_a_stocks()

        if not stocks_to_process:
            logger.warning("没有待处理的股票，任务结束")
            return

        logger.info(f"待处理股票数量: {len(stocks_to_process)}")
        if len(stocks_to_process) <= 50:
            logger.info(f"股票列表: {[s['code'] for s in stocks_to_process]}")

        # 初始化数据库
        db = get_db()

        # 逐个处理股票
        success_count = 0
        fail_count = 0
        skip_count = 0

        for i, stock_info in enumerate(stocks_to_process, 1):
            stock_code = stock_info['code']
            stock_name = stock_info.get('name', '')

            # 检查是否已存在数据（除非强制更新）
            if not force:
                today = date.today()
                if db.has_chip_distribution(stock_code, today):
                    if i % 100 == 0:  # 每100条输出一次跳过日志
                        logger.debug(f"[{i}/{len(stocks_to_process)}] 数据已存在，跳过: {stock_code} {stock_name}")
                    skip_count += 1
                    continue

            logger.info(f"[{i}/{len(stocks_to_process)}] 处理: {stock_code} {stock_name}")

            if fetch_and_save_chip_distribution(stock_code, db, force=force):
                success_count += 1
            else:
                fail_count += 1

        # 输出统计
        logger.info("=" * 60)
        logger.info(f"筹码分布任务完成")
        logger.info(f"成功: {success_count}, 失败: {fail_count}, 跳过: {skip_count}")
        logger.info("=" * 60)

    except Exception as e:
        logger.exception(f"筹码分布任务执行失败: {e}")


def parse_arguments() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='筹码分布定时任务调度器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python chip_scheduler.py                    # 定时任务模式（每天15:30执行）
  python chip_scheduler.py --run-once         # 立即执行一次
  python chip_scheduler.py --debug            # 调试模式
  python chip_scheduler.py --stocks 000001,600519  # 指定股票
  python chip_scheduler.py --force            # 强制更新（覆盖已有数据）
  python chip_scheduler.py --schedule-time 16:00  # 指定定时时间
        '''
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='启用调试模式，输出详细日志'
    )

    parser.add_argument(
        '--stocks',
        type=str,
        help='指定要获取筹码分布的股票代码，逗号分隔（覆盖配置文件）'
    )

    parser.add_argument(
        '--run-once',
        action='store_true',
        help='立即执行一次任务，不使用定时模式'
    )

    parser.add_argument(
        '--force',
        action='store_true',
        help='强制更新，即使数据已存在也重新获取'
    )

    parser.add_argument(
        '--skip-trading-check',
        action='store_true',
        help='跳过交易日检查，强制执行'
    )

    parser.add_argument(
        '--schedule-time',
        type=str,
        default='15:30',
        help='定时执行时间，格式 HH:MM（默认 15:30）'
    )

    parser.add_argument(
        '--no-run-immediately',
        action='store_true',
        help='定时任务启动时不立即执行一次'
    )

    return parser.parse_args()


def main() -> int:
    """主入口函数"""
    args = parse_arguments()

    # 加载配置
    try:
        config = get_config()
    except Exception as exc:
        logging.basicConfig(
            level=logging.DEBUG if args.debug else logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stderr,
        )
        logger.exception("加载配置失败: %s", exc)
        return 1

    # 配置日志
    try:
        setup_logging(log_prefix="chip_distribution", debug=args.debug, log_dir=config.log_dir)
    except Exception as exc:
        logging.basicConfig(
            level=logging.DEBUG if args.debug else logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stderr,
        )
        logger.exception("切换到配置日志目录失败，已回退到 stderr: %s", exc)

    logger.info("=" * 60)
    logger.info("筹码分布定时任务调度器 启动")
    logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # 解析股票列表
    stock_codes = None
    if args.stocks:
        stock_codes = [canonical_stock_code(c) for c in args.stocks.split(',') if (c or "").strip()]
        logger.info(f"使用命令行指定的股票列表: {stock_codes}")

    # 模式1: 立即执行一次
    if args.run_once:
        logger.info("模式: 立即执行一次")
        run_chip_distribution_task(
            stock_codes=stock_codes,
            force=args.force,
            skip_trading_check=args.skip_trading_check,
        )
        return 0

    # 模式2: 定时任务模式
    logger.info("模式: 定时任务")
    logger.info(f"每日执行时间: {args.schedule_time}")

    should_run_immediately = not args.no_run_immediately
    logger.info(f"启动时立即执行: {should_run_immediately}")

    def scheduled_task():
        """定时任务包装函数"""
        runtime_config = _reload_runtime_config()
        run_chip_distribution_task(
            stock_codes=stock_codes,
            force=args.force,
            skip_trading_check=args.skip_trading_check,
        )

    run_with_schedule(
        task=scheduled_task,
        schedule_time=args.schedule_time,
        run_immediately=should_run_immediately,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
