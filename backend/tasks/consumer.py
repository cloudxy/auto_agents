"""Redis 任务/结果双队列消费者 - 数据闭环的 Backend 侧引擎

运行模型（随 FastAPI lifespan 启动，见 backend/app/__init__.py）：
- _dispatch_loop：blpop spider:task_queue → 任务置 running → 写活跃任务关联 →
  把 start URL 投递到 `<spider_name>:start_urls`（scrapy-redis 消费）
- _ingest_loop：lpop 批量拉取 spider:item_queue → 批量 accumulate + 定期 flush →
  bulk insert + result_count 批量累加（单次 commit）
- _retry_loop：扫 spider:retry_zset 到期成员（score=到期时间戳）→
  zrem 原子抢占 → 重新投递主优先级队列（失败重试退避 1s→5s→15s）

失败策略：
- 单条消息处理失败只记日志，不中断循环（队列消费不丢循环）
- 任务消息缺 urls 时直接把任务置 failed（错误信息可追溯到任务行）
"""
import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timedelta
from typing import List, Optional

import redis.asyncio as aioredis
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from backend.app.core.config_consts import (TASKS_STALE_TASK_HOURS)
from platform_core.db import get_manager
from platform_core.logger import get_logger
from platform_core.queues import (
    ACTIVE_TASK_KEY,
    ACTIVE_TASK_TTL,
    DEAD_ITEM_QUEUE,
    ITEM_QUEUE,
    LEGACY_ACTIVE_TASK_PREFIX,
    TASK_CONTROL_KEY,
    TASK_LOG_OFFSET_KEY,
    TASK_QUEUE_PRIORITIES,
    TASK_RESULTS_KEY,
    task_queue,
)
from platform_core.models.spider_result import SpiderResult
from backend.repositories.spider_result_repository import SpiderResultRepository
from backend.repositories.spider_task_repository import SpiderTaskRepository
from backend.services.spider_service import (
    FLOW_SPIDER_NAME,
    extract_flow,
    extract_store_targets,
    resolve_spider_log_path,
)
from backend.services.spider_task_service import RETRY_ZSET_KEY

logger = get_logger("api")

# blpop 超时（秒）：超时后回到循环顶部检查运行开关，保证可优雅退出
_BLPOP_TIMEOUT = 5

# 期 3：ingest 批量化 —— 单次 lpop 拉取条数（替代逐条 blpop 的 Redis round-trip）
_INGEST_POP_COUNT = 20
# 无新消息时的休眠秒数：保证定期 flush 节奏 + 避免 lpop 空转烧 CPU
# （原 blpop timeout=1 同等语义：无消息时最多约该间隔才做一次 flush 检查）
_INGEST_IDLE_SLEEP = 0.2
# 重试 ZSET 扫描节奏（秒）与单次最多搬运条数
_RETRY_SCAN_INTERVAL = 1.0
_RETRY_BATCH = 100


def extract_start_urls(params: Optional[str]) -> List[str]:
    """从任务 params（JSON 字符串）中提取 start URL 列表

    约定：params 形如 {"urls": ["https://..."]}；缺 urls / 解析失败返回空列表。
    """
    if not params:
        return []
    try:
        data = json.loads(params)
    except (TypeError, ValueError):
        logger.warning(f"任务 params 不是合法 JSON: {params!r}")
        return []
    if isinstance(data, dict):
        urls = data.get("urls")
        if isinstance(urls, list):
            return [str(u) for u in urls if u]
    if isinstance(data, list):
        return [str(u) for u in data if u]
    return []


def extract_selectors(params: Optional[str]) -> List[dict]:
    """从任务 params 中提取选择器规则（自定义采集类型专属，普通类型为空）

    约定：params 形如 {"urls": [...], "selectors": [{"name":..., "type":..., "expr":...}]}。
    """
    if not params:
        return []
    try:
        data = json.loads(params)
    except (TypeError, ValueError):
        return []
    if isinstance(data, dict):
        selectors = data.get("selectors")
        if isinstance(selectors, list):
            return [s for s in selectors if isinstance(s, dict)]
    return []


