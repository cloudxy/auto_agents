# Market · 合入后履约裂缝（post-merge-upgrade）

> 作者：researcher 帽｜日期：2026-09-13｜泳道：L3｜下游：discover briefing · pm RICE Reach
> 单位：☑ 租户/买方账号（ToB） ☐ 去重使用者（ToC） — 只勾一个
> 本变更：合入 `feat/litellm-l1` × `origin/main`（`1db6a47`，2026-09-13）之后，**谁仍撞上产品自称已解决、实际未履约的问题**。不是行业 TAM，不是再开「实现四支柱」。上游 `feat-four-pillars-v2` / `feat-product-complete` / `upgrade-four-pillars` 均为 **Closed / 有条件放行，不是四柱 GA**——本文件不把它们重开为 GA。

## 可及集合

本变更的「谁」= 会撞上 **示意完整 + 双轨并存 + 六个开放问未关 + 环境闸从未跑** 的 **买方租户**（采集经办所在企业、开通负责人、租户公司管理员），外加平台侧值班/超管（不是买方，但是同一产品面上的问题持有者）。**不是**「AI 采集 / LLM 中转 / 能力市场行业有多少家公司」。官网商店面随 Power Market，**不单开 ToC 增长环**（briefing）。不混座位、成员席、DAU。

| | 数 | 来源 | 等级 |
|---|---|---|---|
| 下界 | **未量化** | 无生产买方账号快照。本机联调库 2026-09-08：`tenants` 4 行（`default` / 两家演示公司 / `platform`）、`spider_tasks=0`、`orders=0`、`tenant_subscriptions=0`（miner）——操作者工作区，**不是**买方。其后计费/出站/SKU 表已进库（040→046），**没有**「数字+来源+时间窗」的生产查询证明出现过付费租户。v2 spec §1.6 Reach=1 是占位，无市场规模含义。 | 不得标 E3。空仓与占位是 E2 引用，操作者「再深入梳理」是 E1 |
| 上界 | **未量化** | 无生产 UV、无付费样本、无客户工单、无外部买方名单。官网 Hero 已改「没有真实聚合时不展示规模数字」，仍禁止把示意或定价档位数当上界。 | 不得标 E3 |
| 未量化 | **是** | 缺：生产租户数、买方账号、工单、UV、WACT、订阅成功企业、`payment_succeeded` 生产计数、漏斗。产品事件表已在 v2 施工集落地，**本帽没有**生产窗查询。 | E1 |

**禁止当 Reach / E3 租户行为的数字（内容与夹具盘点，E2）：**

| 数 | 是什么 | 来源 | 为何不是市场 |
|---|---|---|---|
| ZCode `local-plugins` **6** 个真实插件 | 操作者本机源供给 | `power-market-design.md` 2026-09-07 只读盘点 | 一台开发机的索引对象，不是租户订阅 |
| Kimi managed **约 16** 个托管插件 | 同上，Kimi 入站主源 | 同稿；许可抽样 12×UNLICENSED / 3×LicenseRef / 1×MIT | 供给与许可闸材料，不是买方 |
| 跨插件 SKILL 名冲突 **51** | 身份规则输入 | 同稿痛点 §2 | 工程约束，不当 Reach |
| QC GWT-18.1 **1** 次完成且 `result_count=1` | 冻结施工验收 | `feat-four-pillars-v2` release-opinion 2026-09-10；夹具已删 | 验证夹具，不是租户出数 |
| pytest / jest 通过条数 | 合入闸指纹 | product-complete / upgrade 放行意见 | 测试绿 ≠ 买方存在 |
| 定价 **¥299** | 专业档印价 | `frontend/official/src/pages/Pricing.tsx` | 价签，不是付费转化 |

`POWER_MARKET.ENABLED: false`（`config/default/power_market.yml`，2026-09-13 仍关）。商店订阅行为在配置上不可发生，故 **0 次订阅 ≠「没人要订」**。

`LITELLM.ENABLED` / `PROXY.ROUTE_INTERNAL` / `SHADOW.ENABLED` / `ADMIN.ENABLED` **全部默认 false**（`config/default/litellm.yml`）。`LLM.ENABLED: false`。`RELAY.SCHEDULER_ENABLED` / `PROBE_ENABLED` 默认 false。`OPS.DUTY_CONTACT: ""`。开 LLM 或开市且值班联系为空 → 进程拒启。这些是开关事实，不是「租户不用网关」的行为计数。

历史上 **0 笔 live 支付**：2026-09-08 miner `orders=0`；upgrade QC 条件 4：HMAC / `signed_body` 夹具 **不是** live 支付宝/微信收银台；BillingPanel 文案「本环境不直连支付网关」。无生产 `payment_succeeded` 计数窗。不得把测试建的 `checkout_pending` 行当付费金标。

