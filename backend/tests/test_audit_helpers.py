"""审计独立短事务单测（P1-11 + ADR-0007 D4）

Seam 迁移说明：独立 session 的开启与提交已从 backend/app/api/_helpers.py
下沉至 backend/services/audit_service.record_audit_standalone（事务所有权
归 Service 层）；本文件 patch 面同步迁移，并钉住 API 钩子的纯委托语义。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import backend.services.audit_service as audit_svc
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
async def test_record_audit_standalone_owns_commit():
    """独立短事务写入：Service 层函数自开 session + 自持 commit（API 层零 session 生命周期）"""
    _AuditSessionCtx.committed = False
    record = AsyncMock()
    with patch.object(audit_svc, "get_manager", lambda: MagicMock()), \
         patch.object(audit_svc, "AsyncSession", _AuditSessionCtx), \
         patch.object(audit_svc, "AuditService", MagicMock(return_value=MagicMock(record=record))):
        await audit_svc.record_audit_standalone(1, "auditor", "task.delete", "task:1", {"reason": "cleanup"})

    record.assert_awaited_once()
    assert record.await_args.args[:3] == (1, "auditor", "task.delete")
    assert _AuditSessionCtx.committed is True


@pytest.mark.asyncio
async def test_record_audit_standalone_swallows_infrastructure_failure():
    """审计基础设施全挂：不向上抛（业务响应不受影响——旧实现会 500）"""
    def _boom():
        raise RuntimeError("db down")

    with patch.object(audit_svc, "get_manager", _boom):
        await audit_svc.record_audit_standalone(1, "auditor", "task.delete", "task:2")  # 不抛即通过


@pytest.mark.asyncio
async def test_api_helper_is_pure_delegation():
    """API 审计钩子只做参数展开与委托（ADR-0007：API 层不碰 session 生命周期）"""
    import backend.app.api._helpers as helpers

    user = CurrentUser(id=7, username="op", role="admin")
    with patch.object(helpers, "record_audit_standalone", AsyncMock()) as standalone:
        await record_audit(MagicMock(), user, "role.create", "role:viewer", {"k": "v"})

    standalone.assert_awaited_once_with(7, "op", "role.create", "role:viewer", {"k": "v"})
