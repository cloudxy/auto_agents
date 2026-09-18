"""feat-agents-market T-01：sync-agents-hub 端点（FR-01 全部 GWT 01.1–01.7）。

口径（contract AD-1/AD-2 + spec FR-01）：
- 01.1 bug 后状态恢复：软删 plugin 行存在 + 磁盘有插件 → 同步后 plugin live 复活，
  其他类型 live 行数不减。
- 01.2 幂等：连续再触发 2 次，各类型 live 行数不变、无软删。
- 01.3 非破坏：磁盘资产移除后再同步，新增 deleted_at 行数 = 0。
- 01.4 失效符号链接：同步完成不报错，已有 live 行不软删，跳过原因入日志。
- 01.5 越权：租户管理员 POST → 404 存在性隐藏门面，DB 零变化。
- 01.6 退役：scan-plugins 路由已删（超管直打 404；行为断言在 b1c 文件）。
- 01.7 并发：撞 uq_asset_type_name_alive → IntegrityError 降级 unchanged（确定性桩）。
"""
from __future__ import annotations

import asyncio
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select

from platform_core.models.capability import CapabilityAsset

_SYNC = "/api/v1/capabilities/sync-agents-hub"
_OLD_SCAN = "/api/v1/capabilities/scan-plugins"


def _q(db_session, stmt):
    async def _go():
        async with db_session() as s:
            return list((await s.execute(stmt)).scalars().all())
    return asyncio.run(_go())


def _live_by_type(db_session) -> dict[str, int]:
    rows = _q(db_session, select(CapabilityAsset).where(
        CapabilityAsset.deleted_at.is_(None)))
    out: dict[str, int] = {}
    for r in rows:
        out[r.asset_type] = out.get(r.asset_type, 0) + 1
    return out


async def _live_by_type_async(db_session) -> dict[str, int]:
    async with db_session() as s:
        rows = (await s.execute(
            select(CapabilityAsset).where(CapabilityAsset.deleted_at.is_(None))
        )).scalars().all()
    out: dict[str, int] = {}
    for r in rows:
        out[r.asset_type] = out.get(r.asset_type, 0) + 1
    return out


def _soft_deleted_count(db_session) -> int:
    async def _go():
        async with db_session() as s:
            return int((await s.execute(
                select(func.count()).select_from(CapabilityAsset).where(
                    CapabilityAsset.deleted_at.is_not(None))
            )).scalar_one())
    return asyncio.run(_go())


def _seed_bug_state(db_session, names: list[str]) -> None:
    """bug 后状态：plugin 行全部带 deleted_at（live 0），另有少量其他类型 live 行。"""

    async def _go():
        async with db_session() as s:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for name in names:
                s.add(CapabilityAsset(
                    asset_type="plugin", name=name, title=name, category="plugin",
                    status="stable", listing_state="listed", deleted_at=now,
                    sync_state="gone",
                ))
            s.add(CapabilityAsset(
                asset_type="skill", name="keep-skill", title="keep", category="skill",
                status="stable", listing_state="listed", license="MIT",
            ))
            s.add(CapabilityAsset(
                asset_type="command", name="keep-command", title="keep", category="command",
                status="stable", listing_state="listed", license="MIT",
            ))
            await s.commit()

    asyncio.run(_go())


def _write_plugin(agents: Path, name: str) -> Path:
    pkg = agents / "plugins" / name
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "plugin.json").write_text(json.dumps({
        "name": name, "description": name, "version": "1.0.0", "license": "MIT",
    }), encoding="utf-8")
    return pkg


@pytest.fixture
def agents_root(tmp_path: Path) -> Path:
    from config import settings

    agents = tmp_path / ".agents"
    agents.mkdir()
    for name in ("plug-a", "plug-b", "plug-c", "plug-d", "plug-e", "plug-f"):
        _write_plugin(agents, name)
    original = settings.get("SKILLS.AGENTS_ROOT")
    settings.set("SKILLS.AGENTS_ROOT", str(agents))
    yield agents
    settings.set("SKILLS.AGENTS_ROOT", original)


# ---------- GWT-01.1 正常（bug 后状态恢复） ----------


def test_gwt_01_1_recovers_plugin_rows_from_bug_state(
    db_client, platform_admin_client, db_session, agents_root,
):
    _seed_bug_state(db_session, [f"plug-{c}" for c in "abcdef"])
    before = _live_by_type(db_session)
    assert before.get("plugin", 0) == 0

    resp = platform_admin_client.post(_SYNC)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["inserted"] >= 6
    assert data["failed"] == 0
    assert {k: data[k] for k in
            ("inserted", "updated", "unchanged", "failed", "total", "failed_items")}

    after = _live_by_type(db_session)
    assert after.get("plugin") == 6  # 12 行软删旧形态不复活干扰：live = 磁盘 6
    assert after.get("skill") == before.get("skill")  # 其他类型 live 行数不减
    assert after.get("command") == before.get("command")


