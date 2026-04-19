"""系统配置接口 - 管理网站基础信息"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from backend.services.config_service import ConfigService
from platform_core.db import get_async_db

router = APIRouter()

@router.get("/")
async def get_configs(session: AsyncSession = Depends(get_async_db)):
    """获取所有系统配置"""
    service = ConfigService(session)
    return await service.get_all_configs()

from pydantic import BaseModel

class ConfigUpdate(BaseModel):
    value: str

@router.put("/{key}")
async def update_config(key: str, data: ConfigUpdate, session: AsyncSession = Depends(get_async_db)):
    """更新单个配置项"""
    service = ConfigService(session)
    await service.set_config(key, data.value)
    return {"message": "Config updated"}
