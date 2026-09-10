"""T9 迁移健康：软删表唯一键补删除标记（5 表）——删后可重建同名

Revision ID: 025
Revises: 024
Create Date: 2026-09-05

体检 F-03 per-table 处置（决策表全文见 .scratch/p0-p1-2026-09/issues/T9.md）：
- 本迁移改造（应用层「已存在」检查均带 deleted_at IS NULL——删后即视为可建，
  DB 唯一键必须与应用语义对齐，否则应用放行、DB 拒绝，IntegrityError 裸奔）：
    departments          uq_departments_tenant_name              (tenant_id, name)
    llm_providers        uq_llm_providers_tenant_name            (tenant_id, name)
    spider_definitions   uq_spider_definitions_tenant_name       (tenant_id, name)
    spider_task_templates uq_task_templates_tenant_name          (tenant_id, name)
    capability_assets    uq_asset_type_name                      (asset_type, name)
- 不改（占位合理，理由）：
    tenants——slug 是全局对外路由标识（登录标识/外部系统引用/审计外链），
      删除=注销不复用：新租户复用旧 slug 会继承旧 slug 的外部引用歧义；租户
      删除是极低频运营操作，真需复用先物理清尸，恢复走 restore
    users——T4 已定：软删占位保留用户名、同名重建 422 优雅报错（024 同口径）

方案（MySQL 无部分索引的等价物）：
PostgreSQL 的 UNIQUE ... WHERE deleted_at IS NULL 在 MySQL 不可用；deleted_at
「NULL=存活」语义已固化于 SoftDeleteMixin + platform_core/repository 全量过滤
（deleted_at IS NULL），哨兵值方案（NOT NULL DEFAULT '1970-01-01'）需同步改
全应用层读写语义，超出本票边界（不动 services/repository）。故采用虚拟生成列：

    alive_flag SMALLINT GENERATED ALWAYS AS
        (CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END) VIRTUAL

新唯一键 (…, name, alive_flag) 的判重行为：
- 存活行 alive_flag=1 → 参与唯一约束 → 同名存活互斥（旧约束语义完整保留）
- 已删行 alive_flag=NULL → MySQL 唯一索引对含 NULL 的行不判重
  → 删后可重建同名、可多次删建（软删的产品语义恢复）

expand-contract 说明（单迁移内完成的结构性理由，与三步分立的判据对照）：
- 方向是「放松」而非「收紧」：新唯一键约束的行子集严格小于旧键——建新键不可
  能被存量违反（旧键保证同键至多一行）；旧键与新键共存期内任一时刻，新旧两版
  应用代码（均已按 deleted_at IS NULL 判存在）都正常工作，不存在需要跨发布
  双写/双读隔离的不兼容窗口，故不适用三迁移分步。
- 线上执行：VIRTUAL 生成列加列为 INSTANT 级 DDL（不重写数据）；唯一键变更
  INPLACE。本批 5 表均为配置/注册表量级（行数 << 1e5），秒级完成。
- downgrade（收紧方向）带前置校验：存在同名多行（删后重建所致）时旧唯一键
  无法重建，显式 raise 报错并附检测 SQL（impossible-down 语义显式化，优于
  ALTER 中途报错留下半回滚态）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "025"
down_revision: Union[str, Sequence[str], None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (表, 旧唯一键名, 新唯一键名, 业务唯一列前缀)——tenants/users 不在列（见模块注释）
_TABLES = [
    ("departments", "uq_departments_tenant_name", "uq_departments_tenant_name_alive", ["tenant_id", "name"]),
    ("llm_providers", "uq_llm_providers_tenant_name", "uq_llm_providers_tenant_name_alive", ["tenant_id", "name"]),
    ("spider_definitions", "uq_spider_definitions_tenant_name",
     "uq_spider_definitions_tenant_name_alive", ["tenant_id", "name"]),
    ("spider_task_templates", "uq_task_templates_tenant_name",
     "uq_task_templates_tenant_name_alive", ["tenant_id", "name"]),
    ("capability_assets", "uq_asset_type_name", "uq_asset_type_name_alive", ["asset_type", "name"]),
]

_ALIVE_EXPR = "CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END"


def upgrade() -> None:
    for table, old_uq, new_uq, cols in _TABLES:
        # expand 1：加 VIRTUAL 生成列（存活=1 / 已删=NULL；INSTANT DDL）
        op.add_column(table, sa.Column(
            "alive_flag", sa.SmallInteger(),
            sa.Computed(_ALIVE_EXPR, persisted=False),
            comment="存活标记（生成列，025）：唯一键组件——软删行 NULL 使其脱离唯一约束，删后可重建同名",
        ))
        # expand 2：建新唯一键（旧键的放松，存量必满足——旧键保证同键至多一行）
        op.create_unique_constraint(new_uq, table, [*cols, "alive_flag"])
        # contract：撤旧唯一键。新键在场后旧键是更强的错误约束（把已删行继续
        # 摁在坑里），且 (tenant_id, name) 查询路径由新键最左前缀完整承接。
        # 约束放松非破坏性变更，与 expand 同文件完成（理由见模块注释）。
        op.drop_constraint(old_uq, table, type_="unique")


def downgrade() -> None:
    for table, old_uq, new_uq, cols in _TABLES:
        # 回滚前置校验（migration data guard）：down 是收紧方向——若业务在 025
        # 存续期做过「删后重建」，同名多行（一活一删或多删）会让旧唯一键无法
        # 重建。显式报错并附检测 SQL，优于 ALTER 中途失败留半回滚态
        # （impossible-down：先 restore/物理清理软删行再回滚）。
        conflict = op.get_bind().execute(sa.text(
            f"SELECT COUNT(*) FROM (SELECT 1 AS c FROM {table} "
            f"GROUP BY {', '.join(cols)} HAVING COUNT(*) > 1) AS dup"
        )).scalar()
        if conflict:
            raise RuntimeError(
                f"025 downgrade 前置校验失败：{table} 存在 {conflict} 组同名多行"
                f"（025 存续期删后重建所致）。需先恢复或物理清理软删同名行再回滚。"
                f"检测 SQL：SELECT {', '.join(cols)}, COUNT(*) FROM {table} "
                f"GROUP BY {', '.join(cols)} HAVING COUNT(*) > 1;"
            )
        op.drop_constraint(new_uq, table, type_="unique")
        op.drop_column(table, "alive_flag")
        op.create_unique_constraint(old_uq, table, cols)
