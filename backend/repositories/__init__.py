"""数据访问层（Repository）- 导出所有 Repository 类"""
from platform_core.repository import BaseRepository
from backend.repositories.user_repository import UserRepository
from backend.repositories.spider_task_repository import SpiderTaskRepository

__all__ = [
    "BaseRepository",
    "UserRepository",
    "SpiderTaskRepository",
]
