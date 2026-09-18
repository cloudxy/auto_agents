#!/usr/bin/env python3
"""把 .agents 的 skill/plugin/command/agent 增量同步进能力市场。

hash 未变则跳过；新项插入；有变动才更新。run.py start/restart 会调用。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


async def _run(agents_root: Path) -> dict:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from platform_core import init_db, init_log
    from platform_core.db import get_manager
    from sqlalchemy.ext.asyncio import AsyncSession

    from backend.services.power_market.agents_hub import sync_agents_hub

    init_log()
    init_db()
    manager = get_manager()
    engine = manager.async_engines["DEFAULT"]
    try:
        async with AsyncSession(engine) as session:
            result = await sync_agents_hub(session, agents_root, actor="startup")
            await session.commit()
        return result
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="同步 .agents 到能力市场")
    parser.add_argument("--env", choices=["local", "dev", "prod"], default=None)
    parser.add_argument("--root", default=None, help=".agents 目录（默认 SKILLS.AGENTS_ROOT）")
    ns = parser.parse_args(argv)
    if ns.env:
        import os
        os.environ["APP_ENV"] = ns.env
    if ns.root:
        agents_root = Path(ns.root)
    else:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from backend.services.power_market.agents_hub import agents_root as hub_root

        agents_root = hub_root()
    try:
        result = asyncio.run(_run(agents_root))
    except Exception as exc:  # noqa: BLE001 启停路径打印后返回非 0
        print(f"agents_hub 同步失败: {exc}")
        return 1
    print(
        "agents_hub 同步完成 "
        f"total={result['total']} inserted={result['inserted']} "
        f"updated={result['updated']} unchanged={result['unchanged']} "
        f"failed={result['failed']}"
    )
    return 0 if int(result.get("failed") or 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
