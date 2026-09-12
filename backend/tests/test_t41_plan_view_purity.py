"""T-41 / FR-104 采集方案视图纯净测试（GWT-104.1..104.4）

口径（spec FR-104 + 票面澄清）：
- 混入项 = demo 爬虫（example/openweather）+ 能力资产收割器（skill_harvester）
  + flow 引擎伪爬虫（flow_generic 源码文件/引擎登记行）+ scrapy 源码文件清单
  （未登记 .py 一律不并入方案视图）。
- AI 注册的 flow 定义（type=flow、source=ai_generated）是真实采集方案，保留。
- 只滤视图：spider_definitions 行、enabled、scrapy/spiders/*.py 文件与
  入队校验（_ensure_spider_available 走 DB 直查）均不受影响。
- 治理目录（/v1/capabilities）只有资产，无 demo/内部爬虫独立入口（GWT-104.2 后半）。
"""
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import backend.services.spider_registry_service as registry_mod  # noqa: E402
from backend.services.spider_common import _INTERNAL_SPIDERS  # noqa: E402
from backend.services.spider_registry_service import SpiderRegistryService  # noqa: E402
from factories import build_spider_definition  # noqa: E402
from platform_core.models.spider_definition import SpiderDefinition  # noqa: E402

INTERNAL_NAMES = {"example", "openweather", "skill_harvester", "flow_generic"}


# ---------------------------------------------------------------------------
# 夹具：四类可展示项（demo 文件+登记 / 收割器登记 / 未登记源码文件 / flow 定义）
# ---------------------------------------------------------------------------

@pytest.fixture
def plan_dir(tmp_path):
    """源码目录：内部文件 + 未登记文件 + 业务文件并存（文件一律不删，GWT-104.2 尾句）"""
    for fname in (
        "__init__.py", "example.py", "skill_harvester.py", "flow_generic.py",
        "stray_thing.py", "zhihu_feed.py",
    ):
        (tmp_path / fname).write_text(f"# {fname}\n" * 3)
    return tmp_path


def _def_row(name: str, dtype: str = "web", source: str = "yml_seed") -> MagicMock:
    row = MagicMock(name=f"row_{name}", title=f"标题 {name}", type=dtype,
                    description="d", enabled=True, source=source, params=None)
    row.name = name  # MagicMock(name=...) 是保留参数，需显式赋值
    return row


def _plan_definitions() -> list:
    """四类登记行：demo / 收割器 / flow 引擎 / 业务 + AI flow 定义（应保留）"""
    return [
        _def_row("example", "web"),
        _def_row("skill_harvester", "api"),
        _def_row("flow_generic", "custom"),
        _def_row("zhihu_feed", "web"),
        _def_row("flow_plan_7", "flow", source="ai_generated"),
    ]


def _svc() -> SpiderRegistryService:
    svc = SpiderRegistryService.__new__(SpiderRegistryService)
    svc.session = MagicMock()
    svc.session.commit = AsyncMock()
    svc.session.refresh = AsyncMock()
    svc.repo = MagicMock()
    return svc


def _patch_repo(definitions, list_enabled=None):
    repo = MagicMock()
    repo.get_all = AsyncMock(return_value=definitions)
    repo.list_enabled = AsyncMock(
        return_value=list_enabled if list_enabled is not None else definitions)
    return patch(
        "backend.services.spider_registry_service.SpiderDefinitionRepository",
        return_value=repo,
    )


def _merged_view(registry_resp, files_resp) -> set:
    """模拟 FileTab 合并读模型：文件行 ∪ 仅注册表行（尾部追加）"""
    names = {i.name for i in files_resp.items}
    names |= {s.name for s in registry_resp.spiders}
    return names


# ---------------------------------------------------------------------------
# GWT-104.1 正常·纯净
# ---------------------------------------------------------------------------

