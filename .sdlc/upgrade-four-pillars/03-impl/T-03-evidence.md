# 实现证据 · T-03 配额已尽/将满句；申请提升分角色（不建支付单）

> 票：T-03｜FR 锚点：FR-U02｜角色：/backend｜日期：2026-09-12

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 入队拦住 HTTP 400 + 用户可见句 | Service 信封 | `backend/services/spider_task_service.py` `_check_enqueue_quota` | 存储/并发闸；工人句不走本闸 |
| 规划 3s 内配额句 | Service | `backend/services/ai_planner/orchestrator.py` `_reject_if_token_quota_full` | 抢断 planning 前拒绝，计划保持 draft |
| LLM 出站前 token 闸信封 | Service | `backend/services/ai_planner/llm_client.py` `_check_llm_tokens` | 内部仍 `QuotaExceededException` |
| 将满/已尽告警 + CTA | Service | `backend/services/quota_service.py` `build_usage_alerts` | 将满无满额 CTA |
| 申请提升分角色 | Service + Router | `resolve_upgrade_intent` + `GET /tenants/me/quota/upgrade-intent` | 不建单 |
| 买方结账空态（N1） | Service + Router | `BillingService.preview_checkout` + `GET /billing/checkout` | 不建单、无 notify |
| 错误码映射 | 统一异常处理器 | `platform_core/exceptions/handlers.py` | 信封 `TASK_QUOTA_LIMIT_REACHED` / `ORDER_ROLE_NOT_ALLOWED`；非 `QUOTA_EXCEEDED`、非 429 |
| 幂等 | N/A | — | 本票无写单 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/quota_service.py` | 修改 | 锁句 CTA「申请提升」；`wrap_quota_exceeded`；将满/满额告警 CTA；`resolve_upgrade_intent` |
| `backend/services/spider_task_service.py` | 修改 | 入队查存储+并发，信封分维 CTA |
| `backend/services/ai_planner/llm_client.py` | 修改 | token 满改写用户可见信封 |
| `backend/services/ai_planner/orchestrator.py` | 修改 | 规划点击前同步 token 闸 |
| `backend/app/api/v1/tenant_usage.py` | 修改 | `GET /quota/upgrade-intent` |
| `backend/services/billing_service.py` | 修改 | `preview_checkout` 只读空态，零订单 |
| `backend/app/api/v1/billing.py` | 修改 | `GET /checkout`（静态段） |
| `backend/tests/test_fr_u02_quota_copy.py` | 新增 | GWT-U02.2…U02.7 |
| `backend/tests/test_fr87_enqueue_envelope.py` | 修改 | PIT-2：并发满额句改为申请提升 |
| `backend/tests/test_t38_platform_tenant_enqueue.py` | 修改 | 同上 |
| `backend/tests/test_saas_wiring.py` | 修改 | 同上 |
| `backend/tests/test_saas_byok.py` | 修改 | llm_chat 可见信封非 429 |
| `backend/tests/test_llm_four_actions_http.py` | 修改 | 规划满额 400 + draft |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：结账 GET 空态落在 billing 读面，仍不建单、不验真）

**未触碰「不许改的文件」**：☑ 确认（无 Alipay notify；未改 GWT/schema）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 入队配额拒绝 | 否 | 只读检查，不写任务行 |
| 申请提升 / 打开结账 | 否 | 纯读意图，禁止插订单 |

**事务提交后的操作失败怎么办**：N/A（本票拒绝路径无提交）

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | N/A |
| 保证方式 | N/A |
| 重复请求返回 | GET 意图/结账重复打开不建单 |

☐ 未使用「先查后插」（本票无插入）

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 规划抢断 | 既有 `claim_status` | 本票在抢断前配额拒绝，不进入 claim |

☐ 所有条件更新的返回行数都有处理（未改 claim 语义）

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 配额计数 Redis | 既有 TTL 缓存 | 故障回源 DB COUNT | 回源 | N/A |

## 4. ORM 与 DBML 对齐

☑ 未自行加字段/改类型（需要变更已回 `/dba`）— 本票不改表

结构核对输出：

```
$ 本票无迁移
N/A
```

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `wrap_quota_exceeded` / `resolve_upgrade_intent` / `preview_checkout` / 规划前 token 闸 |
| trace_id | 既有中间件 `request_id` |
| 错误日志上下文 | 配额信封记 dimension，不含密钥 |
| 慢操作耗时 | N/A |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。

### TDD 红（实现前）

```
$ uv run pytest -x -q backend/tests/test_fr_u02_quota_copy.py --tb=short
F
=================================== FAILURES ===================================
_________ test_gwt_u02_2_storage_full_blocks_enqueue_with_results_cta __________
backend/tests/test_fr_u02_quota_copy.py:176: in test_gwt_u02_2_storage_full_blocks_enqueue_with_results_cta
    assert PLAN_FULL in body["message"]
