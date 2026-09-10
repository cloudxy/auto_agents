"""A-P5-2 候选审核 API 验证（工单 29）

Seam（工单预确认）：/api/v1/skills/candidates* 端点（import_url 管线以桩替身，
管线本身已由工单 16 覆盖——seam 分离）。
"""
import json

import pytest
from sqlalchemy import select

from platform_core.models.skill import Skill
from platform_core.models.spider_result import SpiderResult


async def _seed(db_session) -> None:
    rows = [
        SpiderResult(
            task_id=1, spider_name="skill_harvester", item_type="BaseItem",
            url="https://github.com/anthropics/skills/tree/main/skills/pdf-briefing",
            title="pdf-briefing", content="PDF 简报", source="marketplace",
            extra=json.dumps({"repo": "anthropics/skills", "kind": "github_dir"}),
        ),
        SpiderResult(
            task_id=1, spider_name="skill_harvester", item_type="BaseItem",
            url="https://github.com/x/awesome-skill", title="awesome-skill",
            content="清单候选", source="marketplace",
            extra=json.dumps({"repo": "x/awesome-skill", "kind": "awesome_link"}),
        ),
        SpiderResult(
            task_id=1, spider_name="example", item_type="BaseItem",
            url="https://other", title="无关结果", source="web",
        ),
    ]
    async with db_session() as s:
        s.add_all(rows)
        await s.commit()


def test_candidates_list_filters_marketplace(
    db_client, platform_admin_client, db_engine, db_session,
):
    import asyncio

    asyncio.run(_seed(db_session))
    resp = db_client.get("/api/v1/skills/candidates")
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert {i["title"] for i in items} == {"pdf-briefing", "awesome-skill"}  # 只见 marketplace
    assert items[0]["review_status"] == "pending"


def test_approve_walks_import_pipeline_and_marks(
    db_client, platform_admin_client, db_engine, db_session, monkeypatch,
):
    import asyncio

    asyncio.run(_seed(db_session))
    result_id = 1

    def _init(self, session):
        self.session = session

    received: dict = {}

    async def _fake_import(self, url, category=None, industries=None, client=None, *, commit=True):
        # ADR-0007 D3：组合调用必须以 commit=False 交出事务权——
        # 导入 + 候选标记由 approve_candidate 尾部一个事务统一提交
        received["commit"] = commit
        return {"name": "pdf-briefing", "imported": True, "file_count": 3, "similar_candidates": []}

    monkeypatch.setattr(
        "backend.services.skill_import_service.SkillImportService",
        type("S", (), {"__init__": _init, "import_url": _fake_import}),
    )

    resp = db_client.post(f"/api/v1/skills/candidates/{result_id}/approve")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["imported"] is True

    async def _check():
        async with db_session() as s:
            row = (await s.execute(select(SpiderResult).where(SpiderResult.id == result_id))).scalar_one()
            return json.loads(row.extra or "{}")

    assert asyncio.run(_check()).get("review") == "approved"
    assert received.get("commit") is False  # ADR-0007 D3：组合调用不吞事务权
    # 已处理候选默认不再出现在待审列表
    again = db_client.get("/api/v1/skills/candidates").json()["data"]["items"]
    assert all(i["id"] != result_id for i in again)


def test_reject_marks_and_blacklists_existing(
    db_client, platform_admin_client, db_engine, db_session,
):
    import asyncio

    asyncio.run(_seed(db_session))

    async def _add_existing():
        async with db_session() as s:
            s.add(Skill(name="awesome-skill", file_path="skills/awesome-skill",
                        status="experimental", source_url="https://github.com/x/awesome-skill"))
            await s.commit()

    asyncio.run(_add_existing())

    resp = db_client.post("/api/v1/skills/candidates/2/reject")
    assert resp.status_code == 200

    async def _check():
        async with db_session() as s:
            result = (await s.execute(select(SpiderResult).where(SpiderResult.id == 2))).scalar_one()
            skill = (await s.execute(select(Skill).where(Skill.name == "awesome-skill"))).scalar_one()
            return json.loads(result.extra or "{}"), skill.status

    extra, status = asyncio.run(_check())
    assert extra.get("review") == "rejected"
    assert status == "blacklist"  # 已入库同名技能 → 拉黑防重复


