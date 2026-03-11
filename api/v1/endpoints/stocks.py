# -*- coding: utf-8 -*-
"""
===================================
股票数据接口
===================================

职责：
1. POST /api/v1/stocks/extract-from-image 从图片提取股票代码
2. POST /api/v1/stocks/parse-import 解析 CSV/Excel/剪贴板
3. GET /api/v1/stocks/{code}/quote 实时行情接口
4. GET /api/v1/stocks/{code}/history 历史行情接口
5. GET /api/v1/stocks/{code}/chip-distribution 筹码分布接口
6. GET /api/v1/stocks/{code}/bollinger BOLL线数据接口
7. GET /api/v1/stocks/{code}/news 获取股票相关资讯
"""

import logging
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile

from api.v1.schemas.stocks import (
    BollingerData,
    BollingerResponse,
    ChipDistribution,
    ExtractFromImageResponse,
    ExtractItem,
    KLineData,
    RealtimeTradeQuote,
    SectorRankingsResponse,
    StockHistoryResponse,
    StockNewsItem,
    StockNewsResponse,
    StockQuote,
    StockSectorResponse,
)
from api.v1.schemas.common import ErrorResponse
from src.config import Config
from src.search_service import SearchService
from src.services.image_stock_extractor import (
    ALLOWED_MIME,
    MAX_SIZE_BYTES,
    extract_stock_codes_from_image,
)
from src.services.import_parser import (
    MAX_FILE_BYTES,
    parse_import_from_bytes,
    parse_import_from_text,
)
from src.services.stock_service import StockService

logger = logging.getLogger(__name__)

router = APIRouter()

# 须在 /{stock_code} 路由之前定义
ALLOWED_MIME_STR = ", ".join(ALLOWED_MIME)


@router.post(
    "/extract-from-image",
    response_model=ExtractFromImageResponse,
    responses={
        200: {"description": "提取的股票代码"},
        400: {"description": "图片无效", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="从图片提取股票代码",
    description="上传截图/图片，通过 Vision LLM 提取股票代码。支持 JPEG、PNG、WebP、GIF，最大 5MB。",
)
def extract_from_image(
    file: Optional[UploadFile] = File(None, description="图片文件（表单字段名 file）"),
    include_raw: bool = Query(False, description="是否在结果中包含原始 LLM 响应"),
) -> ExtractFromImageResponse:
    """
    从上传的图片中提取股票代码（使用 Vision LLM）。

    表单字段请使用 file 上传图片。优先级：Gemini / Anthropic / OpenAI（首个可用）。
    """
    if not file or not file.filename:
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_request", "message": "未提供文件，请使用表单字段 file 上传图片"},
        )

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_type",
                "message": f"不支持的类型: {content_type}。允许: {ALLOWED_MIME_STR}",
            },
        )

    try:
        # 先读取限定大小，再检查是否还有剩余（语义清晰：超出则拒绝）
        data = file.file.read(MAX_SIZE_BYTES)
        if file.file.read(1):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "file_too_large",
                    "message": f"图片超过 {MAX_SIZE_BYTES // (1024 * 1024)}MB 限制",
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"读取上传文件失败: {e}")
        raise HTTPException(
            status_code=400,
            detail={"error": "read_failed", "message": "读取上传文件失败"},
        )

    try:
        items, raw_text = extract_stock_codes_from_image(data, content_type)
        extract_items = [
            ExtractItem(code=code, name=name, confidence=conf) for code, name, conf in items
        ]
        codes = [i.code for i in extract_items]
        return ExtractFromImageResponse(
            codes=codes,
            items=extract_items,
            raw_text=raw_text if include_raw else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "extract_failed", "message": str(e)})
    except Exception as e:
        logger.error(f"图片提取失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "图片提取失败"},
        )


