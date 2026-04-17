"""百度热搜榜爬虫 - 采集 PC 端实时热点"""
from scrapy_redis.spiders import RedisSpider
from items import HotSearchItem
from platform_core.infra.log_init import get_logger

logger = get_logger("spider")

class BaiduHotSpider(RedisSpider):
    name = "baidu_hot"
    redis_key = "baidu_hot:start_urls"
    allowed_domains = ["top.baidu.com"]
    start_urls = ["https://top.baidu.com/board?platform=pc&sa=pcindex_entry"]

    def parse(self, response):
        logger.info(f"正在解析百度热搜: {response.url}")
        
        # 百度热搜通常通过接口或页面内的 JSON 数据渲染
        # 这里演示如何从页面提取（实际可能需要分析 API）
        items = response.css('.category-wrap_iQLoo')
        
        for item in items:
            hot_item = HotSearchItem()
            hot_item['url'] = response.url
            hot_item['title'] = item.css('.c-single-text-ellipsis::text').get()
            hot_item['heat_value'] = item.css('.hot-index_1Bl1a::text').get()
            hot_item['source'] = "baidu"
            yield hot_item
