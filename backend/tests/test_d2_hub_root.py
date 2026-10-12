"""D2「分离」：产品 hub 根与开发中枢 `.agents/` 解耦的回归。

锚点：
- (a) 默认配置的根不是 `.agents/`，采集器收不到仓库的开发 SOP skill；
- 入库路径格式 `agents-hub/<相对根>`（与根的物理位置无关）；导入两通道同口径、根缺失惰性创建；
- (c) legacy `.agents/...` 行读兼容（详情正文 / 媒体）且 prune 不误剪；空根 / 缺根 prune 拒剪。
"""
from __future__ import annotations

import asyncio
import io
import json
import zipfile
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

from backend.tests.fr33_support import fr33_asset, seed_rows
from conftest import make_platform_admin_headers
from platform_core.models.capability import CapabilityAsset

_REPO = Path(__file__).resolve().parents[2]
_PRUNE = "/api/v1/capabilities/assets/prune-missing"
_PUBLIC = "/api/v1/public/capabilities"
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


class _RateRedis:
    async def incr(self, key):
        return 1

    async def expire(self, key, ttl):
        return True


@pytest.fixture
def hub_root(tmp_path, monkeypatch):
    """SKILLS.AGENTS_ROOT 指到临时 hub 根；legacy `.agents/` 目录也钉到临时目录。"""
    from config import settings

    import backend.services.power_market.hub_paths as hub_paths

    root = tmp_path / "hub"
    legacy = tmp_path / "legacy-dot-agents"
    monkeypatch.setattr(hub_paths, "LEGACY_HUB_DIR", legacy)
    original = settings.get("SKILLS.AGENTS_ROOT")
    settings.set("SKILLS.AGENTS_ROOT", str(root))
    yield root, legacy
    settings.set("SKILLS.AGENTS_ROOT", original)


@pytest.fixture
def _rate(monkeypatch):
    async def _fake(key: str = "DEFAULT"):
        return _RateRedis()

    import backend.app.api.v1.public_skills as pub
    monkeypatch.setattr(pub, "get_async_redis", _fake)


def _skill(root: Path, name: str, body: str = "# 正文") -> Path:
    folder = root / "skills" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: d\nlicense: MIT\n---\n{body}\n", encoding="utf-8")
    return folder


def _live_names(db_session) -> set[str]:
    async def _go():
        async with db_session() as s:
            rows = (await s.execute(
                select(CapabilityAsset.name).where(CapabilityAsset.deleted_at.is_(None))
            )).all()
            return {n for (n,) in rows}
    return asyncio.run(_go())


# ---------- (a) 默认配置不采集开发中枢 ----------


def test_default_root_is_runtime_hub_and_skips_repo_dev_skills(monkeypatch):
    from config import settings

    from backend.config_consts import SKILLS_AGENTS_ROOT
    from backend.services.power_market.agents_hub import agents_root
    from backend.services.power_market.agents_hub_scan import collect_agents_hub
    from backend.services.power_market.hub_paths import LEGACY_HUB_DIR

    yml = yaml.safe_load((_REPO / "config/default/skills.yml").read_text(encoding="utf-8"))
    assert yml["SKILLS"]["AGENTS_ROOT"] == SKILLS_AGENTS_ROOT == "runtime/agents-hub"
    dev_skills = {d.name for d in (LEGACY_HUB_DIR / "skills").iterdir() if (d / "SKILL.md").is_file()}
    assert {"verify", "check-arch", "new-svc"} <= dev_skills  # 夹具前提：仓库确有开发 SOP skill
    monkeypatch.chdir(_REPO)
    original = settings.get("SKILLS.AGENTS_ROOT")
    settings.set("SKILLS.AGENTS_ROOT", yml["SKILLS"]["AGENTS_ROOT"])
    try:
        root = agents_root()
        items = collect_agents_hub(root)
    finally:
        settings.set("SKILLS.AGENTS_ROOT", original)
    assert root == _REPO / "runtime" / "agents-hub"
    assert root.resolve() != LEGACY_HUB_DIR.resolve()
    assert not ({i.name for i in items} & dev_skills)
    assert not [i for i in items if i.file_path.startswith(".agents/")]


# ---------- 入库路径格式 ----------


def test_stored_paths_are_hub_relative_regardless_of_root_location(tmp_path):
    from backend.services.power_market.agents_hub_scan import collect_agents_hub

    for root in (tmp_path / "a" / ".agents", tmp_path / "b" / "deep" / "agents-hub"):
        folder = _skill(root, "fmt-skill")
        (folder / "icon.png").write_bytes(_PNG)
        (item,) = collect_agents_hub(root)
        assert item.file_path == "agents-hub/skills/fmt-skill"
        assert item.origin_ref == "agents-hub/skills/fmt-skill"
        assert item.logo == "agents-hub/skills/fmt-skill/icon.png"
        assert item.license == "MIT"


