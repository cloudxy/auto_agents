"""LLM 故障转移候选链查询 + 跨级降质告警

拆分自 llm_client.py（规模治理，行为零变化）：_candidate_chain / _query_chain /
_notify_degrade。编排函数 _failover 仍留在 llm_client（递归调用 llm_chat），
并经 llm_client 模块全局名调用 _candidate_chain——patch
backend.services.ai_planner.llm_client._candidate_chain 的语义不变。

本模块不 import 门面、不 import llm_gateway；会话工厂经 llm_common.seam() 晚绑定取值。
"""
from sqlalchemy import select

from backend.services.llm_common.seam import seam as _seam
from platform_core.logger import get_logger

logger = get_logger("api")


async def _candidate_chain(provider_id: int, session=None):
    """候选链：enabled 且 health != down，priority 升序，默认模型行首位

    session 可注入（测试经 db_session）；缺省独立短事务（与 _resolve 同范式）。
    查询失败返回空链（故障转移静默退化为单模型语义，不放大故障）。
    """
    try:
        if session is not None:
            return await _query_chain(session, provider_id)
        manager = _seam().get_manager()
        async with _seam().AsyncSession(manager.async_engines["DEFAULT"]) as s:
            return await _query_chain(s, provider_id)
    except Exception as exc:  # noqa: BLE001 候选链不可用不阻断主路径
        logger.warning(f"候选链查询失败（跳过故障转移）: {exc}")
        return []


async def _query_chain(session, provider_id: int):
    from platform_core.models.llm_provider_model import LlmProviderModel

    rows = (await session.execute(
        select(LlmProviderModel)
        .where(
            LlmProviderModel.provider_id == provider_id,
            LlmProviderModel.enabled == True,  # noqa: E712
            LlmProviderModel.health_status != "down",
        )
        .order_by(LlmProviderModel.priority.asc(), LlmProviderModel.id.asc())
    )).scalars().all()
    ordered = sorted(rows, key=lambda r: (not r.is_default,))
    # feat-llm-cooldown：批量过滤冷却模型（单次 MGET，NFR-02）
    from backend.services.ai_planner._cooldown import filter_cooled

    all_ids = [r.model_id for r in ordered]
    active_ids = set(await filter_cooled(provider_id, all_ids))
    if len(active_ids) < len(all_ids):
        skipped = [m for m in all_ids if m not in active_ids]
        logger.info(f"候选链跳过冷却模型 | models={skipped}")
    return [(r.model_id, r.model_tier) for r in ordered if r.model_id in active_ids]


async def _notify_degrade(cfg, fallback_model: str) -> None:
    """跨级降质告警（strong→basic 不静默）；通知失败仅记日志"""
    try:
        from backend.services.notify_service import NotifyService

        await NotifyService().notify_text(
            "llm.failover.degrade",
            f"LLM 故障转移发生跨级降质（strong→basic）：{cfg.model} → {fallback_model}，"
            "输出质量可能下降，请检查主模型可用性",
        )
    except Exception as exc:  # noqa: BLE001 告警通道故障不影响业务
        logger.warning(f"降质告警发送失败（忽略）: {exc}")
