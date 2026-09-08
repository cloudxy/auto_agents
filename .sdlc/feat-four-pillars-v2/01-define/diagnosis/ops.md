# 运营诊断 · feat-four-pillars-v2

> 作者：/ops｜日期：2026-09-08｜下游：`/pm`（分诊输入；**不下 RICE / 不排期 / 不设计功能 / 不写表**）
> 范围：官网承诺、定价、注册漏斗、工单/反馈通道、竞品叙事、增长数据；对照旧程序 `feat-four-pillars` + grok-files，**不复制为现行合同**。
> **无出处的信号不进本文件。** 本期仍无租户工单系统、无访谈、无生产埋点。能进池子的只有：仓库可核对的对外承诺、已过审设计、旧 SDLC 工件（作输入）、公开竞品文档。把它们当信号，不当用户投票。

对照旧稿：`.sdlc/feat-four-pillars/01-define/diagnosis/ops.md`（2026-09-07 刷新）。本文件回答三问：哪些旧结论仍真、哪些已过期、本轮全新方案必须吸收什么。不写 PRD、不写表结构、不改业务代码。

---

## 0. 任务边界

| 问 | 答 |
|---|---|
| 这是 P9 复盘吗 | **否。** `feat-four-pillars-v2/state.yaml`：`hats_done: []`，`tickets: []`，`current_hat: 定义`。旧程序 `status: superseded`，定义帽 G-fresh **从未过闸**，Wave 0/1 **从未上线**。没有「四周窗实际值」。 |
| 有没有原假设可对照 | **有预测、无发生。** 旧蓝图冻结了 WACT / D1–D4 / 事件名。产品代码里这些事件 **仍 0 命中**。只能写「预测写下、履约未开始」，不能写「提升失败」。 |
| 旧 spec / contract 是现行合同吗 | **不是。** v2 `supersede_reason`：旧工件只作输入。旧 FR 编号、塑形 T-01…T-16、定义帽 T-01…T-17 **三套号段不要混用**。 |
| 有没有增长数字 | **未获取。** Hero 三卡仍是示意；后台 `/admin/stats` 是任务计数。全库无产品分析 SDK。 |
| 有没有用户原声 | **无。** `.scratch/` 不存在。定价写「工单支持」，仓库无租户工单模块。`AGENTS.md` 说工单在 `.scratch/<feature>/issues/`，目录未建。 |
| ops 做什么 | 裁决旧结论；抽出本轮必须吸收的运营信号。不代选 Q-VOICE 等七问。 |

程序目标（lane_judge）：智能采集 + SaaS 多租户 + 中转站外部契约 + Power Market schema。  
对照物：官网 Home / Pricing / Register / Skills / Capabilities；`README.md`；`CONTEXT.md`（2026-09-07b 五类平级）；grok-files 设计与旧 spec/蓝图/contract。

宪法：`sdlc.config.yaml` → `.claude/rules/project_rule.md`。本文件不写连接串、不写表、不写接口形状。

---

## 0.1 本机复跑（2026-09-08，定义帽只读）

| 核对项 | 2026-09-07 旧 ops | 今日 | 裁决 |
|---|---|---|---|
| 产品事件名 / 分析 SDK | `official_page_viewed` / `tenant_signup_succeeded` / gtag / posthog / mixpanel / amplitude **0** | 仍 **0**（产品代码） | **仍真** |
| `POWER_MARKET` / `capability_installs` / `tenants/me/installs` | 代码 0 命中 | 代码仍 0；`listing_state` **只出现在** `CONTEXT.md` 词汇 | 代码侧 **仍真**；词汇侧 **已变** |
| `xlsx` 导出 | 测例期望抛 `BusinessException` | `spider_query_service.py` 仍拒非 csv/json；`test_export_bad_format_raises` 仍在 | **仍真**（P-OPS-01） |
| 定价空头（工单支持 / 渠道组） | 仅 `Pricing.tsx` | 仍仅该文件两处；全库无 stripe/billing/支付模块 | **仍真** |
| 免费档数字 | 「5 / 10,000 / 20 万」= `DEFAULT_QUOTA` | 仍对齐 | **仍真（已兑）** |
| new-api 默认 | `ENABLED` / `SCHEDULER` / `PROBE` 全 `false` | 仍 false；无 `config/default/power_market.yml` | **仍真** |
| 外部拉数 Key | `API_KEYS: []` | 仍空=全拒 | **仍真** |
| 官网 Hero / 双广场 / 注册成功页 | 示意大数、技能+能力双入口、成功钮「再注册一家」 | 页面未改 | **仍真** |
| 能力广场类型 | 四 Tab：技能/插件/专家/专家团 | **仍四 Tab**；`ASSET_TYPE_LABELS` 仍 `expert` / `expert_team` | 相对 CONTEXT **新裂缝** |
| CONTEXT 词汇 | 旧 ops 写「能力资产四类」 | 已是 **五类平级**；「产品文案不再说专家」；订插件不带礼包；上架≠停用；上架是独立闸 | **旧「四类」过期** |
| QA-02（WACT 排除字段未进 GWT） | 旧 ops 当 blocker 仍 open | `state.yaml` review_findings：**fixed**（spec v1.1+）；产品事件仍 0 | **「QA-02 仍 open」过期**；「查不了 WACT」仍真 |
| Q-AGPL | 旧 ops 建议升必答、不代列入 §9.1 | 旧 spec v1.1 已列入 §9.1；七问均 **待确认** | 「未进必答表」**过期**；「未关闭」仍真 |
| 旧程序进度 | `hats_done: []` | 已 `superseded` by v2；票全 todo；G-fresh 未过 | **必须当输入，不当合同** |
| 客户工单 / `.scratch` | 0 | 0；`.scratch/` 不存在 | **仍真** |

