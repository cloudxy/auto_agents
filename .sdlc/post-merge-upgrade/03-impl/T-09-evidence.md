# 实现证据 · T-09 结账/我的订单租户闭集

> 票：contract §10 T-09｜FR 锚点：FR-M10 / FR-M11 / FR-M15｜角色：/frontend（lane: ui）｜日期：2026-09-13

## 1. 契约落位表（UI 面）

| 契约元素 | 落在哪 | 文件 | 备注 |
|---|---|---|---|
| 主钮「提交开通」 | Checkout | `Checkout.tsx` | W2 不要求选通道；不渲染「去支付」 |
| 未配通道仍可提交（GWT-M11.1/2） | 打开≠空页 | 同上 | 看得见商品+提交；提交后待支付+「收款通道未开通，提交后等待平台确认开通」 |
| 已有待支付（GWT-M11.8） | 409 映射 | `CHECKOUT_PENDING_EXISTS_COPY` | 禁「已有未完成的支付」 |
| 非买方（GWT-M11.3） | preview 422 | `ORDER_ROLE_NOT_ALLOWED` | 「请联系本企业管理员开通」 |
| 闭集待支付/已开通 | 映射 | `utils/orderStatus.ts` | `checkout_pending/pending`→待支付；`fulfilled/paid`→已开通；fulfilling/unpaid 不新造第三套名 |
| 无取消 | Checkout | 无取消钮 | GWT-M11.10 |
| 我的订单 | 状态列 | `MyOrders.tsx` | 空行不钉金标；次链「去结账」 |

**9 维**：提交 loading「提交中…」；非法 product「没有这个商品」+返回定价；无新 hex。

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/constants/collectCopy.ts` | 修改 | 「已有待支付」；提交开通；待支付说明句 |
| `frontend/admin/src/utils/orderStatus.ts` | 新增 | 租户两态映射 |
| `frontend/admin/src/services/billing.ts` | 修改 | `createCheckout` channel 可选 |
| `frontend/admin/src/pages/Checkout.tsx` | 重写 | W2 故事；210 行 |
| `frontend/admin/src/pages/MyOrders.tsx` | 修改 | 待支付/已开通；空态去结账 |
| `frontend/admin/src/pages/Checkout.test.tsx` | 重写 | GWT-M11.* |
| `frontend/admin/src/pages/MyOrders.test.tsx` | 修改 | T-09 状态词 |

## 3. 关键实现决策

| 决策 | 内容 | 理由 |
|---|---|---|
| POST `{product}` 无 channel | W2 不要求已选通道 | 设计屏 5；live「去支付」是 GWT-M11.7 |
| 旧 fulfilling 当待支付 | 不渲染「开通处理中」 | expand：旧行不得新造第三套名 |
| 空订单不写金标句 | 只「去结账」 | §0.2 未列本屏 |

## 4. 自测证据

### TDD 红

```
$ cd frontend/admin && CI=true npx jest src/pages/Checkout.test.tsx src/pages/MyOrders.test.tsx --maxWorkers=2
FAIL src/pages/Checkout.test.tsx
  ● GWT-M11.2 … Unable to find role="button" and name "提交开通"
  ● GWT-M11.8 … (旧实现「去支付」/「已有未完成的支付」)
FAIL src/pages/MyOrders.test.tsx
  ● … getByText('待支付') 实际 checkout_pending 原文
  ● empty … 还没有升级申请。
