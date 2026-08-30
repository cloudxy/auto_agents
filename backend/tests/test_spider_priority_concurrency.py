"""阶段 4.1 单测 - 任务优先级 + 并发控制（活跃键 SET 化 / meta 归属）

约定：不连真实 MySQL/Redis，Repository/Redis 用 AsyncMock/MagicMock 桩。
覆盖：
- 优先级队列键约定（task_queue / TASK_QUEUE 兼容常量）
- enqueue 并发槽位守卫（满拒绝 / 释放后放行）+ 优先级透传
- 消费者多队列 blpop 顺序（high > normal > low）+ 旧活跃键清理
- 分发载荷携带 task_id（结果归属走请求 meta）
- 终态/删除后 SREM 释放槽位
- scrapy 侧：队列条目解析、TaskAttribution 中间件、StorePipeline SET 兜底
"""
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SCRAPY_DIR = PROJECT_ROOT / "scrapy"
if str(SCRAPY_DIR) not in sys.path:
    sys.path.insert(0, str(SCRAPY_DIR))

from backend.services.spider_service import SpiderService  # noqa: E402
from backend.tasks.consumer import SpiderTaskConsumer  # noqa: E402
from platform_core.queues import (  # noqa: E402
    LEGACY_ACTIVE_TASK_PREFIX,
    TASK_QUEUE,
    TASK_QUEUE_PRIORITIES,
    task_queue,
)


def _service() -> SpiderService:
    svc = SpiderService.__new__(SpiderService)
    svc.session = MagicMock()
    svc.session.commit = AsyncMock()
    svc.session.refresh = AsyncMock()
    svc.repo = MagicMock()
    svc.result_repo = MagicMock()
    svc.notifier = MagicMock()
    return svc


