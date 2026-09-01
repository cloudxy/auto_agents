"""租户成员管理服务（SaaS S2-1）

租户 owner/admin 自助管理子账号：创建/列表/角色分配（tenant_role）/禁用/重置密码。
守卫语义：viewer/operator 无管理权（端点层租户级守卫）；跨租户成员不可见
（经 users.tenant_id + 中间件租户上下文行级过滤天然成立）。
"""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.utils.auth import get_password_hash
from platform_core.exceptions import NotFoundException, ValidationException
from platform_core.logger import get_logger
from platform_core.models.user import User

logger = get_logger("service.member")

TENANT_ROLES = ("owner", "admin", "operator", "viewer")


def _to_dict(user: User) -> dict:
    return {
        "id": user.id, "username": user.username, "email": user.email,
        "tenant_role": user.tenant_role, "role": user.role,
        "is_active": user.is_active, "is_platform_admin": bool(user.is_platform_admin),
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


class MemberService:
    """租户成员服务（session 注入；调用方保证 owner/admin 权限）"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_members(self, tenant_id: int) -> list[dict]:
        rows = (await self.session.execute(
            select(User).where(User.tenant_id == tenant_id).order_by(User.id.asc())
        )).scalars().all()
        return [_to_dict(r) for r in rows]

    async def create_member(self, tenant_id: int, payload: dict) -> dict:
        logger.info(f"创建成员 | tenant={tenant_id} username={payload.get('username')}")
        tenant_role = str(payload.get("tenant_role") or "viewer")
        if tenant_role not in TENANT_ROLES:
            raise ValidationException(message=f"租户角色不合法: {tenant_role}", field="tenant_role")
        username = str(payload.get("username") or "").strip()
        email = str(payload.get("email") or "").strip()
        password = str(payload.get("password") or "")
        if not username or not email or len(password) < 6:
            raise ValidationException(message="username/email 必填，密码至少 6 位", field="payload")

        exists = (await self.session.execute(
            select(User).where(User.tenant_id == tenant_id, User.username == username)
        )).scalar_one_or_none()
        if exists is not None:
            raise ValidationException(message=f"成员名已存在: {username}", field="username")

        hashed = await asyncio.to_thread(get_password_hash, password)
        user = User(
            username=username, email=email, password_hash=hashed,
            role="viewer" if tenant_role in ("viewer", "operator") else "admin",
            tenant_id=tenant_id, tenant_role=tenant_role,
            is_active=True, is_platform_admin=False,
        )
        self.session.add(user)
        await self.session.flush()
        return _to_dict(user)

    async def patch_member(self, tenant_id: int, member_id: int, payload: dict) -> dict:
        logger.info(f"更新成员 | tenant={tenant_id} member={member_id} fields={sorted(payload)}")
        user = (await self.session.execute(
            select(User).where(User.tenant_id == tenant_id, User.id == member_id)
        )).scalar_one_or_none()
        if user is None:
            raise NotFoundException(resource=f"成员 {member_id}")
        if "tenant_role" in payload:
            role = str(payload["tenant_role"])
            if role not in TENANT_ROLES:
                raise ValidationException(message=f"租户角色不合法: {role}", field="tenant_role")
            if user.tenant_role == "owner":
                raise ValidationException(
                    message="不可变更 owner 角色（租户唯一所有者）", field="tenant_role")
            user.tenant_role = role
            user.role = "viewer" if role in ("viewer", "operator") else "admin"
        if "is_active" in payload:
            if user.tenant_role == "owner" and not payload["is_active"]:
                raise ValidationException(
                    message="不可禁用 owner（租户唯一所有者）", field="is_active")
            user.is_active = bool(payload["is_active"])
        await self.session.flush()
        return _to_dict(user)

    async def reset_password(self, tenant_id: int, member_id: int, new_password: str) -> dict:
        logger.info(f"重置成员密码 | tenant={tenant_id} member={member_id}")
        if len(new_password) < 6:
            raise ValidationException(message="密码至少 6 位", field="new_password")
        user = (await self.session.execute(
            select(User).where(User.tenant_id == tenant_id, User.id == member_id)
        )).scalar_one_or_none()
        if user is None:
            raise NotFoundException(resource=f"成员 {member_id}")
        user.password_hash = await asyncio.to_thread(get_password_hash, new_password)
        await self.session.flush()
        return {"id": member_id, "reset": True}
