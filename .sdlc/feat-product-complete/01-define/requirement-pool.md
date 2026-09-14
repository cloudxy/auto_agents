# 需求信号池 · 2026-09-10 feat-product-complete

> 作者：/ops｜日期：2026-09-10｜下游：`/pm`（需求分诊的输入）｜泳道：L4
> **无出处的信号不进本文件。** 本帽不写 PRD、不做 RICE、不代选 Q-VOICE / Q-PRICE / Q-MARKET-USER / Q-AGPL / Q-OPS-COLLECT。
> 已关闭、禁止再问：Q-LLM / Q-BILL / Q-RELAY / Q-OPS-DUTY。
> 操作者原话是约束，不是用户投票。日历压力（「一次全部执行完毕」）不进信号强度。

## 渠道与偏差声明

| 渠道 | 本期数据量 | 偏差 |
|---|---|---|
| 生产工单 | **0** 条 | 无租户工单模块；不能从「零投诉」推出「没问题」 |
| 应用商店评论 | **0** 条 | 产品未上架应用商店 |
| 客服记录 | **0** 条 | 无客服通道；定价仍写「工单支持」（预告） |
| 访谈 / NPS / 问卷 | **0** 人 | 无付费用户样本 |
| 操作者原话 | 2 条约束 | 站点操作者，不是终端用户投票 |
| **使用数据（本机活体）** | **已获取** 2026-09-10：9111/9112/9113 在听；LiteLLM `127.0.0.1:4000` healthy | 本机预发库，含 NFR 种子；**不是**生产 n |
| 代码 / 测试 / SDLC 账本 | 已对照 | 履约裂缝与测试债；不是「用户都要」 |

**主动反馈的用户通常不到 1%**，本期连这 1% 的通道都没有。影响面除活体列表条数外一律 **未量化**，不编人数。

**约束（给 `/pm`，不是信号强度）：**

> 「将没有执行完的计划，一次全部执行完毕。产品还有很多不好用的地方，我需要深度梳理。」——操作者 2026-09-10，`feat-product-complete/state.yaml` intent.quote

> 「支付先空着，建账务骨架（线下订单；在线通道 PAYMENT_NOT_CONFIGURED）」——Q-BILL 已决，`state.yaml` operator_decisions_inherited

---

## 信号清单

### S-01 满额下一步：出口已离开注册，付费面仍两套真相

| 项 | 内容 |
|---|---|
| **提及次数** | 操作者约束 1 + 活体/代码对照 4 处（非工单） |
| **影响用户数** | **未量化**（工单=0） |
| **行为数据交叉验证** | 活体 `GET /api/v1/billing/plans` **200**，2 档 `free`/`pro` 且 `is_public=1`、`pro.price_cents=29900`（2026-09-10 curl 9111） |
| **实际影响面** | 未量化。结构上：访客看「预告不可购买」，经办在满额时可提交线下订单 |
| 频次 | 未知 |
| 信号强度 | **中**（无用户原声；活体与页面打架，不是臆测） |
| 用户特征 | 访客（定价）；租户经办/公司管理员（用量满额）；平台超管（确认收款） |

**原文样本**（未改写）：

> 「满额 CTA 不得再开一家免费企业。」——`feat-four-pillars-v2/01-define/spec.md` FR-50
> 「该档尚未开通购买。」——`frontend/official/src/pages/Pricing.tsx:170`（专业档/企业档 CTA「预告不可购买」）
> 「本波不提供自助改套餐或支付。请通过联系说明申请提升配额。」——`frontend/admin/src/pages/Usage.tsx:219`
> 「提交升级订单」——同文件 `Usage.tsx:156`（`createOrder(pro.id)` → `/api/v1/billing/orders`）

**用户提的解法 vs 观察到的问题**（分开呈现）：

| 项 | 内容 |
|---|---|
| 用户提的解法 | 无工单。操作者约束：支付先空、建账务骨架 |
| 观察到的问题 | Wave 0 的「不到注册」已落地（GWT-12.6；Usage 申请提升 → mailto，存储满 →「去结果库」）。018c369 另开了公开 `pro` 价目 + 线下挂账 + 超管确认。官网定价仍把专业档标预告。Usage 同一屏既说「本波不提供自助」又提供「提交升级订单」。租户 **没有** 订单列表页（`billing.ts` 有 `listOrders`，菜单无入口；超管在 `PlatformOps` `PendingOrdersTab`） |
| 可能的原因/方向 | ① Q-PRICE 未关，访客面必须继续「未履约不得写成当前可买」 ② 骨架已对经办履约、对访客未履约 ③ 文案未随 018c369 重写 |

