"""AI 智能采集核心单测（规划 / 试采自动修复 / 注册 / FlowConfig 契约 / API 权限）

约定：不连真实 MySQL/Redis，Repository/SpiderService 用 AsyncMock/MagicMock 桩；
LLM 调用 mock AiPlannerService._llm_chat；enqueue mock SpiderService 实例；
试采终态轮询数据源 mock _read_task_snapshot（独立短事务 session，不连 DB）。
patch 点：backend.services.ai_planner_service.<name>。
覆盖：
- 规划：成功落 plan_json/generated_params（html_snippet 优先不抓网页）/ 无 snippet 抓取 /
  FlowConfig 校验失败置 failed / LLM 未启用明确报错
- 试采：通过保持 testing 可注册 / 零结果触发自动修复迭代 / 迭代耗尽置 failed
- 注册：试采通过后注册 source=ai_generated / 未通过拒绝 / 已注册拒绝
- FlowConfig：表达式白名单校验（regex 编译 / xpath 前缀 / XSS 片段 / filters 正则）
- LLM chat：4xx 不重试 / 5xx 重试后成功
- API：端点权限（admin/operator/viewer）+ 快照端点
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import ValidationError

from backend.app.api.deps import CurrentUser, require_admin, require_operator
from backend.services.ai_planner_service import (
    AiPlannerService,
    _TaskSnapshot,
    _derive_spider_name,
    _fetch_html,
    _run_plan_bg,
    reconcile_interrupted_plans,
)
from platform_core.exceptions import AuthorizationException, BusinessException, NotFoundException
from platform_core.schemas.ai_plan import (
    AiPlanCreate,
    AiPlanResponse,
    FlowConfig,
    validate_selector_expr,
)
from platform_core.schemas.spider import TaskQualityReportResponse
from stubs import fake_settings as _fake_settings  # 共享桩（唯一定义处见 stubs.py）

# 合法 LLM 输出（与 flow_generic 契约对齐）
GOOD_LLM_JSON = json.dumps({
    "selectors": [{"name": "title", "type": "css", "expr": "h1::text"}],
    "pagination": {"selector": "a.next", "type": "css", "max_pages": 2},
    "detail": None,
    "filters": [],
})

_FLOW = {
    "selectors": [{"name": "title", "type": "css", "expr": "h1::text"}],
    "pagination": {"selector": "a.next", "type": "css", "max_pages": 2},
}
_GENERATED = {"urls": ["https://example.com/list"], "selectors": _FLOW["selectors"],
              "pagination": _FLOW["pagination"]}
_HISTORY_PASS = [{"iteration": 0, "task_id": 9, "status": "completed",
                  "result_count": 3, "passed": True, "reason": "ok"}]


def _plan(**overrides) -> MagicMock:
    """可被 AiPlanResponse.model_validate 的计划实体桩"""
    defaults = dict(
        id=1, target_url="https://example.com/list", status="draft",
        plan_json=None, generated_params=None, test_task_id=None,
        iteration_count=0, error_message=None, created_by="admin",
        created_at=None, updated_at=None,
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


def _service() -> AiPlannerService:
    svc = AiPlannerService.__new__(AiPlannerService)
    svc.session = MagicMock()
    svc.session.commit = AsyncMock()
    svc.session.refresh = AsyncMock()
    svc.session.rollback = AsyncMock()  # m3：_fail 现在会先回滚再置 failed
    svc.repo = MagicMock()
    for _method in ("get_by_id", "update_status", "update", "delete", "count",
                    "list_plans", "create", "claim_status"):
        setattr(svc.repo, _method, AsyncMock())
    svc.repo.claim_status.return_value = True  # 默认抢断成功
    return svc


def _snapshot(task_id: int = 9, status: str = "completed", result_count: int = 3,
              error_message: str | None = None) -> _TaskSnapshot:
    """试采任务快照桩（_read_task_snapshot 的 patch 返回值，终态轮询数据源）"""
    return _TaskSnapshot(task_id=task_id, status=status,
                         result_count=result_count, error_message=error_message)


def _spider_cls(result_count: int = 3,
                quality_avg: float | None = 90.0) -> MagicMock:
    """patch 后的 SpiderService 类：enqueue + get_task_quality
    （终态轮询数据源 _read_task_snapshot 由各测试单独 patch）"""
    spider = MagicMock()
    spider.enqueue = AsyncMock(side_effect=[
        MagicMock(id=9 + i, status="pending") for i in range(5)
    ])
    spider.get_task_quality = AsyncMock(return_value=TaskQualityReportResponse(
        task_id=9, avg_score=quality_avg, total_items=result_count,
    ))
    return spider


# ---------------- 规划 ----------------
class TestExecutePlan:
    @pytest.mark.asyncio
    async def test_plan_success_persists_flow(self):
        """规划成功：plan_json 含 flow/html_sample，generated_params 按 flow 契约组装"""
        svc = _service()
        snippet = "<html><body><h1>标题</h1></body></html>"
        svc.repo.get_by_id = AsyncMock(return_value=_plan(plan_json={"html_snippet": snippet}))
        svc._llm_chat = AsyncMock(return_value=GOOD_LLM_JSON)

        await svc._execute_plan(1)

        svc._llm_chat.assert_awaited_once()
        statuses = [c.args[1] for c in svc.repo.update_status.await_args_list]
        assert statuses[0] == "planning" and statuses[-1] == "draft"  # 状态机：planning → draft
        kwargs = svc.repo.update.await_args.kwargs
        assert kwargs["generated_params"]["urls"] == ["https://example.com/list"]
        assert kwargs["generated_params"]["selectors"][0]["name"] == "title"
        assert kwargs["generated_params"]["pagination"]["max_pages"] == 2
        assert kwargs["plan_json"]["flow"]["selectors"][0]["type"] == "css"
        assert "html_sample" in kwargs["plan_json"]
        assert kwargs["plan_json"]["test_history"] == []

    @pytest.mark.asyncio
    async def test_plan_fetches_html_when_no_snippet(self):
        """无预置片段时在线抓取目标页（单页 10s 超时语义在 _fetch_html 内）"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_plan(plan_json=None))
        svc._llm_chat = AsyncMock(return_value=GOOD_LLM_JSON)

        with patch("backend.services.ai_planner_service._fetch_html",
                   new=AsyncMock(return_value="<html><body>page</body></html>")) as fh:
            await svc._execute_plan(1)

        fh.assert_awaited_once_with("https://example.com/list")
        user_content = svc._llm_chat.await_args.args[0][1]["content"]
        assert "https://example.com/list" in user_content and "page" in user_content

    @pytest.mark.asyncio
    async def test_plan_invalid_flow_marks_failed(self):
        """LLM 产出非法 flow（selectors 空）→ FlowConfig 校验失败置 failed"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_plan(plan_json={"html_snippet": "<html/>"}))
        svc._llm_chat = AsyncMock(return_value='{"selectors": []}')

        await svc._execute_plan(1)

        last = svc.repo.update_status.await_args_list[-1]
        assert last.args[1] == "failed"
        assert "校验失败" in last.kwargs["error_message"]
        svc.repo.update.assert_not_called()  # 校验失败不落规划产物

    @pytest.mark.asyncio
    async def test_plan_missing_raises(self):
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(NotFoundException):
            await svc._execute_plan(999)


# ---------------- LLM 未启用 / 配置 ----------------
class TestLlmChat:
    @pytest.mark.asyncio
    async def test_llm_disabled_raises_business_exception(self):
        """LLM.ENABLED=false（测试环境默认）→ 明确业务异常，测试环境友好"""
        svc = _service()
        with pytest.raises(BusinessException) as ei:
            await svc._llm_chat([{"role": "user", "content": "hi"}])
        assert "未启用" in str(ei.value)

    @pytest.mark.asyncio
    async def test_llm_missing_config_raises(self):
        svc = _service()
        with patch("backend.services.ai_planner_service.settings",
                   _fake_settings(**{"LLM.ENABLED": True, "LLM.BASE_URL": "", "LLM.MODEL": ""})):
            with pytest.raises(BusinessException) as ei:
                await svc._llm_chat([{"role": "user", "content": "hi"}])
        assert "配置不完整" in str(ei.value)

    @pytest.mark.asyncio
    async def test_llm_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        svc = _service()
        cfg = _fake_settings(**{"LLM.ENABLED": True, "LLM.BASE_URL": "http://llm.test/v1",
                                "LLM.MODEL": "m", "LLM.API_KEY": ""})
        with patch("backend.services.ai_planner_service.settings", cfg):
            with pytest.raises(BusinessException) as ei:
                await svc._llm_chat([{"role": "user", "content": "hi"}])
        assert "LLM_API_KEY" in str(ei.value)

    @pytest.mark.asyncio
    async def test_llm_4xx_no_retry(self, monkeypatch):
        """4xx（非 429）请求被拒绝：不重试直接抛业务异常"""
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        svc = _service()
        cfg = _fake_settings(**{"LLM.ENABLED": True, "LLM.BASE_URL": "http://llm.test/v1",
                                "LLM.MODEL": "m", "LLM.MAX_RETRIES": 3})
        response = MagicMock(status_code=401)
        error = httpx.HTTPStatusError("401", request=MagicMock(), response=response)
        client = MagicMock()
        client.post = AsyncMock(side_effect=error)
        client_cls = MagicMock()
        client_cls.return_value = AsyncMock()
        client_cls.return_value.__aenter__.return_value = client
        client_cls.return_value.__aexit__.return_value = False

        with patch("backend.services.ai_planner_service.settings", cfg), \
             patch("backend.services.ai_planner_service.httpx.AsyncClient", client_cls):
            with pytest.raises(BusinessException):
                await svc._llm_chat([{"role": "user", "content": "hi"}])
        assert client.post.await_count == 1  # 未重试

    @pytest.mark.asyncio
    async def test_llm_retry_then_success(self, monkeypatch):
        """网络故障指数退避重试后成功，并累计 token 用量"""
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        svc = _service()
        cfg = _fake_settings(**{"LLM.ENABLED": True, "LLM.BASE_URL": "http://llm.test/v1",
                                "LLM.MODEL": "m", "LLM.MAX_RETRIES": 3,
                                "LLM.MAX_TOKENS_BUDGET": 1000})
        ok_response = MagicMock()
        ok_response.json.return_value = {
            "choices": [{"message": {"content": GOOD_LLM_JSON}}],
            "usage": {"total_tokens": 42},
        }
        client = MagicMock()
        client.post = AsyncMock(side_effect=[httpx.ConnectError("boom"), ok_response])
        client_cls = MagicMock()
        client_cls.return_value = AsyncMock()
        client_cls.return_value.__aenter__.return_value = client
        client_cls.return_value.__aexit__.return_value = False

        with patch("backend.services.ai_planner_service.settings", cfg), \
             patch("backend.services.ai_planner_service.httpx.AsyncClient", client_cls), \
             patch("asyncio.sleep", new=AsyncMock()):
            result = await svc._llm_chat([{"role": "user", "content": "hi"}])
        assert result == GOOD_LLM_JSON
        assert client.post.await_count == 2


# ---------------- 试采（含自动修复迭代） ----------------
class TestExecuteTest:
    @pytest.mark.asyncio
    @patch("backend.services.ai_planner_service.SpiderService")
    async def test_test_success_keeps_testing(self, spider_cls):
        """试采通过：flow_generic 低优先级入队，保持 testing（可注册），不触发修复"""
        svc = _service()
        plan = _plan(status="draft", generated_params=dict(_GENERATED),
                     plan_json={"flow": _FLOW, "test_history": []})
        svc.repo.get_by_id = AsyncMock(return_value=plan)
        svc._llm_chat = AsyncMock()
        spider_cls.return_value = _spider_cls(result_count=3)

        with patch("backend.services.ai_planner_service._read_task_snapshot",
                   AsyncMock(return_value=_snapshot(status="completed", result_count=3))):
            await svc._execute_test(1)

        spider = spider_cls.return_value
        enqueue_kwargs = spider.enqueue.await_args.kwargs
        assert enqueue_kwargs["spider_name"] == "flow_generic"
        assert enqueue_kwargs["priority"] == "low"
        assert json.loads(enqueue_kwargs["params"])["urls"] == ["https://example.com/list"]
        assert svc.repo.update_status.await_args_list[0].args[1] == "testing"
        history_updates = [c for c in svc.repo.update.await_args_list if "plan_json" in c.kwargs]
        assert history_updates[-1].kwargs["plan_json"]["test_history"][0]["passed"] is True
        svc._llm_chat.assert_not_awaited()  # 一次通过无需修复

    @pytest.mark.asyncio
    @patch("backend.services.ai_planner_service.SpiderService")
    async def test_zero_results_triggers_repair_iteration(self, spider_cls):
        """零结果 → 回喂 LLM 修正 → iteration_count+1 → 重新入队试采并通过"""
        svc = _service()
        plan = _plan(status="draft", generated_params=dict(_GENERATED),
                     plan_json={"flow": _FLOW, "test_history": [], "html_sample": "<html/>"})
        svc.repo.get_by_id = AsyncMock(return_value=plan)
        svc._llm_chat = AsyncMock(return_value=GOOD_LLM_JSON)
        spider = MagicMock()
        spider.enqueue = AsyncMock(side_effect=[
            MagicMock(id=9, status="pending"), MagicMock(id=10, status="pending"),
        ])
        spider.get_task_quality = AsyncMock(return_value=TaskQualityReportResponse(
            task_id=10, avg_score=88.0, total_items=4))
        spider_cls.return_value = spider

        snapshots = [
            _snapshot(task_id=9, result_count=0),
            _snapshot(task_id=10, result_count=4),
        ]
        with patch("backend.services.ai_planner_service._read_task_snapshot",
                   AsyncMock(side_effect=snapshots)):
            await svc._execute_test(1)

        assert spider.enqueue.await_count == 2          # 修复后重新入队
        assert svc._llm_chat.await_count == 1           # 一次修复迭代
        iter_updates = [c for c in svc.repo.update.await_args_list
                        if "iteration_count" in c.kwargs]
        assert iter_updates[0].kwargs["iteration_count"] == 1
        history_updates = [c for c in svc.repo.update.await_args_list if "plan_json" in c.kwargs]
        history = history_updates[-1].kwargs["plan_json"]["test_history"]
        assert len(history) == 2 and history[0]["passed"] is False and history[1]["passed"] is True

    @pytest.mark.asyncio
    @patch("backend.services.ai_planner_service.SpiderService")
    async def test_iterations_exhausted_marks_failed(self, spider_cls):
        """迭代耗尽（MAX_ITERATIONS=1 后仍零结果）→ failed + error_message"""
        svc = _service()
        plan = _plan(status="draft", generated_params=dict(_GENERATED),
                     plan_json={"flow": _FLOW, "test_history": [], "html_sample": "<html/>"})
        svc.repo.get_by_id = AsyncMock(return_value=plan)
        svc._llm_chat = AsyncMock(return_value=GOOD_LLM_JSON)
        spider = MagicMock()
        spider.enqueue = AsyncMock(side_effect=[
            MagicMock(id=9, status="pending"), MagicMock(id=10, status="pending"),
        ])
        spider.get_task_quality = AsyncMock(return_value=TaskQualityReportResponse(task_id=9))
        spider_cls.return_value = spider

        with patch("backend.services.ai_planner_service.settings",
                   _fake_settings(**{"LLM.MAX_ITERATIONS": 1})), \
             patch("backend.services.ai_planner_service._read_task_snapshot",
                   AsyncMock(return_value=_snapshot(task_id=9, result_count=0))):
            await svc._execute_test(1)

        assert spider.enqueue.await_count == 2
        last = svc.repo.update_status.await_args_list[-1]
        assert last.args[1] == "failed"
        assert "已达上限" in last.kwargs["error_message"]


# ---------------- 注册 ----------------
class TestRegister:
    @pytest.mark.asyncio
    @patch("backend.services.ai_planner_service.SpiderService")
    async def test_register_success_marks_ai_generated(self, spider_cls):
        """试采通过后注册：create_definition(source=ai_generated, type=flow)"""
        svc = _service()
        registered = _plan(status="registered",
                           plan_json={"flow": _FLOW, "test_history": _HISTORY_PASS,
                                      "registered_definition": "ai_example_com_1"},
                           generated_params=dict(_GENERATED), test_task_id=9)
        svc.repo.get_by_id = AsyncMock(side_effect=[
            _plan(status="testing", generated_params=dict(_GENERATED),
                  plan_json={"flow": _FLOW, "test_history": _HISTORY_PASS}, test_task_id=9),
            registered,
        ])
        spider_cls.return_value.create_definition = AsyncMock(
            return_value=MagicMock(id=77, name="ai_example_com_1"))

        resp = await svc.register(1)

        create_args = spider_cls.return_value.create_definition.await_args
        assert create_args.kwargs["source"] == "ai_generated"
        payload = create_args.args[0]
        assert payload.name == "ai_example_com_1"  # 域名 slug（example.com）+ plan id
        assert payload.type == "flow"
        assert resp.status == "registered"
        assert resp.plan_json["registered_definition"] == "ai_example_com_1"

    @pytest.mark.asyncio
    @patch("backend.services.ai_planner_service.SpiderService")
    async def test_register_idempotent_when_ai_definition_exists(self, spider_cls):
        """m4 幂等续走：create_definition 撞「已存在」且同名定义 source=ai_generated
        → 不重复建定义，直接完成 plan 状态置 registered（重试不再卡死）"""
        svc = _service()
        registered = _plan(status="registered",
                           plan_json={"flow": _FLOW, "test_history": _HISTORY_PASS,
                                      "registered_definition": "ai_example_com_1"},
                           generated_params=dict(_GENERATED), test_task_id=9)
        svc.repo.get_by_id = AsyncMock(side_effect=[
            _plan(status="testing", generated_params=dict(_GENERATED),
                  plan_json={"flow": _FLOW, "test_history": _HISTORY_PASS}, test_task_id=9),
            registered,
        ])
        spider_cls.return_value.create_definition = AsyncMock(side_effect=BusinessException(
            "爬虫定义 'ai_example_com_1' 已存在（id=77）"))
        with patch("backend.services.ai_planner_service.SpiderDefinitionRepository") as repo_cls:
            repo_cls.return_value.get_by_name = AsyncMock(return_value=MagicMock(
                id=77, name="ai_example_com_1", source="ai_generated"))
            resp = await svc.register(1)
        spider_cls.return_value.create_definition.assert_awaited_once()  # 不重复建
        assert resp.status == "registered"
        assert resp.plan_json["registered_definition"] == "ai_example_com_1"

    @pytest.mark.asyncio
    @patch("backend.services.ai_planner_service.SpiderService")
    async def test_register_reraises_when_existing_is_manual(self, spider_cls):
        """m4：同名定义是手动创建（source=manual）→ 仍拒绝，不允许幂等续走"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_plan(
            status="testing", generated_params=dict(_GENERATED),
            plan_json={"flow": _FLOW, "test_history": _HISTORY_PASS}, test_task_id=9))
        spider_cls.return_value.create_definition = AsyncMock(side_effect=BusinessException(
            "爬虫定义 'ai_example_com_1' 已存在（id=77）"))
        with patch("backend.services.ai_planner_service.SpiderDefinitionRepository") as repo_cls:
            repo_cls.return_value.get_by_name = AsyncMock(return_value=MagicMock(
                id=77, name="ai_example_com_1", source="manual"))
            with pytest.raises(BusinessException):
                await svc.register(1)

    @pytest.mark.asyncio
    async def test_register_rejected_without_passing_test(self):
        """最近一次试采未通过（或未试采）→ 拒绝注册"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_plan(
            status="testing", generated_params=dict(_GENERATED),
            plan_json={"flow": _FLOW, "test_history": []}))
        with pytest.raises(BusinessException) as ei:
            await svc.register(1)
        assert "不允许注册" in str(ei.value)

    @pytest.mark.asyncio
    async def test_register_rejected_when_already_registered(self):
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_plan(
            status="registered", generated_params=dict(_GENERATED),
            plan_json={"flow": _FLOW, "test_history": _HISTORY_PASS}))
        with pytest.raises(BusinessException):
            await svc.register(1)

    @pytest.mark.asyncio
    async def test_register_missing_plan_raises(self):
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(NotFoundException):
            await svc.register(999)


# ---------------- 触发 / 删除 ----------------
class TestLaunchAndDelete:
    @staticmethod
    def _spy_spawn():
        """记录 spawn 调用并显式关闭协程（避免 never-awaited 警告）"""
        spawned: list = []

        def _fake_spawn(coro):
            coro.close()
            spawned.append(coro)

        return spawned, _fake_spawn

    @pytest.mark.asyncio
    async def test_launch_plan_claims_planning_and_spawns(self):
        """M5：launch_plan 用条件 UPDATE 原子抢断置 planning（不再 check-then-act）"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_plan(status="draft"))
        svc.repo.claim_status = AsyncMock(return_value=True)
        spawned, fake_spawn = self._spy_spawn()
        with patch("backend.services.ai_planner_service._spawn", fake_spawn):
            resp = await svc.launch_plan(1)
        claim_args = svc.repo.claim_status.await_args
        assert claim_args.args[0] == 1 and claim_args.args[1] == "planning"
        for busy in ("planning", "testing", "registered"):
            assert busy in claim_args.kwargs["blocked_statuses"]
        assert len(spawned) == 1
        assert resp.status == "draft"

    @pytest.mark.asyncio
    async def test_launch_plan_concurrent_claim_conflict_raises(self):
        """M5 并发抢断：抢断失败（rowcount=0，已被并发任务占用）→ 业务异常且不 spawn"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_plan(status="draft"))
        svc.repo.claim_status = AsyncMock(return_value=False)
        spawned, fake_spawn = self._spy_spawn()
        with patch("backend.services.ai_planner_service._spawn", fake_spawn):
            with pytest.raises(BusinessException) as ei:
                await svc.launch_plan(1)
        assert "请勿重复触发" in str(ei.value)
        assert spawned == []

    @pytest.mark.asyncio
    async def test_launch_test_claims_testing_before_spawn(self):
        """M5：launch_test 在 spawn 前先原子置 testing（原实现 spawn 前不置状态）"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_plan(
            status="draft", generated_params=dict(_GENERATED)))
        svc.repo.claim_status = AsyncMock(return_value=True)
        spawned, fake_spawn = self._spy_spawn()
        with patch("backend.services.ai_planner_service._spawn", fake_spawn):
            await svc.launch_test(1)
        claim_args = svc.repo.claim_status.await_args
        assert claim_args.args[1] == "testing"
        for busy in ("planning", "testing", "registered"):
            assert busy in claim_args.kwargs["blocked_statuses"]
        assert len(spawned) == 1

    @pytest.mark.asyncio
    async def test_launch_test_rejects_during_testing(self):
        """M5：testing 期间重复触发试采 → 业务异常（原实现不拦，会双跑）"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_plan(
            status="testing", generated_params=dict(_GENERATED)))
        spawned, fake_spawn = self._spy_spawn()
        with patch("backend.services.ai_planner_service._spawn", fake_spawn):
            with pytest.raises(BusinessException):
                await svc.launch_test(1)
        assert spawned == []

    @pytest.mark.asyncio
    async def test_launch_plan_rejects_testing(self):
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_plan(status="testing"))
        with pytest.raises(BusinessException):
            await svc.launch_plan(1)

    @pytest.mark.asyncio
    async def test_launch_test_requires_generated_params(self):
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_plan(status="draft", generated_params=None))
        spawned, fake_spawn = self._spy_spawn()
        with patch("backend.services.ai_planner_service._spawn", fake_spawn):
            with pytest.raises(BusinessException):
                await svc.launch_test(1)
        assert spawned == []

    @pytest.mark.asyncio
    async def test_delete_rejects_during_testing(self):
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_plan(status="testing"))
        with pytest.raises(BusinessException):
            await svc.delete_plan(1)

    @pytest.mark.asyncio
    async def test_delete_success(self):
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_plan(status="registered"))
        svc.repo.delete = AsyncMock(return_value=True)
        result = await svc.delete_plan(1)
        assert result == {"id": 1, "deleted": True}

    @pytest.mark.asyncio
    async def test_get_plan_missing_raises(self):
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(NotFoundException):
            await svc.get_plan(999)


# ---------------- FlowConfig 契约校验 ----------------
class TestFlowConfigValidation:
    def _selectors(self, **kw):
        return {"selectors": [{"name": "title", "type": "css", "expr": "h1::text"}], **kw}

    def test_valid_flow_passes(self):
        flow = FlowConfig.model_validate({
            "selectors": [{"name": "title", "type": "xpath", "expr": "//h1/text()"}],
            "pagination": {"selector": "//a[@class='next']", "type": "xpath", "max_pages": 2},
            "detail": {"list_selector": "div.item", "url_selector": "./@href",
                       "selectors": [{"name": "content", "type": "css", "expr": "p"}]},
            "filters": [{"field": "title", "op": "regex", "value": r"\d+"}],
        })
        assert flow.pagination.max_pages == 2
        assert flow.detail.url_selector == "./@href"

    def test_rejects_invalid_regex_expr(self):
        with pytest.raises(ValidationError):
            FlowConfig.model_validate(self._selectors(
                selectors=[{"name": "t", "type": "regex", "expr": "([unclosed"}]))

    def test_rejects_xpath_without_allowed_prefix(self):
        with pytest.raises(ValidationError):
            FlowConfig.model_validate(self._selectors(
                selectors=[{"name": "t", "type": "xpath", "expr": "?//div"}]))

    def test_rejects_js_injection_in_css(self):
        with pytest.raises(ValidationError):
            FlowConfig.model_validate(self._selectors(
                selectors=[{"name": "t", "type": "css", "expr": "javascript:alert(1)"}]))

    def test_rejects_empty_selectors(self):
        with pytest.raises(ValidationError):
            FlowConfig.model_validate({"selectors": []})

    def test_rejects_pagination_regex_type(self):
        """翻页链接提取仅支持 css/xpath（flow_generic._LINK_SELECTOR_TYPES）"""
        with pytest.raises(ValidationError):
            FlowConfig.model_validate(self._selectors(
                pagination={"selector": "a.next", "type": "regex", "max_pages": 2}))

    def test_rejects_bad_filter_regex_value(self):
        with pytest.raises(ValidationError):
            FlowConfig.model_validate(self._selectors(
                filters=[{"field": "title", "op": "regex", "value": "([bad"}]))

    def test_validate_selector_expr_regex(self):
        with pytest.raises(ValueError):
            validate_selector_expr("([bad", "regex")
        assert validate_selector_expr("//div[@id='x']", "xpath") == "//div[@id='x']"

    def test_wait_for_must_be_valid_css(self):
        """i2：wait_for 是 Playwright 等待选择器，复用 css 白名单校验"""
        flow = FlowConfig.model_validate(self._selectors(wait_for="div.content", wait_timeout=10))
        assert flow.wait_for == "div.content"
        with pytest.raises(ValidationError):
            FlowConfig.model_validate(self._selectors(wait_for="javascript:alert(1)"))
        with pytest.raises(ValidationError):
            FlowConfig.model_validate(self._selectors(wait_for="div > ; broken"))


# ---------------- M6：target_url 静态 SSRF 校验（schema 层） ----------------
class TestAiPlanCreateUrlValidation:
    @pytest.mark.parametrize("url", [
        "http://127.0.0.1/x", "http://10.0.0.5/x", "http://192.168.1.1/x",
        "http://172.16.0.9/x", "http://169.254.169.254/latest/meta-data",
        "http://[::1]/x", "http://0.0.0.0/x", "http://2130706433/x",  # 整数编码环回
    ])
    def test_private_literal_ip_rejected(self, url):
        with pytest.raises(ValidationError):
            AiPlanCreate(target_url=url)

    def test_localhost_and_non_standard_port_rejected(self):
        with pytest.raises(ValidationError):
            AiPlanCreate(target_url="http://localhost:8080/x")
        with pytest.raises(ValidationError):
            AiPlanCreate(target_url="http://metadata.google.internal/x")
        with pytest.raises(ValidationError):
            AiPlanCreate(target_url="http://example.com:8080/x")

    def test_public_targets_pass(self):
        assert AiPlanCreate(target_url="https://example.com/list").target_url.endswith("/list")
        assert AiPlanCreate(target_url="http://example.com:443/x").target_url.endswith(":443/x")


# ---------------- i4：注册爬虫名截断 ----------------
class TestDeriveSpiderName:
    def test_length_capped_for_any_plan_id(self):
        """i4：任意 plan_id 下 name 总长 ≤50（slug 截断按 id 位数动态计算）且保留 id 后缀"""
        long_url = f"https://{'a' * 80}.example.com/list"
        for pid in (1, 123456, 9999999):
            name = _derive_spider_name(long_url, pid)
            assert len(name) <= 50
            assert name.startswith("ai_") and name.endswith(f"_{pid}")

    def test_short_domain_keeps_slug(self):
        assert _derive_spider_name("https://example.com/list", 1) == "ai_example_com_1"


# ---------------- M6：_fetch_html SSRF 防护 ----------------
class TestSsrfProtection:
    @staticmethod
    def _client_cls_with(responses):
        """httpx.AsyncClient 桩：逐个返回预置响应"""
        client = MagicMock()
        client.get = AsyncMock(side_effect=responses)
        client_cls = MagicMock()
        client_cls.return_value = AsyncMock()
        client_cls.return_value.__aenter__.return_value = client
        client_cls.return_value.__aexit__.return_value = False
        return client_cls, client

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url", [
        "http://192.168.1.10/admin", "http://127.0.0.1:8500/x", "http://[::1]/x",
        "http://169.254.169.254/latest/meta-data", "http://10.1.2.3/x",
        "http://example.com:8080/x", "ftp://example.com/x",
    ])
    async def test_fetch_html_rejects_before_any_request(self, url):
        """私网/环回/链路本地/非法端口/协议：拒绝且不发起任何 HTTP 请求"""
        with patch("backend.services.ai_planner_service.httpx.AsyncClient") as client_cls:
            with pytest.raises(BusinessException):
                await _fetch_html(url)
        client_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_html_rejects_integer_encoded_host(self):
        """纯数字 host（整数编码 IP 绕过，glibc 会解析为 127.0.0.1）：拒绝且零请求"""
        with patch("backend.services.ai_planner_service.httpx.AsyncClient") as client_cls:
            with pytest.raises(BusinessException):
                await _fetch_html("http://2130706433/x")
        client_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_html_rejects_private_dns_resolution(self):
        """域名解析到私网 IP：拒绝且不发起请求（DNS 级校验）"""
        with patch("backend.services.ai_planner_service._resolve_host_ips",
                   return_value=["10.0.0.5"]) as resolver, \
             patch("backend.services.ai_planner_service.httpx.AsyncClient") as client_cls:
            with pytest.raises(BusinessException):
                await _fetch_html("http://internal.example.com/x")
        resolver.assert_called_once_with("internal.example.com")
        client_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_html_follows_public_redirect_hop_by_hop(self):
        """公网重定向正常跟随（禁自动重定向逐跳校验语义）"""
        r1 = MagicMock(status_code=302, headers={"location": "https://example.com/final"})
        r2 = MagicMock(status_code=200, headers={}, text="<html>ok</html>")
        client_cls, client = self._client_cls_with([r1, r2])
        with patch("backend.services.ai_planner_service._resolve_host_ips",
                   return_value=["93.184.216.34"]), \
             patch("backend.services.ai_planner_service.httpx.AsyncClient", client_cls):
            html = await _fetch_html("https://example.com/start")
        assert html == "<html>ok</html>"
        assert client.get.await_count == 2
        assert client.get.await_args_list[1].args[0] == "https://example.com/final"

    @pytest.mark.asyncio
    async def test_fetch_html_rejects_redirect_to_private(self):
        """M6 重定向防线：公网页面 302 跳内网 → 第二跳校验拒绝，不向内网发请求"""
        r1 = MagicMock(status_code=302, headers={"location": "http://127.0.0.1/admin"})
        client_cls, client = self._client_cls_with([r1])
        with patch("backend.services.ai_planner_service._resolve_host_ips",
                   return_value=["93.184.216.34"]), \
             patch("backend.services.ai_planner_service.httpx.AsyncClient", client_cls):
            with pytest.raises(BusinessException):
                await _fetch_html("https://example.com/open-redirect")
        assert client.get.await_count == 1  # 仅公网第一跳发出

    @pytest.mark.asyncio
    async def test_plan_private_url_marks_failed_without_fetch(self):
        """私网 URL 计划触发规划：置 failed（error_message 可追溯）且零请求"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_plan(
            target_url="http://192.168.1.10/admin", plan_json=None))
        with patch("backend.services.ai_planner_service.httpx.AsyncClient") as client_cls:
            await svc._execute_plan(1)
        client_cls.assert_not_called()
        last = svc.repo.update_status.await_args_list[-1]
        assert last.args[1] == "failed"
        assert "SSRF" in last.kwargs["error_message"]


