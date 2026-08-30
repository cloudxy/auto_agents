"""爬虫定时调度服务 - 对标 Crawlab 定时任务（Cron）

组成：
- ScheduleService：调度计划 CRUD（创建时校验 cron 合法性 / 同爬虫唯一）
- SpiderScheduler：后台触发循环（随 Backend lifespan 启动）
  每轮 tick 抢 Redis 互斥锁（多实例防重）→ 扫描到期计划 → 复用
  SpiderService.enqueue() 入队（活跃键冲突则跳过本次触发）→ 推进
  last_run_at / next_run_at

约定：
- cron_expr 为标准 5 段表达式（分 时 日 月 周）
- 时间比较基于本地时间（MySQL DATETIME 不带时区，与 func.now() 一致）
"""
import asyncio
import json
from datetime import datetime
from typing import Optional

import redis.asyncio as aioredis
from croniter import croniter
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.spider_definition_repository import SpiderDefinitionRepository
from backend.repositories.spider_schedule_repository import SpiderScheduleRepository
from backend.repositories.spider_task_repository import SpiderTaskRepository
from backend.services.spider_service import SpiderService
from config import settings
from platform_core.db import get_manager
from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.queues import SCHEDULER_LOCK_KEY, TASK_QUEUE_PRIORITIES, task_queue
from platform_core.schemas.spider import (
    ScheduleRequest,
    ScheduleUpdateRequest,
    SpiderScheduleListResponse,
    SpiderScheduleResponse,
)

logger = get_logger("api")


def validate_cron(cron_expr: str) -> bool:
    logger.debug(f"校验 cron 表达式: {cron_expr}")
    try:
        croniter(cron_expr)
        return True
    except (KeyError, ValueError):
        return False


def next_fire_time(cron_expr: str, base: Optional[datetime] = None) -> datetime:
    logger.debug(f"计算下一次触发时刻: cron={cron_expr}, base={base}")
    return croniter(cron_expr, base or datetime.now()).get_next(datetime)


