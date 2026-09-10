"""V2 健康检查 - 增强的监控功能

P1-10 修复（2026-08-31）：v2 不再复制 v1 的探测实现（旧副本保留了 v1 已修复的
缺陷——error 回显内部异常全文、storage 探测在事件循环内做同步文件 IO）。
本模块只做 v1 探测的组合与版本化包装，探测逻辑单一事实源在 v1/health.py。
"""
import time

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.v1 import health as v1_health
from platform_core.db import get_async_db
from platform_core.logger import get_logger

router = APIRouter()

_VERSION = "2.0.0"


@router.get("/")
async def health():
    """V2 基础健康检查 - 真实测量请求处理耗时"""
    logger = get_logger("api")
    start = time.perf_counter()
    body = {
        "status": "healthy",
        "version": _VERSION,
    }
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.debug(f"Health check: {elapsed_ms}ms")
    return {**body, "response_time_ms": elapsed_ms}


@router.get("/db")
async def health_db(session: AsyncSession = Depends(get_async_db)):
    """V2 数据库健康检查 - MySQL（v1 探测）+ Redis（v1 异步 ping）组合"""
    logger = get_logger("api")
    start = time.perf_counter()
    mysql_res = await v1_health.health_db(session)
    redis_res = await v1_health.health_redis()
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

    healthy = mysql_res["status"] == "healthy" and redis_res["status"] == "healthy"
    payload = {
        "status": "healthy" if healthy else "unhealthy",
        "version": _VERSION,
        "database": {
            "mysql": mysql_res["status"],
            "redis": redis_res["status"],
        },
        "response_time_ms": elapsed_ms,
    }
    if not healthy:
        # 错误仅暴露异常类型名（细节走日志，与 v1 收窄口径一致）
        payload["error"] = ",".join(
            res.get("error", "unknown")
            for res in (mysql_res, redis_res)
            if res["status"] != "healthy"
        )
        logger.error(f"Database health check failed: mysql={mysql_res}, redis={redis_res}")
    else:
        logger.info(f"Database health check passed: {elapsed_ms}ms")
    return payload


@router.get("/storage")
async def health_storage():
    """V2 存储系统健康检查（复用 v1 探测：同步文件 IO 已下沉线程池）"""
    logger = get_logger("api")
    res = await v1_health.health_storage()
    if res["status"] == "healthy":
        logger.info("Storage health check passed")
        return {"status": "healthy", "version": _VERSION, "storage": "filesystem"}
    logger.error(f"Storage health check failed: {res}")
    return {"status": "unhealthy", "version": _VERSION, "storage": "filesystem",
            "error": res.get("error", "unknown")}
