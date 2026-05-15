"""大众点评首页爬虫 - 高风控站点，需代理与会话保持"""
from scrapy_redis.spiders import RedisSpider
from items import BaseItem
from platform_core.logger import get_logger

logger = get_logger("spider")

class DianpingHomeSpider(RedisSpider):
    name = "dianping_home"
    redis_key = "dianping_home:start_urls"
    allowed_domains = ["dianping.com"]
    start_urls = ["https://www.dianping.com"]

    def parse(self, response):
        logger.info(f"正在解析大众点评首页: {response.url}")
        
        # 点评有极强的字体加密和反爬，此处为逻辑演示
        item = BaseItem()
        item['url'] = response.url
        item['title'] = response.css('title::text').get()
        item['source'] = "dianping"
        yield item
