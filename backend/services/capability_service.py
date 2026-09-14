"""能力资产目录服务（P6 C2）：统一目录层读写 + 技能扫描自动回填"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.exceptions import NotFoundException
from platform_core.logger import get_logger
from platform_core.models.capability import CapabilityAsset
from platform_core.models.skill import Skill

logger = get_logger("service.capability")

# 技能表 → asset 层的列映射（治理字段收口；skill 特有字段留在 skills 表）
_SKILL_TO_ASSET = (
    "name", "title", "description", "category", "status", "source_type",
    "source_url", "source_author", "content_hash", "score", "ai_suggested_score",
    "tier", "reviewed_by", "reviewed_at", "similar_to", "file_path", "sync_state",
)


def _asset_row_from_skill(skill: Skill) -> dict:
    return {col: getattr(skill, col) for col in _SKILL_TO_ASSET}


class CapabilityService:
    """统一目录（session 注入）"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_catalog(
        self, asset_type: Optional[str] = None, category: Optional[str] = None,
        status: Optional[str] = None, q: Optional[str] = None,
        listing_state: Optional[str] = None,
        offset: int = 0, limit: int = 20,
    ) -> dict:
        """超管治理目录（含未上架）。空态不是货架关闭句。"""
        logger.info(
            f"查询治理目录: type={asset_type} status={status} listing={listing_state}"
        )
        rows, total = await self.list_assets(
            asset_type=asset_type, category=category, status=status, q=q,
            listing_state=listing_state, offset=offset, limit=limit,
        )
        items = [
            {
                "id": r.id, "asset_type": r.asset_type, "name": r.name,
                "title": r.title or "", "description": r.description,
                "category": r.category, "status": r.status, "tier": r.tier,
                "score": float(r.score) if r.score is not None else None,
                "ai_suggested_score": (
                    float(r.ai_suggested_score) if r.ai_suggested_score is not None else None
                ),
                "sync_state": r.sync_state,
                "listing_state": r.listing_state,
                "listed_at": r.listed_at.isoformat() if r.listed_at else None,
                "source_type": r.source_type,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]
        payload: dict = {"total": total, "items": items}
        if total == 0:
            payload["empty"] = True
            payload["message"] = "还没有目录项。同步源或扫描后会出现在这里。"
        return payload

    async def list_assets(
        self, asset_type: Optional[str] = None, category: Optional[str] = None,
        status: Optional[str] = None, q: Optional[str] = None,
        listing_state: Optional[str] = None,
        offset: int = 0, limit: int = 20,
    ) -> tuple[list[CapabilityAsset], int]:
        logger.info(f"查询资产列表: type={asset_type} listing={listing_state}")
        # FR-88：软收行（deleted_at 非空）不进治理目录——可上架/可操作列表
        # 与 total 都不含已从源收回的行（GWT-88.1/88.2/88.3）。
        stmt = select(CapabilityAsset).where(CapabilityAsset.deleted_at.is_(None))
        if asset_type:
            stmt = stmt.where(CapabilityAsset.asset_type == asset_type)
        if category:
            stmt = stmt.where(CapabilityAsset.category == category)
        if status:
            stmt = stmt.where(CapabilityAsset.status == status)
        if listing_state:
            stmt = stmt.where(CapabilityAsset.listing_state == listing_state)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(CapabilityAsset.name.like(like))
        from sqlalchemy import func

        total = (await self.session.execute(
            select(func.count()).select_from(stmt.subquery())
        )).scalar_one()
        rows = (await self.session.execute(
            stmt.order_by(CapabilityAsset.updated_at.desc(), CapabilityAsset.id.asc())
            .offset(offset).limit(limit)
        )).scalars().all()
        return list(rows), int(total)

    async def get_asset(self, asset_type: str, name: str) -> CapabilityAsset:
        row = (await self.session.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.asset_type == asset_type,
                CapabilityAsset.name == name,
            )
        )).scalar_one_or_none()
        if row is None:
            raise NotFoundException(resource=f"{asset_type} {name}")
        return row

    async def upsert_skill_asset(self, skill: Skill) -> CapabilityAsset:
        """技能 upsert 后同步 asset 行（skill 扫描管线调用点）

        FR-88 软收可逆：源目录回归时复活镜像行（存活行优先；仅剩软收行则
        取最新清 deleted_at）——镜像行生死跟随源目录，不永久滞留 gone 态。
        """
        existing = (await self.session.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.asset_type == "skill",
                CapabilityAsset.name == skill.name,
                CapabilityAsset.deleted_at.is_(None),
            )
        )).scalars().first()
        if existing is None:
            dead = (await self.session.execute(
                select(CapabilityAsset).where(
                    CapabilityAsset.asset_type == "skill",
                    CapabilityAsset.name == skill.name,
                ).order_by(CapabilityAsset.id.desc())
            )).scalars().first()
            if dead is not None:
                existing = dead
                existing.deleted_at = None
        if existing is None:
            asset = CapabilityAsset(asset_type="skill", detail_id=skill.id, **_asset_row_from_skill(skill))
            self.session.add(asset)
            await self.session.flush()
            return asset
        for col in _SKILL_TO_ASSET:
            setattr(existing, col, getattr(skill, col))
        existing.detail_id = skill.id
        await self.session.flush()
        return existing

    async def retract_skill_assets(self, names: list[str]) -> list[str]:
        """第一方技能镜像行软收回（FR-88）：源目录已删的行不再进治理目录。

        只动 detail_id 镜像行（本扫描创建）且未 attach 源的行——第三方源行
        的收回归 src_sync 单一归属，防两路互踩。
        """
        if not names:
            return []
        rows = (await self.session.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.asset_type == "skill",
                CapabilityAsset.name.in_(names),
                CapabilityAsset.detail_id.is_not(None),
                CapabilityAsset.source_id.is_(None),
                CapabilityAsset.deleted_at.is_(None),
            )
        )).scalars().all()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for row in rows:
            row.deleted_at = now
            row.sync_state = "gone"
        if rows:
            logger.info(f"capability.retract_skill_assets | count={len(rows)}")
        await self.session.flush()
        return [row.name for row in rows]
