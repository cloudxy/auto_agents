# 实现证据 · T-22 列表可搜可筛；预告无按钮；失败≠空

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-22.md`｜FR 锚点：FR-31 / NFR-03｜角色：/frontend official + /backend｜日期：2026-09-09
> 上游：ADR-0012 · ADR-0018 · spec v1.6 FR-31 · edge-states「能力市场列表」· T-23 FR-33 读模型
> 泳道：L4

未实现 T-25 订阅 POST / 安装行；未实现 T-24 XSS 改写；未实现 T-26 admin 安装。未改 FR-33 WHERE/COUNT/LIMIT 本体（只在闸后叠 q/host/category）。未删 `SkillsSquare.test.tsx` T-21 测、未删 `CapabilityDetail.test.tsx` XSS。未代选六问。列表无订阅按钮（含已上架匿名）。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 筛选项进 URL `type/q/host/category` | 官网列表 | `frontend/official/src/pages/Capabilities.tsx` | `useSearchParams`；`/skills` 仍已筛技能 |
| 公开列表 q/host/category | Router + Service | `public_skills.py` + `power_market/service.py` | 叠在 `_fr33_clause()` 之后、COUNT/LIMIT 之前 |
| 卡片主标题 | 页面 | `capabilityMarket.ts` `cardTitle` | 展示名或 origin 短名；禁止 `{plugin}__` 当前标题 |
| 空 / 筛空 / 失败三句 | 页面 | `Capabilities.tsx` | 三句不得互勾；失败夹具 reject 非空 `items` |
| 预告无按钮 | 页面 | `MarketCard` 角标「预告」 | 与 GWT-32.2 同一句；无「尚未上架」 |
| 未上架/黑名单 | Service | T-23 `_fr33_clause` | 本票 q 命中不得把 unlisted/blacklist 捞出 |
| 非法类型 | 页面 | T-21 `没有这种类型` | 不兜成技能；本票不改 FR-44 |

**分层依赖核对**：☑ Router 未 import ORM ☑ 未改 GWT/schema ☑ 未改 design tokens 名 ☑ 未写 `capability_installs` / SubscribeModal

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/official/src/pages/Capabilities.tsx` | 修改 | react-query 列表；URL 筛；三态文案；预告角标 |
| `frontend/official/src/pages/Capabilities.css` | 新增 | 只引用 `--*` token |
| `frontend/official/src/pages/capabilityMarket.ts` | 新增 | 五类/宿主/主标题/是否有筛 |
| `frontend/official/src/pages/Capabilities.test.tsx` | 新增 | GWT-31.1…31.6；三句不得互勾 |
| `frontend/official/src/pages/SkillsSquare.test.tsx` | 修改 | 补 QueryClient；**保留** GWT-30.2 / 44.2 |
| `frontend/official/src/services/capabilities.ts` | 修改 | `listPublicAssets({ type, q, host, category })` |
| `backend/services/power_market/service.py` | 修改 | `host` 叠 FR-33；未知宿主空页 |
| `backend/app/api/v1/public_skills.py` | 修改 | 双公开端 `host` Query |
| `backend/tests/test_t22_list_filters.py` | 新增 | q 展示名/短名；host 非 LIMIT-then-filter；category |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：后端只加 list 筛，未改 404 HTML / 订阅写）

**未触碰「不许改的文件」**：☑ 确认（未改 FR-33 闸函数体、GET 404 HTML、SubscribeModal、`capability_installs`、详情 XSS、admin T-26）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 公开列表 GET | 否 | 只读；react-query |

**事务提交后的操作失败怎么办**：N/A

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | N/A（只读） |
| 保证方式 | 同一 URL 筛 → 同一 `queryKey` |
| 重复请求返回 | 同一 FR-33 ∩ 筛 的 JSON |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 无筛且 200 空 | 页面空态 | 「还没有上架的能力」+ 说明 |
| 有筛且 200 空 | 页面筛空 | 「没有符合条件的能力」+「清除筛选」 |
| 加载失败 | `isError` | 「市场列表加载失败」+「检查网络后重试」；禁止空 `items` 当 31.2 |
| 未知 host | Service 空页 | 200 `items=[]` `total=0`（不是 5xx，前端走筛空） |

