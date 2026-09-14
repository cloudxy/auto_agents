# BUG-V02 · 两买方同时提交同一商品：无并发用例

| 项 | 内容 |
|---|---|
| 严重度 | **major** |
| 违反的 GWT | GWT-M11.12 |
| 发现于 | 覆盖矩阵：仅有顺序二次提交 M11.8 |
| 指派 | `/backend`（用例）+ `/sre`（MYSQL_FIDELITY） |
| 状态 | open |

## 1. 环境

| 项 | 值 |
|---|---|
| 数据库 | 默认 SQLite；生产 MySQL 8 |
| 数据前置状态 | 企业 A 无待支付；两名 owner/admin |
| 约束 | `orders.uk_orders_tenant_open_product`（生成列 `open_product_slot`） |

## 2. 复现步骤

```
1. 确认 test_fr_m11_checkout_pending.py 只有 test_gwt_m11_8_second_submit_already_pending（串行二次 POST）
2. 无 ThreadPool/asyncio.gather 双 POST
3. 默认 pytest 不设 MYSQL_FIDELITY=1
```

## 3. 期望 vs 实际

| | 内容 |
|---|---|
| **期望** | 两人同时提交专业档 → 只 1 笔待支付；另一人「已有待支付」；禁止「已有未完成的支付」；配额仍为开通前 |
| **实际** | 未构造同时提交。SQLite 库级锁即使补测也不等于 MySQL 行锁 |

## 4. 证据

`platform_core/models/billing.py` UniqueConstraint `tenant_id, open_product_slot`。M11.8 是同一 token 顺序 409。

## 5. 影响范围

| 项 | 内容 |
|---|---|
| 受影响的用户 | 同一企业两名买方 |
| 数据是否受损 | 可能两张待支付 |
| 安全影响 | 无越权；账务重复 |

## 7. 关联

| 项 | 内容 |
|---|---|
| 相关 FR | FR-M11 / NFR-M02 |
| 方言 | ESC-2 同类：SQLite 绿 ≠ MySQL 绿 |
