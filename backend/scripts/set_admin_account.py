"""一次性脚本：创建或重置管理员账号（admin / 123456）

T5 决策 B：平台超管显式建模——is_platform_admin=True + tenant_id=platform 租户
（slug='platform'，迁移 024 种子）。旧脚本靠 tenant_id=NULL 的兜底语义进
platform_scope（中间件已收紧，NULL 兜底不再授予平台态）。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import select  # noqa: E402

from platform_core.db import init_db, get_manager  # noqa: E402
from platform_core.models.tenant import Tenant  # noqa: E402
from platform_core.models.user import User  # noqa: E402
from backend.utils.auth import get_password_hash, verify_password  # noqa: E402

USERNAME = "admin"
PASSWORD = "123456"
EMAIL = "admin@example.com"


async def main():
    init_db()
    async for session in get_manager().get_async_session("DEFAULT"):
        platform_tenant = (await session.execute(
            select(Tenant).where(Tenant.slug == "platform")
        )).scalar_one_or_none()
        if platform_tenant is None:
            print("❌ platform 租户缺失：请先执行迁移 024（alembic upgrade head）")
            sys.exit(1)

        # 平台超管按 (platform 租户, username) 精确取（跨租户可能存在同名 admin）
        user = (await session.execute(
            select(User).where(
                User.username == USERNAME, User.tenant_id == platform_tenant.id)
        )).scalar_one_or_none()

        if user is None:
            user = User(
                username=USERNAME,
                email=EMAIL,
                password_hash=get_password_hash(PASSWORD),
                is_admin=True,
                is_active=True,
                role="admin",
                tenant_id=platform_tenant.id,
                tenant_role=None,
                is_platform_admin=True,
            )
            session.add(user)
            await session.commit()
            print(f"✅ 已创建平台超管账号: {USERNAME}（tenant=platform#{platform_tenant.id}）")
        else:
            user.password_hash = get_password_hash(PASSWORD)
            user.is_admin = True
            user.is_active = True
            user.is_platform_admin = True
            await session.commit()
            print(f"✅ 已重置平台超管账号密码: {USERNAME}")

        # 验证
        refreshed = (await session.execute(
            select(User).where(
                User.username == USERNAME, User.tenant_id == platform_tenant.id)
        )).scalar_one()
        assert verify_password(PASSWORD, refreshed.password_hash), "密码校验失败"
        print(f"✅ 密码校验通过 | username={refreshed.username} | is_admin={refreshed.is_admin} "
              f"| is_active={refreshed.is_active} | is_platform_admin={refreshed.is_platform_admin}")


if __name__ == "__main__":
    asyncio.run(main())
