# 实现证据 · T-21 公开值班联系 + 设置不说谎

> 票：T-21｜FR 锚点：FR-M33｜角色：/backend｜日期：2026-09-13

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| GET `/api/v1/public/ops-contact` | Router | `app/api/v1/ops_contact.py` | 无鉴权 |
| 空则隐藏 CTA | Service | `ops_contact_service.public_duty_contact` | `OPS.DUTY_CONTACT` strip；空→`""` |
| PUT `/configs/{key}` | Router | `configs.py` | `require_platform_admin_or_404` |
| 保存句 | Router | `updated(message=配置 {key} 已更新)` | 不含「官网已同步」 |
| 租户写 | Router | 404 同形 | 无「当前账号不能改系统设置」 |

## 2. 改动

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/app/api/v1/ops_contact.py` | 新增 | 公开 GET |
| `backend/services/ops_contact_service.py` | 新增 | 读配置；R10 logger |
| `backend/app/api/v1/__init__.py` | 修改 | 挂 `/public` |
| `backend/app/api/v1/configs.py` | 修改 | PUT 404 守卫 |
| `backend/tests/openapi_routes_golden.txt` | 修改 | `GET /api/v1/public/ops-contact` |
| PIT-2 | 修改 | 低角色 PUT configs 403→404 |

访客页 CTA 渲染属 official UI。本票只保证 API 空串/非空可让前端隐藏或展示。

## 6. 自测

Red：无 `/public/ops-contact`；租户 PUT configs 403 FORBIDDEN。

Green：

```
$ uv run pytest -q backend/tests/test_fr_m33_contact_settings.py
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
| M33.1 | 配置空 → `duty_contact=""`；无 localhost / 值班电话 | ✅ |
| M33.2 | 非空回显该值；不声称已接通电话值班 | ✅ |
| M33.3 | 租户 PUT 联系 404；配置不变 | ✅ |
| M33.4 | 超管保存副标题无「官网已同步」 | ✅ |
| M33.5 | 租户 PUT 设置 404 同形 | ✅ |

## 8. 给下游

| 给谁 | 内容 |
|---|---|
| `/frontend` | official 用 `duty_contact` 空则藏 CTA；Settings 保存句不得写「已同步官网」；租户写面 NotFound |
| `/qa` | 本机 `OPS.DUTY_CONTACT` 可能非空；空态用例须先 set `""` |

## 9. UI（/frontend 同票）

`DUTY_CONTACT` 空则官网无「联系平台」；租户直打 `/settings` 404 同形；保存不称同步官网。

```
admin Settings + official SiteLayout/Pricing in W4; frontend.sh 0
```
