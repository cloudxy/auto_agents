"""渠道真伪探针结果模型（阶段三：new-api 渠道行为指纹体检）

每次巡检批次（batch_id = uuid hex）内对渠道模型做 10 维体检：
身份提问 / 知识截止 / 数值推理 / 指令遵循 / 延迟测量 / reasoning_tokens 异常 /
价格异常 / 同题逐字重复 / 格式稳定性 / 中英一致性。
verdict: original（正品）| spoofed（伪装）| offline（不可用）。
scores JSON 存各维得分与启发式指标（latency_ratio / ref_similarity 等），供人工复核。

只定义结构不操作 Session（红线）；channel_id 为 new-api 渠道 ID（外部系统主键）。
"""
from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, JSON, String
from sqlalchemy.sql import func

from platform_core.models.base import Base


class ChannelProbeResult(Base):
    """渠道真伪探针结果表（批次化，可按渠道/批次追溯）"""

    __tablename__ = "channel_probe_results"
    __table_args__ = (
        Index("ix_channel_probe_results_channel_created", "channel_id", "created_at"),
        Index("ix_channel_probe_results_batch_id", "batch_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    channel_id = Column(BigInteger, nullable=False, comment="new-api 渠道 ID")
    model = Column(String(100), nullable=False, comment="被检模型名（渠道 models 列表首个）")
    verdict = Column(String(20), nullable=False, comment="判定：original/spoofed/offline")
    scores = Column(JSON, nullable=True, comment="10 维探针得分与启发式指标")
    latency_ms = Column(Integer, nullable=True, comment="身份探针往返延迟（毫秒）")
    batch_id = Column(String(64), nullable=False, comment="巡检批次（uuid hex）")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")

    def __repr__(self) -> str:
        return f"<ChannelProbeResult #{self.id} ch={self.channel_id} {self.verdict} {self.model}>"
