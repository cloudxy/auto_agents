<!-- manager 落盘：2026-09-28，reviewer（G-fresh）最终交付原文逐字提取自其交付记录；packet 见 ../packets/ -->

# F2-product-ops 独立审查报告（G-fresh，第二轮，仅报告）

- 角色：sdlc-workflow:reviewer ｜ 主技能：sdlc-workflow:findings ｜ 评判视角：signals（信号收集）与 enablement（上线告知）的优秀标准
- 交付路径（由 manager 落盘）：`/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/F2-product-ops/05-review/findings.md`
- 我做了什么：只做了静态阅读，加上查看 manager 已经记录的执行产物（截图、ui-runtime-summary、devdb 只读查询）。我没有执行任何命令，也没有自己复现过任何结论。需要 manager 复现的地方，每条都写了具体命令或步骤。
- 去重说明：第一轮 R1–R7 和本轮已落盘的 F1、F6、B1、B3 结论不重复报告，只在需要时引用并注明新增了什么（例如 F1 QA-5「核心价值未证明」、F6 QA-3「值班闸被绕过」、R1「notify-config 可被租户写」、B1-6「测试写 dev 库」）。

## Snapshot（manager 提供，原样照录）
- HEAD `82259f301c060dbf411424ec8775f29944e313e1`（工作区只新增了 docs/ops/）
- explore_roots `git ls-files -s` 的 sha256：`95cf62f8a4959ff21f7d9d1199e0dd34d8b470de0c061604277e1568f6dd311d`
- 输入：module-inventory.md、ui-runtime-summary.md、devdb-readonly.txt、README.md、CONTEXT.md、ops_contact.py、product_events.py、notify.yml、official.yml，以及 11 张截图（逐张都看过）。product_context 为空，因为 docs/product 还没有初始化。

---

## FINDINGS

### QA-F2-1 在「系统设置 → Webhook 与通知渠道」保存成功后，实际不会发出任何通知
- 维度：1 / 9 ｜ 严重度：**major**
- **现象**：`admin_settings-1440.png` 里的「通用 Webhook 地址」已保存为 `https://hooks.example.com/test`，钉钉和企业微信也能填写并「保存渠道配置」。页面上没有「启用渠道」开关，没有「发送测试通知」，也没有回显「当前生效渠道」。
- **触发条件**：采用默认配置时，在设置页填好钉钉 URL 并保存，然后让任意任务进入终态或触发告警。
- **根因**：
  - `backend/services/notify_service.py:50-51`：要发哪些渠道只看 yml 的 `NOTIFY.CHANNELS`，而 `config/default/notify.yml:14-15` 默认只有 `[log]`。
  - `notify_service.py:89-100`（任务终态）和 `:144-176`（告警文本）都只遍历 `self._channels`。
  - `_channel_url`（`:106-133`）只负责给已经启用的渠道找 URL。
  - `backend/app/api/v1/admin.py:277-279` 只保存 3 个 URL 键，没有 channels 键。
  - 所以在 UI 上保存 URL，对「要不要发」没有任何影响。
- **后果**：运营以为钉钉告警已经接通，实际上任务失败、队列积压的告警只写进了后端日志，值班的人收不到。F1 在 findings.md:179 只指出「默认只有 log，与官网宣称不符」；本条补充的是：**通过 UI 配置这条路本身也是断的**，而且界面给人「已配置」的错觉。
- **修复方案**：
  1. 把启用渠道改成由「URL 非空」推导出来，或者在 system_configs 里增加 `notify.channels`，并在设置页提供开关。
  2. 增加 `POST /admin/notify-config/test`，页面上加「发送测试通知」按钮，并回显每个渠道的 HTTP 状态。
  3. 在已有的 `GET /admin/webhook-status` 里扩展「最近一次发送时间 / 结果」，在卡片上展示。
  4. 顺带落实 R1 已提出的出站 URL 私网校验。
- **应补的测试或验收**：
  - pytest：`PUT /admin/notify-config {dingtalk_url}` → 调用 `notify_text` → 用 respx 断言目标 URL 收到了 POST（现在应该是红的）。
  - 前端：点「发送测试通知」后显示成功或失败原因。
