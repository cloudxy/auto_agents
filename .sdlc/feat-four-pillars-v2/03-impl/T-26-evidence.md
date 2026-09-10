# 实现证据 · T-26 「我的安装」；unlist 残留可卸；安装行只读 vs 只读角色

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-26.md`｜FR 锚点：FR-35 / FR-40.2｜角色：/backend｜日期：2026-09-09
> 上游：ADR-0018 · spec v1.6 FR-35 QA-03 · db-spec `capability_installs` · T-25 GET installs
> 泳道：L4

未实现 T-27 引用解析；未实现 T-28 七叶；未实现 T-33 alias；无 enable-host。未复活 028–030。未把 `capability_installs` 写入 `TENANT_EXEMPT_TABLES`。未改 T-23 `list_public` FR-33 WHERE/COUNT/LIMIT、GET 404 HTML、分页 total。未改 subscribe 唯一键。未改 `frontend/official`。未代选六问。`power_market/` 零命中 `llm_gateway`。

两句「只读」分夹具：35.4/35.7 经办可卸黑名单行且 PATCH 不是 `MARKET_READONLY_ROLE`；35.5 只读角色（含黑名单行）卸载/改启用/信任均为 `MARKET_READONLY_ROLE`，行不变。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径/方法/状态码 | Router | `backend/app/api/v1/capabilities.py` | GET `/installs`；PATCH/DELETE `/installs/{id}` 静态段先于动态详情 |
| 字段校验（enabled/trusted 0\|1） | Schema | `power_market/types.py` `PatchInstallRequest` | 至少一项 |
| 跨字段参数约束 | Schema | 同上 | 纯 0/1 |
| 权限判定（数据范围） | **Service** | `installs.py` `_assert_writer` / `_require_tenant` | 写权限先看 `tenant_role`（`viewer` 只读；`owner\|admin\|operator` 可写）；无 `tenant_role` 再回落平台 `role`。只读→`MARKET_READONLY_ROLE`；无 tenant→`MARKET_NEEDS_TENANT` |
| 业务规则/状态流转 | Service | `installs.py` patch/uninstall + 投影 | unlist 残留；flags_locked 可卸不可改开关；卸一行不连坐 |
| 数据读写 | Service/ORM | `CapabilityInstall` 软删 | 条件 `deleted_at IS NULL` + `tenant_id` |
| 错误码映射 | 统一异常处理器 | `BusinessException` `code=` | 只读角色用 `code`，禁止用 message 分支 |
| 幂等 | 软删 UNIQUE | `uq_installs_tenant_asset_host_alive` | 已卸行 404；可再订（本票不测再订） |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未把 ORM 送出 API ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/power_market/types.py` | 修改 | 安装只读文案、`PatchInstallRequest` |
| `backend/services/power_market/installs.py` | 修改 | 投影 delisted/flags；PATCH/DELETE 软删；IM-14 `_is_readonly` 先 `tenant_role` |
| `backend/services/power_market/service.py` | 修改 | `patch_install` / `uninstall` |
| `backend/app/api/v1/capabilities.py` | 修改 | PATCH/DELETE `/installs/{id}` |
| `backend/tests/test_t26_installs.py` | 新增/修改 | GWT-35.1…35.7 + 40.2；35.4 软删夹具；IM-14 `test_gwt_35_1_production_operator_shape` |
| `frontend/admin/src/services/capabilities.ts` | 修改 | patch/uninstall + 投影字段 |
| `frontend/admin/src/pages/installsCopy.ts` | 新增 | 冻结句 |
| `frontend/admin/src/pages/MyInstalls.tsx` | 新增 | 五类分组；确认卸/信任；无 enable-host |
| `frontend/admin/src/pages/MyInstalls.test.tsx` | 新增 | 35.1…35.7 / 40.2 UI |
| `frontend/admin/src/App.tsx` | 修改 | `/capabilities/installs` |
| `frontend/admin/src/config/menuConfig.tsx` | 修改 | tenantOnly「我的安装」 |
| `frontend/admin/src/hooks/usePermission.test.tsx` | 修改 | 租户可见 / 无企业隐藏 |
| `.sdlc/feat-four-pillars-v2/02-shape/tickets/T-26.md` | 修改 | done + GWT 勾选 |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：admin 新页 `MyInstalls` 而非改 official；无新 Alembic，035 列已齐）

