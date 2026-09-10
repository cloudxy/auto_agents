# 前端实现证据 · T-01 官网卖点闭集；删虚构规模；定价主按钮分档

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-01.md`｜FR 锚点：FR-01 / FR-02 / FR-05 / FR-70.4｜角色：/frontend｜日期：2026-09-08
> 上游：`02-shape/design-tokens.json` · `02-shape/flows/official-honesty.md` · `02-shape/edge-states.md` · `02-shape/sitemap.md`
> 泳道：L4

## 1. 组件树

```
<Home>                         页面级：Hero / 功能介绍 / 四步 / 架构 / 精选 / CTA
  ├─ <Hero>                    展示：无统计区；主 CTA /register；次 CTA {ADMIN}/login
  ├─ <FeaturesSection>         展示：导出 CSV 或 JSON + 单次最多 100 条
  ├─ <AiFlowSection>           既有四步（粘贴链接 / 任务 / 结果）
  ├─ <ArchitectureSection>     既有（未改卖点闭集）
  ├─ <SkillsSection>           容器：useQuery 公开列表；失败/空/加载分态
  └─ <CtaBand>                 展示：免费注册 → /register
<Pricing>                      页面级：三档静态；付费 Modal「预告不可购买」
```

| 组件 | 类型 | 复用 | 提取理由 |
|---|---|---|---|
| `<SkillsSection>` | 容器 | 仅首页 | 第一次出现，不抽共用库 |
| `<Pricing>` Modal | 容器 | 仅定价 | 第一次出现 |

未新建 `/chat`。未改后台五组。未改 backend。

## 2. 状态归属表

| 状态 | 放在哪 | 理由 |
|---|---|---|
| 能力精选列表 | `useQuery(['official', 'public-skills-featured'])` | 服务端公开列表 |
| 定价付费说明开关 | `Pricing` 内 `useState` | 仅本页 |
| mailto 失败提示 | 同 Modal 内 `useState` | 点击后才出现 |
| 当前用户 | 官网无会话（既有） | 可买集合匿名=登录 |

自检：

- [x] 精选无 `useEffect + fetch`（改为 react-query）
- [x] 服务端数据未复制进本地 list state
- [x] 无派生状态被单独存储
- [ ] 筛选/分页/排序/tab 在 URL 里 — 本票首页精选无筛选（空态链到 `/capabilities`）

## 3. 数据层

| 项 | 内容 |
|---|---|
| queryKey 设计 | `['official', 'public-skills-featured']` |
| 变更后失效范围 | 精选失败点「重试」→ `refetch()`；不 invalidate 其它 |
| 乐观更新 | 无 |
| 竞态验证 | 单测 mock reject 后稳定失败态 ☐ 已实测（Jest） |

## 4. 六态实现与实测

| 态 | 实现 | 怎么造出来的 | 实测 |
|---|---|---|---|
| **加载（首次）** | 精选 6 张 `Skeleton` 卡 | 单测走 query pending（构建时组件存在） | ☐ 无浏览器 Slow 3G |
| **加载（刷新）** | 失败态按钮 `loading` +「重试中…」 | 代码：`isFetching && !isLoading` | ☐ |
| **空（初始）** | 「还没有上架的能力…」+「去能力市场」 | 200 且 0 卡（代码路径） | ☐ 无空夹具页 |
| **空（筛选后）** | ➖ 精选无筛选 | — | ➖ |
| **错误** | 「暂时无法加载能力」+「重试」 | `listPublicSkills` mockRejectedValue | ✅ Jest `featured list failure…` |
| **权限** | 官网无「编辑卖点」入口；可买集合不随登录变 | 代码无该入口 | ✅ 静态审查 |
| **离线** | 精选走错误句；注册 CTA `navigator.onLine` 拦截 | 代码路径 | ☐ 无 DevTools Offline |
| **边界** | 无 Hero 三数；导出 100 条；付费非 `/register` | Jest | ✅ |

### 错误码分支覆盖

精选只消费公开列表成败，无业务错误码表。失败一律区块错误 + 重试（default）。

| 契约错误码 | 前端处理 | 实测 |
|---|---|---|
| 5xx / 网络 / catch | 「暂时无法加载能力」+「重试」 | ✅ |
| **default** | 同上，不渲染空成功句 | ✅ |

- [x] 未用 `message` 做逻辑判断
- [x] `default` 分支存在（isError）

### 交互态

| 态 | 实现 | 实测 |
|---|---|---|
| hover | 沿用既有 Hero/Card；付费按钮非 disabled | ☐ 未截图 |
| focus | 未 `outline: none` | ☐ |
| active | 既有 Button | ☐ |
| disabled | 付费主按钮**不是** disabled 冒充预告 | ✅ 单测可点开 Modal |

- [x] 异步：重试按钮 loading
- [x] 定价 Modal 失败保留页（不跳注册）

## 5. 九维自查

| 维 | 检查 | 结果 |
|---|---|---|
| ① 间距 | 新块沿用既有 padding；未新魔法间距体系 | ✅ 有限（未重做全站） |
| ② 颜色 | 新背景用 `--color-surface-sunken`；未给新块硬编码 hex | ✅ 新代码；Hero 既有 hex 未在本票重画 |
| ③ 字体 | 未新增字号体系 | ✅ |
| ④ 圆角 | 未新增 | ✅ |
| ⑤ 图标 | `@ant-design/icons`；Rocket 在有字按钮上 | ✅ |
| ⑥ 交互态 | 付费可点；重试 loading | ✅ 单测 |
| ⑦ 状态完整性 | 精选 加载/空/错误；定价静态+Modal | ✅ 错误/CTA 有单测 |
| ⑧ 响应式 | 未改断点；沿用既有栅格 | ☐ 未量 375/768/1024/1440 |
| ⑨ 可访问性 | 精选失败 `role="alert"`；Modal Esc；重试 `autoInsertSpace={false}` | ✅ 基线 |

**硬编码扫描**（本票新写样式，Pricing/SkillsSection）：

```
$ rg -n '#[0-9a-fA-F]{3,8}' frontend/official/src/pages/Pricing.tsx frontend/official/src/components/home/SkillsSection.tsx
（无命中）
```

`tokens.css` 新增 `--color-surface-sunken: #fafafa`（semantic.surfaceSunken = primitive.gray.50）。Hero 既有内联 hex 未在本票清扫。

