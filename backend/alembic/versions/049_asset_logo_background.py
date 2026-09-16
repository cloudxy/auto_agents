"""capability_assets 加 logo / background（.agents 同步 icon/background）

Revision ID: 049
Revises: 048
Create Date: 2026-09-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "049"
down_revision: Union[str, Sequence[str], None] = "048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "capability_assets",
        sa.Column("logo", sa.String(length=512), nullable=True, comment="icon 相对仓库路径"),
    )
    op.add_column(
        "capability_assets",
        sa.Column(
            "background", sa.String(length=512), nullable=True,
            comment="背景图相对仓库路径",
        ),
    )


def downgrade() -> None:
    op.drop_column("capability_assets", "background")
    op.drop_column("capability_assets", "logo")
