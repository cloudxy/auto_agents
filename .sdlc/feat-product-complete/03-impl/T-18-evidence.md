# 实现证据 · T-18 无工人：拦住提交 + 「去节点」下一步

> 票：`02-shape/contract.md` §Wave A T-18｜FR 锚点：FR-85（GWT-85.1/85.2/85.3）｜角色：/frontend（admin）｜日期：2026-09-11
> 方式：TDD（companion tdd——先红后绿，两轮输出都在 §5）

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落位 | 文件 | 备注 |
|---|---|---|---|
| GWT-85.1 0 工人 → 横幅 + 「去节点」 | 页组件 | `frontend/admin/src/pages/Spiders.tsx` | 既有 `workerOffline`（isFetched 区分加载中）；Alert 加 `action` |
| 85.1 「去节点」打开节点页 | 页组件 | 同上 | `useNavigate` → `/spiders/nodes`（Nodes 页既有路由） |
| GWT-85.2 提交被拦（未入队、无 toast） | TaskModal | `frontend/admin/src/components/spider/TaskModal.tsx` | 提交时校验（非按钮禁用，加载中不拦）；`workerOffline` 经 props 注入 |
| 85.2 提示句含「去节点」入口 | TaskModal | 同上 | 拦截后弹窗内警示 + 去节点按钮（无「提交后立即可见」支） |
| 节点数来源 | 既有接口 + react-query 缓存共享 | `services/admin.ts` `fetchNodesPage`（queryKey `['spider-nodes']` 与 Nodes 页同键） | 不新增接口 |
| GWT-85.3 只读无提交入口 | 既有角色显隐 | `TaskList`（`canCreate`） | 核对 + 补测试 |
| 文案常量 | `components/spider/copy.ts` | 新增拦截句（不动既有三句） | |

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/pages/Spiders.tsx` | 修改 | 横幅加「去节点」action + navigate；向 TaskModal 传 `workerOffline` |
| `frontend/admin/src/components/spider/TaskModal.tsx` | 修改 | 提交时校验拒绝 + 弹窗内提示句（含去节点） |
| `frontend/admin/src/components/spider/copy.ts` | 修改 | 新增拦截提示句常量 |
| `frontend/admin/src/pages/Spiders.test.tsx` | 修改 | 85.1 横幅+跳转 / 85.3 只读无入口 |
| `frontend/admin/src/components/spider/TaskModal.test.tsx` | 新增 | 85.2 拦截：未入队、无 toast、提示句在场 |

**与票里「会改哪些文件」一致**：✅（页 + TaskModal + copy + 两组件测试，全部在 ui lane）
**未触碰「不许改的文件」**：✅ FileTab（T-40 域）、AlertRulesTab（T-42）未动；`git status` 收尾核对

## 3. 关键实现决策

- **提交时校验（票推荐）而非按钮禁用**：避免误伤节点加载态（0 与未知/加载中区分——`workerOffline = isFetched && total===0`，加载中 false 不拦）。
- **弹窗不关**：被拦时 Modal 保持打开（用户改参数无意义但可取消去节点）；不 toast 成功句。
- **无「提交后立即可见」支**：spec L868 明确不做该支，拦截即唯一分支。
- **拦截优先于字段校验**：0 工人是环境前置错误，先于「请选择爬虫」展示（空表单提交也直接得到去节点提示，不逼用户填完才被告知不能跑）。
- **提示句只在被拦后出现**（`blockedNoWorker` 态，弹窗打开时重置）：页级横幅已做前置预告，弹窗内不重复常态占位。
- react-query 缓存共享：Spiders 与 Nodes 同 queryKey `['spider-nodes']`，不重复拉取。

（事务/幂等/并发 N/A——纯前端票；后端仍为最终防线，未改任何 API）

## 4. 数据契约核对

- 节点接口：`fetchNodesPage` → `GET /spiders/nodes`（既有，Nodes 页同源，queryKey `['spider-nodes']` 双页共享缓存）。✅ 未改 schema、未加字段、未新增接口
- 路由：`/spiders/nodes` 既有（`App.tsx` `spiders/nodes` 子路由 + menuConfig `/spiders/nodes`）。✅
- 改动行数核对：Spiders.tsx 355 行、TaskModal.tsx 214 行（≤400，F-7）✅

## 5. 自测证据（原样粘贴）

### 5.0 红（TDD——实现前，仅新增测试在跑）

```
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest src/pages/Spiders src/components/spider/TaskModal --maxWorkers=2
Test Suites: 2 failed, 2 total
Tests:       2 failed, 4 passed, 6 total
exit: 1

红因（各一）：
- TaskModal GWT-85.2 拦截用例：It looks like undefined was passed instead of a matcher.
  （NO_WORKER_SUBMIT_BLOCKED_COPY 尚不存在于 copy.ts）
- Spiders GWT-85.1 用例：TestingLibraryElementError: Unable to find an accessible element
  with the role "button" and name `/去节点/`（横幅尚无 action）
