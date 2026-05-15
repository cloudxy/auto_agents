---
name: new-spider
description: 创建 Scrapy 爬虫模块
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

#### Items

```python
import scrapy

class {SpiderName}Item(scrapy.Item):
    """{爬虫中文名}数据项"""
    id = scrapy.Field()
    title = scrapy.Field()
    content = scrapy.Field()
    url = scrapy.Field()
```

#### Spider

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

#### Pipelines

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

#### Settings

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

### Step 4: 运行命令

```bash
scrapy crawl {spider_name}
```
