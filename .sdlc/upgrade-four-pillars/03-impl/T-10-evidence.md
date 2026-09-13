# 实现证据 · T-10 关闭句 vs 空货架；订一行出现在我的安装

> 票：contract.md T-10｜FR 锚点：FR-U10 FR-U11｜角色：/frontend｜日期：2026-09-12
> 上游：`01-define/spec.md` v1.2 FR-U10/U11 · `02-shape/edge-states.md` 屏 3/15/16/17/24 · `02-shape/contract.md` T-10 · T-08/T-13
> 泳道：ui｜未做结账 / 未写「当前可买」

总开关关：公开/租户货架锁句「能力市场未开放」，禁止「暂无已上架能力」。开关开且可见行=0：锁句「暂无已上架能力」，禁止空白、禁止加载失败写成这句。经办订 listed 一行后「我的安装」出现该行；订插件不带子卡。预告无订阅按钮。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 公开列表关闭 vs 空货架 | 官网列表 | `frontend/official/src/pages/Capabilities.tsx` | `market_closed` → 关闭句；开且 0 行 → 空货架句 |
| 租户货架 / 超管七叶 | 后台 `/capabilities` 壳差 | `Capabilities.tsx` + `market/TenantShelf.tsx` | 租户屏 15；超管屏 24 |
| 订一行 | SubscribeModal + 安装页 | `SubscribeModal.tsx` + `MyInstalls.tsx` | 成功后 navigate `/capabilities/installs` |
| 预告无按钮 | 货架卡 | TenantShelf / 官网卡 | `coming_soon` 无「订阅」 |
| 总开关 | 超管控件 | `PowerMarketSwitch.tsx` | GET/PUT `/admin/power-market`；租户无控件 |
| 错误码映射 | 弹窗 | `MARKET_CLOSED` → 关闭句 | 关闭尝试不 Toast「已订阅」 |

**分层依赖核对**：☑ 未改 backend Router/ORM/Schema ☑ official 未 import admin ☑ 未新建结账/checkout 页

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/official/src/pages/Capabilities.tsx` | 修改 | 关闭句 / 空货架句 / 筛选空分家 |
| `frontend/official/src/pages/capabilityMarket.ts` | 修改 | 锁句常量 |
| `frontend/official/src/pages/CapabilityDetail.tsx` | 修改 | 关闭详情不渲染正文 |
| `frontend/official/src/services/capabilities.ts` | 修改 | `market_closed` 字段 |
| `frontend/official/src/pages/Capabilities.test.tsx` | 修改 | GWT-U10.2 / U11.2 |
| `frontend/official/src/pages/CapabilityDetail.test.tsx` | 修改 | 关闭详情 |
| `frontend/admin/src/pages/Capabilities.tsx` | 修改 | 租户货架 vs 超管七叶 |
| `frontend/admin/src/pages/market/TenantShelf.tsx` | 新增 | 屏 15 |
| `frontend/admin/src/pages/market/shelfCopy.ts` | 新增 | 与官网同一对锁句 |
| `frontend/admin/src/pages/market/PowerMarketSwitch.tsx` | 新增 | 屏 24 总开关 |
| `frontend/admin/src/services/capabilities.ts` | 修改 | `listPublicAssets` / power-market |
| `frontend/admin/src/components/SubscribeModal.tsx` | 修改 | `MARKET_CLOSED` |
| `.sdlc/upgrade-four-pillars/03-impl/T-10-evidence.md` | 新增 | 本文件 |

**与票里「会改哪些文件」一致**：☑ 是（admin + official 货架；未做 checkout）

**未触碰「不许改的文件」**：☑ 确认（未做 checkout / 未写「当前可买」；未改 GWT / schema / tokens）

## 3. 关键实现决策

关闭优先于筛选空：关+q 仍关闭句。失败走「市场列表加载失败」，不装没货或未开放。租户 `/capabilities` 不是 404。订插件只 POST 该行，安装列表以 `listInstalls` 为准（后端不级联）。

### 事务 / 幂等 / 并发

☑ 本票无多步写 / 无先查后插 / 无条件更新。订阅成功 Toast 后跳转安装页。

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| GET `/public/capabilities` | react-query `retry: false` | 区块「重试」 | 失败句 | 读 |
| POST subscribe | 按钮 loading+disabled | 不关窗 | `MARKET_CLOSED` 关闭句 | 后端唯一约束 |

## 4. ORM 与 DBML 对齐

☑ 未改 ORM / 迁移 / schema.dbml。总开关读运行配置 API。

## 5. 可观测性

失败不展示内部码。☑ 无密码/token/证件。

## 6. 自测证据

```
$ cd /Users/xuyun/auto_agents/frontend/official && npm test -- --watchAll=false src/pages/Capabilities.test.tsx src/pages/CapabilityDetail.test.tsx src/pages/CommandCards.test.tsx

