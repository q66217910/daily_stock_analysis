# -*- coding: utf-8 -*-
"""
===================================
价格盯盘 API
===================================

职责：
1. 启动/停止盯盘服务
2. 获取/添加/删除盯盘股票
3. 获取价格提醒历史
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends, Body

from api.deps import get_database_manager
from api.v1.schemas.price_monitor import (
    WatchingStockCreate,
    WatchingStockUpdate,
    WatchingStockResponse,
    WatchingStockListResponse,
    PriceAlertResponse,
    PriceAlertListResponse,
    MonitorStatusResponse,
    MonitorOperationResponse,
    RefreshRequest,
)
from api.v1.schemas.common import ErrorResponse
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter()


def get_monitor_service():
    """获取盯盘服务实例"""
    from src.services.price_monitor_service import get_price_monitor
    return get_price_monitor()


@router.get(
    "/status",
    response_model=MonitorStatusResponse,
    responses={
        200: {"description": "盯盘服务状态"},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取盯盘服务状态",
    description="获取价格盯盘服务的运行状态和统计信息"
)
def get_monitor_status(
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> MonitorStatusResponse:
    """获取盯盘服务状态"""
    try:
        monitor = get_monitor_service()
        status = monitor.get_status()
        return MonitorStatusResponse(**status)
    except Exception as e:
        logger.error(f"获取盯盘状态失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取盯盘状态失败: {str(e)}"
            }
        )


@router.post(
    "/start",
    response_model=MonitorOperationResponse,
    responses={
        200: {"description": "操作结果"},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="启动盯盘服务",
    description="启动价格盯盘服务，开始监控股票价格"
)
def start_monitor(
    auto_refresh: bool = Query(True, description="是否自动刷新盯盘列表"),
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> MonitorOperationResponse:
    """启动盯盘服务"""
    try:
        monitor = get_monitor_service()
        success = monitor.start(auto_refresh=auto_refresh)
        if success:
            return MonitorOperationResponse(
                success=True,
                message="盯盘服务已启动"
            )
        else:
            return MonitorOperationResponse(
                success=False,
                message="盯盘服务启动失败或已在运行中"
            )
    except Exception as e:
        logger.error(f"启动盯盘服务失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"启动盯盘服务失败: {str(e)}"
            }
        )


@router.post(
    "/stop",
    response_model=MonitorOperationResponse,
    responses={
        200: {"description": "操作结果"},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="停止盯盘服务",
    description="停止价格盯盘服务"
)
def stop_monitor(
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> MonitorOperationResponse:
    """停止盯盘服务"""
    try:
        monitor = get_monitor_service()
        monitor.stop()
        return MonitorOperationResponse(
            success=True,
            message="盯盘服务已停止"
        )
    except Exception as e:
        logger.error(f"停止盯盘服务失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"停止盯盘服务失败: {str(e)}"
            }
        )


@router.post(
    "/refresh",
    response_model=MonitorOperationResponse,
    responses={
        200: {"description": "操作结果"},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="刷新盯盘列表",
    description="从最近的分析历史中刷新盯盘列表，自动添加高分股票"
)
def refresh_watching_list(
    request: RefreshRequest = Body(None),
    min_score: int = Query(85, ge=0, le=100, description="最低评分"),
    days: int = Query(2, ge=1, le=30, description="回溯天数"),
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> MonitorOperationResponse:
    """刷新盯盘列表"""
    try:
        monitor = get_monitor_service()
        # 优先使用请求体中的参数，如果没有则使用查询参数
        use_min_score = request.min_score if request else min_score
        use_days = request.days if request else days
        added = monitor.refresh_watching_list(
            min_score=use_min_score,
            days=use_days
        )
        return MonitorOperationResponse(
            success=True,
            message=f"刷新完成，新增 {added} 只盯盘股票"
        )
    except Exception as e:
        logger.error(f"刷新盯盘列表失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"刷新盯盘列表失败: {str(e)}"
            }
        )


@router.get(
    "/watching",
    response_model=WatchingStockListResponse,
    responses={
        200: {"description": "盯盘股票列表"},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取盯盘股票列表",
    description="分页获取当前盯盘的股票列表"
)
def get_watching_list(
    min_score: int = Query(0, ge=0, le=100, description="最低评分筛选"),
    only_active: bool = Query(False, description="仅显示活跃的"),
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> WatchingStockListResponse:
    """获取盯盘股票列表"""
    try:
        monitor = get_monitor_service()

        # 对于简单查询，直接从服务获取活跃列表
        if min_score > 0 or (only_active and page == 1 and limit >= 100):
            stocks = monitor.get_watching_list(min_score=min_score if min_score > 0 else 0)
            items = [
                WatchingStockResponse(**s)
                for s in stocks
            ]
            return WatchingStockListResponse(
                total=len(items),
                page=1,
                limit=len(items),
                items=items
            )

        # 否则从数据库分页查询
        offset = (page - 1) * limit
        stocks, total = db_manager.get_watching_stocks_paginated(
            offset=offset,
            limit=limit,
            only_active=only_active,
        )
        items = [
            WatchingStockResponse.from_dict(s.to_dict())
            for s in stocks
        ]
        return WatchingStockListResponse(
            total=total,
            page=page,
            limit=limit,
            items=items
        )
    except Exception as e:
        logger.error(f"获取盯盘列表失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取盯盘列表失败: {str(e)}"
            }
        )


@router.post(
    "/watching",
    response_model=WatchingStockResponse,
    responses={
        200: {"description": "添加成功"},
        400: {"description": "请求参数错误", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="添加盯盘股票",
    description="手动添加股票到盯盘列表"
)
def add_watching_stock(
    request: WatchingStockCreate = Body(...),
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> WatchingStockResponse:
    """添加盯盘股票"""
    try:
        from datetime import date
        monitor = get_monitor_service()

        watching = monitor.add_to_watching(
            code=request.code,
            name=request.name or "",
            sentiment_score=request.sentiment_score,
            ideal_buy=request.ideal_buy,
            secondary_buy=request.secondary_buy,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            analysis_history_id=request.analysis_history_id,
        )

        if watching:
            return WatchingStockResponse(**watching)
        else:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "already_exists",
                    "message": "该股票在该分析日期已在盯盘列表中"
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加盯盘股票失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"添加盯盘股票失败: {str(e)}"
            }
        )


@router.delete(
    "/watching/{watching_id}",
    response_model=MonitorOperationResponse,
    responses={
        200: {"description": "删除成功"},
        404: {"description": "记录不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="删除盯盘股票",
    description="从盯盘列表中删除指定股票"
)
def delete_watching_stock(
    watching_id: int,
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> MonitorOperationResponse:
    """删除盯盘股票"""
    try:
        monitor = get_monitor_service()
        success = monitor.remove_from_watching(watching_id)
        if success:
            return MonitorOperationResponse(
                success=True,
                message="删除成功"
            )
        else:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": "盯盘记录不存在"
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除盯盘股票失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"删除盯盘股票失败: {str(e)}"
            }
        )


@router.delete(
    "/watching",
    response_model=MonitorOperationResponse,
    responses={
        200: {"description": "删除成功"},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="删除所有盯盘股票",
    description="清空盯盘列表中的所有股票"
)
def delete_all_watching_stocks(
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> MonitorOperationResponse:
    """删除所有盯盘股票"""
    try:
        monitor = get_monitor_service()
        count = monitor.remove_all_from_watching()
        return MonitorOperationResponse(
            success=True,
            message=f"已删除 {count} 只盯盘股票"
        )
    except Exception as e:
        logger.error(f"删除所有盯盘股票失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"删除所有盯盘股票失败: {str(e)}"
            }
        )


@router.patch(
    "/watching/{watching_id}/activate",
    response_model=MonitorOperationResponse,
    responses={
        200: {"description": "操作成功"},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="激活盯盘股票",
    description="激活指定的盯盘股票"
)
def activate_watching_stock(
    watching_id: int,
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> MonitorOperationResponse:
    """激活盯盘股票"""
    try:
        success = db_manager.update_watching_stock_active(watching_id, True)
        if success:
            return MonitorOperationResponse(
                success=True,
                message="已激活"
            )
        else:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": "盯盘记录不存在"
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"激活盯盘股票失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"激活盯盘股票失败: {str(e)}"
            }
        )


@router.patch(
    "/watching/{watching_id}/deactivate",
    response_model=MonitorOperationResponse,
    responses={
        200: {"description": "操作成功"},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="停用盯盘股票",
    description="停用指定的盯盘股票"
)
def deactivate_watching_stock(
    watching_id: int,
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> MonitorOperationResponse:
    """停用盯盘股票"""
    try:
        success = db_manager.update_watching_stock_active(watching_id, False)
        if success:
            return MonitorOperationResponse(
                success=True,
                message="已停用"
            )
        else:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": "盯盘记录不存在"
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"停用盯盘股票失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"停用盯盘股票失败: {str(e)}"
            }
        )


@router.get(
    "/alerts",
    response_model=PriceAlertListResponse,
    responses={
        200: {"description": "价格提醒历史"},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取价格提醒历史",
    description="分页获取价格提醒历史记录"
)
def get_price_alerts(
    code: Optional[str] = Query(None, description="股票代码筛选"),
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> PriceAlertListResponse:
    """获取价格提醒历史"""
    try:
        offset = (page - 1) * limit
        alerts, total = db_manager.get_price_alerts_paginated(
            code=code,
            offset=offset,
            limit=limit,
        )
        items = [
            PriceAlertResponse(**a.to_dict())
            for a in alerts
        ]
        return PriceAlertListResponse(
            total=total,
            page=page,
            limit=limit,
            items=items
        )
    except Exception as e:
        logger.error(f"获取价格提醒失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取价格提醒失败: {str(e)}"
            }
        )
