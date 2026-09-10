# 实现证据 · T-25 订阅只作用于这一行；不礼包；宿主两态；不占配额

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-25.md`｜FR 锚点：FR-34 / FR-32.6–32.8｜角色：/backend｜日期：2026-09-09
> 上游：ADR-0018 · spec v1.6 FR-34 · db-spec `capability_installs` / `host_compat`
> 泳道：L4

未实现 T-26「我的安装」全套列表/卸载 UI（GET `/capabilities/installs` 可查询本票写入行）；未实现 T-27 引用解析；未实现 T-28 七叶；未实现 T-33 alias；无 enable-host。未复活 028–030。未把 `capability_installs` 写入 `TENANT_EXEMPT_TABLES`。未改 T-23 `list_public` FR-33 WHERE/COUNT/LIMIT、GET 404 HTML、分页 total。未改 `frontend/official`。未代选六问。`power_market/` 零命中 `llm_gateway`。

宿主两态禁止都叫「空」：34.9 夹具 `host_compat IS NULL`（未声明/未给出名单）；34.10 夹具 `host_compat=[]`（已声明且名单为零项）。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径/方法/状态码 | Router | `backend/app/api/v1/capabilities.py` `public_skills.py` | POST subscribe；GET `/capabilities/installs` 静态段先于动态详情 |
| 字段校验（host） | Schema | `power_market/types.py` `SubscribeRequest` | 未上架先 `MARKET_NOT_FOUND`，不因缺 host 盖信封 |
| 跨字段参数约束 | Schema | 同上 | host ∈ 四宿主 |
| 权限判定（数据范围） | **Service** | `power_market/installs.py` `_assert_actor` | viewer→`MARKET_READONLY_ROLE`；无 tenant→`MARKET_NEEDS_TENANT` |
| 业务规则/状态流转 | Service | `service.py` `subscribe_public` + `installs.py` | 已上架才订；不礼包；不占配额；宿主两态 |
| 数据读写 | Service/ORM | `CapabilityInstall` | 唯一键兜幂等 |
| 错误码映射 | 统一异常处理器 | `BusinessException` `code=` | 禁止用 message 分支 |
| 幂等 | Service + 唯一约束 | `uq_installs_tenant_asset_host_alive` | IntegrityError → 已订阅 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未把 ORM 送出 API ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `platform_core/models/capability.py` | 修改 | `host_compat` + `CapabilityInstall` TenantMixin |
| `platform_core/models/__init__.py` | 修改 | 导出 Install |
| `backend/alembic/versions/035_t25_installs_host_compat.py` | 新增 | revises 034 |
| `backend/services/power_market/types.py` | 修改 | 错误码/文案/`SubscribeRequest` |
| `backend/services/power_market/installs.py` | 新增 | 写行/列表/宿主两态 |
| `backend/services/power_market/service.py` | 修改 | subscribe 写行；hosts 投影；list_installs |
| `backend/app/api/v1/public_skills.py` | 修改 | POST 传 host+user（信封不变） |
| `backend/app/api/v1/capabilities.py` | 修改 | 后台订阅 + GET installs |
| `backend/tests/test_t25_subscribe.py` | 新增 | GWT-34.1…34.13 + 32.6/32.7/32.8 行 |
| `backend/tests/t25_support.py` | 新增 | 租户经办绑定 |
| `backend/tests/test_saas_isolation.py` | 修改 | 安装表 UPDATE/DELETE 注入 tenant_id |
| `backend/tests/test_skill_public_api.py` | 修改 | 32.7 回跳 401 + 0 行（表已存在） |
| `backend/tests/test_b1c_capabilities_coverage.py` | 修改 | 同上 |
| `frontend/admin/src/components/SubscribeModal.tsx` | 新增 | 选宿主；code 映射错误 |
| `frontend/admin/src/pages/Capabilities.tsx` | 修改 | 回跳 query 开窗，不自动 POST |
| `frontend/admin/src/pages/Skills.tsx` | 修改 | 订阅按钮 |
| `frontend/admin/src/services/capabilities.ts` | 修改 | subscribe/listInstalls |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：落地 db-spec 已列 `host_compat` + 安装表；未发明列；未改目录 uq）

**未触碰「不许改的文件」**：☑ 确认（未改 FR-33 查询闸、GET 404 HTML、official、T-26 卸载 UI、028–030、TENANT_EXEMPT）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 插入安装行 | 是 | 单表写；flush 撞唯一键则 rollback 返回已订阅 |
| 配额检查 | 否 | 订阅不调三类配额闸 |

**事务提交后的操作失败怎么办**：N/A（无提交后外部调用）

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 业务自然键 `(tenant_id, asset_id, host)` + `alive_flag` |
| 保证方式 | 唯一约束 `uq_installs_tenant_asset_host_alive` + 捕获 IntegrityError |
| 重复请求返回 | 200 + `created=false` + 文案「已订阅」 |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 重复订同一宿主 | 唯一键冲突 | IntegrityError → 已订阅，行数不变 |

☑ 无条件更新

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 无新外部依赖 | — | — | — | — |

## 4. ORM 与 DBML 对齐

☑ 字段名 ☑ 类型 ☑ 可空性 ☑ 默认值 ☑ 索引 ☑ 唯一约束 ☑ 外键 —— `capability_installs`：`tenant_id` NOT NULL；`uq_installs_tenant_asset_host_alive`；`idx_installs_asset`；FK asset/tenant RESTRICT；`enabled` default 1；`trusted` default 0；`alive_flag` 生成列。`capability_assets.host_compat` JSON NULL。未改 `uq_asset_type_name_alive`。

结构核对输出：

```
$ bash tools/check/db_migrations.sh
迁移破坏性变更检测（strong_migrations 语义）
==============================================
✓ 迁移破坏性变更检测通过
mig_exit:0
```

035 revises 034。`enabled`/`trusted`/`created_at` 带 server_default。未复活 028–030。

**未自行加字段/改类型**：☑ 确认（仅落地 db-spec 已列）

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `subscribe_public` / `insert_install` / `list_installs` |
| trace_id | 现网中间件 |
| 错误日志上下文 | 业务异常经统一 handler |
| 慢操作耗时 | 单行 insert |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。

红（TDD，写路径尚未挂路由）：

```
$ uv run pytest -x -q backend/tests/test_t25_subscribe.py::test_gwt_34_1_subscribe_grok_creates_row --tb=short
F
=================================== FAILURES ===================================
___________________ test_gwt_34_1_subscribe_grok_creates_row ___________________
backend/tests/test_t25_subscribe.py:63: in test_gwt_34_1_subscribe_grok_creates_row
    assert resp.status_code == 200, resp.text
