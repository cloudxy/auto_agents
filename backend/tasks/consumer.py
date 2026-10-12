"""Redis 任务/结果双队列消费者 - 数据闭环的 Backend 侧引擎

运行模型（随 FastAPI lifespan 启动，见 backend/app/__init__.py）：
- _dispatch_loop：blpop spider:task_queue → 任务置 running → 写活跃任务关联 →
  把 start URL 投递到 `<spider_name>:start_urls`（scrapy-redis 消费）
- _ingest_loop：lpop 批量拉取 spider:item_queue → 批量 accumulate + 定期 flush →
  bulk insert + result_count 批量累加（单次 commit）
- _retry_loop：扫 spider:retry_zset 到期成员（score=到期时间戳）→
  zrem 原子抢占 → 重新投递主优先级队列（失败重试退避 1s→5s→15s）

失败策略：
- 单条消息处理失败只记日志，不中断循环（队列消费不丢循环）
- 任务消息缺 urls 时直接把任务置 failed（错误信息可追溯到任务行）

模块组成（按职责拆分，SpiderTaskConsumer 以 mixin 组合，实例方法名不变）：
- 本模块：生命周期（start/stop）、start URL 载荷构建、任务分发、_fail_task
- consumer_recovery.py：失败重试 ZSET 扫描 + running 超时回收 + 积压 pending 对账
- consumer_ingest.py：结果回流循环 + 毒消息隔离（REDO / 死信）
- consumer_store.py：批量 / 单条落库、多存储双写、无主拒收
"""
import asyncio
import json
import os
from typing import List, Optional

import redis.asyncio as aioredis
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from backend.config_consts import (TASKS_STALE_TASK_HOURS)
from platform_core.db import get_manager
from platform_core.logger import get_logger
from platform_core.queues import (
    ACTIVE_TASK_KEY,
    ACTIVE_TASK_TTL,
    ITEM_QUEUE,
    LEGACY_ACTIVE_TASK_PREFIX,
    TASK_CONTROL_KEY,
    TASK_LOG_OFFSET_KEY,
    TASK_LOG_OFFSET_TTL,
    TASK_QUEUE_PRIORITIES,
    task_queue,
    tenant_active_key,
)
from backend.repositories.spider_task_repository import SpiderTaskRepository
from backend.services.spider_service import (
    FLOW_SPIDER_NAME,
    extract_flow,
    resolve_spider_log_path,
)
from backend.services.spider_task_service import RETRY_ZSET_KEY
from backend.tasks.consumer_ingest import ResultIngestMixin
from backend.tasks.consumer_recovery import TaskRecoveryMixin

logger = get_logger("api")

# blpop 超时（秒）：超时后回到循环顶部检查运行开关，保证可优雅退出
_BLPOP_TIMEOUT = 5


def extract_start_urls(params: Optional[str]) -> List[str]:
    """从任务 params（JSON 字符串）中提取 start URL 列表

    约定：params 形如 {"urls": ["https://..."]}；缺 urls / 解析失败返回空列表。
    """
    if not params:
        return []
    try:
        data = json.loads(params)
    except (TypeError, ValueError):
        logger.warning(f"任务 params 不是合法 JSON: {params!r}")
        return []
    if isinstance(data, dict):
        urls = data.get("urls")
        if isinstance(urls, list):
            return [str(u) for u in urls if u]
    if isinstance(data, list):
        return [str(u) for u in data if u]
    return []


def extract_selectors(params: Optional[str]) -> List[dict]:
    """从任务 params 中提取选择器规则（自定义采集类型专属，普通类型为空）

    约定：params 形如 {"urls": [...], "selectors": [{"name":..., "type":..., "expr":...}]}。
    """
    if not params:
        return []
    try:
        data = json.loads(params)
    except (TypeError, ValueError):
        return []
    if isinstance(data, dict):
        selectors = data.get("selectors")
        if isinstance(selectors, list):
            return [s for s in selectors if isinstance(s, dict)]
    return []


def extract_render_params(params: Optional[str]) -> dict:
    """M4：flow 任务专属，从任务 params 提取 JS 渲染参数（仅白名单键 + 严格类型）

    flow_generic 在 make_request_from_data 从 start_urls 载荷的 params 字段读取
    render_js/wait_for/wait_timeout；其余 params 键不透传（防意外注入）。"""
    if not params:
        return {}
    try:
        data = json.loads(params)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    render: dict = {}
    if isinstance(data.get("render_js"), bool):
        render["render_js"] = data["render_js"]
    wait_for = data.get("wait_for")
    if isinstance(wait_for, str) and wait_for:
        render["wait_for"] = wait_for
    wait_timeout = data.get("wait_timeout")
    if isinstance(wait_timeout, (int, float)) and not isinstance(wait_timeout, bool):
        render["wait_timeout"] = int(wait_timeout)
    return render


