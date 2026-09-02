# syntax=docker/dockerfile:1
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

# uv workspace 解析需要根配置 + 全部成员 manifest（含 README：包构建 readme 字段引用）
COPY pyproject.toml uv.lock README.md ./
COPY backend/pyproject.toml backend/
COPY scrapy/pyproject.toml scrapy/
# uv export 导出全量 requirements 后 pip install——绕过 Docker 内 workspace 可编辑构建
# （macOS ARM64 lockfile 在 Linux x86_64 的 uv sync --frozen 存在解析差异）
RUN uv export --package auto-agents-backend --no-dev --no-hashes --format requirements-txt -o /tmp/req.txt \
    && echo 'EXPORT_OK' \
    && pip install --no-cache-dir -r /tmp/req.txt && echo 'PIP_INSTALL_OK'

# 应用源码（platform_core 为源码包，经 run_backend.py 注入 sys.path）
COPY backend/ backend/
COPY platform_core/ platform_core/
COPY config/ config/
COPY run_backend.py ./

# 前端构建产物（静态资源，供后续 nginx/静态服务接入）
COPY --from=frontend-builder /build/admin/build /app/frontend-dist/admin
COPY --from=frontend-builder /build/official/build /app/frontend-dist/official

ENV APP_ENV=prod
EXPOSE 9111

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9111/api/v1/health', timeout=3)" || exit 1

CMD ["python", "run_backend.py", "--no-reload"]
