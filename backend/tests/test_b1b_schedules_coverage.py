"""B1b 零覆盖路由清剿：定时调度 CRUD（爬虫运营配置面）

覆盖路由（backend/app/api/v1/spiders/schedules.py，此前零 HTTP 覆盖）：
- GET    /api/v1/spiders/schedules            调度列表（require_login）
- POST   /api/v1/spiders/schedules            创建调度（require_admin；注册表/cron/同爬虫唯一三重校验）
- PATCH  /api/v1/spiders/schedules/{id}       局部更新（require_admin；启停/改表达式重算触发时刻）
- DELETE /api/v1/spiders/schedules/{id}       删除（require_admin）

既有覆盖对照：schedules 无任何 HTTP 层用例（test_backend_fixes_regression.py 仅覆盖
alert-rules 写端点审计；本文件不重复审计切片）。

断言口径（标准 = schema 契约 platform_core/schemas/spider.py + 服务注释行为 +
统一异常体系 NotFoundException→404 / BusinessException→400 / Pydantic→422）：
- 副作用断言：写操作直接查库核对（不依赖响应回显）
- 非法输入断言三件事：返回错误码 + 零落库
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from platform_core.models.spider_schedule import SpiderSchedule

BASE = "/api/v1/spiders/schedules"
VALID_CRON = "*/5 * * * *"  # 10 字符，合法 5 段


# ---------------------------------------------------------------------------
# GET /schedules（require_login：admin/operator/viewer 均可读）
# ---------------------------------------------------------------------------

def test_list_schedules_empty_ok(db_client, viewer_client):
    """viewer（最低特权）读列表：200 + {total, items} 空态结构"""
    resp = viewer_client.get(BASE)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 0
    assert data["items"] == []


def test_list_schedules_returns_created(db_client, admin_client):
    """创建后列表回显（结构 + 计数一致）"""
    post = admin_client.post(
        BASE, json={"spider_name": "example", "cron_expr": VALID_CRON}
    )
    assert post.status_code == 200, post.text
    resp = admin_client.get(BASE)
    data = resp.json()["data"]
    assert data["total"] == 1
    item = data["items"][0]
    assert item["spider_name"] == "example"
    assert item["cron_expr"] == VALID_CRON
    assert item["enabled"] is True


def test_schedules_anonymous_401(client):
    """匿名直调四个方法 → 401 AUTH_FAILED（守卫先于业务）"""
    assert client.get(BASE).status_code == 401
    assert client.post(BASE, json={"spider_name": "example", "cron_expr": VALID_CRON}).status_code == 401
    assert client.patch(f"{BASE}/1", json={"enabled": False}).status_code == 401
    assert client.delete(f"{BASE}/1").status_code == 401
    assert client.get(BASE).json()["code"] == "AUTH_FAILED"


# ---------------------------------------------------------------------------
# POST /schedules（require_admin）
# ---------------------------------------------------------------------------

def test_create_schedule_admin_ok(db_client, admin_client, db_engine, db_session):
    """admin 创建：CREATED 信封 + 落库一行 + next_run_at 已按 cron 预计算（副作用）"""
    resp = admin_client.post(
        BASE,
        json={"spider_name": "example", "cron_expr": VALID_CRON,
              "params": '{"urls": ["https://example.com"]}'},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "CREATED"
    data = body["data"]
    assert data["id"] > 0
    assert data["spider_name"] == "example"
    assert data["enabled"] is True
    assert data["next_run_at"] is not None  # enabled=True 时触发时刻非空

    async def _check():
        async with db_session() as s:
            rows = (await s.execute(select(SpiderSchedule))).scalars().all()
            assert len(rows) == 1
            assert rows[0].cron_expr == VALID_CRON
            assert rows[0].next_run_at is not None

    asyncio.run(_check())


def test_create_schedule_operator_403(db_client, operator_client, db_engine, db_session):
    """operator 直调 admin 端点 → 403 FORBIDDEN + 零落库"""
    resp = operator_client.post(BASE, json={"spider_name": "example", "cron_expr": VALID_CRON})
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"

    async def _check():
        async with db_session() as s:
            assert len((await s.execute(select(SpiderSchedule))).scalars().all()) == 0

    asyncio.run(_check())


@pytest.mark.parametrize("payload,field", [
    ({"cron_expr": VALID_CRON}, "spider_name"),                    # 缺 spider_name
    ({"spider_name": "", "cron_expr": VALID_CRON}, "spider_name"),  # 空串（min_length=1 界外）
    ({"spider_name": "example"}, "cron_expr"),                     # 缺 cron_expr
    ({"spider_name": "example", "cron_expr": "* * * *"}, "cron_expr"),  # 4 段 7 字符（min_length=9 界外）
    ({"spider_name": "x" * 101, "cron_expr": VALID_CRON}, "spider_name"),  # max=100 界外
])
def test_create_schedule_validation_422(db_client, admin_client, db_engine, db_session, payload, field):
    """Pydantic 校验 422（字段名在错误详情中）+ 零落库"""
    resp = admin_client.post(BASE, json=payload)
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "VALIDATION_ERROR"
    assert field in resp.text

    async def _check():
        async with db_session() as s:
            assert len((await s.execute(select(SpiderSchedule))).scalars().all()) == 0

    asyncio.run(_check())


def test_create_schedule_invalid_cron_400(db_client, admin_client, db_engine, db_session):
    """cron 长度合法但 croniter 拒绝（分钟位 99）→ 400 BUSINESS_ERROR + 零落库"""
    resp = admin_client.post(BASE, json={"spider_name": "example", "cron_expr": "99 * * * *"})
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["code"] == "BUSINESS_ERROR"
    assert "cron" in body["message"]

    async def _check():
        async with db_session() as s:
            assert len((await s.execute(select(SpiderSchedule))).scalars().all()) == 0

    asyncio.run(_check())


def test_create_schedule_unregistered_spider_400(db_client, admin_client, db_engine, db_session):
    """未登记爬虫（DB 与 yml 种子均无）→ 400 + 零落库"""
    resp = admin_client.post(BASE, json={"spider_name": "no-such-spider-b1b", "cron_expr": VALID_CRON})
    assert resp.status_code == 400, resp.text
    assert "未在注册表登记" in resp.json()["message"]

    async def _check():
        async with db_session() as s:
            assert len((await s.execute(select(SpiderSchedule))).scalars().all()) == 0

    asyncio.run(_check())


def test_create_schedule_duplicate_spider_400(db_client, admin_client, db_engine, db_session):
    """同爬虫第二条调度 → 400 + 库中仍只有一条（唯一性 + 副作用不变）"""
    first = admin_client.post(BASE, json={"spider_name": "example", "cron_expr": VALID_CRON})
    assert first.status_code == 200, first.text
    second = admin_client.post(BASE, json={"spider_name": "example", "cron_expr": "0 * * * *"})
    assert second.status_code == 400
    assert "已存在调度计划" in second.json()["message"]

    async def _check():
        async with db_session() as s:
            rows = (await s.execute(select(SpiderSchedule))).scalars().all()
            assert len(rows) == 1  # 第二条未落库

    asyncio.run(_check())


# ---------------------------------------------------------------------------
# PATCH /schedules/{id}（require_admin）
# ---------------------------------------------------------------------------

def _create_schedule(admin_client) -> int:
    resp = admin_client.post(BASE, json={"spider_name": "example", "cron_expr": VALID_CRON})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


def test_update_schedule_disable_clears_next_run(db_client, admin_client, db_engine, db_session):
    """停用 → UPDATED + next_run_at 清空 + 库中 enabled=False（状态变更副作用）"""
    sid = _create_schedule(admin_client)
    resp = admin_client.patch(f"{BASE}/{sid}", json={"enabled": False})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "UPDATED"
    assert body["data"]["enabled"] is False
    assert body["data"]["next_run_at"] is None  # 停用即无下次触发

    async def _check():
        async with db_session() as s:
            row = (await s.execute(
                select(SpiderSchedule).where(SpiderSchedule.id == sid))).scalar_one()
            assert row.enabled is False
            assert row.next_run_at is None

    asyncio.run(_check())


def test_update_schedule_change_cron_recalculates(db_client, admin_client):
    """改表达式 → UPDATED + cron 更新 + next_run_at 按新表达式重算（非空）"""
    sid = _create_schedule(admin_client)
    resp = admin_client.patch(f"{BASE}/{sid}", json={"cron_expr": "0 3 * * *"})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["cron_expr"] == "0 3 * * *"
    assert data["next_run_at"] is not None


def test_update_schedule_invalid_cron_400(db_client, admin_client, db_engine, db_session):
    """更新非法 cron → 400 + 原表达式未被破坏（拒绝路径零副作用）"""
    sid = _create_schedule(admin_client)
    resp = admin_client.patch(f"{BASE}/{sid}", json={"cron_expr": "* * * 99 *"})
    assert resp.status_code == 400
    assert "cron" in resp.json()["message"]

    async def _check():
        async with db_session() as s:
            row = (await s.execute(
                select(SpiderSchedule).where(SpiderSchedule.id == sid))).scalar_one()
            assert row.cron_expr == VALID_CRON  # 原值未变

    asyncio.run(_check())


def test_update_schedule_not_found_404(db_client, admin_client):
    """不存在 id → 404 NOT_FOUND（统一异常体系契约）"""
    resp = admin_client.patch(f"{BASE}/99999999", json={"enabled": False})
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_update_schedule_operator_403(operator_client):
    resp = operator_client.patch(f"{BASE}/1", json={"enabled": False})
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# DELETE /schedules/{id}（require_admin）
# ---------------------------------------------------------------------------

def test_delete_schedule_ok(db_client, admin_client, db_engine, db_session):
    """删除 → DELETED + 回执 {schedule_id, spider_name} + 库中已无该行（副作用）"""
    sid = _create_schedule(admin_client)
    resp = admin_client.delete(f"{BASE}/{sid}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "DELETED"
    assert body["data"] == {"schedule_id": sid, "spider_name": "example"}

    async def _check():
        async with db_session() as s:
            rows = (await s.execute(select(SpiderSchedule))).scalars().all()
            assert rows == []  # 物理删除

    asyncio.run(_check())
    listing = admin_client.get(BASE).json()["data"]
    assert listing["total"] == 0  # 列表同步消失


def test_delete_schedule_not_found_404(db_client, admin_client):
    resp = admin_client.delete(f"{BASE}/99999999")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_delete_schedule_operator_403(operator_client):
    resp = operator_client.delete(f"{BASE}/1")
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"
