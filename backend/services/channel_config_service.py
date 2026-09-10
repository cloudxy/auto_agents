"""渠道/模型调度配置（管理面 → Redis hash → 调度器）

T-18：列表来自 LiteLLM 模型；Redis expand 双读
`newapi:channel:cfg:{id}` → `relay:channel:cfg:{ref}`；新写只落 relay。
channel_id 类型不改（int 路径仍给 expand）。
"""
import time
from typing import Optional

from backend.config_consts import (
    RELAY_DEFAULT_COOLDOWN_SECONDS,
    RELAY_DEFAULT_WINDOW_HOURS,
    RELAY_DEFAULT_WINDOW_QUOTA,
)
from config import settings
from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.redis_async import get_async_redis
from platform_core.schemas.newapi import (
    ChannelConfigInfo,
    GatewayModelWithConfigResponse,
)
from backend.repositories.newapi_repository import ChannelEventRepository
from backend.services.gateway_models import items_from_payload, map_gateway_model
from backend.services.llm_gateway import admin as gw_admin
from backend.services.newapi_api import (
    delete_cfg_hash,
    read_cfg_hash,
    write_cfg_hash,
)

logger = get_logger("api")


def _global_default() -> ChannelConfigInfo:
    logger.debug("解析全局默认渠道调度配置")
    return ChannelConfigInfo(
        limit_quota=int(
            settings.get("RELAY.DEFAULT_WINDOW_QUOTA", RELAY_DEFAULT_WINDOW_QUOTA)
            or RELAY_DEFAULT_WINDOW_QUOTA
        ),
        window_hours=int(
            settings.get("RELAY.DEFAULT_WINDOW_HOURS", RELAY_DEFAULT_WINDOW_HOURS)
            or RELAY_DEFAULT_WINDOW_HOURS
        ),
        cooldown_seconds=int(
            settings.get("RELAY.DEFAULT_COOLDOWN_SECONDS", RELAY_DEFAULT_COOLDOWN_SECONDS)
            or RELAY_DEFAULT_COOLDOWN_SECONDS
        ),
    )


def _parse_cfg(raw: dict) -> Optional[ChannelConfigInfo]:
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


