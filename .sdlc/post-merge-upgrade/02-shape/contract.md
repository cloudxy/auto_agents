# 技术方案 · 合入后四角色完备（post-merge-upgrade）

> 上游：`01-define/spec.md` **v1.7** + `user-story.md` + `metrics-blueprint.md` + `00-discover/briefing.md` + define G-fresh r8 PASS
> 特征：`post-merge-upgrade`｜泳道：L3｜appetite：程序；端态四角色可判定完备；施工分波；**W1 与 live 支付不得同一 2 人周**
> 作者：/architect｜日期：2026-09-13｜版本：v1.1（shape r1：QA-01 点名 supersede 0024 决策 3 / 0025 决策 1；QA-05 GWT-M11.11/18 挂 T-07/T-08）
> 冻结 FR：FR-M01…M03、M06、M10…M15、M20…M24、M26、M30…M35、M40、M41、M50、M51（26 条，>20 → 本 spawn 只写票表，不建空 `tickets/`）
> 前合同：upgrade ADR-0024/0025、product-complete ADR-0019/0020 **不复制**。本文件只补合入后缺口。D1–D29 / ADR-0010…0018 / ADR-0019/0020 **不重开**，除非下文显式 supersede。
> 本 spawn：`contract.md` + [ADR-0026](adr-0026-two-legal-fulfill-paths.md)。不写 `db-spec.md` / `edge-states.md` / 实现代码 / 表结构。

下游：`/dba`（§7）· `/designer`（空态金标与单一入口 IA）· 实现角色（票表）· `/qa`（GWT）· `/sre`（C2 环境闸，不是本波代码完成）。

出现任一句 = 本合同不合格：标四柱 GA；指纹前印「当前可买」；W1 与 live 支付同一 2 人周；用量页「套餐与订购」与结账长期双轨当特性；出站与渠道组统一成一把 `sk-`；把 HMAC 夹具写成支付已通；把 C2 真网关轮勾成代码 FR；重开 Q-*；租户可见「已有未完成的支付」；数据中心空态旧句「还没有采集结果。完成一次采集后会显示在这里。」；一张「实现四柱/实现 W1–W5」巨票。

---

## 1. 现状测绘（改造类）

**现有边界**（2026-09-13 读码，分支 `feat/litellm-l1`，tip `1db6a47` Merge origin/main）：单进程 FastAPI `:9111` + 平行 Scrapy Worker + admin `:9112` + official `:9113`。LiteLLM 独立 `deploy/litellm`（ADR-0010/0014）。四柱有条件放行，**非 GA**。

读码结论（缺口，不是已兑清单）：

| 面 | 现码 | 对本特征 |
|---|---|---|
| 规划 | `ai_planner` 在 LLM 关时抛「LLM 功能未启用…」；`launch_plan` 先抢断 `planning` 再后台失败 | FR-M01 要 3 秒内「智能规划未开放」、不产生可入队方案 |
| 数据中心 | 空态金标已是「还没有结果，去提交采集」；导出 CSV/JSON、上限 100 **静默截断出文件**；事件名 `results_exported` | FR-M02.6 要可见「单次最多导出 100 条」且**不产生文件**；事件 `data_export_completed` |
| 第一次采集 | 入队不查付费/订阅；夹具 `example`+httpbin 仍在 | FR-M03 对照验收；禁「请先开通专业档」前置 |
| 结账双轨 | `Usage.tsx` 挂 `BillingPanel`（「套餐与订购」→ `POST /orders`）；另有 `/billing/checkout` | FR-M10 必须拆掉可提交订购表 |
| 未配通道 | `create_checkout` 422 零新行；`CHECKOUT_EMPTY_USER`=「收款通道未开通」 | GWT-M11.1 要待支付 + 「…提交后等待平台确认开通」 |
| 确认收款 | `confirm_paid` 拒绝 `CHECKOUT_PRODUCTS` / 在线通道（`ORDER_CONFIRM_OFFLINE_ONLY`）；运营台列表只 `status==pending` | W2 合法开通边断了；[SEC-3] 无金额核对 |
| 状态词 | `CHECKOUT_PENDING_EXISTS_USER`=「已有未完成的支付」；Checkout UI 仍渲染开通处理中/未完成 | GWT-U30.2 已作废；W2 闭集两态 |
| 专业档配额 | 定价页 `PRO_TIER_QUOTA`=50/200000/5M；040 种子 `pro.quota_json`=20/500000/5M | FR-M12 执法必须与定价页同一套 |
| 企业档→中转 | `_fulfill_product`：`plan_enterprise` 只 `_apply_plan`，不写 SKU | GWT-M11.15 缺口 |
| 出站 | `public.py` 三环：outbound_keys → **api_keys** → KEY_BINDINGS；菜单已有「出站拉数钥匙」 | FR-M20 查找债：未在出站入口签发 → 0 行；[SEC-2] |
| 值班 | 导航叶「中转站管控」`/newapi`；另有 `GET/POST /api/v1/litellm/keys` 无独立前端叶 | FR-M30 用户可见值班类叶子必须=1；钥匙若存在只在该入口内 |
| 设置 | 租户打开 Settings =「当前账号不能改系统设置」说明态，**不是** 404 同形 | GWT-M33.5 要 404 同形、无「当前账号不能改系统设置」 |
| 市场 | `POWER_MARKET.ENABLED` 已闸订阅；租户 `TenantShelf` vs 超管七叶已分叉 | W5 对照走完；关旗句不得写成空货架 |
| 注册 | 官网主钮「创建企业」、公司名 min_length=2 | FR-M51 对照 |

**约束**：

