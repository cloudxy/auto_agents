"""外部插件「引用 + 锁文件」：plugins-lock.json、scripts/agents_plugins.py、tools/check/plugin_refs.py。

全部在 tmp 下造一个假仓库 + 假家目录，不碰真实 ~/.zcode 与仓库适配器。
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts import agents_plugins as ap

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "https://example.invalid/acme/alpha.git"


def _load_plugin_refs():
    spec = importlib.util.spec_from_file_location("plugin_refs", ROOT / "tools" / "check" / "plugin_refs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _body(home: Path, name: str = "alpha") -> tuple[Path, str]:
    """家目录下造一个带 origin 的插件正文仓库，返回 (路径, HEAD)。"""
    body = home / "plugins" / name
    (body / "skills" / "one").mkdir(parents=True)
    (body / "skills" / "one" / "SKILL.md").write_text("---\nname: one\ndescription: x\n---\n", encoding="utf-8")
    _git(body, "init", "-q")
    _git(body, "remote", "add", "origin", SOURCE)
    _git(body, "add", "-A")
    _git(body, "commit", "-q", "-m", "init")
    return body, _git(body, "rev-parse", "HEAD")


def _lock(root: Path, commit: str, hosts=("claude", "grok", "codex")) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / ap.LOCK_NAME).write_text(json.dumps({
        "version": 1,
        "plugins": {"alpha": {
            "source": SOURCE, "ref": "main", "commit": commit,
            "localPath": "~/plugins/alpha", "hosts": list(hosts),
        }},
    }), encoding="utf-8")


def test_repo_lock_pins_only_sdlc_workflow():
    plugins = ap.load_lock(ROOT)
    assert list(plugins) == ["sdlc-workflow"]
    p = plugins["sdlc-workflow"]
    assert p.source == "https://github.com/cloudxy/sdlc-plugins.git"
    assert len(p.commit) == 40 and p.local_path.startswith("~/")
    assert set(p.hosts) == {"claude", "grok", "codex"}


@pytest.mark.parametrize("patch, needle", [
    ({"version": 2}, "version"),
    ({"commit": "d9b8329"}, "commit"),
    ({"hosts": ["claude", "cursor"]}, "hosts"),
    ({"localPath": "vendor/alpha"}, "localPath"),
    ({"source": "git@github.com:acme/alpha.git"}, "source"),
])
def test_lock_problems_rejects_bad_entries(patch, needle):
    entry = {"source": SOURCE, "ref": "main", "commit": "a" * 40, "localPath": "~/p/alpha", "hosts": ["codex"]}
    data = {"version": 1, "plugins": {"alpha": entry}}
    if "version" in patch:
        data["version"] = patch["version"]
    else:
        entry.update(patch)
    assert any(needle in p for p in ap.lock_problems(data))


def test_sync_links_lock_plugins_and_prunes_others(tmp_path):
    home, root = tmp_path / "home", tmp_path / "repo"
    _, head = _body(home)
    _lock(root, head)
    # 预置：锁外插件 beta 的各处链接、一个真实目录、中枢 README、锁外 codex 子代理
    for d in (".agents/plugins", ".claude/plugins", ".grok/plugins", ".codex/skills", ".codex/agents"):
        (root / d).mkdir(parents=True)
    (root / ".agents/plugins/beta").symlink_to("../../../home/plugins/beta")
    (root / ".claude/plugins/beta").symlink_to("../../.agents/plugins/beta")
    (root / ".codex/skills/beta").symlink_to("../../.agents/plugins/beta/skills")
    (root / ".codex/agents/beta-x.toml").symlink_to("../../.agents/plugins/beta/agents/x.toml")
    (root / ".grok/plugins/copied").mkdir()
    (root / ".agents/plugins/README.md").write_text("doc", encoding="utf-8")

    actions, warns, bad = ap.sync(root, home)

    assert warns == []
    assert bad == [".grok/plugins/copied 不在锁内且是真实文件/目录，未删除（请手动处理）"]
    assert os.readlink(root / ".agents/plugins/alpha") == "../../../home/plugins/alpha"
    assert os.readlink(root / ".claude/plugins/alpha") == "../../.agents/plugins/alpha"
    assert os.readlink(root / ".grok/plugins/alpha") == "../../.agents/plugins/alpha"
    assert os.readlink(root / ".codex/skills/alpha") == "../../.agents/plugins/alpha/skills"
    assert (root / ".codex/skills/alpha/one/SKILL.md").is_file()  # 链接经中枢真实可达
    for gone in (".agents/plugins/beta", ".claude/plugins/beta", ".codex/skills/beta", ".codex/agents/beta-x.toml"):
        assert not (root / gone).is_symlink(), gone
    assert (root / ".grok/plugins/copied").is_dir()
    assert (root / ".agents/plugins/README.md").is_file()
    assert any("删除 .agents/plugins/beta" in a for a in actions)

    (root / ".grok/plugins/copied").rmdir()
    assert ap.check(root, home) == ([], [])
    assert ap.sync(root, home) == ([], [], [])  # 幂等


def test_check_drift_warns_and_strict_fails(tmp_path):
    home, root = tmp_path / "home", tmp_path / "repo"
    body, head = _body(home)
    _lock(root, head, hosts=("codex",))
    ap.sync(root, home)
    (body / "NEW").write_text("x", encoding="utf-8")
    _git(body, "add", "-A")
    _git(body, "commit", "-q", "-m", "bump")

    warns, bad = ap.check(root, home)
    assert bad == [] and len(warns) == 1 and "确认后跑 lock" in warns[0]
    _, strict_bad = ap.check(root, home, strict=True)
    assert strict_bad == warns


def test_check_reports_missing_body_and_wrong_origin(tmp_path):
    home, root = tmp_path / "home", tmp_path / "repo"
    _lock(root, "b" * 40, hosts=())
    _, bad = ap.check(root, home)
    assert any("本机没有正文" in b for b in bad)

    body, head = _body(home)
    _git(body, "remote", "set-url", "origin", "https://example.invalid/other/alpha.git")
    _lock(root, head, hosts=())
    _, bad = ap.check(root, home)
    assert any("与锁" in b and "不一致" in b for b in bad)


def test_plugin_refs_repo_checks_follow_lock(tmp_path):
    """CI 侧（无正文）：锁外链接、缺失的已入库适配器、锁外 marketplace 都要报。"""
    refs = _load_plugin_refs()
    root = tmp_path / "repo"
    _lock(root, "c" * 40, hosts=("codex", "claude"))
    (root / ".codex/skills").mkdir(parents=True)
    (root / ".codex/skills/beta").symlink_to("../../.agents/plugins/beta/skills")
    (root / ".claude").mkdir()
    (root / ".claude/settings.json").write_text(json.dumps({"extraKnownMarketplaces": {
        "alpha": {"source": {"source": "directory", "path": "./.agents/plugins/alpha"}},
        "beta": {"source": {"source": "directory", "path": "./.agents/plugins/beta"}},
    }}), encoding="utf-8")

    names, bad = refs.repo_checks(root)
    assert names == ["alpha"]
    assert any(b.startswith("PL-2 .codex/skills/beta") for b in bad)
    assert any(b.startswith("PL-6 缺少 .codex/skills/alpha") for b in bad)
    assert any(b.startswith("PL-3") and "beta" in b for b in bad)
    assert not any("alpha" in b and b.startswith("PL-3") for b in bad)

    (root / ".codex/skills/beta").unlink()
    (root / ".codex/skills/alpha").symlink_to("../../.agents/plugins/alpha/skills")
    settings = json.loads((root / ".claude/settings.json").read_text(encoding="utf-8"))
    del settings["extraKnownMarketplaces"]["beta"]
    (root / ".claude/settings.json").write_text(json.dumps(settings), encoding="utf-8")
    assert refs.repo_checks(root) == (["alpha"], [])


def test_plugin_refs_flags_broken_lock(tmp_path):
    refs = _load_plugin_refs()
    names, bad = refs.repo_checks(tmp_path)
    assert names == [] and bad and bad[0].startswith("PL-0")
