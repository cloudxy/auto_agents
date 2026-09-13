"""产品事件 API：公开埋点（失败不挡）+ 超管查询（租户 404 同形）。"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import CurrentUser, require_platform_admin_or_404
from backend.app.core.rate_limiter import EVENTS_PUBLIC_RATE_POLICY, enforce_request_limit
from backend.app.responses import ok
from backend.services.product_event_service import ProductEventService
from platform_core.db import get_async_db
from platform_core.exceptions import RateLimitException
from platform_core.logger import get_logger
from platform_core.redis_async import get_async_redis
from platform_core.schemas.product_event import PublicEventIn

logger = get_logger("api")

public_router = APIRouter()
admin_router = APIRouter()


def _service(session: AsyncSession = Depends(get_async_db)) -> ProductEventService:
    return ProductEventService(session)


@public_router.post("/events")
async def ingest_public_event(
    body: PublicEventIn,
    request: Request,
    service: ProductEventService = Depends(_service),
):
    """官网页浏览 / CTA 埋点。限流 fail-open；持久化失败仍 200（不挡主路径）。"""
    logger.info(f"公开埋点请求 | name={body.event_name}")
    try:
        redis = get_async_redis()
        await enforce_request_limit(redis, EVENTS_PUBLIC_RATE_POLICY, request)
    except RateLimitException:
        raise
    except Exception as exc:  # noqa: BLE001 限流故障不挡埋点
        logger.warning(f"公开埋点限流跳过 | err={exc}")
    await service.ingest_public(
        body.event_name, body.anonymous_id, props=body.props, occurred_at=body.occurred_at,
    )
    return ok(data={"accepted": True})


@admin_router.get("/product-events")
async def query_product_events(
    event_name: Optional[str] = Query(None, max_length=64),
    tenant_id: Optional[int] = Query(None, ge=1),
    occurred_from: Optional[datetime] = Query(None),
    occurred_to: Optional[datetime] = Query(None),
    is_internal_fixture: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    _user: CurrentUser = Depends(require_platform_admin_or_404),
    service: ProductEventService = Depends(_service),
):
    """超管按发生时间查询产品事实。非超管 HTTP 404 同形。"""
    logger.info(f"超管查询产品事实 | user={_user.username} name={event_name}")
    data = await service.query(
        event_name=event_name, tenant_id=tenant_id,
        occurred_from=occurred_from, occurred_to=occurred_to,
        is_internal_fixture=is_internal_fixture,
        skip=skip, limit=limit,
    )
    return ok(data=data.model_dump(mode="json"))
