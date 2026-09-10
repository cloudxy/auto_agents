"""网关窗口调度（T-19）：spend HTTP → budget；仅冷却恢复且不覆盖人工禁用。

禁止 DSN / SQL / 1:1 复刻 new-api 启停。配置只读 RELAY.*，状态新写 RELAY.*。
"""
import asyncio
import time
from datetime import datetime, timedelta, timezone

from backend.config_consts import (
    RELAY_DEFAULT_COOLDOWN_SECONDS,
    RELAY_DEFAULT_WINDOW_HOURS,
    RELAY_DEFAULT_WINDOW_QUOTA,
    RELAY_INTERVAL_SECONDS,
    RELAY_LOCK_TTL_SECONDS,
    RELAY_SCHEDULER_ENABLED,
)
from backend.repositories.newapi_repository import ChannelEventRepository
from backend.services.gateway_models import items_from_payload, map_gateway_model
from backend.services.llm_gateway import admin as gw_admin
from backend.services.newapi_api import (
    NEWAPI_SCHEDULER_LOCK_KEY,
    _cfg_manual_disabled,
    _channel_id_from_ref,
    _main_async_session,
    delete_state_json,
    read_cfg_hash,
    read_state_json,
    write_state_json,
)
from backend.services.notify_service import NotifyService
from config import settings
from platform_core.logger import get_logger
from platform_core.queues import distributed_lock

logger = get_logger("api")


def _budget_id(gateway_ref: str) -> str:
    return f"relay:{gateway_ref}"


def _window_dates(window_hours: int) -> tuple[str, str]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=max(int(window_hours or 24), 1))
    return start.date().isoformat(), end.date().isoformat()


def _spend_rows(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "logs", "results", "spend"):
        val = payload.get(key)
        if isinstance(val, list):
            return [x for x in val if isinstance(x, dict)]
    if "model" in payload or "spend" in payload:
        return [payload]
    return []


def _row_spend(row: dict) -> float:
    for key in ("spend", "total_cost", "total_spend", "cost"):
        if row.get(key) is None:
            continue
        try:
            return float(row[key])
        except (TypeError, ValueError):
            continue
    return 0.0


def _row_model(row: dict) -> str:
    return str(
        row.get("model") or row.get("model_id") or row.get("model_group") or ""
    ).strip()


def _spend_map(payload: object) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in _spend_rows(payload):
        mid = _row_model(row)
        if not mid:
            continue
        out[mid] = out.get(mid, 0.0) + _row_spend(row)
    return out


def _parse_limit_cfg(raw: dict | None) -> dict | None:
    if not raw:
        return None

    def _int(field: str, default: int) -> int:
        try:
            return int(raw.get(field, default))
        except (TypeError, ValueError):
            return default

    limit = _int("limit_quota", 0)
    if limit <= 0:
        return None
    return {
        "limit_quota": limit,
        "window_hours": _int("window_hours", 24),
        "cooldown_seconds": _int("cooldown_seconds", 3600),
    }


