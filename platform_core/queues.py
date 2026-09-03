"""Redis 队列约定 - Backend 与 Scrapy 共享的队列/键名常量 + 分布式锁设施

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
import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator, Final

from platform_core.logger import get_logger

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger("queues")

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

# 结果回流死信队列（list）：消息缺 task_id 等无法归属的结果转入此处留档排查，
# 不再静默丢弃（P1-4）；人工排查后可重放或清理，无 TTL
DEAD_ITEM_QUEUE: Final[str] = "spider:item_dead"

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

# ── 技能域（方案 A；键名契约唯一源红线）──────────────────────────────
# AI 评分队列（list：lpush 入队 / blpop 消费，SkillScoringService 串行逐个评）
SKILL_SCORE_QUEUE: Final[str] = "skill:score_queue"
# 评分器分布式锁（多实例互斥，worker 启动抢占）
SKILL_SCORER_LOCK: Final[str] = "skill:scorer:lock"
# 扫描互斥锁（scan_library 并发防护）
SKILL_SCAN_LOCK: Final[str] = "skill:scan:lock"
# 公开 API 按 IP 限流计数（INCR+EXPIRE 每分钟窗口，A-P4-1 第三道闸）
SKILL_PUBLIC_RATE_PREFIX: Final[str] = "skill:public:rl:"
# ── B1 限流键契约（backend/app/core/rate_limiter.py 策略表引用）──
# 登录失败计数（按用户名，15 分钟窗口，达 5 次锁）
LOGIN_FAIL_PREFIX: Final[str] = "login_fail:"
# 注册尝试计数（按 IP，成功失败均计）
REGISTER_ATTEMPT_PREFIX: Final[str] = "register_fail:"
# 租户自助注册限流（按 IP，无鉴权写面 fail-closed）
SIGNUP_RATE_PREFIX: Final[str] = "tenant:signup:rl:"
# 配额检查计数缓存（B4：60s TTL，免逐行回流 COUNT 全表）
QUOTA_COUNT_PREFIX: Final[str] = "quota:count:"
# ── B3：LLM 用量与 new-api 渠道调度键契约（原散落字符串字面量收口）──
# LLM token 用量：日明细 hash（30 天 TTL）/ 月汇总 hash（93 天 TTL）/ 聚合锁
LLM_USAGE_DAILY_PREFIX: Final[str] = "llm:usage:d:"
LLM_USAGE_MONTHLY_PREFIX: Final[str] = "llm:usage:m:"
LLM_USAGE_FLUSH_LOCK: Final[str] = "llm:usage:flush:lock"
# new-api 渠道调度：渠道级配置 hash / 探针锁 / 调度器锁与状态
NEWAPI_CHANNEL_CFG_PREFIX: Final[str] = "newapi:channel:cfg:"
NEWAPI_PROBE_LOCK: Final[str] = "newapi:probe:lock"
NEWAPI_SCHEDULER_LOCK: Final[str] = "newapi:scheduler:lock"
NEWAPI_SCHEDULER_STATE: Final[str] = "newapi:scheduler:state"
# LLM 周期健康巡检分布式锁（B-M4-2，多实例单跑）
LLM_PATROL_LOCK: Final[str] = "llm:patrol:lock"


# ── 共享分布式锁设施（全仓库唯一锁样板定义处，禁止再手写锁样板） ──────
# 语义：SET key token NX EX ttl 抢占 → Lua 原子释放/续期（GET==token 才 DEL/EXPIRE）。
# 释放不用 GETDEL：它是无条件删除，锁过期被他人抢占时会误删别人的锁；
# 也不用 GET+DEL：非原子，两步之间存在过期易主窗口，同样会误删。
# 调用方：channel_probe / channel_scheduler / schedule 三处 tick 循环。

# 原子释放（token 比对 DEL）
_LOCK_RELEASE_LUA: Final[str] = (
    "if redis.call('GET', KEYS[1]) == ARGV[1] then "
    "return redis.call('DEL', KEYS[1]) end return 0"
)
# 原子续期（token 比对 EXPIRE）
_LOCK_RENEW_LUA: Final[str] = (
    "if redis.call('GET', KEYS[1]) == ARGV[1] then "
    "return redis.call('EXPIRE', KEYS[1], ARGV[2]) end return 0"
)


class _LockHandle:
    """已持有的锁句柄：唯一 token + 原子续期 + 原子释放

    lost 属性：续期发现锁已丢失（TTL 过期被他人抢占 / Redis 故障）时置 True，
    持有方应感知后立即退出本轮临界区（保守语义：宁可少跑，不可双跑）。
    """

    __slots__ = ("_redis", "_key", "_token", "_ttl", "_renewal_task", "lost")

    def __init__(self, redis: "Redis", key: str, token: str, ttl: int):
        self._redis = redis
        self._key = key
        self._token = token
        self._ttl = ttl
        self._renewal_task: asyncio.Task | None = None
        self.lost = False

    @property
    def token(self) -> str:
        """本次持有的唯一 token（uuid4 hex）"""
        return self._token

    async def renew(self) -> bool:
        """原子续期：token 匹配才 EXPIRE。

        返回 True=续期成功；False=锁已丢失或 Redis 异常（保守感知），
        调用方应立即退出本轮临界区。
        """
        try:
            ok = await self._redis.eval(_LOCK_RENEW_LUA, 1, self._key, self._token, self._ttl)
            if not ok:
                self.lost = True
            return bool(ok)
        except Exception as e:  # noqa: BLE001 Redis 故障按丢失处理（保守语义）
            logger.warning(f"分布式锁续期失败（key={self._key}）: {e}")
            self.lost = True
            return False

    async def release(self) -> None:
        """原子释放：token 匹配才 DEL；释放失败交由 TTL 兑底（不向上抛）"""
        if self._renewal_task is not None:
            self._renewal_task.cancel()
            try:
                await self._renewal_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 退出路径兑底
                pass
            self._renewal_task = None
        try:
            await self._redis.eval(_LOCK_RELEASE_LUA, 1, self._key, self._token)
        except Exception as e:  # noqa: BLE001 释放失败交由 TTL 兑底
            logger.warning(f"分布式锁释放失败（key={self._key}，交由 TTL 兑底）: {e}")

    def _start_auto_renewal(self, interval: float) -> None:
        """启动后台续期任务（异常安全：renew 内部捕获一切异常，
        续期失败置 lost 并让任务自然退出，绝不向上传播）"""

        async def _renew_loop() -> None:
            while True:
                await asyncio.sleep(interval)
                if not await self.renew():
                    logger.warning(
                        f"分布式锁后台续期失败，已标记 lost（key={self._key}）"
                    )
                    return  # 锁已丢失，续期任务退出；持有方通过 lost 感知

        self._renewal_task = asyncio.create_task(_renew_loop())


@asynccontextmanager
async def distributed_lock(
    redis: "Redis", key: str, ttl: int, *, renewal: float | None = None
) -> AsyncIterator[_LockHandle | None]:
    """共享分布式锁（异步上下文管理器）：未抢到 yield None，调用方早退跳过本轮。

    用法（与三处 tick 循环的早退习惯一致）：
        async with distributed_lock(redis, key, ttl=60) as lock:
            if lock is None:
                return  # 其他实例持有中，跳过本轮
            ... 临界区 ...
            if lock.lost:      # 可选：长临界区中检查锁是否仍归属自己
                return

    - 获取：SET key uuid4-token NX EX ttl；Redis 异常按未抢到处理（保守跳过）
    - 释放：finally 中 Lua 原子释放（token 比对 DEL），早退/异常路径同样释放；
      释放失败交由 TTL 兑底
    - renewal：可选后台自动续期间隔（秒，须小于 ttl）；不传则不自动续期。
      续期失败（锁易主/Redis 故障）→ lock.lost = True，持有方主动感知退出

    redis 参数兼容 redis.asyncio.Redis（或任何实现 set/get/eval 的异步客户端）。
    """
    token = uuid.uuid4().hex
    try:
        acquired = await redis.set(key, token, nx=True, ex=ttl)
    except Exception as e:  # noqa: BLE001 Redis 故障按未抢到处理，宁可不做不可双跑
        logger.warning(f"分布式锁获取异常，本轮跳过（key={key}）: {e}")
        acquired = False
    if not acquired:
        yield None
        return
    handle = _LockHandle(redis, key, token, ttl)
    if renewal:
        handle._start_auto_renewal(renewal)
    try:
        yield handle
    finally:
        await handle.release()


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
    "SKILL_SCORE_QUEUE",
    "SKILL_SCORER_LOCK",
    "SKILL_SCAN_LOCK",
    "SKILL_PUBLIC_RATE_PREFIX",
    "LOGIN_FAIL_PREFIX",
    "REGISTER_ATTEMPT_PREFIX",
    "SIGNUP_RATE_PREFIX",
    "QUOTA_COUNT_PREFIX",
    "LLM_USAGE_DAILY_PREFIX",
    "LLM_USAGE_MONTHLY_PREFIX",
    "LLM_USAGE_FLUSH_LOCK",
    "NEWAPI_CHANNEL_CFG_PREFIX",
    "NEWAPI_PROBE_LOCK",
    "NEWAPI_SCHEDULER_LOCK",
    "NEWAPI_SCHEDULER_STATE",
    "LLM_PATROL_LOCK",
    "distributed_lock",
]
