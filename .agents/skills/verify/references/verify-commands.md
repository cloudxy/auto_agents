# 验证命令参考

启停：`uv run python run.py start|stop|restart|status`。测试：`uv run pytest -x -q backend/tests`。

## 命令矩阵

| 改动路径 | 必跑 | 通过 |
|---------|------|------|
| `backend/services/**`、`backend/repositories/**`、`backend/utils/**` | `uv run pytest -x -q backend/tests` | 退出码 0 |
| `backend/app/api/**`、`backend/app/external_api/**` | 同上；`uv run python run.py start backend`；`curl -sS localhost:9111/api/v1/health` | 测试绿 + HTTP 200 |
| `platform_core/models/**`、`platform_core/schemas/**` | pytest + `bash tools/check/arch.sh` | 测试绿 + 红线 0 |
| `platform_core/{logger,db,storage,exceptions,repository}.py` | `uv run python -c "from platform_core import init_log, init_db, init_storage; init_log(); init_db(); init_storage()"` + pytest | 无异常 + 测试绿 |
| `scrapy/**` | `uv run python run.py --list` + `bash tools/check/arch.sh` | 列表含目标爬虫 |
| `config/**`、`scrapy/settings.py` | `uv run python run.py restart <服务>` + health | 启动且 health OK |
| `Dockerfile`、`docker-compose.yml` | `docker compose config --quiet`；Dockerfile 有改再 `docker build -t _verify .` | 退出码 0 |
| `.github/workflows/**` | 对照 `.github/workflows/ci.yml` 五阶段 | job 绿 |
| `frontend/**` | `npm run build:shared`；`bash tools/check/frontend.sh`；`CI= npm run build -w admin`；`CI= npm run build -w official`（依赖变则先 `npm ci`）。改了 UI/布局/路由/状态：构建之外按真实路径点一遍（点击/输入/提交/跳转）；只截图不算。无浏览器则写明哪条路径没点到 | 退出码 0；UI 改动要行为一致 |
| `pyproject.toml`、`uv.lock` | `uv lock --check` + pytest | 锁一致 + 测试绿 |
| `init_project.sh`、`scripts/**`、`run.py` | `uv run pytest -x -q backend/tests/test_run_orchestrator.py` | 退出码 0 |
| `tools/check/**` | 跑被改的脚本 | 退出码符合预期 |

前端从仓库根走 npm workspaces。`run.py start` 已在跑则跳过。

## 生成类产出物

| Skill | 检查 |
|-------|------|
| `/new-svc` | ORM / Schema / Service / Repository / Router + `v1/__init__.py` 已 include + `backend/tests/test_{module}_service.py` |
| `/new-spider` | `scrapy/spiders/{name}.py`；新字段才改 `scrapy/items/__init__.py`；`run.py --list` 含 name |
| `/new-model` | ORM + Schema + models/schemas 两处 `__init__.py` 导出；`bash tools/check/arch.sh` |
| `/db-design` | `.scratch/<feature>/db-spec.md` 访问模式有行；`db_ir.sh` / `db_migrations.sh` |
| `/deploy` | 改根 `Dockerfile` / `docker-compose.yml` / `.env.example`；`docker compose config --quiet` |

## 输出格式

```
=== pytest -x -q ===
========= 42 passed in 3.1s =========

=== curl /api/v1/health ===
{"status":"healthy"}

=== uv run python run.py --list ===
可用爬虫:
  • example
  • zhihu_feed
```