**已落地、不要再报成缺口：** 满额主 CTA 不到 `/register`；只读「只读可见进度，不能改套餐」（`Usage.tsx:127-129`）；在线 `alipay`/`wechat` 抛 `PAYMENT_NOT_CONFIGURED`（`payment_provider.py:39-41`；`test_billing_relay.py`）。

**判断交 `/pm` 做三连问**，本帽不代选 Q-PRICE。

---

### S-02 出站拉数钥匙：租户仍不能自助签发

| 项 | 内容 |
|---|---|
| 提及次数 | spec stub 1 + 活体 1 |
| 影响用户数 | 未量化 |
| 行为数据交叉验证 | 活体 `GET /external/v1/public/data/example` **401** `Invalid API Key`（无钥匙，2026-09-10） |
| **实际影响面** | 未量化 |
| 频次 | 未知 |
| 信号强度 | **中**（FR-51 仍是下一轮；现网拒绝已兑 FR-13） |
| 用户特征 | 租户经办想把结果拉到自家系统 |

**原文样本**：

> 「租户自助发钥匙 = FR-51，本波不做。」——`spec.md` FR-51；`02-shape/tickets/T-10.md`
> `EXTERNAL_API.KEY_BINDINGS: []` ——`config/default/external_api.yml:14`
> OpenAPI 无租户签发出站钥匙路径（活体 `/openapi.json` 2026-09-10：`keys` 过滤结果 `[]`；出站仅 `/external/v1/public/data/{spider_name}`）

**用户提的解法 vs 观察到的问题**：

| 项 | 内容 |
|---|---|
| 用户提的解法 | 无工单。旧推断「租户凭证」来自 2026-09-08 ops S-06，不是本期原声 |
| 观察到的问题 | 未绑定拒绝 **已落地**（GWT-13.2/13.4）。租户后台能签发的是 **渠道组令牌**（`/relay/tokens`），不是出站拉数 `KEY_BINDINGS`。两把钥匙产品名都叫「令牌/钥匙」，易混 |
| 可能的原因/方向 | ① FR-51 仍范围内未做 ② 018c369 令牌被理解成出站钥匙 ③ 平台配置钥匙 vs 租户自助 |

**已落地、不要再报成缺口：** 未绑定 / 绑错企业 → 0 行拒绝。

---

### S-03 租户渠道组：SKU 壳已有，令牌不经网关、用量不走

| 项 | 内容 |
|---|---|
| 提及次数 | Q-RELAY 已决 1 + 代码对照 |
| 影响用户数 | 未量化 |
| 行为数据交叉验证 | 活体 `GET /api/v1/relay/groups` 未登录 **401** `AUTH_FAILED`（路由存在）。OpenAPI：`/api/v1/relay/groups` `POST/PATCH`、`/tokens` 签发/吊销 |
| **实际影响面** | 未量化 |
| 频次 | 未知 |
| 信号强度 | **中** |
| 用户特征 | 租户经办/公司管理员；访客仍在定价企业档看到「中转站渠道组分配」预告 |

**原文样本**：

> 「租户渠道组 SKU 参考常见中转站（relay_groups + relay_tokens；租户改不了全局熔断）」——Q-RELAY 已决
> 「租户渠道组：分组 + 虚拟令牌。不改平台渠道、不打网关库。」——`backend/services/relay_service.py:1`
> 「渠道组只作用于本企业的令牌和限额。平台渠道窗口与熔断由值班超管在「中转站管控」维护，这里改不了。」——`RelayGroups.tsx:88`
> `used_tokens` 只在模型/schema/UI 出现，服务层无递增写入（仓库 `used_tokens` 命中：模型、040 迁移、schema、RelayGroups 列、`relay_service` 读出）

**用户提的解法 vs 观察到的问题**：

