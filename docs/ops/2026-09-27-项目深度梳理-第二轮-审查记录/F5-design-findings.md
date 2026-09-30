<!-- manager 落盘：2026-09-28，reviewer（G-fresh）最终交付原文逐字提取自其交付记录；packet 见 ../packets/ -->

# F5 设计审查（第二轮，G-fresh）：共 17 条 finding，其中 major 5 条、minor 12 条，未确认 blocker

## Snapshot
- HEAD 82259f301c060dbf411424ec8775f29944e313e1（工作区仅新增 docs/ops/）；explore_roots `git ls-files -s` sha256 559834bdb67e490fc62a83e336d24af6997416930579d54369b80a7b0c651a1a（manager 计算，此处原样转述）
- reviewer：sdlc-workflow:reviewer，只读。评判标准加载了 sdlc-workflow:findings 与 design-contract（设计 QA 的优秀标准）。
- 我实际做了什么：
  - 逐张看了 packet 列出的 42 张截图中的 40 张（admin 25 张，其中 1440 宽 22 张、375 宽 3 张；official 15 张），未看 official_privacy-375 和 official_skills-375；读了 ui-runtime-summary 与 R5 第一轮报告。
  - 在截图暴露问题的地方用 Grep/Read 追到了代码行，也读了少量后端代码来确认统计口径。
  - **没有复现任何东西**。凡标「截图」的，是看 manager 已录制的截图得出的；凡标「静态」的，是读代码得出的。
- 没有看的：devdb-readonly.txt、module-inventory.md（本维度用不到）；租户负责人视角的截图（输入里没有）；admin 除登录、仪表盘、采集任务、用量四页以外的 375 截图（输入里没有）。

**摘要**：共 17 条。major 5 条（QA-1、2、4、5、6），minor 12 条。与第一轮 R5 的 QA-1~19 没有重复；对 R5 的补充证据单独放在文末。

---

## FINDINGS

### QA-1 后台在 375 宽下完全不可用：侧栏固定 200px 常驻，内容区只剩约 160px
- Dimension：9 体验 / 8 边界 | Severity：**major** | 工作量：M | 核验：截图 + 静态
- **现象**：
  - admin_dashboard-375：统计卡里的文字一字一行竖排（「任/务/总/数」「运/行/中/0」），顶栏页名「仪表盘」和「admin」叠在一起，「退出登录」被截断，「平台超管」标签压到内容上。
  - admin_spiders_tasks-375：「example」被拆成「e/x/a/m/pl/e」逐字换行，顶栏页名和页级 tab 互相重叠。
  - admin_usage-375：三张用量卡竖排成窄条。
  - 只有登录页（admin_login-375）是正常的。
- **触发**：任意后台页，视口宽 ≤ 约 900px。
- **根因**：
  - `frontend/admin/src/components/AdminLayout.tsx:42` 写的是 `<Sider theme="dark">`，没有 `breakpoint`、`collapsible`、`collapsedWidth`；admin 源码中 Grep `breakpoint|useBreakpoint` 为 0 条。
  - 顶栏 `:61-88` 是单行 flex，没有省略号，也不会换行。
  - `frontend/admin/public/index.html:6` 却声明了 `width=device-width`，浏览器会按设备宽度渲染，但没有任何适配。
- **后果**：值班或运营人员在手机上看任务状态、告警时无法使用；产品也没有写明「仅支持桌面」。
- **修复**：先等 Q-1 决策。
  - 最低做法：给 Sider 加 `breakpoint="lg" collapsedWidth={0}`，小屏改成 Drawer 菜单；顶栏欢迎语在 <md 时隐藏；表格统一 `scroll={{ x: 'max-content' }}`。
  - 如果决定只支持桌面：给 Layout 设 `min-width: 1280px`，在 <1024 时显示「请在桌面端使用」提示。
- **应补验收**：Playwright 在 375 和 768 宽下截全部后台路由，断言 `document.documentElement.scrollWidth <= innerWidth`，并确认顶栏元素之间的包围盒不相交。

### QA-2 能力市场未开放时，官网形成死循环；关闭态只有无样式的一句话
- Dimension：9 / 6 | Severity：**major** | 工作量：S | 核验：截图 + 静态
- **现象**：
  - 顶部导航第一项就是「能力市场」。
  - 首页底部显示「还没有上架的能力。开通后可在能力市场浏览。」并带「去能力市场」链接（official_-1440）。
  - 点进去是「能力市场未开放」+ 浏览器默认蓝色下划线的「返回首页」，形成「首页 → 市场 → 首页」的闭环。
  - 搜索框、「宿主」「分类」筛选在关闭态下仍然显示，而且可以操作（official_capabilities-1440/375、official_skills-1440）。
  - 同一件事有两种说法：「开通后」和「未开放」。
