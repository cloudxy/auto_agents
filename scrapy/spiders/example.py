"""Scrapy 示例爬虫 - 支持 API/Web/嗅探多模式采集"""
from scrapy_redis.spiders import RedisSpider
from ..items import ArticleItem
from core.log_init import get_logger

logger = get_logger("spider")


class ExampleSpider(RedisSpider):
    """
    分布式爬虫示例
    
    1. API 采集：直接请求 JSON 接口
    2. Web 监听：通过中间件捕获 XHR 响应（需配合 DrissionPage）
    3. 页面解析：传统 HTML 提取
    """
    name = "example"
    redis_key = "example:start_urls"
    allowed_domains = ["httpbin.org", "example.com"]
    start_urls = ["https://httpbin.org/get"]

    def parse(self, response):
        """统一解析入口 - 自动识别内容类型"""
        url = response.url
        logger.info(f"正在解析: {url} | Status: {response.status}")

        # 1. API 采集 (JSON)
        if 'application/json' in response.headers.get('Content-Type', b'').decode():
            return self.parse_api(response)
        
        # 2. 页面采集 (HTML)
        return self.parse_html(response)

    def parse_api(self, response):
        """处理 API 响应"""
        data = response.json()
        item = ArticleItem()
        item['url'] = response.url
        item['title'] = f"API Response from {response.url}"
        item['content'] = str(data)  # 存储原始 JSON
        item['source'] = "api"
        yield item

    def parse_html(self, response):
        """处理 HTML 页面"""
        item = ArticleItem()
        item['url'] = response.url
        item['title'] = response.css('title::text').get()
        item['content'] = ''.join(response.css('p::text').getall())
        item['source'] = "web"
        yield item
