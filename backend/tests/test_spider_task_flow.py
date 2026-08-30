"""爬虫任务全生命周期测试 - 失败重试 / 终态通知 / 结果导出 / 定时调度 / 日志隔离

约定：不连接真实 MySQL/Redis，Service 测试用 AsyncMock 桩。
"""
import asyncio
import csv
import io
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.notify_service import NotifyService
from backend.services.schedule_service import (
    ScheduleService,
    SpiderScheduler,
    next_fire_time,
    validate_cron,
)
from backend.services.spider_query_service import SpiderQueryService
from backend.services.spider_task_service import _SIDE_EFFECT_TASKS, SpiderTaskService
from platform_core.exceptions import BusinessException, NotFoundException


async def _drain_side_effects() -> None:
    """等待 finish_task spawn 的终态副作用后台任务全部完成（终态副作用已后台化）

    断言通知/落盘等副作用前必须 drain，否则任务残留在事件循环，
    断言时机不确定且 loop 关闭时会产生 pending 任务警告。
    """
    pending = [t for t in _SIDE_EFFECT_TASKS if not t.done()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    await asyncio.sleep(0)  # 让 done_callback（清理强引用集）执行


def _task(**overrides) -> MagicMock:
    """构造带齐 SpiderTaskResponse 所需属性的任务桩"""
    base = dict(
        id=1,
        spider_name="example",
        status="running",
        priority="normal",
        result_count=0,
        retry_count=0,
        error_message=None,
        params='{"urls": ["https://example.com"]}',
        created_at=None,
        updated_at=None,
        started_at=None,
        completed_at=None,
    )
    base.update(overrides)
    return MagicMock(**base)


def _task_service() -> SpiderTaskService:
    """任务域桩：finish_task 等编排方法（挂 notifier 断言终态通知）"""
    svc = SpiderTaskService.__new__(SpiderTaskService)
    svc.session = MagicMock()
    svc.session.commit = AsyncMock()
    svc.session.refresh = AsyncMock()
    svc.repo = MagicMock()
    svc.result_repo = MagicMock()
    svc.notifier = MagicMock()
    svc.notifier.notify_task_finished = AsyncMock()
    return svc


def _query_service() -> SpiderQueryService:
    """查询域桩：结果导出 / 任务日志"""
    svc = SpiderQueryService.__new__(SpiderQueryService)
    svc.session = MagicMock()
    svc.session.commit = AsyncMock()
    svc.session.refresh = AsyncMock()
    svc.repo = MagicMock()
    svc.result_repo = MagicMock()
    return svc


class TestFinishTaskRetry:
    """finish_task 失败自动重试 + 终态通知"""

    @pytest.mark.asyncio
    async def test_failed_under_limit_requeues_without_notify(self):
        svc = _task_service()
        task = _task(status="running", retry_count=0)
        updated = _task(status="pending", retry_count=1)
        svc.repo.get_by_id = AsyncMock(return_value=task)
        svc.repo.update = AsyncMock(return_value=updated)

        fake_redis = AsyncMock()
        with (
            patch("backend.services.spider_task_service.get_async_redis", return_value=fake_redis),
            patch("backend.services.spider_task_service._spawn_side_effect") as mock_spawn,
        ):
            result = await svc.finish_task(1, "failed", error_message="boom")

        # 回到 pending 重新入队：不推终态、不通知、不触发副作用后台任务
        assert result.status == "pending"
        svc.repo.update.assert_awaited_once()
        kwargs = svc.repo.update.call_args.kwargs
        assert kwargs["status"] == "pending"
        assert kwargs["retry_count"] == 1
        # 重试退避：改 ZSET 延迟入队（不再直投主队列）
        fake_redis.rpush.assert_not_called()
        fake_redis.zadd.assert_called_once()
        zset_key, mapping = fake_redis.zadd.call_args.args
        assert zset_key == "spider:retry_zset"
        ((message, score),) = mapping.items()
        payload = json.loads(message)
        assert payload["task_id"] == 1
        assert payload["priority"] == "normal"  # 重试消息携带优先级，供扫描侧选队
        # 第 1 次重试退避 1s：到期时间戳 ≈ now + 1
        assert 0 < score - time.time() <= 1.5
        svc.notifier.notify_task_finished.assert_not_called()
        mock_spawn.assert_not_called()  # 重试路径不触发终态副作用

    @pytest.mark.asyncio
    async def test_failed_at_limit_finalizes_and_notifies(self):
        svc = _task_service()
        task = _task(status="running", retry_count=2)
        final = _task(status="failed", retry_count=2, error_message="boom")
        svc.repo.get_by_id = AsyncMock(return_value=task)
        svc.repo.update = AsyncMock(return_value=final)

        fake_redis = AsyncMock()
        with patch("backend.services.spider_task_service.get_async_redis", return_value=fake_redis):
            result = await svc.finish_task(1, "failed", error_message="boom")
            await _drain_side_effects()  # patch 块内 drain：副作用需在桩环境下执行

        assert result.status == "failed"
        kwargs = svc.repo.update.call_args.kwargs
        assert kwargs["status"] == "failed"
        assert "retry_count" not in kwargs  # 不再重试
        fake_redis.zadd.assert_not_called()  # 达上限不再延迟入队
        svc.notifier.notify_task_finished.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_completed_notifies_with_item_count(self):
        svc = _task_service()
        task = _task(status="running")
        final = _task(status="completed", result_count=5)
        svc.repo.get_by_id = AsyncMock(return_value=task)
        svc.repo.update = AsyncMock(return_value=final)

        fake_redis = AsyncMock()
        with patch("backend.services.spider_task_service.get_async_redis", return_value=fake_redis):
            await svc.finish_task(1, "completed", item_count=5)
            await _drain_side_effects()  # patch 块内 drain：副作用需在桩环境下执行

        kwargs = svc.repo.update.call_args.kwargs
        assert kwargs["result_count"] == 5  # 回调上报值覆盖
        svc.notifier.notify_task_finished.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_repeat_callback_idempotent(self):
        svc = _task_service()
        svc.repo.get_by_id = AsyncMock(return_value=_task(status="completed"))
        with patch("backend.services.spider_task_service._spawn_side_effect") as mock_spawn:
            await svc.finish_task(1, "completed")
        svc.repo.update.assert_not_called()
        svc.notifier.notify_task_finished.assert_not_called()
        mock_spawn.assert_not_called()  # 终态幂等守卫：重复回调不 spawn 副作用


class TestNotifyService:
    """终态通知渠道分发"""

    @pytest.mark.asyncio
    async def test_disabled_skips_all_channels(self):
        svc = NotifyService()
        svc._enabled = False
        svc._notify_log = MagicMock()
        await svc.notify_task_finished(1, "example", "failed")
        svc._notify_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_webhook_skipped_without_url(self):
        svc = NotifyService()
        svc._channels = ["webhook"]
        svc._webhook_url = ""
        # 无 URL 直接跳过，不抛异常
        await svc.notify_task_finished(1, "example", "completed")

    @pytest.mark.asyncio
    async def test_webhook_posts_payload(self):
        svc = NotifyService()
        svc._channels = ["webhook"]
        svc._webhook_url = "http://127.0.0.1:1/hook"
        resp = MagicMock(status_code=200, text="ok")
        client = MagicMock()
        client.post = AsyncMock(return_value=resp)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        with patch("backend.services.notify_service.httpx.AsyncClient", return_value=client) as mock_cls:
            await svc.notify_task_finished(9, "example", "failed", error_message="x")
        # trust_env=False 防本机代理拦截（Clash 陷阱）
        assert mock_cls.call_args.kwargs.get("trust_env") is False
        payload = client.post.call_args.kwargs["json"]
        assert payload["task_id"] == 9 and payload["status"] == "failed"

    @pytest.mark.asyncio
    async def test_channel_error_swallowed(self):
        svc = NotifyService()
        svc._channels = ["webhook"]
        svc._webhook_url = "http://127.0.0.1:1/hook"
        with patch.object(NotifyService, "_notify_webhook", AsyncMock(side_effect=RuntimeError("net"))):
            # 渠道异常不得上抛
            await svc.notify_task_finished(1, "example", "failed")


class TestExportResults:
    """结果导出（csv / json）—— id 游标分批流式产出，内容与全量导出逐字节一致"""

    @staticmethod
    def _agen(rows):
        """iter_by_task 桩：逐行产出 rows 的异步生成器"""
        async def _gen(task_id):
            for r in rows:
                yield r
        return _gen(0)

    @pytest.mark.asyncio
    async def test_export_csv_with_bom(self):
        svc = _query_service()
        svc.repo.get_by_id = AsyncMock(return_value=_task())
        row = MagicMock(
            id=1, task_id=1, spider_name="example", url="https://e.com",
            title="标题", content="内容", source="web", item_type="BaseItem",
            extra=None, created_at=None,
        )
        svc.result_repo.iter_by_task = MagicMock(side_effect=lambda tid: self._agen([row]))

        stream, filename, media_type = await svc.export_results(1, "csv")
        content = b"".join([chunk async for chunk in stream])
        assert filename == "task_1_results.csv"
        assert media_type == "text/csv"
        assert content.startswith(b"\xef\xbb\xbf")  # utf-8-sig BOM（Excel 兼容）
        assert "标题".encode("utf-8") in content

    @pytest.mark.asyncio
    async def test_export_json_parseable(self):
        svc = _query_service()
        svc.repo.get_by_id = AsyncMock(return_value=_task())
        row = MagicMock(
            id=1, task_id=1, spider_name="example", url=None, title=None,
            content="{}", source=None, item_type=None, extra=None, created_at=None,
        )
        svc.result_repo.iter_by_task = MagicMock(side_effect=lambda tid: self._agen([row]))

        stream, filename, _ = await svc.export_results(1, "json")
        content = b"".join([chunk async for chunk in stream])
        assert filename == "task_1_results.json"
        data = json.loads(content)
        assert len(data) == 1 and data[0]["content"] == "{}"

    @pytest.mark.asyncio
    async def test_export_csv_matches_full_reference(self):
        """分批流式 csv 与全量一次性编码逐字节一致（含 BOM/表头/列序）"""
        svc = _query_service()
        svc.repo.get_by_id = AsyncMock(return_value=_task())
        rows = [
            MagicMock(
                id=1, task_id=1, spider_name="example", url="https://e.com",
                title="标题", content="内容,含逗号", source="web", item_type="BaseItem",
                extra='{"k": "v"}', created_at=datetime(2026, 8, 29, 10, 0, 0),
            ),
            MagicMock(
                id=2, task_id=1, spider_name="example", url=None, title=None,
                content=None, source=None, item_type=None, extra=None, created_at=None,
            ),
        ]
        svc.result_repo.iter_by_task = MagicMock(side_effect=lambda tid: self._agen(rows))

        stream, _, _ = await svc.export_results(1, "csv")
        content = b"".join([chunk async for chunk in stream])

        # 独立参照实现：全量构建（旧实现等价形式）
        ref_rows = [
            {
                "id": 1, "task_id": 1, "spider_name": "example", "url": "https://e.com",
                "title": "标题", "content": "内容,含逗号", "source": "web",
                "item_type": "BaseItem", "extra": '{"k": "v"}',
                "created_at": "2026-08-29T10:00:00",
            },
            {
                "id": 2, "task_id": 1, "spider_name": "example", "url": None,
                "title": None, "content": None, "source": None,
                "item_type": None, "extra": None, "created_at": None,
            },
        ]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=SpiderQueryService._EXPORT_COLUMNS)
        writer.writeheader()
        for row in ref_rows:
            writer.writerow(row)
        assert content == buf.getvalue().encode("utf-8-sig")

    @pytest.mark.asyncio
    async def test_export_json_matches_full_reference(self):
        """分批流式 json 与 json.dumps(rows, indent=2) 逐字节一致"""
        svc = _query_service()
        svc.repo.get_by_id = AsyncMock(return_value=_task())
        rows = [
            MagicMock(
                id=1, task_id=1, spider_name="example", url="https://e.com",
                title="标题", content="内容", source="web", item_type="BaseItem",
                extra=None, created_at=datetime(2026, 8, 29, 10, 0, 0),
            ),
            MagicMock(
                id=2, task_id=1, spider_name="example", url=None, title=None,
                content=None, source=None, item_type=None, extra=None, created_at=None,
            ),
        ]
        svc.result_repo.iter_by_task = MagicMock(side_effect=lambda tid: self._agen(rows))

        stream, _, media_type = await svc.export_results(1, "json")
        content = b"".join([chunk async for chunk in stream])

        ref_rows = [
            {
                "id": 1, "task_id": 1, "spider_name": "example", "url": "https://e.com",
                "title": "标题", "content": "内容", "source": "web",
                "item_type": "BaseItem", "extra": None,
                "created_at": "2026-08-29T10:00:00",
            },
            {
                "id": 2, "task_id": 1, "spider_name": "example", "url": None,
                "title": None, "content": None, "source": None,
                "item_type": None, "extra": None, "created_at": None,
            },
        ]
        expected = json.dumps(ref_rows, ensure_ascii=False, indent=2).encode("utf-8")
        assert media_type == "application/json"
        assert content == expected

    @pytest.mark.asyncio
    async def test_export_json_empty_task_is_bare_empty_array(self):
        svc = _query_service()
        svc.repo.get_by_id = AsyncMock(return_value=_task())
        svc.result_repo.iter_by_task = MagicMock(side_effect=lambda tid: self._agen([]))
        stream, _, _ = await svc.export_results(1, "json")
        assert b"".join([c async for c in stream]) == b"[]"

    @pytest.mark.asyncio
    async def test_export_missing_task_raises(self):
        svc = _query_service()
        svc.repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(NotFoundException):
            await svc.export_results(999, "csv")

    @pytest.mark.asyncio
    async def test_export_bad_format_raises(self):
        svc = _query_service()
        svc.repo.get_by_id = AsyncMock(return_value=_task())
        with pytest.raises(BusinessException):
            await svc.export_results(1, "xlsx")