- **工作量**：M
- **核验方式**：静态阅读 + 截图。manager 复现步骤：
  1. 运行 `nc -lk 18080`。
  2. 在设置页把通用 Webhook 改成 `http://127.0.0.1:18080/x` 并保存。
  3. 在「采集任务」里对任务 #3 点「再次运行」。
  4. 预期现状：nc 收不到任何请求，`logs/` 里只有 log 渠道的记录。

### QA-F2-2 租户自己建的告警规则永远不会通知到租户：规则里的 channels 被忽略，告警走平台全局渠道，站内通知只写不读
- 维度：1 / 4 / 9 ｜ 严重度：**major**
- **现象**：租户在「采集任务 → 告警规则」建规则时可以保存 `channels`（`frontend/admin/src/services/spiders.ts:366,384,397`）。但规则触发后，租户在任何渠道都看不到。
- **根因**：
  - `backend/services/alert_service.py:51-54`：`channels` 只做了 JSON 序列化存库，发送时没有读取它。
  - `alert_service.py:242-250`：`_send_alert` 调用 `notify_task_finished`，走的是全局渠道（`notify_service.py:89`）。
  - `alert_service.py:169-172`：queue_depth 调用 `notify_text`，同样走全局渠道。
  - `alert_service.py:173-184` 会写 `Notification` 行，但 `backend/app/api` 下搜不到任何 `notifications` 路由，`frontend/admin/src` 里也没有通知中心或铃铛。结果是这些行只写不读。
- **后果**：
  - 租户零触达，「失败 → 主动介入」这条运营闭环不存在。
  - 租户的规则名、爬虫名、错误信息会进入**平台**的日志和群（一旦平台启用了渠道），平台渠道因此会收到其他租户的信息。
- **待核验的问题**：`_check_consecutive_failures`（`:198-203`）和 `_check_result_drop`（`:214-223`）只按 `spider_name` 过滤。它们运行在 `spider_task_service.py:686` 新建的 `AsyncSession` 里，这个后台会话有没有 tenant_scope，我没有验证。如果没有，租户 A 的规则会被其他租户同名爬虫的失败触发。请 manager 用 pytest 构造「两个租户、同一个 generic 爬虫」来验证。
- **修复方案**：
  1. 按规则的 `channels` 分发。
  2. 让租户接收地址归租户所有：复用交付 webhook 的 opt-in，或新增租户通知设置。
  3. 新增 `GET /notifications/me`，后台顶栏加未读铃铛。
  4. 平台全局渠道只接收平台级事件（死信、网关、探针）。
- **应补的测试或验收**：
  - pytest：租户规则命中后，租户的 webhook 收到请求，平台渠道收不到。
  - `GET /notifications/me` 只返回本租户、本人的数据。
  - 跨租户同名爬虫不会误触发。
- **工作量**：L
- **核验方式**：静态阅读。
- 需要决策的点见下文 Q-OPS-NOTIFY。

### QA-F2-3 产品事件没法把测试和自动化流量与真实用户分开：dev 库 292 条全部 fixture=0，疑似混有测试套件和本次审查自己写入的事件
- 维度：3 / 9 ｜ 严重度：**major**
- **现象**：
  - `devdb-readonly.txt:38-50`：13 种事件的 fixture 列全部是 0；`internal_fixture_tenants` 为 0 行（`:34`）。
  - 平台运营台截图里有一个看起来是自动化生成的租户「C4闸门企业1789347758」（slug `c4-1789347758`），但没有被标记为 fixture。
- **根因**：
  - `backend/services/product_event_service.py:49-52`：fixture 只按 `tenant_id` 查 `internal_fixture_tenants`。`tenant_id is None` 时直接返回 False，所以官网匿名事件、`duty_entry_opened`（`backend/app/api/v1/newapi.py:62-65` 没有传 tenant_id）、平台超管事件都**不可能**被标记。
  - `frontend/official/src/services/beacon.ts:42-51`：没有自动化标识（例如 `navigator.webdriver`、内部 cookie 或 header）。
  - fixture 租户需要人工登记，而这张表是空的。
