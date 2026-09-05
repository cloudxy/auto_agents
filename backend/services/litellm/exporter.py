"""LiteLLM Proxy 配置导出器（L1 影子接入 · 无 DB 静态模式）

事实源：本仓 MySQL 的 llm_providers（enabled 且未软删 = 运行时可用供应商面，
即「激活行」的集合语义——is_active 单激活是自研直连路径的热切换位，导出面
取全部可用行，LiteLLM 侧才能做完整路由对比）+ llm_provider_models 子表
（enabled 且 health != down，与 ai_planner._candidate_chain 同口径）。

输出：LiteLLM Proxy 静态 config.yaml（model_list：model_name="{provider}/{model}"
公开名，litellm_params 含 model 映射前缀 / api_base / api_key）。

安全红线：
- 生成文件含解密后的明文 api_key（LiteLLM config 原生形态；os.environ/通配符
  引用属 L2 议题），缺省路径 deploy/litellm/config.gen.yaml 已登记 .gitignore，
  文件权限 0600；
- 日志绝不输出 api_key（只记 provider_id / 名称 / 模型计数）；
- 解密经 LlmSecretVault（Fernet 主密钥走 LLM_ENCRYPTION_KEY，可注入便于测试）。

失败可回退：无可用供应商时生成空 model_list 文件 + 警告，ExportResult.empty=True
（CLI 据此以非零退出码退出——运维侧「生成失败」不静默）。
"""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.llm_secret_vault import LlmSecretVault
from config import settings
from platform_core.logger import get_logger
from platform_core.models.llm_provider import LlmProvider
from platform_core.models.llm_provider_model import LlmProviderModel

logger = get_logger("service.litellm.exporter")

# LiteLLM 侧协议前缀映射（与 llm_protocol 的三协议对齐）；
# L1 影子验收范围仅 openai_compatible 路径（README 已注明）
_MODEL_PREFIX_BY_PROTOCOL = {
    "openai_compatible": "openai/",
    "anthropic": "anthropic/",
    "google_gemini": "gemini/",
}

_GENERATED_HEADER = (
    "# GENERATED FILE — 由 backend/scripts/export_litellm_config.py 生成，勿手改\n"
    "# 含明文 API Key：禁止提交版本库（.gitignore 已登记）、禁止外传日志/工单\n"
)


@dataclass(frozen=True)
class ModelExportRow:
    """子表行的导出形状（ORM → 纯函数输入的脱壳）"""

    model_id: str
    tier: str
    priority: int
    is_default: bool


