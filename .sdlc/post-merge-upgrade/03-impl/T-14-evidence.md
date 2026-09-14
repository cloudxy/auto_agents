# 实现证据 · T-14 成员增改删

> 票：T-14｜FR 锚点：FR-M21｜角色：/backend｜日期：2026-09-13

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 添加/改角色/删除 | Service | `member_service.py` | 既有路径可走完 |
| 不能设平台超管 | Service | `_reject_platform_role` | is_platform_admin / platform_admin / superadmin |
| 跨企业 id | Service | `_member_missing` HTTP_404 Not Found | 与页面不存在同形 |
| 只读写 | Router | `require_member_writer` | 400 `MEMBER_ROLE_NOT_ALLOWED`；**不**改共用 `require_tenant_manager`（用量写套餐仍 403） |
| 空名 / 256 字 | Service | 请填写登录名 / 登录名最多 50 个字符 | users.username String(50) |

## 6. 自测

Red：viewer 403+FORBIDDEN；跨租户 NOT_FOUND「成员 3不存在」；256 字 SQLite 放行。

Green：`test_fr_m21_members.py` 8 passed。全量 1827 passed exit 0。

| GWT | 测试 | 结果 |
|---|---|---|
| M21.1 | 添加经办 | ✅ |
| M21.2 | 负责人看见自己 | ✅ |
| M21.3 | 只读写拒绝、名单不变、无 FORBIDDEN | ✅ |
| M21.4 | 不能设超管 | ✅ |
| M21.5 | 跨企业 404 同形 | ✅ |
| M21.6/7 | 空名 / 超长 | ✅ |

## 7. UI（/frontend 同票）

添加/改角色/移除可走完；无平台超管选项；只读隐藏写控件；跨企业 404 同形。

```
admin Members tests in W3 六套 81 passed; frontend.sh 0
```
