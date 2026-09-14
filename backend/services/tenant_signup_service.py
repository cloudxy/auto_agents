"""企业自助注册开通服务（SaaS S5-1）

官网无鉴权注册：公司名 + 管理员邮箱/密码 → 创建 tenant（免费档默认配额）+ owner。
注册后即可登录创建第一个采集任务（最短路径）。
GWT-04.4：已有企业成员再提交不得改写他人租户；失败不泄露其它企业是否存在。
"""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.utils.auth import get_password_hash
from platform_core.exceptions import BusinessException, ValidationException
from platform_core.logger import get_logger
from platform_core.models.tenant import Tenant
from platform_core.models.user import User

logger = get_logger("service.tenant_signup")

# 与前端 Register 锁定句同一条：占用/已有成员失败不得改写为「邮箱已注册」或点名企业。
SIGNUP_INCOMPLETE_CODE = "SIGNUP_INCOMPLETE"
SIGNUP_INCOMPLETE_MESSAGE = "注册未完成，请检查填写内容"


def _slugify(name: str) -> str:
    """公司名 → slug（小写/连字符；非法字符压缩）"""
    import re

    slug = re.sub(r"[^a-z0-9\-]+", "-", (name or "").strip().lower()).strip("-")
    return slug or f"tenant-{__import__('time').strftime('%Y%m%d%H%M%S')}"


def _signup_incomplete() -> None:
    """GWT-04.4：通用失败，不泄露其它企业/邮箱是否存在。"""
    raise BusinessException(
        message=SIGNUP_INCOMPLETE_MESSAGE,
        code=SIGNUP_INCOMPLETE_CODE,
        status_code=422,
    )


class TenantSignupService:
    """企业自助注册（session 注入；幂等：邮箱查重；从不 UPDATE 已有 Tenant）"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def signup(
        self,
        company: str,
        admin_email: str,
        admin_password: str,
        actor_tenant_id: int | None = None,
        anonymous_id: str | None = None,
    ) -> dict:
        """注册 → tenant + owner；返回租户与登录所需最小信息

        actor_tenant_id：请求携带有效登录态且已属某企业时拒绝（只读成员不得
        把别人的企业改成新企业）。本方法只 INSERT，不 UPDATE Tenant/User。
        """
        logger.info(f"企业注册 | company={company} email={admin_email}")
        company = (company or "").strip()
        admin_email = (admin_email or "").strip().lower()
        if not company:
            raise ValidationException(message="请填写企业名", field="company")
        if len(company) < 2:
            raise ValidationException(message="企业名至少 2 个字符", field="company")
        if "@" not in admin_email:
            raise ValidationException(message="管理员邮箱不合法", field="admin_email")
        if len(admin_password or "") < 8:
            raise ValidationException(message="密码至少 8 位", field="admin_password")

        if actor_tenant_id is not None:
            logger.warning(f"已有企业成员提交注册被拒 | actor_tenant_id={actor_tenant_id}")
            _signup_incomplete()

        existing = (await self.session.execute(
            select(User.id).where(User.email == admin_email)
        )).scalar_one_or_none()
        if existing is not None:
            logger.warning("注册邮箱占用（不回写占用细节）")
            _signup_incomplete()

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
        try:
            from backend.services.billing_service import BillingService

            await BillingService(self.session).attach_free_plan(int(tenant.id))
        except Exception as exc:  # noqa: BLE001 价目未种子时不阻断注册
            logger.warning(f"挂接免费档失败（忽略）| tenant={tenant.id} err={exc}")
        snapshot = {
            "tenant": {"id": tenant.id, "slug": tenant.slug, "name": tenant.name},
            "owner": {"id": owner.id, "username": owner.username, "email": owner.email},
        }  # 先固化再提交（ADR-0007 D2）
        logger.success(f"企业注册完成 | tenant={slug} owner={owner.username}")
        from backend.services.billing_service import BillingService

        await BillingService(self.session).attach_free_plan(tenant.id)
        from platform_core.models.task_template import TaskTemplate

        self.session.add(TaskTemplate(
            tenant_id=tenant.id,
            name="示例：公开页面采集",
            spider_name="generic",
            params='{"urls":["https://example.com"],"selectors":[{"name":"title","type":"css","expr":"h1::text"}]}',
            priority="normal",
            created_by=owner.username,
        ))
        await self.session.commit()
        await self._emit_signup(snapshot, anonymous_id)
        return snapshot

    async def _emit_signup(self, snapshot: dict, anonymous_id: str | None) -> None:
        logger.info(f"注册成功事件 | tenant={snapshot['tenant']['id']}")
        from backend.services.product_event_service import emit_product_event
        aid = (anonymous_id or "").strip() or None
        await emit_product_event(
            self.session, "tenant_signup_succeeded",
            tenant_id=snapshot["tenant"]["id"],
            actor_user_id=snapshot["owner"]["id"],
            anonymous_id=aid,
            role="admin",
            props={"slug": snapshot["tenant"]["slug"]},
        )

    async def _unique_slug(self, base: str) -> str:
        slug = base
        suffix = 1
        while True:
            taken = (await self.session.execute(
                select(Tenant.id).where(Tenant.slug == slug)
            )).scalar_one_or_none()
            if taken is None:
                return slug
            suffix += 1
            slug = f"{base}-{suffix}"
