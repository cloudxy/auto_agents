"""爬虫任务控制（A4）- 终止（只终止本任务）/ 恢复；暂停先下线（决策 D6）

自 spider_task_service 拆出（规模约定），SpiderTaskService 经 SpiderTaskControlMixin
组合 control_task（公开签名、返回值与异常不变）。依赖宿主的 session / repo /
_record_log_end。

测试 patch 目标：本模块 Redis 调用经 backend.services.spider_task_control.get_async_redis。
"""
from sqlalchemy import func

from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.queues import ACTIVE_TASK_KEY, TASK_CONTROL_KEY, tenant_active_key
from platform_core.redis_async import get_async_redis

logger = get_logger("api")


class SpiderTaskControlMixin:
    """SpiderTaskService 的任务控制部分：暂停/恢复/终止运行中的任务"""

    _VALID_ACTIONS = ("pause", "resume", "stop")
    _CONTROL_TTL = 3600

    async def control_task(self, task_id: int, action: str) -> dict:
        """控制运行中的任务：pause/resume/stop"""
        logger.info(f"任务控制: task_id={task_id}, action={action}")
        if action not in self._VALID_ACTIONS:
            raise BusinessException(f"无效的控制动作: {action}，仅允许 {', '.join(self._VALID_ACTIONS)}")

        task = await self.repo.get_by_id(task_id)
        if task is None:
            raise NotFoundException("爬虫任务")
        if action == "stop":
            return await self._cancel_task(task)
        if action == "pause":
            # 决策 D6：现有暂停只丢弃后续请求，空闲 30 秒后任务被判完成、请求丢失（BUG-14）；
            # 真挂起有客户需要再做，先下线。resume 保留，清掉旧版本留下的暂停键
            raise BusinessException(
                message="暂停功能暂未开放；如需停下，请终止任务后「再次运行」。",
                code="TASK_PAUSE_UNAVAILABLE", status_code=409,
            )
        if task.status != "running":
            raise BusinessException(f"任务当前状态为 {task.status}，仅运行中的任务可控制")

        control_key = TASK_CONTROL_KEY.format(task_id=task_id)
        try:
            if action == "resume":
                await get_async_redis().delete(control_key)
                logger.info(f"任务恢复: task_id={task_id}")
                return {"task_id": task_id, "action": "resume", "message": "任务已恢复"}
            else:
                await get_async_redis().set(control_key, action, ex=self._CONTROL_TTL)
                logger.info(f"任务控制指令已写入: task_id={task_id}, action={action}")
                return {"task_id": task_id, "action": action, "message": f"任务已{action}"}
        except Exception as e:  # noqa: BLE001
            raise BusinessException(f"控制指令写入 Redis 失败: {e}")

    async def _cancel_task(self, task) -> dict:
        """终止任务（审计 BUG-15）：只终止这一个任务

        原先写 stop 控制键后由 Scrapy 中间件 close_spider——共享爬虫进程整体关闭，
        同实例上其他租户的任务一并被杀。现在：任务按 CAS 直接置终态 cancelled（待执行 /
        运行中均可终止）、释放并发槽；stop 控制键只让 Scrapy 丢弃该任务剩余请求。
        """
        task_id = int(task.id)
        spider_name = str(task.spider_name)
        tid = getattr(task, "tenant_id", None)
        updated = await self.repo.update(
            task_id, only_if_status=("pending", "running"),
            status="cancelled", error_message="用户终止", completed_at=func.now(),
        )
        if updated is None:
            current = await self.repo.get_by_id(task_id)
            status = getattr(current, "status", None)
            raise BusinessException(f"任务当前状态为 {status}，已结束的任务无法终止")
        await self.session.commit()
        try:
            redis = get_async_redis()
            await redis.set(TASK_CONTROL_KEY.format(task_id=task_id), "stop", ex=self._CONTROL_TTL)
            await redis.srem(ACTIVE_TASK_KEY.format(spider_name=spider_name), task_id)
            if isinstance(tid, int):
                await redis.srem(tenant_active_key(tid, spider_name), task_id)
        except Exception as e:  # noqa: BLE001 任务已终止落库；控制键 / 槽位清理失败只记日志
            logger.warning(f"终止后清理控制键 / 槽位失败: task_id={task_id}, error={e}")
        await self._record_log_end(task_id)
        logger.info(f"任务已终止（仅本任务）: task_id={task_id}")
        return {"task_id": task_id, "action": "stop", "message": "任务已终止"}
