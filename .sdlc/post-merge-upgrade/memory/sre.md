# sre memory · post-merge-upgrade

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-14
- Hat: sre / deliver
- Outputs: `06-deliver/checklist.md`

## Facts

- Ancestor SHA `1db6a47`; worktree dirty; **no freeze SHA**.
- This spawn: `arch.sh` exit 0. `db_migrations.sh` **exit 1** SM-8 on `047.downgrade` one-line `DELETE enterprise` (046 passes via `# 回填:`). Full pytest + admin/official **build** not run here.
- Local `auto_agents.alembic_version=039` ≠ 046/047 evidence.
- MYSQL_FIDELITY GWT-M11.12: `test_gwt_m11_12_concurrent_same_product_one_pending` **1 passed / 1.99s / exit 0** (root, isolated schema, same TestClient ThreadPool). Not two uvicorn workers. Not 047 chain. Do **not** flip coverage.md ✅ (qc cond 8 /qa).
- 047 rollback **unverified**. down() skips NULL→offline fill, skips pro quota restore, unconditional DELETE enterprise. Do not claim verified rollback.
- C2 / C4 / GWT-M11.7 / checkout 5s **unticked**. HMAC/`signed_body` ≠ live cashier. Token issue ≠ C2. ingest+webhook ≠ C4.
- Ports: `config/default/{api,admin,official,litellm,billing}.yml` 9111/9112/9113/4000; `BILLING.RELAY_PRICE_CENTS=19900` (price, not secret). Secrets: `AUTO_AGENTS_*` + `MYSQL_FIDELITY_*` (not yml).
- No `compose down`. No downgrade past 037. Prefer leave 047, stop confirms.
- Did not write enablement / 亲爱的用户 / GA / 当前可买.

## Open (mine)

- Freeze SHA then four gates (SM-8 must die first → /backend comment).
- 047 up→down→up on isolated MySQL currently at **046**.
- C2 real chat 0→≥1; C4 live worker 120s; M11.7 live cashier; checkout 5s.

## Do not re-litigate

- qc 有条件放行
- four-pillar GA / 当前可买
- coverage.md M11.12 ✅ (qa)
- business code / Alembic body
- live payment in W2 budget