@router.post(
    "/parse-import",
    response_model=ExtractFromImageResponse,
    responses={
        200: {"description": "解析结果"},
        400: {"description": "未提供数据或解析失败", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="解析 CSV/Excel/剪贴板",
    description="上传 CSV/Excel 文件或粘贴文本，自动解析股票代码。文件上限 2MB，文本上限 100KB。",
)
async def parse_import(request: Request) -> ExtractFromImageResponse:
    """
    解析 CSV/Excel 文件或剪贴板文本。

    - multipart/form-data + file: 上传文件
    - application/json + {"text": "..."}: 粘贴文本
    - 优先使用 file，若同时提供则忽略 text
    """
    content_type = (request.headers.get("content-type") or "").lower()

    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception as e:
            logger.warning("[parse_import] JSON parse failed: %s", e)
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_json", "message": f"JSON 解析失败: {e}"},
            )
        text = body.get("text") if isinstance(body, dict) else None
        if not text or not isinstance(text, str):
            raise HTTPException(
                status_code=400,
                detail={"error": "bad_request", "message": "未提供 text，请使用 {\"text\": \"...\"}"},
            )
        try:
            items = parse_import_from_text(text)
        except ValueError as e:
            text_bytes = len(text.encode("utf-8"))
            logger.warning(
                "[parse_import] parse_import_from_text failed: text_bytes=%d, error=%s",
                text_bytes,
                e,
            )
            raise HTTPException(status_code=400, detail={"error": "parse_failed", "message": str(e)})
    elif "multipart" in content_type:
        form = await request.form()
        file = form.get("file")
        if not file or not hasattr(file, "read"):
            raise HTTPException(
                status_code=400,
                detail={"error": "bad_request", "message": "未提供文件，请使用表单字段 file"},
            )
        file_size = getattr(file, "size", None)
        if isinstance(file_size, int) and file_size > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "file_too_large",
                    "message": f"文件超过 {MAX_FILE_BYTES // (1024 * 1024)}MB 限制",
                },
            )
        try:
            data = file.file.read(MAX_FILE_BYTES)
            if file.file.read(1):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "file_too_large",
                        "message": f"文件超过 {MAX_FILE_BYTES // (1024 * 1024)}MB 限制",
                    },
                )
        except HTTPException:
            raise
        except Exception as e:
            filename = getattr(file, "filename", None) or ""
            size = getattr(file, "size", None)
            logger.warning(
                "[parse_import] file read failed: filename=%r, size=%s, error=%s",
                filename,
                size,
                e,
            )
            raise HTTPException(
                status_code=400,
                detail={"error": "read_failed", "message": "读取文件失败"},
            )
        filename = getattr(file, "filename", None) or ""
        try:
            items = parse_import_from_bytes(data, filename=filename)
        except ValueError as e:
            ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            logger.warning(
                "[parse_import] parse_import_from_bytes failed: filename=%r, ext=%r, bytes=%d, error=%s",
                filename,
                ext,
                len(data),
                e,
            )
            raise HTTPException(status_code=400, detail={"error": "parse_failed", "message": str(e)})
    else:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "bad_request",
                "message": "请使用 multipart/form-data 上传文件，或 application/json 提交 {\"text\": \"...\"}",
            },
        )

    extract_items = [
        ExtractItem(code=code, name=name, confidence=conf)
        for code, name, conf in items
    ]
    codes = list(dict.fromkeys(i.code for i in extract_items if i.code))
    return ExtractFromImageResponse(codes=codes, items=extract_items, raw_text=None)


@router.get(
    "/{stock_code}/quote",
    response_model=StockQuote,
    responses={
        200: {"description": "行情数据"},
        404: {"description": "股票不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取股票实时行情",
    description="获取指定股票的最新行情数据"
)
def get_stock_quote(stock_code: str) -> StockQuote:
    """
    获取股票实时行情
    
    获取指定股票的最新行情数据
    
    Args:
        stock_code: 股票代码（如 600519、00700、AAPL）
        
    Returns:
        StockQuote: 实时行情数据
        
    Raises:
        HTTPException: 404 - 股票不存在
    """
    try:
        service = StockService()
        
        # 使用 def 而非 async def，FastAPI 自动在线程池中执行
        result = service.get_realtime_quote(stock_code)
        
        if result is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": f"未找到股票 {stock_code} 的行情数据"
                }
            )

        logger.info(result)

        return StockQuote(
            stock_code=result.get("stock_code", stock_code),
            stock_name=result.get("stock_name"),
            current_price=result.get("current_price", 0.0),
            change=result.get("change"),
            change_percent=result.get("change_percent"),
            open=result.get("open"),
            high=result.get("high"),
            low=result.get("low"),
            prev_close=result.get("prev_close"),
            volume=result.get("volume"),
            amount=result.get("amount"),
            volume_ratio=result.get("volume_ratio"),
            turnover_rate=result.get("turnover_rate"),
            pe_ratio=result.get("pe_ratio"),
            pb_ratio=result.get("pb_ratio"),
            total_mv=result.get("total_mv"),
            circ_mv=result.get("circ_mv"),
            amplitude=result.get("amplitude"),
            update_time=result.get("update_time")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取实时行情失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取实时行情失败: {str(e)}"
            }
        )


