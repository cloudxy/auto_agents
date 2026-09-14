# 实现证据 · T-06 官网 Hero 第一句锁采集

> 票：contract.md T-06｜FR 锚点：FR-U04（顺带钉首页 GWT-U24.1 四字）｜角色：/frontend｜日期：2026-09-12
> 上游：`01-define/spec.md` v1.2 FR-U04 · `02-shape/edge-states.md` 屏 1 · `02-shape/contract.md` T-06
> 泳道：ui｜未做 N3 结账页 / 我的渠道组

Hero 为静态采集句，不读结账/中转配置。精选空仍用 v2「还没有上架的能力…」，不得用支付/订阅顶替。可见面不写「当前可买」。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径/方法/状态码 | 官网路由 `/` | `frontend/official/src/App.tsx` | 无 Hero CMS、无 `/billing` |
| 字段校验（类型/范围/枚举） | ➖ N/A | | 无表单写 |
| 跨字段参数约束 | ➖ N/A | | |
| 权限判定（数据范围） | 静态页无会话 | `Home.tsx` + `SiteLayout.tsx` | GWT-U04.3：无「编辑官网第一句 / 改 Hero」 |
| 业务规则/状态流转 | 展示组件 | `Home.tsx` `HERO_FIRST_SENTENCE` | 第一句锁「粘贴链接即可出数。」 |
| 数据读写 | 精选 `useQuery` | `SkillsSection.tsx` | 空/错不顶替 Hero |
| 错误码映射 | 精选成败二分 | 同上 | 失败「暂时无法加载能力」+「重试」 |
| 幂等 | ➖ N/A | | 只读页 |

**分层依赖核对**：☑ 未改 backend Router/ORM/Schema ☑ official 未 import admin ☑ 未新建结账/渠道组页

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/official/src/pages/Home.tsx` | 修改 | 导出 `HERO_FIRST_SENTENCE`；h1 第一句锁采集；芯片/英文徽标 `aria-hidden` |
| `frontend/official/src/pages/Home.css` | 修改 | 标题强调色；主 CTA hover 加深 + `focus-visible` token ring |
| `frontend/official/src/pages/Home.test.tsx` | 修改 | GWT-U04.1/2/3 + 首页禁「当前可买」 |
| `frontend/official/src/App.test.tsx` | 修改 | 根路由第一句采集；禁支付/中转/四字 |
| `frontend/official/src/components/home/SkillsSection.tsx` | 修改 | `featured-empty` / `featured-error` testid；空句未改 |
| `.sdlc/upgrade-four-pillars/03-impl/T-06-evidence.md` | 新增 | 本文件 |

**与票里「会改哪些文件」一致**：☑ 是（`frontend/official` App 或 page 测试）

**未触碰「不许改的文件」**：☑ 确认（未做 checkout / relay 组页；未改 admin、backend、定价主按钮出口）

## 3. 关键实现决策

Hero 不订阅 billing/relay。精选 200 且 0 卡保持 v2 空句。主 CTA 仍「免费注册」→ `/register`；离线 `preventDefault` +「网络不可用。连接恢复后再注册。」

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 无写路径 | ➖ N/A | 静态 Hero + 公开列表读 |

**事务提交后的操作失败怎么办**：➖ N/A

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | ➖ N/A（无新建写） |
| 保证方式 | ➖ N/A |
| 重复请求返回 | ➖ N/A |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 无条件更新 | — | — |

☑ 本票无条件更新

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| `GET /public/skills`（精选） | react-query `retry: 1`（App）/ 测里 `retry: false` | 区块「重试」 | 失败句；Hero 仍在 | 读 |

## 4. ORM 与 DBML 对齐

☑ 未改 ORM / 迁移 / schema.dbml

结构核对输出：

```
$ 本票无 SHOW CREATE TABLE
N/A — UI-only；未自行加字段/改类型
```

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | 官网无 service 写；既有 `trackCta` / `trackPageView` 未改语义 |
| trace_id | 精选失败不展示 code/堆栈（沿用区块错误句） |
| 错误日志上下文 | ➖ 无新后端入口 |
| 慢操作耗时 | ➖ |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址 ☑ 无商户密钥

## 6. 自测证据

> 命令与退出码**原样粘贴**。「测试通过」「基本完成」不算证据。

```
$ cd /Users/xuyun/auto_agents/frontend/official && npm test -- --watchAll=false

> official@0.1.0 test
> jest --maxWorkers=2 --watchAll=false

