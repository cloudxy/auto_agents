"""queue_depth 告警接通单测（T-42 / FR-105；db-spec §16.6）

约定：不连真实 MySQL——Repository/NotifyService 用 MagicMock/AsyncMock 桩，
服务实例以 __new__ 构造注入桩（对齐 test_alert_service.py）。

覆盖：
- GWT-105.1 超阈值 → notify_text 渠道发送 + notifications 命中行
  （type='alert'，resource_type='alert_rule'，user_id=规则创建者，content 含深度数字）
  + last_triggered_at 推进（静默窗判据）
- 静默窗：窗口内重复命中不重复发送；窗口过期恢复触发
- 创建者解析不出（软删/不在册）→ 不落命中行、不发送、不静默改投（db-spec §16.6）
- 评估异常吞掉不挡调度循环
- GWT-105.3 四类型（consecutive_failures/result_drop/task_timeout/queue_depth）
  全部有触发路径——「配了规则却无触发路径的类型」= 死规则 = 验收失败
- 调度器接线：_tick_once 每 tick 调用评估（不依赖到期计划）；
  评估失败不挡调度；SCHEDULER.QUEUE_DEPTH_WARN 配置日志路径退役（无 _check_queue_depth）
"""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.alert_service import AlertService
from backend.services.schedule_service import SpiderScheduler
from stubs import fake_async_session

RULE_TYPES = ("consecutive_failures", "result_drop", "task_timeout", "queue_depth")


