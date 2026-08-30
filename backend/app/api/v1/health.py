"""健康检查接口

m-3 评审修复（三端点统一）：
- /redis 改异步门面 get_async_redis().ping()（原同步 redis_client 直调阻塞事件循环，R11 同源问题）；
- /storage 同步文件探测（临时文件创建/删除）下沉 asyncio.to_thread 线程池；
- 三端点 unhealthy 分支 error 字段统一收窄为异常类型名（细节走日志，
  与 /db 既有做法对齐；契约变更已登记 ADR-001 白名单例外记录）。
"""
import asyncio

from fastapi import APIRouter, Depends
from platform_core.db import get_async_db
from platform_core.storage import get_storage
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from platform_core.logger import get_logger
from platform_core.redis_async import get_async_redis

router = APIRouter()

@router.get("/")
async def health():
    """基础健康检查"""
    logger = get_logger("api")
    logger.debug("Health check accessed")
    return {"status": "healthy"}

@router.get("/db")
async def health_db(session: AsyncSession = Depends(get_async_db)):
    """数据库健康检查（异步会话执行探活查询，对齐 v2；错误不回显内部细节）"""
    logger = get_logger("api")
    try:
        # 异步会话执行探活查询（同步阻塞调用会卡住事件循环）
        await session.execute(text("SELECT 1"))
        logger.info("Database health check passed")
        return {"status": "healthy", "database": "mysql"}
    except Exception as e:
        # 仅记入日志（含连接串等敏感信息）；响应只暴露异常类型名，不回显细节
        logger.error(f"Database health check failed: {e}")
        return {"status": "unhealthy", "database": "mysql", "error": type(e).__name__}


def _storage_probe_sync(storage) -> None:
    """存储探活同步探测（仅在 asyncio.to_thread 线程池中执行）：

    临时文件创建 + 删除，验证目录存在且可写；失败向上抛由端点统一处理。
    """
    test_file = storage.create_temp("health_test_", ".tmp")
    test_file.unlink()

@router.get("/storage")
async def health_storage():
    """存储系统健康检查（同步文件探测转线程池，不阻塞事件循环）"""
    logger = get_logger("api")
    try:
        storage = get_storage()
        await asyncio.to_thread(_storage_probe_sync, storage)
        logger.info("Storage health check passed")
        return {"status": "healthy", "storage": "filesystem"}
    except Exception as e:
        logger.error(f"Storage health check failed: {e}")
        return {"status": "unhealthy", "storage": "filesystem", "error": type(e).__name__}

@router.get("/redis")
async def health_redis():
    """Redis 健康检查（异步 ping，对齐限流/服务层异步门面约定）"""
    logger = get_logger("api")
    try:
        await get_async_redis().ping()
        logger.info("Redis health check passed")
        return {"status": "healthy", "database": "redis"}
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return {"status": "unhealthy", "database": "redis", "error": type(e).__name__}
