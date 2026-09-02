"""add alert_rules table

Revision ID: 8551b2c539b2
Revises: ce5210dedbd4
Create Date: 2026-08-26 11:07:48.960583

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
# SM-EXEMPT: 历史迁移（已部署），expand-contract 检查不追溯
# expand-contract: grandfathered
revision: str = '8551b2c539b2'
down_revision: Union[str, Sequence[str], None] = 'ce5210dedbd4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('alert_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('spider_name', sa.String(length=100), nullable=True),
    sa.Column('rule_type', sa.String(length=50), nullable=False),
    sa.Column('threshold', sa.Float(), nullable=False),
    sa.Column('window_minutes', sa.Integer(), nullable=True),
    sa.Column('severity', sa.String(length=20), nullable=True),
    sa.Column('channels', sa.Text(), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=True),
    sa.Column('last_triggered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_alert_rules_id'), 'alert_rules', ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_alert_rules_id'), table_name='alert_rules')
    op.drop_table('alert_rules')
