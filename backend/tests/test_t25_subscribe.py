"""T-25 FR-34 订阅写路径：GWT-34.1…34.13 + 32.6/32.7/32.8 安装行。"""
from datetime import date

import pytest
from sqlalchemy import select

from backend.services.power_market import (
    MARKET_COMING_SOON_CODE,
    MARKET_HOST_INCOMPAT_CODE,
    MARKET_NEEDS_TENANT_CODE,
    MARKET_NOT_FOUND_CODE,
    MARKET_READONLY_ROLE_CODE,
    STORE_NOT_FOUND_HTML,
)
from backend.services.quota_service import QuotaService, shanghai_year_month
from backend.tests.fr33_support import fr33_asset, seed_include_parent, seed_rows
from backend.tests.t25_support import (
    asset_id_of,
    bind_actor,
    live_install_count,
    live_installs,
    public_subscribe_url,
    seed_listed,
    seed_tenant,
    subscribe_url,
)
from platform_core.models.llm_token_usage import LlmTokenUsage
from platform_core.models.spider_result import SpiderResult
from platform_core.models.spider_task import SpiderTask
from platform_core.models.tenant import Tenant

_INSTALLS = "/api/v1/capabilities/installs"
_GIFT = ("礼包", "安装此插件将获得", "全部技能")


@pytest.fixture
def tid(db_session) -> int:
    return seed_tenant(db_session, "t25-op")


@pytest.fixture
def op_client(app, db_client, tid):
    bind_actor(app, role="operator", tenant_id=tid, tenant_role="operator")
    return db_client


def _post(client, asset_type: str, name: str, host: str = "grok"):
    return client.post(subscribe_url(asset_type, name), json={"host": host})


def _assert_no_gift(resp) -> None:
    text = resp.text
    for token in _GIFT:
        assert token not in text


def test_gwt_34_1_subscribe_grok_creates_row(
    op_client, db_engine, db_session, tid,
):
    seed_listed(db_session, name="g341-skill")
    resp = _post(op_client, "skill", "g341-skill", "grok")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] != MARKET_NOT_FOUND_CODE
    data = body["data"]
    assert data["created"] is True
    assert data["message"] == "已订阅到 Grok"
    _assert_no_gift(resp)
    listed = op_client.get(_INSTALLS)
    assert listed.status_code == 200, listed.text
    items = listed.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["host"] == "grok"
    assert items[0]["asset_name"] == "g341-skill"
    assert live_install_count(db_session) == 1


def test_gwt_34_2_coming_soon_rejected_no_row(
    op_client, db_engine, db_session, tid,
):
    seed_listed(db_session, name="g342-soon", listing_state="coming_soon")
    resp = _post(op_client, "skill", "g342-soon", "grok")
    assert resp.json()["code"] == MARKET_COMING_SOON_CODE
    assert resp.json()["code"] != MARKET_NOT_FOUND_CODE
    assert resp.json()["message"] == "这是预告项，现在不能订阅。"
    _assert_no_gift(resp)
    assert live_install_count(db_session) == 0


def test_gwt_34_3_readonly_role_rejected(app, db_client, db_engine, db_session, tid):
    bind_actor(app, role="viewer", tenant_id=tid, tenant_role="viewer")
    seed_listed(db_session, name="g343-skill")
    resp = _post(db_client, "skill", "g343-skill", "grok")
    assert resp.json()["code"] == MARKET_READONLY_ROLE_CODE
    assert resp.json()["message"] == "当前账号不能订阅，请联系企业管理员"
    assert live_install_count(db_session) == 0


def test_gwt_34_4_platform_admin_needs_tenant(
    platform_admin_client, db_engine, db_session, db_client,
):
    seed_listed(db_session, name="g344-skill")
    resp = _post(platform_admin_client, "skill", "g344-skill", "grok")
    assert resp.json()["code"] == MARKET_NEEDS_TENANT_CODE
    assert resp.json()["message"] == "需要企业空间才能订阅"
    assert live_install_count(db_session) == 0


def test_gwt_34_5_second_host_does_not_overwrite(
    op_client, db_engine, db_session, tid,
):
    seed_listed(db_session, name="g345-skill")
    first = _post(op_client, "skill", "g345-skill", "grok")
    second = _post(op_client, "skill", "g345-skill", "claude")
    assert first.status_code == second.status_code == 200
    rows = live_installs(db_session)
    hosts = sorted(r.host for r in rows)
    assert hosts == ["claude", "grok"]
    grok = next(r for r in rows if r.host == "grok")
    claude = next(r for r in rows if r.host == "claude")
    assert grok.id != claude.id
    assert grok.asset_id == claude.asset_id


