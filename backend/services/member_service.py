"""租户成员管理服务（SaaS S2-1）

租户 owner/admin 自助管理子账号：创建/列表/角色分配（tenant_role）/禁用/重置密码。
守卫语义：viewer/operator 无管理权（端点层租户级守卫）。

跨租户隔离机制（真实归因）：users 表未继承 TenantMixin（tenant_id 为手写列），
tenant_context 的读侧自动过滤（with_loader_criteria）不覆盖 User——本服务每个
查询显式 where(User.tenant_id == tenant_id)，跨租户 id 一律按"不存在"处理（404）。
"""
import asyncio

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.utils.auth import get_password_hash
from platform_core.exceptions import NotFoundException, ValidationException
from platform_core.logger import get_logger
from platform_core.models.notification import Notification
from platform_core.models.operation_log import OperationLog
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
            select(User).where(User.tenant_id == tenant_id, User.deleted_at.is_(None))
            .order_by(User.id.asc())
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

        # 唯一性检查含软删行：users 的 (tenant_id, username) 与全局 email 唯一约束
        # 不豁免已删行——若只查活行，同名/同邮箱重建会在 flush 时 IntegrityError 500
        #（已删成员的 username/email 语义为"永久占用"，与"不可恢复"口径一致）
        exists = (await self.session.execute(
            select(User).where(User.tenant_id == tenant_id, User.username == username)
        )).scalar_one_or_none()
        if exists is not None:
            raise ValidationException(message=f"成员名已存在: {username}", field="username")
        email_taken = (await self.session.execute(
            select(User).where(User.email == email)
        )).scalar_one_or_none()
        if email_taken is not None:
            raise ValidationException(message=f"邮箱已注册: {email}", field="email")

        hashed = await asyncio.to_thread(get_password_hash, password)
        user = User(
            username=username, email=email, password_hash=hashed,
            role="viewer" if tenant_role in ("viewer", "operator") else "admin",
            tenant_id=tenant_id, tenant_role=tenant_role,
            is_active=True, is_platform_admin=False,
        )
        self.session.add(user)
        await self.session.flush()
        # created_at/updated_at 为 server_default：flush 后未回填，_to_dict 直接读会触发
        # 异步惰性加载抛 MissingGreenlet，须显式 refresh（与 create_template 同一口径）
        await self.session.refresh(user)
        return _to_dict(user)

    async def patch_member(self, tenant_id: int, member_id: int, payload: dict) -> dict:
        logger.info(f"更新成员 | tenant={tenant_id} member={member_id} fields={sorted(payload)}")
        user = (await self.session.execute(
            select(User).where(User.tenant_id == tenant_id, User.id == member_id,
                               User.deleted_at.is_(None))
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
            select(User).where(User.tenant_id == tenant_id, User.id == member_id,
                               User.deleted_at.is_(None))
        )).scalar_one_or_none()
        if user is None:
            raise NotFoundException(resource=f"成员 {member_id}")
        user.password_hash = await asyncio.to_thread(get_password_hash, new_password)
        await self.session.flush()
        return {"id": member_id, "reset": True}

    async def delete_member(self, tenant_id: int, member_id: int, actor_id: int) -> dict:
        """删除成员（owner 与操作者自身不可删；收件箱随账号清理）

        软删口径（与平台 UserService.delete_user 一致）：deleted_at 置位 + is_active=False
        （存量 JWT 复查即时失效）。users 行保留 → list_tenant_audit_logs 经
        actor_id JOIN 的租户归因不丢（B6"删除后审计保留"）；成员列表经
        deleted_at IS NULL 过滤不可见，username/email 永久占用（唯一约束含死行）。
        并发删除（先读后删窗口）：update 带乐观条件 deleted_at IS NULL，
        rowcount==0 说明已被并发删除 → 404（不抛 StaleDataError 500）。
        """
        logger.info(f"删除成员 | tenant={tenant_id} member={member_id} actor={actor_id}")
        user = (await self.session.execute(
            select(User).where(User.tenant_id == tenant_id, User.id == member_id,
                               User.deleted_at.is_(None))
        )).scalar_one_or_none()
        if user is None:
            raise NotFoundException(resource=f"成员 {member_id}")
        if user.tenant_role == "owner":
            raise ValidationException(message="不可删除租户 owner（租户唯一所有者）", field="member_id")
        if user.id == actor_id:
            raise ValidationException(message="不可删除当前登录账号", field="member_id")
        # 收件箱随账号清理（物理删）：被删成员的站内信无消费方，保留即孤儿数据
        await self.session.execute(delete(Notification).where(Notification.user_id == member_id))
        # 软删（乐观并发）：窗口内被并发删除则 rowcount==0 → 404
        result = (await self.session.execute(
            update(User)
            .where(User.id == member_id, User.tenant_id == tenant_id,
                   User.deleted_at.is_(None))
            .values(deleted_at=func.now(), is_active=False)
        ))
        if result.rowcount == 0:
            raise NotFoundException(resource=f"成员 {member_id}")
        return {"id": member_id, "deleted": True}

    async def list_tenant_audit_logs(self, tenant_id: int, limit: int) -> list[dict]:
        """成员操作审计·租户视角（B6）：本租户成员的近期高危操作留痕

        T1 收口（R7）：backend/app/api/v1/members.py 此前函数内延迟 import
        OperationLog/User 直查；查询与投影收口至本方法。
        平台审计全量仍在 /admin/audit-logs（平台超管）；此处经 actor_id ∈
        本租户 users 过滤（行级隔离之外的显式维度收口）。
        JOIN 不过滤 deleted_at：删除成员走软删（行保留），被删成员的历史
        审计归因与 actor_name 展示不丢（B6"删除后审计保留"）。
        """
        logger.info(f"查询租户成员审计 | tenant={tenant_id} limit={limit}")
        stmt = (
            select(OperationLog)
            .join(User, User.id == OperationLog.actor_id)
            .where(User.tenant_id == tenant_id)
            .order_by(OperationLog.id.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            {
                "id": r.id,
                "actor_name": r.actor_name,
                "action": r.action,
                "target": r.target,
                "detail": r.detail,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
