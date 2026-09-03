"""DB 升级 2026-09 Phase A：软删除 + 审计 Mixin 存量改造 + 关键 FK 补全

Revision ID: 019
Revises: 018
Create Date: 2026-09-02

分步可逆（expand-contract）：
1. 加列：deleted_at（12 表，nullable+索引）/ created_by/updated_by（10 表，String(64) nullable）
2. 孤儿清理（数据回填 backfill）：加 FK 前清理无主行
3. 加 FK：spider_results.task_id / skill_reviews.skill_id / capability_{plugins,experts,teams}.asset_id /
   llm_token_usage.provider_id（MySQL 自动补 FK 索引，列均已带索引）
4. 补复合索引：spider_tasks(tenant_id,status) / spider_results(spider_name,created_at)
5. 修 bug：system_configs.updated_at 由 Python utcnow 改 DB CURRENT_TIMESTAMP

大表（spider_results / skill_reviews）加列与加 FK 为在线 DDL（MySQL 8 INSTANT/INPLACE，
生产超大体量时可用 gh-ost 替代执行，锁表风险可控）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "019"
down_revision: Union[str, Sequence[str], None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 软删除 12 表（豁免矩阵：审计/历史/子表/聚合/系统表不进此列）
SOFT_DELETE_TABLES = [
    "tenants", "users",
    "spider_tasks", "spider_results", "spider_definitions", "spider_schedules",
    "llm_providers", "ai_plans", "skills", "capability_assets",
    "alert_rules", "spider_task_templates",
]

# 审计 10 表（ai_plans 已有 created_by 列；spider_task_templates.created_by 存量为 Integer 需改型）
AUDIT_BOTH_TABLES = [
    "spider_tasks", "spider_results", "spider_definitions", "spider_schedules",
    "llm_providers", "skills", "capability_assets", "alert_rules",
]


def upgrade() -> None:
    # ── 步骤 1：加列（全部 nullable，SM-5 安全）──
    for t in SOFT_DELETE_TABLES:
        op.add_column(t, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True,
                                   comment="软删除时间（NULL=存活）"))
        op.create_index(op.f(f"ix_{t}_deleted_at"), t, ["deleted_at"])

    for t in AUDIT_BOTH_TABLES:
        op.add_column(t, sa.Column("created_by", sa.String(length=64), nullable=True, comment="创建人用户名"))
        op.add_column(t, sa.Column("updated_by", sa.String(length=64), nullable=True, comment="最后修改人用户名"))

    # ai_plans：created_by 已存在（String(64)，迁移 009），仅补 updated_by
    op.add_column("ai_plans", sa.Column("updated_by", sa.String(length=64), nullable=True, comment="最后修改人用户名"))

    # spider_task_templates：created_by 存量 Integer（用户 ID）→ String(64)（用户名，AuditMixin 对齐）
    op.alter_column("spider_task_templates", "created_by",
                    existing_type=sa.Integer(), type_=sa.String(length=64), existing_nullable=True)
    op.add_column("spider_task_templates", sa.Column("updated_by", sa.String(length=64), nullable=True, comment="最后修改人用户名"))

    # ── 步骤 2：孤儿清理（数据回填 backfill / migration data，加 FK 前置条件）──
    op.execute(sa.text(
        "DELETE sr FROM spider_results sr "
        "LEFT JOIN spider_tasks st ON sr.task_id = st.id "
        "WHERE st.id IS NULL"
    ))
    op.execute(sa.text(
        "DELETE sr FROM skill_reviews sr "
        "LEFT JOIN skills s ON sr.skill_id = s.id "
        "WHERE s.id IS NULL"
    ))
    for t in ("capability_plugins", "capability_experts", "capability_teams"):
        op.execute(sa.text(
            f"DELETE cd FROM {t} cd "
            "LEFT JOIN capability_assets ca ON cd.asset_id = ca.id "
            "WHERE ca.id IS NULL"
        ))
    # 聚合表孤儿 provider_id 置 NULL（历史用量保留，provider 维度不失义）
    op.execute(sa.text(
        "UPDATE llm_token_usage SET provider_id = NULL "
        "WHERE provider_id IS NOT NULL AND provider_id NOT IN (SELECT id FROM llm_providers)"
    ))

    # ── 步骤 3：FK 补全（5 处关键关联，llm_provider_models 既有不重）──
    op.create_foreign_key("fk_spider_results_task", "spider_results", "spider_tasks",
                          ["task_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_skill_reviews_skill", "skill_reviews", "skills",
                          ["skill_id"], ["id"])
    op.create_foreign_key("fk_capability_plugins_asset", "capability_plugins", "capability_assets",
                          ["asset_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_capability_experts_asset", "capability_experts", "capability_assets",
                          ["asset_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_capability_teams_asset", "capability_teams", "capability_assets",
                          ["asset_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_llm_token_usage_provider", "llm_token_usage", "llm_providers",
                          ["provider_id"], ["id"])

    # ── 步骤 4：复合索引 ──
    op.create_index("ix_spider_tasks_tenant_status", "spider_tasks", ["tenant_id", "status"])
    op.create_index("ix_spider_results_name_created", "spider_results", ["spider_name", "created_at"])

    # ── 步骤 5：system_configs 时间戳 bug 修复（Python utctime → DB 受控时钟）──
    op.alter_column("system_configs", "updated_at", existing_type=sa.DateTime(),
                    server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"))


def downgrade() -> None:
    # 逆序回滚：索引 → FK → 列 → bug 还原
    op.alter_column("system_configs", "updated_at", existing_type=sa.DateTime(),
                    server_default=None)

    op.drop_index("ix_spider_results_name_created", table_name="spider_results")
    op.drop_index("ix_spider_tasks_tenant_status", table_name="spider_tasks")

    op.drop_constraint("fk_llm_token_usage_provider", "llm_token_usage", type_="foreignkey")
    op.drop_constraint("fk_capability_teams_asset", "capability_teams", type_="foreignkey")
    op.drop_constraint("fk_capability_experts_asset", "capability_experts", type_="foreignkey")
    op.drop_constraint("fk_capability_plugins_asset", "capability_plugins", type_="foreignkey")
    op.drop_constraint("fk_skill_reviews_skill", "skill_reviews", type_="foreignkey")
    op.drop_constraint("fk_spider_results_task", "spider_results", type_="foreignkey")

    op.drop_column("spider_task_templates", "updated_by")
    op.alter_column("spider_task_templates", "created_by",
                    existing_type=sa.String(length=64), type_=sa.Integer(), existing_nullable=True)
    op.drop_column("ai_plans", "updated_by")

    for t in AUDIT_BOTH_TABLES:
        op.drop_column(t, "updated_by")
        op.drop_column(t, "created_by")

    for t in reversed(SOFT_DELETE_TABLES):
        op.drop_index(op.f(f"ix_{t}_deleted_at"), table_name=t)
        op.drop_column(t, "deleted_at")
