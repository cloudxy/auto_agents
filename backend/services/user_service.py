"""用户管理服务 - 业务逻辑编排层

职责：
- 用户列表查询（管理后台用户管理页）
- 所有数据库操作通过 Repository，不直接操作 SQL
"""
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.user_repository import UserRepository
from platform_core.logger import get_logger
from platform_core.schemas.auth import UserListResponse, UserResponse

logger = get_logger("api")

# 平台租户 slug（024 种子；set_admin_account / create_user 同口径）
PLATFORM_TENANT_SLUG = "platform"
# 种子 admin 用户名（init_project.sh / set_admin_account.py 单一口径）
SEED_ADMIN_USERNAME = "admin"
# GWT-92.8：恢复成功上报的产品事实事件名（props 带 restored_user_id）
USER_RESTORED_EVENT = "user_restored"


@dataclass(frozen=True)
class AuthIdentity:
    """鉴权身份 DB 快照（F-01 单一事实源载荷）

    中间件 platform_scope 复核（middleware/tenant_context.py）与
    deps.get_current_user 权限快照共用同一加载函数 load_auth_identity——
    「撤销平台超管立即生效」在隔离作用域与权限守卫两层看到同一行数据（双源一致）。
    纯数据快照：ORM 实体不出 service 层（R7 口径）。
    """

    id: int
    username: str
    role: str | None
    is_admin: bool
    tenant_id: int | None
    tenant_role: str | None
    is_platform_admin: bool
    is_active: bool


# 鉴权身份加载（单一事实源，F-01）。含已软删行——删除时 is_active 已同步置 False，
# 停用判定由调用方做（与 T1 收口 get_user_for_auth 的 session.get 口径一致：
# 主键直查、不经软删过滤；中间件复核发生在任何 scope 进入之前，无注入过滤）。
async def load_auth_identity(session: AsyncSession, user_id: int) -> AuthIdentity | None:
    logger.debug(f"鉴权加载用户 | user_id={user_id}")
    from platform_core.models.user import User

    user = await session.get(User, user_id)
    if user is None:
        return None
    return AuthIdentity(
        id=user.id,
        username=user.username,
        role=user.role,
        is_admin=bool(user.is_admin),
        tenant_id=user.tenant_id,
        tenant_role=user.tenant_role,
        is_platform_admin=bool(user.is_platform_admin),
        is_active=bool(user.is_active),
    )


