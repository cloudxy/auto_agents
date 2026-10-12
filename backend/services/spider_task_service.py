"""爬虫任务编排服务 - 任务入队/终态推进/控制/删除

职责：
- enqueue：数据库登记 + 投递 Redis 优先级队列（数据闭环入口）
- finish_task：Webhook 回调落地，幂等终态推进（含自动重试/告警/通知）
- update_task：编辑待执行任务并搬迁队列消息（SpiderTaskEditMixin，见 spider_task_edit）
- control_task：终止任务；暂停先下线（D6），恢复只清旧暂停键（SpiderTaskControlMixin，见 spider_task_control）
- delete_task：删除任务及级联结果（running 拒绝）
- list_tasks：任务列表（单任务详情 get_task 在 spider_query_service）

设计说明（期 4 Facade 退役后独立化）：
- 自持 session / repo / result_repo / notifier；模块级直引 settings /
  get_async_redis / Repository（测试 patch 目标：backend.services.spider_task_service.<name>；
  update_task / control_task 的 Redis 调用在 spider_task_edit / spider_task_control，
  patch 目标为对应模块）。
- Redis 统一走异步门面 get_async_redis（期 3 收口：同步 redis_client 直调阻塞事件循环）。
- 期 3 主路径减负：finish_task 副作用（CSV 落盘/通知/告警）后台化
  （_spawn_side_effect + _SIDE_EFFECT_TASKS 强引用集），文件 IO 下线程池。
- 期 4：告警评估自开独立短事务 session（对齐 ai_planner 后台协程范式，
  请求 session 随响应关闭，后台协程复用必炸）。
- 规模约定拆分：队列协议 spider_task_queue / 编辑 spider_task_edit / 控制 spider_task_control /
  产品事件 spider_task_events / 终态副作用 spider_task_side_effects；本模块 re-export
  RETRY_ZSET_KEY / retry_delay / queue_message / _SIDE_EFFECT_TASKS / _spawn_side_effect
  （存量 import 与 patch 路径不变）。
"""
import asyncio
import json
import time
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
    require_enqueue_tenant,
    resolve_spider_log_path,
)
from backend.services.spider_task_control import SpiderTaskControlMixin
from backend.services.spider_task_edit import SpiderTaskEditMixin
from backend.services.spider_task_events import SpiderTaskEventsMixin
from backend.services.spider_task_queue import (
    RETRY_ZSET_KEY,
    _release_active_slots,
    _retry_message,
    queue_message,
    retry_delay,
)
from backend.services.spider_task_side_effects import (  # noqa: F401 _SIDE_EFFECT_TASKS 为 re-export
    _SIDE_EFFECT_TASKS,
    SpiderTaskSideEffectsMixin,
    _csv_rows,
    _finish_snapshot,
    _spawn_side_effect,
)
from backend.services.spider_worker_gate import (
    SPIDER_WORKER_OFFLINE_CODE,
    annotate_tasks,
    require_online_worker,
)
from config import settings
from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.queues import ACTIVE_TASK_KEY, task_queue, tenant_active_key
from platform_core.redis_async import get_async_redis
from platform_core.schemas.spider import (
    SpiderTaskListResponse,
    SpiderTaskResponse,
)

logger = get_logger("api")

_QUOTA_BLOCK_REASON = {
    "storage": "quota_storage",
    "concurrency": "quota_concurrency",
    "llm_tokens": "quota_tokens",
}


