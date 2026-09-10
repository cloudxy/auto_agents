"""告警服务单测 - AlertService CRUD + 规则匹配引擎（盲区补测）

约定：不连真实 MySQL，Repository/NotifyService 用 MagicMock/AsyncMock 桩；
服务实例以 __new__ 构造注入桩（绕开 __init__ 的真实依赖组装）。

覆盖（核心公开方法直测）：
- create_rule：channels 列表序列化 JSON 落库 + 返回字典反序列化
- update_rule / delete_rule：缺失行抛 NotFoundException（B5 修复 F-B1b-01，
  统一异常体系，对齐 schedules/templates；HTTP 层映射 404）
- evaluate：consecutive_failures 连败触发（通知 + last_triggered_at 更新）/
  spider_name 不匹配与 queue_depth 跳过 / 仓储异常吞掉不影响主流程 /
  task_timeout 时长超阈值触发
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.alert_service import AlertService
from platform_core.exceptions import NotFoundException
from stubs import fake_async_session


def _rule(**overrides) -> SimpleNamespace:
    """告警规则实体桩（AlertService._rule_to_dict 契约字段）"""
    defaults = dict(
        id=1, name="连败告警", spider_name=None, rule_type="consecutive_failures",
        threshold=3, window_minutes=60, severity="critical", channels='["webhook"]',
        enabled=True, last_triggered_at=None, created_at=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _service() -> AlertService:
    svc = AlertService.__new__(AlertService)
    svc.session = fake_async_session()  # commit/refresh/rollback/execute 均 AsyncMock
    svc.repo = MagicMock()
    svc._notify = MagicMock()
    svc._notify.notify_task_finished = AsyncMock()
    return svc


# ---------------- CRUD ----------------
@pytest.mark.asyncio
async def test_create_rule_serializes_channels_and_returns_dict():
    """创建规则：channels 列表序列化为 JSON 字符串落库，返回字典中反序列化回列表"""
    svc = _service()
    svc.repo.create = AsyncMock(return_value=_rule())

    result = await svc.create_rule(
        {"name": "连败告警", "rule_type": "consecutive_failures", "threshold": 3,
         "channels": ["webhook", "email"]},
    )

    kwargs = svc.repo.create.call_args.kwargs
    assert kwargs["channels"] == '["webhook", "email"]'  # 落库为 JSON 字符串
    assert result["channels"] == ["webhook"]  # 响应取自落库实体的反序列化结果
    assert result["rule_type"] == "consecutive_failures"
    svc.session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_rule_missing_raises_not_found():
    """更新不存在的规则抛 NotFoundException（B5：统一异常体系，HTTP 层映射 404）"""
    svc = _service()
    svc.repo.update = AsyncMock(return_value=None)

    with pytest.raises(NotFoundException, match="告警规则 999不存在"):
        await svc.update_rule(999, {"threshold": 5})


@pytest.mark.asyncio
async def test_delete_rule_success_and_missing():
    """删除存在的规则返回 deleted 标记；缺失行抛 NotFoundException（B5）"""
    svc = _service()
    svc.repo.delete = AsyncMock(return_value=True)
    assert await svc.delete_rule(7) == {"rule_id": 7, "deleted": True}

    svc.repo.delete = AsyncMock(return_value=False)
    with pytest.raises(NotFoundException, match="告警规则 999不存在"):
        await svc.delete_rule(999)


# ---------------- 规则评估 ----------------
@pytest.mark.asyncio
async def test_evaluate_consecutive_failures_triggers():
    """连续失败达到阈值：发送告警（status=alert）并记录触发时间"""
    svc = _service()
    rule = _rule(spider_name="example", threshold=3)
    svc.repo.list_active = AsyncMock(return_value=[rule])
    result = MagicMock()
    result.all.return_value = [("failed",), ("failed",), ("failed",)]
    svc.session.execute = AsyncMock(return_value=result)

    await svc.evaluate({"task_id": 10, "spider_name": "example",
                        "status": "failed", "result_count": 0})

    svc._notify.notify_task_finished.assert_awaited_once()
    kw = svc._notify.notify_task_finished.await_args.kwargs
    assert kw["status"] == "alert"  # 特殊状态标识
    assert "连续失败次数达到 3" in kw["error_message"]
    assert rule.last_triggered_at is not None  # 触发时间被记录
    svc.session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_evaluate_skips_other_spider_and_queue_depth():
    """spider_name 不匹配与 queue_depth 类型（调度器侧处理）均跳过"""
    svc = _service()
    rules = [
        _rule(id=1, spider_name="other"),  # 与 task_info 不匹配
        _rule(id=2, spider_name=None, rule_type="queue_depth"),  # 非终态评估类型
    ]
    svc.repo.list_active = AsyncMock(return_value=rules)

    await svc.evaluate({"task_id": 10, "spider_name": "example", "status": "failed"})

    svc._notify.notify_task_finished.assert_not_awaited()
    svc.session.execute.assert_not_awaited()  # 未走到连败查库分支


@pytest.mark.asyncio
async def test_evaluate_swallows_repo_exception():
    """告警评估失败不影响主流程（吞异常，不向上传播）"""
    svc = _service()
    svc.repo.list_active = AsyncMock(side_effect=RuntimeError("db down"))

    await svc.evaluate({"task_id": 10, "spider_name": "example", "status": "failed"})
    # 未抛异常即通过


@pytest.mark.asyncio
async def test_evaluate_task_timeout_triggers_without_db_query():
    """任务时长超过阈值（分钟）触发；task_timeout 分支不查任务表"""
    svc = _service()
    rule = _rule(rule_type="task_timeout", threshold=5, spider_name="example")
    svc.repo.list_active = AsyncMock(return_value=[rule])

    await svc.evaluate({"task_id": 11, "spider_name": "example", "status": "completed",
                        "duration_seconds": 400})  # 400s > 5min

    svc._notify.notify_task_finished.assert_awaited_once()
    assert "任务时长超过 5 分钟" in svc._notify.notify_task_finished.await_args.kwargs["error_message"]
