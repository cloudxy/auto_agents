"""ORM 数据模型 —— 声明式 Base + 所有业务表

约定（红线）：
- 只定义结构，不操作 Session
- 禁止 import Pydantic schema
- 所有业务模型继承 platform_core.models.base.Base
"""
from platform_core.models.base import Base
from platform_core.models.spider_task import SpiderTask
from platform_core.models.user import User
from platform_core.models.system_config import SystemConfig

__all__ = ["Base", "SpiderTask", "User", "SystemConfig"]
