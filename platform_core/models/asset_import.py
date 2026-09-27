"""能力资产导入域模型（FR-100 / ADR-0023 / 迁移 043）

一行批次 = 一次导入（含部分成功）；一行明细 = 一个条目的处置结果。
平台级表：tenant_id 恒 NULL——禁止 TenantMixin，必须登记 TENANT_EXEMPT_TABLES
（PIT-3，与 product_events 同款同 PR）。沙箱是文件系统不是库表（db-spec §16.5），
库内只落两表回放结果；provenance 经 asset_import_items.asset_id 反查回放。
两表均不加软删（审计/子表，豁免矩阵）。
"""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.sql import func

from platform_core.models.base import Base


class AssetImportBatch(Base):
    """一次能力资产导入（含部分成功）"""

    __tablename__ = "asset_import_batches"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="代理主键（跟仓）")
    origin = Column(String(16), nullable=False, comment="file/directory（GWT-92.9 同字面量）")
    status = Column(
        String(16), nullable=False, default="running", server_default="running",
        comment="running/completed（含部分成功）/failed（整批失败）；应用层校验",
    )
    total_count = Column(
        Integer, nullable=False, default=0, server_default="0",
        comment="= succeeded+failed+skipped；批结束写一次（非增量维护）",
    )
    succeeded_count = Column(Integer, nullable=False, default=0, server_default="0")
    failed_count = Column(Integer, nullable=False, default=0, server_default="0")
    skipped_count = Column(
        Integer, nullable=False, default=0, server_default="0",
        comment="幂等跳过条目（GWT-100.8：目录已有行不产生第二行）",
    )
    created_by = Column(
        String(64), nullable=True, comment="操作者用户名；NULL=系统路径（预留）。仅平台超管可导入",
    )
    tenant_id = Column(Integer, nullable=True, comment="平台级恒 NULL（TENANT_EXEMPT 登记）")
    created_at = Column(
        DateTime, nullable=False, server_default=func.current_timestamp(), comment="批开始（记录时间）",
    )
    finished_at = Column(DateTime, nullable=True, comment="批结束（业务时间）；NULL=未结束")


class AssetImportItem(Base):
    """一次导入中一个条目的处置结果"""

    __tablename__ = "asset_import_items"
    __table_args__ = (
        Index("idx_import_items_batch", "batch_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="代理主键")
    batch_id = Column(
        Integer,
        ForeignKey("asset_import_batches.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属批次；CASCADE=明细为批的组合子行（批无删除入口，防御性）",
    )
    asset_type = Column(
        String(16), nullable=False,
        comment="skill/agent/command/plugin；类型由导入过程判定（GWT-100.4）",
    )
    name = Column(
        String(128), nullable=False,
        comment="资产目录名（与 capability_assets.name 同宽同语义=幂等键组件）",
    )
    status = Column(String(16), nullable=False, comment="succeeded/failed/skipped（应用层校验）")
    reason = Column(
        String(512), nullable=True,
        comment="中文失败原因（不合法/超大/路径逃逸）；NULL=成功或跳过无需原因",
    )
    asset_id = Column(
        Integer,
        ForeignKey("capability_assets.id", ondelete="RESTRICT"),
        nullable=True,
        comment="成功时 FK→capability_assets.id（RESTRICT 保回放链）；NULL=失败/跳过。provenance 入口",
    )
    created_at = Column(
        DateTime, nullable=False, server_default=func.current_timestamp(), comment="记录时间",
    )
