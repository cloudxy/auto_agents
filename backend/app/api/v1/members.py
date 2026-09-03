"""租户成员管理 API（SaaS S2-1）——仅租户 owner/admin 可管理

守卫：require_tenant_manager（owner/admin）；viewer/operator 403。
跨租户不可见经 users.tenant_id 行级过滤（中间件 + 隔离钩子）天然成立。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, get_current_user
from backend.app.responses import created, ok
from backend.services.member_service import MemberService
from platform_core.db import get_async_db
from platform_core.exceptions import AuthorizationException
from platform_core.logger import get_logger

logger = get_logger("api.members")

router = APIRouter()


async def require_tenant_manager(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """租户级管理守卫：owner/admin（平台超管不在此域——成员是租户内部事务）"""
    if user.tenant_role not in ("owner", "admin"):
        raise AuthorizationException(message="需要租户 owner/admin 权限")
    return user


def _service(session: AsyncSession = Depends(get_async_db)) -> MemberService:
    return MemberService(session)


@router.get("")
async def list_members(
    user: CurrentUser = Depends(require_tenant_manager),
    service: MemberService = Depends(_service),
):
    """成员列表（本租户）"""
    return ok(data=await service.list_members(user.tenant_id))


@router.post("")
async def create_member(
    body: dict,
    user: CurrentUser = Depends(require_tenant_manager),
    service: MemberService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
):
    """创建子账号（tenant_role: owner/admin/operator/viewer）"""
    result = await service.create_member(user.tenant_id, body)
    await session.commit()
    await record_audit(session, user, "member.create", f"user#{result['id']}")
    return created(data=result)


@router.patch("/{member_id}")
async def patch_member(
    member_id: int,
    body: dict,
    user: CurrentUser = Depends(require_tenant_manager),
    service: MemberService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
):
    """角色分配 / 禁用（owner 不可变更/禁用）"""
    result = await service.patch_member(user.tenant_id, member_id, body)
    await session.commit()
    await record_audit(session, user, "member.update", f"user#{member_id}", detail=body)
    return ok(data=result)


@router.post("/{member_id}/reset-password")
async def reset_member_password(
    member_id: int,
    body: dict,
    user: CurrentUser = Depends(require_tenant_manager),
    service: MemberService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
):
    """重置成员密码"""
    result = await service.reset_password(user.tenant_id, member_id, str(body.get("new_password") or ""))
    await session.commit()
    await record_audit(session, user, "member.reset_password", f"user#{member_id}")
    return ok(data=result)


@router.get("/audit")
async def member_audit_logs(
    limit: int = 50,
    user: CurrentUser = Depends(require_tenant_manager),
    session: AsyncSession = Depends(get_async_db),
):
    """成员操作审计·租户视角（B6）：本租户成员的近期高危操作留痕

    平台审计全量仍在 /admin/audit-logs（平台超管）；此处按租户收窄，
    经 actor_id ∈ 本租户 users 过滤（行级隔离之外的显式维度收口）。
    """
    from sqlalchemy import select

    from platform_core.models.operation_log import OperationLog
    from platform_core.models.user import User

    stmt = (
        select(OperationLog)
        .join(User, User.id == OperationLog.actor_id)
        .where(User.tenant_id == user.tenant_id)
        .order_by(OperationLog.id.desc())
        .limit(min(max(1, limit), 200))
    )
    rows = (await session.execute(stmt)).scalars().all()
    logger.info(f"成员审计·租户视角 | tenant={user.tenant_id} count={len(rows)}")
    return ok(data=[
        {
            "id": r.id,
            "actor_name": r.actor_name,
            "action": r.action,
            "target": r.target,
            "detail": r.detail,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ])
