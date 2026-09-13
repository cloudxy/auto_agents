"""T-13（FR-80）：公开商店/精选过滤测试种子——PIT-5 双公开端同 PR

GWT-80.1..80.4 两公开端各一份：
- /api/v1/public/skills（官网能力市场「技能」+ 首页能力精选数据源，同一读模型）
- /api/v1/public/capabilities（官网能力市场「全部」，五类枚举）

种子谓词（与 GWT-80.1 同口径）：
短名 nfr01qc2-*（大小写不敏感）∨ 标题以「NFR卡片」开头 ∨ 描述含 preprod nfr-01 seed。
列表/精选/total/详情/订阅 都不含种子；谓词收在读模型层，翻成 listed 也不外泄。
GWT-80.2 后端行为 = 0 结果正常返回空列表（空态句由前端既有文案承接）。
"""
import asyncio

import pytest
from sqlalchemy import select

from backend.services.power_market import (
    MARKET_NOT_FOUND_CODE,
    STORE_NOT_FOUND_HTML,
)
from backend.tests.fr33_support import fr33_asset, seed_rows
from platform_core.models.capability import CapabilityAsset

SKILLS_LIST = "/api/v1/public/skills"
CAPABILITIES_LIST = "/api/v1/public/capabilities"


class _RateLimitRedis:
    """限流桩：incr+expire 计数（与 test_skill_public_api 同口径）"""

    def __init__(self):
        self.counts: dict[str, int] = {}

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, ttl):
        return True


@pytest.fixture
def rate_redis(monkeypatch):
    fake = _RateLimitRedis()

    async def _fake(key: str = "DEFAULT"):
        return fake

    import backend.app.api.v1.public_skills as mod

    monkeypatch.setattr(mod, "get_async_redis", _fake)
    return fake


def _seed_rows(db_session, rows: list) -> None:
    seed_rows(db_session, rows)


def _flip_listed(db_session, name: str) -> None:
    """把已存在行翻成 listed（模拟租户/任意路径把种子改成对访客可见的上架）。"""

    async def _go():
        async with db_session() as s:
            row = (await s.execute(
                select(CapabilityAsset).where(CapabilityAsset.name == name)
            )).scalar_one()
            row.listing_state = "listed"
            await s.commit()

    asyncio.run(_go())


def _seed_variants() -> list[CapabilityAsset]:
    """三支谓词各一行 + 大小写行 + 一张正常对照卡（均已上架/已发布/许可过闸）。"""
    return [
        fr33_asset(name="nfr01qc2-399", title="普通标题"),
        fr33_asset(name="title-seed-01", title="NFR卡片399"),
        fr33_asset(name="desc-seed-01", description="功能说明，preprod nfr-01 seed 数据"),
        fr33_asset(name="NFR01QC2-401", title="大小写"),
        fr33_asset(name="plain-card", title="正常卡"),
    ]


# ---------- GWT-80.1：列表/精选/total 不含种子（技能端） ----------


def test_gwt_80_1_skills_list_excludes_seeds(db_client, db_engine, db_session, rate_redis):
    _seed_rows(db_session, _seed_variants())
    resp = db_client.get(SKILLS_LIST)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    names = {i["name"] for i in data["items"]}
    assert names == {"plain-card"}  # 三支谓词 + 大小写全被滤掉
    assert data["total"] == 1


def test_gwt_80_1_skills_featured_shape_excludes_seeds(
    db_client, db_engine, db_session, rate_redis,
):
    """首页能力精选数据源 = 同一 /public/skills 列表调用。

    T-14 后精选请求形态 page_size=20（公开 MAX 收到 20；精选非翻页列表，≤20 即可）。
    """
    _seed_rows(db_session, _seed_variants())
    resp = db_client.get(SKILLS_LIST, params={"page": 1, "page_size": 20})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert {i["name"] for i in data["items"]} == {"plain-card"}
    assert data["total"] == 1


# ---------- GWT-80.1：能力市场「全部」与类型筛（能力端） ----------


def test_gwt_80_1_capabilities_list_excludes_seeds(
    db_client, db_engine, db_session, rate_redis,
):
    _seed_rows(db_session, _seed_variants() + [
        fr33_asset(asset_type="plugin", name="nfr01qc2-plugin-seed", title="插件种子"),
    ])
    resp = db_client.get(CAPABILITIES_LIST)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert {i["name"] for i in data["items"]} == {"plain-card"}  # 谓词不分资产类型
    assert data["total"] == 1
    by_type = db_client.get(CAPABILITIES_LIST, params={"type": "plugin"})
    assert by_type.status_code == 200, by_type.text
    assert by_type.json()["data"]["total"] == 0
    assert by_type.json()["data"]["items"] == []


