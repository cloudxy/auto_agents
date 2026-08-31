"""add llm_token_usage table (P0-3 LLM 用量持久化)

Revision ID: 013
Revises: 012
Create Date: 2026-08-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '013'
down_revision: Union[str, Sequence[str], None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('llm_token_usage',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('provider_id', sa.Integer(), nullable=True),
    sa.Column('provider_name', sa.String(length=64), nullable=False),
    sa.Column('model', sa.String(length=128), nullable=False),
    sa.Column('stat_date', sa.Date(), nullable=False),
    sa.Column('prompt_tokens', sa.BigInteger(), nullable=False, server_default='0'),
    sa.Column('completion_tokens', sa.BigInteger(), nullable=False, server_default='0'),
    sa.Column('total_tokens', sa.BigInteger(), nullable=False, server_default='0'),
    sa.Column('request_count', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('failed_count', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider_name', 'model', 'stat_date', name='uq_llm_usage_dim')
    )
    op.create_index(op.f('ix_llm_token_usage_provider_name'), 'llm_token_usage', ['provider_name'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_llm_token_usage_provider_name'), table_name='llm_token_usage')
    op.drop_table('llm_token_usage')
