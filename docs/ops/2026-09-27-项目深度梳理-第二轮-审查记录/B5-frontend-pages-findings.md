<!-- manager 落盘：2026-09-28，reviewer（G-fresh）最终交付原文逐字提取自其交付记录；packet 见 ../packets/ -->

# 审查报告：B5 前端页面 Bug 排查（第二轮，G-fresh）

## Snapshot
- 代码快照 HEAD `82259f301c060dbf411424ec8775f29944e313e1`。explore_roots 的 `git ls-files -s` sha256 为 `559834bdb67e490fc62a83e336d24af6997416930579d54369b80a7b0c651a1a`，由 manager 计算，这里原样照抄。
- 审查方式分三类，分开说明：
  - **静态检查**：packet 的全部必需 inputs；另读了 `Settings.tsx`、`Checkout.tsx`、`PlatformOps.tsx`(58-117)、`useAuthStore.ts`、`menuConfig.tsx`、admin `NotFound.tsx`、official `SiteLayout.tsx`、`beacon.ts`、`utils/track.ts`、official `public/index.html`；为核对注册链路，读了后端 `tenant_signup_service.py:60-149`、`billing_service.py:451-473`。其余用 Grep 定位。
  - **截图检查**：7 张截图全部打开看过。
  - **已记录执行**：`ui-runtime-summary.md`、`devdb-readonly.txt`。
- 我没有复现任何问题，也不能执行命令。需要复现的项放在文末。
- 覆盖面要说清楚：23 个 admin 页和 9 个官网页里，逐行读过的只有上面列出的页面。Spiders、SpiderLogs、Nodes、AiPlans、Enterprise、Rbac、Capabilities、MyInstalls、Members、Pricing、RelayGroups、OutboundKeys、LlmProviders、PaymentCredentials、LogCenter、NewApiOps、Dashboard，以及官网 Home、Capabilities、CapabilityDetail、Pricing、Legal，本轮没有逐行审。对这些页，只能依据运行期记录说：超管只读导航时 0 个 pageerror，除结账页外没有 ≥400 的响应。它们的交互（提交、分页、筛选）都**未验证**。
- 第一轮 R5 的 QA-1 到 QA-19 这里不重复报告，只在「对 R5 的更正与升级」一节补新证据。

**摘要**：新发现 12 条。major 4 条（B5-1、2、4、6），minor 8 条，没有 blocker。另外有两条 R5 条目拿到了运行期证据。

---

## FINDINGS

### B5-1 默认登录（不勾选「记住我」）时会话只存在内存里：刷新、新开标签页、点站内 `href` 按钮都会掉登录；如果当时在平台页，看到的是「页面不存在」
- Dimension: 8 边界（刷新后状态、深链接）/ 9 体验 | Severity: **major** | 工作量: S–M
- **现象**：manager 第一轮没勾选记住我，登录后用新页面导航，普通页一律跳回 `/login`；而 `/enterprise /rbac /payment-credentials /newapi /platform-ops /users /settings` 停在原地址，显示 404（`ui-runtime-summary.md:3,14-36`）。
- **触发条件**：登录时不勾选记住我（默认就是不勾：`Login.tsx:194` 的 `remember_me` 没有 initialValues），然后做下面任意一件事：按 F5、新开标签页、点页面里带 `href` 的按钮。
- **根因**：
  - `useAuthStore.ts:45-46`：`rememberMe=false` 时 `partialize` 返回 `{}`，token 一个字段都不落盘。
  - 以下按钮用 antd `Button href`，或直接给 `window.location.href` 赋值，都会整页刷新：
    - `Usage.tsx:136`「去提交采集」
    - `Usage.tsx:150`「去数据中心」
    - `QuotaBlockAlert.tsx:22`
    - `MyOrders.tsx:36` 去结账
    - `Checkout.tsx:184,206` 返回定价
    - `ErrorBoundary.tsx:43` 返回工作台
  - 平台页：`App.tsx:84-86` 对**未登录**用户也直接渲染 `NotFound`，`NotFound.tsx:15` 只给「返回工作台」，原目标地址就丢了。
- **后果**：
  - 默认用户在用量页点「去数据中心」会被踢回登录页。
  - 崩溃恢复按钮也会让用户掉登录。
  - 超管刷新 `/users` 看到「页面不存在或已被移除」，容易误以为功能被删。
  - 和 R5 QA-8 不是同一个问题：那条讲的是 7 天语义没实现、token 放在 localStorage；这条讲的是**默认路径下连一次刷新都撑不过**。
