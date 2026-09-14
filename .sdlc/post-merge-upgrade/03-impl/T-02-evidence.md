# 实现证据 · T-02 数据中心空态与导出闸

> 票：contract §10 T-02｜FR 锚点：FR-M02（GWT-M02.1/2/4/5/6）｜角色：/frontend（lane: ui）｜日期：2026-09-13

## 1. 契约落位表（UI 面）

| 契约元素 | 落在哪 | 文件 | 备注 |
|---|---|---|---|
| 空态金标（GWT-M02.2） | LoadEmpty | `Data.tsx` + `EMPTY_RESULTS_COPY` | 「还没有结果，去提交采集」；禁 84.2 旧句 |
| CSV/JSON 仅此（GWT-M02.1/4） | 格式 Select | `Data.tsx` | 无 xlsx 选项；误选走 `EXPORT_XLSX_FAILED` |
| 恰好 100（GWT-M02.5） | 导出 | `utils/dataExport.ts` + `onExport` | 文件 100 数据行；Toast「已导出」 |
| 101 无文件（GWT-M02.6） | `total>100` 或 `EXPORT_ROW_LIMIT` | `onExport` | 「单次最多导出 100 条」；不 `createObjectURL` |
| 旁注 | 工具条 | `Data.tsx` | 「单次最多 100 条」始终可见（设计部分态） |

**9 维自检**：导出 loading「导出中…」；空≠失败；筛选空「没有符合条件的结果」+清除筛选；无新 hex（既有 Statistic `valueStyle` 未在本票改）。

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/constants/collectCopy.ts` | 修改 | `EXPORT_ROW_LIMIT_*` / `EXPORTED_COPY` |
| `frontend/admin/src/utils/dataExport.ts` | 新增 | CSV/blob/闸，压 Data.tsx 行数 |
| `frontend/admin/src/pages/Data.tsx` | 修改 | 101 拒绝出文件；Toast「已导出」 |
| `frontend/admin/src/pages/Data.test.tsx` | 修改 | GWT-M02.2/4/5/6 |

F-7：Data.tsx 387 行。未拆 BillingPanel。跨租户 404 是既有隔离，本票 UI 不新造他企字段。

## 3. 关键实现决策

| 决策 | 内容 | 理由 |
|---|---|---|
| 101 用 `total` 不是静默 slice(0,100) | `exportWindowOverLimit(res.total)` | 列表 `page_size` 上限 100，拿不到第 101 行；静默截断是测绘缺口 |
| Toast 锁「已导出」 | 与按钮「导出」同动词 | 设计 屏 2 成功态 |
| 旁注保留「单次最多 100 条」 | 与 101 错误句「单次最多导出 100 条」分家 | 设计部分态 vs GWT-M02.6 |

## 4. 自测证据

### TDD 红（实现前）

```
$ cd frontend/admin && CI=true npx jest src/pages/Data.test.tsx --maxWorkers=2
（合跑）FAIL src/pages/Data.test.tsx
  ● GWT-M02.5 exactly 100 non-candidate rows: csv file has 100 data rows and toast 已导出
    Expected: "已导出"
    Received: "已导出 100 条结果（CSV）"
  ● GWT-M02.6 101 non-candidate rows: 单次最多导出 100 条 and no file
    Expected: "单次最多导出 100 条"
    Number of calls: 0
Tests:       8 failed, 16 passed, 24 total
exit: 1
```

红因为断言失败（旧 Toast / 静默 100 行出文件），不是 import/夹具。

### TDD 绿

```
$ cd frontend/admin && CI=true npx jest src/pages/Data.test.tsx --maxWorkers=2
Test Suites: 1 passed, 1 total
Tests:       10 passed, 10 total
exit: 0
```

合跑（含本票）：`Tests: 26 passed, 26 total` / `exit: 0`。`bash tools/check/frontend.sh` → `EXIT:0`。

### 验收项

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-M02.1 导出 CSV/JSON | export options have csv/json, no xlsx | ✅ |
| GWT-M02.2 空态 | true zero + never superseded 84.2 | ✅ |
| GWT-M02.3 越权 | — | ➖ 跨企业 404 同形属壳/后端；本页只本企业 `searchResults` |
| GWT-M02.4 xlsx | GWT-M02.4 xlsx is not a successful export format | ✅ |
| GWT-M02.5 100 行 | exactly 100 … 100 data rows and toast 已导出 | ✅ |
| GWT-M02.6 101 无文件 | 101 … 单次最多导出 100 条 and no file | ✅ |

### 四类易漏

| 类型 | 结果 |
|---|---|
| 事务回滚 | ➖ N/A |
| 幂等 | ➖ N/A |
| 并发写 | ➖ N/A |
| 外部依赖失败 | 列表失败≠空（既有 GWT-84.1）；导出 422 `EXPORT_ROW_LIMIT` 无文件 |

## 5. 给下游

| 给谁 | 内容 |
|---|---|
| `/backend` | 101 时请 422 `EXPORT_ROW_LIMIT`（前端已映射）；前端另用 `total>100` 双闸 |
| `/qa` | 空态只金标句；101 无下载；Toast 仅为「已导出」 |

## 6. 交票自检

- [x] jest + exit 原样
- [x] 未实现 xlsx 成功路径
- [x] 无「当前可买」
- [x] F-7 Data.tsx 387 ≤ 400
