"""LLM 运行时配置层（自 llm_provider_service / ai_planner.llm_client 下沉，T6）

三个共享概念：
- LlmRuntimeConfig          运行时配置快照形状（provider 路径与 yml/env 兜底路径统一）
- resolve_config_from_settings  yml/env 兜底解析（读取顺序与拆分前完全一致）
- resolve_runtime_config    激活供应商三段解析（本租户激活行 → 平台公共行 → yml/env）

Patch 兼容约定：settings 读取经 seam() 命名空间晚绑定（存量单测 patch
backend.services.ai_planner_service.settings 只对门面命名空间的绑定生效，
行为契约与下沉前完全一致）；resolve_runtime_config 的 repo/decrypt 由
LlmProviderService 委托调用时注入（svc.repo.get_active 等实例级 patch 语义不变）。
"""
import os
from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.llm_provider_repository import LlmProviderRepository
from backend.services.llm_secret_vault import LlmSecretVault
from platform_core.logger import get_logger
from platform_core.models.llm_provider import LlmProvider
from platform_core.tenant_context import current_tenant_id

from backend.services.llm_common.seam import seam as _seam

logger = get_logger("api")


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
    """yml/env 兜底配置：读取顺序与阶段一 _llm_chat 完全一致（零回归保证）。

    settings 读取必须经 seam() 命名空间：test_ai_planner.py / test_llm_provider.py
    对 backend.services.ai_planner_service.settings 的 monkeypatch 只对门面
    命名空间的 settings 绑定生效。
    """
    logger.debug("解析 yml/env 兜底 LLM 配置")
    return LlmRuntimeConfig(
        base_url=str(_seam().settings.get("LLM.BASE_URL", "") or "").rstrip("/"),
        api_key=os.environ.get("LLM_API_KEY") or str(_seam().settings.get("LLM.API_KEY", "") or ""),
        model=str(_seam().settings.get("LLM.MODEL", "") or ""),
        temperature=float(_seam().settings.get("LLM.TEMPERATURE", 0.2)),
        timeout=float(_seam().settings.get("LLM.TIMEOUT", 120)),
        max_retries=max(1, int(_seam().settings.get("LLM.MAX_RETRIES", 3))),
        enabled=bool(_seam().settings.get("LLM.ENABLED", False)),
        source="config",
        provider_id=None,
    )


async def resolve_runtime_config(
    session: AsyncSession,
    *,
    repo: Optional[LlmProviderRepository] = None,
    decrypt: Optional[Callable[[Optional[str]], str]] = None,
) -> LlmRuntimeConfig:
    """三段解析（S1-4）：当前租户激活行 → 平台公共行（tenant_id NULL，兜底）→ yml/env

    原 LlmProviderService.resolve_runtime_config 实现（逻辑原样下沉）；
    repo/decrypt 缺省自建，LlmProviderService 委托调用时注入自身实例——
    存量单测对 svc.repo / svc.decrypt_api_key 的实例级 patch 语义不变。
    无租户上下文（legacy/后台）保持原语义：任一激活行优先。
    """
    if repo is None:
        repo = LlmProviderRepository(session)
    if decrypt is None:
        decrypt = LlmSecretVault.decrypt_api_key

    tenant_id = current_tenant_id()
    if tenant_id is not None:
        active = (await session.execute(
            select(LlmProvider).where(
                LlmProvider.is_active == True,  # noqa: E712
                LlmProvider.enabled == True,  # noqa: E712
                LlmProvider.tenant_id == tenant_id,
                LlmProvider.deleted_at.is_(None),  # 软删行不参与运行时解析
            )
        )).scalar_one_or_none()
        if active is None:
            # 平台公共供应商兜底（免费档语义：配额约束在 S3 检查点执行）
            active = (await session.execute(
                select(LlmProvider).where(
                    LlmProvider.enabled == True,  # noqa: E712
                    LlmProvider.tenant_id.is_(None),
                    LlmProvider.deleted_at.is_(None),
                ).order_by(LlmProvider.id.asc())
            )).scalars().first()
    else:
        active = await repo.get_active()
    if active is not None and bool(active.enabled):
        api_key = decrypt(getattr(active, "api_key_encrypted", None))
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
