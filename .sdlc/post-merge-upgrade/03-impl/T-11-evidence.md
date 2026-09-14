# 实现证据 · T-11 禁「当前可买」「支付已通」

> 票：contract §10 T-11｜FR 锚点：FR-M15 / FR-M50｜角色：/frontend（lane: ui）｜日期：2026-09-13

## 1. 契约落位表（UI 面）

| 契约元素 | 落在哪 | 文件 | 备注 |
|---|---|---|---|
| 访客面机械钉 | 源码 walk + 渲染 | `official/src/frU24CopyScan.test.tsx` | 针=`当前可买` **且** `支付已通` |
| 租户面机械钉 | 源码 walk + 渲染 | `admin/src/frU24CopyScan.test.tsx` | Checkout 打开断言「提交开通」而非未配空页 |
| HMAC/确认≠指纹 | 结账源码 | Checkout 禁 `payment_succeeded` / notify | 夹具单不改口 |

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/frU24CopyScan.test.tsx` | 修改 | 双针；结账渲染「提交开通」 |
| `frontend/official/src/frU24CopyScan.test.tsx` | 修改 | 双针 |
| `frontend/official/src/pages/Pricing.test.tsx` | 修改 | 渲染禁「支付已通」 |
| `frontend/admin/src/pages/Pricing.test.tsx` | 修改 | 同上 |
| `frontend/admin/src/pages/Checkout.tsx` | 修改 | 注释不得含四字（walk 扫到注释） |

## 3. 关键实现决策

| 决策 | 内容 | 理由 |
|---|---|---|
| 测试文件可含针 | walk 跳过 `*.test.*` | 断言本身必须写出禁句 |
| 产品注释也不写四字 | Checkout 头注释已改 | 源码 walk 含注释 |

## 4. 自测证据

### TDD 红

```
$ cd frontend/admin && CI=true npx jest src/frU24CopyScan.test.tsx --maxWorkers=2
FAIL src/frU24CopyScan.test.tsx
  ● GWT-M50/M15 …
    Unable to find role="button" and name "提交开通"
    （当时结账未配通道整页「收款通道未开通」）
exit: 1
```

官方 scan 在实现前针「支付已通」已空（characterization）；结账渲染是本票红因。

### TDD 绿

```
$ cd frontend/admin && CI=true npx jest src/frU24CopyScan.test.tsx src/pages/Pricing.test.tsx --maxWorkers=2
PASS src/frU24CopyScan.test.tsx
PASS src/pages/Pricing.test.tsx
exit: 0

$ cd frontend/official && CI=true npx jest src/frU24CopyScan.test.tsx src/pages/Pricing.test.tsx --maxWorkers=2
PASS src/frU24CopyScan.test.tsx (6.691 s)
PASS src/pages/Pricing.test.tsx (6.938 s)
Test Suites: 2 passed, 2 total
Tests:       10 passed, 10 total
Time:        7.811 s
exit: 0
```

`bash tools/check/frontend.sh` EXIT:0。

合跑 admin Usage+Checkout+MyOrders+scan+Pricing+UpgradeIntent：`Tests: 33 passed, 33 total` / exit 0。

### 验收项

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-M50.1 访客无四字 | official copy scan + Pricing | ✅ |
| GWT-M50.4 租户页无四字 | admin copy scan + Usage/Checkout/MyOrders | ✅ |
| GWT-M15.1 夹具≠支付已通 | scan 禁 notify/payment_succeeded；渲染无「支付已通」 | ✅ |
| GWT-M15.2 无单定价仍去结账 | official Pricing 主钮 | ✅ |

### 四类易漏

| 类型 | 结果 |
|---|---|
| 事务回滚 | ➖ N/A |
| 幂等 | ➖ N/A |
| 并发写 | ➖ N/A |
| 外部依赖失败 | scan 不依赖网关 |

## 5. 给下游

| 给谁 | 内容 |
|---|---|
| `/qa` | 双针机械钉已扩到「支付已通」；确认开通后定价页仍禁四字 |
| `/backend` | 勿在租户信封 message 里回这两句 |

## 6. 交票自检

- [x] jest + exit
- [x] 未印四字、未称支付已通
- [x] 未做 live 收银台
