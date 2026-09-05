"""B1b 零覆盖路由清剿：任务模板 CRUD + 一键运行（爬虫运营配置面）

覆盖路由（backend/app/api/v1/spiders/templates.py，此前零 HTTP 覆盖）：
- GET    /api/v1/spiders/templates               模板列表（require_login）
- POST   /api/v1/spiders/templates               创建（require_operator；名称唯一）
- PATCH  /api/v1/spiders/templates/{id}          更新（require_operator）
- DELETE /api/v1/spiders/templates/{id}          删除（require_operator；软删）
- POST   /api/v1/spiders/templates/{id}/run      从模板入队任务（require_operator）

既有覆盖对照：无 HTTP 层用例（test_saas_models / test_db_fixtures 仅触模型与夹具层）。

断言口径（标准 = TaskTemplate* schema 契约 + Service 行为注释 + 统一异常体系）：
- run 断言三件事：任务落库（pending）/ params·priority 透传 / 队列消息投递
- 观察记录（非缺陷）：create 不校验爬虫注册表（收藏语义），未登记模板在 run 时
  由 enqueue 的注册表校验拒绝（400），fail-at-run 而非 fail-at-create
"""
from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import select

from platform_core.models.spider_task import SpiderTask
from platform_core.models.task_template import TaskTemplate

BASE = "/api/v1/spiders/templates"

TEMPLATE_PAYLOAD = {
    "name": "example-每日采集",
    "spider_name": "example",
    "params": '{"urls": ["https://example.com"]}',
    "priority": "high",
}


def _fake_redis(monkeypatch):
    """queue Redis 桩：enqueue 的并发槽位/投递依赖（scard 缺失走异常放行，见 stubs）"""
    from stubs import FakeRedis

    fake = FakeRedis()

    def _get(key=None):
        return fake

    import backend.services.spider_task_service as svc_mod
    monkeypatch.setattr(svc_mod, "get_async_redis", _get)
    return fake


