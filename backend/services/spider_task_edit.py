"""爬虫任务编辑 - 待执行任务改参数 / 改优先级 + Redis 队列消息搬迁

自 spider_task_service 拆出（规模约定），SpiderTaskService 经 SpiderTaskEditMixin
组合 update_task（公开签名、返回值与异常不变）。依赖宿主的 session / repo。

测试 patch 目标：本模块 Redis 调用经 backend.services.spider_task_edit.get_async_redis。
"""
from typing import Optional

from backend.services.spider_task_queue import (
    _find_retry_member,
    _swap_retry_member,
    queue_message,
)
from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.queues import task_queue
from platform_core.redis_async import get_async_redis
from platform_core.schemas.spider import SpiderTaskResponse

logger = get_logger("api")


def _edit_changes(old_priority: str, params: Optional[str], priority: Optional[str]) -> dict:
    """待落库字段：优先级有变化才改；显式给出 params 即改"""
    update_kwargs: dict = {}
    if priority is not None and priority != old_priority:
        update_kwargs["priority"] = priority
    if params is not None:
        update_kwargs["params"] = params
    return update_kwargs


class SpiderTaskEditMixin:
    """SpiderTaskService 的任务编辑部分（update_task + 队列搬迁）"""

    async def update_task(
        self,
        task_id: int,
        params: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> SpiderTaskResponse:
        """编辑待执行任务（仅 pending/queued 可改：参数/优先级）

        有字段变更即搬迁已排队的消息（消息字段/格式与 enqueue 完全一致），
        搬迁规则与失败兜底见 _relocate_queue_message。
        """
        logger.info(f"编辑任务: task_id={task_id}, params={params is not None}, priority={priority}")
        task = await self._editable_task(task_id)
        old_priority = task.priority or "normal"
        new_params = params if params is not None else task.params
        update_kwargs = _edit_changes(old_priority, params, priority)
        if not update_kwargs:
            logger.info(f"任务无字段变更: task_id={task_id}")
            return SpiderTaskResponse.model_validate(task)

        target_priority = update_kwargs.get("priority", old_priority)
        # repo.update 前固化旧消息快照——与 enqueue 投递同一个构造函数（审计 BUG-13：原先这里
        # 多带 tenant_id / priority，与投递字节不一致，LREM 永远命不中，改优先级从未生效）。
        # 参数改动不依赖搬迁：分发时以数据库行为准（consumer._dispatch）。
        old_message = queue_message(task.id, task.spider_name, task.params)
        new_message = queue_message(task.id, task.spider_name, new_params)

        updated = await self.repo.update(task_id, **update_kwargs)
        await self.session.commit()
        await self.session.refresh(updated)

        # 队列搬迁：update_kwargs 非空即搬迁（同队列时 from == to，LREM 后 rpush 回同队列）
        await self._relocate_queue_message(
            task_id=task_id, old_priority=old_priority, target_priority=target_priority,
            old_message=old_message, new_message=new_message,
        )
        logger.info(f"任务编辑完成: task_id={task_id}, fields={list(update_kwargs.keys())}")
        return SpiderTaskResponse.model_validate(updated)

    async def _editable_task(self, task_id: int):
        """取待编辑任务：不存在抛 NotFound；仅 pending/queued 可编辑"""
        task = await self.repo.get_by_id(task_id)
        if task is None:
            raise NotFoundException("爬虫任务")
        if task.status not in ("pending", "queued"):
            raise BusinessException(
                f"任务当前状态为 {task.status}，仅待执行（pending/queued）任务可编辑"
            )
        return task

    async def _relocate_queue_message(
        self,
        task_id: int,
        old_priority: str,
        target_priority: str,
        old_message: str,
        new_message: str,
    ) -> None:
        """队列消息搬迁：LREM 旧消息 → rpush 新消息（M1 失败路径兜底）

        - 仅改参数：同队列 LREM 旧消息后 rpush 新消息回同队列（消息 params 同步更新）
        - 改优先级：跨队列搬迁；from == to 时等效原地替换消息
        - LREM 失败（Redis 连接异常等）：旧消息仍留在原队列，无需补偿
        - LREM 未命中：转查重试 ZSET（_relocate_on_lrem_miss）；也未命中则不动队列，避免重复消费
        - rpush 失败：旧消息已被移除，先 lpush 回原队列补偿；补偿也失败则任务置 failed
          （对齐 enqueue 投递失败兜底语义），避免消息永久丢失
        """
        from_queue = task_queue(old_priority)
        to_queue = task_queue(target_priority)
        try:
            removed = await get_async_redis().lrem(from_queue, 1, old_message)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"队列 LREM 失败（旧消息保留在原队列）: task_id={task_id}, error={e}"
            )
            return
        if not removed:
            await self._relocate_on_lrem_miss(task_id, target_priority, new_message)
            return
        try:
            await get_async_redis().rpush(to_queue, new_message)
        except Exception as e:  # noqa: BLE001
            await self._compensate_failed_push(task_id, from_queue, old_message, e)
            return
        logger.info(f"任务消息已搬迁: task_id={task_id}, {from_queue} -> {to_queue}")

    async def _relocate_on_lrem_miss(
        self, task_id: int, target_priority: str, new_message: str,
    ) -> None:
        """LREM 未命中兜底：转查重试 ZSET，也未命中才不动队列

        消息可能正处失败重试等待期（在 spider:retry_zset 中，其消息格式带
        priority 字段与主队列消息不同，LREM 恒未命中）。m-1 评审修复：按
        task_id 在重试 ZSET 中定位并搬迁，否则编辑结果不会生效（到期重投仍是
        旧 params/旧优先级）。
        """
        if await self._relocate_retry_zset_member(
            task_id, target_priority=target_priority, new_message=new_message
        ):
            logger.info(f"任务消息已从重试 ZSET 搬迁: task_id={task_id}")
            return
        logger.warning(
            f"旧优先级队列未命中任务消息（可能已被消费/从未投递），不动队列: task_id={task_id}"
        )

    async def _compensate_failed_push(
        self, task_id: int, from_queue: str, old_message: str, e: Exception,
    ) -> None:
        """M1：LREM 已移除旧消息而 rpush 失败，先 lpush 回原队列补偿防消息丢失

        补偿也失败则任务置 failed 并抛 BusinessException（在调用方 except 块内执行，异常链不变）。
        """
        try:
            await get_async_redis().lpush(from_queue, old_message)
            logger.error(
                f"新队列投递失败，旧消息已补偿回原队列: task_id={task_id}, "
                f"queue={from_queue}, error={e}"
            )
        except Exception as comp_err:  # noqa: BLE001
            logger.error(f"补偿回队列失败，任务置 failed: task_id={task_id}, error={comp_err}")
            await self.repo.update(
                task_id,
                status="failed",
                error_message=f"队列搬迁投递失败: {e}; 补偿回队列失败: {comp_err}",
            )
            await self.session.commit()
            raise BusinessException("任务队列搬迁失败，请检查 Redis 连接")

    async def _relocate_retry_zset_member(
        self,
        task_id: int,
        target_priority: str,
        new_message: str,
    ) -> bool:
        """重试等待期消息搬迁：按 task_id 在 spider:retry_zset 中定位成员

        LREM 未命中时的兜底：失败重试的消息由 _reenqueue 以 JSON 存于重试
        ZSET（score=到期时间戳，消息含 priority 字段，与主队列消息格式不同）。
        ZSCAN 全量游标按 task_id 定位 → ZREM 原子抢占 → ZADD 新消息
        （新 priority/params，score 保持原到期时刻，不影响重试退避节奏）。

        返回 True=已在重试 ZSET 中完成搬迁；False=无重试成员或 ZREM 被
        consumer 抢占（其将把旧消息重投主队列，按未命中处理不重复操作）。
        Redis 异常吞掉仅记日志（搬迁是编辑操作的附属兜底，不阻断主流程）。
        """
        try:
            redis = get_async_redis()
            matched = await _find_retry_member(redis, task_id)
            if matched is None:
                return False
            return await _swap_retry_member(redis, task_id, matched, target_priority, new_message)
        except Exception as e:  # noqa: BLE001 搬迁失败不影响编辑主流程（DB 已更新）
            logger.warning(
                f"重试 ZSET 消息搬迁失败（不影响编辑主流程）: task_id={task_id}, error={e}"
            )
            return False
