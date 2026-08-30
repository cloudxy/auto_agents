"""终态副作用后台化专项单测（webhook 主路径减负）

覆盖：
- 主路径剥离：finish_task 返回后恰好 spawn 一个副作用任务，通知不再同步 await
- 副作用入参：_run_finish_side_effects 消费终态标量快照（脱离 ORM）
- 异常隔离：副作用任务异常不影响主路径返回；完成后清理强引用集（异常落日志不静默）
- CancelledError 安全：取消穿透不被 except Exception 吞；强引用集正常清理
- _flush_store 文件 IO 下线程：目录创建 + CSV 写承接给 asyncio.to_thread
"""

import asyncio
import csv
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.spider_task_service import (
    _SIDE_EFFECT_TASKS,
    SpiderTaskService,
)


def _service() -> SpiderTaskService:
    """手工构造任务子 Service（期 4 独立化后不再经门面）"""
    svc = SpiderTaskService.__new__(SpiderTaskService)
    svc.session = MagicMock()
    svc.session.commit = AsyncMock()
    svc.session.refresh = AsyncMock()
    svc.repo = MagicMock()
    svc.result_repo = MagicMock()
    svc.notifier = MagicMock()
    svc.notifier.notify_task_finished = AsyncMock()
    return svc


def _task(**overrides) -> MagicMock:
    defaults = dict(
        id=21, spider_name="example", status="running", priority="normal",
        result_count=0, retry_count=0, error_message=None, params=None,
        created_at=None, updated_at=None, started_at=None, completed_at=None,
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


def _snapshot(**overrides) -> dict:
    """与 finish_task 主路径提取的终态标量快照同构"""
    base = dict(
        id=21, spider_name="example", status="completed",
        result_count=0, retry_count=0, error_message=None, params=None,
        started_at=None, completed_at=None,
    )
    base.update(overrides)
    return base


async def _drain_side_effects() -> None:
    """等待已 spawn 的副作用任务全部完成并让清理回调执行"""
    pending = [t for t in _SIDE_EFFECT_TASKS if not t.done()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    await asyncio.sleep(0)


# ---------------- 主路径剥离：spawn 一次 + 立即返回 ----------------
class TestSpawnOnFinish:
    @pytest.mark.asyncio
    async def test_finish_task_spawns_exactly_one_side_effect(self):
        """终态推进后 spawn 恰好一个副作用任务；主路径返回时通知尚未执行"""
        svc = _service()
        final = _task(status="completed", result_count=7)
        svc.repo.get_by_id = AsyncMock(return_value=_task(status="running"))
        svc.repo.update = AsyncMock(return_value=final)

        with (
            patch("backend.services.spider_task_service.get_async_redis", return_value=AsyncMock()),
            patch("backend.services.spider_task_service._spawn_side_effect") as mock_spawn,
        ):
            resp = await svc.finish_task(21, "completed", item_count=7)

        assert resp.status == "completed"
        mock_spawn.assert_called_once()  # 主路径 spawn 恰好一个副作用任务
        coro = mock_spawn.call_args.args[0]
        svc.notifier.notify_task_finished.assert_not_called()  # 通知已剥离出主路径
        coro.close()  # 未消费协程显式关闭，避免 RuntimeWarning

    @pytest.mark.asyncio
    async def test_spawned_coroutine_notifies_from_snapshot(self):
        """spawn 的协程可独立执行：通知入参取自终态标量快照（不触碰 ORM）"""
        svc = _service()
        final = _task(status="completed", result_count=3)
        svc.repo.get_by_id = AsyncMock(return_value=_task(status="running"))
        svc.repo.update = AsyncMock(return_value=final)

        with (
            patch("backend.services.spider_task_service.get_async_redis", return_value=AsyncMock()),
            patch("backend.services.spider_task_service._spawn_side_effect") as mock_spawn,
            patch("backend.services.spider_task_service.settings") as fake_settings,
        ):
            fake_settings.get.side_effect = lambda key, default=None: (
                [] if key == "STORAGE.EXTRA_TARGETS" else default
            )
            await svc.finish_task(21, "completed")
            coro = mock_spawn.call_args.args[0]
            assert "finish_side_effects" in coro.__qualname__
            snapshot = coro.cr_frame.f_locals["snapshot"]
            assert snapshot == {
                "id": 21, "spider_name": "example", "status": "completed",
                "result_count": 3, "retry_count": 0, "error_message": None,
                "params": None, "started_at": None, "completed_at": None,
            }
            await coro  # 直接执行副作用协程（不经 create_task）

        svc.notifier.notify_task_finished.assert_awaited_once_with(
            task_id=21, spider_name="example", status="completed",
            result_count=3, retry_count=0, error_message=None,
        )

    @pytest.mark.asyncio
    async def test_real_spawn_completes_and_clears_registry(self):
        """真实 spawn 全生命周期：返回时在强引用集中 → 完成后自动清理"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_task(status="running"))
        svc.repo.update = AsyncMock(return_value=_task(status="completed"))

        with (
            patch("backend.services.spider_task_service.get_async_redis", return_value=AsyncMock()),
            patch("backend.services.spider_task_service.settings") as fake_settings,
        ):
            fake_settings.get.side_effect = lambda key, default=None: (
                [] if key == "STORAGE.EXTRA_TARGETS" else default
            )
            await svc.finish_task(21, "completed")
            assert len(_SIDE_EFFECT_TASKS) == 1  # 任务被强引用（防 GC）
            await _drain_side_effects()

        assert _SIDE_EFFECT_TASKS == set()  # 完成回调已清理强引用集
        svc.notifier.notify_task_finished.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_repeat_callback_never_spawns_twice(self):
        """幂等：已终态任务重复回调命中终态守卫，不重复 spawn 副作用"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_task(status="completed"))

        with (
            patch("backend.services.spider_task_service.get_async_redis", return_value=AsyncMock()),
            patch("backend.services.spider_task_service._spawn_side_effect") as mock_spawn,
        ):
            await svc.finish_task(21, "completed")

        mock_spawn.assert_not_called()
        svc.repo.update.assert_not_called()
        svc.notifier.notify_task_finished.assert_not_called()


# ---------------- 异常隔离：副作用炸了主路径照常返回 ----------------
class TestSideEffectIsolation:
    @pytest.mark.asyncio
    async def test_side_effect_exception_does_not_break_main_path(self):
        """副作用协程异常不影响 finish_task 返回；异常留在任务内由回调记录"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_task(status="running"))
        svc.repo.update = AsyncMock(return_value=_task(status="completed"))

        async def _boom(self, snapshot):
            raise RuntimeError("side effect boom")

        with (
            patch("backend.services.spider_task_service.get_async_redis", return_value=AsyncMock()),
            patch.object(SpiderTaskService, "_run_finish_side_effects", _boom),
        ):
            resp = await svc.finish_task(21, "completed")

        assert resp.status == "completed"  # 主路径不受副作用异常影响
        pending = list(_SIDE_EFFECT_TASKS)
        assert len(pending) == 1
        results = await asyncio.gather(*pending, return_exceptions=True)
        assert isinstance(results[0], RuntimeError)  # 异常留在任务内（done_callback 已记录）
        await asyncio.sleep(0)
        assert _SIDE_EFFECT_TASKS == set()  # 异常完成后同样清理强引用集

    @pytest.mark.asyncio
    async def test_flush_failure_does_not_block_notify(self):
        """副作用协程内段落隔离：CSV 落盘失败不阻断终态通知执行"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_task(status="running"))
        svc.repo.update = AsyncMock(return_value=_task(status="completed"))

        with (
            patch("backend.services.spider_task_service.get_async_redis", return_value=AsyncMock()),
            patch("backend.services.spider_task_service.settings") as fake_settings,
            patch.object(
                SpiderTaskService, "_flush_store",
                AsyncMock(side_effect=ConnectionError("disk boom")),
            ),
        ):
            fake_settings.get.side_effect = lambda key, default=None: (
                [] if key == "STORAGE.EXTRA_TARGETS" else default
            )
            await svc.finish_task(21, "completed")
            await _drain_side_effects()

        svc.notifier.notify_task_finished.assert_awaited_once()  # 落盘炸了通知照发


# ---------------- 取消安全 ----------------
class TestCancellation:
    @pytest.mark.asyncio
    async def test_cancelled_side_effect_is_cleaned_up(self):
        """取消副作用任务：CancelledError 正常收尾，强引用集清理无残留"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_task(status="running"))
        svc.repo.update = AsyncMock(return_value=_task(status="completed"))

        with patch("backend.services.spider_task_service.get_async_redis", return_value=AsyncMock()):
            await svc.finish_task(21, "completed")

        assert len(_SIDE_EFFECT_TASKS) == 1
        for t in list(_SIDE_EFFECT_TASKS):
            t.cancel()
        results = await asyncio.gather(*_SIDE_EFFECT_TASKS, return_exceptions=True)
        assert all(isinstance(r, asyncio.CancelledError) for r in results)
        await asyncio.sleep(0)
        assert _SIDE_EFFECT_TASKS == set()

    @pytest.mark.asyncio
    async def test_flush_store_cancel_error_propagates(self):
        """落盘内 CancelledError 穿透（不进 except Exception），取消语义不被吞"""
        svc = _service()

        async def _cancelled(self, task):
            raise asyncio.CancelledError()

        with patch.object(SpiderTaskService, "_flush_store", _cancelled):
            with pytest.raises(asyncio.CancelledError):
                await svc._run_finish_side_effects(_snapshot())


# ---------------- 落盘文件 IO 下线程 ----------------
class TestFlushStoreThread:
    @pytest.mark.asyncio
    async def test_flush_store_delegates_file_io_to_thread(self, tmp_path):
        """CSV 落盘走 asyncio.to_thread：目录创建+写入承接给线程池（patch 断言）"""
        svc = _service()
        task = SimpleNamespace(id=33, spider_name="example", params=json.dumps({"store_to": "csv"}))
        fake_redis = AsyncMock()
        fake_redis.lrange.return_value = []
        fake_to_thread = AsyncMock(return_value=str(tmp_path / "task_33.csv"))

        with (
            patch("backend.services.spider_task_service.get_async_redis", return_value=fake_redis),
            patch("backend.services.spider_task_service.settings") as fake_settings,
            patch("backend.services.spider_task_service.asyncio.to_thread", fake_to_thread),
        ):
            fake_settings.get.side_effect = lambda key, default=None: (
                str(tmp_path) if key == "STORAGE.DIR" else default
            )
            await svc._flush_store(task)

        fake_to_thread.assert_awaited_once()
        fn, out_dir, task_id, rows = fake_to_thread.await_args.args
        assert fn is SpiderTaskService._write_csv_sync  # 写入函数整体下沉线程池
        assert out_dir == str(tmp_path)
        assert task_id == 33
        assert rows == []
        assert not (tmp_path / "task_33.csv").exists()  # 事件循环内未直接写文件

    def test_write_csv_sync_produces_bom_csv(self, tmp_path):
        """_write_csv_sync 与旧内联实现一致：BOM + 表头列序 + 行内容"""
        rows = [{
            "id": None, "task_id": 33, "spider_name": "example", "url": "https://a.b",
            "title": "标题", "content": None, "source": None, "item_type": "BaseItem",
            "extra": None, "created_at": None,
        }]
        path = SpiderTaskService._write_csv_sync(str(tmp_path), 33, rows)

        assert path == str(tmp_path / "task_33.csv")
        raw = Path(path).read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf")  # utf-8-sig BOM（Excel 兼容）
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames == list(SpiderTaskService._EXPORT_COLUMNS)
            written = list(reader)
        assert written[0]["title"] == "标题"
        assert written[0]["task_id"] == "33"
