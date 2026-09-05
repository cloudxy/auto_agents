"""渠道调度事件模型（阶段三：new-api 渠道调度器审计轨迹）

记录调度器/人工对 new-api 渠道的启停动作上下文：
- action: disabled（超限下线）| enabled（冷却恢复/人工启用）
- source: scheduler（后台调度器）| manual（人工操作）
- usage/limit_quota/window_hours：触发时的窗口用量上下文（可追溯判定依据）

只定义结构不操作 Session（红线）；channel_id 为 new-api 渠道 ID（外部系统主键，
不设外键关联本库任何表）。
"""
from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String
from sqlalchemy.sql import func

from platform_core.models.base import Base


class ChannelEvent(Base):
    """渠道启停事件表（调度动作审计轨迹）"""

    __tablename__ = "channel_events"
    __table_args__ = (
        Index("ix_channel_events_channel_created", "channel_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    channel_id = Column(BigInteger, nullable=False, comment="new-api 渠道 ID")
    action = Column(String(20), nullable=False, comment="动作：disabled/enabled")
    usage = Column(BigInteger, nullable=True, comment="触发时窗口用量（quota）")
    limit_quota = Column(BigInteger, nullable=True, comment="触发的用量上限")
    window_hours = Column(Integer, nullable=True, comment="统计窗口（小时）")
    reason = Column(String(255), nullable=True, comment="原因说明")
    source = Column(String(20), nullable=False, comment="来源：scheduler/manual")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间",
                        index=True)

    def __repr__(self) -> str:
        return f"<ChannelEvent #{self.id} ch={self.channel_id} {self.action} {self.source}>"
