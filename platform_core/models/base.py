"""SQLAlchemy 基础模型 - 只保留 Base 类，引擎由 cors/db_init.py 统一管理"""
from sqlalchemy.orm import declarative_base

# 声明式基类（所有 ORM 模型继承此类）
Base = declarative_base()

__all__ = ["Base"]
