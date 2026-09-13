# 操作者反馈 · 2026-09-11（define 返工 r2 输入，非合同）

> 性质：管理窗整理的**原始输入**（操作者原话 + 代码事实核对）。合同仍以 `spec.md` 为准；本文件不冻任何句。
> 取证时间：2026-09-11；取证方式：两枚只读探查代理（前端/后端各一）+ 截图两枚。

## 0. 操作者原话（verbatim）

> 当前产品存在的问题：系统管理-用户管理，平台超管，归属公司默认是：AutoAgents，而且不允许删除，可以拥有编辑能力，但是admin这位平台超管比较特殊，不允许删除。当前是总公司后台，可以查看所有信息，所以，被删除的用户，要通过筛选项，查看到，并且超管可以将删除的用户恢复（因为是软删除，所以能够恢复）。用户管理栏目后面，需要增加企业管理，当前仅有用户管理，没有企业管理，就没办法修改企业信息，控制企业账户。企业管理中要有一个默认平台租户选项，因为不是每一个人都有企业，很多人是C端用户，所以，为了方便管理，需要给这些C端用户一个默认归属公司。统一归属成"平台租户"，AutoAgents是平台默认企业，不允许修改它的名称。点击侧边栏菜单后，不要刷新侧边栏，侧边栏与右边的页面要分开。LLM配置管理页面，配置的是平台能够提供的大模型，这里的激活应该是默认使用哪一个模型的意思，也可以根据需要更换大模型。所以，这个不应该是激活，而是在没有指定大模型的场景下，"默认"使用那个大模型。中转站管理中，总览、探针、事件这三个模块没有做明白，探针可以参考：https://checkyourtoken.ai，事件在我的理解里，类似日志的模块。至于总览该如何设计，我希望听听你的意见。系统设置里面， Webhook 是不是通过一个邮件发送接口，通知用户信息。在LLM管理图片中，红色部分框起来的地方，我认为是不需要的，它占据了屏幕的一些空间，导致主要内容不凸显。例如中转站管控页面，可以将总览、探针、事件放到与"欢迎回来，admin"同一高度，只是"总览、探针、事件"它们是三个可以切换的tab。其他的也可以类似修改。
> 能力资产中，必须要做到通过文件或者目录，能够一键导入skill，一键导入agents，一键导入commands，一键导入插件，而且专家团可以通过组装智能体来实现。"源"与"目录"是什么意思？源我能理解，就是外部的资源（插件、skill、智能体等等），但是目录有什么作用？AI采集规划中，默认租户，也要能操作。采集任务栏目中，任务列表、定时任务、采集方案、警告规则，这些栏目都要符合采集的具体需要，不能随意设置。采集方案，要能够编辑，删除，不要讲不属于爬虫的部分，也放进来。

## 1. 事实核对表（用户感知 vs 代码现状）

