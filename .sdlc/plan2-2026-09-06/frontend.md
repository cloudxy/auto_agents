# 前端深层次问题审查（2026-09-06）

范围：`frontend/{admin,official,shared}`（React 19 + TS + antd v6，npm workspaces）；对照 `backend/app/api` 契约。审查方式：只依据代码事实 + 本机可复现验证（`npm run build:shared/admin/official` 全部 exit 0；admin jest 13 用例通过、official 3 用例通过；`scripts/check-frontend.sh` 0 违规）。未读 .sdlc/.scratch/docs/plan/docs/research。

## 总体判断

这套前端的"工程外壳"明显高于"内核质量"：workspaces + shared 编译产物、lazy 路由 + 双层 ErrorBoundary、统一信封、grep 式门禁脚本、带回归注释的测试，都做得很像样。但内核有三条断层。**其一，数据层是双轨制**——react-query 只迁移了 6 处（SpiderLogs/Nodes/Spiders/AdminLayout/LogDrawer/useAiPlanFlow），其余 20 个页面仍是 useState+useEffect 手写取数，没有取消/竞态防护，错误处理各自为政（toast、静默吞掉后伪装成空态、`.catch(()=>{})` 并存）；**其二，类型契约是表演性的**——openapi-typescript 生成了 8394 行 schema.d.ts 但业务代码 0 消费，service 层 100% 手写 `unwrap<T>` 且由调用方泛型自定类型，契约漂移在编译期不可见；**其三，测试防线只覆盖了表演区**——约 13k 行应用代码只有 16 个用例（≈1.5% 文件覆盖率），26 页只测 4 页，而官方站两个真实的功能性 bug（注册成功态永不显示、技能广场搜索框无法键入）恰好都落在未测试区。权限模型存在"下发权限码 ↔ 端点实际要求 ↔ 页面内守卫"三源互相矛盾的事实漂移。结论：当前形态能跑、能交付，但每一层"看起来有的机制"（codegen、react-query、R5 权限单源、F-4 令牌门禁）都只落地了一半，需求增长时新代码不知道该跟哪一半。

---

## 深层次问题清单（按严重度排序）

### 1. 官网企业注册：service 已解包、页面二次 `.data`，注册成功但成功态永不显示
**严重度：高**（核心转化流功能性 bug，可复现）

**证据**：
- `frontend/official/src/services/signup.ts:11-12` — `tenantSignup` 已 `unwrap<SignupResult>(r)`，返回 `{tenant, owner}`；
- `frontend/official/src/pages/Register.tsx:29` — `const result = await tenantSignup(values).then((r) => (r as unknown as { data: SignupResult }).data)`，对已解包结果再取 `.data` → `undefined`；
- 后端链路印证：`backend/app/api/v1/tenant_signup.py` `return created(data=result)`（信封），shared 拦截器再剥 axios 层（`frontend/shared/src/api/client.ts:48`），`unwrap` 取信封 `data`——即 service 返回值已是业务载荷；
- 结果：`setDone(undefined)` → `done ? 成功面板 : 表单` 永远走表单分支，仅 toast 一闪"注册成功"。用户以为失败 → 重复提交 → 撞后端唯一性 422。测试未覆盖：official 仅 3 个用例（App smoke + SkillsSquare 渲染/XSS）。

**为什么深层**：`unwrap` 的返回类型是 `Promise<SignupResult>`，TypeScript 本应在此处报 `Property 'data' does not exist`——但页面用了 `as unknown as { data: SignupResult }` 双重断言把编译器闭嘴了。这暴露的不是手滑，而是"断言即可绕过类型系统"没有约束，叠加该路径零测试。

**解决方案**：
1. 删掉 Register.tsx:29 的 `.then(...)`，直接 `setDone(await tenantSignup(values))`；顺手全局封禁双重断言：tsconfig 加 `@typescript-eslint/no-unnecessary-type-assertion`（需 TS≥5）或先以 ESLint `no-unsafe-assignment` 过渡规则扫描 `as unknown as`（当前仓库出现 4 处业务代码）。
2. 为官方注册页补 1 条行为测试：mock signup resolve payload → 断言成功面板出现"管理员账号"文案。可放进现有 SkillsSquare.test 同级文件，成本 <30 分钟。
3. 取舍：若想保留"信封可能有嵌套 data"的容错，应在 `unwrap` 单点做（判断 payload 形状），而不是在每个调用点各断言一次。

