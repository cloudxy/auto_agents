"""B1c 零 HTTP 覆盖路由清剿——能力资产域 + 官网能力广场（10 条路由）

覆盖路由清单：
管理端（/api/v1/capabilities，require_login——viewer 亦放行，无 403 分支）：
- GET  /api/v1/capabilities/{asset_type}/{name}   统一资产详情（治理字段投影）
- POST /api/v1/capabilities/scan-plugins          扫描 plugins/ 目录入库
- GET  /api/v1/capabilities/plugins/{name}        插件详情（manifest/健康态）
- POST /api/v1/capabilities/plugins/{name}/verify 插件验证管线（无 MCP → degraded）
- POST /api/v1/capabilities/scan-experts          扫描 experts/ 目录入库
- GET  /api/v1/capabilities/experts/{name}        专家详情（tools/persona）
- POST /api/v1/capabilities/teams                 专家团 upsert（引用校验）
- GET  /api/v1/capabilities/teams/{name}          专家团详情
- GET  /api/v1/capabilities/teams/{name}/export   专家团导出（TEAM.md）
公开端（无鉴权）：
- GET  /api/v1/public/capabilities                官网能力广场（仅 stable + 白名单 + IP 限流）

行为契约级口径：
- 管理端写路径副作用：capability_assets / capability_plugins / capability_experts /
  capability_teams 落库；悬空专家引用 → 422 且零落库
- 公开端：非 stable 不外泄；字段白名单投影（file_path/sync_state 等内部字段不得出现）；
  超 RATE_LIMIT_PER_MIN → 429
- GET /api/v1/capabilities（列表）已由 test_capability_catalog.py 覆盖，不在本文件

finding F-1（B1c 记录，B5 已修复）：/plugins/{name} /experts/{name} /teams/{name}
曾被先注册的 /{asset_type}/{name} 动态段遮蔽（恒 404）——B5 调整注册顺序
（静态段先于动态段，capabilities.py 文件头有防线注释），三条契约用例已转正。
"""
import asyncio
import json

import pytest
from sqlalchemy import select

from platform_core.models.capability import (
    CapabilityAsset,
    CapabilityExpert,
    CapabilityPlugin,
    CapabilityTeam,
)

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
        # 不声明 mcpServers：verify 管线的 degraded 分支
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


def _seed_via_http_scan(db_client, viewer_client):
    """经 HTTP 扫描端点播种插件 + 专家（扫描端点本身即被测路由）"""
    p = db_client.post("/api/v1/capabilities/scan-plugins")
    e = db_client.post("/api/v1/capabilities/scan-experts")
    assert p.status_code == 200 and e.status_code == 200, (p.text, e.text)


# ---------------------------------------------------------------------------
# POST /api/v1/capabilities/scan-plugins
# ---------------------------------------------------------------------------

def test_scan_plugins_ok(db_client, viewer_client, db_engine, db_session, cap_library):
    """viewer（require_login 下最低角色）扫描：200 摘要 + asset/detail 落库"""
    resp = db_client.post("/api/v1/capabilities/scan-plugins")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["succeeded"] == 1
    assert data["failed"] == 0

    assets = _query_all(db_session, select(CapabilityAsset).where(
        CapabilityAsset.asset_type == "plugin"))
    assert len(assets) == 1  # 副作用：恰好一条插件资产
    assert assets[0].name == PLUGIN_NAME
    details = _query_all(db_session, select(CapabilityPlugin))
    assert len(details) == 1
    assert details[0].version == "1.2.3"
    assert details[0].mcp_servers == {}


def test_scan_plugins_bad_dir_counted_failed(db_client, viewer_client, db_engine, db_session, cap_library):
    """缺 plugin.json 的目录：单插件失败不中断整批（failed=1），坏目录零落库"""
    (cap_library / "plugins" / "broken-plugin").mkdir()
    resp = db_client.post("/api/v1/capabilities/scan-plugins")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 2
    assert data["succeeded"] == 1
    assert data["failed"] == 1
    assert data["failed_names"] == ["broken-plugin"]

    names = {a.name for a in _query_all(db_session, select(CapabilityAsset).where(
        CapabilityAsset.asset_type == "plugin"))}
    assert names == {PLUGIN_NAME}  # 坏目录零落库


def test_scan_plugins_anonymous_401(client):
    assert client.post("/api/v1/capabilities/scan-plugins").status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/capabilities/plugins/{name} + POST .../verify
