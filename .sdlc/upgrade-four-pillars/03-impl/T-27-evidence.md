# 实现证据 · T-27 值班页三态 UI；租户直打仍 404 同形

> 票：`02-shape/contract.md` §10 T-27｜FR 锚点：FR-U25｜角色：/frontend｜日期：2026-09-13
> 上游：`01-define/spec.md` FR-U25 GWT-U25.1…U25.4 · `02-shape/edge-states.md` 屏 19 · `newapiShared.ts` 锁句
> 泳道：ui｜未做 checkout｜禁 FR-U24 四字｜租户 `/newapi` 404 同形保持（T-09/T-12 / GWT-U25.3）
> 返工 1：QA-01 证据复跑 + QA-02 三态互斥（hasLiveRow 压过 empty/degrade；行「活」须网关可达）

空 / 降级 / 活 页级标题互斥。禁止「暂无渠道」。活行状态「活」+●。伪装不把渠道打成自动禁用。加载失败 ≠ 空。消费 T-26 `duty_page_state` / `duty_row_status*`。值班「活」≠ SKU active。Q-OPS-DUTY 本波无 SLA 数字。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 屏 19 空句 | `DUTY_EMPTY_71_2` | `newapiShared.ts` + Overview3q | 「还没有平台模型，去网关登记」+ 刷新 |
| 屏 19 降级句 | `DUTY_DEGRADE_71_3` | 同上 | 「LLM 网关管理面不可达，仅本地事件/探针」；本地表继续 |
| 屏 19 活 | `DUTY_LIVE` + Badge | OverviewChannels 状态列 | 网关可达 ∧（API live ∨ 本地 original） |
| 三态互斥 | `resolveDutyBanner` | `newapiShared.ts` | loading/error → hasLiveRow(live) → duty_page_state → degrade → empty → ok |
| 加载失败 | `DUTY_LOAD_FAILED` | Overview3q health | 失败 ≠ 空 ≠ 降级 |
| 伪装不自动关 | 行判定 Tag | OverviewChannels | 无「自动禁用」；开关/禁用钮不出现 |
| 租户直打 `/newapi` | 既有 MainLayout | `App.tsx` | 屏 21 同形；本票回归 GWT-U25.3 |

