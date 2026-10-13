# CI 五阶段

权威文件：`.github/workflows/ci.yml`。改 CI 时对照现有 yaml。

## Contents

- 必须对齐的事实
- MySQL 保真通道
- 本地门禁
- 部署

## 必须对齐的事实

| 项 | 值 |
|----|----|
| uv | `astral-sh/setup-uv@v6` + `uv python install 3.13` + `uv sync` |
| 测试 | `uv run pytest -x -q --tb=short backend/tests` |
| lint | `uv run ruff check .`（全仓，E9 + F） |
| 架构 | `bash tools/check/arch.sh`（R1–R13 + B1–B4 + FR-14 + PL + SZ） |
| 前端 lock | 根 `package-lock.json` + `npm ci`（无 `.npmrc` legacy-peer-deps） |
| Node | `actions/setup-node@v4` + `node-version: 24`（frontend-build / security-audit） |
| 前端构建 | 先 `npm run build -w @auto-agents/frontend-shared`，再 `-w admin` / `-w official`（`tsc --noEmit` + `vite build`） |
| OpenAPI | `uv run python tools/dump_openapi.py` + `npm run codegen:api -w @auto-agents/frontend-shared` |
| 前端门禁 | `bash tools/check/frontend.sh`（CI 里设 `CHECK_FRONTEND_LINT=0`，ESLint 走独立步骤） |
| 前端 lint | `npm run lint -w admin` / `npm run lint -w official` |
| npm 审计 | `npm audit --audit-level=high`（全量依赖） |
| compose | `docker compose config --quiet` |
| 镜像 | `docker build -t auto-agents-backend .` |
| JWT（CI） | `AUTO_AGENTS_JWT__SECRET_KEY` |

## MySQL 保真通道

`python-lint-test` 挂 `mysql:8`。第二段 pytest 需要 `MYSQL_FIDELITY=1` 及 HOST/USER/PASSWORD。子集文件名单以 `ci.yml` 为准；`backend/tests/test_ci_fidelity_manifest.py` 守护名单——按 `MYSQL_FIDELITY` 门控的测试文件没登记，普通通道即红。

## 本地门禁

`.pre-commit-config.yaml`：提交跑 ruff + `tools/check/arch.sh` + db 脚本；推送再跑 pytest。

## 部署

默认 CI 不含 SSH `docker compose up`。发布另开 job，密钥用 GitHub Secrets。
