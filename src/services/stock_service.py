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
