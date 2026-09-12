# 实现证据 · T-23 失败≠空：超管待确认收款 + 产品事实 Tab（FR-84 GWT-84.3/84.4）

> 票：contract §11 T-23（L4 P0）｜FR 锚点：FR-84（GWT-84.3 越权 404 同形 / GWT-84.4 超管收款失败句）｜角色：frontend admin｜日期：2026-09-11
> 口径：超管待确认收款列表失败 = 「待确认收款列表加载失败。检查网络后重试。」+ 可点重试，**不是**默认「暂无数据」；真 0 = edge-states 钉句「还没有待确认的收款。租户提交线下升级申请后会出现在这里。」；产品事实 Tab 失败/真 0 同走 FR-84 句族；租户直打两查询面 = 缺页同形 404（守卫 T-15/T-29 已落，本票测试钉住两处）。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素（edge-states 待确认收款屏 + 产品事实 Tab 条目） | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| GWT-84.4 收款列表失败句 + 重试 | 组件（LoadFailure error 态） | `frontend/admin/src/pages/PlatformOps.tsx` | 整表替换（含刷新钮区块）；复用 T-17 `components/LoadState.tsx`，句式单一来源，钉句原文照抄 |
| GWT-84.4 重试可点且真拉 | react-query refetch | 同上 | PendingOrdersTab 弃 `useState+useEffect+手写 loading` 改 `useQuery(['pending-orders'])`，与 T-17 改造口径一致 |
| 真 0 空态句（edge-states 钉句） | 组件（LoadEmpty 真 0 态） | 同上 | Table `locale.emptyText` 槽接 `LoadEmpty`；仅成功且 0 行才渲染（失败不回落空表） |
| 产品事实 Tab 失败句/真 0 句（票面第 3 要点） | 页面 react-query 化 | `frontend/admin/src/pages/ProductEvents.tsx` | 旧实现 `catch → setRows([]) + message.error` 即「失败装空」点名缺陷，整除；失败句「产品事实加载失败。检查网络后重试。」+ 重试（有旧数据句置顶旧表保留，T-17 Data 同款）；真 0「还没有产品事实。访客浏览或租户完成动作后会出现在这里。」；失败时「共 N 条」不渲染（不落 共 0 条） |
| 产品事实查询面 applied 语义 | 同上 | 同上 | 输入为草稿、点「查询」落查询键 + invalidate 同键真拉（T-17 Data 同款；旧行为=每击键触发请求） |
| GWT-84.3 租户直打 404 同形 | 路由守卫（既有，零改动） | `App.tsx` MainLayout + `menuConfig.tsx` `PLATFORM_WRITE_KEYS` 含 `/platform-ops` | 两查询面（待确认收款/产品事实）均在本页 Tab 内，整页守卫即覆盖两处；本票测试断言两处 + 空表不出现 |

**分层核对**：☐ N/A（纯前端票）——未动后端、未动 GWT/冻结句/设计 token/LoadState 组件本体；守卫文件零改动。

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/pages/PlatformOps.tsx` | 修改 | PendingOrdersTab react-query 化 + GWT-84.4 失败态 + 真 0 空态（其余 Tab/租户管理/死信队列零改动） |
| `frontend/admin/src/pages/PlatformOps.test.tsx` | 新增 | GWT-84.4 两例（失败句+禁句、重试真拉）+ 真 0 一例 + 产品事实 Tab 失败/真 0 两例 + GWT-84.3 租户 404 同形（断言两查询面）共 6 例 |
| `frontend/admin/src/pages/ProductEvents.tsx` | 修改 | react-query 化（applied 查询键）+ 失败句/真 0 句 + 失败不渲染「共 0 条」；删 toast 装空路径 |
| `frontend/admin/src/pages/ProductEvents.test.tsx` | 修改 | 补 QueryClientProvider 包装（react-query 化适配）；T-12 既有断言零改动保持绿 |

**与票里「会改哪些文件」一致**：☑ 是（票面点名两处查询面 + 测试三例齐）。

**未触碰「不许改的文件」**：☑ 确认（T-17 五屏、T-15/T-29 守卫文件（App.tsx / menuConfig.tsx）、LoadState.tsx、运营台其余 Tab 零改动；无其他屏）。

## 3. 关键实现决策

### 状态语义

| 态 | 待确认收款 Tab | 产品事实 Tab |
|---|---|---|
| 失败（GWT-84.4 / FR-84 句族） | `ordersQuery.isError` → 信息条保留 + 整表替换 `LoadFailure`（重试=refetch）；「刷新」钮随表隐藏（重试即语义等价） | 无旧数据整表替换 `LoadFailure`；有旧数据（翻页/改筛选用 placeholderData 保表）句置顶 + 旧表保留（T-17 Data 同款）；「共 N 条」仅在成功有数据时渲染 |
| 真 0（GWT-84.2 同族） | Table `locale.emptyText` 槽 `LoadEmpty` 钉句「还没有待确认的收款。租户提交线下升级申请后会出现在这里。」 | 同槽钉句「还没有产品事实。访客浏览或租户完成动作后会出现在这里。」 |
| 越权（GWT-84.3） | MainLayout 平台写面守卫（`/platform-ops` ∈ PLATFORM_WRITE_KEYS）：非超管（含未登录）= NotFound「页面不存在或已被移除」整页，两 Tab 均不挂载 | 同上（同页 Tab；edge-states 产品事实权限条同句） |

### 钉句来源

- 全部句子取自 `02-shape/edge-states.md` 待确认收款屏（空/错误/权限三节）与产品事实 Tab 条目（空/错误/权限），未自造句（票面「无则自造」分支未触发）。

### 测试夹具

- 默认激活「租户管理」Tab 喂 1 行——防其空表「暂无数据」留驻 DOM（antd Tabs 惰性挂载+保活）污染跨 Tab 禁句断言。
- GWT-84.3 例复用 App.layout.test 夹具：zustand `useAuthStore.setState`（tenant company admin，`is_platform_admin:false`）+ `window.history.replaceState('/platform-ops')` + 全端点 mock 拒绝（守卫短路，无页面请求）。

## 4. ORM / Schema 对齐

☐ N/A（无后端/数据契约改动；全部走既有 service 函数 `listPendingOrders` / `confirmOrder` / `listProductEvents`）

## 5. 可观测性

☐ N/A（读路径失败改用户可见失败态即本票目的；ProductEvents 删 toast 装空路径，收款确认 toast 行为保持）

## 6. 自测证据

> 命令与退出码原样粘贴。

```
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest src/pages/PlatformOps --maxWorkers=2
PASS src/pages/PlatformOps.test.tsx (24.074 s)
Test Suites: 1 passed, 1 total
Tests:       6 passed, 6 total
Time:        24.46 s, estimated 27 s
exit:0
（票据 success_check 原命令。）

