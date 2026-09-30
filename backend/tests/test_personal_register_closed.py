"""决策 D1 = A（2026-09-29「按照建议做」）：关闭个人自助注册

个人注册都进同一个共享的 default 企业——不同人等于共用一个企业的数据。个人用户改走企业注册
（一人企业）。入口由 AUTH.PERSONAL_REGISTER_ENABLED 控制，默认关闭，关闭时与不存在的路由同形 404。
"""
from sqlalchemy import func, select

from platform_core.models.user import User

BODY = {"username": "solo-user", "email": "solo@x.co", "password": "Passw0rd!"}


def test_personal_register_is_closed_by_default(db_client, db_session):
    import asyncio

    resp = db_client.post("/api/v1/auth/register", json=BODY)
    missing = db_client.post("/api/v1/auth/no-such-endpoint", json=BODY)
    assert resp.status_code == missing.status_code == 404
    shape = lambda body: {k: v for k, v in body.items() if k != "request_id"}  # noqa: E731
    assert shape(resp.json()) == shape(missing.json())  # 与不存在的路由同形

    async def _count():
        async with db_session() as s:
            return (await s.execute(select(func.count()).select_from(User).where(User.username == "solo-user"))).scalar()

    assert asyncio.run(_count()) == 0
