# API 契约 · 能力市场治理台

> 上游：PRD FR-06 FR-22 FR-23 FR-25 FR-27｜作者：/architect｜版本：v1｜日期：2026-09-07
> 消费方：`/backend` `/frontend`（admin）`/qa`
> 写守卫：一律 `require_platform_admin`（D14）。读：`require_login`。
> 静态前缀路由必须注册在 `GET /{asset_type}/{name}` 之前。

## 源

### GET `/api/v1/capabilities/sources`

登录可读。返回源列表（name/type/uri 脱敏为非家目录展示策略：管理详情 **不** 把可展开的本机绝对路径当复制字段给非超管——Wave 0 已去 `file_path`；源 uri 仅超管）。

### POST `/api/v1/capabilities/sources`

超管。`{name, type, uri, ref?, skip?, enabled?}`

| 错误 | HTTP | code |
|---|---|---|
| `type=url` | 422 | `LISTING_DENIED` 或 `INVALID_PARAM` field=type |
| uri 逃逸 / 不在允许前缀（local_dir/kimi_home） | 422 | `INVALID_PARAM` field=uri |
| git https/ssh | 允许 | — |
| git `file://` 走与 local_dir 相同前缀检查 | 422 if 失败 | `INVALID_PARAM` |

### PATCH `/api/v1/capabilities/sources/{name}`

不可改 `name`/`type`。config_owned 行改 uri：409 提示改 yml，或允许但下次启动被覆盖——实现选一种并写进 OpenAPI 描述。

### POST `/api/v1/capabilities/sources/{name}/sync`

超管。返回 `{job_id, total, succeeded, failed, missing}`。同步 **不得** 把未上架改成已上架/预告。新第三方包 `listing_state=unlisted`。源不可读：该源 `last_error`，其它源不受影响；已上架商店不清空。

空目录：「没有可同步的包」可行动空态，不是假成功。

### GET `/api/v1/capabilities/sources/{name}`

详情 + 最近 20 jobs（`skill_jobs.source_id`）。

## 上架

### PATCH `/api/v1/capabilities/{asset_type}/{name}/listing`

`{listing_state: unlisted|listed|coming_soon}`

| 场景 | HTTP | code |
|---|---|---|
| 租户公司管理员 | 403 | `FORBIDDEN_SCOPE`；上架态不变；审计 |
| `name ∈ UNLISTABLE_PACKAGES` 且目标 listed/coming_soon | 422 | `LISTING_DENIED`；旁注「已合并，不可上架」 |
| listed + 当前 status=blacklist | 422 | `LISTING_DENIED` |
| 成功 | 200 | 审计 `asset.list` |

## 许可放行

### PATCH `/api/v1/capabilities/{asset_type}/{name}/license-override`

仅超管。`{public_license_override: bool}`。审计 `asset.license_override`。租户 403。

## 别名

### PUT `/api/v1/capabilities/{asset_type}/{name}/aliases`

`{slugs: ["code-review"]}`

与存活 alias **或** 任意存活 `capability_assets.name` 冲突 → **409** `ALIAS_CONFLICT`。两条公开地址都不被静默改写。同步不自动生成。

## 组件

### GET `/api/v1/capabilities/plugins/{name}/components`

登录。bundled children。商店投影只出已上架子资产（公开面另滤）。

## 管理详情

### GET `/api/v1/capabilities/{asset_type}/{name}`

登录可读。**白名单去掉 `file_path`**（FR-13）。可含 listing_state、source_name、origin_local_name、license、health_status、writable。

## 扫描回退（D16）

`POST /scan-plugins`：若 `POWER_MARKET.ENABLED=false` 或无 enabled 源或调用方测试传了 root= → 今日 `LIBRARY_ROOT/plugins` 遍历，**不**插入 `library_plugins` 源行。守卫已是超管。

## `dev-team`

listing PATCH 422；sync 保持 unlisted。管理端目录仍可见磁盘索引。
