# 实现证据 · T-14 公开列表页大小≤20 + 夹具第 21 张 + 翻页事件

> 票：contract §11 T-14（FR-81 + FR-92.5）｜FR 锚点：FR-81（GWT-81.1…81.4）、FR-92（GWT-92.5）｜角色：official + /backend｜日期：2026-09-11
> 依据：contract §7.5 公开商店 + §7.8 分页 + §2.3 依赖图（Power Market ──► 产品事件 `market_list_paged`）；spec FR-81 / FR-92.5；NFR-02 第一页最多 20（NFR-01 计时归 verify）
> 范围闸：不动种子谓词（T-13 已落，含 T-19 顺修的 coalesce）；不为翻页造商品模型（≥21 用 `fr33_asset` 夹具资产）；首页精选非翻页列表，按 ≤20 精选承接，不扩假数据。

## 1. 契约落位表（实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 公开 `PAGE_SIZE_MAX=20` | 读模型常量 | `backend/services/power_market/types.py` | 50→20；全仓消费方仅公开两端 + `PowerMarketService._page_size`（读码确认），无管理端分闸需求 |
| `page/page_size/total/has_more` 返回形态 | 读模型（既有） | `backend/services/power_market/service.py::list_public` | 零改动，形态既有 |
| 翻页事件名 + 事件投递 | 产品事件叶 | `backend/services/market_events.py` | `MARKET_LIST_PAGED="market_list_paged"` 入 `MARKET_EVENT_NAMES`；`emit_market_list_paged(page, result_count, anonymous_id)`；`emit_market_event` 透传 `anonymous_id` |
| 翻页动作挂载（第 2 页起） | Router | `backend/app/api/v1/public_skills.py::_emit_paged_event` | 两公开端同挂；`page>=2` 才上报；失败不挡列表（`emit_product_event` 既有吞异常语义） |
| `anonymous_id` 入口 | Router Query 参数 | `public_skills.py`（两列表端点） | `Query(None, max_length=64)`，与 product_events 表列宽一致 |
| 事件落库（anonymous_id 列、无 tenant_id） | 既有持久层 | `product_event_service.emit_product_event` | 零改动；访客 `tenant_id=None`、`anonymous_id` 走列、`page/result_count` 走 props |
| 翻页控件（总件数 + 上一页/下一页，无假下一页） | official 组件 | `frontend/official/src/pages/Capabilities.tsx` | `MarketPager`：`total<=0` 不渲染（81.3）；`has_more!==true` 不渲染下一页（81.2）；`page` 进 URL，筛选变化回第 1 页 |
| 翻页请求带浏览会话身份 | official service | `frontend/official/src/services/capabilities.ts` | `page>=2` 时附 `anonymous_id=ensureAnonymousId()`（beacon 既有 localStorage 身份）；第 1 页不带 |
| 首页精选对齐 MAX=20 | official 组件 | `frontend/official/src/components/home/SkillsSection.tsx` | `page_size: 50 → 20`（精选取前 20 挑 ≤6 张，非翻页列表不扩假数据） |