- **根因**：
  - `frontend/official/src/pages/Capabilities.tsx:70-76` 关闭分支只渲染 `<p>{MARKET_CLOSED}</p><Link to="/">返回首页</Link>`。
  - 已定义的 `MARKET_CLOSED_HINT`（`capabilityMarket.ts:31`「开放后，已上架的能力会出现在这里。」）没有被这个页面使用（`Capabilities.tsx:13-24` 的 import 列表里没有它）。
  - 筛选栏在关闭分支之外渲染。
  - 首页 `components/home/SkillsSection.tsx:83-85` 在关闭时仍渲染区块和链接。
  - 404 页用了 Result 插图 + 主按钮（official_no-such-page-1440），关闭态却是裸 `<p>`，同一站点两套状态样式。
- **后果**：营销站的首要导航把访客引进空房间，回头只能「返回首页」，没有注册或定价等转化出口；页面显得半成品。
- **修复**：
  - 关闭态改用与 404 同款的 Result：标题 MARKET_CLOSED，副文 MARKET_CLOSED_HINT，主按钮「免费注册」，次按钮「查看定价」。
  - 关闭时隐藏筛选栏。
  - 首页 SkillsSection 在 `market_closed` 时整段不渲染。
  - 导航项是否隐藏等 Q-2 决策。
- **应补测试**：Capabilities.test 断言关闭态下没有 `role=searchbox`、有注册 CTA；SkillsSection.test 断言关闭态不渲染。

### QA-3 官网首页首屏以下内容默认透明，全页截图约 2,700px 空白，本轮无法审查首页主体
- Dimension：3 证据 / 9 | Severity：minor（对真实滚动用户多半不可见；**首页主体设计仍未审查**） | 工作量：S | 核验：截图 + 静态
- **现象**：official_-1440 全页截图中：
  - 「CORE FEATURES」眉标以下的核心功能、AI 流程、架构、CTA 带都是空白；
  - 灰色区块只剩三处「- -」小标记，无法判断是什么；
  - 深色 CTA 带没有文字。
- **根因**：
  - `frontend/official/src/components/home/common.tsx:34-38` 的 FadeIn 是 `initial={{opacity:0}}` + `whileInView`（`amount:0.18, once`），不进入视口就一直透明。
  - reduced-motion 分支 `:30-32` 做得对（见 Strengths）。
- **后果**：
  - 不滚动的全页截图（社交分享卡、Lighthouse 全页截图、本次设计 QA 取证）、打印、IntersectionObserver 不触发的环境都会看到空白。
  - 本轮无法评判首页主体的层级、文案和招牌时刻。
- **修复**：
  - 入场动效只做位移，不从 0 透明度开始（例如 `initial={{ opacity: 0.001? }}` 改为 `initial={{ y }}`、opacity 恒为 1）；
  - 或在 `@media print` 与无 IO 环境强制可见。
- **需 manager 复拍**：`page.emulateMedia({ reducedMotion: 'reduce' })` 后对 `http://127.0.0.1:9113/` 截 1440/375 全页（FadeIn 会直接显示终态），再请求 F5 复审首页主体。

### QA-4 「AI 采集规划」同时显示两套步骤条，步骤名与试采所在步骤互相矛盾
- Dimension：6 / 9 | Severity：**major**（这是首页承诺「粘贴链接即可出数」的核心路径） | 工作量：S | 核验：截图 + 静态
- **现象**（admin_ai-1440）：
  - 上面一条小号步骤条：1 输入目标 / 2 方案与试采 / 3 上线；
  - 下面一条大号步骤条：1 创建计划 / 2 方案预览与调整 / 3 试采与上线。
  - 「试采」一个在第 2 步，一个在第 3 步。
- **根因**：`frontend/admin/src/pages/AiPlans.tsx:88-97`（工单 89 新加的阶段指示）和 `frontend/admin/src/components/ai/PlanDetail.tsx:363`（原有 Steps）同时渲染。
- **后果**：用户无法判断当前处于哪一步、什么时候会真正试采；AI 流程这个核心体验显得拼凑。
- **修复**：只保留一条；步骤名收敛到一个常量，例如 `AI_FLOW_STEPS`，由 PlanDetail 独占渲染，并删除 AiPlans 那一条。
- **应补测试**：AiPlans.test 断言 `container.querySelectorAll('.ant-steps').length === 1`，且步骤名等于常量。

