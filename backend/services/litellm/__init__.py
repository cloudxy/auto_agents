"""LiteLLM Proxy 接入子包（L1 影子接入 · sidecar 形态）

product-review 任务二的 L1 范围：sidecar proxy 影子接入 + 供应链安全基线。
本包为纯工具层（无业务编排、不进 backend.app 装配），三模块职责：

- guard.py    镜像版本守卫纯函数（compose 解析 + 恶意版本黑名单断言，
              test_litellm_version_guard.py 消费——compose 变更时红）
- exporter.py 配置导出器（llm_providers(+models 子表) → LiteLLM 静态 config.yaml；
              生成文件含明文 api_key，路径 gitignore）
- shadow.py   影子只读对比器（自研候选链决策 vs 生成的 LiteLLM config 路由对照，
              零外呼——不发任何真实 LLM 请求）

分层边界：依赖方向恒单向向下（platform_core / config / models / 无环 service 叶）；
禁止 import ai_planner / llm_provider_service 等带业务编排语义的 service
（shadow.capture_self_side_choice 的延迟 import 仅为读取既有选择逻辑结果，
且全部可注入，与 llm_common ADR-0006 的叶子层口径一致）。
"""
from backend.services.litellm.exporter import (
    ExportResult,
    ModelExportRow,
    ProviderExportRow,
    build_litellm_config,
    export_litellm_config,
    fetch_export_rows,
    render_config_yaml,
)
from backend.services.litellm.guard import (
    BLACKLISTED_VERSIONS,
    check_compose,
    check_version,
    extract_litellm_image,
    image_tag,
)
from backend.services.litellm.shadow import (
    LitellmDeployment,
    SelfSideChoice,
    ShadowDiff,
    ShadowDiffRow,
    capture_self_side_choice,
    compare_routing,
    load_deployments_from_config,
)

__all__ = [
    "BLACKLISTED_VERSIONS",
    "ExportResult",
    "LitellmDeployment",
    "ModelExportRow",
    "ProviderExportRow",
    "SelfSideChoice",
    "ShadowDiff",
    "ShadowDiffRow",
    "build_litellm_config",
    "capture_self_side_choice",
    "check_compose",
    "check_version",
    "compare_routing",
    "export_litellm_config",
    "extract_litellm_image",
    "fetch_export_rows",
    "image_tag",
    "load_deployments_from_config",
    "render_config_yaml",
]