def test_resolve_hub_path_rejects_escapes(tmp_path):
    from backend.services.power_market.hub_paths import _resolve_hub_path

    assert _resolve_hub_path("agents-hub/../etc/passwd", tmp_path) is None
    assert _resolve_hub_path("agents-hub//etc/passwd", tmp_path) is None
    assert _resolve_hub_path("capability-library/skills/x", tmp_path) is None
    assert _resolve_hub_path("agents-hub/skills/x", tmp_path) == tmp_path / "skills" / "x"


@pytest.mark.asyncio
async def test_sync_on_missing_root_is_empty_and_writes_nothing(db_session, tmp_path):
    from backend.services.power_market.agents_hub import sync_agents_hub

    missing = tmp_path / "not-there"
    async with db_session() as session:
        result = await sync_agents_hub(session, missing)
        await session.commit()
    assert result["total"] == 0 and result["inserted"] == 0 and result["failed"] == 0
    assert not missing.exists()  # 同步只读，不建根


def test_tree_import_creates_missing_root_and_stores_hub_prefix(
    db_client, platform_admin_client, db_session, hub_root,
):
    root, _legacy = hub_root
    assert not root.exists()
    skill = "---\nname: lazy\ndescription: d\n---\n# lazy\n"
    resp = platform_admin_client.post(
        "/api/v1/capabilities/import/tree/confirm",
        files=[("files", ("up/lazy/SKILL.md", skill.encode("utf-8")))],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["created"] == 1
    assert (root / "skills" / "lazy" / "SKILL.md").is_file()

    async def _row():
        async with db_session() as s:
            return (await s.execute(
                select(CapabilityAsset).where(CapabilityAsset.name == "lazy")
            )).scalar_one()
    row = asyncio.run(_row())
    assert row.file_path == "agents-hub/skills/lazy"
    assert row.listing_state == "unlisted" and row.license is None


def test_legacy_import_creates_missing_root_and_stores_hub_prefix(db_client, db_session, hub_root):
    root, _legacy = hub_root
    pa = make_platform_admin_headers(db_session)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("zipped/SKILL.md", "---\nname: zipped\ndescription: d\n---\n# z\n")
    resp = db_client.post(
        "/api/v1/capabilities/import", headers=pa,
        files={"file": ("pkg.zip", buf.getvalue(), "application/zip")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["succeeded"] == 1
    assert (root / "skills" / "zipped" / "SKILL.md").is_file()

    async def _row():
        async with db_session() as s:
            return (await s.execute(
                select(CapabilityAsset).where(CapabilityAsset.name == "zipped")
            )).scalar_one()
    assert asyncio.run(_row()).file_path == "agents-hub/skills/zipped"


# ---------- (c) legacy `.agents/...` 行读兼容 ----------


def test_detail_reads_body_for_new_and_legacy_prefixes(db_client, db_session, hub_root, _rate):
    root, legacy = hub_root
    _skill(root, "new-row", body="# 新根正文")
    _skill(root, "moved-row", body="# 已迁移正文")
    _skill(legacy, "unmoved-row", body="# 未迁移正文")
    seed_rows(db_session, [
        fr33_asset(name="new-row", file_path="agents-hub/skills/new-row"),
        fr33_asset(name="moved-row", file_path=".agents/skills/moved-row"),
        fr33_asset(name="unmoved-row", file_path=".agents/skills/unmoved-row"),
    ])
    for name, body in (("new-row", "新根正文"), ("moved-row", "已迁移正文"), ("unmoved-row", "未迁移正文")):
        got = db_client.get(f"{_PUBLIC}/skill/{name}")
        assert got.status_code == 200, got.text
        assert body in got.json()["data"]["skill_md"], name


def test_media_served_for_new_and_legacy_prefixes(db_client, db_session, hub_root, _rate):
    root, legacy = hub_root
    (_skill(root, "m-new") / "icon.png").write_bytes(_PNG)
    (_skill(legacy, "m-old") / "icon.png").write_bytes(_PNG)
    seed_rows(db_session, [
        fr33_asset(name="m-new", logo="agents-hub/skills/m-new/icon.png"),
        fr33_asset(name="m-old", logo=".agents/skills/m-old/icon.png"),
        fr33_asset(name="m-bad", logo="capability-library/skills/m-bad/icon.png"),
    ])
    for name in ("m-new", "m-old"):
        got = db_client.get(f"{_PUBLIC}/skill/{name}/media/logo")
        assert got.status_code == 200, f"{name}: {got.text}"
        assert got.content == _PNG
    assert db_client.get(f"{_PUBLIC}/skill/m-bad/media/logo").status_code == 404


def _prune_rows() -> list[CapabilityAsset]:
    return [
        fr33_asset(name="on-disk", file_path="agents-hub/skills/on-disk"),
        fr33_asset(name="legacy-unmoved", file_path=".agents/skills/legacy-unmoved"),
        fr33_asset(name="legacy-orphan", file_path=".agents/skills/legacy-orphan"),
        fr33_asset(name="new-orphan", file_path="agents-hub/skills/new-orphan"),
    ]


def test_prune_keeps_legacy_rows_whose_content_still_exists(
    db_client, platform_admin_client, db_session, hub_root,
):
    root, legacy = hub_root
    _skill(root, "on-disk")
    _skill(legacy, "legacy-unmoved")  # 内容还在旧位置（未跑迁移）
    seed_rows(db_session, _prune_rows())
    data = platform_admin_client.post(_PRUNE).json()["data"]
    pruned = {p["name"] for p in data["pruned"]}
    assert pruned == {"legacy-orphan", "new-orphan"}  # 哪里都没有内容的才剪
    assert data["skipped_reason"] is None
    assert {"on-disk", "legacy-unmoved"} <= _live_names(db_session)


@pytest.mark.parametrize("make_root", [False, True], ids=["missing-root", "empty-root"])
def test_prune_refuses_on_missing_or_empty_root(
    db_client, platform_admin_client, db_session, hub_root, make_root,
):
    root, _legacy = hub_root
    if make_root:
        (root / "skills").mkdir(parents=True)
    seed_rows(db_session, _prune_rows())
    before = _live_names(db_session)
    for params in ({"dry_run": "true"}, {}):
        resp = platform_admin_client.post(_PRUNE, params=params)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["pruned"] == [] and data["disk_total"] == 0
        assert data["skipped_reason"] == "hub_root_empty"
    assert _live_names(db_session) == before  # 一行都没软删


def test_scan_collects_loose_command_license_from_frontmatter(tmp_path):
    from backend.services.power_market.agents_hub_scan import collect_agents_hub

    root = tmp_path / "hub"
    (root / "commands").mkdir(parents=True)
    (root / "commands" / "ping.md").write_text(
        "---\nname: ping\nlicense: ISC\n---\nping\n", encoding="utf-8")
    (root / "agents").mkdir()
    (root / "agents" / "solo.md").write_text("---\nname: solo\n---\nYou are solo.\n", encoding="utf-8")
    (root / "plugins" / "p").mkdir(parents=True)
    (root / "plugins" / "p" / "plugin.json").write_text(
        json.dumps({"name": "p", "description": "d"}), encoding="utf-8")
    got = {(i.asset_type, i.name): i.license for i in collect_agents_hub(root)}
    assert got == {("command", "ping"): "ISC", ("agent", "solo"): "", ("plugin", "p"): ""}


@pytest.mark.asyncio
async def test_source_sync_bundled_skill_inherits_manifest_license(db_session, tmp_path):
    """源注册表通道同口径：包内技能许可继承包清单，缺失 = NULL（此前恒写 MIT）。"""
    from backend.services.power_market.sync import SourceSync
    from platform_core.models.capability import CapabilitySource

    src_root = tmp_path / "src"
    for pkg, manifest in (("lic-pkg", {"license": "Apache-2.0"}), ("bare-pkg", {})):
        (src_root / pkg / "skills" / "s").mkdir(parents=True)
        (src_root / pkg / "plugin.json").write_text(
            json.dumps({"name": pkg, "description": pkg, **manifest}), encoding="utf-8")
        (src_root / pkg / "skills" / "s" / "SKILL.md").write_text(
            "---\nname: s\n---\n# s\n", encoding="utf-8")
    async with db_session() as session:
        session.add(CapabilitySource(name="d2-src", source_kind="local", uri=str(src_root)))
        await session.commit()
        result = await SourceSync(session).sync("d2-src")
        rows = {r.name: r for r in (await session.execute(select(CapabilityAsset))).scalars().all()}
    assert result["failed"] == 0
    assert rows["lic-pkg__s"].license == "Apache-2.0"
    assert rows["bare-pkg__s"].license is None and rows["bare-pkg"].license is None
    assert all(r.listing_state == "unlisted" for r in rows.values())  # 第三方新行恒 unlisted
