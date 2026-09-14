# AGENTS.md - Auto Agents 项目指南

多应用混合平台：FastAPI 后端 + Scrapy 分布式爬虫 + React 双前端（admin 后台 / official 官网），
统一配置、统一基础设施、统一 Python 环境。

## 模块地图

| 模块 | 路径 | 职责 |
|------|------|------|
| 后端 | `backend/` | FastAPI API（`app/api/v1+v2`）+ 外部 API（`app/external_api`）+ services + repositories |
| 爬虫 | `scrapy/` | spiders / middlewares / pipelines / items（禁止 import backend） |
| 共享基建 | `platform_core/` | logger / db / storage / exceptions / repository / models / schemas |
| 前端 | `frontend/{admin,official,shared}/` | React 19 + TypeScript；`shared` 经 `dist/` 给双应用消费 |
| 配置 | `config/` | Dynaconf 多层合并（default → `<env>` → `.env` → 环境变量） |
| 初始化 | `init_project.sh` | 新人一键：工具 / 依赖 / .env / 库 / 管理员 |
| 编排 | `run.py` + `scripts/runlib/` | 统一启停（默认 start 全部；stop / restart） |
| 产品目录 | `capability-library/` | 能力资产内容与扫描入口（`plugins/` 适配器 → `.agents/plugins`） |
| 开发协作 | `.agents/` | 项目 skill + 第三方插件指针农场；宿主目录只做适配器 |

## 环境红线（uv workspace，必须遵守）

- 根 `.venv` 是**唯一**的 Python 虚拟环境，禁止创建 `backend/.venv` 或 `scrapy/.venv`
- 加依赖用 `uv add --package auto-agents-backend <pkg>`，禁止 `cd backend && uv add`
- `uv.lock` 必须提交（可复现性保证），禁止加入 `.gitignore`
- `platform_core/` 是源码包，经 `sys.path` 引入，不打包、不进 workspace
- 前端用仓库根 `package.json` workspaces + 根 `package-lock.json`；先 `npm ci`，再 `npm run build:shared`

## 架构红线 + 核心边界（R1–R13 + B1–B3，机械可检查）

权威清单是 `tools/check/arch.sh`（以脚本输出为准，不要靠记忆数条数）。提交前 pre-commit + CI 会跑。核心约束：

- 禁止硬编码连接串/密钥/端口（配置即代码）
- 爬虫禁止 import backend、禁止直写主库（走 Redis 队列）
- 爬虫必须配反爬（DOWNLOAD_DELAY + USER_AGENT 轮换）
- API 层禁止直接 import ORM 模型；ORM 禁止 import Pydantic schema（模型即契约）
- async 上下文禁止同步 `redis_client()` 链式直调，统一走 `get_async_redis()`（R11）
- 租户过滤收口（R13）；`spider_service` 门面白名单（R12）
- 核心边界：`platform_core/` 只依赖 `config/`（B1）；`backend/` 禁止 import `scrapy/`（B2）；`config/` 不依赖任何业务模块（B3）

规则正文：`.claude/rules/project_rule.md`。

## 编码 / 日志 / 配置（常驻约定，不是 skill）

实现以仓库文件为准：`config/__init__.py`、`config/default/log.yml`、`.env.example`。

**配置** — `APP_ENV` 只选一层（`local`/`dev`/`prod`，缺省 `local`）。后者覆盖前者：`config/default/*.yml` → `config/scrapy/default/*.yml` → `config/<env>/*.yml` → `config/scrapy/<env>/*.yml` → `config/<env>/.env` → `AUTO_AGENTS_*`。MySQL 在 `config/<env>/mysql.yml` 的 `MYSQL.DEFAULT.*`。密钥用 `AUTO_AGENTS_MYSQL_DEFAULT_PASSWORD` / `AUTO_AGENTS_REDIS_DEFAULT_PASSWORD` / `AUTO_AGENTS_JWT__SECRET_KEY`（双下划线嵌套；`.env` 不做 `${VAR}` 展开）。读取：`from config import settings` → `settings.JWT.SECRET_KEY`。

**日志** — `from platform_core.logger import get_logger`；`get_logger("api"|"spider"|"admin"|"official")` 必须对上 `LOGGERS`。进程 stdout 在 `runtime/run/`。落盘 `logs/{global,api,admin,official,spider,error}/`。`backend/services/*.py` 公开方法入口要有 `logger.`（R10）。密码/Token 不入日志。