def test_tenant_operator_candidates_same_as_missing(
    db_client, operator_client, db_session,
):
    """GWT-11.3：租户经办打开候选审核 → 与不存在同形；审核仅超管"""
    import asyncio

    asyncio.run(_seed(db_session))
    listed = db_client.get("/api/v1/skills/candidates")
    assert listed.status_code == 404
    assert listed.json()["code"] == "HTTP_404"
    assert listed.json()["data"] == {}
    approve = db_client.post("/api/v1/skills/candidates/1/approve")
    assert approve.status_code == 404
    assert approve.json()["code"] == "HTTP_404"
    reject = db_client.post("/api/v1/skills/candidates/2/reject")
    assert reject.status_code == 404
    assert reject.json()["code"] == "HTTP_404"


def test_tenant_admin_candidates_same_as_missing(db_client, admin_client, db_session):
    """GWT-11.3：租户公司管理员直打开候选审核，亦 404 同形（审核仅超管）"""
    import asyncio

    asyncio.run(_seed(db_session))
    listed = db_client.get("/api/v1/skills/candidates")
    assert listed.status_code == 404
    assert listed.json()["code"] == "HTTP_404"


def test_superadmin_candidates_sql_pagination(
    db_client, platform_admin_client, db_session,
):
    """超管候选列表 SQL 分页：page_size 窗外行不进本页；已审不计入 total"""
    import asyncio

    async def _seed_pages() -> None:
        rows = [
            SpiderResult(
                task_id=1, spider_name="skill_harvester", item_type="BaseItem",
                url=f"https://github.com/x/skill-{i}", title=f"skill-{i:02d}",
                content="c", source="marketplace",
            )
            for i in range(25)
        ]
        rows.append(SpiderResult(
            task_id=1, spider_name="skill_harvester", item_type="BaseItem",
            url="https://github.com/x/done", title="already-approved",
            content="c", source="marketplace",
            extra=json.dumps({"review": "approved"}),
        ))
        rows.append(SpiderResult(
            task_id=1, spider_name="example", item_type="BaseItem",
            url="https://own.example/row", title="owned-row", source="web",
        ))
        async with db_session() as s:
            s.add_all(rows)
            await s.commit()

    asyncio.run(_seed_pages())
    page1 = db_client.get("/api/v1/skills/candidates", params={"page": 1, "page_size": 20})
    assert page1.status_code == 200, page1.text
    body1 = page1.json()["data"]
    assert body1["total"] == 25
    assert len(body1["items"]) == 20
    titles1 = [i["title"] for i in body1["items"]]
    assert "already-approved" not in titles1
    assert "owned-row" not in titles1

    page2 = db_client.get("/api/v1/skills/candidates", params={"page": 2, "page_size": 20})
    assert page2.status_code == 200, page2.text
    body2 = page2.json()["data"]
    assert body2["total"] == 25
    assert len(body2["items"]) == 5
    overlap = {i["id"] for i in body1["items"]} & {i["id"] for i in body2["items"]}
    assert overlap == set()


@pytest.mark.asyncio
async def test_storage_quota_ignores_marketplace_at_ninety_percent(db_session, monkeypatch):
    """GWT-11.1：存储 90% + 候选行，未超非候选上限 → 不被候选顶满而拒绝"""
    from backend.services import quota_service as qs
    from backend.services.quota_service import QuotaService
    from platform_core.models.tenant import Tenant

    def _no_redis():
        raise RuntimeError("quota count must hit SQL")

    monkeypatch.setattr(qs, "get_async_redis", _no_redis)

    async with db_session() as s:
        t = Tenant(slug="q-mkt-90", name="Q", quota={"result_storage": 10})
        s.add(t)
        await s.flush()
        tid = int(t.id)
        own = [
            SpiderResult(
                task_id=1, spider_name="x", url=f"https://own/{i}",
                tenant_id=tid, source="web",
            )
            for i in range(9)
        ]
        cands = [
            SpiderResult(
                task_id=1, spider_name="skill_harvester",
                url=f"https://mkt/{i}", tenant_id=tid, source="marketplace",
            )
            for i in range(20)
        ]
        s.add_all(own + cands)
        await s.commit()

    async with db_session() as s:
        await QuotaService(s).check_result_storage(tid)
