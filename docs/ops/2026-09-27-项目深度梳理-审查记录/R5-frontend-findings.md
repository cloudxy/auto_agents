# Findings — R5-frontend（admin / official / shared）

## Snapshot
- HEAD: 82259f301c060dbf411424ec8775f29944e313e1（工作区干净）
- slice: `git ls-files -s` over explore_roots(frontend/admin/src frontend/official/src frontend/shared/src frontend/admin/e2e) + inputs → sha256 0b406ba6867f…（270 条），由 manager 计算
- reviewer: sdlc-workflow:reviewer（G-fresh，只读）；packet: ../packets/2026-09-27-1830-review-reviewer-R5-frontend.md
- 方式：静态检查——packet 全部 inputs + admin 认证链路（`useAuthStore.ts`、`api.ts`、`auth.ts`、`navigation.ts`、`ProtectedRoute.tsx`、`usePermission.ts`、`Login.tsx`、`index.tsx`、`services/admin.ts`、`services/users.ts`、`e2e/smoke.spec.ts`）与 shared `client.ts`、`envelope.ts`；Grep/Glob 统计 react-query / useEffect 分布、OpenAPI 类型引用、服务层测试、mock。为验证 QA-1 读了第三方源码 `node_modules/axios`（1.20.0）`lib/defaults/index.js:44-58,101-103`、`lib/helpers/formDataToJSON.js:75-123`、`lib/core/Axios.js:155-162`。已记录执行：evidence/ 下 frontend-gate / frontend-build / frontend-test-admin / frontend-test-official / npm-audit / arch。reviewer 未复现任何东西。
- 首轮触达 24-turn 上限，经 manager 要求交付。未读（一律视为未验证）：`App.tsx`、`AdminLayout.tsx`、`MarkdownBody.tsx`、official `services/api.ts`、admin `setupProxy.js`、`.github/workflows/ci.yml`、后端 `/auth/permissions` 鉴权依赖。

**摘要**：19 条（major 7：QA-1、3、6、8、9、11、12；minor 12；无已确认 blocker——QA-1 若复现成立应升 blocker）。

---

## FINDINGS

### QA-1 共享 client 把 JSON 设为默认 Content-Type，按 axios 1.20 逻辑所有 FormData 上传会被转成 JSON、文件内容丢失（能力导入 / 目录导入）
- Dimension: 6 契约 / 9 产品价值 | Severity: **major**（复现成立应升 blocker：FR-100、FR-07 导入主路径不可用） | 工作量: S
- Evidence：`frontend/shared/src/api/client.ts:28-30` 实例级 `headers: { 'Content-Type': 'application/json' }`；`frontend/admin/src/services/capabilities.ts:86-92`（`importAssets`）、`:186-204`（`previewTreeImport` / `confirmTreeImport`）直接 `api.post(url, form, { onUploadProgress })` 不覆盖 Content-Type；`node_modules/axios/lib/core/Axios.js:155-162` 实例头合并进 `config.headers`；`lib/defaults/index.js:46-57` `hasJSONContentType && isFormData → JSON.stringify(formDataToJSON(data))`；`formDataToJSON.js:115-117` File 值原样放进对象，`JSON.stringify(File)` = `{}`。测试为何没发现：所有 UI 测试在服务层 mock 掉上传函数（`pages/market/ImportTreePicker.test.tsx:23-25`、`pages/Capabilities.import.test.tsx:28,41`、`pages/market/TenantShelf.test.tsx:36,46`），`frontend/admin/src/services/` 下无任何 `*.test.*`。
- 后果：后端收到 `application/json` 体 `{"file":{}}`（或 `{"files":[{},…]}`），按 multipart 定义的端点（`schema.d.ts:12710,12745,13153`）返回 422 或按「无文件」处理——一键导入与目录导入在真实浏览器很可能完全不可用，而 391 条单测全绿。
- Suggestion：删掉 `createApiClient` 默认 Content-Type（axios 对普通对象自动设 `application/json`，`defaults/index.js:101-103`；对 FormData 交由浏览器生成带 boundary 的 multipart 头）；若不改共享层，至少三处上传显式传 `headers: { 'Content-Type': 'multipart/form-data' }`；shared client 加契约单测（自定义 adapter 断言 `config.data instanceof FormData`）。状态：**未验证**（静态推导），复现命令见文末。

