"""A-P5-2 候选审核 API 验证（工单 29）

Seam（工单预确认）：/api/v1/skills/candidates* 端点（import_url 管线以桩替身，
管线本身已由工单 16 覆盖——seam 分离）。
"""
import json

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


def test_candidates_list_filters_marketplace(db_client, db_engine, db_session):
    import asyncio

    asyncio.run(_seed(db_session))
    resp = db_client.get("/api/v1/skills/candidates")
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert {i["title"] for i in items} == {"pdf-briefing", "awesome-skill"}  # 只见 marketplace
    assert items[0]["review_status"] == "pending"


def test_approve_walks_import_pipeline_and_marks(db_client, db_engine, db_session, monkeypatch):
    import asyncio

    asyncio.run(_seed(db_session))
    result_id = 1

    def _init(self, session):
        self.session = session

    async def _fake_import(self, url, category=None, industries=None, client=None):
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
    # 已处理候选默认不再出现在待审列表
    again = db_client.get("/api/v1/skills/candidates").json()["data"]["items"]
    assert all(i["id"] != result_id for i in again)


def test_reject_marks_and_blacklists_existing(db_client, db_engine, db_session):
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
