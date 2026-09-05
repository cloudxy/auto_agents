"""审计服务 - 高危操作留痕 + 查询

约定：
- record() 只插入不提交，随调用方业务事务一起提交
- 审计失败不应阻断业务：由调用方决定是否捕获（本服务内部只记日志）
- record_audit_standalone()（ADR-0007 D4）：独立短事务审计写入——自开 session
  + 自持 commit，API 层审计钩子只做委托，不碰任何 session 生命周期
"""
import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.operation_log_repository import OperationLogRepository
from platform_core.db import get_manager
from platform_core.logger import get_logger
from platform_core.schemas.audit import AuditLogListResponse, AuditLogResponse

logger = get_logger("api")


# （P1-11 / ADR-0007 D4）自开独立 session 写审计并提交——独立于业务事务：
# 审计任何失败只记日志，绝不影响业务事务与响应码；业务回滚也不连带丢审计
# （拒绝/失败操作的留痕价值）。事务所有权在本函数（Service 层），API 审计
# 钩子（api/_helpers.record_audit）仅做委托，不碰 session 生命周期。
async def record_audit_standalone(actor_id: Optional[int], actor_name: str, action: str, target: str, detail: Any = None) -> None:
    logger.info(f"审计独立短事务写入 | actor={actor_name} action={action} target={target}")
    try:
        manager = get_manager()
        async with AsyncSession(manager.async_engines["DEFAULT"]) as audit_session:
            await AuditService(audit_session).record(
                actor_id, actor_name, action, target, detail
            )
            await audit_session.commit()
    except Exception as e:  # noqa: BLE001 审计失败绝不影响业务响应
        logger.error(f"审计写入失败（已忽略，不影响业务）: action={action}, error={e}")


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
