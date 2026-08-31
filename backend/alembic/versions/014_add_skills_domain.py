"""add skills domain tables (方案 A 技能管理中心, A-P1a-1)

Revision ID: 014
Revises: 013
Create Date: 2026-08-31

三表（总方案 §5.1）：skills / skill_reviews / skill_jobs。
tenant_id 预留恒 NULL（D3 平台级统一库）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "014"
down_revision: Union[str, Sequence[str], None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """建技能域三表"""
    op.create_table(
        "skills",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="目录名，全局唯一（唯一取值源）"),
        sa.Column("title", sa.String(length=256), nullable=True, comment="SKILL.md frontmatter 显示名"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="uncategorized",
                  comment="一级分类（受控枚举）"),
        sa.Column("industries", mysql.JSON(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="experimental",
                  comment="experimental/testing/stable/recommended/deprecated/blacklist"),
        sa.Column("source_type", sa.String(length=16), nullable=False, server_default="self_built"),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("source_author", sa.String(length=128), nullable=True),
        sa.Column("imported_at", sa.DateTime(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("score", sa.Numeric(3, 1), nullable=True, comment="人工终评（AI 永不写）"),
        sa.Column("ai_suggested_score", sa.Numeric(3, 1), nullable=True),
        sa.Column("rubric_human", mysql.JSON(), nullable=True),
        sa.Column("rubric_ai", mysql.JSON(), nullable=True),
        sa.Column("tier", sa.String(length=2), nullable=True),
        sa.Column("reviewed_by", sa.String(length=64), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("similar_to", mysql.JSON(), nullable=True),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("sync_state", sa.String(length=16), nullable=False, server_default="ok"),
        sa.Column("tenant_id", sa.Integer(), nullable=True, comment="D3 预留：平台级恒 NULL"),
        sa.Column("raw_meta", mysql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_skills_name"),
    )
    op.create_index(op.f("ix_skills_name"), "skills", ["name"], unique=False)
    op.create_index(op.f("ix_skills_category"), "skills", ["category"], unique=False)
    op.create_index(op.f("ix_skills_status"), "skills", ["status"], unique=False)

    op.create_table(
        "skill_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_type", sa.String(length=8), nullable=False, comment="ai/human"),
        sa.Column("reviewer", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Numeric(3, 1), nullable=True),
        sa.Column("rubric", mysql.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("prompt_version", sa.String(length=8), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_skill_reviews_skill_id"), "skill_reviews", ["skill_id"], unique=False)

    op.create_table(
        "skill_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column("succeeded", sa.Integer(), nullable=True),
        sa.Column("failed", sa.Integer(), nullable=True),
        sa.Column("detail", mysql.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """回滚技能域三表"""
    op.drop_table("skill_jobs")
    op.drop_table("skill_reviews")
    op.drop_index(op.f("ix_skills_status"), table_name="skills")
    op.drop_index(op.f("ix_skills_category"), table_name="skills")
    op.drop_index(op.f("ix_skills_name"), table_name="skills")
    op.drop_table("skills")
