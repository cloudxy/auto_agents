"""LLM 供应商连通性与模型健康：远端模型 diff / 逐模型 1-token 测试 / 入库连通测试

拆分自 llm_provider_service.py（规模治理，行为零变化）：LlmProviderService 继承
LlmProviderHealthMixin，fetch_models_diff / test_model / test_connectivity 的方法名、
签名与调用面不变（类级 patch LlmProviderService.<method> 照常生效）。

mixin 依赖宿主类提供：self.session / self.repo / self.decrypt_api_key /
self._guard_platform_provider_write。本模块不 import llm_provider_service（无环）。
"""
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.llm_provider_repository import LlmProviderRepository
from backend.services.ai_planner._cooldown import clear as _cooldown_clear
from backend.services.llm_probe_engine import LlmProbeEngine
from backend.services.llm_protocol import ProtocolError, execute_json, get_adapter
from backend.services.llm_secret_vault import LlmSecretVault
from platform_core.exceptions import NotFoundException
from platform_core.logger import get_logger
from platform_core.models.llm_provider_model import LlmProviderModel
from platform_core.schemas.llm_provider import LlmProviderTestResponse

logger = get_logger("api")


class LlmProviderHealthMixin:
    """连通/健康编排（宿主：LlmProviderService）"""

    session: AsyncSession
    repo: LlmProviderRepository

    # ---------- B-M2-2 fetch diff + 逐模型健康 ----------

    async def fetch_models_diff(self, provider_id: int) -> dict:
        """远端列表 vs 本地子表三分类（new/existing/vanished）——不直写"""
        provider = await self.repo.get_by_id(provider_id)
        if provider is None:
            raise NotFoundException(resource=f"LLM 供应商 {provider_id}")
        await LlmSecretVault.assert_outbound_base_url(provider.base_url)
        api_key = self.decrypt_api_key(provider.api_key_encrypted)
        adapter = get_adapter(provider.provider_type or "openai_compatible")
        remote = await adapter.list_models(provider.base_url, api_key)
        remote_ids = set(remote.ids())
        local_ids = set(
            (await self.session.execute(
                select(LlmProviderModel.model_id).where(LlmProviderModel.provider_id == provider_id)
            )).scalars()
        )
        return {
            "new": sorted(remote_ids - local_ids),
            "existing": sorted(remote_ids & local_ids),
            "vanished": sorted(local_ids - remote_ids),
        }

    async def test_model(self, provider_id: int, model_id: str, *, commit: bool = True) -> dict:
        """单模型 1-token 测试（落库行持久化健康态；未落库行一次性测试即回）：200→healthy / 401·403→down / 其余→degraded

        ADR-0007 D3：默认自持事务（API 直调）；被巡检等批量场景组合时传
        commit=False，由外层统一提交（中途提交会 expire 循环内 ORM 行）。
        """
        logger.info(f"模型连通测试 | provider={provider_id} model={model_id}")
        provider = await self.repo.get_by_id(provider_id)
        if provider is None:
            raise NotFoundException(resource=f"LLM 供应商 {provider_id}")
        row = (await self.session.execute(
            select(LlmProviderModel).where(
                LlmProviderModel.provider_id == provider_id,
                LlmProviderModel.model_id == model_id,
            )
        )).scalar_one_or_none()

        ok, error, status, latency_ms = await self._ping_model(provider, model_id)
        if row is not None:
            # feat-llm-cooldown：连通成功立即清除冷却
            if ok:
                await _cooldown_clear(provider_id, model_id)
            row.health_status = status
            row.last_latency_ms = latency_ms
            row.last_checked_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await self.session.flush()
        else:
            # 未落库模型（导入新增的预览测试）：一次性测试，结果即回不落库——
            # 保存（put_models）后再次测试才持久化健康态
            logger.debug(f"模型未落库，一次性测试 | provider={provider_id} model={model_id}")
        if commit and row is not None:
            await self.session.commit()
        return {"ok": ok, "latency_ms": latency_ms, "model": model_id, "error": error, "health_status": status}

    async def _ping_model(self, provider, model_id: str) -> tuple[bool, str, str, int]:
        """出站 1-token ping，返回 (ok, error, health_status, latency_ms)"""
        await LlmSecretVault.assert_outbound_base_url(provider.base_url)
        api_key = self.decrypt_api_key(provider.api_key_encrypted)
        adapter = get_adapter(provider.provider_type or "openai_compatible")
        request = adapter.build_chat(
            provider.base_url, api_key, model_id,
            [{"role": "user", "content": "ping"}], max_tokens=16,
        )
        started = time.perf_counter()
        try:
            data = await execute_json(None, "POST", request.url, request.headers, request.json_payload)
            if not adapter.parse_chat(data):
                raise ProtocolError("HTTP 200 响应缺少文本内容")
            ok, error, status = True, "", "healthy"
        except ProtocolError as exc:
            ok, error = False, str(exc)
            status = "down" if any(f"HTTP {code}" in str(exc) for code in (401, 403)) else "degraded"
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ok, error, status, latency_ms

    # ---------- 入库连通测试（探测 → llm_probe_engine） ----------

    async def test_connectivity(
        self, provider_id: int,
        *, actor_is_platform_admin: bool | None = None,
        actor_id: int | None = None, actor_name: str = "",
    ) -> LlmProviderTestResponse:
        """入库连通测试（测该行地址；平台行对非超管拒绝）"""
        logger.info(f"测试 LLM 供应商连通 | id={provider_id}")
        item = await self.repo.get_by_id(provider_id)
        if item is None:
            raise NotFoundException("LLM 供应商")
        await self._guard_platform_provider_write(
            item, actor_is_platform_admin=actor_is_platform_admin,
            actor_id=actor_id, actor_name=actor_name,
        )
        result = await LlmProbeEngine.test_connectivity(self.repo, provider_id)
        # feat-llm-cooldown（QA-7）：连通成功清除默认模型冷却
        if result.ok and result.model:
            await _cooldown_clear(provider_id, result.model)
        try:
            row = (await self.session.execute(
                select(LlmProviderModel).where(
                    LlmProviderModel.provider_id == provider_id,
                    LlmProviderModel.model_id == result.model,
                )
            )).scalar_one_or_none()
            if row is not None:
                row.health_status = "healthy" if result.ok else "down"
                if result.latency_ms is not None:
                    row.last_latency_ms = result.latency_ms
                from datetime import datetime, timezone

                row.last_checked_at = datetime.now(timezone.utc).replace(tzinfo=None)
                await self.session.commit()
        except Exception as e:  # noqa: BLE001 健康态同步失败不影响测试结果返回
            logger.warning(f"连通测试健康态同步失败: provider={provider_id}, error={e}")
        return result
