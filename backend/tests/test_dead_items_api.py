"""B6 工单 91：死信队列 API（查看/丢弃/清空）

期望值来自独立事实源（种子字面量与队列名常量）。
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from platform_core.queues import DEAD_ITEM_QUEUE

# 种子：3 条死信（2 条合法 JSON + 1 条损坏载荷）
_SEED = [
    '{"spider_name": "hotsearch", "url": "http://a"}',
    "not-json-at-all",
    '{"spider_name": "weibo", "url": "http://b"}',
]


def _fake_redis(items: list[str]):
    m = MagicMock()
    m.llen = AsyncMock(return_value=len(items))
    m.lrange = AsyncMock(side_effect=lambda _k, start, end: items[max(0, start):end + 1] if start >= 0 else items[start:])
    m.lindex = AsyncMock(side_effect=lambda _k, i: items[i] if -len(items) <= i < len(items) else None)
    m.lrem = AsyncMock(side_effect=lambda _k, _n, v: 1 if v in items else 0)
    m.delete = AsyncMock(return_value=1)
    return m


@pytest.fixture
def seeded(monkeypatch):
    items = list(_SEED)
    m = _fake_redis(items)
    monkeypatch.setattr("backend.services.dead_item_service.get_async_redis", lambda *a, **k: m)
    return m, items


def test_list_returns_newest_first_with_total(db_client, seeded):
    resp = db_client.get("/api/v1/admin/dead-items?limit=10")
    body = resp.json()["data"]
    assert body["total"] == 3
    # 最新（尾元素）在最前
    assert body["items"][0]["spider_name"] == "weibo"
    assert body["items"][0]["seq"] == 1 and body["items"][0]["index"] == 2
    # 损坏载荷不炸：payload=None 但 raw 保留
    assert body["items"][1]["payload"] is None
    assert "not-json" in body["items"][1]["raw"]


def test_discard_removes_single_item(db_client, seeded):
    m, items = seeded
    resp = db_client.delete("/api/v1/admin/dead-items/0")
    assert resp.json()["data"] == {"index": 0, "removed": True}
    m.lrem.assert_awaited_once_with(DEAD_ITEM_QUEUE, 1, items[0])


def test_discard_missing_index_404(db_client, seeded):
    m, _ = seeded
    m.lindex = AsyncMock(return_value=None)
    resp = db_client.delete("/api/v1/admin/dead-items/99")
    assert resp.status_code == 404


def test_clear_empties_queue(db_client, seeded):
    resp = db_client.delete("/api/v1/admin/dead-items")
    assert resp.json()["data"]["removed"] == 3
    seeded[0].delete.assert_awaited_once_with(DEAD_ITEM_QUEUE)
