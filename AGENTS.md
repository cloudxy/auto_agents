# AGENTS.md - Auto Agents 项目指南（Qoder）

多应用混合平台：FastAPI 后端 + Scrapy 分布式爬虫 + React 双前端（admin 后台 / official 官网），
统一配置、统一基础设施、统一 Python 环境。

## 模块地图

| 模块 | 路径 | 职责 |
|------|------|------|
| 后端 | `backend/` | FastAPI API（`app/api/v1+v2`）+ 外部 API（`app/external_api`）+ services + repositories |
| 爬虫 | `scrapy/` | spiders / middlewares / pipelines / items（禁止 import backend） |
| 共享基建 | `platform_core/` | logger / db / storage / exceptions / repository / models / schemas |
| 前端 | `frontend/{admin,official}/` | React 19 + TypeScript（独立 npm 包） |
| 配置 | `config/` | Dynaconf 多层合并（default → `<env>` → `.env` → 环境变量） |
| 编排 | `run.py` / `run_*.py` | 全栈启停入口 |

## 环境红线（uv workspace，必须遵守）

- 根 `.venv` 是**唯一**的 Python 虚拟环境，禁止创建 `backend/.venv` 或 `scrapy/.venv`
- 加依赖用 `uv add --package auto-agents-backend <pkg>`，禁止 `cd backend && uv add`
- `uv.lock` 必须提交（可复现性保证），禁止加入 `.gitignore`
- `platform_core/` 是源码包，经 `sys.path` 引入，不打包、不进 workspace

## 架构红线 + 核心边界（12 红线（R1-R12） + 3 边界，机械可检查）

详见 `.claude/rules/project_rule.md`；提交前会自动执行 `scripts/check-arch.sh`
（pre-commit hook + CI）。核心约束：

- 禁止硬编码连接串/密钥/端口（配置即代码）
- 爬虫禁止 import backend、禁止直写主库（走 Redis 队列）
- 爬虫必须配反爬（DOWNLOAD_DELAY + USER_AGENT 轮换）
- API 层禁止直接 import ORM 模型；ORM 禁止 import Pydantic schema（模型即契约）
- async 上下文禁止同步 `redis_client()` 链式直调，统一走 `get_async_redis()`（R11 异步优先）
- 核心边界：`platform_core/` 只依赖 `config/`（B1）；`backend/` 禁止 import `scrapy/`（B2）；`config/` 不依赖任何业务模块（B3）

## 关键文件索引

- `pyproject.toml` — uv workspace 根配置（含 pytest / ruff 配置）
- `backend/app/__init__.py` — FastAPI 应用工厂 `create_app()`
- `backend/app/api/__init__.py` — API 版本路由聚合（v1/v2）
- `platform_core/__init__.py` — 基建初始化（`init_log / init_db / init_storage`）
- `platform_core/exceptions/` — 统一异常体系 + FastAPI handler
- `config/__init__.py` — Dynaconf 加载入口（多层合并）
- `scripts/check-arch.sh` — 架构红线扫描（退出码 = 违规数）
- `.claude/hooks/*.sh` — Claude Code Hook 脚本（运行时依赖：bash >= 3.2 + grep/sed/awk；jq 可选）

## 快速开始

```bash
uv sync                                    # 安装依赖（含测试工具链）
uv run python run.py all                   # 后端 + 双前端一把梭
uv run pytest -x -q backend/tests          # 后端测试
bash scripts/check-arch.sh                 # 架构合规检查
uv run pre-commit install --hook-type pre-commit --hook-type pre-push  # 安装门禁（ruff+arch 提交时，pytest 推送时）
```

环境切换：所有入口接受 `--env {local,dev,prod}`；本地联调全栈可用
`docker compose up --build`（backend + MySQL + Redis）。

## 验证与交付约定

- 任何"已完成"陈述必须伴随可验证输出（测试输出 / curl 结果 / 构建日志）
- 后端改动：`uv run pytest -x -q backend/tests` 必须退出码 0
- 数据契约改动（models/schemas）：额外跑 `bash scripts/check-arch.sh`
- CI 三阶段关卡：Python lint+test / 架构红线 / 前端构建

## Skill 路由（.agents/skills/）

项目协作 skill 在 `.agents/skills/`。跨工具共享的 skill 目录库在 `skills-library/`（**技能治理已并入主 API `v1/skills`**，本地 8765 后台已退役；用法见该目录 README）。

| 场景 | Skill |
|------|-------|
| 创建服务模块 | `/new-svc` |
| 创建爬虫 | `/new-spider` |
| 创建数据模型（ORM + Schema 配对） | `/new-model` |
| 架构合规检查 | `/check-arch` |
| 交付自检 | `/verify` |
| 编码规范 / 日志规范 / 配置规范 | `/coding-style` / `/logging` / `/config` |
| 部署 / CI/CD | `/deploy` / `/cicd` |
| 穷尽式问题解决（重复失败 / 质量投诉触发） | `/pua` |

## Agent skills

### Issue tracker

工单以本地 markdown 存放于 `.scratch/<feature>/`（spec + `issues/` 每票一文件）。见 `docs/agents/issue-tracker.md`。

### Triage labels

沿用五个默认 triage 角色标签（`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`）。见 `docs/agents/triage-labels.md`。

### Domain docs

single-context：根级 `CONTEXT.md` + `docs/adr/`（按需惰性创建）；平台演进总方案权威源为 `docs/plan/README.md`。见 `docs/agents/domain.md`。

其他 provider 的完整项目指令见 `CLAUDE.md`（Claude）与 `GEMINI.md`（Gemini），
本文件与其保持同一架构事实，如有冲突以 `project_rule.md` 为准。
