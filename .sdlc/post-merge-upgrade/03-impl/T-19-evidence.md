# 实现证据 · T-19 运营台待支付列表 + 确认

> 票：T-19｜FR 锚点：FR-M31｜角色：/backend｜日期：2026-09-13

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| GET `/billing/admin/orders` | Router | `app/api/v1/billing.py` | `require_platform_admin_or_404` |
| 企业名 + 展示金额 | Service+Schema | `list_pending_orders` / `OrderOut` | `tenant_name`；`amount_yuan`=cents/100 |
| 空列表 | Router | data=`[]` | 空态句属 UI |
| 确认 | Service | T-07 `confirm_paid` CAS | 错金额 `CONFIRM_AMOUNT_MISMATCH`；再确认不叠 |
| 租户直打 | Router | 404 同形 | 确认亦 404 |

## 2. 改动

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/app/api/v1/billing.py` | 修改 | admin list / confirm → 404 守卫 |
| PIT-2 测试 | 修改 | 租户 403 → 404（`test_billing_*` / authz 不在本票文件） |

未接 live 收银。企业档展示分 ≠ 29900（T-07 CAS 已用当前价目）。

## 3. 决策

确认金额核对仍在 T-07：`WHERE id=? AND status='checkout_pending' AND amount_cents=?`（?=该商品当前展示分）。企业档被改成 29900 → 422，单仍 `checkout_pending`。

## 6. 自测

Red：租户 GET admin/orders 403。

Green：

```
$ uv run pytest -q backend/tests/test_fr_m31_ops_console.py
....                                                                     [100%]
4 passed

$ uv run pytest -x -q backend/tests
1845 passed, 41 skipped, 8 warnings in 146.09s (0:02:26)
exit: 0
```

| GWT | 测试 | 结果 |
|---|---|---|
| M31.1 | 列表含企业名 + 专业档 29900/¥299 | ✅ |
| M31.2 | 空 → `[]`（200） | ✅ |
| M31.3 | 租户 list/confirm 404 | ✅ |
| M31.6 | 企业档金额改 29900 拒绝、仍待支付 | ✅ |

M31.4/5 金额/错单 CAS 已由 T-07 `test_fr_m11_confirm.py` 覆盖。空态金标句 UI。

## 8. 给下游

| 给谁 | 内容 |
|---|---|
| `/frontend` | 空列表渲染「暂无待确认收款」；金额用 `amount_yuan` 勿写死 ¥299 |
| `/qa` | 再确认走 T-07 no-op；错单 body `order_id` 不符 422 |

## 9. UI（/frontend 同票）

待确认列表含企业名+展示金额（专业档 ¥299）；空态「暂无待确认收款」；确认失败行仍待确认。

```
admin PlatformOps in W4 六套 63 passed
```
