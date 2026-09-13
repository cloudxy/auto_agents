"""T-12（FR-87）入队信封用户可见禁配额内码。

GWT-87.1 满额 / GWT-87.2 未满 / GWT-87.3 只读强提交（API 面）。
对照：
- test_saas_quota.py：执法本体（QuotaService 直调）内部码仍 QUOTA_EXCEEDED——内部码留给验收；
- test_saas_wiring.py：入队金标已随本票改写（PIT-2 改守卫同 PR 改测试）。
"""
import asyncio

from sqlalchemy import select

from platform_core.models.spider_task import SpiderTask
from platform_core.models.tenant import Tenant
from platform_core.models.user import User

# X-QUOTA：用户可见信封禁内码（code 字段与 message 双断言；无裸 429 状态码）
_FORBIDDEN_CODES = {"FORBIDDEN", "QUOTA_EXCEEDED", "QUOTA_PLAN_LOCKED", "HTTP_403", "HTTP_429"}
_VISIBLE_TOKENS = ("QUOTA_EXCEEDED", "QUOTA_PLAN_LOCKED", "FORBIDDEN", "PAYMENT_NOT_CONFIGURED")

RUN_URL = "/api/v1/spiders/run"


def _seed_worker_redis(monkeypatch):
    """入队链路 Redis 桩：工人心跳在线 + 槽位/配额计数走 FakeRedis"""
    from stubs import FakeRedis, seed_worker_heartbeat

    fake = FakeRedis()
    seed_worker_heartbeat(fake)

    import backend.services.quota_service as quota_mod
    import backend.services.spider_task_service as svc_mod
    monkeypatch.setattr(svc_mod, "get_async_redis", lambda: fake)
    monkeypatch.setattr(quota_mod, "get_async_redis", lambda: fake)


def _set_tenant_quota(db_session, tid: int, **quota) -> None:
    async def _go():
        async with db_session() as s:
            tenant = (await s.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()
            tenant.quota = quota
            await s.commit()

    asyncio.run(_go())


def _seed_active_task(db_session, tid: int, status: str = "running") -> None:
    async def _go():
        async with db_session() as s:
            s.add(SpiderTask(spider_name="example", tenant_id=tid, status=status, params="{}"))
            await s.commit()

    asyncio.run(_go())


def _tasks_of(db_session, tid: int) -> list:
    async def _go():
        async with db_session() as s:
            return (await s.execute(
                select(SpiderTask).where(SpiderTask.tenant_id == tid)
            )).scalars().all()

    return asyncio.run(_go())


def _assert_no_inner_code(resp) -> None:
    """可见处断言：无裸 429、信封 code 非内码、message 无内码串与 429 数字串"""
    assert resp.status_code != 429, resp.text
    body = resp.json()
    assert body["code"] not in _FORBIDDEN_CODES, body["code"]
    for token in _VISIBLE_TOKENS:
        assert token not in body["message"], body["message"]
    assert "429" not in body["message"], body["message"]


def _make_viewer_headers(db_session, tid: int, username: str) -> dict:
    """只读成员 Bearer（role=viewer，真链路 JWT→DB 快照）"""
    from backend.services.auth_service import AuthService

    async def _go():
        async with db_session() as s:
            s.add(User(
                username=username, email=f"{username}@x.co", password_hash="x",
                role="viewer", tenant_id=tid, tenant_role="viewer", is_active=True,
            ))
            await s.commit()
            u = (await s.execute(select(User).where(User.username == username))).scalar_one()
            token = await AuthService(s).create_token({
                "id": u.id, "username": u.username, "is_admin": False, "role": "viewer",
                "tenant_id": tid, "tenant_role": "viewer", "is_platform_admin": False,
            })
            return token.access_token

    return {"Authorization": f"Bearer {asyncio.run(_go())}"}


def test_gwt_87_1_quota_full_envelope_is_user_visible(db_client, db_session, monkeypatch):
    """GWT-87.1 / FR-U02：并发已满 → 「已达配额上限」+「申请提升」；
    可见处无 QUOTA_EXCEEDED、无裸 429；不建支付单。"""
    from conftest import make_tenant_owner_headers

    _seed_worker_redis(monkeypatch)
    headers, tid = make_tenant_owner_headers(db_session, slug="t12-871")
    _set_tenant_quota(db_session, tid, task_concurrency=1)
    _seed_active_task(db_session, tid)  # 1/1 占满

    resp = db_client.post(
        RUN_URL, headers=headers,
        json={"spider_name": "example", "params": "{}"},
    )
    _assert_no_inner_code(resp)
    body = resp.json()
    assert "已达配额上限" in body["message"]
    assert "申请提升" in body["message"]
    assert "采集未运行，不会出数" not in body["message"]
    assert "去结果库" not in body["message"]
    assert "提交升级" not in body["message"]
    assert len(_tasks_of(db_session, tid)) == 1  # 拒绝路径零新任务


def test_gwt_87_2_under_quota_enqueues_normally(db_client, db_session, monkeypatch):
    """GWT-87.2：并发未满，提交采集入队 → 不出现满额句；任务按已兑出数环继续（落库 pending）"""
    from conftest import make_tenant_owner_headers

    _seed_worker_redis(monkeypatch)
    headers, tid = make_tenant_owner_headers(db_session, slug="t12-872")

    resp = db_client.post(
        RUN_URL, headers=headers,
        json={"spider_name": "example", "params": "{}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert "已达配额上限" not in body["message"]
    assert "申请提升" not in body["message"]
    rows = _tasks_of(db_session, tid)
    assert len(rows) == 1
    assert rows[0].status == "pending"


def test_gwt_87_3_viewer_submit_rejected_user_visible(db_client, db_session):
    """GWT-87.3：只读成员直提交采集入队 → 说明当前账号不能提交（同族中文）；
    可见处仍不含 QUOTA_EXCEEDED 与裸 429；不产生任务。"""
    from conftest import make_tenant_owner_headers

    _headers, tid = make_tenant_owner_headers(db_session, slug="t12-873")
    viewer = _make_viewer_headers(db_session, tid, "t12-viewer")

    resp = db_client.post(
        RUN_URL, headers=viewer,
        json={"spider_name": "example", "params": "{}"},
    )
    _assert_no_inner_code(resp)
    body = resp.json()
    assert "不能提交" in body["message"]
    assert "请联系企业管理员" in body["message"]
    assert _tasks_of(db_session, tid) == []  # 越权路径零落库
