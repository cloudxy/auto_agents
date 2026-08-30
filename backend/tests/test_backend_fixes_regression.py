"""后端高优缺陷修复回归单测 - 集中覆盖（可随本轮改动整体 revert）

覆盖：
- trust_env：ai_planner 三处 httpx client 构造必须 trust_env=False
  （本机系统代理劫持 502 陷阱，对齐 notify/newapi/llm_provider 既有约定）
- alert-rules 审计：create/update/delete 写端点必须落 record_audit（B2 审计缺口补齐）
- register 限流：Redis 计数器达阈值返回 429 且不触业务，未达阈值计数后放行
- v1/health/db：异步会话探活 + unhealthy 时错误不回显内部细节（只暴露类型名）
- consumer 关停：_ingest_loop 收到 CancelledError 先 flush 残余批次再传播取消
- consumer 重试：重新入队失败且回滚双失败时 DB 兜底置 failed（M-2）
- consumer flush：入口重算计数，失败重试不重复扣减去重结果（m-5）
- health/storage+redis：探活健康路径 + unhealthy 错误只暴露类型名（m-3）
"""
import asyncio
import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.api.deps import CurrentUser
from backend.app.api.v1.spiders import create_alert_rule, delete_alert_rule, update_alert_rule
from backend.services.ai_planner_service import (
    _fetch_html,
    get_shared_client,
    invalidate_client_cache,
)
from backend.tasks.consumer import SpiderTaskConsumer
from platform_core.queues import ITEM_QUEUE
from platform_core.schemas.spider import AlertRuleRequest, AlertRuleUpdateRequest

GOOD_LLM_JSON = json.dumps({
    "selectors": [{"name": "title", "type": "css", "expr": "h1::text"}],
    "pagination": None,
    "detail": None,
    "filters": [],
})


# ---------------- trust_env（本机代理劫持陷阱防护） ----------------
class TestTrustEnvDisabled:
    """三处 httpx client 构造（共享池 / 抓取 / 兜底）必须显式 trust_env=False"""

    @pytest.mark.asyncio
    async def test_shared_client_trust_env_disabled(self):
        """provider 共享连接池 client：trust_env=False"""
        client = await get_shared_client(
            "https://api.example.com", "sk-test-key", 30.0, provider_id=9901
        )
        try:
            assert client.trust_env is False
        finally:
            await invalidate_client_cache(9901)  # 清理模块级缓存，避免污染其他测试

    @pytest.mark.asyncio
    async def test_fetch_html_client_trust_env_disabled(self, monkeypatch):
        """目标页抓取 client（重定向链内惰性创建）：trust_env=False"""
        monkeypatch.setattr(
            "backend.services.ai_planner_service._resolve_host_ips",
            lambda host: ["93.184.216.34"],
        )
        resp = MagicMock(status_code=200, headers={}, text="<html>ok</html>")
        client = MagicMock()
        client.get = AsyncMock(return_value=resp)
        captured: dict = {}

        class _StubClient:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            async def __aenter__(self):
                return client

            async def __aexit__(self, *exc):
                return False

        with patch("backend.services.ai_planner_service.httpx.AsyncClient", _StubClient):
            html = await _fetch_html("https://example.com/page")

        assert html == "<html>ok</html>"
        assert captured.get("trust_env") is False

    @pytest.mark.asyncio
    async def test_llm_fallback_client_trust_env_disabled(self):
        """yml/env 兜底路径（provider_id=None 一次性 client）：trust_env=False

        直接 patch _resolve_llm_runtime_config 返回 provider_id=None 的配置，
        强制走兜底分支（不依赖 DB 环境：全量运行时本机 llm_providers 表
        可能有激活 provider，会走 provider 路径导致误判）。"""
        from backend.services.llm_provider_service import LlmRuntimeConfig

        async def _fake_resolve():
            return LlmRuntimeConfig(
                base_url="http://llm.test/v1", api_key="test-key", model="m",
                temperature=0.2, timeout=30.0, max_retries=1, enabled=True,
                source="config", provider_id=None,
            )

        ok_response = MagicMock()
        ok_response.json.return_value = {
            "choices": [{"message": {"content": GOOD_LLM_JSON}}],
            "usage": {"total_tokens": 10},
        }
        client = MagicMock()
        client.post = AsyncMock(return_value=ok_response)
        client_cls = MagicMock()
        client_cls.return_value = AsyncMock()
        client_cls.return_value.__aenter__.return_value = client
        client_cls.return_value.__aexit__.return_value = False

        svc = AiPlannerServiceStub()
        with patch("backend.services.ai_planner_service._resolve_llm_runtime_config", _fake_resolve), \
             patch("backend.services.ai_planner_service.httpx.AsyncClient", client_cls), \
             patch("backend.services.ai_planner_service._TOKEN_USAGE", {}):
            result = await svc._llm_chat([{"role": "user", "content": "hi"}])

        assert result == GOOD_LLM_JSON
        assert client_cls.call_args.kwargs.get("trust_env") is False


