# pm memory · upgrade-four-pillars

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-12
- Hat: pm / define rework round 2
- Outputs: `01-define/spec.md` v1.2；`01-define/user-story.md`；`01-define/metrics-blueprint.md`
- Closed: QA-01…QA-12。未关 Q-AGPL。泳道 L3。
- root_cause: Checkout/fulfillment GWTs named pages not product-scoped actions: 去升级 never became a When, plan_pro success did not keep relay none, and payment_succeeded / unconfigured / forged-notify / revoke oracles were post-fulfill-only, two-When, or unconstructable.

## Facts

- 号段 **FR-U01…U38** 只追加。v1.2 新 GWT：**U23.8 / U35.5 / U35.6 / U35.7 / U37.7 / U37.8**。无新 FR。无 `plan_ent`（N/A）；企业档=`plan_enterprise`。
- 「去升级」When = GWT-U35.6 商品=`relay`；只读/经办 = U35.7。U35.1 钉 `plan_pro`。
- U33.1 Then：专业档开通 ∧ 中转 none ∧ 令牌 0 ∧ 不能当 U20.1。非法表已补 `plan_pro`→relay active。
- `payment_succeeded` 验真后、开通前可查（U37.7）。U38.3 Given = 缺通道签名的成功报文（不写算法）。
- 未配置去支付：checkout_pending → unpaid + `payment_failed` unconfigured（U32.1）。仅打开结账不建单（U32.2 / U37.8）。U23.2 只测空页；吊销令牌失败 = U23.8。
- 开通触发 = 通道通知验真通过。不选算法/表/日期。spec §6 以蓝图为准。N3 appetite **上限 8 人周**。

## Open (mine)

- Q-AGPL 仍 **待确认**（operator）：只阻塞「当前可买」，不阻塞能付施工。

## Do not re-litigate

- Q-RELAY=可买 SKU；Q-VOICE=采集；Q-PRICE=履约；Q-BILL=支付宝+微信。
- D1–D29 Accepted。无 Casbin / Stripe / new-api 运行时 / 开发者门户。
- 北极星不改订阅或支付。N1≠N3。