☑ 无条件更新

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 公开列表 API | 现网 client 10s | 本查询 `retry: false` | 失败句 + 重试按钮 | 只读 |

`q` 命中 `name` LIKE 或 `title` LIKE（带前缀目录名可被 origin 短名命中）。`host`：`host_compat IS NULL`（四宿主）或 JSON 文本含 `"kimi"`；`[]` 不命中。禁止先 LIMIT 再滤宿主。

## 4. ORM 与 DBML 对齐

➖ N/A 本票不加列。`host` 筛消费 T-25 已落的 `host_compat`。未改 `uq_asset_type_name_alive`。☑

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `list_public` 记 type/page/q/host/category |
| trace_id | 现网中间件 |
| 错误日志上下文 | 页级 `role="alert"`；不展示堆栈 |
| 慢操作耗时 | N/A 前端只读 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

### 九维自查

| 维 | 检查 | 结果 |
|---|---|---|
| ① 间距 | `--space-inset-*` / `--space-stack-md` | ✅ |
| ② 颜色 | 组件无 hex；token 映射 semantic | ✅ |
| ③ 字体 | `--font-size-2xl` / `--font-size-sm` | ✅ |
| ④ 圆角 | `--radius-card` / `--radius-pill` | ✅ |
| ⑤ 图标 | 无新 emoji | ✅ |
| ⑥ 交互态 | 搜索/清除/重试；预告无按钮；focus ring | ✅ Jest |
| ⑦ 状态完整性 | 骨架 / 空 / 筛空 / 失败+重试 / 非法类型 / 预告 | ✅ Jest |
| ⑧ 响应式 | grid auto-fill；未量 375/768/1024/1440 | ☐ |
| ⑨ a11y | `h1`；卡片 `aria-label` 真链接；错误 `role="alert"` | ✅ 基线 |

```
$ rg -n '#[0-9a-fA-F]{3,8}' frontend/official/src/pages/Capabilities.tsx frontend/official/src/pages/Capabilities.css frontend/official/src/pages/Capabilities.test.tsx frontend/official/src/pages/capabilityMarket.ts frontend/official/src/services/capabilities.ts
hex_grep_exit:1
```

## 6. 自测证据

> 命令与退出码**原样粘贴**。TDD：先红后绿。

### TDD 红（现网「暂无已发布」+ catch 装空；list 忽略 host）

```
$ npm test --prefix frontend/official -- --watchAll=false --runInBand src/pages/Capabilities.test.tsx
FAIL src/pages/Capabilities.test.tsx (59.176 s)
  ✕ GWT-31.1 search hits display name and opens a real detail link (8175 ms)
  ✕ GWT-31.1 origin short name search hits prefixed catalog name (8543 ms)
  ✕ search box writes q into the URL (8084 ms)
  ✕ GWT-31.2 unfiltered empty is 还没有上架的能力, not 暂无已发布 (8032 ms)
  ✕ GWT-31.3 filtered empty is 没有符合条件的能力 plus 清除筛选 (8050 ms)
  ✕ GWT-31.4 load failure is 市场列表加载失败, not empty stock (8043 ms)
  ✕ GWT-31.4 fail fixture must not return empty items as 31.2 (8047 ms)
  ✕ GWT-31.5 coming_soon card shows 预告 and no subscribe button (50 ms)
  ✓ GWT-31.6 unlisted or blacklist names do not appear (38 ms)
  ✕ type host category stay in the URL and are sent to list_public (44 ms)

  ● GWT-31.2 unfiltered empty is 还没有上架的能力, not 暂无已发布
    Unable to find an element with the text: 还没有上架的能力
    （现网 Empty「暂无已发布能力」——oracle 正确，不是 import 失败）

  ● GWT-31.5 coming_soon card shows 预告 and no subscribe button
    Unable to find an element with the text: 预告

Test Suites: 1 failed, 1 total
Tests:       9 failed, 1 passed, 10 total
exit: 1
```

