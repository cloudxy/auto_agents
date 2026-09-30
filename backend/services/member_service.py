"""租户成员管理服务（SaaS S2-1）

租户 owner/admin 自助管理子账号：创建/列表/角色分配（tenant_role）/禁用/重置密码；
负责人本人可把负责人转让给本企业成员（决策 D23）。
守卫语义：viewer/operator 无管理权（端点层租户级守卫）。

跨租户隔离机制（T5 后双保险）：User 已继承 TenantMixin——tenant_scope 下
读侧自动过滤（with_loader_criteria）+ 写侧 before_flush 断言；本服务各查询
保留显式 where(User.tenant_id == tenant_id)（同值幂等），跨租户 id 一律按
"不存在"处理（404）。
"""
import asyncio

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.utils.auth import get_password_hash, verify_password
from platform_core.exceptions import BusinessException, ValidationException
from platform_core.logger import get_logger
from platform_core.models.notification import Notification
from platform_core.models.operation_log import OperationLog
from platform_core.models.user import User
from platform_core.roles import derive_legacy_role
from platform_core.timeutil import utc_iso

logger = get_logger("service.member")

TENANT_ROLES = ("owner", "admin", "operator", "viewer")
_PLATFORM_ROLES = frozenset({
    "platform_admin", "superadmin", "platform", "超管", "平台超管",
})
_USERNAME_MAX = 50
MSG_NEED_USERNAME = "请填写登录名"
MSG_USERNAME_LONG = "登录名最多 50 个字符"
MSG_NO_PLATFORM_ADMIN = "不能设为平台超管"
MSG_NO_OWNER = "不能指定为负责人（每个企业只有一位负责人）"
MSG_HIERARCHY = "当前账号不能管理该成员：管理员只能管理操作员和查看者"

# 可管理的目标角色（审计 R1-1 / B1-1 / BUG-01；决策 D23 = 边界 A）：admin 只能管 operator/viewer；
# owner 只能由 owner 自己管理，换负责人走 transfer_ownership。
_MANAGEABLE_BY: dict[str, frozenset[str]] = {
    "owner": frozenset({"admin", "operator", "viewer"}),
    "admin": frozenset({"operator", "viewer"}),
}


def _member_missing() -> None:
    raise BusinessException(message="Not Found", code="HTTP_404", status_code=404)


def _reject_platform_role(tenant_role: str, payload: dict) -> None:
    logger.debug("校验不得设平台超管")
    if payload.get("is_platform_admin") is True:
        raise ValidationException(message=MSG_NO_PLATFORM_ADMIN, field="is_platform_admin")
    if str(tenant_role or "").strip().lower() in _PLATFORM_ROLES:
        raise ValidationException(message=MSG_NO_PLATFORM_ADMIN, field="tenant_role")


def _hierarchy_denied() -> None:
    raise BusinessException(message=MSG_HIERARCHY, code="MEMBER_HIERARCHY", status_code=403)


def _target_rank(user: User) -> str:
    """目标成员的租户级别；历史行 tenant_role 为空时按 admin 标记推导（宁严勿宽）"""
    if user.tenant_role:
        return str(user.tenant_role)
    return "admin" if (user.is_admin or user.role == "admin") else "viewer"


def _assert_can_manage(actor_role: str | None, target: User) -> None:
    """操作者能否管理目标成员

    - 平台超管对租户侧不可见：404 同形（不泄露存在性，堵住平台租户内 admin 接管超管）
    - owner 只能由 owner 管理
    - 其余按 _MANAGEABLE_BY 分级
    """
    if target.is_platform_admin:
        logger.warning(f"租户侧触达平台超管被拒 | target={target.id}")
        _member_missing()
    rank = _target_rank(target)
    if rank == "owner":
        if actor_role != "owner":
            logger.warning(f"非负责人管理负责人被拒 | actor_role={actor_role} target={target.id}")
            _hierarchy_denied()
        return
    if rank not in _MANAGEABLE_BY.get(str(actor_role or ""), frozenset()):
        logger.warning(f"越级管理成员被拒 | actor_role={actor_role} target={target.id} rank={rank}")
        _hierarchy_denied()


def _assert_can_assign(actor_role: str | None, tenant_role: str) -> None:
    """操作者能否把成员设为 tenant_role（owner 不可经成员接口产生）"""
    if tenant_role == "owner":
        raise ValidationException(message=MSG_NO_OWNER, field="tenant_role")
    if tenant_role not in _MANAGEABLE_BY.get(str(actor_role or ""), frozenset()):
        _hierarchy_denied()


def _to_dict(user: User) -> dict:
    return {
        "id": user.id, "username": user.username, "email": user.email,
        "tenant_role": user.tenant_role, "role": user.role,
        "is_active": user.is_active, "is_platform_admin": bool(user.is_platform_admin),
        "created_at": utc_iso(user.created_at),
    }


