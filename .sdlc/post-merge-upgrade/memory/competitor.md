# competitor memory · post-merge-upgrade

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-13
- Hat: competitor
- Outputs: `.sdlc/post-merge-upgrade/00-discover/compete.md`

## Facts

- 泳道 L3。交付快照（非 signals 全量 battlecard）。现状=合入后半成品（`1db6a47` feat/litellm-l1 并 origin/main）。
- 本变更粒=双轨收口 vs 下一波可判定，不是四柱并集。关账三特征=有条件放行非 GA。
- 双轨 E2：BillingPanel（`/billing/orders`+confirm_paid）与 Checkout（ADR-0024）同挂；拉数三环 outbound_keys→api_keys→KEY_BINDINGS；`/litellm` admin keys 与租户 `/relay` 签发并存。CONTEXT 仍写「令牌不发给租户」。
- 环境闸 C2–C5 未跑。`POWER_MARKET.ENABLED`/`LITELLM.*.ENABLED` 默认关。禁「当前可买」机械钉仍绿。
- 直接：LiteLLM 操作者 Key（文档 200）；New API 令牌店 AGPLv3（本仓 README E2，运行时退役）。间接：Dify/Crawlab/Apify。标杆 Casbin/Ory 本波回避。替代：Excel/自建 Scrapy/BYOK/不用我们。
- 总判：收双轨+诚实半成品。借「一条对外故事」+ `/key/generate` 边界。不借充值码/Stripe/Admin UI 租户化/工程托管。ADR-0020 分平面强化。Q-AGPL 未关不得写当前可买。

## Open (mine)

- Q-AGPL 挡「当前可买」；竞品有店 ≠ 可印该四字。
- Q-PRICE：双轨像两种收费故事；不代选哪条 API 留下。
- Q-MARKET-USER 若改作者投稿，市场回避表重开。
- Q-RELAY 上带已选 SKU；本快照不重开、也不写成可印当前可买。

## Do not re-litigate

- D1–D29；new-api 不回运行时；ADR-0020 出站≠sk-；404 同形；不写 FR/RICE；不代关 Q-*。
