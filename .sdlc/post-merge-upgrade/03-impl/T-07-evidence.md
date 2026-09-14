# 实现证据 · T-07 confirm 接结账单 + [SEC-3]

> 票：T-07｜FR 锚点：FR-M11｜角色：/backend｜日期：2026-09-13

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| confirm checkout_pending | Service | `_confirm_checkout` | 不再 ORDER_CONFIRM_OFFLINE_ONLY |
| CAS 本笔+金额 | Repository | `cas_confirm_checkout` | id + status + amount_cents=展示分 |
| 错单 | Router body | `OrderConfirmIn.order_id` | `CONFIRM_ORDER_MISMATCH` |
| 再确认 | Service | status fulfilled/paid no-op | 不叠 |
| 迟到通知 | Repository | `_LATE_FROM` 含 fulfilled | `late_notify_at` |

## 3. 决策

CAS：`UPDATE ... WHERE id=? AND status='checkout_pending' AND amount_cents=?`（?=当前价目展示分）。0 行且非已开通 → `CONFIRM_AMOUNT_MISMATCH`。通道路径验真仍独立；迟到成功在 fulfilled 上只记 late，不履约。

旧 `pending` 线下单仍走 `_confirm_legacy_offline`（expand）。

## 6. 自测

Red：confirm 在线结账单 400 `ORDER_CONFIRM_OFFLINE_ONLY`。

Green：`test_fr_m11_confirm.py` 6 passed；全量 1808 passed exit 0。

| GWT | 测试 | 结果 |
|---|---|---|
| M11.4 | confirm 专业档 | ✅ fulfilled；SKU none |
| M11.5 | 再确认 | ✅ 不叠 |
| M11.6 | 租户自开通 | ✅ 403/404 仍 pending |
| M31.4 | 改金额 | ✅ 422 待支付 |
| M31.5 | body 错单 | ✅ 两单仍 pending |
| M11.11 | 迟到 notify | ✅ late_notify_at；中转未开通 |

## BUG-V03（GWT-M11.18）

企业档与 relay 确认后迟到通道成功通知：`late_notify_at` 有值；SKU 仍 active；配额不叠；relay 令牌数仍 0（不重签）。

```
$ uv run pytest -q backend/tests/test_fr_m11_confirm.py \
    backend/tests/test_fr_m12_fulfill.py \
    backend/tests/test_fr_m11_checkout_pending.py \
    backend/tests/test_fr_m20_outbound_lookup.py
..............................                                           [100%]
30 passed in 7.64s
exit: 0
```

