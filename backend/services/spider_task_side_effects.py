"""爬虫任务终态副作用 - 后台任务托管 / 终态快照 / CSV 行映射与写盘 / 租户交付 / 告警评估

自 spider_task_service 拆出（规模约定），SpiderTaskService 经
SpiderTaskSideEffectsMixin 组合本模块方法：

- 期 3 webhook 主路径减负：finish_task 终态落库 + 槽位释放后立即返回，
  CSV 落盘 / 终态通知 / 租户交付 / 告警评估由 _spawn_side_effect 后台执行
  （_SIDE_EFFECT_TASKS 强引用集防 GC，对齐 ai_planner._spawn 范式）。
- 期 4：告警评估与租户交付自开独立短事务 session（请求 session 随响应关闭，
  后台协程复用必炸）。
- 读 Redis / settings 的 _flush_store / _store_targets / _store_dir 留在
  spider_task_service（测试 patch 目标 backend.services.spider_task_service.<name> 不变）；
  _SIDE_EFFECT_TASKS / _spawn_side_effect 由 spider_task_service re-export。
"""
import asyncio
import json
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.db import get_manager
from platform_core.logger import get_logger

logger = get_logger("api")

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


def _finish_snapshot(task) -> dict:
    """终态标量快照：后台副作用只消费它（脱离 ORM）

    幂等：finish_task 入口已有终态守卫（completed/failed 直接返回），同一任务
    重复回调不会走到 spawn → 副作用仅随本次终态推进 spawn 一次；后台任务内
    不再重复查终态，仅消费本快照（无二次 DB 读，也规避后台执行期 ORM 惰性
    加载触碰已关闭的 session）。
    """
    return {
        "id": task.id,
        "spider_name": task.spider_name,
        "status": task.status,
        "result_count": task.result_count or 0,
        "retry_count": task.retry_count or 0,
        "error_message": task.error_message,
        "params": task.params,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
        "tenant_id": getattr(task, "tenant_id", None),
    }


def _csv_rows(task, raw_entries) -> list[dict]:
    """Redis 结果缓存条目 → CSV 行（列序见 _EXPORT_COLUMNS；无法解析的条目跳过）"""
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
    return rows


async def _deliver_to_tenant(snapshot: dict) -> None:
    """租户交付 webhook：租户配置了交付地址才投递；失败只记日志不影响终态"""
    task_id = snapshot["id"]
    tid = snapshot.get("tenant_id")
    if not isinstance(tid, int):
        return
    try:
        from backend.services.delivery_webhook_service import DeliveryWebhookService
        from backend.services.tenant_settings_service import TenantSettingsService

        manager = get_manager()
        async with AsyncSession(manager.async_engines["DEFAULT"]) as sess:
            url, secret = await TenantSettingsService(sess).get_delivery_config(tid)
        if url:
            await DeliveryWebhookService().deliver(url, secret=secret, payload={
                "event": "task.finished",
                "task_id": task_id,
                "spider_name": snapshot["spider_name"],
                "status": snapshot["status"],
                "result_count": snapshot["result_count"],
                "tenant_id": tid,
            })
    except Exception as e:  # noqa: BLE001 租户交付失败不影响终态
        logger.warning(f"租户交付 webhook 失败（忽略）: task={task_id} err={e}")


async def _evaluate_alerts(snapshot: dict) -> None:
    """告警规则评估：自开独立短事务 session（期 4 收口，Oscar 登记）

    本协程由 _spawn_side_effect 后台执行，生命周期长于 webhook 请求；
    finish_task 的请求 session 在响应返回后已关闭，复用会触发「session
    已关闭」异常（原被自吞）。对齐 ai_planner 后台协程范式（_run_plan_bg /
    state._read_task_snapshot）：经 get_manager() 新建独立 AsyncSession，
    用完即关；评估失败仍吞异常仅记日志。
    """
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
                "task_id": snapshot["id"],
                "spider_name": snapshot["spider_name"],
                "status": snapshot["status"],
                "result_count": snapshot["result_count"],
                "duration_seconds": duration,
            })
    except Exception as e:  # noqa: BLE001
        logger.warning(f"告警评估失败（不影响主流程）: {e}")


class SpiderTaskSideEffectsMixin:
    """SpiderTaskService 的终态副作用部分（依赖宿主的 notifier / _flush_store）"""

    # 数据源多存储（4.2）：终态 CSV 落盘列序
    _EXPORT_COLUMNS = (
        "id", "task_id", "spider_name", "url", "title", "content",
        "source", "item_type", "extra", "created_at",
    )

    async def _run_finish_side_effects(self, snapshot: dict) -> None:
        """终态副作用后台协程（由 _spawn_side_effect 启动，不阻塞 webhook 主路径）

        入参为 finish_task 提取的任务标量快照；_flush_store 经 SimpleNamespace
        按原 task 鸭子类型访问。副作用按原有顺序执行：
        - CSV 落盘 / 租户交付 / 告警评估：沿用原有吞异常语义，失败仅记日志
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
        await _deliver_to_tenant(snapshot)
        await _evaluate_alerts(snapshot)

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
            writer = csv.DictWriter(f, fieldnames=SpiderTaskSideEffectsMixin._EXPORT_COLUMNS)
            writer.writeheader()
            from backend.utils.csv_safe import safe_csv_row

            writer.writerows(safe_csv_row(r) for r in rows)  # 审计 BUG-20：公式注入
        return path
