"""健康检查冒烟测试 - 不依赖外部服务的基础端点"""


class TestRootEndpoints:
    """根路由冒烟"""

    def test_v1_root_returns_running_message(self, client):
        resp = client.get("/api/v1/")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Auto Agents API is running"

    def test_v1_health_returns_200(self, client):
        """/verify Skill 约定的后端健康检查端点"""
        resp = client.get("/api/v1/health")
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
