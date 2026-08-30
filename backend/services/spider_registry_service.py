"""爬虫注册表/文件/节点/模板服务 - 注册表/代码爬虫文件/Worker 节点/任务模板

职责：
- registry：爬虫类型表单 + 可调度爬虫清单（DB 优先，配置兜底）
- spider_files：代码爬虫文件清单（只读元数据 + 启停状态）
- update_definition：启停代码爬虫
- list_nodes：Worker 节点心跳扫描
- list/create/update/delete_template + create_task_from_template：模板管理

设计说明（期 4 Facade 退役后独立化）：
- 自持 session / repo；模块级直引 settings / get_async_redis / Repository /
  _SPIDERS_DIR（测试 patch 目标：backend.services.spider_registry_service.<name>）。
"""
import os

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.spider_definition_repository import SpiderDefinitionRepository
from backend.repositories.spider_task_repository import SpiderTaskRepository
from backend.repositories.task_template_repository import TaskTemplateRepository
from backend.services.spider_common import _SPIDERS_DIR
from config import settings
from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.queues import ACTIVE_TASK_KEY, WORKER_HEARTBEAT_PREFIX
from platform_core.redis_async import get_async_redis
from platform_core.schemas.spider import (
    DefinitionCreateRequest,
    DefinitionUpdateMetaRequest,
    SpiderDefinitionResponse,
    SpiderFileListResponse,
    SpiderFileResponse,
    SpiderInfo,
    SpiderParamField,
    SpiderRegistryResponse,
    SpiderTaskResponse,
    SpiderTypeInfo,
    TaskTemplateResponse,
    WorkerActiveTask,
    WorkerNodeListResponse,
    WorkerNodeResponse,
)

logger = get_logger("api")


