# 实现证据 · T-31 中转站管控三 tab 上提页头行（GWT-98.1）

> 票：contract §11 T-31（Wave A P0）｜FR 锚点：FR-98 第一步（GWT-98.1 = FR-99 §0.10 同规范）｜角色：frontend admin｜日期：2026-09-11
> 口径：本票**只动结构**——三 tab 上提顶栏行、移除页内标题卡、内容区直接开始、为 T-32 预留三问分区容器。总览三问内容（T-32）、立即探测（T-33）、探针/事件 tab 内部数据渲染均不动。机制抽成通用件 `PageHeaderTabs` 供 T-34 六页推广复用。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 三 tab 与欢迎语同一行（GWT-98.1） | 布局+页面 | `frontend/admin/src/components/AdminLayout.tsx` | 顶栏行开槽：页名右侧渲染页面注册的页级 tab（与「欢迎回来」同一 `.ant-layout-header` 行） |
| 页级 tab 注册/回退机制（T-34 复用） | 组件 | `frontend/admin/src/components/layout/PageHeaderTabs.tsx`（新增） | Context 槽位 + `PageHeaderTabs` 组件；无槽位（单测直渲染）时原位回退，tab 可用性不变 |
| 页名唯一标题：移除页内 Card title「LLM 网关值班」 | 页面 | `frontend/admin/src/pages/NewApiOps.tsx` | Card 包裹整体移除；Modal（区块弹窗）保留不受 §0.10 约束 |
| 内容区直接以当前 tab 内容开始 | 页面 | 同上 | pane 容器直排；动作行（刷新，原 Card extra）保留在内容区顶部（GWT-99.3 动作等价） |
| §0.10 布局 token：header 56px / 页名 16/600 / tab 14px 选中 600 / gap 16 / 切换 ≤150ms 透明度无位移 | 布局+组件 | AdminLayout + PageHeaderTabs | token 落 inline style + 组件内 `<style>`（无色值新增）；`content.padding-top/block-gap` 属共享 Content 外框，归 T-34 铺页批（本票最小侵入不动 Content chrome） |
| tab 数据装配/挂载时机不变 | 页面 | 同上 | pane 与原 Tabs 同语义：首次激活才挂载、此后保持（筛选/分页态不丢）；ProbeResults/EventsList/总览渲染零改动 |
| T-32 预留总览三问分区容器（结构位，不填内容） | 页面 | 同上 | `data-testid="overview-3q"`（+ health/channels/events 三子位），空 div 无视觉影响 |
| tab 切换 URL 不同步（可选，不做） | 页面 | 同上 | 状态态 `activeTab`，与原 `defaultActiveKey` 行为一致 |

**分层核对**：☐ N/A（纯前端结构票）——未动任何后端文件、未动 GWT/冻结句/设计 token 定义。

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/components/layout/PageHeaderTabs.tsx` | 新增 | 页级 tab 上提机制（Context 槽位 + 回退渲染 + §0.10 tab/切换 token） |
| `frontend/admin/src/components/AdminLayout.tsx` | 修改 | 顶栏行开槽（56px/16-600/16px gap token）；Provider 包布局树 |
| `frontend/admin/src/pages/NewApiOps.tsx` | 修改 | 移除标题卡 Card；三 tab 经 PageHeaderTabs 上提；动作行 + pane 容器 + 3Q 预留 |
| `frontend/admin/src/pages/NewApiOps.test.tsx` | 修改 | 新增 GWT-98.1 两例（顶栏行集成 + 回退切换）；既有 T-18 三例不动 |

**与票里「会改哪些文件」一致**：☑ 是（NewApiOps.tsx 结构改造 + 测试适配；AdminLayout 槽位为实现 §0.10 顶栏行的必要落点，票面已点名）

**未触碰「不许改的文件」**：☑ 确认（探针/事件 tab 内部组件 `ProbeResults.tsx` / `EventsList.tsx` / `newapiShared.ts` 零改动；未做 T-32 内容、T-33 探测）

## 3. 关键实现决策

### 机制选型（T-34 可复用）

| 方案 | 取舍 |
|---|---|
| AdminLayout 顶栏 Context 槽位 + `PageHeaderTabs` 组件（选定） | 对现有代码侵入最小（AdminLayout +~15 行）；页面一次声明即挂顶栏；T-34 点名页直接复用同组件同 token |
| 页面自 sticky 头对齐顶栏基线 | 需每页自算 56px 基线 + 滚动行为，六页重复，弃 |

- **回退语义**：无 Provider（单测直渲染页面）时 `PageHeaderTabs` 原位渲染 tab——保证既有 T-18 测试与独立渲染不依赖 AdminLayout。
- **pane 挂载语义**：与原 antd Tabs 一致——首次激活才挂载（数据装配时机不变，原 GWT-71.1 单元素断言不破）、激活过即保持（tab 内筛选/分页态不丢，GWT-99.3 等价）；切换仅 display + ≤150ms 透明度（token `tab-switch.motion`，无位移）。
- **App.layout.test 兼容**：`headerTitle()` 取 header 首个 div——页名容器仍为首子（tab 槽位在其内、仅 /newapi 注册时出现）。

### token 落位（edge-states §0.10）

| token | 落点 |
|---|---|
| `page-header.height` 56px | AdminLayout Header inline `height: 56` |
| `page-header.title` 16px/600 | 页名 div inline |
| `page-header.tab` 14px、选中 600 | PageHeaderTabs 内 `<style>`（仅字号/字重，无色值） |
| `page-header.gap` 16px | 槽位容器 `marginLeft: 16` |
| `tab-switch.motion` ≤150ms 透明度、无位移 | `pageTabPaneStyle` + `page-tab-switch-fade` keyframes |
| `content.padding-top/block-gap` 16px | **未动**（共享 Content 外框属全局六页统一面，归 T-34 铺页批；见「给下游」） |

## 4. ORM / Schema 对齐

☐ N/A（无后端/数据契约改动）

## 5. 可观测性

☐ N/A（纯结构票，无新日志面；原有 message 提示零改动）

## 6. 自测证据

> 命令与退出码原样粘贴。

```
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npm test -- --watchAll=false --maxWorkers=2 src/pages/NewApiOps.test.tsx src/App.layout.test.tsx
PASS src/pages/NewApiOps.test.tsx (22.723 s)
PASS src/App.layout.test.tsx
Test Suites: 2 passed, 2 total
Tests:       9 passed, 9 total
exit=0
（实现中第一轮定向曾有 1 例失败：GWT-71.1 `findByText('gpt-4o')` 多元素匹配——pane 急挂载把探针行的 gpt-4o 也挂进 DOM；改为「首次激活挂载、此后保持」的原 Tabs 语义后修绿，数据装配时机与基线一致。）