# ---------------- m3：_fail 自身失败兜底 ----------------
class TestFailFallback:
    @pytest.mark.asyncio
    async def test_fail_rolls_back_before_status_update(self):
        """m3：_fail 先回滚脏事务再置 failed（rollback 先于 commit）"""
        svc = _service()
        await svc._fail(1, "boom")
        svc.session.rollback.assert_awaited_once()
        call_names = [c[0] for c in svc.session.mock_calls]
        assert call_names.index("rollback") < call_names.index("commit")
        assert svc.repo.update_status.await_args.args[1] == "failed"
        assert svc.repo.update_status.await_args.kwargs["error_message"] == "boom"

    @pytest.mark.asyncio
    async def test_run_plan_bg_persists_failed_via_new_session(self):
        """m3：后台兜底异常（如 _fail 自身 DB 失败）→ 新 session 落 failed，且不再抛出"""
        with patch("backend.services.ai_planner_service.get_manager"), \
             patch("backend.services.ai_planner_service.AsyncSession") as session_cm, \
             patch("backend.services.ai_planner_service.AiPlanRepository") as repo_cls:
            session = AsyncMock()
            session_cm.return_value = AsyncMock()
            session_cm.return_value.__aenter__.return_value = session
            session_cm.return_value.__aexit__.return_value = False
            repo_cls.return_value.get_by_id = AsyncMock(return_value=None)  # 计划不存在 → 异常
            repo_cls.return_value.update_status = AsyncMock()
            await _run_plan_bg(1)  # 不应抛出
            repo_cls.return_value.update_status.assert_awaited_once()
            assert repo_cls.return_value.update_status.await_args.args[1] == "failed"

    @pytest.mark.asyncio
    async def test_force_fail_status_swallows_new_session_failure(self):
        """m3：新 session 兜底也失败 → 仅记日志，不抛（避免掩盖原始异常）"""
        from backend.services.ai_planner_service import _force_fail_status
        with patch("backend.services.ai_planner_service.get_manager"), \
             patch("backend.services.ai_planner_service.AsyncSession") as session_cm:
            session_cm.side_effect = RuntimeError("db down")
            await _force_fail_status(1, "msg")  # 不抛出


