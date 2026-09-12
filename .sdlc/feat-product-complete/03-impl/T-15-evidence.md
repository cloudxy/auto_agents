# 实现证据 · T-15 侧栏单一真相：停用 /auth/menus 驱动；组织幽灵页 404 同形

> 票：contract §11 Wave C `T-15`｜FR 锚点：FR-82（GWT-82.1/82.2/82.3/82.4）｜角色：/frontend（lane=ui）｜日期：2026-09-11
> 依据：ADR-0021 v2（accepted，含 FR-95 /enterprise 和解句）；spec v1.5 FR-82；T-29 成果（App.tsx 单布局树 + `MainLayout` 守卫先例）。companion=tdd：先红后绿，双输出见 §6。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 决策 1：侧栏唯一输入 = `menuConfig` 经 `usePermission().filteredMenus`；**停用** `/auth/menus` 驱动 | 布局组件 | `frontend/admin/src/components/AdminLayout.tsx` | 删除 `useQuery(fetchDynamicMenus)` 整个动态分支（原 `dynamicMenus.length` 时改画 IA 的代码不再存在）；`menuItems = filteredMenus.map(...)` 唯一来源 |
| 脏 DB 树不影响侧栏（GWT-82.1） | 测试 | `App.menu.test.tsx` | mock `/auth/menus` 返回脏树（含角色权限/企业管理、缺渠道组/我的安装）；断言侧栏仍见渠道组/我的安装、无幽灵叶、**且侧栏生命周期 0 次消费 `/auth/menus`** |
| 权限未就绪：「权限加载中」+ 渠道组/我的安装不消失 + 不闪幽灵叶（GWT-82.2） | hook 既有语义 + 测试 | `usePermission.ts` **未改**；`App.menu.test.tsx` | deferred promise 钉住未就绪首现；就绪后叶保留、句退场 |
| 幽灵路由 `/rbac` `/enterprise`：租户 = 缺页同形 404（GWT-82.3） | 路由守卫 | `frontend/admin/src/App.tsx` `MainLayout` | 沿 T-29 先例：守卫在 AdminLayout 渲染前短路（全屏 404 无侧栏，不进 Unauthorized）；两路由 element 由 `ProtectedRoute requireAdmin`（租户公司管理员可过——漏洞根因）改为裸 `Page`，与 /newapi 同形 |
| `/enterprise` 超管可达不砍（ADR-0021 v2 和解句） | 同上 + 测试 | `App.menu.test.tsx` | 超管直打 /enterprise /rbac 仍进页（Card 标题断言） |
| 超管无企业空间开渠道组/我的安装 = 「…属于企业空间」说明（GWT-82.4，不因 FR-102 改变） | 页组件 | `RelayGroups.tsx` / `MyInstalls.tsx` + 新 `components/TenantSpaceOnly.tsx` | 判据 `is_platform_admin && tenant_id==null`（纯前端态，不发空表请求）；与 Usage 页「用量属于企业空间」同形（antd v6 `title`） |
| 五组不重排 / FR-91 零施工 | — | `config/menuConfig.tsx` **零 diff** | git diff --stat 确认；menuConfig/usePermission 语义未动 |

