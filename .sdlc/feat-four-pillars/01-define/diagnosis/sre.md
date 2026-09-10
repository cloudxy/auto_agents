# SRE 诊断 · feat-four-pillars（智能采集 + SaaS + 中转站 + Power Market）

| 字段 | 值 |
|------|----|
| 角色 | sre（定义帽并行诊断；不实现、不写业务代码、不改 schema、**本波次不改 deploy/compose**） |
| 日期 | 2026-09-07（refresh） |
| 复核 HEAD | `44e9446`（`deploy:litellm`；工作区相对 origin **ahead 1**） |
| 泳道 | L4（`state.yaml`：schema / 租户 / 外部契约 / 不可逆 / 新依赖 / 多子项目 全 true） |
| 宪法 | `sdlc.config.yaml` → `.claude/rules/project_rule.md`（R1 配置即代码、独立部署、爬取与存储分离） |
| 范围 | 部署编排、compose、密钥、可观测/告警、回滚；目标态对照 `power-market-design.md` |
| 放行 | 本文件不做 QC 放行。回滚路径**未在真实环境实测**（见 §8） |

本轮复核（只读）：根/`deploy/newapi` compose、`Dockerfile`、`.github/workflows/ci.yml`、`config/`、`run.py`/`run_*.py`、`scripts/watchdog.sh`/`migrate.sh`、`backend/app/api/v1/health.py`、`platform_core/db.py`、git 事故提交、`power-market-design.md` Observability/Rollout。  
本轮命令指纹：`docker compose -f docker-compose.yml config --quiet` **exit 0**。`deploy/newapi/*.yml` 无 `.env` 时插值失败（`SESSION_SECRET is required`）——fail-fast 有效，但 **CI 不跑这两份文件**。未跑 `docker build`、未演练 rollback、未拉 Actions 日志。

信号源：`README.md`、`docker-compose.yml`、`Dockerfile`、`deploy/`、`.github/workflows/ci.yml`、`config/`、`sdlc.config.yaml`、`.sdlc/feat-four-pillars/state.yaml`、`/Users/xuyun/Documents/grok-files/power-market-design.md`。

---

## 0. 结论（给 PM 的一页）

当前仓库能撑**本机联调**（`run.py` + 根 compose 的 backend/MySQL/Redis），**撑不住**四支柱生产面。

| ID | 问题 | 为什么 | 改进（NFR，本波次不落地） |
|----|------|--------|---------------------------|
| C1 | 拓扑残缺 | 根 compose 只有 backend+MySQL+Redis；Worker/前端/new-api/CACHE_DIR/watchdog/反代都不在编排里 | 编排一等公民：backend、scrapy Worker、静态前端、new-api、CACHE_DIR 卷、watchdog 可独立扩缩 |
| C2 | 观测残缺 | 有 `/health/deep` 与终态 `alert_rules`，无 Prometheus/OTel/P95/连接池/队列对外告警；Notify 默认仅 `log` | 四类指标 + P0/P1 非 log 渠道 + 每条 runbook 入库 |
| C3 | 回滚空洞 | `docs/ops/deploy.md` 被引用但 `docs/` gitignore；无镜像仓库/tag/CD/canary；Alembic down 不在 CI | 入库 runbook；tag 规范；expand 迁移 up→down→up；listing/installs 补偿流程 |
| C4 | 密钥事故（P0） | `deploy/litellm/config.gen.yaml` **git 跟踪 + 明文上游 Key**；文件头自称 gitignore，根 `.gitignore` 未登记 | 立即轮换已出现过的上游 Key、从历史剔除、补 ignore、加 secrets scan |
| C5 | CI 与目标态脱节 | 闸门覆盖 Python lint/test + 架构 + 迁移静态检查 + 前端 workspaces build；**不**校验 new-api compose、**不**装 Power Market 源、**不**测 scrapy 包、Dockerfile 前端 COPY 已删除的 per-app lockfile | Dockerfile 与根 `package-lock.json` 同源；new-api `compose config` 进 CI；secrets scan；scrapy 进 ruff |

四支柱各自的致命依赖：采集要 **独立 Worker + 共享 Redis + 共享日志盘**；SaaS 要 **租户灰度与不可逆 DDL 纪律**；中转站要 **隔离网络 + backend 能访问 new-api**；Power Market 要 **CI/生产可解析的 git 源 + 可驱逐 CACHE_DIR + `ENABLED` 开关**。现在四条链路都没有端到端编排。

---

## 1. 运行时拓扑（现状 vs 目标）

### 1.1 现状（已核实）

```
  CRA 开发服务器（不在 compose）
  admin :9112     official :9113
        \              /
         \            /
      FastAPI backend :9111
      ├ lifespan: SpiderTaskConsumer / SpiderScheduler /
      │            LlmUsageFlush / (opt) LlmHealthPatrol /
      │            SkillScoringWorker / ChannelScheduler / ChannelProbe
      │            （任一失败仅 warning，不阻断启动）
      ├ 深探测: GET /api/v1/health/deep  → MySQL SELECT 1 + Redis PING
      └ 静态产物: 镜像内 frontend-dist/{admin,official}  **无进程提供 HTTP**
              │
              ├── 平台 MySQL 8（compose 服务 mysql，卷 mysql_data；镜像未钉补丁）
              ├── 平台 Redis 7（compose 服务 redis，**无数据卷**）
              │         ▲
              │         │ Redis 队列 / 心跳 / 锁（B2 唯一允许的耦合）
              │         │
              └── scrapy Worker（run_spider.py，**compose 无此服务**）
                        │ 心跳 spider:worker:{id} TTL 30s（失败只 print）
                        │ 日志 logs/spider/spider.log（需与 backend 同文件系统）

  另一套 compose（deploy/newapi/，独立网络 newapi-net，不并入根文件）
      new-api :3000  → newapi-mysql / newapi-redis   或 SQLite ./data
      backend 默认 NEWAPI.BASE_URL=http://localhost:3000，ENABLED=false
      根 compose 的 backend **未加入 newapi-net**

  不在任何编排中
      scripts/watchdog.sh（默认只告警不杀进程；B4 已实测修过两处真缺陷）
      POWER_MARKET.CACHE_DIR / 源适配器（yml 尚未入库；全库无 POWER_MARKET 键）
      ~/.zcode/local-plugins、Kimi daimon 树（仅操作者 macOS）
      deploy/litellm（生成配置，非运行单元；**已被 git 跟踪**）
```

