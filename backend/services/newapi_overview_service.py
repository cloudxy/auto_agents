"""值班总览：LiteLLM 模型/部署 + 本地事件/探针（T-18）

远程异常一律降级 available=false（HTTP 200，不 500）。
空态 71.2 / 降级 71.3 冻结句。页上无完整上游 Key。
"""
import asyncio
from datetime import datetime, timedelta
from typing import NamedTuple, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.newapi_repository import (
    ChannelEventRepository,
    ChannelProbeResultRepository,
)
from backend.services.gateway_models import (
    DUTY_DEGRADE_71_3,
    DUTY_EMPTY_71_2,
    items_from_payload,
    map_gateway_model,
)
from backend.services.llm_gateway import admin as gw_admin
from platform_core.logger import get_logger
from platform_core.schemas.newapi import (
    ChannelEventListResponse,
    ChannelEventResponse,
    ChannelProbeResultListResponse,
    ChannelProbeResultResponse,
    GatewayModelResponse,
    GatewayModelWriteRequest,
    GatewayUpstreamWriteRequest,
    NewapiOverviewResponse,
)

logger = get_logger("api")

OVERVIEW_TIMEOUT_SECONDS: float = 5.0
EVENTS_WINDOW_HOURS: int = 24


class _ModelFetchResult(NamedTuple):
    available: bool
    reason: Optional[str]
    models: list[GatewayModelResponse]
    deployments: list[GatewayModelResponse]


class NewapiOverviewService:
    """值班聚合（网关模型 + 本地事件/探针；写面仅超管）"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.event_repo = ChannelEventRepository(session)
        self.probe_repo = ChannelProbeResultRepository(session)

    async def get_overview(self) -> NewapiOverviewResponse:
        """总览：网关模型（降级安全）+ 近 24h 事件 + 最近探针分布"""
        logger.info("聚合 LLM 网关值班总览")
        fetched = await self._fetch_models()
        events_24h = await self.event_repo.count_events_since(
            datetime.now() - timedelta(hours=EVENTS_WINDOW_HOURS)
        )
        batch_id = await self.probe_repo.latest_batch_id()
        verdicts = (
            await self.probe_repo.count_results_by_verdict(batch_id) if batch_id else {}
        )
        total = len(fetched.models)
        empty = DUTY_EMPTY_71_2 if fetched.available and total == 0 else None
        degrade = DUTY_DEGRADE_71_3 if not fetched.available else None
        return NewapiOverviewResponse(
            available=fetched.available,
            reason=fetched.reason,
            empty_state=empty,
            degrade_state=degrade,
            models=fetched.models,
            deployments=fetched.deployments,
            channels=[],
            total=total,
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

    async def register_model(
        self, payload: GatewayModelWriteRequest,
    ) -> GatewayModelResponse:
        """超管登记/改平台网关模型（租户写面由守卫拒绝）"""
        logger.info(f"登记平台网关模型: model_name={payload.model_name}")
        body: dict = {
            "model_name": payload.model_name,
            "litellm_params": dict(payload.litellm_params or {}),
        }
        if payload.gateway_ref:
            body["model_info"] = {"id": payload.gateway_ref}
        raw = await gw_admin.create_model(body)
        mapped = _mapped_or_name(raw, payload.model_name, payload.gateway_ref)
        return mapped

    async def register_upstream(
        self, payload: GatewayUpstreamWriteRequest,
    ) -> GatewayModelResponse:
        """超管登记平台上游（api_base）；不记完整 Key"""
        logger.info(f"登记平台上游: gateway_ref={payload.gateway_ref}")
        params = dict(payload.litellm_params or {})
        params["api_base"] = payload.api_base
        name = payload.model_name or payload.gateway_ref
        raw = await gw_admin.create_model({
            "model_name": name,
            "litellm_params": params,
            "model_info": {"id": payload.gateway_ref},
        })
        return _mapped_or_name(raw, name, payload.gateway_ref)

    async def _fetch_models(self) -> _ModelFetchResult:
        """拉取网关模型；不可达统一降级，不向上抛"""
        try:
            payload = await asyncio.wait_for(
                gw_admin.list_models(), timeout=OVERVIEW_TIMEOUT_SECONDS,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 —— 超时/网络/解析异常统一降级（不 500）
            logger.warning(f"拉取网关模型失败（降级）: error={e}")
            return _ModelFetchResult(False, DUTY_DEGRADE_71_3, [], [])
        models = [
            item for item in (
                map_gateway_model(raw) for raw in items_from_payload(payload)
            ) if item is not None
        ]
        deployments = await self._fetch_deployments()
        return _ModelFetchResult(True, None, models, deployments)

    async def _fetch_deployments(self) -> list[GatewayModelResponse]:
        """部署列表尽力而为；失败不影响 available"""
        try:
            payload = await asyncio.wait_for(
                gw_admin.list_deployments(), timeout=OVERVIEW_TIMEOUT_SECONDS,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning(f"拉取网关部署失败（忽略）: error={e}")
            return []
        return [
            item for item in (
                map_gateway_model(raw) for raw in items_from_payload(payload)
            ) if item is not None
        ]


def _mapped_or_name(
    raw: object, name: str, gateway_ref: Optional[str],
) -> GatewayModelResponse:
    """写回执映射；上游异常结构时仍回模型名（不含 Key）"""
    if isinstance(raw, dict):
        data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
        if isinstance(data, dict):
            mapped = map_gateway_model(data)
            if mapped is not None:
                return mapped
    return GatewayModelResponse(
        gateway_ref=gateway_ref or name, model_name=name,
    )