class TestGwt1041PlanViewPurity:
    @pytest.mark.asyncio
    async def test_plan_view_excludes_internal_and_unregistered(self, plan_dir):
        """四类混入项均不出现；业务爬虫与 AI flow 定义保留"""
        svc = _svc()
        defs = _plan_definitions()
        with (
            patch.object(registry_mod, "_SPIDERS_DIR", str(plan_dir)),
            _patch_repo(defs),
        ):
            reg = await svc.registry()
            files = await svc.spider_files()

        assert {s.name for s in reg.spiders} == {"zhihu_feed", "flow_plan_7"}
        assert {i.name for i in files.items} == {"zhihu_feed"}
        merged = _merged_view(reg, files)
        # demo 爬虫 / 收割器 / flow 伪爬虫 / 未登记源码文件 均不混入
        assert merged == {"zhihu_feed", "flow_plan_7"}
        assert "stray_thing" not in merged
        assert not (merged & INTERNAL_NAMES)

    @pytest.mark.asyncio
    async def test_fallback_config_seeds_filtered_on_db_error(self):
        """DB 读失败回退 yml 种子时同口径过滤（example/openweather/flow_generic 不下发）"""
        svc = _svc()
        repo = MagicMock()
        repo.list_enabled = AsyncMock(side_effect=RuntimeError("db down"))
        with (
            patch.object(registry_mod, "_SPIDERS_DIR", "/nonexistent"),
            patch("backend.services.spider_registry_service.SpiderDefinitionRepository",
                  return_value=repo),
        ):
            reg = await svc.registry()

        names = {s.name for s in reg.spiders}
        assert not (names & INTERNAL_NAMES)
        assert {"dianping_home", "zhihu_feed", "generic"} <= names

    @pytest.mark.asyncio
    async def test_files_db_failure_fails_closed(self, plan_dir):
        """定义读取失败 → 清单收敛为空（宁空勿泄：不回退全量源码清单）"""
        svc = _svc()
        repo = MagicMock()
        repo.get_all = AsyncMock(side_effect=ConnectionError("db down"))
        with (
            patch.object(registry_mod, "_SPIDERS_DIR", str(plan_dir)),
            patch("backend.services.spider_registry_service.SpiderDefinitionRepository",
                  return_value=repo),
        ):
            resp = await svc.spider_files()

        assert resp.total == 0
        assert resp.items == []

    def test_internal_manifest_is_frozen_contract(self):
        """内部项清单与口径一致（防漂移：增删须回 spec）"""
        assert _INTERNAL_SPIDERS == frozenset(INTERNAL_NAMES)


# ---------------------------------------------------------------------------
# GWT-104.2 边界·独立入口 + 尾句（不删爬虫与文件）
# ---------------------------------------------------------------------------

class TestGwt1042NoIndependentEntry:
    @pytest.mark.asyncio
    async def test_view_filter_deletes_nothing_on_disk(self, plan_dir):
        """过滤只作用视图：源码文件在调用后全部仍在（GWT-104.2 尾句）"""
        svc = _svc()
        with (
            patch.object(registry_mod, "_SPIDERS_DIR", str(plan_dir)),
            _patch_repo(_plan_definitions()),
        ):
            await svc.registry()
            await svc.spider_files()

        for fname in ("example.py", "skill_harvester.py", "flow_generic.py",
                      "stray_thing.py", "zhihu_feed.py"):
            assert os.path.exists(plan_dir / fname), f"{fname} 被误删"


def _seed(db_session, *rows):
    async def _go():
        async with db_session() as s:
            for row in rows:
                s.add(row)
            await s.commit()

    asyncio.run(_go())


def _fetch(db_session, stmt):
    async def _go():
        async with db_session() as s:
            return (await s.execute(stmt)).scalars().all()

    return asyncio.run(_go())


