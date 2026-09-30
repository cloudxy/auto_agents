# 功能模块清单（manager 事实整理，2026-09-27，HEAD 82259f3）

## 后端路由组（live /openapi.json：184 paths / 229 ops）
- `/api/v1/` (1)
  - GET /api/v1/
- `/api/v1/admin` (25)
  - GET /api/v1/admin/stats
  - GET /api/v1/admin/users
  - POST /api/v1/admin/users
  - PATCH /api/v1/admin/users/{user_id}
  - DELETE /api/v1/admin/users/{user_id}
  - POST /api/v1/admin/users/{user_id}/restore
  - GET /api/v1/admin/audit-logs
  - GET /api/v1/admin/tenants
  - POST /api/v1/admin/tenants
  - PATCH /api/v1/admin/tenants/{tenant_id}
  - GET /api/v1/admin/power-market
  - PUT /api/v1/admin/power-market
  - GET /api/v1/admin/dead-items
  - DELETE /api/v1/admin/dead-items
  - DELETE /api/v1/admin/dead-items/{index}
  - GET /api/v1/admin/notify-config
  - PUT /api/v1/admin/notify-config
  - GET /api/v1/admin/webhook-status
  - GET /api/v1/admin/internal-fixture-tenants
  - POST /api/v1/admin/internal-fixture-tenants
  - DELETE /api/v1/admin/internal-fixture-tenants/{tenant_id}
  - GET /api/v1/admin/payment-credentials
  - PUT /api/v1/admin/payment-credentials
  - DELETE /api/v1/admin/payment-credentials/{channel}
  - POST /api/v1/admin/payment-credentials/{channel}/validate
- `/api/v1/ai` (7)
  - POST /api/v1/ai/plans
  - GET /api/v1/ai/plans
  - GET /api/v1/ai/plans/{plan_id}
  - DELETE /api/v1/ai/plans/{plan_id}
  - POST /api/v1/ai/plans/{plan_id}/plan
  - POST /api/v1/ai/plans/{plan_id}/test
  - POST /api/v1/ai/plans/{plan_id}/register
- `/api/v1/api-keys` (3)
  - GET /api/v1/api-keys
  - POST /api/v1/api-keys
  - POST /api/v1/api-keys/{key_id}/revoke
- `/api/v1/auth` (4)
  - POST /api/v1/auth/login
  - GET /api/v1/auth/permissions
  - GET /api/v1/auth/menus
  - POST /api/v1/auth/register
- `/api/v1/billing` (10)
  - GET /api/v1/billing/plans
  - GET /api/v1/billing/checkout
  - POST /api/v1/billing/checkout
  - POST /api/v1/billing/notify/{channel}
  - GET /api/v1/billing/subscription
  - POST /api/v1/billing/orders
  - GET /api/v1/billing/orders
  - GET /api/v1/billing/orders/{order_id}/pay-intent
  - GET /api/v1/billing/admin/orders
  - POST /api/v1/billing/orders/{order_id}/confirm
- `/api/v1/capabilities` (28)
  - POST /api/v1/capabilities/sync-agents-hub
  - POST /api/v1/capabilities/assets/prune-missing
  - PATCH /api/v1/capabilities/{asset_type}/{name}/featured
  - PATCH /api/v1/capabilities/{asset_type}/{name}/examples
  - POST /api/v1/capabilities/import/tree/preview
  - POST /api/v1/capabilities/import/tree/confirm
  - GET /api/v1/capabilities
  - GET /api/v1/capabilities/sources
  - POST /api/v1/capabilities/sources
  - POST /api/v1/capabilities/sources/{name}/sync
  - POST /api/v1/capabilities/backfill-first-party
  - GET /api/v1/capabilities/plugins/{name}
  - POST /api/v1/capabilities/plugins/{name}/verify
  - GET /api/v1/capabilities/experts/{name}
  - POST /api/v1/capabilities/teams
  - GET /api/v1/capabilities/teams/{name}
  - GET /api/v1/capabilities/teams/{name}/export
  - POST /api/v1/capabilities/import
  - GET /api/v1/capabilities/installs
  - PATCH /api/v1/capabilities/installs/{install_id}
  - DELETE /api/v1/capabilities/installs/{install_id}
  - POST /api/v1/capabilities/{asset_type}/{name}/correct
  - PATCH /api/v1/capabilities/{asset_type}/{name}/listing
  - PATCH /api/v1/capabilities/{asset_type}/{name}/license-override
  - PUT /api/v1/capabilities/{asset_type}/{name}/alias
  - POST /api/v1/capabilities/{asset_type}/{name}/subscribe
  - GET /api/v1/capabilities/{asset_type}/{name}/references
  - GET /api/v1/capabilities/{asset_type}/{name}
