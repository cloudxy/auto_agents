"""B1c 能力资产域 HTTP 覆盖（T-04：平台写面 require_platform_admin）

覆盖路由清单：
管理端读（/api/v1/capabilities，require_login）：
- GET  /api/v1/capabilities                       统一列表（空目录可行动空态）
- GET  /api/v1/capabilities/{asset_type}/{name}   统一资产详情（治理字段投影）
- GET  /api/v1/capabilities/plugins/{name}        插件详情（manifest/健康态）
- GET  /api/v1/capabilities/experts/{name}        专家详情（tools/persona）
- GET  /api/v1/capabilities/teams/{name}          专家团详情
- GET  /api/v1/capabilities/teams/{name}/export   专家团导出（TEAM.md）
管理端写（require_platform_admin；租户 admin / viewer 403 + 零落库 + leftover）：
- POST /api/v1/capabilities/plugins/{name}/verify
管理端写（require_platform_admin_or_404；租户 404 同形 + 零落库 + leftover）：
- POST /api/v1/capabilities/scan-experts
- PATCH /api/v1/capabilities/{type}/{name}/listing
- POST /api/v1/capabilities/teams（T-37 / GWT-101.5：与「页面不存在」同形）
公开端（无鉴权）：
- GET  /api/v1/public/capabilities                官网能力市场（五类枚举；非法 type 失败）

T-04 改写：现网「viewer 可扫 200」金标作废（GWT-06.4）。正面路径走 platform_admin_client。
feat-agents-market AD-1：scan-plugins 端点退役（破坏性软删根因），其端点行为
覆盖由 test_sync_endpoint.py 的 sync-agents-hub 用例承接；本文件插件播种改为
直插行（manifest 同 cap_library 夹具）。
"""
import asyncio
import json

import pytest
from sqlalchemy import select

from backend.services.power_market import (
    MARKET_NOT_FOUND_CODE,
    STORE_NOT_FOUND_COPY,
    STORE_NOT_FOUND_HOME,
    STORE_NOT_FOUND_HTML,
)
from backend.tests.fr33_support import (
    fr33_asset,
    gwt_33_2_rows,
    gwt_33_4_rows,
    gwt_33_5_rows,
    seed_include_parent,
    seed_rows,
    utcnow,
)
from platform_core.models.capability import (
    CapabilityAsset,
    CapabilityExpert,
    CapabilityPlugin,
    CapabilityTeam,
)
from platform_core.models.operation_log import OperationLog

PLUGIN_NAME = "demo-plugin"
EXPERT_NAME = "code-reviewer"


@pytest.fixture
def cap_library(tmp_path):
    """能力库根（plugins/ + experts/），SKILLS.LIBRARY_ROOT 指到临时目录"""
    from config import settings

    original = settings.get("SKILLS.LIBRARY_ROOT")
    settings.set("SKILLS.LIBRARY_ROOT", str(tmp_path))

    plugin_dir = tmp_path / "plugins" / PLUGIN_NAME
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(json.dumps({
        "name": PLUGIN_NAME, "description": "演示插件", "version": "1.2.3",
        "author": {"name": "qa"}, "license": "MIT",
        # 不声明 mcpServers：verify 管线的 unknown 分支（PIT-6）
    }), encoding="utf-8")

    expert_dir = tmp_path / "experts" / EXPERT_NAME
    expert_dir.mkdir(parents=True)
    (expert_dir / "AGENT.md").write_text(
        "---\n"
        f"name: {EXPERT_NAME}\n"
        "description: 代码评审专家\n"
        "tools: [Read, Grep]\n"
        "skills: []\n"
        "model: glm-4.7\n"
        "---\n"
        "你是资深代码评审员。\n",
        encoding="utf-8",
    )
    yield tmp_path
    settings.set("SKILLS.LIBRARY_ROOT", original)


def _query_all(db_session, stmt):
    async def _go():
        async with db_session() as s:
            return (await s.execute(stmt)).scalars().all()
    return asyncio.run(_go())


def _seed_plugin_row(db_session):
    """直插插件资产行 + 细节行（feat-agents-market：扫描播种端点已退役）"""

    async def _go():
        async with db_session() as s:
            asset = CapabilityAsset(
                asset_type="plugin", name=PLUGIN_NAME, title="演示插件",
                category="plugin", status="stable", source_type="self_built",
                listing_state="listed", sync_state="ok", license="MIT",
            )
            s.add(asset)
            await s.flush()
            s.add(CapabilityPlugin(
                asset_id=asset.id, version="1.2.3", author="qa", license="MIT",
                manifest={"name": PLUGIN_NAME, "description": "演示插件",
                          "version": "1.2.3"},
                bundled_skills=[], mcp_servers={}, hooks={}, commands={},
            ))
            await s.commit()

    asyncio.run(_go())


