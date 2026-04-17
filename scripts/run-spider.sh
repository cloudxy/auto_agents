#!/bin/bash
# 运行爬虫（使用 scrapy 独立环境）
cd "$(dirname "$0")/../scrapy"
uv run python ../run_spider.py --spider ${1:-example}
