"""Scrapy 项目配置 - 高并发分布式采集系统

数据源：根目录 config/ 的 Dynaconf 实例（scrapy 和 backend 共享）
数据出口：Redis 队列（scrapy-redis），禁止直连 MySQL
"""
import os
import sys

# 将项目根加入 sys.path，保证 `from config import settings` 能加载
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config import settings as project_settings

# === 基础配置 ===
BOT_NAME = "auto_agents_spider"
SPIDER_MODULES = ["spiders"]
NEWSPIDER_MODULE = "spiders"

# === 动态加载站点配置 ===
SITE_CONFIG = project_settings.get("SITES", {})
# 爬虫侧站点配置（数据源 config/scrapy/default/sites.yml），供 spider 读取 api_key 等
SPIDER_SITES = project_settings.get("SITES", {})

# === 高并发配置 ===
CONCURRENT_REQUESTS = project_settings.get("CONCURRENT_REQUESTS", 32)
CONCURRENT_REQUESTS_PER_DOMAIN = 16
CONCURRENT_REQUESTS_PER_IP = 0
DOWNLOAD_DELAY = project_settings.get("DOWNLOAD_DELAY", 1)
RANDOMIZE_DOWNLOAD_DELAY = True
DOWNLOAD_TIMEOUT = 30

# === 反爬与风控（红线必备） ===
ROBOTSTXT_OBEY = project_settings.get("ROBOTSTXT_OBEY", False)
COOKIES_ENABLED = project_settings.get("COOKIES_ENABLED", False)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# === 重试与异常处理 ===
RETRY_TIMES = project_settings.get("RETRY_TIMES", 3)
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]

# === 代理池（配置化，默认关闭；见 config/scrapy/*/settings.yml） ===
PROXY_ENABLED = project_settings.get("PROXY_ENABLED", False)
PROXY_LIST = project_settings.get("PROXY_LIST", []) or []
PROXY_REDIS_KEY = project_settings.get("PROXY_REDIS_KEY", "") or ""

# === Scrapy-Redis 分布式调度 ===
SCHEDULER = "scrapy_redis.scheduler.Scheduler"
DUPEFILTER_CLASS = "scrapy_redis.dupefilter.RFPDupeFilter"
SCHEDULER_PERSIST = True
SCHEDULER_QUEUE_CLASS = "scrapy_redis.queue.SpiderPriorityQueue"
REDIS_URL = project_settings.REDIS.DEFAULT.URL

# === 中间件配置（按优先级排序）===
DOWNLOADER_MIDDLEWARES = {
    "middlewares.AccountSessionMiddleware": 250,
    "middlewares.FingerprintMiddleware": 300,
    "middlewares.ProxyMiddleware": 350,
    "middlewares.UserAgentMiddleware": 400,
    "middlewares.TaskControlMiddleware": 542,
    "middlewares.RetryMiddleware": 550,
    "middlewares.playwright_dm.PlaywrightMiddleware": 590,
}

# 任务归属：把响应 meta 的 task_id 注入 Item（阶段 4.1，并发结果精确归属）
SPIDER_MIDDLEWARES = {
    "middlewares.TaskAttributionSpiderMiddleware": 543,
}

# === 管道配置 ===
ITEM_PIPELINES = {
    # P1-8：scrapy-redis 自带 RedisPipeline 已禁用——它把每条 item 再复制到
    # <spider>:items 键，全仓无消费者且无 TTL（内存无限增长）；真实数据出口
    # 是 StorePipeline → spider:item_queue（backend 消费者回流落库）
    "scrapy_redis.pipelines.RedisPipeline": None,
    "pipelines.CleanPipeline": 200,
    "pipelines.ValidatePipeline": 300,
    "pipelines.quality.QualityCheckPipeline": 350,
    "pipelines.StorePipeline": 400,
}

# === 数据质量监控（B1）===
# 映射 config 的 QUALITY_CHECK 段（config/default/settings.yml）到 scrapy Settings。
# 注意：Scrapy Settings 不支持嵌套 dict 的点号读取（settings.get("QUALITY_CHECK.ENABLED")
# 会静默回退默认值），因此必须用平铺键 QUALITY_CHECK_*，quality 管道同步读平铺键。
# config 缺失时默认启用（与 config 默认值 true 及既有默认行为一致）。
QUALITY_CHECK_ENABLED = project_settings.get("QUALITY_CHECK.ENABLED", True)
QUALITY_CHECK_REQUIRED_FIELDS = list(
    project_settings.get("QUALITY_CHECK.REQUIRED_FIELDS", ["url"])
)
QUALITY_CHECK_CORE_FIELDS = list(
    project_settings.get("QUALITY_CHECK.CORE_FIELDS", ["url", "title", "content"])
)

# === 扩展配置 ===
# 爬虫关闭时向 Backend 回调任务终态（数据闭环最后一步）
EXTENSIONS = {
    "extensions.SpiderCloseWebhook": 100,
    "extensions.IdleAutoClose": 110,
}

# 空闲自动收尾（秒）：>0 时单次任务模式下连续空闲即以 finished 收尾；0=禁用（常驻 Worker）
IDLE_CLOSE_SECONDS = project_settings.get("SPIDER_IDLE_CLOSE_SECONDS", 0)

# === Playwright 动态渲染（可选依赖，默认关闭）===
PLAYWRIGHT_ENABLED = project_settings.get("PLAYWRIGHT.ENABLED", False)
PLAYWRIGHT_MAX_PAGES = project_settings.get("PLAYWRIGHT.MAX_PAGES", 2)
PLAYWRIGHT_TIMEOUT = project_settings.get("PLAYWRIGHT.TIMEOUT", 30)
PLAYWRIGHT_BROWSER = project_settings.get("PLAYWRIGHT.BROWSER", "chromium")

# === 日志配置 ===
LOG_LEVEL = project_settings.get("LOG_LEVEL", "INFO")
