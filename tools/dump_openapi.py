#!/usr/bin/env python3
"""离线导出后端 OpenAPI schema（工单 81 / D5）

create_app().openapi() 离线生成（不起服务、不连 DB/Redis——路由装饰器
在 import 期即完成模型绑定），输出 JSON 供 openapi-typescript 生成
frontend/shared/src/api/schema.d.ts。后端改字段 → 重跑本脚本 + codegen
即前端类型同步。

用法：uv run python scripts/dump_openapi.py [输出路径]
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT_ROOT / "openapi.json"
    from backend.app import create_app

    schema = create_app().openapi()
    out.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    paths = len(schema.get("paths", {}))
    print(f"OpenAPI schema 已导出: {out}（{paths} paths, openapi {schema.get('openapi')}）")


if __name__ == "__main__":
    main()