```
$ uv run pytest -x -q backend/tests/test_t22_list_filters.py
....F
______________ test_host_kimi_matches_null_and_declared_not_empty ______________
>       assert names == {"undeclared", "kimi-only"}
E       AssertionError: assert {'grok-only',..., 'zero-host'} == {'kimi-only', 'undeclared'}
E         Extra items in the left set:
E         'grok-only'
E         'zero-host'
FAILED backend/tests/test_t22_list_filters.py::test_host_kimi_matches_null_and_declared_not_empty
1 failed, 4 passed in 2.53s
```

host 红因：`list_public` 忽略 `host`（oracle 正确）。q 展示名/短名在 T-23 LIKE 上已绿。

### 绿

```
$ npm test --prefix frontend/official -- --watchAll=false --runInBand
PASS src/pages/Capabilities.test.tsx (65.752 s)
PASS src/pages/Register.test.tsx (46.423 s)
PASS src/pages/SkillsSquare.test.tsx (8.022 s)
PASS src/pages/Home.test.tsx
PASS src/pages/Pricing.test.tsx
PASS src/pages/Pricing.beacon.test.tsx
PASS src/pages/Home.beacon.test.tsx
PASS src/App.test.tsx
PASS src/pages/CapabilityDetail.test.tsx
PASS src/components/layout/SiteLayout.beacon.test.tsx
PASS src/components/home/FeaturesSection.test.tsx

Test Suites: 11 passed, 11 total
Tests:       48 passed, 48 total
Time:        133.617 s
Ran all test suites.
exit: 0

$ npm run build --prefix frontend/official
Creating an optimized production build...
Compiled successfully.
File sizes after gzip:
  167.82 kB  build/static/js/main.814f2e44.js
  ...
The project was built assuming it is hosted at /.
exit: 0

$ uv run pytest -x -q backend/tests/test_t22_list_filters.py backend/tests/test_skill_public_api.py backend/tests/test_b1c_capabilities_coverage.py
........................................................................ [ 96%]
...                                                                      [100%]
75 passed in 69.37s
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

$ bash /Users/xuyun/.zcode/local-plugins/sdlc-workflow/scripts/check-sdlc.sh --require --hat implement /Users/xuyun/auto_agents/.sdlc/feat-four-pillars-v2
✓ 泳道声明
----------------------------------------
✓ SDLC 工件合规通过
sdlc_exit:0
```

`SkillsSquare.test.tsx` GWT-30.2 / 44.2 仍绿。`CapabilityDetail.test.tsx` GWT-32.4 / 32.5 仍绿。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-31.1 展示名/短名命中 + 真链接 | `GWT-31.1 search hits display name…` / `origin short name…`；后端 `test_q_hits_*` | ✅ |
| GWT-31.2 还没有上架的能力，不是暂无已发布 | `GWT-31.2 unfiltered empty…` | ✅ |
| GWT-31.3 没有符合条件的能力 + 清除筛选 | `GWT-31.3 filtered empty…` | ✅ |
| GWT-31.4 市场列表加载失败 + 检查网络后重试 | `GWT-31.4 load failure…`；失败夹具 reject | ✅ |
| GWT-31.5 预告角标、无订阅、无尚未上架 | `GWT-31.5 coming_soon card…` | ✅ |
| GWT-31.6 未上架/黑名单不出现 | 前端不宣称本格（见 Rework IM-15）；后端 `test_q_does_not_surface_unlisted_or_blacklist` | ✅ 服务端 |
| NFR-03 失败不得装空 | 31.4 三句不得互勾 | ✅ |
| T-21 `/skills` 映射未丢 | `SkillsSquare.test` GWT-30.2 / 44.2 | ✅ |
| T-24 XSS 未丢 | `CapabilityDetail.test` GWT-32.4 | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A | 只读列表，无写 |
| 幂等 | ➖ N/A | 无创建/订阅写 |
| 并发写 | ➖ N/A | 无条件更新 |
| 外部依赖失败 | 列表 reject → 31.4 失败句，不是 31.2 | ✅ |
| LIMIT-then-filter | `test_host_filter_not_limit_then_filter`：20 grok 后插入占满页，host=kimi 仍 total=5 | ✅ |