def extract_render_params(params: Optional[str]) -> dict:
    """M4：flow 任务专属，从任务 params 提取 JS 渲染参数（仅白名单键 + 严格类型）

    flow_generic 在 make_request_from_data 从 start_urls 载荷的 params 字段读取
    render_js/wait_for/wait_timeout；其余 params 键不透传（防意外注入）。"""
    if not params:
        return {}
    try:
        data = json.loads(params)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    render: dict = {}
    if isinstance(data.get("render_js"), bool):
        render["render_js"] = data["render_js"]
    wait_for = data.get("wait_for")
    if isinstance(wait_for, str) and wait_for:
        render["wait_for"] = wait_for
    wait_timeout = data.get("wait_timeout")
    if isinstance(wait_timeout, (int, float)) and not isinstance(wait_timeout, bool):
        render["wait_timeout"] = int(wait_timeout)
    return render


def build_start_payload(
    url: str,
    task_id,
    flow: Optional[dict],
    selectors: List[dict],
    render_params: Optional[dict] = None,
) -> str:
    """start URL 载荷构建：{"url", "task_id", flow|selectors, params?}

    flow 任务且存在渲染参数时携带 params（对齐 flow_generic 的读取约定）；
    非 flow 任务载荷结构保持 {"url","task_id","selectors"} 零变化。"""
    payload_extra = {"flow": flow} if flow is not None else (
        {"selectors": selectors} if selectors else {}
    )
    if flow is not None and render_params:
        payload_extra["params"] = render_params
    return json.dumps({"url": url, "task_id": task_id, **payload_extra}, ensure_ascii=False)