$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npm test -- --watchAll=false --maxWorkers=2
PASS src/pages/NewApiOps.test.tsx
PASS src/App.layout.test.tsx
（…24 套件逐行 PASS…）
Test Suites: 24 passed, 24 total
Tests:       134 passed, 134 total
Snapshots:   0 total
Time:        333.61 s, estimated 390 s
Ran all test suites.
exit=0

$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/admin
Compiled with warnings.（警告全部为存量：LogDrawer/EnterpriseManagement/Nodes/RbacManagement/SpiderLogs/services/auth——本次改动四文件零警告）
File sizes after gzip:
（The build folder is ready to be deployed.）
exit=0

$ bash /Users/xuyun/auto_agents/tools/check/frontend.sh
前端工程门禁（F-2/F-3/F-4/F-5/F-6/F-7 已启用；F-1 批次 2 已由 service 归一承接）
✓ 前端工程门禁通过
exit=0
```

**行数红线（F-7 ≤400）**：NewApiOps.tsx 315｜NewApiOps.test.tsx 209｜AdminLayout.tsx 90｜PageHeaderTabs.tsx 83。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-98.1 tab 与欢迎语同一行、内容区直接开始、无标题卡 | `page tabs sit in the header row with the welcome text; content starts directly`（AdminLayout+NewApiOps 集成） | ✅ |
| GWT-98.1 无槽位回退可用 + 切换只动内容区 + 旧标题不在场 | `fallback tabs stay usable standalone and switching only toggles content panes` | ✅ |
| T-18 回归（71.1/71.2/71.3 冻结句） | 既有三例不动，全绿 | ✅ |
| FR-96 布局树回归（GWT-96.1/96.2/96.4） | `App.layout.test.tsx` 四例不动，全绿 | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（纯前端） | |
| 幂等 | ➖ N/A | |
| 并发写 | ➖ N/A | |
| 外部依赖失败 | 既有 71.3 降级例（网关不可达）+ DUTY_LOAD_FAILED 例保持 | ✅ |

## 7. NFR 验证

➖ 票面无 NFR 条目。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/frontend`(T-32) | 总览三问容器已留：`data-testid="overview-3q"` + `overview-3q-health/channels/events` 三子位（空 div）；三问内容直接填入子位，删占位即接 |
| `/frontend`(T-33) | 立即探测入口按 edge-states 只进总览渠道行；`activeTab` 状态在 NewApiOps 页内（`onTabChange` 可加受控切换供事件跳转复用） |
| `/frontend`(T-34) | 复用 `components/layout/PageHeaderTabs.tsx`：页面根部放 `<PageHeaderTabs items activeKey onChange>`，内容区用 `pageTabPaneStyle(active)`；顶栏 token 已在 AdminLayout 落（56/16-600/gap16）；**content.padding-top/block-gap 16px 尚未落**（共享 Content 外框 margin '24px 16px'+padding 24 未动，铺页批统一处理，勿逐页私改） |
| `/qa` | App.layout.test 的 `headerTitle()` 依赖「header 首个 div=页名容器」——新增顶栏元素须置于该容器内部或之后，勿前插 |
| `/architect` | 无契约歧义 |

## 9. 交票自检

- [x] 验收项有 evidence（命令 + 退出码）
- [x] 自测全绿（定向 9 例 + 全量 24 套件/134 例 + 构建 + 前端门禁，全 exit 0）
- [x] 未动 GWT/冻结句/设计 token 定义
- [x] 无硬编码色值新增（仅既有 #fff 阴影原样）
- [x] .tsx ≤ 400 行
- [x] 未做 T-32/T-33 范围内容
