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


class BollingerData(BaseModel):
    """BOLL线数据点"""

    date: str = Field(..., description="日期")
    close: float = Field(..., description="收盘价")
    middle: float = Field(..., description="中轨线（MA）")
    upper: float = Field(..., description="上轨线")
    lower: float = Field(..., description="下轨线")
    bandwidth: Optional[float] = Field(None, description="带宽（(upper-lower)/middle）")
    percent_b: Optional[float] = Field(None, description="%B指标（(close-lower)/(upper-lower)）")

    class Config:
        json_schema_extra = {
            "example": {
                "date": "2024-01-01",
                "close": 1800.00,
                "middle": 1780.00,
                "upper": 1820.00,
                "lower": 1740.00,
                "bandwidth": 0.0449,
                "percent_b": 0.75
            }
        }


class BollingerResponse(BaseModel):
    """BOLL线数据响应"""

    stock_code: str = Field(..., description="股票代码")
    stock_name: Optional[str] = Field(None, description="股票名称")
    period: int = Field(..., description="BOLL周期（默认20）")
    std_dev: float = Field(..., description="标准差倍数（默认2）")
    data: List[BollingerData] = Field(default_factory=list, description="BOLL线数据列表")
    latest: Optional[BollingerData] = Field(None, description="最新BOLL数据")
    position: Optional[str] = Field(None, description="价格位置描述（上轨上方/上轨附近/中轨附近/下轨附近/下轨下方）")

    class Config:
        json_schema_extra = {
            "example": {
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "period": 20,
                "std_dev": 2,
                "data": [],
                "latest": None,
                "position": "中轨附近"
            }
        }


class RealtimeTradeQuote(BaseModel):
    """实时股票交易数据（精简字段版）"""

    t: Optional[str] = Field(None, description="更新时间 yyyy-MM-ddHH:mm:ss", alias="t")
    p: Optional[float] = Field(None, description="当前价格（元）", alias="p")
    o: Optional[float] = Field(None, description="开盘价（元）", alias="o")
    h: Optional[float] = Field(None, description="最高价（元）", alias="h")
    l: Optional[float] = Field(None, description="最低价（元）", alias="l")
    yc: Optional[float] = Field(None, description="昨日收盘价（元）", alias="yc")
    cje: Optional[float] = Field(None, description="成交额（元）", alias="cje")
    v: Optional[float] = Field(None, description="成交量（手）", alias="v")
    ud: Optional[float] = Field(None, description="涨跌额（元）", alias="ud")
    pe: Optional[float] = Field(None, description="市盈率（动态）", alias="pe")
    zf: Optional[float] = Field(None, description="振幅（%）", alias="zf")
    pc: Optional[float] = Field(None, description="涨跌幅（%）", alias="pc")
    fm: Optional[float] = Field(None, description="五分钟涨跌幅（%）", alias="fm")
    hs: Optional[float] = Field(None, description="换手（%）", alias="hs")
    lb: Optional[float] = Field(None, description="量比（%）", alias="lb")
    lt: Optional[float] = Field(None, description="流通市值（元）", alias="lt")
    zs: Optional[float] = Field(None, description="涨速（%）", alias="zs")
    sjl: Optional[float] = Field(None, description="市净率", alias="sjl")
    zdf60: Optional[float] = Field(None, description="60日涨跌幅（%）", alias="zdf60")
    zdfnc: Optional[float] = Field(None, description="年初至今涨跌幅（%）", alias="zdfnc")
    sz: Optional[float] = Field(None, description="总市值（元）", alias="sz")
    rp: Optional[float] = Field(None, description="复盘股价（元）", alias="rp")

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "t": "2024-01-0115:00:00",
                "p": 1800.00,
                "o": 1785.00,
                "h": 1810.00,
                "l": 1780.00,
                "yc": 1785.00,
                "cje": 18000000000.0,
                "v": 100000.0,
                "ud": 15.00,
                "pe": 35.5,
                "zf": 1.67,
                "pc": 0.84,
                "fm": 0.25,
                "hs": 0.5,
                "lb": 1.2,
                "lt": 2000000000000.0,
                "zs": 0.1,
                "sjl": 8.5,
                "zdf60": 12.5,
                "zdfnc": 8.2,
                "sz": 2500000000000.0,
                "rp": 1800.00
            }
        }


class StockNewsItem(BaseModel):
    """单条股票新闻"""

    title: str = Field(..., description="新闻标题")
    snippet: str = Field(..., description="新闻摘要")
    url: str = Field(..., description="新闻链接")
    source: str = Field(..., description="来源网站")
    published_date: Optional[str] = Field(None, description="发布日期")

    class Config:
        json_schema_extra = {
            "example": {
                "title": "贵州茅台发布2024年一季度财报",
                "snippet": "贵州茅台今日发布2024年一季度财报，营收同比增长15%...",
                "url": "https://example.com/news/12345",
                "source": "财经网",
                "published_date": "2024-04-15"
            }
        }


class StockNewsResponse(BaseModel):
    """股票新闻搜索响应"""

    stock_code: str = Field(..., description="股票代码")
    stock_name: Optional[str] = Field(None, description="股票名称")
    query: str = Field(..., description="搜索查询词")
    results: List[StockNewsItem] = Field(default_factory=list, description="新闻结果列表")
    provider: str = Field(..., description="使用的搜索引擎")
    success: bool = Field(True, description="是否成功")
    error_message: Optional[str] = Field(None, description="错误信息")
    search_time: float = Field(0.0, description="搜索耗时（秒）")

    class Config:
        json_schema_extra = {
            "example": {
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "query": "贵州茅台 600519 股票 最新消息",
                "results": [],
                "provider": "bocha",
                "success": True,
                "error_message": None,
                "search_time": 0.5
            }
        }