### 问题持有者（命名，不计数）

合入后产品仍自称四件事都能做。持有「履约裂缝」的人按动作拆，不得合成一种「用户」。六个 Q-* **未关**，下表只标谁会撞上缺口，不代选主用户、不代选下一波。

| 裂缝 | 谁有这个问题 | 单位 | 证据 | 等级 |
|---|---|---|---|---|
| 第一次出数仍脆 | 租户里要把网页变成表格的 **采集经办**（角色 operator） | 租户 | 官网首屏锁「粘贴链接即可出数」（`Home.tsx` HERO）；`LLM.ENABLED` 默认关；product-complete **C4** 工人环冒烟未勾；upgrade GWT-U01.1 = FakeRedis，**不得**宣称非夹具北极星已在生产出现 | E2 合同角色 + 闸未跑；**无**经办行为 E3 |
| 能看价、付不成 | **开通企业的负责人 / 租户公司管理员**（买方） | 租户 | 官网专业档「去结账」→ `/billing/checkout?product=plan_pro`；企业档同形；用量页仍挂 **线下订购卡片**（`BillingPanel`：`createOrder` + `offline`/`alipay`/`wechat` + 超管 `confirm_paid`）。结账路径要通道通知验真（ADR-0024），夹具 ≠ live。Q-PRICE 仍开 | E2 双轨代码；0 live 支付不得标 E3「没人买」 |
| 钥匙三环 | 要把结果拉出本企业的 **经办 / 公司管理员** | 租户 | 出站拉数查找链（`public.py`）：`outbound_keys` → `api_keys` → `KEY_BINDINGS`。后台有「出站拉数钥匙」页，**无** `api_keys` 前端。CONTEXT 仍写「令牌不发给租户」，与 ADR-0019/0020/0025 已发渠道组令牌、已发出站钥匙 **漂移** | E2 鉴权三环并存；无拉数生产计数 |
| 中转「看起来能用」 | **已开通 SKU 叙事下的公司管理员**（签发）；**平台值班（超管）**（`/newapi` 三问驾驶舱 vs `/litellm` admin keys）。租户直打值班页仍 404 同形 | 值班 ≠ 买方；经办随租户 | Q-RELAY 在 upgrade 已答「对外可买 SKU」；本轮 **Q-AGPL 未关**，访客/租户可见面禁止「当前可买」。渠道组令牌经 LiteLLM HTTP 登记（ADR-0019）；L1 另有超管 `/api/v1/litellm/keys`（`LITELLM.ADMIN.ENABLED` 默认关）。**C2 真网关轮**在「向租户开放渠道组/令牌前」仍未勾 | E1（商用口径）+ E2（双轨 API）；无 live chat 用量 E3 |
| 能力市场订不到 | 三件不得合成：① 匿名访客逛已上架 ② 已登录租户按 **一行** 订到宿主 ③ 平台超管管源/上架/许可 | ② 才是 ToB 单位；① 是访客场景，本变更不拿 DAU | D10/D22–D29 Accepted；flag 关则订一行不可发生；Q-MARKET-USER 未关。无「我想安装」原声 | E2 设计拍板 + 开关；**不是**「用户要市场」 |
| 找不到人 | 访客 / 买方要值班或收集通道 | 租户或未转化访客 | 官网 **无 Contact 页**（pages 闭集：Home/Pricing/Register/Capabilities/Skills/Legal）；`OPS.DUTY_CONTACT` 空。Q-OPS-COLLECT 未关 | E2 缺页；负荷 **未量化** |
| C 端个人注册 | 没有企业、却被强制「创建企业」的人 | **不是**本文件 ToB 单位，除非注册后变成买方租户 | `Register.tsx` 企业名必填、主按钮「创建企业」。Q-C-REG 未关。归属「平台租户」规则已在产品面讨论，**本帽不代开** | E2 注册路径；人数未量化 |

操作者「再次深入梳理 / 给出升级方案」= **E1 程序目标**，不是租户投票。一人不是市场。

## 渠道偏差

当前证据来自：**操作者**（intent + 本轮六个开放问 + 上轮已关的 Q-RELAY/Q-BILL）/ **设计与评审**（D1–D29 Accepted；ADR-0019/0020/0024/0025）/ **内部诊断与放行**（miner 2026-09-08；ops 0 工单；product-complete / upgrade **有条件放行**；remaining-work C2–C5 未勾）/ **销售与产品面代码**（官网、定价、结账、BillingPanel、三环鉴权、双值班 API）。

**不是**来自：工单（0；定价仍写「工单支持」，仓库无租户工单模块）/ 应用商店评论（0）/ 访谈 / NPS / 问卷 / 生产行为数据。