- **推断（需 manager 核验，不是已证实的事实）**：
  - `login_succeeded` 最后一条是 22:57:20，`duty_entry_opened` 是 22:58:19，`official_page_viewed` 是 22:55:36，都在 2026-09-27。这和 manager 用 Playwright 登录、浏览 `/newapi` 与官网的时间段吻合。
  - `sync_completed` 最后一条 18:23:53，和成员页截图里测试账号 `m-owner` 的 `member.create/delete` 审计时间 18:23:58 相差 5 秒。B1-6 已经确认测试套件会把审计写进 dev 库，同样的根因很可能也在往 dev 库写 product_events。
  - 两张表的时区口径（`ProductEvents.tsx:62` 声称 UTC 存储）还需要一并确认。
- **后果**：现在只有 5 个租户、1 个任务，噪声比信号还多。漏斗、活跃度、「谁卡在哪一步」都不可信，运营决策会建立在 QA、CI 和 Playwright 的行为上。
- **修复方案**：
  1. 事件加 `traffic_class` 字段，取值 real / internal / automation。
  2. 后端自动判定：平台超管、platform 租户、fixture 租户记为 internal；带 `X-AA-Traffic: automation` 请求头（在 e2e 和 Playwright 里统一注入）或 `navigator.webdriver` 的记为 automation。
  3. 测试套件禁止连接 dev 库，和 B1-6 一起修。
  4. 查询和看板默认排除非 real 流量。
- **应补的测试或验收**：
  - pytest：带 automation 请求头的事件入库时标记为 automation；超管登录记为 internal；查询默认过滤。
  - 跑一轮完整 pytest 前后对比 `SELECT COUNT(*) FROM auto_agents.product_events`，数量应该不变。
- **工作量**：M
- **核验方式**：已记录的 devdb + 静态阅读。manager 核验 SQL：
  ```sql
  SELECT id,event_name,tenant_id,actor_user_id,anonymous_id,role,occurred_at FROM product_events WHERE occurred_at >= '2026-09-27 18:00' ORDER BY occurred_at;
  SELECT id,slug,name,created_at FROM tenants ORDER BY id;
  ```

### QA-F2-4 首次成功路径：引导第一步要求配置 LLM；注册时已经预置的「示例：公开页面采集」模板没有出现在引导里；第一个任务失败后引导直接消失
- 维度：9 / 8 ｜ 严重度：**major**
- **现象（按代码和截图数步骤）**：
  - 当前路径：官网注册（3 个字段）→ 成功页「登录管理后台」→ 登录 → 仪表盘引导。
  - 引导第 1 步是「配置本企业模型 → LLM 配置」（需要自己的 API Key）；第 2 步是「在采集任务页选择爬虫并提交」（需要会写 URL 和 CSS/XPath 选择器）；第 3 步是 AI 规划（F1 QA-5 已指出默认不可用）。
  - 这样从注册到拿到第一条结果**至少 10 步，并且要跨过两道知识门槛**。
  - 而注册时已经自动建好了一个可以一键运行的示例模板。走模板只需要「登录 → 任务模板 → 运行 → 结果」4 步，但引导里没有提到它。它藏在采集任务页的第 5 个 Tab「任务模板」里（`admin_spiders_tasks-1440.png`）。
- **根因**：
  - `frontend/admin/src/pages/Dashboard.tsx:115-136`：引导的显示条件是 `total_tasks === 0`，三步的顺序和指向如上。
  - `backend/services/tenant_signup_service.py:112-121`：注册时预置了模板（generic，example.com h1）。
  - 模板运行端点 `POST /api/v1/spiders/templates/{id}/run` 已存在（module-inventory.md:235）。
  - `frontend/official/src/pages/Register.tsx:62`：成功页文案只写了「登录后开始采集」，没有指向任何具体入口。
  - 第一个任务失败后 `total_tasks = 1`，引导消失。仪表盘只显示「失败 1」，没有下一步提示。
