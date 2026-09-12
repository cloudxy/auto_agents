"""T-09（FR-60 / FR-92，ADR-0019）：令牌打网关用量走；吊销后再打拒绝。

GWT-60.3（QA-21/QA-05 夹具口径，contract §7.4）：夹具网关是 **真实 HTTP 服务**
（等价桩），签发令牌对 Base URL 的 chat 路径发起真实请求，网关认证通过并返回
真实响应体——裸 httpx 200 不算。Then 三同时：非无效平台钥匙、非套餐超限、
用量 0→≥1（本地 used_tokens 缓存列经网关 key info/spend HTTP 回填）。

夹具按 v1.100.0 OpenAPI/源码实读钉端点（T-08 §0 + 本票核对）：
- GET /key/info?key=<sha256(明文)>（litellm token 即 sha256 hexdigest，与本地
  key_hash 同值——明文永不出库）
- GET /spend/logs/v2?key_alias=<alias>（分页；rows 含 total_tokens）
"""
import asyncio
import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import httpx
from sqlalchemy import select

from platform_core.models.product_event import ProductEvent
from platform_core.models.relay import RelayToken
from platform_core.models.tenant import Tenant

# spec 冻结句 / 冻结码（§7.1）
GATEWAY_UNREACHABLE_SENTENCE = "平台 LLM 网关不可达"
_QUOTA_WORDS = ("QUOTA", "套餐", "已达配额上限")

_CHAT_TOKENS_PER_CALL = 27  # 夹具 chat 一次的 total_tokens（≥1 即满足 60.3 单位口径）