$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest src/pages/PlatformOps src/pages/ProductEvents --maxWorkers=2
PASS src/pages/ProductEvents.test.tsx (9.725 s)
PASS src/pages/PlatformOps.test.tsx (26.702 s)
Test Suites: 2 passed, 2 total
Tests:       7 passed, 7 total
Snapshots:   0 total
Time:        27.316 s
exit:0
（含受 ProductEvents.tsx 改动影响的 T-12 既有例，回归绿。）

$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/admin
Compiled with warnings.（警告全为存量：LogDrawer/RbacManagement/SpiderLogs/services/auth 未用导入——本次四文件零警告）
File sizes after gzip:
  251.32 kB (-2 B)  build/static/js/main.6c85de2d.js
exit:0
```

（实现中第一轮真 0 例失败一次：`findByText` 单点断言拿到 antd Table loading 翻转中被换下的空态节点（jest-dom 报 not in document）；改 `waitFor + getByText` 重试式断言后全绿。）

**行数红线（F-7 ≤400）**：PlatformOps.tsx 284｜PlatformOps.test.tsx 145｜ProductEvents.tsx 116｜ProductEvents.test.tsx 57。

### 验收项逐条对应

| GWT / 票面要点 | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-84.4 收款失败句+重试；非「暂无数据」、非真 0 句 | `GWT-84.4 pending orders failure shows failure sentence + retry, not default 暂无数据` | ✅ |
| GWT-84.4 重试真拉 | `GWT-84.4 retry refetches the pending orders list` | ✅ |
| 真 0（成功且 0 条 pending）空态钉句，非失败句 | `pending orders true zero (200 + 0 pending) shows 还没有待确认的收款 sentence, not failure` | ✅ |
| GWT-84.3 租户直打收款面 = 404 同形，非空表（断言两处之一） | `GWT-84.3 tenant direct hit on /platform-ops is 404 shell for both pending-orders & product-events surfaces`（断言收款 Tab 标签+信息条不在场） | ✅ |
| GWT-84.3 租户直打产品事实面 = 404 同形（断言两处之二） | 同上例（断言产品事实 Tab 标签+查询输入不在场 + 全页无「暂无数据」） | ✅ |
| 产品事实 Tab 失败同 FR-84 句族，不空表冒充 | `product-events tab failure shows FR-84 sentence + retry, not empty-table masquerade` | ✅ |
| 产品事实 Tab 真 0 空态句 | `product-events tab true zero shows 还没有产品事实 sentence, not failure` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（纯前端读路径） | |
| 幂等 | ➖ N/A（同键重点「查询」invalidate 真拉，见 ProductEvents T-12 例回归） | |
| 并发写 | ➖ N/A | |
| 外部依赖失败 | 收款失败两例 + 产品事实失败例（mock reject 驱动失败态） | ✅ |

## 7. NFR 验证

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-03 | 失败不得装空（FR-84） | 收款/产品事实失败态与真 0 态组件测试全绿（见 §6） | jest/jsdom + CI 构建 |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 失败态由 mock reject 驱动（未真连后端）；ProductEvents 查询语义有行为变化：输入为草稿、点「查询」才拉（旧行为=每击键即请求），真环境请重验「输一半不触发请求 + 同键重点真拉」；收款确认动作（confirmOrder）失败路径未加捕获（票面无对应 GWT 行，edge-states「网络不可用，收款没有确认。」属确认动作离线句，不在本票范围） |
| `/qc` | 产品事实「共 N 条」失败时不渲染（防「共 0 条」冒充）；GWT-84.3 两处断言在同一测试例内（两查询面同页同守卫，拆两例会重复渲染整 App） |
| `/architect` | 无契约歧义；收款确认失败句/确认中态是否需补 GWT 行，请 pm 定 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（定向 6/6 + 含 ProductEvents 回归 7/7、构建 exit 0）
- [x] 契约落位表已核对；未动 GWT/钉句/token；守卫与 LoadState 组件零改动
- [x] react-query isError/refetch 驱动（PendingOrdersTab/ProductEvents 两处新改），无 setInterval / 手写 loading 布尔（本票范围内）
- [x] .tsx ≤ 400 行（最大 PlatformOps.tsx 284）
- [x] 只动 T-23 范围；未动 T-17 五屏 / T-15·T-29 守卫 / 其他屏
