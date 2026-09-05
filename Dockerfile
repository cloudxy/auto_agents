# Auto Agents 镜像 - 多阶段构建（前端构建 + 后端运行时）
#
# 构建：docker build -t auto-agents-backend .
# 运行：见 docker-compose.yml（本地联调含 MySQL + Redis）

# ===== Stage 1: 前端构建（admin + official）=====
FROM node:20 AS frontend-builder

WORKDIR /build/admin
COPY frontend/admin/package.json frontend/admin/package-lock.json ./
RUN npm ci --no-audit --no-fund && echo 'ADMIN_CI_OK'
COPY frontend/admin/ ./
RUN CI= npm run build && echo 'ADMIN_BUILD_OK'

WORKDIR /build/official
COPY frontend/official/package.json frontend/official/package-lock.json ./
RUN npm ci --no-audit --no-fund && echo 'OFFICIAL_CI_OK'
COPY frontend/official/ ./
RUN CI= npm run build && echo 'OFFICIAL_BUILD_OK'

# ===== Stage 2: 后端运行时 =====
FROM python:3.13-slim AS backend

RUN pip install --no-cache-dir uv

WORKDIR /app

# 完整源码一次 COPY（uv sync 需要包目录存在才能构建 workspace 成员的元数据）
COPY pyproject.toml uv.lock README.md ./
COPY backend/ backend/
COPY scrapy/ scrapy/
COPY platform_core/ platform_core/
RUN uv sync --package auto-agents-backend --no-dev && echo 'UV_SYNC_OK'

COPY config/ config/
COPY run_backend.py ./

# 前端构建产物（静态资源，供后续 nginx/静态服务接入）
COPY --from=frontend-builder /build/admin/build /app/frontend-dist/admin
COPY --from=frontend-builder /build/official/build /app/frontend-dist/official

# 镜像安全缺省（T11）：
# - APP_ENV=prod 为部署缺省（生产部署时必须按 docs/ops/deploy.md 显式确认），
#   运行时 -e APP_ENV=<env> 覆盖；
# - HOST 缺省 0.0.0.0：config/default/api.yml 的 127.0.0.1 是本机开发缺省，
#   容器内沿用会绑定回环 → 发布端口在容器外不可达（独立 docker run 直跑陷阱）
ENV APP_ENV=prod \
    AUTO_AGENTS_API__HOST=0.0.0.0
# 端口与 config/default/api.yml 的 API.PORT（9111）一致；config/prod 无 api.yml，
# 生产回落同值（改端口须三处同步：api.yml / EXPOSE / HEALTHCHECK）
EXPOSE 9111

# 深探测（T11）：/api/v1/health/deep = MySQL SELECT 1 + Redis PING，
# 任一失败返回 503 → 探测失败。旧浅探测 /api/v1/health 恒 200，
# DB/Redis 挂掉仍判定"健康"
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9111/api/v1/health/deep', timeout=3)" || exit 1

CMD ["uv", "run", "python", "run_backend.py", "--no-reload"]