| # | 反馈项 | 用户感知 | 代码现状（证据） | 差距 |
|---|---|---|---|---|
| F1 | 归属公司默认 AutoAgents | 默认公司叫 AutoAgents 且不可删 | **无 AutoAgents 租户**。种子租户：`default`「默认租户」(alembic 017)、`platform`「平台租户」(alembic 024)。"AutoAgents" 只是站点标题常量（`AdminLayout.tsx:63`/`Settings.tsx:91`，配置键 `site.name`）。建用户不选公司挂 platform 租户（`user_service.py:117-125`） | 命名错位：平台默认企业=「平台租户」已存在但用户不知道；需在产品上显式化 |
| F2 | admin 不可删除 | admin 特殊不可删 | 保护只有两条：不能删自己（`user_service.py:230`）、不能删**最后一个**平台超管（`:237-246`）。存在第二个超管时 admin 本体可删 | 需冻「种子 admin 不可删」或保持现状由 pm 定 |
| F3 | 软删用户可见+可恢复 | 筛选项查看已删、超管恢复 | 软删为真（`deleted_at`+`is_active=False`，`user_service.py:247-248`），列表 `WHERE deleted_at IS NULL`（`:81`）。**无「已删除」筛选、无恢复 API/UI**；软删 username/email 永久占用（`user_repository.py:47-59`） | 需新增：已删筛选 + 恢复端点 + 恢复时的唯一性冲突处理 |
| F4 | 企业管理模块 | 用户管理后面加企业管理；默认平台租户；AutoAgents 不可改名 | **企业管理页已存在**（`EnterpriseManagement.tsx`：公司管理 tab 仅新建+列表；部门管理 tab）。运营台可停用/配额/续期（`PlatformOps.tsx:65-73`；`admin.py:136-174`）。**无改名、无删除企业端点**（`tenant_admin_service.py:75-101` 仅 quota/expires_at/status）。Tenant 模型无 is_default/is_platform 字段（`models/tenant.py:9-26`），platform 身份靠 slug 约定 | 补：企业改名/停用收口到企业管理页 + 平台租户保护（不可改名/不可删/不可停用） |
| F5 | C 端无企业用户归属 | 统一归属「平台租户」 | 现状注册强制建新租户（official `Register.tsx:208-211`、`tenant_signup_service.py:82-86`）；无个人注册路径。超管建号默认挂 platform | 「C 端个人注册」路径本身不存在；本特征范围=归属规则与管理面显式化，是否开个人注册是开放问 |
| F6 | 侧边栏不刷新 | 点菜单不要刷新侧边栏 | 树内切页**不**重挂（布局路由+Outlet）；但 `/newapi` `/platform-ops` `/users` 在独立 `PlatformAdminLayout` 分支（`App.tsx:71-84`），跨组切换 AdminLayout **整树卸载重挂**、闪「权限加载中」（`AdminLayout.tsx:65-69`）；全 19 页 lazy，Suspense fallback 在内容区（`App.tsx:35-40`） | 根因明确：路由双分支。修法=单布局树（平台页并入主树） |
| F7 | 「激活」改「默认」 | 激活应是"未指定模型时默认用它" | 后端**本来就是这个语义**：`is_active` 激活=租户域互斥单选（`llm_provider_repository.py:39-60`）；运行时三段选路：本租户激活行→平台公共行→yml/env（`llm_common/runtime.py:73-134`）；provider 行 `model` 列即默认模型快照；子表 `llm_provider_models.is_default` 至多一行。**API 无请求级 model 参数**（model_override 仅服务端内部） | 主要改文案+交互（「激活」→「默认」）+ UI 呈现默认模型；后端语义基本不动 |
| F8 | 中转站三模块「没做明白」 | 总览/探针/事件要重做；探针参考 checkyourtoken.ai；事件=日志 | **三 tab 均真数据**（`NewApiOps.tsx:237-243`）：总览=`GET /newapi/overview`（LiteLLM 模型/部署+24h 事件+探针判定分布，`newapi_overview_service.py:56-82`）；探针=10 维指纹引擎（身份/知识截止/数值/指令/延迟/reasoning/价格/重复/格式/中英，判 original/spoofed/offline，`channel_probe_service.py:81+`）；事件=`channel_events` 落库（调度启停/budget，`channel_scheduler_service.py:273-308`）。问题在信息呈现与"值班视角"缺失，不是无实现 | 设计层重做（IA+呈现），引擎可复用；checkyourtoken.ai 对照=面向"这把钥匙/渠道现在能不能用、多快、真不真"的实用体检视角 |
| F9 | Webhook 疑问 | 是否邮件发送接口 | **不是邮件接口**。设置页 Webhook 区=**出站通知渠道**（webhook_url 通用 HTTP POST JSON/钉钉/企微，`Settings.tsx:123-159`→`PUT /admin/notify-config`）；后端另有邮件 SMTP 实现（`notify_service.py:234-257`，aiosmtplib，未配置自动跳过）**但设置页无邮件 UI**。触发方：任务终态/告警命中/探针伪装/渠道调度（`spider_task_service.py:541`、`alert_service.py:169` 等）。另有同名不同物的**入站回调** `POST /spider/callback`（HMAC 验签，爬虫终态回流） | 回答操作者即可；可顺带补「邮件通知」配置 UI 或文案说明（pm 定范围） |
| F10 | 页头冗余移除 | 红框区（页题卡+绿色横幅）不要；中转站 tab 与"欢迎回来"同高 | 冗余模式普遍：顶栏 pageTitle（`AdminLayout.tsx:81`）+ 页内 Card title 复述页名（LlmProviders/Spiders/AiPlans/Settings/Users/NewApiOps 均有）+ LLM 页三层标题（h1+Alert 横幅+Card，`LlmProviders.tsx:218-232`） | 统一布局规范：页名/页级 tab 上提到顶栏行，内容区直接开始（designer 塑形） |
| F11 | 能力资产一键导入 | 文件/目录一键导入 skill/agents/commands/plugins；专家团组装智能体 | 现有：技能 URL 导入（`POST /skills/import-url`，GitHub/zip/raw）、服务器目录扫描三个入口（scan-plugins/scan-experts/`/skills/scan`）、源同步只认 local 路径+plugin.json 包（`power_market/sync.py`）。**无浏览器文件/目录上传导入**；agents 类型有枚举无独立扫描（walk 只认 plugin.json 包）。**专家团组装已存在**（`TeamLeafTab.tsx` 组建弹窗：leader+members+workflow_md → `POST /capabilities/teams`），但成员域=expert 资产，不是 agent 资产；无执行引擎（注释"一期无执行态"） | 新增本地上传/目录导入通道（含 agents/commands 类型）；专家团成员域是否扩到智能体=需操作者一句话确认 |
| F12 | AI 采集规划·默认租户可操作 | 默认租户也要能操作 | 无 default/platform 特判；真门=`task_actor_tenant_id` 对平台超管返回 None（`deps.py:127-131`）→ 入队拒绝「没有企业身份，无法入队」（`spider_common.py:41-53`）。admin 实操 AI 规划时试采/上线被拒 | 解法方向：平台超管以「平台租户」身份入队（acting tenant），方案归属平台租户 |
| F13 | 采集任务栏目整改 | 四栏目贴合采集实际；采集方案可编辑/删除；剔除非爬虫部分 | 5 个 tab（含隐藏的"任务模板"）。「采集方案」=爬虫定义合并视图：仅元信息可编辑（title/description，name/类型不可改，`FileTab.tsx:147-165`）、可删除（被引用拒绝）、可启停。**混入**：demo 爬虫（example.py/openweather.py）、能力资产收割器（skill_harvester.py）、AI 流程伪爬虫（flow_generic.py）、scrapy 源码文件清单（GET /spiders/files）。**警告规则 queue_depth 是死规则**（`alert_service.py:91` 显式跳过；调度器只读配置记日志不读规则表，`schedule_service.py:302-311`） | 采集方案编辑面扩容+来源分类过滤；混入项分流；queue_depth 规则接通或下架该类型 |