def _create_template(operator_client, **overrides) -> dict:
    payload = {**TEMPLATE_PAYLOAD, **overrides}
    resp = operator_client.post(BASE, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# GET /templates（require_login）
# ---------------------------------------------------------------------------

def test_list_templates_empty_ok(db_client, viewer_client):
    """viewer 读列表：200 + 空态 []（data 为 list）"""
    resp = viewer_client.get(BASE)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == []


def test_list_templates_anonymous_401(client):
    assert client.get(BASE).status_code == 401
    assert client.get(BASE).json()["code"] == "AUTH_FAILED"


# ---------------------------------------------------------------------------
# POST /templates（require_operator）
# ---------------------------------------------------------------------------

def test_create_template_operator_ok(db_client, operator_client, db_engine, db_session):
    """operator 创建：CREATED + created_by 取操作者用户名 + 落库一行（副作用）"""
    resp = operator_client.post(BASE, json=TEMPLATE_PAYLOAD)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "CREATED"
    data = body["data"]
    assert data["id"] > 0
    assert data["name"] == "example-每日采集"
    assert data["priority"] == "high"
    assert data["created_by"] == "test-operator"  # 审计列由 API 层传入

    async def _check():
        async with db_session() as s:
            rows = (await s.execute(select(TaskTemplate))).scalars().all()
            assert len(rows) == 1
            assert rows[0].spider_name == "example"
            assert rows[0].created_by == "test-operator"

    asyncio.run(_check())


def test_create_template_duplicate_name_400(db_client, operator_client, db_engine, db_session):
    """重名模板 → 400 + 库中仍只有一条（唯一性副作用）"""
    _create_template(operator_client)
    resp = operator_client.post(BASE, json={**TEMPLATE_PAYLOAD, "spider_name": "generic"})
    assert resp.status_code == 400, resp.text
    assert "已存在" in resp.json()["message"]

    async def _check():
        async with db_session() as s:
            assert len((await s.execute(select(TaskTemplate))).scalars().all()) == 1

    asyncio.run(_check())


@pytest.mark.parametrize("payload,field", [
    ({"spider_name": "example"}, "name"),                          # 缺 name
    ({"name": "", "spider_name": "example"}, "name"),              # 空串（min=1 界外）
    ({"name": "x" * 201, "spider_name": "example"}, "name"),       # max=200 界外
    ({"name": "t", "spider_name": "x" * 101}, "spider_name"),      # max=100 界外
    ({"name": "t", "spider_name": "example", "priority": "urgent"}, "priority"),  # 非法枚举
])
def test_create_template_validation_422(db_client, operator_client, payload, field):
    resp = operator_client.post(BASE, json=payload)
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "VALIDATION_ERROR"
    assert field in resp.text


def test_create_template_viewer_403(db_client, viewer_client, db_engine, db_session):
    """viewer 直调（绕过前端隐藏按钮）→ 403 + 零落库"""
    resp = viewer_client.post(BASE, json=TEMPLATE_PAYLOAD)
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"

    async def _check():
        async with db_session() as s:
            assert len((await s.execute(select(TaskTemplate))).scalars().all()) == 0

    asyncio.run(_check())


def test_templates_anonymous_401(client):
    assert client.get(BASE).status_code == 401
    assert client.post(BASE, json=TEMPLATE_PAYLOAD).status_code == 401
    assert client.patch(f"{BASE}/1", json={"name": "t"}).status_code == 401
    assert client.delete(f"{BASE}/1").status_code == 401
    assert client.post(f"{BASE}/1/run").status_code == 401


# ---------------------------------------------------------------------------
# PATCH /templates/{id}（require_operator）
# ---------------------------------------------------------------------------

def test_update_template_ok(db_client, operator_client, db_engine, db_session):
    """局部更新 name/priority → UPDATED + 未提交字段保持 + DB 同步（副作用）"""
    template = _create_template(operator_client)
    resp = operator_client.patch(f"{BASE}/{template['id']}", json={
        "name": "example-改名", "priority": "low",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "UPDATED"
    assert body["data"]["name"] == "example-改名"
    assert body["data"]["priority"] == "low"
    assert body["data"]["spider_name"] == "example"  # 未提交字段不被清空

    async def _check():
        async with db_session() as s:
            row = (await s.execute(
                select(TaskTemplate).where(TaskTemplate.id == template["id"]))).scalar_one()
            assert row.name == "example-改名"

    asyncio.run(_check())


def test_update_template_rename_conflict_400(db_client, operator_client):
    """改名撞已有模板名 → 400（唯一性在更新路径同样生效）"""
    _create_template(operator_client)
    other = _create_template(operator_client, name="第二模板")
    resp = operator_client.patch(f"{BASE}/{other['id']}", json={"name": TEMPLATE_PAYLOAD["name"]})
    assert resp.status_code == 400
    assert "已存在" in resp.json()["message"]


def test_update_template_not_found_404(db_client, operator_client):
    resp = operator_client.patch(f"{BASE}/99999999", json={"name": "t"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_update_template_viewer_403(viewer_client):
    resp = viewer_client.patch(f"{BASE}/1", json={"name": "t"})
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# DELETE /templates/{id}（require_operator；软删）
# ---------------------------------------------------------------------------

def test_delete_template_ok(db_client, operator_client, db_engine, db_session):
    """删除 → DELETED + 回执 {id, deleted} + 列表不再回显 + 行已移除（副作用）

    观察记录（非缺陷）：模型含 SoftDeleteMixin 且 025 迁移为「软删脱离唯一约束」
    设计，但 Service 走 repo.delete（物理删除）——行为契约（删后可重建同名）仍
    成立，见下一条用例；仅审计痕迹不保留，无 GWT 依据不定缺陷。
    """
    template = _create_template(operator_client)
    resp = operator_client.delete(f"{BASE}/{template['id']}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "DELETED"
    assert body["data"] == {"id": template["id"], "deleted": True}
    assert operator_client.get(BASE).json()["data"] == []

    async def _check():
        async with db_session() as s:
            rows = (await s.execute(select(TaskTemplate))).scalars().all()
            assert rows == []  # 物理删除

    asyncio.run(_check())


def test_recreate_same_name_after_delete_ok(db_client, operator_client):
    """删后同名模板可重建（025 唯一约束设计承诺：删后可重建同名）"""
    first = _create_template(operator_client)
    assert operator_client.delete(f"{BASE}/{first['id']}").status_code == 200
    resp = operator_client.post(BASE, json=TEMPLATE_PAYLOAD)
    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == "CREATED"
    items = operator_client.get(BASE).json()["data"]
    assert len(items) == 1
    assert items[0]["name"] == TEMPLATE_PAYLOAD["name"]  # 同名重建成功且仅一条


def test_delete_template_not_found_404(db_client, operator_client):
    resp = operator_client.delete(f"{BASE}/99999999")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_delete_template_viewer_403(viewer_client):
    resp = viewer_client.delete(f"{BASE}/1")
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# POST /templates/{id}/run（require_operator；核心运营入口）
# ---------------------------------------------------------------------------

def test_run_from_template_ok(db_client, operator_client, db_engine, db_session, monkeypatch):
    """一键运行：CREATED + 任务落库 pending + params/priority 透传 + 消息投递队列（副作用）"""
    fake = _fake_redis(monkeypatch)
    template = _create_template(operator_client)

    resp = operator_client.post(f"{BASE}/{template['id']}/run")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "CREATED"
    task = body["data"]
    assert task["spider_name"] == "example"
    assert task["status"] == "pending"
    assert task["priority"] == "high"  # 模板优先级透传

    async def _check():
        async with db_session() as s:
            rows = (await s.execute(
                select(SpiderTask).where(SpiderTask.spider_name == "example"))).scalars().all()
            assert len(rows) == 1
            assert rows[0].status == "pending"
            assert json.loads(rows[0].params)["urls"] == ["https://example.com"]

    asyncio.run(_check())
    assert sum(len(v) for v in fake.lists.values()) == 1  # 恰好投递一条队列消息


def test_run_from_template_not_found_404(db_client, operator_client, monkeypatch):
    _fake_redis(monkeypatch)  # 守卫在 enqueue 之前，但保持环境一致
    resp = operator_client.post(f"{BASE}/99999999/run")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_run_from_template_unregistered_spider_400(
    db_client, operator_client, db_engine, db_session, monkeypatch
):
    """未登记爬虫的模板 → run 时 400 + 任务零落库（注册表校验在 enqueue 内生效）"""
    _fake_redis(monkeypatch)
    template = _create_template(operator_client, name="坏模板", spider_name="no-such-spider-b1b")

    resp = operator_client.post(f"{BASE}/{template['id']}/run")
    assert resp.status_code == 400, resp.text
    assert "未在注册表登记" in resp.json()["message"]

    async def _check():
        async with db_session() as s:
            assert len((await s.execute(select(SpiderTask))).scalars().all()) == 0

    asyncio.run(_check())


def test_run_from_template_viewer_403(viewer_client):
    resp = viewer_client.post(f"{BASE}/1/run")
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"
