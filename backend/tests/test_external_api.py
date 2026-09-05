"""外部 API 鉴权与公开数据端点测试

覆盖：
- validate_api_key：配置合法 key 放行 / 非法拒绝 / 空配置一律拒绝 / 字符串配置容错
- 双轨鉴权统一（H1）：仅配旧单 key（EXTERNAL_API.API_KEY）/ 仅配新列表（API_KEYS）/
  两者都空 → 新旧端点同一校验函数同一 401 口径
- /external/v1/public/data/{spider_name}：统一 _require_api_key 后与
  status/results/stats 同为 401 口径（不再存在 403 分支）
- /external/v1/public/spider/status|results|stats：真实数据 + API Key 鉴权 + 404 分支

约定：不连接真实 MySQL/Redis（HTTP 层用 AsyncMock 桩，对齐 conftest 约定）。
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.external_api.v1.webhooks import _configured_api_keys, validate_api_key
from config import settings
from platform_core.exceptions import NotFoundException
from platform_core.schemas.spider import (
    SpiderResultListResponse,
    SpiderResultResponse,
    SpiderStatsResponse,
)

PUBLIC_BASE = "/external/v1/public"
VALID_KEY = "test-external-key"


def _set_api_keys(value) -> None:
    """临时覆盖 EXTERNAL_API.API_KEYS（fixture 中恢复原值）"""
    settings.set("EXTERNAL_API.API_KEYS", value)


def _set_legacy_api_key(value: str) -> None:
    """临时覆盖旧单 key EXTERNAL_API.API_KEY（过渡期兼容配置）"""
    settings.set("EXTERNAL_API.API_KEY", value)


@pytest.fixture
def api_keys():
    """配置测试 API Key 并在用例结束后恢复"""
    original = settings.get("EXTERNAL_API.API_KEYS", [])
    _set_api_keys([VALID_KEY])
    yield VALID_KEY
    _set_api_keys(original)


@pytest.fixture
def empty_api_keys():
    """置空 API Key 配置（模拟未部署密钥）并恢复"""
    original = settings.get("EXTERNAL_API.API_KEYS", [])
    _set_api_keys([])
    yield
    _set_api_keys(original)


@pytest.fixture
def restore_legacy_key():
    """双轨鉴权测试的旧单 key 配置恢复（默认清空，用例内自行设置）"""
    original = settings.get("EXTERNAL_API.API_KEY", "")
    _set_legacy_api_key("")
    yield
    _set_legacy_api_key(str(original or ""))


def _task(**overrides) -> MagicMock:
    """构造带齐 SpiderTaskResponse 所需属性的任务桩"""
    base = dict(
        id=1,
        spider_name="demo_spider",
        status="running",
        priority="normal",
        result_count=5,
        retry_count=0,
        error_message=None,
        created_at=datetime(2026, 8, 30, 12, 0, 0),
        updated_at=None,
        started_at=datetime(2026, 8, 30, 12, 0, 5),
        completed_at=None,
    )
    base.update(overrides)
    return MagicMock(**base)


class TestValidateApiKey:
    """validate_api_key 纯函数（配置驱动，无 DB）"""

    def test_valid_key_passes(self):
        _set_api_keys(["k1", "k2"])
        try:
            assert validate_api_key("k1") is True
        finally:
            _set_api_keys([])

    def test_invalid_key_rejected(self):
        _set_api_keys(["k1"])
        try:
            assert validate_api_key("nope") is False
        finally:
            _set_api_keys([])

    def test_empty_config_rejects_all(self):
        """空配置（默认未部署）时一律拒绝，杜绝默认密钥"""
        _set_api_keys([])
        assert validate_api_key("") is False
        assert validate_api_key("anything") is False

    def test_json_string_config_tolerated(self):
        """环境变量以 JSON 字符串注入时容错解析"""
        _set_api_keys('["key-a"]')
        try:
            assert _configured_api_keys() == ["key-a"]
            assert validate_api_key("key-a") is True
        finally:
            _set_api_keys([])

    def test_empty_key_string_rejected(self):
        _set_api_keys([VALID_KEY])
        try:
            assert validate_api_key("") is False
        finally:
            _set_api_keys([])


class TestDualTrackAuth:
    """双轨鉴权统一（H1）：旧单 key 与新列表同一校验函数同一 401 口径"""

    def test_legacy_key_only_accepted(self, restore_legacy_key):
        """仅配旧单 key EXTERNAL_API.API_KEY 时也通过（过渡期兼容）"""
        _set_api_keys([])
        _set_legacy_api_key(VALID_KEY)
        assert validate_api_key(VALID_KEY) is True
        assert validate_api_key("other") is False

    def test_legacy_key_merged_dedup(self, restore_legacy_key):
        """旧单 key 与新列表同时配置时合并去重"""
        _set_api_keys([VALID_KEY])
        _set_legacy_api_key(VALID_KEY)
        assert _configured_api_keys() == [VALID_KEY]
        assert validate_api_key(VALID_KEY) is True

    def test_new_list_only_accepted(self, restore_legacy_key):
        """仅配新列表 EXTERNAL_API.API_KEYS 时通过，旧单 key 空不影响"""
        _set_api_keys([VALID_KEY])
        _set_legacy_api_key("")
        assert validate_api_key(VALID_KEY) is True

    def test_both_empty_rejects_all(self, restore_legacy_key):
        """两处配置都空时一律拒绝（新列表与旧 key 双空 → 401 口径）"""
        _set_api_keys([])
        _set_legacy_api_key("")
        assert validate_api_key("") is False
        assert validate_api_key(VALID_KEY) is False

    def test_data_endpoint_legacy_key_passes(self, client, restore_legacy_key):
        """仅配旧单 key 时 /data/{spider_name} 也通过（统一校验函数）"""
        _set_api_keys([])
        _set_legacy_api_key(VALID_KEY)
        with patch(
            "backend.app.external_api.v1.public.SpiderQueryService.query_public_results",
            new=AsyncMock(return_value=([], 0)),
        ):
            resp = client.get(
                f"{PUBLIC_BASE}/data/demo_spider",
                headers={"X-API-Key": VALID_KEY},
            )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_data_endpoint_invalid_key_401(self, client, api_keys, restore_legacy_key):
        """/data/{spider_name} 密钥不匹配时 401（与其他公开端点同口径）"""
        _set_legacy_api_key("")
        resp = client.get(
            f"{PUBLIC_BASE}/data/demo_spider", headers={"X-API-Key": "wrong-key"}
        )
        assert resp.status_code == 401

    def test_data_endpoint_missing_key_401(self, client, empty_api_keys, restore_legacy_key):
        """两处配置都空时 /data/{spider_name} 返回 401（原 403 分支已移除）"""
        _set_legacy_api_key("")
        resp = client.get(f"{PUBLIC_BASE}/data/demo_spider")
        assert resp.status_code == 401

    def test_status_endpoint_legacy_key_passes(self, client, restore_legacy_key):
        """仅配旧单 key 时 /spider/status 也通过"""
        _set_api_keys([])
        _set_legacy_api_key(VALID_KEY)
        task = _task()
        with patch(
            "backend.app.external_api.v1.public.SpiderQueryService.get_task",
            new=AsyncMock(return_value=task),
        ):
            resp = client.get(
                f"{PUBLIC_BASE}/spider/status/1",
                headers={"X-API-Key": VALID_KEY},
            )
        assert resp.status_code == 200


class TestPublicEndpointAuth:
    """公开端点统一鉴权（X-API-Key）"""

    def test_status_missing_key_401(self, client, empty_api_keys):
        resp = client.get(f"{PUBLIC_BASE}/spider/status/1")
        assert resp.status_code == 401

    def test_status_invalid_key_401(self, client, api_keys):
        resp = client.get(
            f"{PUBLIC_BASE}/spider/status/1", headers={"X-API-Key": "wrong-key"}
        )
        assert resp.status_code == 401

    def test_results_missing_key_401(self, client, empty_api_keys):
        resp = client.get(f"{PUBLIC_BASE}/spider/results/1")
        assert resp.status_code == 401

    def test_stats_missing_key_401(self, client, empty_api_keys):
        resp = client.get(f"{PUBLIC_BASE}/stats")
        assert resp.status_code == 401


class TestSpiderStatusEndpoint:
    """/spider/status/{task_id} 真实数据"""

    def test_real_task_data(self, client, api_keys):
        task = _task()
        with patch(
            "backend.app.external_api.v1.public.SpiderQueryService.get_task",
            new=AsyncMock(return_value=task),
        ):
            resp = client.get(
                f"{PUBLIC_BASE}/spider/status/1",
                headers={"X-API-Key": VALID_KEY},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 1
        assert body["spider_name"] == "demo_spider"
        assert body["status"] == "running"
        assert body["result_count"] == 5

    def test_not_found_404(self, client, api_keys):
        """任务缺失 404 语义归 Service（get_task 内抛，路由只映射）"""
        with patch(
            "backend.app.external_api.v1.public.SpiderQueryService.get_task",
            new=AsyncMock(side_effect=NotFoundException("爬虫任务")),
        ):
            resp = client.get(
                f"{PUBLIC_BASE}/spider/status/999",
                headers={"X-API-Key": VALID_KEY},
            )
        assert resp.status_code == 404


class TestSpiderResultsEndpoint:
    """/spider/results/{task_id} 真实数据"""

    def test_real_results_data(self, client, api_keys):
        resp_model = SpiderResultListResponse(
            total=1,
            items=[
                SpiderResultResponse(
                    id=1,
                    task_id=1,
                    spider_name="demo_spider",
                    url="https://example.com/1",
                    title="demo",
                )
            ],
        )
        with patch(
            "backend.app.external_api.v1.public.SpiderQueryService.list_results",
            new=AsyncMock(return_value=resp_model),
        ):
            resp = client.get(
                f"{PUBLIC_BASE}/spider/results/1",
                headers={"X-API-Key": VALID_KEY},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["task_id"] == 1
        assert body["total"] == 1
        assert body["data"][0]["url"] == "https://example.com/1"

    def test_not_found_404(self, client, api_keys):
        with patch(
            "backend.app.external_api.v1.public.SpiderQueryService.list_results",
            new=AsyncMock(side_effect=NotFoundException("爬虫任务")),
        ):
            resp = client.get(
                f"{PUBLIC_BASE}/spider/results/999",
                headers={"X-API-Key": VALID_KEY},
            )
        assert resp.status_code == 404


class TestPublicStatsEndpoint:
    """/stats 真实聚合统计"""

    def test_real_stats_data(self, client, api_keys):
        stats = SpiderStatsResponse(
            total_tasks=10,
            pending=1,
            running=2,
            completed=6,
            failed=1,
            success_rate=0.8571,
        )
        with patch(
            "backend.app.external_api.v1.public.SpiderQueryService.stats",
            new=AsyncMock(return_value=stats),
        ):
            resp = client.get(
                f"{PUBLIC_BASE}/stats",
                headers={"X-API-Key": VALID_KEY},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_tasks"] == 10
        assert body["completed"] == 6
        assert body["failed"] == 1
