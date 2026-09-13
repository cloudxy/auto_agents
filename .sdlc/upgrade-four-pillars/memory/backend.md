# backend memory · upgrade-four-pillars

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-13
- Hat: backend (T-26 rework 1 · QA-03/04/05)
- Outputs: `.sdlc/upgrade-four-pillars/03-impl/T-26-evidence.md`

## Facts

- 值班 `GET /api/v1/newapi/overview`：`duty_page_state` empty|degrade|live 互斥。空句仅 0 模型。降级句管理面不可达。活：可达 + ≥1 模型 + 该行探针 original。第四态：可达 + ≥1 模型 + 无 original → `duty_page_state is None`，empty/degrade 句均为 null，行不标活（勿塌成空句）。
- 降级若出现 model 行：`clear_duty_row`，禁止 `duty_row_status=live`。降级不调用 `latest_result_per_channel`；本地 24h 事件/批次仍回。
- 探针查询收口：`latest_result_per_channel(channel_ids, since)`。无 channel_ids 不 execute。总览传入当前 gateway_ref→id 集合 + 24h `created_at` + LIMIT。
- 行匹配仍按 channel_id / scores._gateway_ref / model 名。活 ≠ SKU active。
- 租户打 `/newapi/*` 仍 `require_platform_admin_or_404`，404 同形。未租户化 LiteLLM admin。
- 伪装不关渠：GWT-07.6。
- 测试：`test_fr_u25_duty` 10 passed。

## Open (mine)

- 响应 expand 了 `duty_page_state` / `duty_row_status`（已报 architect/frontend T-27）。

## Do not re-litigate

- 不改 GWT / schema 046。
- 可见面不写「当前可买」。
- 不把网关 Admin UI 做成租户菜单。
- 不重开 N1–N3。不弱化 GWT-U25.3。