@router.get(
    "/{stock_code}/history",
    response_model=StockHistoryResponse,
    responses={
        200: {"description": "历史行情数据"},
        422: {"description": "不支持的周期参数", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取股票历史行情",
    description="获取指定股票的历史 K 线数据"
)
def get_stock_history(
    stock_code: str,
    period: str = Query("daily", description="K 线周期", pattern="^(daily|weekly|monthly)$"),
    days: int = Query(30, ge=1, le=365, description="获取天数")
) -> StockHistoryResponse:
    """
    获取股票历史行情
    
    获取指定股票的历史 K 线数据
    
    Args:
        stock_code: 股票代码
        period: K 线周期 (daily/weekly/monthly)
        days: 获取天数
        
    Returns:
        StockHistoryResponse: 历史行情数据
    """
    try:
        service = StockService()
        
        # 使用 def 而非 async def，FastAPI 自动在线程池中执行
        result = service.get_history_data(
            stock_code=stock_code,
            period=period,
            days=days
        )
        
        # 转换为响应模型
        data = [
            KLineData(
                date=item.get("date"),
                open=item.get("open"),
                high=item.get("high"),
                low=item.get("low"),
                close=item.get("close"),
                volume=item.get("volume"),
                amount=item.get("amount"),
                change_percent=item.get("change_percent")
            )
            for item in result.get("data", [])
        ]
        
        return StockHistoryResponse(
            stock_code=stock_code,
            stock_name=result.get("stock_name"),
            period=period,
            data=data
        )
    
    except ValueError as e:
        # period 参数不支持的错误（如 weekly/monthly）
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unsupported_period",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error(f"获取历史行情失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取历史行情失败: {str(e)}"
            }
        )


@router.get(
    "/{stock_code}/chip-distribution",
    response_model=ChipDistribution,
    responses={
        200: {"description": "筹码分布数据"},
        404: {"description": "股票不存在或筹码数据不可用", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取股票筹码分布",
    description="获取指定股票的筹码分布数据（获利比例、平均成本、筹码集中度等）"
)
def get_chip_distribution(stock_code: str) -> ChipDistribution:
    """
    获取股票筹码分布

    获取指定股票的筹码分布数据，包括获利比例、平均成本、筹码集中度等。

    Args:
        stock_code: 股票代码（如 600519、00700、AAPL）

    Returns:
        ChipDistribution: 筹码分布数据

    Raises:
        HTTPException: 404 - 股票不存在或筹码数据不可用
    """
    try:
        service = StockService()

        # 使用 StockService 获取筹码分布
        result = service.get_chip_distribution(stock_code)

        if result is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": f"未找到股票 {stock_code} 的筹码分布数据"
                }
            )

        return ChipDistribution(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取筹码分布失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取筹码分布失败: {str(e)}"
            }
        )


@router.get(
    "/sector-rankings",
    response_model=SectorRankingsResponse,
    responses={
        200: {"description": "板块排名数据"},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取板块排名",
    description="获取涨幅前N和跌幅前N的板块排名数据"
)
def get_sector_rankings(n: int = Query(5, ge=1, le=20, description="排名数量，默认前5名和后5名")) -> SectorRankingsResponse:
    """
    获取板块排名数据

    获取涨幅前N和跌幅前N的板块排名数据。

    Args:
        n: 排名数量，默认前5名和后5名

    Returns:
        SectorRankingsResponse: 板块排名数据
    """
    try:
        service = StockService()

        # 使用 def 而非 async def，FastAPI 自动在线程池中执行
        result = service.get_sector_rankings(n)

        return SectorRankingsResponse(
            top_sectors=result.get("top_sectors", []),
            bottom_sectors=result.get("bottom_sectors", [])
        )

    except Exception as e:
        logger.error(f"获取板块排名失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取板块排名失败: {str(e)}"
            }
        )


