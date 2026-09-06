# UI/UX 深层问题审查（design.md）

- 审查人视角：设计负责人，独立审查，仅依据仓库事实（frontend/ 源码 + backend 能力面）
- 审查范围：frontend/admin（管理后台 21 页/路由）、frontend/official（官网 6 页）、frontend/shared、backend/app/api/v1 能力面
- 方法：IA（menuConfig/App.tsx）→ 逐页抽查 14+ 页的状态实现（加载/空/错误/权限/边界/离线）→ 关键流程走查（注册-登录-首任务-结果）→ 组件与令牌横切面
- 日期：2026-09-06

## 总体判断

admin 的信息架构经过认真治理（菜单 5 组收进 Miller 7±2、能力资产单入口、路由级权限守卫、删除操作普遍有 Popconfirm + 后果说明、Dashboard 有零任务 onboarding 引导），AI 采集向导与 LLM 供应商向导的复杂表单也有预设回填/测试前置等超出平均水准的设计。官网首页静态数据有"示意"标注，技能详情有 XSS 安全渲染和键盘可达性。但把界面当唯一产品看，存在四类系统性缺陷：**（1）错误态在全局缺失**——全仓库没有一个 `Alert type="error"`、没有一个 Skeleton，所有请求失败要么一次性 toast 要么静默吞掉，用户看到的是"暂无数据/0 值"，错误与空态在 UI 上不可区分，这是数据诚实性的根子问题；**（2）跨端转化漏斗断裂**——注册成功页唯一主按钮是"再注册一家"，没有"去登录/进控制台"；**（3）admin 布局零响应式**且无租户/角色上下文展示；**（4）设计令牌有单源但被 60+ 处硬编码绕过**，与"禁硬编码色值"的自家注释直接矛盾。以下 10 条按严重度排序，每条给可执行方案。

---

## 深层次问题清单

### 1. 错误态系统性缺失：请求失败被呈现为"空态/0 值"，错误与无数据不可区分

- **严重度**：高
- **证据**（抽查 6 页全部命中同一模式）：
  - `frontend/admin/src/pages/Dashboard.tsx:64-74` 统计接口失败仅 `message.error` 一次性 toast；`146-196` Spin 结束后四张统计卡显示 `0`/'-'、图表显示 Empty——后端宕机与"业务为零"视觉完全相同。
  - `frontend/admin/src/pages/Usage.tsx:39-40` `if (!data) return <Alert type="warning" message="暂无用量数据" />`——接口报错后同样落入"暂无用量数据"。
  - `frontend/admin/src/pages/LlmProviders.tsx:54-63` `loadList` catch 注释写"列表加载失败由壳层兜底"，但壳层并无兜底；`252` 空表 emptyText 是"暂无 LLM 供应商，点击右上角「新建供应商」添加"——加载失败时引导用户去新建，制造重复数据风险。`78` 平台预设 `getPlatformPresets().catch(() => setPresets([]))` 同理，向导里"选择平台"下拉静默变空。
  - `frontend/admin/src/components/spider/LogDrawer.tsx:79-91` 日志接口失败 → `logData` 为空 → 显示"暂无日志输出（Worker 启动后开始记录）"。
  - `frontend/admin/src/pages/Spiders.tsx:79-93` 任务列表 react-query 只取 `isLoading`，无 `isError` 分支；失败即空表。
  - `frontend/official/src/pages/SkillsSquare.tsx:33-39`、`frontend/official/src/pages/Capabilities.tsx:20` catch → `setItems([])` → "暂无已发布技能"。
  - 横切证据：admin+official 全源码 `Skeleton` 0 处、`Alert type="error"` 0 处、react-query 页面 `isError` 0 处。