class SpiderTaskConsumer:
    """Redis 双队列消费者（任务分发 + 结果回流）"""

    async def start(self) -> None:
        """启动两个消费循环（幂等：重复调用不叠加）"""
        if self._running:
            return
        # B3：归一异步 Redis 门面（共享连接池，键契约见 platform_core.queues）
        from platform_core.redis_async import get_async_redis

        self._redis = get_async_redis()
        await self._purge_legacy_active_keys()
        self._running = True
        self._loops = [
            asyncio.create_task(self._dispatch_loop(), name="spider-task-dispatch"),
            asyncio.create_task(self._ingest_loop(), name="spider-item-ingest"),
            asyncio.create_task(self._retry_loop(), name="spider-retry-scan"),
        ]
        # P0-1b：running 任务超时回收循环（STALE_TASK_HOURS=0 时关闭）
        stale_hours = float(settings.get("TASKS.STALE_TASK_HOURS", TASKS_STALE_TASK_HOURS) or 0)
        if stale_hours > 0:
            self._loops.append(
                asyncio.create_task(self._recover_loop(), name="spider-stale-recover")
            )
        logger.info(
            f"队列消费者已启动: tasks={[task_queue(p) for p in TASK_QUEUE_PRIORITIES]}, "
            f"items={ITEM_QUEUE}, retry_zset={RETRY_ZSET_KEY}, "
            f"stale_recover={'on(%.0fh)' % stale_hours if stale_hours > 0 else 'off'}"
        )

    async def _purge_legacy_active_keys(self) -> None:
        """一次性清理阶段 4.1 之前的旧活跃键（string 语义，前缀不带 s）

        新语义用 SET（spider:active_tasks:*）；旧键残留会让旧版前端/脚本误读，
        且与 SET 键并存时易混淆，启动时统一删除（容忍 Redis 异常）。
        """
        try:
            stale = [k async for k in self._redis.scan_iter(match=f"{LEGACY_ACTIVE_TASK_PREFIX}*")]
            if stale:
                await self._redis.delete(*stale)
                logger.info(f"已清理旧版活跃键: {len(stale)} 个")
        except Exception as e:  # noqa: BLE001 清理失败不阻断启动（旧键有 TTL 自然过期）
            logger.warning(f"清理旧版活跃键失败: {e}")

    async def stop(self) -> None:
        """优雅停止：取消循环并关闭 Redis 连接"""
        self._running = False
        for task in self._loops:
            task.cancel()
        for task in self._loops:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 退出路径兜底
                pass
        self._loops = []
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        logger.info("队列消费者已停止")

    # ------------------------------------------------------------------
    # 任务分发：pending → running → 投递 start URL
    # ------------------------------------------------------------------
    async def _dispatch_loop(self) -> None:
        # 优先级多队列：blpop 多键按列表顺序检查，天然实现 high > normal > low
        queues = [task_queue(p) for p in TASK_QUEUE_PRIORITIES]
        while self._running:
            try:
                message = await self._redis.blpop(queues, timeout=_BLPOP_TIMEOUT)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 连接抖动等：退避重试
                logger.error(f"任务队列 blpop 失败: {e}")
                await asyncio.sleep(2)
                continue
            if not message:
                continue
            try:
                await self._dispatch(json.loads(message[1]))
            except Exception as e:  # noqa: BLE001 单条消息失败不中断循环
                logger.error(f"任务分发失败: raw={message[1]!r}, error={e}")

    async def _dispatch(self, msg: dict) -> None:
        task_id = msg.get("task_id")
        spider_name = msg.get("spider_name", "")
        logger.info(f"消费任务消息: task_id={task_id}, spider={spider_name}")

        # A4：分发前检查控制键，如果已有 stop 控制键则直接置 failed（用户已终止）
        try:
            control_val = await self._redis.get(TASK_CONTROL_KEY.format(task_id=task_id))
            if control_val and str(control_val).strip().lower() == "stop":
                await self._fail_task(task_id, "user_stopped")
                await self._redis.delete(TASK_CONTROL_KEY.format(task_id=task_id))
                logger.info(f"任务分发前已终止（用户控制）: task_id={task_id}")
                return
        except Exception as e:  # noqa: BLE001
            logger.warning(f"分发前检查控制键失败（放行）: task_id={task_id}, error={e}")

        # 阶段 5.1：识别流程参数 → 统一切到 flow_generic 爬虫执行；
        # 任务行同步改写，保证活跃键/并发槽位/关闭回调与实际执行爬虫一致。
        flow = extract_flow(msg.get("params"))
        if flow is not None and spider_name != FLOW_SPIDER_NAME:
            spider_name = FLOW_SPIDER_NAME
            async with AsyncSession(self._engine()) as session:
                await SpiderTaskRepository(session).update(task_id, spider_name=FLOW_SPIDER_NAME)
                await session.commit()
            logger.info(f"流程采集任务切换执行爬虫: task_id={task_id} → {FLOW_SPIDER_NAME}")

        urls = extract_start_urls(msg.get("params"))
        if not urls:
            await self._fail_task(task_id, "params 缺少 urls，无法分发采集目标")
            return

        # 1. 任务置 running（同时写 started_at，供运行时长统计）
        async with AsyncSession(self._engine()) as session:
            repo = SpiderTaskRepository(session)
            task = await repo.update(task_id, status="running", started_at=func.now())
            await session.commit()
            if task is None:
                logger.warning(f"任务不存在，丢弃消息: task_id={task_id}")
                return

        # 2. 写活跃任务关联（供并发槽位控制 / 终态回调）+ 投递 start URL
        # 任一步失败都会导致任务卡死 running（blpop 后消息已丢），用 _fail_task 兜底推终态。
        # 先校验任务仍存在再写活跃键：若任务在排队期间被删除，
        # 旧投递会让活跃集合残留幽灵成员，后续任务的并发槽位会被错误占用。
        try:
            async with AsyncSession(self._engine()) as session:
                check_repo = SpiderTaskRepository(session)
                still_exists = await check_repo.get_by_id(task_id)
            if still_exists is None:
                logger.warning(f"任务已不存在（可能已被删除），丢弃分发: task_id={task_id}")
                return
            active_key = ACTIVE_TASK_KEY.format(spider_name=spider_name)
            await self._redis.sadd(active_key, task_id)
            await self._redis.expire(active_key, ACTIVE_TASK_TTL)
            # 记录当前日志文件偏移量：供日志隔离切出本任务区间（各并发任务各自记录）
            await self._record_log_offset(task_id)
            # 3. 投递 start URL（scrapy-redis 约定键 `<spider_name>:start_urls`）
            # 载荷统一包装为 JSON 并携带 task_id：并发下结果归属走请求 meta（精确），
            # TaskAwareRedisSpider / generic 解析 JSON；scrapy-redis 对 start_urls 天然 dont_filter。
            # M4：flow 任务透传 AI 规划的 JS 渲染配置（flow_generic 从载荷 params 读取），
            # 其余 params 键不透传防意外注入；非 flow 任务载荷结构零变化。
            selectors = extract_selectors(msg.get("params"))
            render_params = extract_render_params(msg.get("params")) if flow is not None else {}
            payloads = [
                build_start_payload(u, task_id, flow, selectors, render_params)
                for u in urls
            ]
            for payload in payloads:
                await self._redis.rpush(f"{spider_name}:start_urls", payload)
        except Exception as e:  # noqa: BLE001
            logger.error(f"投递采集任务失败: task_id={task_id}, spider={spider_name}, error={e}")
            await self._fail_task(task_id, f"投递 start URL 失败: {e}")
            return

        logger.info(
            f"任务已分发: task_id={task_id}, spider={spider_name}, urls={len(urls)}"
        )

    async def _record_log_offset(self, task_id) -> None:
        """记录分发时刻的爬虫日志文件大小（失败仅记日志，不阻断分发）"""
        try:
            log_path = resolve_spider_log_path()
            offset = os.path.getsize(log_path) if log_path and os.path.isfile(log_path) else 0
            await self._redis.set(
                TASK_LOG_OFFSET_KEY.format(task_id=task_id), offset, ex=ACTIVE_TASK_TTL
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"记录任务日志偏移量失败: task_id={task_id}, error={e}")

    async def _fail_task(self, task_id, error_message: str) -> None:
        """把任务直接置 failed（消息无法正常处理时）"""
        try:
            async with AsyncSession(self._engine()) as session:
                repo = SpiderTaskRepository(session)
                await repo.update(task_id, status="failed", error_message=error_message)
                await session.commit()
            logger.warning(f"任务置 failed: task_id={task_id}, reason={error_message}")
        except Exception as e:  # noqa: BLE001
            logger.error(f"任务置 failed 失败: task_id={task_id}, error={e}")

    async def _accept_message(self, raw: str, message: dict) -> bool:
        """消息准入校验（P1-4）：缺 task_id 的结果转入死信队列留档，不再静默丢弃"""
        if message.get("task_id"):
            return True
        logger.warning(
            f"结果消息缺少 task_id，转入死信队列 {DEAD_ITEM_QUEUE}: "
            f"spider={message.get('spider_name', '')}"
        )
        try:
            await self._redis.rpush(DEAD_ITEM_QUEUE, raw)
        except Exception as e:  # noqa: BLE001 死信写入失败不阻断回流主路径
            logger.error(f"死信队列写入失败: {e}")
        return False

    # ------------------------------------------------------------------
    # 失败重试延迟扫描（期 3）：ZSET 到期成员重新入主队列
    # ------------------------------------------------------------------
    async def _retry_loop(self) -> None:
        """重试扫描循环：每 tick 扫到期成员，与 dispatch/ingest 并行的独立小节

        入队侧：SpiderTaskService._reenqueue 失败重试时 ZADD（score=到期时间戳）。
        出队侧：本循环 zrangebyscore 取到期成员 → zrem 原子抢占 → rpush 主队列。
        """
        while self._running:
            try:
                await self._scan_retry_zset()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 扫描失败只记日志，不中断循环
                logger.error(f"重试扫描异常: {e}")
            await asyncio.sleep(self._RETRY_SCAN_INTERVAL)

    async def _scan_retry_zset(self) -> None:
        """扫描到期成员并重新入主队列（zrem 抢占防多实例重复入队）"""
        now = time.time()
        due = await self._redis.zrangebyscore(
            RETRY_ZSET_KEY, "-inf", now, start=0, num=self._RETRY_BATCH
        )
        if not due:
            return
        for raw in due:
            # zrem 原子抢占：多实例部署时同一到期成员只被一个消费者搬走
            removed = await self._redis.zrem(RETRY_ZSET_KEY, raw)
            if not removed:
                continue  # 已被其他实例抢占
            try:
                msg = json.loads(raw)
                queue_key = task_queue(str(msg.get("priority") or "normal"))
                await self._redis.rpush(queue_key, raw)
                logger.info(
                    f"重试任务到期重新入队: task_id={msg.get('task_id')}, queue={queue_key}"
                )
            except Exception as e:  # noqa: BLE001
                # 入队失败回滚 ZSET（延迟 5s 再试），防消息丢失
                try:
                    await self._redis.zadd(RETRY_ZSET_KEY, {raw: time.time() + 5})
                except Exception as rollback_err:  # noqa: BLE001
                    # 回滚也失败（M-2 评审修复）：消息已被 zrem 移除且无法恢复，
                    # DB 兜底置 failed（对齐 SpiderTaskService._reenqueue 投递失败
                    # 置 failed 语义），避免任务永远停留在 running/pending 悬挂
                    logger.error(
                        f"重试任务重新入队失败且回滚 ZSET 失败，任务置 failed 兜底: "
                        f"error={e}, rollback_error={rollback_err}"
                    )
                    task_id = None
                    try:
                        task_id = json.loads(raw).get("task_id")
                    except (TypeError, ValueError):
                        pass
                    await self._fail_task(task_id, "重试重新入队失败（消息丢失）")

    # ------------------------------------------------------------------
    # running 任务超时回收（P0-1b）：防爬虫崩溃/webhook 丢失导致任务永久卡 running
    # ------------------------------------------------------------------
    _STALE_BATCH = 100  # 单轮回收扫描的候选任务上限
    # P1-4：同一任务最多对账重投次数（进程内存计数，防止坏消息每轮循环重投）
    _MAX_REQUEUE_ATTEMPTS = 2

    def __init__(self):
        self._running = False
        self._loops: List[asyncio.Task] = []
        self._redis: Optional[aioredis.Redis] = None
        self._requeued_counts: dict[int, int] = {}

    async def _recover_loop(self) -> None:
        """超时回收循环：孤儿 running 置 failed + 积压 pending 对账重投"""
        interval = float(settings.get("TASKS.STALE_RECOVER_INTERVAL", 300) or 300)
        while self._running:
            try:
                await self._recover_stale_once()
                await self._requeue_stale_pending()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 回收失败不中断循环
                logger.error(f"任务超时回收/对账异常: {e}")
            await asyncio.sleep(max(5.0, interval))

    async def _recover_stale_once(self) -> None:
        """单轮回收：running 超过 STALE_TASK_HOURS 且不在对应爬虫活跃集合的任务 → failed

        判定依据：dispatch 时写入活跃集合（sadd + TTL）；爬虫进程崩溃后集合成员
        不被移除（靠 TTL 自然过期），因此"超时 + 集合无此成员"是孤儿任务的有效
        信号。Redis 异常时保守跳过（member 视为存在，不误杀存活任务）。
        不做自动重试：坏站点/失效选择器会形成无限失败循环，交由用户重新运行。
        """
        stale_hours = float(settings.get("TASKS.STALE_TASK_HOURS", TASKS_STALE_TASK_HOURS) or 0)
        if stale_hours <= 0 or self._redis is None:
            return
        cutoff = datetime.now() - timedelta(hours=stale_hours)
        async with AsyncSession(self._engine()) as session:
            candidates = await SpiderTaskRepository(session).find_stale_running(
                cutoff, limit=self._STALE_BATCH
            )
        orphans = []
        for task in candidates:
            active_key = ACTIVE_TASK_KEY.format(spider_name=task.spider_name)
            try:
                member = bool(await self._redis.sismember(active_key, task.id))
            except Exception as e:  # noqa: BLE001 Redis 异常：保守视为仍在运行
                logger.warning(f"活跃集合查询失败（跳过回收）: task_id={task.id}, error={e}")
                continue
            if not member:
                orphans.append(task)
        for task in orphans:
            await self._fail_task(
                task.id,
                f"任务超时回收：running 超过 {stale_hours:g} 小时且执行器无活跃记录"
                "（爬虫可能崩溃或回调丢失），请检查日志后重新运行",
            )
        if orphans:
            logger.warning(
                f"超时回收完成: {len(orphans)} 个孤儿任务置 failed, "
                f"task_ids={[t.id for t in orphans]}"
            )

    async def _requeue_stale_pending(self) -> None:
        """积压 pending 对账重投（P1-4）：blpop 后进程崩溃会丢任务消息，
        任务永久 pending——超过阈值且从未启动的任务重建消息重新入队；
        同一任务重投超过 _MAX_REQUEUE_ATTEMPTS 次仍无效则置 failed 闭环。
        """
        stale_hours = float(settings.get("TASKS.STALE_TASK_HOURS", TASKS_STALE_TASK_HOURS) or 0)
        if stale_hours <= 0 or self._redis is None:
            return
        cutoff = datetime.now() - timedelta(hours=stale_hours)
        async with AsyncSession(self._engine()) as session:
            candidates = await SpiderTaskRepository(session).find_stale_pending(
                cutoff, limit=self._STALE_BATCH
            )
        for task in candidates:
            attempts = self._requeued_counts.get(task.id, 0)
            if attempts >= self._MAX_REQUEUE_ATTEMPTS:
                await self._fail_task(
                    task.id,
                    f"任务长期 pending 且对账重投 {attempts} 次仍无消费进展，"
                    "请检查消费者与队列后重新创建任务",
                )
                self._requeued_counts.pop(task.id, None)
                continue
            message = json.dumps(
                {
                    "task_id": task.id,
                    "spider_name": task.spider_name,
                    "params": task.params,
                    "priority": task.priority or "normal",
                },
                ensure_ascii=False,
            )
            try:
                await self._redis.rpush(
                    task_queue(str(task.priority or "normal")), message
                )
            except Exception as e:  # noqa: BLE001 重投失败下轮再试
                logger.error(f"积压任务重投失败: task_id={task.id}, error={e}")
                continue
            self._requeued_counts[task.id] = attempts + 1
            logger.warning(
                f"积压任务对账重投（第 {attempts + 1} 次）: task_id={task.id}, "
                f"spider={task.spider_name}"
            )

    # ------------------------------------------------------------------
    # 结果回流：批量 accumulate + 定期 flush（高吞吐优化）
    # ------------------------------------------------------------------
    _BATCH_SIZE = 50          # 单次 flush 最大条数
    _FLUSH_INTERVAL = 2.0     # 秒：无新消息时最长等待
    _POP_COUNT = _INGEST_POP_COUNT   # 单次 lpop 拉取条数（期 3 批量化）
    _IDLE_SLEEP = _INGEST_IDLE_SLEEP  # 无新消息时休眠秒数
    _RETRY_SCAN_INTERVAL = _RETRY_SCAN_INTERVAL  # 重试扫描周期（秒）
    _RETRY_BATCH = _RETRY_BATCH  # 单次扫描到期成员上限

    async def _ingest_loop(self) -> None:
        """批量结果回流循环 — lpop 批量拉取 + accumulate + 定期 flush

        与旧版逐条 blpop 不同：单次 lpop(count=N) 批量弹出，减少 Redis
        round-trip；消息先 accumulate 到内存批次，达到 batch_size 或
        flush_interval 后统一 bulk insert + 单次 commit。
        """
        batch: list[dict] = []
        batch_counts: dict[int, int] = {}  # task_id → count
        last_flush = asyncio.get_event_loop().time()

        while self._running:
            try:
                # 批量弹出（count=N）：一次往返取多条，显著减少逐条 blpop 的往返开销
                raws = await self._redis.lpop(ITEM_QUEUE, count=self._POP_COUNT)
                for raw in raws or []:
                    try:
                        message = json.loads(raw)
                    except (TypeError, ValueError):
                        logger.warning(f"结果消息 JSON 解析失败，跳过: raw={raw!r}")
                        continue
                    if not await self._accept_message(raw, message):
                        continue
                    batch.append(message)
                    tid = message["task_id"]
                    batch_counts[tid] = batch_counts.get(tid, 0) + 1

                now = asyncio.get_event_loop().time()
                if batch and (
                    len(batch) >= self._BATCH_SIZE
                    or now - last_flush >= self._FLUSH_INTERVAL
                ):
                    await self._flush_batch(batch, batch_counts)
                    batch.clear()
                    batch_counts.clear()
                    last_flush = now

                if not raws:
                    # 无新消息：短暂休眠保持定期 flush 节奏，避免 lpop 空转
                    await asyncio.sleep(self._IDLE_SLEEP)

            except asyncio.CancelledError:
                # 关停路径：先尝试 flush 当前批次防丢数据（flush 自身失败仅记日志，
                # 也要 re-raise CancelledError，保证关停路径不吞取消信号）
                if batch:
                    try:
                        await self._flush_batch(batch, batch_counts)
                        batch.clear()
                        batch_counts.clear()
                    except Exception as e:  # noqa: BLE001 flush 失败不阻断取消传播
                        logger.error(f"关停 flush 残余批次失败: {e}")
                raise
            except Exception as e:  # noqa: BLE001
                logger.error(f"ingest 循环异常: {e}")
                await asyncio.sleep(1)

        # 退出前 flush 残余批次
        if batch:
            try:
                await self._flush_batch(batch, batch_counts)
            except Exception as e:  # noqa: BLE001
                logger.error(f"退出前 flush 残余批次失败: {e}")

    async def _flush_batch(
        self, messages: list[dict], counts: dict[int, int]
    ) -> None:
        """批量落库：bulk insert + 批量 result_count 累加 + 多存储双写

        单次 session 完成所有操作，最后统一 commit；
        增量去重（B5）和多存储镜像（4.2）均在此处理。

        counts 入参仅为兼容旧签名保留，实际不使用：flush 入口按本批
        messages 一次性重算计数（m-5 评审修复），保证 flush 失败重试
        幂等（去重扣减不跨轮次累计，详见下方注释）。
        """
        if not messages:
            return

        # ── 0. 按本批 messages 一次性重算计数（m-5 评审修复）──
        # 调用方的 counts 在 flush 失败重试场景下会被上一轮的去重扣减污染
        # （失败 → 同一批次连同已扣减的 counts 原样重试），继续在其上扣减
        # 会让重试轮次重复扣减、唯一未去重结果的计数被错误归零；
        # 本地按 messages 重算是幂等基准，调用方 dict 保持只读。
        counts = {}
        for msg in messages:
            tid = msg["task_id"]
            counts[tid] = counts.get(tid, 0) + 1

        async with AsyncSession(self._engine()) as session:
            # ── 1. 加载批次内涉及的 task params（增量去重 + 多存储目标）──
            task_params_cache: dict[int, dict] = {}
            task_store_cache: dict[int, list[str]] = {}
            for tid in counts:
                task = await SpiderTaskRepository(session).get_by_id(tid)
                params = {}
                if task and task.params:
                    try:
                        params = json.loads(task.params)
                    except (TypeError, ValueError):
                        pass
                task_params_cache[tid] = params
                task_store_cache[tid] = extract_store_targets(
                    task.params if task else None
                )

            # ── 2. 构建 SpiderResult 实例（跳过增量去重命中项）──
            result_repo = SpiderResultRepository(session)
            instances: list[SpiderResult] = []
            mirror_msgs: list[tuple[int, dict]] = []  # (task_id, msg)

            for msg in messages:
                task_id = msg["task_id"]
                spider_name = msg.get("spider_name", "")
                item = msg.get("item") or {}
                item_type = msg.get("item_type", "BaseItem")

                # B1：数据质量评分（与 _ingest 一致，pop 避免进 extra）
                quality_score = item.pop("_quality_score", None)

                # B5：content_hash = md5(url + title + content)
                url_val = str(item.get("url") or "")[:500]
                title_val = item.get("title") or ""
                content_val = item.get("content") or ""
                content_hash = hashlib.md5(
                    f"{url_val}{title_val}{content_val}".encode()
                ).hexdigest()

                # 增量去重（B5）：task params.incremental=true 时跳过重复
                params = task_params_cache.get(task_id, {})
                if params.get("incremental") and content_hash:
                    existing = await result_repo.find_by_content_hash(content_hash, tenant_id=msg.get("tenant_id"))
                    if existing:
                        logger.debug(
                            f"增量去重：重复内容已跳过: hash={content_hash}, url={url_val}"
                        )
                        # 去重项不计入 result_count，修正 batch_counts
                        counts[task_id] = max(0, counts[task_id] - 1)
                        continue

                # 未映射字段进 extra
                mapped = {"url", "title", "content", "source"}
                extra = {k: v for k, v in item.items() if k not in mapped}

                instances.append(
                    SpiderResult(
                        task_id=task_id,
                        spider_name=spider_name,
                        tenant_id=msg.get("tenant_id"),
                        item_type=item_type,
                        url=url_val or None,
                        title=item.get("title"),
                        content=item.get("content"),
                        source=item.get("source"),
                        extra=(
                            json.dumps(extra, ensure_ascii=False, default=str)
                            if extra
                            else None
                        ),
                        quality_score=quality_score,
                        content_hash=content_hash,
                    )
                )
                mirror_msgs.append((task_id, msg))

            # ── 3. 批量插入（含租户配额·结果存储检查）──
            if instances:
                _tenants = {msg.get("tenant_id") for _, msg in mirror_msgs if msg.get("tenant_id")}
                for tid in _tenants:
                    from backend.services.quota_service import QuotaService

                    await QuotaService(session).check_result_storage(tid)
                session.add_all(instances)

            # ── 4. 批量累加 result_count ──
            await SpiderTaskRepository(session).batch_increment_result_counts(counts)

            # ── 5. 多存储双写（4.2）：命中 redis/csv 目标时追加任务级缓存 ──
            await self._mirror_batch(mirror_msgs, task_store_cache)

            # ── 6. 单次 commit ──
            await session.commit()

        logger.debug(
            f"批量落库完成: {len(messages)} 条消息, "
            f"{len(instances)} 条入库, {len(counts)} 个任务"
        )

    async def _mirror_batch(
        self,
        mirror_msgs: list[tuple[int, dict]],
        task_store_cache: dict[int, list[str]],
    ) -> None:
        """批量多存储双写：按 task_id 分组 rpush 到对应 TASK_RESULTS_KEY"""
        ttl = int(settings.get("STORAGE.REDIS_RESULT_TTL", 604800))
        # 按 task_id 聚合，减少 Redis 调用次数
        grouped: dict[int, list[str]] = {}
        for task_id, msg in mirror_msgs:
            targets = task_store_cache.get(task_id, [])
            if not targets:
                continue
            key = TASK_RESULTS_KEY.format(task_id=task_id)
            grouped.setdefault(task_id, []).append(
                json.dumps(msg, ensure_ascii=False, default=str)
            )
        for task_id, payloads in grouped.items():
            try:
                key = TASK_RESULTS_KEY.format(task_id=task_id)
                await self._redis.rpush(key, *payloads)
                await self._redis.expire(key, ttl)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"批量结果缓存双写失败: task_id={task_id}, error={e}")

    # ------------------------------------------------------------------
    # 单条结果回流（保留供向后兼容 / 直接调用场景）
    # ------------------------------------------------------------------
    async def _ingest(self, msg: dict) -> None:
        task_id = msg.get("task_id")
        spider_name = msg.get("spider_name", "")
        item = msg.get("item") or {}
        if not task_id:
            logger.warning(f"结果消息缺少 task_id，跳过: spider={spider_name}")
            return

        item_type = msg.get("item_type", "BaseItem")
        # 数据质量评分（B1）：由 Scrapy 侧 QualityCheckPipeline 写入 item
        quality_score = item.pop("_quality_score", None)

        # B5：计算 content_hash（md5 of url+title+content），用于增量去重
        url_val = str(item.get("url") or "")[:500]
        title_val = item.get("title") or ""
        content_val = item.get("content") or ""
        content_hash = hashlib.md5(
            f"{url_val}{title_val}{content_val}".encode()
        ).hexdigest()

        mapped = {"url", "title", "content", "source"}
        extra = {k: v for k, v in item.items() if k not in mapped}
        async with AsyncSession(self._engine()) as session:
            # B5：增量模式去重——任务 params.incremental=true 时跳过重复内容
            task_repo = SpiderTaskRepository(session)
            task = await task_repo.get_by_id(task_id)
            params = {}
            if task and task.params:
                try:
                    params = json.loads(task.params)
                except (TypeError, ValueError):
                    pass
            if params.get("incremental") and content_hash:
                existing = await SpiderResultRepository(session).find_by_content_hash(content_hash)
                if existing:
                    logger.debug(f"增量去重：重复内容已跳过: hash={content_hash}, url={url_val}")
                    return

            repo = SpiderResultRepository(session)
            await repo.create_for_task(
                task_id=task_id,
                spider_name=spider_name,
                item_type=item_type,
                url=url_val or None,
                title=item.get("title"),
                content=item.get("content"),
                source=item.get("source"),
                extra=json.dumps(extra, ensure_ascii=False, default=str) if extra else None,
                quality_score=quality_score,
                content_hash=content_hash,
            )
            await session.commit()
            # 数据源多存储（4.2）：store_to 命中 redis/csv 时追加任务级结果缓存列表，
            # redis 目标供直读，csv 目标终态后由 Service 落盘（失败不影响落库主路径）
            await self._mirror_result(session, task_id, msg)
        logger.info(
            f"结果已落库: task_id={task_id}, spider={spider_name}, item={item_type}"
        )

    async def _mirror_result(self, session, task_id: int, msg: dict) -> None:
        """数据源多存储双写（4.2）：查任务 store_to，命中则追加任务级结果缓存列表"""
        logger.debug(f"检查结果缓存双写目标: task_id={task_id}")
        try:
            task = await SpiderTaskRepository(session).get_by_id(task_id)
            targets = extract_store_targets(task.params if task else None)
            if not targets:
                return
            key = TASK_RESULTS_KEY.format(task_id=task_id)
            await self._redis.rpush(key, json.dumps(msg, ensure_ascii=False, default=str))
            ttl = int(settings.get("STORAGE.REDIS_RESULT_TTL", 604800))
            await self._redis.expire(key, ttl)
        except Exception as e:  # noqa: BLE001 双写失败仅告警，不影响落库主路径
            logger.warning(f"结果缓存双写失败: task_id={task_id}, error={e}")

    @staticmethod
    def _engine():
        return get_manager().async_engines["DEFAULT"]
