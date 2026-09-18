"""T-06 / FR-04：货架三档排序 + 精选/示例治理端点（contract AD-6/AD-7）。

GWT 锚：04.1（综合=精选置顶 + updated_at 次序）、04.2（最新）、04.3（最热有数据）、
04.4（最热全零降级 smart 且页面无计数数字）、04.5（精选治理即时生效）、
04.6（越权 404 存在性隐藏）+ 附加 d 示例端点（上限 422 / 空列表取消维护）。

隔离手法：每个用例用独立 category 过滤（_apply_list_filters 支持），避免与其它
用例种子互相污染；updated_at 显式赋值（server_default 仅在缺省时生效）。
"""
from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from sqlalchemy import select

from backend.tests.fr33_support import fr33_asset, seed_rows
from backend.tests.t25_support import seed_tenant
from conftest import make_platform_admin_headers, make_tenant_owner_headers
from platform_core.models.capability import CapabilityAsset, CapabilityInstall

PUBLIC = "/api/v1/public/capabilities"
FEATURED = "/api/v1/capabilities/skill/{}/featured"
EXAMPLES = "/api/v1/capabilities/skill/{}/examples"


class _RateRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, ttl):
        return True


@pytest.fixture(autouse=True)
def _rate(monkeypatch):
    fake = _RateRedis()

    async def _fake(key: str = "DEFAULT"):
        return fake

    import backend.app.api.v1.public_skills as pub
    monkeypatch.setattr(pub, "get_async_redis", _fake)
    return fake


def _at(day: int) -> datetime:
    return datetime(2026, 1, day, 12, 0, 0)


def _seed(db_session, cat: str, rows: list[dict]) -> None:
    seed_rows(db_session, [fr33_asset(category=cat, **r) for r in rows])


def _names(resp) -> list[str]:
    assert resp.status_code == 200, resp.text
    return [i["name"] for i in resp.json()["data"]["items"]]


def _install(db_session, name: str, tenant_id: int, hosts: list[str]) -> None:
    async def _go():
        async with db_session() as s:
            asset_id = (await s.execute(
                select(CapabilityAsset.id).where(CapabilityAsset.name == name)
            )).scalar_one()
            for host in hosts:
                s.add(CapabilityInstall(
                    tenant_id=tenant_id, asset_id=int(asset_id), host=host,
                    enabled=1, trusted=0,
                ))
            await s.commit()

    asyncio.run(_go())


# --- GWT-04.1 综合 -----------------------------------------------------------

def test_gwt_04_1_smart_features_first_then_updated_at(db_client, db_session):
    """精选区内部仍按 updated_at 倒序；未精选区整体排在精选区之后。"""
    _seed(db_session, "srt-1", [
        {"name": "s1-a", "featured": 1, "updated_at": _at(1)},
        {"name": "s1-b", "featured": 1, "updated_at": _at(3)},
        {"name": "s1-c", "featured": 0, "updated_at": _at(5)},
        {"name": "s1-d", "featured": 0, "updated_at": _at(2)},
    ])
    got = db_client.get(PUBLIC, params={"category": "srt-1", "sort": "smart"})
    assert _names(got) == ["s1-b", "s1-a", "s1-c", "s1-d"]
    assert got.json()["data"]["sort_applied"] == "smart"


def test_smart_is_default_when_sort_absent_or_invalid(db_client, db_session):
    """缺省与非法档都回落 smart（契约 §4 只对非法 type 约定 422）。"""
    _seed(db_session, "srt-1d", [
        {"name": "s1d-a", "featured": 0, "updated_at": _at(9)},
        {"name": "s1d-b", "featured": 1, "updated_at": _at(1)},
    ])
    bare = db_client.get(PUBLIC, params={"category": "srt-1d"})
    junk = db_client.get(PUBLIC, params={"category": "srt-1d", "sort": "no-such"})
    assert _names(bare) == _names(junk) == ["s1d-b", "s1d-a"]
    assert bare.json()["data"]["sort_applied"] == "smart"
    assert junk.json()["data"]["sort_applied"] == "smart"


# --- GWT-04.2 最新 -----------------------------------------------------------

def test_gwt_04_2_latest_ignores_featured(db_client, db_session):
    """最新档纯 updated_at 倒序——精选不得插队。"""
    _seed(db_session, "srt-2", [
        {"name": "s2-old-featured", "featured": 1, "updated_at": _at(1)},
        {"name": "s2-new-plain", "featured": 0, "updated_at": _at(7)},
    ])
    got = db_client.get(PUBLIC, params={"category": "srt-2", "sort": "latest"})
    assert _names(got) == ["s2-new-plain", "s2-old-featured"]
    assert got.json()["data"]["sort_applied"] == "latest"