def _task(**overrides) -> MagicMock:
    """可被 SpiderTaskResponse.model_validate 的任务实体桩"""
    defaults = dict(
        id=9, spider_name="example", status="pending", priority="normal",
        result_count=0, retry_count=0, error_message=None,
        created_at=None, updated_at=None, started_at=None, completed_at=None,
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


# ---------------- 队列键约定 ----------------
class TestTaskQueueKeys:
    def test_task_queue_by_priority(self):
        assert task_queue("high") == "spider:task_queue:high"
        assert task_queue("normal") == "spider:task_queue:normal"
        assert task_queue("low") == "spider:task_queue:low"

    def test_unknown_priority_falls_back_to_normal(self):
        assert task_queue("urgent") == "spider:task_queue:normal"
        assert task_queue() == "spider:task_queue:normal"

    def test_legacy_constant_keeps_default_reference(self):
        assert TASK_QUEUE == task_queue("normal")
        assert TASK_QUEUE_PRIORITIES == ("high", "normal", "low")

    def test_legacy_active_prefix_is_old_string_key(self):
        # 新 SET 键带 s（active_tasks），旧 string 键前缀不带（用于启动清理）
        assert LEGACY_ACTIVE_TASK_PREFIX == "spider:active_task:"


# ---------------- enqueue 并发槽位 + 优先级 ----------------
class TestEnqueueConcurrency:
    @pytest.mark.asyncio
    async def test_enqueue_rejected_when_slots_full(self):
        svc = _service()
        fake_redis = MagicMock()
        fake_redis.scard.return_value = 2  # 默认上限 2，已满

        with (
            patch("backend.services.spider_service.redis_client", return_value=fake_redis),
            patch("backend.services.spider_service.settings") as fake_settings,
        ):
            fake_settings.get.return_value = 2
            from platform_core.exceptions import BusinessException
            with pytest.raises(BusinessException):
                await svc.enqueue("example", priority="high")
        svc.repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_enqueue_allowed_after_slot_released(self):
        svc = _service()
        fake_redis = MagicMock()
        fake_redis.scard.return_value = 1  # 释放一个槽位后未满

        task = _task(id=9)
        svc.repo.create = AsyncMock(return_value=task)
        with (
            patch("backend.services.spider_service.redis_client", return_value=fake_redis),
            patch("backend.services.spider_service.settings") as fake_settings,
        ):
            fake_settings.get.return_value = 2
            resp = await svc.enqueue("example", params='{"urls": ["https://a.b"]}', priority="high")
        assert resp.id == 9
        kwargs = svc.repo.create.call_args.kwargs
        assert kwargs["priority"] == "high"
        # 投递到对应优先级队列
        fake_redis.rpush.assert_called_once()
        queue_key = fake_redis.rpush.call_args.args[0]
        assert queue_key == "spider:task_queue:high"

    @pytest.mark.asyncio
    async def test_enqueue_redis_down_allows_through(self):
        svc = _service()
        fake_redis = MagicMock()
        fake_redis.scard.side_effect = ConnectionError("redis down")

        task = _task(id=10)
        svc.repo.create = AsyncMock(return_value=task)
        with (
            patch("backend.services.spider_service.redis_client", return_value=fake_redis),
            patch("backend.services.spider_service.settings") as fake_settings,
        ):
            fake_settings.get.return_value = 2
            resp = await svc.enqueue("example")
        assert resp.id == 10  # Redis 抖动放行，失败兜底在投递路径

    @pytest.mark.asyncio
    async def test_finish_task_releases_slot_via_srem(self):
        svc = _service()
        task = _task(id=7, status="running")
        svc.repo.get_by_id = AsyncMock(return_value=task)
        finished = _task(id=7, status="completed", result_count=3)
        svc.repo.update = AsyncMock(return_value=finished)
        svc.notifier.notify_task_finished = AsyncMock()
        fake_redis = MagicMock()

        with patch("backend.services.spider_service.redis_client", return_value=fake_redis):
            await svc.finish_task(7, "completed")
        fake_redis.srem.assert_called_once_with("spider:active_tasks:example", 7)


# ---------------- 消费者：多队列顺序 / 旧键清理 / 载荷 ----------------
class TestConsumerPriority:
    @pytest.mark.asyncio
    async def test_dispatch_loop_blpop_order_is_high_normal_low(self):
        consumer = SpiderTaskConsumer()
        consumer._running = True
        fake_redis = MagicMock()

        async def _blpop(queues, timeout=None):
            consumer._running = False  # 首轮后退出循环
            assert list(queues) == [
                "spider:task_queue:high",
                "spider:task_queue:normal",
                "spider:task_queue:low",
            ]
            return None

        fake_redis.blpop = _blpop
        consumer._redis = fake_redis
        await consumer._dispatch_loop()

    @pytest.mark.asyncio
    async def test_purge_legacy_active_keys(self):
        consumer = SpiderTaskConsumer()
        fake_redis = MagicMock()

        async def _scan_iter(match=None, count=None):
            assert match == f"{LEGACY_ACTIVE_TASK_PREFIX}*"
            yield "spider:active_task:example"
            yield "spider:active_task:zhihu_feed"

        fake_redis.scan_iter = _scan_iter
        fake_redis.delete = AsyncMock()
        consumer._redis = fake_redis
        await consumer._purge_legacy_active_keys()
        fake_redis.delete.assert_awaited_once_with(
            "spider:active_task:example", "spider:active_task:zhihu_feed"
        )

    @pytest.mark.asyncio
    async def test_dispatch_payload_carries_task_id(self):
        consumer = SpiderTaskConsumer()
        fake_redis = MagicMock()
        fake_redis.sadd = AsyncMock()
        fake_redis.expire = AsyncMock()
        fake_redis.rpush = AsyncMock()
        fake_redis.set = AsyncMock()
        consumer._redis = fake_redis

        repo = MagicMock()
        repo.update = AsyncMock(return_value=MagicMock(id=5))
        repo.get_by_id = AsyncMock(return_value=MagicMock(id=5))
        session = MagicMock()
        session.commit = AsyncMock()

        with (
            patch("backend.tasks.consumer.AsyncSession", return_value=session),
            patch("backend.tasks.consumer.SpiderTaskRepository", return_value=repo),
            patch.object(SpiderTaskConsumer, "_engine", return_value=MagicMock()),
            patch.object(SpiderTaskConsumer, "_record_log_offset", new=AsyncMock()),
        ):
            # AsyncSession 需支持 async with
            session.__aenter__ = AsyncMock(return_value=session)
            session.__aexit__ = AsyncMock(return_value=None)
            await consumer._dispatch({
                "task_id": 5,
                "spider_name": "example",
                "params": json.dumps({"urls": ["https://a.b/1"]}),
            })

        fake_redis.sadd.assert_awaited_once_with("spider:active_tasks:example", 5)
        fake_redis.rpush.assert_awaited_once()
        queue_key, payload = fake_redis.rpush.call_args.args
        assert queue_key == "example:start_urls"
        entry = json.loads(payload)
        assert entry["url"] == "https://a.b/1"
        assert entry["task_id"] == 5  # 结果归属走请求 meta 的契约


# ---------------- scrapy 侧：队列条目解析 + meta 归属 ----------------
class TestScrapyAttribution:
    def test_parse_queue_entry_json_and_plain(self):
        from spiders.base import parse_queue_entry

        url, task_id, extra = parse_queue_entry(
            json.dumps({"url": "https://a.b", "task_id": 3, "selectors": [{"name": "t"}]})
        )
        assert url == "https://a.b"
        assert task_id == 3
        assert extra == {"selectors": [{"name": "t"}]}

        # 纯 URL 条目兼容：无 task_id
        url2, task_id2, extra2 = parse_queue_entry("https://plain.url")
        assert (url2, task_id2, extra2) == ("https://plain.url", None, {})

    def test_make_request_injects_task_meta(self):
        from spiders.base import TaskAwareRedisSpider

        spider = TaskAwareRedisSpider.__new__(TaskAwareRedisSpider)
        req = spider.make_request_from_data(json.dumps({"url": "https://a.b", "task_id": 8}))
        assert req.meta["task_id"] == 8

        plain = spider.make_request_from_data("https://plain.url")
        assert "task_id" not in plain.meta

    def test_attribution_middleware_injects_task_id_into_items(self):
        from scrapy import Item, Field
        from middlewares import TaskAttributionSpiderMiddleware

        class DemoItem(Item):
            url = Field()
            task_id = Field()

        mw = TaskAttributionSpiderMiddleware()
        response = MagicMock()
        response.meta = {"task_id": 42}
        item_without = DemoItem(url="https://a.b")
        item_with = DemoItem(url="https://c.d", task_id=1)

        out = list(mw.process_spider_output(response, [item_without, item_with, "request"], None))
        assert out[0]["task_id"] == 42  # 缺失才注入
        assert out[1]["task_id"] == 1  # 已有不覆盖
        assert out[2] == "request"  # 非 Item 透传

    def test_store_pipeline_prefers_item_task_id(self):
        from pipelines import StorePipeline
        from scrapy import Item, Field

        class DemoItem(Item):
            url = Field()
            task_id = Field()

        pipe = StorePipeline.__new__(StorePipeline)
        pipe.redis = MagicMock()
        spider = MagicMock()
        spider.name = "example"

        item = DemoItem(url="https://a.b", task_id=11)
        pipe.process_item(item, spider)
        pipe.redis.smembers.assert_not_called()  # Item 自带归属，不查活跃集合
        pushed = json.loads(pipe.redis.rpush.call_args.args[1])
        assert pushed["task_id"] == 11

    def test_store_pipeline_set_fallback_single_member(self):
        from pipelines import StorePipeline
        from scrapy import Item, Field

        class DemoItem(Item):
            url = Field()
            task_id = Field()

        pipe = StorePipeline.__new__(StorePipeline)
        pipe.redis = MagicMock()
        pipe.redis.smembers.return_value = {"21"}
        spider = MagicMock()
        spider.name = "example"

        item = DemoItem(url="https://a.b")
        pipe.process_item(item, spider)
        pushed = json.loads(pipe.redis.rpush.call_args.args[1])
        assert pushed["task_id"] == 21  # 唯一成员才归属

    def test_store_pipeline_set_fallback_multi_member_keeps_none(self):
        from pipelines import StorePipeline
        from scrapy import Item, Field

        class DemoItem(Item):
            url = Field()
            task_id = Field()

        pipe = StorePipeline.__new__(StorePipeline)
        pipe.redis = MagicMock()
        pipe.redis.smembers.return_value = {"21", "22"}
        spider = MagicMock()
        spider.name = "example"

        item = DemoItem(url="https://a.b")
        pipe.process_item(item, spider)
        pushed = json.loads(pipe.redis.rpush.call_args.args[1])
        assert pushed["task_id"] is None  # 多成员防误关联