- **后果**：激活率直接受损。没有 LLM Key、不懂选择器的企业用户会卡在第 1 步或第 2 步。第一次失败后没有任何兜底，用户就流失了。和 F1 QA-5 不重复：F1 讲的是价值没有被证明、AI 默认不可用；本条讲的是**引导的顺序、示例资产没被用上、失败态没有兜底**。
- **修复方案**：
  1. 引导的主按钮改为「运行示例采集」，调用 templates/{id}/run，完成后自动打开结果抽屉。
  2. LLM 配置降为「进阶（可选）」。
  3. 引导显示与否改用「是否存在 completed 且 result_count > 0 的任务」判断；如果只有失败任务，显示失败原因摘要和「用示例重试」。
  4. 成功页文案改为「登录后点『运行示例』，1 分钟看到第一条数据」。
- **应补的测试或验收**：
  - `Dashboard.test.tsx`：`total_tasks=1`、`completed=0` 时引导仍然显示；存在示例模板时主按钮可见。
  - Playwright J-1（和 F1 QA-5 的 J-1 合并）：新注册租户在 3 次点击之内看到至少 1 条结果。
- **工作量**：M
- **核验方式**：静态阅读 + 截图（只有平台超管视角；**没有租户负责人视角的截图**）。请 manager 补拍：新注册租户首次登录后的 `/dashboard`，以及 `/spiders/tasks` 的「任务模板」Tab。

### QA-F2-5 文案让用户「请联系平台」，但没有任何地方可以联系：值班联系人有两个来源且互不相通，后台完全没有联系或反馈入口
- 维度：6 / 9 ｜ 严重度：**major**
- **现象**：
  - `frontend/admin/src/pages/Login.tsx:17` 的到期或停用提示是「企业已到期或停用，请联系平台」，但页面上没有给出联系方式。
  - 官网首页和注册页截图里都没有「联系平台」。
  - 后台 `frontend/admin/src` 里搜不到任何值班联系、帮助或反馈入口。
- **根因**：
  - 官网 `frontend/official/src/dutyContact.ts:2` 读的是**构建期**变量 `REACT_APP_DUTY_CONTACT`，渲染在 `SiteLayout.tsx:155-156`。
  - 后端 `GET /api/v1/public/ops-contact`（`backend/app/api/v1/ops_contact.py:10-12` 读取 `OPS.DUTY_CONTACT`，默认值在 `config/default/settings.yml:14`，为 `""`）在两个前端里**都没有调用方**，只出现在 `frontend/shared/src/api/schema.d.ts:2522`。
  - 运营修改 `OPS.DUTY_CONTACT` 之后，官网必须重新构建才会变。两个来源会漂移。
  - F6 QA-3 讲的是启动闸被绕过，没有涉及这条消费链路。
- **后果**：以下这些**必须人工介入**的场景都会变成死路：企业到期或停用、配额超限、线下收款待确认（`CONTEXT.md:48`：「平台超管人工确认收款」）、忘记密码（`/auth` 没有找回端点，见 QA-F2-9）。同时没有反馈渠道，也就收不到任何「用户说了什么」的信号。
- **修复方案**：
  1. 官网和后台都在运行时读取 `/public/ops-contact`，构建期变量只作为兜底。
  2. 后台顶栏加「帮助 / 联系平台」。
  3. 所有「请联系平台」的文案都内联实际联系方式；联系方式为空时改写为可自助的下一步。
  4. 加一个轻量反馈入口：`POST /public/feedback` 或 `POST /feedback`，写入事件，并推送到平台渠道。
- **应补的测试或验收**：
  - official `SiteLayout.test`：mock API 返回联系方式后链接可见。
  - `Login.test`：到期文案包含联系方式。
  - pytest：反馈写入并触发平台通知。
- **工作量**：S（运行时读取）/ M（包含反馈入口）
- **核验方式**：静态阅读 + 截图。
- 需要决策的点见 Q-OPS-DUTY（代码里已经记为开放项：`backend/app/__init__.py:73`）。

