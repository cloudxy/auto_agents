# 实现证据 · T-25 用户管理页「已删除」筛选 + 恢复按钮（重派收尾 + 两处跨票测试修复）

> 票：contract §11 Wave A `T-25`｜FR 锚点：FR-93（GWT-93.1/93.2/93.3 UI 面 + 93.4/93.8 冲突中文句 + 93.9 重复恢复）｜角色：/frontend（lane=ui）｜日期：2026-09-11
> 性质：**串行重派**——第一代理改了 `pages/Users.tsx` `services/users.ts` `services/admin.ts` 未写 evidence 且 Users.test 半成品；本会话核验其改动、补齐缺口（离线钉句/两句各占元素）、修红 Users.test（antd 两字空格）与 App.menu.test 过时选择器（T-15 票 1 例，T-10 合法改版所致）。
> 依据：edge-states「屏：用户管理 /users（FR-93）」全部钉句；T-24 evidence §8 给前端契约（status 参数 / deleted_at 标记 / restore 端点 / 400 中文句 / 幂等 200）。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| `GET /admin/users?status=deleted`（默认 active 不含已删，GWT-93.2） | services | `frontend/admin/src/services/admin.ts` | `fetchUsersPage` 增 `status?: 'active'\|'deleted'`；后端参数白名单 `^(active\|deleted)$`（T-24） |
| 已删标记（GWT-93.1） | 类型 + 页面 | `services/users.ts` `UserItem.deleted_at` + `pages/Users.tsx` 状态列 | 非空 → Tag「已删除」；`deleted` 视图行唯一动作=恢复 |
| 恢复端点 `POST /admin/users/{id}/restore`（GWT-93.3） | services | `services/users.ts` `restoreUser` | 200=快照；400=占用中文句；重复恢复 200 no-op（T-24 §8） |
| 恢复确认弹窗/占用冲突/离线/成功 toast | 页面子组件 | `frontend/admin/src/pages/UsersRestore.tsx` | 钉句全按 edge-states 用户管理屏（见 §3） |
| 空态两分野 + 错误≠空表（FR-84 族） | 页面 | `pages/Users.tsx` | `locale.emptyText` 自定义 Empty；失败=页级 Alert+重试 |
| 默认视图不含已删（GWT-93.2 既有保持） | 页面请求参数 | `pages/Users.tsx` `loadUsers` | 非 deleted 视图一律 `status:'active'`（在职=激活+停用；后端 active 语义=未软删全集） |

