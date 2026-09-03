"""LLM 供应商管理单测（加密 / 单激活互斥 / 掩码 / 兜底顺序 / 权限 / 连通性）

约定：不连真实 MySQL/Redis，Repository 用 AsyncMock/MagicMock 桩；
连通性测试 mock httpx.AsyncClient；
兜底路径的 settings 读取桩 patch backend.services.ai_planner_service.settings
（resolve_config_from_settings 实现所在命名空间，与 test_ai_planner.py 约定一致）。
覆盖：
- Fernet 加密 roundtrip / 未配主密钥拒绝保存（不降级明文）/ 解密失败按缺失处理
- 掩码不泄露明文（schema 级 + 响应级）
- CRUD：重名拒绝 / api_key 留空不修改 / 非空重新加密 / 激活行可删除
- activate_exclusive 单语句 CASE 互斥
- resolve 兜底顺序：有激活行 / 无激活行 / 禁用行 / 激活行密钥缺失 / 删除激活行走兜底
- _llm_chat provider 路径共享 client + 按 provider 维度 token 计数
- invalidate_client_cache 定向 / 全清
- test_connectivity：成功 / HTTP 错误 / 网络异常 / 不存在的供应商
- API：GET 直出数组且 api_key_masked 掩码 / 写操作 operator 403
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from backend.app.api.deps import CurrentUser, require_admin
from backend.repositories.llm_provider_repository import LlmProviderRepository
from backend.services.ai_planner_service import (
    _HTTP_CLIENTS,
    _HTTP_CLIENT_OWNER,
    AiPlannerService,
    resolve_config_from_settings,
)
from backend.services.llm_provider_service import LlmProviderService, LlmRuntimeConfig
from platform_core.exceptions import AuthorizationException, BusinessException, NotFoundException
from platform_core.schemas.llm_provider import (
    LlmProviderCreate,
    LlmProviderResponse,
    LlmProviderUpdate,
    is_metadata_host,
    is_private_base_url,
    mask_api_key,
)
from stubs import fake_settings as _fake_settings  # 共享桩（唯一定义处见 stubs.py）

# 测试专用 Fernet 主密钥（模块级生成一次，monkeypatch 注入环境变量）
_FERNET_KEY = Fernet.generate_key().decode()
_PLAIN_KEY = "sk-test-plain-1234567890"


def _provider(**overrides) -> SimpleNamespace:
    """可被 LlmProviderResponse.model_validate 的供应商实体桩"""
    defaults = dict(
        id=1, name="prov-a", provider_type="openai_compatible",
        base_url="https://llm.test/v1", api_key_encrypted=None, model="gpt-test",
        temperature=0.2, timeout=120, max_retries=3,
        is_active=False, enabled=True, remark=None, created_at=None, updated_at=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _service() -> LlmProviderService:
    """repo 全 AsyncMock 的服务桩（不连 DB）"""
    svc = LlmProviderService.__new__(LlmProviderService)
    svc.session = MagicMock()
    svc.session.commit = AsyncMock()
    svc.session.refresh = AsyncMock()
    svc.session.rollback = AsyncMock()
    svc.session.execute = AsyncMock()  # B-M2-1：delete_provider 子表清理走 session.execute
    svc.repo = MagicMock()
    for _method in ("get_by_id", "get_by_name", "get_active", "list_providers",
                    "activate_exclusive", "delete", "create", "update",
                    "get_max_updated_at"):
        setattr(svc.repo, _method, AsyncMock())
    return svc


def _planner() -> AiPlannerService:
    """repo 桩化的 AiPlannerService（仅用 _llm_chat，不连 DB）"""
    svc = AiPlannerService.__new__(AiPlannerService)
    svc.session = MagicMock()
    svc.session.commit = AsyncMock()
    svc.session.refresh = AsyncMock()
    svc.session.rollback = AsyncMock()
    svc.repo = MagicMock()
    return svc


# ---------------- Fernet 加密 ----------------
class TestEncryption:
    @pytest.mark.asyncio
    async def test_roundtrip(self, monkeypatch):
        """配置主密钥后：密文 ≠ 明文，解密还原明文"""
        monkeypatch.setenv("LLM_ENCRYPTION_KEY", _FERNET_KEY)
        svc = _service()
        encrypted = svc.encrypt_api_key(_PLAIN_KEY)
        assert encrypted and encrypted != _PLAIN_KEY
        assert encrypted.startswith("gAAAA")  # Fernet token 前缀
        assert svc.decrypt_api_key(encrypted) == _PLAIN_KEY

    @pytest.mark.asyncio
    async def test_encrypt_without_master_key_rejected(self, monkeypatch):
        """未配置 LLM_ENCRYPTION_KEY：保存带 api_key 的请求直接拒绝（不降级明文入库）"""
        monkeypatch.delenv("LLM_ENCRYPTION_KEY", raising=False)
        with patch("backend.services.llm_secret_vault.settings", _fake_settings()):
            svc = _service()
            with pytest.raises(BusinessException) as ei:
                svc.encrypt_api_key(_PLAIN_KEY)
        assert "LLM_ENCRYPTION_KEY" in str(ei.value)

    @pytest.mark.asyncio
    async def test_encrypt_empty_key_is_noop(self):
        """空密文路径：encrypt_api_key(None/空串) 返回空串，不触发主密钥检查"""
        svc = _service()
        assert svc.encrypt_api_key(None) == ""
        assert svc.encrypt_api_key("") == ""

    @pytest.mark.asyncio
    async def test_decrypt_failure_treated_as_missing(self, monkeypatch):
        """密文损坏（或主密钥轮换）：解密失败按密钥缺失处理，返回空串不抛异常"""
        monkeypatch.setenv("LLM_ENCRYPTION_KEY", _FERNET_KEY)
        svc = _service()
        assert svc.decrypt_api_key("not-a-valid-fernet-token") == ""

    @pytest.mark.asyncio
    async def test_decrypt_without_master_key_treated_as_missing(self, monkeypatch):
        """读取时未配置主密钥：按密钥缺失处理（log warning + 空串），不影响请求链路"""
        monkeypatch.delenv("LLM_ENCRYPTION_KEY", raising=False)
        with patch("backend.services.llm_secret_vault.settings", _fake_settings()):
            svc = _service()
            assert svc.decrypt_api_key("whatever-cipher") == ""

    @pytest.mark.asyncio
    async def test_invalid_master_key_rejected(self, monkeypatch):
        """主密钥格式非法：拒绝并提示生成命令"""
        monkeypatch.setenv("LLM_ENCRYPTION_KEY", "definitely-not-a-fernet-key")
        svc = _service()
        with pytest.raises(BusinessException) as ei:
            svc.encrypt_api_key(_PLAIN_KEY)
        assert "格式非法" in str(ei.value)


# ---------------- 掩码 ----------------
class TestMask:
    def test_mask_hides_plaintext(self):
        masked = mask_api_key("sk-abcdef123456")
        assert masked == "***3456"
        assert "abcdef" not in masked
        assert "sk-" not in masked

    def test_mask_empty_key_returns_empty(self):
        assert mask_api_key(None) == ""
        assert mask_api_key("") == ""

    def test_mask_short_key(self):
        assert mask_api_key("abc") == "***abc"

    @pytest.mark.asyncio
    async def test_response_never_leaks_plaintext(self, monkeypatch):
        """响应级：api_key_masked 仅含尾 4 位，序列化结果无明文"""
        monkeypatch.setenv("LLM_ENCRYPTION_KEY", _FERNET_KEY)
        svc = _service()
        encrypted = svc.encrypt_api_key(_PLAIN_KEY)
        resp = await svc._to_response(_provider(api_key_encrypted=encrypted))
        assert resp.api_key_masked == mask_api_key(_PLAIN_KEY)
        assert _PLAIN_KEY not in resp.model_dump_json()


# ---------------- CRUD ----------------
class TestCrud:
    @pytest.mark.asyncio
    async def test_create_encrypts_key(self, monkeypatch):
        monkeypatch.setenv("LLM_ENCRYPTION_KEY", _FERNET_KEY)
        svc = _service()
        svc.repo.get_by_name = AsyncMock(return_value=None)
        svc.repo.create = AsyncMock(return_value=_provider(id=7, name="p"))
        svc.repo.get_by_id = AsyncMock(return_value=_provider(id=7, name="p"))
        payload = LlmProviderCreate(name="p", base_url="https://llm.test/v1",
                                    model="m", api_key=_PLAIN_KEY)
        resp = await svc.create_provider(payload)
        kwargs = svc.repo.create.await_args.kwargs
        assert kwargs["api_key_encrypted"].startswith("gAAAA")
        assert _PLAIN_KEY not in kwargs["api_key_encrypted"]
        assert kwargs["name"] == "p"
        svc.session.commit.assert_awaited()
        assert resp.id == 7

    @pytest.mark.asyncio
    async def test_create_duplicate_name_rejected(self):
        svc = _service()
        svc.repo.get_by_name = AsyncMock(return_value=_provider(id=2, name="prov-a"))
        payload = LlmProviderCreate(name="prov-a", base_url="https://llm.test/v1", model="m")
        with pytest.raises(BusinessException) as ei:
            await svc.create_provider(payload)
        assert "已存在" in str(ei.value)
        svc.repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_with_api_key_without_master_key_rejected(self, monkeypatch):
        """未配置主密钥 + 带 api_key：拒绝且不落库"""
        monkeypatch.delenv("LLM_ENCRYPTION_KEY", raising=False)
        with patch("backend.services.llm_secret_vault.settings", _fake_settings()):
            svc = _service()
            payload = LlmProviderCreate(name="p", base_url="https://llm.test/v1",
                                        model="m", api_key=_PLAIN_KEY)
            with pytest.raises(BusinessException):
                await svc.create_provider(payload)
        svc.repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_blank_api_key_keeps_existing(self):
        """前端契约：PUT api_key 留空不修改（不产生空覆盖）"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_provider(id=1))
        payload = LlmProviderUpdate(api_key="")
        with patch("backend.services.llm_provider_service._invalidate_llm_clients",
                   new=AsyncMock()):
            await svc.update_provider(1, payload)
        svc.repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_new_key_reencrypts(self, monkeypatch):
        monkeypatch.setenv("LLM_ENCRYPTION_KEY", _FERNET_KEY)
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_provider(id=1))
        svc.repo.update = AsyncMock(return_value=_provider(id=1))
        payload = LlmProviderUpdate(api_key="sk-brand-new-key")
        with patch("backend.services.llm_provider_service._invalidate_llm_clients",
                   new=AsyncMock()):
            await svc.update_provider(1, payload)
        kwargs = svc.repo.update.await_args.kwargs
        assert kwargs["api_key_encrypted"].startswith("gAAAA")
        assert "sk-brand-new-key" not in kwargs["api_key_encrypted"]

    @pytest.mark.asyncio
    async def test_update_name_conflict_rejected(self):
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_provider(id=1, name="a"))
        svc.repo.get_by_name = AsyncMock(return_value=_provider(id=2, name="b"))
        with pytest.raises(BusinessException) as ei:
            await svc.update_provider(1, LlmProviderUpdate(name="b"))
        assert "已存在" in str(ei.value)

    @pytest.mark.asyncio
    async def test_delete_allows_active_provider(self):
        """激活位随行删除：激活行也允许删除（resolve 无激活行时自动走兜底）"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_provider(id=1, is_active=True))
        svc.repo.delete = AsyncMock(return_value=True)  # 旧物理删除桩保留兼容
        svc.repo.soft_delete = AsyncMock(return_value=True)
        with patch("backend.services.llm_provider_service._invalidate_llm_clients",
                   new=AsyncMock()) as inv:
            result = await svc.delete_provider(1)
        assert result == {"id": 1, "deleted": True}
        svc.repo.soft_delete.assert_awaited_once_with(1)
        inv.assert_awaited_once_with(1)  # 定向失效该供应商的共享连接

    @pytest.mark.asyncio
    async def test_activate_calls_exclusive_and_invalidates_all(self):
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_provider(id=3))
        with patch("backend.services.llm_provider_service._invalidate_llm_clients",
                   new=AsyncMock()) as inv:
            resp = await svc.activate_provider(3)
        svc.repo.activate_exclusive.assert_awaited_once_with(3)
        inv.assert_awaited_once_with()  # 全清（旧激活行连接不再权威）
        assert resp.id == 3

    @pytest.mark.asyncio
    async def test_get_provider_missing_raises(self):
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(NotFoundException):
            await svc.get_provider(999)


# ---------------- 单激活互斥（repo 级） ----------------
class TestActivateExclusive:
    @pytest.mark.asyncio
    async def test_single_statement_case_update(self):
        """activate_exclusive 是单条 UPDATE ... CASE 语句（目标行置 1、其余置 0）"""
        repo = LlmProviderRepository(MagicMock())
        repo.session.execute = AsyncMock()
        await repo.activate_exclusive(5)
        stmt = repo.session.execute.await_args.args[0]
        compiled = str(stmt.compile()).upper()
        assert "CASE" in compiled
        assert "IS_ACTIVE" in compiled
        assert compiled.strip().startswith("UPDATE")

    @pytest.mark.asyncio
    async def test_get_active_and_max_updated_at(self):
        repo = LlmProviderRepository(MagicMock())
        repo.session.execute = AsyncMock()
        repo.session.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=_provider(id=1)))
        assert (await repo.get_active()).id == 1
        repo.session.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=None))
        assert await repo.get_max_updated_at() is None


# ---------------- resolve 兜底顺序 ----------------
class TestResolveRuntimeConfig:
    @pytest.mark.asyncio
    async def test_active_enabled_provider_wins(self, monkeypatch):
        """激活且 enabled 且密钥可用 → provider 路径（source=provider:<id>）"""
        monkeypatch.setenv("LLM_ENCRYPTION_KEY", _FERNET_KEY)
        svc = _service()
        encrypted = svc.encrypt_api_key("sk-live-key")
        svc.repo.get_active = AsyncMock(return_value=_provider(
            id=3, is_active=True, enabled=True, api_key_encrypted=encrypted))
        cfg = await svc.resolve_runtime_config()
        assert cfg.source == "provider:3"
        assert cfg.provider_id == 3
        assert cfg.api_key == "sk-live-key"
        assert cfg.base_url == "https://llm.test/v1"
        assert cfg.enabled is True

    @pytest.mark.asyncio
    async def test_no_active_row_falls_back(self, monkeypatch):
        """无激活行 → yml/env 兜底；密钥读取顺序 env 优先于 yml（与现状一致）"""
        monkeypatch.setenv("LLM_API_KEY", "env-key")
        svc = _service()
        svc.repo.get_active = AsyncMock(return_value=None)
        with patch("backend.services.ai_planner_service.settings", _fake_settings(
                **{"LLM.ENABLED": True, "LLM.BASE_URL": "http://fb.test/v1",
                   "LLM.MODEL": "m2", "LLM.API_KEY": "yml-key"})):
            cfg = await svc.resolve_runtime_config()
        assert cfg.source == "config"
        assert cfg.provider_id is None
        assert cfg.api_key == "env-key"  # env 优先
        assert cfg.base_url == "http://fb.test/v1"
        assert cfg.enabled is True

    @pytest.mark.asyncio
    async def test_fallback_without_env_uses_yml_key(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        svc = _service()
        svc.repo.get_active = AsyncMock(return_value=None)
        with patch("backend.services.ai_planner_service.settings", _fake_settings(
                **{"LLM.ENABLED": False, "LLM.API_KEY": "yml-key"})):
            cfg = await svc.resolve_runtime_config()
        assert cfg.source == "config"
        assert cfg.api_key == "yml-key"
        assert cfg.enabled is False

    @pytest.mark.asyncio
    async def test_disabled_active_row_falls_back(self, monkeypatch):
        """激活行被禁用 → 兜底"""
        svc = _service()
        svc.repo.get_active = AsyncMock(return_value=_provider(id=3, enabled=False))
        with patch("backend.services.ai_planner_service.settings", _fake_settings(
                **{"LLM.ENABLED": True})):
            cfg = await svc.resolve_runtime_config()
        assert cfg.source == "config"

    @pytest.mark.asyncio
    async def test_active_row_missing_key_falls_back(self, monkeypatch):
        """激活行密钥缺失/解密失败 → 按密钥缺失处理并回退兜底"""
        svc = _service()
        svc.repo.get_active = AsyncMock(return_value=_provider(id=3, api_key_encrypted=None))
        with patch("backend.services.ai_planner_service.settings", _fake_settings(
                **{"LLM.ENABLED": True})):
            cfg = await svc.resolve_runtime_config()
        assert cfg.source == "config"

    @pytest.mark.asyncio
    async def test_delete_active_provider_then_resolve_falls_back(self, monkeypatch):
        """删除激活行 → 激活位随行删除，resolve 自动走 yml/env 兜底"""
        monkeypatch.setenv("LLM_API_KEY", "env-key")
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_provider(id=1, is_active=True))
        svc.repo.delete = AsyncMock(return_value=True)  # 旧物理删除桩保留兼容
        svc.repo.soft_delete = AsyncMock(return_value=True)
        with patch("backend.services.llm_provider_service._invalidate_llm_clients",
                   new=AsyncMock()):
            await svc.delete_provider(1)
        svc.repo.get_active = AsyncMock(return_value=None)  # 删除后无激活行
        with patch("backend.services.ai_planner_service.settings", _fake_settings(
                **{"LLM.ENABLED": True, "LLM.BASE_URL": "http://fb.test/v1",
                   "LLM.MODEL": "m2"})):
            cfg = await svc.resolve_runtime_config()
        assert cfg.source == "config"
        assert cfg.api_key == "env-key"

    def test_resolve_config_from_settings_shape(self, monkeypatch):
        """兜底配置形状：字段与 _llm_chat 读取项一一对应"""
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        with patch("backend.services.ai_planner_service.settings", _fake_settings(
                **{"LLM.ENABLED": True, "LLM.BASE_URL": "http://x/v1/",
                   "LLM.MODEL": "m", "LLM.TEMPERATURE": 0.5, "LLM.TIMEOUT": 30,
                   "LLM.MAX_RETRIES": 2, "LLM.API_KEY": "k"})):
            cfg = resolve_config_from_settings()
        assert isinstance(cfg, LlmRuntimeConfig)
        assert cfg.base_url == "http://x/v1"  # 去尾斜杠
        assert cfg.timeout == 30.0 and cfg.max_retries == 2 and cfg.temperature == 0.5
        assert cfg.source == "config" and cfg.provider_id is None


# ---------------- _llm_chat provider 路径（共享 client + token 维度） ----------------
class TestLlmChatProviderPath:
    @staticmethod
    def _ok_response(content: str = "hi", tokens: int = 42) -> MagicMock:
        resp = MagicMock()
        resp.json.return_value = {
            "choices": [{"message": {"content": content}}],
            "usage": {"total_tokens": tokens},
        }
        return resp

    @pytest.mark.asyncio
    async def test_provider_path_uses_shared_client_and_token_dimension(self, monkeypatch):
        """provider 路径：复用共享 client（同 key 二次调用不新建），token 按 provider 维度累计"""
        monkeypatch.setattr("backend.services.ai_planner_service._TOKEN_USAGE", {})
        cfg = LlmRuntimeConfig(
            base_url="https://p.test/v1", api_key="sk-p", model="m", temperature=0.1,
            timeout=5.0, max_retries=2, enabled=True, source="provider:9", provider_id=9,
        )
        client = MagicMock()
        client.is_closed = False
        client.post = AsyncMock(return_value=self._ok_response())
        client.aclose = AsyncMock()
        client_cls = MagicMock(return_value=client)
        svc = _planner()
        try:
            with patch("backend.services.ai_planner_service._resolve_llm_runtime_config",
                       AsyncMock(return_value=cfg)), \
                 patch("backend.services.ai_planner_service.httpx.AsyncClient", client_cls), \
                 patch("backend.services.ai_planner_service.settings", _fake_settings(
                     **{"LLM.MAX_TOKENS_BUDGET": 1000})):
                first = await svc._llm_chat([{"role": "user", "content": "hi"}])
                second = await svc._llm_chat([{"role": "user", "content": "hi"}])
            assert first == "hi" and second == "hi"
            assert client.post.await_count == 2
            client_cls.assert_called_once()  # 共享 client 复用，未重复创建
            from backend.services.ai_planner_service import _TOKEN_USAGE
            assert _TOKEN_USAGE["provider:9"] == 84  # 42 * 2，按 provider 维度累计
            assert _TOKEN_USAGE.get("config", 0) == 0
        finally:
            from backend.services.ai_planner_service import invalidate_client_cache
            await invalidate_client_cache()  # 清理共享缓存，避免污染其他用例
            _HTTP_CLIENTS.clear()
            _HTTP_CLIENT_OWNER.clear()


# ---------------- invalidate_client_cache ----------------
class TestInvalidateClientCache:
    @pytest.mark.asyncio
    async def test_targeted_invalidation_by_provider(self):
        from backend.services.ai_planner_service import invalidate_client_cache
        c5, c6 = MagicMock(), MagicMock()
        c5.aclose = AsyncMock()
        c6.aclose = AsyncMock()
        try:
            _HTTP_CLIENTS[("u5", "h5")] = c5
            _HTTP_CLIENT_OWNER[("u5", "h5")] = 5
            _HTTP_CLIENTS[("u6", "h6")] = c6
            _HTTP_CLIENT_OWNER[("u6", "h6")] = 6
            await invalidate_client_cache(5)
            c5.aclose.assert_awaited_once()
            c6.aclose.assert_not_awaited()
            assert ("u5", "h5") not in _HTTP_CLIENTS
            assert ("u6", "h6") in _HTTP_CLIENTS
        finally:
            _HTTP_CLIENTS.clear()
            _HTTP_CLIENT_OWNER.clear()

    @pytest.mark.asyncio
    async def test_invalidate_all(self):
        from backend.services.ai_planner_service import invalidate_client_cache
        c = MagicMock()
        c.aclose = AsyncMock()
        try:
            _HTTP_CLIENTS[("u", "h")] = c
            _HTTP_CLIENT_OWNER[("u", "h")] = 1
            await invalidate_client_cache()
            c.aclose.assert_awaited_once()
            assert _HTTP_CLIENTS == {} and _HTTP_CLIENT_OWNER == {}
        finally:
            _HTTP_CLIENTS.clear()
            _HTTP_CLIENT_OWNER.clear()


# ---------------- test_connectivity ----------------
class TestConnectivity:
    @pytest.mark.asyncio
    async def test_ok(self, monkeypatch):
        monkeypatch.setenv("LLM_ENCRYPTION_KEY", _FERNET_KEY)
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_provider(
            id=1, api_key_encrypted=svc.encrypt_api_key(_PLAIN_KEY)))
        resp = MagicMock(status_code=200, text="")
        client = MagicMock()
        client.post = AsyncMock(return_value=resp)
        client_cls = MagicMock()
        client_cls.return_value = AsyncMock()
        client_cls.return_value.__aenter__.return_value = client
        client_cls.return_value.__aexit__.return_value = False
        with patch("backend.services.llm_probe_engine.httpx.AsyncClient", client_cls):
            result = await svc.test_connectivity(1)
        assert result.ok is True
        assert result.error is None
        assert result.model == "gpt-test"
        assert result.latency_ms >= 0
        url = client.post.await_args.args[0]
        assert url == "https://llm.test/v1/chat/completions"
        payload = client.post.await_args.kwargs["json"]
        assert payload["max_tokens"] == 16
        assert client.post.await_args.kwargs["headers"]["Authorization"] == f"Bearer {_PLAIN_KEY}"

    @pytest.mark.asyncio
    async def test_http_error_reported(self):
        """HTTP 错误脱敏（评审 M-1）：仅状态码 + 标准化原因，不回显响应体"""
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_provider(id=1))
        resp = MagicMock(status_code=403, reason_phrase="Forbidden", text="secret-body-contents")
        client = MagicMock()
        client.post = AsyncMock(return_value=resp)
        client_cls = MagicMock()
        client_cls.return_value = AsyncMock()
        client_cls.return_value.__aenter__.return_value = client
        client_cls.return_value.__aexit__.return_value = False
        with patch("backend.services.llm_probe_engine.httpx.AsyncClient", client_cls):
            result = await svc.test_connectivity(1)
        assert result.ok is False
        assert result.error == "HTTP 403 Forbidden"
        assert "secret-body-contents" not in result.error

    @pytest.mark.asyncio
    async def test_network_error_reported(self):
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=_provider(id=1))
        client = MagicMock()
        client.post = AsyncMock(side_effect=httpx.ConnectError("boom"))
        client_cls = MagicMock()
        client_cls.return_value = AsyncMock()
        client_cls.return_value.__aenter__.return_value = client
        client_cls.return_value.__aexit__.return_value = False
        with patch("backend.services.llm_probe_engine.httpx.AsyncClient", client_cls):
            result = await svc.test_connectivity(1)
        assert result.ok is False
        assert "boom" in result.error

    @pytest.mark.asyncio
    async def test_missing_provider_raises(self):
        svc = _service()
        svc.repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(NotFoundException):
            await svc.test_connectivity(999)


# ---------------- SSRF 加固（评审 M-1） ----------------
class TestBaseUrlSsrfGuard:
    """base_url SSRF 加固：元数据端点恒拒绝（schema 层，不受开关影响）"""

    @pytest.mark.parametrize("url", [
        "http://169.254.169.254/v1",       # AWS metadata 字面量
        "http://169.254.0.1/v1",           # link-local 网段内其他地址
        "http://metadata.google.internal/v1",
        "http://metadata/v1",
        "https://METADATA.internal:8443",   # 大小写归一后命中
    ])
    def test_metadata_endpoints_rejected(self, url):
        with pytest.raises(ValidationError):
            LlmProviderCreate(name="p", base_url=url, model="m")

    def test_is_metadata_host(self):
        assert is_metadata_host("169.254.169.254") is True
        assert is_metadata_host("metadata.azure.internal") is True
        assert is_metadata_host("api.openai.com") is False
        assert is_metadata_host("127.0.0.1") is False

    def test_private_local_paths_allowed_by_schema(self):
        """本地 new-api/ollama 属文档化合法路径：schema 层放行（服务层开关控制）"""
        payload = LlmProviderCreate(
            name="local", base_url="http://localhost:3000/v1", model="m")
        assert payload.base_url == "http://localhost:3000/v1"

    def test_is_private_base_url_detection(self):
        assert is_private_base_url("http://127.0.0.1:3000/v1") is True
        assert is_private_base_url("http://localhost:3000") is True
        assert is_private_base_url("http://10.0.0.5/v1") is True
        assert is_private_base_url("http://192.168.1.5") is True
        assert is_private_base_url("http://172.16.0.1") is True
        assert is_private_base_url("http://2130706433") is True  # 整数编码 IP
        assert is_private_base_url("http://proxy.internal") is True
        assert is_private_base_url("https://api.openai.com/v1") is False
        assert is_private_base_url("http://8.8.8.8") is False


class TestPrivateUrlSwitch:
    """LLM.PROVIDER_BLOCK_PRIVATE_URL 开关（评审 M-1）：服务层校验"""

    @pytest.mark.asyncio
    async def test_switch_on_rejects_private_create(self, monkeypatch):
        """开关 true：创建私网 base_url 被拒"""
        monkeypatch.setenv("LLM_ENCRYPTION_KEY", _FERNET_KEY)
        with patch("backend.services.llm_secret_vault.settings", _fake_settings(
                **{"LLM.PROVIDER_BLOCK_PRIVATE_URL": True})):
            svc = _service()
            svc.repo.get_by_name = AsyncMock(return_value=None)
            payload = LlmProviderCreate(
                name="p", base_url="http://10.0.0.5/v1", model="m")
            with pytest.raises(BusinessException) as ei:
                await svc.create_provider(payload)
        assert "PROVIDER_BLOCK_PRIVATE_URL" in str(ei.value)
        svc.repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_switch_on_rejects_private_update(self, monkeypatch):
        """开关 true：更新为私网 base_url 被拒"""
        with patch("backend.services.llm_secret_vault.settings", _fake_settings(
                **{"LLM.PROVIDER_BLOCK_PRIVATE_URL": True})):
            svc = _service()
            svc.repo.get_by_id = AsyncMock(return_value=_provider(id=1))
            with pytest.raises(BusinessException):
                await svc.update_provider(
                    1, LlmProviderUpdate(base_url="http://192.168.1.1/v1"))
            svc.repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_switch_off_allows_private(self, monkeypatch):
        """开关 false（默认）：本地 new-api/ollama 合法路径正常创建"""
        monkeypatch.setenv("LLM_ENCRYPTION_KEY", _FERNET_KEY)
        with patch("backend.services.llm_secret_vault.settings", _fake_settings(
                **{"LLM.PROVIDER_BLOCK_PRIVATE_URL": False})):
            svc = _service()
            svc.repo.get_by_name = AsyncMock(return_value=None)
            svc.repo.create = AsyncMock(return_value=_provider(id=9, base_url="http://localhost:3000/v1"))
            svc.repo.get_by_id = AsyncMock(return_value=_provider(id=9, base_url="http://localhost:3000/v1"))
            payload = LlmProviderCreate(
                name="local-newapi", base_url="http://localhost:3000/v1", model="m")
            resp = await svc.create_provider(payload)
        assert resp.base_url == "http://localhost:3000/v1"

    @pytest.mark.asyncio
    async def test_switch_default_off(self):
        """默认配置（llm.yml false / 缺省）不拦截私网"""
        with patch("backend.services.llm_secret_vault.settings", _fake_settings()):
            assert LlmProviderService._ensure_public_base_url(
                "http://127.0.0.1:18901/v1") is None

    @pytest.mark.asyncio
    async def test_metadata_rejected_even_when_switch_off(self, monkeypatch):
        """元数据端点在 schema 层恒拒绝，与服务层开关无关"""
        with pytest.raises(ValidationError):
            LlmProviderCreate(
                name="p", base_url="http://169.254.169.254/v1", model="m")


# ---------------- 权限 ----------------
class TestPermissions:
    @pytest.mark.asyncio
    async def test_write_requires_admin(self):
        with pytest.raises(AuthorizationException):
            await require_admin(user=CurrentUser(id=2, username="op", role="operator"))

    @pytest.mark.asyncio
    async def test_admin_passes(self):
        user = await require_admin(user=CurrentUser(id=1, username="admin", role="admin"))
        assert user.role == "admin"


# ---------------- API 端点契约 ----------------
class TestApiEndpoints:
    @pytest.fixture
    def llm_client(self, client, app):
        """client + get_async_db override（mock session，审计提交不落库）"""
        from platform_core.db import get_async_db

        session = MagicMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        app.dependency_overrides[get_async_db] = lambda: session
        yield client
        app.dependency_overrides.pop(get_async_db, None)

    def test_list_endpoint_direct_array_masked(self, llm_client, monkeypatch):
        """GET /llm/providers 直出数组（无信封无分页），api_key_masked 掩码且无明文字段"""
        resp_obj = LlmProviderResponse(
            id=1, name="a", provider_type="openai_compatible", base_url="https://x/v1",
            api_key_masked="***cdef", model="m", temperature=0.2, timeout=120, max_retries=3,
        )

        async def fake_list(self):
            return [resp_obj]

        monkeypatch.setattr(LlmProviderService, "list_providers", fake_list)
        resp = llm_client.get("/api/v1/llm/providers")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        items = body["data"]
        assert isinstance(items, list)
        assert items[0]["api_key_masked"] == "***cdef"
        assert "api_key" not in items[0]  # 明文字段不存在于契约

    def test_active_endpoint_none_returns_404(self, llm_client, monkeypatch):
        async def fake_active(self):
            from platform_core.exceptions import NotFoundException

            raise NotFoundException("激活的 LLM 供应商")

        monkeypatch.setattr(LlmProviderService, "get_active_provider", fake_active)
        resp = llm_client.get("/api/v1/llm/providers/active")
        assert resp.status_code == 404

    def test_create_endpoint_admin_ok(self, llm_client, monkeypatch):
        async def fake_create(self, payload):
            return LlmProviderResponse(
                id=1, name=payload.name, provider_type="openai_compatible",
                base_url=payload.base_url, model=payload.model, temperature=0.2,
                timeout=120, max_retries=3,
            )

        monkeypatch.setattr(LlmProviderService, "create_provider", fake_create)
        monkeypatch.setattr("backend.app.api.v1.llm_providers.record_audit", AsyncMock())
        resp = llm_client.post("/api/v1/llm/providers",
                               json={"name": "p", "base_url": "https://x/v1", "model": "m"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True and body["code"] == "CREATED"
        assert body["data"]["name"] == "p"

    def test_create_endpoint_rejects_operator(self, llm_client, app):
        """写操作仅 admin：operator 403（恢复必须还原 conftest 原 override——本地重造旧签名
        会丢失 Bearer 直通链路，污染后续 SaaS 用例的租户身份解析）"""
        from backend.app.api.deps import CurrentUser as _CU, get_current_user

        async def _operator_user():
            return _CU(id=2, username="op", role="operator")

        original = app.dependency_overrides[get_current_user]
        app.dependency_overrides[get_current_user] = _operator_user
        try:
            resp = llm_client.post("/api/v1/llm/providers",
                                   json={"name": "p", "base_url": "https://x/v1", "model": "m"})
        finally:
            app.dependency_overrides[get_current_user] = original
        assert resp.status_code == 403

    def test_test_endpoint_shape(self, llm_client, monkeypatch):
        """POST /llm/providers/{id}/test 信封 data={ok, latency_ms, model, error}（ADR-001）"""
        from platform_core.schemas.llm_provider import LlmProviderTestResponse

        async def fake_test(self, provider_id):
            return LlmProviderTestResponse(ok=False, latency_ms=12, model="m", error="HTTP 401")

        monkeypatch.setattr(LlmProviderService, "test_connectivity", fake_test)
        monkeypatch.setattr("backend.app.api.v1.llm_providers.record_audit", AsyncMock())
        resp = llm_client.post("/api/v1/llm/providers/1/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["ok"] is False and body["data"]["latency_ms"] == 12
        assert body["data"]["model"] == "m" and body["data"]["error"] == "HTTP 401"

    def test_activate_endpoint_admin_ok(self, llm_client, monkeypatch):
        async def fake_activate(self, provider_id):
            return LlmProviderResponse(
                id=provider_id, name="a", provider_type="openai_compatible",
                base_url="https://x/v1", model="m", temperature=0.2, timeout=120,
                max_retries=3, is_active=True,
            )

        monkeypatch.setattr(LlmProviderService, "activate_provider", fake_activate)
        monkeypatch.setattr("backend.app.api.v1.llm_providers.record_audit", AsyncMock())
        resp = llm_client.put("/api/v1/llm/providers/1/activate")
        assert resp.status_code == 200
        assert resp.json()["data"]["is_active"] is True