| 约束 | 来源 | 影响 |
|---|---|---|
| 017 业务表 `tenant_id` NOT NULL | PIT-4 | 出站/令牌/订单禁止 NULL=平台 |
| `require_admin` ≠ 超管 | PIT-2 / ADR-0017 | 改守卫同 PR 改测试 |
| 平台表恒 NULL `tenant_id` 必须豁免 | PIT-3 | 商户凭据无租户列则不要硬加 Mixin |
| 同前缀静态段先于动态段 | PIT-1 | `/billing/notify/{channel}`、`/billing/checkout` 必须在 `/orders/{id}` 之前 |
| 出站 ≠ `sk-` | ADR-0020；A5 | 禁止 `relay_tokens` 兼出站；拉数查找不含 relay hash |
| 令牌打独立 LiteLLM HTTP | ADR-0019 | 不持 `LITELLM.DB_DSN`；不焊根编排 |
| 中转已买=权益行不是组行 | ADR-0025（未 supersede 部分） | 读路径以 SKU 为闸 |
| 两条开通 | **ADR-0026**（本波） | 确认收款接结账单据；未配通道可待支付 |
| B1–B3 | `tools/check/arch.sh` | 市场禁 import billing/relay/网关；爬虫不写主库 |
| 专业档 ¥299 + 三数字 | Q-PRICE；`frontend/shared/src/constants/quota.ts` | 执法数字以定价页为准，不以 040 种子为准 |

**本次不动什么**：

- Scrapy 管道、Redis 队列协议、工人不决定归属
- LiteLLM 独立 compose；不请回 new-api 运行时；不租户化网关 `/ui`
- 通道闭集以外的支付（Stripe/兑换码/易支付）
- 退款 / 发票 / 取消入口 / 租户可见 `unpaid`/`fulfilling`（live 波）
- 把 C2 真网关轮写成代码 FR 完成
- Casbin / Ory / 开发者门户 / 分成 / enable-host
- xlsx 导出（P-01）
- 北极星改成支付或订阅
- ADR-0019 登记虚拟 Key 的 HTTP 路径（本波不重接网关）

**已知技术债**（碰到要小心，不在本轮当新故事）：

| 位置 | 债 | 本次 |
|---|---|---|
| ORM Mixin 可空 vs 017 NOT NULL | 测试引擎骗人 | 入队/钥匙/订单显式传租户 |
| `POST /billing/orders` + BillingPanel | 第二套故事 | **触碰**：拒建单 + 拆 UI（expand） |
| `confirm_paid` 拒结账单 | 与 FR-M11 反 | **触碰**：ADR-0026 |
| 出站三环含 `api_keys` | 第二平面能拉数 | **触碰**：FR-M20 收口 |
| 040 `pro.quota_json` ≠ 定价页 | 确认后执法错 | **触碰**：履约写入定价页三数字 |
| Settings 说明态 vs 404 | GWT-M33.5 | **触碰** |
| R10 子包日志 | 历史 | 新公开方法仍要 `logger.` |
| 企业档价目行未进 040 种子 | 测试夹具才有 `enterprise` ¥999 | **触碰**：/dba 语义；结账必须有 ≠¥299 的展示金额 |

---

## 2. 模块边界

### 2.1 能力聚类

| FR | 能力拆解 | 归属模块 |
|---|---|---|
| FR-M01 | 规划未开放诚实句 · 不入队不产方案 · 成功只到「方案与试采」 | 智能规划叶 + Admin 壳 |
| FR-M02 | 本企业结果可见 · CSV/JSON 导出 · 100 条闸 · 跨租户 404 | 采集入队/结果 |
| FR-M03 | 空免费企业无付费/订阅/中转前置仍可入队 | 采集入队/结果（配额只拦三类上限，不拦档位） |
| FR-M06 | `llm_planning_blocked` / `data_export_completed` 仅超管可查 | 产品事件叶 |
| FR-M10 M13 | 一条结账故事；满额「去结账」；拆用量页订购表 | 收款履约 + Admin/官网壳 |
| FR-M11 | 下单待支付 · 确认开通 · 一商品一单 · 未配通道可提交 | 收款履约（编排者） |
| FR-M12 | 专业档三数字执法 · 中转非专业赠品 · 企业档写 SKU | 收款履约写；SaaS 配额读；中转 SKU 权益写 |
| FR-M14 | 结账故事事件；`second_checkout_story_submitted`=0 | 产品事件叶 |
| FR-M15 M50 | 夹具≠指纹；禁「当前可买」 | Admin/官网壳（全可见面护栏） |
| FR-M20 M26 | 出站单一产品名 · 错平面 0 行 · 拒绝可查 | 出站拉数钥匙 |
| FR-M21 | 成员增改删；不能设超管 | 成员 |
| FR-M22 | 三类用量与上限；0≠失败；将满≠已尽 | SaaS 配额 + Admin 壳 |
| FR-M23 | 渠道组未开通 vs 已开通零令牌 | 中转产品面（读权益） |
| FR-M24 M40 M41 | 货架+安装；关旗诚实；上架下架；无投稿 | Power Market + Admin 壳 |
| FR-M30 M34 M35 | 值班单一入口；签发≠live；入口打开可查 | 值班编排 |
| FR-M31 | 运营台确认本笔+金额 | 收款履约 + Admin 壳 |
| FR-M32 | 停用/恢复 | 用户生命周期 |
| FR-M33 | 联系空不展示；设置不说谎；租户直打设置 404 | Admin/官网壳 |
| FR-M51 | 注册=创建企业 | SaaS 鉴权 |

**FR 归属核对**：26 条均有归属。FR-M11 跨履约与壳：建单/确认在履约，两态文案在壳。FR-M12 跨配额与 SKU：履约按商品码写，配额模块不猜「这是不是中转」。FR-M50 随各波护栏，票挂 W2 机械钉（全可见面），W5 回归。

### 2.2 模块清单

