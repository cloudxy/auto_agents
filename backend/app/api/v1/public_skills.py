"""官网技能广场公开 API（方案 A · A-P4-1）——无鉴权，三道闸缺一不可

1. 仅发布态：status ∈ {stable, recommended}；
2. 字段白名单：PublicSkillResponse 只含展示字段（评审笔记/同步状态/文件路径等内部字段不出协议）；
3. 按 IP 限流：Redis 原子计数（键契约见 queues.SKILL_PUBLIC_RATE_PREFIX），超限 429。

不复用 external_api 的 X-API-Key 体系（Key 不能嵌进官网前端）。
"""
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from backend.app.responses import ok
from backend.repositories.skill_repository import SkillRepository
from platform_core.db import get_async_db
from platform_core.exceptions import NotFoundException, RateLimitException
from platform_core.logger import get_logger
from platform_core.models.skill import Skill
from platform_core.queues import SKILL_PUBLIC_RATE_PREFIX
from platform_core.redis_async import get_async_redis
from platform_core.schemas.skill import SkillQuery
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

logger = get_logger("api.public_skills")

PUBLISHED_STATUSES = ("stable", "recommended")

router = APIRouter()


class PublicSkillResponse(BaseModel):
    """字段白名单（第二道闸）：仅展示字段——新增内部字段不会经此泄漏"""

    model_config = ConfigDict(from_attributes=True)

    name: str
    title: str = ""
    description: Optional[str] = None
    category: str
    industries: Optional[list[str]] = None
    tier: Optional[str] = None
    score: Optional[float] = None
    status: str
    source_url: str = ""
    source_author: str = ""
    updated_at: Optional[datetime] = None
    skill_md: Optional[str] = None


class PublicSkillListResponse(BaseModel):
    total: int
    items: list[PublicSkillResponse]


def _repo(session: AsyncSession = Depends(get_async_db)) -> SkillRepository:
    return SkillRepository(session)


def _client_ip(request: Request) -> str:
    """直连取 client.host；反代后取 X-Forwarded-For 首跳（部署侧保证头可信）"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _enforce_rate_limit(request: Request) -> None:
    """第三道闸：按 IP 每分钟计数（Redis INCR + EXPIRE 原子窗口）"""
    from config import settings

    limit = int(settings.get("SKILLS.PUBLIC_API.RATE_LIMIT_PER_MIN", 60) or 60)
    if limit <= 0:
        return
    try:
        redis = await get_async_redis()
        key = f"{SKILL_PUBLIC_RATE_PREFIX}{_client_ip(request)}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
        if count > limit:
            raise RateLimitException(message=f"请求过于频繁（限 {limit} 次/分钟），请稍后再试")
    except RateLimitException:
        raise
    except Exception as exc:  # noqa: BLE001 Redis 故障 fail-open（公开只读面保可用性）
        logger.warning(f"公开 API 限流检查失败（放行）: {exc}")


def _read_skill_md(row: Skill) -> str:
    from pathlib import Path

    from config import settings

    md = Path(str(settings.get("SKILLS.LIBRARY_ROOT", "capability-library"))) / row.file_path / "SKILL.md"
    try:
        return md.read_text(encoding="utf-8") if md.exists() else ""
    except OSError:
        return ""


def _to_public(row: Skill, include_body: bool = False) -> PublicSkillResponse:
    item = PublicSkillResponse.model_validate(row)
    if include_body:
        item.skill_md = _read_skill_md(row)
    return item


@router.get("/skills")
async def public_list_skills(
    request: Request,
    q: SkillQuery = Depends(),
    repo: SkillRepository = Depends(_repo),
):
    """公开列表：仅发布态 + 白名单投影 + 按 IP 限流"""
    await _enforce_rate_limit(request)
    rows, total = await repo.list_skills(
        q=q.q, category=q.category, industry=q.industry, sort=q.sort,
        offset=(q.page - 1) * q.page_size, limit=q.page_size,
        status=None,
    )
    published = [r for r in rows if r.status in PUBLISHED_STATUSES]
    return ok(
        data=PublicSkillListResponse(
            total=len(published), items=[_to_public(r) for r in published]
        ).model_dump(mode="json")
    )


@router.get("/skills/{name}")
async def public_get_skill(
    name: str,
    request: Request,
    repo: SkillRepository = Depends(_repo),
):
    """公开详情：未发布一律 404（不泄露存在性差异）"""
    await _enforce_rate_limit(request)
    row = await repo.get_by_name(name)
    if row is None or row.status not in PUBLISHED_STATUSES:
        raise NotFoundException(resource="技能")
    return ok(data=_to_public(row, include_body=True).model_dump())


# ---------- P6 C9：公开能力广场（四类资产白名单投影） ----------

_PUBLIC_ASSET_FIELDS = {
    "name", "title", "description", "category", "tier", "score",
    "status", "source_url", "source_author", "updated_at", "asset_type",
}


@router.get("/capabilities")
async def public_list_capabilities(
    request: Request,
    type: str = "skill",
    category: str = None,
    page: int = 1,
    page_size: int = 20,
    session: AsyncSession = Depends(get_async_db),
):
    """官网能力广场：四类资产公开列表（仅发布态 + 白名单投影 + IP 限流）"""
    from backend.services.capability_service import CapabilityService

    await _enforce_rate_limit(request)
    if type not in ("skill", "plugin", "expert", "expert_team"):
        type = "skill"
    svc = CapabilityService(session)
    rows, total = await svc.list_assets(
        asset_type=type, category=category, status="stable",
        offset=(page - 1) * page_size, limit=page_size,
    )

    items = []
    for r in rows:
        item = {f: getattr(r, f) for f in _PUBLIC_ASSET_FIELDS if hasattr(r, f)}
        item["updated_at"] = r.updated_at.isoformat() if r.updated_at else None
        item["score"] = float(r.score) if r.score is not None else None
        items.append(item)
    return ok(data={"total": total, "items": items})
