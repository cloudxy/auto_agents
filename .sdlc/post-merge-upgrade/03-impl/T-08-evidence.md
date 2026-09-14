# 实现证据 · T-08 按商品码履约

> 票：T-08｜FR 锚点：FR-M12 / FR-M11｜角色：/backend｜日期：2026-09-13

## 1. 契约落位表

| 商品 | 配额 | SKU | 函数 |
|---|---|---|---|
| plan_pro | 50/200000/5000000（定价页，不信 040 20/500k） | 不写 | `fulfill_checkout_product` |
| plan_enterprise | 价目 JSON 且 ≠ 专业三数字 | active | 同上 |
| relay | 保持开通前 | active | 同上 |

确认与 notify `_fulfill_product` **同一函数**（`billing_fulfill.py`）。

047：UPDATE `plans.pro.quota_json`；INSERT enterprise 99900 若缺。

## 6. 自测

Green：`test_fr_m12_fulfill.py` 4 passed。全量 1808 passed exit 0。

| GWT | 测试 | 结果 |
|---|---|---|
| M12.6 | 专业档执法 | ✅ 50 不是种子 20 |
| M12.4 | 专业档不开中转 | ✅ SKU none |
| M11.15 | 企业档 | ✅ ENT 配额 + SKU active |
| M11.17 | relay | ✅ SKU active、配额不变 |

夹具 `payment_notify_support.PRO_QUOTA` 仍种 20/500k，履约覆盖为定价页三数字。

## BUG-V01（GWT-M12.6/7/8 执法 When）

确认专业档后：5 个 running 再 POST `/spiders/run` → 已入队；10001 条结果再采集 → 已入队；月度 token=200001 且 LLM.ENABLED 开 → POST `/ai/plans` 可见方案，launch 非 429/QUOTA_EXCEEDED。不是只断言 quota JSON。入队走本进程 FakeRedis 心跳（与 M03 同缝），不声称 C4 live worker。

```
$ uv run pytest -q backend/tests/test_fr_m12_fulfill.py \
    backend/tests/test_fr_m11_checkout_pending.py \
    backend/tests/test_fr_m11_confirm.py \
    backend/tests/test_fr_m20_outbound_lookup.py
..............................                                           [100%]
30 passed in 7.64s
exit: 0
```

## verify G-fresh r1 QA-01

重写 `test_gwt_m12_8_*`：GWT-70.1 夹具（litellm 网关可达、有模型、无本企业供应商）；`POST /ai/plans` 再 `POST .../plan`；Then=HTTP 200、code ≠ `TASK_QUOTA_LIMIT_REACHED`、无「已达配额上限」、快照有 selectors。对照 `test_gwt_m12_8_free_tier_200001_blocks_plan`：未开通专业档同样 200001 → `TASK_QUOTA_LIMIT_REACHED` +「已达配额上限」（空心 Then 会让对照失败）。不用 `!=429` / 不含 `200000` 当成功。

```
$ uv run pytest -q backend/tests/test_fr_m12_fulfill.py::test_gwt_m12_8_tokens_200001_plan_visible_not_free_cap backend/tests/test_fr_m12_fulfill.py::test_gwt_m12_8_free_tier_200001_blocks_plan
..                                                                       [100%]
2 passed in 1.38s
exit: 0
```


