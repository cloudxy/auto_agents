"""A-P4-1 公开 API + T-23 FR-33 查询侧闸（技能端 /api/v1/public/skills）

Seam：db_client + db_session + 限流桩。技能与能力同一条 FR-33（PIT-5）。
"""
import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.services.power_market import (
    MARKET_NOT_FOUND_CODE,
    STORE_NOT_FOUND_COPY,
    STORE_NOT_FOUND_HOME,
    STORE_NOT_FOUND_HTML,
)
from backend.services.skill_service import SkillService
from backend.tests.fr33_support import (
    fr33_asset,
    gwt_33_2_rows,
    gwt_33_4_rows,
    gwt_33_5_rows,
    seed_rows,
)
from platform_core.models.capability import CapabilityAsset


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
    async def _go():
        async with db_session() as s:
            await SkillService(s).scan_library(root=library_root / "skills")
            rows = (await s.execute(select(CapabilityAsset))).scalars().all()
            for r in rows:
                if r.status in ("stable", "recommended"):
                    r.listing_state = "listed"
                    r.license = "MIT"
            await s.commit()

    asyncio.run(_go())


def test_public_list_only_published(db_client, db_engine, db_session, library_root, rate_redis):
    _seed_library(db_session, library_root)
    resp = db_client.get("/api/v1/public/skills")
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    names = {i["name"] for i in items}
    assert names == {"pub-stable", "pub-rec"}  # FR-33：已上架 ∩ 已发布/推荐 ∩ 许可


def test_public_fields_whitelist_enforced(db_client, db_engine, db_session, library_root, rate_redis):
    """白名单外字段（review_notes/sync_state/file_path/raw_meta）不得出现"""
    _seed_library(db_session, library_root)
    resp = db_client.get("/api/v1/public/skills/pub-stable")
    assert resp.status_code == 200
    data = resp.json()["data"]
    allowed = {
        "name", "title", "description", "category", "industries", "tier",
        "score", "status", "source_url", "source_author", "updated_at", "skill_md",
        "download_count",
        "asset_type", "listing_state", "license", "subscribable", "hosts", "includes",
    }
    assert set(data.keys()) <= allowed, f"越界字段: {set(data.keys()) - allowed}"


def test_public_unpublished_detail_404(db_client, db_engine, db_session, library_root, rate_redis):
    _seed_library(db_session, library_root)
    resp = db_client.get("/api/v1/public/skills/hidden-exp")
    assert resp.status_code == 404
    assert resp.content == STORE_NOT_FOUND_HTML.encode("utf-8")


