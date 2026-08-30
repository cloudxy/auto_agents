"""API 层共享辅助函数

职责：
- 收敛各路由模块重复的横切逻辑（当前仅审计写入），保持 API 层行为一致
"""
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import CurrentUser
from backend.services.audit_service import AuditService


async def record_audit(
    session: AsyncSession,
    user: CurrentUser,
    action: str,
    target: str,
    detail: dict | None = None,
) -> None:
    """写一条审计日志并单独提交（业务事务已在 Service 内提交）"""
    await AuditService(session).record(user.id, user.username, action, target, detail)
    await session.commit()
