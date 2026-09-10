# 实现证据 · T-32 市场事件可查

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-32.md`｜FR 锚点：FR-43 / NFR-08｜角色：/backend + 双前端｜日期：2026-09-10
> 上游：ADR-0016 · metrics-blueprint v1.4 · spec v1.6 FR-43（QA-14 / QA-22）
> 泳道：L4

未建仓；未做精确一次键；未改事件名；未给租户分析查询面；未改 FR-33 许可谓词（T-31）；未实现 T-33 alias；未代选六问；未复活 028–030；未加列。`power_market/` 零命中 `llm_gateway`。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径/方法/状态码 | Router | `product_events.py` 复用 GET `/product-events`；公开 list/detail/subscribe 在 `public_skills.py`；后台 subscribe 在 `capabilities.py` | 查询仅超管 200；租户 404 |
| 字段校验（类型/范围/枚举） | Schema | `platform_core/schemas/product_event.py` `MARKET_EVENT_NAMES` | 事件名原样；公开 ingest 仍只允许 Wave 0 两名 |
| 跨字段参数约束 | Schema | 同上 | 无新列 |
| 权限判定（数据范围） | Router | `require_platform_admin_or_404` | 与 T-05 / T-12 同形 HTTP 404 |
| 业务规则/状态流转 | Service | `market_events.py` + listing/sync/installs | 预告拒订 `reason=coming_soon`；失败不挡主路径 |
| 数据读写 | Repository | `product_event_repository.py`（T-12） | 按 `occurred_at` 倒序；name/tenant 过滤 |
| 错误码映射 | 统一异常处理器 | 订阅拒绝仍 `MARKET_COMING_SOON` 等 | Router 无业务 try/except 吞掉 |
| 幂等 | N/A | 无 UNIQUE | 合同禁止精确一次键；至少一次 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未把 ORM 送出 API ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/market_events.py` | 新增 | 投递助手；订阅成功/拒绝；公开 list/search/detail |
| `backend/app/api/v1/public_skills.py` | 修改 | 公开 list/detail/subscribe 接线 |
| `backend/app/api/v1/capabilities.py` | 修改 | 后台 subscribe 走 `run_subscribe` |
| `backend/services/power_market/listing.py` | 修改 | `market_listing_changed` 旧态/新态 |
| `backend/services/power_market/sync.py` | 修改 | `market_source_sync_completed` 成功数/失败数 |
| `backend/services/power_market/installs.py` | 修改 | uninstall 后 `market_uninstalled` 含 host |
| `platform_core/schemas/product_event.py` | 修改 | `MARKET_EVENT_NAMES` 常量（不加列） |
| `backend/tests/test_t32_market_events.py` | 新增 | GWT-43.1…43.10 + 投递失败不挡订阅 |
| `frontend/admin/src/pages/ProductEvents.tsx` | 修改 | 超管查询占位含市场事件名 |
| `frontend/admin/src/pages/ProductEvents.test.tsx` | 修改 | 可按 `market_subscribe_succeeded` 过滤 |
| `frontend/admin/src/App.test.tsx` | 修改 | GWT-43.3 租户直打同形 404 |
| `frontend/admin/src/hooks/usePermission.test.tsx` | 修改 | 导航无「市场分析」 |
| `frontend/official/src/pages/Capabilities.test.tsx` | 修改 | 官网无租户分析面；筛选项仍走公开列表 |
| `frontend/official/src/pages/CapabilityDetail.test.tsx` | 修改 | 详情无分析入口 |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：查询面复用 T-12 `/product-events` + 平台运营台 Tab，未新建租户分析路由）

**未触碰「不许改的文件」**：☑ 确认（未改 FR-33 WHERE、许可 allowlist、`public_license_override` 写、T-33 alias、028–030）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 订阅/卸载/上架/同步主路径 | 否 | 上报失败不挡；事件用 T-12 独立短会话 |
| 事件行写入 | 独立短会话 commit | 主路径 rollback 不得带走已发生事实 |

**事务提交后的操作失败怎么办**：记日志，事件可缺失（至少一次；GWT 投递失败订阅仍 200）

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 无（合同禁止） |
| 保证方式 | 至少一次追加，允许重复 |
| 重复请求返回 | 再插一行 |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 追加写 | INSERT | N/A（无条件更新） |

☑ 无条件更新

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 事件落库 | 会话默认 | 无 | 吞异常，主路径成功 | 允许重复 |

## 4. ORM 与 DBML 对齐

☑ 字段名 ☑ 类型 ☑ 可空性 ☑ 默认值 ☑ 索引 ☑ 无唯一约束 ☑ 无 FK —— 复用 T-12 `product_events`，本票不加列

结构核对输出：

```
本票无新迁移。查询/写入仍走 alembic 031 product_events
（occurred_at UTC NOT NULL, event_name, tenant_id NULL, props JSON）。
```

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `emit_market_event` / `run_subscribe` / list/detail 记 name+tenant |
| trace_id | 既有中间件 |
| 错误日志上下文 | 上报失败 warning 含 event_name（T-12 emit） |
| 慢操作耗时 | 未加独立计时（追加写） |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。

红（TDD：投递未接线，GWT-43.1 订阅 200 但查询面无事件）：

