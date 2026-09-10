"""租户/软删除/审计 Mixin —— 业务表横切列的单一来源

- TenantMixin：租户归属（SaaS S1）
- SoftDeleteMixin：软删除（DB 升级 2026-09 Phase A）
- AuditMixin：操作人审计（DB 升级 2026-09 Phase A）

隔离行为（before_flush 断言 / do_orm_execute 注入）见 platform_core/tenant_context.py（工单 32）。
"""
from sqlalchemy import Column, DateTime, Integer, String


class TenantMixin:
    """租户归属列：默认 NULL 允许（llm_providers 平台公共行 / 存量回填前过渡）；
    非 llm_providers 表在迁移层收紧为 NOT NULL（默认租户回填后）。

    index=True 为共享声明：spider_results/spider_schedules/ai_plans/
    alert_rules/attachments/resource_versions 六表的单列 tenant_id 索引
    真实存在（无更左复合索引承接）；其余表该单列索引已于 026 删除（被
    唯一键/复合索引最左前缀覆盖），create_all 与迁移链的此差异为已知
    豁免（基线对拍口径=列集；部署事实源是迁移链）。
    """

    tenant_id = Column(Integer, index=True, comment="所属租户（NULL=平台级/未归属）")


class SoftDeleteMixin:
    """软删除：deleted_at 非空即已删除，NULL 为存活行。

    Repository 层（platform_core/repository.py）对含 deleted_at 的模型
    自动过滤；无此 Mixin 的表（审计/历史/子表/聚合/系统表）行为不变。

    deleted_at 不带索引（026 索引治理）：访问侧全库仅 `IS NULL` 叠加过滤，
    无单列入口/排序模式，列值几乎全 NULL（选择性≈0）。未来出现「回收站
    按删除时间排序」模式时建 (tenant_id, deleted_at) 复合，不恢复单列。
    """

    deleted_at = Column(DateTime(timezone=True), nullable=True,
                        comment="软删除时间（NULL=存活）")

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class AuditMixin:
    """审计字段：created_by/updated_by 由 Repository 层按需填充（用户名字符串）。"""

    created_by = Column(String(64), nullable=True, comment="创建人用户名")
    updated_by = Column(String(64), nullable=True, comment="最后修改人用户名")
