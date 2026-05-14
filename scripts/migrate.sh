#!/bin/bash
# 数据库迁移（统一根 venv）
cd "$(dirname "$0")/.."
uv run alembic -c backend/alembic.ini upgrade head
