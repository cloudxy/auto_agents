# 实现证据 · T-24 详情正文纯文本；迁 XSS 合同；出处不泄漏未上架父插件

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-24.md`｜FR 锚点：FR-32.4 / FR-32.5 / NFR-04｜角色：/frontend official｜日期：2026-09-09
> 上游：ADR-0018 · spec v1.6 FR-32 · edge-states「能力市场详情」· T-23 详情 JSON
> 泳道：L4

未实现 T-25 订阅 POST / 安装行；未实现 T-22 列表搜索筛 URL；未改 backend / Alembic / power_market / public_skills / admin。未删 `SkillsSquare.test.tsx` T-21 映射测。未代选六问。无 enable-host。无礼包句。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径 `/capabilities/:type/:slug` | 官网路由 | `frontend/official/src/App.tsx` | lazy 详情；未上架 404 走 `<NotFound>` |
| 详情 GET | service | `frontend/official/src/services/capabilities.ts` `getPublicAsset` | `GET /public/capabilities/{type}/{name}` |
| 正文纯文本（GWT-32.4） | 页面 | `CapabilityDetail.tsx` `<pre data-testid="skill-md">` | React 文本节点；禁 markdown / innerHTML |
| 出处链接闸（GWT-32.5） | 页面 | `originStoreHref` 仅消费 `origin.href` | 无 href 则纯文本；不从 name 拼商店 path |
| 未上架/黑名单 | 页面 | HTTP 404 → 官网 404 句 | 不是空详情、无「已下架」 |
| 错误/离线 | 页面 | 失败句 + 重试；离线专用句 | 失败 ≠ 空 |
| 预告 / 订阅 CTA | 页面 | 预告无按钮；已上架「登录后订阅」 | `{REACT_APP_ADMIN_URL}/login?subscribeType&subscribeName`；未设则隐藏；不 POST（T-25） |

**分层依赖核对**：☑ 未改 Router/ORM ☑ 未发明 schema ☑ 未改 GWT ☑ 未改 design tokens 名（只在 `tokens.css` 映射 semantic）

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/official/src/pages/CapabilityDetail.tsx` | 新增 | 详情：骨架 / 404 / 错误 / 纯文本正文 / 出处 |
| `frontend/official/src/pages/CapabilityDetail.css` | 新增 | 只引用 `--*` token |
| `frontend/official/src/pages/CapabilityDetail.test.tsx` | 新增 | GWT-32.4 XSS 迁入；GWT-32.5 出处 |
| `frontend/official/src/services/capabilities.ts` | 修改 | `getPublicAsset` + 详情类型 |
| `frontend/official/src/App.tsx` | 修改 | `/capabilities/:type/:slug` |
| `frontend/official/src/pages/Capabilities.tsx` | 修改 | 卡片真链接进详情（仍单一「能力市场」） |
| `frontend/official/src/tokens.css` | 修改 | 详情 semantic 映射（hex 只在此文件） |
| `frontend/official/src/pages/SkillsSquare.test.tsx` | 未改 | 保留 GWT-30.2 / 44.2 |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：卡片加 Link 以便打开详情；未改 backend）

**未触碰「不许改的文件」**：☑ 确认（backend / admin / 列表筛 URL / 订阅 POST / FR-33 SQL / LiteLLM）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 公开详情 GET | 否 | 只读；react-query |

**事务提交后的操作失败怎么办**：N/A

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | N/A（只读） |
| 保证方式 | N/A |
| 重复请求返回 | 同一详情 JSON |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 详情 miss | HTTP 404 | 官网 404 句，不是空详情 |

☑ 无条件更新

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 公开详情 API | 现网 client 10s | 本查询 `retry: false`（404 不重试） | 错误句 + 重试按钮 | 只读 |

### 出处字段（T-23 实装 vs 本票渲染）

