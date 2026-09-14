# frontend memory · upgrade-four-pillars

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-13
- Hat: frontend (T-27 rework 1 · QA-01/QA-02)
- Outputs: `.sdlc/upgrade-four-pillars/03-impl/T-27-evidence.md`

## Facts

- 屏 19 锁句：`DUTY_EMPTY_71_2` / `DUTY_DEGRADE_71_3` / `DUTY_LIVE` / `DUTY_LOAD_FAILED`。禁渲染「暂无渠道」。禁「当前可买」。
- `resolveDutyBanner`：loading/error → hasLiveRow(live) → duty_page_state → degrade → empty → ok。有活行压过 empty/degrade（含 T-26 `duty_page_state=empty`）。
- 行「活」= `gatewayAvailable && (API live ∨ 本地 original)`。降级禁止标活。消费 `duty_page_state` / `duty_row_status*`。
- 租户 `/newapi` 仍 MainLayout 404 同形（GWT-U25.3）。值班「活」≠ SKU active。Q-OPS-DUTY 无 SLA 数字。
- 验证：Overview3q 14 + NewApiOps 15 + App.menu 14 = 43 passed；`frontend.sh` 0；Overview3q 354 行。
- T-19/T-20/T-21 仍有效：结账 GET+POST；SKU 闸；定价去结账。

## Open (mine)

- 无。QA-03/04/05 属 backend。取消支付/pay_url 仍无 T-16。

## Do not re-litigate

- Q-AGPL：不写「当前可买」。
- 关闭句≠空货架句；租户货架≠上架治理 404。
- Hero 第一句仍采集（T-06）。
- P-FE-03 空权限缓存；P-FE-08 antd `title`/`orientation`/`destroyOnHidden`。
- 不重开 N1–N3。不改 GWT。
