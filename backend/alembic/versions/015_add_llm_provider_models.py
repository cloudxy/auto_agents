"""add llm_provider_models table (方案 B · B-M2-1)

Revision ID: 015
Revises: 014
Create Date: 2026-08-31

一供应商多模型子表：父行 model 列保留为默认模型冗余快照（Service 同事务刷新）；
删除父行级联删除子行（FK ON DELETE CASCADE + ORM cascade 双保险）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
# SM-EXEMPT: 历史迁移（已部署），expand-contract 检查不追溯
# expand-contract: grandfathered
revision: str = "015"
down_revision: Union[str, Sequence[str], None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """建 llm_provider_models"""
    op.create_table(
        "llm_provider_models",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("alias", sa.String(length=128), nullable=True),
        sa.Column("model_tier", sa.String(length=16), nullable=False, server_default="basic"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("health_status", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("last_latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "model_id", name="uq_provider_model"),
        sa.ForeignKeyConstraint(["provider_id"], ["llm_providers.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_llm_provider_models_provider_id"), "llm_provider_models", ["provider_id"])


def downgrade() -> None:
    """回滚子表"""
    op.drop_index(op.f("ix_llm_provider_models_provider_id"), table_name="llm_provider_models")
    op.drop_table("llm_provider_models")