def test_gwt_34_6_idempotent_same_host(op_client, db_engine, db_session, tid):
    seed_listed(db_session, name="g346-skill")
    first = _post(op_client, "skill", "g346-skill", "grok")
    again = _post(op_client, "skill", "g346-skill", "grok")
    assert first.json()["data"]["created"] is True
    assert again.status_code == 200
    data = again.json()["data"]
    assert data["created"] is False
    assert data["message"] == "已订阅到 Grok，没有新增行。"
    assert live_install_count(db_session) == 1


def test_gwt_34_7_declared_kimi_only_rejects_grok(
    op_client, db_engine, db_session, tid,
):
    seed_listed(db_session, name="g347-kimi-only", host_compat=["kimi"])
    detail = op_client.get("/api/v1/public/capabilities/skill/g347-kimi-only")
    assert detail.status_code == 200
    assert "grok" not in detail.json()["data"]["hosts"]
    assert detail.json()["data"]["hosts"] == ["kimi"]
    resp = _post(op_client, "skill", "g347-kimi-only", "grok")
    assert resp.json()["code"] == MARKET_HOST_INCOMPAT_CODE
    assert "该能力未声明支持 Grok" in resp.json()["message"]
    assert live_install_count(db_session) == 0


def test_gwt_34_8_plugin_no_gift_child_rows(op_client, db_engine, db_session, tid):
    seed_include_parent(db_session, parent="g348-plug", children=[
        {"name": "g348-s1"}, {"name": "g348-s2"}, {"name": "g348-s3"},
    ])
    resp = _post(op_client, "plugin", "g348-plug", "grok")
    assert resp.status_code == 200, resp.text
    _assert_no_gift(resp)
    rows = live_installs(db_session)
    assert len(rows) == 1
    assert rows[0].asset_id == asset_id_of(db_session, "g348-plug")
    child_ids = {
        asset_id_of(db_session, n) for n in ("g348-s1", "g348-s2", "g348-s3")
    }
    assert rows[0].asset_id not in child_ids


def test_gwt_34_9_undeclared_host_compat_allows_any(
    op_client, db_engine, db_session, tid,
):
    """未声明 / 未给出名单（host_compat IS NULL）= 四宿主都可订。禁止叫空名单。"""
    seed_listed(db_session, name="g349-undeclared")
    detail = op_client.get("/api/v1/public/capabilities/skill/g349-undeclared")
    assert detail.json()["data"]["hosts"] == ["grok", "zcode", "kimi", "claude"]
    resp = _post(op_client, "skill", "g349-undeclared", "zcode")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["created"] is True
    assert resp.json()["data"]["message"] == "已订阅到 ZCode"
    assert live_install_count(db_session) == 1
    assert live_installs(db_session)[0].host == "zcode"


def test_gwt_34_10_declared_zero_hosts_rejects(
    op_client, db_engine, db_session, tid,
):
    """已声明且名单为零项（host_compat=[]）= 四宿主都不可订。禁止叫空名单。"""
    seed_listed(db_session, name="g3410-declared-zero", host_compat=[])
    detail = op_client.get("/api/v1/public/capabilities/skill/g3410-declared-zero")
    assert detail.json()["data"]["hosts"] == []
    resp = _post(op_client, "skill", "g3410-declared-zero", "kimi")
    assert resp.json()["code"] == MARKET_HOST_INCOMPAT_CODE
    assert live_install_count(db_session) == 0


