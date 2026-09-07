# API 契约 · 配额、隔离、用量、导出

> 上游：PRD FR-03 FR-08 FR-09 FR-10 FR-11 FR-12 FR-16｜作者：/architect｜版本：v1｜日期：2026-09-07
> 消费方：`/backend` `/frontend` `/qa`

## 入队

所有产任务路径必须把 `tenant_id` 传入 `SpiderTaskService.enqueue`（含门面转发）：

| 路径 | tenant_id 来源 |
|---|---|
| `POST /api/v1/spiders/run` | 已有：`user.tenant_id`（保持） |
| 调度到期 `_fire` | `SpiderSchedule.tenant_id` |
| `create_task_from_template` | 模板行 `tenant_id`（与当前用户企业一致；跨租户 403） |
| AI 试采 `_execute_test` | 规划行 `tenant_id` / 当前用户 |

`tenant_id` 缺失时：**拒绝入队**（真库 NOT NULL）。不得插入无主任务。并发配额在 `tenant_id is not None` 时检查（修转发后闸才生效）。

## 结果存储配额（FR-11）

`check_result_storage` COUNT 谓词必须排除市场候选：

- 计入：`tenant_id=? AND (source IS NULL OR source <> 'marketplace')`
- 不计入：`source='marketplace'`

租户「我的结果」/ 数据中心 / 导出同一谓词。超管候选审核：`source='marketplace'` SQL 分页，禁止全表进 Python。

## LLM 月度配额（FR-10）

在 `llm_chat` 调用模型 **之前** 调 `QuotaService.check_llm_tokens_month(tenant_id, year_month)`。

- `year_month` = Asia/Shanghai 日历月 `YYYY-MM`，禁止 `datetime.utcnow()`。
- 无租户上下文（平台内部）跳过套餐闸，与并发闸对称。
- 市场验证抽样若走模型，同样过闸。
- 套餐未尽而 provider 预算尽：不得展示 `QUOTA_EXCEEDED` 字样（ADR-0014）。

## 用量 API（FR-12 / FR-16）

`GET /api/v1/tenants/me/usage`

响应（在既有三条进度上扩展，前端可算百分比但后端应给数字）：

```json
{
  "timezone": "Asia/Shanghai",
  "year_month": "2026-09",
  "dimensions": [
    {
      "key": "concurrency",
      "used": 2,
      "limit": 5,
      "percent": 40,
      "warn_level": "ok"
    }
  ]
}
```

| `warn_level` | 条件 | 用户文案（前端） | 主按钮 |
|---|---|---|---|
| `ok` | <70% | 无警告 | — |
| `warn` | 70–89% | 「已用 {p}%」+ 维度名 | — |
| `critical` | 90–99% | 「已用 {p}%，接近上限」 | 存储→去结果库；Token/并发→申请提升配额 |
| `full` | used≥limit 或刚被拒 | FR-12.2 全文；**禁止** `QUOTA_EXCEEDED` / `429` 字样 | 同上 |

超管无租户上下文打开用量：不是「暂无用量数据」，而是「用量属于企业空间」+ 去平台运营（GWT-12.3）。前端路由已 `tenantOnly` 的，补空态文案。

`quota_exceeded` 事件：`dimension` ∈ `concurrency` / `storage` / `llm_tokens`。

## 导出（FR-03）

`GET /api/v1/spiders/results/{task_id}/export?format=csv|json`

| 规则 | 行为 |
|---|---|
| 格式 | 只允许 csv/json；xlsx → 400，UI **不出现** Excel |
| 条数 | 单次最多 **100** 条；按钮/说明写明。0 条 → 提示「没有可导出的结果」，不生成空文件 |
| 跨租户 | 403；审计；A 得不到 B 的文件 |
| 候选 | 导出不得包含 `source=marketplace` 行 |

## 仪表盘窗口（FR-16）

「近 7 日」与「本月」必须标明时区 Asia/Shanghai。成功率与结果条数若并列，必须同一时间窗，或明确标不同窗。超管卡标明「平台合计」；租户标明「本企业」。
