# 实现证据 · T-36 一键导入向导 UI（FR-100 UI 半 / ADR-0023）

> 票：contract §11 T-36｜FR 锚点：FR-100（UI 面，GWT-100.1…100.8）｜角色：/frontend｜日期：2026-09-11
> 依赖：T-35 已落 `POST /api/v1/capabilities/import`（multipart file 可重复 或 directory 二选一；同传 422「文件与目录只能二选一」；响应 data：batch_id/origin/status/total/succeeded/failed/skipped/items[{asset_type,name,status,reason?,asset_id?}]/message?）

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| POST /capabilities/import（multipart file / form directory） | service | `frontend/admin/src/services/capabilities.ts`（`importAssets`） | FormData file 可重复；axios 浏览器态自动剥 Content-Type 让浏览器带 multipart boundary；onUploadProgress 透传 |
| 三步向导（选来源→结果清单→完成） | 页面组件 | `frontend/admin/src/pages/market/ImportWizard.tsx` | 解析预览并入结果清单（T-35 单端点无预览 API，packet 口径） |
| 入口仅超管（GWT-100.6 无入口面） | 页面 | `frontend/admin/src/pages/Capabilities.tsx` 页头动作行 | `isPlatformAdmin` 才渲染「导入资产」；租户零入口（隐藏非禁用） |
| 完成后目录可见新资产（未上架） | 页面 | `Capabilities.tsx`（refreshKey）+ `market/CatalogTab.tsx`（refreshKey prop） | 完成时刷新目录 + 切到目录 tab；不跳公开商店 |
| 冻结句 | copy 模块 | `frontend/admin/src/pages/market/importWizardCopy.ts` | edge-states「一键导入向导」屏钉句单源；逐条失败原因=后端成品中文句直出 |

**分层核对**：☑ 未动源/目录 tab 既有结构（CatalogTab 仅加可选 `refreshKey` 触发重载，2 行）☑ 未定义新 token ☑ 未动后端/GWT

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/pages/market/importWizardCopy.ts` | 新增 | 冻结句 + 四类中文化 + 汇总/上传句族 |
| `frontend/admin/src/pages/market/ImportWizard.tsx` | 新增 | 三步向导组件（286 行 ≤400） |
| `frontend/admin/src/services/capabilities.ts` | 修改 | +`importAssets`/`ImportResult`/`ImportItemResult` |
| `frontend/admin/src/pages/Capabilities.tsx` | 修改 | 页头动作行（仅超管）+ 向导挂载 + catalogRefresh |
| `frontend/admin/src/pages/market/CatalogTab.tsx` | 修改 | +可选 `refreshKey` prop 进 load 依赖（结构未动） |
| `frontend/admin/src/pages/Capabilities.import.test.tsx` | 新增 | 9 例组件测试 |
| `Capabilities.{governance,subscribe,command}.test.tsx` | 修改 | mock 工厂补 `importAssets: jest.fn()` |

**与票面一致**：☑（票面允许导入入口放页头动作行；CatalogTab 加 refreshKey 是「完成后目录可见新资产」的最小实现，结构未动，非偏差项）

**未触碰「不许改的文件」**：☑ 确认（源 tab / 目录 tab 既有结构、后端、GWT、token 均未动）

## 3. 关键实现决策

| 决策 | 理由 |
|---|---|
| 解析预览并入结果清单 | T-35 单端点一次返回逐条 status/reason；前端不发明第二套预览态（packet 要点 1→2 顺承） |
| 上传/解析 loading：onUploadProgress 实测 percent（「上传中…{N}%」），percent=100 后切「解析中…」+ 骨架 | 真实数据驱动，不放假进度 |
| 互斥 = 禁用 + 同句提示（「文件与目录只能二选一」） | 客户端先拦，后端 422 同句兜底；不可能同时提交 |
| 逐条失败原因直接渲染后端中文句 | T-35 evidence §8 契约注：reason 已是成品句（含路径逃逸/超大上限句） |
| 网络失败（无 response）→「导入没有开始：网络不可用。」保留所选 + 重试；有 response →「解析失败。{原因或检查文件格式后重试}。」+ 重新选择 | edge-states 钉句；FR-84 失败≠空、给下一步 |
| 完成反馈 = 结果清单行（类型徽标+名称）+ 未上架注记，不 toast 不跳商店 | GWT-100.1 完成反馈含类型与名称；PC-2 不自动上架 |
| mutation 用 async handler（loading+disabled 防重复提交），不引 react-query | 匹配本页既有代码风格（SourceTab/SubscribeModal 同款）；红线「match existing codebase style」 |

## 4. 六态对照（edge-states 一键导入向导屏）

| 态 | 实现 | 测试 |
|---|---|---|
| 加载（上传/解析/导入） | 「上传中…{N}%」→「解析中…」+ Skeleton；按钮 loading+disabled | `导入中 loading 态…` |
| 空·初始未选 | 选择包含 skill/agent/command/plugin 提示句 | 三步流转用例断言 |
| 空·无可导入（100.3） | 「没有可导入的资产。」中性句 + 重新选择（footer），无失败 Alert | `GWT-100.3…` |
| 错误·网络 | 「导入没有开始：网络不可用。」保留所选 + 重试 | `网络失败句保留所选…` |
| 错误·解析 | 「解析失败。{原因或检查文件格式后重试}。」+ 重新选择 | 组件分支（apiErrorMessage fallback） |
| 错误·逐条（100.2/100.5/100.7） | 后端 reason 直出（格式不合法/超大含上限数字/路径逃逸句） | `GWT-100.2/100.5/100.7…` |
| 权限（100.6） | 非超管：页头零入口（隐藏）；直打 404 同形由后端 T-35 保证 | `GWT-100.6…` |
| 边界·部分成功 | 汇总行「成功 N · 失败 N · 跳过 N」+ 逐行状态 | 汇总断言 |
| 边界·幂等（100.8） | skipped 行标「已存在，跳过」，不计失败 | `GWT-100.8…` |
| 边界·四类齐（100.4） | 类型徽标中文化（技能/命令/智能体/插件），图标 @ant-design/icons | `GWT-100.4…` |
| 未上架提示 | 成功批次注记「已导入，未上架。上架请在治理目录操作。」；全文无「已上架」承诺 | 三步流转用例 |

## 5. 自测证据

> 命令与退出码原样粘贴。定向 → 全量 → 构建。

```
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npm test -- --watchAll=false --maxWorkers=2 src/pages/Capabilities.import.test.tsx
PASS src/pages/Capabilities.import.test.tsx
Tests:       9 passed, 9 total
Test Suites: 1 passed, 1 total
exit: 0
（9 例：三步流转/失败原因逐条/跳过标记/越权无入口/空批次/二选一互斥/网络句/loading/四类中文化）

