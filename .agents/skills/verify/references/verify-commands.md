# 验证命令参考

仓库没有 `platform_core/tests/`。数据契约测试在 `backend/tests`。覆盖率红线在 `pyproject.toml`：`fail_under = 70`（omit `*/tests/*`），CI 带 `--cov` 时生效。

## 验证命令矩阵

| 改动路径 | 类型 | 必跑命令 | 通过标准 |
|---------|------|---------|---------|
| `backend/services/**`、`backend/utils/**`、`backend/repositories/**` | 后端代码 | `uv run pytest -x -q backend/tests` | 退出码 0 |
| `backend/app/api/**`、`backend/app/external_api/**` | API 层 | 上条 pytest + 若增删路由则 `uv run pytest -x -q backend/tests/test_openapi_routes_golden.py`；需要活进程时 `uv run python run_backend.py --no-reload` + `curl -sS localhost:9111/api/v1/health` | pytest 0；health HTTP 200 |
| `platform_core/models/**`、`platform_core/schemas/**`、`backend/alembic/**` | 数据契约 / 迁移 | `uv run pytest -x -q backend/tests` + `bash scripts/check-arch.sh`；schema 变更走 `/db-design` | 测试 0 且红线 0 违规 |
| `platform_core/{logger,db,storage,exceptions,repository,tenant_context}.py` | 基建层 | `uv run python -c "from platform_core import init_log, init_db, init_storage; init_log(); init_db(); init_storage()"` + `bash scripts/check-arch.sh` | 无异常；红线 0 |
| `scrapy/**` | 爬虫 | `uv run python run_spider.py --list` | 列表含目标爬虫名 |
| `config/**`、`.env*`、`scrapy/settings.py` | 配置 | 重启对应服务 + `curl -sS localhost:9111/api/v1/health` | 服务启动 + 健康 OK |
| `Dockerfile`、`docker-compose.yml` | 容器 | `docker compose config --quiet`；镜像变更再 `docker build -t auto-agents-backend .` | 退出码 0 |
| `.github/workflows/**` | CI | 改的是现有 `.github/workflows/ci.yml`，推分支看 Actions | job 变绿 |
| `frontend/{admin,official,shared}/**` | 前端 | `bash scripts/check-frontend.sh` + `CI= npm run build -w {admin\|official\|@auto-agents/frontend-shared}` + `npm test -w {admin\|official}` | 退出码 0 |
| `frontend/admin/src/pages/{Login,Dashboard,Usage,Members}*` 或 e2e 夹具 | admin E2E | 先 `CI= npm run build -w admin`，再 `CI=1 npm run e2e -w admin`（`NO_PROXY=127.0.0.1,localhost,::1`，端口 `E2E_PORT` 默认 46112） | 1 passed |
| `pyproject.toml`、`uv.lock` | 依赖 / workspace | `uv lock --check` + `uv run ruff check backend platform_core scripts` | 锁一致；ruff 0 |
| `scripts/check-arch.sh`、`scripts/check-frontend.sh` | 门禁脚本 | 直接跑该脚本 | 退出码 0 |

## 生成类 Skill 产出物检查

| 触发 Skill | 产出物检查 | 附加验证命令 |
|------------|---------|----------|
| `/new-svc` | ORM / Schema / Service / Repository / Router 都在 + `v1/__init__.py` 已 `include_router` + `backend/tests/openapi_routes_golden.txt` 已更新 | `uv run pytest -x -q backend/tests/test_openapi_routes_golden.py` + `bash scripts/check-arch.sh` |
| `/new-spider` | `scrapy/spiders/{name}.py` 存在且 `run_spider.py --list` 含该 name；新字段在 `scrapy/items/` | `uv run python run_spider.py --list` + `bash scripts/check-arch.sh` |
| `/new-model` | ORM + Schema 配对 + `__init__.py` 已注册；租户表带 `TenantMixin` | `bash scripts/check-arch.sh` + `uv run python -c "from platform_core.models.{m} import {M}; from platform_core.schemas.{m} import {M}Out"` |
| `/db-design` | `db-spec.md` + DBML + 迁移走 autogenerate | `bash scripts/check-db-ir.sh` + `bash scripts/check-db-migrations.sh` |
| `/deploy` | 改的是仓库已有 `Dockerfile` / `docker-compose.yml`，不是另起一套 | `docker compose config --quiet` |

**判定规则**：产出物缺一个 = 未完成，禁止说"已完成"。

**并行原则**：独立命令在一次 Bash 里 `&` 并行或者一条消息里多个 tool call，禁止串行空等。

## 输出格式示例

把**实际 stdout/stderr 最后 20-50 行**贴回对话，禁止总结、禁止"大致通过"：

```
=== pytest -x -q ===
========= 42 passed in 3.1s =========

=== curl /api/v1/health ===
{"status":"healthy"}

=== uv run python run_spider.py --list ===
🕷️  可用爬虫列表
  • example
  • zhihu_feed
```

## 反模式自检

- ❌ "应该没问题" / "大概能跑" / "可能通过"
- ❌ "测试了，通过了"（不贴输出）
- ❌ "本地没装环境，跳过"
- ❌ "功能代码写完了，测试后面补"
- ❌ 跑不存在的 `platform_core/tests`
- ❌ 前端只 `cd frontend/admin && npm run build`（应用已是 npm workspaces：`npm run build -w admin`）
