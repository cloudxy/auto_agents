"""T-39（FR-103 / GWT-103.1…103.5 后端半）：采集方案定义字段可编辑 + 可删除

编辑面扩容（GWT-103.1）：定义要素按资产类型最小集——
- api 型：urls（入口地址）/ headers（既有 definition 字段集，源自 yml SPIDER_TYPES.api.fields）
- flow 型：流程字段落到注册来源 ai_plans（plan_json.flow + generated_params 再生），定义行镜像
- custom/web（代码型）：仅元信息，params 编辑拒绝（受限句「代码型爬虫请在源码中修改」）
- 名称/类型不可改（稳定标识，既有语义保持）
- 编辑校验：字段类型 / URL 形态（http/https）
- 在跑任务不受影响（GWT-103.3 编辑半）：任务 params 在入队时快照，编辑不回写存量任务；
  后续任务取新定义（enqueue 未带 params 时填定义参数）

删除（GWT-103.2/103.3）：未引用可删；被任务引用拒绝且中文句说明引用任务（既有口径钉住）。
越权（GWT-103.5）：经办（operator）可编辑/删除；只读 403；跨企业直打 404 同形且 B 行不变。
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from backend.services.spider_registry_service import SpiderRegistryService
from backend.services.spider_task_service import SpiderTaskService
from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.models.spider_definition import SpiderDefinition
from platform_core.models.spider_task import SpiderTask
from platform_core.schemas.spider import DefinitionUpdateMetaRequest

DEFS_URL = "/api/v1/spiders/definitions"
API_PARAMS = {"urls": ["https://new.example.com/api"], "headers": {"Authorization": "Bearer t"}}


def _registry_service() -> SpiderRegistryService:
    """注册表域桩（同 test_spider_datacenter_crud 口径）"""
    svc = SpiderRegistryService.__new__(SpiderRegistryService)
    svc.session = MagicMock()
    svc.session.commit = AsyncMock()
    svc.session.refresh = AsyncMock()
    svc.repo = MagicMock()
    return svc


def _definition(**overrides) -> MagicMock:
    """可被 SpiderDefinitionResponse.model_validate 的定义实体桩"""
    d = MagicMock(
        id=5, title="方案", type="api", description="", enabled=True,
        source="manual", params=None, created_at=None, updated_at=None,
    )
    d.name = overrides.pop("name", "openweather")
    for k, v in overrides.items():
        setattr(d, k, v)
    return d


def _task(**overrides) -> MagicMock:
    defaults = dict(
        id=9, spider_name="openweather", status="pending", priority="normal",
        result_count=0, retry_count=0, error_message=None, params=None,
        created_at=None, updated_at=None, started_at=None, completed_at=None,
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


# ---------------- GWT-103.1 api 型：定义参数编辑 ----------------
class TestApiParamsEdit:
    @pytest.mark.asyncio
    async def test_api_params_saved_and_echoed(self):
        """api 型 urls/headers 保存成功；响应回显新值（再次打开显示新值）"""
        svc = _registry_service()
        updated = _definition(params=API_PARAMS)
        repo = MagicMock()
        repo.get_by_name = AsyncMock(return_value=_definition())
        repo.update = AsyncMock(return_value=updated)

        with patch("backend.services.spider_registry_service.SpiderDefinitionRepository", return_value=repo):
            resp = await svc.update_definition_meta(
                "openweather", DefinitionUpdateMetaRequest(params=API_PARAMS)
            )

        kwargs = repo.update.call_args.kwargs
        assert kwargs["params"] == API_PARAMS          # 定义参数落库
        assert resp.params == API_PARAMS               # 响应回显
        svc.session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_api_params_rejects_bad_url_shape(self):
        """URL 形态校验：非 http(s) 入口地址拒绝"""
        svc = _registry_service()
        repo = MagicMock()
        repo.get_by_name = AsyncMock(return_value=_definition())

        with patch("backend.services.spider_registry_service.SpiderDefinitionRepository", return_value=repo):
            with pytest.raises(BusinessException):
                await svc.update_definition_meta(
                    "openweather",
                    DefinitionUpdateMetaRequest(params={"urls": ["ftp://bad.example/x"]}),
                )
        repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_params_rejects_unknown_field(self):
        """字段集校验：api 型只认 yml 表单既有字段（urls/headers），未知字段拒绝"""
        svc = _registry_service()
        repo = MagicMock()
        repo.get_by_name = AsyncMock(return_value=_definition())

        with patch("backend.services.spider_registry_service.SpiderDefinitionRepository", return_value=repo):
            with pytest.raises(BusinessException):
                await svc.update_definition_meta(
                    "openweather",
                    DefinitionUpdateMetaRequest(
                        params={"urls": ["https://ok.example"], "bogus": 1}
                    ),
                )
        repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_params_rejects_wrong_types(self):
        """字段类型校验：urls 必须是非空字符串列表、headers 必须是字符串字典"""
        svc = _registry_service()
        repo = MagicMock()
        repo.get_by_name = AsyncMock(return_value=_definition())

        with patch("backend.services.spider_registry_service.SpiderDefinitionRepository", return_value=repo):
            with pytest.raises(BusinessException):
                await svc.update_definition_meta(
                    "openweather",
                    DefinitionUpdateMetaRequest(params={"urls": "https://not-a-list"}),
                )
            with pytest.raises(BusinessException):
                await svc.update_definition_meta(
                    "openweather",
                    DefinitionUpdateMetaRequest(params={"headers": ["not-dict"]}),
                )
        repo.update.assert_not_called()


# ---------------- GWT-103.1 flow 型：流程字段编辑（落注册来源计划） ----------------
FLOW_PARAMS = {
    "urls": ["https://new.example.com/list"],
    "selectors": [{"name": "title", "type": "css", "expr": ".title"}],
}


def _flow_plan(name: str = "ai_site_7") -> MagicMock:
    return MagicMock(
        id=3, target_url="https://old.example.com", status="registered",
        plan_json={
            "flow": {"selectors": [{"name": "old", "type": "css", "expr": ".old"}]},
            "registered_definition": name,
            "test_history": [{"iteration": 1, "passed": True}],
        },
        generated_params={"urls": ["https://old.example.com"]},
        tenant_id=1, created_by="op", error_message=None,
        test_task_id=11, iteration_count=1,
        created_at=None, updated_at=None,
    )


class TestFlowParamsEdit:
    @pytest.mark.asyncio
    async def test_flow_edit_updates_plan_and_mirrors(self):
        """flow 型：plan_json.flow 更新 + generated_params 再生 + 定义行镜像（后续任务取新定义）"""
        svc = _registry_service()
        definition = _definition(name="ai_site_7", type="flow", source="ai_generated")
        def_repo = MagicMock()
        def_repo.get_by_name = AsyncMock(return_value=definition)
        def_repo.update = AsyncMock(return_value=_definition(
            name="ai_site_7", type="flow", params={"urls": FLOW_PARAMS["urls"]}
        ))
        plan = _flow_plan()
        plan_repo = MagicMock()
        plan_repo.get_by_registered_definition = AsyncMock(return_value=plan)
        plan_repo.update = AsyncMock(return_value=plan)

        with (
            patch("backend.services.spider_registry_service.SpiderDefinitionRepository", return_value=def_repo),
            patch("backend.repositories.ai_plan_repository.AiPlanRepository", return_value=plan_repo),
        ):
            await svc.update_definition_meta(
                "ai_site_7", DefinitionUpdateMetaRequest(params=FLOW_PARAMS)
            )

        plan_kwargs = plan_repo.update.call_args.kwargs
        assert plan_kwargs["target_url"] == "https://new.example.com/list"  # 入口地址更新
        new_flow = plan_kwargs["plan_json"]["flow"]
        assert new_flow["selectors"][0]["name"] == "title"                  # 采集项更新
        assert plan_kwargs["plan_json"]["registered_definition"] == "ai_site_7"  # 关联保持
        generated = plan_kwargs["generated_params"]
        assert generated["urls"] == ["https://new.example.com/list"]        # 后续试采取新定义
        assert generated["selectors"] == [{"name": "title", "type": "css", "expr": ".title"}]
        # 定义行镜像 generated_params（enqueue 默认参数数据源）
        assert def_repo.update.call_args.kwargs["params"] == generated
        svc.session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_flow_edit_without_linked_plan_rejected(self):
        """flow 型但找不到注册来源计划 → 拒绝（不静默改定义行）"""
        svc = _registry_service()
        def_repo = MagicMock()
        def_repo.get_by_name = AsyncMock(
            return_value=_definition(name="ai_ghost_9", type="flow")
        )
        plan_repo = MagicMock()
        plan_repo.get_by_registered_definition = AsyncMock(return_value=None)

        with (
            patch("backend.services.spider_registry_service.SpiderDefinitionRepository", return_value=def_repo),
            patch("backend.repositories.ai_plan_repository.AiPlanRepository", return_value=plan_repo),
        ):
            with pytest.raises(BusinessException):
                await svc.update_definition_meta(
                    "ai_ghost_9", DefinitionUpdateMetaRequest(params=FLOW_PARAMS)
                )
        def_repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_flow_edit_invalid_selector_rejected(self):
        """流程字段校验：selectors 为空列表 → FlowConfig 校验拒绝"""
        svc = _registry_service()
        def_repo = MagicMock()
        def_repo.get_by_name = AsyncMock(
            return_value=_definition(name="ai_site_7", type="flow")
        )
        plan_repo = MagicMock()
        plan_repo.get_by_registered_definition = AsyncMock(return_value=_flow_plan())

        with (
            patch("backend.services.spider_registry_service.SpiderDefinitionRepository", return_value=def_repo),
            patch("backend.repositories.ai_plan_repository.AiPlanRepository", return_value=plan_repo),
        ):
            with pytest.raises(BusinessException):
                await svc.update_definition_meta(
                    "ai_site_7",
                    DefinitionUpdateMetaRequest(
                        params={"urls": ["https://new.example.com"], "selectors": []}
                    ),
                )


# ---------------- 代码型（custom/web）：仅元信息 ----------------
class TestCodeTypeLimited:
    @pytest.mark.parametrize("spider_type", ["custom", "web"])
    @pytest.mark.asyncio
    async def test_code_type_params_rejected_with_sentence(self, spider_type):
        """代码型仅元信息：params 编辑拒绝，可见句含「代码型爬虫请在源码中修改」"""
        svc = _registry_service()
        repo = MagicMock()
        repo.get_by_name = AsyncMock(return_value=_definition(type=spider_type))

        with patch("backend.services.spider_registry_service.SpiderDefinitionRepository", return_value=repo):
            with pytest.raises(BusinessException) as e:
                await svc.update_definition_meta(
                    "generic", DefinitionUpdateMetaRequest(params=API_PARAMS)
                )
        assert "代码型爬虫请在源码中修改" in str(e.value)
        repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_meta_only_edit_still_works_for_code_type(self):
        """代码型元信息（标题/描述）仍可编辑（既有行为不回退）"""
        svc = _registry_service()
        updated = _definition(type="custom", title="新标题")
        repo = MagicMock()
        repo.get_by_name = AsyncMock(return_value=_definition(type="custom"))
        repo.update = AsyncMock(return_value=updated)

        with patch("backend.services.spider_registry_service.SpiderDefinitionRepository", return_value=repo):
            resp = await svc.update_definition_meta(
                "generic", DefinitionUpdateMetaRequest(title="新标题")
            )
        assert resp.title == "新标题"
        assert "params" not in repo.update.call_args.kwargs


# ---------------- GWT-103.1 后续任务取新定义（enqueue 默认参数） ----------------
class TestEnqueueTakesDefinitionParams:
    def _task_service(self) -> SpiderTaskService:
        svc = SpiderTaskService.__new__(SpiderTaskService)
        svc.session = MagicMock()
        svc.session.commit = AsyncMock()
        svc.session.refresh = AsyncMock()
        svc.repo = MagicMock()
        svc.result_repo = MagicMock()
        svc.notifier = MagicMock()
        svc._check_enqueue_quota = AsyncMock()
        return svc

    async def _run_enqueue(self, svc, definition, params=None):
        repo = MagicMock()
        repo.get_by_name = AsyncMock(return_value=definition)
        fake_redis = AsyncMock()
        fake_redis.scard.return_value = 0
        svc.repo.create = AsyncMock(return_value=_task(id=50))

        with (
            patch("backend.services.spider_task_service.SpiderDefinitionRepository", return_value=repo),
            patch("backend.services.spider_task_service.get_async_redis", return_value=fake_redis),
            patch("backend.services.spider_task_service.settings") as fake_settings,
        ):
            fake_settings.get.return_value = 2
            await svc.enqueue("openweather", params=params, tenant_id=1)
        return svc.repo.create.call_args.kwargs

    @pytest.mark.asyncio
    async def test_enqueue_without_params_uses_definition_params(self):
        """未带 params 的入队取定义参数（方案编辑后，后续任务按新定义执行）"""
        svc = self._task_service()
        definition = _definition(enabled=True, params=API_PARAMS)

        kwargs = await self._run_enqueue(svc, definition)

        assert kwargs["params"] == json.dumps(API_PARAMS, ensure_ascii=False)

    @pytest.mark.asyncio
    async def test_explicit_params_win_over_definition(self):
        """显式 params 优先（任务级覆盖，既有行为不回退）"""
        svc = self._task_service()
        definition = _definition(enabled=True, params=API_PARAMS)
        explicit = '{"urls": ["https://explicit.example"]}'

        kwargs = await self._run_enqueue(svc, definition, params=explicit)

        assert kwargs["params"] == explicit


# ---------------- GWT-103.3 删除：被引用拒绝句说明引用任务 ----------------
class TestDeleteReferencedMessage:
    @pytest.mark.asyncio
    async def test_reject_message_names_tasks(self):
        """被引用拒绝句列出引用任务（中文说明引用它的任务）；方案保持"""
        svc = _registry_service()
        repo = MagicMock()
        repo.delete_if_unreferenced = AsyncMock(return_value=False)
        repo.get_by_name = AsyncMock(return_value=_definition())
        svc.repo.count_by_spider = AsyncMock(return_value=2)
        svc.repo.list_ids_by_spider = AsyncMock(return_value=[12, 15])

        with patch("backend.services.spider_registry_service.SpiderDefinitionRepository", return_value=repo):
            with pytest.raises(BusinessException) as e:
                await svc.delete_definition("openweather")

        assert "#12" in str(e.value) and "#15" in str(e.value)
        svc.session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unreferenced_delete_still_succeeds(self):
        """未引用可删（既有口径保持）"""
        svc = _registry_service()
        repo = MagicMock()
        repo.delete_if_unreferenced = AsyncMock(return_value=True)

        with patch("backend.services.spider_registry_service.SpiderDefinitionRepository", return_value=repo):
            result = await svc.delete_definition("openweather")

        assert result == {"name": "openweather", "deleted": True}

    @pytest.mark.asyncio
    async def test_missing_definition_404(self):
        svc = _registry_service()
        repo = MagicMock()
        repo.delete_if_unreferenced = AsyncMock(return_value=False)
        repo.get_by_name = AsyncMock(return_value=None)

        with patch("backend.services.spider_registry_service.SpiderDefinitionRepository", return_value=repo):
            with pytest.raises(NotFoundException):
                await svc.delete_definition("ghost")


# ---------------- 仓储契约：注册来源计划反查（JSON 路径） ----------------
class TestGetByRegisteredDefinition:
    def test_finds_latest_registered_plan(self, db_engine, db_session):
        """plan_json.registered_definition 反查注册来源计划（取 id 最新；无关联返回 None）"""
        from platform_core.models.ai_plan import AiPlan
        from backend.repositories.ai_plan_repository import AiPlanRepository

        async def _seed():
            async with db_session() as s:
                s.add_all([
                    AiPlan(target_url="https://old.example", status="registered",
                           plan_json={"registered_definition": "ai_site_7", "flow": {}}),
                    AiPlan(target_url="https://new.example", status="registered",
                           plan_json={"registered_definition": "ai_site_7", "flow": {}}),
                    AiPlan(target_url="https://other.example", status="registered",
                           plan_json={"registered_definition": "ai_other_1", "flow": {}}),
                ])
                await s.commit()

        asyncio.run(_seed())

        async def _fetch(name):
            async with db_session() as s:
                return await AiPlanRepository(s).get_by_registered_definition(name)

        plan = asyncio.run(_fetch("ai_site_7"))
        assert plan is not None and plan.target_url == "https://new.example"  # id 最新
        assert asyncio.run(_fetch("ghost")) is None


# ---------------- HTTP 面：经办可编辑/删除、只读 403、跨企业 404 ----------------
class TestHttpGuards:
    def _seed_definition(self, db_session, **overrides):
        async def _go():
            async with db_session() as s:
                row = SpiderDefinition(
                    name=overrides.get("name", "t39-api"),
                    title=overrides.get("title", "T39 API 方案"),
                    type=overrides.get("type", "api"),
                    tenant_id=overrides.get("tenant_id"),
                )
                s.add(row)
                await s.commit()
                return row.id

        return asyncio.run(_go())

    def _fetch_definitions(self, db_session, name):
        async def _go():
            async with db_session() as s:
                return (await s.execute(
                    select(SpiderDefinition).where(SpiderDefinition.name == name)
                )).scalars().all()

        return asyncio.run(_go())

    def test_operator_can_edit_params(self, db_client, operator_client, db_engine, db_session):
        """经办（operator）编辑 api 型定义参数成功且落库（GWT-103.1 Given=经办）"""
        self._seed_definition(db_session)
        resp = operator_client.patch(
            f"{DEFS_URL}/t39-api/meta", json={"params": API_PARAMS}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["params"] == API_PARAMS
        rows = self._fetch_definitions(db_session, "t39-api")
        assert rows[0].params == API_PARAMS

    def test_viewer_edit_rejected_403(self, db_client, viewer_client, db_engine, db_session):
        """只读直打编辑 → 403（GWT-103.5 / FR-89）"""
        self._seed_definition(db_session)
        resp = viewer_client.patch(
            f"{DEFS_URL}/t39-api/meta", json={"params": API_PARAMS}
        )
        assert resp.status_code == 403
        assert self._fetch_definitions(db_session, "t39-api")[0].params is None

    def test_viewer_delete_rejected_403(self, db_client, viewer_client, db_engine, db_session):
        """只读直打删除 → 403（GWT-103.5 / FR-89）"""
        self._seed_definition(db_session)
        assert viewer_client.delete(f"{DEFS_URL}/t39-api").status_code == 403
        assert len(self._fetch_definitions(db_session, "t39-api")) == 1

    def test_operator_can_delete_unreferenced(self, db_client, operator_client, db_engine, db_session):
        """经办删除未被引用方案 → 成功，从方案列表消失（GWT-103.2）"""
        self._seed_definition(db_session)
        resp = operator_client.delete(f"{DEFS_URL}/t39-api")
        assert resp.status_code == 200, resp.text
        assert self._fetch_definitions(db_session, "t39-api") == []

    def test_delete_referenced_rejected_lists_tasks(
        self, db_client, admin_client, db_engine, db_session
    ):
        """被任务引用 → 400 拒绝且句中说明引用任务；方案保持（GWT-103.3）"""
        async def _go():
            async with db_session() as s:
                s.add(SpiderDefinition(name="t39-ref", title="被引用方案", tenant_id=1))
                s.add(SpiderTask(spider_name="t39-ref", status="running", tenant_id=1, params="{}"))
                await s.commit()

        asyncio.run(_go())
        resp = admin_client.delete(f"{DEFS_URL}/t39-ref")
        assert resp.status_code == 400, resp.text
        message = resp.json()["message"]
        assert "历史任务" in message and "#" in message
        assert len(self._fetch_definitions(db_session, "t39-ref")) == 1

    def test_cross_tenant_edit_404_and_target_unchanged(
        self, db_client, db_engine, db_session
    ):
        """企业 A 经办直打企业 B 方案编辑 → 404 同形拒绝；B 的方案不变（GWT-103.5）"""
        from conftest import make_tenant_owner_headers

        _, tid_b = make_tenant_owner_headers(db_session, slug="t39-b")
        self._seed_definition(db_session, name="t39-b-def", tenant_id=tid_b)

        headers_a, _ = make_tenant_owner_headers(db_session, slug="t39-a")
        resp = db_client.patch(
            f"{DEFS_URL}/t39-b-def/meta", headers=headers_a, json={"params": API_PARAMS}
        )
        assert resp.status_code == 404
        rows = self._fetch_definitions(db_session, "t39-b-def")
        assert len(rows) == 1 and rows[0].params is None   # B 的方案不变

    def test_cross_tenant_delete_404_and_target_kept(
        self, db_client, db_engine, db_session
    ):
        """企业 A 经办直打企业 B 方案删除 → 404 同形拒绝；B 的方案不变（GWT-103.5）"""
        from conftest import make_tenant_owner_headers

        _, tid_b = make_tenant_owner_headers(db_session, slug="t39-b2")
        self._seed_definition(db_session, name="t39-b2-def", tenant_id=tid_b)

        headers_a, _ = make_tenant_owner_headers(db_session, slug="t39-a2")
        resp = db_client.delete(f"{DEFS_URL}/t39-b2-def", headers=headers_a)
        assert resp.status_code == 404
        assert len(self._fetch_definitions(db_session, "t39-b2-def")) == 1


# ---------------- GWT-103.3 编辑半：在跑任务不受影响 ----------------
class TestRunningTaskUnaffected:
    def test_edit_does_not_touch_existing_tasks(self, db_client, operator_client, db_engine, db_session):
        """编辑定义参数后：存量任务 params 不变、状态不变（编辑不中断运行中任务）"""
        async def _seed():
            async with db_session() as s:
                s.add(SpiderDefinition(
                    name="t39-run", title="运行中方案", type="api", tenant_id=1,
                ))
                s.add(SpiderTask(
                    spider_name="t39-run", status="running", tenant_id=1,
                    params='{"urls": ["https://old.example.com"]}',
                ))
                await s.commit()

        asyncio.run(_seed())
        resp = operator_client.patch(
            f"{DEFS_URL}/t39-run/meta", json={"params": API_PARAMS}
        )
        assert resp.status_code == 200, resp.text

        async def _fetch_task():
            async with db_session() as s:
                return (await s.execute(
                    select(SpiderTask).where(SpiderTask.spider_name == "t39-run")
                )).scalars().one()

        task = asyncio.run(_fetch_task())
        assert task.params == '{"urls": ["https://old.example.com"]}'  # 任务快照不变
        assert task.status == "running"                                # 不中断
