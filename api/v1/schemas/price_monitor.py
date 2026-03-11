# -*- coding: utf-8 -*-
"""
===================================
价格盯盘 API Schema
===================================
"""

from typing import Optional, List, Any
from datetime import date, datetime

from pydantic import BaseModel, Field


class WatchingStockBase(BaseModel):
    """盯盘股票基础模型"""
    code: str = Field(..., description="股票代码")
    name: Optional[str] = Field(None, description="股票名称")
    sentiment_score: int = Field(..., ge=0, le=100, description="评分")
    ideal_buy: float = Field(..., gt=0, description="理想买入价格")
    secondary_buy: Optional[float] = Field(None, description="次级买入价格")
    stop_loss: Optional[float] = Field(None, description="止损价格")
    take_profit: Optional[float] = Field(None, description="止盈价格")
    analysis_history_id: Optional[int] = Field(None, description="关联的分析历史ID")
    note: Optional[str] = Field(None, description="备注")


class WatchingStockCreate(WatchingStockBase):
    """创建盯盘股票请求"""
    analysis_date: Optional[date] = Field(None, description="分析日期")


class WatchingStockUpdate(BaseModel):
    """更新盯盘股票请求"""
    name: Optional[str] = None
    sentiment_score: Optional[int] = Field(None, ge=0, le=100)
    ideal_buy: Optional[float] = Field(None, gt=0)
    secondary_buy: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    is_active: Optional[bool] = None
    note: Optional[str] = None


class WatchingStockResponse(BaseModel):
    """盯盘股票响应"""
    id: int
    code: str
    name: Optional[str]
    sentiment_score: int
    analysis_date: Optional[str]
    ideal_buy: Optional[float]
    secondary_buy: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    analysis_history_id: Optional[int]
    is_active: bool
    triggered: bool
    triggered_at: Optional[str]
    trigger_price: Optional[float]
    note: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]

    @classmethod
    def from_dict(cls, data: dict) -> "WatchingStockResponse":
        return cls(**data)


class WatchingStockListResponse(BaseModel):
    """盯盘股票列表响应"""
    total: int
    page: int
    limit: int
    items: List[WatchingStockResponse]


class PriceAlertResponse(BaseModel):
    """价格提醒响应"""
    id: int
    watching_stock_id: int
    code: str
    name: Optional[str]
    alert_type: str
    target_price: float
    trigger_price: float
    change_pct: Optional[float]
    analysis_triggered: bool
    analysis_query_id: Optional[str]
    notification_sent: bool
    notification_sent_at: Optional[str]
    created_at: Optional[str]


class PriceAlertListResponse(BaseModel):
    """价格提醒列表响应"""
    total: int
    page: int
    limit: int
    items: List[PriceAlertResponse]


class MonitorStatusResponse(BaseModel):
    """盯盘服务状态响应"""
    running: bool
    check_interval_seconds: int
    watching_count: int
    triggered_cache_count: int


class MonitorOperationResponse(BaseModel):
    """盯盘操作响应"""
    success: bool
    message: str


class RefreshRequest(BaseModel):
    """刷新盯盘列表请求"""
    min_score: Optional[int] = Field(None, ge=0, le=100, description="最低评分")
    days: Optional[int] = Field(None, ge=1, le=30, description="回溯天数")
