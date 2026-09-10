#!/bin/bash
# 数据库迁移（统一根 venv；alembic.ini 的 script_location 相对 backend/ 目录）
cd "$(dirname "$0")/../backend"
APP_ENV="${APP_ENV:-local}" ../.venv/bin/alembic -c alembic.ini upgrade head