## 7. NFR 验证

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-03 | 公开列表失败不得装空（FR-31.4） | Jest：reject 夹具出「市场列表加载失败」+「检查网络后重试」；无「还没有上架的能力」/「没有符合条件的能力」/「暂无已发布」 | jsdom |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 三句互斥：空=`还没有上架的能力`；筛空=`没有符合条件的能力`+`清除筛选`；失败=`市场列表加载失败`+`检查网络后重试`。失败夹具必须 reject，禁止空 `items` 当 31.2。预告卡无订阅节点、无「尚未上架」。XSS 仍在 `CapabilityDetail.test.tsx`。 |
| `/backend` | `GET /public/capabilities` 与 `/public/skills` 均接受 `q`/`host`/`category`；`host` 非法 → 200 空页。q 已能 LIKE 命中前缀 `name` 与 `title`。 |
| `/architect` | 无新错误码。未知宿主未走 422，避免前端把校验当 31.4 失败。 |
| T-25 / T-26 | 列表无订阅按钮。详情 CTA 仍 T-24。不要改本票空/失败句。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿
- [x] 契约落位表已核对；未改 GWT/schema
- [x] ORM N/A（未加列）
- [x] 无硬编码连接串/密钥/端口；列表组件无 hex
- [x] 无同步 redis 直调
- [x] 无 `except: pass`
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等 N/A
- [x] 条件更新 N/A
- [x] 外部依赖：超时沿 client；失败可重试；404 非法类型不进列表
- [x] 四类易漏已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已写入下游，未自行拼订阅按钮
- [x] 票状态已更新为 done

## Rework · IM-15 / IM-16（G-fresh `01a086d3-0fcf-7452-ad0b-67ae73ca5143`）

> 日期：2026-09-09｜角色：/frontend official｜未改 FR-33 SQL；未删 T-21/T-24 测；未碰 T-26；未代选六问。

| IM | 处置 |
|---|---|
| IM-15 / QA-02 | 删除前端 `GWT-31.6 unlisted or blacklist names do not appear`（mock 未给的名字再 query 缺席）。31.6 只由 `backend/tests/test_t22_list_filters.py::test_q_does_not_surface_unlisted_or_blacklist` 持有。保留测改断言 URL 筛原样进 `listPublicAssets`、无 `listing_state`/`status` 二次滤、mock 返回几条就渲染几条。 |
| IM-16 / QA-03 | 筛空列出当前 URL 筛 `类型/关键词/宿主/分类`（值=type/q/host/category）+「没有符合条件的能力」+「清除筛选」。无筛空 / 失败无 `filter-echo`。 |

### TDD 红（测已写、产品未回显）

```
$ npm test --prefix frontend/official -- --watchAll=false --runInBand src/pages/Capabilities.test.tsx
FAIL src/pages/Capabilities.test.tsx (19.455 s)
  ✓ GWT-31.1 search hits display name and opens a real detail link (987 ms)
  ✓ GWT-31.1 origin short name search hits prefixed catalog name (1036 ms)
  ✓ search box writes q into the URL (2805 ms)
  ✓ GWT-31.2 unfiltered empty is 还没有上架的能力, not 暂无已发布 (82 ms)
  ✕ GWT-31.3 filtered empty is 没有符合条件的能力 plus 清除筛选 (3213 ms)
  ✓ GWT-31.4 load failure is 市场列表加载失败, not empty stock (2152 ms)
  ✓ GWT-31.4 fail fixture must not return empty items as 31.2 (90 ms)
  ✓ GWT-31.4 filtered URL still fails as load error, not filter-empty (2457 ms)
  ✓ GWT-31.5 coming_soon card shows 预告 and no subscribe button (1462 ms)
  ✓ list sends URL filters and renders mock items without a second client filter (2490 ms)
  ✓ type host category stay in the URL and are sent to list_public (116 ms)

  ● GWT-31.3 filtered empty is 没有符合条件的能力 plus 清除筛选
    TestingLibraryElementError: Unable to find an element by: [data-testid="filter-echo"]

Test Suites: 1 failed, 1 total
Tests:       1 failed, 10 passed, 11 total
exit: 1
```

