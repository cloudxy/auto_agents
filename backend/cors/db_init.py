"""数据库初始化模块 - 统一管理所有 MySQL/Redis 连接（含 Async Session）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from typing import Dict, Any
import redis
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine
from sqlalchemy.orm import sessionmaker, Session
from urllib.parse import quote_plus
from loguru import logger
from config import settings
from backend.cors.log_init import get_logger


class DBManager:
    """数据库管理器 - 统一管理所有 MySQL/Redis 连接（含 Async Session）"""

    def __init__(self):
        self.mysql: Dict[str, sessionmaker] = {}  # {bind_key: SessionFactory}
        self.async_engines: Dict[str, AsyncEngine] = {}  # {bind_key: AsyncEngine} 用于 FastAPI 异步会话
        self.redis: Dict[str, redis.Redis] = {}  # {bind_key: RedisClient}
        self._ready: bool = False

    def init_all(self):
        """初始化所有数据库连接"""
        if self._ready:
            return

        # 使用 global_logger（初始化阶段）
        global_log = get_logger("global")
        global_log.info("初始化所有数据库...")
        self._init_mysql_all()
        self._init_redis_all()
        self._ready = True
        global_log.success(f"数据库初始化完成 (MySQL: {len(self.mysql)}, Redis: {len(self.redis)})")

    def _get_password(self, db_type: str, key: str) -> str:
        """从环境变量获取密码"""
        env_key = f"{db_type}_{key}_PASSWORD"
        pwd = os.getenv(env_key) or settings.get(env_key, "")
        return str(pwd) if pwd else ""

    def _init_mysql_all(self):
        """初始化所有 MySQL 实例（同步 + 异步引擎）"""
        global_log = get_logger("global")
        error_log = get_logger("error")
        
        mysql_cfg = getattr(settings, "MYSQL", {})
        if not hasattr(mysql_cfg, "keys"):
            return

        for key in mysql_cfg.keys():
            if key.startswith("_"):
                continue

            cfg = getattr(mysql_cfg, key)
            host = getattr(cfg, "HOST", "127.0.0.1")
            port = getattr(cfg, "PORT", 3306)
            user = getattr(cfg, "USER", "root")
            dbname = getattr(cfg, "DB_NAME", "")
            charset = getattr(cfg, "CHARSET", "utf8mb4")
            password = self._get_password("MYSQL", key)

            encoded_pwd = quote_plus(password) if password else ""
            # 同步 URL
            sync_url = f"mysql+pymysql://{user}:{encoded_pwd}@{host}:{port}/{dbname}?charset={charset}"
            # 异步 URL (aiomysql)
            async_url = f"mysql+aiomysql://{user}:{encoded_pwd}@{host}:{port}/{dbname}?charset={charset}"

            try:
                # 1. 同步引擎（用于 Alembic 迁移等）
                engine = create_engine(sync_url, pool_size=5, max_overflow=10, pool_recycle=3600)
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                self.mysql[key] = sessionmaker(bind=engine)
                
                # 2. 异步引擎（用于 FastAPI 异步会话）
                async_engine = create_async_engine(
                    async_url,
                    pool_size=5,
                    max_overflow=10,
                    pool_recycle=3600,
                    echo=False,
                )
                self.async_engines[key] = async_engine
                
                global_log.success(f"MySQL [{key}] OK: {host}:{port}/{dbname}")
            except Exception as e:
                error_msg = f"MySQL [{key}] FAIL: {e}"
                global_log.error(error_msg)
                error_log.error(error_msg)  # 同步到 error 日志
                raise

    def _init_redis_all(self):
        """初始化所有 Redis 实例"""
        global_log = get_logger("global")
        error_log = get_logger("error")
        
        redis_cfg = getattr(settings, "REDIS", {})
        if not hasattr(redis_cfg, "keys"):
            return

        for key in redis_cfg.keys():
            if key.startswith("_"):
                continue

            cfg = getattr(redis_cfg, key)
            host = getattr(cfg, "HOST", "127.0.0.1")
            port = getattr(cfg, "PORT", 6379)
            db = getattr(cfg, "DB", 0)
            password = self._get_password("REDIS", key)

            encoded_pwd = quote_plus(password) if password else ""
            auth_part = f":{encoded_pwd}@" if password else ""
            url = f"redis://{auth_part}{host}:{port}/{db}"

            try:
                pool = redis.ConnectionPool.from_url(
                    url,
                    max_connections=100,
                    socket_keepalive=True,
                    socket_connect_timeout=5,
                    decode_responses=True,
                )
                client = redis.Redis(connection_pool=pool)
                client.ping()
                self.redis[key] = client
                global_log.success(f"Redis [{key}] OK: {host}:{port}/{db}")
            except Exception as e:
                error_msg = f"Redis [{key}] FAIL: {e}"
                global_log.error(error_msg)
                error_log.error(error_msg)  # 同步到 error 日志
                raise

    def get_mysql(self, key: str = "DEFAULT"):
        """获取指定标签的 MySQL Session（同步）"""
        if not self._ready:
            self.init_all()
        if key not in self.mysql:
            raise KeyError(f"MySQL '{key}' not found. Available: {list(self.mysql.keys())}")
        return self.mysql[key]()

    async def get_async_session(self, key: str = "DEFAULT"):
        """获取指定标签的 AsyncSession（异步，用于 FastAPI 依赖注入）"""
        if not self._ready:
            self.init_all()
        if key not in self.async_engines:
            raise KeyError(f"Async MySQL '{key}' not found. Available: {list(self.async_engines.keys())}")
        
        async_engine = self.async_engines[key]
        async with AsyncSession(async_engine) as session:
            yield session

    def get_redis(self, key: str = "DEFAULT", db: int = None):
        """获取指定标签的 Redis Client
        
        Args:
            key: Redis 配置标签
            db: 可选，指定数据库编号。如果为None则使用配置中的默认值
        """
        if not self._ready:
            self.init_all()
        if key not in self.redis:
            raise KeyError(f"Redis '{key}' not found. Available: {list(self.redis.keys())}")
        
        # 如果指定了 db 参数，需要创建新的连接到指定数据库
        if db is not None:
            return self._create_redis_client_for_db(key, db)
        
        return self.redis[key]

    def _create_redis_client_for_db(self, key: str, db: int):
        """为指定数据库编号创建新的 Redis Client
        
        Args:
            key: Redis 配置标签
            db: 目标数据库编号
            
        Returns:
            Redis 客户端实例，连接到指定数据库
        """
        global_log = get_logger("global")
        error_log = get_logger("error")
        
        # 获取原始配置（不连接的配置）
        redis_cfg = getattr(settings, "REDIS", {})
        if not hasattr(redis_cfg, "keys"):
            raise ValueError("Redis configuration not found")
            
        config_key = key
        if config_key not in redis_cfg.keys() or config_key.startswith("_"):
            raise KeyError(f"Redis configuration '{key}' not found. Available: {list(redis_cfg.keys())}")
            
        cfg = getattr(redis_cfg, config_key)
        host = getattr(cfg, "HOST", "127.0.0.1")
        port = getattr(cfg, "PORT", 6379)
        password = self._get_password("REDIS", key)
        
        # 构建新 URL 指定数据库编号
        encoded_pwd = quote_plus(password) if password else ""
        auth_part = f":{encoded_pwd}@" if password else ""
        url = f"redis://{auth_part}{host}:{port}/{db}"
        
        try:
            pool = redis.ConnectionPool.from_url(
                url,
                max_connections=100,
                socket_keepalive=True,
                socket_connect_timeout=5,
                decode_responses=True,
            )
            client = redis.Redis(connection_pool=pool)
            client.ping()
            global_log.success(f"Redis [{key}] OK: {host}:{port}/{db} (临时连接)")
            return client
        except Exception as e:
            error_msg = f"Redis [{key}] DB[{db}] FAIL: {e}"
            global_log.error(error_msg)
            error_log.error(error_msg)
            raise
    
    def close_all(self):
        """关闭所有连接"""
        global_log = get_logger("global")
        
        # 关闭同步引擎
        for engine_factory in self.mysql.values():
            engine_factory.kw["bind"].dispose()
        
        # 关闭异步引擎
        for async_engine in self.async_engines.values():
            import asyncio
            asyncio.run(async_engine.dispose())
        
        # 关闭 Redis
        for client in self.redis.values():
            client.close()
        
        self.mysql.clear()
        self.async_engines.clear()
        self.redis.clear()
        self._ready = False
        global_log.info("所有数据库连接已关闭")


# 全局单例
_manager = None


def get_manager() -> DBManager:
    """获取全局管理器单例"""
    global _manager
    if _manager is None:
        _manager = DBManager()
    return _manager


def init_db():
    """初始化所有数据库"""
    return get_manager().init_all()


def mysql_session(key: str = "DEFAULT"):
    """便捷函数：获取 MySQL Session（同步）"""
    return get_manager().get_mysql(key)


async def get_async_db(key: str = "DEFAULT"):
    """便捷函数：获取 AsyncSession（异步，用于 FastAPI 依赖注入）"""
    async for session in get_manager().get_async_session(key):
        yield session


def redis_client(key: str = "DEFAULT", db: int = None):
    """便捷函数：获取 Redis Client
    Args:
        key: Redis 配置标签
        db: 可选，指定数据库编号。如果为None则使用配置中的默认值
    """
    return get_manager().get_redis(key, db)
