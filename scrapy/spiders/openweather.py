"""OpenWeatherMap API 爬虫 - 采集全球天气数据

P1-5 修复（2026-08-31）：
- 配置读取：走 SITE_CONFIG + sites 命名空间解包（旧代码读 SPIDER_SITES
  顶层键恒为空，爬虫永远跑不了）；
- 队列语义：删除 start_requests 覆盖（RedisSpider 的 start_requests 是
  无限消费循环，覆盖后收不到 Backend 分发的任务），改为被动执行队列条目，
  URL 缺 appid 时用站点配置的 api_key 注入；
- 密钥安全：入库 url 剥离 appid 参数，防止 API Key 明文落 spider_results。
"""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from scrapy import Request
from spiders.base import TaskAwareRedisSpider
from items import WeatherItem
from platform_core.logger import get_logger

logger = get_logger("spider")

# sites.yml 的占位符（读取逻辑修复后必须拒绝，防止拿占位符发请求）
_PLACEHOLDER_KEYS = ("", "YOUR_API_KEY_HERE")


def strip_appid(url: str) -> str:
    """剥离 URL 中的 appid 查询参数（API Key 不入库、不进日志）"""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "appid"]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


class OpenWeatherSpider(TaskAwareRedisSpider):
    """OpenWeather 天气采集（任务驱动：URL 由 Backend 分发，密钥由站点配置注入）"""

    name = "openweather"
    redis_key = "openweather:start_urls"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key = ""
        self._load_site_config()

    def _load_site_config(self):
        """读取站点配置（延迟到实例化后：settings 由 from_crawler 注入）"""
        try:
            from middlewares import _get_site_config

            site = _get_site_config(self)
        except Exception as e:  # noqa: BLE001 配置异常降级为空（请求层会拒绝）
            logger.warning(f"读取 openweather 站点配置失败: {e}")
            return
        raw_key = site.get("api_key", "")
        self.api_key = str(raw_key).strip() if raw_key else ""

    @property
    def _key_ready(self) -> bool:
        if self.api_key in _PLACEHOLDER_KEYS:
            logger.error(
                "OpenWeather API Key 未配置（config/scrapy/<env>/sites.yml 的 "
                "sites.openweather.api_key，占位符 YOUR_API_KEY_HERE 不生效）"
            )
            return False
        return True

    def make_request_from_data(self, data):
        """队列条目 → 请求：URL 缺 appid 时注入站点配置密钥；无有效密钥则丢弃条目"""
        from spiders.base import parse_queue_entry

        url, task_id, _extra = parse_queue_entry(data)
        if not url:
            logger.warning(f"收到空 URL 条目，丢弃: {data!r}")
            return None
        if "appid=" not in url:
            if not self._key_ready:
                return None  # 无有效密钥：明确丢弃并给出配置指引
            parts = urlsplit(url)
            query = parts.query + ("&" if parts.query else "") + f"appid={self.api_key}"
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
        meta = {"task_id": int(task_id)} if task_id is not None else {}
        return Request(url, meta=meta, callback=self.parse_weather, dont_filter=True)

    def parse_weather(self, response):
        data = response.json()
        item = WeatherItem()
        # 脱敏入库：剥离 appid（API Key），保留其余查询参数
        item['url'] = strip_appid(response.url)
        item['city'] = data.get('name')
        item['temperature'] = data.get('main', {}).get('temp')
        item['humidity'] = data.get('main', {}).get('humidity')
        item['description'] = (data.get('weather') or [{}])[0].get('description')
        item['wind_speed'] = (data.get('wind') or {}).get('speed')
        item['source'] = "openweather_api"
        yield item
