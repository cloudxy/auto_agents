"""阶段 6 单测 - 后端 CRUD 缺口补齐（定义完整 CRUD / 入队注册表校验 / 任务可编辑 / 数据中心与审计查询）

约定：不连真实 MySQL/Redis，Repository/Redis 用 AsyncMock/MagicMock 桩；
patch 点与既有 phase 测试一致（backend.services.spider_service.<name>）。
覆盖：
- 定义 CRUD：创建（source=manual）/ 重名拒绝 / 元信息编辑 /
  原子条件删除（m1：引用拒绝、成功、缺失；DELETE NOT EXISTS rowcount 语义）
- 入队注册表校验：DB 停用拒绝 / DB 无记录 yml 兑底放行 / DB+YML 均无拒绝 / DB 异常跳过校验
- 任务可编辑（B1/M1 回归）：pending 改优先级（LREM+rpush 队列搬迁）/
  仅改参数同队列消息更新（读队列断言）/ params+priority 同改跨队列搬迁 /
  LREM 未命中不重投 / rpush 失败 lpush 补偿 / 补偿失败任务置 failed / running 拒绝
- 控制端点契约（M2 回归）：缺 body 返回 422
- 跨任务结果查询：过滤参数透传与响应构造 / 结果删除（缺失拒绝、成功）
- 审计日志查询：过滤参数透传 / 响应构造
- 调度创建：DB 停用拒绝（DB 优先校验）
"""
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.audit_service import AuditService
from backend.services.schedule_service import ScheduleService
from backend.services.spider_service import SpiderService
from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.schemas.spider import (
    DefinitionCreateRequest,
    DefinitionUpdateMetaRequest,
    TaskUpdateRequest,
)

OLD_PARAMS = '{"urls": ["https://a.b"]}'
NEW_PARAMS = '{"urls": ["https://c.d"]}'


def _msg(task_id: int, spider_name: str, params: str) -> str:
    """构造与 enqueue/_relocate_queue_message 完全一致的任务消息"""
    return json.dumps(
        {"task_id": task_id, "spider_name": spider_name, "params": params},
        ensure_ascii=False,
    )


class _FakeQueueRedis:
    """极简 Redis list 语义桩：内存维护优先级队列，支持读队列内容断言"""

    def __init__(self):
        self.queues: dict = {}

    def rpush(self, key, value):
        self.queues.setdefault(key, []).append(value)
        return 1

    def lpush(self, key, value):
        self.queues.setdefault(key, []).insert(0, value)
        return 1

    def lrem(self, key, count, value):
        q = self.queues.get(key, [])
        if value in q:
            q.remove(value)
            return 1
        return 0

    def items(self, key):
        return list(self.queues.get(key, []))


class _RpushBrokenRedis(_FakeQueueRedis):
    """rpush 恒失败（M1：LREM 成功后投递新队列失败）"""

    def rpush(self, key, value):
        raise ConnectionError("redis rpush down")


class _CompensationBrokenRedis(_RpushBrokenRedis):
    """rpush 与 lpush 均失败（M1：补偿回队列也失败）"""

    def lpush(self, key, value):
        raise ConnectionError("redis lpush down")


def _service() -> SpiderService:
    svc = SpiderService.__new__(SpiderService)
    svc.session = MagicMock()
    svc.session.commit = AsyncMock()
    svc.session.refresh = AsyncMock()
    svc.repo = MagicMock()
    svc.result_repo = MagicMock()
    svc.notifier = MagicMock()
    return svc


def _definition(**overrides) -> MagicMock:
    """可被 SpiderDefinitionResponse.model_validate 的定义实体桩"""
    d = MagicMock(
        id=5, title="通用采集示例", type="web",
        description="", enabled=True, source="yml_seed",
        created_at=None, updated_at=None,
    )
    d.name = overrides.pop("name", "example")  # name 是 MagicMock 保留参数，需显式赋值
    for k, v in overrides.items():
        setattr(d, k, v)
    return d


