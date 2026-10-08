# AGENTS.md - Auto Agents 项目指南

多应用混合平台：FastAPI 后端 + Scrapy 分布式爬虫 + React 双前端（admin 后台 / official 官网），
统一配置、统一基础设施、统一 Python 环境。

本文件是**所有 AI 工具共用的唯一项目指南**：Codex、Grok 直接读取；Gemini 经根目录 `GEMINI.md`（指向本文件的链接，任意子目录启动都能读到）与 `.gemini/settings.json` 的 `context.fileName` 读取；Claude Code 经 `CLAUDE.md` 的 `@AGENTS.md` 导入，Claude 专属内容（子代理、hooks）只写在 `CLAUDE.md`。不要再新建其他工具的指令文件副本。

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
| 部署 | `deploy/` | `litellm/` 平台 LLM 网关编排；`newapi/` 已退役运行时的历史编排（默认不启） |
| 质量门禁 | `tools/` | `check/`（arch / db / frontend / 插件引用）+ OpenAPI 导出 |
| 开发协作 | `.agents/` | 项目 skill、规则、第三方插件指针（按 `plugins-lock.json`）；`.claude/` `.codex/` `.grok/` 只做适配器 |

## 环境红线（uv workspace，必须遵守）

- 根 `.venv` 是**唯一**的 Python 虚拟环境，禁止创建 `backend/.venv` 或 `scrapy/.venv`
- 加依赖用 `uv add --package auto-agents-backend <pkg>`，禁止 `cd backend && uv add`
- `uv.lock` 必须提交（可复现性保证），禁止加入 `.gitignore`
- `platform_core/` 是源码包，经 `sys.path` 引入，不打包、不进 workspace
- 前端用仓库根 `package.json` workspaces + 根 `package-lock.json`；先 `npm ci`，再 `npm run build:shared`

## 架构红线 + 核心边界（R1–R13 + B1–B4，机械可检查）

权威清单是 `tools/check/arch.sh`（以脚本输出为准，不要靠记忆数条数）。提交前 pre-commit + CI 会跑。核心约束：

- 禁止硬编码连接串/密钥/端口（配置即代码）
- 爬虫禁止 import backend、禁止直写主库（走 Redis 队列）
- 爬虫必须配反爬（DOWNLOAD_DELAY + USER_AGENT 轮换）
- API 层禁止直接 import ORM 模型；ORM 禁止 import Pydantic schema（模型即契约）
- async 上下文禁止同步 `redis_client()` 链式直调，统一走 `get_async_redis()`（R11）
- 租户过滤收口（R13）；`spider_service` 门面白名单（R12）
- 核心边界：`platform_core/` 只依赖 `config/`（B1）；`backend/` 禁止 import `scrapy/`（B2）；`config/` 不依赖任何业务模块（B3）；四柱域 import 边界（B4，ADR-0010：`power_market` 禁 spider_/newapi_/litellm_/relay_/channel_/ai_planner/llm_gateway 直连；`ai_planner` 只禁 llm_gateway.admin，chat 仅 llm_client.py 可用；backend 对网关只走 HTTP，禁 DSN/create_async_engine）

## 规则（`.agents/rules/`，所有工具共用）

回答、写代码、改架构前按触发条件读对应规则（Claude Code 经 `.claude/rules` 链接自动加载，其他工具按需读取）：

| 规则 | 何时读 |
|------|--------|
| [`project_rule.md`](.agents/rules/project_rule.md) | 新建模块、改分层、引入依赖、涉及数据 / 配置：架构哲学、红线、模块边界 |
| [`answer_rule.md`](.agents/rules/answer_rule.md) | 回答问题、输出方案、写代码：解决问题优先、用证据说话 |
| [`pua.md`](.agents/rules/pua.md) | 同一问题失败 ≥ 2 次、想放弃、用户不满：穷尽式问题解决 |

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
- `scrapy/settings.py` — 爬虫配置（从 `config/` 注入）
- `init_project.sh` — 新人一键初始化
- `tools/check/arch.sh` — 架构红线扫描（退出码 = 违规数）
- `.agents/README.md` — 开发协作中枢契约
- `plugins-lock.json` + `scripts/agents_plugins.py` — 第三方插件锁与同步（`sync` / `check` / `lock`）
- `.claude/hooks/*.sh` — Claude Code Hook（bash >= 3.2 + grep/sed/awk；jq 可选）

## 快速开始

