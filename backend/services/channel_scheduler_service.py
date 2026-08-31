"""new-api 渠道调度器服务（阶段三）

职责（后台 asyncio task，随 Backend lifespan 启停）：
- 每 tick 抢 Redis 互斥锁（多实例防重，newapi:scheduler:lock）→ 拉取渠道清单
- 直连 new-api 库（独立 engine，NEWAPI.DB_DSN）聚合 logs 表窗口用量
- 超限渠道 → 调 new-api 管理 API 禁用（下线）→ 写 channel_events → notify 通知
- 冷却到期 → 先 GET 渠道当前状态（人工禁用跳过不覆盖）→ 重新启用 → 写事件
- 渠道级配置走 Redis hash newapi:channel:cfg:{id}，无配置用全局默认
  （NEWAPI.DEFAULT_WINDOW_QUOTA / DEFAULT_WINDOW_HOURS / DEFAULT_COOLDOWN_SECONDS）
- 运行状态存 Redis newapi:scheduler:state:{channel_id}
  （disabled_at / cooldown_until / last_usage，原子写，进程崩溃不丢失）

对蓝本脚本 channel-scheduler.py 四处缺陷的规避：
① DSN 直取配置 NEWAPI.DB_DSN（DSN 即真相，不做 127.0.0.1 本机误连假设）
② logs.created_at 列类型启动探测（unix BIGINT / datetime 双兼容），杜绝字符串比较
③ 状态存 Redis 原子键值，不再落本地 JSON 文件
④ 单渠道处理 try/except 隔离，逐渠道继续，不中断整轮

依赖 new-api v0.10.x logs 表结构（channel_id / quota / created_at），见 _fetch_usage。
"""
import asyncio
import json
import time
from datetime import datetime, timedelta

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.repositories.newapi_repository import ChannelEventRepository
from backend.services.newapi_api import (
    CHANNEL_STATUS_AUTO_DISABLED,
    CHANNEL_STATUS_ENABLED,
    CHANNEL_STATUS_MANUALLY_DISABLED,
    NEWAPI_CHANNEL_CFG_PREFIX,
    NEWAPI_CHANNEL_STATE_PREFIX,
    NEWAPI_SCHEDULER_LOCK_KEY,
    NewapiApiClient,
    _main_async_session,
)
from backend.services.notify_service import NotifyService
from config import settings
from platform_core.logger import get_logger
from platform_core.queues import distributed_lock

logger = get_logger("api")

# 窗口用量聚合 SQL（依赖 new-api v0.10.x logs 表结构：channel_id/quota/created_at）。
# 别名用 total_quota 规避 MySQL 保留字 USAGE。
# unix 模式：created_at 为 BIGINT unix 秒，绑定整型窗口起点
_USAGE_SQL = (
    "SELECT channel_id, COALESCE(SUM(quota), 0) AS total_quota "
    "FROM logs WHERE created_at >= :since GROUP BY channel_id"
)
# datetime 模式：created_at 为原生 DATETIME，窗口起点下推 DB 侧
# NOW() - INTERVAL :hours HOUR（评审 m-3）：消除应用服务器本地时区与
# DB 服务器时区不一致导致的窗口偏差（不再在应用侧拼 datetime 参数）
_USAGE_SQL_DATETIME = (
    "SELECT channel_id, COALESCE(SUM(quota), 0) AS total_quota "
    "FROM logs WHERE created_at >= NOW() - INTERVAL :hours HOUR GROUP BY channel_id"
)

# logs.created_at 列类型探测（information_schema；unix BIGINT 与 datetime 二者都可能出现）
_SCHEMA_PROBE_SQL = (
    "SELECT DATA_TYPE FROM information_schema.COLUMNS "
    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'logs' AND COLUMN_NAME = 'created_at'"
)
_DATETIME_TYPES = ("datetime", "timestamp", "date")

# 「参数类型不匹配」错误特征（评审 m-2：仅此类错误才翻转 created_at 模式）
_TYPE_MISMATCH_MARKERS = (
    "type",        # sqlalchemy 绑定类型不匹配 / MySQL type 相关报错
    "illegal",     # MySQL: Illegal mix of collations 等
    "incorrect",   # MySQL: Truncated incorrect DOUBLE/INTEGER value
    "mismatch",    # 通用类型不匹配关键词
)


def _is_type_mismatch_error(e: Exception) -> bool:
    """错误是否为「参数类型不匹配」特征（created_at 模式翻转的触发条件）"""
    from sqlalchemy.exc import DataError

    if isinstance(e, DataError):
        return True
    msg = str(e).lower()
    return any(marker in msg for marker in _TYPE_MISMATCH_MARKERS)


