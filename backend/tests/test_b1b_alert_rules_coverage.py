"""B1b 零覆盖路由清剿：告警规则 CRUD（爬虫运营配置面）

覆盖路由（backend/app/api/v1/spiders/schedules.py 告警段，此前零 HTTP 覆盖）：
- GET    /api/v1/spiders/alert-rules          规则列表（require_operator —— 注意高于
        schedules 列表的 require_login，viewer 不可读）
- POST   /api/v1/spiders/alert-rules          创建（require_admin）
- PATCH  /api/v1/spiders/alert-rules/{id}     更新（require_admin）
- DELETE /api/v1/spiders/alert-rules/{id}     删除（require_admin）

既有覆盖对照：test_backend_fixes_regression.py 以直接函数调用覆盖三个写端点的
record_audit 切片；test_alert_service.py 覆盖 Service 单元。本文件补 HTTP 层
（401/403/信封结构/副作用），不重复审计切片。

已修复缺陷（F-B1b-01，B5）：PATCH/DELETE 不存在的 rule_id 此前 Service 抛裸
ValueError → 500；B5 已改抛 NotFoundException（platform_core.exceptions 统一体系，
对齐同域 schedules/templates），现按标准断言 404，复现用例已转正。
"""
from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import select

from platform_core.models.alert_rule import AlertRule

BASE = "/api/v1/spiders/alert-rules"

RULE_PAYLOAD = {
    "name": "连续失败告警",
    "spider_name": "example",
    "rule_type": "consecutive_failures",
    "threshold": 3.0,
    "window_minutes": 30,
    "severity": "critical",
    "channels": ["webhook", "email"],
}