| 模块 | 一句话职责（不含「和」） | 变更理由 | 新建/既有 |
|---|---|---|---|
| SaaS 鉴权/配额 | 判定谁能写、三类配额是否放行 | 专业档执法三数字与定价页对齐；注册仍创建企业 | 既有 |
| 采集入队/结果 | 把任务钉在企业上并把条还回本企业 | 导出 101 拒绝出文件；第一次采集无付费墙 | 既有 |
| 智能规划叶 | 规划提交的即时可见结果 | 未开放不装成在规划 | 既有 `ai_planner` |
| 收款履约 | 待支付→（确认或通道验真）→按商品开通 | ADR-0026 第二条开通；拆第二套单据 | 既有 billing，**改编排** |
| 商户凭据 | 保管支付宝/微信商户密文 | W2 不强制已配；live 波仍用 | 既有，本波只读 |
| 中转 SKU 权益 | 记住该企业中转买没买 | 写入者扩为 `relay` **或** `plan_enterprise` 履约 | 既有，扩写点 |
| 中转产品面 | 本企业组/令牌的看与签发 | 未开通/已开通零令牌两句分家（对照） | 既有 |
| 出站拉数钥匙 | 签发只拉本企业结果的钥匙 | 查找集合收口；错平面拒绝 | 既有域，收口查找 |
| Power Market | 总开关下的目录/上架/订一行 | 侧栏货架≠治理七叶 | 既有 |
| 产品事件叶 | 追加事实，失败不挡 | 本特征增量事件名 | 既有 |
| 值班编排 | 超管单一入口看活/空/挂 | 叶子数=1；钥匙进该入口 | 既有 `/newapi` |
| 用户生命周期 | 超管停用/恢复 | 对照走完 | 既有 |
| 成员 | 本企业成员增改删 | 对照走完；禁设超管 | 既有 |
| Admin/官网壳 | 渲染、直打同形、禁四字 | 拆 BillingPanel；设置 404；联系空不展示 | 既有 |
| 网关适配叶 | HTTP 打独立 LiteLLM | **本波不改拓扑** | 既有 |

工人（Scrapy）不是本表业务模块。**不新建可部署单元。**

### 2.3 依赖图

```
官网 / Admin 壳
        │
        ▼
编排 API（不 import ORM，R7）
        │
        ├──► 【SaaS 鉴权/配额】──► 主库
        ├──► 【采集入队/结果】──► Redis ──► Scrapy Worker
        │         └──► 【产品事件】
        ├──► 【智能规划叶】──► 配额（token 闸）──► 网关适配叶（仅规划已开放）
        │         └──► 【产品事件】llm_planning_blocked
        ├──► 【收款履约】（W2 编排者）
        │         ├──► 【商户凭据】（只给通道路径验真；确认收款不读密钥）
        │         ├──► 【SaaS 配额】（写档位上限）
        │         ├──► 【中转 SKU 权益】（商品=relay 或 plan_enterprise 时写）
        │         └──► 【产品事件】
        ├──► 【出站拉数钥匙】──► 主库凭证 ──► 结果查询（只本企业非候选）
        │         └──► 【产品事件】outbound_wrong_plane_rejected
        ├──► 【中转产品面】──► 读 【中转 SKU 权益】
        │         └──► 【网关适配叶】（签发；禁 DSN）
        ├──► 【Power Market】──► 主库目录/安装
        ├──► 【成员】【用户生命周期】──► 主库
        └──► 【值班编排】──► 【网关适配叶】（管理 HTTP + 探针）
                  └──► 租户打值班 API：404 同形

通道侧 ──通知──► 【收款履约】验真端口（无 JWT）     ← W2 不作为放行；live 波
超管    ──确认──► 【收款履约】confirm 端口（JWT 超管） ← W2 合法开通
```

**无环确认**：☑ 已检查。履约写权益与配额；中转产品面只读权益。出站与渠道组互不 import。Power Market 禁止 import billing/relay/spider/llm_gateway。值班禁止服务租户 SKU。产品事件为叶子。规划叶不写订单。

### 2.4 耦合检查

| 检查项 | 结果 |
|---|---|
| 两模块共享表且都写 | 订单只收款履约写。SKU 只履约写（产品面不 activate）。出站凭证只出站域写。`api_keys` 表**不再**作为出站拉数命中集合 |
| 模块含其它模块知识 | 履约只按**商品码**分支。禁止 `if channel==wechat and plan==pro: sku=active`。出站查找禁止 `if kind==relay`——查找集合不相交 |
| 强制手段 | 目录约定 + 既有 `tools/check/arch.sh` B1–B3；本波追加 grep（实现票落地，挂 lint）：出站域禁 import `relay`/`llm_gateway`；`power_market/` 禁 `billing`/`payment`/`relay_`；`billing_service.confirm_paid` 禁调用 notify 验真函数 |

---

## 3. C4 模型

### Context

```
[访客]           ──逛官网/定价/注册──► [本系统]
[采集经办]       ──贴 URL / 规划 / 数据中心 / 出站钥匙──► [本系统]
[买方]           ──唯一结账页──► [本系统]
[租户公司管理员] ──成员/用量/渠道组/安装/结账──► [本系统]
[平台超管]       ──唯一值班入口 / 运营台确认 / 用户 / 设置 / 上架──► [本系统]
[支付宝/微信]    ──通知──► [本系统]（验真后才走通道路径；W2 不放行此边）
[LiteLLM Proxy]  ◄──管理 HTTP / 租户 chat── [本系统]（独立故障域）
[Scrapy Worker]  ◄──Redis── [本系统]
```

边界：浏览器与通道都不可信；Worker 不可信决定归属。确认收款是超管信任域内的不可逆写。Q-AGPL 已答可施工可结账 ≠ 可印「当前可买」。

### Container

```
[official :9113] ──HTTP──► [backend FastAPI :9111]
[admin :9112]    ──HTTP──► [backend]
[backend] ──SQL──► [MySQL 8]
[backend] ──队列/心跳──► [Redis]
[backend] ──管理/聊天 HTTP──► [LiteLLM 独立 compose]
[scrapy worker] ──Redis──► [backend 终态回调]
[通道] ──公网 POST──► [backend 验真入口]   （同进程、无 JWT；W2 不作为放行）
```

不拆支付微服务、不拆市场微服务（ADR-0010）。不把 litellm 写入根 compose。

### Component

见 §2.3。不画类图。

---

## 4. 可行性验证（spike）

