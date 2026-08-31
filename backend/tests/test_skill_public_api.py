"""A-P4-1 公开 API 三道闸验证（工单 18）：仅发布态 / 字段白名单 / 按 IP 限流

Seam（工单预确认）：/api/v1/public/skills 端点（db_client + db_session + 限流桩）。
"""
from pathlib import Path

import pytest

from backend.services.skill_service import SkillService


def _make_skill(root: Path, name: str, status: str) -> None:
    d = root / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: d\n---\n# {name}\n")
    (d / "meta.yaml").write_text(
        f"name: {name}\ncategory: dev-tools\nstatus: {status}\nsimilar_to: []\n"
    )


@pytest.fixture
def library_root(tmp_path):
    from config import settings

    original = settings.get("SKILLS.LIBRARY_ROOT")
    original_limit = settings.get("SKILLS.PUBLIC_API.RATE_LIMIT_PER_MIN")
    settings.set("SKILLS.LIBRARY_ROOT", str(tmp_path))
    settings.set("SKILLS.PUBLIC_API.RATE_LIMIT_PER_MIN", 3)
    _make_skill(tmp_path, "pub-stable", "stable")
    _make_skill(tmp_path, "pub-rec", "recommended")
    _make_skill(tmp_path, "hidden-exp", "experimental")
    _make_skill(tmp_path, "hidden-dep", "deprecated")
    yield tmp_path
    settings.set("SKILLS.LIBRARY_ROOT", original)
    settings.set("SKILLS.PUBLIC_API.RATE_LIMIT_PER_MIN", original_limit)


class _RateLimitRedis:
    """限流桩：incr+expire 原子计数"""

    def __init__(self):
        self.counts: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, ttl):
        self.ttls[key] = ttl
        return True


@pytest.fixture
def rate_redis(monkeypatch):
    fake = _RateLimitRedis()
    async def _fake(key: str = "DEFAULT"):
        return fake
    import backend.app.api.v1.public_skills as mod

    monkeypatch.setattr(mod, "get_async_redis", _fake)
    return fake


def _seed_library(db_session, library_root):
    import asyncio

    async def _go():
        async with db_session() as s:
            await SkillService(s).scan_library(root=library_root / "skills")
            await s.commit()

    asyncio.run(_go())


def test_public_list_only_published(db_client, db_engine, db_session, library_root, rate_redis):
    _seed_library(db_session, library_root)
    resp = db_client.get("/api/v1/public/skills")
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    names = {i["name"] for i in items}
    assert names == {"pub-stable", "pub-rec"}  # 发布态白名单


def test_public_fields_whitelist_enforced(db_client, db_engine, db_session, library_root, rate_redis):
    """白名单外字段（review_notes/sync_state/file_path/raw_meta/score 内部语义）不得出现"""
    _seed_library(db_session, library_root)
    resp = db_client.get("/api/v1/public/skills/pub-stable")
    assert resp.status_code == 200
    data = resp.json()["data"]
    allowed = {
        "name", "title", "description", "category", "industries", "tier",
        "score", "status", "source_url", "source_author", "updated_at", "skill_md",
    }
    assert set(data.keys()) <= allowed, f"越界字段: {set(data.keys()) - allowed}"


def test_public_unpublished_detail_404(db_client, db_engine, db_session, library_root, rate_redis):
    _seed_library(db_session, library_root)
    resp = db_client.get("/api/v1/public/skills/hidden-exp")
    assert resp.status_code == 404


def test_public_rate_limit_429(db_client, db_engine, db_session, library_root, rate_redis):
    """超 SKILLS.PUBLIC_API.RATE_LIMIT_PER_MIN 返回 429（桩计满 3 次）"""
    _seed_library(db_session, library_root)
    codes = [db_client.get("/api/v1/public/skills").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429 and codes[4] == 429
