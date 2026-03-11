# -*- coding: utf-8 -*-
"""
===================================
均线多头筛选器 - MA5>MA10>MA20>MA60
===================================

功能：
1. 从MySQL数据库 tb_stock 表获取A股股票列表
2. 从MySQL数据库 tb_api_stock_history 表获取K线数据
3. 计算均线 MA5/MA10/MA20/MA60
4. 筛选满足 MA5>MA10>MA20>MA60 的股票
5. 定时任务支持
6. 结果输出和通知
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# 确保项目根目录在路径中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.config import setup_env
setup_env()

import pandas as pd
import numpy as np

from data_provider.base import DataFetcherManager, is_st_stock,is_kc_cy_stock,is_bse_code
from src.notification import NotificationService
from src.storage import DatabaseManager
from sqlalchemy import text
from src.core.pipeline import StockAnalysisPipeline
from src.enums import ReportType
import uuid

logger = logging.getLogger(__name__)


@dataclass
class BullishStock:
    """多头股票结果"""
    code: str
    name: str
    current_price: float
    ma5: float
    ma10: float
    ma20: float
    ma60: float
    pct_chg: float = 0.0
    volume_ratio: float = 0.0
    turnover_rate: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'code': self.code,
            'name': self.name,
            'current_price': self.current_price,
            'ma5': self.ma5,
            'ma10': self.ma10,
            'ma20': self.ma20,
            'ma60': self.ma60,
            'pct_chg': self.pct_chg,
            'volume_ratio': self.volume_ratio,
            'turnover_rate': self.turnover_rate,
        }


class MABullScreener:
    """
    均线多头筛选器

    筛选条件：MA5 > MA10 > MA20 > MA60
    """

    def __init__(self, max_workers: int = 10):
        """
        初始化筛选器

        Args:
            max_workers: 并发线程数
        """
        self.max_workers = max_workers
        self.fetcher_manager = DataFetcherManager()
        self.notifier = NotificationService()
        self._stock_name_map = {}  # 股票名称缓存

    def get_stock_list(self) -> List[str]:
        return self._get_stock_list_from_db()

    def _get_stock_list_from_db(self) -> List[str]:
        """
        从 MySQL 数据库 tb_stock 表获取股票列表

        表结构：
        - dm: 股票代码
        - mc: 股票名称
        - jys: 交易所

        Returns:
            股票代码列表，失败返回空列表
        """
        try:
            import pandas as pd

            db = DatabaseManager.get_instance()
            logger.info("尝试从数据库 tb_stock 表获取股票列表...")

            # 使用 pandas 读取 SQL，最简单可靠
            sql = "SELECT dm, mc FROM tb_stock ORDER BY dm"
            df = pd.read_sql(sql, db._engine)

            logger.info(f"tb_stock 表共有 {len(df)} 条记录")

            # 保存股票名称映射
            self._stock_name_map = {}
            stock_codes = []
            for _, row in df.iterrows():
                code = str(row['dm']).strip()
                name = str(row['mc']).strip() if pd.notna(row['mc']) else ''

                # 保存名称映射 - 使用原始代码(带后缀)
                self._stock_name_map[code] = name

                if is_st_stock(name):
                    continue
                if is_kc_cy_stock(code):
                    continue
                if is_bse_code(code):
                    continue

                stock_codes.append(code)

            if stock_codes:
                logger.info(f"从数据库 tb_stock 表获取到 {len(stock_codes)} 只股票")
                return stock_codes
            else:
                logger.warning("数据库查询成功，但没有符合条件的股票")

        except Exception as e:
            logger.error(f"从数据库获取股票列表失败: {e}", exc_info=True)

        return []

    def get_stock_name_from_db(self, code: str) -> Optional[str]:
        """
        从缓存获取股票名称

        Args:
            code: 股票代码

        Returns:
            股票名称，失败返回 None
        """
        # 先检查内存缓存
        if code in self._stock_name_map:
            return self._stock_name_map[code]
        return None

    def calculate_mas(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算均线

        Args:
            df: 包含 close 列的 DataFrame

        Returns:
            添加了均线列的 DataFrame
        """
        df = df.copy()
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        df['MA60'] = df['close'].rolling(window=60).mean()
        return df

    def check_bullish_alignment(self, df: pd.DataFrame) -> Tuple[bool, Dict[str, float]]:
        """
        检查是否满足多头排列 MA5>MA10>MA20>MA60

        Args:
            df: 包含均线数据的 DataFrame

        Returns:
            (是否满足, 均线数据字典)
        """
        if df is None or len(df) < 60:
            return False, {}

        latest = df.iloc[-1]

        ma5 = float(latest.get('MA5', 0))
        ma10 = float(latest.get('MA10', 0))
        ma20 = float(latest.get('MA20', 0))
        ma60 = float(latest.get('MA60', 0))

        # 检查均线是否有效
        if ma5 <= 0 or ma10 <= 0 or ma20 <= 0 or ma60 <= 0:
            return False, {}

        # 检查多头排列 MA5 > MA10 > MA20 > MA60
        is_bullish = (ma5 > ma10) and (ma10 > ma20) and (ma20 > ma60)

        ma_data = {
            'ma5': ma5,
            'ma10': ma10,
            'ma20': ma20,
            'ma60': ma60,
            'current_price': float(latest.get('close', 0))
        }

        return is_bullish, ma_data

    def get_daily_data_from_db(self, code: str, days: int = 180) -> Optional[pd.DataFrame]:
        """
        从数据库 tb_api_stock_history 表获取K线数据

        表结构：
        - stock_code: 股票代码
        - time: 时间戳 (格式: YYYY-MM-DD 或 YYYYMMDD)
        - open_price: 开盘价
        - high_price: 最高价
        - low_price: 最低价
        - close_price: 收盘价
        - volume: 成交量
        - amount: 成交额

        Args:
            code: 股票代码
            days: 获取最近多少天的数据

        Returns:
            标准化的 DataFrame，包含 date, open, high, low, close, volume, amount 列
        """
        try:
            import pandas as pd

            db = DatabaseManager.get_instance()

            # 查询最近 N 天的数据 - 使用 SQLAlchemy text 确保参数兼容性
            from sqlalchemy import text

            sql = text("""
                SELECT
                    time as date,
                    open_price as open,
                    high_price as high,
                    low_price as low,
                    close_price as close,
                    volume,
                    amount
                FROM tb_api_stock_history
                WHERE stock_code = :code
                ORDER BY time DESC
                LIMIT :limit
            """)

            logger.info(f"查询 {code} 的K线数据...")

            with db.get_session() as session:
                result = session.execute(sql, {'code': code, 'limit': days})
                df = pd.DataFrame(result.fetchall())
                if not df.empty:
                    df.columns = result.keys()

            if df is None or len(df) == 0:
                logger.warning(f"{code} 未找到任何K线数据")
                return None

            logger.info(f"从数据库获取 {code} K线数据: {len(df)} 条")

            # 转换日期格式 - 兼容多种格式 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)
            df['date'] = pd.to_datetime(df['date'], format='mixed').dt.date

            # 按日期升序排列
            df = df.sort_values('date').reset_index(drop=True)

            # 确保数值类型正确
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            logger.info(f"{code} K线日期范围: {df['date'].iloc[0]} ~ {df['date'].iloc[-1]}")
            return df

        except Exception as e:
            logger.error(f"从数据库获取 {code} K线数据失败: {e}", exc_info=True)
            return None

    def analyze_single_stock(self, code: str) -> Optional[BullishStock]:
        """
        分析单只股票

        Args:
            code: 股票代码

        Returns:
            如果满足多头条件返回 BullishStock，否则返回 None
        """
        try:
            # 优先从数据库获取K线数据
            df = self.get_daily_data_from_db(code, days=180)

            if df is None or len(df) < 60:
                return None

            # 计算均线
            df = self.calculate_mas(df)

            # 检查多头排列
            is_bullish, ma_data = self.check_bullish_alignment(df)

            if not is_bullish:
                return None

            # 从缓存获取股票名称
            name = self.get_stock_name_from_db(code) or code

            # 获取实时行情补充信息
            quote = None
            try:
                quote = self.fetcher_manager.get_realtime_quote(code)
            except:
                pass

            return BullishStock(
                code=code,
                name=name,
                current_price=ma_data['current_price'],
                ma5=ma_data['ma5'],
                ma10=ma_data['ma10'],
                ma20=ma_data['ma20'],
                ma60=ma_data['ma60'],
                pct_chg=quote.change_pct if quote else 0.0,
                volume_ratio=quote.volume_ratio if quote else 0.0,
                turnover_rate=quote.turnover_rate if quote else 0.0,
            )

        except Exception as e:
            logger.debug(f"分析股票 {code} 失败: {e}")
            return None

    def run_screener(self, max_stocks: Optional[int] = None, verbose: bool = False) -> List[BullishStock]:
        """
        运行筛选器

        Args:
            max_stocks: 限制分析的股票数量（用于测试）
            verbose: 是否输出详细日志

        Returns:
            满足多头条件的股票列表
        """
        logger.info("=" * 60)
        logger.info("均线多头筛选器启动")
        logger.info("=" * 60)

        # 获取股票列表
        stock_codes = self.get_stock_list()

        if not stock_codes:
            logger.error("未获取到股票列表")
            return []

        # 限制股票数量（用于测试）
        if max_stocks and max_stocks > 0:
            stock_codes = stock_codes[:max_stocks]
            logger.info(f"限制分析前 {max_stocks} 只股票")

        logger.info(f"开始分析 {len(stock_codes)} 只股票...")

        # 并发分析
        bullish_stocks = []
        processed = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            logger.info(f"开始分析")
            future_to_code = {
                executor.submit(self.analyze_single_stock, code): code
                for code in stock_codes
            }

            for future in as_completed(future_to_code):
                code = future_to_code[future]
                processed += 1

                try:
                    result = future.result()
                    if result:
                        bullish_stocks.append(result)
                        if verbose:
                            logger.info(f"[{processed}/{len(stock_codes)}] ✓ {result.name}({result.code}) 满足多头条件")

                except Exception as e:
                    logger.debug(f"处理股票 {code} 时出错: {e}")

                if processed % 100 == 0:
                    logger.info(f"进度: {processed}/{len(stock_codes)}, 已找到 {len(bullish_stocks)} 只多头股票")

        # 按涨跌幅排序
        bullish_stocks.sort(key=lambda x: x.pct_chg, reverse=True)

        logger.info("=" * 60)
        logger.info(f"筛选完成！共找到 {len(bullish_stocks)} 只满足 MA5>MA10>MA20>MA60 的股票")
        logger.info("=" * 60)

        return bullish_stocks

    def save_results(self, bullish_stocks: List[BullishStock], output_dir: str = "reports") -> Optional[str]:
        """
        保存结果到文件

        Args:
            bullish_stocks: 多头股票列表
            output_dir: 输出目录

        Returns:
            保存的文件路径，失败返回 None
        """
        try:
            os.makedirs(output_dir, exist_ok=True)

            now = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"ma_bull_{now}.csv"
            filepath = os.path.join(output_dir, filename)

            df = pd.DataFrame([s.to_dict() for s in bullish_stocks])
            df.to_csv(filepath, index=False, encoding='utf-8-sig')

            logger.info(f"结果已保存到: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"保存结果失败: {e}")
            return None

    def send_notification(self, report: str, bullish_stocks: List[BullishStock]) -> bool:
        """
        发送通知

        Args:
            report: 报告文本
            bullish_stocks: 多头股票列表

        Returns:
            是否发送成功
        """
        try:
            if not self.notifier.is_available():
                logger.info("通知服务未配置，跳过发送")
                return False

            # 简短版本用于推送
            short_msg = (
                f"📊 均线多头筛选完成\n"
                f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"结果: 共 {len(bullish_stocks)} 只股票满足 MA5>MA10>MA20>MA60"
            )

            if bullish_stocks:
                short_msg += "\n\n前10只:\n"
                for stock in bullish_stocks[:10]:
                    short_msg += f"  {stock.name}({stock.code}): {stock.current_price:.2f} {stock.pct_chg:+.2f}%\n"

            # 发送简短消息
            if self.notifier.send(short_msg):
                logger.info("通知发送成功")
                return True

            return False

        except Exception as e:
            logger.error(f"发送通知失败: {e}")
            return False

    def analyze_bullish_stocks(
        self,
        bullish_stocks: List[BullishStock],
        max_analyze: Optional[int] = None,
        report_type: str = "full"
    ) -> List[Dict[str, Any]]:
        """
        对筛选出的多头股票进行AI分析

        Args:
            bullish_stocks: 多头股票列表
            max_analyze: 最多分析多少只股票（None表示全部）
            report_type: 报告类型 ("brief"|"full"|"simple")

        Returns:
            分析结果列表，每个元素包含股票代码和分析结果
        """
        if not bullish_stocks:
            logger.info("没有满足条件的股票，跳过AI分析")
            return []

        stocks_to_analyze = bullish_stocks

        logger.info(f"开始对 {len(stocks_to_analyze)} 只股票进行AI分析...")

        pipeline = StockAnalysisPipeline(max_workers=self.max_workers)
        results = []

        for idx, stock in enumerate(stocks_to_analyze, 1):
            try:
                query_id = str(uuid.uuid4())
                logger.info(f"[{idx}/{len(stocks_to_analyze)}] 正在分析 {stock.name}({stock.code})...")

                result = pipeline.analyze_stock(
                    code=stock.code,
                    report_type=ReportType.from_str(report_type),
                    query_id=query_id
                )

                if result:
                    results.append({
                        'code': stock.code,
                        'name': stock.name,
                        'analysis_result': result,
                        'query_id': query_id
                    })
                    logger.info(f"[{idx}/{len(stocks_to_analyze)}] {stock.name}({stock.code}) 分析完成")
                else:
                    logger.warning(f"[{idx}/{len(stocks_to_analyze)}] {stock.name}({stock.code}) 分析失败")

            except Exception as e:
                logger.error(f"[{idx}/{len(stocks_to_analyze)}] {stock.name}({stock.code}) 分析异常: {e}", exc_info=True)

        logger.info(f"AI分析完成，成功分析 {len(results)} 只股票")
        return results

    def generate_ai_analysis_report(self, analysis_results: List[Dict[str, Any]]) -> str:
        """
        生成AI分析报告

        Args:
            analysis_results: AI分析结果列表

        Returns:
            报告文本
        """
        lines = []
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        lines.append("=" * 60)
        lines.append(f"🤖 AI分析报告 - {now}")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"分析股票数: {len(analysis_results)}")
        lines.append("")

        for idx, item in enumerate(analysis_results, 1):
            result = item.get('analysis_result')
            if not result:
                continue

            lines.append("-" * 60)
            lines.append(f"{idx}. {item['name']}({item['code']})")
            lines.append("-" * 60)

            # 提取核心信息
            sentiment = getattr(result, 'sentiment_score', 'N/A')
            advice = getattr(result, 'operation_advice', 'N/A')
            summary = getattr(result, 'analysis_summary', '')

            lines.append(f"   情绪评分: {sentiment}")
            lines.append(f"   操作建议: {advice}")
            if summary:
                lines.append(f"   分析摘要: {summary[:200]}..." if len(summary) > 200 else f"   分析摘要: {summary}")
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)