| 项 | 内容 |
|---|---|
| 用户提的解法 | 无工单。操作者：参考常见中转站做组+令牌 |
| 观察到的问题 | **已有：** 表 `relay_groups`/`relay_tokens`（040）、租户菜单「渠道组」`tenantOnly`、CRUD、默认组、明文只回显一次、超管熔断不在此页。**仍缺：** 令牌不打 LiteLLM 虚拟钥匙；`used_tokens` 恒 0；官网企业档仍「中转站渠道组分配」+预告；CONTEXT 仍写「令牌不发给租户」（见 S-11） |
| 可能的原因/方向 | ① SKU 记账与数据面未焊 ② Q-AGPL 未关，对外收费叙事不能写死 ③ 产品把「能签发字符串」当成「能调模型」 |

**已落地、不要再报成缺口：** 「Q-RELAY 未关前不得出现我的渠道组」（GWT-60.1）——问已关，菜单出现是履约不是回潮。租户改全局熔断：无入口（GWT-60.3 / Wave 0）。

---

### S-04 探针伪装不熔断已兑；值班入口仍叫中转站管控

| 项 | 内容 |
|---|---|
| 提及次数 | spec GWT-07.6 + 代码 1 |
| 影响用户数 | 未量化（值班超管） |
| 行为数据交叉验证 | 未获取活体探针行（`/api/v1/newapi/channels` 未登录 401；未持超管会话打值班页） |
| **实际影响面** | 未量化 |
| 频次 | 未知 |
| 信号强度 | **弱**（不熔断已有测试与实现句；命名/入口是体验，不是新 FR-61 功能洞） |
| 用户特征 | 平台超管值班 |

**原文样本**：

> 「spoofed 不关渠道、不改窗口/额度（GWT-07.6）。」——`backend/services/channel_probe_service.py:280`
> 菜单「中转站管控」→ `/newapi`，`platformOnly` ——`menuConfig.tsx:87`
> CONTEXT：「new-api 为已退役运行时」——`CONTEXT.md:48`

**用户提的解法 vs 观察到的问题**：

| 项 | 内容 |
|---|---|
| 用户提的解法 | 无 |
| 观察到的问题 | FR-61 熔断句与 GWT-07.6 **已兑**。租户无探针阈值入口（GWT-61.3 已真）。值班页仍挂 new-api 路径名；Wave L 后空态走 FR-71，本 stub 不另写第二套空态 |
| 可能的原因/方向 | ① 只差值班可见性/改名 ② 探针结果是否仍有行取决于网关是否在跑 |

**已落地、不要再报成缺口：** 伪装自动下线渠道。

---

### S-05 冻结施工账本仍 open 的 minor：对照现网，勿把已修的再开票

| 项 | 内容 |
|---|---|
| 提及次数 | `feat-four-pillars-v2/state.yaml` review_findings 仍 open 的集合 |
| 影响用户数 | 未量化（主伤 QA 闸与超管治理，不是访客主路径） |
| 行为数据交叉验证 | 代码/测试 2026-09-10 对照（下表） |
| **实际影响面** | 未量化 |
| 信号强度 | **弱～中**（测试债 ≠ 用户投票） |
| 用户特征 | 超管治理台；订阅弹窗离线；公开 404 字节 |

**账本 vs 现网**（出处：`state.yaml` notes；`04-verify/coverage.md:496-506`；`d7a6f78`）：