证据：

- 根编排自白「backend + MySQL + Redis」；生产文档指针指向缺失文件：[`docker-compose.yml`](docker-compose.yml) L1–L9。本轮 `docker compose config --quiet` exit 0。
- 双进程心智模型（Worker 不启动则任务永 pending）：[`README.md`](README.md) L60–L79。
- new-api 故意隔离：[`deploy/newapi/README.md`](deploy/newapi/README.md) L8–L11、[`deploy/newapi/docker-compose.yml`](deploy/newapi/docker-compose.yml) L4–L5。
- 镜像把前端 dist 拷进 `/app/frontend-dist`，「供后续 nginx/静态服务接入」，仓库无 nginx/Caddy：[`Dockerfile`](Dockerfile) L38–L40。
- `run.py all` 只拉 backend + 双前端，**不含 spider**：[`run.py`](run.py) L9–L14。
- `config/default/` 无 `power_market.yml`。目标键来自设计 D13/D16：`POWER_MARKET.CACHE_DIR`、`AUTO_AGENTS_POWER_MARKET_SOURCES`。

### 1.2 四支柱目标拓扑（设计已写、编排未接）

| 支柱 | 运行单元 | 依赖 | 故障域 |
|------|----------|------|--------|
| 智能采集 | backend 消费者 + **N 个 scrapy Worker** + Redis 队列 | 平台 MySQL、共享 `logs/spider/`、可选 Playwright | Worker 挂 → pending 堆积；Redis 丢数据 → 任务/结果断链 |
| SaaS | 同一 backend（租户中间件）+ admin | JWT、租户行级隔离、配额 | 无租户灰度；不可逆 DDL（如 `024` NOT NULL） |
| 中转站 | **独立** new-api + 其 MySQL/Redis；backend 内调度/探针 | `NEWAPI.ACCESS_TOKEN` / `DB_DSN` / `BASE_URL`；网络互通 | 两套库、两套 Redis；backend 容器默认打不到 sidecar |
| Power Market | 同 backend 进程内适配器 + **CACHE_DIR 磁盘** + 可选 git 网络 | `ENABLED`、`SOURCES`、指针目录、公开 API 限流 | CI/Linux 无 `~/.zcode` / Kimi 路径；clone 失败则商店正文 404 |

独立部署优于耦合（宪法）：采集 Worker、new-api、前端静态、backend API **应可独立扩缩与回滚**。现状是「一个 backend 镜像假装全栈」。

### 1.3 拓扑缺口清单

| ID | 缺口 | 严重度 | 证据 |
|----|------|--------|------|
| T1 | compose 无 spider Worker | P0（采集不可用） | `docker-compose.yml` 无 scrapy 服务；README 明确双进程 |
| T2 | compose 无 admin/official HTTP | P0（SaaS/商店面不可达） | 端口 9112/9113 只在 `run_frontend.py` / `config/default/{admin,official}.yml` |
| T3 | 镜像内 frontend-dist 无服务者 | P1 | `Dockerfile` L38–40 注释「后续接入」 |
| T4 | backend 未加入 `newapi-net` | P1（中转站容器化即断） | 根 compose 无 `networks:`；new-api README §5.2 要求加入后用 `http://new-api:3000` |
| T5 | 平台 Redis **无 volume** | P1（重启丢队列/心跳/调度状态） | 根 compose 仅 `mysql_data:`；new-api Redis 有 `./redis-data`。`newapi:scheduler:state:*` 在**平台** Redis |
| T6 | watchdog 未挂编排 | P1（僵死不退出时 restart 无效） | `scripts/watchdog.sh` L5–13；compose 无 sidecar |
| T7 | 无反代 / TLS / SSE 超时 | P1 | 仅 new-api README 有 Caddy/Nginx 示例；平台 9111/9112/9113 无 |
| T8 | Dockerfile 前端构建与 workspaces 分叉 | **P0（`docker build` 保真度）** | 见 §6.4：per-app lockfile 已删，Dockerfile 仍 COPY |
| T9 | 镜像 `uv sync --package auto-agents-backend --no-dev`，却 COPY 了 `scrapy/` | P2 | `Dockerfile` L29–33；ARM 绕过（`b50be93` uv export）已被 `c3a7d4d` 改回 `uv sync`（无 `--frozen`） |
| T10 | Playwright/Chromium 不在镜像 | P2 | `config/default/settings.yml` `PLAYWRIGHT.ENABLED: false` |
| T11 | `capability-library/` 未进镜像 | P1（Power Market / 技能扫描） | `Dockerfile` 未 COPY；`SKILLS.LIBRARY_ROOT: capability-library` |
| T12 | 日志跨机 | P1 | README FAQ「任务日志抽屉为空」：backend 与 Worker 需同一 `logs/spider/` |
| T13 | `docs/ops/deploy.md` 缺失 | P0（发布/回滚说明书不在仓库） | compose L9、watchdog L68 引用；`.gitignore` L76 `docs/`；`git check-ignore -v docs/ops/deploy.md` → `.gitignore:76:docs/`；工作区无 `docs/` |
| T14 | 无 CD / 镜像仓库 / tag 规范 | P1 | `.github/workflows/` 仅 `ci.yml` |
| T15 | Kimi `kimi_home` 路径绑定 macOS Application Support | P1（Linux CI/生产不可用） | 设计文档本机源盘点 |
| T16 | MySQL 8.0 线 EOL 2026-10 | P1 | `deploy/newapi/README.md` 版本锁定表；根 compose `mysql:8` 未钉补丁 |
| T17 | Dockerfile HEALTHCHECK 写死 `:9111` | P2 | compose healthcheck 从 `AUTO_AGENTS_API__PORT` 拼接；镜像 HEALTHCHECK 硬编码。改端口双写漂移 |
| T18 | `config/scrapy/prod/settings.yml` 为空 | P2 | 仅一行注释。生产爬虫覆盖实际在 `config/prod/settings.yml`（`DOWNLOAD_DELAY: 0.5`） |

---

## 2. Power Market：`CACHE_DIR` / `SOURCES` / CI

设计（尚未实现，诊断按目标态验收）：

