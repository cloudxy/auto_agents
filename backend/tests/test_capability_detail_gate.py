"""能力详情闸（审计 B4-4 / BUG-45 / P0-3 回归）

- 非超管读详情只放行「市场开放 + 已上架 + 治理可公开」的资产，其余 404 同形
- 放行时只给公开投影，不含 AI 建议分、同步态、库路径等治理字段
- 插件 mcp_servers 的 env / headers / 敏感 args 一律脱敏（超管也不下发明文）
- 同名孪生行（1 存活 + 1 软删）不再 500
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from backend.tests.fr33_support import fr33_asset, seed_rows
from platform_core.models.capability import CapabilityPlugin

CAP = "/api/v1/capabilities"
SECRET = "sk-live-should-never-leak"


def _seed_plugin(db_session, name: str, *, listing_state: str) -> None:
    async def _go():
        async with db_session() as s:
            asset = fr33_asset(asset_type="plugin", name=name, listing_state=listing_state)
            s.add(asset)
            await s.flush()
            s.add(CapabilityPlugin(
                asset_id=asset.id, version="1.0.0", author="qa", license="MIT",
                mcp_servers={"svc": {
                    "command": "npx",
                    "args": ["-y", "server", "--api-key", SECRET, f"--token={SECRET}"],
                    "env": {"OPENAI_API_KEY": SECRET},
                    "headers": {"Authorization": f"Bearer {SECRET}"},
                }},
            ))
            await s.commit()

    asyncio.run(_go())


def test_tenant_unlisted_skill_detail_404(db_client, admin_client, db_session):
    seed_rows(db_session, [fr33_asset(name="gate-hidden", listing_state="unlisted")])
    assert admin_client.get(f"{CAP}/skill/gate-hidden").status_code == 404


def test_tenant_blacklisted_detail_404(db_client, viewer_client, db_session):
    seed_rows(db_session, [fr33_asset(name="gate-black", status="blacklist")])
    assert viewer_client.get(f"{CAP}/skill/gate-black").status_code == 404


def test_tenant_listed_detail_is_public_projection(db_client, admin_client, db_session):
    seed_rows(db_session, [fr33_asset(name="gate-open", score=88, file_path="skills/gate-open")])
    resp = admin_client.get(f"{CAP}/skill/gate-open")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["name"] == "gate-open"
    for field in ("ai_suggested_score", "sync_state", "file_path", "similar_to"):
        assert field not in data  # 治理字段不外发（score 属公开货架字段）


def test_tenant_detail_404_when_market_closed(db_client, admin_client, db_session):
    from config import settings

    seed_rows(db_session, [fr33_asset(name="gate-closed")])
    settings.set("POWER_MARKET.ENABLED", False)
    try:
        assert admin_client.get(f"{CAP}/skill/gate-closed").status_code == 404
    finally:
        settings.set("POWER_MARKET.ENABLED", True)


def test_platform_admin_sees_unlisted_governance_detail(db_client, platform_admin_client, db_session):
    seed_rows(db_session, [fr33_asset(name="gate-gov", listing_state="unlisted", score=70)])
    resp = platform_admin_client.get(f"{CAP}/skill/gate-gov")
    assert resp.status_code == 200
    assert resp.json()["data"]["listing_state"] == "unlisted"
    assert "score" in resp.json()["data"]


def test_tenant_unlisted_plugin_detail_404(db_client, admin_client, db_session):
    _seed_plugin(db_session, "gate-plugin-hidden", listing_state="unlisted")
    resp = admin_client.get(f"{CAP}/plugins/gate-plugin-hidden")
    assert resp.status_code == 404
    assert SECRET not in resp.text


def test_plugin_detail_redacts_mcp_secrets_for_everyone(
    db_client, platform_admin_client, db_session,
):
    _seed_plugin(db_session, "gate-plugin", listing_state="listed")
    resp = platform_admin_client.get(f"{CAP}/plugins/gate-plugin")
    assert resp.status_code == 200, resp.text
    assert SECRET not in resp.text
    svc = resp.json()["data"]["mcp_servers"]["svc"]
    assert svc["env"] == {"OPENAI_API_KEY": "******"}
    assert svc["headers"] == {"Authorization": "******"}
    assert svc["args"][:4] == ["-y", "server", "--api-key", "******"]
    assert svc["args"][4] == "--token=******"


def test_tenant_listed_plugin_detail_redacted_without_verify_detail(db_client, admin_client, db_session):
    _seed_plugin(db_session, "gate-plugin-open", listing_state="listed")
    resp = admin_client.get(f"{CAP}/plugins/gate-plugin-open")
    assert resp.status_code == 200, resp.text
    assert SECRET not in resp.text
    assert "verify_detail" not in resp.json()["data"]


def test_tenant_unlisted_expert_and_team_404(db_client, admin_client, db_session):
    seed_rows(db_session, [
        fr33_asset(asset_type="expert", name="gate-expert", listing_state="unlisted"),
        fr33_asset(asset_type="expert_team", name="gate-team", listing_state="unlisted"),
    ])
    assert admin_client.get(f"{CAP}/experts/gate-expert").status_code == 404
    assert admin_client.get(f"{CAP}/teams/gate-team").status_code == 404
    assert admin_client.get(f"{CAP}/teams/gate-team/export").status_code == 404


def test_twin_rows_detail_prefers_alive_not_500(db_client, platform_admin_client, db_session):
    """B4-4：同名 1 存活 + 1 软删 → 200 且返回存活行（原先 MultipleResultsFound 500）"""
    dead = fr33_asset(name="gate-twin", title="旧行", deleted_at=datetime.now(timezone.utc))
    seed_rows(db_session, [dead])
    seed_rows(db_session, [fr33_asset(name="gate-twin", title="新行")])
    resp = platform_admin_client.get(f"{CAP}/skill/gate-twin")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["title"] == "新行"


def test_twin_plugin_rows_detail_not_500(db_client, platform_admin_client, db_session):
    async def _go():
        async with db_session() as s:
            s.add(fr33_asset(asset_type="plugin", name="gate-twin-plugin",
                             deleted_at=datetime.now(timezone.utc)))
            await s.commit()

    asyncio.run(_go())
    _seed_plugin(db_session, "gate-twin-plugin", listing_state="listed")
    resp = platform_admin_client.get(f"{CAP}/plugins/gate-twin-plugin")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["version"] == "1.0.0"