**双公开端（PIT-5 口径）**：`/api/v1/public/skills` 与 `/api/v1/public/capabilities` 同 `_emit_paged_event` + 同 `le=PAGE_SIZE_MAX`，测试两端各一份。

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import（arch.sh 全绿）

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/power_market/types.py` | 修改 | `PAGE_SIZE_MAX = 50 → 20`（+注释 FR-81） |
| `backend/services/market_events.py` | 修改 | `MARKET_LIST_PAGED` 常量/清单 + `emit_market_list_paged` + `emit_market_event` 透传 anonymous_id |
| `backend/app/api/v1/public_skills.py` | 修改 | 两列表端点 +`anonymous_id` Query；+`_emit_paged_event`（第 2 页起） |
| `backend/tests/test_t14_public_paging.py` | 新增 | 9 测试：81.1×3（含 MAX=20 闸）、81.2、81.3、81.4、92.5×3 |
| `backend/tests/test_b1c_capabilities_coverage.py` | 修改 | 金标 `page_size_max_50` → `page_size_max_20`（21→422、20→200；PIT-2 同 PR） |
| `backend/tests/test_t13_public_seed_filter.py` | 修改 | 精选形态测试 `page_size 50 → 20`（本票改了精选调用形态，同 PR 更新） |
| `frontend/official/src/services/capabilities.ts` | 修改 | 返回类型补 `total/page/page_size/has_more`；`page>=2` 附 anonymous_id；page 始终显式传递 |
| `frontend/official/src/pages/Capabilities.tsx` | 修改 | +`MarketPager`；`page` 进 URL；筛选变化回第 1 页；深链越末页不谎称「还没有上架的能力」 |
| `frontend/official/src/pages/Capabilities.css` | 修改 | +翻页控件样式 |
| `frontend/official/src/pages/Capabilities.test.tsx` | 修改 | +4 翻页测试（81.1/81.2/81.3/92.5+重置）；既有精确调用形态测试 +`page:1` |
| `frontend/official/src/services/capabilities.test.ts` | 新增 | 2 测试：page≥2 带 anonymous_id / page 1 不带 |
| `frontend/official/src/components/home/SkillsSection.tsx` | 修改 | 精选 `page_size 50 → 20` |

**与票里「会改哪些文件」对照**（票表 T-14 + stale 票存档）：types.py / public_skills.py / Capabilities.tsx / market_events.py / 夹具 ✓；偏差 2 处（均小于票面）：① 精选对齐只动 `SkillsSection.tsx` 调用形态，`Home.tsx` 零改动（精选数据源即 SkillsSection，票面写「对照」）；② `product_event_service.py` 零改动——既有 `emit_product_event` 已带 `anonymous_id` 形参，无需扩。
**未触碰**：`power_market/service.py`（种子谓词/查询闸，T-13/T-19 面）、`listing.py`（上架状态机）、ORM/迁移（无 DDL）、商店模型（未新建）。**未 git commit**（票禁令）。

## 3. 关键实现决策

- **事件挂后端列表请求，不挂前端 beacon**：与既有市场事件族（`market_list_viewed` 等）同一投递路径（服务端 `market_events` → `product_events`），契合 contract §2.3 依赖图（Power Market ──► 产品事件）；「失败不挡列表」由 `emit_product_event` 既有吞异常语义直接满足。前端只负责把浏览会话身份 `anonymous_id` 作为查询参数随翻页请求带上来（第 1 页不带——最小数据面，列表浏览不因此可关联）。
- **`result_count` = 该页实得件数**：GWT-92.5「第 2 页渲染」时第 2 页的条数（21 张夹具翻页时 = 1），取自同一响应的 `items`，不重复数库。
- **无假下一页是「不渲染」不是「禁用」**：GWT-81.2 字面是「无假控件」，`has_more!==true` 时下一页按钮整个不渲染；上一页仅 `page>1` 渲染。总件数（`共 N 件`）与页码可见（GWT-81.1「页上能看见总件数与下一页」）。
- **0 件零翻页数字（81.3）**：`total<=0` 时 pager 整体不渲染——不出现「共 0 件」式谎称有货的数字；空态句走既有「还没有上架的能力」。
- **深链越末页诚实化**：`items` 空而 `total>0`（直打 `?page=99`）时不再落「还没有上架的能力」空态（那会谎称无货），渲染「没有更多了」+ 上一页。
- **筛选变化回第 1 页**：`page` 进 URL；patch type/q/host/category 时删 `page`，翻页视图不会带着第 2 页偏移去命中新筛选的空白页。
- **精选不扩假数据**：公开 MAX 收到 20 后，首页精选请求形态 `page_size 50→20`（精选本就只取 ≤6 张）；按 spawn 指引「精选非翻页列表，允许 ≤20，不扩假数据」。

### 事务/幂等/并发/外部依赖

| 项 | 结论 | 理由 |
|---|---|---|
| 事务 | N/A | 列表纯读；事件走独立短会话（既有 `_persist_event`），不与主路径同事务 |
| 幂等 | N/A | product_events v1 至少一次、允许重复（db-spec：无幂等 UNIQUE），翻页每次第 2 页请求即一次事实 |
| 并发 | N/A | 无写竞争面（事件追加表） |
| 外部依赖 | N/A | 未新增外部调用；事件失败 fail-open（既有语义，系统化 fail-open 测试归 T-22/GWT-92.6） |

## 4. ORM 与 DBML 对齐

N/A——零模型/迁移改动。`market_list_paged` 已在 shape `schema.dbml` §77 事件枚举与 §483（`anonymous_id varchar(64)`「market_list_paged 访客必带」）预留；实现走既有 `product_events` 列，未自行加列。

## 5. 可观测性

- 事件投递入口日志：`emit_market_event` / `emit_market_list_paged` 记 `page`、`result_count`（数字，无敏感数据）；`emit_product_event` 记事件名。
- Router `_emit_paged_event` 不落日志（无新信息；R10 由所调 Service/事件叶入口承担）。
- **日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ anonymous_id 是客户端生成会话标识（非凭证），仅入事件列不入日志。

## 6. 自测证据（原样粘贴）

**红（TDD：实现前。后端 4 项失败均为新 oracle：MAX 仍 50 放行 21、无 market_list_paged 事件；81.2/81.3/81.4 与 81.1 翻页可达性为既有行为钉桩，红绿两态同绿，如实记录）**：

```
$ uv run pytest -q backend/tests/test_t14_public_paging.py
=========================== short test summary info ===========================
FAILED backend/tests/test_t14_public_paging.py::test_gwt_81_1_public_page_size_cap_is_20
FAILED backend/tests/test_t14_public_paging.py::test_gwt_92_5_market_list_paged_emitted_on_page2
FAILED backend/tests/test_t14_public_paging.py::test_gwt_92_5_market_list_paged_capabilities_endpoint
FAILED backend/tests/test_t14_public_paging.py::test_gwt_92_5_admin_query_surface_can_see_event
4 failed, 5 passed in 3.46s
exit: 1
```

**绿（后端实现后）**：

```
$ uv run pytest -q backend/tests/test_t14_public_paging.py
.........                                                                [100%]
9 passed in 3.50s
exit: 0
```

**红（TDD：前端实现前。5 失败：服务层无 anonymous_id、组件无翻页控件/总件数、既有精确调用形态缺 page）**：

```
$ npx jest src/pages/Capabilities.test.tsx src/services/capabilities.test.ts
FAIL src/services/capabilities.test.ts
  ● page 2 list request carries anonymous_id (GWT-92.5)