| spike | 问题（可判真假） | 时限 | 结论 |
|---|---|---|---|
| 确认收款能否接结账单 | `confirm_paid` 是否拒绝 CHECKOUT_PRODUCTS | 读码 | **是拒绝**。W2 必须改这条边（ADR-0026），不是新系统 |
| 未配通道能否待支付 | `create_checkout` 无凭据时是否建行 | 读码 | **否**。必须改拒绝为零行 |
| 第二套故事是否仍可提交 | Usage 是否仍挂 BillingPanel | 读码 | **是**。必须拆 |
| 出站三环是否仍能用 api_keys 拉数 | `public.py` `_require_bound_tenant` | 读码 | **是**。FR-M20 必须收口 |
| 专业档执法数字 | 040 种子 vs `PRO_TIER_QUOTA` | 读码 | **不一致**。履约必须写定价页三数字 |
| 企业档是否写 SKU | `_fulfill_product` | 读码 | **否**。GWT-M11.15 必须补写点 |
| 规划未开放句 | llm_client 错误文案 | 读码 | **不是**「智能规划未开放」 |
| 数据中心空态 | `EMPTY_DATACENTER_COPY` | 读码 | **已是金标**。缺口在 101 条出文件 |
| 市场关旗 | `require_power_market_open` | 读码 | **已闸**。W5 对照走完 |

```
spike：W2 是接线还是新支付平台
问题：能否在不引入第二种主存储、不拆进程、不接 live 沙箱的前提下让买方被开通
环境：本仓库 billing_service.py + payment_notify_service.py + Usage.tsx + BillingPanel.tsx
结果：订单表、商品码、confirm 端口、notify 验真、SKU 表均已存在；
      缺的是「未配通道建 pending」「confirm 接 checkout_pending + 金额核对」
      「拆 BillingPanel」「企业档写 SKU」「配额三数字对齐」
结论：W2 是既有 billing 改编排（ADR-0026），不是新支付平台。
      2 人周预算给双轨拆除+确认收款+配额执法，禁止拿去接真收银台。
```

**无未验证技术。** 性能：入队/规划拦住 3 秒句、去结账 5 秒句都是本进程同步，距已知 p95 有余量。120 秒出数沿用夹具站点，不新开源。

---

## 5. 关键决策

| 决策 | 结论 | ADR |
|---|---|---|
| 开通何时发生 | 通道验真 **或** 超管确认本笔且金额一致；互不覆盖 | [ADR-0026](adr-0026-two-legal-fulfill-paths.md) |
| 未配通道能否下单 | 能：产生待支付，等确认 | ADR-0026 |
| 租户下单入口 | 只结账页；用量页无提交订购 | ADR-0026；无需第三份 ADR |
| 中转谁写 SKU | `relay` 履约 **或** `plan_enterprise` 履约（配额 **且** SKU=active）；`plan_pro` 永不写 | ADR-0026（点名 supersede 0024 决策 3「plan_enterprise 只开通企业档」、0025 决策 1 enterprise 档位句；0024 决策 4 凭据条款保持） |
| 出站 vs `sk-` | 两套存储两套入口；拉数查找只出站签发行 | ADR-0020 **保持** |
| 令牌怎么进网关 | 管理 HTTP，禁 DSN | ADR-0019 **保持** |
| 商户凭据 | 加密落库，确认收款**不**读密钥全文 | ADR-0024 凭据条款 **保持** |
| 值班叶子 | 用户可见=1；`/api/v1/litellm/keys` 不得再长第二菜单叶 | 无需 ADR（IA；可逆） |
| 存储 | 沿用 MySQL+Redis；不引入新主存储 | 无需 ADR |
| 拓扑 | 沿用 ADR-0010 | 不重开 |
| live / 当前可买 | 代码 FR 不替代 C2；四字绑指纹 | 禁止方案帽代开 |

---

## 6. 契约

| 契约 | 路径 | 消费方 |
|---|---|---|
| HTTP/事件（本波增量） | 本节 6.1–6.6 | `/backend` `/frontend` `/qa` |
| 数据语义 | §7 | `/dba` |

通用：Base `/api/v1`；时间 ISO 8601 UTC；集合不返回 null；业务判断用 `code` 不用 `message`；5xx 带 `trace_id`。破坏性字段并存。用户可见禁止把 `code` 渲染成内部码（X-QUOTA）。

### 6.1 错误码（本波收紧/改文案）

| HTTP | code | 语义 | 用户可见（禁止把 code 渲染给租户） |
|---|---|---|---|
| 409 | `ORDER_PENDING_EXISTS` | 同一企业同一商品已有待支付 | **「已有待支付」**（作废「已有未完成的支付」） |
| 422 | `ORDER_ROLE_NOT_ALLOWED` | 非买方建单 | 「请联系本企业管理员开通」 |
| 422 | `PLANNING_DISABLED` | 智能规划未开放时提交规划 | 「智能规划未开放」 |
| 422 | `EXPORT_ROW_LIMIT` | 导出窗 >100 条非候选 | 「单次最多导出 100 条」；**不产生文件** |
| 422 | `CONFIRM_AMOUNT_MISMATCH` | 确认金额≠结账页该商品展示 | 超管可见拒绝；租户仍见「待支付」 |
| 422 | `CONFIRM_ORDER_MISMATCH` | 确认动作提交了另一张单 | 拒绝；两单都保持待支付 |
| 422 | `RELAY_SKU_INACTIVE` | 未开通中转签发 | 「未开通中转」 |
| 409 | `MARKET_CLOSED` | 总开关关闭时订阅 | 「能力市场未开放」 |
| 404 | （无业务信封） | 租户打平台专属页 / 历史第二套钥匙地址 / 设置写面 | 与未登录打不存在页同形 |
| 禁止用户可见 | `QUOTA_EXCEEDED` / 裸 `429` / `PAYMENT_NOT_CONFIGURED` / `QUOTA_PLAN_LOCKED` / `FORBIDDEN` | X-QUOTA | 规划未开放不得用套餐超限句 |

`BILLING_CHANNELS_UNCONFIGURED`：**不再**作为「打开或提交结账失败、零新行」的 W2 语义。未配通道提交成功时 HTTP 201，message 含「收款通道未开通，提交后等待平台确认开通」。

旧 `POST /billing/orders`：不得 201 新行。可 409/422；不得改变已有结账单据。不得上报成功的 `second_checkout_story_submitted`。

