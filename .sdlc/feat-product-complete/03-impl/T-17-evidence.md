# 实现证据 · T-17 失败≠空：节点/仪表盘/数据/渠道组/LLM 供应商点名屏（FR-84 GWT-84.1/84.2）

> 票：contract §11 T-17（L4 P0）｜FR 锚点：FR-84（GWT-84.1 失败句+重试 / GWT-84.2 真 0 空态句）｜角色：frontend admin｜日期：2026-09-11
> 口径：五点名屏接口失败 → 「{名称}加载失败。检查网络后重试。」+ 可点重试；**禁止**失败画成「暂无数据 / 暂无在线节点 / 还没有采集结果（当失败时）/ 暂无 LLM 供应商，点击新建」；仪表盘卡片不得用 0 冒充没跑过。真 0 走「还没有…」。渠道组（T-10）/LLM 供应商（T-30）失败态与空态已落，本票核对在位、不重排结构。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素（edge-states §0.2 + 各屏条目） | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 通用失败态：失败句 + 可点「重试」（FR-84 同句式，不发明第二套） | 组件（新增） | `frontend/admin/src/components/LoadState.tsx` | `LoadFailure`（Alert error + 重试）与 `LoadEmpty`（Alert info + 可选动作）；视觉与 RelayGroups/LlmProviders/Users 已落失败态同款；先查 T-30/T-25 无现成组件，故抽此通用件 |
| 节点屏失败句「节点状态加载失败。检查网络后重试。」+ 重试；标题数不落 0 | 页面 | `frontend/admin/src/pages/Nodes.tsx` | react-query `isError` 分支整表替换；`isError` 未分支画空表的旧缺陷修除 |
| 节点屏真 0「还没有在线采集节点。没有在线工人时提交会被拦住，不会出数。」 | 页面 | 同上 | 替换禁句「暂无在线节点（Worker 进程心跳 10s 上报一次）」（把心跳实现细节当空态） |
| 仪表盘统计失败「仪表盘加载失败。检查网络后重试。」+ 重试；卡片不得 0 冒充 | 页面 | `frontend/admin/src/pages/Dashboard.tsx` | `statsQuery.isError` → 内容区（卡片+图+质量区）整体替换为 LoadFailure；旧实现 toast + `stats?.x ?? 0` 即 GWT-84.1 点名缺陷 |
| 仪表盘局部卡失败只卡内错误 + 重试 | 页面 | 同上 | 质量报告失败 → 两张质量卡内 `LoadFailure`（质量概览不受统计卡影响，反之亦然） |
| 仪表盘真 0：引导句 +「近 7 日还没有运行记录。」，不留死胡同句 | 页面 | 同上 | 零任务引导（T-05）保留；Top5「暂无采集结果」、质量区「暂无质量评分数据/暂无质量分布数据」三处死胡同句统一换「近 7 日还没有运行记录。」 |
| 数据中心结果失败「结果加载失败。检查网络后重试。」+ 重试；禁止 catch 变空 | 页面 | `frontend/admin/src/pages/Data.tsx` | 无旧数据整表替换；有旧数据（筛选/翻页刷新失败）句置顶、旧表保留 |
| 数据中心统计卡失败不得 `?? 0` | 页面 | 同上 | `statsQuery.isError` → 统计卡行替换为 LoadFailure（「统计数据加载失败。检查网络后重试。」，{名称}替换属同族句式）；检索区照常工作 |
| 数据中心真 0「还没有采集结果。完成一次采集后会显示在这里。」+「去采集」 | 页面 | 同上 | 表格 emptyText 槽接 `LoadEmpty`；「去采集」→ `/spiders/tasks` |
| 渠道组失败句/空态（GWT-60.4 走 T-10） | 页面 | `frontend/admin/src/pages/RelayGroups.tsx` | **核对在位**：`isError` → 失败句+重试（RelayGroups.test:159）；无组/无令牌空态句（test:138）；零改动 |
| LLM 供应商失败句/空态（走 T-30） | 页面 | `frontend/admin/src/pages/LlmProviders.tsx` | **核对在位**：失败句+重试（LlmProviders.test:229，且断言空态句不在场）；「还没有模型供应商。」（test:211/221）；零改动 |
| React Query isError/refetch 驱动 | 页面 | Dashboard/Data | Dashboard 弃 `useState+useEffect+fetch` 改 `useQuery`（stats/recent/quality 三查询，quality 依赖 recent enabled 门控）；Data 弃手写 loader 改 `useQuery`（stats/registry/results，applied 提交键 + placeholderData 保旧表） |