- GWT-85.3 用例在红轮即绿——既有 canCreate 角色显隐本就在（票述「既有角色显隐核对+测试」）；
  TaskModal 放行用例同绿（提交路径本就通）
```

### 5.1 绿 · 定向

```
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest src/components/spider/TaskModal --maxWorkers=1
Test Suites: 1 passed, 1 total
Tests:       2 passed, 2 total
exit: 0

$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest src/pages/Spiders --maxWorkers=2
（real 2:28.28 · user 133.00s · sys 4.97s）
Test Suites: 1 passed, 1 total
Tests:       4 passed, 4 total
exit: 0

# 85.1 用例重构为「单渲染 + 手动 deferred」（在途→真 0 一镜到底）后复跑两套件：
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest src/pages/Spiders src/components/spider/TaskModal --maxWorkers=2
Test Suites: 2 passed, 2 total
Tests:       6 passed, 6 total
exit: 0
```

### 5.2 全量（两轮 + 归因）

```
# 第一轮全量（maxWorkers=2，机器同时承载多套重套件）：
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest --maxWorkers=2
Test Suites: 5 failed, 27 passed, 32 total
Tests:       7 failed, 179 passed, 186 total
exit: 1
# 失败归因：
# - Spiders「T-18 GWT-85.1」60s 超时 —— 本票用例，双全页渲染对满载敏感；已重构为单渲染（见 5.1 第三跑），随后定向 6/6 绿
# - FileTab×2 / RelayGroups×1 / EnterpriseManagement×1 —— 非本票文件（FileTab=T-40 域、AlertRulesTab=T-42 均未动），小批重跑全绿：
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest src/components/spider/FileTab src/pages/NewApiOps src/pages/RelayGroups src/pages/EnterpriseManagement --maxWorkers=2
Test Suites: 1 failed, 3 passed, 4 total
Tests:       2 failed, 32 passed, 34 total
exit: 1
#   → FileTab / RelayGroups / EnterpriseManagement 三套件全绿（满载超时确认环境性，与 T-36/T-40 会话记录的负载 flake 同族）
# - NewApiOps GWT-98.2/98.4 —— 非本票域（NewApiOps*.tsx 与 spider/copy、Spiders、TaskModal 零 import 交叉）；
#   该 lane 组件（EventsList/newapiShared）在工作树带未提交改动；单套件重跑 1 failed, 10 passed（GWT-98.2）
#   → 移交 open_questions，归该 lane（GWT-98.4 即 memory 记录的满载超时 flake）

