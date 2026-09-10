"""T-26 FR-35 我的安装：GWT-35.1…35.7 + 40.2。35.4/35.7 与 35.5 分夹具。"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from backend.services.power_market import MARKET_READONLY_ROLE_CODE
from backend.tests.fr33_support import seed_include_parent
from backend.tests.t25_support import (
    bind_actor,
    live_install_count,
    live_installs,
    seed_listed,
    seed_tenant,
    subscribe_url,
)
from platform_core.models.capability import CapabilityAsset

_INSTALLS = "/api/v1/capabilities/installs"
_FORBIDDEN = ("已在你的宿主里运行", "启用到宿主", "enable-host")
_EMPTY_COPY = "还没有订阅的能力"
_DELISTED = "已下架"
_NO_RESUB = "已下架，不能新订"
_INSTALL_READONLY = "当前账号不能改安装。请联系企业管理员。"


@pytest.fixture
def tid(db_session) -> int:
    return seed_tenant(db_session, "t26-op")


@pytest.fixture
def op_client(app, db_client, tid):
    bind_actor(app, role="operator", tenant_id=tid, tenant_role="operator")
    return db_client


def _post(client, asset_type: str, name: str, host: str = "grok"):
    return client.post(subscribe_url(asset_type, name), json={"host": host})


def _items(client) -> list[dict]:
    resp = client.get(_INSTALLS)
    assert resp.status_code == 200, resp.text
    return list(resp.json()["data"]["items"])


def _by_name(items: list[dict], name: str) -> dict:
    return next(row for row in items if row["asset_name"] == name)


def _patch(client, install_id: int, **body):
    return client.patch(f"{_INSTALLS}/{install_id}", json=body)


def _delete(client, install_id: int):
    return client.delete(f"{_INSTALLS}/{install_id}")


def _set_asset(db_session, name: str, **fields) -> None:
    import asyncio

    async def _go():
        async with db_session() as s:
            row = (await s.execute(
                select(CapabilityAsset).where(CapabilityAsset.name == name)
            )).scalar_one()
            for key, value in fields.items():
                setattr(row, key, value)
            await s.commit()

    asyncio.run(_go())


def _assert_no_host_runtime(payload) -> None:
    text = payload if isinstance(payload, str) else str(payload)
    for token in _FORBIDDEN:
        assert token not in text


def test_gwt_35_1_two_rows_can_uninstall(op_client, db_engine, db_session, tid):
    seed_listed(db_session, name="g351-a")
    seed_listed(db_session, name="g351-b")
    assert _post(op_client, "skill", "g351-a").status_code == 200
    assert _post(op_client, "skill", "g351-b").status_code == 200
    items = _items(op_client)
    names = {row["asset_name"] for row in items}
    assert names == {"g351-a", "g351-b"}
    assert all(row["can_uninstall"] for row in items)
    first = items[0]
    gone = _delete(op_client, first["id"])
    assert gone.status_code == 200, gone.text
    left = {row["asset_name"] for row in _items(op_client)}
    assert first["asset_name"] not in left
    assert names - {first["asset_name"]} <= left


def test_gwt_35_1_production_operator_shape(
    app, db_client, db_engine, db_session, tid,
):
    """member_service 邀请经办：User.role=viewer + tenant_role=operator。"""
    bind_actor(app, role="operator", tenant_id=tid, tenant_role="operator")
    seed_listed(db_session, name="g351-prod")
    assert _post(db_client, "skill", "g351-prod").status_code == 200
    bind_actor(app, role="viewer", tenant_id=tid, tenant_role="operator")
    row = _by_name(_items(db_client), "g351-prod")
    assert row["can_uninstall"] is True
    gone = _delete(db_client, row["id"])
    assert gone.status_code == 200, gone.text
    assert gone.json()["code"] != MARKET_READONLY_ROLE_CODE
    assert live_install_count(db_session) == 0


def test_gwt_35_2_empty_not_load_fail(op_client, db_engine, db_session, tid):
    resp = op_client.get(_INSTALLS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "SUCCESS"
    assert body["data"]["total"] == 0
    assert body["data"]["items"] == []
    assert live_install_count(db_session) == 0
    _assert_no_host_runtime(resp.text)
    assert _EMPTY_COPY not in resp.text  # 空句在 UI；接口空 ≠ 加载失败


def test_gwt_35_3_unlist_residual_operator_can_uninstall(
    op_client, db_engine, db_session, tid,
):
    seed_listed(db_session, name="g353-row")
    assert _post(op_client, "skill", "g353-row").status_code == 200
    _set_asset(db_session, "g353-row", listing_state="unlisted")
    items = _items(op_client)
    row = _by_name(items, "g353-row")
    assert row["delisted"] is True
    assert row["delisted_label"] == _DELISTED
    assert row["can_uninstall"] is True
    assert row["resubscribe_allowed"] is False
    assert row["resubscribe_hint"] == _NO_RESUB
    assert row["flags_locked"] is False
    again = _post(op_client, "skill", "g353-row")
    assert again.json()["code"] == "MARKET_NOT_FOUND"
    assert _DELISTED not in again.json()["message"]
    gone = _delete(op_client, row["id"])
    assert gone.status_code == 200, gone.text
    assert all(item["asset_name"] != "g353-row" for item in _items(op_client))


def test_gwt_35_4_blacklist_row_flags_locked_operator_can_uninstall(
    op_client, db_engine, db_session, tid,
):
    seed_listed(db_session, name="g354-black")
    assert _post(op_client, "skill", "g354-black").status_code == 200
    _set_asset(db_session, "g354-black", status="blacklist")
    row = _by_name(_items(op_client), "g354-black")
    assert row["flags_locked"] is True
    assert row["can_change_flags"] is False
    assert row["can_uninstall"] is True
    patched = _patch(op_client, row["id"], enabled=0)
    assert patched.json()["code"] != MARKET_READONLY_ROLE_CODE
    assert patched.status_code >= 400
    trust = _patch(op_client, row["id"], trusted=1)
    assert trust.json()["code"] != MARKET_READONLY_ROLE_CODE
    live = live_installs(db_session)
    assert len(live) == 1
    assert int(live[0].enabled) == 1
    assert int(live[0].trusted) == 0
    assert _delete(op_client, row["id"]).status_code == 200


def test_gwt_35_7_uninstall_blacklist_row_others_stay(
    op_client, db_engine, db_session, tid,
):
    seed_listed(db_session, name="g357-keep")
    seed_listed(db_session, name="g357-black")
    assert _post(op_client, "skill", "g357-keep").status_code == 200
    assert _post(op_client, "skill", "g357-black").status_code == 200
    _set_asset(db_session, "g357-black", status="blacklist")
    black = _by_name(_items(op_client), "g357-black")
    keep_id = _by_name(_items(op_client), "g357-keep")["id"]
    assert _delete(op_client, black["id"]).status_code == 200
    left = _items(op_client)
    names = {row["asset_name"] for row in left}
    assert names == {"g357-keep"}
    assert left[0]["id"] == keep_id
    assert live_install_count(db_session) == 1


def test_gwt_35_5_readonly_refuses_including_blacklist(
    app, db_client, db_engine, db_session, tid,
):
    bind_actor(app, role="operator", tenant_id=tid, tenant_role="operator")
    seed_listed(db_session, name="g355-black")
    seed_listed(db_session, name="g355-ok")
    assert _post(db_client, "skill", "g355-black").status_code == 200
    assert _post(db_client, "skill", "g355-ok").status_code == 200
    _set_asset(db_session, "g355-black", status="blacklist")
    bind_actor(app, role="viewer", tenant_id=tid, tenant_role="viewer")
    items = _items(db_client)
    assert {row["asset_name"] for row in items} == {"g355-black", "g355-ok"}
    assert all(row["can_uninstall"] is False for row in items)
    assert all(row["can_change_flags"] is False for row in items)
    black = _by_name(items, "g355-black")
    ok_row = _by_name(items, "g355-ok")
    for target, body in (
        (black["id"], {"enabled": 0}),
        (black["id"], {"trusted": 1}),
        (ok_row["id"], {"enabled": 0}),
    ):
        resp = _patch(db_client, target, **body)
        assert resp.json()["code"] == MARKET_READONLY_ROLE_CODE
        assert resp.json()["message"] == _INSTALL_READONLY
    for target in (black["id"], ok_row["id"]):
        resp = _delete(db_client, target)
        assert resp.json()["code"] == MARKET_READONLY_ROLE_CODE
        assert resp.json()["message"] == _INSTALL_READONLY
    assert live_install_count(db_session) == 2
    live = {r.asset_id: (int(r.enabled), int(r.trusted)) for r in live_installs(db_session)}
    assert set(live.values()) == {(1, 0)}


def test_gwt_35_6_uninstall_plugin_keeps_child_skill(
    op_client, db_engine, db_session, tid,
):
    seed_include_parent(db_session, parent="g356-plug", children=[{"name": "g356-skill"}])
    assert _post(op_client, "plugin", "g356-plug").status_code == 200
    assert _post(op_client, "skill", "g356-skill").status_code == 200
    plug = _by_name(_items(op_client), "g356-plug")
    assert _delete(op_client, plug["id"]).status_code == 200
    left = _items(op_client)
    assert {row["asset_name"] for row in left} == {"g356-skill"}
    assert live_install_count(db_session) == 1


def test_gwt_40_2_no_enable_host_copy(op_client, db_engine, db_session, tid):
    seed_listed(db_session, name="g402-row")
    created = _post(op_client, "skill", "g402-row")
    listed = op_client.get(_INSTALLS)
    row = _by_name(listed.json()["data"]["items"], "g402-row")
    patched = _patch(op_client, row["id"], enabled=1)
    _assert_no_host_runtime(created.text)
    _assert_no_host_runtime(listed.text)
    _assert_no_host_runtime(patched.text)
    assert "enable-host" not in listed.text.lower()


def test_gwt_35_4_soft_delete_asset_flags_locked(
    op_client, db_engine, db_session, tid,
):
    seed_listed(db_session, name="g354-soft")
    assert _post(op_client, "skill", "g354-soft").status_code == 200
    _set_asset(db_session, "g354-soft", deleted_at=datetime.now(timezone.utc))
    row = _by_name(_items(op_client), "g354-soft")
    assert row["flags_locked"] is True
    assert row["can_change_flags"] is False
    assert row["can_uninstall"] is True
    patched = _patch(op_client, row["id"], trusted=1)
    assert patched.json()["code"] != MARKET_READONLY_ROLE_CODE
    assert int(live_installs(db_session)[0].trusted) == 0