### 6.2 W1 采集 / 规划 / 导出

沿用 `POST /api/v1/spiders/run`、结果列表。入队 3 秒内：已入队 **或** 工人/配额拦住句，不得停在「正在采集」。免费空企业：无「请先开通专业档」「请先订阅能力」作为提交前置。

规划：`POST /api/v1/ai/plans` 与触发规划。智能规划未开放：3 秒内「智能规划未开放」；**不**把行抢成 `planning` 再后台失败；不产生可入队方案；不创建采集任务。只读拒绝。已开放且 GWT-70.1 前置满足：只「向导进入方案与试采且列表出现该行」——禁止「已入队」「规划已受理」。失败只走既有 70.2 / 74.1 / 73.6，不另写「规划失败」。

数据中心空态 message 必须是「还没有结果，去提交采集」。导出仅 `csv`|`json`；xlsx → 可见失败、无文件。筛选结果非候选恰好 100 → 文件 100 行；101 → `EXPORT_ROW_LIMIT`、无文件。跨企业 0 行、无对方字段。

### 6.3 W2 结账 / 确认

商品码闭集：`plan_pro` | `plan_enterprise` | `relay`。通道闭集（live）：`alipay` | `wechat`。W2 提交**不要求**已选通道。

| 方法 | 路径 | 谁 | 幂等 / 语义 |
|---|---|---|---|
| GET | `/billing/checkout?product=` | 买方预览；经办/只读 → 联系管理员句，不建单 | 打开不建单 |
| POST | `/billing/checkout` body `{product, channel?}` | 仅买方 | 未配通道仍 201 `checkout_pending`；同一企业同一商品仅 1 笔待支付；重复 409「已有待支付」 |
| GET | `/billing/orders` | 本企业 | 租户可见状态映射见下；无他企 |
| POST | `/billing/orders` | 任何租户 | **不建第二套单**（GWT-M10.4） |
| POST | `/billing/orders/{id}/confirm` | 仅超管 | 本笔+金额核对 → `fulfilled`；已开通再确认 no-op；错单/错金额拒绝 |
| POST | `/billing/notify/{channel}` | **无 JWT** | 静态段先于 `/orders/{id}`（PIT-1）。W2 **不**把此边当放行。未验真不得开通 |

租户可见映射（W2 只构造前两行）：

| 内部 | 租户 | `order_status_reached.status` |
|---|---|---|
| `checkout_pending` | 待支付 | `pending` |
| `fulfilled` | 已开通 | `fulfilled` |
| `paid_pending_fulfillment` | （live；W2 不构造、不上报） | `fulfilling` |
| `unpaid` | （live；W2 不构造、不上报） | `unpaid` |

Expand-contract：读模型仍认识旧 `pending`/`paid`；**新**结账写 `checkout_pending`/`fulfilled`。运营台待确认列表必须包含 `checkout_pending`（不得只查旧 `pending`）。

并发：唯一约束（已有 `open_product_slot` 生成列）是唯一可靠防线；禁止只先查后插。冲突方 409「已有待支付」。

### 6.4 W3 出站查找收口

`GET /external/v1/public/data/{spider}`：`X-API-Key` **只**命中本企业出站钥匙表的未吊销行。渠道组 `sk-`、`/api-keys` 签发的租户 API Key、乱填、已吊销、未在「出站拉数钥匙」入口签发的凭证 → 拒绝、**0 行**（响应不含结果数组或空 items）。一次最多 100 条（GWT-M20.8）。

KEY_BINDINGS：保持 FR-13 平台绑定语义，**不得**作为租户可见第二产品名，**不得**出现在出站入口列表。平台共享 `/spider/status|results|stats` 三条不改成租户功能（ADR-0020 决策 5）。

签发/吊销沿用 `/api/v1/outbound/*`。明文只一次。页标题与菜单只「出站拉数钥匙」。历史第二套「API 钥匙」地址直打 404 同形，**不**重定向到出站页（GWT-M20.7）。

### 6.5 值班 / 设置 / 联系

超管导航值班类叶子 **恰好 1 项**（现网 label「中转站管控」可改名，但不得并存「网关钥匙」第二叶）。`/api/v1/litellm/keys` 保持超管 API；若提供签发 UI，只嵌在该唯一入口内。租户直打值班、运营台、用户管理、设置**写面**、平台 RBAC：404 同形，无渠道列表、无密钥、无「抱歉您没有权限」、无「当前账号不能改系统设置」。

`OPS.DUTY_CONTACT` 空：所有访客可达页不出现联系 CTA、不出现 `contact@localhost`、不出现「值班电话」。非空：展示该值，不声称已接通电话值班。

权限未知（`permissionsReady=false`）：「权限加载中」或读叶仍在；整站不空白；写入口不得按无权限隐藏、也不得提交成功；值班与结账在 ready 之前不可提交（GWT-M30.5）。

### 6.6 事件（至少一次，失败不挡，查询仅超管）

| event_name | 何时 | props 必有 | 禁止 |
|---|---|---|---|
| `llm_planning_blocked` | GWT-M01.1 | `tenant_id`，`reason=disabled` | 该次规划产生 `task_completed` 且 `result_count>0` |
| `data_export_completed` | GWT-M02.1 导出成功 | `tenant_id`，`file_format=csv\|json`，`row_count` | 密钥；101 拒绝出文件时不得有本事件 |
| `checkout_story_started` | 买方成功进入结账页 | `tenant_id`，`product`，`surface=checkout`，`referrer_surface=pricing\|usage\|nav` | `surface` 为 `pricing`/`usage` |
| `order_status_reached` | 待支付或已开通 | `tenant_id`，`product`，`status=pending\|fulfilled` | W2 上报 `unpaid`/`fulfilling` |
| `second_checkout_story_submitted` | 若成功产生第二套单据才计 | — | **次数必须 0**；旧入口被拒不得记成功 |
| `outbound_wrong_plane_rejected` | GWT-M20.4/5 | `tenant_id` | 凭证明文 |
| `duty_entry_opened` | 超管成功打开唯一值班入口 | `user_id` | 密钥全文；租户 404 尝试不得记成功 |
| `offline_order_confirmed` | 若确认仍用此名 | 必须能关联**同一**结账单据 | 表示第二套故事 |

