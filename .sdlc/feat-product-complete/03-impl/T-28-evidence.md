# 实现证据 · T-28 企业管理页增强 UI

> 票：contract §11 T-28（FR-95 UI 半；GWT-95.1/95.2/95.3/95.5/95.7 + GWT-94.2/94.3/94.4 呈现）｜FR 锚点：FR-95（搭 FR-94 守卫句呈现）｜角色：/frontend（admin）｜lane：ui｜日期：2026-09-11
> 上游：T-27 已落（`GET /admin/tenants` 行带 `is_platform_default`；`PATCH /admin/tenants/{id}` 改名/状态 + 平台租户守卫句；冲突 400 句「企业名称不可用: {name}」）。

## 1. 契约落位表（UI 面）

| 契约元素 | 落在哪 | 文件 | 备注 |
|---|---|---|---|
| 平台默认租户标注（GWT-95.3） | 公司名列 Tag | `pages/EnterpriseManagement.tsx` | `is_platform_default` 行显「默认归属」Tag（blue）；种子行名「平台租户」即数据，页内 0 处「AutoAgents」 |
| 改名（GWT-95.1） | 确认弹窗（Modal 表单） | 同上 + `services/enterprise.ts#renameTenant` | PATCH `{name}`；成功 toast「企业名称已更新。」+ `load()` 同真相刷新 |
| 改名冲突呈现 | 弹窗内联红字 | 同上 | 后端 400 句**原样**呈现 + edge-states 内联句「“{名称}”与现有企业或保留名冲突，请更换名称。」两行；弹窗不关、无内码、不 toast（UsersRestore 同款） |
| 平台租户改名入口（GWT-94.2） | 操作列禁用 + 旁注 | 同上 | 按钮 disabled + 可见句「平台租户不可修改名称。」（后端守卫保持兜底） |
| 停用（GWT-95.2） | Popconfirm | 同上 + `setTenantStatus` | 确认句「停用 “{企业名}”？」+ 后果句「停用后该企业用户将无法登录。」；成功 toast「企业已停用。」；状态列中文「已停用」 |
| 再启用（GWT-95.7） | 行内按钮 | 同上 | PATCH `{status:'active'}`；toast「企业已启用。」；双向仅常规企业 |
| 平台租户停用入口（GWT-94.3） | 操作列禁用 + 旁注 | 同上 | disabled + 可见句「平台租户不可停用。」 |
| 无删除企业（GWT-94.4） | 操作列 | 同上 | 常规企业与平台租户都无删除控件（前置冻结，未新增） |
| 归属默认显式化（GWT-95.4 UI 半） | 建号表单文案 | `pages/Users.tsx` | 选项「（平台账户，不挂公司）」→「平台租户（默认归属）」；tooltip/placeholder 同口径改写；提交仍 `tenant_id: null`（**行为不变**，0→platform 映射在 T-27 后端）；归属列回退 Tag「平台」→「平台租户」 |
| 列表失败（GWT-95.5） | T-17 `LoadFailure` 复用 | 同上 | 「企业列表加载失败。检查网络后重试。」+「重试」，失败时不渲染表格（≠空表） |
| 空态 | Table locale | 同上 | 「还没有企业。新建后出现在这里，可修改名称与账户状态。」（edge-states 企业管理屏） |
| 同一真相 | 数据源 | `services/enterprise.ts` | 本页与运营台同打 `GET/PATCH /admin/tenants`（tenant_admin_service 单点）；本页写后 `load()` 刷新，运营台自身加载即同显 |

**同真相口径**：一处写（PATCH 单点在后端 service）、两处读同一端点；未动 PlatformOps（既有停用/配额/续期保持）。

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/pages/EnterpriseManagement.tsx` | 修改 | 公司 tab 增强（359 行 ≤400）；部门 tab 未动 |
| `frontend/admin/src/services/enterprise.ts` | 修改 | `TenantRow` 加 `is_platform_default?`；新增 `renameTenant` / `setTenantStatus` |
| `frontend/admin/src/pages/Users.tsx` | 修改 | 纯文案 4 处（GWT-95.4 显式化），无行为变更 |
| `frontend/admin/src/pages/EnterpriseManagement.test.tsx` | 新增 | 8 例（§6） |

**与票里「会改哪些文件」一致**：☑（票面点名 EnterpriseManagement.tsx 增强 + 建号表单文案；service 扩展为其自然配套）

**未触碰「不许改的文件」**：☑ 确认——后端 0 改动（T-27 已落）；`PlatformOps.tsx` 0 改动；`Content`/布局 0 改动（本页在六点名页之外，按 T-34 全局 16px 顶距口径，不私改 Content；Card+Tabs 页头保持原状）。

## 3. 关键实现决策

- **冲突句呈现取 packet 口径**：票面「冲突 400 句原样呈现」+ edge-states 内联句并存为两行（第一行后端原句、第二行设计内联句）；单源仍在后端，前端不重写第二套映射。判断用前缀 `企业名称不可用`（T-27 单源句族），非 `code` 分支之外的 `message` 全量相等——避免后端句尾变化即断。
- **守卫句旁注而非 Tooltip**：GWT 句要求可见（qa 可断言/朗读）；两句各占一个 `<span style="display:block">`（UsersRestore 先例），`queryByText` 可精确命中。
- **状态列中文标签**：`active→启用 / disabled→已停用 / expired→已到期`（此前渲染英文枚举原值）；「已停用」行展示与运营台同数据同词。
- **离线钉句**：改名/停用/启用统一「网络不可用，企业信息没有保存。」，不发请求、弹窗不关（edge-states 离线）。
- **停用需确认、启用直击**：edge-states 只冻停用确认弹窗与两 toast；启用为轻动作直接执行（无第三套句式）。
- **react-query 未引入本页**：与页面既有 `useState+load` 同构（Users/Members 同款），本票不借机迁移，避免超范围重写。

## 4. ORM 与 DBML 对齐

➖ N/A（UI 票；0 后端/模型改动。`is_platform_default` 为 T-27 已落的服务端计算字段，前端只读）。

## 5. 可观测性

➖ N/A（UI 票；无新增日志面。错误呈现即用户可见面）。

## 6. 自测证据（命令与退出码原样粘贴）

```
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npm test -- --watchAll=false --maxWorkers=2 EnterpriseManagement
（红：实现前，TDD 先行）
Test Suites: 1 failed, 1 total
Tests:       8 failed, 8 total
npm error code 1
exit: 1（npm Lifecycle script `test` failed with error code 1）

