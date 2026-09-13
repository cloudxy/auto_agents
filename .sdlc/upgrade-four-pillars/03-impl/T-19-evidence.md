# 实现证据 · T-19 结账页通道选择与空态；买方 POST

> 票：`02-shape/contract.md` §10 T-19｜FR 锚点：FR-U30 FR-U32 FR-U35 FR-U36 FR-U02｜角色：/frontend｜日期：2026-09-12
> 上游：T-16 GET/POST `/billing/checkout` · T-25 屏 11 锁句
> 泳道：ui｜未做 notify 验真｜未改 GWT / schema / tokens

打开结账 ≠ 已买。通道名只用「支付宝」「微信支付」。禁 FR-U24 四字。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| GET `/billing/checkout?product=` | service + page | `services/billing.ts` · `pages/Checkout.tsx` | `plan_pro\|plan_enterprise\|relay` |
| POST `/billing/checkout` | service + mutation | `createCheckout` | 买方 alipay/wechat；不走线下 `createOrder` |
| 两通道未配 | 空态 | 锁句「收款通道未开通」 | GET 200；无「去支付」；不 POST |
| 单通道未配 | 通道 Radio | 旁注「该通道未开通」 | 已配项可去支付 |
| `CHECKOUT_PENDING_EXISTS` 409 | 内联 | 「已有未完成的支付」 | **继续支付**；不建第二笔 |
| `checkout_pending` / 旧 pending | 单据态 | 「待支付」 | 继续支付同一单 |
| `paid_pending_fulfillment` | 警告 Alert | 「支付已到账，开通处理中」 | 无去支付；数字仍开通前 |
| `ORDER_ROLE_NOT_ALLOWED` | 屏 10 | 「请联系本企业管理员开通」 | 经办/只读；不 POST |
| 非法 `plan_ent` | 页内 | 「没有这个商品。」 | 不打 GET |

**分层依赖核对**：☑ 未改 backend Router/ORM ☑ 未接 `/billing/notify` ☑ official 未 import admin ☑ 未写 FR-U24 四字

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/pages/Checkout.tsx` | 修改 | 通道选择 + 空态/待支付/处理中 + 买方 POST |
| `frontend/admin/src/pages/Checkout.test.tsx` | 修改 | GWT-U30/U32/U35 产品码 |
| `frontend/admin/src/services/billing.ts` | 修改 | `createCheckout`；channels 类型 |
| `frontend/admin/src/constants/collectCopy.ts` | 修改 | T-25 结账锁句 |
| `.sdlc/upgrade-four-pillars/03-impl/T-19-evidence.md` | 新增 | 本文件 |

**与票里「会改哪些文件」一致**：☑ 是（admin 结账页 + billing client）

**未触碰「不许改的文件」**：☑ 确认（无 notify；无 Hero；无 GWT/schema/tokens）

## 3. 关键实现决策

GET 给 `order_id` 时再 `GET /billing/orders` 读状态（T-16 preview 无 status 字段，不发明 schema）。`继续支付` 不二次 POST（T-16 无 pay_url / 不调 SDK）。409 才出「已有未完成的支付」。

### 事务 / 幂等 / 并发

➖ N/A UI。二次去支付由后端 UNIQUE + 409 挡住；前端展示锁句。

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| GET/POST checkout | 测里 `retry: false` | 页内重试 | 空态/联系管理员/打开失败句 | 一商品一待支付 |

## 4. ORM 与 DBML 对齐

☑ 未改 ORM / 迁移 / schema.dbml

## 5. 可观测性

无新后端入口。页上不渲染内部枚举名、不写密钥。

## 6. 自测证据

```
$ cd /Users/xuyun/auto_agents/frontend/admin && npm test -- --watchAll=false --silent src/pages/Checkout.test.tsx

> admin@0.1.0 test
> jest --maxWorkers=2 --watchAll=false --silent src/pages/Checkout.test.tsx

PASS src/pages/Checkout.test.tsx
Test Suites: 1 passed, 1 total
Tests:       10 passed, 10 total
Snapshots:   0 total
Time:        2.564 s
EXIT:0
```

```
$ bash tools/check/frontend.sh
前端工程门禁（F-2/F-3/F-4/F-5/F-6/F-7 已启用；F-1 批次 2 已由 service 归一承接）
==============================================================
✓ 前端工程门禁通过
FRONTEND_SH_EXIT:0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-U32.2 两通道未配 | `GWT-U32.2 both channels unconfigured` | ✅ 无去支付、无 POST |
| GWT-U30.1 支付宝 | `GWT-U30.1 buyer selects 支付宝` | ✅ POST alipay；不到注册 |
| GWT-U30.4 微信 | `GWT-U30.4 buyer selects 微信支付` | ✅ POST wechat |
| GWT-U30.2 一待支付 | `GWT-U30.2 POST 409` | ✅ 「已有未完成的支付」 |
| GWT-U32.1 未配通道 | `POST unconfigured wechat` + 旁注 | ✅ 「该通道未开通」非 5xx |
| 单据态 pending | `checkout_pending GET renders 待支付` | ✅ product=relay |
| paid_pending | `paid_pending_fulfillment shows…` | ✅ 无去支付 |
| GWT-U32.3 / U36.2 经办 | `operator/readonly GET ORDER_ROLE_NOT_ALLOWED` | ✅ 联系管理员 |
| GWT-U35 商品码 | plan_pro / plan_enterprise / relay / plan_ent | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（UI 不写库） |
| 幂等 | 409 不建第二笔 | ✅ |
| 并发写 | — | ➖ N/A |
| 外部依赖失败 | 打开失败 / 角色拒绝 / 未配通道 | ✅ |

## 7. NFR

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-U02 | 同一商品 1 笔待支付 | 409 锁句 | jsdom |
| FR-U24 | 无「当前可买」 | Checkout 渲染 + 扫描 | jsdom |

九维：空/加载/错误/权限/边界/离线句已落；通道禁用+旁注不只靠灰色。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | T-16 无 pay_url：201 后停在「待支付」，不假装跳转支付宝/微信。取消支付无 API，未做。 |
| `/backend` | preview 仍无 `status`；前端用 orders 列表映射。 |
| `/architect` | 错误码按 T-16：`CHECKOUT_PENDING_EXISTS` / `BILLING_CHANNEL_UNCONFIGURED`（非 edge-states 表里的 ORDER_* 别名）。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿
- [x] 未改 GWT / schema / tokens
- [x] 无 notify；无「当前可买」；无 SDK 名当按钮
- [x] `.tsx` ≤ 400（Checkout 321）