**分层核对**：☐ Router 未 import ORM ➖ N/A（纯前端票）｜☐ 未定义新 token / 未改 GWT ☑｜☐ 未动 T-29 路由树结构 ☑（同一 `MainLayout` 布局分支，仅改守卫条件与两条 element 的包装；未增删路由）｜☐ 未动页头（T-34）☑｜☐ 未做 FR-91 ☑

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/components/AdminLayout.tsx` | 修改 | 删动态菜单分支（`useQuery`/`fetchDynamicMenus`/`MENU_ICON_MAP`/`PLATFORM_WRITE_KEYS` 引用随之移除）；71 行（F-7） |
| `frontend/admin/src/App.tsx` | 修改 | `ORG_GHOST_PATHS` + `isOrgGhostPath`；`MainLayout` 守卫扩为「平台写面 ∪ 组织幽灵页」；/rbac /enterprise element 摘除 `requireAdmin` 包装。141 行 |
| `frontend/admin/src/components/TenantSpaceOnly.tsx` | 新增 | GWT-82.4 说明态组件（14 行），两页共用 |
| `frontend/admin/src/pages/RelayGroups.tsx` | 修改 | `noTenantSpace` 早退说明态；`load` 跳过请求。167 行 |
| `frontend/admin/src/pages/MyInstalls.tsx` | 修改 | 同上。237 行 |
| `frontend/admin/src/App.menu.test.tsx` | 新增 | GWT-82.1…82.4 + 超管可达 + 租户回归共 8 例。221 行 |

**与票里「会改哪些文件」一致**：☑ 是（预期 AdminLayout + 幽灵页守卫 + 82.4 说明态 + 测试；menuConfig/usePermission 零 diff 如预期）
**未触碰「不许改的文件」**：☑ 确认（App.tsx 路由树结构、页头、NewApiOps、FR-91、`services/menus.ts` 本体均未动；工作树中其余 M/?? 为 Wave 并行票所有）

## 3. 关键实现决策

### 守卫为什么放 `MainLayout` 渲染前而非页 element 内（沿 T-29 结论）

若只在 `/rbac` `/enterprise` 的 element 内判 `requirePlatformAdmin`，租户直打时主树 `AdminLayout` 仍先挂载（侧栏+内容区 404）——与平台写面的**全屏同形 404（无侧栏）**不同形，且租户侧栏文案（如「渠道组」）会出现在 404 屏上，撞 App.test 既有断言（`queryByText(/渠道/)` 必须缺席）。故并入 `MainLayout` 既有守卫条件（`isPlatformWritePath(pathname) || isOrgGhostPath(pathname)`），element 同步摘除 `requireAdmin`（租户公司管理员 `role==='admin'` 可过——正是 ADR 记录的漏洞根因），与 /newapi /platform-ops /users 完全同形。超管分支零影响。

### 「停用」= 删除消费点，不是「拉了但忽略」

ADR 决策 1 的验收是脏 DB 树不影响租户可见叶。若保留 `useQuery` 仅不采纳，请求仍发出（浪费 + 语义含混）。实现为**删除整个动态分支**；测试同时断言 `api.get` 从未被以 `/auth/menus` 调用（钉住「停用」本身）。`/auth/menus` 端点与 `services/menus.ts` 保留（expand-contract 决策 4：RBAC 页/旧客户端本波仍 200，删表留给下一特征）。

### GWT-82.4 判据用登录态而非 API 错误映射

Usage 页走的是响应体 `scope/message` 判「用量属于企业空间」；渠道组/我的安装后端未必回同形错误码，且 GWT 禁止「空表假装没订阅」——所以判据取 `user.is_platform_admin && user.tenant_id == null`（登录响应快照，FR-102 平台租户身份只在入队/方案归属点后端解析，不回填此字段 → Then 不因 FR-102 改变），命中即早退说明态并**跳过列表请求**（连空表都不发）。文案与 Usage 同族：「渠道组属于企业空间」「安装属于企业空间」。

### 事务边界 / 幂等 / 并发 / 外部依赖

➖ N/A（纯前端数据源与守卫票，无写操作、无事务面）。

## 4. ORM 与 DBML 对齐

➖ N/A（未触及 models/schemas；零后端代码 diff；未改 023 种子——ADR 决策 4：本波不删表不改种子主路径）。

## 5. 可观测性

➖ N/A（无新日志面；沿用既有 ErrorBoundary label 与页 label）。

## 6. 自测证据

> 命令与退出码**原样粘贴**。companion=tdd：红（实现前）/ 绿（实现后）双输出。

```
# 红：实现前，新测试对现网代码跑（脏树驱动侧栏 + requireAdmin 漏洞 + 无 82.4 说明态）
$ cd frontend/admin && CI=true npm test -- --watchAll=false App.menu
  ✕ GWT-82.1 dirty /auth/menus tree does not drive the tenant sidebar (543 ms)
  ✕ GWT-82.2 permissions not ready: loading note, tenant leaves stay, no ghost flash (180 ms)
  ✕ GWT-82.3 tenant company admin direct hit on /rbac is same 404 shell without sidebar (8048 ms)
  ✕ GWT-82.3 tenant company admin direct hit on /enterprise is same 404 shell, no other-company list (8070 ms)
  ✓ platform super admin still reaches /enterprise and /rbac (ADR-0021 v2) (1282 ms)
  ✕ GWT-82.4 super admin without enterprise space on /relay: explanation, not a fake empty table (8073 ms)
  ✕ GWT-82.4 super admin without enterprise space on /capabilities/installs: explanation, not empty subscription (8065 ms)
  ✓ tenant owner still gets the real relay page, not the enterprise-space note (7213 ms)