- `/api/v1/configs` (2)
  - GET /api/v1/configs/
  - PUT /api/v1/configs/{key}
- `/api/v1/health` (5)
  - GET /api/v1/health/
  - GET /api/v1/health/db
  - GET /api/v1/health/storage
  - GET /api/v1/health/redis
  - GET /api/v1/health/deep
- `/api/v1/litellm` (4)
  - GET /api/v1/litellm/keys
  - POST /api/v1/litellm/keys
  - DELETE /api/v1/litellm/keys
  - GET /api/v1/litellm/spend
- `/api/v1/llm` (15)
  - GET /api/v1/llm/providers
  - POST /api/v1/llm/providers
  - GET /api/v1/llm/providers/active
  - GET /api/v1/llm/providers/platform-presets
  - POST /api/v1/llm/providers/models/probe
  - POST /api/v1/llm/providers/models/probe-test
  - POST /api/v1/llm/providers/{provider_id}/models/fetch
  - POST /api/v1/llm/providers/{provider_id}/models/{model_id}/test
  - GET /api/v1/llm/providers/{provider_id}/models
  - PUT /api/v1/llm/providers/{provider_id}/models
  - PUT /api/v1/llm/providers/{provider_id}
  - DELETE /api/v1/llm/providers/{provider_id}
  - PUT /api/v1/llm/providers/{provider_id}/activate
  - PUT /api/v1/llm/providers/{provider_id}/deactivate
  - POST /api/v1/llm/providers/{provider_id}/test
- `/api/v1/members` (6)
  - GET /api/v1/members
  - POST /api/v1/members
  - PATCH /api/v1/members/{member_id}
  - DELETE /api/v1/members/{member_id}
  - POST /api/v1/members/{member_id}/reset-password
  - GET /api/v1/members/audit
- `/api/v1/newapi` (11)
  - GET /api/v1/newapi/overview
  - GET /api/v1/newapi/events
  - GET /api/v1/newapi/probe-results
  - POST /api/v1/newapi/probe
  - GET /api/v1/newapi/channels
  - PUT /api/v1/newapi/channels/{channel_id}/config
  - DELETE /api/v1/newapi/channels/{channel_id}/config
  - PUT /api/v1/newapi/models/{gateway_ref}/config
  - DELETE /api/v1/newapi/models/{gateway_ref}/config
  - POST /api/v1/newapi/models
  - POST /api/v1/newapi/upstreams
- `/api/v1/outbound` (3)
  - GET /api/v1/outbound/keys
  - POST /api/v1/outbound/keys
  - DELETE /api/v1/outbound/keys/{key_id}
- `/api/v1/product-events` (1)
  - GET /api/v1/product-events
- `/api/v1/public` (11)
  - GET /api/v1/public/capabilities/aliases
  - GET /api/v1/public/capabilities
  - GET /api/v1/public/capabilities/{asset_type}/{name}/media/{kind}
  - POST /api/v1/public/capabilities/{asset_type}/{name}/subscribe
  - GET /api/v1/public/capabilities/{asset_type}/{name}
  - POST /api/v1/public/skills/{name}/subscribe
  - GET /api/v1/public/skills/{name}
  - GET /api/v1/public/skills
  - POST /api/v1/public/tenant/signup
  - GET /api/v1/public/ops-contact
  - POST /api/v1/public/events
- `/api/v1/rbac` (16)
  - GET /api/v1/rbac/roles
  - POST /api/v1/rbac/roles
  - DELETE /api/v1/rbac/roles/{role_key}
  - PUT /api/v1/rbac/roles/{role_key}
  - GET /api/v1/rbac/departments
  - POST /api/v1/rbac/departments
  - PUT /api/v1/rbac/departments/{department_id}
  - DELETE /api/v1/rbac/departments/{department_id}
  - GET /api/v1/rbac/menus/tree
  - POST /api/v1/rbac/menus
  - PUT /api/v1/rbac/menus/{menu_id}
  - DELETE /api/v1/rbac/menus/{menu_id}
  - GET /api/v1/rbac/permissions
  - POST /api/v1/rbac/permissions
  - PUT /api/v1/rbac/permissions/{permission_id}
  - DELETE /api/v1/rbac/permissions/{permission_id}
