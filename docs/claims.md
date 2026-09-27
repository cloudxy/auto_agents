# 对外宣称 ↔ 实现锚点（I2）

文案变更须同步改本表；CI `test_claims_anchors.py` 校验锚点文件存在。

| 宣称 | 实现锚点 |
|---|---|
| 到期拒绝登录 | `backend/services/auth_service.py` `assert_tenant_login_allowed` |
| 超配额拒绝（429 QUOTA_EXCEEDED） | `backend/services/quota_service.py` `QuotaExceededException` |
| 租户结果隔离 | `backend/app/external_api/v1/public.py` API Key → tenant_id |
| 平台配置仅超管可写 | `backend/app/api/deps.py` `require_platform_admin` |
| rememberMe 才持久化 token | `frontend/admin/src/store/useAuthStore.ts` `partialize` |
| 用量以 MySQL 为事实源 | `backend/services/llm_usage_service.py` `LlmUsageFlushService` |
| 任务终态可回调租户 | `backend/services/delivery_webhook_service.py` |
| 注册即免费档 | `backend/services/billing_service.py` `attach_free_plan` |
