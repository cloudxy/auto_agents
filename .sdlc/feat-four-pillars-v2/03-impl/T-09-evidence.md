# 实现证据 · T-09 `check_llm_tokens_month` 接到 `llm_chat` 成功路径前

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-09.md`｜FR 锚点：FR-12 / FR-74.3｜角色：/backend｜日期：2026-09-08
> 泳道：L4

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径/方法/状态码 | Router | `backend/app/api/v1/tenant_usage.py` | GET `/tenants/me/usage` 只读；PATCH `/tenants/me/quota` 改套餐写权 |
| 字段校验（类型/范围/枚举） | Schema | 未改 | 本票不改请求体契约 |
| 跨字段参数约束 | Schema | 未改 | |
| 权限判定（数据范围） | Router | GET `require_login`（含 viewer）；PATCH `require_tenant_manager` | GWT-12.4 写权；无企业空间 200「用量属于企业空间」 |
| 业务规则/状态流转 | Service | `quota_service.py` + `llm_client.llm_chat` | 闸在出站 HTTP 前；成本熔断 `LLM_COST_FUSE` ≠ 套餐句 |
| 数据读写 | Service/既有表 | `llm_token_usage` 聚合 | 执法走表，不改 schema |
| 错误码映射 | 统一异常处理器 | `QuotaExceededException(code=QUOTA_EXCEEDED, 429)` | 内部码可保留；禁止渲染给租户 |
| 幂等 | N/A | | 本票无新建写 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/quota_service.py` | 修改 | 上海月、满额/将满告警、用户可见句、网关失败映射 |
| `backend/services/ai_planner/llm_client.py` | 修改 | `_enforce_tenant_token_quota` 在出站 HTTP 前；成本熔断 `LLM_COST_FUSE` |
| `backend/app/api/v1/tenant_usage.py` | 修改 | 只读 GET；PATCH quota 403 只读；Asia/Shanghai |
| `backend/tests/test_saas_quota.py` | 修改 | 12.1 / 12.2 / 12.3 / 12.5 / 12.4+74.3 并格 |
| `backend/tests/test_saas_byok.py` | 修改 | `test_platform_fallback_subject_to_token_quota` 拒绝在出站前 |
| `frontend/admin/src/pages/Usage.tsx` | 修改 | 用户可见句；CTA 不到 `/register`；只读不能改套餐 |
| `frontend/admin/src/pages/Usage.test.tsx` | 新增 | `test_readonly_usage_no_plan_edit_gateway_failure_not_quota` |
| `frontend/admin/src/services/usage.ts` | 修改 | alerts / timezone / 平台空态字段 |
| `.sdlc/feat-four-pillars-v2/02-shape/tickets/T-09.md` | 修改 | 状态 done |

**与票里「会改哪些文件」一致**：☑ 是（闸命令活路径 `bash tools/check/arch.sh`）

**未触碰「不许改的文件」**：☑ 确认（未改 LiteLLM 出口 / T-16 四动作 HTTP / official Home·Pricing / export / Register / 未把 operator 403 写成 `/llm` 完成态）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 套餐闸读 `llm_token_usage` | 独立短事务 | 与 `_resolve_llm_runtime_config` 同范式；测试可注入 `quota_session_factory` |
| 成本熔断读 Redis/内存 | 否 | 既有预算路径，不写库 |

**事务提交后的操作失败怎么办**：闸失败直接抛，无提交后动作。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | N/A |
| 保证方式 | N/A |
| 重复请求返回 | N/A |

☑ 未使用「先查后插」（本票无新建业务写）

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 无本票条件更新 | — | — |

☑ 本票无条件更新

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 企业月度 token 读库 | 既有 session | 无 | 无租户上下文跳过闸；有租户则 fail-closed | 读 |

## 4. ORM 与 DBML 对齐

☑ 未改 ORM 字段/类型/索引/唯一约束/外键。未切 LiteLLM PG。未 Mixin 回填。

结构核对输出：

```
$ 本票无 DDL / 无 autogenerate
（执法走既有 llm_token_usage + tenants.quota JSON）
```

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `_enforce_tenant_token_quota` 记 tenant/month；PATCH quota 记 user |
| trace_id | 既有中间件 |
| 错误日志上下文 | 配额超限走统一异常处理器 code=QUOTA_EXCEEDED |
| 慢操作耗时 | 未新增外部调用 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。