### QA-5 仪表盘同一排指标混用「累计」和「近 7 日」却不标注，出现「成功率 – / 失败 0」这种自相矛盾
- Dimension：6 / 9 | Severity：**major**（这是登录后的首页） | 工作量：S | 核验：截图 + 静态（含后端口径）
- **现象**（admin_dashboard-1440）：
  - 任务总数 1，成功率「-」且旁边写「失败 0」，平均运行时长 4.0s，近 7 日采集结果 0。
  - 但采集任务页显示任务 #3「已完成」、采集结果 1，数据中心也有 1 条结果。
  - 「采集结果 Top5」「质量分布」只有坐标轴、没有柱子，而质量卡明明写着「75/100，基于 #3（1 条数据）」。
- **根因**：
  - 口径：`backend/services/spider_query_service.py:380-402`：
    - `total_tasks`、`failed`、`avg_duration` 按全量统计；
    - `success_rate` 只算窗口内（:385，窗口内没有已结束任务时为 None）；
    - `total_results` 是近 7 日之和（:402）；
    - Top5 是全量 `sum(result_count)`（`spider_task_repository.py:171-180`）。
  - 前端 `frontend/admin/src/pages/Dashboard.tsx:101,164-209` 只有第四张卡写了「近 7 日」，`:187` 用全量的 `failed` 去配窗口成功率。
  - Top5 只判断 `.length`（`:236`），不判断是否全为 0，所以全 0 时会画空坐标轴。
- **柱子缺失（未验证）**：按数据应当有 1 根柱，很可能是截图时 recharts 入场动画还没画完。需要 manager 在 networkidle 后再等 2s 复拍 `/dashboard`。
- **后果**：运营看到「成功率 –、失败 0」会误以为统计坏了；累计和窗口混在一起，得出错误结论。
- **修复**：
  - 每张卡明确窗口：「累计任务」「近 7 日成功率」「近 7 日失败」「近 7 日采集结果」；
  - 成功率为 null 时写「近 7 日没有已结束的任务」，不要显示「-」；
  - Top5 改名为「累计采集结果 Top5」，或者后端改成按窗口统计；
  - 全 0 时显示 Empty。
- **应补测试**：Dashboard.test 覆盖「success_rate=null 但 total_tasks>0」「top_spiders 全 0」两种情况下的文案。

### QA-6 租户管理分散在两个页面：术语、状态显示和保护规则都不一致，平台运营台「禁用」一键生效、没有确认
- Dimension：8 权限/边界 / 6 | Severity：**major** | 工作量：S–M | 核验：截图 + 静态
- **两个页面的对比**：

| 方面 | /enterprise（admin_enterprise-1440） | /platform-ops 租户管理（admin_platform-ops-1440） |
|---|---|---|
| 列名 | 公司名 / 标识 | 企业名称 / Slug |
| 状态显示 | 「启用」 | 原始值 `active` |
| 停用动作 | 「停用」，带后果确认 | 「禁 用」，无确认 |
| 平台租户行 | 动作置灰，并写明「平台租户不可停用」 | 「禁用」按钮可点 |

- **根因**：
  - `frontend/admin/src/pages/PlatformOps.tsx:65-74`（`onToggleStatus` 直接 PATCH，没有 Modal.confirm）、`:81`（`<Tag>{v}</Tag>` 显示原始值）、`:99-101`（没有平台租户判断）。
  - 对比 `EnterpriseManagement.tsx:222`（停用带确认）、`:259-270`（平台租户守卫）。
  - 两页调用同一个接口 `PATCH /admin/tenants/{id}`（`services/platformOps.ts:19-20`、`services/enterprise.ts:27-31`）；后端 `tenant_admin_service.py:111-116` 会拒绝平台租户，所以点平台租户只会得到一个报错提示。
- **后果**：误点一次就立即停用一个客户租户，其全部成员登录被拒；平台租户那一行展示了一个注定失败的动作；同一实体两套叫法。
- **修复**：
  - 抽一个共享的 `TenantStatusAction`：确认弹窗写明后果，平台租户置灰并附原因；
  - 共享 `TENANT_STATUS_LABEL`（active→启用 / disabled→已停用）；
  - 两页复用；是否合并页面等 Q-3 决策。
- **应补测试**：PlatformOps.test：①点「禁用」出现确认；②slug=platform 的行按钮 disabled 且有说明文案。