T-23 详情 JSON 有 `skill_md` / `includes` / `license` / `hosts` / `source_author` / `source_url` / `listing_state` / `subscribable`。盘上 **无** `origin.href`。本票：仅当 `origin.href` 以 `/capabilities/` 开头时渲染 `<Link>`；否则 `origin.title|name` 或 `source_author` 纯文本。禁止用父插件 name 拼商店 path。

## 4. ORM 与 DBML 对齐

➖ N/A 本票不改库。未自行加字段/改类型。☑

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | 公开只读；无新 logger |
| trace_id | 现网信封；错误页不展示堆栈 |
| 错误日志上下文 | 页级 `role="alert"` |
| 慢操作耗时 | N/A 前端只读 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

### 九维自查

| 维 | 检查 | 结果 |
|---|---|---|
| ① 间距 | `--space-inset-*` / `--space-stack-md` | ✅ |
| ② 颜色 | 组件无 hex；token 映射 semantic | ✅ |
| ③ 字体 | `--font-mono` / `--font-size-*` | ✅ |
| ④ 圆角 | `--radius-card` / `--radius-pill` | ✅ |
| ⑤ 图标 | 无新 emoji | ✅ |
| ⑥ 交互态 | 预告无按钮；离线订阅 disabled；focus ring | ✅ Jest |
| ⑦ 状态完整性 | 骨架 / 404 / 错误+重试 / 离线句 / XSS 文本 / 出处纯文本 | ✅ Jest |
| ⑧ 响应式 | 预 overflow 滚动；未量 375/768/1024/1440 | ☐ |
| ⑨ a11y | `article`/`h1`；`pre` tabIndex；错误 `role="alert"` | ✅ 基线 |

```
$ rg -n '#[0-9a-fA-F]{3,8}' frontend/official/src/pages/CapabilityDetail.tsx frontend/official/src/pages/CapabilityDetail.css frontend/official/src/pages/CapabilityDetail.test.tsx frontend/official/src/services/capabilities.ts
hex_grep_exit:1
```

## 6. 自测证据

> 命令与退出码**原样粘贴**。TDD：先红后绿。

### TDD 红（stub `<pre data-testid="skill-md" />`，正文空）

```
$ npm test --prefix frontend/official -- --watchAll=false src/pages/CapabilityDetail.test.tsx
FAIL src/pages/CapabilityDetail.test.tsx (56.834 s)
  ✕ GWT-32.4 skill body is text: script source visible, no script/img nodes (23 ms)
  ✕ GWT-32.5 unlisted parent origin is plain text, not a store link (8007 ms)
  ✕ listed parent origin renders a store link when href is present (8006 ms)
  ✕ unlisted GET shows official 404 copy, not empty detail or 已下架 (8007 ms)
  ✕ load failure shows retry copy, not empty success (8010 ms)
  ✕ offline failure uses offline copy (8006 ms)
  ✕ coming_soon has preview mark, no subscribe, no gift-pack or enable-host copy (8004 ms)
  ✕ listed detail offers 登录后订阅 and no gift-pack copy (8006 ms)

  ● GWT-32.4 skill body is text: script source visible, no script/img nodes

    expect(received).toContain(expected) // indexOf

    Expected substring: "<script>"
    Received string:    ""

      64 |   expect(body.textContent).toContain('<script>')
         |                            ^

Test Suites: 1 failed, 1 total
Tests:       8 failed, 8 total
exit: 1
```

GWT-32.4 红因：脚本文本不可见（oracle 正确），不是 import 失败。

### 绿