Test Suites: 1 failed, 1 total
Tests:       6 failed, 2 passed, 8 total
exit: 1
（两例 ✓ 为超管可达/租户回归守护——现网本就应过，属防过度收紧的回归钉）

# 绿：实现后同命令
$ cd frontend/admin && CI=true npm test -- --watchAll=false App.menu
  ✓ GWT-82.1 dirty /auth/menus tree does not drive the tenant sidebar (593 ms)
  ✓ GWT-82.2 permissions not ready: loading note, tenant leaves stay, no ghost flash (195 ms)
  ✓ GWT-82.3 tenant company admin direct hit on /rbac is same 404 shell without sidebar (1294 ms)
  ✓ GWT-82.3 tenant company admin direct hit on /enterprise is same 404 shell, no other-company list (864 ms)
  ✓ platform super admin still reaches /enterprise and /rbac (ADR-0021 v2) (1700 ms)
  ✓ GWT-82.4 super admin without enterprise space on /relay: explanation, not a fake empty table (1012 ms)
  ✓ GWT-82.4 super admin without enterprise space on /capabilities/installs: explanation, not empty subscription (345 ms)
  ✓ tenant owner still gets the real relay page, not the enterprise-space note (7480 ms)
Test Suites: 1 passed, 1 total
Tests:       8 passed, 8 total
exit: 0

# 全量 admin Jest（含 T-29 App.layout / usePermission / RelayGroups 等既有回归）
$ cd frontend/admin && CI=true npm test -- --watchAll=false --maxWorkers=2
Test Suites: 23 passed, 23 total
Tests:       103 passed, 103 total
exit: 0
```

### 全量跑的环境干扰记录（非本票缺陷，已定界）

默认 worker 并行下全量出现**漂移性超时**（`Exceeded timeout of 60000 ms`，落在 Members / Capabilities.command 等本票零 diff 的重组件套件；失败用例每次不同、单套隔离跑全绿、本票文件与这些套件无共享模块状态）。与 T-29 记录的 Wave A 并行会话争用机器同源。处置：`--maxWorkers=2` 降并行后全量全绿（上行输出）。包内 `npm test --prefix frontend/admin` 形式在 npm workspace 下报 exit 254，仓库等价可用命令为 `cd frontend/admin && npm test`（本节采用）。

```
# 构建门禁
$ npm run build --prefix /Users/xuyun/auto_agents/frontend/admin
The build folder is ready to be deployed.
exit: 0
（首轮 build 抓到测试 helper TS 类型过窄——login(user: typeof TENANT_OWNER) 拒收 tenant_id:null；改为 Record<string, unknown> + as never 后通过。tsc 在 CRA build 内生效）