**编码** — Python：`uv run ruff check backend platform_core scripts`。模块/函数下划线，类大驼峰。单函数 ≤ 40 行，单文件 ≤ 500 行。API 用 `backend.app.responses.ok/created`（health 探活除外）。前端：ESLint；业务 `.tsx` ≤ 400 行（F-7）；admin 用 Zustand + React Query；共享进 `frontend/shared` 经 dist。爬虫：`DOWNLOAD_DELAY` + `UserAgentMiddleware`；出口 `StorePipeline`。

## 关键文件索引

- `pyproject.toml` — uv workspace 根配置（含 pytest / ruff）
- `package.json` — npm workspaces（`frontend/*`）
- `backend/app/__init__.py` — FastAPI 应用工厂 `create_app()`
- `backend/app/api/__init__.py` — API 版本路由聚合（v1/v2）
- `platform_core/__init__.py` — 基建初始化（`init_log / init_db / init_storage`）
- `config/__init__.py` — Dynaconf 加载入口
- `init_project.sh` — 新人一键初始化
- `tools/check/arch.sh` — 架构红线扫描（退出码 = 违规数）
- `.agents/README.md` — 开发协作中枢契约
- `.claude/hooks/*.sh` — Claude Code Hook（bash >= 3.2 + grep/sed/awk；jq 可选）

## 快速开始

```bash
bash init_project.sh                       # 新人一键初始化
uv run python run.py                       # 默认启动全部（已运行则跳过）
uv run python run.py stop                  # 停止全部
uv run python run.py restart               # 强制重启
uv run pytest -x -q backend/tests          # 后端测试
bash tools/check/arch.sh                 # 架构合规检查
uv run pre-commit install --hook-type pre-commit --hook-type pre-push --hook-type post-checkout
```

环境切换：所有入口接受 `--env {local,dev,prod}`。本地联调全栈：`docker compose up --build`（backend + MySQL 8 + Redis 7；compose 已设 `AUTO_AGENTS_API__HOST=0.0.0.0`）。

## 验证与交付约定

- 任何「已完成」陈述必须伴随可验证输出（测试输出 / curl 结果 / 构建日志）
- 后端改动：`uv run pytest -x -q backend/tests` 必须退出码 0
- 数据契约改动（models/schemas）：额外跑 `bash tools/check/arch.sh`
- CI 五阶段：Python lint+test / 架构红线 / DB 迁移门禁 / 前端构建 / Docker 校验

## Skill 路由（`.agents/`）

中枢契约见 `.agents/README.md`。项目 skill 在 `.agents/skills/`（`.claude/skills` 指向它）。产品扫描走 `capability-library/`（**技能治理在主 API `v1/skills` + `v1/capabilities`**）。

第三方插件正文只在 `~/.zcode/local-plugins/`。仓库内只在 `.agents/plugins/<name>` 放符号链接。Grok/Claude 启用子集：`sdlc-workflow` / `dev-team` / `drama-skills` / `oh-story`。`superpowers` / `mattpocock-skills` 只留在农场给产品扫描（已含于 `dev-team`）。跳过 `sdlc-workflow-eval-workspace`。

调用：Claude/Grok `/name`。ZCode Agent：`$name` 调 skill，`/` 调 command（[原文](https://zcode.z.ai/en/docs/agents)）。description 每轮最多注入 250 字符，见 `.agents/README.md`。

| 场景 | Skill |
|------|-------|
| 创建服务模块 | `/new-svc`（ZCode `$new-svc`） |
| 创建爬虫 | `/new-spider`（ZCode `$new-spider`） |
| 创建数据模型（ORM + Schema 配对） | `/new-model`（ZCode `$new-model`） |
| 数据库设计流水线（DBML → 迁移） | `/db-design`（ZCode `$db-design`） |
| 架构合规检查 | `/check-arch`（ZCode `$check-arch`） |
| 交付自检 | `/verify`（ZCode `$verify`） |
| 部署 / CI/CD | `/deploy` `/cicd` |
| 穷尽式问题解决（重复失败 / 质量投诉触发） | `/pua`（ZCode `$pua`） |

## Agent skills

### Issue tracker

工单以本地 markdown 存放于 `.scratch/<feature>/`（spec + `issues/` 每票一文件）。约定文件 `docs/agents/issue-tracker.md` 为本地私有配置（不入库）。

### Triage labels

沿用五个默认 triage 角色标签（`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`）。

### Domain docs

single-context：根级 `CONTEXT.md`（词汇）；`docs/` 为本地私有不入库。

Claude 侧完整指南见 `CLAUDE.md`。架构事实冲突以 `tools/check/arch.sh` 与 `.claude/rules/project_rule.md` 为准。
