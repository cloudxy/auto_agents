"""SaaS 化拓展：角色权限 DB 化 + 部门组织树（roles / departments + users.department_id）

Revision ID: 022
Revises: 021
Create Date: 2026-09-03

- roles 表 + 内置三角色种子（权限码迁自 auth.py _ROLE_PERMISSIONS 硬编码单源）
- departments 表（租户内部门，软删除）
- users.department_id（部门挂接；NULL=未分组）
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "022"
down_revision: Union[str, Sequence[str], None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 内置角色种子（与 auth.py _ROLE_PERMISSIONS 当前值一致——迁移后 DB 为唯一源）
_SEED_ROLES = [
    ("admin", "管理员", "全权：含平台配置/用户/渠道治理", [
        'menu:dashboard', 'menu:spiders', 'menu:spiders.tasks', 'menu:spiders.logs',
        'menu:users', 'menu:data', 'menu:settings', 'menu:ai', 'menu:skills',
        'menu:members', 'menu:usage', 'menu:platform-ops', 'menu:logs',
        'menu:llm', 'menu:newapi',
        'btn:create', 'btn:delete', 'btn:schedule', 'btn:skill:edit', 'btn:skill:admin',
    ]),
    ("operator", "操作员", "业务执行：创建/运行任务与技能矫正", [
        'menu:dashboard', 'menu:spiders', 'menu:spiders.tasks', 'menu:spiders.logs',
        'menu:data', 'menu:ai', 'menu:skills', 'menu:members', 'menu:usage',
        'btn:create', 'btn:skill:edit',
    ]),
    ("viewer", "只读", "查看业务数据，无写操作", [
        'menu:dashboard', 'menu:spiders', 'menu:spiders.tasks', 'menu:spiders.logs',
        'menu:ai', 'menu:skills', 'menu:members', 'menu:usage',
    ]),
]


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("role_key", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_key", name="uq_roles_key"),
    )
    # 数据回填 backfill：内置三角色种子（migration data）
    for key, name, desc, perms in _SEED_ROLES:
        op.execute(sa.text(
            f"INSERT INTO roles (role_key, name, description, permissions, is_builtin) "
            f"VALUES ('{key}', '{name}', '{desc}', "
            f"'{__import__('json').dumps(perms, ensure_ascii=False)}', 1)"
        ))

    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_departments_tenant_name"),
    )
    op.create_index(op.f("ix_departments_tenant_id"), "departments", ["tenant_id"])
    op.create_index(op.f("ix_departments_deleted_at"), "departments", ["deleted_at"])

    op.add_column("users", sa.Column("department_id", sa.Integer(), nullable=True,
                                     comment="所属部门（departments.id；SaaS 组织树一层）"))


def downgrade() -> None:
    op.drop_column("users", "department_id")
    op.drop_index(op.f("ix_departments_deleted_at"), table_name="departments")
    op.drop_index(op.f("ix_departments_tenant_id"), table_name="departments")
    op.drop_table("departments")
    op.execute(sa.text("DELETE FROM roles WHERE is_builtin = 1"))
    op.drop_table("roles")
