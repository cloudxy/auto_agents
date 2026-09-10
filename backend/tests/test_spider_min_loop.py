"""T-13 / GWT-18.1：夹具 example + https://httpbin.org/get，120s 内出数。

闭环：工人在线 → POST /run 入队 → StorePipeline 形 rpush ITEM_QUEUE
→ task_consumer lpop + _flush_batch（T-07 回流）→ webhook 终态 → 我的结果 + FR-03 导出。
禁止直写 SpiderResult / 手工 finish_task 顶替采集结束。
httpbin 不可达 → pytest.skip（skip ≠ GWT-18.1 pass）。
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from conftest import make_tenant_owner_headers
from platform_core.queues import ITEM_QUEUE
from stubs import FakeRedis, seed_worker_heartbeat

HTTPBIN_URL = "https://httpbin.org/get"
SCRAPY_DIR = str(Path(__file__).resolve().parents[2] / "scrapy")
CALLBACK_URL = "/external/v1/webhooks/spider/callback"


def _patch_redis(monkeypatch) -> FakeRedis:
    fake = FakeRedis()
    seed_worker_heartbeat(fake)

    def _get(key=None):
        return fake

    import backend.services.quota_service as quota_mod
    import backend.services.spider_task_service as svc_mod

    monkeypatch.setattr(svc_mod, "get_async_redis", _get)
    monkeypatch.setattr(quota_mod, "get_async_redis", _get)
    return fake


def _probe_httpbin():
    """夹具探活：不可达则 skip。skip 不得记为 GWT-18.1 绿。"""
    try:
        import httpx

        resp = httpx.get(HTTPBIN_URL, timeout=15.0, follow_redirects=True)
        resp.raise_for_status()
        return resp
    except Exception as exc:  # noqa: BLE001 网络阻断记 skip，不记 fail，也不记 pass
        pytest.skip(
            f"httpbin.org unreachable: {exc} "
            "(skip ≠ GWT-18.1 pass; live httpbin required)"
        )


def _parse_example(url: str, body: bytes, content_type: str) -> list:
    if SCRAPY_DIR not in sys.path:
        sys.path.insert(0, SCRAPY_DIR)
    from scrapy.http import TextResponse
    from spiders.example import ExampleSpider

    response = TextResponse(
        url=url,
        body=body,
        encoding="utf-8",
        headers={"Content-Type": content_type.encode("utf-8")},
    )
    spider = ExampleSpider.__new__(ExampleSpider)
    return list(ExampleSpider.parse(spider, response))


def _item_dict(item) -> dict:
    raw = dict(item) if not isinstance(item, dict) else dict(item)
    raw.pop("task_id", None)
    return raw


async def _ingest_flush(fake: FakeRedis, engine, task_id: int, item: dict) -> None:
    """StorePipeline rpush → consumer lpop → _flush_batch（T-07 回流，写测试库）。"""
    from backend.tasks.consumer import SpiderTaskConsumer

    message = json.dumps(
        {
            "task_id": task_id,
            "spider_name": "example",
            "item_type": "BaseItem",
            "item": item,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
        ensure_ascii=False,
        default=str,
    )
    await fake.rpush(ITEM_QUEUE, message)
    consumer = SpiderTaskConsumer()
    consumer._redis = fake
    consumer._engine = lambda: engine
    raws = await fake.lpop(ITEM_QUEUE, count=20)
    assert raws, "ITEM_QUEUE empty after StorePipeline rpush"
    messages = [json.loads(raw) for raw in raws]
    counts: dict[int, int] = {}
    for msg in messages:
        tid = msg["task_id"]
        counts[tid] = counts.get(tid, 0) + 1
    await consumer._flush_batch(messages, counts)


def _webhook_complete(client, task_id: int):
    """生产终态：Scrapy 同口径 HMAC 回调，不传 item_count（条数认回流累加）。"""
    from config import settings

    body = json.dumps({"task_id": task_id, "status": "completed"}).encode()
    ts = str(int(time.time()))
    secret = str(settings.WEBHOOK.SECRET_KEY)
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return client.post(
        CALLBACK_URL,
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Timestamp": ts,
            "X-Webhook-Signature": sig,
        },
    )


def test_example_httpbin_get_completes_with_items_within_120s(
    db_client, db_engine, db_session, monkeypatch,
):
    """GWT-18.1：工人在线 + example + httpbin/get → 入队→回流→终态；我的结果可导出。"""
    started = time.monotonic()
    http_resp = _probe_httpbin()
    items = _parse_example(
        str(http_resp.url), http_resp.content,
        http_resp.headers.get("content-type", "application/json"),
    )
    assert items
    fake = _patch_redis(monkeypatch)
    headers, _tid = make_tenant_owner_headers(db_session, slug="t13loop")
    run = db_client.post(
        "/api/v1/spiders/run",
        json={"spider_name": "example", "params": json.dumps({"urls": [HTTPBIN_URL]})},
        headers=headers,
    )
    assert run.status_code == 200, run.text
    task_id = run.json()["data"]["id"]
    asyncio.run(_ingest_flush(fake, db_engine, task_id, _item_dict(items[0])))
    assert _webhook_complete(db_client, task_id).status_code == 200
    listing = db_client.get("/api/v1/spiders/tasks", headers=headers)
    assert listing.status_code == 200, listing.text
    row = next(i for i in listing.json()["data"]["items"] if i["id"] == task_id)
    assert row["status"] == "completed" and row["result_count"] > 0
    mine = db_client.get(f"/api/v1/spiders/results/{task_id}", headers=headers)
    assert mine.status_code == 200 and mine.json()["data"]["total"] > 0
    exported = db_client.get(
        f"/api/v1/spiders/results/{task_id}/export",
        params={"format": "json"}, headers=headers,
    )
    assert exported.status_code == 200, exported.text
    assert len(json.loads(exported.content.decode("utf-8"))) > 0
    assert time.monotonic() - started <= 120
