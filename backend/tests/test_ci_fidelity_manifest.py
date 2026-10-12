"""CI 保真通道清单元测试：凡是靠 MYSQL_FIDELITY 开关才运行的测试文件，都必须出现在
`.github/workflows/ci.yml` 的「Pytest (MySQL 保真通道子集)」显式清单里。

背景：保真通道按文件清单跑，新加的 `mysql_fidelity` 文件忘记登记时，默认通道整文件 skip、
保真通道又不选它，测试从此一次都不运行（test_explain_indexes / test_t14_migration_046 /
test_t42_fidelity_queue_depth 曾因此漏跑）。本测试在普通通道里把这种漏登记变成红灯。
"""
from __future__ import annotations

import ast
from pathlib import Path

import yaml

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[1]
CI_FILE = REPO_ROOT / ".github" / "workflows" / "ci.yml"
FIDELITY_STEP = "Pytest (MySQL 保真通道子集)"


def _is_fidelity_gated(path: Path) -> bool:
    """文件代码（不含注释/文档串里的提及）是否按保真开关决定运行"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "mysql_fidelity_enabled":
            return True
        if isinstance(node, ast.Attribute) and node.attr in ("mysql_fidelity", "mysql_fidelity_enabled"):
            return True
        if isinstance(node, ast.Constant) and node.value == "MYSQL_FIDELITY":
            return True
    return False


def _ci_fidelity_files() -> set[str]:
    workflow = yaml.safe_load(CI_FILE.read_text(encoding="utf-8"))
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if step.get("name") == FIDELITY_STEP:
                return {Path(tok).name for tok in step["run"].split() if tok.endswith(".py")}
    raise AssertionError(f"ci.yml 里找不到步骤「{FIDELITY_STEP}」")


def test_every_fidelity_gated_file_is_in_ci_channel():
    me = Path(__file__).name  # 本文件自身含开关字面量，不算门控
    gated = {p.name for p in TESTS_DIR.glob("test_*.py") if p.name != me and _is_fidelity_gated(p)}
    missing = sorted(gated - _ci_fidelity_files())
    assert not missing, f"以下文件按 MYSQL_FIDELITY 门控却不在 CI 保真通道清单里（永远不会运行）: {missing}"


def test_ci_channel_lists_only_existing_files():
    stale = sorted(name for name in _ci_fidelity_files() if not (TESTS_DIR / name).is_file())
    assert not stale, f"CI 保真通道清单里的文件不存在: {stale}"
