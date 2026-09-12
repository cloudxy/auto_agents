"""T-38（FR-102 / GWT-102.1…102.5）平台超管以平台租户身份入队。

对照：
- test_saas_wiring.py GWT-09.4 金标本 PR 同步改写（PIT-2：改守卫同 PR 改测试；
  契约 §5 已裁「平台入队被拒 → T-38 改解析」）；
- test_fr87_enqueue_envelope.py T-12 满额句族（102.3 复用同句式断言）；
- test_saas_wiring.py::test_enqueue_without_tenant_does_not_create（服务层
  None 拒绝守卫不变——本票只改解析点，require_enqueue_tenant 本体零改动）。

边界（GWT-82.4 / QA-07）：平台租户身份仅用于采集入队与方案归属；relay 域
（渠道组/我的安装）行为不回归——由全量套件（test_relay_token_usage 等）兜底。
"""
import asyncio
import json

from sqlalchemy import select

from platform_core.models.ai_plan import AiPlan
from platform_core.models.spider_definition import SpiderDefinition
from platform_core.models.spider_task import SpiderTask
from platform_core.models.tenant import Tenant
from platform_core.models.user import User

RUN_URL = "/api/v1/spiders/run"
PLANS_URL = "/api/v1/ai/plans"
TASKS_URL = "/api/v1/spiders/tasks"

# X-QUOTA 同口径：可见信封禁内码（code 与 message 双断言；无裸 429）
_FORBIDDEN_CODES = {"FORBIDDEN", "QUOTA_EXCEEDED", "QUOTA_PLAN_LOCKED", "HTTP_403", "HTTP_429"}
_VISIBLE_TOKENS = ("QUOTA_EXCEEDED", "QUOTA_PLAN_LOCKED", "FORBIDDEN", "PAYMENT_NOT_CONFIGURED")


def _seed_worker_redis(monkeypatch):
    """入队链路 Redis 桩：工人心跳在线 + 槽位/配额计数走 FakeRedis"""
    from stubs import FakeRedis, seed_worker_heartbeat

    fake = FakeRedis()
    seed_worker_heartbeat(fake)

    import backend.services.quota_service as quota_mod
    import backend.services.spider_task_service as svc_mod
    monkeypatch.setattr(svc_mod, "get_async_redis", lambda: fake)
    monkeypatch.setattr(quota_mod, "get_async_redis", lambda: fake)


def _seed_platform_tenant(db_session) -> int:
    """种平台租户行（slug=platform，024 种子同构）；返回 tenant id"""
    async def _go():
        async with db_session() as s:
            row = Tenant(slug="platform", name="平台租户")
            s.add(row)
            await s.commit()
            return int(row.id)

    return asyncio.run(_go())


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


def _all_tasks(db_session) -> list:
    async def _go():
        async with db_session() as s:
            return (await s.execute(select(SpiderTask))).scalars().all()

    return asyncio.run(_go())


def _assert_no_inner_code(resp) -> None:
    assert resp.status_code != 429, resp.text
    body = resp.json()
    assert body["code"] not in _FORBIDDEN_CODES, body["code"]
    for token in _VISIBLE_TOKENS:
        assert token not in body["message"], body["message"]
    assert "429" not in body["message"], body["message"]


def _make_operator_headers(db_session, tid: int, username: str) -> dict:
    """operator Bearer（role=operator，挂指定租户；真链路 JWT→DB 快照）"""
    from backend.services.auth_service import AuthService

    async def _go():
        async with db_session() as s:
            s.add(User(
                username=username, email=f"{username}@x.co", password_hash="x",
                role="operator", tenant_id=tid, tenant_role="operator", is_active=True,
            ))
            await s.commit()
            u = (await s.execute(select(User).where(User.username == username))).scalar_one()
            token = await AuthService(s).create_token({
                "id": u.id, "username": u.username, "is_admin": False, "role": "operator",
                "tenant_id": tid, "tenant_role": "operator", "is_platform_admin": False,
            })
            return token.access_token

    return {"Authorization": f"Bearer {asyncio.run(_go())}"}