- `POWER_MARKET.CACHE_DIR: "storage/power-market-cache"`，git 适配器 clone 到 `CACHE_DIR/<source.name>`。
- CI 用环境变量 `AUTO_AGENTS_POWER_MARKET_SOURCES` = **JSON 数组字符串**，`json.loads` 后**整表替换** yml `SOURCES`（禁止与 Dynaconf list 按下标 merge）。
- `POWER_MARKET.ENABLED` 默认 false；false 或 SOURCES 空 → `scan_plugins` 回退 `LIBRARY_ROOT/plugins`。
- `config/__init__.py` 现为 `merge_enabled=True`（L50）——正是设计 D13 要绕开的坑。

### 2.1 现状缺口

| ID | 缺口 | 说明 |
|----|------|------|
| PM1 | 配置文件不存在 | 无 `config/default/power_market.yml`、无 local overlay。全库 grep `POWER_MARKET` **零命中** |
| PM2 | CI 零覆盖 | [`.github/workflows/ci.yml`](.github/workflows/ci.yml) 无 `AUTO_AGENTS_POWER_MARKET_*`、无 cache 目录准备、无 `file://` 夹具 job |
| PM3 | `storage/` 整目录 gitignore | 根 `.gitignore` L72。`CACHE_DIR` 落此处则 clone **不会进 git**（符合 D1），但 CI runner 必须 `mkdir` + 可写；无 eviction/配额 |
| PM4 | 镜像无 cache 卷 | compose/Dockerfile 未挂 `storage/power-market-cache`；容器内 git sync 写 ephemeral 层，重启丢树 → `resolve_origin_path` 读正文失败 |
| PM5 | git 适配器无凭证/allowlist 闸门 | 设计明确「不实现 updater 门禁」。CI 若允许任意 `https://` uri，是供应链面 |
| PM6 | 本机源与 CI 源分裂 | 操作者用 `local_dir ~/.zcode/local-plugins`；CI/生产必须 `type=git`。没有「同一组 SOURCE.yaml 在两种环境下都绿」的 job |
| PM7 | Kimi 源在 CI 必失败 | `kimi_home` uri 指向 `~/Library/Application Support/kimi-desktop/...`。ubuntu-latest 无此树 |
| PM8 | 公开正文依赖磁盘 | D15：读 SKILL.md 走 `CACHE_DIR/<source.name>` 或 expanduser(uri)。`/health/deep` **不探 CACHE_DIR** → 「API 200 + 详情 500/空正文」盲飞 |
| PM9 | `.env.example` / `config/prod/.env.example` 无 Power Market 键 | 发布时无人知道要注入 `AUTO_AGENTS_POWER_MARKET_SOURCES` |
| PM10 | 指针 `WRITE_POINTERS` 默认 false | 回滚扫描根安全（不写 `plugins/`），但 CI 无指针 round-trip 测试 |

### 2.2 必须进闸门的最小集（给后续实现帽，不是本诊断实现）

1. CI 显式 `POWER_MARKET.ENABLED=false` 回归：现有 `scan_plugins` / `test_b1c` 绿（设计 PR2 验收）。
2. 独立 job：`ENABLED=true` + `AUTO_AGENTS_POWER_MARKET_SOURCES` 指向 **临时 `file://` fixture**（禁止 clone 真实 superpowers），断言 `origin_ref="."` 单插件与 monorepo 两分支。
3. 准备 `CACHE_DIR`（gitignore 的 `storage/` 下），跑完可 `rm -rf`；加磁盘用量断言。
4. **禁止** Dynaconf 把 JSON 数组当 list merge；应用层 `json.loads` 整表替换——单测必须覆盖「yml 有一项 + env 有两项 → 只有 env 两项」。
5. Linux runner **不得**启用 `kimi_home` / `local_dir ~/.zcode`。
6. secrets scan：SOURCE.yaml / 指针禁止 token（设计 Security 表已写）。

---

## 3. new-api sidecar（中转站）

### 3.1 已做对的事

- 独立目录、独立网络、版本锁定 `calciumion/new-api:v0.10.7`，禁止 `:latest`。
- 密钥缺失 fail-fast：`SESSION_SECRET=${SESSION_SECRET:?...}`、生产版 `CRYPTO_SECRET` 同款。本轮无 `.env` 跑 `compose config` 即报 `SESSION_SECRET is required`。
- MySQL/Redis **不发布宿主端口**；健康检查用 env 转义密码，避免明文进 `docker inspect`。
- backend 调度/探针默认全关：[`config/default/newapi.yml`](config/default/newapi.yml) L17–L20。
- 敏感项不落 yml：`ACCESS_TOKEN` / `DB_DSN` / `PROBE_API_KEY` 走 `.env`（根 [`.env.example`](.env.example) L61–L71）。
- AGPLv3 边界已写：仅容器化、不改上游源码。

### 3.2 缺口

| ID | 缺口 | 严重度 |
|----|------|--------|
| N1 | CI `docker-validate` **只** `docker compose config` 根文件，不校验 `deploy/newapi/*.yml` | P1。README §6 要求本地跑，CI 未执法 |
| N2 | 根 backend 与 new-api 网络不通 | P1。容器化 backend 用 `localhost:3000` 打到自己；需 `external: newapi-net` 或统一 overlay |
| N3 | 平台与中转站 **两套 MySQL + 两套 Redis** | P2 运维负担。备份/监控/口令轮换无入库 runbook |
| N4 | `CRYPTO_SECRET` 轮换不可逆 | P1。`.env.example` 已警告；无「导出渠道 → 轮换 → 重建」演练记录 |
| N5 | 初始 `root / 123456` | P1。文档要求改密，无自动化「未改密不得发布端口」闸门 |
| N6 | SQLite 快速版无 Redis → 令牌限流缺席 | 误用于多租户即容量事故。缺「生产禁用 sqlite compose」CI 标签 |
| N7 | 调度器直连 new-api **业务库** 聚合 `logs` | 外部契约。`created_at` 类型需部署后记录；无健康端点暴露「调度器模式=unix/datetime」 |
| N8 | backend 对 new-api 探活未进 `/health/deep` | 中转站挂了，平台 API 仍 200。AI 采集/探针静默失败 |
| N9 | `NEWAPI.ENABLED` 启动失败只 warning 不阻断 | [`backend/app/__init__.py`](backend/app/__init__.py) L141–161。符合「外部依赖不影响主平台」，但 **无告警** = 开关打开却无人知道没跑 |
| N10 | 生产 `config/prod/.env.example` **没有** NEWAPI 段 | 只覆盖 JWT/Webhook/MySQL/Redis/LLM。按 prod 模板部署会漏中转站密钥 |
| N11 | new-api MySQL 8.0 EOL 2026-10 | 与平台 compose `mysql:8`（未钉补丁）一起构成升级窗 |