### QA-7 核心实体术语不统一：租户 / 企业 / 公司，能力 / 资产 / 技能 / skill，中转 / 渠道组 / 令牌 / 钥匙
- Dimension：6 / 9 | Severity：minor（覆盖面广） | 工作量：M | 核验：截图
- **现象**：
  - 注册页叫「企业注册 / 企业名」；后台有企业管理页、「公司管理」tab、「公司名」列、「新建公司」按钮；数据里是「默认租户 / 平台租户」；用户页叫「归属公司」；平台运营台叫「企业名称」「租户管理」。
  - 菜单叫「能力资产」，页面叫「能力市场」，按钮是「导入资产」「清理失源资产」，tab 叫「技能」，类型列显示原始值 `skill`，官网定价写「私有技能库」，筛选叫「宿主」。
  - 中转相关：「我的渠道组」、「中转站管控」、「出站拉数钥匙」、「渠道组令牌」。
- **根因**：没有术语表。shared 只导出了 `TIER_LABELS` 和 `ASSET_TYPE_LABELS`（`frontend/shared/src/index.ts:3`），类型列也没有用它（看截图是原始值 `skill`）。
- **后果**：新租户无法判断「公司 / 租户 / 企业」是否同一个东西；客服成本上升；也和 R5 QA-16 的角色口径问题叠加。
- **修复**：在 shared 加 `GLOSSARY`（对外统一用「企业」，「租户」只留在平台超管视图；对外统一用「能力」，「资产」只在治理台出现），所有标签从这里取；类型列用 `ASSET_TYPE_LABELS`。
- **应补验收**：门禁用 grep 统计页面里的硬编码「公司」「租户」文案数，只允许减少。

### QA-8 原始机器值直接给用户看：日期至少三种格式，还有英文状态码、审计码、slug、Python repr
- Dimension：9 / 6 | Severity：minor | 工作量：S–M | 核验：截图 + 静态
- **现象**：
  - 日期：
    - 原始 ISO `2026-09-14T09:02:53`：采集任务、数据中心、日志中心、结果抽屉、模板；
    - 带微秒 `2026-09-14T09:45:04.535066`：能力目录「最近上架」；
    - `2026/9/27 18:23:58`：用户页、成员页。
  - 其他原始值：`active`；审计动作 `member.delete`、对象 `user#4`、`ai_plan#6`；资产名是 `dev-team__brainstorming` 这类 slug；LLM 成本里的供应商是 `config`；数据中心「内容」列是 `{'arg…`（Python dict repr）。
- **根因**：
  - 原始 ISO：`components/spider/TaskList.tsx:147`、`components/spider/TemplateTab.tsx:88`、`pages/LogCenter.tsx:75`、`pages/Data.tsx:225`、`components/spider/ResultDrawer.tsx:121`、`pages/market/ListingControls.tsx:65`；
  - `toLocaleString`：`pages/Users.tsx:215`、`pages/Members.tsx:244`；
  - 各页自带的 formatTime/fmtTime：`OutboundKeys.tsx:159`、`newapi/*`；
  - `Members.tsx:246-247` 原样显示 action/target；
  - shared 里没有日期格式化函数（`shared/src/index.ts` 没有导出）。
- **后果**：可读性差，跨页对比时间容易出错；审计记录非技术人员看不懂。
- **修复**：
  - shared 增加 `formatDateTime`（统一 `YYYY-MM-DD HH:mm:ss`，Asia/Shanghai）并在全部表格中使用；
  - 审计动作做中文映射，例如 `member.delete`→「删除成员」；
  - 资产列表优先显示 display_name，slug 作为副文；
  - 内容列用 JSON 格式显示。
- **应补验收**：门禁禁止 `dataIndex: 'created_at'` 不带 render。

### QA-9 1440 宽下的版式缺陷：文字重叠、逐字换行、操作列被裁切、内容区上内边距为 0
- Dimension：9 | Severity：minor | 工作量：S | 核验：截图 + 静态
- **现象**：
  - 中转站管控「刚才发生了什么」表里，`config_update` 标签和「额度配置更新…」叠在一起（admin_newapi-1440）。
  - 逐字换行：「exam/ple」（任务列表）、「DeepSee/k」（LLM 配置）、「当前任/务」（节点表头）、采集时间折成两行（数据中心）。
  - LLM 配置的操作列被右边缘裁掉，编辑图标只露出一半。
  - 用户页状态下拉被截成「在职（全...」。
  - 每一页的首行内容都贴着白色容器顶边（仪表盘标题、AI 页按钮、我的安装空态插图、定价页标题）；日志中心是卡片套卡片再套容器，三层边框。
- **根因**：
  - `components/newapi/Overview3q.tsx:266`：动作列 `width: 80`，标签没有省略号，而且 `ACTION_TAG` 缺 `config_update` 的映射；
  - 各 Table 没有 `scroll.x` 和列最小宽度；
  - `AdminLayout.tsx:92` Content 写的是 `padding: '0 24px 24px'`，上内边距为 0。
