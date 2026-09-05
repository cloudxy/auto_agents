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

    async def get_configs(self, keys: list[str]) -> dict[str, str]:
        """按键集合批量读取配置项（miss 的键不出现在返回值中）

        T1 收口（R7）：backend/app/api/v1/admin.py 此前函数内延迟 import
        SystemConfig 直查；通知渠道配置读取收口至本方法。
        """
        from sqlalchemy import select

        logger.info(f"批量读取配置 | keys={keys}")
        rows = (await self.session.execute(
            select(SystemConfig.config_key, SystemConfig.config_value)
            .where(SystemConfig.config_key.in_(keys))
        )).all()
        return dict(rows)

    async def upsert_configs(self, updates: dict[str, str], description: str = "") -> None:
        """批量写入配置项（存在则改、缺省则建；不提交——commit 由调用方统一执行）"""
        from sqlalchemy import select

        logger.info(f"批量写入配置 | keys={sorted(updates.keys())}")
        for key, value in updates.items():
            row = (await self.session.execute(
                select(SystemConfig).where(SystemConfig.config_key == key)
            )).scalar_one_or_none()
            if row is None:
                self.session.add(SystemConfig(config_key=key, config_value=value,
                                              description=description))
            else:
                row.config_value = value
