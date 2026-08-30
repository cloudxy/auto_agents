"""AI 采集规划编排层：AiPlannerService（规划 / 试采自动修复 / 注册 / CRUD）

拆分自 ai_planner_service.py（期4 结构治理）。原模块 docstring 中的设计约束
继续有效：
- 后台任务（规划/试采）自开独立 AsyncSession（端点请求 session 在响应后关闭），
  服务内所有状态变更落 DB，状态机可查询进度
- 试采终态轮询用独立短事务 session（_read_task_snapshot，见 state.py）：
  长生命周期 session 的 identity map 会遮蔽 webhook 并发推进的终态
- DOM/HTML 清洗等 CPU 操作走 asyncio.to_thread，不阻塞事件循环
- commit 后不再读 ORM 属性（防 expire 惰性加载 MissingGreenlet），全部用本地变量

Patch 兼容约定：_spawn / _run_plan_bg / _run_test_bg / _BUSY_STATUSES /
_fetch_html / _clean_html_sync / _parse_llm_json / _build_* / _read_task_snapshot /
SpiderService / SpiderDefinitionRepository / settings 等被存量单测 patch 的符号
一律经门面模块 _facade 属性查找（文件末行 import），使
patch("backend.services.ai_planner_service.<name>") 在运行时生效。
llm_chat 调用委托 llm_client.llm_chat（token 预算/重试逻辑真身所在）。
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Optional

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.schemas.ai_plan import (
    AiPlanCreate,
    AiPlanListResponse,
    AiPlanResponse,
    FlowConfig,
)
from platform_core.schemas.spider import DefinitionCreateRequest

if TYPE_CHECKING:  # 仅类型检查期导入（运行时不求值注解，规避 shim ↔ 包循环）
    from backend.services.ai_planner.state import _TaskSnapshot

logger = get_logger("api")


class AiPlannerService:
    """AI 采集计划服务：规划 / 试采（含自动修复迭代）/ 注册 / CRUD"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = _facade.AiPlanRepository(session)

    # ------------------------------------------------------------------
    # CRUD（同步返回，规划/试采走后台任务）
    # ------------------------------------------------------------------
    async def create_plan(
        self, payload: AiPlanCreate, created_by: Optional[str] = None
    ) -> AiPlanResponse:
        """创建计划（draft；html_snippet 预置后规划阶段跳过在线抓取）"""
        logger.info(f"创建 AI 采集计划: target_url={payload.target_url}, by={created_by}")
        plan_json = {"html_snippet": payload.html_snippet} if payload.html_snippet else None
        item = await self.repo.create(
            target_url=payload.target_url, status="draft", plan_json=plan_json,
            created_by=created_by,
        )
        await self.session.commit()
        await self.session.refresh(item)
        return AiPlanResponse.model_validate(item)

    async def list_plans(
        self, skip: int = 0, limit: int = 20, status: Optional[str] = None
    ) -> AiPlanListResponse:
        """分页列表（可按状态过滤）"""
        items = await self.repo.list_plans(skip=skip, limit=limit, status=status)
        total = await self.repo.count(status=status)
        return AiPlanListResponse(
            total=total, items=[AiPlanResponse.model_validate(p) for p in items]
        )

    async def get_plan(self, plan_id: int) -> AiPlanResponse:
        """单条计划快照"""
        plan = await self.repo.get_by_id(plan_id)
        if plan is None:
            raise NotFoundException("AI 采集计划")
        return AiPlanResponse.model_validate(plan)

    async def delete_plan(self, plan_id: int) -> dict:
        """删除计划（规划/试采进行中拒绝，防后台任务写空）"""
        plan = await self.repo.get_by_id(plan_id)
        if plan is None:
            raise NotFoundException("AI 采集计划")
        if plan.status in ("planning", "testing"):
            raise BusinessException("计划正在规划/试采中，无法删除；请等待后台任务结束")
        deleted = await self.repo.delete(plan_id)
        await self.session.commit()
        logger.info(f"AI 采集计划已删除: plan_id={plan_id}")
        return {"id": plan_id, "deleted": deleted}

    # ------------------------------------------------------------------
    # 后台任务触发（API 端点内 create_task，立即返回快照）
    # ------------------------------------------------------------------
    async def launch_plan(self, plan_id: int) -> AiPlanResponse:
        """触发后台规划：原子抢断置 planning → asyncio.create_task 执行，立即返回快照"""
        plan = await self.repo.get_by_id(plan_id)
        if plan is None:
            raise NotFoundException("AI 采集计划")
        if plan.status in _facade._BUSY_STATUSES:
            raise BusinessException(f"计划当前状态为 {plan.status}，不允许触发规划")
        # M5：check-then-act 非原子，并发触发会双跑双 LLM 调用；
        # 条件 UPDATE（status NOT IN busy）一次语句抢断，rowcount=0 即已被并发占用。
        claimed = await self.repo.claim_status(
            plan_id, "planning", blocked_statuses=_facade._BUSY_STATUSES,
            error_message=None, test_task_id=None,
        )
        await self.session.commit()
        if not claimed:
            raise BusinessException("计划已进入规划/试采/注册流程，请勿重复触发")
        _facade._spawn(_facade._run_plan_bg(plan_id))
        return await self.get_plan(plan_id)

    async def launch_test(self, plan_id: int) -> AiPlanResponse:
        """触发后台试采：spawn 前原子抢断置 testing，立即返回快照"""
        plan = await self.repo.get_by_id(plan_id)
        if plan is None:
            raise NotFoundException("AI 采集计划")
        if plan.status == "planning":
            raise BusinessException("规划进行中，请等待规划完成后再试采")
        if plan.status == "testing":
            raise BusinessException("试采进行中，请勿重复触发")
        if plan.status == "registered":
            raise BusinessException("计划已注册，无需再次试采")
        if not plan.generated_params:
            raise BusinessException("请先完成规划（/plan）再试采")
        # M5：原实现不拦 testing 且 spawn 前不置状态 → testing 期间重复触发即双跑；
        # spawn 前先条件 UPDATE 原子置 testing，抢断失败（并发已占）直接拒绝。
        claimed = await self.repo.claim_status(
            plan_id, "testing", blocked_statuses=_facade._BUSY_STATUSES, error_message=None,
        )
        await self.session.commit()
        if not claimed:
            raise BusinessException("计划已进入规划/试采/注册流程，请勿重复触发")
        _facade._spawn(_facade._run_test_bg(plan_id))
        return await self.get_plan(plan_id)

    # ------------------------------------------------------------------
    # LLM 调用（OpenAI 兼容 chat completions，httpx 直连；供应商优先 / 兜底不变）
    # ------------------------------------------------------------------
    async def _llm_chat(self, messages: list[dict]) -> str:
        """chat completions（真身在 llm_client.llm_chat，委托保持方法签名兼容）"""
        return await _facade.llm_chat(messages)

    # ------------------------------------------------------------------
    # 规划（后台执行：planning → 抓取/复用 HTML → LLM → FlowConfig → 落库）
    # ------------------------------------------------------------------
    async def _execute_plan(self, plan_id: int) -> None:
        plan = await self.repo.get_by_id(plan_id)
        if plan is None:
            raise NotFoundException("AI 采集计划")
        # commit 会 expire ORM 对象，先提取本地变量再推进状态机
        target_url = plan.target_url
        plan_json = dict(plan.plan_json or {})

        await self.repo.update_status(plan_id, "planning", error_message=None, test_task_id=None)
        await self.session.commit()

        try:
            snippet = plan_json.get("html_snippet")
            if snippet:
                html = snippet
                logger.info(f"AI 规划使用预置 HTML 片段: plan_id={plan_id}")
            else:
                html = await _facade._fetch_html(target_url)
            cleaned = await asyncio.to_thread(_facade._clean_html_sync, html)
            raw = await self._llm_chat(_facade._build_plan_messages(target_url, cleaned))
            flow_dict = await asyncio.to_thread(_facade._parse_llm_json, raw)
            flow = await asyncio.to_thread(FlowConfig.model_validate, flow_dict)
            generated = _facade._build_generated_params(target_url, flow)
            new_plan_json = {"flow": flow.model_dump(), "test_history": [], "html_sample": cleaned}
            await self.repo.update(plan_id, plan_json=new_plan_json, generated_params=generated)
            # 规划成功回 draft（规划产物已落库，等待试采触发）
            await self.repo.update_status(plan_id, "draft", error_message=None, test_task_id=None)
            await self.session.commit()
            logger.info(f"AI 规划完成: plan_id={plan_id}, selectors={len(flow.selectors)}")
        except ValidationError as e:
            await self._fail(plan_id, f"FlowConfig 校验失败: {e}")
        except BusinessException as e:
            await self._fail(plan_id, str(e))
        except Exception as e:  # noqa: BLE001 后台任务兜底置 failed
            await self._fail(plan_id, f"规划异常: {e}")

    # ------------------------------------------------------------------
    # 试采（后台执行：flow_generic 低优先级试采 + 自动修复迭代）
    # ------------------------------------------------------------------
    async def _execute_test(self, plan_id: int) -> None:
        plan = await self.repo.get_by_id(plan_id)
        if plan is None:
            raise NotFoundException("AI 采集计划")
        if not plan.generated_params:
            raise BusinessException("计划缺少生成的任务参数，请先执行规划")
        target_url = plan.target_url
        plan_json = dict(plan.plan_json or {})
        params_dict = dict(plan.generated_params)
        iteration = int(plan.iteration_count or 0)
        history = [dict(h) for h in (plan_json.get("test_history") or [])]
        html_sample = str(plan_json.get("html_sample") or "")
        flow_dict = dict(plan_json.get("flow") or {})
        max_iterations = max(0, int(_facade.settings.get("LLM.MAX_ITERATIONS", 2)))
        spider_svc = _facade.SpiderService(self.session)

        try:
            while True:
                params_str = json.dumps(params_dict, ensure_ascii=False)
                task = await spider_svc.enqueue(
                    spider_name="flow_generic", params=params_str, priority="low"
                )
                await self.repo.update(plan_id, test_task_id=task.id)
                await self.repo.update_status(plan_id, "testing", error_message=None,
                                              test_task_id=task.id)
                await self.session.commit()
                logger.info(
                    f"AI 试采任务已入队: plan_id={plan_id}, task_id={task.id}, iteration={iteration}"
                )

                final_task = await self._wait_task_final(spider_svc, task.id)
                passed, reason = await self._judge_test(spider_svc, final_task)
                history.append({
                    "iteration": iteration,
                    "task_id": task.id,
                    "status": final_task.status,
                    "result_count": int(final_task.result_count or 0),
                    "passed": passed,
                    "reason": reason,
                })
                plan_json["test_history"] = history
                await self.repo.update(plan_id, plan_json=plan_json, test_task_id=task.id)
                await self.session.commit()

                if passed:
                    # 试采通过：保持 testing（可注册），注册时校验最近一次通过
                    logger.info(f"AI 试采通过: plan_id={plan_id}, task_id={task.id}, reason={reason}")
                    return

                if iteration < max_iterations:
                    iteration += 1
                    await self.repo.update(plan_id, iteration_count=iteration)
                    await self.session.commit()
                    logger.warning(
                        f"AI 试采未通过，自动修复迭代 {iteration}/{max_iterations}: "
                        f"plan_id={plan_id}, reason={reason}"
                    )
                    flow = await self._repair_flow(target_url, flow_dict, reason, html_sample)
                    params_dict = _facade._build_generated_params(target_url, flow)
                    plan_json["flow"] = flow.model_dump()
                    await self.repo.update(
                        plan_id, generated_params=params_dict, plan_json=plan_json
                    )
                    await self.session.commit()
                    continue  # 重新入队试采

                await self._fail(
                    plan_id, f"试采未通过（自动修复迭代已达上限 {max_iterations} 次）: {reason}"
                )
                return
        except BusinessException as e:
            await self._fail(plan_id, str(e))
        except Exception as e:  # noqa: BLE001
            await self._fail(plan_id, f"试采异常: {e}")

    async def _repair_flow(
        self, target_url: str, flow_dict: dict, reason: str, html_sample: str
    ) -> FlowConfig:
        """把失败原因 + 样本 HTML 回喂 LLM 修正 selectors（修复失败由调用方置 failed）"""
        html = html_sample
        if not html:
            html = await _facade._fetch_html(target_url)
        cleaned = await asyncio.to_thread(_facade._clean_html_sync, html)
        raw = await self._llm_chat(_facade._build_repair_messages(target_url, flow_dict, reason, cleaned))
        new_flow_dict = await asyncio.to_thread(_facade._parse_llm_json, raw)
        return await asyncio.to_thread(FlowConfig.model_validate, new_flow_dict)

    async def _wait_task_final(self, spider_svc, task_id: int) -> _TaskSnapshot:
        """轮询试采任务至终态（completed/failed），超时抛业务异常

        每轮经 _read_task_snapshot 用独立短事务 session 读最新终态
        （间隔/超时语义不变），规避长生命周期 session identity map 遮蔽；
        返回脱离 ORM session 的纯标量快照。
        """
        deadline = time.monotonic() + _facade._WAIT_TIMEOUT_SECONDS
        while True:
            snapshot = await _facade._read_task_snapshot(task_id)
            if snapshot is not None and snapshot.status in ("completed", "failed"):
                return snapshot
            if time.monotonic() >= deadline:
                raise BusinessException(
                    f"试采任务 {task_id} 超时未结束（>{_facade._WAIT_TIMEOUT_SECONDS:.0f}s）"
                )
            await asyncio.sleep(_facade._WAIT_INTERVAL_SECONDS)

    async def _judge_test(self, spider_svc, task: _TaskSnapshot) -> tuple[bool, str]:
        """试采判定：completed 且 result_count>0，质量分过低（<40）判失败"""
        if task.status != "completed":
            return False, f"试采任务失败: {task.error_message or task.status}"
        result_count = task.result_count
        if result_count <= 0:
            return False, "试采结果为空（result_count=0）"
        quality = await spider_svc.get_task_quality(task.task_id)
        avg = quality.avg_score
        if avg is not None and float(avg) < 40:
            return False, f"试采质量分过低（avg_score={float(avg):.1f} < 40）"
        return True, f"试采通过: {result_count} 条结果"

    # ------------------------------------------------------------------
    # 注册（同步执行：校验最近试采通过 → create_definition(source=ai_generated)）
    # ------------------------------------------------------------------
    async def register(self, plan_id: int) -> AiPlanResponse:
        plan = await self.repo.get_by_id(plan_id)
        if plan is None:
            raise NotFoundException("AI 采集计划")
        if plan.status == "registered":
            raise BusinessException("该计划已注册过爬虫定义")
        # create_definition 内部会 commit（expire ORM），先提取全部本地变量
        plan_json = dict(plan.plan_json or {})
        history = plan_json.get("test_history") or []
        generated_params = plan.generated_params
        test_task_id = plan.test_task_id
        target_url = plan.target_url

        if not history or not history[-1].get("passed"):
            raise BusinessException("最近一次试采未通过（或尚未试采），不允许注册；请先执行试采并通过")
        if not generated_params:
            raise BusinessException("计划缺少生成的任务参数，请先执行规划")

        name = _facade._derive_spider_name(target_url, plan_id)
        payload = DefinitionCreateRequest(
            name=name,
            title=f"AI 采集 - {_facade._domain_of(target_url)}",
            type="flow",
            description=f"AI 生成的流程化采集（计划 #{plan_id}，目标 {target_url}）",
        )
        spider_svc = _facade.SpiderService(self.session)
        try:
            definition = await spider_svc.create_definition(payload, source="ai_generated")
        except BusinessException as e:
            # m4：create_definition 已 commit 但 plan 状态更新失败时，重试会撞「已存在」；
            # 同名且 source=ai_generated 的定义即本次 AI 注册产物 → 幂等续走（不重复建定义）。
            if "已存在" not in str(e):
                raise
            existing = await _facade.SpiderDefinitionRepository(self.session).get_by_name(name)
            if existing is None or existing.source != "ai_generated":
                raise
            logger.warning(
                f"AI 计划注册幂等续走（定义已存在且来源为 ai_generated）: "
                f"plan_id={plan_id}, definition={name}"
            )
            definition = existing

        plan_json["registered_definition"] = definition.name
        await self.repo.update(plan_id, plan_json=plan_json)
        await self.repo.update_status(
            plan_id, "registered", error_message=None, test_task_id=test_task_id
        )
        await self.session.commit()
        logger.info(f"AI 计划已注册为爬虫定义: plan_id={plan_id}, definition={definition.name}")
        return await self.get_plan(plan_id)

    # ------------------------------------------------------------------
    # 失败兜底：置 failed + error_message（状态机可追溯）
    # ------------------------------------------------------------------
    async def _fail(self, plan_id: int, message: str) -> None:
        """失败兜底：先回滚（m3：原异常可能让 session 处于待回滚态，直接 update 会连坐失败卡死）
        再置 failed（状态机可追溯）；自身仍失败则由 _run_*_bg 的 _force_fail_status 收尾。"""
        logger.error(f"AI 计划失败: plan_id={plan_id}, error={message}")
        await self.session.rollback()
        await self.repo.update_status(plan_id, "failed", error_message=message[:2000],
                                      test_task_id=None)
        await self.session.commit()


# ----------------------------------------------------------------------
# 门面引用（循环导入兼容，必须置于文件末尾；语义见 llm_client.py 同名注释）
# ----------------------------------------------------------------------
import backend.services.ai_planner_service as _facade  # noqa: E402