Tests:       5 failed, 13 passed, 18 total
exit: 1
```

**绿（前端实现后）**：

```
$ npx jest src/pages/Capabilities.test.tsx src/services/capabilities.test.ts
Tests:       18 passed, 18 total
exit: 0
```

**Power Market 域回归（16 个读模型/公开端/事件测试文件，含两份同 PR 金标更新）**：

```
$ uv run pytest -q backend/tests/test_t14_public_paging.py backend/tests/test_t13_public_seed_filter.py backend/tests/test_skill_public_api.py backend/tests/test_b1c_capabilities_coverage.py backend/tests/test_capability_catalog.py backend/tests/test_t22_list_filters.py backend/tests/test_t25_subscribe.py backend/tests/test_t26_installs.py backend/tests/test_t27_references.py backend/tests/test_t28_listing.py backend/tests/test_t29_sources.py backend/tests/test_t30_command_cards.py backend/tests/test_t31_license.py backend/tests/test_t32_market_events.py backend/tests/test_t33_aliases.py backend/tests/test_product_events.py
214 passed in 45.26s
exit: 0
```

**后端全量**：

```
$ uv run pytest -q backend/tests
1449 passed, 37 skipped, 8 warnings in 487.28s (0:08:07)
exit: 0
```

**official 前端全量 jest**：

```
$ npx jest（frontend/official）
Test Suites: 13 passed, 13 total
Tests:       74 passed, 74 total
exit: 0
```

**official 前端构建（成功检查项）**：

```
$ npm run build --prefix frontend/official
Compiled successfully.
exit: 0
```

（构建中间态曾出 1 条 `PAGE_SIZE` 未使用警告，删除该死常量后复建 Compiled successfully；复跑受影响 5 个测试文件 `30 passed, exit 0`。）

**架构红线（成功检查项）**：

```
$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0
```

**Lint（改动后端文件）**：

```
$ uv run ruff check backend/services/power_market/types.py backend/services/market_events.py backend/app/api/v1/public_skills.py backend/tests/test_t14_public_paging.py backend/tests/test_t13_public_seed_filter.py backend/tests/test_b1c_capabilities_coverage.py
All checks passed!
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-81.1 第一页 ≤20、总件数与下一页可见、第 21 张可到且不重复 | 后端 `test_gwt_81_1_public_page_size_cap_is_20`（MAX=20 闸：21/50→422、20→200）+ `test_gwt_81_1_21st_reachable_on_page2_skills` + `..._capabilities`（total=21、首页 20 张、has_more=True、第 2 页 1 张且与首页零交集）；前端 `GWT-81.1 pager shows total and next; page 2 reaches the 21st without overlap`（共 21 件、下一页、第 2 页 21st 张、首页卡不再在屏、末页无下一页） | ✅ |
| GWT-81.2 恰好 20 无假下一页 | 后端 `test_gwt_81_2_exactly_20_no_fake_next_page`（has_more=False、第 2 页空且无下一页）；前端 `GWT-81.2 exactly 20 items has no fake next control`（无下一页按钮） | ✅ |
| GWT-81.3 0 上架空态、无谎称有货的数字 | 后端 `test_gwt_81_3_zero_listed_is_empty_not_failure`（200 + total 0 + items [] + has_more False）；前端 `GWT-81.3 zero stock keeps empty sentence without pager numbers`（空态句在、无「共 N 件」、无 pager） | ✅ |
| GWT-81.4 未上架资产任何页不可见 | 后端 `test_gwt_81_4_unlisted_asset_never_on_any_page`（21 listed + 1 unlisted：total=21 不含、第 1/2 页均无该行） | ✅ |
| GWT-92.5 翻页上报 market_list_paged（page/result_count/anonymous_id，无 tenant_id） | `test_gwt_92_5_market_list_paged_emitted_on_page2`（第 1 页零上报 → 第 2 页 1 行：tenant_id None、anonymous_id、props.page=2、props.result_count=1、列表仍 200）+ `..._capabilities_endpoint`（能力端同口径）+ `..._admin_query_surface_can_see_event`（超管查询面可查）+ 前端服务层 `page 2 list request carries anonymous_id` / `page 1 ... does not` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（纯读路径 + 事件独立短会话，无多步写） |
| 幂等 | — | ➖ N/A（事件至少一次语义，蓝图允许重复） |
| 并发写 | — | ➖ N/A（无写竞争面） |
| 外部依赖失败 | 列表 200 即断言于 92.5 用例内（事件失败被服务层吞） | ✅（系统化 fail-open 验收归 T-22/GWT-92.6） |

