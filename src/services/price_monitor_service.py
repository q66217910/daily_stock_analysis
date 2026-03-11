# -*- coding: utf-8 -*-
"""
===================================
价格盯盘服务
===================================

职责：
1. 筛选评分>=85分的股票（今天和上一个交易日）
2. 获取这些股票的理想买入价格
3. 定时获取实时价格
4. 检查价格是否到达理想买入价
5. 触发AI分析和通知
"""

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional, Dict, Any, List, Callable

logger = logging.getLogger(__name__)


@dataclass
class PriceCheckResult:
    """价格检查结果"""
    code: str
    name: str
    current_price: Optional[float]
    target_price: float
    alert_type: str  # ideal_buy / secondary_buy / stop_loss / take_profit
    triggered: bool
    triggered_at: Optional[datetime] = None
    watching_stock_id: Optional[int] = None


class PriceMonitorService:
    """
    价格盯盘服务

    核心功能：
    - 从分析历史中自动添加高分股票到盯盘列表
    - 定时检查股票价格是否触发买入/卖出条件
    - 触发时自动进行AI分析
    - 根据股票数量动态调整检查间隔
    """

    # 检查间隔配置：根据股票数量动态调整
    MIN_INTERVAL = 10  # 最小间隔10秒
    MAX_INTERVAL = 300  # 最大间隔5分钟
    BASE_INTERVAL = 30  # 基础间隔30秒
    STOCKS_PER_INTERVAL_STEP = 5  # 每增加5只股票，间隔增加一些
    INTERVAL_INCREMENT_PER_STEP = 10  # 每步增加10秒

    def __init__(self, check_interval_seconds: int = 30):
        """
        初始化盯盘服务

        Args:
            check_interval_seconds: 价格检查间隔（秒），默认30秒
        """
        self.base_check_interval = check_interval_seconds
        self.check_interval = check_interval_seconds
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # 回调函数
        self._on_alert_callback: Optional[Callable[[PriceCheckResult], None]] = None
        self._on_analysis_callback: Optional[Callable[[str, str], None]] = None

        # 已触发的缓存，避免重复触发
        self._triggered_cache: Dict[str, datetime] = {}
        self._cache_expiry_seconds = 3600  # 1小时内不重复触发同一只股票

        # 依赖注入（延迟初始化）
        self._db = None
        self._data_fetcher = None
        self._analysis_service = None

    def _calculate_dynamic_interval(self, stock_count: int) -> int:
        """
        根据股票数量动态计算检查间隔

        策略：
        - 0-5只股票：30秒
        - 每增加5只，间隔增加10秒
        - 最大不超过5分钟
        """
        if stock_count <= 0:
            return self.BASE_INTERVAL

        steps = (stock_count - 1) // self.STOCKS_PER_INTERVAL_STEP
        interval = self.BASE_INTERVAL + steps * self.INTERVAL_INCREMENT_PER_STEP

        # 限制在最小和最大间隔之间
        return max(self.MIN_INTERVAL, min(self.MAX_INTERVAL, interval))

    def _update_check_interval(self) -> None:
        """根据当前盯盘股票数量更新检查间隔"""
        try:
            stocks = self.get_watching_list(min_score=0)
            stock_count = len(stocks)
            new_interval = self._calculate_dynamic_interval(stock_count)

            if new_interval != self.check_interval:
                old_interval = self.check_interval
                self.check_interval = new_interval
                logger.info(
                    f"动态调整检查间隔: {old_interval}秒 -> {new_interval}秒 "
                    f"(盯盘股票数: {stock_count})"
                )
        except Exception as e:
            logger.warning(f"更新检查间隔失败: {e}")

    def _init_dependencies(self) -> None:
        """延迟初始化依赖"""
        if self._db is None:
            from src.storage import get_db
            self._db = get_db()

        if self._data_fetcher is None:
            from data_provider.base import DataFetcherManager
            self._data_fetcher = DataFetcherManager()

    def set_alert_callback(self, callback: Callable[[PriceCheckResult], None]) -> None:
        """设置价格提醒回调函数"""
        self._on_alert_callback = callback

    def set_analysis_callback(self, callback: Callable[[str, str], None]) -> None:
        """设置AI分析回调函数"""
        self._on_analysis_callback = callback

    def start(self, auto_refresh: bool = True) -> bool:
        """
        启动盯盘服务

        Args:
            auto_refresh: 是否自动从分析历史刷新盯盘列表

        Returns:
            是否启动成功
        """
        if self._running:
            logger.warning("盯盘服务已在运行中")
            return False

        try:
            self._init_dependencies()

            if auto_refresh:
                self.refresh_watching_list()

            self._running = True
            self._stop_event.clear()
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name="price-monitor"
            )
            self._monitor_thread.start()
            logger.info(f"盯盘服务已启动，检查间隔: {self.check_interval}秒")
            return True
        except Exception as e:
            logger.error(f"启动盯盘服务失败: {e}", exc_info=True)
            return False

    def stop(self) -> None:
        """停止盯盘服务"""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=10)

        logger.info("盯盘服务已停止")

    def is_running(self) -> bool:
        """检查服务是否在运行"""
        return self._running

    def refresh_watching_list(self, min_score: int = 85, days: int = 2) -> int:
        """
        刷新盯盘列表

        从最近几天的分析历史中，找出评分>=min_score的股票，
        自动添加到盯盘列表中

        Args:
            min_score: 最低评分
            days: 回溯天数

        Returns:
            新增的盯盘股票数量
        """
        self._init_dependencies()

        try:
            added = self._db.refresh_watching_stocks_from_history(
                days=days,
                min_score=min_score
            )
            logger.info(f"刷新盯盘列表完成，新增 {added} 只股票")
            return added
        except Exception as e:
            logger.error(f"刷新盯盘列表失败: {e}", exc_info=True)
            return 0

    def get_watching_list(self, min_score: int = 85) -> List[Dict[str, Any]]:
        """
        获取当前盯盘列表

        Args:
            min_score: 最低评分筛选

        Returns:
            盯盘股票列表
        """
        self._init_dependencies()

        try:
            stocks = self._db.get_active_watching_stocks(min_score=min_score)
            return [s.to_dict() for s in stocks]
        except Exception as e:
            logger.error(f"获取盯盘列表失败: {e}", exc_info=True)
            return []

    def add_to_watching(
        self,
        code: str,
        name: str,
        sentiment_score: int,
        ideal_buy: float,
        secondary_buy: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        analysis_history_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        手动添加股票到盯盘列表

        Returns:
            添加成功返回盯盘股票信息，已存在返回None
        """
        self._init_dependencies()

        try:
            watching = self._db.add_watching_stock(
                code=code,
                name=name,
                sentiment_score=sentiment_score,
                analysis_date=date.today(),
                ideal_buy=ideal_buy,
                secondary_buy=secondary_buy,
                stop_loss=stop_loss,
                take_profit=take_profit,
                analysis_history_id=analysis_history_id,
            )
            if watching:
                logger.info(f"添加盯盘股票成功: {code} {name}")
                return watching.to_dict()
            return None
        except Exception as e:
            logger.error(f"添加盯盘股票失败: {e}", exc_info=True)
            return None

    def remove_from_watching(self, watching_id: int) -> bool:
        """从盯盘列表中移除"""
        self._init_dependencies()
        return self._db.delete_watching_stock(watching_id)

    def remove_all_from_watching(self) -> int:
        """删除所有盯盘股票"""
        self._init_dependencies()
        count = self._db.delete_all_watching_stocks()
        # 清空触发缓存
        self._triggered_cache.clear()
        return count

    def _monitor_loop(self) -> None:
        """监控主循环"""
        logger.info("盯盘监控循环已启动")

        # 记录上次是否在交易时间的状态，用于日志提示
        last_in_trading_hours: Optional[bool] = None
        # 记录上次更新间隔的时间，避免频繁更新
        last_interval_update = 0.0
        interval_update_cooldown = 60.0  # 至少每隔60秒才更新一次间隔

        while self._running and not self._stop_event.is_set():
            try:
                # 定期更新检查间隔（带冷却）
                now = time.time()
                if now - last_interval_update > interval_update_cooldown:
                    self._update_check_interval()
                    last_interval_update = now

                in_trading = self._is_any_market_in_trading_hours()

                # 状态变化时打日志
                if last_in_trading_hours != in_trading:
                    if in_trading:
                        logger.info("进入交易时间，开始价格监控")
                    else:
                        logger.info("当前不在交易时间，暂停价格监控")
                    last_in_trading_hours = in_trading

                if in_trading:
                    self._check_prices()
                else:
                    # 非交易时间，清理过期的触发缓存
                    self._cleanup_expired_cache()

            except Exception as e:
                logger.error(f"价格检查异常: {e}", exc_info=True)

            # 等待下一次检查或直到停止事件
            self._stop_event.wait(self.check_interval)

        logger.info("盯盘监控循环已退出")

    def _is_any_market_in_trading_hours(self) -> bool:
        """
        检查是否有市场在交易时间内

        Returns:
            True 如果有任何市场在交易时间内
        """
        try:
            from src.core.trading_calendar import is_any_market_in_trading_hours
            return is_any_market_in_trading_hours()
        except ImportError:
            # 如果交易日历模块不可用，默认认为在交易时间（fail-open）
            logger.debug("交易日历模块不可用，默认允许价格检查")
            return True
        except Exception as e:
            logger.warning(f"检查交易时间失败: {e}，默认允许价格检查")
            return True

    def _cleanup_expired_cache(self) -> None:
        """清理过期的触发缓存"""
        now = datetime.now()
        expired_codes = [
            code for code, triggered_at in self._triggered_cache.items()
            if (now - triggered_at).total_seconds() > self._cache_expiry_seconds
        ]
        for code in expired_codes:
            del self._triggered_cache[code]
        if expired_codes:
            logger.debug(f"清理了 {len(expired_codes)} 个过期的触发缓存")

    def _check_prices(self) -> None:
        """执行一次价格检查"""
        self._init_dependencies()

        # 获取活跃的盯盘股票
        watching_stocks = self._db.get_active_watching_stocks(min_score=0)

        if not watching_stocks:
            logger.debug("没有活跃的盯盘股票")
            return

        # 获取当前在交易的市场
        try:
            from src.core.trading_calendar import get_current_trading_markets, get_market_for_stock
            trading_markets = get_current_trading_markets()

            # 只保留属于当前交易市场的股票
            filtered_stocks = []
            for stock in watching_stocks:
                market = get_market_for_stock(stock.code)
                if market is None or market in trading_markets:
                    filtered_stocks.append(stock)

            if len(filtered_stocks) != len(watching_stocks):
                logger.debug(
                    f"过滤盯盘股票: 原始 {len(watching_stocks)} 只, "
                    f"当前交易市场 {trading_markets}, 保留 {len(filtered_stocks)} 只"
                )
            watching_stocks = filtered_stocks
        except Exception as e:
            logger.debug(f"按市场过滤盯盘股票失败: {e}，使用完整列表")

        if not watching_stocks:
            logger.debug("没有在交易时间内的盯盘股票")
            return

        logger.debug(f"检查 {len(watching_stocks)} 只盯盘股票的价格")

        # 批量获取实时价格
        codes = [s.code for s in watching_stocks]
        quotes = self._fetch_realtime_quotes(codes)

        # 检查每只股票
        for stock in watching_stocks:
            if stock.code not in quotes:
                logger.debug(f"无法获取 {stock.code} 的实时价格")
                continue

            quote = quotes[stock.code]
            current_price = quote.price

            if current_price is None or current_price <= 0:
                continue

            # 检查是否应该触发（去重缓存）
            if self._is_recently_triggered(stock.code):
                continue

            # 检查各种价格条件
            result = self._check_price_conditions(stock, quote)
            if result and result.triggered:
                self._handle_trigger(result, stock)

    def _fetch_realtime_quotes(self, codes: List[str]) -> Dict[str, Any]:
        """
        批量获取实时行情

        Returns:
            {code: UnifiedRealtimeQuote}
        """
        result = {}

        try:
            for code in codes:
                quote = self._data_fetcher.get_realtime_quote(code)
                if quote and quote.has_basic_data():
                    result[code] = quote
        except Exception as e:
            logger.error(f"获取实时行情失败: {e}", exc_info=True)

        return result

    def _check_price_conditions(self, watching_stock: Any, quote: Any) -> Optional[PriceCheckResult]:
        """
        检查价格条件

        检查顺序：
        1. 止损（最优先）
        2. 理想买入
        3. 次级买入
        4. 止盈

        返回第一个触发的条件
        """
        current_price = quote.price
        code = watching_stock.code
        name = watching_stock.name or code

        # 止损检查（价格 <= 止损价）
        if watching_stock.stop_loss and current_price <= watching_stock.stop_loss:
            return PriceCheckResult(
                code=code,
                name=name,
                current_price=current_price,
                target_price=watching_stock.stop_loss,
                alert_type="stop_loss",
                triggered=True,
                watching_stock_id=watching_stock.id,
            )

        # 理想买入检查（价格 <= 理想买入价）
        if watching_stock.ideal_buy and current_price <= watching_stock.ideal_buy:
            return PriceCheckResult(
                code=code,
                name=name,
                current_price=current_price,
                target_price=watching_stock.ideal_buy,
                alert_type="ideal_buy",
                triggered=True,
                watching_stock_id=watching_stock.id,
            )

        # 次级买入检查
        if watching_stock.secondary_buy and current_price <= watching_stock.secondary_buy:
            return PriceCheckResult(
                code=code,
                name=name,
                current_price=current_price,
                target_price=watching_stock.secondary_buy,
                alert_type="secondary_buy",
                triggered=True,
                watching_stock_id=watching_stock.id,
            )

        # 止盈检查（价格 >= 止盈价）
        if watching_stock.take_profit and current_price >= watching_stock.take_profit:
            return PriceCheckResult(
                code=code,
                name=name,
                current_price=current_price,
                target_price=watching_stock.take_profit,
                alert_type="take_profit",
                triggered=True,
                watching_stock_id=watching_stock.id,
            )

        # 未触发
        return PriceCheckResult(
            code=code,
            name=name,
            current_price=current_price,
            target_price=0,
            alert_type="none",
            triggered=False,
        )

    def _handle_trigger(self, result: PriceCheckResult, watching_stock: Any) -> None:
        """处理价格触发事件"""
        logger.info(
            f"价格触发: {result.code} {result.name} "
            f"类型: {result.alert_type} "
            f"目标价: {result.target_price} "
            f"现价: {result.current_price}"
        )

        # 记录触发时间
        result.triggered_at = datetime.now()

        # 缓存已触发
        self._triggered_cache[result.code] = datetime.now()

        # 更新数据库状态
        if result.watching_stock_id:
            self._db.update_watching_stock_triggered(
                result.watching_stock_id,
                result.current_price,
            )

        # 创建价格提醒记录
        alert = self._db.add_price_alert(
            watching_stock_id=result.watching_stock_id,
            code=result.code,
            name=result.name,
            alert_type=result.alert_type,
            target_price=result.target_price,
            trigger_price=result.current_price,
            change_pct=getattr(result, 'change_pct', None),
        )

        # 调用回调
        if self._on_alert_callback:
            try:
                self._on_alert_callback(result)
            except Exception as e:
                logger.error(f"价格提醒回调异常: {e}", exc_info=True)

        # 触发AI分析
        if result.alert_type in ("ideal_buy", "secondary_buy"):
            self._trigger_analysis(result, alert.id if alert else None)

    def _trigger_analysis(self, result: PriceCheckResult, alert_id: Optional[int] = None) -> None:
        """触发AI分析"""
        logger.info(f"触发AI分析: {result.code} {result.name}")

        query_id = uuid.uuid4().hex

        try:
            # 如果有回调，使用回调
            if self._on_analysis_callback:
                self._on_analysis_callback(result.code, query_id)
            else:
                # 直接调用分析服务
                self._run_analysis(result.code, query_id)

            # 更新价格提醒记录
            if alert_id:
                self._db.update_price_alert_analysis(alert_id, query_id)

        except Exception as e:
            logger.error(f"触发AI分析失败: {e}", exc_info=True)

    def _run_analysis(self, code: str, query_id: str) -> Optional[Dict[str, Any]]:
        """运行股票分析"""
        try:
            from src.services.analysis_service import AnalysisService

            if self._analysis_service is None:
                self._analysis_service = AnalysisService()

            return self._analysis_service.analyze_stock(
                stock_code=code,
                report_type="detailed",
                query_id=query_id,
                send_notification=True,
            )
        except Exception as e:
            logger.error(f"运行分析失败: {e}", exc_info=True)
            return None

    def _is_recently_triggered(self, code: str) -> bool:
        """检查是否最近已触发过（去重）"""
        if code not in self._triggered_cache:
            return False

        triggered_at = self._triggered_cache[code]
        elapsed = (datetime.now() - triggered_at).total_seconds()

        if elapsed > self._cache_expiry_seconds:
            del self._triggered_cache[code]
            return False

        return True

    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        watching_list = self.get_watching_list()
        # 确保返回的间隔是动态计算后的最新值
        self._update_check_interval()
        return {
            "running": self._running,
            "check_interval_seconds": self.check_interval,
            "watching_count": len(watching_list),
            "triggered_cache_count": len(self._triggered_cache),
        }


# 全局单例
_monitor_service: Optional[PriceMonitorService] = None
_monitor_lock = threading.Lock()


def get_price_monitor(check_interval_seconds: int = 30) -> PriceMonitorService:
    """获取价格盯盘服务单例"""
    global _monitor_service

    if _monitor_service is None:
        with _monitor_lock:
            if _monitor_service is None:
                _monitor_service = PriceMonitorService(
                    check_interval_seconds=check_interval_seconds
                )

    return _monitor_service
