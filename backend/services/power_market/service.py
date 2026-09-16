"""能力市场公开读模型：查询侧 FR-33 闸再 COUNT/LIMIT（PIT-5）+ FR-80 测试种子闸。

feat-agents-market（AD-5）：平台管理员预览旁路 preview=True 跳闸（list/detail/media
三端点）；detail/media 额外豁免 listed 过滤的 listing_state 分量（unlisted 可读 +
preview_unlisted 标记，OQ-D1）；投影/媒体 href/md 正文读取已迁 projection.py（AD-11）。
"""
from typing import Optional

from sqlalchemy import String, cast, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.power_market.aliases import AliasWriter
from backend.services.power_market.installs import (
    _assert_actor,
    _assert_host,
    _require_tenant,
    insert_install,
    list_tenant_installs,
    patch_live_install,
    uninstall_live_install,
)
from backend.services.power_market.correct import CorrectGuard
from backend.services.power_market.license import LicenseWriter
from backend.services.power_market.listing import ListingWriter
from backend.services.power_market.projection import (
    _project as _project_row,
    _read_skill_md,
)
from backend.services.power_market.sorting import _apply_sort, _resolve_sort
from backend.services.power_market.sources import SourceRegistry
from backend.services.power_market.sync import SourceSync
from backend.services.power_market.references import list_runtime_refs
from backend.services.power_market.flag import (
    MSG_EMPTY_SHELF,
    closed_detail_payload,
    closed_list_payload,
    is_power_market_enabled,
    require_power_market_open,
)
from backend.services.power_market.types import (
    DEFAULT_ALLOWED_LICENSES,
    GOVERNANCE_PUBLIC,
    INVALID_ASSET_TYPE_MESSAGE,
    LEGACY_ASSET_TYPE_MAP,
    LISTING_VISIBLE,
    MARKET_COMING_SOON_CODE,
    MSG_COMING_SOON,
    MSG_NOT_FOUND,
    PAGE_SIZE_DEFAULT,
    PAGE_SIZE_MAX,
    PUBLIC_ASSET_TYPES,
    PUBLIC_HOSTS,
    READABLE_ASSET_TYPES,
    SEED_DESC_MARKER,
    SEED_NAME_PREFIX,
    SEED_TITLE_PREFIX,
    PatchInstallRequest,
    PatchLicenseOverrideRequest,
    PatchListingRequest,
    PutAliasRequest,
    _stored_types_for,
)
from platform_core.exceptions import (
    BusinessException,
    MarketNotFoundException,
    ValidationException,
)
from platform_core.logger import get_logger
from platform_core.models.capability import (
    CapabilityAlias, CapabilityAsset, CapabilityCommand, CapabilityComponent,
    CapabilityExpert,
)

logger = get_logger("service.power_market")


def _license_clause():
    """许可过闸：默认允许集 ∪ 超管特例。不进已订/引用解析。"""
    return or_(
        CapabilityAsset.public_license_override == 1,
        CapabilityAsset.license.in_(DEFAULT_ALLOWED_LICENSES),
    )


def _license_ok(row: CapabilityAsset) -> bool:
    if int(row.public_license_override or 0) == 1:
        return True
    return (row.license or "") in DEFAULT_ALLOWED_LICENSES


def _seed_clause():
    """FR-80 测试种子谓词（读模型层单点）：短名 nfr01qc2-* ∨ 标题「NFR卡片」开头 ∨ 描述含标记。

    三支 coalesce 到空串——NULL 列不是"未知种子"，是与 _row_is_seed 同口径的
    非种子（SQL 三值逻辑下 or_ 出 NULL 会把 listed 行整个挡出商店）。
    """
    return or_(
        func.coalesce(func.lower(CapabilityAsset.name), "").like(f"{SEED_NAME_PREFIX}%"),
        func.coalesce(CapabilityAsset.title, "").like(f"{SEED_TITLE_PREFIX}%"),
        func.coalesce(CapabilityAsset.description, "").like(f"%{SEED_DESC_MARKER}%"),
    )


def _row_is_seed(row: CapabilityAsset) -> bool:
    """FR-80 行级种子判定——与 _seed_clause 同口径（详情/订阅走同一闸）。"""
    return (
        (row.name or "").lower().startswith(SEED_NAME_PREFIX)
        or (row.title or "").startswith(SEED_TITLE_PREFIX)
        or SEED_DESC_MARKER in (row.description or "")
    )


