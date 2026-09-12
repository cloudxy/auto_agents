"""T-19 FR-88 GWT-88.1..88.5：技能/插件同步收回 + 治理目录不含已删行。

三路收回：skills/scan（第一方技能镜像行）、scan-plugins（第一方插件行）、
src_sync（源注册表行，命令已兑同构扩到技能/插件）。
公开商店过滤已兑（T-13 FR-33 谓词含非软删），本文件叠加断言。
"""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest
from sqlalchemy import select

from conftest import make_platform_admin_headers, make_tenant_owner_headers
from platform_core.models.capability import CapabilityAsset
from platform_core.models.skill import Skill

_SCAN_SKILLS = "/api/v1/skills/scan"
_SCAN_PLUGINS = "/api/v1/capabilities/scan-plugins"
_CATALOG = "/api/v1/capabilities"
_SRC = "/api/v1/capabilities/sources"
_LISTING = "/api/v1/capabilities/{}/{}/listing"
_PUB_SKILLS = "/api/v1/public/skills"
_PUB_CAPS = "/api/v1/public/capabilities"


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


@pytest.fixture(autouse=True)
def _rate(monkeypatch):
    """公开端限流打桩（本机 Redis 计数跨轮存活的既有坑）"""
    fake = _RateLimitRedis()

    async def _fake(key: str = "DEFAULT"):
        return fake

    import backend.app.api.v1.public_skills as pub
    monkeypatch.setattr(pub, "get_async_redis", _fake)
    return fake


@pytest.fixture
def library_root(tmp_path: Path):
    from config import settings

    original = settings.get("SKILLS.LIBRARY_ROOT")
    settings.set("SKILLS.LIBRARY_ROOT", str(tmp_path))
    (tmp_path / "plugins").mkdir(parents=True, exist_ok=True)
    (tmp_path / "skills").mkdir(parents=True, exist_ok=True)
    yield tmp_path
    settings.set("SKILLS.LIBRARY_ROOT", original)


def _query(db_session, stmt):
    async def _go():
        async with db_session() as s:
            return list((await s.execute(stmt)).scalars().all())
    return asyncio.run(_go())


def _one(db_session, stmt):
    rows = _query(db_session, stmt)
    return rows[0] if rows else None


def _write_skill_dir(root: Path, name: str, *, status: str = "stable") -> Path:
    d = root / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} 说明\n---\n# {name}\n",
        encoding="utf-8",
    )
    (d / "meta.yaml").write_text(
        f"name: {name}\ncategory: cat-t19\nstatus: {status}\n"
        "industries: []\nsimilar_to: []\n"
        "source:\n  url: ''\n  author: qa\n",
        encoding="utf-8",
    )
    return d


def _write_plugin(root: Path, name: str, skills: list[str] | None = None) -> Path:
    plugin = root / name
    plugin.mkdir(parents=True, exist_ok=True)
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


def _catalog_names(db_client, headers, asset_type: str) -> tuple[list[str], dict]:
    resp = db_client.get(_CATALOG, headers=headers, params={"type": asset_type})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    return [i["name"] for i in data["items"]], data


def _public_names(db_client, path: str, *, type_: str | None = None) -> list[str]:
    params = {"type": type_} if type_ else None
    resp = db_client.get(path, params=params)
    assert resp.status_code == 200, resp.text
    return [i["name"] for i in resp.json()["data"]["items"]]


def _list_asset(db_client, headers, asset_type: str, name: str, *, confirm: bool = False):
    resp = db_client.patch(
        _LISTING.format(asset_type, name), headers=headers,
        json={"listing_state": "listed", "confirm": confirm},
    )
    assert resp.status_code == 200, resp.text
    return resp


def _fixture_public_ready(db_session, asset_type: str, name: str) -> None:
    """夹具级补齐公开可见前提（许可/治理 stable）——不在本票施工面内"""
    async def _go():
        async with db_session() as s:
            row = (await s.execute(
                select(CapabilityAsset).where(
                    CapabilityAsset.asset_type == asset_type,
                    CapabilityAsset.name == name,
                )
            )).scalar_one()
            row.license = "MIT"
            row.status = "stable"
            await s.commit()
    asyncio.run(_go())


