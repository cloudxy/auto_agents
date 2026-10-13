"""任务恢复循环 - SpiderTaskConsumer 的重试扫描与超时回收（从 consumer.py 拆出，行为不变）

- _retry_loop：扫 spider:retry_zset 到期成员（score=到期时间戳）→ zrem 原子抢占 →
  重新投递主优先级队列（失败重试退避 1s→5s→15s）
- _recover_loop（P0-1b / P1-4）：running 超时且执行器无活跃记录的孤儿任务置 failed；
  积压 pending（blpop 后进程崩溃丢消息）重建消息对账重投，超限置 failed 闭环

宿主约定（由 SpiderTaskConsumer 提供）：self._running、self._redis、self._engine()、
self._fail_task()、self._requeued_counts。
"""
import asyncio
import json
import time
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.config_consts import TASKS_STALE_TASK_HOURS
from backend.repositories.spider_task_repository import SpiderTaskRepository
from backend.services.spider_task_service import RETRY_ZSET_KEY
from config import settings
from platform_core.logger import get_logger
from platform_core.queues import ACTIVE_TASK_KEY, task_queue
from platform_core.timeutil import utcnow

logger = get_logger("api")

# 重试 ZSET 扫描节奏（秒）与单次最多搬运条数
_RETRY_SCAN_INTERVAL = 1.0
_RETRY_BATCH = 100


class TaskRecoveryMixin:
    """失败重试延迟扫描（期 3）+ running 超时回收（P0-1b）+ 积压 pending 对账重投（P1-4）"""

    _RETRY_SCAN_INTERVAL = _RETRY_SCAN_INTERVAL  # 重试扫描周期（秒）
    _RETRY_BATCH = _RETRY_BATCH  # 单次扫描到期成员上限
    _STALE_BATCH = 100  # 单轮回收扫描的候选任务上限
    # P1-4：同一任务最多对账重投次数（进程内存计数，防止坏消息每轮循环重投）
    _MAX_REQUEUE_ATTEMPTS = 2

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
        cutoff = utcnow() - timedelta(hours=stale_hours)
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
        cutoff = utcnow() - timedelta(hours=stale_hours)
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
            message = self._requeue_message(task)
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

    @staticmethod
    def _requeue_message(task) -> str:
        """由任务行重建分发消息（字段与入队消息一致：task_id / spider_name / params / priority）"""
        return json.dumps(
            {
                "task_id": task.id,
                "spider_name": task.spider_name,
                "params": task.params,
                "priority": task.priority or "normal",
            },
            ensure_ascii=False,
        )