E   AssertionError: {"detail":"Not Found"}
E   assert 404 == 200
FAILED backend/tests/test_t25_subscribe.py::test_gwt_34_1_subscribe_grok_creates_row
1 failed in 6.99s
```

绿：

```
$ uv run pytest -x -q backend/tests/test_saas_isolation.py backend/tests/test_skill_public_api.py backend/tests/test_b1c_capabilities_coverage.py backend/tests/test_t25_subscribe.py
........................................................................ [ 74%]
.........................                                                [100%]
97 passed in 14.54s
pytest_exit:0

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
arch_exit:0

$ grep -rn llm_gateway backend/services/power_market/; echo "llm_gw_grep_exit:$?"
llm_gw_grep_exit:1

$ uv run python /Users/xuyun/.zcode/local-plugins/sdlc-workflow/skills/impl-evidence/scripts/check-layering.py
✓ 分层依赖检查通过
layering_exit:0

$ npm run build --prefix frontend/admin
> admin@0.1.0 build
> react-scripts build
Creating an optimized production build...
Compiled with warnings.
The build folder is ready to be deployed.
admin_build_exit:0

$ npm test --prefix frontend/admin -- --watchAll=false --testPathPattern='SubscribeModal|Capabilities.subscribe'
Test Suites: 2 passed, 2 total
Tests:       6 passed, 6 total
jest_exit:0

