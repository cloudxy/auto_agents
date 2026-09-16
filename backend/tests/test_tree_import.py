"""T-07 / FR-07：目录导入两段式（contract AD-4）。

GWT 锚：07.1 正常、07.2 取消零写入、07.3 upsert、07.4 空态、07.5 部分失败、
07.6 超限、07.7/07.10 越权 404、07.9 非白名单跳过；外加 QA-8 相对路径清洗
（`..`/绝对路径/反斜杠一律入跳过清单）与 AD-4c/AD-4g 落盘根 + 顶层游离资产。

夹具口径：multipart 每个 part 的 filename = 前端 webkitRelativePath（含顶层目录
名）。confirm 会真落盘，**所有 confirm 用例必须先把 SKILLS.AGENTS_ROOT 指到
tmp_path**，否则会写进仓库真 .agents。
"""
from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import func, select

from platform_core.models.capability import CapabilityAsset

PREVIEW = "/api/v1/capabilities/import/tree/preview"
CONFIRM = "/api/v1/capabilities/import/tree/confirm"

SKILL_MD = "---\nname: {name}\ndescription: {name} 的说明\n---\n\n# {name}\n正文\n"


@pytest.fixture
def agents_root(tmp_path):
    """把落盘根钉到临时目录——confirm 绝不能写进仓库真 .agents。"""
    from config import settings

    root = tmp_path / "agents-root" / ".agents"
    root.mkdir(parents=True)
    original = settings.get("SKILLS.AGENTS_ROOT")
    settings.set("SKILLS.AGENTS_ROOT", str(root))
    yield root
    settings.set("SKILLS.AGENTS_ROOT", original)


def _parts(mapping: dict[str, bytes | str]) -> list[tuple[str, tuple[str, bytes]]]:
    out = []
    for rel, body in mapping.items():
        blob = body.encode("utf-8") if isinstance(body, str) else body
        out.append(("files", (rel, blob)))
    return out


def _tree() -> dict[str, str]:
    """2 个游离 skill + 1 个插件（含 3 个 bundled skill）。"""
    files = {
        "up/alpha/SKILL.md": SKILL_MD.format(name="alpha"),
        "up/beta/SKILL.md": SKILL_MD.format(name="beta"),
        "up/myplug/plugin.json": json.dumps(
            {"name": "myplug", "description": "插件说明", "version": "1.0.0",
             "license": "MIT"},
            ensure_ascii=False,
        ),
    }
    for idx in ("s1", "s2", "s3"):
        files[f"up/myplug/skills/{idx}/SKILL.md"] = SKILL_MD.format(name=idx)
    return files


def _live(db_session) -> list[tuple[str, str]]:
    async def _go():
        async with db_session() as s:
            rows = (await s.execute(
                select(CapabilityAsset.asset_type, CapabilityAsset.name)
                .where(CapabilityAsset.deleted_at.is_(None))
            )).all()
            return sorted((t, n) for t, n in rows)

    return asyncio.run(_go())


def _count(db_session) -> int:
    async def _go():
        async with db_session() as s:
            return int((await s.execute(
                select(func.count()).select_from(CapabilityAsset)
                .where(CapabilityAsset.deleted_at.is_(None))
            )).scalar_one())

    return asyncio.run(_go())


# ---------- GWT-07.1 正常 ----------

def test_gwt_07_1_preview_then_confirm_matches(
    db_client, platform_admin_client, db_session, agents_root,
):
    files = _tree()
    pre = platform_admin_client.post(PREVIEW, files=_parts(files))
    assert pre.status_code == 200, pre.text
    data = pre.json()["data"]
    assert data["files_total"] == len(files)
    assert data["counts"]["skill"] == 5   # alpha/beta + 3 bundled
    assert data["counts"]["plugin"] == 1
    top = {(a["asset_type"], a["name"]) for a in data["assets"]}
    assert ("plugin", "myplug") in top
    assert ("skill", "alpha") in top and ("skill", "beta") in top
    plug = next(a for a in data["assets"] if a["name"] == "myplug")
    assert {b["name"] for b in plug["bundled"]} == {
        "myplug__s1", "myplug__s2", "myplug__s3",
    }
    assert all(a["action"] == "create" for a in data["assets"])
    assert _count(db_session) == 0  # 预览零写入

    got = platform_admin_client.post(CONFIRM, files=_parts(files))
    assert got.status_code == 200, got.text
    out = got.json()["data"]
    assert out["created"] == 6 and out["updated"] == 0 and out["failed"] == []
    live = _live(db_session)
    assert ("skill", "alpha") in live and ("plugin", "myplug") in live
    assert len(live) == 6  # 与预览计数一致
    assert (agents_root / "skills" / "alpha" / "SKILL.md").is_file()
    assert (agents_root / "plugins" / "myplug" / "plugin.json").is_file()


