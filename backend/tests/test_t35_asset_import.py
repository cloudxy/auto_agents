"""T-35 FR-100 能力资产一键导入：四类/部分成功/空态/超大/越权/逃逸/幂等 + asset_imported。

Seam（票面）：POST /api/v1/capabilities/import（multipart 文件 或 directory 表单）。
沙箱红线（GWT-100.7/NFR-04/SEC-11）：三形态逃逸各一例 + 资产目录外零新文件
（tmp 区目录快照前后对比）；沙箱导入结束即清理。
"""
from __future__ import annotations

import asyncio
import io
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import func, select

from platform_core.models.asset_import import AssetImportBatch, AssetImportItem
from platform_core.models.capability import CapabilityAsset
from platform_core.models.product_event import ProductEvent

IMPORT_URL = "/api/v1/capabilities/import"
EVENTS_URL = "/api/v1/product-events"

SKILL_MD = "---\nname: imported-skill\ndescription: 导入技能\n---\n# S\n"
SKILL2_MD = "---\nname: second-skill\ndescription: 第二技能\n---\n# S2\n"
SKILL3_MD = "---\nname: third-skill\ndescription: 第三技能\n---\n# S3\n"
AGENT_MD = "---\nname: helper-agent\ndescription: 智能体\n---\n你是助手。\n"
CMD_MD = "---\nname: deploy-now\ndescription: 部署命令\n---\n运行部署。\n"

PLUGIN_JSON = '{"name": "sample-plugin", "description": "插件", "version": "1.0.0"}'


@pytest.fixture
def import_env(tmp_path: Path):
    """库根 + 沙箱根都收进 tmp_path（逃逸断言可快照整个 tmp 区）"""
    from config import settings

    # AD-4c/OQ-2：legacy 导入落盘根已由 capability-library 统一切到 .agents，
    # 故本夹具钉的是 SKILLS.AGENTS_ROOT；LIBRARY_ROOT 一并钉住，防止旧路径残留
    # 写到仓库真库根（逃逸断言仍可快照整个 tmp 区）。
    library = tmp_path / "library" / ".agents"
    sandbox = tmp_path / "_sandbox"
    library.mkdir(parents=True)
    originals = (
        settings.get("SKILLS.LIBRARY_ROOT"),
        settings.get("ASSET_IMPORT.SANDBOX_ROOT"),
        settings.get("SKILLS.AGENTS_ROOT"),
    )
    settings.set("SKILLS.LIBRARY_ROOT", str(library))
    settings.set("ASSET_IMPORT.SANDBOX_ROOT", str(sandbox))
    settings.set("SKILLS.AGENTS_ROOT", str(library))
    yield {"library": library, "sandbox": sandbox, "area": tmp_path}
    settings.set("SKILLS.LIBRARY_ROOT", originals[0])
    settings.set("ASSET_IMPORT.SANDBOX_ROOT", originals[1])
    settings.set("SKILLS.AGENTS_ROOT", originals[2])