### 2. 官网技能广场搜索框被受控值锁死：用户无法键入任何字符
**严重度：高**（公开页核心交互失效，现网可直接验证）

**证据**：`frontend/official/src/pages/SkillsSquare.tsx:80-89`
```tsx
<Input
  value={keyword}                                        // 受控
  onPressEnter={(e) => applyKeyword(...)}                // 回车才提交
  onChange={(e) => !e.target.value && applyKeyword('')}  // 仅清空时回写
```
`value={keyword}` 受控，但 onChange 在非空输入时不更新 state → React 重渲染把 DOM 值弹回 `keyword`，**键盘输入全部被吞**；唯一生效的是 allowClear 清空与 URL `?q=` 深链。搜索功能实际处于"只能清空、不能输入"状态。测试（SkillsSquare.test.tsx）mock 了 service、只断言渲染，未触碰输入框，故漏网。

**为什么深层**：这是"受控 + 回车提交"模式实现到一半的产物（正确做法需要 draft state 分离输入态与提交态）。它说明官方站的交互改动没有"打开页面点一遍"的最低验证，也没有任何 e2e/交互测试兜底——同类问题在其他官方页同样可能存在。

**解决方案**：
1. 最小修复：`onChange={(e) => setKeyword(e.target.value)}`，保留回车提交（`onPressEnter` 内 `applyKeyword(keyword)`）；或 antd `Input.Search` 自带 enterButton 语义，直接替换可同时修掉手写交互。
2. 补交互测试：`fireEvent.change(input, {target:{value:'爬虫'}})` → `await screen.findByText(...)` 断言请求参数带 `q=爬虫`（断言 listPublicSkills 调用参数即可）。
3. 治本：官方站 4 个数据页（SkillsSquare/Capabilities/Home SkillsSection）已装了 react-query（QueryClientProvider 在 index.tsx 挂着）却仍手写 `load()`，把这三处迁到 `useQuery({queryKey:['skills',q,cat]})`，输入竞态（连打回车乱序返回）也一并消除。

### 3. 数据层双轨制：react-query 迁移完成度 ~23%，其余页面手写取数且无竞态防护
**严重度：高**（架构级不一致，随页面数线性恶化）

**证据**：
- 使用 react-query 的仅 6 处：`pages/Spiders.tsx`、`pages/SpiderLogs.tsx`、`pages/Nodes.tsx`、`components/AdminLayout.tsx`、`components/spider/LogDrawer.tsx`、`hooks/useAiPlanFlow.ts`（AiPlans 经 hook 间接使用）；
- 其余 20 个页面手写 `useState+useEffect` 取数：Dashboard.tsx:64-83（`Promise.all` + 两个接力 useEffect + `.catch(()=>{})` 静默吞掉质量报告失败）、Data.tsx:95-103、Users.tsx:49-65、Members.tsx:51-63、LogCenter.tsx:52-74、官方站 SkillsSquare/Capabilities/Home 等；
- 错误处理三种范式并存：`message.error(apiErrorMessage(...))`（Users）、`catch(() => setItems([]))` 把网络错误伪装成"暂无已发布技能"空态（SkillsSquare.tsx:35-37、official Capabilities.tsx:20）、`.catch(() => {})` 完全静默（Dashboard.tsx:70,82）；
- 无一处使用 AbortController/queryKey 竞态防护：SkillsSquare 的 `load(keyword, category)` 连续触发时慢响应会覆盖新响应；Users 翻页（useEffect [page]）同样乱序可覆盖。
- 同一页面混用两套范式：Spiders.tsx 任务列表是 react-query（:79-91），registry/templates 仍是 useEffect 手写（:113-116）。

