# FINDINGS · define G-fresh r7

## Snapshot

- briefing.md `adad27803db35a535242c09b5e6001e78b0ddaaf6c57ac39ffb9f1e2746f16bc`
- spec.md `f447de4396cdacea008ea4d217f6948a03ad1caef40ba345959274a3db482339`
- user-story.md `436b73b2a76912bcd5582f861d961227d261acf64ded3385bec2ab520feb4599`
- metrics-blueprint.md `4988ba927991ac52e0eb9f904496247b2a3ed553f0bc44a1480763023d1e0849`

Stage: define r7. Verdict: **FAIL**.

r6 规划成功句三套 Then 按本快照关闭。

### QA-01 规划成功/降级与仍有效 FR-70/73/74 同一提交规划两套 Then
- Dimension: 6 | Severity: major
- Suggestion: M01.4 / M12.8 Given 钉 GWT-70.1 成功前置（无本企业激活供应商、网关可达、已登记模型）。未登记只走 70.2。网关不可达且无本企业激活供应商只走 74.1「平台 LLM 网关不可达」。有本企业激活供应商走 73.6。M01.5 不得另造「规划失败」句。NFR-M01 失败分支 = 74.1 / 73.6。

### QA-02 「可见方案」没有可测形态
- Dimension: 2 | Severity: minor

### QA-03 GWT-M12.4 Then 未钉「未开通中转」
- Dimension: 6 | Severity: minor

### QA-04 GWT-M11.11「不开通中转」未钉商品
- Dimension: 2 | Severity: minor

## 总计

| 严重度 | 数量 |
|---|---|
| blocker | 0 |
| major | 1 |
| minor | 3 |

**PASS/FAIL: FAIL**
