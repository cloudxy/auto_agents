"""T-08（FR-60 / ADR-0019）签发/吊销经 LiteLLM HTTP 登记虚拟 Key：禁 DSN、禁本地假成功。

OpenAPI 核对（deploy/litellm 钉 ghcr.io/berriai/litellm:v1.100.0，实读
/openapi.json）：POST /key/generate（GenerateKeyRequest：key_alias / models /
rpm_limit / tpm_limit / metadata → GenerateKeyResponse：key=明文、token_id）；
POST /key/delete（KeyRequest：keys / key_aliases——**无 key_ids**，明文不落库
故按 key_alias 作废，本地 gateway_key_id 存 alias）。
"""
import asyncio
import hashlib

import httpx
from sqlalchemy import select

from platform_core.models.relay import RelayToken


def _stub_generate(monkeypatch, *, reply=None, error=None) -> list[dict]:
    from backend.services.llm_gateway import admin as gateway_admin

    calls: list[dict] = []

    async def _fake_generate(body, **_kwargs):
        calls.append(body)
        if error is not None:
            raise error
        return reply

    monkeypatch.setattr(gateway_admin, "generate_key", _fake_generate)
    return calls


def _stub_delete(monkeypatch, *, error=None) -> list[dict]:
    from backend.services.llm_gateway import admin as gateway_admin

    calls: list[dict] = []

    async def _fake_delete(body, **_kwargs):
        calls.append(body)
        if error is not None:
            raise error
        return {"deleted_keys": [], "key_aliases": {}}

    monkeypatch.setattr(gateway_admin, "delete_key", _fake_delete)
    return calls


def _create_group(db_client, owner, db_session, tid) -> int:
    from backend.tests.relay_sku_support import seed_relay_sku

    seed_relay_sku(db_session, tid)
    created = db_client.post(
        "/api/v1/relay/groups", headers=owner,
        json={"name": "vip", "rpm_limit": 60, "tpm_limit": 10000, "models": ["gpt-4o"]},
    )
    assert created.status_code == 201, created.text
    return created.json()["data"]["id"]


def _tokens_of(db_session, tid: int) -> list[RelayToken]:
    async def _go():
        async with db_session() as s:
            return list((await s.execute(
                select(RelayToken).where(RelayToken.tenant_id == tid)
            )).scalars().all())

    return asyncio.run(_go())


def _issue(db_client, owner, gid: int):
    return db_client.post(
        "/api/v1/relay/tokens", headers=owner,
        json={"group_id": gid, "name": "ci", "quota_tokens": 1000},
    )


def test_issue_registers_gateway_key_and_plaintext_once(
    db_client, db_session, db_engine, monkeypatch,
):
    from conftest import make_tenant_owner_headers

    owner, tid = make_tenant_owner_headers(db_session, slug="t08-issue")
    gid = _create_group(db_client, owner, db_session, tid)
    gen_calls = _stub_generate(
        monkeypatch, reply={"key": "sk-gw-plain-1", "token_id": "tok-1"},
    )

    issued = _issue(db_client, owner, gid)
    assert issued.status_code == 201, issued.text
    data = issued.json()["data"]
    # 网关明文只回一次（GWT-60.1 签发半程）
    assert data["plaintext_key"] == "sk-gw-plain-1"
    assert data["key_prefix"] == "sk-gw-plai"

    body = gen_calls[0]
    # 组上 models / rpm / tpm 映射为网关虚拟 Key 限额（ADR-0019 决策 1）
    assert body["models"] == ["gpt-4o"]
    assert body["rpm_limit"] == 60
    assert body["tpm_limit"] == 10000
    assert body["metadata"]["tenant_id"] == tid
    assert body["metadata"]["group_id"] == gid
    assert body["key_alias"]

    rows = _tokens_of(db_session, tid)
    assert len(rows) == 1
    row = rows[0]
    # 本地只存 hash + 网关不透明引用（gateway_key_id），明文不落库
    assert row.gateway_key_id == body["key_alias"]
    assert row.key_hash == hashlib.sha256(b"sk-gw-plain-1").hexdigest()
    assert row.key_prefix == "sk-gw-plai"

    listed = db_client.get("/api/v1/relay/tokens", headers=owner)
    assert listed.status_code == 200
    assert listed.json()["data"][0]["plaintext_key"] is None


def test_issue_group_without_limits_omits_zero_limits(
    db_client, db_session, db_engine, monkeypatch,
):
    from conftest import make_tenant_owner_headers

    owner, tid = make_tenant_owner_headers(db_session, slug="t08-nolimit")
    from backend.tests.relay_sku_support import seed_relay_sku
    seed_relay_sku(db_session, tid)
    created = db_client.post("/api/v1/relay/groups", headers=owner, json={"name": "flat"})
    assert created.status_code == 201, created.text
    gid = created.json()["data"]["id"]
    gen_calls = _stub_generate(
        monkeypatch, reply={"key": "sk-gw-plain-2", "token_id": "tok-2"},
    )

    issued = _issue(db_client, owner, gid)
    assert issued.status_code == 201, issued.text
    # 0=不限 → 不下发给网关（键整体缺省，不是 0）
    body = gen_calls[0]
    assert "models" not in body
    assert "rpm_limit" not in body
    assert "tpm_limit" not in body


