"""外部 API - 公开查询接口

职责：
- 提供 API Key 认证的采集结果数据查询
- 支持第三方系统按爬虫名称分页拉取结果
- 任务状态 / 任务结果 / 聚合统计的真实数据查询（API Key 认证）
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.external_api.v1.webhooks import bound_tenant_id, validate_api_key
from backend.services.api_key_service import ApiKeyService
from backend.services.outbound_key_service import OutboundKeyService
from backend.services.spider_query_service import SpiderQueryService
from platform_core.db import get_async_db
from platform_core.logger import get_logger
from platform_core.schemas.spider import SpiderTaskResponse

router = APIRouter()
logger = get_logger("api")


# ---------------------------------------------------------------------------
# 公开数据查询端点（API Key 认证）
# ---------------------------------------------------------------------------

async def _resolve_tenant_key(request: Request, session: AsyncSession) -> Optional[int]:
    """租户 Key 优先；旧平台静态 Key 仅作运维过渡（无租户过滤，记警告）。"""
    api_key = request.headers.get("X-API-Key", "")
    tenant_id = await ApiKeyService(session).authenticate(api_key)
    if tenant_id is not None:
        return tenant_id
    if validate_api_key(api_key):
        logger.warning("外部 API 使用已退役的平台静态 Key，过渡期允许且无租户过滤")
        return None
    raise HTTPException(status_code=401, detail="Invalid API Key")


async def _require_bound_tenant(request: Request, session: AsyncSession) -> int:
    """出站拉数查找链：出站钥匙表 → 租户 API Key → KEY_BINDINGS → 401。

    第一环：本企业 active 出站拉数钥匙（SHA-256 指纹 + compare_digest，
    Service 内执法；revoked / 渠道组 sk- / 乱填一律不命中，GWT-51.3/6/7）；
    第二环：L1 租户 API Key（api_keys 表）；
    第三环：既有 KEY_BINDINGS 配置绑定（FR-13 平台钥匙行为保持，不放宽）；
    三环都未命中 → 401 且不查结果库（0 行）。明文不落日志。
    """
    api_key = request.headers.get("X-API-Key", "")
    tenant_id = await OutboundKeyService(session).resolve_active_tenant(api_key)
    if tenant_id is not None:
        logger.info("出站拉数鉴权命中 | 链=出站钥匙表")
        return int(tenant_id)
    tenant_id = await ApiKeyService(session).authenticate(api_key)
    if tenant_id is not None:
        logger.info("出站拉数鉴权命中 | 链=租户 API Key")
        return int(tenant_id)
    tenant_id = bound_tenant_id(api_key)
    if tenant_id is not None:
        logger.info("出站拉数鉴权命中 | 链=KEY_BINDINGS")
        return int(tenant_id)
    logger.warning("出站拉数鉴权拒绝 | 链=三环未命中（未绑定/已吊销/他形态）")
    raise HTTPException(status_code=401, detail="Invalid API Key")


def _clamp_page(page: int, page_size: int, default_size: int = 20) -> tuple[int, int]:
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = default_size
    if page_size > 100:
        page_size = 100
    return page, page_size


@router.get("/data/{spider_name}")
async def get_spider_data(
    spider_name: str,
    request: Request,
    page: int = 1,
    page_size: int = 20,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    fields: Optional[str] = None,
    session: AsyncSession = Depends(get_async_db),
):
    """公开数据查询 — 按爬虫名分页拉本企业非候选结果

    认证：X-API-Key 先查出站钥匙表（本企业 active 出站
    拉数钥匙，FR-51），再查租户 API Key，未命中再查 KEY_BINDINGS。
    三环都未命中 / 旧字符串列表钥匙 → 401，响应不含结果行。
    可选参数：page / page_size / start_time / end_time / fields。
    """
    tenant_id = await _require_bound_tenant(request, session)
    page, page_size = _clamp_page(page, page_size)

    items, total = await SpiderQueryService(session).query_public_results(
        spider_name=spider_name,
        page=page,
        page_size=page_size,
        start_time=start_time,
        end_time=end_time,
        tenant_id=tenant_id,
    )

    # 4. 字段过滤
    if fields:
        field_list = {f.strip() for f in fields.split(",") if f.strip()}
        if field_list:
            items = [{k: v for k, v in item.items() if k in field_list} for item in items]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


# ---------------------------------------------------------------------------
# 任务状态 / 结果 / 统计（真实数据，API Key 认证）
# ---------------------------------------------------------------------------

@router.get("/spider/status/{task_id}", response_model=SpiderTaskResponse)
async def get_spider_status(
    task_id: int,
    request: Request,
    session: AsyncSession = Depends(get_async_db),
):
    """查询爬虫任务状态（公开接口，API Key 认证；任务不存在返回 404）"""
    tenant_id = await _resolve_tenant_key(request, session)
    task = await SpiderQueryService(session).get_task(task_id, tenant_id=tenant_id)
    return SpiderTaskResponse.model_validate(task)


@router.get("/spider/results/{task_id}")
async def get_spider_results(
    task_id: int,
    request: Request,
    page: int = 1,
    page_size: int = 50,
    session: AsyncSession = Depends(get_async_db),
):
    """获取任务采集结果（公开接口，API Key 认证；分页；任务不存在返回 404）"""
    tenant_id = await _resolve_tenant_key(request, session)
    await SpiderQueryService(session).get_task(task_id, tenant_id=tenant_id)
    page, page_size = _clamp_page(page, page_size, default_size=50)

    resp = await SpiderQueryService(session).list_results(
        task_id=task_id, skip=(page - 1) * page_size, limit=page_size
    )
    return {
        "task_id": task_id,
        "page": page,
        "page_size": page_size,
        "total": resp.total,
        "data": [item.model_dump(mode="json") for item in resp.items],
    }


@router.get("/stats")
async def get_public_stats(
    request: Request,
    session: AsyncSession = Depends(get_async_db),
):
    """系统公开统计（真实聚合数据：任务状态分布/成功率/近 7 日趋势；API Key 认证）"""
    tenant_id = await _resolve_tenant_key(request, session)
    if tenant_id is None:
        return (await SpiderQueryService(session).stats()).model_dump(mode="json")
    items, total = await SpiderQueryService(session).query_public_results(
        tenant_id=tenant_id, page=1, page_size=1
    )
    return {"tenant_id": tenant_id, "result_total": total}
