# -*- coding: utf-8 -*-
"""
===================================
交易日历模块 (Issue #373)
===================================

职责：
1. 按市场（A股/港股/美股）判断当日是否为交易日
2. 按市场时区取“今日”日期，避免服务器 UTC 导致日期错误
3. 支持 per-stock 过滤：只分析当日开市市场的股票

依赖：exchange-calendars（可选，不可用时 fail-open）
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, time
from typing import Optional, Set
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Exchange-calendars availability
_XCALS_AVAILABLE = False
try:
    import exchange_calendars as xcals
    _XCALS_AVAILABLE = True
except ImportError:
    logger.warning(
        "exchange-calendars not installed; trading day check disabled. "
        "Run: pip install exchange-calendars"
    )

# Market -> exchange code (exchange-calendars)
MARKET_EXCHANGE = {"cn": "XSHG", "hk": "XHKG", "us": "XNYS"}

# Market -> IANA timezone for "today"
MARKET_TIMEZONE = {
    "cn": "Asia/Shanghai",
    "hk": "Asia/Hong_Kong",
    "us": "America/New_York",
}


def get_market_for_stock(code: str) -> Optional[str]:
    """
    Infer market region for a stock code.

    Returns:
        'cn' | 'hk' | 'us' | None (None = unrecognized, fail-open: treat as open)
    """
    if not code or not isinstance(code, str):
        return None
    code = (code or "").strip().upper()

    from data_provider import is_us_stock_code, is_us_index_code, is_hk_stock_code

    if is_us_stock_code(code) or is_us_index_code(code):
        return "us"
    if is_hk_stock_code(code):
        return "hk"
    # A-share: 6-digit numeric
    if code.isdigit() and len(code) == 6:
        return "cn"
    return None


def is_market_open(market: str, check_date: date) -> bool:
    """
    Check if the given market is open on the given date.

    Fail-open: returns True if exchange-calendars unavailable or date out of range.

    Args:
        market: 'cn' | 'hk' | 'us'
        check_date: Date to check

    Returns:
        True if trading day (or fail-open), False otherwise
    """
    if not _XCALS_AVAILABLE:
        return True
    ex = MARKET_EXCHANGE.get(market)
    if not ex:
        return True
    try:
        cal = xcals.get_calendar(ex)
        session = datetime(check_date.year, check_date.month, check_date.day)
        return cal.is_session(session)
    except Exception as e:
        logger.warning("trading_calendar.is_market_open fail-open: %s", e)
        return True


def get_market_now(
    market: Optional[str], current_time: Optional[datetime] = None
) -> datetime:
    """
    Return current time in the market's local timezone.

    If current_time is naive, treat it as already expressed in the market timezone.
    Unknown markets fall back to the given datetime (or local system time).
    """
    tz_name = MARKET_TIMEZONE.get(market or "")

    if current_time is None:
        if tz_name:
            return datetime.now(ZoneInfo(tz_name))
        return datetime.now()

    if not tz_name:
        return current_time

    tz = ZoneInfo(tz_name)
    if current_time.tzinfo is None:
        return current_time.replace(tzinfo=tz)
    return current_time.astimezone(tz)


def get_effective_trading_date(
    market: Optional[str], current_time: Optional[datetime] = None
) -> date:
    """
    Resolve the latest reusable daily-bar date for checkpoint/resume logic.

    Rules:
    - Non-trading day / holiday: previous trading session
    - Trading day before market close: previous completed trading session
    - Trading day after market close: current trading session
    - Calendar lookup failure: fail-open to market-local natural date
    """
    market_now = get_market_now(market, current_time=current_time)
    fallback_date = market_now.date()

    if not _XCALS_AVAILABLE:
        return fallback_date

    ex = MARKET_EXCHANGE.get(market or "")
    tz_name = MARKET_TIMEZONE.get(market or "")
    if not ex or not tz_name:
        return fallback_date

    try:
        cal = xcals.get_calendar(ex)
        local_date = market_now.date()

        if not cal.is_session(local_date):
            return cal.date_to_session(local_date, direction="previous").date()

        session = cal.date_to_session(local_date, direction="previous")
        session_close = cal.session_close(session)
        if hasattr(session_close, "tz_convert"):
            close_local = session_close.tz_convert(tz_name).to_pydatetime()
        elif session_close.tzinfo is not None:
            close_local = session_close.astimezone(ZoneInfo(tz_name))
        else:
            close_local = session_close.replace(tzinfo=ZoneInfo(tz_name))

        if market_now >= close_local:
            return session.date()

        return cal.previous_session(session).date()
    except Exception as e:
        logger.warning("trading_calendar.get_effective_trading_date fail-open: %s", e)
        return fallback_date


def get_open_markets_today() -> Set[str]:
    """
    Get markets that are open today (by each market's local timezone).

    Returns:
        Set of market keys ('cn', 'hk', 'us') that are trading today
    """
    if not _XCALS_AVAILABLE:
        return {"cn", "hk", "us"}
    result: Set[str] = set()
    for mkt, tz_name in MARKET_TIMEZONE.items():
        try:
            tz = ZoneInfo(tz_name)
            today = datetime.now(tz).date()
            if is_market_open(mkt, today):
                result.add(mkt)
        except Exception as e:
            logger.warning("get_open_markets_today fail-open for %s: %s", mkt, e)
            result.add(mkt)
    return result


def compute_effective_region(
    config_region: str, open_markets: Set[str]
) -> Optional[str]:
    """
    Compute effective market review region given config and open markets.

    Args:
        config_region: From MARKET_REVIEW_REGION ('cn' | 'hk' | 'us' | 'both')
        open_markets: Markets open today

    Returns:
        None: caller uses config default (check disabled)
        '': all relevant markets closed, skip market review
        'cn' | 'hk' | 'us' | 'both': effective subset for today
    """
    if config_region not in ("cn", "hk", "us", "both"):
        config_region = "cn"
    if config_region in ("cn", "hk", "us"):
        return config_region if config_region in open_markets else ""
    # both: return only the markets that are actually open today
    parts = [m for m in ("cn", "hk", "us") if m in open_markets]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ",".join(parts)


# ============================================
# 交易时段判断
# ============================================

@dataclass
class TradingSession:
    """交易时段定义"""
    start: datetime.time
    end: datetime.time


# 各市场交易时段（本地时间）
MARKET_TRADING_SESSIONS = {
    "cn": [
        # A股: 9:30-11:30, 13:00-15:00
        TradingSession(start=time(9, 30), end=time(11, 30)),
        TradingSession(start=time(13, 0), end=time(15, 0)),
    ],
    "hk": [
        # 港股: 9:30-12:00, 13:00-16:00
        TradingSession(start=time(9, 30), end=time(12, 0)),
        TradingSession(start=time(13, 0), end=time(16, 0)),
    ],
    "us": [
        # 美股(NYSE): 9:30-16:00 (东部时间)
        TradingSession(start=time(9, 30), end=time(16, 0)),
    ],
}


def is_in_trading_hours(
    market: str,
    check_time: Optional[datetime] = None
) -> bool:
    """
    检查指定市场当前是否在交易时段内

    Args:
        market: 'cn' | 'hk' | 'us'
        check_time: 检查时间（None表示当前时间）

    Returns:
        True 如果在交易时段内，否则返回False
    """
    sessions = MARKET_TRADING_SESSIONS.get(market)
    if not sessions:
        # 未知市场，默认认为在交易时间（fail-open）
        return True

    # 获取市场本地时间
    market_time = get_market_now(market, check_time)
    check_time_today = market_time.time()
    check_weekday = market_time.weekday()

    # 周末不交易
    if check_weekday >= 5:  # 5=周六, 6=周日
        return False

    # 检查是否在任何一个交易时段内
    for session in sessions:
        if session.start <= check_time_today <= session.end:
            return True

    return False


def is_any_market_in_trading_hours(
    check_time: Optional[datetime] = None
) -> bool:
    """
    检查是否有任何一个市场（A股/港股/美股）当前在交易时段内

    Args:
        check_time: 检查时间（None表示当前时间）

    Returns:
        True 如果有任何市场在交易时段内
    """
    for market in ["cn", "hk", "us"]:
        if is_in_trading_hours(market, check_time):
            return True
    return False


def get_current_trading_markets(
    check_time: Optional[datetime] = None
) -> Set[str]:
    """
    获取当前在交易时段内的市场集合

    Args:
        check_time: 检查时间（None表示当前时间）

    Returns:
        正在交易的市场集合 {'cn', 'hk', 'us'}
    """
    result: Set[str] = set()
    for market in ["cn", "hk", "us"]:
        if is_in_trading_hours(market, check_time):
            result.add(market)
    return result


def get_next_trading_start(
    market: str,
    from_time: Optional[datetime] = None
) -> Optional[datetime]:
    """
    获取下一个交易开始时间

    Args:
        market: 'cn' | 'hk' | 'us'
        from_time: 起始时间（None表示当前时间）

    Returns:
        下一个交易开始时间，如果无法计算返回None
    """
    sessions = MARKET_TRADING_SESSIONS.get(market)
    if not sessions:
        return None

    market_time = get_market_now(market, from_time)
    tz = market_time.tzinfo
    check_time_today = market_time.time()

    # 先看今天剩下的时段
    for session in sessions:
        if check_time_today < session.start:
            return datetime.combine(market_time.date(), session.start, tzinfo=tz)

    # 今天没有剩余时段，找下一个交易日的第一个时段
    days_to_add = 1
    while days_to_add <= 14:  # 最多查两周
        next_date = market_time.date() + timedelta(days=days_to_add)
        if is_market_open(market, next_date):
            first_session = sessions[0]
            return datetime.combine(next_date, first_session.start, tzinfo=tz)
        days_to_add += 1

    return None