class _FixtureGateway:
    """QA-21「夹具网关可达」的等价桩：真实 HTTP 服务 + 真实鉴权 + 真实响应体。

    管理面（/key/*、/spend/*）按 v1.100.0 实测 schema 应答；chat 面
    （/v1/chat/completions）按 Bearer 明文鉴权：未签发 / 已作废 / 非 sk- 虚拟
    Key（如出站 ok- 钥匙）一律 401，绝不计入用量。
    """

    def __init__(self) -> None:
        self.base_url = ""
        self.keys: dict[str, dict] = {}       # alias -> row
        self.by_plain: dict[str, str] = {}    # 明文 -> alias
        self.by_hash: dict[str, str] = {}     # sha256(明文) -> alias
        self.logs: list[dict] = []            # 每 chat 调用一条 spend log 行
        self.admin_hits: list[str] = []       # 管理面被 backend 打过的路径（QA-08 断言用）
        self.chat_calls: list[dict] = []      # chat 鉴权面审计
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # -- 生命周期 ---------------------------------------------------------
    def start(self) -> "_FixtureGateway":
        gw = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # 静默访问日志
                pass

            def _reply(self, status: int, payload: dict) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _read_json(self) -> dict:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    return json.loads(raw or b"{}")
                except json.JSONDecodeError:
                    return {}

            def do_POST(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                payload = self._read_json()
                if path == "/key/generate":
                    with gw._lock:
                        gw.admin_hits.append(path)
                        alias = str(payload.get("key_alias") or "")
                        plaintext = f"sk-fixture-{uuid.uuid4().hex}"
                        row = {
                            "alias": alias, "plaintext": plaintext,
                            "key_hash": hashlib.sha256(plaintext.encode()).hexdigest(),
                            "revoked": False, "tokens": 0, "spend": 0.0,
                            "last_active": None,
                            "metadata": payload.get("metadata") or {},
                        }
                        gw.keys[alias] = row
                        gw.by_plain[plaintext] = alias
                        gw.by_hash[row["key_hash"]] = alias
                    self._reply(200, {"key": plaintext, "token_id": uuid.uuid4().hex[:12], "expires": None})
                    return
                if path == "/key/delete":
                    with gw._lock:
                        gw.admin_hits.append(path)
                        for alias in payload.get("key_aliases") or []:
                            if alias in gw.keys:
                                gw.keys[alias]["revoked"] = True
                    self._reply(200, {"deleted_keys": [], "key_aliases": {}})
                    return
                if path == "/v1/chat/completions":
                    auth = self.headers.get("Authorization") or ""
                    token = auth[7:].strip() if auth.startswith("Bearer ") else ""
                    with gw._lock:
                        gw.chat_calls.append({"token": token, "body": payload})
                        alias = gw.by_plain.get(token)
                        row = gw.keys.get(alias) if alias else None
                        if row is None or row["revoked"]:
                            # 网关侧最小前缀/登记判断：出站 ok- 钥匙等非虚拟 Key 一律拒绝
                            self._reply(401, {"error": {
                                "message": "Invalid proxy server token used",
                                "type": "auth_error", "param": None, "code": "401",
                            }})
                            return
                        row["tokens"] += _CHAT_TOKENS_PER_CALL
                        row["spend"] += 0.0004
                        row["last_active"] = datetime.now(timezone.utc).isoformat()
                        gw.logs.append({
                            "request_id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                            "api_key": row["key_hash"], "key_alias": alias,
                            "total_tokens": _CHAT_TOKENS_PER_CALL,
                            "spend": 0.0004,
                        })
                    self._reply(200, {
                        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                        "object": "chat.completion", "created": int(datetime.now(timezone.utc).timestamp()),
                        "model": payload.get("model") or "gpt-4o",
                        "choices": [{
                            "index": 0,
                            "message": {"role": "assistant", "content": "pong"},
                            "finish_reason": "stop",
                        }],
                        "usage": {
                            "prompt_tokens": 11, "completion_tokens": _CHAT_TOKENS_PER_CALL - 11,
                            "total_tokens": _CHAT_TOKENS_PER_CALL,
                        },
                    })
                    return
                self._reply(404, {"error": {"message": f"no route {path}"}})

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                path, query = parsed.path, parse_qs(parsed.query)
                if path == "/key/info":
                    with gw._lock:
                        gw.admin_hits.append(path)
                        key = (query.get("key") or [""])[0]
                        alias = gw.by_hash.get(key)
                        row = gw.keys.get(alias) if alias else None
                        if row is None:
                            self._reply(404, {"error": {"message": "Key not found in database"}})
                            return
                        info = {
                            "key_alias": row["alias"], "spend": row["spend"],
                            "last_active": row["last_active"], "models": [],
                            "metadata": row["metadata"], "blocked": None,
                            "expires": None,
                        }
                    self._reply(200, {"key": key, "token_id": None, "expires": None, "info": info})
                    return
                if path == "/spend/logs/v2":
                    with gw._lock:
                        gw.admin_hits.append(path)
                        alias = (query.get("key_alias") or [""])[0]
                        page = int((query.get("page") or ["1"])[0])
                        page_size = int((query.get("page_size") or ["100"])[0])
                        rows = [dict(r) for r in gw.logs if r["key_alias"] == alias]
                    total = len(rows)
                    start = (page - 1) * page_size
                    page_rows = rows[start:start + page_size]
                    self._reply(200, {
                        "data": page_rows, "total": total, "page": page,
                        "page_size": page_size,
                        "total_pages": (total + page_size - 1) // page_size,
                        "total_is_capped": False,
                    })
                    return
                self._reply(404, {"error": {"message": f"no route {path}"}})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.base_url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def close(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    def chat(self, token: str, *, model: str = "gpt-4o") -> httpx.Response:
        """租户客户端按页上用法对 Base URL 直打 chat（真实 HTTP 请求）。"""
        return httpx.post(
            f"{self.base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {token}"},
            json={"model": model, "messages": [{"role": "user", "content": "ping"}]},
            timeout=10.0, trust_env=False,
        )

    def alias_of(self, plaintext: str) -> str:
        return self.by_plain[plaintext]


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


def _create_group(db_client, owner) -> int:
    created = db_client.post(
        "/api/v1/relay/groups", headers=owner,
        json={"name": "vip", "rpm_limit": 60, "tpm_limit": 10000, "models": ["gpt-4o"]},
    )
    assert created.status_code == 201, created.text
    return created.json()["data"]["id"]


def _issue(db_client, owner, gid: int) -> tuple[int, str]:
    resp = db_client.post(
        "/api/v1/relay/tokens", headers=owner,
        json={"group_id": gid, "name": "ci", "quota_tokens": 1000},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    return int(data["id"]), str(data["plaintext_key"])


def _token_row(db_session, tid: int, token_id: int) -> RelayToken:
    async def _go():
        async with db_session() as s:
            return await s.get(RelayToken, token_id)

    row = asyncio.run(_go())
    assert row is not None and int(row.tenant_id) == tid
    return row


def _relay_events(db_session, tid: int) -> list[dict]:
    async def _go():
        async with db_session() as s:
            rows = (await s.execute(
                select(ProductEvent).where(
                    ProductEvent.event_name == "relay_token_call_succeeded",
                    ProductEvent.tenant_id == tid,
                ).order_by(ProductEvent.id.asc())
            )).scalars().all()
            return [r.props or {} for r in rows]

    return asyncio.run(_go())


def _tenant_quota(db_session, tid: int) -> dict | None:
    async def _go():
        async with db_session() as s:
            row = await s.get(Tenant, tid)
            return dict(row.quota) if row and row.quota else None

    return asyncio.run(_go())


# ---------------------------------------------------------------------------
# GWT-60.3 + GWT-92.4：夹具网关可达 → 真实 chat → 用量 0→≥1 → 事件
# ---------------------------------------------------------------------------

def test_gwt_60_3_chat_authed_usage_moves_and_event(
    db_client, db_session, db_engine, monkeypatch,
):
    from conftest import make_tenant_owner_headers

    gw = _FixtureGateway().start()
    monkeypatch.setattr(
        "backend.services.llm_gateway._settings._base_url", lambda: gw.base_url,
    )
    try:
        owner, tid = make_tenant_owner_headers(db_session, slug="t09-603")
        gid = _create_group(db_client, owner)
        token_id, plaintext = _issue(db_client, owner, gid)

        # Given：该令牌用量为 0（签发即 0）
        row = _token_row(db_session, tid, token_id)
        assert int(row.used_tokens or 0) == 0

        # When：负责人按页上用法对 Base URL 发一条合法请求（真实 HTTP、真实鉴权）
        chat = gw.chat(plaintext)
        assert chat.status_code == 200, chat.text
        body = chat.json()
        # QA-05：网关认证通过并返回真实响应体——裸 200 不算
        assert body["object"] == "chat.completion"
        assert body["choices"][0]["message"]["content"]
        assert int(body["usage"]["total_tokens"]) >= 1

        # Then 三同时：用量 0→≥1（详情=回写触发点，经真实 /key/info + /spend/logs/v2）
        detail = db_client.get(f"/api/v1/relay/tokens/{token_id}", headers=owner)
        assert detail.status_code == 200, detail.text
        env = detail.json()
        data = env["data"]
        assert int(data["used_tokens"]) >= 1
        assert data["plaintext_key"] is None  # 60.11 面：再进页不见明文
        assert "QUOTA" not in env["code"]
        assert not any(w in env["message"] for w in _QUOTA_WORDS)

        row = _token_row(db_session, tid, token_id)
        assert int(row.used_tokens) >= 1
        assert row.spend_synced_at is not None
        assert row.last_used_at is not None

        # GWT-92.4：0→≥1 上报 relay_token_call_succeeded（tenant_id、无明文）
        events = _relay_events(db_session, tid)
        assert len(events) == 1
        assert events[0].get("token_id") == token_id
        assert plaintext not in json.dumps(events[0], ensure_ascii=False)

        # 重复观察（已 ≥1，无新 0→≥1 跃迁）不重复上报
        again = db_client.get(f"/api/v1/relay/tokens/{token_id}", headers=owner)
        assert again.status_code == 200
        assert len(_relay_events(db_session, tid)) == 1

        # 显式刷新（批量触发点）走同一回写；空跃迁不再上报
        refreshed = db_client.post("/api/v1/relay/tokens/refresh-usage", headers=owner)
        assert refreshed.status_code == 200, refreshed.text
        rows = refreshed.json()["data"]
        assert any(int(t["used_tokens"]) >= 1 for t in rows)
        assert len(_relay_events(db_session, tid)) == 1
    finally:
        gw.close()


# ---------------------------------------------------------------------------
# GWT-60.2：用量 ≥1 只读成员也可见（数字来自本地缓存列；列表禁打网关）
# ---------------------------------------------------------------------------

def test_gwt_60_2_viewer_sees_usage_list_reads_local_column_only(
    db_client, db_session, db_engine, monkeypatch,
):
    from conftest import make_tenant_owner_headers

    gw = _FixtureGateway().start()
    monkeypatch.setattr(
        "backend.services.llm_gateway._settings._base_url", lambda: gw.base_url,
    )
    try:
        owner, tid = make_tenant_owner_headers(db_session, slug="t09-602")
        viewer = _make_member_headers(db_session, tid, "viewer", "t09-viewer-602")
        gid = _create_group(db_client, owner)
        token_id, plaintext = _issue(db_client, owner, gid)
        assert gw.chat(plaintext).status_code == 200

        # 详情触发回写（本地列落 ≥1）
        detail = db_client.get(f"/api/v1/relay/tokens/{token_id}", headers=owner)
        assert detail.status_code == 200
        assert int(detail.json()["data"]["used_tokens"]) >= 1

        # 只读成员经列表看见同一数字（GWT-60.2）
        with gw._lock:
            admin_hits_before = list(gw.admin_hits)
        listed = db_client.get("/api/v1/relay/tokens", headers=viewer)
        assert listed.status_code == 200, listed.text
        row = next(t for t in listed.json()["data"] if t["id"] == token_id)
        assert int(row["used_tokens"]) >= 1

        # QA-08：list_tokens 列表读路径禁止每行打网关
        with gw._lock:
            assert gw.admin_hits == admin_hits_before
    finally:
        gw.close()


# ---------------------------------------------------------------------------
# QA-20：吊销后再打 Base URL → 拒绝（网关作废 + 本地 revoked 双闸）
# ---------------------------------------------------------------------------

def test_qa_20_revoked_token_rejected_on_chat(
    db_client, db_session, db_engine, monkeypatch,
):
    from conftest import make_tenant_owner_headers

    gw = _FixtureGateway().start()
    monkeypatch.setattr(
        "backend.services.llm_gateway._settings._base_url", lambda: gw.base_url,
    )
    try:
        owner, tid = make_tenant_owner_headers(db_session, slug="t09-qa20")
        gid = _create_group(db_client, owner)
        token_id, plaintext = _issue(db_client, owner, gid)
        assert gw.chat(plaintext).status_code == 200

        revoked = db_client.delete(f"/api/v1/relay/tokens/{token_id}", headers=owner)
        assert revoked.status_code == 200, revoked.text

        # 吊销后再打 Base URL → 网关拒绝（不是 60.3 成功）
        rejected = gw.chat(plaintext)
        assert rejected.status_code == 401, rejected.text

        # 本地双闸：status=revoked；详情不同步已吊销行（管理面零新调用）
        detail = db_client.get(f"/api/v1/relay/tokens/{token_id}", headers=owner)
        assert detail.status_code == 200
        assert detail.json()["data"]["status"] == "revoked"
        with gw._lock:
            admin_hits = list(gw.admin_hits)
        assert db_client.get(f"/api/v1/relay/tokens/{token_id}", headers=owner).status_code == 200
        with gw._lock:
            assert gw.admin_hits == admin_hits
    finally:
        gw.close()


# ---------------------------------------------------------------------------
# GWT-60.5：网关不可达 → 「平台 LLM 网关不可达」句族；非套餐句；用量不显示已用完
# ---------------------------------------------------------------------------

def test_gwt_60_5_gateway_unreachable_same_then_not_quota(
    db_client, db_session, db_engine, monkeypatch,
):
    from conftest import make_tenant_owner_headers

    gw = _FixtureGateway().start()
    monkeypatch.setattr(
        "backend.services.llm_gateway._settings._base_url", lambda: gw.base_url,
    )
    try:
        owner, tid = make_tenant_owner_headers(db_session, slug="t09-605")
        gid = _create_group(db_client, owner)
        token_id, plaintext = _issue(db_client, owner, gid)
        assert gw.chat(plaintext).status_code == 200
        seeded = db_client.get(f"/api/v1/relay/tokens/{token_id}", headers=owner)
        seeded_used = int(seeded.json()["data"]["used_tokens"])
        assert seeded_used >= 1

        # 网关不可达（指向确定关闭的本地端口）
        monkeypatch.setattr(
            "backend.services.llm_gateway._settings._base_url", lambda: "http://127.0.0.1:1",
        )

        # 详情：可见失败句族（信封 message），本地缓存数字保持（不是「已用完」）
        detail = db_client.get(f"/api/v1/relay/tokens/{token_id}", headers=owner)
        assert detail.status_code == 200, detail.text
        env = detail.json()
        assert int(env["data"]["used_tokens"]) == seeded_used
        assert GATEWAY_UNREACHABLE_SENTENCE in env["message"]
        assert "QUOTA" not in env["code"]
        assert not any(w in env["message"] for w in _QUOTA_WORDS)

        # 显式刷新：失败可见（502 + LLM_GATEWAY_UNREACHABLE 句族），非套餐句
        refresh = db_client.post("/api/v1/relay/tokens/refresh-usage", headers=owner)
        assert refresh.status_code == 502, refresh.text
        renv = refresh.json()
        assert renv["code"] == "LLM_GATEWAY_UNREACHABLE"
        assert GATEWAY_UNREACHABLE_SENTENCE in renv["message"]
        assert "QUOTA" not in renv["code"]
        assert not any(w in renv["message"] for w in _QUOTA_WORDS)

        # 失败不改本地缓存（用量不因不可达被清零/顶满）
        row = _token_row(db_session, tid, token_id)
        assert int(row.used_tokens) == seeded_used
    finally:
        gw.close()


# ---------------------------------------------------------------------------
# GWT-60.10：A 调用成功后 B 用量/配额基线不变（按 tenant_id 隔离）
# ---------------------------------------------------------------------------

def test_gwt_60_10_tenant_a_call_does_not_move_tenant_b(
    db_client, db_session, db_engine, monkeypatch,
):
    from conftest import make_tenant_owner_headers

    gw = _FixtureGateway().start()
    monkeypatch.setattr(
        "backend.services.llm_gateway._settings._base_url", lambda: gw.base_url,
    )
    try:
        owner_a, tid_a = make_tenant_owner_headers(db_session, slug="t09-a")
        owner_b, tid_b = make_tenant_owner_headers(db_session, slug="t09-b")
        gid_a = _create_group(db_client, owner_a)
        gid_b = _create_group(db_client, owner_b)
        token_a, plain_a = _issue(db_client, owner_a, gid_a)
        token_b, plain_b = _issue(db_client, owner_b, gid_b)
        quota_b_before = _tenant_quota(db_session, tid_b)

        # A 完成一次 60.3 用户可观察成功调用
        assert gw.chat(plain_a).status_code == 200
        detail_a = db_client.get(f"/api/v1/relay/tokens/{token_a}", headers=owner_a)
        assert int(detail_a.json()["data"]["used_tokens"]) >= 1

        # B：用量与配额相对基线不变
        detail_b = db_client.get(f"/api/v1/relay/tokens/{token_b}", headers=owner_b)
        assert detail_b.status_code == 200
        assert int(detail_b.json()["data"]["used_tokens"]) == 0
        row_b = _token_row(db_session, tid_b, token_b)
        assert int(row_b.used_tokens) == 0
        assert _tenant_quota(db_session, tid_b) == quota_b_before

        # B 的令牌从未被 chat（plain_b 未使用）
        with gw._lock:
            used_plains = [c["token"] for c in gw.chat_calls]
        assert plain_b not in used_plains

        # 事件只属于 A
        assert len(_relay_events(db_session, tid_a)) == 1
        assert _relay_events(db_session, tid_b) == []
    finally:
        gw.close()


# ---------------------------------------------------------------------------
# GWT-60.6：租户改全局熔断/探针阈值/渠道窗口 → 无入口（既有守卫核对）
# ---------------------------------------------------------------------------

def test_gwt_60_6_tenant_no_entry_to_platform_fuse_probe_window(
    db_client, db_session, db_engine, monkeypatch,
):
    from unittest.mock import AsyncMock

    from conftest import make_tenant_owner_headers

    owner, _tid = make_tenant_owner_headers(db_session, slug="t09-606")

    # 直打平台数据面 = 页面不存在同形（GWT-07.3 既有守卫：require_platform_admin_or_404）
    for path in ("/api/v1/newapi/overview", "/api/v1/newapi/channels"):
        resp = db_client.get(path, headers=owner)
        assert resp.status_code == 404, f"{path} -> {resp.status_code}"

    # 改渠道窗口/冷却（熔断面）→ 既有写守卫拒绝（GWT-70.3 403 + 越权记录），窗口不变
    spy = AsyncMock()
    monkeypatch.setattr(
        "backend.services.channel_config_service.ChannelConfigService.set_config", spy,
    )
    resp = db_client.put("/api/v1/newapi/channels/999999/config", headers=owner, json={
        "limit_quota": 10, "window_hours": 24, "cooldown_seconds": 60,
    })
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "FORBIDDEN"
    spy.assert_not_awaited()

    monkeypatch.setattr(
        "backend.services.channel_config_service.ChannelConfigService.set_config_ref", spy,
    )
    resp = db_client.put("/api/v1/newapi/models/some-ref/config", headers=owner, json={
        "limit_quota": 10, "window_hours": 24, "cooldown_seconds": 60,
    })
    assert resp.status_code == 403, resp.text
    spy.assert_not_awaited()


# ---------------------------------------------------------------------------
# GWT-60.8：跨企业吊销/看详情 → 404 同形；A 的令牌不变
# ---------------------------------------------------------------------------

def test_gwt_60_8_cross_tenant_revoke_and_detail_404(
    db_client, db_session, db_engine, monkeypatch,
):
    from conftest import make_tenant_owner_headers

    gw = _FixtureGateway().start()
    monkeypatch.setattr(
        "backend.services.llm_gateway._settings._base_url", lambda: gw.base_url,
    )
    try:
        owner_a, tid_a = make_tenant_owner_headers(db_session, slug="t09-xa")
        owner_b, _tid_b = make_tenant_owner_headers(db_session, slug="t09-xb")
        gid = _create_group(db_client, owner_a)
        token_a, _plain = _issue(db_client, owner_a, gid)

        stolen_revoke = db_client.delete(f"/api/v1/relay/tokens/{token_a}", headers=owner_b)
        assert stolen_revoke.status_code == 404, stolen_revoke.text

        stolen_detail = db_client.get(f"/api/v1/relay/tokens/{token_a}", headers=owner_b)
        assert stolen_detail.status_code == 404, stolen_detail.text

        row = _token_row(db_session, tid_a, token_a)
        assert row.revoked_at is None
    finally:
        gw.close()


# ---------------------------------------------------------------------------
# 出站钥匙打 chat → 拒绝（与 T-05 GWT-51.10 同一断言面；网关侧最小登记判断）
# ---------------------------------------------------------------------------

def test_outbound_style_key_rejected_on_chat(db_client, db_session, db_engine, monkeypatch):
    from conftest import make_tenant_owner_headers

    gw = _FixtureGateway().start()
    monkeypatch.setattr(
        "backend.services.llm_gateway._settings._base_url", lambda: gw.base_url,
    )
    try:
        owner, tid = make_tenant_owner_headers(db_session, slug="t09-outb")
        gid = _create_group(db_client, owner)
        _issue(db_client, owner, gid)  # 渠道组令牌在册（基线对照）

        # 出站钥匙（ok- 前缀）不是网关虚拟 Key → chat 拒绝
        rejected = gw.chat("ok-outbound-key-1")
        assert rejected.status_code == 401, rejected.text

        # 渠道组用量基线不变（零 spend log、零 60.3 语义成功）
        with gw._lock:
            assert gw.logs == []
    finally:
        gw.close()
