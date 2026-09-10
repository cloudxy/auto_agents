# 实现证据 · T-30 命令独立可订卡片

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-30.md`｜FR 锚点：FR-39｜角色：/frontend official + admin + /backend｜日期：2026-09-10
> 上游：ADR-0018 · spec v1.6 FR-39 · T-21 五类 · T-22 URL `type=command` · T-23 `list_public` · T-25 订阅一行 · T-28 七叶
> 泳道：L4

不是插件 JSON 货架。命令与智能体仍是独立 catalog 行；订阅不沿父插件级联（ADR-0018）。未改 FR-33 WHERE/COUNT/LIMIT 本体（slash 叠在 `_apply_list_filters`）。未改 T-29 源登记/同步。未改 T-27 引用。未砍治理台命令叶。未实现 slash 执行引擎。未代选六问。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 公开列表 `type=command` | Service | `power_market/service.py` `list_public` | 复用 T-23 `_fr33_clause`；只出 `asset_type=command` |
| slash 搜（可带 `/`） | Service overlay | `_q_clause` → `_apply_list_filters` | 叠 FR-33 之后、COUNT 之前；不改闸函数体 |
| 卡片主标题 + slash | 官网列表 | `Capabilities.tsx` `displaySlash` | `/sdlc`；href `/capabilities/command/{name}` |
| 详情 slash + 正文 | 官网详情 | `CapabilityDetail.tsx` | `body_md` 走同一 `pre`（T-24 纯文本） |
| 筛空句 | 页面 | 复用 T-22 `MarketEmpty` | type=command 是有筛；GWT-31.3 句 |
| 未上架 slash | Service | `_fr33_clause` ∩ slash overlay | GWT-39.3 服务端持有（同 IM-15） |
| 订阅一行 | Service | `subscribe_public` + `insert_install` | 复用 T-25；不级联插件/技能 |
| 治理台命令叶 | admin | `Capabilities.tsx` 七叶 + `onSubscribe` | 不砍叶；订入口开 SubscribeModal |
| 插件抽屉 | admin | `PluginTab.tsx` | 不把 `commands` JSON 当货架 |
| 错误码映射 | 现网 | T-25 `MARKET_*` | 本票无新码 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未把 ORM 送出 API ☑ 未改 GWT/schema ☑ 未改 design tokens 名 ☑ 未改 `uq_asset_type_name_alive` ☑ 未改 FR-33 闸函数体

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/power_market/service.py` | 修改 | slash overlay；list/detail 投影 `slash`/`body_md` |
| `backend/tests/test_t30_command_cards.py` | 新增 | GWT-39.1…39.3 + 订一行不级联 |
| `backend/tests/test_b1c_capabilities_coverage.py` | 修改 | 公开白名单加 `slash` |
| `frontend/official/src/pages/capabilityMarket.ts` | 修改 | `displaySlash` |
| `frontend/official/src/pages/Capabilities.tsx` | 修改 | 命令卡 slash |
| `frontend/official/src/pages/Capabilities.css` | 修改 | slash token 样式 |
| `frontend/official/src/pages/CapabilityDetail.tsx` | 修改 | slash + `body_md` 纯文本 |
| `frontend/official/src/pages/CapabilityDetail.css` | 修改 | slash token 样式 |
| `frontend/official/src/services/capabilities.ts` | 修改 | `slash` / `body_md` 类型 |
| `frontend/official/src/pages/CommandCards.test.tsx` | 新增 | GWT-39.1 / 39.2 |
| `frontend/official/src/pages/CapabilityDetail.test.tsx` | 修改 | 命令详情 XSS 纯文本 + 订阅 CTA |
| `frontend/admin/src/pages/Capabilities.tsx` | 修改 | 命令叶 `onSubscribe` |
| `frontend/admin/src/pages/Capabilities.command.test.tsx` | 新增 | 命令叶可订；抽屉不是 JSON 货架 |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：slash 搜走 T-22 overlay 而非新端；订入口复用 T-25 安装行 + 官网详情 CTA + 治理台命令叶按钮）

