"""企业自助注册 API（SaaS S5-1）——无鉴权（官网注册页调用）

B1 加固（工单 74-76）：
- Pydantic 请求模型（此前裸 dict 零校验，422 语义缺失）
- 每 IP 限流 fail-closed（无鉴权写面，反滥用优先；策略见 rate_limiter.SIGNUP_RATE_POLICY）
- XFF 取最右可信反代值（首跳可伪造）
"""
from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import _bearer, get_current_user
from backend.app.core.rate_limiter import SIGNUP_RATE_POLICY, enforce_request_limit
from backend.app.responses import created
from backend.services.tenant_signup_service import TenantSignupService
from platform_core.db import get_async_db
from platform_core.exceptions import AuthenticationException, RateLimitException
from platform_core.logger import get_logger
from platform_core.redis_async import get_async_redis

logger = get_logger("api.tenant_signup")

router = APIRouter()


class TenantSignupRequest(BaseModel):
    """企业注册请求（与服务层校验对齐：公司名 ≥2 字符 / 邮箱合法 / 密码 ≥8 位）"""

    company: str = Field(..., min_length=2, max_length=128, description="公司名")
    admin_email: str = Field(..., max_length=100, description="管理员邮箱")
    admin_password: str = Field(..., min_length=8, max_length=128, description="管理员密码（至少 8 位）")
    anonymous_id: str | None = Field(None, max_length=64, description="浏览会话匿名身份")

    @field_validator("admin_email")
    @classmethod
    def _email_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("管理员邮箱不合法")
        return v


def _service(session: AsyncSession = Depends(get_async_db)) -> TenantSignupService:
    return TenantSignupService(session)


async def _actor_tenant_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_async_db),
) -> int | None:
    """可选登录态：已属某企业则把 tenant_id 交给 service 拒绝改写；无效 Token 当匿名。"""
    if credentials is None or not credentials.credentials:
        return None
    try:
        user = await get_current_user(request, credentials, session)
    except AuthenticationException:
        return None
    return user.tenant_id


@router.post("/tenant/signup")
async def tenant_signup(
    body: TenantSignupRequest,
    request: Request,
    service: TenantSignupService = Depends(_service),
    actor_tenant_id: int | None = Depends(_actor_tenant_id),
):
    """企业注册：公司名 + 管理员邮箱/密码 → tenant + owner（免费档默认配额）

    限流 fail-closed：Redis 故障时拒绝（无鉴权写面不可放行滥用流量）。
    事务由 service 持有（ADR-0007）。
    已登录且已有企业的成员（含只读）提交：422 SIGNUP_INCOMPLETE，不改写他人租户。
    """
    try:
        redis = await get_async_redis()
        await enforce_request_limit(redis, SIGNUP_RATE_POLICY, request)
    except RateLimitException:
        raise

    result = await service.signup(
        company=body.company,
        admin_email=body.admin_email,
        admin_password=body.admin_password,
        actor_tenant_id=actor_tenant_id,
        anonymous_id=body.anonymous_id,
    )
    logger.info(f"注册成功 | tenant={result['tenant']['slug']}")
    return created(data=result)
