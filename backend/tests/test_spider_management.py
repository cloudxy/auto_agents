"""爬虫管理功能测试 - 注册表 / 任务删除 / 日志路径解析

约定：不连接真实 MySQL/Redis，Service 测试用 AsyncMock 桩。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.spider_common import resolve_spider_log_path
from backend.services.spider_task_service import SpiderTaskService
from platform_core.exceptions import BusinessException, NotFoundException


class TestSpiderRegistryEndpoint:
    """/spiders/registry 端点（配置驱动，无 DB 依赖）"""

    def test_registry_returns_types_and_spiders(self, client):
        resp = client.get("/api/v1/spiders/registry")
        assert resp.status_code == 200
        body = resp.json()["data"]

        type_keys = {t["type"] for t in body["types"]}
        assert {"api", "web"} <= type_keys

        spider_map = {s["name"]: s for s in body["spiders"]}
        assert "example" in spider_map
        assert spider_map["openweather"]["type"] == "api"
        assert spider_map["zhihu_feed"]["type"] == "web"

    def test_registry_fields_drive_dynamic_form(self, client):
        """类型的 fields 必须带 name/label/kind（前端动态表单契约）"""
        body = client.get("/api/v1/spiders/registry").json()["data"]
        for t in body["types"]:
            assert t["fields"], f"类型 {t['type']} 缺少字段定义"
            for f in t["fields"]:
                assert f["name"] and f["label"] and f["kind"]
        # urls 字段在两种类型中均为必填（消费者依赖 params.urls 分发）
        for t in body["types"]:
            urls_field = next((f for f in t["fields"] if f["name"] == "urls"), None)
            assert urls_field is not None and urls_field["required"] is True


class TestDeleteTask:
    """SpiderTaskService.delete_task 状态机规则"""

    def _service(self):
        svc = SpiderTaskService.__new__(SpiderTaskService)
        svc.session = MagicMock()
        svc.session.commit = AsyncMock()
        svc.repo = MagicMock()
        svc.result_repo = MagicMock()
        return svc

    @pytest.mark.asyncio
    async def test_delete_missing_task_raises_not_found(self):
        svc = self._service()
        svc.repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(NotFoundException):
            await svc.delete_task(999)

    @pytest.mark.asyncio
    async def test_delete_running_task_rejected(self):
        svc = self._service()
        task = MagicMock(status="running", spider_name="example")
        svc.repo.get_by_id = AsyncMock(return_value=task)
        with pytest.raises(BusinessException):
            await svc.delete_task(1)
        svc.repo.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_completed_task_cascades_results(self):
        svc = self._service()
        task = MagicMock(status="completed", spider_name="example")
        svc.repo.get_by_id = AsyncMock(return_value=task)
        svc.result_repo.delete_by_task = AsyncMock(return_value=3)
        svc.repo.delete = AsyncMock(return_value=True)

        fake_redis = AsyncMock()
        with patch("backend.services.spider_task_service.get_async_redis", return_value=fake_redis):
            result = await svc.delete_task(7)

        assert result == {"task_id": 7, "removed_results": 3}
        svc.result_repo.delete_by_task.assert_awaited_once_with(7)
        svc.repo.delete.assert_awaited_once_with(7)
        svc.session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_pending_task_clears_matching_active_key(self):
        svc = self._service()
        task = MagicMock(status="pending", spider_name="example")
        svc.repo.get_by_id = AsyncMock(return_value=task)
        svc.result_repo.delete_by_task = AsyncMock(return_value=0)
        svc.repo.delete = AsyncMock(return_value=True)

        fake_redis = AsyncMock()
        with patch("backend.services.spider_task_service.get_async_redis", return_value=fake_redis):
            await svc.delete_task(5)
            # 活跃键为 SET：从集合中移除被删任务（容忍 Redis 异常）
            fake_redis.srem.assert_awaited_once_with(
                "spider:active_tasks:example", 5
            )


class TestTaskLogPathResolution:
    """日志路径解析必须限定在项目 logs/ 目录（防目录穿越）"""

    def test_default_path_inside_logs_dir(self):
        path = resolve_spider_log_path()
        assert path is not None
        assert path.endswith(".log")
        assert "logs" in path.split("/")

    def test_malicious_path_rejected(self):
        spider_cfg = {"FILE": "../../etc/passwd"}
        with patch("backend.services.spider_common.settings") as mock_settings:
            mock_settings.LOGGERS = {"spider": spider_cfg}
            assert resolve_spider_log_path() is None
