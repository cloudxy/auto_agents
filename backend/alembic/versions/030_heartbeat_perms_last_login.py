"""last_login / skill downloads / result hash unique / builtin role perms

Revision ID: 030
Revises: 029
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "030"
down_revision: Union[str, Sequence[str], None] = "029"
branch_labels = None
depends_on = None


def _has_column(table: str, col: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return col in {c["name"] for c in insp.get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return name in {i["name"] for i in insp.get_indexes(table)}


def upgrade() -> None:
    # 不做 roles 整表覆盖：040/032 用 JSON_ARRAY_APPEND；整表写回会抹掉 menu:relay/llm。
    if not _has_column("users", "last_login_at"):
        op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    if not _has_column("skills", "download_count"):
        op.add_column(
            "skills",
            sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"),
        )
    if not _has_index("spider_results", "uq_spider_results_tenant_spider_hash"):
        op.create_index(
            "uq_spider_results_tenant_spider_hash",
            "spider_results",
            ["tenant_id", "spider_name", "content_hash"],
            unique=True,
        )


def downgrade() -> None:
    if _has_index("spider_results", "uq_spider_results_tenant_spider_hash"):
        op.drop_index("uq_spider_results_tenant_spider_hash", table_name="spider_results")
    if _has_column("skills", "download_count"):
        op.drop_column("skills", "download_count")
    if _has_column("users", "last_login_at"):
        op.drop_column("users", "last_login_at")