### QA-2 登录时先拉权限后写 token，第一次 `/auth/permissions` 请求不带 Authorization
- Dimension: 4 / 6 | Severity: minor（后端是否 401 未验证；若 401 会在登录过程中顺带触发一次 logout） | 工作量: S
- Evidence：`frontend/admin/src/store/useAuthStore.ts:23-34` `apiLogin` → `refreshPermissions()`（:27）→ 之后才 `set({ token … })`（:29-34）；`services/api.ts:13` `getAuthToken` 请求发出时读 store（此时 token 仍 null）；`hooks/usePermission.ts:22` 发请求、`:26-28` 吞异常并置 `loadState='error'`；若 401 走 `api.ts:14-18` `logout()`。
- 后果：注释（:24）「登录即拉取权限」实际未生效，每次登录多一次无效请求；要等组件挂载 `usePermission.ts:64-69` 再拉一次才恢复，菜单先显示「权限加载中」降级态；e2e 桩对所有请求放行且不校验请求头（`e2e/smoke.spec.ts:36-38`），测不到。
- Suggestion：先 `set({ token })` 再 `refreshPermissions()`，或给 `refreshPermissions(token)` 显式传入；e2e 桩对需鉴权路由校验 `Authorization`，缺失返回 401。

### QA-3 用户管理页的搜索/角色/公司/部门/启停筛选只作用于当前服务端分页 20 行，总数却是全库
- Dimension: 8 超量边界 / 9 | Severity: **major** | 工作量: M（后端加查询参数 + 前端改服务端筛选）
- Evidence：`frontend/admin/src/pages/Users.tsx:5-7`（设计注释「搜索/角色/公司/部门保持本地过滤」）、`:36` `pageSize = 20`、`:61-64` 只传 skip/limit/status、`:312-321` `users.filter(...)` 只过滤当前页、`:325-328` `total` 与「共 N 位用户」来自服务端、`:248-253` 本地无匹配显示「当前筛选无匹配的用户。」；`services/admin.ts:22-27` `fetchUsersPage` 只支持 skip/limit/status。
- 后果：超 20 人后，目标用户在第 2 页时第 1 页搜不到且被告知「无匹配」；表格行数与「共 N 位用户」对不上；「在职·激活 / 已停用」也只筛当前页——平台超管会漏判账号状态。
- Suggestion：后端 `/admin/users` 加 `q / role / tenant_id / department_id / is_active`，前端把筛选值放进 queryKey、用 react-query 做服务端筛选、筛选变化回第 1 页。短期止血：文案改「本页筛选」、筛选时隐藏分页总数。

### QA-4 `Users.tsx` loadUsers 无防过期响应，快速切换状态/翻页时旧响应覆盖新视图
- Dimension: 8 并发 | Severity: minor | 工作量: S
- Evidence：`Users.tsx:56-77` 每次 `page/filterActive` 变化都发请求，无 abort、序号或 alive 标记，`setUsers(res.items)` 谁最后返回用谁。
- 后果：从「已删除」快速切回「在职（全部）」时，可能在在职视图显示软删行（只带「恢复」动作），或反之。
- Suggestion：随 QA-5 迁移到 `useQuery({ queryKey: ['admin-users', page, status], placeholderData: keepPreviousData })`。

### QA-5 数据获取两套范式：react-query（27 文件 55 处 hook）与手写 useEffect+useState 加载器（42 文件）并存
- Dimension: 6 / 8 | Severity: minor | 工作量: L（按域逐步迁移）
- Evidence：Grep（排除测试）`useQuery(|useMutation(` 55 处 / 27 文件；`useEffect(` 52 处 / 42 文件；手写加载器例：`Users.tsx:56-86`、`Members.tsx`、`Settings.tsx`、`EnterpriseManagement.tsx`、`market/*Tab.tsx`、`components/spider/*Tab.tsx`；`index.tsx:10-13` 声明「react-query 全局客户端（轮询/缓存/失焦暂停统一托管）」，但门禁 F-3 只禁 `setInterval`（`tools/check/frontend.sh:107-117`）。
- 后果：加载态、错误态、竞态、重试、缓存失效各页各写一套，QA-4 类竞态反复出现；页面间写后无法用 `invalidateQueries` 联动刷新。
- Suggestion：约定「读 useQuery、写 useMutation」，新代码强制；加门禁 F-8 禁止在 pages/components 写 `useEffect(() => { …service… }, …)`（白名单逐步收敛）。

