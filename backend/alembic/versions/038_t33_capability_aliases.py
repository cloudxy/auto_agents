"""t33 capability_aliases vanity slugs

Revision ID: 038
Revises: 037
Create Date: 2026-09-10

T-33：人工短名平台表。tenant_id 恒 NULL。不改 uq_asset_type_name_alive。
同步不 insert alias。禁止复活 028/029/030。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "038"
down_revision: Union[str, Sequence[str], None] = "037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ALIVE_EXPR = "CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END"


def upgrade() -> None:
    op.create_table(
        "capability_aliases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False, comment="人工短名；存活全局唯一"),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column(
            "asset_type", sa.String(length=16), nullable=False,
            comment="反规范化，公开路由第一段；D22b 回填须同步",
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=True, comment="平台级恒 NULL"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column(
            "alive_flag", sa.SmallInteger(),
            sa.Computed(_ALIVE_EXPR, persisted=False),
            comment="存活标记（生成列）：唯一键组件",
        ),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("updated_by", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["capability_assets.id"], ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", "alive_flag", name="uq_aliases_slug_alive"),
        sa.UniqueConstraint("asset_id", "alive_flag", name="uq_aliases_asset_alive"),
    )


def downgrade() -> None:
    op.drop_table("capability_aliases")
