# -*- coding: utf-8 -*-
"""
===================================
股票数据相关模型
===================================

职责：
1. 定义股票实时行情模型
2. 定义历史 K 线数据模型
"""

from typing import Optional, List

from pydantic import BaseModel, Field


class StockQuote(BaseModel):
    """股票实时行情"""
    
    stock_code: str = Field(..., description="股票代码")
    stock_name: Optional[str] = Field(None, description="股票名称")
    current_price: float = Field(..., description="当前价格")
    change: Optional[float] = Field(None, description="涨跌额")
    change_percent: Optional[float] = Field(None, description="涨跌幅 (%)")
    open: Optional[float] = Field(None, description="开盘价")
    high: Optional[float] = Field(None, description="最高价")
    low: Optional[float] = Field(None, description="最低价")
    prev_close: Optional[float] = Field(None, description="昨收价")
    volume: Optional[float] = Field(None, description="成交量（股）")
    amount: Optional[float] = Field(None, description="成交额（元）")
    update_time: Optional[str] = Field(None, description="更新时间")
    volume_ratio: Optional[float] = Field(None, description="量比")
    turnover_rate: Optional[float] = Field(None, description="换手率")
    pe_ratio: Optional[float] = Field(None, description="市盈率（动态）")
    pb_ratio: Optional[float] = Field(None, description="市盈率")
    total_mv: Optional[float] = Field(None, description="总市值")
    circ_mv: Optional[float] = Field(None, description="流通市值")
    amplitude: Optional[float] = Field(None, description="振幅")

    class Config:
        json_schema_extra = {
            "example": {
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "current_price": 1800.00,
                "change": 15.00,
                "change_percent": 0.84,
                "open": 1785.00,
                "high": 1810.00,
                "low": 1780.00,
                "prev_close": 1785.00,
                "volume_ratio": 1,
                "volume": 10000000,
                "amount": 18000000000,
                "update_time": "2024-01-01T15:00:00"
            }
        }


class KLineData(BaseModel):
    """K 线数据点"""
    
    date: str = Field(..., description="日期")
    open: float = Field(..., description="开盘价")
    high: float = Field(..., description="最高价")
    low: float = Field(..., description="最低价")
    close: float = Field(..., description="收盘价")
    volume: Optional[float] = Field(None, description="成交量")
    amount: Optional[float] = Field(None, description="成交额")
    change_percent: Optional[float] = Field(None, description="涨跌幅 (%)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "date": "2024-01-01",
                "open": 1785.00,
                "high": 1810.00,
                "low": 1780.00,
                "close": 1800.00,
                "volume": 10000000,
                "amount": 18000000000,
                "change_percent": 0.84
            }
        }


class ExtractItem(BaseModel):
    """单条提取结果（代码、名称、置信度）"""

    code: Optional[str] = Field(None, description="股票代码，None 表示解析失败")
    name: Optional[str] = Field(None, description="股票名称（如有）")
    confidence: str = Field("medium", description="置信度：high/medium/low")


class ExtractFromImageResponse(BaseModel):
    """图片股票代码提取响应"""

    codes: List[str] = Field(..., description="提取的股票代码（已去重，向后兼容）")
    items: List[ExtractItem] = Field(default_factory=list, description="提取结果明细（代码+名称+置信度）")
    raw_text: Optional[str] = Field(None, description="原始 LLM 响应（调试用）")


class StockHistoryResponse(BaseModel):
    """股票历史行情响应"""

    stock_code: str = Field(..., description="股票代码")
    stock_name: Optional[str] = Field(None, description="股票名称")
    period: str = Field(..., description="K 线周期")
    data: List[KLineData] = Field(default_factory=list, description="K 线数据列表")

    class Config:
        json_schema_extra = {
            "example": {
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "period": "daily",
                "data": []
            }
        }


class ChipDistribution(BaseModel):
    """筹码分布数据"""

    code: str = Field(..., description="股票代码")
    date: str = Field(..., description="日期")
    source: str = Field(..., description="数据源")

    # 获利情况
    profit_ratio: float = Field(..., ge=0.0, le=1.0, description="获利比例 (0-1)")
    avg_cost: float = Field(..., ge=0.0, description="平均成本")

    # 筹码集中度
    cost_90_low: float = Field(..., ge=0.0, description="90%筹码成本下限")
    cost_90_high: float = Field(..., ge=0.0, description="90%筹码成本上限")
    concentration_90: float = Field(..., ge=0.0, description="90%筹码集中度（越小越集中）")

    cost_70_low: float = Field(..., ge=0.0, description="70%筹码成本下限")
    cost_70_high: float = Field(..., ge=0.0, description="70%筹码成本上限")
    concentration_70: float = Field(..., ge=0.0, description="70%筹码集中度")

    chip_status: str = Field(..., description="筹码状态描述")

    class Config:
        json_schema_extra = {
            "example": {
                "code": "600519",
                "date": "2025-03-11",
                "source": "akshare",
                "profit_ratio": 0.65,
                "avg_cost": 1750.50,
                "cost_90_low": 1700.20,
                "cost_90_high": 1800.80,
                "concentration_90": 0.12,
                "cost_70_low": 1720.30,
                "cost_70_high": 1780.70,
                "concentration_70": 0.08,
                "chip_status": "获利盘中等(50-70%)，筹码较集中，现价略高于成本5.2%"
            }
        }


class SectorRanking(BaseModel):
    """板块排名数据"""

    name: str = Field(..., description="板块名称")
    change_pct: float = Field(..., description="涨跌幅 (%)")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "白酒",
                "change_pct": 3.2
            }
        }


class SectorRankingsResponse(BaseModel):
    """板块排名响应"""

    top_sectors: List[SectorRanking] = Field(default_factory=list, description="涨幅前 N 的板块")
    bottom_sectors: List[SectorRanking] = Field(default_factory=list, description="跌幅前 N 的板块")

    class Config:
        json_schema_extra = {
            "example": {
                "top_sectors": [
                    {"name": "白酒", "change_pct": 3.2},
                    {"name": "半导体", "change_pct": 2.8}
                ],
                "bottom_sectors": [
                    {"name": "煤炭", "change_pct": -1.5},
                    {"name": "房地产", "change_pct": -2.1}
                ]
            }
        }


class StockSectorInfo(BaseModel):
    """板块详细信息"""
    # 动态字段，允许额外字段
    class Config:
        extra = "allow"


class StockSectorResponse(BaseModel):
    """股票所属板块响应"""
    stock_code: str = Field(..., description="股票代码")
    sectors: List[StockSectorInfo] = Field(default_factory=list, description="所属板块列表")
    count: int = Field(..., description="板块数量")
