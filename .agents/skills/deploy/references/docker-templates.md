# 部署约束

权威文件：`Dockerfile`、`docker-compose.yml`、`.env.example`、`init_project.sh`。

## Contents

- 镜像
- compose
- 环境变量
- 命令

## 镜像

| 项 | 值 |
|----|----|
| 前端 | `FROM node:20`；`npm ci`；先 `npm run build -w @auto-agents/frontend-shared`，再 admin / official |
| 后端 | `FROM python:3.13-slim` + `uv`；`uv sync --package auto-agents-backend --no-dev` |
| 启动 | `uv run python -m scripts.runlib.backend --no-reload` |
| 端口 | `EXPOSE 9111` |
| 健康检查 | `http://127.0.0.1:9111/api/v1/health/deep` |
| 依赖 | `pyproject.toml` + `uv.lock` |

容器内 `AUTO_AGENTS_API__HOST=0.0.0.0`。

## compose

| 服务 | 构建 | 宿主端口 |
|------|------|---------|
| mysql | `mysql:8` | 3306 |
| redis | `redis:7-alpine` | 6379 |
| backend | `build: .` | 9111 |

backend command：`uv run python -m scripts.runlib.backend --no-reload --env local`。开发默认密码对齐 `init_project.sh`。

## 环境变量

```
APP_ENV=local
AUTO_AGENTS_API__HOST=0.0.0.0
AUTO_AGENTS_API__PORT=9111
AUTO_AGENTS_MYSQL_DEFAULT_PASSWORD=...
AUTO_AGENTS_REDIS_DEFAULT_PASSWORD=...
AUTO_AGENTS_JWT__SECRET_KEY=...
AUTO_AGENTS_WEBHOOK__SECRET_KEY=...
```

密钥写 `config/<env>/.env`。完整清单：根 `.env.example`。

## 命令

```bash
docker compose config --quiet
docker compose up --build
docker compose logs -f backend
docker compose down
```

冻住不退出的 watchdog：`deploy/watchdog.sh`。
