"""T-30 FR-39：命令是独立 catalog 卡，不是插件 JSON 货架；订阅一行不级联。"""
import asyncio

from sqlalchemy import select

from backend.tests.fr33_support import fr33_asset, seed_rows
from backend.tests.t25_support import (
    asset_id_of,
    bind_actor,
    live_install_count,
    live_installs,
    seed_tenant,
    subscribe_url,
)
from platform_core.models.capability import (
    CapabilityAsset,
    CapabilityCommand,
    CapabilityComponent,
    CapabilityPlugin,
)

_CAP = "/api/v1/public/capabilities"
_JSON_SHELF = ('"commands"', "plugin.json", "/shelf-slash")


class _RateLimitRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, ttl):
        return True


def _rate(monkeypatch):
    fake = _RateLimitRedis()

    async def _fake(key: str = "DEFAULT"):
        return fake

    import backend.app.api.v1.public_skills as mod
    monkeypatch.setattr(mod, "get_async_redis", _fake)
    return fake


def _seed_command(
    db_session,
    *,
    name: str,
    slash: str,
    title: str = "",
    listing_state: str = "listed",
    body_md: str = "# cmd body",
    **kwargs,
) -> None:
    async def _go():
        async with db_session() as s:
            row = fr33_asset(
                asset_type="command",
                name=name,
                title=title,
                category="command",
                listing_state=listing_state,
                **kwargs,
            )
            s.add(row)
            await s.flush()
            s.add(CapabilityCommand(
                asset_id=row.id, slash=slash, description="cmd", body_md=body_md,
            ))
            await s.commit()

    asyncio.run(_go())


def _seed_plugin_json_commands(db_session, *, name: str, commands: dict) -> None:
    async def _go():
        async with db_session() as s:
            row = fr33_asset(
                asset_type="plugin", name=name, category="cat-p", title=name,
            )
            s.add(row)
            await s.flush()
            s.add(CapabilityPlugin(
                asset_id=row.id,
                commands=commands,
                manifest={"name": name, "commands": commands},
            ))
            await s.commit()

    asyncio.run(_go())


def test_gwt_39_1_listed_command_card_and_detail(
    db_client, db_engine, db_session, monkeypatch,
):
    _rate(monkeypatch)
    _seed_command(
        db_session, name="pack__run-task", slash="sdlc", title="跑任务",
    )
    seed_rows(db_session, [
        fr33_asset(asset_type="plugin", name="pack", category="cat-p"),
        fr33_asset(name="pack-skill", title="插件技能"),
    ])
    listed = db_client.get(_CAP, params={"type": "command"})
    assert listed.status_code == 200, listed.text
    items = listed.json()["data"]["items"]
    assert [i["name"] for i in items] == ["pack__run-task"]
    assert {i["asset_type"] for i in items} == {"command"}
    assert items[0]["slash"] == "sdlc"
    assert items[0]["title"] == "跑任务"
    blob = listed.text
    for token in _JSON_SHELF:
        assert token not in blob
    detail = db_client.get(f"{_CAP}/command/pack__run-task")
    assert detail.status_code == 200, detail.text
    data = detail.json()["data"]
    assert data["asset_type"] == "command"
    assert data["slash"] == "sdlc"
    assert data["body_md"] == "# cmd body"
    assert data["subscribable"] is True


def test_gwt_39_2_no_listed_command_is_empty_not_plugin_json(
    db_client, db_engine, db_session, monkeypatch,
):
    _rate(monkeypatch)
    _seed_plugin_json_commands(
        db_session,
        name="shelf-plug",
        commands={"/shelf-slash": {"prompt": "not a catalog card"}},
    )
    seed_rows(db_session, [
        fr33_asset(name="other-skill", title="其它技能"),
    ])
    resp = db_client.get(_CAP, params={"type": "command"})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["items"] == []
    assert data["total"] == 0
    blob = resp.text
    for token in _JSON_SHELF:
        assert token not in blob
    assert "shelf-plug" not in blob
    assert "other-skill" not in blob