**缺失的 token**：无。`CONTACT_MAIL` 走 `REACT_APP_CONTACT_MAIL`，缺省 `contact@localhost`。

## 6. a11y 核对

- [x] 定价付费/免费用 `Button`/`a`，非 div onClick
- [x] 重试为 button
- [x] Enter / Space：原生 button
- [ ] 焦点可见：未专门加 2px focusRing（沿用 antd）
- [x] 弹窗：antd Modal Esc + 关闭；`destroyOnHidden`
- [ ] 表单 label：本票无新表单
- [x] 精选失败 `role="alert"`
- [x] 不只靠颜色：预告有文字角标
- [ ] 键盘走查全流程：未在真浏览器走完

## 7. 响应式

| 断点 | 来源 | 实测 | 表格/宽内容处理 |
|---|---|---|---|
| 640 / 768 / 1024 | tokens / 既有 antd Col | ☐ | 定价 `xs=24 md=8` |

- [ ] 断点值来自 tokens，未自定义（沿用既有）
- [x] 主 CTA 高度 52–54px（≥44）
- [ ] 最窄断点无溢出：未量

## 8. 性能

| 项 | 措施 | 数字 |
|---|---|---|
| 路由懒加载 | `App.tsx` 既有 lazy | Home chunk `551.f1a8a4a2.chunk.js` 7.37 kB gzip |
| 首屏包大小 | CRA 构建 | `main.b1e2ab2d.js` 148.67 kB gzip |
| 长列表 | 精选最多 6 卡 | 6 |
| 重渲染 | react-query | 未 Profiler |

路由三件套：☑ 懒加载 ☑ 错误边界（既有 `*` NotFound）☑ 404 兜底。无 `/chat`。

## 9. 自测证据

> 命令与退出码原样粘贴。日期：2026-09-08。

