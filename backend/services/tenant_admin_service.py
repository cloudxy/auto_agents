"""平台运营台租户管理服务（SaaS S5-2，平台超管专属）

T1 收口（R7）：backend/app/api/v1/admin.py 此前在路由层直连 Tenant/SystemConfig
ORM（含函数内延迟 import）。本服务承接平台运营台的租户数据访问与编辑规则，
对上只暴露 dict 快照。

事务约定（ADR-0007）：service 方法边界 = 业务不可分割操作，写方法尾部自持 commit
并回传 dict 快照（snapshot-before-commit，防 expire_on_commit 惰性加载）。
"""
import re
import time
from datetime import datetime
from unicodedata import normalize

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.exceptions import NotFoundException, ValidationException
from platform_core.logger import get_logger
from platform_core.models.tenant import Tenant

logger = get_logger("service.tenant_admin")


def _slugify(name: str) -> str:
    """公司名 → slug（NFKD 归一化 + 小写 + 非法字符压缩；空则时间戳兜底）"""
    slug = re.sub(
        r"[^a-z0-9]+", "-",
        normalize("NFKD", name).encode("ascii", "ignore").decode().lower()).strip("-")
    return slug or f"co-{int(time.time()) % 100000}"


class TenantAdminService:
    """租户运营编排（session 注入；调用方保证平台超管权限）"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_tenants(self) -> list[dict]:
        """租户列表（按 id 升序）"""
        logger.info("查询租户列表")
        rows = (await self.session.execute(select(Tenant).order_by(Tenant.id.asc()))).scalars().all()
        return [
            {
                "id": r.id, "slug": r.slug, "name": r.name, "status": r.status,
                "quota": r.quota,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    async def create_tenant_minimal(self, name: str, slug: str | None = None) -> dict:
        """新建公司（最小语义：名称+可选 slug；配额/到期走平台运营台编辑）

        slug 冲突自动追加时间后缀（容错建号，不因撞名阻断）。
        """
        logger.info(f"创建租户 | name={name}")
        name = str(name or "").strip()
        if len(name) < 2:
            raise ValidationException(message="公司名至少 2 个字符", field="name")
        slug = str(slug or "").strip() or _slugify(name)
        dup = (await self.session.execute(
            select(Tenant).where(Tenant.slug == slug)
        )).scalar_one_or_none()
        if dup is not None:
            slug = f"{slug}-{int(time.time()) % 10000}"
        row = Tenant(slug=slug, name=name, status="active", quota=None)
        self.session.add(row)
        await self.session.flush()
        snapshot = {"id": int(row.id), "slug": slug}  # 先固化再提交（ADR-0007 D2）
        await self.session.commit()
        return snapshot

    async def patch_tenant(self, tenant_id: int, body: dict) -> None:
        """套餐/配额/到期编辑（quota 深合并；清到期=续期恢复；status 白名单透传）"""
        logger.info(f"更新租户 | tenant={tenant_id} fields={sorted(body.keys())}")
        row = (await self.session.execute(
            select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
        if row is None:
            raise NotFoundException(resource=f"租户 {tenant_id}")
        if "quota" in body and isinstance(body["quota"], dict):
            merged = dict(row.quota or {})
            merged.update({k: v for k, v in body["quota"].items() if v is not None})
            row.quota = merged
        if "expires_at" in body:
            raw = body.get("expires_at")
            if raw:
                row.expires_at = datetime.fromisoformat(str(raw).replace("Z", ""))
            else:
                row.expires_at = None
                row.status = "active"  # 清除到期时间 = 续期恢复
        # status 显式白名单透传（R7：禁用语义不再被挡——body 传 disabled/expired 即生效）
        if "status" in body and str(body["status"]) in ("active", "expired", "disabled"):
            row.status = str(body["status"])
        await self.session.commit()