**分层核对**：☐ N/A（纯前端票）——未动后端、未动 GWT/冻结句/设计 token/运营台(T-23)/Spiders(T-18)/NewApiOps(T-31)。

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/components/LoadState.tsx` | 新增 | FR-84 通用失败/空态组件（LoadFailure/LoadEmpty），句式单一来源 |
| `frontend/admin/src/pages/Nodes.tsx` | 修改 | isError 分支 + 真 0 空态句；删未用导入（消一条存量构建警告） |
| `frontend/admin/src/pages/Nodes.test.tsx` | 新增 | GWT-84.1 两例（失败句+禁句不在场、重试 refetch 生效）+ GWT-84.2 一例（真 0 句） |
| `frontend/admin/src/pages/Dashboard.tsx` | 修改 | react-query 化 + 页级失败态 + 质量卡局部失败态 + 三处死胡同空句换钉句 |
| `frontend/admin/src/pages/Dashboard.test.tsx` | 修改 | 补 QueryClientProvider（react-query 化适配）；保留 T-05 零任务例 + 新增 84.1 两例 + 84.2 一例 |
| `frontend/admin/src/pages/Data.tsx` | 修改 | react-query 化（stats/registry/results）+ 统计卡/结果表失败态 + 真 0 空态（去采集） |
| `frontend/admin/src/pages/Data.test.tsx` | 修改 | 补 QueryClientProvider+MemoryRouter；保留 T-02 两例 + 新增 84.1 两例 + 84.2 一例 |

**与票里「会改哪些文件」一致**：☑ 是（票面点名五屏中的三新例屏 + 通用组件；渠道组/LLM 供应商核对零改动）

**未触碰「不许改的文件」**：☑ 确认（运营台 PlatformOps/ProductEvents(T-23)、Spiders(T-18)、NewApiOps(T-31) 零改动；RelayGroups/LlmProviders 本票零编辑——working tree 中该两文件的改动为 T-10/T-30 既有产物）

## 3. 关键实现决策

### 失败态语义（GWT-84.1）

| 屏 | 失败渲染范围 | 依据 |
|---|---|---|
| 节点 | 卡身内整表替换；标题「共 N 个」只在有数据时出现（失败不落「共 0 个」） | §0.2 + 节点屏错误条 |
| 仪表盘统计 | 页头行保留，数据内容区（卡片+两图+质量区）整体替换 | §0.6 页级加载失败=内容区替换 |
| 仪表盘质量卡 | 卡内错误 + 重试（两张质量卡共用 qualityBody，局部不拖垮整页） | 仪表盘错误条「局部卡失败只卡内错误 + 重试」 |
| 数据中心统计卡 | 卡片行替换（不落 0）；检索区照常 | 边界条「统计卡失败不得 ?? 0」 |
| 数据中心结果表 | 无旧数据整表替换；有旧数据句置顶旧表保留 | 错误条「禁止 catch 变空」+ §加载「刷新保留旧表」 |

### 真 0 语义（GWT-84.2）

- 节点：`nodes.length===0 && !isLoading` → 钉句（无心跳实现细节）。
- 仪表盘：零任务引导（T-05 句不动）+ 图区统一「近 7 日还没有运行记录。」（替换「暂无采集结果/暂无质量评分数据/暂无质量分布数据」三处死胡同——edge-states 明令「不要」）。
- 数据中心：表 emptyText 槽 `LoadEmpty` 钉句 + 「去采集」→ `/spiders/tasks`。
- 渠道组无令牌/无组、LLM 供应商「还没有模型供应商。」：T-10/T-30 已落，核对在位。

### 数据层改造（react-query，无 setInterval）

| 屏 | 查询 | 备注 |
|---|---|---|
| Dashboard | `['admin-stats']` / `['recent-completed-tasks',5]` / `['quality-report',id]`（enabled=有最近完成任务） | recent 失败降级为空数组（辅助入口不拖垮整页，与旧行为一致） |
| Data | `['data-stats']` / `['spider-registry']` / `['data-results', applied]` | applied=已提交条件（点查询/重置/翻页才落键）；`placeholderData:(prev)=>prev` 保旧表；同键重点「查询」经 invalidate 保持真拉；删除后 invalidate 刷新 |

## 4. ORM / Schema 对齐

☐ N/A（无后端/数据契约改动；全部走既有 service 函数）

## 5. 可观测性

☐ N/A（读路径失败改为用户可见失败态即本票目的；无新日志面，删除/导出 toast 保持）

## 6. 自测证据

> 命令与退出码原样粘贴。

```
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest src/pages/Nodes.test.tsx --watchAll=false --maxWorkers=2
Test Suites: 1 passed, 1 total
Tests:       3 passed, 3 total
Time:        3.516 s
exit:0
（实现中第一轮曾有 3 例失败：重试按钮断言 /重试/ 匹配不到——antd 两字按钮 accessible name 插空格（存量坑），改 /重\s*试/ 后全绿。）