- **修复**：
  - Content 改为 `padding: 24`；
  - 表格统一 `scroll={{x:'max-content'}}`，名称列设 `minWidth`，标签加 `ellipsis`；
  - 补齐 ACTION_TAG；
  - 日志中心去掉内层 Card。
- **应补验收**：视觉回归（Playwright `toHaveScreenshot`）覆盖上述 6 页。

### QA-10 导航定位弱：当前分组不展开、两套 tab 模式、页名兜底为「后台管理」、同一功能两个入口
- Dimension：9 | Severity：minor | 工作量：S | 核验：截图 + 静态
- **现象**：
  - 所有页面侧栏五个分组都是折叠的，看不到当前页对应哪一项。
  - 采集任务、AI、中转站把 tab 放在顶栏；企业、RBAC、日志中心、平台运营台、用量、能力市场把 tab 放在内容区。
  - /enterprise、/rbac、/pricing、/billing/checkout 的顶栏页名都显示「后台管理」。
  - 仪表盘上「欢迎回来，admin」出现两次（顶栏和页内）。
  - 「运营管理 > 日志中心 > 任务日志」和「数据工厂 > 运行日志」是同一个组件。
  - 「我的渠道组」挂在「概览」下，「出站拉数钥匙」挂在「数据工厂」下，归类令人意外。
- **根因**：
  - `AdminLayout.tsx:51-57` 的 Menu 没有 `openKeys`/`defaultOpenKeys`；
  - `config/menuConfig.tsx:104-111` 只覆盖菜单内路由，其余兜底为「后台管理」；
  - `Dashboard.tsx:141-143` 与 `AdminLayout.tsx:78` 重复欢迎语；
  - `menuConfig.tsx:46-50,62-64` 决定了分组归属。
- **修复**：
  - `defaultOpenKeys` 由当前路径推导；
  - 给幽灵页和计费页建一张路由→标题表；
  - 页级 tab 只保留一种模式（推荐 PageHeaderTabs）；
  - 删掉页内欢迎语，改成页面用途说明；
  - 日志中心只保留审计日志。

### QA-11 权限死胡同和角色无关的 CTA：超管结账页没有下一步；「定制」档配「去结账」
- Dimension：9 / 8 权限 | Severity：minor | 工作量：S | 核验：截图 + 静态 + 已记录执行
- **现象**：
  - admin_billing_checkout-1440 整页只有一条「超管不能代企业支付」信息条，没有任何操作；运行记录里有一次预期内的 `400 GET /billing/checkout`，同时产生一条 console error（ui-runtime-summary.md:49）。
  - admin_pricing-1440 对不能付款的超管仍然显示两个「去结账」。
  - 官网和后台的「企业档：定制」都配「去结账」，定制价应当是联系我们。
  - admin_relay-1440 对平台超管显示「未开通中转……去升级」。
- **根因**：
  - `pages/Checkout.tsx:210-213` 超管分支没有 `action`，而旁边 `:206` 的分支有「返回定价」；
  - 定价卡的 CTA 不看角色、也不看档位类型。
- **修复**：
  - 超管分支加「返回定价」和「去平台运营台」；
  - 已知超管时不发这次预检请求；
  - 定价页对超管隐藏结账 CTA，改为只读说明；
  - 企业档 CTA 等 Q-4 决策。
- **应补测试**：Checkout.test 断言超管分支至少有一个按钮。

### QA-12 官网 375 宽顶栏折成两行：Logo 贴顶，「管理后台」按钮压住下沿，没有移动端菜单
- Dimension：9 | Severity：minor | 工作量：S | 核验：截图 + 静态
- **现象**：official_-375、pricing-375、register-375、capabilities-375、terms-375、no-such-page-375 都一样：Logo 贴顶，导航和按钮挤成两行，按钮下缘碰到顶栏底边。
- **根因**：`frontend/official/src/components/layout/SiteLayout.tsx:72,92` 用 `flexWrap: 'wrap'` 当作移动端兜底，行间距为 0。
- **修复**：<768 时导航收进汉堡菜单（Drawer），「管理后台」放进菜单，顶栏固定 56px；给行加 `rowGap`。
- **应补验收**：375 截图中顶栏高度 ≤ 64，且元素包围盒不越出顶栏。

### QA-13 按钮文字间距不一致：「保 存」「查 询」「禁 用」和「刷新」「签发出站拉数钥匙」并存
- Dimension：9 一致性 | Severity：minor | 工作量：S | 核验：截图 + 静态
- **根因**：antd 默认会在两个汉字的按钮中间插空格，带图标的按钮不插；`frontend/admin/src/index.tsx:22-34` 的 ConfigProvider 没有设置 `button={{ autoInsertSpace: false }}`（官网同理，未核对）。
- **修复**：两个应用的 ConfigProvider 都加上 `button={{ autoInsertSpace: false }}`。