- `/api/v1/relay` (10)
  - GET /api/v1/relay/sku
  - GET /api/v1/relay/groups
  - POST /api/v1/relay/groups
  - PATCH /api/v1/relay/groups/{group_id}
  - GET /api/v1/relay/tokens
  - POST /api/v1/relay/tokens
  - GET /api/v1/relay/tokens/by-key
  - GET /api/v1/relay/tokens/{token_id}
  - DELETE /api/v1/relay/tokens/{token_id}
  - POST /api/v1/relay/tokens/refresh-usage
- `/api/v1/skills` (17)
  - POST /api/v1/skills/scan
  - POST /api/v1/skills/import-url
  - GET /api/v1/skills/manifests
  - PUT /api/v1/skills/manifests
  - POST /api/v1/skills/sync-adapters
  - POST /api/v1/skills/similar-suggest
  - PUT /api/v1/skills/similar-confirm
  - GET /api/v1/skills/candidates
  - POST /api/v1/skills/candidates/{result_id}/approve
  - POST /api/v1/skills/candidates/{result_id}/reject
  - GET /api/v1/skills/jobs
  - GET /api/v1/skills
  - GET /api/v1/skills/{name}
  - POST /api/v1/skills/{name}/rescore
  - PUT /api/v1/skills/{name}/meta
  - POST /api/v1/skills/{name}/export-meta
  - GET /api/v1/skills/{name}/check-update
- `/api/v1/spiders` (33)
  - GET /api/v1/spiders/tasks
  - POST /api/v1/spiders/run
  - GET /api/v1/spiders/tasks/{task_id}/store
  - PATCH /api/v1/spiders/tasks/{task_id}
  - DELETE /api/v1/spiders/tasks/{task_id}
  - POST /api/v1/spiders/tasks/{task_id}/control
  - GET /api/v1/spiders/tasks/{task_id}/logs
  - GET /api/v1/spiders/tasks/{task_id}/quality
  - GET /api/v1/spiders/results
  - DELETE /api/v1/spiders/results/{result_id}
  - GET /api/v1/spiders/results/{task_id}
  - GET /api/v1/spiders/results/{task_id}/export
  - GET /api/v1/spiders/registry
  - GET /api/v1/spiders/nodes
  - GET /api/v1/spiders/files
  - PATCH /api/v1/spiders/definitions/{name}
  - DELETE /api/v1/spiders/definitions/{name}
  - POST /api/v1/spiders/definitions
  - PATCH /api/v1/spiders/definitions/{name}/meta
  - GET /api/v1/spiders/proxy-health
  - GET /api/v1/spiders/schedules
  - POST /api/v1/spiders/schedules
  - PATCH /api/v1/spiders/schedules/{schedule_id}
  - DELETE /api/v1/spiders/schedules/{schedule_id}
  - GET /api/v1/spiders/alert-rules
  - POST /api/v1/spiders/alert-rules
  - PATCH /api/v1/spiders/alert-rules/{rule_id}
  - DELETE /api/v1/spiders/alert-rules/{rule_id}
  - GET /api/v1/spiders/templates
  - POST /api/v1/spiders/templates
  - PATCH /api/v1/spiders/templates/{template_id}
  - DELETE /api/v1/spiders/templates/{template_id}
  - POST /api/v1/spiders/templates/{template_id}/run
- `/api/v1/tenants` (6)
  - GET /api/v1/tenants/me/usage
  - GET /api/v1/tenants/me/usage/by-member
  - GET /api/v1/tenants/me/delivery-webhook
  - PUT /api/v1/tenants/me/delivery-webhook
  - GET /api/v1/tenants/me/quota/upgrade-intent
  - PATCH /api/v1/tenants/me/quota
- `/api/v2/` (1)
  - GET /api/v2/
- `/api/v2/health` (3)
  - GET /api/v2/health/
  - GET /api/v2/health/db
  - GET /api/v2/health/storage
- `/external/v1` (7)
  - POST /external/v1/webhooks/spider/callback
  - GET /external/v1/public/data/{spider_name}
  - GET /external/v1/public/spider/status/{task_id}
  - GET /external/v1/public/spider/results/{task_id}
  - GET /external/v1/public/stats
  - POST /external/v1/payments/alipay/notify
  - POST /external/v1/payments/wechat/notify

## admin 页面路由（frontend/admin/src/App.tsx）
path="/login" path="/unauthorized" path="dashboard" path="spiders/tasks" path="spiders/logs" path="spiders/nodes" path="ai" path="enterprise" path="rbac" path="capabilities/installs" path="capabilities" path="members" path="usage" path="billing/checkout" path="pricing" path="relay" path="outbound-keys" path="llm" path="payment-credentials" path="logs" path="data" path="newapi" path="platform-ops" path="users" path="settings" path="*" 