def test_gwt_39_3_unlisted_slash_not_in_public_search(
    db_client, db_engine, db_session, monkeypatch,
):
    _rate(monkeypatch)
    _seed_command(
        db_session,
        name="ghost__hidden",
        slash="unlisted-slash",
        title="幽灵命令",
        listing_state="unlisted",
    )
    _seed_plugin_json_commands(
        db_session,
        name="json-pack",
        commands={"/unlisted-slash": {"prompt": "from plugin.json"}},
    )
    for q in ("unlisted-slash", "/unlisted-slash"):
        resp = db_client.get(_CAP, params={"q": q})
        assert resp.status_code == 200, resp.text
        names = [i["name"] for i in resp.json()["data"]["items"]]
        types = {i["asset_type"] for i in resp.json()["data"]["items"]}
        assert names == []
        assert "command" not in types
        blob = resp.text
        assert "ghost__hidden" not in blob
        assert "unlisted-slash" not in blob
        assert "/unlisted-slash" not in blob
        assert "plugin.json" not in blob


def test_listed_command_q_hits_slash_not_in_name_or_title(
    db_client, db_engine, db_session, monkeypatch,
):
    """slash 叠在 FR-33 之后：列名/标题不含 slash 时仍能搜到已上架命令。"""
    _rate(monkeypatch)
    _seed_command(
        db_session, name="pack__run-task", slash="sdlc", title="跑任务",
    )
    _seed_command(
        db_session,
        name="ghost__sdlc",
        slash="sdlc",
        title="未上架同 slash",
        listing_state="unlisted",
    )
    resp = db_client.get(_CAP, params={"q": "/sdlc"})
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]["items"]
    names = [i["name"] for i in items]
    assert names == ["pack__run-task"]
    assert items[0]["slash"] == "sdlc"
    assert "ghost__sdlc" not in names


def test_type_command_does_not_include_plugin_or_skill(
    db_client, db_engine, db_session, monkeypatch,
):
    _rate(monkeypatch)
    _seed_command(db_session, name="only-cmd", slash="only", title="仅命令")
    seed_rows(db_session, [
        fr33_asset(asset_type="plugin", name="only-plug", category="cat-p"),
        fr33_asset(name="only-skill", title="仅技能"),
    ])
    resp = db_client.get(_CAP, params={"type": "command"})
    items = resp.json()["data"]["items"]
    assert [i["asset_type"] for i in items] == ["command"]
    assert [i["name"] for i in items] == ["only-cmd"]


def test_subscribe_command_one_row_no_cascade(
    app, db_client, db_engine, db_session,
):
    tid = seed_tenant(db_session, "t30-op")
    bind_actor(app, role="operator", tenant_id=tid, tenant_role="operator")
    _seed_command(db_session, name="t30-cmd", slash="t30", title="可订命令")
    seed_rows(db_session, [
        fr33_asset(asset_type="plugin", name="t30-plug", category="cat-p"),
        fr33_asset(name="t30-skill", title="同包技能"),
    ])

    async def _edges():
        async with db_session() as s:
            parent = (await s.execute(
                select(CapabilityAsset).where(CapabilityAsset.name == "t30-plug")
            )).scalar_one()
            cmd = (await s.execute(
                select(CapabilityAsset).where(CapabilityAsset.name == "t30-cmd")
            )).scalar_one()
            skill = (await s.execute(
                select(CapabilityAsset).where(CapabilityAsset.name == "t30-skill")
            )).scalar_one()
            s.add(CapabilityComponent(
                parent_asset_id=parent.id, child_asset_id=cmd.id, role="bundled_command",
            ))
            s.add(CapabilityComponent(
                parent_asset_id=parent.id, child_asset_id=skill.id, role="bundled_skill",
            ))
            await s.commit()

    asyncio.run(_edges())
    resp = db_client.post(subscribe_url("command", "t30-cmd"), json={"host": "grok"})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["created"] is True
    assert data["message"] == "已订阅到 Grok"
    assert live_install_count(db_session) == 1
    row = live_installs(db_session)[0]
    assert row.asset_id == asset_id_of(db_session, "t30-cmd")
    assert row.host == "grok"
    plug_id = asset_id_of(db_session, "t30-plug")
    skill_id = asset_id_of(db_session, "t30-skill")
    assert row.asset_id not in {plug_id, skill_id}
    assert all(r.asset_id != plug_id for r in live_installs(db_session))
    assert all(r.asset_id != skill_id for r in live_installs(db_session))
    text = resp.text
    assert "礼包" not in text
    assert "安装此插件将获得" not in text
