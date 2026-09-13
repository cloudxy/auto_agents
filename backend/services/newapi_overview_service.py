"""值班总览：LiteLLM 模型/部署 + 本地事件/探针（T-18 / T-26 FR-U25）

远程异常一律降级 available=false（HTTP 200，不 500）。
空态 / 降级 / 活 三句互斥；页上无完整上游 Key；禁止「暂无渠道」。
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
    apply_duty_row,
    clear_duty_row,
    items_from_payload,
    map_gateway_model,
    page_duty_copy,
)
from backend.services.llm_gateway import admin as gw_admin
from backend.services.newapi_api import _channel_id_from_ref
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
        events_24h, batch_id, verdicts = await self._local_stats()
        models = await self._duty_models(fetched)
        empty, degrade, page = page_duty_copy(fetched.available, models)
        return NewapiOverviewResponse(
            available=fetched.available,
            reason=fetched.reason,
            empty_state=empty,
            degrade_state=degrade,
            duty_page_state=page,
            models=models,
            deployments=fetched.deployments,
            channels=[],
            total=len(models),
            events_24h=events_24h,
            latest_batch_id=batch_id,
            latest_batch_verdicts=verdicts,
        )

    async def _duty_models(
        self, fetched: _ModelFetchResult,
    ) -> list[GatewayModelResponse]:
        """可达时按当前 gateway_ref 集合+24h 窗标活；降级禁止标活。"""
        logger.debug(
            f"合成值班行态: available={fetched.available}, models={len(fetched.models)}"
        )
        models = fetched.models
        if not fetched.available:
            return [clear_duty_row(m) for m in models]
        if not models:
            return models
        latest = await self.probe_repo.latest_result_per_channel(
            channel_ids=[_channel_id_from_ref(m.gateway_ref) for m in models],
            since=datetime.now() - timedelta(hours=EVENTS_WINDOW_HOURS),
        )
        return _annotate_duty_models(models, latest)

    async def _local_stats(self) -> tuple[int, Optional[str], dict]:
        """本地事件/探针统计（降级时仍返回）。"""
        logger.debug("读取值班本地事件与探针统计")
        events_24h = await self.event_repo.count_events_since(
            datetime.now() - timedelta(hours=EVENTS_WINDOW_HOURS)
        )
        batch_id = await self.probe_repo.latest_batch_id()
        verdicts = (
            await self.probe_repo.count_results_by_verdict(batch_id) if batch_id else {}
        )
        return events_24h, batch_id, verdicts

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


def _index_probe_rows(latest: dict[int, object]) -> tuple[dict[str, object], dict[str, object]]:
    """按 gateway_ref / 模型名建索引，供行匹配。"""
    by_ref: dict[str, object] = {}
    by_name: dict[str, object] = {}
    for row in latest.values():
        scores = getattr(row, "scores", None)
        payload = scores if isinstance(scores, dict) else {}
        ref = str(payload.get("_gateway_ref") or "")
        if ref and ref not in by_ref:
            by_ref[ref] = row
        name = str(getattr(row, "model", "") or "")
        if name and name not in by_name:
            by_name[name] = row
    return by_ref, by_name


def _annotate_duty_models(
    models: list[GatewayModelResponse], latest: dict[int, object],
) -> list[GatewayModelResponse]:
    """可达且已登记时：original 行标「活」；降级路径不调用。"""
    by_ref, by_name = _index_probe_rows(latest)
    out: list[GatewayModelResponse] = []
    for model in models:
        cid = _channel_id_from_ref(model.gateway_ref)
        row = latest.get(cid) or by_ref.get(model.gateway_ref) or by_name.get(
            model.model_name,
        )
        verdict = getattr(row, "verdict", None) if row is not None else None
        out.append(apply_duty_row(model, str(verdict) if verdict else None))
    return out


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