Expand：`results_exported` 可与 `data_export_completed` 双写一期，查询面以新名为准。投递至少一次；分区键语义=`tenant_id`。开通本身必须精确一次（CAS/唯一约束），事件仍至少一次（ADR-0016）。

---

## 7. 数据语义诉求（给 /dba，不写表结构）

```
实体诉求：
  结账单据 —— 一行 = 一次结账意图（商品码闭集）
    需要记录：企业、商品码、金额快照（分）、状态、通道（可空——W2 未配通道）、
              商户快照（通道路径才有）、失败理由、迟到回调标记
    生命周期：无单 → checkout_pending →（确认且金额一致 | live 验真开通完成）fulfilled
              live 才构造：unpaid / paid_pending_fulfillment（本波写路径不产生）
    访问模式：按企业+商品查是否已有待支付（同时最多 1）；
              超管待确认列表必须能列出 checkout_pending（含企业名与展示金额）
              确认按主键点查，核对金额与当前价目展示

  价目 / 配额真相 —— 专业档展示与执法同一套三数字
    需要记录：专业档 cents=29900；执法 50 / 200000 / 5000000
              企业档展示金额存在且 ≠29900（确认比对用结账页数字，不用官网「定制」）
              relay 展示金额存在且 ≠29900（配置价，不进 git 明文密钥）
    生命周期：履约按商品码把配额 JSON 写到该企业；再确认不叠
    访问模式：入队/规划读该企业当前执法上限，不读「订单列表里的文案」

  中转 SKU 权益 —— 一行 = 一企业当前中转买没买
    需要记录：企业、状态 none/active/expired、账期结束
    生命周期：商品=relay 或 plan_enterprise 的开通写入 active；
              plan_pro 开通不得改此行
    访问模式：渠道组读路径按企业点查；禁止用组行 COUNT 当已买
    tenant_id NOT NULL（PIT-4）

  出站拉数钥匙 —— 一行 = 一把在出站入口签发的本企业钥匙
    需要记录：企业、hash、prefix、吊销时刻
    生命周期：签发（明文只响应一次）→ 吊销
    访问模式：拉数只查本表 active；命中集合不含 relay_tokens / api_keys
    禁止进 TENANT_EXEMPT_TABLES

约束诉求：
  同一企业同一商品同时最多 1 笔待支付 → 已有生成列唯一约束则沿用；
      禁止只先查后插（GWT-M11.12）
  确认开通同一订单只发生一次；金额不符不得 fulfilled
  专业档履约不得改中转权益
  导出/出站拉数单次最多 100 条（应用闸；超限无文件/无 101 行）
  跨租户点查 0 行 0 字段

expand-contract：
  orders.status 旧 pending/paid 读模型仍认识；新结账写 checkout_pending/fulfilled
  confirm_paid 先接 checkout_pending，再停写第二套 POST /orders
  专业档配额：履约写入定价页三数字；旧租户行不靠「改历史订单」回放
  出站查找：先拒 api_keys 命中拉数，KEY_BINDINGS 不进租户产品名
  既有 relay_groups 行不删；SKU≠active 时读路径当作不存在
```

此表须与日后 `/dba` 的 db-spec 2.1 一致。不一致以 spec §3.1 与 ADR-0026 为准，但要显式同步。本文件 **不选表名**。

---

## 8. 角色裁剪声明

| 角色 | 参与 | 理由 |
|---|---|---|
| `/dba` | 是 | 待支付列表语义、配额三数字、企业档/relay 金额≠29900、出站查找集合、SKU 写入者 |
| `/designer` | 是 | 空态金标（规划/数据中心/结账/渠道组/值班/设置 404）、拆 BillingPanel、值班单入口名 |
| `/backend` | 是 | 五波主实现 |
| `/frontend` | 是 | admin + official |
| `/sre` | 是 | C2 环境闸（非本波代码勾选）；密钥不进镜像；通知入口已有 |
| `/qa` | 是 | GWT 矩阵；跨租户；[SEC-1/2/3] |
| `/analyst` | 是 | 蓝图复盘；北极星仍是非夹具合格出数 |
| `/algo` | **N/A** | 无新模型/评分；规划叶只改未开放句 |
| `/miner` | **N/A** | 无离线建模 |
| `/data-collector` | **N/A** | 不新开采集源；夹具仍 example/httpbin |
| `/data-warehouse-engineer` | **N/A** | 数仓实现面 N/A；事件仍 OLTP |
| `/ops` | **N/A** | 值班联系已是运行配置；无 SLA 施工 |

---

## 9. Rabbit Holes

| 坑 | 为什么危险 | 边界 |
|---|---|---|
| 把 live 沙箱塞进 W2/W1 的 2 人周 | 北极星被支付拖死；杀死条件 | W2 放行不含 GWT-M11.7；无真收银台票 |
| 维持 ADR-0024 绝对句 | 确认收款永远开不了 | ADR-0026 |
| BillingPanel 当「灵活线下」保留 | D2>0；双状态词 | 拆可提交表；旧 POST 不建单 |
| 确认不核金额 / 企业档写成 ¥299 | [SEC-3] 失败 | 价目展示比对 |
| 统一出站与 `sk-` | A5 已杀 | ADR-0020 |
| 三环都当用户产品 | 查找债变三种钥匙 | 拉数只出站表；api_keys 0 行 |
| 第二套网关钥匙菜单 | 值班叶子>1 | FR-M30 |
| 设置说明态冒充 404 | GWT-M33.5 | 直打 NotFound 同形 |
| 040 种子 20 并发当专业档 | GWT-M12.6 第 6 个任务被拦 | 履约写 50/200000/5M |
| 把 `results_exported` 当 M06 完成 | 蓝图查不到新名 | 必须可查 `data_export_completed` |
| 规划未开放却抢成 planning | 经办以为在出方案 | 提交当时拒绝，不后台失败 |
| 导出 101 静默 100 行 | GWT-M02.6 失败 | 超限无文件 |
| 标 GA / 印当前可买 | X-GA / X-BUY | 机械钉 T-11 |