- **修复方案**：
  1. 不勾记住我时持久化到 `sessionStorage`（能撑过刷新，关浏览器失效）；勾选时才用 `localStorage`。做法是写自定义 `createJSONStorage`，按 `rememberMe` 决定存到哪里。
  2. 站内跳转一律改成 `navigate()` 或 `<Link>`；antd `Button href` 只允许用于外链。
  3. 未登录用户访问平台路由怎么处理，见 Q-1。
- **应补测试**：
  - e2e：不勾记住我登录，进 `/data`，`page.reload()`，断言仍在 `/data`；点 Usage 的 CTA 后断言 URL 变化且没有回到 `/login`。
  - 门禁：`grep -rnE 'href=\{?["'\''`]?/' frontend/admin/src --include=*.tsx`，只放行外链。
- **核验方式**：已记录执行（运行期摘要第 3 行）+ 静态检查。

### B5-2 系统设置页写着「修改后立即生效」、主标题会用于「官网首页主标题和管理后台 Logo」、简介会用于「官网 Hero 副标题 / SEO」，但这两个值没有任何消费方
- Dimension: 1 对外承诺 / 9 | Severity: **major** | 工作量: S（改文案）/ M（真正同步）
- **现象**：截图 `admin_settings-1440` 顶部写着「修改后立即生效」，按钮叫「保存并发布」。
- **根因**：
  - 文案在 `Settings.tsx:99`、`:111` tooltip、`:119` tooltip、`:131`。
  - 在 `frontend/` 里 Grep `site_title|site_description|/configs`，只命中 Settings 和它的 service 与测试。
  - 后台 Logo 写死：`AdminLayout.tsx:44` 的 `AutoAgents`。
  - 官网标题写死：`SiteLayout.tsx:18-19,35-43`。
  - 官网 meta description 是静态的：`official/public/index.html:8-11`。
  - 代码自己的注释也承认不同步：`Settings.tsx:78`「本波不做设置→官网真同步」（FR-90）。`Settings.test.tsx:93` 还断言了页面不发官网请求。
- **后果**：平台超管以为改名、改 SEO 已经发布，实际官网和后台都没变。本来只有 toast 那一句是「诚实句」，页面上的其他文案反过来推翻了它。
- **修复方案**：FR-90 已经决定本波不做同步，所以直接按运营性默认执行：
  - `:99` 改为「仅保存配置，暂未同步到官网与后台」；
  - 删掉两处 tooltip 里「官网 / Logo / SEO」的承诺；
  - 按钮改为「保存」。
  - 以后要真正同步，另立 FR：公开只读 `/public/site-config`，官网和后台启动时读取。
- **应补测试**：`Settings.test.tsx` 加一条断言：页面不出现「立即生效」「官网首页」「发布」字样（直到同步 FR 落地）。
- **核验方式**：截图 + 静态检查。

### B5-3 设置页加载失败时的问题：站点配置拉取失败后，表单显示硬编码默认值，此时点保存会覆盖真实配置；通知渠道或 Webhook 拉取失败则一直转圈；运行期的 `useForm not connected` 告警也是这里引起的
- Dimension: 8 错误态 / 6 | Severity: minor | 工作量: S
- **现象**：运行期记录到 `Instance created by useForm is not connected to any Form element`（`ui-runtime-summary.md:60`）。
- **触发条件**：
  - `GET /configs/` 失败，然后点「保存并发布」；
  - 或者 `GET /admin/notify-config`、`/admin/webhook-status` 失败。
- **根因**：
  - 告警：`Settings.tsx:36` 调 `notifyForm.setFieldsValue` 时，`<Form form={notifyForm}>` 只在 `notifyCfg!==null` 才渲染（`:149-150`），也就是还没挂载；`:43` 的 `form.setFieldsValue` 发生时，页面还在渲染 `:90-92` 的 Spin，站点表单同样没挂载。截图显示值最终合并进来了（Webhook 地址回填正常），所以这个告警本身影响不大。
  - 真正的缺陷有两个：
    - `:44-47` 失败只弹 toast，然后 `setFetching(false)`，表单露出 `:105` 的 `initialValues`（`AutoAgents` 和空简介）；再点保存，`:73-77` 会逐键 PUT，把真实值覆盖成默认值。
    - `:35,37` 失败时把状态设成 `null`，而 `:138,149` 把 `null` 当作「加载中」，结果永远转圈，没有重试。
  - 另外，`:73-77` 用 `Promise.all` 逐键写入，不是原子操作，部分失败时只提示「保存失败」。
