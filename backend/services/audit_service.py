"""审计服务 - 高危操作留痕 + 查询

约定：
- record() 只插入不提交，随调用方业务事务一起提交
- 审计失败不应阻断业务：由调用方决定是否捕获（本服务内部只记日志）
"""
import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.operation_log_repository import OperationLogRepository
from platform_core.logger import get_logger
from platform_core.schemas.audit import AuditLogListResponse, AuditLogResponse

logger = get_logger("api")


class AuditService:
    """操作审计编排"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = OperationLogRepository(session)

    async def record(
        self,
        actor_id: Optional[int],
        actor_name: str,
        action: str,
        target: str,
        detail: Optional[Any] = None,
    ) -> None:
        """记录一条审计日志（detail 自动序列化为 JSON 串）"""
        logger.info(f"审计记录 | actor={actor_name} action={action} target={target}")
        try:
            detail_str = json.dumps(detail, ensure_ascii=False) if detail is not None else None
            await self.repo.create(
                actor_id=actor_id,
                actor_name=actor_name,
                action=action,
                target=target,
                detail=detail_str,
            )
        except Exception as e:
            # 审计失败仅记日志，不阻断主流程
            logger.error(f"审计记录失败（已忽略）: {e}")

    async def list_logs(
        self,
        skip: int = 0,
        limit: int = 20,
        action: Optional[str] = None,
        user: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> AuditLogListResponse:
        """分页查询审计日志（可按操作类型/操作人/时间范围过滤，供 /admin/audit-logs）"""
        logger.info(
            f"查询审计日志: user={user}, action={action}, "
            f"start={start_time}, end={end_time}, skip={skip}, limit={limit}"
        )
        items = await self.repo.list_logs(
            skip=skip, limit=limit, action=action,
            user=user, start_time=start_time, end_time=end_time,
        )
        total = await self.repo.count_logs(
            action=action, user=user, start_time=start_time, end_time=end_time
        )
        return AuditLogListResponse(
            total=total,
            items=[AuditLogResponse.model_validate(item) for item in items],
        )
