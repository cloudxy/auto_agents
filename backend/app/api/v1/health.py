"""健康检查接口"""
from fastapi import APIRouter
from platform_core.infra.db_init import mysql_session, redis_client
from platform_core.infra.storage_init import get_storage
from sqlalchemy import text
from platform_core.infra.log_init import get_logger

router = APIRouter()

@router.get("/")
async def health():
    """基础健康检查"""
    logger = get_logger("api")
    logger.debug("Health check accessed")
    return {"status": "ok"}

@router.get("/db")
async def health_db():
    """数据库健康检查"""
    logger = get_logger("api")
    try:
        # 测试默认 MySQL 连接
        session = mysql_session("DEFAULT")
        session.execute(text("SELECT 1"))
        session.close()
        logger.info("Database health check passed")
        return {"status": "healthy", "database": "mysql"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {"status": "unhealthy", "database": "mysql", "error": str(e)}

@router.get("/storage")
async def health_storage():
    """存储系统健康检查"""
    logger = get_logger("api")
    try:
        storage = get_storage()
        # 测试目录是否存在且可写
        test_file = storage.create_temp("health_test_", ".tmp")
        test_file.unlink()
        logger.info("Storage health check passed")
        return {"status": "healthy", "storage": "filesystem"}
    except Exception as e:
        logger.error(f"Storage health check failed: {e}")
        return {"status": "unhealthy", "storage": "filesystem", "error": str(e)}

@router.get("/redis")
async def health_redis():
    """Redis 健康检查"""
    logger = get_logger("api")
    try:
        r = redis_client("DEFAULT")
        r.ping()
        logger.info("Redis health check passed")
        return {"status": "healthy", "database": "redis"}
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return {"status": "unhealthy", "database": "redis", "error": str(e)}
