---
name: new-spider
description: >-
  Adds a TaskAwareRedisSpider under scrapy/spiders/ that ships items through
  StorePipeline to Redis. Use when 新建爬虫, 抓站, 加 item 字段, or anti-crawl delay/UA.
---

# 创建 Scrapy 爬虫

先读 `scrapy/spiders/example.py` 再改编。骨架：[references/code-templates.md](references/code-templates.md)。

爬虫只采集和清洗。出口：已有 `StorePipeline` → Redis `spider:item_queue`。

## Route

| 观察到 | 先做 |
|--------|------|
| 要 FastAPI CRUD / 落主库的 API | `new-svc` |
| 只要改后端消费 item 的表结构 | `db-design` / `new-model`，本 skill 只改 Item 字段 |

## Quick start

信息不足时先问：`name`、allowed_domains、字段。

Copy and check off:

```
new-spider:
- [ ] name 小写+下划线，redis_key = {name}:start_urls
- [ ] scrapy/spiders/{name}.py 继承 TaskAwareRedisSpider
- [ ] item 至少写 url / title / source；能复用 BaseItem 就复用
- [ ] 新字段才改 scrapy/items/__init__.py（未声明字段 → KeyError → 任务卡 running）
- [ ] 用现有 Clean/Validate/Quality/Store 管道，不新建 Pipeline、不改 ITEM_PIPELINES
- [ ] 延迟/UA 走 settings + UserAgentMiddleware（站点级延迟写 config/scrapy/）
- [ ] uv run python run.py --list 含新 name
- [ ] bash tools/check/arch.sh 退出码 0
```

队列条目是 JSON `{"url":"...","task_id":123}`（纯 URL 也能兜底）。Worker：`uv run python run.py start spider` 或 `uv run python -m scripts.runlib.spider --spider {name}`。`--list` 没有新 name：修文件后再跑 `--list`。

## 完成时回复

1. spider 路径 + `name` / `redis_key` / `allowed_domains`
2. 若加了 Item 子类，写出新字段名
3. `--list` 与 arch.sh 原文（退出码 0）

## Examples

**Input:** 「抓 zhihu.com 推荐流」

**Then:** 对齐 `scrapy/spiders/zhihu_feed.py`；`--list` 出现该 name；未新建 pipeline。
