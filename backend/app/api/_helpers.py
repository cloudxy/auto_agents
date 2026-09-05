"""API 层共享辅助函数

职责：
- 收敛各路由模块重复的横切逻辑（当前仅审计写入），保持 API 层行为一致
- ADR-0007 D4：本函数是纯委托——审计的独立 session 开启与提交归属
  backend/services/audit_service.record_audit_standalone（Service 层），
  API 层不碰任何 session 生命周期
"""
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import CurrentUser
from backend.services.audit_service import record_audit_standalone
from platform_core.logger import get_logger

logger = get_logger("api")


async def record_audit(
    session: AsyncSession,
    user: CurrentUser,
    action: str,
    target: str,
    detail: dict | None = None,
) -> None:
    """写一条审计日志（独立短事务，P1-11 口径不变）

    审计与业务不同事务：审计失败只记日志，绝不影响业务事务与响应码；
    业务回滚不连带丢审计。session 形参保留以兼容既有调用方签名与测试
    patch 面，实际不使用（后续机械工单可移除）。
    """
    await record_audit_standalone(
        user.id, user.username, action, target, detail
    )
