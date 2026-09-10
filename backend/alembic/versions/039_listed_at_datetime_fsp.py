"""t28 listed_at DATETIME(6)；GWT-37.6 MySQL isoformat 往返

Revision ID: 039
Revises: 038
Create Date: 2026-09-10

QC cond-2：036 加列为 DATETIME (fsp=0)。PATCH listed 返回
datetime.isoformat() 微秒；unlist 再读 MySQL 截到秒并四舍五入。
DATETIME -> DATETIME(6) 是精度加宽（expand）：列仍在，无 DROP。
生产禁止 downgrade past 037。禁止复活 028/029/030。
隔离库可 039 <-> 038；业务库 auto_agents 禁止拿来做 down 实验。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME as MYSQL_DATETIME


revision: str = "039"
down_revision: Union[str, Sequence[str], None] = "038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COMMENT = "最近一次 listed；unlist 不清空；NULL=从未 listed"


def upgrade() -> None:
    op.alter_column(
        "capability_assets",
        "listed_at",
        existing_type=sa.DateTime(),
        type_=MYSQL_DATETIME(fsp=6),
        existing_nullable=True,
        existing_comment=_COMMENT,
        comment=_COMMENT,
    )


def downgrade() -> None:
    op.alter_column(
        "capability_assets",
        "listed_at",
        existing_type=MYSQL_DATETIME(fsp=6),
        type_=sa.DateTime(),
        existing_nullable=True,
        existing_comment=_COMMENT,
        comment=_COMMENT,
    )
