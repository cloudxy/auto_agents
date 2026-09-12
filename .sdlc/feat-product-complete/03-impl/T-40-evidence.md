# 实现证据 · T-40 采集方案编辑/删除 UI（FR-103 UI 半）

> 票：FR-103 UI 半（后端 T-39 已落）｜角色：/frontend（sdlc-workflow:frontend）｜lane：L4/ui｜重试：③｜日期：2026-09-11

## 1. 契约落位表（前端 UI 半）

| 契约元素 | 落位 | 文件 | 备注 |
|---|---|---|---|
| `updateDefinitionMeta(name, {title?, description?, params?})` | service 签名 | `frontend/admin/src/services/spiders.ts` | 仅加可选 `params`，存量调用零破坏（全仓唯一调用点在新弹窗组件） |
| api 型 params=`{urls, headers}` | 编辑弹窗 | `EditDefinitionModal.tsx` | 多行文本（每行一个 url）+ Form.List 键值行；空行/空键丢弃 |
| flow 型 params=动态键值 | 编辑弹窗 | 同上 | 按定义现有 params 键动态文本输入；非字符串值 JSON 文本回显 |
| 代码型（web/custom）传 params → 400 | UI 锁定 | 同上 | 锁定句「代码型爬虫请在源码中修改」，不渲染任何 params 控件、payload 不带 params |
| 删除被引用拒绝句（含 #任务号，≤5）原样 | 删除确认弹窗 | `FileTab.tsx` | Popconfirm → 受控 Modal；失败句留弹窗内（`data-testid="delete-reject-reason"`），弹窗不关、无假成功 |
| 编辑/删除守卫=经办（tenant_role ∈ operator/owner/admin） | 操作列 | `FileTab.tsx` | `useAuthStore` + 角色数组判断，RelayGroups 同款写法；非经办不渲染按钮（后端为最终防线） |
| 回显数据源 | `SpiderInfo.params?` | `services/spiders.ts` | 注册表行携带定义级参数，FileTab 合并视图透传 |

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/services/spiders.ts` | 修改 | `updateDefinitionMeta` payload 加 `params?: Record<string, unknown>`；`SpiderInfo` 加 `params?`（回显用）。均为可选附加 |
| `frontend/admin/src/components/spider/EditDefinitionModal.tsx` | 新增 | 编辑弹窗抽件（FileTab 原 343 行贴 F-7 上限，抽件后 337/212 行）：api/flow/代码型三形态参数区；成功句「已保存。后续新任务将使用新定义。」；名称/类型只读回显 |
| `frontend/admin/src/components/spider/FileTab.tsx` | 修改 | ①编辑/删除守卫改经办（原 isAdmin）；②删除 Popconfirm→确认弹窗（拒绝句原样展示）；③合并行透传 params；④顺修本文件既有 `Space direction` 弃用（P-FE-08 fix-on-touch，消除测试台 deprecation 告警） |
| `frontend/admin/src/components/spider/FileTab.test.tsx` | 新增 | 5 测：api/flow/代码型三形态、被引用拒绝句、viewer 越权隐藏 |

**未触碰**：后端文件（packet 禁）、RelayGroups.tsx、GWT/设计 token：无涉及。

## 3. 关键实现决策

- **抽件而非内联**：FileTab.tsx 改前 343 行，内联三形态参数区必破 F-7（≤400 行）红线；编辑弹窗整体抽到 `EditDefinitionModal.tsx`，FileTab 持 `editRow` 状态并在 `onSaved` 后 `loadRows()`。
- **代码型不发 params**：payload 仅在 api/flow 分支携带 params；web/custom 永不带（后端 400 契约在 UI 侧直接锁死入口，而非依赖报错回显）。
- **flow 提交口径**：键集合=定义现有 params 键；每键按文本提交（值为空串保留键，可清值不删键）；无键定义不发 params 字段。
- **删除失败留在弹窗**：`deleteError` state + 受控 Modal，`apiErrorMessage` 取后端信封 message 原样渲染；弹窗保持打开（对齐 RelayGroups「失败≠关闭、无假成功」形态）。
- **非字符串 flow 值回显**：`JSON.stringify` 文本回显，提交按字符串（契约「动态文本输入」口径）。
- **测试定位手法**（沿仓库既有）：行定位 `findByText(name).closest('tr')` + `within(row)`；弹层圈定 `document.querySelector('.ant-modal')`；两字按钮 `/编\s*辑/` 形态断言（无页面级 ConfigProvider autoInsertSpace）。

## 4. 自测证据（命令与退出码原样）

```
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest src/components/spider --maxWorkers=2
PASS src/components/spider/ResultDrawer.test.tsx (5.307 s)
PASS src/components/spider/FileTab.test.tsx (120.433 s)
Test Suites: 2 passed, 2 total
Tests:       7 passed, 7 total
Time:        121.188 s, estimated 127 s
exit:0