$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npm test -- --watchAll=false --maxWorkers=2
PASS src/pages/Capabilities.import.test.tsx (41.213 s)
Test Suites:        29 passed, 29 total
Tests:              172 passed, 172 total
Snapshots:          0 total
Time:               446.147 s, estimated 490 s
Ran all test suites.
exit: 0
（基线 28 套件/163 测 + 本票 1 套件 9 测 = 29/172）

$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/admin
Compiled successfully（"Compiled with warnings"= 存量 4 文件：LogDrawer/RbacManagement/SpiderLogs/services/auth 的 no-unused-vars，与本票无关）
The build folder is ready to be deployed.
exit: 0
```

### 验收项逐条对应（GWT UI 面）

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-100.1 三步流转/完成反馈含类型与名称/目录未上架新行 | `GWT-100.1 UI 三步流转…` | ✅ |
| GWT-100.2 部分成功逐条中文原因 | `GWT-100.2/100.5/100.7 失败原因逐条呈现…` | ✅ |
| GWT-100.3 空批次中性句 | `GWT-100.3 空批次中性句…`（断言无 alert） | ✅ |
| GWT-100.4 四类中文化 | `GWT-100.4 四类类型中文化…` | ✅ |
| GWT-100.5 超大含上限数字 | 失败原因测试（mock 含「10485760 字节」句直出） | ✅ |
| GWT-100.6 越权无入口 | `GWT-100.6 非超管无导入入口…` | ✅ |
| GWT-100.7 路径逃逸句 | 失败原因测试（「路径指向资产目录之外：evil.md，已拒绝」直出） | ✅ |
| GWT-100.8 跳过标记 | `GWT-100.8 幂等重导行标「已存在，跳过」…` | ✅ |
| 互斥（同传禁用提示） | `文件与目录二选一互斥…`（{directory} 单独成参） | ✅ |
| 网络句保留所选 + 重试 | `网络失败句保留所选，可重试成功` | ✅ |
| 上传/解析 loading | `导入中 loading 态…`（percent 实测走 onUploadProgress，jsdom 无法模拟进度事件，断言统一「导入中…」态） | ✅ |

### 过程记录（flaky 排查）

- 全量首两跑 NewApiOps `GWT-98.4` 60s 超时挂 1 例；本票改动与 NewApiOps 无 import 关系，该测试为**另一在途 lane 的未提交新增**（`git diff` 362 行未提交，T-34 evidence 全量基线 27/155 不含它；其文件内注释自证曾在满载并行下超时被改过）。隔离单跑该套件 11/11 exit 0；本票将新增套件从 271s 减到 ~41s（向导行为直挂 ImportWizard 轻渲染）后，最终两轮全量 29/172 连续 exit 0。未改他票文件。
- 测试断言踩坑（已入 memory）：antd icon/loading 外层 `aria-label` 前缀使按钮 accessible name 变「import 导入资产」「loading 导入中…」→ 正则匹配；独立渲染无 `autoInsertSpace:false` 时两字按钮「重 试」→ `/重\s*试/`。

## 6. 给下游的信息

| 给谁 | 内容 |
|---|---|
| /qa | 三步流转、互斥、网络句、空批次、跳过标记均有组件级 mock 测试；真实 multipart 上传（FormData boundary/大文件 percent）需联调实测；导入产物未上架需在治理目录动作复核 |
| /architect | T-35 无独立「解析预览」端点，向导把预览折叠进结果清单（packet 口径已认可）；若后续要求真预览需回票 |

## 7. 交票自检

- [x] 逐条验收项有测试（命令 + 退出码原样，§5）
- [x] 全量测试绿：29 套件/172 测 exit 0（基线 28/163 + 本票 +1 套件 9 测）
- [x] `npm run build --prefix frontend/admin` exit 0（警告=存量 4 文件，无新增）
- [x] .tsx ≤400 行（ImportWizard 286 / 测试 287 / Capabilities 122 / CatalogTab 100）
- [x] 未动 GWT、token、源/目录 tab 既有结构（CatalogTab 仅 +refreshKey 触发器，2 行）
- [x] 无硬编码色值（分隔线用 theme.useToken().colorBorderSecondary）；图标取自 @ant-design/icons
- [x] antd v6 新 API：Alert `title`、Modal `mask={{closable}}`；未用已弃用的 `List`/`maskClosable`
- [x] 发现的上游问题已回报（NewApiOps GWT-98.4 满载并行 flaky，§5 过程记录）