**「第二次出现时再抽象」**：第二种确认入口或第三种钥匙出现时再抽插件框架。本波硬编码商品码三闭集。

---

## 10. 任务拆解

一票 = 一独立可验收能力（实现+自测+交付，单会话）。每票有 FR。lane ∈ `backend`|`frontend`|`both`。W1 与 live 支付禁止排进同一 2 人周。

| 票 | 标题 | FR 锚点 | lane | wave |
|---|---|---|---|---|
| T-01 | 智能规划未开放：3 秒内金标句，不产方案、不入队、不抢成 planning | FR-M01 | both | W1 |
| T-02 | 数据中心本企业结果；CSV/JSON；100 行可出；101 可见上限且无文件；xlsx 失败 | FR-M02 | both | W1 |
| T-03 | 空免费非夹具企业第一次采集：无付费/订阅/中转前置；只读拒绝 | FR-M03 | both | W1 |
| T-04 | 超管可查 `llm_planning_blocked` 与 `data_export_completed`；失败上报不挡；租户无查询面 | FR-M06 | backend | W1 |
| T-05 | 拆用量页可提交「套餐与订购」；旧 `POST /orders` 不建第二套单；满额/去结账进同一结账页 | FR-M10 FR-M13 | both | W2 |
| T-06 | 未配通道可提交待支付；一商品一待支付（含并发）；再提交「已有待支付」 | FR-M11 | both | W2 |
| T-07 | 超管确认收款接结账单据：本笔+金额核对、不可逆、不走 FR-U38、再确认不叠；已开通后迟到通道成功通知保持已开通并记 `late_notify_at`（GWT-M11.11/18） | FR-M11 | backend | W2 |
| T-08 | 按商品码履约：专业档三数字执法；`plan_pro` 不开中转；企业档写配额且 SKU=active；`relay` 写 SKU；迟到通知不叠配额、不重签令牌（GWT-M11.11/18） | FR-M12 FR-M11 | backend | W2 |
| T-09 | 结账/我的订单租户闭集仅待支付/已开通；无取消；无「已确认」「未完成」 | FR-M10 FR-M11 FR-M15 | frontend | W2 |
| T-10 | `checkout_story_started`（surface 钉死 checkout）与 `order_status_reached`（pending/fulfilled）；第二套故事事件保持 0 | FR-M14 | backend | W2 |
| T-11 | 访客与租户可见面机械钉禁「当前可买」「支付已通」；夹具/确认≠指纹 | FR-M15 FR-M50 | frontend | W2 |
| T-12 | 出站拉数查找只认出站签发行；`sk-`/api_keys/乱填 0 行；拒绝事件无明文 | FR-M20 FR-M26 | backend | W3 |
| T-13 | 出站页只有「出站拉数钥匙」名与空态金标；第二套钥匙地址 404 同形不重定向 | FR-M20 | frontend | W3 |
| T-14 | 成员添加/改角色/移除可走完；不能设平台超管；只读写控件隐藏；跨企业 404 | FR-M21 | both | W3 |
| T-15 | 用量看板三类数字与上限；0 不是失败；将满≠已尽；只读能看不能下单 | FR-M22 | frontend | W3 |
| T-16 | 我的渠道组：未开通「未开通中转」；已开通零令牌「还没有令牌」；专业档仍未开通 | FR-M23 | both | W3 |
| T-17 | 我的安装走完；空态「还没有安装」；跨企业 404；无治理七叶 | FR-M24 | frontend | W3 |
| T-18 | 值班用户可见单一入口；平台网关钥匙只在该入口内；租户直打 404；签发≠live；`duty_entry_opened` | FR-M30 FR-M34 FR-M35 | both | W4 |
| T-19 | 运营台列出结账待支付（企业名+展示金额）并可确认；空态「暂无待确认收款」；错单/错金额拒绝 | FR-M31 | both | W4 |
| T-20 | 用户管理按登录名停用/筛选已停用/恢复；租户直打 404；种子 admin 不可删 | FR-M32 | both | W4 |
| T-21 | 值班联系空则访客页无 CTA；设置保存不谎称同步官网；租户直打设置写面 404 同形 | FR-M33 | both | W4 |
| T-22 | 租户侧栏货架+我的安装；点货架不进治理七叶；关旗「能力市场未开放」 | FR-M40 | both | W5 |
| T-23 | 超管上架/下架一行；无作者投稿入口；下架不级联删安装 | FR-M41 | both | W5 |
| T-24 | 注册主钮「创建企业」；名≥2；成功进该企业后台；无个人空间入口 | FR-M51 | both | W1 |

**并行度**：

- T-01 / T-02 / T-03 文件重叠少，W1 内可并行；T-04 依赖 T-01/T-02 事件发生点。
- T-24 与采集无代码依赖，可与 W1 并行，**计入 W1 预算外的薄对照**，但不得把人从 T-03 抽去接支付。
- **禁止** T-05…T-11 与 T-01…T-04 抢同一 2 人周。W2 在 W1 对用户可判定出数之后开工。
- T-06 与 T-07：T-07 可在 T-06 能建 pending 后接；不要先做 confirm 再发现建不了单。
- T-08 依赖 T-07 写入函数；SKU 写点与配额写点同一履约函数。GWT-M11.11/18 挂 T-07/T-08 验收（`late_notify_at`；不叠配额、不重签令牌），不是 live 波。
- T-09 依赖 T-06 的 API 形状（未配通道 201）。
- T-12 不依赖 W2 代码，但验收 GWT-M20.1 需要本企业已有结果 → **W1 之后**；可与 W2 后半并行。
- T-16 的「已开通」Given 依赖 T-08 企业档/`relay` 履约 → W3 排在 W2 之后。
- T-19 依赖 T-07 的 confirm 语义；可与 T-18 并行。
- T-22/T-23 可与 W3 后半并行，**不涨** W1 的 1.5 人周。
- 无 live 通道票。GWT-M11.7 不进本表。

