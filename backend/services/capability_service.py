"""能力资产目录服务（P6 C2）：统一目录层读写 + 技能扫描自动回填"""
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

    async def list_assets(
        self, asset_type: Optional[str] = None, category: Optional[str] = None,
        status: Optional[str] = None, q: Optional[str] = None,
        offset: int = 0, limit: int = 20,
    ) -> tuple[list[CapabilityAsset], int]:
        stmt = select(CapabilityAsset)
        if asset_type:
            stmt = stmt.where(CapabilityAsset.asset_type == asset_type)
        if category:
            stmt = stmt.where(CapabilityAsset.category == category)
        if status:
            stmt = stmt.where(CapabilityAsset.status == status)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(CapabilityAsset.name.like(like))
        from sqlalchemy import func

        total = (await self.session.execute(
            select(func.count()).select_from(stmt.subquery())
        )).scalar_one()
        rows = (await self.session.execute(
            stmt.order_by(CapabilityAsset.updated_at.desc().nullslast(), CapabilityAsset.id.asc())
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
        """技能 upsert 后同步 asset 行（skill 扫描管线调用点）"""
        existing = (await self.session.execute(
            select(CapabilityAsset).where(
                CapabilityAsset.asset_type == "skill",
                CapabilityAsset.name == skill.name,
            )
        )).scalar_one_or_none()
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
