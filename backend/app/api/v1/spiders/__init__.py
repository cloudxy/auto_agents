"""爬虫域路由聚合包 —— 原 v1/spiders.py 按子域拆分

结构：
- deps.py        共享依赖工厂（_service / _schedule_service）
- tasks.py       任务子域（列表 / 入队 / 编辑 / 删除 / 控制 / 日志 / 质量 / 存储状态）
- results.py     采集结果子域（跨任务查询 / 按任务查询 / 删除 / 导出）
- definitions.py 注册表 / Worker 节点 / 文件清单 / 定义 CRUD / 代理健康
- schedules.py   定时调度 CRUD / 告警规则 CRUD
- templates.py   任务模板 CRUD / 一键运行

路由聚合：本模块创建 APIRouter 并 include 各子模块 router（不传 prefix/tags，
与拆分前单文件形态一致 —— 由 v1/__init__.py 统一挂载 prefix="/spiders"、
tags=["spiders"]）。

兼容命名空间：re-export 全部端点函数与共享依赖，并绑定 AlertService /
record_audit 与三个子 Service 依赖工厂，使存量 from-import 与 patch
路径 backend.app.api.v1.spiders.X 继续生效（告警端点在 schedules.py 内经
本包命名空间做调用时查找）。期 4 Facade 退役：原 SpiderService/_service
由 _task_service/_query_service/_registry_service 三工厂替代。
"""
from fastapi import APIRouter

from backend.app.api._helpers import record_audit
from backend.services.alert_service import AlertService
from backend.services.schedule_service import ScheduleService
from backend.services.spider_query_service import SpiderQueryService
from backend.services.spider_registry_service import SpiderRegistryService
from backend.services.spider_task_service import SpiderTaskService

from .deps import _query_service, _registry_service, _schedule_service, _task_service
from .tasks import router as tasks_router
from .tasks import (
    control_task,
    delete_task,
    get_task_logs,
    get_task_quality,
    list_tasks,
    run_spider,
    task_store_status,
    update_task,
)
from .results import router as results_router
from .results import delete_result, export_results, list_results, search_results
from .definitions import router as definitions_router
from .definitions import (
    create_definition,
    delete_definition,
    get_proxy_health,
    get_registry,
    list_nodes,
    list_spider_files,
    update_definition,
    update_definition_meta,
)
from .schedules import router as schedules_router
from .schedules import (
    create_alert_rule,
    create_schedule,
    delete_alert_rule,
    delete_schedule,
    list_alert_rules,
    list_schedules,
    update_alert_rule,
    update_schedule,
)
from .templates import router as templates_router
from .templates import (
    create_template,
    delete_template,
    list_templates,
    run_from_template,
    update_template,
)

router = APIRouter()
router.include_router(tasks_router)
router.include_router(results_router)
router.include_router(definitions_router)
router.include_router(schedules_router)
router.include_router(templates_router)

__all__ = [
    "router",
    # 兼容命名空间（旧 from-import / patch 路径）
    "AlertService",
    "ScheduleService",
    "SpiderTaskService",
    "SpiderQueryService",
    "SpiderRegistryService",
    "record_audit",
    "_task_service",
    "_query_service",
    "_registry_service",
    "_schedule_service",
    # tasks 子域（8）
    "list_tasks",
    "run_spider",
    "task_store_status",
    "update_task",
    "delete_task",
    "control_task",
    "get_task_logs",
    "get_task_quality",
    # results 子域（4）
    "search_results",
    "delete_result",
    "list_results",
    "export_results",
    # definitions 子域（8）
    "get_registry",
    "list_nodes",
    "list_spider_files",
    "update_definition",
    "create_definition",
    "update_definition_meta",
    "delete_definition",
    "get_proxy_health",
    # schedules + alert rules 子域（8）
    "list_schedules",
    "create_schedule",
    "update_schedule",
    "delete_schedule",
    "list_alert_rules",
    "create_alert_rule",
    "update_alert_rule",
    "delete_alert_rule",
    # templates 子域（5）
    "list_templates",
    "create_template",
    "update_template",
    "delete_template",
    "run_from_template",
]
