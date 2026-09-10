"""知乎推荐页爬虫 - 需登录态与会话保持"""
from spiders.base import TaskAwareRedisSpider
from items import ZhihuFeedItem
from platform_core.logger import get_logger

logger = get_logger("spider")

class ZhihuFeedSpider(TaskAwareRedisSpider):
    name = "zhihu_feed"
    redis_key = "zhihu_feed:start_urls"
    allowed_domains = ["zhihu.com"]
    start_urls = ["https://www.zhihu.com"]

    def parse(self, response):
        logger.info(f"正在解析知乎推荐流: {response.url}")
        
        # 知乎内容通常在 div.Card 中
        cards = response.css('div.Card')
        for card in cards:
            item = ZhihuFeedItem()
            item['url'] = response.url
            item['title'] = card.css('h2.ContentItem-title::text').get()
            item['author'] = card.css('.AuthorInfo-name::text').get()
            item['vote_count'] = card.css('.VoteButton--up::text').get()
            item['source'] = "zhihu"
            yield item