### 3.3 LiteLLM 旁路（密钥事故）

[`deploy/litellm/config.gen.yaml`](deploy/litellm/config.gen.yaml) 文件头写「含明文 API Key，gitignore 已登记」。本轮核实：

- `git ls-files`：**已跟踪**（HEAD `44e9446 deploy:litellm`）
- `git check-ignore`：exit 1（**未被忽略**）
- 根 `.gitignore` 无 `litellm` / `config.gen.yaml` 规则
- 正文含明文上游 `api_key`（本诊断不粘贴密钥）

这是 **P0 密钥泄漏**（上游 Key 等同于中转站 `CRYPTO_SECRET` 泄露）。SRE 要求：立即轮换文件中出现过的上游 Key、从 git 历史剔除、补 ignore、加 gitleaks/trufflehog 闸门。本波次**不改**该文件（不改 deploy 配置）。

LiteLLM 与 new-api 的职责边界在 README 中未定义：生成配置是否还要进生产？若已废弃，应从部署拓扑删除以免双中转。

---

## 4. Spider workers（智能采集）

### 4.1 运行契约（已实现、未编排）

- 启动：`uv run python run.py spider` / `run_spider.py`；常驻重生 + Redis 心跳 [`run_spider.py`](run_spider.py) L150–191。
- 心跳键 `spider:worker:{id}`，间隔 10s / TTL 30s：[`config/default/settings.yml`](config/default/settings.yml) L43–48。失败 `print` 忽略（L187–188）。
- 反爬：`DOWNLOAD_DELAY` + UA 中间件：[`config/scrapy/default/settings.yml`](config/scrapy/default/settings.yml)；prod 覆盖 delay 0.5、并发 16：[`config/prod/settings.yml`](config/prod/settings.yml)（**不是**空的 `config/scrapy/prod/settings.yml`）。
- 结果不写主库，经 Redis 回 backend 消费者（R 红线 / B2）。
- 市场入站：`skill_harvester` → `spider_results.source=marketplace`，人工闸门。

### 4.2 缺口

| ID | 缺口 | 严重度 |
|----|------|--------|
| S1 | **无 Worker 容器/systemd 单元** | P0。compose 起来的「全栈」采集永远 pending |
| S2 | 心跳失败只 print 忽略 | P1。Redis 抖动时节点页全离线，无告警 |
| S3 | 无 Worker 存活告警 | P1。`/health/deep` 不看心跳。任务 pending 靠人点「节点」页 |
| S4 | `alert_rules.queue_depth` 在任务终态评估中被 skip，改由调度器打 **warning 日志** | P1。[`alert_service.py`](backend/services/alert_service.py) L89–91；[`schedule_service.py`](backend/services/schedule_service.py) L294–302 只 `logger.warning`，不走 NotifyService |
| S5 | 通知渠道默认仅 `log` | [`config/default/notify.yml`](config/default/notify.yml) L12–16。P0 没人接 |
| S6 | 共享日志盘未编排 | README FAQ；多机 Worker 无 NFS/sidecar 方案 |
| S7 | CI 不测 scrapy 包 | `pyproject.toml` `testpaths = ["backend/tests"]`；ruff 仅 `backend platform_core scripts`（ci.yml L52） |
| S8 | Dockerfile 不同步 spider 包依赖 | `uv sync --package auto-agents-backend`；Playwright/Selenium 不在 slim 镜像 |
| S9 | `SPIDER_IDLE_CLOSE_SECONDS: 0` 常驻 | 正确；但无「Worker 进程数 / 并发 / 队列深度」容量面板 |
| S10 | 站点配置含 API Key 占位 | [`config/scrapy/default/sites.yml`](config/scrapy/default/sites.yml) `openweather.api_key: "YOUR_API_KEY_HERE"` — 填真值易入库 |
| S11 | webhook 密钥 Backend↔Scrapy 必须一致 | 有启动期守卫（`create_app._validate_runtime_secrets`）；**Worker 进程无对等 fail-fast**（[`scrapy/extensions/__init__.py`](scrapy/extensions/__init__.py) L40–47 只读配置），配错只表现为回调 401、任务卡 running，靠 `STALE_TASK_HOURS: 6` 兜底 |

采集支柱的 SRE 底线：Worker 是一等公民（镜像、健康、扩缩、日志、告警），不能继续当「另开一个终端」。

---

## 5. 可观测性

技能要求四类：可用性 / 延迟 / 饱和度 / 业务。对照仓库（本轮全库 grep `prometheus`/`grafana`/`opentelemetry`/`otel`：**零命中**）。

### 5.1 已有

| 能力 | 位置 | 局限 |
|------|------|------|
| 浅健康 `/api/v1/health` | [`backend/app/api/v1/health.py`](backend/app/api/v1/health.py) L22–27 | **恒 200**，不查依赖 |
| 深健康 `/api/v1/health/deep` | 同文件 L78–106 | MySQL + Redis；失败 503。**不含** storage、CACHE_DIR、new-api、Worker 心跳、公开 `/public/capabilities` |
| `/db` `/redis` `/storage` | 同文件 | 失败仍 **HTTP 200 + body unhealthy**（注释写明给人工看）。编排必须用 `/deep` |
| v2 包装 | [`backend/app/api/v2/health.py`](backend/app/api/v2/health.py) | 有 `response_time_ms`，是探测耗时不是业务 P95 |
| compose HEALTHCHECK | `docker-compose.yml` L86–94；`Dockerfile` L56–57 | 打 `/deep`（T11 修复浅探测假健康）。镜像侧端口硬编码 |
| watchdog | `scripts/watchdog.sh` | 连续 N 次 deep 失败 → P1 webhook；默认 `WATCHDOG_RESTART=0`；**未接入 compose**。hint 指向缺失 docs |
| 爬虫告警规则 | `alert_rules` + 终态 `evaluate` | 连续失败 / 结果下降 / 超时；queue_depth 不在此路径 |
| 渠道事件 / 探针结果 | newapi 模块 + admin 页 | 产品内看板，不是值班告警 |
| 日志 | loguru 分文件 + request_id | prod 默认 WARNING（[`config/prod/log.yml`](config/prod/log.yml)）；无集中采集 |
| 审计 | `record_audit` | 管理动作留痕；无导出到 SIEM |
| LLM 预算 | Redis 计数 + prod `BUDGET_FAIL_CLOSED` | 无「预算逼近」告警 |

