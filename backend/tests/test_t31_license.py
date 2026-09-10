"""T-31 FR-42：许可闸；已订与解析不被拆；特例仅超管。GWT-42.1…42.6。"""
import asyncio

import pytest
from sqlalchemy import select

from backend.services.power_market import MARKET_NOT_FOUND_CODE
from backend.tests.fr33_support import fr33_asset, seed_rows
from backend.tests.t25_support import (
    bind_actor,
    live_install_count,
    live_installs,
    seed_listed,
    seed_tenant,
    subscribe_url,
)
from backend.tests.t27_support import refs_url, seed_agent_collection
from platform_core.models.capability import CapabilityAsset, CapabilityInstall

_OVERRIDE = "/api/v1/capabilities/{}/{}/license-override"
_INSTALLS = "/api/v1/capabilities/installs"
_PUBLIC = "/api/v1/public/skills"
_PUBLIC_CAPS = "/api/v1/public/capabilities"


def _override_url(asset_type: str, name: str) -> str:
    return _OVERRIDE.format(asset_type, name)


def _public_names(client, path: str = _PUBLIC) -> tuple[set[str], int]:
    resp = client.get(path)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    return {i["name"] for i in data["items"]}, int(data["total"])


def _set_asset(db_session, name: str, **fields) -> None:
    async def _go():
        async with db_session() as s:
            row = (await s.execute(
                select(CapabilityAsset).where(CapabilityAsset.name == name)
            )).scalar_one()
            for key, value in fields.items():
                setattr(row, key, value)
            await s.commit()

    asyncio.run(_go())


def _asset_override(db_session, name: str) -> int:
    async def _go():
        async with db_session() as s:
            row = (await s.execute(
                select(CapabilityAsset).where(CapabilityAsset.name == name)
            )).scalar_one()
            return int(row.public_license_override or 0)

    return asyncio.run(_go())


def _live_for_tenant(db_session, tenant_id: int) -> list[CapabilityInstall]:
    return [row for row in live_installs(db_session) if int(row.tenant_id) == tenant_id]


@pytest.fixture
def tid(db_session) -> int:
    return seed_tenant(db_session, "t31-op")


@pytest.fixture
def op_client(app, db_client, tid):
    bind_actor(app, role="operator", tenant_id=tid, tenant_role="operator")
    return db_client


def test_gwt_42_1_unlicensed_not_in_public_total(
    db_client, db_engine, db_session, op_client, tid,
):
    """Given 许可在默认不允许之列且未放行 When 访客逛 Then 该项不出现。"""
    seed_rows(db_session, [
        fr33_asset(name="g421-mit", license="MIT"),
        fr33_asset(name="g421-nolic", license="NOASSERTION"),
    ])
    names, total = _public_names(db_client)
    cap_names, cap_total = _public_names(db_client, _PUBLIC_CAPS)
    assert "g421-nolic" not in names
    assert "g421-nolic" not in cap_names
    assert "g421-mit" in names
    assert total == cap_total == 1
    denied = op_client.post(
        subscribe_url("skill", "g421-nolic"), json={"host": "grok"},
    )
    assert denied.json()["code"] == MARKET_NOT_FOUND_CODE
    assert live_install_count(db_session) == 0


