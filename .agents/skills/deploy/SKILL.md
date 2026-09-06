---
name: deploy
description: >-
  生成 Docker 部署配置。当用户需要将项目部署到服务器、进行容器化打包、
  生成或修改 Dockerfile / docker-compose.yml / .env 配置时触发。
  适用于首次部署、环境迁移、新增服务的容器化，以及调整端口映射、
  环境变量、数据卷等配置的场景。
trigger: >-
  部署到服务器、生成 Docker 配置、容器化项目、环境迁移、
  调整端口映射/环境变量/数据卷、首次部署或新增服务容器化
---

# Docker 部署配置

仓库**已经有**根 `Dockerfile` 和 `docker-compose.yml`。本 skill 是改这两份文件，不是再生成 python:3.11 + `requirements.txt` + uvicorn 8000。

约束清单见 [references/docker-templates.md](references/docker-templates.md)。

## 触发场景

- "帮我部署到服务器"
- "生成 Docker 配置"
- "容器化这个项目"

## 执行流程

### Step 1: 确认

1. 环境（local compose 联调 / 生产镜像）
2. 是否需要改端口（默认 API **9111**，与 `config/default/api.yml` / `EXPOSE` / HEALTHCHECK 三处同步）
3. 是否动 LiteLLM sidecar（compose `profiles: ["litellm"]`，**默认关**，不要改成默认开）

### Step 2: 改现有文件

| 文件 | 用途 |
|------|------|
| `Dockerfile` | 多阶段：Node 20 编 admin+official → python:3.13-slim + uv；`CMD uv run python run_backend.py --no-reload` |
| `docker-compose.yml` | mysql + redis + backend；可选 litellm profile |
| `config/<env>/.env` | 密钥，不入库 |

不要新建 `backend/Dockerfile`、`frontend/*/Dockerfile`、根 `requirements.txt`。

生产步骤以 `docs/ops/deploy.md`（本地私有）为准，不要在 compose 里写生产密码。

## 验证

```bash
docker compose config --quiet
docker build -t auto-agents-backend .
```

本地联调：`docker compose up --build`。不要用已退役的 `docker-compose` 连字符命令当唯一入口。