# ---------- GWT-88.1 技能收回（skills/scan 路与 src_sync 路各一） ----------


def test_gwt_88_1_skill_retract_after_scan(
    db_client, db_session, library_root,
):
    """Given 源里删除某技能文件且一次同步结束 When 打开治理目录/公开商店
    Then 该行不在可上架列表；镜像行软收（sync_state=gone），不物理删。"""
    pa = make_platform_admin_headers(db_session)
    skill_dir = _write_skill_dir(library_root, "t19-scan-skill")

    first = db_client.post(_SCAN_SKILLS, headers=pa)
    assert first.status_code == 200, first.text
    _fixture_public_ready(db_session, "skill", "t19-scan-skill")
    _list_asset(db_client, pa, "skill", "t19-scan-skill")
    assert "t19-scan-skill" in _catalog_names(db_client, pa, "skill")[0]
    assert "t19-scan-skill" in _public_names(db_client, _PUB_SKILLS)

    shutil.rmtree(skill_dir)
    second = db_client.post(_SCAN_SKILLS, headers=pa)
    assert second.status_code == 200, second.text

    names, data = _catalog_names(db_client, pa, "skill")
    assert "t19-scan-skill" not in names
    assert data["total"] == 0
    assert "t19-scan-skill" not in _public_names(db_client, _PUB_SKILLS)

    asset = _one(db_session, select(CapabilityAsset).where(
        CapabilityAsset.name == "t19-scan-skill"))
    assert asset is not None
    assert asset.deleted_at is not None
    assert asset.sync_state == "gone"
    skill = _one(db_session, select(Skill).where(Skill.name == "t19-scan-skill"))
    assert skill is not None  # 软收：skills 表行不物理删
    assert skill.sync_state == "missing"


def test_gwt_88_1_skill_retract_after_src_sync(
    db_client, db_session, library_root,
):
    """源同步路：包内技能文件删除 → 再同步 → 治理目录/公开商店不含该行。"""
    pa = make_platform_admin_headers(db_session)
    tree = library_root / "src-t19-skill"
    plugin = _write_plugin(tree, "t19-pack", ["keep-me", "drop-me"])
    assert db_client.post(_SRC, headers=pa, json={
        "name": "src-t19-skill", "source_kind": "local", "uri": str(tree),
    }).status_code in (200, 201)
    assert db_client.post(f"{_SRC}/src-t19-skill/sync", headers=pa).status_code == 200

    for local in ("keep-me", "drop-me"):
        _fixture_public_ready(db_session, "skill", f"t19-pack__{local}")
        _list_asset(db_client, pa, "skill", f"t19-pack__{local}", confirm=True)
    assert "t19-pack__drop-me" in _catalog_names(db_client, pa, "skill")[0]
    assert "t19-pack__drop-me" in _public_names(db_client, _PUB_SKILLS)

    shutil.rmtree(plugin / "skills" / "drop-me")
    assert db_client.post(f"{_SRC}/src-t19-skill/sync", headers=pa).status_code == 200

    names, data = _catalog_names(db_client, pa, "skill")
    assert "t19-pack__drop-me" not in names
    assert "t19-pack__keep-me" in names
    assert data["total"] == 1  # 总件不被已收回行顶满
    assert "t19-pack__drop-me" not in _public_names(db_client, _PUB_SKILLS)
    assert "t19-pack__keep-me" in _public_names(db_client, _PUB_SKILLS)

    gone = _one(db_session, select(CapabilityAsset).where(
        CapabilityAsset.name == "t19-pack__drop-me"))
    assert gone is not None
    assert gone.deleted_at is not None
    assert gone.sync_state == "gone"


# ---------- GWT-88.2 插件收回（scan-plugins 路与 src_sync 路各一） ----------


