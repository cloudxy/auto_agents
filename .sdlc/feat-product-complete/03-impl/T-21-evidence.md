# 实现证据 · T-21 设置页不得声称官网已同步（FR-90）

> 票：T-21（contract §11｜spec FR-90 GWT-90.1/90.2/90.3；QA-22 并案：90.2 单 Then）｜角色：/frontend（sdlc-workflow:frontend）｜lane：L4/ui｜日期：2026-09-12
> 状态：**已完成**（定向 jest 5/5 绿 + admin build 绿，退出码均 0）

## 1. 契约落位表（前端 UI 半）

| 契约元素 | 落位 | 文件 | 备注 |
|---|---|---|---|
| GWT-90.1 保存后无「官网已同步」「官网内容已实时同步更新」 | 保存回调 toast | `frontend/admin/src/pages/Settings.tsx` | 删 `message.info('官网内容已实时同步更新')`；成功句改 edge-states 钦定诚实句「系统配置已保存」（只声明保存，不声明同步） |
| GWT-90.1 访客首页 Hero 不变 | 前端无同步动作 | 同上 | 保存路径只调 `updateSiteConfig`（PUT /configs），不发任何官网数据请求；本波不做设置→官网真同步（合同 §非目标） |
| GWT-90.2（QA-22 单 Then）经办/只读 → 「当前账号不能改系统设置」 | 页面组件说明态 | 同上 | 非写者早退渲染 `Alert title="当前账号不能改系统设置"`（antd v6 用 title）；**不**做 404 同形（设置不是组织幽灵页） |
| GWT-90.2 无保存按钮 | 条件渲染 | 同上 | 说明态不渲染系统设置表单与「Webhook 与通知渠道」卡（两处保存控件都不在场）；配置拉取 effect 同步加守卫（无写面即无请求，也避免对未挂载 form 调 setFieldsValue） |
| GWT-90.3 只读保存不可达 | 强提交不可达 | 同上 + `Settings.test.tsx` | 说明态无 `<form>` 元素即无提交路径；测试断言写 API 零调用 |
| 写面角色判定 | 数组 includes | 同上 | `SETTINGS_WRITER_ROLES=['owner','admin']`（Members 的 `MEMBER_WRITER_ROLES` 同款写法）+ `is_platform_admin` 单列放行（见 §3） |

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/pages/Settings.tsx` | 修改 | 171 → 193 行：useAuthStore 写面守卫；非写者早退 Alert 说明态；toast 诚实化（删 message.info）；拉取 effect 加守卫 |
| `frontend/admin/src/pages/Settings.test.tsx` | 修改 | 36 → 134 行：新增 `useAuthStore` 容器 mock + antd message 捕获；T-21 四测（GWT-90.1 / 90.2 经办 / 90.2+90.3 只读 / 写侧不回归）；T-34 既有用例零改动 |

**与票「会改哪些文件」一致**：☑ 是（票列的正是这两个文件）。
**未触碰「不许改的文件」**：☑ 确认（`git status` 钉对：`frontend/official/src/pages/Home.tsx`、`frontend/admin/src/layouts/` 零改动；`/rbac` 404 未动）。未改 GWT、未改设计 token、未动路由守卫（App.tsx 的 `requireAdmin` 包裹保持原样）。

## 3. 关键实现决策

- **写面 = `is_platform_admin || tenant_role ∈ ['owner','admin']`**：票面「非 owner/admin 渲染只读说明」取 Members 同款租户角色数组；**平台超管单列放行**是后端守卫对齐——`PUT /configs/{key}` 挂 `require_platform_admin`（`backend/app/api/v1/configs.py`），纯平台超管 `tenant_role` 为空（auth.ts 注释：NULL=纯平台超管），只按租户角色判会误伤唯一有后端写权的账号（回归风险，测试「写侧不回归」钉住）。
- **诚实句取 edge-states 钦定文案**「系统配置已保存」：原「系统配置已成功保存」虽不撒谎，但统一到 edge-states「保存成功允许」句式；`message.info`（旧已同步句载体）整个删除并断言零调用。
- **「保存并发布」按钮文案保留**：T-34 GWT-99.3 已钉「动作不丢：『保存并发布』『保存渠道配置』保留」（memory Do-not-re-litigate），FR-90 禁的是成功句谎称同步，不动按钮。
- **说明态 = Alert 而非 404 同形**（QA-22 单 Then）：`title="当前账号不能改系统设置"` + 引导句「请联系管理员」；description 无「同步/官网」措辞。
- **测试夹具容器化**（Members.test 同款）：`mockUserState` 容器 + `beforeEach` 重置为 ADMIN_USER——T-34 既有用例零改动保持绿；`updateSiteConfig`/`message.*` mockClear 防「零调用」断言被前序用例污染；antd message 整体 mock 以捕获 toast 文案。
- **禁句断言口径**：成功句 `not.toMatch(/官网|同步/)` + 页面文本 `not.toMatch(/同步/)`；「不是 404 同形」用 `queryByText(/页面不存在/))` 为 null 断言。

## 4. 自测证据（命令与退出码原样）

```
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest src/pages/Settings --maxWorkers=2
PASS src/pages/Settings.test.tsx (13.828 s)
  ✓ 页头规范：无复述页名的标题卡，表单直接开始，动作与提示不丢（GWT-99.1/99.3/99.4） (3887 ms)
  T-21 FR-90 设置页不得声称官网已同步
    ✓ GWT-90.1 保存官网副标题类字段：成功句只声明保存，无任何已同步句 (4002 ms)
    ✓ GWT-90.2（QA-22 单 Then）经办打开：只见「当前账号不能改系统设置」，无保存控件，非 404 同形 (15 ms)
    ✓ GWT-90.2/90.3 只读打开：同说明态，强提交不可达（无 form、写 API 零调用） (12 ms)
    ✓ 写侧不回归：平台超管（后端 PUT /configs 守卫的角色）仍见表单与保存 (3641 ms)

