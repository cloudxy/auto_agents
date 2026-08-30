"""new-api 中转站总览服务（阶段三：admin 渠道健康页只读聚合）

职责：
- overview：调共享 NewapiApiClient.list_channels 拉取渠道（宽松映射 + 敏感字段剔除），
  附本地统计（近 24h 事件数 / 最近探针批次 verdict 分布）；
  远程异常/超时/开关关闭一律降级 available=false（HTTP 200，页面可读，不 500）
- events / probe-results：分页透出本地 channel_events / channel_probe_results（始终可用）

边界：
- 只读服务，无写代理（渠道启停由调度器/人工在 new-api 侧操作，本服务不写）
- 远程渠道数据不落库；本地表查询走 Repository，事务边界不动
"""
import asyncio
from datetime import datetime, timedelta
from typing import NamedTuple, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.newapi_repository import (
    ChannelEventRepository,
    ChannelProbeResultRepository,
)
from backend.services.newapi_api import NewapiApiClient
from config import settings
from platform_core.logger import get_logger
from platform_core.schemas.newapi import (
    ChannelEventListResponse,
    ChannelEventResponse,
    ChannelProbeResultListResponse,
    ChannelProbeResultResponse,
    NewapiChannelResponse,
    NewapiOverviewResponse,
)

logger = get_logger("api")

# overview 拉取渠道的超时（秒）：同时约束单请求（client timeout）与整体 wait_for
OVERVIEW_TIMEOUT_SECONDS: float = 5.0

# 本地事件统计窗口（小时）
EVENTS_WINDOW_HOURS: int = 24

# 渠道对象敏感字段：宽松映射时强制剔除，绝不透传给前端（红线 R1 精神：密钥不出后端）
_CHANNEL_SENSITIVE_FIELDS: frozenset = frozenset({"key"})

# 渠道已知字段（对齐 new-api 管理面 GET /api/channel/ 返回；宽松容忍缺失）
_CHANNEL_KNOWN_FIELDS: tuple = (
    "id", "name", "status", "type", "used_quota", "balance", "response_time",
    "test_time", "models", "group", "base_url", "priority", "weight", "created_time",
)


class _ChannelFetchResult(NamedTuple):
    """渠道拉取结果（available=false 时 items 恒为空）"""

    available: bool
    reason: Optional[str]
    items: list[NewapiChannelResponse]


def _map_channel(raw: dict) -> Optional[NewapiChannelResponse]:
    """new-api 渠道原始 dict → 响应模型（宽松映射：已知字段归一，未知字段收 extra）"""
    if raw.get("id") is None:
        logger.warning(f"渠道条目缺 id，跳过: keys={sorted(raw.keys())}")
        return None
    known = {k: raw[k] for k in _CHANNEL_KNOWN_FIELDS if k in raw}
    extra = {
        k: v for k, v in raw.items()
        if k not in _CHANNEL_KNOWN_FIELDS and k not in _CHANNEL_SENSITIVE_FIELDS
    }
    return NewapiChannelResponse(**known, extra=extra)


class NewapiOverviewService:
    """中转站总览聚合（渠道列表 + 本地事件/探针统计；只读）"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.event_repo = ChannelEventRepository(session)
        self.probe_repo = ChannelProbeResultRepository(session)

    async def get_overview(self) -> NewapiOverviewResponse:
        """总览聚合：远程渠道（降级安全）+ 近 24h 事件数 + 最近批次 verdict 分布"""
        logger.info("聚合 new-api 中转站总览")
        fetched = await self._fetch_channels()
        events_24h = await self.event_repo.count_events_since(
            datetime.now() - timedelta(hours=EVENTS_WINDOW_HOURS)
        )
        batch_id = await self.probe_repo.latest_batch_id()
        verdicts = (
            await self.probe_repo.count_results_by_verdict(batch_id) if batch_id else {}
        )
        return NewapiOverviewResponse(
            available=fetched.available,
            reason=fetched.reason,
            channels=fetched.items,
            total=len(fetched.items),
            events_24h=events_24h,
            latest_batch_id=batch_id,
            latest_batch_verdicts=verdicts,
        )

    async def list_events(
        self, page: int, page_size: int, channel_id: Optional[int] = None
    ) -> ChannelEventListResponse:
        """渠道启停事件分页（时间倒序，本地表始终可用）"""
        logger.info(f"查询渠道事件: page={page}, page_size={page_size}, channel_id={channel_id}")
        items = await self.event_repo.list_events(
            skip=(page - 1) * page_size, limit=page_size, channel_id=channel_id
        )
        total = await self.event_repo.count_events(channel_id=channel_id)
        return ChannelEventListResponse(
            total=total,
            items=[ChannelEventResponse.model_validate(item) for item in items],
        )

    async def list_probe_results(
        self, page: int, page_size: int, channel_id: Optional[int] = None
    ) -> ChannelProbeResultListResponse:
        """探针结果分页（时间倒序，本地表始终可用）"""
        logger.info(
            f"查询探针结果: page={page}, page_size={page_size}, channel_id={channel_id}"
        )
        items = await self.probe_repo.list_results(
            skip=(page - 1) * page_size, limit=page_size, channel_id=channel_id
        )
        total = await self.probe_repo.count_results(channel_id=channel_id)
        return ChannelProbeResultListResponse(
            total=total,
            items=[ChannelProbeResultResponse.model_validate(item) for item in items],
        )

    async def _fetch_channels(self) -> _ChannelFetchResult:
        """拉取远程渠道列表；开关关闭/不可达/超时统一降级，不向上抛"""
        if not bool(settings.get("NEWAPI.ENABLED", False)):
            return _ChannelFetchResult(False, "newapi disabled", [])
        base_url = str(settings.get("NEWAPI.BASE_URL", "") or "")
        if not base_url:
            return _ChannelFetchResult(False, "newapi base_url not configured", [])
        client = NewapiApiClient(timeout=OVERVIEW_TIMEOUT_SECONDS)
        try:
            raw_list = await asyncio.wait_for(
                client.list_channels(), timeout=OVERVIEW_TIMEOUT_SECONDS
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 —— 超时/网络/解析异常统一降级（不 500）
            logger.warning(f"拉取中转站渠道失败（降级）: base_url={base_url}, error={e}")
            return _ChannelFetchResult(False, f"newapi unreachable: {e}", [])
        items = [
            channel
            for channel in (_map_channel(raw) for raw in raw_list if isinstance(raw, dict))
            if channel is not None
        ]
        return _ChannelFetchResult(True, None, items)