- **为什么深层**：这不是单页瑕疵而是状态设计矩阵缺了一整列（6 状态只实现 3 个）。用户会把"系统故障"读成"没有数据"，在管理台诱发错误决策（以为采集没结果、重复新建供应商），在官网直接损伤产品可信度（技能广场看起来是空的）。任何逐页修补都无法根治，必须建统一错误态机制。
- **解决方案**：
  1. shared 新增 `<QueryState>` 组件：error 分支渲染 `Alert type="error"` + `apiErrorMessage` 具体信息 + "重试"按钮；空态与错误态分离。
  2. 约定改写规则：react-query 页面用 `isError` 渲染错误态；手写 try/catch 页面增加 `loadError` state；Table 的 `emptyText` 仅在"请求成功且为空"时出现（LlmProviders/SkillsSquare/Capabilities/LogDrawer 优先改造）。
  3. 验证：`docker stop` 后端后逐页巡检（Dashboard/Usage/LlmProviders/SkillsSquare/LogDrawer），断言无任何页面把失败渲染为空态或 0；恢复后断言重试按钮可用。

### 2. 注册-登录转化断点：注册成功后没有"去登录"主 CTA，主按钮反而是"再注册一家"

- **严重度**：高
- **证据**：`frontend/official/src/pages/Register.tsx:48-57`——成功 Alert 内按钮为 primary「再注册一家」（`href="/register"`）+「返回官网」；顶部文案写"注册成功，即可登录开始第一次采集"，但整页无任何登录入口。管理后台与官网分应用部署（`SiteLayout.tsx:13` / `Home.tsx:25` 的 `REACT_APP_ADMIN_URL || http://localhost:9112`），新用户无从得知要去另一个域名登录。
- **为什么深层**：这是 SaaS 激活漏斗的第一块断板。注册完成 3 秒内用户目标只有一个——"开始用"，而界面给的 primary 动作是重复注册（对刚注册成功的用户是语义悖论）；漏斗在"注册成功→首次登录→首任务"的官方 onboarding（Dashboard 零任务引导做得很好）之前就流失了。
- **解决方案**：
  1. 成功态重排：primary 按钮 `href={ADMIN_URL + '/login'}` 文案"进入管理后台登录"；"返回官网"降为 link；"再注册一家"删除（多租户批量开通属运营台场景）。
  2. 成功文案补齐关键信息：管理员账号（已有）+ 提示"首次登录后请尽快修改密码"（衔接问题 8）。
  3. 验证：走查断言注册成功页首屏可见登录入口；点击后直达 admin 登录页且 `?username=` 预填用户名（可选）。

### 3. admin 布局零响应式：无断点、Sider 固定宽、统计卡不折叠——桌面之外基本不可用

- **严重度**：高
- **证据**：`frontend/admin/src/components/AdminLayout.tsx:57` `<Sider theme="dark">` 无 `breakpoint/collapsedWidth/collapsible`（默认固定 200px）；admin 全源码 `@media` / `useBreakpoint` / `breakpoint` 0 处（对比 official：`Home.css:412` 有 992px 断点、`SkillsSquare.tsx:92` Sider 有 `breakpoint="lg"`）；`Data.tsx:240-261` 统计卡 `Col span={6}` 无 xs（同页 Dashboard 用了 `xs={12} md={6}`，说明团队知道该写法但未成规范）；`TaskList.tsx:130` 操作列固定 width 380、`LlmProviders.tsx:251` 表格 `scroll={{x:1400}}` 在无折叠侧栏配合下半屏必然双向滚动。
- **为什么深层**：响应式缺失是布局系统层缺策略，不是某页样式问题。管理台用户普遍半屏分屏/平板巡检，现状是侧栏吃掉 1/3 宽 + 表格横向滚动叠加，操作列（每个页面都塞 140-380px 的多按钮）最先被截断——高频操作反而最不可达。
- **解决方案**：
  1. AdminLayout Sider 加 `breakpoint="lg" collapsedWidth={0}`（或 collapsible + Header 汉堡触发器），移动端自动收起。
  2. 建布局规约：统计卡一律 `xs={12} md={6}`；宽表一律 `scroll={{x}}` + 操作列用 Dropdown 收敛（超 3 个动作折叠为"更多"）。
  3. 验证：Playwright 375/768/1280 三档视口对 6 个高频页截图回归；断言 768px 下无横向页面级滚动条。

### 4. 权限兜底策略失真 + 身份上下文缺失：权限不可知时展示全量菜单，页头不显示租户/角色

