"""feat-agents-market T-03：失源行清理（FR-02 全部 GWT 02.1–02.6）。

夹具口径（contract AD-3 + QA-7R 裁定）：
- legacy 形态行 = file_path 非 `.agents/` 前缀 + 有 capability_experts 侧行 +
  无磁盘源 → **负向断言：prune 后仍 live**（persona_md 正文存侧行，剪除即丢）。
- hub 来源 agent 孤儿 = file_path `.agents/` 前缀 + 有侧行 + 无磁盘源 →
  **正向断言：被 prune**（失磁盘源属正常失源）。
- NULL file_path 行 → 视为可清（QA-14 manager 裁定，夹具补断言）。
- dry_run=true → 同构 pruned 预览且 deleted_at 不变（QA-9）。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from platform_core.models.capability import (
    CapabilityAsset, CapabilityExpert, CapabilitySource,
)

_PRUNE = "/api/v1/capabilities/assets/prune-missing"


def _q(db_session, stmt):
    async def _go():
        async with db_session() as s:
            return list((await s.execute(stmt)).scalars().all())
    return asyncio.run(_go())


def _row(**kwargs) -> CapabilityAsset:
    base = dict(
        asset_type="skill", category="cat", status="stable",
        listing_state="listed", license="MIT", source_type="self_built",
        sync_state="ok",
    )
    base.update(kwargs)
    return CapabilityAsset(**base)


def _seed(db_session, rows: list[CapabilityAsset], sides: list | None = None) -> None:
    async def _go():
        async with db_session() as s:
            s.add_all(rows)
            await s.flush()
            for side in (sides or []):
                s.add(side)
            await s.commit()
    asyncio.run(_go())


def _agents_tree(tmp_path: Path) -> Path:
    """磁盘 .agents：1 skill + 1 plugin（其余行制造失源差）"""
    agents = tmp_path / ".agents"
    skill = agents / "skills" / "on-disk-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: on-disk-skill\ndescription: d\n---\n# S\n", encoding="utf-8")
    plug = agents / "plugins" / "on-disk-plug"
    plug.mkdir(parents=True)
    (plug / "plugin.json").write_text(json.dumps({
        "name": "on-disk-plug", "description": "d", "license": "MIT",
    }), encoding="utf-8")
    return agents


def _fixture_rows() -> list[CapabilityAsset]:
    return [
        # 磁盘有源（GWT-02.3 保护面）
        _row(name="on-disk-skill", file_path=".agents/skills/on-disk-skill"),
        _row(asset_type="plugin", name="on-disk-plug",
             file_path=".agents/plugins/on-disk-plug"),
        # 孤儿 command（oh-story__* 存量形态）
        _row(asset_type="command", name="oh-story__export",
             file_path="capability-library/commands/oh-story__export.md"),
        # 孤儿 skill
        _row(name="dead-skill", file_path="capability-library/skills/dead-skill"),
        # 排除面：team（人工定义，非磁盘源）
        _row(asset_type="team", name="a-team", file_path=None),
    ]


def _fixture_sides(asset_ids: dict[str, int]) -> list[CapabilityExpert]:
    return [
        # legacy 形态 agent：侧行 + 非 .agents 前缀 → 保护
        CapabilityExpert(asset_id=asset_ids["legacy-agent"],
                         persona_md="legacy persona body"),
        # hub 孤儿 agent：侧行 + .agents 前缀 → 应被 prune
        CapabilityExpert(asset_id=asset_ids["hub-orphan-agent"],
                         persona_md="hub persona body"),
        # NULL file_path agent：侧行 + NULL → 视为可清（QA-14）
        CapabilityExpert(asset_id=asset_ids["null-path-agent"], persona_md="null"),
    ]


def _full_fixture(db_session) -> None:
    """一次落全部夹具（含需要 asset_id 的侧行）"""

    async def _go():
        async with db_session() as s:
            src = CapabilitySource(name="src-a", source_kind="local", uri="/tmp/x")
            s.add(src)
            await s.flush()
            rows = _fixture_rows() + [
                _row(asset_type="agent", name="legacy-agent",
                     file_path="capability-library/experts/legacy-agent.md"),
                _row(asset_type="agent", name="hub-orphan-agent",
                     file_path=".agents/plugins/x/agents/hub-orphan-agent.md"),
                _row(asset_type="agent", name="null-path-agent", file_path=None),
                # 排除面：源注册表行（source_id 非空，收归 src_sync）
                _row(name="src-row", file_path="capability-library/skills/src-row",
                     source_type="source_indexed", source_id=src.id),
            ]
            s.add_all(rows)
            await s.flush()
            ids = {r.name: int(r.id) for r in rows}
            s.add_all(_fixture_sides(ids))
            await s.commit()

    asyncio.run(_go())


def _names(rows):
    return sorted(r.name for r in rows)


# ---------- GWT-02.1 正常（存量孤儿清出 live 集） ----------


def test_gwt_02_1_prunes_orphans_and_keeps_the_rest(
    db_client, platform_admin_client, db_session, tmp_path,
):
    from config import settings

    agents = _agents_tree(tmp_path)
    _full_fixture(db_session)
    original = settings.get("SKILLS.AGENTS_ROOT")
    settings.set("SKILLS.AGENTS_ROOT", str(agents))
    try:
        resp = platform_admin_client.post(_PRUNE)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        pruned = {(p["asset_type"], p["name"]) for p in data["pruned"]}
        # 孤儿被清：command 孤儿 + skill 孤儿 + hub agent 孤儿 + NULL path agent
        assert ("command", "oh-story__export") in pruned
        assert ("skill", "dead-skill") in pruned
        assert ("agent", "hub-orphan-agent") in pruned
        assert ("agent", "null-path-agent") in pruned  # QA-14
        # 磁盘有源 + 排除面不在剪除清单
        assert not any(n in {"on-disk-skill", "on-disk-plug", "a-team",
                             "legacy-agent", "src-row"} for _, n in pruned)

        live = _names(_q(db_session, select(CapabilityAsset).where(
            CapabilityAsset.deleted_at.is_(None))))
        assert "oh-story__export" not in live  # 治理目录不再可见
        assert "dead-skill" not in live
        assert "legacy-agent" in live  # QA-7R 负向：legacy 形态仍 live
        assert "on-disk-skill" in live and "on-disk-plug" in live
        assert "a-team" in live
    finally:
        settings.set("SKILLS.AGENTS_ROOT", original)


# ---------- GWT-02.2 对账 ----------


def test_gwt_02_2_reconciliation_zero_gap(db_client, platform_admin_client,
                                           db_session, tmp_path):
    from config import settings

    agents = _agents_tree(tmp_path)
    _full_fixture(db_session)
    original = settings.get("SKILLS.AGENTS_ROOT")
    settings.set("SKILLS.AGENTS_ROOT", str(agents))
    try:
        pruned = platform_admin_client.post(_PRUNE).json()["data"]
        assert pruned["live_total"] == pruned["disk_total"]  # 差值 = 0
        again = platform_admin_client.post(_PRUNE).json()["data"]
        assert again["pruned"] == []
        assert again["live_total"] == again["disk_total"]
    finally:
        settings.set("SKILLS.AGENTS_ROOT", original)


# ---------- GWT-02.3 范围保护 ----------


def test_gwt_02_3_disk_present_rows_stay_live(
    db_client, platform_admin_client, db_session, tmp_path,
):
    from config import settings

    agents = _agents_tree(tmp_path)
    _full_fixture(db_session)
    original = settings.get("SKILLS.AGENTS_ROOT")
    settings.set("SKILLS.AGENTS_ROOT", str(agents))
    try:
        platform_admin_client.post(_PRUNE)
        for name in ("on-disk-skill", "on-disk-plug"):
            row = _q(db_session, select(CapabilityAsset).where(
                CapabilityAsset.name == name))[0]
            assert row.deleted_at is None
    finally:
        settings.set("SKILLS.AGENTS_ROOT", original)


# ---------- GWT-02.4 幂等 ----------


def test_gwt_02_4_idempotent_second_run_no_change(
    db_client, platform_admin_client, db_session, tmp_path,
):
    from config import settings

    agents = _agents_tree(tmp_path)
    _full_fixture(db_session)
    original = settings.get("SKILLS.AGENTS_ROOT")
    settings.set("SKILLS.AGENTS_ROOT", str(agents))
    try:
        first = platform_admin_client.post(_PRUNE).json()["data"]
        live_after_first = _q(db_session, select(CapabilityAsset).where(
            CapabilityAsset.deleted_at.is_(None)))
        second = platform_admin_client.post(_PRUNE).json()["data"]
        live_after_second = _q(db_session, select(CapabilityAsset).where(
            CapabilityAsset.deleted_at.is_(None)))
        assert second["pruned"] == []
        assert _names(live_after_first) == _names(live_after_second)
        assert len(first["pruned"]) > 0
    finally:
        settings.set("SKILLS.AGENTS_ROOT", original)


# ---------- QA-9 dry_run 同构不落库 ----------


def test_dry_run_same_shape_no_write(
    db_client, platform_admin_client, db_session, tmp_path,
):
    from config import settings

    agents = _agents_tree(tmp_path)
    _full_fixture(db_session)
    original = settings.get("SKILLS.AGENTS_ROOT")
    settings.set("SKILLS.AGENTS_ROOT", str(agents))
    try:
        before = _q(db_session, select(CapabilityAsset))
        deleted_before = sorted(
            r.name for r in before if r.deleted_at is not None)

        preview = platform_admin_client.post(_PRUNE, params={"dry_run": "true"})
        assert preview.status_code == 200, preview.text
        pv = preview.json()["data"]
        assert pv["dry_run"] is True
        assert pv["live_total"] == pv["disk_total"]  # 模拟剪除后对账归零

        after = _q(db_session, select(CapabilityAsset))
        deleted_after = sorted(
            r.name for r in after if r.deleted_at is not None)
        assert deleted_before == deleted_after  # deleted_at 不变

        executed = platform_admin_client.post(_PRUNE).json()["data"]
        assert {(p["asset_type"], p["name"]) for p in pv["pruned"]} == {
            (p["asset_type"], p["name"]) for p in executed["pruned"]}  # 同构
        assert pv["disk_total"] == executed["disk_total"]
    finally:
        settings.set("SKILLS.AGENTS_ROOT", original)


# ---------- QA-7R 夹具口径专测（侧行判别式） ----------


def test_qa7r_legacy_agent_with_side_row_survives(
    db_client, platform_admin_client, db_session, tmp_path,
):
    """legacy 形态（非 .agents 前缀 + 侧行 + 无磁盘源）→ prune 后仍 live（正文在侧行）"""
    from config import settings

    agents = _agents_tree(tmp_path)
    _full_fixture(db_session)
    original = settings.get("SKILLS.AGENTS_ROOT")
    settings.set("SKILLS.AGENTS_ROOT", str(agents))
    try:
        platform_admin_client.post(_PRUNE)
        row = _q(db_session, select(CapabilityAsset).where(
            CapabilityAsset.name == "legacy-agent"))[0]
        side = _q(db_session, select(CapabilityExpert).where(
            CapabilityExpert.asset_id == row.id))
        assert row.deleted_at is None
        assert side and side[0].persona_md == "legacy persona body"
    finally:
        settings.set("SKILLS.AGENTS_ROOT", original)


def test_qa7r_hub_agent_orphan_with_side_row_pruned(
    db_client, platform_admin_client, db_session, tmp_path,
):
    """hub 孤儿（.agents 前缀 + 侧行 + 无磁盘源）→ 被 prune（侧行不豁免 hub 失源）"""
    from config import settings

    agents = _agents_tree(tmp_path)
    _full_fixture(db_session)
    original = settings.get("SKILLS.AGENTS_ROOT")
    settings.set("SKILLS.AGENTS_ROOT", str(agents))
    try:
        platform_admin_client.post(_PRUNE)
        row = _q(db_session, select(CapabilityAsset).where(
            CapabilityAsset.name == "hub-orphan-agent"))[0]
        assert row.deleted_at is not None
        assert row.sync_state == "gone"
    finally:
        settings.set("SKILLS.AGENTS_ROOT", original)


# ---------- QA-6：存量 capability-library 行磁盘源仍在，不得误判失源 ----------


def test_qa6_legacy_skill_with_real_library_source_survives(
    db_client, platform_admin_client, db_session, tmp_path,
):
    """legacy skill 行（无 .agents 前缀 + 磁盘源仍在 capability-library）
    prune 后仍 live——OQ-2 切根只处理了新写路径，prune 的磁盘集只扫 .agents，
    不能把"扫描器没往那看"当成"真的没有磁盘源"。用仓库长期稳定的一等夹具
    资产 example-pdf-extractor（多处既有测试同样依赖其磁盘常在）。
    """
    from config import settings

    agents = _agents_tree(tmp_path)
    _seed(db_session, [
        _row(name="example-pdf-extractor", file_path="capability-library/skills/example-pdf-extractor"),
    ])
    original = settings.get("SKILLS.AGENTS_ROOT")
    settings.set("SKILLS.AGENTS_ROOT", str(agents))
    try:
        resp = platform_admin_client.post(_PRUNE)
        assert resp.status_code == 200, resp.text
        pruned = {(p["asset_type"], p["name"]) for p in resp.json()["data"]["pruned"]}
        assert ("skill", "example-pdf-extractor") not in pruned

        row = _q(db_session, select(CapabilityAsset).where(
            CapabilityAsset.name == "example-pdf-extractor"))[0]
        assert row.deleted_at is None
    finally:
        settings.set("SKILLS.AGENTS_ROOT", original)


def test_qa6_true_orphan_without_any_disk_source_still_pruned(
    db_client, platform_admin_client, db_session, tmp_path,
):
    """真孤儿行（file_path 指向的路径哪里都不存在）不受 QA-6 保护，仍被
    剪除——不是全称保护 legacy 行，是"磁盘源真的还在就别删"。回归
    test_gwt_02_1 已覆盖的 dead-skill/oh-story__export 断言，这里单独钉死
    避免以后有人把 QA-6 实现成"非 .agents 前缀一律不删"。
    """
    from config import settings

    agents = _agents_tree(tmp_path)
    _seed(db_session, [
        _row(name="truly-gone-skill", file_path="capability-library/skills/does-not-exist-anywhere"),
    ])
    original = settings.get("SKILLS.AGENTS_ROOT")
    settings.set("SKILLS.AGENTS_ROOT", str(agents))
    try:
        resp = platform_admin_client.post(_PRUNE)
        assert resp.status_code == 200, resp.text
        pruned = {(p["asset_type"], p["name"]) for p in resp.json()["data"]["pruned"]}
        assert ("skill", "truly-gone-skill") in pruned
    finally:
        settings.set("SKILLS.AGENTS_ROOT", original)


# ---------- GWT-02.5 / GWT-02.6 越权 ----------


def test_gwt_02_5_tenant_admin_404_zero_write(
    db_client, admin_client, db_session, tmp_path,
):
    from config import settings

    agents = _agents_tree(tmp_path)
    _full_fixture(db_session)
    original = settings.get("SKILLS.AGENTS_ROOT")
    settings.set("SKILLS.AGENTS_ROOT", str(agents))
    try:
        before = _names(_q(db_session, select(CapabilityAsset).where(
            CapabilityAsset.deleted_at.is_(None))))
        resp = admin_client.post(_PRUNE)
        assert resp.status_code == 404
        assert resp.json()["code"] == "HTTP_404"
        after = _names(_q(db_session, select(CapabilityAsset).where(
            CapabilityAsset.deleted_at.is_(None))))
        assert before == after  # DB 无变化
    finally:
        settings.set("SKILLS.AGENTS_ROOT", original)


def test_gwt_02_6_normal_user_404_zero_write(
    db_client, viewer_client, db_session, tmp_path,
):
    from config import settings

    agents = _agents_tree(tmp_path)
    _full_fixture(db_session)
    original = settings.get("SKILLS.AGENTS_ROOT")
    settings.set("SKILLS.AGENTS_ROOT", str(agents))
    try:
        before = _names(_q(db_session, select(CapabilityAsset).where(
            CapabilityAsset.deleted_at.is_(None))))
        resp = viewer_client.post(_PRUNE, params={"dry_run": "true"})
        assert resp.status_code == 404
        assert resp.json()["code"] == "HTTP_404"
        after = _names(_q(db_session, select(CapabilityAsset).where(
            CapabilityAsset.deleted_at.is_(None))))
        assert before == after
    finally:
        settings.set("SKILLS.AGENTS_ROOT", original)
