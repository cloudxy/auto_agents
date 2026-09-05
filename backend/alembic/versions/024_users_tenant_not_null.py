"""T5 用户层租户隔离：users.tenant_id 收紧 NOT NULL + platform 租户兜底

Revision ID: 024
Revises: 023
Create Date: 2026-09-05

expand-contract（单迁移内分步，工单 T5 设计决策 B）：
1. expand：INSERT 平台租户行（slug='platform'，幂等）；
2. 回填 backfill migration data：NULL 租户同名存量先去重（按回填目标组
   (is_platform_admin, username) 分组，保留 id 最新行，旧行软删——与 T4 软删
   口径一致 deleted_at=NOW()+is_active=0，软删行继续占 (tenant_id, username)
   唯一键位，是**有意**行为，不加删除标记进唯一键）；
3. 回填：is_platform_admin=1 的 NULL 行 → platform 租户；其余 NULL 行 → default
   租户（017 种子）；
4. contract：users.tenant_id 收紧 NOT NULL——(tenant_id, username) 唯一键由此
   真正生效，MySQL NULL≠NULL 的重复名绕过（体检发现 2）消灭。

downgrade（可回滚，up→down→up 演练归 T9/025 口径）：先放开 NOT NULL，再
platform 租户超管行 tenant_id 置 NULL（还原"平台超管 NULL"旧语义），最后删
platform 租户行。去重软删的行不恢复（旧行本就是重复名死行，语义与 T4 一致）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# 回填 backfill migration data
# revision identifiers, used by Alembic.
revision: str = "024"
down_revision: Union[str, Sequence[str], None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── expand：平台租户行（幂等，up→down→up 演练可重入）──
    op.execute(sa.text(
        "INSERT INTO tenants (slug, name, status, quota, created_at, updated_at) "
        "SELECT 'platform', '平台租户', 'active', NULL, NOW(), NOW() "
        "WHERE NOT EXISTS (SELECT 1 FROM tenants WHERE slug = 'platform')"
    ))

    # ── 回填前置：NULL 租户同名去重（按回填目标组分组，否则回填后撞唯一键）──
    # 目标组键 = (is_platform_admin, username)：platform 超管组与 default 组各自
    # 去重（两组回填后分属不同租户，跨组同名不冲突，不去重）。
    # 保留每组 id 最大行（自增主键 = 最新创建），旧行软删（T4 口径）。
    op.execute(sa.text(
        "UPDATE users AS older "
        "JOIN users AS newer "
        "  ON newer.tenant_id IS NULL "
        " AND newer.username = older.username "
        " AND newer.is_platform_admin = older.is_platform_admin "
        " AND newer.id > older.id "
        "SET older.deleted_at = NOW(), older.is_active = 0 "
        "WHERE older.tenant_id IS NULL "
        "  AND older.deleted_at IS NULL"
    ))

    # ── 回填：NULL 二义性消灭（体检发现 2 的根源）──
    op.execute(sa.text(
        "UPDATE users SET tenant_id = (SELECT id FROM tenants WHERE slug = 'platform') "
        "WHERE tenant_id IS NULL AND is_platform_admin = 1"
    ))
    op.execute(sa.text(
        "UPDATE users SET tenant_id = (SELECT id FROM tenants WHERE slug = 'default') "
        "WHERE tenant_id IS NULL"
    ))

    # ── contract：收紧 NOT NULL（先回填后收紧，存量 NULL 行数必为 0）──
    op.alter_column("users", "tenant_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    # 反向：先放开 NOT NULL，再还原平台超管 NULL 语义，最后撤 platform 租户行
    op.alter_column("users", "tenant_id", existing_type=sa.Integer(), nullable=True)
    op.execute(sa.text(
        "UPDATE users SET tenant_id = NULL "
        "WHERE is_platform_admin = 1 "
        "  AND tenant_id = (SELECT id FROM tenants WHERE slug = 'platform')"
    ))
    op.execute(sa.text("DELETE FROM tenants WHERE slug = 'platform'"))
