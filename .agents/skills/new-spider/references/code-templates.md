# 爬虫代码模板

## Items

```python
import scrapy

class {SpiderName}Item(scrapy.Item):
    """{爬虫中文名}数据项"""
    id = scrapy.Field()
    title = scrapy.Field()
    content = scrapy.Field()
    url = scrapy.Field()
```

## Spider

```python
import scrapy
import random
import time
from scrapy.utils.logger import logger

class {SpiderName}Spider(scrapy.Spider):
    name = "{spider_name}"
    allowed_domains = ["{domain}"]
    start_urls = ["{target_url}"]
    
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    ]
    
    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url=url,
                callback=self.parse,
                headers={"User-Agent": random.choice(self.user_agents)}
            )
    
    def parse(self, response):
        logger.info(f"解析页面: {response.url}")
        items = response.css(".item-selector")
        
        for item in items:
            data = {SpiderName}Item()
            data["title"] = item.css(".title::text").get()
            
            if self._validate_data(data):
                yield data
            
            time.sleep(random.uniform(1, 3))
    
    def _validate_data(self, data):
        if not data.get("title"):
            logger.warning(f"数据缺少标题")
            return False
        return True
```

## Pipelines

```python
from scrapy.utils.logger import logger

class {SpiderName}Pipeline:
    def open_spider(self, spider):
        logger.info(f"爬虫启动: {spider.name}")
    
    def process_item(self, item, spider):
        logger.info(f"处理数据: {dict(item)}")
        # 发送到消息队列或调用 Service
        return item
    
    def close_spider(self, spider):
        logger.info(f"爬虫关闭: {spider.name}")
```

## Settings

```python
BOT_NAME = "{spider_name}"
SPIDER_MODULES = ["scrapy.spiders"]
NEWSPIDER_MODULE = "scrapy.spiders"

CONCURRENT_REQUESTS = 4
DOWNLOAD_DELAY = 2

ITEM_PIPELINES = {
    "scrapy.pipelines.{SpiderName}Pipeline": 300,
}
```

## 运行命令

```bash
scrapy crawl {spider_name}
```