Test Suites: 1 passed, 1 total
Tests:       5 passed, 5 total
Snapshots:   0 total
Time:        14.244 s
Ran all test suites matching /src\/pages\/Settings/i.
exit: 0

$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/admin
Compiled with warnings.   ← 全部为存量文件（RbacManagement/SpiderLogs/auth.ts 未触碰文件）的 no-unused-vars；触碰文件零告警
File sizes after gzip:
  （输出尾部：cra.link/deployment 提示，无 Settings 告警）
exit: 0
```

测试输出中的 `Warning: [antd: Spin] \`tip\` is deprecated` 为 `Settings.tsx` 第 83 行存量的 `<Spin tip>`（未触碰行，antd v6 已知弃用项，T-34 时期即在）。

## 5. 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-90.1 保存官网副标题类字段：无已同步句；Hero 不变 | `GWT-90.1 保存官网副标题类字段：成功句只声明保存，无任何已同步句`（成功句含「已保存」且 `!/官网|同步/`；`message.info` 零调用；保存只调 updateSiteConfig=前端无同步动作，Hero 自然不变——票面明示「核心是 toast 文案」） | ✅ |
| GWT-90.2（QA-22 单 Then）经办/只读 → 「当前账号不能改系统设置」 | `GWT-90.2（QA-22 单 Then）经办打开：…`（说明句在场 + 两处保存控件/表单字段全 null + 非「页面不存在」同形 + 无同步句） | ✅ |
| GWT-90.3 只读保存 → Hero 不变；无已同步成功句 | `GWT-90.2/90.3 只读打开：同说明态，强提交不可达（无 form、写 API 零调用）`（`document.querySelector('form')` 为 null=提交不可达；updateSiteConfig/message.success 零调用；无同步句） | ✅ |
| 写侧不误伤 | `写侧不回归：平台超管（后端 PUT /configs 守卫的角色）仍见表单与保存` + T-34 既有用例（默认 admin 视角跑，零改动全绿） | ✅ |

### 四类易漏测试（前端票）

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（纯前端 UI 票，无事务） | |
| 幂等 | ➖ N/A（无重复提交语义变更） | |
| 并发写 | ➖ N/A（无并发面） | |
| 外部依赖失败 | ➖ N/A（API mock 边界不变；保存失败路径 `保存失败，请稍后重试` 原样保留，本票只改成功句） | |

## 6. F-7 行数核对

- `Settings.tsx` 193 行（≤400）☑｜`Settings.test.tsx` 134 行（≤400）☑

## 7. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 经办/只读打开 /settings = **Alert 说明态**（「当前账号不能改系统设置」+ 联系管理员引导），不是 disabled、不是 404；两处保存按钮（保存并发布/保存渠道配置）DOM 均不存在；成功 toast 固定「系统配置已保存」。注意路由层 `requireAdmin`（全局 role）仍会把全局 operator/viewer 重定向 /unauthorized——GWT-90.2 的经办/只读指**租户维度** tenant_role（全局 admin 但租户 operator 的形态走说明态） |
| `/architect` | 角色模型口径差（只报告不裁决）：spec GWT-90.1 的保存者是「租户公司管理员」，但后端 `PUT /configs` 实际挂 `require_platform_admin`——租户 owner/admin 保存会被后端 403（前端 toast「保存失败，请稍后重试」，不违反 FR-90 不说谎）。本票按票面 owner/admin 开放写面，未收紧到平台超管；若后续要对齐后端只留平台超管，是 GWT 变更（→ pm） |

