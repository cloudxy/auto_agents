"""操作审计日志模型"""
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from platform_core.models.base import Base


class OperationLog(Base):
    """操作审计表（任务增/删/运行、调度变更等高危操作留痕）"""
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, comment="日志ID")
    actor_id = Column(Integer, nullable=True, index=True, comment="操作人ID（系统行为为空）")
    actor_name = Column(String(50), nullable=False, comment="操作人用户名")
    action = Column(String(50), nullable=False, index=True, comment="操作类型，如 task.run/task.delete/schedule.create")
    target = Column(String(100), nullable=False, comment="操作对象，如 task#12/example")
    detail = Column(Text, nullable=True, comment="操作详情（JSON 串）")
    created_at = Column(DateTime, server_default=func.now(), index=True, comment="操作时间")

    def __repr__(self):
        return f"<OperationLog {self.actor_name}:{self.action}:{self.target}>"
