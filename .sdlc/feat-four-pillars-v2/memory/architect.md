# architect memory · feat-four-pillars-v2

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-08
- Hat: 定义（诊断 + Q-LLM 替换方案；未写 contract）
- Outputs: `01-define/diagnosis/architect.md`；`01-define/diagnosis/litellm-replace-newapi.md`

## Facts

- Q-LLM **已决**：LiteLLM = LLM 数据面；new-api **退出运行时**。禁止再标待确认。
- 规划器零引用 `NewapiApiClient`。`llm_chat` 已是 OpenAI `/chat/completions`。套餐闸仍未接线。
- LiteLLM 现网 ≠ 运行时：仅 `deploy/litellm/config.gen.yaml` git 跟踪明文 Key（7 处）；`services/litellm/` 仅 pyc；exporter 脚本不在树。
- new-api：独立 compose；调度 **DSN+logs SQL**；探针打 `/v1/chat/completions`；值班 `/newapi` + `require_admin`。
- 目标：独立 `deploy/litellm` + 自有 PG（禁并根 compose、禁网关 DSN）。BYOK 直连。短双跑后停 new-api。
- Wave L 第一等（FR-70…建议），**禁止**塞 Wave 3 stub。Wave 0 只做 FR-14 离树 + 收权 + FR-12 闸。
- 旧 ADR-0014「替换不进本特征」OVERTURN；KEEP：`llm_chat` 单入口、闸在前、mcp 仅验证、伪装不熔断。

## Open (mine)

- 塑形：重写 ADR-0014；B4 扩 `litellm_*`/`relay_*`；`gateway_ref` expand 交 `/dba`；镜像 tag 交 `/sre`。
- 值班 URL `/newapi` 保留一周期（b1c 锁信封）。
- 不代选 Q-VOICE/PRICE/RELAY/MARKET-USER/BILL/AGPL。

## Do not re-litigate

- 拆市场微服务；LiteLLM 并进根 compose；网关 DB_DSN；resume litellm pyc；Q-CAND NULL；Q-LLM 再开放；Wave L=FR-60。
