"""
API V1 版本路由聚合器

职责：
- 聚合 V1 版本的所有业务路由
- 定义 V1 版本的路由前缀和标签
"""
from fastapi import APIRouter
from . import (
    admin, ai, api_keys, auth, billing, capabilities, capabilities_gov, configs,
    health, internal_fixture_tenants, litellm_admin, llm_providers, members,
    newapi, ops_contact, outbound_keys, payment_credentials, product_events,
    public_skills, rbac, relay, root, skills, spiders, tenant_signup,
    tenant_usage,
)

router = APIRouter()

router.include_router(auth.router, tags=["认证"])
router.include_router(root.router, tags=["root"])
router.include_router(health.router, prefix="/health", tags=["health"])
router.include_router(spiders.router, prefix="/spiders", tags=["spiders"])
router.include_router(admin.router, prefix="/admin", tags=["admin"])
from .rbac import router as rbac_router
router.include_router(rbac_router, prefix="/rbac", tags=["rbac"])
router.include_router(configs.router, prefix="/configs", tags=["configs"])
router.include_router(ai.router, prefix="/ai", tags=["ai"])
router.include_router(llm_providers.router, prefix="/llm", tags=["llm"])
router.include_router(newapi.router, prefix="/newapi", tags=["newapi"])
router.include_router(skills.router, prefix="/skills", tags=["skills"])
router.include_router(public_skills.router, prefix="/public", tags=["public"])
router.include_router(members.router, prefix="/members", tags=["members"])
router.include_router(tenant_usage.router, prefix="/tenants/me", tags=["tenants"])
router.include_router(tenant_signup.router, prefix="/public", tags=["public"])
router.include_router(ops_contact.router, prefix="/public", tags=["public"])
# feat-agents-market：gov（静态治理段）必须先于 capabilities（含二段式动态段）挂载
router.include_router(capabilities_gov.router, prefix="/capabilities", tags=["capabilities"])
router.include_router(capabilities.router, prefix="/capabilities", tags=["capabilities"])
router.include_router(api_keys.router, prefix="/api-keys", tags=["api-keys"])
router.include_router(billing.router, prefix="/billing", tags=["billing"])
router.include_router(litellm_admin.router, prefix="/litellm", tags=["litellm"])
router.include_router(product_events.public_router, prefix="/public", tags=["public"])
router.include_router(product_events.admin_router, tags=["product-events"])
router.include_router(
    internal_fixture_tenants.router,
    prefix="/admin/internal-fixture-tenants",
    tags=["internal-fixture-tenants"],
)
router.include_router(
    payment_credentials.router,
    prefix="/admin/payment-credentials",
    tags=["payment-credentials"],
)
router.include_router(relay.router, prefix="/relay", tags=["relay"])
router.include_router(outbound_keys.router, prefix="/outbound", tags=["outbound"])

__all__ = ["router"]
