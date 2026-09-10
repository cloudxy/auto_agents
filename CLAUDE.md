# Auto Agents 项目指南

## 项目概览

多应用混合平台：FastAPI 后端 + Scrapy 分布式爬虫 + React 双前端（官网 + 后台管理），统一配置、统一基础设施、统一 Python 环境。架构事实与 `AGENTS.md` 同一份；冲突以 `tools/check/arch.sh` 与 `.claude/rules/project_rule.md` 为准。

```
auto_agents/
├── pyproject.toml        # uv workspace 根（members: backend, scrapy）
├── uv.lock               # 统一锁文件（提交）
├── package.json          # npm workspaces（frontend/*）
├── .venv/                # 统一 Python 虚拟环境
│
├── run.py                # 统一启停：start / stop / restart|reload / status
│                             # 实现：scripts/runlib/
│
├── backend/              # FastAPI 后端（workspace member）
├── scrapy/               # Scrapy 爬虫（workspace member）
├── platform_core/        # 共享基建（logger/db/storage/exceptions/repository/models/schemas）
├── frontend/
│   ├── admin/            # 后台（React 19 + Ant Design + Zustand）
│   ├── official/         # 官网（React 19 + Ant Design + Framer Motion）
│   └── shared/           # 双应用共享层（编译 dist/ 再消费）
├── config/               # Dynaconf（default + local/dev/prod + scrapy 子层）
├── init_project.sh       # 新人一键初始化
├── scripts/              # 初始化辅助 + 启停（lib / runlib / db）
├── tools/                # 质量门禁 / OpenAPI
├── deploy/litellm/       # 平台 LLM 网关（LiteLLM Proxy）编排
├── deploy/newapi/        # 已退役运行时的历史编排（默认不启）
├── capability-library/   # 产品能力目录；plugins/ → .agents/plugins
├── .agents/              # 开发协作中枢（skills/ + plugins/ 指针农场）
├── .claude/              # 规则 / hooks / agents；skills、plugins 为适配器
└── .grok/                # Grok 项目配置；plugins/ 为启用子集
```

## 核心架构哲学

- **配置即代码**：所有配置外置、版本化、环境隔离
- **日志即证据**：关键路径必须留痕且可追溯
- **独立部署优于耦合**：本地统一 venv（uv workspace），部署仍可按子项目独立 `uv sync --package`
- **爬取与存储分离**：爬虫只采集和清洗，不负责持久化（禁止直写主库，走 Redis 队列）
- **反爬是生存底线**：每个爬虫必须实现反爬策略

## 技术栈

| 模块 | 技术 |
|------|------|
| 后端 | FastAPI ≥0.135 + SQLAlchemy 2 + PyMySQL/aiomysql + redis-py + Pydantic 2 + PyJWT + Loguru |
| 爬虫 | Scrapy ≥2.15 + scrapy-redis + Selenium + DrissionPage |
| 前端 | React 19 + TypeScript + Ant Design 6 + React Router v7 + Axios + React Query + Zustand |
| 配置 | Dynaconf ≥3.2 |
| 数据库 | MySQL 8 / Redis 6+（compose 用 Redis 7） |
| 包管理 | uv workspace（Python）/ npm workspaces（前端） |
| 迁移 | Alembic ≥1.18 |
| 基建 | Docker + GitHub Actions（五阶段 CI） |
| 平台 LLM 网关 | LiteLLM Proxy（目标运行时）；new-api 管控面默认关闭 |

## 快速开始

### Python（后端 + 爬虫共用 venv）

```bash
bash init_project.sh           # 新人一键初始化
uv add --package auto-agents-backend <pkg>
uv add --package auto-agents-spider <pkg>
```

### 前端

`setup.sh` 已含 `npm ci` 与 `build:shared`。不要在 `frontend/admin` 里单独 `npm install` 当唯一安装路径。

### 启动

```bash
uv run python run.py                       # 默认启动全部（已运行则跳过）
uv run python run.py stop                  # 停止全部
uv run python run.py restart               # 强制重启
uv run python run.py start backend         # http://127.0.0.1:9111
uv run python run.py spider --list         # 列出爬虫
uv run python run.py start spider
uv run python run.py start frontend        # admin:9112 / official:9113
```

环境切换：所有入口接受 `--env {local,dev,prod}`，透传为 `APP_ENV`。

## 规则和技能

规则在 `.claude/rules/`。项目 skill 在 `.agents/skills/`（`.claude/skills` 是符号链接）。中枢说明：`.agents/README.md`。

| 规则 | 描述 |
|------|------|
| `answer_rule` | 回答思维框架 - 解决问题优先 |
| `project_rule` | 架构哲学、设计原则、演进方向 |
| `pua` | 穷尽式问题解决引擎 |

| 技能 | 描述 |
|------|------|
| `/new-svc` | 创建 FastAPI 服务模块 |
| `/new-spider` | 创建 Scrapy 爬虫 |
| `/new-model` | 创建 ORM + Pydantic 数据模型 |
| `/db-design` | 数据库设计流水线（DBML → 迁移） |
| `/check-arch` | 架构合规检查（R1–R13 + B1–B3） |
| `/verify` | 交付自检 |
| `/deploy` `/cicd` | Docker / GitHub Actions |

Claude 子代理仍在 `.claude/agents/`：`arch-warden` / `spider-doctor` / `memory-curator`。

## 项目状态

当前分支：`feature/project-structure`。

已落地：异常/CORS/日志收敛到 `platform_core`；Python 单一 `.venv`；前端 npm workspaces + `frontend/shared`；开发协作中枢 `.agents/`。

进行中：四柱程序（采集出数环 / SaaS / LiteLLM 数据面 / 能力市场）。平台 LLM 网关目标为 LiteLLM；`/api/v1/newapi` 与 `deploy/newapi` 是遗留管控面，默认关闭，不作为长期运行时。

## 关键文件

- `pyproject.toml` / `package.json` — Python / 前端 workspace
- `run.py` + `scripts/runlib/`（backend / spider / frontend 进程）
- `backend/app/__init__.py` — `create_app()`
- `backend/app/api/v1/__init__.py` — v1 路由聚合
- `platform_core/` — 基建
- `config/__init__.py` — Dynaconf
- `scrapy/settings.py` — 从 `config/` 注入
- `tools/check/arch.sh` — 红线扫描
- `.agents/README.md` — 协作中枢