def _qrule(**overrides) -> SimpleNamespace:
    """queue_depth 规则桩（AlertRule 契约字段；TenantMixin/AuditMixin 含 tenant_id/created_by）

    用 SimpleNamespace 而非 MagicMock：name 是 MagicMock 构造保留字
    （设的是 repr 而非属性），属性访问须返回字面值。
    """
    defaults = dict(
        id=5, tenant_id=8, name="队列堆积告警", spider_name=None,
        rule_type="queue_depth", threshold=10, window_minutes=60,
        severity="warning", channels=None, enabled=True,
        last_triggered_at=None, created_by="alice", created_at=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _service() -> AlertService:
    svc = AlertService.__new__(AlertService)
    svc.session = fake_async_session()  # commit/refresh/execute 均 AsyncMock；add 可断言
    svc.repo = MagicMock()
    svc._tasks = MagicMock()
    svc._users = MagicMock()
    svc._notify = MagicMock()
    svc._notify.notify_text = AsyncMock()
    svc._notify.notify_task_finished = AsyncMock()
    return svc


def _arm_queue_depth(svc: AlertService, rule: MagicMock, depth: int, creator_id: int | None = 42):
    """装配 queue_depth 评估桩：规则行 + 租户排队深度 + 创建者解析"""
    svc.repo.list_queue_depth_rules = AsyncMock(return_value=[rule])
    svc._tasks.count_pending_by_tenant = AsyncMock(return_value=depth)
    svc._users.get_active_id_by_username_in_tenant = AsyncMock(return_value=creator_id)


# ---------------- GWT-105.1：超阈值 → 通知 + 命中记录 ----------------
@pytest.mark.asyncio
async def test_queue_depth_over_threshold_triggers_notify_and_hit_row():
    """排队深度 12 > 阈值 10：渠道通知 + notifications 命中行 + last_triggered_at 推进"""
    svc = _service()
    rule = _qrule()
    _arm_queue_depth(svc, rule, depth=12, creator_id=42)

    triggered = await svc.evaluate_queue_depth()

    assert triggered == 1
    # 渠道通知（NotifyService 通用文本路径，通知失败本身由 NotifyService 吞掉）
    svc._notify.notify_text.assert_awaited_once()
    kw = svc._notify.notify_text.await_args.kwargs
    assert kw["event"] == "alert.queue_depth"
    assert "[告警:warning] 队列堆积告警" in kw["text"]
    assert "12" in kw["text"]
    # 命中记录：notifications 行（db-spec §16.6）
    svc.session.add.assert_called_once()
    hit = svc.session.add.call_args.args[0]
    assert hit.tenant_id == 8
    assert hit.user_id == 42  # 规则创建者（同租户在册解析）
    assert hit.type == "alert"
    assert hit.resource_type == "alert_rule"
    assert hit.resource_id == 5
    assert "12" in hit.content  # 内容含队列深度数字
    # 静默窗判据：规则行记最近命中时刻；命中行与时刻同事务提交
    assert rule.last_triggered_at is not None
    svc.session.commit.assert_awaited_once()
    # 评估口径=规则所属租户的排队任务深度
    svc._tasks.count_pending_by_tenant.assert_awaited_once_with(8)


@pytest.mark.asyncio
async def test_queue_depth_under_threshold_no_trigger():
    """排队深度 3 ≤ 阈值 10：不通知、不落命中行、不推进触发时刻"""
    svc = _service()
    rule = _qrule()
    _arm_queue_depth(svc, rule, depth=3)

    triggered = await svc.evaluate_queue_depth()

    assert triggered == 0
    svc._notify.notify_text.assert_not_awaited()
    svc.session.add.assert_not_called()
    svc.session.commit.assert_not_awaited()
    assert rule.last_triggered_at is None


# ---------------- 静默窗 ----------------
@pytest.mark.asyncio
async def test_queue_depth_silence_window_suppresses_repeat():
    """静默窗内重复命中不重复发送（GWT-105.1 后半）"""
    svc = _service()
    rule = _qrule(last_triggered_at=datetime.now())  # 60 分钟窗口内
    _arm_queue_depth(svc, rule, depth=12)

    triggered = await svc.evaluate_queue_depth()

    assert triggered == 0
    svc._notify.notify_text.assert_not_awaited()
    svc.session.add.assert_not_called()
    svc.session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_depth_silence_window_expired_triggers_again():
    """窗口过期（61 分钟前触发过）恢复发送"""
    svc = _service()
    rule = _qrule(last_triggered_at=datetime.now() - timedelta(minutes=61))
    _arm_queue_depth(svc, rule, depth=12)

    triggered = await svc.evaluate_queue_depth()

    assert triggered == 1
    svc._notify.notify_text.assert_awaited_once()


# ---------------- 创建者解析 ----------------
@pytest.mark.asyncio
async def test_queue_depth_creator_unresolvable_skips_entirely():
    """创建者软删/不在册：不落命中行、不发送、不静默改投（db-spec §16.6）"""
    svc = _service()
    rule = _qrule()
    _arm_queue_depth(svc, rule, depth=12, creator_id=None)

    triggered = await svc.evaluate_queue_depth()

    assert triggered == 0
    svc._notify.notify_text.assert_not_awaited()
    svc.session.add.assert_not_called()
    svc.session.commit.assert_not_awaited()
    assert rule.last_triggered_at is None
    svc._users.get_active_id_by_username_in_tenant.assert_awaited_once_with(8, "alice")


# ---------------- 失败面 ----------------
@pytest.mark.asyncio
async def test_queue_depth_eval_exception_swallowed():
    """规则读取异常吞掉（返回 0），不向上传播——不挡调度循环"""
    svc = _service()
    svc.repo.list_queue_depth_rules = AsyncMock(side_effect=RuntimeError("db down"))

    assert await svc.evaluate_queue_depth() == 0  # 未抛异常即通过


# ---------------- GWT-105.3：四类型无死规则 ----------------
@pytest.mark.asyncio
async def test_all_four_rule_types_have_trigger_path():
    """四类型命中条件成立时均有触发路径（通知已发出）——存在无路径类型即失败"""
    fired: dict[str, bool] = {t: False for t in RULE_TYPES}

    # consecutive_failures：最近 N 条全 failed（任务终态评估路径）
    svc = _service()
    rule = _qrule(id=1, rule_type="consecutive_failures", threshold=3, spider_name="example")
    svc.repo.list_active = AsyncMock(return_value=[rule])
    result = MagicMock()
    result.all.return_value = [("failed",), ("failed",), ("failed",)]
    svc.session.execute = AsyncMock(return_value=result)
    await svc.evaluate({"task_id": 10, "spider_name": "example", "status": "failed"})
    fired["consecutive_failures"] = svc._notify.notify_task_finished.await_count == 1

    # result_drop：上轮 100 → 本轮 10（降 90% ≥ 50%）
    svc = _service()
    rule = _qrule(id=2, rule_type="result_drop", threshold=50, spider_name="example")
    svc.repo.list_active = AsyncMock(return_value=[rule])
    result = MagicMock()
    result.scalar.return_value = 100
    svc.session.execute = AsyncMock(return_value=result)
    await svc.evaluate({"task_id": 11, "spider_name": "example", "status": "completed",
                        "result_count": 10})
    fired["result_drop"] = svc._notify.notify_task_finished.await_count == 1

    # task_timeout：400s > 5 分钟
    svc = _service()
    rule = _qrule(id=3, rule_type="task_timeout", threshold=5, spider_name="example")
    svc.repo.list_active = AsyncMock(return_value=[rule])
    await svc.evaluate({"task_id": 12, "spider_name": "example", "status": "completed",
                        "duration_seconds": 400})
    fired["task_timeout"] = svc._notify.notify_task_finished.await_count == 1

    # queue_depth：调度器周期评估路径（T-42 接通）
    svc = _service()
    rule = _qrule(id=4)
    _arm_queue_depth(svc, rule, depth=12, creator_id=42)
    await svc.evaluate_queue_depth()
    fired["queue_depth"] = svc._notify.notify_text.await_count == 1

    dead = [t for t, ok in fired.items() if not ok]
    assert not dead, f"存在配了规则却无触发路径的类型（死规则）: {dead}"


# ---------------- 调度器接线 ----------------
def _scheduler_tick_patches(repo: MagicMock, alert_svc: MagicMock, settings_mock):
    """_tick_once 公共桩：健康锁 + mock session + 仓储/告警服务桩"""
    class _HealthyLock:
        lost = False

    @asynccontextmanager
    async def _fake_lock(redis, key, ttl, **kwargs):
        yield _HealthyLock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=MagicMock())
    ctx.__aexit__ = AsyncMock(return_value=False)
    alert_cls = MagicMock(return_value=alert_svc)
    return (
        patch("backend.services.schedule_service.distributed_lock", _fake_lock),
        patch("backend.services.schedule_service.AsyncSession", return_value=ctx),
        patch("backend.services.schedule_service.SpiderScheduleRepository", return_value=repo),
        patch("backend.services.schedule_service.AlertService", alert_cls),
        patch.object(SpiderScheduler, "_engine", return_value=MagicMock()),
        patch("backend.services.schedule_service.settings", settings_mock),
    )


