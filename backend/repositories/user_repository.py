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
          查重场景**不走本方法**（在册占用判见 exists_username_in_tenant）。
        """
        result = await self.session.execute(
            select(User).where(User.username == username, User.deleted_at.is_(None))
        )
        return list(result.scalars().all())

    async def get_by_email(self, email: str) -> Optional[User]:
        """根据邮箱查询**在册**用户（deleted_at IS NULL）

        042 唯一键在册化后同 email 可存在多行（1 在册 + N 已删）——本方法
        必须保持软删过滤，否则 scalar_one_or_none 会因多已删行抛
        MultipleResultsFound（db-spec §16 红线）。查重/占用场景即「在册
        判」：已删行不阻塞新建（GWT-93.7 释放口径）。
        """
        result = await self.session.execute(
            select(User).where(User.email == email, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_login_candidates_by_email(self, email: str) -> list[User]:
        """登录路径按注册邮箱查候选（FR-83 / contract §7.6）

        - users.email 在册行全局唯一（042 后唯一键带 alive_flag 尾列）→ 0 或
          1 行；返回 list 与 get_by_username 同构，auth_service 下游（停用
          过滤/密码消歧）零分叉复用。
        - 软删行不参与（deleted_at IS NULL），与 get_by_username 登录口径
          一致：软删用户不得登录；042 在册化后多已删行共享 email 也不会歧义。
        - 查重/占用场景**不走本方法**（在册占用判见 exists_by_email /
          get_by_email，均已过滤软删行）。
        """
        result = await self.session.execute(
            select(User).where(User.email == email, User.deleted_at.is_(None))
        )
        return list(result.scalars().all())

    async def exists_username_in_tenant(self, tenant_id: int, username: str) -> bool:
        """租户内用户名**在册**占用检查（042 唯一键在册化口径，T-24/FR-93）

        users 的 (tenant_id, username, alive_flag) 唯一约束只对在册行生效
        （迁移 042）——软删行 NULL 脱离唯一，查重同步改在册判：已删行不阻塞
        同名新建（GWT-93.5 释放口径）；并发窗口由 DB 唯一键兜底（1062 →
        上层映射占用句）。登录路径不走本方法（见 get_by_username）。
        """
        result = await self.session.execute(
            select(User.id).where(
                User.tenant_id == tenant_id, User.username == username,
                User.deleted_at.is_(None),
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_active_id_by_username_in_tenant(
        self, tenant_id: int, username: str
    ) -> Optional[int]:
        """同租户在册用户 id（deleted_at IS NULL；软删行不参与）

        queue_depth 告警命中记录接收人解析（FR-105 / db-spec §16.6）：
        alert_rules.created_by 用户名 → 同租户在册 users.id；解析不出由
        调用方决策（不落命中行、不静默改投）。唯一键 (tenant_id, username,
        alive_flag) 保证至多一行。
        """
        if not username:
            return None
        result = await self.session.execute(
            select(User.id).where(
                User.tenant_id == tenant_id, User.username == username,
                User.deleted_at.is_(None),
            ).limit(1)
        )
        return result.scalar_one_or_none()

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
