"""LLM 公共下沉层（T6 service 解环）

被多个 service 域共享、且无业务方向依赖的 LLM 概念收口于此（叶子层，
依赖方向恒单向向下：platform_core / config / repositories / 无环 service 叶）：

- runtime.py  LlmRuntimeConfig（运行时配置快照形状）+ resolve_config_from_settings
  （yml/env 兜底解析）+ resolve_runtime_config（激活供应商三段解析，repo/decrypt
  可注入）——此前散在 llm_provider_service 与 ai_planner.llm_client，是
  llm_provider ⇄ ai_planner 环的纠缠根因
- seam.py     晚绑定命名空间缝（见该模块 docstring；ai_planner 门面装配后注入）

边界（ADR-0006）：
- 本包禁止 import 任何带业务编排语义的 service（llm_provider_service /
  ai_planner 包 / skill 域……）；允许依赖的 service 仅限无状态叶子
  （如 llm_secret_vault）
- cooldown 逻辑上属公共概念，但其存量单测以 backend.services.ai_planner.
  _cooldown 模块命名为 patch 缝，物理搬迁会破坏 patch 语义，故保留原位
  （方向已单向化：消费者 → ai_planner._cooldown → platform_core）
"""
from backend.services.llm_common.seam import bind, seam
from backend.services.llm_common.runtime import (
    LlmRuntimeConfig,
    resolve_config_from_settings,
    resolve_runtime_config,
)

__all__ = [
    "LlmRuntimeConfig",
    "bind",
    "resolve_config_from_settings",
    "resolve_runtime_config",
    "seam",
]
