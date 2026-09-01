"""SaaS S1-1 租户数据契约：tenants + 租户化列 + 复合唯一 + 默认租户回填

Revision ID: 017
Revises: 016
Create Date: 2026-09-01

- 新建 tenants；
- users + tenant_id/tenant_role/is_platform_admin，唯一改 (tenant_id, username)（email 保持全局唯一）；
- 9 张业务表 + tenant_id；4 表唯一约束改 (tenant_id, col)；llm_token_usage 唯一键 3→4 列（10.2-C）；
- 默认租户（slug=default）承接存量：role='admin' → tenant_role='owner'，其余沿用；
- NOT NULL 收紧：除 users（平台超管 NULL）与 llm_providers（平台公共行 NULL）外全部业务表。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "017"
down_revision: Union[str, Sequence[str], None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_TABLES = (
    "spider_tasks", "spider_results", "spider_schedules", "spider_definitions",
    "spider_task_templates", "ai_plans", "llm_providers", "alert_rules", "llm_token_usage",
)


def upgrade() -> None:
    """租户化（回填默认租户后收紧 NOT NULL）"""
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False, comment="租户标识（全局唯一）"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="企业名称"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("quota", sa.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    op.create_index(op.f("ix_tenants_slug"), "tenants", ["slug"], unique=False)
    # 免费档默认配额（S3 消费；数值为平台级默认，运营台可改）
    op.execute(sa.text(
        "INSERT INTO tenants (slug, name, status, quota, created_at, updated_at) "
        "VALUES ('default', '默认租户', 'active', "
        "'{\"task_concurrency\": 5, \"result_storage\": 10000, \"llm_tokens_month\": 200000}', "
        "NOW(), NOW())"
    ))

    # users 租户化
    op.add_column("users", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("tenant_role", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column(
        "is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.execute(sa.text("UPDATE users SET tenant_id = (SELECT id FROM tenants WHERE slug='default')"))
    op.execute(sa.text(
        "UPDATE users SET tenant_role = CASE WHEN role='admin' THEN 'owner' ELSE role END "
        "WHERE tenant_role IS NULL"
    ))
    op.create_index(op.f("ix_users_tenant_id"), "users", ["tenant_id"], unique=False)
    op.drop_index("username", table_name="users")  # 001 的列级唯一（MySQL 自动名）
    op.create_unique_constraint("uq_users_tenant_username", "users", ["tenant_id", "username"])

    # 9 张业务表 + tenant_id（回填后除 llm_providers 外收紧 NOT NULL）
    for table in TENANT_TABLES:
        op.add_column(table, sa.Column("tenant_id", sa.Integer(), nullable=True, comment="所属租户"))
        op.execute(sa.text(
            f"UPDATE {table} SET tenant_id = (SELECT id FROM tenants WHERE slug='default') "
            "WHERE tenant_id IS NULL"
        ))
        op.create_index(op.f(f"ix_{table}_tenant_id"), table, ["tenant_id"], unique=False)
        if table != "llm_providers":
            op.alter_column(table, "tenant_id", existing_type=sa.Integer(), nullable=False)

    # 4 表唯一约束 → (tenant_id, col)
    op.drop_index("name", table_name="spider_definitions")
    op.create_unique_constraint(
        "uq_spider_definitions_tenant_name", "spider_definitions", ["tenant_id", "name"])
    op.drop_constraint("uq_llm_providers_name", "llm_providers", type_="unique")
    op.create_unique_constraint(
        "uq_llm_providers_tenant_name", "llm_providers", ["tenant_id", "name"])
    op.drop_index("name", table_name="spider_task_templates")
    op.create_unique_constraint(
        "uq_task_templates_tenant_name", "spider_task_templates", ["tenant_id", "name"])

    # 用量表唯一键 3→4 列（10.2-C：一次改对，SaaS 免二次迁移）
    op.drop_constraint("uq_llm_usage_dim", "llm_token_usage", type_="unique")
    op.create_unique_constraint(
        "uq_llm_usage_dim", "llm_token_usage",
        ["tenant_id", "provider_name", "model", "stat_date"])


def downgrade() -> None:
    """回滚租户化（列删除 + 唯一约束还原）"""
    op.drop_constraint("uq_llm_usage_dim", "llm_token_usage", type_="unique")
    op.create_unique_constraint("uq_llm_usage_dim", "llm_token_usage",
                                ["provider_name", "model", "stat_date"])

    op.drop_constraint("uq_task_templates_tenant_name", "spider_task_templates", type_="unique")
    op.create_index("name", "spider_task_templates", ["name"], unique=True)
    op.drop_constraint("uq_llm_providers_tenant_name", "llm_providers", type_="unique")
    op.create_unique_constraint("uq_llm_providers_name", "llm_providers", ["name"])
    op.drop_constraint("uq_spider_definitions_tenant_name", "spider_definitions", type_="unique")
    op.create_index("name", "spider_definitions", ["name"], unique=True)

    for table in reversed(TENANT_TABLES):
        op.drop_index(op.f(f"ix_{table}_tenant_id"), table_name=table)
        op.drop_column(table, "tenant_id")

    op.drop_constraint("uq_users_tenant_username", "users", type_="unique")
    op.create_index("username", "users", ["username"], unique=True)
    op.drop_index(op.f("ix_users_tenant_id"), table_name="users")
    op.drop_column("users", "is_platform_admin")
    op.drop_column("users", "tenant_role")
    op.drop_column("users", "tenant_id")

    op.drop_index(op.f("ix_tenants_slug"), table_name="tenants")
    op.drop_table("tenants")
