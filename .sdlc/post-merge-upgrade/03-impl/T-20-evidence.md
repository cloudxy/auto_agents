# 实现证据 · T-20 用户停用 / 筛选已停用 / 恢复

> 票：T-20｜FR 锚点：FR-M32｜角色：/backend｜日期：2026-09-13

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| GET `/admin/users` | Router | `admin.py` | `status=active\|deleted\|disabled`；`q` 登录名 |
| 筛选/搜索 | Service | `list_users` + `_list_users_where` | disabled=未删且 `is_active=False` |
| 停用 | Service | `update_user` is_active=False | 登录 401 |
| 恢复停用 | Service | `_reactivate_disabled` | 未软删；emit `user_restored` |
| 租户直打 | Router | `require_platform_admin_or_404` | HTTP_404 |
| 种子 admin 不可删 | Service | `delete_user` | 既有 T-26 / FR-94 |

## 2. 改动

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/app/api/v1/admin.py` | 修改 | users CRUD 404 守卫；status 含 disabled；q |
| `backend/services/user_service.py` | 修改 | q/disabled 谓词；停用恢复 + refresh 防 MissingGreenlet |
| PIT-2 | 修改 | viewer/租户 403→404；CRUD 用 `platform_admin_client` |

## 3. 决策

软删恢复仍走 `deleted_at IS NOT NULL` 条件 UPDATE（GWT-93.9 已在册启用 = no-op）。停用（`deleted_at` 空、`is_active=False`）另路 `_reactivate_disabled`：flush+refresh 后再 `UserResponse`（P-BE-01）。

## 6. 自测

Red：`status=disabled` 422；租户 `/admin/users` 403；停用恢复 no-op。

Green：

```
$ uv run pytest -q backend/tests/test_fr_m32_user_lifecycle.py
....                                                                     [100%]
4 passed

$ uv run pytest -x -q backend/tests
1845 passed, 41 skipped, 8 warnings in 146.09s (0:02:26)
exit: 0
```

| GWT | 测试 | 结果 |
|---|---|---|
| M32.1 | q=登录名找到并停用；原密码登录 401 | ✅ |
| M32.2 | status=disabled 空列表 total=0 | ✅ |
| M32.3 | 租户 list/patch 404 | ✅ |
| M32.4 | 恢复可登录；`user_restored.restored_user_id` | ✅ |
| M32 边界 | 种子 admin 不可删 | ✅ 既有 `test_t26_base_protection` |

空态金标句 UI。

## 8. 给下游

| 给谁 | 内容 |
|---|---|
| `/frontend` | 筛选「已停用」打 `status=disabled`；搜索登录名 `q`；租户直打 NotFound |
| `/qa` | 软删恢复与停用恢复分路；重复恢复启用用户仍 no-op 无第二事件 |

## 9. UI（/frontend 同票）

筛选「已停用」；恢复沿用既有；种子 `admin` 无删除；租户 `/users` 404。

```
admin Users in W4 六套 63 passed
```