## official 页面路由（frontend/official/src/App.tsx）
path="/" path="/skills" path="/capabilities/:type/:slug" path="/capabilities" path="/register" path="/pricing" path="/terms" path="/privacy" path="*" 

## 服务模块（backend/services）
__init__.py __pycache__ ai_planner ai_planner_service.py alert_service.py api_key_service.py asset_import_sandbox.py asset_import_service.py audit_service.py auth_service.py background_session.py billing_fulfill.py billing_service.py capability_service.py channel_config_service.py channel_notify_auth.py channel_probe_score.py channel_probe_service.py channel_scheduler_service.py config_service.py dead_item_service.py delivery_webhook_service.py expert_service.py gateway_models.py internal_fixture_tenant_service.py litellm llm_common llm_gateway llm_health_patrol.py llm_probe_engine.py llm_protocol llm_provider_service.py llm_secret_vault.py llm_usage_service.py market_events.py mcp_bridge.py member_service.py newapi_api.py newapi_overview_service.py notify_service.py ops_contact_service.py outbound_key_service.py outbound_pull_auth.py payment_credential_service.py payment_gateways payment_notify_service.py payment_provider.py plugin_service.py power_market product_event_service.py proxy_health_service.py quota_service.py rbac_service.py relay_service.py relay_sku_gate.py relay_usage.py retention_service.py schedule_service.py skill_import_service.py skill_scoring_service.py skill_service.py spider_common.py spider_query_service.py spider_registry_service.py spider_service.py spider_task_service.py spider_worker_gate.py tenant_admin_service.py tenant_expiry_service.py tenant_settings_service.py tenant_signup_service.py user_service.py workflow_service.py 

## 功能开关（config/default/*.yml 中的 ENABLED / 开关类键）
power_market.yml:3:  ENABLED: false
llm.yml:12:  ENABLED: false              # 默认关闭（未配置 Key 时调用直接抛业务异常，测试环境友好）
llm.yml:14:  DATA_PLANE: "litellm"
llm.yml:25:  USAGE_PERSIST_ENABLED: true # 用量落库后台任务开关（关闭则预算仍用进程内存口径）
llm.yml:49:  HEALTH_PATROL_ENABLED: false
llm.yml:53:  BUDGET_FAIL_CLOSED: false
skills.yml:10:    ENABLED: false
skills.yml:16:    ENABLED: true
skills.yml:19:    ENABLED: false
notify.yml:13:  ENABLED: true
newapi.yml:8:  ENABLED: false
retention.yml:4:  ENABLED: true
litellm.yml:9:  ENABLED: false                      # 影子/网关总开关（默认关）
litellm.yml:15:    ROUTE_INTERNAL: false             # 内部 LLM 调用切到 sidecar（默认关）
litellm.yml:19:    ENABLED: false                    # 只读对比器，不发起真实 LLM 调用
litellm.yml:21:    ENABLED: false
relay.yml:12:  SCHEDULER_ENABLED: false          # 窗口调度（spend→budget）；默认不启动
relay.yml:13:  PROBE_ENABLED: false              # 真伪探针；默认不启动
official.yml:15:  SITEMAP_ENABLED: false
settings.yml:24:  CONSUMER_ENABLED: true
settings.yml:34:  ENABLED: true
settings.yml:63:  ENABLED: false
settings.yml:75:  ENABLED: true
settings.yml:83:  ENABLED: false        # 默认关闭（需要安装 playwright）

## 爬虫（scrapy/spiders）
__init__.py __pycache__ base.py dianping_home.py example.py flow_generic.py generic.py openweather.py skill_harvester.py zhihu_feed.py 

## 指标定义
# 指标口径注册表（H2）：id / name / formula / window / unit / source
metrics:
  - id: task_success_rate
    name: 任务成功率
    formula: completed / (completed + failed)
    window: 7d
    unit: ratio
    source: spider_tasks.status
  - id: result_volume
    name: 采集结果量
    formula: COUNT(spider_results)
    window: 7d
    unit: count
    source: spider_results.created_at
  - id: llm_tokens_month
    name: 租户月度 LLM token
    formula: SUM(llm_token_usage.total_tokens)
    window: calendar_month
    unit: tokens
    source: llm_token_usage
  - id: llm_cost_cents_month
    name: 租户月度 LLM 成本
    formula: SUM(llm_token_usage.cost_cents)
    window: calendar_month
    unit: cents
    source: llm_token_usage.cost_cents
  - id: quota_task_concurrency
    name: 任务并发占用
    formula: COUNT(pending+running) / quota.task_concurrency
    window: point_in_time