E   AssertionError: assert '已达配额上限' in '创建成功'
=========================== short test summary info ============================
FAILED backend/tests/test_fr_u02_quota_copy.py::test_gwt_u02_2_storage_full_blocks_enqueue_with_results_cta
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 2.40s
exit: 1
```

### 绿

```
$ uv run pytest -q backend/tests/test_fr_u02_quota_copy.py backend/tests/test_fr87_enqueue_envelope.py backend/tests/test_t38_platform_tenant_enqueue.py backend/tests/test_saas_quota.py backend/tests/test_saas_wiring.py backend/tests/test_saas_byok.py backend/tests/test_llm_four_actions_http.py::test_post_plan_quota_full_gateway_reachable_only_12_3 backend/tests/test_llm_four_actions_http.py::test_post_plan_quota_full_gateway_unreachable_only_12_3 backend/tests/test_spider_worker_offline.py backend/tests/test_billing_orders_write_rules.py --tb=line
...........................................................              [100%]
59 passed in 11.68s
exit: 0

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0

$ python PLUGIN_ROOT/skills/impl-evidence/scripts/check-layering.py backend/app/api/v1/tenant_usage.py backend/app/api/v1/billing.py
✓ 分层依赖检查通过
exit: 0

$ uv run ruff check backend/services/quota_service.py backend/services/spider_task_service.py backend/services/billing_service.py backend/app/api/v1/tenant_usage.py backend/app/api/v1/billing.py
All checks passed!
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-U02.2 存储满 | `test_gwt_u02_2_storage_full_blocks_enqueue_with_results_cta` | ✅ |
| GWT-U02.3 只读提交 | `test_gwt_u02_3_readonly_submit_rejected_no_enqueue` | ✅ |
| GWT-U02.4 token 满规划 | `test_gwt_u02_4_token_full_planning_is_quota_copy_not_worker` | ✅ |
| GWT-U02.5 将满 | `test_gwt_u02_5_usage_near_limit_is_not_full_copy` | ✅ |
| GWT-U02.6 经办/只读申请提升 | `test_gwt_u02_6_operator_upgrade_intent_contact_admin_no_order` / `test_gwt_u02_6_viewer_upgrade_intent_contact_admin_no_order` | ✅ |
| GWT-U02.7 买方结账路由 | `test_gwt_u02_7_buyer_upgrade_intent_checkout_path_no_order` / `test_gwt_u02_7_buyer_checkout_empty_state_creates_no_order` | ✅ |
| 工人句分家 | `test_concurrency_full_enqueue_uses_upgrade_cta_not_worker` + worker-offline 回归 | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（拒绝路径无多步写） |
| 幂等 | GET upgrade-intent / checkout 重复不插订单 | ✅ |
| 并发写 | — | ➖ N/A（无新建支付单） |
| 外部依赖失败 | 配额 Redis 故障回源既有 | ➖ N/A（本票未改缓存语义） |

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-U01 | 提交/规划 3s 内见拦住句 | 入队/规划同步拒绝，pytest 即时 400 | SQLite pytest |
| NFR-U06 | 可见面无「当前可买」 | checkout 响应断言 | 同上 |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 内部 `QuotaExceededException` 仍 429/`QUOTA_EXCEEDED`；HTTP 信封为 400 + `TASK_QUOTA_LIMIT_REACHED`。工人句 `SPIDER_WORKER_OFFLINE` 未改。GET checkout 为 N1 空态 200 +「收款通道未开通」，T-16 可改为 422 `BILLING_CHANNELS_UNCONFIGURED`。 |
| `/frontend` | 锁句：已达配额上限；存储 CTA「去结果库」；token/并发 CTA「申请提升」（不再是「申请提升配额」）。将满：「接近上限。超额操作会被拒绝。」无满额 CTA。`GET /api/v1/tenants/me/quota/upgrade-intent`：经办/只读 `action=contact_admin` +「请联系本企业管理员开通」；买方 `action=checkout` + `checkout_path=/billing/checkout?product=plan_pro`。买方再 GET checkout 得空态，不建单。 |
| `/architect` | N1 GET checkout 用 200 空态而非契约表 422；待 T-16 收口。未实现 notify。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（不是「大部分通过」）
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`（吞异常）
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」
- [x] 条件更新的 `rows == 0` 已处理（未改 claim）
- [x] 外部依赖四件套齐全或 N/A
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 票证据已落盘