### QA-14 用户界面暴露内部配置与服务器路径
- Dimension：4 信息泄露 / 9 | Severity：minor | 工作量：S | 核验：截图
- **现象**：
  - 租户可见的用量页 Webhook 说明里写着「密钥走 AUTO_AGENTS_WEBHOOK__SECRET_KEY」（admin_usage-1440；`/usage` 是 tenantOnly，`menuConfig.tsx:48`）。
  - 运行日志和日志中心直接输出 `/Users/xuyun/auto_agents/.venv/lib/python3.13/site-packages/scrapy/...`，以及中间件清单和大量 DeprecationWarning（admin_spiders_logs-1440、admin_logs-1440）。
  - RBAC 截图显示 viewer 角色也有 `menu:spiders.logs`。
- **后果**：服务器用户名、目录结构、依赖版本泄露给租户；日志里的噪声淹没用户真正关心的采集进度。
- **修复**：
  - 租户可见文案去掉环境变量名，改为「签名密钥由平台统一配置」；
  - 日志接口对非平台超管过滤掉绝对路径和 `py.warnings` 级别，或者只展示任务事件日志；
  - scrapy 侧关闭 DeprecationWarning（属于 F-采集域）。
- **需 manager 核验**：用租户 viewer 身份打开 `/spiders/logs`，确认是否能看到同样的路径。

### QA-15 节点监控显示「重启 69256 次」且状态为「在线」，没有任何警示
- Dimension：9 / 6 | Severity：minor（语义未验证；如果是真实的崩溃循环则应升级） | 工作量：S | 核验：截图
- **现象**：admin_spiders_nodes-1440 节点 ffe413c56357，「启动于 2026-09-17T15:33:47 · 重启 69256 次」，状态绿色「在线」。
- **问题**：这要么是字段含义错了（比如心跳次数被当成重启次数），要么是真实的崩溃循环但界面没有阈值和颜色提示。
- **需 manager 核验**：`grep -rn "restart" backend/services backend/app/api/v1 | grep -i node`，确认字段来源。
- **修复方向**：字段名改对；或者设阈值（例如 1h 内重启 >3 次时标橙色并给出排查指引）。

### QA-16 后台令牌只有颜色；硬编码颜色绕开「单一来源」约定
- Dimension：7「配置即代码」精神 / 9 | Severity：minor | 工作量：S–M | 核验：静态 + 截图
- **证据**：
  - `frontend/admin/src/index.tsx:26-32` 只注入了 5 个颜色令牌，间距、字号、圆角、动效都没有令牌；
  - admin 源码中硬编码十六进制颜色 21 处，分布在 9 个文件，其中 `Dashboard.tsx` 11 处（例如 `#3f8600`、`#cf1322`、`#722ed1`、`#52c41a`、`#999`）；
  - 官网 `tokens.css:2-3` 声称「品牌换色只改此文件」，但后台并不遵守；
  - 语义色被当装饰用：管理员角色标签、模型名标签用橙色（warning 色）。
- **修复**：
  - shared 输出完整令牌（color/space/type/radius/motion），admin 用 ConfigProvider token 和 CSS 变量消费；
  - 门禁禁止 pages 中出现 `'#xxxxxx'`；
  - 角色和模型标签改用中性色或品牌色。

### QA-17 次要文字对比度不达 WCAG AA
- Dimension：9 可访问性 | Severity：minor（如果对外承诺无障碍则升 major） | 工作量：S | 核验：静态计算，未跑 axe
- **证据**：
  - 官网 `tokens.css:12` `--site-text-secondary: rgba(0,0,0,0.45)` 叠在 `#fafafa` 上约 **3.3:1**，低于 4.5:1；同文件 `:17` `--color-text-secondary: #595959` 约 7:1 是达标的，也就是有两个「次要文字」令牌，其中一个不达标。
  - 后台 `Dashboard.tsx:171,207,279` 的 `#999` 叠白色约 **2.85:1**。
  - 截图中的「三档价格如下。」、登录页「管理后台登录」都属于浅灰小字。
- **修复**：删掉 `--site-text-secondary` 或改为 #595959；后台次要文字统一用 `token.colorTextSecondary`，不直接写 #999。
- **需 manager 执行**：`npx @axe-core/cli http://127.0.0.1:9113/ http://127.0.0.1:9113/pricing http://127.0.0.1:9113/register --tags wcag2aa`

---

