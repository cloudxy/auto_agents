# API 契约 · 能力市场公开面

> 上游：PRD FR-13 FR-17 FR-18 FR-19 FR-28 FR-31 FR-32 FR-33…36｜作者：/architect｜版本：v1.1｜日期：2026-09-07
> 消费方：`/backend` `/frontend`（official）`/qa`
> 官网新 UI **只打** 本文件路径，不得再调 `/public/skills` 作为主数据源。

## 公开闸（必须在 SQL 内完成后再分页）

同时满足才出现在列表/详情：

1. `listing_state IN ('listed', 'coming_soon')`
2. `status IN ('stable', 'recommended')`（对用户：已发布 / 推荐）
3. `COALESCE(license,'') NOT IN blocklist OR public_license_override=1`  
   默认黑名单：`UNLICENSED`、`LicenseRef-Moonshot-AI-Skill`
4. 不是 `status=blacklist`（即使误标 listed → 公开当不存在）

`UNLISTABLE_PACKAGES`（`dev-team`）不得 listed/coming_soon；防御性：公开仍不出现。

失败不得装空：列表接口 5xx/网络失败 → 前端「市场列表加载失败」+ 重试，**禁止**「暂无已发布」。

## GET `/api/v1/public/capabilities`

鉴权：无。IP 限流（复用 `skill:public:rl:` 前缀；INCR+EXPIRE 原子 pipeline）。

查询：

| 参数 | 说明 |
|---|---|
| `type` | `skill` / `plugin` / `command` / `agent` / `team`（旧值 `expert`→`agent`、`expert_team`→`team` 只读别名一个发布周期） |
| `q` | 匹配 `name`、`title`、`origin_local_name`（短名）；过长截断并提示 |
| `host` | 可选；`JSON_CONTAINS` 过滤，无函数索引 |
| `category` | 可选 |
| `page` / `page_size` | 默认 20，最大 50 |

200：

```json
{
  "items": [
    {
      "asset_type": "skill",
      "name": "mattpocock-skills__code-review",
      "title": "Code Review",
      "origin_local_name": "code-review",
      "listing_state": "listed",
      "installable": true,
      "license": "MIT",
      "origin_plugin": "mattpocock-skills"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

| 字段 | 可空 | 说明 |
|---|---|---|
| `listing_state` | 否 | 只会出现 `listed` / `coming_soon`（闸后） |
| `installable` | 否 | `listing_state==listed` 且过许可/治理；预告为 false |
| `file_path` | — | **永不返回** |
| `items` | 否 | 空目录 `[]`，配合前端「还没有上架的能力」 |

筛选 0 条 vs 目录空：前端用「是否带 q/type 筛选」区分文案（FR-28.2）。接口都返回 `items:[]` + `total:0`。

`installable` 不表示「已在宿主运行」。

## GET `/api/v1/public/capabilities/{asset_type}/{name_or_slug}`

先查存活 alias slug（且 `asset_type` 匹配），否则 catalog `name`。闸门失败 → **404 `NOT_FOUND`**，与不存在相同；**不**回「已被拉黑/未上架」。

正文：`body_text` 为纯文本（FR-32）。含 `<script>` 的源文以文本出现；响应 `Content-Type` 为 JSON，前端按文本节点渲染，不得 `dangerouslySetInnerHTML`。

无正文：`body_text: ""`，前端「暂无说明」。

白名单不得含 `file_path`、本机绝对路径、`verify_detail` 内部栈。

## GET `/api/v1/public/skills`

**Deprecated。** 实现内部转调 `type=skill`。官网新页禁止调用。

## 首页精选（FR-01.4）

首页技能/能力精选依赖本列表。失败时该区块「技能列表加载失败」+ 重试，**禁止**空白或「还没有技能」。其余静态区可继续显示。
