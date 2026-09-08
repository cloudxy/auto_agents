# miner memory · feat-four-pillars-v2

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-08
- Hat: 定义 / 只读复审（不训练）
- Outputs: `.sdlc/feat-four-pillars-v2/01-define/diagnosis/miner.md`

## Facts

- 本程序模型面 = **N/A**。不上流失/分群/异常/LTR。旧 spec「离线模型下一轮」保持。
- 本机 OLTP 2026-09-08：tenants=4 全 active、expires 全 NULL；users=6；tasks=0；results=0；llm_token_usage=0；probe/events=0；orders=0。skill_jobs=9 done。operation_logs=627 无 tenant_id/无登录。
- 鉴权不读 `tenants.status`。`test_expired_tenant_login_rejected` 不 POST /login。`TenantExpiryService` 未挂 lifespan。expired ≠ 不能用。
- `users.last_login_at`：库有、ORM/登录 0 写入、1/6 非空。来自幽灵 030 pyc（git 无 .py）。不算登录事实。
- 本机 `alembic_version=030`；工作树 versions 无 028/029/030 .py。多出 plans(2 SKU)/orders(0)/tenant_subscriptions(0)/api_keys(0)。禁止当付费金标。
- `check_llm_tokens_month` 仅测试；用量页 `utcnow` ≠ 上海日。429 不落事件。
- 质量公式/REQUIRED 死配置/`"{}"` content/代理 0.5 vs 0.2/listing 0 命中：相对旧 miner 未修。
- 无 sklearn、无 dwd_/metrics.yaml、无 FR-15 事件名命中。

## Open (mine)

- Q2/Q13：活跃事件=登录还是任务？到期拒登？未答则 churn 标签禁写。
- Q3/Q7：触达动作与分群策略套数未定。
- Q8：登录/配额事件表（幽灵列不算）。
- Q9：生产 n 未知；本机不够撑 K。
- Q14：stamp 030 幽灵表如何处置 → dba。

## Do not re-litigate

- 不训练、不引入 ML 包、不在 OLTP `fit`。
- 不用 quality_score / verdict / status=expired / last_login_at / 幽灵 orders 当 y。
- WACT 是分析北极星不是 churn。
- 规则基线先修缺陷，不转成「质量模型」票。