| 渠道 | 本期量 | 系统性偏差（本变更） |
|---|---|---|
| 操作者对话 | 1 名程序主人 | 把「合入后还有问题」听成「租户都撞上了这些问题」。聊天窗 = ≤E1 |
| 设计文档 / ADR / 放行意见 | 上游三特征 Closed + 本仓读码 | 有条件放行易被写成「已经卖得出去」。测试绿、夹具出数、HMAC 通知 ≠ 买方行为 |
| 官网 / 定价 / README | 已读 | 销售口径可靠性低～中。现 Hero 不再印示意大数，但 ¥299 / 「去结账」仍会冒充已通支付 |
| 工单 / 客服 | **0** | 「零投诉」不能推出「没问题」；也听不到不满。Q-OPS-COLLECT 未关 = 连这 1% 的通道都没有 |
| 使用数据 | **未获取**生产 n | 无行为则无法发现沉默需求（重复操作、搜无点、漏斗掉）。事件 SDK 在仓 ≠ 有查询窗 |
| 本机插件树 / 联调库 | 6 / ~16 / 51；4 租户行（2026-09-08） | 供给盘点与工作区 OLTP 冒充需求规模 |

听不到谁：**真实买方租户**、**轻度经办**、**已流失**（无付费样本则无流失原因）、**企业沉默**（公司管理员不来聊天窗）、**满意者**、**匿名访客 UV**、非操作者的平台值班接班人、**被强制创建企业的个人**（Q-C-REG 未关，注册漏斗外无声）。

主动反馈通常不到 1%。本期连这 1% 的通道都没有。影响面一律 **未量化**。

本轮补不补：**明确不补** 生产 UV/工单/支付查询（没有可引用的生产窗；把本机库当市场会把工作区写成买方）。**不补** 把 6/16/51、pytest 条数、¥299 写成 Reach。发现带不开问卷。补数属于事件查询面可用之后的 ops/analyst，不在本帽。

## 现状替代与切换成本

与 compete 的「现状」对齐（本帽只写 **他们现在用什么代替「合入后声称可履约的产品」**，不写 borrow/avoid/differentiate）。集合必须含 **现状 = 合入后的本仓半成品**。

唯一被观察到的使用者是操作者 / 本机工作区。合入后他们面对的不是「没有功能」，而是 **两套都能点、哪套算数不清楚**：

| 裂缝 | 现状替代（合入后本仓 + 仓外习惯） | 切到「单一履约」时要放下什么 |
|---|---|---|
| 智能采集 | 后台数据工厂碎片（任务/向导/CSV）；QC 曾跑通一次夹具出数后删除；官网按采集叙事获客；`LLM.ENABLED` 关则规划/试采走业务异常句 | 自建规则、人工导出、BYOK 直连供应商。第一次出数仍可能卡在工人/配额/LLM 前置（C4 未跑） |
| 收款 | **双轨**：① 官网/结账页 `POST /billing/checkout`（支付宝/微信，验真通知才开通，ADR-0024）；② 用量页 `BillingPanel` 线下订购 + 超管 `POST /orders/{id}/confirm`。live 收银台不在合入闸。定价印 ¥299，可见面禁「当前可买」 | 习惯「点确认即开通」或「HMAC 夹具当已付」。无付费样本可练。Q-PRICE 仍问专业档与确认后三数字 |
| 拉数鉴权 | **三环并存**：出站拉数钥匙（有租户页）/ L1 `api_keys`（仅 API）/ `KEY_BINDINGS`（配置）。渠道组令牌 `sk-` 是第四把、平面不同（ADR-0020 互否） | 记错用哪一把；用 `sk-` 拉数或用出站钥匙打网关 = 拒绝。CONTEXT「令牌不发给租户」会把值班/买方一起教错 |
| 中转 / 值班 | 租户 **BYOK**；平台路径目标 LiteLLM 但默认全关。值班页路径仍 `/newapi`（NewApiOps），L1 另挂 `/api/v1/litellm/*` admin keys。new-api **已退役运行时**，不作为可卖网关。企业档仍印「中转站渠道组分配」 | 自建网关 / 厂商控制台 / 不走平台路径。C2 真网关轮未跑前，签发成功 ≠ live chat 用量。卖 SKU 还挡 Q-AGPL |
| 能力市场 | 各宿主自己的目录：`~/.zcode/local-plugins`、Kimi desktop managed、Claude/Grok 启用子集；商店 flag 关 | 按宿主重复安装；跨宿主 51 个重名靠人记。切换成本 = 改用平台订阅语义（订插件不带礼包，与宿主商店习惯相反） |
| 找人 / 注册 | 无联系页；mailto 只在类型注释里。注册 = 创建企业 | 个人用户要么建空壳租户，要么离开。不是 ToC 增长环本轮要做的证据 |