- **严重度**：高
- **证据**：
  - `frontend/admin/src/hooks/usePermission.ts:76-81`：权限缓存为空（后端重启/接口失败）时 `filterMenu` 返回全量菜单，注释自述理由是"安全在 API 层"——但这把"系统异常"呈现为"你拥有全部功能"，viewer 点击 LLM 配置/平台运营台全部落到 /unauthorized。
  - `frontend/admin/src/components/AdminLayout.tsx:70-77`：页头仅渲染 `user?.username`；`services/auth.ts:19-20` 登录响应已含 `tenant_id/tenant_role` 但从不展示——多租户产品里用户无法确认"我在操作哪家公司、以什么身份"。
  - `frontend/admin/src/pages/LogCenter.tsx:91-93`：非管理员分支 `<Alert type="warning" showIcon title="审计日志仅管理员可查看" />` 用错 prop（antd Alert 应为 `message`），渲染出一个只有图标没有文字的空警告框——权限态自身就是个坏 UI。
- **为什么深层**：兜底方向反了：菜单可见性按"最乐观"处理，把不确定态当能力展示；再叠加身份上下文缺位，审计敏感的采集产品里用户可能带着错误角色认知执行操作。三个证据（全量菜单、无租户/角色、空 Alert）共同构成"权限态"这一整列的失真。
- **解决方案**：
  1. 缓存为空时菜单进入"受限兜底"：仅展示无需权限码的概览组，其余渲染为禁用+Tooltip"权限信息加载中"，而非全量；拉取失败给全局重试条。
  2. 页头加 `租户名 · 角色徽章`（数据现成在 user store）；平台超管显示"平台"标。
  3. 修复 LogCenter:92 `title=` → `message=`。
  4. 验证：mock `/auth/permissions` 返回 500，断言非 admin 不可见高危菜单；截图对比 LogCenter 权限提示渲染。

### 5. 两个完整功能页是"导航孤岛"：/enterprise 与 /rbac 有路由有实现、无菜单入口、页头标题错误

- **严重度**：中
- **证据**：`frontend/admin/src/App.tsx:80-95` 注册了 `/enterprise`（EnterpriseManagement，196 行）与 `/rbac`（RbacManagement，374 行）；`frontend/admin/src/config/menuConfig.tsx:32-83` 静态菜单 5 组中无这两项；`pageTitleFor`（同文件 89-96）对这两条路径回退"后台管理"；后端 menus 表无 seed（`backend/services/rbac_service.py` 仅提供 CRUD，全后端 grep 无企业管理/RBAC 菜单初始数据），动态菜单需人工插 DB 行，且 RbacManagement 本身就是插菜单行的工具——先有鸡还是先有蛋。
- **为什么深层**：功能可达性在 IA 层断裂：企业/部门组织树与 RBAC 管理是 SaaS 多租户叙事的关键能力，却只能手输 URL 发现；同时暴露菜单双真相源（静态 menuConfig vs DB menus 表）未对齐，一旦有人插了部分菜单行，两源继续分叉，IA 失控。
- **解决方案**：
  1. menuConfig「系统管理」组补 `{ key: '/enterprise', label: '企业管理' }` 与 `{ key: '/rbac', label: 'RBAC 管理' }`（均 admin 限定）；pageTitleFor 即自动修复。
  2. 明确单真相源策略并写进 menuConfig 头注释：静态配置为唯一来源、DB 菜单仅做权限过滤增量；或为 DB 提供 seed 脚本。二选一，禁止当前"两源并存无 seed"。
  3. 验证：单测遍历 App.tsx 全部受保护路由，断言 `pageTitleFor(path) !== '后台管理'` 且每个路由在 menuConfig 中存在或被显式标注"仅深链"。

### 6. 中文 UI 系统性泄漏英文枚举原值：角色/技能状态/同步状态/评测维度直接上界面