def _fr33_clause():
    """上架∈listed∪coming_soon ∩ 治理∈stable∪recommended ∩ 许可过闸 ∩ 非软删 ∩ 非测试种子（FR-80）。"""
    return (
        CapabilityAsset.listing_state.in_(LISTING_VISIBLE),
        CapabilityAsset.status.in_(GOVERNANCE_PUBLIC),
        CapabilityAsset.deleted_at.is_(None),
        _license_clause(),
        not_(_seed_clause()),
    )


def _host_sql(host: str):
    """NULL=四宿主可订；[]=无；名单含 host 才命中。叠在 FR-33 之后、COUNT 之前。"""
    blob = cast(CapabilityAsset.host_compat, String)
    return or_(
        CapabilityAsset.host_compat.is_(None),
        blob.contains(f'"{host}"'),
    )


def _q_clause(text: str):
    """name/title LIKE，或 FR-33 过闸后的 command.slash（访客可带 /）。"""
    like = f"%{text}%"
    bare = text[1:] if text.startswith("/") else text
    slash_pats = [CapabilityCommand.slash.like(like)]
    if bare and bare != text:
        slash_pats.append(CapabilityCommand.slash.like(f"%{bare}%"))
    slash_ids = select(CapabilityCommand.asset_id).where(or_(*slash_pats))
    return or_(
        CapabilityAsset.name.like(like),
        CapabilityAsset.title.like(like),
        CapabilityAsset.origin_local_name.like(like),
        CapabilityAsset.id.in_(slash_ids),
    )


def _apply_list_filters(stmt, category: Optional[str], q: Optional[str], host: Optional[str]):
    cat = (category or "").strip()
    if cat:
        stmt = stmt.where(CapabilityAsset.category == cat)
    text = (q or "").strip()
    if text:
        stmt = stmt.where(_q_clause(text))
    key = (host or "").strip().lower()
    if not key:
        return stmt
    if key not in PUBLIC_HOSTS:
        return None
    return stmt.where(_host_sql(key))


def _row_is_fr33(row: CapabilityAsset, *, allow_unlisted: bool = False) -> bool:
    if row.deleted_at is not None:
        return False
    # AD-5c：预览态只豁免 listing_state 分量——deleted/status/种子/许可仍全生效
    if row.listing_state not in LISTING_VISIBLE and not allow_unlisted:
        return False
    if row.status not in GOVERNANCE_PUBLIC:
        return False
    if _row_is_seed(row):  # FR-80：种子翻成 listed 也不进公开详情/订阅
        return False
    return _license_ok(row)