**没有**「已在用竞品四柱一体、等着迁来」的计数样本。合入后的半成品面前，默认替代是 **拆开的宿主工具 + 双轨本仓 + 操作者本人当唯一租户**。

## 频次 / 付费位置

- **每租户多久遇到一次：** **未量化**。推断（不得当 E3）：采集经办按任务撞出数闸；买方在看定价/结账时撞双轨与未通收银台；钥匙三环在第一次对外拉数时撞一次、之后每次用错再撞；值班按排班；市场订阅远低于采集（若主用户是治理则更稀）。无工单可证「多久疼一次」。
- **ToB 预算 / 套餐：** 定价印专业 ¥299、企业档渠道组/私有技能库/工单支持；付费档 CTA 已改「去结账」（不再三档同进注册）。**0 笔 live 支付**。谁出钱、专业档确认后是否履约三数字、渠道组是否企业档专属 = **Q-PRICE 未关**。中转是否可写「当前可买」还挡 **Q-AGPL**（Q-RELAY 在 upgrade 已答对外可买 SKU，本帽不重开、也不把已答写成已通商用）。
- **ToC：** 本变更单位不是去重访客。briefing：官网商店面随市场波次，**本轮不做 ToC 增长环**。Q-C-REG 未关；注册强制建企业。访客诚实履约是裂缝，UV **未量化**。

## 给 RICE 的 Reach

**未量化。**

不要把 v2 spec 的 Reach=1 占位抄进本轮打分当「至少 1 个租户」。不要把 6 插件 / 16 Kimi / 51 冲突 / QC 1 次出数 / 合入闸通过条数写成 Reach。不要打 RICE 分。安全/权限/隔离/密钥不进 git / 404 同形仍可被 pm 标成必做，那是合规约束，不是本文件的市场规模。

未量化不得标市场 **pass**（briefing Falsify）。本帽不关 falsify。

---

## 证据对照（防串级）

| 说法 | 等级 | 备注 |
|---|---|---|
| 操作者要求合入后再梳理问题与升级方案 | E1 | intent_quote；不是租户原声 |
| D1–D29 Accepted；ADR-0019/0020/0024/0025 Accepted | E2 | 设计拍板 |
| 2026-09-07 本机 6 / ~16 / 51 | E2 | 内容库存 |
| ops：0 工单、无 UV、无付费样本（2026-09-08） | E2 | 引用诊断；**不是** E3「用户行为计数」 |
| miner 4 租户行、0 任务、0 订单（2026-09-08 本机） | E2 | 工作区 OLTP，过期快照；禁止当今日生产 n |
| `POWER_MARKET.ENABLED: false`；LITELLM/LLM/RELAY 默认关；`DUTY_CONTACT` 空 | E2 | 2026-09-13 读配置 |
| 出站拉数三环：outbound_keys → api_keys → KEY_BINDINGS | E2 | `backend/app/external_api/v1/public.py` |
| 收款双轨：checkout notify vs BillingPanel `createOrder`+`confirm_paid` | E2 | `billing.py` + `BillingPanel.tsx` + `Checkout` 路由 |
| 值班双轨：`/newapi` NewApiOps vs `/api/v1/litellm` admin keys | E2 | 路由聚合；`LITELLM.ADMIN.ENABLED` 默认关 |
| CONTEXT 计费/令牌句滞后于已合入代码 | E2 | 词汇表 vs ADR-0019/0024；调研不在 Frame 改判 |
| 上游三特征有条件放行、非四柱 GA | E2 | 三份 `release-opinion.md` |
| product-complete C2–C5 环境闸未勾 | E2 | `remaining-work.md` + `checklist.md` 待办框 |
| 任一本周生产 WACT / 订阅企业 / UV / live `payment_succeeded` | — | **没有**。不得标 E3 |

## 开放问题（本帽不代答）

| id | 与 Reach 的关系 | 谁答 |
|---|---|---|
| Q-VOICE | 获客第一句是否采集；代码面 Hero 已锁采集，本轮 briefing 仍列为待确认。不改变 ToB 单位，改变「谁先撞上产品」 | operator |
| Q-PRICE | 付费位置与确认后是否履约三数字；无 live 支付样本则频次/预算保持未量化 | operator |
| Q-MARKET-USER | 市场主用户是租户订阅还是平台治理 → 可及集合的主角色不同，但仍是 ToB 单位或非买方超管，不是 DAU | operator |
| Q-AGPL | 中转作独立 SKU 的商用口径；未关不得写「当前可买」，买方集合是否含「要渠道组的企业」今日 **0 样本** | operator |
| Q-OPS-COLLECT | 真实值班/收集通道；无工单则频次保持未量化 | operator |
| Q-C-REG | C 端个人注册是否开放；开放也不把 DAU 写进本文件单位，除非转化成买方租户 | operator |
