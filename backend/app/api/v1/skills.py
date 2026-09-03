"""技能管理中心管理端 API（方案 A）

路由注册顺序约束（总方案 3.2-A-5）：静态段（scan/jobs/similar-suggest/similar-confirm/candidates/manifests/
sync-adapters/import-url）必须先于 /{name} 注册，否则被动态段吞掉。
本文件落地：列表 / 详情 / 扫描 / 任务记录；其余静态段随对应工单补充（同样置于 {name} 之前）。
"""
from pathlib import Path
from backend.app.core.config_consts import (SKILLS_LIBRARY_ROOT)

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, require_admin, require_login, require_operator
from backend.app.responses import ok
from backend.repositories.skill_repository import SkillRepository, SkillReviewRepository
from backend.services.skill_service import SkillService
from platform_core.db import get_async_db
from platform_core.exceptions import NotFoundException, ValidationException
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
    """全量/增量扫描 capability-library（admin）"""
    summary = await service.scan_library()
    await session.commit()
    await record_audit(session, user, "skill.scan", "skills", detail={"total": summary["total"]})
    return ok(data=summary)


@router.post("/import-url")
async def import_skill_from_url(
    body: dict,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
):
    """URL 导入（admin）：GitHub 子目录 / raw 文件 / zip（安全边界见 skill_import_service）"""
    from backend.services.skill_import_service import SkillImportService

    url = str(body.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ValidationException(message="url 必须是 http(s) 地址", field="url")
    result = await SkillImportService(session).import_url(
        url,
        category=body.get("category"),
        industries=body.get("industries"),
    )
    await session.commit()
    await record_audit(session, user, "skill.import", f"skill#{result['name']}", detail={"url": url})
    return ok(data=result)


@router.get("/manifests")
async def get_manifests(
    user: CurrentUser = Depends(require_login),
    service: SkillService = Depends(_service),
):
    """启用矩阵读取（tool → 已启用技能名列表）"""
    return ok(data=await service.list_manifests())


@router.put("/manifests")
async def put_manifest(
    body: dict,
    user: CurrentUser = Depends(require_admin),
    service: SkillService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
):
    """启用矩阵写入（保留 `- name` 行格式与注释头，adapters 零改动）"""
    result = await service.update_manifest(str(body.get("tool") or ""), list(body.get("names") or []))
    await record_audit(session, user, "skill.manifest.update", f"manifest#{result['tool']}")
    return ok(data=result)


@router.post("/sync-adapters")
async def sync_adapters(
    user: CurrentUser = Depends(require_admin),
    service: SkillService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
):
    """触发 sync.sh 分发（受 SKILLS.ADAPTER_SYNC.ENABLED 开关约束）"""
    result = await service.sync_adapters()
    await record_audit(session, user, "skill.adapters.sync", "adapters", detail={"ok": result["ok"]})
    return ok(data=result)


@router.post("/similar-suggest")
async def similar_suggest(
    user: CurrentUser = Depends(require_admin),
    service: SkillService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
):
    """AI 辅助同类候选（建议区，不动 similar_to；确认走 similar-confirm）"""
    result = await service.similar_suggest()
    await session.commit()
    await record_audit(session, user, "skill.similar.suggest", "skills")
    return ok(data=result)


@router.put("/similar-confirm")
async def similar_confirm(
    body: dict,
    user: CurrentUser = Depends(require_admin),
    service: SkillService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
):
    """人工确认等价簇 → 互写 similar_to"""
    groups = [g for g in (body.get("groups") or []) if isinstance(g, list) and len(g) >= 2]
    result = await service.similar_confirm(groups)
    await session.commit()
    await record_audit(session, user, "skill.similar.confirm", "skills", detail={"groups": len(groups)})
    return ok(data=result)


@router.get("/candidates")
async def list_skill_candidates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(require_login),
    service: SkillService = Depends(_service),
):
    """市场采集候选（待人工审核转正）"""
    return ok(data=await service.list_candidates(page, page_size))


@router.post("/candidates/{result_id}/approve")
async def approve_skill_candidate(
    result_id: int,
    user: CurrentUser = Depends(require_admin),
    service: SkillService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
):
    """候选转正：走 import-url 正式管线（人工闸门）"""
    result = await service.approve_candidate(result_id)
    await session.commit()
    await record_audit(session, user, "skill.candidate.approve", f"candidate#{result_id}")
    return ok(data=result)


@router.post("/candidates/{result_id}/reject")
async def reject_skill_candidate(
    result_id: int,
    user: CurrentUser = Depends(require_admin),
    service: SkillService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
):
    """候选拒绝：标记已审；同名已入库技能置 blacklist"""
    result = await service.reject_candidate(result_id)
    await session.commit()
    await record_audit(session, user, "skill.candidate.reject", f"candidate#{result_id}")
    return ok(data=result)


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


@router.post("/{name}/rescore")
async def rescore_skill(
    name: str,
    user: CurrentUser = Depends(require_operator),
    session: AsyncSession = Depends(get_async_db),
):
    """手动触发 AI 重评（入队；评分由后台 worker 消费）"""
    from backend.services.skill_scoring_service import SkillScoringService

    repo = SkillRepository(session)
    if not await repo.get_by_name(name):
        raise NotFoundException(resource=f"技能 {name}")
    queued = await SkillScoringService.enqueue_rescore(name)
    await record_audit(session, user, "skill.rescore", f"skill#{name}")
    return ok(data={"name": name, "queued": queued})


@router.put("/{name}/meta")
async def correct_skill_meta(
    name: str,
    body: dict,
    user: CurrentUser = Depends(require_operator),
    service: SkillService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
):
    """人工矫正（operator）：落 DB + 写回 meta.yaml + CHANGELOG + skill_reviews(human)"""
    allowed = {
        "category", "industries", "status", "similar_to",
        "score", "rubric_human", "review_notes",
    }
    payload = {k: v for k, v in body.items() if k in allowed}
    if not payload:
        raise ValidationException(message="无可矫正字段", field="url")
    result = await service.correct_meta(name, reviewer=user.username, payload=payload)
    await session.commit()
    await record_audit(session, user, "skill.correct", f"skill#{name}", detail=payload)
    return ok(data=result)


@router.post("/{name}/export-meta")
async def export_skill_meta(
    name: str,
    user: CurrentUser = Depends(require_operator),
    service: SkillService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
):
    """手动补导出 meta.yaml（写回失败后的恢复路径）"""
    done = await service.export_meta(name)
    await session.commit()
    await record_audit(session, user, "skill.export_meta", f"skill#{name}")
    return ok(data={"name": name, "written_back": done})


@router.get("/{name}/check-update")
async def check_skill_update(
    name: str,
    user: CurrentUser = Depends(require_operator),
    session: AsyncSession = Depends(get_async_db),
):
    """只读检查来源更新（哈希比对，不自动覆盖——手动更新走 git）"""
    from backend.services.skill_import_service import SkillImportService

    data = await SkillImportService(session).check_update(name)
    return ok(data=data)


def _read_skill_files(file_path: str) -> tuple[str, str]:
    """读技能目录的 SKILL.md 与 meta.yaml 原文（缺失容忍为空串）"""
    from config import settings

    library_root = Path(str(settings.get("SKILLS.LIBRARY_ROOT", SKILLS_LIBRARY_ROOT)))
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
