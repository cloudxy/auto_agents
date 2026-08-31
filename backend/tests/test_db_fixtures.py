"""E0.1a 测试基座核心验证（工单 01）：SQLite 会话 fixture 与测试间隔离

Seam（工单预确认）：
- fixture 本身：db_engine / db_session / db_client
- API 端点：TestClient 走真实读路径 GET /api/v1/admin/users

期望值全部来自独立事实源（模型表名清单、字面量用户名），不做同源重算。
"""
import asyncio

import pytest
from sqlalchemy import func, inspect as sa_inspect, select

from platform_core.models.user import User

# 独立事实源：platform_core/models/ 下模型文件的表名清单
# （不用 Base.metadata 回读——那与 create_all 同源，属 tautological 断言）
ALL_ORM_TABLES = {
    "users",
    "spider_tasks",
    "spider_results",
    "spider_schedules",
    "spider_definitions",
    "spider_task_templates",
    "ai_plans",
    "llm_providers",
    "llm_token_usage",
    "channel_events",
    "channel_probe_results",
    "alert_rules",
    "operation_logs",
    "system_configs",
    "skills",
    "skill_reviews",
    "skill_jobs",
    "llm_provider_models",
}


def _new_user(username: str) -> User:
    """最小可入库用户（工厂 builder 属工单 02，此处仅内联构造）"""
    return User(
        username=username,
        email=f"{username}@test.local",
        password_hash="not-a-real-hash",
        role="viewer",
        is_active=True,
    )


async def _seed_one(db_session, username: str) -> None:
    async with db_session() as s:
        s.add(_new_user(username))
        await s.commit()


@pytest.mark.asyncio
async def test_db_engine_creates_all_orm_tables(db_engine):
    """create_all 覆盖 ORM 全表——等值断言：漏注册模型或意外多表都会被抓"""
    async with db_engine.connect() as conn:
        actual = await conn.run_sync(lambda c: set(sa_inspect(c).get_table_names()))
    assert actual == ALL_ORM_TABLES, (
        f"缺表: {ALL_ORM_TABLES - actual}; 多表: {actual - ALL_ORM_TABLES}"
    )


@pytest.mark.asyncio
async def test_isolation_writer_a_seeds_unique_key(db_session):
    """隔离·写方 A：落一行唯一键用户并自证可读"""
    async with db_session() as s:
        s.add(_new_user("isolation-probe"))
        await s.commit()
        count = (
            await s.execute(select(func.count()).select_from(User))
        ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_isolation_writer_b_same_unique_key_succeeds(db_session):
    """隔离·写方 B：同一唯一键必须可再次落库。

    等价性前提：User.username/email 带 unique 约束——若 A 的数据泄漏进本测试的库，
    B 的 insert 必撞 IntegrityError，且 scalar_one 因出现两行而抛错。故"两测全绿"
    严格强于"A 写入的行在 B 中不可见"。
    """
    async with db_session() as s:
        s.add(_new_user("isolation-probe"))
        await s.commit()
        stored = (
            await s.execute(select(User).where(User.username == "isolation-probe"))
        ).scalar_one()
        assert stored.email == "isolation-probe@test.local"
        assert stored.role == "viewer"


def test_db_client_reads_seeded_data(db_engine, db_client, db_session):
    """端点与测试断言走同一引擎同一库：种子数据经真实 API 可见（含统一信封形状）"""
    asyncio.run(_seed_one(db_session, "endpoint-probe"))

    resp = db_client.get("/api/v1/admin/users")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    usernames = [u["username"] for u in body["data"]["items"]]
    assert "endpoint-probe" in usernames
    assert body["data"]["total"] >= 1
