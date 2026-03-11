# -*- coding: utf-8 -*-
"""
===================================
股票数据服务层
===================================

职责：
1. 封装股票数据获取逻辑
2. 提供实时行情和历史数据接口
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from src.repositories.stock_repo import StockRepository

logger = logging.getLogger(__name__)

# 价格缓存，用于计算五分钟涨跌幅和涨速
# 结构: {stock_code: [(timestamp, price), ...]}
_price_cache: Dict[str, List[tuple]] = {}
# 缓存最大保留时间（秒）
_CACHE_MAX_SECONDS = 3600  # 保留1小时
# 清理缓存的阈值
_CACHE_MAX_ENTRIES = 120  # 每只股票最多保留120个点（约每30秒一个点）


def _cleanup_old_cache(stock_code: str, now: float):
    """清理过期的缓存数据"""
    if stock_code not in _price_cache:
        return
    # 过滤掉过期的数据
    valid_entries = [
        (ts, price) for ts, price in _price_cache[stock_code]
        if now - ts <= _CACHE_MAX_SECONDS
    ]
    # 如果数据点太多，保留最新的
    if len(valid_entries) > _CACHE_MAX_ENTRIES:
        valid_entries = valid_entries[-_CACHE_MAX_ENTRIES:]
    _price_cache[stock_code] = valid_entries


def _get_price_before_minutes(stock_code: str, minutes: int, now: float) -> Optional[float]:
    """获取几分钟前的最近价格"""
    if stock_code not in _price_cache:
        return None
    target_time = now - (minutes * 60)
    # 寻找最接近目标时间的价格
    closest_price = None
    closest_diff = float('inf')
    for ts, price in _price_cache[stock_code]:
        if ts <= target_time:
            diff = target_time - ts
            if diff < closest_diff:
                closest_diff = diff
                closest_price = price
    return closest_price


class StockService:
    """
    股票数据服务
    
    封装股票数据获取的业务逻辑
    """
    
    def __init__(self):
        """初始化股票数据服务"""
        self.repo = StockRepository()
    
    def get_realtime_quote(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        获取股票实时行情
        
        Args:
            stock_code: 股票代码
            
        Returns:
            实时行情数据字典
        """
        try:
            # 调用数据获取器获取实时行情
            from data_provider.base import DataFetcherManager
            
            manager = DataFetcherManager()
            quote = manager.get_realtime_quote(stock_code)
            
            if quote is None:
                logger.warning(f"获取 {stock_code} 实时行情失败")
                return None
            
            # UnifiedRealtimeQuote 是 dataclass，使用 getattr 安全访问字段
            # 字段映射: UnifiedRealtimeQuote -> API 响应
            # - code -> stock_code
            # - name -> stock_name
            # - price -> current_price
            # - change_amount -> change
            # - change_pct -> change_percent
            # - open_price -> open
            # - high -> high
            # - low -> low
            # - pre_close -> prev_close
            # - volume -> volume
            # - amount -> amount
            return {
                "stock_code": getattr(quote, "code", stock_code),
                "stock_name": getattr(quote, "name", None),
                "current_price": getattr(quote, "price", 0.0) or 0.0,
                "change": getattr(quote, "change_amount", None),
                "change_percent": getattr(quote, "change_pct", None),
                "open": getattr(quote, "open_price", None),
                "high": getattr(quote, "high", None),
                "low": getattr(quote, "low", None),
                "prev_close": getattr(quote, "pre_close", None),
                "volume": getattr(quote, "volume", None),
                "amount": getattr(quote, "amount", None),
                "volume_ratio": getattr(quote, "volume_ratio", None),
                "turnover_rate": getattr(quote, "turnover_rate", None),
                "pe_ratio": getattr(quote, "pe_ratio", None),
                "pb_ratio": getattr(quote, "pb_ratio", None),
                "total_mv": getattr(quote, "total_mv", None),
                "circ_mv": getattr(quote, "circ_mv", None),
                "amplitude": getattr(quote, "amplitude", None),
                "update_time": datetime.now().isoformat(),
            }
            
        except ImportError:
            logger.warning("DataFetcherManager 未找到，使用占位数据")
            return self._get_placeholder_quote(stock_code)
        except Exception as e:
            logger.error(f"获取实时行情失败: {e}", exc_info=True)
            return None
    
    def get_history_data(
        self,
        stock_code: str,
        period: str = "daily",
        days: int = 30
    ) -> Dict[str, Any]:
        """
        获取股票历史行情
        
        Args:
            stock_code: 股票代码
            period: K 线周期 (daily/weekly/monthly)
            days: 获取天数
            
        Returns:
            历史行情数据字典
            
        Raises:
            ValueError: 当 period 不是 daily 时抛出（weekly/monthly 暂未实现）
        """
        # 验证 period 参数，只支持 daily
        if period != "daily":
            raise ValueError(
                f"暂不支持 '{period}' 周期，目前仅支持 'daily'。"
                "weekly/monthly 聚合功能将在后续版本实现。"
            )
        
        try:
            # 调用数据获取器获取历史数据
            from data_provider.base import DataFetcherManager
            
            manager = DataFetcherManager()
            df, source = manager.get_daily_data(stock_code, days=days)
            
            if df is None or df.empty:
                logger.warning(f"获取 {stock_code} 历史数据失败")
                return {"stock_code": stock_code, "period": period, "data": []}
            
            # 获取股票名称
            stock_name = manager.get_stock_name(stock_code)
            
            # 转换为响应格式
            data = []
            for _, row in df.iterrows():
                date_val = row.get("date")
                if hasattr(date_val, "strftime"):
                    date_str = date_val.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_val)
                
                data.append({
                    "date": date_str,
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "close": float(row.get("close", 0)),
                    "volume": float(row.get("volume", 0)) if row.get("volume") else None,
                    "amount": float(row.get("amount", 0)) if row.get("amount") else None,
                    "change_percent": float(row.get("pct_chg", 0)) if row.get("pct_chg") else None,
                })
            
            return {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "period": period,
                "data": data,
            }
            
        except ImportError:
            logger.warning("DataFetcherManager 未找到，返回空数据")
            return {"stock_code": stock_code, "period": period, "data": []}
        except Exception as e:
            logger.error(f"获取历史数据失败: {e}", exc_info=True)
            return {"stock_code": stock_code, "period": period, "data": []}
    
    def _get_placeholder_quote(self, stock_code: str) -> Dict[str, Any]:
        """
        获取占位行情数据（用于测试）

        Args:
            stock_code: 股票代码

        Returns:
            占位行情数据
        """
        return {
            "stock_code": stock_code,
            "stock_name": f"股票{stock_code}",
            "current_price": 0.0,
            "change": None,
            "change_percent": None,
            "open": None,
            "high": None,
            "low": None,
            "prev_close": None,
            "volume": None,
            "amount": None,
            "update_time": datetime.now().isoformat(),
        }

    def get_chip_distribution(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        获取筹码分布数据

        Args:
            stock_code: 股票代码

        Returns:
            筹码分布数据字典，失败返回 None
        """
        try:
            # 调用数据获取器获取筹码分布
            from data_provider.base import DataFetcherManager

            manager = DataFetcherManager()
            chip = manager.get_chip_distribution(stock_code)

            if chip is None:
                logger.warning(f"获取 {stock_code} 筹码分布失败")
                return None

            # 获取当前价格用于计算筹码状态
            quote = manager.get_realtime_quote(stock_code)
            current_price = quote.price if quote else 0.0
            chip_status = chip.get_chip_status(current_price)

            return {
                "code": chip.code,
                "date": chip.date,
                "source": chip.source,
                "profit_ratio": chip.profit_ratio,
                "avg_cost": chip.avg_cost,
                "cost_90_low": chip.cost_90_low,
                "cost_90_high": chip.cost_90_high,
                "concentration_90": chip.concentration_90,
                "cost_70_low": chip.cost_70_low,
                "cost_70_high": chip.cost_70_high,
                "concentration_70": chip.concentration_70,
                "chip_status": chip_status,
            }

        except ImportError:
            logger.warning("DataFetcherManager 未找到，无法获取筹码分布")
            return None
        except Exception as e:
            logger.error(f"获取筹码分布失败: {e}", exc_info=True)
            return None

    def get_sector_rankings(self, n: int = 5) -> Dict[str, Any]:
        """
        获取板块排名数据

        Args:
            n: 排名数量，默认前5名和后5名

        Returns:
            包含 top_sectors 和 bottom_sectors 的字典
        """
        try:
            from data_provider.base import DataFetcherManager

            manager = DataFetcherManager()
            top_sectors, bottom_sectors = manager.get_sector_rankings(n=n)

            # 转换为响应格式
            return {
                "top_sectors": top_sectors,
                "bottom_sectors": bottom_sectors,
            }

        except ImportError:
            logger.warning("DataFetcherManager 未找到，返回空数据")
            return {"top_sectors": [], "bottom_sectors": []}
        except Exception as e:
            logger.error(f"获取板块排名失败: {e}", exc_info=True)
            return {"top_sectors": [], "bottom_sectors": []}

    def get_stock_sectors(self, stock_code: str) -> Dict[str, Any]:
        """
        获取股票所属板块信息

        Args:
            stock_code: 股票代码

        Returns:
            包含股票所属板块信息的字典
        """
        try:
            from data_provider.base import DataFetcherManager

            manager = DataFetcherManager()
            board_df = manager.get_belong_board(stock_code)

            if board_df is None or board_df.empty:
                return {
                    "stock_code": stock_code,
                    "sectors": [],
                    "count": 0
                }

            # 将DataFrame转换为字典列表
            sectors = []
            for _, row in board_df.iterrows():
                sector_info = {}
                # 提取常见的列
                for col in board_df.columns:
                    value = row[col]
                    # 转换不可JSON序列化的类型
                    if hasattr(value, 'item'):  # numpy types
                        value = value.item()
                    elif hasattr(value, 'isoformat'):  # datetime
                        value = str(value)
                    sector_info[col] = value
                sectors.append(sector_info)

            return {
                "stock_code": stock_code,
                "sectors": sectors,
                "count": len(sectors)
            }

        except ImportError:
            logger.warning("DataFetcherManager 未找到，返回空数据")
            return {"stock_code": stock_code, "sectors": [], "count": 0}
        except Exception as e:
            logger.error(f"获取股票板块信息失败: {e}", exc_info=True)
            return {"stock_code": stock_code, "sectors": [], "count": 0}

    def get_bollinger_bands(
        self,
        stock_code: str,
        period: int = 20,
        std_dev: float = 2.0,
        days: int = 60
    ) -> Dict[str, Any]:
        """
        获取BOLL线（布林线）数据

        BOLL线计算公式：
        - 中轨线（Middle）= N日移动平均线（默认20日）
        - 上轨线（Upper）= 中轨线 + K × N日收盘价的标准差（K默认2）
        - 下轨线（Lower）= 中轨线 - K × N日收盘价的标准差

        Args:
            stock_code: 股票代码
            period: BOLL周期（默认20）
            std_dev: 标准差倍数（默认2）
            days: 获取天数（默认60）

        Returns:
            包含BOLL线数据的字典
        """
        try:
            import pandas as pd
            import numpy as np
            from data_provider.base import DataFetcherManager

            manager = DataFetcherManager()

            # 需要足够的数据来计算BOLL线，获取 period + days 天数据
            fetch_days = max(days + period, 100)
            df, source = manager.get_daily_data(stock_code, days=fetch_days)

            if df is None or df.empty:
                logger.warning(f"获取 {stock_code} 历史数据失败，无法计算BOLL线")
                return {
                    "stock_code": stock_code,
                    "stock_name": None,
                    "period": period,
                    "std_dev": std_dev,
                    "data": [],
                    "latest": None,
                    "position": None
                }

            # 获取股票名称
            stock_name = manager.get_stock_name(stock_code)

            # 确保数据按日期排序
            df = df.sort_values('date').reset_index(drop=True)

            # 计算BOLL线
            close_prices = df['close']

            # 中轨线 = 移动平均线
            middle = close_prices.rolling(window=period).mean()

            # 计算标准差
            std = close_prices.rolling(window=period).std()

            # 上轨线和下轨线
            upper = middle + (std_dev * std)
            lower = middle - (std_dev * std)

            # 计算带宽 (bandwidth) = (upper - lower) / middle
            bandwidth = (upper - lower) / middle

            # 计算 %B 指标 = (close - lower) / (upper - lower)
            percent_b = (close_prices - lower) / (upper - lower)

            # 构建结果数据
            data = []
            for idx, row in df.iterrows():
                date_val = row.get("date")
                if hasattr(date_val, "strftime"):
                    date_str = date_val.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_val)

                # 只返回有BOLL数据的记录（跳过前period-1天的NaN值）
                if pd.notna(middle.iloc[idx]):
                    data.append({
                        "date": date_str,
                        "close": float(row.get("close", 0)),
                        "middle": float(middle.iloc[idx]),
                        "upper": float(upper.iloc[idx]),
                        "lower": float(lower.iloc[idx]),
                        "bandwidth": float(bandwidth.iloc[idx]) if pd.notna(bandwidth.iloc[idx]) else None,
                        "percent_b": float(percent_b.iloc[idx]) if pd.notna(percent_b.iloc[idx]) else None,
                    })

            # 只返回最近 days 天的数据
            data = data[-days:] if len(data) > days else data

            # 获取最新数据并判断价格位置
            latest = None
            position = None
            if data:
                latest = data[-1]
                close_price = latest["close"]
                upper_line = latest["upper"]
                middle_line = latest["middle"]
                lower_line = latest["lower"]

                # 判断价格位置
                if close_price >= upper_line:
                    position = "上轨上方"
                elif close_price >= (upper_line + middle_line) / 2:
                    position = "上轨附近"
                elif close_price >= (middle_line + lower_line) / 2:
                    position = "中轨附近"
                elif close_price >= lower_line:
                    position = "下轨附近"
                else:
                    position = "下轨下方"

            return {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "period": period,
                "std_dev": std_dev,
                "data": data,
                "latest": latest,
                "position": position
            }

        except ImportError as e:
            logger.warning(f"缺少依赖库，无法计算BOLL线: {e}")
            return {
                "stock_code": stock_code,
                "stock_name": None,
                "period": period,
                "std_dev": std_dev,
                "data": [],
                "latest": None,
                "position": None
            }
        except Exception as e:
            logger.error(f"获取BOLL线数据失败: {e}", exc_info=True)
            return {
                "stock_code": stock_code,
                "stock_name": None,
                "period": period,
                "std_dev": std_dev,
                "data": [],
                "latest": None,
                "position": None
            }

    def get_realtime_trade_quote(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        获取股票实时交易数据（精简字段版）

        Args:
            stock_code: 股票代码

        Returns:
            实时交易数据字典，字段包括：
            - t: 更新时间 yyyy-MM-ddHH:mm:ss
            - p: 当前价格（元）
            - o: 开盘价（元）
            - h: 最高价（元）
            - l: 最低价（元）
            - yc: 昨日收盘价（元）
            - cje: 成交额（元）
            - v: 成交量（手）
            - ud: 涨跌额（元）
            - pe: 市盈率（动态）
            - zf: 振幅（%）
            - pc: 涨跌幅（%）
            - fm: 五分钟涨跌幅（%）
            - hs: 换手（%）
            - lb: 量比（%）
            - lt: 流通市值（元）
            - zs: 涨速（%）
            - sjl: 市净率
            - zdf60: 60日涨跌幅（%）
            - zdfnc: 年初至今涨跌幅（%）
            - sz: 总市值（元）
            - rp: 复盘股价（元）
        """
        try:
            import time
            from data_provider.base import DataFetcherManager
            from datetime import datetime

            manager = DataFetcherManager()
            quote = manager.get_realtime_quote(stock_code)

            if quote is None:
                logger.warning(f"获取 {stock_code} 实时交易数据失败")
                return None

            # 格式化更新时间为 yyyy-MM-ddHH:mm:ss
            now = datetime.now()
            now_ts = time.time()
            update_time = now.strftime("%Y-%m-%d%H:%M:%S")

            # 获取当前价格
            current_price = getattr(quote, "price", None) or 0.0
            pre_close = getattr(quote, "pre_close", None)
            open_price = getattr(quote, "open_price", None)

            # 计算涨跌额
            change_amount = getattr(quote, "change_amount", None)
            if change_amount is None and current_price and pre_close:
                change_amount = current_price - pre_close

            # 计算五分钟涨跌幅和涨速
            five_minute_change = None
            rise_speed = None

            if current_price and current_price > 0:
                # 更新价格缓存
                if stock_code not in _price_cache:
                    _price_cache[stock_code] = []
                # 避免重复添加相同时间点的价格
                if not _price_cache[stock_code] or (now_ts - _price_cache[stock_code][-1][0] > 10):
                    _price_cache[stock_code].append((now_ts, current_price))

                # 清理过期缓存
                _cleanup_old_cache(stock_code, now_ts)

                # 计算五分钟涨跌幅 (fm)
                price_5min_ago = _get_price_before_minutes(stock_code, 5, now_ts)
                if price_5min_ago and price_5min_ago > 0:
                    five_minute_change = (current_price - price_5min_ago) / price_5min_ago * 100

                # 计算涨速 (zs) - 这里用两种方式：
                # 1. 如果有1分钟前的数据，用1分钟涨跌幅作为涨速
                # 2. 如果没有，用从开盘到现在的平均涨速
                price_1min_ago = _get_price_before_minutes(stock_code, 1, now_ts)
                if price_1min_ago and price_1min_ago > 0:
                    # 使用1分钟涨跌幅作为涨速（每分钟的涨跌幅）
                    rise_speed = (current_price - price_1min_ago) / price_1min_ago * 100
                elif open_price and open_price > 0:
                    # 使用开盘到现在的平均涨速
                    # 计算从开盘到现在的分钟数
                    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
                    if now < market_open:
                        # 还没开盘，用昨收
                        if pre_close and pre_close > 0:
                            rise_speed = (current_price - pre_close) / pre_close * 100
                    else:
                        # 计算开盘后的分钟数
                        minutes_since_open = (now - market_open).total_seconds() / 60
                        if minutes_since_open > 0:
                            total_change = (current_price - open_price) / open_price * 100
                            # 平均每分钟的涨跌幅
                            rise_speed = total_change / minutes_since_open

            # 获取60日涨跌幅和年初至今涨跌幅（从历史数据计算）
            change_60d = getattr(quote, "change_60d", None)
            change_ytd = None

            # 尝试从历史数据计算年初至今涨跌幅
            try:
                df, _ = manager.get_daily_data(stock_code, days=365)
                if df is not None and not df.empty:
                    # 计算60日涨跌幅
                    if len(df) >= 60:
                        close_60d_ago = df.iloc[-60]['close']
                        if close_60d_ago and close_60d_ago > 0:
                            change_60d = (current_price - close_60d_ago) / close_60d_ago * 100

                    # 计算年初至今涨跌幅
                    from datetime import datetime as dt
                    current_year = now.year
                    year_start_df = df[df['date'].apply(lambda x: hasattr(x, 'year') and x.year == current_year)]
                    if len(year_start_df) > 0:
                        first_close = year_start_df.iloc[0]['close']
                        if first_close and first_close > 0:
                            change_ytd = (current_price - first_close) / first_close * 100
            except Exception as e:
                logger.debug(f"计算历史涨跌幅失败: {e}")

            # 构建返回数据
            return {
                "t": update_time,
                "p": current_price,
                "o": open_price,
                "h": getattr(quote, "high", None),
                "l": getattr(quote, "low", None),
                "yc": pre_close,
                "cje": getattr(quote, "amount", None),
                "v": getattr(quote, "volume", None),
                "ud": change_amount,
                "pe": getattr(quote, "pe_ratio", None),
                "zf": getattr(quote, "amplitude", None),
                "pc": getattr(quote, "change_pct", None),
                "fm": five_minute_change,
                "hs": getattr(quote, "turnover_rate", None),
                "lb": getattr(quote, "volume_ratio", None),
                "lt": getattr(quote, "circ_mv", None),
                "zs": rise_speed,
                "sjl": getattr(quote, "pb_ratio", None),
                "zdf60": change_60d,
                "zdfnc": change_ytd,
                "sz": getattr(quote, "total_mv", None),
                "rp": current_price,
            }

        except ImportError:
            logger.warning("DataFetcherManager 未找到，返回占位数据")
            return self._get_placeholder_trade_quote(stock_code)
        except Exception as e:
            logger.error(f"获取实时交易数据失败: {e}", exc_info=True)
            return None

    def _get_placeholder_trade_quote(self, stock_code: str) -> Dict[str, Any]:
        """
        获取占位实时交易数据（用于测试）

        Args:
            stock_code: 股票代码

        Returns:
            占位实时交易数据
        """
        import time
        from datetime import datetime
        now = datetime.now()
        now_ts = time.time()
        update_time = now.strftime("%Y-%m-%d%H:%M:%S")

        # 对于占位数据，我们也维护一个简单的缓存来计算 fm 和 zs
        placeholder_price = 100.0
        if stock_code not in _price_cache:
            _price_cache[stock_code] = []
        # 添加一个模拟的历史价格点（5分钟前的价格）
        if not _price_cache[stock_code]:
            # 初始时添加一个5分钟前的价格
            _price_cache[stock_code].append((now_ts - 300, placeholder_price * 0.99))
        # 添加当前价格
        _price_cache[stock_code].append((now_ts, placeholder_price))
        # 清理过期缓存
        _cleanup_old_cache(stock_code, now_ts)

        # 计算 fm 和 zs
        five_minute_change = None
        rise_speed = None
        price_5min_ago = _get_price_before_minutes(stock_code, 5, now_ts)
        if price_5min_ago and price_5min_ago > 0:
            five_minute_change = (placeholder_price - price_5min_ago) / price_5min_ago * 100
        # 简单的涨速
        rise_speed = 0.1

        return {
            "t": update_time,
            "p": placeholder_price,
            "o": placeholder_price * 0.995,
            "h": placeholder_price * 1.01,
            "l": placeholder_price * 0.985,
            "yc": placeholder_price * 0.99,
            "cje": 100000000.0,
            "v": 10000.0,
            "ud": placeholder_price * 0.01,
            "pe": 25.5,
            "zf": 2.5,
            "pc": 1.01,
            "fm": five_minute_change,
            "hs": 1.5,
            "lb": 1.2,
            "lt": 10000000000.0,
            "zs": rise_speed,
            "sjl": 3.5,
            "zdf60": 5.2,
            "zdfnc": 8.1,
            "sz": 20000000000.0,
            "rp": placeholder_price,
        }

