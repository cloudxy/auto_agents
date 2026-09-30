"""orders.amount_sig：下单金额快照签名（审计 BUG-24 / 收费闸）

Revision ID: 052
Revises: 051
Create Date: 2026-09-28

确认收款原先拿订单快照与「当前价目」比对：调价后已下单未确认的订单永远确认不了
（卡死）；而直接信任快照又会丢掉 GWT-M31.4 [SEC-3] 的防篡改。改为下单时对
(order_no, product_code, amount_cents) 做 HMAC 签名入列，确认时验签：
验签通过即以快照为准（调价不影响在途订单），签名不符视为篡改拒绝；
存量行 amount_sig 为 NULL，确认时回退旧的现价比对。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "052"
down_revision: Union[str, Sequence[str], None] = "051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "amount_sig", sa.String(64), nullable=True,
            comment="下单金额快照 HMAC（防篡改）；NULL=存量行，确认时回退现价比对",
        ),
    )


def downgrade() -> None:
    op.drop_column("orders", "amount_sig")
