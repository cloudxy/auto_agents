"""产品事实服务：至少一次追加；失败不挡主路径；查询仅超管走 Router 守卫。"""
import inspect
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from backend.repositories.product_event_repository import ProductEventRepository
from platform_core.logger import get_logger
from platform_core.models.product_event import ProductEvent
from platform_core.schemas.product_event import (
    ProductEventListOut,
    ProductEventOut,
    strip_secret_props,
)

logger = get_logger("api")


def utc_now_naive() -> datetime:
    logger.debug("UTC naive now")
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _row_kwargs(
    event_name: str,
    *,
    tenant_id: int | None,
    actor_user_id: int | None,
    anonymous_id: str | None,
    role: str | None,
    props: dict[str, Any] | None,
    occurred_at: datetime | None,
) -> dict[str, Any]:
    logger.debug(f"组装产品事件行 | name={event_name}")
    return {
        "occurred_at": occurred_at or utc_now_naive(),
        "event_name": event_name,
        "tenant_id": tenant_id,
        "actor_user_id": actor_user_id,
        "anonymous_id": anonymous_id,
        "role": role,
        "props": strip_secret_props(props),
    }


async def _persist_event(session: AsyncSession, fields: dict[str, Any]) -> None:
    logger.debug(f"写入产品事件 | name={fields.get('event_name')}")
    # 独立短会话：主路径 rollback（配额拒绝/登录失败）不得带走已发生的事实。
    bind = session.get_bind()
    if inspect.isawaitable(bind):
        bind = await bind
    own = not isinstance(bind, AsyncEngine)
    engine = bind if isinstance(bind, AsyncEngine) else create_async_engine(str(bind.url), poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as extra:
            extra.add(ProductEvent(**fields))
            await extra.commit()
    finally:
        if own:
            await engine.dispose()


async def emit_product_event(session: AsyncSession, event_name: str, *, tenant_id: int | None = None, actor_user_id: int | None = None, anonymous_id: str | None = None, role: str | None = None, props: dict[str, Any] | None = None, occurred_at: datetime | None = None) -> None:
    logger.info(f"上报产品事件 | name={event_name} tenant={tenant_id}")
    try:
        await _persist_event(session, _row_kwargs(
            event_name, tenant_id=tenant_id, actor_user_id=actor_user_id,
            anonymous_id=anonymous_id, role=role, props=props, occurred_at=occurred_at,
        ))
    except Exception as exc:  # noqa: BLE001 至少一次；失败不挡主路径
        logger.warning(f"产品事件上报失败（不挡主路径） | name={event_name} err={exc}")


class ProductEventService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ProductEventRepository(session)

    async def ingest_public(
        self, event_name: str, anonymous_id: str,
        props: dict[str, Any] | None = None, occurred_at: datetime | None = None,
    ) -> None:
        logger.info(f"公开埋点 | name={event_name}")
        await emit_product_event(
            self.session, event_name, anonymous_id=anonymous_id,
            props=props, occurred_at=occurred_at,
        )

    async def query(
        self,
        *,
        event_name: Optional[str] = None,
        tenant_id: Optional[int] = None,
        occurred_from: Optional[datetime] = None,
        occurred_to: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> ProductEventListOut:
        logger.info(f"超管查询产品事实 | name={event_name} tenant={tenant_id}")
        total, rows = await self.repo.list_by_occurred(
            event_name=event_name, tenant_id=tenant_id,
            occurred_from=occurred_from, occurred_to=occurred_to,
            skip=skip, limit=limit,
        )
        return ProductEventListOut(
            total=total,
            items=[ProductEventOut.model_validate(r) for r in rows],
        )
