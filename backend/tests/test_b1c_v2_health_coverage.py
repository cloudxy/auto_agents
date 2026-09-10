"""B1c 零 HTTP 覆盖路由清剿——v2 健康检查组合端点（2 条）

覆盖路由清单（无鉴权——健康检查面向编排器）：
- GET /api/v2/health/db      MySQL + Redis 组合探测（v1 单一事实源的版本化包装）
- GET /api/v2/health/storage 存储探测（复用 v1，同步 IO 已下沉线程池）

行为契约级口径（v2/health.py 模块契约：探测逻辑单一事实源在 v1，v2 只做组合包装）：
- 全部依赖健康 → 200 status=healthy + version=2.0.0 + database 分项明细
- 任一依赖故障 → 200 status=unhealthy + error 仅暴露异常类型名（细节走日志，
  与 v1 收窄口径一致；HTTP 503 语义由 /api/v1/health/deep 承担，不在本端点）
- v1 三端点与 /deep 已由 test_health_api.py / test_backend_fixes_regression.py
  覆盖，本文件只锁 v2 组合层接线
"""
from unittest.mock import AsyncMock, MagicMock

from platform_core.db import get_async_db


def _healthy_redis(monkeypatch):
    from backend.app.api.v1 import health as health_module

    redis_mock = MagicMock()
    redis_mock.ping = AsyncMock(return_value=True)
    monkeypatch.setattr(health_module, "get_async_redis", lambda: redis_mock)


# ---------------------------------------------------------------------------
# GET /api/v2/health/db
# ---------------------------------------------------------------------------

def test_v2_db_healthy(client, monkeypatch):
    """MySQL（conftest mock 会话 SELECT 1）+ Redis ping 均 OK → healthy + 分项明细"""
    _healthy_redis(monkeypatch)
    resp = client.get("/api/v2/health/db")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["version"] == "2.0.0"
    assert body["database"] == {"mysql": "healthy", "redis": "healthy"}
    assert body["response_time_ms"] >= 0


def test_v2_db_down_reports_type_name_only(client, monkeypatch):
    """MySQL 挂：unhealthy + database.mysql 分项 + error 只暴露异常类型名"""

    async def _broken_db():
        bad = MagicMock()
        bad.execute = AsyncMock(side_effect=RuntimeError("db down"))
        yield bad

    app = client.app
    original = app.dependency_overrides.get(get_async_db)
    app.dependency_overrides[get_async_db] = _broken_db
    try:
        _healthy_redis(monkeypatch)
        resp = client.get("/api/v2/health/db")
    finally:
        if original is not None:
            app.dependency_overrides[get_async_db] = original
        else:
            app.dependency_overrides.pop(get_async_db, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unhealthy"
    assert body["database"] == {"mysql": "unhealthy", "redis": "healthy"}
    assert body["error"] == "RuntimeError"  # 不回显连接串等内部细节


def test_v2_db_redis_down(client, monkeypatch):
    """Redis 挂：ping 抛错 → database.redis=unhealthy，error 只暴露类型名"""
    from backend.app.api.v1 import health as health_module

    redis_mock = MagicMock()
    redis_mock.ping = AsyncMock(side_effect=ConnectionError("redis down"))
    monkeypatch.setattr(health_module, "get_async_redis", lambda: redis_mock)

    resp = client.get("/api/v2/health/db")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unhealthy"
    assert body["database"]["redis"] == "unhealthy"
    assert body["database"]["mysql"] == "healthy"
    assert body["error"] == "ConnectionError"


# ---------------------------------------------------------------------------
# GET /api/v2/health/storage
# ---------------------------------------------------------------------------

def test_v2_storage_healthy(client):
    """本机存储可写（临时文件创建/删除探活）→ healthy"""
    resp = client.get("/api/v2/health/storage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["version"] == "2.0.0"
    assert body["storage"] == "filesystem"


def test_v2_storage_down_reports_type_name_only(client, monkeypatch):
    """存储故障：unhealthy + error 只暴露异常类型名（路径等细节不外泄）"""
    from backend.app.api.v1 import health as health_module

    def _boom():
        raise OSError("disk full")

    monkeypatch.setattr(health_module, "get_storage", _boom)
    resp = client.get("/api/v2/health/storage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unhealthy"
    assert body["error"] == "OSError"