### QA-6 OpenAPI 生成类型零消费，服务层 116 个手写接口/类型，契约漂移只能运行时暴露
- Dimension: 6 | Severity: **major** | 工作量: M→L（先漂移门禁，再按域替换）
- Evidence：`frontend/shared/src/index.ts:11-12` 导出 `components/paths/operations`；`package.json:15` 有 `gen:api`；`shared/src/api/schema.d.ts:7,34,788` 覆盖 login、permissions、admin/users；但 admin 与 official src 里 Grep `components\[|paths\[|operations\[` **0 条**；`frontend/admin/src/services/**` 的 `^export (interface|type)` **116 处** / 24 文件（如 `users.ts:6-37`、`spiders.ts:10-101`、`capabilities.ts:8-377`）。已有漂移痕迹：`capabilities.ts:21-23`（「QA-12：后端恒返回 int（0/1），不是 boolean」）而 `patchFeatured` 发送 boolean（`:207-215`）；`spiders.ts:13,43,44` 用 `| string` 把联合类型放宽成 string；`fetchAdminStats<T>`、`fetchUsersPage<T>` 由调用方随意指定泛型（`admin.ts:8-9,22-27`），等于无类型。
- 后果：后端改字段名/类型时 `tsc` 与构建照过（`frontend-build.txt` exit=0 不能说明契约一致），问题只在界面暴露；`gen:api` 产物是摆设。
- Suggestion：① 门禁 `npm run gen:api && git diff --exit-code frontend/shared/src/api/schema.d.ts` 保证 schema 新鲜；② shared 提供 `type Schema<K extends keyof components['schemas']> = components['schemas'][K]`，服务层返回类型改引用生成类型，从 users、auth、capabilities 高频域开始；③ frontend.sh 统计手写 interface 数量，只减不增。

### QA-7 客户端类型与运行时不一致：拦截器已返回 `response.data`，AxiosInstance 签名仍说返回 AxiosResponse；`unwrap` 不检查 `success`
- Dimension: 6 | Severity: minor | 工作量: S
- Evidence：`shared/src/api/client.ts:47-48` `(response) => response.data`，返回类型仍 `AxiosInstance`（`:24`）；于是到处 `unwrap(envelope: unknown)`（`shared/src/api/envelope.ts:16-17`）与双重断言（`usePermission.ts:23` `resp as unknown as { data?: string[] }`、`spiders.ts:214` `res as unknown as Blob`）；`unwrap` 直接取 `.data` 不看 `success`/`code`。
- 后果：类型系统无法约束服务层，断言让 QA-6 迁移无处着力；若后端 HTTP 200 且 `success=false`（是否会这样**未验证**），服务层静默返回 `null`。
- Suggestion：shared 提供带类型 `request<T>(config): Promise<ApiEnvelope<T>>` 封装或用 axios 泛型重写实例类型；`unwrap` 在 `success === false` 时抛出带 `code/message` 的错误。

### QA-8 「记住我（7天）」前后端都未实现 7 天语义；JWT 明文长期存 localStorage 且前端不查过期
- Dimension: 1 对外承诺 / 4 安全 | Severity: **major** | 工作量: M
- Evidence：`Login.tsx:195` 文案「记住我（7天）」；`useAuthStore.ts:22` 剥掉 `rememberMe` 后才调 `apiLogin`；`services/auth.ts:9` 声明了 `remember_me` 但不发送；Grep `backend/app` 的 `remember_me` **0 条**；`useAuthStore.ts:43-53` zustand `persist` 默认 localStorage（key `auth-storage`）存 `token/user/isAuthenticated`，无 `expires_at`，水合不校验。
- 后果：界面「7 天」无任何实现，会话寿命完全由后端 JWT exp 决定（未读，**未验证**）；过期后本地仍显示已登录并渲染受保护外壳，直到第一个 401 才被踢出；Bearer token 可被任意 XSS 读取，而 admin 会渲染导入资产的 Markdown（`react-markdown`，`MarkdownBody.tsx` 未读，是否开 raw HTML **未验证**）。
- Suggestion：`remember_me` 发给后端、由后端决定 exp 并在响应返回 `expires_at`；前端持久化 `expires_at`、水合时过期即清空；中期改 httpOnly Refresh Cookie + 内存 Access Token；做到之前把文案改成与实际一致。

