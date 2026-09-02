"""爬虫任务编排服务 - 任务入队/终态推进/控制/删除

职责：
- enqueue：数据库登记 + 投递 Redis 优先级队列（数据闭环入口）
- finish_task：Webhook 回调落地，幂等终态推进（含自动重试/告警/通知）
- control_task：暂停/恢复/终止运行中的任务（Redis 控制键通信）
- delete_task：删除任务及级联结果（running 拒绝）
- list_tasks / get_task：任务查询

设计说明（期 4 Facade 退役后独立化）：
- 自持 session / repo / result_repo / notifier；模块级直引 settings /
  get_async_redis / Repository（测试 patch 目标：backend.services.spider_task_service.<name>）。
- Redis 统一走异步门面 get_async_redis（期 3 收口：同步 redis_client 直调阻塞事件循环）。
- 期 3 主路径减负：finish_task 副作用（CSV 落盘/通知/告警）后台化
  （_spawn_side_effect + _SIDE_EFFECT_TASKS 强引用集），文件 IO 下线程池。
- 期 4：告警评估自开独立短事务 session（对齐 ai_planner 后台协程范式，
  请求 session 随响应关闭，后台协程复用必炸）。
"""
import asyncio
import json
import time
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.spider_definition_repository import SpiderDefinitionRepository
from backend.repositories.spider_result_repository import SpiderResultRepository
from backend.repositories.spider_task_repository import SpiderTaskRepository
from backend.services.notify_service import NotifyService
from backend.services.spider_common import (
    FLOW_SPIDER_NAME,
    _PROJECT_ROOT,
    _STORE_TARGET_ENUM,
    extract_flow,
    extract_store_targets,
)
from config import settings
from platform_core.db import get_manager
from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.queues import ACTIVE_TASK_KEY, TASK_CONTROL_KEY, task_queue
from platform_core.redis_async import get_async_redis
from platform_core.schemas.spider import (
    SpiderTaskListResponse,
    SpiderTaskResponse,
)

logger = get_logger("api")

# ----------------------------------------------------------------------
# 失败重试延迟队列（ZSET）：score = 到期时间戳，consumer._scan_retry_zset
# 每 tick 扫描到期成员原子抢占后重新投递主优先级队列。
# 键常量归置于本模块（重试逻辑归属；platform_core.queues 为禁改共享文件）。
# ----------------------------------------------------------------------
RETRY_ZSET_KEY = "spider:retry_zset"
_RETRY_DELAYS = (1, 5, 15)  # 第 n 次重试退避秒数（超出档位数取最后一档封顶）


def retry_delay(retry_count: int) -> int:
    logger.debug(f"计算重试退避: retry_count={retry_count}")
    # 退避档位：1 次→1s，2 次→5s，≥3 次→15s（封顶）
    idx = min(max(retry_count, 1), len(_RETRY_DELAYS)) - 1
    return _RETRY_DELAYS[idx]


# ----------------------------------------------------------------------
# 终态副作用后台任务（期 3 webhook 主路径减负）：
# 强引用集防 asyncio.Task 被 GC，完成后自动清理（对齐 ai_planner._spawn 范式）
# ----------------------------------------------------------------------
_SIDE_EFFECT_TASKS: set = set()


def _side_effect_done(task: "asyncio.Task") -> None:
    """副作用任务完成回调：移出强引用集；异常记录日志（不静默）"""
    _SIDE_EFFECT_TASKS.discard(task)
    if task.cancelled():
        logger.info("终态副作用后台任务已取消")
        return
    exc = task.exception()
    if exc is not None:
        logger.error(f"终态副作用后台任务异常: {exc}")


def _spawn_side_effect(coro) -> "asyncio.Task":
    """创建终态副作用后台任务并持有强引用（防 GC），完成后自动清理"""
    task = asyncio.create_task(coro)
    _SIDE_EFFECT_TASKS.add(task)
    task.add_done_callback(_side_effect_done)
    return task