### 5.2 缺失（上线即盲飞）

**可用性**

- 无 5xx 率、无按路由拆分成功率。
- `/deep` 不覆盖：storage 可写、Power Market `CACHE_DIR`、new-api `/api/status`、Worker 心跳、公开 `/public/capabilities` 冒烟。
- 无合成监控（官网商店面 / 登录 / 提交任务）。
- `sdlc.config.yaml` `e2e: null`——生产无持续探针。

**延迟**

- 无 RED/USE 指标，无 P50/P95/P99。
- 无慢查询 / 连接等待拆分（连接池耗尽会表现为超时）。

**饱和度**

- MySQL 池 `pool_size=5, max_overflow=10`（[`platform_core/db.py`](platform_core/db.py) L77–78）**无使用率指标**。
- Redis 无 memory/evicted/connected_clients。
- 队列深度只有调度器 warning 日志。
- `CACHE_DIR` / `logs/` / mysql volume 无磁盘告警（compose 已给 json-file 10m×3，这是容器日志不是业务盘）。
- new-api 渠道额度、LLM `MAX_TOKENS_BUDGET` 无「80% 预警」。

**业务指标（四支柱）**

| 支柱 | 应有业务指标 | 现状 |
|------|----------------|------|
| 采集 | 任务完成率、pending 时长、quality_score 分布、Worker 在线数 | 仅 admin 仪表盘，无告警阈值 |
| SaaS | 登录成功、租户安装成功率、配额 429 数 | 无 |
| 中转站 | 渠道熔断次数、探针 down 数、调度器 tick 成功 | 事件表，无 Pager |
| Power Market | `src_sync` 成功/失败、listed 资产数、公开 5xx、sync `last_error` 龄 | 设计 Observability 节已写，**代码/配置/CI 均无** |

设计已写的可观测（尚未落地）：`source.sync.start\|done` 日志、`power_market_sync_total{source,result}`、`power_market_assets{type,listing_state}`、连续 `src_sync` failed / `last_error`>24h / 公开 5xx 告警。

### 5.3 告警草案（每条必须带 runbook；当前均未接线）

| 告警 | 级 | 阈值 | 先看 | 缓解 | 升级 |
|------|----|------|------|------|------|
| API `/health/deep` 503 持续 2m | P0 | watchdog 已接近（默认 3×10s） | MySQL/Redis 容器；backend 日志尾 | 不先杀 backend（watchdog 注释：依赖挂了杀 API 无益） | 5m 未恢复 → 电话 |
| 无 Worker 心跳 > 2×TTL（60s）且存在 pending 任务 | P0 | 心跳 TTL 30s | `run_spider` 进程；Redis | 拉起 Worker；勿重复入队 | 采集 SLA 破裂 |
| 任务队列深度 > `QUEUE_DEPTH_WARN`(50) 持续 10m | P1 | 已有配置无通知 | 调度器日志；Worker 数 | 扩 Worker / 降并发 | 30m → P0 |
| new-api `/api/status` 失败且 `NEWAPI.ENABLED=true` | P1 | 无探活 | newapi-net；DSN | 关调度/探针开关保主站 | 影响 AI 采集则 P0 |
| `src_sync` 连续失败或 `last_error` 龄 > 24h | P1 | 设计已写 | skill_jobs.detail；CACHE_DIR；git 网络 | `ENABLED=false` 回退扫描 | 商店面空洞 |
| 公开 `/public/capabilities` 5xx > 2% 5m | P1 | 无 | 限流 Redis；resolve_origin_path | 关商店 flag / 切 listed | 数据泄漏类升 P0 |
| JWT/Webhook 占位符启动拒绝 | P0 | 启动期已 fail-fast | `.env` | 不发布 | — |
| 磁盘 `CACHE_DIR` 或 mysql volume > 85% | P1 | 无 | df；clone 体积 | 清 cache 并重 sync（会短时空正文） | 写满 → P0 |
| LLM 月预算 > 80% | P2 | 有熔断无预警 | llm_token_usage | 降级模型 | 100% fail-closed 变 P1 |

Notify 默认只有 log：所有上表在生产都是「写了日志当告警」。必须先定值班渠道（钉钉/邮件已有配置位，均为空）。

**没有处理指引的告警不要上。** 仓库内唯一接近 runbook 的是 watchdog payload 的 `hint` 字段，且指向缺失的 `docs/ops/deploy.md`。

---

## 6. 配置 / 密钥 / 环境漂移

### 6.1 密钥与占位符

| 项 | 状态 | 风险 |
|----|------|------|
| JWT `change-me-in-production` | 导入即抛（[`backend/utils/auth.py`](backend/utils/auth.py) L12–16） | 好 |
| Webhook 同款占位符 | `create_app` 拒绝启动 | 好；Worker 侧无对等守卫 |
| compose 开发密钥 | JWT/Webhook/MySQL/Redis 明文写在 `docker-compose.yml` L81–85 | 文件头声明禁用于生产；**无** compose profile 隔离 prod |
| 初始 admin `123456` | README / `set_admin_account.py` | 与 new-api root/123456 同类 |
| `deploy/litellm/config.gen.yaml` | **跟踪 + 明文 Key** | **P0** |
| `sites.yml` YOUR_API_KEY_HERE | 占位在 default 配置 | 填真值易入库 |
| LLM Fernet 空值放行 | `__init__.py` L47–49：空=不落库加密 | 生产若忘配，带 api_key 的请求会被拒（服务层），不是启动失败 |
| CORS 生产占位域名 | [`config/prod/web.yml`](config/prod/web.yml) `https://your-domain.com` | 按模板发布会把浏览器 CORS 指到不存在的域 |

### 6.2 MySQL 密码键名漂移（配置事故）

三套「正确写法」并存：

