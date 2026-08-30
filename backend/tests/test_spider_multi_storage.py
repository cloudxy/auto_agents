"""阶段 4.2 单测 - 数据源多存储（redis 缓存 + csv 落盘）

约定：不连真实 MySQL/Redis，Repository/Redis 用 AsyncMock/MagicMock 桩。
覆盖：
- store_to 目标解析（字符串/列表/非法枚举/缺失）+ 配置默认兜底
- 消费者 _ingest 双写（命中目标追加任务级结果缓存列表 + TTL）
- finish_task 终态后 csv 落盘（列复用导出定义）
- store_status 目标状态查询
"""
import csv
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.spider_service import SpiderService, extract_store_targets  # noqa: E402
from backend.tasks.consumer import SpiderTaskConsumer  # noqa: E402
from platform_core.queues import TASK_RESULTS_KEY  # noqa: E402


def _service() -> SpiderService:
    svc = SpiderService.__new__(SpiderService)
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
        svc = _service()
        task = _task(params=None)
        with patch("backend.services.spider_service.settings") as fake_settings:
            fake_settings.get.return_value = ["csv"]
            assert svc._store_targets(task) == ["csv"]

    def test_params_override_config_default(self):
        svc = _service()
        task = _task(params=json.dumps({"store_to": "redis"}))
        with patch("backend.services.spider_service.settings") as fake_settings:
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
        svc = _service()
        task = _task(id=8, status="running", retry_count=2,
                     params=json.dumps({"urls": [], "store_to": "csv"}))
        finished = _task(id=8, status="completed", retry_count=2,
                         params=json.dumps({"urls": [], "store_to": "csv"}))
        svc.repo.get_by_id = AsyncMock(return_value=task)
        svc.repo.update = AsyncMock(return_value=finished)

        fake_redis = MagicMock()
        entry = json.dumps({
            "task_id": 8, "spider_name": "example", "item_type": "BaseItem",
            "item": {"url": "https://a.b", "title": "标题", "content": "正文", "source": "web"},
            "fetched_at": "2026-01-01T00:00:00Z",
        })
        fake_redis.lrange.return_value = [entry]

        with (
            patch("backend.services.spider_service.redis_client", return_value=fake_redis),
            patch("backend.services.spider_service.settings") as fake_settings,
        ):
            fake_settings.get.side_effect = lambda key, default=None: (
                str(tmp_path) if key == "STORAGE.DIR" else default
            )
            await svc.finish_task(8, "completed")

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
        svc = _service()
        task = _task(id=11, status="running", retry_count=2, params=None)
        finished = _task(id=11, status="completed", retry_count=2, params=None)
        svc.repo.get_by_id = AsyncMock(return_value=task)
        svc.repo.update = AsyncMock(return_value=finished)

        fake_redis = MagicMock()
        with (
            patch("backend.services.spider_service.redis_client", return_value=fake_redis),
            patch("backend.services.spider_service.settings") as fake_settings,
        ):
            fake_settings.get.side_effect = lambda key, default=None: (
                [] if key == "STORAGE.EXTRA_TARGETS" else default
            )
            await svc.finish_task(11, "completed")

        fake_redis.lrange.assert_not_called()  # 无 csv 目标不落盘
        assert list(tmp_path.iterdir()) == []


# ---------------- store_status ----------------
class TestStoreStatus:
    @pytest.mark.asyncio
    async def test_store_status_reports_targets_and_counts(self):
        svc = _service()
        task = _task(id=6, params=json.dumps({"urls": [], "store_to": ["csv", "redis"]}))
        svc.repo.get_by_id = AsyncMock(return_value=task)
        fake_redis = MagicMock()
        fake_redis.llen.return_value = 12

        with patch("backend.services.spider_service.redis_client", return_value=fake_redis):
            resp = await svc.store_status(6)

        assert resp.task_id == 6
        assert resp.targets == ["csv", "redis"]
        assert resp.redis_count == 12
        assert resp.csv_path is None  # 文件不存在时为 None
        fake_redis.llen.assert_called_once_with(TASK_RESULTS_KEY.format(task_id=6))

    @pytest.mark.asyncio
    async def test_store_status_no_targets(self):
        svc = _service()
        task = _task(id=12, params=None)
        svc.repo.get_by_id = AsyncMock(return_value=task)

        with patch("backend.services.spider_service.settings") as fake_settings:
            fake_settings.get.return_value = []
            resp = await svc.store_status(12)

        assert resp.targets == []
        assert resp.redis_count is None
        assert resp.csv_path is None
