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
from urllib.parse import urlparse

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.spider_definition_repository import SpiderDefinitionRepository
from backend.repositories.spider_task_repository import SpiderTaskRepository
from backend.repositories.task_template_repository import TaskTemplateRepository
from backend.services.spider_common import (
    _INTERNAL_SPIDERS,
    _SPIDERS_DIR,
    require_enqueue_tenant,
)
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

        # 爬虫清单：DB 优先；查询失败回退配置种子（成功而可见方案为 0 → 空清单，
        # 不用种子充数——GWT-103.4/104.3 空态可达）
        spiders: list[SpiderInfo] | None = None
        try:
            definitions = await SpiderDefinitionRepository(self.session).list_enabled()
            # T-41 / FR-104：demo/收割器/flow 引擎伪爬虫不下发（只滤视图，行不动）
            definitions = [d for d in definitions if d.name not in _INTERNAL_SPIDERS]
            spiders = [
                SpiderInfo(
                    name=d.name,
                    title=d.title,
                    type=d.type,
                    description=d.description or "",
                    params=d.params if isinstance(d.params, dict) else None,
                )
                for d in definitions
            ]
        except Exception as e:  # noqa: BLE001
            logger.warning(f"注册表 DB 读取失败，回退配置: {e}")

        if spiders is None:
            spiders = []
            for name, scfg in spiders_cfg.items():
                # 回退种子同口径过滤（GWT-104.1：demo/内部项不因兜底混入）
                if name.startswith("_") or name in _INTERNAL_SPIDERS:
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
        """已登记代码爬虫文件清单（T-41 / FR-104：未登记源码文件与内部项不并入方案视图；不删文件）"""
        logger.info("扫描已登记代码爬虫文件清单（方案视图纯净口径）")
        definitions: dict = {}
        try:
            defs = await SpiderDefinitionRepository(self.session).get_all(limit=500)
            definitions = {d.name: d for d in defs}
        except Exception as e:  # noqa: BLE001
            logger.warning(f"爬虫定义读取失败，文件清单收敛为空（不并入方案视图）: {e}")

        items: list[SpiderFileResponse] = []
        spiders_dir = _SPIDERS_DIR
        if os.path.isdir(spiders_dir):
            for fname in sorted(os.listdir(spiders_dir)):
                if not fname.endswith(".py") or fname == "__init__.py":
                    continue
                name = fname[: -len(".py")]
                definition = definitions.get(name)
                # GWT-104.1：无登记行不并入；内部/演示项（_INTERNAL_SPIDERS）同滤
                if definition is None or name in _INTERNAL_SPIDERS:
                    continue
                path = os.path.join(spiders_dir, fname)
                try:
                    size = os.path.getsize(path)
                except OSError:
                    size = 0
                items.append(
                    SpiderFileResponse(
                        name=name,
                        file=f"scrapy/spiders/{fname}",
                        size_bytes=size,
                        registered=True,
                        enabled=definition.enabled,
                        title=definition.title,
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
        """编辑采集方案（元信息 + 定义参数，FR-103 / GWT-103.1）

        定义参数按类型分派：api 型校验后落定义行；flow 型落注册来源 ai_plans
        （plan_json.flow + generated_params 再生）并镜像到定义行；代码型
        （web/custom）仅元信息，params 编辑拒绝。名称/类型不可改（稳定标识，
        既有语义保持）。存量任务 params 在入队时已快照，编辑不影响在跑任务。
        """
        logger.info(
            f"编辑采集方案: name={name}, fields={sorted(payload.model_dump(exclude_unset=True).keys())}"
        )
        repo = SpiderDefinitionRepository(self.session)
        definition = await repo.get_by_name(name)
        if definition is None:
            raise NotFoundException("爬虫定义")
        set_fields = payload.model_dump(exclude_unset=True)
        changes = {k: v for k, v in set_fields.items() if k != "params" and v is not None}
        if set_fields.get("params") is not None:
            changes["params"] = await self._resolve_definition_params(
                definition, set_fields["params"]
            )
        if not changes:
            return SpiderDefinitionResponse.model_validate(definition)
        updated = await repo.update(definition.id, **changes)
        await self.session.commit()
        await self.session.refresh(updated)
        return SpiderDefinitionResponse.model_validate(updated)

    # ------------------------------------------------------------------
    # 定义参数编辑分派（T-39 / FR-103：按资产类型最小集）
    # ------------------------------------------------------------------
    async def _resolve_definition_params(self, definition, params: dict) -> dict:
        """定义参数分派：api 型校验直存；flow 型落计划并镜像；代码型拒绝"""
        if definition.type == "flow":
            return await self._flow_definition_params(definition, params)
        if definition.type == "api":
            return self._api_definition_params(params)
        raise BusinessException(
            f"爬虫 {definition.name} 为代码型爬虫，仅支持编辑标题与描述；"
            f"代码型爬虫请在源码中修改"
        )

    def _api_definition_params(self, params: dict) -> dict:
        """api 型定义参数校验（字段集 = yml SPIDER_TYPES.api.fields；URL 形态）"""
        allowed = self._api_param_keys()
        unknown = sorted(k for k in params if k not in allowed)
        if unknown:
            raise BusinessException(
                f"定义参数不支持的参数字段: {'、'.join(unknown)}"
                f"（api 型可编辑字段: {'、'.join(allowed)}）"
            )
        normalized: dict = {}
        if "urls" in params:
            normalized["urls"] = self._require_http_urls(params["urls"])
        if "headers" in params:
            headers = params["headers"]
            if not isinstance(headers, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in headers.items()
            ):
                raise BusinessException("定义参数 headers 必须是字符串键值的 JSON 对象")
            normalized["headers"] = headers
        return normalized

    @staticmethod
    def _api_param_keys() -> tuple:
        """api 型可编辑字段集（yml SPIDER_TYPES.api.fields 的 name 集合）"""
        types_cfg = settings.get("SPIDER_TYPES", {}) or {}
        fields = (types_cfg.get("api") or {}).get("fields") or []
        names = tuple(
            f.get("name") for f in fields if isinstance(f, dict) and f.get("name")
        )
        return names or ("urls", "headers")

    @staticmethod
    def _require_http_urls(raw: object) -> list:
        """入口地址形态校验：非空字符串列表，每条为 http(s) URL"""
        if isinstance(raw, str) or not isinstance(raw, (list, tuple)) or not raw:
            raise BusinessException("入口地址 urls 必须是非空字符串列表")
        urls = []
        for item in raw:
            if not isinstance(item, str):
                raise BusinessException("入口地址 urls 必须是非空字符串列表")
            parsed = urlparse(item)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise BusinessException(f"入口地址必须是 http(s) URL: {item}")
            urls.append(item)
        return urls

    async def _flow_definition_params(self, definition, params: dict) -> dict:
        """flow 型：流程字段落到注册来源 ai_plans，返回镜像参数（GWT-103.1）

        plan_json.flow 更新 + generated_params 按新流程再生（后续试采取新定义）；
        入口地址（urls[0]）同步为计划 target_url。局部 import 断开
        ai_planner → spider_service → 本模块 的 import 环（同 create_task_from_template 先例）。
        """
        from backend.repositories.ai_plan_repository import AiPlanRepository
        from backend.services.ai_planner.prompting import _build_generated_params
        from platform_core.schemas.ai_plan import FlowConfig

        plan_repo = AiPlanRepository(self.session)
        plan = await plan_repo.get_by_registered_definition(definition.name)
        if plan is None:
            raise BusinessException(
                f"流程方案 {definition.name} 未关联 AI 采集计划，无法编辑流程参数"
            )
        plan_id = int(plan.id)  # commit 前捕获（P-BE-01）
        target_url = str(plan.target_url)
        if params.get("urls") is not None:
            target_url = self._require_http_urls(params["urls"])[0]
        try:
            flow = FlowConfig.model_validate(params)
        except ValidationError as e:
            first = e.errors()[0]
            field = ".".join(str(part) for part in first.get("loc", ()))
            raise BusinessException(f"流程参数不合法（{field}）: {first.get('msg')}")
        plan_json = dict(plan.plan_json or {})
        plan_json["flow"] = flow.model_dump()
        generated = _build_generated_params(target_url, flow)
        await plan_repo.update(
            plan_id, target_url=target_url, plan_json=plan_json,
            generated_params=generated,
        )
        return generated

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
        task_ids = await self.repo.list_ids_by_spider(name, limit=5)
        refs = "、".join(f"#{tid}" for tid in task_ids)
        hint = f"（如 {refs}）" if refs else ""
        raise BusinessException(
            f"爬虫 {name} 存在 {task_count} 条历史任务记录{hint}，拒绝删除；"
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

    async def create_template(
        self, payload: dict, created_by: str | None = None, tenant_id: int | None = None,
    ) -> TaskTemplateResponse:
        """创建任务模板（名称唯一性校验）"""
        logger.info(f"创建任务模板: name={payload.get('name')}")
        owner_id = require_enqueue_tenant(tenant_id)
        repo = TaskTemplateRepository(self.session)
        existing = await repo.get_by_name(payload["name"])
        if existing:
            raise BusinessException(f"模板名称 '{payload['name']}' 已存在")
        data = {k: v for k, v in payload.items() if k != "tenant_id"}
        item = await repo.create(**data, created_by=created_by, tenant_id=owner_id)
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

    async def create_task_from_template(
        self, template_id: int, tenant_id: int | None = None,
    ) -> SpiderTaskResponse:
        """从模板创建并运行任务"""
        logger.info(f"从模板创建任务: template_id={template_id}")
        owner_id = require_enqueue_tenant(tenant_id)
        repo = TaskTemplateRepository(self.session)
        template = await repo.get_by_id(template_id)
        if template is None:
            raise NotFoundException("任务模板")
        tmpl_tid = getattr(template, "tenant_id", None)
        try:
            tmpl_owner = int(tmpl_tid) if tmpl_tid is not None else None
        except (TypeError, ValueError):
            tmpl_owner = None
        if tmpl_owner != owner_id:
            raise NotFoundException("任务模板")
        # 局部构造（无状态）：避免 registry → task 顶层互相依赖
        from backend.services.spider_task_service import SpiderTaskService
        return await SpiderTaskService(self.session).enqueue(
            spider_name=template.spider_name,
            params=template.params,
            priority=template.priority or "normal",
            tenant_id=owner_id,
        )
