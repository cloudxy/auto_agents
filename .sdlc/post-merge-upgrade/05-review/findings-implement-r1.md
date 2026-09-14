# FINDINGS · implement G-fresh r1

## Snapshot

- spec.md `541c2793901e05f3b9b0c618b1d30425b813603d8f20a6f9030a77638d4a542c`
- contract.md `9b450cb818c3dc32b7739780e270b215e4f8887e4fee22ae6c9a9d54c1fa9612`
- 03-impl T-01…T-24（抽检 T-05/T-06/T-12/T-16/T-18/T-22）

Stage: implement. Verdict: **FAIL**.

### QA-01 未配通道提交后结账页不展示 GWT-M11.1 金标句
- Dimension: 1, 6 | Severity: major
- Evidence: `billing_service.py` preview `can_pay` 写死 True；`Checkout.tsx` 用 `can_pay === false` 才渲染「收款通道未开通，提交后等待平台确认开通」；createCheckout 丢弃 POST message；U30 测断言 `can_pay is True`
- Suggestion: 预览在所选/全部通道未配时给出页面可消费信号（`can_pay=false`，或 `channels[].configured` 全 false，或 pending `notice`=金标句）；Checkout 用该信号渲染 Alert；测夹具与 GET 真包络对齐。不要只把句子留在 201 envelope。

### QA-02 重复待支付 code 合同与实现不是同一枚
- Dimension: 6 | Severity: minor
- Suggestion: 实现改成合同 `ORDER_PENDING_EXISTS`，或改合同并删测试里那枚不再下发的码。

### QA-03 渠道组第三套空态常量仍导出
- Dimension: 1, 8 | Severity: minor
- Suggestion: 删除 `relayCopy.ts` 里「还没有渠道组。创建后才能签发令牌。」产品导出。

### QA-04 预览会把已作废 live 态句子写进租户 GET message
- Dimension: 1 | Severity: minor
- Suggestion: W2 预览对非 `checkout_pending`/`fulfilled` 不要回「支付已到账，开通处理中」「支付未完成，套餐未开通」。

### QA-05 部分 UI 证据是缩写
- Dimension: 3 | Severity: minor
- Suggestion: 补完整 jest 命令行。不单独判 fail。

## 总计

| 严重度 | 数量 |
|---|---|
| blocker | 0 |
| major | 1 |
| minor | 4 |

**PASS/FAIL: FAIL**
