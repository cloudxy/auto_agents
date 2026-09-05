"""系统配置接口 - 管理网站基础信息（读需登录，写仅管理员）

响应契约：统一 ApiResponse 信封（ADR-001）。
"""
from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, require_admin, require_login
from backend.app.responses import ApiResponse, ok, updated
from backend.services.config_service import ConfigService
from platform_core.db import get_async_db

router = APIRouter()


@router.get("/", response_model=ApiResponse[dict])
async def get_configs(
    session: AsyncSession = Depends(get_async_db),
    _user: CurrentUser = Depends(require_login),
) -> ApiResponse[dict]:
    """获取所有系统配置（信封 data 为 {key: value} 字典）"""
    service = ConfigService(session)
    return ok(await service.get_all_configs())


class ConfigUpdate(BaseModel):
    value: str

# key 契约对齐 SystemConfig.config_key String(50)：长度 ≤50；
# 格式按存量键形态（site.name / site_url / notify.webhook_url）收敛为
# 小写字母数字 + . / _ 分隔（B5 修复 F-B1b-02：界外 key 应 422 而非落库后
# 在 MySQL 严格模式下 DataError→500）
_CONFIG_KEY_PATTERN = r"^[a-z0-9][a-z0-9_.]*$"

@router.put("/{key}", response_model=ApiResponse)
async def update_config(
    key: str = Path(..., min_length=1, max_length=50, pattern=_CONFIG_KEY_PATTERN,
                    description="配置键：小写字母数字 + . / _ 分隔，≤50 字符"),
    data: ConfigUpdate = ...,
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
) -> ApiResponse:
    """更新单个配置项（仅管理员，写入审计；set_config 内部已提交业务事务，
    审计记录由 record_audit 单独提交）"""
    service = ConfigService(session)
    await service.set_config(key, data.value)
    await record_audit(session, user, "config.update", key)
    return updated(message=f"配置 {key} 已更新")
