"""AI 计划目标地址 DNS 复检（审计 F4-1 / BUG-22 / P0-8 回归）

schema 静态校验只挡字面量内网 IP 与 localhost；127.0.0.1.nip.io 这类解析到内网的
域名原先被接受（离线 html_snippet 路径更是从不联网校验，但 target_url 仍是试采起始地址）。
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.ai_planner.orchestrator import AiPlannerService
from platform_core.exceptions import ValidationException
from platform_core.schemas.ai_plan import AiPlanCreate


def _service(monkeypatch) -> tuple[AiPlannerService, MagicMock]:
    session = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    svc = AiPlannerService(session)
    svc.repo = MagicMock()
    svc.repo.create = AsyncMock()
    monkeypatch.setattr(AiPlannerService, "_reject_if_planning_disabled", AsyncMock())
    return svc, session


@pytest.mark.parametrize("snippet", [None, "<html><h1>t</h1></html>"])
@pytest.mark.parametrize("url", [
    "https://127.0.0.1.nip.io/list",
    "https://svc.127-0-0-1.sslip.io/x",
])
def test_create_plan_rejects_domains_resolving_to_internal(monkeypatch, url, snippet):
    svc, session = _service(monkeypatch)
    payload = AiPlanCreate(target_url=url, html_snippet=snippet)
    with pytest.raises(ValidationException) as exc:
        asyncio.run(svc.create_plan(payload, created_by="op", tenant_id=5))
    assert exc.value.data["field"] == "target_url"
    svc.repo.create.assert_not_awaited()
    session.commit.assert_not_awaited()


def test_create_plan_accepts_public_domain(monkeypatch):
    svc, session = _service(monkeypatch)
    svc.repo.create = AsyncMock(return_value=MagicMock())
    payload = AiPlanCreate(target_url="https://example.com/list")
    try:
        asyncio.run(svc.create_plan(payload, created_by="op", tenant_id=5))
    except Exception:  # noqa: BLE001 响应模型校验与本用例无关，只断言已落库
        pass
    svc.repo.create.assert_awaited_once()