def test_issue_gateway_5xx_visible_no_local_row(
    db_client, db_session, db_engine, monkeypatch,
):
    from conftest import make_tenant_owner_headers

    owner, tid = make_tenant_owner_headers(db_session, slug="t08-5xx")
    gid = _create_group(db_client, owner, db_session, tid)
    _req = httpx.Request("POST", "http://gw/key/generate")
    _stub_generate(
        monkeypatch,
        error=httpx.HTTPStatusError(
            "Server Error", request=_req, response=httpx.Response(503, request=_req),
        ),
    )

    resp = _issue(db_client, owner, gid)
    # 网关 HTTP 失败 = 签发失败可见（ADR-0019 决策 5），不是套餐句
    assert resp.status_code == 502, resp.text
    assert resp.json()["code"] == "RELAY_GATEWAY_UNAVAILABLE"
    assert "签发失败" in resp.json()["message"]
    assert "QUOTA" not in resp.json()["code"]
    assert "套餐" not in resp.json()["message"]
    # 禁止「列表有网关无」的本地假成功行
    assert _tokens_of(db_session, tid) == []


def test_issue_gateway_unreachable_visible_no_local_row(
    db_client, db_session, db_engine, monkeypatch,
):
    from conftest import make_tenant_owner_headers

    owner, tid = make_tenant_owner_headers(db_session, slug="t08-down")
    gid = _create_group(db_client, owner, db_session, tid)
    _stub_generate(monkeypatch, error=httpx.ConnectError("gateway down"))

    resp = _issue(db_client, owner, gid)
    assert resp.status_code == 502, resp.text
    assert resp.json()["code"] == "RELAY_GATEWAY_UNAVAILABLE"
    assert "签发失败" in resp.json()["message"]
    assert _tokens_of(db_session, tid) == []


def test_revoke_invalidates_gateway_then_local(
    db_client, db_session, db_engine, monkeypatch,
):
    from conftest import make_tenant_owner_headers

    owner, tid = make_tenant_owner_headers(db_session, slug="t08-revoke")
    gid = _create_group(db_client, owner, db_session, tid)
    gen_calls = _stub_generate(
        monkeypatch, reply={"key": "sk-gw-plain-3", "token_id": "tok-3"},
    )
    issued = _issue(db_client, owner, gid)
    assert issued.status_code == 201, issued.text
    token_id = issued.json()["data"]["id"]
    alias = gen_calls[0]["key_alias"]

    del_calls = _stub_delete(monkeypatch)
    revoked = db_client.delete(f"/api/v1/relay/tokens/{token_id}", headers=owner)
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["data"]["status"] == "revoked"
    # 吊销 = 网关 /key/delete 等价作废（按引用，明文不可再现）+ 本地 revoked
    assert del_calls == [{"key_aliases": [alias]}]
    rows = _tokens_of(db_session, tid)
    assert rows[0].revoked_at is not None

    # 再吊销幂等：不重复打网关
    again = db_client.delete(f"/api/v1/relay/tokens/{token_id}", headers=owner)
    assert again.status_code == 200
    assert again.json()["data"]["status"] == "revoked"
    assert len(del_calls) == 1


def test_revoke_gateway_failure_keeps_active_then_recovers(
    db_client, db_session, db_engine, monkeypatch,
):
    from conftest import make_tenant_owner_headers

    owner, tid = make_tenant_owner_headers(db_session, slug="t08-revfail")
    gid = _create_group(db_client, owner, db_session, tid)
    _stub_generate(
        monkeypatch, reply={"key": "sk-gw-plain-4", "token_id": "tok-4"},
    )
    issued = _issue(db_client, owner, gid)
    assert issued.status_code == 201, issued.text
    token_id = issued.json()["data"]["id"]

    _stub_delete(monkeypatch, error=httpx.ConnectError("gateway down"))
    resp = db_client.delete(f"/api/v1/relay/tokens/{token_id}", headers=owner)
    # 网关失败 = 吊销失败可见；不本地假吊销（ADR-0019 决策 4/5 同口径）
    assert resp.status_code == 502, resp.text
    assert resp.json()["code"] == "RELAY_GATEWAY_UNAVAILABLE"
    assert "吊销失败" in resp.json()["message"]
    assert _tokens_of(db_session, tid)[0].revoked_at is None

    # 网关恢复后再吊销成功
    del_calls = _stub_delete(monkeypatch)
    again = db_client.delete(f"/api/v1/relay/tokens/{token_id}", headers=owner)
    assert again.status_code == 200, again.text
    assert again.json()["data"]["status"] == "revoked"
    assert len(del_calls) == 1
    assert _tokens_of(db_session, tid)[0].revoked_at is not None