class TestGwt1042HttpSurface:
    def test_capabilities_catalog_has_no_spider_entry(self, db_client, viewer_client,
                                                      db_session):
        """治理目录只有资产：目录项无爬虫类型/名称，路由表无爬虫入口"""
        _seed(db_session,
              build_spider_definition(name="example", title="demo", type="web"),
              build_spider_definition(name="skill_harvester", title="收割器", type="api"))
        resp = db_client.get("/api/v1/capabilities")
        assert resp.status_code == 200, resp.text
        items = resp.json()["data"]["items"] or []
        asset_types = {i["asset_type"] for i in items}
        assert asset_types <= {"skill", "plugin", "command", "agent",
                               "expert", "expert_team"}
        assert not ({i["name"] for i in items} & INTERNAL_NAMES)

        # 结构断言：capabilities 路由族不含任何爬虫入口
        from backend.app.api.v1.capabilities import router as cap_router
        for route in cap_router.routes:
            assert "spider" not in route.path

    def test_view_reads_delete_no_rows(self, db_client, viewer_client, db_session,
                                       tmp_path, monkeypatch):
        """读方案视图后定义行仍在（只滤视图，行不删）+ HTTP 面纯净口径"""
        for fname in ("example.py", "zhihu_feed.py"):
            (tmp_path / fname).write_text("# f\n")
        monkeypatch.setattr(registry_mod, "_SPIDERS_DIR", str(tmp_path))
        _seed(db_session,
              build_spider_definition(name="example", title="demo", type="web"),
              build_spider_definition(name="zhihu_feed", title="业务", type="web"))

        files_resp = db_client.get("/api/v1/spiders/files")
        assert files_resp.status_code == 200, files_resp.text
        assert {i["name"] for i in files_resp.json()["data"]["items"]} == {"zhihu_feed"}

        rows = _fetch(db_session, select(SpiderDefinition))
        assert {r.name for r in rows} == {"example", "zhihu_feed"}


# ---------------------------------------------------------------------------
# GWT-104.3 空态
# ---------------------------------------------------------------------------

class TestGwt1043EmptyState:
    @pytest.mark.asyncio
    async def test_all_internal_yields_empty_view(self, plan_dir):
        """仅存内部项 → 方案视图 0 行（空态可达；总数不被混入项顶满）"""
        svc = _svc()
        defs = [_def_row("example"), _def_row("skill_harvester"),
                _def_row("flow_generic", "custom")]
        with (
            patch.object(registry_mod, "_SPIDERS_DIR", str(plan_dir)),
            _patch_repo(defs),
        ):
            reg = await svc.registry()
            files = await svc.spider_files()

        assert reg.spiders == []
        assert files.items == []
        assert _merged_view(reg, files) == set()


# ---------------------------------------------------------------------------
# GWT-104.4 越权·只读同口径
# ---------------------------------------------------------------------------

class TestGwt1044ReadonlySameView:
    def test_viewer_sees_same_filtered_view(self, db_client, viewer_client,
                                            db_session, tmp_path, monkeypatch):
        """过滤在数据层与角色无关：只读成员同口径不出现混入项"""
        for fname in ("example.py", "zhihu_feed.py"):
            (tmp_path / fname).write_text("# f\n")
        monkeypatch.setattr(registry_mod, "_SPIDERS_DIR", str(tmp_path))
        _seed(db_session,
              build_spider_definition(name="example", title="demo", type="web"),
              build_spider_definition(name="zhihu_feed", title="业务", type="web"),
              build_spider_definition(name="flow_plan_9", title="AI 方案",
                                      type="flow", source="ai_generated"))

        names_by_role = {}
        for label, cl in (("member", db_client), ("viewer", viewer_client)):
            resp = cl.get("/api/v1/spiders/registry")
            assert resp.status_code == 200, resp.text
            names_by_role[label] = {s["name"] for s in resp.json()["data"]["spiders"]}

        assert names_by_role["viewer"] == {"zhihu_feed", "flow_plan_9"}
        assert names_by_role["viewer"] == names_by_role["member"]

        files_resp = viewer_client.get("/api/v1/spiders/files")
        assert files_resp.status_code == 200, files_resp.text
        assert {i["name"] for i in files_resp.json()["data"]["items"]} == {"zhihu_feed"}
