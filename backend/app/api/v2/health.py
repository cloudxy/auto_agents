"""V2 健康检查 - 增强的监控功能"""
from fastapi import APIRouter
from platform_core.db import mysql_session, redis_client
from platform_core.storage import get_storage
from sqlalchemy import text
from platform_core.logger import get_logger
import time

router = APIRouter()

@router.get("/")
async def health():
    """V2 基础健康检查 - 包含响应时间"""
    logger = get_logger("api")
    start_time = time.time()
    response_time = round((time.time() - start_time) * 1000, 2)
    
    logger.debug(f"Health check: {response_time}ms")
    
    return {
        "status": "healthy",
        "version": "2.0.0",
        "response_time_ms": response_time
    }

@router.get("/db")
async def health_db():
    """V2 数据库健康检查 - 增强版"""
    logger = get_logger("api")
    try:
        start_time = time.time()
        
        # 测试 MySQL
        session = mysql_session("DEFAULT")
        session.execute(text("SELECT 1"))
        session.close()
        
        # 测试 Redis
        r = redis_client("DEFAULT")
        r.ping()
        
        response_time = round((time.time() - start_time) * 1000, 2)
        
        logger.info(f"Database health check passed: {response_time}ms")
        
        return {
            "status": "healthy",
            "version": "2.0.0",
            "database": {
                "mysql": "connected",
                "redis": "connected"
            },
            "response_time_ms": response_time
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
