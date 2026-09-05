"""DB 升级 2026-09 Phase C：运维扩展（归档 / i18n + 种子 / 系统缓存）

Revision ID: 021
Revises: 020
Create Date: 2026-09-02

纯新增表 + i18n 种子数据（zh-CN 默认 + en），downgrade 逆序清理。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "021"
down_revision: Union[str, Sequence[str], None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DT = sa.DateTime(timezone=True)


def upgrade() -> None:
    # ── B6 数据归档 ──
    op.create_table(
        "archive_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("source_table", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("archived_at", _DT, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("archived_by", sa.String(length=64), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("retention_until", _DT, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_table", "source_id", name="uq_archive_records_source"),
    )
    op.create_index(op.f("ix_archive_records_tenant_id"), "archive_records", ["tenant_id"])
    op.create_index("ix_archive_records_tenant_archived", "archive_records",
                    ["tenant_id", "archived_at"])

    # ── B7 i18n ──
    op.create_table(
        "i18n_locales",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_i18n_locales_code"),
    )
    op.create_table(
        "i18n_translations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("locale_id", sa.Integer(), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("translated_value", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["locale_id"], ["i18n_locales.id"]),
        sa.UniqueConstraint("locale_id", "resource_type", "resource_id", "field_name",
                            name="uq_i18n_translations_field"),
    )

    # ── B8 系统缓存 ──
    op.create_table(
        "system_caches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cache_key", sa.String(length=255), nullable=False),
        sa.Column("cache_value", sa.Text(), nullable=False),
        sa.Column("expires_at", _DT, nullable=True),
        sa.Column("created_at", _DT, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", _DT, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cache_key", name="uq_system_caches_key"),
    )

    # ── i18n 种子（数据回填 backfill / migration data：zh-CN 默认 + en）──
    op.execute(sa.text(
        "INSERT INTO i18n_locales (code, name, is_default, enabled) VALUES "
        "('zh-CN', '简体中文', 1, 1), "
        "('en', 'English', 0, 1)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM i18n_locales WHERE code IN ('zh-CN', 'en')"))
    op.drop_table("system_caches")
    op.drop_table("i18n_translations")
    op.drop_table("i18n_locales")
    op.drop_index("ix_archive_records_tenant_archived", table_name="archive_records")
    op.drop_index(op.f("ix_archive_records_tenant_id"), table_name="archive_records")
    op.drop_table("archive_records")
