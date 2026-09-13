# 实现证据 · T-34 页头规范推广六点名页（FR-99 / §0.10）

> 票：contract §11 T-34（Wave A P1，依赖 T-29 已落）｜FR 锚点：FR-99（GWT-99.1/99.2/99.3/99.4）｜角色：frontend admin｜日期：2026-09-11
> 口径：六点名页（LLM 配置 / 中转站管控 / 用户管理 / 采集任务 / AI 采集规划 / 系统设置）移除页内标题卡与装饰横幅、页级 tab 上提顶栏行（复用 T-31 `PageHeaderTabs`）；共享 Content 外框统一 `content.padding-top/block-gap 16px`（T-31 遗留）。各页业务逻辑/数据渲染不动；动作/失败句/只读显隐不回退（99.2/99.3/99.4）。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| §0.10 content.padding-top 16px（顶栏下沿→内容首行） | 布局 | `frontend/admin/src/components/AdminLayout.tsx` | Content 外框 `margin 24→16 / padding 24→'0 24px 24px'` 一次落，全部页面同享 |
| §0.10 content.block-gap 16px | 各页 | 既有 marginBottom/marginTop 16 惯例即 token 值 | 动作行统一 marginBottom 16；Settings 两区块 marginTop 16 |
| GWT-99.1 LLM 配置：移除 h1「LLM 配置」+ Card title「LLM 供应商配置」+ 绿色「当前默认供应商」横幅 | 页面 | `frontend/admin/src/pages/LlmProviders.tsx` | 横幅信息「当前默认供应商：X（model）」并入 T-30 说明句行首行（Text 行非横幅）；「默认」列/未设默认提示行/经办旁注保留（T-30 注记遵守） |
| GWT-99.1 中转站管控：核对 | — | `NewApiOps.tsx`（T-31） | 已合规（无标题卡、三 tab 经 PageHeaderTabs 上提、内容区直接开始），本票零改动 |
| GWT-99.1 用户管理：移除 Card title「用户管理（共/已删除 N 人）」 | 页面 | `frontend/admin/src/pages/Users.tsx` | 计数信息不丢：分页 showTotal「共 N 位用户」同屏承担；筛选行+新建保留为内容区动作行（99.3）；status-filter testid 原样 |
| GWT-99.1+§0.10 采集任务：移除 Card title；五 tab（任务列表/定时任务/采集方案/告警规则/任务模板）上提 | 页面 | `frontend/admin/src/pages/Spiders.tsx` | PageHeaderTabs + pane 首次激活挂载、此后保持（与原 antd Tabs 同语义，tab 内筛选/分页态不丢 99.3）；无工人横幅（FR-85 条件态提示，§0.10 允许）保留在内容区 |
| GWT-99.1 AI 采集规划：移除 Card title「AI 采集」；两 tab 上提 | 页面 | `frontend/admin/src/pages/AiPlans.tsx` | 「新建采集计划」保留为内容区动作行（重置向导+切回向导 tab，99.3）；六态沿用 v2 不动 |
| GWT-99.1 系统设置：移除首 Card title「全局系统设置」（复述页名） | 页面 | `frontend/admin/src/pages/Settings.tsx` | 表单分区直接开始；「修改后立即生效」提示保留为表单上方 Text secondary 说明行（原 #999 内联色改 antd token 语义类，无新增色值）；「Webhook 与通知渠道」= 区块标题（§0.10 允许）保留 |
| GWT-99.2/99.3/99.4 不变式 | 各页 | 上述文件 | 失败句+重试（LlmProviders LIST_LOAD_FAILED / Users FR-84 例）、动作按钮、只读写控件显隐逻辑零改动（仅结构重排）；各页既有相关测试全绿 |
| 五组不重排；菜单不动 | — | `menuConfig` 零改动 | ☑ |

