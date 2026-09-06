---
name: new-spider
description: >-
  创建 Scrapy 爬虫模块。当用户需要从目标网站抓取数据、新建爬虫任务、
  或为已有爬虫添加新的数据字段与管道时触发。
  适用于从零搭建完整爬虫（Spider + Item + 反爬 + Redis 队列），
  以及需要配置反爬策略（延迟、UA 轮换）和数据存储方式（Redis 队列）的场景。
trigger: >-
  从目标网站抓取数据、新建爬虫任务、为已有爬虫添加字段、
  配置反爬策略（延迟/UA 轮换）、数据存储方式（Redis 队列）
---

# 创建 Scrapy 爬虫

对齐现行布局：`scrapy-redis` + `TaskAwareRedisSpider`，数据出口只有 Redis 队列。
禁止 `scrapy crawl` 当主入口，禁止新建单体 `items.py` / `pipelines.py`。

## 触发场景

- "爬取某网站的用户信息"
- "创建一个新闻爬虫"
- "抓取商品数据"

## 执行流程

### Step 1: 确认爬虫信息

1. 爬虫名称（英文，小写+下划线，等于 `Spider.name`）
2. 目标网站 URL / `allowed_domains`
3. 字段：优先复用 `items.BaseItem`；新字段再加子类
4. 反爬：全局在 `scrapy/settings.py`（`DOWNLOAD_DELAY` 从 config 注入）。站点级 delay 见 `TaskAwareRedisSpider` 对 `sites.yml` 的消费
5. 存储：只能走现有 `pipelines.StorePipeline` → Redis（`platform_core.queues.ITEM_QUEUE`），Backend 消费者落库

### Step 2: 代码结构（现行）

```
scrapy/
├── spiders/{spider_name}.py     # 继承 TaskAwareRedisSpider
├── spiders/base.py              # 基类，不要改 unless 队列协议变了
├── items/__init__.py            # Item 定义（继承 BaseItem）
├── pipelines/                   # Clean / Validate / quality / Store —— 不要为单个爬虫新建管道
├── middlewares/
└── settings.py                  # 全局；不要改 BOT_NAME，不要给每个爬虫再注册 ITEM_PIPELINES
```

对照实现：`scrapy/spiders/example.py`、`scrapy/spiders/openweather.py`。

### Step 3: 代码模板

完整模板见 [references/code-templates.md](references/code-templates.md)。

### Step 4: 运行命令

```bash
uv run python run_spider.py --list
uv run python run_spider.py --spider {spider_name}
```

## 预期产出物

```
scrapy/spiders/{spider_name}.py          # TaskAwareRedisSpider，name / redis_key 已设
scrapy/items/__init__.py                 # 仅当有新字段：新增 {SpiderName}Item(BaseItem)
```

不要产出：`scrapy/items.py`、`scrapy/pipelines.py`、每爬虫一条 `ITEM_PIPELINES`。

## 验证步骤

```bash
uv run python run_spider.py --list
bash scripts/check-arch.sh
```

`--list` 必须出现新 name。R3/R4/R5/R6 以脚本为准，不要另 grep。
