"""last_login / skill downloads / result hash unique / builtin role perms

Revision ID: 030
Revises: 029
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "030"
down_revision: Union[str, Sequence[str], None] = "029"
branch_labels = None
depends_on = None

_VIEWER = (
    '["menu:dashboard","menu:spiders","menu:spiders.tasks","menu:spiders.logs",'
    '"menu:spiders.nodes","menu:ai","menu:skills"]'
)
_OPERATOR = (
    '["menu:dashboard","menu:spiders","menu:spiders.tasks","menu:spiders.logs",'
    '"menu:spiders.nodes","menu:data","menu:ai","menu:skills",'
    '"btn:create","btn:skill:edit"]'
)
_ADMIN = (
    '["menu:dashboard","menu:spiders","menu:spiders.tasks","menu:spiders.logs",'
    '"menu:spiders.nodes","menu:users","menu:data","menu:settings","menu:ai",'
    '"menu:skills","menu:members","menu:usage","menu:platform-ops","menu:logs",'
    '"menu:llm","menu:newapi","btn:create","btn:delete","btn:schedule",'
    '"btn:skill:edit","btn:skill:admin"]'
)


def upgrade() -> None:
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "skills",
        sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "uq_spider_results_tenant_spider_hash",
        "spider_results",
        ["tenant_id", "spider_name", "content_hash"],
        unique=True,
    )
    op.execute(sa.text(f"UPDATE roles SET permissions = '{_VIEWER}' WHERE role_key = 'viewer'"))
    op.execute(sa.text(f"UPDATE roles SET permissions = '{_OPERATOR}' WHERE role_key = 'operator'"))
    op.execute(sa.text(f"UPDATE roles SET permissions = '{_ADMIN}' WHERE role_key = 'admin'"))


def downgrade() -> None:
    op.execute(sa.text("UPDATE roles SET permissions = '[]' WHERE role_key IN ('viewer','operator','admin')"))
    op.drop_index("uq_spider_results_tenant_spider_hash", table_name="spider_results")
    op.drop_column("skills", "download_count")
    op.drop_column("users", "last_login_at")
