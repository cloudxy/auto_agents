"""new-api 中转站管控接口（阶段三 + 4.2 接线）—— 总览/事件/探针只读 + 渠道额度配置读写

设计：
- overview 聚合远程渠道列表与本地统计；远程异常/超时/开关关闭时 HTTP 200 降级
  available=false（不 500）；events / probe-results 直出本地表，始终可用
- 4.2 渠道调度接线：GET /channels 合并视图 + PUT/DELETE /channels/{id}/config
  写 Redis hash（newapi:channel:cfg:{id}），调度器下一轮巡检即按新额度受管
- 响应契约：统一 ApiResponse 信封（ADR-001）；events / probe-results 为
  PaginatedResponse 分页信封（data.items/total，与前端消费字段命名对齐）
- 全部 require_admin（中转站管控仅管理员可见，与前端 menu:newapi 权限对齐）
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, require_admin
from backend.app.responses import ApiResponse, PaginatedResponse, ok, paginated
from backend.services.channel_config_service import ChannelConfigService
from backend.services.newapi_overview_service import NewapiOverviewService
from platform_core.db import get_async_db
from platform_core.schemas.newapi import (
    ChannelConfigInfo,
    ChannelConfigUpdateResult,
    ChannelEventResponse,
    ChannelProbeResultResponse,
    ChannelWithConfigResponse,
    NewapiOverviewResponse,
)

router = APIRouter()


def _service(session: AsyncSession = Depends(get_async_db)) -> NewapiOverviewService:
    return NewapiOverviewService(session)


def _config_service() -> ChannelConfigService:
    return ChannelConfigService()


@router.get("/overview", response_model=ApiResponse[NewapiOverviewResponse])
async def get_overview(
    service: NewapiOverviewService = Depends(_service),
    _user: CurrentUser = Depends(require_admin),
) -> ApiResponse[NewapiOverviewResponse]:
    """中转站总览：远程渠道列表（异常降级 available=false）+ 本地事件/探针统计"""
    return ok(await service.get_overview())


@router.get("/events", response_model=PaginatedResponse[ChannelEventResponse])
async def list_events(
    channel_id: Optional[int] = Query(None, description="按 new-api 渠道 ID 过滤"),
    page: int = Query(1, ge=1, description="页码（1 起）"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    service: NewapiOverviewService = Depends(_service),
    _user: CurrentUser = Depends(require_admin),
) -> PaginatedResponse[ChannelEventResponse]:
    """渠道启停事件分页（时间倒序；本地表，始终可用）"""
    resp = await service.list_events(channel_id=channel_id, page=page, page_size=page_size)
    return paginated(
        items=resp.items, total=resp.total, page=page, page_size=page_size
    )


@router.get("/probe-results", response_model=PaginatedResponse[ChannelProbeResultResponse])
async def list_probe_results(
    channel_id: Optional[int] = Query(None, description="按 new-api 渠道 ID 过滤"),
    page: int = Query(1, ge=1, description="页码（1 起）"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    service: NewapiOverviewService = Depends(_service),
    _user: CurrentUser = Depends(require_admin),
) -> PaginatedResponse[ChannelProbeResultResponse]:
    """渠道真伪探针结果分页（时间倒序；本地表，始终可用）"""
    resp = await service.list_probe_results(
        channel_id=channel_id, page=page, page_size=page_size
    )
    return paginated(
        items=resp.items, total=resp.total, page=page, page_size=page_size
    )


# ---------------- 4.2 渠道调度配置（写路径：管理面 → Redis → 调度器生效） ----------------


@router.get("/channels", response_model=ApiResponse[list[ChannelWithConfigResponse]])
async def list_channels_with_config(
    service: ChannelConfigService = Depends(_config_service),
    _user: CurrentUser = Depends(require_admin),
) -> ApiResponse[list[ChannelWithConfigResponse]]:
    """渠道列表 + 调度配置合并视图（渠道级 > 全局默认；远程不可达返回业务码 502）"""
    return ok(await service.list_channels())


@router.put("/channels/{channel_id}/config", response_model=ApiResponse[ChannelConfigUpdateResult])
async def set_channel_config(
    channel_id: int,
    payload: ChannelConfigInfo,
    session: AsyncSession = Depends(get_async_db),
    service: ChannelConfigService = Depends(_config_service),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[ChannelConfigUpdateResult]:
    """写入渠道级额度配置（limit_quota=0 表示显式关闭该渠道调度）"""
    info = await service.set_config(channel_id, payload)
    await record_audit(
        session, user, "newapi.channel_config.set", f"channel:{channel_id}",
        {"limit_quota": info.limit_quota, "window_hours": info.window_hours,
         "cooldown_seconds": info.cooldown_seconds},
    )
    return ok(ChannelConfigUpdateResult(channel_id=channel_id, config=info))


@router.delete("/channels/{channel_id}/config", response_model=ApiResponse[ChannelConfigUpdateResult])
async def clear_channel_config(
    channel_id: int,
    session: AsyncSession = Depends(get_async_db),
    service: ChannelConfigService = Depends(_config_service),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse[ChannelConfigUpdateResult]:
    """清除渠道级配置（该渠道回退全局默认额度；无全局默认则退出纳管）"""
    previous = await service.clear_config(channel_id)
    await record_audit(
        session, user, "newapi.channel_config.clear", f"channel:{channel_id}",
        {"previous": previous.model_dump() if previous else None},
    )
    return ok(ChannelConfigUpdateResult(
        channel_id=channel_id, cleared=True, config=previous,
    ))