class AiPlannerServiceStub:
    """不触 DB 的 AiPlannerService（config 解析异常时自动回退 yml/env 兜底路径）"""

    def __init__(self):
        from backend.services.ai_planner_service import AiPlannerService

        svc = AiPlannerService.__new__(AiPlannerService)
        svc.session = MagicMock()
        svc.repo = MagicMock()
        self._llm_chat = svc._llm_chat


# ---------------- alert-rules 审计（B2 审计缺口补齐） ----------------
class TestAlertRuleAudit:
    """alert-rules 三个写端点必须写审计日志（action/target 与同文件既有模式对齐）"""

    @staticmethod
    def _user() -> CurrentUser:
        return CurrentUser(id=1, username="admin", role="admin")

    @pytest.mark.asyncio
    async def test_create_alert_rule_records_audit(self):
        session = MagicMock()
        body = AlertRuleRequest(name="r1", rule_type="task_timeout", threshold=10.0)
        result = {"id": 5, "name": "r1", "rule_type": "task_timeout", "threshold": 10.0}
        with patch("backend.app.api.v1.spiders.AlertService") as svc_cls, \
             patch("backend.app.api.v1.spiders.record_audit", new=AsyncMock()) as audit:
            svc_cls.return_value.create_rule = AsyncMock(return_value=result)
            resp = await create_alert_rule(body=body, session=session, user=self._user())

        assert resp.data.id == 5
        audit.assert_awaited_once()
        args = audit.await_args.args
        assert args[2] == "alert_rule.create"
        assert args[3] == "alert_rule#5"
        assert args[4] == {"name": "r1", "rule_type": "task_timeout", "spider": None}

    @pytest.mark.asyncio
    async def test_update_alert_rule_records_audit(self):
        session = MagicMock()
        body = AlertRuleUpdateRequest(enabled=False)
        result = {"id": 5, "name": "r1", "rule_type": "task_timeout",
                  "threshold": 10.0, "enabled": False}
        with patch("backend.app.api.v1.spiders.AlertService") as svc_cls, \
             patch("backend.app.api.v1.spiders.record_audit", new=AsyncMock()) as audit:
            svc_cls.return_value.update_rule = AsyncMock(return_value=result)
            resp = await update_alert_rule(rule_id=5, body=body, session=session,
                                           user=self._user())

        assert resp.data.enabled is False
        audit.assert_awaited_once()
        args = audit.await_args.args
        assert args[2] == "alert_rule.update"
        assert args[3] == "alert_rule#5"
        assert args[4] == {"enabled": False}

    @pytest.mark.asyncio
    async def test_delete_alert_rule_records_audit(self):
        session = MagicMock()
        result = {"rule_id": 5, "deleted": True}
        with patch("backend.app.api.v1.spiders.AlertService") as svc_cls, \
             patch("backend.app.api.v1.spiders.record_audit", new=AsyncMock()) as audit:
            svc_cls.return_value.delete_rule = AsyncMock(return_value=result)
            resp = await delete_alert_rule(rule_id=5, session=session, user=self._user())

        assert resp.data == {"rule_id": 5, "deleted": True}
        audit.assert_awaited_once()
        args = audit.await_args.args
        assert args[2] == "alert_rule.delete"
        assert args[3] == "alert_rule#5"


