#!/usr/bin/env python3
"""统一启停入口。实现见 scripts/runlib/。初始化请用 init_project.sh。"""
from __future__ import annotations

from scripts.runlib.ctl import main

if __name__ == "__main__":
    raise SystemExit(main())
