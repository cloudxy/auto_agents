# 实现证据 · T-16 结账创建 / 一待支付 / 未配通道空态 / 角色闸

> 票：`02-shape/contract.md` §10 T-16｜FR 锚点：FR-U30 FR-U32 FR-U35 FR-U36｜角色：/backend｜日期：2026-09-12

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| GET/POST `/api/v1/billing/checkout` | Router | `backend/app/api/v1/billing.py` | 静态段先于 `/orders/{id}` |
| product/channel 闭集 | Schema | `CheckoutCreate` | `plan_pro\|plan_enterprise\|relay` × `alipay\|wechat` |
| 买方 / 超管代付 / 经办只读 | Service | `BillingService._assert_checkout_actor` | 超管 `CHECKOUT_SUPERADMIN_FORBIDDEN`；非买方「请联系本企业管理员开通」 |
| 未配通道空态、一商品一待支付、金额快照 | Service | `preview_checkout` / `create_checkout` | GET 两通道未配 **200** +「收款通道未开通」；POST 同条件 **422** `BILLING_CHANNELS_UNCONFIGURED` |
| 数据读写 | Repository | `order_repository` + 凭据 repo | `relay` 单 `plan_id` NULL；列表 OUTER JOIN plans |
| 错误码 | 统一处理器 | 409 `CHECKOUT_PENDING_EXISTS`；422 通道未配 | 单通道未配：先 pending 再 unpaid |
| 幂等 | UNIQUE `uk_orders_tenant_open_product` | 046 | IntegrityError → 409「已有未完成的支付」 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/repositories/order_repository.py` | 新增 | 开坑点查；租户列表 outerjoin |
| `backend/services/billing_service.py` | 修改 | preview 读已配通道；POST 建 `checkout_pending` |
| `backend/app/api/v1/billing.py` | 修改 | POST `/checkout` |
| `platform_core/schemas/billing.py` | 修改 | `CheckoutCreate` / preview 视图 |
| `backend/tests/test_fr_u30_checkout.py` | 新增 | U30/U32/U35/U36 |
| `backend/tests/test_billing_orders_write_rules.py` | 修改 | PIT-2：50.5 改为未配通道不建单 |

**与票里「会改哪些文件」一致**：☑ PIT-2 同 PR 改 write_rules。

**未触碰「不许改的文件」**：☑ 确认（无 `/billing/notify`；无履约写订阅/SKU；无「当前可买」。）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 插入 `checkout_pending` | 是 | 占 `open_product_slot` |
| 单通道未配：pending→unpaid | 是 | GWT-U32.1 同一笔单据 |
| `payment_failed` 事件 | 否（commit 后） | 失败不挡；独立短会话 |

**事务提交后的操作失败怎么办**：事件 fail-open（既有 emit）。本票不调通道 SDK。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 生成列 `(tenant_id, open_product_slot)` |
| 保证方式 | UNIQUE + IntegrityError |
| 重复 POST | 409「已有未完成的支付」；不建第二笔 |

☑ 未使用「先查后插」当唯一保证

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 两买方同商品同时 POST | UNIQUE | 查开坑行 → 409；否则原样抛 |

☑ 本票无履约 CAS（T-17）

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 无支付网关 | — | — | 未配通道人话空态，不是 500 | N/A |

## 4. ORM 与 DBML 对齐

☑ 新结账写 `product_code` / `order_no` / `channel` / `amount_cents` 快照 / `merchant_id_snapshot`（已配时）。`relay` 的 `plan_id` NULL。未加列。

**未自行加字段/改类型**：☑ 确认。中转标价读 `BILLING.RELAY_PRICE_CENTS`（缺省 0=未标价，拒绝把 0 当可履约价）。

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `preview_checkout` / `create_checkout` 记 tenant/role/product/channel |
| 错误上下文 | 未配 / 开坑冲突 / 超管代付 |
| 脱敏 | 不记凭据明文；事件 props 仅 reason/channel/product |

**日志脱敏核对**：☑ 无密钥 ☑ 无「当前可买」

## 6. 自测证据

```
$ uv run pytest -q backend/tests/test_fr_u30_checkout.py backend/tests/test_billing_orders_write_rules.py
.........................                                                [100%]
25 passed in 8.31s
T16_EXIT:0
```

```
$ uv run pytest -x -q backend/tests
1641 passed, 40 skipped, 7 warnings in 248.26s (0:04:08)
exit: 0
```

```
$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
arch_exit:0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-U30.1 支付宝待支付 | `test_gwt_u30_1_alipay_creates_pending` | ✅ 本票只建 pending，不调 SDK |
| GWT-U30.2 一待支付 | `test_gwt_u30_2_second_pending_409` | ✅ |
| GWT-U30.3 跨租户 | `test_gwt_u30_3_tenant_a_cannot_see_b` | ✅ |
| GWT-U30.4 微信 | `test_gwt_u30_4_wechat_creates_pending` | ✅ |
| GWT-U32.1 单通道未配 | `test_gwt_u32_1_unconfigured_channel_pending_then_unpaid` | ✅ unpaid + `payment_failed`/`unconfigured`；支付宝仍可选 |
| GWT-U32.2 两通道未配 | `test_gwt_u32_2_get_both_unconfigured_200_empty_no_order` + POST 变体 | ✅ GET **200** 空态（保持 N1）；POST **422** 不建单 |
| GWT-U32.3 只读不能配通道 | T-15 `test_gwt_u31_3` | ✅ |
| GWT-U35.1/5/6 商品码 | `test_gwt_u35_1` / `_5` / `_6` | ✅ `plan_pro` / `plan_enterprise` / `relay` |
| GWT-U35.3 / U35.7 / U36.2 | viewer/operator POST+GET | ✅ 联系管理员；不建单 |
| GWT-U36.3 匿名 | `test_gwt_u36_3_anonymous_no_order` | ✅ 401 |
| GWT-U36.4 超管代付 | `test_gwt_u36_4_superadmin_cannot_pay` | ✅ |
| GWT-U36.1 可见选择 | `test_one_channel_unconfigured_other_selectable` | ✅ |
| PIT-2 50.5 | `test_gwt_50_5_online_channel_creates_no_order` | ✅ 未配通道零新行 |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | 两通道未配 POST 零行 | ✅ |
| 幂等 | 二次 POST 409 仍一行 | ✅ |
| 并发写 | UNIQUE 兜底 | ✅ 未做 HTTP gather |
| 外部依赖失败 | 无 SDK；未配通道 422 人话 | ✅ N/A 通道调用（T-17） |

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-U02 | 同一商品最多 1 笔待支付 | 409 + UNIQUE | pytest/SQLite |
| FR-U24 | 可见面无「当前可买」 | 结账响应断言 | pytest |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| T-17 | 已配通道的单停在 `checkout_pending`。不要在 T-16 路径上验真。单通道未配已落到 `unpaid`+`unconfigured`。 |
| T-19 / `/frontend` | GET 200：`channels[].selectable`；两通道未配 `empty_state=收款通道未开通`（**不是 422**）。POST 未配两通道 → 422 `BILLING_CHANNELS_UNCONFIGURED`。POST 已配 → 201 pending。单通道未配 POST → 422 `BILLING_CHANNEL_UNCONFIGURED`「该通道未开通」，单据 unpaid。409「已有未完成的支付」。经办/只读句「请联系本企业管理员开通」。 |
| `/qa` | 选 GET 200 空态而非契约表 422，避免打爆 N1 结账着陆。POST 才 422。 |
| `/architect` | 新增码：`BILLING_CHANNELS_UNCONFIGURED`、`BILLING_CHANNEL_UNCONFIGURED`、`CHECKOUT_PENDING_EXISTS`、`CHECKOUT_SUPERADMIN_FORBIDDEN`、`CHECKOUT_PRICE_MISSING`。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」当唯一保证
- [x] 未实现 notify 验真/履约
- [x] 未写「当前可买」
- [x] 票状态：本 spawn 交付 evidence；orchestrator 更新 state