| 来源 | 键 | 谁读 |
|------|----|------|
| compose / 根 `.env.example` | `AUTO_AGENTS_MYSQL_DEFAULT_PASSWORD`（扁平） | Dynaconf → `MYSQL_DEFAULT_PASSWORD`；`DBManager._get_password("MYSQL","DEFAULT")` 读这个 |
| README / `config/prod/.env.example` | `AUTO_AGENTS_MYSQL__DEFAULT__PASSWORD`（嵌套） | Dynaconf → `MYSQL.DEFAULT.PASSWORD` |
| bootstrap-db / alembic `env.py` / CI pytest | `MYSQL_DEFAULT_PASSWORD` 裸键 **或** `settings.get('MYSQL_DEFAULT_PASSWORD')` | **不读** `MYSQL.DEFAULT.PASSWORD` |

[`platform_core/db.py`](platform_core/db.py) L40–44 只拼 `MYSQL_DEFAULT_PASSWORD`，**忽略** yml 嵌套 `PASSWORD` 字段（yml 里本来就是 `PASSWORD: ""`）。按 **prod 模板**只填嵌套键时，应用层密码为空，表现为连库失败或误用空密码。这是环境逃逸，不是产品缺陷。

对比：[`config/__init__.py`](config/__init__.py) L63–67 拼 Redis URL 时有三层回退（裸 env → 扁平 settings → `cfg.PASSWORD`）。MySQL **没有**对等回退。根 `.env.example` L4–7 已写「扁平与裸键二选一」，prod 模板仍推嵌套键。

Redis 同构：compose 用扁平 `AUTO_AGENTS_REDIS_DEFAULT_PASSWORD`，prod 模板用 `AUTO_AGENTS_REDIS__DEFAULT__PASSWORD`。

### 6.3 Dynaconf

- `merge_enabled=True`（[`config/__init__.py`](config/__init__.py) L50）对 `POWER_MARKET.SOURCES` 列表是已知陷阱；设计要求 env JSON **整表替换**。
- `.env` **不**做 `${VAR}` 展开（prod 模板 P1-1 已警示；旧模板导致启动即拒——见 pitfalls）。
- `APP_ENV` 决定加载哪层；Dockerfile 缺省 `APP_ENV=prod`，根 compose 强制 `local` + 开发密钥——同一镜像两种人格，tag 规范未写（规范文件还在 gitignore 的 docs 里）。

### 6.4 环境漂移（技能 Gotchas + 本仓实锤）

| 漂移 | 仓库事实 |
|------|----------|
| macOS ARM vs Linux x86_64 镜像 | `b50be93`：本机 ARM64 lockfile 在 Linux `uv sync --frozen` 解析失败，曾改为 `uv export`+pip。随后 `c3a7d4d` 改回「完整源码 COPY + `uv sync`」（**无 `--frozen`**）。跨平台镜像仍只在 CI `ubuntu-latest` 构建 |
| npm 11 vs npm 10 lockfile | `4a54127`：npm 11（Node 25）生成的 per-app lockfile 缺 `yaml@2.9.0`，CI Node 20 npm@10 / Docker `npm ci` 全炸。已用 npm@10 重生 |
| 前端 lockfile 布局 vs Dockerfile | `902de6d`（2026-09-03）根 workspaces + 根 `package-lock.json`；`9d0627b`/`34914ac` **删除** `frontend/{admin,official}/package-lock.json`。`df5db02`（2026-09-05，T11）仍改 Dockerfile，**未改** L10/L16 `COPY .../package-lock.json`。`git ls-files '*package-lock.json'` 仅根文件。按 Docker 语义 Stage1 COPY **必失败**。本波次未跑 `docker build`，不把 CI 状态写成已红 |
| 前端 shared | admin 源码 `import from '@auto-agents/frontend-shared'`，`frontend/admin/package.json` **未声明该依赖**，靠根 workspaces。Dockerfile 只 COPY admin 目录，即便补 lockfile，`npm ci` 也无法解析 shared |
| Python 3.13 | CI `uv python install 3.13` 与 `requires-python` 一致 |
| 无 secrets scanning / Dependabot / CodeQL | `.github/` 仅 `ci.yml` |
| `docs/` gitignore | 运维真源不入库 → 新环境/CI/值班看不到 deploy 与 incident 复盘。T11 提交说明写「部署回滚文档」，diff 只有 5 个非 docs 文件 |

---

## 7. CI / 闸门指纹（宪法对照）

`sdlc.config.yaml` 闸门：

