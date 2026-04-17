#!/bin/bash
# 数据库迁移（使用 backend 独立环境）
cd "$(dirname "$0")/../backend"
uv run python -m alembic upgrade head
