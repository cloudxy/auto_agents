"""capability_assets 加 featured / examples（feat-agents-market FR-04/FR-05）

Revision ID: 050
Revises: 049
Create Date: 2026-09-15

规格来源：02-shape/db-spec.md §8（featured smallint NOT NULL server_default '0'；
examples JSON NULL；downgrade 反序对称）。agents_hub._desired 白名单不含这两列
（db-spec §9），同步不重置治理字段。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "050"
down_revision: Union[str, Sequence[str], None] = "049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "capability_assets",
        sa.Column(
            "featured", sa.SmallInteger(), nullable=False, server_default="0",
            comment="精选权重（feat-agents-market FR-04 综合/最热序）；0=非精选",
        ),
    )
    op.add_column(
        "capability_assets",
        sa.Column(
            "examples", sa.JSON(), nullable=True,
            comment="详情示例区（feat-agents-market FR-05）；NULL/空=隐藏示例区",
        ),
    )


def downgrade() -> None:
    op.drop_column("capability_assets", "examples")
    op.drop_column("capability_assets", "featured")
