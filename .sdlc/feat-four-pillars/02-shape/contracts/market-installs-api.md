# API 契约 · 租户安装（订阅）

> 上游：PRD FR-20 FR-21 FR-26 FR-29｜作者：/architect｜版本：v1｜日期：2026-09-07
> 消费方：`/backend` `/frontend` `/qa`
> 前缀：`/api/v1/tenants/me/installs`
> 守卫：`require_login` + `tenant_scope`。**不是** `require_platform_admin`。表禁止豁免。

## 角色

| 角色 | POST 订阅 | PATCH 启用/信任 | DELETE 卸载 |
|---|---|---|---|
| 经办 / 负责人（owner/admin tenant_role，且能创建任务同级） | 允许 | 允许 | 允许 |
| 只读成员 | 403「当前账号不能订阅，请联系企业管理员」；不新增行 | 403 同一文案；行不变 | 403；行仍在 |
| 未登录 | 先登录，回到详情，**尚未订阅** | — | — |
| 平台超管无企业空间 | 403「需要企业空间才能订阅」；不新增行 | — | — |
| 租户 B 改租户 A 的 id | 403；A 的行不变 | 同 | 同 |

## 宿主兼容名单（产品冻结）

| 资产上的名单 | 订阅 UI | POST |
|---|---|---|
| 未声明（空缺 / NULL） | 四个宿主均可选 | 任一成功（GWT-20.7）；第一方已发布默认走此条（FR-31.4） |
| 已声明空数组 | 四个都灰掉，「该能力不支持 {host}」 | 422「该能力不能订到 {host}」；不新增行 |
| 已声明部分 | 仅名单内可选 | 名单外 422 `host_incompat` |

租户不能改该名单。Wave 1 **无**「启用到宿主」动作；此拒绝只约束订阅记录。

## POST `/api/v1/tenants/me/installs`

```json
{ "asset_type": "skill", "name": "example-pdf-extractor", "host": "grok" }
```

`name` 可为 catalog name 或 alias。

须 `listing_state='listed'`（**不是** coming_soon）+ 发布态 + 许可闸或 override。

成功：200/201 一行：`enabled=true`，`trusted=false`。同一能力同一宿主已存在存活行 → **200 返回已有行**（幂等，不新增）。

订到第二宿主 → **新增一行**，不覆盖第一行的启用/信任（GWT-20.9）。

| 拒绝 | HTTP | 订阅拒绝原因（事件） |
|---|---|---|
| 预告 | 422 | `coming_soon` |
| 未上架 / 公开闸失败 | 422 或 404 | `unlisted` |
| 许可未过闸 | 422 | `license` |
| 未登录走了 API | 401 | `auth` |
| 宿主不兼容 | 422 | `host_incompat` |
| 只读 | 403 | `readonly` |

预告详情无订阅主按钮；旁注「尚未上架」。

## GET `/api/v1/tenants/me/installs`

`host?` 可选。本租户 SQL `tenant_id=?`。空：`items: []`（前端「还没有订阅的能力」）。

列表 JOIN 当前资产 title/listing；已下架行标记 `listing_state` 供「已下架」展示。**不**把黑名单资产的公开正文带给未持有者——持有安装的租户可在「我的安装」看到行以便卸载。

## PATCH `/api/v1/tenants/me/installs/{id}`

`{enabled?, trusted?}`。仅本租户行。

- 开信任必须请求带确认字段或二次 POST；未确认保持 `trusted=false`（GWT-21.3）。
- **不**写回资产行的上架/信任。
- 资产已黑名单：不可改启用、不可改信任，**可卸载**（GWT-29.3/29.4）。PATCH → 422/403，值保持。

## DELETE `/api/v1/tenants/me/installs/{id}`

软删。商店若仍 listed 可再订。卸载 **不**把能力下架。黑名单行仍可卸载。

## 订阅不占三类配额

用量 API 不因安装行变化。