```
$ npm test --prefix frontend/official -- --watchAll=false
PASS src/pages/SkillsSquare.test.tsx
PASS src/pages/CapabilityDetail.test.tsx
PASS src/components/layout/SiteLayout.beacon.test.tsx (5.526 s)
PASS src/App.test.tsx (5.716 s)
PASS src/components/home/FeaturesSection.test.tsx
PASS src/pages/Home.beacon.test.tsx (6.136 s)
PASS src/pages/Pricing.beacon.test.tsx
PASS src/pages/Home.test.tsx (6.578 s)
PASS src/pages/Pricing.test.tsx
PASS src/pages/Register.test.tsx (20.05 s)

Test Suites: 10 passed, 10 total
Tests:       36 passed, 36 total
Time:        20.709 s, estimated 37 s
Ran all test suites.
exit: 0

$ npm run build --prefix frontend/official
Creating an optimized production build...
Compiled successfully.
File sizes after gzip:
  167.8 kB (+113 B)    build/static/js/main.d2759c40.js
  ...
  608 B (+205 B)       build/static/css/main.780995fd.css
The project was built assuming it is hosted at /.
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
arch_exit:0

$ bash /Users/xuyun/.zcode/local-plugins/sdlc-workflow/scripts/check-sdlc.sh --require --hat implement /Users/xuyun/auto_agents/.sdlc/feat-four-pillars-v2
✓ 泳道声明
----------------------------------------
✓ SDLC 工件合规通过
sdlc_exit:0
```

XSS 节点（GWT-32.4）：`XSS_PAYLOAD = '<script>alert("xss")</script> <img src=x onerror=alert(1)>'`；`skill-md` `textContent` 含 `<script>`；`container.querySelector('script')` 为 null；`img[src="x"]` 为 null。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-32.4 脚本源码当文本、无脚本节点 | `GWT-32.4 skill body is text…` | ✅ |
| GWT-32.5 纯文本署名、不可点进父插件商店页 | `GWT-32.5 unlisted parent origin…` | ✅ |
| 父已上架才给 href | `listed parent origin renders a store link…` | ✅ |
| 未上架 GET = 官网 404 句 | `unlisted GET shows official 404 copy…` | ✅ |
| 加载失败 ≠ 空 | `load failure shows retry copy…` | ✅ |
| 离线句 | `offline failure uses offline copy` | ✅ |
| 预告无订阅 / 无礼包 / 无 enable-host | `coming_soon has preview mark…` | ✅ |
| 已上架「登录后订阅」 | `listed detail offers 登录后订阅…` | ✅ |
| IM-08 bounce query | `login-after-subscribe CTA href has subscribeType and subscribeName, not from=/capabilities/` | ✅ |
| IM-10 无端口兜底 | `hides 登录后订阅 when REACT_APP_ADMIN_URL is unset` | ✅ |
| T-21 `/skills` 映射未丢 | `SkillsSquare.test` GWT-30.2 / 44.2 | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A | 只读详情，无写 |
| 幂等 | ➖ N/A | 无创建/订阅写 |
| 并发写 | ➖ N/A | 无条件更新 |
| 外部依赖失败 | 5xx/网络 → 「能力详情加载失败」+重试；404 → 官网 404 | ✅ |

## 7. NFR 验证

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-04 | SKILL.md 纯文本；脚本不执行、无脚本节点 | Jest GWT-32.4：textContent 含 `<script>`；`querySelector('script')` null；`img[src="x"]` null | jsdom |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | XSS 合同已迁到 `CapabilityDetail.test.tsx`；`SkillsSquare.test.tsx` 仍是 T-21 列表映射，**不要当 XSS 还在旧页**。未上架详情前端消费 HTTP 404 后渲染与官网同一 404 句（SPA 不是后端 HTML 字节级）。订阅不 POST。mock `getPublicAsset`。 |
| `/backend` | 盘上详情无 `origin.href`；前端已按「无 href = 纯文本」实现。若要父已上架可点，需在 JSON 给 `origin.href=/capabilities/plugin/{name}`，未上架父不要给该字段。 |
| `/architect` | 无新错误码。 |
| T-25 | 「登录后订阅」跳 `{REACT_APP_ADMIN_URL}/login?subscribeType=&subscribeName=`（可选 `from=/capabilities?…` 后台列表，不是官网详情 path）。回跳只开窗、不自动 POST、安装行仍 0。未设 env 则隐藏 CTA。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿
- [x] 契约落位表已核对；未改 GWT/schema
- [x] ORM N/A
- [x] 无硬编码连接串/密钥/端口；详情组件无 hex
- [x] 无同步 redis 直调
- [x] 无 `except: pass`
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等 N/A
- [x] 条件更新 N/A
- [x] 外部依赖：超时沿 client；404 不重试；失败可重试
- [x] 四类易漏已覆盖或标 N/A 并给理由
- [x] T-23 无 origin.href 已写入下游，未自行拼父插件商店 path
- [x] 票状态已更新为 done（本文件为交票证据；ticket 头由 orchestrator 记账）

