"""结果回流循环 - SpiderTaskConsumer 的 ingest 侧（从 consumer.py 拆出，行为不变）

- _ingest_loop：lpop 批量拉取 spider:item_queue（空则取 REDO 重放队列）→
  批量 accumulate + 定期 flush（落库见 consumer_store.ResultStoreMixin）
- 毒消息隔离（审计 R2-1）：基础设施故障整批暂存 REDO、不计重放次数；数据类故障
  逐条隔离落库，单条连续失败达 _MAX_REDO_ATTEMPTS 次进死信

宿主约定（由 SpiderTaskConsumer 提供）：self._running、self._redis、self._engine()、
self._fail_task()。
"""
import asyncio
import json

from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SATimeoutError

from backend.tasks.consumer_store import ResultStoreMixin
from platform_core.logger import get_logger
from platform_core.queues import DEAD_ITEM_QUEUE, ITEM_QUEUE, ITEM_REDO_QUEUE

logger = get_logger("api")

# 期 3：ingest 批量化 —— 单次 lpop 拉取条数（替代逐条 blpop 的 Redis round-trip）
_INGEST_POP_COUNT = 20
# 回流失败的单条消息最多重放次数，超过进死信（审计 R2-1：毒消息不再无限循环）
_MAX_REDO_ATTEMPTS = 3
_REDO_ATTEMPTS_KEY = "_redo_attempts"
# 基础设施类故障（库/网络不可用）：整批暂存重放，不计入单条重放次数
_TRANSIENT_ERRORS = (OperationalError, InterfaceError, SATimeoutError, ConnectionError, OSError)
# 无新消息时的休眠秒数：保证定期 flush 节奏 + 避免 lpop 空转烧 CPU
# （原 blpop timeout=1 同等语义：无消息时最多约该间隔才做一次 flush 检查）
_INGEST_IDLE_SLEEP = 0.2


class ResultIngestMixin(ResultStoreMixin):
    """结果回流：批量 accumulate + 定期 flush（高吞吐优化）+ 失败批次隔离恢复"""

    _BATCH_SIZE = 50          # 单次 flush 最大条数
    _FLUSH_INTERVAL = 2.0     # 秒：无新消息时最长等待
    _POP_COUNT = _INGEST_POP_COUNT   # 单次 lpop 拉取条数（期 3 批量化）
    _IDLE_SLEEP = _INGEST_IDLE_SLEEP  # 无新消息时休眠秒数

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
                raws = await self._pop_raw_items()
                await self._accumulate(raws, batch, batch_counts)
                last_flush = await self._flush_if_due(batch, batch_counts, last_flush)

                if not raws:
                    # 无新消息：短暂休眠保持定期 flush 节奏，避免 lpop 空转
                    await asyncio.sleep(self._IDLE_SLEEP)

            except asyncio.CancelledError:
                # 关停路径：先尝试 flush 当前批次防丢数据（flush 自身失败仅记日志，
                # 也要 re-raise CancelledError，保证关停路径不吞取消信号）
                await self._flush_before_cancel(batch, batch_counts)
                raise
            except Exception as e:  # noqa: BLE001
                await self._on_ingest_error(batch, batch_counts, e)

        # 退出前 flush 残余批次
        if batch:
            try:
                await self._flush_batch(batch, batch_counts)
            except Exception as e:  # noqa: BLE001
                logger.error(f"退出前 flush 残余批次失败: {e}")

    async def _pop_raw_items(self):
        """批量弹出（count=N）：一次往返取多条，显著减少逐条 blpop 的往返开销

        主队列为空时再取 REDO 重放队列。"""
        raws = await self._redis.lpop(ITEM_QUEUE, count=self._POP_COUNT)
        if not raws:
            raws = await self._redis.lpop(ITEM_REDO_QUEUE, count=self._POP_COUNT)
        return raws

    async def _accumulate(self, raws, batch: list[dict], batch_counts: dict[int, int]) -> None:
        """解析 + 准入校验后原地追加进内存批次（JSON 非法跳过，缺 task_id 进死信）"""
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

    async def _flush_if_due(
        self, batch: list[dict], batch_counts: dict[int, int], last_flush: float,
    ) -> float:
        """达到 batch_size 或距上次 flush 超过 flush_interval 则批量落库并清空批次

        返回最新的 last_flush（未 flush 时原样返回）。"""
        now = asyncio.get_event_loop().time()
        if batch and (
            len(batch) >= self._BATCH_SIZE
            or now - last_flush >= self._FLUSH_INTERVAL
        ):
            await self._flush_batch(batch, batch_counts)
            batch.clear()
            batch_counts.clear()
            return now
        return last_flush

    async def _flush_before_cancel(self, batch: list[dict], batch_counts: dict[int, int]) -> None:
        """关停（CancelledError）前 flush 当前批次；flush 失败仅记日志，由调用方继续 re-raise"""
        if batch:
            try:
                await self._flush_batch(batch, batch_counts)
                batch.clear()
                batch_counts.clear()
            except Exception as e:  # noqa: BLE001 flush 失败不阻断取消传播
                logger.error(f"关停 flush 残余批次失败: {e}")

    async def _on_ingest_error(
        self, batch: list[dict], batch_counts: dict[int, int], error: Exception,
    ) -> None:
        """循环异常：记日志 → 内存批次走隔离恢复（R2-1）后清空 → 退避 1s"""
        logger.error(f"ingest 循环异常: {type(error).__name__}: {error}")
        if batch:
            await self._recover_failed_batch(list(batch), error)
            batch.clear()
            batch_counts.clear()
        await asyncio.sleep(1)

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

    async def _recover_failed_batch(self, batch: list[dict], error: Exception) -> None:
        """批次落库失败后的隔离恢复（审计 R2-1）

        - 基础设施故障（库连接/超时）：整批原样进 REDO，不计重放次数，等依赖恢复；
        - 数据类故障（唯一键冲突、字段超长等）：逐条单独落库，好消息照常入库，
          仍失败的单条累加重放次数，超过上限进死信留档——一条毒消息不再拖住整批。
        """
        if isinstance(error, _TRANSIENT_ERRORS):
            logger.warning(f"回流批次遇基础设施故障，整批暂存重放: n={len(batch)}")
            await self._park_messages(ITEM_REDO_QUEUE, batch)
            return
        logger.warning(f"回流批次数据异常，转逐条隔离落库: n={len(batch)} error={type(error).__name__}")
        for msg in batch:
            try:
                await self._flush_batch([msg], {})
            except _TRANSIENT_ERRORS:
                await self._park_messages(ITEM_REDO_QUEUE, [msg])
            except Exception as e:  # noqa: BLE001 单条失败只影响自身
                await self._redo_or_dead(msg, e)

    async def _redo_or_dead(self, msg: dict, error: Exception) -> None:
        """单条失败：累加重放次数；达到上限进死信（带原因），否则回 REDO"""
        attempts = int(msg.get(_REDO_ATTEMPTS_KEY) or 0) + 1
        retry = dict(msg)
        retry[_REDO_ATTEMPTS_KEY] = attempts
        if attempts >= _MAX_REDO_ATTEMPTS:
            retry["_reject_reason"] = f"回流落库连续失败 {attempts} 次: {type(error).__name__}: {str(error)[:200]}"
            logger.error(
                f"回流消息进死信: task_id={msg.get('task_id')} attempts={attempts} error={error}"
            )
            await self._park_messages(DEAD_ITEM_QUEUE, [retry])
            return
        logger.warning(f"回流消息回 REDO: task_id={msg.get('task_id')} attempts={attempts}")
        await self._park_messages(ITEM_REDO_QUEUE, [retry])
