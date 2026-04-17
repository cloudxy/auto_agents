"""数据访问层（Repository）- 导出所有 Repository 类"""
from backend.repositories.base import BaseRepository
from backend.repositories.user_repository import UserRepository

__all__ = [
    "BaseRepository",
    "UserRepository",
]
