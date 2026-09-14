# architect memory · upgrade-four-pillars

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-12
- Hat: shape（FR>20 → 合同+ADR+票表，无 tickets/T-nn.md）
- Outputs: `02-shape/contract.md` v1；`adr-0024-notify-driven-checkout.md`；`adr-0025-relay-sku-entitlement.md`

## Facts

- 泳道 L3。票 T-01…T-27。N1≠N3 同一 2 人周。N2 无 N1 代码依赖，N1 开工后可并行。
- 读码：`billing` 在创建前拒绝 alipay/wechat；`POWER_MARKET.ENABLED` 不闸订阅；`relay_service` 无 SKU；`is_internal_fixture` 0 命中；值班只有 empty/degrade。
- 履约=验真后通知（ADR-0024）。凭据=LLM 保险库同级。不把通道 SDK 当模块名。
- 中转已买=权益不是组行（ADR-0025）。`plan_pro` 不得把 SKU 置 active。
- 商品码闭集 `plan_pro`/`plan_enterprise`/`relay`。无 `plan_ent`。
- N1 结账路由只允许「收款通道未开通」空态。
- PIT-1 通知静态段先于 `/orders/{id}`。PIT-2 改 billing 测同 PR。PIT-3/4 凭据无租户列、令牌 NOT NULL。
- 事件新增 `task_blocked`；`payment_succeeded` 验真后即可查。

## Open (mine)

- 验真算法仍不选（FR-U38）。适配器无法「视为通道侧真通知」则 N3 不能完成。
- Q-AGPL 仍待确认；本帽只守四字禁令。

## Do not re-litigate

Q-RELAY/VOICE/PRICE/BILL；D1–D29；ADR-0010 拆市场微服务；Casbin/Stripe/new-api 运行时；N1 接真通道；口头可买=当前可买；明文商户密钥；GWT-07.3 合并句禁渠道组页。