# ---------------- register 限流（429 + 计数） ----------------
class TestRegisterRateLimit:
    """register 端点复用 login 的 Redis 限流模式（同 key 结构 prefix:{scope}）"""

    _BODY = {"username": "newuser", "email": "newuser@example.com", "password": "secret-123"}

    def test_register_blocked_returns_429_without_touching_counter(self, client, monkeypatch):
        """达到阈值：429（RATE_LIMITED）且不再递增计数（check 先于 record）"""
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value="5")
        mock_redis.ttl = AsyncMock(return_value=600)
        monkeypatch.setattr(
            "backend.app.api.v1.auth.get_async_redis", lambda *a, **k: mock_redis
        )

        resp = client.post("/api/v1/auth/register", json=self._BODY)

        assert resp.status_code == 429
        body = resp.json()
        assert body["code"] == "RATE_LIMITED"
        mock_redis.incr.assert_not_called()

    def test_register_records_attempt_and_passes_through(self, client, monkeypatch):
        """未达阈值：按 IP 递增计数器（15 分钟窗口）后放行到注册业务

        m-4 评审修复后计数走 pipeline：INCR+EXPIRE 同批提交，
        消除无 TTL 永久计数（限流计数器不再可能永久存在）。
        """
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)
        pipe = MagicMock()
        pipe.incr = MagicMock()
        pipe.expire = MagicMock()
        pipe.execute = AsyncMock()
        mock_redis.pipeline = MagicMock(return_value=pipe)
        monkeypatch.setattr(
            "backend.app.api.v1.auth.get_async_redis", lambda *a, **k: mock_redis
        )

        class _FakeAuthService:
            def __init__(self, db):
                pass

            async def register_user(self, **kwargs):
                return {"id": 99}

        monkeypatch.setattr("backend.app.api.v1.auth.AuthService", _FakeAuthService)

        resp = client.post("/api/v1/auth/register", json=self._BODY)

        assert resp.status_code == 200
        assert resp.json()["data"]["user_id"] == 99
        pipe.incr.assert_called_once_with("register_fail:testclient")
        pipe.expire.assert_called_once_with("register_fail:testclient", 900)
        pipe.execute.assert_awaited_once()


# ---------------- v1/health/db（async 探活 + 错误掩码） ----------------
class TestV1HealthDb:
    """v1 /health/db 对齐 v2：异步会话 SELECT 1；unhealthy 不回显内部异常细节"""

    def test_v1_health_db_healthy_uses_async_session(self, app, client):
        from platform_core.db import get_async_db

        session = AsyncMock()
        session.execute = AsyncMock(return_value=MagicMock())

        async def _override():
            yield session

        app.dependency_overrides[get_async_db] = _override
        try:
            resp = client.get("/api/v1/health/db")
        finally:
            app.dependency_overrides.pop(get_async_db, None)

        assert resp.status_code == 200
        assert resp.json() == {"status": "healthy", "database": "mysql"}
        session.execute.assert_awaited_once()

    def test_v1_health_db_unhealthy_masks_internal_detail(self, app, client):
        """DB 故障：status=unhealthy，error 仅类型名（连接串/主机名等细节不外泄）"""
        from platform_core.db import get_async_db

        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=RuntimeError("Access denied for user 'root'@'10.0.0.8'")
        )

        async def _override():
            yield session

        app.dependency_overrides[get_async_db] = _override
        try:
            resp = client.get("/api/v1/health/db")
        finally:
            app.dependency_overrides.pop(get_async_db, None)

        body = resp.json()
        assert body["status"] == "unhealthy"
        assert body["error"] == "RuntimeError"
        assert "root" not in body["error"]
        assert "10.0.0.8" not in body["error"]