## 8. 交票自检

- [x] QA-22：90.2 仅「不能改系统设置」一支 Then（无 404 同形分支）
- [x] 无已同步成功句；未做真同步（无任何官网数据请求）
- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（jest 5/5、build exit 0）
- [x] 契约落位表已核对；未改 GWT/设计 token/路由守卫/后端
- [x] .tsx ≤ 400 行（F-7）

---

## 9. IMPL-QA-2 写面收紧（微修：implement 终审）

> 日期：2026-09-11｜触发：implement 终审 IMPL-QA-2｜lane：L4/ui｜状态：**已完成**（定向 jest 6/6 绿 + admin build 绿，退出码均 0）

**问题**：§1/§3 原写面判定 `is_platform_admin || tenant_role ∈ ['owner','admin']` 与后端错配——`PUT /configs/{key}` 挂 `require_platform_admin`，租户 owner/admin 见表单但保存恒 403（「见表单但保存必败」的坏体验）。§7 给 /architect 的口径差回报即此问题；本微修按后端守卫收紧前端写面，**非 GWT 变更**：GWT-90.2 的 Then 句「当前账号不能改系统设置」不变，仅覆盖角色从「经办/只读」扩为全部租户角色（owner/admin/operator/viewer 统一说明态早退）。

**改动**：

| 文件 | 说明 |
|---|---|
| `frontend/admin/src/pages/Settings.tsx` | 删 `SETTINGS_WRITER_ROLES=['owner','admin']` 数组；写面收紧为 `canWriteSettings = user?.is_platform_admin === true`；说明态 description 改「系统设置由平台超管维护；…请联系平台管理员」（原「由企业负责人、管理员或平台超管维护」在收紧后为假话，违 FR-90 不说谎口径）；title 句不动（193 行） |
| `frontend/admin/src/pages/Settings.test.tsx` | 夹具新增 `PLATFORM_ADMIN_USER` / `OWNER_USER`；`beforeEach` 默认改平台超管（T-34/GWT-90.1 表单用例零逻辑改动保持绿）；新增「IMPL-QA-2 写面收紧」测（owner/admin 循环渲染：同说明态、无表单/两处保存控件、写 API 零调用、非 404 同形、无同步句）；「写侧不回归」复用 `PLATFORM_ADMIN_USER` 夹具（157 行） |

**自测证据（命令与退出码原样）**：

```
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest src/pages/Settings --maxWorkers=2
PASS src/pages/Settings.test.tsx (8.345 s)
  ✓ 页头规范：无复述页名的标题卡，表单直接开始，动作与提示不丢（GWT-99.1/99.3/99.4） (2375 ms)
  T-21 FR-90 设置页不得声称官网已同步
    ✓ GWT-90.1 保存官网副标题类字段：成功句只声明保存，无任何已同步句 (2411 ms)
    ✓ GWT-90.2（QA-22 单 Then）经办打开：只见「当前账号不能改系统设置」，无保存控件，非 404 同形 (9 ms)
    ✓ GWT-90.2/90.3 只读打开：同说明态，强提交不可达（无 form、写 API 零调用） (7 ms)
    ✓ IMPL-QA-2 写面收紧：租户 owner/admin（原写面角色）打开 = 同说明态，不再见表单 (14 ms)
    ✓ 写侧不回归：平台超管（后端 PUT /configs 守卫的角色）仍见表单与保存 (2161 ms)

Test Suites: 1 passed, 1 total
Tests:       6 passed, 6 total
Snapshots:   0 total
Time:        8.684 s, estimated 12 s
Ran all test suites matching /src\/pages\/Settings/i.
exit: 0

$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/admin
（输出尾部：File sizes after: gzip 列表 +「The build folder is ready to be deployed.」+ cra.link/deployment 提示）
exit: 0
```

- jest 输出中的 `Warning: [antd: Spin] tip is deprecated` 为 `Settings.tsx` 存量 `<Spin tip>`（未触碰行，T-34 时期即在）。
- build「Compiled with warnings」全部在未触碰文件（`src/components/spider/LogDrawer.tsx` / `src/pages/RbacManagement.tsx` / `src/pages/SpiderLogs.tsx` / `src/services/auth.ts`），build 输出零 Settings 提及（grep 钉对）。
- F-7：`Settings.tsx` 193 行、`Settings.test.tsx` 157 行（均 ≤400）☑

**给下游**：/qa——/settings 写面现为**平台超管 only**；租户四角色（owner/admin/operator/viewer）统一「当前账号不能改系统设置」Alert，引导句改「请联系平台管理员」（不再是泛「管理员」）。§7 给 /architect 的口径差回报已由本微修消解，无需再裁。