$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npm test -- --watchAll=false --maxWorkers=2 EnterpriseManagement
（绿：实现后定向）
Test Suites: 1 passed, 1 total
Tests:       8 passed, 8 total
Time:        71.799 s
exit: 0

$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npm test -- --watchAll=false --maxWorkers=2
Test Suites: 28 passed, 28 total
Tests:       163 passed, 163 total
Time:        505.334 s
exit: 0

$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/admin
Compiled with warnings.（存量 4 文件 6 条 no-unused-vars：LogDrawer/RbacManagement/SpiderLogs/services/auth，与本票无关）
exit: 0
```

基线 27 套件/155 测 → 28 套件/163 测（+1 套件 +8 测，全绿）。

### 验收项逐条对应（UI 半）

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-95.3 平台租户标注 + 无 AutoAgents | `平台默认租户标注：行带「默认归属」Tag…` | ✅ |
| GWT-94.2/94.3 守卫句 + 入口禁用；GWT-94.4 无删除控件 | `平台租户守卫（UI 面）…` | ✅ |
| GWT-95.1 改名成功 + 同显刷新 | `改名成功：弹窗保存 → renameTenant → toast + 列表同显新名` | ✅ |
| GWT-95.1 冲突 400 句原样 + 弹窗不关 + 无内码 | `改名冲突：400 句原样内联呈现…` | ✅ |
| GWT-95.2 停用确认/后果句/状态「已停用」 | `停用：确认弹窗后果句 → setTenantStatus(2, "disabled")…` | ✅ |
| GWT-95.7 再启用 | `再启用：已停用行「启用」→ setTenantStatus(3, "active")…` | ✅ |
| GWT-95.5 列表失败≠空 + 重试 | `列表失败：失败句 + 重试…` | ✅ |
| 空态（edge-states） | `空态：公司 0 → 「还没有企业。」…` | ✅ |
| GWT-95.4 表单文案显式化 | 纯文案改动；Users 套件全量回归绿（无行为断言变化） | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（UI 票，无多步写） | |
| 幂等 | ➖ N/A（改名同值后端 no-op；UI 不重复提交面） | |
| 并发写 | ➖ N/A（单端点串行写，守卫在后端单点） | |
| 外部依赖失败 | `GWT-95.5 列表失败` + `改名冲突`（axios 形态 400 rejection）+ 离线钉句（断言不发请求） | ✅ |

## 7. NFR 验证

➖ 本票无 NFR 行（NFR-03 失败≠空由 GWT-95.5 覆盖）。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | ① 守卫句 UI 面为禁用+旁注，直打 API 的拒绝句仍以后端为金标（T-27）；② 冲突呈现为「后端原句 + 设计内联句」两行，如与 edge-states 单句口径有出入，以两行齐备为过；③ 部门 tab 空态仍为表格默认文案（票面未含，未动）；④ 两处同显=同端点各自刷新，非跨页实时推送（契约即此口径）。 |
| `/architect` | 无契约歧义。`Users.tsx` 归属回退 Tag「平台」→「平台租户」是 §0.4 命名收口的顺手纯文案（无行为变化）。 |
| `/designer` | 启用动作未加确认弹窗（edge-states 未冻该形态）；平台租户守卫两句以两行旁注呈现（操作列内）。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样；红→绿双输出）
- [x] 自测全绿（定向 8/8；全量 28 套件/163 测 exit 0；构建 exit 0）
- [x] 契约落位表已核对；未动后端/PlatformOps/Content
- [x] 未自行加字段/改类型（`is_platform_default?` 为后端已落字段的只读声明）
- [x] 无硬编码连接串/密钥/端口
- [x] 失败≠空（GWT-95.5）；空态句非「暂无数据」
- [x] 可见处无内码（测试断言 `BUSINESS_ERROR` 不出现）
- [x] .tsx ≤400 行（359）
- [x] 票状态：done（evidence 落盘）