### QA-F2-6 运营台回答不了「谁卡在哪一步」：产品事实页没有时间范围、分页、漏斗，也没有 fixture 过滤；租户表没有生命周期字段
- 维度：9 / 5 ｜ 严重度：**major**
- **现象**：
  - 产品事实 Tab 只能按「事件名 / 企业 ID」查询。
  - 租户管理表（`admin_platform-ops-1440.png`）只有 Slug、名称、状态、配额、到期。演示租户的配额显示为「- / - / -」。
- **根因**：
  - `frontend/admin/src/pages/ProductEvents.tsx:18-21,64-88`：没有接入 API 已经支持的 `occurred_from/occurred_to/is_internal_fixture`（`backend/app/api/v1/product_events.py:51-57`）。
  - `ProductEvents.tsx:107` 设置了 `pagination={false}`，而后端默认 `limit=100`（`product_events.py:57`）。页面显示「共 N 条」，但只渲染前 100 条，也没法翻页。
  - 没有任何聚合或漏斗端点。
  - `frontend/admin/src/pages/PlatformOps.tsx:76-115` 的租户列里没有注册时间、负责人邮箱、最近登录、首次出数时间、结果量。
  - 注册时写入 `quota=None`，表示使用免费档默认值（`tenant_signup_service.py:85`），但 UI 直接显示「-」（`PlatformOps.tsx:87`）。运营分不清这是「无限」「默认」还是「未设置」。
  - 指标注册表（module-inventory.md:296-326）里没有激活类指标，例如注册 → 首次出数转化率、首次出数耗时。
- **后果**：「新注册的企业里谁还没跑出第一条数据」「卡在登录、提交还是失败」这类日常运营问题只能手写 SQL。运营台没法形成每日动作。
- **修复方案**：
  1. 新增 `GET /admin/funnel?from&to&traffic_class=real`，按租户返回阶段：signup → login → task_run_submitted → task_completed（result > 0）→ results_exported。
  2. 租户表增加上述生命周期列，加「卡在第 N 步」筛选，配额显示有效值和来源（默认 / 自定义）。
  3. 产品事实页加时间范围和服务端分页，默认排除 internal 和 automation。
  4. 指标注册表补充 `activation_rate` 和 `time_to_first_result`。
- **应补的测试或验收**：
  - pytest：构造 3 个租户分别停在 3 个阶段，funnel 接口返回正确的阶段分布。
  - 前端：`total > 100` 时可以翻页。
- **工作量**：L
- **核验方式**：静态阅读 + 截图。

### QA-F2-7 运营台的「禁用」一点就执行：没有二次确认、没有原因、不通知租户；platform 行仍然显示可点的「禁用」
- 维度：8 / 9 ｜ 严重度：**major**
- **现象**：截图里每一行（包括 `platform`、`default`）都有红色「禁用」按钮，紧挨着「编辑」。
- **根因**：
  - `frontend/admin/src/pages/PlatformOps.tsx:65-74,99-102`：`onToggleStatus` 直接 PATCH `status=disabled`，没有 Popconfirm。对比同一页面的死信操作，用了 `Modal.confirm` 或 Popconfirm（`:149-151,183`）。
  - 列表接口已经返回 `is_platform_default`（`backend/services/tenant_admin_service.py:62,71`），但 UI 没有使用。后端会拒绝停用 platform（`:111-116`），用户点了只会看到报错。
- **后果**：一次误点就会让一家企业的全部成员立即被挡在登录外，看到的是「请联系平台」（而平台没有联系方式，见 QA-F2-5）。停用原因没有记录，租户也收不到通知。B1-3（成员页可以停用自己）和 B1-5（到期状态机）都没有覆盖这个入口。
- **修复方案**：
  1. 禁用前 Popconfirm 或 Modal，必须填写原因，原因写入审计和 `tenants.status_reason`。
  2. platform 行隐藏或禁用该按钮。
  3. 禁用或启用时通知租户负责人（依赖 QA-F2-2 的租户通知通道）。
  4. 登录页的停用提示展示原因和联系方式。
- **应补的测试或验收**：
  - `PlatformOps.test`：点击「禁用」先弹出确认，不填原因不能提交；platform 行没有该按钮。
  - pytest：原因被写入审计。
- **工作量**：S–M
- **核验方式**：静态阅读 + 截图。

