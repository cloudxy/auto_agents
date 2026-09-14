# ADR-0026：两条合法开通；确认收款是第二条路径；未配通道仍可待支付

> 状态：**accepted**
> 日期：2026-09-13｜决策者：architect 帽｜相关：spec v1.7 FR-M10…M15、FR-M31、NFR-M04 [SEC-1]/[SEC-3]；`02-shape/contract.md`
> 本 ADR **supersede** [ADR-0024](../../upgrade-four-pillars/02-shape/adr-0024-notify-driven-checkout.md) 决策 1 的绝对句、决策 2、决策 5，以及 **决策 3 中「`plan_enterprise` 只开通企业档」**：企业档履约写企业档配额 **且** 中转 SKU=active。
> 本 ADR **supersede** [ADR-0025](../../upgrade-four-pillars/02-shape/adr-0025-relay-sku-entitlement.md) **决策 1 中「采集套餐档位（free/pro/enterprise）不是该权益」** 对企业档的绝对句：`plan_enterprise` **要**写 `relay_sku_entitlements`；`plan_pro` **仍不得**写。决策 1 其余（权益独立生命周期、仅履约模块写入、组行≠已买）仍有效。
> **ADR-0024 决策 4 保持对齐**（不 supersede）：商户凭据仅超管可配可轮换、加密落库、与 LLM 密钥同级、不把通道 SDK 当架构选型。
> ADR-0024 决策 3 其余仍有效：`plan_pro` 只开通专业档；`relay` 只把中转 SKU 置 active；禁止一份成功通知改另一商品；通道路径仍须验真后开通。
> ADR-0024 其余：通道闭集支付宝/微信、未验真通道通知不得开通、expand-contract 旧 status。
> ADR-0025 其余：权益与组行分家、`plan_pro` 不得把中转置 active、值班页对租户 404 同形、令牌 `tenant_id` NOT NULL。

## 背景

ADR-0024 把「可履约的支付成功」钉成**仅**验真后的通道通知，并写「线下 `confirm_paid` 不得再给租户可见的专业/企业/中转当成功路径」；两通道未配时打开结账**不建单**。合入后定义波（spec v1.7）冻结：W2 必须功能=能下单、能见状态、能被开通，**不要求 live 沙箱**；超管确认收款是**第二条合法开通**，不走 FR-U38。GWT-U32.2 / 「无验真一律不得开通」已被 FR-M11 supersede。

现码（`feat/litellm-l1` × `origin/main`，`1db6a47`）：`create_checkout` 在两通道未配时 422 零新行；`confirm_paid` 对 `product_code ∈ CHECKOUT_PRODUCTS` 抛 `ORDER_CONFIRM_OFFLINE_ONLY`；用量页仍挂 `BillingPanel` 走 `POST /billing/orders`。按 ADR-0024 施工会让 W2 无法被开通。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 两条合法开通互不覆盖 | spec X-FULFILL；FR-M11 |
| 通道路径未验真不得开通 | FR-U38；ADR-0024 仍约束**通道**边 |
| 确认收款不走 FR-U38；金额=结账页该商品展示 | FR-M11 [SEC-3]；GWT-M11.4/15/17；GWT-M31.4/6 |
| 两通道未配仍可产生待支付 | GWT-M11.1（GWT-U32.2 已作废） |
| 租户只一条结账故事 | X-STORY；FR-M10 |
| `plan_pro` 开通后中转仍未开通 | X-RELAY-ENT；GWT-M12.4 |
| 企业档或 `relay` 确认后中转已开通 | GWT-M11.15/17；GWT-M12.5 |
| W2 不构造 `unpaid` / 不开 live 沙箱 | spec §0.4.1；appetite |

## 决策

1. **开通有且仅有两条合法边，按触发源分平面，禁止用一条的绝对句否决另一条。**
   - **通道路径**：`POST /billing/notify/{channel}` 无 JWT。四要素（本笔订单号、商户、金额、视为通道侧真通知）缺一 → 保持待支付，无 `payment_succeeded`，不得 `fulfilled`。[SEC-1] 只约束这条边。
   - **确认收款路径**：平台超管 `POST /billing/orders/{id}/confirm`。不要求通道验真、不要求通道已配置。必须：目标行是**本笔** `checkout_pending`；`amount_cents` 与**结账页该商品当前展示金额**一致（专业档=定价页 ¥299=29900 分；企业档/`relay` **不得**为 29900 分）。不符 → 拒绝，单据保持待支付，配额/中转不变。[SEC-3]
