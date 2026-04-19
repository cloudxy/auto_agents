"""爬虫任务模型"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Enum
from sqlalchemy.sql import func
from .base import Base

class SpiderTask(Base):
    __tablename__ = "spider_tasks"

    id = Column(Integer, primary_key=True, index=True)
    spider_name = Column(String(100), nullable=False, index=True)
    status = Column(
        Enum("pending", "running", "completed", "failed"),
        default="pending"
    )
    params = Column(Text)  # JSON 字符串
    result_count = Column(Integer, default=0)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True))
