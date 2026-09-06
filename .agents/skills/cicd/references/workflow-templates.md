# CI 现行结构（权威：`.github/workflows/ci.yml`）

不要把下面复制成新文件。加步骤时对号入座。

| job | 做什么 |
|-----|--------|
| `python-lint-test` | `uv python install 3.13`；`uv run ruff check backend platform_core scripts`；`uv run pytest -x -q --cov=backend --cov=platform_core --cov-fail-under=70 backend/tests`；`MYSQL_FIDELITY=1 pytest -m mysql_fidelity` |
| `arch-check` | `bash scripts/check-arch.sh`（13 红线 + 3 边界） |
| `db-migration-gate` | `scripts/check-db-ir.sh` + `scripts/check-db-migrations.sh` |
| `frontend-build` | 根 `npm ci`；shared codegen/build；`bash scripts/check-frontend.sh`；`CI= npm run build -w admin` / `official`；`npm test -w admin` / `official`；`npm run e2e -w admin`（`CI=true`，`NO_PROXY=127.0.0.1,localhost,::1`） |
| `docker-validate` | `docker compose config --quiet` + `docker build -t auto-agents-backend .` |
| `ghcr-publish` | 仅 push `main` 或 tag：`ghcr.io/<repo>:git-$SHA` |

本地门禁（`.pre-commit-config.yaml`）：提交跑 ruff + `check-arch` + db 脚本；`pre-push` 跑 `pytest backend/tests`。

加新检查时：

1. 能进现有 job 的不要新 job
2. 架构类进 `scripts/check-arch.sh` 或 `check-frontend.sh`，不要在 YAML 里再写一套 grep
3. `pip-audit` / `npm audit` 目前 `continue-on-error: true`，改强制红之前先确认噪声

禁止再引入：`uv python install 3.11`、`pytest platform_core/tests`、`setup-uv@v3` 当新标准、按 `frontend/${{ matrix.app }}` 各自 `npm ci`（lock 已在仓库根）。