class ChannelSchedulerService:
    """spend→budget 窗口；backend 只留冷却恢复且不覆盖人工禁用。"""

    def __init__(self):
        self._running = False
        self._loop_task: asyncio.Task | None = None
        self._redis = None

    async def start(self) -> None:
        """启动调度循环（幂等；无 DSN）。"""
        if self._running:
            return
        if not settings.get("RELAY.SCHEDULER_ENABLED", RELAY_SCHEDULER_ENABLED):
            logger.info("渠道调度器已禁用（RELAY.SCHEDULER_ENABLED=false），不启动")
            return
        from platform_core.redis_async import get_async_redis as _get_async_redis

        self._redis = _get_async_redis()
        self._running = True
        self._loop_task = asyncio.create_task(
            self._tick_loop(), name="gateway-channel-scheduler",
        )
        interval = int(
            settings.get("RELAY.INTERVAL_SECONDS", RELAY_INTERVAL_SECONDS)
            or RELAY_INTERVAL_SECONDS
        )
        logger.info(f"渠道调度器已启动（spend HTTP / 无 DSN）: interval={interval}s")

    async def stop(self) -> None:
        """优雅停止（不关闭共享 Redis）。"""
        self._running = False
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._loop_task = None
        self._redis = None
        logger.info("渠道调度器已停止")

    async def _tick_loop(self) -> None:
        interval = int(
            settings.get("RELAY.INTERVAL_SECONDS", RELAY_INTERVAL_SECONDS)
            or RELAY_INTERVAL_SECONDS
        )
        while self._running:
            try:
                await self._tick_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                logger.error(f"渠道调度轮次失败: {e}")
            await asyncio.sleep(interval)

    async def _tick_once(self) -> None:
        """抢锁 → 列模型 → 读 spend → budget 写 / 冷却恢复。"""
        lock_ttl = int(
            settings.get("RELAY.LOCK_TTL_SECONDS", RELAY_LOCK_TTL_SECONDS)
            or RELAY_LOCK_TTL_SECONDS
        )
        async with distributed_lock(
            self._redis, NEWAPI_SCHEDULER_LOCK_KEY, ttl=lock_ttl,
        ) as lock:
            if lock is None:
                return
            models = await self._list_mapped()
            if not models:
                logger.debug("网关模型列表为空，本轮跳过")
                return
            spend_by = await self._read_spend_map(models)
            logger.info(f"渠道调度本轮受管模型数: {len(models)}")
            for mapped in models:
                try:
                    await self._process_ref(mapped, spend_by)
                except Exception as e:  # noqa: BLE001
                    logger.error(
                        f"渠道调度处理失败（已隔离）: ref={mapped.get('gateway_ref')}, error={e}"
                    )

    async def _list_mapped(self) -> list[dict]:
        try:
            payload = await gw_admin.list_models()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"网关模型列表不可达，本轮跳过: error={e}")
            return []
        out: list[dict] = []
        for raw in items_from_payload(payload):
            mapped = map_gateway_model(raw)
            if mapped is None:
                continue
            out.append({
                "gateway_ref": mapped.gateway_ref,
                "model_name": mapped.model_name,
                "name": mapped.model_name,
            })
        return out

    async def _read_spend_map(self, models: list[dict]) -> dict[str, float]:
        """先只读 spend（官方 API）；失败则空 map，不写。"""
        hours = int(
            settings.get("RELAY.DEFAULT_WINDOW_HOURS", RELAY_DEFAULT_WINDOW_HOURS)
            or RELAY_DEFAULT_WINDOW_HOURS
        )
        for item in models:
            cfg = await self._effective_cfg(str(item["gateway_ref"]))
            if cfg:
                hours = max(hours, int(cfg["window_hours"]))
        start, end = _window_dates(hours)
        try:
            payload = await gw_admin.get_spend_logs(
                params={"start_date": start, "end_date": end},
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"读取网关 spend 失败（本轮不写 budget）: error={e}")
            return {}
        return _spend_map(payload)

    async def _process_ref(self, mapped: dict, spend_by: dict[str, float]) -> None:
        ref = str(mapped["gateway_ref"])
        cid = _channel_id_from_ref(ref)
        raw = await self._raw_cfg(ref, cid)
        state = await read_state_json(self._redis, channel_id=cid, gateway_ref=ref)
        if _cfg_manual_disabled(raw):
            if state:
                logger.warning(
                    f"模型 {ref} 已人工禁用，跳过冷却恢复并解除跟踪（不覆盖人工操作）"
                )
                await delete_state_json(self._redis, channel_id=cid, gateway_ref=ref)
            return
        cfg = await self._effective_cfg(ref)
        if not cfg:
            return
        if state:
            await self._handle_cooldown(mapped, cfg, state, cid)
            return
        spend = self._lookup_spend(mapped, spend_by)
        if spend >= int(cfg["limit_quota"]):
            await self._open_budget_write(mapped, cfg, spend, cid)

    async def _handle_cooldown(
        self, mapped: dict, cfg: dict, state: dict, cid: int,
    ) -> None:
        ref = str(mapped["gateway_ref"])
        until = int(state.get("cooldown_until") or 0)
        if time.time() < until:
            logger.info(f"模型 {ref} 冷却中，剩余 {int(until - time.time())}s")
            return
        await self._recover_ref(mapped, cfg, cid)

    async def _recover_ref(self, mapped: dict, cfg: dict, cid: int) -> None:
        """冷却到期自动恢复：HTTP 核对人工禁用后才写 budget；不覆盖人工禁用。"""
        ref = str(mapped["gateway_ref"])
        live = await self._list_mapped()
        if not any(item.get("gateway_ref") == ref for item in live):
            logger.warning(f"模型 {ref} 冷却到期但不在网关列表，跳过恢复")
            return
        raw = await self._raw_cfg(ref, cid)
        if _cfg_manual_disabled(raw):
            logger.warning(f"模型 {ref} 冷却到期但已人工禁用，跳过恢复")
            await delete_state_json(self._redis, channel_id=cid, gateway_ref=ref)
            return
        await self._write_budget(ref, cfg)
        await delete_state_json(self._redis, channel_id=cid, gateway_ref=ref)
        await self._record_event(
            channel_id=cid, action="enabled", source="scheduler",
            reason="冷却到期自动恢复上线",
        )
        logger.info(f"模型冷却恢复: ref={ref}")
        await NotifyService().notify_text(
            "channel.enabled",
            f"✅ 模型 {ref}（{mapped.get('name', '')}）冷却结束，已自动恢复",
        )

    async def _open_budget_write(
        self, mapped: dict, cfg: dict, spend: float, cid: int,
    ) -> None:
        """超限：先已读 spend，再打开 budget 写；不禁用模型。"""
        ref = str(mapped["gateway_ref"])
        ok = await self._write_budget(ref, cfg)
        now = int(time.time())
        await write_state_json(
            self._redis,
            {
                "disabled_at": datetime.now().isoformat(timespec="seconds"),
                "cooldown_until": now + int(cfg["cooldown_seconds"]),
                "last_usage": spend,
            },
            channel_id=cid,
            gateway_ref=ref,
        )
        reason = (
            f"近 {cfg['window_hours']}h spend {spend} 达上限 {cfg['limit_quota']}，"
            f"冷却 {cfg['cooldown_seconds']}s 后自动恢复"
        )
        await self._record_event(
            channel_id=cid, action="budget_enforced", usage=int(spend),
            limit_quota=cfg["limit_quota"], window_hours=cfg["window_hours"],
            reason=reason, source="scheduler",
        )
        logger.warning(
            f"窗口超限已映射 budget: ref={ref}, spend={spend}, wrote={ok}"
        )

    async def _write_budget(self, gateway_ref: str, cfg: dict) -> bool:
        body = {
            "budget_id": _budget_id(gateway_ref),
            "max_budget": cfg["limit_quota"],
            "budget_duration": f"{int(cfg['window_hours'])}h",
        }
        try:
            await gw_admin.create_budget(body)
            return True
        except Exception as create_err:  # noqa: BLE001
            logger.info(f"budget/new 未成功，改 update: ref={gateway_ref}, error={create_err}")
        try:
            await gw_admin.update_budget(body)
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"budget 写入失败: ref={gateway_ref}, error={e}")
            return False

    async def _raw_cfg(self, gateway_ref: str, cid: int) -> dict:
        try:
            return await read_cfg_hash(
                self._redis, channel_id=cid, gateway_ref=gateway_ref,
            ) or {}
        except Exception as e:  # noqa: BLE001
            logger.warning(f"读取渠道配置失败: ref={gateway_ref}, error={e}")
            return {}

    async def _effective_cfg(self, gateway_ref: str) -> dict | None:
        cid = _channel_id_from_ref(gateway_ref)
        parsed = _parse_limit_cfg(await self._raw_cfg(gateway_ref, cid))
        if parsed:
            return parsed
        global_limit = int(
            settings.get("RELAY.DEFAULT_WINDOW_QUOTA", RELAY_DEFAULT_WINDOW_QUOTA)
            or RELAY_DEFAULT_WINDOW_QUOTA
        )
        if global_limit <= 0:
            return None
        return {
            "limit_quota": global_limit,
            "window_hours": int(
                settings.get("RELAY.DEFAULT_WINDOW_HOURS", RELAY_DEFAULT_WINDOW_HOURS)
                or RELAY_DEFAULT_WINDOW_HOURS
            ),
            "cooldown_seconds": int(
                settings.get(
                    "RELAY.DEFAULT_COOLDOWN_SECONDS", RELAY_DEFAULT_COOLDOWN_SECONDS,
                )
                or RELAY_DEFAULT_COOLDOWN_SECONDS
            ),
        }

    @staticmethod
    def _lookup_spend(mapped: dict, spend_by: dict[str, float]) -> float:
        ref = str(mapped.get("gateway_ref") or "")
        name = str(mapped.get("model_name") or "")
        if ref in spend_by:
            return float(spend_by[ref])
        if name in spend_by:
            return float(spend_by[name])
        return 0.0

    async def _record_event(
        self,
        *,
        channel_id: int,
        action: str,
        usage: int | None = None,
        limit_quota: int | None = None,
        window_hours: int | None = None,
        reason: str | None = None,
        source: str = "scheduler",
    ) -> None:
        """channel_events 落本库；失败仅告警。"""
        try:
            async with _main_async_session() as session:
                await ChannelEventRepository(session).create_event(
                    channel_id=channel_id, action=action, usage=usage,
                    limit_quota=limit_quota, window_hours=window_hours,
                    reason=reason, source=source,
                )
                await session.commit()
        except Exception as e:  # noqa: BLE001
            logger.error(
                f"渠道事件落库失败: channel_id={channel_id}, action={action}, error={e}"
            )
