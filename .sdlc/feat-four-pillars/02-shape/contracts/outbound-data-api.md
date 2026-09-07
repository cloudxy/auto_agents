# API 契约 · 出站拉数（无绑定则拒绝）

> 上游：PRD GWT-08.4 FR-08｜作者：/architect｜版本：v1｜日期：2026-09-07
> 消费方：`/backend` `/qa` `/dba`（绑定语义）
> Wave 0 **只冻拒绝**。租户自助钥匙 = FR-52，不在本波。

## 接口

```
GET /external/v1/data/{spider_name}
```

头：`X-API-Key` 必填。

### 今日

空 `EXTERNAL_API.API_KEYS` → 全部 401（保持）。非空字符串列表命中后 `query_public_results` **无租户参数**，可混拉两家企业。

### 目标（GWT-08.4）

| 钥匙状态 | 行为 |
|---|---|
| 未配置 / 不匹配 | 401，响应不含任何结果行（保持） |
| 命中但 **未绑定单一企业** | **拒绝**（401 或 403 `FORBIDDEN_SCOPE`）；响应 **不含** 任何租户的行；不得把两家企业结果混在一次响应里 |
| 命中且绑定 tenant_id=T | 只返回 T 的行；且排除 `source=marketplace` |
| 空名单 | 继续全部拒绝 |

绑定表达（给 /dba / 实现，不写表）：配置必须能表示「这把钥匙 → 恰好一个 tenant_id」。旧字符串列表在 expand 期视为 **未绑定** → 走拒绝，而不是「全平台后门」。这是有意行为收紧。

### 错误

| 场景 | HTTP | code |
|---|---|---|
| 无 Key / 错 Key | 401 | `UNAUTHENTICATED` |
| Key 有效但未绑定租户 | 403 | `FORBIDDEN_SCOPE`（message 不泄露其他租户存在） |
| 绑定租户无此爬虫数据 | 200 | `items: []` |

空名单时继续全部拒绝（与今日默认一致）。