### QA-9 退出登录不清 React Query 缓存，同标签页换账号/换租户后可能先显示上一个账号的缓存数据
- Dimension: 4 租户隔离（界面层） | Severity: **major**（多租户 SaaS） | 工作量: S
- Evidence：`index.tsx:11-13` 在模块内创建 `queryClient` 且未导出给认证层；admin/src Grep `queryClient.(clear|removeQueries|resetQueries)` **0 条**；两处退出路径（`services/api.ts:15`、`components/AdminLayout.tsx:87`）只调 `logout()`，`useAuthStore.ts:36-41` 只清权限缓存（注释写「防跨账号残留」，只做了一半）。
- 后果：react-query 默认 `staleTime=0`、`gcTime=5min`；租户 B 登录后同一 queryKey 的页面挂载时**先渲染租户 A 的缓存数据**再后台重拉；queryKey 是否带 tenant/user 维度未逐一核对（**未验证**）。
- Suggestion：`queryClient` 抽成单例模块，在 `logout()` 里 `queryClient.clear()`；租户相关 queryKey 统一 `['t', tenantId, …]` 前缀；加「A 退出 → B 登录不闪数据」e2e。

### QA-10 未用 antd `<App>` 包裹，静态 `message` 读不到主题上下文；测试日志有 antd 弃用与上下文告警
- Dimension: 6 / 9 | Severity: minor | 工作量: S–M
- Evidence：`frontend/admin/src/index.tsx:21-37` 只有 `ConfigProvider`；测试记录 `frontend-test-admin.txt:50-68`（`DutyKeysTab.tsx:39` 报 "Static function can not consume context like dynamic theme"）、`:8`（`Statistic valueStyle` 已弃用），`frontend-test-official.txt:9-26`（`Register.tsx:110`）。
- 后果：BRAND_TOKENS 主题（`index.tsx:24-33`）对 message / notification 不生效；antd 下个大版本移除弃用 API 会直接出错；测试噪声掩盖真正的 console.error。
- Suggestion：根节点包 `<App>`，经 `App.useApp()` 取 message/modal/notification；统一清理弃用 API；setupTests 把 antd deprecated 警告设为测试失败。

### QA-11 工具链停在 CRA 5.0.1 + TypeScript 4.9；测试与类型依赖放在 `dependencies`；`npm audit --omit=dev` 报 44 个漏洞（2 critical / 20 high）且无法常规修复
- Dimension: 4 依赖 / 7 可维护性 | Severity: **major** | 工作量: L
- Evidence：`frontend/admin/package.json:22,25`、`frontend/official/package.json:21-22`、`frontend/shared/package.json:22`：`react-scripts 5.0.1`、`typescript ^4.9.5`；`admin/package.json:7-14`、`official/package.json:7-14`：`@testing-library/*`、`@types/*`、`@types/node ^16`、`@testing-library/user-event ^13.5` 都在 `dependencies`；`npm-audit.txt:55` 汇总行，漏洞路径属 CRA 构建与开发服务器链路（`webpack-dev-server/sockjs/uuid`、`websocket-driver`、`shell-quote`、`workbox-build`、`bfj/jsonpath/underscore`，`:1-53`），`:34` 显示 `--force` 会装 `react-scripts@0.0.0`（破坏性）；两应用 jest 配置几乎一模一样复制（`admin/package.json:54-97` vs `official/package.json:49-92`），`transformIgnorePatterns` 已长到难维护（admin `:94`）；jest 走 babel-jest，测试时不做类型检查。
- 后果：构建工具链放在 dependencies 使 `--omit=dev` 分不出运行时与构建风险，审计长期噪声大、真正的运行时漏洞被淹没；critical/high 主要影响本地开发服务器与构建机，对线上 bundle 实际影响**未验证**，但仍是供应链风险；TS 4.9 用不了 `satisfies` 之后的新特性，也限制 openapi-typescript 等工具升级。
- Suggestion：短期（S）testing-library、@types、typescript、react-scripts 挪到 devDependencies，CI 分别跑 `npm audit --omit=dev` 与全量审计并设阈值，统一 jest 预设（抽 `frontend/jest.preset.js`）；中期（L）迁 Vite + TS 5.x + Vitest，shared 改源码直连（去掉「先 build dist 再消费」），先迁 official（体量小、15 套件）再迁 admin。