**未触碰「不许改的文件」**：☑ 确认（未改 `_fr33_clause`、T-29 源、T-27 refs、T-28 七叶结构、slash 执行引擎）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 公开列表/详情 GET | 否 | 只读 |
| 订命令 | 是 | 复用 T-25 单表 insert；唯一键兜幂等 |

**事务提交后的操作失败怎么办**：N/A（无提交后外部调用）

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | T-25 `(tenant_id, asset_id, host)` + `alive_flag` |
| 保证方式 | 现网唯一约束；本票不新写路径 |
| 重复请求返回 | 200 `created=false`「已订阅」 |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| `type=command` 且 200 空 | 页面筛空 | 「没有符合条件的能力」+「清除筛选」 |
| 未上架 slash 搜 | FR-33 | 200 `items=[]`，不是插件 JSON |

☑ 无条件更新

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 公开列表 API | 现网 client 10s | 本查询 `retry: false` | T-22 失败句 | 只读 |

slash 列非全局唯一（db-spec）；商店身份仍是 catalog `name`。访客 q 可带或不带 `/`。

## 4. ORM 与 DBML 对齐

➖ N/A 本票不加列。消费 T-21 `capability_commands.slash` / `body_md`。未改 `uq_asset_type_name_alive`。☑

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | 现网 `list_public` / `get_public` / `subscribe_public` |
| trace_id | 现网中间件 |
| 错误日志上下文 | 页级 `role="alert"`；不展示堆栈 |
| 慢操作耗时 | slash 子查询叠在闸后 COUNT 前 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

### 九维自查

| 维 | 检查 | 结果 |
|---|---|---|
| ① 间距 | `--space-inset-*` | ✅ |
| ② 颜色 | 组件无 hex；token | ✅ |
| ③ 字体 | `--font-mono` / `--font-size-sm` | ✅ |
| ④ 圆角 | 沿用卡片 token | ✅ |
| ⑤ 图标 | 无新 emoji | ✅ |
| ⑥ 交互态 | 卡为真链接；详情订阅 CTA；命令叶订阅 | ✅ Jest |
| ⑦ 状态完整性 | 命令卡 / 筛空 / 未上架 slash / 非 JSON 货架 | ✅ |
| ⑧ 响应式 | 沿用 grid auto-fill；未量 375/1440 | ☐ |
| ⑨ a11y | 卡 `aria-label`；slash 文本；错误 `role="alert"` | ✅ 基线 |

```
$ rg -n '#[0-9a-fA-F]{3,8}' frontend/official/src/pages/Capabilities.tsx frontend/official/src/pages/Capabilities.css frontend/official/src/pages/capabilityMarket.ts frontend/official/src/pages/CapabilityDetail.tsx frontend/official/src/pages/CapabilityDetail.css frontend/official/src/pages/CommandCards.test.tsx
hex_grep_exit:1
```

## 6. 自测证据

> 命令与退出码**原样粘贴**。TDD：先红后绿。

### TDD 红

```
$ uv run pytest -x -q backend/tests/test_t30_command_cards.py --tb=short
F
=================================== FAILURES ===================================
_________________ test_gwt_39_1_listed_command_card_and_detail _________________
backend/tests/test_t30_command_cards.py:113: in test_gwt_39_1_listed_command_card_and_detail
    assert items[0]["slash"] == "sdlc"
E   KeyError: 'slash'
FAILED backend/tests/test_t30_command_cards.py::test_gwt_39_1_listed_command_card_and_detail
1 failed in 2.06s
```

```
$ uv run pytest -q backend/tests/test_t30_command_cards.py --tb=line
F..F..                                                                   [100%]
E   KeyError: 'slash'
E   AssertionError: assert [] == ['pack__run-task']
FAILED ...test_gwt_39_1_listed_command_card_and_detail
FAILED ...test_listed_command_q_hits_slash_not_in_name_or_title
2 failed, 4 passed in 3.52s
```

