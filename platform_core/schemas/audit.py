"""操作审计日志 Schema —— /admin/audit-logs 查询契约"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    """单条审计日志的对外响应"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: Optional[int] = None
    actor_name: str
    action: str
    target: str
    detail: Optional[str] = None
    created_at: Optional[datetime] = None


class AuditLogListResponse(BaseModel):
    """审计日志分页响应"""

    total: int
    items: List[AuditLogResponse]
