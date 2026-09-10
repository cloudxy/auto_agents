from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENV_PYTHON = ROOT / ".venv" / "bin" / "python3"
RUN_DIR = ROOT / "runtime" / "run"


def ensure_sys_path() -> None:
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def ensure_run_dir() -> Path:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    return RUN_DIR