slash 红因：list 未投影 `slash`；q 只 LIKE name/title（oracle 正确）。39.2 / 39.3 / type=command 只出命令 / 订一行已绿（复用 T-23 闸 + T-25 安装行）。

```
$ npm test --prefix frontend/official -- --watchAll=false --runInBand src/pages/CommandCards.test.tsx src/pages/CapabilityDetail.test.tsx
FAIL src/pages/CommandCards.test.tsx
  ● GWT-39.1 listed command card appears and opens detail
    TestingLibraryElementError: Unable to find an element by: [data-testid="command-slash"]
FAIL src/pages/CapabilityDetail.test.tsx
  ● GWT-39.1 command detail shows slash, body as text, subscribe, not plugin JSON
    TestingLibraryElementError: Unable to find an element by: [data-testid="command-slash"]
Test Suites: 2 failed, 2 total
Tests:       2 failed, 12 passed, 14 total
```

```
$ npm test --prefix frontend/admin -- --watchAll=false --runInBand --testPathPattern='Capabilities.command'
FAIL src/pages/Capabilities.command.test.tsx
  ✕ command tab remains and listed command opens subscribe one row
  ✓ plugin drawer does not turn commands JSON into a command shelf
    TestingLibraryElementError: Unable to find an accessible element with the role "button" and name "订阅"
Test Suites: 1 failed, 1 total
Tests:       1 failed, 1 passed, 2 total
```

红因：卡/详情无 slash 节点；命令叶未接 `onSubscribe`（oracle 正确，不是 import 失败）。39.2 筛空句与抽屉非 JSON 货架在红轮已绿。

### 绿

```
$ uv run pytest -q backend/tests/test_t30_command_cards.py
......                                                                   [100%]
6 passed in 3.10s

$ uv run pytest -x -q backend/tests/test_t30_command_cards.py backend/tests/test_t22_list_filters.py backend/tests/test_t25_subscribe.py backend/tests/test_b1c_capabilities_coverage.py backend/tests/test_skill_public_api.py
........................................................................ [ 72%]
...........................                                              [100%]
99 passed in 18.56s
pytest_exit:0

$ npm test --prefix frontend/official -- --watchAll=false --runInBand
PASS src/pages/Register.test.tsx
PASS src/pages/Capabilities.test.tsx
PASS src/pages/SkillsSquare.test.tsx
PASS src/pages/CommandCards.test.tsx
PASS src/pages/Home.test.tsx
PASS src/pages/Pricing.test.tsx
PASS src/pages/Pricing.beacon.test.tsx
PASS src/App.test.tsx
PASS src/pages/Home.beacon.test.tsx
PASS src/pages/CapabilityDetail.test.tsx
PASS src/components/layout/SiteLayout.beacon.test.tsx
PASS src/components/home/FeaturesSection.test.tsx
Test Suites: 12 passed, 12 total
Tests:       53 passed, 53 total
Time:        66.067 s
Ran all test suites.
official_jest_exit:0

$ npm test --prefix frontend/admin -- --watchAll=false --runInBand --testPathPattern='Capabilities.command|Capabilities.governance|SubscribeModal|Capabilities.subscribe'
PASS src/pages/Capabilities.governance.test.tsx
PASS src/components/SubscribeModal.test.tsx
PASS src/pages/Capabilities.command.test.tsx
PASS src/pages/Capabilities.subscribe.test.tsx
Test Suites: 4 passed, 4 total
Tests:       25 passed, 25 total
admin_jest_exit:0

$ npm run build --prefix frontend/official
Creating an optimized production build...
Compiled successfully.
official_build_exit:0

$ npm run build --prefix frontend/admin
Creating an optimized production build...
Compiled with warnings.
The build folder is ready to be deployed.
admin_build_exit:0

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

$ bash tools/check/frontend.sh
前端工程门禁（F-2/F-3/F-4/F-5/F-6/F-7 已启用；F-1 批次 2 已由 service 归一承接）
==============================================================
✓ 前端工程门禁通过
frontend_check_exit:0

$ uv run ruff check backend/services/power_market/service.py backend/tests/test_t30_command_cards.py
All checks passed!
ruff_exit:0

$ bash /Users/xuyun/.zcode/local-plugins/sdlc-workflow/scripts/check-sdlc.sh --require --hat implement /Users/xuyun/auto_agents/.sdlc/feat-four-pillars-v2
✓ 泳道声明
----------------------------------------
✓ SDLC 工件合规通过
sdlc_exit:0
```

