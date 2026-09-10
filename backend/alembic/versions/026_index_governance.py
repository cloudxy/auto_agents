"""B3 索引治理：删除冗余/无访问模式索引（27 个）+ spider_tasks 复合索引升级

Revision ID: 026
Revises: 025
Create Date: 2026-09-05

体检 F-05/F-06 处置（dba findings P2 池，逐项访问模式审查证据见
.scratch/p0-p1-2026-09/issues/B3.md）：

A. 冗余索引（13 个）——单列索引被唯一键/复合索引最左前缀完整覆盖，
   读侧收益为零、写侧双份 B+ 树维护：
   - ix_tenants_slug                 ← uq_tenants_slug（同列唯一键，纯重复）
   - ix_users_tenant_id              ← uq_users_tenant_username (tenant_id 最左)
   - ix_spider_tasks_tenant_id       ← ix_spider_tasks_tenant_status（tenant_id 最左）
   - ix_spider_definitions_tenant_id ← uq_spider_definitions_tenant_name_alive
   - ix_spider_task_templates_tenant_id ← uq_task_templates_tenant_name_alive
   - ix_llm_providers_tenant_id      ← uq_llm_providers_tenant_name_alive
   - ix_llm_token_usage_tenant_id    ← uq_llm_usage_dim (tenant_id 最左)
   - ix_tags_tenant_id               ← uq_tags_tenant_name
   - ix_archive_records_tenant_id    ← ix_archive_records_tenant_archived
   - ix_notifications_tenant_id      ← ix_notifications_inbox (tenant_id 最左)
   - ix_workflow_definitions_tenant_id ← uq_workflow_definitions_tenant_name
   - ix_workflow_instances_tenant_id ← ix_workflow_instances_tenant_status
   - ix_departments_tenant_id        ← uq_departments_tenant_name_alive（025）
   （体检列 8 处为下界，全库最左前缀盘点后为 13 处——多出的 5 类是
     被唯一键前缀覆盖的 tenant_id 单列索引，同一性质同一处置。）

B. 低基数索引无访问模式支撑（14 个）：
   - 13 张软删表的 ix_{t}_deleted_at（019 的 12 张 + 022 的 departments，
     后者为体检清单外漏网、性质相同）——访问侧全库审查：
     deleted_at 仅以 `IS NULL` 叠加其他条件出现（BaseRepository 软删过滤
     / member_service / user_service / rbac_service 等 20+ 处），无任何
     以 deleted_at 为入口或排序键的模式；列值几乎全 NULL（选择性≈0），
     优化器不会选用。唯一纯 deleted_at 过滤（llm_provider_repository:27
     平台 provider 列表）在近乎全 NULL 列上同样不会走索引，且该表为
     个位数行配置表。→ 无访问模式依赖，删。
     保留条件（写进 ADR-0009）：未来出现「回收站按删除时间排序」
     模式时，建 (tenant_id, deleted_at) 复合索引，而非恢复单列。
   - ix_spider_tasks_priority（006）——priority 基数=3；访问侧
     spider_task_repository.list_tasks/count 为可选等值过滤，且租户态下
     注入 tenant_id 等值 → 由升级后的 (tenant_id, status, priority) 复合
     索引承接（见 C），单列不再保留。

C. spider_tasks 复合索引升级（ESR：三列全等值，基数降序
   tenant_id > status(4) > priority(3)）：
   drop ix_spider_tasks_tenant_status (tenant_id, status)
   →  create ix_spider_tasks_tenant_status_priority (tenant_id, status, priority)
   旧 (tenant_id, status) 前缀语义由新索引完整承接（quota_service /
   list_tasks 的 status 等值、status IN 组合不降级；真库 EXPLAIN 证据见
   B3.md——key_len 87 前缀命中 + Using index）。

expand-contract 定性：drop index 是 contract 步（可逆），downgrade 全量
重建被删索引（含 019/006/017/022 原名原列），up→down→up 三连见 B3.md 演练记录。

MySQL 1553 风险声明：本批被删索引均不被外键依赖——全库无 tenant_id 外键；
notifications FK(user_id) 有独立索引 ix_notifications_user_id；
workflow_instances FK(definition_id) 由建表时自动索引承接。真库演练实证
无 1553 报错。
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "026"
down_revision: Union[str, Sequence[str], None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# A 组：被唯一键/复合索引最左前缀覆盖的冗余单列索引（表, 索引名）
_REDUNDANT = [
    ("tenants", "ix_tenants_slug"),
    ("users", "ix_users_tenant_id"),
    ("spider_tasks", "ix_spider_tasks_tenant_id"),
    ("spider_definitions", "ix_spider_definitions_tenant_id"),
    ("spider_task_templates", "ix_spider_task_templates_tenant_id"),
    ("llm_providers", "ix_llm_providers_tenant_id"),
    ("llm_token_usage", "ix_llm_token_usage_tenant_id"),
    ("tags", "ix_tags_tenant_id"),
    ("archive_records", "ix_archive_records_tenant_id"),
    ("notifications", "ix_notifications_tenant_id"),
    ("workflow_definitions", "ix_workflow_definitions_tenant_id"),
    ("workflow_instances", "ix_workflow_instances_tenant_id"),
    ("departments", "ix_departments_tenant_id"),
]

# B 组：无访问模式支撑的 deleted_at 单列索引（019 的 12 张软删表
# + 022 的 departments，共 13 张）
_SOFT_DELETE_TABLES = [
    "tenants", "users",
    "spider_tasks", "spider_results", "spider_definitions", "spider_schedules",
    "llm_providers", "ai_plans", "skills", "capability_assets",
    "alert_rules", "spider_task_templates",
    "departments",
]


def upgrade() -> None:
    # B 组：删 deleted_at 单列索引（低基数，无访问模式依赖——见模块注释）
    for t in _SOFT_DELETE_TABLES:
        op.drop_index(op.f(f"ix_{t}_deleted_at"), table_name=t)

    # B 组：删 priority 单列索引（基数=3，由 C 组复合索引承接等值过滤）
    op.drop_index("ix_spider_tasks_priority", table_name="spider_tasks")

    # C 组：复合索引升级（先删旧建新，避免共存期的额外写放大）
    op.drop_index("ix_spider_tasks_tenant_status", table_name="spider_tasks")
    op.create_index("ix_spider_tasks_tenant_status_priority", "spider_tasks",
                    ["tenant_id", "status", "priority"])

    # A 组：删被最左前缀覆盖的冗余单列索引
    for table, index in _REDUNDANT:
        op.drop_index(index, table_name=table)


def downgrade() -> None:
    # A 组逆：重建冗余单列索引（017/019/020/021 原名原列）
    for table, index in _REDUNDANT:
        col = "slug" if table == "tenants" else "tenant_id"
        op.create_index(index, table, [col])

    # C 组逆：复合索引还原为 (tenant_id, status)
    op.drop_index("ix_spider_tasks_tenant_status_priority", table_name="spider_tasks")
    op.create_index("ix_spider_tasks_tenant_status", "spider_tasks",
                    ["tenant_id", "status"])

    # B 组逆：重建 priority 单列（006 原名原列）
    op.create_index("ix_spider_tasks_priority", "spider_tasks", ["priority"])

    # B 组逆：重建 12 张软删表的 deleted_at 单列索引（019 原名原列）
    for t in reversed(_SOFT_DELETE_TABLES):
        op.create_index(op.f(f"ix_{t}_deleted_at"), t, ["deleted_at"])