# ---------- GWT-01.2 幂等 ----------


def test_gwt_01_2_idempotent_repeated_sync(
    db_client, platform_admin_client, db_session, agents_root,
):
    first = platform_admin_client.post(_SYNC)
    assert first.status_code == 200, first.text
    baseline = _live_by_type(db_session)

    for _ in range(2):
        again = platform_admin_client.post(_SYNC)
        assert again.status_code == 200, again.text
        body = again.json()["data"]
        assert body["inserted"] == 0
        assert body["updated"] == 0
        assert body["unchanged"] == first.json()["data"]["inserted"]

    assert _live_by_type(db_session) == baseline
    assert _soft_deleted_count(db_session) == 0  # 无行被软删


# ---------- GWT-01.3 非破坏（验收线） ----------


def test_gwt_01_3_sync_never_soft_deletes(
    db_client, platform_admin_client, db_session, agents_root,
):
    assert platform_admin_client.post(_SYNC).status_code == 200
    shutil.rmtree(agents_root / "plugins" / "plug-a")  # 磁盘资产移除（改名/移除场景）

    resp = platform_admin_client.post(_SYNC)
    assert resp.status_code == 200, resp.text
    assert _soft_deleted_count(db_session) == 0  # 本轮触发新增的 deleted_at 行数 = 0
    gone_row = [r for r in _q(db_session, select(CapabilityAsset).where(
        CapabilityAsset.name == "plug-a")) if r.deleted_at is None]
    assert gone_row  # 失源行仍 live（回收只能来自显式动作，FR-02）


# ---------- GWT-01.4 失效符号链接 ----------


def test_gwt_01_4_broken_symlink_logged_not_fatal(
    db_client, platform_admin_client, db_session, agents_root, monkeypatch,
):
    assert platform_admin_client.post(_SYNC).status_code == 200
    before = _live_by_type(db_session)
    (agents_root / "plugins" / "ghost-plug").symlink_to(agents_root / "no-such-target")

    # loguru 非 stdlib logging，caplog 不可用——桩掉模块 logger 收集 info 行
    import backend.services.power_market.agents_hub_scan as scan_mod

    messages: list[str] = []

    class _StubLogger:
        def info(self, msg, *args):
            messages.append(msg % args if args else msg)

        def warning(self, msg, *args):
            messages.append(msg % args if args else msg)

    monkeypatch.setattr(scan_mod, "logger", _StubLogger())
    resp = platform_admin_client.post(_SYNC)
    assert resp.status_code == 200, resp.text  # 同步完成不报错
    assert _live_by_type(db_session) == before  # 已有 live 行不被软删
    assert _soft_deleted_count(db_session) == 0
    assert any("ghost-plug" in m for m in messages), "跳过原因必须写入日志（GWT-01.4）"


# ---------- GWT-01.5 越权（租户管理员） ----------


def test_gwt_01_5_tenant_admin_404_zero_write(
    db_client, admin_client, db_session, agents_root,
):
    _seed_bug_state(db_session, ["plug-x"])
    before = _live_by_type(db_session)

    resp = admin_client.post(_SYNC)
    assert resp.status_code == 404
    assert resp.json()["code"] == "HTTP_404"
    assert _live_by_type(db_session) == before  # DB 行数与状态无任何变化


def test_gwt_01_5_anonymous_401(client):
    assert client.post(_SYNC).status_code == 401


# ---------- GWT-01.6 退役（扫描类入口不存在） ----------


def test_gwt_01_6_old_scan_retired(db_client, platform_admin_client):
    assert platform_admin_client.post(_OLD_SCAN).status_code == 404


# ---------- GWT-01.7 并发（唯一键兜底降级 unchanged） ----------


@pytest.mark.asyncio
async def test_gwt_01_7_unique_collision_degrades_to_unchanged(
    db_session, agents_root, monkeypatch,
):
    """确定性并发模拟：另一请求已先插入同名行 → 本请求 INSERT 撞
    uq_asset_type_name_alive → IntegrityError → 重读存活行按 unchanged 记。"""
    from backend.services.power_market import agents_hub as hub

    async with db_session() as s:
        await hub.sync_agents_hub(s, agents_root, actor="manual")
        await s.commit()
    baseline = await _live_by_type_async(db_session)

    real_load = hub._load
    calls = {"n": 0}

    async def _stale_load(session, asset_type, name):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # 模拟并发窗口：读到过期「不存在」
        return await real_load(session, asset_type, name)

    monkeypatch.setattr(hub, "_load", _stale_load)
    async with db_session() as s:
        # 期望值重算：全部行都在 → 期望 unchanged 插入降级
        result = await hub.sync_agents_hub(s, agents_root, actor="manual")
        await s.commit()

    assert result["failed"] == 0
    assert result["inserted"] == 0
    assert result["updated"] == 0
    assert result["unchanged"] == result["total"]
    after = await _live_by_type_async(db_session)
    assert after == baseline  # 不产生重复行，无行软删
