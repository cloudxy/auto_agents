"""T-05（FR-51 后半 + FR-92.3）出站拉数执法 + 与渠道组互否 + 签发事件。

查找链（ADR-0020 §2）：先出站钥匙表（SHA-256 指纹 + compare_digest）
→ 未命中走既有 KEY_BINDINGS（FR-13 平台钥匙行为不放宽）→ 两环未命中 401/0 行。

GWT-51.1 后半（拉到行）/ 51.3 未绑定·乱填 / 51.4 跨企业 / 51.6 渠道组 sk-
互否 / 51.7 吊销后再拉 / 51.10 出站钥匙打网关路径 / GWT-92.3 签发事件无明文 /
GWT-92.6 事件失败不挡签发。
"""
import asyncio
import json

import httpx
import pytest
from sqlalchemy import select

from platform_core.models.product_event import ProductEvent
from platform_core.models.relay import RelayToken
from platform_core.models.spider_result import SpiderResult
from platform_core.models.spider_task import SpiderTask

PULL = "/external/v1/public/data"


# ---------------------------------------------------------------------------
# 种子 / 查询辅助
# ---------------------------------------------------------------------------

def _seed_results(db_session, tid: int, spider: str, *, marker: str, count: int = 1) -> None:
    """给企业种非候选采集行（source=web；task 外键一并落）。"""

    async def _go():
        async with db_session() as s:
            task = SpiderTask(
                tenant_id=tid, spider_name=spider, status="completed", params="{}",
            )
            s.add(task)
            await s.flush()
            for i in range(count):
                s.add(SpiderResult(
                    task_id=int(task.id), tenant_id=tid, spider_name=spider,
                    url=f"https://{marker}.example/{i}", title=f"{marker}-{i}",
                    source="web",
                ))
            await s.commit()

    asyncio.run(_go())


def _pull(db_client, spider: str, key: str):
    return db_client.get(f"{PULL}/{spider}", headers={"X-API-Key": key})


def _issue_outbound_key(db_client, operator: dict, name: str = "数据管道") -> str:
    issued = db_client.post("/api/v1/outbound/keys", headers=operator, json={"name": name})
    assert issued.status_code == 201, issued.text
    return issued.json()["data"]["plaintext_key"]


def _events_of(db_session, name: str) -> list[ProductEvent]:
    async def _go():
        async with db_session() as s:
            return list((await s.execute(
                select(ProductEvent).where(ProductEvent.event_name == name)
            )).scalars().all())

    return asyncio.run(_go())


def _relay_usage_of(db_session, tid: int) -> list[tuple]:
    """渠道组用量基线快照：(id, used_tokens, revoked_at)。"""

    async def _go():
        async with db_session() as s:
            rows = (await s.execute(
                select(RelayToken).where(RelayToken.tenant_id == tid).order_by(RelayToken.id)
            )).scalars().all()
            return [(int(r.id), int(r.used_tokens or 0), r.revoked_at) for r in rows]

    return asyncio.run(_go())


# ---------------------------------------------------------------------------
# GWT-51.1 后半 + 查找链
# ---------------------------------------------------------------------------

def test_gwt_51_1_latter_half_outbound_key_pulls_own_rows(db_client, db_session, db_engine):
    """51.1 后半：刚签发的出站钥匙拉本企业结果能拿到行（真实 DB 全链）。"""
    from conftest import make_tenant_owner_headers
    from test_outbound_keys import _make_member_headers

    owner, tid = make_tenant_owner_headers(db_session, slug="t05-511")
    operator, _ = _make_member_headers(db_session, tid, "operator", "t05-op-511")
    _seed_results(db_session, tid, "alpha", marker="a-owned")

    raw = _issue_outbound_key(db_client, operator)
    assert raw.startswith("ok-") and not raw.startswith("sk-")

    resp = _pull(db_client, "alpha", raw)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] >= 1
    assert any("a-owned" in (item.get("url") or "") for item in body["items"])


def test_chain_fallback_key_bindings_still_works(db_client, db_session, db_engine):
    """FR-13 不放宽：无出站钥匙时，配置绑定钥匙（KEY_BINDINGS）仍可拉数。"""
    from config import settings

    from conftest import make_tenant_owner_headers

    _, tid = make_tenant_owner_headers(db_session, slug="t05-fr13")
    _seed_results(db_session, tid, "alpha", marker="fr13-owned")
    original = settings.get("EXTERNAL_API.KEY_BINDINGS", [])
    settings.set("EXTERNAL_API.KEY_BINDINGS", [
        {"key": "cfg-bound-platform-key", "tenant_id": int(tid)},
    ])
    try:
        resp = _pull(db_client, "alpha", "cfg-bound-platform-key")
    finally:
        settings.set("EXTERNAL_API.KEY_BINDINGS", original)
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] >= 1
    assert any("fr13-owned" in (item.get("url") or "") for item in resp.json()["items"])


# ---------------------------------------------------------------------------
# GWT-51.3 / 51.4 / 51.6 / 51.7：拒绝面全部 0 行
# ---------------------------------------------------------------------------

