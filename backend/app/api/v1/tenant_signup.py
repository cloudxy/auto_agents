"""企业自助注册 API（SaaS S5-1）——无鉴权（官网注册页调用）"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.responses import created
from backend.services.tenant_signup_service import TenantSignupService
from platform_core.db import get_async_db
from platform_core.logger import get_logger

logger = get_logger("api.tenant_signup")

router = APIRouter()


def _service(session: AsyncSession = Depends(get_async_db)) -> TenantSignupService:
    return TenantSignupService(session)


@router.post("/tenant/signup")
async def tenant_signup(
    body: dict,
    service: TenantSignupService = Depends(_service),
    session: AsyncSession = Depends(get_async_db),
):
    """企业注册：公司名 + 管理员邮箱/密码 → tenant + owner（免费档默认配额）"""
    result = await service.signup(
        company=str(body.get("company") or ""),
        admin_email=str(body.get("admin_email") or ""),
        admin_password=str(body.get("admin_password") or ""),
    )
    await session.commit()
    logger.info(f"注册成功 | tenant={result['tenant']['slug']}")
    return created(data=result)
