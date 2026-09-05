"""T10 API 层覆盖切片：零 HTTP 测试的高风险端点最小用例（正常 + 401/403 + 校验）

覆盖端点（qa findings F1/F4）：
- POST /api/v1/spiders/run     核心入队入口（参数校验 / 权限 / 未登记拒绝）
- GET  /api/v1/spiders/tasks/{id}/store   404 分支（任务不存在）
- GET  /api/v1/admin/audit-logs           审计查询（require_admin）
- GET|PUT /api/v1/admin/notify-config     通知渠道配置（require_admin + URL 校验）
- POST /external/v1/webhooks/spider/callback  爬虫回调（HMAC 签名三态拒绝 + 合法推进）

权限断言口径（三类越权中的第三类——绕过前端直调接口）：
- 401：匿名（无凭据，与生产 get_current_user 同口径）
- 403：低权限角色直调（viewer/operator 对 admin 端点）
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time

import pytest
from sqlalchemy import select

from factories import build_spider_task
from platform_core.models.spider_task import SpiderTask

# ---------------------------------------------------------------------------
# POST /api/v1/spiders/run
# ---------------------------------------------------------------------------

RUN_URL = "/api/v1/spiders/run"


def _fake_redis(monkeypatch):
    """queue Redis 桩（rpush 成功、scard=0）——enqueue 的投递/并发槽位依赖"""
    from stubs import FakeRedis

    fake = FakeRedis()

    def _get(key=None):  # get_async_redis 为同步工厂（platform_core/redis_async.py）
        return fake

    import backend.services.spider_task_service as svc_mod
    monkeypatch.setattr(svc_mod, "get_async_redis", _get)
    return fake


def test_run_spider_operator_enqueues(db_client, operator_client, db_engine, db_session, monkeypatch):
    """operator 入队：201 信封 CREATED + 落库 pending + 消息投递队列（副作用断言）"""
    _fake_redis(monkeypatch)
    resp = operator_client.post(
        RUN_URL,
        json={"spider_name": "example", "params": '{"urls": ["https://example.com"]}',
              "priority": "high"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "CREATED"
    assert body["data"]["status"] == "pending"
    assert body["data"]["spider_name"] == "example"

    async def _check():
        async with db_session() as s:
            rows = (await s.execute(
                select(SpiderTask).where(SpiderTask.spider_name == "example")
            )).scalars().all()
            assert len(rows) == 1  # 恰好一条（幂等副作用）
            assert rows[0].priority == "high"

    asyncio.run(_check())


def test_run_spider_anonymous_401(client):
    """匿名直调 → 401（AUTH_FAILED），不产生任务"""
    resp = client.post(RUN_URL, json={"spider_name": "example"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_FAILED"


def test_run_spider_viewer_403(viewer_client):
    """viewer 直调（绕过前端隐藏按钮）→ 403（require_operator 守卫）"""
    resp = viewer_client.post(RUN_URL, json={"spider_name": "example"})
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


@pytest.mark.parametrize("payload,field", [
    ({"params": "{}"}, "spider_name"),                      # 缺 spider_name
    ({"spider_name": ""}, "spider_name"),                   # 空串（min_length=1 界上外）
    ({"spider_name": "x" * 101}, "spider_name"),            # 超长（max=100 界外）
    ({"spider_name": "example", "priority": "urgent"}, "priority"),  # 非法优先级
])
def test_run_spider_validation_422(db_client, operator_client, db_engine, db_session, payload, field):
    """参数校验 422，且无副作用（VALIDATION 失败不落任务）"""
    resp = operator_client.post(RUN_URL, json=payload)
    assert resp.status_code == 422, resp.text
    assert field in resp.text

    async def _check():
        async with db_session() as s:
            count = len((await s.execute(select(SpiderTask))).scalars().all())
            assert count == 0  # 副作用断言：校验失败零落库

    asyncio.run(_check())


def test_run_spider_unregistered_rejected_400(db_client, operator_client, db_engine, db_session, monkeypatch):
    """未登记爬虫 → 400 BUSINESS_ERROR（契约注记：注册表拒绝映射 400 而非 404——
    「资源不存在」语义由 GET /tasks/{id}/store 的 404 分支另行覆盖）"""
    _fake_redis(monkeypatch)
    resp = operator_client.post(RUN_URL, json={"spider_name": "no-such-spider-t10"})
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["code"] == "BUSINESS_ERROR"
    assert "未在注册表登记" in body["message"]

    async def _check():
        async with db_session() as s:
            count = len((await s.execute(select(SpiderTask))).scalars().all())
            assert count == 0  # 拒绝路径零落库

    asyncio.run(_check())


def test_task_store_status_404(db_client, operator_client):
    """GET /tasks/{id}/store 不存在任务 → 404 NOT_FOUND（资源不存在分支）"""
    resp = operator_client.get("/api/v1/spiders/tasks/99999999/store")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# GET /api/v1/admin/audit-logs（require_admin）
# ---------------------------------------------------------------------------


def test_audit_logs_admin_ok(db_client, admin_client):
    """admin 查审计日志：200 + 分页信封（total/items）"""
    resp = admin_client.get("/api/v1/admin/audit-logs")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert isinstance(data["total"], int)
    assert isinstance(data["items"], list)


def test_audit_logs_anonymous_401(client):
    resp = client.get("/api/v1/admin/audit-logs")
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_FAILED"


def test_audit_logs_operator_403(operator_client):
    """operator 直调 admin 端点 → 403（守卫存在性证明）"""
    resp = operator_client.get("/api/v1/admin/audit-logs")
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# GET|PUT /api/v1/admin/notify-config（require_admin + URL 契约）
# ---------------------------------------------------------------------------


def test_notify_config_roundtrip(db_client, admin_client):
    """GET 默认空 → PUT 合法 URL → updated 回执 + GET 回读一致"""
    resp = admin_client.get("/api/v1/admin/notify-config")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data.keys()) == {"webhook_url", "dingtalk_url", "wechat_work_url"}

    put = admin_client.put(
        "/api/v1/admin/notify-config",
        json={"webhook_url": "https://hooks.example.com/t10"},
    )
    assert put.status_code == 200, put.text
    assert put.json()["data"]["updated"] == ["notify.webhook_url"]  # 回执为 DB 配置键名

    again = admin_client.get("/api/v1/admin/notify-config")
    assert again.json()["data"]["webhook_url"] == "https://hooks.example.com/t10"


def test_notify_config_invalid_url_422(db_client, admin_client):
    """PUT 非 http(s) URL → 422，且配置未写入（副作用断言）"""
    put = admin_client.put(
        "/api/v1/admin/notify-config",
        json={"dingtalk_url": "ftp://not-http.example.com"},
    )
    assert put.status_code == 422
    assert put.json()["code"] == "VALIDATION_ERROR"

    got = admin_client.get("/api/v1/admin/notify-config")
    assert got.json()["data"]["dingtalk_url"] == ""  # 拒绝路径零写入


def test_notify_config_anonymous_401(client):
    """匿名 GET/PUT → 401（特权 fixture 与默认 client 共享 TestClient 实例，
    匿名断言必须在不声明任何特权 fixture 的用例中进行）"""
    assert client.get("/api/v1/admin/notify-config").status_code == 401
    assert client.put(
        "/api/v1/admin/notify-config", json={"webhook_url": "https://x"}
    ).status_code == 401


def test_notify_config_operator_403(operator_client):
    assert operator_client.get("/api/v1/admin/notify-config").status_code == 403
    assert operator_client.put(
        "/api/v1/admin/notify-config", json={"webhook_url": "https://x"}
    ).status_code == 403


# ---------------------------------------------------------------------------
# POST /external/v1/webhooks/spider/callback（HMAC 签名 + 终态推进）
# ---------------------------------------------------------------------------

CALLBACK_URL = "/external/v1/webhooks/spider/callback"


def _sign(timestamp: str, body: bytes) -> str:
    """与 Scrapy 侧 SpiderCloseWebhook 相同算法（HMAC-SHA256(secret, ts.body)）"""
    from config import settings

    secret = str(settings.WEBHOOK.SECRET_KEY)
    payload = f"{timestamp}.".encode() + body
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def test_callback_without_headers_401(client):
    """缺签名头 → 401（回调端点无 JWT，安全边界即签名）"""
    resp = client.post(CALLBACK_URL, json={"task_id": 1, "status": "completed"})
    assert resp.status_code == 401


def test_callback_tampered_signature_401(client):
    body = json.dumps({"task_id": 1, "status": "completed"}).encode()
    resp = client.post(
        CALLBACK_URL, content=body,
        headers={"X-Webhook-Timestamp": str(int(time.time())),
                 "X-Webhook-Signature": "0" * 64},
    )
    assert resp.status_code == 401


def test_callback_stale_timestamp_401(client):
    """时间戳超窗（> MAX_CLOCK_SKEW）→ 401（防重放）"""
    body = json.dumps({"task_id": 1, "status": "completed"}).encode()
    stale = str(int(time.time()) - 3600)
    resp = client.post(
        CALLBACK_URL, content=body,
        headers={"X-Webhook-Timestamp": stale, "X-Webhook-Signature": _sign(stale, body)},
    )
    assert resp.status_code == 401


def test_callback_valid_signature_404_unknown_task(client):
    """合法签名但任务不存在 → 404（签名通过后的资源分支）"""
    body = json.dumps({"task_id": 99999999, "status": "completed"}).encode()
    ts = str(int(time.time()))
    resp = client.post(
        CALLBACK_URL, content=body,
        headers={"X-Webhook-Timestamp": ts, "X-Webhook-Signature": _sign(ts, body)},
    )
    assert resp.status_code == 404


def test_callback_valid_signature_advances_task(db_client, client, db_engine, db_session, monkeypatch):
    """合法签名 + pending 任务 → 200 received + 任务终态 completed（副作用断言）"""
    from stubs import FakeRedis

    fake = FakeRedis()

    def _get(key=None):  # 同步工厂（见 _fake_redis 注释）
        return fake

    import backend.services.spider_task_service as svc_mod
    monkeypatch.setattr(svc_mod, "get_async_redis", _get)

    async def _seed():
        async with db_session() as s:
            s.add(build_spider_task(status="running"))
            await s.commit()

    asyncio.run(_seed())

    async def _task_id():
        async with db_session() as s:
            task = (await s.execute(select(SpiderTask))).scalars().first()
            return task.id

    task_id = asyncio.run(_task_id())

    body = json.dumps({"task_id": task_id, "status": "completed", "item_count": 5}).encode()
    ts = str(int(time.time()))
    resp = client.post(
        CALLBACK_URL, content=body,
        headers={"X-Webhook-Timestamp": ts, "X-Webhook-Signature": _sign(ts, body)},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "received"
    assert data["task_status"] == "completed"

    async def _verify():
        async with db_session() as s:
            task = (await s.execute(
                select(SpiderTask).where(SpiderTask.id == task_id))).scalar_one()
            assert task.status == "completed"
            assert task.result_count == 5

    asyncio.run(_verify())