class PowerMarketService:
    """商店读模型：FR-33 查询侧闸；GET 详情 miss 由路由套商店不存在句。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    def parse_asset_type(
        self, raw: Optional[str], *, default: Optional[str] = None,
    ) -> Optional[str]:
        logger.info(f"power_market.parse_asset_type | raw={raw} default={default}")
        value = default if raw is None or raw == "" else raw
        if value is None or value == "":
            return None
        if value in PUBLIC_ASSET_TYPES:
            return value
        mapped = LEGACY_ASSET_TYPE_MAP.get(value)
        if mapped:
            return mapped
        raise ValidationException(INVALID_ASSET_TYPE_MESSAGE, field="type")

    async def list_public(
        self,
        asset_type: Optional[str] = None,
        *,
        default: Optional[str] = None,
        category: Optional[str] = None,
        q: Optional[str] = None,
        host: Optional[str] = None,
        page: int = 1,
        page_size: int = PAGE_SIZE_DEFAULT,
        preview: bool = False,
        sort: Optional[str] = None,
    ) -> dict:
        logger.info(
            f"power_market.list_public | type={asset_type} page={page} "
            f"q={q} host={host} category={category} preview={preview} sort={sort}"
        )
        page_size = self._page_size(page_size)
        page = max(int(page or 1), 1)
        if not preview and not is_power_market_enabled():
            return closed_list_payload(page=page, page_size=page_size)
        public = self.parse_asset_type(asset_type, default=default)
        stored = None if public is None else _stored_types_for(public)
        applied = await _resolve_sort(self.session, sort)  # AD-6：hot 无计数降级
        rows, total = await self._list_fr33(
            stored, category, q, page, page_size, host=host, sort=applied,
        )
        sides = await self._command_sides(rows)
        payload = {
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": (page * page_size) < total,
            "items": [
                self._project(row, command=sides.get(row.id)) for row in rows
            ],
            "market_closed": False,
            "sort_applied": applied,
        }
        if preview:  # AD-5c：管理员预览态跳闸，payload 带实际闸值
            payload["preview"] = True
            payload["gate_open"] = is_power_market_enabled()
        if total == 0:
            payload["empty"] = True
            payload["message"] = MSG_EMPTY_SHELF
        return payload

    async def get_public(
        self, asset_type: Optional[str], name: str, *, default: Optional[str] = None,
        preview: bool = False,
    ) -> Optional[dict]:
        logger.info(
            f"power_market.get_public | type={asset_type} name={name} preview={preview}"
        )
        if not preview and not is_power_market_enabled():
            return {**closed_detail_payload(), "gate_open": False}
        public = self.parse_asset_type(asset_type, default=default)
        row = await self._load_named(public, name)
        if row is None or not _row_is_fr33(row, allow_unlisted=preview):
            return None
        sides = await self._command_sides([row])
        cmd = sides.get(row.id)
        item = self._project(row, command=cmd)
        item["includes"] = await self._list_includes(row.id)
        if item["asset_type"] == "skill":
            item["skill_md"] = _read_skill_md(row)
        if cmd is not None:
            item["body_md"] = cmd.body_md
        if item["asset_type"] == "agent":
            item["persona_md"] = await self._persona_md(row.id)
        # 同 QA-13 模式（examples 列随 050 迁移落地，getattr 防御不到 SQL 层
        # 未知列错误）：只留 ORM 侧真实存在时的默认值归一化。
        item["examples"] = row.examples or []
        item["gate_open"] = is_power_market_enabled()
        if preview:
            item["preview"] = True
            item["market_closed"] = False
            if row.listing_state == "unlisted":
                item["preview_unlisted"] = True  # 抽屉「未上架」提醒标签（OQ-D1）
        return item

    async def get_media_path(
        self, asset_type: Optional[str], name: str, kind: str,
        *, preview: bool = False,
    ) -> Optional[str]:
        logger.info(
            f"power_market.get_media_path | type={asset_type} name={name} "
            f"kind={kind} preview={preview}"
        )
        if kind not in ("logo", "background"):
            return None
        if not preview and not is_power_market_enabled():
            return None
        public = self.parse_asset_type(asset_type)
        row = await self._load_named(public, name)
        if row is None or not _row_is_fr33(row, allow_unlisted=preview):
            return None
        stored = getattr(row, kind, None)
        return str(stored) if stored else None

    async def subscribe_public(
        self,
        asset_type: Optional[str],
        name: str,
        *,
        host: Optional[str] = None,
        user=None,
        default: Optional[str] = None,
    ) -> dict:
        logger.info(f"power_market.subscribe_public | type={asset_type} name={name}")
        require_power_market_open()
        public = self.parse_asset_type(asset_type, default=default)
        row = await self._load_named(public, name)
        if row is None or not _row_is_fr33(row):
            raise MarketNotFoundException(MSG_NOT_FOUND)
        if row.listing_state == "coming_soon":
            raise BusinessException(
                message=MSG_COMING_SOON, code=MARKET_COMING_SOON_CODE, status_code=409,
            )
        if row.listing_state != "listed":
            raise MarketNotFoundException(MSG_NOT_FOUND)
        _assert_actor(user)
        host_key = _assert_host(row, host)
        return await insert_install(self.session, row, host_key, user)

    async def list_installs(self, user) -> dict:
        logger.info("power_market.list_installs")
        tenant_id = _require_tenant(user)
        return await list_tenant_installs(self.session, tenant_id, user)

    async def patch_install(self, install_id: int, user, payload: PatchInstallRequest) -> dict:
        logger.info(f"power_market.patch_install | id={install_id}")
        return await patch_live_install(
            self.session, install_id, user,
            enabled=payload.enabled, trusted=payload.trusted,
        )

    async def uninstall(self, install_id: int, user) -> dict:
        logger.info(f"power_market.uninstall | id={install_id}")
        return await uninstall_live_install(self.session, install_id, user)

    async def set_listing(
        self, asset_type: str, name: str, payload: PatchListingRequest,
    ) -> dict:
        logger.info(f"power_market.set_listing | type={asset_type} name={name}")
        return await ListingWriter(self.session).set_listing(asset_type, name, payload)

    async def set_license_override(
        self, asset_type: str, name: str, payload: PatchLicenseOverrideRequest,
    ) -> dict:
        logger.info(
            f"power_market.set_license_override | type={asset_type} name={name}"
        )
        return await LicenseWriter(self.session).set_override(asset_type, name, payload)

    async def set_alias(
        self, asset_type: str, name: str, payload: PutAliasRequest, *, actor: str,
    ) -> dict:
        logger.info(f"power_market.set_alias | type={asset_type} name={name}")
        return await AliasWriter(self.session).set_alias(
            asset_type, name, payload, actor=actor,
        )

    async def list_sources(self) -> dict:
        logger.info("power_market.list_sources")
        return await SourceRegistry(self.session).list_sources()

    async def register_source(self, payload, *, actor: str) -> dict:
        logger.info("power_market.register_source")
        return await SourceRegistry(self.session).register(payload, actor=actor)

    async def sync_source(self, name: str) -> dict:
        logger.info(f"power_market.sync_source | name={name}")
        return await SourceSync(self.session).sync(name)

    async def backfill_first_party(self) -> dict:
        logger.info("power_market.backfill_first_party")
        return await SourceRegistry(self.session).backfill_first_party()

    async def correct_asset(self, asset_type: str, name: str, payload: dict) -> dict:
        logger.info(f"power_market.correct_asset | type={asset_type} name={name}")
        return await CorrectGuard(self.session).correct(asset_type, name, payload)

    async def list_runtime_references(
        self, asset_type: Optional[str], name: str, *, user=None,
    ) -> dict:
        logger.info(
            f"power_market.list_runtime_references | type={asset_type} name={name}"
        )
        public = self.parse_asset_type(asset_type)
        return await list_runtime_refs(self.session, public, name, user=user)

    def _page_size(self, page_size: int) -> int:
        size = int(page_size or PAGE_SIZE_DEFAULT)
        if size < 1 or size > PAGE_SIZE_MAX:
            raise ValidationException(
                f"page_size 范围 1–{PAGE_SIZE_MAX}", field="page_size",
            )
        return size

    async def _list_fr33(
        self,
        stored_types: Optional[tuple[str, ...]],
        category: Optional[str],
        q: Optional[str],
        page: int,
        page_size: int,
        host: Optional[str] = None,
        sort: str = "smart",
    ) -> tuple[list[CapabilityAsset], int]:
        types = stored_types if stored_types else READABLE_ASSET_TYPES
        stmt = select(CapabilityAsset).where(
            CapabilityAsset.asset_type.in_(types), *_fr33_clause(),
        )
        stmt = _apply_list_filters(stmt, category, q, host)
        if stmt is None:
            return [], 0
        total = (await self.session.execute(
            select(func.count()).select_from(stmt.subquery())
        )).scalar_one()
        offset = (page - 1) * page_size
        rows = (await self.session.execute(
            _apply_sort(stmt, sort).offset(offset).limit(page_size)
        )).scalars().all()
        return list(rows), int(total)

    async def _load_named(
        self, public_type: Optional[str], name: str,
    ) -> Optional[CapabilityAsset]:
        types = READABLE_ASSET_TYPES if public_type is None else _stored_types_for(public_type)
        row = (await self.session.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.name == name,
                CapabilityAsset.asset_type.in_(types),
                CapabilityAsset.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if row is not None:
            return row
        return await self._load_by_alias(types, name)

    async def _load_by_alias(
        self, types: tuple[str, ...], slug: str,
    ) -> Optional[CapabilityAsset]:
        alias = (await self.session.execute(
            select(CapabilityAlias).where(
                CapabilityAlias.slug == slug,
                CapabilityAlias.asset_type.in_(types),
                CapabilityAlias.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if alias is None:
            return None
        return (await self.session.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.id == alias.asset_id,
                CapabilityAsset.deleted_at.is_(None),
            )
        )).scalar_one_or_none()

    async def _list_includes(self, parent_id: int) -> list[dict]:
        stmt = (
            select(CapabilityAsset)
            .join(
                CapabilityComponent,
                CapabilityComponent.child_asset_id == CapabilityAsset.id,
            )
            .where(
                CapabilityComponent.parent_asset_id == parent_id,
                *_fr33_clause(),
            )
            .order_by(CapabilityAsset.id.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [self._project(row) for row in rows]

    async def _command_sides(
        self, rows: list[CapabilityAsset],
    ) -> dict[int, CapabilityCommand]:
        ids = [r.id for r in rows if r.asset_type == "command"]
        if not ids:
            return {}
        found = (await self.session.execute(
            select(CapabilityCommand).where(CapabilityCommand.asset_id.in_(ids))
        )).scalars().all()
        return {int(c.asset_id): c for c in found}

    def _project(
        self, row: CapabilityAsset, *, command: Optional[CapabilityCommand] = None,
    ) -> dict:
        return _project_row(row, command=command)

    async def _persona_md(self, asset_id: int) -> str:
        detail = (await self.session.execute(
            select(CapabilityExpert).where(CapabilityExpert.asset_id == asset_id)
        )).scalar_one_or_none()
        return (detail.persona_md or "") if detail is not None else ""