PASS src/pages/Register.test.tsx (90.644 s)
PASS src/pages/CommandCards.test.tsx
PASS src/pages/Capabilities.test.tsx (94.435 s)
PASS src/components/layout/SiteLayout.beacon.test.tsx
PASS src/pages/Pricing.beacon.test.tsx
PASS src/pages/SkillsSquare.test.tsx (7.831 s)
PASS src/pages/CapabilityDetail.test.tsx
PASS src/pages/Pricing.test.tsx (5.56 s)
PASS src/pages/Home.beacon.test.tsx
PASS src/components/home/FeaturesSection.test.tsx
PASS src/App.test.tsx
PASS src/services/capabilities.test.ts
PASS src/pages/Home.test.tsx
A worker process has failed to exit gracefully and has been force exited. This is likely caused by tests leaking due to improper teardown. Try running with --detectOpenHandles to find leaks. Active timers can also cause this, ensure that .unref() was called on them.

Test Suites: 13 passed, 13 total
Tests:       79 passed, 79 total
Snapshots:   0 total
Time:        111.591 s, estimated 144 s
Ran all test suites.
exit: 0
```

Worker 未优雅退出为既有 jsdom/antd 定时器（P-FE-07）；套件仍 exit 0。

```
$ cd /Users/xuyun/auto_agents && bash tools/check/frontend.sh
前端工程门禁（F-2/F-3/F-4/F-5/F-6/F-7 已启用；F-1 批次 2 已由 service 归一承接）
==============================================================
✓ 前端工程门禁通过
exit: 0
```

```
$ cd /Users/xuyun/auto_agents && npm run build -w official

> official@0.1.0 build
> react-scripts build

Creating an optimized production build...
Compiled successfully.
exit: 0
```

```
$ rg -n '当前可买' frontend/official/src --glob '!*.test.*'
(no matches)
exit: 1
```

非测试源码 0 命中「当前可买」（rg 无匹配 exit 1）。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-U04.1 正常 | `GWT-U04.1 hero first sentence is collection paste-link / 出数`；`GWT-U04.1 root route first sentence is collection not payment` | ✅ |
| GWT-U04.2 空态 | `GWT-U04.2 featured empty does not replace hero with payment or subscribe` | ✅ |
| GWT-U04.3 越权 | `GWT-U04.3 no edit-hero entry on official home` | ✅ |
| GWT-U24.1 首页四字 | `GWT-U24.1 homepage visitor copy has no 当前可买`（全站机械钉交给 T-23） | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（无多步写） |
| 幂等 | — | ➖ N/A（无新建写） |
| 并发写 | — | ➖ N/A（无并发写） |
| 外部依赖失败 | `featured list failure shows retry not empty-success copy` | ✅ 精选失败不装空货架；Hero 仍在 |

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-U06 / FR-U24 | 访客首页无「当前可买」 | Jest + rg 非测试源 0 命中 | jsdom / 源码 |
| NFR-U09 | 本轮仅中文 | 第一句中文锁句 | 源码 |
| 屏 1 离线 | 静态 Hero 可阅读；CTA 锁句 | `warnOfflineRegister` 已实现；本票未新开 DevTools Offline | 代码路径 |

九维（本票触及）：主 CTA `hero-cta-primary` hover 加深、`focus-visible` 用 `--color-focus-ring`；芯片/徽标改 token 色。Hero 深空底与标题渐变沿用既有视觉，未重画全站。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 第一句常量 `HERO_FIRST_SENTENCE = '粘贴链接即可出数。'`，挂在 `data-testid="hero-first-sentence"`（h1）。精选 mock：失败 reject / 空 `{total:0,items:[]}`。官网无登录壳，U04.3 用源码+DOM 无编辑入口证明。全站「当前可买」机械钉仍是 T-23。 |
| `/frontend` | T-19/T-20/T-21 不得改 Home Hero 第一句。定价付费 CTA 仍是 v2「预告不可购买」（T-21）。 |
| `/architect` | 无新错误码。Hero 不读通道/SKU——U04.2 用「无分支」满足，不是 mock 已配通道。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（不是「大部分通过」）
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口/阈值（ADMIN_URL 仍走 `REACT_APP_ADMIN_URL`）
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`（吞异常）
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」
- [x] 条件更新的 `rows == 0` 已处理（无条件更新）
- [x] 外部依赖四件套齐全（超时/重试/降级/幂等前提）— 精选读：retry + 区块降级
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 无 `tickets/T-06.md`（shape 不写票文件）；本证据即交票物