---

## 0.2 旧结论裁决（给 `/pm` 的主表）

### A. 仍真（代码/页面 2026-09-08 可并排核对）

| 旧编号 | 结论 | 今日证据 | 本轮怎么用 |
|---|---|---|---|
| S-01 | 官网只卖采集；四柱有三柱在对外面消失 | `SITE_SLOGAN`；`Home.tsx` Hero；`NAV_LINKS` 无中转/LLM/能力市场一词；README 四模块仍无 Power Market | 仍是获客裂缝。首屏句 **仍阻塞 Q-VOICE**，不得新写并列四柱 Hero |
| S-02 | 卖 CSV/Excel，实现拒 xlsx；数据中心顶 100 条 CSV | Features「支持 CSV / Excel 一键导出」；`fmt not in ("csv","json")`；`Data.tsx` `page_size: 100` | 履约裂缝。对外只许写测例允许的字面量 |
| S-03 | Hero `128,000+` / `12 节点` / `3.2 亿条` 是示意；不能当增长 | 三卡仍在，脚注「示意数据」 | 禁止当基线 / OEC |
| S-04 | 「免代码」停在自建规则，无站点模板店 | 预置爬虫仍 example/zhihu/dianping/openweather；CTA「体验 AI 采集流程」只 `scrollIntoView('#ai-flow')` | 不要写成「用户都要 Actor 店」；真问题是第一次出数 |
| S-05 | 注册成功进不了产品；AI 还有 LLM 前置 | 成功钮「再注册一家」「返回官网」；文案却说「即可登录开始第一次采集」；底部 CTA 去 `ADMIN_URL`（默认 localhost:9112） | 激活断链。D2/D3 在路径上接近结构零 |
| S-06 | 出站是平台级 API Key，不是租户凭证 | `EXTERNAL_API.API_KEYS: []` | 场景推断，无原声；强度中 |
| S-07 | 定价卖未履约项；三档 CTA 都进 `/register` | 专业「联系升级」/企业「联系销售」href 都是 `/register`；无销售表单、无工单 | 即使埋点落地，`pricing_pro` / `pricing_enterprise` 也会被写成免费注册 |
| S-08 | 配额硬闸；用量页泄漏内部错误码 | `Usage.tsx` 明文「429 QUOTA_EXCEEDED」；`check_llm_tokens_month` **只被测试调用**，未挂 `llm_chat` | 弱（无超限工单）；是履约裂缝不是「用户嫌配额严」 |
| S-09 / S-10 | 中转官网零曝光、默认关；两本账未解释 | 官网 0 入口；`NEWAPI.*.ENABLED=false`；企业档仍印「渠道组」 | 曝光取决于 Q-RELAY；未关前定价不能假装在卖 |
| S-11 | AGPLv3 是约束不是需求 | `deploy/newapi/README.md` §七 | 约束给 `/pm`；不进 RICE |
| S-12 | 双广场；能力页更空 | 导航仍「技能广场」「能力广场」；技能能搜能开正文；能力四 Tab 无搜索无详情无按钮 | 仍强。且 **比旧稿更重**：CONTEXT 已要求单一「能力市场」+ 五类 |
| S-13 | 公开能力只滤 `stable`，丢掉 `recommended` | `public_list_capabilities` `status="stable"`；技能 `PUBLISHED_STATUSES = ("stable","recommended")` | P-OPS-02；对账必须写清命中哪条 API |
| S-14 | 入站：本机 symlink + GitHub 候选；Kimi 主市场未接 | `_MANIFEST_CANDIDATES` 仍无 `kimi.plugin.json`（设计原文）；`capability-library/README.md` 仍写 Kimi/zcode「未知」 | 文档漂移仍在；本机盘点数字不外推市场规模 |
| S-15 | 「订阅/安装」被设计成一期，商店面零动作 | 无 installs API；卡片不可点 | **不得写成「用户强烈要求安装按钮」** |
| S-16 | Admin 仍「验证后方可分发」 | `admin/.../Capabilities.tsx` L78 原文仍在 | 与 CONTEXT「上架是独立闸门」**直接打架**（见 S-V2-03） |
| S-17 | 公开信任信号不足 | 公开字段仍无 license / health / host_compat / listing_state | 弱；无「这插件安全吗」原声 |
| S-18 | 蓝图事件名冻结、查询面为零 | 产品代码 0 命中 | 元信号仍强。**不要再绑 QA-02 open** |
| S-19 | 后台数字不能当驱动（窗口/时区/总体混用） | `tenant_usage.py` 仍 `datetime.utcnow()` 取月；蓝图要 Asia/Shanghai | 仍真 |
| F-01…F-R2 | 竞品三层结论（见 §5） | 仍未亲自付费试用 | 结论方向仍真；可靠性不变 |
| 免费档配额已对齐 | 5 / 10000 / 200000 | `DEFAULT_QUOTA` + `Pricing.tsx` + `Register.tsx` | 已兑，避免只报缺口 |
| 成员 / 用量页 / BYOK 测例存在 | 部分已兑 | 同旧稿 | 已兑部分 |

### B. 已过期（禁止再写进 v2 方案当现行事实）