# --- GWT-04.3 最热（有数据）--------------------------------------------------

def test_gwt_04_3_hot_orders_by_install_count(db_client, db_session):
    """订阅多者在前；计数并列按 updated_at 倒序；零计数左联归零排尾。"""
    tid = seed_tenant(db_session, slug="srt-3-co")
    _seed(db_session, "srt-3", [
        {"name": "s3-hi", "updated_at": _at(1)},
        {"name": "s3-mid-old", "updated_at": _at(2)},
        {"name": "s3-mid-new", "updated_at": _at(6)},
        {"name": "s3-zero", "updated_at": _at(8)},
    ])
    _install(db_session, "s3-hi", tid, ["grok", "zcode", "kimi"])
    _install(db_session, "s3-mid-old", tid, ["grok"])
    _install(db_session, "s3-mid-new", tid, ["grok"])
    got = db_client.get(PUBLIC, params={"category": "srt-3", "sort": "hot"})
    assert _names(got) == ["s3-hi", "s3-mid-new", "s3-mid-old", "s3-zero"]
    assert got.json()["data"]["sort_applied"] == "hot"


def test_hot_ignores_soft_deleted_installs(db_client, db_session):
    """软删订阅不计入热度（alive 谓词）。"""
    tid = seed_tenant(db_session, slug="srt-3b-co")
    _seed(db_session, "srt-3b", [
        {"name": "s3b-live", "updated_at": _at(1)},
        {"name": "s3b-dead", "updated_at": _at(2)},
    ])
    _install(db_session, "s3b-live", tid, ["grok"])
    _install(db_session, "s3b-dead", tid, ["grok", "zcode"])

    async def _soft_delete():
        async with db_session() as s:
            asset_id = (await s.execute(
                select(CapabilityAsset.id).where(CapabilityAsset.name == "s3b-dead")
            )).scalar_one()
            rows = (await s.execute(
                select(CapabilityInstall).where(CapabilityInstall.asset_id == asset_id)
            )).scalars().all()
            for row in rows:
                row.deleted_at = datetime(2026, 2, 1, 0, 0, 0)
            await s.commit()

    asyncio.run(_soft_delete())
    got = db_client.get(PUBLIC, params={"category": "srt-3b", "sort": "hot"})
    assert _names(got) == ["s3b-live", "s3b-dead"]


# --- GWT-04.4 最热降级 -------------------------------------------------------

def test_gwt_04_4_hot_degrades_to_smart_without_counts(db_client, db_session):
    """全库零订阅 → 序同 smart、sort_applied=smart、payload 不带任何计数字段。"""
    _seed(db_session, "srt-4", [
        {"name": "s4-plain", "featured": 0, "updated_at": _at(9)},
        {"name": "s4-featured", "featured": 1, "updated_at": _at(1)},
    ])
    hot = db_client.get(PUBLIC, params={"category": "srt-4", "sort": "hot"})
    smart = db_client.get(PUBLIC, params={"category": "srt-4", "sort": "smart"})
    assert _names(hot) == _names(smart) == ["s4-featured", "s4-plain"]
    assert hot.json()["data"]["sort_applied"] == "smart"
    for item in hot.json()["data"]["items"]:
        leaked = {k for k in item if "count" in k or "install" in k or k == "cnt"}
        assert not leaked, f"降级态外发计数字段: {leaked}"


# --- GWT-04.5 精选治理 -------------------------------------------------------

