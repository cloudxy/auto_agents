"""技能域数据访问层 - Skill / SkillReview 查询封装"""
from typing import Optional

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.models.skill import Skill, SkillReview
from platform_core.repository import BaseRepository

# tier 排序权重（S>A>B>C 的字典序与语义序不一致，须显式映射）
_TIER_ORDER = case({"S": 4, "A": 3, "B": 2, "C": 1}, value=Skill.tier)

_SORT_COLUMNS = {
    "score": Skill.score,
    "tier": _TIER_ORDER,
    "updated_at": Skill.updated_at,
    "name": Skill.name,
}


class SkillRepository(BaseRepository[Skill]):
    """技能主表 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(model=Skill, session=session)

    async def get_by_name(self, name: str) -> Optional[Skill]:
        result = await self.session.execute(select(Skill).where(Skill.name == name))
        return result.scalar_one_or_none()

    async def list_skills(
        self,
        q: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        tier: Optional[str] = None,
        source_type: Optional[str] = None,
        industry: Optional[str] = None,
        sort: str = "updated_at",
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Skill], int]:
        stmt = select(Skill)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(Skill.name.like(like), Skill.title.like(like), Skill.description.like(like))
            )
        if category:
            stmt = stmt.where(Skill.category == category)
        if status:
            stmt = stmt.where(Skill.status == status)
        if tier:
            stmt = stmt.where(Skill.tier == tier)
        if source_type:
            stmt = stmt.where(Skill.source_type == source_type)
        if industry:
            stmt = stmt.where(Skill.industries.contains([industry]))

        total = (
            await self.session.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()

        sort_col = _SORT_COLUMNS.get(sort, Skill.updated_at)
        stmt = stmt.order_by(sort_col.desc(), Skill.id.asc()).offset(offset).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), int(total)


class SkillReviewRepository(BaseRepository[SkillReview]):
    """评分历史 Repository"""

    def __init__(self, session: AsyncSession):
        super().__init__(model=SkillReview, session=session)

    async def list_by_skill(self, skill_id: int, limit: int = 20) -> list[SkillReview]:
        stmt = (
            select(SkillReview)
            .where(SkillReview.skill_id == skill_id)
            .order_by(SkillReview.id.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())
