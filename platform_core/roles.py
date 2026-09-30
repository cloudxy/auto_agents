"""租户角色 → 兼容 role 的唯一派生（审计 QA-B1-4 / BUG-05）

users 表同时有 tenant_role（owner/admin/operator/viewer，企业内身份）与历史 role
（admin/operator/viewer，驱动 require_admin / require_operator 与 /auth/permissions）。
原先派生规则散在 4 处且互相矛盾：成员接口把 operator 降成 viewer（「可操作任务」的
operator 实际只读），平台用户页反过来把 role 原样复制成 tenant_role（能把 owner 覆盖掉）。
一律经本函数派生。
"""
from __future__ import annotations

from typing import Optional

from platform_core.logger import get_logger

logger = get_logger("platform.roles")

TENANT_ROLES: tuple[str, ...] = ("owner", "admin", "operator", "viewer")
_LEGACY_OF = {"owner": "admin", "admin": "admin", "operator": "operator", "viewer": "viewer"}


def derive_legacy_role(tenant_role: Optional[str]) -> str:
    """owner/admin → admin；operator → operator；viewer / 未知 → viewer（最小权限）"""
    logger.debug(f"派生兼容角色 | tenant_role={tenant_role}")
    return _LEGACY_OF.get(str(tenant_role or "").strip().lower(), "viewer")


def tenant_role_from_legacy(role: Optional[str]) -> str:
    """平台用户页按 role 分配时反推 tenant_role——永不产生 owner（owner 只能走转让）"""
    logger.debug(f"反推租户角色 | role={role}")
    value = str(role or "").strip().lower()
    return value if value in ("admin", "operator", "viewer") else "viewer"
