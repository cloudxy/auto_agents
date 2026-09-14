# 实现证据 · T-17 我的安装空态与 404

> 票：contract §10 T-17｜FR 锚点：FR-M24｜角色：/frontend（lane: ui）｜日期：2026-09-13

## 1. 契约落位表（UI 面）

| 契约元素 | 落在哪 | 文件 | 备注 |
|---|---|---|---|
| 空态金标 | `EMPTY_COPY` | `installsCopy.ts` | 「还没有安装」≠「能力市场未开放」 |
| 可走完 | 既有卸载/信任 | `MyInstalls.tsx` | 无治理七叶 |
| 跨企业 404 同形 | `isNotFoundError` | 渲染 `NotFound` | |

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/pages/installsCopy.ts` | 修改 | 金标句 |
| `frontend/admin/src/pages/MyInstalls.tsx` | 修改 | 404 同形 |
| `frontend/admin/src/pages/MyInstalls.test.tsx` | 修改 | GWT-M24 |
| `frontend/admin/src/utils/httpError.ts` | 新增 | 与成员共用 |

F-7：MyInstalls.tsx 247 行。

## 3. 自测证据

```
$ cd frontend/admin && CI=true npx jest src/pages/MyInstalls.test.tsx --maxWorkers=2
PASS src/pages/MyInstalls.test.tsx
exit: 0
```

| GWT | 测试 | 结果 |
|---|---|---|
| 空态金标 | GWT-M24 empty is 还没有安装 | ✅ |
| ≠市场关闭 | query 能力市场未开放 null | ✅ |
| 无七叶 | 无源 tab / governance-shell | ✅ |
| 跨企业 404 | GWT-M24 cross-tenant 404 | ✅ |
| 可走完 | 既有 GWT-35.1 卸载 | ✅ |

## 4. 给下游

| 给谁 | 内容 |
|---|---|
| `/qa` | 安装空句只「还没有安装」；关闭市场句只货架 |
| `/backend` | 他企安装 id 404 同形 |

## 5. 交票自检

- [x] jest + exit
- [x] 无「当前可买」
- [x] 未做治理七叶
