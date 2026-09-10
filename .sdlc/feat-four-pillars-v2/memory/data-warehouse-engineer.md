# data-warehouse-engineer memory · feat-four-pillars-v2

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-08
- Hat: 定义（诊断 fan-out）
- Outputs: `.sdlc/feat-four-pillars-v2/01-define/diagnosis/warehouse.md`

## Facts

- 实现面 **显式 N/A**：本程序不建 `ods_`/`dwd_`/`dws_`/`ads_`，不写现行 `metrics.yaml`，不写 ETL。L4 数据线本程序 = OLTP 产品事件（dba/backend）+ 四周 analyst 复盘。塑形/实现帽应 `roles_skipped: data-warehouse-engineer`。
- 2026-09-08 现树四零：无分层表、无 `metrics.yaml`、无血缘、无产品事件 SDK。Alembic 头仍 027。`listing_state` / `capability_installs` / `POWER_MARKET` 0 命中。
- 伪仓：`llm_token_usage`（配额 ADD upsert）≠ DWS；`archive_records`（无生产写入）≠ ODS；`/admin/stats` ≠ ADS。同实例 MySQL 8，无 OLAP。
- 禁止把 grok `four-pillars-diagnosis-and-plan.md` §3.10 候选表抄进 v2 spec（第二套口径 = 红线）。旧 warehouse 已收回 `FR-WH-*`。
- 输入层已关、仓遵守：WACT 北极星；上海日；排除字段名 `is_marketplace_candidate`（旧 Q-W1）；护栏以蓝图为准（旧 Q-W2）。Q-VOICE 仍开，禁止双北极星。
- 仍存活在线债（非仓票）：D1 全历史成功率；D3 `datetime.now()` naive；D6 配额 COUNT 不过滤 marketplace；D7 月 Redis 写 `{dim}|total` 无租户。
- `capability_assets.tenant_id` 恒 NULL 未进 `TENANT_EXEMPT_TABLES`。P-WH-01：仓 SQL 禁 `NULLS LAST`。
- 旧 ADR-0016 / T-13：事件进 OLTP、票明确不做数仓——是输入材料，不是 v2 现行合同。存储形状 → architect/dba；仓约束：可按 `occurred_at` 查，禁 Redis TTL / operation_logs / notifications 当事实源。

## Open (mine)

- Q-WH-STORE：事件落点形状（不选，只约束）
- Q-WH-INTERNAL：内部租户手工名单
- Q-WH-RECON：软删 vs 事件 result_count 对账（另程序）
- Q-WH-LLM：ADD upsert 是否改幂等快照
- Q-WH-OLAP：同实例→OLAP 阈值
- Q-VOICE：核心动作变更则改 `wact`，不双星

## Do not re-litigate

- 本程序建仓 / 写 yaml / 发明 FR-WH-* / 抄 §3.10 表
- 用任务表冒充 WACT 验收
- 时区、北极星名、候选字段名（输入已冻）
