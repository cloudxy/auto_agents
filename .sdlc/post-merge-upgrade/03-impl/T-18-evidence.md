# 实现证据 · T-18 值班单一入口 / 签发≠live / duty_entry_opened

> 票：T-18｜FR 锚点：FR-M30 FR-M34 FR-M35｜角色：/backend｜日期：2026-09-13

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 值班入口 GET `/newapi/overview` | Router | `app/api/v1/newapi.py` | `require_platform_admin_or_404` |
| 平台钥匙 `/litellm/keys` | Router | `app/api/v1/litellm_admin.py` | 同一 404 守卫；不是第二套租户店 |
| 租户直打 404 同形 | Router | `deps.require_platform_admin_or_404` | HTTP_404 / Not Found；无 FORBIDDEN |
| 签发≠live | Router | `create_litellm_key` message | 「签发成功不代表已对租户开通」 |
| `duty_entry_opened` | Router+Service | overview 打开 fail-open emit | props.user_id；无密钥；租户尝试不记 |

**分层**：☐ Router 未 import ORM（钥匙路由只调 AdminService）

## 2. 改动

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/app/api/v1/newapi.py` | 修改 | 打开总览 emit `duty_entry_opened`（失败不挡） |
| `backend/app/api/v1/litellm_admin.py` | 修改 | 404 守卫；签发文案不含 C2/live |
| `platform_core/schemas/product_event.py` | 修改 | WAVE0 加 `duty_entry_opened` |

未触碰 UI 菜单叶（前端 T-18）。未标 C2 / live 支付。

## 6. 自测

Red（本波先前）：租户 GET `/litellm/keys` 403；超管打开值班无 `duty_entry_opened`。

Green：

```
$ uv run pytest -q backend/tests/test_fr_m30_duty_entry.py
.....                                                                    [100%]
5 passed

$ uv run pytest -x -q backend/tests
1845 passed, 41 skipped, 8 warnings in 146.09s (0:02:26)
exit: 0

$ bash tools/check/arch.sh
exit: 0
```

| GWT | 测试 | 结果 |
|---|---|---|
| M30.3 | 租户值班 404 同形 | ✅ |
| M30.4 | 租户 litellm keys 404 非 403 | ✅ |
| M34.1 API | 打开值班响应无「网关已对租户开通」/「当前可买」/C2 | ✅ |
| M35.1 | 超管打开可查 `duty_entry_opened` + user_id | ✅ |
| M35.2 | 租户打开不记成功事件 | ✅ |
| M35.3 | 租户查事件面 404 | ✅ |

M30.1/2/5 导航叶与 permissionsReady 属 UI。

## 8. 给下游

| 给谁 | 内容 |
|---|---|
| `/frontend` | 钥匙签发控件只放 `/newapi` 内；租户直打走 NotFound；签发成功句不得写成 live |
| `/qa` | 事件 fail-open；查询面仅超管 |

## 9. UI（/frontend 同票）

值班仍只 `/newapi`；钥匙折进页内 tab「钥匙」；租户 `/litellm` 404 不跳转；签发≠live；权限未就绪「权限加载中」。

```
admin NewApiOps + DutyKeysTab + App.menu in W4 六套 63 passed; frontend.sh 0
```