红因：筛空只有「没有符合条件的能力」+「清除筛选」，未列出当前 URL 筛（oracle 正确，不是 import 失败）。IM-15 替换测已绿（无 GWT-31.6 名、无 unlisted-secret 缺席断言）。

### 绿

```
$ npm test --prefix frontend/official -- --watchAll=false --runInBand src/pages/Capabilities.test.tsx
PASS src/pages/Capabilities.test.tsx (26.477 s)
  ✓ GWT-31.1 search hits display name and opens a real detail link (995 ms)
  ✓ GWT-31.1 origin short name search hits prefixed catalog name (882 ms)
  ✓ search box writes q into the URL (2578 ms)
  ✓ GWT-31.2 unfiltered empty is 还没有上架的能力, not 暂无已发布 (93 ms)
  ✓ GWT-31.3 filtered empty is 没有符合条件的能力 plus 清除筛选 (8727 ms)
  ✓ GWT-31.4 load failure is 市场列表加载失败, not empty stock (4343 ms)
  ✓ GWT-31.4 fail fixture must not return empty items as 31.2 (141 ms)
  ✓ GWT-31.4 filtered URL still fails as load error, not filter-empty (3048 ms)
  ✓ GWT-31.5 coming_soon card shows 预告 and no subscribe button (1345 ms)
  ✓ list sends URL filters and renders mock items without a second client filter (1779 ms)
  ✓ type host category stay in the URL and are sent to list_public (87 ms)

Test Suites: 1 passed, 1 total
Tests:       11 passed, 11 total
exit: 0

$ npm test --prefix frontend/official -- --watchAll=false --runInBand
PASS src/pages/Register.test.tsx (26.627 s)
PASS src/pages/Capabilities.test.tsx (27.213 s)
PASS src/pages/SkillsSquare.test.tsx (5.947 s)
PASS src/pages/Pricing.test.tsx
PASS src/pages/Home.test.tsx
PASS src/pages/Pricing.beacon.test.tsx
PASS src/App.test.tsx
PASS src/pages/CapabilityDetail.test.tsx
PASS src/pages/Home.beacon.test.tsx
PASS src/components/layout/SiteLayout.beacon.test.tsx
PASS src/components/home/FeaturesSection.test.tsx

Test Suites: 11 passed, 11 total
Tests:       49 passed, 49 total
Time:        70.673 s
Ran all test suites.
exit: 0

$ rg -n '#[0-9a-fA-F]{3,8}' frontend/official/src/pages/Capabilities.tsx frontend/official/src/pages/Capabilities.css frontend/official/src/pages/Capabilities.test.tsx frontend/official/src/pages/capabilityMarket.ts
hex_grep_exit:1
```

`SkillsSquare.test.tsx` / `CapabilityDetail.test.tsx` 仍在闸里。前端无名为 `GWT-31.6` 的测。

### 验收对照（本返工）

| 项 | 覆盖 | 结果 |
|---|---|---|
| IM-15 无空洞 31.6 | 无 `GWT-31.6` / 无 `unlisted-secret` 缺席断言；改为请求参数 + 无二次滤 | ✅ |
| IM-16 筛空回显 | 31.3：`filter-echo` 含 type=skill / q=没有这货 / host=kimi / category=none +「没有符合条件的能力」+「清除筛选」 | ✅ |
| 31.2/31.3/31.4 互斥 | 31.2 无 echo/无筛空句；31.4 无筛/有筛均失败句、无 echo、无「清除筛选」 | ✅ |