**测试合同（PIT-2）**：下列金标与本波 Then 冲突，必须**同 PR** 改测试，禁止先改产品后让 CI 红当「下一步」：

- `Checkout.test.tsx` / `collectCopy.ts`：`已有未完成的支付` → `已有待支付`
- `test_fr_u30_checkout.py`：未配通道零新行 → 201 待支付
- `billing_service.confirm_paid` / `test_billing_orders_write_rules`：`ORDER_CONFIRM_OFFLINE_ONLY` 对结账单作废
- 出站 `public.py` 三环测：api_keys 命中拉数改为 0 行
- Settings 租户说明态测：改为 404 同形
- 规划测：LLM.ENABLED=false 的用户句改为「智能规划未开放」，且不留下 planning 行

**总粗估（给人周闸，不写日历日）**：

| 波 | 粗估 | 50% 停判 | 备注 |
|---|---|---|---|
| W1 | **1.5 人周** | >2.25 人周停下 | 北极星路径；**不得**把余量拿去接支付 |
| W2 | **2 人周** | >3 人周停下 | 必须功能不含 live 沙箱 |
| W3 | **1.5 人周** | >2.25 停下 | 出站收口 + 五条对照 |
| W4 | **1.5 人周** | >2.25 停下 | 单入口 + 三页 |
| W5 | **1 人周** | 不涨 W1 | 与 W3 后半可并行 |

单波校正后超该波预算 50% → 停下重判，不是自动延期。

---

## 11. 风险点（给 /qa 与 /sre）

| 风险 | 影响 | 给谁 | 建议关注 |
|---|---|---|---|
| 确认收款误开通 | 不可逆配额/SKU | `/qa` | GWT-M11.4/5/6；M31.4/5/6 金额与错单 |
| 确认后迟到通道成功通知叠配额或重签令牌 | 专业档误开中转 / 企业档令牌被重签 | `/qa` | T-07/T-08 验收 GWT-M11.11/18（记 `late_notify_at`）；不是 live 波 |
| 两套结账仍可提交 | D2>0 | `/qa` | GWT-M10.4；事件 second_*=0 |
| api_keys 仍能拉数 | [SEC-2] 护栏破 | `/qa` | GWT-M20.4/5/8 |
| 跨租户读结果/单/成员/安装 | 停发布 | `/qa` | 各 FR 越权格；404 同形不是道歉 403 |
| 规划未开放却有方案 | W1 未完成 | `/qa` | GWT-M01.1/2；无对应合格出数 |
| 导出 101 仍出文件 | NFR-M02 | `/qa` | GWT-M02.6 |
| 专业档执法仍是 20 并发 | GWT-M12.6 失败 | `/qa` | 第 6 个任务必须已入队 |
| 值班第二叶 / litellm keys 菜单 | FR-M30 | `/qa` | 导航叶子计数=1 |
| 指纹前出现「当前可买」 | 撤回文案 | `/qa` | T-11 机械钉；确认开通后定价页再扫 |
| C2 未跑却对租户称网关已开通 | FR-M34 | `/sre` `/qa` | 环境闸与代码勾选分家 |
| 改守卫不改测试 | PIT-2 CI 红或假绿 | `/backend` | 同 PR |

---

## 12. Security findings `[SEC-n]`（Q-security=yes）

Walk：`architecture/references/threat-model.md`。信任边界：浏览器、通道公网 POST、出站 `X-API-Key`、超管确认不可逆写、LiteLLM HTTP、租户 JWT。

| ID | Boundary | STRIDE | Mitigation | Downstream |
|---|---|---|---|---|
| [SEC-1] | 通道通知 `POST /billing/notify/{channel}`（无 JWT） | S/T/E：伪造成功通知开通 | 通道路径必须四要素一致且视为通道侧真通知，否则保持待支付、无 `payment_succeeded`。**不**覆盖确认收款 | NFR-M04；FR-U38；qa：缺签/金额/商户/订单号不符。W2 不放行此边，live 波必测 |
| [SEC-2] | 出站拉数 `GET /external/v1/public/data/{spider}`（`X-API-Key`） | E/I：渠道组令牌或 api_keys 拉到本企业行 | 命中集合=出站入口签发行；`sk-` / 未在该入口签发 / 他企 → 拒绝、0 行；事件无明文 | NFR-M04；FR-M20/M26；qa GWT-M20.4/5/8 |
| [SEC-3] | 超管确认收款 `POST /billing/orders/{id}/confirm` | T/E：改金额、套用 ¥299 开企业档/中转、拿 B 的单确认 A | 只能确认本笔 `checkout_pending`；金额=结账页该商品展示（专业档 29900 分；企业档/`relay` ≠29900）；不符拒绝、配额/中转不变 | NFR-M04；GWT-M11.4/15/17；GWT-M31.4/5/6；qa 错单/错金额 |

未缓解残留（写入 §11，不静默接受）：

- 通道适配器「视为真通知」的算法本波**不选**；未接 live 前 [SEC-1] 靠现有 notify 实现与 live 波复测。不能把 HMAC 夹具当指纹。
- 超管账号被盗可确认收款：残留接受原因=确认已是超管信任域；缓解=审计 `offline_order_confirmed` 关联本笔 + 不可逆提示。不把确认做成租户自助。

额外边界（有缓解、不另编号文件）：跨租户 IDOR → 404 同形 + tenant_id 过滤（各越权 GWT）。商户/上游密钥 → 不进 git、不进租户响应（NFR-M04）。LiteLLM master 不进租户复制框（ADR-0019）。

---

## 13. 变更记录

| 版本 | 日期 | 变更 | 触发者 |
|---|---|---|---|
| v1 | 2026-09-13 | 初版：读码测绘；ADR-0026；W1–W5 票表 T-01…T-24；[SEC-1..3] | define r8 PASS 进 shape |
| v1.1 | 2026-09-13 | shape r1：点名 supersede 0024 决策 3 / 0025 决策 1；0024 决策 4 保持；GWT-M11.11/18 挂 T-07/T-08，票数不增 | QA-01 / QA-05 |
