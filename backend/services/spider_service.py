"""爬虫服务 - 统一入口（Facade）+ 共享工具函数

职责：
- 提供 SpiderService 门面类，委托给三个子 Service（向后兼容）
- 定义共享常量 / 工具函数（extract_flow / resolve_spider_log_path 等）
- 子 Service 通过 __getattr__ 委托访问本模块的属性和依赖

约束（遵循 AuthService 范式）：
- 不直接写 SQL、不直接 session.execute
- 所有数据操作通过 Repository
"""
import json
import os
import sys
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

# 以下导入供子 Service 通过 self.xxx 委托访问（测试 patch 需要），保留即使 Facade 未直接使用
from backend.repositories.spider_definition_repository import SpiderDefinitionRepository  # noqa: F401
from backend.repositories.spider_result_repository import SpiderResultRepository
from backend.repositories.spider_task_repository import SpiderTaskRepository
from backend.repositories.task_template_repository import TaskTemplateRepository  # noqa: F401
from backend.services.notify_service import NotifyService
from config import settings
from platform_core.db import redis_client  # noqa: F401
from platform_core.exceptions import BusinessException, NotFoundException  # noqa: F401
from platform_core.logger import get_logger
from platform_core.queues import (  # noqa: F401
    ACTIVE_TASK_KEY,
    TASK_CONTROL_KEY,
    TASK_LOG_OFFSET_KEY,
    TASK_RESULTS_KEY,
    WORKER_HEARTBEAT_PREFIX,
    task_queue,
)

logger = get_logger("api")

# 项目根目录（与 platform_core.logger 的日志根解析保持一致）
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# 代码爬虫目录（4.4 文件清单只读扫描，不读文件内容，B2 边界）
_SPIDERS_DIR = os.path.join(_PROJECT_ROOT, "scrapy", "spiders")


def resolve_spider_log_path() -> Optional[str]:
    logger.debug("解析爬虫日志文件路径")
    spider_cfg = getattr(settings, "LOGGERS", {}).get("spider", {}) if hasattr(settings, "LOGGERS") else {}
    rel = "logs/spider/spider.log"
    if spider_cfg:
        rel = spider_cfg.get("FILE", spider_cfg.get("file", rel))
    if os.path.isabs(rel):
        candidate = os.path.abspath(rel)
    else:
        candidate = os.path.abspath(os.path.join(_PROJECT_ROOT, rel))
    log_root = os.path.join(_PROJECT_ROOT, "logs")
    if not candidate.startswith(log_root + os.sep):
        logger.warning(f"非法的爬虫日志路径，已拒绝: {candidate}")
        return None
    return candidate


def extract_store_targets(params: Optional[str]) -> list[str]:
    logger.debug(f"解析任务存储目标: params={params!r}" if params else "解析任务存储目标: 无 params")
    if not params:
        return []
    try:
        data = json.loads(params)
    except (TypeError, ValueError):
        return []
    raw = data.get("store_to") if isinstance(data, dict) else None
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [t for t in raw if t in _STORE_TARGET_ENUM]


# 已实现的额外存储目标枚举
_STORE_TARGET_ENUM = ("redis", "csv")

# 阶段 5.1 流程化采集
FLOW_SPIDER_NAME = "flow_generic"
_FLOW_KEYS = ("pagination", "detail", "filters")


def extract_flow(params: Optional[str]) -> Optional[dict]:
    logger.debug(f"识别流程采集参数: params={params!r}" if params else "识别流程采集参数: 无 params")
    if not params:
        return None
    try:
        data = json.loads(params)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    flow = {}
    selectors = data.get("selectors")
    if isinstance(selectors, list):
        flow["selectors"] = [s for s in selectors if isinstance(s, dict)]
    for key in _FLOW_KEYS:
        section = data.get(key)
        if isinstance(section, dict) and section:
            flow[key] = section
        elif key == "filters" and isinstance(section, list):
            rules = [r for r in section if isinstance(r, dict)]
            if rules:
                flow[key] = rules
    has_section = any(k in flow for k in _FLOW_KEYS)
    return flow if has_section else None


def _read_task_log_sync(
    log_path: str,
    offset: int | None,
    tail: int,
    keyword: str | None = None,
    level: str | None = None,
) -> list[str]:
    """同步读取并过滤任务日志（供 asyncio.to_thread 调用）"""
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        size = os.fstat(f.fileno()).st_size
        if offset is not None and 0 < offset <= size:
            f.seek(offset)
        lines = f.read().splitlines()

    if not keyword and not level:
        return lines[-tail:]

    kw_lower = keyword.lower() if keyword else None
    level_upper = level.upper() if level else None
    filtered: list[str] = []
    for line in lines:
        if level_upper:
            parts = line.split("|")
            if len(parts) >= 2:
                line_level = parts[1].strip().upper()
                if line_level != level_upper:
                    continue
            else:
                continue
        if kw_lower and kw_lower not in line.lower():
            continue
        filtered.append(line)
    return filtered[-tail:]


# 当前模块引用（供 __getattr__ 回退到模块级名称，支持测试 patch）
_this_module = sys.modules[__name__]


