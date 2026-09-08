# sre memory · feat-four-pillars-v2

> Facts (**what**). Procedures in SKILL.md. Cap 2200 chars.

## Last

- Date: 2026-09-08
- Hat: 定义 / sre 诊断
- Outputs: `.sdlc/feat-four-pillars-v2/01-define/diagnosis/sre.md`

## Facts

- HEAD `5d2e600`. Deploy/compose/Dockerfile/CI/litellm unchanged vs old diagnosis `44e9446`.
- Root compose: mysql, redis, backend. No Worker. `run.py all` no spider. Redis no volume.
- `docs/` gitignored; `docs/ops/deploy.md` 404. watchdog hint points there.
- litellm `config.gen.yaml` tracked, not ignored, 7× `sk-` (do not paste keys).
- `POWER_MARKET` runtime hits = 0. `/health/deep` = MySQL+Redis only. Notify = `[log]`.
- new-api on `newapi-net`; missing `.env` → `SESSION_SECRET is required`. Backend not on that net; BASE_URL localhost:3000.
- Dockerfile copies missing per-app lockfiles; only root `package-lock.json`. admin.json has no frontend-shared.
- MySQL `_get_password` reads flat `MYSQL_DEFAULT_PASSWORD`; prod nested `__DEFAULT__PASSWORD` ignored.
- `migrate.sh` upgrade only. `024`/`027` down not in CI.
- Old contract deferred Worker compose to Wave 4. grok-files W0-9 wanted spider in compose. v2 must not copy deferral.
- Did not edit deploy. Did not write `06-deliver/checklist.md`. Rollback unverified.
- Root `docker compose config --quiet` exit 0. `docker build` not run.

## Open (mine)

- Prod shape: compose vs multi-host vs k8s.
- On-call channel / who pages.
- LiteLLM keep vs delete+rotate; filter-repo?
- Redis persist? Password key canonical form?
- Wave 0 Worker: compose vs `run.py all` vs empty-state (process or hard stop).
- Tag policy; ARM images to prod?

## Do not re-litigate

- new-api stays sidecar (do not merge into root compose).
- Power Market in-process (ADR-0010) does not cancel Worker as a process.
- Secrets never in git; no litellm key paste.
- Alerts without runbooks do not ship. `docs/` is not runbook home.