### QA-F2-8 发布告知机制缺失：没有面向用户的更新说明或版本信息；newapi 值班 URL「一周期保留」没有任何弃用信号
- 维度：6 / 9 ｜ 严重度：minor（出现付费租户或外部集成方后升为 major）
- **现象与根因**：
  - 在 `frontend/admin/src`、`frontend/official/src`、`backend/app`、`backend/services` 里搜索 changelog、更新日志、更新说明、release notes、Deprecation、Sunset、弃用，只找到技能资产自己的 CHANGELOG（`backend/services/skill_service.py:724-736`），和平台发布无关。
  - `README.md:269` 写着「值班 URL `/api/v1/newapi` 一周期保留」，但没有写具体日期，也没有弃用提示：`backend/app/api/v1/newapi.py` 不返回 `Deprecation` 或 `Sunset` 响应头，值班页（截图标题「中转站管控」）上也没有提示。
  - 配额、套餐、市场开关这类会影响租户的变更，也没有站内告知位置。
- **后果**：别名下线时，值班书签和脚本会没有预告地失效。租户无法得知功能或配额的变化，运营只能逐个解释。
- **修复方案**：
  1. 后台加「更新说明」抽屉或页面（读取仓库里的 `docs/releases/*.md` 或 system_configs），有新版本时顶栏显示小红点。
  2. newapi 路由统一加上 `Deprecation: true` 和 `Sunset: <日期>` 响应头，值班页顶部显示下线日期横幅。
  3. 对影响租户的变更（套餐、配额）走 QA-F2-2 的租户通知。
- **应补的测试或验收**：
  - pytest：`GET /api/v1/newapi/overview` 的响应头包含 Sunset。
  - 前端：有新版本时显示提示，已读后消失。
- **工作量**：M
- **核验方式**：静态阅读（grep）+ 截图。
- 需要决策的点见 Q-OPS-RELEASE。

### QA-F2-9 注册到登录的衔接断在两处：登录框写「用户名」，成功页却让用户填邮箱；没有找回密码
- 维度：6 / 9 ｜ 严重度：minor
- **根因**：
  - `frontend/admin/src/pages/Login.tsx:171-177` 的标签和占位符都是「用户名」，而 `frontend/official/src/pages/Register.tsx:62` 写的是「登录时请填写注册邮箱」。后端确实支持邮箱登录（`backend/services/auth_service.py:98-100`），所以功能是通的，只是文案互相矛盾。
  - `/api/v1/auth` 只有 login / permissions / menus / register（module-inventory.md:44-48），没有找回密码。负责人忘记密码后，唯一出路是「联系平台」，而联系方式不存在（QA-F2-5）。
- **修复方案**：标签改为「邮箱或用户名」；注册成功页的登录链接带上 `?login_hint=<email>` 预填；新增邮件找回（依赖 SMTP），或者至少在登录页放联系方式。
- **应补的测试或验收**：`Login.test` 断言标签文案，以及 login_hint 能预填。
- **工作量**：S（文案和预填）/ M（找回密码）
- **核验方式**：静态阅读 + 截图（`admin_login-1440.png` 显示「用户名」）。

### QA-F2-10 值班页事件表的「动作」列溢出，盖住了「原因」列；不可用提示「恢复后点刷新」没有给出恢复路径
- 维度：9 ｜ 严重度：minor
- **现象**：`admin_newapi-1440.png` 中，「刚才发生了什么」表格里 `config_upda…` 与「额度配置更新…」重叠。网关不可达的提示只写了「恢复后点刷新」。
- **根因**：
  - `frontend/admin/src/components/newapi/Overview3q.tsx:266-270` 的动作列 `width: 80`，而 `ACTION_TAG` 里没有 `config_updated` 的映射，于是把原始英文值直接渲染成 Tag，超出了列宽。
  - `frontend/admin/src/components/newapi/newapiShared.ts:32` 的文案没有告诉值班人员去检查什么，例如 `LITELLM.ENABLED`、sidecar 进程、`/api/v1/health/deep`。