```
$ uv run pytest -x -q backend/tests/test_saas_quota.py backend/tests/test_saas_quota.py::test_readonly_usage_cannot_change_plan_and_cannot_render_gateway_failure_as_quota
...........                                                              [100%]
11 passed in 2.10s
exit: 0

$ bash tools/check/arch.sh
架构合规检查（13 条红线 + 3 条边界）
======================================
✓ R1: 硬编码连接串
✓ R2: 明文 password
✓ R3: scrapy → backend 反向依赖
✓ R4: scrapy 使用 SQLAlchemy
✓ R5: DOWNLOAD_DELAY 已配置
✓ R6: USER_AGENT 配置存在
✓ R7: API 层 import models
✓ R8: models 反向 import schemas
✓ R9: 无循环 import
✓ R10: service 方法入口缺 logger
✓ R11: backend 同步 redis_client() 直调（阻塞事件循环）
✓ R12: spider_service 门面白名单外 import（应直接依赖子 Service）
✓ R13: 租户过滤收口（安装点/裸语句/豁免清单同步）

--- 核心代码边界 ---
✓ B1: platform_core → backend/scrapy 反向依赖
✓ B2: backend → scrapy 直接依赖
✓ B3: config → 业务模块反向依赖

--- 发布物密钥（FR-14）---
✓ FR-14: config.gen.yaml 不在跟踪树
✓ FR-14: 跟踪的 deploy/config 无上游 Key 样例模式

✓ 架构合规检查通过（13 红线 + 3 边界 + FR-14 发布物密钥，全部通过）
exit: 0

$ npm test --prefix frontend/admin -- --testPathPattern=Usage.test --watchAll=false --silent
PASS src/pages/Usage.test.tsx
Test Suites: 1 passed, 1 total
Tests:       4 passed, 4 total
exit: 0

$ uv run pytest -x -q backend/tests/test_saas_byok.py::test_platform_fallback_subject_to_token_quota
.                                                                        [100%]
1 passed in 1.04s
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-12.1 正常 | `test_llm_chat_under_quota_not_rejected_by_plan_gate` | ✅ |
| GWT-12.2 边界 | `test_usage_overview_near_limit_alert_has_no_internal_code`；Usage `near limit warning has no internal codes` | ✅ |
| GWT-12.3 超限 | `test_usage_overview_full_alert_is_plan_full_sentence`；`test_platform_fallback_subject_to_token_quota`；Usage token full CTA | ✅ |
| GWT-12.6 出口 | Usage `token full CTA does not go to register` | ✅ |
| GWT-12.7 出口 | Usage `storage full CTA goes to results not register` | ✅ |
| GWT-12.4 越权 | `test_readonly_usage_cannot_change_plan_and_cannot_render_gateway_failure_as_quota`（只读 GET 200 + PATCH 403） | ✅ |
| GWT-74.3 越权（并格） | 同上夹具后半：网关失败句 ≠ 套餐已满；Usage `test_readonly_usage_no_plan_edit_gateway_failure_not_quota` | ✅ |
| GWT-12.5 降级 | `test_platform_cost_fuse_copy_is_not_plan_full`（`LLM_COST_FUSE`，无「已达配额上限」+「申请提升配额」，无出站） | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（本票只读闸 + 拒绝写套餐，无多步写） |
| 幂等 | — | ➖ N/A（无新建业务写） |
| 并发写 | — | ➖ N/A（无条件更新） |
| 外部依赖失败 | `test_platform_cost_fuse_copy_is_not_plan_full`；只读夹具网关失败映射 | ✅ 熔断/网关失败均不套用套餐句 |

## 7. NFR 验证（票里有 NFR 时填）

本票无独立 NFR 数字闸。用量月 = Asia/Shanghai（禁止 `datetime.utcnow()`）。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 套餐闸观察点 = `llm_chat` 抛 `QuotaExceededException` 且 outbound 列表空。成本熔断观察点 = `code=LLM_COST_FUSE`。网关不可达仍是 T-16（GWT-74.1/74.4/74.5/74.6），本票只保证不套用套餐句。74.3 已与 12.4 并格，T-16 禁止单独勾「是」。 |
| `/frontend` | 用量页已改：满额「已达配额上限」+「申请提升配额」（mailto 联系说明，不到 `/register`）；存储满「去结果库」→ `/data`；≥90%「接近上限。超额操作会被拒绝。」只读横幅「只读可见进度，不能改套餐」。内部码不得上屏。 |
| `/architect` | 无契约歧义需回。内部码 `QUOTA_EXCEEDED` / `LLM_COST_FUSE` / `LLM_GATEWAY_UNREACHABLE` 按 §7.1。 |

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
- [x] 条件更新的 `rows == 0` 已处理（N/A）
- [x] 外部依赖四件套齐全或标 N/A
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 票状态已更新为 done