$ bash /Users/xuyun/.zcode/local-plugins/sdlc-workflow/scripts/check-sdlc.sh --require --hat implement /Users/xuyun/auto_agents/.sdlc/feat-four-pillars-v2
✓ 泳道声明
----------------------------------------
✓ SDLC 工件合规通过
sdlc_exit:0
```

`llm_gw_grep_exit:1` = 零命中（空输出）。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-34.1 订到 Grok 多一行 | `test_gwt_34_1_subscribe_grok_creates_row` | ✅ |
| GWT-34.2 预告拒绝无行 | `test_gwt_34_2_coming_soon_rejected_no_row` | ✅ |
| GWT-34.3 只读角色 | `test_gwt_34_3_readonly_role_rejected` | ✅ |
| GWT-34.4 超管无企业 | `test_gwt_34_4_platform_admin_needs_tenant` | ✅ |
| GWT-34.5 再订另一宿主 | `test_gwt_34_5_second_host_does_not_overwrite` | ✅ |
| GWT-34.6 幂等 | `test_gwt_34_6_idempotent_same_host` | ✅ |
| GWT-34.7 仅 Kimi 拒 Grok | `test_gwt_34_7_declared_kimi_only_rejects_grok` | ✅ |
| GWT-34.8 不礼包 | `test_gwt_34_8_plugin_no_gift_child_rows` | ✅ |
| GWT-34.9 未声明名单 | `test_gwt_34_9_undeclared_host_compat_allows_any` | ✅ |
| GWT-34.10 已声明零项 | `test_gwt_34_10_declared_zero_hosts_rejects` | ✅ |
| GWT-34.11 不占配额 | `test_gwt_34_11_quota_full_still_subscribes` | ✅ |
| GWT-34.12 父未上架不挡子卡 | `test_gwt_34_12_unlisted_parent_does_not_block_child` | ✅ |
| GWT-34.13 不得订未上架父 | `test_gwt_34_13_unlisted_parent_store_not_found` | ✅ |
| GWT-32.6 未登录 401 无行 | `test_gwt_32_6_anonymous_subscribe_401` | ✅ |
| GWT-32.7 回跳仍 0 行 | `test_gwt_32_7_login_bounce_no_install_row` | ✅ |
| GWT-32.8 未上架无行 | `test_gwt_32_8_unlisted_subscribe_no_row` | ✅ |
| PIT-3 禁豁免夹具 | `test_capability_installs_update_delete_injects_tenant_id` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | IntegrityError 路径 rollback 后查已有行 | ✅ `test_gwt_34_6_idempotent_same_host` |
| 幂等 | 同上 | ✅ |
| 并发写 | 唯一约束兜底（同 34.6） | ✅ |
| 外部依赖失败 | ➖ N/A | 无新外部调用；不打配额/网关 |

## 7. NFR 验证（票里有 NFR 时填）

本票无独立 NFR。NFR-01/02 属 T-23 查询侧，未改。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 错误码用 `code`：`MARKET_NOT_FOUND` / `MARKET_COMING_SOON` / `MARKET_HOST_INCOMPAT` / `MARKET_READONLY_ROLE` / `MARKET_NEEDS_TENANT`。34.9 NULL ≠ 34.10 `[]`。GET 详情仍 HTML 404；POST 未上架仍 JSON NOT_FOUND。GET `/api/v1/capabilities/installs` 可读行。 |
| `/frontend` | 后台 POST `{host}`；成功 `data.message`「已订阅到 Grok」；重复「已订阅到 {host}，没有新增行。」。错误按 `code`：`MARKET_NOT_FOUND`「没有这个能力，不能订阅。」/`MARKET_COMING_SOON`「这是预告项，现在不能订阅。」。回跳 `/capabilities?subscribeType=&subscribeName=` 只开窗不自动订。四宿主位始终在；`hosts=[]` 全禁用。 |
| `/architect` | 无新错误码。T-26 接 GET installs + 卸载。 |

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
- [x] 条件更新的 `rows == 0` 已处理
- [x] 外部依赖四件套齐全（超时/重试/降级/幂等前提）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 票状态已更新为 done

## Rework（IM-06 / IM-07 / IM-08 / IM-09 / IM-11）

审查会话 `01a08695-6df8-7d40-bc30-09526b7ea3db` G-fresh FAIL。本返工只关 T-25 侧。未改 `frontend/official`（T-24 发 bounce URL）。未改 FR-33 / GET 404 HTML / installs 隔离。未把 `capability_installs` 写入 `TENANT_EXEMPT_TABLES`。未代选六问。

| ID | 处置 |
|---|---|
| IM-06 / QA-01 | `COPY_BY_CODE` + 后端信封按 `code`：`MARKET_NOT_FOUND`→「没有这个能力，不能订阅。」；`MARKET_COMING_SOON`→「这是预告项，现在不能订阅。」；幂等 `created=false`→「已订阅到 {host}，没有新增行。」。首次成功仍「已订阅到 Grok」（GWT-34.1）。 |
| IM-07 / QA-02 | `host_compat=[]` 仍渲染 Grok/ZCode/Kimi/Claude 四个 Radio 全禁用 + 旁注。禁止单句替代 Radio 组。jest：`declared zero hosts still renders four disabled radios`。 |
| IM-08 / QA-03 | 继续读 `subscribeType`/`subscribeName`；开窗不自动 POST。官网 `from=` 由 T-24 改。 |
| IM-09 / QA-04 | 插件 Tab 删「插件经 MCP 验证后方可分发（ADR-0001）」→「上架不等于验证通过」。 |
| IM-11 / QA-06 | 票头 **done**；GWT 勾选与测试覆盖对齐。 |

```
$ uv run pytest -x -q backend/tests/test_t25_subscribe.py backend/tests/test_saas_isolation.py
.............................                                            [100%]
29 passed in 8.17s
pytest_exit:0

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
arch_exit:0