def _create_rule(admin_client, **overrides) -> dict:
    payload = {**RULE_PAYLOAD, **overrides}
    resp = admin_client.post(BASE, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# GET /alert-rules（require_operator：admin/operator 可读，viewer 不可）
# ---------------------------------------------------------------------------

def test_list_alert_rules_operator_ok(db_client, operator_client):
    """operator 读列表：200 + 空态为 []（data 是 list，非分页信封）"""
    resp = operator_client.get(BASE)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == []


def test_list_alert_rules_returns_created(db_client, admin_client):
    """创建后列表回显，channels 反序列化为 list（存储 JSON 串、出口还原）

    注：同一用例只能持一个特权 fixture（conftest 特权 client 共享 TestClient，
    后实例化者覆盖角色）；operator 可读性由 test_list_alert_rules_operator_ok 单测。
    """
    created = _create_rule(admin_client)
    resp = admin_client.get(BASE)  # require_operator 含 admin
    rules = resp.json()["data"]
    assert len(rules) == 1
    assert rules[0]["id"] == created["id"]
    assert rules[0]["channels"] == ["webhook", "email"]  # 出口必须是 list 而非 JSON 串
    assert rules[0]["rule_type"] == "consecutive_failures"
    assert rules[0]["threshold"] == 3.0


def test_list_alert_rules_viewer_403(viewer_client):
    """viewer 直调 → 403（守卫为 require_operator 而非 require_login 的差异证明）"""
    resp = viewer_client.get(BASE)
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_alert_rules_anonymous_401(client):
    assert client.get(BASE).status_code == 401
    assert client.post(BASE, json=RULE_PAYLOAD).status_code == 401
    assert client.patch(f"{BASE}/1", json={"enabled": False}).status_code == 401
    assert client.delete(f"{BASE}/1").status_code == 401
    assert client.get(BASE).json()["code"] == "AUTH_FAILED"


# ---------------------------------------------------------------------------
# POST /alert-rules（require_admin）
# ---------------------------------------------------------------------------

def test_create_alert_rule_admin_ok(db_client, admin_client, db_engine, db_session):
    """admin 创建：CREATED 信封 + channels 出口为 list + DB 行以 JSON 串存储（副作用）"""
    resp = admin_client.post(BASE, json=RULE_PAYLOAD)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "CREATED"
    data = body["data"]
    assert data["id"] > 0
    assert data["name"] == "连续失败告警"
    assert data["severity"] == "critical"
    assert data["enabled"] is True
    assert data["channels"] == ["webhook", "email"]

    async def _check():
        async with db_session() as s:
            rows = (await s.execute(select(AlertRule))).scalars().all()
            assert len(rows) == 1
            assert json.loads(rows[0].channels) == ["webhook", "email"]  # 入库为 JSON 串
            assert rows[0].window_minutes == 30

    asyncio.run(_check())


def test_create_alert_rule_defaults(db_client, admin_client):
    """可选字段缺省：window_minutes=60 / severity=warning / enabled=True（契约默认值）"""
    resp = admin_client.post(BASE, json={
        "name": "结果数下降", "rule_type": "result_drop", "threshold": 50.0,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["window_minutes"] == 60
    assert data["severity"] == "warning"
    assert data["enabled"] is True
    assert data["spider_name"] is None  # 全局规则


def test_create_alert_rule_operator_403(db_client, operator_client, db_engine, db_session):
    """operator 直调 admin 端点 → 403 + 零落库"""
    resp = operator_client.post(BASE, json=RULE_PAYLOAD)
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"

    async def _check():
        async with db_session() as s:
            assert len((await s.execute(select(AlertRule))).scalars().all()) == 0

    asyncio.run(_check())


@pytest.mark.parametrize("payload,field", [
    ({"name": "x", "rule_type": "consecutive_failures"}, "threshold"),  # 缺必填 threshold
    ({"name": "x", "threshold": 1.0}, "rule_type"),                     # 缺必填 rule_type
    ({"rule_type": "consecutive_failures", "threshold": 1.0}, "name"),  # 缺必填 name
])
def test_create_alert_rule_validation_422(db_client, admin_client, payload, field):
    resp = admin_client.post(BASE, json=payload)
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "VALIDATION_ERROR"
    assert field in resp.text


# ---------------------------------------------------------------------------
# PATCH /alert-rules/{id}（require_admin）
# ---------------------------------------------------------------------------

def test_update_alert_rule_ok(db_client, admin_client, db_engine, db_session):
    """更新 threshold/enabled/channels → UPDATED + 回显新值 + DB 同步（副作用）"""
    rule = _create_rule(admin_client)
    resp = admin_client.patch(f"{BASE}/{rule['id']}", json={
        "threshold": 5.0, "enabled": False, "channels": ["dingtalk"],
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "UPDATED"
    assert body["data"]["threshold"] == 5.0
    assert body["data"]["enabled"] is False
    assert body["data"]["channels"] == ["dingtalk"]
    assert body["data"]["name"] == "连续失败告警"  # 未提交字段不被清空

    async def _check():
        async with db_session() as s:
            row = (await s.execute(
                select(AlertRule).where(AlertRule.id == rule["id"]))).scalar_one()
            assert row.threshold == 5.0
            assert row.enabled is False
            assert json.loads(row.channels) == ["dingtalk"]

    asyncio.run(_check())


def test_update_alert_rule_not_found_404(db_client, admin_client):
    """不存在 id → 404 NOT_FOUND（B5 修复 F-B1b-01：ValueError→NotFoundException）"""
    resp = admin_client.patch(f"{BASE}/99999999", json={"enabled": False})
    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == "NOT_FOUND"


def test_update_alert_rule_operator_403(operator_client):
    resp = operator_client.patch(f"{BASE}/1", json={"enabled": False})
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# DELETE /alert-rules/{id}（require_admin）
# ---------------------------------------------------------------------------

def test_delete_alert_rule_ok(db_client, admin_client, db_engine, db_session):
    """删除 → DELETED + 回执 {rule_id, deleted} + 列表同步为空（副作用）"""
    rule = _create_rule(admin_client)
    resp = admin_client.delete(f"{BASE}/{rule['id']}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "DELETED"
    assert body["data"] == {"rule_id": rule["id"], "deleted": True}

    async def _check():
        async with db_session() as s:
            assert (await s.execute(select(AlertRule))).scalars().all() == []

    asyncio.run(_check())
    assert admin_client.get(BASE).json()["data"] == []


def test_delete_alert_rule_not_found_404(db_client, admin_client):
    """不存在 id → 404 NOT_FOUND（B5 修复 F-B1b-01：ValueError→NotFoundException）"""
    resp = admin_client.delete(f"{BASE}/99999999")
    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == "NOT_FOUND"


def test_delete_alert_rule_operator_403(operator_client):
    resp = operator_client.delete(f"{BASE}/1")
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"
