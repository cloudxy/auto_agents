# qa memory · feat-four-pillars-v2

> Facts (**what**). How stays in SKILL.md. Cap 2200 chars.

## Last

- Date: 2026-09-10
- Hat: 验证
- Outputs: `.sdlc/feat-four-pillars-v2/04-verify/coverage.md`

## Facts

- Frozen set: FR-01…20 + 70…75 + 30…45 + NFR-01…10. Stub FR-50/51/60/61 = N/A Wave 2/3. Six Qs N/A 不代选.
- GWT-18.1 / TC-18.1 **✅** live Then（非 FakeRedis）：`run.py restart spider`；tenant `qc181-1789008085`；task #2 example+httpbin；+6.1s running count=1；**+40.6s completed count=1**；export JSON 200 rows 1；elapsed **40.56s ≤ 120s**. Idle close **30 ≠** 18.4 窗 **120**. 旧 +129s（idle 当时 120）作废.
- C35-QA-03 Register **已关**：`Register.test.tsx:177` 钉 FREE_TIER_FEATURE_COPY、禁 10000.
- NFR-07 **✅**：Home:76 / Pricing:70 / Register:192 ≥44px；Jest 4 passed exit 0.
- wiring/byok `or True` **已关**；pytest 两文件 14 passed exit 0.
- 01.1 / 06.1 / NFR-01 / 37.6 保持 ✅. 未发明 FR-50 覆盖. 未改 GWT/产品.
- Dialect: pytest SQLite / prod MySQL 8. ESC-2 NULLS LAST 仍有效.
- 未写 test-report.md / release-opinion.md.

## Open (mine)

- 16.1 时区 / IM-02/03/18/26 / 一次性 live 未入库 CI → sre 或实现债，本帽不改产品.
- MYSQL_FIDELITY 预发已过，未进仓库 CI.

## Do not re-litigate

- 六问答案。Wave 2/3 施工。GWT 正文。T-33 implement PASS ≠ 覆盖完成.
- 18.4 标注窗保持 120s，不得写成 idle 30.
- 01.1 / 06.1 保持 ✅.
