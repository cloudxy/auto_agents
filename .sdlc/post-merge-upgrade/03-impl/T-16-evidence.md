# 实现证据 · T-16 渠道组未开通 vs 零令牌

> 票：T-16｜FR 锚点：FR-M23｜角色：/backend｜日期：2026-09-13

## 1. 契约落位表

既有 `relay_sku_gate` + `GET /relay/sku|tokens|groups`：

| Given | GET /tokens message | data |
|---|---|---|
| SKU≠active | 「未开通中转」 | `[]`（不是令牌空列表句） |
| SKU=active 且 0 令牌 | 「还没有令牌…」 | `[]` |
| plan_pro 已开通 | 仍「未开通中转」 | T-08 不写 SKU |

签发未开通：422 `RELAY_SKU_INACTIVE`。无第三套「还没有渠道组」。

M23.1 Given 用 T-08 确认收款开通企业档/`relay`。

## 6. 自测

本票多为对照（读闸 W2 已具备）。新测一次即绿：

```
$ uv run pytest -q backend/tests/test_fr_m23_relay_empty.py
.....                                                                    [100%]
5 passed

$ uv run pytest -x -q backend/tests
1827 passed, 41 skipped
exit: 0
```

| GWT | 测试 | 结果 |
|---|---|---|
| M23.2 | 免费未开通 | ✅ 未开通中转；禁还没有令牌 |
| M23.1 | 企业档 / relay 确认后零令牌 | ✅ 还没有令牌；可签发 |
| M12.4 | 专业档确认后仍未开通 | ✅ |
| M23.3 | 未开通签发拒绝 | ✅ 令牌数 0 |

## 7. UI（/frontend 同票）

未开通只「未开通中转」；已开通零令牌「还没有令牌」+签发；禁第三套「还没有渠道组…」。

```
admin RelayGroups tests in W3 六套 81 passed; frontend.sh 0
```