### QA-12 e2e 只有一条全桩冒烟，单测在服务层整体 mock，HTTP 线上契约（请求头、编码、信封）无任何测试覆盖
- Dimension: 3 证据有效性 / 2 | Severity: **major** | 工作量: M
- Evidence：`frontend/admin/e2e/` 只有 `smoke.spec.ts` 一个 `test`（`:79-98`，登录 → 仪表盘 → 用量 → 成员）；`stubApi` 对所有 `/api/v1/**` 返回 200、未命中一律 `json(null)`（`:75`），不校验 Authorization / Content-Type；`playwright.config.ts:17-18` 依赖事先构建的 `build/`，但 `admin/package.json:33` `e2e` 脚本不先构建；服务层无测试（Glob `admin/src/services/**/*.test.*` = 0）；页面测试普遍 `jest.mock('../services/…')`；e2e 是否在 CI 运行**未验证**。
- 后果：391 + 90 条全绿单测（`frontend-test-admin.txt:78-83`、`frontend-test-official.txt:78-83`）无法证明 QA-1、2、9 这类跨层缺陷不存在——对「前端可交付」是空心证据。
- Suggestion：shared client 加契约单测（自定义 adapter 断言 FormData、Bearer 头、401 回调）；e2e 桩对鉴权路由校验请求头、未知路由改 404 并让测试失败；补关键旅程 e2e（能力导入、用户管理筛选与恢复、退出后换租户登录）；`e2e` 加 `pree2e: npm run build` 或 CI 显式构建，并确认 CI 执行。

### QA-13 前端门禁脚本有死代码与失效分支，F-5 互引检测比描述弱，F-7 注释与实际矛盾
- Dimension: 3 / 7 | Severity: minor | 工作量: S
- Evidence（`tools/check/frontend.sh`）：`:29-34` 第一次 `hits=` 被 `:36` 直接覆盖（死代码）；`:39` sed 模式 `.*/src/((admin|official))/src/.*` 匹配不上真实路径 `frontend/admin/src/...`，`app` 永远是完整路径，「同应用排除」未生效（现在能工作只因正则要求路径里有 `../`）；`:30,36,50,62` 只匹配单引号 `from '…'`，双引号 import 可绕过；`:11-12` 注释「待启用：F-7」但 `:143` 已执行 f7；F-2（`:83`）只能匹配单行写法。
- 后果：`frontend-gate.txt` exit=0 对 F-5 的保证强度被高估。
- Suggestion：删死代码；改 `grep -E "from ['\"]"`；F-5 改为按「文件所属应用 vs 被引路径」判断（或用 eslint `import/no-restricted-paths`）；更新文件头注释；另增 F-8（OpenAPI 漂移）与 F-9（bundle 预算）。

### QA-14 包体积无预算门禁：admin 主包 255 kB gzip + 128 kB 共享 chunk；官网主包 168 kB gzip
- Dimension: 5 | Severity: minor | 工作量: S–M
- Evidence：`frontend-build.txt:19-20`（admin `main` 255.19 kB、`7955.chunk` 127.62 kB）、`:105`（official `main` 167.69 kB）；路由级拆分已在做（大量小 chunk，`:21-76`）；主包构成**未验证**。
- 后果：官网是营销入口，168 kB gzip 首屏 JS 拖慢 LCP；admin 首次加载近 400 kB gzip；无预算体积只会增长。
- Suggestion：`source-map-explorer` 定位主包构成（重点 antd、recharts、framer-motion、react-markdown 是否进入口）；重型图表与 Markdown 挪进路由 chunk；引入 size-limit / bundlesize 作 F-9。

