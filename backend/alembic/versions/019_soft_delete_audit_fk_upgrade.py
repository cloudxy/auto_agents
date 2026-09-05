"""DB 升级 2026-09 Phase A：软删除 + 审计 Mixin 存量改造 + 关键 FK 补全

Revision ID: 019
Revises: 018
Create Date: 2026-09-02

分步可逆（expand-contract）：
1. 加列：deleted_at（12 表，nullable+索引）/ created_by/updated_by（10 表，String(64) nullable）
2. 孤儿清理（数据回填 backfill）：加 FK 前清理无主行——2026-09 T9 起为「先归档
   进 _mig019_orphan_* 备份表再删」，downgrade 可按主键还原
3. 加 FK：spider_results.task_id / skill_reviews.skill_id / capability_{plugins,experts,teams}.asset_id /
   llm_token_usage.provider_id（MySQL 自动补 FK 索引，列均已带索引）
4. 补复合索引：spider_tasks(tenant_id,status) / spider_results(spider_name,created_at)
5. 修 bug：system_configs.updated_at 由 Python utcnow 改 DB CURRENT_TIMESTAMP

downgrade（T9 修复后完整可回滚）：
- 孤儿行从备份表还原（还原点在 FK 撤除后、019 新增列撤除前）
- spider_task_templates.created_by String→Integer 回退前，非数字用户名显式置 NULL
  （用户名→用户 ID 的映射信息不存在，语义翻译损耗显式化，杜绝截断报错/静默截断）

注：019 已应用于各环境的库不受本文件修改影响（alembic 只记版本号不重放），
修复在下一次 downgrade 019 时生效。

大表（spider_results / skill_reviews）加列与加 FK 为在线 DDL（MySQL 8 INSTANT/INPLACE，
生产超大体量时可用 gh-ost 替代执行，锁表风险可控）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "019"
down_revision: Union[str, Sequence[str], None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 软删除 12 表（豁免矩阵：审计/历史/子表/聚合/系统表不进此列）
SOFT_DELETE_TABLES = [
    "tenants", "users",
    "spider_tasks", "spider_results", "spider_definitions", "spider_schedules",
    "llm_providers", "ai_plans", "skills", "capability_assets",
    "alert_rules", "spider_task_templates",
]

# 审计 10 表（ai_plans 已有 created_by 列；spider_task_templates.created_by 存量为 Integer 需改型）
AUDIT_BOTH_TABLES = [
    "spider_tasks", "spider_results", "spider_definitions", "spider_schedules",
    "llm_providers", "skills", "capability_assets", "alert_rules",
]

# 孤儿组：(子表, 外键列, 父表)——与步骤 3 的 FK 清单一一对应。
# 2026-09 T9：孤儿清理由「直接 DELETE」改为「先归档进 _mig019_orphan_* 备份表再删」，
# downgrade 按 ID 还原（可回滚形式）。备份表仅在孤儿数 > 0 时创建——空库/干净库
# 零残留，不污染 test_alembic_baseline 的 create_all 表集合对拍。
_ORPHAN_GROUPS = [
    ("spider_results", "task_id", "spider_tasks"),
    ("skill_reviews", "skill_id", "skills"),
    ("capability_plugins", "asset_id", "capability_assets"),
    ("capability_experts", "asset_id", "capability_assets"),
    ("capability_teams", "asset_id", "capability_assets"),
]


def _backup_table_exists(name: str) -> bool:
    """备份表存在性探测（downgrade 还原路径用；MySQL information_schema）"""
    row = op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = :n"
    ), {"n": name}).scalar()
    return bool(row)


def upgrade() -> None:
    # ── 步骤 1：加列（全部 nullable，SM-5 安全）──
    for t in SOFT_DELETE_TABLES:
        op.add_column(t, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True,
                                   comment="软删除时间（NULL=存活）"))
        op.create_index(op.f(f"ix_{t}_deleted_at"), t, ["deleted_at"])

    for t in AUDIT_BOTH_TABLES:
        op.add_column(t, sa.Column("created_by", sa.String(length=64), nullable=True, comment="创建人用户名"))
        op.add_column(t, sa.Column("updated_by", sa.String(length=64), nullable=True, comment="最后修改人用户名"))

    # ai_plans：created_by 已存在（String(64)，迁移 009），仅补 updated_by
    op.add_column("ai_plans", sa.Column("updated_by", sa.String(length=64), nullable=True, comment="最后修改人用户名"))

    # spider_task_templates：created_by 存量 Integer（用户 ID）→ String(64)（用户名，AuditMixin 对齐）
    op.alter_column("spider_task_templates", "created_by",
                    existing_type=sa.Integer(), type_=sa.String(length=64), existing_nullable=True)
    op.add_column("spider_task_templates", sa.Column("updated_by", sa.String(length=64), nullable=True, comment="最后修改人用户名"))

    # ── 步骤 2：孤儿清理（数据回填 backfill / migration data，加 FK 前置条件）──
    # T9：先归档（CREATE TABLE ... AS SELECT 全行快照）再 DELETE，down 可按主键还原。
    # 孤儿判定加 c.{col} IS NOT NULL 守卫：NULL 外键不是孤儿（FK 对 NULL 不生效），
    # 旧写法会把 NULL 外键行一并误删。
    for table, col, parent in _ORPHAN_GROUPS:
        orphan_n = op.get_bind().execute(sa.text(
            f"SELECT COUNT(*) FROM {table} c LEFT JOIN {parent} p ON c.{col} = p.id "
            f"WHERE c.{col} IS NOT NULL AND p.id IS NULL"
        )).scalar()
        if orphan_n:
            backup = f"_mig019_orphan_{table}"
            op.execute(sa.text(
                f"CREATE TABLE {backup} AS SELECT c.* FROM {table} c "
                f"LEFT JOIN {parent} p ON c.{col} = p.id "
                f"WHERE c.{col} IS NOT NULL AND p.id IS NULL"
            ))
        op.execute(sa.text(
            f"DELETE c FROM {table} c LEFT JOIN {parent} p ON c.{col} = p.id "
            f"WHERE c.{col} IS NOT NULL AND p.id IS NULL"
        ))
    # 聚合表孤儿 provider_id 置 NULL（历史用量保留，provider 维度不失义）
    # T9：(id, provider_id) 映射先归档，down 可还原原值
    orphan_usage_n = op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM llm_token_usage "
        "WHERE provider_id IS NOT NULL AND provider_id NOT IN (SELECT id FROM llm_providers)"
    )).scalar()
    if orphan_usage_n:
        op.execute(sa.text(
            "CREATE TABLE _mig019_orphan_llm_token_usage AS "
            "SELECT id, provider_id FROM llm_token_usage "
            "WHERE provider_id IS NOT NULL AND provider_id NOT IN (SELECT id FROM llm_providers)"
        ))
    op.execute(sa.text(
        "UPDATE llm_token_usage SET provider_id = NULL "
        "WHERE provider_id IS NOT NULL AND provider_id NOT IN (SELECT id FROM llm_providers)"
    ))

    # ── 步骤 3：FK 补全（5 处关键关联，llm_provider_models 既有不重）──
    op.create_foreign_key("fk_spider_results_task", "spider_results", "spider_tasks",
                          ["task_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_skill_reviews_skill", "skill_reviews", "skills",
                          ["skill_id"], ["id"])
    op.create_foreign_key("fk_capability_plugins_asset", "capability_plugins", "capability_assets",
                          ["asset_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_capability_experts_asset", "capability_experts", "capability_assets",
                          ["asset_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_capability_teams_asset", "capability_teams", "capability_assets",
                          ["asset_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_llm_token_usage_provider", "llm_token_usage", "llm_providers",
                          ["provider_id"], ["id"])

    # ── 步骤 4：复合索引 ──
    op.create_index("ix_spider_tasks_tenant_status", "spider_tasks", ["tenant_id", "status"])
    op.create_index("ix_spider_results_name_created", "spider_results", ["spider_name", "created_at"])

    # ── 步骤 5：system_configs 时间戳 bug 修复（Python utctime → DB 受控时钟）──
    op.alter_column("system_configs", "updated_at", existing_type=sa.DateTime(),
                    server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"))


def downgrade() -> None:
    # 逆序回滚：索引 → FK → 孤儿还原 → 列 → bug 还原
    op.alter_column("system_configs", "updated_at", existing_type=sa.DateTime(),
                    server_default=None)

    op.drop_index("ix_spider_results_name_created", table_name="spider_results")
    op.drop_index("ix_spider_tasks_tenant_status", table_name="spider_tasks")

    op.drop_constraint("fk_llm_token_usage_provider", "llm_token_usage", type_="foreignkey")
    op.drop_constraint("fk_capability_teams_asset", "capability_teams", type_="foreignkey")
    op.drop_constraint("fk_capability_experts_asset", "capability_experts", type_="foreignkey")
    op.drop_constraint("fk_capability_plugins_asset", "capability_plugins", type_="foreignkey")
    op.drop_constraint("fk_skill_reviews_skill", "skill_reviews", type_="foreignkey")
    op.drop_constraint("fk_spider_results_task", "spider_results", type_="foreignkey")

    # ── T9：孤儿还原（数据回填 backfill / migration data，upgrade 归档行的对称逆）──
    # 必须在 FK 全部撤除之后（孤儿行本身违反 FK）、019 新增列撤除之前（备份表
    # 携带全行含 deleted_at/审计列）执行。CTAS 保序 → INSERT ... SELECT * 列序一致。
    for table, _col, _parent in _ORPHAN_GROUPS:
        backup = f"_mig019_orphan_{table}"
        if _backup_table_exists(backup):
            op.execute(sa.text(f"INSERT INTO {table} SELECT * FROM {backup}"))
            op.drop_table(backup)
    if _backup_table_exists("_mig019_orphan_llm_token_usage"):
        op.execute(sa.text(
            "UPDATE llm_token_usage u JOIN _mig019_orphan_llm_token_usage b ON u.id = b.id "
            "SET u.provider_id = b.provider_id"
        ))
        op.drop_table("_mig019_orphan_llm_token_usage")

    op.drop_column("spider_task_templates", "updated_by")
    # T9：String→Integer 回退守卫——019 之后业务写入的 created_by 是用户名（如
    # 'zhangsan'），旧语义（用户 ID）的映射信息不存在，无法无损回滚。非 1-9 位
    # 纯数字显式置 NULL（审计归属让位，语义翻译损耗在此写明），不让 ALTER 在
    # 严格模式下报错或静默截断（体检 F-09）。9 位上限 < INT 最大值，防越界。
    op.execute(sa.text(
        "UPDATE spider_task_templates SET created_by = NULL "
        "WHERE created_by IS NOT NULL AND created_by NOT REGEXP '^[0-9]{1,9}$'"
    ))
    op.alter_column("spider_task_templates", "created_by",
                    existing_type=sa.String(length=64), type_=sa.Integer(), existing_nullable=True)
    op.drop_column("ai_plans", "updated_by")

    for t in AUDIT_BOTH_TABLES:
        op.drop_column(t, "updated_by")
        op.drop_column(t, "created_by")

    for t in reversed(SOFT_DELETE_TABLES):
        op.drop_index(op.f(f"ix_{t}_deleted_at"), table_name=t)
        op.drop_column(t, "deleted_at")
