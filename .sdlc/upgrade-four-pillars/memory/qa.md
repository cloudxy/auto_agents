# qa memory · upgrade-four-pillars

> Facts (**what**). How stays in SKILL.md. Cap 2200 chars.

## Last

- Date: 2026-09-13
- Hat: verify
- Outputs: `04-verify/coverage.md`（Closed leftover：QA-01/QA-02）

## Facts

- check-matrix.py 只抽 `\bFR-\d+\b`/`\bNFR-\d+\b`，不抽 FR-U01。spec 13 条 FR-01,06,14,15,18,30,33,34,50,51,70,71,74。无 NFR-nn。豁免须字面「前合同 v2，本波不重测」。check-matrix exit 0。
- 本波交 N1–N4（T-01…T-27，含 T-24）。L3。禁四柱 GA / 「当前可买」。值班活 ≠ SKU active。HMAC ≠ live 支付。Q-OPS-DUTY 无 SLA。qc 有条件放行 condition 10 only。
- T-24 已交（`03-impl/T-24-evidence.md`：checklist + 密钥扫描）。应用层 notify 无 RateLimitPolicy → NFR-U03 保持 ⚠️，不升 ❌。
- GWT-U02.7：`test_fr_u02_quota_copy.py:291`/`:313`，`Usage.test.tsx:232`，`frontend/admin/src/components/quota/UpgradeIntentButton.test.tsx:80`。已删 `Checkout.test.tsx:36`（ONLY_ALIPAY 夹具，非 test(）。
- N4 r2：pytest 10（U25.1 `:293` / U25.2 `:135` / U25.3 `:323` / U25.4 `:154`；`:177` 降级非空不标活；`:208` 第四态；`:232/:258/:271` bounded）。Jest 43：hasLiveRow `:111/:280`；行活须 gatewayAvailable `:137`；NewApiOps `:550/:89/:114`；App.menu U25.3 `:285`。漂移：sources `:301`、货架 `:312`、/newapi `:276`；U21.2 `:265`；U15.2 `:234`。
- 屏 19 离线 hint 无 Jest → ⚠️ 非 GWT-U25。NFR-U01 去支付无 5s monotonic。方言 SQLite；045/046 抛开库见 T-01/T-14。

## Open (mine)

- live 120s / live 支付宝微信 / live LiteLLM 未跑。应用层 notify 无 RateLimitPolicy（qc 条件 9）。离线 hint 无 Jest。不阻塞本矩阵豁免。

## Do not re-litigate

- 不代答 Q-AGPL；U24 钉是 T-23。不写测试、不修缺陷、不放行。
- 不把 pending/SKU active/值班活 写成当前可买。第四态不是 GWT-U25 行。
- 不写「T-24 未交」/「无 T-24 evidence」。不把 NFR-U03 ⚠️ 升 ❌。不重开 N1–N4 GWT。