**边界核对**：☑ 未定义 token/未改 GWT ☑ 未动后端（T-24 面零 diff）☑ 未动其他页面（RelayGroups/LlmProviders/NewApiOps 零 diff）☑ X-QUOTA：占用/失败句均不含内码（测试断言 `queryByText(/BUSINESS_ERROR/)` 为 null）

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/pages/Users.tsx` | 修改（第一代理起稿，本会话核验收口） | 状态筛选改服务端档（在职全部/在职·激活/在职·停用/已删除）+ 已删行恢复动作 + 空态两分野 + 页级错误态。386 行（F-7 ≤400） |
| `frontend/admin/src/pages/UsersRestore.tsx` | 新增（第一代理起稿，本会话补齐） | 恢复确认弹窗；本会话补：离线钉句前置判定（不发请求）+ 占用两句各占一个元素。100 行 |
| `frontend/admin/src/services/users.ts` | 修改 | `UserItem.deleted_at`；`restoreUser` |
| `frontend/admin/src/services/admin.ts` | 修改 | `fetchUsersPage` status 参数 |
| `frontend/admin/src/pages/Users.test.tsx` | 新增（第一代理半成品，本会话修红） | 9 例：GWT-93.1/93.2/93.3/93.4+93.8/93.9 + 空态/错误态/离线钉句 |
| `frontend/admin/src/App.menu.test.tsx` | 修改（**跨票测试修复**，T-15 票 1 例） | 仅换过时选择器：「新建渠道组」按钮名 → T-10 现版面稳定判据（RelayGroups 自有失败句），测试意图/其余 7 例零改动 |

工作树其余 M/?? 文件为 Wave A 并行票所有（T-24 后端、T-10 RelayGroups、T-30 LlmProviders 等）；`types/env.d.ts` 的 `REACT_APP_RELAY_PUBLIC_BASE_URL` 是 **T-10 改动**（随其收口），非本票。

**与票里「会改哪些文件」一致**：☑ 是（预期 Users 页 + services + 测试；`env.d.ts` 为并行票面）
**未触碰「不许改的文件」**：☑ 确认（后端零 diff；RelayGroups.tsx/NewApiOps/LlmProviders/App.tsx 零 diff；App.menu.test 未改测试意图）

## 3. 关键实现决策

### 文案钉句落位（edge-states 用户管理屏，逐句核对）

| 屏态 | 钉句 | 落点 |
|---|---|---|
| 恢复确认弹窗 | 「恢复用户 “{用户名}”？」/「恢复后该用户回到用户列表并恢复为启用状态，可重新登录。」按钮 恢复/取消；恢复中「恢复中…」 | UsersRestore Modal title/body/okText |
| 占用冲突（93.4/93.8） | 红字两句「用户名或邮箱已被现有用户占用。」「该用户仍保留在已删除列表中。」弹窗不关 | UsersRestore 内联，**两句各占一个 `<span display:block>`**（可精确断言、各自成句朗读；`<br/>` 拼接形态会被 getNodeText 连成一条，无法精确钉句） |
| 恢复成功（93.3） | toast「已恢复 “{用户名}”。该用户已回到用户列表。」行从已删筛选消失 | message.success + 刷新当前视图 |
| 重复恢复（93.9） | 无恢复入口（默认列表无该行）；残留触发=无感 | 见下「no-op 判定面」 |
| 非占用失败（FR-84 族） | 「恢复失败。{原因或检查网络后重试}。该用户仍保持已删除。」弹窗不关 | UsersRestore failure 内联 |
| 离线点恢复 | 「网络不可用，用户没有恢复。」弹窗不关 | **本会话补**：onOk 前置 `navigator.onLine` 判定（RelayGroups.onIssue 同口径），不发请求 |
| 空态 | 默认「还没有用户。」+新建入口；已删「还没有已删除的用户。删除的用户会保留在这里，可恢复。」无动作 | Users.tsx `locale.emptyText` 按视图分野 |
| 错误态 | 「用户列表加载失败。检查网络后重试。」+重试；不是空表 | Users.tsx 页级 Alert（listError），替代原 message.error 漂移写法 |

### 重复恢复 no-op 判定面（GWT-93.9）

后端幂等 no-op 与真恢复**同形返回 200**（均 `deleted_at=null`；并发抢先恢复的快照 `is_active=true`，客户端不可区分）。保守信号：真恢复必置 `is_active=true`，故「在册且停用」（`deleted_at==null && is_active===false`）只可能是 no-op 残留 → 不报成功、静默刷新；其余成功一律按真恢复 toast（并发抢先场景结果为真，句义成立）。主保证仍是列表面：已恢复行不在「已删除」筛选中，无恢复入口。

### 状态筛选本地/服务端分工

`status`（在职/已删）走服务端参数（GWT-93.1/93.2 的行集语义由后端 T-24 保证）；搜索/角色/公司/部门保持本地过滤（服务端无对应参数，不扩契约）。切档重置页码。

### 恢复成功不自动切档

GWT-93.3「该用户出现在默认列表且状态=启用；已删除筛选不再出现该用户」——实现为刷新当前（已删）视图使行消失；默认列表语义由后端 status=active 行集保证。edge-states 无「自动跳回默认档」钉句，不发明交互。

### 跨票修复 1：Users.test 红的根因与修法

antd Button 两字中文自动插空格（「恢 复」「取 消」「重 试」「编 辑」「删 除」），第一代理用全等 name 断言 → 6 例红。修法=按钮断言一律 `getByRole('button', { name: /恢\s*复/ })` 形态（兼容空格有无；memory 既有教训的再应用）。其中 GWT-93.1 的 编辑/删除 **负向**断言原为空过（全等永不命中），regex 化后才真正可判。

### 跨票修复 2：App.menu.test「tenant owner still gets the real relay page」

T-15 时选择器「新建渠道组」按钮：T-10 合法改版后该按钮按 `canIssue`（`tenant_role ∈ {owner,admin}`）渲染，且该套 mock 对 `/relay/page` 一律 reject → 页面走自有错误态早退，按钮永不出现 → 1 例红。修法（只换选择器不改意图）：断言 RelayGroups 自有失败句「渠道组加载失败。检查网络后重试。」+ 保持「渠道组属于企业空间」缺席断言——仍证明 owner 拿到真实页（其自身错误态）而非企业空间说明态。**不**给 fixture 补 `tenant_role`（写权档位非本测意图，且错误态早退使按钮判据在该 mock 下结构性不可达）。

### 事务边界 / 幂等 / 并发 / 外部依赖

➖ N/A（纯前端票；占用判定/事件上报的事务与幂等由 T-24 后端保证，见其 evidence §3）。

## 4. ORM 与 DBML 对齐

➖ N/A（未触及 models/schemas；零后端 diff）。

## 5. 可观测性

➖ N/A（无新日志面；恢复动作的后端审计/事件在 T-24：`user.restore` 审计 + `user_restored` 事件）。

## 6. 自测证据

> 命令与退出码**原样粘贴**。

```
# 定向：Users.test 修复前（第一代理半成品，重派核验基线；输出经 tail 管道回显，jest 判定以 Tests: 行为准）
$ cd frontend/admin && CI=true npx jest src/pages/Users.test.tsx --watchAll=false --maxWorkers=2
Test Suites: 1 failed, 1 total
Tests:       6 failed, 2 passed, 8 total
（6 failed = 红：antd 两字按钮空格 + 冲突句 br 拼接）

