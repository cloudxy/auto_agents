# Auto Agents

> 多应用混合平台：**FastAPI 后端 + Scrapy 分布式爬虫 + React 双端（官网 / 后台管理）**，统一配置、统一基础设施、独立部署、AI 原生协作。

---

## 目录

- [架构总览](#架构总览)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [启动入口](#启动入口)
- [依赖管理（uv workspace）](#依赖管理uv-workspace)
- [配置管理](#配置管理)
- [API 设计](#api-设计)
- [爬虫体系](#爬虫体系)
- [前端体系](#前端体系)
- [AI 协作层（`.claude/`）](#ai-协作层claude)
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

         ┌────────────────────────────────────────────┐
         │  .claude/  AI 协作层（IDENTITY / SOUL /     │
         │            MEMORY / agents / hooks）        │
         └────────────────────────────────────────────┘
```

**核心原则**

| 价值观 | 落地 |
|--------|------|
| 配置即代码 | 所有连接串、密钥、端口外置到 `config/`，按 `local/dev/prod` 隔离 |
| 日志即证据 | Loguru 多 logger 路由（`global / api / admin / official / spider / error`） |
| 独立部署优于耦合 | 本地统一 venv（uv workspace），部署时各子项目可独立 `uv sync --package` |
| 爬取与存储分离 | 爬虫只采集清洗，**禁止直写主库**，通过 Redis 队列流向后端 |
| 模型即契约 | ORM 在 `platform_core/models`，Pydantic 在 `platform_core/schemas`，互不 import |
| AI 协作即契约 | `.claude/IDENTITY+SOUL+rules+skills` 同样是项目长期契约，与代码一起 git review |

详见 `.claude/rules/project_rule.md`。

---

## 项目结构

```
auto_agents/
├── pyproject.toml               # uv workspace 根（members: backend, scrapy）
├── uv.lock                      # 统一锁文件（提交到仓库）
├── .venv/                       # 统一虚拟环境（uv sync 自动创建）
│
├── run.py                       # 统一编排器（all / backend / spider / frontend）
├── run_backend.py               # 后端单独启动
├── run_spider.py                # 爬虫单独启动
├── run_frontend.py              # 前端单独启动（admin + official 并行）
│
├── backend/                     # FastAPI 后端（workspace member）
│   ├── app/
│   │   ├── __init__.py          # create_app() 工厂
│   │   ├── api/                 # 内部 API：/api/v1, /api/v2
│   │   ├── external_api/        # 外部 API：/external/v1（API Key 认证）
│   │   ├── middleware/          # RequestID 中间件等
│   │   └── responses/           # 统一响应模型
│   ├── services/                # 业务逻辑（auth / spider / config）
│   ├── repositories/            # 数据访问（继承 platform_core.repository）
│   ├── alembic/                 # 数据库迁移
│   ├── utils/                   # auth 工具等
│   └── pyproject.toml           # 后端依赖声明（部署可独立 sync）
│
├── scrapy/                      # Scrapy 分布式爬虫（workspace member）
│   ├── settings.py              # 入口配置（从 config/ 注入参数）
│   ├── spiders/                 # 爬虫实现（example/zhihu_feed/dianping_home/openweather）
│   ├── middlewares/             # 反爬五件套（UA/代理/指纹/会话/重试）
│   ├── pipelines/               # 清洗 → 校验 → 入库（Redis）
│   ├── items/                   # 数据契约
│   ├── utils/                   # session_manager / redis_client / logger
│   └── pyproject.toml           # 爬虫依赖声明（部署可独立 sync）
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
│   └── scrapy/                  # 爬虫专属（同样按 default/local/dev/prod 分层）
│
├── frontend/                    # 前端双端（React 19 + TS）
│   ├── admin/                   # 后台管理（Ant Design + Zustand + React Query）
│   └── official/                # 官方网站（Ant Design + Framer Motion）
│
├── .agents/                    # 工具中立的 AI 资产（可被任何 IDE 复用）
│   └── skills/                 # Skill 物理位置（new-svc / new-spider / check-arch ...）
│
├── .claude/                    # Claude Code 专属配置
│   ├── IDENTITY.md             # 项目身份
│   ├── SOUL.md                 # 项目性格
│   ├── MEMORY.md               # 项目记忆索引
│   ├── memory/                 # 记忆条目
│   ├── agents/                 # 子代理定义（spider-doctor / arch-warden / memory-curator）
│   ├── hooks/                  # 半自动进化 hook（inject / guard / suggest）
│   ├── rules/                  # 硬约束（answer / project / pua）
│   ├── skills -> ../.agents/skills   # symlink，让 Claude Code 自动发现机制照常工作
│   └── settings.json           # hook 启用配置
│
├── scripts/                     # 运维脚本（init-db / migrate / start / run-spider）
├── logs/                        # 运行时日志（按 logger 名分目录）
├── files/                       # 上传/下载/导出文件
└── runtime/                     # 缓存、会话等运行时数据
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
| uv | 最新 | Python 依赖管理 |

### 1. 安装依赖

```bash
# Python：根目录一把梭，自动装齐 backend + scrapy 全部依赖到 .venv/
uv sync

# 前端
cd frontend/admin    && npm install && cd ../..
cd frontend/official && npm install && cd ../..
```

> 不再需要 `cd backend && uv sync` —— uv workspace 已统一管理。给子项目加包用 `uv add --package auto-agents-backend <pkg>` 或 `uv add --package auto-agents-spider <pkg>`。

### 2. 初始化数据库

```bash
bash scripts/init-db.sh       # 创建库与用户
bash scripts/migrate.sh       # 执行 Alembic 迁移
```

### 3. 启动

```bash
# 一键：后端 + 双前端
uv run python run.py all

# 或分别启动
uv run python run.py backend                       # http://127.0.0.1:9111
uv run python run.py frontend --all                # admin:3001 / official:3002
uv run python run.py spider --list                 # 列出可用爬虫
uv run python run.py spider --spider example
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

纯 orchestrator，fork 子进程统一日志、信号、关停。**不做依赖安装、不跑迁移** —— 那是 `scripts/` 的活。

```bash
uv run python run.py all                           # backend + 双前端
uv run python run.py all --env dev                 # 指定环境
uv run python run.py backend --no-reload           # 关闭热重载
uv run python run.py backend --port 9200           # 临时改端口
uv run python run.py spider --spider zhihu_feed
uv run python run.py frontend --app admin
```

### 单独入口

| 脚本 | 用途 | 关键特性 |
|------|------|----------|
| `run_backend.py` | 启动 FastAPI | 端口预检、串行初始化 logger→db→storage→app |
| `run_spider.py` | 启动 Scrapy | 注入 `sys.path`，`SCRAPY_SETTINGS_MODULE=settings`；支持 `--list / --spider <name>` |
| `run_frontend.py` | 启动前端 | 端口预检、自动 `npm install`、并行启动、按应用名加日志前缀 |

所有入口都接受 `--env {local,dev,prod}`，会透传为 `APP_ENV`（前端透传为 `REACT_APP_ENV`）。

---

## 依赖管理（uv workspace）

根目录一个 `.venv`，`backend/` 和 `scrapy/` 作为 workspace member 各自保留 `pyproject.toml` —— 依赖声明分散、安装环境统一。

### 结构

```
pyproject.toml          # 根：[tool.uv.workspace] members = ["backend", "scrapy"]
uv.lock                 # 根：统一锁文件（必须提交）
.venv/                  # 根：统一虚拟环境
backend/pyproject.toml  # 后端依赖声明
scrapy/pyproject.toml   # 爬虫依赖声明
platform_core/          # 源码包，不打包，由 sys.path 引入
```

### 常用命令

```bash
uv sync                                          # 装齐所有依赖

uv add --package auto-agents-backend  fastapi-pagination
uv add --package auto-agents-spider   playwright

uv run python run_backend.py                     # 自动用根 .venv
uv run alembic -c backend/alembic.ini upgrade head
```

### 部署时的独立性

虽然本地用统一 venv，**生产部署时仍可按子项目独立打包**：

```bash
uv sync --package auto-agents-backend --no-dev   # 后端镜像
uv sync --package auto-agents-spider  --no-dev   # 爬虫镜像
```

子项目的 `pyproject.toml` 是各自的依赖契约 —— workspace 只是本地开发的便利层。

### 红线

- ❌ 禁止再创建 `backend/.venv` 或 `scrapy/.venv`
- ❌ 禁止 `cd backend && uv add ...`，改用 `uv add --package`
- ❌ 禁止把 `uv.lock` 加入 `.gitignore`
- ⚠️ shell 残留 `VIRTUAL_ENV` 指向旧子项目 venv 时，先 `unset VIRTUAL_ENV UV_PROJECT_ENVIRONMENT` 再 `uv sync`

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
| `log.yml` | 多 logger 路由（global / api / admin / official / spider / error） |
| `storage.yml` | 缓存 / 上传 / 导出 / 临时目录 + 上传限制 |
| `jwt.yml` | SECRET_KEY / 算法 / 过期时间 |
| `admin.yml` `official.yml` | 双前端配置 |

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
APP_ENV=dev  uv run python run.py backend
uv run python run.py backend --env prod
```

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
3. 实现新版业务（参考 `/new-svc` skill）

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
/new-spider                                      # 推荐：用 skill 一键脚手架

# 或手动
# 1. scrapy/spiders/<name>.py 继承 scrapy.Spider 或 RedisSpider
# 2. config/scrapy/default/sites.yml 加站点反爬配置
# 3. uv run python run.py spider --spider <name>
```

### 高并发参数（`config/scrapy/default/settings.yml`）

| 参数 | 默认 | 说明 |
|------|------|------|
| `CONCURRENT_REQUESTS` | 32 | 全局并发 |
| `CONCURRENT_REQUESTS_PER_DOMAIN` | 16 | 单域名并发 |
| `DOWNLOAD_DELAY` | 1s | 下载延迟（**红线必备**） |
| `RANDOMIZE_DOWNLOAD_DELAY` | true | 抖动 |
| `RETRY_TIMES` | 3 | 重试次数 |

爬虫失效（selector 失效 / 403/429 / 队列断流）请拉起 `.claude/agents/spider-doctor.md`（见下节）。

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

## AI 协作层（`.claude/`）

本项目内置一套与 Claude Code 协作的"AI 原生"基础设施。它**不是项目运行依赖**，而是把 AI 协作规则、记忆、自动化拦截固化下来，让任何成员（或任何接手仓库的 AI）开箱即得统一行为。

### Agents vs Claude（先澄清概念）

- **Claude** = 你正在对话的主 LLM，独占一个 context window
- **Agents（子代理）** = `.claude/agents/*.md` 定义的"专项小弟"。主 Claude 用 `Task` 工具拉起它们，**每个子代理有隔离的 context window**，结束后只把摘要带回主对话 —— 既不污染主上下文，又能并行处理

> 注意：项目名 `auto_agents` 是品牌词，指 Scrapy 爬虫这类"自动化工人"，**与 LLM Agent 完全无关**。本仓库目前不依赖任何 LLM SDK。

### 五件套 + 工具中立资产

skills 物理放在 `.agents/skills/`（工具中立，可被任何 IDE 复用），通过 symlink 暴露给 `.claude/skills`，借鉴自 [warpdotdev/warp](https://github.com/warpdotdev/warp/tree/master/.claude) 的设计。

```
.agents/                工具中立 AI 资产（任何 IDE 都可读）
└── skills/             Skill 物理位置（new-svc / new-spider / new-model / check-arch / verify ...）

.claude/                Claude Code 专属
├── IDENTITY.md         项目身份：Role / Mission / Expertise / Boundaries
├── SOUL.md             项目性格：5 条软偏好（悲观验证 / 延伸排查 / 沉默优于啰嗦 ...）
├── MEMORY.md           项目记忆索引（具体条目在 memory/）
├── memory/             长期知识条目（reference / troubleshooting / playbook / decision）
├── rules/              硬约束（answer_rule / project_rule / pua）
├── skills -> ../.agents/skills    symlink → .agents/skills，Claude Code 自动发现 /slash 命令照常工作
├── agents/             子代理定义（见下）
├── hooks/              半自动进化脚本
└── settings.json       启用 hooks
```

未来如要接入 Cursor / Lingma / Gemini，只需在对应的 `.cursor/skills` / `.lingma/skills` 各自软链到 `../.agents/skills`，零迁移成本。

| 文件类型 | 性质 | 谁能改 |
|---------|------|--------|
| `IDENTITY.md` `SOUL.md` `rules/*` `.agents/skills/*` `settings.json` | 长期契约 | **人类**（PreToolUse hook 拦截 AI 写入 `.claude/skills` 与 `.agents/skills`，要求确认） |
| `MEMORY.md` 索引 | 半契约 | AI 可改，PR review |
| `memory/*.md` 条目 | 项目知识 | AI 产 diff，用户 apply 后入库 |
| `settings.local.json` | 个人本地 | AI / 人类皆可（不入库） |

### 内置子代理

| Agent | 触发场景 | 职责 |
|-------|---------|------|
| `spider-doctor` | "爬虫跑不出"、"selector 返回空"、"403/429" | 按概率从高到低诊断（selector → 反爬 → 队列 → pipeline），输出"已验证/已排除/缩小到"结构化报告 |
| `arch-warden` | "准备提交"、"做 PR"、"check 架构" | 跑 `.claude/skills/check-arch` 的 10 条 grep 红线，给 verdict |
| `memory-curator` | Stop hook 提示后用户确认；或周期性调用 | 整理 memory 去重、合并、归档，**产 diff 不直写** |

### 半自动进化（hooks）

`.claude/hooks/` 三个 shell 脚本通过 `.claude/settings.json` 启用，全部 **fail-open**（任何异常 exit 0，绝不阻塞工作流）：

| Hook | 事件 | 作用 |
|------|------|------|
| `inject_context.sh` | UserPromptSubmit | 每次对话开头注入 IDENTITY Role+Mission + 最近 3 条 memory（< 1KB），让 AI 自动获取项目上下文 |
| `guard_meta.sh` | PreToolUse (Write\|Edit) | 拦截对 `.claude/(rules\|skills\|IDENTITY\|SOUL\|settings.json)` 的写入，输出 `permissionDecision: ask` 强制人类确认 |
| `suggest_memory.sh` | Stop | 扫 transcript 关键词（`坑 / pitfall / 约定 / 下次记住`），命中 ≥ 2 处时提示运行 `memory-curator` 归档 |

进化闭环：

```
踩坑/约定出现 → Stop hook 提示 → 用户拉起 memory-curator
              → 产出 memory diff → 用户 review + apply
              → git commit → 团队共享生效
```

`rules/*` `skills/*` 和 IDENTITY/SOUL 等长期契约**禁止 AI 自主修改**（hook 拦截），保证项目行为可预测、可回滚。

### 常用 Skill

| Skill | 用途 |
|-------|------|
| `/new-svc` | 创建 FastAPI 服务模块 |
| `/new-spider` | 创建 Scrapy 爬虫 |
| `/new-model` | 配对生成 ORM + Pydantic Schema |
| `/check-arch` | 扫描 10 条架构红线 |
| `/verify` | 交付自检（强制 build/test/curl） |
| `/coding-style` `/logging` `/config` `/deploy` `/cicd` | 各类规范 |

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

- 上层可调下层，下层禁止反向调用
- API 层禁止 import ORM（用 Pydantic schema 隔离）
- ORM 禁止 import schema（避免循环）

### 架构红线（10 条，可机械检查）

```bash
/check-arch                                      # 一键扫描全部
```

| 红线 | 检查 |
|------|------|
| 硬编码连接串/密钥 | `grep -rE "(mysql\|redis)://[^\$]" backend/ scrapy/` |
| scrapy 反向 import backend | `grep -rE "from (backend\|app)\." scrapy/` |
| 爬虫使用 SQLAlchemy Session | `grep -rE "SessionLocal\|get_db" scrapy/` |
| 爬虫缺 DOWNLOAD_DELAY | `grep DOWNLOAD_DELAY scrapy/settings.py` |
| API 直接 import ORM | `grep "from.*\.models import" backend/app/api/` |
| ORM import Pydantic schema | `grep "from.*\.schemas import" platform_core/models/` |
| ... | 完整 10 条见 `.claude/rules/project_rule.md` |

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

运维/部署：new-api 网关（渠道调度/探针依赖）部署编排见 [deploy/newapi/README.md](deploy/newapi/README.md)。

---

## 技术栈速查

| 模块 | 技术 |
|------|------|
| 后端 | FastAPI ≥0.135 / SQLAlchemy 2 / PyMySQL / aiomysql / redis-py ≥7.4 / Pydantic 2 / PyJWT / Loguru |
| 爬虫 | Scrapy ≥2.15 / scrapy-redis / Selenium / DrissionPage |
| 前端 | React 19 / TypeScript / Ant Design 6 / React Router v7 / React Query / Zustand / Framer Motion |
| 配置 | Dynaconf ≥3.2 |
| 数据库 | MySQL 8 / Redis 6+ |
| 包管理 | uv（Python workspace）/ npm（前端） |
| 迁移 | Alembic ≥1.18 |
| AI 协作 | Claude Code（`.claude/` 五件套） |

---

## 相关文档

- 项目身份：`.claude/IDENTITY.md`
- 项目性格：`.claude/SOUL.md`
- 项目记忆：`.claude/MEMORY.md` + `.claude/memory/`
- 架构哲学 + 10 条红线：`.claude/rules/project_rule.md`
- 回答规范：`.claude/rules/answer_rule.md`
- 调试激励：`.claude/rules/pua.md`
- 子代理：`.claude/agents/{spider-doctor,arch-warden,memory-curator}.md`
- 技能库：`.claude/skills/`
- Claude 入口：`CLAUDE.md`

---

**当前分支**：`feature/project-structure` —— 进行中的结构重构：
- 异常处理、CORS、日志初始化等已统一收敛到 `platform_core`
- Python 环境收敛为 uv workspace 单一 `.venv`
- 新增 `.claude/` AI 协作层（IDENTITY / SOUL / MEMORY / agents / hooks）
