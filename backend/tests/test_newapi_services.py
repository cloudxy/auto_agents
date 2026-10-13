"""new-api 渠道调度器 + 真伪探针服务单测

约定：不连真实 MySQL/Redis/new-api，外部依赖全部打桩：
- new-api 管理 API / 采集 API：httpx.MockTransport（验证 HTTP 契约）或 Fake 客户端
- Redis：内存 Fake（SET NX / GET / DEL / HGETALL / HSET 语义）
- 主库落库：patch _main_async_session 为 Fake 上下文会话（验证 ORM 字段映射）

覆盖（T-19 后调度窗口改为 spend HTTP → budget，用量 SQL / 状态 PUT 禁用用例已随实现删除，
现行窗口与冷却语义见 test_llm_cooldown.py）：
- 探针判定 original/spoofed/offline 三分支 + 逐字缓存指纹 + 参考相似度
- 事件/探针结果落库字段映射；开关关闭时不启动
- new-api 客户端 HTTP 契约（Bearer 头 / New-Api-User / 分页 / chat 解析）
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.repositories.newapi_repository import (
    ChannelEventRepository,
    ChannelProbeResultRepository,
)
from backend.services import channel_probe_service as probe_mod
from backend.services import channel_scheduler_service as sched_mod
from backend.services.channel_probe_service import (
    DEFAULT_PROBE_QUESTIONS,
    ChannelProbeService,
    _load_questions,
    _score_probe_batch,
)
from backend.services.channel_scheduler_service import ChannelSchedulerService
from backend.services.newapi_api import (
    CHANNEL_STATUS_AUTO_DISABLED,
    CHANNEL_STATUS_ENABLED,
    NewapiApiClient,
)
from platform_core.models.channel_event import ChannelEvent
from platform_core.models.channel_probe_result import ChannelProbeResult
from stubs import FakeRedis as _FakeRedis  # 共享桩（唯一定义处见 stubs.py）
from stubs import fake_settings as _fake_settings


# ---------------- 测试桩 ----------------
class _FakeApiClient:
    """new-api 客户端桩（记录启停调用）"""

    def __init__(self, channels=None, details=None):
        self.channels = channels or []
        self.details = details or {}
        self.status_calls: list[tuple[int, int]] = []

    async def list_channels(self):
        return [dict(c) for c in self.channels]

    async def get_channel(self, channel_id):
        return self.details.get(channel_id)

    async def set_channel_status(self, channel_id, status):
        self.status_calls.append((channel_id, status))
        return True


class _CtxSessionStub:
    """主库会话桩（异步上下文 + add/commit，验证落库字段映射）"""

    def __init__(self):
        self.add = MagicMock()
        self.flush = AsyncMock()
        self.refresh = AsyncMock()
        self.commit = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _scheduler(fake_redis, fake_api, mode: str | None = "unix") -> ChannelSchedulerService:
    """不触发生命周期的调度器实例（依赖注入桩）"""
    svc = ChannelSchedulerService.__new__(ChannelSchedulerService)
    svc._running = False
    svc._loop_task = None
    svc._redis = fake_redis
    svc._engine = None
    svc._sessionmaker = None
    svc._api = fake_api
    svc._created_at_mode = mode
    return svc


def _probe(fake_redis, fake_api) -> ChannelProbeService:
    """不触发生命周期的探针实例"""
    svc = ChannelProbeService.__new__(ChannelProbeService)
    svc._running = False
    svc._loop_task = None
    svc._redis = fake_redis
    svc._api = fake_api
    return svc


# ---------------- 调度器/探针：开关与生命周期 ----------------
class TestSwitches:
    @pytest.mark.asyncio
    async def test_scheduler_disabled_when_switch_off(self):
        svc = _scheduler(_FakeRedis(), _FakeApiClient(), mode=None)
        with patch.object(sched_mod, "settings", _fake_settings(
                **{"RELAY.SCHEDULER_ENABLED": False})):
            await svc.start()
        assert not svc._running and svc._loop_task is None

    @pytest.mark.asyncio
    async def test_scheduler_start_and_stop(self):
        with patch.object(sched_mod, "settings", _fake_settings(**{
                "RELAY.SCHEDULER_ENABLED": True,
                "RELAY.INTERVAL_SECONDS": 3600})), \
             patch("platform_core.redis_async.get_async_redis", return_value=_FakeRedis()):
            svc = ChannelSchedulerService()
            await svc.start()
            assert svc._running is True
            assert svc._loop_task is not None
            await svc.stop()
        assert svc._running is False and svc._loop_task is None

    @pytest.mark.asyncio
    async def test_scheduler_starts_without_db_dsn(self):
        with patch.object(sched_mod, "settings", _fake_settings(
                **{"RELAY.SCHEDULER_ENABLED": True,
                   "RELAY.INTERVAL_SECONDS": 3600})), \
             patch("platform_core.redis_async.get_async_redis", return_value=_FakeRedis()):
            svc = ChannelSchedulerService()
            await svc.start()
            assert svc._running is True
            await svc.stop()

    @pytest.mark.asyncio
    async def test_probe_disabled_when_switch_off(self):
        svc = _probe(_FakeRedis(), _FakeApiClient())
        with patch.object(probe_mod, "settings", _fake_settings(
                **{"RELAY.PROBE_ENABLED": False})):
            await svc.start()
        assert not svc._running and svc._loop_task is None

    @pytest.mark.asyncio
    async def test_probe_start_and_stop(self):
        with patch.object(probe_mod, "settings", _fake_settings(**{
                "RELAY.PROBE_ENABLED": True,
                "RELAY.PROBE_INTERVAL_SECONDS": 3600})), \
             patch("platform_core.redis_async.get_async_redis", return_value=_FakeRedis()):
            svc = ChannelProbeService()
            await svc.start()
            assert svc._running is True
            await svc.stop()
        assert svc._running is False


# ---------------- 探针判定三分支 ----------------
def _resp(content="ok", ok=True, latency=800, model="gpt-4o", usage=None,
          reasoning=0, error=None) -> dict:
    return {"ok": ok, "content": content, "latency_ms": latency, "model": model,
            "usage": usage if usage is not None else {"total_tokens": 20},
            "reasoning_tokens": reasoning, "error": error}


def _results(**overrides) -> dict:
    base = {
        "identity_zh": _resp("我是 gpt-4o 模型"),
        "identity_en": _resp("I am gpt-4o."),
        "knowledge_cutoff_zh": _resp("2025 年 3 月发生了某发布会"),
        "knowledge_cutoff_en": _resp("In March 2025 an event happened"),
        "math_reasoning": _resp("10145"),
        "instruction_following": _resp("RED\nBLUE"),
        "knowledge_cutoff_zh:repeat": _resp("2025 年 6 月另有事件"),
        "instruction_following:repeat1": _resp("RED\nBLUE"),
        "instruction_following:repeat2": _resp("RED\nBLUE"),
    }
    base.update(overrides)
    return base


class TestProbeVerdict:
    def test_original_when_all_signals_clean(self):
        verdict, scores = _score_probe_batch("gpt-4o", _results(), DEFAULT_PROBE_QUESTIONS)
        assert verdict == "original"
        assert scores["identity"] == 1.0
        assert scores["zh_en_consistency"] == 1.0
        assert scores["math_reasoning"] == 1.0
        assert scores["instruction_following"] == 1.0
        assert scores["verbatim_repeat"] == 1.0
        assert scores["format_stability"] == 1.0
        assert scores["reasoning_tokens_anomaly"] == 1.0

    def test_spoofed_by_identity_contradiction(self):
        r = _results(identity_zh=_resp("我是 GLM-4"), identity_en=_resp("I am GLM-4."))
        verdict, scores = _score_probe_batch("gpt-4o", r, DEFAULT_PROBE_QUESTIONS)
        assert verdict == "spoofed"
        assert scores["identity"] == 0.0

    def test_unknown_family_not_spoofed_by_identity_contradiction(self):
        """评审 m-6：请求模型家族无法识别时，身份回答提及已知家族词
        不判 spoofed（scores 保留记录，供人工复核）"""
        r = _results(identity_zh=_resp("我是 GLM-4"), identity_en=_resp("I am GLM-4."))
        verdict, scores = _score_probe_batch("some-unknown-model-x", r, DEFAULT_PROBE_QUESTIONS)
        assert verdict == "original"  # 不再误判 spoofed
        assert scores["identity"] == 0.0  # 低分仅记录

    def test_known_family_still_spoofed_by_contradiction(self):
        """评审 m-6 回归：已知家族的身份矛盾仍正常判 spoofed"""
        r = _results(identity_zh=_resp("我是 GLM-4"), identity_en=_resp("I am GLM-4."))
        verdict, scores = _score_probe_batch("gpt-4o", r, DEFAULT_PROBE_QUESTIONS)
        assert verdict == "spoofed"
        assert scores["identity"] == 0.0

    def test_spoofed_by_verbatim_cache_fingerprint(self):
        """同题逐字重复（缓存指纹）→ spoofed"""
        r = _results(**{"knowledge_cutoff_zh:repeat": _resp("2025 年 3 月发生了某发布会")})
        verdict, scores = _score_probe_batch("gpt-4o", r, DEFAULT_PROBE_QUESTIONS)
        assert verdict == "spoofed"
        assert scores["verbatim_repeat"] == 0.0

    def test_spoofed_by_low_reference_similarity(self):
        ref = _results(identity_zh=_resp("甲乙丙丁戊己庚辛"),
                       identity_en=_resp("Totally different reference answer"),
                       knowledge_cutoff_zh=_resp("壬癸子丑寅卯辰巳"),
                       knowledge_cutoff_en=_resp("No similarity at all here"),
                       math_reasoning=_resp("99999"),
                       instruction_following=_resp("XXX\nYYY"))
        verdict, scores = _score_probe_batch(
            "gpt-4o", _results(), DEFAULT_PROBE_QUESTIONS, ref_results=ref)
        assert verdict == "spoofed"
        assert scores["ref_similarity"] < 0.15

    def test_offline_when_majority_calls_fail(self):
        r = {k: _resp(ok=False, error="timeout") for k in _results()}
        verdict, scores = _score_probe_batch("gpt-4o", r, DEFAULT_PROBE_QUESTIONS)
        assert verdict == "offline"
        assert scores == {"total_calls": 9, "ok_calls": 0}

    def test_reasoning_tokens_anomaly_on_non_o_series(self):
        r = _results(identity_zh=_resp("我是 gpt-4o 模型", reasoning=128))
        _, scores = _score_probe_batch("gpt-4o", r, DEFAULT_PROBE_QUESTIONS)
        assert scores["reasoning_tokens_anomaly"] == 0.0
        # o 系模型返回 reasoning_tokens 属正常
        r2 = _results(identity_zh=_resp("我是 o3", reasoning=128))
        _, scores2 = _score_probe_batch("o3", r2, DEFAULT_PROBE_QUESTIONS)
        assert scores2["reasoning_tokens_anomaly"] == 1.0

    def test_low_latency_ratio_against_reference(self):
        ref = _results()
        r = _results(identity_zh=_resp("我是 gpt-4o 模型", latency=10))
        _, scores = _score_probe_batch("gpt-4o", r, DEFAULT_PROBE_QUESTIONS, ref_results=ref)
        assert scores["latency_ratio"] < 0.2
        assert scores["latency"] == 0.5

    def test_price_anomaly_on_missing_usage(self):
        r = _results(identity_zh=_resp("我是 gpt-4o 模型", usage={}))
        _, scores = _score_probe_batch("gpt-4o", r, DEFAULT_PROBE_QUESTIONS)
        assert scores["price_anomaly"] == 0.5


# ---------------- 探针：批次巡检与落库 ----------------
_chat_calls: dict[str, int] = {}


def _fake_chat(model, prompt, timeout=None) -> dict:
    """确定性采集桩；同题重复调用返回略异内容（模拟真实非缓存行为）"""
    answers = [
        ("你是什么模型", "我是 gpt-4o 模型"),
        ("What model are you", "I am gpt-4o."),
        ("2025 年发生的具体事件", "2025 年 6 月举办了发布会"),
        ("Name one specific event", "In June 2025 a launch event happened"),
        ("137 × 89", "10145"),
        ("严格按照以下格式", "RED\nBLUE"),
    ]
    for key, ans in answers:
        if key in prompt:
            _chat_calls[key] = _chat_calls.get(key, 0) + 1
            n = _chat_calls[key]
            return _resp(ans if n == 1 else f"{ans}（补充说明{n}）", model=model)
    return _resp("好的。", model=model)


async def _fake_chat_completions(body, **kwargs) -> dict:
    model = str((body or {}).get("model") or "")
    prompt = str((((body or {}).get("messages") or [{}])[0].get("content") or ""))
    row = _fake_chat(model, prompt)
    return {
        "choices": [{"message": {"content": row["content"]}}],
        "usage": row.get("usage") or {"total_tokens": 20},
        "model": model,
    }


class TestProbeFlow:
    @pytest.mark.asyncio
    async def test_tick_once_probes_enabled_targets_excluding_reference(self):
        _chat_calls.clear()
        redis = _FakeRedis()
        redis.hashes["relay:channel:cfg:3"] = {"manual_disabled": "1"}
        svc = _probe(redis, None)
        recorded: list = []
        svc._record_probe_result = AsyncMock(side_effect=lambda **kw: recorded.append(kw))
        payload = {"data": [
            {"model_name": "gpt-4o", "model_info": {"id": "1"}},
            {"model_name": "gpt-4o-mini", "model_info": {"id": "2"}},
            {"model_name": "qwen-max", "model_info": {"id": "3"}},
        ]}
        with patch.object(probe_mod, "settings", _fake_settings(
                **{"RELAY.PROBE_REFERENCE_CHANNEL": "1"})), \
             patch.object(probe_mod.gw_admin, "list_models", AsyncMock(return_value=payload)), \
             patch.object(probe_mod, "chat_completions", _fake_chat_completions):
            await svc._tick_once()
        assert [r["channel_id"] for r in recorded] == [2]
        assert recorded[0]["model"] == "gpt-4o-mini"
        assert recorded[0]["verdict"] == "original"
        assert len(recorded[0]["batch_id"]) == 32  # uuid hex
        assert probe_mod.NEWAPI_PROBE_LOCK_KEY not in redis.strings
        assert sum(_chat_calls.values()) >= 9

    @pytest.mark.asyncio
    async def test_probe_channel_records_result(self):
        _chat_calls.clear()
        svc = _probe(_FakeRedis(), MagicMock())
        recorded: list = []
        svc._record_probe_result = AsyncMock(side_effect=lambda **kw: recorded.append(kw))
        with patch.object(probe_mod, "chat_completions", _fake_chat_completions):
            await svc._probe_channel(
                {"gateway_ref": "9", "model_name": "gpt-4o", "name": "prov"},
                None, DEFAULT_PROBE_QUESTIONS, "batch-xyz")
        assert recorded[0]["channel_id"] == 9
        assert recorded[0]["model"] == "gpt-4o"
        assert recorded[0]["verdict"] == "original"
        assert recorded[0]["batch_id"] == "batch-xyz"
        assert recorded[0]["latency_ms"] is not None and recorded[0]["latency_ms"] >= 0
        assert recorded[0]["scores"]["identity"] == 1.0

    @pytest.mark.asyncio
    async def test_probe_channel_without_identity_question(self):
        """评审 m-5：问题集缺失 identity 题时不 KeyError，latency 为 None"""
        questions = [q for q in DEFAULT_PROBE_QUESTIONS if q["category"] != "identity"]
        svc = _probe(_FakeRedis(), MagicMock())
        recorded: list = []
        svc._record_probe_result = AsyncMock(side_effect=lambda **kw: recorded.append(kw))
        with patch.object(probe_mod, "chat_completions", _fake_chat_completions):
            await svc._probe_channel(
                {"gateway_ref": "9", "model_name": "gpt-4o", "name": "prov"},
                None, questions, "batch-no-identity")
        assert len(recorded) == 1
        assert recorded[0]["latency_ms"] is None

    @pytest.mark.asyncio
    async def test_record_probe_result_writes_via_main_session(self, monkeypatch):
        fake_session = _CtxSessionStub()
        monkeypatch.setattr(probe_mod, "_main_async_session", lambda: fake_session)
        svc = _probe(_FakeRedis(), MagicMock())
        await svc._record_probe_result(
            channel_id=9, model="gpt-4o", verdict="spoofed",
            scores={"identity": 0.0}, latency_ms=800, batch_id="b1")
        fake_session.commit.assert_awaited_once()
        added = fake_session.add.call_args.args[0]
        assert isinstance(added, ChannelProbeResult)
        assert added.channel_id == 9 and added.verdict == "spoofed"
        assert added.model == "gpt-4o" and added.batch_id == "b1"

    def test_load_questions_file_override_and_fallback(self, tmp_path):
        qfile = tmp_path / "q.json"
        qfile.write_text(json.dumps({"questions": [
            {"id": "x1", "category": "identity", "text": "你是谁？"},
        ]}), encoding="utf-8")
        qs = _load_questions(str(qfile))
        assert qs[0]["id"] == "x1"
        bad = tmp_path / "bad.json"
        bad.write_text("{not-json", encoding="utf-8")
        assert _load_questions(str(bad)) == DEFAULT_PROBE_QUESTIONS
        assert _load_questions("") == DEFAULT_PROBE_QUESTIONS


# ---------------- 落库字段映射（Repository + 主库会话） ----------------
def _session_stub() -> MagicMock:
    s = MagicMock()
    s.add = MagicMock()
    s.flush = AsyncMock()
    s.refresh = AsyncMock()
    s.execute = AsyncMock()
    return s


class TestRepositories:
    @pytest.mark.asyncio
    async def test_event_repo_create_fields(self):
        session = _session_stub()
        event = await ChannelEventRepository(session).create_event(
            channel_id=5, action="disabled", usage=1500, limit_quota=1000,
            window_hours=24, reason="超限", source="scheduler")
        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        assert isinstance(event, ChannelEvent)
        assert event.channel_id == 5 and event.action == "disabled"
        assert event.usage == 1500 and event.limit_quota == 1000
        assert event.window_hours == 24 and event.source == "scheduler"

    @pytest.mark.asyncio
    async def test_event_repo_list_and_count_filters(self):
        session = _session_stub()
        stub = MagicMock()
        stub.scalars.return_value.all.return_value = []
        stub.scalar_one.return_value = 0
        session.execute.return_value = stub
        repo = ChannelEventRepository(session)
        assert await repo.list_events(channel_id=5, action="disabled") == []
        stmt = session.execute.call_args.args[0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "channel_events" in compiled and "channel_id" in compiled
        assert await repo.count_events(source="scheduler") == 0

    @pytest.mark.asyncio
    async def test_probe_result_repo_create_and_latest(self):
        session = _session_stub()
        repo = ChannelProbeResultRepository(session)
        result = await repo.create_result(
            channel_id=9, model="gpt-4o", verdict="spoofed",
            scores={"identity": 0.0}, latency_ms=800, batch_id="abc")
        session.add.assert_called_once()
        assert isinstance(result, ChannelProbeResult)
        assert result.verdict == "spoofed" and result.batch_id == "abc"
        assert result.scores == {"identity": 0.0} and result.latency_ms == 800

        sentinel = SimpleNamespace(verdict="original")
        stub = MagicMock()
        stub.scalars.return_value.first.return_value = sentinel
        session.execute.return_value = stub
        assert await repo.latest_verdict(9) is sentinel
        compiled = str(session.execute.call_args.args[0].compile(
            compile_kwargs={"literal_binds": True}))
        assert "channel_probe_results" in compiled

    @pytest.mark.asyncio
    async def test_record_event_writes_via_main_session(self, monkeypatch):
        fake_session = _CtxSessionStub()
        monkeypatch.setattr(sched_mod, "_main_async_session", lambda: fake_session)
        svc = _scheduler(_FakeRedis(), _FakeApiClient())
        await svc._record_event(channel_id=5, action="enabled",
                                source="scheduler", reason="冷却到期自动恢复上线")
        fake_session.commit.assert_awaited_once()
        added = fake_session.add.call_args.args[0]
        assert isinstance(added, ChannelEvent)
        assert added.action == "enabled" and added.reason == "冷却到期自动恢复上线"


# ---------------- new-api 客户端 HTTP 契约 ----------------
class TestNewapiApiClient:
    @pytest.mark.asyncio
    async def test_set_channel_status_request_contract(self):
        """PUT /api/channel/ body={id,status} + Bearer 头（蓝本 :158-184 写法）"""
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("Authorization")
            captured["user"] = request.headers.get("New-Api-User")
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"success": True})

        client = NewapiApiClient(
            base_url="http://newapi.test", token="tok-abc",
            transport=httpx.MockTransport(handler))
        assert await client.set_channel_status(5, CHANNEL_STATUS_AUTO_DISABLED) is True
        assert captured["method"] == "PUT"
        assert captured["url"] == "http://newapi.test/api/channel/"
        assert captured["auth"] == "Bearer tok-abc"
        assert captured["body"] == {"id": 5, "status": CHANNEL_STATUS_AUTO_DISABLED}

    @pytest.mark.asyncio
    async def test_set_channel_status_rejected(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"success": False, "message": "no permission"})

        client = NewapiApiClient(base_url="http://newapi.test", token="t",
                                 transport=httpx.MockTransport(handler))
        assert await client.set_channel_status(5, CHANNEL_STATUS_ENABLED) is False

    @pytest.mark.asyncio
    async def test_list_channels_paginates(self):
        def handler(request: httpx.Request) -> httpx.Response:
            page = int(request.url.params.get("p", "1"))
            items = [{"id": i} for i in range(100)] if page == 1 else [{"id": 100}]
            return httpx.Response(200, json={"success": True, "data": {"items": items}})

        client = NewapiApiClient(base_url="http://newapi.test", token="t",
                                 transport=httpx.MockTransport(handler))
        channels = await client.list_channels()
        assert len(channels) == 101

    @pytest.mark.asyncio
    async def test_list_channels_network_error_returns_empty(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        client = NewapiApiClient(base_url="http://newapi.test", token="t",
                                 transport=httpx.MockTransport(handler))
        assert await client.list_channels() == []

    @pytest.mark.asyncio
    async def test_get_channel_contract(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/channel/7"
            return httpx.Response(200, json={"success": True, "data": {"id": 7, "status": 2}})

        client = NewapiApiClient(base_url="http://newapi.test", token="t",
                                 transport=httpx.MockTransport(handler))
        assert await client.get_channel(7) == {"id": 7, "status": 2}

    @pytest.mark.asyncio
    async def test_chat_completion_parses_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body["model"] == "gpt-4o" and body["stream"] is False
            assert request.headers.get("Authorization") == "Bearer sk-probe"
            return httpx.Response(200, json={
                "model": "gpt-4o",
                "choices": [{"message": {"content": "我是 gpt-4o"}}],
                "usage": {"total_tokens": 42,
                          "completion_tokens_details": {"reasoning_tokens": 7}},
            })

        client = NewapiApiClient(
            base_url="http://newapi.test", token="tok",
            probe_api_key="sk-probe",
            transport=httpx.MockTransport(handler),
        )
        r = await client.chat_completion("gpt-4o", "你是什么模型")
        assert r["ok"] is True
        assert r["content"] == "我是 gpt-4o"
        assert r["reasoning_tokens"] == 7
        assert r["usage"]["total_tokens"] == 42
        assert r["error"] is None

    @pytest.mark.asyncio
    async def test_chat_completion_http_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"})

        client = NewapiApiClient(base_url="http://newapi.test", token="t",
                                 transport=httpx.MockTransport(handler))
        r = await client.chat_completion("gpt-4o", "你好")
        assert r["ok"] is False
        assert "500" in r["error"]
