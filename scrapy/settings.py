"""Scrapy 项目配置 - 高并发分布式采集系统"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings as project_settings

# === 基础配置 ===
BOT_NAME = "auto_agents_spider"
SPIDER_MODULES = ["spiders"]
NEWSPIDER_MODULE = "spiders"

# === 动态加载站点配置 ===
# 从 config/scrapy/default/sites.yml 中加载
SITE_CONFIG = project_settings.get("SITES", {})

# === 高并发配置 ===
CONCURRENT_REQUESTS = project_settings.get("CONCURRENT_REQUESTS", 32)
CONCURRENT_REQUESTS_PER_DOMAIN = 16
CONCURRENT_REQUESTS_PER_IP = 0
DOWNLOAD_DELAY = project_settings.get("DOWNLOAD_DELAY", 1)
RANDOMIZE_DOWNLOAD_DELAY = True
DOWNLOAD_TIMEOUT = 30

# === 反爬与风控 ===
COOKIES_ENABLED = False
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# === 重试与异常处理 ===
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]

# === Scrapy-Redis 分布式调度 ===
SCHEDULER = "scrapy_redis.scheduler.Scheduler"
DUPEFILTER_CLASS = "scrapy_redis.dupefilter.RFPDupeFilter"
SCHEDULER_PERSIST = True
SCHEDULER_QUEUE_CLASS = "scrapy_redis.queue.SpiderPriorityQueue"
REDIS_URL = project_settings.REDIS.DEFAULT.URL

# === 中间件配置（按优先级排序）===
DOWNLOADER_MIDDLEWARES = {
    "middlewares.AccountSessionMiddleware": 250, # 优先处理账号会话
    "middlewares.FingerprintMiddleware": 300,
    "middlewares.ProxyMiddleware": 350,
    "middlewares.UserAgentMiddleware": 400,
    "middlewares.RetryMiddleware": 550,
}

# === 管道配置 ===
ITEM_PIPELINES = {
    "scrapy_redis.pipelines.RedisPipeline": 100,
    "pipelines.CleanPipeline": 200,
    "pipelines.ValidatePipeline": 300,
    "pipelines.StorePipeline": 400,
}

# === 日志配置 ===
LOG_LEVEL = project_settings.get("LOG_LEVEL", "INFO")