- **后果**：一次网络抖动加一次误点，就会覆盖平台名；渠道配置加载失败时，用户分不清是在加载还是已经失败。
- **修复方案**：
  - 加载失败时渲染 `LoadFailure` 并禁用保存（这个组件在 `Checkout.tsx:11` 已经有了）；
  - 通知与 Webhook 状态改成三态 `loading | error | data`；
  - 改用 `useQuery`，拿到数据后通过 `initialValues` 加 `key` 重挂载表单，不再在挂载前调 `setFieldsValue`；
  - 后端提供批量 `PUT /configs`。
- **应补测试**：mock `fetchSiteConfigs` reject，断言保存按钮不可用、出现重试入口；mock `fetchNotifyConfig` reject，断言出现错误态而不是 Spin。
- **核验方式**：已记录执行（告警）+ 静态检查（覆盖路径未复现）。

### B5-4 平台运营台「禁用」租户是一键生效：没有二次确认，没有进行中锁，`platform` 和 `default` 租户上也能点
- Dimension: 8 权限与危险操作 / 4 | Severity: **major** | 工作量: S
- **现象**：截图 `admin_platform-ops-1440` 每一行，包括 `platform`，都有一个和「编辑」紧挨着的红色「禁用」按钮。
- **根因**：
  - `PlatformOps.tsx:99-102` 的 `onClick` 直接调用 `onToggleStatus`；
  - `:65-74` 直接 `patchTenant(... 'disabled')`，没有 Popconfirm，没有 loading 或 disabled 状态；
  - 页面提示（`:204`）自己也写着「到期租户会被登录拒绝」。
  - 对比之下，删除一条采集结果都要 Popconfirm（`Data.tsx:237-246`），停掉整个企业反而不用。
- **后果**：一次误点就会让整家企业的成员都登录不了。如果平台超管账号属于 `platform` 租户，而且登录会校验租户状态，就可能把自己锁在外面，从 UI 上无法恢复。这一点**未验证**。
- **修复方案**：
  - 加 Popconfirm，文案写明影响，例如「将阻止该企业 N 名成员登录」；
  - 请求进行中禁用按钮；
  - `platform` 和 `default` 两行隐藏或禁用这个按钮；
  - 后端 `PATCH /admin/tenants/{id}` 拒绝禁用平台租户。
- **应补测试**：点禁用后断言出现确认框、取消时不发请求；`platform` 行没有禁用按钮；后端测试：禁用平台租户返回 4xx。
- **核验方式**：截图 + 静态检查；自锁风险需要 manager 执行文末第 3 条。

### B5-5 运营台配额列把 `quota=null` 显示成「- / - / -」，和「免费档 = 默认配额」的语义不符；状态直接显示英文原值
- Dimension: 6 / 9 | Severity: minor | 工作量: S
- **现象**：截图里 `co-24634`、`co-25727` 两行配额是 `- / - / -`，状态显示 `active`。
- **根因**：
  - `PlatformOps.tsx:87` 对空值统一回落成 `'-'`；
  - 注册时写入的是 `quota=None`，注释说明「免费档=默认配额」（`tenant_signup_service.py:85`）；
  - `:81` 直接渲染 `status` 原值；
  - `:106-111` 编辑时回填 `undefined`，只填一项保存时后端是合并还是覆盖**未验证**。
- **后果**：超管判断不了这个租户到底是「默认免费档」还是「无限制」，续期或调档时容易误判。
- **修复方案**：后端列表返回 `effective_quota` 和 `quota_source`（plan/override/default），前端显示「默认·免费档 5 / 10000 / 200000」；状态映射为中文标签。
- **应补测试**：给 `quota=null` 的行渲染断言，要求出现「默认」字样。
- **核验方式**：截图 + 静态检查。