## Rework · IM-08 / IM-10（G-fresh FAIL 会话 01a08695-6df8-7d40-bc30-09526b7ea3db）

关闭：QA-03 / IM-08（官网 CTA 与后台 `subscribeType`/`subscribeName` 对不上）；QA-05 / IM-10（硬编码 `http://localhost:9112`）。未改 XSS/出处 Then、未改 admin/backend/T-22/T-25、未删 SkillsSquare T-21 测。

落点：`{REACT_APP_ADMIN_URL}/login?subscribeType={type}&subscribeName={slug}`；`from` 仅为后台 `/capabilities?subscribeType=&subscribeName=`（Login 已读 `from` 才能开窗），**不含** `from=/capabilities/{type}/{name}`。env 未设则隐藏 CTA，源码无端口兜底。

### TDD 红（实现前）

```
$ npm test --prefix frontend/official -- --watchAll=false --runInBand -t 'login-after-subscribe CTA href|hides 登录后订阅'
FAIL src/pages/CapabilityDetail.test.tsx
  ● login-after-subscribe CTA href has subscribeType and subscribeName, not from=/capabilities/

    expect(received).toContain(expected) // indexOf

    Expected substring: "subscribeType=skill"
    Received string:    "http://localhost:9112/login?from=%2Fcapabilities%2Fskill%2Fchild-skill"

  ● hides 登录后订阅 when REACT_APP_ADMIN_URL is unset

    expected document not to contain element, found <a class="capability-detail__subscribe" href="http://localhost:9112/login?from=%2Fcapabilities%2Fskill%2Fchild-skill">登录后订阅</a> instead

Test Suites: 1 failed, 9 skipped, 1 of 10 total
Tests:       2 failed, 36 skipped, 38 total
exit: 1
```

红因：href 仍是官网详情 `from=` + 端口兜底（oracle 正确），不是 import 失败。

### 绿

```
$ npm test --prefix frontend/official -- --watchAll=false --runInBand
PASS src/pages/CapabilityDetail.test.tsx
PASS src/pages/Register.test.tsx (21.812 s)
PASS src/pages/Pricing.test.tsx
PASS src/pages/Pricing.beacon.test.tsx
PASS src/pages/Home.test.tsx
PASS src/pages/SkillsSquare.test.tsx
…
Test Suites: 10 passed, 10 total
Tests:       38 passed, 38 total
Time:        32.74 s, estimated 40 s
Ran all test suites.
exit: 0

$ npm test --prefix frontend/official -- --watchAll=false --runInBand -t 'GWT-32.4|GWT-32.5'
PASS src/pages/CapabilityDetail.test.tsx
Test Suites: 9 skipped, 1 passed, 1 of 10 total
Tests:       36 skipped, 2 passed, 38 total
exit: 0

$ npm run build --prefix frontend/official
Creating an optimized production build...
Compiled successfully.
File sizes after gzip:
  167.8 kB (-2 B)  build/static/js/main.87e6e881.js
  ...
The project was built assuming it is hosted at /.
exit: 0
```

`CapabilityDetail.tsx` 无 `localhost:9112`（仅测试负向断言）。GWT-32.4 / 32.5 仍绿。