def test_gwt_102_1_platform_admin_enqueue_belongs_to_platform_tenant(
    db_client, platform_admin_client, db_session, monkeypatch,
):
    """GWT-102.1：平台超管完成 AI 方案后试采 → 入队成功；不出现「没有企业身份，
    无法入队」；任务列表可见且归属平台租户（行级 tenant_id 钉住）。"""
    _seed_worker_redis(monkeypatch)
    ptid = _seed_platform_tenant(db_session)

    resp = db_client.post(
        RUN_URL, json={"spider_name": "example", "params": "{}"},
    )
    assert resp.status_code == 200, resp.text
    assert "没有企业身份" not in resp.text
    task_id = resp.json()["data"]["id"]

    listing = db_client.get(f"{TASKS_URL}?limit=100")
    assert listing.status_code == 200, listing.text
    assert task_id in [i["id"] for i in listing.json()["data"]["items"]]

    rows = _tasks_of(db_session, ptid)
    assert [t.id for t in rows] == [task_id]
    assert all(t.tenant_id == ptid for t in _all_tasks(db_session))  # 无无主任务


def test_gwt_102_1_plan_and_test_capture_share_platform_identity(
    db_client, platform_admin_client, db_session, monkeypatch,
):
    """GWT-102.1 后半：AI 方案归属平台租户；试采入队（orchestrator._execute_test
    同链：require_enqueue_tenant(plan.tenant_id) → SpiderService.enqueue）成功。"""
    from backend.services.spider_task_service import SpiderTaskService

    _seed_worker_redis(monkeypatch)
    ptid = _seed_platform_tenant(db_session)

    created = db_client.post(PLANS_URL, json={"target_url": "https://wiz.example"})
    assert created.status_code == 200, created.text
    plan_id = created.json()["data"]["id"]

    async def _check():
        async with db_session() as s:
            plan = (await s.execute(select(AiPlan).where(AiPlan.id == plan_id))).scalar_one()
            assert plan.tenant_id == ptid  # 方案归属平台租户
            # 试采同链（ai_planner/orchestrator.py L213-220）：以 plan.tenant_id 入队
            task = await SpiderTaskService(s).enqueue(
                spider_name="flow_generic",
                params=json.dumps({"pagination": {"page": 1}}),
                priority="low", tenant_id=plan.tenant_id,
            )
            return int(task.id)

    task_id = asyncio.run(_check())
    rows = _tasks_of(db_session, ptid)
    assert task_id in [t.id for t in rows]
    assert all(t.tenant_id == ptid for t in rows)


def test_gwt_102_2_online_enqueue_same_platform_identity(
    db_client, platform_admin_client, db_session, monkeypatch,
):
    """GWT-102.2：上线入队（AI 注册定义经 run 端点）成功，与试采同一身份语义。"""
    async def _seed():
        async with db_session() as s:
            s.add(SpiderDefinition(
                name="ai_wiz_example", title="AI 采集 - wiz", type="flow",
                description="AI 生成（T-38 夹具）", enabled=True, source="ai_generated",
            ))
            await s.commit()

    asyncio.run(_seed())
    _seed_worker_redis(monkeypatch)
    ptid = _seed_platform_tenant(db_session)

    resp = db_client.post(
        RUN_URL, json={"spider_name": "ai_wiz_example", "params": "{}"},
    )
    assert resp.status_code == 200, resp.text
    rows = _tasks_of(db_session, ptid)
    assert len(rows) == 1
    assert rows[0].tenant_id == ptid


