"""T-07（FR-60）渠道组空态可达 + 经办只读：GET 禁建组；无权者可见找管理员句。

GWT-60.4（无令牌空态）/ GWT-60.7（经办只读）。对照 test_billing_relay.py
骨架——「GET 必有 data[0]」金标已作废（contract §7.4：默认组只许显式建）。
"""
import asyncio
import uuid

from sqlalchemy import select

from platform_core.models.relay import RelayGroup, RelayToken

# spec 冻结句（GWT-60.4 / 60.7）——不另造第二套
MSG_TOKENS_EMPTY = "还没有令牌。签发后才能按下方用法调用平台网关。"
MSG_CANNOT_ISSUE = "当前账号不能签发，请联系企业管理员"
MSG_CANNOT_MODIFY_GROUP = "当前账号不能修改渠道组，请联系企业管理员"
_FORBIDDEN_CODES = {"FORBIDDEN", "HTTP_403", "QUOTA_EXCEEDED"}


def _make_member_headers(db_session, tid: int, tenant_role: str, username: str) -> dict:
    from backend.services.auth_service import AuthService
    from platform_core.models.user import User

    async def _go():
        async with db_session() as s:
            s.add(User(
                username=username, email=f"{username}@x.co", password_hash="x",
                role=tenant_role, tenant_id=tid, tenant_role=tenant_role, is_active=True,
            ))
            await s.commit()
            u = (await s.execute(select(User).where(User.username == username))).scalar_one()
            token = await AuthService(s).create_token({
                "id": u.id, "username": u.username, "is_admin": False, "role": tenant_role,
                "tenant_id": tid, "tenant_role": tenant_role, "is_platform_admin": False,
            })
            return token.access_token

    return {"Authorization": f"Bearer {asyncio.run(_go())}"}


def _group_count(db_session, tid: int) -> int:
    async def _go():
        async with db_session() as s:
            return len((await s.execute(
                select(RelayGroup).where(RelayGroup.tenant_id == tid)
            )).scalars().all())

    return asyncio.run(_go())


def test_gwt_60_4_viewer_get_groups_inserts_nothing(db_client, db_session, db_engine):
    from conftest import make_tenant_owner_headers

    owner, tid = make_tenant_owner_headers(db_session, slug="t07-604")
    from backend.tests.relay_sku_support import seed_relay_sku
    seed_relay_sku(db_session, tid)
    viewer = _make_member_headers(db_session, tid, "viewer", "t07-viewer-604")

    assert _group_count(db_session, tid) == 0
    resp = db_client.get("/api/v1/relay/groups", headers=viewer)
    assert resp.status_code == 200, resp.text
    # 空态可达：data 为空，禁止 GET 落 default 组
    assert resp.json()["data"] == []
    assert _group_count(db_session, tid) == 0
    # 无权者看见找管理员句（GWT-60.7 句面在页入口 groups 读模型上）
    assert MSG_CANNOT_ISSUE in resp.json()["message"]

    # 无令牌空态：冻结句不是「暂无数据」，viewer / owner 同句
    for headers in (viewer, owner):
        tokens = db_client.get("/api/v1/relay/tokens", headers=headers)
        assert tokens.status_code == 200, tokens.text
        assert tokens.json()["data"] == []
        assert tokens.json()["message"] == MSG_TOKENS_EMPTY


def test_gwt_60_7_operator_readonly_no_write_faces(db_client, db_session, db_engine):
    from conftest import make_tenant_owner_headers

    owner, tid = make_tenant_owner_headers(db_session, slug="t07-607")
    from backend.tests.relay_sku_support import seed_relay_sku
    seed_relay_sku(db_session, tid)
    operator = _make_member_headers(db_session, tid, "operator", "t07-operator-607")

    created = db_client.post(
        "/api/v1/relay/groups", headers=owner, json={"name": "g1", "models": ["gpt-4o"]},
    )
    assert created.status_code == 201, created.text
    gid = created.json()["data"]["id"]

    # 直接落一把已登记令牌（本票只测角色面；网关登记路径在 T-08 测）
    async def _seed_token() -> int:
        async with db_session() as s:
            row = RelayToken(
                tenant_id=tid, group_id=gid, name="seed", key_prefix="sk-seed",
                key_hash="h-" + uuid.uuid4().hex, quota_tokens=-1,
            )
            s.add(row)
            await s.commit()
            await s.refresh(row)
            return int(row.id)

    token_id = asyncio.run(_seed_token())

    # 经办能看：组与令牌读面 200（能看见 Base URL/用法/用量的数据面）
    assert db_client.get("/api/v1/relay/groups", headers=operator).status_code == 200
    tokens_view = db_client.get("/api/v1/relay/tokens", headers=operator)
    assert tokens_view.status_code == 200
    assert any(t["id"] == token_id for t in tokens_view.json()["data"])

    # 经办无签发/吊销/停用/建组的 API 面：可见句拒绝，不是裸 403 内码
    issue = db_client.post(
        "/api/v1/relay/tokens", headers=operator, json={"group_id": gid, "name": "x"},
    )
    assert issue.status_code != 403, issue.text
    assert MSG_CANNOT_ISSUE in issue.json()["message"]
    assert issue.json()["code"] not in _FORBIDDEN_CODES

    revoke = db_client.delete(f"/api/v1/relay/tokens/{token_id}", headers=operator)
    assert revoke.status_code != 403, revoke.text
    assert MSG_CANNOT_ISSUE in revoke.json()["message"]
    assert revoke.json()["code"] not in _FORBIDDEN_CODES

    patch = db_client.patch(
        f"/api/v1/relay/groups/{gid}", headers=operator, json={"status": "disabled"},
    )
    assert patch.status_code != 403, patch.text
    assert MSG_CANNOT_MODIFY_GROUP in patch.json()["message"]

    create = db_client.post("/api/v1/relay/groups", headers=operator, json={"name": "ops"})
    assert create.status_code != 403, create.text
    assert MSG_CANNOT_MODIFY_GROUP in create.json()["message"]

    # 拒绝即无副作用：组数不变、组仍 enabled、令牌未吊销、零新令牌
    async def _after():
        async with db_session() as s:
            groups = (await s.execute(
                select(RelayGroup).where(RelayGroup.tenant_id == tid)
            )).scalars().all()
            tokens = (await s.execute(
                select(RelayToken).where(RelayToken.tenant_id == tid)
            )).scalars().all()
            return (
                len(groups), {g.status for g in groups},
                len(tokens), {t.revoked_at for t in tokens},
            )

    group_n, statuses, token_n, revoked = asyncio.run(_after())
    assert group_n == 1 and statuses == {"enabled"}
    assert token_n == 1 and revoked == {None}
