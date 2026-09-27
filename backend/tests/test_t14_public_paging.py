"""T-14（FR-81 + FR-92.5）：公开列表页大小 ≤20 + 夹具第 21 张 + 翻页事件。

GWT-81.1..81.4 / GWT-92.5，双公开端（/public/skills 与 /public/capabilities）。
夹具 = fr33_asset 资产行（T-23 既有夹具原语），禁止为翻页造商店模型/改种子。
"""
import asyncio

import pytest
from sqlalchemy import select

from backend.tests.fr33_support import fr33_asset, seed_rows
from conftest import make_platform_admin_headers
from platform_core.models.product_event import ProductEvent

SKILLS_LIST = "/api/v1/public/skills"
CAPABILITIES_LIST = "/api/v1/public/capabilities"
EVENTS_QUERY = "/api/v1/product-events"


class _RateLimitRedis:
    """限流桩：incr+expire 计数（与 test_t13_public_seed_filter 同口径）"""

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


def listed_fixture(count: int, prefix: str = "g814") -> list:
    """非种子已上架夹具资产（不是商品模型；与 GWT-81.1「夹具资产」口径一致）。"""
    return [
        fr33_asset(name=f"{prefix}-vis-{i:02d}", title=f"夹具{i:02d}")
        for i in range(count)
    ]


def _paged(client, url: str, page: int, page_size: int = None, **extra):
    params = {"page": page}
    if page_size is not None:
        params["page_size"] = page_size
    params.update(extra)
    return client.get(url, params=params)


def _market_paged_rows(db_session) -> list:
    async def _go():
        async with db_session() as s:
            rows = (await s.execute(
                select(ProductEvent).where(
                    ProductEvent.event_name == "market_list_paged"
                )
            )).scalars().all()
            return [
                {
                    "tenant_id": r.tenant_id,
                    "anonymous_id": r.anonymous_id,
                    "props": r.props,
                }
                for r in rows
            ]

    return asyncio.run(_go())


# ---------- FR-81：公开端 PAGE_SIZE_MAX=20 ----------


def test_gwt_81_1_public_page_size_cap_is_20(db_client, db_engine, db_session, rate_redis):
    """页大小上限收到 20：21 与 50 都 422（现状 50 放行，FR-81 违约）。"""
    assert db_client.get(
        CAPABILITIES_LIST, params={"page_size": 21}
    ).status_code == 422
    assert db_client.get(SKILLS_LIST, params={"page_size": 50}).status_code == 422
    assert db_client.get(SKILLS_LIST, params={"page_size": 20}).status_code == 200


def test_gwt_81_1_21st_reachable_on_page2_skills(db_client, db_engine, db_session, rate_redis):
    """夹具恰好 21 张：第一页 ≤20 且可见总件与下一页；第 21 张第 2 页可到且不重复。"""
    seed_rows(db_session, listed_fixture(21))
    page1 = db_client.get(SKILLS_LIST, params={"page": 1, "page_size": 20})
    assert page1.status_code == 200, page1.text
    d1 = page1.json()["data"]
    assert d1["total"] == 21  # 页上能看见总件数
    assert len(d1["items"]) == 20  # 第一页 ≤20 张
    assert d1["has_more"] is True  # 下一页存在
    page2 = db_client.get(SKILLS_LIST, params={"page": 2, "page_size": 20})
    d2 = page2.json()["data"]
    names1 = {i["name"] for i in d1["items"]}
    names2 = {i["name"] for i in d2["items"]}
    assert len(names2) == 1  # 第 21 张可到达
    assert not (names1 & names2)  # 不与第一页整页重复
    assert d2["has_more"] is False


def test_gwt_81_1_21st_reachable_on_page2_capabilities(
    db_client, db_engine, db_session, rate_redis,
):
    """能力端同一翻页形态（PIT-5 双公开端同口径）。"""
    seed_rows(db_session, listed_fixture(21))
    page1 = db_client.get(CAPABILITIES_LIST, params={"page": 1, "page_size": 20})
    page2 = db_client.get(CAPABILITIES_LIST, params={"page": 2, "page_size": 20})
    d1, d2 = page1.json()["data"], page2.json()["data"]
    assert d1["total"] == 21 and len(d1["items"]) == 20 and d1["has_more"] is True
    assert {i["name"] for i in d2["items"]} == {"g814-vis-00"}
    assert d2["has_more"] is False


