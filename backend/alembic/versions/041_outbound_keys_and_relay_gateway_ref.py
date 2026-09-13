"""outbound_keys + relay_tokens gateway ref (expand-only)

Revision ID: 041
Revises: 040
Create Date: 2026-09-11

feat-product-complete T-04（FR-51 前半 / ADR-0020 / db-spec §1 §5 §14）：
- 新表 outbound_keys：一行一把本企业出站拉数钥匙（hash 行；明文不落库）；
  TenantMixin 不豁免（PIT-3/4），tenant_id NOT NULL；
- relay_tokens expand：可空 gateway_key_id（LiteLLM 虚拟 Key 不透明引用，
  为 T-08 备列）+ spend_synced_at；UNIQUE(gateway_key_id)（多 NULL 合法）。
纯加法、可逆（down 只在隔离库验证；生产禁止 downgrade past 037）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "041"
down_revision: Union[str, Sequence[str], None] = "040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outbound_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("tenant_id", sa.Integer(), nullable=False, comment="所属租户（NOT NULL：禁止平台钥匙，PIT-4）"),
        sa.Column("name", sa.String(length=64), nullable=True, comment="备注名；NULL=未起名"),
        sa.Column("key_prefix", sa.String(length=16), nullable=False, comment="再进页可见前缀；不以 sk- 开头"),
        sa.Column("key_hash", sa.String(length=64), nullable=False, comment="SHA-256 指纹；明文不落库"),
        sa.Column("issued_by_user_id", sa.Integer(), nullable=False, comment="签发者用户 id；无 FK（用户可删，钥匙留审计）"),
        sa.Column("revoked_at", sa.DateTime(), nullable=True, comment="吊销时间；NULL=active，非空=revoked（终态）"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="签发时刻"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash", name="uk_outbound_keys_key_hash"),
    )
    op.create_index(
        "idx_outbound_keys_tenant_created", "outbound_keys", ["tenant_id", "created_at"],
    )
    op.add_column(
        "relay_tokens",
        sa.Column(
            "gateway_key_id", sa.String(length=191), nullable=True,
            comment="LiteLLM 虚拟 Key 稳定引用（不透明）；NULL=骨架签发未登记网关",
        ),
    )
    op.add_column(
        "relay_tokens",
        sa.Column(
            "spend_synced_at", sa.DateTime(), nullable=True,
            comment="最近一次网关 spend 回写 used_tokens 的时刻；NULL=从未同步",
        ),
    )
    # Step0 守卫（db-spec §8）：新列全 NULL 时必过；若隔离库回放数据出现重复
    # 网关引用则显式失败（停、问 pm），不带重复值建 UNIQUE
    bind = op.get_bind()
    duplicated = bind.execute(sa.text(
        "SELECT gateway_key_id, COUNT(*) AS c FROM relay_tokens "
        "WHERE gateway_key_id IS NOT NULL GROUP BY gateway_key_id HAVING c > 1"
    )).fetchall()
    if duplicated:
        raise RuntimeError(
            f"relay_tokens.gateway_key_id 存在重复非空值 {len(duplicated)} 组，禁止建 UNIQUE（db-spec §8：停、问 pm）"
        )
    op.create_unique_constraint(
        "uk_relay_tokens_gateway_key_id", "relay_tokens", ["gateway_key_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uk_relay_tokens_gateway_key_id", "relay_tokens", type_="unique")
    op.drop_column("relay_tokens", "spend_synced_at")
    op.drop_column("relay_tokens", "gateway_key_id")
    op.drop_index("idx_outbound_keys_tenant_created", table_name="outbound_keys")
    op.drop_table("outbound_keys")
