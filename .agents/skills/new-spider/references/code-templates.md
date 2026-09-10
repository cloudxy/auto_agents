# 爬虫代码模板

## Contents

- Item
- Spider
- 管道与 settings
- 运行

先读再改编：`scrapy/spiders/example.py`、`scrapy/spiders/zhihu_feed.py`。

## Item

新字段才加子类，否则 spider 直接用 `from items import BaseItem`。

`scrapy/items/__init__.py`：

```python
class {SpiderName}Item(BaseItem):
    """{中文名}"""
    extra_field = scrapy.Field()
```

`BaseItem` 已声明 `id/title/url/content/source/task_id/_quality_score` 等。未声明字段写入会 `KeyError` 并卡住任务。

## Spider（`scrapy/spiders/{name}.py`）

```python
from spiders.base import TaskAwareRedisSpider
from items import BaseItem  # 或 {SpiderName}Item
from platform_core.logger import get_logger

logger = get_logger("spider")


class {SpiderName}Spider(TaskAwareRedisSpider):
    name = "{name}"
    redis_key = "{name}:start_urls"
    allowed_domains = ["{domain}"]
    start_urls = ["{target_url}"]

    def parse(self, response):
        logger.info(f"解析: {response.url} | Status: {response.status}")
        for node in response.css(".item-selector"):
            item = BaseItem()
            item["url"] = response.url
            item["title"] = node.css(".title::text").get()
            item["source"] = "{name}"
            yield item
```

- 基类负责解析 Redis 队列 JSON（`url` + `task_id`）并注入 request meta。
- 日志：`platform_core.logger.get_logger("spider")`。
- 延迟与 UA：`scrapy/settings.py` 的 `DOWNLOAD_DELAY` + `middlewares.UserAgentMiddleware`。

## 管道与 settings

已有管道，默认不要新建、不要改 `ITEM_PIPELINES`：

```
pipelines.CleanPipeline
pipelines.ValidatePipeline
pipelines.quality.QualityCheckPipeline
pipelines.StorePipeline          # Redis spider:item_queue，Backend 消费者落库
```

`scrapy_redis.pipelines.RedisPipeline` 已禁用。禁止「调用 Service」或 SQLAlchemy Session。

确需站点级延迟：写 `config/scrapy/` 的 sites 段 `anti_crawl.download_delay`，由 `TaskAwareRedisSpider.from_crawler` 消费。

## 运行

`{name}:start_urls` 队列条目（Backend 消费者投递，见 `scrapy/spiders/base.py`）：

```json
{"url": "https://example.com/page", "task_id": 123}
```

纯 URL 字符串也能兜底。worker 不负责手写 LPUSH；本地冒烟用 `--list` 确认 name 已注册。

```bash
uv run python run.py --list
uv run python run.py start spider
# 或指定爬虫：
uv run python -m scripts.runlib.spider --spider {name}
```