### QA-15 开发代理目标与官网地址硬编码端口，与「配置即代码」不一致
- Dimension: 7 | Severity: minor | 工作量: S
- Evidence：`frontend/official/src/setupProxy.js:7` `target: 'http://127.0.0.1:9111'`；`frontend/admin/src/pages/Login.tsx:13` 缺省回落 `'http://localhost:9113'`；宪法 R1 机械检查只覆盖 backend 与 scrapy（此处仅违反原则精神）；admin `setupProxy.js` 未读（**未验证**）。
- 后果：`run.py --env` 或改端口部署时开发代理不跟随；生产构建漏配 `REACT_APP_OFFICIAL_URL` 时注册链接指向 localhost。
- Suggestion：`process.env.PROXY_TARGET || 'http://127.0.0.1:9111'`，由 `scripts/runlib` 从 Dynaconf 注入；构建时校验必填 `REACT_APP_*`（为空即失败）。

### QA-16 角色缺省回落规则前后不一致，删除保护按用户名 `'admin'` 硬编码
- Dimension: 6 / 8 | Severity: minor | 工作量: S
- Evidence：`Users.tsx:131,201,315` `u.role || (u.is_admin ? 'admin' : 'operator')`（缺省 **operator**），`hooks/usePermission.ts:60` `user?.role || (user?.is_admin ? 'admin' : 'viewer')`（缺省 **viewer**）；`Users.tsx:226` `record.username !== 'admin'` 决定是否显示删除按钮。
- 后果：无 role 字段的旧数据在用户管理显示「操作员」、自身权限却按「只读」——界面自相矛盾；删除保护绑在用户名上：真平台超管改名后出现删除按钮（后端防自锁守卫仍在，仅界面误导），普通用户起名 admin 则无法删除。
- Suggestion：抽共享 `normalizeRole()` 统一缺省（与后端 `_ROLE_PERMISSIONS` 对齐）；删除按钮改由后端下发 `can_delete`，或按 `is_platform_admin` + 「不是当前用户」判断。

### QA-17 权限缓存是模块级可变变量，不通知其他组件，已挂载消费者可能停在「未就绪」
- Dimension: 6 | Severity: minor | 工作量: S–M
- Evidence：`hooks/usePermission.ts:13-15`（`cachedPermissions/loadState` 为模块变量）、`:62-72`（只有触发刷新的组件实例经本地 `revision` 重渲染）。
- 后果：多个组件同时用 `usePermission`（布局 + 页面）时只有发起者更新，菜单与按钮级权限可能短暂不一致。
- Suggestion：权限放进 zustand（与 auth 同一 store）或 `useQuery(['permissions', userId])`，由登录/退出统一驱动；与 QA-2、QA-9 一起处理。

### QA-18 用户页筛选控件无可访问名称
- Dimension: 9 可访问性 | Severity: minor | 工作量: S
- Evidence：`Users.tsx:267-298` 4 个 `Select` 与 `Input.Search` 只有 placeholder/当前值，无 `aria-label` / label；对比 `Login.tsx:170-192` 用了 `Form.Item label`（正确做法）。
- 后果：读屏用户无法区分「角色/公司/部门/状态」四个下拉。
- Suggestion：统一补 `aria-label`；jest 引入 `jest-axe` 从高频页面做基线。国际化：全站中文硬编码、antd zhCN，本切片未见多语言需求，不作缺陷。

### QA-19（证据有效性）已记录的执行日志有截断，漏洞清单不完整
- Dimension: 3 | Severity: minor | 工作量: S
- Evidence：`frontend-test-admin.txt:2-3`、`frontend-test-official.txt:2-3` 从堆栈中途开始；`npm-audit.txt:1-2` 从依赖链中途开始，44 个漏洞只列一部分；退出码与汇总行完整。
- 后果：能证明「通过/失败」，不能追溯具体漏洞包与测试告警。
- Suggestion：manager 保存完整日志（`npm audit --omit=dev --json > evidence/npm-audit.json`），或在截断处标注省略行数。

