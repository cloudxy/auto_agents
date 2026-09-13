# 实现证据 · T-20 「我的渠道组」未开通/已开通/到期/明文一次

> 票：`02-shape/contract.md` §10 T-20｜FR 锚点：FR-U20 FR-U21 FR-U23｜角色：/frontend｜日期：2026-09-12
> 上游：T-18 GET `/relay/sku` · T-25 屏 13/14 锁句
> 泳道：ui｜租户 `/newapi` 仍 404 同形｜禁 FR-U24 四字

已买真相只在 SKU 闸，禁止 COUNT 组行。专业档开通 ≠ 中转 active。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| GET `/api/v1/relay/sku` | service + page | `services/relay.ts` `fetchRelaySku` | status none/active/expired |
| none（含已停用） | 空态 | 「未开通中转」+「去升级」 | 买方 `product=relay`；隐藏组/令牌 |
| expired | 空态 | 「中转已到期」+「去升级」 | 无签发 |
| active + 0 令牌 | 空态 | 「还没有令牌」 | 买方签发入口 |
| active 用量 | 既有表 | 本企业 used_tokens | 无上游 Key 全文 |
| 明文一次 | 弹窗 | 关闭后仅前缀 | Toast「已签发」；复制「已复制令牌」 |
| 经办去升级 | 屏 10 | 「请联系本企业管理员开通」 | 不进结账、不建单 |
| 导航 | menuConfig | 「我的渠道组」 | 无「已开通/使用中」角标 |
| 租户 `/newapi` | 既有守卫 | App MainLayout | 404 同形；本票回归 |

**分层依赖核对**：☑ 未写权益表 ☑ 未改值班页 ☑ 未接 notify

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/pages/RelayGroups.tsx` | 修改 | SKU 闸；none/expired 不拉组表 |
| `frontend/admin/src/components/relay/RelaySkuEmpty.tsx` | 新增 | 未开通/到期空态 |
| `frontend/admin/src/constants/relayCopy.ts` | 新增 | T-25 锁句 |
| `frontend/admin/src/services/relay.ts` | 修改 | `fetchRelaySku` |
| `frontend/admin/src/pages/RelayGroups.test.tsx` | 修改 | U20/U21/U23 + 既有签发 |
| `frontend/admin/src/config/menuConfig.tsx` | 修改 | 叶名「我的渠道组」 |
| `frontend/admin/src/App.menu.test.tsx` | 修改 | 导航文案 + U21.2 |
| `.sdlc/upgrade-four-pillars/03-impl/T-20-evidence.md` | 新增 | 本文件 |

**未触碰「不许改的文件」**：☑ 确认（无 046；无履约写 SKU；无 `/newapi` 租户入口）

## 3. 关键实现决策

SKU≠active 不调用 `fetchRelayPage`（040 骨架行由 T-18 已藏；前端再闸一层）。`paid_pending_fulfillment` 且 product=relay：顶栏处理中句，内容仍 none/expired。去升级读 `upgrade.action`：checkout → `/billing/checkout?product=relay`；否则屏 10。

## 4. ORM 与 DBML 对齐

☑ 未改 ORM。读 T-18 已有 `/relay/sku`。

## 5. 可观测性

签发明文不进列表 DOM。无 master / 上游 Key。

## 6. 自测证据

```
$ cd /Users/xuyun/auto_agents/frontend/admin && npm test -- --watchAll=false --silent src/pages/RelayGroups.test.tsx src/App.test.tsx src/App.menu.test.tsx

> admin@0.1.0 test
> jest --maxWorkers=2 --watchAll=false --silent src/pages/RelayGroups.test.tsx src/App.test.tsx src/App.menu.test.tsx

PASS src/App.menu.test.tsx (11.364 s)
PASS src/App.test.tsx
PASS src/pages/RelayGroups.test.tsx (64.447 s)
Test Suites: 3 passed, 3 total
Tests:       35 passed, 35 total
Snapshots:   0 total
Time:        64.793 s
EXIT:0
```

```
$ bash tools/check/frontend.sh
✓ 前端工程门禁通过
FRONTEND_SH_EXIT:0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-U20.1 已开通 | `GWT-U20.1 active lists own usage…` | ✅ 用量；无 master；非值班 |
| GWT-U20.2 0 令牌 | `gwt_60_4 / GWT-U20.2` | ✅ 「还没有令牌」 |
| GWT-U21.1 未开通 | `GWT-U21.1 SKU none…去升级 product=relay` | ✅ 不拉组表 |
| GWT-U21.2 导航 | `GWT-U21.2 我的渠道组 nav has no 已开通/使用中` | ✅ |
| GWT-U23.1 明文一次 | `gwt_60_1` / `gwt_60_11` | ✅ |
| GWT-U23.4 到期 | `GWT-U23.4 SKU expired` | ✅ 「中转已到期」 |
| GWT-U23.5 经办拒签 | `gwt_60_7` | ✅ |
| GWT-U35.6/7 去升级 | none 买方进结账；经办屏 10 | ✅ |
| GWT-U22 租户值班 | `App.test` operator/company admin `/newapi` 404 | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A UI |
| 幂等 | — | ➖ N/A（签发仍走 T-18） |
| 并发写 | — | ➖ N/A |
| 外部依赖失败 | `gwt_84_1` 失败≠未开通/还没有令牌 | ✅ |

## 7. NFR

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| FR-U24 | 无「当前可买」 | none 渲染 + 扫描 | jsdom |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 租户打开「我的渠道组」≠ 直打 `/newapi`。SKU none 时「签发令牌」隐藏不是禁用。 |
| `/frontend` | 菜单叶现名「我的渠道组」；页头随 `pageTitleFor` 派生。 |

## 9. 交票自检

- [x] 命令 + 退出码原样
- [x] 自测全绿
- [x] 未改 GWT / schema / tokens
- [x] 租户 `/newapi` 仍 404
- [x] RelayGroups 346 行 ≤ 400
