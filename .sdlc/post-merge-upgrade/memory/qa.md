# qa memory · post-merge-upgrade

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-14
- Hat: verify
- Outputs: `04-verify/coverage.md` · `04-verify/test-report.md`（r2：M12.8 ✅；V01 关）

## Facts

- GWT-M 130：✅127 / ❌0 / ⚠️3（M11.7 live 收银、M11.12 真库、M34.2 C2）。
- M12.8 `:228` POST `.../plan` 200、code≠TASK_QUOTA_LIMIT、无「已达配额上限」、selectors、outbound。`:252` 免费档拦住可失败。2 passed 1.39s。
- M11.12 SQLite ThreadPool **不算** W2 已兑；需 MYSQL_FIDELITY=1。
- V01/V03/V04/V05 关。V02 仍开。不标 GA。

## Open (mine)

- BUG-V02 M11.12 MYSQL_FIDELITY
- `/sre`：C2、C4、live 收银、真库并发

## Do not re-litigate

- GWT 正文（pm）
- 实现缺陷修复
- 放行/四柱 GA（qc）
- live 波通道开通边
- M12.8 空心（已重写）
