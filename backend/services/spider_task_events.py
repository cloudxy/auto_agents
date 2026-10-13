"""爬虫任务产品事件埋点 - task_blocked / task_run_submitted / task_completed

自 spider_task_service 拆出（规模约定），SpiderTaskService 经 SpiderTaskEventsMixin
组合。emit_product_event 按调用局部 import（测试 patch 目标仍是
backend.services.product_event_service.<name>）；依赖宿主的 session。
"""
from platform_core.logger import get_logger

logger = get_logger("api")


class SpiderTaskEventsMixin:
    """SpiderTaskService 的产品事件部分：入队拦住 / 入队提交 / 任务完成"""

    async def _emit_blocked(self, tenant_id: int, reason: str, spider_name: str) -> None:
        logger.info(f"拦住事件 | tenant={tenant_id} reason={reason}")
        from backend.services.product_event_service import emit_product_event
        await emit_product_event(
            self.session, "task_blocked",
            tenant_id=tenant_id,
            props={"reason": reason, "spider": spider_name},
        )

    async def _emit_submitted(self, task) -> None:
        logger.info(f"入队事件 | task={task.id} spider={task.spider_name}")
        from backend.services.product_event_service import emit_product_event
        await emit_product_event(
            self.session, "task_run_submitted",
            tenant_id=getattr(task, "tenant_id", None),
            props={"spider": task.spider_name},
        )

    async def _emit_completed(self, snapshot: dict) -> None:
        logger.info(f"完成事件 | task={snapshot['id']}")
        from backend.services.product_event_service import emit_product_event
        spider = snapshot["spider_name"]
        is_mkt = spider == "skill_harvester"
        await emit_product_event(
            self.session, "task_completed",
            tenant_id=snapshot.get("tenant_id"),
            props={
                "result_count": snapshot["result_count"],
                "spider": spider,
                "source": "marketplace" if is_mkt else "collect",
                "is_marketplace_candidate": is_mkt,
            },
        )
