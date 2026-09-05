"""健康检查冒烟测试 - 不依赖外部服务的基础端点"""


class TestRootEndpoints:
    """根路由冒烟"""

    def test_v1_root_returns_running_message(self, client):
        resp = client.get("/api/v1/")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Auto Agents API is running"

    def test_v1_health_returns_200(self, client):
        """/verify Skill 约定的后端健康检查端点"""
        resp = client.get("/api/v1/health/")
        assert resp.status_code == 200
        assert resp.json() == {"status": "healthy"}


class TestV2Health:
    """V2 增强健康检查（基础端点，不含 DB 依赖）"""

    def test_v2_health_returns_200_with_version(self, client):
        resp = client.get("/api/v2/health/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["version"] == "2.0.0"
        assert "response_time_ms" in body


class TestV1HealthDeep:
    """深探测端点（T11）：Docker HEALTHCHECK / watchdog 按 HTTP 状态码判定，
    任一依赖失败必须 503（旧端点恒 200 是编排器视角的浅探测）。全 mock，不连真库。"""

    def test_deep_returns_200_when_deps_healthy(self, app, client, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock

        from backend.app.api.v1 import health as health_module

        redis_mock = MagicMock()
        redis_mock.ping = AsyncMock(return_value=True)
        monkeypatch.setattr(health_module, "get_async_redis", lambda: redis_mock)
        # MySQL 侧走 conftest 全局 mock 会话（execute 成功）

        resp = client.get("/api/v1/health/deep")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["checks"] == {"mysql": "healthy", "redis": "healthy"}

    def test_deep_returns_503_when_db_down(self, app, client, monkeypatch):
        """DB 挂掉：会话 execute 抛错 → 503，error 仅暴露异常类型名"""
        from unittest.mock import AsyncMock, MagicMock

        from backend.app.api.v1 import health as health_module
        from platform_core.db import get_async_db

        bad_session = MagicMock()
        bad_session.execute = AsyncMock(side_effect=RuntimeError("db down"))

        async def _broken_db():
            yield bad_session

        redis_mock = MagicMock()
        redis_mock.ping = AsyncMock(return_value=True)
        monkeypatch.setattr(health_module, "get_async_redis", lambda: redis_mock)

        # 临时替换全局 override，finally 恢复（bfa31f7 教训：不恢复会污染后续用例）
        original = app.dependency_overrides.get(get_async_db)
        app.dependency_overrides[get_async_db] = _broken_db
        try:
            resp = client.get("/api/v1/health/deep")
        finally:
            if original is not None:
                app.dependency_overrides[get_async_db] = original
            else:
                app.dependency_overrides.pop(get_async_db, None)

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "unhealthy"
        assert body["checks"]["mysql"] == "unhealthy"
        assert body["checks"]["redis"] == "healthy"
        assert body["error"] == "RuntimeError"

    def test_deep_returns_503_when_redis_down(self, app, client, monkeypatch):
        """Redis 挂掉：ping 抛错 → 503（MySQL 侧走 conftest 全局 mock 会话，healthy）"""
        from unittest.mock import AsyncMock, MagicMock

        from backend.app.api.v1 import health as health_module

        redis_mock = MagicMock()
        redis_mock.ping = AsyncMock(side_effect=ConnectionError("redis down"))
        monkeypatch.setattr(health_module, "get_async_redis", lambda: redis_mock)

        resp = client.get("/api/v1/health/deep")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "unhealthy"
        assert body["checks"]["mysql"] == "healthy"
        assert body["checks"]["redis"] == "unhealthy"
        assert body["error"] == "ConnectionError"
