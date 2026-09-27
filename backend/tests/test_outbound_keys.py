"""T-04（FR-51 前半）出站拉数钥匙域：签发/吊销/列表 + 只读拒绝。

GWT-51.1 签发半格（明文一次 + 前缀/hash 落库）/ 51.2 空态句 /
51.5 只读签发拒绝 / 51.8 再进页不见明文 / 51.9 只读吊销拒绝。
拉数执法、与渠道组互否、签发事件在 T-05（不在此文件）。
"""
import asyncio
import hashlib

from sqlalchemy import select

from platform_core.models.outbound_key import OutboundKey

_FORBIDDEN_CODES = {"FORBIDDEN", "QUOTA_EXCEEDED", "QUOTA_PLAN_LOCKED", "HTTP_403", "HTTP_429"}
EMPTY_51_2 = "还没有出站拉数钥匙。签发后才能从外部系统拉本企业结果。"


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
            return token.access_token, int(u.id)

    token, uid = asyncio.run(_go())
    return {"Authorization": f"Bearer {token}"}, uid


def _keys_of(db_session, tid: int) -> list[OutboundKey]:
    async def _go():
        async with db_session() as s:
            rows = (await s.execute(
                select(OutboundKey).where(OutboundKey.tenant_id == tid).order_by(OutboundKey.id.asc())
            )).scalars().all()
            return list(rows)

    return asyncio.run(_go())


def _assert_contact_admin_no_inner_code(resp) -> None:
    """GWT-51.5/51.9：可见句=「请联系企业管理员」，无 403/内码/裸 429。"""
    assert resp.status_code != 429
    body = resp.json()
    assert body["code"] not in _FORBIDDEN_CODES
    assert "请联系企业管理员" in body["message"]
    for token in ("FORBIDDEN", "QUOTA_EXCEEDED", "QUOTA_PLAN_LOCKED"):
        assert token not in body["message"]


