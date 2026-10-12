"""爬虫任务 Redis 队列协议 - 主队列消息 / 失败重试 ZSET / 并发槽位

自 spider_task_service 拆出（规模约定），供任务编排与任务编辑共用：
- queue_message：优先级主队列消息的唯一构造点（投递与编辑搬迁共用，保证 LREM 字节一致）
- RETRY_ZSET_KEY / retry_delay / _retry_message：失败重试延迟队列
- _find_retry_member / _swap_retry_member：重试等待期消息按 task_id 定位与替换
- _release_active_slots：释放全局 / 租户并发槽位

本模块函数只接收调用方传入的 redis 客户端，不自取连接：get_async_redis 的
调用点留在 Service 内（测试 patch 目标不变，异常语义由调用方 try 承接）。
spider_task_service 对 RETRY_ZSET_KEY / retry_delay / queue_message 做 re-export，
存量 import 路径（consumer / 测试）不变。
"""
import json
from typing import Optional

from platform_core.logger import get_logger
from platform_core.queues import ACTIVE_TASK_KEY, tenant_active_key

logger = get_logger("api")

# ----------------------------------------------------------------------
# 失败重试延迟队列（ZSET）：score = 到期时间戳，consumer._scan_retry_zset
# 每 tick 扫描到期成员原子抢占后重新投递主优先级队列。
# 键常量归置于任务域（重试逻辑归属；platform_core.queues 为禁改共享文件）。
# ----------------------------------------------------------------------
RETRY_ZSET_KEY = "spider:retry_zset"
_RETRY_DELAYS = (1, 5, 15)  # 第 n 次重试退避秒数（超出档位数取最后一档封顶）


def retry_delay(retry_count: int) -> int:
    logger.debug(f"计算重试退避: retry_count={retry_count}")
    # 退避档位：1 次→1s，2 次→5s，≥3 次→15s（封顶）
    idx = min(max(retry_count, 1), len(_RETRY_DELAYS)) - 1
    return _RETRY_DELAYS[idx]


def queue_message(task_id: int, spider_name: str, params: Optional[str]) -> str:
    """优先级主队列消息的唯一构造点（投递与编辑搬迁共用，保证 LREM 字节一致）"""
    logger.debug(f"构造队列消息 | task_id={task_id} spider={spider_name}")
    return json.dumps({"task_id": task_id, "spider_name": spider_name, "params": params},
                      ensure_ascii=False)


def _retry_message(task) -> str:
    """重试 ZSET 成员消息：携带 priority 字段供扫描侧选队（与主队列消息格式不同）"""
    return json.dumps(
        {
            "task_id": task.id,
            "spider_name": task.spider_name,
            "params": task.params,
            "priority": task.priority or "normal",
            "tenant_id": getattr(task, "tenant_id", None),
        },
        ensure_ascii=False,
    )


async def _find_retry_member(redis, task_id: int) -> Optional[tuple[str, float]]:
    """ZSCAN 全量游标按 task_id 定位重试 ZSET 成员，返回 (原始成员, score)；无则 None

    无法解析为 JSON 的成员跳过；其余异常原样上抛（由调用方吞掉记日志）。
    """
    cursor = 0
    while True:
        cursor, members = await redis.zscan(RETRY_ZSET_KEY, cursor=cursor, count=50)
        for raw, score in members:
            try:
                payload = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if payload.get("task_id") == task_id:
                return raw, score
        if cursor == 0:
            return None


async def _swap_retry_member(
    redis, task_id: int, matched: tuple[str, float], target_priority: str, new_message: str,
) -> bool:
    """ZREM 原子抢占旧成员 → ZADD 新消息（新 priority/params，score 保持原到期时刻）

    返回 False 表示 ZREM 被 consumer 抢占（其将把旧消息重投主队列，按未命中处理）。
    """
    raw, score = matched
    removed = await redis.zrem(RETRY_ZSET_KEY, raw)
    if not removed:
        logger.warning(
            f"重试 ZSET 成员已被 consumer 抢占，按未命中处理: task_id={task_id}"
        )
        return False
    new_payload = json.loads(new_message)
    new_payload["priority"] = target_priority
    await redis.zadd(
        RETRY_ZSET_KEY,
        {json.dumps(new_payload, ensure_ascii=False): score},
    )
    return True


async def _release_active_slots(redis, spider_name: str, task_id: int, task) -> None:
    """释放并发槽位：全局活跃键；task 带 int tenant_id 时再释放租户活跃键

    tenant_id 在全局键 SREM 之后再读取（与原内联写法同序）。
    """
    await redis.srem(ACTIVE_TASK_KEY.format(spider_name=spider_name), task_id)
    tid = getattr(task, "tenant_id", None)
    if isinstance(tid, int):
        await redis.srem(tenant_active_key(tid, spider_name), task_id)