| 旧说法 | 为何过期 | 今日应写成 |
|---|---|---|
| 「CONTEXT 能力资产四类」「产品还叫专家」 | `CONTEXT.md` 2026-09-07b 已五类平级；「产品文案不再说专家」；公开 `asset_type` ∈ skill/plugin/command/agent/team | **词汇已迁、访客面未迁**。过期的是 glossary，不是官网 Tab |
| 设计评审「CONTEXT 仍是四类，PR9 必须改 glossary」 | glossary 已改 | PR9 文档债该项关闭；剩下的是 UI/OpenAPI/`ASSET_TYPE_LABELS` |
| ADR-0018「CONTEXT 仍写未经 verify 不得分发」 | CONTEXT 插件行已写「上架是独立闸门」 | glossary 已跟上；Admin 文案没跟上 |
| 「QA-02 仍 open / GWT 盖不住 WACT 排除」当 **现行 blocker** | spec v1.1 已补 `is_marketplace_candidate` / `login_failed`；`state.yaml` QA-02 **fixed** | 契约字面已补；**查询面仍不存在**，所以仍不能判定，原因改成「事件未落地」不是「GWT 缺字段」 |
| 旧 analyst 诊断里「QA-02 仍 open」 | 同日后续 spec 已修；该 analyst 稿未再刷 | 引用 analyst 时核 `review_findings`，不要核 09-07 早稿 |
| 「Q-AGPL 不在 §9.1」 | 旧 spec v1.1 已列入；state.yaml `open_questions` 七问含它 | 问仍开；「没列进必答」过期 |
| 「没有度量蓝图可对照」 | 旧 ops 刷新已纠正；蓝图在 `01-define/metrics-blueprint.md` 与 grok-files | 有预测、无实际 |
| 「appetite 8h 覆盖四柱」 | 旧 state 已改 program waves；v2 `appetite: program; waves pending PM` | 不要把四柱合成一张 8h 票 |
| 旧 ops「S-xx → spec T-xx」= 塑形票号 | 定义帽 T-01=叙事；塑形 T-01=目录豁免。两套号。v2 `tickets: []` | 信号用主题名，**不要把旧 T-xx 当 v2 工单** |
| 把旧 spec v1.4 / contract v2.1 当 **已过闸现行合同** | G-fresh 未过；`hats_done: []`；feature superseded | 可吸收其中 **不变式**（见 §0.3），不可当已批准交付范围 |
| 「本机 `POWER_MARKET` 配置键全库 0，连词汇也没有」 | 词汇已进 CONTEXT；配置 yml 仍无 | 拆开写：设计词在 glossary，运行开关/表/路由仍 0 |

### C. 本轮全新方案必须吸收（旧稿权重不足，或 09-07b 之后才钉死）

这些不是「用户投票」，是 **运营一旦开张就会说错话** 的约束。`/pm` 分诊时若丢掉，Wave 1 商店面会教错分类、错动词、错北极星。

| ID | 必须吸收的运营信号 | 来源 | 若忽略会怎样 |
|---|---|---|---|
| **M-01** | 旧程序 **从未上线、从未过 G-fresh**。v2 是全新方案。吸收旧 **不变式**，不吸收旧 FR 清单当 backlog | `feat-four-pillars/state.yaml` superseded；v2 supersede_reason | 把未过闸 PRD 当合同，重复一轮自批 |
| **M-02** | 对外第一句与北极星核心动作绑在 **Q-VOICE**；默认核心动作是 **出数**，不是订阅。禁止双北极星 | 旧蓝图 §2；spec §9.1 | 市场叙事把 WACT 偷换成订阅数，采集从未交差也被算成功 |
| **M-03** | 未履约不得写成「当前可买」。撤 vs 履约 = **Q-PRICE**；付费形态 = **Q-BILL**。专业/企业 CTA 不得再进同一注册表——否则分档埋点是假的 | S-07；蓝图 `official_cta_clicked` 分档 | 定价剧场继续；四周后「付费意向」= 免费注册 |
| **M-04** | 中转是否出现在获客面 = **Q-RELAY**；对外收费还要先关 **Q-AGPL**。探针差异化成立，但默认关，不宜当「当前可买」 | S-09/S-11；spec §9.1 绑定句 | 空头渠道组；或 AGPL 投诉通道用「工单支持」暗示却无系统 |
| **M-05** | 商品中文名冻结为 **能力市场**（不是广场、不是 Power Market 导航名）。导航只留一个入口（D19） | 旧 spec §9.2；设计 D19 | 继续双入口；访客以为有两个产品 |
| **M-06** | 商店 **五类平级**：技能 / 插件 / 命令 / 智能体 / 专家团。对外 **不说「专家」**。命令是独立可订卡片，不是插件 JSON 附属 | CONTEXT；D22–D26；旧 spec FR-33/36 | 官网仍四 Tab「专家」，glossary 与 OpenAPI 教两套词 |
| **M-07** | **订插件不会带上子卡片。** 合集边不是安装礼包。文案禁止「安装此插件将获得全部技能」 | CONTEXT 插件行；D24；设计评审冻结 | 按宿主市场习惯写文案，上线第一周被当成欺诈 |
| **M-08** | **未上架 ≠ 停用。** unlist = 商店没有、不能新订；已订与引用仍在。黑名单才是停用。客服/FAQ 若说「下架=不能用」是错的 | CONTEXT 上架/停用；D23/D29 | 治理 unlist 后租户以为坏了；或值班把引用解析当 bug |
| **M-09** | 五动词分列，运营材料不得互替：**上架 listed** / **验证 health** / **订阅 installs** / **信任 trusted** / **启用到宿主 enable-host**。Wave 1 按旧设计 **不交付**「启用到宿主」按钮；详情不得写「已在你的宿主里运行」 | ADR-0018；D6/D10/D21；Admin 现文案仍把验证=分发 | 把 MCP 验证当成法律担保（F-05 回避）；或把订阅写成已运行 |
| **M-10** | `dev-team` **只禁插件这一行**，不连坐子卡片。设计评审原文：若开张第一周商店出现三份 `tdd`，**那是运营闸，不是设计缺口** | D20+D25；`power-market-design-review.md` | 工程去「自动合并」，或运营以为名单能一刀切整棵树 |
| **M-11** | 许可黑名单是运营闸（UNLICENSED / Moonshot LicenseRef 默认藏）。公开面今天不过滤 license | 设计 D11；本机 Kimi 抽样 n=16 | 未审专有包出现在广场；或把许可闸写成「障碍」而不是差异化 |
| **M-12** | 增长成功定义仍是 **能判定**，不是提升 x%。Hero / 全历史成功率 / 渠道 24h / 技能均分 / 扫描成功 **禁止当 OEC** | 蓝图 §1；S-03/S-18/S-19 | 用示意大数讲增长故事 |
| **M-13** | AI 规划「试采通过」、技能 AI 分、探针 original/spoofed **都没有评估集**（algo：评估集条数=0）。不得把这些代理指标写成对外效果承诺 | grok-files `feat-four-pillars-algo-diagnosis.md` | 官网「AI 自动规划」被听成已验证准确率 |
| **M-14** | 过期租户：`TenantExpiryService` 存在但 **全库仅自身引用**，未挂 `create_app`。无付费样本，但这是到期叙事的履约洞 | 代码 grep | 若 Wave 2 开始讲「到期拒绝」，今日登录路径未执法 |
| **M-15** | 竞品：回避「第四宿主市场 / 开发者门户分成 / 双收银台 / 平台担保 MCP / 覆盖站点竞赛 / 未履约先标价」。差异化：跨宿主索引+别名、探针外挂、人工评分。这些旧 F 结论 **仍约束文案** | 旧 ops 竞品表；设计 Non-Goals | 新方案把网页做成第四个 `/plugin` |

