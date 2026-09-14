# 实现证据 · T-12 出站拉数只认出站钥匙

> 票：T-12｜FR 锚点：FR-M20 FR-M26 [SEC-2]｜角色：/backend｜日期：2026-09-13

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| `GET /external/v1/public/data/{spider}` | Router | `external_api/v1/public.py` | 只走出站钥匙 |
| 查找 | Service | `OutboundKeyService.resolve_active_tenant` | sk- 不进 |
| 错平面 401 0 行 | Router | `_require_bound_tenant` | 不查结果库 |
| 事件无明文 | Service | `outbound_pull_auth.record_wrong_plane_rejected` | |

KEY_BINDINGS / 静态 Key：**仍**用于 `/spider/status|results|stats`（FR-13 平台绑定），**不得**拉 `/data/{spider}`。

## 2. 改动

`public.py` 收口三环；`outbound_pull_auth.py` 新增；WAVE0 加 `outbound_wrong_plane_rejected`。PIT-2：`test_outbound_pull_enforcement` KEY_BINDINGS 拉数改为 401；`TestOutboundPullBinding` 13.1/13.3 同改。

## 6. 自测

Red：api_keys / KEY_BINDINGS 仍 200 出数；无拒绝事件。

```
FAILED test_fr_m20_outbound_lookup.py::test_gwt_m20_5_api_key_and_garbage_rejected
FAILED test_fr_m20_outbound_lookup.py::test_gwt_m20_5_key_bindings_cannot_pull
FAILED test_fr_m20_outbound_lookup.py::test_gwt_m26_1_reject_event_no_plaintext
```

Green：

```
$ uv run pytest -q backend/tests/test_fr_m20_outbound_lookup.py
......                                                                   [100%]
6 passed

$ uv run pytest -x -q backend/tests
1827 passed, 41 skipped, 8 warnings in 207.91s (0:03:27)
exit: 0

$ bash tools/check/arch.sh
exit: 0
```

| GWT | 测试 | 结果 |
|---|---|---|
| M20.1 | 出站钥匙拉本企业行 | ✅ |
| M20.4 | sk- 拒绝 0 行 | ✅ |
| M20.5 | api_keys / 乱填 / KEY_BINDINGS | ✅ |
| M20.8 | page_size 上限 100 | ✅ |
| M26.1/3 | 超管可查事件无明文；租户 404 | ✅ |

## BUG-V05（GWT-M26.2）

超管 `GET /product-events?event_name=outbound_wrong_plane_rejected` 且无行 → 200、`total=0`、`items=[]`，不是查询失败。

```
$ uv run pytest -q backend/tests/test_fr_m20_outbound_lookup.py \
    backend/tests/test_fr_m12_fulfill.py \
    backend/tests/test_fr_m11_checkout_pending.py \
    backend/tests/test_fr_m11_confirm.py
..............................                                           [100%]
30 passed in 7.64s
exit: 0
```