def _settings_mock():
    s = MagicMock()
    s.get = lambda key, default=None: 30 if key == "SCHEDULER.TICK_SECONDS" else default
    return s


@pytest.mark.asyncio
async def test_tick_once_invokes_queue_depth_evaluation_every_tick():
    """每 tick 调用 queue_depth 评估（无到期计划也评估——GWT-105.1 调度检查周期）"""
    scheduler = SpiderScheduler()
    repo = MagicMock()
    repo.list_due = AsyncMock(return_value=[])  # 无到期计划
    alert_svc = MagicMock()
    alert_svc.evaluate_queue_depth = AsyncMock(return_value=0)

    patches = _scheduler_tick_patches(repo, alert_svc, _settings_mock())
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
        await scheduler._tick_once()

    alert_svc.evaluate_queue_depth.assert_awaited_once()
    repo.list_due.assert_awaited_once()  # 调度主流程不受影响


@pytest.mark.asyncio
async def test_tick_once_alert_failure_does_not_block_scheduling():
    """queue_depth 评估抛异常：吞掉，本轮到期计划仍正常扫描触发"""
    scheduler = SpiderScheduler()
    repo = MagicMock()
    repo.list_due = AsyncMock(return_value=[])
    alert_svc = MagicMock()
    alert_svc.evaluate_queue_depth = AsyncMock(side_effect=RuntimeError("alert boom"))

    patches = _scheduler_tick_patches(repo, alert_svc, _settings_mock())
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
        await scheduler._tick_once()  # 未抛异常即通过

    repo.list_due.assert_awaited_once()


def test_queue_depth_config_log_path_retired():
    """SCHEDULER.QUEUE_DEPTH_WARN 配置日志路径退役：调度器不再有 _check_queue_depth"""
    assert not hasattr(SpiderScheduler, "_check_queue_depth")
