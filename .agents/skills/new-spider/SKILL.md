---
name: new-spider
description: >-
  创建 Scrapy 爬虫模块。当用户需要从目标网站抓取数据、新建爬虫任务、
  或为已有爬虫添加新的数据字段与管道时触发。
  适用于从零搭建完整爬虫（Spider + Item + Pipeline + Settings），
  以及需要配置反爬策略（延迟、UA 轮换）和数据存储方式（Redis 队列 / Service）的场景。
trigger: >-
  从目标网站抓取数据、新建爬虫任务、为已有爬虫添加字段与管道、
  配置反爬策略（延迟/UA 轮换）、数据存储方式选择（Redis 队列/Service）
---

# 创建 Scrapy 爬虫

当用户需要创建新的爬虫任务时，使用此 Skill 生成完整的 Scrapy 爬虫代码。

## 触发场景

- "爬取某网站的用户信息"
- "创建一个新闻爬虫"
- "抓取商品数据"

## 执行流程

### Step 1: 确认爬虫信息

1. 爬虫名称（英文，小写+下划线）
2. 目标网站 URL
3. 需要爬取的字段
4. 反爬策略（延迟、User-Agent 轮换）
5. 数据存储方式（直接传 Service / 消息队列）

### Step 2: 代码结构

```
scrapy/
├── spiders/{spider_name}_spider.py  # 爬虫主文件
├── items.py                          # 数据项定义
├── pipelines.py                      # 数据管道
├── middlewares.py                    # 中间件
└── settings.py                       # 爬虫配置
```

### Step 3: 代码模板

完整模板见 [references/code-templates.md](references/code-templates.md)，包含：

| 组件 | 文件路径 | 说明 |
|------|---------|------|
| Items | `scrapy/items.py` | 数据字段定义 |
| Spider | `scrapy/spiders/{name}_spider.py` | 爬虫主文件（含 UA 轮换 + 延迟） |
| Pipelines | `scrapy/pipelines.py` | 数据管道（发送到队列/Service） |
| Settings | `scrapy/settings.py` | 并发/延迟/管道配置 |

### Step 4: 运行命令

```bash
scrapy crawl {spider_name}
```

## 预期产出物

完成后**必须**存在以下文件/变更，缺少任何一个 = 未完成：

```
✅ 文件清单
scrapy/spiders/{spider_name}_spider.py   # 爬虫主文件（含 UA 轮换 + DOWNLOAD_DELAY）
scrapy/items.py                          # 新增 {SpiderName}Item 数据字段
scrapy/pipelines.py                      # 新增 {SpiderName}Pipeline 数据管道
scrapy/settings.py                       # ITEM_PIPELINES 已注册新管道
```

## 验证步骤

生成代码后，**必须**依次执行以下验证（调用 `/verify`）：

```bash
# 1. 爬虫可列出
uv run python run_spider.py --list

# 2. 爬虫合约检查
uv run scrapy check {spider_name}

# 3. 架构红线（爬虫不 import backend）
grep -rnE "import backend|from backend" scrapy/spiders/{spider_name}_spider.py
# 期望：输出为空

# 4. 反爬配置检查
grep -nE "DOWNLOAD_DELAY|USER_AGENT" scrapy/settings.py
# 期望：两个配置项均存在
```

全部通过后调用 `/check-arch` 做完整架构扫描。
