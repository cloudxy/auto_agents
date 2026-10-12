"""LLM 调用的 quota_service 依赖面：企业月度 token 套餐闸 + 用户可见失败文案

拆分自 llm_client.py（规模治理，行为零变化）：_enforce_tenant_token_quota /
_check_llm_tokens / _gateway_unreachable / _no_platform_model / _provider_error。
llm_client 原样 re-export 全部名字，旧 import 路径不变。

本模块不 import 门面、不 import llm_gateway；会话工厂经 llm_common.seam() 晚绑定取值
（含可选的 quota_session_factory 测试缝）。quota_service 一律函数内延迟 import。
"""
from backend.services.llm_common.seam import seam as _seam
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger

logger = get_logger("api")


def _gateway_unreachable(cause: Exception | None = None) -> BusinessException:
    from backend.services.quota_service import GATEWAY_UNREACHABLE_USER

    logger.warning(f"平台 LLM 网关不可达: {cause}")
    return BusinessException(GATEWAY_UNREACHABLE_USER, code="LLM_GATEWAY_UNREACHABLE")


def _no_platform_model() -> BusinessException:
    from backend.services.quota_service import NO_MODEL_USER

    logger.warning("平台网关未登记任何模型")
    return BusinessException(NO_MODEL_USER, code="LLM_GATEWAY_NO_MODEL")


def _provider_error(cause: Exception | None = None) -> BusinessException:
    from backend.services.quota_service import PROVIDER_ERROR_USER

    logger.warning(f"本企业供应商调用失败: {cause}")
    return BusinessException(PROVIDER_ERROR_USER, code="LLM_PROVIDER_ERROR")


async def _check_llm_tokens(session, tenant_id: int, year_month: str) -> None:
    from backend.services.quota_service import (
        QuotaExceededException, QuotaService, wrap_quota_exceeded,
    )

    logger.debug(f"月度 token 闸 | tenant={tenant_id} month={year_month}")
    try:
        await QuotaService(session).check_llm_tokens_month(int(tenant_id), year_month)
    except QuotaExceededException as exc:
        raise wrap_quota_exceeded(exc) from exc


async def _enforce_tenant_token_quota() -> None:
    """企业月度 token 闸：真正打模型 / 出站 HTTP 之前。无租户上下文跳过。"""
    from backend.services.quota_service import shanghai_year_month
    from platform_core.tenant_context import current_tenant_id as _cur_tid

    tid = _cur_tid()
    if tid is None:
        logger.debug("无租户上下文，跳过企业月度 token 闸")
        return
    year_month = shanghai_year_month()
    logger.info(f"套餐闸检查企业月度 token | tenant={tid} month={year_month}")
    factory = getattr(_seam(), "quota_session_factory", None)
    if factory is not None:
        async with factory() as session:
            await _check_llm_tokens(session, int(tid), year_month)
        return
    manager = _seam().get_manager()
    async with _seam().AsyncSession(manager.async_engines["DEFAULT"]) as session:
        await _check_llm_tokens(session, int(tid), year_month)