**分层核对**：☑ N/A（纯前端结构票）——未动后端、未动 GWT/冻结句/token 定义、未动菜单树/路由。

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/components/AdminLayout.tsx` | 修改 | Content token：padding-top 16（T-31 遗留铺页批） |
| `frontend/admin/src/pages/LlmProviders.tsx` | 修改 | 移除 h1/标题卡/绿横幅；横幅信息并入说明句行；动作行上移（387 行 ≤400） |
| `frontend/admin/src/pages/Users.tsx` | 修改 | 移除标题卡；筛选/新建保留为内容区动作行（387 行 ≤400） |
| `frontend/admin/src/pages/Spiders.tsx` | 修改 | 五 tab 上提 PageHeaderTabs + visitedTabs pane 语义；移除标题卡（347 行 ≤400） |
| `frontend/admin/src/pages/AiPlans.tsx` | 修改 | 两 tab 上提；新建动作行（120 行 ≤400） |
| `frontend/admin/src/pages/Settings.tsx` | 修改 | 移除复述页名首卡；提示行保留；区块卡保留（170 行 ≤400） |
| `frontend/admin/src/pages/LlmProviders.test.tsx` | 修改 | 标题断言改内容断言（1 例）+ 新增 GWT-99.1/99.4 例（1 例） |
| `frontend/admin/src/pages/Users.test.tsx` | 修改 | 新增 GWT-99.1/99.3 例（1 例） |
| `frontend/admin/src/pages/Spiders.test.tsx` | 修改 | 新增五 tab 切换/pane 状态例（1 例） |
| `frontend/admin/src/pages/AiPlans.test.tsx` | 新增 | GWT-99.1/99.3 两例（tab 上提回退可用、切换只动内容区、新建动作） |
| `frontend/admin/src/pages/Settings.test.tsx` | 新增 | GWT-99.1/99.3/99.4 一例（无标题卡、表单直接开始、动作与提示不丢） |

**与票里「会改哪些文件」一致**：☑ 是（六点名页 + 共享 Content；NewApiOps 核对零改动）。

**未触碰「不许改的文件」**：☑ 确认（`PageHeaderTabs.tsx`/`AdminLayout` 顶栏结构未动，仅 Content 外框；各页业务逻辑/数据渲染/弹窗组件零改动；未动 GWT/冻结句）。

## 3. 关键实现决策

### tab 上提复用机制（T-31 遗产）

| 页 | tab 机制 | pane 语义 |
|---|---|---|
| Spiders（五 tab）/ AiPlans（两 tab） | `<PageHeaderTabs items activeKey onChange>` + `pageTabPaneStyle(active)` | visitedTabs：首次激活才挂载（数据装配时机与原 antd Tabs 一致），此后常挂载 display 切换 + ≤150ms 透明度（GWT-99.3 tab 内状态不丢） |
| Users / LlmProviders / Settings | 无页级 tab（与 edge-states §0.10 表一致） | — |

- **回退语义**：无 AdminLayout 槽位（单测直渲染）时 PageHeaderTabs 原位渲染 tab——Spiders/AiPlans 新测试即走该路径验证可用性。
- **URL/tab 态**：Spiders 原为非受控 Tabs（无 URL 同步），改受控 state 行为等价（默认首 tab）；AiPlans 既有 activeTab 状态保持。

### 横幅信息安置（§0.10「不删信息、不加新横幅」）

| 原横幅/标题 | 安置 |
|---|---|
| LLM 绿色「当前默认供应商：X（model）」 | 说明句行首行 `<Text type="secondary">`（与 DEFAULT_EXPLAIN 同组，GWT-99.4 信息等价；测试断言钉句保持） |
| Users「（共/已删除 N 人）」计数 | 分页 showTotal「共 N 位用户」同屏既有承担 |
| Settings「修改后立即生效」extra | 表单上方 Text secondary 说明行 |
| Spiders 无工人横幅（FR-85）/ LlmProviders 只读 Alert / 失败句 Alert | 条件态提示非装饰横幅，§0.10 允许，原样保留 |

### Content token 落位

`margin: '24px 16px' → '16px 16px 24px'`、`padding: 24 → '0 24px 24px'`：顶栏下沿→内容首行 = 16px（token），左右节奏不变（16+24）；block-gap 由各页既有 16px 间距承担。

## 4. ORM / Schema 对齐

☑ N/A（无后端/数据契约改动）。

## 5. 可观测性

☑ N/A（纯结构票，无新日志面；各页 message 提示零改动）。

## 6. 自测证据

> 命令与退出码原样粘贴。

```
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npm test -- --watchAll=false --maxWorkers=2 src/pages/LlmProviders.test.tsx src/pages/Users.test.tsx src/pages/Spiders.test.tsx src/pages/AiPlans.test.tsx src/pages/Settings.test.tsx src/App.layout.test.tsx
Test Suites: 6 passed, 6 total
Tests:       35 passed, 35 total
exit=0

$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npm test -- --watchAll=false --maxWorkers=2
Test Suites: 27 passed, 27 total
Tests:       155 passed, 155 total
Snapshots:   0 total
Time:        376.257 s, estimated 425 s
exit=0
（基线 25 套件/149 测 → 27/155：+AiPlans/+Settings 两套件，+6 例全为本票 GWT-99 面）

