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

    async def activate_exclusive(self, provider_id: int, tenant_id: int | None = None) -> None:
        """单激活互斥热切换（单语句，S1-4 租户内收窄）：目标行置 1、其余置 0

        互斥范围 = 目标行的租户域：
        - tenant_id 非空（租户行）→ 仅该租户内互斥（其余租户激活位不受扰，10.2-B）；
        - tenant_id 为空（平台公共行）→ 仅平台公共域（tenant_id IS NULL）互斥。
        无租户上下文时按目标行自身 tenant_id 分域（读行成本可接受，换取语义确定）。
        """
        if tenant_id is None:
            row = await self.get_by_id(provider_id)
            tenant_id = getattr(row, "tenant_id", None) if row is not None else None
        scope = (
            LlmProvider.tenant_id == tenant_id if tenant_id is not None
            else LlmProvider.tenant_id.is_(None)
        )
        stmt = (
            update(LlmProvider)
            .where(scope)
            .values(is_active=case((LlmProvider.id == provider_id, true()), else_=false()))
            .execution_options(synchronize_session=False)
        )
        await self.session.execute(stmt)

    async def get_max_updated_at(self) -> Optional[datetime]:
        """全表最大 updated_at（供上层缓存失效判断；空表返回 None）"""
        result = await self.session.execute(select(func.max(LlmProvider.updated_at)))
        return result.scalar_one_or_none()
