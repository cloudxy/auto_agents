"""值班管控接口（T-18）—— 总览/事件/探针只读 + 网关模型/上游写 + 窗口配置 + 手动探针触发（T-33）

- 路径 `/api/v1/newapi/*` 一周期保留；页 URL `/newapi` 保留
- 列表来自 LiteLLM 模型/部署，不是 new-api 渠道
- GET：require_platform_admin_or_404（GWT-71.4 / 07.3 同形）
- 写/触发：require_platform_admin_or_404（FR-U12 / U15；GWT-70.3 拒绝+行不变，404 同形）
- 信封远端不可达 = 200 + available=false；探针触发即返回 accepted（不阻塞轮询循环）
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import (
    CurrentUser,
    require_platform_admin_or_404,
)
from backend.app.responses import ApiResponse, PaginatedResponse, ok, paginated
from backend.services.channel_config_service import ChannelConfigService
from backend.services.channel_probe_service import ChannelProbeService
from backend.services.newapi_overview_service import NewapiOverviewService
from platform_core.db import get_async_db
from platform_core.logger import get_logger
from platform_core.schemas.newapi import (
    ChannelConfigInfo,
    ChannelConfigUpdateResult,
    ChannelEventResponse,
    ChannelProbeResultResponse,
    GatewayConfigUpdateResult,
    GatewayModelResponse,
    GatewayModelWithConfigResponse,
    GatewayModelWriteRequest,
    GatewayUpstreamWriteRequest,
    NewapiOverviewResponse,
    ProbeTriggerRequest,
    ProbeTriggerResponse,
)

router = APIRouter()
logger = get_logger("api.newapi")


def _service(session: AsyncSession = Depends(get_async_db)) -> NewapiOverviewService:
    return NewapiOverviewService(session)


def _config_service() -> ChannelConfigService:
    return ChannelConfigService()


@router.get("/overview", response_model=ApiResponse[NewapiOverviewResponse])
async def get_overview(
    service: NewapiOverviewService = Depends(_service),
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
) -> ApiResponse[NewapiOverviewResponse]:
    """值班总览：网关模型（异常降级 available=false）+ 本地事件/探针统计"""
    data = await service.get_overview()
    try:
        from backend.services.product_event_service import emit_product_event
        await emit_product_event(
            session, "duty_entry_opened",
            actor_user_id=user.id, role="platform_admin",
            props={"user_id": user.id},
        )
    except Exception as exc:  # noqa: BLE001 失败不挡值班打开
        logger.warning(f"值班打开事件上报失败 | err={exc}")
    return ok(data)


@router.get("/events", response_model=PaginatedResponse[ChannelEventResponse])
async def list_events(
    channel_id: Optional[int] = Query(None, description="按渠道 ID 过滤（BIGINT，类型不改）"),
    page: int = Query(1, ge=1, description="页码（1 起）"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    service: NewapiOverviewService = Depends(_service),
    _user: CurrentUser = Depends(require_platform_admin_or_404),
) -> PaginatedResponse[ChannelEventResponse]:
    """渠道启停事件分页（时间倒序；本地表，始终可用）"""
    resp = await service.list_events(channel_id=channel_id, page=page, page_size=page_size)
    return paginated(
        items=resp.items, total=resp.total, page=page, page_size=page_size
    )


@router.get("/probe-results", response_model=PaginatedResponse[ChannelProbeResultResponse])
async def list_probe_results(
    channel_id: Optional[int] = Query(None, description="按渠道 ID 过滤（BIGINT，类型不改）"),
    page: int = Query(1, ge=1, description="页码（1 起）"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    service: NewapiOverviewService = Depends(_service),
    _user: CurrentUser = Depends(require_platform_admin_or_404),
) -> PaginatedResponse[ChannelProbeResultResponse]:
    """探针结果分页（时间倒序；本地表，始终可用）"""
    resp = await service.list_probe_results(
        channel_id=channel_id, page=page, page_size=page_size
    )
    return paginated(
        items=resp.items, total=resp.total, page=page, page_size=page_size
    )


@router.post("/probe", response_model=ApiResponse[ProbeTriggerResponse])
async def trigger_probe(
    payload: ProbeTriggerRequest,
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_platform_admin_or_404),
) -> ApiResponse[ProbeTriggerResponse]:
    """T-33 / GWT-98.4：立即探测单渠道（触发即返回 accepted+batch_id，不阻塞轮询循环）。

    GWT-98.7：非平台超管 = 404 同形（守卫先于 handler 失败，零渠道/事件副作用）。
    """
    accepted, batch_id, reason = await ChannelProbeService().trigger_manual_probe(
        payload.gateway_ref,
    )
    await record_audit(user, "newapi.probe.trigger", f"gateway:{payload.gateway_ref}",
        {"accepted": accepted, "batch_id": batch_id},
    )
    return ok(ProbeTriggerResponse(
        accepted=accepted, gateway_ref=payload.gateway_ref,
        batch_id=batch_id, reason=reason,
    ))


@router.get("/channels", response_model=ApiResponse[list[GatewayModelWithConfigResponse]])
async def list_channels_with_config(
    service: ChannelConfigService = Depends(_config_service),
    _user: CurrentUser = Depends(require_platform_admin_or_404),
) -> ApiResponse[list[GatewayModelWithConfigResponse]]:
    """网关模型 + 调度配置；远端不可达返回空列表（200，不 502）"""
    return ok(await service.list_channels())


@router.put("/channels/{channel_id}/config", response_model=ApiResponse[ChannelConfigUpdateResult])
async def set_channel_config(
    channel_id: int,
    payload: ChannelConfigInfo,
    session: AsyncSession = Depends(get_async_db),
    service: ChannelConfigService = Depends(_config_service),
    user: CurrentUser = Depends(require_platform_admin_or_404),
) -> ApiResponse[ChannelConfigUpdateResult]:
    """int 路径 expand 写窗口配置（channel_id 类型不改）"""
    info = await service.set_config(channel_id, payload)
    await record_audit(user, "newapi.channel_config.set", f"channel:{channel_id}",
        {"limit_quota": info.limit_quota, "window_hours": info.window_hours,
         "cooldown_seconds": info.cooldown_seconds},
    )
    return ok(ChannelConfigUpdateResult(channel_id=channel_id, config=info))


@router.delete("/channels/{channel_id}/config", response_model=ApiResponse[ChannelConfigUpdateResult])
async def clear_channel_config(
    channel_id: int,
    session: AsyncSession = Depends(get_async_db),
    service: ChannelConfigService = Depends(_config_service),
    user: CurrentUser = Depends(require_platform_admin_or_404),
) -> ApiResponse[ChannelConfigUpdateResult]:
    """清除 int 路径配置"""
    previous = await service.clear_config(channel_id)
    await record_audit(user, "newapi.channel_config.clear", f"channel:{channel_id}",
        {"previous": previous.model_dump() if previous else None},
    )
    return ok(ChannelConfigUpdateResult(
        channel_id=channel_id, cleared=True, config=previous,
    ))


@router.put(
    "/models/{gateway_ref}/config",
    response_model=ApiResponse[GatewayConfigUpdateResult],
)
async def set_model_config(
    gateway_ref: str,
    payload: ChannelConfigInfo,
    session: AsyncSession = Depends(get_async_db),
    service: ChannelConfigService = Depends(_config_service),
    user: CurrentUser = Depends(require_platform_admin_or_404),
) -> ApiResponse[GatewayConfigUpdateResult]:
    """按 string gateway_ref 写窗口配置"""
    info = await service.set_config_ref(gateway_ref, payload)
    await record_audit(user, "newapi.channel_config.set", f"gateway:{gateway_ref}",
        {"limit_quota": info.limit_quota},
    )
    return ok(GatewayConfigUpdateResult(gateway_ref=gateway_ref, config=info))


@router.delete(
    "/models/{gateway_ref}/config",
    response_model=ApiResponse[GatewayConfigUpdateResult],
)
async def clear_model_config(
    gateway_ref: str,
    session: AsyncSession = Depends(get_async_db),
    service: ChannelConfigService = Depends(_config_service),
    user: CurrentUser = Depends(require_platform_admin_or_404),
) -> ApiResponse[GatewayConfigUpdateResult]:
    previous = await service.clear_config_ref(gateway_ref)
    await record_audit(user, "newapi.channel_config.clear", f"gateway:{gateway_ref}",
        {"previous": previous.model_dump() if previous else None},
    )
    return ok(GatewayConfigUpdateResult(
        gateway_ref=gateway_ref, cleared=True, config=previous,
    ))


@router.post("/models", response_model=ApiResponse[GatewayModelResponse])
async def write_gateway_model(
    payload: GatewayModelWriteRequest,
    session: AsyncSession = Depends(get_async_db),
    service: NewapiOverviewService = Depends(_service),
    user: CurrentUser = Depends(require_platform_admin_or_404),
) -> ApiResponse[GatewayModelResponse]:
    """改/登记平台网关模型（GWT-70.3 非超管拒绝）"""
    info = await service.register_model(payload)
    await record_audit(user, "newapi.gateway_model.set", f"gateway:{info.gateway_ref}",
        {"model_name": info.model_name},
    )
    return ok(info)


@router.post("/upstreams", response_model=ApiResponse[GatewayModelResponse])
async def register_platform_upstream(
    payload: GatewayUpstreamWriteRequest,
    session: AsyncSession = Depends(get_async_db),
    service: NewapiOverviewService = Depends(_service),
    user: CurrentUser = Depends(require_platform_admin_or_404),
) -> ApiResponse[GatewayModelResponse]:
    """登记平台上游（GWT-70.3 非超管拒绝）"""
    info = await service.register_upstream(payload)
    await record_audit(user, "newapi.gateway_upstream.set", f"gateway:{info.gateway_ref}",
        {"api_base": info.api_base},
    )
    return ok(info)