- **严重度**：中
- **证据**：`frontend/admin/src/pages/Members.tsx:128-139` 租户角色 Tag 与下拉直接显示 `owner/admin/operator/viewer`，`93` 成功提示 `${row.username} → ${role}`；`Skills.tsx:115-123` 状态 `experimental/testing/stable`、同步 `hash_changed/missing/parse_error` 裸显，`154` 筛选项同，`222-225` 评测维度 label 拼成"四维 · completeness（1-10）"。对比已有正确先例：`llmShared.PROTOCOL_NAMES`、`TaskList.TYPE_META`——映射能力存在但未成规约。
- **为什么深层**：术语一致性是设计系统基线。同一产品"操作员"与"operator"并存、"已上线"与"registered"混用，用户建立不起状态心智；付费决策场景里"半成品感"直接侵蚀信任。这是横切 10+ 页的文案体系问题，逐个改 label 无济于事。
- **解决方案**：
  1. shared 新增 `enumLabels` 词典（tenant_role、skill status/sync_state、tier、rubric dims、audit action 等），Tag/Select/message 统一经 `labelOf(enum)` 输出，原始码仅允许出现在 `<Text code>` 语境。
  2. 验证：grep UI 渲染点断言无裸枚举；对 Members/Skills 两页做文案快照测试。

### 7. 技能广场（对外门面）三处交互缺陷：60 条静默截断、分类 facet 基于已过滤结果、详情失败静默关窗

- **严重度**：中
- **证据**：`frontend/official/src/pages/SkillsSquare.tsx:18,33`（`PAGE_SIZE=60` 且 `page: 1` 写死、无分页 UI——第 61 条起对访客不存在）；`61-65` 侧栏分类计数由当前 `items` 统计——选中某分类后服务端已过滤返回，侧栏塌缩成单分类，facet 语义损坏；`67-76,142-149` `openDetail` 失败 `setDetail(null)` → Modal 自动关闭，用户点击卡片后弹窗闪现即消失、无任何反馈。
- **为什么深层**：这是官网获客核心页，资产数量是可信度信号，静默截断让平台"看起来只有 60 个技能"；facet 计数错误让筛选系统显得坏了；点击无响应式关闭是典型的转化杀手。三处同源：数据获取层没有区分"截断/过滤/失败"三种状态。
- **解决方案**：
  1. 列表接分页（Pagination 或"加载更多"，total 已在响应中）。
  2. 分类 facet 改为独立请求全量分类统计（或首次 unfiltered 请求时缓存计数），过滤不重算。
  3. openDetail 失败时 Modal 内渲染错误态 + 重试，而非关闭。
  4. 验证：seed 80 条技能断言第 61 条可达；断网点卡片断言出现错误提示。

### 8. 密码生命周期链路缺失：无忘记密码、无自助改密，且两处密码强度口径矛盾（8 位 vs 6 位）

- **严重度**：中
- **证据**：backend `app/api/v1/auth.py` 仅有登录/注册，无 change-password/forgot-password 端点（全 v1 grep 仅 `members.py:86` 管理员重置成员密码）；admin 全源码无"修改密码/个人中心"（grep 0 hit）；`Login.tsx` 无忘记密码入口；`official/Register.tsx:66` 要求 `min: 8`，而 `admin/Members.tsx:189,205` 创建成员/重置密码仅 `min: 6`——同一产品两种口径，官网承诺的强度被管理端打破；成员创建无"生成强密码/复制"affordance，初始密码靠管理员手发明文传递。
- **为什么深层**：账号体系是 SaaS 信任基座。强度口径自相矛盾属于安全叙事漏洞；没有找回路径意味着丢密码只能找平台方，这与"租户自助"的产品定位冲突，且随成员数增长线性放大管理成本。
- **解决方案**：
  1. 统一 min 8（两前端 rules + 后端 schema 同步校验）。
  2. Members 创建弹窗加"生成强密码 + 一键复制"，消除明文传递场景。
  3. 后端补 `PUT /auth/me/password`，AdminLayout 头像下拉加"修改密码"；忘记密码短期做"联系企业管理员重置"引导文案（成员重置入口已存在）。
  4. 验证：pytest 新端点（旧密码校验/强度拒绝）；两前端表单 rules 快照。