### B5-6 admin 在 375 宽度下不可用：侧栏固定 200px，内容区只剩约 95px，顶栏标题和用户名叠在一起；但官网注册是按手机设计的，注册成功后的主按钮正好直达后台
- Dimension: 9 旅程连贯 / 8 | Severity: **major**（取决于 Q-2） | 工作量: S（最小可用）/ M
- **现象**：截图 `admin_dashboard-375` 里，统计卡的文字一个字一个字竖排；顶栏「仪表盘」和「admin」叠成「表min」；「退出登录」被裁掉。
- **根因**：
  - `AdminLayout.tsx:42` 的 `<Sider theme="dark">` 没有 `breakpoint`、`collapsedWidth`、`collapsible`；
  - `:61-88` 顶栏没有省略号或换行策略；
  - `:92` 内容区两侧还有 16+24px 的边距。
  - 官网这边：`Register.tsx:25-28,173-181` 按 44px 触控目标设计；截图 `official_register-375` 显示注册页在手机上完整可用。
- **后果**：在手机上完成注册的企业负责人，点「登录管理后台」后进入的是一个用不了的后台，获客旅程在最后一步断掉。
- **修复方案**（最小可用）：
  - `<Sider breakpoint="lg" collapsedWidth={0}>`，窄屏下侧栏收成抽屉；
  - 顶栏标题 `ellipsis`，`md` 以下隐藏「欢迎回来」；
  - 窄屏把 Content 边距降到 8px。
  - 表格的移动端适配不在本条范围内。
- **应补测试**：Playwright 在 375 视口下访问 `/dashboard`、`/usage`、`/spiders/tasks`，断言 `document.documentElement.scrollWidth <= 375`，并保存截图基线。
- **核验方式**：截图 + 静态检查。

### B5-7 结账页（超管视角）：前端明知是超管还发请求，拿到 400 并在控制台报错；页面是死胡同；顶栏标题兜底成「后台管理」；订单列表失败没有处理
- Dimension: 6 / 9 | Severity: minor | 工作量: S
- **现象**：`400 GET /api/v1/billing/checkout?product=plan_pro` 加一条 console error（`ui-runtime-summary.md:49`）；截图里整页只有一句「超管不能代企业支付」，顶栏写「后台管理」。
- **根因**：
  - `Checkout.tsx:116-121` 没按 `user.is_platform_admin` 做前置判断；
  - 后端用 HTTP 400 表达「角色不允许」（`billing.py:44-55` 把 `is_platform_admin` 传给 service；错误码 `CHECKOUT_SUPERADMIN_FORBIDDEN`），语义上应该是 403；
  - `:210-214` 只显示一个 info，没有任何可做的动作；
  - `menuConfig.tsx:104-111` 找不到 `/billing/checkout`，于是回落成「后台管理」；
  - `:123-128,156-159`：`ordersQuery` 出错时 `openStatus=''`，页面仍按「待支付」显示一个状态为空的提示。显示成什么样**未验证**。
- **后果**：控制台噪声会掩盖真正的错误；超管进入后无路可走；页面标题不对。
- **修复方案**：
  - 超管在前端直接渲染说明，并给出「去平台运营台·待确认收款」链接，不发请求；
  - 后端改为返回 403 并带同样的 code；
  - `pageTitleFor` 支持不在菜单里的路由标题表（checkout、enterprise、rbac）；
  - `ordersQuery.isError` 时渲染 `LoadFailure`。
- **应补测试**：超管渲染断言 `previewCheckout` 没有被调用；`ordersQuery` reject 时出现重试入口。
- **核验方式**：已记录执行 + 截图 + 静态检查。

### B5-8 官网移动端：头部换行后没有行距；注册页嵌套了 `100vh`，首屏顶部空出一大块
- Dimension: 9 | Severity: minor | 工作量: S
- **现象**：截图 `official_register-375` 里，「管理后台」按钮折到第二行，贴着导航行；表单卡片上方空出约 170px。
- **根因**：
  - `SiteLayout.tsx:72` 设了 `flexWrap: 'wrap'`，但没有 `rowGap` 和上下内边距；
  - `Register.tsx:132-140` 的 `minHeight: '100vh'` 又套在 `main {flex:1}`（`SiteLayout.tsx:121`）里面，把卡片居中在一整屏高的盒子里。
- **修复方案**：
  - 头部加 `rowGap: 8`、`padding: '8px 16px'`，窄屏把「管理后台」收成图标按钮或放进导航；
  - 注册页去掉 `100vh`，改为 `padding: '48px 16px'`。
- **应补测试**：375 视口截图基线；断言表单卡片顶部 y 小于 140。
- **核验方式**：截图 + 静态检查。

