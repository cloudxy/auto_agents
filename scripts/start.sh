#!/bin/bash
# 启动后端服务（使用 backend 独立环境）
cd "$(dirname "$0")/../backend"
uv run python ../run_app.py