**为什么深层**：这不是"风格不统一"的审美问题，而是**缓存失效模型缺失**——react-query 那半有 staleTime/轮询/失焦策略，手写那半每次进页面重拉、写操作后靠人肉 `load()` 全刷（Users.tsx:96 `loadUsers(page)` 创建后整页重拉）。需求增长时：新页面抄手写模板 → 竞态/空态伪装 bug 复制扩散；改轮询策略 → 只改到 6 处。工单 78 的"react-query 全局托管"实际是半程停工，但没有断点清单。

**解决方案**：
1. 先立规矩再迁移：在 `src/queries/` 下按域建 hooks（`useUsers(page)`、`useMembers()`、`useStats()`），QueryClient 全局配 `retry:1` 已有，补 `staleTime` 默认 30s + `QueryCache.onError` 统一 toast（去掉各页 message.error 样板）。
2. 迁移顺序按风险排：Users/Data/Members（服务端分页 + 变更）→ LogCenter/Dashboard → 官方站 3 页。每个 service 对应一个 `useQuery` + `useMutation`+`invalidateQueries`，删掉手写 `load()`。工作量约 2-3 人日，可逐页 PR 化。
3. 门禁收口：check-frontend.sh 增 F-8 规则——`pages/**` 禁止 `useEffect` 内出现 `api.get|fetch[A-Z]` 直调（白名单豁免清单起步），让双轨制只能收敛不能新增。

### 4. 权限模型三源漂移：下发的 menu 码、后端端点实际要求、页面内守卫互相矛盾
**严重度：高**（viewer/member 等角色会看到必然 403 的功能；页面可达性与权限码对不上）

**证据**：
- 后端 `_ROLE_PERMISSIONS`（`backend/app/api/v1/auth.py:98-115`）给 **viewer/operator** 都发了 `menu:members`、`menu:usage`；但 members 全部端点要求 `require_tenant_manager`（owner/admin，`backend/app/api/v1/members.py:38-87`）→ viewer 点开"成员管理"即见"成员加载失败"错误墙 + 一个提交必 403 的"添加成员"按钮；
- `menu:spiders.nodes` 在前端 menuConfig.tsx:49 被引用，但**后端任何角色都不含此码** → 所有角色（含 admin）静态菜单都看不到"节点监控"，页面只能 URL 直达（Nodes.tsx 有 react-query 轮询，功能完整）；
- 页面内守卫覆盖不全：App.tsx:98 注释称 members "owner/admin 语义在页内守卫"、capabilities "权限由其内部 usePermission 控制"，但 grep 证实 `Members.tsx`/`Usage.tsx`/`Capabilities.tsx`/`Data.tsx` 均 **无 usePermission 调用**（Data.tsx 只用了按钮级 hasPermission）；守卫实际只有菜单过滤 + requireAdmin 路由两层，中间态（有菜单码、无操作权限）完全裸奔；
- 权限缓存空时菜单全量兜底（usePermission.ts:79-81，bea13b5 修复的故意行为）：后端瞬断时 viewer 也会看到 admin 全菜单，点击 403——菜单可见性"fail-open"、按钮"fail-closed"两套哲学混在同一 hook。

**为什么深层**：R5 的"权限单真相源"只统一了**发放渠道**（都从 /auth/permissions 读），没统一**语义映射**。menu 码在后端硬编码字典里"凭感觉"发，与端点守卫没有联动校验；前端页面守卫又各自决定要不要消费。这类漂移每次加角色/页面都会再发生，且 RBAC 页（RbacManagement）允许管理员改 DB 权限矩阵后，`menu:*` 与页面真实可达性的偏差会被进一步放大。

**解决方案**：
1. 后端收口：`_ROLE_PERMISSIONS` 与 `_helpers.py/deps.py` 的守卫做一致性测试——遍历所有路由的依赖（tenant_manager/require_admin），断言"能进端点的角色必有对应 menu 码"；立即修两处事实错误（viewer/operator 的 menu:members、补 menu:spiders.nodes 进 admin）。
2. 前端对齐：Members/Usage 页挂 `usePermission` + `hasPermission('menu:members')` 不满足时渲染 `<Result status="403">`（复用 Unauthorized 页），替代"页面能进、按钮必败"。
3. 把"menu 码 = 页面可达"变成生成物：后端从路由依赖表导出 page→minRole 映射（挂进 dump_openapi），前端 menuConfig 的 permission 字段 CI 校验之，消灭第三处人工同步。