### B5-9 官网 SEO 基础不足：详情页和 404 标题回落成 "AutoAgents"；description 和 OG 全站静态；404 返回 200（软 404）且没有 noindex；`/skills` 和 `/capabilities` 内容重复却没有 canonical
- Dimension: 9 增长基础 | Severity: minor | 工作量: S–M
- **现象**：截图 `official_no-such-page-1440` 的 404 页面本身做得不错，但运行期显示 `final=/no-such-page`，没有任何 404 信号（`ui-runtime-summary.md:12`）。
- **根因**：
  - `SiteLayout.tsx:35-43,56`：`TITLES` 只覆盖 7 个静态路径；`/capabilities/:type/:slug` 和 404 都回落到 `SITE_NAME`；
  - `index.html:8-11,27-30`：description、og:title、og:description 只有一份静态值，没有 `og:url`、`og:image`；
  - `App.tsx:36-38`：两个路径渲染同一个组件；
  - `App.tsx:43` 加 `NotFound`：没有 `robots noindex`；
  - 另外 `official.yml:15` 的 `SITEMAP_ENABLED: false`，页面是纯 CSR。
- **后果**：能力详情页是长尾流量的主要入口，但每个详情页标题都一样；软 404 会被收录；重复内容会分散权重。
- **修复方案**：
  - 做一个 `usePageMeta({title, description, canonical, noindex})` hook（或 react-helmet-async）；
  - 详情页用能力名和简介填充；
  - NotFound 设置 `noindex`；
  - `/skills` 指向 `/capabilities` 的 canonical，或者直接 301；
  - 生产环境 nginx 对未知路径返回 404 状态码（需要和 deploy 协同）。
- **应补测试**：jest 渲染详情页后断言 `document.title` 含能力名；NotFound 渲染后 head 里有 `meta[name=robots][content*=noindex]`。
- **核验方式**：静态检查 + 已记录执行。

### B5-10 官网埋点：两套机制并存，其中一套是死代码；page_viewed 覆盖不全；注册提交和失败没有事件；dev 库里没有任何注册成功事件
- Dimension: 3 / 9（埋点触发时机） | Severity: minor | 工作量: S
- **根因**：
  - `utils/track.ts:1-15` 注释自称「官网北极星最小埋点」，实际只写进 sessionStorage 的 `aa_track`，「不外呼」。Grep `aa_track` 只命中它自己，也就是没有消费方；它唯一的调用处是 `SiteLayout.tsx:57`。
  - `SiteLayout.tsx:45-51,58-59` 的 `PAGE_BY_PATH` 只有 5 个路径，详情、条款、隐私、404 都不上报 `official_page_viewed`。
  - `Register.tsx:86-126` 在提交、校验失败、服务端失败时都不打点，只有服务端的 `tenant_signup_succeeded`（`tenant_signup_service.py:123,126-137`）。
  - `devdb-readonly.txt:36-50`：事件表里有 `official_page_viewed` 79 条、`official_cta_clicked` 22 条，但**没有一条** `tenant_signup_succeeded`，而租户表里有 5 个租户（`:52-53`），其中 `co-24634`、`co-25727` 的 slug 形态像是注册产生的。
- **后果**：「访问 → 点注册 → 提交 → 成功」这个漏斗算不出来，表单流失没法定位。如果那些租户是在埋点上线（最早事件是 2026-09-14）之后注册的，说明成功事件在丢，这一点**未验证**。
- **修复方案**：
  - 删掉 `utils/track.ts` 及其调用；
  - `PAGE_BY_PATH` 补上 detail、legal、not_found（可以带 `props.slug`）；
  - `onFinish` 入口打 `official_signup_submitted`，失败时打 `official_signup_failed{reason_code}`，不带任何表单值；
  - 服务端白名单同步：`platform_core/schemas/product_event.py:23` 附近。
- **应补测试**：`Register.beacon.test.tsx` 断言提交和失败各触发一次，并且 props 里没有 email 或 password。
- **核验方式**：静态检查 + 已记录执行；是否丢事件见文末第 4 条。

### B5-11 注册表单与后端契约的细节没对齐：企业名长度计入首尾空格；密码和邮箱前端没有上限；请求超时被说成「网络不可用」
- Dimension: 6 / 8 | Severity: minor | 工作量: S
- **根因**：
  - 企业名：前端 `min: 2` 计入空格（`Register.tsx:212-215`），后端先 `strip()` 再校验（`tenant_signup_service.py:62,66-67`），所以「 a」前端能过、后端拒绝。
  - 密码：前端只有 `min: 8`（`Register.tsx:229-232`），后端 `max_length=128`（`tenant_signup.py:32`）。
  - 邮箱：前端没有 `maxLength`（`Register.tsx:224`），后端 `max_length=100`（`tenant_signup.py:31`）。
  - 超时：`isNetworkError`（`Register.tsx:53-57`）把 axios 超时（10s，没有 response）也归为「网络不可用」。
