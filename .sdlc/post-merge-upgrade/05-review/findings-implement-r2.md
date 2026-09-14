# FINDINGS · implement G-fresh r2

## Snapshot

Stage: implement r2. Verdict: **PASS**（0 blocker / 0 major）.

r1 QA-01…05 按代码关闭。

### QA-01 已配通道 + W2 不传 channel 时提交后仍会画未开通金标句
- Dimension: 1, 8 | Severity: minor
- Suggestion: `wait_unconfigured` 只在两通道均未配时为真。`pending.channel is None` 但已有配置通道时不要 `can_pay=false`、不要下发该金标句。

### QA-02 无单打开结账时 GET empty_state 已是提交后金标句
- Dimension: 6, 8 | Severity: minor
- Suggestion: 仅 pending_open 时写金标 notice；无单 GET 不要带「提交后等待平台确认开通」。

## 总计

| 严重度 | 数量 |
|---|---|
| blocker | 0 |
| major | 0 |
| minor | 2 |

**PASS/FAIL: PASS**
