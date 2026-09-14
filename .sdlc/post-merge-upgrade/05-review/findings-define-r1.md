# FINDINGS · define G-fresh r1

## Snapshot

- path: `00-discover/briefing.md`  
  sha256: `adad27803db35a535242c09b5e6001e78b0ddaaf6c57ac39ffb9f1e2746f16bc`
- path: `01-define/spec.md`  
  sha256: `9e4b9e390b5e0c4a844fc26a1e9b68fa5c340873de521ca22ac9cc5682759f22`
- path: `01-define/user-story.md`  
  sha256: `4c194569362706608bf8141f2bfacd7f31bbef3044ff9cf308fed03a646550d8`
- path: `01-define/metrics-blueprint.md`  
  sha256: `b684395d065ea1abc831c3038f13e38413de9540269b8d74a2186f3805131980`

Stage: define. Verdict: **FAIL**.

## FINDINGS

### QA-01 W2 把「验真才开通」和「无通道确认即开通」冻成两套 Then
- Dimension: 6 | Severity: major | Evidence: spec.md:257；spec.md:51–53；spec.md:272–281；spec.md:592–594 | Suggestion: 在 §0.2 把 FR-U33 改成「通道路径：未验真不得开通」；显式增加「超管确认收款是第二条合法开通，不走 FR-U38」；FR-U30…U38 的「仍有效」行必须划掉 GWT-U32.2（含 POST 不建单）以及任何「无验真不得开通」的绝对句，只留通道闭集 / 凭据 / 验真 / 失败不得已买。

### QA-02 租户状态词闭集、上游仍有效 GWT、埋点枚举三套名
- Dimension: 6 | Severity: major | Evidence: spec.md:263；spec.md:318；spec.md:537–543；spec.md:53；metrics-blueprint.md:127 | Suggestion: 给四态做一张内部码↔租户可见词↔`order_status_reached.status` 对照表；作废或改写 GWT-U34.1「支付未完成，套餐未开通」与 GWT-50.10「已确认」；补上「开通处理中」的事件值，或把它移出 W2 闭集。

### QA-03 Q-PRICE「确认后套用三数字」没有可执法 GWT
- Dimension: 2 | Severity: major | Evidence: spec.md:281；spec.md:289–295；briefing.md:107 | Suggestion: 给确认收款路径补一条与 GWT-U33.1 同强度的 Then：开通后第 6 个并发（或越过免费 10,000 条 / 20 万 tokens）必须按专业档执法，不得只验收用量页上的三个数字。

### QA-04 「未完成 / 开通处理中」进了闭集，本波没有合法产生路径
- Dimension: 2 | Severity: major | Evidence: spec.md:538–552；spec.md:635；spec.md:289 | Suggestion: 要么从本波闭集/FR-M14 拿掉「未完成」「开通处理中」，留给 live 波并改 GWT-M11.10 的 Given；要么冻一条本波可构造的合法流转（超时时长，或保留取消入口），禁止 §3.1 写「买方取消」同时 §5 写「取消入口下一轮」。

### QA-05 同一 When 两套 Then，违反本文件 X-IA-OPEN
- Dimension: 6 | Severity: major | Evidence: spec.md:77；spec.md:349；spec.md:451 | Suggestion: 每个 When 只留一个 Then。第二套「API 钥匙」直打：只 404 同形，或只重定向到「出站拉数钥匙」。租户直打系统设置写面：只 404 同形，或只「当前账号不能改系统设置」。

### QA-06 「同一商品一笔待支付」没有并发 GWT
- Dimension: 8 | Severity: major | Evidence: spec.md:274；spec.md:287；spec.md:601 | Suggestion: 补 GWT：两名买方（或同一买方双提交）同时对同一商品提交开通 → 只 1 笔待支付，另一笔可见「已有未完成的支付」、不建第二单、配额不变。

### QA-07 `checkout_story_started.surface` 在 spec 与蓝图不一致
- Dimension: 6 | Severity: minor | Evidence: spec.md:313–317；metrics-blueprint.md:126 | Suggestion: 钉死：事件在进入结账页时上报，`surface=checkout`；来源页用另字段 `referrer_surface=pricing|usage|nav`。

### QA-08 导出 100 条上限与出站拉数都没有容量 GWT
- Dimension: 5 | Severity: minor | Evidence: spec.md:227；spec.md:344；spec.md:601 | Suggestion: GWT-M02 补刚好 100 / 101 条；出站拉数补分页或与导出同一上限。

### QA-09 故事表与放行范围和 3C 正文对不齐
- Dimension: 6 | Severity: minor | Evidence: spec.md:19；spec.md:165–173；spec.md:259；user-story.md:133 | Suggestion: user-story 补 US-M1-04 / US-M2-04，或从表里删掉；W2 放行句在两文件抄同一串。

### QA-10 出站拉数外部边界没有 `[SEC-n]`；确认收款不可逆未锚金额/单据
- Dimension: 4 | Severity: minor | Evidence: spec.md:339–349；spec.md:427–430；spec.md:596 | Suggestion: 出站拉数标 `[SEC-2]`；确认收款标 `[SEC-3]`：只能确认本笔待支付、金额与定价页该档一致。

## 总计

| 严重度 | 数量 | 已处置 |
|---|---|---|
| blocker | 0 | open 0 |
| major | 6 | open 6 |
| minor | 4 | open 4 |

**PASS/FAIL: FAIL**
