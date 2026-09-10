"""状态机辅助层：后台任务启动 / 试采终态快照 / 失败兜底 / 启动对账

拆分自 ai_planner_service.py（期4 结构治理），职责边界：
- 后台任务启动：_spawn（强引用防 GC）+ _BACKGROUND_TASKS
- 试采终态快照：_TaskSnapshot / _read_task_snapshot（独立短事务 session，
  规避长生命周期 session identity map 遮蔽 worker webhook 推进的终态）
- 失败兜底：_force_fail_status（m3 最后防线）+ _run_plan_bg / _run_test_bg
- 启动对账：reconcile_interrupted_plans（评审 M-2：无条件清理中断遗留占用态）
- 状态守卫常量：_BUSY_STATUSES（M5 条件 UPDATE 原子抢断的占用态集合）

Patch 兼容约定：get_manager / AsyncSession / AiPlanRepository / AiPlannerService
等被存量单测 patch 的符号一律经 llm_common.seam() 命名空间调用期取值（T6 解环：
门面初始化完成后注入 seam，无文件末尾反向 import），
使 patch("backend.services.ai_planner_service.<name>") 在运行时生效。
"""
import asyncio
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, update

from backend.services.llm_common.seam import seam as _seam
from platform_core.logger import get_logger
from platform_core.models.ai_plan import AiPlan
from platform_core.models.spider_task import SpiderTask

logger = get_logger("api")

# M5：规划/试采/注册互斥的占用态（条件 UPDATE 原子抢断的状态守卫集合）
_BUSY_STATUSES = ("planning", "testing", "registered")

# 试采等待参数（终态轮询）
_WAIT_INTERVAL_SECONDS = 5.0
_WAIT_TIMEOUT_SECONDS = 600.0

# 后台任务强引用集（防 asyncio.Task 被 GC），完成后自动清理
_BACKGROUND_TASKS: set = set()


# ----------------------------------------------------------------------
# 后台任务启动（自开独立 session）
# ----------------------------------------------------------------------
def _spawn(coro) -> None:
    """创建后台任务并持有引用（防 GC），完成后自动清理"""
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


@dataclass(frozen=True)
class _TaskSnapshot:
    """试采任务状态快照（独立短事务读取的纯标量，脱离 ORM session，无懒加载风险）"""

    task_id: int
    status: str
    result_count: int
    error_message: Optional[str]


async def _read_task_snapshot(task_id: int) -> Optional[_TaskSnapshot]:
    """独立短事务 session 读任务标量快照（每轮新建、查完即关）

    缺陷背景：后台试采协程曾复用长生命周期 session 轮询 repo.get_by_id，
    identity map 中已加载未过期实体即使 SELECT 到新行也不刷新属性（默认无
    populate_existing）→ worker webhook 推进的终态永不可见 → 600s 必超时。
    独立 session 每轮新建连接/事务，读到的永远是 DB 最新已提交行（与事务
    隔离级别无关）；且只取标量列，连 ORM 实体都不进 identity map（双保险）。
    """
    manager = _seam().get_manager()
    async with _seam().AsyncSession(manager.async_engines["DEFAULT"]) as session:
        row = await session.execute(
            select(
                SpiderTask.id,
                SpiderTask.status,
                SpiderTask.result_count,
                SpiderTask.error_message,
            ).where(SpiderTask.id == task_id)
        )
        data = row.first()
    if data is None:
        return None
    return _TaskSnapshot(
        task_id=int(data.id),
        status=str(data.status),
        result_count=int(data.result_count or 0),
        error_message=data.error_message,
    )


async def _force_fail_status(plan_id: int, message: str) -> None:
    """m3 最后防线：_fail 自身失败（如 DB 异常卡死）时用全新 session 落 failed；
    新 session 也失败则仅记日志，不再抛（避免掩盖原始异常/无限递归）。"""
    try:
        manager = _seam().get_manager()
        async with _seam().AsyncSession(manager.async_engines["DEFAULT"]) as session:
            await _seam().AiPlanRepository(session).update_status(
                plan_id, "failed", error_message=message[:2000], test_task_id=None
            )
            await session.commit()
        logger.warning(f"AI 计划兜底置 failed 完成: plan_id={plan_id}")
    except Exception as e:  # noqa: BLE001 兜底失败只记日志
        logger.error(f"AI 计划兜底置 failed 失败: plan_id={plan_id}, error={e}")


async def reconcile_interrupted_plans() -> int:
    logger.info("启动对账开始：无条件清理中断遗留的 planning/testing AI 计划（评审 M-2）")
    # 后台规划/试采任务不跨进程持久：进程重启后这些行会永久滞留占用态
    # （_BUSY_STATUSES 抢断锁），阻塞重新触发。lifespan 启动阶段为单实例
    # 语义，进行中的后台任务必然已随进程消亡，故不再按 updated_at 宽限
    # （评审 M-2：原 10 分钟窗口会让启动前 10 分钟内的滞留行逃过对账）
    # ——无条件全部置 failed("进程中断，请重新发起")，单语句批量 UPDATE。
    # 多副本部署会误伤其他副本正在执行的任务，故仅在单实例语义的
    # lifespan 启动阶段调用。
    stmt = (
        update(AiPlan)
        .where(AiPlan.status.in_(("planning", "testing")))
        .values(status="failed", error_message="进程中断，请重新发起", test_task_id=None)
        .execution_options(synchronize_session=False)
    )
    manager = _seam().get_manager()
    async with _seam().AsyncSession(manager.async_engines["DEFAULT"]) as session:
        result = await session.execute(stmt)
        await session.commit()
    affected = int(result.rowcount or 0)
    if affected:
        logger.warning(f"启动对账：{affected} 个中断遗留的 AI 计划已置 failed")
    return affected


async def _run_plan_bg(plan_id: int) -> None:
    """后台规划协程：自开独立 AsyncSession（端点请求 session 已随响应关闭）"""
    try:
        manager = _seam().get_manager()
        async with _seam().AsyncSession(manager.async_engines["DEFAULT"]) as session:
            await _seam().AiPlannerService(session)._execute_plan(plan_id)
    except Exception as e:  # noqa: BLE001 兜底：后台异常记日志 + 新 session 落失败态
        logger.error(f"AI 规划后台任务异常: plan_id={plan_id}, error={e}")
        await _seam()._force_fail_status(plan_id, f"规划后台异常: {e}")


async def _run_test_bg(plan_id: int) -> None:
    """后台试采协程：自开独立 AsyncSession"""
    try:
        manager = _seam().get_manager()
        async with _seam().AsyncSession(manager.async_engines["DEFAULT"]) as session:
            await _seam().AiPlannerService(session)._execute_test(plan_id)
    except Exception as e:  # noqa: BLE001
        logger.error(f"AI 试采后台任务异常: plan_id={plan_id}, error={e}")
        await _seam()._force_fail_status(plan_id, f"试采后台异常: {e}")

