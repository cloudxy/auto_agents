# 实现证据 · T-17 通知验真后履约；失败/取消/超时/迟到/重复

> 票：`02-shape/contract.md` §10 T-17｜FR 锚点：FR-U33 FR-U34 FR-U38 [SEC-1]｜角色：/backend｜日期：2026-09-12

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| POST `/billing/notify/{channel}` 无 JWT | Router | `backend/app/api/v1/billing.py` | 静态段，注册在 `/orders/{id}` 之前（PIT-1） |
| 通道闭集 alipay/wechat；报文形状 | Schema | `ChannelNotifyIn` | extra allow；缺校验字段不当真通知 |
| 四要素验真 + 视为通道侧真通知 | Service | `payment_notify_service` + `channel_notify_auth` | 只解密**当前**密文；用户文案不点算法名 |
| 开通按商品码 | Service | `_fulfill_product` | `plan_pro`→订阅专业档；`plan_enterprise`→企业档；`relay`→SKU active。专业档不写中转 |
| 数据读写 / CAS | Repository | `order_repository` CAS；SKU `activate_for_tenant` | `rowcount==0` 停止或迟到 |
| 验真失败 HTTP | Router | 恒 200 `accepted` | 不开通、无 `payment_succeeded` |
| 幂等 | UNIQUE + CAS | 046 已有；应用 `cas_mark_verified/fulfilled` | 重复通知不叠加 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/payment_notify_service.py` | 新增 | 验真、emit、履约一次 |
| `backend/services/channel_notify_auth.py` | 新增 | 当前密钥校验口（测试可构造缺校验伪造报文） |
| `backend/app/api/v1/billing.py` | 修改 | POST `/notify/{channel}`；结账 notice |
| `backend/services/billing_service.py` | 修改 | 处理中/未完成句；`confirm_paid` 拒在线单 |
| `backend/repositories/order_repository.py` | 修改 | 点查 order_no；CAS；populate_existing |
| `backend/repositories/relay_sku_entitlement_repository.py` | 修改 | T-17 写 `activate_for_tenant` |
| `platform_core/schemas/billing.py` | 修改 | `ChannelNotifyIn`；preview `notice` |
| `backend/tests/test_fr_u33_notify.py` | 新增 | U33/U34/U38 |
| `backend/tests/payment_notify_support.py` | 新增 | 配通道/签名夹具 |
| `backend/tests/test_billing_orders_write_rules.py` | 修改 | PIT-2：伪造成功通知保持 pending |

**与票里「会改哪些文件」一致**：☑ PIT-2 同 PR。

**未触碰「不许改的文件」**：☑ 确认（未改 GWT / 046；可见面无「当前可买」；用户响应无算法名。）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| CAS `checkout_pending`→`paid_pending_fulfillment` | 是，先 commit | GWT-U37.7 窗口：事件可查、档位仍开通前 |
| `payment_succeeded` | 否（独立短会话） | 既有 emit；验真后、开通前 |
| 按商品开通 + CAS →`fulfilled` | 是 | CAS 0 行则 rollback 履约写 |

**事务提交后的操作失败怎么办**：emit fail-open。开通失败单据停在 `paid_pending_fulfillment`，重复通知可再履约。无通道 SDK 外呼。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 业务自然键 `order_no`（通道至少一次） |
| 保证方式 | CAS `WHERE status=checkout_pending` / `paid_pending_fulfillment`；`rowcount==0` 再读状态 |
| 重复成功通知 | 已 fulfilled → no-op；不叠配额/SKU |

☑ 未使用「先查后插」当唯一保证

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 两通知同时成功 | CAS verified / fulfilled | 0：读当前；unpaid→`late_notify_at`；fulfilled→停；处理中→再履约 |
| unpaid→fulfilled | CAS 不含 unpaid | 0 行，保持 unpaid |

☑ 所有条件更新的返回行数都有处理

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 无通道 SDK | — | 通道重投由我方幂等 | 验真失败 200 且不开通 | 我方按订单号精确一次开通 |

验真只读当前 `secrets_encrypted`（轮换后旧明文无法过校验）。

## 4. ORM 与 DBML 对齐

☑ 未加列。写 `verified_at` / `paid_at` / `fulfilled_at` / `unpaid_at` / `late_notify_at` / `fail_reason` / `channel_trade_no`，与 046 一致。

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `handle` / `_verify` / `_fulfill` 记 channel/order_no/product；**不记密钥/校验码** |
| 错误上下文 | 缺字段 / 非真通知 / 商户金额订单号不符 / 迟到 |
| 脱敏 | 事件 props 仅 channel/product/tenant_id/reason |

**日志脱敏核对**：☑ 无密钥 ☑ 无 token ☑ 用户文案无算法名 ☑ 无「当前可买」

## 6. 自测证据

```
$ uv run pytest -q backend/tests/test_fr_u33_notify.py
...................                                                      [100%]
19 passed in 4.29s
T17_EXIT:0
```

```
$ uv run pytest -q backend/tests/test_fr_u33_notify.py backend/tests/test_fr_u37_payment_events.py backend/tests/test_billing_orders_write_rules.py
.....................................                                    [100%]
37 passed in 13.35s
```

```
$ uv run pytest -x -q backend/tests
1669 passed, 40 skipped, 7 warnings in 166.58s (0:02:46)
exit: 0
```

```
$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
ARCH_EXIT:0
```

```
$ uv run python /Users/xuyun/.zcode/local-plugins/sdlc-workflow/skills/impl-evidence/scripts/check-layering.py backend/app/api backend/services backend/repositories
✓ 分层依赖检查通过
LAYER_EXIT:0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-U33.1 专业档不开中转 | `test_gwt_u33_1_plan_pro_opens_pro_not_relay` | ✅ 专业档+配额；SKU none；令牌 0 |
| GWT-U33.2 无已付单 | `test_gwt_u33_2_no_paid_order_keeps_plan` | ✅ |
| GWT-U33.3 跨企业 | `test_gwt_u33_3_tenant_b_pay_does_not_open_a` | ✅ |
| GWT-U33.4 微信中转 | `test_gwt_u33_4_relay_wechat_opens_sku_not_plan` | ✅ SKU active；档位不变 |
| GWT-U33.5 开通处理中 | `test_gwt_u33_5_verified_before_fulfill_shows_processing` | ✅ paid_pending +「支付已到账，开通处理中」 |
| GWT-U33.6 重复通知 | `test_gwt_u33_6_duplicate_notify_fulfills_once` | ✅ |
| GWT-U34.1 取消 | `test_gwt_u34_1_cancel_stays_unpaid` | ✅ unpaid +「支付未完成，套餐未开通」 |
| GWT-U34.2 超时 | `test_gwt_u34_2_timeout_not_bought` | ✅ |
| GWT-U34.3 只读标已买 | `test_gwt_u34_3_viewer_cannot_mark_paid` | ✅ confirm 拒；仍 pending |
| GWT-U34.4 迟到成功 | `test_gwt_u34_4_late_success_after_cancel` | ✅ unpaid + `late_notify_at`；无 succeeded |
| GWT-U34.5 通道失败 | `test_gwt_u34_5_channel_error_unpaid` | ✅ |
| GWT-U38.1 四要素通过 | U33.1 / U33.4 | ✅ |
| GWT-U38.2 无待支付 | `test_gwt_u38_2_unknown_order_no_noop` | ✅ |
| GWT-U38.3 缺签名 | `test_gwt_u38_3_missing_sign_stays_pending` | ✅ 伪造 payload |
| GWT-U38.4 金额不符 | `test_gwt_u38_4_amount_mismatch` | ✅ |
| GWT-U38.5 商户不符 | `test_gwt_u38_5_merchant_mismatch` | ✅ |
| GWT-U38.6 订单号不符 | `test_gwt_u38_6_wrong_order_no` | ✅ |
| GWT-U31.5 旧密钥 | `test_rotate_drops_old_secret_cannot_fulfill` | ✅ 只读当前密文 |
| PIT-2 验真失败格 | `test_gwt_50_verify_fail_keeps_checkout_pending` | ✅ |
| 企业档履约 | `test_gwt_u35_enterprise_notify_opens_enterprise` | ✅ 不开中转 |
| confirm 不接在线单 | `test_confirm_cannot_fulfill_online_checkout` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | 伪造/四要素不符零履约 | ✅ |
| 幂等 | `test_gwt_u33_6` 二次通知 | ✅ |
| 并发写 | CAS `rows==0` 分支（迟到/已开通） | ✅ 未做 HTTP gather；约束+CAS |
| 外部依赖失败 | 无 SDK；缺签名 200 不开通 | ✅ |

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-U04 [SEC-1] | 四要素+真通知否则不开通、无 succeeded | U38.3–6 伪造/不符 | pytest/SQLite |
| FR-U24 | 可见面无「当前可买」 | 通知/结账响应断言 | pytest |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| T-22 | 验真通过即 `payment_succeeded`（含开通前窗口）。失败 `payment_failed.reason` 闭集。查询仍 `GET /api/v1/product-events`。 |
| T-19 / `/frontend` | 无 JWT：`POST /api/v1/billing/notify/{alipay\|wechat}`。GET 结账 `notice`：处理中「支付已到账，开通处理中」；unpaid「支付未完成，套餐未开通」。回跳不改档位。 |
| `/qa` | 伪造=缺 `sign` 的成功 JSON。金额/商户不符用**该错误字段**做校验码再投。迟到：先 cancel 再 success。 |
| `/architect` | 新增码 `ORDER_CONFIRM_OFFLINE_ONLY`（线下 confirm 不接在线待支付，ADR-0024）。验真实现用当前密文校验，产品文案不出现算法名。 |
| T-24 / `/sre` | 公开通知 URL 已挂；验真失败 200；密钥不进日志/事件。 |

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
- [x] 条件更新 `rows == 0` 已处理
- [x] 伪造 payload 已测
- [x] 未写「当前可买」
- [x] 票状态：本 spawn 交付 evidence；orchestrator 更新 state
