"""后台工作会话深模块（SaaS 接线，评审候选1根因修复）

一处封装「开 session + 从锚派生 tenant_scope/platform_scope」——后台组件
（consumer/调度器/评分 worker/巡检/用量聚合）统一经此拿会话，不再各自
直开 manager.async_engines。有租户锚（如 task.tenant_id）→ tenant_scope
（行级隔离生效）；无锚 → platform_scope（平台域全量，写豁免租户断言）。

删除测试：删掉本模块，每个后台路径又要各自开 session + 手挂 scope——
复杂度集中重现，确认为深模块（见 docs/plan/architecture-review 候选1）。
"""
from contextlib import asynccontextmanager
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

import platform_core.db as _db
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger
from platform_core.tenant_context import platform_scope, tenant_scope

logger = get_logger("service.background_session")

# 平台租户 slug（024 种子行；与 user_service / tenant_admin_service 同字面量口径）
PLATFORM_TENANT_SLUG = "platform"


def _anchor_tenant_id(anchor: Any) -> Optional[int]:
    """从锚对象提取租户（属性或 dict 键；无 → None = 平台域）"""
    if anchor is None:
        return None
    if isinstance(anchor, dict):
        return anchor.get("tenant_id")
    return getattr(anchor, "tenant_id", None)


# 后台会话：session + 作用域一体。anchor 带租户（如队列消息/task 行）→
# tenant_scope；否则 platform_scope。tenant_id 显式传参优先。
@asynccontextmanager
async def background_session(anchor: Any = None, tenant_id: Optional[int] = None):
    logger.debug(f"后台会话开启 | tenant={tenant_id if tenant_id is not None else _anchor_tenant_id(anchor)}")
    from platform_core.db import AsyncSession as _AsyncSession

    manager = _db.get_manager()
    resolved = tenant_id if tenant_id is not None else _anchor_tenant_id(anchor)
    scope = tenant_scope(resolved) if resolved is not None else platform_scope()
    with scope:
        async with _AsyncSession(manager.async_engines["DEFAULT"]) as session:
            yield session


# 默认租户（slug=default，迁移 017 承接存量）；不存在则建（幂等）。
# 后台无请求上下文的计量/写入归属此租户（单团队语义与迁移回填一致）。
async def default_tenant_id(session: AsyncSession) -> int:
    logger.debug("默认租户查建")
    from sqlalchemy import select

    from platform_core.models.tenant import Tenant

    row = (await session.execute(
        select(Tenant.id).where(Tenant.slug == "default")
    )).scalar_one_or_none()
    if row is not None:
        return row
    tenant = Tenant(slug="default", name="默认租户", status="active")
    session.add(tenant)
    await session.flush()
    logger.info("默认租户已按需创建")
    return int(tenant.id)


# 平台租户（slug=platform，024 种子行）——平台超管的 acting tenant（FR-102 / T-38）。
# 与 default_tenant_id 的关键差异（契约 §7/§8 钉死）：种子行缺失 = 配置错误 →
# 入队失败可见（fail loud），不静默回退 None、不临时建租户。
async def platform_tenant_id_or_none(session: AsyncSession) -> Optional[int]:
    """查平台租户 id（行缺失返回 None；非致命判定路径用，如冒名守卫）"""
    logger.debug("平台租户查询")
    from sqlalchemy import select

    from platform_core.models.tenant import Tenant

    return (await session.execute(
        select(Tenant.id).where(Tenant.slug == PLATFORM_TENANT_SLUG)
    )).scalar_one_or_none()


async def platform_tenant_id(session: AsyncSession) -> int:
    """平台租户 id（行缺失 = 配置错误，BusinessException 入队失败可见）"""
    logger.debug("平台租户解析（严格）")
    row = await platform_tenant_id_or_none(session)
    if row is None:
        logger.error("平台租户缺失（slug=platform 种子行不存在，迁移 024 未执行？）")
        raise BusinessException("平台租户未初始化，无法入队")
    return row