def test_gwt_81_2_exactly_20_no_fake_next_page(db_client, db_engine, db_session, rate_redis):
    """恰好 20 张：无假下一页（has_more=False；第 2 页为空且不再有下一页）。"""
    seed_rows(db_session, listed_fixture(20))
    page1 = db_client.get(SKILLS_LIST, params={"page": 1, "page_size": 20})
    d1 = page1.json()["data"]
    assert d1["total"] == 20
    assert len(d1["items"]) == 20
    assert d1["has_more"] is False
    page2 = db_client.get(SKILLS_LIST, params={"page": 2, "page_size": 20})
    d2 = page2.json()["data"]
    assert d2["items"] == []
    assert d2["has_more"] is False


def test_gwt_81_3_zero_listed_is_empty_not_failure(db_client, db_engine, db_session, rate_redis):
    """0 张已上架：正常空列表（200），不出现总件>0 或翻页谎称有货。"""
    resp = db_client.get(SKILLS_LIST, params={"page": 1, "page_size": 20})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 0
    assert data["items"] == []
    assert data["has_more"] is False
    deep = db_client.get(SKILLS_LIST, params={"page": 2, "page_size": 20})
    assert deep.status_code == 200
    assert deep.json()["data"]["total"] == 0


def test_gwt_81_4_unlisted_asset_never_on_any_page(db_client, db_engine, db_session, rate_redis):
    """未上架资产：任何一页都不出现（含深翻到第 2 页）。"""
    seed_rows(db_session, listed_fixture(21) + [
        fr33_asset(name="g814-hidden-unlisted", title="未上架卡", listing_state="unlisted"),
    ])
    page1 = db_client.get(SKILLS_LIST, params={"page": 1, "page_size": 20})
    page2 = db_client.get(SKILLS_LIST, params={"page": 2, "page_size": 20})
    d1, d2 = page1.json()["data"], page2.json()["data"]
    assert d1["total"] == 21  # 未上架行不进 total
    assert "g814-hidden-unlisted" not in {i["name"] for i in d1["items"]}
    assert "g814-hidden-unlisted" not in {i["name"] for i in d2["items"]}


# ---------- GWT-92.5：market_list_paged（第 2 页起上报；访客无 tenant_id） ----------


def test_gwt_92_5_market_list_paged_emitted_on_page2(
    db_client, db_engine, db_session, rate_redis,
):
    """点下一页（page=2）：上报 market_list_paged，含 page/result_count/anonymous_id，无 tenant_id。"""
    seed_rows(db_session, listed_fixture(21))
    first = db_client.get(SKILLS_LIST, params={
        "page": 1, "page_size": 20, "anonymous_id": "anon-t14-visitor",
    })
    assert first.status_code == 200, first.text
    assert _market_paged_rows(db_session) == []  # 第 1 页不上报
    second = db_client.get(SKILLS_LIST, params={
        "page": 2, "page_size": 20, "anonymous_id": "anon-t14-visitor",
    })
    assert second.status_code == 200, second.text  # 上报失败也不挡列表
    rows = _market_paged_rows(db_session)
    assert len(rows) == 1
    row = rows[0]
    assert row["tenant_id"] is None  # 访客无 tenant_id
    assert row["anonymous_id"] == "anon-t14-visitor"
    props = row["props"] or {}
    assert props.get("page") == 2
    assert props.get("result_count") == 1  # 第 2 页实得 1 张（第 21 张）


def test_gwt_92_5_market_list_paged_capabilities_endpoint(
    db_client, db_engine, db_session, rate_redis,
):
    """能力端翻页同样上报（双公开端同口径）。"""
    seed_rows(db_session, listed_fixture(21))
    resp = db_client.get(CAPABILITIES_LIST, params={
        "page": 2, "page_size": 20, "anonymous_id": "anon-t14-caps",
    })
    assert resp.status_code == 200, resp.text
    rows = _market_paged_rows(db_session)
    assert len(rows) == 1
    assert rows[0]["anonymous_id"] == "anon-t14-caps"
    assert (rows[0]["props"] or {}).get("page") == 2


def test_gwt_92_5_admin_query_surface_can_see_event(
    db_client, db_engine, db_session, rate_redis,
):
    """超管查询面可查（FR-92 查询面既有语义回归）。"""
    seed_rows(db_session, listed_fixture(21))
    db_client.get(SKILLS_LIST, params={
        "page": 2, "page_size": 20, "anonymous_id": "anon-t14-q",
    })
    resp = db_client.get(
        EVENTS_QUERY,
        headers=make_platform_admin_headers(db_session),
        params={"event_name": "market_list_paged"},
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]["items"]
    assert items and items[0]["event_name"] == "market_list_paged"
