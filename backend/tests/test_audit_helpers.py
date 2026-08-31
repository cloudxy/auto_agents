"""审计独立 session 单测（P1-11：审计故障绝不影响业务事务与响应码）"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import backend.app.api._helpers as helpers
from backend.app.api._helpers import record_audit
from backend.app.api.deps import CurrentUser


class _AuditSessionCtx:
    """审计短事务 session 桩：记录 commit 调用"""

    committed = False

    def __init__(self, engine):
        pass

    async def __aenter__(self):
        session = MagicMock()
        session.commit = AsyncMock(side_effect=lambda: setattr(_AuditSessionCtx, "committed", True))
        return session

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_record_audit_uses_independent_session():
    """审计走独立 session + 独立 commit（不再复用业务会话）"""
    _AuditSessionCtx.committed = False
    record = AsyncMock()
    user = CurrentUser(id=1, username="auditor", role="admin")
    with patch.object(helpers, "get_manager", lambda: MagicMock()), \
         patch.object(helpers, "_AuditSession", _AuditSessionCtx), \
         patch.object(helpers, "AuditService", MagicMock(return_value=MagicMock(record=record))):
        await record_audit(MagicMock(), user, "task.delete", "task:1", {"reason": "cleanup"})

    record.assert_awaited_once()
    assert record.await_args.args[:3] == (1, "auditor", "task.delete")
    assert _AuditSessionCtx.committed is True


@pytest.mark.asyncio
async def test_record_audit_swallows_infrastructure_failure():
    """审计基础设施全挂：不向上抛（业务响应不受影响——旧实现会 500）"""
    def _boom():
        raise RuntimeError("db down")

    user = CurrentUser(id=1, username="auditor", role="admin")
    with patch.object(helpers, "get_manager", _boom):
        await record_audit(MagicMock(), user, "task.delete", "task:2")  # 不抛即通过