# ---------------- consumer 关停 flush（防丢数据） ----------------
class TestIngestLoopShutdownFlush:
    """_ingest_loop 收到 CancelledError：先 flush 残余批次再传播取消"""

    @staticmethod
    def _consumer_with_pending_batch() -> tuple[SpiderTaskConsumer, str]:
        consumer = SpiderTaskConsumer()
        consumer._running = True
        consumer._redis = AsyncMock()
        message = json.dumps({"task_id": 1, "spider_name": "s1", "item": {"title": "t"}})
        # 第一轮 lpop 批量返回一条消息（进入内存批次），第二轮抛 CancelledError（模拟 stop）
        consumer._redis.lpop = AsyncMock(
            side_effect=[[message], asyncio.CancelledError()]
        )
        return consumer, message

    @pytest.mark.asyncio
    async def test_cancelled_error_flushes_pending_batch(self):
        """关停时内存批次被 flush（批量落库前进程退出不丢数据）"""
        consumer, message = self._consumer_with_pending_batch()
        captured: list[tuple[list, dict]] = []

        async def _capture_flush(batch, counts):
            captured.append((list(batch), dict(counts)))  # 拷贝：循环后续会 clear 原列表

        consumer._flush_batch = AsyncMock(side_effect=_capture_flush)

        with patch("backend.tasks.consumer.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.time.return_value = 100.0
            task = asyncio.create_task(consumer._ingest_loop())
            with pytest.raises(asyncio.CancelledError):
                await task

        assert len(captured) == 1
        batch, counts = captured[0]
        assert batch == [json.loads(message)]
        assert counts == {1: 1}

    @pytest.mark.asyncio
    async def test_cancelled_error_flush_failure_still_raises(self):
        """flush 失败也必须 re-raise CancelledError（关停路径不吞取消信号）"""
        consumer, _ = self._consumer_with_pending_batch()
        consumer._flush_batch = AsyncMock(side_effect=RuntimeError("db down"))

        with patch("backend.tasks.consumer.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.time.return_value = 100.0
            task = asyncio.create_task(consumer._ingest_loop())
            with pytest.raises(asyncio.CancelledError):
                await task

        consumer._flush_batch.assert_awaited_once()


# ---------------- 重试 ZSET 回滚双失败 DB 兜底（M-2） ----------------
class TestRetryReenqueueRollbackFailure:
    """_scan_retry_zset：重新入队失败且回滚 ZSET 也失败 → 任务置 failed 兜底"""

    @staticmethod
    def _retry_raw() -> str:
        return json.dumps({
            "task_id": 9, "spider_name": "s1",
            "params": '{"urls": ["https://e.com"]}', "priority": "high",
        })

    @pytest.mark.asyncio
    async def test_rollback_double_failure_marks_task_failed(self):
        """rpush 与回滚 zadd 双失败：消息不再残留，DB 兜底置 failed 可追溯"""
        consumer = SpiderTaskConsumer()
        consumer._running = True
        consumer._redis = AsyncMock()
        consumer._redis.zrangebyscore = AsyncMock(return_value=[self._retry_raw()])
        consumer._redis.zrem = AsyncMock(return_value=1)
        consumer._redis.rpush = AsyncMock(side_effect=RuntimeError("redis rpush down"))
        consumer._redis.zadd = AsyncMock(side_effect=RuntimeError("redis zadd down"))
        consumer._fail_task = AsyncMock()

        await consumer._scan_retry_zset()

        # 回滚尝试过（zadd 被调用）但失败：消息不再重入 ZSET
        consumer._redis.zadd.assert_awaited_once()
        # DB 兜底：任务置 failed（对齐 _reenqueue 投递失败语义），错误可追溯到任务行
        consumer._fail_task.assert_awaited_once_with(9, "重试重新入队失败（消息丢失）")

    @pytest.mark.asyncio
    async def test_rollback_success_keeps_delayed_retry_semantics(self):
        """仅 rpush 失败（回滚成功，既有语义）：消息延迟 5s 重入 ZSET，不置 failed"""
        consumer = SpiderTaskConsumer()
        consumer._running = True
        consumer._redis = AsyncMock()
        consumer._redis.zrangebyscore = AsyncMock(return_value=[self._retry_raw()])
        consumer._redis.zrem = AsyncMock(return_value=1)
        consumer._redis.rpush = AsyncMock(side_effect=RuntimeError("redis rpush down"))
        consumer._fail_task = AsyncMock()

        await consumer._scan_retry_zset()

        consumer._redis.zadd.assert_awaited_once()
        consumer._fail_task.assert_not_awaited()


# ---------------- flush 计数重算（m-5：失败重试不重复扣减） ----------------
class TestFlushBatchCountsRecompute:
    """_flush_batch 入口按 messages 重算计数：去重扣减不跨重试轮次累计"""

    @staticmethod
    def _hash_of(item: dict) -> str:
        return hashlib.md5(
            f"{item.get('url') or ''}{item.get('title') or ''}{item.get('content') or ''}".encode()
        ).hexdigest()

    @pytest.mark.asyncio
    async def test_flush_retry_does_not_double_deduct_dedup_counts(self):
        """flush 失败重试后：唯一未去重结果的 result_count 不被重复扣减归零"""
        consumer = SpiderTaskConsumer()
        consumer._redis = AsyncMock()  # 多存储双写路径（store_to 未命中不触达）
        items = [
            {"task_id": 1, "spider_name": "s1", "item": {"url": "u1", "title": "a", "content": "x"}},
            {"task_id": 1, "spider_name": "s1", "item": {"url": "u2", "title": "b", "content": "y"}},
            {"task_id": 2, "spider_name": "s1", "item": {"url": "u3", "title": "c", "content": "z"}},
        ]
        counts = {1: 2, 2: 1}  # 调用方累计值（旧实现会被失败轮次的去重扣减污染）

        task1 = MagicMock(params='{"incremental": true}')
        task2 = MagicMock(params=None)
        dup_hash = self._hash_of(items[0]["item"])

        repo = MagicMock()
        repo.get_by_id = AsyncMock(side_effect=lambda tid: {1: task1, 2: task2}[tid])
        repo.batch_increment_result_counts = AsyncMock()
        repo.find_by_content_hash = AsyncMock(
            side_effect=lambda h: MagicMock() if h == dup_hash else None
        )

        session = AsyncMock()
        session.commit = AsyncMock(side_effect=[RuntimeError("db down"), None])
        session.add_all = MagicMock()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.tasks.consumer.AsyncSession", return_value=ctx), \
             patch("backend.tasks.consumer.SpiderTaskRepository", return_value=repo), \
             patch("backend.tasks.consumer.SpiderResultRepository", return_value=repo):
            # 第一轮 flush：去重扣减后 commit 失败（批次原样重试场景）
            with pytest.raises(RuntimeError):
                await consumer._flush_batch(items, counts)
            # 第二轮 flush（重试）：按 messages 重算计数，扣减不跨轮次累计
            await consumer._flush_batch(items, counts)

        second_call = repo.batch_increment_result_counts.await_args_list[1]
        # 修复前：调用方 counts 已被第一轮扣成 {1: 1}，重试再扣 → {1: 0}，未去重结果计数丢失
        assert second_call.args[0] == {1: 1, 2: 1}
        # 调用方计数保持只读：重试基准始终是 messages 重算值
        assert counts == {1: 2, 2: 1}


# ---------------- health 三端点统一（m-3：异步化 + 错误掩码） ----------------
class TestV1HealthStorageRedis:
    """v1 /health/storage + /health/redis：healthy 探活 + unhealthy 只暴露异常类型名"""

    def test_health_storage_healthy(self, client):
        storage = MagicMock()
        storage.create_temp = MagicMock(return_value=MagicMock())
        with patch("backend.app.api.v1.health.get_storage", return_value=storage):
            resp = client.get("/api/v1/health/storage")
        assert resp.status_code == 200
        assert resp.json() == {"status": "healthy", "storage": "filesystem"}

    def test_health_storage_unhealthy_masks_internal_detail(self, client):
        """存储故障：error 仅类型名（路径等细节不外泄，与 /health/db 对齐）"""
        storage = MagicMock()
        storage.create_temp = MagicMock(side_effect=PermissionError("/data/exports denied"))
        with patch("backend.app.api.v1.health.get_storage", return_value=storage):
            resp = client.get("/api/v1/health/storage")
        body = resp.json()
        assert body["status"] == "unhealthy"
        assert body["error"] == "PermissionError"
        assert "/data/exports" not in body["error"]

    def test_health_redis_healthy_uses_async_ping(self, client):
        """m-3：/health/redis 改异步门面 ping（不再同步 redis_client 直调）"""
        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock(return_value=True)
        with patch("backend.app.api.v1.health.get_async_redis", return_value=mock_redis):
            resp = client.get("/api/v1/health/redis")
        assert resp.status_code == 200
        assert resp.json() == {"status": "healthy", "database": "redis"}
        mock_redis.ping.assert_awaited_once()

    def test_health_redis_unhealthy_masks_internal_detail(self, client):
        """Redis 故障：error 仅类型名（连接串/主机等细节不外泄）"""
        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock(
            side_effect=ConnectionError("Error 111 connecting to 10.0.0.9:6379")
        )
        with patch("backend.app.api.v1.health.get_async_redis", return_value=mock_redis):
            resp = client.get("/api/v1/health/redis")
        body = resp.json()
        assert body["status"] == "unhealthy"
        assert body["error"] == "ConnectionError"
        assert "10.0.0.9" not in body["error"]


# ---------------- ingest 批量化：lpop 批量替代逐条 blpop ----------------
class TestIngestBatchLpop:
    """_ingest_loop 单次 lpop(count=N) 批量弹出，减少 Redis round-trip"""

    @staticmethod
    def _item(task_id: int) -> str:
        return json.dumps({"task_id": task_id, "spider_name": "s1", "item": {"title": "t"}})

    @pytest.mark.asyncio
    async def test_lpop_batch_count_and_aggregation(self):
        """单轮拉取 POP_COUNT(20) 条：lpop 带 count 参数，批量消息聚合进同一批次"""
        consumer = SpiderTaskConsumer()
        consumer._running = True
        consumer._redis = AsyncMock()
        messages = [self._item(1) for _ in range(consumer._POP_COUNT)]
        consumer._redis.lpop = AsyncMock(side_effect=[messages, asyncio.CancelledError()])
        captured: list[tuple[list, dict]] = []

        async def _capture_flush(batch, counts):
            captured.append((list(batch), dict(counts)))

        consumer._flush_batch = AsyncMock(side_effect=_capture_flush)

        # time 恒定：不满足 flush_interval，20 条 < BATCH_SIZE(50)，
        # 仅在 CancelledError 关停时 flush 残余批次
        with patch("backend.tasks.consumer.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.time.return_value = 100.0
            task = asyncio.create_task(consumer._ingest_loop())
            with pytest.raises(asyncio.CancelledError):
                await task

        # lpop 批量语义：键 + count 参数
        first_call = consumer._redis.lpop.await_args_list[0]
        assert first_call.args == (ITEM_QUEUE,)
        assert first_call.kwargs["count"] == consumer._POP_COUNT
        # 20 条消息聚合进同一批次，按 task_id 计数
        assert len(captured) == 1
        batch, counts = captured[0]
        assert len(batch) == consumer._POP_COUNT
        assert counts == {1: consumer._POP_COUNT}

    @pytest.mark.asyncio
    async def test_idle_lpop_sleeps_without_flush(self):
        """lpop 返回 None（无新消息）：不 flush、短暂休眠保持节奏"""
        consumer = SpiderTaskConsumer()
        consumer._running = True
        consumer._redis = AsyncMock()
        consumer._redis.lpop = AsyncMock(side_effect=[None, asyncio.CancelledError()])
        consumer._flush_batch = AsyncMock()
        fake_sleep = AsyncMock()

        with (
            patch("backend.tasks.consumer.asyncio.get_event_loop") as mock_loop,
            patch("backend.tasks.consumer.asyncio.sleep", fake_sleep),
        ):
            mock_loop.return_value.time.return_value = 100.0
            task = asyncio.create_task(consumer._ingest_loop())
            with pytest.raises(asyncio.CancelledError):
                await task

        fake_sleep.assert_awaited_once_with(consumer._IDLE_SLEEP)
        consumer._flush_batch.assert_not_awaited()  # 空批次不触发 flush