def test_imported_rows_are_unlisted(
    db_client, platform_admin_client, db_session, agents_root,
):
    """AD-4e：导入不自动上架。"""
    platform_admin_client.post(CONFIRM, files=_parts(_tree()))

    async def _states():
        async with db_session() as s:
            return sorted({r for (r,) in (await s.execute(
                select(CapabilityAsset.listing_state)
                .where(CapabilityAsset.deleted_at.is_(None))
            )).all()})

    assert asyncio.run(_states()) == ["unlisted"]


# ---------- GWT-07.2 取消 ----------

def test_gwt_07_2_cancel_writes_nothing(
    db_client, platform_admin_client, db_session, agents_root,
):
    before = _live(db_session)
    pre = platform_admin_client.post(PREVIEW, files=_parts(_tree()))
    assert pre.status_code == 200
    assert _live(db_session) == before          # 取消 = 不发 confirm
    assert not list(agents_root.rglob("SKILL.md"))  # 预览也不落盘


# ---------- GWT-07.3 upsert ----------

def test_gwt_07_3_second_import_updates_not_duplicates(
    db_client, platform_admin_client, db_session, agents_root,
):
    files = _tree()
    platform_admin_client.post(CONFIRM, files=_parts(files))
    total = _count(db_session)
    files["up/alpha/SKILL.md"] = SKILL_MD.format(name="alpha") + "\n改了正文\n"
    again = platform_admin_client.post(CONFIRM, files=_parts(files))
    assert again.status_code == 200, again.text
    out = again.json()["data"]
    assert out["created"] == 0
    assert out["updated"] >= 1
    assert _count(db_session) == total  # live 行数不增


def test_reimport_keeps_existing_listing_state(
    db_client, platform_admin_client, db_session, agents_root,
):
    """已上架资产重导不得被打回 unlisted（AD-4e 的 update 分支）。"""
    files = _tree()
    platform_admin_client.post(CONFIRM, files=_parts(files))

    async def _list_alpha():
        async with db_session() as s:
            row = (await s.execute(
                select(CapabilityAsset).where(CapabilityAsset.name == "alpha")
            )).scalar_one()
            row.listing_state = "listed"
            await s.commit()

    asyncio.run(_list_alpha())
    files["up/alpha/SKILL.md"] = SKILL_MD.format(name="alpha") + "\n又改了\n"
    platform_admin_client.post(CONFIRM, files=_parts(files))

    async def _state():
        async with db_session() as s:
            return (await s.execute(
                select(CapabilityAsset.listing_state)
                .where(CapabilityAsset.name == "alpha")
            )).scalar_one()

    assert asyncio.run(_state()) == "listed"


# ---------- GWT-07.4 空态 ----------

def test_gwt_07_4_no_recognizable_asset_422(
    db_client, platform_admin_client, db_session, agents_root,
):
    got = platform_admin_client.post(
        PREVIEW, files=_parts({"up/readme/NOTES.md": "# 只是笔记\n"}),
    )
    assert got.status_code == 422, got.text
    assert "未识别到可导入资产" in got.text
    assert _count(db_session) == 0


# ---------- GWT-07.5 部分失败 ----------

def test_gwt_07_5_single_failure_listed_not_whole_batch(
    db_client, platform_admin_client, db_session, agents_root, monkeypatch,
):
    """单项失败入 failed 清单，其余照常入库（不整批回滚）。"""
    import backend.services.power_market.hub_import as mod

    real = mod._upsert_item_listing

    async def _flaky(session, item, *, listing):
        if item.name == "beta":
            raise RuntimeError("标题解析失败")
        return await real(session, item, listing=listing)

    monkeypatch.setattr(mod, "_upsert_item_listing", _flaky)
    got = platform_admin_client.post(CONFIRM, files=_parts(_tree()))
    assert got.status_code == 200, got.text
    out = got.json()["data"]
    assert out["created"] == 5
    assert [f["name"] for f in out["failed"]] == ["beta"]
    assert "标题解析失败" in out["failed"][0]["reason"]
    assert ("skill", "beta") not in _live(db_session)
    assert ("skill", "alpha") in _live(db_session)