class TestTaskLogOffset:
    """任务日志按任务隔离（偏移量切区间）"""

    @pytest.mark.asyncio
    async def test_logs_read_from_offset(self, tmp_path):
        log_file = tmp_path / "spider.log"
        log_file.write_text("old-task-line\nnew-task-line-1\nnew-task-line-2\n", encoding="utf-8")

        svc = _query_service()
        svc.repo.get_by_id = AsyncMock(return_value=_task())
        offset = len("old-task-line\n".encode("utf-8"))

        with patch("backend.services.spider_query_service.resolve_spider_log_path", return_value=str(log_file)):
            with patch.object(SpiderQueryService, "_task_log_offset", AsyncMock(return_value=offset)):
                resp = await svc.task_logs(1, lines=200)

        assert resp.lines == ["new-task-line-1", "new-task-line-2"]

    @pytest.mark.asyncio
    async def test_logs_fallback_without_offset(self, tmp_path):
        log_file = tmp_path / "spider.log"
        log_file.write_text("line-a\nline-b\n", encoding="utf-8")

        svc = _query_service()
        svc.repo.get_by_id = AsyncMock(return_value=_task())
        with patch("backend.services.spider_query_service.resolve_spider_log_path", return_value=str(log_file)):
            with patch.object(SpiderQueryService, "_task_log_offset", AsyncMock(return_value=None)):
                resp = await svc.task_logs(1)
        assert resp.lines == ["line-a", "line-b"]


