"""R10 门禁自测：直接抽取 tools/check/arch.sh 的 R10 Python 段，在临时树上跑黄金样例。

覆盖口径：模块级公开函数 + 顶层 *Service / *Mixin 类公开方法（含 staticmethod /
classmethod）；豁免 property 访问器、抽象桩（docstring + ... / pass）、Protocol 类、
非 Service/Mixin 类与私有方法。
"""
import subprocess
import sys
import textwrap
from pathlib import Path

ARCH_SH = Path(__file__).resolve().parents[2] / "tools" / "check" / "arch.sh"

SAMPLE = textwrap.dedent('''
    from typing import Protocol

    def module_ok():
        logger.info("ok")

    def module_bad():
        return 1

    class FooService:
        def __init__(self):
            self.x = 1

        async def logged(self, item_id):
            """docstring 之后第一条即日志"""
            logger.info(f"logged | id={item_id}")
            return item_id

        async def missing(self):
            return 1

        def import_first(self):
            from os import path

            logger.info("日志不在第一条")
            return path

        @staticmethod
        def static_missing():
            return 2

        @classmethod
        def class_ok(cls):
            logger.debug("ok")

        @property
        def prop(self):
            return 3

        @prop.setter
        def prop(self, value):
            self.x = value

        def stub(self):
            """抽象桩"""
            ...

        def stub_pass(self):
            pass

        def _private(self):
            return 4

    class BarMixin:
        def mixin_missing(self):
            return 5

    class PortProtocolService(Protocol):
        def call(self):
            return 6

    class Helper:
        def not_service(self):
            return 7
''')


def _r10_block() -> str:
    text = ARCH_SH.read_text(encoding="utf-8")
    anchor = text.index('R10_OUTPUT="$(')
    start = text.index("\n", text.index("<<'PYEOF'", anchor)) + 1
    end = text.index("\nPYEOF\n", start)
    return text[start:end] + "\n"


def _run(tmp_path: Path) -> list[str]:
    services = tmp_path / "backend" / "services"
    services.mkdir(parents=True)
    (services / "sample.py").write_text(SAMPLE, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-"], input=_r10_block(), text=True,
        capture_output=True, cwd=tmp_path, check=True,
    )
    return [line.split(": def ", 1)[1] for line in proc.stdout.splitlines() if line]


def test_r10_flags_class_methods_and_module_functions(tmp_path):
    hits = _run(tmp_path)
    assert sorted(hits) == sorted([
        "module_bad",
        "FooService.missing",
        "FooService.import_first",
        "FooService.static_missing",
        "BarMixin.mixin_missing",
    ])


def test_r10_output_format_is_path_line_def(tmp_path):
    services = tmp_path / "backend" / "services"
    services.mkdir(parents=True)
    (services / "one.py").write_text("class OneService:\n    def run(self):\n        return 1\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-"], input=_r10_block(), text=True,
        capture_output=True, cwd=tmp_path, check=True,
    )
    assert proc.stdout == "backend/services/one.py:2: def OneService.run"