| id | 账本状态 | 现网 | 是否仍当缺口进池 |
|---|---|---|---|
| IM-02 | open | `test_skill_public_api.py:167` 仍 `ghost.content == STORE_NOT_FOUND_HTML.encode` | 是（测试 oracle 自比；不升产品 FR） |
| IM-03 | open | 技能端 `test_skill_public_api.py:248` 已 `len(d1["items"])==20`；能力端 `test_b1c_capabilities_coverage.py:812-819` **未**钉 len | 是（能力端 33.4） |
| IM-04 | open | `test_t31_license.py:144,203` 已有 `public_license_override=1`（42.4/42.6）；coverage 写「override 改走 42.2」 | **否**（不要把 42.x 夹具再报成 33.2 缺口） |
| IM-05 | open | coverage：「方言债 MYSQL_FIDELITY 已过；本格 ✅」；034 列 `SmallInteger` | **否**（账本未关，现网已过） |
| IM-12 | open | 官网详情有「网络不可用，现在不能订阅。」（`CapabilityDetail.tsx:99-100`）；后台 `SubscribeModal.tsx` **无** `navigator.onLine` | 是 → S-09 |
| IM-13 | open | `CapabilityDetail.test.tsx:152-160` 负向 `not.toContain('from=/capabilities/')` **未** `decodeURIComponent` | 是（测试债） |
| IM-17 | open | `Capabilities.governance.test.tsx:156`「IM-17 open in catalog keeps short name」+ `CatalogTab.tsx` `matchesFocus`；提交 `d7a6f78` | **否（代码已关，账本陈旧）** |
| IM-18 | open | `test_t27_references.py:40` GWT-36.1；coverage ⚠️「礼包合集边未挂对照」 | 是（测试对照，不发明礼包安装） |
| IM-19 | open | `TypeLeafTab.tsx:70` `GOVERNANCE_PAGINATION`；同测试 `IM-19 governance catalog table paginates`；`d7a6f78` | **否（代码已关）** |
| IM-26 | open | coverage FR-45.5 ⚠️「HTTP 夹具未钉同步出数」 | 是（测试债） |
| C35-QA-03 | open | coverage 写已关：`Register.test.tsx:177` 钉 `FREE_TIER_FEATURE_COPY`；`Register.tsx:24` 用 copy | **否（代码已关）** |
| C35-QA-04 | open | `sync.py:229` `_retract_missing_commands`；`d7a6f78`「同步收回已删命令」 | **否（代码已关）** |
| C35-QA-05 | open | `03-impl/qc-cond-4-evidence.md` 仍含 DEFAULT_QUOTA 绿段（如 :115、:200） | 是（证据文件陈旧，转文档债不是新 FR） |

**用户提的解法 vs 观察到的问题：** 无用户解法。观察：账本 `status: open` 落后于 `d7a6f78` / Register copy / 方言批。`/pm` 分诊时应用上表，禁止把 IM-17/19、C35-QA-03/04 再写成施工缺口。

---

### S-06 本机 LLM 网关在听，上游 key 空，产品闸默认关

| 项 | 内容 |
|---|---|
| 提及次数 | 操作者约束 1 + 活体 3 |
| 影响用户数 | 未量化 |
| 行为数据交叉验证 | `docker ps`：`litellm-proxy` Up healthy `127.0.0.1:4000`；`GET /health/liveliness` 200 `"I'm alive!"`；`GET /v1/models` 401 `No api key passed in`；容器内 `DEEPSEEK_API_KEY`/`MOONSHOT_API_KEY`/`OPENAI_API_KEY` **EMPTY len 0**（只报空/非空，不抄值） |
| **实际影响面** | 未量化 |
| 信号强度 | **中**（本机预发；不是生产事故） |
| 用户特征 | 租户经办点 AI 规划 / 平台路径；超管值班 |

**原文样本**：

> `LLM.ENABLED: false` ——`config/default/llm.yml:12`
> `POWER_MARKET.ENABLED: false` ——`config/default/power_market.yml:3`
> 「LLM.ENABLED 或 POWER_MARKET.ENABLED 为 true 时必须非空，否则拒绝启动。」——`config/default/settings.yml:8`

**用户提的解法 vs 观察到的问题**：

| 项 | 内容 |
|---|---|
| 用户提的解法 | 无。操作者：跟踪树默认 false；不要读密钥 |
| 观察到的问题 | 网关进程与产品闸是两件事：compose 已 up，应用默认不走；上游三键在 **运行中的** litellm 容器为空。开启 `LLM.ENABLED` 会撞启动闸（DUTY_CONTACT 亦空，Q-OPS-DUTY 已决不发明电话） |
| 可能的原因/方向 | ① 有意保持关 ② compose 未注入（默认 `${DEEPSEEK_API_KEY:-}`） ③ 经办会在 AI 规划看到网关/未配置失败，而不是「模型列表」 |

禁止把「打开 LLM.ENABLED」写成已投票需求。

---

### S-07 分支超 origin 7 commit 未推；合主干仍须 031→040；活体版本表停在 039

| 项 | 内容 |
|---|---|
| 提及次数 | 操作者约束 1 |
| 影响用户数 | 工程/合主干，不是终端用户 |
| 行为数据交叉验证 | `git status -sb`：`feature/project-structure...origin/feature/project-structure [ahead 7]`；`git rev-list --count` **7**。ahead 含 `018c369`（040）、`d7a6f78`。本机 `uv run --directory backend alembic current` 打印 **039**；同时活体 `GET /billing/plans` 已返回 040 回填的 `free`/`pro` |
| **实际影响面** | 未量化 |
| 信号强度 | **中**（合主干风险；版本表 vs 表存在不一致 → 已转 /sre） |
| 用户特征 | 合入操作者 / 预发库 |

