"""外部 API 鉴权与公开数据端点测试

validate_api_key / 双轨鉴权（H1）/ 出站拉数 KEY_BINDINGS（GWT-13.1–13.4）/
status|results|stats。HTTP 层 AsyncMock，不连真 MySQL/Redis。
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.external_api.v1.webhooks import (
    _configured_api_keys,
    bound_tenant_id,
    validate_api_key,
)
from backend.repositories.spider_result_repository import CANDIDATE_SOURCE
from config import settings
from platform_core.exceptions import NotFoundException
from platform_core.schemas.spider import (
    SpiderResultListResponse,
    SpiderResultResponse,
    SpiderStatsResponse,
)

PUBLIC_BASE = "/external/v1/public"
VALID_KEY = "test-external-key"
TENANT_A = 11
TENANT_B = 22
KEY_A = "bound-key-tenant-a"
A_OWNED_ROW = {
    "id": 101, "task_id": 1, "spider_name": "alpha",
    "url": "https://a.example/1", "title": "a-owned", "source": "web",
}


def _set_api_keys(value) -> None:
    settings.set("EXTERNAL_API.API_KEYS", value)


def _set_legacy_api_key(value: str) -> None:
    settings.set("EXTERNAL_API.API_KEY", value)


def _set_key_bindings(value) -> None:
    settings.set("EXTERNAL_API.KEY_BINDINGS", value)


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


@pytest.fixture(autouse=True)
def restore_key_bindings():
    """每测恢复 KEY_BINDINGS，避免出站绑定泄漏到其它用例"""
    original = settings.get("EXTERNAL_API.KEY_BINDINGS", [])
    _set_key_bindings([])
    yield
    _set_key_bindings(original)


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

    def test_data_endpoint_legacy_key_rejected(self, client, restore_legacy_key):
        """GWT-13.4：仅配旧单 key 拉数视为未绑定，拒绝且不查库"""
        _set_api_keys([])
        _set_legacy_api_key(VALID_KEY)
        with patch(
            "backend.app.external_api.v1.public.SpiderQueryService.query_public_results",
            new=AsyncMock(return_value=([A_OWNED_ROW], 1)),
        ) as mocked:
            resp = client.get(
                f"{PUBLIC_BASE}/data/demo_spider",
                headers={"X-API-Key": VALID_KEY},
            )
        assert resp.status_code == 401
        assert resp.json().get("items") in (None, [])
        mocked.assert_not_called()

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


class TestBoundTenantId:
    """bound_tenant_id：配置绑定恰好一租户；旧列表 / 冲突 = 未绑定"""

    def test_list_binding_resolves(self):
        _set_key_bindings([{"key": KEY_A, "tenant_id": TENANT_A}])
        assert bound_tenant_id(KEY_A) == TENANT_A
        assert bound_tenant_id("other") is None

    def test_dict_and_json_string_binding(self):
        _set_key_bindings({KEY_A: TENANT_A})
        assert bound_tenant_id(KEY_A) == TENANT_A
        _set_key_bindings(f'[{{"key": "{KEY_A}", "tenant_id": {TENANT_A}}}]')
        assert bound_tenant_id(KEY_A) == TENANT_A

    def test_string_list_in_bindings_is_unbound(self):
        _set_key_bindings([KEY_A, VALID_KEY])
        assert bound_tenant_id(KEY_A) is None

    def test_conflicting_tenants_unbound(self):
        _set_key_bindings([
            {"key": KEY_A, "tenant_id": TENANT_A},
            {"key": KEY_A, "tenant_id": TENANT_B},
        ])
        assert bound_tenant_id(KEY_A) is None

    def test_same_tenant_twice_still_bound(self):
        _set_key_bindings([
            {"key": KEY_A, "tenant_id": TENANT_A},
            {"key": KEY_A, "tenant_id": TENANT_A},
        ])
        assert bound_tenant_id(KEY_A) == TENANT_A


class TestOutboundPullBinding:
    """GWT-13.1–13.4：出站拉数必须绑恰好一家企业；绑定后仍排除候选"""

    def test_gwt_13_1_bound_key_only_tenant_a(
        self, client, restore_legacy_key,
    ):
        """GWT-13.1：钥匙已绑定企业 A，拉 A 的非候选结果 → 只看到 A 的行"""
        _set_api_keys([])
        _set_legacy_api_key("")
        _set_key_bindings([{"key": KEY_A, "tenant_id": TENANT_A}])
        with patch(
            "backend.app.external_api.v1.public.SpiderQueryService.query_public_results",
            new=AsyncMock(return_value=([A_OWNED_ROW], 1)),
        ) as mocked:
            resp = client.get(
                f"{PUBLIC_BASE}/data/alpha",
                headers={"X-API-Key": KEY_A},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"] == [A_OWNED_ROW]
        kwargs = mocked.await_args.kwargs
        assert kwargs["tenant_id"] == TENANT_A
        assert kwargs["spider_name"] == "alpha"

    def test_gwt_13_2_no_binding_rejects_any_key(
        self, client, api_keys, restore_legacy_key,
    ):
        """GWT-13.2：未配置任何绑定，任意钥匙拉数 → 拒绝，0 行"""
        _set_legacy_api_key("")
        _set_key_bindings([])
        with patch(
            "backend.app.external_api.v1.public.SpiderQueryService.query_public_results",
            new=AsyncMock(return_value=([A_OWNED_ROW], 1)),
        ) as mocked:
            resp = client.get(
                f"{PUBLIC_BASE}/data/alpha",
                headers={"X-API-Key": VALID_KEY},
            )
        assert resp.status_code == 401
        assert resp.json().get("items") in (None, [])
        mocked.assert_not_called()

    def test_gwt_13_3_tenant_a_key_spider_b_zero_rows_of_b(
        self, client, restore_legacy_key,
    ):
        """GWT-13.3：绑定 A 的钥匙指定 B 的爬虫名 → 0 行 B 数据"""
        _set_api_keys([])
        _set_legacy_api_key("")
        _set_key_bindings([{"key": KEY_A, "tenant_id": TENANT_A}])
        with patch(
            "backend.app.external_api.v1.public.SpiderQueryService.query_public_results",
            new=AsyncMock(return_value=([], 0)),
        ) as mocked:
            resp = client.get(
                f"{PUBLIC_BASE}/data/beta",
                headers={"X-API-Key": KEY_A},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []
        kwargs = mocked.await_args.kwargs
        assert kwargs["tenant_id"] == TENANT_A
        assert kwargs["tenant_id"] != TENANT_B
        assert kwargs["spider_name"] == "beta"

    def test_gwt_13_4_string_list_key_rejected(
        self, client, api_keys, restore_legacy_key,
    ):
        """GWT-13.4：旧字符串列表钥匙尚未绑企业 → 视为未绑定，拒绝"""
        _set_legacy_api_key("")
        _set_key_bindings([])
        with patch(
            "backend.app.external_api.v1.public.SpiderQueryService.query_public_results",
            new=AsyncMock(return_value=([A_OWNED_ROW], 1)),
        ) as mocked:
            resp = client.get(
                f"{PUBLIC_BASE}/data/alpha",
                headers={"X-API-Key": VALID_KEY},
            )
        assert resp.status_code == 401
        assert resp.json().get("items") in (None, [])
        mocked.assert_not_called()

    @pytest.mark.asyncio
    async def test_bound_pull_still_excludes_marketplace(self):
        """绑定后仍 source <> marketplace（T-08 谓词，T-10 不放宽）"""
        from backend.services.spider_query_service import SpiderQueryService

        svc = SpiderQueryService.__new__(SpiderQueryService)
        svc.result_repo = MagicMock()
        svc.result_repo.query_by_spider = AsyncMock(return_value=([], 0))

        items, total = await svc.query_public_results(
            spider_name="alpha", tenant_id=TENANT_A,
        )

        assert items == [] and total == 0
        kwargs = svc.result_repo.query_by_spider.await_args.kwargs
        assert kwargs.get("exclude_source") == CANDIDATE_SOURCE
        assert kwargs.get("tenant_id") == TENANT_A

    @pytest.mark.asyncio
    async def test_unbound_service_returns_zero_rows_without_query(self):
        """未绑 tenant_id 时服务层 fail-closed：0 行且不打仓储"""
        from backend.services.spider_query_service import SpiderQueryService

        svc = SpiderQueryService.__new__(SpiderQueryService)
        svc.result_repo = MagicMock()
        svc.result_repo.query_by_spider = AsyncMock(return_value=([A_OWNED_ROW], 1))

        items, total = await svc.query_public_results(spider_name="alpha")

        assert items == [] and total == 0
        svc.result_repo.query_by_spider.assert_not_called()
