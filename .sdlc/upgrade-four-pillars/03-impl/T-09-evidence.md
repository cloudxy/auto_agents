# 实现证据 · T-09 公司管理员打上架/扫描/平台渠道/RBAC = 404 同形

> 票：`02-shape/contract.md` §10 T-09｜FR 锚点：FR-U12 FR-U15｜角色：/backend｜日期：2026-09-12

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 上架 PATCH listing | Router | `capabilities.py` | `require_platform_admin_or_404` |
| 扫描 scan-plugins/experts/skills/scan；源列表 | Router | `capabilities.py` / `skills.py` | 同上；部门仍 `require_admin` |
| 平台渠道写 | Router | `newapi.py` | GET 本已 404；写面改 404 同形 |
| 平台 RBAC 列表/保存 | Router | `rbac.py` GET/PUT `/roles` 等 | 超管仍可 list/save |
| 越权留痕 | Router 守卫 | `require_platform_admin_or_404` | `authz.denied`；HTTP_404 Not Found |
| 权限判定 | **未削弱** `require_platform_admin` | `deps.py` 本体 403 仍在 | 本票只换挂 _or_404；verify/correct/license 仍 403 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/app/api/v1/capabilities.py` | 修改 | listing/scan/sources → `_or_404` |
| `backend/app/api/v1/skills.py` | 修改 | `/scan` → `_or_404` |
| `backend/app/api/v1/newapi.py` | 修改 | 写面 → `_or_404` |
| `backend/app/api/v1/rbac.py` | 修改 | roles/permissions/menus → `_or_404`；departments 仍 admin |
| `backend/tests/test_fr_u12_u15_rbac.py` | 新增 | GWT-U12/U15 |
| PIT-2 测 | 修改 | b1c / t28 / t19 / t29 / saas_rbac / newapi / relay_token_usage 403→404 |

**与票里「会改哪些文件」一致**：☑ 是（PIT-2：同 PR 改 b1c/rbac/newapi）

**未触碰「不许改的文件」**：☑ 确认（`require_platform_admin` 函数本体未改；plugin verify 仍 403）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 守卫拒绝 | 否（不进 handler） | 零落库；审计独立短事务 |

**事务提交后的操作失败怎么办**：越权审计 fail 不改变 404 信封（既有）。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | N/A（无新写路径） |
| 保证方式 | — |
| 重复请求返回 | 重复直打仍 404 同形 |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 无条件更新 | — | — |

☑ N/A

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 无 | — | — | — | — |

## 4. ORM 与 DBML 对齐

☑ 本票无 schema 变更。

```
$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
```

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | 守卫 `平台写面越权拒绝(404)` |
| 越权留痕 | `record_authz_denied` target=METHOD path |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

```
$ uv run pytest -q backend/tests/test_fr_u12_u15_rbac.py
.....                                                                    [100%]
5 passed in 2.80s
exit: 0

$ uv run pytest -x -q backend/tests
1585 passed, 40 skipped, 7 warnings in 237.07s (0:03:57)
exit: 0

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-U12.1 超管上架 | `test_gwt_u12_1_platform_admin_can_list` | ✅ |
| GWT-U12.2 租户直打上架/扫描 404 | `test_gwt_u12_2_tenant_admin_listing_scan_404` | ✅ |
| GWT-U12.3 上架/渠道拒绝+行不变+leftover | `test_gwt_u12_3_tenant_admin_channel_and_listing_leftover` | ✅ |
| GWT-U15.1 超管看/存 RBAC 勾选 | `test_gwt_u15_1_superadmin_list_save_rbac` | ✅ |
| GWT-U15.2 权限加载中 | — | ➖ N/A 前端 T-12 |
| GWT-U15.3 租户 RBAC 404 无「抱歉」 | `test_gwt_u15_3_tenant_admin_rbac_404_no_sorry` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（守卫短接，无多步写） |
| 幂等 | 重复直打仍 404 | ✅（同形断言） |
| 并发写 | — | ➖ N/A |
| 外部依赖失败 | — | ➖ N/A |

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-U05 权限三态 | 拒绝=404 同形不是道歉 403 | HTTP_404 / Not Found；无「抱歉您没有权限」 | pytest |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 租户直打对照 `/api/v1/admin/tenants` 同信封。plugin verify / correct / license 仍 403（未削弱 `require_platform_admin`）。部门 CRUD 仍 `require_admin`。 |
| `/frontend` | T-12：导航无上架/扫描/平台渠道/RBAC；未知态另票。直打 API 已是缺页同形。 |
| `/architect` | GWT-70.3「拒绝」本波落实为 404 同形（SEC-4）；函数 `require_platform_admin` 仍 403。 |

## 9. 交票自检

- [x] 每条后端验收项有 evidence
- [x] 自测全绿
- [x] 未削弱 `require_platform_admin` 本体
- [x] 无硬编码连接串/密钥
- [x] 无 Alipay/WeChat notify、商户凭据、中转 SKU
- [x] 四类易漏已标 N/A 或覆盖
