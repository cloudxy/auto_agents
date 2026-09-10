"""add spider_task_templates table

Revision ID: e7a6f5a12bc9
Revises: a1b2c3d4e5f6
Create Date: 2026-08-26 11:19:26.098481

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
# SM-EXEMPT: 历史迁移（已部署），expand-contract 检查不追溯
# expand-contract: grandfathered
revision: str = 'e7a6f5a12bc9'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('spider_task_templates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('spider_name', sa.String(length=100), nullable=False),
    sa.Column('params', sa.Text(), nullable=True),
    sa.Column('priority', sa.String(length=10), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_spider_task_templates_id'), 'spider_task_templates', ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_spider_task_templates_id'), table_name='spider_task_templates')
    op.drop_table('spider_task_templates')
