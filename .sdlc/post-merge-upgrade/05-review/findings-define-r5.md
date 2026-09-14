# FINDINGS · define G-fresh r5

## Snapshot

- briefing.md `adad27803db35a535242c09b5e6001e78b0ddaaf6c57ac39ffb9f1e2746f16bc`
- spec.md `09fae4bebd390c3792d499aef993bd1b0cecbc6c17793a388f0303a1bbe18576`
- user-story.md `e690472a7a03201d42c0574480f98fae58e30aaff78b023246ce0f64c477cfad`
- metrics-blueprint.md `9234b7d2f213b251035e9e32c6ae3939c5a513708e50ed39fec91574e451a371`

Stage: define r5. Verdict: **FAIL**.

r4 major（GWT-84.2）按本快照关闭。

### QA-01 打开渠道组：未开通 vs 零令牌仍是同一动作两套 Then
- Dimension: 6 | Severity: major | Evidence: FR-60 仍有效；GWT-60.4 Given 仅「零把令牌」；GWT-U21.1 / GWT-M12.4 / GWT-M23.2 未开通中转。免费且未开通 ⇒ 令牌必为 0，两套 Then 同时成立。
- Suggestion: §0.2 将 GWT-60.4（及 GWT-60.7）Given 收口为 **中转已开通**；未开通只走 U21.1 / M12.4 / M23.2。

### QA-02 规划未开放空态允许「同等句」
- Dimension: 2 | Severity: minor

### QA-03 GWT-M12.8 成功 Then「入队」与 GWT-M01.4「可见方案」不完全同一句
- Dimension: 2 | Severity: minor

## 总计

| 严重度 | 数量 |
|---|---|
| blocker | 0 |
| major | 1 |
| minor | 2 |

**PASS/FAIL: FAIL**