- **后果**：边界输入会拿到 422 或服务端文案，和前端的就地校验不一致；后端慢的时候，用户被误导去检查网络。
- **修复方案**：
  - 企业名规则加 `whitespace: true` 并在提交前 trim；
  - 密码 `max: 128`，邮箱 `maxLength={100}`；
  - 超时单独给一条文案：`code==='ECONNABORTED'` 时显示「服务响应超时，请稍后重试」。
- **应补测试**：`Register.test.tsx` 覆盖「 a」、129 位密码、超时三个用例。
- **核验方式**：静态检查。

### B5-12（跨 lane，owner 是 backend）注册服务里 `attach_free_plan` 被调用了两次，第二次没有异常保护，和「不阻断注册」的注释矛盾
- Dimension: 6 / 8 | Severity: minor | 工作量: S
- **根因**：`tenant_signup_service.py:98-103` 在 try/except 里调一次（注释「价目未种子时不阻断注册」），`:109-111` 又裸调一次。`billing_service.py:451-465` 每次调用都会再走一遍 `_apply_plan` 和 LiteLLM 的 `ensure_tenant_key`。
- **后果**：如果第一次因为数据库或配额错误抛异常被吞掉，第二次会原样抛出，导致注册失败，官网显示「注册未完成」；即使一切正常，也会重复申请虚拟键。`ensure_tenant_key` 是否幂等**未验证**。
- **修复方案**：删掉 `:109-111`；在单测里断言 `attach_free_plan` 只调用一次。
- **核验方式**：静态检查。

---

## 对 R5 的更正与升级（不算新条目）
- **R5 QA-2（登录时先拉权限再写 token）**：从「未验证」改为**已由记录的执行确认**。两次登录都出现 `401 GET /api/v1/auth/permissions`（`ui-runtime-summary.md:13,37`）。补充一个脆弱点：这次 401 会走 `api.ts:14-17` 的 `logout()`，登录过程中间先被登出一次，之所以没出事，只是因为靠 `pathname==='/login'` 提前 return，以及随后 `set()` 覆盖回来（`useAuthStore.ts:29-34`）。严重度维持 minor，修复方案不变。
- **R5 QA-10（antd 弃用 API 与上下文）**：补运行期逐页证据：
  - Statistic `valueStyle`：dashboard、data，以及登录后的 dashboard；
  - Drawer `width`：spiders/tasks、ai、llm、data；
  - Alert `message`：platform-ops（`PlatformOps.tsx:204`）；
  - Spin `tip`：settings（`Settings.tsx:91`）；
  - 静态 `message`：登录（`ui-runtime-summary.md:13,38-60`）。
  
  `Register.tsx:166,204` 和 `Checkout.tsx` 已经改用 Alert `title`，说明迁移只做了一半。可以用 `grep -rn "valueStyle=\|<Alert[^>]*message=\|<Spin[^>]*tip=\|<Drawer[^>]*width=" frontend/admin/src` 生成清单，一次性清掉。