def run_screener(
    max_workers: int = 10,
    max_stocks: Optional[int] = None,
    verbose: bool = False,
    save: bool = True,
    notify: bool = True,
    analyze_ai: bool = True,
    max_ai_analyze: Optional[int] = 10
) -> str:
    """
    运行筛选器的便捷函数

    Args:
        max_workers: 并发线程数
        max_stocks: 限制股票数量
        verbose: 详细输出
        save: 是否保存结果
        notify: 是否发送通知
        analyze_ai: 是否对筛选出的股票进行AI分析
        max_ai_analyze: 最多AI分析多少只股票

    Returns:
        报告文本
    """
    screener = MABullScreener(max_workers=max_workers)
    bullish_stocks = screener.run_screener(max_stocks=max_stocks, verbose=verbose)

    # AI分析
    ai_analysis_results = []
    if analyze_ai and bullish_stocks:
        ai_analysis_results = screener.analyze_bullish_stocks(
            bullish_stocks,
            max_analyze=max_ai_analyze
        )
        if ai_analysis_results:
            ai_report = screener.generate_ai_analysis_report(ai_analysis_results)
            print("\n" + ai_report)

    return ai_analysis_results


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(message)s'
    )

    print("")
    print("=" * 60)
    print("均线多头筛选器 - MA5>MA10>MA20>MA60")
    print("=" * 60)
    print("")

    try:
        print("步骤1: 输入要筛选的股票数量 (默认100):")
        user_input = input().strip()
        max_stocks = int(user_input) if user_input else 100

        print("")
        print("步骤2: 是否对筛选出的股票进行AI分析? (y/n, 默认n):")
        ai_input = input().strip().lower()
        analyze_ai = ai_input in ('y', 'yes', '是')

        max_ai_analyze = 10
        if analyze_ai:
            print("")
            print("步骤3: 最多AI分析多少只股票? (默认10):")
            ai_count_input = input().strip()
            if ai_count_input:
                try:
                    max_ai_analyze = int(ai_count_input)
                except ValueError:
                    max_ai_analyze = 10

        print("")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(0)
    except ValueError:
        max_stocks = 100
        analyze_ai = False

    run_screener(
        max_workers=10,
        max_stocks=max_stocks,
        verbose=True,
        analyze_ai=analyze_ai,
        max_ai_analyze=max_ai_analyze
    )