PASS src/pages/CapabilityDetail.test.tsx
PASS src/pages/CommandCards.test.tsx
PASS src/pages/Capabilities.test.tsx
Test Suites: 3 passed, 3 total
Tests:       35 passed, 35 total
exit: 0
```

```
$ cd /Users/xuyun/auto_agents/frontend/official && npm test -- --watchAll=false src/pages/Capabilities.test.tsx

PASS src/pages/Capabilities.test.tsx (33.629 s)
  ✓ GWT-31.2 / GWT-U10.2 unfiltered empty is 暂无已上架能力, not closed or load-fail
  ✓ GWT-U11.2 closed market is 能力市场未开放, not empty shelf
  ✓ GWT-U11.2 closed plus filters still uses closed copy, not filter-empty
  ✓ GWT-U10.2 load failure is not empty shelf or closed
Test Suites: 1 passed, 1 total
Tests:       19 passed, 19 total
exit: 0
```

```
$ cd /Users/xuyun/auto_agents/frontend/admin && npm test -- --watchAll=false src/pages/market/TenantShelf.test.tsx src/pages/market/PowerMarketSwitch.test.tsx src/components/SubscribeModal.test.tsx src/pages/Capabilities.governance.test.tsx src/pages/Capabilities.subscribe.test.tsx src/pages/Capabilities.command.test.tsx src/pages/Capabilities.import.test.tsx src/hooks/usePermission.test.tsx src/App.menu.test.tsx

PASS src/pages/market/TenantShelf.test.tsx
PASS src/pages/market/PowerMarketSwitch.test.tsx
PASS src/components/SubscribeModal.test.tsx
PASS src/pages/Capabilities.governance.test.tsx
PASS src/pages/Capabilities.subscribe.test.tsx
PASS src/pages/Capabilities.command.test.tsx
PASS src/pages/Capabilities.import.test.tsx
PASS src/hooks/usePermission.test.tsx
PASS src/App.menu.test.tsx
Test Suites: 9 passed, 9 total
Tests:       65 passed, 65 total
exit: 0
```

```
$ cd /Users/xuyun/auto_agents/frontend/admin && npm test -- --watchAll=false src/pages/market/TenantShelf.test.tsx

PASS src/pages/market/TenantShelf.test.tsx
  ✓ GWT-U11.2 closed flag copy is 能力市场未开放, not empty shelf
  ✓ GWT-U10.2 open plus 0 listed is 暂无已上架能力, not blank or load-fail
  ✓ GWT-U10.4 coming_soon has 预告 and no subscribe button
  ✓ GWT-U10.3 readonly subscribe is disabled and does not POST
  ✓ GWT-U10.1 subscribe plugin appears in 我的安装 without children
Tests: 8 passed, 8 total
exit: 0
```

```
$ cd /Users/xuyun/auto_agents && bash tools/check/frontend.sh
✓ 前端工程门禁通过
exit: 0
```

非测试官网/租户货架源码不渲染「当前可买」（仅注释禁令与测试负向断言）。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-U10.1 订一行且插件不带子卡 | `GWT-U10.1 subscribe plugin appears in 我的安装 without children` | ✅ 安装页仅父插件行 |
| GWT-U10.2 开且 0 行空货架 | official + TenantShelf `暂无已上架能力`；失败≠这句 | ✅ |
| GWT-U10.3 只读 | `GWT-U10.3 readonly subscribe is disabled and does not POST` | ✅ |
| GWT-U10.4 预告 | official GWT-31.5 + TenantShelf GWT-U10.4 | ✅ 无订阅按钮 |
| GWT-U11.1 关闭订不到 | 关闭态无按钮；弹窗 `MARKET_CLOSED` 不 Toast 已订阅 | ✅ |
| GWT-U11.2 关闭≠空货架 | official + TenantShelf GWT-U11.2 | ✅ 「能力市场未开放」 |
| GWT-U11.3 公司管理员不能改开关 | `tenant company admin has no market switch` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（无多步写） |
| 幂等 | SubscribeModal 已订阅无新增行（既有） | ✅ |
| 并发写 | — | ➖ N/A |
| 外部依赖失败 | 列表失败≠空货架/关闭；开关读失败可重试 | ✅ |

## 7. NFR

| NFR | 要求 | 实测 |
|---|---|---|
| NFR-U06 / FR-U24（本页） | 不写「当前可买」 | Jest 负向断言 + 非测试源无渲染 |
| 屏 3/15 三空 | 关闭 / 空货架 / 筛选空分家 | Jest |

未做 checkout。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 关闭：`data-testid="market-closed"`。空货架：`empty-shelf`。租户壳：`tenant-shelf`。超管：`governance-shell` + `power-market-switch`。订插件 fixture `u101-plug`，安装列表不得出现 `u101-s1/s2`。 |
| `/frontend` | T-19 结账不得改货架两句。T-23 全站机械钉仍待做。 |
| `/architect` | 关闭列表依赖后端 `market_closed`；前端不把 0 行当关闭。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿
- [x] 未做 checkout / 未写「当前可买」
- [x] 未改 GWT / schema / tokens
- [x] 四类易漏已覆盖或标 N/A
