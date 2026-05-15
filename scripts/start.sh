#!/bin/bash
# 启动后端服务（统一根 venv）
cd "$(dirname "$0")/.."
uv run python run_backend.py "$@"
