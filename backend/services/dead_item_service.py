"""死信队列服务（B6，工单 91）——spider:item_dead 留档消息的查看/清理/丢弃

死信来源（consumer._accept_message）：结果消息缺 task_id 等无法归属的载荷，
rpush 留档供排障；本服务提供运营视角的读/删能力（只读快照 + 指定丢弃）。
"""
import json
from typing import Optional

from platform_core.logger import get_logger
from platform_core.queues import DEAD_ITEM_QUEUE
from platform_core.redis_async import get_async_redis

logger = get_logger("service.dead_items")

# 死信留档上限（超过后写入端继续 rpush 但运营面只展示最新 N 条；防 unbounded list 拖垮 UI）
_MAX_LIST_WINDOW = 500


class DeadItemService:
    """死信队列读/删（无状态，每次经门面取连接）"""

    async def list_items(self, limit: int = 100) -> dict:
        """最新死信倒序列表（lrange 尾窗 + 反转，最新在前）+ 队列总量"""
        redis = get_async_redis()
        total = int(await redis.llen(DEAD_ITEM_QUEUE))
        window = min(max(1, min(limit, _MAX_LIST_WINDOW)), total) if total else 0
        raw_items: list[str] = []
        if window:
            raw_items = list(await redis.lrange(DEAD_ITEM_QUEUE, -window, -1))
        items = []
        for offset, raw in enumerate(reversed(raw_items)):
            payload: Optional[dict]
            try:
                payload = json.loads(raw)
            except (TypeError, ValueError):
                payload = None
            items.append({
                # 倒序序号：1 = 最新（真实 index = total - 1 - offset，用于定点删除）
                "seq": offset + 1,
                "index": total - 1 - offset,
                "raw": raw,
                "spider_name": (payload or {}).get("spider_name"),
                "payload": payload,
            })
        logger.info(f"死信队列查看 | total={total} shown={len(items)}")
        return {"total": total, "items": items}

    async def discard(self, index: int) -> bool:
        """按队列 index 丢弃一条死信（lrem 按值删除，值重复时删最早一条）"""
        redis = get_async_redis()
        raw = await redis.lindex(DEAD_ITEM_QUEUE, index)
        if raw is None:
            return False
        removed = int(await redis.lrem(DEAD_ITEM_QUEUE, 1, raw))
        logger.warning(f"死信丢弃 | index={index} removed={removed}")
        return removed > 0

    async def clear(self) -> int:
        """清空死信队列（排障终态动作，返回清除量）"""
        redis = get_async_redis()
        total = int(await redis.llen(DEAD_ITEM_QUEUE))
        await redis.delete(DEAD_ITEM_QUEUE)
        logger.warning(f"死信队列清空 | removed={total}")
        return total
