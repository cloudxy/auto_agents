"""企业自助注册 API（SaaS S5-1）——无鉴权（官网注册页调用）

B1 加固（工单 74-76）：
- Pydantic 请求模型（此前裸 dict 零校验，422 语义缺失）
- 每 IP 限流 fail-closed（无鉴权写面，反滥用优先；策略见 rate_limiter.SIGNUP_RATE_POLICY）
- XFF 取最右可信反代值（首跳可伪造）
"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.rate_limiter import SIGNUP_RATE_POLICY, enforce_request_limit
from backend.app.responses import created
from backend.services.tenant_signup_service import TenantSignupService
from platform_core.db import get_async_db
from platform_core.exceptions import RateLimitException
from platform_core.logger import get_logger
from platform_core.redis_async import get_async_redis

logger = get_logger("api.tenant_signup")

router = APIRouter()


class TenantSignupRequest(BaseModel):
    """企业注册请求（与服务层校验对齐：公司名 ≥2 字符 / 邮箱合法 / 密码 ≥8 位）"""

    company: str = Field(..., min_length=2, max_length=128, description="公司名")
    admin_email: str = Field(..., max_length=100, description="管理员邮箱")
    admin_password: str = Field(..., min_length=8, max_length=128, description="管理员密码（至少 8 位）")

    @field_validator("admin_email")
    @classmethod
    def _email_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("管理员邮箱不合法")
        return v


def _service(session: AsyncSession = Depends(get_async_db)) -> TenantSignupService:
    return TenantSignupService(session)


@router.post("/tenant/signup")
async def tenant_signup(
    body: TenantSignupRequest,
    request: Request,
    service: TenantSignupService = Depends(_service),
):
    """企业注册：公司名 + 管理员邮箱/密码 → tenant + owner（免费档默认配额）

    限流 fail-closed：Redis 故障时拒绝（无鉴权写面不可放行滥用流量）。
    事务由 service 持有（ADR-0007）。
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
    )
    logger.info(f"注册成功 | tenant={result['tenant']['slug']}")
    return created(data=result)
