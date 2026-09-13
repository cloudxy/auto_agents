# Compete · 四柱深度调整（中转站 / Power Market / RBAC / 智能采集）

> 作者：competitor 帽｜日期：2026-09-12｜泳道：L3｜下游：discover briefing
> 长文模板（仅当快照不够）：`skills/signals/templates/competitor-analysis.md`
> 本变更 = 现网四柱半成品的深度调整，不是从零开店。不代选 Q-RELAY / Q-AGPL / Q-PRICE / Q-BILL / Q-MARKET-USER。不写 FR、不排 RICE。

## 集合

| 类 | 名字 | 来源等级 |
|---|---|---|
| 直接 | LiteLLM Proxy：虚拟 Key / Team / Budget / Admin UI | 官方文档 E2（[Virtual Keys](https://docs.litellm.ai/docs/proxy/virtual_keys)、[Team Budgets](https://docs.litellm.ai/docs/proxy/team_budgets)）；本仓 `deploy/litellm/README.md` E2 |
| 直接 | New API（One API 分支）：渠道组 + 令牌 + 计费充值中转站 | GitHub README / LICENSE 说明 E2（[QuantumNous/new-api](https://github.com/QuantumNous/new-api)）；Group 管理官方文档 E2（[Group Management](https://docs.newapi.pro/en/docs/guide/feature-guide/admin/group)）。第三方「One API vs New API」对比文 **E0，不作结论** |
| 直接 | Dify Marketplace / Coze Plugin Store / FastGPT plugin pack | Dify 官方发布文档 E2（[Publish Plugins](https://docs.dify.ai/en/develop-plugin/publishing/marketplace-listing/release-overview)）；Coze 官方「Publish plugins to plugin store」E2；FastGPT plugin 仓库 README E2（[labring/fastgpt-plugin](https://github.com/labring/fastgpt-plugin)） |
| 直接 | Crawlab（分布式爬虫管理台）/ Apify Actors + Store | Crawlab GitHub README E2（[crawlab-team/crawlab](https://github.com/crawlab-team/crawlab)）；Apify 官方 Actor tasks E2（[Actor tasks](https://docs.apify.com/actors/running/tasks)） |
| 直接 | Casbin RBAC / Ory Keto（ReBAC / Zanzibar） | Casbin 官方 RBAC 文档 E2；Ory Keto 官方文档 E2（[Introduction](https://www.ory.com/docs/keto)、[RBAC guide](https://www.ory.com/docs/keto/guides/rbac)） |
| 间接 | Claude Code plugin marketplace（宿主目录：加市场 ≠ 装插件 ≠ 运行） | 官方文档 E2（[Discover plugins](https://code.claude.com/docs/en/discover-plugins)） |
| 间接 | ScrapydWeb / Gerapy（Scrapy 专用管理台） | 仅经 Crawlab README 对比表转述，**不单独作结论** |
| 替代行为 | 值班另开一台 OneAPI/NewAPI；插件靠 per-name symlink；权限靠角色勾选；采集靠手配 Scrapy/generic 任务 | 本仓现网 E2（见现状行） |
| 标杆 | Claude Code：catalog 注册与 plugin 安装分两步；LiteLLM：Key 继承 Team 限额（操作者面，不是租户店） | 官方文档 E2 |
| **现状** | 现网 auto_agents 四柱半成品：LiteLLM 独立数据面 + `/newapi` 值班页 + 租户 `/relay` 渠道组令牌已落代码但本发现带 Q-RELAY 仍开 + 治理台七叶 UI 而 `POWER_MARKET.ENABLED=false` 扫描仍走本机 plugins/ + RBAC 勾选矩阵 + Spiders 手配任务/模板/调度 | 读码 E2：`RelayGroups.tsx`、`NewApiOps.tsx`、`Capabilities.tsx`、`RbacManagement.tsx`、`Spiders.tsx`、`config/default/power_market.yml`、`plugin_service.scan_plugins`、v2 spec **X-SLICE**、ADR-0011/0017/0019、power-market-design Non-Goals |

## 本变更一行

四柱各一行。禁止读成「他们有所以我们要做」。

| 能力 | 他们 | 现状 | 我们若做 | 台面资格 / 差异化 / 浪费 |
|---|---|---|---|---|
| **中转站** | LiteLLM：Postgres 上的虚拟 Key，按 key/user/team 记 spend、models、RPM/TPM；Admin UI + `/key/generate` 是**网关操作者**产品。New API：用户/令牌/渠道三维 Group，token group=`auto` 可跨组failover；核心买卖是 **sk- 分发 + 额度/充值**（Stripe/EPay 在 README 功能表里）；协议 **AGPLv3 + §7 署名条款** | 数据面已切 LiteLLM（`deploy/newapi` 墓碑）。值班是 `NewApiOps` 三问驾驶舱（总览/探针/事件），不是 New API 管理面。租户菜单已有「渠道组」+ `RelayService` 经 HTTP 登记网关 Key（ADR-0019）。**v2 X-SLICE：Wave 0/L/1 不把租户中转写成可卖 SKU**；本带 Q-RELAY / Q-AGPL 仍开 | 加深值班可判定性（探针/窗口/空态）。令牌页保持「本企业用法」而不是对外店。不把 LiteLLM `/ui` 做成租户菜单 | **台面**：平台路径 chat 走网关、值班能答「渠道是否活」。**差异化**：值班规则在本站 backend，不在网关 Admin UI；租户 BYOK 仍直连。**浪费**：复制 New API 充值/兑换码/Discord 登录/MJ-Suno；把 Admin UI 租户化；在 Q-RELAY 未关时把渠道组写成「当前可买中转」 |
| **Power Market** | Dify：Marketplace（审+一键装）/ GitHub URL / 本地 `.difypkg` 三通道，插件在 **Dify 运行时**里执行。Coze：团队内可见 → 提交到社区 Plugin Store。FastGPT：热插拔 tool pack，偏宿主扩展不是商店。Claude Code：先 add marketplace，再 install **整包**插件（skills/agents/hooks/MCP 随包进来） | 七叶治理台 + 官网 `/capabilities` 已有壳。`POWER_MARKET.ENABLED=false`（默认），`scan_plugins` **永远** `LIBRARY_ROOT/plugins` iterdir（D16）。内容接入仍靠 `.agents/plugins` 指针农场，不是源注册表生产路径。Non-Goals：开发者门户 / 分成 / 代写 `~/.zcode/cli/config.json`。无 enable-host 按钮 | 把「索引外部树 + 上架闸 + 按行订阅」做成可演示，而不是再开一家插件商店。订阅不平级礼包（D24）已是设计锁 | **台面**：源能同步、listed 出现在公开面、租户能订一行。**差异化**：五类平级 + 订插件不带子卡 + listing≠停用 + 不执行专家团。他们做不到：跨 zcode/kimi/git 适配器归一到同一目录且不 vendor 进 git。**浪费**：Dify 开发者投稿漏斗、Coze 社区增长环、Claude「整包安装即运行」、分成/门户 |
| **RBAC** | Casbin：`g, alice, role` + matcher，角色层级默认可传递 10 层，不区分 user/role 字符串。Ory Keto：关系元组 + OPL（TS 子集），为「亿级关系、亚 10ms check」的 Zanzibar 场景；RBAC 只是一种建模 | `RbacManagement` = 每角色一张勾选卡（`menu:*` / `btn:*`），保存即 DB。无 Casbin/Ory 依赖。ADR-0017 已冻：平台写面 `is_platform_admin`；租户 admin ≠ 超管；直打值班页与「页面不存在」同形。Wave 0 明确不做完整 `require_permission` 矩阵引擎 | 把「谁能看见哪一柱、谁能签发/上架/扫描」收成可演示的壳差，而不是换一套策略引擎 | **台面**：公司管理员改不了平台渠道/上架；经办签发渠道组被可见拒绝。**差异化**：404 同形是产品壳，Casbin 不提供。**浪费**：本波引入 OPL/关系元组/独立权限服务——现网是三角色 + 数十个权限码，不是文档树继承 |
| **智能采集** | Crawlab：任意语言/框架的**爬虫工程**上传、Master/Worker、SeaweedFS 同步、在线文件、任务日志/结果/Cron；用户是爬虫作者。Apify：Actor（可运行微应用）+ **预配置 Task** + Store 发现/变现；用户买的是别人写好的 Actor 运行次数 | `Spiders.tsx` 已对齐 Crawlab **交互粒**（任务轮询、日志抽屉、结果导出、Cron、模板），但执行面是登记表驱动的 `generic` / `flow_generic` + AI 规划试采，不是上传 Scrapy 工程。Worker 不写主库（Redis 队列）。候选与成果曾同表，出数环已进 v2 Wave 0 | 让「非爬虫作者」贴 URL → 本企业结果里看到条数。调度/模板/AI 规划是加深现网，不是新开爬虫云 | **台面**：一次合格出数（非市场候选）+ 工人空态可见。**差异化**：选择器/流程无代码 + 租户配额 + 结果企业维；Crawlab/Apify 不带本站 SaaS 四柱。**浪费**：任意语言工程托管、Actor 商店与按次计费、站点模板竞赛 |

## 结论

**总判：四柱都是「加深现网可判定动作」，不是四家竞品功能并集。** 现状必须进集合：它已经是半成品，竞品清单会诱使重开巨票。

### 场景差（他们的用户 / 量级 / 频次 vs 我们）

| 柱 | 他们 | 我们 | 差 |
|---|---|---|---|
| 中转 | 站长给下游发 sk-、按量售卖或给内部 Team 发 Key，日频 | ToB 租户经办主路径是采集；平台超管主路径是值班。租户数与令牌数是十到百，不是中转站的万级 token | 同一套「渠道组+令牌」在 New API 是**整店**，在我们最多是**侧门**。LiteLLM 文档里的 Team/Key 是网关操作者面，场景接近值班，不是租户 SKU |
| 市场 | Dify/Coze 作者面向云上全体用户投稿；Claude 用户在 IDE 里装整包 | 平台索引本机/git/kimi 树（一期约三百行资产）；租户按卡片订阅，**不在站内跑智能体** | 他们的「安装」= 运行时可用。我们的「订阅」= 目录行 + 安装记录，Wave 1 明确不等于宿主已运行 |
| 权限 | Keto/Casbin 服务对象级 check（文件/文档/组织图） | 菜单可见性 + 按钮 + 平台/租户两壳 | 对象级 ReBAC 的量级我们没有；壳差他们没有 |
| 采集 | Crawlab 作者改代码；Apify 用户跑别人的 Actor | 经办填 URL/选择器，不会 `scrapy crawl` | 「管理任意爬虫工程」是他们的主场景，是我们的范围外 |

### 借鉴到功能点 / 明确不借鉴什么

**借鉴（功能点粒，不是品类）：**

1. **LiteLLM `/key/generate` + models/RPM/TPM 映射、明文只出现一次、吊销走网关 HTTP** — 已是 ADR-0019 的操作者管道，不是「学 New API 开店」。
2. **New API Group 的「用户组 / 令牌组 / 渠道组」隔离直觉** — 只借鉴「令牌看不到平台渠道明文、组约束模型名单」；不借鉴 group=`auto` 跨组售卖 failover 当租户产品。
3. **Dify 三通道（审过的目录 / git URL / 本地包）** — 对应我们的 source `local_dir` / `git` / 本机文件，**不是** `.difypkg` 作为分发单位。
4. **Claude Code：先注册 catalog，再逐个 install** — 对应「源同步 ≠ 上架 ≠ 订阅」。不借鉴「install 插件即带上 skills/agents/hooks」。
5. **Crawlab：任务列表状态轮询、日志抽屉、结果表、Cron** — 现网已借；继续借「工人离线要在提交前可见」，不借在线编辑器。
6. **Casbin/Ory 的「权限码是一等公民」** — 现网 `PERMISSION_CATALOG` 已是；借「平台写面与租户写面不要共用 `require_admin`」（ADR-0017 已冻）。

**明确不借鉴：**

- New API / One API 的充值、兑换码、Stripe/易支付、公开转售、Discord/LinuxDO 登录、MJ/Suno 接口。
- LiteLLM Admin UI 租户化、租户持 master、租户改全局熔断。
- Dify/Coze 开发者门户、审核投稿漏斗、一键礼包、分成。
- 代写宿主 `config.json` / 把 `.grok/plugins` 当目录真相（D21；ADR-0011 Runtime ≠ Catalog）。
- Crawlab 任意语言工程 + SeaweedFS；Apify Store 变现与 SEO 落地页。
- Ory 关系元组服务、Casbin `model.conf` 本波替换勾选矩阵。

### 回避：替代方案 + 复审条件

| 回避 | 替代（现网已能走） | 复审条件（不要变成永久教条） |
|---|---|---|
| 把中转做成对外可买 SKU / 三入口一账单 | 平台路径走 LiteLLM；租户 BYOK 直连；值班页只给超管。令牌页若保留，文案是「本企业用法」不是「买中转」 | **Q-RELAY 关闭为「对外可卖」且 Q-AGPL / Q-PRICE 同步关**。未关前，竞品有令牌店 ≠ 本带要卖 |
| 开发者门户 / 分成 / 第三方投稿 | 源注册表 + 超管上架闸；git 适配器给 CI | Q-MARKET-USER = 外部作者投稿，或公开第三方作者 >0 |
| enable-host / 代写本机配置 | snippet / 安装说明；订阅只写 `capability_installs` | 操作者明确要本机投影，且 HOST_PROJECTION.ENABLED 仅操作者机 |
| Casbin / Ory 本波 | 角色勾选 + `is_platform_admin` 壳差 + 按钮码 | 权限码持续膨胀到勾选不可运维，或出现租户×资产×宿主的关系型 check |
| Apify Actor 店 / Crawlab 工程托管 | generic/flow_generic + AI 规划 + 模板 | 内部出现「爬虫作者团队」且需要上传工程，而不是经办贴 URL |
| 把 new-api 请回运行时 | `LLM.DATA_PLANE=litellm`；墓碑目录只作回滚文物 | 无。双通道长期并存已否决 |

### 差异化：为什么我们能他们不能

1. **四柱同租户壳。** LiteLLM/New API 没有采集出数与能力目录；Crawlab/Apify 没有平台 LLM 值班；Dify/Coze 没有本站 Scrapy 出数环。拼一个「他们有的功能」会拆掉我们唯一能同时做的事：同一企业里贴 URL 出数、订一张技能卡、看本企业用量。
2. **上架 / 治理 / 订阅 / 宿主启用四闸分列。** Dify 的 Marketplace 一键装把审、发、跑绑在一起；Claude 的 install 把磁盘合集当运行时礼包。我们能拆，是因为资产 `tenant_id` 恒 NULL、安装行才有租户，且一期**不**在站内执行智能体。
3. **爬虫不写主库。** Crawlab Worker 直写 Mongo；我们 StorePipeline → Redis → backend 回流，才能做租户结果隔离与候选不计配额。他们改成这样会否定自己的架构。
4. **值班规则在业务库。** 额度窗口 / 真伪探针是本站产品，不是网关插件。LiteLLM 能做 cooldown，但不能用我们的租户配额词表与「用户可见禁内部码」。
5. **404 同形。** 中转站产品必须让用户看见渠道列表；我们的平台写叶必须让租户看起来像页面不存在。这是 SaaS 隔离，不是网关 ACL。

## 我们已有、他们没有

| 项 | 是否强化 |
|---|---|
| 采集出数环（登记表爬虫 + Redis 队列 + 企业维结果 + CSV/JSON 导出） | **是** — 这是现状里唯一能演示的主路径；竞品采集柱会把它冲成「工程托管」 |
| AI 采集规划（URL → 选择器方案 → 试采 → 注册 flow_generic） | **是** — Crawlab/Apify 没有这条「非作者」路径 |
| 平台 vs 租户两壳（`is_platform_admin`、值班 404 同形、`/llm` 本企业可写） | **是** — 不要用 Casbin 项目替换壳差 |
| listing_state / status / installs / enable-host 分列（设计已锁，旗关时扫描回退） | **是** — 打开 `POWER_MARKET.ENABLED` 时守住四闸，而不是学 Dify 一键装 |
| 五类平级 + 订插件不级联 + unlist≠停用 | **是** — 相对 Claude/Dify 的礼包模型，这是故意的窄 |
| LiteLLM 独立故障域（不进根 compose、backend 不持网关 DSN） | **是** — 不要为了「更像 New API」把网关并进主站 |
| 值班三问驾驶舱（总览/探针/事件） | **是** — 竞品 Admin UI 是配置面；这是我们的操作者产品 |
| `POWER_MARKET.ENABLED=false` 默认 | **保持** — 诚实开关，不是功能缺失；打开前不要对外装成已切源 |

## 观察到的他们的问题（已验证的错误解法）

| 问题 | 来源 | 我们的机会 |
|---|---|---|
| New API 以令牌店为中心，AGPL + 公开转售义务写进 README 警告 | GitHub README E2 | 我们若学「当前可买中转」会把 Q-AGPL 变成产品债；机会是**不当发卡网** |
| Dify Marketplace 一键装 = 审发跑绑死；GitHub/本地通道无审 | 官方对比表 E2 | 我们用 listing 闸把「索引到了」和「商店可见」切开 |
| Claude install 整包带 skills/agents/hooks | 官方 Discover 文档 E2 | 磁盘合集 ≠ 订阅礼包；详情禁止「安装此插件将获得全部技能」 |
| Crawlab 把自己定义成「不限语言的爬虫工程平台」 | GitHub README E2 | 我们的用户不是爬虫作者；继续无代码，而不是补在线 IDE |
| Ory/Casbin 把权限做成独立服务与建模语言 | 官方文档 E2 | 在三角色阶段引入会把勾选矩阵变成第二套真相 |

## 本带开问（竞品视角，不代选）

- **Q-RELAY**：竞品（New API）把渠道组令牌当整店；LiteLLM 把 Key 当操作者面。现状代码已有租户 `/relay`。本快照**不**把「他们有令牌页」写成要卖 SKU。关闭方式仍归操作者。
- **Q-AGPL**：New API README 明示 AGPLv3 + 对公生成式服务的备案/授权义务；LiteLLM 企业功能在官方文档里打企业标。对外收费中转前必须关，不是本帽能关。
- **Q-MARKET-USER**：Dify/Coze 的主用户是插件作者；我们设计主用户是平台治理 + 租户订阅。若操作者改成作者投稿，回避表要重开。

## 自检

- [x] 集合含 **现状**
- [x] 一行一柱，不是全产品矩阵
- [x] 结论是借鉴 / 回避 / 差异化，并写场景差
- [x] 每条主张有来源等级；销售页 E0 未作结论依据
- [x] 无「他们有所以我们要做」
- [x] 无 RICE、无 FR
- [x] 列了我们已有、他们没有
- [x] 回避带替代方案与复审条件
