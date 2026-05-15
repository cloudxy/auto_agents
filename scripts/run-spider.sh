#!/bin/bash
# 运行爬虫（统一根 venv）
cd "$(dirname "$0")/.."
uv run python run_spider.py --spider "${1:-example}"