**原文样本**：

> 「合主干仍须 Alembic 031→040。」——本拍 spawn 约束
> `040_billing_and_relay_sku.py` `Revises: 039`，INSERT `free`/`pro`

**用户提的解法 vs 观察到的问题**：

| 项 | 内容 |
|---|---|
| 用户提的解法 | 无产品解法 |
| 观察到的问题 | 树已有 031–040 文件；origin 未含这 7 拍。活体 API 已能列 plans，CLI `current` 仍 039 → **不要**在信号池当「没建表」 |
| 可能的原因/方向 | ① 另一条库 ② stamp 漂移 ③ 手工建表未 stamp |

日历「一次做完」不改变本条强度。

---

### S-08 访客能力市场被预发种子占领：400 张 NFR 卡，四类空，列表无翻页

| 项 | 内容 |
|---|---|
| 提及次数 | 活体 1 次普查（非工单） |
| 影响用户数 | 未量化。活体公开列表 **total=400** 全为 `nfr01qc2-*` 技能 |
| **行为数据交叉验证** | 2026-09-10 `GET /api/v1/public/capabilities?page_size=5` total **400**，首页 `nfr01qc2-399`…；`type=skill` 400；`type=plugin|command|agent|team` total **0**。官网 `Capabilities.tsx` `AssetGrid` 无 page 控件（`page_size` 默认 20）。首页精选 `SkillsSection.tsx` `listPublicSkills({ page: 1, page_size: 50 })`，无 S/A/recommended 时回退前 6 张 |
| **实际影响面** | 至少：任何打开 9113 `/capabilities` 或首页精选的访客，在本机预发会看到 NFR 卡片而不是五类商品 |
| 频次 | 每次打开公开市场 |
| 信号强度 | **强**（行为数据：400/0/无翻页；本机预发，勿外推生产 UV） |
| 用户特征 | 访客；注册用户登录前逛市场 |

**原文样本**：

> 活体条目 `name: nfr01qc2-399` `title: NFR卡片399` `description: preprod nfr-01 seed` `listing_state: listed`
> 「还没有上架的能力」——空态文案 `Capabilities.tsx:73`（四类 total=0 时会走到这句，与「全部」400 张并存）
> 「已上架的可复用能力，可在能力市场查看详情。」——`SkillsSection.tsx:42`

**用户提的解法 vs 观察到的问题**：

| 项 | 内容 |
|---|---|
| 用户提的解法 | 无工单。操作者要「深度梳理不好用」 |
| 观察到的问题 | 预发 NFR 种子 **listed** 进了公开商店；五类 Tab 里插件/命令/智能体/专家团空；全部/技能被 400 张测试卡占满且不能翻到第 21 张。失败≠空的文案在代码里（`MarketError`），本拍列表 **200 成功**，不是加载失败 |
| 可能的原因/方向 | ① 种子未隔离/未 unlist ② 公开查询无内部标记 ③ 官网未接分页 ④ Q-MARKET-USER 未关，不知道这页是给谁看的 |

**已落地、不要再报成缺口：** 单一「能力市场」导航（`SiteLayout.tsx` `NAV_LINKS`）；失败有「市场列表加载失败 / 重试」；预告无订阅按钮（代码路径存在，本机 400 张均为 listed）。

---

### S-09 后台订阅弹窗离线句未用冻结文案（IM-12）

| 项 | 内容 |
|---|---|
| 提及次数 | 审查账本 1（IM-12） |
| 影响用户数 | 未量化 |
| 行为数据交叉验证 | 未获取活体离线（浏览器未切离线）；代码静态对照 |
| **实际影响面** | 未量化 |
| 信号强度 | **弱** |
| 用户特征 | 已登录、在后台点订阅的经办 |

**原文样本**：

> 「订阅弹窗离线句未用冻结文案」——`feat-four-pillars-v2/state.yaml` IM-12
> 官网：`网络不可用，现在不能订阅。` ——`CapabilityDetail.tsx:100`
> 后台 `SubscribeModal.tsx` 无 `navigator.onLine`；失败回落「订阅失败。检查网络后重试。」（`:54`/`:144`）