- **修复方案**：给 `ACTION_TAG` 补上 `config_updated → 配置更新`，列宽改为自适应或加 ellipsis；不可用提示改成可操作的检查清单或 runbook 链接。
- **应补的测试或验收**：`NewApiOps.test` 断言 `config_updated` 显示为中文；截图回归。
- **工作量**：S
- **核验方式**：截图 + 静态阅读。

---

## Strengths（有证据）
1. **事件底座的可靠性设计扎实**：`product_event_service.py:59-111` 使用独立短会话，主路径回滚不会带走事实；锁冲突时降级回主会话；失败不阻塞主路径；`strip_secret_props` 会脱敏；fixture 快照机制也已经在位。
2. **错误文案可操作，并且区分「失败」和「空」**：`Login.tsx:16-20` 对凭据、网络（带「重试」）、限流、会话过期分别给出文案；`ProductEvents.tsx:15-16,90-108` 与 `Dashboard.tsx:157-160` 严格区分加载失败和真的为空，避免用 0 冒充「没跑过」。
3. **激活所需的物料已经存在**：注册时自动挂免费档，并预置可运行的示例模板（`tenant_signup_service.py:99-121`）。离「一键出数」只差引导接线。
4. **运营台的危险操作有先例可循**：死信清空和丢弃都有二次确认和不可恢复说明（`PlatformOps.tsx:149-151,183`），可以直接复用到禁用租户。
5. **值班页的降级态是诚实的**：网关不可达时明确显示「不可用」，以及「仅本地事件/探针」（截图），而不是白屏或假数据。

## Improvement themes（目标状态与落地顺序）
1. **激活闭环（第一优先）**：定义「首次出数」为激活；在仪表盘提供一键运行示例 → 自动打开结果；首个任务失败时给出兜底；登录文案统一（QA-F2-4、QA-F2-9）。验收：新租户 3 次点击内看到第一条数据。
2. **信号可信（与 1 并行）**：引入 traffic_class，测试不再写 dev 库，e2e 统一打自动化请求头；在此基础上做 funnel 接口和租户生命周期列（QA-F2-3 → QA-F2-6）。顺序上先净化数据，再做看板。
3. **人工兜底通道**：运行时读取值班联系方式，后台加帮助和反馈入口，所有「请联系平台」内联联系方式（QA-F2-5）。成本低，可以最先上线。
4. **触达分层**：平台渠道、租户渠道、站内通知三层分开；渠道配置保存后即生效，并可测试发送；禁用和配额等事件通知到租户（QA-F2-1 → QA-F2-2 → QA-F2-7）。
5. **发布告知**：后台「更新说明」+ newapi 的 Sunset 响应头和下线日期横幅 + 影响租户的变更走站内通知（QA-F2-8）。放在 3、4 之后。

## 需要 operator 决定的事项（战略，待确认）
- **Q-OPS-DUTY（代码已记为开放：`backend/app/__init__.py:73`）**：对外的联系渠道和响应时效。选项：(a) 邮箱（mailto 已实现）；(b) 企业微信客服或群；(c) 工单系统。**推荐 (a)，并写明时效（如「工作日 24h 内回复」）**，出现付费租户后再评估 (c)。
- **Q-OPS-NOTIFY**：租户告警的触达方式。选项：(a) 站内通知中心；(b) 复用租户交付 webhook；(c) 租户负责人邮箱；(d) 组合。**推荐 (a)+(c)**：站内零配置可用，邮件兜底离线场景；(b) 留给有技术团队的租户。
- **Q-OPS-ACTIVATION**（与北极星相邻，属于战略口径）：激活的定义。选项：(a) 首个 completed 且 result > 0 的任务；(b) 首次导出；(c) 7 日内至少 2 次成功任务。**推荐 (a) 作为激活，(b) 作为价值确认**，(c) 作为留存指标。
- **Q-OPS-RELEASE**：newapi 别名的下线日期和告知对象（只有值班人员，还是也包括外部脚本）。**推荐**：写明具体日期，发出 Sunset 响应头，并至少提前 2 周在值班页显示横幅。