**未触碰「不许改的文件」**：☑ 确认（未改 FR-33 查询闸、GET 404 HTML、subscribe 唯一性、official、T-27/T-28、028–030、TENANT_EXEMPT）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| PATCH enabled/trusted | 是 | 单行；flags_locked 在写前拒绝 |
| DELETE 软删 | 是 | 单行；不碰子技能/合集边 |

**事务提交后的操作失败怎么办**：N/A（无提交后外部调用）

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 存活自然键 `(tenant_id, asset_id, host, alive_flag)` |
| 保证方式 | 软删后 `alive_flag` NULL 脱离 UNIQUE；再订走 T-25 insert |
| 重复卸载 | 已无存活行 → `NotFoundException`「安装行」 |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 卸已卸行 | `WHERE id+tenant_id+deleted_at IS NULL` 再写 | 找不到 → 404 |

☑ 无条件更新（flags_locked 在写前分支，不静默 0 行）

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 无新外部依赖 | — | — | — | — |

## 4. ORM 与 DBML 对齐

☑ 字段名 ☑ 类型 ☑ 可空性 ☑ 默认值 ☑ 索引 ☑ 唯一约束 ☑ 外键 —— 未加列。卸载用已有 `deleted_at` / `alive_flag`。`enabled`/`trusted` 仍 TINYINT。禁止豁免。

结构核对输出：无新迁移。035 已含安装表全列。

**未自行加字段/改类型**：☑ 确认（未发明列；revises 035 不需要）

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `list_tenant_installs` / `patch_live_install` / `uninstall_live_install` |
| trace_id | 现网中间件 |
| 错误日志上下文 | 业务异常经统一 handler；`code` 判断 |
| 慢操作耗时 | 单行 update |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。

红（TDD，投影尚无 `can_uninstall` / 无 PATCH/DELETE）：

```
$ uv run pytest -x -q backend/tests/test_t26_installs.py::test_gwt_35_1_two_rows_can_uninstall --tb=short
F
=================================== FAILURES ===================================
_____________________ test_gwt_35_1_two_rows_can_uninstall _____________________
backend/tests/test_t26_installs.py:89: in test_gwt_35_1_two_rows_can_uninstall
    assert all(row["can_uninstall"] for row in items)
E   KeyError: 'can_uninstall'
FAILED backend/tests/test_t26_installs.py::test_gwt_35_1_two_rows_can_uninstall
1 failed in 2.23s
```

绿：

