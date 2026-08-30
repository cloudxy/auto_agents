"""一次性脚本：创建或重置管理员账号（admin / 123456）"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from platform_core.db import init_db, get_manager  # noqa: E402
from platform_core.models.user import User  # noqa: E402
from backend.utils.auth import get_password_hash, verify_password  # noqa: E402
from backend.repositories.user_repository import UserRepository  # noqa: E402

USERNAME = "admin"
PASSWORD = "123456"
EMAIL = "admin@example.com"


async def main():
    init_db()
    async for session in get_manager().get_async_session("DEFAULT"):
        repo = UserRepository(session)
        user = await repo.get_by_username(USERNAME)

        if user is None:
            user = User(
                username=USERNAME,
                email=EMAIL,
                password_hash=get_password_hash(PASSWORD),
                is_admin=True,
                is_active=True,
            )
            session.add(user)
            await session.commit()
            print(f"✅ 已创建管理员账号: {USERNAME}")
        else:
            user.password_hash = get_password_hash(PASSWORD)
            user.is_admin = True
            user.is_active = True
            await session.commit()
            print(f"✅ 已重置管理员账号密码: {USERNAME}")

        # 验证
        refreshed = await repo.get_by_username(USERNAME)
        assert verify_password(PASSWORD, refreshed.password_hash), "密码校验失败"
        print(f"✅ 密码校验通过 | username={refreshed.username} | is_admin={refreshed.is_admin} | is_active={refreshed.is_active}")


if __name__ == "__main__":
    asyncio.run(main())
