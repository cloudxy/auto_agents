from __future__ import annotations

import os
import sys

from .paths import ROOT, VENV_PYTHON, ensure_sys_path


def reexec_with_venv() -> None:
    ensure_sys_path()
    if not VENV_PYTHON.exists():
        return
    if os.path.realpath(sys.executable) == os.path.realpath(VENV_PYTHON):
        return
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])


def apply_env(name: str | None) -> None:
    if name:
        os.environ["APP_ENV"] = name
    os.chdir(ROOT)