def test_gwt_04_5_featured_patch_moves_asset_to_top(db_client, db_session):
    """置顶区/未精选区是两段；取消精选后必须退回后一段。

    注意：PATCH 会触发 updated_at onupdate 跳到 now，被操作行因此成为「最新」——
    所以「回到未精选区」只能对着**已有精选行 s5-anchor** 断言相对位置，
    不能断言它不在列表首位（dba OQ1 已接受 updated_at 跳档，无 GWT 反例）。
    """
    admin = make_platform_admin_headers(db_session)
    _seed(db_session, "srt-5", [
        {"name": "s5-anchor", "featured": 1, "updated_at": _at(1)},
        {"name": "s5-a", "featured": 0, "updated_at": _at(9)},
        {"name": "s5-b", "featured": 0, "updated_at": _at(2)},
    ])
    before = db_client.get(PUBLIC, params={"category": "srt-5", "sort": "smart"})
    assert _names(before) == ["s5-anchor", "s5-a", "s5-b"]

    on = db_client.patch(FEATURED.format("s5-b"), headers=admin, json={"featured": True})
    assert on.status_code == 200, on.text
    assert on.json()["data"]["featured"] == 1
    after = db_client.get(PUBLIC, params={"category": "srt-5", "sort": "smart"})
    assert _names(after)[0] == "s5-b"  # 进置顶区且是区内最新
    assert after.json()["data"]["items"][0]["featured"] == 1
    assert _names(after).index("s5-b") < _names(after).index("s5-anchor")

    off = db_client.patch(FEATURED.format("s5-b"), headers=admin, json={"featured": False})
    assert off.status_code == 200, off.text
    assert off.json()["data"]["featured"] == 0
    back = _names(db_client.get(PUBLIC, params={"category": "srt-5", "sort": "smart"}))
    assert back[0] == "s5-anchor"                       # 置顶区只剩 anchor
    assert back.index("s5-anchor") < back.index("s5-b")  # s5-b 退回未精选区


def test_featured_patch_unknown_asset_404(db_client, db_session):
    admin = make_platform_admin_headers(db_session)
    got = db_client.patch(FEATURED.format("no-such-asset"), headers=admin,
                          json={"featured": True})
    assert got.status_code == 404, got.text


# --- GWT-04.6 越权 -----------------------------------------------------------

def test_gwt_04_6_non_admin_featured_patch_404_and_no_change(db_client, db_session):
    owner, _tid = make_tenant_owner_headers(db_session, slug="srt-6-co")
    _seed(db_session, "srt-6", [{"name": "s6-a", "featured": 0, "updated_at": _at(1)}])
    got = db_client.patch(FEATURED.format("s6-a"), headers=owner, json={"featured": True})
    assert got.status_code == 404, got.text
    assert got.json()["code"] == "HTTP_404"
    assert "抱歉您没有权限" not in got.text

    async def _read():
        async with db_session() as s:
            return (await s.execute(
                select(CapabilityAsset.featured).where(CapabilityAsset.name == "s6-a")
            )).scalar_one()

    assert int(asyncio.run(_read()) or 0) == 0


def test_non_admin_examples_patch_404(db_client, db_session):
    owner, _tid = make_tenant_owner_headers(db_session, slug="srt-6b-co")
    _seed(db_session, "srt-6b", [{"name": "s6b-a", "updated_at": _at(1)}])
    got = db_client.patch(EXAMPLES.format("s6b-a"), headers=owner,
                          json={"examples": ["越权不得写入"]})
    assert got.status_code == 404, got.text


# --- 附加 d：示例区端点 ------------------------------------------------------

def test_examples_roundtrip_and_empty_clears(db_client, db_session):
    admin = make_platform_admin_headers(db_session)
    _seed(db_session, "srt-7", [{"name": "s7-a", "updated_at": _at(1)}])
    saved = db_client.patch(EXAMPLES.format("s7-a"), headers=admin,
                            json={"examples": ["帮我写周报", "  ", "总结这份 PDF"]})
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["examples"] == ["帮我写周报", "总结这份 PDF"]

    detail = db_client.get(f"{PUBLIC}/skill/s7-a")
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["examples"] == ["帮我写周报", "总结这份 PDF"]

    cleared = db_client.patch(EXAMPLES.format("s7-a"), headers=admin, json={"examples": []})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["data"]["examples"] == []
    assert db_client.get(f"{PUBLIC}/skill/s7-a").json()["data"]["examples"] == []


def test_examples_over_limits_422(db_client, db_session):
    admin = make_platform_admin_headers(db_session)
    _seed(db_session, "srt-8", [{"name": "s8-a", "updated_at": _at(1)}])
    too_many = db_client.patch(EXAMPLES.format("s8-a"), headers=admin,
                               json={"examples": [f"e{i}" for i in range(21)]})
    assert too_many.status_code == 422, too_many.text
    too_long = db_client.patch(EXAMPLES.format("s8-a"), headers=admin,
                               json={"examples": ["x" * 201]})
    assert too_long.status_code == 422, too_long.text

    async def _read():
        async with db_session() as s:
            return (await s.execute(
                select(CapabilityAsset.examples).where(CapabilityAsset.name == "s8-a")
            )).scalar_one()

    assert not (asyncio.run(_read()) or [])
