"""管理后台相关接口 —— 只做编排，统计数据通过 SpiderService

鉴权（存量安全漏洞修复）：/admin/* 全部要求登录；用户列表仅管理员。
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import (
    CurrentUser, require_admin, require_login,
    require_platform_admin, require_platform_admin_or_404,
)
from platform_core.schemas.auth import AdminUserCreateRequest, AdminUserUpdateRequest
from backend.app.responses import ok, created
from backend.app.api._helpers import record_audit
from backend.services.audit_service import AuditService
from backend.services.config_service import ConfigService
from backend.services.spider_service import SpiderService
from backend.services.tenant_admin_service import TenantAdminService
from backend.services.user_service import UserService
from platform_core.db import get_async_db, get_async_readonly_db

router = APIRouter()


def _service(session: AsyncSession = Depends(get_async_db)) -> SpiderService:
    return SpiderService(session)


def _stats_service(session: AsyncSession = Depends(get_async_readonly_db)) -> SpiderService:
    return SpiderService(session)


def _user_service(session: AsyncSession = Depends(get_async_db)) -> UserService:
    return UserService(session)


def _audit_service(session: AsyncSession = Depends(get_async_db)) -> AuditService:
    return AuditService(session)


def _tenant_service(session: AsyncSession = Depends(get_async_db)) -> TenantAdminService:
    return TenantAdminService(session)


def _config_service(session: AsyncSession = Depends(get_async_db)) -> ConfigService:
    return ConfigService(session)


@router.get("/stats")
async def get_stats(
    service: SpiderService = Depends(_stats_service),
    _user: CurrentUser = Depends(require_login),
):
    """获取系统统计数据（含运行时长/成功率/近 7 日趋势/爬虫 Top5）"""
    spider_stats = await service.stats()
    return ok(data=spider_stats.model_dump())


@router.get("/users")
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: str = Query("active", pattern="^(active|deleted|disabled)$",
                        description="active=默认（不含已删）；deleted=已删除；disabled=已停用"),
    q: Optional[str] = Query(None, max_length=50, description="按登录名筛选"),
    service: UserService = Depends(_user_service),
    _user: CurrentUser = Depends(require_platform_admin_or_404),
):
    """用户列表（用户管理页陈列，不含密码哈希；status=deleted 为已删筛选）"""
    data = await service.list_users(skip=skip, limit=limit, status=status, q=q)
    return ok(data=data.model_dump())


@router.post("/users", status_code=201)
async def admin_create_user(
    payload: AdminUserCreateRequest,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
    service: UserService = Depends(_user_service),
):
    """创建账户（平台超管；角色分配 role 单源，归属公司可选）"""
    created = await service.create_user(payload)
    await record_audit(user, "user.create", f"user#{created.id}",
                       detail={"username": created.username, "role": created.role, "tenant_id": created.tenant_id})
    return ok(data=created.model_dump())


@router.patch("/users/{user_id}")
async def admin_update_user(
    user_id: int,
    payload: AdminUserUpdateRequest,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
    service: UserService = Depends(_user_service),
):
    """编辑账户：角色分配/启停/归属调整（防自锁：不可降级/停用/删除自己）"""
    updated = await service.update_user(user_id, payload, actor_id=int(user.id))
    await record_audit(user, "user.update", f"user#{user_id}", detail=payload.model_dump(exclude_unset=True))
    return ok(data=updated.model_dump())


@router.delete("/users/{user_id}")
async def admin_delete_user(
    user_id: int,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
    service: UserService = Depends(_user_service),
):
    """软删除账户（防删自己；防删最后一个平台超管；种子 admin 不可删）"""
    await service.delete_user(user_id, actor_id=int(user.id))
    await record_audit(user, "user.delete", f"user#{user_id}")
    return ok(data={"id": user_id, "deleted": True})


@router.post("/users/{user_id}/restore")
async def admin_restore_user(
    user_id: int,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
    service: UserService = Depends(_user_service),
):
    """恢复软删账户（T-24 / FR-93；仅平台超管，租户直打 404 同形 GWT-93.6）

    占用冲突（username 同租户在册 / email 全局在册）→ 400 中文句；
    重复恢复 no-op（GWT-93.9）；成功上报 user_restored（GWT-92.8）。
    """
    restored = await service.restore_user(user_id, actor_id=int(user.id))
    await record_audit(user, "user.restore", f"user#{user_id}")
    return ok(data=restored.model_dump())


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
    _user: CurrentUser = Depends(require_platform_admin_or_404),
    service: TenantAdminService = Depends(_tenant_service),
):
    """租户列表（平台超管；非超管 404 同形）"""
    return ok(data=await service.list_tenants())


@router.post("/tenants", status_code=201)
async def create_tenant_minimal(
    body: dict,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
    service: TenantAdminService = Depends(_tenant_service),
):
    """新建公司（最小语义：名称+可选 slug；配额/到期走平台运营台编辑；事务由 service 持有 ADR-0007）"""
    result = await service.create_tenant_minimal(
        str(body.get("name") or ""), slug=str(body.get("slug") or "") or None)
    await record_audit(user, "tenant.create", f"tenant#{result['id']}",
                       detail={"name": str(body.get("name") or "").strip(), "slug": result["slug"]})
    return created(data={"id": result["id"], "slug": result["slug"]})


@router.patch("/tenants/{tenant_id}")
async def patch_tenant(
    tenant_id: int,
    body: dict,
    user: CurrentUser = Depends(require_platform_admin_or_404),
    session: AsyncSession = Depends(get_async_db),
    service: TenantAdminService = Depends(_tenant_service),
):
    """名称/套餐/配额/到期编辑（平台超管；改名冲突域与平台租户守卫在 service 单点 T-26/T-27）"""
    await service.patch_tenant(tenant_id, body)
    await record_audit(user, "tenant.update", f"tenant#{tenant_id}", detail=body)
    return ok(data={"id": tenant_id, "updated": True})


class PowerMarketSwitchBody(BaseModel):
    enabled: bool


@router.get("/power-market")
async def get_power_market_switch(
    _user: CurrentUser = Depends(require_platform_admin),
):
    """市场总开关（超管可读；租户公司管理员拒绝且开关不变，GWT-U11.3）。"""
    from backend.services.power_market.flag import is_power_market_enabled

    return ok(data={"enabled": is_power_market_enabled()})


@router.put("/power-market")
async def put_power_market_switch(
    body: PowerMarketSwitchBody,
    user: CurrentUser = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_async_db),
):
    """超管打开/关闭能力市场总开关。yaml 默认 false；本写覆盖运行时。"""
    from backend.services.power_market.flag import set_power_market_enabled

    enabled = set_power_market_enabled(body.enabled)
    await record_audit(user, "power_market.switch", "POWER_MARKET.ENABLED",
        detail={"enabled": enabled},
    )
    return ok(data={"enabled": enabled})


# ---------------- 死信队列（B6 工单 91：排障刚需，admin 专属） ----------------

@router.get("/dead-items")
async def list_dead_items(
    limit: int = 100,
    _user: CurrentUser = Depends(require_admin),
):
    """查看结果回流死信（缺 task_id 等无法归属的载荷留档）"""
    from backend.services.dead_item_service import DeadItemService

    return ok(data=await DeadItemService().list_items(limit=limit))


@router.delete("/dead-items/{index}")
async def discard_dead_item(
    index: int,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
):
    """丢弃单条死信（按队列 index）"""
    from backend.services.dead_item_service import DeadItemService

    removed = await DeadItemService().discard(index)
    if not removed:
        from platform_core.exceptions import NotFoundException

        raise NotFoundException(resource=f"死信 #{index}")
    await record_audit(user, "dead_item.discard", f"dead_item#{index}")
    return ok(data={"index": index, "removed": True})


@router.delete("/dead-items")
async def clear_dead_items(
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
):
    """清空死信队列（排障终态动作）"""
    from backend.services.dead_item_service import DeadItemService

    removed = await DeadItemService().clear()
    await record_audit(user, "dead_item.clear", f"dead_items:{removed}")
    return ok(data={"removed": removed})


# ---------------- 通知渠道配置（B6：webhook/钉钉/企微 URL 运营面可写） ----------------

_NOTIFY_CFG_KEYS = {
    "webhook_url": "notify.webhook_url",
    "dingtalk_url": "notify.dingtalk_webhook_url",
    "wechat_work_url": "notify.wechat_work_webhook_url",
}


@router.get("/notify-config")
async def get_notify_config(
    _user: CurrentUser = Depends(require_admin),
    service: ConfigService = Depends(_config_service),
):
    """通知渠道配置（三渠道 URL；密钥类仍走 env，不入库不入此接口）"""
    stored = await service.get_configs(list(_NOTIFY_CFG_KEYS.values()))
    return ok(data={
        field: stored.get(key) or "" for field, key in _NOTIFY_CFG_KEYS.items()
    })


@router.put("/notify-config")
async def put_notify_config(
    body: dict,
    user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_db),
    service: ConfigService = Depends(_config_service),
):
    """更新通知渠道 URL（空串=清除覆盖，回退 settings 默认）"""
    from platform_core.exceptions import ValidationException

    updates = {}
    for field, key in _NOTIFY_CFG_KEYS.items():
        if field in body:
            value = str(body[field] or "").strip()
            if value and not value.startswith(("http://", "https://")):
                raise ValidationException(message=f"{field} 必须是 http(s) 地址", field=field)
            updates[key] = value
    if not updates:
        raise ValidationException(message="无可更新字段（webhook_url/dingtalk_url/wechat_work_url）")
    await service.upsert_configs(updates, description="通知渠道 URL（运营面配置）")
    await record_audit(user, "notify_config.update", "notify_config",
                       detail={k: (v[:40] + "…") if len(v) > 40 else v for k, v in updates.items()})
    return ok(data={"updated": sorted(updates.keys())})


@router.get("/webhook-status")
async def webhook_status(
    _user: CurrentUser = Depends(require_admin),
):
    """Webhook 配置状态（B6 工单 91）：只读展示，密钥仅回显配置态（布尔）不回显值

    密钥经 env/.env 注入（AUTO_AGENTS_WEBHOOK__SECRET_KEY），刻意不经
    system_configs 落库——API 无法读出明文，仅暴露「已配置/未配置」。
    """
    import os

    from config import settings

    secret = str(settings.get("WEBHOOK.SECRET_KEY", "") or "").strip()
    return ok(data={
        "secret_configured": bool(secret) and secret != "change-me-in-production",
        "notify_webhook_url_configured": bool(str(settings.get("NOTIFY.WEBHOOK_URL", "") or "")),
        "dingtalk_configured": bool(str(settings.get("NOTIFY.DINGTALK.WEBHOOK_URL", "") or "")),
        "wechat_work_configured": bool(str(settings.get("NOTIFY.WECHAT_WORK.WEBHOOK_URL", "") or "")),
        "env_override_active": "AUTO_AGENTS_WEBHOOK__SECRET_KEY" in os.environ,
    })