def test_gwt_51_3_unbound_or_garbage_key_rejected_zero_rows(db_client, db_session, db_engine):
    """51.3：ok- 形态但未签发 / 乱填 → 与 FR-13 同一拒绝（401，0 行）。"""
    from conftest import make_tenant_owner_headers

    _, tid = make_tenant_owner_headers(db_session, slug="t05-513")
    _seed_results(db_session, tid, "alpha", marker="a-owned")

    for bogus in ("ok-never-issued-anywhere-1234567890", "totally-made-up", ""):
        resp = _pull(db_client, "alpha", bogus)
        assert resp.status_code == 401, f"key={bogus[:6]}… 应拒绝"
        assert resp.json().get("items") in (None, [])


def test_gwt_51_4_tenant_a_key_never_returns_tenant_b_rows(db_client, db_session, db_engine):
    """51.4：A 的钥匙拉同名爬虫 → 只有 A 的行；B 的行不出现。"""
    from conftest import make_tenant_owner_headers
    from test_outbound_keys import _make_member_headers

    _, tid_a = make_tenant_owner_headers(db_session, slug="t05-51a")
    _, tid_b = make_tenant_owner_headers(db_session, slug="t05-51b")
    operator_a, _ = _make_member_headers(db_session, tid_a, "operator", "t05-op-51a")
    _seed_results(db_session, tid_a, "shared", marker="a-owned")
    _seed_results(db_session, tid_b, "shared", marker="b-owned")

    raw = _issue_outbound_key(db_client, operator_a)
    resp = _pull(db_client, "shared", raw)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert items, "A 的行应可见"
    assert all("a-owned" in (item.get("url") or "") for item in items)
    assert not any("b-owned" in (item.get("url") or "") for item in items)  # B 的行不出现


def test_gwt_51_6_relay_sk_token_rejected_and_not_listed(
    db_client, db_session, db_engine, monkeypatch,
):
    """51.6：本企业刚签发的渠道组 sk- 当出站钥匙 → 拒绝 0 行；出站入口不列它。"""
    from conftest import make_tenant_owner_headers
    from test_relay_token_gateway import _create_group, _stub_generate

    owner, tid = make_tenant_owner_headers(db_session, slug="t05-516")
    _stub_generate(
        monkeypatch, reply={"key": "sk-relay-fresh-token-x", "token_id": "tok-516"},
    )
    gid = _create_group(db_client, owner, db_session, tid)
    issued = db_client.post(
        "/api/v1/relay/tokens", headers=owner,
        json={"group_id": gid, "name": "ci", "quota_tokens": 1000},
    )
    assert issued.status_code == 201, issued.text
    sk_raw = issued.json()["data"]["plaintext_key"]
    assert sk_raw.startswith("sk-")

    # 同企业的渠道组令牌也拉不到本企业数据（查找集合不相交）
    _seed_results(db_session, tid, "alpha", marker="a-owned")
    resp = _pull(db_client, "alpha", sk_raw)
    assert resp.status_code == 401
    assert resp.json().get("items") in (None, [])

    # 出站入口不得把渠道组令牌列成出站拉数钥匙
    listed = db_client.get("/api/v1/outbound/keys", headers=owner)
    assert listed.status_code == 200
    rows = listed.json()["data"]
    assert rows == []  # 本企业没签过出站钥匙：sk- 令牌绝不入列
    assert all(r["key_prefix"].startswith("ok-") for r in rows)


def test_gwt_51_7_revoked_key_pull_zero_rows(db_client, db_session, db_engine):
    """51.7：签发→拉到行→吊销→再拉 0 行。"""
    from conftest import make_tenant_owner_headers
    from test_outbound_keys import _make_member_headers

    owner, tid = make_tenant_owner_headers(db_session, slug="t05-517")
    operator, _ = _make_member_headers(db_session, tid, "operator", "t05-op-517")
    _seed_results(db_session, tid, "alpha", marker="a-owned")

    raw = _issue_outbound_key(db_client, operator)
    assert _pull(db_client, "alpha", raw).status_code == 200  # 吊销前能拉

    keys = db_client.get("/api/v1/outbound/keys", headers=operator).json()["data"]
    revoked = db_client.delete(f"/api/v1/outbound/keys/{keys[0]['id']}", headers=owner)
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["data"]["status"] == "revoked"

    again = _pull(db_client, "alpha", raw)
    assert again.status_code == 401
    assert again.json().get("items") in (None, [])


# ---------------------------------------------------------------------------
# GWT-92.3 / 92.6：签发事件
# ---------------------------------------------------------------------------

def test_gwt_92_3_issue_event_has_tenant_no_plaintext(db_client, db_session, db_engine):
    """92.3：签发成功上报 outbound_key_issued（含 tenant_id/actor），全行无明文。"""
    from conftest import make_tenant_owner_headers
    from test_outbound_keys import _make_member_headers

    owner, tid = make_tenant_owner_headers(db_session, slug="t05-923")
    operator, operator_uid = _make_member_headers(db_session, tid, "operator", "t05-op-923")

    issued = db_client.post("/api/v1/outbound/keys", headers=operator, json={})
    assert issued.status_code == 201, issued.text
    raw = issued.json()["data"]["plaintext_key"]
    key_id = issued.json()["data"]["id"]

    events = _events_of(db_session, "outbound_key_issued")
    assert len(events) == 1
    ev = events[0]
    assert ev.tenant_id == tid
    assert ev.actor_user_id == operator_uid
    assert ev.props == {"key_id": key_id}
    dump = json.dumps({"props": ev.props}, ensure_ascii=False, default=str)
    assert raw not in dump
    assert "plaintext" not in dump
    assert raw[:10] not in dump  # 连前缀片段也不进事件


