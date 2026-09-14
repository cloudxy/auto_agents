# backend memory · post-merge-upgrade

> Facts this role learned (**what**). Cap **2200 characters**.

## Last

- Date: 2026-09-14
- Hat: backend
- Outputs: 047 SM-8 down rewrite; T-06-evidence.md append

## Facts

- GET `/capabilities`: tenant → `list_public`；超管 → `list_catalog`。Governance writes: `require_platform_admin_or_404`. Power-market switch stays 403.
- Checkout preview: gold + `can_pay=false` only when both alipay/wechat unconfigured **and** a pending exists. Duplicate pending `ORDER_PENDING_EXISTS`.
- BUG-V01 M12.8: GWT-70.1 fixture; 200001 tokens + plan_pro → POST /plan HTTP 200; free → `TASK_QUOTA_LIMIT_REACHED`. SQLite ThreadPool ≠ M11.12 done.
- **047 down (db-spec §8):** fill `orders.channel` NULL→`'offline'` first; restore pro `quota_json` to 040 seed `20/500000/5000000`; DELETE `plans.enterprise` only if no `orders.plan_id` / `tenant_subscriptions.plan_id`; then NOT NULL DEFAULT `'offline'`. `# 回填` on those executes. Do **not** DELETE NULL-channel orders.
- `bash tools/check/db_migrations.sh` **exit 0** after that rewrite. SM-8 绿 ≠ 047 up→down→up 已验。
- Full suite after W5: **1854 passed, 41 skipped**, arch.sh 0.

## Open (mine)

- `/auth/register` still joins default.
- Live unpaid path not in W2 write.
- 047 up→down→up on isolated MySQL currently at 046: still unverified (local `alembic_version=039`).

## Do not re-litigate

- Do not print 当前可买 / mark GA / live payment / C2 done.
- Do not restore three-ring pull on `/data/{spider}`.
- Do not change GWT. Empty ops / market UI copy is frontend.
- Do not treat SM-8 green as 047 rollback verified.
- Do not change coverage.md M11.12 to ✅.