## 7. NFR 验证

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-02 | 市场第一页最多 20 张；当且仅当非种子 listed>20 时第 21 张可到 | `PAGE_SIZE_MAX=20` 闸（21/50→422）；21 夹具第 2 页可达 | 本机 TestClient + SQLite（§6） |
| NFR-01 | 公开列表 P95 < 2s | 计时归 verify 阶段（票面指定），本票不造假秒数；既有 `test_nfr01_list_400_listed_p95_under_2s` 随域回归绿 | — |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | ① 夹具即测试数据（`fr33_asset` 行），未造任何商品模型、未动种子；预发验收 ≥21 时需真实 listed 夹具资产。② `anonymous_id` 由前端 localStorage 会话身份携带（第 2 页起）；无前端会话的裸 curl 翻页仍上报事件但 anonymous_id 为空（列可 NULL）——访客「必带」由前端契约满足，抽检时用浏览器路径验。③ MySQL 复核点：分页 OFFSET/COUNT 走既有 FR-33 查询侧闸，方言无新增。 |
| `/frontend` | 后端行为已定：MAX=20（>20 一律 422）；`has_more`/`total` 为唯一翻页真相；精选请求形态已对齐 page_size=20（SkillsSection 本票已改，home 测试无需再动）。 |
| `/architect` | 无契约歧义。一处口径已按契约字面执行：`result_count`=该页实得件数（第 2 页 21 张夹具时=1），非 total。 |
| `/ops`（verify） | NFR-01 计时按票面归 verify；本票不留口头秒数。 |

## 9. 过程记录（共享工作树跨票干扰，非本票缺陷）

第一次全量（`-x`）在 `test_relay_token_usage.py::test_gwt_60_5_gateway_unreachable_same_then_not_quota` 失败——relay/网关泳道文件（`relay_service.py`、`llm_gateway/admin.py` 等）正被并行票编辑（git status 多文件 M）。standalone 复跑该测 `1 passed, exit 0`；随后无 `-x` 全量一次通过（§6：1449 passed, exit 0）。判定：与本票（power_market/public_skills/market_events + official 前端）无关，留档供 qa 复跑参考。

## 10. 交票自检

- [x] 每条验收项（81.1…81.4 × 双端可用面、92.5）有 evidence（命令 + 退出码原样；红绿两态）
- [x] 自测全绿（后端域 214/214、全量 1449 passed exit 0；前端 74/74 + 受影响复跑 30/30；build Compiled successfully；arch 0 违规；ruff 全过）
- [x] 契约落位表已核对，分层无违规（Router 无 ORM；事件经服务层投递）
- [x] ORM 与 DBML 一致（零模型改动；事件名/列早已在 shape 预留）
- [x] 无硬编码连接串/密钥/端口/阈值（PAGE_SIZE_MAX=20 为契约冻结值）
- [x] async 上下文无同步阻塞调用（未新增；限流走既有 `get_async_redis`）
- [x] 无 `except: pass`（事件失败走既有 `logger.warning` 吞异常路径）
- [x] 日志已脱敏（anonymous_id 非凭证且不入日志）
- [x] 事务里无外部调用（无事务）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 未动种子谓词（T-13/T-19 面零触碰）；未造商品模型；首页精选 ≤20 不扩假数据
- [x] 未 git commit（票禁令）