class SpiderRegistryService:
    """注册表 / 文件管理 / Worker 节点 / 模板"""

    def __init__(self, session: AsyncSession):
        """独立 Service：自持会话与仓储（期 4 Facade 退役）"""
        self.session = session
        self.repo = SpiderTaskRepository(session)

    # ------------------------------------------------------------------
    # 爬虫注册表（类型表单走配置；爬虫清单 DB 优先、配置兜底）
    # ------------------------------------------------------------------
    async def registry(self) -> SpiderRegistryResponse:
        """返回爬虫类型表单定义 + 可调度爬虫清单"""
        logger.debug("构建爬虫注册表")
        types_cfg = settings.get("SPIDER_TYPES", {}) or {}
        spiders_cfg = settings.get("SPIDERS", {}) or {}

        types = []
        for type_key, tcfg in types_cfg.items():
            if type_key.startswith("_"):
                continue
            fields = [
                SpiderParamField(
                    name=f.get("name"),
                    label=f.get("label") or f.get("name"),
                    kind=f.get("kind", "text"),
                    required=bool(f.get("required", False)),
                    default=f.get("default"),
                    help=f.get("help"),
                    options=f.get("options"),
                )
                for f in (tcfg.get("fields") or [])
            ]
            types.append(
                SpiderTypeInfo(type=type_key, label=tcfg.get("label", type_key), fields=fields)
            )

        # 爬虫清单：DB 优先，查询失败或空表回退配置种子
        spiders: list[SpiderInfo] | None = None
        try:
            definitions = await SpiderDefinitionRepository(self.session).list_enabled()
            if definitions:
                spiders = [
                    SpiderInfo(
                        name=d.name,
                        title=d.title,
                        type=d.type,
                        description=d.description or "",
                    )
                    for d in definitions
                ]
        except Exception as e:  # noqa: BLE001
            logger.warning(f"注册表 DB 读取失败，回退配置: {e}")

        if spiders is None:
            spiders = []
            for name, scfg in spiders_cfg.items():
                if name.startswith("_"):
                    continue
                spiders.append(
                    SpiderInfo(
                        name=name,
                        title=scfg.get("title", name),
                        type=scfg.get("type", "web"),
                        description=scfg.get("description", ""),
                    )
                )
        return SpiderRegistryResponse(types=types, spiders=spiders)

    # ------------------------------------------------------------------
    # 代码爬虫文件管理（4.4）
    # ------------------------------------------------------------------
    async def spider_files(self) -> SpiderFileListResponse:
        """扫描 scrapy/spiders/*.py 文件清单，关联启停状态"""
        logger.info("扫描代码爬虫文件清单")
        definitions: dict = {}
        try:
            defs = await SpiderDefinitionRepository(self.session).get_all(limit=500)
            definitions = {d.name: d for d in defs}
        except Exception as e:  # noqa: BLE001
            logger.warning(f"爬虫定义读取失败，文件清单不含启停状态: {e}")

        items: list[SpiderFileResponse] = []
        spiders_dir = _SPIDERS_DIR
        if os.path.isdir(spiders_dir):
            for fname in sorted(os.listdir(spiders_dir)):
                if not fname.endswith(".py") or fname == "__init__.py":
                    continue
                name = fname[: -len(".py")]
                path = os.path.join(spiders_dir, fname)
                definition = definitions.get(name)
                try:
                    size = os.path.getsize(path)
                except OSError:
                    size = 0
                items.append(
                    SpiderFileResponse(
                        name=name,
                        file=f"scrapy/spiders/{fname}",
                        size_bytes=size,
                        registered=definition is not None,
                        enabled=definition.enabled if definition else None,
                        title=definition.title if definition else None,
                    )
                )
        else:
            logger.warning(f"代码爬虫目录不存在: {spiders_dir}")
        return SpiderFileListResponse(total=len(items), items=items)

    async def update_definition(self, name: str, enabled: bool) -> SpiderDefinitionResponse:
        """启停代码爬虫"""
        logger.info(f"更新爬虫定义启停: name={name}, enabled={enabled}")
        repo = SpiderDefinitionRepository(self.session)
        definition = await repo.get_by_name(name)
        if definition is None:
            raise NotFoundException("爬虫定义")
        updated = await repo.update(definition.id, enabled=enabled)
        await self.session.commit()
        await self.session.refresh(updated)
        return SpiderDefinitionResponse.model_validate(updated)

    # ------------------------------------------------------------------
    # 爬虫定义完整 CRUD（阶段 6）：登记/元信息编辑/删除（引用检查）
    # ------------------------------------------------------------------
    async def create_definition(
        self, payload: DefinitionCreateRequest, source: str = "manual"
    ) -> SpiderDefinitionResponse:
        """新建爬虫定义（来源标记默认 manual；AI 注册传 ai_generated；名称唯一）"""
        logger.info(f"新建爬虫定义: name={payload.name}, type={payload.type}, source={source}")
        repo = SpiderDefinitionRepository(self.session)
        existing = await repo.get_by_name(payload.name)
        if existing is not None:
            raise BusinessException(f"爬虫定义 '{payload.name}' 已存在（id={existing.id}）")
        item = await repo.create(
            name=payload.name,
            title=payload.title,
            type=payload.type,
            description=payload.description,
            enabled=True,
            source=source,
        )
        await self.session.commit()
        await self.session.refresh(item)
        return SpiderDefinitionResponse.model_validate(item)

    async def update_definition_meta(
        self, name: str, payload: DefinitionUpdateMetaRequest
    ) -> SpiderDefinitionResponse:
        """编辑爬虫定义元信息（标题/描述，不含启停与名称）"""
        logger.info(f"编辑爬虫定义元信息: name={name}, fields={list(payload.model_dump(exclude_unset=True).keys())}")
        repo = SpiderDefinitionRepository(self.session)
        definition = await repo.get_by_name(name)
        if definition is None:
            raise NotFoundException("爬虫定义")
        changes = payload.model_dump(exclude_unset=True, exclude_none=True)
        if not changes:
            return SpiderDefinitionResponse.model_validate(definition)
        updated = await repo.update(definition.id, **changes)
        await self.session.commit()
        await self.session.refresh(updated)
        return SpiderDefinitionResponse.model_validate(updated)

    async def delete_definition(self, name: str) -> dict:
        """删除爬虫定义（原子条件删除，存在历史任务引用时拒绝，防统计断链）

        m1 TOCTOU：DELETE ... NOT EXISTS 单语句原子判定，并发入队无法绕过
        引用检查；rowcount=0 时二次查询区分「定义不存在」与「被引用拒绝」。
        """
        logger.info(f"删除爬虫定义: name={name}")
        repo = SpiderDefinitionRepository(self.session)
        deleted = await repo.delete_if_unreferenced(name)
        if deleted:
            await self.session.commit()
            return {"name": name, "deleted": True}
        # rowcount=0：区分「定义不存在」（NotFound）与「被引用拒绝」（Business）两种失败
        definition = await repo.get_by_name(name)
        if definition is None:
            raise NotFoundException("爬虫定义")
        task_count = await self.repo.count_by_spider(name)
        raise BusinessException(
            f"爬虫 {name} 存在 {task_count} 条历史任务记录，拒绝删除；"
            f"可先停用（enabled=false）保留下线痕迹"
        )

    # ------------------------------------------------------------------
    # Worker 节点心跳（2.2）
    # ------------------------------------------------------------------
    async def list_nodes(self) -> WorkerNodeListResponse:
        """扫描 Worker 心跳键，返回在线节点及其各爬虫的活跃任务

        期 3 优化：
        - Redis 全异步化（scan_iter 异步迭代 / hgetall / smembers 均 await）
        - 消除逐 task get_by_id 的 N+1：先汇总全部活跃 task_id，
          一次 WHERE id IN (...) 批查（repo.get_by_ids）后回填状态
        """
        logger.info("查询 Worker 节点列表")
        try:
            client = get_async_redis()
            keys = [
                k async for k in client.scan_iter(
                    match=f"{WORKER_HEARTBEAT_PREFIX}*", count=100
                )
            ]
        except Exception as e:  # noqa: BLE001
            logger.warning(f"扫描节点心跳失败（返回空列表）: {e}")
            return WorkerNodeListResponse(total=0, items=[])

        # 第一遍：读心跳 + 收集各爬虫活跃 task_id（spider → task_ids）
        nodes: list[tuple[str, dict, list[str], list[tuple[str, list[int]]]]] = []
        all_task_ids: set[int] = set()
        for key in keys:
            data = await client.hgetall(key) or {}
            worker_id = str(key).removeprefix(WORKER_HEARTBEAT_PREFIX)
            spiders = [s for s in str(data.get("spiders", "")).split(",") if s]

            spider_task_ids: list[tuple[str, list[int]]] = []
            for spider_name in spiders:
                task_ids = sorted(
                    int(v)
                    for v in await client.smembers(
                        ACTIVE_TASK_KEY.format(spider_name=spider_name)
                    )
                )
                spider_task_ids.append((spider_name, task_ids))
                all_task_ids.update(task_ids)
            nodes.append((worker_id, data, spiders, spider_task_ids))

        # 批查任务状态（一次 WHERE id IN，替代逐 task get_by_id 的 N+1 轮询路径）
        tasks_map: dict[int, object] = {}
        if all_task_ids:
            tasks = await self.repo.get_by_ids(sorted(all_task_ids))
            tasks_map = {t.id: t for t in tasks}

        # 第二遍：用批查结果构建响应
        items: list[WorkerNodeResponse] = []
        for worker_id, data, spiders, spider_task_ids in nodes:
            active_tasks: list[WorkerActiveTask] = []
            for spider_name, task_ids in spider_task_ids:
                if task_ids:
                    for task_id in task_ids:
                        task = tasks_map.get(task_id)
                        active_tasks.append(
                            WorkerActiveTask(
                                spider_name=spider_name,
                                task_id=task_id,
                                status=task.status if task else None,
                            )
                        )
                else:
                    active_tasks.append(
                        WorkerActiveTask(spider_name=spider_name, task_id=None, status=None)
                    )

            items.append(
                WorkerNodeResponse(
                    worker_id=worker_id,
                    pid=int(data["pid"]) if data.get("pid", "").isdigit() else None,
                    spiders=spiders,
                    started_at=data.get("started_at"),
                    respawn_count=int(data.get("respawn_count", 0) or 0),
                    online=True,
                    active_tasks=active_tasks,
                )
            )
        items.sort(key=lambda n: n.worker_id)
        return WorkerNodeListResponse(total=len(items), items=items)

    # ------------------------------------------------------------------
    # 任务模板（C1）
    # ------------------------------------------------------------------
    async def list_templates(self) -> list[TaskTemplateResponse]:
        """获取所有任务模板"""
        logger.debug("获取任务模板列表")
        repo = TaskTemplateRepository(self.session)
        items = await repo.list_all()
        return [TaskTemplateResponse.model_validate(item) for item in items]

    async def create_template(self, payload: dict, created_by: int | None = None) -> TaskTemplateResponse:
        """创建任务模板（名称唯一性校验）"""
        logger.info(f"创建任务模板: name={payload.get('name')}")
        repo = TaskTemplateRepository(self.session)
        existing = await repo.get_by_name(payload["name"])
        if existing:
            raise BusinessException(f"模板名称 '{payload['name']}' 已存在")
        item = await repo.create(**payload, created_by=created_by)
        await self.session.commit()
        await self.session.refresh(item)
        return TaskTemplateResponse.model_validate(item)

    async def update_template(self, template_id: int, payload: dict) -> TaskTemplateResponse:
        """更新任务模板"""
        logger.info(f"更新任务模板: id={template_id}")
        repo = TaskTemplateRepository(self.session)
        item = await repo.get_by_id(template_id)
        if item is None:
            raise NotFoundException("任务模板")
        if "name" in payload and payload["name"] != item.name:
            existing = await repo.get_by_name(payload["name"])
            if existing:
                raise BusinessException(f"模板名称 '{payload['name']}' 已存在")
        updated = await repo.update(template_id, **payload)
        await self.session.commit()
        await self.session.refresh(updated)
        return TaskTemplateResponse.model_validate(updated)

    async def delete_template(self, template_id: int) -> dict:
        """删除任务模板"""
        logger.info(f"删除任务模板: id={template_id}")
        repo = TaskTemplateRepository(self.session)
        item = await repo.get_by_id(template_id)
        if item is None:
            raise NotFoundException("任务模板")
        await repo.delete(template_id)
        await self.session.commit()
        return {"id": template_id, "deleted": True}

    async def create_task_from_template(self, template_id: int) -> SpiderTaskResponse:
        """从模板创建并运行任务"""
        logger.info(f"从模板创建任务: template_id={template_id}")
        repo = TaskTemplateRepository(self.session)
        template = await repo.get_by_id(template_id)
        if template is None:
            raise NotFoundException("任务模板")
        # 局部构造（无状态）：避免 registry → task 顶层互相依赖
        from backend.services.spider_task_service import SpiderTaskService
        return await SpiderTaskService(self.session).enqueue(
            spider_name=template.spider_name,
            params=template.params,
            priority=template.priority or "normal",
        )