def test_gwt_102_3_platform_tenant_quota_not_bypassed(
    db_client, platform_admin_client, db_session, monkeypatch,
):
    """GWT-102.3：平台租户配额已满 → 超管入队吃 T-12 满额句族（X-QUOTA 无内码）；
    不入队、不因超管身份绕过。"""
    _seed_worker_redis(monkeypatch)
    ptid = _seed_platform_tenant(db_session)
    _set_tenant_quota(db_session, ptid, task_concurrency=1)
    _seed_active_task(db_session, ptid)  # 1/1 占满

    resp = db_client.post(
        RUN_URL, json={"spider_name": "example", "params": "{}"},
    )
    _assert_no_inner_code(resp)
    body = resp.json()
    assert "已达配额上限" in body["message"]
    assert "请联系企业管理员" in body["message"]
    assert len(_tasks_of(db_session, ptid)) == 1  # 拒绝路径零新任务


def test_gwt_102_4_regular_tenant_attribution_unchanged(
    db_client, db_session, monkeypatch,
):
    """GWT-102.4：企业 A 经办提交入队 → 任务归属企业 A（解析不变）；平台租户与
    企业 B 的队列零变化。"""
    from conftest import make_tenant_owner_headers

    _seed_worker_redis(monkeypatch)
    ptid = _seed_platform_tenant(db_session)
    headers_a, tid_a = make_tenant_owner_headers(db_session, slug="t38-a")

    async def _mk_b():
        async with db_session() as s:
            s.add(Tenant(slug="t38-b", name="公司-B"))
            await s.commit()
    asyncio.run(_mk_b())

    resp = db_client.post(
        RUN_URL, headers=headers_a,
        json={"spider_name": "example", "params": "{}"},
    )
    assert resp.status_code == 200, resp.text
    rows_a = _tasks_of(db_session, tid_a)
    assert len(rows_a) == 1 and rows_a[0].tenant_id == tid_a  # 归属企业 A，绝非平台租户
    assert _tasks_of(db_session, ptid) == []  # 平台租户队列不变

    async def _b_count():
        async with db_session() as s:
            from sqlalchemy import func
            tb = (await s.execute(select(Tenant).where(Tenant.slug == "t38-b"))).scalar_one()
            n = (await s.execute(
                select(func.count()).select_from(SpiderTask)
                .where(SpiderTask.tenant_id == tb.id)
            )).scalar_one()
            return int(n)
    assert asyncio.run(_b_count()) == 0  # 企业 B 用量不变


def test_gwt_102_5_non_admin_impersonation_rejected(
    db_client, db_session, monkeypatch,
):
    """GWT-102.5：非超管（挂平台租户的 operator）直打入队 → 拒绝；不产生平台
    租户任务；可见句不含内部码。"""
    _seed_worker_redis(monkeypatch)
    ptid = _seed_platform_tenant(db_session)
    headers = _make_operator_headers(db_session, ptid, "t38-impersonator")

    resp = db_client.post(
        RUN_URL, headers=headers,
        json={"spider_name": "example", "params": "{}"},
    )
    assert resp.status_code == 400, resp.text
    _assert_no_inner_code(resp)
    assert "平台租户" in resp.json()["message"]  # 中文可见句（非内码）
    assert _tasks_of(db_session, ptid) == []  # 不产生平台租户任务


def test_platform_tenant_missing_fails_loud(
    db_client, platform_admin_client, db_session, monkeypatch,
):
    """契约 §7/§8：平台租户种子行缺失 = 配置错误 → 入队失败可见（fail loud），
    不静默回退 None、不临时建租户、不产生无主任务。"""
    _seed_worker_redis(monkeypatch)  # 不种 platform 租户行

    resp = db_client.post(
        RUN_URL, json={"spider_name": "example", "params": "{}"},
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert "平台租户" in body["message"]
    _assert_no_inner_code(resp)
    assert _all_tasks(db_session) == []  # 零任务（含 NULL 归属）

    async def _no_fallback_tenant():
        async with db_session() as s:
            slugs = (await s.execute(select(Tenant.slug))).scalars().all()
            assert "platform" not in slugs  # 未临时建租户
    asyncio.run(_no_fallback_tenant())
