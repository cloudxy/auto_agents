"""add llm_providers table

Revision ID: 010
Revises: 009
Create Date: 2026-08-30 12:00:00.000000

阶段二 LLM 供应商管理（多供应商 DB 化 + 热切换）：
- llm_providers：供应商注册表（OpenAI 兼容协议），api_key_encrypted 仅存 Fernet 密文
- is_active 单激活互斥（全表至多一行），ai_planner 运行时配置优先取激活行，
  否则回退 config/default/llm.yml + .env 兜底（行为不变）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
# SM-EXEMPT: 历史迁移（已部署），expand-contract 检查不追溯
# expand-contract: grandfathered
revision: str = '010'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级数据库结构"""
    op.create_table(
        'llm_providers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('name', sa.String(length=100), nullable=False, comment='供应商名称（唯一）'),
        sa.Column('provider_type', sa.String(length=50), nullable=False,
                  server_default='openai_compatible', comment='协议类型（openai_compatible）'),
        sa.Column('base_url', sa.String(length=500), nullable=False,
                  comment='API 基地址（http/https）'),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True,
                  comment='Fernet 加密后的 API Key 密文（主密钥走 LLM_ENCRYPTION_KEY）'),
        sa.Column('model', sa.String(length=100), nullable=False, comment='默认模型名'),
        sa.Column('temperature', sa.Float(), nullable=False, server_default='0.2',
                  comment='采样温度（0-2）'),
        sa.Column('timeout', sa.Integer(), nullable=False, server_default='120',
                  comment='单次请求超时（秒）'),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='3',
                  comment='指数退避重试次数'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('0'),
                  comment='是否为当前激活供应商（全表至多一行）'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('1'),
                  comment='是否启用（禁用后即使激活也走 yml/env 兜底）'),
        sa.Column('remark', sa.String(length=255), nullable=True, comment='备注'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'),
                  nullable=True, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'),
                  nullable=True, comment='更新时间'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_llm_providers_name'),
    )
    op.create_index(op.f('ix_llm_providers_name'), 'llm_providers', ['name'])


def downgrade() -> None:
    """回滚数据库结构"""
    op.drop_index(op.f('ix_llm_providers_name'), table_name='llm_providers')
    op.drop_table('llm_providers')