exit: 1
```

（合跑红：15 failed / 14 passed / exit 1，见 T-05 红命令）

### TDD 绿

```
$ cd frontend/admin && CI=true npx jest src/pages/Checkout.test.tsx src/pages/MyOrders.test.tsx --maxWorkers=2
PASS src/pages/Checkout.test.tsx
PASS src/pages/MyOrders.test.tsx
Test Suites: 2 passed, 2 total
Tests:       11 passed, 11 total
exit: 0
```

`bash tools/check/frontend.sh` EXIT:0。F-7 Checkout 210 / MyOrders 58。

### 验收项

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-M11.1 未配通道提交待支付 | unconfigured submit | ✅ |
| GWT-M11.2 打开见商品+提交 | unconfigured open | ✅ |
| GWT-M11.3 经办联系管理员 | operator GET | ✅ |
| GWT-M11.8 已有待支付 | duplicate submit | ✅ |
| GWT-M11.10 无取消 | assertNoForbidden 无取消钮 | ✅ |
| 已开通 ≠ 已确认 | fulfilled renders 已开通 | ✅ |
| 不渲染开通处理中 | paid_pending_fulfillment | ✅ |

### 四类易漏

| 类型 | 结果 |
|---|---|
| 事务回滚 | ➖ N/A |
| 幂等 | 409 已有待支付，不二次 createOrder |
| 并发写 | ➖ UI 不模拟两人同时；后端唯一约束 |
| 外部依赖失败 | preview 5xx → 结账打开失败+重试 |

## 5. 给下游

| 给谁 | 内容 |
|---|---|
| `/qa` | 租户只见待支付/已开通；未配通道打开不是整页「收款通道未开通」 |
| `/backend` | POST `/billing/checkout` W2 应接受无 channel；409 `ORDER_PENDING_EXISTS` |

## 6. 交票自检

- [x] jest + exit
- [x] 无 live 收银台
- [x] 无「当前可买」

## UI · G-fresh r1（QA-01 / QA-03 / QA-05）

> 票：contract §10 T-09｜FR：FR-M11 GWT-M11.1｜角色：/frontend（lane: ui）｜日期：2026-09-14
> 不覆盖 T-06 API 段。本段只记 UI 返工。

### 契约落位

| 契约元素 | 落在哪 | 文件 | 备注 |
|---|---|---|---|
| 未配 pending 金标句 | Checkout Alert description | `Checkout.tsx` `showUnconfiguredPendingCopy` | `can_pay===false` **或** `notice`/`empty_state`=金标句 **或** `channels` 全 `configured=false`；且 pending |
| 「待支付」仍可见 | Alert title | `tenantOrderStatus` | 不因金标句替换闭集词 |
| GWT-M11.1 夹具=GET 真包络 | 测 | `Checkout.test.tsx` | pending：`can_pay: false` + `notice`/`empty_state` 金标句 + `order_id` |
| 渠道组第三套空态 | 删除产品导出 | `relayCopy.ts` | 测仍把该句当禁句 |

**未改 GWT / token / schema。** F-7 Checkout 229 行。无「当前可买」。无 live 收银台。antd Alert 用 `title`/`description`。

### 改动文件

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/pages/Checkout.tsx` | 修改 | pending 金标三信号 OR |
| `frontend/admin/src/pages/Checkout.test.tsx` | 修改 | M11.1 真包络 + notice/全未配 OR 测 |
| `frontend/admin/src/services/billing.ts` | 修改 | `CheckoutPreview.notice` |
| `frontend/admin/src/constants/relayCopy.ts` | 修改 | 删除 `RELAY_EMPTY_GROUPS` |

### TDD 红

```
$ cd frontend/admin && CI=true npx jest --maxWorkers=2 src/pages/Checkout.test.tsx src/pages/RelayGroups.test.tsx
FAIL src/pages/Checkout.test.tsx
  ● GWT-M11.1 pending gold wait from notice when can_pay is not false
    TestingLibraryElementError: Unable to find an element with the text: 收款通道未开通，提交后等待平台确认开通.
    （Alert title 仅「待支付」，无 description）
  ● GWT-M11.1 pending gold wait when all channels configured=false
    TestingLibraryElementError: Unable to find an element with the text: 收款通道未开通，提交后等待平台确认开通.
PASS src/pages/RelayGroups.test.tsx
Test Suites: 1 failed, 1 passed, 2 total
Tests:       2 failed, 24 passed, 26 total
exit: 1
```

### TDD 绿（QA-05 完整命令行）

```
$ cd frontend/admin && CI=true npx jest --maxWorkers=2 src/pages/Checkout.test.tsx src/pages/RelayGroups.test.tsx
PASS src/pages/Checkout.test.tsx
PASS src/pages/RelayGroups.test.tsx
Test Suites: 2 passed, 2 total
Tests:       26 passed, 26 total
Snapshots:   0 total
Time:        5.014 s, estimated 6 s
Ran all test suites matching /src\/pages\/Checkout.test.tsx|src\/pages\/RelayGroups.test.tsx/i.
exit: 0
```

```
$ bash tools/check/frontend.sh
前端工程门禁（F-2/F-3/F-4/F-5/F-6/F-7 已启用；F-1 批次 2 已由 service 归一承接）
==============================================================
✓ 前端工程门禁通过
exit: 0
```

### 验收

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-M11.1 未配提交待支付+金标句 | unconfigured submit（真包络 can_pay false + notice） | ✅ |
| GWT-M11.1 notice/empty_state 信号 | pending gold wait from notice when can_pay is not false | ✅ |
| GWT-M11.1 通道全未配信号 | pending gold wait when all channels configured=false | ✅ |
| GWT-M11.2 打开仍提交开通 | unconfigured open | ✅ |
| 渠道组无第三套空态 | RelayGroups 禁句 queryByText | ✅ |

### 四类易漏

| 类型 | 结果 |
|---|---|
| 事务回滚 | ➖ N/A（UI） |
| 幂等 | ➖ 本轮未改 409 映射 |
| 并发写 | ➖ N/A |
| 外部依赖失败 | ➖ 本轮未改 preview 5xx |

### 给下游

| 给谁 | 内容 |
|---|---|
| `/qa` | pending 金标三信号；M11.1 夹具已对齐 GET；`relayCopy` 不再导出第三套空态 |
| `/backend` | UI 消费 preview.`can_pay` / `notice` / `empty_state` / `channels[].configured`；未读 T-06 API 段 |

### 交票自检

- [x] 红绿命令 + 退出码原样
- [x] 未改 GWT
- [x] 未写 backend Python
- [x] 无「当前可买」