# 第二轮全量（85.1 重构后，终验）：
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest --maxWorkers=2
PASS src/pages/Spiders.test.tsx (139.941 s)
PASS src/components/spider/TaskModal.test.tsx (8.287 s)
Test Suites: 1 failed, 31 passed, 32 total
Tests:       1 failed, 185 passed, 186 total
exit: 1
# 唯一红 = NewApiOps GWT-98.2（三跑三红：批跑/单跑/终验全量，稳定红非 flake；非本票域）；
# GWT-98.4 批跑红、单跑与终验全量均绿（负载型 flake）。本票两套件（Spiders/TaskModal）全量内全绿。
```

### 5.2.1 第二轮全量结论

全量 32 套件中 31 绿；本票触碰的两个套件在全量内亦绿。唯一失败 NewApiOps GWT-98.2 与本票零耦合（无 import 交叉、文件未触碰），已在 §6 移交。

### 5.3 构建

```
$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/admin
Compiled with warnings.
File sizes after gzip: …（详见构建日志；exit 0）
exit: 0
```

warning 明细：唯一来源 `src/components/spider/LogDrawer.tsx` Line 4 `'ApiEnvelope' is defined but never used`——**存量、非本票触碰文件**（沿 T-40「警告=存量不变」）。本票 5 个触碰文件零警告（CRA 构建内嵌 eslint 同时通过）。

注：仓库根 node_modules 无独立 eslint 可执行文件、admin 无 lint script（build 是门禁，沿 T-40 memory）；lint 以构建内嵌 eslint 为证。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-85.1 0 工人→横幅+去节点；去节点打开节点页 | `Spiders.test.tsx`「T-18 GWT-85.1」（真 0 才横幅；点击后 /spiders/nodes 探针在场） | ✅ |
| GWT-85.2 提交被拦（未入队、无「正在排队执行」） | `TaskModal.test.tsx`「T-18 GWT-85.2」（runSpider 未调用、无排队 toast、未报成功、提示句在场且含去节点） | ✅ |
| GWT-85.3 只读无提交入口 | `Spiders.test.tsx`「T-18 GWT-85.3」（新增任务/再次运行/收藏全隐藏；刷新读操作仍在） | ✅ |
| 0 与未知/加载中区分（加载中不拦） | 85.1 用例前半（节点在途→无横幅）+ TaskModal 放行用例（workerOffline=false→正常入队+排队 toast） | ✅ |

四类易漏测试（事务/幂等/并发/外部依赖）：➖ N/A（纯前端票；「任务未入队」以 `runSpider` 未被调用为证，见 85.2 用例）

## 6. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 85.1/85.2 的「0 工人」以 fetchNodesPage mock 模拟——真实环境需在 0 在线工人下重验（节点心跳 15s 续约，前端 15s 轮询）；「加载中不拦」依赖 isFetched，断网/接口失败时**不**显示横幅也**不**拦提交（保守放行，后端为最终防线） |
| `/qc` | 拦截用「提交时校验 + 弹窗内提示句」实现（票推荐支），未用按钮禁用；无「提交后立即可见」支（spec L868）；颜色全走 antd Alert/Button 默认 token，未引入硬编码 |
| 协调者 | NewApiOps GWT-98.2 三跑三红（批跑/单跑/终验全量，稳定红）；GWT-98.4 为负载型 flake（批跑红、单跑/全量绿）。均非 T-18 域（零 import 交叉、文件未触碰；该 lane 组件 EventsList/newapiShared 在树上有未提交改动）——需该 lane 认领 |

## 7. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样，§5）
- [x] 定向 jest（Spiders）exit 0（§5.1 第 1/3 跑）；TaskModal 定向 exit 0；两套件合并定向 6/6 exit 0
- [x] `npm run build --prefix frontend/admin` exit 0（§5.3）
- [x] 未改 GWT、未改 schema、未定义 design token（Alert/Button 默认 token）
- [x] .tsx ≤ 400 行：Spiders.tsx 355 / TaskModal.tsx 214（测试文件 199/106）
- [x] 只做 T-18：FileTab（T-40 域）、AlertRulesTab（T-42）未动（git status 核对，二者 dirty 为其他 lane 既有改动，本票 diff 不含）
- [x] 全量：终验 31/32 套件、185/186 测试绿，本票两套件在全量内全绿；唯一红 NewApiOps GWT-98.2 非本票域、三跑三红，已移交 §6

> 动作计划（GWT-98.2 回归修复启动）：定向复现 NewApiOps 单文件红 → 读测试+OverviewChannels 定位「1」缺失根因 → 最小修复 → 定向绿 + build 绿 → 本文件追加「## GWT-98.2 回归修复」节。

## GWT-98.2 回归修复（缺陷票：三跑三红）

**根因（一行）**：测试夹具绝对时间戳 `NOW = '2026-09-11T08:00:00'`（本地时 = 2026-09-11T00:00Z）在真实时钟越过 **2026-09-12 08:00 CST** 后掉出 `Overview3q` 的 24h 窗口过滤（`ts >= Date.now() - DAY_MS`），per-channel 事件计数变 0——纯时间炸弹，非组件回归、非 mock 污染（修证时真实时钟 2026-09-12 08:55 CST，`Date.parse(NOW)=2026-09-11T00:00Z < cutoff=2026-09-11T00:55Z`）。

**诊断链（为何锁定时间窗）**：失败 DOM 里同一渠道行 `4,200 / 5,000`（窗口用量）**正常渲染**——`usedQuota` 快照与 `events24h` 计数在 `Overview3q.tsx` 同一事件循环里装配，且 `usedQuota` 无时间过滤、`events24h` 有 → 唯一分叉点是 24h 窗口判定。时间线互证：T-32/T-36/T-37 绿均在边界时刻之前；红与 T-40/T-42/T-18 改动零关联（该 lane 组件未提交 diff 亦不涉时间/计数语义，已核 git diff）。

**修复面（最小，仅测试夹具一行 + 注释）**：`frontend/admin/src/pages/NewApiOps.test.tsx` 的 `NOW` 改为相对时钟 `new Date(Date.now() - 5 * 60 * 1000).toISOString()`（UTC ISO，跨时域 Date.parse 稳定，恒在 24h 窗内）。组件 `Overview3q`/`OverviewChannels` 零改动——「事件掉出 24h 窗口即不计数」是产品语义（正确行为），不属「对降级态过严断言」；断言 `getByText('1')` 意图不变（事件在窗内必须计数）。全文件 11 用例共用 `NOW`（DEFAULT_EVENT/DEFAULT_PROBE/98.2–98.5 夹具），已核对无任何断言依赖绝对时间文本。

**输出（原样）**：

```bash
# 修复前复现
$ cd frontend/admin && CI=true npx jest src/pages/NewApiOps.test.tsx --maxWorkers=2
Tests:       1 failed, 10 passed, 11 total   # GWT-98.2: Unable to find an element with the text: 1
exit:1

# 修复后定向
$ cd frontend/admin && CI=true npx jest src/pages/NewApiOps.test.tsx --maxWorkers=2
Test Suites: 1 passed, 1 total
Tests:       11 passed, 11 total
exit:0

# 构建
$ npm run build --prefix frontend/admin
Compiled with warnings.   # 警告=存量（LogDrawer/roles 等未触碰文件），本票触碰文件零警告
exit:0
```