2. **两通道均未配置**：结账页仍可提交开通，产生一张 `checkout_pending`；用户可见「收款通道未开通，提交后等待平台确认开通」。**禁止**因此写 `unpaid`，禁止服务器错误页。W2 不提供取消入口，不把该单流转为 `unpaid`。
3. **租户可见 W2 闭集**仅「待支付」(`checkout_pending`) / 「已开通」(`fulfilled`)。超管动作名可以是「确认收款」；租户订单列表不得写「已确认」。同一企业同一商品同时最多 1 笔待支付（含并发）；再提交只见「已有待支付」，禁止「已有未完成的支付」。
4. **按商品码写副作用（确认收款与通道路径开通完成共用同一写入函数，禁止第二套 if）：**
   - `plan_pro`：配额执法改为专业档三数字（50 并发 / 200,000 条 / 500 万 tokens/月，与定价页同一套）。中转 SKU **保持 none**，令牌数不因本单增加。
   - `plan_enterprise`：写入企业档配额（不得套用专业档 ¥299 与专业档三数字）；**同时**把中转 SKU 置 active（企业档履约能力）。此条 **supersede** ADR-0024 决策 3「plan_enterprise 只开通企业档」与 ADR-0025 决策 1「采集套餐档位 enterprise 不是该权益」。
   - `relay`：只把中转 SKU 置 active；若开通前为免费档，并发/存储/tokens **仍为免费三数字**。
5. **租户可见下单只走结账页。** `POST /billing/orders`（用量页 BillingPanel）不得再产生第二套单据；已有结账单据不变。超管确认只挂在结账单据上。
6. **HMAC / `signed_body` 夹具、确认收款、待支付都不是 live 支付通道指纹。** 不得因此印「当前可买」或「支付已通」。C2 真网关轮仍是环境闸，不是本 ADR 的完成条件。

**明确不在本 ADR：** 通道验真算法/SDK 名称（仍不选）；退款/发票/取消；live 波的 `unpaid` / `paid_pending_fulfillment` 租户可见态。

## 备选与否决理由

### 备选 A：维持 ADR-0024「无通道验真不得开通」（含确认收款）

W2 两通道未配时无人能被开通；北极星旁的驱动 D1 永远停在 pending。spec 已把「无验真一律不得开通」标为 superseded。

**否决理由**：GWT-M11.4 Then 明确不走 FR-U38；X-FULFILL 禁止用通道绝对句否决确认收款。

### 备选 B：维持「两通道未配 → 不建单」（ADR-0024 决策 2 / 旧 GWT-U32.2）

买方提交开通得到 422「收款通道未开通」且零行，运营台无待确认。

**否决理由**：GWT-M11.1 要求产生租户可见「待支付」；GWT-U32.2 已作废。

### 备选 C：用量页 BillingPanel 线下单与结账页长期并存，确认只接旧 `pending`

现码即此。租户看见两套入口、两套状态词；`second_checkout_story_submitted` 无法保持 0。

**否决理由**：X-STORY；FR-M10；蓝图 D2 红线=0。

### 备选 D：`plan_pro` 确认后顺带开通中转

少一次下单。与「渠道组是企业档履约、不是专业赠品」冲突。

**否决理由**：GWT-M12.4 / X-RELAY-ENT。专业档开通后打开渠道组必须「未开通中转」。

### 备选 E：确认收款不核对金额、或允许把企业档/`relay` 写成 ¥299

运营省一步。伪造或改行即可用专业档价开通企业档/中转。

**否决理由**：GWT-M31.4 / M31.6 [SEC-3]；NFR-M04。

### 备选 F：把 live 沙箱/真收银台并进 W2 同一 2 人周

一次做完「能付」。与杀死条件冲突。

**否决理由**：briefing 方案 C 已否；W1 与 live 支付不得同一 2 人周；GWT-M11.7 不是 W2 放行条件。

### 备选 G：维持 ADR-0024 决策 3「plan_enterprise 只开通企业档」（履约不写 SKU）

企业档只改套餐行，中转另买 `relay`。GWT-M11.15 / M12.5 / M23.1 的 Given 将无法由企业档确认收款构造。

**否决理由**（rejected）：spec GWT-M11.15 Then 钉死确认企业档后中转已开通能力具备。企业档履约必须写企业档配额 **且** SKU=active。

### 备选 H：维持 ADR-0025 决策 1「采集套餐档位 enterprise 不是该权益」

