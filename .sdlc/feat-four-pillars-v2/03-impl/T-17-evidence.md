# 实现证据 · T-17 BYOK 直连四动作；本企业写/test=`require_operator`；经办点测试连接

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-17.md`｜FR 锚点：FR-73 / FR-06.5 / 06.6｜角色：/backend + admin `/llm`｜日期：2026-09-09
> 泳道：L4

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 本企业写/test 守卫 | Router | `backend/app/api/v1/llm_providers.py` | `require_operator`；viewer 403 |
| 平台级行拒绝 | Service | `llm_provider_service._guard_platform_provider_write` | 含 test；GWT-73.3 / 06.6 |
| 四动作 outbound=本企业行 | Service | `ai_planner/llm_client.py` + `resolve_own_tenant_config` | `provider_id` 走共享 client，不经 LiteLLM |
| 该行失败句 | Service | `quota_service.PROVIDER_ERROR_USER` + `_provider_error` | `LLM_PROVIDER_ERROR`；禁止 74.1 / 套餐句 |
| 评分消费带租户 | Service | `skill_scoring_service.enqueue_rescore` | 队列 JSON `{name,tenant_id}`；`consume_once` 进 `tenant_scope` |
| operator `menu:llm` | Auth + 迁移 | `auth.py` `_ROLE_PERMISSIONS` + 022 种子 + 032 UPDATE | 不加 `menu:newapi` |
| `/llm` 经办可进 | Router | `frontend/admin/src/App.tsx` | 去掉 `ProtectedRoute requireAdmin`；`/newapi` 仍平台壳 |
| 点「测试连接」 | Page | `LlmProviders.tsx` | 经办本企业行可见可点；只读无按钮 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import ☑ 未改 T-16 平台路径 Then

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/app/api/v1/llm_providers.py` | 修改 | 写/test/probe/models → `require_operator`；test 传 `_actor` |
| `backend/app/api/v1/auth.py` | 修改 | operator 加 `menu:llm` |
| `backend/alembic/versions/022_saas_roles_departments.py` | 修改 | `_SEED_ROLES` operator 加 `menu:llm` |
| `backend/alembic/versions/032_operator_menu_llm.py` | 新增 | 已 applied 库 UPDATE JSON；禁止改表 |
| `backend/services/quota_service.py` | 修改 | `PROVIDER_ERROR_USER` / `LLM_PROVIDER_ERROR` 映射 |
| `backend/services/ai_planner/llm_client.py` | 修改 | 本企业行失败 → `LLM_PROVIDER_ERROR` |
| `backend/services/llm_provider_service.py` | 修改 | `test_connectivity` 平台行守卫 |
| `backend/services/skill_scoring_service.py` | 修改 | 入队带 `tenant_id`；消费进本企业行解析 |
| `frontend/admin/src/App.tsx` | 修改 | `/llm` 去 `requireAdmin` |
| `frontend/admin/src/components/ProtectedRoute.tsx` | 修改 | 注释：`/llm` 经办可进 |
| `frontend/admin/src/pages/LlmProviders.tsx` | 修改 | h1「LLM 配置」；按钮「测试连接」；只读句；本行失败句 |
| `frontend/admin/src/pages/LlmProviders.test.tsx` | 修改 | 经办见保存/测试连接；只读仍无 |
| `frontend/admin/src/components/ProtectedRoute.test.tsx` | 修改 | 经办可进 `/llm` |
| `frontend/admin/src/App.test.tsx` | 修改 | 经办 `/newapi` 仍 404 壳 |
| `backend/tests/test_fr73_byok_four_actions_http.py` | 新增 | 73.5–73.12 / 73.2 九格 |
| `backend/tests/test_llm_provider.py` | 修改 | 作废 `rejects_operator`；operator 200 / viewer 403 |
| `backend/tests/test_llm_platform_row_writes.py` | 修改 | 经办保存本企业行；经办改平台行 403 |
| `backend/tests/test_rbac_audit.py` | 修改 | operator 有 `menu:llm`、无 `menu:newapi` |
| `.sdlc/feat-four-pillars-v2/02-shape/tickets/T-17.md` | 修改 | 状态 done（Then 未改） |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：评分队列补 `tenant_id` 才能让 `consume_once` 打本企业行；032 数据回填；未改 T-16 平台 Then）

**未触碰「不许改的文件」**：☑ 确认（无租户虚拟令牌；无「我的渠道组」；无 `menu:newapi`；`/newapi` 仍平台壳；无新聊天 UI；未答六问；未退役 new-api；未改 T-16 Then）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 本企业行 CRUD/test 守卫 | 与既有写事务同 | 平台行拒绝在写前，行不变 |
| 四动作 LLM HTTP | 否 | 外部调用；解析短事务 |
| 评分入队 | 否 | Redis；载荷带 tenant_id |

**事务提交后的操作失败怎么办**：本企业行失败落 `LLM_PROVIDER_ERROR` / `PROVIDER_ERROR_USER`；规划/试采 `_fail`；评分 job failed 原样该句。

### 幂等

N/A（无新建写契约键）。☑ 未使用「先查后插」

### 并发控制

