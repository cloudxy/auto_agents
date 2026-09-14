# 实现证据 · T-22 租户货架 + 安装；关旗诚实；治理七叶 404

> 票：T-22｜FR 锚点：FR-M40｜角色：/backend｜日期：2026-09-13

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| GET `/capabilities` 租户货架 | Router+Service | `capabilities.py` → `list_public` | 关旗 `能力市场未开放`；不含 unlisted |
| GET `/capabilities` 超管目录 | Service | `CapabilityService.list_catalog` | 空态「还没有目录项…」≠关闭句 |
| 订阅写关旗失败 | Service | `require_power_market_open` | 409 `MARKET_CLOSED` 同句 |
| 本企业安装 | Service | `list_installs` | 既有 |
| 治理七叶 | Router | `require_platform_admin_or_404` | listing/scan/sources/import/verify/correct/alias/license/refs |
| 跨企业 install id | Service | `_load_live_pair` | HTTP_404 / Not Found |

## 2. 改动

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/app/api/v1/capabilities.py` | 修改 | 租户 list=货架；剩余治理守卫 404 |
| `backend/services/capability_service.py` | 修改 | `list_catalog` |
| `backend/services/power_market/installs.py` | 修改 | 跨租户同形 404 |
| PIT-2 测试 | 修改 | 租户 verify/correct/alias/license/refs 403→404；治理目录用 platform_admin |

未标 GA / live 支付。未改出站三环。

## 6. 自测

Red：租户 GET `/capabilities` 露出 unlisted；关旗仍出货架行；跨租户 `NOT_FOUND`「安装行不存在」。

```
FAILED test_fr_m40_market_shelf.py::test_gwt_m40_1_tenant_shelf_listed_and_own_installs
FAILED test_fr_m40_market_shelf.py::test_gwt_m40_2_flag_off_is_closed_not_empty_shelf
FAILED test_fr_m40_market_shelf.py::test_gwt_m40_cross_tenant_install_404
3 failed, 6 passed in 2.35s
```

Green：

```
$ uv run pytest -q backend/tests/test_fr_m40_market_shelf.py backend/tests/test_fr_m41_listing.py
.........                                                                [100%]
9 passed in 2.70s
exit: 0

$ uv run pytest -x -q backend/tests
1854 passed, 41 skipped, 8 warnings in 242.43s (0:04:02)
exit: 0

$ bash tools/check/arch.sh
exit: 0
```

| GWT | 测试 | 结果 |
|---|---|---|
| M40.1 | 货架仅 listed + 本企业安装 | ✅ |
| M40.2 | 关旗关闭句、禁空货架句；订阅不落行 | ✅ |
| M40.3 | listing/sources/scan/import 404 同形 | ✅ |
| M40.4 | 预告订阅不产生安装 | ✅ |
| 跨企业 | patch/delete 404 同形 | ✅ |

导航叶与七叶控件属 UI。

## 8. 给下游

| 给谁 | 内容 |
|---|---|
| `/frontend` | 租户 `/capabilities` 已是货架信封（`market_closed`/`message`）；治理写面 404 |
| `/qa` | 总开关仍 `/admin/power-market`（U11.3 403）；跨租户安装码是 HTTP_404 不是 NOT_FOUND |

## 9. UI（/frontend 同票）

侧栏货架+我的安装；关旗只「能力市场未开放」；开旗空「暂无已上架能力」；点货架不进七叶；安装空「还没有安装」≠未开放。

```
admin TenantShelf+governance+MyInstalls+subscribe 37 passed; official Capabilities 32 passed; frontend.sh 0
```
