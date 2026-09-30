"""转让负责人（决策 D23 = 边界 A + 转让，2026-09-29「按照建议做」）

负责人离职 / 换人时原先只能找平台改库。现在：
- 只有负责人本人能转让，且须再次输入登录密码（高危操作二次确认）
- 只能转给本企业在册、启用中的成员；不能转给自己、平台超管行（404 同形）、其他企业成员（404）
- 转让后：对方成为负责人，原负责人降为管理员；原负责人的会话全部失效（降权即吊销）
- 负责人邮箱未验证时不能转让（否则「注册 → 建成员 → 转让」可绕过 D21 验证闸）
- 留审计
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select, update

from backend.utils.auth import get_password_hash
from conftest import make_tenant_owner_headers
from platform_core.models.operation_log import OperationLog
from platform_core.models.user import User
from test_member_hierarchy import _owner_id, _seed_user

MEMBERS = "/api/v1/members"
PASSWORD = "Owner-Passw0rd!"


def _transfer(client, headers, member_id: int, password: str = PASSWORD):
    return client.post(f"{MEMBERS}/{member_id}/transfer-ownership", headers=headers, json={"password": password})


def _owner_with_password(db_session, slug: str) -> tuple[dict, int, int]:
    headers, tid = make_tenant_owner_headers(db_session, slug=slug)
    oid = _owner_id(db_session, tid)

    async def _go():
        async with db_session() as s:
            await s.execute(update(User).where(User.id == oid).values(password_hash=get_password_hash(PASSWORD)))
            await s.commit()

    asyncio.run(_go())
    return headers, tid, oid


def _roles(db_session, *ids: int) -> dict[int, tuple[str, str]]:
    async def _go():
        async with db_session() as s:
            rows = (await s.execute(select(User.id, User.tenant_role, User.role).where(User.id.in_(ids)))).all()
            return {int(r.id): (r.tenant_role, r.role) for r in rows}
    return asyncio.run(_go())


def test_owner_transfers_to_member_and_old_owner_becomes_admin(db_client, db_session):
    owner, tid, oid = _owner_with_password(db_session, "xfer-ok")
    member, mid = _seed_user(db_session, tid, "xfer-op", tenant_role="operator", role="operator")

    resp = _transfer(db_client, owner, mid)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["owner_id"] == mid

    roles = _roles(db_session, oid, mid)
    assert roles[mid] == ("owner", "admin")
    assert roles[oid] == ("admin", "admin")
    # 原负责人降权 → 旧会话失效；新负责人按库内角色立即获得管理权
    assert db_client.get(MEMBERS, headers=owner).status_code == 401
    assert db_client.get(MEMBERS, headers=member).status_code == 200

    async def _audit():
        async with db_session() as s:
            return (await s.execute(select(OperationLog.action, OperationLog.target)
                                    .where(OperationLog.action == "member.transfer_ownership"))).all()
    assert [(a, t) for a, t in asyncio.run(_audit())] == [("member.transfer_ownership", f"user#{mid}")]


def test_wrong_password_changes_nothing(db_client, db_session):
    owner, tid, oid = _owner_with_password(db_session, "xfer-pw")
    _h, mid = _seed_user(db_session, tid, "xfer-pw-admin", tenant_role="admin", role="admin")
    resp = _transfer(db_client, owner, mid, password="wrong-password")
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "PASSWORD_INCORRECT"
    assert _roles(db_session, oid, mid) == {oid: ("owner", "admin"), mid: ("admin", "admin")}


def test_only_owner_can_transfer(db_client, db_session):
    _owner, tid, oid = _owner_with_password(db_session, "xfer-admin")
    admin, _aid = _seed_user(db_session, tid, "xfer-admin-a", tenant_role="admin", role="admin")
    _h, vid = _seed_user(db_session, tid, "xfer-admin-v", tenant_role="viewer")
    resp = _transfer(db_client, admin, vid)
    assert resp.status_code == 403
    assert resp.json()["code"] == "MEMBER_HIERARCHY"
    assert _roles(db_session, oid)[oid][0] == "owner"


def test_invalid_targets(db_client, db_session):
    owner, tid, oid = _owner_with_password(db_session, "xfer-bad")
    _h, off = _seed_user(db_session, tid, "xfer-bad-off", tenant_role="operator", role="operator")
    _h, plat = _seed_user(db_session, tid, "xfer-bad-plat", tenant_role=None, role="admin", platform=True)
    _other_owner, other_tid = make_tenant_owner_headers(db_session, slug="xfer-bad-other")
    _h, foreign = _seed_user(db_session, other_tid, "xfer-bad-foreign", tenant_role="operator", role="operator")

    async def _disable():
        async with db_session() as s:
            await s.execute(update(User).where(User.id == off).values(is_active=False))
            await s.commit()
    asyncio.run(_disable())

    assert _transfer(db_client, owner, oid).status_code == 422          # 自己
    assert _transfer(db_client, owner, off).status_code == 422          # 已停用
    assert _transfer(db_client, owner, plat).status_code == 404         # 平台超管行不可见
    assert _transfer(db_client, owner, foreign).status_code == 404      # 其他企业
    assert _roles(db_session, oid)[oid][0] == "owner"


def test_unverified_owner_cannot_transfer(db_client, db_session):
    owner, tid, oid = _owner_with_password(db_session, "xfer-unv")
    _h, mid = _seed_user(db_session, tid, "xfer-unv-op", tenant_role="operator", role="operator")

    async def _pending():
        async with db_session() as s:
            await s.execute(update(User).where(User.id == oid).values(email_verify_pending=True))
            await s.commit()
    asyncio.run(_pending())

    resp = _transfer(db_client, owner, mid)
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "EMAIL_NOT_VERIFIED"
    assert _roles(db_session, oid)[oid][0] == "owner"