def test_gwt_88_2_plugin_retract_after_scan_plugins(
    db_client, db_session, library_root,
):
    """Given 本机 plugins/ 删除某插件目录且一次扫描结束 Then 治理目录/公开商店不含。"""
    pa = make_platform_admin_headers(db_session)
    keep = _write_plugin(library_root / "plugins", "t19-plug-keep")
    drop = _write_plugin(library_root / "plugins", "t19-plug-drop")

    first = db_client.post(_SCAN_PLUGINS, headers=pa)
    assert first.status_code == 200, first.text
    for name in ("t19-plug-keep", "t19-plug-drop"):
        _fixture_public_ready(db_session, "plugin", name)
        _list_asset(db_client, pa, "plugin", name)
    assert "t19-plug-drop" in _catalog_names(db_client, pa, "plugin")[0]
    assert "t19-plug-drop" in _public_names(db_client, _PUB_CAPS, type_="plugin")

    shutil.rmtree(drop)
    second = db_client.post(_SCAN_PLUGINS, headers=pa)
    assert second.status_code == 200, second.text
    assert keep.is_dir()  # 不物理删文件只针对收回行本身；留存目录不动

    names, data = _catalog_names(db_client, pa, "plugin")
    assert "t19-plug-drop" not in names
    assert "t19-plug-keep" in names
    assert data["total"] == 1
    assert "t19-plug-drop" not in _public_names(db_client, _PUB_CAPS, type_="plugin")

    gone = _one(db_session, select(CapabilityAsset).where(
        CapabilityAsset.asset_type == "plugin",
        CapabilityAsset.name == "t19-plug-drop"))
    assert gone is not None
    assert gone.deleted_at is not None
    assert gone.sync_state == "gone"


def test_gwt_88_2_plugin_retract_after_src_sync(
    db_client, db_session, library_root,
):
    """源同步路：整包删除 → 再同步 → 插件行收回，包内技能随包收回。"""
    pa = make_platform_admin_headers(db_session)
    tree = library_root / "src-t19-plugin"
    _write_plugin(tree, "t19-pkg-a", ["leaf-a"])
    _write_plugin(tree, "t19-pkg-b", ["leaf-b"])
    assert db_client.post(_SRC, headers=pa, json={
        "name": "src-t19-plugin", "source_kind": "local", "uri": str(tree),
    }).status_code in (200, 201)
    assert db_client.post(f"{_SRC}/src-t19-plugin/sync", headers=pa).status_code == 200

    for name in ("t19-pkg-a", "t19-pkg-b"):
        _fixture_public_ready(db_session, "plugin", name)
        _list_asset(db_client, pa, "plugin", name, confirm=True)
    assert "t19-pkg-b" in _catalog_names(db_client, pa, "plugin")[0]
    assert "t19-pkg-b" in _public_names(db_client, _PUB_CAPS, type_="plugin")

    shutil.rmtree(tree / "t19-pkg-b")
    assert db_client.post(f"{_SRC}/src-t19-plugin/sync", headers=pa).status_code == 200

    names, _ = _catalog_names(db_client, pa, "plugin")
    assert "t19-pkg-b" not in names
    assert "t19-pkg-a" in names
    assert "t19-pkg-b" not in _public_names(db_client, _PUB_CAPS, type_="plugin")
    # 包内技能随包收回（不残留孤儿行）
    assert "t19-pkg-b__leaf-b" not in _catalog_names(db_client, pa, "skill")[0]

    gone = _one(db_session, select(CapabilityAsset).where(
        CapabilityAsset.name == "t19-pkg-b"))
    assert gone is not None
    assert gone.deleted_at is not None
    assert gone.sync_state == "gone"
    orphan = _one(db_session, select(CapabilityAsset).where(
        CapabilityAsset.name == "t19-pkg-b__leaf-b"))
    assert orphan is not None
    assert orphan.deleted_at is not None


# ---------- GWT-88.3 空态 ----------


def test_gwt_88_3_catalog_empty_state(db_client, db_session, library_root):
    """目录去掉已收回行后为 0 → 空态句；总件不被已收回行顶满。"""
    pa = make_platform_admin_headers(db_session)
    only = _write_skill_dir(library_root, "t19-only-skill")
    _write_skill_dir(library_root, "t19-alive-skill")
    assert db_client.post(_SCAN_SKILLS, headers=pa).status_code == 200
    assert _catalog_names(db_client, pa, "skill")[1]["total"] == 2

    shutil.rmtree(only)
    assert db_client.post(_SCAN_SKILLS, headers=pa).status_code == 200
    _, data = _catalog_names(db_client, pa, "skill")
    assert data["total"] == 1  # 只剩活行，gone 行不顶件数

    shutil.rmtree(library_root / "skills" / "t19-alive-skill")
    assert db_client.post(_SCAN_SKILLS, headers=pa).status_code == 200
    _, data = _catalog_names(db_client, pa, "skill")
    assert data["total"] == 0
    assert data.get("empty") is True
    assert "还没有目录项" in (data.get("message") or "")


