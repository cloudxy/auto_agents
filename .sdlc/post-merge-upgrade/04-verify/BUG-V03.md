# BUG-V03 · 企业档/relay 已开通后迟到通道通知未测

| 项 | 内容 |
|---|---|
| 严重度 | **major** |
| 违反的 GWT | GWT-M11.18 |
| 发现于 | 覆盖矩阵：迟到只覆盖专业档 `test_gwt_m11_11_late_notify_after_confirm_sets_late_at` |
| 指派 | `/backend` |
| 状态 | open |

## 1. 环境

| 项 | 值 |
|---|---|
| 数据前置状态 | GWT-M11.15 或 GWT-M11.17 已发生（企业档或 relay 已开通） |

## 2. 复现步骤

```
1. 打开 backend/tests/test_fr_m11_confirm.py::test_gwt_m11_11_late_notify_after_confirm_sets_late_at
2. 该测只 checkout(product=plan_pro)，断言 sku_status == none
3. 仓库无 gwt_m11_18 / late_notify + plan_enterprise / relay
```

## 3. 期望 vs 实际

| | 内容 |
|---|---|
| **期望** | 保持已开通；不叠配额；不重签令牌；中转保持已开通 |
| **实际** | 企业档/relay 迟到路径无断言。专业档迟到已测（中转保持未开通） |

## 5. 影响范围

| 项 | 内容 |
|---|---|
| 受影响的用户 | 已开通企业档或中转的租户 |
| 数据是否受损 | 可能重签发令牌或叠配额 |
| 有 workaround 吗 | 无 |

## 7. 关联

| 项 | 内容 |
|---|---|
| 相关缺陷 | 可复用 M11.11 HMAC notify 夹具 |
| 相关 FR | FR-M11 |