class ScheduleService:
    """调度计划 CRUD（API 层编排入口）"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = SpiderScheduleRepository(session)

    async def list_schedules(self) -> SpiderScheduleListResponse:
        """调度计划列表"""
        items = await self.repo.list_all()
        total = await self.repo.count()
        return SpiderScheduleListResponse(
            total=total,
            items=[SpiderScheduleResponse.model_validate(s) for s in items],
        )

    async def _ensure_spider_registered(self, spider_name: str) -> None:
        """爬虫注册表校验：DB 优先，无记录回退 yml 种子（与入队校验同一策略）

        - DB 有记录且停用 → 拒绝创建调度
        - DB 无记录 → yml settings.SPIDERS 兜底（存量 yml-only 爬虫不破坏）
        - DB 查询异常 → 回退 yml（DB 故障不阻断调度管理）
        """
        definition = None
        try:
            definition = await SpiderDefinitionRepository(self.session).get_by_name(spider_name)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"注册表 DB 校验失败，回退配置种子: spider={spider_name}, error={e}")
        if definition is not None:
            if not definition.enabled:
                raise BusinessException(f"爬虫 {spider_name} 已停用，无法创建调度")
            return
        spiders_cfg = settings.get("SPIDERS", {}) or {}
        if isinstance(spiders_cfg, dict) and spider_name not in spiders_cfg:
            raise BusinessException(f"爬虫 {spider_name} 未在注册表登记")

    async def create_schedule(self, payload: ScheduleRequest) -> SpiderScheduleResponse:
        """创建调度计划（校验：爬虫注册表存在 / cron 合法 / 同爬虫唯一）"""
        await self._ensure_spider_registered(payload.spider_name)
        if not validate_cron(payload.cron_expr):
            raise BusinessException(f"非法的 cron 表达式: {payload.cron_expr}")
        existing = await self.repo.find_by_spider(payload.spider_name)
        if existing is not None:
            raise BusinessException(f"爬虫 {payload.spider_name} 已存在调度计划（id={existing.id}）")

        schedule = await self.repo.create(
            spider_name=payload.spider_name,
            cron_expr=payload.cron_expr,
            params=payload.params,
            enabled=payload.enabled,
            next_run_at=next_fire_time(payload.cron_expr) if payload.enabled else None,
        )
        await self.session.commit()
        await self.session.refresh(schedule)
        logger.info(
            f"调度计划已创建: id={schedule.id}, spider={schedule.spider_name}, "
            f"cron={schedule.cron_expr}, next_run_at={schedule.next_run_at}"
        )
        return SpiderScheduleResponse.model_validate(schedule)

    async def update_schedule(
        self, schedule_id: int, payload: ScheduleUpdateRequest
    ) -> SpiderScheduleResponse:
        """局部更新：启停 / 改表达式 / 改参数（任一变更都重算触发时刻）"""
        schedule = await self.repo.get_by_id(schedule_id)
        if schedule is None:
            raise NotFoundException("调度计划")

        update_kwargs = {}
        if payload.cron_expr is not None:
            if not validate_cron(payload.cron_expr):
                raise BusinessException(f"非法的 cron 表达式: {payload.cron_expr}")
            update_kwargs["cron_expr"] = payload.cron_expr
        if payload.params is not None:
            update_kwargs["params"] = payload.params
        if payload.enabled is not None:
            update_kwargs["enabled"] = payload.enabled

        # 重算下次触发：停用清空，启用按最新表达式计算
        cron_expr = update_kwargs.get("cron_expr", schedule.cron_expr)
        enabled = update_kwargs.get("enabled", schedule.enabled)
        update_kwargs["next_run_at"] = next_fire_time(cron_expr) if enabled else None

        schedule = await self.repo.update(schedule_id, **update_kwargs)
        await self.session.commit()
        await self.session.refresh(schedule)
        logger.info(f"调度计划已更新: id={schedule_id}, fields={list(update_kwargs.keys())}")
        return SpiderScheduleResponse.model_validate(schedule)

    async def delete_schedule(self, schedule_id: int) -> dict:
        """删除调度计划"""
        schedule = await self.repo.get_by_id(schedule_id)
        if schedule is None:
            raise NotFoundException("调度计划")
        await self.repo.delete(schedule_id)
        await self.session.commit()
        logger.info(f"调度计划已删除: id={schedule_id}, spider={schedule.spider_name}")
        return {"schedule_id": schedule_id, "spider_name": schedule.spider_name}


class SpiderScheduler:
    """后台触发循环：扫描到期计划并入队任务（多实例用 Redis 锁互斥）"""

    def __init__(self):
        self._running = False
        self._loop_task: Optional[asyncio.Task] = None
        self._redis: Optional[aioredis.Redis] = None

    async def start(self) -> None:
        """启动触发循环（幂等）"""
        if self._running:
            return
        self._redis = aioredis.from_url(
            settings.REDIS.DEFAULT.URL, decode_responses=True
        )
        self._running = True
        self._loop_task = asyncio.create_task(self._tick_loop(), name="spider-scheduler")
        logger.info(
            f"定时调度器已启动: tick={settings.get('SCHEDULER.TICK_SECONDS', 30)}s"
        )

    async def stop(self) -> None:
        """优雅停止"""
        self._running = False
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 退出路径兜底
                pass
            self._loop_task = None
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        logger.info("定时调度器已停止")

    async def _tick_loop(self) -> None:
        tick = float(settings.get("SCHEDULER.TICK_SECONDS", 30))
        while self._running:
            try:
                await self._tick_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 单轮失败不中断循环
                logger.error(f"调度轮次执行失败: {e}")
            await asyncio.sleep(tick)

    async def _tick_once(self) -> None:
        """单轮扫描：抢锁 → 查到期计划 → 触发入队 → 推进触发时刻"""
        lock_ttl = int(settings.get("SCHEDULER.LOCK_TTL_SECONDS", 25))
        acquired = await self._redis.set(SCHEDULER_LOCK_KEY, "1", nx=True, ex=lock_ttl)
        if not acquired:
            return  # 其他实例已在执行本轮
        now = datetime.now()
        async with AsyncSession(self._engine()) as session:
            repo = SpiderScheduleRepository(session)
            due_list = await repo.list_due(now)
            for schedule in due_list:
                await self._fire(session, repo, schedule, now)

    async def _fire(self, session, repo, schedule, now: datetime) -> None:
        """触发一条到期计划：入队任务并推进触发时刻

        智能调度扩展：
        - 队列深度监控：触发前检查三级队列，超阈值告警
        - 动态优先级：根据历史成功率/时长自动调整
        - 时段感知：静默时段内非 high 优先级跳过触发

        入队被活跃键守卫拒绝（同爬虫已有任务）时仅跳过本次触发，
        仍推进 next_run_at，避免下一轮重复触发造成日志风暴。
        """
        spider_name = schedule.spider_name

        # ── 0. 队列深度监控 ──
        await self._check_queue_depth()

        # ── 1. 解析调度策略（存在 params JSON 的 _strategy 字段） ──
        strategy = self._parse_strategy(schedule.params)

        # ── 2. 动态优先级调整 ──
        priority = "normal"
        if strategy in ("dynamic", "quiet") and settings.get("SCHEDULER.DYNAMIC_PRIORITY", True):
            priority = await self._compute_priority(session, spider_name)

        # ── 3. 时段感知：静默时段内非 high 优先级延迟触发 ──
        quiet_hours = settings.get("SCHEDULER.QUIET_HOURS", []) or []
        if self._in_quiet_hours(now, quiet_hours) and priority != "high":
            logger.info(f"静默时段跳过调度: spider={spider_name}, quiet_hours={quiet_hours}")
            await self._advance_schedule(repo, schedule, now)
            return

        # ── 4. 入队（使用计算出的优先级） ──
        triggered = False
        try:
            service = SpiderService(session)
            await service.enqueue(spider_name=spider_name, params=schedule.params, priority=priority)
            triggered = True
            logger.info(
                f"调度触发任务入队: schedule_id={schedule.id}, spider={spider_name}, "
                f"priority={priority}, strategy={strategy}"
            )
        except BusinessException as e:
            logger.warning(
                f"调度触发被拒绝（跳过本次）: schedule_id={schedule.id}, "
                f"spider={spider_name}, reason={e}"
            )
        except Exception as e:  # noqa: BLE001 其他失败也推进时刻，防止死循环触发
            logger.error(
                f"调度触发失败: schedule_id={schedule.id}, spider={spider_name}, error={e}"
            )
        await self._advance_schedule(repo, schedule, now)
        if triggered:
            logger.info(f"调度触发完成: schedule_id={schedule.id}, spider={spider_name}")

    async def _check_queue_depth(self) -> None:
        """检查三级队列深度，超阈值记录告警日志（Redis 不可用时静默跳过）"""
        if self._redis is None:
            return
        warn_threshold = int(settings.get("SCHEDULER.QUEUE_DEPTH_WARN", 50))
        for p in TASK_QUEUE_PRIORITIES:
            depth = await self._redis.llen(task_queue(p))
            if depth > warn_threshold:
                logger.warning(f"队列堆积告警: priority={p}, depth={depth}")

    @staticmethod
    def _parse_strategy(params_json: Optional[str]) -> str:
        """从 params JSON 中提取调度策略字段 _strategy"""
        if not params_json:
            return "static"
        try:
            params = json.loads(params_json)
            return params.get("_strategy", "static")
        except (json.JSONDecodeError, TypeError):
            return "static"

    @staticmethod
    async def _compute_priority(session: AsyncSession, spider_name: str) -> str:
        """根据历史统计数据动态计算优先级"""
        task_repo = SpiderTaskRepository(session)
        stats = await task_repo.recent_stats_by_spider(spider_name)
        if stats["run_count"] < 3:
            return "normal"
        slow_threshold = int(settings.get("SCHEDULER.SLOW_TASK_THRESHOLD", 300))
        low_threshold = float(settings.get("SCHEDULER.LOW_SUCCESS_THRESHOLD", 0.5))
        if stats["success_rate"] < low_threshold:
            return "low"
        if stats["avg_duration"] > slow_threshold:
            return "high"
        return "normal"

    @staticmethod
    def _in_quiet_hours(now: datetime, quiet_hours: list) -> bool:
        """检查当前时间是否在静默时段内

        quiet_hours 格式: ["02:00-06:00", "23:00-23:59"]
        """
        if not quiet_hours:
            return False
        now_minutes = now.hour * 60 + now.minute
        for period in quiet_hours:
            try:
                start_str, end_str = period.split("-")
                sh, sm = map(int, start_str.strip().split(":"))
                eh, em = map(int, end_str.strip().split(":"))
                start_minutes = sh * 60 + sm
                end_minutes = eh * 60 + em
                if start_minutes <= end_minutes:
                    if start_minutes <= now_minutes <= end_minutes:
                        return True
                else:
                    # 跨午夜，如 23:00-02:00
                    if now_minutes >= start_minutes or now_minutes <= end_minutes:
                        return True
            except (ValueError, AttributeError):
                continue
        return False

    @staticmethod
    async def _advance_schedule(repo, schedule, now: datetime) -> None:
        """推进调度计划的触发时刻"""
        try:
            await repo.update(
                schedule.id,
                last_run_at=now,
                next_run_at=next_fire_time(schedule.cron_expr, now),
            )
            await repo.session.commit()
        except Exception as e:  # noqa: BLE001
            logger.error(f"推进调度触发时刻失败: schedule_id={schedule.id}, error={e}")

    @staticmethod
    def _engine():
        return get_manager().async_engines["DEFAULT"]

