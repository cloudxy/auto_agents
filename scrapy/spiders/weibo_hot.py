"""微博热搜榜爬虫 - 需登录态支持"""
from scrapy_redis.spiders import RedisSpider
from items import HotSearchItem
from platform_core.infra.log_init import get_logger

logger = get_logger("spider")

class WeiboHotSpider(RedisSpider):
    name = "weibo_hot"
    redis_key = "weibo_hot:start_urls"
    allowed_domains = ["weibo.com"]
    # 微博热搜通常有专门的移动端或 API 接口，这里以 PC 端为例
    start_urls = ["https://weibo.com/hot/search"]

    def parse(self, response):
        logger.info(f"正在解析微博热搜: {response.url}")
        
        # 微博页面结构复杂且经常变动，建议通过 API 采集
        # 这里演示提取逻辑
        rows = response.css('.list-box .item-box')
        for row in rows:
            item = HotSearchItem()
            item['url'] = response.url
            item['title'] = row.css('.main-text::text').get()
            item['rank'] = row.css('.num::text').get()
            item['source'] = "weibo"
            yield item
