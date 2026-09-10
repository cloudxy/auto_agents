# 事件契约 · 市场发现与订阅（FR-30）

> 上游：PRD FR-30、`metrics-blueprint.md` §5｜作者：/architect｜版本：v1｜日期：2026-09-07
> 消费方：`/backend` `/frontend` `/qa` `/analyst`
> 与 Wave 0 共用同一查询面（ADR-0016）。失败不挡主路径。

## 投递

至少一次；幂等键见各事件。分区键建议 `tenant_id`（可空则 `anonymous_id`）。无全局顺序。

## 事件清单

| event | 何时 | 关键字段 | 幂等键建议 |
|---|---|---|---|
| `market_list_viewed` | 打开市场列表 | 筛选：类型/宿主/分类 | 会话+时间窗（允许重复浏览） |
| `market_search_submitted` | 搜索完成（含 0 结果） | `q`、`result_count` | — |
| `market_detail_viewed` | 打开详情 | `asset_type`、`listing_state`、`name` | — |
| `market_subscribe_succeeded` | 订阅成功 | `host`、`asset_type`、`name`、`tenant_id` | install 行 id |
| `market_subscribe_rejected` | 订阅被拒 | `host`、`reason`：`coming_soon` / `unlisted` / `license` / `auth` / `host_incompat` / `readonly` | — |
| `market_uninstalled` | 卸载 | `host`、`tenant_id` | — |
| `market_listing_changed` | 超管改上架 | 旧态/新态、`asset_type`、`name`、actor | — |
| `market_source_sync_completed` | 同步结束 | 成功数/失败数、`source_name` | job_id |

搜索 0 结果：仍有 `market_search_submitted`，`result_count=0`。

租户 A 订阅成功后，租户 B 查事件看不到 A 的订阅细节。

查询面同 `product-events.md`（`event_name` 过滤）。
