"""D2 一次性迁移脚本 scripts/db/migrate_agents_hub_root.py：dry-run 零改动、--apply 搬移 +
改写前缀 + 开发内容行下架、幂等、冲突跳过、拒跑条件。临时目录 + SQLite（模板库副本）。
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select

from platform_core.models.capability import CapabilityAsset

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "db" / "migrate_agents_hub_root.py"
_TRACKED = {"skills/devskill", "plugins/README.md"}
_PRODUCT_KEYS = ("skills/prodskill", "plugins/imported-plug", "agents/solo.md", "commands/ping.md")


def _load():
    spec = importlib.util.spec_from_file_location("migrate_agents_hub_root", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass 需要按模块名回查
    spec.loader.exec_module(mod)
    return mod


def _w(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """仓库形状：git 跟踪的开发 skill、锁内插件指针（符号链接）、四类 D2 前落进中枢的产品内容。"""
    repo = tmp_path / "repo"
    agents = repo / ".agents"
    _w(agents / "skills" / "devskill" / "SKILL.md", "---\nname: devskill\n---\n# dev\n")
    _w(agents / "skills" / "prodskill" / "SKILL.md", "---\nname: prodskill\n---\n# prod\n")
    _w(agents / "skills" / "prodskill" / "icon.png", "png")
    _w(agents / "plugins" / "README.md", "指针说明")
    outside = tmp_path / "local-plugins" / "locked-plug"
    _w(outside / "plugin.json", json.dumps({"name": "locked-plug"}))
    (agents / "plugins" / "locked-plug").symlink_to(outside)
    _w(agents / "plugins" / "imported-plug" / "plugin.json", json.dumps({"name": "imported-plug"}))
    _w(agents / "plugins" / "imported-plug" / "skills" / "s" / "SKILL.md", "---\nname: s\n---\n# s\n")
    _w(agents / "agents" / "solo.md", "---\nname: solo\n---\nYou are solo.\n")
    _w(agents / "commands" / "ping.md", "---\nname: ping\n---\nping\n")
    _w(agents / "rules" / "r.md", "规则不是资产目录")
    _w(repo / "plugins-lock.json", json.dumps({"version": 1, "plugins": {"locked-plug": {}}}))
    return repo


def _asset(name: str, file_path: str, **kw) -> dict:
    row = {"asset_type": "skill", "name": name, "file_path": file_path,
           "listing_state": "listed", "status": "stable", "license": "MIT",
           "origin_ref": None, "logo": None, "deleted_at": None}
    row.update(kw)
    return row


@pytest.fixture
def db_url(tmp_path: Path, _sqlite_schema_template) -> str:
    db = tmp_path / "migrate.db"
    shutil.copyfile(_sqlite_schema_template, db)
    url = f"sqlite:///{db}"
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(CapabilityAsset.__table__.insert(), [
            _asset("prodskill", ".agents/skills/prodskill", origin_ref=".agents/skills/prodskill",
                   logo=".agents/skills/prodskill/icon.png"),
            _asset("imported-plug", ".agents/plugins/imported-plug", asset_type="plugin"),
            _asset("imported-plug__s", ".agents/plugins/imported-plug/skills/s"),
            _asset("solo", ".agents/agents/solo.md", asset_type="agent"),
            _asset("devskill", ".agents/skills/devskill"),
            _asset("locked-plug", ".agents/plugins/locked-plug", asset_type="plugin",
                   listing_state="coming_soon"),
            _asset("devskill-old", ".agents/skills/devskill", deleted_at=datetime(2026, 1, 1)),
            _asset("gone-skill", ".agents/skills/gone"),
            _asset("lib-skill", "capability-library/skills/lib"),
        ])
    engine.dispose()
    return url


def _rows(url: str) -> dict[str, tuple]:
    table = CapabilityAsset.__table__
    engine = create_engine(url)
    with engine.connect() as conn:
        got = conn.execute(select(
            table.c.name, table.c.file_path, table.c.origin_ref, table.c.logo, table.c.listing_state,
        )).all()
    engine.dispose()
    return {r[0]: tuple(r[1:]) for r in got}


def _files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*")}


def _run(mod, repo: Path, target: Path, *extra: str, db_url: str | None = None) -> int:
    argv = ["--repo", str(repo), "--target", str(target), *extra]
    return mod.main(argv + (["--db-url", db_url] if db_url else ["--skip-db"]))


def test_dry_run_prints_plan_and_changes_nothing(repo, db_url, tmp_path, monkeypatch, capsys):
    mod = _load()
    monkeypatch.setattr(mod, "_tracked_keys", lambda _repo: set(_TRACKED))
    target = tmp_path / "hub"
    before_rows, before_files = _rows(db_url), _files(repo)
    assert _run(mod, repo, target, db_url=db_url) == 0
    out = capsys.readouterr().out
    for key in _PRODUCT_KEYS:
        assert f"[move] .agents/{key} -> {target / key}" in out
    assert "[keep] .agents/skills/devskill（git 跟踪的开发内容）" in out
    assert "[keep] .agents/plugins/locked-plug（符号链接（插件指针农场））" in out
    assert "README" not in out and "rules/" not in out
    assert "汇总：move=4 keep=2 conflict=0 | 改写=4 下架=2" in out
    assert "dry-run" in out
    assert _rows(db_url) == before_rows and _files(repo) == before_files
    assert not target.exists()


def test_apply_moves_rewrites_and_unlists_then_is_idempotent(
    repo, db_url, tmp_path, monkeypatch, capsys,
):
    from backend.services.power_market.agents_hub_scan import collect_agents_hub

    mod = _load()
    monkeypatch.setattr(mod, "_tracked_keys", lambda _repo: set(_TRACKED))
    target = tmp_path / "hub"
    assert _run(mod, repo, target, "--apply", db_url=db_url) == 0
    for key in _PRODUCT_KEYS:
        assert (target / key).exists() and not (repo / ".agents" / key).exists(), key
    assert (repo / ".agents" / "skills" / "devskill" / "SKILL.md").is_file()
    assert (repo / ".agents" / "plugins" / "locked-plug").is_symlink()
    rows = _rows(db_url)
    assert rows["prodskill"] == (
        "agents-hub/skills/prodskill", "agents-hub/skills/prodskill",
        "agents-hub/skills/prodskill/icon.png", "listed",
    )
    assert rows["imported-plug__s"][0] == "agents-hub/plugins/imported-plug/skills/s"
    assert rows["solo"][0] == "agents-hub/agents/solo.md"
    assert rows["devskill"] == (".agents/skills/devskill", None, None, "unlisted")
    assert rows["locked-plug"][3] == "unlisted"
    assert rows["devskill-old"][3] == "listed"  # 软删行不动
    assert rows["gone-skill"] == (".agents/skills/gone", None, None, "listed")  # 孤儿留给 prune
    assert rows["lib-skill"][0] == "capability-library/skills/lib"
    hub_paths = {i.name: i.file_path for i in collect_agents_hub(target)}
    assert hub_paths["prodskill"] == rows["prodskill"][0]  # 库内路径 = 同步通道口径

    capsys.readouterr()
    assert _run(mod, repo, target, "--apply", db_url=db_url) == 0
    assert "汇总：move=0 keep=2 conflict=0 | 改写=0 下架=0" in capsys.readouterr().out
    assert _rows(db_url) == rows


def test_conflict_is_skipped_and_reported(repo, tmp_path, monkeypatch, capsys):
    mod = _load()
    monkeypatch.setattr(mod, "_tracked_keys", lambda _repo: set(_TRACKED))
    target = tmp_path / "hub"
    (target / "skills" / "prodskill").mkdir(parents=True)
    assert _run(mod, repo, target, "--apply") == 0
    out = capsys.readouterr().out
    assert f"[conflict] .agents/skills/prodskill（hub 根已有 {target / 'skills' / 'prodskill'}）" in out
    assert (repo / ".agents" / "skills" / "prodskill" / "SKILL.md").is_file()
    assert not (target / "skills" / "prodskill" / "SKILL.md").exists()
    assert "库：已跳过" in out


def test_refuses_when_target_is_dev_hub_or_git_unavailable(repo, tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "_tracked_keys", lambda _repo: set(_TRACKED))
    assert _run(mod, repo, repo / ".agents", "--apply") == 2
    monkeypatch.setattr(mod, "_tracked_keys", lambda _repo: None)
    assert _run(mod, repo, tmp_path / "hub", "--apply") == 2
    assert (repo / ".agents" / "skills" / "prodskill").is_dir()  # 拒跑 = 零搬移


def test_default_target_follows_config_relative_to_repo(tmp_path):
    from config import settings

    mod = _load()
    original = settings.get("SKILLS.AGENTS_ROOT")
    try:
        settings.set("SKILLS.AGENTS_ROOT", "runtime/agents-hub")
        assert mod._target_root(None, tmp_path) == tmp_path / "runtime" / "agents-hub"
        assert mod._target_root("/abs/hub", tmp_path) == Path("/abs/hub")
    finally:
        settings.set("SKILLS.AGENTS_ROOT", original)


def test_tracked_keys_reads_this_repo_index():
    keys = _load()._tracked_keys(_REPO)
    if keys is None:
        pytest.skip("git 不可用或不是 git 检出")
    assert {"skills/verify", "skills/check-arch"} <= keys


def test_env_flag_selects_config_layer_before_config_import(repo):
    """--env 必须在 config 导入前生效：脚本顶层就链式导入 config，晚设 APP_ENV 会连到别的环境的库。
    独立进程、不带 APP_ENV 环境变量运行，打印出的生效环境必须是 --env 指定的那个。"""
    import os
    import subprocess

    env = {k: v for k, v in os.environ.items() if k != "APP_ENV"}
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--env", "dev", "--skip-db", "--repo", str(repo)],
        cwd=_REPO, env=env, capture_output=True, text=True, timeout=120,
    )
    assert "环境: dev" in proc.stdout, proc.stdout + proc.stderr


def test_env_flag_mismatch_in_process_is_refused(repo, capsys):
    """进程内调用（config 已按当前环境加载）且 --env 不同：拒绝执行，不碰任何文件与库。"""
    import config

    other = next(e for e in ("local", "dev", "prod") if e != config.APP_ENV)
    assert _load().main(["--env", other, "--skip-db", "--repo", str(repo)]) == 2
    assert "不一致" in capsys.readouterr().out
    assert (repo / ".agents" / "skills" / "prodskill").is_dir()
