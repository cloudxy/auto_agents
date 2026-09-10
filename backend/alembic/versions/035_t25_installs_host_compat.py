"""t25 capability_installs + assets.host_compat

Revision ID: 035
Revises: 034
Create Date: 2026-09-09

T-25：安装表 TenantMixin 禁豁免；唯一 (tenant_id, asset_id, host, alive_flag)。
host_compat 已在 db-spec（NULL=四宿主可订；[]=都不可订）。
禁止复活 028/029/030。不改 uq_asset_type_name_alive。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "035"
down_revision: Union[str, Sequence[str], None] = "034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ALIVE_EXPR = "CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END"


def upgrade() -> None:
    op.add_column(
        "capability_assets",
        sa.Column(
            "host_compat",
            sa.JSON(),
            nullable=True,
            comment="NULL=四宿主可订；[]=都不可订；非空数组=仅名单",
        ),
    )
    op.create_table(
        "capability_installs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "tenant_id", sa.Integer(), nullable=False,
            comment="隔离列；迁移层 NOT NULL；禁止豁免",
        ),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column(
            "host", sa.String(length=16), nullable=False,
            comment="grok/zcode/kimi/claude",
        ),
        sa.Column(
            "enabled", sa.SmallInteger(), server_default="1", nullable=False,
            comment="我的安装开关；不是 enable-host",
        ),
        sa.Column(
            "trusted", sa.SmallInteger(), server_default="0", nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column(
            "alive_flag", sa.SmallInteger(),
            sa.Computed(_ALIVE_EXPR, persisted=False),
            comment="存活标记（生成列）：唯一键组件，软删行 NULL 脱离唯一约束",
        ),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("updated_by", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
            comment="订阅成功时刻",
        ),
        sa.Column(
            "updated_at", sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["capability_assets.id"], ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "asset_id", "host", "alive_flag",
            name="uq_installs_tenant_asset_host_alive",
        ),
    )
    op.create_index(
        "idx_installs_asset", "capability_installs", ["asset_id"], unique=False,
    )
    op.create_index(
        op.f("ix_capability_installs_tenant_id"),
        "capability_installs", ["tenant_id"], unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_capability_installs_tenant_id"),
        table_name="capability_installs",
    )
    op.drop_index("idx_installs_asset", table_name="capability_installs")
    op.drop_table("capability_installs")
    op.drop_column("capability_assets", "host_compat")