def test_public_rate_limit_429(db_client, db_engine, db_session, library_root, rate_redis):
    """超 SKILLS.PUBLIC_API.RATE_LIMIT_PER_MIN 返回 429（桩计满 3 次）"""
    _seed_library(db_session, library_root)
    codes = [db_client.get("/api/v1/public/skills").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429 and codes[4] == 429


def test_gwt_32_1_listed_detail_subscribable(db_client, db_engine, db_session, rate_redis):
    seed_rows(db_session, [fr33_asset(name="listed-ok", title="已上架技能")])
    resp = db_client.get("/api/v1/public/skills/listed-ok")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["description"] == "说明"
    assert data["license"] == "MIT"
    assert data["source_url"] and data["source_author"]
    assert data["hosts"] == ["grok", "zcode", "kimi", "claude"]
    assert data["subscribable"] is True
    assert data["listing_state"] == "listed"


def test_gwt_32_2_coming_soon_no_subscribe_button(db_client, db_engine, db_session, rate_redis):
    seed_rows(db_session, [fr33_asset(name="soon-ok", listing_state="coming_soon")])
    resp = db_client.get("/api/v1/public/skills/soon-ok")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["listing_state"] == "coming_soon"
    assert data["subscribable"] is False
    assert "尚未上架" not in resp.text


def test_gwt_32_3_unlisted_html_matches_true_404(db_client, db_engine, db_session, rate_redis):
    seed_rows(db_session, [
        fr33_asset(name="unlisted-x", listing_state="unlisted"),
        fr33_asset(name="black-x", status="blacklist"),
    ])
    ghost = db_client.get("/api/v1/public/skills/never-existed-slug")
    unlisted = db_client.get("/api/v1/public/skills/unlisted-x")
    black = db_client.get("/api/v1/public/skills/black-x")
    assert ghost.status_code == unlisted.status_code == black.status_code == 404
    assert ghost.content == unlisted.content == black.content == STORE_NOT_FOUND_HTML.encode("utf-8")
    text = ghost.text
    assert STORE_NOT_FOUND_COPY in text and STORE_NOT_FOUND_HOME in text
    assert "已下架" not in text


def test_gwt_32_6_anonymous_subscribe_401(db_client, db_engine, db_session, rate_redis):
    seed_rows(db_session, [fr33_asset(name="listed-anon")])
    resp = db_client.post("/api/v1/public/skills/listed-anon/subscribe")
    assert resp.status_code == 401
    assert resp.json()["code"] != MARKET_NOT_FOUND_CODE


def test_gwt_32_7_login_bounce_no_install_row(
    db_client, db_engine, db_session, rate_redis,
):
    seed_rows(db_session, [fr33_asset(name="listed-bounce")])
    resp = db_client.post("/api/v1/public/skills/listed-bounce/subscribe")
    assert resp.status_code == 401
    from platform_core.models.capability import CapabilityInstall
    from sqlalchemy import func, select
    import asyncio

    async def _count():
        async with db_session() as s:
            return int((await s.execute(
                select(func.count()).select_from(CapabilityInstall).where(
                    CapabilityInstall.deleted_at.is_(None),
                )
            )).scalar_one())

    assert asyncio.run(_count()) == 0


def test_gwt_32_8_subscribe_unlisted_json_not_html(
    db_client, operator_client, db_engine, db_session, rate_redis,
):
    seed_rows(db_session, [
        fr33_asset(name="unlisted-sub", listing_state="unlisted"),
        fr33_asset(name="black-sub", status="blacklist"),
    ])
    ghost = db_client.post("/api/v1/public/skills/never-existed-slug/subscribe")
    unlisted = db_client.post("/api/v1/public/skills/unlisted-sub/subscribe")
    black = db_client.post("/api/v1/public/skills/black-sub/subscribe")
    for resp in (ghost, unlisted, black):
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == MARKET_NOT_FOUND_CODE
        assert body["success"] is False
        assert "已下架" not in resp.text
        assert "text/html" not in resp.headers.get("content-type", "")
        assert STORE_NOT_FOUND_COPY not in resp.text
    assert ghost.json()["code"] == unlisted.json()["code"] == black.json()["code"]
    assert ghost.json()["message"] == unlisted.json()["message"] == black.json()["message"]


def test_gwt_33_2_six_row_fixture(db_client, db_engine, db_session, rate_redis):
    seed_rows(db_session, gwt_33_2_rows())
    resp = db_client.get("/api/v1/public/skills")
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]["items"]
    names = {i["name"] for i in items}
    assert names == {"g332-soon", "g332-rec"}
    by_name = {i["name"]: i for i in items}
    assert by_name["g332-soon"]["subscribable"] is False
    assert by_name["g332-rec"]["subscribable"] is True


def test_gwt_33_3_blacklist_store_not_found(db_client, db_engine, db_session, rate_redis):
    seed_rows(db_session, [fr33_asset(name="listed-black", status="blacklist")])
    resp = db_client.get("/api/v1/public/skills/listed-black")
    assert resp.status_code == 404
    assert resp.content == STORE_NOT_FOUND_HTML.encode("utf-8")


def test_gwt_33_4_page2_empty_total_visible_only(db_client, db_engine, db_session, rate_redis):
    seed_rows(db_session, gwt_33_4_rows(page_size=20))
    page1 = db_client.get("/api/v1/public/skills", params={"page": 1, "page_size": 20})
    page2 = db_client.get("/api/v1/public/skills", params={"page": 2, "page_size": 20})
    d1, d2 = page1.json()["data"], page2.json()["data"]
    assert d1["total"] == d2["total"] == 20
    assert len(d1["items"]) == 20
    assert all(n.startswith("g334-vis-") for n in (i["name"] for i in d1["items"]))
    assert d2["items"] == []
    assert d2["has_more"] is False


def test_gwt_33_5_page2_only_gated_rows(db_client, db_engine, db_session, rate_redis):
    seed_rows(db_session, gwt_33_5_rows(page_size=20, extra=5))
    page1 = db_client.get("/api/v1/public/skills", params={"page": 1, "page_size": 20})
    page2 = db_client.get("/api/v1/public/skills", params={"page": 2, "page_size": 20})
    d1, d2 = page1.json()["data"], page2.json()["data"]
    assert d1["total"] == d2["total"] == 25
    assert d1["has_more"] is True
    assert len(d2["items"]) == 5
    names = [i["name"] for i in d2["items"]]
    assert all(n.startswith("g335-vis-") for n in names)
    assert not any(x in "".join(names) for x in ("unlist", "black", "nolic", "exp", "test", "dep"))


def test_public_page_size_max_50(db_client, db_engine, db_session, rate_redis):
    resp = db_client.get("/api/v1/public/skills", params={"page_size": 51})
    assert resp.status_code == 422