# ---------------------------------------------------------------------------
# F-1（B1c 发现，B5 已修复）：GET /{asset_type}/{name} 动态段曾先于
# /plugins/{name} /experts/{name} /teams/{name} 注册，三条静态段详情路由被吞
# （asset_type 取到复数形式 → 恒 404）。B5 将动态段移至文件末尾注册并加
# 防线注释（同 skills.py），以下三条契约用例已按修复后行为转正。


def test_plugin_detail_contract(db_client, viewer_client, db_engine, db_session, cap_library):
    """契约：插件详情 200 + manifest 投影（B5 修复路由遮蔽后可用）"""
    _seed_via_http_scan(db_client, viewer_client)
    resp = db_client.get(f"/api/v1/capabilities/plugins/{PLUGIN_NAME}")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["name"] == PLUGIN_NAME
    assert data["version"] == "1.2.3"
    assert data["health_status"] == "unknown"  # 未验证前健康态未知


def test_plugin_detail_anonymous_401(client):
    """匿名 401：require_login 守卫在 handler 前生效"""
    assert client.get(f"/api/v1/capabilities/plugins/{PLUGIN_NAME}").status_code == 401


def test_plugin_verify_no_mcp_degraded(db_client, viewer_client, db_engine, db_session, cap_library):
    """未声明 MCP servers 的插件验证 → degraded，健康态落库（副作用）"""
    _seed_via_http_scan(db_client, viewer_client)
    resp = db_client.post(f"/api/v1/capabilities/plugins/{PLUGIN_NAME}/verify")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["health"] == "degraded"
    assert "未声明" in data["detail"]["error"]

    details = _query_all(db_session, select(CapabilityPlugin))
    assert details[0].health_status == "degraded"   # 副作用：健康态持久化
    assert details[0].last_verified_at is not None


def test_plugin_verify_unknown_404(db_client, viewer_client, db_engine, db_session, cap_library):
    _seed_via_http_scan(db_client, viewer_client)
    resp = db_client.post("/api/v1/capabilities/plugins/ghost/verify")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_plugin_verify_anonymous_401(client):
    assert client.post(f"/api/v1/capabilities/plugins/{PLUGIN_NAME}/verify").status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/capabilities/scan-experts + GET .../experts/{name}
# ---------------------------------------------------------------------------

def test_scan_experts_ok(db_client, viewer_client, db_engine, db_session, cap_library):
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


def test_expert_detail_contract(db_client, viewer_client, db_engine, db_session, cap_library):
    """契约：专家详情 200 + tools/model_pref 投影（B5 修复路由遮蔽后可用）"""
    _seed_via_http_scan(db_client, viewer_client)
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

def test_capability_detail_ok_and_404(db_client, viewer_client, db_engine, db_session, cap_library):
    """统一详情路由：动态段 (asset_type, name) 二段式不被 /plugins /experts 吞掉"""
    _seed_via_http_scan(db_client, viewer_client)
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


def test_team_upsert_create_then_update(db_client, viewer_client, db_engine, db_session, cap_library):
    _seed_via_http_scan(db_client, viewer_client)

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


def test_team_upsert_dangling_ref_422(db_client, viewer_client, db_engine, db_session, cap_library):
    """悬空专家引用 → 422，且零落库（副作用断言：无 expert_team 行）"""
    _seed_via_http_scan(db_client, viewer_client)
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


def test_team_detail_contract(db_client, viewer_client, db_engine, db_session, cap_library):
    """契约：专家团详情 200 + leader/members/workflow 投影（B5 修复路由遮蔽后可用）"""
    _seed_via_http_scan(db_client, viewer_client)
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


def test_team_export_ok_and_404(db_client, viewer_client, db_engine, db_session, cap_library):
    _seed_via_http_scan(db_client, viewer_client)
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
    """直接落读模型行：skill stable / skill experimental / expert stable"""

    async def _go():
        async with db_session() as s:
            s.add(CapabilityAsset(asset_type="skill", name="pub-skill",
                                  status="stable", category="cat-a"))
            s.add(CapabilityAsset(asset_type="skill", name="draft-skill",
                                  status="experimental", category="cat-a"))
            s.add(CapabilityAsset(asset_type="expert", name="pub-expert",
                                  status="stable", category="cat-b"))
            await s.commit()

    asyncio.run(_go())


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


def test_public_capabilities_invalid_type_falls_back_skill(db_client, db_engine, db_session, rate_redis):
    """非法 type 收敛为 skill（不 4xx、不空列表）"""
    _seed_public_assets(db_session)
    resp = db_client.get("/api/v1/public/capabilities", params={"type": "bogus"})
    assert resp.status_code == 200
    names = [i["name"] for i in resp.json()["data"]["items"]]
    assert names == ["pub-skill"]  # 兜底到 skill：不含 expert 行


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
