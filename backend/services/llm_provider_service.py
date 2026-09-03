"""LLM 供应商管理 —— CRUD 薄壳（B2，工单 82 拆分后）

深模块剥离：
- 加解密/SSRF 守卫 → llm_secret_vault.py（安全关注点一处收口）
- 保存前探测/入库连通测试 → llm_probe_engine.py

本模块保留：CRUD/激活/多模型集全量替换/模型 diff/运行时配置解析
（激活供应商优先，兜底 yml/env；llm_client._llm_chat 消费）。
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.llm_provider_repository import LlmProviderRepository
from backend.services.llm_probe_engine import LlmProbeEngine
from backend.services.llm_secret_vault import LlmSecretVault
from platform_core.models.llm_provider import LlmProvider
from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.exceptions import NotFoundException, ValidationException
from platform_core.models.llm_provider_model import LlmProviderModel
from sqlalchemy import delete, select

from backend.services.llm_protocol import ProtocolError, execute_json, get_adapter
from platform_core.logger import get_logger
from platform_core.schemas.llm_provider import (
    LlmProviderCreate,
    LlmProviderResponse,
    LlmProviderTestResponse,
    LlmProviderUpdate,
    mask_api_key,
)

logger = get_logger("api")

# 连通性测试参数（一次性轻量探测，非业务调用）

# Fernet 主密钥读取顺序：环境变量（含 .env 注入）→ settings 顶层 → settings LLM 嵌套
@dataclass(frozen=True)
class LlmRuntimeConfig:
    """LLM 运行时配置快照（provider 路径或 yml/env 兜底路径的统一形状）

    source: "provider:<id>"（激活供应商）| "config"（yml/env 兜底）
    provider_id: provider 路径时为激活行 id（token 计费维度 / client 缓存归属），兜底为 None
    """

    base_url: str
    api_key: str
    model: str
    temperature: float
    timeout: float
    max_retries: int
    enabled: bool
    source: str
    provider_id: Optional[int] = None
    # B-M3：消费面经此路由到协议适配器（兜底路径恒 openai_compatible）
    protocol: str = "openai_compatible"


def resolve_config_from_settings() -> LlmRuntimeConfig:
    logger.debug("解析 yml/env 兜底 LLM 配置（透传 ai_planner_service 实现）")
    # yml/env 兜底配置（实现位于 ai_planner_service，见模块 docstring 说明）
    from backend.services.ai_planner_service import resolve_config_from_settings as _fallback

    return _fallback()


async def _invalidate_llm_clients(provider_id: Optional[int] = None) -> None:
    """供应商变更/热切换后失效共享 httpx client 缓存（延迟导入避免与 ai_planner 循环依赖）"""
    try:
        from backend.services.ai_planner_service import invalidate_client_cache

        await invalidate_client_cache(provider_id)
    except Exception as e:  # noqa: BLE001 缓存清理失败不影响主流程（连接池自然回收）
        logger.warning(f"LLM 共享 client 缓存清理失败（忽略）: {e}")



class LlmProviderService:
    """LLM 供应商管理编排（CRUD / 激活 / 测试 / 运行时配置解析）"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = LlmProviderRepository(session)

    # ------------------------------------------------------------------
    # 加解密/SSRF 守卫 → llm_secret_vault（B2）；保留同名薄委托兼容存量调用面
    @staticmethod
    def _ensure_public_base_url(base_url: str) -> None:
        LlmSecretVault.ensure_public_base_url(base_url)

    @staticmethod
    def encrypt_api_key(plain: Optional[str]) -> str:
        return LlmSecretVault.encrypt_api_key(plain)

    @staticmethod
    def decrypt_api_key(encrypted: Optional[str]) -> str:
        return LlmSecretVault.decrypt_api_key(encrypted)

    # ------------------------------------------------------------------
    # 响应组装（api_key 恒为掩码）
    # ------------------------------------------------------------------
    async def _to_response(self, item) -> LlmProviderResponse:
        """ORM 行 → 响应（解密仅为取掩码尾 4 位，明文不出方法）"""
        resp = LlmProviderResponse.model_validate(item)
        resp.api_key_masked = mask_api_key(
            self.decrypt_api_key(getattr(item, "api_key_encrypted", None))
        )
        return resp

    # ------------------------------------------------------------------
    # CRUD（前端契约：列表直出数组无信封无分页；api_key 恒为掩码）
    # ------------------------------------------------------------------
    async def list_providers(self) -> list[LlmProviderResponse]:
        """全量列表（api_key 全部掩码；量级小，无分页）"""
        items = await self.repo.list_providers()
        return [await self._to_response(i) for i in items]

    async def get_provider(self, provider_id: int) -> LlmProviderResponse:
        """单条快照（api_key 掩码）"""
        item = await self.repo.get_by_id(provider_id)
        if item is None:
            raise NotFoundException("LLM 供应商")
        return await self._to_response(item)

    async def get_active_provider(self) -> LlmProviderResponse:
        """当前激活供应商（无激活行 404，前端可提示走 yml/env 兜底）"""
        item = await self.repo.get_active()
        if item is None:
            raise NotFoundException("激活的 LLM 供应商")
        return await self._to_response(item)

    async def create_provider(self, payload: LlmProviderCreate) -> LlmProviderResponse:
        """创建供应商（名称唯一；api_key 可选，配置了则必须可加密落库）"""
        existing = await self.repo.get_by_name(payload.name)
        if existing is not None:
            raise BusinessException(f"LLM 供应商 '{payload.name}' 已存在")
        LlmSecretVault.ensure_public_base_url(payload.base_url)
        encrypted = self.encrypt_api_key(payload.api_key)
        item = await self.repo.create(
            name=payload.name,
            provider_type=payload.provider_type,
            base_url=payload.base_url,
            api_key_encrypted=encrypted,
            model=payload.model,
            temperature=payload.temperature,
            timeout=payload.timeout,
            max_retries=payload.max_retries,
            enabled=payload.enabled,
            remark=payload.remark,
        )
        # commit 会 expire ORM 对象（expire_on_commit=True），过期属性访问将触发
        # 同步 refresh → MissingGreenlet，故主键必须在 commit 前固化为普通 int
        new_id = int(item.id)
        # B-M2 向导流：models[] 一并落子表（父行 model 取 is_default 行，缺省取首行）
        if payload.models:
            defaults = [m for m in payload.models if m.is_default]
            if len(defaults) > 1:
                raise ValidationException(message="默认模型至多一个（is_default 多行）", field="models")
            for entry in payload.models:
                self.session.add(
                    LlmProviderModel(
                        provider_id=new_id,
                        model_id=entry.model_id,
                        alias=entry.alias or "",
                        model_tier=entry.model_tier or "basic",
                        priority=int(entry.priority or 100),
                        is_default=bool(entry.is_default),
                        enabled=bool(entry.enabled if entry.enabled is not None else True),
                    )
                )
            chosen = defaults[0].model_id if defaults else payload.models[0].model_id
            item.model = chosen
        await self.session.commit()
        logger.info(f"创建 LLM 供应商: id={new_id}, name={payload.name}")
        return await self.get_provider(new_id)

    async def update_provider(
        self, provider_id: int, payload: LlmProviderUpdate
    ) -> LlmProviderResponse:
        """更新供应商（PATCH 语义；api_key：未提交/空串均不修改，非空重新加密落库）"""
        item = await self.repo.get_by_id(provider_id)
        if item is None:
            raise NotFoundException("LLM 供应商")
        changes = payload.model_dump(exclude_unset=True, exclude_none=True)

        if "name" in changes and changes["name"] != item.name:
            existing = await self.repo.get_by_name(changes["name"])
            if existing is not None and existing.id != provider_id:
                raise BusinessException(f"LLM 供应商 '{changes['name']}' 已存在")

        if "base_url" in changes:
            LlmSecretVault.ensure_public_base_url(changes["base_url"])

        if "api_key" in changes:
            submitted = changes.pop("api_key")
            # 前端契约：留空（空串）或未提交均不修改，非空才重新加密落库
            if submitted:
                changes["api_key_encrypted"] = self.encrypt_api_key(submitted)

        if changes:
            await self.repo.update(provider_id, **changes)
        await self.session.commit()
        await _invalidate_llm_clients(provider_id)  # key/base_url 可能已变，定向失效共享连接
        logger.info(f"更新 LLM 供应商: id={provider_id}, fields={sorted(changes.keys())}")
        return await self.get_provider(provider_id)

    async def delete_provider(self, provider_id: int) -> dict:
        """删除供应商（激活位随行删除；无激活行时 resolve_runtime_config 自动走兜底）"""
        item = await self.repo.get_by_id(provider_id)
        if item is None:
            raise NotFoundException("LLM 供应商")
        # 子表显式清理（Core delete 不触发 ORM cascade，SQLite 默认不启用 FK——
        # 显式语句与 MySQL FK ON DELETE CASCADE 语义对齐的双保险）
        await self.session.execute(
            delete(LlmProviderModel).where(LlmProviderModel.provider_id == provider_id)
        )
        # commit 会 expire ORM 对象且行已删除（refresh 会抛 ObjectDeletedError），
        # 名称必须在 commit 前固化为普通字符串
        deleted_name = str(getattr(item, "name", "") or "")
        deleted = await self.repo.delete(provider_id)
        await self.session.commit()
        await _invalidate_llm_clients(provider_id)
        logger.info(f"LLM 供应商已删除: id={provider_id}, name={deleted_name}")
        return {"id": provider_id, "deleted": deleted}

    async def activate_provider(self, provider_id: int) -> LlmProviderResponse:
        """单激活热切换（activate_exclusive 单语句互斥；旧激活行的共享连接全清失效）"""
        item = await self.repo.get_by_id(provider_id)
        if item is None:
            raise NotFoundException("LLM 供应商")
        await self.repo.activate_exclusive(provider_id)
        await self.session.commit()
        await _invalidate_llm_clients()  # 全清：旧激活行连接不再权威，重建成本低
        logger.info(f"LLM 供应商热切换完成: active_id={provider_id}")
        return await self.get_provider(provider_id)

    # ------------------------------------------------------------------
    # 连通性测试（一次性 client，10s 超时，1-token 请求，不落库）
    # ------------------------------------------------------------------
    # ---------- B-M2-2 fetch diff + 逐模型健康 ----------

    async def fetch_models_diff(self, provider_id: int) -> dict:
        """远端列表 vs 本地子表三分类（new/existing/vanished）——不直写"""
        provider = await self.repo.get_by_id(provider_id)
        if provider is None:
            raise NotFoundException(resource=f"LLM 供应商 {provider_id}")
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

    async def test_model(self, provider_id: int, model_id: str) -> dict:
        """单模型 1-token 测试并落健康态：200→healthy / 401·403→down / 其余→degraded"""
        import time

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
        if row is None:
            raise NotFoundException(resource=f"模型 {model_id}")

        api_key = self.decrypt_api_key(provider.api_key_encrypted)
        adapter = get_adapter(provider.provider_type or "openai_compatible")
        request = adapter.build_chat(
            provider.base_url, api_key, model_id,
            [{"role": "user", "content": "ping"}], max_tokens=1,
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

        row.health_status = status
        row.last_latency_ms = latency_ms
        row.last_checked_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self.session.flush()
        return {"ok": ok, "latency_ms": latency_ms, "model": model_id, "error": error, "health_status": status}

    # ---------- B-M2-1 多模型（全量替换 + 默认冗余同步） ----------

    async def get_models(self, provider_id: int) -> list[dict]:
        """列供应商全部模型（含健康态）"""
        rows = (
            await self.session.execute(
                select(LlmProviderModel)
                .where(LlmProviderModel.provider_id == provider_id)
                .order_by(LlmProviderModel.priority.asc(), LlmProviderModel.id.asc())
            )
        ).scalars().all()
        return [
            {
                "model_id": r.model_id, "alias": r.alias or "", "model_tier": r.model_tier,
                "priority": r.priority, "is_default": r.is_default, "enabled": r.enabled,
                "health_status": r.health_status,
                "last_checked_at": r.last_checked_at.isoformat() if r.last_checked_at else None,
                "last_latency_ms": r.last_latency_ms,
            }
            for r in rows
        ]

    async def put_models(self, provider_id: int, entries: list[dict]) -> list[dict]:
        """全量替换模型集；is_default 至多一行（多行 422）；默认变更同事务刷新父行 model 列"""
        logger.info(f"模型集全量替换 | provider={provider_id} count={len(entries)}")
        provider = await self.repo.get_by_id(provider_id)
        if provider is None:
            raise NotFoundException(resource=f"LLM 供应商 {provider_id}")

        defaults = [e for e in entries if e.get("is_default")]
        if len(defaults) > 1:
            raise ValidationException(
                message="默认模型至多一个（is_default 多行）", field="models"
            )

        await self.session.execute(
            delete(LlmProviderModel).where(LlmProviderModel.provider_id == provider_id)
        )
        for entry in entries:
            self.session.add(
                LlmProviderModel(
                    provider_id=provider_id,
                    model_id=entry["model_id"],
                    alias=entry.get("alias") or "",
                    model_tier=entry.get("model_tier") or "basic",
                    priority=int(entry.get("priority") or 100),
                    is_default=bool(entry.get("is_default")),
                    enabled=bool(entry.get("enabled", True)),
                )
            )
        if defaults:
            provider.model = defaults[0]["model_id"]  # 冗余快照：消费路径零改动的前提
        elif entries:
            provider.model = entries[0]["model_id"]
        await self.session.flush()
        await _invalidate_llm_clients(provider_id)
        return await self.get_models(provider_id)

    # ---------- B-M1 探测（保存前；key 仅本次请求使用，不落库不落日志不回显） ----------

    # 探测 → llm_probe_engine（B2）；同名薄委托兼容存量调用面
    @staticmethod
    async def probe_models(provider_type: str, base_url: str, api_key: str) -> dict:
        return await LlmProbeEngine.probe_models(provider_type, base_url, api_key)

    @staticmethod
    async def probe_test(provider_type: str, base_url: str, api_key: str, model: str) -> dict:
        return await LlmProbeEngine.probe_test(provider_type, base_url, api_key, model)


    async def test_connectivity(self, provider_id: int) -> LlmProviderTestResponse:
        """入库连通测试 → llm_probe_engine（B2 薄委托）"""
        return await LlmProbeEngine.test_connectivity(self.repo, provider_id)

    
    # ------------------------------------------------------------------
    # 运行时配置解析（激活供应商优先，兜底 yml/env；_llm_chat 消费）
    # ------------------------------------------------------------------
    async def resolve_runtime_config(self) -> LlmRuntimeConfig:
        """三段解析（S1-4）：当前租户激活行 → 平台公共行（tenant_id NULL，兜底）→ yml/env

        无租户上下文（legacy/后台）保持原语义：任一激活行优先。
        """
        from platform_core.tenant_context import current_tenant_id

        tenant_id = current_tenant_id()
        if tenant_id is not None:
            active = (await self.session.execute(
                select(LlmProvider).where(
                    LlmProvider.is_active == True,  # noqa: E712
                    LlmProvider.enabled == True,  # noqa: E712
                    LlmProvider.tenant_id == tenant_id,
                )
            )).scalar_one_or_none()
            if active is None:
                # 平台公共供应商兜底（免费档语义：配额约束在 S3 检查点执行）
                active = (await self.session.execute(
                    select(LlmProvider).where(
                        LlmProvider.enabled == True,  # noqa: E712
                        LlmProvider.tenant_id.is_(None),
                    ).order_by(LlmProvider.id.asc())
                )).scalars().first()
        else:
            active = await self.repo.get_active()
        if active is not None and bool(active.enabled):
            api_key = self.decrypt_api_key(getattr(active, "api_key_encrypted", None))
            base_url = str(active.base_url or "").rstrip("/")
            model = str(active.model or "")
            if api_key and base_url and model:
                return LlmRuntimeConfig(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    temperature=float(active.temperature),
                    timeout=float(active.timeout),
                    max_retries=max(1, int(active.max_retries)),
                    enabled=True,
                    source=f"provider:{active.id}",
                    provider_id=int(active.id),
                    protocol=str(active.provider_type or "openai_compatible"),
                )
            logger.warning(
                "激活的 LLM 供应商配置不完整（密钥缺失/解密失败/base_url/model 为空），"
                f"回退 yml/env 兜底: provider_id={getattr(active, 'id', None)}"
            )
        return resolve_config_from_settings()