$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest src/pages/Dashboard.test.tsx src/pages/Data.test.tsx --watchAll=false --maxWorkers=2
Test Suites: 2 passed, 2 total
Tests:       9 passed, 9 total
Time:        30.24 s
exit:0

$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest src/pages/RelayGroups.test.tsx src/pages/LlmProviders.test.tsx src/App.test.tsx src/App.menu.test.tsx src/App.layout.test.tsx src/pages/Spiders.test.tsx --watchAll=false --maxWorkers=2
Test Suites: 6 passed, 6 total
Tests:       45 passed, 45 total
Time:        67.44 s
exit:0
（T-10/T-30 屏核对 + 渲染 Dashboard 的三个 App 级套件回归——react-query 化未破坏 GWT-82/96/99 断言。）

$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npm test -- --watchAll=false --maxWorkers=2
Test Suites: 25 passed, 25 total
Tests:       143 passed, 143 total
Snapshots:   0 total
Time:        346.805 s
Ran all test suites.
exit:0
（基线 24 套件/134 测 → 25/143：+Nodes 套件 3 例，Dashboard +3，Data +3。）

$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/admin
Compiled with warnings.（警告全为存量五文件：LogDrawer/EnterpriseManagement/RbacManagement/SpiderLogs/services/auth——本次七文件零警告，且 Nodes.tsx 删未用导入消掉一条存量警告，六文件→五文件）
File sizes after gzip: …
The build folder is ready to be deployed.
exit:0

