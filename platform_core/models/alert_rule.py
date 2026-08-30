"""告警规则模型"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.sql import func
from .base import Base


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    spider_name = Column(String(100), nullable=True)  # NULL = 全局规则
    rule_type = Column(String(50), nullable=False)  # consecutive_failures / result_drop / task_timeout / queue_depth
    threshold = Column(Float, nullable=False)  # 阈值（含义取决于 rule_type）
    window_minutes = Column(Integer, default=60)  # 检查窗口（分钟）
    severity = Column(String(20), default="warning")  # info / warning / critical
    channels = Column(Text)  # JSON 列表，覆盖全局渠道；空 = 用全局
    enabled = Column(Boolean, default=True)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