class SpiderService:
    """爬虫服务门面 — 委托给三个子 Service（向后兼容）

    属性查找链：
    1. 实例 __dict__（session / repo / result_repo / notifier）
    2. 类属性 / 描述符（_task_svc property 等）
    3. __getattr__ → 子 Service 懒初始化 → 模块级名称回退
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = SpiderTaskRepository(session)
        self.result_repo = SpiderResultRepository(session)
        self.notifier = NotifyService()

    def __getattr__(self, name):
        """懒初始化子 Service + 模块级名称回退（支持测试 patch）"""
        # 子 Service 懒初始化
        if name == "_task_svc":
            from backend.services.spider_task_service import SpiderTaskService
            svc = SpiderTaskService(self)
            self.__dict__["_task_svc"] = svc
            return svc
        if name == "_query_svc":
            from backend.services.spider_query_service import SpiderQueryService
            svc = SpiderQueryService(self)
            self.__dict__["_query_svc"] = svc
            return svc
        if name == "_registry_svc":
            from backend.services.spider_registry_service import SpiderRegistryService
            svc = SpiderRegistryService(self)
            self.__dict__["_registry_svc"] = svc
            return svc
        # 模块级名称回退（settings / redis_client / _SPIDERS_DIR 等）
        try:
            return getattr(_this_module, name)
        except AttributeError:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    # ------------------------------------------------------------------
    # 任务编排 → SpiderTaskService
    # ------------------------------------------------------------------
    async def list_tasks(self, skip=0, limit=20, status=None, priority=None):
        return await self._task_svc.list_tasks(skip=skip, limit=limit, status=status, priority=priority)

    async def enqueue(self, spider_name, params=None, priority="normal"):
        return await self._task_svc.enqueue(spider_name=spider_name, params=params, priority=priority)

    async def finish_task(self, task_id, status, error_message=None, item_count=None):
        return await self._task_svc.finish_task(task_id, status, error_message=error_message, item_count=item_count)

    async def delete_task(self, task_id):
        return await self._task_svc.delete_task(task_id)

    async def control_task(self, task_id, action):
        return await self._task_svc.control_task(task_id, action)

    async def update_task(self, task_id, params=None, priority=None):
        return await self._task_svc.update_task(task_id, params=params, priority=priority)

    # ------------------------------------------------------------------
    # 结果查询 / 统计 → SpiderQueryService
    # ------------------------------------------------------------------
    async def list_results(self, task_id, skip=0, limit=50):
        return await self._query_svc.list_results(task_id=task_id, skip=skip, limit=limit)

    async def search_results(self, spider_name=None, page=1, page_size=20, start_time=None, end_time=None, keyword=None):
        return await self._query_svc.search_results(
            spider_name=spider_name, page=page, page_size=page_size,
            start_time=start_time, end_time=end_time, keyword=keyword,
        )

    async def delete_result(self, result_id):
        return await self._query_svc.delete_result(result_id)

    async def export_results(self, task_id, fmt):
        return await self._query_svc.export_results(task_id, fmt)

    async def get_task_quality(self, task_id):
        return await self._query_svc.get_task_quality(task_id)

    async def task_logs(self, task_id, lines=200, keyword=None, level=None):
        return await self._query_svc.task_logs(task_id, lines=lines, keyword=keyword, level=level)

    async def store_status(self, task_id):
        return await self._query_svc.store_status(task_id)

    def _store_targets(self, task):
        return self._query_svc._store_targets(task)

    def _store_dir(self):
        return self._query_svc._store_dir()

    async def stats(self):
        return await self._query_svc.stats()

    # ------------------------------------------------------------------
    # 注册表 / 文件 / 节点 / 模板 → SpiderRegistryService
    # ------------------------------------------------------------------
    async def registry(self):
        return await self._registry_svc.registry()

    async def spider_files(self):
        return await self._registry_svc.spider_files()

    async def update_definition(self, name, enabled):
        return await self._registry_svc.update_definition(name, enabled)

    async def create_definition(self, payload, source="manual"):
        # E2E 修复 (2026-08-29): 转发层漏传 source，AI 注册(source=ai_generated)必 500——
        # ai_planner_service.register 经此处调用， SpiderRegistryService.create_definition 本身支持该参数。
        return await self._registry_svc.create_definition(payload, source=source)

    async def update_definition_meta(self, name, payload):
        return await self._registry_svc.update_definition_meta(name, payload)

    async def delete_definition(self, name):
        return await self._registry_svc.delete_definition(name)

    async def list_nodes(self):
        return await self._registry_svc.list_nodes()

    async def list_templates(self):
        return await self._registry_svc.list_templates()

    async def create_template(self, payload, created_by=None):
        return await self._registry_svc.create_template(payload, created_by=created_by)

    async def update_template(self, template_id, payload):
        return await self._registry_svc.update_template(template_id, payload)

    async def delete_template(self, template_id):
        return await self._registry_svc.delete_template(template_id)

    async def create_task_from_template(self, template_id):
        return await self._registry_svc.create_task_from_template(template_id)

    @staticmethod
    def _task_log_offset(task_id: int) -> Optional[int]:
        from platform_core.db import redis_client
        from platform_core.queues import TASK_LOG_OFFSET_KEY
        from platform_core.logger import get_logger
        logger = get_logger("api")
        try:
            raw = redis_client().get(TASK_LOG_OFFSET_KEY.format(task_id=task_id))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"读取任务日志偏移量失败: task_id={task_id}, error={e}")
            return None
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
