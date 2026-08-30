"""爬虫任务编排服务 - 任务入队/终态推进/控制/删除

职责：
- enqueue：数据库登记 + 投递 Redis 优先级队列（数据闭环入口）
- finish_task：Webhook 回调落地，幂等终态推进（含自动重试/告警/通知）
- control_task：暂停/恢复/终止运行中的任务（Redis 控制键通信）
- delete_task：删除任务及级联结果（running 拒绝）
- list_tasks / get_task：任务查询

设计说明：
- 子 Service 通过 __getattr__ 将未知属性委托给父 Facade（SpiderService），
  确保测试 patch backend.services.spider_service.<name> 能正确生效。
- 不直接 import Repository/redis_client/settings；通过 self 委托访问。
"""
import json
from typing import Optional

from sqlalchemy import func

from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.queues import ACTIVE_TASK_KEY, TASK_CONTROL_KEY, task_queue
from platform_core.schemas.spider import (
    SpiderTaskListResponse,
    SpiderTaskResponse,
)

# 从 spider_service 导入共享常量（不会被测试 patch，可安全模块级引用）
from backend.services.spider_service import (  # noqa: E402
    FLOW_SPIDER_NAME,
    extract_flow,
    extract_store_targets,
)

logger = get_logger("api")


class SpiderTaskService:
    """任务编排：入队 / 终态 / 控制 / 删除 / 列表"""

    def __init__(self, parent):
        """parent: SpiderService Facade 实例，提供 session/repo 等属性委托"""
        self._parent = parent

    def __getattr__(self, name):
        """委托未知属性到父 Facade（session/repo/settings/redis_client 等）"""
        return getattr(self._parent, name)

    async def list_tasks(
        self,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> SpiderTaskListResponse:
        """分页列表（Service 层负责把 ORM 实体转成响应契约）"""
        items = await self.repo.list_tasks(skip=skip, limit=limit, status=status, priority=priority)
        total = await self.repo.count(status=status, priority=priority)
        return SpiderTaskListResponse(
            total=total,
            items=[SpiderTaskResponse.model_validate(t) for t in items],
        )

    def _max_concurrent(self) -> int:
        """同爬虫并发任务上限（配置即代码，至少 1）"""
        return max(1, int(self.settings.get("SPIDER_MAX_CONCURRENT_PER_SPIDER", 2)))

    async def _ensure_spider_available(self, spider_name: str) -> None:
        """入队前注册表校验：DB 优先（存在且 enabled），无记录回退 yml 种子

        - DB 有记录且停用 → 拒绝（停用爬虫不允许再入队）
        - DB 无记录 → yml settings.SPIDERS 兜底（存量 yml-only 爬虫不破坏）
        - DB 与 yml 均无 → 拒绝（未登记的爬虫不允许入队）
        - DB 查询异常 → 仅记日志并跳过校验（DB 故障不阻断入队主流程）
        """
        definition = None
        try:
            definition = await self.SpiderDefinitionRepository(self.session).get_by_name(spider_name)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"注册表 DB 校验失败，跳过: spider={spider_name}, error={e}")
            return
        if definition is not None:
            if not definition.enabled:
                raise BusinessException(f"爬虫 {spider_name} 已停用，无法提交任务")
            return
        spiders_cfg = self.settings.get("SPIDERS", {}) or {}
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
    ) -> SpiderTaskResponse:
        """入队一个新任务：数据库登记 + 投递 Redis 优先级队列（数据闭环入口）"""
        logger.info(f"爬虫任务入队: spider={spider_name}, priority={priority}")

        # 阶段 5.1：含流程段（分页/详情/过滤）的任务统一归入 flow_generic 执行
        if extract_flow(params) is not None:
            spider_name = FLOW_SPIDER_NAME

        # 阶段 6：注册表校验（DB 优先，yml 兜底；停用/未登记拒绝）
        await self._ensure_spider_available(spider_name)

        # 并发槽位守卫
        active_key = ACTIVE_TASK_KEY.format(spider_name=spider_name)
        max_concurrent = self._max_concurrent()
        try:
            active_count = self.redis_client().scard(active_key)
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
        )
        await self.session.commit()
        await self.session.refresh(task)

        # 投递任务消息到对应优先级队列
        message = json.dumps(
            {"task_id": task.id, "spider_name": spider_name, "params": params},
            ensure_ascii=False,
        )
        try:
            self.redis_client().rpush(task_queue(priority), message)
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
        - LREM 未命中（消息已被消费/从未投递）时不动队列，仅改 DB，避免重复消费
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
            removed = self.redis_client().lrem(from_queue, 1, old_message)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"队列 LREM 失败（旧消息保留在原队列）: task_id={task_id}, error={e}"
            )
            return
        if not removed:
            logger.warning(
                f"旧优先级队列未命中任务消息（可能已被消费/从未投递），不动队列: task_id={task_id}"
            )
            return
        try:
            self.redis_client().rpush(to_queue, new_message)
        except Exception as e:  # noqa: BLE001
            # M1：LREM 已移除旧消息而 rpush 失败，先 lpush 回原队列补偿防消息丢失
            try:
                self.redis_client().lpush(from_queue, old_message)
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

    async def finish_task(
        self,
        task_id: int,
        status: str,
        error_message: Optional[str] = None,
        item_count: Optional[int] = None,
    ) -> SpiderTaskResponse:
        """Webhook 回调落地：任务终态推进（completed/failed，幂等）"""
        logger.info(f"任务终态推进: task_id={task_id}, status={status}")
        task = await self.repo.get_by_id(task_id)
        if task is None:
            raise NotFoundException("爬虫任务")
        if task.status in ("completed", "failed"):
            return SpiderTaskResponse.model_validate(task)

        # 失败自动重试
        max_retries = int(self.settings.get("SPIDER_MAX_RETRIES", 2))
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
                self.redis_client().srem(
                    ACTIVE_TASK_KEY.format(spider_name=task.spider_name), task_id
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"重试前清理活跃键失败: task_id={task_id}, error={e}")
            await self._reenqueue(task)
            logger.warning(
                f"任务失败自动重试: task_id={task_id}, spider={task.spider_name}, "
                f"第 {next_retry}/{max_retries} 次"
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
            self.redis_client().srem(ACTIVE_TASK_KEY.format(spider_name=task.spider_name), task_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"清理活跃任务关联失败: task_id={task_id}, error={e}")

        # 数据源多存储（4.2）：终态后 CSV 落盘
        try:
            await self._flush_store(task)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"csv 落盘失败（不影响任务终态）: task_id={task_id}, error={e}")

        # 终态通知
        await self.notifier.notify_task_finished(
            task_id=task.id,
            spider_name=task.spider_name,
            status=task.status,
            result_count=task.result_count or 0,
            retry_count=task.retry_count or 0,
            error_message=task.error_message,
        )

        # 告警规则评估
        try:
            from backend.services.alert_service import AlertService
            alert_svc = AlertService(self.session)
            duration = 0
            if task.started_at and task.completed_at:
                duration = (task.completed_at - task.started_at).total_seconds()
            await alert_svc.evaluate({
                "task_id": task.id,
                "spider_name": task.spider_name,
                "status": task.status,
                "result_count": task.result_count or 0,
                "duration_seconds": duration,
            })
        except Exception as e:  # noqa: BLE001
            logger.warning(f"告警评估失败（不影响主流程）: {e}")

        return SpiderTaskResponse.model_validate(task)

    async def _reenqueue(self, task) -> None:
        """重试专用入队：直接投递对应优先级队列，绕过并发槽位检查"""
        message = json.dumps(
            {"task_id": task.id, "spider_name": task.spider_name, "params": task.params},
            ensure_ascii=False,
        )
        try:
            self.redis_client().rpush(task_queue(task.priority or "normal"), message)
        except Exception as e:  # noqa: BLE001
            logger.error(f"重试投递 Redis 失败: task_id={task.id}, error={e}")
            await self.repo.update(
                task.id, status="failed", error_message=f"重试投递失败: {e}"
            )
            await self.session.commit()

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
            self.redis_client().srem(ACTIVE_TASK_KEY.format(spider_name=spider_name), task_id)
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
                self.redis_client().delete(control_key)
                logger.info(f"任务恢复: task_id={task_id}")
                return {"task_id": task_id, "action": "resume", "message": "任务已恢复"}
            else:
                self.redis_client().set(control_key, action, ex=self._CONTROL_TTL)
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
        """终态落盘：把任务结果缓存列表写成 CSV（仅 csv 目标生效）"""
        logger.info(f"检查任务存储落盘: task_id={task.id}")
        if "csv" not in self._store_targets(task):
            return
        from platform_core.queues import TASK_RESULTS_KEY
        key = TASK_RESULTS_KEY.format(task_id=task.id)
        raw_entries = self.redis_client().lrange(key, 0, -1)
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
        import os
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"task_{task.id}.csv")
        import csv
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=self._EXPORT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        logger.info(f"csv 已落盘: task_id={task.id}, path={path}, rows={len(rows)}")

    def _store_dir(self) -> str:
        """csv 落盘目录（配置即代码）"""
        import os
        from backend.services.spider_service import _PROJECT_ROOT
        rel = self.settings.get("STORAGE.DIR", "storage/exports") or "storage/exports"
        return rel if os.path.isabs(rel) else os.path.abspath(os.path.join(_PROJECT_ROOT, rel))

    def _store_targets(self, task) -> list[str]:
        """生效的额外存储目标"""
        from backend.services.spider_service import _STORE_TARGET_ENUM
        targets = extract_store_targets(getattr(task, "params", None))
        if not targets:
            default = self.settings.get("STORAGE.EXTRA_TARGETS", []) or []
            if isinstance(default, str):
                default = [default]
            targets = [t for t in default if t in _STORE_TARGET_ENUM]
        return targets