def _build_usage_window(
    created_at_mode: str, window_hours: int, now: datetime | None = None
) -> tuple[str, dict]:
    """窗口用量聚合 SQL + 绑定参数（unix/datetime 双分支，蓝本缺陷②规避）

    - unix 模式：created_at 为 BIGINT unix 秒（new-api gorm 默认），绑定整型窗口起点
    - datetime 模式：窗口起点下推 DB 侧 NOW() - INTERVAL :hours HOUR（评审 m-3），
      绑定整型小时数，不依赖应用服务器本地时区
    """
    if created_at_mode == "datetime":
        return _USAGE_SQL_DATETIME, {"hours": int(window_hours)}
    moment = now or datetime.now()
    since_dt = moment - timedelta(hours=window_hours)
    return _USAGE_SQL, {"since": int(since_dt.timestamp())}


class ChannelSchedulerService:
    """new-api 渠道调度器：用量上限 → 下线 → 冷却 → 自动上线"""

    def __init__(self):
        self._running = False
        self._loop_task: asyncio.Task | None = None
        self._redis: aioredis.Redis | None = None
        self._engine = None
        self._sessionmaker = None
        self._api: NewapiApiClient | None = None
        # logs.created_at 比较模式："unix" | "datetime"，启动探测后缓存
        self._created_at_mode: str | None = None

    # ── 生命周期 ──────────────────────────────────────────────
    async def start(self) -> None:
        """启动调度循环（幂等；NEWAPI.ENABLED / SCHEDULER_ENABLED 分层开关，关闭时 log 一行）"""
        if self._running:
            return
        if not settings.get("NEWAPI.ENABLED", False):
            logger.info("new-api 集成总开关关闭（NEWAPI.ENABLED=false），渠道调度器不启动")
            return
        if not settings.get("NEWAPI.SCHEDULER_ENABLED", False):
            logger.info("渠道调度器已禁用（NEWAPI.SCHEDULER_ENABLED=false），不启动")
            return
        dsn = str(settings.get("NEWAPI.DB_DSN", "") or "")
        if not dsn:
            logger.warning(
                "渠道调度器未启动：NEWAPI.DB_DSN 未配置"
                "（.env 经 AUTO_AGENTS_NEWAPI__DB_DSN 注入）"
            )
            return
        self._redis = aioredis.from_url(settings.REDIS.DEFAULT.URL, decode_responses=True)
        # 独立 engine：直连 new-api 库（蓝本缺陷①规避：DSN 即真相），
        # 完全独立于主库 engine manager（platform_core.db），两侧连接互不共享
        self._engine = create_async_engine(dsn, pool_pre_ping=True, pool_recycle=1800)
        self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)
        self._api = NewapiApiClient()
        self._running = True
        self._loop_task = asyncio.create_task(
            self._tick_loop(), name="newapi-channel-scheduler"
        )
        interval = int(settings.get("NEWAPI.INTERVAL_SECONDS", 300) or 300)
        logger.info(f"渠道调度器已启动: interval={interval}s")

    async def stop(self) -> None:
        """优雅停止（取消循环 + 释放 new-api 库 engine + 关闭 Redis）"""
        self._running = False
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 退出路径兜底
                pass
            self._loop_task = None
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._sessionmaker = None
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        logger.info("渠道调度器已停止")

    async def _tick_loop(self) -> None:
        interval = int(settings.get("NEWAPI.INTERVAL_SECONDS", 300) or 300)
        while self._running:
            try:
                await self._tick_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 单轮失败不中断循环
                logger.error(f"渠道调度轮次失败: {e}")
            await asyncio.sleep(interval)

    # ── 单轮巡检 ──────────────────────────────────────────────
    async def _tick_once(self) -> None:
        """单轮：抢锁 → 拉渠道 → 解析受管渠道 → 聚合用量 → 逐渠道处理（隔离）

        锁走 platform_core.queues.distributed_lock 共享设施（唯一 token +
        finally 原子释放，早退/异常路径同样释放，评审 m-1）；
        TTL 仅作进程崩溃兑底，正常运行靠主动释放。
        """
        lock_ttl = int(settings.get("NEWAPI.LOCK_TTL_SECONDS", 120) or 120)
        async with distributed_lock(
            self._redis, NEWAPI_SCHEDULER_LOCK_KEY, ttl=lock_ttl
        ) as lock:
            if lock is None:
                return  # 其他实例已在执行本轮
            channels = await self._api.list_channels()
            if not channels:
                logger.debug("new-api 渠道列表为空，本轮跳过")
                return

            global_limit = int(settings.get("NEWAPI.DEFAULT_WINDOW_QUOTA", 0) or 0)
            managed: dict[int, tuple[dict, dict]] = {}
            for ch in channels:
                try:
                    cid = int(ch.get("id") or 0)
                except (TypeError, ValueError):
                    continue
                if cid <= 0:
                    continue
                cfg = await self._channel_cfg(cid)
                if cfg is None and global_limit > 0:
                    cfg = {
                        "limit_quota": global_limit,
                        "window_hours": int(settings.get("NEWAPI.DEFAULT_WINDOW_HOURS", 24) or 24),
                        "cooldown_seconds": int(
                            settings.get("NEWAPI.DEFAULT_COOLDOWN_SECONDS", 3600) or 3600
                        ),
                    }
                if cfg:
                    managed[cid] = (ch, cfg)
            if not managed:
                # 4.2：空转显式告警（原来是 debug 级静默跳过——三层开关全开也无人知晓受管数为 0）
                logger.warning(
                    "渠道调度器受管渠道数为 0（无渠道级配置且 DEFAULT_WINDOW_QUOTA=0），"
                    "本轮空转。请在「中转站 → 渠道配置」设置渠道额度，"
                    "或调高 NEWAPI.DEFAULT_WINDOW_QUOTA"
                )
                return
            logger.info(f"渠道调度本轮受管渠道数: {len(managed)}")

            # 按窗口小时分组聚合用量（同窗口共享一条 SQL 结果）。
            # 聚合失败降级为空用量（评审 m-2：异常抛给上层，按窗口隔离降级，
            # 渠道处理循环继续——该窗口渠道本轮不触发禁用，错误不静默）
            usage_by_window: dict[int, dict[int, int]] = {}
            for _cid, (_ch, cfg) in managed.items():
                wh = int(cfg.get("window_hours") or 24)
                if wh in usage_by_window:
                    continue
                try:
                    usage_by_window[wh] = await self._fetch_usage(wh)
                except Exception as e:  # noqa: BLE001 聚合失败不中断整轮
                    logger.error(
                        f"窗口用量聚合失败（本窗口降级为空用量）: window_hours={wh}, error={e}"
                    )
                    usage_by_window[wh] = {}

            for cid, (ch, cfg) in managed.items():
                try:
                    usage = usage_by_window[int(cfg["window_hours"])].get(cid, 0)
                    await self._process_channel(ch, cfg, usage)
                except Exception as e:  # noqa: BLE001 单渠道隔离（蓝本缺陷④规避）
                    logger.error(f"渠道调度处理失败（已隔离）: channel_id={cid}, error={e}")

    async def _process_channel(self, channel: dict, cfg: dict, usage: int) -> None:
        """单渠道状态机：启用超限→禁用；自动禁用冷却到期→恢复；人工禁用→不覆盖"""
        cid = int(channel["id"])
        status = int(channel.get("status") or 0)
        state = await self._load_state(cid)
        state_key = self._state_key(cid)

        if state and status == CHANNEL_STATUS_ENABLED:
            # 冷却期内被人工重新启用 → 解除调度跟踪（不覆盖人工操作）
            logger.info(f"渠道 {cid} 冷却期内已被人工启用，解除调度跟踪")
            await self._redis.delete(state_key)
            state = None

        if status == CHANNEL_STATUS_ENABLED:
            if usage >= int(cfg["limit_quota"]):
                await self._disable_channel(channel, cfg, usage)
            return

        if status == CHANNEL_STATUS_AUTO_DISABLED and state:
            cooldown_until = int(state.get("cooldown_until") or 0)
            if time.time() >= cooldown_until:
                await self._recover_channel(channel)
            else:
                logger.info(f"渠道 {cid} 冷却中，剩余 {int(cooldown_until - time.time())}s")
            return

        if status == CHANNEL_STATUS_AUTO_DISABLED:
            # 评审 m-4：状态丢失（Redis TTL 过期/误清/重启清库）时不再静默跳过——
            # 按默认 cooldown 重建状态，保证冷却语义闭环（到期后可自动恢复），
            # 并落事件留痕（source=scheduler, reason="state rebuilt"）
            await self._rebuild_state(channel, cfg)
            return

        if status == CHANNEL_STATUS_MANUALLY_DISABLED and state:
            # 人工禁用（冷却期内被人工接管）→ 解除跟踪，不自动恢复
            logger.warning(f"渠道 {cid} 已被人工禁用，跳过调度恢复并解除跟踪（不覆盖人工操作）")
            await self._redis.delete(state_key)

    # ── 禁用 / 恢复 ───────────────────────────────────────────
    async def _disable_channel(self, channel: dict, cfg: dict, usage: int) -> None:
        """超限禁用：管理 API 置 auto_disabled(3) → 存状态 → 落事件 → 通知

        PUT 前先 GET 复核当前状态（评审 m-8）：渠道已被人工禁用(status=2)则
        跳过并落事件留痕，缩小「列表快照过期 → 覆盖人工操作」的 TOCTOU 窗口。
        残余风险：GET 与 PUT 之间仍存在极小竞态（new-api 管理面无带状态
        前置条件的原子 CAS 接口），完全消除需上游支持；GET 失败按列表快照
        继续执行（可用性优先）。
        """
        cid = int(channel["id"])
        current = await self._api.get_channel(cid)
        if current is not None and int(current.get("status") or 0) == CHANNEL_STATUS_MANUALLY_DISABLED:
            logger.warning(
                f"渠道 {cid} 禁用前复核发现已被人工禁用，跳过自动下线（不覆盖人工操作）"
            )
            await self._record_event(
                channel_id=cid, action="disable_skipped", source="scheduler",
                usage=usage, reason="禁用前复核发现人工禁用，自动下线跳过",
            )
            return
        ok = await self._api.set_channel_status(cid, CHANNEL_STATUS_AUTO_DISABLED)
        if not ok:
            logger.error(f"渠道 {cid} 禁用调用失败，本轮跳过（下轮重试）")
            return
        now = int(time.time())
        state = {
            "disabled_at": datetime.now().isoformat(timespec="seconds"),
            "cooldown_until": now + int(cfg["cooldown_seconds"]),
            "last_usage": usage,
        }
        # Redis 原子写（蓝本缺陷③规避：不再落本地 JSON 文件）
        await self._redis.set(self._state_key(cid), json.dumps(state, ensure_ascii=False))
        reason = (
            f"近 {cfg['window_hours']}h 用量 {usage} 达上限 {cfg['limit_quota']}，"
            f"冷却 {cfg['cooldown_seconds']}s 后自动恢复"
        )
        await self._record_event(
            channel_id=cid, action="disabled", usage=usage,
            limit_quota=cfg["limit_quota"], window_hours=cfg["window_hours"],
            reason=reason, source="scheduler",
        )
        logger.warning(f"渠道超限下线: channel_id={cid}, name={channel.get('name')}, {reason}")
        await NotifyService().notify_text(
            "channel.disabled",
            f"⛔ 渠道 #{cid}（{channel.get('name', '')}）超限下线：{reason}",
        )

    async def _rebuild_state(self, channel: dict, cfg: dict) -> None:
        """自动禁用渠道的状态重建（评审 m-4）：Redis 无状态时按默认 cooldown 补建

        disabled_at 以本轮时间近似（真实禁用时刻不可考），实际冷却时长
        可能短于原定值——相当于从发现时刻重新计冷却，语义保守不提前恢复。
        """
        cid = int(channel["id"])
        now = int(time.time())
        state = {
            "disabled_at": datetime.now().isoformat(timespec="seconds"),
            "cooldown_until": now + int(cfg["cooldown_seconds"]),
            "last_usage": 0,
        }
        await self._redis.set(self._state_key(cid), json.dumps(state, ensure_ascii=False))
        await self._record_event(
            channel_id=cid, action="state_rebuilt", source="scheduler",
            reason="state rebuilt",
        )
        logger.warning(
            f"渠道 {cid} 自动禁用但状态丢失，已按默认冷却重建: "
            f"cooldown_seconds={cfg['cooldown_seconds']}"
        )

    async def _recover_channel(self, channel: dict) -> None:
        """冷却恢复：先 GET 当前状态，人工禁用跳过并记录，否则启用 + 写事件 + 通知"""
        cid = int(channel["id"])
        current = await self._api.get_channel(cid)
        if current is None:
            logger.warning(f"渠道 {cid} 冷却到期但获取当前状态失败，本轮跳过恢复")
            return
        cur_status = int(current.get("status") or 0)
        if cur_status == CHANNEL_STATUS_MANUALLY_DISABLED:
            logger.warning(
                f"渠道 {cid} 冷却到期但已被人工禁用，跳过恢复并解除跟踪（不覆盖人工操作）"
            )
            await self._redis.delete(self._state_key(cid))
            return
        if cur_status == CHANNEL_STATUS_ENABLED:
            logger.info(f"渠道 {cid} 已处于启用状态（可能被人工启用），解除调度跟踪")
            await self._redis.delete(self._state_key(cid))
            return
        ok = await self._api.set_channel_status(cid, CHANNEL_STATUS_ENABLED)
        if not ok:
            return
        await self._redis.delete(self._state_key(cid))
        await self._record_event(
            channel_id=cid, action="enabled", source="scheduler", reason="冷却到期自动恢复上线"
        )
        logger.info(f"渠道冷却恢复上线: channel_id={cid}, name={current.get('name')}")
        await NotifyService().notify_text(
            "channel.enabled",
            f"✅ 渠道 #{cid}（{current.get('name', '')}）冷却结束，已自动恢复上线",
        )

    # ── 用量聚合（直连 new-api 库） ───────────────────────────
    async def _fetch_usage(self, window_hours: int) -> dict[int, int]:
        """窗口内各渠道用量聚合 {channel_id: total_quota}

        依赖 new-api v0.10.x logs 表结构（channel_id/quota/created_at）。
        created_at 兼容判断：优先 information_schema 探测列类型；查询报错且
        错误特征匹配「参数类型不匹配」时才翻转 unix/datetime 模式重试一次
        并缓存新模式（评审 m-2：其余异常不翻转不缓存——把模式误判与
        连接/服务类故障区分开，异常直接抛给上层按窗口隔离降级，
        避免把网络闪断误缓存成错误模式）。
        """
        mode = await self._ensure_created_at_mode()
        sql, params = _build_usage_window(mode, window_hours)
        try:
            return await self._execute_usage(sql, params)
        except Exception as e:  # noqa: BLE001
            if not _is_type_mismatch_error(e):
                raise
            flipped = "datetime" if mode == "unix" else "unix"
            logger.warning(
                f"窗口用量查询参数类型不匹配，切换 created_at 模式 {mode} → {flipped} 重试: {e}"
            )
            sql, params = _build_usage_window(flipped, window_hours)
            try:
                rows = await self._execute_usage(sql, params)
            except Exception as retry_err:  # noqa: BLE001 翻转后仍失败
                # 新模式同样报错说明探测/翻转均不可信，清缓存下次重新探测
                self._created_at_mode = None
                raise retry_err
            self._created_at_mode = flipped
            logger.info(f"created_at 模式已缓存为 {flipped}")
            return rows

    async def _execute_usage(self, sql: str, params: dict) -> dict[int, int]:
        """执行聚合 SQL 并格式化结果 {channel_id: total_quota}（供翻转重试复用）"""
        async with self._sessionmaker() as session:
            result = await session.execute(text(sql), params)
            rows = result.all()
        return {int(r[0]): int(r[1] or 0) for r in rows}

    async def _ensure_created_at_mode(self) -> str:
        """启动探测 logs.created_at 列类型并缓存（unix BIGINT / datetime 二者都可能出现）"""
        if self._created_at_mode:
            return self._created_at_mode
        try:
            async with self._sessionmaker() as session:
                row = (await session.execute(text(_SCHEMA_PROBE_SQL))).first()
            dtype = str(row[0]).lower() if row and row[0] else ""
            self._created_at_mode = "datetime" if dtype in _DATETIME_TYPES else "unix"
        except Exception as e:  # noqa: BLE001
            logger.warning(f"logs.created_at 列类型探测失败，回退 unix 模式: {e}")
            self._created_at_mode = "unix"
        logger.info(f"new-api logs.created_at 比较模式: {self._created_at_mode}")
        return self._created_at_mode

    # ── 渠道配置 / 状态（Redis） ──────────────────────────────
    async def _channel_cfg(self, channel_id: int) -> dict | None:
        """渠道级配置（Redis hash：limit_quota/window_hours/cooldown_seconds）

        limit_quota<=0 视为显式关闭该渠道调度；无配置返回 None（走全局默认）。
        """
        try:
            raw = await self._redis.hgetall(f"{NEWAPI_CHANNEL_CFG_PREFIX}{channel_id}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"读取渠道配置失败: channel_id={channel_id}, error={e}")
            return None
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

    async def _load_state(self, channel_id: int) -> dict | None:
        """读取调度状态（disabled_at/cooldown_until/last_usage）"""
        try:
            raw = await self._redis.get(self._state_key(channel_id))
            return json.loads(raw) if raw else None
        except Exception as e:  # noqa: BLE001
            logger.warning(f"读取调度状态失败: channel_id={channel_id}, error={e}")
            return None

    @staticmethod
    def _state_key(channel_id: int) -> str:
        return f"{NEWAPI_CHANNEL_STATE_PREFIX}{channel_id}"

    # ── 事件落库（主库） ──────────────────────────────────────
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
        """channel_events 落库（主库独立提交；失败仅告警，不影响渠道动作）"""
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