def _seed_via_http_scan(db_client, db_session, headers: dict | None = None):
    """播种插件（直插）+ 专家（HTTP scan-experts；调用方须已是特权或带超管 Bearer）"""
    _seed_plugin_row(db_session)
    kw = {"headers": headers} if headers else {}
    e = db_client.post("/api/v1/capabilities/scan-experts", **kw)
    assert e.status_code == 200, e.text


def _seed_via_http_scan_headers(db_client, db_session, headers: dict):
    _seed_via_http_scan(db_client, db_session, headers=headers)


def _denied_logs(db_session):
    async def _go():
        async with db_session() as s:
            return list((await s.execute(
                select(OperationLog).where(OperationLog.action == "authz.denied")
            )).scalars().all())
    return asyncio.run(_go())


# ---------------------------------------------------------------------------
# POST /api/v1/capabilities/scan-plugins（已退役——feat-agents-market AD-1）
# 端点级行为覆盖由 test_sync_endpoint.py（sync-agents-hub）承接。
# ---------------------------------------------------------------------------


def test_retired_scan_plugins_gone_for_everyone(db_client, platform_admin_client):
    """AD-1 验收：破坏性扫描入口不存在——超管直打也 404（路由已删）"""
    resp = platform_admin_client.post("/api/v1/capabilities/scan-plugins")
    assert resp.status_code == 404
    assert db_client.post("/api/v1/capabilities/scan-plugins").status_code == 404


def test_list_capabilities_empty_actionable(db_client, platform_admin_client):
    """GWT-20.2：目录本就为空 → 可行动空态，不是加载失败装空"""
    resp = platform_admin_client.get("/api/v1/capabilities")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 0
    assert data["items"] == []
    assert data.get("empty") is True
    assert data.get("message")


def test_platform_admin_catalog_sees_seeded_plugin(
    db_client, platform_admin_client, db_engine, db_session, cap_library,
):
    """GWT-20.1 后继：目录出现已同步插件（不得静默 0 行）"""
    _seed_plugin_row(db_session)
    listing = platform_admin_client.get(
        "/api/v1/capabilities", params={"type": "plugin"},
    )
    assert listing.status_code == 200, listing.text
    data = listing.json()["data"]
    assert data["total"] == 1
    assert [i["name"] for i in data["items"]] == [PLUGIN_NAME]


# ---------------------------------------------------------------------------
# GET /api/v1/capabilities/plugins/{name} + POST .../verify
# ---------------------------------------------------------------------------
# F-1（B1c 发现，B5 已修复）：GET /{asset_type}/{name} 动态段曾先于
# /plugins/{name} /experts/{name} /teams/{name} 注册，三条静态段详情路由被吞
# （asset_type 取到复数形式 → 恒 404）。B5 将动态段移至文件末尾注册并加
# 防线注释（同 skills.py），以下三条契约用例已按修复后行为转正。


def test_plugin_detail_contract(db_client, platform_admin_client, db_engine, db_session, cap_library):
    """契约：插件详情 200 + manifest 投影（B5 修复路由遮蔽后可用）"""
    _seed_via_http_scan(db_client, db_session)
    resp = db_client.get(f"/api/v1/capabilities/plugins/{PLUGIN_NAME}")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["name"] == PLUGIN_NAME
    assert data["version"] == "1.2.3"
    assert data["health_status"] == "unknown"  # 未验证前健康态未知


def test_plugin_detail_anonymous_401(client):
    """匿名 401：require_login 守卫在 handler 前生效"""
    assert client.get(f"/api/v1/capabilities/plugins/{PLUGIN_NAME}").status_code == 401


def test_plugin_verify_no_mcp_unknown(db_client, platform_admin_client, db_engine, db_session, cap_library):
    """未声明 MCP servers 的插件验证 → unknown（可上架）；健康态落库（PIT-6）"""
    _seed_via_http_scan(db_client, db_session)
    resp = db_client.post(f"/api/v1/capabilities/plugins/{PLUGIN_NAME}/verify")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["health"] == "unknown"
    assert "未声明" in data["detail"]["error"]

    details = _query_all(db_session, select(CapabilityPlugin))
    assert details[0].health_status == "unknown"
    assert details[0].last_verified_at is not None


def test_plugin_verify_unknown_404(db_client, platform_admin_client, db_engine, db_session, cap_library):
    _seed_via_http_scan(db_client, db_session)
    resp = db_client.post("/api/v1/capabilities/plugins/ghost/verify")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_plugin_verify_anonymous_401(client):
    assert client.post(f"/api/v1/capabilities/plugins/{PLUGIN_NAME}/verify").status_code == 401


