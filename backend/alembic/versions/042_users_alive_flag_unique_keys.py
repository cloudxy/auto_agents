"""users 唯一键在册化（alive_flag 生成列）——软删行释放 username/email

Revision ID: 042
Revises: 041
Create Date: 2026-09-11

feat-product-complete T-24（FR-93 / contract §8 QA-03 / db-spec §16.1）：
- users.alive_flag SMALLINT VIRTUAL 生成列（025 既定机制推到 users，capability_assets
  生产在用）：存活=1 参与唯一判重；已删=NULL 脱离唯一（MySQL 唯一索引不对含
  NULL 行判重）→ 软删行释放 username（同租户口径）/email（全局口径）。
- 新键 uq_users_tenant_username_alive (tenant_id, username, alive_flag) 与
  uq_users_email_alive (email, alive_flag)——最左前缀承接旧键查询义务。
- 撤旧键：uq_users_tenant_username（017）、001 部署自动名 email 唯一键（本机
  SHOW CREATE TABLE users 实证，按 information_schema.STATISTICS 定位）、
  ix_users_email（与唯一键纯重复，026 治理口径，down 不恢复）。
- 单迁移 expand→contract：方向是放松（新键约束行子集严格小于旧键，存量必满足，
  旧键保证同键至多一行），025 先例；VIRTUAL 加列 INSTANT，唯一键变更 INPLACE。
- downgrade 带前置校验（impossible-down，025 同款）：042 存续期发生过「删后
  同名重建」→ 同键多行 → 旧键无法重建 → 显式 raise（先恢复或物理清理软删同名
  行再回滚）。生产禁止 downgrade past 037，本特征 down 只在隔离库验证。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "042"
down_revision: Union[str, Sequence[str], None] = "041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ALIVE_EXPR = "CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END"


def _index_exists(bind, table: str, name: str) -> bool:
    return bind.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND INDEX_NAME = :n"
    ), {"t": table, "n": name}).scalar() > 0


def _legacy_email_unique_key(bind) -> str | None:
    """定位 001 部署自动名的 email 唯一键（本机实证名 'email'，不硬编码假设）。

    None=不在场：042 down→up 重放时 down 已恢复同名键但本迁移幂等重入的
    环境差异（结构断言由测试侧钉住），跳过 DROP。
    """
    row = bind.execute(sa.text(
        "SELECT INDEX_NAME FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' "
        "AND COLUMN_NAME = 'email' AND NON_UNIQUE = 0 "
        "AND INDEX_NAME NOT IN ('uq_users_email_alive', 'uq_users_tenant_username_alive') "
        "GROUP BY INDEX_NAME"
    )).fetchone()
    return str(row[0]) if row else None


def upgrade() -> None:
    bind = op.get_bind()
    # expand 1：加 VIRTUAL 生成列（存活=1 / 已删=NULL；INSTANT DDL）
    op.add_column("users", sa.Column(
        "alive_flag", sa.SmallInteger(),
        sa.Computed(_ALIVE_EXPR, persisted=False),
        comment="alive marker (042): unique-key component, soft-deleted rows NULL out",
    ))
    # expand 2：建两新键（旧键的放松——旧键保证同键至多一行，存量必满足）
    op.create_unique_constraint(
        "uq_users_tenant_username_alive", "users", ["tenant_id", "username", "alive_flag"])
    op.create_unique_constraint(
        "uq_users_email_alive", "users", ["email", "alive_flag"])
    # contract：撤旧键。新键在场后旧键是把已删行继续摁在坑里的更强错误约束；
    # (tenant_id, username) 与 (email) 等值查询由新键最左前缀承接（db-spec §16.1）。
    # ix_users_email 与唯一键纯重复（026 治理口径，down 不恢复）→ down→up 重放
    # 时不在场，按在场性条件撤（幂等重入）。
    op.drop_constraint("uq_users_tenant_username", "users", type_="unique")
    legacy_email_uq = _legacy_email_unique_key(bind)
    if legacy_email_uq:
        op.drop_constraint(legacy_email_uq, "users", type_="unique")
    if _index_exists(bind, "users", "ix_users_email"):
        op.drop_index("ix_users_email", table_name="users")


def downgrade() -> None:
    bind = op.get_bind()
    # 回滚前置校验（impossible-down，025 同款）：042 存续期「删后同名重建」产生
    # 同键多行（一活一删或多删）会让旧唯一键无法重建——显式报错优于 ALTER 中途
    # 失败留半回滚态（先恢复或物理清理软删同名行再回滚）
    dup_username = bind.execute(sa.text(
        "SELECT COUNT(*) FROM (SELECT 1 AS c FROM users "
        "GROUP BY tenant_id, username HAVING COUNT(*) > 1) AS dup"
    )).scalar()
    if dup_username:
        raise RuntimeError(
            f"042 downgrade 前置校验失败：users 存在 {dup_username} 组 (tenant_id, username) "
            "同名多行（042 存续期删后重建所致）。需先恢复或物理清理软删同名行再回滚。"
            "检测 SQL：SELECT tenant_id, username, COUNT(*) FROM users "
            "GROUP BY tenant_id, username HAVING COUNT(*) > 1;"
        )
    dup_email = bind.execute(sa.text(
        "SELECT COUNT(*) FROM (SELECT 1 AS c FROM users "
        "GROUP BY email HAVING COUNT(*) > 1) AS dup"
    )).scalar()
    if dup_email:
        raise RuntimeError(
            f"042 downgrade 前置校验失败：users 存在 {dup_email} 组 email 同名多行"
            "（042 存续期删后重建所致）。需先恢复或物理清理软删同名行再回滚。"
            "检测 SQL：SELECT email, COUNT(*) FROM users GROUP BY email HAVING COUNT(*) > 1;"
        )
    op.drop_constraint("uq_users_tenant_username_alive", "users", type_="unique")
    op.drop_constraint("uq_users_email_alive", "users", type_="unique")
    op.drop_column("users", "alive_flag")
    op.create_unique_constraint("uq_users_tenant_username", "users", ["tenant_id", "username"])
    # 恢复 001 部署自动名形态（MySQL 自动名=email）；ix_users_email 不恢复（026 口径）
    op.create_unique_constraint("email", "users", ["email"])