**用户提的解法 vs 观察到的问题**：

| 项 | 内容 |
|---|---|
| 用户提的解法 | 无 |
| 观察到的问题 | 同一订阅动作，官网详情与后台弹窗离线句不一致；edge-states 冻结句未进弹窗 |
| 可能的原因/方向 | ① 漏接文案 ② 弹窗把网络失败与业务 code 混成一句 |

---

### S-10 LLM 配置页：列表失败被吞掉，空表与故障不分

| 项 | 内容 |
|---|---|
| 提及次数 | 代码 1 |
| 影响用户数 | 未量化 |
| 行为数据交叉验证 | 未登录 `GET /api/v1/llm/providers` **401**（守卫在）。页面 `loadList` catch 空（`LlmProviders.tsx:60-61`「列表加载失败由壳层兜底」）；本文件未见壳层 Alert |
| **实际影响面** | 未量化 |
| 信号强度 | **弱** |
| 用户特征 | 租户经办 / 公司管理员（`/llm` 经办可进） |

**原文样本**：

> `} catch { /* 列表加载失败由壳层兜底 */ }` ——`LlmProviders.tsx:60-61`

**用户提的解法 vs 观察到的问题**：

| 项 | 内容 |
|---|---|
| 用户提的解法 | 无 |
| 观察到的问题 | 加载失败可能渲染成「没有供应商」，与真空间不可分。对照官网市场已区分失败≠空 |
| 可能的原因/方向 | ① 壳层兜底未接 ② 有意忽略 |

非 500，不转 /sre。

---

### S-11 词汇表仍写「令牌不发给租户」，现网已签发租户令牌

| 项 | 内容 |
|---|---|
| 提及次数 | glossary 1 vs 018c369 |
| 影响用户数 | 运营/客服会说错话（无客服样本） |
| 行为数据交叉验证 | 代码：`POST /api/v1/relay/tokens` 经办可签发 |
| 信号强度 | **中**（对内教错，不是用户投票「要市场」） |
| 用户特征 | 写 FAQ / 值班的人；租户看到「签发令牌」 |

**原文样本**：

> 「租户渠道组 / 虚拟令牌仍待产品拍板，不发给租户。」——`CONTEXT.md:48`
> 「令牌（平台路径） \| 网关虚拟钥匙，**不发给租户**，直至租户中转 SKU 另开需求。」——`CONTEXT.md:50`

**用户提的解法 vs 观察到的问题**：

| 项 | 内容 |
|---|---|
| 用户提的解法 | 无 |
| 观察到的问题 | Q-RELAY 已关且 SKU 已发租户明文一次。glossary 未跟上。平台网关 master key 仍不发给租户（LiteLLM `/v1/models` 401）——两套「令牌」仍混名 |
| 可能的原因/方向 | ① 更新 glossary ② 产品名区分「渠道组令牌」vs「网关钥匙」vs「出站拉数钥匙」 |

---

## 已转出的非需求项

| 项 | 类型 | 转给谁 | 时间 |
|---|---|---|---|
| 本机 `alembic current` 打印 039，同时 `/api/v1/billing/plans` 200 且含 040 回填档 | **故障/环境漂移** | `/sre` | 2026-09-10 |
| 抽样 API 未登录 401/422（relay/usage/orders/llm/newapi/product-events、signup 缺字段、events 缺 `anonymous_id`） | 守卫/校验，非 500 | — | 2026-09-10 |
| `GET /api/v1/health` 无斜杠 307 → `/health/` 200 `{"status":"healthy"}` | 重定向，非故障 | — | 2026-09-10 |
| urllib 对 9113 一次 502；随后 curl 三次 200 | 未复现，不编事故 | `/sre` 仅作观察 | 2026-09-10 |
| IM-02 HTML 常量对照、IM-13 未解码、IM-26 HTTP 夹具、C35-QA-05 陈旧证据段 | 测试/文档债 | `/qa`（账本回写），不是新 FR | 2026-09-10 |

**本拍抽样未见 500/进程崩溃。** 故障不走信号池。

## 本期汇总

| 信号强度 | 数量 | 编号 |
|---|---|---|
| 强 | 1 | S-08 |
| 中 | 7 | S-01 S-02 S-03 S-06 S-07 S-11（S-05 内仍开项并入测试债，不单计强） |
| 弱 | 3 | S-04 S-09 S-10 |
| 已转出（非需求） | 5 行 | 上表 |

