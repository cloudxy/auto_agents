"""爬虫服务 —— 期 4 Facade 退役过渡模块

原 SpiderService 门面（模块级名称回退懒加载 + 94 行机械委托 + 隐式兼容导入）已退役：

- 共享工具 / 常量迁至 spider_common.py；
- 三个子 Service 独立化（自持 session/repo，模块级直引 settings / get_async_redis /
  Repository，不再经父 Facade 委托）：
    SpiderTaskService     任务编排（入队/终态/控制/删除）
    SpiderQueryService    结果查询 / 统计 / 日志 / 质量 / 存储状态
    SpiderRegistryService 注册表 / 文件 / 节点 / 模板
- API 层（app/api/v1/spiders/）已改为直接构造对应子 Service。

本模块仅保留两类存量符号（__all__ 显式列出）：

1. 共享工具 re-export —— tasks/consumer.py 等域外存量 from-import 路径不变；
2. SpiderService 过渡门面 —— 仅保留域外消费者实际调用的 6 个委托方法，逐条保留理由：
   - enqueue           schedule_service.py:264（定时调度触发入队）、
                       ai_planner/orchestrator.py:212（AI 试采入队）
   - get_task_quality  ai_planner/orchestrator.py:305（试采质量判定）
   - create_definition ai_planner/orchestrator.py:341（AI 注册爬虫定义）
   - stats             app/api/v1/admin.py:39（后台仪表盘统计）、
                       app/external_api/v1/public.py:149（公开统计）
   - list_results      app/external_api/v1/public.py:130（公开结果查询）
   - finish_task       app/external_api/webhooks.py:81（Worker Webhook 终态回调）
   上述文件均不在期 4 文件域内；后续任务将其迁移到子 Service 后本模块可整体删除。
"""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.spider_common import (
    FLOW_SPIDER_NAME,
    _FLOW_KEYS,
    _PROJECT_ROOT,
    _SPIDERS_DIR,
    _STORE_TARGET_ENUM,
    _read_task_log_sync,
    extract_flow,
    extract_store_targets,
    resolve_spider_log_path,
    settings,
)
from backend.services.spider_query_service import SpiderQueryService
from backend.services.spider_registry_service import SpiderRegistryService
from backend.services.spider_task_service import SpiderTaskService

__all__ = [
    "SpiderService",
    "SpiderTaskService",
    "SpiderQueryService",
    "SpiderRegistryService",
    "FLOW_SPIDER_NAME",
    "_FLOW_KEYS",
    "_PROJECT_ROOT",
    "_SPIDERS_DIR",
    "_STORE_TARGET_ENUM",
    "_read_task_log_sync",
    "extract_flow",
    "extract_store_targets",
    "resolve_spider_log_path",
    "settings",
]


class SpiderService:
    """退役过渡门面：显式构造三个子 Service，仅转发域外消费者使用的 6 个方法。

    保留理由见模块 docstring；新代码请直接使用对应子 Service。
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self._task_svc = SpiderTaskService(session)
        self._query_svc = SpiderQueryService(session)
        self._registry_svc = SpiderRegistryService(session)

    # 任务编排 → SpiderTaskService
    async def enqueue(self, spider_name, params: Optional[str] = None, priority: str = "normal"):
        return await self._task_svc.enqueue(spider_name=spider_name, params=params, priority=priority)

    async def finish_task(self, task_id, status, error_message=None, item_count=None):
        return await self._task_svc.finish_task(
            task_id, status, error_message=error_message, item_count=item_count
        )

    # 结果查询 → SpiderQueryService
    async def list_results(self, task_id, skip: int = 0, limit: int = 50):
        return await self._query_svc.list_results(task_id=task_id, skip=skip, limit=limit)

    async def get_task_quality(self, task_id):
        return await self._query_svc.get_task_quality(task_id)

    async def stats(self):
        return await self._query_svc.stats()

    # 注册表 → SpiderRegistryService
    async def create_definition(self, payload, source: str = "manual"):
        return await self._registry_svc.create_definition(payload, source=source)