class TestScheduleService:
    """定时调度计划 CRUD"""

    def _schedule_service(self) -> ScheduleService:
        svc = ScheduleService(session=MagicMock())
        svc.repo = MagicMock()
        svc.session.commit = AsyncMock()
        svc.session.refresh = AsyncMock()
        return svc

    def test_validate_cron(self):
        assert validate_cron("*/5 * * * *") is True
        assert validate_cron("0 8 * * 1-5") is True
        assert validate_cron("not a cron") is False

    def test_next_fire_time_future(self):
        from datetime import datetime
        assert next_fire_time("* * * * *") > datetime.now()

    @pytest.mark.asyncio
    async def test_create_rejects_unknown_spider(self):
        from platform_core.schemas.spider import ScheduleRequest
        svc = self._schedule_service()
        with pytest.raises(BusinessException):
            await svc.create_schedule(
                ScheduleRequest(spider_name="no_such_spider", cron_expr="* * * * *")
            )

    @pytest.mark.asyncio
    async def test_create_rejects_invalid_cron(self):
        from platform_core.schemas.spider import ScheduleRequest
        svc = self._schedule_service()
        with pytest.raises(BusinessException):
            await svc.create_schedule(
                ScheduleRequest(spider_name="example", cron_expr="bad expr !")
            )

    @pytest.mark.asyncio
    async def test_create_rejects_duplicate_spider(self):
        from platform_core.schemas.spider import ScheduleRequest
        svc = self._schedule_service()
        svc.repo.find_by_spider = AsyncMock(return_value=MagicMock(id=3))
        with pytest.raises(BusinessException):
            await svc.create_schedule(
                ScheduleRequest(spider_name="example", cron_expr="* * * * *")
            )

    @pytest.mark.asyncio
    async def test_create_success_computes_next_run(self):
        from platform_core.schemas.spider import ScheduleRequest
        svc = self._schedule_service()
        svc.repo.find_by_spider = AsyncMock(return_value=None)
        created = MagicMock(
            id=1, spider_name="example", cron_expr="*/10 * * * *", params=None,
            enabled=True, last_run_at=None, next_run_at=datetime.now(),
            created_at=None, updated_at=None,
        )
        svc.repo.create = AsyncMock(return_value=created)
        resp = await svc.create_schedule(
            ScheduleRequest(spider_name="example", cron_expr="*/10 * * * *")
        )
        assert resp.id == 1
        kwargs = svc.repo.create.call_args.kwargs
        assert kwargs["next_run_at"] is not None

    @pytest.mark.asyncio
    async def test_update_disable_clears_next_run(self):
        from platform_core.schemas.spider import ScheduleUpdateRequest
        svc = self._schedule_service()
        schedule = MagicMock(id=2, cron_expr="* * * * *", enabled=True)
        svc.repo.get_by_id = AsyncMock(return_value=schedule)
        updated = MagicMock(
            id=2, spider_name="example", cron_expr="* * * * *", params=None,
            enabled=False, last_run_at=None, next_run_at=None,
            created_at=None, updated_at=None,
        )
        svc.repo.update = AsyncMock(return_value=updated)
        await svc.update_schedule(2, ScheduleUpdateRequest(enabled=False))
        kwargs = svc.repo.update.call_args.kwargs
        assert kwargs["enabled"] is False
        assert kwargs["next_run_at"] is None

    @pytest.mark.asyncio
    async def test_delete_missing_raises(self):
        svc = self._schedule_service()
        svc.repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(NotFoundException):
            await svc.delete_schedule(999)