class MemberService:
    """租户成员服务（session 注入；调用方保证 owner/admin 权限）"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_members(self, tenant_id: int) -> list[dict]:
        """成员列表；平台超管行对租户侧不可见（即便挂在同一租户）"""
        logger.info(f"列出成员 | tenant={tenant_id}")
        rows = (await self.session.execute(
            select(User).where(User.tenant_id == tenant_id, User.deleted_at.is_(None),
                               User.is_platform_admin.is_not(True))
            .order_by(User.id.asc())
        )).scalars().all()
        return [_to_dict(r) for r in rows]

    async def create_member(self, tenant_id: int, payload: dict,
                            actor_role: str | None = None) -> dict:
        logger.info(f"创建成员 | tenant={tenant_id} username={payload.get('username')} actor_role={actor_role}")
        tenant_role = str(payload.get("tenant_role") or "viewer")
        _reject_platform_role(tenant_role, payload)
        if tenant_role not in TENANT_ROLES:
            raise ValidationException(message=f"租户角色不合法: {tenant_role}", field="tenant_role")
        _assert_can_assign(actor_role, tenant_role)
        username = str(payload.get("username") or "").strip()
        email = str(payload.get("email") or "").strip()
        password = str(payload.get("password") or "")
        if not username:
            raise ValidationException(message=MSG_NEED_USERNAME, field="username")
        if len(username) > _USERNAME_MAX:
            raise ValidationException(message=MSG_USERNAME_LONG, field="username")
        if not email or len(password) < 6:
            raise ValidationException(message="username/email 必填，密码至少 6 位", field="payload")

        # 唯一性检查含软删行（租户自助口径，与用户管理超管路径的「在册释放」
        # 口径不同，test_deleted_member_not_operable_or_reusable 钉住）：.limit(1)
        # 是 042 在册化后的多行护栏——同 username/email 可同时存在在册行与
        # 已删行（用户管理侧释放/恢复所致），scalar_one_or_none 会抛
        # MultipleResultsFound 500；limit(1) 只判「有无任一行」，语义不变
        exists = (await self.session.execute(
            select(User.id).where(User.tenant_id == tenant_id, User.username == username)
            .limit(1)
        )).scalar_one_or_none()
        if exists is not None:
            raise ValidationException(message=f"成员名已存在: {username}", field="username")
        email_taken = (await self.session.execute(
            select(User.id).where(User.email == email).limit(1)
        )).scalar_one_or_none()
        if email_taken is not None:
            raise ValidationException(message=f"邮箱已注册: {email}", field="email")

        hashed = await asyncio.to_thread(get_password_hash, password)
        user = User(
            username=username, email=email, password_hash=hashed,
            role=derive_legacy_role(tenant_role),
            tenant_id=tenant_id, tenant_role=tenant_role,
            is_active=True, is_platform_admin=False,
        )
        self.session.add(user)
        await self.session.flush()
        # created_at/updated_at 为 server_default：flush 后未回填，_to_dict 直接读会触发
        # 异步惰性加载抛 MissingGreenlet，须显式 refresh（与 create_template 同一口径）
        await self.session.refresh(user)
        # ADR-0007 D2：先固化快照再 commit（expire_on_commit 后属性惰性加载会抛 MissingGreenlet）
        snapshot = _to_dict(user)
        await self.session.commit()
        return snapshot

    async def patch_member(self, tenant_id: int, member_id: int, payload: dict,
                           actor_role: str | None = None, actor_id: int | None = None) -> dict:
        logger.info(f"更新成员 | tenant={tenant_id} member={member_id} fields={sorted(payload)} actor_role={actor_role}")
        user = (await self.session.execute(
            select(User).where(User.tenant_id == tenant_id, User.id == member_id,
                               User.deleted_at.is_(None))
        )).scalar_one_or_none()
        if user is None:
            _member_missing()
        if actor_id is not None and int(user.id) == int(actor_id):
            # 审计 BUG-06：不能停用或改动自己的角色（防自锁 / 自降级误操作）
            if "tenant_role" in payload and str(payload["tenant_role"]) != str(user.tenant_role):
                raise ValidationException(message="不能修改自己的角色", field="tenant_role")
            if "is_active" in payload and not payload["is_active"]:
                raise ValidationException(message="不能停用当前登录账号", field="is_active")
        _assert_can_manage(actor_role, user)
        if "tenant_role" in payload:
            role = str(payload["tenant_role"])
            _reject_platform_role(role, payload)
            if role not in TENANT_ROLES:
                raise ValidationException(message=f"租户角色不合法: {role}", field="tenant_role")
            if user.tenant_role == "owner":
                raise ValidationException(
                    message="不可变更 owner 角色（租户唯一所有者）", field="tenant_role")
            _assert_can_assign(actor_role, role)
            user.tenant_role = role
            user.role = derive_legacy_role(role)
        if "is_active" in payload:
            if user.tenant_role == "owner" and not payload["is_active"]:
                raise ValidationException(
                    message="不可禁用 owner（租户唯一所有者）", field="is_active")
            user.is_active = bool(payload["is_active"])
        await self.session.flush()
        snapshot = _to_dict(user)
        await self.session.commit()
        return snapshot

    async def reset_password(self, tenant_id: int, member_id: int, new_password: str,
                             actor_role: str | None = None) -> dict:
        logger.info(f"重置成员密码 | tenant={tenant_id} member={member_id} actor_role={actor_role}")
        if len(new_password) < 6:
            raise ValidationException(message="密码至少 6 位", field="new_password")
        user = (await self.session.execute(
            select(User).where(User.tenant_id == tenant_id, User.id == member_id,
                               User.deleted_at.is_(None))
        )).scalar_one_or_none()
        if user is None:
            _member_missing()
        _assert_can_manage(actor_role, user)
        user.password_hash = await asyncio.to_thread(get_password_hash, new_password)
        # 审计 QA-B1-12：重置密码即吊销该成员已签发的全部会话
        user.token_version = int(user.token_version or 0) + 1
        await self.session.flush()
        await self.session.commit()
        return {"id": member_id, "reset": True}

    async def delete_member(self, tenant_id: int, member_id: int, actor_id: int,
                            actor_role: str | None = None) -> dict:
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
            _member_missing()
        if user.is_platform_admin:
            _member_missing()
        if user.tenant_role == "owner":
            raise ValidationException(message="不可删除租户 owner（租户唯一所有者）", field="member_id")
        if user.id == actor_id:
            raise ValidationException(message="不可删除当前登录账号", field="member_id")
        _assert_can_manage(actor_role, user)
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
            _member_missing()
        # 收件箱清理 + 软删同一事务（ADR-0007：service 方法 = 业务不可分割操作）
        await self.session.commit()
        return {"id": member_id, "deleted": True}

    async def transfer_ownership(self, tenant_id: int, member_id: int, *, actor_id: int,
                                 actor_role: str | None, password: str) -> dict:
        """转让负责人（决策 D23）：对方成为负责人，本人降为管理员并吊销本人全部会话

        - 仅负责人本人，且须再次输入登录密码
        - 负责人邮箱未验证不能转（否则「注册 → 建成员 → 转让」绕过 D21 验证闸）
        - 目标：本企业在册、启用中的非平台成员，且不是自己
        - 并发：降级原负责人用条件更新（仍是 owner 才改），两次并发转让只有一次生效
        """
        logger.info(f"转让负责人 | tenant={tenant_id} from={actor_id} to={member_id}")
        if actor_role != "owner":
            logger.warning(f"非负责人尝试转让被拒 | actor={actor_id} role={actor_role}")
            _hierarchy_denied()
        actor = (await self.session.execute(
            select(User).where(User.tenant_id == tenant_id, User.id == actor_id,
                               User.tenant_role == "owner", User.deleted_at.is_(None))
        )).scalar_one_or_none()
        if actor is None:
            _hierarchy_denied()
        ok = await asyncio.to_thread(verify_password, password or "", str(actor.password_hash or ""))
        if not ok:
            logger.warning(f"转让负责人密码校验失败 | actor={actor_id}")
            raise BusinessException(message="登录密码不正确", code="PASSWORD_INCORRECT", status_code=403)
        if actor.email_verify_pending:
            from backend.services.email_verification_service import EMAIL_NOT_VERIFIED

            raise BusinessException(message="请先验证负责人邮箱，再转让负责人。",
                                    code=EMAIL_NOT_VERIFIED, status_code=403)
        target = (await self.session.execute(
            select(User).where(User.tenant_id == tenant_id, User.id == member_id,
                               User.deleted_at.is_(None))
        )).scalar_one_or_none()
        if target is None or target.is_platform_admin:
            _member_missing()
        if int(target.id) == int(actor_id):
            raise ValidationException(message="你已经是负责人", field="member_id")
        if not target.is_active:
            raise ValidationException(message="该成员已停用，请先启用再转让", field="member_id")

        demoted = await self.session.execute(
            update(User)
            .where(User.id == actor_id, User.tenant_id == tenant_id, User.tenant_role == "owner")
            .values(tenant_role="admin", role=derive_legacy_role("admin"),
                    token_version=User.token_version + 1)
        )
        if demoted.rowcount != 1:
            logger.warning(f"转让负责人并发冲突 | tenant={tenant_id} actor={actor_id}")
            _hierarchy_denied()
        target.tenant_role = "owner"
        target.role = derive_legacy_role("owner")
        await self.session.commit()
        logger.info(f"负责人已转让 | tenant={tenant_id} from={actor_id} to={member_id}")
        return {"owner_id": int(member_id), "previous_owner_id": int(actor_id)}

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
                "created_at": utc_iso(r.created_at),
            }
            for r in rows
        ]
