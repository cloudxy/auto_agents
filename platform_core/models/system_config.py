"""系统配置模型 - 存储网站基础信息"""
from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from .base import Base

class SystemConfig(Base):
    __tablename__ = "system_configs"

    id = Column(Integer, primary_key=True, index=True)
    config_key = Column(String(50), unique=True, nullable=False, comment="配置键")
    config_value = Column(Text, nullable=False, comment="配置值")
    description = Column(String(255), comment="配置描述")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
