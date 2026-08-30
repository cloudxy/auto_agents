"""V2 健康检查 - 增强的监控功能"""
import asyncio
import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.db import get_async_db, redis_client
from platform_core.logger import get_logger
from platform_core.storage import get_storage

router = APIRouter()

@router.get("/")
async def health():
    """V2 基础健康检查 - 真实测量请求处理耗时"""
    logger = get_logger("api")
    start = time.perf_counter()
    body = {
        "status": "healthy",
        "version": "2.0.0",
    }
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.debug(f"Health check: {elapsed_ms}ms")
    return {**body, "response_time_ms": elapsed_ms}

@router.get("/db")
async def health_db(session: AsyncSession = Depends(get_async_db)):
    """V2 数据库健康检查 - async MySQL 会话 + Redis（同步客户端走线程池）"""
    logger = get_logger("api")
    try:
        start = time.perf_counter()

        # 测试 MySQL（async 会话执行探活查询）
        await session.execute(text("SELECT 1"))

        # 测试 Redis（同步客户端，避免阻塞事件循环）
        r = redis_client("DEFAULT")
        await asyncio.to_thread(r.ping)

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        logger.info(f"Database health check passed: {elapsed_ms}ms")

        return {
            "status": "healthy",
            "version": "2.0.0",
            "database": {
                "mysql": "connected",
                "redis": "connected"
            },
            "response_time_ms": elapsed_ms
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "version": "2.0.0",
            "error": str(e)
        }

@router.get("/storage")
async def health_storage():
    """V2 存储系统健康检查"""
    logger = get_logger("api")
    try:
        storage = get_storage()
        test_file = storage.create_temp("health_test_", ".tmp")
        test_file.unlink()
        
        logger.info("Storage health check passed")
        
        return {
            "status": "healthy",
            "version": "2.0.0",
            "storage": "filesystem"
        }
    except Exception as e:
        logger.error(f"Storage health check failed: {e}")
        return {
            "status": "unhealthy",
            "version": "2.0.0",
            "error": str(e)
        }
