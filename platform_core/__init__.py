"""
platform_core —— 项目公共基础设施层

跨子项目（backend、scrapy、其他）的共享能力：
- logger      结构化日志
- db          MySQL（sync+async） + Redis 连接管理
- storage     本地存储（缓存/上传/临时文件）
- exceptions  统一异常 + FastAPI handler
- repository  通用数据访问层 BaseRepository[Model]
- models      ORM 模型（共享数据结构）
- schemas     Pydantic schema（共享数据契约）

红线：
- 只依赖 config，不依赖 backend 或 scrapy
- scrapy 侧禁止 import models / 使用 Session（见 project_rule.md）
"""
from platform_core.logger import init_log, get_logger
from platform_core.db import (
    init_db,
    mysql_session,
    get_async_db,
    redis_client,
    get_manager as get_db_manager,
)
from platform_core.storage import init_storage, get_storage

__all__ = [
    "init_log",
    "get_logger",
    "init_db",
    "mysql_session",
    "get_async_db",
    "redis_client",
    "get_db_manager",
    "init_storage",
    "get_storage",
]
