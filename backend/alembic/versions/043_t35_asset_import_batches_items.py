"""能力资产导入两表（asset_import_batches / asset_import_items）——FR-100 / ADR-0023

Revision ID: 043
Revises: 042
Create Date: 2026-09-11

feat-product-complete T-35（contract §11 / db-spec §16.5）：
- asset_import_batches：一行 = 一次导入（含部分成功）；平台级 tenant_id 恒 NULL
  （模型禁 TenantMixin，TENANT_EXEMPT_TABLES 同 PR 登记，PIT-3 与 product_events 同款）。
- asset_import_items：batch_id CASCADE（明细=批的组合子行；批无删除入口，防御性）；
  asset_id → capability_assets RESTRICT（provenance 回放链保链）；
  succeeded/failed/skipped + 中文原因（GWT-100.2/100.3/100.5/100.7）。
- 纯新建表（expand-only，无破坏性变更）；down = 按建表逆序 drop 两表。
- 幂等键 = 既有 capability_assets.uq_asset_type_name_alive（不加列不加键）；
  沙箱是文件系统不是库表（db-spec §16.5），库内只落两表回放结果。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "043"
down_revision: Union[str, Sequence[str], None] = "042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "asset_import_batches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False,
                  comment="代理主键（跟仓）"),
        sa.Column("origin", sa.String(length=16), nullable=False,
                  comment="file/directory（GWT-92.9 同字面量）"),
        sa.Column("status", sa.String(length=16), nullable=False,
                  server_default="running",
                  comment="running/completed（含部分成功）/failed（整批失败）；应用层校验"),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0",
                  comment="= succeeded+failed+skipped；批结束写一次（非增量维护）"),
        sa.Column("succeeded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0",
                  comment="幂等跳过条目（GWT-100.8：目录已有行不产生第二行）"),
        sa.Column("created_by", sa.String(length=64), nullable=True,
                  comment="操作者用户名；NULL=系统路径（预留）。仅平台超管可导入"),
        sa.Column("tenant_id", sa.Integer(), nullable=True,
                  comment="平台级恒 NULL（TENANT_EXEMPT 登记）"),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP"), comment="批开始（记录时间）"),
        sa.Column("finished_at", sa.DateTime(), nullable=True,
                  comment="批结束（业务时间）；NULL=未结束"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_table(
        "asset_import_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False,
                  comment="代理主键"),
        sa.Column("batch_id", sa.Integer(), nullable=False,
                  comment="所属批次；CASCADE=明细为批的组合子行（批无删除入口，防御性）"),
        sa.Column("asset_type", sa.String(length=16), nullable=False,
                  comment="skill/agent/command/plugin；类型由导入过程判定（GWT-100.4）"),
        sa.Column("name", sa.String(length=128), nullable=False,
                  comment="资产目录名（与 capability_assets.name 同宽同语义=幂等键组件）"),
        sa.Column("status", sa.String(length=16), nullable=False,
                  comment="succeeded/failed/skipped（应用层校验）"),
        sa.Column("reason", sa.String(length=512), nullable=True,
                  comment="中文失败原因（不合法/超大/路径逃逸）；NULL=成功或跳过无需原因"),
        sa.Column("asset_id", sa.Integer(), nullable=True,
                  comment="成功时 FK→capability_assets.id（RESTRICT 保回放链）；NULL=失败/跳过。provenance 入口"),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP"), comment="记录时间"),
        sa.ForeignKeyConstraint(["batch_id"], ["asset_import_batches.id"],
                                ondelete="CASCADE", name="fk_import_items_batch"),
        sa.ForeignKeyConstraint(["asset_id"], ["capability_assets.id"],
                                ondelete="RESTRICT", name="fk_import_items_asset"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_import_items_batch", "asset_import_items", ["batch_id"])


def downgrade() -> None:
    # MySQL 1553：FK 在场时索引不可删——先撤约束再撤索引，最后按建表逆序 drop 两表
    op.drop_constraint("fk_import_items_batch", "asset_import_items", type_="foreignkey")
    op.drop_constraint("fk_import_items_asset", "asset_import_items", type_="foreignkey")
    op.drop_index("idx_import_items_batch", table_name="asset_import_items")
    op.drop_table("asset_import_items")
    op.drop_table("asset_import_batches")
