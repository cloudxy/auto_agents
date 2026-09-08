# dba memory · feat-four-pillars-v2

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-08
- Hat: 定义 / dba 诊断
- Outputs: `.sdlc/feat-four-pillars-v2/01-define/diagnosis/dba.md`

## Facts

- Alembic 单头 **027**（32 revision 线性）。0 个 `*.dbml`。`env.py` 未开 `compare_type`。
- 幽灵 pyc 仍在且无 `.py`：028 `api_keys`、029 billing/subscriptions、030 last_login + `uq_spider_results_tenant_spider_hash`；models `api_key.pyc`/`billing.pyc`。禁止复活。
- `TENANT_EXEMPT_TABLES` 仍无 `capability_assets`（有 `tenant_id` 恒 NULL、非 Mixin）。R13 不扫该洞。
- 017：`spider_results.tenant_id` NOT NULL。024 已种子 `tenants.slug=platform`。
- 入队门面/调度/模板仍丢 `tenant_id`。配额 COUNT 不排除 `source=marketplace`。出站 `query_public_results` 无租户。
- 现 `ASSET_TYPES` = skill/plugin/expert/expert_team。目标五类 + `capability_commands`。不 rename `capability_experts`。
- `source_type VARCHAR(16)` 装不下 `marketplace_crawled`(20)。
- Redis 月度 field 写 `{dim}|total` 无租户；公开 INCR/EXPIRE 非原子。
- 占位租户默认 `platform`。出站钥匙 v1 配置绑定，不建表。

## Open (mine)

- Q-PLACE：占位=platform 还是单独 inbound 租户
- Q-LISTED-AT：unlist 是否清空 listed_at（默认不清）
- Q-IDEM：product_events 是否 UNIQUE 幂等键（默认不要）
- Q2 writable 窗口；Q6 origin_ref 256 vs 512；Q7 结果 hash UNIQUE（勿用 030）
- 脏库是否 stamp 过 028–030 → sre

## Do not re-litigate

- 不改 `uq_asset_type_name_alive`；skills.name 不补 alive_flag
- unlist 后安装保留；订插件不级联安装行
- 候选不迁表、禁止 NULL tenant_id
- 禁手写 Alembic SQL；禁 MySQL ENUM
- Q-BILL 未决 → 不建 billing
- host_compat：NULL=四宿主可订，[]=都不可订