### 9. 能力资产导出绕过统一 client 硬编码 `/api/v1` 相对路径——跨域部署下必坏

- **严重度**：中
- **证据**：`frontend/admin/src/pages/Capabilities.tsx:174` `window.open('/api/v1/capabilities/teams/.../export', '_blank')`；而两应用真实基地址是 `REACT_APP_API_BASE_URL || http://localhost:9111/api/v1`（`admin/services/api.ts:12`），前端默认跑在 9112——localhost 同源代理下恰好能跑，生产分域/加前缀部署时该按钮 404。同页其他导出（ResultDrawer.onExport、Data.onExport）都走 axios client。
- **为什么深层**："配置即代码"红线在前端唯一的漏网点；它藏在深层 Tab（专家团 → 导出）里，测试环境验证不到，属于典型的环境相关隐性缺陷；且反映"所有下载类操作必须走 client"这条规约没有被机械检查兜住。
- **解决方案**：
  1. 改为 `api.get(url, { responseType: 'blob' })` 走 createApiClient（与 ResultDrawer 同模式），URL 拼接基于共享 baseURL。
  2. 加 lint 门禁：禁止源码出现 `window.open('/api` 模式（eslint no-restricted-syntax）。
  3. 验证：将 `REACT_APP_API_BASE_URL` 指向远程主机构建后，点击导出断言文件可下载。

### 10. 设计令牌有单源但被 60+ 处硬编码绕过：语义色写死、official 的 antd 不随令牌换肤

- **严重度**：低
- **证据**：`frontend/shared/src/theme/tokens.ts:6` 自述"禁止在业务代码硬编码色值"，但实测 admin 30+ 处 hex（`Dashboard.tsx` 图表色 '#3f8600'/'#cf1322'/'#722ed1'/'#52c41a' 均未用 BRAND_TOKENS.success/danger，`Login.tsx:46` 渐变 '#667eea/#764ba2' 与品牌色系完全无关、大量 '#999'/'#888' 灰阶）；official 68+ 处（`Pricing.tsx:52` 直接 `background: plan.color` 覆盖按钮主色）；official `App.tsx:23` ConfigProvider 只给了 locale 未给 theme token，`tokens.css` 改色时 antd 组件不跟随——"品牌换色只改 shared"的承诺只覆盖 admin 五个 token。
- **为什么深层**：令牌体系的价值在"改一处全局生效"，现状只做到"存在"未做到"消费"。语义色（成功/危险）绕过 token 意味着未来的暗色主题、SaaS 白标（多租户产品常见诉求）都要全库扫描替换；Login 页品牌色与 BRAND_TOKENS 脱节说明新页面开发不查令牌。
- **解决方案**：
  1. 扩展 BRAND_TOKENS：图表序列色板、灰阶文本层级、Login 渐变；Dashboard/Login/Pricing 替换为 token 引用。
  2. official `index.tsx` 加 ConfigProvider theme（colorPrimary 等与 tokens.css 同源）。
  3. 建门禁：CI grep 全部 hex 黑名单（白名单仅 shared/tokens 两处），新增硬编码即失败。
  4. 验证：改 `BRAND_TOKENS.primary` 一个值，双应用截图对比全量换肤生效。

---

## 覆盖度自检

- FR 覆盖：信息架构（问题 5）、关键流程完整性（问题 2/8）、状态覆盖（问题 1/4/7，抽查 Dashboard/Spiders/Usage/Data/LlmProviders/Settings/Members/Capabilities/EnterpriseManagement + official Register/Pricing/SkillsSquare/Capabilities 共 13 页）、可访问性与响应式（问题 3，aria 仅 official 5 处、admin 0 处，已并入 3/6 的修法中）、数据诚实性（问题 1/7/10）、复杂表单认知负荷（LLM 向导/任务弹窗实测有预设+测试前置，未列严重问题）、文案质量（问题 6）。
- 交接口：问题 1/4/6/10 需 shared 层改（QueryState 组件、enumLabels、令牌扩容），请 frontend 实现方优先落 shared 再回填页面；问题 5/8/9 涉及后端小改动（菜单 seed 决策、/auth/me/password、无）。