**不变式（可进 v2 方案、不依赖七问答案）：** 停止说谎（示意大数、Excel、空头套餐、三档同注册）；公司管理员 ≠ 平台超管；候选不计入租户成果/WACT；上架≠验证≠订阅≠启用宿主；五类词表；订插件不带礼包；展示≠停用。

**仍禁止代选：** Q-VOICE / Q-PRICE / Q-RELAY / Q-MARKET-USER / Q-BILL / Q-LLM / Q-AGPL。

---

## 1. 渠道与偏差声明

| 渠道 | 本期数据量 | 偏差 |
|---|---|---|
| 客户工单 / 客服 | **0**（无模块；定价却写「工单支持」） | 不能从「零投诉」推出「没问题」 |
| `.scratch` 工程票 | 目录 **不存在** | AGENTS.md 约定未落地；不是租户声音 |
| 应用商店评论 | **0** | 产品未上架应用商店 |
| 访谈 / NPS / 问卷 | **0** | 无付费用户样本 |
| 使用数据 / 漏斗埋点 | **未获取** | 无产品事件 SDK |
| 官网 / 定价 / README | 已读且复跑 | 销售材料口径（可靠性 **低～中**） |
| 旧 PRD / 蓝图 / contract | 输入，非现行合同 | **内部预测**；七问未关；G-fresh 未过 |
| 设计文档 / 评审 | Accepted + Approve、0 open 产品 issue | 操作者拍板，**不是**用户投票「要市场」 |
| 本机插件树盘点 | 设计 2026-09-07；`.grok/config.toml` 今日仍 5 个 enabled（无 `dev-team`） | 一台开发机，不外推市场供给 |
| 竞品官方文档 | Claude / Kimi / Grok / new-api；采集 SaaS 评测 | 官方 **高**；评测 **中**；**未亲自付费试用** |
| algo 评估集 | **0 条** | 效果数字不可报；不是增长样本 |

**主动反馈通常不到 1%。** 本期连这 1% 的通道都没有。影响面一律 **未量化**，不编人数。

**P9 纪律：** 蓝图目标是「四周后能报每周 WACT=？」。今日：事件查询面不存在 → **预测未开始检验**。不得把 Hero 三卡、全历史成功率、渠道 24h 写成已经好于/差于假设。

---

## 2. 承诺 vs 履约（访客会撞上的裂缝）