## Dimensions checked
1. 标准符合 ⚠️：没有 spec 或产品层，按代码注释里的 FR/GWT 判断。B5-2（设置页承诺了不存在的同步）；B5-7（结账页超管路径没有出口）。
2. 标准质量 ➖/⚠️：输入里没有 GWT。已有测试只覆盖正向路径，没有覆盖「加载失败后保存」「刷新保留登录」「375 视口」（B5-1、3、6）。
3. 证据有效性 ⚠️：运行期记录可靠，但只做了超管只读导航，没有租户负责人视角、没有提交类操作。B5-10 的埋点里有死代码。本报告没有复现任何问题。
4. 安全 ⚠️：B5-4（一键禁用整家企业、可能自锁）。平台路由对未登录者返回 404 的保密价值很低：`PLATFORM_WRITE_KEYS` 本来就在公开 bundle 里（`menuConfig.tsx:31-33`），见 Q-1。另外注册错误不回显邮箱是否被占用（`tenant_signup_service.py:80-82`），这一点做得好。
5. 性能 ➖/✅：本切片没看到无界请求；数据中心导出单次上限 100 条，有文案说明（截图 `admin_data-1440`）。包体积已在 R5 QA-14 报过。
6. 契约一致性 ⚠️：B5-5、7、11、12。
7. 宪法合规 ✅/⚠️：前端不在 R1–R13 的机械检查范围内。「配置即代码」的精神问题（`SiteLayout.tsx:16`、`Register.tsx:15` 的 localhost 回落）R5 QA-15 已经报过，不重复。没看到违反依赖方向的地方。
8. 边界 ⚠️：刷新和深链接（B5-1）、错误态（B5-3、7）、危险操作（B5-4）、超长输入（B5-11）、窄屏（B5-6、8）。
9. 产品价值与体验 ⚠️：结合截图判断。官网注册页在移动端完整可用，但成功后进入的后台在 375 宽度下用不了（B5-6）；设置页的承诺与现实不符（B5-2）；超管进入结账页是死胡同（B5-7）；SEO 和埋点基础不足以支撑增长（B5-9、10）。缺少租户负责人视角的截图，所以租户主旅程（用量 → 结账、成员、采集）的界面**未验证**。

## Strengths（改进时应保留）
1. **路由级隔离稳**：每页都套了 `ErrorBoundary + Suspense`（`App.tsx:63-70`），页面全部懒加载。运行期 8 个官网路由和 24 个 admin 路由都没有 pageerror（`ui-runtime-summary.md:5-60`）。
2. **结账页状态闭集做得好**：角色不允许、未知产品、超管、离线、通用失败各有独立呈现（`Checkout.tsx:193-225`）；提交进行中禁用按钮（`:283-290`）；在线支付失败会退回人工确认，不会误报错误（`:78-80`）。
3. **注册页可访问性与防重做得认真**：离线预检（`Register.tsx:87-90`）；成功后焦点移到主按钮（`:76-78`）；`aria-live`、`role="alert"`（`:161,206`）；44px 触控目标；校验失败滚动定位（`:195-198`）；提交中 `disabled`，同时阻止回车重复提交（`:246-247`）。服务端不回显邮箱是否被占用。
4. **平台写面多层防护**：`MainLayout` 守卫（`App.tsx:84-86`）、`ProtectedRoute requireAdmin`（`:135`）、页面内再判断（`Settings.tsx:88`），后端 `require_platform_admin_or_404` 四层一致。
5. **数据中心的破坏性操作与限额文案清楚**：单条删除有 Popconfirm（`Data.tsx:237-246`）；截图可见「单次最多 100 条」「详情打开所属任务的完整结果」等说明，空态和分页正常。

## Improvement themes
1. **会话与导航一致**（B5-1、R5 QA-2/8/9）。目标：默认登录能撑过刷新；站内导航全部走 router；登录、权限、查询缓存在同一会话对象里建立和清除。落地顺序：sessionStorage 持久化（S）→ 替换站内 `href` 并加门禁（S）→ 按 Q-1 决定未登录访问平台路由的去向（S）→ 与 R5 主题 2 合并推进。
2. **页面只承诺已实现的能力**（B5-2、7、5）。目标：文案、按钮名、tooltip 与实际行为一一对应；不在菜单里的页也有正确标题和出口。顺序：设置页改文案（S）→ 结账页超管出口和标题表（S）→ 运营台显示有效配额（S，需要后端配合）。
3. **危险操作与失败态统一范式**（B5-3、4）。目标：影响整个租户的操作一律二次确认、有进行中锁、后端也有守卫；所有加载失败都用 `LoadFailure` 且禁止写入。顺序：运营台禁用确认加平台租户保护（S）→ 设置页三态（S）→ 抽 `useDangerAction` / `LoadState` 的使用约定进 code review 清单（S）。
4. **响应式基线**（B5-6、8）。目标：两个应用在 375 宽度下没有横向溢出，关键旅程可以走完。顺序：Sider 断点和顶栏收敛（S）→ 官网头部与注册页布局（S）→ Playwright 375 截图基线接入 CI（M）。
5. **官网增长基础**（B5-9、10、11）。目标：每个路由有独立的 title、description、canonical；404 有 noindex；漏斗事件从页面浏览一路到注册成功都完整且不含 PII；删掉死埋点。顺序：删 `track.ts`、补 `PAGE_BY_PATH` 和注册事件（S）→ `usePageMeta` 加详情页（S）→ nginx 真 404 与 sitemap（M，协同 deploy）。

