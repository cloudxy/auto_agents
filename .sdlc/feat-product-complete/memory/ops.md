# ops memory · feat-product-complete

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-10
- Hat: signals
- Outputs: `01-define/requirement-pool.md` · `01-define/feedback-digest.md`

## Facts

- 生产工单=0。活体 9111/9112/9113 在听；LiteLLM 4000 healthy。
- `GET /api/v1/billing/plans` 200：free + pro（29900，is_public=1）。官网 Pricing 专业档仍「预告不可购买」。Usage 同时有「本波不提供自助」与「提交升级订单」。
- `GET /api/v1/public/capabilities` total=400 全 `nfr01qc2-*` skill；plugin/command/agent/team total=0。官网列表无翻页。
- 出站 `/external/v1/public/data/example` 401。OpenAPI 无租户出站钥匙。
- Relay API 在；`relay_service` 不打网关库；`used_tokens` 无写入。
- 容器内 DEEPSEEK/MOONSHOT/OPENAI key EMPTY。`LLM.ENABLED`/`POWER_MARKET.ENABLED` false。
- git ahead 7（含 018c369、d7a6f78）。`alembic current` 打印 039，同时 plans 活体存在 → 已转 /sre。
- 代码已关勿再开票：IM-17/19、C35-QA-03/04。IM-04/05 现网已过、账本仍 open。
- 仍开测试债：IM-02/03/12/13/18/26、C35-QA-05。
- CONTEXT.md:48-50 仍写令牌不发给租户。
- 已兑勿再报：Hero 大数、Excel、注册主钮去登录、满额不到注册、伪装不熔断、单一市场导航。

## Open (mine)

- 无。开放五问属操作者，不代选。

## Do not re-litigate

- Q-LLM / Q-BILL / Q-RELAY / Q-OPS-DUTY
- 四柱 GA；litellm 焊根 compose
- 把 工单=0 写成「没问题」
- 把日历「一次做完」当 RICE
