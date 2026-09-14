# ADR-0024：在线履约只认验真后的通道通知；商户凭据加密落库

> 状态：**accepted**
> 日期：2026-09-12｜决策者：architect 帽｜相关：spec FR-U30…U38、NFR-U04、`02-shape/contract.md`

## 背景

v2 把支付宝/微信做成骨架：`PaymentProvider` 在 `alipay`/`wechat` 上抛「在线支付尚未开通」，租户下单被 `_assert_order_allowed` 在**创建前**拦下，零新行。超管 `confirm_paid` 是线下挂账的履约口。操作者已关 Q-BILL=支付宝+微信、Q-PRICE=履约。若继续用「创建即开通」或「超管点确认当支付成功」，会把伪造回调和代付写进产品。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 可履约的支付成功 = 商户+金额+订单号一致且视为通道侧真通知 | FR-U38 [SEC-1] |
| 未验真不得开通、不得出现 `payment_succeeded` | FR-U33 / FR-U37 / NFR-U04 |
| 商户密钥不进 git、不进默认配置明文、不进任何浏览器全文 | FR-U31；A5 |
| 超管无企业空间时不能代付 | FR-U36 |
| 迟到成功回调不开通 | GWT-U34.4 |
| 通道闭集支付宝+微信；不把通道 SDK 写成产品 | Q-BILL；本 ADR 纪律 |
| 现网 LLM 密钥已是「主密钥在环境变量、密文落库、读回掩码」 | `LlmSecretVault` |

## 决策

1. **履约驱动 = 验真通过的通道通知**，不是下单、不是前端回跳、不是超管 `confirm_paid`。验真四要素（订单号、商户、金额、视为通道侧真通知）缺一则单据保持未开通。
2. **租户结账只创建待支付**（`checkout_pending`）。通道未配置：选择该通道并去支付 → 先有待支付再 `unpaid` + `payment_failed reason=unconfigured`；仅打开结账且两通道均未配 → **不**建单。
3. **开通在验真之后**：验真通过先可查 `payment_succeeded`，开通未完成时单据为 `paid_pending_fulfillment`，租户见「支付已到账，开通处理中」。开通按**商品码**执行：`plan_pro` 只开通专业档；`plan_enterprise` 只开通企业档；`relay` 只把中转 SKU 置 active。禁止一份成功通知改另一商品。
4. **商户凭据**仅超管可配、可轮换；落库加密，与现网 LLM 密钥**同级**（同一保险库家族：主密钥只在环境/运行配置，密文入库，读回只掩码，未配主密钥则拒绝保存明文）。本 ADR **不**把某一通道 SDK 名称当成架构选型。
5. **线下 `confirm_paid` 不得再给本波租户可见的专业/企业/中转履约当成功路径。** 存量 `pending` 线下单可继续人工处理，但不作为 GWT-U33/U38 的 Then。
6. **破坏性字段走 expand-contract**：既有订单 `status=pending/paid/cancelled` 与本波 `checkout_pending/unpaid/paid_pending_fulfillment/fulfilled` 并存映射，读模型同时认识旧值；商品码新列可空一期，新结账必填。禁止一刀改枚举让旧测试/旧行全部失败却不改合同。

## 备选与否决理由

> **这一节是 ADR 的全部价值。** 只写「我们决定用 X」的 ADR 等于没写。

### 备选 A：前端回跳 / 查单轮询当履约

浏览器带回的「支付成功」可被伪造或提前。FR-U38 要求视为**通道侧**真通知。回跳只用于把人带回本站看单据状态。

**否决理由**：GWT-U38.3 缺通道签名的成功报文不得开通；回跳没有这四要素。

### 备选 B：超管 `POST /billing/orders/{id}/confirm` 当在线履约

**否决理由**：FR-U36 禁止超管代付；confirm 不是通道通知。若把 confirm 接到 `plan_pro`/`relay`，护栏「未验真不开通」失败。

### 备选 C：商户号/密钥写入仓库 yml 或默认配置明文