def build_start_payload(
    url: str,
    task_id,
    flow: Optional[dict],
    selectors: List[dict],
    render_params: Optional[dict] = None,
) -> str:
    """start URL 载荷构建：{"url", "task_id", flow|selectors, params?}

    flow 任务且存在渲染参数时携带 params（对齐 flow_generic 的读取约定）；
    非 flow 任务载荷结构保持 {"url","task_id","selectors"} 零变化。"""
    payload_extra = {"flow": flow} if flow is not None else (
        {"selectors": selectors} if selectors else {}
    )
    if flow is not None and render_params:
        payload_extra["params"] = render_params
    return json.dumps({"url": url, "task_id": task_id, **payload_extra}, ensure_ascii=False)


class SpiderTaskConsumer(TaskRecoveryMixin, ResultIngestMixin):
    """Redis 双队列消费者（任务分发 + 结果回流）"""

    def __init__(self):
        self._running = False
        self._loops: List[asyncio.Task] = []
        self._redis: Optional[aioredis.Redis] = None
        self._requeued_counts: dict[int, int] = {}

    async def start(self) -> None:
        """启动两个消费循环（幂等：重复调用不叠加）"""
        if self._running:
            return
        # B3：归一异步 Redis 门面（共享连接池，键契约见 platform_core.queues）
        from platform_core.redis_async import get_async_redis

        self._redis = get_async_redis()
        await self._purge_legacy_active_keys()
        self._running = True
        self._loops = [
            asyncio.create_task(self._dispatch_loop(), name="spider-task-dispatch"),
            asyncio.create_task(self._ingest_loop(), name="spider-item-ingest"),
            asyncio.create_task(self._retry_loop(), name="spider-retry-scan"),
        ]
        # P0-1b：running 任务超时回收循环（STALE_TASK_HOURS=0 时关闭）
        stale_hours = float(settings.get("TASKS.STALE_TASK_HOURS", TASKS_STALE_TASK_HOURS) or 0)
        if stale_hours > 0:
            self._loops.append(
                asyncio.create_task(self._recover_loop(), name="spider-stale-recover")
            )
        logger.info(
            f"队列消费者已启动: tasks={[task_queue(p) for p in TASK_QUEUE_PRIORITIES]}, "
            f"items={ITEM_QUEUE}, retry_zset={RETRY_ZSET_KEY}, "
            f"stale_recover={'on(%.0fh)' % stale_hours if stale_hours > 0 else 'off'}"
        )

    async def _purge_legacy_active_keys(self) -> None:
        """一次性清理阶段 4.1 之前的旧活跃键（string 语义，前缀不带 s）

        新语义用 SET（spider:active_tasks:*）；旧键残留会让旧版前端/脚本误读，
        且与 SET 键并存时易混淆，启动时统一删除（容忍 Redis 异常）。
        """
        try:
            stale = [k async for k in self._redis.scan_iter(match=f"{LEGACY_ACTIVE_TASK_PREFIX}*")]
            if stale:
                await self._redis.delete(*stale)
                logger.info(f"已清理旧版活跃键: {len(stale)} 个")
        except Exception as e:  # noqa: BLE001 清理失败不阻断启动（旧键有 TTL 自然过期）
            logger.warning(f"清理旧版活跃键失败: {e}")

    async def stop(self) -> None:
        """优雅停止：取消循环并关闭 Redis 连接"""
        self._running = False
        for task in self._loops:
            task.cancel()
        for task in self._loops:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 退出路径兜底
                pass
        self._loops = []
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        logger.info("队列消费者已停止")

    # ------------------------------------------------------------------
    # 任务分发：pending → running → 投递 start URL
    # ------------------------------------------------------------------
    async def _dispatch_loop(self) -> None:
        # 优先级多队列：blpop 多键按列表顺序检查，天然实现 high > normal > low
        queues = [task_queue(p) for p in TASK_QUEUE_PRIORITIES]
        while self._running:
            try:
                message = await self._redis.blpop(queues, timeout=_BLPOP_TIMEOUT)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 连接抖动等：退避重试
                logger.error(f"任务队列 blpop 失败: {e}")
                await asyncio.sleep(2)
                continue
            if not message:
                continue
            try:
                await self._dispatch(json.loads(message[1]))
            except Exception as e:  # noqa: BLE001 单条消息失败不中断循环
                logger.error(f"任务分发失败: raw={message[1]!r}, error={e}")

    async def _dispatch(self, msg: dict) -> None:
        """单条任务消息分发：控制键 → 流程切换 → 校验 urls → CAS 置 running → 投递"""
        task_id = msg.get("task_id")
        spider_name = msg.get("spider_name", "")
        logger.info(f"消费任务消息: task_id={task_id}, spider={spider_name}")
        msg = await self._with_db_params(msg)

        # A4：分发前检查控制键，如果已有 stop 控制键则直接置 failed（用户已终止）
        if await self._stopped_before_dispatch(task_id):
            return

        # 阶段 5.1：识别流程参数 → 统一切到 flow_generic 爬虫执行；
        # 任务行同步改写，保证活跃键/并发槽位/关闭回调与实际执行爬虫一致。
        flow = extract_flow(msg.get("params"))
        if flow is not None and spider_name != FLOW_SPIDER_NAME:
            spider_name = FLOW_SPIDER_NAME
            await self._switch_to_flow_spider(task_id)

        urls = extract_start_urls(msg.get("params"))
        if not urls:
            await self._fail_task(task_id, "params 缺少 urls，无法分发采集目标")
            return

        # 1. 任务置 running（同时写 started_at，供运行时长统计）
        if not await self._mark_running(task_id):
            return

        # 2. 写活跃任务关联（供并发槽位控制 / 终态回调）+ 3. 投递 start URL
        if not await self._deliver(msg, task_id, spider_name, flow, urls):
            return

        logger.info(
            f"任务已分发: task_id={task_id}, spider={spider_name}, urls={len(urls)}"
        )

    async def _stopped_before_dispatch(self, task_id) -> bool:
        """A4：已有 stop 控制键 → 任务置 failed 并清控制键，返回 True（本消息不再分发）

        控制键读取 / 清理异常时放行（返回 False，照常分发）。
        """
        try:
            control_val = await self._redis.get(TASK_CONTROL_KEY.format(task_id=task_id))
            if control_val and str(control_val).strip().lower() == "stop":
                await self._fail_task(task_id, "user_stopped")
                await self._redis.delete(TASK_CONTROL_KEY.format(task_id=task_id))
                logger.info(f"任务分发前已终止（用户控制）: task_id={task_id}")
                return True
        except Exception as e:  # noqa: BLE001
            logger.warning(f"分发前检查控制键失败（放行）: task_id={task_id}, error={e}")
        return False

    async def _switch_to_flow_spider(self, task_id) -> None:
        """流程采集任务：任务行执行爬虫改写为 flow_generic（阶段 5.1）"""
        async with AsyncSession(self._engine()) as session:
            await SpiderTaskRepository(session).update(task_id, spider_name=FLOW_SPIDER_NAME)
            await session.commit()
        logger.info(f"流程采集任务切换执行爬虫: task_id={task_id} → {FLOW_SPIDER_NAME}")

    async def _mark_running(self, task_id) -> bool:
        """任务 pending → running（CAS）；任务不存在或已不在待执行状态返回 False

        审计 BUG-12：只从 pending 迁移（CAS）。重复 / 迟到的分发消息原先无条件 UPDATE，
        把已完成 / 已失败的任务翻回 running，并再抓一遍。
        """
        async with AsyncSession(self._engine()) as session:
            repo = SpiderTaskRepository(session)
            task = await repo.update(
                task_id, only_if_status=("pending",), status="running", started_at=func.now(),
            )
            await session.commit()
            if task is None:
                logger.warning(f"任务不存在或已不在待执行状态（重复 / 迟到消息），丢弃: task_id={task_id}")
                return False
        return True

    async def _deliver(self, msg: dict, task_id, spider_name: str, flow, urls: List[str]) -> bool:
        """写活跃任务关联 + 投递 start URL；成功返回 True

        任一步失败都会导致任务卡死 running（blpop 后消息已丢），用 _fail_task 兜底推终态。
        先校验任务仍存在再写活跃键：若任务在排队期间被删除，
        旧投递会让活跃集合残留幽灵成员，后续任务的并发槽位会被错误占用。
        """
        try:
            async with AsyncSession(self._engine()) as session:
                check_repo = SpiderTaskRepository(session)
                still_exists = await check_repo.get_by_id(task_id)
            if still_exists is None:
                logger.warning(f"任务已不存在（可能已被删除），丢弃分发: task_id={task_id}")
                return False
            await self._register_active(task_id, spider_name, msg.get("tenant_id"))
            # 记录当前日志文件偏移量：供日志隔离切出本任务区间（各并发任务各自记录）
            await self._record_log_offset(task_id)
            await self._push_start_urls(msg, task_id, spider_name, flow, urls)
        except Exception as e:  # noqa: BLE001
            logger.error(f"投递采集任务失败: task_id={task_id}, spider={spider_name}, error={e}")
            await self._fail_task(task_id, f"投递 start URL 失败: {e}")
            return False
        return True

    async def _register_active(self, task_id, spider_name: str, raw_tid) -> None:
        """写活跃任务集合（爬虫级 + 租户级）并续 TTL：供并发槽位控制 / 终态回调"""
        active_key = ACTIVE_TASK_KEY.format(spider_name=spider_name)
        await self._redis.sadd(active_key, task_id)
        await self._redis.expire(active_key, ACTIVE_TASK_TTL)
        if isinstance(raw_tid, int):
            tkey = tenant_active_key(raw_tid, spider_name)
            await self._redis.sadd(tkey, task_id)
            await self._redis.expire(tkey, ACTIVE_TASK_TTL)

    async def _push_start_urls(
        self, msg: dict, task_id, spider_name: str, flow, urls: List[str],
    ) -> None:
        """投递 start URL（scrapy-redis 约定键 `<spider_name>:start_urls`）

        载荷统一包装为 JSON 并携带 task_id：并发下结果归属走请求 meta（精确），
        TaskAwareRedisSpider / generic 解析 JSON；scrapy-redis 对 start_urls 天然 dont_filter。
        M4：flow 任务透传 AI 规划的 JS 渲染配置（flow_generic 从载荷 params 读取），
        其余 params 键不透传防意外注入；非 flow 任务载荷结构零变化。
        """
        selectors = extract_selectors(msg.get("params"))
        render_params = extract_render_params(msg.get("params")) if flow is not None else {}
        payloads = [
            build_start_payload(u, task_id, flow, selectors, render_params)
            for u in urls
        ]
        for payload in payloads:
            await self._redis.rpush(f"{spider_name}:start_urls", payload)

    async def _with_db_params(self, msg: dict) -> dict:
        """分发以数据库行为准（审计 BUG-13）：待执行任务被编辑后，队列里的旧消息仍带旧 params；
        按 task_id 取库内最新 params 覆盖消息快照。读库失败沿用消息内容（不阻断分发）"""
        task_id = msg.get("task_id")
        if not task_id:
            return msg
        try:
            async with AsyncSession(self._engine()) as session:
                task = await SpiderTaskRepository(session).get_by_id(task_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"分发读取任务参数失败，沿用消息快照: task_id={task_id}, error={e}")
            return msg
        if task is None:
            return msg
        merged = dict(msg)
        db_params = getattr(task, "params", None)
        if isinstance(db_params, str) and db_params != msg.get("params"):
            logger.info(f"分发参数以库内为准（任务已编辑）: task_id={task_id}")
            merged["params"] = db_params
        return merged

    async def _record_log_offset(self, task_id) -> None:
        """记录分发时刻的爬虫日志文件大小（失败仅记日志，不阻断分发）"""
        try:
            log_path = resolve_spider_log_path()
            offset = os.path.getsize(log_path) if log_path and os.path.isfile(log_path) else 0
            await self._redis.set(
                TASK_LOG_OFFSET_KEY.format(task_id=task_id), offset, ex=TASK_LOG_OFFSET_TTL
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"记录任务日志偏移量失败: task_id={task_id}, error={e}")

    async def _fail_task(self, task_id, error_message: str) -> None:
        """把任务直接置 failed（消息无法正常处理时）"""
        try:
            async with AsyncSession(self._engine()) as session:
                repo = SpiderTaskRepository(session)
                await repo.update(task_id, status="failed", error_message=error_message)
                await session.commit()
            logger.warning(f"任务置 failed: task_id={task_id}, reason={error_message}")
        except Exception as e:  # noqa: BLE001
            logger.error(f"任务置 failed 失败: task_id={task_id}, error={e}")

    @staticmethod
    def _engine():
        return get_manager().async_engines["DEFAULT"]
