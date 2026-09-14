# FINDINGS · verify G-fresh r1

Stage: verify. Verdict: **FAIL**.

### QA-01 GWT-M12.8 新用例空心 Then
- Dimension: 3 | Severity: major
- Suggestion: 铺 GWT-70.1（无本企业激活供应商、网关可达、至少一条模型）；`POST /ai/plans/{id}/plan` 必须 200 且 code != TASK_QUOTA_LIMIT_REACHED；可见句无「已达配额上限」；Then=向导方案与试采+列表该行。禁止用 !=429 / 不含 200000 当成功。

### QA-02 GWT-M11.12 两人同时未构造
- Dimension: 3, 8 | Severity: major
- Suggestion: `MYSQL_FIDELITY=1` 双连接同时 POST；或矩阵标 ⚠️ 需真库，**不得**当 W2 并发 Then 已兑。SQLite ThreadPool 不算。

### QA-03 coverage.md 仍把已映射 GWT 写成 ❌
- Dimension: 6 | Severity: minor
- Suggestion: M12.6/7、M11.13、M11.18、M26.2 改为 ✅ file:line；不要把空心 M12.8 / 未真跑 M11.12 改成 ✅。

## 总计

| 严重度 | 数量 |
|---|---|
| blocker | 0 |
| major | 2 |
| minor | 1 |

**PASS/FAIL: FAIL**