class SpiderTaskService(
    SpiderTaskEditMixin,
    SpiderTaskControlMixin,
    SpiderTaskEventsMixin,
    SpiderTaskSideEffectsMixin,
):
    """任务编排：入队 / 终态 / 编辑 / 控制 / 删除 / 列表"""

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
        logger.info(f"列出爬虫任务: skip={skip}, limit={limit}")
        items = await self.repo.list_tasks(
            skip=skip, limit=limit, status=status, priority=priority, spider_name=spider_name
        )
        total = await self.repo.count(status=status, priority=priority, spider_name=spider_name)
        annotated = await annotate_tasks(items, get_async_redis())
        return SpiderTaskListResponse(total=total, items=annotated)

    def _max_concurrent(self) -> int:
        """同爬虫并发任务上限（配置即代码，至少 1）"""
        return max(1, int(settings.get("SPIDER_MAX_CONCURRENT_PER_SPIDER", 2)))

    async def _check_enqueue_quota(self, tenant_id: int, spider_name: str = "example") -> None:
        """入队前本租户并发配额（显式 tenant_id，不靠 Mixin 回填）

        FR-U02：执法本体仍抛 QuotaExceededException（内部码 QUOTA_EXCEEDED
        留给验收）；入队信封改写为「已达配额上限」+ 存储「去结果库」/
        并发「申请提升」。HTTP 400，无裸 429。工人句不走本闸。
        """
        logger.debug(f"入队配额检查: tenant_id={tenant_id}")
        from backend.services.quota_service import (
            QuotaExceededException,
            QuotaService,
            wrap_quota_exceeded,
        )

        quota = QuotaService(self.session)
        try:
            await quota.check_task_concurrency(tenant_id)
            await quota.check_result_storage(tenant_id)
        except QuotaExceededException as exc:
            reason = _QUOTA_BLOCK_REASON.get(exc.dimension, "quota_concurrency")
            await self._emit_blocked(tenant_id, reason, spider_name)
            raise wrap_quota_exceeded(exc) from exc

    async def _reject_if_blocked(self, owner_id: int, spider_name: str) -> None:
        """工人闸先于配额；拦住发 task_blocked，不入队、不停在采集中。"""
        logger.info(f"入队拦住闸 | tenant={owner_id} spider={spider_name}")
        try:
            await require_online_worker(get_async_redis())
        except BusinessException as exc:
            if getattr(exc, "code", None) == SPIDER_WORKER_OFFLINE_CODE:
                await self._emit_blocked(owner_id, "worker_offline", spider_name)
            raise
        await self._check_enqueue_quota(owner_id, spider_name)

    async def _ensure_spider_available(self, spider_name: str, tenant_id: Optional[int] = None) -> None:
        """入队前注册表校验：DB 优先（存在且 enabled），无记录回退 yml 种子

        - DB 有记录且停用 → 拒绝（停用爬虫不允许再入队）
        - DB 无记录 → yml settings.SPIDERS 兜底（存量 yml-only 爬虫不破坏）
        - DB 与 yml 均无 → 拒绝（未登记的爬虫不允许入队）
        - DB 查询异常 → 仅记日志并跳过校验（DB 故障不阻断入队主流程）
        """
        definition = None
        try:
            definition = await SpiderDefinitionRepository(self.session).get_by_name(spider_name, tenant_id)
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

    async def _definition_default_params(
        self, spider_name: str, tenant_id: Optional[int] = None,
    ) -> Optional[str]:
        """取定义参数（T-39 / GWT-103.1：方案编辑后，后续未带 params 的任务按新定义执行）

        定义行无 params（None/非 dict/空）返回 None（既有行为不变）；
        DB 故障只记日志不阻断入队（与 _ensure_spider_available 同口径）。
        """
        logger.debug(f"读取定义参数默认值: spider={spider_name}")
        try:
            definition = await SpiderDefinitionRepository(self.session).get_by_name(spider_name, tenant_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"定义参数读取失败（跳过默认填充）: spider={spider_name}, error={e}")
            return None
        if definition is None:
            return None
        stored = definition.params
        if not isinstance(stored, dict) or not stored:
            return None
        return json.dumps(stored, ensure_ascii=False)

    async def enqueue(
        self,
        spider_name: str,
        params: Optional[str] = None,
        priority: str = "normal",
        tenant_id: int | None = None,
    ) -> SpiderTaskResponse:
        """入队一个新任务：数据库登记 + 投递 Redis 优先级队列（数据闭环入口）"""
        logger.info(f"爬虫任务入队: spider={spider_name}, priority={priority}")
        owner_id = require_enqueue_tenant(tenant_id)

        # FR-103 / GWT-103.1：请求未带 params 时取定义参数（显式 params 优先）。
        # 放在流程段识别之前：flow 型定义的镜像参数含 flow 段，需参与 flow_generic 归并。
        if params is None:
            params = await self._definition_default_params(spider_name, owner_id)

        # 阶段 5.1：含流程段（分页/详情/过滤）的任务统一归入 flow_generic 执行
        if extract_flow(params) is not None:
            spider_name = FLOW_SPIDER_NAME

        # 阶段 6：注册表校验（DB 优先，yml 兜底；停用/未登记拒绝）
        await self._ensure_spider_available(spider_name, owner_id)

        await self._reject_if_blocked(owner_id, spider_name)
        await self._require_free_slot(spider_name, tenant_id)
        task = await self.repo.create(
            spider_name=spider_name, status="pending", params=params,
            priority=priority, tenant_id=owner_id,
        )
        await self.session.commit()
        await self.session.refresh(task)
        await self._push_task_message(task, spider_name, params, priority)

        logger.info(f"爬虫任务已投递: spider={spider_name}, task_id={task.id}")
        await self._emit_submitted(task)
        return SpiderTaskResponse.model_validate(task)

    async def _require_free_slot(self, spider_name: str, tenant_id: Optional[int]) -> None:
        """并发槽位：有租户时按 {tenant}:{spider} 计数，两租户互不挤占；已满拒绝入队"""
        max_concurrent = self._max_concurrent()
        if tenant_id is not None:
            slot_key = tenant_active_key(tenant_id, spider_name)
        else:
            slot_key = ACTIVE_TASK_KEY.format(spider_name=spider_name)
        try:
            active_count = await get_async_redis().scard(slot_key)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"并发槽位检查失败（放行）: spider={spider_name}, error={e}")
            active_count = 0
        if active_count >= max_concurrent:
            logger.warning(
                f"同爬虫并发任务已达上限，拒绝入队: spider={spider_name}, "
                f"tenant={tenant_id}, active={active_count}, max={max_concurrent}"
            )
            raise BusinessException(
                f"爬虫 {spider_name} 已有 {active_count} 个进行中的任务（上限 {max_concurrent}），请稍后再提交"
            )

    async def _push_task_message(
        self, task, spider_name: str, params: Optional[str], priority: str,
    ) -> None:
        """投递任务消息到对应优先级队列（不含 tenant_id：工人不决定归属，LREM 与 update 对齐）

        投递失败：任务置 failed 并抛 BusinessException。
        """
        message = queue_message(task.id, spider_name, params)
        try:
            await get_async_redis().rpush(task_queue(priority), message)
        except Exception as e:  # noqa: BLE001
            logger.error(f"任务投递 Redis 失败: task_id={task.id}, error={e}")
            await self.repo.update(
                task.id, status="failed", error_message=f"任务投递失败: {e}"
            )
            await self.session.commit()
            raise BusinessException("任务投递失败，请检查 Redis 连接")

    async def _record_log_end(self, task_id: int) -> None:
        """终态时记录任务日志窗口终点（审计 BUG-16）；失败只记日志"""
        import os

        from platform_core.queues import TASK_LOG_END_KEY, TASK_LOG_OFFSET_TTL

        try:
            log_path = resolve_spider_log_path()
            size = os.path.getsize(log_path) if log_path and os.path.isfile(log_path) else None
            if size is not None:
                await get_async_redis().set(
                    TASK_LOG_END_KEY.format(task_id=task_id), size, ex=TASK_LOG_OFFSET_TTL,
                )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"记录任务日志终点失败: task_id={task_id}, error={e}")

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
        if task.status in ("completed", "failed", "cancelled"):
            return SpiderTaskResponse.model_validate(task)

        # 失败自动重试（ZSET 延迟入队：退避 1s→5s→15s，consumer 扫描到期成员重投主队列）
        max_retries = int(settings.get("SPIDER_MAX_RETRIES", 2))
        if status == "failed" and (task.retry_count or 0) < max_retries:
            return await self._retry_failed(task, task_id, error_message, max_retries)
        return await self._finalize_task(task_id, status, error_message, item_count)

    async def _retry_failed(
        self, task, task_id: int, error_message: Optional[str], max_retries: int,
    ) -> SpiderTaskResponse:
        """失败且未达重试上限：CAS 回 pending（retry_count+1）→ 释放槽位 → 延迟入重试 ZSET"""
        next_retry = (task.retry_count or 0) + 1
        task = await self.repo.update(
            task_id,
            only_if_status=("pending", "running"),
            status="pending",
            retry_count=next_retry,
            completed_at=None,
            error_message=error_message,
        )
        if task is None:
            return await self._current_response(task_id)
        await self.session.commit()
        await self.session.refresh(task)
        try:
            await _release_active_slots(get_async_redis(), task.spider_name, task_id, task)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"重试前清理活跃键失败: task_id={task_id}, error={e}")
        delay = await self._reenqueue(task)
        logger.warning(
            f"任务失败自动重试（延迟 {delay}s 入队）: task_id={task_id}, "
            f"spider={task.spider_name}, 第 {next_retry}/{max_retries} 次"
        )
        return SpiderTaskResponse.model_validate(task)

    async def _finalize_task(
        self, task_id: int, status: str, error_message: Optional[str], item_count: Optional[int],
    ) -> SpiderTaskResponse:
        """终态推进：CAS 落库 → 释放槽位 → 记日志终点 → 后台副作用

        期 3 webhook 主路径减负：CSV 落盘 / 终态通知 / 告警评估三大副作用
        移入后台任务（_spawn_side_effect 强引用防 GC），主路径在终态落库 +
        槽位释放后立即返回，不再被大结果落盘 / 通知 HTTP / 告警评估阻塞
        （幂等与快照约定见 _finish_snapshot）。
        """
        update_kwargs = await self._terminal_fields(task_id, status, error_message, item_count)
        task = await self.repo.update(
            task_id, only_if_status=("pending", "running"), **update_kwargs
        )
        if task is None:
            return await self._current_response(task_id)
        await self.session.commit()
        await self.session.refresh(task)

        try:
            await _release_active_slots(get_async_redis(), task.spider_name, task_id, task)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"清理活跃任务关联失败: task_id={task_id}, error={e}")
        await self._record_log_end(task_id)

        snapshot = _finish_snapshot(task)
        if status == "completed":
            await self._emit_completed(snapshot)
        _spawn_side_effect(self._run_finish_side_effects(snapshot))
        return SpiderTaskResponse.model_validate(task)

    async def _terminal_fields(
        self, task_id: int, status: str, error_message: Optional[str], item_count: Optional[int],
    ) -> dict:
        """终态落库字段：result_count 结果表计数 >0（或无上报值）取计数，否则取 webhook 上报值"""
        update_kwargs = dict(
            status=status,
            error_message=error_message,
            completed_at=func.now(),
        )
        counted = None
        try:
            raw = await self.result_repo.count_by_task(task_id)
            if isinstance(raw, int):
                counted = raw
        except Exception:  # noqa: BLE001 计数失败回退 webhook 上报值
            counted = None
        if counted is not None and (counted > 0 or item_count is None):
            update_kwargs["result_count"] = counted
        elif item_count is not None:
            update_kwargs["result_count"] = item_count
        return update_kwargs

    async def _current_response(self, task_id: int) -> SpiderTaskResponse:
        """CAS 未命中（任务已被并发推进）：按当前行返回；行已不存在抛 NotFound"""
        current = await self.repo.get_by_id(task_id)
        if current is None:
            raise NotFoundException("爬虫任务")
        return SpiderTaskResponse.model_validate(current)

    async def _reenqueue(self, task) -> int:
        """重试专用延迟入队：ZSET score=到期时间戳（退避 1s→5s→15s），绕过并发槽位检查

        consumer._scan_retry_zset 每 tick 扫描到期成员，原子抢占后重新投递
        对应优先级主队列（消息携带 priority 字段供扫描侧选队）。
        返回本次退避延迟秒数（供调用方日志）。
        """
        delay = retry_delay(task.retry_count or 1)
        message = _retry_message(task)
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
            await _release_active_slots(get_async_redis(), spider_name, task_id, task)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"删除任务后清理活跃键失败: task_id={task_id}, error={e}")

        logger.info(
            f"任务已删除: task_id={task_id}, spider={spider_name}, 级联结果数={removed_results}"
        )
        return {"task_id": task_id, "removed_results": removed_results}

    # ------------------------------------------------------------------
    # 数据源多存储（4.2）：终态 CSV 落盘（行映射 / 写盘见 spider_task_side_effects）
    # ------------------------------------------------------------------
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
        rows = _csv_rows(task, raw_entries)
        out_dir = self._store_dir()
        path = await asyncio.to_thread(self._write_csv_sync, out_dir, task.id, rows)
        logger.info(f"csv 已落盘: task_id={task.id}, path={path}, rows={len(rows)}")

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
