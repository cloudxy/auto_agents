# 爬虫代码模板

对齐 `scrapy/spiders/example.py`。启动入口是 `uv run python run_spider.py`，不是 `scrapy crawl`。

## Item（仅新字段时）

加在 `scrapy/items/__init__.py`，继承 `BaseItem`（已含 url/title/content/source/task_id）：

```python
class {SpiderName}Item(BaseItem):
    """{爬虫中文名}"""
    extra_field = scrapy.Field()
```

## Spider（`scrapy/spiders/{spider_name}.py`）

```python
from spiders.base import TaskAwareRedisSpider
from items import BaseItem
from platform_core.logger import get_logger

logger = get_logger("spider")


class {SpiderName}Spider(TaskAwareRedisSpider):
    name = "{spider_name}"
    redis_key = "{spider_name}:start_urls"
    allowed_domains = ["{domain}"]

    def parse(self, response):
        logger.info(f"解析页面: {response.url} | Status: {response.status}")
        item = BaseItem()
        item["url"] = response.url
        item["title"] = response.css("title::text").get()
        item["content"] = "".join(response.css("p::text").getall())
        item["source"] = "web"
        yield item
```

- 队列条目由 Backend 投递，基类解析 JSON `{url, task_id}`。不要覆盖 `start_requests` 把 Redis 消费循环吃掉（见 `openweather.py` 注释）。
- 需要站点密钥时从 `sites.yml` 读，禁止把 API Key 写入 item / 日志。

## Pipeline / Settings

不要新建。全局管道已在 `scrapy/settings.py`：

`CleanPipeline` → `ValidatePipeline` → `QualityCheckPipeline` → `StorePipeline`

`StorePipeline` 只推 Redis。禁止在爬虫里 `import sqlalchemy` / `get_async_db` / `import backend`。

反爬（R5/R6）在 `scrapy/settings.py`，由 config 的 `DOWNLOAD_DELAY` 与 UA 中间件提供，不要在 spider 里 `time.sleep`。

## 运行

```bash
uv run python run_spider.py --list
uv run python run_spider.py --spider {spider_name}
```