@router.get(
    "/{stock_code}/sectors",
    response_model=StockSectorResponse,
    responses={
        200: {"description": "股票所属板块信息"},
        404: {"description": "股票不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取股票所属板块",
    description="获取指定股票所属板块的详细信息，包括板块名称、涨跌幅等"
)
def get_stock_sectors(stock_code: str) -> StockSectorResponse:
    """
    获取股票所属板块信息

    获取指定股票所属板块的详细信息，包括板块名称、涨跌幅等。

    Args:
        stock_code: 股票代码（如 600519、00700、AAPL）

    Returns:
        StockSectorResponse: 股票所属板块信息

    Raises:
        HTTPException: 404 - 股票不存在
    """
    try:
        service = StockService()

        # 使用 def 而非 async def，FastAPI 自动在线程池中执行
        result = service.get_stock_sectors(stock_code)

        if result is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": f"未找到股票 {stock_code} 的板块信息"
                }
            )

        return StockSectorResponse(
            stock_code=result.get("stock_code", stock_code),
            sectors=result.get("sectors", []),
            count=result.get("count", 0)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取股票板块信息失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取股票板块信息失败: {str(e)}"
            }
        )


@router.get(
    "/{stock_code}/bollinger",
    response_model=BollingerResponse,
    responses={
        200: {"description": "BOLL线数据"},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取股票BOLL线数据",
    description="获取指定股票的BOLL线（布林线）数据，包括上轨、中轨、下轨、带宽和%B指标"
)
def get_bollinger_bands(
    stock_code: str,
    period: int = Query(20, ge=5, le=100, description="BOLL周期（默认20）"),
    std_dev: float = Query(2.0, ge=0.5, le=5.0, description="标准差倍数（默认2）"),
    days: int = Query(60, ge=1, le=365, description="获取天数（默认60）")
) -> BollingerResponse:
    """
    获取股票BOLL线（布林线）数据

    BOLL线计算公式：
    - 中轨线（Middle）= N日移动平均线（默认20日）
    - 上轨线（Upper）= 中轨线 + K × N日收盘价的标准差（K默认2）
    - 下轨线（Lower）= 中轨线 - K × N日收盘价的标准差
    - 带宽（Bandwidth）= (上轨 - 下轨) / 中轨
    - %B指标 = (收盘价 - 下轨) / (上轨 - 下轨)

    Args:
        stock_code: 股票代码（如 600519、00700、AAPL）
        period: BOLL周期（默认20，范围5-100）
        std_dev: 标准差倍数（默认2.0，范围0.5-5.0）
        days: 获取天数（默认60，范围1-365）

    Returns:
        BollingerResponse: BOLL线数据响应
    """
    try:
        service = StockService()

        # 使用 def 而非 async def，FastAPI 自动在线程池中执行
        result = service.get_bollinger_bands(
            stock_code=stock_code,
            period=period,
            std_dev=std_dev,
            days=days
        )

        # 转换为响应模型
        data = [
            BollingerData(
                date=item.get("date"),
                close=item.get("close"),
                middle=item.get("middle"),
                upper=item.get("upper"),
                lower=item.get("lower"),
                bandwidth=item.get("bandwidth"),
                percent_b=item.get("percent_b")
            )
            for item in result.get("data", [])
        ]

        latest_data = None
        latest_dict = result.get("latest")
        if latest_dict:
            latest_data = BollingerData(
                date=latest_dict.get("date"),
                close=latest_dict.get("close"),
                middle=latest_dict.get("middle"),
                upper=latest_dict.get("upper"),
                lower=latest_dict.get("lower"),
                bandwidth=latest_dict.get("bandwidth"),
                percent_b=latest_dict.get("percent_b")
            )

        return BollingerResponse(
            stock_code=result.get("stock_code", stock_code),
            stock_name=result.get("stock_name"),
            period=result.get("period", period),
            std_dev=result.get("std_dev", std_dev),
            data=data,
            latest=latest_data,
            position=result.get("position")
        )

    except Exception as e:
        logger.error(f"获取BOLL线数据失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取BOLL线数据失败: {str(e)}"
            }
        )