## 2. 操作者三个提问的回答（管理窗答复，供 pm 引用）

1. **Webhook 是邮件接口吗？** 不是。设置页的 Webhook 是**出站通知渠道配置**：通用 Webhook（向任意 URL POST JSON）、钉钉机器人、企业微信机器人。任务跑完、告警命中、探针发现伪装渠道时会发。邮件通道后端已实现（SMTP）但设置页还没有配置入口。另有一个名字撞车的「入站 Webhook」（爬虫执行完回调平台报结果，HMAC 验签），与通知无关。
2. **「源」与「目录」是什么？** 治理台七叶的前两叶。「**源**」=资产进货渠道：登记一个来源（目前仅本地路径；git/url 尚未支持），点同步后从这里扫描出资产。「**目录**」=全平台资产台账：七类资产（技能/插件/命令/智能体/专家/专家团/团队）的统一登记册，治理位在此控制**上架/下架**（决定官网商店是否可见）。一句话：源管「从哪来」，目录管「有什么、卖不卖」。
3. **中转站「总览」怎么设计（我的意见）**：总览应做成**值班驾驶舱**，一屏回答三问——网关**能不能用**（LiteLLM 可达性、模型数、部署列表，红绿灯头）、渠道**真不真/稳不稳**（每渠道最新探针判定+延迟+24h 事件数+预算窗口用量，问题渠道置顶）、**刚才发生了什么**（最近事件 Top N，点击跳事件 tab）。补一个「立即探测」按钮（现在探针只有定时循环）。排版上按操作者要求：总览/探针/事件三个 tab 上提到与「欢迎回来，admin」同一行，内容区直接开始。

## 3. 与现行 spec 冻结句的关系（pm 必须显式处理）

| 冻结句 | 今日反馈的关系 | 处理方向 |
|---|---|---|
| X-IA「后台五组不重排；幽灵 /enterprise 不修成超管功能页」 | 企业管理页**已存在**且本就是超管页（幽灵页问题是租户走进去，FR-82.1 不变）；反馈只要求增强它 | 不违反五组不重排：系统管理组内既有叶增强 + 平台租户保护；FR-82.1 租户不可见企业管理**保持** |
| FR-61「值班入口同一入口，总览/探针/事件；不另写第二套空态」 | 反馈与冻结句**同向**（tab 上提、三模块做好） | FR-61 扩写为呈现级要求，不新开第二入口 |
| X-VOICE 相关「首页 Webhook 功能卡过承诺 → §5 下一轮」 | 反馈问的是系统设置里的 Webhook（另一物） | 互不影响；回答已给，spec 不动 X-VOICE |
| X-QUOTA（用户可见禁内码） | F12 的「没有企业身份，无法入队」已中文，OK | 新 FR 沿用同句式 |
| 「不代选 Q-VOICE/Q-PRICE/Q-MARKET-USER/Q-AGPL/Q-OPS-COLLECT」 | 今日反馈不碰五问 | 新增 FR 避免绑定五问 |

## 4. 返工 r2 同时必须关闭的评审发现（上一轮遗留）

- **QA-14（major）**：蓝图漏斗与 US-C-01 把「确认收款后配额变三数字」写成 FR-50 完成条件 → 删漏斗最后一步与 US Context「新上限」，停在「我的订单能看见已确认」。
- **QA-15（major）**：GWT-82.1+60.4 与 60.9/X-TRUTH/护栏互否 → 三选一（推荐①：82.1/60.4 加档位前提），只留一句。
- **QA-16（minor）**：GWT-85.2 双 Then → 只留一支。
- **QA-17（minor）**：GWT-91.1 负向空洞 → 钉可观察落点或移出冻结集。
- **QA-18（minor）**：GWT-87.1 经办 Then 写了经办不能做的事 → 只留「已达配额上限+找管理员」。
- **QA-19（minor）**：X-KEY 出站钥匙不能打网关无 GWT → 补一格。

## 5. 根因初判（debug-loop 输入，pm 须给 root_cause 一行）

r1/r2 两轮同型失败：spec/user-story/metrics-blueprint 三文件分头演进、无跨文件一致性对账步骤，冻结句修订时漏改姊妹文件（QA-01…15 多数属此类）。建议 root_cause 候选：「define 产物三文件无单一一致性清单，互否句修复只落在 spec 未传播到 story/blueprint」。本轮新增操作者反馈后，**先建「对外不变式清单」再动三文件**，改一处核三处。
