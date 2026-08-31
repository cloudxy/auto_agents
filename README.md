# Auto Agents

> 综合数据智能平台：**智能爬虫 + 大模型管理（cc-switch 式）+ new-api token 智能调度 + 官网与后台**。
> 技术底座：FastAPI 后端 + Scrapy 分布式爬虫（scrapy-redis）+ React 19 双前端，统一配置、统一基础设施（uv workspace）。

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
| **智能爬虫** | 后台「爬虫管理」 | 免代码采集：通用选择器爬虫（generic）与流程爬虫（列表/翻页/详情/条件过滤，flow_generic）；任务队列、定时调度、失败自动重试、增量去重、质量评分、AI 自动生成采集方案 |
| **大模型管理** | 后台「LLM 配置」 | cc-switch 式多供应商注册表：API Key Fernet 加密存储、单激活热切换、连通性测试（延迟+模型回显）；为 AI 采集规划提供 LLM 能力 |
| **token 智能调度** | 后台「中转站」 | 对外部 [new-api](https://github.com/QuantumNous/new-api) 网关的管控侧：渠道额度巡检熔断（超限自动下线/冷却恢复）、渠道真伪探针（10 维行为指纹）、事件时间线 |
| **官网与后台** | 9113 / 9112 | 官网（产品展示）+ 管理后台（仪表盘/爬虫/AI 采集/LLM/中转站/日志/用户/数据中心/设置） |

> 定位说明：token 调度模块是 new-api 实例的**外挂巡检器**（额度熔断 + 真伪探针 + 只读总览），请求转发/计费由 new-api 本体承担；生产部署编排见 [deploy/newapi/](deploy/newapi/)。

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
│               │  + 后台消费者    │   backend)    │  models/schemas │
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

> **双进程心智模型**：backend（含任务分发消费者）与 scrapy Worker 是两个进程。**Worker 不启动，任务会一直停在 pending**——用 `uv run python run.py spider --list` 查看/启动，后台「爬虫管理→节点」可看 Worker 心跳。

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
├── run.py / run_backend.py / run_spider.py / run_frontend.py
│                                 # 全栈编排入口（all / backend / spider / frontend）
├── backend/                      # FastAPI 后端（workspace member）
│   ├── app/api/v1/               # 9 个业务域（见「API 设计」）
│   ├── app/api/v2/               # 增强版健康检查
│   ├── app/external_api/v1/      # 外部 API：API Key 数据查询 + Webhook 回调
│   ├── services/                 # 20+ 服务（spider 三域拆分 / ai_planner / llm_provider /
│   │                             #   channel_scheduler / channel_probe / auth / notify ...）
│   ├── repositories/             # 数据访问（继承 BaseRepository）
│   ├── tasks/consumer.py         # Redis 三循环消费者（分发/回流/重试）
│   ├── alembic/                  # 数据库迁移
│   └── scripts/set_admin_account.py   # 初始管理员脚本
├── scrapy/                       # Scrapy 分布式爬虫（workspace member）
│   ├── spiders/                  # base / generic（通用选择器）/ flow_generic（流程）
│   │                             #   + example / zhihu_feed / dianping_home / openweather
│   ├── middlewares/              # UA 轮换 / 代理评分 / 账号会话 / 任务控制 / 重试 / Playwright
│   ├── pipelines/                # Clean → Validate → QualityCheck → Store（Redis 队列）
│   └── extensions/               # 关闭 Webhook（HMAC 签名）/ 空闲自动收尾
├── platform_core/                # 共享基建：db / redis_async / queues(分布式锁) /
│                                 #   logger / storage / repository / models / schemas / exceptions
├── config/                       # Dynaconf 多层合并（backend & scrapy 共用）
├── frontend/admin/               # 管理后台（React 19 + antd 6 + Zustand + axios）
├── frontend/official/            # 官网（React 19 + antd + Framer Motion）
├── deploy/newapi/                # new-api 网关独立部署编排
├── scripts/                      # bootstrap-db / check-arch / migrate / start ...
├── skills-library/               # 多工具共享 skill 库（内容文件/adapters；治理并入主 API v1/skills）
├── .agents/skills/               # 工具中立 AI 资产（/new-svc /new-spider /check-arch ...）
└── .claude/                      # Claude Code 协作层（IDENTITY/SOUL/MEMORY/agents/hooks）
```

---

## 快速开始

### 前置依赖

| 工具 | 版本 | 用途 |
|------|------|------|
| Python | 3.13+ | 后端 / 爬虫 |
| Node.js | 18+ | 前端 |
| MySQL | 8.0+ | 主数据存储 |
| Redis | 6+ | 队列调度 / 缓存 / 分布式锁 |
| uv | 最新 | Python 依赖管理 |

### 1. 安装依赖

```bash
uv sync                                            # Python 一把梭（backend + scrapy 全部装入根 .venv）
cd frontend/admin    && npm install && cd ../..     # 后台
cd frontend/official && npm install && cd ../..     # 官网
```

### 2. 配置敏感信息

复制 `.env.example` 为 `config/local/.env`，填入 MySQL/Redis 密码与 JWT 密钥（**JWT 不允许使用默认占位符，否则启动即拒绝**）：

```env
AUTO_AGENTS_MYSQL__DEFAULT__PASSWORD=xxx
AUTO_AGENTS_REDIS__DEFAULT__PASSWORD=xxx
AUTO_AGENTS_JWT__SECRET_KEY=<32位以上随机串>
```

### 3. 初始化数据库

```bash
bash scripts/bootstrap-db.sh     # 新环境唯一推荐入口：建库 → 基线表 → 迁移链 head（幂等）
```

> 直接 `alembic upgrade head` 在空库上会因基线表缺失失败（已知遗留项，见脚本头注释），务必走 bootstrap-db.sh。

### 4. 创建管理员并启动

```bash
uv run python backend/scripts/set_admin_account.py   # 创建/重置 admin（默认 123456，务必登录后修改）