def test_gwt_34_11_quota_full_still_subscribes(
    op_client, db_engine, db_session, tid,
):
    async def _fill():
        async with db_session() as s:
            t = (await s.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()
            t.quota = {
                "task_concurrency": 1, "result_storage": 1, "llm_tokens_month": 1,
            }
            task = SpiderTask(
                spider_name="g3411", tenant_id=tid, status="running", params="{}",
            )
            s.add(task)
            await s.flush()
            s.add(SpiderResult(
                task_id=task.id, spider_name="g3411", url="https://u", tenant_id=tid,
            ))
            ym = shanghai_year_month()
            year, month = (int(p) for p in ym.split("-"))
            s.add(LlmTokenUsage(
                tenant_id=tid, provider_name="provider:1", model="m",
                stat_date=date(year, month, 1), total_tokens=1,
            ))
            await s.commit()

    import asyncio
    asyncio.run(_fill())
    seed_listed(db_session, name="g3411-skill")

    async def _usage():
        async with db_session() as s:
            return await QuotaService(s).usage_overview(tid, shanghai_year_month())

    before = asyncio.run(_usage())
    assert before["usage"]["task_concurrency"] == 1
    assert before["usage"]["result_storage"] == 1
    assert before["usage"]["llm_tokens_month"] == 1
    resp = _post(op_client, "skill", "g3411-skill", "grok")
    assert resp.status_code == 200, resp.text
    assert resp.json().get("code") != "QUOTA_EXCEEDED"
    assert resp.json()["data"]["created"] is True
    after = asyncio.run(_usage())
    assert after["usage"] == before["usage"]
    assert live_install_count(db_session) == 1


def test_gwt_34_12_unlisted_parent_does_not_block_child(
    op_client, db_engine, db_session, tid,
):
    seed_rows(db_session, [
        fr33_asset(
            asset_type="plugin", name="g3412-parent", listing_state="unlisted",
            category="cat-p",
        ),
        fr33_asset(name="g3412-child", title="子技能"),
    ])
    from platform_core.models.capability import CapabilityAsset, CapabilityComponent

    async def _edge():
        async with db_session() as s:
            parent = (await s.execute(
                select(CapabilityAsset).where(CapabilityAsset.name == "g3412-parent")
            )).scalar_one()
            child = (await s.execute(
                select(CapabilityAsset).where(CapabilityAsset.name == "g3412-child")
            )).scalar_one()
            s.add(CapabilityComponent(
                parent_asset_id=parent.id, child_asset_id=child.id, role="bundled_skill",
            ))
            await s.commit()

    import asyncio
    asyncio.run(_edge())
    resp = _post(op_client, "skill", "g3412-child", "grok")
    assert resp.status_code == 200, resp.text
    rows = live_installs(db_session)
    assert len(rows) == 1
    assert rows[0].asset_id == asset_id_of(db_session, "g3412-child")
    parent_id = asset_id_of(db_session, "g3412-parent")
    assert all(r.asset_id != parent_id for r in rows)


def test_gwt_34_13_unlisted_parent_store_not_found(
    op_client, db_client, db_engine, db_session, tid,
):
    seed_rows(db_session, [
        fr33_asset(
            asset_type="plugin", name="g3413-parent", listing_state="unlisted",
            category="cat-p",
        ),
        fr33_asset(name="g3413-child"),
    ])
    ghost = db_client.get("/api/v1/public/capabilities/plugin/g3413-parent")
    assert ghost.status_code == 404
    assert ghost.content == STORE_NOT_FOUND_HTML.encode("utf-8")
    posted = _post(op_client, "plugin", "g3413-parent", "grok")
    assert posted.json()["code"] == MARKET_NOT_FOUND_CODE
    assert posted.json()["message"] == "没有这个能力，不能订阅。"
    assert "已下架" not in posted.text
    assert live_install_count(db_session) == 0


def test_gwt_32_6_anonymous_subscribe_401(db_client, db_engine, db_session):
    seed_listed(db_session, name="g326-anon")
    resp = db_client.post(public_subscribe_url("skill", "g326-anon"), json={"host": "grok"})
    assert resp.status_code == 401
    assert resp.json()["code"] != MARKET_NOT_FOUND_CODE
    assert live_install_count(db_session) == 0


def test_gwt_32_7_login_bounce_no_install_row(
    app, db_client, db_engine, db_session,
):
    bounce_tid = seed_tenant(db_session, "t25-bounce")
    seed_listed(db_session, name="g327-bounce")
    anon = db_client.post(
        public_subscribe_url("skill", "g327-bounce"), json={"host": "grok"},
    )
    assert anon.status_code == 401
    bind_actor(app, role="operator", tenant_id=bounce_tid, tenant_role="operator")
    listed = db_client.get(_INSTALLS)
    assert listed.status_code == 200
    assert listed.json()["data"]["items"] == []
    assert live_install_count(db_session) == 0


def test_gwt_32_8_unlisted_subscribe_no_row(
    op_client, db_engine, db_session, tid,
):
    seed_listed(db_session, name="g328-unlist", listing_state="unlisted")
    resp = _post(op_client, "skill", "g328-unlist", "grok")
    assert resp.json()["code"] == MARKET_NOT_FOUND_CODE
    assert resp.json()["message"] == "没有这个能力，不能订阅。"
    assert "已下架" not in resp.text
    assert live_install_count(db_session) == 0