$ bash /Users/xuyun/auto_agents/tools/check/frontend.sh
前端工程门禁（F-2/F-3/F-4/F-5/F-6/F-7 已启用；F-1 批次 2 已由 service 归一承接）
✓ 前端工程门禁通过
exit:0
```

**行数红线（F-7 ≤400）**：LoadState.tsx 40｜Nodes.tsx 114｜Nodes.test.tsx 57｜Dashboard.tsx 321｜Dashboard.test.tsx 91｜Data.tsx 367｜Data.test.tsx 133。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-84.1 节点失败句+重试；非「暂无在线节点」/真 0 句 | `nodes list failure shows failure sentence + retry, not forbidden empty copy` | ✅ |
| GWT-84.1 重试可点且真拉 | `retry button refetches the nodes list` | ✅ |
| GWT-84.1 仪表盘统计失败句+重试；卡片不 0 冒充；非真 0 | `stats failure: failure sentence + retry, no zero cards faking never-ran` | ✅ |
| GWT-84.1 仪表盘局部卡（质量）卡内错误+重试 | `quality report local failure stays card-local with retry, stats still render` | ✅ |
| GWT-84.1 数据中心结果失败句+重试；不落「暂无数据」 | `results load failure: failure sentence + retry, table does not fall to 暂无数据` | ✅ |
| GWT-84.1 数据中心统计卡失败不 `?? 0` | `stats failure: stats cards replaced by failure sentence + retry, results still work` | ✅ |
| GWT-84.1 渠道组（T-10 已落，核对） | `RelayGroups.test.tsx` gwt_84_1 例（禁句断言在位） | ✅ |
| GWT-84.1 LLM 供应商（T-30 已落，核对） | `LlmProviders.test.tsx` 失败例（空态句不在场断言在位） | ✅ |
| GWT-84.2 节点真 0 句非失败句 | `nodes true zero (200 + 0) shows 还没有在线采集节点 sentence, not failure` | ✅ |
| GWT-84.2 仪表盘真 0 引导+图区钉句、无死胡同句 | `true zero keeps onboarding + chart empty sentence, no dead-end 暂无 copy` | ✅ |
| GWT-84.2 数据中心真 0 句 + 去采集 | `true zero results: 还没有采集结果 + 去采集 goes to /spiders/tasks` | ✅ |
| GWT-84.2 渠道组无令牌走 GWT-60.4（核对） | `RelayGroups.test.tsx` 空态例（tokensMessage 句） | ✅ |
| GWT-84.2 LLM 供应商真 0 句（核对） | `LlmProviders.test.tsx` GWT-97.3 例 | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（纯前端读路径） | |
| 幂等 | ➖ N/A | |
| 并发写 | ➖ N/A | |
| 外部依赖失败 | 全部失败态例即本票主体（mock reject × 6 新例 + T-10/T-30 两例核对） | ✅ |

## 7. NFR 验证

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-03 | 失败不得装空（FR-84） | 五点名屏失败态/真 0 态组件测试全绿（见 §6） | jest/jsdom + CI 构建 |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 失败态由 mock reject 驱动（未真连后端）；Dashboard/Data 已 react-query 化，真环境需重验筛选-翻页-刷新链路与删除后 invalidate 刷新；Data 重置/查询同键也 invalidate 真拉（按钮语义保持） |
| `/frontend`(后续票) | 新屏失败/空态请接 `components/LoadState.tsx`（LoadFailure/LoadEmpty），勿再写第三套句式；Wave A 新增屏（GWT-95.5/99.2）同族接入点在此 |
| `/architect` | 数据中心统计卡失败句「统计数据加载失败。检查网络后重试。」、质量卡「质量报告加载失败。」为 {名称} 替换的同族句（edge-states 未逐字钉该两处名称）；若需钉名请回 spec，前端一处常量即可改 |
| `/qc` | Dashboard 图区三处死胡同句（暂无采集结果/暂无质量评分数据/暂无质量分布数据）统一换成钉句「近 7 日还没有运行记录。」（edge-states 明令替换）；质量分布卡在有运行但无评分数据时也显示该句（图区口径），若需区分请回 designer |

## 9. 交票自检

- [x] 验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（定向 3+9+45 例、全量 25 套件/143 例、构建、前端门禁，全 exit 0）
- [x] 未动 GWT/冻结句/设计 token（仅按 edge-states 钉句落位）
- [x] React Query isError/refetch 驱动，无 setInterval / 手写 loading 布尔（三屏改造后）
- [x] .tsx ≤ 400 行（最大 Data.tsx 367）
- [x] 渠道组/LLM 供应商核对在位、零重排；未动 T-18/T-23/T-31 范围
