#!/usr/bin/env python3
"""SZ：Python 规模门禁——单文件 ≤ 500 行、单函数 ≤ 40 行（AGENTS.md「编码」约定的机械化）。

口径（固定，改口径须同步 AGENTS.md）：
- 范围：git 跟踪的 *.py，排除测试（tests/ 目录、test_*.py、conftest.py）与 alembic 迁移版本文件；
- 文件行数 = 物理行数；
- 函数行数 = `def` 所在行到函数体最后一行（含文档串、注释、空行，不含装饰器）；
  嵌套函数与方法各自单独计，外层函数的行数包含嵌套函数。

用法：
  python3 tools/check/size.py                 # 全仓
  python3 tools/check/size.py a.py b.py       # 只查给定文件（拆分时自检）
退出码 = 违规数（上限 255）。
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAX_FILE_LINES = 500
MAX_FUNC_LINES = 40


def _in_scope(rel: str) -> bool:
    parts = rel.split("/")
    name = parts[-1]
    if "tests" in parts[:-1] or name.startswith("test_") or name == "conftest.py":
        return False
    return "/alembic/versions/" not in f"/{rel}"


def tracked_python_files() -> list[str]:
    """-z：不转义中文 / 空格路径（默认 quotepath 会给出带引号的八进制串）；工作区里已删的跟踪文件跳过"""
    out = subprocess.run(["git", "ls-files", "-z", "--", "*.py"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout
    return [p for p in out.split("\0") if p and _in_scope(p) and (ROOT / p).is_file()]


def file_violations(rel: str) -> list[str]:
    path = ROOT / rel
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{rel}: 无法读取（{type(exc).__name__}）"]
    problems = []
    lines = len(source.splitlines())
    if lines > MAX_FILE_LINES:
        problems.append(f"{rel}: 文件 {lines} 行 > {MAX_FILE_LINES}")
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError as exc:
        return problems + [f"{rel}:{exc.lineno or 1}: 语法错误，无法统计（{exc.msg}）"]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            span = node.end_lineno - node.lineno + 1
            if span > MAX_FUNC_LINES:
                problems.append(f"{rel}:{node.lineno}: 函数 {node.name} {span} 行 > {MAX_FUNC_LINES}")
    return problems


def main(argv: list[str]) -> int:
    targets = [str(Path(a).resolve().relative_to(ROOT)) for a in argv] or tracked_python_files()
    problems = [p for rel in sorted(targets) if _in_scope(rel) for p in file_violations(rel)]
    for line in problems:
        print(f"❌ SZ {line}")
    if not problems:
        print(f"✓ SZ: 文件 ≤ {MAX_FILE_LINES} 行、函数 ≤ {MAX_FUNC_LINES} 行（{len(targets)} 个文件）")
    return min(len(problems), 255)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