S-05 是账本对照，不按「用户强烈要求」计强。

## 与上期对比

上期：`feat-four-pillars-v2/01-define/diagnosis/ops.md`（2026-09-08）。当时 Wave 0/1 **未上线**、事件查询面 0、定价空头、注册成功钮「再注册一家」、Hero 示意大数、Excel 承诺。无生产使用量，**不能按 UV 归一化提及量**。

| 主题 | 上期 | 本期 | 变化 | 说明 |
|---|---|---|---|---|
| 官网示意大数 / Excel | 仍在（S-02/S-03） | Home「没有真实聚合时不展示规模数字」；Features「CSV 或 JSON，单次最多 100 条」 | ↓ 已兑 | 不要再报 Excel/Hero 大数缺口 |
| 注册成功进不了后台 | 主钮再注册 | `Register.tsx` 主钮「登录管理后台」`/login?from=/dashboard` | ↓ 已兑 | |
| 单一能力市场 | 双广场 | 导航只留「能力市场」 | ↓ 已兑入口；**新问题**是种子内容（S-08） | |
| 定价空头 CTA 进注册 | 专业/企业 href=/register | 预告 Modal + mailto，免费档才 `/register` | ↓ 已兑「不到注册」；**新裂缝** 价目 API 公开 pro（S-01） | |
| 中转零入口 | 官网 0；Q-RELAY 开 | 后台「渠道组」已有；官网仍预告 | → 产品面部分履约 | |
| 出站钥匙 | 平台级空列表 | 仍空；401 | → 未变（S-02） | |
| 工单 | 0 | 0 | → | 渠道声明不变 |
| WACT / 事件 | 查询面 0 | 路由在：`POST /api/v1/public/events` 缺 `anonymous_id` 422；`GET /product-events` 401 | → 能打到守卫，**生产四周窗仍未开始** | |

## 角色对照（解法 vs 观察，禁止代选开放问）

| 角色 | 用户提的解法 | 观察到的问题（出处） |
|---|---|---|
| 访客 | 无 | 9113 SPA 200 标题「AutoAgents · 智能数据采集系统」；首屏仍采集叙事（`Home.tsx:120-121`，Q-VOICE 未关故不升「要改 Slogan」）；定价专业/企业预告；市场 400 NFR 卡 / 四类空 / 无翻页（S-08） |
| 注册用户（开通负责人） | 无 | 注册端点活体 `POST /public/tenant/signup` 缺字段 422（契约在）；成功主钮去 9112 登录（已兑）；登录页「没有账号？企业注册」（`Login.tsx:222-224`）。未持会话打后台：SPA 仍 200 壳，客户端守卫 |
| 租户经办 | 无 | 菜单：采集/AI/数据/用量/渠道组/LLM/我的安装。不能进 `/newapi` `/platform-ops` `/users`（`platformOnly` + 直打 404）。渠道组令牌 ≠ 出站钥匙 ≠ 网关 key（S-02/S-03/S-06） |
| 公司管理员 | 无 | 成员页冲突文案已转可行动作（`Members.tsx:27-35`）；满额可提交线下订单但无订单历史（S-01）；只读成员不能改套餐（已兑） |
| 平台超管 | 无 | 平台运营台含待确认订单、死信、产品事件；值班仍 `/newapi`；治理台分页/短名跳转已在 `d7a6f78`（不要再开 IM-17/19） |

活体未登录后台业务页：只拿到 HTML 壳（`/login` `/dashboard` `/usage` `/relay` 均为 200 bytes≈1847），**未获取**登录后 DOM。上表后台交互以源码+Jest+OpenAPI 为准，不编点击结果。

## 自检

- [x] 每条信号有具体出处（文件:行 / 测试名 / 操作者原话 / 活体 curl）
- [x] 原文未改写
- [x] 提及次数与影响用户数分开；工单=0 未编
- [x] 活体交叉验证已做；未量化显式标注
- [x] 信号弱的如实标注
- [x] 用户提的解法与观察到的问题分开
- [x] 未在归纳阶段下因果（只列可能原因）
- [x] 故障已转 `/sre`，未把 401/422 当新 FR
- [x] 渠道偏差已声明；日历压力未当信号
- [x] 与上期对比未假装有生产 UV 归一化
- [x] 未代选开放五问
