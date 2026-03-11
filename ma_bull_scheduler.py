# -*- coding: utf-8 -*-
"""
===================================
均线多头筛选定时任务
===================================

功能：
1. 每日定时筛选 MA5>MA10>MA20>MA60 的股票
2. 支持配置定时时间
3. 结果保存和通知

使用方式：
    # 立即运行一次
    python ma_bull_scheduler.py --run-once

    # 定时模式（每天 11:30 执行）
    python ma_bull_scheduler.py --schedule --time 11:30

    # 定时模式，启动时立即执行一次
    python ma_bull_scheduler.py --schedule --time 11:30 --run-immediately
"""

import os
import sys
import logging
import argparse
import time
from datetime import datetime

# 确保项目根目录在路径中
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from src.config import setup_env
setup_env()

from src.ma_bull_screener import run_screener
from src.logging_config import setup_logging
from src.config import get_config

logger = logging.getLogger(__name__)


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='均线多头筛选定时任务',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python ma_bull_scheduler.py --run-once                        # 立即运行一次
  python ma_bull_scheduler.py --schedule                         # 定时模式（默认 11:30）
  python ma_bull_scheduler.py --schedule --time 15:00           # 每天 15:00 执行
  python ma_bull_scheduler.py --schedule --run-immediately      # 启动时立即执行一次
  python ma_bull_scheduler.py --max-stocks 200                  # 限制分析200只股票（测试用）
  python ma_bull_scheduler.py --run-once --analyze-ai           # 立即运行一次并进行AI分析
  python ma_bull_scheduler.py --run-once --analyze-ai --max-ai-analyze 20  # AI分析最多20只
        '''
    )

    parser.add_argument(
        '--run-once',
        action='store_true',
        help='立即运行一次筛选并退出'
    )

    parser.add_argument(
        '--schedule',
        action='store_true',
        help='启用定时任务模式'
    )

    parser.add_argument(
        '--time',
        type=str,
        default='11:30',
        help='定时执行时间，格式 HH:MM (默认: 11:30)'
    )

    parser.add_argument(
        '--run-immediately',
        action='store_true',
        help='定时模式下，启动时立即执行一次'
    )

    parser.add_argument(
        '--max-stocks',
        type=int,
        default=None,
        help='限制分析的股票数量（用于测试，默认分析全部）'
    )

    parser.add_argument(
        '--workers',
        type=int,
        default=10,
        help='并发线程数 (默认: 10)'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='详细输出模式'
    )

    parser.add_argument(
        '--no-save',
        action='store_true',
        help='不保存结果到文件'
    )

    parser.add_argument(
        '--no-notify',
        action='store_true',
        help='不发送通知'
    )

    parser.add_argument(
        '--analyze-ai',
        action='store_true',
        help='对筛选出的股票进行AI分析'
    )

    parser.add_argument(
        '--max-ai-analyze',
        type=int,
        default=10,
        help='最多AI分析多少只股票 (默认: 10)'
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='调试模式'
    )

    return parser.parse_args()


def run_screener_task(args):
    """执行筛选任务"""
    logger.info("=" * 60)
    logger.info(f"开始执行均线多头筛选 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.analyze_ai:
        logger.info(f"AI分析已启用，最多分析 {args.max_ai_analyze} 只股票")
    logger.info("=" * 60)

    try:
        report = run_screener(
            max_workers=args.workers,
            max_stocks=args.max_stocks,
            verbose=args.verbose,
            save=not args.no_save,
            notify=not args.no_notify,
            analyze_ai=args.analyze_ai,
            max_ai_analyze=args.max_ai_analyze
        )
        logger.info("筛选任务执行完成")
        return report
    except Exception as e:
        logger.exception(f"筛选任务执行失败: {e}")
        return None


def run_with_schedule(task_func, schedule_time: str, run_immediately: bool = False):
    """
    使用定时调度运行任务（阻塞式，用于独立运行）

    Args:
        task_func: 任务函数
        schedule_time: 定时时间 HH:MM
        run_immediately: 是否立即执行一次
    """
    try:
        import schedule
    except ImportError:
        logger.error("schedule 库未安装，请执行: pip install schedule")
        sys.exit(1)

    # 注册定时任务
    schedule.every().day.at(schedule_time).do(task_func)
    logger.info(f"已设置每日定时任务: {schedule_time}")

    # 立即执行一次
    if run_immediately:
        logger.info("启动时立即执行一次任务...")
        task_func()

    logger.info(f"下次执行时间: {schedule.next_run()}")
    logger.info("按 Ctrl+C 退出...")

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)

            # 每分钟输出一次心跳
            now = datetime.now()
            if now.second < 30 and now.minute % 30 == 0:
                logger.info(f"调度器运行中... 下次执行: {schedule.next_run()}")

    except KeyboardInterrupt:
        logger.info("\n用户中断，程序退出")


def start_scheduler_in_background(args, daemon: bool = True):
    """
    在后台线程启动定时任务（用于与API服务一起运行）

    Args:
        args: 命令行参数
        daemon: 是否为守护线程

    Returns:
        threading.Thread: 后台线程对象
    """
    import threading
    import schedule

    # 定义任务函数
    def task():
        run_screener_task(args)

    # 注册定时任务
    schedule.every().day.at(args.time).do(task)
    logger.info(f"[MA Bull Scheduler] 已设置每日定时任务: {args.time}")

    # 立即执行一次
    if args.run_immediately:
        logger.info("[MA Bull Scheduler] 启动时立即执行一次任务...")
        # 在新线程中执行，避免阻塞
        import threading
        threading.Thread(target=task, daemon=True).start()

    # 后台调度循环
    def scheduler_loop():
        logger.info(f"[MA Bull Scheduler] 下次执行时间: {schedule.next_run()}")
        try:
            while True:
                schedule.run_pending()
                time.sleep(30)

                # 每30分钟输出一次心跳
                now = datetime.now()
                if now.second < 30 and now.minute % 30 == 0:
                    logger.info(f"[MA Bull Scheduler] 调度器运行中... 下次执行: {schedule.next_run()}")
        except Exception as e:
            logger.exception(f"[MA Bull Scheduler] 调度器异常: {e}")

    thread = threading.Thread(target=scheduler_loop, daemon=daemon)
    thread.start()
    logger.info("[MA Bull Scheduler] 已在后台启动")
    return thread


def main():
    """主入口"""
    args = parse_arguments()

    # 加载配置
    config = get_config()

    # 设置日志
    setup_logging(
        log_prefix="ma_bull_screener",
        debug=args.debug,
        log_dir=config.log_dir
    )

    logger.info("=" * 60)
    logger.info("均线多头筛选器启动")
    logger.info(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # 定义任务函数
    def task():
        run_screener_task(args)

    # 模式1: 立即运行一次
    if args.run_once:
        logger.info("模式: 立即运行一次")
        run_screener_task(args)
        return 0

    # 模式2: 定时任务模式
    if args.schedule:
        logger.info("模式: 定时任务")
        logger.info(f"定时时间: {args.time}")
        logger.info(f"启动时立即执行: {args.run_immediately}")

        run_with_schedule(
            task_func=task,
            schedule_time=args.time,
            run_immediately=args.run_immediately
        )
        return 0

    # 默认模式: 立即运行一次
    logger.info("模式: 默认（立即运行一次）")
    run_screener_task(args)

    logger.info("程序执行完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())