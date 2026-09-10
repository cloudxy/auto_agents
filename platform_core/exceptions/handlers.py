"""异常处理器 - 将异常转换为统一 JSON 响应"""
import uuid
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from platform_core.logger import get_logger
from platform_core.exceptions.base import AppException

logger = get_logger("error")


async def app_exception_handler(request: Request, exc: AppException):
    """处理所有应用级异常（AppException 及其子类）"""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4())[:8])
    
    if exc.status_code >= 500:
        logger.error(
            f"服务器异常 | request_id={request_id} | "
            f"code={exc.code} | message={exc.message}",
            exc_info=True
        )
    else:
        logger.warning(
            f"客户端异常 | request_id={request_id} | "
            f"code={exc.code} | message={exc.message}"
        )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "code": exc.code,
            "message": exc.message,
            "data": exc.data,
            "request_id": request_id,
        }
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    """处理 FastAPI HTTP 异常"""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4())[:8])
    
    logger.warning(
        f"HTTP 异常 | request_id={request_id} | "
        f"status={exc.status_code} | detail={exc.detail}"
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "code": f"HTTP_{exc.status_code}",
            "message": exc.detail,
            "data": {},
            "request_id": request_id,
        }
    )


async def validation_exception_handler(request: Request, exc):
    """处理 Pydantic 验证异常（422）"""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4())[:8])
    
    errors = exc.errors()
    first_error = errors[0] if errors else {}
    field = ".".join(str(loc) for loc in first_error.get("loc", []))
    error_msg = first_error.get("msg", "参数验证失败")
    
    logger.warning(
        f"参数验证失败 | request_id={request_id} | "
        f"field={field} | error={error_msg}"
    )
    
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "code": "VALIDATION_ERROR",
            "message": error_msg,
            "data": {
                "field": field,
                "errors": [{"field": ".".join(str(loc) for loc in e.get("loc", [])), "message": e.get("msg")} for e in errors]
            },
            "request_id": request_id,
        }
    )


async def general_exception_handler(request: Request, exc: Exception):
    """处理未捕获的通用异常（兜底）"""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4())[:8])

    # 用 opt(exception=...) 记录堆栈：异常 message 可能含 SQL 参数花括号，
    # 若走 loguru 的位置参数 format（exc_info=True）会触发 KeyError
    logger.opt(exception=exc).error(
        f"未捕获异常 | request_id={request_id} | "
        f"type={type(exc).__name__} | message={str(exc)}"
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "code": "INTERNAL_SERVER_ERROR",
            "message": "服务器内部错误，请联系管理员",
            "data": {},
            "request_id": request_id,
        }
    )


def register_exception_handlers(app):
    """注册所有异常处理器到 FastAPI 应用
    
    注册顺序：从具体到通用
    """
    from fastapi.exceptions import RequestValidationError
    
    # 1. Pydantic 验证异常（最具体）
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    
    # 2. 应用级异常（AppException 及其子类）
    app.add_exception_handler(AppException, app_exception_handler)
    
    # 3. FastAPI HTTP 异常
    app.add_exception_handler(HTTPException, http_exception_handler)
    
    # 4. 通用异常（兜底）
    app.add_exception_handler(Exception, general_exception_handler)
