"""存量修正：租户 operator 的兼容 role 被写成 viewer（审计 QA-B1-4 / BUG-05）

Revision ID: 055
Revises: 054
Create Date: 2026-09-28

成员接口曾把 tenant_role=operator 的成员写成 role=viewer，导致「可操作任务」的操作员
实际只读（require_operator 全部 403，/auth/permissions 下发 viewer 权限码）。
派生规则已收口到 platform_core.roles.derive_legacy_role，这里修正存量行。
"""
from typing import Sequence, Union

from alembic import op

revision: str = "055"
down_revision: Union[str, Sequence[str], None] = "054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# SM-EXEMPT: 纯数据修正、无 schema 变更；downgrade 不还原错误数据（还原即重新引入缺陷），
# 回滚到 054 照常成功


def upgrade() -> None:
    op.execute(
        "UPDATE users SET role = 'operator' "
        "WHERE tenant_role = 'operator' AND role = 'viewer' AND is_platform_admin = 0"
    )


def downgrade() -> None:
    # 不还原（见文件头 SM-EXEMPT 说明）
    return None
