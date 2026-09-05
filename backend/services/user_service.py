"""用户管理服务 - 业务逻辑编排层

职责：
- 用户列表查询（管理后台用户管理页）
- 所有数据库操作通过 Repository，不直接写 SQL
"""
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.user_repository import UserRepository
from platform_core.logger import get_logger
from platform_core.schemas.auth import UserListResponse, UserResponse

logger = get_logger("api")


# 鉴权用主键直查（含已软删行——删除时 is_active 已同步置 False，快照口径由调用方判定）。
# T1 收口（R7）：backend/app/api/deps.py 此前模块级 import User ORM 模型，改经本函数取实体；
# 保持 session.get 形态（不经软删过滤，行为与收口前一致）。
async def get_user_for_auth(session: AsyncSession, user_id: int):
    logger.debug(f"鉴权加载用户 | user_id={user_id}")
    from platform_core.models.user import User

    return await session.get(User, user_id)


class UserService:
    """用户管理编排"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = UserRepository(session)

    async def list_users(self, skip: int = 0, limit: int = 20) -> UserListResponse:
        """分页查询用户（JOIN tenants 带归属公司名；不含密码哈希）"""
        logger.info(f"查询用户列表: skip={skip}, limit={limit}")
        from sqlalchemy import func, select

        from platform_core.models.department import Department
        from platform_core.models.tenant import Tenant
        from platform_core.models.user import User

        rows = (await self.session.execute(
            select(User, Tenant.name.label("tenant_name"),
                   Department.name.label("department_name"))
            .outerjoin(Tenant, Tenant.id == User.tenant_id)
            .outerjoin(Department, Department.id == User.department_id)
            .where(User.deleted_at.is_(None))  # 软删除行不陈列（回收站语义见操作审计）
            .order_by(User.id.asc())
            .offset(skip).limit(limit)
        )).all()
        total = (await self.session.execute(
            select(func.count()).select_from(User).where(User.deleted_at.is_(None))
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

        from platform_core.exceptions import BusinessException, ValidationException
        from platform_core.models.tenant import Tenant
        from platform_core.models.user import User
        from backend.utils.auth import get_password_hash

        tenant_role = None
        is_platform_admin = False
        target_tenant_id = payload.tenant_id
        if target_tenant_id is None:
            # 平台超管账户：挂 platform 租户（024 种子；NULL 租户语义已消灭）
            target_tenant_id = (await self.session.execute(
                select(Tenant.id).where(Tenant.slug == "platform")
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

        # 查重按 (目标租户, username) 口径且含软删行（与唯一约束及 T4 占位一致）
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
        await self.session.flush()
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
        """软删除账户（防删自己；防删最后一个平台超管）"""
        from sqlalchemy import func, select

        from platform_core.exceptions import BusinessException
        from platform_core.models.user import User

        if user_id == actor_id:
            raise BusinessException("不能删除自己")
        user = (await self.session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()
        if user is None:
            raise BusinessException(f"用户不存在: {user_id}")
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