## 需 manager 执行的验证（未验证项）
1. **B5-1**：用 Playwright，不勾记住我登录 → `goto /usage`（需要租户负责人账号）→ 点「去数据中心」→ 预期 URL 变成 `/login`（缺陷成立）。超管可以换成 `goto /users` 后 `reload()`，预期出现 404 文案。
2. **B5-3**：Playwright 里 `page.route('**/api/v1/configs/', r => r.abort())` → 打开 `/settings` → 点「保存并发布」→ 抓到 `PUT /api/v1/configs/site_title` 且请求体为 `{"value":"AutoAgents"}`，即缺陷成立。**注意这是写操作，只能在隔离库上执行。**
3. **B5-4 自锁风险**：`grep -n "status\|disabled\|expires" backend/services/auth_service.py | head -40`；`SELECT u.id,u.username,u.tenant_id,t.slug FROM users u LEFT JOIN tenants t ON t.id=u.tenant_id WHERE u.is_platform_admin=1;`
4. **B5-10**：`SELECT slug, created_at FROM tenants ORDER BY created_at;` 与 `SELECT COUNT(*) FROM product_events WHERE event_name='tenant_signup_succeeded';` 对比。如果有租户创建于 2026-09-14 之后而计数为 0，说明成功事件在丢，应升为 major。
5. **B5-6**：Playwright 视口 375×812，访问 `/dashboard`，执行 `page.evaluate(() => document.documentElement.scrollWidth)`，预期大于 375。
6. **B5-7**：`curl -s -H "Authorization: Bearer $SUPER" "http://127.0.0.1:9111/api/v1/billing/checkout?product=plan_pro" -w "\n%{http_code}\n"`，确认返回 `400` 且 code 为 `CHECKOUT_SUPERADMIN_FORBIDDEN`。
7. **B5-9**：`curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9113/no-such-page`（开发服务器预期是 200）；生产 nginx 的配置另查 `deploy/`。
8. **B5-12**：`grep -n "async def ensure_tenant_key" -A25 backend/services/litellm/admin_service.py`，确认是否幂等。

## 返回项
- **Output path**：本报告由 manager 保存到 `/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/B5-frontend-pages/05-review/findings.md`。
- **Summary**：新发现 12 条，其中 major 4 条（B5-1 默认会话撑不过刷新和站内跳转、B5-2 设置页虚假承诺、B5-4 一键禁用租户、B5-6 admin 移动端不可用），minor 8 条；R5 QA-2 已由运行期确认，R5 QA-10 补了逐页证据。
- **Decisions**：无，本轮只出报告。已按运营性默认处理一项：B5-2 按 FR-90 既定的「本波不同步」只改文案。
- **Open questions**：
  - **Q-1（战略，待确认）未登录访问平台路由返回什么？**
    - 选项 A：保持 404 同形（ADR-0021/0022、GWT-96.4）；
    - 选项 B：跳转登录页并带上 from；
    - 选项 C：仍显示 404，但对未登录者额外给一个「登录后继续」按钮（带 from）。
    - **推荐 C**：路由表已经在公开 bundle 里，A 实际不提供保密性，还会让超管的深链接失效；C 不改变对租户的 404 语义，改动最小。
  - **Q-2（战略，待确认）admin 是否把移动端（≤768px）列为支持范围？**
    - 选项 A：只保证最小可用（侧栏抽屉化、顶栏收敛）；
    - 选项 B：主旅程页（用量、结账、成员）完整适配；
    - 选项 C：明确声明只支持桌面，并把官网注册成功后的主按钮改成「在电脑上登录」加邮件提醒。
    - **推荐 A**：成本 S，能先把官网注册到后台这条旅程接上。
- **Product-delta**：无（`docs/product` 不存在）。
- **Lessons（已核实的坑）**：
  1. zustand `persist` 的 `partialize` 在 `rememberMe=false` 时返回 `{}`，token 只在内存里。任何整页跳转（包括 antd `Button href="/x"`、`window.location.href`）都等于登出。已由运行期记录第 3 行和代码核实。
  2. antd 表单被 Spin 或条件渲染挡住、还没挂载时就调 `form.setFieldsValue`，会出现 `useForm not connected` 告警。更要紧的是，同一处「先加载后挂载」的写法通常把「加载失败」和「加载中」混成一个状态，失败后还可能露出默认值被保存。已由运行期告警和 `Settings.tsx` 核实。
