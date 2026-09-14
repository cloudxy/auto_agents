# 实现证据 · T-23 超管上架/下架一行；无投稿；下架不级联

> 票：T-23｜FR 锚点：FR-M41｜角色：/backend｜日期：2026-09-13

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| PATCH `/{type}/{name}/listing` | Router+Service | `set_listing` | 超管；租户 404 |
| 上架后公开可见 | 既有 | `list_public` FR-33 | 总开关开 |
| 治理空目录 | Service | `list_catalog` total=0 | 无投稿表单字段 |
| 无作者门户 | Router | 无 submit/publish/author 路由 | 直打 404 |
| 下架不级联安装 | Service | listing 只改 `listing_state` | 安装行仍在 |

## 2. 改动

上架写路径既有（T-28 / FR-U12）。本票补对照测试 + 租户 404 同形（与 T-22 同 PR 守卫）。`set_listing` 不 DELETE `capability_installs`。

## 6. 自测

Red：本票 4 条在产品补齐前已绿（上架/空目录/租户 listing 404/不级联）；与 T-22 同跑。

Green：

```
$ uv run pytest -q backend/tests/test_fr_m41_listing.py
....                                                                     [100%]
4 passed

$ uv run pytest -x -q backend/tests
1854 passed, 41 skipped, 8 warnings in 242.43s (0:04:02)
exit: 0
```

| GWT | 测试 | 结果 |
|---|---|---|
| M41.1 | 超管上架 → 公开货架可见 | ✅ |
| M41.2 | 可上架 0 行 200；无投稿文案 | ✅ |
| M41.3 | 租户 listing 404；submit/publish/author 无入口 | ✅ |
| M41.4 | 下架后公开不可订；安装行仍在 | ✅ |

## 8. 给下游

| 给谁 | 内容 |
|---|---|
| `/frontend` | 无投稿表单；下架 Toast 不得说已删安装 |
| `/qa` | 关旗时超管仍可上架；租户货架走关闭句 |

## 9. UI（/frontend 同票）

超管可上架/下架一行；租户无投稿入口；下架不调用 uninstall。

```
admin governance tests in W5 37 passed
```
