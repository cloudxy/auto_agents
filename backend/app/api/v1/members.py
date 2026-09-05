"""租户成员管理 API（SaaS S2-1）——仅租户 owner/admin 可管理

守卫：require_tenant_manager（owner/admin）；viewer/operator 403。
跨租户隔离（T5 后双保险）：User 继承 TenantMixin，tenant_scope 下读侧自动
过滤 + 写侧断言；MemberService 仍保留显式 where(User.tenant_id == tenant_id)
（同值幂等）。跨租户 id 一律 404。
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
    await record_audit(session, user, "member.update", f"user#{member_id}", detail=body)
    return ok(data=result)


@router.delete("/{member_id}")
async def delete_member(
    member_id: int,
    user: CurrentUser = Depends(require_tenant_manager),
    service: MemberService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
):
    """删除成员（软删：owner 与当前登录账号不可删；收件箱随账号清理，审计保留）"""
    result = await service.delete_member(user.tenant_id, member_id, actor_id=user.id)
    await record_audit(session, user, "member.delete", f"user#{member_id}")
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
    await record_audit(session, user, "member.reset_password", f"user#{member_id}")
    return ok(data=result)


@router.get("/audit")
async def member_audit_logs(
    limit: int = 50,
    user: CurrentUser = Depends(require_tenant_manager),
    service: MemberService = Depends(_service),
):
    """成员操作审计·租户视角（B6）：本租户成员的近期高危操作留痕

    平台审计全量仍在 /admin/audit-logs（平台超管）；此处按租户收窄，
    经 actor_id ∈ 本租户 users 过滤（行级隔离之外的显式维度收口）。
    """
    limit = min(max(1, limit), 200)
    rows = await service.list_tenant_audit_logs(user.tenant_id, limit)
    logger.info(f"成员审计·租户视角 | tenant={user.tenant_id} count={len(rows)}")
    return ok(data=rows)
