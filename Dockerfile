# Auto Agents 镜像 - 多阶段构建（前端 workspaces + 后端运行时）
#
# 构建：docker build -t auto-agents-backend .
# 运行：见 docker-compose.yml（本地联调含 MySQL 8 + Redis 7）

# ===== Stage 1: 前端构建（shared dist → admin + official）=====
FROM node:20 AS frontend-builder

WORKDIR /build
COPY package.json package-lock.json .npmrc ./
COPY frontend/shared/package.json frontend/shared/package.json
COPY frontend/admin/package.json frontend/admin/package.json
COPY frontend/official/package.json frontend/official/package.json
RUN npm ci --no-audit --no-fund && echo 'NPM_CI_OK'

COPY frontend/shared/ frontend/shared/
RUN npm run build -w @auto-agents/frontend-shared && echo 'SHARED_BUILD_OK'

COPY frontend/admin/ frontend/admin/
RUN CI= npm run build -w admin && echo 'ADMIN_BUILD_OK'

COPY frontend/official/ frontend/official/
RUN CI= npm run build -w official && echo 'OFFICIAL_BUILD_OK'

# ===== Stage 2: 后端运行时 =====
FROM python:3.13-slim AS backend

RUN pip install --no-cache-dir uv

WORKDIR /app

# 完整源码一次 COPY（uv sync 需要包目录存在才能构建 workspace 成员的元数据）
COPY pyproject.toml uv.lock README.md ./
COPY backend/ backend/
COPY scrapy/ scrapy/
COPY platform_core/ platform_core/
# --locked：uv.lock 与 pyproject 不一致直接构建失败（不在镜像里悄悄重解析）
RUN uv sync --locked --package auto-agents-backend --no-dev && echo 'UV_SYNC_OK'

COPY config/ config/
COPY scripts/ scripts/

# 前端构建产物（静态资源，供后续 nginx/静态服务接入）
COPY --from=frontend-builder /build/frontend/admin/build /app/frontend-dist/admin
COPY --from=frontend-builder /build/frontend/official/build /app/frontend-dist/official

# 镜像安全缺省：
# - APP_ENV=prod 为部署缺省，运行时 -e APP_ENV=<env> 覆盖；
# - HOST 缺省 0.0.0.0：config/default/api.yml 的 127.0.0.1 是本机开发缺省，
#   容器内沿用会绑定回环 → 发布端口在容器外不可达
# - UV_NO_SYNC=1：运行期 `uv run` 只用构建好的 .venv，不再按根项目重新同步——否则容器每次启动
#   都会联网补装根项目的爬虫包与 dev 组（pytest / ruff / pip-audit / pre-commit 等 36 个包），
#   出网受限的生产环境直接起不来（compose 的 command 同样经 uv run，共用本变量）。
ENV APP_ENV=prod \
    AUTO_AGENTS_API__HOST=0.0.0.0 \
    UV_NO_SYNC=1
# 端口与 config/default/api.yml 的 API.PORT（9111）一致；config/prod 无 api.yml，
# 生产回落同值（改端口须三处同步：api.yml / EXPOSE / HEALTHCHECK）
EXPOSE 9111

# /api/v1/health/deep = MySQL SELECT 1 + Redis PING，任一失败 503
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9111/api/v1/health/deep', timeout=3)" || exit 1

CMD ["uv", "run", "python", "-m", "scripts.runlib.backend", "--no-reload"]
