"""add ai_plans table

Revision ID: 009
Revises: 008
Create Date: 2026-08-29 14:00:00.000000

阶段二 AI 智能采集核心（AI 采集计划状态机）：
- ai_plans：目标 URL → LLM 规划 flow 流程 → 试采验证 → 注册爬虫定义
- plan_json / generated_params 为 JSON 列（流程定义与任务参数均可追溯）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级数据库结构"""
    op.create_table(
        'ai_plans',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('target_url', sa.String(length=500), nullable=False, comment='目标页面 URL'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='draft',
                  comment='状态：draft/planning/testing/registered/failed'),
        sa.Column('plan_json', sa.JSON(), nullable=True,
                  comment='LLM 产出（flow 流程定义 + test_history + html_sample 等元数据）'),
        sa.Column('generated_params', sa.JSON(), nullable=True,
                  comment='组装后的 flow_generic 任务参数'),
        sa.Column('test_task_id', sa.Integer(), nullable=True, comment='最近一次试采的爬虫任务 ID'),
        sa.Column('iteration_count', sa.Integer(), nullable=False, server_default='0',
                  comment='自动修复迭代次数'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='失败原因'),
        sa.Column('created_by', sa.String(length=64), nullable=True, comment='创建人用户名'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'),
                  nullable=True, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'),
                  nullable=True, comment='更新时间'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ai_plans_target_url'), 'ai_plans', ['target_url'])


def downgrade() -> None:
    """回滚数据库结构"""
    op.drop_index(op.f('ix_ai_plans_target_url'), table_name='ai_plans')
    op.drop_table('ai_plans')
