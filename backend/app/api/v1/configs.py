"""系统配置接口 - 管理网站基础信息（读需登录，写仅管理员）"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser, require_admin, require_login
from backend.services.config_service import ConfigService
from platform_core.db import get_async_db

router = APIRouter()

@router.get("/")
async def get_configs(
    session: AsyncSession = Depends(get_async_db),
    _user: CurrentUser = Depends(require_login),
):
    """获取所有系统配置"""
    service = ConfigService(session)
    return await service.get_all_configs()


class ConfigUpdate(BaseModel):
    value: str

@router.put("/{key}")
async def update_config(
    key: str,
    data: ConfigUpdate,
    session: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(require_admin),
):
    """更新单个配置项（仅管理员，写入审计；set_config 内部已提交业务事务，
    审计记录由 record_audit 单独提交）"""
    service = ConfigService(session)
    await service.set_config(key, data.value)
    await record_audit(session, user, "config.update", key)
    return {"message": "Config updated"}
