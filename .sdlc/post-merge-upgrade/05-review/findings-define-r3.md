# FINDINGS · define G-fresh r3

## Snapshot

- briefing.md `adad27803db35a535242c09b5e6001e78b0ddaaf6c57ac39ffb9f1e2746f16bc`
- spec.md `a74041e96d8e7cfe716027e15b7a0b5db50a1d1af856b3631f992a5c03e55e02`
- user-story.md `43cb196dfb74329596dead490b8975abba347c1d71fc65bd8dc712b1b4c49ecb`
- metrics-blueprint.md `8fd1cdead126539a60e4defbe184a0bf16aa74548969947c128c1f09659591f7`

Stage: define r3. Verdict: **FAIL**.

r2 QA-01 / QA-02 按本快照关闭。

### QA-01 W2 放行的 GWT-M12.8 When 在本合同内无法合法构造
- Dimension: 2 | Severity: major | Evidence: spec.md:330；FR-M01 规划未开放不入队；FR-M03 夹具采集不耗专业档 tokens
- Suggestion: 把 When 改成「规划已开放且用量=200,001 的会打模型的规划/提交」；或把 M12.8 移出 W2 放行，只留 GWT-M12.6 / M12.7

### QA-02 运营台金额 oracle 钉「定价页」vs 确认收款钉「结账页」
- Dimension: 6 | Severity: minor

### QA-03 导出超限 GWT 两个出口
- Dimension: 8 | Severity: minor

### QA-04 GWT-M11.8 不在 W2 放行串
- Dimension: 6 | Severity: minor

## 总计

| 严重度 | 数量 |
|---|---|
| blocker | 0 |
| major | 1 |
| minor | 3 |

**PASS/FAIL: FAIL**