def test_listing_tenant_admin_404_row_unchanged(db_client, admin_client, db_session):
    """PIT-2 / FR-U12：租户公司管理员不能上架；404 同形；行不变。"""
    from backend.tests.fr33_support import fr33_asset, seed_rows

    seed_rows(db_session, [fr33_asset(name="pit2-row", listing_state="unlisted")])
    resp = admin_client.patch(
        "/api/v1/capabilities/skill/pit2-row/listing",
        json={"listing_state": "listed"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "HTTP_404"
    assert "抱歉" not in resp.text
    row = _query_all(db_session, select(CapabilityAsset).where(
        CapabilityAsset.name == "pit2-row",
    ))[0]
    assert row.listing_state == "unlisted"
    assert _denied_logs(db_session)


def test_listing_viewer_404_row_unchanged(db_client, viewer_client, db_session):
    """PIT-2 / FR-U12：viewer 不能上架；404 同形。"""
    from backend.tests.fr33_support import fr33_asset, seed_rows

    seed_rows(db_session, [fr33_asset(name="pit2-view", listing_state="unlisted")])
    resp = viewer_client.patch(
        "/api/v1/capabilities/skill/pit2-view/listing",
        json={"listing_state": "listed"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "HTTP_404"
    row = _query_all(db_session, select(CapabilityAsset).where(
        CapabilityAsset.name == "pit2-view",
    ))[0]
    assert row.listing_state == "unlisted"


def test_plugin_verify_tenant_admin_404_row_unchanged(
    db_client, admin_client, db_session, cap_library,
):
    """GWT-06.3：租户公司管理员验证 → 拒绝；健康态不变；越权记录"""
    from conftest import make_platform_admin_headers

    seed_auth = make_platform_admin_headers(db_session)
    _seed_via_http_scan_headers(db_client, db_session, seed_auth)
    before = _query_all(db_session, select(CapabilityPlugin))
    assert before and before[0].health_status == "unknown"
    resp = admin_client.post(f"/api/v1/capabilities/plugins/{PLUGIN_NAME}/verify")
    assert resp.status_code == 404
    assert resp.json()["code"] == "HTTP_404"
    after = _query_all(db_session, select(CapabilityPlugin))
    assert after[0].health_status == "unknown"
    assert _denied_logs(db_session)


# ---------------------------------------------------------------------------
# POST /api/v1/capabilities/scan-experts + GET .../experts/{name}
# ---------------------------------------------------------------------------

def test_scan_experts_ok(db_client, platform_admin_client, db_engine, db_session, cap_library):
    resp = db_client.post("/api/v1/capabilities/scan-experts")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["succeeded"] == 1

    assets = _query_all(db_session, select(CapabilityAsset).where(
        CapabilityAsset.asset_type == "expert"))
    assert len(assets) == 1 and assets[0].name == EXPERT_NAME
    details = _query_all(db_session, select(CapabilityExpert))
    assert details[0].tools == ["Read", "Grep"]
    assert "资深代码评审员" in details[0].persona_md


def test_scan_experts_anonymous_401(client):
    assert client.post("/api/v1/capabilities/scan-experts").status_code == 401


def test_expert_detail_contract(db_client, platform_admin_client, db_engine, db_session, cap_library):
    """契约：专家详情 200 + tools/model_pref 投影（B5 修复路由遮蔽后可用）"""
    _seed_via_http_scan(db_client, db_session)
    resp = db_client.get(f"/api/v1/capabilities/experts/{EXPERT_NAME}")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["name"] == EXPERT_NAME
    assert data["tools"] == ["Read", "Grep"]
    assert data["model_pref"] == "glm-4.7"


def test_expert_detail_anonymous_401(client):
    assert client.get(f"/api/v1/capabilities/experts/{EXPERT_NAME}").status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/capabilities/{asset_type}/{name}（统一详情）
# ---------------------------------------------------------------------------

def test_capability_detail_ok_and_404(db_client, platform_admin_client, db_engine, db_session, cap_library):
    """统一详情路由：动态段 (asset_type, name) 二段式不被 /plugins /experts 吞掉"""
    _seed_via_http_scan(db_client, db_session)
    resp = db_client.get(f"/api/v1/capabilities/expert/{EXPERT_NAME}")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["asset_type"] == "expert"
    assert data["name"] == EXPERT_NAME
    assert data["sync_state"] == "ok"

    assert db_client.get("/api/v1/capabilities/expert/ghost").status_code == 404


def test_capability_detail_anonymous_401(client):
    assert client.get(f"/api/v1/capabilities/expert/{EXPERT_NAME}").status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/capabilities/teams + GET .../teams/{name}(+/export)
# ---------------------------------------------------------------------------

TEAM_BODY = {
    "name": "review-team",
    "leader": EXPERT_NAME,
    "members": [EXPERT_NAME],
    "workflow_md": "团长拆解 → 并行评审 → 汇总",
    "title": "评审专家团",
}


def test_team_upsert_create_then_update(db_client, platform_admin_client, db_engine, db_session, cap_library):
    _seed_via_http_scan(db_client, db_session)

    resp = db_client.post("/api/v1/capabilities/teams", json=TEAM_BODY)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {"name": "review-team", "created": True}

    teams = _query_all(db_session, select(CapabilityTeam))
    assert len(teams) == 1                          # 副作用：恰好一条
    assert teams[0].leader_expert == EXPERT_NAME
    assert teams[0].members == [EXPERT_NAME]
    assets = _query_all(db_session, select(CapabilityAsset).where(
        CapabilityAsset.asset_type == "expert_team"))
    assert len(assets) == 1

    # 二次提交同名 → upsert（created=False），不新增行
    resp2 = db_client.post("/api/v1/capabilities/teams", json=TEAM_BODY)
    assert resp2.status_code == 200
    assert resp2.json()["data"]["created"] is False
    assert len(_query_all(db_session, select(CapabilityTeam))) == 1


def test_team_upsert_dangling_ref_422(db_client, platform_admin_client, db_engine, db_session, cap_library):
    """悬空专家引用 → 422，且零落库（副作用断言：无 expert_team 行）"""
    _seed_via_http_scan(db_client, db_session)
    resp = db_client.post("/api/v1/capabilities/teams", json={
        **TEAM_BODY, "members": ["ghost-expert"]})
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "VALIDATION_ERROR"
    assert "ghost-expert" in resp.json()["message"]

    assert _query_all(db_session, select(CapabilityTeam)) == []
    assert _query_all(db_session, select(CapabilityAsset).where(
        CapabilityAsset.asset_type == "expert_team")) == []


def test_team_upsert_anonymous_401(client):
    assert client.post("/api/v1/capabilities/teams", json=TEAM_BODY).status_code == 401


def test_team_upsert_tenant_404_same_shape_zero_rows(
    db_client, operator_client, admin_client, db_session, cap_library,
):
    """GWT-101.5（T-37）：租户直打组建团队 → 与「页面不存在」同形（404，非 403 信封），
    零团队落库，留越权记录。GWT-20.3 Then（拒绝且行不变）同时保持。"""
    from conftest import make_platform_admin_headers

    _seed_via_http_scan_headers(db_client, db_session, make_platform_admin_headers(db_session))
    for tenant_client in (operator_client, admin_client):
        resp = tenant_client.post("/api/v1/capabilities/teams", json=TEAM_BODY)
        assert resp.status_code == 404
        assert resp.json().get("code") != "FORBIDDEN"  # 404 同形，不走 403 信封
    assert _query_all(db_session, select(CapabilityTeam)) == []
    assert _query_all(db_session, select(CapabilityAsset).where(
        CapabilityAsset.asset_type == "expert_team")) == []
    assert _denied_logs(db_session)


def test_team_mixed_members_expert_union_agent_route(
    db_client, platform_admin_client, db_engine, db_session, cap_library,
):
    """GWT-101.1/101.2（T-37，HTTP 面）：agent 成员可提交；详情/导出带类型标注"""
    from backend.tests.fr33_support import fr33_asset, seed_rows

    _seed_via_http_scan(db_client, db_session)
    seed_rows(db_session, [fr33_asset(
        asset_type="agent", name="g101-agent", category="cat-g", title="调研智能体")])

    resp = db_client.post("/api/v1/capabilities/teams", json={
        **TEAM_BODY,
        "members": [{"type": "expert", "name": EXPERT_NAME},
                    {"type": "agent", "name": "g101-agent"}],
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {"name": "review-team", "created": True}

    detail = db_client.get("/api/v1/capabilities/teams/review-team").json()["data"]
    assert {"type": "expert", "name": EXPERT_NAME} in detail["members"]
    assert {"type": "agent", "name": "g101-agent"} in detail["members"]

    markdown = db_client.get("/api/v1/capabilities/teams/review-team/export").json()["data"]["markdown"]
    assert "g101-agent（智能体）" in markdown
    assert f"{EXPERT_NAME}（专家）" in markdown


def test_team_agent_dangling_route_422(
    db_client, platform_admin_client, db_engine, db_session, cap_library,
):
    """智能体悬空引用 → 422 中文句 + 零落库（T-37）"""
    _seed_via_http_scan(db_client, db_session)
    resp = db_client.post("/api/v1/capabilities/teams", json={
        **TEAM_BODY, "members": [{"type": "agent", "name": "ghost-agent"}]})
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "VALIDATION_ERROR"
    assert "智能体引用不存在" in resp.json()["message"]
    assert _query_all(db_session, select(CapabilityTeam)) == []


def test_team_detail_contract(db_client, platform_admin_client, db_engine, db_session, cap_library):
    """契约：专家团详情 200 + leader/members/workflow 投影（B5 修复路由遮蔽后可用）"""
    _seed_via_http_scan(db_client, db_session)
    assert db_client.post("/api/v1/capabilities/teams", json=TEAM_BODY).status_code == 200

    resp = db_client.get("/api/v1/capabilities/teams/review-team")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["name"] == "review-team"
    assert data["leader"] == EXPERT_NAME
    assert data["members"] == [EXPERT_NAME]
    assert data["workflow_md"] == TEAM_BODY["workflow_md"]


def test_team_detail_anonymous_401(client):
    assert client.get("/api/v1/capabilities/teams/review-team").status_code == 401


def test_team_export_ok_and_404(db_client, platform_admin_client, db_engine, db_session, cap_library):
    _seed_via_http_scan(db_client, db_session)
    assert db_client.post("/api/v1/capabilities/teams", json=TEAM_BODY).status_code == 200

    resp = db_client.get("/api/v1/capabilities/teams/review-team/export")
    assert resp.status_code == 200, resp.text
    markdown = resp.json()["data"]["markdown"]
    assert f"**团长**：{EXPERT_NAME}" in markdown
    assert "团长拆解" in markdown  # workflow 段落收录

    assert db_client.get("/api/v1/capabilities/teams/ghost/export").status_code == 404


def test_team_export_anonymous_401(client):
    assert client.get("/api/v1/capabilities/teams/review-team/export").status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/public/capabilities（公开：仅 stable + 白名单 + IP 限流）
# ---------------------------------------------------------------------------

_PUBLIC_WHITELIST = {
    "name", "title", "description", "category", "tier", "score",
    "status", "source_url", "source_author", "updated_at", "asset_type",
    "listing_state", "license", "subscribable", "hosts", "slash",
    # feat-agents-market WIP：logo/background 以相对媒体 href 外发（无本机绝对路径）
    "logo", "background",
    # feat-agents-market T-06：featured 随 items 外发（AD-6 综合序权重）
    "featured",
}


class _RateLimitRedis:
    """限流桩：incr+expire 计数（与 test_skill_public_api 同口径，域内局部桩）"""

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


def _seed_public_assets(db_session):
    """直接落读模型行：五类 FR-33 过闸 + skill experimental + expert stable"""
    seed_rows(db_session, [
        fr33_asset(asset_type="skill", name="pub-skill", category="cat-a"),
        fr33_asset(asset_type="skill", name="draft-skill", status="experimental",
                   listing_state="listed", category="cat-a"),
        fr33_asset(asset_type="plugin", name="pub-plugin", category="cat-p"),
        fr33_asset(asset_type="command", name="pub-command", category="cat-c"),
        fr33_asset(asset_type="agent", name="pub-agent", category="cat-g"),
        fr33_asset(asset_type="team", name="pub-team", category="cat-t"),
        fr33_asset(asset_type="expert", name="pub-expert", category="cat-b"),
    ])


def test_public_capabilities_only_stable(db_client, db_engine, db_session, rate_redis):
    _seed_public_assets(db_session)
    resp = db_client.get("/api/v1/public/capabilities", params={"type": "skill"})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 1
    assert [i["name"] for i in data["items"]] == ["pub-skill"]  # experimental 不外泄


def test_public_capabilities_fields_whitelist(db_client, db_engine, db_session, rate_redis):
    _seed_public_assets(db_session)
    resp = db_client.get("/api/v1/public/capabilities")
    items = resp.json()["data"]["items"]
    assert items, "预置数据缺失"
    for item in items:
        leaked = set(item.keys()) - _PUBLIC_WHITELIST
        assert not leaked, f"白名单外字段外泄: {leaked}"


def test_public_capabilities_invalid_type_fails(db_client, db_engine, db_session, rate_redis):
    """GWT-44.2：非法 type 筛选失败，不得展示技能列表当作成功"""
    _seed_public_assets(db_session)
    resp = db_client.get("/api/v1/public/capabilities", params={"type": "bogus"})
    body = resp.json()
    assert resp.status_code == 422
    assert body["code"] == "VALIDATION_ERROR"
    assert "没有这种类型" in body["message"]
    data = body.get("data") or {}
    assert data.get("items") is None or data.get("items") == [] or "items" not in data
    assert "pub-skill" not in str(body)


def test_public_skills_invalid_type_fails(db_client, db_engine, db_session, rate_redis):
    """双公开端同一五类枚举：/public/skills?type=bogus 亦不得兜成技能"""
    _seed_public_assets(db_session)
    resp = db_client.get("/api/v1/public/skills", params={"type": "bogus"})
    body = resp.json()
    assert resp.status_code == 422
    assert body["code"] == "VALIDATION_ERROR"
    assert "没有这种类型" in body["message"]
    assert "pub-skill" not in str(body)


def test_public_capabilities_plugin_filter_only(db_client, db_engine, db_session, rate_redis):
    """GWT-44.1：按插件筛选只出现插件卡"""
    _seed_public_assets(db_session)
    resp = db_client.get("/api/v1/public/capabilities", params={"type": "plugin"})
    assert resp.status_code == 200, resp.text
    names = [i["name"] for i in resp.json()["data"]["items"]]
    types = {i["asset_type"] for i in resp.json()["data"]["items"]}
    assert names == ["pub-plugin"]
    assert types == {"plugin"}


def test_public_capabilities_untyped_five_types(db_client, db_engine, db_session, rate_redis):
    """GWT-44.3：未选类型时五类均可出现（枚举不得挡 command/agent/team）"""
    _seed_public_assets(db_session)
    resp = db_client.get("/api/v1/public/capabilities")
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]["items"]
    types = {i["asset_type"] for i in items}
    names = {i["name"] for i in items}
    assert {"skill", "plugin", "command", "agent", "team"} <= types
    assert "pub-command" in names and "pub-agent" in names and "pub-team" in names
    assert "expert" not in types
    assert "pub-expert" in names  # expand：库内 expert 以智能体出现
    expert_row = next(i for i in items if i["name"] == "pub-expert")
    assert expert_row["asset_type"] == "agent"


def test_public_expert_type_maps_to_agent(db_client, db_engine, db_session, rate_redis):
    """GWT-30.4：旧 type=expert 映射到智能体，不新开第四个店"""
    _seed_public_assets(db_session)
    as_expert = db_client.get("/api/v1/public/capabilities", params={"type": "expert"})
    as_agent = db_client.get("/api/v1/public/capabilities", params={"type": "agent"})
    assert as_expert.status_code == 200 and as_agent.status_code == 200
    expert_names = {i["name"] for i in as_expert.json()["data"]["items"]}
    agent_names = {i["name"] for i in as_agent.json()["data"]["items"]}
    assert expert_names == agent_names
    assert "pub-expert" in expert_names and "pub-agent" in expert_names
    assert "pub-skill" not in expert_names
    assert {i["asset_type"] for i in as_expert.json()["data"]["items"]} == {"agent"}


def test_public_endpoints_share_five_type_enum():
    """双公开端必须同一五类枚举（禁止一边修一边留 bogus→skill）"""
    from backend.app.api.v1 import public_skills
    from backend.services.power_market import PUBLIC_ASSET_TYPES

    assert public_skills.PUBLIC_ASSET_TYPES is PUBLIC_ASSET_TYPES
    assert PUBLIC_ASSET_TYPES == ("skill", "plugin", "command", "agent", "team")
    assert "expert" not in PUBLIC_ASSET_TYPES


def test_public_capabilities_rate_limit_429(db_client, db_engine, db_session, rate_redis, monkeypatch):
    """超 SKILLS.PUBLIC_API.RATE_LIMIT_PER_MIN → 429（第三道闸按 IP 计数）"""
    from config import settings

    original = settings.get("SKILLS.PUBLIC_API.RATE_LIMIT_PER_MIN")
    settings.set("SKILLS.PUBLIC_API.RATE_LIMIT_PER_MIN", 2)
    try:
        _seed_public_assets(db_session)
        codes = [db_client.get("/api/v1/public/capabilities").status_code for _ in range(4)]
    finally:
        settings.set("SKILLS.PUBLIC_API.RATE_LIMIT_PER_MIN", original)
    assert codes[:2] == [200, 200]
    assert codes[2] == 429 and codes[3] == 429


# ---------------------------------------------------------------------------
# T-23 FR-33 查询侧闸 / 商店不存在句 / 包含 / 分页（能力端）
# ---------------------------------------------------------------------------

_CAP = "/api/v1/public/capabilities"


def test_gwt_32_1_capability_detail_fields(db_client, db_engine, db_session, rate_redis):
    seed_rows(db_session, [fr33_asset(
        asset_type="plugin", name="plug-ok", category="cat-p", title="插件卡",
    )])
    resp = db_client.get(f"{_CAP}/plugin/plug-ok")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["description"] == "说明"
    assert data["license"] == "MIT"
    assert data["source_author"] == "qa"
    assert data["hosts"] == ["grok", "zcode", "kimi", "claude"]
    assert data["subscribable"] is True
    assert "includes" in data


def test_gwt_32_2_coming_soon_capability_no_subscribe(db_client, db_engine, db_session, rate_redis):
    seed_rows(db_session, [fr33_asset(
        asset_type="plugin", name="plug-soon", listing_state="coming_soon", category="cat-p",
    )])
    resp = db_client.get(f"{_CAP}/plugin/plug-soon")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["listing_state"] == "coming_soon"
    assert data["subscribable"] is False
    assert "尚未上架" not in resp.text


def test_gwt_32_3_capability_unlisted_html_404(db_client, db_engine, db_session, rate_redis):
    seed_rows(db_session, [
        fr33_asset(asset_type="plugin", name="plug-unlist", listing_state="unlisted"),
        fr33_asset(asset_type="plugin", name="plug-black", status="blacklist"),
    ])
    ghost = db_client.get(f"{_CAP}/plugin/never-existed-slug")
    unlisted = db_client.get(f"{_CAP}/plugin/plug-unlist")
    black = db_client.get(f"{_CAP}/plugin/plug-black")
    assert ghost.content == unlisted.content == black.content == STORE_NOT_FOUND_HTML.encode("utf-8")
    assert STORE_NOT_FOUND_COPY in ghost.text and STORE_NOT_FOUND_HOME in ghost.text
    assert "已下架" not in ghost.text


def test_gwt_32_8_capability_subscribe_market_not_found(
    db_client, operator_client, db_engine, db_session, rate_redis,
):
    seed_rows(db_session, [
        fr33_asset(asset_type="plugin", name="plug-unlist", listing_state="unlisted"),
        fr33_asset(asset_type="plugin", name="plug-black", status="blacklist"),
    ])
    ghost = db_client.post(f"{_CAP}/plugin/never-existed-slug/subscribe")
    unlisted = db_client.post(f"{_CAP}/plugin/plug-unlist/subscribe")
    black = db_client.post(f"{_CAP}/plugin/plug-black/subscribe")
    for resp in (ghost, unlisted, black):
        assert resp.status_code == 404
        assert resp.json()["code"] == MARKET_NOT_FOUND_CODE
        assert "已下架" not in resp.text
        assert STORE_NOT_FOUND_COPY not in resp.text
        assert "text/html" not in resp.headers.get("content-type", "")
    assert ghost.json()["message"] == unlisted.json()["message"] == black.json()["message"]


def test_gwt_32_7_logged_in_subscribe_no_install_row(
    db_client, db_engine, db_session, rate_redis,
):
    seed_rows(db_session, [fr33_asset(asset_type="plugin", name="plug-sub")])
    resp = db_client.post(f"{_CAP}/plugin/plug-sub/subscribe")
    assert resp.status_code == 401
    from platform_core.models.capability import CapabilityInstall
    from sqlalchemy import func, select

    async def _count():
        async with db_session() as s:
            return int((await s.execute(
                select(func.count()).select_from(CapabilityInstall).where(
                    CapabilityInstall.deleted_at.is_(None),
                )
            )).scalar_one())

    assert asyncio.run(_count()) == 0


def test_gwt_32_9_includes_a_and_b(db_client, db_engine, db_session, rate_redis):
    seed_include_parent(db_session, parent="plug-inc-9", children=[
        {"name": "inc-a", "listing_state": "listed"},
        {"name": "inc-b", "listing_state": "coming_soon"},
    ])
    names = {i["name"] for i in db_client.get(f"{_CAP}/plugin/plug-inc-9").json()["data"]["includes"]}
    assert names == {"inc-a", "inc-b"}


def test_gwt_32_10_includes_skips_unlisted(db_client, db_engine, db_session, rate_redis):
    seed_include_parent(db_session, parent="plug-inc-10", children=[
        {"name": "inc-a10", "listing_state": "listed"},
        {"name": "inc-unlisted", "listing_state": "unlisted"},
    ])
    names = {i["name"] for i in db_client.get(f"{_CAP}/plugin/plug-inc-10").json()["data"]["includes"]}
    assert names == {"inc-a10"}
    assert "inc-unlisted" not in names


def test_gwt_32_11_includes_skips_blacklist_and_soft_delete(
    db_client, db_engine, db_session, rate_redis,
):
    seed_include_parent(db_session, parent="plug-inc-11", children=[
        {"name": "inc-a11", "listing_state": "listed"},
        {"name": "inc-c", "status": "blacklist"},
        {"name": "inc-d", "deleted_at": utcnow()},
    ])
    names = {i["name"] for i in db_client.get(f"{_CAP}/plugin/plug-inc-11").json()["data"]["includes"]}
    assert names == {"inc-a11"}
    assert "inc-c" not in names and "inc-d" not in names


def test_gwt_32_12_includes_skips_unlicensed_and_experimental(
    db_client, db_engine, db_session, rate_redis,
):
    seed_include_parent(db_session, parent="plug-inc-12", children=[
        {"name": "inc-a12", "listing_state": "listed"},
        {"name": "inc-e", "license": "NOASSERTION"},
        {"name": "inc-f", "status": "experimental"},
    ])
    names = {i["name"] for i in db_client.get(f"{_CAP}/plugin/plug-inc-12").json()["data"]["includes"]}
    assert names == {"inc-a12"}
    assert "inc-e" not in names and "inc-f" not in names


def test_gwt_33_1_listed_appears_coming_soon_not_subscribable(
    db_client, db_engine, db_session, rate_redis,
):
    seed_rows(db_session, [
        fr33_asset(name="mkt-listed", asset_type="skill"),
        fr33_asset(name="mkt-soon", asset_type="skill", listing_state="coming_soon"),
    ])
    items = db_client.get(_CAP, params={"type": "skill"}).json()["data"]["items"]
    by_name = {i["name"]: i for i in items}
    assert by_name["mkt-listed"]["subscribable"] is True
    assert by_name["mkt-soon"]["subscribable"] is False


def test_gwt_33_2_capabilities_six_row_fixture(db_client, db_engine, db_session, rate_redis):
    seed_rows(db_session, gwt_33_2_rows(prefix="c332"))
    items = db_client.get(_CAP, params={"type": "skill"}).json()["data"]["items"]
    names = {i["name"] for i in items}
    assert names == {"c332-soon", "c332-rec"}
    by_name = {i["name"]: i for i in items}
    assert by_name["c332-soon"]["subscribable"] is False
    assert by_name["c332-rec"]["subscribable"] is True


def test_gwt_33_4_capabilities_page2_empty(db_client, db_engine, db_session, rate_redis):
    seed_rows(db_session, gwt_33_4_rows(page_size=20))
    page1 = db_client.get(_CAP, params={"type": "skill", "page": 1, "page_size": 20})
    page2 = db_client.get(_CAP, params={"type": "skill", "page": 2, "page_size": 20})
    d1, d2 = page1.json()["data"], page2.json()["data"]
    assert d1["total"] == d2["total"] == 20
    assert d2["items"] == [] and d2["has_more"] is False
    assert all(i["name"].startswith("g334-vis-") for i in d1["items"])


def test_gwt_33_5_capabilities_page2_gated_only(db_client, db_engine, db_session, rate_redis):
    seed_rows(db_session, gwt_33_5_rows(page_size=20, extra=5))
    page1 = db_client.get(_CAP, params={"type": "skill", "page": 1, "page_size": 20})
    page2 = db_client.get(_CAP, params={"type": "skill", "page": 2, "page_size": 20})
    d1, d2 = page1.json()["data"], page2.json()["data"]
    assert d1["total"] == d2["total"] == 25
    assert d1["has_more"] is True
    names = [i["name"] for i in d2["items"]]
    assert len(names) == 5
    assert all(n.startswith("g335-vis-") for n in names)


def test_public_capabilities_page_size_max_20(db_client, db_engine, db_session, rate_redis):
    """T-14（FR-81）：公开端页大小上限收到 20（此前 50；金标同 PR 更新）。"""
    assert db_client.get(_CAP, params={"page_size": 21}).status_code == 422
    assert db_client.get(_CAP, params={"page_size": 20}).status_code == 200


def test_public_aliases_static_route_reserved(db_client, db_engine, db_session, rate_redis):
    """PIT-1：/capabilities/aliases 不得被 /{type}/{name} 吞掉。"""
    resp = db_client.get(f"{_CAP}/aliases")
    assert resp.status_code == 404
    assert resp.content == STORE_NOT_FOUND_HTML.encode("utf-8")


def test_nfr01_list_400_listed_p95_under_2s(db_client, db_engine, db_session, rate_redis):
    """NFR-01：≤400 已上架浏览列表 P95 < 2s（TestClient 计时，禁止口头过）。"""
    import time

    seed_rows(db_session, [
        fr33_asset(name=f"nfr-{i:03d}", title=f"n{i}") for i in range(400)
    ])
    samples = []
    for _ in range(20):
        t0 = time.perf_counter()
        resp = db_client.get(_CAP, params={"page": 1, "page_size": 20})
        samples.append(time.perf_counter() - t0)
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 400
    samples.sort()
    p95 = samples[int(0.95 * (len(samples) - 1))]
    print(
        f"NFR-01 P95={p95:.6f}s n={len(samples)} "
        f"min={samples[0]:.6f} max={samples[-1]:.6f} samples={samples!r}"
    )
    assert p95 < 2.0, f"NFR-01 P95={p95:.4f}s samples={samples}"

