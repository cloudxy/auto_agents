"""DB 升级 2026-09 Phase B：横切功能表（标签/附件/通知/版本/工作流引擎 4 表）

Revision ID: 020
Revises: 019
Create Date: 2026-09-02

纯新增（create_table，无破坏性变更）；downgrade 整体 drop。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "020"
down_revision: Union[str, Sequence[str], None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DT = sa.DateTime(timezone=True)


def upgrade() -> None:
    # ── B1 标签系统 ──
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", _DT, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_tags_tenant_name"),
    )
    op.create_index(op.f("ix_tags_tenant_id"), "tags", ["tenant_id"])
    op.create_table(
        "taggings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("created_at", _DT, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_taggings_tag_id"), "taggings", ["tag_id"])
    op.create_index("uq_taggings_resource_tag", "taggings",
                    ["resource_type", "resource_id", "tag_id"], unique=True)

    # ── B2 附件系统 ──
    op.create_table(
        "attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("uploaded_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", _DT, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_attachments_tenant_id"), "attachments", ["tenant_id"])
    op.create_index("ix_attachments_resource", "attachments", ["resource_type", "resource_id"])

    # ── B3 通知系统 ──
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("resource_type", sa.String(length=32), nullable=True),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("read_at", _DT, nullable=True),
        sa.Column("created_at", _DT, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_notifications_tenant_id"), "notifications", ["tenant_id"])
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"])
    op.create_index("ix_notifications_inbox", "notifications",
                    ["tenant_id", "user_id", "is_read", "created_at"])

    # ── B4 版本系统 ──
    op.create_table(
        "resource_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("change_summary", sa.String(length=512), nullable=True),
        sa.Column("changed_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", _DT, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("resource_type", "resource_id", "version_number",
                            name="uq_resource_versions_rid"),
    )
    op.create_index(op.f("ix_resource_versions_tenant_id"), "resource_versions", ["tenant_id"])
    op.create_index(op.f("ix_resource_versions_resource_id"), "resource_versions", ["resource_id"])

    # ── B5 通用工作流引擎（4 表）──
    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("steps_config", sa.JSON(), nullable=False),
        sa.Column("triggers_config", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", _DT, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", _DT, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_workflow_definitions_tenant_name"),
    )
    op.create_index(op.f("ix_workflow_definitions_tenant_id"), "workflow_definitions", ["tenant_id"])
    op.create_table(
        "workflow_instances",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("definition_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("current_step", sa.String(length=64), nullable=True),
        sa.Column("started_at", _DT, nullable=True),
        sa.Column("completed_at", _DT, nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", _DT, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", _DT, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["definition_id"], ["workflow_definitions.id"]),
    )
    op.create_index(op.f("ix_workflow_instances_tenant_id"), "workflow_instances", ["tenant_id"])
    op.create_index("ix_workflow_instances_tenant_status", "workflow_instances",
                    ["tenant_id", "status", "created_at"])
    op.create_table(
        "workflow_steps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instance_id", sa.Integer(), nullable=False),
        sa.Column("step_key", sa.String(length=64), nullable=False),
        sa.Column("step_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("input", sa.JSON(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("started_at", _DT, nullable=True),
        sa.Column("completed_at", _DT, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["instance_id"], ["workflow_instances.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_workflow_steps_instance_id"), "workflow_steps", ["instance_id"])
    op.create_table(
        "workflow_transitions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("step_id", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=True),
        sa.Column("to_status", sa.String(length=16), nullable=False),
        sa.Column("trigger_type", sa.String(length=16), nullable=False),
        sa.Column("operator_id", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", _DT, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["step_id"], ["workflow_steps.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_workflow_transitions_step_id"), "workflow_transitions", ["step_id"])


def downgrade() -> None:
    # T9 修复：原版在 drop_table 前显式 drop_index 了 4 个 FK 依赖索引
    # （workflow_transitions.step_id / workflow_steps.instance_id /
    #  notifications.user_id / taggings.tag_id），MySQL 1553
    # "Cannot drop index: needed in a foreign key constraint" 拒绝——down 实际跑不通。
    # drop_table 会连带删除本表全部索引与 FK，这些 drop_index 是冗余且非法的，直接移除。
    op.drop_table("workflow_transitions")
    op.drop_table("workflow_steps")
    op.drop_index("ix_workflow_instances_tenant_status", table_name="workflow_instances")
    op.drop_index(op.f("ix_workflow_instances_tenant_id"), table_name="workflow_instances")
    op.drop_table("workflow_instances")
    op.drop_index(op.f("ix_workflow_definitions_tenant_id"), table_name="workflow_definitions")
    op.drop_table("workflow_definitions")
    op.drop_index(op.f("ix_resource_versions_resource_id"), table_name="resource_versions")
    op.drop_index(op.f("ix_resource_versions_tenant_id"), table_name="resource_versions")
    op.drop_table("resource_versions")
    op.drop_index("ix_notifications_inbox", table_name="notifications")
    op.drop_index(op.f("ix_notifications_tenant_id"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_attachments_resource", table_name="attachments")
    op.drop_index(op.f("ix_attachments_tenant_id"), table_name="attachments")
    op.drop_table("attachments")
    op.drop_index("uq_taggings_resource_tag", table_name="taggings")
    op.drop_table("taggings")
    op.drop_index(op.f("ix_tags_tenant_id"), table_name="tags")
    op.drop_table("tags")
