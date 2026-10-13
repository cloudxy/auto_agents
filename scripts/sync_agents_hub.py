#!/usr/bin/env python3
"""把产品 hub 根的 skill/plugin/command/agent 增量同步进能力市场。

hub 根 = SKILLS.AGENTS_ROOT（D2 后默认 runtime/agents-hub，不入库）——**不是**开发协作
中枢 `.agents/`：仓库自己的开发 SOP skill 与第三方插件指针不会被上架。根不存在按空处理
（total=0，不报错）。hash 未变则跳过；新项插入；有变动才更新；许可缺失的新资产不自动上架。
run.py start/restart 会调用。D2 前已入库的 `.agents/...` 行迁移见
scripts/db/migrate_agents_hub_root.py。
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
    parser = argparse.ArgumentParser(description="同步产品 hub 根到能力市场（不扫开发中枢 .agents/）")
    parser.add_argument("--env", choices=["local", "dev", "prod"], default=None)
    parser.add_argument(
        "--root", default=None,
        help="产品 hub 根目录（默认 SKILLS.AGENTS_ROOT=runtime/agents-hub；显式指向 .agents 才会扫开发中枢）",
    )
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
