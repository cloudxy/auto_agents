"""代码爬虫文件管理测试（只读清单 + 启停）

约定：不连真实 MySQL，Repository 用 AsyncMock 桩；文件扫描用 tmp 目录。
覆盖：文件清单扫描、未登记爬虫展示、启停写库、未登记定义 404。
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.spider_registry_service import SpiderRegistryService  # noqa: E402
from platform_core.exceptions import NotFoundException  # noqa: E402


def _service() -> SpiderRegistryService:
    svc = SpiderRegistryService.__new__(SpiderRegistryService)
    svc.session = MagicMock()
    svc.session.commit = AsyncMock()
    svc.session.refresh = AsyncMock()
    svc.repo = MagicMock()
    return svc


@pytest.fixture
def spiders_dir(tmp_path):
    (tmp_path / "__init__.py").write_text("")
    (tmp_path / "example.py").write_text("name = 'example'\n" * 10)
    (tmp_path / "zhihu_feed.py").write_text("name = 'zhihu_feed'\n")
    (tmp_path / "not_a_spider.txt").write_text("ignored")
    return tmp_path


class TestSpiderFiles:
    @pytest.mark.asyncio
    async def test_scan_joins_definition_enabled(self, spiders_dir):
        svc = _service()
        definitions = [
            MagicMock(name="def_example", title="示例爬虫", enabled=True),
            MagicMock(name="def_zhihu", title="知乎动态", enabled=False),
        ]
        definitions[0].name = "example"
        definitions[1].name = "zhihu_feed"

        repo = MagicMock()
        repo.get_all = AsyncMock(return_value=definitions)
        with (
            patch("backend.services.spider_registry_service._SPIDERS_DIR", str(spiders_dir)),
            patch(
                "backend.services.spider_registry_service.SpiderDefinitionRepository",
                return_value=repo,
            ),
        ):
            resp = await svc.spider_files()

        # __init__.py 与非 .py 文件被排除
        assert resp.total == 2
        by_name = {i.name: i for i in resp.items}
        assert by_name["example"].registered is True
        assert by_name["example"].enabled is True
        assert by_name["example"].title == "示例爬虫"
        assert by_name["example"].file == "scrapy/spiders/example.py"
        assert by_name["example"].size_bytes > 0
        assert by_name["zhihu_feed"].enabled is False

    @pytest.mark.asyncio
    async def test_unregistered_file_shown_as_disabled(self, spiders_dir):
        svc = _service()
        repo = MagicMock()
        repo.get_all = AsyncMock(return_value=[])  # 无任何登记

        with (
            patch("backend.services.spider_registry_service._SPIDERS_DIR", str(spiders_dir)),
            patch(
                "backend.services.spider_registry_service.SpiderDefinitionRepository",
                return_value=repo,
            ),
        ):
            resp = await svc.spider_files()

        for item in resp.items:
            assert item.registered is False
            assert item.enabled is None  # 未登记视为未启用

    @pytest.mark.asyncio
    async def test_definition_read_failure_degrades_gracefully(self, spiders_dir):
        svc = _service()
        repo = MagicMock()
        repo.get_all = AsyncMock(side_effect=ConnectionError("db down"))

        with (
            patch("backend.services.spider_registry_service._SPIDERS_DIR", str(spiders_dir)),
            patch(
                "backend.services.spider_registry_service.SpiderDefinitionRepository",
                return_value=repo,
            ),
        ):
            resp = await svc.spider_files()

        assert resp.total == 2  # DB 异常时清单仍返回


class TestUpdateDefinition:
    @pytest.mark.asyncio
    async def test_toggle_writes_enabled(self):
        svc = _service()
        definition = MagicMock(id=3, title="示例爬虫",
                               type="web", description="", enabled=True,
                               source="yml_seed")
        definition.name = "example"  # MagicMock(name=...) 是保留参数，需显式赋值
        repo = MagicMock()
        repo.get_by_name = AsyncMock(return_value=definition)
        repo.update = AsyncMock(return_value=definition)

        with patch(
            "backend.services.spider_registry_service.SpiderDefinitionRepository",
            return_value=repo,
        ):
            resp = await svc.update_definition("example", False)

        repo.update.assert_awaited_once_with(3, enabled=False)
        svc.session.commit.assert_awaited()
        assert resp.name == "example"

    @pytest.mark.asyncio
    async def test_missing_definition_raises(self):
        svc = _service()
        repo = MagicMock()
        repo.get_by_name = AsyncMock(return_value=None)

        with patch(
            "backend.services.spider_registry_service.SpiderDefinitionRepository",
            return_value=repo,
        ):
            with pytest.raises(NotFoundException):
                await svc.update_definition("ghost", True)
