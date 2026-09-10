"""t29 capability_sources + assets origin columns + skill_jobs.source_id

Revision ID: 037
Revises: 036
Create Date: 2026-09-10

T-29：源表 + assets 源列 + source_type 16→32。不改 uq_asset_type_name_alive。
禁止 attach 源（含 zcode_local）。禁止回填 listed。禁止复活 028/029/030。
idx_assets_source_origin_alive 为本波 Step1 普通索引，不升 UNIQUE。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "037"
down_revision: Union[str, Sequence[str], None] = "036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ALIVE_EXPR = "CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END"


def upgrade() -> None:
    op.create_table(
        "capability_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False, comment="源稳定名；存活唯一"),
        sa.Column(
            "source_kind", sa.String(length=16), nullable=False,
            comment="local/git/url；禁止列名 type",
        ),
        sa.Column("uri", sa.String(length=512), nullable=False),
        sa.Column(
            "is_enabled", sa.SmallInteger(), server_default="1", nullable=False,
        ),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column(
            "last_succeeded", sa.Integer(), server_default="0", nullable=False,
        ),
        sa.Column(
            "last_failed", sa.Integer(), server_default="0", nullable=False,
        ),
        sa.Column("last_error", sa.String(length=512), nullable=True),
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
            "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "alive_flag", name="uq_sources_name_alive"),
    )
    op.add_column(
        "capability_assets",
        sa.Column(
            "source_id", sa.Integer(), nullable=True,
            comment="NULL=尚未 attach 源（第一方窗口）",
        ),
    )
    op.add_column(
        "capability_assets",
        sa.Column("origin_ref", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "capability_assets",
        sa.Column("origin_local_name", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "capability_assets",
        sa.Column("origin_plugin_name", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "capability_assets",
        sa.Column("alias_origin_refs", sa.JSON(), nullable=True),
    )
    op.add_column(
        "capability_assets",
        sa.Column(
            "writable", sa.SmallInteger(), server_default="1", nullable=False,
            comment="1=第一方可写库+源树；0=第三方",
        ),
    )
    op.create_foreign_key(
        "fk_assets_source_id", "capability_assets", "capability_sources",
        ["source_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_index(
        "idx_assets_source_origin_alive", "capability_assets",
        ["source_id", "origin_ref", "alive_flag"], unique=False,
    )
    op.add_column(
        "skill_jobs",
        sa.Column(
            "source_id", sa.Integer(), nullable=True,
            comment="src_sync 作业指向源；其它 job_type 为 NULL",
        ),
    )
    op.create_foreign_key(
        "fk_skill_jobs_source_id", "skill_jobs", "capability_sources",
        ["source_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("idx_skill_jobs_source", "skill_jobs", ["source_id"], unique=False)
    op.alter_column(
        "capability_assets", "source_type",
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
        existing_server_default="self_built",
    )
    op.alter_column(
        "skills", "source_type",
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
        existing_server_default="self_built",
    )


def downgrade() -> None:
    op.alter_column(
        "skills", "source_type",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=False,
        existing_server_default="self_built",
    )
    op.alter_column(
        "capability_assets", "source_type",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=False,
        existing_server_default="self_built",
    )
    op.drop_index("idx_skill_jobs_source", table_name="skill_jobs")
    op.drop_constraint("fk_skill_jobs_source_id", "skill_jobs", type_="foreignkey")
    op.drop_column("skill_jobs", "source_id")
    op.drop_index("idx_assets_source_origin_alive", table_name="capability_assets")
    op.drop_constraint("fk_assets_source_id", "capability_assets", type_="foreignkey")
    op.drop_column("capability_assets", "writable")
    op.drop_column("capability_assets", "alias_origin_refs")
    op.drop_column("capability_assets", "origin_plugin_name")
    op.drop_column("capability_assets", "origin_local_name")
    op.drop_column("capability_assets", "origin_ref")
    op.drop_column("capability_assets", "source_id")
    op.drop_table("capability_sources")
