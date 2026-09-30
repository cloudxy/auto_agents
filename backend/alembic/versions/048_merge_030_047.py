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
    # 审计 BUG-42：merge 修订本身无 DDL，降级即回到两个父修订（030、047），无需任何操作。
    # 原先抛 NotImplementedError，使任何穿过 048 的回滚（含保真往返测试）一律失败，
    # 真实回滚下限被卡在 048。「生产禁止 downgrade past 037」是运维约束，不应由 merge 修订代为执行
    return None