## 对第一轮 R5 的补充证据（不另立条目）
- **R5 QA-2 由「未验证」升为「已记录执行」**：两次登录都记录到 `401 GET /api/v1/auth/permissions`（ui-runtime-summary.md:13,37），说明先拉权限、后写 token 的问题确实存在。
- **R5 QA-8 补一条体验后果**：不勾选「记住我」时，登录后每次整页导航或新开页面都会跳回 /login（ui-runtime-summary.md:3,14-36）。刷新即掉线，界面上却没有任何说明，用户会当成 bug。
- **R5 QA-10 补充运行期告警**：除 R5 已列的，还有：
  - Drawer `width` 已弃用：采集任务、AI、LLM、数据中心四页；
  - Alert `message` 已弃用：平台运营台；
  - Spin `tip` 已弃用：系统设置；
  - 系统设置有「useForm 实例未连接任何 Form」告警（ui-runtime-summary.md:60），可能是多出的无用 form 实例，也可能导致某次 setFieldsValue 不生效，**未验证**。
  - 截图里目前看不到这些告警造成的视觉问题；风险在 antd 升级时集中暴露。
- **R5 QA-18**：用户页状态下拉在 1440 宽下也被截断成「在职（全...」，见 QA-9。

## Dimensions checked
1. 标准符合 ⚠️：没有 spec 和产品层，只能对照代码注释里的 FR/GWT 意图。首页承诺的「粘贴链接即可出数」对应的 AI 流程出现两套步骤条（QA-4）；「近 7 日」标签和实际口径不符（QA-5）。
2. 标准质量 ➖：输入里没有 GWT 或设计契约（edge-states、flows、tokens）可以评判，产品层 design-system.md 也不存在。
3. 证据有效性 ⚠️：
   - 首页全页截图因为透明入场动画成了空白证据（QA-3）；
   - 仪表盘图表很可能截在动画结束前（QA-5）；
   - 没有租户负责人视角的截图，也没有后台其余页面的 375 截图，所以权限态和移动态覆盖不全。
4. 安全 ⚠️：内部配置和服务器路径暴露（QA-14）；租户一键停用、无确认（QA-6）。
5. 性能 ➖：设计维度下没有新发现。包体积见 R5 QA-14；运行日志每 2s 轮询只针对未结束的任务，属合理设计。
6. 契约一致性 ⚠️：QA-4、5、6、7、8。
7. 宪法合规 ⚠️：前端不在 R1–R13 的机械检查范围；只违反「配置即代码」和令牌单一来源的精神（QA-16）；依赖方向没有问题。
8. 边界 ⚠️：375 宽（QA-1、12）；权限死胡同（QA-11）；危险操作缺确认（QA-6）；空态和全 0 数据（QA-5 Top5）。
9. 产品价值与体验 ⚠️：
   - 核心路径（AI 规划）和首页（登录后仪表盘）各有一个 major（QA-4、5）；
   - 营销站主导航通向死胡同（QA-2）；
   - 后台完全没有移动端（QA-1）；
   - 首页主体没法审（QA-3），需要复拍后补审。

## Strengths（改进时应保留）
1. **失败 / 空 / 关闭三态分开写文案**：`official/src/pages/capabilityMarket.ts:29-35` 把关闭、空货架、筛选无结果、加载失败写成不同常量；`admin/src/pages/Dashboard.tsx:104-111,157-160` 失败时显示错误和重试，不用 0 冒充；「我的安装」空态带「去能力市场」CTA（admin_capabilities_installs-1440）。
2. **不能操作时说明原因，而不是藏起来**：企业管理里平台租户的动作置灰，旁边写明「平台租户不可修改名称 / 不可停用」（EnterpriseManagement.tsx:259-270）；RBAC 无改动时按钮显示「保存（无变更）」并禁用；成员页、出站钥匙页有「本页只管什么、别处管什么」的边界说明。
3. **官网 404 设计完整，尊重减少动效**：插图、说明、主按钮齐全，375 也正常；`common.tsx:28-32`、`Home.css:481` 实现了 prefers-reduced-motion；44px 触控令牌（tokens.css:36）。
4. **两端品牌一致**：官网深空蓝 #001529 与后台 dark Sider 同色，主色经 shared `BRAND_TOKENS` 单一来源（admin index.tsx:26-32）；Hero 文案克制诚实（「没有真实聚合时不展示规模数字」）。
5. **信息架构已收敛为 5 组**（menuConfig.tsx:1-8），页名由 `pageTitleFor` 单源推导，消除了原来的双源问题。

