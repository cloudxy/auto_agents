"""T-04 / AD-5c：平台管理员公开详情预览旁路 + 租户/匿名不变回归。

GWT 锚：05.1/05.3/05.6 回归、03.4/03.5 不变、**03.7 点名**（unlisted 对非管理员
详情与媒体均 404）、**03.8 点名**（上下架端点越权 404 门面）、08.4（detail_opened）。

AD-5c 的豁免边界是本文件的重点：preview 只豁免 `listing_state` 分量，
`_row_is_fr33` 其余分量（黑名单 / license / 软删）对预览态仍全部生效。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.tests.fr33_support import fr33_asset, seed_rows
from conftest import make_platform_admin_headers, make_tenant_owner_headers
from platform_core.models.capability import CapabilityAsset

PUBLIC = "/api/v1/public/capabilities"
LISTING = "/api/v1/capabilities/skill/{}/listing"


class _RateRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, ttl):
        return True


@pytest.fixture(autouse=True)
def _rate(monkeypatch):
    fake = _RateRedis()

    async def _fake(key: str = "DEFAULT"):
        return fake

    import backend.app.api.v1.public_skills as pub
    monkeypatch.setattr(pub, "get_async_redis", _fake)
    return fake


def _seed(db_session, **kwargs) -> None:
    seed_rows(db_session, [fr33_asset(**kwargs)])


def _detail(name: str) -> str:
    return f"{PUBLIC}/skill/{name}"


def _media(name: str) -> str:
    return f"{PUBLIC}/skill/{name}/media/logo"


# ---------- AD-5c：管理员预览可读 unlisted ----------

def test_admin_preview_reads_unlisted_detail_with_marker(db_client, db_session):
    admin = make_platform_admin_headers(db_session)
    _seed(db_session, name="prev-unlisted", listing_state="unlisted")
    got = db_client.get(_detail("prev-unlisted"), params={"preview": "true"}, headers=admin)
    assert got.status_code == 200, got.text
    data = got.json()["data"]
    assert data["preview"] is True
    assert data["preview_unlisted"] is True       # 抽屉「未上架」提醒标签
    assert data["name"] == "prev-unlisted"
    assert "gate_open" in data                    # AD-5d：恒带实际闸值


def test_admin_without_preview_flag_still_404_on_unlisted(db_client, db_session):
    """旁路必须显式请求——不带 preview=true 的管理员走普通口径。"""
    admin = make_platform_admin_headers(db_session)
    _seed(db_session, name="prev-noflag", listing_state="unlisted")
    assert db_client.get(_detail("prev-noflag"), headers=admin).status_code == 404


def test_preview_exempts_listing_state_only(db_client, db_session):
    """黑名单/许可不合规分量对预览态仍然生效（豁免边界）。"""
    admin = make_platform_admin_headers(db_session)
    _seed(db_session, name="prev-black", listing_state="unlisted", status="blacklist")
    _seed(db_session, name="prev-nolic", listing_state="unlisted", license="NOASSERTION")
    for name in ("prev-black", "prev-nolic", "prev-ghost"):
        got = db_client.get(_detail(name), params={"preview": "true"}, headers=admin)
        assert got.status_code == 404, f"{name} -> {got.status_code}"


def test_admin_preview_list_bypasses_gate(db_client, db_session):
    """闸关时管理员预览仍拿到货架数据（FR-03 验收通道），payload 带真实闸值。"""
    from config import settings

    admin = make_platform_admin_headers(db_session)
    _seed(db_session, name="prev-gate", category="prev-gate")
    original = settings.get("POWER_MARKET.ENABLED")
    settings.set("POWER_MARKET.ENABLED", False)
    try:
        got = db_client.get(
            PUBLIC, params={"preview": "true", "category": "prev-gate"}, headers=admin,
        )
        assert got.status_code == 200, got.text
        data = got.json()["data"]
        assert data["preview"] is True
        assert data["market_closed"] is False
        assert data["gate_open"] is False
        assert [i["name"] for i in data["items"]] == ["prev-gate"]
    finally:
        settings.set("POWER_MARKET.ENABLED", original)


# ---------- GWT-03.7 unlisted 对非管理员不泄露 ----------

def test_gwt_03_7_tenant_and_anonymous_404_on_unlisted_detail_and_media(
    db_client, db_session,
):
    owner, _tid = make_tenant_owner_headers(db_session, slug="prev-t37")
    _seed(db_session, name="t37-unlisted", listing_state="unlisted",
          logo=".agents/skills/t37/icon.png")
    for headers in (owner, None):
        detail = db_client.get(_detail("t37-unlisted"), headers=headers)
        assert detail.status_code == 404, detail.text
        assert "SKILL" not in detail.text and "skill_md" not in detail.text
        media = db_client.get(_media("t37-unlisted"), headers=headers)
        assert media.status_code == 404


def test_gwt_03_7_tenant_preview_flag_is_ignored(db_client, db_session):
    """租户自己带 preview=true 不得生效（旁路只认 is_platform_admin）。"""
    owner, _tid = make_tenant_owner_headers(db_session, slug="prev-t37b")
    _seed(db_session, name="t37b-unlisted", listing_state="unlisted")
    got = db_client.get(_detail("t37b-unlisted"), params={"preview": "true"}, headers=owner)
    assert got.status_code == 404, got.text


# ---------- GWT-03.4 / 05.6 闸语义不变 ----------

def test_gwt_03_4_gate_closed_tenant_detail_unchanged(db_client, db_session):
    from config import settings

    owner, _tid = make_tenant_owner_headers(db_session, slug="prev-t34")
    _seed(db_session, name="t34-listed")
    original = settings.get("POWER_MARKET.ENABLED")
    settings.set("POWER_MARKET.ENABLED", False)
    try:
        got = db_client.get(_detail("t34-listed"), headers=owner)
        assert got.status_code == 200, got.text
        data = got.json()["data"]
        assert data.get("market_closed") is True
        assert data.get("gate_open") is False
        assert "skill_md" not in data          # 闸关不吐正文
    finally:
        settings.set("POWER_MARKET.ENABLED", original)


# ---------- GWT-03.8 上下架端点越权 404 门面 ----------

def test_gwt_03_8_listing_endpoint_404_for_non_admin_and_state_unchanged(
    db_client, db_session,
):
    owner, _tid = make_tenant_owner_headers(db_session, slug="prev-t38")
    _seed(db_session, name="t38-listed")
    got = db_client.patch(
        LISTING.format("t38-listed"), headers=owner, json={"listing_state": "unlisted"},
    )
    assert got.status_code == 404, got.text
    assert got.json()["code"] == "HTTP_404"
    assert "抱歉您没有权限" not in got.text and "FORBIDDEN" not in got.text

    async def _state():
        async with db_session() as s:
            return (await s.execute(
                select(CapabilityAsset.listing_state)
                .where(CapabilityAsset.name == "t38-listed")
            )).scalar_one()

    assert asyncio.run(_state()) == "listed"


# ---------- GWT-05.1 / 05.3 投影位回归 ----------

def test_detail_projects_examples_and_gate_open(db_client, db_session):
    _seed(db_session, name="prev-proj")
    got = db_client.get(_detail("prev-proj"))
    assert got.status_code == 200, got.text
    data = got.json()["data"]
    assert data["examples"] == []          # 未维护 → 空列表 → 前端隐藏区块
    assert data["gate_open"] is True


# ---------- QA-5：_md_path legacy 分支绝对/相对根回归 ----------

def test_qa5_md_path_reads_legacy_body_on_relative_and_absolute_root(
    db_client, db_session, tmp_path, monkeypatch,
):
    """相对 HEAD 回归：projection._md_path 的 legacy 分支（file_path 不带
    `.agents/` 前缀）曾在 `SKILLS.LIBRARY_ROOT` 为**绝对路径**时整个丢掉
    `rel`——读的是 `<LIBRARY_ROOT>/SKILL.md`（通常不存在→恒空正文；恰好
    存在则读到别的资产的正文），而不是 `<LIBRARY_ROOT>/<rel>/SKILL.md`。
    默认配置 `SKILLS.LIBRARY_ROOT="capability-library"` 是相对路径，绝对
    分支此前零覆盖，回归静默通过。参数化相对/绝对两种配置，断言同一
    legacy 行都读到正文。
    """
    from config import settings

    body = "# legacy 正文\n真实内容"
    skill_dir_name = "legacy-skill"

    def _write_skill(root: Path) -> None:
        d = root / skill_dir_name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(body, encoding="utf-8")

    original = settings.get("SKILLS.LIBRARY_ROOT")
    try:
        # 绝对路径配置：曾经被 bug 影响的分支
        abs_root = tmp_path / "abs-library"
        _write_skill(abs_root)
        settings.set("SKILLS.LIBRARY_ROOT", str(abs_root))
        _seed(db_session, name="qa5-abs", file_path=skill_dir_name)
        got = db_client.get(_detail("qa5-abs"))
        assert got.status_code == 200, got.text
        assert got.json()["data"]["skill_md"] == body

        # 相对路径配置：默认口径，修复前后都应正确（防止"修好绝对分支时
        # 顺手改坏相对分支"）。chdir 到 tmp_path，不碰真实仓库 cwd。
        rel_root_name = "rel-library"
        monkeypatch.chdir(tmp_path)
        _write_skill(tmp_path / rel_root_name)
        settings.set("SKILLS.LIBRARY_ROOT", rel_root_name)
        _seed(db_session, name="qa5-rel", file_path=skill_dir_name)
        got = db_client.get(_detail("qa5-rel"))
        assert got.status_code == 200, got.text
        assert got.json()["data"]["skill_md"] == body
    finally:
        settings.set("SKILLS.LIBRARY_ROOT", original)


# ---------- QA-11：预览态 install_count（OQ-D3 裁定过，实现一直没接） ----------

def test_qa11_preview_detail_carries_alive_install_count(db_client, db_session):
    """OQ-D3 裁定预览态显示订阅计数，但 get_public 一直没填这个字段——前端
    抽屉的「已订阅 N 次」恒不出现。种 3 条 alive 订阅，断言预览详情带
    install_count=3；再种一条软删订阅，断言不计入（alive 谓词与 hot 排序
    同一口径）。
    """
    from backend.tests.t25_support import seed_tenant
    from platform_core.models.capability import CapabilityInstall

    admin = make_platform_admin_headers(db_session)
    _seed(db_session, name="qa11-skill")
    tid = seed_tenant(db_session, slug="qa11-co")

    async def _install(hosts, *, alive=True):
        async with db_session() as s:
            asset_id = (await s.execute(
                select(CapabilityAsset.id).where(CapabilityAsset.name == "qa11-skill")
            )).scalar_one()
            for host in hosts:
                row = CapabilityInstall(
                    tenant_id=tid, asset_id=int(asset_id), host=host, enabled=1, trusted=0,
                )
                if not alive:
                    from datetime import datetime, timezone
                    row.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
                s.add(row)
            await s.commit()

    asyncio.run(_install(["grok", "zcode", "kimi"]))
    asyncio.run(_install(["claude-code"], alive=False))

    got = db_client.get(_detail("qa11-skill"), params={"preview": "true"}, headers=admin)
    assert got.status_code == 200, got.text
    assert got.json()["data"]["install_count"] == 3  # 软删的第 4 条不计入


def test_qa11_preview_detail_zero_installs(db_client, db_session):
    """无订阅时字段仍存在且为 0（不是缺字段），前端才能正确走"不显示"分支。"""
    admin = make_platform_admin_headers(db_session)
    _seed(db_session, name="qa11-zero-skill")

    got = db_client.get(_detail("qa11-zero-skill"), params={"preview": "true"}, headers=admin)
    assert got.status_code == 200, got.text
    assert got.json()["data"]["install_count"] == 0
