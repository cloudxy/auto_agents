# FINDINGS · define G-fresh r2

## Snapshot

- briefing.md `adad27803db35a535242c09b5e6001e78b0ddaaf6c57ac39ffb9f1e2746f16bc`
- spec.md `4b138931e185158637a93f9755c64bcb97aff5f89b105fe4c4a6be2dd7755a86`
- user-story.md `964b7e67fa7cb1c8d34e19017e720384da4e642dd53bece83cfb289614e83d94`
- metrics-blueprint.md `6eac955c4a91db93e55d37876384fae44a46697ea64087ed6bd0b842254eff48`

Stage: define r2. Verdict: **FAIL**.

r1 QA-01/03/04/05/06 按本快照关闭。

### QA-01 同一商品再提交仍有两套租户提示句
- Dimension: 6 | Severity: major | Evidence: spec.md:51；spec.md:108；spec.md:283；spec.md:305；上游 GWT-U30.2「已有未完成的支付」未作废
- Suggestion: 把 GWT-U30.2 标 `[superseded by FR-M10 状态词表]`，全程序只留「已有待支付」

### QA-02 `plan_enterprise` / `relay` 确认开通无 GWT，W2 放行 FR 的 Given 无法合法构造
- Dimension: 2 | Severity: major | Evidence: spec.md:299；spec.md:301；spec.md:279；spec.md:322；spec.md:408
- Suggestion: 补企业档/`relay` 提交→待支付→超管确认（金额=定价页该档）→已开通 GWT；或把 GWT-M12.5 / M23.1 移出 W2 放行

### QA-03 W2 冻结集含 FR-M14/M15，放行句没有
- Dimension: 6 | Severity: minor

### QA-04 专业档 tokens 没有穿越执法 GWT
- Dimension: 2 | Severity: minor

### QA-05 成员添加与注册长度边界不足
- Dimension: 8 | Severity: minor

## 总计

| 严重度 | 数量 |
|---|---|
| blocker | 0 |
| major | 2 |
| minor | 3 |

**PASS/FAIL: FAIL**