```
$ npm run build --prefix frontend/official
Creating an optimized production build...
Compiled successfully.
File sizes after gzip:
  148.67 kB (+1 B)  build/static/js/main.b1e2ab2d.js
  ...
  7.37 kB (-5 B)    build/static/js/551.f1a8a4a2.chunk.js
exit: 0

$ npm test --prefix frontend/official -- --testPathPattern=Home.test --testNamePattern=test_no_direct_gateway_or_relay_token_copy
PASS src/pages/Home.test.tsx
  ✓ test_no_direct_gateway_or_relay_token_copy (409 ms)
Test Suites: 1 passed, 1 total
Tests:       3 skipped, 1 passed, 4 total
exit: 0

$ npm test --prefix frontend/official -- --testPathPattern=FeaturesSection.test --testNamePattern=test_no_direct_gateway_or_relay_token_copy
PASS src/components/home/FeaturesSection.test.tsx
  ✓ test_no_direct_gateway_or_relay_token_copy (83 ms)
Test Suites: 1 passed, 1 total
Tests:       1 skipped, 1 passed, 2 total
exit: 0

$ npm test --prefix frontend/official -- --testPathPattern=Pricing.test --testNamePattern=test_no_direct_gateway_or_relay_token_copy
PASS src/pages/Pricing.test.tsx
  ✓ test_no_direct_gateway_or_relay_token_copy (254 ms)
Test Suites: 1 passed, 1 total
Tests:       3 skipped, 1 passed, 4 total
exit: 0

$ bash tools/check/frontend.sh
前端工程门禁（F-2/F-3/F-4/F-5/F-6/F-7 已启用；F-1 批次 2 已由 service 归一承接）
==============================================================
✓ 前端工程门禁通过
exit: 0

$ npm test --prefix frontend/official -- --watchAll=false
Test Suites: 5 passed, 5 total
Tests:       13 passed, 13 total
exit: 0
```

三个 70.4 node **分别跑过**，禁止只跑 Pricing.test。未把 GWT-72.3「我的渠道组」写成同一句。

### 验收项对应

| GWT | 覆盖方式 | 结果 |
|---|---|---|
| GWT-01.1 | 定价免费档文案 5 / 10,000 / 20 万；Jest | ✅ |
| GWT-01.7 / 05.1 | 免费档 `href="/register"` | ✅ |
| GWT-01.8 | Hero/四步保留粘贴链接、任务、结果 | ✅ 文案 |
| GWT-01.9 / 01.11 | FeaturesSection 无 Excel/xlsx；CSV 或 JSON + 100 条 | ✅ |
| GWT-01.10 | 定价免费档出现成员管理、用量看板 | ✅ 文案 |
| GWT-01.2 | B1–B4 带「预告」；所在档主按钮非注册 | ✅ |
| GWT-01.12 / 05.2 | 付费「预告不可购买」+ Modal；不到 `/register` | ✅ |
| GWT-01.3 | 官网无会话，可买集合同一套静态 | ✅ |
| GWT-01.4 | 精选失败句 + 重试；禁空成功句 | ✅ |
| GWT-01.5 | 未加「编辑官网卖点」入口 | ✅ 静态 |
| GWT-01.6 | 未写准确率/已校准/官方认证/正品保证 | ✅ 静态 |
| GWT-02.1–02.3 | 删除 `HERO_STATS`；无「示意数据」脚注 | ✅ |
| GWT-05.3 | 付费 CTA 仍非再注册 | ✅ |
| GWT-70.4（本票侧） | 三 node：Home / FeaturesSection / Pricing | ✅ 三闸 exit 0 |
| GWT-72.3 | **不是本票同一句**；未当 70.4 完成态 | — |

## 10. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 三 node 路径见上。另：Home.test 覆盖假统计/注册 CTA/精选失败；Pricing.test 覆盖付费不到 register。精选失败 mock = `listPublicSkills` reject。已知：SiteLayout 仍并列「技能广场」「能力广场」（sitemap 禁并列，属市场票非 T-01）；`SkillsSquare`/`Capabilities` 空态仍有「暂无已发布*」（非首页精选块）。无 `/chat`。 |
| `/designer` | 付费 mailto 收件人用 `REACT_APP_CONTACT_MAIL`，缺省 `contact@localhost`。Hero 既有深空 hex 未换 ink token。 |
| `/architect` | Q-PRICE / Q-BILL 未关：付费只预告+mailto，未履约。70.4 官网三 node 已加；T-20 admin node 不在本票。 |
| `/backend` | 未改 API。精选仍打 `GET /public/skills`。 |

## 11. 交票自检

- [x] 九维自查已走（响应式/键盘未真机量完，已标明）
- [x] 精选错误态单测实测；其它六态代码路径在
- [x] 精选失败 default 分支
- [x] 本票新样式无硬编码 hex
- [x] 精选无手写 `useEffect + fetch`
- [x] 状态归属符合
- [ ] a11y 键盘走查未在真浏览器完成
- [ ] 每个断点未实测
- [x] 构建与三闸 + check-frontend 全绿，证据原样贴
- [x] 无 `/chat`；路由三件套既有
- [x] 六问未代选
- [x] 票状态已更新为 done
