"""企业自助注册开通服务（SaaS S5-1）

官网无鉴权注册：公司名 + 管理员邮箱/密码 → 创建 tenant（免费档默认配额）+ owner。
注册后即可登录创建第一个采集任务（最短路径）。
"""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.utils.auth import get_password_hash
from platform_core.exceptions import ValidationException
from platform_core.logger import get_logger
from platform_core.models.tenant import Tenant
from platform_core.models.user import User

logger = get_logger("service.tenant_signup")


def _slugify(name: str) -> str:
    """公司名 → slug（小写/连字符；非法字符压缩）"""
    import re

    slug = re.sub(r"[^a-z0-9\-]+", "-", (name or "").strip().lower()).strip("-")
    return slug or f"tenant-{__import__('time').strftime('%Y%m%d%H%M%S')}"


class TenantSignupService:
    """企业自助注册（session 注入；幂等：邮箱查重）"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def signup(self, company: str, admin_email: str, admin_password: str) -> dict:
        """注册 → tenant + owner；返回租户与登录所需最小信息"""
        logger.info(f"企业注册 | company={company} email={admin_email}")
        company = (company or "").strip()
        admin_email = (admin_email or "").strip().lower()
        if not company or len(company) < 2:
            raise ValidationException(message="公司名至少 2 个字符", field="company")
        if "@" not in admin_email:
            raise ValidationException(message="管理员邮箱不合法", field="admin_email")
        if len(admin_password or "") < 8:
            raise ValidationException(message="密码至少 8 位", field="admin_password")

        existing = (await self.session.execute(
            select(User).where(User.email == admin_email)
        )).scalar_one_or_none()
        if existing is not None:
            raise ValidationException(
                message=f"邮箱已注册: {admin_email}（如需加入企业请联系该企业管理员）",
                field="admin_email",
            )

        slug = await self._unique_slug(_slugify(company))
        tenant = Tenant(slug=slug, name=company, status="active", quota=None)  # 免费档=默认配额
        self.session.add(tenant)
        await self.session.flush()

        owner = User(
            username=admin_email.split("@")[0][:48] or f"owner-{tenant.id}",
            email=admin_email,
            password_hash=await asyncio.to_thread(get_password_hash, admin_password),
            role="admin", tenant_id=tenant.id, tenant_role="owner",
            is_active=True, is_platform_admin=False,
        )
        self.session.add(owner)
        await self.session.flush()
        logger.success(f"企业注册完成 | tenant={slug} owner={owner.username}")
        return {
            "tenant": {"id": tenant.id, "slug": tenant.slug, "name": tenant.name},
            "owner": {"id": owner.id, "username": owner.username, "email": owner.email},
        }

    async def _unique_slug(self, base: str) -> str:
        slug = base
        suffix = 1
        while True:
            taken = (await self.session.execute(
                select(Tenant).where(Tenant.slug == slug)
            )).scalar_one_or_none()
            if taken is None:
                return slug
            suffix += 1
            slug = f"{base}-{suffix}"