---

## Dimensions checked
1. 标准符合 ⚠️ — 无 spec/产品层，按代码内注明的 FR/GWT 意图：偏离见 QA-3（本地筛选语义）、QA-8（「7 天」未实现）。
2. 标准质量 ➖/⚠️ — 输入无 GWT；测试质量问题在 QA-12（服务层整体 mock、e2e 仅一条）。
3. 证据有效性 ⚠️ — 构建、tsc、门禁、单测均有命令 + 退出码；但单测 mock 服务层、e2e 全桩不校验请求头属空心证据（QA-12）；F-5 比描述弱（QA-13）；日志截断（QA-19）。
4. 安全 ⚠️ — QA-8（token 存储与寿命）、QA-9（跨租户缓存残留）、QA-2（先拉权限后写 token）、QA-11（依赖漏洞）；登录回跳已防开放重定向；react-markdown XSS 面**未验证**。
5. 性能 ⚠️ — QA-14（包体积无预算）；QA-3 本地筛选也是功能问题；未见无界请求（列表都带 limit/page_size，`capabilities.ts:43` 固定 50）。
6. 契约一致性 ⚠️ — QA-1、6、7、16、17。
7. 宪法合规 ✅/⚠️ — `arch.txt` R1–R13、B1–B4、FR-14、PL 全过（exit=0），检查范围在后端与基建；前端相关只有「配置即代码」精神（QA-15）与前端自有 F-5 边界（通过但检测偏弱，QA-13）；未见违反依赖方向（shared 不反向依赖应用，F-5 通过）。
8. 边界 ⚠️ — 超量 QA-3（>20 用户）、并发 QA-4、权限 QA-16/17；空态与错误态区分得好（`Users.tsx:67-68,243-258,303-308`）。
9. 产品价值与体验 ⚠️ — 无产品层与截图，只能依据代码与已记录执行：两条关键运营链路可能在真实环境失效或误导——能力导入（QA-1，待复现）与用户检索（QA-3）；「记住我」承诺与实现不符（QA-8）；可访问性 QA-18；设计 QA 所需截图**不在输入中**，视觉层无法判断。

## Strengths（改进时应保留）
1. 共享层边界清楚：`shared/src/api/client.ts:1-6` 说明用工厂不用单例（避免把 admin 鉴权逻辑带进官网）；`ApiEnvelope` 单处定义并由门禁 F-6 机械保证（`tools/check/frontend.sh:59-78`、`envelope.ts:1-6`），`frontend-gate.txt` exit=0。
2. 服务层统一解包信封：页面拿到业务结构，二进制下载作为白名单单独处理（`spiders.ts:1-7,202-244`、`admin.ts:1-4`）——迁移到 OpenAPI 类型的理想接入点。
3. 防开放重定向：两处都做（`services/navigation.ts:16-22`、`pages/Login.tsx:44-52` `safeInternalPath`）；401 后导航保留来源并提示「会话过期」（`Login.tsx:99-103,160-161`）。
4. 边缘态与权限降级设计认真：失败与空表分开（`Users.tsx:67-68,303-308`），不同视图不同空态（`:243-258`）；权限未就绪走保守降级菜单（`usePermission.ts:1-6,85-89`）；非超管访问平台路由看到与未登录一致的 404（`ProtectedRoute.tsx:27-33`）；退出时清权限缓存（`useAuthStore.ts:37-39`）。
5. 已记录执行全绿并做了路由级拆分：shared build、两应用 `tsc --noEmit` 与 build exit=0（`frontend-build.txt:6,8,92,94,141`）；admin 54 套件 391 条、official 15 套件 90 条全过（`frontend-test-admin.txt:78-83`、`frontend-test-official.txt:78-83`）。

