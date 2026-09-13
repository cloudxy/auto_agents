# dba memory · upgrade-four-pillars

> Facts (**what**). How stays in SKILL.md. Cap 2200.

## Last

- Date: 2026-09-12
- Hat: implement / dba
- Outputs: Alembic 046 · ORM · `03-impl/T-14-evidence.md`
- Lint: `db_migrations.sh` 0 · `arch.sh` 0 · pytest 1602 passed
- New tables: `payment_channel_credentials`, `relay_sku_entitlements`

## Facts

- Head is **046** (revises 045). N1 stays in 045. Do not stuff N3 into 045.
- `orders`: product_code/order_no/channel_trade_no/merchant_id_snapshot/fail_reason/late_notify_at/verified_at/fulfilled_at/unpaid_at/open_product_slot(STORED generated)/updated_at. status VARCHAR 32. plan_id nullable. Keep `ix_orders_tenant_id`.
- Slot UNIQUE `(tenant_id, open_product_slot)`: non-terminal + product_code occupies; fulfilled/unpaid NULL out. Multiple NULL ok.
- Credentials: no tenant_id, TENANT_EXEMPT, secrets_encrypted TEXT blob only. Channel unique.
- SKU entitlements: tenant_id UNIQUE NOT NULL, not exempt. status none/active/expired. Do not DELETE `relay_groups`.
- Illegal unpaid→fulfilled: no CHECK; CAS UPDATE rowcount 0.
- 046 up→down→up exit 0 on throwaway MySQL (relay_groups survived down).
- No git/yml merchant secrets. No checkout HTTP / Alipay SDK this ticket.
- `plans.updated_at` ADD only. No slug=relay seed.

## Open (mine)

- `plans.slug=enterprise` price/quota → /pm
- Relay SKU period length → /pm
- Backfill product_code on legacy pending → still recommend no

## Do not re-litigate

- ADR-0024 notify-driven; ADR-0025 SKU ≠ groups
- No handwritten full-SQL except generated-column patch + down remap
- No drop of live orders indexes
- Production no downgrade past 037