def test_gwt_92_6_event_failure_does_not_block_issue(db_client, db_session, db_engine, monkeypatch):
    """92.6：事件上报失败 → 钥匙仍签发成功（主路径不受影响）。"""
    from conftest import make_tenant_owner_headers
    from test_outbound_keys import _make_member_headers
    from platform_core.models.outbound_key import OutboundKey

    async def _boom(*_a, **_k):
        raise RuntimeError("events down")

    monkeypatch.setattr("backend.services.product_event_service._persist_event", _boom)

    owner, tid = make_tenant_owner_headers(db_session, slug="t05-926")
    operator, _ = _make_member_headers(db_session, tid, "operator", "t05-op-926")

    issued = db_client.post("/api/v1/outbound/keys", headers=operator, json={})
    assert issued.status_code == 201, issued.text

    async def _go():
        async with db_session() as s:
            return list((await s.execute(
                select(OutboundKey).where(OutboundKey.tenant_id == tid)
            )).scalars().all())

    rows = asyncio.run(_go())
    assert len(rows) == 1  # 钥匙已签发，事件失败不回滚


# ---------------------------------------------------------------------------
# GWT-51.10：出站钥匙不得出现在任何网关鉴权路径
# ---------------------------------------------------------------------------

def test_gwt_51_10_outbound_key_rejected_on_gateway_paths_no_usage_side_effect(
    db_client, db_session, db_engine, monkeypatch,
):
    """51.10 / X-KEY：ok- 钥匙打网关路径 → 非 2xx、非套餐句、渠道组用量不变。

    归属说明（票面）：网关侧拒绝属 T-08/T-09 域；本测钉住出站域侧不变量——
    (1) 网关 chat 适配叶鉴权头只可能是 master（ok- 钥匙从不被携带/注册）；
    (2) 网关管理既有路由对 Bearer ok- 一律非 2xx（JWT 面，非套餐句）；
    (3) 尝试前后渠道组用量（used_tokens）相对基线不变。
    """
    from config import settings

    from backend.services.llm_gateway.chat import chat_completions
    from conftest import make_tenant_owner_headers
    from test_outbound_keys import _make_member_headers
    from test_relay_token_gateway import _create_group, _stub_generate

    owner, tid = make_tenant_owner_headers(db_session, slug="t05-510")
    operator, _ = _make_member_headers(db_session, tid, "operator", "t05-op-510")
    raw = _issue_outbound_key(db_client, operator)
    assert raw.startswith("ok-")

    # 基线：本企业一把渠道组令牌（用量 0）
    _stub_generate(
        monkeypatch, reply={"key": "sk-relay-baseline-x", "token_id": "tok-510"},
    )
    gid = _create_group(db_client, owner, db_session, tid)
    created = db_client.post(
        "/api/v1/relay/tokens", headers=owner,
        json={"group_id": gid, "name": "ci", "quota_tokens": 1000},
    )
    assert created.status_code == 201, created.text
    baseline = _relay_usage_of(db_session, tid)
    assert baseline and baseline[0][1] == 0

    # (1) 网关 chat 适配叶：鉴权头只携带 master；网关对未知钥匙 401（非 2xx 上抛）
    original_master = str(settings.get("LITELLM.MASTER_KEY", "") or "")
    settings.set("LITELLM.MASTER_KEY", "sk-master-marker")
    captured: dict = {}

    def _gw_handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            401, json={"error": {"message": "Invalid authentication token",
                                  "type": "auth_error"}},
        )

    try:
        with pytest.raises(httpx.HTTPStatusError) as excinfo:
            asyncio.run(chat_completions(
                {"model": "gpt-4o", "messages": []},
                transport=httpx.MockTransport(_gw_handler),
            ))
    finally:
        settings.set("LITELLM.MASTER_KEY", original_master)
    assert excinfo.value.response.status_code == 401  # 非 2xx：网关不认
    assert "QUOTA" not in excinfo.value.response.text  # 不是套餐超限句
    assert captured["authorization"] == "Bearer sk-master-marker"
    assert raw not in (captured.get("authorization") or "")  # ok- 不在网关鉴权头

    # (2) 网关管理既有路由：Bearer ok- → 非 2xx，可见处无 QUOTA_EXCEEDED
    listed = db_client.get("/api/v1/relay/tokens", headers={"Authorization": f"Bearer {raw}"})
    assert listed.status_code not in (200, 201)
    assert "QUOTA_EXCEEDED" not in listed.text

    # (3) 渠道组用量相对基线不变
    assert _relay_usage_of(db_session, tid) == baseline