# 定向：两文件修复后（同样经 tail 回显）
$ cd frontend/admin && CI=true npx jest src/pages/Users.test.tsx src/App.menu.test.tsx --watchAll=false --maxWorkers=2
Test Suites: 2 passed, 2 total
Tests:       17 passed, 17 total

# 全量（admin 门禁，不经管道，exit 为 jest 真实退出码）
$ cd frontend/admin && CI=true npm test -- --watchAll=false --maxWorkers=2
Test Suites: 24 passed, 24 total
Tests:       132 passed, 132 total
Snapshots:   0 total
Time:        381.768 s
Ran all test suites.
exit: 0

# 构建（admin 门禁）
$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/admin
The build folder is ready to be deployed.
exit: 0
```

### 验收项逐条对应

| GWT（UI 面） | 覆盖的测试 | 结果 |
|---|---|---|
| 93.1 筛已删（标记可见、活跃用户缺席、无编辑/删除动作） | `GWT-93.1 筛「已删除」…` | ✅ |
| 93.2 默认视图不含已删（status=active） | `GWT-93.2 默认视图…` | ✅ |
| 93.3 恢复成功（确认弹窗→toast→行从已删筛选消失） | `GWT-93.3 恢复成功…` | ✅ |
| 93.4/93.8 占用冲突（两句中文、弹窗不关、无内码、不误报 error） | `GWT-93.4/93.8 占用冲突…` | ✅ |
| 93.9 重复恢复（无感：不重复 toast、静默刷新） | `GWT-93.9 重复恢复…` | ✅ |
| 空态两分野 | `空态：默认视图 0 行…` | ✅ |
| 错误≠空表（FR-84 族）+ 重试 | `错误态：列表加载失败…` | ✅ |
| 离线钉句（不发请求、弹窗不关） | `离线点恢复…`（本会话新增） | ✅ |
| 非占用失败句 | `恢复失败（非占用，网络）…` | ✅ |
| 93.6 越权 404 同形 | 路由守卫面（T-29 `App.layout.test` 404 同形回归 + 后端 T-24 `test_tenant_direct_restore_is_404_shape`） | ➖ 本票 N/A（守卫非本票施工面） |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（前端无多步写；后端 T-24 已测） |
| 幂等 | `GWT-93.9 重复恢复…`（no-op 判定面） | ✅ |
| 并发写 | ➖ N/A（并发恢复同形 200 不可前端区分，见 §3；行为保证在后端条件 UPDATE） |
| 外部依赖失败 | `错误态` / `恢复失败（非占用）` / `离线点恢复` | ✅ |

## 7. NFR 验证

➖ 票面无 NFR 条目。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | Users.test 全 mock services 层（fetchUsersPage/restoreUser），真实联调需验：① `status=deleted` 真行集；② 400 占用句经信封 message 到达前端的形态（本测 mock 的 axios rejection 形态）；③ 离线判定只在提交时刻（打开弹窗时不判）。 |
| `/architect` | 无契约歧义。no-op 与真恢复响应同形是 T-24 契约既定（幂等 200），前端按保守信号处理已记录 §3。 |
| T-15 作者（跨票修复知会） | App.menu.test 1 例选择器已随 T-10 现版面更新（真实页错误态判据），意图未动；T-29/T-15 其余断言零改动。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（定向 17/17 + 全量 24 suites/132 tests exit 0 + build exit 0）
- [x] 契约落位表已核对（UI 面；分层无违规）
- [x] 无硬编码连接串/密钥/端口；颜色/间距无裸 hex（沿用 antd token 体系）
- [x] 无 `except: pass`（catch 均有用户可见落点）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报（App.menu 过时选择器根因=T-10 改版，已修并知会）
