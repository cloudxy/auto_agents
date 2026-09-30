"""配置优先级（审计 R4-6 / P0-9）：真实环境变量 > .env 文件

子进程隔离（Dynaconf 在导入期定型，单进程内探测会被已加载的 settings 污染）：
临时 env 目录放一份 .env，同名键同时以环境变量注入，断言环境变量胜出；
仅 .env 有的键仍能读到（.env 只补缺）。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_real_env_var_wins_over_dotenv():
    env_name = f"ztest_{uuid.uuid4().hex[:8]}"
    env_dir = ROOT / "config" / env_name
    env_dir.mkdir()
    try:
        (env_dir / ".env").write_text(
            "AUTO_AGENTS_PRIORITY_PROBE=from_dotenv\nAUTO_AGENTS_DOTENV_ONLY=dotenv_value\n",
            encoding="utf-8",
        )
        code = (
            "from config import settings;"
            "print(settings.get('PRIORITY_PROBE'));"
            "print(settings.get('DOTENV_ONLY'))"
        )
        env = {k: v for k, v in os.environ.items() if not k.startswith("AUTO_AGENTS_")}
        env.update({"APP_ENV": env_name, "AUTO_AGENTS_PRIORITY_PROBE": "from_real_env"})
        out = subprocess.run(
            [sys.executable, "-c", code], cwd=ROOT, env=env,
            capture_output=True, text=True, timeout=60,
        )
        assert out.returncode == 0, out.stderr[-2000:]
        lines = out.stdout.strip().splitlines()[-2:]
        assert lines == ["from_real_env", "dotenv_value"]
    finally:
        shutil.rmtree(env_dir, ignore_errors=True)
