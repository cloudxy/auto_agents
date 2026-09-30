"""users 唯一键漂移自愈：补齐 042 的 contract（alive_flag 键在、旧键撤）

Revision ID: 050a
Revises: 050
Create Date: 2026-09-29

dev 库实证（2026-09-29 结构比对：新建库跑到 050 vs dev 库）：alembic_version=050、
users.alive_flag 生成列在场，但 042 的键替换没落地——仍是旧键
uq_users_tenant_username (tenant_id, username) / email (email) / ix_users_email，
缺 uq_users_tenant_username_alive / uq_users_email_alive。后果：
- 软删账号继续占着 username/email（FR-93「删后同名重建」在该库失效）；
- 051 把超管迁回 platform 租户时撞上 platform 租户里已软删的同名 admin → 1062。

本迁移按在场性逐项补齐（每步幂等，042 正常落地的库上整体 no-op），插在 051 之前。
新键是旧键的放松（旧键保证同键至多一行，存量必满足），先建新键再撤旧键，不留无约束窗口。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# SM-EXEMPT: 漂移自愈、非新 schema——这些键归 042 所有（042 downgrade 负责撤回）；
# 050a 的 downgrade 若撤新键会把库打回 042 之前的错误形态，故 downgrade 刻意 no-op，
# 回滚到 050 照常成功（审计 10.2-G「可回滚」本意）

revision: str = "050a"
down_revision: Union[str, Sequence[str], None] = "050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ALIVE_EXPR = "CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END"


def _column_exists(bind, table: str, column: str) -> bool:
    return bind.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
    ), {"t": table, "c": column}).scalar() > 0


def _index_exists(bind, table: str, name: str) -> bool:
    return bind.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND INDEX_NAME = :n"
    ), {"t": table, "n": name}).scalar() > 0


def _legacy_email_unique_keys(bind) -> list[str]:
    """只含 email 一列的旧唯一键（001 部署自动名，dev 库实证名 'email'）"""
    rows = bind.execute(sa.text(
        "SELECT INDEX_NAME FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND NON_UNIQUE = 0 "
        "GROUP BY INDEX_NAME HAVING GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) = 'email'"
    )).fetchall()
    return [str(r[0]) for r in rows]


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "users", "alive_flag"):
        op.add_column("users", sa.Column(
            "alive_flag", sa.SmallInteger(),
            sa.Computed(_ALIVE_EXPR, persisted=False),
            comment="alive marker (042): unique-key component, soft-deleted rows NULL out",
        ))
    if not _index_exists(bind, "users", "uq_users_tenant_username_alive"):
        op.create_unique_constraint(
            "uq_users_tenant_username_alive", "users", ["tenant_id", "username", "alive_flag"])
    if not _index_exists(bind, "users", "uq_users_email_alive"):
        op.create_unique_constraint("uq_users_email_alive", "users", ["email", "alive_flag"])
    if _index_exists(bind, "users", "uq_users_tenant_username"):
        op.drop_constraint("uq_users_tenant_username", "users", type_="unique")
    for name in _legacy_email_unique_keys(bind):
        op.drop_constraint(name, "users", type_="unique")
    if _index_exists(bind, "users", "ix_users_email"):
        op.drop_index("ix_users_email", table_name="users")


def downgrade() -> None:
    # 键归 042 所有，见文件头 SM-EXEMPT 说明
    return None