def _task(**overrides) -> MagicMock:
    """可被 SpiderTaskResponse.model_validate 的任务实体桩"""
    defaults = dict(
        id=9, spider_name="example", status="pending", priority="normal",
        result_count=0, retry_count=0, error_message=None,
        params='{"urls": ["https://a.b"]}',
        created_at=None, updated_at=None, started_at=None, completed_at=None,
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


# ---------------- 定义完整 CRUD ----------------
class TestDefinitionCrud:
    @pytest.mark.asyncio
    async def test_create_success_marks_manual_source(self):
        svc = _service()
        created = _definition(id=99)
        created.name = "new_spider"
        repo = MagicMock()
        repo.get_by_name = AsyncMock(return_value=None)
        repo.create = AsyncMock(return_value=created)

        with patch("backend.services.spider_service.SpiderDefinitionRepository", return_value=repo):
            resp = await svc.create_definition(
                DefinitionCreateRequest(name="new_spider", title="新爬虫", type="api")
            )

        kwargs = repo.create.call_args.kwargs
        assert kwargs["source"] == "manual"  # 手动登记来源标记
        assert kwargs["enabled"] is True
        assert resp.id == 99
        svc.session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_rejects_duplicate_name(self):
        svc = _service()
        repo = MagicMock()
        repo.get_by_name = AsyncMock(return_value=_definition(id=5))

        with patch("backend.services.spider_service.SpiderDefinitionRepository", return_value=repo):
            with pytest.raises(BusinessException):
                await svc.create_definition(
                    DefinitionCreateRequest(name="example", title="重复", type="web")
                )
        repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_meta_writes_fields(self):
        svc = _service()
        updated = _definition(id=5, title="新标题")
        repo = MagicMock()
        repo.get_by_name = AsyncMock(return_value=_definition(id=5))
        repo.update = AsyncMock(return_value=updated)

        with patch("backend.services.spider_service.SpiderDefinitionRepository", return_value=repo):
            resp = await svc.update_definition_meta(
                "example", DefinitionUpdateMetaRequest(title="新标题")
            )

        repo.update.assert_awaited_once_with(5, title="新标题")
        assert resp.title == "新标题"

    @pytest.mark.asyncio
    async def test_update_meta_missing_raises(self):
        svc = _service()
        repo = MagicMock()
        repo.get_by_name = AsyncMock(return_value=None)

        with patch("backend.services.spider_service.SpiderDefinitionRepository", return_value=repo):
            with pytest.raises(NotFoundException):
                await svc.update_definition_meta(
                    "ghost", DefinitionUpdateMetaRequest(title="x")
                )

    @pytest.mark.asyncio
    async def test_delete_rejected_when_tasks_exist(self):
        """m1 回归：原子条件删除 rowcount=0 且定义存在 → 被引用拒绝（先插任务再删的等价态）"""
        svc = _service()
        repo = MagicMock()
        repo.delete_if_unreferenced = AsyncMock(return_value=False)
        repo.get_by_name = AsyncMock(return_value=_definition(id=5))
        svc.repo.count_by_spider = AsyncMock(return_value=3)

        with patch("backend.services.spider_service.SpiderDefinitionRepository", return_value=repo):
            with pytest.raises(BusinessException):
                await svc.delete_definition("example")

        repo.delete_if_unreferenced.assert_awaited_once_with("example")
        svc.session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_success_when_unreferenced(self):
        """m1 回归：原子条件删除 rowcount=1 → 删除成功（无需二次查询）"""
        svc = _service()
        repo = MagicMock()
        repo.delete_if_unreferenced = AsyncMock(return_value=True)
        repo.get_by_name = AsyncMock(return_value=_definition(id=5))

        with patch("backend.services.spider_service.SpiderDefinitionRepository", return_value=repo):
            result = await svc.delete_definition("example")

        assert result == {"name": "example", "deleted": True}
        repo.get_by_name.assert_not_awaited()
        svc.session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_missing_raises(self):
        """m1 回归：原子条件删除 rowcount=0 且定义不存在 → NotFoundException"""
        svc = _service()
        repo = MagicMock()
        repo.delete_if_unreferenced = AsyncMock(return_value=False)
        repo.get_by_name = AsyncMock(return_value=None)

        with patch("backend.services.spider_service.SpiderDefinitionRepository", return_value=repo):
            with pytest.raises(NotFoundException):
                await svc.delete_definition("ghost")


# ---------------- 入队注册表校验（DB 优先，yml 兜底） ----------------
class TestEnqueueRegistryValidation:
    @pytest.mark.asyncio
    async def test_rejected_when_disabled_in_db(self):
        svc = _service()
        repo = MagicMock()
        repo.get_by_name = AsyncMock(return_value=_definition(enabled=False))
        fake_redis = MagicMock()
        fake_redis.scard.return_value = 0

        with (
            patch("backend.services.spider_service.SpiderDefinitionRepository", return_value=repo),
            patch("backend.services.spider_service.redis_client", return_value=fake_redis),
            patch("backend.services.spider_service.settings") as fake_settings,
        ):
            fake_settings.get.return_value = 2
            with pytest.raises(BusinessException):
                await svc.enqueue("example")

        svc.repo.create.assert_not_called()  # 停用爬虫不入库不投递
        fake_redis.rpush.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_to_yml_seed_when_db_missing(self):
        svc = _service()
        repo = MagicMock()
        repo.get_by_name = AsyncMock(return_value=None)
        fake_redis = MagicMock()
        fake_redis.scard.return_value = 0
        task = _task(id=40)
        svc.repo.create = AsyncMock(return_value=task)

        with (
            patch("backend.services.spider_service.SpiderDefinitionRepository", return_value=repo),
            patch("backend.services.spider_service.redis_client", return_value=fake_redis),
            patch("backend.services.spider_service.settings") as fake_settings,
        ):
            fake_settings.get.side_effect = lambda k, d=None: (
                2 if k == "SPIDER_MAX_CONCURRENT_PER_SPIDER"
                else ({"example": {}} if k == "SPIDERS" else d)
            )
            resp = await svc.enqueue("example")

        assert resp.id == 40  # yml 种子兜底放行（存量 yml-only 爬虫不破坏）

    @pytest.mark.asyncio
    async def test_rejected_when_unregistered_in_db_and_yml(self):
        svc = _service()
        repo = MagicMock()
        repo.get_by_name = AsyncMock(return_value=None)
        fake_redis = MagicMock()

        with (
            patch("backend.services.spider_service.SpiderDefinitionRepository", return_value=repo),
            patch("backend.services.spider_service.redis_client", return_value=fake_redis),
            patch("backend.services.spider_service.settings") as fake_settings,
        ):
            fake_settings.get.side_effect = lambda k, d=None: (
                2 if k == "SPIDER_MAX_CONCURRENT_PER_SPIDER"
                else ({} if k == "SPIDERS" else d)
            )
            with pytest.raises(BusinessException):
                await svc.enqueue("ghost_spider")

        svc.repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_db_error_skips_validation(self):
        """DB 故障不阻断入队主流程（跳过注册表校验）"""
        svc = _service()
        repo = MagicMock()
        repo.get_by_name = AsyncMock(side_effect=RuntimeError("db down"))
        fake_redis = MagicMock()
        fake_redis.scard.return_value = 0
        task = _task(id=41)
        svc.repo.create = AsyncMock(return_value=task)

        with (
            patch("backend.services.spider_service.SpiderDefinitionRepository", return_value=repo),
            patch("backend.services.spider_service.redis_client", return_value=fake_redis),
            patch("backend.services.spider_service.settings") as fake_settings,
        ):
            fake_settings.get.return_value = 2
            resp = await svc.enqueue("example")

        assert resp.id == 41


# ---------------- 任务可编辑（PATCH /tasks/{task_id}） ----------------
class TestUpdateTask:
    def _pending(self) -> MagicMock:
        return _task(id=12, status="pending", priority="normal",
                     params='{"urls": ["https://a.b"]}')

    @pytest.mark.asyncio
    async def test_priority_change_relocates_queue(self):
        svc = _service()
        task = self._pending()
        updated = _task(id=12, status="pending", priority="high")
        svc.repo.get_by_id = AsyncMock(return_value=task)
        svc.repo.update = AsyncMock(return_value=updated)
        fake_redis = MagicMock()
        fake_redis.lrem.return_value = 1

        with patch("backend.services.spider_service.redis_client", return_value=fake_redis):
            resp = await svc.update_task(12, priority="high")

        assert resp.priority == "high"
        svc.repo.update.assert_awaited_once_with(12, priority="high")
        old_msg = json.dumps(
            {"task_id": 12, "spider_name": "example", "params": '{"urls": ["https://a.b"]}'},
            ensure_ascii=False,
        )
        new_msg = json.dumps(
            {"task_id": 12, "spider_name": "example", "params": '{"urls": ["https://a.b"]}'},
            ensure_ascii=False,
        )
        fake_redis.lrem.assert_called_once_with("spider:task_queue:normal", 1, old_msg)
        fake_redis.rpush.assert_called_once_with("spider:task_queue:high", new_msg)

    @pytest.mark.asyncio
    async def test_no_repush_when_lrem_misses(self):
        """LREM 未命中（消息已被消费/从未投递）时不重投，避免重复消费"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=self._pending())
        svc.repo.update = AsyncMock(return_value=_task(id=12, priority="high"))
        fake_redis = MagicMock()
        fake_redis.lrem.return_value = 0

        with patch("backend.services.spider_service.redis_client", return_value=fake_redis):
            await svc.update_task(12, priority="high")

        fake_redis.rpush.assert_not_called()

    @pytest.mark.asyncio
    async def test_running_task_rejected(self):
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_task(id=13, status="running"))

        with pytest.raises(BusinessException):
            await svc.update_task(13, priority="high")
        svc.repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_params_only_change_updates_queue_message(self):
        """B1 回归：仅改 params 时同队列消息同步更新为新 params（读队列内容断言）"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=self._pending())
        svc.repo.update = AsyncMock(return_value=_task(id=12, params=NEW_PARAMS))
        fake_redis = _FakeQueueRedis()
        fake_redis.queues["spider:task_queue:normal"] = [_msg(12, "example", OLD_PARAMS)]

        with patch("backend.services.spider_service.redis_client", return_value=fake_redis):
            await svc.update_task(12, params=NEW_PARAMS)

        kwargs = svc.repo.update.call_args.kwargs
        assert kwargs == {"params": NEW_PARAMS}
        # 同队列原地替换：normal 队列只剩新 params 消息，不产生跨队列搬迁
        assert fake_redis.items("spider:task_queue:normal") == [_msg(12, "example", NEW_PARAMS)]
        assert "spider:task_queue:high" not in fake_redis.queues

    @pytest.mark.asyncio
    async def test_params_and_priority_change_relocates_message(self):
        """B1 回归：params+priority 同改时消息出现在新队列且 params 为新值"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=self._pending())
        svc.repo.update = AsyncMock(
            return_value=_task(id=12, priority="high", params=NEW_PARAMS)
        )
        fake_redis = _FakeQueueRedis()
        fake_redis.queues["spider:task_queue:normal"] = [_msg(12, "example", OLD_PARAMS)]

        with patch("backend.services.spider_service.redis_client", return_value=fake_redis):
            await svc.update_task(12, params=NEW_PARAMS, priority="high")

        assert fake_redis.items("spider:task_queue:normal") == []
        assert fake_redis.items("spider:task_queue:high") == [_msg(12, "example", NEW_PARAMS)]

    @pytest.mark.asyncio
    async def test_rpush_failure_compensates_back_to_source_queue(self):
        """M1 回归：LREM 成功后 rpush 失败 → 旧消息 lpush 补偿回原队列，不丢失"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=self._pending())
        svc.repo.update = AsyncMock(return_value=_task(id=12, priority="high"))
        fake_redis = _RpushBrokenRedis()
        fake_redis.queues["spider:task_queue:normal"] = [_msg(12, "example", OLD_PARAMS)]

        with patch("backend.services.spider_service.redis_client", return_value=fake_redis):
            await svc.update_task(12, priority="high")

        # 旧消息回到原队列、新队列为空；补偿成功不置 failed（repo.update 仅编辑一次）
        assert fake_redis.items("spider:task_queue:normal") == [_msg(12, "example", OLD_PARAMS)]
        assert fake_redis.items("spider:task_queue:high") == []
        svc.repo.update.assert_awaited_once_with(12, priority="high")

    @pytest.mark.asyncio
    async def test_compensation_failure_marks_task_failed(self):
        """M1 回归：补偿回队列也失败 → 任务置 failed 并抛 BusinessException（对齐 enqueue 兑底）"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=self._pending())
        svc.repo.update = AsyncMock(return_value=_task(id=12, priority="high"))
        fake_redis = _CompensationBrokenRedis()
        fake_redis.queues["spider:task_queue:normal"] = [_msg(12, "example", OLD_PARAMS)]

        with patch("backend.services.spider_service.redis_client", return_value=fake_redis):
            with pytest.raises(BusinessException):
                await svc.update_task(12, priority="high")

        last_call = svc.repo.update.await_args_list[-1]
        assert last_call.args[0] == 12
        assert last_call.kwargs["status"] == "failed"
        assert "队列搬迁投递失败" in last_call.kwargs["error_message"]

    def test_task_update_request_defaults(self):
        payload = TaskUpdateRequest()
        assert payload.params is None and payload.priority is None
        payload = TaskUpdateRequest(priority="low")
        assert payload.priority == "low"

    @pytest.mark.asyncio
    async def test_missing_task_raises(self):
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundException):
            await svc.update_task(999, priority="high")


# ---------------- 控制端点契约（M2 回归） ----------------
class TestControlEndpointContract:
    def test_control_without_body_returns_422(self, client):
        """M2 回归：control 端点缺 body → FastAPI 校验失败返回 422（修复前为 500）"""
        resp = client.post("/api/v1/spiders/tasks/1/control")
        assert resp.status_code == 422


# ---------------- 跨任务结果查询 / 结果删除 ----------------
class TestSearchResults:
    @pytest.mark.asyncio
    async def test_search_results_passes_filters_and_builds_response(self):
        svc = _service()
        row = {
            "id": 7, "task_id": 9, "spider_name": "example", "url": "https://a.b",
            "title": "标题", "content": None, "source": None, "item_type": None,
            "quality_score": None, "content_hash": None,
            "created_at": "2026-08-29T10:00:00",
        }
        svc.result_repo.query_by_spider = AsyncMock(return_value=([row], 1))

        resp = await svc.search_results(
            spider_name="example", page=2, page_size=10,
            start_time=datetime(2026, 8, 1), end_time=datetime(2026, 8, 29),
            keyword="标题",
        )

        kwargs = svc.result_repo.query_by_spider.await_args.kwargs
        assert kwargs["spider_name"] == "example"
        assert kwargs["page"] == 2 and kwargs["page_size"] == 10
        assert kwargs["keyword"] == "标题"
        assert resp.total == 1
        assert resp.items[0].id == 7
        assert resp.items[0].created_at == datetime(2026, 8, 29, 10, 0, 0)

    @pytest.mark.asyncio
    async def test_search_results_without_spider_queries_all(self):
        svc = _service()
        svc.result_repo.query_by_spider = AsyncMock(return_value=([], 0))

        resp = await svc.search_results()  # 跨任务全量

        kwargs = svc.result_repo.query_by_spider.await_args.kwargs
        assert kwargs["spider_name"] is None
        assert resp.total == 0 and resp.items == []

    @pytest.mark.asyncio
    async def test_delete_result_missing_raises(self):
        svc = _service()
        svc.result_repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundException):
            await svc.delete_result(999)

    @pytest.mark.asyncio
    async def test_delete_result_success(self):
        svc = _service()
        svc.result_repo.get_by_id = AsyncMock(return_value=MagicMock(id=7))
        svc.result_repo.delete = AsyncMock(return_value=True)

        result = await svc.delete_result(7)

        assert result == {"id": 7, "deleted": True}
        svc.result_repo.delete.assert_awaited_once_with(7)


# ---------------- 审计日志查询 ----------------
class TestAuditLogQuery:
    def _log(self) -> MagicMock:
        return MagicMock(
            id=7, actor_id=1, actor_name="test-admin", action="task.run",
            target="task#9", detail='{"spider": "example"}', created_at=datetime(2026, 8, 29, 9, 0, 0),
        )

    @pytest.mark.asyncio
    async def test_list_logs_passes_filters(self):
        svc = AuditService(MagicMock())
        svc.repo = MagicMock()
        svc.repo.list_logs = AsyncMock(return_value=[self._log()])
        svc.repo.count_logs = AsyncMock(return_value=1)

        resp = await svc.list_logs(
            skip=10, limit=5, user="test-admin",
            start_time=datetime(2026, 8, 1), end_time=datetime(2026, 8, 29),
        )

        svc.repo.list_logs.assert_awaited_once_with(
            skip=10, limit=5, action=None, user="test-admin",
            start_time=datetime(2026, 8, 1), end_time=datetime(2026, 8, 29),
        )
        svc.repo.count_logs.assert_awaited_once_with(
            action=None, user="test-admin",
            start_time=datetime(2026, 8, 1), end_time=datetime(2026, 8, 29),
        )
        assert resp.total == 1
        assert resp.items[0].action == "task.run"
        assert resp.items[0].actor_name == "test-admin"

    @pytest.mark.asyncio
    async def test_list_logs_default_filters_none(self):
        svc = AuditService(MagicMock())
        svc.repo = MagicMock()
        svc.repo.list_logs = AsyncMock(return_value=[])
        svc.repo.count_logs = AsyncMock(return_value=0)

        resp = await svc.list_logs()

        assert resp.total == 0 and resp.items == []
        kwargs = svc.repo.list_logs.await_args.kwargs
        assert kwargs["user"] is None and kwargs["action"] is None


# ---------------- 调度创建（DB 优先校验） ----------------
class TestScheduleSpiderValidation:
    @pytest.mark.asyncio
    async def test_create_rejected_when_disabled_in_db(self):
        from platform_core.schemas.spider import ScheduleRequest

        svc = ScheduleService(session=MagicMock())
        repo = MagicMock()
        repo.get_by_name = AsyncMock(return_value=_definition(enabled=False))

        with patch(
            "backend.services.schedule_service.SpiderDefinitionRepository", return_value=repo
        ):
            with pytest.raises(BusinessException):
                await svc.create_schedule(
                    ScheduleRequest(spider_name="example", cron_expr="*/5 * * * *")
                )

    @pytest.mark.asyncio
    async def test_create_allowed_when_db_record_enabled(self):
        from platform_core.schemas.spider import ScheduleRequest

        svc = ScheduleService(session=MagicMock())
        svc.session.commit = AsyncMock()
        svc.session.refresh = AsyncMock()
        repo = MagicMock()
        repo.get_by_name = AsyncMock(return_value=_definition(enabled=True))
        svc.repo = MagicMock()
        svc.repo.find_by_spider = AsyncMock(return_value=None)
        created = MagicMock(
            id=3, spider_name="example", cron_expr="*/5 * * * *", params=None,
            enabled=True, last_run_at=None, next_run_at=datetime.now(),
            created_at=None, updated_at=None,
        )
        svc.repo.create = AsyncMock(return_value=created)

        with patch(
            "backend.services.schedule_service.SpiderDefinitionRepository", return_value=repo
        ):
            resp = await svc.create_schedule(
                ScheduleRequest(spider_name="example", cron_expr="*/5 * * * *")
            )

        assert resp.id == 3
