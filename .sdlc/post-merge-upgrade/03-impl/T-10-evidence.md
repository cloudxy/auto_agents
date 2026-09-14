# 实现证据 · T-10 结账故事事件

> 票：T-10｜FR 锚点：FR-M14｜角色：/backend｜日期：2026-09-13

## 1. 契约落位表

| 事件 | 何时 | props |
|---|---|---|
| `checkout_story_started` | 买方 GET `/billing/checkout` 成功 | tenant_id, product, surface=checkout, referrer_surface |
| `order_status_reached` | 建 pending / 确认 fulfilled | status=pending\|fulfilled |
| `second_checkout_story_submitted` | 不报成功 | 次数 0 |

`referrer_surface` 查询参数：pricing\|usage\|nav（缺省 nav）。

## 6. 自测

Green：`test_fr_m14_checkout_events.py` 4 passed。全量 1808 passed exit 0。

| GWT | 测试 | 结果 |
|---|---|---|
| M14.1 | 定价来源 + pending | ✅ surface 钉死 checkout |
| M14.2 | fulfilled；无 unpaid/fulfilling | ✅ |
| M14.3 | 旧 POST 不记第二套成功 | ✅ |
| M14.5 | usage referrer | ✅ |

查询面仍仅超管 404 同形（既有）。