## Improvement themes
1. **API 契约单源化**（QA-1、6、7、19 契约证据部分）— 目标：服务层请求/响应类型全部来自 `schema.d.ts`；client 带类型返回信封；有契约单测与漂移门禁；上传走真正 multipart。顺序：修 QA-1 默认 Content-Type + client 契约单测（S，先做）→ `gen:api` 漂移门禁 F-8（S）→ `request<T>` 类型封装、`unwrap` 查 success（S）→ 按域替换手写类型 auth/users → capabilities → spiders（M–L）。
2. **认证态与会话安全**（QA-2、8、9、17）— 目标：先写 token 再拉权限；认证、权限、查询缓存由同一会话对象管理、退出全清；token 过期时间显式存前端（或 httpOnly Refresh）；「记住我」由后端决定寿命。顺序：退出 `queryClient.clear()` + 调整登录顺序（S）→ 权限进 store 或 react-query（S–M）→ 前后端联调 remember_me 与 expires_at 并改文案（M）→ 评估 httpOnly Cookie（M–L，需与后端协同）。
3. **数据获取与列表语义统一**（QA-3、4、5）— 目标：读 useQuery、写 useMutation；列表筛选/分页/总数全由服务端提供；不再有手写竞态。顺序：用户管理页改服务端筛选（M，含后端参数）→ 门禁禁新增手写加载器 → 按访问频率逐页迁移（L）。
4. **工具链现代化与依赖卫生**（QA-11、10、14、15）— 目标：Vite + TS 5 + Vitest；dependencies 只含运行时依赖，`--omit=dev` 审计干净；antd `<App>` 上下文到位；bundle 预算；端口与地址来自配置。顺序：依赖归位 + jest 公共预设 + 代理/地址配置化 + 包 `<App>`（S）→ bundle 分析 + 预算门禁（S–M）→ 先迁 official 到 Vite 再迁 admin、shared 源码直连（L）。
5. **测试与门禁有效性**（QA-12、13、18、19）— 目标：关键旅程 e2e 在 CI 运行，桩校验请求头与未知路由；门禁脚本无死代码、覆盖双引号 import；可访问性基线；证据日志完整。顺序：修门禁脚本（S）→ e2e 桩收紧 + 三条旅程接入 CI（M）→ jest-axe 基线（S）→ 证据落盘规范（S）。

## 需 manager 执行的验证（未验证项）
1. QA-1 复现（仓库根，Node ≥18）：`node -e "const axios=require('axios');const c=axios.create({headers:{'Content-Type':'application/json'}});const fd=new FormData();fd.append('file',new Blob(['x']),'a.md');c.post('http://x/y',fd,{adapter:async(cfg)=>{console.log(typeof cfg.data, cfg.data instanceof FormData, String(cfg.data).slice(0,80));return {data:{},status:200,statusText:'OK',headers:{},config:cfg}}})"`——缺陷成立预期输出 `string false {"file":{}}`。
2. QA-2：`grep -n "permissions" -A5 backend/app/api/v1/auth*.py` 确认 `/auth/permissions` 是否依赖当前用户（是否会 401）。
3. QA-9：`grep -rn "queryKey" frontend/admin/src --include=*.tsx | grep -v test | head -50`。
4. QA-8/9 XSS 面：`grep -rn "rehype-raw\|dangerouslySetInnerHTML\|skipHtml" frontend/*/src`。
5. QA-12：`grep -n "e2e\|playwright" .github/workflows/ci.yml`。
6. QA-14：`GENERATE_SOURCEMAP=true npm run build -w admin && npx source-map-explorer frontend/admin/build/static/js/main.*.js`。
7. QA-11/19：`npm audit --omit=dev --json > .sdlc/_review/2026-09-27-project-audit/evidence/npm-audit.json`。

## 返回项
- Decisions：无（仅出报告，不推进状态）。
- Open questions：Q-1 用户管理检索是否需要跨页？推荐服务端筛选（备选：文案改「本页筛选」）。Q-2「记住我」寿命由谁决定？推荐后端按 remember_me 设 exp（备选：删掉「7天」文案）。Q-3 是否启动 CRA → Vite？推荐先迁 official 验证（备选：只做依赖归位与审计分层）。
- Product-delta：无（产品层不存在）。
- Lesson（已核实）：axios 1.x 实例级 `Content-Type: application/json` 会把 FormData 序列化成 JSON（`node_modules/axios/lib/defaults/index.js:46-57`）；上传类服务不能只靠服务层被 mock 的页面测试，必须有 client 级契约测试。
