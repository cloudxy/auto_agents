"""值班页网关模型映射（T-18）：LiteLLM model/info → 无完整上游 Key。"""
from typing import Any, Optional

from platform_core.logger import get_logger
from platform_core.schemas.newapi import GatewayModelResponse

logger = get_logger("api")

DUTY_EMPTY_71_2 = "还没有平台模型，去网关登记"
DUTY_DEGRADE_71_3 = "LLM 网关管理面不可达，仅本地事件/探针"
DUTY_PAGE_EMPTY = "empty"
DUTY_PAGE_DEGRADE = "degrade"
DUTY_PAGE_LIVE = "live"
DUTY_ROW_LIVE = "live"
DUTY_ROW_LIVE_TEXT = "活"

_KEY_FIELDS = frozenset({
    "key", "api_key", "openai_api_key", "anthropic_api_key",
    "master_key", "litellm_api_key", "aws_secret_access_key",
})


def items_from_payload(payload: Any) -> list[dict]:
    """宽松抽出 model/info 列表。"""
    logger.debug("解析网关模型载荷")
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        inner = data.get("data") or data.get("items") or []
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
    return []


def mask_secret(value: Optional[str]) -> Optional[str]:
    """仅掩码；完整 Key 不回传。"""
    logger.debug("掩码上游 Key")
    if not value:
        return None
    text = str(value)
    if len(text) < 8:
        return "***"
    return f"{text[:2]}***{text[-4:]}"


def map_gateway_model(raw: dict) -> Optional[GatewayModelResponse]:
    """LiteLLM 模型/部署条目 → 响应；剔除上游 Key。"""
    logger.debug("映射网关模型条目")
    params = raw.get("litellm_params") if isinstance(raw.get("litellm_params"), dict) else {}
    info = raw.get("model_info") if isinstance(raw.get("model_info"), dict) else {}
    name = str(raw.get("model_name") or raw.get("model") or info.get("id") or "").strip()
    if not name:
        logger.warning(f"网关模型缺名称，跳过: keys={sorted(raw.keys())}")
        return None
    ref = str(info.get("id") or raw.get("model_info_id") or name).strip()
    secret = params.get("api_key") or raw.get("api_key") or raw.get("key")
    extra = {
        k: v for k, v in raw.items()
        if k not in {
            "litellm_params", "model_info", "model_name", "model",
            "api_base", "model_info_id", *_KEY_FIELDS,
        }
    }
    return GatewayModelResponse(
        gateway_ref=ref,
        model_name=name,
        deployment_id=str(info.get("id") or "") or None,
        mode=str(info.get("mode") or "") or None,
        api_base=str(params.get("api_base") or raw.get("api_base") or "") or None,
        api_key_masked=mask_secret(str(secret) if secret else None),
        extra=extra,
    )


def apply_duty_row(
    model: GatewayModelResponse, verdict: Optional[str],
) -> GatewayModelResponse:
    """探针 original → 行态 live / 文字「活」；伪装/离线只打 status，不写「活」。"""
    logger.debug(f"标注值班行态: ref={model.gateway_ref}, verdict={verdict}")
    if verdict == "original":
        return model.model_copy(update={
            "duty_row_status": DUTY_ROW_LIVE,
            "duty_row_status_text": DUTY_ROW_LIVE_TEXT,
        })
    if verdict in {"spoofed", "offline"}:
        return model.model_copy(update={"duty_row_status": verdict})
    return model


def clear_duty_row(model: GatewayModelResponse) -> GatewayModelResponse:
    """降级路径禁止把行标活。"""
    logger.debug(f"清除值班行活标: ref={model.gateway_ref}")
    if model.duty_row_status is None and model.duty_row_status_text is None:
        return model
    return model.model_copy(update={
        "duty_row_status": None,
        "duty_row_status_text": None,
    })


def page_duty_copy(
    available: bool, models: list[GatewayModelResponse],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """页级三句互斥：empty / degrade / live。有活行时不得回空/降级句。"""
    logger.debug(f"合成值班页态: available={available}, models={len(models)}")
    if not available:
        return None, DUTY_DEGRADE_71_3, DUTY_PAGE_DEGRADE
    if not models:
        return DUTY_EMPTY_71_2, None, DUTY_PAGE_EMPTY
    if any(m.duty_row_status == DUTY_ROW_LIVE for m in models):
        return None, None, DUTY_PAGE_LIVE
    return None, None, None
