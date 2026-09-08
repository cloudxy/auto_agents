# qa memory · feat-four-pillars-v2

> Facts (**what**). How stays in SKILL.md. Cap 2200 chars.

## Last

- Date: 2026-09-08
- Hat: 定义 / 并行诊断
- Outputs: `.sdlc/feat-four-pillars-v2/01-define/diagnosis/qa.md`

## Facts

- Suite 2026-09-08: pytest 103/1050; Jest 7/16; e2e null.
- grok-files qa-diagnosis == old sdlc qa.md (2026-09-07). Stale vs spec v1.4 on QA-02 (`GWT-15.1` has `is_marketplace_candidate`).
- Findings: round 3 fail QA-29; no round 4. v1.4 self-close ≠ gate.
- Conflicts still in code:
  - `test_scan_plugins_ok` locks viewer 200 (`viewer_client` override + `db_client.post`); `capabilities.py` all `require_login`; scan has no audit.
  - `admin_client` = `role=admin, is_platform_admin=False` → `require_platform_admin` 403. Pattern: `test_create_tenant_plain_admin_403`.
  - `/public/capabilities` SQL `status=stable`; `/public/skills` includes recommended. `only_stable` seed has no recommended row.
  - `test_plugin_verify_no_mcp_degraded` locks `degraded`; CONTEXT/ADR-0018 say `unknown`.
  - No `btn:market:*`. Admin scan/verify no `usePermission`.
  - `listing_state`/installs/sources: 0 backend hits. `ALL_ORM_TABLES`=40; fidelity comment “14 tables”. MYSQL_FIDELITY 8 files exclude b1c/public.
- XSS only in `SkillsSquare.test.tsx`. Migrate before deleting page.
- Hollow: `or True` wiring/byok; harvester empty-tuple; EXPLAIN on dict.
- Did not write `04-verify/coverage.md`. Did not edit tests.

## Open (mine)

- v2 spec must pin diagnosis §8 (identity, public formula, `/public/skills` fate, no-MCP enum, host_compat NULL vs [], pairwise, MYSQL_FIDELITY on new uniques) or cases stay pending GWT.
- Q-VOICE/Q-PRICE block positive CTA asserts.

## Do not re-litigate

- Suite counts (re-collected 2026-09-08).
- `admin_client` ≠ platform admin.
- Old qa.md QA-02 blocker vs v1.4 text.
- No full FR↔TC matrix until v2 spec frozen.