| 对外承诺（原文级） | 写在哪 | 仓库现状 | 信号 |
|---|---|---|---|
| 「AI 驱动的智能数据采集系统」；Hero 只讲爬虫 | `SiteLayout.tsx` `SITE_SLOGAN`；`Home.tsx` | README：爬虫+LLM+中转+双前端；程序含 Power Market；CONTEXT 五类市场；官网导航无中转/LLM/「能力市场」 | S-01，M-02 |
| 「支持 CSV / Excel 一键导出」 | `FeaturesSection.tsx` | 任务导出 csv/json；xlsx 抛错；数据中心最多 100 条 CSV（BOM≠xlsx） | S-02 |
| `128,000+` / `12 节点` / `3.2 亿条` | `HERO_STATS`（标了示意） | 无对应 API | S-03 |
| 「无需编写任何代码」；CTA「体验 AI 采集流程」 | `AiFlowSection.tsx`；`Home.tsx` | CTA 只滚到 CSS 模拟；AI 向导要先激活 LLM；Worker 不启则 pending | S-04, S-05 |
| 「注册成功，即可登录开始第一次采集」 | `Register.tsx` `message.success` | 主按钮「再注册一家」+「返回官网」；无去登录 | S-05 |
| 底部「立即开始」 | `Home.tsx` CtaBand | `href={ADMIN_URL}` 默认 `http://localhost:9112`，**绕过注册漏斗** | S-05, S-18 |
| 专业档 ¥299 / 工单支持；企业档渠道组、私有技能库 | `Pricing.tsx` | 三档都进 `/register`；支付/工单/渠道组实现 0 | S-07 |
| 免费档 5 / 10,000 / 20 万 tokens | Pricing / Register | **已对齐** `DEFAULT_QUOTA` | 已兑 |
| 「token 智能调度」 | `README.md` | 官网 0 入口；默认关闭 | S-09 |
| 技能广场 + 能力广场 | 导航 | 技能能搜；能力四 Tab 无搜索无详情无按钮；类型仍 expert | S-12, S-V2-01 |
| 能力市场 / 订阅 / 五类（设计+CONTEXT） | CONTEXT；设计 D19/D22 | 无 `POWER_MARKET` 配置、无安装、无 command/agent 公开枚举 | S-15, M-05…M-09 |

---

## 3. 增长埋点对照（蓝图预测 vs 仓库）

时间窗（蓝图）：Asia/Shanghai 业务日；事件发生时间；相关波次对用户可用后 **4 个上海自然周**。无基线 → 目标 = 能报出数字。  
本表不是「增长差」，是「现在无法判定」。旧蓝图仍是 **唯一写成的口径**；v2 `/pm` 可改口径，但改之前不要另发明百分比。

| 蓝图项 | 预测口径 | 今日能否报 | 缺口 |
|---|---|---|---|
| WACT | 上海周内 ≥1 次「任务 completed 且 result_count>0」企业去重；排除市场候选 | **不能**按事件验收。任务表可弱重构，蓝图禁止用任务表冒充验收 | S-18；候选仍 `spider_results.source=marketplace` |
| D1 注册成功 | `tenant_signup_succeeded` 按次 | 租户行有 `created_at`，无事件 | S-18 |
| D2 168h 首次登录 | 注册成功 ∩ `login_succeeded` 能关联企业 | 登录不落事实表；成功页无登录钮 | S-05, S-18 |
| D3 TTFV | 首次合格 `task_completed` − 注册，中位数 | 两端事件都缺 | S-05, S-18 |
| D4 周订阅租户 | `market_subscribe_succeeded` | 安装对象不存在 | S-15, S-18 |
| 护栏：配额文案 | 抽检 0 次露出 `QUOTA_EXCEEDED` | 用量页 Alert **明文**该串 | S-08 → 转 `/pm` |
| 禁止当 OEC | Hero / 全历史成功率 / 渠道 24h / 技能均分 | 这些数今天就能看见 | S-03, S-19, M-12, M-13 |

冻结事件名（蓝图 §5）在产品代码 **全部 0 命中**。漏斗 F1（官网→第一次出数）与 F3（浏览→订阅）除注册行/任务行可事后数以外全是洞。不允许把「直接打开后台登录」算进官网漏斗分母——这条现在也无法执行（无 `official_page_viewed`），而首页「立即开始」**已经在教人走这条旁路**。

**现有计数器仍不能顶替：**

- 成功率全历史、无 since；「近 7 日」用 `datetime.now()-6d`
- 用量「本月」token = `datetime.utcnow()` 的 `YYYY-MM`（`tenant_usage.py` L26）vs 蓝图 Asia/Shanghai
- `skill_harvester` 与租户成果同表；不排除则污染 WACT
- 质量概览常用最近 1 条已完成任务（旧 analyst；本轮未当增长）

观察（不排序）：① 查询面可查之前不要用 Hero/成功率讲增长 ② 付费 CTA 与免费注册拆开，否则分档事件是假的 ③ Q-VOICE 关闭前不要宣称观察钟已开始 ④ GWT 字段在旧 spec 已补，v2 若重写 FR-15 不要把 QA-02 的洞写回去。交 `/pm`。

---

## 4. 信号清单

渠道偏差见 §1。影响面全部 **未量化**。用户解法 vs 观察分开；不下因果。

### 4.1 继承仍真（编号沿用旧稿，便于对照；**不是** v2 工单号）

S-01…S-19 的证据与强度见 §0.2 A 与旧稿原文样本。本轮不重复粘贴全部原文，关键原文仍可核对：

> 「AutoAgents 是一个 AI 驱动的爬虫管理平台：粘贴目标链接，AI 自动规划采集方案」——`frontend/official/src/pages/Home.tsx`  
> 「综合数据智能平台：**智能爬虫 + 大模型管理（cc-switch 式）+ new-api token 智能调度 + 官网与后台**」——`README.md` L3  
> 「支持 CSV / Excel 一键导出。」——`FeaturesSection.tsx`  
> `HERO_STATS`：`128,000+` / `12 节点` / `3.2 亿条` + 「* 示意数据，非实时统计」  
> 「注册成功，即可登录开始第一次采集」vs 按钮「再注册一家」「返回官网」——`Register.tsx`  
> 专业档「工单支持」CTA「联系升级」`href: '/register'`；企业档「中转站渠道组分配」CTA「联系销售」`href: '/register'`——`Pricing.tsx`  
> 导航「技能广场」「能力广场」——`SiteLayout.tsx`  
> 「插件经 MCP 验证后方可分发（ADR-0001）」——`frontend/admin/src/pages/Capabilities.tsx`  
> 「本轮成功 = 能判定。」——旧 `metrics-blueprint.md` 文首  