### 5. 测试防线：≈1.5% 文件覆盖，26 页只测 4 页，且全部 mock 掉 service 层
**严重度：高**（上文 1、2 两个 P0 均为测试盲区直接漏网）

**证据**：
- 全仓测试代码 389 行（admin 5 suites/13 用例，official 2 suites/3 用例）对 ~13k 行应用代码；admin 26 页中仅 Members/LlmProviders/Skills/usePermission/App 被测，official 8 页仅 SkillsSquare/App；
- 未被测的高危面：登录/401 拦截器/ProtectedRoute（权限核心）、Users（服务端分页+本地过滤混搭）、Spiders 全家（核心业务，0 测试）、Dashboard/Data、官方站 Register；
- 既有测试全部 `jest.mock('../services/api')`——信封语义靠手写 mock 还原（Members.test.tsx:12 手搓 `{success,code,message,data}`），契约不真；好处是 Members 的 422 错误路径用例质量不错（真实行为测试），坏处是 service 函数本身的 unwrap/参数拼装从不被执行；
- CI 三阶段只跑 `npm run build`（根 package.json scripts），测试不在 CI 关卡内（前端无 `npm test -w` 门禁脚本）。

**为什么深层**：现有 16 个用例几乎都是"修完 bug 补回归"的产物（注释里全是工单号），属于守成而非探雷；两个 P0 都在"新写的交互路径"上。覆盖率低本身不是罪，罪在没有**分层策略**：哪些层必须测（service 解包、权限 hook、路由守卫）、哪些可以放（纯静态官网 Home）没有约定，导致测试只长在被投诉过的地方。

**解决方案**：
1. 立即补 3 类"高杠杆"测试（约 1 人日）：a) Register 成功路径（见问题 1）；b) SkillsSquare 键入→请求参数（见问题 2）；c) `services/` 层非 mock 直测：mock axios adapter 而非 service 本身，让 unwrap/参数拼装真实执行（axios-mock-adapter 或 MSW；MSW 还可跨用例共享信封 fixture，替代手搓信封）。
2. 把测试挂进门禁：根 package.json 加 `test:frontend`（两 workspace 串跑），CI 前端阶段改为 `build && test`；失败的 `npm test` 在 CI 是纯摆设这一条必须先修。
3. 定覆盖底线而非数字：约定"每个 service 文件至少 1 条真实解包用例 + 每个 requireAdmin/权限分支页面 1 条守卫用例"，新页面 PR 不满足不合并（code review checklist 化，不必上 coverage 工具）。

### 6. codegen 是摆设：schema.d.ts 8394 行 0 消费，service 层 100% 手写"调用方自定类型"
**严重度：中高**（契约漂移在编译期不可见，gen:api 流程白维护）

**证据**：
- `npm run gen:api`（根 package.json）→ `openapi-typescript` → `shared/src/api/schema.d.ts`（8394 行，与 openapi.json 同步生成于 09-03）→ `shared/index.ts:8` 导出 `components/paths/operations` ——但 grep 全前端 **无任何业务 import**；`shared/src/types/skills.ts:4-6` 自注释"批次 3 接入 codegen 后本文件届时退役"至今未退役；
- service 层泛型由**调用方**指定：`fetchAdminStats<T>(): Promise<T>`（services/admin.ts:8，Dashboard 传 Stats、Data 传 StatsData，两处手写字段各猜一遍 `/admin/stats` 的形状）；Users/Members/LogCenter 各自手写 `interface AuditLogItem` 等；
- 手写类型已现偏差实例：`SpiderTask.status: 'pending'|'running'|'completed'|'failed'|string`（services/spiders.ts:41，末尾 `|string` 使联合类型形同虚设）；`tsconfig skipLibCheck:true` 还会掩盖生成物自身的类型错误。