$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/admin
Compiled successfully? -> "Compiled with warnings."（警告=存量 4 文件：LogDrawer/RbacManagement/SpiderLogs/auth.ts 未用 import，与本票无关，基线不变）
The project was built assuming it is hosted at /.
exit:0

$ cd /Users/xuyun/auto_agents/frontend/admin && npx eslint src/components/spider/FileTab.tsx src/components/spider/FileTab.test.tsx src/components/spider/EditDefinitionModal.tsx src/services/spiders.ts
（无输出）
exit:0
```

### 验收项逐条对应

| 验收点（packet） | 覆盖的测试 | 结果 |
|---|---|---|
| api 型：入口地址多行 + headers 键值 | `api 型：入口地址多行 + headers 键值回显…`（回显值 + 提交 payload 断言 + 成功句） | ✅ |
| flow 型：按 params 键动态输入 | `flow 型：按 params 键动态文本输入…`（改值后提交动态键值） | ✅ |
| 代码型：锁定句无 params 控件 | `代码型（web）：锁定句 + 无 params 控件…`（锁定句在场 + 三个控件缺席断言 + payload 不带 params） | ✅ |
| 编辑成功句 | api/flow/代码型三测均断言「已保存。后续新任务将使用新定义。」 | ✅ |
| 删除被引用拒绝句原样（含任务号） | `删除被引用：确认弹窗原样展示后端拒绝句（含 #任务号）…`（#101 #102 #103 句逐字 + 弹窗不关 + 无假成功） | ✅ |
| 非经办无编辑/删除按钮 | `非经办（viewer）无编辑/删除按钮`（isAdmin=true 传入仍隐藏，证明守卫=经办非 isAdmin） | ✅ |

### 过程记录

- 首轮后台复跑曾出 1 例 flaky（与 eslint 并行 + 同命令内双 jest 竞争，P-FE-07 负载型超时形态）；此后连续两轮独立全绿（7/7），未复现。
- zsh 无 `PIPESTATUS`（bash 变量），退出码取证改为重定向 + `echo "exit:$?"` 直取。

## 5. 给下游的信息

| 给谁 | 内容 |
|---|---|
| /qa | ①删除拒绝句断言用 mock 信封 message，真实联调需对后端 T-39 实句复核（含 ≤5 任务号截断口径）；②flow 非字符串值（数组/对象）回显为 JSON 文本、提交为字符串，属「动态文本输入」口径，如需保结构编辑请回产品；③平台超管（无 tenant_role）按契约无编辑/删除入口。 |
| /architect | 无契约歧义。`SpiderInfo.params` 为 UI 回显附加字段，若后端注册表未返回则回显为空（不报错），api 编辑首填从空开始。 |

## 6. 交票自检

- [x] evidence 落盘（本文件）
- [x] 定向 jest（spider 目录）exit 0：2 套件 / 7 测（新 5 + 存量 ResultDrawer 2）
- [x] `npm run build --prefix frontend/admin` exit 0（警告=存量 4 文件不变）
- [x] 触碰文件 eslint 0 error 0 warning（新测试用 targeted disable，低于仓库基线错误数）
- [x] 业务文件 ≤400 行（FileTab 337 / EditDefinitionModal 212）
- [x] 未改 GWT/token/后端；未 git commit；未起 dev server；未 spawn 子代理

---

# 实现证据 · T-40 补票 · GWT-103.4 空态冻结句（微票，verify 帽唯一缺口）

