"""测试进程不得连开发库（审计 BUG-44 / QA-B1-6 回归）"""
import platform_core.db as db


def test_lazy_init_refuses_non_test_database(monkeypatch):
    from config import settings

    monkeypatch.setattr(db, "_IN_PYTEST", True)
    original = settings.get("MYSQL.DEFAULT.DB_NAME")
    settings.set("MYSQL.DEFAULT.DB_NAME", "auto_agents")  # 开发库名
    manager = db.DBManager()
    try:
        manager._init_mysql_all()
    finally:
        settings.set("MYSQL.DEFAULT.DB_NAME", original)
    assert "DEFAULT" not in manager.async_engines
    assert "DEFAULT" not in manager.mysql


def test_lazy_init_keeps_injected_engine(monkeypatch):
    monkeypatch.setattr(db, "_IN_PYTEST", True)
    manager = db.DBManager()
    sentinel = object()
    manager.async_engines["DEFAULT"] = sentinel
    manager._init_mysql_all()
    assert manager.async_engines["DEFAULT"] is sentinel  # 注入的测试引擎不被覆盖


def test_child_process_of_a_test_is_also_guarded():
    """测试里拉起的子进程（run.py start → scripts/sync_agents_hub.py）不 import pytest，
    原先护栏失效、直写开发库（2026-09-29 实证：每跑一次全量测试多 3 条 startup 同步事件）。
    pytest 运行测试时设置 PYTEST_CURRENT_TEST，子进程继承——据此同样拒连非测试库。"""
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    out = subprocess.run(
        [sys.executable, "-c", "import platform_core.db as d; print(d._IN_PYTEST)"],
        cwd=root, env={**os.environ, "PYTEST_CURRENT_TEST": "x (call)", "PYTHONPATH": str(root)},
        capture_output=True, text=True, timeout=60,
    )
    assert out.stdout.strip().splitlines()[-1] == "True", out.stderr[-500:]


def test_tests_use_dedicated_redis_db_not_dev_db():
    """测试进程不写开发 Redis（与 BUG-44 同类）：本机 config/local/redis.yml 的开发库是 DB 0，
    原先测试直连它（刷新令牌防重放标记、限流计数都落进开发库，且跨次运行累积成 429）。
    串行跑用 DB 15；pytest-xdist 并行时每个 worker 各用一个库（gwN → 4 + N % 11），互不串扰。
    """
    import os

    from config import settings

    worker = os.environ.get("PYTEST_XDIST_WORKER", "")
    expected = 4 + int(worker[2:]) % 11 if worker.startswith("gw") else 15
    url = str(settings.get("REDIS.DEFAULT.URL"))
    assert url.rsplit("/", 1)[-1] == str(expected), "测试 Redis 仍指向开发库"