@router.get(
    "/{stock_code}/trade-quote",
    response_model=RealtimeTradeQuote,
    responses={
        200: {"description": "实时交易数据"},
        404: {"description": "股票不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取股票实时交易数据（精简字段版）",
    description="获取指定股票的实时交易数据，包含精简的字段格式"
)
def get_stock_trade_quote(stock_code: str) -> RealtimeTradeQuote:
    """
    获取股票实时交易数据（精简字段版）

    获取指定股票的实时交易数据，返回字段包括：
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

    Args:
        stock_code: 股票代码（如 600519、00700、AAPL）

    Returns:
        RealtimeTradeQuote: 实时交易数据

    Raises:
        HTTPException: 404 - 股票不存在
    """
    try:
        service = StockService()

        # 使用 def 而非 async def，FastAPI 自动在线程池中执行
        result = service.get_realtime_trade_quote(stock_code)

        if result is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": f"未找到股票 {stock_code} 的实时交易数据"
                }
            )

        return RealtimeTradeQuote(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取实时交易数据失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取实时交易数据失败: {str(e)}"
            }
        )


@router.get(
    "/{stock_code}/news",
    response_model=StockNewsResponse,
    responses={
        200: {"description": "股票新闻资讯"},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取股票相关资讯",
    description="搜索并获取指定股票的相关新闻资讯"
)
def get_stock_news(
    stock_code: str,
    max_results: int = Query(5, ge=1, le=20, description="返回新闻条数，默认5条"),
    stock_name: Optional[str] = Query(None, description="股票名称（可选，不传则自动获取）"),
) -> StockNewsResponse:
    """
    获取股票相关资讯

    搜索并获取指定股票的相关新闻资讯。

    Args:
        stock_code: 股票代码（如 600519、00700、AAPL）
        max_results: 返回新闻条数，默认5条，最多20条
        stock_name: 股票名称（可选，不传则自动从数据源获取）

    Returns:
        StockNewsResponse: 股票新闻资讯响应
    """
    try:
        config = Config()

        # 如果没有提供股票名称，尝试获取
        if not stock_name:
            try:
                from data_provider.base import DataFetcherManager
                manager = DataFetcherManager()
                stock_name = manager.get_stock_name(stock_code)
            except Exception as e:
                logger.warning(f"获取股票名称失败: {e}")
                stock_name = f"股票{stock_code}"

        # 初始化搜索服务
        search_service = SearchService(
            bocha_keys=config.bocha_api_keys,
            tavily_keys=config.tavily_api_keys,
            anspire_keys=config.anspire_api_keys,
            brave_keys=config.brave_api_keys,
            serpapi_keys='',
            minimax_keys=config.minimax_api_keys,
            searxng_base_urls=["https://searxng.touchfishes.com"],
            searxng_public_instances_enabled=config.searxng_public_instances_enabled,
            news_max_age_days=config.news_max_age_days,
            news_strategy_profile=config.news_strategy_profile,
        )

        # 搜索股票新闻
        response = search_service.search_stock_news(
            stock_code=stock_code,
            stock_name=stock_name,
            max_results=max_results,
        )

        # 转换结果
        news_items = [
            StockNewsItem(
                title=item.title,
                snippet=item.snippet,
                url=item.url,
                source=item.source,
                published_date=item.published_date,
            )
            for item in response.results
        ]

        return StockNewsResponse(
            stock_code=stock_code,
            stock_name=stock_name,
            query=response.query,
            results=news_items,
            provider=response.provider,
            success=response.success,
            error_message=response.error_message,
            search_time=response.search_time,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取股票资讯失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取股票资讯失败: {str(e)}"
            }
        )
