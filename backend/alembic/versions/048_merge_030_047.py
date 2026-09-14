"""merge Alembic heads 030 + 047（039 后分叉收口）

Revision ID: 048
Revises: 030, 047
Create Date: 2026-09-14

039 后两线：028→029→030（api_keys / 计价列 / last_login）与 040→047（价目+中转）。
040 已覆盖 029 的 plans/orders，禁止再双建。本修订无 DDL；028–030 与 040 已幂等。
"""
from typing import Sequence, Union

revision: str = "048"
down_revision: Union[str, Sequence[str], None] = ("030", "047")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    return


def downgrade() -> None:
    raise NotImplementedError(
        "048 是 030+047 的 merge；请指定单一父修订。生产禁止 downgrade past 037"
    )