`llm_gw_grep_exit:1` = 零命中。`SkillsSquare.test.tsx` GWT-30.2 / 44.2 仍绿。`CapabilityDetail.test.tsx` GWT-32.4 / 32.5 仍绿。治理台七叶 GWT-37.1 / 37.2 仍绿。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-39.1 该卡出现且可进详情 | official `GWT-39.1 listed command card…` + 详情 slash/正文/订阅 CTA；后端 `test_gwt_39_1_listed_command_card_and_detail` | ✅ |
| GWT-39.2 筛选空态句，不是插件 JSON 货架 | official `GWT-39.2 command filter empty…`；后端 `test_gwt_39_2_no_listed_command_is_empty_not_plugin_json` | ✅ |
| GWT-39.3 未上架 slash 不出现 | 后端 `test_gwt_39_3_unlisted_slash_not_in_public_search`（前端不宣称空洞缺席，同 IM-15） | ✅ 服务端 |
| 公开 `type=command` 只出命令卡 | `test_type_command_does_not_include_plugin_or_skill` | ✅ |
| 已上架命令可订一行、不级联 | `test_subscribe_command_one_row_no_cascade`；admin 命令叶开窗不自动 POST | ✅ |
| 列名/标题不含 slash 时 q=/sdlc 仍命中已上架 | `test_listed_command_q_hits_slash_not_in_name_or_title` | ✅ |
| 不砍命令叶 | admin `command tab remains…` + T-28 GWT-37.1 | ✅ |
| 插件抽屉不是命令货架 | admin `plugin drawer does not turn commands JSON…` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A | 订命令复用 T-25 单表 insert；本票无多步新写 |
| 幂等 | 复用 T-25 `test_gwt_34_6_idempotent_same_host` | ✅ 回归 99 内 |
| 并发写 | ➖ N/A | 本票无新条件更新 |
| 外部依赖失败 | 列表失败仍走 T-22 31.4，不是 39.2 筛空 | ✅ `Capabilities.test.tsx` |
| 礼包/级联 | 订命令 1 行；插件/技能 asset_id 不在安装表 | ✅ |
| JSON 货架 | type=command 空页无 `plugin.json` / `commands` JSON；抽屉不渲染 `/shelf-slash` | ✅ |

## 7. NFR 验证

本票无独立 NFR。NFR-03 失败不得装空仍由 T-22 31.4 持有（本闸 official 全绿）。NFR-07 `power_market/` 零命中 `llm_gateway`：`llm_gw_grep_exit:1`。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 命令卡 = catalog 行，不是 `capability_plugins.commands`。筛「命令」空 = 「没有符合条件的能力」+「清除筛选」+ filter-echo `type=command`。访客搜未上架 slash（可带 `/`）公开列表为空。订命令只插这一行。详情正文 `body_md` 纯文本。 |
| `/backend` | 公开 JSON 命令行可带 `slash`；详情另带 `body_md`。list 白名单已含 `slash`。q overlay 命中 `capability_commands.slash`。 |
| `/architect` | 无新错误码。slash 非全局唯一，商店身份仍是 catalog name。 |
| T-29 / T-27 / T-33 | 未改源同步、引用解析、alias。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿
- [x] 契约落位表已核对；未改 GWT/schema
- [x] ORM N/A（未加列）
- [x] 无硬编码连接串/密钥/端口；列表/详情无 hex
- [x] 无同步 redis 直调
- [x] 无 `except: pass`
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」
- [x] 条件更新 N/A
- [x] 外部依赖：失败可重试；非法类型不进列表
- [x] 四类易漏已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已写入下游，未自行写 slash 引擎
- [x] 票状态已更新为 done
