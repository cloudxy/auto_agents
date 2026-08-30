"""Redis 队列约定 - Backend 与 Scrapy 共享的队列/键名常量

数据闭环（阶段 0）：
1. Backend enqueue() 把任务消息 rpush 到 TASK_QUEUE
2. Backend 消费者 blpop TASK_QUEUE：任务 pending → running，
   并把 start URL 投递到 `<spider_name>:start_urls`（scrapy-redis 约定）
3. Scrapy StorePipeline 把结果消息 rpush 到 ITEM_QUEUE（携带 task_id 关联）
4. Backend 消费者 blpop ITEM_QUEUE：结果落库 spider_results + result_count 累加
5. Scrapy 关闭时通过 Webhook 回调 Backend，任务推进到 completed/failed，
   并清除 ACTIVE_TASK_KEY

约定（红线）：
- Scrapy 与 Backend 只通过本模块的键名 + Redis 通信，禁止互相 import
"""
from typing import Final

# Backend → 消费者：任务分发队列（list，消息为 JSON 字符串）
# 阶段 4.1：按优先级拆为三条队列，blpop 多键按序消费（high > normal > low）
TASK_QUEUE_PREFIX: Final[str] = "spider:task_queue:"
TASK_QUEUE_PRIORITIES: Final[tuple] = ("high", "normal", "low")
TASK_QUEUE: Final[str] = "spider:task_queue:normal"  # 兼容旧引用（默认优先级）


def task_queue(priority: str = "normal") -> str:
    """优先级队列键；未知优先级归入 normal"""
    return f"{TASK_QUEUE_PREFIX}{priority if priority in TASK_QUEUE_PRIORITIES else 'normal'}"


# Scrapy → 消费者：采集结果回流队列（list，消息为 JSON 字符串）
ITEM_QUEUE: Final[str] = "spider:item_queue"

# 当前活跃任务关联键（SET，成员为 task_id），用于把结果关联回任务 + 并发槽位控制；
# 阶段 4.1 由 string 升级为 SET：同爬虫可并发运行多个任务（上限见 SPIDER_MAX_CONCURRENT_PER_SPIDER）
ACTIVE_TASK_KEY: Final[str] = "spider:active_tasks:{spider_name}"

# 阶段 4.1 之前的旧活跃键前缀（string 语义），消费者启动时一次性清理，防语义串扰
LEGACY_ACTIVE_TASK_PREFIX: Final[str] = "spider:active_task:"

# 活跃任务关联键的过期时间（秒）：防止爬虫异常退出后悬挂
ACTIVE_TASK_TTL: Final[int] = 86400

# 任务日志偏移量（string，value = 分发时刻日志文件字节大小），用于切出任务日志区间
TASK_LOG_OFFSET_KEY: Final[str] = "spider:task_log_offset:{task_id}"

# 阶段 4.2 数据源多存储：任务级结果缓存（list，元素为结果消息 JSON）；
# store_to=redis 时供直接读取，store_to=csv 时终态落盘后保留至过期，默认 7 天过期
TASK_RESULTS_KEY: Final[str] = "spider:task_results:{task_id}"

# 定时调度器多实例互斥锁（string，SET NX EX 抢占）
SCHEDULER_LOCK_KEY: Final[str] = "spider:scheduler:lock"

# 任务控制键（string，value = pause/stop）：用户通过 API 写入，Scrapy 侧中间件轮询读取
# pause → 抛出 IgnoreRequest 跳过当前请求；stop → close_spider 终止爬虫
# resume → Backend 侧 DELETE 控制键，中间件自然放行
TASK_CONTROL_KEY: Final[str] = "spider:task_control:{task_id}"

# Worker 节点心跳（hash：pid/spiders/started_at/respawn_count），EX 到期未续约视为离线；
# Scrapy 侧只写该键，Backend 侧只读（符合 B2 边界）
WORKER_HEARTBEAT_PREFIX: Final[str] = "spider:worker:"
WORKER_HEARTBEAT_KEY: Final[str] = "spider:worker:{worker_id}"

# 代理池健康管理（B3）：评分驱动的智能代理管理
# HASH: proxy → score (float, 0.0~1.0)
PROXY_SCORES_KEY: Final[str] = "spider:proxy:scores"
# HASH: proxy → JSON({success, fail, avg_latency, last_check})
PROXY_STATS_KEY: Final[str] = "spider:proxy:stats"


__all__ = [
    "TASK_QUEUE_PREFIX",
    "TASK_QUEUE_PRIORITIES",
    "TASK_QUEUE",
    "task_queue",
    "ITEM_QUEUE",
    "ACTIVE_TASK_KEY",
    "ACTIVE_TASK_TTL",
    "TASK_LOG_OFFSET_KEY",
    "TASK_RESULTS_KEY",
    "SCHEDULER_LOCK_KEY",
    "LEGACY_ACTIVE_TASK_PREFIX",
    "WORKER_HEARTBEAT_PREFIX",
    "WORKER_HEARTBEAT_KEY",
    "TASK_CONTROL_KEY",
    "PROXY_SCORES_KEY",
    "PROXY_STATS_KEY",
]
