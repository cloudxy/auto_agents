"""LLM 模型冷却深模块（feat-llm-cooldown）

Redis string 键 llm:cooldown:{provider_id}:{model_id}，值=连续失败次数。
值达到阈值即冷却中（TTL 未过期）；TTL 过期自动恢复。
Redis 故障 fail-open：读侧不过滤任何模型、写侧吞异常——冷却是优化不是依赖。
"""
from platform_core.logger import get_logger
from platform_core.queues import LLM_COOLDOWN_PREFIX
from platform_core.redis_async import get_async_redis
from config import settings

logger = get_logger("service.llm.cooldown")

_DEFAULT_THRESHOLD = 2
_DEFAULT_SECONDS = 300


def _threshold() -> int:
    return int(settings.get("LLM.FAILOVER.COOLDOWN_THRESHOLD", _DEFAULT_THRESHOLD) or _DEFAULT_THRESHOLD)


def _seconds() -> int:
    return int(settings.get("LLM.FAILOVER.COOLDOWN_SECONDS", _DEFAULT_SECONDS) or _DEFAULT_SECONDS)


def _key(provider_id: int, model_id: str) -> str:
    return f"{LLM_COOLDOWN_PREFIX}{provider_id}:{model_id}"


async def record_failure(provider_id: int, model_id: str) -> None:
    """记录一次失败（pipeline INCR+EXPIRE 原子提交；达阈值时刷新 TTL 确保窗口完整）。"""
    if not provider_id:
        return
    try:
        redis = get_async_redis()
        key = _key(provider_id, model_id)
        pipe = redis.pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, _seconds())
        count, _ = await pipe.execute()
        if int(count) >= _threshold():
            logger.warning(f"模型进入冷却 | provider={provider_id} model={model_id} count={count} window={_seconds()}s")
    except Exception as e:  # noqa: BLE001 fail-open
        logger.debug(f"冷却写入失败（忽略）: {e}")


async def is_cooled_down(provider_id: int, model_id: str) -> bool:
    """模型是否冷却中：GET 值 ≥ 阈值（非仅 EXISTS——QA-2 修复：首次失败建键但值 < 阈值不算冷却）。"""
    if not provider_id:
        return False
    try:
        redis = get_async_redis()
        v = await redis.get(_key(provider_id, model_id))
        return v is not None and int(v) >= _threshold()
    except Exception:  # noqa: BLE001
        return False


async def filter_cooled(provider_id: int, model_ids: list[str]) -> list[str]:
    """批量过滤冷却模型（单次 MGET，NFR-02：不逐模型 EXISTS）。"""
    if not provider_id or not model_ids:
        return model_ids
    try:
        redis = get_async_redis()
        keys = [_key(provider_id, m) for m in model_ids]
        values = await redis.mget(keys)
        threshold = _threshold()
        return [m for m, v in zip(model_ids, values) if v is None or int(v) < threshold]
    except Exception:  # noqa: BLE001 fail-open：全返回
        return model_ids


async def clear(provider_id: int, model_id: str) -> None:
    """清除冷却（手动重测连通成功时调用）。"""
    if not provider_id:
        return
    try:
        redis = get_async_redis()
        await redis.delete(_key(provider_id, model_id))
        logger.info(f"模型冷却清除 | provider={provider_id} model={model_id}")
    except Exception as e:  # noqa: BLE101
        logger.debug(f"冷却清除失败（忽略）: {e}")
