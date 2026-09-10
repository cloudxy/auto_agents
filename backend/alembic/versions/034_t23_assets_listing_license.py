"""t23 capability_assets listing_state + license gate columns

Revision ID: 034
Revises: 033
Create Date: 2026-09-09

T-23 查询侧 FR-33：listing_state / license / public_license_override + P-M01 索引。
列已在 db-spec；prefer autogenerate（stamp 033 空库 + INCLUDE_TABLES=capability_assets）。
禁止复活 028/029/030。不改 uq_asset_type_name_alive。不加 source_id / installs。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "034"
down_revision: Union[str, Sequence[str], None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "capability_assets",
        sa.Column(
            "listing_state",
            sa.String(length=16),
            server_default="unlisted",
            nullable=False,
            comment="unlisted/listed/coming_soon；与 status / 许可 / 黑名单独立",
        ),
    )
    op.add_column(
        "capability_assets",
        sa.Column(
            "license",
            sa.String(length=64),
            nullable=True,
            comment="同步拷贝的许可标识（现在）。NULL=未声明",
        ),
    )
    op.add_column(
        "capability_assets",
        sa.Column(
            "public_license_override",
            sa.SmallInteger(),
            server_default="0",
            nullable=False,
            comment="超管特例放行（现在）。0=未放行",
        ),
    )
    op.create_index(
        "idx_assets_listing_status_type_cat",
        "capability_assets",
        ["listing_state", "status", "asset_type", "category"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_assets_listing_status_type_cat", table_name="capability_assets")
    op.drop_column("capability_assets", "public_license_override")
    op.drop_column("capability_assets", "license")
    op.drop_column("capability_assets", "listing_state")
