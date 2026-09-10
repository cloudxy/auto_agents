"""告警规则数据访问层"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.models.alert_rule import AlertRule
from platform_core.repository import BaseRepository


class AlertRuleRepository(BaseRepository[AlertRule]):
    """AlertRule Repository —— 告警规则的 CRUD 操作"""

    def __init__(self, session: AsyncSession):
        super().__init__(model=AlertRule, session=session)

    async def list_all(self, enabled_only: bool = False) -> List[AlertRule]:
        """获取所有规则（可选仅启用的）"""
        stmt = select(AlertRule)
        if enabled_only:
            stmt = stmt.where(AlertRule.enabled == True)  # noqa: E712
        stmt = stmt.order_by(AlertRule.id.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_active(self) -> List[AlertRule]:
        """返回 enabled=True 的规则列表"""
        return await self.list_all(enabled_only=True)

    async def get_by_id(self, rule_id: int) -> Optional[AlertRule]:
        """根据 ID 获取规则"""
        return await super().get_by_id(rule_id)
