# Compete · 合入后下一波（post-merge-upgrade）

> 作者：competitor 帽｜日期：2026-09-13｜泳道：L3｜下游：discover briefing
> 长文模板（仅当快照不够）：`skills/signals/templates/competitor-analysis.md`
> 本变更 = **合入后半成品的双轨 vs 下一波可判定动作**，不是四柱功能并集、不是从零开店。
> 关账特征 `feat-four-pillars-v2` / `feat-product-complete` / `upgrade-four-pillars` 按 **有条件放行、非 GA** 读。不代关 Q-*。不写 FR、不排 RICE。

## 集合

| 类 | 名字 | 来源等级 |
|---|---|---|
| 直接 | LiteLLM Proxy：Virtual Key / Team / Budget / Admin UI（**网关操作者**产品，不是租户店） | 官方文档 E2（2026-09-13 HEAD 200：[Virtual Keys](https://docs.litellm.ai/docs/proxy/virtual_keys)、[Team Budgets](https://docs.litellm.ai/docs/proxy/team_budgets)）；本仓 `deploy/litellm/README.md` E2 |
| 直接 | New API（One API 分支；**本仓已退役运行时**）：sk- 分发 + 额度/充值中转站；协议 AGPLv3 | GitHub README E2（2026-09-13 HEAD 200：[QuantumNous/new-api](https://github.com/QuantumNous/new-api)）；本仓 `deploy/newapi/README.md` §七 E2、`TOMBSTONE.md` E2。第三方「One API vs New API」对比文 **E0，不作结论** |
| 间接 | Dify Marketplace / Coze Plugin Store（目录 + 一键装/投稿） | Dify 官方发布文档 E2（2026-09-13 HEAD 200：[Marketplace listing](https://docs.dify.ai/en/develop-plugin/publishing/marketplace-listing/release-overview)） |
| 间接 | Crawlab（爬虫工程管理台）/ Apify Actors + Store（买别人写好的运行次数） | Crawlab GitHub README E2（HEAD 200）；Apify Actor tasks E2（HEAD 200：[Actor tasks](https://docs.apify.com/actors/running/tasks)） |
| 替代行为 | Excel / 自建 Scrapy / 供应商控制台 BYOK / 另开一台 NewAPI / **不用本仓** / 继续只点用量页「套餐与订购」 | 本仓现网 E2（见现状行）；upgrade-four-pillars `market.md` 替代表 E2 |
| 标杆 | Claude Code：catalog 注册 ≠ plugin 安装；LiteLLM：Key 继承 Team 限额（操作者面） | 官方文档 E2（沿用上带；本带不重写商店矩阵） |
| 标杆 | Casbin RBAC / Ory Keto（ReBAC / Zanzibar） | **仅当本波宣称策略引擎量级才对标**。本变更不宣称 → 集合内回避。不引销售页 |
| **现状** | **合入后的本仓半成品本身**（`feat/litellm-l1` @ `1db6a47` 2026-09-13 已并 `origin/main`）：示意完整、双轨并存、环境闸未跑、Q-AGPL 未关故无「当前可买」 | 读码 + 关账意见 E2（下表） |

**现状核验（合入树，不是销售页）：**

| 双轨 / 裂缝 | 合入后仍在 | 出处（E2） |
|---|---|---|
| 计费 | 用量页仍挂 L1 `BillingPanel`（`POST /billing/orders` → `pending`，超管 `confirm_paid`；收音机含支付宝/微信，后端对在线渠道抛「在线支付尚未开通」并强制 `channel=offline`）。主线 `Checkout`（`POST /billing/checkout` → `checkout_pending`，履约认通道通知，ADR-0024）。同一 `billing.ts` 两套入口 | `Usage.tsx` 挂 `BillingPanel`；`Checkout.tsx`；`billing_service.create_order` / `preview_checkout` / `confirm_paid` |
| 拉数钥匙 | 出站查找三环并存：`outbound_keys` → `api_keys` → `KEY_BINDINGS`。出站有租户叶 `/outbound-keys`；`/api-keys` 有 API **无菜单叶** | `external_api/v1/public.py` `_require_bound_tenant`；`menuConfig.tsx`；`api_keys.py` vs `outbound_keys.py` |
| 中转令牌 | 平台 `GET/POST /api/v1/litellm/keys`（`LITELLM.ADMIN.ENABLED` 默认关）与租户 `/relay` 签发 `sk-`（ADR-0019）+ SKU 闸（ADR-0025）并存。`CONTEXT.md` 仍写「令牌不发给租户」 | `litellm_admin.py`；`RelayGroups.tsx`；`config/default/litellm.yml`；`CONTEXT.md` 中转站/令牌行 |
| 示意完整 | 菜单含渠道组 / 出站钥匙 / 结账 / 能力市场；官网 Hero「粘贴链接即可出数」、定价「去结账」+ 企业档印「中转站渠道组分配」；机械钉禁「当前可买」仍绿 | `menuConfig.tsx`；`Home.tsx` `HERO_FIRST_SENTENCE`；`Pricing.tsx`；`frU24CopyScan.test.tsx` |
| 环境闸未跑 | product-complete C2 真网关轮 / C3 迁移现场 / C4 worker 冒烟 / C5 P95 **仍是交付条件，不是已跑指纹** | `feat-product-complete/06-deliver/remaining-work.md` §一 |
| 非 GA | 三份关账均为 **有条件放行**；upgrade 明确「不得标四柱 GA / 支付已通」 | v2 / product-complete / upgrade `release-opinion.md` |
| 旗默认关 | `POWER_MARKET.ENABLED=false`；`LITELLM.ENABLED` / `ADMIN.ENABLED` / `PROXY.ROUTE_INTERNAL` 默认 false | `config/default/power_market.yml`；`litellm.yml` |

空集合或缺现状行 = 本快照失败。现状是竞品，不是背景噪音。

## 本变更一行

一行 = **合入后双轨的一个面**，不是四柱矩阵。禁止读成「他们有所以我们要做」。

| 能力 | 他们 | 现状 | 我们若做 | 台面资格 / 差异化 / 浪费 |
|---|---|---|---|---|
| **结账路径** | LiteLLM 把限额放在 Team/Key（操作者预算）。New API 把充值/兑换码/Stripe·EPay 写进**同一家店**（README 功能表，不作「必须抄」）。各家对外是**一条**收款或限额故事 | 租户可见两条：用量页「套餐与订购」+ 定价 CTA「去结账」。状态词两套（`pending/paid` vs `checkout_pending/paid_pending_fulfillment`）。ADR-0024 已冻：在线履约 ≠ `confirm_paid` | 下一波若动结账，竞品只证明「用户撞上一条故事」；不证明要第三条网关 | **台面**：买方能走完下单→到账→档位变，且不把 HMAC 夹具写成 live 收银台。**差异化**：Q-AGPL 未关 + live 通道未跑时，文案仍能诚实（竞品店做不到「可买但禁止写当前可买」）。**浪费**：学 New API 充值码/Stripe/Discord；把双轨当「灵活」长期并存 |
| **拉数钥匙** | Apify 一把 token 拉自己的 run。Crawlab 用登录会话看结果。New API 的 sk- **就是**店——没有「拉数钥匙 vs 中转令牌」分平面 | ADR-0020 已冻出站 ≠ `sk-`（这是差异化，不是双轨债）。双轨债是 **同一 GET 上三环查找** + 两套租户产品名（出站页 vs 无菜单的 `/api-keys`） | 收口查找链是内部合入问题。竞品「一把钥匙」是场景差，不是新种类清单 | **台面**：外部系统用一把本企业钥匙拉到本企业行；`sk-` 当出站 = 拒绝、0 行。**差异化**：分平面他们做不到（否决自己的店）。**浪费**：给同一经办两个「拉数 Key」产品名；把 `api_keys` 做成第二套出站店 |
| **中转令牌** | LiteLLM `/key/generate` = 网关操作者。New API sk- = 整店买卖。Admin UI ≠ 租户菜单（LiteLLM 文档场景） | 操作者面（`/litellm` + 值班 `/newapi`）与租户面（`/relay` + SKU）**代码都在**。词表滞后：CONTEXT / L1 memory 仍像「不发给租户 / 没有支付网关」。真网关轮未跑 | 加深「本企业用法」可判定（签发一次明文、吊销后网关拒）。不把 `/ui` 做成租户菜单 | **台面**：已开通企业能用令牌打独立网关且用量可观察——**环境闸通过之后**。**差异化**：值班规则在本站 backend；租户直打值班页 404 同形；BYOK 仍直连。**浪费**：Q-AGPL 未关写成「当前可买」；L1 admin keys 租户化；把 new-api 请回运行时 |
| **示意完整** | 竞品文档与可买运行时是同一条产品故事（商店即店、工程台即工程台） | 菜单/官网/定价看起来齐；三关账有条件放行；C2–C5 未跑；市场/网关旗默认关；「当前可买」被测试禁止 | 下一波钉词表=代码、环境闸有指纹，而不是再开「实现四支柱」 | **台面**：对外句与代码同句。**差异化**：能诚实关旗（Dify 商店默认就是店）。**浪费**：把示意完整当 GA；Hero 改成支付/中转成功（Q-VOICE 未关，且升级波已把采集锁在首屏——本帽不代选，只标场景：改 Hero 会与已钉句冲突） |

## 场景差（他们的用户 / 量级 / 频次 vs 我们）

| 面 | 他们 | 我们（合入后） | 差 |
|---|---|---|---|
| 结账 | 站长日频给下游充值或给内部 Team 加预算；一单一种商品故事 | ToB 买方偶发升级（专业/企业/中转 SKU）。**0 笔生产支付**（上带 market：本机 `orders=0`，不是买方） | 他们的「第二条通道」是支付服务商；我们的第二条是 **L1 与主线合入残留**。场景不是「再接 Stripe」 |
| 拉数 | Actor/工程作者拉自己的 run；一把凭证 | 经办把本企业结果交给外部系统。量级是租户数×钥匙数（十到百），不是 Apify 的按次商店 | 「三环查找」解决的是合入兼容，不是用户要三种 Key |
| 中转 | New API 用户买的是 sk- 额度；LiteLLM 用户是网关操作者 | 采集经办主路径仍是贴 URL；渠道组是侧门。SKU 权益已在代码（ADR-0025），商用句仍挡 Q-AGPL | 同一套「渠道组+令牌」在 New API 是整店，在我们最多是企业侧门。LiteLLM Admin 场景接近值班，不是租户 SKU |
| 完整度 | 开源项目以「能卖/能自托管」为完成定义 | 本仓以有条件放行 + 环境闸为完成定义 | 他们没有「示意完整」这种内部病；抄他们的功能表会把半成品写成 GA |

## 结论

**总判：下一波是收双轨 + 保持诚实半成品，不是四家竞品功能并集。** 现状必须进集合：它已经是半成品，竞品清单会诱使重开巨票。上带 compete「加深现网可判定动作」仍成立；本带新增的竞品是 **合入后的双轨自己**。

### 借鉴到功能点 / 明确不借鉴什么

**借鉴（功能点粒，不是品类）：**

1. **「一条对外故事」** — LiteLLM 操作者面一条、New API 店一条。借鉴的是 **用户只撞上一种下单/一种拉数名/一种令牌名**；不借鉴他们用哪家支付、哪种充值。
2. **LiteLLM `/key/generate` + models/RPM/TPM、明文只一次、吊销走网关 HTTP** — 已是 ADR-0019 操作者管道。本带只借「操作者 Key ≠ 租户 SKU」这条边界（`deploy/litellm/README.md` 第三节）。
3. **New API Group 的隔离直觉** — 令牌看不到平台渠道明文、组约束模型名单。不借鉴 group=`auto` 跨组售卖 failover 当租户产品。
4. **Claude Code：先注册 catalog，再逐个 install** — 对应「源同步 ≠ 上架 ≠ 订阅」。不借鉴「install 即带上 skills/agents/hooks」。上带已借；本带不重开市场矩阵。
5. **Crawlab：工人离线要在提交前可见** — 现网已借交互粒。本带不借在线编辑器、任意语言工程托管。

**明确不借鉴：**

- New API / One API 的充值、兑换码、Stripe/易支付、公开转售、Discord/LinuxDO 登录、MJ/Suno。
- LiteLLM Admin UI 租户化、租户持 master、租户改全局熔断。
- Dify/Coze 开发者门户、审核投稿漏斗、一键礼包、分成。
- Crawlab 任意语言工程 + SeaweedFS；Apify Store 变现与 SEO 落地页。
- Ory 关系元组、Casbin `model.conf` 替换勾选矩阵。
- 把「他们有两套 Key API」读成我们要保留三环查找——他们没有这个场景。

### 回避：替代方案 + 复审条件

| 回避 | 替代（现网已能走，不代选哪条赢） | 复审条件（不要变成永久教条） |
|---|---|---|
| 把中转写成定价「当前可买」/ 三入口一账单 | 代码可有 SKU 闸与 `/relay`；对外句继续禁该四字。平台路径走 LiteLLM；BYOK 直连；值班页只给超管 | **Q-AGPL 关闭为可对外收费** 且 live 通道窗已跑。未关前，竞品有令牌店 ≠ 本带可写「当前可买」。ADR-0025 的 SKU 权益 **不**被本行推翻 |
| 双轨当特性（两套结账 UI、两套拉数产品名长期并存） | 现状两条都能点；这是合入残留，不是用户要的「选择权」 | 操作者明确要「线下挂账」与「通道通知」分角色长期并存，并改词表让用户分得清 |
| 把 `api_keys` 与 `outbound_keys` 做成两个租户店 | ADR-0020 分平面（出站 vs `sk-`）保留；查找链三环是债不是产品 | 出现第三种外部系统且不能走出站钥匙时再开新平面 |
| Casbin / Ory 本波 | 角色勾选 + `is_platform_admin` 壳差 + 404 同形 | 权限码膨胀到勾选不可运维，或出现租户×资产×宿主的关系型 check |
| Apify Actor 店 / Crawlab 工程托管 | generic / flow_generic + AI 规划 + 模板 | 内部出现「爬虫作者团队」且需要上传工程，而不是经办贴 URL |
| 把 new-api 请回运行时 | `LLM.DATA_PLANE=litellm`；墓碑目录只作回滚文物 | 无。双通道长期并存已否决 |
| Stripe / 兑换码 / Discord 登录（briefing Fog） | 通道闭集仍是支付宝+微信（上带 Discuss-S；本帽不重开） | 操作者把 Fog 里的 Stripe 从范围外拿回来 |
| 开发者门户 / 分成 / 代写宿主 `config.json` | 源注册表 + 超管上架闸；订阅只写 `capability_installs` | Q-MARKET-USER = 外部作者投稿，或公开第三方作者 >0 |

### 差异化：为什么我们能他们不能

1. **四柱同租户壳。** LiteLLM/New API 没有采集出数与能力目录；Crawlab/Apify 没有平台 LLM 值班；Dify/Coze 没有本站 Scrapy 出数环。拼一个「他们有的功能」会拆掉我们唯一能同时做的事：同一企业里贴 URL 出数、订一张技能卡、看本企业用量。合入后双轨威胁的是这层壳，不是缺某一个竞品按钮。
2. **出站 vs 中转分平面。** New API 做不到：sk- 既是店又是钥匙。我们能，是因为拉数不进网关 Key 列表（ADR-0020 备选 A/D 已否决）。下一波若「统一成一把 sk-」是在抄他们的错误解法。
3. **404 同形 + 值班不在网关 Admin UI。** 中转站产品必须让用户看见渠道列表；我们的平台写叶必须让租户看起来像页面不存在。LiteLLM `/ui` 租户化会否决这条。
4. **能诚实关旗、禁四字。** Dify 商店默认就是店；New API README 以令牌店为中心。我们能在 Q-AGPL 未关、C2 未跑时仍禁止「当前可买」——这是半成品纪律，不是功能缺失。
5. **爬虫不写主库。** Crawlab Worker 直写 Mongo；我们 StorePipeline → Redis → backend 回流，才能做租户结果隔离。他们改成这样会否定自己的架构。本带不重开采集矩阵，只标：双轨收口时不要顺手改成「直写主库更像 Crawlab」。

## 我们已有、他们没有

| 项 | 是否强化 |
|---|---|
| 采集出数环（登记表爬虫 + Redis 队列 + 企业维结果 + CSV/JSON 导出） | **是** — 合入后仍是唯一能演示的主路径；竞品采集柱会把它冲成工程托管 |
| AI 采集规划（URL → 选择器 → 试采 → flow_generic） | **是** — Crawlab/Apify 没有「非作者」路径 |
| 出站拉数钥匙 ≠ 渠道组 `sk-`（互否执法） | **是** — 这是护城河；不要为「一把钥匙更简单」拆掉 |
| 平台 vs 租户两壳（`is_platform_admin`、值班 404 同形） | **是** — 不要用 Casbin 项目替换壳差 |
| 结账占坑 + 通道通知履约（ADR-0024）与线下 `confirm_paid` 已能分词 | **部分** — 代码分了；**租户可见面还没分干净**（BillingPanel 仍在）。强化的是「一条可见故事」，不是再接一家支付 |
| 禁「当前可买」机械钉 + 有条件放行词 | **保持** — 竞品没有这种自我约束；打开前不要对外装成已切源 / 已可买 |
| LiteLLM 独立故障域（不进根 compose、backend 不持网关 DSN） | **是** — 不要为了更像 New API 把网关并进主站 |
| 值班三问驾驶舱（总览/探针/事件） | **是** — 竞品 Admin UI 是配置面；这是我们的操作者产品 |
| `POWER_MARKET.ENABLED=false` / `LITELLM.*.ENABLED=false` 默认 | **保持** — 诚实开关，不是功能缺失 |

## 观察到的他们的问题（已验证的错误解法）

| 问题 | 来源 | 我们的机会 |
|---|---|---|
| New API 以令牌店为中心，AGPL + 对公生成式服务义务写进 README | 本仓 `deploy/newapi/README.md` §七 E2；上游 GitHub E2 | 学「当前可买中转」会把 Q-AGPL 变成产品债；机会是 **不当发卡网** |
| LiteLLM Admin UI / Virtual Keys 文档面向网关操作者，不是 SaaS 租户 | 官方 Virtual Keys E2；本仓 litellm README「不要做成租户菜单」E2 | 值班留在本站；租户面保持「本企业用法」 |
| Dify Marketplace 一键装 = 审发跑绑死 | 官方发布文档 E2 | listing 闸把「索引到了」和「商店可见」切开（上带已锁；本带不重开） |
| Crawlab 把自己定义成不限语言的爬虫工程平台 | GitHub README E2 | 用户不是爬虫作者；继续无代码 |
| Ory/Casbin 把权限做成独立服务与建模语言 | 官方文档 E2（上带；本带不宣称该量级） | 三角色阶段引入会把勾选矩阵变成第二套真相 |

## 本带开问（竞品视角，不代选）

- **Q-AGPL**：New API README 明示 AGPLv3 + 对外商用义务；LiteLLM 企业功能在官方文档打企业标。对外收费中转前必须关。未关 = 竞品有店 ≠ 我们可写「当前可买」。
- **Q-PRICE**：双轨让「怎么收钱」同时像 L1 线下挂账和主线通道通知。竞品各只有一种故事。关问方式仍归操作者；本快照不挑哪条 API 留下。
- **Q-VOICE**：官网首屏已锁采集句（`HERO_FIRST_SENTENCE`）。竞品（Dify/Apify）会把商店或 Actor 当第一句。改 Hero 会与已钉句冲突——是否改仍归操作者。
- **Q-MARKET-USER**：Dify/Coze 主用户是插件作者；我们设计主用户是平台治理 + 租户订阅。若改成作者投稿，回避表要重开。
- **Q-OPS-COLLECT / Q-C-REG**：竞品各有联系/注册默认路径；本仓 mailto 占位与「注册强制建企业」不是从他们抄来的，也不是本帽能关。
- **Q-RELAY**：上带 Discuss-S 已选对外可买 SKU，代码有 ADR-0025。墓碑/部分 README 仍写未关。本快照 **不**重开该问，也 **不**把「他们有令牌页」写成可以对外印「当前可买」。商用句仍绑 Q-AGPL。

## 自检

- [x] 集合含 **现状**（合入后半成品，不是 Excel 空话）
- [x] 一行一面（结账 / 拉数 / 令牌 / 示意完整），不是全产品矩阵
- [x] 结论是借鉴 / 回避 / 差异化，并写场景差
- [x] 每条主张有来源等级；销售页 E0 未作结论依据；官方文档本带 HEAD 200
- [x] 无「他们有所以我们要做」
- [x] 无 RICE、无 FR、无代选 Q-*
- [x] 列了我们已有、他们没有
- [x] 回避带替代方案与复审条件
- [x] 借鉴到功能点，并写明不借鉴什么
- [x] 差异化说清「为什么我们能他们不能」
