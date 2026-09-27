"""N1 夹具名单表 + product_events.is_internal_fixture 快照列（T-01 / FR-U03）

Revision ID: 045
Revises: 044
Create Date: 2026-09-12

upgrade-four-pillars T-01：internal_fixture_tenants 新表（物理 DELETE=移出）；
product_events 表尾 ADD 可空 is_internal_fixture + 北极星复合索引。
expand-only。禁止本文件改 orders / 商户凭据 / relay SKU（N3=T-14）。
禁止复活 028/029/030。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "045"
down_revision: Union[str, Sequence[str], None] = "044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "internal_fixture_tenants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False,
                  comment="代理主键，跟仓 INT"),
        sa.Column("tenant_id", sa.Integer(), nullable=False,
                  comment="被标为夹具的企业；PIT-4 禁止 NULL=平台"),
        sa.Column("created_by", sa.String(length=64), nullable=False,
                  comment="谁标的（超管用户名快照，无用户 FK）"),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP"), comment="何时标上"),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP"),
                  comment="R-AUD；移出为 DELETE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uk_internal_fixture_tenants_tenant"),
    )
    op.add_column(
        "product_events",
        sa.Column(
            "is_internal_fixture",
            sa.Boolean(),
            nullable=True,
            comment="当时是否夹具企业。1=是 0=否 NULL=本列上线前旧事件",
        ),
    )
    op.create_index(
        "idx_product_events_name_fixture_occurred",
        "product_events",
        ["event_name", "is_internal_fixture", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_product_events_name_fixture_occurred", table_name="product_events")
    op.drop_column("product_events", "is_internal_fixture")
    op.drop_table("internal_fixture_tenants")