class TestSpiderSchedulerLockRenewal:
    """调度锁续期（m-5）：renewal 后台续期启用 + lost 早退（宁可少跑不可双跑）"""

    @pytest.mark.asyncio
    async def test_tick_once_enables_renewal_and_exits_when_lock_lost(self):
        """renewal=lock_ttl/3 传入共享锁；续期失败（lost）后本轮不再触发任何计划"""
        scheduler = SpiderScheduler()
        captured: dict = {}

        class _LostLock:
            lost = True

        @asynccontextmanager
        async def _fake_lock(redis, key, ttl, **kwargs):
            captured["ttl"] = ttl
            captured["renewal"] = kwargs.get("renewal")
            yield _LostLock()

        repo = MagicMock()
        repo.list_due = AsyncMock(return_value=[
            MagicMock(id=1, spider_name="example", cron_expr="* * * * *", params=None)
        ])
        repo.update = AsyncMock()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("backend.services.schedule_service.distributed_lock", _fake_lock),
            patch("backend.services.schedule_service.AsyncSession", return_value=ctx),
            patch("backend.services.schedule_service.SpiderScheduleRepository", return_value=repo),
            patch.object(SpiderScheduler, "_engine", return_value=MagicMock()),
            patch("backend.services.schedule_service.settings") as mock_settings,
        ):
            mock_settings.get = lambda key, default=None: (
                30 if key == "SCHEDULER.TICK_SECONDS" else default
            )
            await scheduler._tick_once()

        # tick=30 → min_ttl=60 → lock_ttl=max(默认 60, 60)=60 → renewal=60/3=20
        assert captured["renewal"] == 20.0
        repo.list_due.assert_awaited_once()   # 已进入临界区并扫描到期计划
        repo.update.assert_not_awaited()      # lost → 触发前早退，未入队未推进

    @pytest.mark.asyncio
    async def test_tick_once_fires_all_when_lock_not_lost(self):
        """锁未丢失（既有语义）：到期计划正常触发"""
        scheduler = SpiderScheduler()

        class _HealthyLock:
            lost = False

        @asynccontextmanager
        async def _fake_lock(redis, key, ttl, **kwargs):
            yield _HealthyLock()

        repo = MagicMock()
        repo.list_due = AsyncMock(return_value=[
            MagicMock(id=1, spider_name="example", cron_expr="* * * * *", params=None)
        ])
        repo.update = AsyncMock()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        ctx.__aexit__ = AsyncMock(return_value=False)
        busy_service = MagicMock()
        busy_service.enqueue = AsyncMock()

        with (
            patch("backend.services.schedule_service.distributed_lock", _fake_lock),
            patch("backend.services.schedule_service.AsyncSession", return_value=ctx),
            patch("backend.services.schedule_service.SpiderScheduleRepository", return_value=repo),
            patch.object(SpiderScheduler, "_engine", return_value=MagicMock()),
            patch("backend.services.schedule_service.settings") as mock_settings,
            patch("backend.services.schedule_service.SpiderService", return_value=busy_service),
        ):
            mock_settings.get = lambda key, default=None: (
                30 if key == "SCHEDULER.TICK_SECONDS" else default
            )
            await scheduler._tick_once()

        repo.update.assert_awaited_once()  # 入队成功后推进触发时刻


class TestSpiderSchedulerFire:
    """调度触发：入队被拒仍推进触发时刻（防重复触发风暴）"""

    @pytest.mark.asyncio
    async def test_fire_advances_next_run_on_conflict(self):
        scheduler = SpiderScheduler()
        session = MagicMock()
        repo = MagicMock()
        repo.update = AsyncMock()
        schedule = MagicMock(id=1, spider_name="example", cron_expr="* * * * *", params=None)

        busy_service = MagicMock()
        busy_service.enqueue = AsyncMock(side_effect=BusinessException("已有进行中的任务"))
        with patch("backend.services.schedule_service.SpiderService", return_value=busy_service):
            await scheduler._fire(session, repo, schedule, next_fire_time("* * * * *"))

        repo.update.assert_awaited_once()
        kwargs = repo.update.call_args.kwargs
        assert kwargs["next_run_at"] is not None
        assert kwargs["last_run_at"] is not None