```
$ uv run pytest -x -q backend/tests/test_t32_market_events.py::test_gwt_43_1_market_subscribe_succeeded --tb=short
F
=================================== FAILURES ===================================
___________________ test_gwt_43_1_market_subscribe_succeeded ___________________
backend/tests/test_t32_market_events.py:92: in test_gwt_43_1_market_subscribe_succeeded
    assert rows, resp.text
E   AssertionError: {"success":true,"code":"SUCCESS","message":"操作成功","data":{"created":true,"already_subscribed":false,"message":"已订阅到 Grok","host":"grok","asset_id":1},"request_id":null}
E   assert []
FAILED backend/tests/test_t32_market_events.py::test_gwt_43_1_market_subscribe_succeeded
1 failed in 2.25s
```

绿：

```
$ uv run pytest -x -q backend/tests/test_t32_market_events.py backend/tests/test_product_events.py --tb=short
.................................                                        [100%]
33 passed in 10.16s
pytest_exit:0

$ uv run pytest -x -q backend/tests/test_t25_subscribe.py backend/tests/test_t26_installs.py backend/tests/test_t28_listing.py backend/tests/test_t29_sources.py backend/tests/test_t22_list_filters.py --tb=short
..............................................................           [100%]
62 passed in 11.99s
overlap_exit:0

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

$ npm test --prefix frontend/admin -- --watchAll=false --runInBand --testPathPattern='ProductEvents.test|App.test|usePermission.test'
Test Suites: 3 passed, 3 total
Tests:       14 passed, 14 total
admin_jest_exit:0

$ npm test --prefix frontend/official -- --watchAll=false --runInBand --testPathPattern='Capabilities.test|CapabilityDetail.test'
Test Suites: 2 passed, 2 total
Tests:       23 passed, 23 total
official_jest_exit:0

$ npm run build --prefix frontend/admin
> admin@0.1.0 build
> react-scripts build
Creating an optimized production build...
Compiled with warnings.
The build folder is ready to be deployed.
admin_build_exit:0

$ npm run build --prefix frontend/official
> official@0.1.0 build
> react-scripts build
Creating an optimized production build...
Compiled successfully.
The build folder is ready to be deployed.
official_build_exit:0

$ bash /Users/xuyun/.zcode/local-plugins/sdlc-workflow/scripts/check-sdlc.sh --require --hat implement /Users/xuyun/auto_agents/.sdlc/feat-four-pillars-v2
✓ 泳道声明
----------------------------------------
✓ SDLC 工件合规通过
sdlc_exit:0
```

`llm_gw_grep_exit:1` = 零命中。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-43.1 订阅成功含宿主与企业 | `test_gwt_43_1_market_subscribe_succeeded` | ✅ |
| GWT-43.2 预告拒订 reason=`coming_soon` | `test_gwt_43_2_coming_soon_rejected_reason` | ✅ |
| GWT-43.3 租户无入口；直打同形 404 | `test_gwt_43_3_tenant_query_is_404_shell`；admin `App.test` `/product-events`；`usePermission.test` 无「市场分析/产品事实」；official Capabilities/Detail 无分析面 | ✅ |
| GWT-43.4 `market_list_viewed` 含筛选 | `test_gwt_43_4_market_list_viewed` | ✅ |
| GWT-43.5 `market_search_submitted` 含 q 与 result_count | `test_gwt_43_5_market_search_submitted` | ✅ |
| GWT-43.6 `market_detail_viewed` 含类型与上架态 | `test_gwt_43_6_market_detail_viewed` | ✅ |
| GWT-43.7 `market_uninstalled` 含宿主 | `test_gwt_43_7_market_uninstalled` | ✅ |
| GWT-43.8 `market_listing_changed` 旧态与新态 | `test_gwt_43_8_market_listing_changed` | ✅ |
| GWT-43.9 `market_source_sync_completed` 成功数失败数 | `test_gwt_43_9_market_source_sync_completed` | ✅ |
| GWT-43.10 按企业 A 过滤不见 B | `test_gwt_43_10_filter_by_tenant_a` | ✅ |
| 投递失败不挡订阅 200 | `test_emit_failure_does_not_block_subscribe` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | 独立短会话：订阅 200 与事件写入分离 | ✅ `test_emit_failure_does_not_block_subscribe` |
| 幂等 | ➖ N/A（合同禁止精确一次键，允许重复） | ➖ |
| 并发写 | ➖ N/A（追加表无条件更新） | ➖ |
| 外部依赖失败 | 同上，mock `_persist_event` 抛错仍 HTTP 200 | ✅ |

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-08 | 蓝图事件仅超管可按发生时间查询 | GET `/product-events` 超管 200；租户 404 `HTTP_404`；导航无入口 | pytest + admin jest |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 查询仍 `GET /api/v1/product-events`。43.2 `props.reason` **等于** `coming_soon`。租户直打 404 信封 `HTTP_404`；壳「页面不存在或已被移除」。公开 list 有 q 时同时落 `market_list_viewed` + `market_search_submitted`。 |
| `/frontend` | 官网列表/搜索/详情走既有 public API，由后端投递；无需扩展 `POST /public/events`（禁止租户伪造订阅成功）。超管仍在 `/platform-ops`「产品事实」Tab 按事件名过滤。 |
| `/architect` | 无新错误码。拒绝原因映射：`MARKET_COMING_SOON`→`coming_soon` / `MARKET_NOT_FOUND`→`unlisted` / `MARKET_HOST_INCOMPAT`→`host_incompat` / `MARKET_READONLY_ROLE`→`readonly`。`license`/`auth` 未在本票接线（T-31 许可闸并行）。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（不是「大部分通过」）
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`（吞异常有 warning）
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」
- [x] 条件更新的 `rows == 0` 已处理
- [x] 外部依赖四件套齐全（超时/重试/降级/幂等前提）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 票状态已更新为 done
