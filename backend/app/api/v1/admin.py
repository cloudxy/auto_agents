"""管理后台相关接口 —— 只做编排，统计数据通过 SpiderService

鉴权（存量安全漏洞修复）：/admin/* 全部要求登录；用户列表仅管理员。
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import CurrentUser, require_admin, require_login, require_platform_admin
from backend.app.responses import ok
from backend.app.api._helpers import record_audit
from backend.services.audit_service import AuditService
from backend.services.spider_service import SpiderService
from backend.services.user_service import UserService
from platform_core.db import get_async_db

router = APIRouter()


def _service(session: AsyncSession = Depends(get_async_db)) -> SpiderService:
    return SpiderService(session)


def _user_service(session: AsyncSession = Depends(get_async_db)) -> UserService:
    return UserService(session)


def _audit_service(session: AsyncSession = Depends(get_async_db)) -> AuditService:
    return AuditService(session)


@router.get("/stats")
async def get_stats(
    service: SpiderService = Depends(_service),
    _user: CurrentUser = Depends(require_login),
):
    """获取系统统计数据（含运行时长/成功率/近 7 日趋势/爬虫 Top5）"""
    spider_stats = await service.stats()
    return ok(data=spider_stats.model_dump())


@router.get("/users")
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    service: UserService = Depends(_user_service),
    _user: CurrentUser = Depends(require_admin),
):
    """用户列表（用户管理页陈列，不含密码哈希）"""
    data = await service.list_users(skip=skip, limit=limit)
    return ok(data=data.model_dump())


@router.get("/audit-logs")
async def list_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user: Optional[str] = Query(None, max_length=50, description="按操作人用户名过滤"),
    action: Optional[str] = Query(None, max_length=50, description="按操作类型过滤，如 task.run"),
    start_time: Optional[datetime] = Query(None, description="操作时间起（ISO 8601）"),
    end_time: Optional[datetime] = Query(None, description="操作时间止（ISO 8601）"),
    service: AuditService = Depends(_audit_service),
    _user: CurrentUser = Depends(require_admin),
):
    """审计日志分页查询（操作人/操作类型/时间范围过滤；仅管理员）"""
    data = await service.list_logs(
        skip=skip,
        limit=limit,
        action=action,
        user=user,
        start_time=start_time,
        end_time=end_time,
    )
    return ok(data=data.model_dump())


# ---------- SaaS S5-2 平台运营台（平台超管专属） ----------


@router.get("/tenants")
async def list_tenants(
    _user: CurrentUser = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_async_db),
):
    """租户列表（平台超管）"""
    from sqlalchemy import select

    from platform_core.models.tenant import Tenant

    rows = (await session.execute(select(Tenant).order_by(Tenant.id.asc()))).scalars().all()
    return ok(data=[
        {
            "id": r.id, "slug": r.slug, "name": r.name, "status": r.status,
            "quota": r.quota,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ])


@router.patch("/tenants/{tenant_id}")
async def patch_tenant(
    tenant_id: int,
    body: dict,
    user: CurrentUser = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_async_db),
):
    """套餐/配额/到期编辑（平台超管）"""
    from sqlalchemy import select

    from platform_core.exceptions import NotFoundException
    from platform_core.models.tenant import Tenant

    row = (await session.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    if row is None:
        raise NotFoundException(resource=f"租户 {tenant_id}")
    if "quota" in body and isinstance(body["quota"], dict):
        merged = dict(row.quota or {})
        merged.update({k: v for k, v in body["quota"].items() if v is not None})
        row.quota = merged
    if "expires_at" in body:
        from datetime import datetime

        raw = body.get("expires_at")
        if raw:
            row.expires_at = datetime.fromisoformat(str(raw).replace("Z", ""))
        else:
            row.expires_at = None
            row.status = "active"  # 清除到期时间 = 续期恢复
    # status 显式白名单透传（R7：禁用语义不再被挡——body 传 disabled/expired 即生效）
    if "status" in body and str(body["status"]) in ("active", "expired", "disabled"):
        row.status = str(body["status"])
    await session.commit()
    await record_audit(session, user, "tenant.update", f"tenant#{tenant_id}", detail=body)
    return ok(data={"id": tenant_id, "updated": True})