**为什么深层**：这套基建给人的安全感是"后端改字段 → gen:api 就同步"，实际同步的只是一个没人 import 的文件。真正的契约检查点（service 返回类型 = schema 路径响应类型）不存在，`<T>` 调用方泛型把类型责任推给了每个页面，等于没有契约。一旦后端改 `result_count` 为可选或分页从 `{items,total}` 变 `{list,count}`，前端要等运行时 undefined 才发现。

**解决方案**：
1. 分两步消费 schema，不必一步到位：第一步只在 **service 层**替换返回类型——`unwrap` 换成 `unwrapOp<'get','/spiders/tasks'>(res)`（一个基于 `operations['get /spiders/tasks']['responses'][200]` 的 helper，约 20 行），service 签名改为返回 schema 类型，页面代码零改动；
2. 第二步删手写：`components['schemas']['Task']` 替换 `spiders.ts` 内 13 个 interface；`shared/types/skills.ts` 正式退役。每替换一个 service 跑一次双端 build，冲突点即契约漂移点，逐个对齐；
3. 门禁：`dump_openapi.py` + codegen 进 pre-push，schema.d.ts 有 diff 而业务未同步时 CI 提示；迁移完成后再加 ESLint `no-restricted-syntax` 禁止 service 层再写 `unwrap<字面量类型>`（保留 `<T>` 过渡白名单直至清零）。

### 7. 会话持久化：rememberMe 是假功能，token 无条件永久落 localStorage
**严重度：中**（安全语义与 UI 承诺不符；共享机器场景凭据长期残留）

**证据**：`frontend/admin/src/store/useAuthStore.ts:45-53`
```ts
partialize: (state) => {
  if (!state.rememberMe && !state.token) return {} // 注释自认: "we might want to clear on close, but zustand/persist is localStorage"
  return { token: state.token, user: state.user, ... }
```
条件 `!rememberMe && !token` 意味着**只要已登录就永远持久化**（勾不勾"记住我"无差别）；Login.tsx:80 承诺"记住我（7天）"，但全仓无任何 7 天过期逻辑（无 expiresAt、无 rehydrate 校验时间戳）；rememberMe 也从未发给后端（login() 里剥掉，services/auth.ts:9 的 `remember_me?` 是死字段）。另外 persist 无跨 tab 同步：A 标签页 401 登出后，B 标签页仍持内存 token 继续发请求直到下一次 401。

**为什么深层**：这是 skill gotchas 里"localStorage persists across browser restarts"的教科书案例——已知坑、写了承认注释、依然上线。深层原因是有意半途而废："sessionStorage 方案"被 zustand/persist 能力限制劝退后，没有把 UI 承诺降级（去掉 7 天文案），留下了"功能在、语义错"的状态，安全审计时会被当成越权残留项。

**解决方案**：
1. 短期（10 分钟）：login 成功后写 `localStorage.setItem('auth-exp', String(Date.now()+7*24h))`（勾选时）或不写；App 挂载时 rehydrate 后校验过期即 `logout()`。文案与行为即刻一致。
2. 中期：记住我=7 天 → persist 到 localStorage；不勾 → 内存态（ zustand 无 persist 的裸 store）+ 可选 sessionStorage。用两个 store 或 `createJSONStorage(() => remember? localStorage: memoryStorage)` 动态切换即可，zustand 原生支持。
3. 补 1 条 usePermission.test 同款回归用例：`useAuthStore.getState()` 直测 partialize 输出（当前这段逻辑 0 测试）。

### 8. 菜单三重来源叠加：静态 menuConfig + 动态 /auth/menus + 兜底全量，keys/权限码/icon 三处人工同步
**严重度：中**（已产生实际漂移；每次加页面要改 3 处）