强度仍为：

| 强度 | 编号 |
|---|---|
| 强 | S-02, S-03, S-07, S-12, S-14, S-18 |
| 中 | S-01, S-04, S-05, S-06, S-09, S-10, S-13, S-15, S-16, S-19 |
| 弱 | S-08, S-17 |
| 约束 | S-11 |

S-12 / S-16 因 M-05…M-09 **比旧稿更值得被方案吸收**（词汇已迁、页面未迁）。

### 4.2 本轮新增

#### S-V2-01 词汇五类 / 访客面四类+「专家」

| 项 | 内容 |
|---|---|
| 提及次数 | CONTEXT 五类定义 + 官网 Tab 4 + shared 标签 4 + 公开 API 仍 expert 枚举 |
| 影响用户数 | **未量化** |
| 信号强度 | **强**（glossary 与访客面可并排证伪） |
| 用户特征 | 无原声；这是开张后会教错词 |

**原文样本：**

> 「产品文案不再说「专家」。」——`CONTEXT.md` 智能体行  
> 「五类平级」：技能 / 插件 / 命令 / 智能体 / 专家团——同文件  
> `Tabs`：`expert`「专家」、`expert_team`「专家团」——`frontend/official/src/pages/Capabilities.tsx`  
> `ASSET_TYPE_LABELS`：`expert: '专家', expert_team: '专家团'`——`frontend/shared/src/constants/tiers.ts`  
> 公开列表 `type not in ("skill", "plugin", "expert", "expert_team")`——`public_skills.py`  

| 项 | 内容 |
|---|---|
| 用户提的解法 | 无 |
| 观察到的问题 | 内部已经用 agent/team/command 说话；访客仍看到四类专家。命令在 CONTEXT 里是可独立上架的商品，官网上不存在该类 |
| 可能方向 | ① 方案先改词表再谈商店 ② 继续双词直到 Wave 1（成本是文档与客服） |

判断交 `/pm`。ops 不选「先改官网还是先改 API」。

#### S-V2-02 首页主 CTA 绕过注册漏斗

| 项 | 内容 |
|---|---|
| 提及次数 | Hero 次按钮「进入管理后台」+ 底部「立即开始」均 `ADMIN_URL` |
| 信号强度 | **中**（路径可走查；蓝图 F1 分母因此更不可测） |
| 行为交叉 | **未获取** |

**原文：** 底部「打开管理后台，粘贴第一条链接」按钮「立即开始」`href={ADMIN_URL}`。蓝图：不得把直接打开后台算进官网漏斗分母。

观察到的问题：即使补上 `official_page_viewed`，主转化动作仍可能是「打开 localhost 后台」，注册事件与页面浏览拼不上企业。

#### S-V2-03 治理台文案与已修订 ADR 相反

| 项 | 内容 |
|---|---|
| 信号强度 | **中**（文案 vs CONTEXT/ADR-0018） |
| 对应 | M-09, S-16 |

Admin：「验证后方可分发」。CONTEXT/ADR-0018：上架独立；无 MCP → unknown 仍可 listed；含 MCP 须验证方可 **enable-host**；Wave 1 无该按钮。

#### S-V2-04 开张后的运营 SLA 尚未指定责任人

| 项 | 内容 |
|---|---|
| 信号强度 | **中**（设计已写，仓库无运营手册） |
| 来源 | 设计评审：三份 `tdd` = 运营 unlist；D7 第三方不同步自动 listed；D11 许可 override 仅超管；D20 不连坐 |

无「谁审、多久、unlist 默认、重名怎么藏」的对外/对内 SLA。旧 OPS-3 仍在，且 D22–D25 让它从 P2 变成 **商店能否诚实开张** 的前提。不要写成用户需求；写成方案若做 Wave 1，必须同时指定运营闸，否则第一周货架不可解释。

#### S-V2-05 旧号段污染

| 项 | 内容 |
|---|---|
| 信号强度 | **强**（元信号，给编排/`pm`） |
| 来源 | 定义 spec 1.5 表 T-01=叙事；塑形 `tickets/T-01.md`=目录豁免；v2 `tickets: []` |

若新方案继续写「按 T-09 做官网诚实」，会拿错票。ops 建议 v2 用主题名或新号，旧号只出现在「对照」列。

### 4.3 已转出的非需求项

| 项 | 类型 | 转给谁 |
|---|---|---|
| 公开能力丢掉 `recommended`（S-13） | 行为不一致 | `/backend`（若当 bug 则离开信号池） |
| Admin 验证按钮未走 `usePermission` | 权限 R5 | `/frontend` + `/backend` |
| `capability-library/README.md` Kimi/zcode「未知」 | 文档漂移 | 文档维护 |
| Hero 示意 3.2 亿 | 品牌/合规 | `/pm` 约束，不是功能 |
| AGPLv3 商用边界 | 法律约束 | `/pm` + 法务（Q-AGPL） |
| `NEWAPI.*.ENABLED=false` | 发布开关 | `/sre` |
| Worker 未启任务 pending | 运维 FAQ | `/sre`（README 已有） |
| 数据中心导出顶 100 条 | 保护或缺陷 | `/backend` 核实 |
| 用量页 `429 QUOTA_EXCEEDED` | 与旧 FR-12 冲突 | `/pm` 若重写文案契约 |
| `datetime.utcnow()` 月度用量 | 口径 | `/analyst` + `/backend` |
| `TenantExpiryService` 未挂 lifespan | 到期执法空洞 | `/backend` / `/sre` |
| `deploy/litellm` 明文 Key（sre 诊断） | 密钥事故 | `/sre`（ops 不展开） |
| 评估集 = 0 | 效果不可报 | `/algo`；ops 只禁对外效果承诺 |
| `check_llm_tokens_month` 未进 `llm_chat` | 套餐数字不挡模型 | `/backend`；定价诚实问题给 `/pm` |
| `/newapi/*` 仍 `require_admin` | 租户 admin=超管能力 | Wave 0 类收权；非增长需求 |