def test_gwt_42_2_override_appears_still_gated(
    db_client, platform_admin_client, db_session,
):
    """Given 超管已放行 When 访客逛 Then 可出现（仍要过上架与治理闸）。"""
    seed_rows(db_session, [
        fr33_asset(name="g422-ok", license="NOASSERTION"),
        fr33_asset(
            name="g422-unlist", license="NOASSERTION", listing_state="unlisted",
        ),
        fr33_asset(name="g422-exp", license="NOASSERTION", status="experimental"),
    ])
    for name in ("g422-ok", "g422-unlist", "g422-exp"):
        resp = platform_admin_client.patch(
            _override_url("skill", name), json={"public_license_override": 1},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["public_license_override"] == 1
    names, total = _public_names(db_client)
    assert names == {"g422-ok"}
    assert total == 1
    assert "g422-unlist" not in names and "g422-exp" not in names


def test_gwt_42_3_tenant_cannot_override_public_unchanged(
    db_client, admin_client, db_session,
):
    """Given 租户 When 放行许可 Then 拒绝；公开集合不变。"""
    seed_listed(db_session, name="g423-nolic", license="NOASSERTION")
    before_names, before_total = _public_names(db_client)
    resp = admin_client.patch(
        _override_url("skill", "g423-nolic"), json={"public_license_override": 1},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"
    assert _asset_override(db_session, "g423-nolic") == 0
    after_names, after_total = _public_names(db_client)
    assert after_names == before_names
    assert after_total == before_total
    assert "g423-nolic" not in after_names


def test_gwt_42_4_revoke_keeps_install_operator_can_uninstall(
    app, db_client, db_engine, db_session, tid,
):
    """Given 已订后许可收回 When 打开我的安装 Then 行仍在，经办可卸。"""
    seed_listed(
        db_session, name="g424-row", license="NOASSERTION",
        public_license_override=1,
    )
    bind_actor(app, role="operator", tenant_id=tid, tenant_role="operator")
    created = db_client.post(
        subscribe_url("skill", "g424-row"), json={"host": "grok"},
    )
    assert created.status_code == 200, created.text
    assert live_install_count(db_session) == 1
    bind_actor(app, role="admin", tenant_id=None, tenant_role=None, is_platform_admin=True)
    revoked = db_client.patch(
        _override_url("skill", "g424-row"), json={"public_license_override": 0},
    )
    assert revoked.status_code == 200, revoked.text
    assert _asset_override(db_session, "g424-row") == 0
    names, _total = _public_names(db_client)
    assert "g424-row" not in names
    bind_actor(app, role="operator", tenant_id=tid, tenant_role="operator")
    listed = db_client.get(_INSTALLS)
    assert listed.status_code == 200, listed.text
    items = listed.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["asset_name"] == "g424-row"
    assert items[0]["can_uninstall"] is True
    assert live_install_count(db_session) == 1
    again = db_client.post(
        subscribe_url("skill", "g424-row"), json={"host": "grok"},
    )
    assert again.json()["code"] == MARKET_NOT_FOUND_CODE
    gone = db_client.delete(f"{_INSTALLS}/{items[0]['id']}")
    assert gone.status_code == 200, gone.text
    assert live_install_count(db_session) == 0


def test_gwt_42_5_unlicensed_still_in_ref_list(
    platform_admin_client, db_client, db_session,
):
    """When=超管打开引用列表。许可未放行且非黑名单仍在。"""
    seed_agent_collection(db_session, agent="g425-agent", children=[
        {"name": "g425-skill", "listing_state": "listed", "role": "uses_skill"},
    ])
    _set_asset(
        db_session, "g425-skill", license="NOASSERTION", public_license_override=0,
    )
    resp = platform_admin_client.get(refs_url("agent", "g425-agent"))
    assert resp.status_code == 200, resp.text
    names = {i["name"] for i in resp.json()["data"]["items"]}
    assert "g425-skill" in names
    public, _total = _public_names(db_client)
    assert "g425-skill" not in public


def test_gwt_42_6_tenant_a_cannot_tear_down_b_install(
    app, db_client, db_engine, db_session,
):
    """企业 A 经办企图用许可闸拆企业 B 的已订行 → 拒绝；B 的安装行不变。"""
    tid_a = seed_tenant(db_session, "t31-a")
    tid_b = seed_tenant(db_session, "t31-b")
    seed_listed(
        db_session, name="g426-row", license="NOASSERTION",
        public_license_override=1,
    )
    bind_actor(app, role="operator", tenant_id=tid_b, tenant_role="operator")
    created = db_client.post(
        subscribe_url("skill", "g426-row"), json={"host": "grok"},
    )
    assert created.status_code == 200, created.text
    b_rows = _live_for_tenant(db_session, tid_b)
    assert len(b_rows) == 1
    b_id, b_enabled = int(b_rows[0].id), int(b_rows[0].enabled)
    bind_actor(app, role="operator", tenant_id=tid_a, tenant_role="operator")
    gate = db_client.patch(
        _override_url("skill", "g426-row"), json={"public_license_override": 0},
    )
    assert gate.status_code == 403
    assert gate.json()["code"] == "FORBIDDEN"
    stolen = db_client.delete(f"{_INSTALLS}/{b_id}")
    assert stolen.status_code == 404
    assert _asset_override(db_session, "g426-row") == 1
    left = _live_for_tenant(db_session, tid_b)
    assert len(left) == 1
    assert int(left[0].id) == b_id
    assert int(left[0].enabled) == b_enabled
    assert left[0].deleted_at is None
    assert live_install_count(db_session) == 1