# ---------- GWT-07.6 超限 ----------

def test_gwt_07_6_over_500_files_rejected(
    db_client, platform_admin_client, db_session, agents_root,
):
    files = {f"up/pad/f{i}.md": "x" for i in range(501)}
    got = platform_admin_client.post(PREVIEW, files=_parts(files))
    assert got.status_code == 422, got.text
    assert "单次最多导入 500 个文件，请改用服务器路径导入" in got.text
    assert _count(db_session) == 0


# ---------- GWT-07.9 白名单 ----------

def test_gwt_07_9_non_whitelisted_extension_skipped(
    db_client, platform_admin_client, db_session, agents_root,
):
    files = _tree()
    files["up/alpha/payload.exe"] = "MZ"
    got = platform_admin_client.post(PREVIEW, files=_parts(files))
    assert got.status_code == 200, got.text
    data = got.json()["data"]
    assert {"path": "up/alpha/payload.exe", "reason": "非白名单扩展名"} in data["skipped"]
    assert data["counts"]["skill"] == 5  # 其余资产数量不受影响

    platform_admin_client.post(CONFIRM, files=_parts(files))
    assert not list(agents_root.rglob("*.exe"))


# ---------- QA-8 相对路径清洗 ----------

def test_qa8_malicious_relative_paths_skipped(
    db_client, platform_admin_client, db_session, agents_root,
):
    files = _tree()
    evil = {
        "../../etc/passwd.md": "x",
        "/abs/alpha.md": "x",
        "C:/win/alpha.md": "x",
        "up\\back\\slash.md": "x",
    }
    got = platform_admin_client.post(PREVIEW, files=_parts({**files, **evil}))
    assert got.status_code == 200, got.text
    bad = {s["path"] for s in got.json()["data"]["skipped"] if s["reason"] == "非法路径"}
    assert bad == set(evil)

    platform_admin_client.post(CONFIRM, files=_parts({**files, **evil}))
    assert not list(agents_root.parent.parent.rglob("passwd.md"))
    assert not list(agents_root.rglob("*slash*"))


# ---------- QA-1 出口路径收容（符号链接逃逸，穿越式） ----------

def test_qa1_symlink_escape_rejected_top_and_nested(
    db_client, platform_admin_client, db_session, agents_root, tmp_path,
):
    """复现报告的完整攻击链：`.agents/plugins/<name>` 若是指向仓外真实目录的
    符号链接——顶层 `_land(".../plugins/<name>")` 与嵌套 bundled 子项
    `_land(".../plugins/<name>/skills/<idx>")` **都**必须被拒绝，不能只靠
    顶层 `rmtree` 对符号链接的"运气式"拒绝；仓外目标树的文件集合与 mtime
    必须零变化（既不能被写入，也不能被删除），且不能有任何 DB 行落库。

    "穿越式"覆盖两个挂载点：顶层项自身 = 符号链接、嵌套 bundled 项的父路径
    经过符号链接，对应 finding 里"顶层运气拒绝 + 嵌套穿透"两段式攻击链。
    """
    outside = tmp_path / "outside-plugin-real"
    outside.mkdir()
    sentinel = outside / "untouched.txt"
    sentinel.write_bytes(b"real content living outside the repo")
    before_mtime = sentinel.stat().st_mtime

    plugins_dir = agents_root / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    (plugins_dir / "myplug").symlink_to(outside, target_is_directory=True)

    files = _tree()  # 顶层 myplug（符号链接同名）+ 3 个嵌套 bundled skill + alpha/beta
    got = platform_admin_client.post(CONFIRM, files=_parts(files))
    assert got.status_code == 200, got.text
    out = got.json()["data"]

    # 不相关的游离 skill 不受影响；myplug 顶层 + 3 个嵌套 bundled 全部拒绝
    assert out["created"] == 2 and out["updated"] == 0   # alpha、beta
    assert len(out["failed"]) == 4
    assert all("myplug" in f["name"] for f in out["failed"])

    # 仓外目标树零变化：未被写入新内容，也未被 rmtree 删除
    assert sentinel.is_file()
    assert sentinel.stat().st_mtime == before_mtime
    assert list(outside.iterdir()) == [sentinel]

    # 符号链接本身未被穿透覆盖，仍是符号链接（不是被替换成真实目录）
    assert plugins_dir.joinpath("myplug").is_symlink()

    # DB 零写入：myplug 及其 bundled 子项都不应该落库
    live = _live(db_session)
    assert not any(name.startswith("myplug") for _t, name in live)
    assert ("skill", "alpha") in live and ("skill", "beta") in live