故障不走信号池。

---

## 5. 竞品拆解（仍成立；本轮只补 D22–D29 增量）

> 每个功能三层之一：借鉴 / 回避 / 差异化。「它有我们没有」不是分析。  
> **未亲自付费试用。** 官方文档高；评测中；销售材料低。  
> 旧 spec「未采纳的解法」已吸收 F-01 / F-02 / F-05 / F-06 / F-R1。本表给信号，**不排序**。

分层不变：

| 层 | 对象 | 重叠依据 |
|---|---|---|
| 直接（采集） | Apify、Octoparse 类 | 官网主叙事仍是采集平台 |
| 直接（中转） | new-api 本体 | 我们是外挂，不是替代 |
| 直接（能力分发，未来） | Claude / Kimi / Grok **官方市场** | 设计要把它们当 **源**，不是当宿主 UI |
| 间接 | Firecrawl、Bright Data、Zyte | 评测（中） |
| 基准 | 各宿主 Discover / Official / `/marketplace` | 官方文档（高） |

旧结论 **全部仍真**（不重写操作细节）：

| 编号 | 主题 | 结论 | 对应 |
|---|---|---|---|
| F-01 | 宿主内一键安装 | **回避**当主路径；**借鉴** listed ≠ installed ≠ trusted | S-15, M-09 |
| F-02 | 官方/社区分层 | **借鉴**分层语义；**回避**冒充官方认证 | S-14, S-17 |
| F-03 | 跨宿主重名 | **差异化**（索引+别名）；回避静默改名 | S-14, M-10 |
| F-04 | Kimi 专有/金融包 | **回避**可运行上架；**借鉴** host_compat+许可闸 | S-14, M-11 |
| F-05 | SHA/免责/验证 | **借鉴**信任展示；**回避**法律担保 | S-16, M-09 |
| F-06 | 开发者门户分成 | **回避**一期 | 设计 Non-Goals |
| F-C1 | Actor 模板店 | **借鉴**激活钩子；**回避**覆盖竞赛 | S-04, S-05 |
| F-C2 | 自助计费 | **借鉴**计量诚实（免费档已对齐）；**回避**未履约先标价 | S-07 |
| F-C3 | AI 抽页 vs 采集运营 | **差异化**未讲清 | S-01, S-05, M-13 |
| F-C4 | 代理网 | **回避**当卖点，直到有能力数字 | S-03 |
| F-R1 | 探针外挂 | **差异化**；回避再做令牌收银台 | S-09, S-10, S-11 |
| F-R2 | 渠道组卖点 | **回避**对外承诺直到有映射 | S-07 |

### 本轮增量

#### F-M1 五类平级 vs 宿主「插件礼包」——结论：**差异化（必须写进文案）；回避学「订插件得全家桶」**

| 项 | 内容 |
|---|---|
| 他们怎么做的 | 宿主市场的安装单位通常是 **插件包**；bundled skills 随包而至（Claude `/plugin install`、Kimi 点安装）。 |
| 我们的场景 | D24：订/卸只作用于这一行。插件是磁盘合集，不是订阅礼包。命令/智能体可独立 listed。 |
| 为什么我们能、他们不能 | 我们做跨宿主 **目录**；他们做本宿主 **runtime 包**。礼包模型在跨宿主索引上会把未上架父插件「带」出来（评审已禁）。 |
| **借鉴什么** | 「安装是独立动作」；coming_soon 可见不可装。 |
| **不借鉴什么** | 「安装此插件将获得全部技能」；把网页做成第四个宿主市场。 |
| 复审条件 | 若出现站内执行引擎（CONTEXT：二期），再评估站内 enable。 |
| 来源 | 设计 D22–D25 + 评审冻结（高）；官方宿主文档（高）；未试用（不写「我们用过」） |

#### F-M2 「下架」语义——结论：**差异化；回避用应用商店「下架=卸载」语言**

他们的 unlist/remove 常等于用户侧不可用。我们 D23：unlist 只关商店与新订。客服话术必须新写，不能抄应用商店。对应 M-08。

### 我们已有、竞品不一定有的

| 我们有他们没有的 | 说明 | 强化与否（观察，非优先级） |
|---|---|---|
| 渠道真伪探针 + 额度熔断外挂 | 相对 new-api 本体、相对采集 SaaS | 官网没讲；默认关——交 Q-RELAY |
| AI 规划→试采→注册 flow_generic | 相对纯 Actor / 纯点选 | 官网有模拟 UI，无试用闭环；**无评估集，不可承诺准确率** |
| 技能四维人工评分 + 候选人工闸 | 相对 Grok「index + SHA、不审查内容」 | 公开面几乎不展示 |
| 多租户配额三件套 + 成员 + 用量 | 相对「只有后台的爬虫项目」 | 定价已写；LLM 月度闸未挂生产调用 |
| 跨宿主适配器方向（设计） | 各宿主只顾自己 | 实现未进分支 |
| glossary 已吸收五类 + 展示≠停用 | 竞品少把「停止说谎」写进内部词表 | **访客看不到**；页面仍是采集剧场 |

