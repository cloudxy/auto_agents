# analyst memory · feat-four-pillars-v2

> Facts (**what**). Cap 2200 chars.

## Last

- Date: 2026-09-08
- Hat: 定义 / 可判定性复审（非 retro）
- Outputs: `.sdlc/feat-four-pillars-v2/01-define/diagnosis/analyst.md`

## Facts

- 无 `metrics.yaml`、无产品事件 SDK/查询面。事件名仅命中 `notifications.type=task_completed`。
- `POWER_MARKET` / `listing_state` / `capability_installs` / `is_marketplace_candidate` / `Asia/Shanghai`：2026-09-08 零命中。
- 口径底稿 = 旧 `metrics-blueprint.md` v1.2。WACT 唯一北极星；核心动作 completed∧result_count>0∧候选 false。
- grok-files 度量稿更松（TTFV 不过滤候选、无失败装空、散文排除）→ 不当 v2 合同。
- 诊断稿 §8 WAU=任务∨订阅∨LLM：禁止回流。
- Hero `HERO_STATS` 仍渲染；禁止当 OEC/基线。
- Dashboard：成功率全历史、结果近 7 日 now()、用量 utcnow()、质量 n=1。
- 注册成功「再注册一家」；定价三档同 `/register`；首页 CTA 不在五档。
- 失败装空已红：Capabilities catch→「暂无」；SkillsSection catch→空白。Usage 可见 `QUOTA_EXCEEDED`。
- ADR-0016 / product-events / T-13·T-14 为 superseded todo，未落地。signup 不要求 anonymous_id。
- 失败率 +10pp 与「基线无」互否。未写 07-retro。

## Open (mine)

- v2 蓝图是否以 v1.2 为底、拒 grok-files TTFV 回退与诊断稿 WAU。
- Q-VOICE 未关能否打观察钟。
- signup 是否带注册前 anonymous_id；后台直达是否另表。
- F3 步间窗 / 跳过 search / 预告分母。
- 失败率第一轮是否只记录。
- 测试企名单（含 platform）；WACT=0 且节点离线是否不算产品失败。

## Do not re-litigate

- 北极星=WACT（出数，非订阅/LLM）；禁止双北极星。
- Hero / 全历史成功率 / 质量分 / 渠道 24h 不当 OEC。
- 验收以事件可查为准；审计/通知/stats 不得顶替。
- 无对照只说变化；无 n 不下百分比。
- 仓 / metrics.yaml 下一轮。本轮不做 A/B；分流单位=企业。
