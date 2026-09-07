# API 契约 · 通用约定

> 上游：PRD v1.3｜作者：/architect｜版本：v1｜日期：2026-09-07
> 消费方：`/backend` `/frontend` `/qa`
> **契约先行**：本文件定稿后实现角色可并行。字段名与 `/dba` 落库名若不同，实现映射表必须写在 PR 里。

## 通用约定

| 项 | 约定 |
|---|---|
| Base path | `/api/v1`（外部拉数 `/external/v1`） |
| 认证 | 管理/租户：`Authorization: Bearer <token>`。公开商店：无鉴权 + IP 限流。出站拉数：`X-API-Key` |
| 时间格式 | ISO 8601 UTC（`2026-09-07T14:30:00Z`）；纯日期 `2026-09-07`。业务切日 = **Asia/Shanghai**（FR-16） |
| 字符编码 | UTF-8 |
| 集合类字段 | **永不返回 null**，用 `[]` / `{}` |
| 未知字段 | 客户端必须容忍（服务端可新增字段） |
| trace_id | 5xx 响应必带 |
| 信封 | 既有 `ok` / `paginated` 信封保持；本文用业务 `data` 形状描述 |
| 词表 | 对用户禁止：技能广场、能力广场、资产目录、`listing_state` 英文、`QUOTA_EXCEEDED`、仓库路径。对用户说：**能力市场**、未上架/已上架/预告 |

## 错误码清单

业务判断用稳定的 `code` 字符串。**`message` 是给人看的，前端不许用它做逻辑判断。**

| HTTP | code | 语义 | 前端处理建议 |
|---|---|---|---|
| 400 | `INVALID_PARAM` | 参数校验失败，含 `field` | 高亮对应字段 |
| 401 | `UNAUTHENTICATED` | 未登录或 token 过期 | 跳登录 |
| 403 | `FORBIDDEN_SCOPE` | 权限不足（需要平台管理员 / 需要企业空间 / 请联系企业管理员） | 按 message 展示；**渠道页不要用这个当「页面」**（直打同 404） |
| 404 | `NOT_FOUND` | 资源不存在；未上架/黑名单公开详情；租户直打渠道页 | 与「页面不存在」相同 |
| 409 | `ALIAS_CONFLICT` | 别名与存活目录名或别名冲突 | 提示改 slug |
| 422 | `LISTING_DENIED` | denylist / listed+blacklist / 预告不可订 / 宿主不兼容 | 旁注已合并或尚未上架或不支持该宿主 |
| 422 | `ROW_LIMIT_EXCEEDED` | 导出超 100 条 | 提示缩小范围 |
| 429 | `QUOTA_EXCEEDED` | **协议层保留**；**用户可见层禁止渲染该字样**（FR-12） | 用 `detail.dimension` 分流文案 |
| 429 | `RATE_LIMITED` | 公开 API 限流，`Retry-After` | 退避 |
| 500 | `INTERNAL_ERROR` | 含 `trace_id` | 稍后重试 |
| 503 | `DEPENDENCY_DOWN` | 含 `detail.service`（如 new-api） | 降级说明 |

错误响应：

```json
{
  "code": "FORBIDDEN_SCOPE",
  "message": "需要平台管理员权限",
  "field": null,
  "detail": {},
  "trace_id": "abc123"
}
```

## 分页约定

| 项 | 值 |
|---|---|
| 方式 | offset（沿用现公开/管理列表） |
| 参数 | `page` + `page_size` |
| 默认页大小 | 20 |
| 最大页大小 | 公开市场 **50**（NFR-02）；管理列表 100；导出 100 |
| 返回 total | 是（现信封）；公开列表 total 必须是 **闸门后** 的库内计数，禁止页内过滤后 `len(items)` |

## 幂等约定

| 操作 | 幂等 | 保证方式 |
|---|---|---|
| GET | 天然 | — |
| POST 订阅 | **需要** | 业务键 `(tenant_id, asset_id, host, alive)`；重复返回 **已有行 200**，不新增 |
| POST 源同步 | 可重复跑 | 幂等 upsert；不覆盖 listing |
| POST 注册 | 重复企业失败 | 现有校验 |

## 版本策略

| 变更类型 | 处理 |
|---|---|
| 新增可选请求/响应字段/错误码 | 直接加 |
| 删除或重命名字段 | 字段并存 → 客户端迁移 → Deprecated 下线日期 |
| `GET /public/skills` | **deprecated**：内部转调 `type=skill` 的 capabilities；官网新 UI 不得再调 |

## 宿主枚举

`grok` / `zcode` / `kimi` / `claude`（API 小写）。对用户展示：Grok / ZCode / Kimi / Claude。