# ---------- GWT-80.2：清种子后 0 结果 = 正常空列表（不是失败） ----------


def test_gwt_80_2_skills_empty_after_seed_filter(
    db_client, db_engine, db_session, rate_redis,
):
    _seed_rows(db_session, [fr33_asset(name="nfr01qc2-399", title="普通标题")])
    resp = db_client.get(SKILLS_LIST)
    assert resp.status_code == 200, resp.text  # 正常成功，不是失败句
    data = resp.json()["data"]
    assert data["total"] == 0
    assert data["items"] == []
    assert data["has_more"] is False


def test_gwt_80_2_capabilities_type_empty_after_seed_filter(
    db_client, db_engine, db_session, rate_redis,
):
    _seed_rows(db_session, [
        fr33_asset(asset_type="plugin", name="nfr01qc2-plugin-seed", title="插件种子"),
    ])
    resp = db_client.get(CAPABILITIES_LIST, params={"type": "plugin"})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 0
    assert data["items"] == []
    assert data["has_more"] is False


# ---------- GWT-80.3：种子翻成 listed 仍不出现（两公开端） ----------


def test_gwt_80_3_seed_flipped_listed_still_hidden_skills(
    db_client, db_engine, db_session, rate_redis,
):
    _seed_rows(db_session, [fr33_asset(
        name="nfr01qc2-flip", title="普通标题", listing_state="unlisted",
    )])
    _flip_listed(db_session, "nfr01qc2-flip")  # 改成对访客可见的上架
    resp = db_client.get(SKILLS_LIST)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["total"] == 0
    assert resp.json()["data"]["items"] == []
    detail = db_client.get(f"{SKILLS_LIST}/nfr01qc2-flip")
    assert detail.status_code == 404
    assert detail.content == STORE_NOT_FOUND_HTML.encode("utf-8")  # 与真 404 同形


def test_gwt_80_3_seed_flipped_listed_still_hidden_capabilities(
    db_client, operator_client, db_engine, db_session, rate_redis,
):
    _seed_rows(db_session, [fr33_asset(
        name="nfr01qc2-flip", title="普通标题", listing_state="unlisted",
    )])
    _flip_listed(db_session, "nfr01qc2-flip")
    resp = db_client.get(CAPABILITIES_LIST)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["total"] == 0
    assert resp.json()["data"]["items"] == []
    detail = db_client.get(f"{CAPABILITIES_LIST}/skill/nfr01qc2-flip")
    assert detail.status_code == 404
    assert detail.content == STORE_NOT_FOUND_HTML.encode("utf-8")
    sub = operator_client.post(f"{CAPABILITIES_LIST}/skill/nfr01qc2-flip/subscribe")
    assert sub.status_code == 404
    assert sub.json()["code"] == MARKET_NOT_FOUND_CODE  # 订阅也不放行种子


# ---------- GWT-80.4：清污染后夹具仍可被搜到（两公开端） ----------


def _pdf_contrast_rows() -> list[CapabilityAsset]:
    """夹具 example-pdf-extractor（非种子已上架）+ 会命中 q=pdf 的种子。"""
    return [
        fr33_asset(name="example-pdf-extractor", title="PDF 提取器",
                   description="提取 PDF 文本与表格"),
        fr33_asset(name="nfr01qc2-pdf-sampler", title="NFR卡片-pdf样例",
                   description="preprod nfr-01 seed"),
    ]


def test_gwt_80_4_fixture_searchable_skills(db_client, db_engine, db_session, rate_redis):
    _seed_rows(db_session, _pdf_contrast_rows())
    resp = db_client.get(SKILLS_LIST, params={"q": "pdf"})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert {i["name"] for i in data["items"]} == {"example-pdf-extractor"}
    assert data["total"] == 1  # 对照成立：夹具在，种子不在


def test_gwt_80_4_fixture_searchable_capabilities(
    db_client, db_engine, db_session, rate_redis,
):
    _seed_rows(db_session, _pdf_contrast_rows())
    resp = db_client.get(CAPABILITIES_LIST, params={"q": "pdf"})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert {i["name"] for i in data["items"]} == {"example-pdf-extractor"}
    assert data["total"] == 1
