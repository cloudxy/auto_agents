"""add user role column and operation_logs table

Revision ID: 004
Revises: 003
Create Date: 2026-08-25 14:00:00.000000

阶段 2.3 数据库变更（RBAC 与审计）：
- users 增加 role（admin/operator/viewer，默认 operator；存量 is_admin=1 回填为 admin）
- 新增 operation_logs 表（高危操作审计留痕）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级数据库结构"""
    op.add_column('users', sa.Column('role', sa.String(length=20), nullable=False, server_default='operator'))
    # 存量管理员回填（is_admin 为历史标记，role 为新契约）
    op.execute("UPDATE users SET role = 'admin' WHERE is_admin = 1")

    op.create_table(
        'operation_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('actor_name', sa.String(length=50), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('target', sa.String(length=100), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_operation_logs_actor_id'), 'operation_logs', ['actor_id'], unique=False)
    op.create_index(op.f('ix_operation_logs_action'), 'operation_logs', ['action'], unique=False)
    op.create_index(op.f('ix_operation_logs_created_at'), 'operation_logs', ['created_at'], unique=False)


def downgrade() -> None:
    """降级数据库结构"""
    op.drop_index(op.f('ix_operation_logs_created_at'), table_name='operation_logs')
    op.drop_index(op.f('ix_operation_logs_action'), table_name='operation_logs')
    op.drop_index(op.f('ix_operation_logs_actor_id'), table_name='operation_logs')
    op.drop_table('operation_logs')
    op.drop_column('users', 'role')
