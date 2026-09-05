"""B1b 零覆盖路由清剿：系统配置读写（配置面）

覆盖路由（backend/app/api/v1/configs.py，此前零 HTTP 覆盖）：
- GET /api/v1/configs/          全量配置（require_login；data 为 {key: value} 字典）
- PUT /api/v1/configs/{key}     单项更新（require_admin；存在则改、缺省则建）

既有覆盖对照：test_config_service.py 仅 Service 单元（session 直查），HTTP 层零覆盖；
test_t10_api_coverage.py 的 notify-config 是 /admin 域另一端点，不重复。

断言口径（标准 = 端点契约注释「读需登录，写仅管理员」+ SystemConfig 模型
config_key String(50) unique + Service「不存在则创建」行为）：
- 配置类核心断言：写入后 GET 回读一致（持久化与读取回显一致）
- 覆盖更新分支：同 key 二次 PUT 不新增行

已修复缺陷（F-B1b-02，B5）：PUT {key} 此前无长度/格式校验，51 字符 key 在
SQLite 放行落库（MySQL 严格模式将 DataError→500）。B5 已在路由层补
Path(max_length=50, pattern=小写字母数字+./_) 契约校验 → 422，用例已转正。
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from platform_core.models.system_config import SystemConfig

BASE = "/api/v1/configs"


# ---------------------------------------------------------------------------
# GET /configs/（require_login）
# ---------------------------------------------------------------------------

def test_get_configs_empty_ok(db_client, viewer_client):
    """viewer（最低特权）读：200 + data 为 {key: value} 字典（空库为 {}）"""
    resp = viewer_client.get(f"{BASE}/")
    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == "SUCCESS"
    assert resp.json()["data"] == {}


def test_get_configs_anonymous_401(client):
    resp = client.get(f"{BASE}/")
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_FAILED"


# ---------------------------------------------------------------------------
# PUT /configs/{key}（require_admin）
# ---------------------------------------------------------------------------

def test_put_config_create_and_readback(db_client, admin_client, db_engine, db_session):
    """新建配置 → UPDATED + GET 回读一致 + DB 一行（持久化与读取回显一致）"""
    resp = admin_client.put(f"{BASE}/site.name", json={"value": "AutoAgents 平台"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "UPDATED"
    assert "site.name" in body["message"]

    got = admin_client.get(f"{BASE}/").json()["data"]
    assert got["site.name"] == "AutoAgents 平台"  # 回显一致

    async def _check():
        async with db_session() as s:
            rows = (await s.execute(
                select(SystemConfig).where(SystemConfig.config_key == "site.name"))).scalars().all()
            assert len(rows) == 1
            assert rows[0].config_value == "AutoAgents 平台"

    asyncio.run(_check())


def test_put_config_overwrite_no_duplicate(db_client, admin_client, db_engine, db_session):
    """同 key 二次 PUT → 覆盖旧值（更新分支），DB 不新增行"""
    admin_client.put(f"{BASE}/site.name", json={"value": "v1"})
    resp = admin_client.put(f"{BASE}/site.name", json={"value": "v2"})
    assert resp.status_code == 200, resp.text
    assert admin_client.get(f"{BASE}/").json()["data"]["site.name"] == "v2"

    async def _check():
        async with db_session() as s:
            rows = (await s.execute(
                select(SystemConfig).where(SystemConfig.config_key == "site.name"))).scalars().all()
            assert len(rows) == 1
            assert rows[0].config_value == "v2"

    asyncio.run(_check())


def test_put_config_validation_422(db_client, admin_client):
    """缺 value 字段 → 422（ConfigUpdate 契约必填）"""
    resp = admin_client.put(f"{BASE}/site.name", json={})
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "VALIDATION_ERROR"
    assert "value" in resp.text


def test_put_config_overlength_key_422(db_client, admin_client):
    """51 字符 key（模型 String(50) 界外）→ 422（B5 修复 F-B1b-02：路由层 Path 校验）"""
    resp = admin_client.put(f"{BASE}/{'k' * 51}", json={"value": "v"})
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_put_config_anonymous_401(client):
    resp = client.put(f"{BASE}/site.name", json={"value": "x"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_FAILED"


@pytest.mark.parametrize("low_client", ["operator_client", "viewer_client"])
def test_put_config_low_role_403(request, low_client):
    """operator / viewer 直调 admin 端点 → 403（角色矩阵逐格）"""
    resp = request.getfixturevalue(low_client).put(f"{BASE}/site.name", json={"value": "x"})
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"