```bash
bash init_project.sh                       # 新人一键初始化（uv sync + npm ci + build:shared + 建库 + admin 账号）
uv run python run.py                       # 默认启动全部（已运行则跳过）
uv run python run.py status                # 查看运行状态
uv run python run.py stop                  # 停止全部
uv run python run.py restart               # 强制重启
uv run python run.py start backend         # 单独启动：backend / spider / frontend
uv run python run.py spider --list         # 列出爬虫
uv run pytest -x -q backend/tests          # 后端测试
bash tools/check/arch.sh                   # 架构合规检查（退出码 = 违规数）
npm run gen:api                            # 后端 OpenAPI 变更后：dump → shared 类型重生成 → shared 重建
uv run pre-commit install --hook-type pre-commit --hook-type pre-push --hook-type post-checkout
python3 scripts/agents_plugins.py sync     # 按 plugins-lock.json 接好第三方插件（新机器首次）
```

端口：backend `9111` / admin `9112` / official `9113`。

环境切换：所有入口接受 `--env {local,dev,prod}`。本地联调全栈：`docker compose up --build`（backend + MySQL 8 + Redis 7；compose 已设 `AUTO_AGENTS_API__HOST=0.0.0.0`）。

## 验证与交付约定

- 任何「已完成」陈述必须伴随可验证输出（测试输出 / curl 结果 / 构建日志）
- 后端改动：`uv run pytest -x -q backend/tests` 必须退出码 0；lint：`uv run ruff check backend platform_core scripts`（只查 E9+F401）
- 数据契约改动（models/schemas）：额外跑 `bash tools/check/arch.sh`
- 迁移改动：`bash tools/check/db_ir.sh` + `bash tools/check/db_migrations.sh`（CI db-migration-gate 同款）
- 前端改动：`npm run check-frontend`（F-5/F-6 门禁）；测试 `npm test -w admin` / `npm test -w official`
- 真库保真测试默认跳过，需 `MYSQL_FIDELITY=1`（CI 用 MySQL service container 承载）
- CI 五阶段：Python lint+test / 架构红线 / DB 迁移门禁 / 前端构建 / Docker 校验

## Skill 路由（`.agents/`）

中枢契约见 `.agents/README.md`。项目 skill 在 `.agents/skills/`：Codex、Grok、Gemini 原生读取这个目录，只有 Claude Code 需要 `.claude/skills` 链接过来（不要再给其他工具建链接，会出现同名技能重复）。产品扫描走 `capability-library/`（**技能治理在主 API `v1/skills` + `v1/capabilities`**）。

`.agents/agents/*.md` 与 `.agents/commands/*.md` 是**顶层游离资产位**（feat-agents-market OQ-1）：目录导入落盘与同步扫描都认这两处，不属于任何插件；目录不存在时行为与扩展前一致。

第三方插件采用「引用 + 锁文件」：仓库根 `plugins-lock.json` 是启用插件的唯一清单（git 来源 + 固定 commit + 接入哪些宿主），目前只有 `sdlc-workflow`（`https://github.com/cloudxy/sdlc-plugins`）。正文只在本机 `~/.zcode/local-plugins/<name>`，仓库内只放符号链接：`python3 scripts/agents_plugins.py sync` 按锁克隆缺失正文、建好 `.agents/plugins` 与各宿主适配器链接、删掉锁外插件的链接；`check` 只读校验；正文更新并推到远端后用 `lock` 改锁。**所有 AI 工具只能引用插件、禁止复制**（不用 `claude plugin install` / `grok plugin install` / `codex plugin add`；`tools/check/arch.sh` PL 段按锁文件把关，细则见 `.agents/README.md`）。

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

## 项目状态

已落地：异常 / CORS / 日志收敛到 `platform_core`；Python 单一 `.venv`；前端 npm workspaces + `frontend/shared`；开发协作中枢 `.agents/`（skill、规则、插件锁）。

进行中：四柱程序（采集出数环 / SaaS / LiteLLM 数据面 / 能力市场）。平台 LLM 网关目标为 LiteLLM；`/api/v1/newapi` 与 `deploy/newapi` 是遗留管控面，默认关闭，不作为长期运行时。

待办：开发中枢与产品内容源解耦（决策 D2）——能力市场同步目前直接扫描 `.agents/`，本仓库的开发 skill 会被当成产品资产上架；解耦前不要往 `.agents/agents/`、`.agents/commands/` 放开发专用内容。

Claude 专属内容见 `CLAUDE.md`。架构事实冲突以 `tools/check/arch.sh` 与 `.agents/rules/project_rule.md` 为准。
