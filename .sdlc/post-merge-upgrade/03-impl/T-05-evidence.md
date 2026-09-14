# 实现证据 · T-05 旧 POST /orders 不建第二套单

> 票：T-05｜FR 锚点：FR-M10｜角色：/backend｜日期：2026-09-13

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| POST `/billing/orders` 拒建单 | Service | `billing_service.create_order` | 422 `ORDER_STORY_CLOSED` |
| 不改已有结账单 | Service | 零 INSERT | |
| 不报成功 second_story | Service | 不 emit | |

**分层**：☑ Router 未 import ORM

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/billing_service.py` | 修改 | create_order 一律 422 |
| `backend/tests/test_fr_m10_orders_closed.py` | 新增 | GWT-M10.4 |
| PIT-2 若干旧 `/orders` 测 | 修改 | 改守卫同 PR 改测试 |

## 3. 关键实现决策

旧入口不再走线下 pending。文案「请从结账页提交开通」。不 emit `second_checkout_story_submitted`。

## 4. ORM 与 DBML

☑ 无新列。

## 5. 可观测性

入口 `创建订单 | tenant=` 后立即拒绝。

## 6. 自测证据

### Red

```
FAILED test_fr_m10_orders_closed.py::test_gwt_m10_4_legacy_orders_post_creates_no_row
20 failed, 2 passed in 5.83s
exit: 非 0
```

### Green

```
$ uv run pytest -q backend/tests/test_fr_m10_orders_closed.py
..                                                                       [100%]
2 passed

$ uv run pytest -x -q backend/tests
1808 passed, 41 skipped, 8 warnings in 203.94s (0:03:23)
exit: 0
```

| GWT | 测试 | 结果 |
|---|---|---|
| GWT-M10.4 | `test_gwt_m10_4_*` | ✅ 422 零新行；已有 checkout_pending 不变；second_story=0 |

## 7. UI（/frontend 同票）

用量页拆除可提交 `BillingPanel`。升级只「去结账」/满额「申请提升」→ `/billing/checkout?product=plan_pro`。

```
admin Usage+Pricing+UpgradeIntent 21 passed; Checkout+MyOrders 11 passed
bash tools/check/frontend.sh  exit 0
```

## 8–9

NFR：无新性能闸。未接 live 收银台。