### 他们的问题（公开渠道）

| 问题 | 来源 | 我们的机会（观察） |
|---|---|---|
| 第三方插件安全免责 | Claude/Grok README（高） | 已有 MCP verify 与评分；公开面没当信任商品；也 **不要** 反过来做法律担保 |
| 采集 SaaS 评测互打 Actor 数量 | 评测（中） | 不要用「最大市场」语言 |
| Octoparse 类：点选难搞 JS（评测转述） | 评测（中） | 我们本就 API/Scrapy 向；官网却在学无代码语言 |
| Kimi 大量 UNLICENSED | 设计抽样 n=16（高，样本小） | 许可闸是差异化 |

决策权在 `/pm`。上表不是 backlog。

---

## 6. 四柱一页纸（仍不排序）

| 柱 | 对外是否存在 | 仓库是否可演示 | 蓝图能否判定 | 本轮相对旧稿的变化 |
|---|---|---|---|---|
| 智能采集 | 官网主叙事 | 是（任务/AI/结果/CSV） | WACT 事件缺 | 承诺/履约 **未变**；AI 效果不可报（M-13）是旧稿低估项 |
| SaaS | 定价+注册 | 部分（配额/成员/用量/注册） | 注册/登录事件缺；CTA 三档并成注册 | **未变**；到期服务未挂、LLM 月度闸未进 `llm_chat` |
| 中转站 | 官网无 | 默认关；后台 `require_admin` | 渠道 24h 禁止当 OEC | **未变**；Q-AGPL 已在必答表但仍开 |
| Power Market | 两个「广场」 | P6 目录，非市场 | 订阅对象与事件均为 0 | **词汇已五类，页面仍四类**——这是本轮最大新裂缝 |

---

## 7. 缺失证据（不要把下面当成已验证需求）

1. 任意生产 UV / 注册数 / 付费转化 / 流失原因  
2. 租户工单、访谈、NPS  
3. 导出、安装、升级、探针查看的行为埋点（事件名写过，查询面未建）  
4. 亲自试用 Apify / Octoparse / Claude Discover / Kimi Plugin Center / Grok `/marketplace` 的操作记录  
5. 技能广场 vs 能力广场点击占比  
6. `recommended` 资产实际条数  
7. 超限 429 是否真实发生过  
8. new-api 是否已有外部租户在用（默认关暗示可能没有）  
9. 开张后谁负责 unlist 重名 / 许可 override（M-10/M-11 责任人）  
10. 评估集版本与试采/评分金标（M-13）

没有这些，**不能**写「用户都要 Power Market」或「采集 SaaS 必须做 Actor 店」。只能写：对外承诺、内部设计、旧蓝图、竞品主路径之间的空洞。

---

## 8. open_questions

ops **不答**。1–7 与旧 spec §9.1 同语义（仍全部待确认，v2 `/pm` 须重列或关闭）。8–10 是本轮收集手段 / 运营闸，仍交 `/pm`。

1. **Q-VOICE** 对外第一句话是采集、四柱平台，还是给 Agent 用的能力市场？未关前不得新写并列四柱 Hero；北极星核心动作是否改「订阅成功」绑在这里。  
2. **Q-PRICE** 定价空头（工单支持 / 渠道组 / 私有技能库 / ¥299）先撤文案还是先履约？  
3. **Q-RELAY** 中转站是独立 SKU、采集附加、还是仅内部成本控制？官网零入口是否有意？  
4. **Q-MARKET-USER** 获客主用户是超管、租户，还是各宿主 Agent 使用者？一期无门户无分成时获客如何发生？  
5. **Q-BILL** 付费是 v1 在线账单还是只联系销售？专业档按钮出口绑在这里。  
6. **Q-LLM** 长期 LLM 数据面是 LiteLLM 还是 new-api（或继续旁路）？中转若变规划依赖，S-09/S-10 对外解释必须重写。  
7. **Q-AGPL** 中转若对外收费，AGPLv3 故事与投诉通道怎么写？投诉通道对应定价「工单支持」——做还是删？  
8. 是否允许 ops 下轮 **主动**收集（注册成功一题、后台「你希望我们做什么」）？样本可能仍为 0。  
9. Wave 1 若做商店：unlist 重名、许可 override、`dev-team` 子卡的 **运营值班人与 SLA** 是谁？（M-10/S-V2-04）ops 不代指定人名。  
10. 旧蓝图事件名是否在 v2 **原样冻结**，还是 `/pm` 重写？ops 只要求：成功定义保持「能判定」；不要用任务表冒充验收。

---

## 9. 自检

- [x] 每条信号有出处；无工单号则写「无用户原声」
- [x] 关键原文未改写
- [x] 影响面未编数字
- [x] 行为数据交叉：全部未获取
- [x] 弱信号如实标注
- [x] 用户解法 vs 观察分开；未下因果
- [x] 故障/权限/文档漂移/密钥已转出
- [x] 渠道偏差已声明
- [x] 与上期对比：无使用量，未假装归一化；页面履约未变；变化来自 glossary/D22–D29/程序 superseded
- [x] 竞品每项借鉴/回避/差异化；回避有复审条件
- [x] 未替 `/pm` 做 RICE / 功能设计 / 表结构
- [x] P9：无法对照实际值；只对照预测 vs 零落点
- [x] 增长：时间窗与口径来自旧蓝图；实际值未获取
- [x] 明确哪些旧结论过期、哪些必须吸收
- [x] 未把旧 spec/contract 写成现行合同
