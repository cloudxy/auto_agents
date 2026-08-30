"""new-api 集成 Schema —— 渠道事件 / 探针结果契约（阶段三）

当前阶段后台服务（调度器/探针）内部消费，暂无对外 API 端点；
枚举与响应模型先行定义，后续 API 层（禁 import ORM 红线）直接复用，
model_config(from_attributes) 支持 ORM 实体直接 model_validate。

verdict 判定口径（与 channel_probe_service._score_probe_batch 对齐）：
- original：正品（各维启发式未见伪装信号）
- spoofed：伪装（身份矛盾 / 同题逐字重复 / 参考相似度过低）
- offline：不可用（探针调用过半失败）
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ProbeVerdict(str, Enum):
    """探针判定枚举"""

    ORIGINAL = "original"
    SPOOFED = "spoofed"
    OFFLINE = "offline"


class ChannelEventAction(str, Enum):
    """渠道事件动作枚举"""

    DISABLED = "disabled"
    ENABLED = "enabled"


class ChannelEventSource(str, Enum):
    """渠道事件来源枚举"""

    SCHEDULER = "scheduler"
    MANUAL = "manual"


class ChannelEventResponse(BaseModel):
    """渠道启停事件响应快照"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int = Field(..., description="new-api 渠道 ID")
    action: str = Field(..., description="动作：disabled/enabled")
    usage: Optional[int] = Field(None, description="触发时窗口用量（quota）")
    limit_quota: Optional[int] = Field(None, description="触发的用量上限")
    window_hours: Optional[int] = Field(None, description="统计窗口（小时）")
    reason: Optional[str] = Field(None, description="原因说明")
    source: str = Field(..., description="来源：scheduler/manual")
    created_at: Optional[datetime] = None


class ChannelEventListResponse(BaseModel):
    """渠道事件分页列表"""

    total: int
    items: list[ChannelEventResponse]


class ChannelProbeResultResponse(BaseModel):
    """探针结果响应快照"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int = Field(..., description="new-api 渠道 ID")
    model: str = Field(..., description="被检模型名")
    verdict: ProbeVerdict = Field(..., description="判定：original/spoofed/offline")
    scores: Optional[dict] = Field(None, description="10 维探针得分与启发式指标")
    latency_ms: Optional[int] = Field(None, description="身份探针往返延迟（毫秒）")
    batch_id: str = Field(..., description="巡检批次（uuid hex）")
    created_at: Optional[datetime] = None


class ChannelProbeResultListResponse(BaseModel):
    """探针结果分页列表"""

    total: int
    items: list[ChannelProbeResultResponse]


class NewapiChannelResponse(BaseModel):
    """new-api 渠道快照（管理 API 宽松映射）

    映射规则（newapi_overview_service._map_channel）：
    - 已知字段归一类型（new-api 各版本字段可能缺失，一律 Optional 带默认值）
    - 未知字段收进 extra dict 透传（前端可扩展展示）
    - 敏感字段（key 渠道密钥等）绝不透传，见 service 侧剔除名单
    """

    id: int = Field(..., description="new-api 渠道 ID")
    name: str = ""
    status: int = Field(0, description="1 启用 / 2 人工禁用 / 3 自动禁用")
    type: int = Field(0, description="渠道类型常量（new-api common/constants）")
    used_quota: Optional[float] = Field(None, description="已用额度（quota 单位）")
    balance: Optional[float] = Field(None, description="余额（美元，以上游返回为准）")
    response_time: Optional[int] = Field(None, description="测速延迟（毫秒，-1=未测）")
    test_time: Optional[int] = Field(None, description="上次测速 unix 时间（秒）")
    models: Optional[str] = Field(None, description="模型列表（逗号分隔）")
    group: Optional[str] = Field(None, description="分组")
    base_url: Optional[str] = Field(None, description="渠道上游地址")
    priority: Optional[int] = Field(None, description="权重优先级")
    weight: Optional[int] = Field(None, description="权重")
    created_time: Optional[int] = Field(None, description="创建 unix 时间（秒）")
    extra: dict = Field(default_factory=dict, description="未知字段的宽松透传（敏感字段已剔除）")


class NewapiOverviewResponse(BaseModel):
    """中转站总览（远程渠道 + 本地统计）

    远程不可达/开关关闭时 available=false 并附 reason（HTTP 仍 200，页面降级展示），
    本地统计（events_24h / latest_batch_*）始终返回（本地表，不依赖 new-api 可达）。
    """

    available: bool = Field(True, description="new-api 管理面是否可达")
    reason: Optional[str] = Field(None, description="不可达原因（available=false 时给出）")
    channels: list[NewapiChannelResponse] = Field(default_factory=list, description="渠道列表")
    total: int = Field(0, description="渠道总数")
    events_24h: int = Field(0, description="近 24h 渠道事件数（本地表）")
    latest_batch_id: Optional[str] = Field(None, description="最近一次探针批次（无记录时 null）")
    latest_batch_verdicts: dict[str, int] = Field(
        default_factory=dict,
        description="最近批次 verdict 分布：original/spoofed/offline 计数",
    )
