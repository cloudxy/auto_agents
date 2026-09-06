# 部署约束（不要复制一份第二 Dockerfile）

权威文件：

- 根 `Dockerfile`
- 根 `docker-compose.yml`

改它们时必须保持：

| 项 | 现行值 |
|----|--------|
| Python | 3.13-slim + `uv`（`uv sync --package auto-agents-backend --package auto-agents-spider --no-dev`） |
| Node 构建 | `node:20`，admin/official `CI= npm run build`，产物进 `/app/frontend-dist/` |
| 启动 | `uv run python run_backend.py --no-reload` |
| 端口 | `EXPOSE 9111`；`AUTO_AGENTS_API__HOST=0.0.0.0`（容器内禁止绑 127.0.0.1） |
| 健康检查 | `GET /api/v1/health/deep` |
| Compose 服务 | `mysql`（mysql:8）+ `redis`（redis:7-alpine）+ `backend`（`9111:9111`） |
| 配置注入 | `APP_ENV` + `AUTO_AGENTS_MYSQL__DEFAULT__HOST=mysql` 这类双下划线 |
| LiteLLM | 仅 `profiles: ["litellm"]`，`LITELLM.ENABLED` / `ROUTE_INTERNAL` / `ADMIN.ENABLED` 默认 false |

禁止出现在新改动里：

- `FROM python:3.11`
- `COPY requirements.txt` / `pip install -r requirements.txt`
- `uvicorn main:app --port 8000`
- 前端 `COPY --from=builder /app/dist`（CRA 产物目录是 `build/`）
- 把 LiteLLM / delivery webhook 改成默认开
