"""LLM 供应商数据访问层 - 封装所有 LlmProvider 相关的数据库操作（阶段二）"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import case, false, func, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.models.llm_provider import LlmProvider
from platform_core.repository import BaseRepository


class LlmProviderRepository(BaseRepository[LlmProvider]):
    """LlmProvider Repository —— 多供应商注册表的 DB 数据源（单激活互斥）"""

    def __init__(self, session: AsyncSession):
        super().__init__(model=LlmProvider, session=session)

    async def get_by_name(self, name: str) -> Optional[LlmProvider]:
        """按名称查询（唯一性校验）"""
        result = await self.session.execute(select(LlmProvider).where(LlmProvider.name == name))
        return result.scalar_one_or_none()

    async def list_providers(self) -> List[LlmProvider]:
        """全量列表（id 倒序：新供应商优先；激活位随行返回；量级小无分页）"""
        stmt = select(LlmProvider).order_by(LlmProvider.id.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active(self) -> Optional[LlmProvider]:
        """当前激活行（全表至多一行；无激活行返回 None，调用方走 yml/env 兜底）"""
        result = await self.session.execute(select(LlmProvider).where(LlmProvider.is_active == true()))
        return result.scalar_one_or_none()

    async def activate_exclusive(self, provider_id: int) -> None:
        """单激活互斥热切换（单语句）：目标行置 1、其余全部置 0

        UPDATE llm_providers SET is_active = CASE WHEN id = :id THEN 1 ELSE 0 END
        无 WHERE 全表扫描置位，数据库行级原子性保证并发激活下也至多一行 active；
        MySQL 默认 rowcount 语义为「变更行数」（值未变的行不计），故此处不依赖
        rowcount 判定成败，存在性校验由调用方完成。
        """
        stmt = (
            update(LlmProvider)
            .values(is_active=case((LlmProvider.id == provider_id, true()), else_=false()))
            .execution_options(synchronize_session=False)
        )
        await self.session.execute(stmt)

    async def get_max_updated_at(self) -> Optional[datetime]:
        """全表最大 updated_at（供上层缓存失效判断；空表返回 None）"""
        result = await self.session.execute(select(func.max(LlmProvider.updated_at)))
        return result.scalar_one_or_none()
