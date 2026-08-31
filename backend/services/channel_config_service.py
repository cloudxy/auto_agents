"""渠道调度配置服务（4.2 接线：管理面 → Redis hash → 调度器生效）

背景（审计 P1-6）：channel_scheduler_service 只读 newapi:channel:cfg:{id}，
全仓无写入方——三层开关全开时受管渠道仍为 0，调度器每轮空转。本服务补齐
"方向盘"：渠道级额度配置的查/写/清除（经 get_async_redis 异步门面），
写操作落 channel_events 留痕；审计由 API 层 record_audit 记录。
"""
import time
from typing import Optional

from config import settings
from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.redis_async import get_async_redis
from platform_core.schemas.newapi import (
    ChannelConfigInfo,
    ChannelWithConfigResponse,
)
from backend.repositories.newapi_repository import ChannelEventRepository
from backend.services.newapi_api import NEWAPI_CHANNEL_CFG_PREFIX, NewapiApiClient
from backend.services.newapi_overview_service import _map_channel

logger = get_logger("api")

_OVERVIEW_TIMEOUT_SECONDS = 8


# 全局默认配置（newapi.yml DEFAULT_* 三元组）
def _global_default() -> ChannelConfigInfo:
    logger.debug("解析全局默认渠道调度配置")
    return ChannelConfigInfo(
        limit_quota=int(settings.get("NEWAPI.DEFAULT_WINDOW_QUOTA", 0) or 0),
        window_hours=int(settings.get("NEWAPI.DEFAULT_WINDOW_HOURS", 24) or 24),
        cooldown_seconds=int(settings.get("NEWAPI.DEFAULT_COOLDOWN_SECONDS", 3600) or 3600),
    )


# 渠道级配置的 Redis hash 键（与调度器读取侧同一前缀契约）
def _cfg_key(channel_id: int) -> str:
    logger.debug(f"构造渠道配置键: channel_id={channel_id}")
    return f"{NEWAPI_CHANNEL_CFG_PREFIX}{channel_id}"


