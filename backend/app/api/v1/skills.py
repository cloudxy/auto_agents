"""技能管理中心管理端 API（方案 A）

路由注册顺序约束（总方案 3.2-A-5）：静态段（scan/jobs/compare/categories/manifests/
sync-adapters/import-url）必须先于 /{name} 注册，否则被动态段吞掉。
本文件落地：列表 / 详情 / 扫描 / 任务记录；其余静态段随对应工单补充（同样置于 {name} 之前）。
"""
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, require_admin, require_login
from backend.app.responses import ok
from backend.repositories.skill_repository import SkillRepository, SkillReviewRepository
from backend.services.skill_service import SkillService
from platform_core.db import get_async_db
from platform_core.exceptions import NotFoundException
from platform_core.logger import get_logger
from platform_core.models.skill import SkillJob
from platform_core.schemas.skill import (
    SkillDetailResponse,
    SkillListResponse,
    SkillQuery,
    SkillResponse,
    SkillReviewResponse,
)
from sqlalchemy import select

logger = get_logger("api.skills")

router = APIRouter()


def _service(session: AsyncSession = Depends(get_async_db)) -> SkillService:
    return SkillService(session)


def _repo(session: AsyncSession = Depends(get_async_db)) -> SkillRepository:
    return SkillRepository(session)


def _review_repo(session: AsyncSession = Depends(get_async_db)) -> SkillReviewRepository:
    return SkillReviewRepository(session)


# ---------- 静态段（必须先于 /{name}） ----------


@router.post("/scan")
async def scan_skills(
    user: CurrentUser = Depends(require_admin),
    service: SkillService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
):
    """全量/增量扫描 skills-library（admin）"""
    summary = await service.scan_library()
    await session.commit()
    await record_audit(session, user, "skill.scan", "skills", detail={"total": summary["total"]})
    return ok(data=summary)


@router.get("/jobs")
async def list_skill_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(require_login),
    session: AsyncSession = Depends(get_async_db),
):
    """任务运行记录（scan/score_batch/import/export_meta）"""
    from sqlalchemy import func

    total = (await session.execute(select(func.count()).select_from(SkillJob))).scalar_one()
    rows = (
        await session.execute(
            select(SkillJob).order_by(SkillJob.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().all()
    items = [
        {
            "id": r.id, "job_type": r.job_type, "status": r.status,
            "total": r.total or 0, "succeeded": r.succeeded or 0, "failed": r.failed or 0,
            "detail": r.detail, "started_at": r.started_at, "finished_at": r.finished_at,
        }
        for r in rows
    ]
    return ok(data={"total": int(total), "items": items})


# ---------- 动态段 ----------


@router.get("")
async def list_skills(
    q: SkillQuery = Depends(),
    user: CurrentUser = Depends(require_login),
    repo: SkillRepository = Depends(_repo),
):
    """技能库列表（筛选/排序/分页）"""
    rows, total = await repo.list_skills(
        q=q.q, category=q.category, status=q.status, tier=q.tier,
        source_type=q.source_type, industry=q.industry, sort=q.sort,
        offset=(q.page - 1) * q.page_size, limit=q.page_size,
    )
    items = [SkillResponse.model_validate(r).model_dump() for r in rows]
    return ok(data=SkillListResponse(total=total, items=items).model_dump())


@router.get("/{name}")
async def get_skill_detail(
    name: str,
    user: CurrentUser = Depends(require_login),
    repo: SkillRepository = Depends(_repo),
    review_repo: SkillReviewRepository = Depends(_review_repo),
):
    """技能详情：治理字段 + SKILL.md 正文只读 + meta.yaml 原文 + 最近评分历史"""
    row = await repo.get_by_name(name)
    if not row:
        raise NotFoundException(resource=f"技能 {name}")

    reviews = await review_repo.list_by_skill(row.id, limit=20)
    detail = SkillDetailResponse.model_validate(row)
    detail.skill_md, detail.meta_yaml = _read_skill_files(row.file_path)
    detail.reviews = [SkillReviewResponse.model_validate(rv) for rv in reviews]
    return ok(data=detail.model_dump())


def _read_skill_files(file_path: str) -> tuple[str, str]:
    """读技能目录的 SKILL.md 与 meta.yaml 原文（缺失容忍为空串）"""
    from config import settings

    library_root = Path(str(settings.get("SKILLS.LIBRARY_ROOT", "skills-library")))
    skill_dir = library_root / file_path
    skill_md = meta_yaml = ""
    try:
        md_path = skill_dir / "SKILL.md"
        meta_path = skill_dir / "meta.yaml"
        if md_path.exists():
            skill_md = md_path.read_text(encoding="utf-8")
        if meta_path.exists():
            meta_yaml = meta_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning(f"技能文件读取失败 | path={skill_dir} err={exc}")
    return skill_md, meta_yaml
