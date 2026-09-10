"""T-33 FR-45：人工短名 alias；冲突保存失败；同步不建。GWT-45.1…45.5。"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import inspect, select

from backend.tests.fr33_support import fr33_asset, seed_rows
from backend.tests.t25_support import bind_actor, seed_listed, seed_tenant
from backend.tests.test_t29_sources import _register, _sync, _write_plugin
from platform_core.models.capability import CapabilityAsset

_CAP = "/api/v1/public/capabilities"
_ALIAS = "/api/v1/capabilities/{}/{}/alias"


class _RateLimitRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, ttl):
        return True


@pytest.fixture
def rate_redis(monkeypatch):
    fake = _RateLimitRedis()

    async def _fake(key: str = "DEFAULT"):
        return fake

    import backend.app.api.v1.public_skills as pub
    monkeypatch.setattr(pub, "get_async_redis", _fake)
    return fake


@pytest.fixture
def library_root(tmp_path: Path):
    from config import settings

    original = settings.get("SKILLS.LIBRARY_ROOT")
    settings.set("SKILLS.LIBRARY_ROOT", str(tmp_path))
    (tmp_path / "plugins").mkdir(parents=True, exist_ok=True)
    yield tmp_path
    settings.set("SKILLS.LIBRARY_ROOT", original)


def _query(db_session, stmt):
    async def _go():
        async with db_session() as s:
            return list((await s.execute(stmt)).scalars().all())
    return asyncio.run(_go())


def _put_alias(client, asset_type: str, name: str, slug: str):
    return client.put(_ALIAS.format(asset_type, name), json={"slug": slug})


def _public_detail(client, asset_type: str, name: str):
    return client.get(f"{_CAP}/{asset_type}/{name}")


def _public_payload(client, asset_type: str, name: str) -> dict:
    resp = _public_detail(client, asset_type, name)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _alias_snapshot(db_session) -> list[tuple]:
    from platform_core.models.capability import CapabilityAlias

    rows = _query(db_session, select(CapabilityAlias).order_by(CapabilityAlias.id))
    return [
        (r.slug, int(r.asset_id), r.asset_type, r.deleted_at, r.tenant_id)
        for r in rows
    ]


def _catalog_names(db_session) -> list[tuple[str, str]]:
    rows = _query(
        db_session,
        select(CapabilityAsset)
        .where(CapabilityAsset.deleted_at.is_(None))
        .order_by(CapabilityAsset.id),
    )
    return [(r.asset_type, r.name) for r in rows]


def _public_url_set(client, pairs: list[tuple[str, str]]) -> dict:
    out = {}
    for asset_type, name in pairs:
        resp = _public_detail(client, asset_type, name)
        out[(asset_type, name)] = (resp.status_code, bytes(resp.content))
    return out


def test_gwt_45_1_alias_url_same_row_as_catalog_slug(
    db_client, platform_admin_client, db_session, rate_redis,
):
    """Given 超管指定未占用 alias「代码审查」 When 访客打开 Then 与目录短名同一行。"""
    seed_listed(db_session, name="g451-slug", title="代码审查技能")
    saved = _put_alias(platform_admin_client, "skill", "g451-slug", "代码审查")
    assert saved.status_code == 200, saved.text
    catalog = _public_payload(db_client, "skill", "g451-slug")
    aliased = _public_payload(db_client, "skill", "代码审查")
    assert catalog["name"] == aliased["name"] == "g451-slug"
    assert catalog == aliased


def test_gwt_45_2_catalog_slug_works_without_alias(
    db_client, db_session, rate_redis,
):
    """Given 该行没有 alias When 访客用目录短名打开 Then 仍到达详情。"""
    seed_listed(db_session, name="g452-only", title="无 alias")
    data = _public_payload(db_client, "skill", "g452-only")
    assert data["name"] == "g452-only"
    assert data["title"] == "无 alias"


def test_gwt_45_3_tenant_operator_cannot_set_alias(
    app, db_client, db_session, rate_redis,
):
    """Given 租户经办 When 指定或改 alias Then 拒绝；公开地址集合不变。"""
    seed_listed(db_session, name="g453-row", title="经办不可写")
    pairs = [("skill", "g453-row"), ("skill", "经办短名")]
    before_urls = _public_url_set(db_client, pairs)
    before_names = _catalog_names(db_session)
    before_alias = _alias_snapshot(db_session)
    tid = seed_tenant(db_session, "t33-op")
    bind_actor(app, role="operator", tenant_id=tid, tenant_role="operator")
    denied_op = _put_alias(db_client, "skill", "g453-row", "经办短名")
    assert denied_op.status_code == 403
    assert denied_op.json()["code"] == "FORBIDDEN"
    bind_actor(app, role="admin", tenant_id=tid, tenant_role="admin")
    denied_admin = _put_alias(db_client, "skill", "g453-row", "经办短名")
    assert denied_admin.status_code == 403
    assert denied_admin.json()["code"] == "FORBIDDEN"
    assert _public_url_set(db_client, pairs) == before_urls
    assert _catalog_names(db_session) == before_names
    assert _alias_snapshot(db_session) == before_alias
    assert _public_detail(db_client, "skill", "经办短名").status_code == 404


def test_gwt_45_4_conflict_catalog_name_both_unchanged(
    db_client, platform_admin_client, db_session, rate_redis,
):
    """夹具①：拟用 alias = 另一存活目录 name → 保存失败，两边字节不变。"""
    seed_rows(db_session, [
        fr33_asset(name="g454-a", title="A"),
        fr33_asset(name="taken-name", title="B"),
    ])
    before_names = _catalog_names(db_session)
    before_alias = _alias_snapshot(db_session)
    before_urls = _public_url_set(db_client, [
        ("skill", "g454-a"), ("skill", "taken-name"),
    ])
    resp = _put_alias(platform_admin_client, "skill", "g454-a", "taken-name")
    assert resp.status_code == 409, resp.text
    assert _catalog_names(db_session) == before_names
    assert _alias_snapshot(db_session) == before_alias
    assert _public_url_set(db_client, [
        ("skill", "g454-a"), ("skill", "taken-name"),
    ]) == before_urls
    assert _public_payload(db_client, "skill", "taken-name")["name"] == "taken-name"
    assert _public_detail(db_client, "skill", "g454-a").json()["data"]["name"] == "g454-a"


def test_gwt_45_4_conflict_live_alias_both_unchanged(
    db_client, platform_admin_client, db_session, rate_redis,
):
    """夹具②：拟用 alias = 另一存活 alias → 保存失败，两边字节不变。"""
    seed_rows(db_session, [
        fr33_asset(name="g454-left", title="左"),
        fr33_asset(name="g454-right", title="右"),
    ])
    first = _put_alias(platform_admin_client, "skill", "g454-right", "shared-alias")
    assert first.status_code == 200, first.text
    before_alias = _alias_snapshot(db_session)
    before_names = _catalog_names(db_session)
    before_urls = _public_url_set(db_client, [
        ("skill", "g454-left"), ("skill", "g454-right"), ("skill", "shared-alias"),
    ])
    resp = _put_alias(platform_admin_client, "skill", "g454-left", "shared-alias")
    assert resp.status_code == 409, resp.text
    assert _alias_snapshot(db_session) == before_alias
    assert _catalog_names(db_session) == before_names
    assert _public_url_set(db_client, [
        ("skill", "g454-left"), ("skill", "g454-right"), ("skill", "shared-alias"),
    ]) == before_urls
    assert _public_payload(db_client, "skill", "shared-alias")["name"] == "g454-right"


def test_gwt_45_5_src_sync_creates_zero_aliases(
    db_client, platform_admin_client, db_session, library_root, rate_redis,
):
    """Given 一次源同步结束 When 查看 alias Then 没有自动新建的 alias。"""
    from platform_core.models.capability import CapabilityAlias

    before = len(_query(db_session, select(CapabilityAlias)))
    tree = library_root / "src-t33"
    _write_plugin(tree, "t33-pack", ["short"])
    assert _register(platform_admin_client, "src-t33", str(tree)).status_code in (200, 201)
    synced = _sync(platform_admin_client, "src-t33")
    assert synced.status_code == 200, synced.text
    after = _query(db_session, select(CapabilityAlias))
    assert len(after) == before == 0


def test_pit1_public_aliases_registered_before_dynamic():
    """PIT-1：GET /public/capabilities/aliases 先于动态 /{type}/{name}。"""
    from backend.app.api.v1.public_skills import router

    paths = [(getattr(r, "path", ""), getattr(r, "methods", set()) or set())
             for r in router.routes]
    alias_i = next(i for i, (p, _) in enumerate(paths) if p.endswith("/aliases"))
    dyn_i = next(
        i for i, (p, m) in enumerate(paths)
        if "{asset_type}" in p and p.endswith("/{name}") and "GET" in m
    )
    assert alias_i < dyn_i


def test_pit1_admin_alias_write_before_dynamic_detail():
    """PIT-1：PUT /{type}/{name}/alias 先于动态 GET /{type}/{name}。"""
    from backend.app.api.v1.capabilities import router

    paths = [(getattr(r, "path", ""), getattr(r, "methods", set()) or set())
             for r in router.routes]
    put_i = next(
        i for i, (p, m) in enumerate(paths)
        if p.endswith("/alias") and "PUT" in m
    )
    get_i = next(
        i for i, (p, m) in enumerate(paths)
        if p.endswith("/{name}") and "{asset_type}" in p and "GET" in m
        and "/plugins/" not in p and "/experts/" not in p and "/teams/" not in p
    )
    assert put_i < get_i


def test_adr_0012_uq_asset_type_name_alive_unchanged():
    uq = [c for c in CapabilityAsset.__table__.constraints
          if c.name == "uq_asset_type_name_alive"]
    assert len(uq) == 1
    cols = [c.name for c in uq[0].columns]
    assert cols == ["asset_type", "name", "alive_flag"]
    assert inspect(CapabilityAsset) is not None


def test_migration_038_revises_037():
    import ast

    path = Path("backend/alembic/versions/038_t33_capability_aliases.py")
    text = path.read_text(encoding="utf-8")
    assert 'revision: str = "038"' in text
    assert 'down_revision: Union[str, Sequence[str], None] = "037"' in text
    assert "capability_aliases" in text
    assert "uq_aliases_slug_alive" in text
    assert "uq_aliases_asset_alive" in text
    tree = ast.parse(text)
    upgrade_fn = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "upgrade"
    )
    body = ast.get_source_segment(text, upgrade_fn) or ""
    assert "INSERT" not in body.upper()
    assert "028_" not in body and "029_" not in body and "030_" not in body


def test_alias_model_not_tenant_mixin():
    from platform_core.models.capability import CapabilityAlias
    from platform_core.models.mixins import TenantMixin

    assert TenantMixin not in CapabilityAlias.__mro__
    assert CapabilityAlias.__tablename__ == "capability_aliases"


def test_sync_path_does_not_insert_alias():
    src = Path("backend/services/power_market/sync.py").read_text(encoding="utf-8")
    assert "CapabilityAlias" not in src
    assert "capability_aliases" not in src
