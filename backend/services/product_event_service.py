"""产品事实服务：至少一次追加；失败不挡主路径；查询仅超管走 Router 守卫。"""
import inspect
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

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


async def _fixture_snapshot(session: AsyncSession, tenant_id: int | None) -> bool:
    logger.debug(f"夹具快照点查 | tenant={tenant_id}")
    if tenant_id is None:
        return False
    from backend.repositories.internal_fixture_tenant_repository import (
        InternalFixtureTenantRepository,
    )
    return await InternalFixtureTenantRepository(session).exists(tenant_id=tenant_id)


async def _persist_event(session: AsyncSession, fields: dict[str, Any]) -> None:
    logger.debug(f"写入产品事件 | name={fields.get('event_name')}")
    # 独立短会话：主路径 rollback 不得带走已发生的事实。
    # 必须复用 session.bind（AsyncEngine）。str(url) 重建会丢掉密码（***）并
    # 改走 pymysql@localhost → 1045，主路径却仍成功。
    bind = session.bind
    if inspect.isawaitable(bind):
        bind = await bind
    if not isinstance(bind, AsyncEngine):
        raise RuntimeError("product event persist needs AsyncEngine bind")
    row = dict(fields)
    try:
        async with AsyncSession(bind, expire_on_commit=False) as extra:
            if bind.dialect.name == "sqlite":
                # 单写库不做长等：主路径持写锁时 250ms 内认输走下面的兜底，
                # 而不是干等 connect_args 的 30s（CI 全量曾因此每次同步 +33s）。
                await extra.execute(text("PRAGMA busy_timeout=250"))
            row["is_internal_fixture"] = await _fixture_snapshot(extra, row.get("tenant_id"))
            extra.add(ProductEvent(**row))
            await extra.commit()
        return
    except OperationalError as exc:
        # 单写库（SQLite：本仓库 CI 主 pytest job 的默认口径）下，主路径若已 flush
        # 过写操作就持着库级写锁，独立会话必然 `database is locked` 超时 →
        # 事实被上层 try/except 吞掉、**永久丢失**（feat-agents-market T-14 实测：
        # sync_completed/import_completed 在事务内发射时 100% 丢）。
        # 兜底：退回主会话追加。代价是事实与主路径同生共死（弱于独立会话的保证），
        # 但「弱保证」严格优于「丢事件」，且 MySQL 生产路径不会走到这里。
        logger.warning(
            f"产品事件独立会话被写锁挡住，退回主会话追加 | "
            f"name={row.get('event_name')} err={exc}"
        )
    row["is_internal_fixture"] = await _fixture_snapshot(session, row.get("tenant_id"))
    session.add(ProductEvent(**row))
    await session.flush()


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
        is_internal_fixture: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> ProductEventListOut:
        logger.info(f"超管查询产品事实 | name={event_name} tenant={tenant_id}")
        total, rows = await self.repo.list_by_occurred(
            event_name=event_name, tenant_id=tenant_id,
            occurred_from=occurred_from, occurred_to=occurred_to,
            is_internal_fixture=is_internal_fixture,
            skip=skip, limit=limit,
        )
        return ProductEventListOut(
            total=total,
            items=[ProductEventOut.model_validate(r) for r in rows],
        )
