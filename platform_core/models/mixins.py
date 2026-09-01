"""租户 Mixin（SaaS S1）——业务表 tenant_id 列的单一来源

隔离行为（before_flush 断言 / do_orm_execute 注入）见 platform_core/tenant_context.py（工单 32）。
"""
from sqlalchemy import Column, Integer


class TenantMixin:
    """租户归属列：默认 NULL 允许（llm_providers 平台公共行 / 存量回填前过渡）；
    非 llm_providers 表在迁移层收紧为 NOT NULL（默认租户回填后）。"""

    tenant_id = Column(Integer, index=True, comment="所属租户（NULL=平台级/未归属）")