class ChannelConfigService:
    """渠道级额度配置：列表合并视图 / 写入 / 清除"""

    def __init__(self):
        self._client: Optional[NewapiApiClient] = None

    @property
    def client(self) -> NewapiApiClient:
        if self._client is None:
            self._client = NewapiApiClient(timeout=_OVERVIEW_TIMEOUT_SECONDS)
        return self._client

    async def _read_cfg(self, channel_id: int) -> Optional[ChannelConfigInfo]:
        """读渠道级配置（无配置/坏值返回 None；limit_quota<=0 视为显式关闭 → 也返回 None 归入未纳管）"""
        try:
            raw = await get_async_redis().hgetall(_cfg_key(channel_id))
        except Exception as e:  # noqa: BLE001 Redis 故障按未配置处理（读路径降级）
            logger.warning(f"读取渠道配置失败: channel_id={channel_id}, error={e}")
            return None
        if not raw:
            return None
        try:
            info = ChannelConfigInfo(
                limit_quota=int(raw.get("limit_quota", 0) or 0),
                window_hours=int(raw.get("window_hours", 24) or 24),
                cooldown_seconds=int(raw.get("cooldown_seconds", 3600) or 3600),
            )
        except (TypeError, ValueError):
            return None
        if info.limit_quota <= 0:
            return None
        return info

    async def list_channels(self) -> list[ChannelWithConfigResponse]:
        """渠道列表 + 配置合并视图（渠道级 > 全局默认；远程不可达抛业务异常）"""
        logger.debug("拉取渠道列表并合并调度配置")
        try:
            channels = await self.client.list_channels()
        except Exception as e:  # noqa: BLE001 远程故障向上抛业务码（前端可提示）
            raise BusinessException(
                message=f"new-api 管理面不可达：{e}",
                code="NEWAPI_UNREACHABLE",
                status_code=502,
            )
        global_default = _global_default()
        result: list[ChannelWithConfigResponse] = []
        for raw in channels or []:
            mapped = _map_channel(raw)
            if mapped is None:
                continue
            cid = int(mapped.id)
            cfg = await self._read_cfg(cid)
            if cfg is not None:
                effective, source = cfg, "channel"
            elif global_default.limit_quota > 0:
                effective, source = global_default, "global"
            else:
                effective, source = global_default, "none"
            result.append(
                ChannelWithConfigResponse(
                    **mapped.model_dump(),
                    config=cfg,
                    effective=effective,
                    effective_source=source,
                )
            )
        return result

    async def set_config(self, channel_id: int, info: ChannelConfigInfo) -> ChannelConfigInfo:
        """写入渠道级配置（hash 字段与调度器读取契约一一对应）"""
        logger.info(
            f"写入渠道调度配置: channel_id={channel_id}, "
            f"limit_quota={info.limit_quota}, window_hours={info.window_hours}"
        )
        await self._ensure_channel_exists(channel_id)
        try:
            redis = get_async_redis()
            key = _cfg_key(channel_id)
            await redis.hset(key, mapping={
                "limit_quota": str(info.limit_quota),
                "window_hours": str(info.window_hours),
                "cooldown_seconds": str(info.cooldown_seconds),
                "updated_at": str(int(time.time())),
            })
        except Exception as e:  # noqa: BLE001
            raise BusinessException(
                message=f"渠道配置写入失败：{e}", code="REDIS_WRITE_FAILED", status_code=502
            )
        await self._record_event(
            channel_id, action="config_updated", info=info,
            reason=f"额度配置更新：窗口 {info.window_hours}h 上限 {info.limit_quota}，"
                   f"超限冷却 {info.cooldown_seconds}s",
        )
        return info

    async def clear_config(self, channel_id: int) -> ChannelConfigInfo | None:
        """清除渠道级配置（回退全局默认）；返回清除前的配置（无配置时返回 None）"""
        logger.info(f"清除渠道调度配置: channel_id={channel_id}")
        previous = await self._read_cfg(channel_id)
        try:
            await get_async_redis().delete(_cfg_key(channel_id))
        except Exception as e:  # noqa: BLE001
            raise BusinessException(
                message=f"渠道配置清除失败：{e}", code="REDIS_WRITE_FAILED", status_code=502
            )
        await self._record_event(
            channel_id, action="config_cleared", info=previous,
            reason="额度配置已清除（回退全局默认或退出纳管）",
        )
        return previous

    async def _ensure_channel_exists(self, channel_id: int) -> None:
        """校验渠道存在（防止把配置写到不存在的 ID 上静默空转）"""
        try:
            channel = await self.client.get_channel(channel_id)
        except Exception as e:  # noqa: BLE001 远程故障视为不可校验，放行写入（hash 独立于远程）
            logger.warning(f"渠道存在性校验失败（放行写入）: channel_id={channel_id}, error={e}")
            return
        if channel is None:
            raise NotFoundException(f"new-api 渠道 #{channel_id} ")

    @staticmethod
    async def _record_event(
        channel_id: int, action: str, info: Optional[ChannelConfigInfo], reason: str
    ) -> None:
        """channel_events 落库（独立短事务；失败仅告警不影响配置写入）"""
        from backend.services.channel_scheduler_service import _main_async_session

        try:
            async with _main_async_session() as session:
                await ChannelEventRepository(session).create_event(
                    channel_id=channel_id,
                    action=action,
                    usage=None,
                    limit_quota=info.limit_quota if info else None,
                    window_hours=info.window_hours if info else None,
                    reason=reason,
                    source="admin",
                )
                await session.commit()
        except Exception as e:  # noqa: BLE001 事件失败不阻断配置写入
            logger.warning(f"渠道配置事件落库失败（忽略）: channel_id={channel_id}, error={e}")
