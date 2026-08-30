"""数据源多存储测试（redis 缓存 + csv 落盘）

约定：不连真实 MySQL/Redis，Repository/Redis 用 AsyncMock/MagicMock 桩。
覆盖：
- store_to 目标解析（字符串/列表/非法枚举/缺失）+ 配置默认兜底
- 消费者 _ingest 双写（命中目标追加任务级结果缓存列表 + TTL）
- finish_task 终态后 csv 落盘（列复用导出定义）
- store_status 目标状态查询
"""
import asyncio
import csv
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.spider_common import extract_store_targets  # noqa: E402
from backend.services.spider_query_service import SpiderQueryService  # noqa: E402
from backend.services.spider_task_service import SpiderTaskService  # noqa: E402
from backend.services.spider_task_service import _SIDE_EFFECT_TASKS  # noqa: E402
from backend.tasks.consumer import SpiderTaskConsumer  # noqa: E402
from platform_core.queues import TASK_RESULTS_KEY  # noqa: E402


async def _drain_side_effects() -> None:
    """等待 finish_task spawn 的终态副作用后台任务完成（终态副作用已后台化）

    落盘在后台任务内执行，断言 CSV 产物前必须 drain。
    """
    pending = [t for t in _SIDE_EFFECT_TASKS if not t.done()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    await asyncio.sleep(0)


def _task_service() -> SpiderTaskService:
    """任务域桩：store_to 解析 / finish_task 落盘（挂 notifier）"""
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
    """查询域桩：store_status"""
    svc = SpiderQueryService.__new__(SpiderQueryService)
    svc.session = MagicMock()
    svc.repo = MagicMock()
    svc.result_repo = MagicMock()
    return svc


def _task(**overrides) -> MagicMock:
    defaults = dict(
        id=9, spider_name="example", status="running", priority="normal",
        result_count=0, retry_count=2, error_message=None, params=None,
        created_at=None, updated_at=None, started_at=None, completed_at=None,
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


# ---------------- store_to 目标解析 ----------------
class TestExtractStoreTargets:
    def test_string_and_list_forms(self):
        assert extract_store_targets(json.dumps({"store_to": "csv"})) == ["csv"]
        assert extract_store_targets(
            json.dumps({"store_to": ["redis", "csv"]})
        ) == ["redis", "csv"]

    def test_unknown_enum_filtered(self):
        # mongo/es 仅预留枚举不实现；非法值同样过滤
        assert extract_store_targets(json.dumps({"store_to": "mongo"})) == []
        assert extract_store_targets(json.dumps({"store_to": ["csv", "es"]})) == ["csv"]

    def test_missing_or_invalid_returns_empty(self):
        assert extract_store_targets(None) == []
        assert extract_store_targets(json.dumps({"urls": []})) == []
        assert extract_store_targets("not-json{") == []
        assert extract_store_targets(json.dumps({"store_to": 123})) == []

    def test_config_default_fallback(self):
        svc = _task_service()
        task = _task(params=None)
        with patch("backend.services.spider_task_service.settings") as fake_settings:
            fake_settings.get.return_value = ["csv"]
            assert svc._store_targets(task) == ["csv"]

    def test_params_override_config_default(self):
        svc = _task_service()
        task = _task(params=json.dumps({"store_to": "redis"}))
        with patch("backend.services.spider_task_service.settings") as fake_settings:
            fake_settings.get.return_value = ["csv"]
            assert svc._store_targets(task) == ["redis"]  # 任务级优先


# ---------------- 消费者双写 ----------------
class TestIngestMirror:
    @pytest.mark.asyncio
    async def test_ingest_mirrors_when_store_to_hit(self):
        consumer = SpiderTaskConsumer()
        consumer._redis = AsyncMock()
        consumer._engine = MagicMock()

        session = MagicMock()
        session.commit = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        result_repo = MagicMock()
        result_repo.create_for_task = AsyncMock()
        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(
            return_value=_task(id=3, params=json.dumps({"urls": [], "store_to": "csv"}))
        )

        msg = {
            "task_id": 3, "spider_name": "example", "item_type": "BaseItem",
            "item": {"url": "https://a.b", "title": "t"}, "fetched_at": "2026-01-01T00:00:00Z",
        }
        with (
            patch("backend.tasks.consumer.AsyncSession", return_value=session),
            patch("backend.tasks.consumer.SpiderResultRepository", return_value=result_repo),
            patch("backend.tasks.consumer.SpiderTaskRepository", return_value=task_repo),
            patch("backend.tasks.consumer.settings") as fake_settings,
        ):
            fake_settings.get.return_value = 604800
            await consumer._ingest(msg)

        key = TASK_RESULTS_KEY.format(task_id=3)
        consumer._redis.rpush.assert_awaited_once()
        pushed_key, payload = consumer._redis.rpush.await_args.args
        assert pushed_key == key
        assert json.loads(payload)["item"]["title"] == "t"
        consumer._redis.expire.assert_awaited_once_with(key, 604800)

    @pytest.mark.asyncio
    async def test_ingest_no_mirror_without_store_to(self):
        consumer = SpiderTaskConsumer()
        consumer._redis = AsyncMock()
        consumer._engine = MagicMock()

        session = MagicMock()
        session.commit = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        result_repo = MagicMock()
        result_repo.create_for_task = AsyncMock()
        task_repo = MagicMock()
        task_repo.get_by_id = AsyncMock(return_value=_task(id=4, params=None))

        msg = {"task_id": 4, "spider_name": "example", "item": {"url": "https://a.b"}}
        with (
            patch("backend.tasks.consumer.AsyncSession", return_value=session),
            patch("backend.tasks.consumer.SpiderResultRepository", return_value=result_repo),
            patch("backend.tasks.consumer.SpiderTaskRepository", return_value=task_repo),
        ):
            await consumer._ingest(msg)

        consumer._redis.rpush.assert_not_awaited()  # 未命中目标不双写


# ---------------- 终态 csv 落盘 ----------------
class TestFlushStore:
    @pytest.mark.asyncio
    async def test_finish_task_flushes_csv(self, tmp_path):
        svc = _task_service()
        task = _task(id=8, status="running", retry_count=2,
                     params=json.dumps({"urls": [], "store_to": "csv"}))
        finished = _task(id=8, status="completed", retry_count=2,
                         params=json.dumps({"urls": [], "store_to": "csv"}))
        svc.repo.get_by_id = AsyncMock(return_value=task)
        svc.repo.update = AsyncMock(return_value=finished)

        fake_redis = AsyncMock()
        entry = json.dumps({
            "task_id": 8, "spider_name": "example", "item_type": "BaseItem",
            "item": {"url": "https://a.b", "title": "标题", "content": "正文", "source": "web"},
            "fetched_at": "2026-01-01T00:00:00Z",
        })
        fake_redis.lrange.return_value = [entry]

        with (
            patch("backend.services.spider_task_service.get_async_redis", return_value=fake_redis),
            patch("backend.services.spider_task_service.settings") as fake_settings,
        ):
            fake_settings.get.side_effect = lambda key, default=None: (
                str(tmp_path) if key == "STORAGE.DIR" else default
            )
            await svc.finish_task(8, "completed")
            await _drain_side_effects()  # patch 块内 drain：副作用需在桩环境下执行

        out_file = tmp_path / "task_8.csv"
        assert out_file.is_file()
        with open(out_file, "r", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        assert rows[0]["url"] == "https://a.b"
        assert rows[0]["title"] == "标题"
        assert rows[0]["task_id"] == "8"

    @pytest.mark.asyncio
    async def test_finish_task_without_csv_target_skips_flush(self, tmp_path):
        svc = _task_service()
        task = _task(id=11, status="running", retry_count=2, params=None)
        finished = _task(id=11, status="completed", retry_count=2, params=None)
        svc.repo.get_by_id = AsyncMock(return_value=task)
        svc.repo.update = AsyncMock(return_value=finished)

        fake_redis = AsyncMock()
        with (
            patch("backend.services.spider_task_service.get_async_redis", return_value=fake_redis),
            patch("backend.services.spider_task_service.settings") as fake_settings,
        ):
            fake_settings.get.side_effect = lambda key, default=None: (
                [] if key == "STORAGE.EXTRA_TARGETS" else default
            )
            await svc.finish_task(11, "completed")
            await _drain_side_effects()  # patch 块内 drain：等副作用任务执行完再断言无落盘动作

        fake_redis.lrange.assert_not_called()  # 无 csv 目标不落盘
        assert list(tmp_path.iterdir()) == []


# ---------------- store_status ----------------
class TestStoreStatus:
    @pytest.mark.asyncio
    async def test_store_status_reports_targets_and_counts(self):
        svc = _query_service()
        task = _task(id=6, params=json.dumps({"urls": [], "store_to": ["csv", "redis"]}))
        svc.repo.get_by_id = AsyncMock(return_value=task)
        # 期 4 R11 收口：store_status 改异步门面 get_async_redis().llen，
        # 同步 redis_client 桩随之退役；llen 为协程需 AsyncMock
        fake_redis = MagicMock()
        fake_redis.llen = AsyncMock(return_value=12)

        with patch("backend.services.spider_query_service.get_async_redis", return_value=fake_redis):
            resp = await svc.store_status(6)

        assert resp.task_id == 6
        assert resp.targets == ["csv", "redis"]
        assert resp.redis_count == 12
        assert resp.csv_path is None  # 文件不存在时为 None
        fake_redis.llen.assert_called_once_with(TASK_RESULTS_KEY.format(task_id=6))

    @pytest.mark.asyncio
    async def test_store_status_no_targets(self):
        svc = _query_service()
        task = _task(id=12, params=None)
        svc.repo.get_by_id = AsyncMock(return_value=task)

        with patch("backend.services.spider_query_service.settings") as fake_settings:
            fake_settings.get.return_value = []
            resp = await svc.store_status(12)

        assert resp.targets == []
        assert resp.redis_count is None
        assert resp.csv_path is None
