"""LLM token 用量数据访问层 - 批量 upsert（MySQL ON DUPLICATE KEY UPDATE 累加）"""
from typing import List

from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.models.llm_token_usage import LlmTokenUsage
from platform_core.repository import BaseRepository

# upsert 必备列（行构造方 llm_usage_service 保证齐全且类型正确）
_UPSERT_COLS = ("prompt_tokens", "completion_tokens", "total_tokens", "request_count", "failed_count")


class LlmTokenUsageRepository(BaseRepository[LlmTokenUsage]):
    """LlmTokenUsage Repository —— 日聚合行的幂等累加写入"""

    def __init__(self, session: AsyncSession):
        super().__init__(model=LlmTokenUsage, session=session)

    async def upsert_daily(self, rows: List[dict]) -> int:
        """批量 upsert 日聚合行：命中唯一键 (provider_name, model, stat_date) 时按列累加

        行结构（由 llm_usage_service.flush 保证）：
        {provider_id, provider_name, model, stat_date,
         prompt_tokens, completion_tokens, total_tokens, request_count, failed_count}
        """
        if not rows:
            return 0
        stmt = mysql_insert(LlmTokenUsage).values(rows)
        update_cols = {
            col: getattr(LlmTokenUsage, col) + getattr(stmt.inserted, col)
            for col in _UPSERT_COLS
        }
        stmt = stmt.on_duplicate_key_update(**update_cols)
        await self.session.execute(stmt)
        return len(rows)