**分层依赖核对**：☑ 未改 backend Router/ORM/Schema ☑ 消费 T-26 字段、未改 schema ☑ 未做 checkout ☑ official 未 import admin

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/components/newapi/newapiShared.ts` | 修改 | `showDutyLiveRow` 先闸 `gatewayAvailable`；`resolveDutyBanner` 在 error/loading 后 `hasLiveRow` 压过 empty/degrade |
| `frontend/admin/src/components/newapi/OverviewChannels.tsx` | 修改 | 状态列「活」+●；降级不标活（经 `showDutyLiveRow`） |
| `frontend/admin/src/components/newapi/Overview3q.tsx` | 修改 | 空/降级/错误/活标题互斥；消费 duty 字段 |
| `frontend/admin/src/components/newapi/Overview3q.test.tsx` | 修改 | 删冲突金标；补 `duty_page_state=empty` + 活行不得出空句 |
| `frontend/admin/src/pages/NewApiOps.test.tsx` | 修改 | 页级 U25.1 / 失败≠空；71.2/71.3 钉 活 |
| `frontend/admin/src/App.menu.test.tsx` | 修改 | GWT-U25.3 租户直打 404 同形（保留 U15.3） |
| `.sdlc/upgrade-four-pillars/03-impl/T-27-evidence.md` | 修改 | 本文件（QA-01 原样粘贴） |

**与票里「会改哪些文件」一致**：☑ 是（值班 UI + 三套 Jest）

**未触碰「不许改的文件」**：☑ 确认（无 checkout；无 GWT/schema/tokens；无租户 `/newapi` 入口）

## 3. 关键实现决策

消费 T-26：`overview.duty_page_state` 与 `models[].duty_row_status*`。`showDutyLiveRow`：`gatewayAvailable && (API live ∨ 本地 original)`；`gatewayAvailable===false` 即使 API 标 live 也不标行「活」。`resolveDutyBanner`：error/loading 之后 `hasLiveRow` 压过 empty/degrade（含 `duty_page_state=empty`，覆盖总览 0 模型 + 渠道缓存活行）。无活行时仍信 `duty_page_state`。伪装只出「伪装」Tag，不映射 `CHANNEL_STATUS.AUTO_DISABLED`。

### 9 维

1. 间距：沿用既有 Card/Table 节奏 2. 色：Badge `status="success"` / Tag，无新 hex 3. 字：锁句 4. 圆角阴影：antd 5. 图标：Badge 点 = ●，非 emoji 6. 交互：空态刷新、失败重试 7. 六态：加载骨架 / 空 / 错误 / 降级 / 权限 404 / 离线提示 8. 表 `scroll.x` 窄屏 9. 「活」文字 + 点，不只靠绿

### 事务 / 幂等 / 并发

➖ N/A UI 只读驾驶舱。探测仍走既有 react-query `refetchInterval`。

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| GET `/newapi/overview` | react-query `retry: false`（测） | 失败句「重试」 | 失败 ≠ 空 | 读 |
| GET `/newapi/channels` + probes | 同 | 区级失败 | 降级禁标活 | 读 |

## 4. ORM 与 DBML 对齐

☑ 未改 ORM / 迁移 / schema.dbml。未自行加 live 列。

## 5. 可观测性

页上无完整 Key（既有掩码）。☑ 无密码/token。

## 6. 自测证据

### TDD 红（QA-02 断言先于产品改）

```
$ cd /Users/xuyun/auto_agents/frontend/admin && npm test -- --watchAll=false --silent src/components/newapi/Overview3q.test.tsx

> admin@0.1.0 test
> jest --maxWorkers=2 --watchAll=false --silent src/components/newapi/Overview3q.test.tsx

FAIL src/components/newapi/Overview3q.test.tsx (5.869 s)
  ● resolveDutyBanner: empty / degrade / live / error are mutually exclusive
    Expected: "live"
    Received: "degrade"
  ● resolveDutyBanner: hasLiveRow overrides empty/degrade duty_page_state; error still wins
    Expected: "live"
    Received: "empty"
  ● showDutyLiveRow requires gatewayAvailable and API live or local original
    Expected: false
    Received: true
  ● duty_page_state empty plus a live row must not show empty copy
    expected document not to contain element, found <div data-testid="duty-banner-empty">…还没有平台模型，去网关登记…

Test Suites: 1 failed, 1 total
Tests:       4 failed, 10 passed, 14 total
exit: 1
```

### TDD 绿 + QA-01 三套 Jest

```
$ cd /Users/xuyun/auto_agents/frontend/admin && npm test -- --watchAll=false --silent src/components/newapi/Overview3q.test.tsx src/pages/NewApiOps.test.tsx src/App.menu.test.tsx

> admin@0.1.0 test
> jest --maxWorkers=2 --watchAll=false --silent src/components/newapi/Overview3q.test.tsx src/pages/NewApiOps.test.tsx src/App.menu.test.tsx

PASS src/App.menu.test.tsx (19.488 s)
PASS src/components/newapi/Overview3q.test.tsx
PASS src/pages/NewApiOps.test.tsx (165.072 s)

Test Suites: 3 passed, 3 total
Tests:       43 passed, 43 total
Snapshots:   0 total
Time:        165.804 s
exit: 0
```

```
$ cd /Users/xuyun/auto_agents && bash tools/check/frontend.sh
前端工程门禁（F-2/F-3/F-4/F-5/F-6/F-7 已启用；F-1 批次 2 已由 service 归一承接）
==============================================================
✓ 前端工程门禁通过
exit: 0
```

```
$ wc -l frontend/admin/src/components/newapi/Overview3q.tsx frontend/admin/src/components/newapi/OverviewChannels.tsx
     354 frontend/admin/src/components/newapi/Overview3q.tsx
     226 frontend/admin/src/components/newapi/OverviewChannels.tsx
