"""T-29 FR-38 / FR-41：源登记/同步；第三方不 listed；ADR-0012；D16/D5。"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from sqlalchemy import inspect, select

from backend.tests.fr33_support import fr33_asset, seed_rows
from backend.tests.t25_support import bind_actor, seed_listed, seed_tenant, subscribe_url
from platform_core.models.capability import CapabilityAsset

_SRC = "/api/v1/capabilities/sources"
_SCAN = "/api/v1/capabilities/scan-plugins"
_CAP = "/api/v1/public/capabilities"
_LISTING = "/api/v1/capabilities/{}/{}/listing"
_CORRECT = "/api/v1/capabilities/{}/{}/correct"
_FIXTURE = "example-pdf-extractor"
_SWITCHED = "已切换到源注册表"
_FAKE_SOURCE = "zcode_local"
_UNSUPPORTED = "未支持"


class _RateLimitRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, ttl):
        return True

    async def set(self, *args, **kwargs):
        return True

    async def eval(self, *args, **kwargs):
        return 1


def _rate(monkeypatch):
    fake = _RateLimitRedis()

    async def _fake(key: str = "DEFAULT"):
        return fake

    import backend.app.api.v1.public_skills as pub
    monkeypatch.setattr(pub, "get_async_redis", _fake)
    return fake


def _query(db_session, stmt):
    async def _go():
        async with db_session() as s:
            return list((await s.execute(stmt)).scalars().all())
    return asyncio.run(_go())


@pytest.fixture
def library_root(tmp_path: Path):
    from config import settings

    original = settings.get("SKILLS.LIBRARY_ROOT")
    settings.set("SKILLS.LIBRARY_ROOT", str(tmp_path))
    (tmp_path / "plugins").mkdir(parents=True, exist_ok=True)
    (tmp_path / "skills").mkdir(parents=True, exist_ok=True)
    yield tmp_path
    settings.set("SKILLS.LIBRARY_ROOT", original)


def _write_plugin(root: Path, name: str, skills: list[str] | None = None, *, broken: bool = False) -> Path:
    plugin = root / name
    plugin.mkdir(parents=True, exist_ok=True)
    if broken:
        (plugin / "plugin.json").write_text("{not-json", encoding="utf-8")
        return plugin
    (plugin / "plugin.json").write_text(json.dumps({
        "name": name, "description": name, "version": "1.0.0", "license": "MIT",
    }), encoding="utf-8")
    for skill in skills or []:
        d = plugin / "skills" / skill
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {skill}\ndescription: {skill}\n---\n# {skill}\n",
            encoding="utf-8",
        )
    return plugin


def _register(client, name: str, uri: str, kind: str = "local"):
    return client.post(_SRC, json={"name": name, "source_kind": kind, "uri": uri})


def _sync(client, name: str):
    return client.post(f"{_SRC}/{name}/sync")


def test_adr_0012_uq_asset_type_name_alive_unchanged():
    table = inspect(CapabilityAsset)
    uq = [c for c in CapabilityAsset.__table__.constraints if c.name == "uq_asset_type_name_alive"]
    assert len(uq) == 1
    cols = [c.name for c in uq[0].columns]
    assert cols == ["asset_type", "name", "alive_flag"]
    assert "source_id" not in cols
    assert table is not None


def test_gwt_38_3_tenant_cannot_register(db_client, db_session, library_root):
    from conftest import make_platform_admin_headers, make_tenant_owner_headers

    pa = make_platform_admin_headers(db_session)
    tenant, _ = make_tenant_owner_headers(db_session, slug="t29-38-3")
    before = db_client.get(_SRC, headers=pa)
    assert before.status_code == 200
    resp = db_client.post(_SRC, json={
        "name": "tenant-src", "source_kind": "local", "uri": str(library_root),
    }, headers=tenant)
    assert resp.status_code == 404
    assert resp.json()["code"] == "HTTP_404"
    after = db_client.get(_SRC, headers=pa)
    assert after.status_code == 200
    assert before.json()["data"]["items"] == after.json()["data"]["items"]


def test_gwt_38_4_url_kind_unsupported(db_client, platform_admin_client, db_session):
    resp = platform_admin_client.post(_SRC, json={
        "name": "web-src", "source_kind": "url", "uri": "https://example.invalid/tree",
    })
    assert resp.status_code in (400, 422)
    body = resp.json()
    text = (body.get("message") or "") + json.dumps(body, ensure_ascii=False)
    assert _UNSUPPORTED in text
    listed = platform_admin_client.get(_SRC)
    names = []
    if listed.status_code == 200:
        names = [i["name"] for i in listed.json()["data"]["items"]]
    assert "web-src" not in names


def test_gwt_38_1_sync_counts_third_party_unlisted(
    db_client, platform_admin_client, db_session, library_root,
):
    tree = library_root / "src-a"
    _write_plugin(tree, "pack-ok", ["short-name"])
    created = _register(platform_admin_client, "src-a", str(tree))
    assert created.status_code in (200, 201), created.text
    synced = _sync(platform_admin_client, "src-a")
    assert synced.status_code == 200, synced.text
    data = synced.json()["data"]
    assert data["succeeded"] >= 1
    assert "failed" in data
    rows = _query(db_session, select(CapabilityAsset).where(
        CapabilityAsset.name.in_(("pack-ok", "pack-ok__short-name")),
    ))
    assert rows
    assert all(r.listing_state != "listed" for r in rows)
    bundled = [r for r in rows if r.asset_type == "skill"]
    assert any(r.name == "pack-ok__short-name" for r in bundled)
    assert all(r.title != r.name for r in bundled if r.name.startswith("pack-ok__"))


def test_adr_0012_collision_second_source_fails(
    db_client, platform_admin_client, db_session, library_root,
):
    a = library_root / "src-a"
    b = library_root / "src-b"
    _write_plugin(a, "dup-plug", ["alpha"])
    _write_plugin(b, "dup-plug", ["beta"])
    assert _register(platform_admin_client, "src-a", str(a)).status_code in (200, 201)
    assert _register(platform_admin_client, "src-b", str(b)).status_code in (200, 201)
    first = _sync(platform_admin_client, "src-a")
    assert first.status_code == 200, first.text
    second = _sync(platform_admin_client, "src-b")
    assert second.status_code == 200, second.text
    data = second.json()["data"]
    assert data["failed"] >= 1
    reasons = data.get("failed_items") or data.get("failures") or []
    assert reasons
    plug = _query(db_session, select(CapabilityAsset).where(
        CapabilityAsset.asset_type == "plugin", CapabilityAsset.name == "dup-plug",
    ))
    assert len(plug) == 1
    assert plug[0].name == "dup-plug"


def test_gwt_38_2_partial_failure_keeps_success(
    db_client, platform_admin_client, db_session, library_root,
):
    tree = library_root / "src-partial"
    for i in range(12):
        _write_plugin(tree, f"ok-{i:02d}")
    _write_plugin(tree, "bad-01", broken=True)
    _write_plugin(tree, "bad-02", broken=True)
    _register(platform_admin_client, "src-partial", str(tree))
    synced = _sync(platform_admin_client, "src-partial")
    assert synced.status_code == 200, synced.text
    data = synced.json()["data"]
    assert data["succeeded"] == 12
    assert data["failed"] == 2
    items = data.get("failed_items") or data.get("failures") or []
    assert len(items) == 2
    names = {a.name for a in _query(db_session, select(CapabilityAsset).where(
        CapabilityAsset.asset_type == "plugin",
    ))}
    assert {f"ok-{i:02d}" for i in range(12)} <= names
    catalog = platform_admin_client.get("/api/v1/capabilities", params={"type": "plugin"})
    assert catalog.status_code == 200
    assert catalog.json()["data"].get("empty") is not True


def test_gwt_38_5_d16_fallback_local_scan(
    db_client, platform_admin_client, db_session, library_root,
):
    from config import settings

    _write_plugin(library_root / "plugins", "local-only")
    original = settings.get("POWER_MARKET.ENABLED")
    settings.set("POWER_MARKET.ENABLED", False)
    resp = platform_admin_client.post(_SCAN)
    assert resp.status_code == 200, resp.text
    body = json.dumps(resp.json(), ensure_ascii=False)
    assert _SWITCHED not in body
    from platform_core.models.capability import CapabilitySource
    sources = _query(db_session, select(CapabilitySource))
    assert all(s.name != _FAKE_SOURCE for s in sources)
    plugins = _query(db_session, select(CapabilityAsset).where(
        CapabilityAsset.asset_type == "plugin",
    ))
    assert {p.name for p in plugins} == {"local-only"}
    settings.set("POWER_MARKET.ENABLED", original)


def test_gwt_38_5_d16_empty_sources_still_local(
    db_client, platform_admin_client, db_session, library_root,
):
    from config import settings

    _write_plugin(library_root / "plugins", "still-local")
    original = settings.get("POWER_MARKET.ENABLED")
    settings.set("POWER_MARKET.ENABLED", True)
    listed = platform_admin_client.get(_SRC)
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"]["items"] == [] or listed.json()["data"].get("total", 0) == 0
    resp = platform_admin_client.post(_SCAN)
    assert resp.status_code == 200, resp.text
    assert _SWITCHED not in json.dumps(resp.json(), ensure_ascii=False)
    from platform_core.models.capability import CapabilitySource
    assert _query(db_session, select(CapabilitySource)) == []
    settings.set("POWER_MARKET.ENABLED", original)


def test_gwt_38_6_correct_third_party_no_source_tree(
    db_client, platform_admin_client, db_session, library_root,
):
    tree = library_root / "src-d5"
    _write_plugin(tree, "third-pack", ["leaf"])
    skill_md = tree / "third-pack" / "skills" / "leaf" / "SKILL.md"
    before = skill_md.read_bytes()
    _register(platform_admin_client, "src-d5", str(tree))
    assert _sync(platform_admin_client, "src-d5").status_code == 200
    row_before = _query(db_session, select(CapabilityAsset).where(
        CapabilityAsset.name == "third-pack__leaf",
    ))[0]
    before_cat = row_before.category
    resp = platform_admin_client.post(_CORRECT.format("skill", "third-pack__leaf"), json={
        "category": "hacked",
    })
    assert resp.status_code == 409
    assert skill_md.read_bytes() == before
    row = _query(db_session, select(CapabilityAsset).where(
        CapabilityAsset.name == "third-pack__leaf",
    ))[0]
    assert row.category == before_cat


def test_gwt_38_7_tenant_correct_rejected(db_client, admin_client, db_session, library_root):
    tree = library_root / "src-d5b"
    _write_plugin(tree, "pack-t", ["leaf"])
    skill_md = tree / "pack-t" / "skills" / "leaf" / "SKILL.md"
    before = skill_md.read_bytes()
    seed_rows(db_session, [fr33_asset(
        name="pack-t__leaf", listing_state="unlisted",
        source_type="source_indexed", category="keep-cat",
    )])
    resp = admin_client.post(
        _CORRECT.format("skill", "pack-t__leaf"), json={"category": "nope"},
    )
    assert resp.status_code == 403
    assert skill_md.read_bytes() == before
    row_after = _query(db_session, select(CapabilityAsset).where(
        CapabilityAsset.name == "pack-t__leaf",
    ))[0]
    assert row_after.category == "keep-cat"


def test_gwt_41_1_fixture_searchable_and_subscribable(
    db_client, platform_admin_client, db_session, monkeypatch, app,
):
    _rate(monkeypatch)
    seed_listed(
        db_session, name=_FIXTURE, status="stable", listing_state="unlisted",
        license="MIT", origin_plugin_name=None, source_type="self_built",
    )
    resp = platform_admin_client.post("/api/v1/capabilities/backfill-first-party")
    assert resp.status_code == 200, resp.text
    row = _query(db_session, select(CapabilityAsset).where(
        CapabilityAsset.name == _FIXTURE,
    ))[0]
    assert row.listing_state == "listed"
    assert row.host_compat is None
    public = db_client.get(_CAP, params={"q": _FIXTURE})
    assert public.status_code == 200, public.text
    names = [i["name"] for i in public.json()["data"]["items"]]
    assert _FIXTURE in names
    tid = seed_tenant(db_session, "t29-op")
    bind_actor(app, role="operator", tenant_id=tid, tenant_role="operator")
    sub = db_client.post(subscribe_url("skill", _FIXTURE), json={"host": "grok"})
    assert sub.status_code == 200, sub.text


def test_gwt_41_2_prefixed_third_party_not_public(
    db_client, db_session, monkeypatch,
):
    _rate(monkeypatch)
    seed_rows(db_session, [fr33_asset(
        name="mattpocock-skills__code-review",
        listing_state="unlisted",
        status="stable",
        source_type="source_indexed",
        title="代码审查",
    )])
    resp = db_client.get(_CAP, params={"q": "code-review"})
    assert resp.status_code == 200, resp.text
    names = [i["name"] for i in resp.json()["data"]["items"]]
    assert "mattpocock-skills__code-review" not in names


def test_gwt_41_3_tenant_cannot_list_third_party(
    db_client, admin_client, db_session,
):
    seed_listed(
        db_session, name="third-list", listing_state="unlisted",
        source_type="source_indexed",
    )
    resp = admin_client.patch(
        _LISTING.format("skill", "third-list"), json={"listing_state": "listed"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "HTTP_404"
    row = _query(db_session, select(CapabilityAsset).where(
        CapabilityAsset.name == "third-list",
    ))[0]
    assert row.listing_state == "unlisted"


def test_gwt_41_4_attach_source_does_not_auto_list(
    db_client, platform_admin_client, db_session, library_root,
):
    tree = library_root / "src-attach"
    _write_plugin(tree, "was-first", ["leaf"])
    seed_listed(
        db_session, name="was-first", asset_type="plugin", category="plugin",
        listing_state="listed", status="stable", source_type="self_built",
        license="MIT",
    )
    _register(platform_admin_client, "src-attach", str(tree))
    synced = _sync(platform_admin_client, "src-attach")
    assert synced.status_code == 200, synced.text
    row = _query(db_session, select(CapabilityAsset).where(
        CapabilityAsset.asset_type == "plugin", CapabilityAsset.name == "was-first",
    ))[0]
    assert row.listing_state != "listed"
    assert row.source_id is not None


def test_hash_fold_nested_copies(
    db_client, platform_admin_client, db_session, library_root,
):
    tree = library_root / "src-fold"
    plugin = _write_plugin(tree, "fold-pack", ["code-review"])
    nested = plugin / "skills" / "engineering" / "code-review"
    nested.mkdir(parents=True)
    src = (plugin / "skills" / "code-review" / "SKILL.md").read_text(encoding="utf-8")
    (nested / "SKILL.md").write_text(src, encoding="utf-8")
    _register(platform_admin_client, "src-fold", str(tree))
    assert _sync(platform_admin_client, "src-fold").status_code == 200
    skills = _query(db_session, select(CapabilityAsset).where(
        CapabilityAsset.asset_type == "skill",
        CapabilityAsset.name.like("fold-pack__%"),
    ))
    assert len(skills) == 1
    assert skills[0].name == "fold-pack__code-review"


def test_migration_037_has_no_attach_source():
    path = Path("backend/alembic/versions/037_t29_capability_sources.py")
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    upgrade = text.split("def upgrade")[1].split("def downgrade")[0]
    assert "zcode_local" not in upgrade
    assert "INSERT INTO" not in upgrade
    assert "listing_state" not in upgrade
    assert "036" in text


def test_im20_confirm_listed_src_sync_still_listed(
    db_client, platform_admin_client, db_session, library_root,
):
    tree = library_root / "src-keep"
    _write_plugin(tree, "keep-pack", ["leaf"])
    assert _register(platform_admin_client, "src-keep", str(tree)).status_code in (200, 201)
    assert _sync(platform_admin_client, "src-keep").status_code == 200
    listed = platform_admin_client.patch(
        _LISTING.format("plugin", "keep-pack"),
        json={"listing_state": "listed", "confirm": True},
    )
    assert listed.status_code == 200, listed.text
    row = _query(db_session, select(CapabilityAsset).where(
        CapabilityAsset.asset_type == "plugin", CapabilityAsset.name == "keep-pack",
    ))[0]
    assert row.listing_state == "listed"
    listed_at = row.listed_at
    assert _sync(platform_admin_client, "src-keep").status_code == 200
    again = _query(db_session, select(CapabilityAsset).where(
        CapabilityAsset.asset_type == "plugin", CapabilityAsset.name == "keep-pack",
    ))[0]
    assert again.listing_state == "listed"
    assert again.listed_at == listed_at


def test_im21_vendor_without_manifest_not_upserted(
    db_client, platform_admin_client, db_session, library_root,
):
    tree = library_root / "src-vendor"
    _write_plugin(tree, "real-pack")
    vendor = tree / "vendor"
    vendor.mkdir()
    (vendor / "readme.txt").write_text("not a plugin", encoding="utf-8")
    assert _register(platform_admin_client, "src-vendor", str(tree)).status_code in (200, 201)
    synced = _sync(platform_admin_client, "src-vendor")
    assert synced.status_code == 200, synced.text
    names = {a.name for a in _query(db_session, select(CapabilityAsset).where(
        CapabilityAsset.asset_type == "plugin",
    ))}
    assert "real-pack" in names
    assert "vendor" not in names
    assert synced.json()["data"]["succeeded"] == 1


def test_im23_git_kind_unsupported(db_client, platform_admin_client, db_session):
    resp = platform_admin_client.post(_SRC, json={
        "name": "git-src", "source_kind": "git", "uri": "https://example.invalid/repo.git",
    })
    assert resp.status_code in (400, 422)
    body = resp.json()
    text = (body.get("message") or "") + json.dumps(body, ensure_ascii=False)
    assert _UNSUPPORTED in text
    listed = platform_admin_client.get(_SRC)
    names = []
    if listed.status_code == 200:
        names = [i["name"] for i in listed.json()["data"]["items"]]
    assert "git-src" not in names


def test_no_auto_alias_on_sync(
    db_client, platform_admin_client, db_session, library_root,
):
    tree = library_root / "src-alias"
    _write_plugin(tree, "alias-pack", ["short"])
    _register(platform_admin_client, "src-alias", str(tree))
    _sync(platform_admin_client, "src-alias")
    from platform_core.models import capability as cap_mod
    assert not hasattr(cap_mod, "CapabilityAlias") or _query(
        db_session, select(getattr(cap_mod, "CapabilityAlias")),
    ) == []


def test_src_sync_plugin_json_commands_creates_unlisted_command_adr0012_slug(
    db_client, platform_admin_client, db_session, library_root,
):
    """src_sync：plugin.json commands → asset_type=command；slug={plugin}__{origin_local_name}；第三方 unlisted。"""
    from platform_core.models.capability import CapabilityAlias, CapabilityCommand

    tree = library_root / "src-cmd"
    plugin = _write_plugin(tree, "cmd-pack", ["leaf"])
    manifest_path = plugin / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["commands"] = {
        "/run-task": {
            "name": "run-task",
            "description": "跑任务",
            "prompt": "# run-task body",
        },
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    cmd_dir = plugin / "commands"
    cmd_dir.mkdir()
    (cmd_dir / "run-task.md").write_text(
        "---\nname: run-task\ndescription: 跑任务\n---\n# run-task body\n",
        encoding="utf-8",
    )
    created = _register(platform_admin_client, "src-cmd", str(tree))
    assert created.status_code in (200, 201), created.text
    synced = _sync(platform_admin_client, "src-cmd")
    assert synced.status_code == 200, synced.text

    rows = _query(db_session, select(CapabilityAsset).where(
        CapabilityAsset.asset_type == "command",
        CapabilityAsset.deleted_at.is_(None),
    ))
    assert len(rows) == 1
    row = rows[0]
    assert row.name == "cmd-pack__run-task"
    assert row.origin_local_name == "run-task"
    assert row.origin_plugin_name == "cmd-pack"
    assert row.title == "run-task"
    assert row.title != row.name
    assert not row.title.startswith("cmd-pack__")
    assert row.listing_state == "unlisted"
    details = _query(db_session, select(CapabilityCommand))
    assert len(details) == 1
    assert details[0].asset_id == row.id
    assert details[0].slash == "run-task"
    assert _query(db_session, select(CapabilityAlias)) == []

    again = _sync(platform_admin_client, "src-cmd")
    assert again.status_code == 200, again.text
    kept = _query(db_session, select(CapabilityAsset).where(
        CapabilityAsset.asset_type == "command",
        CapabilityAsset.name == "cmd-pack__run-task",
    ))
    assert len(kept) == 1
    assert kept[0].listing_state == "unlisted"


def test_src_sync_retracts_commands_removed_from_manifest(
    db_client, platform_admin_client, db_session, library_root,
):
    """C35-QA-04：manifest 去掉命令后，再同步必须软删，不得残留治理行。"""
    tree = library_root / "src-cmd-retract"
    plugin = _write_plugin(tree, "retract-pack", ["leaf"])
    manifest_path = plugin / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["commands"] = {
        "/keep-me": {"name": "keep-me", "description": "留"},
        "/drop-me": {"name": "drop-me", "description": "删"},
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    cmd_dir = plugin / "commands"
    cmd_dir.mkdir()
    (cmd_dir / "keep-me.md").write_text("---\nname: keep-me\n---\n# keep\n", encoding="utf-8")
    (cmd_dir / "drop-me.md").write_text("---\nname: drop-me\n---\n# drop\n", encoding="utf-8")
    created = _register(platform_admin_client, "src-cmd-retract", str(tree))
    assert created.status_code in (200, 201), created.text
    first = _sync(platform_admin_client, "src-cmd-retract")
    assert first.status_code == 200, first.text
    names = {
        r.name for r in _query(db_session, select(CapabilityAsset).where(
            CapabilityAsset.asset_type == "command",
            CapabilityAsset.deleted_at.is_(None),
        ))
    }
    assert names == {"retract-pack__keep-me", "retract-pack__drop-me"}

    (cmd_dir / "drop-me.md").unlink()
    manifest["commands"] = {"/keep-me": {"name": "keep-me", "description": "留"}}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    second = _sync(platform_admin_client, "src-cmd-retract")
    assert second.status_code == 200, second.text
    alive = _query(db_session, select(CapabilityAsset).where(
        CapabilityAsset.asset_type == "command",
        CapabilityAsset.deleted_at.is_(None),
    ))
    assert [r.name for r in alive] == ["retract-pack__keep-me"]
    gone = _query(db_session, select(CapabilityAsset).where(
        CapabilityAsset.name == "retract-pack__drop-me",
    ))
    assert len(gone) == 1
    assert gone[0].deleted_at is not None
    assert gone[0].sync_state == "gone"