class SpiderTaskService:
    """任务编排：入队 / 终态 / 控制 / 删除 / 列表"""

    def __init__(self, session: AsyncSession):
        """独立 Service：自持会话与仓储（期 4 Facade 退役）"""
        self.session = session
        self.repo = SpiderTaskRepository(session)
        self.result_repo = SpiderResultRepository(session)
        self.notifier = NotifyService()

    async def list_tasks(
        self,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        spider_name: Optional[str] = None,
    ) -> SpiderTaskListResponse:
        """分页列表（Service 层负责把 ORM 实体转成响应契约）"""
        items = await self.repo.list_tasks(
            skip=skip, limit=limit, status=status, priority=priority, spider_name=spider_name
        )
        total = await self.repo.count(status=status, priority=priority, spider_name=spider_name)
        return SpiderTaskListResponse(
            total=total,
            items=[SpiderTaskResponse.model_validate(t) for t in items],
        )

    def _max_concurrent(self) -> int:
        """同爬虫并发任务上限（配置即代码，至少 1）"""
        return max(1, int(settings.get("SPIDER_MAX_CONCURRENT_PER_SPIDER", 2)))

    async def _ensure_spider_available(self, spider_name: str) -> None:
        """入队前注册表校验：DB 优先（存在且 enabled），无记录回退 yml 种子

        - DB 有记录且停用 → 拒绝（停用爬虫不允许再入队）
        - DB 无记录 → yml settings.SPIDERS 兜底（存量 yml-only 爬虫不破坏）
        - DB 与 yml 均无 → 拒绝（未登记的爬虫不允许入队）
        - DB 查询异常 → 仅记日志并跳过校验（DB 故障不阻断入队主流程）
        """
        definition = None
        try:
            definition = await SpiderDefinitionRepository(self.session).get_by_name(spider_name)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"注册表 DB 校验失败，跳过: spider={spider_name}, error={e}")
            return
        if definition is not None:
            if not definition.enabled:
                raise BusinessException(f"爬虫 {spider_name} 已停用，无法提交任务")
            return
        spiders_cfg = settings.get("SPIDERS", {}) or {}
        if isinstance(spiders_cfg, dict):
            if spider_name in spiders_cfg:
                logger.debug(f"爬虫 {spider_name} 走 yml 种子兜底放行")
                return
            raise BusinessException(f"爬虫 {spider_name} 未在注册表登记，请先登记后再提交任务")
        logger.warning(f"配置种子不可读，跳过注册表校验: spider={spider_name}")

    async def enqueue(
        self,
        spider_name: str,
        params: Optional[str] = None,
        priority: str = "normal",
        tenant_id: int | None = None,
    ) -> SpiderTaskResponse:
        """入队一个新任务：数据库登记 + 投递 Redis 优先级队列（数据闭环入口）"""
        logger.info(f"爬虫任务入队: spider={spider_name}, priority={priority}")

        # 阶段 5.1：含流程段（分页/详情/过滤）的任务统一归入 flow_generic 执行
        if extract_flow(params) is not None:
            spider_name = FLOW_SPIDER_NAME

        # 阶段 6：注册表校验（DB 优先，yml 兜底；停用/未登记拒绝）
        await self._ensure_spider_available(spider_name)

        # 租户配额·任务并发（S1 接线；平台/无租户跳过）
        if tenant_id is not None:
            from backend.services.quota_service import QuotaService

            await QuotaService(self.session).check_task_concurrency(tenant_id)

        # 并发槽位守卫
        active_key = ACTIVE_TASK_KEY.format(spider_name=spider_name)
        max_concurrent = self._max_concurrent()
        try:
            active_count = await get_async_redis().scard(active_key)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"并发槽位检查失败（放行）: spider={spider_name}, error={e}")
            active_count = 0
        if active_count >= max_concurrent:
            logger.warning(
                f"同爬虫并发任务已达上限，拒绝入队: spider={spider_name}, "
                f"active={active_count}, max={max_concurrent}"
            )
            raise BusinessException(
                f"爬虫 {spider_name} 已有 {active_count} 个进行中的任务（上限 {max_concurrent}），请稍后再提交"
            )
        task = await self.repo.create(
            spider_name=spider_name,
            status="pending",
            params=params,
            priority=priority,
            tenant_id=tenant_id,
        )
        await self.session.commit()
        await self.session.refresh(task)

        # 投递任务消息到对应优先级队列
        message = json.dumps(
            {"task_id": task.id, "spider_name": spider_name, "params": params,
             "tenant_id": tenant_id},
            ensure_ascii=False,
        )
        try:
            await get_async_redis().rpush(task_queue(priority), message)
        except Exception as e:  # noqa: BLE001
            logger.error(f"任务投递 Redis 失败: task_id={task.id}, error={e}")
            await self.repo.update(
                task.id, status="failed", error_message=f"任务投递失败: {e}"
            )
            await self.session.commit()
            raise BusinessException("任务投递失败，请检查 Redis 连接")

        logger.info(f"爬虫任务已投递: spider={spider_name}, task_id={task.id}")
        return SpiderTaskResponse.model_validate(task)

    async def update_task(
        self,
        task_id: int,
        params: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> SpiderTaskResponse:
        """编辑待执行任务（仅 pending/queued 可改：参数/优先级）

        已在 Redis 队列排队的任务变更（参数或优先级）时，用 LREM 从旧优先级
        队列移除旧消息、rpush 到目标队列（消息字段/格式与 enqueue 完全一致）：
        - 仅改参数：同队列 LREM 旧消息后 rpush 新消息回同队列（消息 params 同步更新）
        - 改优先级：跨队列搬迁；from == to 时等效原地替换消息
        - LREM 未命中：先按 task_id 在重试 ZSET 中定位（失败重试等待期，消息
          携带 priority 字段与主队列消息格式不同、LREM 恒未命中），命中则
          ZREM + ZADD 新消息（新 priority/params，到期 score 不变）；
          ZSET 也未命中（消息已被消费/从未投递）才不动队列，避免重复消费
        - rpush 失败时旧消息已被 LREM 移除，先 lpush 回原队列补偿；补偿也失败则
          任务置 failed（对齐 enqueue 投递失败兜底语义），避免消息永久丢失
        """
        logger.info(f"编辑任务: task_id={task_id}, params={params is not None}, priority={priority}")
        task = await self.repo.get_by_id(task_id)
        if task is None:
            raise NotFoundException("爬虫任务")
        if task.status not in ("pending", "queued"):
            raise BusinessException(
                f"任务当前状态为 {task.status}，仅待执行（pending/queued）任务可编辑"
            )

        update_kwargs: dict = {}
        old_priority = task.priority or "normal"
        new_params = params if params is not None else task.params
        if priority is not None and priority != old_priority:
            update_kwargs["priority"] = priority
        if params is not None:
            update_kwargs["params"] = params

        if not update_kwargs:
            logger.info(f"任务无字段变更: task_id={task_id}")
            return SpiderTaskResponse.model_validate(task)

        # B1：repo.update 前固化旧消息快照（字段/格式与 enqueue 投递、consumer 消费的
        # 消息完全一致）。update + commit + refresh 后 ORM 实体 params 已是新值，
        # 届时再用其构造 old_message 会与 Redis 中旧消息永不匹配 → LREM 恒未命中。
        old_message = json.dumps(
            {"task_id": task.id, "spider_name": task.spider_name, "params": task.params},
            ensure_ascii=False,
        )
        new_message = json.dumps(
            {"task_id": task.id, "spider_name": task.spider_name, "params": new_params},
            ensure_ascii=False,
        )
        target_priority = update_kwargs.get("priority", old_priority)

        updated = await self.repo.update(task_id, **update_kwargs)
        await self.session.commit()
        await self.session.refresh(updated)

        # 队列搬迁：update_kwargs 非空即搬迁（同队列时 from == to，LREM 后 rpush 回同队列）
        await self._relocate_queue_message(
            task_id=task_id,
            old_priority=old_priority,
            target_priority=target_priority,
            old_message=old_message,
            new_message=new_message,
        )

        logger.info(f"任务编辑完成: task_id={task_id}, fields={list(update_kwargs.keys())}")
        return SpiderTaskResponse.model_validate(updated)

    async def _relocate_queue_message(
        self,
        task_id: int,
        old_priority: str,
        target_priority: str,
        old_message: str,
        new_message: str,
    ) -> None:
        """队列消息搬迁：LREM 旧消息 → rpush 新消息（M1 失败路径兜底）

        - LREM 失败（Redis 连接异常等）：旧消息仍留在原队列，无需补偿
        - LREM 未命中：消息已被消费/从未投递，不动队列避免重复投递
        - rpush 失败：旧消息已被移除，先 lpush 回原队列补偿；补偿也失败则任务置 failed
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
            # LREM 未命中：消息可能正处失败重试等待期（在 spider:retry_zset 中，
            # 其消息格式带 priority 字段与主队列消息不同，LREM 恒未命中）。
            # m-1 评审修复：按 task_id 在重试 ZSET 中定位并搬迁，否则编辑结果
            # 不会生效（到期重投仍是旧 params/旧优先级）。
            if await self._relocate_retry_zset_member(
                task_id, target_priority=target_priority, new_message=new_message
            ):
                logger.info(f"任务消息已从重试 ZSET 搬迁: task_id={task_id}")
                return
            logger.warning(
                f"旧优先级队列未命中任务消息（可能已被消费/从未投递），不动队列: task_id={task_id}"
            )
            return
        try:
            await get_async_redis().rpush(to_queue, new_message)
        except Exception as e:  # noqa: BLE001
            # M1：LREM 已移除旧消息而 rpush 失败，先 lpush 回原队列补偿防消息丢失
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
            return
        logger.info(f"任务消息已搬迁: task_id={task_id}, {from_queue} -> {to_queue}")

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
            cursor = 0
            matched: Optional[tuple[str, float]] = None
            while True:
                cursor, members = await redis.zscan(RETRY_ZSET_KEY, cursor=cursor, count=50)
                for raw, score in members:
                    try:
                        payload = json.loads(raw)
                    except (TypeError, ValueError):
                        continue
                    if payload.get("task_id") == task_id:
                        matched = (raw, score)
                        break
                if matched is not None or cursor == 0:
                    break
            if matched is None:
                return False
            raw, score = matched
            removed = await redis.zrem(RETRY_ZSET_KEY, raw)
            if not removed:
                logger.warning(
                    f"重试 ZSET 成员已被 consumer 抢占，按未命中处理: task_id={task_id}"
                )
                return False
            new_payload = json.loads(new_message)
            new_payload["priority"] = target_priority
            await redis.zadd(
                RETRY_ZSET_KEY,
                {json.dumps(new_payload, ensure_ascii=False): score},
            )
            return True
        except Exception as e:  # noqa: BLE001 搬迁失败不影响编辑主流程（DB 已更新）
            logger.warning(
                f"重试 ZSET 消息搬迁失败（不影响编辑主流程）: task_id={task_id}, error={e}"
            )
            return False

    async def finish_task(
        self,
        task_id: int,
        status: str,
        error_message: Optional[str] = None,
        item_count: Optional[int] = None,
    ) -> SpiderTaskResponse:
        """Webhook 回调落地：任务终态推进（completed/failed，幂等）

        期 3 主路径减负：终态落库 + 活跃键清理后立即返回；
        CSV 落盘 / 终态通知 / 告警评估转交后台任务执行（_spawn_side_effect）。
        """
        logger.info(f"任务终态推进: task_id={task_id}, status={status}")
        task = await self.repo.get_by_id(task_id)
        if task is None:
            raise NotFoundException("爬虫任务")
        if task.status in ("completed", "failed"):
            return SpiderTaskResponse.model_validate(task)

        # 失败自动重试（ZSET 延迟入队：退避 1s→5s→15s，consumer 扫描到期成员重投主队列）
        max_retries = int(settings.get("SPIDER_MAX_RETRIES", 2))
        if status == "failed" and (task.retry_count or 0) < max_retries:
            next_retry = (task.retry_count or 0) + 1
            task = await self.repo.update(
                task_id,
                status="pending",
                retry_count=next_retry,
                completed_at=None,
                error_message=error_message,
            )
            await self.session.commit()
            await self.session.refresh(task)
            try:
                await get_async_redis().srem(
                    ACTIVE_TASK_KEY.format(spider_name=task.spider_name), task_id
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"重试前清理活跃键失败: task_id={task_id}, error={e}")
            delay = await self._reenqueue(task)
            logger.warning(
                f"任务失败自动重试（延迟 {delay}s 入队）: task_id={task_id}, "
                f"spider={task.spider_name}, 第 {next_retry}/{max_retries} 次"
            )
            return SpiderTaskResponse.model_validate(task)

        update_kwargs = dict(
            status=status,
            error_message=error_message,
            completed_at=func.now(),
        )
        if item_count is not None:
            update_kwargs["result_count"] = item_count
        task = await self.repo.update(task_id, **update_kwargs)
        await self.session.commit()
        await self.session.refresh(task)

        # 从活跃任务集合移除
        try:
            await get_async_redis().srem(
                ACTIVE_TASK_KEY.format(spider_name=task.spider_name), task_id
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"清理活跃任务关联失败: task_id={task_id}, error={e}")

        # 期 3 webhook 主路径减负：CSV 落盘 / 终态通知 / 告警评估三大副作用
        # 移入后台任务（_spawn_side_effect 强引用防 GC），主路径在终态落库 +
        # 槽位释放后立即返回，不再被大结果落盘 / 通知 HTTP / 告警评估阻塞。
        # 幂等：方法入口已有终态守卫（completed/failed 直接返回），同一任务
        # 重复回调不会再走到此处 → 副作用仅随本次终态推进 spawn 一次；
        # 后台任务内不再重复查终态，仅消费下方标量快照（脱离 ORM，
        # 无二次 DB 读，也规避后台执行期 ORM 惰性加载触碰已关闭的 session）。
        snapshot = {
            "id": task.id,
            "spider_name": task.spider_name,
            "status": task.status,
            "result_count": task.result_count or 0,
            "retry_count": task.retry_count or 0,
            "error_message": task.error_message,
            "params": task.params,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
        }
        _spawn_side_effect(self._run_finish_side_effects(snapshot))

        return SpiderTaskResponse.model_validate(task)

    async def _run_finish_side_effects(self, snapshot: dict) -> None:
        """终态副作用后台协程（由 _spawn_side_effect 启动，不阻塞 webhook 主路径）

        入参为 finish_task 提取的任务标量快照；_flush_store 经 SimpleNamespace
        按原 task 鸭子类型访问。三个副作用按原有顺序执行：
        - CSV 落盘 / 告警评估：沿用原有吞异常语义，失败仅记日志
        - 终态通知：notify_service 渠道级自吞异常，保持裸 await
        - 整体兜底：协程自身异常由 _side_effect_done 记录日志（不静默）
        - CancelledError 不吞（BaseException 不进 except Exception），取消原样上抛
        """
        task_id = snapshot["id"]

        # 数据源多存储（4.2）：终态后 CSV 落盘
        try:
            await self._flush_store(SimpleNamespace(**snapshot))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"csv 落盘失败（不影响任务终态）: task_id={task_id}, error={e}")

        # 终态通知
        await self.notifier.notify_task_finished(
            task_id=task_id,
            spider_name=snapshot["spider_name"],
            status=snapshot["status"],
            result_count=snapshot["result_count"],
            retry_count=snapshot["retry_count"],
            error_message=snapshot["error_message"],
        )

        # 告警规则评估：自开独立短事务 session（期 4 收口，Oscar 登记）
        # 本协程由 _spawn_side_effect 后台执行，生命周期长于 webhook 请求；
        # finish_task 的请求 session 在响应返回后已关闭，复用会触发「session
        # 已关闭」异常（原被自吞）。对齐 ai_planner 后台协程范式（_run_plan_bg /
        # state._read_task_snapshot）：经 get_manager() 新建独立 AsyncSession，
        # 用完即关；评估失败仍吞异常仅记日志。
        try:
            from backend.services.alert_service import AlertService
            manager = get_manager()
            async with AsyncSession(manager.async_engines["DEFAULT"]) as alert_session:
                alert_svc = AlertService(alert_session)
                duration = 0
                started_at = snapshot["started_at"]
                completed_at = snapshot["completed_at"]
                if started_at and completed_at:
                    duration = (completed_at - started_at).total_seconds()
                await alert_svc.evaluate({
                    "task_id": task_id,
                    "spider_name": snapshot["spider_name"],
                    "status": snapshot["status"],
                    "result_count": snapshot["result_count"],
                    "duration_seconds": duration,
                })
        except Exception as e:  # noqa: BLE001
            logger.warning(f"告警评估失败（不影响主流程）: {e}")

    async def _reenqueue(self, task) -> int:
        """重试专用延迟入队：ZSET score=到期时间戳（退避 1s→5s→15s），绕过并发槽位检查

        consumer._scan_retry_zset 每 tick 扫描到期成员，原子抢占后重新投递
        对应优先级主队列（消息携带 priority 字段供扫描侧选队）。
        返回本次退避延迟秒数（供调用方日志）。
        """
        delay = retry_delay(task.retry_count or 1)
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
            await get_async_redis().zadd(
                RETRY_ZSET_KEY, {message: time.time() + delay}
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"重试投递 Redis 失败: task_id={task.id}, error={e}")
            await self.repo.update(
                task.id, status="failed", error_message=f"重试投递失败: {e}"
            )
            await self.session.commit()
        return delay

    async def delete_task(self, task_id: int) -> dict:
        """删除任务及其采集结果（级联）"""
        task = await self.repo.get_by_id(task_id)
        if task is None:
            raise NotFoundException("爬虫任务")
        if task.status == "running":
            raise BusinessException("任务正在运行，无法删除；请等待任务结束后再操作")

        spider_name = task.spider_name
        removed_results = await self.result_repo.delete_by_task(task_id)
        await self.repo.delete(task_id)
        await self.session.commit()

        try:
            await get_async_redis().srem(ACTIVE_TASK_KEY.format(spider_name=spider_name), task_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"删除任务后清理活跃键失败: task_id={task_id}, error={e}")

        logger.info(
            f"任务已删除: task_id={task_id}, spider={spider_name}, 级联结果数={removed_results}"
        )
        return {"task_id": task_id, "removed_results": removed_results}

    # ------------------------------------------------------------------
    # 任务控制（A4）：暂停/恢复/终止运行中的任务
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 数据源多存储（4.2）：终态 CSV 落盘
    # ------------------------------------------------------------------
    _EXPORT_COLUMNS = (
        "id", "task_id", "spider_name", "url", "title", "content",
        "source", "item_type", "extra", "created_at",
    )

    async def _flush_store(self, task) -> None:
        """终态落盘：把任务结果缓存列表写成 CSV（仅 csv 目标生效）

        期 3 主路径减负：Redis 结果缓存读取保持事件循环内异步，目录创建 +
        文件写入（裸 open + writerows）整体下沉 asyncio.to_thread 线程池，
        大结果任务的同步文件写不再阻塞事件循环；写入路径/格式/覆盖写语义
        与旧实现逐字节一致（现状无临时文件+rename 惯例，维持直接覆盖写）。
        """
        logger.info(f"检查任务存储落盘: task_id={task.id}")
        if "csv" not in self._store_targets(task):
            return
        from platform_core.queues import TASK_RESULTS_KEY
        key = TASK_RESULTS_KEY.format(task_id=task.id)
        raw_entries = await get_async_redis().lrange(key, 0, -1)
        rows = []
        for raw in raw_entries:
            try:
                msg = json.loads(raw)
            except (TypeError, ValueError):
                continue
            item = msg.get("item") or {}
            mapped = {"url", "title", "content", "source"}
            extra = {k: v for k, v in item.items() if k not in mapped}
            rows.append(
                {
                    "id": None,
                    "task_id": task.id,
                    "spider_name": task.spider_name,
                    "url": item.get("url"),
                    "title": item.get("title"),
                    "content": item.get("content"),
                    "source": item.get("source"),
                    "item_type": msg.get("item_type"),
                    "extra": json.dumps(extra, ensure_ascii=False, default=str) if extra else None,
                    "created_at": msg.get("fetched_at"),
                }
            )
        out_dir = self._store_dir()
        path = await asyncio.to_thread(self._write_csv_sync, out_dir, task.id, rows)
        logger.info(f"csv 已落盘: task_id={task.id}, path={path}, rows={len(rows)}")

    @staticmethod
    def _write_csv_sync(out_dir: str, task_id: int, rows: list) -> str:
        """同步 CSV 写（仅在 asyncio.to_thread 线程池中执行）

        目录创建 + 打开写入为原 _flush_store 内联逻辑原样搬移
        （utf-8-sig BOM、_EXPORT_COLUMNS 列序、直接覆盖写），返回落盘路径供日志。
        """
        import csv
        import os
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"task_{task_id}.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=SpiderTaskService._EXPORT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def _store_dir(self) -> str:
        """csv 落盘目录（配置即代码）"""
        import os
        rel = settings.get("STORAGE.DIR", "storage/exports") or "storage/exports"
        return rel if os.path.isabs(rel) else os.path.abspath(os.path.join(_PROJECT_ROOT, rel))

    def _store_targets(self, task) -> list[str]:
        """生效的额外存储目标"""
        targets = extract_store_targets(getattr(task, "params", None))
        if not targets:
            default = settings.get("STORAGE.EXTRA_TARGETS", []) or []
            if isinstance(default, str):
                default = [default]
            targets = [t for t in default if t in _STORE_TARGET_ENUM]
        return targets