## Improvement themes
1. **先决定响应式策略再实现**（QA-1、12）：目标是后台至少在仪表盘、采集任务、运行日志三页小屏可读，官网有移动端菜单。顺序：Q-1 决策 → Sider 加 breakpoint + Drawer 菜单、表格加 scroll.x（M）→ 官网汉堡菜单（S）→ 375/768 截图门禁（S）。
2. **建立后台设计系统底座**（QA-7、8、13、16、17）：目标是 shared 输出完整令牌、`formatDateTime`、术语表和状态标签映射，页面里不再有硬编码颜色和原始值。顺序：ConfigProvider 的 autoInsertSpace 与次要文字色（S）→ formatDateTime 与状态/审计映射（S）→ 术语表并批量替换（M）→ 硬编码颜色门禁（S）。
3. **修通核心旅程**（QA-4、5、2、11）：目标是 AI 流程只有一条步骤条，仪表盘每个数字都标明窗口，市场关闭态和定价 CTA 按角色给出下一步。顺序：删重复步骤条（S）→ 仪表盘口径文案（S）→ 市场关闭态 Result + 隐藏筛选和首页区块（S）→ 结账和定价按角色给 CTA（S）。
4. **合并租户管理**（QA-6、7）：目标是只有一个共享的租户状态组件（带确认和平台守卫），术语统一。顺序：共享组件（S）→ 按 Q-3 决定是否合并页面（M）。
5. **设计 QA 取证流水线**（QA-3，以及维度 3）：目标是每轮都能看到全页真实内容和全部状态。做法：截图脚本统一 `reducedMotion: 'reduce'` + networkidle 后再等 2s；增加租户 owner/viewer 视角；后台全部路由截 375；接入 `toHaveScreenshot` 视觉回归。

## 需 manager 执行的验证
1. 复拍首页：用 Playwright `page.emulateMedia({ reducedMotion: 'reduce' })` 后对 `http://127.0.0.1:9113/` 截 1440/375 全页，供 QA-3 补审首页主体。
2. 复拍仪表盘：`/dashboard` 在 networkidle 后 `waitForTimeout(2000)` 再截图，确认 Top5 和质量分布是否有柱（QA-5）。
3. 用租户 owner 和 viewer 各登录一次，截 `/dashboard /spiders/logs /usage /capabilities /members /pricing /billing/checkout`，覆盖权限态和 QA-14 的泄露面。
4. 节点重启字段来源：`grep -rn "restart" backend/services backend/app/api/v1 | grep -i node`（QA-15）。
5. 对比度：`npx @axe-core/cli http://127.0.0.1:9113/ http://127.0.0.1:9113/pricing http://127.0.0.1:9113/register --tags wcag2aa`（QA-17）。
6. QA-6 的点击验证是写操作，需要 operator 批准后在测试环境做：平台运营台点平台租户的「禁用」，预期报错「平台租户不可停用。」；点普通租户，确认没有二次确认就生效。

## 返回项
- **Output paths**：本报告供 manager 保存到 `/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/F5-design/05-review/findings.md`（我没有写任何文件）。
- **Decisions**：无（本轮只出报告）。
- **Open questions**（战略，待确认）：
  - **Q-1 后台是否支持移动端？** 选项：A 明确只支持桌面（min-width 1280 + 提示）；B 仪表盘、采集任务、运行日志三页小屏只读可用；C 全站响应式。推荐：现在先做 A（S），确认有值班场景后做 B（M）。
  - **Q-2 能力市场未开放期间，入口怎么处理？** 选项：A 隐藏导航项和首页区块；B 保留入口，显示「即将开放」并附注册 CTA；C 维持现状。推荐 A；如果增长侧需要预热，再用 B。
  - **Q-3 /enterprise 与 /platform-ops 是否合并？** ADR-0021 已授权 /enterprise 作为超管的幽灵页。选项：A 两页保留，共用组件；B 合并到平台运营台。推荐先 A，下个迭代再 B。
  - **Q-4 企业档（定制）的 CTA 用什么？** 选项：A「联系我们」（表单或邮件）；B 保持「去结账」。推荐 A。定价和销售方式由 operator 决定。
- **Product-delta**：无（产品层 docs/product 不存在；建议 bootstrap design-system.md 时吸收 Improvement themes 第 2 条）。
- **Lessons**（已核实）：
  - framer-motion 的 `whileInView` + `initial opacity:0` 会让全页截图的首屏以下空白（common.tsx:34-38，截图 official_-1440 为证）。设计 QA 截图要先 `emulateMedia({reducedMotion:'reduce'})` 或逐段滚动。
  - antd 的 `<Sider>` 不设 `breakpoint` 就不会自动折叠（AdminLayout.tsx:42，截图 admin_*-375 为证）。