| 闸门 | 宪法命令 | CI 是否跑 | 缺口 |
|------|----------|-----------|------|
| test | `uv run pytest -x -q backend/tests` | 是（另加 MySQL 保真子集 8 文件） | 无 scrapy 测试；无 Power Market git fixture；pytest `APP_ENV=local` |
| lint | `bash scripts/check-arch.sh` | 是；另 ruff 但 **不含 scrapy/** | 前端 F-5/F-6 在 frontend-build job |
| build | 双前端 `npm run build --prefix ...` | 是，且先 shared + codegen（workspaces `-w`） | 与 Dockerfile 前端构建路径不一致 |
| migration | `bash scripts/check-db-migrations.sh` | 是 + `check-db-ir.sh` | **静态**检查；无 `alembic upgrade/downgrade` 往返。`scripts/migrate.sh` 只有 `upgrade head` |
| e2e | `null` | 不跑 | 商店面/登录/任务闭环无持续探针 |

`docker-validate`：`docker compose config`（根，本轮 exit 0）+ `docker build`。未：new-api compose、多 arch、spider 镜像、cache 卷。前端 COPY 路径与 lockfile 布局已分叉（§6.4）。

无 CD：通过 CI ≠ 可发布。无镜像 tag、无预发、无 canary、无「门禁指纹写入 release-checklist」的载体（`docs/` 不在库）。

Power Market / 中转站 **外部契约**（lane_judge Q3）在 CI 里没有契约测试：new-api `/api/status`、git adapter `file://`、公开 capabilities 闸门 SQL。

Alembic head：`027_spider_tasks_status_varchar`（ENUM→VARCHAR 放宽；downgrade 有非法值前置校验）。`024` contract NOT NULL。二者 down 路径都只在迁移注释里，不在 CI。

---

## 8. 回滚

### 8.1 三类回滚：全部未实测

技能铁律：写下来的回滚在要用时经常是错的。本仓库：

| 类型 | 现状 | 实测？ |
|------|------|--------|
| 代码 | 无镜像仓库/tag；compose 无 `image:` 仅 `build:`；回滚命令未文档化于可提交路径 | **否**（本波次未部署、未回滚） |
| 数据 | 迁移有 `downgrade()`；`024` 含 contract（NOT NULL，软删行不恢复）；`027` down 遇非法 status 会显式 raise。CI 不做 up→down→up | **否**（T9/025 口径写在迁移注释里，不是 CI 指纹） |
| 配置 | Dynaconf 层 + `.env`；无配置版本/一键回上一版；`ENABLED` 类开关可用 | 开关级可手搓；**无演练** |

`scripts/migrate.sh` 只有 `upgrade head`，没有 downgrade 封装。

引用的 `docs/ops/deploy.md`（镜像 tag / 迁移顺序 / 回滚步骤 / 验证清单 / 看门狗）**不在仓库**。值班按引用打开 404。

B4 看门狗是本仓**唯一**带「演练实测」字样的运维脚本（bash 3.2 UTF-8 崩溃 + `RESTART=0` 仍 kill）。它修的是探针，不是发布回滚。

### 8.2 四支柱回滚语义

**采集（低风险代码 + 中风险数据）**

- Worker 与 backend 独立进程：可只回滚一边。Webhook 密钥必须两边一致，否则回调伪造/失败。
- Redis 无 volume：重启即「清空队列」，不是回滚，是砍数据。
- 任务 running 靠 `STALE_TASK_HOURS: 6` 回收——回滚窗口以小时计。

**SaaS（高 / 部分不可逆）**

- 租户 NOT NULL（`024`）downgrade 会把平台超管 `tenant_id` 置 NULL；去重软删行**不恢复**（迁移头注释）。
- 无按租户灰度（技能推荐多租户按租户灰度）。`POWER_MARKET.ENABLED` 是全进程开关，不是租户开关。

**中转站（配置 + 密钥不可逆）**

- 镜像 tag 锁定，理论上 `compose pull` 旧 tag 可回。需保证旧 tag 没被 GC。
- `CRYPTO_SECRET` 一换，渠道 Key 全部不可解密 → **密钥回滚窗口在加密发生时关闭**。
- SQLite `./data` 与 MySQL `./mysql-data` 备份未自动化。
- 调度器会**下线渠道**：打开 `SCHEDULER_ENABLED` 不是普通配置回滚。

**Power Market（设计已给配置回滚，数据面不可逆）**

设计 Rollout §7：

> 回滚：`ENABLED=false` → 扫描回退 `LIBRARY_ROOT/plugins`；新列有默认值。指针只写 `pointers/`，从不碰旧扫描根。

这只覆盖 **扫描路径**。覆盖不了：

| 副作用 | 代码回滚后 | 窗口 |
|--------|------------|------|
| `listing_state=listed` 已公开 | 旧代码若无该列/闸门，行为取决于 expand 默认值；商店面语义变了 | 已爬虫/CDN 缓存的公开页不可撤回 |
| `capability_installs` 租户订阅 | 旧代码可能不识表（expand 加表通常可忽略）；用户侧「已安装」预期在 | **已发出的安装关系不可撤回**，需补偿（卸载公告） |
| vanity alias / license override | 数据面 | 冲突 409 后改名不可随便 down |
| `CACHE_DIR` clone | 代码回滚不删盘；或盘被清则正文 404 | 需文档化「保留 cache vs 清空」 |
| enable-host symlink（PR8） | `.grok/plugins` 投影；生产 `HOST_PROJECTION.ENABLED=false` | 本机 symlink 不随 API 回滚 |
| git 历史 SOURCE.yaml | 安全 | — |

expand-contract：设计要求 PR1 **只加列、默认 `unlisted`/`writable=1`**。该步代码回滚安全（旧版忽略新列）。**禁止**把「回填第一方 listed」与「打开公开 REQUIRE_LISTED 商店面」做成不可拆的同一发布——否则回滚代码后商店闸门仍按新列过滤，第一方卡片可能消失或全露出。

### 8.3 建议的发布策略（与风险匹配；未实施）

| 变更 | 风险 | 策略 |
|------|------|------|
| `ENABLED=false` 的 schema expand | 中 | 先迁库，商店面不开；观察迁移与回填 |
| 打开 git 源 CI | 中 | 仅 fixture；再生产 allowlist |
| 打开本机 `zcode_local` sync | 中 | 同步不得 auto-list（D7） |
| 公开商店面 PR6 | 高 | 按租户：内部租户 → 10% → 全量；观察公开 5xx、listing 计数 |
| 租户 installs | 高 | 同商店面；回滚条件含「错误安装数」 |
| new-api ENABLED | 高 | 先探针只读，再调度写渠道状态（调度会下线渠道，**不可当普通配置回滚**） |
| `024` 类 contract DDL | 不可逆 | 备份 + 演练 + 窗口；本特征不在本次四支柱必须 contract 的集合（设计只要 expand） |

放量/回滚判据现在 **无基线**（没有 P95/错误率时间序列）。在接到指标之前，Power Market 只能用 **feature flag + 人工看 admin 源 Tab**，不能假装有 canary。

### 8.4 自检（技能清单）

- [ ] 回滚路径已在真实环境验证？**否**（阻塞把「可回滚」写进发布结论；本波次按指令不改 deploy、不演练）
- [ ] 预发布清单引用闸门指纹？无 release-checklist 载体；本诊断记录 compose config exit 0 与 HEAD `44e9446`
- [ ] 告警有 runbook？**否**（watchdog hint 指向缺失 docs）
- [x] 诊断未引入新的硬编码密钥；并标出仓库内已有问题（不粘贴 litellm 正文）
- [x] 环境漂移已记录（ARM、npm lockfile、Dockerfile vs workspaces、密码键名、APP_ENV、docs gitignore）

---

## 9. 给 spec 的 SRE 约束（非产品 FR / 非 schema）

PM 写 `spec.md` 时请把下列当作 **NFR / 运维验收**，不要当成功能列表：

1. **编排一等公民**：backend、scrapy Worker、admin 静态、official 静态、new-api、平台 MySQL/Redis、CACHE_DIR 卷、watchdog；Worker 与 backend 可独立扩缩。
2. **网络**：backend 访问 new-api 用服务名，禁止容器内 `localhost:3000` 当生产默认。
3. **开关**：`POWER_MARKET.ENABLED`、`NEWAPI.ENABLED`、`HOST_PROJECTION.ENABLED` 默认关；打开必须可在不发版情况下关掉（配置热加载或重启窗口 ≤ 回滚实测时长）。
4. **CI**：`SOURCES` JSON 整表替换测试；`file://` git 两分支夹具；根 + new-api compose `config`；Dockerfile 与 workspaces 同源（根 lockfile + shared 先构建）；secrets scan；scrapy 进 ruff 范围。
5. **深探测扩展**（或独立 `/health/ready`）：storage、CACHE_DIR、可选 new-api、Worker 心跳（readiness 与 liveness 分离：依赖挂了不要让 kube/compose 无限杀 API）。
6. **告警**：§5.3 表至少 P0/P1 接到非 log 渠道，每条 runbook 入库（不要再只写 gitignore 的 `docs/`）。
7. **回滚演练**：expand 迁移 up→down→up 进 CI 或预发；发布前记录耗时。listing/installs 的补偿流程写进 spec「不可撤回副作用」。
8. **密钥**：litellm 生成文件移出 git 并轮换；统一 MySQL/Redis 密码键名（扁平与嵌套只留一条，且与 `DBManager._get_password` 对齐）；prod `.env.example` 补 NEWAPI / POWER_MARKET。
9. **EOL**：new-api 与平台 MySQL 8.0 线在 2026-10 EOL 前给出升级窗。
10. **日志**：多 Worker 必须共享或集中采集 `logs/spider/`，否则任务抽屉验收失败。

拒绝项（本角色不做）：表结构、listing 状态机、适配器算法、前端交互、具体 SQL、本波次 deploy 配置改动。

---

## 10. open_questions

1. 生产目标形态是什么：单机 docker compose、多机 + 共享 Redis、还是 K8s？没有这个选择，T1–T7 无法收口到一份 compose。
2. `docs/ops/deploy.md` 与 incident 复盘的真源是否应改为**入库**路径（例如 `deploy/README.md`）？当前 `docs/` gitignore 让所有「见 docs/ops」引用落空。
3. CI 是否允许出网 clone 真实 git 源，还是 **只允许 `file://` fixture + allowlist host**？（设计倾向 fixture；需 operator 拍板 token/rate limit。）
4. `kimi_home` 是否承诺 Linux/生产索引？若否，spec 应写「仅 operator macOS overlay」，CI 永不开。
5. 平台 Redis 是否要持久化（AOF/卷）？无卷则「回滚/重启」= 丢队列与 new-api 调度状态（`newapi:scheduler:state:*` 在平台 Redis，不在 newapi-redis）。
6. 告警默认接到哪条渠道（钉钉/邮件/webhook）？谁值班？升级电话是谁？
7. new-api 与平台是否必须保持双库，还是接受运维复杂度换隔离？备份 RPO/RTO 分别多少？
8. LiteLLM `config.gen.yaml` 是否仍要部署？若否，删除并轮换已泄漏 Key；若是，它与 new-api 如何分流、密钥如何注入而不入库。
9. 镜像仓库与 tag 策略（git sha / semver / `prod` 浮动）？无 tag 则代码回滚无法陈述。
10. Power Market 商店面灰度维度：按租户、按 `ENABLED`、还是按 `listing_state` 人工闸门？SRE 建议租户灰度，但平台资产 `tenant_id` NULL，公开面是全局的——**全局 listing 没有租户爆炸半径**，需要产品接受「一下架全员看见」。
11. `AUTO_AGENTS_MYSQL__DEFAULT__PASSWORD` vs 扁平键：以哪边为唯一契约？需要一次配置修复（实现帽/ops），否则 prod 模板是陷阱。
12. 本机 ARM 构建的镜像是否要进生产？若要，CI 必须 `buildx` 双平台，不能只信 ubuntu-latest。当前 `uv sync` 无 `--frozen`，可复现性弱于曾用的 export 绕过。

---

## 11. 引用文件（绝对路径）

- `/Users/xuyun/auto_agents/README.md`
- `/Users/xuyun/auto_agents/docker-compose.yml`
- `/Users/xuyun/auto_agents/Dockerfile`
- `/Users/xuyun/auto_agents/.github/workflows/ci.yml`
- `/Users/xuyun/auto_agents/sdlc.config.yaml`
- `/Users/xuyun/auto_agents/.sdlc/feat-four-pillars/state.yaml`
- `/Users/xuyun/auto_agents/.claude/rules/project_rule.md`
- `/Users/xuyun/auto_agents/config/__init__.py`
- `/Users/xuyun/auto_agents/config/default/{settings,newapi,notify,jwt,webhook,skills,storage,log,web,spiders,api,admin}.yml`
- `/Users/xuyun/auto_agents/config/prod/{settings,mysql,redis,web,llm,log}.yml` + `.env.example`
- `/Users/xuyun/auto_agents/config/scrapy/default/{settings,sites}.yml`
- `/Users/xuyun/auto_agents/config/scrapy/prod/settings.yml`
- `/Users/xuyun/auto_agents/deploy/newapi/{README.md,docker-compose.yml,docker-compose.sqlite.yml,.env.example}`
- `/Users/xuyun/auto_agents/deploy/litellm/config.gen.yaml`
- `/Users/xuyun/auto_agents/scripts/{watchdog.sh,migrate.sh,bootstrap-db.sh,check-db-migrations.sh}`
- `/Users/xuyun/auto_agents/backend/app/{__init__.py,api/v1/health.py}`
- `/Users/xuyun/auto_agents/backend/services/{alert_service.py,schedule_service.py}`
- `/Users/xuyun/auto_agents/backend/utils/auth.py`
- `/Users/xuyun/auto_agents/backend/alembic/versions/{024_users_tenant_not_null.py,027_spider_tasks_status_varchar.py}`
- `/Users/xuyun/auto_agents/platform_core/db.py`
- `/Users/xuyun/auto_agents/run.py` / `run_spider.py` / `run_frontend.py`
- `/Users/xuyun/Documents/grok-files/power-market-design.md`（Observability / Rollout / D13 CACHE_DIR SOURCES）