$ uv run python /Users/xuyun/.zcode/local-plugins/sdlc-workflow/skills/impl-evidence/scripts/check-layering.py
✓ 分层依赖检查通过
layering_exit:0

$ grep -rn llm_gateway backend/services/power_market/; echo "llm_gw_grep_exit:$?"
llm_gw_grep_exit:1

$ npm test --prefix frontend/admin -- --watchAll=false --testPathPattern='SubscribeModal|Capabilities.subscribe'
Test Suites: 2 passed, 2 total
Tests:       11 passed, 11 total
jest_exit:0

$ npm run build --prefix frontend/admin
> admin@0.1.0 build
> react-scripts build
Creating an optimized production build...
Compiled with warnings.
The build folder is ready to be deployed.
admin_build_exit:0

$ bash /Users/xuyun/.zcode/local-plugins/sdlc-workflow/scripts/check-sdlc.sh --require --hat implement /Users/xuyun/auto_agents/.sdlc/feat-four-pillars-v2
✓ 泳道声明
----------------------------------------
✓ SDLC 工件合规通过
sdlc_exit:0
```

`llm_gw_grep_exit:1` = 零命中。

## Debug record

- **Reproduce**：G-fresh FAIL QA-01/02/04/06（T-25 侧）。弹窗 `COPY_BY_CODE` 与 `MSG_*` 偏离 edge-states；`declaredEmpty` 用单句替换 Radio 组；插件 Tab 残留 ADR-0001；票头 todo。
- **Eliminated**：后端 34.9/34.10 夹具仍成立；GET HTML vs POST JSON 未混；回跳 query 已是 `subscribeType`/`subscribeName`（IM-08 本侧无需改路径）。
- **Root cause**：用户可见句与宿主空态按实现便利缩短，未锁 edge-states 冻结句/四位始终在。
- **Minimal fix**：冻结句进 `types.py` + `COPY_BY_CODE`（按 `code`）；Radio 组无条件渲染；插件 Tab listed≠verify；票头 done。
- **Re-run**：上表 pytest 29 / arch 0 / jest 11 / admin_build 0。
