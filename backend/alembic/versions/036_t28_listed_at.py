"""t28 capability_assets.listed_at；治理台叶名能力市场

Revision ID: 036
Revises: 035
Create Date: 2026-09-10

T-28：listed_at ADD 接表尾；unlist 不清空。不改 uq。不加 source_id。
禁止复活 028/029/030。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "036"
down_revision: Union[str, Sequence[str], None] = "035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "capability_assets",
        sa.Column(
            "listed_at",
            sa.DateTime(),
            nullable=True,
            comment="最近一次 listed；unlist 不清空；NULL=从未 listed",
        ),
    )
    op.execute(
        sa.text(
            "UPDATE menus SET name = '能力市场' "
            "WHERE path = '/capabilities' AND name = '资产目录'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE menus SET name = '资产目录' "
            "WHERE path = '/capabilities' AND name = '能力市场'"
        )
    )
    op.drop_column("capability_assets", "listed_at")
