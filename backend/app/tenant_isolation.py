"""租户隔离业务豁免登记（T8）——豁免清单唯一事实源

platform_core/tenant_context.py 只提供注册机制，不含任何业务表名（B1 语义收口：
基建不感知业务表）。哪些业务表是平台级/平台共享，由本文件声明并经应用组装点
（backend/app/__init__.py create_app）显式注册——platform_core 零业务表名。

防漂移：scripts/check-arch.sh R13 从本文件读取清单做双向校验
（组装点注册生效 + platform_core 未回写表名字面量），改清单只改这里。

登记语义（platform_core/tenant_context.py）：
- 豁免表：tenant_scope 下 Core UPDATE/DELETE 不注入 tenant_id 条件
  （SELECT 侧豁免表因不继承 TenantMixin 天然不过滤，登记不影响读路径）；
- 平台共享读表：tenant_scope 读注入保留 tenant_id IS NULL 平台公共行，
  写侧仍收窄本租户（平台公共行仅平台态可写）。

T8 全量核对结论：清单内唯一功能必需的豁免是 skills（唯一带 tenant_id 列的
平台级表，不豁免则 Core UPDATE/DELETE 注入条件后恒 NULL 行全部失配）；
其余表无 tenant_id 列（注入分支本就跳过），登记属防御性声明——防止未来
给平台级表加 tenant_id 列后语义静默漂移，故全部保留并逐表注明理由。
"""
from platform_core.logger import get_logger
from platform_core.tenant_context import (
    register_platform_shared_read_tables,
    register_tenant_exempt_tables,
)

logger = get_logger("tenant_isolation")

# 平台级豁免表（逐表理由见各注释；新增须同步评估是否带 tenant_id 列）
TENANT_EXEMPT_TABLES: "tuple[str, ...]" = (
    # 租户表自身（S1-1）：平台域资源，无"属于租户"语义；无 tenant_id 列（防御性声明）
    "tenants",
    # 系统全局配置：全平台一份，无租户维度；无 tenant_id 列（防御性声明）
    "system_configs",
    # new-api 渠道调度审计轨迹（阶段三）：平台域运营数据；无 tenant_id 列（防御性声明）
    "channel_events",
    # 渠道真伪探针结果（阶段三）：平台域运营数据；无 tenant_id 列（防御性声明）
    "channel_probe_results",
    # 操作审计日志：跨租户全局留痕（归属在 actor 行为人，不在行本身）；
    # 无 tenant_id 列（防御性声明）
    "operation_logs",
    # 技能主表（D3 平台级统一技能库）：tenant_id 列为预留恒 NULL——
    # 清单内唯一功能必需的豁免（不豁免则 Core UPDATE/DELETE 注入 tenant_id
    # 条件，恒 NULL 行全部失配，平台级技能维护/评分写路径全断）
    "skills",
    # 技能评审留痕：随 skills 同域平台级；无 tenant_id 列（防御性声明）
    "skill_reviews",
    # 技能任务运行记录（scan/score_batch 等观测）：平台域；无 tenant_id 列（防御性声明）
    "skill_jobs",
    # 供应商模型子表：无独立归属，随父表 llm_providers 行走（访问经父行收口）；
    # 无 tenant_id 列（防御性声明）
    "llm_provider_models",
)

# 平台共享读表：tenant_scope 读注入保留平台公共行（tenant_id IS NULL 可见，
# BYOK S4 兜底可见性——租户未配自有供应商时回落平台公共供应商）；
# 写侧仍注入本租户条件（平台公共行仅平台态可写）
PLATFORM_SHARED_READ_TABLES: "tuple[str, ...]" = (
    "llm_providers",
)


def setup_tenant_isolation() -> None:
    """应用组装点显式注册（幂等；create_app 调用，R13 同步校验依赖此接线）"""
    register_tenant_exempt_tables(*TENANT_EXEMPT_TABLES)
    register_platform_shared_read_tables(*PLATFORM_SHARED_READ_TABLES)
    logger.info(
        f"租户隔离豁免登记完成 | exempt={len(TENANT_EXEMPT_TABLES)} "
        f"shared_read={len(PLATFORM_SHARED_READ_TABLES)}"
    )