## Dimensions checked
1. 标准符合：⚠️ 通知 UI 的配置路径和告警规则 channels 都没有生效（QA-F2-1、QA-F2-2）；值班联系人的 API 没有调用方（QA-F2-5）。
2. 标准质量：➖ 本项目没有 spec 或 GWT 产品层（docs/product 未初始化），无法对 GWT 的可测性逐条评判；代码注释里引用的 GWT 编号无法对照原文。
3. 证据有效性：⚠️ 产品事件没法区分测试和真实流量，疑似被测试和审查流量污染（QA-F2-3，其中推断部分需要核验）；`SiteLayout.test` 只断言「为空时隐藏」，没有覆盖「有值时显示」和运行时来源，这是空断言。
4. 安全：⚠️ 租户告警内容会进入平台全局渠道（QA-F2-2）；notify-config 的 SSRF 和租户可写问题 R1 已报，这里不重复。
5. 性能：⚠️ 产品事实页没有分页，固定只取 100 条，且没有时间范围（QA-F2-6）。这是可用性问题，不是负载问题；我没有看到新的 N+1。
6. 契约一致：⚠️ 登录的「用户名」和成功页的「邮箱」不一致（QA-F2-9）；值班联系人的构建期变量和运行时 API 是两个事实源（QA-F2-5）；newapi「一周期保留」没有日期（QA-F2-8）。
7. 合规（宪法红线）：✅ 本范围内没有发现硬编码连接串或密钥、跨层 import；日志留痕都有入口 logger（`ops_contact_service.py:10`、`product_event_service.py:104,123,140`）。
8. 边界：⚠️ 第一个任务失败后引导消失（QA-F2-4）；禁用没有确认，platform 行仍有按钮（QA-F2-7）；配额为 null 时显示成「-」（QA-F2-6）。
9. 产品价值与体验：⚠️ 首次成功路径至少 10 步、有两道知识门槛，而现成的 4 步示例路径被藏起来了（QA-F2-4）；运营台回答不了「谁卡在哪」（QA-F2-6）；触达和发布告知缺位。**没有租户负责人视角的截图**，所以租户侧的仪表盘和引导只能从代码推断。官网首页截图中大段空白，可能是滚动动画没触发造成的截图伪影，属于 F5 设计的范围，本报告不作判断。

---

## 需要 manager 执行或补充的核验（我没有执行）
1. QA-F2-1：按上文 `nc -lk 18080` 的步骤，确认 UI 配置的 webhook 收不到请求。
2. QA-F2-3：执行上文两条 SQL；另外跑一轮 `uv run pytest -x -q backend/tests`，比较前后 `SELECT COUNT(*) FROM auto_agents.product_events`。
3. QA-F2-2（待核验部分）：用 pytest 构造两个租户、同一个 generic 爬虫连续失败，看 A 租户的 consecutive_failures 规则会不会被 B 租户的失败触发。
4. QA-F2-4：用新注册租户负责人登录后截图 `/dashboard`、`/spiders/tasks`（任务模板 Tab）；数一下「运行示例模板 → 看到结果」实际需要几次点击。

## Decisions（本次审查采用的操作性默认值）
- F1、F6、B1、B3、R1 已报的问题不重复报；在新增证据或新机制上引用它们的编号。
- 严重度按影响程度和发生可能性来定；QA-F2-8 目前没有外部集成方，所以定为 minor，并写明升为 major 的条件。

## Product-delta 行（供产品层初始化时登记）
- 激活定义：待 Q-OPS-ACTIVATION 决定；指标注册表需要新增 `activation_rate` 和 `time_to_first_result`。
- 触达分层：平台渠道、租户渠道、站内通知是三个独立概念，需要写进 `CONTEXT.md` 的术语表（目前只有「交付 webhook」）。
- 流量分类：`traffic_class`（real / internal / automation）作为产品事件的一级维度。

## Lessons（已核实的陷阱）
- 渠道 URL 能在 UI 配置，并不代表渠道已经启用：NotifyService 的渠道列表只读 yml。以后审查任何「在 UI 保存配置」的功能，都要追到发送端的遍历条件。
- 只按 tenant_id 判定 fixture，会让匿名和平台事件天然漏标。流量分类不能依赖租户归属。