**否决理由**：A5 已杀死；NFR-U04 / FR-U31.4 仓库跟踪文件无密钥全文。与 LLM 密钥纪律相反。

### 备选 D：创建待支付即开通 / 前端拿到 checkout 链接即标已买

**否决理由**：GWT-U32.1 未配通道也会先有 `checkout_pending`；GWT-U34.1 取消必须未开通。创建≠验真。

### 备选 E：引入闭集以外的通道（含把某一国际卡组织当默认）

**否决理由**：spec §5 通道闭集；Q-BILL 已答支付宝+微信。

### 备选 F：把某通道官方 SDK 名称写进产品合同当「架构」

**否决理由**：spawn 纪律与 FR-U38「不选验真算法、不选密钥格式、不选回调路径」。产品面是通道码 `alipay`/`wechat` + 验真端口；适配器可替换，SDK 名不是模块名。

## 证据

```
读码：backend/services/payment_provider.py
  UnconfiguredOnlineProvider.collect → BusinessException PAYMENT_NOT_CONFIGURED
读码：backend/services/billing_service.py
  _assert_order_allowed：alipay/wechat 在创建前拒绝，零新行
  confirm_paid：超管 pending→paid 并 _apply_plan
读码：backend/app/api/v1/billing.py
  POST /orders/{order_id}/confirm = require_platform_admin
读码：backend/services/llm_secret_vault.py
  未配主密钥拒绝明文入库；读回解密失败当缺失
读码：platform_core/models/billing.py
  Order.status pending/paid/cancelled；channel offline/alipay/wechat
  Plan 种子仅 free / pro（无 enterprise slug；无独立 relay 商品列）
```

无新存储引擎 spike。性能：点去支付 5 秒内见通道或空态（NFR-U01）落在本进程 HTTP，距已知 p95 有余量。

## 代价与风险

**我们接受的代价**（诚实列出，不要只写好处）：

| 代价 | 缓解措施 |
|---|---|
| 最终一致：验真通过到开通完成有窗口 | 窗口内用户见「支付已到账，开通处理中」；档位/SKU 仍是开通前；`payment_succeeded` 已可查（GWT-U37.7） |
| 重复通知 | 同一待支付只开通一次（GWT-U33.6）；消费幂等键=本笔订单号 |
| 迟到成功回调 | 已 `unpaid` 保持 unpaid，记「迟到回调」，不开通（GWT-U34.4） |
| 线下 confirm 与在线履约并存一期 | 租户可见升级出口不再走线下创建；confirm 不勾 N3 GWT |
| 适配器要接真通道 | 未配通道必须人话空态，不是 500（FR-U32） |

**选最终一致时三问**：可接受延迟=开通处理完成前（无日历 SLA）；期间用户看到开通前数字+处理中句；发现不一致用超管查询面按订单号对账（`payment_succeeded` 有、档位未变 → 开通失败，不靠用户口头）。

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/backend` | 拆「创建待支付 / 验真 / 开通」；通知入口无租户 JWT；PIT-2：与 `test_billing_orders_write_rules` 同 PR |
| `dba` | 数据语义见 `contract.md` §7；expand-contract 旧 status；商品码与套餐行分家 |
| `/sre` | 公开通知 URL、不把密钥打进镜像、通道失败与验真失败可观测 |
| `/qa` | 必测：缺签名/金额不符/商户不符/订单号不符/迟到回调/重复通知；未配通道；买方 vs 经办 |
| `/frontend` | 回跳只展示单据；禁止用回跳参数改档位 |

## 后续复审条件

Q-AGPL 关闭且要对外写收费故事时，复审可见文案（仍禁止本 ADR 去关那一问）。出现退款/发票需求时另写 ADR，不在本决策里加反向 `fulfilled → unpaid`。通道适配器无法满足「视为通道侧真通知」时停下，不降级成查单轮询履约。

---

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-12 | proposed → accepted | 塑形初版 |
