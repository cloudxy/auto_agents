# dba memory · post-merge-upgrade

> Facts (**what**). How stays in SKILL.md. Cap 2200.

## Last

- Date: 2026-09-13
- Hat: dba / schema（shape r1 QA-03/QA-04）
- Outputs: `02-shape/db-spec.md` · `02-shape/schema.dbml`
- New tables: **none**.

## Facts

- Head **046** → spec **047**. Local `alembic_version=039` is not 046 evidence.
- Unique pending = 046 `uk_orders_tenant_open_product`. Do not rebuild.
- **QA-03**: widen `orders.channel` NULL **and DROP DEFAULT 'offline'**. W2 unconfigured INSERT must list `channel` = SQL NULL. No ORM `server_default`/`default='offline'`. Literal `offline` only on 040 leftover rows; 047 does not UPDATE them. down: NULL→offline then NOT NULL DEFAULT offline.
- SEC-3: CAS `id + checkout_pending + amount_cents=current display`. pro=29900; enterprise seed 99900; relay config `BILLING.RELAY_PRICE_CENTS` ≠29900. No slug=relay.
- pro `quota_json` UPDATE to 50/200000/5000000. Do not rewrite historical `tenants.quota`.
- **QA-04**: enterprise quota triple **not frozen**. T-08 only: JSON ≠ pro three numbers. Fixture 50/2M/20M is not T-08 gold. pm must write a sentence then UPDATE.
- SKU writers: `relay` or `plan_enterprise`. `plan_pro` must not write entitlements.
- Outbound lookup = `outbound_keys` only. No Stripe. No new Redis/indexes.

## Open (mine)

- pm: enterprise quota three numbers (blocking T-08 gold, not columns).
- pm may UPDATE enterprise 99900 / relay config cents.
- Relay period still app 30d.

## Do not re-litigate

- No second orders table. Do not keep channel DEFAULT offline after NULL widen.
- Do not freeze 50/2M/20M. Do not edit 040. Do not contract old status / tenant_id NOT NULL this wave.
