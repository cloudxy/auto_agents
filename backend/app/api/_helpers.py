"""API 层共享辅助函数

职责：
- 收敛各路由模块重复的横切逻辑（当前仅审计写入），保持 API 层行为一致
"""
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import CurrentUser
from backend.services.audit_service import AuditService
from platform_core.db import get_manager
from platform_core.logger import get_logger

# AsyncSession 在此显式绑定（测试经 _helpers.AsyncSession 注入桩）
from sqlalchemy.ext.asyncio import AsyncSession as _AuditSession

logger = get_logger("api")


async def record_audit(
    session: AsyncSession,
    user: CurrentUser,
    action: str,
    target: str,
    detail: dict | None = None,
) -> None:
    """写一条审计日志（P1-11：独立短事务 session）

    旧实现复用业务 session：审计 flush 失败会把 session 打入 PendingRollback，
    随后的无条件 commit 抛 PendingRollbackError → 业务已成功却对用户返回 500
    （并诱发重试造成重复操作）。现改用独立 session + 独立提交：
    - 审计任何失败只记日志，绝不影响业务事务与响应码；
    - session 参数保留以兼容既有调用方签名，实际不再复用业务会话。
    """
    try:
        manager = get_manager()
        async with _AuditSession(manager.async_engines["DEFAULT"]) as audit_session:
            await AuditService(audit_session).record(
                user.id, user.username, action, target, detail
            )
            await audit_session.commit()
    except Exception as e:  # noqa: BLE001 审计失败绝不影响业务响应
        logger.error(f"审计写入失败（已忽略，不影响业务）: action={action}, error={e}")