@dataclass(frozen=True)
class ProviderExportRow:
    """供应商行的导出形状（api_key 已解密，仅存在于导出链路内存中）"""

    provider_id: int
    name: str
    base_url: str
    api_key: str
    protocol: str
    fallback_model: str
    models: tuple[ModelExportRow, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExportResult:
    """导出结果（不含任何密钥，可安全打印/入日志）"""

    out_path: str
    provider_count: int
    model_count: int
    empty: bool


def _slug(name: str) -> str:
    """model_name 的 provider 段 slug 化（中文/空格/斜杠 → 连字符，保稳定可读）"""
    return re.sub(r"[^a-zA-Z0-9]+", "-", str(name)).strip("-").lower() or "provider"


async def fetch_export_rows(
    session: AsyncSession,
    *,
    decrypt=None,
) -> list[ProviderExportRow]:
    """读库提取导出行：enabled 且未软删的供应商 × 其可用模型子表行。

    decrypt 可注入（缺省 LlmSecretVault.decrypt_api_key）；子表空时保留
    父表 model 默认模型快照作兜底（build 阶段展开为单条 model_list 条目）。
    """
    logger.info("导出器读库开始: llm_providers(enabled) × llm_provider_models")
    providers = (await session.execute(
        select(LlmProvider).where(
            LlmProvider.enabled == True,  # noqa: E712
            LlmProvider.deleted_at.is_(None),
        ).order_by(LlmProvider.id.asc())
    )).scalars().all()
    if not providers:
        logger.warning("无可用 LLM 供应商（enabled 且未软删），导出为空 model_list")
        return []
    sub_rows = (await session.execute(
        select(LlmProviderModel).where(
            LlmProviderModel.enabled == True,  # noqa: E712
            LlmProviderModel.health_status != "down",
        )
    )).scalars().all()
    by_provider: dict[int, list[LlmProviderModel]] = {}
    for row in sub_rows:
        by_provider.setdefault(int(row.provider_id), []).append(row)
    if decrypt is None:
        decrypt = LlmSecretVault.decrypt_api_key
    rows: list[ProviderExportRow] = []
    for p in providers:
        models = tuple(
            ModelExportRow(
                model_id=str(r.model_id),
                tier=str(r.model_tier or "basic"),
                priority=int(r.priority or 100),
                is_default=bool(r.is_default),
            )
            for r in sorted(
                by_provider.get(int(p.id), []),
                key=lambda r: (not r.is_default, r.priority, r.id),
            )
        )
        rows.append(ProviderExportRow(
            provider_id=int(p.id),
            name=str(p.name),
            base_url=str(p.base_url or "").rstrip("/"),
            api_key=str(decrypt(getattr(p, "api_key_encrypted", None)) or ""),
            protocol=str(p.provider_type or "openai_compatible"),
            fallback_model=str(p.model or ""),
            models=models,
        ))
    logger.info(
        f"导出器读库完成: providers={len(rows)} "
        f"models={sum(len(r.models) for r in rows)}"
    )
    return rows


def build_litellm_config(rows: list[ProviderExportRow]) -> dict:
    """纯函数：导出行 → LiteLLM config dict（不发 IO、不落密钥到日志）。

    跳过并警告：协议无 LiteLLM 前缀映射 / base_url 或 api_key 缺失 /
    无任何可用模型（子表空且父表兜底模型也空）的行。
    """
    model_list: list[dict] = []
    for row in rows:
        prefix = _MODEL_PREFIX_BY_PROTOCOL.get(row.protocol)
        if prefix is None:
            logger.warning(
                f"跳过供应商（协议暂不支持导出）: id={row.provider_id} "
                f"name={row.name} protocol={row.protocol}"
            )
            continue
        if not row.base_url or not row.api_key:
            logger.warning(
                f"跳过供应商（base_url/api_key 缺失）: id={row.provider_id} name={row.name}"
            )
            continue
        entries: list[tuple[str, dict]] = []
        if row.models:
            entries = [
                (m.model_id, {
                    "model": f"{prefix}{m.model_id}",
                    "api_base": row.base_url,
                    "api_key": row.api_key,
                })
                for m in row.models
            ]
        elif row.fallback_model:
            # 子表空：父表 model 默认模型快照兜底（与自研消费路径第一阶段一致）
            entries = [(row.fallback_model, {
                "model": f"{prefix}{row.fallback_model}",
                "api_base": row.base_url,
                "api_key": row.api_key,
            })]
        else:
            logger.warning(
                f"跳过供应商（无可用模型）: id={row.provider_id} name={row.name}"
            )
            continue
        slug = _slug(row.name)
        for model_id, litellm_params in entries:
            model_list.append({
                "model_name": f"{slug}/{model_id}",
                "litellm_params": litellm_params,
            })
    # drop_params：OpenAI 兼容端点对可选参数容忍（影子对比期减少无谓 400）
    return {"model_list": model_list, "litellm_settings": {"drop_params": True}}


def render_config_yaml(config: dict) -> str:
    """config dict → YAML 文本（含安全头注释；排序关闭保持 model_list 顺序）"""
    return _GENERATED_HEADER + yaml.safe_dump(
        config, sort_keys=False, allow_unicode=True, default_flow_style=False
    )


async def export_litellm_config(
    session: AsyncSession,
    *,
    out_path: str | None = None,
    decrypt=None,
) -> ExportResult:
    """端到端导出：读库 → build → 写文件（0600，父目录自动创建）。

    out_path 缺省取 settings LITELLM.EXPORT.DEFAULT_OUT（config/default/litellm.yml）。
    返回 ExportResult（empty=True 时调用方应按失败处理：CLI 非零退出码）。
    """
    logger.info(f"LiteLLM 配置导出开始: out={out_path or '<settings 缺省>'}")
    rows = await fetch_export_rows(session, decrypt=decrypt)
    config = build_litellm_config(rows)
    target = Path(out_path or str(settings.get("LITELLM.EXPORT.DEFAULT_OUT", "")))
    if not str(target).strip():
        raise ValueError("导出路径为空：请传 out_path 或配置 LITELLM.EXPORT.DEFAULT_OUT")
    target.parent.mkdir(parents=True, exist_ok=True)
    content = render_config_yaml(config)
    # 0600：文件含明文 api_key，最小权限（已存在文件 chmod 收口）
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(target, 0o600)
    result = ExportResult(
        out_path=str(target),
        provider_count=len(rows),
        model_count=len(config["model_list"]),
        empty=len(config["model_list"]) == 0,
    )
    if result.empty:
        logger.warning(
            f"LiteLLM 配置导出完成但 model_list 为空（无可用供应商）: out={result.out_path}"
        )
    else:
        logger.info(
            f"LiteLLM 配置导出完成: out={result.out_path} "
            f"providers={result.provider_count} models={result.model_count}"
        )
    return result
