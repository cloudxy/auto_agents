# 事件契约 · 获客与激活漏斗（FR-15）

> 上游：PRD FR-15、`metrics-blueprint.md` §5｜作者：/architect｜版本：v1｜日期：2026-09-07
> 消费方：`/backend` `/frontend` `/qa` `/analyst`
> architect **不改** 事件名与口径。

## 投递

| 项 | 约定 |
|---|---|
| 投递语义 | 至少一次；消费方按 `(event_name, idempotency_key)` 或插入失败可忽略 |
| 顺序 | 无全局顺序；乱序用 `occurred_at` |
| 形态 | 状态传递（载荷带分析所需字段，查询面不必回查业务表才能验收） |
| 失败 | **不得**挡主路径 |
| 查询 | 平台超管 `GET /api/v1/admin/product-events?event_name=&from=&to=&page=` |
| 时区 | `occurred_at` UTC；报表日 Asia/Shanghai |

## 事件清单（Wave 0）

最低集：`occurred_at`；已登录时 `tenant_id`/`user_id`；匿名 `anonymous_id`。

| event | 何时 | 关键字段 |
|---|---|---|
| `official_page_viewed` | 打开首页/定价/市场/注册 | `page`：`home` / `pricing` / `market` / `register` |
| `official_cta_clicked` | 点主按钮 | `cta`：`register_free` / `pricing_pro` / `pricing_enterprise` / `login` / `browse_market` **分档不得合并** |
| `tenant_signup_succeeded` | 企业开通成功 | `tenant_id` |
| `login_succeeded` | 登录成功 | **必须** `tenant_id` |
| `login_failed` | 登录失败 | `reason`：`credential` / `expired` / `locked`；**不含密码**；能消歧到企业时带 `tenant_id` |
| `task_run_submitted` | 提交采集 | `tenant_id`、`spider` |
| `task_completed` | 任务完成 | `tenant_id`、`result_count`、`spider`、`source`、`is_marketplace_candidate`（布尔；候选入站=true） |
| `results_exported` | 导出成功 | `format`、`row_count`、`tenant_id` |
| `quota_exceeded` | 配额拒绝 | `dimension`：`concurrency` / `storage` / `llm_tokens`、`tenant_id` |

WACT 用 `is_marketplace_candidate=false` 且 `result_count>0` 排除候选，不得靠事后猜。

## 查询 API

```
GET /api/v1/admin/product-events
```

守卫：`require_platform_admin`。

查询参数：`event_name`、`from`、`to`（ISO）、`tenant_id`（可选）、`page`、`page_size`。

200：`{ items: [...], total, page, page_size }`。`items` 空时 `[]`。

租户成员调此接口 → 403。租户 B 不得在任何查询面看到租户 A 的用户级事件。

## 空态

访客打开定价未点击：有 `official_page_viewed`（page=pricing），**没有** `official_cta_clicked`。
