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
| lint | `uv run ruff check backend platform_core scripts` |
| 架构 | `bash tools/check/arch.sh` |
| 前端 lock | 根 `package-lock.json` + `npm ci` |
| 前端构建 | 先 `npm run build -w @auto-agents/frontend-shared`，再 `-w admin` / `-w official` |
| OpenAPI | `uv run python tools/dump_openapi.py` + `npm run codegen:api -w @auto-agents/frontend-shared` |
| 前端门禁 | `bash tools/check/frontend.sh` |
| compose | `docker compose config --quiet` |
| 镜像 | `docker build -t auto-agents-backend .` |
| JWT（CI） | `AUTO_AGENTS_JWT__SECRET_KEY` |

## MySQL 保真通道

`python-lint-test` 挂 `mysql:8`。第二段 pytest 需要 `MYSQL_FIDELITY=1` 及 HOST/USER/PASSWORD。子集文件名单以 `ci.yml` 为准。

## 本地门禁

`.pre-commit-config.yaml`：提交跑 ruff + `tools/check/arch.sh` + db 脚本；推送再跑 pytest。

## 部署

默认 CI 不含 SSH `docker compose up`。发布另开 job，密钥用 GitHub Secrets。
