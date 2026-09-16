# 实现证据 · T-06 排序三档 + 精选/示例治理端点

> 票：contract §7 T-06｜FR 锚点：FR-04 GWT-04.1–04.6 + 附加 d｜lane：api｜日期：2026-09-15

## 1. 交付面

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/power_market/sorting.py` | 新增 76 行 | 三档排序子句 + alive 订阅计数派生表 + hot 降级判定（AD-6） |
| `backend/services/power_market/curation.py` | 新增 85 行 | featured/examples 写 + 请求模型（20 条 × 200 字校验，AD-7） |
| `backend/app/api/v1/capabilities_gov.py` | +2 端点 | `PATCH /{t}/{n}/featured`、`PATCH /{t}/{n}/examples`（契约 §4 #5/#6） |
| `backend/services/power_market/service.py` | 改 | `list_public(sort=)` → `sort_applied`；`_list_fr33(sort=)` 换掉 `id DESC` |
| `backend/services/power_market/projection.py` | 改 | items 外发 `featured`（契约 §4 #7） |
| `backend/app/api/v1/public_skills.py` | 改 | `GET /public/capabilities` 增 `sort` 查询参数 |
| `backend/tests/test_shelf_sorting.py` | 新增 280 行 | 12 用例 |
| golden + 两处公开字段白名单 | 同步 | 新路由入 golden；`featured` 入白名单 |

## 2. 关键实现裁定

- **MySQL 无 `NULLS LAST`**（db-spec §9:306 明示不可照抄）：hot 档用 `LEFT JOIN` 计数派生表 +
  `COALESCE(cnt, 0) DESC`，左联归零与「无计数不显示数字」同义。
- **降级判定放在 `_resolve_sort`**：全库 alive 订阅计数为 0 → 实际按 smart 出序并回
  `sort_applied="smart"`（GWT-04.4）。降级态 payload 不含任何计数字段，用例逐项断言无
  `*count*`/`*install*`/`cnt` 键外泄。
- **非法 sort 回落 smart**，不新增 422 面——契约 §4 只对非法 `type` 约定 422。
- **排序只挂行查询**：`total` 仍从未排序子查询算，避免 hot 的左联影响计数。
- **AD-11 行数预算**：`service.py` 488 → 491 行（原始基线 495），净行数未增；期间 ruff 修掉
  WIP 搬迁残留的两处 F401（`hosts_for_asset` / `_to_public_asset_type`）。

## 3. GWT × 用例对照

| GWT | 用例 |
|---|---|
| 04.1 综合 | `test_gwt_04_1_smart_features_first_then_updated_at`（精选区内仍按 updated_at 倒序） |
| 04.2 最新 | `test_gwt_04_2_latest_ignores_featured`（精选不得插队） |
| 04.3 最热 | `test_gwt_04_3_hot_orders_by_install_count` + `test_hot_ignores_soft_deleted_installs` |
| 04.4 降级 | `test_gwt_04_4_hot_degrades_to_smart_without_counts` |
| 04.5 精选治理 | `test_gwt_04_5_featured_patch_moves_asset_to_top` |
| 04.6 越权 | `test_gwt_04_6_non_admin_featured_patch_404_and_no_change` + `test_non_admin_examples_patch_404` |
| 附加 d | `test_examples_roundtrip_and_empty_clears` + `test_examples_over_limits_422` |
| 缺省/非法档 | `test_smart_is_default_when_sort_absent_or_invalid` |

**GWT-04.5 的断言口径修正**：PATCH 会触发 `updated_at` 的 `onupdate` 跳到 now，被操作行因此
成为「最新」。故「取消精选后回到未精选区」只能对着另一条既有精选行断言相对位置，不能断言
它离开列表首位（dba OQ1 已接受 updated_at 跳档，无 GWT 反例）。首版用例按后者写、实测红，
已改为前者并在用例 docstring 记录原因。

## 4. 自测证据

```
$ python -m pytest -q backend/tests/test_shelf_sorting.py -p no:cacheprovider
12 passed in 10.50s

$ python -m pytest -q backend/tests/test_openapi_routes_golden.py \
    backend/tests/test_b1c_capabilities_coverage.py backend/tests/test_skill_public_api.py \
    backend/tests/test_t14_public_paging.py backend/tests/test_t13_public_seed_filter.py
86 passed in 55.03s          ← 排序默认序由 id DESC 改为 smart，分页/白名单回归专测

$ ruff check backend platform_core scripts   → All checks passed!
$ bash tools/check/arch.sh                   → exit 0
```

## 5. 交票自检

- [x] 三档 + 降级 + sort_applied 全部有用例
- [x] 越权 404 门面（featured/examples 两端点）
- [x] golden 同步；公开字段白名单同步
- [x] service.py 净行数未增（AD-11）
- [x] ruff / arch.sh 退出码 0