class ChannelConfigService:
    """模型级额度配置：列表合并视图 / 写入 / 清除"""

    async def _read_cfg(
        self, *, channel_id: int | None = None, gateway_ref: str | None = None,
    ) -> Optional[ChannelConfigInfo]:
        """双读配置；坏值/未配置/显式关闭 → None"""
        try:
            raw = await read_cfg_hash(
                get_async_redis(), channel_id=channel_id, gateway_ref=gateway_ref,
            )
        except Exception as e:  # noqa: BLE001 Redis 故障按未配置处理
            logger.warning(f"读取渠道配置失败: channel_id={channel_id}, error={e}")
            return None
        if not raw:
            return None
        return _parse_cfg(raw)

    async def list_channels(self) -> list[GatewayModelWithConfigResponse]:
        """网关模型 + 配置合并；远端不可达返回空列表（总览信封承担 71.3）"""
        logger.info("拉取网关模型并合并调度配置")
        try:
            payload = await gw_admin.list_models()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"网关模型列表不可达（降级空列表）: error={e}")
            return []
        global_default = _global_default()
        result: list[GatewayModelWithConfigResponse] = []
        for raw in items_from_payload(payload):
            mapped = map_gateway_model(raw)
            if mapped is None:
                continue
            row = await self._merge_row(mapped, global_default)
            result.append(row)
        return result

    async def _merge_row(self, mapped, global_default: ChannelConfigInfo):
        cfg = await self._read_cfg(gateway_ref=mapped.gateway_ref)
        if cfg is not None:
            effective, source = cfg, "channel"
        elif global_default.limit_quota > 0:
            effective, source = global_default, "global"
        else:
            effective, source = global_default, "none"
        return GatewayModelWithConfigResponse(
            **mapped.model_dump(),
            config=cfg,
            effective=effective,
            effective_source=source,
        )

    async def set_config(self, channel_id: int, info: ChannelConfigInfo) -> ChannelConfigInfo:
        """int 路径 expand：ref=str(channel_id)；不改 channel_id 类型"""
        logger.info(
            f"写入渠道调度配置: channel_id={channel_id}, "
            f"limit_quota={info.limit_quota}, window_hours={info.window_hours}"
        )
        await self._ensure_ref_exists(str(channel_id))
        return await self._write_ref(str(channel_id), info, channel_id=channel_id)

    async def set_config_ref(
        self, gateway_ref: str, info: ChannelConfigInfo,
    ) -> ChannelConfigInfo:
        """string gateway_ref 写窗口配置（新路径）"""
        logger.info(f"写入网关模型调度配置: gateway_ref={gateway_ref}")
        await self._ensure_ref_exists(gateway_ref)
        return await self._write_ref(gateway_ref, info, channel_id=None)

    async def _write_ref(
        self, gateway_ref: str, info: ChannelConfigInfo, *, channel_id: int | None,
    ) -> ChannelConfigInfo:
        try:
            redis = get_async_redis()
            await write_cfg_hash(
                redis,
                {
                    "limit_quota": str(info.limit_quota),
                    "window_hours": str(info.window_hours),
                    "cooldown_seconds": str(info.cooldown_seconds),
                    "updated_at": str(int(time.time())),
                },
                channel_id=channel_id,
                gateway_ref=gateway_ref,
            )
        except Exception as e:  # noqa: BLE001
            raise BusinessException(
                message=f"渠道配置写入失败：{e}", code="REDIS_WRITE_FAILED", status_code=502
            )
        event_id = channel_id if channel_id is not None else 0
        await self._record_event(
            event_id, action="config_updated", info=info,
            reason=f"额度配置更新：窗口 {info.window_hours}h 上限 {info.limit_quota}，"
                   f"超限冷却 {info.cooldown_seconds}s",
        )
        return info

    async def clear_config(self, channel_id: int) -> ChannelConfigInfo | None:
        """清除 int 路径配置（回退全局默认）"""
        logger.info(f"清除渠道调度配置: channel_id={channel_id}")
        return await self._clear_ref(str(channel_id), channel_id=channel_id)

    async def clear_config_ref(self, gateway_ref: str) -> ChannelConfigInfo | None:
        logger.info(f"清除网关模型调度配置: gateway_ref={gateway_ref}")
        return await self._clear_ref(gateway_ref, channel_id=None)

    async def _clear_ref(
        self, gateway_ref: str, *, channel_id: int | None,
    ) -> ChannelConfigInfo | None:
        previous = await self._read_cfg(channel_id=channel_id, gateway_ref=gateway_ref)
        try:
            await delete_cfg_hash(
                get_async_redis(), channel_id=channel_id, gateway_ref=gateway_ref,
            )
        except Exception as e:  # noqa: BLE001
            raise BusinessException(
                message=f"渠道配置清除失败：{e}", code="REDIS_WRITE_FAILED", status_code=502
            )
        event_id = channel_id if channel_id is not None else 0
        await self._record_event(
            event_id, action="config_cleared", info=previous,
            reason="额度配置已清除（回退全局默认或退出纳管）",
        )
        return previous

    async def _ensure_ref_exists(self, gateway_ref: str) -> None:
        """列表可达且完全无此 ref 时 404；列表失败则放行写入"""
        try:
            payload = await gw_admin.list_models()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"模型存在性校验失败（放行写入）: ref={gateway_ref}, error={e}")
            return
        refs = set()
        for raw in items_from_payload(payload):
            mapped = map_gateway_model(raw)
            if mapped is not None:
                refs.add(mapped.gateway_ref)
                refs.add(mapped.model_name)
        if gateway_ref not in refs:
            raise NotFoundException(f"网关模型 {gateway_ref} ")

    @staticmethod
    async def _record_event(
        channel_id: int, action: str, info: Optional[ChannelConfigInfo], reason: str
    ) -> None:
        """channel_events 落库（独立短事务；失败仅告警不影响配置写入）"""
        from backend.services.newapi_api import _main_async_session

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
