"""数据库初始化模块 - 统一管理所有 MySQL/Redis 连接（含 Async Session）"""
import os
from typing import Dict
import redis
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine
from sqlalchemy.orm import sessionmaker
from urllib.parse import quote_plus
from config import settings
from platform_core.logger import get_logger


class DBManager:
    """数据库管理器 - 统一管理所有 MySQL/Redis 连接（含 Async Session）"""

    def __init__(self):
        self.mysql: Dict[str, sessionmaker] = {}
        self.async_engines: Dict[str, AsyncEngine] = {}
        self.redis: Dict[str, redis.Redis] = {}
        self._ready: bool = False

    def init_all(self):
        """初始化所有数据库连接"""
        if self._ready:
            return

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
            sync_url = f"mysql+pymysql://{user}:{encoded_pwd}@{host}:{port}/{dbname}?charset={charset}"
            async_url = f"mysql+aiomysql://{user}:{encoded_pwd}@{host}:{port}/{dbname}?charset={charset}"

            try:
                # 1. 同步引擎
                engine = create_engine(sync_url, pool_size=5, max_overflow=10, pool_recycle=3600)
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                self.mysql[key] = sessionmaker(bind=engine)
                
                # 2. 异步引擎
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
                error_log.error(error_msg)
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
                error_log.error(error_msg)
                raise

    def get_mysql(self, key: str = "DEFAULT"):
        if not self._ready:
            self.init_all()
        if key not in self.mysql:
            raise KeyError(f"MySQL '{key}' not found.")
        return self.mysql[key]()

    async def get_async_session(self, key: str = "DEFAULT"):
        if not self._ready:
            self.init_all()
        if key not in self.async_engines:
            raise KeyError(f"Async MySQL '{key}' not found.")
        
        async_engine = self.async_engines[key]
        async with AsyncSession(async_engine) as session:
            yield session

    def get_redis(self, key: str = "DEFAULT", db: int = None):
        if not self._ready:
            self.init_all()
        if key not in self.redis:
            raise KeyError(f"Redis '{key}' not found.")
        
        if db is not None:
            return self._create_redis_client_for_db(key, db)
        return self.redis[key]

    def _create_redis_client_for_db(self, key: str, db: int):
        global_log = get_logger("global")
        redis_cfg = getattr(settings, "REDIS", {})
        cfg = getattr(redis_cfg, key)
        host = getattr(cfg, "HOST", "127.0.0.1")
        port = getattr(cfg, "PORT", 6379)
        password = self._get_password("REDIS", key)
        
        encoded_pwd = quote_plus(password) if password else ""
        auth_part = f":{encoded_pwd}@" if password else ""
        url = f"redis://{auth_part}{host}:{port}/{db}"
        
        try:
            pool = redis.ConnectionPool.from_url(url, max_connections=100, decode_responses=True)
            client = redis.Redis(connection_pool=pool)
            client.ping()
            return client
        except Exception as e:
            global_log.error(f"Redis [{key}] DB[{db}] FAIL: {e}")
            raise
    
    def close_all(self):
        for engine_factory in self.mysql.values():
            engine_factory.kw["bind"].dispose()
        for async_engine in self.async_engines.values():
            import asyncio
            asyncio.run(async_engine.dispose())
        for client in self.redis.values():
            client.close()
        self.mysql.clear()
        self.async_engines.clear()
        self.redis.clear()
        self._ready = False


_manager = None

def get_manager() -> DBManager:
    global _manager
    if _manager is None:
        _manager = DBManager()
    return _manager

def init_db():
    return get_manager().init_all()

def mysql_session(key: str = "DEFAULT"):
    return get_manager().get_mysql(key)

async def get_async_db(key: str = "DEFAULT"):
    async for session in get_manager().get_async_session(key):
        yield session

def redis_client(key: str = "DEFAULT", db: int = None):
    return get_manager().get_redis(key, db)
