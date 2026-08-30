# Auto Agents 项目指南

## 项目概览

多应用混合平台：FastAPI 后端 + Scrapy 分布式爬虫 + React 双前端（官网 + 后台管理），统一配置、统一基础设施、统一 Python 环境。

```
auto_agents/
├── pyproject.toml        # uv workspace 根（members: backend, scrapy）
├── uv.lock               # 统一锁文件（提交）
├── .venv/                # 统一虚拟环境
│
├── run.py                # 编排器：all / backend / spider / frontend
├── run_backend.py        # 后端启动入口
├── run_spider.py         # 爬虫启动入口
├── run_frontend.py       # 前端启动入口（admin + official 并行）
│
├── backend/              # FastAPI 后端（workspace member）
├── scrapy/               # Scrapy 爬虫（workspace member）
├── platform_core/        # 共享基础设施（logger/db/storage/exceptions/repository/models/schemas）
├── frontend/
│   ├── admin/            # 后台管理（React 19 + Ant Design + Zustand）
│   └── official/         # 官方网站（React 19 + Ant Design + Framer Motion）
├── config/               # Dynaconf 配置（default + local/dev/prod + scrapy 子层）
├── scripts/              # 运维脚本（init-db / migrate / start / run-spider）
└── .claude/              # 规则和技能库
```

## 核心架构哲学

- **配置即代码**：所有配置外置、版本化、环境隔离
- **日志即证据**：关键路径必须留痕且可追溯
- **独立部署优于耦合**：本地统一 venv（uv workspace），部署仍可按子项目独立 `uv sync --package`
- **爬取与存储分离**：爬虫只采集和清洗，不负责持久化（禁止直写主库，走 Redis 队列）
- **反爬是生存底线**:每个爬虫必须实现反爬策略

## 技术栈

| 模块 | 技术 |
|------|------|
| 后端 | FastAPI 0.136 + SQLAlchemy 2 + PyMySQL/aiomysql + redis-py + Pydantic 2 + PyJWT + Loguru |
| 爬虫 | Scrapy 2.15 + scrapy-redis + Selenium + DrissionPage |
| 前端 | React 19 + TypeScript + Ant Design 6 + React Router v7 + Axios + React Query + Zustand |
| 配置 | Dynaconf 3.2 |
| 数据库 | MySQL 8 / Redis 6+ |
| 包管理 | uv workspace（Python）/ npm（前端） |
| 迁移 | Alembic 1.18 |
| 基建 | Docker + GitHub Actions |

## 快速开始

### Python（后端 + 爬虫共用 venv）

```bash
# 一次装齐所有依赖到根 .venv
uv sync

# 给子项目加包（在仓库任意层级都行）
uv add --package auto-agents-backend <pkg>
uv add --package auto-agents-spider <pkg>
```

### 前端

```bash
cd frontend/admin && npm install && cd ../..
cd frontend/official && npm install && cd ../..
```

### 启动

```bash
# 一把梭：后端 + 双前端
uv run python run.py all

# 单独启动
uv run python run_backend.py                       # http://127.0.0.1:9111
uv run python run_spider.py --list                 # 列出爬虫
uv run python run_spider.py --spider example
uv run python run_frontend.py --all                # admin:3001 / official:3002
```

环境切换：所有入口接受 `--env {local,dev,prod}`，透传为 `APP_ENV`。

## 规则和技能

使用 `.claude/` 中的规则和技能：

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
| `/check-arch` | 架构合规检查（11 条红线） |
| `/verify` | 交付自检 |
| `/coding-style` | 编码规范 |
| `/logging` | 日志规范 |
| `/config` | 配置规范 |
| `/deploy` | Docker 部署配置 |
| `/cicd` | GitHub Actions CI/CD |

## 项目状态

当前分支：`feature/project-structure`

正在进行的结构重构：
- 异常处理、CORS、日志初始化等已统一收敛到 `platform_core`
- Python 环境已收敛为 uv workspace 单一 `.venv`

## 关键文件

- `pyproject.toml` - uv workspace 根配置
- `run.py` / `run_backend.py` / `run_spider.py` / `run_frontend.py` - 启动入口
- `backend/app/__init__.py` - FastAPI 应用工厂（`create_app()`）
- `backend/app/api/__init__.py` - API 版本路由聚合（v1/v2）
- `platform_core/__init__.py` - 基础设施初始化导出（`init_log / init_db / init_storage`）
- `platform_core/logger.py` / `db.py` / `storage.py` - 基建实现
- `platform_core/exceptions/` - 统一异常 + FastAPI handler
- `config/__init__.py` - Dynaconf 加载入口（多层合并）
- `scrapy/settings.py` - Scrapy 配置（从 `config/` 注入）
- `.claude/` - 规则和技能库