exit: 0
```

```
$ grep -n '当前可买' frontend/admin/src/components/newapi/Overview3q.tsx frontend/admin/src/components/newapi/OverviewChannels.tsx frontend/admin/src/components/newapi/newapiShared.ts
(none)
$ grep -nE "['\">]暂无渠道" frontend/admin/src/components/newapi/Overview3q.tsx frontend/admin/src/components/newapi/OverviewChannels.tsx
(none)
$ grep -n 'FORBIDDEN_CHANNEL_EMPTY' frontend/admin/src/components/newapi/Overview3q.tsx frontend/admin/src/components/newapi/OverviewChannels.tsx
(none)
$ grep -n 'FORBIDDEN_CHANNEL_EMPTY' frontend/admin/src/components/newapi/newapiShared.ts
38:export const FORBIDDEN_CHANNEL_EMPTY = '暂无渠道'
banned-phrase scan PASS
exit: 0
```

`暂无渠道` 仅 `FORBIDDEN_CHANNEL_EMPTY` 禁句常量，产品 tsx 不引用、不渲染。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-U25.1 正常 | `Overview3q` / `NewApiOps` `GWT-U25.1`；`GWT-98.2` 钉「活」 | ✅ 行「活」；非空/非降级 |
| GWT-U25.2 空态 | `GWT-U25.2` / `GWT-71.2` | ✅ 空句；禁「暂无渠道」；非加载失败；无「活」 |
| GWT-U25.3 越权 | `App.menu` `GWT-U25.3`（保留 `GWT-U15.3`） | ✅ 404 同形；无渠道/密钥/抱歉 |
| GWT-U25.4 降级 | `GWT-U25.4` / `GWT-71.3` | ✅ 降级句；本地探针；无空句；无「活」 |
| 失败 ≠ 空 | `load fail is not empty`（两套） | ✅ `DUTY_LOAD_FAILED` |
| 伪装不自动关 | `spoofed tag does not flip…` / `GWT-61.1` | ✅ 「伪装」；无自动禁用；非「活」 |
| QA-02 空+活 | `duty_page_state empty plus a live row must not show empty copy` | ✅ 有活行不出空句 |
| QA-02 降级不标活 | `showDutyLiveRow` `gatewayAvailable: false` → false | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A UI |
| 幂等 | — | ➖ N/A 只读 |
| 并发写 | — | ➖ N/A |
| 外部依赖失败 | overview reject → 失败句，不装空 | ✅ |

## 7. NFR

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| FR-U24 | 无「当前可买」 | grep 产品文件 0 hit + Jest `not.toContain` | jsdom |
| F-7 | 业务 tsx ≤ 400 | Overview3q 354；OverviewChannels 226 | wc -l |
| Q-OPS-DUTY | 本波无 SLA 数字 | 未写入 SLA | — |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 活 = 可达 ∧（API live ∨ 已登记 ∧ original）。降级不标活。`duty_page_state=empty` 且渠道行活 → 页标题不回空句。租户 `/newapi` 仍屏 21。值班「活」≠ SKU active。 |
| `/backend` | 已消费 `duty_page_state` / `duty_row_status*`。QA-03/04/05 仍属 backend。 |
| `/architect` | 无新错误码。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（43 passed）
- [x] 未改 GWT / schema / tokens
- [x] 租户 `/newapi` 仍 404 同形
- [x] 无「当前可买」；无「暂无渠道」渲染（命令 + exit 0）
- [x] 无 checkout
- [x] Overview3q 354 ≤ 400
- [x] 已删「T-26 仍 todo / 活不另开 API 字段」