# ---------------- API 端点权限 ----------------
class TestApiPermissions:
    @pytest.mark.asyncio
    async def test_delete_plan_requires_admin(self):
        with pytest.raises(AuthorizationException):
            await require_admin(user=CurrentUser(id=2, username="op", role="operator"))

    @pytest.mark.asyncio
    async def test_trigger_plan_requires_operator(self):
        with pytest.raises(AuthorizationException):
            await require_operator(user=CurrentUser(id=3, username="viewer", role="viewer"))

    @pytest.mark.asyncio
    async def test_create_plan_allows_operator(self):
        user = await require_operator(user=CurrentUser(id=2, username="op", role="operator"))
        assert user.role == "operator"

    @pytest.mark.asyncio
    async def test_register_requires_admin_role(self):
        """M3：register 守卫为 admin，operator 越权被拒（AuthorizationException→403）"""
        with pytest.raises(AuthorizationException):
            await require_admin(user=CurrentUser(id=2, username="op", role="operator"))


# ---------------- API 端点快照 ----------------
@pytest.fixture
def ai_client(admin_client, app):
    """admin 特权 client + get_async_db override（mock session，审计提交不落库）

    T10：原依赖 conftest 全局兜底 admin，兜底收紧后显式声明 admin 特权
    （delete/register 端点挂 require_admin，operator/viewer 需另见越权用例）。
    """
    from platform_core.db import get_async_db
    session = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    app.dependency_overrides[get_async_db] = lambda: session
    yield admin_client
    app.dependency_overrides.pop(get_async_db, None)


