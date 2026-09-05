"""用户数据访问层 - 封装所有 User 相关的数据库操作"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from platform_core.models.user import User
from platform_core.repository import BaseRepository


class UserRepository(BaseRepository[User]):
    """用户 Repository

    继承 BaseRepository，扩展用户特定的查询方法
    """

    def __init__(self, session: AsyncSession):
        super().__init__(model=User, session=session)

    async def get_by_username(self, username: str) -> list[User]:
        """按用户名查询**全部候选**用户（跨租户同名是产品既定能力，T5 决策 A）

        【R13 跨租户口径声明——此处显式允许跨租户查询】
        - User 继承 TenantMixin 后，tenant_scope 下本查询会被 do_orm_execute
          自动注入 tenant_id 过滤（跨租户同名行被裁掉）；登录链路**依赖**
          "登录请求无 token → 中间件不设作用域 → mode=none → 钩子不动"这一
          前提（T5 设计决策 C 的关键坑位）。未来若给登录加租户作用域，
          多租户同名登录将静默退化为单租户——test_auth_login_tenant.py 钉住。
        - 返回 list 而非单行：同名多行由调用方（auth_service 密码消歧 /
          user_service 租户口径查重）显式决策，不再让 scalar_one_or_none
          抛 MultipleResultsFound 500（T5 体检发现 1）。
        - 软删行不参与（deleted_at IS NULL）：软删用户不得登录（T4 软删时
          is_active=False 已拦一道，此处为直接 UPDATE deleted_at 的路径兜底）；
          查重场景**不走本方法**（软删行占唯一键位是有意行为，见
          exists_username_in_tenant）。
        """
        result = await self.session.execute(
            select(User).where(User.username == username, User.deleted_at.is_(None))
        )
        return list(result.scalars().all())

    async def get_by_email(self, email: str) -> Optional[User]:
        """根据邮箱查询用户"""
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def exists_username_in_tenant(self, tenant_id: int, username: str) -> bool:
        """租户内用户名占用检查（**含软删行**，T4 占位口径）

        users 的 (tenant_id, username) 唯一约束不豁免已删行——若只查活行，
        同名重建会在 flush 时撞唯一键 IntegrityError 500。软删成员的
        username 语义为"永久占用"（与 member_service 查重同一口径）。
        """
        result = await self.session.execute(
            select(User.id).where(
                User.tenant_id == tenant_id, User.username == username
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def exists_by_username(self, username: str) -> bool:
        """检查用户名是否存在"""
        return await self.exists(username=username)

    async def exists_by_email(self, email: str) -> bool:
        """检查邮箱是否存在"""
        return await self.exists(email=email)

    async def get_active_users(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> list[User]:
        """查询活跃用户列表"""
        result = await self.session.execute(
            select(User)
            .where(User.is_active == True)
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 20
    ) -> list[User]:
        """分页查询全部用户（最新优先，供用户管理页陈列）"""
        result = await self.session.execute(
            select(User)
            .order_by(User.id.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_users(self) -> int:
        """用户总数"""
        result = await self.session.execute(select(func.count(User.id)))
        return int(result.scalar() or 0)