# 前端工程门禁（F-2..F-7）
$ bash /Users/xuyun/auto_agents/tools/check/frontend.sh
✓ 前端工程门禁通过
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-82.1 脏树下仍找到自己的叶 | `App.menu.test.tsx`「dirty /auth/menus tree does not drive the tenant sidebar」——mock 脏树（含 rbac/enterprise、缺渠道组/安装）下：渠道组✓ 我的安装✓ 角色权限✗ 企业管理✗，且 `/auth/menus` 零消费 | ✅ |
| GWT-82.2 权限未就绪 | 「permissions not ready」——deferred 权限：权限加载中✓ 渠道组/我的安装在场✓ 无幽灵叶✓；resolve 后叶保留、句退场 | ✅ |
| GWT-82.3 深链组织页同形 404 | /rbac、/enterprise 两例——「页面不存在或已被移除」+返回工作台✓ 无「抱歉」✓ 无侧栏（AutoAgents/渠道缺席）✓ 无其他公司列表（新建公司缺席）✓ | ✅ |
| GWT-82.3 反向：超管入口不砍 | 「super admin still reaches /enterprise and /rbac」——超管进页（新建公司/角色权限菜单管理 Card）+ 布局在场 | ✅ |
| GWT-82.4 超管无企业空间 | /relay →「渠道组属于企业空间」且无「新建渠道组」；/capabilities/installs →「安装属于企业空间」且无「去能力市场」/空态句；不发列表请求 | ✅ |
| GWT-82.4 反向：租户不受说明态影响 | 「tenant owner still gets the real relay page」——租户开 /relay 仍是真实页（新建渠道组在场、说明态缺席） | ✅ |
| 五组不重排 / FR-91 零施工 | `menuConfig.tsx` 零 diff（git diff --stat 空）；FR-91 无任何代码 | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（无数据面写操作） | |
| 幂等 | ➖ N/A（守卫/渲染纯函数式；`noTenantSpace` 判据来自登录快照，重复求值同值） | |
| 并发写 | ➖ N/A | |
| 外部依赖失败 | GWT-82.2 用例在权限端点 pending + 其余端点全拒绝下渲染不崩；82.4 说明态在零请求下达成 | ✅ |

## 7. NFR 验证

| NFR | 要求（spec §819） | 实测 | 环境 |
|---|---|---|---|
| NFR-05（本票切片） | 租户直打平台专属**与组织幽灵页** = 页面不存在同形；空缓存 ≠ 无权限 | 82.3 两例全屏同形 404；82.2 空缓存 fallback 读叶在场 | jsdom（admin Jest 23 套件） |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | ① 组件级 82.1–82.4 已绿；**活体回归需真环境**：把 DB `menus` 表故意写脏（023 形态：含 rbac/enterprise、缺渠道组）再登录看侧栏（jsdom 只能 mock）。② 直打面补全：/rbac /enterprise ×（未登录/租户管理员/租户经办/超管）× 子路径深链（/rbac/xxx → 同 404）。③ 82.4 说明态需真实超管号（tenant_id=NULL）过 FR-102 上线后回归一次：确认平台租户身份未回填 tenant_id。④ 全量 Jest 在并行争用下有 60s 超时漂移（§6 干扰记录），重跑建议 `--maxWorkers=2`。 |
| `/backend` | 本波零 diff，无需动 `/auth/menus` 形状（ADR 影响范围表如此）；提醒：侧栏已不消费该端点，任何 menus 表变更不会再影响导航。 |
| `/architect` | ① `services/menus.ts`（`fetchDynamicMenus`）现已无消费方（唯一调用方 AdminLayout 已删分支）——expand-contract 下一特征可连同 `menus` 表一起评估删除，本票按 ADR 决策 4 保留。② `MENU_ICON_MAP` 导出随之失去消费方，同批清理候选。 |
| `/frontend`(T-34) | 页头规范未动；`pageTitleFor('/rbac'|'/enterprise')` 兜底「后台管理」——幽灵页无菜单叶是预期（不在五组），如需专属标题请走 T-34 的页头通道并保持租户不可达。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（红/绿双输出 + 命令 + 退出码原样）
- [x] 自测全绿（admin Jest 23/23 套件 103 例、build、前端门禁）
- [x] 契约落位表已核对；menuConfig/usePermission 零 diff（真相未漂）
- [x] ORM/DBML N/A（未触及）
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] 业务 .tsx ≤ 400 行（App 141 / AdminLayout 71 / RelayGroups 167 / MyInstalls 237 / TenantSpaceOnly 14 / 测试 221，F-7）
- [x] 数据获取未新增手动 loading（本票删除一个 useQuery；82.4 说明态跳过请求而非加 loading）
- [x] antd v6 弃用项未新增（新 Alert 用 `title`，P-FE-08）
- [x] 路由 lazy/ErrorBoundary/404 保持（单布局树结构未动）
- [x] 发现的上游问题已回报（全量超时漂移 → §6/§8-qa），未自行绕过
