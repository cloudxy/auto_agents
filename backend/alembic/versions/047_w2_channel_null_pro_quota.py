"""W2：orders.channel 可空去 default；专业档配额对齐定价页；补企业档价目。

Revision ID: 047
Revises: 046
Create Date: 2026-09-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "047"
down_revision: Union[str, Sequence[str], None] = "046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRO_QUOTA = '{"task_concurrency":50,"result_storage":200000,"llm_tokens_month":5000000}'
_PRO_QUOTA_040 = '{"task_concurrency":20,"result_storage":500000,"llm_tokens_month":5000000}'
_ENT_QUOTA = '{"task_concurrency":50,"result_storage":2000000,"llm_tokens_month":20000000}'


def upgrade() -> None:
    op.alter_column(
        "orders", "channel",
        existing_type=sa.String(length=16),
        nullable=True,
        existing_nullable=False,
        server_default=None,
        existing_server_default=sa.text("'offline'"),
        comment="alipay/wechat；NULL=W2 未选通道。禁止新写 offline",
    )
    op.execute(
        sa.text("UPDATE plans SET quota_json = :q WHERE slug = 'pro'").bindparams(q=_PRO_QUOTA)
    )
    op.execute(
        sa.text(
            "INSERT INTO plans (slug, name, price_cents, period, quota_json, is_public) "
            "SELECT 'enterprise', '企业档', 99900, 'month', :q, 1 "
            "WHERE NOT EXISTS (SELECT 1 FROM plans WHERE slug = 'enterprise')"
        ).bindparams(q=_ENT_QUOTA)
    )


def downgrade() -> None:
    # 回填: NULL channel → 040 default，再收紧 NOT NULL（禁止未填就 MODIFY）
    op.execute(sa.text(
        "UPDATE orders SET channel = 'offline' WHERE channel IS NULL"
    ))
    # 回填: pro.quota_json 写回 040 种子；不碰 tenants.quota
    op.execute(
        sa.text("UPDATE plans SET quota_json = :q WHERE slug = 'pro'").bindparams(
            q=_PRO_QUOTA_040
        )
    )
    # 回填: 无 orders/tenant_subscriptions FK 才删 enterprise；有引用则保留
    op.execute(sa.text(
        "DELETE FROM plans WHERE slug = 'enterprise' "
        "AND NOT EXISTS (SELECT 1 FROM orders WHERE orders.plan_id = plans.id) "
        "AND NOT EXISTS ("
        "SELECT 1 FROM tenant_subscriptions "
        "WHERE tenant_subscriptions.plan_id = plans.id)"
    ))
    op.alter_column(
        "orders", "channel",
        existing_type=sa.String(length=16),
        nullable=False,
        existing_nullable=True,
        server_default=sa.text("'offline'"),
        comment="offline/alipay/wechat",
    )