把 SKU 写入锁死在 `product=relay` ∧ FR-U38。确认收款开通企业档后渠道组仍「未开通中转」。

**否决理由**（rejected）：X-RELAY-ENT 否决的是专业档赠中转，不是企业档。`plan_enterprise` **要**写 `relay_sku_entitlements`；`plan_pro` 仍不得写（备选 D 已否决）。

## 证据

```
读码：backend/services/billing_service.py
  preview_checkout：两通道未配 → empty_state，can_pay=false，不建单
  create_checkout：if not configured → 422 BILLING_CHANNELS_UNCONFIGURED，零新行
  confirm_paid：product_code in CHECKOUT_PRODUCTS or channel in alipay/wechat
                → ORDER_CONFIRM_OFFLINE_ONLY
  CHECKOUT_PENDING_EXISTS_USER = "已有未完成的支付"
读码：frontend/admin/src/pages/Usage.tsx 挂载 BillingPanel
读码：frontend/admin/src/components/usage/BillingPanel.tsx
  标题「套餐与订购」；createOrder → POST /billing/orders
读码：backend/services/payment_notify_service.py
  _fulfill_product：relay → activate SKU；plan_* → _apply_plan；
  plan_enterprise 不写 SKU（与 GWT-M11.15 缺口）
读码：backend/alembic/versions/040_billing_and_relay_sku.py
  pro quota_json = 20/500000/5000000，与定价页 50/200000/5000000 不一致
读码：frontend/shared/src/constants/quota.ts
  PRO_TIER_QUOTA = 50 / 200000 / 5000000（spec FR-M12 金标）
```

无新存储引擎。确认收款与建单都是本进程同步写主库，距 NFR-M01「去结账 5 秒内」有余量。

## 代价与风险

| 代价 | 缓解措施 |
|---|---|
| 确认收款可在无通道时开通，运营误点会成真开通 | [SEC-3] 金额+本笔；再确认 no-op 不叠配额（GWT-M11.5）；不可逆，无取消 |
| 通道路径与确认路径两套入口 | 写入函数按商品码唯一；GWT-M11.11/18 挂 T-07/T-08 验收（记 `late_notify_at`；不叠配额、不重签令牌），不是 live 波 |
| 旧 `POST /orders` 与测试金标作废 | expand：先拒建第二套单；同 PR 改 `test_fr_u30_*` / `test_billing_orders_write_rules` / Checkout.test（PIT-2） |
| 企业档官网文案「定制」无数字 | 确认比对**结账页展示金额**（价目行），不是官网营销句 |
| live 波仍要接通道 | 本 ADR 不删 notify 验真；W2 不构造 unpaid |

**最终一致三问（确认收款路径）**：无异步窗口——确认成功的响应时单据已是已开通、配额已按商品码执法。期间用户若未刷新，仍可见待支付，直到下次读。发现金额不符：保持待支付，不对账成已开通。

**通道路径最终一致**仍走 ADR-0024（验真到开通完成的处理中态是 **live 波**才构造；W2 不上报 `fulfilling`/`unpaid`）。

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/backend` | 未配通道可建 `checkout_pending`；`confirm_paid` 接结账单据+[SEC-3]；按商品码写配额/SKU；拒 `POST /orders` 第二套单；事件名见合同 §6 |
| `dba` | 待支付列表含 `checkout_pending`；专业档配额与定价页三数字对齐；企业档价目行 cents≠29900；不写表名以外的新存储 |
| `/frontend` | 拆 BillingPanel；结账闭集两态；「已有待支付」；未配通道可提交 |
| `/qa` | W2 放行串按 spec；禁止再用 U32.2/U30.2/「无验真不得开通」覆盖确认收款 |
| `/sre` | 本波不把通道通知当 W2 放行；密钥仍不进镜像 |

## 后续复审条件

live 支付通道指纹出现后，复审租户是否仍只需确认收款、以及是否对访客印「当前可买」（仍禁止本 ADR 代开四字）。出现退款/取消需求时另写 ADR，不在本决策加 `fulfilled → unpaid`。若企业档改为「不含中转」的新商品，另写 ADR，禁止在履约里写 `if product==plan_pro: sku=active`。

---

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-13 | proposed → accepted | post-merge-upgrade 塑形；消化 spec v1.7 X-FULFILL |
| 2026-09-13 | accepted（shape r1） | 点名 supersede 0024 决策 3「plan_enterprise 只开通企业档」、0025 决策 1 enterprise 档位句；0024 决策 4 保持；GWT-M11.11/18 挂 T-07/T-08 |
