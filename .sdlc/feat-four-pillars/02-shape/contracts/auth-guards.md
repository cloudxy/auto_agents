# API 契约 · 鉴权守卫与平台写面

> 上游：PRD FR-06 FR-07 NFR-05｜作者：/architect｜版本：v1｜日期：2026-09-07
> 消费方：`/backend` `/frontend` `/qa`
> 相关：ADR-0017

## 守卫映射

| 守卫 | 含义 | Wave 0/1 用于 |
|---|---|---|
| `require_login` | 任意已登录 | 管理目录读、插件详情读 |
| `require_admin` | `users.role==admin`（**含租户公司管理员**） | **禁止**再用于平台目录写 / 渠道写 / 平台 LLM 写 |
| `require_platform_admin` | `is_platform_admin` | 扫描/验证/源/上架/许可放行/渠道窗口/平台供应商写 |
| `require_tenant_manager` | `tenant_role in (owner, admin)` | 成员、用量、租户自有 LLM 行 |
| `require_login` + `tenant_scope` | 有企业空间的登录者 | 安装 API；只读角色在资源层再拒写 |

## 写面变更（相对今日）

| 方法 | 路径 | 今日 | 目标 |
|---|---|---|---|
| POST | `/api/v1/capabilities/scan-plugins` | `require_login` | `require_platform_admin` |
| POST | `/api/v1/capabilities/plugins/{name}/verify` | `require_login` | `require_platform_admin` |
| POST | `/api/v1/capabilities/scan-experts` | `require_login` | `require_platform_admin` |
| POST | `/api/v1/capabilities/teams` | `require_login` | `require_platform_admin` |
| POST | `/api/v1/skills/scan` 及 import/sync/candidates 写 | `require_admin` | `require_platform_admin` |
| PUT/DELETE | `/api/v1/newapi/channels/{id}/config` | `require_admin` | `require_platform_admin` |
| POST/PUT/DELETE/activate | `/api/v1/llm/providers*` **平台行** | `require_admin` | `require_platform_admin` |
| POST/PUT/DELETE/activate | `/api/v1/llm/providers*` **本租户行** | `require_admin` | `require_tenant_manager`（保持租户 BYOK） |

拒绝时：资源不变 + `record_audit` 记越权尝试。HTTP 403 `FORBIDDEN_SCOPE`，message「需要平台管理员权限」（目录/渠道写）。

## 渠道/中转页对租户（GWT-07.3）

| 角色 | 导航 | 直打 `/newapi` 及子路径 |
|---|---|---|
| 平台超管 | 可见 | 200，可读写（写走超管守卫） |
| 租户公司管理员 / 经办 / 只读 | **不出现** | **与「页面不存在」相同**：不展示渠道数据、不是道歉式 403、不回工作台道歉页 |
| 匿名 | 后台本就跳登录 | — |

管理面不可达时（超管）：降级说明「管理面不可达，本地记录仍可看」；改额度提交失败弹窗不关、额度保持原值（GWT-07.2）。

## 登录投影（T-04）

`POST /api/v1/auth/login` 与后续 `/me` 必须带：

| 字段 | 类型 | 说明 |
|---|---|---|
| `is_platform_admin` | bool | 必返，默认 false |
| `role` | string | 已有 |
| `tenant_role` | string \| null | 已有 |
| `tenant_id` | int \| null | 超管可 null |

前端不得再用 `role==='admin'` 当作平台超管。

## 测试合同（必与实现同 PR）

- `test_b1c`：viewer 扫描 **403**，不再 200。
- 租户 JWT `role=admin` 调 scan-plugins / 改渠道额度 / 激活平台 LLM 行 → 403，行不变，有审计。
- 超管同样动作 → 200 且落库。