$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/admin
Compiled with warnings.（警告全部为存量五文件：LogDrawer / EnterpriseManagement / RbacManagement / SpiderLogs / services/auth——本票改动文件零警告）
File sizes after gzip:
The build folder is ready to be deployed.
exit=0
（首轮曾 exit=1：Settings.tsx 的 const { Text } 落在 import 之间触发 eslint import/first——移至 import 块后即 0）

$ bash /Users/xuyun/auto_agents/tools/check/frontend.sh
前端工程门禁（F-2/F-3/F-4/F-5/F-6/F-7 已启用；F-1 批次 2 已由 service 归一承接）
✓ 前端工程门禁通过
exit=0
```

**行数红线（F-7 ≤400）**：LlmProviders 387｜Users 387｜Spiders 347｜AiPlans 120｜Settings 170｜AdminLayout 92。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-99.1 LLM 配置（无标题卡/横幅，首屏即业务内容） | LlmProviders.test「page header spec: no in-page title card or banner…」 | ✅ |
| GWT-99.1+99.4 LLM 横幅信息等价呈现（钉句保持） | 同上（`当前默认供应商：主用（claude-sonnet-4-6）` 内容行）+ 既有 GWT-97.1 例 | ✅ |
| GWT-99.1 用户管理 | Users.test「T-34 页头规范…」 | ✅ |
| GWT-99.1+99.3 采集任务五 tab 上提、切换只动内容区、pane 状态不丢 | Spiders.test「T-34 页级 tab 上提…」 | ✅ |
| GWT-99.1+99.3 AI 采集规划两 tab 上提 + 新建动作 | AiPlans.test 两例（新套件） | ✅ |
| GWT-99.1+99.3+99.4 系统设置（无标题卡、动作/提示不丢） | Settings.test（新套件） | ✅ |
| GWT-99.1 中转站管控 | NewApiOps.test 既有 T-31 两例（本票零改动，全量回归绿） | ✅ |
| GWT-99.2 失败句+重试不吞 | LlmProviders.test `list failure…`（GWT-97.3/FR-84）+ Users.test `错误态…`（FR-84）既有例不动，全绿 | ✅ |
| GWT-99.3 动作等价 | 各页动作行断言（新建供应商/刷新/新建用户/新建采集计划/保存并发布）+ NewApiOps 刷新 | ✅ |
| GWT-99.4 只读写控件仍隐藏 | LlmProviders.test 既有 GWT-97.4 / SHAPE-QA-03 两例不动，全绿 | ✅ |
| FR-96 布局树回归 | App.layout.test 四例不动（Content token 改动后全绿） | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（纯前端结构票） | |
| 幂等 | ➖ N/A | |
| 并发写 | ➖ N/A | |
| 外部依赖失败 | 既有 97.3 / FR-84 失败句例保持（GWT-99.2 不变式） | ✅ |

## 7. NFR 验证

➖ 票面无 NFR 条目。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 六页页头已按 §0.10 铺完；肉眼复核点：顶栏行页名+页级 tab 同行、内容首行距顶栏 16px、LLM 页「当前默认供应商」为文字行非绿横幅；tab 切换 pane 常挂载（DOM 内 hidden 元素属预期，非泄漏）。 |
| `/frontend` | Content token 已全局生效（所有页面顶距 48→16px）——未点名页同样受益/受影响，若某页自带头部间距请按 16 口径对齐，勿逐页私改 Content。 |
| `/architect` | 无契约歧义（edge-states §0.10 表与 spec 点名页一一对应）。 |
| `/designer` | Settings「修改后立即生效」由 #999 内联色改 `Text type="secondary"`（token 语义类，视觉近 rgba(0,0,0,0.45)）——非 token 定义变更，如需精确 #999 请回票。 |

## 9. 交票自检

- [x] 验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（定向 6 套件/35 例 + 全量 27 套件/155 例 + 构建 + 前端门禁，全 exit 0）
- [x] 未动 GWT/冻结句/设计 token 定义（横幅钉句「当前默认供应商：X（model）」原样保留）
- [x] 无硬编码色值新增（改动面仅结构与既有样式；Settings 一处既有 #999 → token 语义类）
- [x] .tsx ≤400 行（最大 LlmProviders 387）
- [x] 未动各页业务逻辑/数据渲染；NewApiOps 仅核对零改动；菜单/五组未动