class TestApiEndpoints:
    def test_create_plan_endpoint(self, ai_client, monkeypatch):
        async def fake_create(self, payload, created_by=None):
            return AiPlanResponse(id=1, target_url=payload.target_url, status="draft",
                                  created_by=created_by)
        monkeypatch.setattr(AiPlannerService, "create_plan", fake_create)
        monkeypatch.setattr("backend.app.api.v1.ai.record_audit", AsyncMock())
        resp = ai_client.post("/api/v1/ai/plans", json={"target_url": "https://a.b/c"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["status"] == "draft" and body["data"]["created_by"] == "test-admin"

    def test_create_plan_rejects_bad_url(self, ai_client):
        resp = ai_client.post("/api/v1/ai/plans", json={"target_url": "ftp://x"})
        assert resp.status_code == 422

    def test_list_plans_endpoint(self, ai_client, monkeypatch):
        from platform_core.schemas.ai_plan import AiPlanListResponse

        async def fake_list(self, skip=0, limit=20, status=None):
            return AiPlanListResponse(total=0, items=[])

        monkeypatch.setattr(AiPlannerService, "list_plans", fake_list)
        resp = ai_client.get("/api/v1/ai/plans")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == {"total": 0, "items": [], "page": 1, "page_size": 20,
                                "total_pages": 0}

    def test_trigger_plan_endpoint(self, ai_client, monkeypatch):
        async def fake_launch(self, plan_id):
            return AiPlanResponse(id=plan_id, target_url="https://a.b", status="planning")
        monkeypatch.setattr(AiPlannerService, "launch_plan", fake_launch)
        monkeypatch.setattr("backend.app.api.v1.ai.record_audit", AsyncMock())
        resp = ai_client.post("/api/v1/ai/plans/1/plan")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "planning"

    def test_delete_plan_endpoint_admin_only(self, ai_client, monkeypatch):
        async def fake_delete(self, plan_id):
            return {"id": plan_id, "deleted": True}
        monkeypatch.setattr(AiPlannerService, "delete_plan", fake_delete)
        monkeypatch.setattr("backend.app.api.v1.ai.record_audit", AsyncMock())
        resp = ai_client.delete("/api/v1/ai/plans/1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True and body["code"] == "DELETED"
        assert body["data"] == {"id": 1, "deleted": True}

    def test_register_endpoint_rejects_operator(self, ai_client, app):
        """M3：register 端点仅 admin，operator 调用被拒 403"""
        from backend.app.api.deps import get_current_user

        async def _operator_user():
            return CurrentUser(id=2, username="op", role="operator")

        async def _admin_user():
            return CurrentUser(id=1, username="test-admin", role="admin")

        original = app.dependency_overrides[get_current_user]
        app.dependency_overrides[get_current_user] = _operator_user
        try:
            resp = ai_client.post("/api/v1/ai/plans/1/register")
        finally:
            app.dependency_overrides[get_current_user] = original
        assert resp.status_code == 403

    def test_register_endpoint_allows_admin(self, ai_client, app, monkeypatch):
        """M3：admin 正常走 register（service 层 mock，不落库）"""
        from backend.app.api.deps import get_current_user

        async def fake_register(self, plan_id):
            return AiPlanResponse(id=plan_id, target_url="https://a.b", status="registered",
                                  plan_json={"registered_definition": "ai_a_b_1"})

        monkeypatch.setattr(AiPlannerService, "register", fake_register)
        monkeypatch.setattr("backend.app.api.v1.ai.record_audit", AsyncMock())
        admin_override = app.dependency_overrides.get(get_current_user)
        assert admin_override is not None  # conftest 已 override 为 admin
        resp = ai_client.post("/api/v1/ai/plans/1/register")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "registered"


# ---------------- 启动对账（评审 M-2：无条件置 failed，消除宽限窗口盲区） ----------------
class TestReconcileInterruptedPlans:
    """reconcile_interrupted_plans：启动时无条件把 planning/testing 置 failed"""

    @pytest.mark.asyncio
    async def test_unconditional_fail_no_updated_at_filter(self, monkeypatch):
        """UPDATE 语句不含 updated_at 过滤（原 10 分钟宽限盲区已消除）"""
        captured: dict = {}

        class _FakeResult:
            rowcount = 2

        class _FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def execute(self, stmt):
                captured["stmt"] = stmt
                return _FakeResult()

            async def commit(self):
                pass

        class _FakeManager:
            async_engines = {"DEFAULT": object()}

        monkeypatch.setattr(
            "backend.services.ai_planner_service.get_manager", lambda: _FakeManager())
        monkeypatch.setattr(
            "backend.services.ai_planner_service.AsyncSession", lambda engine: _FakeSession())
        assert await reconcile_interrupted_plans() == 2
        compiled = captured["stmt"].compile(compile_kwargs={"literal_binds": True})
        assert "planning" in str(compiled) and "testing" in str(compiled)
        assert "failed" in str(compiled)
        # WHERE 子句不含 updated_at 过滤（SET 子句的 updated_at=now() 为 ORM
        # onupdate 自动填充，与本修复无关）
        whereclause = captured["stmt"].whereclause
        where_clause = str(whereclause) if whereclause is not None else ""
        assert "updated_at" not in where_clause.lower()

    @pytest.mark.asyncio
    async def test_zero_affected_returns_zero(self, monkeypatch):
        """无滞留行时返回 0（不误报恢复数量）"""
        class _FakeResult:
            rowcount = 0

        class _FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def execute(self, stmt):
                return _FakeResult()

            async def commit(self):
                pass

        class _FakeManager:
            async_engines = {"DEFAULT": object()}

        monkeypatch.setattr(
            "backend.services.ai_planner_service.get_manager", lambda: _FakeManager())
        monkeypatch.setattr(
            "backend.services.ai_planner_service.AsyncSession", lambda engine: _FakeSession())
        assert await reconcile_interrupted_plans() == 0
