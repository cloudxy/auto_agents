"""OpenWeatherMap API 爬虫 - 采集全球天气数据"""
from scrapy import Request
from scrapy_redis.spiders import RedisSpider
from items import WeatherItem
from config import settings
from platform_core.infra.log_init import get_logger

logger = get_logger("spider")

class OpenWeatherSpider(RedisSpider):
    name = "openweather"
    redis_key = "openweather:start_urls"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 从配置中心获取 API Key
        self.api_key = settings.SPIDER_SITES.get('openweather', {}).get('api_key', '')

    def start_requests(self):
        if not self.api_key or self.api_key == "YOUR_API_KEY_HERE":
            logger.error("请在 config/default/spider_sites.yml 中配置 OpenWeather API Key")
            return

        # 示例：采集北京天气
        cities = ["Beijing", "Shanghai", "Shenzhen"]
        for city in cities:
            url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={self.api_key}&units=metric&lang=zh_cn"
            yield Request(url=url, callback=self.parse_weather)

    def parse_weather(self, response):
        data = response.json()
        item = WeatherItem()
        item['url'] = response.url
        item['city'] = data.get('name')
        item['temperature'] = data['main'].get('temp')
        item['humidity'] = data['main'].get('humidity')
        item['description'] = data['weather'][0].get('description')
        item['wind_speed'] = data['wind'].get('speed')
        item['source'] = "openweather_api"
        yield item
