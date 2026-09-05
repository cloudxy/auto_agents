"""baseline: create spider_tasks & system_configs (chain-external table repair, E0.2)

Revision ID: 002a
Revises: 002
Create Date: 2026-08-31

链外表修复（审计 §3.1-T2 / 总方案 §4-E0.2）：
- spider_tasks 与 system_configs 历史上由 create_all bootstrap 预建后 stamp head，
  从未进迁移链——空库 `alembic upgrade head` 在 003（对 spider_tasks add_column）即断。
- 本基线插在 002 与 003 之间：spider_tasks 按"003 前形态"建表（无 priority/retry_count/
  started_at，三者由 003/006 补齐），保证全链可重放且终点与模型 create_all 一致。
- 已 stamp 的存量库不经过本版本（版本指针已在其后），无兼容风险。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
# SM-EXEMPT: 历史迁移（已部署），expand-contract 检查不追溯
# expand-contract: grandfathered
revision: str = "002a"
down_revision: Union[str, Sequence[str], None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """按 003 前形态建 spider_tasks + 建 system_configs"""
    op.create_table(
        "spider_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("spider_name", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "completed", "failed", name="spider_task_status"),
            nullable=True,
        ),
        sa.Column("params", sa.Text(), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_spider_tasks_id"), "spider_tasks", ["id"], unique=False)
    op.create_index(op.f("ix_spider_tasks_spider_name"), "spider_tasks", ["spider_name"], unique=False)

    op.create_table(
        "system_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("config_key", sa.String(length=50), nullable=False),
        sa.Column("config_value", sa.Text(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("config_key", name="uq_system_configs_config_key"),
    )
    op.create_index(op.f("ix_system_configs_id"), "system_configs", ["id"], unique=False)
    op.create_index(op.f("ix_system_configs_config_key"), "system_configs", ["config_key"], unique=False)


def downgrade() -> None:
    """回滚基线（注意：spider_tasks 含业务数据，downgrade 过此版本会连带删表）"""
    op.drop_index(op.f("ix_system_configs_config_key"), table_name="system_configs")
    op.drop_index(op.f("ix_system_configs_id"), table_name="system_configs")
    op.drop_table("system_configs")
    op.drop_index(op.f("ix_spider_tasks_spider_name"), table_name="spider_tasks")
    op.drop_index(op.f("ix_spider_tasks_id"), table_name="spider_tasks")
    op.drop_table("spider_tasks")
