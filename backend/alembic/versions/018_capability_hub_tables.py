"""P6 capability hub：统一资产目录 + 插件/专家/专家团细节表

Revision ID: 018
Revises: 017
Create Date: 2026-09-02

- capability_assets（UNIQUE(asset_type, name)，平台级豁免）
- capability_plugins / capability_experts / capability_teams
- 存量 skills 回填 asset 行（type=skill, detail_id=skills.id）
- skill_reviews 泛化：加 asset_id 列（存量回填指向新 asset 行）
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "018"
down_revision: Union[str, Sequence[str], None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "capability_assets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("asset_type", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=True),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="uncategorized"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="experimental"),
        sa.Column("source_type", sa.String(length=16), nullable=False, server_default="self_built"),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("source_author", sa.String(length=128), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("score", sa.Numeric(3, 1), nullable=True),
        sa.Column("ai_suggested_score", sa.Numeric(3, 1), nullable=True),
        sa.Column("tier", sa.String(length=2), nullable=True),
        sa.Column("reviewed_by", sa.String(length=64), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("similar_to", mysql.JSON(), nullable=True),
        sa.Column("file_path", sa.String(length=512), nullable=True),
        sa.Column("sync_state", sa.String(length=16), nullable=False, server_default="ok"),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("detail_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_type", "name", name="uq_asset_type_name"),
    )
    op.create_index(op.f("ix_capability_assets_asset_type"), "capability_assets", ["asset_type"])
    op.create_index(op.f("ix_capability_assets_category"), "capability_assets", ["category"])
    op.create_index(op.f("ix_capability_assets_status"), "capability_assets", ["status"])

    for table, extra_cols in [
        ("capability_plugins", [
            ("version", sa.String(32)), ("author", sa.String(128)), ("license", sa.String(64)),
            ("manifest", mysql.JSON()), ("bundled_skills", mysql.JSON()),
            ("mcp_servers", mysql.JSON()), ("hooks", mysql.JSON()), ("commands", mysql.JSON()),
            ("health_status", sa.String(16)), ("last_verified_at", sa.DateTime()),
            ("verify_detail", mysql.JSON()),
        ]),
        ("capability_experts", [
            ("persona_md", sa.Text()), ("tools", mysql.JSON()),
            ("bundled_skills", mysql.JSON()), ("mcp_refs", mysql.JSON()),
            ("model_pref", sa.String(64)),
        ]),
        ("capability_teams", [
            ("leader_expert", sa.String(128)), ("members", mysql.JSON()),
            ("workflow_md", sa.Text()),
        ]),
    ]:
        cols = [
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("asset_id", sa.Integer(), nullable=False),
        ] + [sa.Column(name, typ, **({"nullable": True} if name not in ("health_status",) else {"nullable": False, "server_default": "unknown"})) for name, typ in extra_cols]
        cols.append(sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True))
        cols.append(sa.Column("updated_at", sa.DateTime(), nullable=True))
        op.create_table(table, *cols,
                        sa.PrimaryKeyConstraint("id"),
                        __import__("sqlalchemy").UniqueConstraint("asset_id", name=f"uq_{table}_asset"))
        op.create_index(op.f(f"ix_{table}_asset_id"), table, ["asset_id"])

    # skill_reviews 泛化：加 asset_id（存量回填）
    op.add_column("skill_reviews", sa.Column("asset_id", sa.Integer(), nullable=True, index=True))

    # 存量 skills 回填 asset 行 + reviews 挂钩
    op.execute(sa.text("""
        INSERT INTO capability_assets
            (asset_type, name, title, description, category, status, source_type,
             source_url, source_author, content_hash, score, ai_suggested_score, tier,
             reviewed_by, reviewed_at, similar_to, file_path, sync_state, detail_id,
             created_at, updated_at)
        SELECT 'skill', s.name, s.title, s.description, s.category, s.status, s.source_type,
               s.source_url, s.source_author, s.content_hash, s.score, s.ai_suggested_score,
               s.tier, s.reviewed_by, s.reviewed_at, s.similar_to, s.file_path, s.sync_state,
               s.id, NOW(), NOW()
        FROM skills s
        WHERE NOT EXISTS (
            SELECT 1 FROM capability_assets ca
            WHERE ca.asset_type = 'skill' AND ca.name = s.name
        )
    """))
    op.execute(sa.text("""
        UPDATE skill_reviews sr
        JOIN capability_assets ca ON ca.asset_type = 'skill'
             AND ca.detail_id = sr.skill_id
        SET sr.asset_id = ca.id
        WHERE sr.asset_id IS NULL
    """))


def downgrade() -> None:
    op.drop_column("skill_reviews", "asset_id")
    op.drop_index(op.f("ix_capability_teams_asset_id"), table_name="capability_teams")
    op.drop_table("capability_teams")
    op.drop_index(op.f("ix_capability_experts_asset_id"), table_name="capability_experts")
    op.drop_table("capability_experts")
    op.drop_index(op.f("ix_capability_plugins_asset_id"), table_name="capability_plugins")
    op.drop_table("capability_plugins")
    op.drop_index(op.f("ix_capability_assets_status"), table_name="capability_assets")
    op.drop_index(op.f("ix_capability_assets_category"), table_name="capability_assets")
    op.drop_index(op.f("ix_capability_assets_asset_type"), table_name="capability_assets")
    op.drop_table("capability_assets")
