# dba memory · feat-four-pillars-v2

> Facts (**what**). How stays in SKILL.md. Cap 2200.

## Last

- Date: 2026-09-08
- Hat: shape / dba（G-fresh r1 FAIL → close DB-01/DB-02 only）
- Outputs: `02-shape/schema.dbml` · `db-spec.md` · `migration-review.md`
- Lint: `tools/check/db_ir.sh` exit 0

## Facts

- Existing-table IR = **live full columns ∪ this-feature added**. Stub forbidden. SHOW CREATE must not DROP live cols/indexes.
- Live sources: ORM + 011/014/018/019/025. ADD columns append. `source_type` widen in place.
- Alembic head **027**. No 028/029/030. No billing. No LiteLLM PG in Alembic/models. No handwritten SQL. No ORM this hat.
- `gateway_ref VARCHAR(191) NULL` on channel_events + probe. Keep `channel_id` BIGINT.
- Installs not exempt. `uq_asset_type_name_alive` unchanged. 泳道 L4.
- DB-01 closed: assets keep-list `ai_suggested_score/tier/reviewed_by/reviewed_at/similar_to`; channel usage/limit_quota/window_hours/reason; probe scores/latency_ms; plugins/experts/teams 018 full; skill_jobs total/succeeded/failed/detail.
- DB-02 closed: `Table skills` live 014+019; only `source_type` 16→32. No alive on skills.name.
- UI-01 is designer, not this hat.

## Open (mine)

- Q-PLACE default platform; no second inbound tenant
- Q6 origin_ref 256 vs 512
- Q2 writable window
- Q7 results hash UNIQUE (not 030)
- Dirty stamp 028–030 → sre
- gateway_ref shape (opaque 191)
- 90d archive owner

## Do not re-litigate

- Six operator Qs; Q-LLM closed
- Q-LISTED-AT / Q-IDEM locked
- No handwritten Alembic SQL; no ORM this hat
- No rename capability_experts
- T-18/T-19 must not alter channel_id type
- SH/TK not reopened