> 票：GWT-103.4 UI 半（verify §5.A-1 钉的缺口：FileTab.tsx:266 旧句「未发现爬虫定义」）｜角色：/frontend（sdlc-workflow:frontend）｜lane：L4/ui｜日期：2026-09-11

## 1. 契约落位

| 契约元素（edge-states 屏：采集方案 tab · 空） | 落位 | 文件 | 备注 |
|---|---|---|---|
| 主句「还没有采集方案。」 | 表格 emptyText | `FileTab.tsx` | spec.md GWT-103.4 Then 冻结句，逐字 |
| 说明「创建入口在 AI 采集规划。」 | Empty description 次行（Text secondary） | 同上 | edge-states 钉的下一步说明 |
| 次链「去 AI 采集规划」 | Empty 内 Button type=primary → navigate('/ai') | 同上 | 路由对 menuConfig `/ai`（AI 采集规划）；形态照抄 Users.tsx 空态 CTA 先例 |
| 「不是失败句」 | 测试负断言 | `FileTab.test.tsx` | 旧句「未发现爬虫定义」必须不在场 |

数据半（空可达、不回填 demo、总件数不被混入项顶满）已由 T-41 `test_all_internal_yields_empty_view` 兑现，本票只钉 UI 句面（coverage.md §5.A-1 整改面=一句文案+一测）。

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/components/spider/FileTab.tsx` | 修改 | 266 行 emptyText 换冻结句三件套（主句+说明+次链）；加 `useNavigate`（354 行 ≤400，F-7 保住）；Empty 形态=PRESENTED_IMAGE_SIMPLE + primary CTA（Users.tsx 空态同款） |
| `frontend/admin/src/components/spider/FileTab.test.tsx` | 修改 | renderTab 包 MemoryRouter（FileTab 现 hook 用 navigate，TaskModal.test 同型）；新增 1 测：mock 空列表（items:[] + spiders:[]）断言主句/说明/次链在场 + 旧句缺席 |

**未触碰**：后端、EditDefinitionModal、GWT/token：无涉及。未 git commit、未 spawn 子代理。

## 3. 自测证据（命令与退出码原样）

```
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest src/components/spider --maxWorkers=2
PASS src/components/spider/TaskModal.test.tsx (6.843 s)
PASS src/components/spider/ResultDrawer.test.tsx
PASS src/components/spider/FileTab.test.tsx (63.857 s)
Test Suites: 3 passed, 3 total
Tests:       10 passed, 10 total
Time:        64.422 s, estimated 88 s
exit:0

$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest src/components/spider/FileTab.test.tsx --verbose
  ✓ api 型：入口地址多行 + headers 键值回显；保存提交 params={urls,headers} 并提示新任务句 (13159 ms)
  ✓ flow 型：按 params 键动态文本输入；保存提交动态键值 (17182 ms)
  ✓ 代码型（web）：锁定句 + 无 params 控件；保存不带 params (15845 ms)
  ✓ 删除被引用：确认弹窗原样展示后端拒绝句（含 #任务号），弹窗保持打开无假成功 (6231 ms)
  ✓ 非经办（viewer）无编辑/删除按钮（FR-103 守卫=经办，与 isAdmin 解耦） (2914 ms)
  ✓ 空态（GWT-103.4）：冻结句「还没有采集方案。」+ 说明与次链，旧句不残留 (3843 ms)
Tests:       6 passed, 6 total
exit:0

$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/admin
Compiled with warnings.（存量基线 4 文件未用 import，FileTab 不在警告名单，与本票无关）
The project was built assuming it is hosted at /.
exit:0

$ cd /Users/xuyun/auto_agents/frontend/admin && npx eslint src/components/spider/FileTab.tsx src/components/spider/FileTab.test.tsx
（无输出）
exit:0
```

## 4. 微票自检

- [x] 冻结句逐字：主句/说明/次链均照 edge-states 屏钉句，无自造半句
- [x] 旧句清除有负断言钉住（防回退）
- [x] 定向 jest（spider 目录 3 套件 10 测）exit 0；build exit 0；触碰文件 eslint 0 输出
- [x] FileTab.tsx 354 行 ≤400（F-7）
- [x] evidence 追加落盘（本节）；未改 GWT/token/后端；未 git commit
