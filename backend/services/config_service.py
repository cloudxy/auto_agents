"""系统配置服务 - 管理网站基础信息"""
from sqlalchemy.ext.asyncio import AsyncSession
from platform_core.models.system_config import SystemConfig
from platform_core.repository import BaseRepository
from platform_core.logger import get_logger

logger = get_logger("api")

class ConfigService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = BaseRepository(SystemConfig, session)

    async def get_config(self, key: str) -> str:
        """获取单个配置项"""
        from sqlalchemy import select
        result = await self.session.execute(
            select(SystemConfig).filter_by(config_key=key)
        )
        config = result.scalar_one_or_none()
        return config.config_value if config else ""

    async def set_config(self, key: str, value: str, description: str = ""):
        """设置配置项（不存在则创建）"""
        from sqlalchemy import select
        result = await self.session.execute(
            select(SystemConfig).filter_by(config_key=key)
        )
        config = result.scalar_one_or_none()
        
        if config:
            config.config_value = value
        else:
            config = SystemConfig(config_key=key, config_value=value, description=description)
            self.session.add(config)
        
        await self.session.commit()
        logger.info(f"系统配置更新: {key}")

    async def get_all_configs(self) -> dict:
        """获取所有配置并转为字典"""
        result = await self.repo.get_all(limit=1000)
        return {c.config_key: c.config_value for c in result}