**证据**：
- AdminLayout.tsx:24-53：动态菜单优先、空/失败回退静态 menuConfig，回退又叠加 usePermission 的权限过滤与 tenantOnly 递归过滤——同一次渲染的菜单可见性由 3 层逻辑共同决定，行为组合难以推断（权限缓存空 + 动态菜单失败 = 全量菜单；缓存空 + 动态菜单成功 = DB 口径）；
- 两源 key 需人工保持同构：动态 key = `m["path"] or f"grp-{id}"`（auth.py:155），静态 key = 硬编码路径；icon 靠 `MENU_ICON_MAP` 字符串映射（menuConfig.tsx:99-105），DB 里写错 icon 名 → 菜单无图标但不报错；
- `AdminLayout.tsx:34` `const toItems = (nodes: DynamicMenuNode[]): any[]`——全仓业务代码唯一的显式 `any`，恰好藏在最复杂的分支里；
- Menu `selectedKeys={[location.pathname]}`：父级分组（如 /spiders/tasks 下的 /spiders）不会展开高亮，属同源小病。

**为什么深层**：菜单从"前端配置"演进到"DB 动态下发"是 SaaS 化的正确方向，但旧源没删、回退语义没定义（回退应该保可用性还是保权限正确性？usePermission 选了可用性、静态过滤选了正确性，两哲学共存）。未来加"菜单排序/多语言"必然第四源。

**解决方案**：
1. 明确单源：动态菜单为唯一真相源；静态 menuConfig 仅保留 `pageTitleFor` 与首次渲染骨架（可接受闪变），删除其 permission 字段的过滤职责（动态菜单后端已按权限过滤，auth.py:153-154）。回退时明确策略：回退到"仅 dashboard + 提示菜单服务暂不可用"，而非全量——比 fail-open 更可预期（后端同时修 menu:members 事实错误，见问题 4）。
2. `toItems` 返回 `MenuItem[]` 类型（menuConfig 已有），删 any；icon 映射改为 DB 存 antd 组件名 + 白名单校验，非法名记 warning。
3. 回归测试：AdminLayout 渲染用例 ×3（动态成功/动态空/动态失败 × 权限缓存空），把三层组合钉死——当前该组件 0 测试。

### 9. 信封契约防不住失败：unwrap 无视 success/code，blob 下载会把错误 JSON 存成 .csv
**严重度：中**（潜伏性：现网后端碰巧全走非 2xx，一旦有 200+success=false 立即全前端静默 undefined）

**证据**：
- `shared/src/api/envelope.ts:16-17`：`unwrap = <T,>(envelope) => (envelope as ApiEnvelope<T>).data`——不检查 `success`/`code`；而后端 `err()`（backend/app/responses/api.py:36-38）与 tenant_context 中间件（middleware/tenant_context.py:59 `"success": False`）都具备产出 200+success=false 的能力；
- `services/spiders.ts:200-206` `exportResults`：`responseType:'blob'` + `res as unknown as Blob`——当导出失败（401/500），response.data 是含错误信封的 Blob，被原样当文件保存，用户得到一个名为 .csv 的 JSON 报错文件；且 blob 响应下 `apiErrorMessage` 读不到 message（data 是 Blob），报错回退到兜底文案；
- 全局 401 拦截器（client.ts:50-53）只认 HTTP 401：若后端某日以 200+code='UNAUTHORIZED' 表达过期，前端所有"已登录但数据全 undefined"的诡异态都会出现。

**为什么深层**：信封协议定义了 `success/code/message/data` 四个字段，前端消费了 1 个。协议里"业务失败可以是 200"这一可能性没有被前端立场否定或适配，属于契约两端的默会理解不一致——这类问题在后端重构异常处理器时（比如统一改成 200+code）会成批爆炸，且因"类型全对、运行时 undefined"而极难排查。

**解决方案**：
1. `unwrap` 收紧为两态：`unwrap`（success!==true 时 throw `ApiBusinessError(code,message)`，入全局 QueryCache.onError/message 统一提示）+ `unwrapRaw`（存量豁免清单）。TS 层返回 `T` 不变，调用点零改动。
2. exportResults 修复：`if (res.type.includes('application/json')) { const body = JSON.parse(await res.text()); throw new Error(body.message) }`；顺带给 blob 请求的 401/403 加显式判断。
3. 与后端确认一条写死的事实进 ADR："业务失败永远非 2xx"——若确认，把该约定写成 unwrap 的注释与后端 responses.py 的断言测试，双向钉死。

