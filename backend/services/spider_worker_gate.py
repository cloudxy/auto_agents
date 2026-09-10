"""采集工人在线闸与超时空态标注（FR-18 / GWT-18.2 / 18.4）

心跳键 spider:worker:* 由 Worker 写入；无键即无在线工人。
IdleAutoClose 用 SPIDER_IDLE_CLOSE_SECONDS（默认 30）；
GWT-18.4 标注用 SPIDER_WORKER_OFFLINE_SECONDS（默认 120）。
21600 是渠道探针锁，禁止当任一窗。
扫描失败放行（与并发槽位 scard 失败同口径），0 键则拦住入队。
"""
from datetime import datetime, timezone
from typing import Iterable

from config import settings
from platform_core.exceptions import BusinessException
from platform_core.logger import get_logger
from platform_core.queues import WORKER_HEARTBEAT_PREFIX
from platform_core.schemas.spider import SpiderTaskResponse

logger = get_logger("api")

SPIDER_WORKER_OFFLINE_CODE = "SPIDER_WORKER_OFFLINE"
SPIDER_WORKER_OFFLINE_MESSAGE = "采集未运行，不会出数"
NON_TERMINAL = frozenset({"pending", "running", "queued"})
_IDLE_CLOSE_SECONDS = 30
_WORKER_OFFLINE_SECONDS = 120
_PROBE_LOCK_SECONDS = 21600


def _positive_seconds(key: str, default: int) -> int:
    logger.debug(f"读取秒数配置 | key={key}")
    raw = settings.get(key, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if value <= 0 or value == _PROBE_LOCK_SECONDS:
        return default
    return value


def product_idle_close_seconds() -> int:
    logger.debug("读取产品空闲收尾秒数")
    return _positive_seconds("SPIDER_IDLE_CLOSE_SECONDS", _IDLE_CLOSE_SECONDS)


def product_worker_offline_seconds() -> int:
    logger.debug("读取工人离线标注秒数")
    return _positive_seconds("SPIDER_WORKER_OFFLINE_SECONDS", _WORKER_OFFLINE_SECONDS)


async def count_online_workers(client) -> int:
    logger.info("扫描采集工人心跳")
    try:
        n = 0
        async for _key in client.scan_iter(
            match=f"{WORKER_HEARTBEAT_PREFIX}*", count=100
        ):
            n += 1
        return n
    except Exception as exc:  # noqa: BLE001 与槽位检查同口径：扫描失败放行
        logger.warning(f"扫描工人心跳失败（放行）: {exc}")
        return -1


async def require_online_worker(client) -> None:
    logger.info("入队前校验采集工人在线")
    n = await count_online_workers(client)
    if n == 0:
        raise BusinessException(
            SPIDER_WORKER_OFFLINE_MESSAGE,
            code=SPIDER_WORKER_OFFLINE_CODE,
        )


def _age_seconds(origin, now: datetime) -> float | None:
    if origin is None:
        return None
    if origin.tzinfo is None:
        origin = origin.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - origin).total_seconds()


def annotate_task_worker_status(task, worker_online: bool, now: datetime, window_s: int) -> SpiderTaskResponse:
    logger.debug("标注任务工人空态")
    resp = SpiderTaskResponse.model_validate(task)
    if worker_online or getattr(task, "status", None) not in NON_TERMINAL:
        return resp
    age = _age_seconds(getattr(task, "started_at", None) or getattr(task, "created_at", None), now)
    if age is None or age < window_s:
        return resp
    return resp.model_copy(
        update={
            "worker_offline": True,
            "error_message": getattr(task, "error_message", None)
            or SPIDER_WORKER_OFFLINE_MESSAGE,
        }
    )


async def annotate_tasks(tasks: Iterable, client) -> list[SpiderTaskResponse]:
    logger.info("标注任务列表工人空态")
    online = await count_online_workers(client)
    window = product_worker_offline_seconds()
    now = datetime.now(timezone.utc)
    worker_online = online != 0
    return [
        annotate_task_worker_status(task, worker_online, now, window) for task in tasks
    ]
