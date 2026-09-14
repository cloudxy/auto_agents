# 实现证据 · T-06 未配通道可待支付

> 票：T-06｜FR 锚点：FR-M11｜角色：/backend｜日期：2026-09-13

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| POST `/billing/checkout` 201 | Router+Service | `billing.py` / `create_checkout` | channel 可空 |
| 未配通道句 | Router message | `CHECKOUT_UNCONFIGURED_SUBMIT_USER` | |
| channel=NULL 显式 | Service INSERT | `_new_checkout_order` | 禁止省略列撞 offline |
| 一商品一待支付 | UNIQUE + IntegrityError | `open_product_slot` | 409「已有待支付」 |
| 买方角色 | Service | `ORDER_ROLE_NOT_ALLOWED` | |

## 2. 改动

`CheckoutCreate.channel` Optional；`Order.channel` 可空；`047` 去 default；`config/default/billing.yml` RELAY 19900。

## 3. 决策

未配或所选通道不在 configured → `channel=NULL` 仍 201 `checkout_pending`。W2 不写 `unpaid`。冲突靠 UNIQUE，不是只先查后插。

## 6. 自测

Red：未配 POST 仍 422 `BILLING_CHANNELS_UNCONFIGURED`（见 W2 新测 20 failed）。

Green：

```
$ uv run pytest -q backend/tests/test_fr_m11_checkout_pending.py
......                                                                   [100%]

$ uv run pytest -x -q backend/tests
1808 passed, 41 skipped
exit: 0
```

| GWT | 测试 | 结果 |
|---|---|---|
| M11.1 | unconfigured_creates_pending | ✅ 201 + 未配句 + channel NULL |
| M11.2 | open_checkout | ✅ 200 商品可见不建单 |
| M11.3 | operator | ✅ 联系管理员 |
| M11.8 | second | ✅ 409 已有待支付 |
| M11.14/16 | enterprise/relay | ✅ 金额 ≠29900 |

`$ bash tools/check/arch.sh` exit 0

## G-fresh r1（QA-01/02/04）

预览不再写死 `can_pay=True`。未配通道（或 pending.channel 空）→ `can_pay=false`，`empty_state`/`notice`=「收款通道未开通，提交后等待平台确认开通」。POST 201 仍建 pending。重复待支付 code=`ORDER_PENDING_EXISTS`（409「已有待支付」）。`_notice_for` 只映射待支付/已开通，不再下发「支付已到账，开通处理中」「支付未完成，套餐未开通」。

Red：GET 提交后 `can_pay is True`；409 code `CHECKOUT_PENDING_EXISTS`；U33 预览含 live 态句。

Green：

```
$ uv run pytest -q backend/tests/test_fr_m11_checkout_pending.py \
    backend/tests/test_fr_u30_checkout.py \
    backend/tests/test_fr_u02_quota_copy.py::test_gwt_u02_7_buyer_checkout_empty_state_creates_no_order \
    backend/tests/test_billing_orders_write_rules.py \
    backend/tests/test_fr_u33_notify.py
....................................................                     [100%]
52 passed in 8.91s
exit: 0
```

## G-fresh r2（QA-01/02 minor）

`wait_unconfigured` 仅两通道均未配。已配任一通道时，即使 `pending.channel is None` 也不下发金标、不把 `can_pay` 置 false。金标 `empty_state`/`notice` 仅 `pending_open and wait_unconfigured`（无单 GET 不带「提交后等待平台确认开通」）。GWT-M11.1 未配+提交后仍 `can_pay=false` + 金标句。

```
$ uv run pytest -q backend/tests/test_fr_m11_checkout_pending.py \
    backend/tests/test_fr_u30_checkout.py \
    backend/tests/test_fr_u02_quota_copy.py::test_gwt_u02_7_buyer_checkout_empty_state_creates_no_order \
    backend/tests/test_billing_orders_write_rules.py \
    backend/tests/test_fr_u33_notify.py
.....................................................                    [100%]
53 passed in 9.00s
exit: 0
```

## BUG-V02 / BUG-V04（GWT-M11.12 / M11.13）

两买方 ThreadPool 同时 POST 同一商品：待支付 ≤1；409 为 `ORDER_PENDING_EXISTS`「已有待支付」。SQLite 生成列 UNIQUE 弱于 MySQL，真行锁需 `MYSQL_FIDELITY=1`。直打 `/orders/{id}/cancel|unpaid`、PATCH unpaid、DELETE → 404/405/422；单据仍 `checkout_pending`；无「未完成」。无取消 API。

```
$ uv run pytest -q backend/tests/test_fr_m11_checkout_pending.py \
    backend/tests/test_fr_m12_fulfill.py \
    backend/tests/test_fr_m11_confirm.py \
    backend/tests/test_fr_m20_outbound_lookup.py
..............................                                           [100%]
30 passed in 7.64s
exit: 0
```

## SRE SM-8 · 047 `downgrade()`（db-spec §8）

`047.downgrade` 原单行 `DELETE FROM plans WHERE slug='enterprise'` 无 `# 回填`，SM-8 红。按 db-spec §8/§11 改 down（不是只贴注释）：

1. `# 回填` `UPDATE orders SET channel='offline' WHERE channel IS NULL`（禁止未填 NULL 就 `MODIFY NOT NULL`；不删 NULL 通道订单）
2. `# 回填` `plans.pro.quota_json` 写回 040 种子 `20/500000/5000000`（不碰 `tenants.quota`）
3. `# 回填` `DELETE enterprise` 仅当 `orders.plan_id` 与 `tenant_subscriptions.plan_id` 均无引用；有 FK 则保留（不可无痕删）
4. 再 `channel` `NOT NULL DEFAULT 'offline'`

047 真库 `up→down→up` **本 spawn 未跑**（本机 `alembic_version=039` ≠ 046/047）。SM-8 绿 ≠ 回滚已验证。

```
$ bash tools/check/db_migrations.sh
迁移破坏性变更检测（strong_migrations 语义）
==============================================
✓ 迁移破坏性变更检测通过
DBMIG_EXIT:0

$ uv run ruff check backend/alembic/versions/047_w2_channel_null_pro_quota.py
All checks passed!
RUFF_EXIT:0
```