# ---------- AD-4g 顶层游离 agent/command ----------

def test_ad4g_loose_agent_and_command_land_and_collect(
    db_client, platform_admin_client, db_session, agents_root,
):
    from pathlib import Path

    from backend.services.power_market.agents_hub_scan import collect_agents_hub

    files = {
        "up/agents/solo.md": "---\nname: solo\ndescription: 游离智能体\n---\n人设正文\n",
        "up/commands/ping.md": "---\nname: ping\ndescription: 游离命令\n---\n命令正文\n",
    }
    got = platform_admin_client.post(CONFIRM, files=_parts(files))
    assert got.status_code == 200, got.text
    live = _live(db_session)
    assert ("agent", "solo") in live      # 游离资产 name 不带 plugin__ 前缀
    assert ("command", "ping") in live
    assert (agents_root / "agents" / "solo.md").is_file()
    assert (agents_root / "commands" / "ping.md").is_file()
    # 落盘后同步通道必须认得它们，否则 prune 对账会把它们当失源剪掉
    names = {(i.asset_type, i.name) for i in collect_agents_hub(Path(agents_root))}
    assert ("agent", "solo") in names and ("command", "ping") in names


def test_qa15_loose_agents_colliding_frontmatter_name_both_land(
    db_client, platform_admin_client, db_session, agents_root,
):
    """QA-15 回归：两份游离 agent .md 文件名不同，但 frontmatter name 撞了
    （曾经的 slug 来源）——两份都必须各自入库，不能因为 slug 撞车让第二份
    的 upsert 静默覆盖第一份刚 flush 的行（同 (asset_type, name) 唯一键
    命中同一行，磁盘两份文件对应库里一行，一份资产悄悄不可见）。slug 改用
    磁盘文件名（stem，同目录天然唯一）后，两份各自成行。
    """
    files = {
        "up/agents/alpha-agent.md": "---\nname: shared-name\ndescription: 甲\n---\n甲的人设正文\n",
        "up/agents/beta-agent.md": "---\nname: shared-name\ndescription: 乙\n---\n乙的人设正文\n",
    }
    got = platform_admin_client.post(CONFIRM, files=_parts(files))
    assert got.status_code == 200, got.text
    out = got.json()["data"]
    assert out["created"] == 2 and out["failed"] == []  # 都成功入库，不是二选一

    live = _live(db_session)
    assert ("agent", "alpha-agent") in live
    assert ("agent", "beta-agent") in live
    assert len(live) == 2  # 不是撞成一行

    from platform_core.models.capability import CapabilityExpert

    async def _personas():
        async with db_session() as s:
            rows = (await s.execute(
                select(CapabilityAsset.name, CapabilityExpert.persona_md)
                .join(CapabilityExpert, CapabilityExpert.asset_id == CapabilityAsset.id)
                .where(CapabilityAsset.name.in_(["alpha-agent", "beta-agent"]))
            )).all()
            return {name: persona for name, persona in rows}

    personas = asyncio.run(_personas())
    assert personas["alpha-agent"] == "甲的人设正文"
    assert personas["beta-agent"] == "乙的人设正文"  # 各自的正文没有互相覆盖


# ---------- GWT-07.7 / 07.10 越权 ----------

def test_gwt_07_7_tenant_admin_404_zero_write(
    db_client, admin_client, db_session, agents_root,
):
    before = _live(db_session)
    for url in (PREVIEW, CONFIRM):
        got = admin_client.post(url, files=_parts(_tree()))
        assert got.status_code == 404, got.text
        assert got.json()["code"] == "HTTP_404"
        assert "抱歉您没有权限" not in got.text
    assert _live(db_session) == before
    assert not list(agents_root.rglob("SKILL.md"))


def test_gwt_07_10_normal_user_404_zero_write(
    db_client, viewer_client, db_session, agents_root,
):
    before = _live(db_session)
    for url in (PREVIEW, CONFIRM):
        got = viewer_client.post(url, files=_parts(_tree()))
        assert got.status_code == 404, got.text
    assert _live(db_session) == before
    assert not list(agents_root.rglob("SKILL.md"))