class UserService:
    """用户管理编排"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = UserRepository(session)

    async def list_users(self, skip: int = 0, limit: int = 20,
                         status: str = "active") -> UserListResponse:
        """分页查询用户（JOIN tenants 带归属公司名；不含密码哈希）

        status 筛选（T-24 / GWT-93.1/93.2）：active=默认视图（不含已删，
        既有行为保持）；deleted=已删筛选（只含软删行，行带 deleted_at 标记，
        恢复动作的入口读模型）。
        """
        logger.info(f"查询用户列表: skip={skip} limit={limit} status={status}")
        from sqlalchemy import func, select

        from platform_core.models.department import Department
        from platform_core.models.tenant import Tenant
        from platform_core.models.user import User

        if status == "deleted":
            alive_cond = User.deleted_at.isnot(None)
        else:
            alive_cond = User.deleted_at.is_(None)  # 软删除行不陈列（回收站语义见操作审计）

        rows = (await self.session.execute(
            select(User, Tenant.name.label("tenant_name"),
                   Department.name.label("department_name"))
            .outerjoin(Tenant, Tenant.id == User.tenant_id)
            .outerjoin(Department, Department.id == User.department_id)
            .where(alive_cond)
            .order_by(User.id.asc())
            .offset(skip).limit(limit)
        )).all()
        total = (await self.session.execute(
            select(func.count()).select_from(User).where(alive_cond)
        )).scalar_one()
        items = []
        for user, tenant_name, department_name in rows:
            resp = UserResponse.model_validate(user)
            resp.tenant_name = tenant_name
            resp.department_name = department_name
            items.append(resp)
        return UserListResponse(total=total, items=items)

    # ---------------- 平台超管 CRUD（用户管理页：增删改查 + 角色分配） ----------------

    async def create_user(self, payload) -> UserResponse:
        """创建账户（用户名/邮箱唯一；密码 bcrypt；tenant 校验存在）

        T5 决策 B：users.tenant_id 已 NOT NULL（迁移 024）——tenant_id 缺省的
        平台超管账户显式挂 platform 租户（不再产 NULL 行）；username 查重按
        (目标租户, username) 口径（跨租户同名是产品既定能力）。
        """
        import asyncio

        from sqlalchemy import select
        from sqlalchemy.exc import IntegrityError

        from platform_core.exceptions import BusinessException, ValidationException
        from platform_core.models.tenant import Tenant
        from platform_core.models.user import User
        from backend.utils.auth import get_password_hash

        tenant_role = None
        is_platform_admin = False
        target_tenant_id = payload.tenant_id
        if target_tenant_id is None or target_tenant_id == 0:
            # 平台账户（不挂公司）：显式挂 platform 租户（024 种子；NULL 租户语义
            # 已消灭）。0 = 前端「（平台账户，不挂公司）」选项值 → 同一映射，
            # 归属显示「平台租户」（GWT-95.4 显式化；行为不变，归属清晰）
            target_tenant_id = (await self.session.execute(
                select(Tenant.id).where(Tenant.slug == PLATFORM_TENANT_SLUG)
            )).scalar_one_or_none()
            if target_tenant_id is None:
                raise ValidationException(
                    message="platform 租户缺失（迁移 024 未执行？）", field="tenant_id")
            is_platform_admin = payload.role == "admin"
        else:
            tenant = (await self.session.execute(
                select(Tenant).where(Tenant.id == target_tenant_id)
            )).scalar_one_or_none()
            if tenant is None:
                raise ValidationException(message=f"租户不存在: {target_tenant_id}", field="tenant_id")
            tenant_role = "admin" if payload.role == "admin" else payload.role

        # 查重按在册行口径（042 唯一键在册化 / GWT-93.5/93.7 释放语义）：
        # 已删行不阻塞新建；并发窗口由 DB 唯一键兜底（IntegrityError → 400）
        if await self.repo.exists_username_in_tenant(target_tenant_id, payload.username):
            raise BusinessException(f"用户名已存在: {payload.username}")
        if await self.repo.get_by_email(payload.email):
            raise BusinessException(f"邮箱已注册: {payload.email}")
        user = User(
            username=payload.username,
            email=payload.email,
            password_hash=await asyncio.to_thread(get_password_hash, payload.password),
            is_active=payload.is_active,
            is_admin=payload.role == "admin",
            role=payload.role,
            tenant_id=target_tenant_id,
            tenant_role=tenant_role,
            is_platform_admin=is_platform_admin,
        )
        self.session.add(user)
        try:
            await self.session.flush()
        except IntegrityError:
            # 并发占名竞态兜底（db-spec §16.1：恢复先落 → 并发新建撞唯一键 →
            # 优雅报错，不裸奔 IntegrityError 500）
            await self.session.rollback()
            raise BusinessException("用户名或邮箱已被现有用户占用")
        await self.session.refresh(user)  # onupdate/默认列需回读，防 expired 属性同步 IO
        logger.info(f"创建用户 | id={user.id} username={payload.username} tenant={target_tenant_id}")
        resp = UserResponse.model_validate(user)
        resp.tenant_name = (await self.session.execute(
            select(Tenant.name).where(Tenant.id == target_tenant_id)
        )).scalar_one_or_none()
        # ADR-0007 D2：快照先于 commit（resp 已是 Pydantic 固化值）
        await self.session.commit()
        return resp

    async def update_user(self, user_id: int, payload, actor_id: int) -> UserResponse:
        """编辑账户：角色分配（role 单源）/启停/归属调整"""
        from sqlalchemy import select

        from platform_core.exceptions import BusinessException, ValidationException
        from platform_core.models.tenant import Tenant
        from platform_core.models.user import User

        user = (await self.session.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )).scalar_one_or_none()
        if user is None:
            raise BusinessException(f"用户不存在: {user_id}")
        changes = payload.model_dump(exclude_unset=True, exclude_none=True)
        if "role" in changes:
            if user_id == actor_id and changes["role"] != "admin":
                raise BusinessException("不能降级自己的 admin 角色（防自锁）")
            user.role = changes["role"]
            user.is_admin = changes["role"] == "admin"
            if user.tenant_id is not None:
                user.tenant_role = changes["role"]
        if "is_active" in changes:
            if user_id == actor_id and not changes["is_active"]:
                raise BusinessException("不能停用自己（防自锁）")
            user.is_active = changes["is_active"]
        if "tenant_id" in changes:
            if changes["tenant_id"] is not None:
                tenant = (await self.session.execute(
                    select(Tenant).where(Tenant.id == changes["tenant_id"])
                )).scalar_one_or_none()
                if tenant is None:
                    raise ValidationException(message=f"租户不存在: {changes['tenant_id']}", field="tenant_id")
            user.tenant_id = changes["tenant_id"]
            user.tenant_role = None if changes["tenant_id"] is None else (user.role or "operator")
        if "department_id" in changes:
            if changes["department_id"] is not None:
                from platform_core.models.department import Department

                dept = (await self.session.execute(
                    select(Department).where(
                        Department.id == changes["department_id"],
                        Department.deleted_at.is_(None))
                )).scalar_one_or_none()
                if dept is None:
                    raise ValidationException(message=f"部门不存在: {changes['department_id']}", field="department_id")
                if user.tenant_id is None or dept.tenant_id != user.tenant_id:
                    raise ValidationException(message="部门必须属于用户所在公司", field="department_id")
            user.department_id = changes["department_id"]
        await self.session.flush()
        await self.session.refresh(user)
        logger.info(f"更新用户 | id={user_id} fields={sorted(changes.keys())}")
        resp = UserResponse.model_validate(user)
        if user.department_id is not None:
            from platform_core.models.department import Department

            resp.department_name = (await self.session.execute(
                select(Department.name).where(Department.id == user.department_id)
            )).scalar_one_or_none()
        await self.session.commit()
        return resp

    async def delete_user(self, user_id: int, actor_id: int) -> None:
        """软删除账户（种子 admin 不可删；防删自己；防删最后一个平台超管）"""
        from sqlalchemy import func, select

        from platform_core.exceptions import BusinessException
        from platform_core.models.tenant import Tenant
        from platform_core.models.user import User

        user = (await self.session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()
        if user is None:
            raise BusinessException(f"用户不存在: {user_id}")
        # 种子 admin 守卫（T-26 / GWT-94.1，判定在既有两守卫之前）：身份=
        # (platform 租户, username='admin') 的平台超管行（set_admin_account
        # 按此精确取）；跨租户同名 admin 不误伤。即使存在第二个平台超管
        # （「最后超管」不适用）也拒绝，中文句不含内部码。
        if user.username == SEED_ADMIN_USERNAME and user.is_platform_admin:
            platform_id = (await self.session.execute(
                select(Tenant.id).where(Tenant.slug == PLATFORM_TENANT_SLUG)
            )).scalar_one_or_none()
            if platform_id is not None and user.tenant_id == platform_id:
                raise BusinessException("平台初始账号不可删除。")
        if user_id == actor_id:
            raise BusinessException("不能删除自己")
        if user.is_platform_admin:
            admins = (await self.session.execute(
                select(func.count()).select_from(User).where(
                    User.is_platform_admin == True,  # noqa: E712
                    User.is_active == True,  # noqa: E712
                    User.id != user_id,
                )
            )).scalar_one()
            if admins == 0:
                raise BusinessException("不能删除最后一个平台超管")
        user.deleted_at = func.now()
        user.is_active = False
        await self.session.flush()
        logger.warning(f"软删除用户 | id={user_id} username={user.username}")
        await self.session.commit()

    async def restore_user(self, user_id: int, actor_id: int) -> UserResponse:
        """恢复软删账户（T-24 / FR-93；仅平台超管，路由层 404 同形守卫）

        机制（db-spec §16.1）：
        - 占用预检与恢复写入同事务；正确性由 042 唯一键兜底——并发「新建占名
          先落」时恢复 UPDATE 使 alive_flag=1 撞唯一键 → IntegrityError → 回滚
          → 同句拒绝，现有用户行不被触碰（UPDATE 只清本行，永不覆盖他人）。
        - 恢复=单条条件 UPDATE（deleted_at IS NOT NULL 使 rowcount=0）：重复
          恢复/并发恢复均为 no-op，不写、不重复上报 user_restored（GWT-93.9）。
        - 占用判定各自独立（GWT-93.4）：username 同租户在册判、email 全局
          在册判，任一冲突即拒绝（预检只为提前给友好文案，不当正确性依据）。
        """
        logger.info(f"恢复软删用户 | id={user_id} actor={actor_id}")
        from sqlalchemy import select, update

        from sqlalchemy.exc import IntegrityError

        from platform_core.exceptions import BusinessException
        from platform_core.models.user import User

        from backend.services.product_event_service import emit_product_event

        user = (await self.session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()
        if user is None:
            raise BusinessException(f"用户不存在: {user_id}")
        if user.deleted_at is None:
            # GWT-93.9：已在册（含已恢复）= no-op，状态保持、无事件、无副作用
            return UserResponse.model_validate(user)

        # 占用预检（同事务；在册口径——目标行本身已删，不参与判重）
        if await self.repo.exists_username_in_tenant(user.tenant_id, user.username):
            raise BusinessException("用户名或邮箱已被现有用户占用")
        if await self.repo.exists_by_email(user.email):
            raise BusinessException("用户名或邮箱已被现有用户占用")

        # 快照先于写入/提交（ADR-0007 D2：commit 后属性惰性加载抛 MissingGreenlet）
        tenant_id_snapshot = int(user.tenant_id) if user.tenant_id is not None else None
        try:
            result = await self.session.execute(
                update(User)
                .where(User.id == user_id, User.deleted_at.isnot(None))
                .values(deleted_at=None, is_active=True)
            )
        except IntegrityError:
            # DB 兜底（并发新建占名先落）：回滚保持已删 + 同句（GWT-93.4/93.8）
            await self.session.rollback()
            raise BusinessException("用户名或邮箱已被现有用户占用")

        # 条件 UPDATE 后回读响应快照（身份映射中的旧实例已过期语义）
        fresh = (await self.session.execute(
            select(User).where(User.id == user_id)
            .execution_options(populate_existing=True)
        )).scalar_one()
        resp = UserResponse.model_validate(fresh)
        await self.session.commit()

        if result.rowcount == 1:
            logger.info(f"恢复软删用户成功 | id={user_id} tenant={tenant_id_snapshot}")
            # GWT-92.8：user_restored（tenant_id + restored_user_id）；失败不挡主路径
            await emit_product_event(
                self.session, USER_RESTORED_EVENT,
                tenant_id=tenant_id_snapshot, actor_user_id=actor_id,
                props={"restored_user_id": user_id},
            )
        else:
            # rowcount=0：预检后、UPDATE 前被并发恢复抢先 → no-op、不重复上报
            logger.info(f"恢复软删用户 no-op（并发已恢复） | id={user_id}")
        return resp
