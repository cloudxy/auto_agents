"""阶段 1 平台能力测试 - 失败重试 / 终态通知 / 结果导出 / 定时调度 / 日志隔离

约定：不连接真实 MySQL/Redis，Service 测试用 AsyncMock 桩。
"""
import json
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
from backend.services.spider_service import SpiderService
from platform_core.exceptions import BusinessException, NotFoundException


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


def _service() -> SpiderService:
    svc = SpiderService(session=MagicMock())
    svc.repo = MagicMock()
    svc.result_repo = MagicMock()
    svc.session.commit = AsyncMock()
    svc.session.refresh = AsyncMock()
    svc.notifier = MagicMock()
    svc.notifier.notify_task_finished = AsyncMock()
    return svc


class TestFinishTaskRetry:
    """finish_task 失败自动重试 + 终态通知"""

    @pytest.mark.asyncio
    async def test_failed_under_limit_requeues_without_notify(self):
        svc = _service()
        task = _task(status="running", retry_count=0)
        updated = _task(status="pending", retry_count=1)
        svc.repo.get_by_id = AsyncMock(return_value=task)
        svc.repo.update = AsyncMock(return_value=updated)

        with patch("backend.services.spider_service.redis_client") as mock_redis:
            result = await svc.finish_task(1, "failed", error_message="boom")

        # 回到 pending 重新入队：不推终态、不通知
        assert result.status == "pending"
        svc.repo.update.assert_awaited_once()
        kwargs = svc.repo.update.call_args.kwargs
        assert kwargs["status"] == "pending"
        assert kwargs["retry_count"] == 1
        mock_redis.return_value.rpush.assert_called_once()  # 重试投递
        svc.notifier.notify_task_finished.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_at_limit_finalizes_and_notifies(self):
        svc = _service()
        task = _task(status="running", retry_count=2)
        final = _task(status="failed", retry_count=2, error_message="boom")
        svc.repo.get_by_id = AsyncMock(return_value=task)
        svc.repo.update = AsyncMock(return_value=final)

        with patch("backend.services.spider_service.redis_client"):
            result = await svc.finish_task(1, "failed", error_message="boom")

        assert result.status == "failed"
        kwargs = svc.repo.update.call_args.kwargs
        assert kwargs["status"] == "failed"
        assert "retry_count" not in kwargs  # 不再重试
        svc.notifier.notify_task_finished.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_completed_notifies_with_item_count(self):
        svc = _service()
        task = _task(status="running")
        final = _task(status="completed", result_count=5)
        svc.repo.get_by_id = AsyncMock(return_value=task)
        svc.repo.update = AsyncMock(return_value=final)

        with patch("backend.services.spider_service.redis_client"):
            await svc.finish_task(1, "completed", item_count=5)

        kwargs = svc.repo.update.call_args.kwargs
        assert kwargs["result_count"] == 5  # 回调上报值覆盖
        svc.notifier.notify_task_finished.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_repeat_callback_idempotent(self):
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_task(status="completed"))
        await svc.finish_task(1, "completed")
        svc.repo.update.assert_not_called()
        svc.notifier.notify_task_finished.assert_not_called()


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
    """结果导出（csv / json）"""

    @pytest.mark.asyncio
    async def test_export_csv_with_bom(self):
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_task())
        row = MagicMock(
            id=1, task_id=1, spider_name="example", url="https://e.com",
            title="标题", content="内容", source="web", item_type="BaseItem",
            extra=None, created_at=None,
        )
        svc.result_repo.all_by_task = AsyncMock(return_value=[row])

        content, filename, media_type = await svc.export_results(1, "csv")
        assert filename == "task_1_results.csv"
        assert media_type == "text/csv"
        assert content.startswith(b"\xef\xbb\xbf")  # utf-8-sig BOM（Excel 兼容）
        assert "标题".encode("utf-8") in content

    @pytest.mark.asyncio
    async def test_export_json_parseable(self):
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_task())
        row = MagicMock(
            id=1, task_id=1, spider_name="example", url=None, title=None,
            content="{}", source=None, item_type=None, extra=None, created_at=None,
        )
        svc.result_repo.all_by_task = AsyncMock(return_value=[row])

        content, filename, _ = await svc.export_results(1, "json")
        assert filename == "task_1_results.json"
        data = json.loads(content)
        assert len(data) == 1 and data[0]["content"] == "{}"

    @pytest.mark.asyncio
    async def test_export_missing_task_raises(self):
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(NotFoundException):
            await svc.export_results(999, "csv")

    @pytest.mark.asyncio
    async def test_export_bad_format_raises(self):
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_task())
        with pytest.raises(BusinessException):
            await svc.export_results(1, "xlsx")


class TestTaskLogOffset:
    """任务日志按任务隔离（偏移量切区间）"""

    @pytest.mark.asyncio
    async def test_logs_read_from_offset(self, tmp_path):
        log_file = tmp_path / "spider.log"
        log_file.write_text("old-task-line\nnew-task-line-1\nnew-task-line-2\n", encoding="utf-8")

        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_task())
        offset = len("old-task-line\n".encode("utf-8"))

        with patch("backend.services.spider_service.resolve_spider_log_path", return_value=str(log_file)):
            with patch.object(SpiderService, "_task_log_offset", return_value=offset):
                resp = await svc.task_logs(1, lines=200)

        assert resp.lines == ["new-task-line-1", "new-task-line-2"]

    @pytest.mark.asyncio
    async def test_logs_fallback_without_offset(self, tmp_path):
        log_file = tmp_path / "spider.log"
        log_file.write_text("line-a\nline-b\n", encoding="utf-8")

        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_task())
        with patch("backend.services.spider_service.resolve_spider_log_path", return_value=str(log_file)):
            with patch.object(SpiderService, "_task_log_offset", return_value=None):
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