def test_gwt_51_1_operator_issues_plaintext_once_prefix_stored(db_client, db_session, db_engine):
    """签发半格：明文只回一次且非 sk-；库内只落 hash+前缀（GWT-51.1）。"""
    from conftest import make_tenant_owner_headers

    _, tid = make_tenant_owner_headers(db_session, slug="t04-511")
    operator, operator_uid = _make_member_headers(db_session, tid, "operator", "t04-op-511")

    resp = db_client.post("/api/v1/outbound/keys", headers=operator, json={"name": "数据管道"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    data = body["data"]
    raw = data["plaintext_key"]
    assert raw.startswith("ok-") and not raw.startswith("sk-")  # ADR-0020：非 sk- 前缀
    assert data["key_prefix"] == raw[:10]
    assert data["status"] == "active"
    assert "出站拉数钥匙" in body["message"]  # 产品名钉死（不是渠道组令牌）
    assert "渠道组令牌" not in body["message"]

    rows = _keys_of(db_session, tid)
    assert len(rows) == 1  # 不产生第二把
    row = rows[0]
    assert row.key_hash == hashlib.sha256(raw.encode("utf-8")).hexdigest()
    assert row.key_hash != raw and len(row.key_hash) == 64  # 明文不落库
    assert row.key_prefix == raw[:10]
    assert row.revoked_at is None
    assert int(row.issued_by_user_id) == operator_uid  # 签发者留审计
    assert row.tenant_id == tid  # PIT-4：钥匙必须挂本企业
    assert row.name == "数据管道"


def test_gwt_51_2_empty_state_sentence(db_client, db_session, db_engine):
    """空态：零把钥匙 → 列表空 + spec 冻结句；只读也能看列表（51.9 前置）。"""
    from conftest import make_tenant_owner_headers

    owner, tid = make_tenant_owner_headers(db_session, slug="t04-512")
    viewer, _ = _make_member_headers(db_session, tid, "viewer", "t04-view-512")

    for headers in (owner, viewer):
        resp = db_client.get("/api/v1/outbound/keys", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"] == []
        assert resp.json()["message"] == EMPTY_51_2


def test_gwt_51_5_viewer_cannot_issue_no_key_row(db_client, db_session, db_engine):
    """只读签发：拒绝 + 找管理员句；不产生钥匙行。"""
    from conftest import make_tenant_owner_headers

    _, tid = make_tenant_owner_headers(db_session, slug="t04-515")
    viewer, _ = _make_member_headers(db_session, tid, "viewer", "t04-view-515")

    resp = db_client.post("/api/v1/outbound/keys", headers=viewer, json={"name": "越权"})
    _assert_contact_admin_no_inner_code(resp)
    assert _keys_of(db_session, tid) == []


def test_gwt_51_8_revisit_shows_prefix_and_status_only(db_client, db_session, db_engine):
    """再进页不见明文：列表只回前缀与状态。"""
    from conftest import make_tenant_owner_headers

    _, tid = make_tenant_owner_headers(db_session, slug="t04-518")
    operator, _ = _make_member_headers(db_session, tid, "operator", "t04-op-518")
    issued = db_client.post("/api/v1/outbound/keys", headers=operator, json={})
    assert issued.status_code == 201, issued.text
    key_id = issued.json()["data"]["id"]
    prefix = issued.json()["data"]["key_prefix"]

    listed = db_client.get("/api/v1/outbound/keys", headers=operator)
    assert listed.status_code == 200
    rows = listed.json()["data"]
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == key_id
    assert row["key_prefix"] == prefix
    assert row["status"] == "active"
    assert "plaintext_key" not in row  # 契约上列表无明文字段
    assert "plaintext" not in listed.text  # 响应体任何位置都不出现明文


def test_gwt_51_9_viewer_cannot_revoke_key_stays_active(db_client, db_session, db_engine):
    """只读吊销：拒绝 + 找管理员句；钥匙仍 active。"""
    from conftest import make_tenant_owner_headers

    _, tid = make_tenant_owner_headers(db_session, slug="t04-519")
    operator, _ = _make_member_headers(db_session, tid, "operator", "t04-op-519")
    issued = db_client.post("/api/v1/outbound/keys", headers=operator, json={})
    assert issued.status_code == 201, issued.text
    key_id = issued.json()["data"]["id"]

    viewer, _ = _make_member_headers(db_session, tid, "viewer", "t04-view-519")
    resp = db_client.delete(f"/api/v1/outbound/keys/{key_id}", headers=viewer)
    _assert_contact_admin_no_inner_code(resp)
    rows = _keys_of(db_session, tid)
    assert len(rows) == 1 and rows[0].revoked_at is None  # 未写 revoked_at，仍可拉数
    assert db_client.get("/api/v1/outbound/keys", headers=operator).json()["data"][0]["status"] == "active"


def test_revoke_terminal_idempotent_cross_tenant_404(db_client, db_session, db_engine):
    """经办/负责人可吊销；revoked 是终态（重复吊销幂等）；跨企业 404 同形。"""
    from conftest import make_tenant_owner_headers

    owner, tid = make_tenant_owner_headers(db_session, slug="t04-rvk")
    operator, _ = _make_member_headers(db_session, tid, "operator", "t04-op-rvk")
    issued = db_client.post("/api/v1/outbound/keys", headers=operator, json={})
    assert issued.status_code == 201, issued.text
    key_id = issued.json()["data"]["id"]

    revoked = db_client.delete(f"/api/v1/outbound/keys/{key_id}", headers=owner)
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["data"]["status"] == "revoked"
    assert revoked.json()["data"]["revoked_at"] is not None
    first_revoked_at = revoked.json()["data"]["revoked_at"]

    again = db_client.delete(f"/api/v1/outbound/keys/{key_id}", headers=owner)
    assert again.status_code == 200  # 幂等：已吊销再吊销不报错不复活
    assert again.json()["data"]["status"] == "revoked"
    assert again.json()["data"]["revoked_at"] == first_revoked_at  # 终态不再改写

    other, other_tid = make_tenant_owner_headers(db_session, slug="t04-other")
    stolen = db_client.delete(f"/api/v1/outbound/keys/{key_id}", headers=other)
    assert stolen.status_code == 404  # 跨企业 404 同形
    other_list = db_client.get("/api/v1/outbound/keys", headers=other)
    assert other_list.status_code == 200
    assert other_list.json()["data"] == []  # 他企业列表看不到本企业钥匙
    assert all(int(r.tenant_id) != other_tid for r in _keys_of(db_session, tid))


def test_admin_and_operator_both_allowed_on_issue_and_revoke(db_client, db_session, db_engine):
    """角色面：owner/admin/operator 都可签发与吊销（仅只读被拒）。"""
    from conftest import make_tenant_owner_headers

    owner, tid = make_tenant_owner_headers(db_session, slug="t04-roles")
    admin, _ = _make_member_headers(db_session, tid, "admin", "t04-admin-roles")
    operator, _ = _make_member_headers(db_session, tid, "operator", "t04-op-roles")

    by_admin = db_client.post("/api/v1/outbound/keys", headers=admin, json={})
    assert by_admin.status_code == 201
    by_operator = db_client.post("/api/v1/outbound/keys", headers=operator, json={})
    assert by_operator.status_code == 201
    assert len(_keys_of(db_session, tid)) == 2  # 一企业允许多把并存

    revoked = db_client.delete(
        f"/api/v1/outbound/keys/{by_admin.json()['data']['id']}", headers=owner,
    )
    assert revoked.status_code == 200
    assert revoked.json()["data"]["status"] == "revoked"