N/A（未改激活 CASE）。☑ 本票无新条件更新

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 本企业行 chat | 行 `timeout` | 行 `max_retries` | `LLM_PROVIDER_ERROR`（不是 74.1） | 调用方 |
| 测试连接 | 10s 探测 | 无 | 行内失败句，不要求网关活 | 探测 |

有本企业激活行时四动作 **不** 打 LiteLLM。网关停仍走该行。

## 4. ORM 与 DBML 对齐

➖ N/A（无表变更；032 只 UPDATE `roles.permissions` JSON）

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `test_connectivity` / `enqueue_rescore` / `_score_payload` / `_provider_error` |
| 错误日志上下文 | 本企业行 cause 进 warning；用户句不含 traceback / 74.1 |
| 慢操作耗时 | 沿用行 timeout / 探测 10s |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。

```
$ uv run pytest -x -q backend/tests/test_fr73_byok_four_actions_http.py
.........                                                                [100%]
9 passed in 2.53s
exit: 0

$ uv run pytest -x -q \
  backend/tests/test_fr73_byok_four_actions_http.py \
  backend/tests/test_llm_provider.py \
  backend/tests/test_saas_byok.py
.......................................................................  [100%]
71 passed, 4 warnings in 3.46s
exit: 0

$ bash tools/check/arch.sh
架构合规检查（13 条红线 + 4 条边界）
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
✓ B4: power_market 禁 spider_/newapi_/litellm_/relay_/channel_/ai_planner/llm_gateway 直连
✓ B4: ai_planner 禁 llm_gateway.admin（三模式）
✓ B4: ai_planner 除 llm_client.py 禁 llm_gateway.chat（三模式）
✓ B4: 禁止 LITELLM.DB_DSN
✓ B4: 禁止 create_async_engine 打网关库

--- 发布物密钥（FR-14）---
✓ FR-14: config.gen.yaml 不在跟踪树
✓ FR-14: 跟踪的 deploy/config 无上游 Key 样例模式

✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0

$ cd frontend/admin && npx jest --watchAll=false --testPathPattern='LlmProviders.test|ProtectedRoute.test|App.test' --testTimeout=15000 --forceExit
PASS src/components/ProtectedRoute.test.tsx
PASS src/pages/LlmProviders.test.tsx
PASS src/App.test.tsx
Test Suites: 3 passed, 3 total
Tests:       12 passed, 12 total
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-73.1 网关停保存本企业行 | `test_operator_saves_own_tenant_provider_row` + 写面不打网关 | ✅ |
| GWT-73.5 /plan outbound=本企业行 | `test_post_plan_byok_outbound_own_row` | ✅ |
| GWT-73.7 /test + `_repair_flow` | `test_post_test_byok_repair_flow_outbound_own_row` | ✅ |
| GWT-73.8 /rescore + `consume_once` | `test_post_rescore_byok_consume_once_outbound_own_row` | ✅ |
| GWT-73.9 similar-suggest | `test_similar_suggest_byok_outbound_own_row` | ✅ |
| GWT-73.6 网关停 /plan 不得 74.1 | `test_post_plan_byok_gateway_down_outbound_own_row_not_74_1` | ✅ |
| GWT-73.10 网关停试采不得 74.1 | `test_post_test_byok_gateway_down_repair_flow_not_74_1` | ✅ |
| GWT-73.11 网关停评分不得 74.1 | `test_post_rescore_byok_gateway_down_consume_once_not_74_1` | ✅ |
| GWT-73.12 网关停第四夹具不得 74.1 | `test_similar_suggest_byok_gateway_down_not_74_1` | ✅ |
| GWT-73.2 无本企业行走 FR-70 | `test_post_plan_no_own_row_follows_fr70` | ✅ |
| GWT-73.3 / 06.6 平台行拒绝 | `test_operator_activate_platform_provider_rejected_row_unchanged` + test 403 | ✅ |
| GWT-73.4 经办点测试连接 | `LlmProviders.test` operator 见「测试连接」+ `/llm` 去 requireAdmin | ✅ |
| SH-09 viewer 403 | `test_create_endpoint_rejects_viewer` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（无新多表写） | ➖ |
| 幂等 | ➖ N/A（无新建幂等键） | ➖ |
| 并发写 | ➖ N/A（未改激活 CASE） | ➖ |
| 外部依赖失败 | 73.6 族网关停 + 本企业行 outbound / `LLM_PROVIDER_ERROR` | ✅ |

## 7. NFR 验证（票里有 NFR 时填）

➖ 本票无独立 NFR 数字闸。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 73.4 点路径：operator `menu:llm` → 侧栏「LLM 配置」→ `/llm`（无 requireAdmin）→ 本企业行「测试连接」可见可点。HTTP 200 无按钮仍不勾。73.6 族网关停不得出现「平台 LLM 网关不可达」。mock：四动作 outbound 经 `get_shared_client`；评分队列 JSON 含 tenant_id。 |
| `/frontend` | 按钮文案「测试连接」；只读 Alert「当前账号不能管理供应商」；失败句连的是本企业行不是网关。`/newapi` 仍平台壳。 |
| `/architect` | 评分 worker 无请求租户上下文：入队写入 `tenant_id`。未改 GWT。 |

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
- [x] 条件更新的 `rows == 0` 已处理（本票无新条件更新）
- [x] 外部依赖四件套齐全（超时/重试/降级/幂等前提）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 票状态已更新为 done
