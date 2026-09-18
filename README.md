# Auto Agents

> 综合数据智能平台：**智能采集 + SaaS 租户 + 能力市场 + 平台 LLM 网关 + 官网与后台**。
> 技术底座：FastAPI 后端 + Scrapy 分布式爬虫（scrapy-redis）+ React 19 双前端（admin / official，经 `frontend/shared`），uv workspace + npm workspaces。

---

## 目录

- [产品概览](#产品概览)
- [架构总览](#架构总览)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [第一个采集任务](#第一个采集任务)
- [爬虫参数契约](#爬虫参数契约)
- [账号与权限](#账号与权限)
- [功能模块指南](#功能模块指南)
- [API 设计](#api-设计)
- [依赖管理（uv workspace）](#依赖管理uv-workspace)
- [配置管理](#配置管理)
- [开发规范与架构红线](#开发规范与架构红线)
- [运维脚本](#运维脚本)
- [故障排查 FAQ](#故障排查-faq)
- [技术栈速查](#技术栈速查)
- [相关文档](#相关文档)

---

## 产品概览

| 模块 | 入口 | 说明 |
|------|------|------|
| **智能采集** | 后台「数据工厂」 | 免代码采集：generic / flow_generic；任务队列、定时调度、失败重试、增量去重、质量评分、AI 规划试采 |
| **SaaS** | 注册 / 成员 / 用量 | 租户空间、成员、配额；公司管理员与平台超管写面分离 |
| **能力市场** | 后台「资产目录」+ 官网能力/技能 | 技能 / 插件 / 命令 / 智能体 / 专家团 五类平级；治理走 `v1/skills` 与 `v1/capabilities` |
| **大模型管理** | 后台「LLM 配置」 | 多供应商注册表：API Key Fernet 加密、激活切换、连通性测试；租户 BYOK 直连 |
| **中转站** | 后台「中转站管控」 | 平台 LLM 网关目标为 **LiteLLM Proxy**（`deploy/litellm/`）。new-api 为**已退役运行时**：`/api/v1/newapi` 与 `deploy/newapi` 仍在树里，默认关闭，不与 LiteLLM 长期双通道并存 |
| **官网与后台** | 9113 / 9112 | 官网 + 管理后台（五组 IA：概览 / 数据工厂 / 能力资产 / 运营管理 / 系统管理） |

> 平台路径的规划/评分应走 LiteLLM；不要再把 new-api 写成当前可卖的网关产品。

---

## 架构总览

```
┌────────────────────────────────────────────────────────────────────┐
│                          Auto Agents Platform                       │
├───────────────┬──────────────────┬───────────────┬─────────────────┤
│  frontend/    │    backend/      │    scrapy/    │  platform_core/ │
│  admin (9112) │  FastAPI (9111)  │  scrapy-redis │   公共基建层    │
│  official     │  api/v1 + v2     │  独立 Worker  │  db/log/queue   │
│  (9113)       │  external_api/v1 │  (禁 import   │  repo/exception │
│  + shared     │  + 后台消费者    │   backend)    │  models/schemas │
└───────┬───────┴────────┬─────────┴───────┬───────┴────────┬────────┘
        │                │                 │                │
        └──────── config/ (Dynaconf：default → <env> → .env → 环境变量) ┘
                          │
                MySQL 8（主库）+ Redis 6+（队列/缓存/锁）
```

### 任务数据流（核心闭环）

```
后台/API 提交任务 ──► MySQL spider_tasks(pending) + Redis 优先级队列
        │
backend SpiderTaskConsumer（lifespan 常驻）
        │  blpop 任务队列 → 任务置 running → rpush <spider>:start_urls
        ▼
scrapy Worker（独立进程）采集
        │  管道：Clean(200) → Validate(300) → QualityCheck(350) → Store(400)
        │  StorePipeline 把 item rpush 到 spider:item_queue
        ▼
backend consumer 批量取回 → 增量去重 → bulk insert spider_results
        │                       + result_count 累加 + redis/csv 镜像
        ▼
爬虫空闲收尾 → HMAC 签名 Webhook 回调 → 任务终态（completed/failed）
                                    └─ 失败自动重试（1s/5s/15s 退避，最多 3 次）
```

> **双进程心智模型**：backend（含任务分发消费者）与 scrapy Worker 是两个进程。**Worker 不启动，任务会一直停在 pending**。`uv run python run.py` 默认会把 Worker 一起拉起；`uv run python run.py spider --list` 只列爬虫。后台「数据工厂 → 节点监控」可看 Worker 心跳。

### 核心原则

| 价值观 | 落地 |
|--------|------|
| 配置即代码 | 连接串/密钥/端口全部外置 `config/`，按 local/dev/prod 隔离 |
| 爬取与存储分离 | 爬虫只采集清洗，**禁止直写主库**，经 Redis 队列流向后端 |
| 模型即契约 | ORM 在 `platform_core/models`，Pydantic 在 `platform_core/schemas`，互不 import |
| 异步优先 | async 上下文统一走 `get_async_redis()`；同步操作 `to_thread` |
| 独立部署优于耦合 | 本地 uv workspace 单 venv；部署时可按子项目独立打包 |

---

## 项目结构

```
auto_agents/
├── init_project.sh               # 新人一键初始化
├── run.py                        # 统一启停入口（实现在 scripts/runlib/）
├── backend/                      # FastAPI 后端（workspace member）
│   ├── app/api/v1/               # 业务域（auth/spiders/ai/llm/skills/capabilities/…）
│   ├── app/api/v2/               # 增强版健康检查
│   ├── app/external_api/v1/      # 外部 API：API Key 数据查询 + Webhook 回调
│   ├── services/                 # spider / ai_planner / llm / skills / capabilities / tenant ...
│   ├── repositories/
│   ├── tasks/consumer.py         # Redis 三循环消费者（分发/回流/重试）
│   ├── alembic/
│   └── scripts/set_admin_account.py
├── scrapy/                       # Scrapy 分布式爬虫（workspace member）
│   ├── spiders/                  # base / generic / flow_generic + example / zhihu_feed / ...
│   ├── middlewares/              # UA 轮换 / 代理 / 账号会话 / 任务控制 / 重试
│   ├── pipelines/                # Clean → Validate → QualityCheck → Store（Redis 队列）
│   └── extensions/
├── platform_core/                # 共享基建
├── config/                       # Dynaconf 多层合并
├── frontend/
│   ├── admin/                    # 后台（React 19 + antd 6 + Zustand）
│   ├── official/                 # 官网（React 19 + antd + Framer Motion）
│   └── shared/                   # 双应用共享层（先 build dist）
├── deploy/                       # litellm / watchdog / newapi（历史）
├── scripts/                      # 只做初始化辅助 + 启停（lib / runlib / db）
├── tools/                        # 质量门禁与 OpenAPI 导出
├── capability-library/           # 产品能力目录；plugins/ → .agents/plugins
├── .agents/                      # 开发协作中枢（skills/ + plugins/ 指针农场）
├── .claude/                      # 规则 / hooks / agents；skills、plugins 为适配器
└── .grok/                        # Grok 项目配置；plugins/ 为启用子集
```

---

## 快速开始

### 前置依赖

| 工具 | 版本 | 用途 |
|------|------|------|
| Python | 3.13+ | 后端 / 爬虫 |
| Node.js | 20 | 前端（CI 与 Dockerfile 均为 20；根 npm workspaces） |
| MySQL | 8.0+ | 主数据存储 |
| Redis | 6+ | 队列调度 / 缓存 / 分布式锁（compose 用 Redis 7） |
| uv | 最新 | Python 依赖管理 |

### 1. 一键初始化（推荐）

```bash
bash init_project.sh
# 或：uv run python run.py setup
```

会检查 uv / Node，安装 Python 与前端依赖，生成 `config/local/.env`（已有则不覆盖），本机没有 MySQL/Redis 时用 docker compose 拉起，然后建库迁移并创建管理员 `admin / 123456`。

分步等价于：`uv sync` → `npm ci && npm run build:shared` → 写 `.env` → `scripts/db/bootstrap.sh` → `set_admin_account.py`。

### 2. 启动

```bash
uv run python run.py                # 默认启动全部：后端 + Worker + 双前端（已运行则提示跳过）
uv run python run.py stop           # 停止全部
uv run python run.py restart        # 强制重启
uv run python run.py status         # 查看状态
```

### 3. 访问入口

| 服务 | 地址 |
|------|------|
| 管理后台 | http://127.0.0.1:9112 |
| 后端 API 文档（Swagger） | http://127.0.0.1:9111/docs |
| 后端健康检查 | http://127.0.0.1:9111/api/v1/health |
| 官网 | http://127.0.0.1:9113 |

本地联调也可 `docker compose up --build`（backend + MySQL 8 + Redis 7；compose 已注入 `AUTO_AGENTS_API__HOST=0.0.0.0`）。

---

## 第一个采集任务

1. 浏览器打开 http://127.0.0.1:9112 ，用管理员账号登录；
2. 左侧「数据工厂 → 采集任务」→「新增任务」；
3. 选择爬虫（如 **generic 通用采集**）→ 填写目标 URL 与要提取的字段（选择器支持 css / xpath / regex）；
4. 「提交任务」——系统自动打开日志抽屉实时观察执行；
5. 任务完成后点该行「结果」查看数据，可导出 CSV / JSON。

进阶玩法：

- **AI 自动生成采集方案**：「数据工厂 → AI 采集规划」，输入目标页 URL，LLM 自动规划选择器并试采验证，通过后一键注册为新爬虫（需先在「LLM 配置」激活一个供应商）；
- **周期采集**：采集任务里配 cron / 调度（以当前后台「数据工厂」为准）；
- **收藏复用**：任务行「收藏」存为模板，后续一键再跑。

---

## 爬虫参数契约

后台表单会自动生成以下结构；直接调 API 时按下述契约传 `params`（JSON 字符串）。

**generic（通用选择器采集）**

```json
{
  "urls": ["https://example.com/list"],
  "selectors": [
    { "name": "title", "type": "css",   "expr": "h2 a::text" },
    { "name": "link",  "type": "xpath", "expr": "//h2/a/@href" }
  ]
}
```

**flow_generic（流程采集：翻页 / 进详情 / 条件过滤）** —— params 含以下任一段即自动按流程模式执行

```json
{
  "urls": ["..."],
  "selectors": [ { "name": "title", "type": "css", "expr": "..." } ],
  "pagination": { "selector": "a.next", "type": "css", "max_pages": 10 },
  "detail":     { "list_selector": "div.item", "url_selector": "a::attr(href)",
                  "selectors": [ { "name": "content", "type": "css", "expr": "#main::text" } ] },
  "filters":    [ { "field": "title", "op": "contains", "value": "Python" } ]
}
```

**高级参数（可选键）**

| 键 | 类型 | 说明 |
|----|------|------|
| `incremental` | bool | 增量模式：基于内容指纹（md5）跨任务去重 |
| `store_to` | list | 存储镜像，如 `["redis","csv"]` |
| `render_js` | bool | 动态渲染（需 Worker 启用渲染中间件） |
| `wait_for` / `wait_timeout` | str / int | 渲染等待选择器 / 超时秒数 |

---

## 账号与权限

| 角色 | 能力 |
|------|------|
| viewer | 查看仪表盘 / 任务 / 结果 / AI 采集（只读） |
| operator | viewer + 创建/运行/管理任务、模板、调度执行 |
| admin | 全部：LLM 配置、中转站、用户管理、调度与告警规则、系统设置 |

- 自注册用户默认 operator（开放注册开关见 `config`）；
- 首个管理员：`uv run python backend/scripts/set_admin_account.py`（默认口令弱，生产必须修改）；
- Token 30 分钟过期（`config/default/jwt.yml`）。

---

## 功能模块指南

### 智能爬虫体系

- **注册表驱动**：爬虫须在 `spider_definitions` 登记（迁移已预置 6 个）且 enabled 才可提交任务；后台「爬虫定义」Tab 管理登记。
- **反爬中间件**（按优先级）：账号会话(250) / 指纹(300) / 代理评分加权(350) / UA 轮换(400) / 重试(550)；站点级策略见 `config/scrapy/default/sites.yml`。
- **任务控制**：运行中任务可暂停 / 恢复 / 终止（Redis 控制键）。
- **可靠性**：失败自动重试（退避 1s/5s/15s）、增量去重、分布式锁防重复消费、Worker 心跳（「节点」页）。
- **新建爬虫**：`/new-spider` skill 一键脚手架，或后台「AI 采集」由 LLM 生成后自动注册。

### AI 采集规划

「数据工厂 → AI 采集规划」：输入目标 URL → LLM 规划选择器方案（可人工微调）→ 自动试采与质量评判（失败自动修复迭代，最多 2 轮）→ 一键上线注册为 flow_generic 爬虫。前置条件：LLM 配置页已激活供应商。

### 大模型管理（LLM 配置）

多供应商注册（openai_compatible 协议）；API Key Fernet 加密落库、接口出参掩码；行内「测试连通性」回显延迟与模型；「激活」热切换（全表至多一个激活；未激活时回退 `config/default/llm.yml` + 环境变量兜底）。

### 中转站 / 平台 LLM 网关

目标运行时是 **LiteLLM Proxy**（`deploy/litellm/`），平台路径规划/评分走网关，租户自己配的供应商仍直连。

T-20：`deploy/newapi` 已墓碑（进程停止，`NEWAPI.ENABLED` 恒 false 且读路径已删）。值班 URL `/api/v1/newapi` 一周期保留，列表来自 LiteLLM。不要把 new-api 写回根 compose，也不要与 LiteLLM 长期双通道并存。

---

## API 设计

### 双通道结构

```
/api/v1/*       内部 API（JWT）：管理后台、内部服务
/api/v2/*       内部 API：增强健康检查（db / storage）
/external/v1/*  外部 API：API Key 数据查询 + 爬虫回调 Webhook（HMAC-SHA256 签名）
```

### V1 路由域（`backend/app/api/v1/`）

| 前缀 | 模块 | 职责 |
|------|------|------|
| `/auth` | auth | 登录、注册、权限清单 |
| `/spiders` | spiders（5 子域） | 任务运行/控制/日志、结果查询/导出、注册表/定义、定时调度、模板（+告警规则） |
| `/ai` | ai | AI 采集计划（创建/规划/试采/上线注册） |
| `/llm` | llm_providers | LLM 供应商 CRUD / 激活 / 连通性测试 |
| `/newapi` | newapi | 遗留中转站管控面（默认关闭） |
| `/skills` | skills | 技能治理（扫描/评分/矫正）；公开面见 `/public` |
| `/capabilities` | capabilities | 插件/智能体/专家团等能力资产 |
| `/members` | members | 租户成员 |
| `/tenants/me` | tenant_usage | 当前租户用量 |
| `/rbac` | rbac | 权限 |
| `/admin` | admin | 统计、用户列表、审计日志 |
| `/configs` | configs | 系统配置读写 |
| `/health` | health | 存活 / db / storage / redis 探针 |
| `/` | root | 版本信息 |

### 示例

```bash
# 登录取 token
curl -X POST http://127.0.0.1:9111/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"***"}'

# 提交采集任务
curl -X POST http://127.0.0.1:9111/api/v1/spiders/run \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"spider_name":"generic","params":"{\"urls\":[\"https://example.com\"],\"selectors\":[{\"name\":\"title\",\"type\":\"css\",\"expr\":\"h1::text\"}]}"}'

# 查询任务结果 / 导出
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:9111/api/v1/spiders/results/{task_id}"
curl -O -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:9111/api/v1/spiders/results/{task_id}/export?format=csv"
```

---

## 依赖管理（uv workspace）

根目录一个 `.venv`，`backend/` 与 `scrapy/` 作为 workspace member 各自保留 `pyproject.toml`——依赖声明分散、安装环境统一。

```bash
uv sync                                                        # 装齐所有依赖
uv add --package auto-agents-backend  fastapi-pagination       # 给后端加包
uv add --package auto-agents-spider   playwright               # 给爬虫加包
uv sync --package auto-agents-backend --no-dev                 # 部署：后端独立打包
```

**红线**：❌ 禁止创建 `backend/.venv`、`scrapy/.venv`；❌ 禁止 `cd backend && uv add`；❌ 禁止 gitignore `uv.lock`；⚠️ shell 残留 `VIRTUAL_ENV` 时先 `unset VIRTUAL_ENV UV_PROJECT_ENVIRONMENT`。

---

## 配置管理

### 加载顺序（后者覆盖前者）

```
1. config/default/*.yml           通用默认
2. config/scrapy/default/*.yml    爬虫默认
3. config/<env>/*.yml             环境覆盖（local / dev / prod）
4. config/scrapy/<env>/*.yml      爬虫环境覆盖
5. config/<env>/.env              敏感变量（密码、密钥；已 gitignore）
6. AUTO_AGENTS_* 环境变量          最高优先级（双下划线嵌套：AUTO_AGENTS_JWT__SECRET_KEY）
```

```python
from config import settings, APP_ENV
settings.API.PORT              # 9111
settings.MYSQL.DEFAULT.HOST    # "127.0.0.1"
settings.REDIS.DEFAULT.URL     # 自动注入（含密码）
```

**敏感信息禁止写 yml 明文**；`.env` 支持 `AUTO_AGENTS_<SECTION>__<KEY>` 双下划线映射（注意：`.env` 内不做 `${VAR}` 展开，由部署脚本直接注入真实值）。

---

## 开发规范与架构红线

### 分层铁律

```
API Routes → Services → Repositories → Models(ORM)
   ↓            ↓            ↓             ↓
 请求校验     业务编排      数据访问      数据契约（与 Schemas 互不 import）
```

### 架构红线（R1–R13 + B1–B3，机械可检查）

```bash
bash tools/check/arch.sh      # 退出码 = 违规数（pre-commit 与 CI 自动执行）
```

核心：禁止硬编码连接串/密钥；爬虫禁止 import backend、禁止直写主库；爬虫必须配反爬（DOWNLOAD_DELAY + UA 轮换）；API 层禁止 import ORM；async 上下文禁止同步 Redis 链式直调（统一 `get_async_redis()`）。条数以 `tools/check/arch.sh` 为准（R1–R13 + B1–B3）；规则正文 `.claude/rules/project_rule.md`。

### 质量门禁

```bash
uv run pytest -x -q backend/tests   # 后端测试必须退出码 0
bash tools/check/arch.sh          # 数据契约改动必跑
uv run pre-commit install --hook-type pre-commit --hook-type pre-push --hook-type post-checkout
```

CI 五阶段：Python lint+test → 架构红线 → DB 迁移门禁 → 前端构建 → Docker 校验。

---

## 运维脚本

初始化：`init_project.sh`。启停：`run.py`（`scripts/`）。门禁：`tools/`。看门狗：`deploy/watchdog.sh`。

| 脚本 | 用途 |
|------|------|
| `init_project.sh` | 新人一键初始化 |
| `run.py` | 启停 |
| `scripts/db/bootstrap.sh` | 建库 → 基线表 → 迁移 |
| `scripts/db/migrate.sh` | alembic upgrade head |
| `tools/check/arch.sh` | 架构红线 |
| `tools/check/frontend.sh` | 前端门禁 |
| `backend/scripts/set_admin_account.py` | 管理员账号（init_project.sh 已调用） |

---

## 故障排查 FAQ

| 现象 | 原因与处理 |
|------|-----------|
| 任务一直 `pending` | 爬虫 Worker 未启动：`uv run python run.py start spider`；后台「数据工厂 → 节点监控」确认心跳 |
| 任务日志抽屉为空 | 任务日志读取共享日志文件（backend 与 Worker 需同一文件系统）；跨机部署时需共享 `logs/spider/` 或检查 `config/default/log.yml` 路径 |
| 任务失败，错误是 "params 缺少 urls" | 多为 params JSON 写错（引号/逗号）；对照「爬虫参数契约」检查 |
| 提交任务报"请先登记" | 目标爬虫未在注册表登记或已停用：采集任务相关登记/启用入口（以当前后台为准） |
| 登录 401 频繁 | Token 30 分钟过期，重新登录即可 |
| 429 / 403 被风控 | 提高 `DOWNLOAD_DELAY`、启用 UA 轮换与代理（站点级策略 `config/scrapy/default/sites.yml`） |
| `git push` 报 `Failed to connect to 127.0.0.1 port 7897` | 本机代理软件未启动但 shell 设了 `HTTP_PROXY/HTTPS_PROXY`：启动代理，或 `unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy`（详见诊断报告附录 8.3） |
| 启动报 JWT SECRET_KEY 错误 | 使用了默认占位符；在 `config/<env>/.env` 配置 `AUTO_AGENTS_JWT__SECRET_KEY`（注意键名格式，不支持 `${}` 展开） |

---

## 技术栈速查

| 模块 | 技术 |
|------|------|
| 后端 | FastAPI ≥0.135 / SQLAlchemy 2 / PyMySQL + aiomysql / redis-py(async) / Pydantic 2 / PyJWT / Loguru / Alembic |
| 爬虫 | Scrapy ≥2.15 / scrapy-redis / DrissionPage / Selenium / httpx |
| 前端 | React 19 / TypeScript / Ant Design 6 / React Router v7 / Zustand / axios / React Query / Framer Motion(official) / `frontend/shared` |
| 配置 | Dynaconf ≥3.2 |
| 数据 | MySQL 8 / Redis 6+（compose：Redis 7） |
| 包管理 | uv（Python workspace）/ npm workspaces |
| 平台 LLM 网关 | LiteLLM Proxy（目标）；new-api 遗留管控面默认关闭 |
| AI 协作 | `.agents/` 中枢；`.claude/` 规则与 hooks；`.grok/` 启用子集 |

> AI 协作层不是运行时依赖；项目名 `auto_agents` 中的 "agents" 也指采集工人。开发协作中枢在 `.agents/`（契约：`.agents/README.md`）。技能治理在主 API `v1/skills` 与 `v1/capabilities`。

---

## 相关文档

- 平台方案 / ADR / 诊断档案：`docs/` 为本地私有内容不入库
- 项目规则：`.claude/rules/project_rule.md`；机械检查：`tools/check/arch.sh`（R1–R13 + B1–B3）
- 词汇：`CONTEXT.md`
- 平台 LLM 网关：`deploy/litellm/`（new-api 历史编排：`deploy/newapi/`，默认不启）
- 开发协作中枢：`.agents/README.md`
- Claude 子代理：`.claude/agents/`（`arch-warden` / `spider-doctor` / `memory-curator`）
- 常用 Skill：`/new-svc` `/new-spider` `/new-model` `/db-design` `/check-arch` `/verify` `/deploy` `/cicd`