### 10. 官网健壮性短板：无 ErrorBoundary + lazy chunk 发版失效白屏 + 纯 CSR 无 SEO
**严重度：中**（admin 已修的三件事在对外门面上全裸奔）

**证据**：
- `official/src/App.tsx` 全文无 ErrorBoundary（对照 admin App.tsx:46-52 有双层），6 个 lazy 页任一渲染异常 → 整站白屏；
- lazy chunk 失效无恢复：发新版本后，用户停留的旧页面点击导航 → 旧 chunk 404 → `React.lazy` 抛错。admin 的 ErrorBoundary "重试"按钮只是 `setState({error:null})`（ErrorBoundary.tsx:40-42），chunk URL 已失效，重试必然再抛，唯一出路是用户自己想到刷新；admin/official 皆同病；
- official 面向公网获客却是纯 CSR：无预渲染/SSG，无 OG/Twitter meta（public/index.html 仅基本 description），搜索引擎与社交分享抓不到内容——营销站的立身之本。

**为什么深层**：三件事共享一个根因：**official 被当作"admin 的简化版"对待**，复用了基建却没继承 admin 踩坑后的修复（工单 69 的 lazy+Boundary 成果没有回灌官网）；而"官网需要被搜索引擎看见"这一产品级需求从未进入前端技术约束。这类问题不爆发时无人问，爆发即流量事故。

**解决方案**：
1. 官网套用 admin 同款 `<Page label>`（ErrorBoundary+Suspense），10 分钟工作量；chunk 失效恢复做成 shared 组件：ErrorBoundary 捕获时判断 `error.message` 含 `Loading chunk`/`dynamically imported` → `window.location.reload()`（sessionStorage 防循环）。
2. SEO 三选一按投入排：a) 零构建改动——`react-snap`/`prerender-spa-plugin` 构建后预渲染 6 个静态路由（官方站除技能广场外全静态，最划算）；b) `@prerenderer/rollup-plugin` 同理；c) 若要彻底，官方站迁 Next.js/Astro 是一年期议题，不建议现在做。同时 index.html 补 OG 标签与 canonical。
3. 把"admin 修复必须同步 official"写成 check-frontend.sh 的软规则：例如 F-9 检查 official/src/App.tsx 包含 `ErrorBoundary` 引用（grep 级，够用）。

---

## 附：验证记录

| 检查 | 结果 |
|---|---|
| `npm run build:shared/admin/official` | 全部 exit 0（admin main 240.6KB gzip；official main 147.7KB gzip） |
| admin jest | 5 suites / 13 tests 全过（~49s） |
| official jest | 2 suites / 3 tests 全过 |
| `scripts/check-frontend.sh` | 0 违规（F-2~F-7 启用） |
| tsc --noEmit（admin） | 0 错误（TS 4.9.5 + skipLibCheck:true） |

附注（未列入清单的低危观察）：TS 4.9.5（2022）搭配 React 19.2/antd 6.3/RR 7 的 2026 生态，靠 skipLibCheck 免疫类型冲突，`satisfies`/const 泛型等能力不可用，且 CRA（react-scripts 5.0.1）已停止维护——迁移 Vite 是半年内值得排期的独立事项；F-4 令牌门禁只黑名单 `#1890ff`，业务代码仍有 94 处硬编码色值（Dashboard 图表色 `#52c41a/#722ed1/#ff4d4f` 等未走 BRAND_TOKENS）；`SITE_NAME/SITE_SLOGAN` 在 Home.tsx 与 SiteLayout.tsx 重复定义（Home 的 SITE_SLOGAN 是未用变量，构建警告）；SpiderLogs.tsx:34 在 useEffect 里动态 import 同一模块的另一个函数（顶部已静态 import），属无意义写法；`STATUS_META` 在 components/spider/types.ts 与 pages/SpiderLogs.tsx 双份定义。
