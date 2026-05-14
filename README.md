# Auto Agents

> 多应用混合平台：**FastAPI 后端 + Scrapy 分布式爬虫 + React 双端（官网 / 后台管理）**，统一配置、统一基础设施、独立部署。

---

## 目录

- [架构总览](#架构总览)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [启动入口](#启动入口)
- [依赖管理](#依赖管理uv-workspace)
- [配置管理](#配置管理)
- [API 设计](#api-设计)
- [爬虫体系](#爬虫体系)
- [前端体系](#前端体系)
- [开发规范](#开发规范)
- [运维脚本](#运维脚本)

---

## 架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│                        Auto Agents Platform                       │
├───────────────┬──────────────────┬──────────────┬────────────────┤
│  frontend/    │   backend/       │   scrapy/    │ platform_core/ │
│  admin (3001) │   FastAPI (9111) │  分布式爬虫  │   公共基建层   │
│  official(3002│   API v1/v2      │  scrapy-redis│  db/log/store  │
└───────────────┴────────┬─────────┴──────┬───────┴────────┬───────┘
                         │                │                │
                         └─────── config/ (Dynaconf) ──────┘
                                  │
                         default → <env> → .env → 环境变量
```

**核心原则**

| 价值观 | 落地 |
|--------|------|
| 配置即代码 | 所有连接串、密钥、端口外置到 `config/`，按 `local/dev/prod` 隔离 |
| 日志即证据 | Loguru 多 logger 路由（`global / api / admin / official / spider / error`） |
| 独立部署优于耦合 | 本地开发统一 venv（uv workspace），部署时各子项目可独立 `uv sync --package` |
| 爬取与存储分离 | 爬虫只采集清洗，**禁止直写主库**，通过 Redis 队列流向后端 |
| 模型即契约 | ORM = 数据库契约（`platform_core/models`），Pydantic = 接口契约（`platform_core/schemas`），互不 import |

详见 `.claude/rules/project_rule.md`。

---

## 项目结构

```
auto_agents/
├── pyproject.toml               # uv workspace 根配置（members: backend, scrapy）
├── uv.lock                      # 统一锁文件（提交到仓库）
├── .venv/                       # 统一虚拟环境（uv sync 自动创建）
│
├── run.py                       # 统一编排器（all / backend / spider / frontend）
├── run_backend.py               # 后端单独启动（自动切根 .venv）
├── run_spider.py                # 爬虫单独启动（共用根 .venv）
├── run_frontend.py              # 前端单独启动（admin + official 并行）
│
├── backend/                     # FastAPI 后端（workspace member）
│   ├── app/
│   │   ├── __init__.py          # create_app() 工厂
│   │   ├── api/                 # 内部 API：/api/v1, /api/v2
│   │   │   ├── v1/              # auth / spiders / admin / configs / health / root
│   │   │   └── v2/              # 增强健康检查（含 db/storage 探针）
│   │   ├── external_api/        # 外部 API：/external/v1（API Key 认证）
│   │   ├── middleware/          # RequestID 中间件等
│   │   └── responses/           # 统一响应模型
│   ├── services/                # 业务逻辑（auth / spider / config）
│   ├── repositories/            # 数据访问（继承 platform_core.repository）
│   ├── alembic/                 # 数据库迁移
│   ├── utils/                   # auth 工具等
│   └── pyproject.toml           # 后端依赖声明（部署时可独立 sync）
│
├── scrapy/                      # Scrapy 分布式爬虫（workspace member）
│   ├── settings.py              # 入口配置（从 config/ 注入参数）
│   ├── spiders/                 # 爬虫实现（example/zhihu/dianping/openweather…）
│   ├── middlewares/             # 反爬中间件（UA/代理/指纹/会话/重试）
│   ├── pipelines/               # 清洗 → 校验 → 入库（Redis）
│   ├── items/                   # 数据契约
│   ├── utils/                   # session_manager / redis_client / logger
│   └── pyproject.toml           # 爬虫依赖声明（部署时可独立 sync）
│
├── platform_core/               # 公共基础设施层（源码包，被 backend & scrapy 共享）
│   ├── logger.py                # Loguru 多 logger 路由
│   ├── db.py                    # MySQL（sync+async）+ Redis 连接管理
│   ├── storage.py               # 本地文件存储（cache/uploads/exports/temp）
│   ├── exceptions/              # 统一异常 + FastAPI handler
│   ├── repository.py            # 通用 BaseRepository[Model]
│   ├── models/                  # 共享 ORM（user / spider_task / system_config）
│   └── schemas/                 # 共享 Pydantic（auth / spider / validators）
│
├── config/                      # Dynaconf 统一配置（backend & scrapy 共用）
│   ├── default/                 # 通用默认（settings/api/web/log/jwt/storage/admin/official）
│   ├── local/  dev/  prod/      # 环境覆盖（mysql/redis/web/log/settings + .env）
│   └── scrapy/                  # 爬虫专属（按相同 default/local/dev/prod 分层）
│       ├── default/             # settings.yml / sites.yml（站点反爬策略）
│       └── <env>/
│
├── frontend/                    # 前端双端（React 19 + TS）
│   ├── admin/                   # 后台管理（Ant Design + Zustand + React Query）
│   └── official/                # 官方网站（Ant Design + Framer Motion）
│
├── scripts/                     # 运维脚本（init-db / migrate / start / run-spider）
├── logs/                        # 运行时日志（按 logger 名分目录）
├── files/                       # 上传/下载/导出文件
├── runtime/                     # 缓存、会话等运行时数据
└── .claude/                     # 项目规则与技能（rules + skills）
```

---

## 快速开始

### 前置依赖

| 工具 | 版本 | 用途 |
|------|------|------|
| Python | 3.13+ | 后端 / 爬虫 |
| Node.js | 18+ | 前端 |
| MySQL | 8.0+ | 主数据存储 |
| Redis | 6+ | 队列调度 / 缓存 |
| uv | 最新 | 依赖管理（推荐） |

### 1. 安装依赖

```bash
# Python 依赖：根目录一把梭，自动装齐 backend + scrapy 全部依赖到 .venv/
uv sync

# 前端
cd frontend/admin && npm install && cd ../..
cd frontend/official && npm install && cd ../..
```

> 不再需要 `cd backend && uv sync`——uv workspace 已统一管理。给某个子项目加包用 `uv add --package auto-agents-backend <pkg>` 或 `uv add --package auto-agents-spider <pkg>`。

### 2. 初始化数据库

```bash
# 创建库与用户
bash scripts/init-db.sh

# 执行迁移
bash scripts/migrate.sh
```

### 3. 启动

```bash
# 一键启动后端 + 双前端
python run.py all

# 或分别启动
python run.py backend                       # 后端 → http://127.0.0.1:9111
python run.py frontend --all                # 双前端 → 3001 / 3002
python run.py spider --list                 # 列出可用爬虫
python run.py spider --spider example       # 运行指定爬虫
```

### 4. 访问

| 服务 | 地址 |
|------|------|
| 后端 API 文档 | http://127.0.0.1:9111/api/docs |
| 后端健康检查 | http://127.0.0.1:9111/api/v1/health |
| 后台管理 | http://127.0.0.1:3001 |
| 官方网站 | http://127.0.0.1:3002 |

---

## 启动入口

### `run.py` —— 统一编排器

纯 orchestrator，fork 子进程统一日志、信号、关停。**不做依赖安装、不跑迁移**——那是 `scripts/` 的活。

```bash
python run.py all                           # backend + 双前端
python run.py all --env dev                 # 指定环境
python run.py backend --no-reload           # 关闭热重载
python run.py backend --port 9200           # 临时改端口
python run.py spider --spider zhihu_feed
python run.py frontend --app admin
```

### 单独入口

| 脚本 | 用途 | 关键特性 |
|------|------|----------|
| `run_backend.py` | 启动 FastAPI | 自动切根 `.venv`、端口预检、串行初始化 logger→db→storage→app |
| `run_spider.py` | 启动 Scrapy | 自动切根 `.venv`，注入 `sys.path`，`SCRAPY_SETTINGS_MODULE=settings`；支持 `--list / --spider <name>` |
| `run_frontend.py` | 启动前端 | 端口预检、自动 `npm install`、并行启动、按应用名加日志前缀 |

所有入口都接受 `--env {local,dev,prod}`，会透传为 `APP_ENV`（前端透传为 `REACT_APP_ENV`）。

---

## 依赖管理（uv workspace）

本项目采用 **uv workspace** 统一管理 Python 依赖：根目录一个 `.venv`，`backend/` 和 `scrapy/` 作为 workspace member 各自保留 `pyproject.toml`，依赖声明分散、安装环境统一。

### 结构

```
pyproject.toml          # 根：[tool.uv.workspace] members = ["backend", "scrapy"]
uv.lock                 # 根：统一锁文件（提交到仓库）
.venv/                  # 根：统一虚拟环境
backend/pyproject.toml  # 后端依赖声明（部署可独立 sync）
scrapy/pyproject.toml   # 爬虫依赖声明（部署可独立 sync）
platform_core/          # 源码包，不打包，由 sys.path 引入
```

### 常用命令

```bash
# 一次装齐所有依赖（在仓库任意层级执行均可）
uv sync

# 给 backend 加包
uv add --package auto-agents-backend fastapi-pagination

# 给 scrapy 加包
uv add --package auto-agents-spider playwright

# 跑命令（自动用根 .venv）
uv run python run_backend.py
uv run python run_spider.py --spider example
uv run alembic -c backend/alembic.ini upgrade head
```

### 部署时的独立性

虽然本地用统一 venv，**生产部署时仍可按子项目独立打包**：

```bash
# 后端镜像
uv sync --package auto-agents-backend --no-dev

# 爬虫镜像
uv sync --package auto-agents-spider --no-dev
```

子项目的 `pyproject.toml` 仍然是各自的依赖契约——workspace 只是本地开发的便利层。

### 常见坑

- 若 shell 残留 `VIRTUAL_ENV` 指向旧的 `backend/.venv`，`uv sync` 会困惑。先 `unset VIRTUAL_ENV UV_PROJECT_ENVIRONMENT`，或直接用 `uv run` 让 uv 自己接管。
- `platform_core/` 不需要 pyproject——它通过 `sys.path` 被 backend / scrapy 引入，不参与打包。

---

## 配置管理

### 加载顺序（后者覆盖前者）

```
1. config/default/*.yml           通用默认
2. config/scrapy/default/*.yml    爬虫默认
3. config/<env>/*.yml             环境覆盖（local / dev / prod）
4. config/scrapy/<env>/*.yml      爬虫环境覆盖
5. config/<env>/.env              敏感变量（密码、密钥）
6. AUTO_AGENTS_* 环境变量          最高优先级
```

### 默认配置清单（`config/default/`）

| 文件 | 内容 |
|------|------|
| `settings.yml` | APP_NAME / VERSION / ENVIRONMENT |
| `api.yml` | API.HOST / PORT (9111) / DEBUG |
| `web.yml` | CORS 白名单与策略 |
| `log.yml` | 多 logger 路由（global/api/admin/official/spider/error） |
| `storage.yml` | 缓存 / 上传 / 导出 / 临时目录 + 上传限制 |
| `jwt.yml` | SECRET_KEY / 算法 / 过期时间 |
| `admin.yml` | 后台管理端配置（端口 9112、分页、导出） |
| `official.yml` | 官网配置（端口 9113、SEO） |
| `mysql.yml` / `redis.yml` | 各环境覆盖（默认放在 `local/dev/prod/`） |

爬虫配置在 `config/scrapy/`，含 `settings.yml`（并发/延迟/中间件/管道）和 `sites.yml`（每个目标站点的反爬策略）。

### 使用配置

```python
from config import settings, APP_ENV

settings.APP_NAME              # "Auto Agents"
settings.API.PORT              # 9111
settings.MYSQL.DEFAULT.HOST    # "127.0.0.1"
settings.REDIS.DEFAULT.URL     # "redis://127.0.0.1:6379/0"（自动注入）
settings.JWT.SECRET_KEY
APP_ENV                        # "local" / "dev" / "prod"
```

### 切换环境

```bash
APP_ENV=dev  python run.py backend
APP_ENV=prod python run.py all
```

或用 `--env`：`python run.py backend --env prod`。

### 敏感信息

**禁止**在 yml 里写明文密码。在 `config/<env>/.env` 中放：

```env
AUTO_AGENTS_MYSQL__DEFAULT__PASSWORD=xxx
AUTO_AGENTS_REDIS__DEFAULT__PASSWORD=xxx
AUTO_AGENTS_JWT__SECRET_KEY=xxx
```

`.env` 已在 `.gitignore` 中。

---

## API 设计

### 双通道结构

```
/api/v1/*      内部 API   面向管理后台、官网、内部服务
/api/v2/*      内部 API   增强版（含 db/storage 健康探针）
/external/v1/* 外部 API   面向第三方集成、Webhook（API Key 认证）
```

### V1 路由（`backend/app/api/v1/`）

| 模块 | 前缀 | 职责 |
|------|------|------|
| `auth.py` | `/auth` | 登录、刷新 token、登出 |
| `root.py` | `/` | 根路由 |
| `health.py` | `/health` | 存活探针 |
| `spiders.py` | `/spiders` | 爬虫任务管理 |
| `admin.py` | `/admin` | 后台管理接口 |
| `configs.py` | `/configs` | 系统配置读写 |

### V2 增强（`backend/app/api/v2/`）

- `GET /api/v2/` 版本信息
- `GET /api/v2/health` 含响应时间
- `GET /api/v2/health/db` MySQL + Redis 探针
- `GET /api/v2/health/storage` 存储系统检查

### 新增 API 版本

1. 创建 `backend/app/api/v3/`
2. 在 `backend/app/api/__init__.py` 注册
3. 实现新版业务

---

## 爬虫体系

### 设计原则

> 爬虫是生产者，后端是消费者，中间用 **Redis 队列** 解耦。

- ❌ 禁止 `from backend.* import ...`
- ❌ 禁止 SQLAlchemy Session 直写主库
- ✅ 通过 `scrapy_redis.pipelines.RedisPipeline` 推送，后端消费

### 反爬五件套（中间件按优先级）

| 优先级 | 中间件 | 作用 |
|--------|--------|------|
| 250 | `AccountSessionMiddleware` | 会话/账号池管理 |
| 300 | `FingerprintMiddleware` | 浏览器指纹伪造 |
| 350 | `ProxyMiddleware` | IP 代理池 |
| 400 | `UserAgentMiddleware` | UA 轮换 |
| 550 | `RetryMiddleware` | 重试（429/5xx） |

### 数据流（Pipeline）

```
RedisPipeline (100) → CleanPipeline (200) → ValidatePipeline (300) → StorePipeline (400)
       ↓                    ↓                        ↓                       ↓
    入队列            清洗（去空白/编码）       校验（schema/必填）       本地落盘 / 转发
```

### 内置爬虫示例

| 爬虫 | 站点 | 特点 |
|------|------|------|
| `example` | 占位 | 调试用 |
| `openweather` | OpenWeatherMap API | 需 API Key |
| `zhihu_feed` | 知乎推荐 | 登录态 + UA 固定 |
| `dianping_home` | 大众点评 | 登录 + 代理 + 指纹 |

### 创建新爬虫

```bash
# 使用 Skill
/new-spider

# 或手动
# 1. scrapy/spiders/<name>.py 继承 scrapy.Spider
# 2. config/scrapy/default/sites.yml 加站点反爬配置
# 3. python run.py spider --spider <name>
```

### 高并发参数（`config/scrapy/default/settings.yml`）

| 参数 | 默认 | 说明 |
|------|------|------|
| `CONCURRENT_REQUESTS` | 32 | 全局并发 |
| `CONCURRENT_REQUESTS_PER_DOMAIN` | 16 | 单域名并发 |
| `DOWNLOAD_DELAY` | 1s | 下载延迟（**红线必备**） |
| `RANDOMIZE_DOWNLOAD_DELAY` | true | 抖动 |
| `RETRY_TIMES` | 3 | 重试次数 |

---

## 前端体系

### 技术栈

| 维度 | admin（后台） | official（官网） |
|------|---------------|------------------|
| 框架 | React 19 + TS | React 19 + TS |
| 路由 | React Router v7 | React Router v7 |
| 状态 | Zustand | （局部 useState） |
| UI | Ant Design 6 | Ant Design 6 + Framer Motion |
| 数据 | Axios + React Query | Axios |
| 端口 | 3001（开发）/ 9112（部署） | 3002（开发）/ 9113（部署） |

### 标准目录（`src/`）

```
src/
├── components/      # 通用组件（无业务逻辑）
├── pages/           # 页面级组件（含业务编排）
├── services/        # API 调用层（禁止在组件中直接 axios）
├── hooks/           # 自定义 Hooks
├── store/           # Zustand store（admin 用）
├── types/           # TypeScript 类型
├── utils/           # 工具函数
├── config/          # 前端配置
└── assets/          # 静态资源
```

### 开发约定

- **Components vs Pages**：纯 UI 组件无副作用；页面级组件可编排业务
- **Services 层强制**：所有 API 必须经 `services/`，禁止组件内直接 `axios`
- **环境变量**：通过 `REACT_APP_ENV` 注入，build 时区分目标环境

---

## 开发规范

### 编码

- Python：PEP 8，类型注解必备，`from __future__ import annotations`
- 命名：模块 `snake_case`、类 `PascalCase`、常量 `UPPER_SNAKE`
- 详见 `/coding-style` Skill

### 日志（Loguru 多路由）

```python
from platform_core import get_logger
logger = get_logger("api")          # 路由到 logs/api/api.log
logger.info("user login", uid=123)  # 关键路径必须留痕
```

详见 `/logging` Skill。

### 分层铁律

```
API Routes  →  Services  →  Repositories  →  Models
   ↓             ↓               ↓              ↓
请求校验      业务编排         数据访问       数据契约
```

- **上层可调下层，下层禁止反向调用**
- **API 层禁止 import ORM**（用 Pydantic schema 隔离）
- **ORM 禁止 import schema**（避免循环）

### 架构红线（自动检查）

```bash
# 一键扫描 10 条红线（grep + 静态分析）
/check-arch
```

| 红线 | 检查 |
|------|------|
| 硬编码连接串/密钥 | `grep -rE "mysql\|redis://[^$]" backend/ scrapy/` |
| scrapy 反向 import backend | `grep -rE "from (backend\|app)\." scrapy/` |
| 爬虫使用 SQLAlchemy Session | `grep -rE "SessionLocal\|get_db" scrapy/` |
| 爬虫缺 DOWNLOAD_DELAY | `grep DOWNLOAD_DELAY scrapy/settings.py` |
| API 直接 import ORM | `grep "from.*\.models import" backend/app/api/` |

详见 `.claude/rules/project_rule.md` 与 `.claude/skills/check-arch/`。

### 禁止清单

| 禁止 | 原因 | 替代 |
|------|------|------|
| 硬编码配置 | 改配置要重新构建 | Dynaconf 外置 |
| 爬虫直写主库 | 连接池竞争、脏数据污染 | RedisPipeline → 后端消费 |
| scrapy import backend | 耦合，无法独立部署 | API / 消息队列 |
| API 直接操作数据库 | 跨层穿透 | Service → Repository |
| 关键路径无日志 | 出问题无法定位 | 入口处 `logger.info` |
| 前端绕过 API 直连 DB | 安全/架构破坏 | 必须走 backend API |

---

## 运维脚本

| 脚本 | 用途 |
|------|------|
| `scripts/init-db.sh` | 创建 MySQL 库与用户（交互式输入 root 密码） |
| `scripts/init-database.sh <env>` | 调用 Python 初始化逻辑建表 |
| `scripts/migrate.sh` | 执行 Alembic 迁移到最新 |
| `scripts/start.sh` | 启动后端（兼容旧入口） |
| `scripts/run-spider.sh <name>` | 启动指定爬虫 |
| `scripts/start_frontend.sh` | 同时启动 admin + official |

---

## 技术栈速查

| 模块 | 技术 |
|------|------|
| 后端 | FastAPI 0.135 / SQLAlchemy 2.0 / PyMySQL / aiomysql / redis-py / Pydantic 2 / PyJWT / Loguru |
| 爬虫 | Scrapy 2.15 / scrapy-redis / Selenium / DrissionPage |
| 前端 | React 19 / TypeScript 4.9 / Ant Design 6 / React Router v7 / React Query / Zustand / Framer Motion |
| 配置 | Dynaconf 3.2 |
| 数据库 | MySQL 8 / Redis 6+ |
| 包管理 | uv（Python） / npm（前端） |
| 迁移 | Alembic 1.18 |

---

## 相关文档

- 项目规则：`.claude/rules/project_rule.md`（架构哲学 + 10 条红线）
- 回答规范：`.claude/rules/answer_rule.md`
- 调试激励：`.claude/rules/pua.md`
- 技能库：`.claude/skills/`（`new-svc / new-spider / new-model / check-arch / verify / coding-style / logging / config / deploy / cicd`）
- 项目说明：`CLAUDE.md`

---

**当前分支**：`feature/project-structure` —— 进行中的结构重构：
- 异常处理、CORS、日志初始化等统一收敛到 `platform_core`
- Python 环境收敛为 uv workspace 单一 `.venv`（原 `backend/.venv` 和 `scrapy/.venv` 已废弃）
