# 实现证据 · T-15 用量三类数字；只读不能下单

> 票：contract §10 T-15｜FR 锚点：FR-M22｜角色：/frontend（lane: ui）｜日期：2026-09-13

## 1. 契约落位表（UI 面）

| 契约元素 | 落在哪 | 文件 | 备注 |
|---|---|---|---|
| 三类数字 vs 上限 | 卡片 | `Usage.tsx` | 并发/存储/token |
| 0 ≠ 失败 | 真 0 渲染数字 | 不走 loadError | |
| 将满 ≠ 已尽 | 既有 GWT-U02.5 | 将满无「已达配额上限」 | |
| 只读不能下单 | 「去结账」仅买方 | owner/admin | W3 收口：viewer 不再见去结账（W2 GWT-M10.3 改为无钮） |
| 无 BillingPanel | T-05 | 保持拆除 | |

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/pages/Usage.tsx` | 修改 | `buyer` 才渲染去结账 |
| `frontend/admin/src/pages/Usage.test.tsx` | 修改 | GWT-M22 零用量；viewer 无去结账 |

F-7：Usage.tsx 221 行。

## 3. 自测证据

```
$ cd frontend/admin && CI=true npx jest src/pages/Usage.test.tsx --maxWorkers=2
PASS src/pages/Usage.test.tsx
exit: 0
```

| GWT | 测试 | 结果 |
|---|---|---|
| 三类数字 | 既有 FREE/PRO 三数字 | ✅ |
| 0 不是失败 | GWT-M22 zero usage | ✅ |
| 将满≠已尽 | GWT-U02.5 | ✅ |
| 只读不能下单 | GWT-M22 viewer cannot order | ✅ |
| 买方去结账 | GWT-M10.1 | ✅ |

## 4. 给下游

| 给谁 | 内容 |
|---|---|
| `/qa` | 只读用量页无「去结账」；买方仍有 |
| `/frontend` W2 | GWT-M10.3 由「点去结账→联系管理员」改为「无去结账钮」以对齐 FR-M22 |

## 5. 交票自检

- [x] jest + exit
- [x] 无 BillingPanel / 无「当前可买」