```
$ uv run pytest -x -q backend/tests/test_t26_installs.py backend/tests/test_t25_subscribe.py backend/tests/test_saas_isolation.py
......................................                                   [100%]
38 passed in 7.06s
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

$ cd frontend/admin && npx jest src/pages/MyInstalls.test.tsx src/hooks/usePermission.test.tsx --runInBand --forceExit
PASS src/pages/MyInstalls.test.tsx
PASS src/hooks/usePermission.test.tsx
Test Suites: 2 passed, 2 total
Tests:       16 passed, 16 total
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
| GWT-35.1 两行都在可卸 | `test_gwt_35_1_two_rows_can_uninstall` | ✅ |
| GWT-35.1 生产经办形 | `test_gwt_35_1_production_operator_shape`（`role=viewer` + `tenant_role=operator`） | ✅ |
| GWT-35.2 空 ≠ 加载失败 | `test_gwt_35_2_empty_not_load_fail` + jest empty | ✅ |
| GWT-35.3 unlist 残留 | `test_gwt_35_3_unlist_residual_operator_can_uninstall` | ✅ |
| GWT-35.4 安装行只读可卸 | `test_gwt_35_4_blacklist_row_flags_locked_operator_can_uninstall`（另 `test_gwt_35_4_soft_delete_asset_flags_locked`） | ✅ |
| GWT-35.7 卸黑名单其它行在 | `test_gwt_35_7_uninstall_blacklist_row_others_stay` | ✅ |
| GWT-35.5 只读角色拒绝 | `test_gwt_35_5_readonly_refuses_including_blacklist` | ✅ |
| GWT-35.6 卸插件不连坐 | `test_gwt_35_6_uninstall_plugin_keeps_child_skill` | ✅ |
| GWT-40.2 无宿主运行句/无 enable-host | `test_gwt_40_2_no_enable_host_copy` + jest | ✅ |
| PIT-3 禁豁免 | `test_capability_installs_update_delete_injects_tenant_id` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（单行写；flags_locked 写前拒绝，无多表） | ➖ |
| 幂等 | 已卸再 DELETE → 404；UNIQUE 仍带 alive_flag | ✅ 路径在 uninstall `_load_live_pair` |
| 并发写 | 存活谓词 `deleted_at IS NULL`；找不到当 404 | ✅ |
| 外部依赖失败 | ➖ N/A | 无新外部调用；不打配额/网关 |

## 7. NFR 验证（票里有 NFR 时填）

本票无独立 NFR。NFR-01/02 属 T-23 查询侧，未改。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 错误码用 `code`：只读角色 `MARKET_READONLY_ROLE`（安装改/卸文案「当前账号不能改安装。请联系企业管理员。」）。flags_locked PATCH 是 409 `BUSINESS_ERROR`，**禁止**用 `MARKET_READONLY_ROLE` 勾 35.4。空列表 200 + `items=[]`，空句只在 UI。 |
| `/frontend` | GET items：`delisted`/`delisted_label`/`flags_locked`/`can_change_flags`/`can_uninstall`/`resubscribe_allowed`/`resubscribe_hint`。再订禁用句「已下架，不能新订」。无 enable-host。 |
| `/architect` | 未新造 MARKET_*。flags_locked 复用 `BUSINESS_ERROR` 以免与只读角色互勾。 |

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

## Rework · IM-14 / QA-01 BLOCKER

> 独立 G-fresh FAIL 会话 `01a086d3-0fcf-7452-ad0b-67ae73ca5143`。只修经办写权限；保持 35.4 vs 35.5 分夹具。未改 FR-33、official、TENANT_EXEMPT、六问。无 enable-host。卸插件不连坐。

### 复现

`member_service` 邀请经办落 `User.role=viewer` + `tenant_role=operator`。旧 `_is_readonly` 把平台 `role==viewer` **OR** `tenant_role==viewer`，生产经办被当成只读角色。旧夹具 `role=operator` 与写入路径不一致。

排除：安装行豁免、35.4/35.5 合成一个「只读」、flags_locked 误用 `MARKET_READONLY_ROLE`。

### 根因（一行）

写权限 OR 了平台 `role`，覆盖了真实 `tenant_role=operator`。

### 最小修复

`installs.py` `_is_readonly`：有 `tenant_role` 则只看租户角色（`viewer` 只读；`owner|admin|operator` 可写）；缺失再回落平台 `role`。补夹具 `test_gwt_35_1_production_operator_shape`。

### 红（夹具先于修复）

```
$ uv run pytest -x -q backend/tests/test_t26_installs.py::test_gwt_35_1_production_operator_shape --tb=short
F
=================================== FAILURES ===================================
___________________ test_gwt_35_1_production_operator_shape ____________________
backend/tests/test_t26_installs.py:107: in test_gwt_35_1_production_operator_shape
    assert row["can_uninstall"] is True
E   assert False is True
FAILED backend/tests/test_t26_installs.py::test_gwt_35_1_production_operator_shape
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 2.15s
pytest_exit:1
```

### 绿

```
$ uv run pytest -x -q backend/tests/test_t26_installs.py backend/tests/test_t25_subscribe.py backend/tests/test_saas_isolation.py
.......................................                                  [100%]
39 passed in 7.11s
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
```

### 本轮夹具

| 夹具 | 期望 | 结果 |
|---|---|---|
| `role=viewer` `tenant_role=operator` | list `can_uninstall=true`；DELETE 200；非 `MARKET_READONLY_ROLE` | ✅ `test_gwt_35_1_production_operator_shape` |
| `role=viewer` `tenant_role=viewer` | 仍 `MARKET_READONLY_ROLE`，行不变 | ✅ `test_gwt_35_5_readonly_refuses_including_blacklist` |
| flags_locked 经办可卸黑名单行 | PATCH 非只读码；DELETE 200 | ✅ 35.4 |
| 卸插件不礼包 | 子技能行仍在 | ✅ 35.6 |
| installs 未豁免 | `capability_installs` 不在 `TENANT_EXEMPT_TABLES` | ✅ `test_saas_isolation` |
| 无 enable-host | 响应无宿主运行句 | ✅ 40.2 |