# ---------- GWT-88.4 越权 ----------


def test_gwt_88_4_tenant_cannot_touch_retracted(
    db_client, db_session, library_root,
):
    """租户经办改治理收回/上架已收回行 → 拒绝；公开商店不变。"""
    pa = make_platform_admin_headers(db_session)
    tenant, _ = make_tenant_owner_headers(db_session, slug="t19-88-4")
    skill_dir = _write_skill_dir(library_root, "t19-gone-skill")
    assert db_client.post(_SCAN_SKILLS, headers=pa).status_code == 200
    _fixture_public_ready(db_session, "skill", "t19-gone-skill")
    _list_asset(db_client, pa, "skill", "t19-gone-skill")

    shutil.rmtree(skill_dir)
    assert db_client.post(_SCAN_SKILLS, headers=pa).status_code == 200

    denied = db_client.patch(
        _LISTING.format("skill", "t19-gone-skill"), headers=tenant,
        json={"listing_state": "listed"},
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "FORBIDDEN"

    before = _public_names(db_client, _PUB_SKILLS)
    assert "t19-gone-skill" not in before
    # 平台超管再上架也拿不到行（软收行对上架写不存在）
    missing = db_client.patch(
        _LISTING.format("skill", "t19-gone-skill"), headers=pa,
        json={"listing_state": "listed"},
    )
    assert missing.status_code == 404
    assert "t19-gone-skill" not in _public_names(db_client, _PUB_SKILLS)


# ---------- GWT-88.5 命令收回不回潮（回归） ----------


def test_gwt_88_5_command_retract_no_regression(
    db_client, db_session, library_root,
):
    """清单去掉命令且同步结束 → 命令叶可操作列表仍不含（目录视角回归）。"""
    pa = make_platform_admin_headers(db_session)
    tree = library_root / "src-t19-cmd"
    plugin = _write_plugin(tree, "t19-cmd-pack")
    manifest_path = plugin / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["commands"] = {
        "/keep-cmd": {"name": "keep-cmd", "description": "留"},
        "/drop-cmd": {"name": "drop-cmd", "description": "删"},
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    cmd_dir = plugin / "commands"
    cmd_dir.mkdir()
    (cmd_dir / "keep-cmd.md").write_text(
        "---\nname: keep-cmd\n---\n# keep\n", encoding="utf-8")
    (cmd_dir / "drop-cmd.md").write_text(
        "---\nname: drop-cmd\n---\n# drop\n", encoding="utf-8")
    assert db_client.post(_SRC, headers=pa, json={
        "name": "src-t19-cmd", "source_kind": "local", "uri": str(tree),
    }).status_code in (200, 201)
    assert db_client.post(f"{_SRC}/src-t19-cmd/sync", headers=pa).status_code == 200
    assert "t19-cmd-pack__drop-cmd" in _catalog_names(db_client, pa, "command")[0]

    (cmd_dir / "drop-cmd.md").unlink()
    manifest["commands"] = {"/keep-cmd": {"name": "keep-cmd", "description": "留"}}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert db_client.post(f"{_SRC}/src-t19-cmd/sync", headers=pa).status_code == 200

    names, data = _catalog_names(db_client, pa, "command")
    assert "t19-cmd-pack__drop-cmd" not in names
    assert "t19-cmd-pack__keep-cmd" in names
    assert data["total"] == 1

    # 再同步一次：不得回潮
    assert db_client.post(f"{_SRC}/src-t19-cmd/sync", headers=pa).status_code == 200
    names, _ = _catalog_names(db_client, pa, "command")
    assert "t19-cmd-pack__drop-cmd" not in names