uv run python run.py all            # 后端(9111) + 后台(9112) + 官网(9113)
uv run python run.py spider         # 另开终端：启动爬虫 Worker（不启动则任务一直 pending）
```

### 5. 访问入口

| 服务 | 地址 |
|------|------|
| 管理后台 | http://127.0.0.1:9112 |
| 后端 API 文档（Swagger） | http://127.0.0.1:9111/docs |
| 后端健康检查 | http://127.0.0.1:9111/api/v1/health |
| 官网 | http://127.0.0.1:9113 |

本地联调也可 `docker compose up --build`（backend + MySQL + Redis；注意需为容器覆盖 `AUTO_AGENTS_API__HOST=0.0.0.0`）。

---

## 第一个采集任务

1. 浏览器打开 http://127.0.0.1:9112 ，用管理员账号登录；
2. 左侧「爬虫管理 → 任务列表」→「新增任务」；
3. 选择爬虫（如 **generic 通用采集**）→ 填写目标 URL 与要提取的字段（选择器支持 css / xpath / regex）；
4. 「提交任务」——系统自动打开日志抽屉实时观察执行；
5. 任务完成后点该行「结果」查看数据，可导出 CSV / JSON。

进阶玩法：

- **AI 自动生成采集方案**：「AI 采集 → 采集向导」，输入目标页 URL，LLM 自动规划选择器并试采验证，通过后一键注册为新爬虫（需先在「LLM 配置」激活一个供应商）；
- **周期采集**：「爬虫管理 → 定时任务」，按 cron 定时执行；
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

「AI 采集 → 采集向导」：输入目标 URL → LLM 规划选择器方案（可人工微调）→ 自动试采与质量评判（失败自动修复迭代，最多 2 轮）→ 一键上线注册为 flow_generic 爬虫。前置条件：LLM 配置页已激活供应商。

### 大模型管理（LLM 配置）

多供应商注册（openai_compatible 协议）；API Key Fernet 加密落库、接口出参掩码；行内「测试连通性」回显延迟与模型；「激活」热切换（全表至多一个激活；未激活时回退 `config/default/llm.yml` + 环境变量兜底）。

### new-api 中转站管控

三个只读视图：渠道总览（额度窗口用量）/ 探针结果（渠道真伪判定）/ 事件时间线（熔断与恢复动作）。渠道额度巡检器随 backend 启动，超限渠道自动下线（status=3）、冷却到期复核恢复；渠道级额度配置经 Redis hash `newapi:channel:cfg:{id}` 下发。部署见 [deploy/newapi/README.md](deploy/newapi/README.md)。

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
| `/newapi` | newapi | 中转站总览 / 渠道事件 / 探针结果 |
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

### 架构红线（12 条 + 3 边界，机械可检查）

```bash
bash scripts/check-arch.sh      # 退出码 = 违规数（pre-commit 与 CI 自动执行）
```

核心：禁止硬编码连接串/密钥；爬虫禁止 import backend、禁止直写主库；爬虫必须配反爬（DOWNLOAD_DELAY + UA 轮换）；API 层禁止 import ORM；async 上下文禁止同步 Redis 链式直调（统一 `get_async_redis()`）；完整清单见 `.claude/rules/project_rule.md`。

### 质量门禁

```bash
uv run pytest -x -q backend/tests   # 后端测试必须退出码 0
bash scripts/check-arch.sh          # 数据契约改动必跑
uv run pre-commit install --hook-type pre-commit --hook-type pre-push
```

CI 三阶段：Python lint+test → 架构红线 → 前端构建。

---

## 运维脚本

| 脚本 | 用途 |
|------|------|
| `scripts/bootstrap-db.sh` | **新环境唯一推荐入口**：建库 → 基线表 → 迁移（幂等） |
| `scripts/migrate.sh` | 执行 Alembic 迁移到最新 |
| `scripts/init_db_sync.py` | create_all 基线建表（bootstrap-db.sh 的内部依赖，勿单独使用） |
| `scripts/check-arch.sh` | 架构红线扫描（退出码 = 违规数；pre-commit 与 CI 自动执行） |
| `backend/scripts/set_admin_account.py` | 创建/重置管理员账号（默认 admin/123456，登录后请修改） |

> 旧脚本（init-db.sh / init-database.sh / start.sh / start_frontend.sh / run-spider.sh / init_worktree.sh）已于 2026-08-31 清理：初始化统一走 bootstrap-db.sh，启停统一走 `run.py` 编排器（诊断报告第 9 章决策）。

---

## 故障排查 FAQ

| 现象 | 原因与处理 |
|------|-----------|
| 任务一直 `pending` | 爬虫 Worker 未启动：另开终端 `uv run python run.py spider`；后台「爬虫管理→节点」确认心跳 |
| 任务日志抽屉为空 | 任务日志读取共享日志文件（backend 与 Worker 需同一文件系统）；跨机部署时需共享 `logs/spider/` 或检查 `config/default/log.yml` 路径 |
| 任务失败，错误是 "params 缺少 urls" | 多为 params JSON 写错（引号/逗号）；对照「爬虫参数契约」检查 |
| 提交任务报"请先登记" | 目标爬虫未在注册表登记或已停用：后台「爬虫管理→爬虫定义」登记/启用 |
| 登录 401 频繁 | Token 30 分钟过期，重新登录即可 |
| 429 / 403 被风控 | 提高 `DOWNLOAD_DELAY`、启用 UA 轮换与代理（站点级策略 `config/scrapy/default/sites.yml`） |
| `git push` 报 `Failed to connect to 127.0.0.1 port 7897` | 本机代理软件未启动但 shell 设了 `HTTP_PROXY/HTTPS_PROXY`：启动代理，或 `unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy`（详见诊断报告附录 8.3） |
| 启动报 JWT SECRET_KEY 错误 | 使用了默认占位符；在 `config/<env>/.env` 配置 `AUTO_AGENTS_JWT__SECRET_KEY`（注意键名格式，不支持 `${}` 展开） |

---

## 技术栈速查

| 模块 | 技术 |
|------|------|
| 后端 | FastAPI / SQLAlchemy 2 / PyMySQL + aiomysql / redis-py(async) / Pydantic 2 / PyJWT / Loguru / Alembic |
| 爬虫 | Scrapy ≥2.15 / scrapy-redis / DrissionPage / Selenium / httpx |
| 前端 | React 19 / TypeScript / Ant Design 6 / React Router v7 / Zustand / axios / Framer Motion(official) |
| 配置 | Dynaconf ≥3.2 |
| 数据 | MySQL 8 / Redis 6+ |
| 包管理 | uv（Python workspace）/ npm |
| AI 协作 | Claude Code（`.claude/` 协作层：IDENTITY / SOUL / MEMORY / agents / hooks / skills） |

> AI 协作层不是运行时依赖；项目名 `auto_agents` 中的 "agents" 指自动化爬虫工人。项目协作 skills 位于 `.agents/skills/`（工具中立），`.claude/skills` 为 symlink。跨工具共享的 skill 目录库在 [`skills-library/`](skills-library/README.md)（内容文件与适配器载体；**治理/评分/矫正并入主 API `v1/skills`**，本地 8765 后台已退役 deprecated）。

---

## 相关文档

- **[全系统架构与模块诊断报告（docs/architecture-audit-2026-08.md）](docs/architecture-audit-2026-08.md)** —— 63+8 项问题清单（P0/P1/P2 带证据）、LLM 故障转移与 new-api 调度接线设计、对标 EasySpider/crawlab/spider-flow 的易用性优化方案、SaaS 多租户升级方案（企业子账号管理）、自动化脚本存废决策、分批修复路线图
- 项目规则（12 红线 + 3 边界）：`.claude/rules/project_rule.md`
- new-api 网关部署：[deploy/newapi/README.md](deploy/newapi/README.md)
- AI 协作层：`.claude/IDENTITY.md` / `SOUL.md` / `MEMORY.md`、子代理 `spider-doctor / arch-warden / memory-curator`
- 常用 Skill：`/new-svc` `/new-spider` `/new-model` `/check-arch` `/verify` `/coding-style` `/logging` `/config` `/deploy` `/cicd`
- 跨工具 skill 库：[skills-library/README.md](skills-library/README.md)