def _zip(entries: dict[str, bytes], symlinks: dict[str, str] | None = None) -> bytes:
    """构造上传 zip（deflate，压缩包口径）；symlinks={成员名: 目标} 生成符号链接条目"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, content in entries.items():
            zf.writestr(path, content)
        for path, target in (symlinks or {}).items():
            info = zipfile.ZipInfo(path)
            info.create_system = 3  # unix
            info.external_attr = 0o120777 << 16  # S_IFLNK | 0777
            zf.writestr(info, target)
    return buf.getvalue()


def _snapshot(root: Path) -> set[str]:
    """文件级快照（目录不计——沙箱基目录为 fixture 产物，导入结束应只剩空壳）"""
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def _rows(db_session, stmt):
    async def _go():
        async with db_session() as s:
            return list((await s.execute(stmt)).scalars().all())
    return asyncio.run(_go())


def _count(db_session, entity, *where) -> int:
    async def _go():
        async with db_session() as s:
            stmt = select(func.count()).select_from(entity)
            if where:
                stmt = stmt.where(*where)
            return int((await s.execute(stmt)).scalar_one())
    return asyncio.run(_go())


def _assets(db_session, asset_type: str | None = None):
    stmt = select(CapabilityAsset)
    if asset_type:
        stmt = stmt.where(CapabilityAsset.asset_type == asset_type)
    return _rows(db_session, stmt)


def _post_zip(db_client, headers, payload: bytes, fname: str = "pkg.zip"):
    return db_client.post(
        IMPORT_URL, headers=headers,
        files={"file": (fname, payload, "application/zip")},
    )


def _post_files(db_client, headers, files: list[tuple[str, bytes, str]]):
    return db_client.post(
        IMPORT_URL, headers=headers,
        files=[("file", (n, d, ct)) for n, d, ct in files],
    )


# ---------------- GWT-100.1：单文件/包导入（未上架） ----------------


def test_gwt_100_1_single_zip_import_unlisted(db_client, db_session, import_env):
    from conftest import make_platform_admin_headers

    pa = make_platform_admin_headers(db_session)
    before = _snapshot(import_env["area"])

    resp = _post_zip(db_client, pa, _zip({"imported-skill/SKILL.md": SKILL_MD}))

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["succeeded"] == 1 and data["failed"] == 0
    item = data["items"][0]
    assert item["asset_type"] == "skill" and item["name"] == "imported-skill"  # 含类型与名称

    rows = _assets(db_session, "skill")
    assert [r.name for r in rows] == ["imported-skill"]
    assert rows[0].listing_state == "unlisted"  # 未上架，公开商店不出现新卡
    assert (import_env["library"] / "skills" / "imported-skill" / "SKILL.md").exists()

    new_files = _snapshot(import_env["area"]) - before
    assert new_files == {"library/.agents/skills/imported-skill/SKILL.md"}  # 目录外零新文件
    assert not import_env["sandbox"].exists() or not any(import_env["sandbox"].iterdir())


# ---------------- GWT-100.2：目录部分成功 ----------------


def test_gwt_100_2_directory_partial_success(db_client, db_session, import_env, tmp_path):
    from conftest import make_platform_admin_headers

    pa = make_platform_admin_headers(db_session)
    batch_dir = tmp_path / "assets-dir"
    (batch_dir / "good-skill").mkdir(parents=True)
    (batch_dir / "good-skill" / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    (batch_dir / "good-plugin").mkdir()
    (batch_dir / "good-plugin" / "plugin.json").write_text(
        '{"name": "good-plugin", "description": "好插件"}', encoding="utf-8")
    (batch_dir / "broken-command.md").write_text(
        "---\nname: broken\n未闭合 frontmatter", encoding="utf-8")  # 不合法文件

    resp = db_client.post(IMPORT_URL, headers=pa, data={"directory": str(batch_dir)})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["origin"] == "directory"
    assert data["succeeded"] == 2 and data["failed"] == 1
    names = {(i["asset_type"], i["name"]) for i in data["items"] if i["status"] == "succeeded"}
    assert ("skill", "imported-skill") in names and ("plugin", "good-plugin") in names
    failed = [i for i in data["items"] if i["status"] == "failed"]
    assert failed == [{
        "asset_type": "command", "name": "broken-command", "status": "failed",
        "reason": "broken-command.md frontmatter 未闭合",  # 名称+中文原因
    }]

    rows = _assets(db_session)
    assert {r.name for r in rows} == {"imported-skill", "good-plugin"}
    batch = _rows(db_session, select(AssetImportBatch))[0]
    assert (batch.origin, batch.status, batch.total_count,
            batch.succeeded_count, batch.failed_count) == ("directory", "completed", 3, 2, 1)
    reasons = {i.name: i.reason for i in _rows(db_session, select(AssetImportItem))}
    assert "frontmatter 未闭合" in reasons["broken-command"]


# ---------------- GWT-100.3：无可导入（中性说明，非静默非失败句） ----------------


def test_gwt_100_3_nothing_importable(db_client, db_session, import_env, tmp_path):
    from conftest import make_platform_admin_headers

    pa = make_platform_admin_headers(db_session)
    empty_dir = tmp_path / "empty-assets"
    empty_dir.mkdir()
    (empty_dir / "readme.txt").write_text("不是资产", encoding="utf-8")

    resp = db_client.post(IMPORT_URL, headers=pa, data={"directory": str(empty_dir)})

    assert resp.status_code == 200  # 不是失败句
    data = resp.json()["data"]
    assert data["total"] == 0
    assert data["message"] == "没有可导入的资产。"  # 静默成功也不是
    assert _count(db_session, CapabilityAsset) == 0
    batch = _rows(db_session, select(AssetImportBatch))[0]
    assert (batch.status, batch.total_count) == ("completed", 0)


# ---------------- GWT-100.4：四类齐（类型由导入过程判定） ----------------


def test_gwt_100_4_four_types_auto_detected(db_client, db_session, import_env):
    from conftest import make_platform_admin_headers

    pa = make_platform_admin_headers(db_session)
    payload = _zip({
        "skill-pkg/SKILL.md": SKILL_MD,
        "agent-pkg/AGENT.md": AGENT_MD,
        "plugin-pkg/plugin.json": PLUGIN_JSON,
        "deploy-now.md": CMD_MD,  # 独立 .md → command
    })

    resp = _post_zip(db_client, pa, payload)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["succeeded"] == 4 and data["failed"] == 0
    detected = {i["asset_type"] for i in data["items"]}
    assert detected == {"skill", "agent", "command", "plugin"}  # 四类齐，无手工分型
    rows = {r.asset_type for r in _assets(db_session)}
    assert rows == {"skill", "agent", "command", "plugin"}
    assert (import_env["library"] / "agents" / "helper-agent" / "AGENT.md").exists()
    assert (import_env["library"] / "commands" / "deploy-now.md").exists()
    assert (import_env["library"] / "plugins" / "sample-plugin" / "plugin.json").exists()


# ---------------- GWT-100.5：超大拒绝含上限数字；同批其余继续 ----------------


def test_gwt_100_5_oversize_rejection_with_limit_number(db_client, db_session, import_env):
    from conftest import make_platform_admin_headers
    from config import settings

    pa = make_platform_admin_headers(db_session)
    original = settings.get("ASSET_IMPORT.MAX_FILE_BYTES")
    settings.set("ASSET_IMPORT.MAX_FILE_BYTES", 200)  # 上限来自配置（NFR-10）
    try:
        payload = _zip({
            "good-skill/SKILL.md": SKILL_MD,
            "big-pkg/SKILL.md": SKILL2_MD,
            "big-pkg/huge.bin": b"x" * 300,
        })
        resp = _post_zip(db_client, pa, payload)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["succeeded"] == 1 and data["failed"] == 1  # 部分成功
        failed = [i for i in data["items"] if i["status"] == "failed"][0]
        assert failed["name"] == "second-skill"
        assert "200" in failed["reason"] and "huge.bin" in failed["reason"]

        rows = _assets(db_session, "skill")
        assert [r.name for r in rows] == ["imported-skill"]
        assert not (import_env["library"] / "skills" / "second-skill").exists()

        # 多文件上传同语义：单个超大 .md 拒绝、同批合法文件继续
        resp2 = _post_files(db_client, pa, [
            ("huge.md", b"x" * 300, "text/markdown"),
            ("deploy-now.md", CMD_MD, "text/markdown"),
        ])
        data2 = resp2.json()["data"]
        assert data2["succeeded"] == 1 and data2["failed"] == 1
        failed2 = [i for i in data2["items"] if i["status"] == "failed"][0]
        assert failed2["name"] == "huge" and "200" in failed2["reason"]
    finally:
        settings.set("ASSET_IMPORT.MAX_FILE_BYTES", original)


# ---------------- GWT-100.6：非超管直打 404 同形、零行 ----------------


def test_gwt_100_6_non_admin_direct_post_404_shape(db_client, db_session, import_env):
    from conftest import make_tenant_owner_headers

    tenant, _tid = make_tenant_owner_headers(db_session, slug="t35-1006")

    resp = db_client.post(
        IMPORT_URL, headers=tenant,
        files={"file": ("pkg.zip", _zip({"imported-skill/SKILL.md": SKILL_MD}),
                        "application/zip")},
    )
    assert resp.status_code == 404
    assert resp.json()["message"] == "Not Found"  # 与「页面不存在」同形，不是 403 信封
    assert _count(db_session, CapabilityAsset) == 0
    assert _count(db_session, AssetImportBatch) == 0  # 不产生任何目录行/批次
    assert not (import_env["library"] / "skills").exists()


# ---------------- GWT-100.7：路径逃逸三形态 + 目录外零新文件 ----------------


def test_gwt_100_7_escape_three_forms_zero_leak(db_client, db_session, import_env, tmp_path):
    from conftest import make_platform_admin_headers

    pa = make_platform_admin_headers(db_session)
    payload = _zip(
        entries={
            "ok/SKILL.md": SKILL_MD,
            "esc-rel/SKILL.md": SKILL2_MD,
            "esc-rel/../evil-rel.txt": b"pwned",       # ../ 形态
            "esc-abs/SKILL.md": AGENT_MD,
            "/esc-abs/evil-abs.txt": b"pwned",          # 绝对路径形态
            "esc-sym/SKILL.md": SKILL3_MD,
        },
        symlinks={"esc-sym/link.txt": "/etc/passwd"},   # 符号链接条目形态
    )
    before = _snapshot(import_env["area"])

    resp = _post_zip(db_client, pa, payload)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["succeeded"] == 1 and data["failed"] == 3  # 同批合法项部分成功
    failed_items = [i for i in data["items"] if i["status"] == "failed"]
    reasons = [i["reason"] for i in failed_items]
    assert all("路径指向资产目录之外" in r for r in reasons)
    assert any("evil-rel.txt" in r for r in reasons)   # 失败原因列出条目名称
    assert any("evil-abs.txt" in r for r in reasons)
    assert any("link.txt" in r for r in reasons)
    assert {i["name"] for i in failed_items} == {"second-skill", "helper-agent", "third-skill"}

    # 资产目录外零新文件：tmp 区快照差集只含库内合法产物
    new_files = _snapshot(import_env["area"]) - before
    assert new_files == {"library/.agents/skills/imported-skill/SKILL.md"}
    assert not (import_env["area"] / "evil-rel.txt").exists()
    rows = _assets(db_session)
    assert [r.name for r in rows] == ["imported-skill"]  # 逃逸携带资产不产生行


def test_gwt_100_7_directory_channel_symlink_rejected(db_client, db_session, import_env, tmp_path):
    from conftest import make_platform_admin_headers

    pa = make_platform_admin_headers(db_session)
    batch_dir = tmp_path / "dir-assets"
    pkg = batch_dir / "escd"
    pkg.mkdir(parents=True)
    (pkg / "SKILL.md").write_text(SKILL2_MD, encoding="utf-8")
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    (pkg / "link.md").symlink_to(outside)  # 目录通道 symlink 条目
    good = batch_dir / "good-skill"
    good.mkdir()
    (good / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")

    resp = db_client.post(IMPORT_URL, headers=pa, data={"directory": str(batch_dir)})

    data = resp.json()["data"]
    assert data["succeeded"] == 1 and data["failed"] == 1
    failed = [i for i in data["items"] if i["status"] == "failed"][0]
    assert "路径指向资产目录之外" in failed["reason"] and "link.md" in failed["reason"]
    assert (import_env["library"] / "skills" / "second-skill").exists() is False
    assert outside.read_text() == "secret"  # 符号链接目标未被触碰


# ---------------- GWT-100.8：幂等重导不产生第二行 ----------------


def test_gwt_100_8_idempotent_reimport(db_client, db_session, import_env):
    from conftest import make_platform_admin_headers

    pa = make_platform_admin_headers(db_session)
    payload = _zip({"imported-skill/SKILL.md": SKILL_MD})

    first = _post_zip(db_client, pa, payload)
    assert first.json()["data"]["succeeded"] == 1
    second = _post_zip(db_client, pa, payload)

    data = second.json()["data"]
    assert data["succeeded"] == 0 and data["skipped"] == 1  # 不产生第二行
    assert _count(db_session, CapabilityAsset,
                  CapabilityAsset.asset_type == "skill",
                  CapabilityAsset.name == "imported-skill") == 1
    batches = _rows(db_session, select(AssetImportBatch).order_by(AssetImportBatch.id))
    assert (batches[1].skipped_count, batches[1].status) == (1, "completed")
    skipped = _rows(db_session, select(AssetImportItem).where(
        AssetImportItem.batch_id == batches[1].id))[0]
    assert (skipped.status, skipped.asset_id, skipped.reason) == ("skipped", None, None)


# ---------------- GWT-92.9：asset_imported 事件（超管查询面可查） ----------------


def test_gwt_92_9_asset_imported_event_queryable(db_client, db_session, import_env):
    from conftest import make_platform_admin_headers

    pa_headers = make_platform_admin_headers(db_session)
    payload = _zip({
        "good-skill/SKILL.md": SKILL_MD,
        "broken-command.md": "---\nname: broken\n未闭合",
    })

    resp = _post_zip(db_client, pa_headers, payload)
    assert resp.json()["data"]["failed"] == 1  # 含部分成功的一次导入

    rows = _rows(db_session, select(ProductEvent).where(
        ProductEvent.event_name == "asset_imported"))
    assert len(rows) == 1
    props = rows[0].props
    assert props["origin"] == "file"
    assert props["types"] == ["skill"]  # 本次涉及类型（失败项不进 types）
    assert props["succeeded"] == 1 and props["failed"] == 1
    admin_user_id = _t04_root_id(db_session)
    assert rows[0].tenant_id is None and rows[0].actor_user_id == admin_user_id

    listed = db_client.get(EVENTS_URL, headers=pa_headers,
                           params={"event_name": "asset_imported"})
    assert listed.status_code == 200
    payload_items = listed.json()["data"]["items"]
    assert len(payload_items) == 1
    assert payload_items[0]["props"]["origin"] == "file"  # 超管查询面可查


def _t04_root_id(db_session) -> int:
    from platform_core.models.user import User

    async def _go():
        async with db_session() as s:
            row = (await s.execute(
                select(User).where(User.username == "t04-root"))).scalar_one()
            return int(row.id)
    return asyncio.run(_go())


# ---------------- 整批失败口径（db-spec 2.1 failed；GWT-100.5 上限同句） ----------------


def test_batch_level_rejection_records_failed_batch(db_client, db_session, import_env):
    """解包累计超限（压缩炸弹口径，db-spec 2.1 failed）：整批拒绝留痕 + 上限数字"""
    from conftest import make_platform_admin_headers
    from config import settings

    pa = make_platform_admin_headers(db_session)
    original = settings.get("ASSET_IMPORT.MAX_BATCH_BYTES")
    settings.set("ASSET_IMPORT.MAX_BATCH_BYTES", 2000)
    try:
        payload = _zip({  # 原始体积被 deflate 压到远小于 2000；解压后 > 2000
            "a/SKILL.md": SKILL_MD,
            "a/big1.bin": b"\x00" * 1500,
            "a/big2.bin": b"\x00" * 1500,
        })
        resp = _post_zip(db_client, pa, payload)
        assert resp.status_code == 422
        assert "2000" in resp.json()["message"]  # 拒绝句含上限数字
        batches = _rows(db_session, select(AssetImportBatch))
        assert [b.status for b in batches] == ["failed"]  # 整批失败留痕
        assert _count(db_session, CapabilityAsset) == 0
    finally:
        settings.set("ASSET_IMPORT.MAX_BATCH_BYTES", original)


def test_bad_directory_path_rejected(db_client, db_session, import_env, tmp_path):
    from conftest import make_platform_admin_headers

    pa = make_platform_admin_headers(db_session)
    resp = db_client.post(IMPORT_URL, headers=pa,
                          data={"directory": str(tmp_path / "no-such-dir")})
    assert resp.status_code == 422
    assert "导入目录不存在" in resp.json()["message"]
    assert _count(db_session, AssetImportBatch) == 0  # 未开始的导入不留批次


# ---------------- 迁移链锚定（043 链在 042 之后；不依赖数据库） ----------------


def test_migration_043_chain_anchor():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / (
        "043_t35_asset_import_batches_items.py")
    spec = importlib.util.spec_from_file_location("mig043", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "043"
    assert mod.down_revision == "042"
    assert mod.revision != mod.down_revision
