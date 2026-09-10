# SRE 诊断 · feat-four-pillars-v2

| 字段 | 值 |
|------|----|
| 角色 | sre（定义帽并行诊断；不实现、不写业务代码、不改 schema、**不改 deploy/compose**、**不写** `06-deliver/checklist.md`） |
| 日期 | 2026-09-08 |
| 复核 HEAD | `5d2e600`（`structure`；相对旧诊断 HEAD `44e9446` 仅 SDLC/能力库结构，**部署面零 diff**） |
| 泳道 | L4（`state.yaml`：schema / 租户 / 外部契约 / 不可逆 / 新依赖 / 多子项目 全 true） |
| 宪法 | `sdlc.config.yaml` → `.claude/rules/project_rule.md`（R1 配置即代码、独立部署优于耦合、爬取与存储分离） |
| 范围 | 运行时拓扑、compose、Worker 是否在编排、密钥/明文、监控/回滚、new-api 旁路；产出运行时风险 + **全新方案交付清单必须吸收的项** |
| 放行 | 本文件不做 QC 放行。回滚路径**未在真实环境实测**。交付帽清单由后续 `/sre` 在 `06-deliver/` 写，本诊断只列必须吸收的字段 |

本轮只读命令指纹（见 §13）：根 `docker compose config --quiet` **exit 0**；`deploy/newapi` 无 `.env` 时 `SESSION_SECRET is required`（fail-fast 有效）；`git ls-files deploy/litellm/config.gen.yaml` **已跟踪**；`git grep -l 'sk-[A-Za-z0-9]{10,}' -- deploy config/default` **仅命中该文件（7 处）**；`POWER_MARKET` 运行时代码 **0 命中**；compose 服务名仅 `mysql redis backend`。未跑 `docker build`、未演练 rollback、未拉 Actions 日志。

输入：`INPUTS.md` 书单（grok-files SRE 诊断 + 旧 SDLC 程序 + 设计 Observability/Rollout）+ 仓库 `docker-compose.yml` / `Dockerfile` / `deploy/` / CI / `config/`。旧工件只作对照，**不复制为现行合同**。

---

## 0. 相对旧程序 / grok-files 的差集（先读）

部署事实与 2026-09-07 grok-files / 旧 `feat-four-pillars` SRE 诊断 **同构**：HEAD 从 `44e9446` → `5d2e600` 未改 compose、Dockerfile、CI、`deploy/`、健康探针、密钥文件。本文件不重抄那 500 行，只钉 **v2 必须改的合同取向**。

| 来源 | 对运行时的处置 | v2 是否可照抄 |
|------|----------------|---------------|
| grok-files `feat-four-pillars-sre-diagnosis.md` + 旧 `diagnosis/sre.md` | 拓扑残缺 / 观测残缺 / 回滚空洞 / litellm P0 / CI 脱节；Worker 是一等公民 | **事实可沿用**（本轮已复验） |
| grok-files `four-pillars-diagnosis-and-plan.md` W0-9 / W4-6 | Wave 0 就把 spider 写进 compose；干净 compose 能跑通一条 generic 任务 | **取向正确**：与「停止说谎」同波，不得再埋 |
| 旧 `contract.md` v2.1 §2 / ADR-0010 | 「sre 诊断的 Worker/前端编排缺口 **不在本程序实现票**」；`/sre` 仅 T-12 密钥离树；W1「CACHE_DIR 观察，**不改 compose**」；「无新进程监控」 | **禁止照抄为 v2 默认**。那是旧波次裁切，不是运行时真理 |
| 旧 spec FR-70/71、Wave 4 stub | Worker 空态 / 第一次出数放到 Wave 4 | 产品空态文案可分波；**编排缺口不得再当「下波再说」**——否则 WACT/TTFV 分母永远是 pending |
| 旧 T-12 | 明文离树 + 掩码，**不**做 git filter-repo | 密钥离树仍是 Wave 0 P0；历史剔除仍须操作者机外拍板（Q 见 §12） |

一句话：旧方案把 SRE 拓扑债记进风险表然后继续卖「采集柱 Wave 0」。v2 若仍这样写，交付清单会再次漏 Worker、漏 CACHE_DIR 卷、漏 new-api 网络、漏实测回滚。

---

## 1. 结论（给 PM / architect 的一页）

当前仓库能撑 **本机双终端联调**（`run.py all` + 另开 `run.py spider` + 根 compose 的 backend/MySQL/Redis），**撑不住**四支柱任何一柱的生产面或「干净 compose 可演示」。

| ID | 问题 | 为什么是运行时（不是产品功能） | v2 必须怎么写进方案 |
|----|------|-------------------------------|----------------------|
| C1 | 拓扑残缺 | 根 compose 只有 backend+MySQL+Redis；Worker / 双前端 HTTP / new-api / CACHE_DIR 卷 / watchdog / 反代都不在编排里 | 编排一等公民；**不得**再写「本程序不改 compose」 |
| C2 | 观测残缺 | `/health/deep` 只探 MySQL+Redis；Notify 默认仅 `log`；无 P95/连接池/队列/Worker 心跳/new-api/CACHE_DIR 对外告警 | 四类指标 + P0/P1 非 log 渠道 + 每条 runbook **入库路径** |
| C3 | 回滚空洞 | `docs/ops/deploy.md` 被引用但 `docs/` gitignore；无镜像 tag/CD/canary；Alembic down 不在 CI | 入库 runbook；expand 迁移 up→down→up；listing/installs 补偿写进不可撤回副作用 |
| C4 | 密钥事故 P0 | `deploy/litellm/config.gen.yaml` git 跟踪 + 明文上游 Key（本轮 7 处 `sk-…`）；头自称 gitignore，根 ignore **未登记** | Wave 0 必做：轮换 + 离树 + ignore + secrets scan。历史 filter 由操作者拍板 |
| C5 | CI 与目标态脱节 | 不校验 new-api compose；不装 Power Market 源；不测 scrapy；Dockerfile 仍 COPY 已删除的 per-app lockfile | Dockerfile 与根 workspaces 同源；new-api `compose config` 进 CI；scrapy 进 ruff |
| C6 | 旧方案裁切债 | 把 C1 推到 Wave 4 / T-12 只修密钥 | v2 交付清单按 §9 吸收；波次可以分，**字段不能丢** |

四柱致命依赖（未变）：

- **采集**：独立 Worker + 共享 Redis + 共享 `logs/spider/`。Worker 不在编排 → 任务永 pending → WACT/TTFV 无法发生。
- **SaaS**：同一 backend；无租户灰度；`024` 类 contract DDL 不可当普通回滚。
- **中转站**：隔离网络是对的；backend 容器默认打不到 sidecar；`SCHEDULER_ENABLED` 会**下线渠道**。
- **Power Market**：`ENABLED` + 可驱逐 `CACHE_DIR` + CI `file://` 源。代码零落地，但设计已写回滚只覆盖扫描路径。

---

## 2. 运行时拓扑（已核实，HEAD `5d2e600`）

```
  CRA 开发服务器（不在 compose）
  admin :9112     official :9113          ← 仅 run_frontend.py
        \              /
      FastAPI backend :9111
      ├ lifespan: 消费者/调度/LLM flush/评分/渠道调度·探针
      │            （任一失败仅 warning，不阻断启动）
      ├ /api/v1/health       恒 200
      ├ /api/v1/health/deep  MySQL SELECT 1 + Redis PING → 失败 503
      └ 镜像内 frontend-dist/{admin,official}  无进程提供 HTTP
              │
              ├── MySQL 8（卷 mysql_data；镜像未钉补丁）
              ├── Redis 7（**无数据卷**）
              └── scrapy Worker（run_spider.py，**compose 无此服务**）
                        心跳 spider:worker:{id} TTL 30s（失败只 print）
                        日志 logs/spider/（需与 backend 同文件系统）

  deploy/newapi/  独立网络 newapi-net，不并入根文件
      new-api :3000 → newapi-mysql / newapi-redis  或 SQLite ./data
      backend 默认 NEWAPI.BASE_URL=http://localhost:3000，ENABLED=false
      根 compose backend **未加入 newapi-net**

  不在任何编排中
      scripts/watchdog.sh（默认只告警不杀；hint 指向缺失 docs）
      POWER_MARKET.CACHE_DIR（yml 不存在）
      ~/.zcode/local-plugins、Kimi daimon（仅操作者 macOS）
      deploy/litellm（生成配置，**已被 git 跟踪**）
```

compose 服务名本轮：`mysql` / `redis` / `backend`。无 `spider`、无 `admin`、无 `official`、无 `watchdog`、无 `new-api`。

`run.py all` 只拉 backend + 双前端，**不含 spider**（`run.py` L9–L14）。README 自己写双进程心智模型（L79）：Worker 不启动则任务一直 pending。

### 2.1 拓扑缺口（沿用旧 ID，本轮仍成立）

| ID | 缺口 | 严重度 | 本轮证据 |
|----|------|--------|----------|
| T1 | compose 无 scrapy Worker | **P0** | `docker compose config --services` → mysql redis backend |
| T2 | compose 无 admin/official HTTP | P0（商店/SaaS 面） | 9112/9113 只在 `run_frontend.py` |
| T3 | 镜像 frontend-dist 无服务者 | P1 | `Dockerfile` L38–40「后续接入」；仓库无 nginx/Caddy |
| T4 | backend 未加入 `newapi-net` | P1 | 根 compose 无 `networks:`；new-api README §5.2 要求服务名 `http://new-api:3000` |
| T5 | 平台 Redis **无 volume** | P1 | 仅 `mysql_data:`。`newapi:scheduler:state:*` 在**平台** Redis，不在 newapi-redis |
| T6 | watchdog 未挂编排 | P1 | `scripts/watchdog.sh`；compose 无 sidecar |
| T7 | 无反代 / TLS / SSE 超时 | P1 | 仅 new-api README 有 Caddy 示例 |
| T8 | Dockerfile 前端构建与 workspaces 分叉 | **P0（`docker build` 保真度）** | Stage1 COPY `frontend/*/package-lock.json`；工作区与 git **均无**这两文件；仅根 `package-lock.json` |
| T9 | 镜像 `uv sync --package auto-agents-backend --no-dev`，却 COPY 了 `scrapy/` | P2 | 无 `--frozen`（P-SRE-02） |
| T10 | Playwright/Chromium 不在镜像 | P2 | `PLAYWRIGHT.ENABLED: false` |
| T11 | `capability-library/` 未进镜像 | P1 | Dockerfile 未 COPY；`SKILLS.LIBRARY_ROOT: capability-library`。HEAD 已加插件 symlink，镜像仍看不见 |
| T12 | 日志跨机 | P1 | README FAQ：backend 与 Worker 需同一 `logs/spider/` |
| T13 | `docs/ops/deploy.md` 缺失 | **P0（runbook 404）** | `git check-ignore -v docs/ops/deploy.md` → `.gitignore:76:docs/`；工作区无 `docs/` |
| T14 | 无 CD / 镜像仓库 / tag | P1 | `.github/workflows/` 仅 `ci.yml` |
| T15 | Kimi `kimi_home` 绑 macOS Application Support | P1 | 设计本机源；ubuntu-latest 无此树 |
| T16 | MySQL 8.0 线 EOL **2026-10** | P1 | 距本诊断约三周；根 `mysql:8` 未钉补丁；new-api `mysql:8.0` |
| T17 | Dockerfile HEALTHCHECK 写死 `:9111` | P2 | compose healthcheck 从 `AUTO_AGENTS_API__PORT` 拼；镜像硬编码 |
| T18 | `config/scrapy/prod/settings.yml` 为空 | P2 | 生产覆盖实际在 `config/prod/settings.yml` |

独立部署优于耦合（宪法）：Worker、new-api、前端静态、backend **应可独立扩缩与回滚**。现状是「一个 backend 镜像假装全栈」。ADR-0010「市场不另起进程」**仍然成立**——那只约束 Power Market 子包，**不**等于 Worker 可以继续当「另开一个终端」。

---

## 3. 运行时风险（按爆炸半径）

| ID | 风险 | 触发 | 爆炸半径 | 发现速度（现状） | 恢复 | 数据会坏？ |
|----|------|------|----------|------------------|------|------------|
| R1 | 采集全 pending | compose/`run.py all` 无 Worker | 柱 A 主路径；WACT/TTFV 分母=0 | 靠人点「节点」页；`/deep` 仍 200 | 拉起 Worker；勿重复入队 | Redis 无卷时重启=砍队列 |
| R2 | 明文上游 Key 在 git | 克隆公开树 / CI 日志 | 等同中转 `CRYPTO_SECRET` 级泄漏；须轮换 | 已存在（跟踪文件） | 轮换 + 离树；历史须 filter | 密钥一旦用过窗口关闭 |
| R3 | 容器化中转站静默断 | backend 用 `localhost:3000` | 调度/探针/AI 采集走中转失败；主站 `/deep` 仍 200 | 无 | 关 `NEWAPI.ENABLED` 保主站 | 调度器曾下线的渠道不会自动当「没发生」 |
| R4 | 商店 API 200 + 正文 404 | `CACHE_DIR` 无卷 / git clone 失败 | 公开详情空；listing 仍在 | `/deep` 不探 CACHE_DIR | `ENABLED=false` 回退扫描；**已 listed 不收回** | clone 树丢失；listed 行仍在 |
| R5 | 配置回滚当数据回滚 | 只关 flag / 回代码 | listing、installs、alias、许可 override 仍在 | 无补偿流程 | 需卸载公告 + 人工 unlist | **不可撤回副作用** |
| R6 | prod 模板密码键读空 | 只填 `AUTO_AGENTS_MYSQL__DEFAULT__PASSWORD` | 应用层 `DBManager._get_password` 读扁平键，嵌套键被忽略 | 启动连库失败或空密码 | 改键名；不是产品 bug | 可能误用空密码 |
| R7 | `docker build` 前端 Stage 必失败 | COPY 已删 lockfile | 镜像管线与 CI `npm ci` 不是同一条 | CI `docker-validate` 会在 build 步红（本轮未跑 build，不写已红） | 改 Dockerfile 与根 lockfile+shared 同源 | 无 |
| R8 | 僵死进程假健康 | 只打 `/health` 或 body 200 | 编排器不重启；2026-08 已炸过（P-SRE-04） | watchdog 未挂 | 不先杀 API（依赖挂了杀无益） | 无 |
| R9 | 打开调度器下线渠道 | `SCHEDULER_ENABLED=true` | 中转渠道被禁 | 产品内事件表，无 Pager | **不是**改回配置就能当没发生 | 渠道状态被写 |
| R10 | `CRYPTO_SECRET` 轮换 | 换密钥重建 | 渠道 Key 全部不可解密 | 无演练 | 先导出渠道再轮换 | 窗口在加密发生时关闭 |
| R11 | SQLite 中转当生产 | 用 `docker-compose.sqlite.yml` | 无 Redis → 令牌限流缺席；`CRYPTO_SECRET` 该文件可空 | 无 CI 标签禁用于 prod | 切 MySQL 版 | 限流失效=配额事故 |
| R12 | 迁移 contract 当可回 | `024` NOT NULL down | 超管 `tenant_id` 置 NULL；软删行不恢复 | CI 无 up→down→up | 备份 + 窗口；四支柱新列应只 expand | **部分不可逆** |
| R13 | 告警写了没人接 | Notify 仅 `log` | 上表 P0/P1 全是日志 | 值班看不到 | 先定渠道再接线 | 无 |
| R14 | 全局 listing 无租户灰度 | 公开面 `tenant_id` NULL | 一下架/一上架全员看见 | 无 canary 基线（无 P95 时间序列） | 只能 flag + 人工源 Tab | 已爬虫/CDN 缓存不可撤回 |

技能三个风险问题（现状答案，阻塞把「可发布」写进方案）：

| 问题 | 答 |
|------|----|
| 出问题多快能发现？ | `/deep` 失败约 3×10s（watchdog 默认，**未挂编排**）。Worker 挂、new-api 挂、CACHE_DIR 挂：**发现时间 = 有人点页面** |
| 出问题多快能回滚？ | **未知**。无 tag、无演练、无入库步骤 |
| 出问题数据会不会坏？ | Redis 重启丢队列；listing/installs/渠道下线/**密钥轮换**会坏或不可撤回 |

---

## 4. Worker 是否在编排：**否**

运行契约已实现、未编排：

- 启动：`uv run python run.py spider` / `run_spider.py`；心跳 `spider:worker:{id}` 间隔 10s / TTL 30s；失败 `print` 忽略。
- 反爬：`DOWNLOAD_DELAY` + UA；prod 覆盖在 `config/prod/settings.yml`（不是空的 `config/scrapy/prod/settings.yml`）。
- 结果经 Redis 回 backend（R3/R4/B2）。禁止把 Worker 并进 backend 进程来「简化 compose」。

| ID | 缺口 | 严重度 |
|----|------|--------|
| S1 | **无 Worker 容器/systemd 单元** | P0。`docker compose up` 的「全栈」采集永远 pending |
| S2 | 心跳失败只 print | P1 |
| S3 | `/health/deep` 不看心跳 | P1 |
| S4 | `queue_depth` 只打调度器 warning，不走 NotifyService | P1 |
| S5 | 通知渠道默认仅 `log` | P0 没人接 |
| S6 | 共享日志盘未编排 | 多机抽屉空 |
| S7 | CI 不测 scrapy；ruff 不含 `scrapy/` | P1 |
| S8 | 镜像不同步 spider 包依赖 | P2 |
| S9 | 无 Worker 数 / 并发 / 队列容量面板 | P2 |
| S10 | `sites.yml` `YOUR_API_KEY_HERE` | 填真值易入库 |
| S11 | Worker 无 Webhook 密钥 fail-fast；配错 → 回调 401、任务卡 running，靠 `STALE_TASK_HOURS: 6` | P1 |

**与旧方案的冲突**：contract 把 S1 记成「Wave 4 / 本波不修编排」。度量蓝图 D3 写 TTFV 诊断用途 =「Worker/配额/LLM 前置（Wave 4）」。若 v2 Wave 0 仍宣称「停止说谎」却不把 Worker 列为联调编排验收，官网/后台会继续让任务停在 pending（README 已承认）。SRE 建议：

- **联调 compose 或 `run.py all` 默认拉起 Worker**（或启动时打印不可忽略的「采集未运行」——产品空态是 designer/frontend；进程缺席是 sre）。
- 生产：Worker 独立镜像或同一镜像不同 `command`，可独立扩缩、独立回滚；与 backend 共享 Redis + 日志卷。
- 不得为了「进 compose」而让 scrapy import backend。

---

## 5. 密钥 / 明文

### 5.1 P0：LiteLLM 生成配置在 git 里

`deploy/litellm/config.gen.yaml`：

- 文件头：「含明文 API Key，gitignore 已登记」
- `git ls-files`：已跟踪
- `git check-ignore`：exit 1（未被忽略）
- 根 `.gitignore` 无 `litellm` / `config.gen.yaml`
- 本轮 `git grep`：该文件 **7** 处长 `sk-` 模式（本诊断不粘贴密钥）

处置（实现帽 / 操作者，本波次不改文件）：立即轮换文件中出现过的上游 Key；从跟踪中移除；补 ignore；加 gitleaks/trufflehog；历史 `git filter-repo` 是否执行 = 开放问题。旧 T-12 把历史剔除推给「机外」——v2 交付清单必须有 **evidence 栏**（轮换时间、ignore diff、scan 退出码），不能再只写「todo」。

LiteLLM 与 new-api 职责：grok-files 诊断计划写「实验旁路、非租户产品」。CONTEXT 中转站 = 外部 new-api。双通道未定义。**不要把 LiteLLM 并进四柱卖点**；要么删除生成物并轮换，要么密钥注入不入库。

### 5.2 已做对的

- JWT / Webhook 占位符启动拒绝（Worker 侧 **无**对等守卫 → S11）。
- new-api `SESSION_SECRET` / 生产 `CRYPTO_SECRET` 缺失 fail-fast（本轮无 `.env` 即插值失败）。
- `ACCESS_TOKEN` / `DB_DSN` / `PROBE_API_KEY` 不落 yml。
- new-api `.gitignore` 已忽略 `.env` / `data/` / `mysql-data/` / `redis-data/`。

### 5.3 密码键名漂移（环境逃逸）

| 来源 | 键 | 谁读 |
|------|----|------|
| compose / 根 `.env.example` | `AUTO_AGENTS_MYSQL_DEFAULT_PASSWORD`（扁平） | `DBManager._get_password` → `MYSQL_DEFAULT_PASSWORD` |
| README / `config/prod/.env.example` | `AUTO_AGENTS_MYSQL__DEFAULT__PASSWORD`（嵌套） | Dynaconf → `MYSQL.DEFAULT.PASSWORD`；**db.py 忽略** |
| bootstrap-db / alembic / CI pytest | 裸 `MYSQL_DEFAULT_PASSWORD` | 不读嵌套 |

Redis 注入有三层回退（`config/__init__.py` L63–67）；MySQL **没有**。按 prod 模板只填嵌套键 → 应用层密码为空。

### 5.4 其它

| 项 | 风险 |
|----|------|
| 根 compose 开发密钥明文 | 文件头禁用于生产；**无** compose profile 隔离 prod |
| 初始 admin `123456`；new-api `root / 123456` | 无「未改密不得发布端口」闸门 |
| SQLite 版 `CRYPTO_SECRET` 可空（`:-`） | 与生产 compose `:?` 不一致，误用于多租户更危险 |
| CORS `https://your-domain.com` | 按 prod 模板发布会指到不存在的域 |
| `config/prod/.env.example` 无 NEWAPI / POWER_MARKET 段 | 按 prod 模板会漏中转与市场源 |
| Dynaconf `merge_enabled=True` | 设计 D13：`AUTO_AGENTS_POWER_MARKET_SOURCES` 必须 `json.loads` **整表替换**，禁止 list 下标 merge |

---

## 6. new-api 旁路（隔离是对的，互通未接）

### 6.1 不要并入根 compose

architect / new-api README / 旧 ADR-0010 在这一点上是对的：独立目录、独立网络 `newapi-net`、镜像钉 `calciumion/new-api:v0.10.7`、禁止 `:latest`、AGPLv3 仅容器化不改上游。v2 **不要**为了「一张 compose 好看」把中转站并进根文件（故障域、密钥、AGPL、双库备份都会糊掉）。

要做的是 **网络契约**：backend 若容器化，`external: newapi-net` + `BASE_URL=http://new-api:3000`。禁止容器内 `localhost:3000` 当生产默认。

### 6.2 缺口（沿用 N 号）

| ID | 缺口 | 严重度 |
|----|------|--------|
| N1 | CI `docker-validate` 只 `compose config` 根文件 | P1。README §6 要求本地跑两份 yml，CI 未执法 |
| N2 | 根 backend 与 new-api 网络不通 | P1 |
| N3 | 两套 MySQL + 两套 Redis | P2 运维负担；无入库备份 runbook |
| N4 | `CRYPTO_SECRET` 轮换不可逆 | P1 |
| N5 | 初始 root/123456 | P1 |
| N6 | SQLite 快速版无 Redis 限流 | 缺「生产禁用」CI 标签 |
| N7 | 调度器直连 new-api 业务库 `logs`；`created_at` 类型需部署后记录 | 外部契约 |
| N8 | new-api 探活未进 `/health/deep` | 中转挂了平台仍 200 |
| N9 | `NEWAPI.ENABLED` 启动失败只 warning | 符合「外部依赖不拖死主站」，但 **无告警** = 开关打开无人知道没跑 |
| N10 | prod `.env.example` 无 NEWAPI 段 | P1 |
| N11 | MySQL 8.0 EOL 2026-10 | 与平台 `mysql:8` 同一升级窗 |

调度器会写渠道状态：打开 `SCHEDULER_ENABLED` 的发布策略必须是「先探针只读，再调度写」——旧 contract 这条 **要吸收**。

---

## 7. 监控与回滚

### 7.1 已有 vs 盲区

有：`/health` 恒 200；`/deep` = MySQL+Redis 503（编排必须用它，P-SRE-04）；`/db` `/redis` `/storage` 失败仍 200；compose HEALTHCHECK 打 `/deep`；watchdog 探 `/deep`（B4 已实测修 bash 3.2 / `RESTART=0` 误杀，P-SRE-05）；爬虫终态 `alert_rules`；loguru + request_id。

无：Prometheus/Grafana/OTel（全库 0 命中）；业务 P95；连接池使用率；Redis memory/evicted；队列对外通知；Worker 心跳告警；CACHE_DIR 可写；new-api `/api/status`；公开 `/public/capabilities` 合成监控；`e2e: null`。

设计已写、代码未接：`source.sync.start|done`、`power_market_sync_total`、`power_market_assets`、`src_sync` 连续失败 / `last_error`>24h / 公开 5xx。

Notify 默认 `CHANNELS: [log]`。没有处理指引的告警不要上。唯一接近 runbook 的是 watchdog `hint`，指向 gitignore 的 `docs/ops/deploy.md`（P-SRE-08）。

### 7.2 告警草案（接线前必须有 runbook；当前均未接）

| 告警 | 级 | 先看 | 缓解 | 升级 |
|------|----|------|------|------|
| `/health/deep` 503 持续 2m | P0 | MySQL/Redis；backend 日志尾 | 不先杀 backend | 5m → 电话 |
| 无 Worker 心跳 > 60s 且有 pending | P0 | `run_spider`；Redis | 拉起 Worker；勿重复入队 | 采集 SLA |
| 队列深度 > `QUEUE_DEPTH_WARN`(50) 持续 10m | P1 | 调度器日志；Worker 数 | 扩 Worker / 降并发 | 30m → P0 |
| `NEWAPI.ENABLED=true` 且 `/api/status` 失败 | P1 | newapi-net；DSN | 关调度/探针保主站 | 影响 AI 采集 → P0 |
| `src_sync` 连续失败或 `last_error`>24h | P1 | skill_jobs；CACHE_DIR；git | `ENABLED=false` | 商店空洞 |
| 公开 capabilities 5xx > 2% 5m | P1 | 限流 Redis；resolve_origin_path | 关商店 flag / 切 listed | 泄漏类 → P0 |
| JWT/Webhook 占位符 | P0 | `.env` | 不发布 | — |
| CACHE_DIR 或 mysql volume > 85% | P1 | df；clone 体积 | 清 cache 并重 sync（短时空正文） | 写满 → P0 |
| LLM 月预算 > 80% | P2 | llm_token_usage | 降级模型 | 100% fail-closed → P1 |

### 7.3 三类回滚：全部未实测

| 类型 | 现状 | 实测？ |
|------|------|--------|
| 代码 | 无镜像仓库/tag；compose 仅 `build:` | **否** |
| 数据 | 迁移有 `downgrade()`；`024` contract；`027` down 遇非法 status raise；`scripts/migrate.sh` 只有 `upgrade head` | **否** |
| 配置 | `ENABLED` 类可手关；无配置版本 | 无演练 |

Power Market 设计 Rollout §7：`ENABLED=false` 只回退 **扫描路径**。覆盖不了 listed 已公开、`capability_installs`、alias/许可、CACHE_DIR 保留 vs 清空、enable-host symlink。expand 加列默认 `unlisted` 代码回滚安全。**禁止**「回填第一方 listed」与「打开 REQUIRE_LISTED 商店面」做成同一发布。

放量判据现在无基线（无 P95 时间序列）。接到指标之前只能 **feature flag + 人工源 Tab**，不能假装有 canary。公开面是全局 listing，没有租户爆炸半径。

---

## 8. CI / Dockerfile / 闸门

`sdlc.config.yaml`：test = `uv run pytest -x -q backend/tests`；lint = `check-arch.sh`；build = 双前端 npm；migration = `check-db-migrations.sh`；e2e = null。

| 闸门 | CI | 缺口 |
|------|-----|------|
| test | 是（另 MySQL 保真 8 文件） | 无 scrapy；无 Power Market `file://` fixture；`APP_ENV=local` |
| lint | 是；ruff **不含 scrapy/** | |
| build | 是，根 workspaces + shared 先构建 | 与 Dockerfile 前端 Stage **不是同一条管线** |
| migration | 静态 IR + strong_migrations | 无 alembic up→down→up |
| docker-validate | 根 `compose config` + `docker build` | 不跑 `deploy/newapi/*.yml`；不 buildx 双平台 |
| secrets | 无 | litellm 已在树上仍能过 CI |

Dockerfile 前端：`frontend/admin/package.json` **未声明** `@auto-agents/frontend-shared`，靠根 workspaces。只 COPY admin 目录即使有 lockfile 也解析不了 shared（P-SRE-03）。

Power Market / 中转站外部契约（lane Q3）在 CI 无契约测试。

---

## 9. 全新方案交付清单必须吸收的项

> 本角色 **不写** `.sdlc/feat-four-pillars-v2/06-deliver/checklist.md`（交付帽）。下列是诊断约束：后续 `spec` / `contract` / 票 / `06-deliver/checklist.md` **缺任一条 = 清单不合格**。映射技能 `templates/release-checklist.md` 的节。

### 9.1 变更概要与三个风险问题（清单 §1）

| CL | 必须吸收 | 验收 |
|----|----------|------|
| CL-01 | 风险分级按波：密钥离树=高；schema expand=中；公开商店/installs=高；`SCHEDULER_ENABLED`=高；contract DDL=不可逆 | 不得把四柱写成一张「低风险」发布 |
| CL-02 | 书面回答：发现速度 / 回滚耗时（**实测秒数**）/ 数据会不会坏 | 现答案是「未知 / 未测 / 会」→ 未测不得写可发布 |
| CL-03 | 不可撤回副作用表：listed 公开页、installs、渠道下线、CRYPTO 轮换、CACHE_DIR 清空 | 旧设计「ENABLED=false」不得冒充全量回滚 |

### 9.2 门禁指纹（清单 §2）

| CL | 必须吸收 | 验收 |
|----|----------|------|
| CL-04 | 引用 `sdlc.config.yaml` 四闸命令的 **exit code + commit** | 不接受「应该绿」 |
| CL-05 | 额外闸：`docker compose -f deploy/newapi/docker-compose.yml config`（需 fixture `.env` 或文档化的 dummy secrets job） | 旧 CI 只跑根文件 |
| CL-06 | secrets scan：`git grep -E 'sk-[A-Za-z0-9]{10,}' -- deploy config/default` 跟踪文件 0 真 Key | 本轮 7 命中 → Wave 0 未完成 |
| CL-07 | Dockerfile 前端与 CI 同源：根 `package-lock.json` + shared 先 build；禁止 COPY 不存在的 per-app lockfile | T8 |
| CL-08 | Power Market：`ENABLED=false` 回归绿；独立 job `ENABLED=true` + `AUTO_AGENTS_POWER_MARKET_SOURCES` **JSON 整表替换** + 临时 `file://` 两分支夹具；Linux runner **不得**开 `kimi_home` / `~/.zcode` | 设计 D13/D16 |
| CL-09 | scrapy 进 ruff（至少） | S7 |
| CL-10 | e2e 仍 null 时：verify 帽 curl 路径必须覆盖 登录、提交任务、**Worker 心跳存在**、公开 capabilities（商店面打开后） | 不得用单测代替 |

### 9.3 编排与发布步骤（清单 §8）

| CL | 必须吸收 | 验收 |
|----|----------|------|
| CL-11 | 运行单元清单：backend、**scrapy Worker**、admin 静态、official 静态、平台 MySQL/Redis、CACHE_DIR 卷、watchdog；new-api **独立 compose** | Worker 出现在步骤里，不是 README FAQ |
| CL-12 | 联调：`docker compose up` 或 `run.py all` 能证明采集不是永 pending（拉起 Worker **或** 产品空态拦截，二者必居其一，写入步骤） | 旧方案「本波不修编排」作废 |
| CL-13 | backend→new-api：服务名 URL；禁止容器 `localhost:3000` 当生产默认 | T4/N2 |
| CL-14 | 平台 Redis 持久化决策（卷/AOF 或显式接受「重启=丢队列」）写进步骤与回滚窗口 | T5 |
| CL-15 | 共享 `logs/spider/` 或集中采集，否则任务抽屉验收失败 | T12 |
| CL-16 | 镜像 tag 规范（git sha，禁止只 `prod` 浮动）；compose 生产用 `image:` 可回滚 | 无 tag 则代码回滚无法陈述 |
| CL-17 | `POWER_MARKET.ENABLED` / `NEWAPI.ENABLED` / `HOST_PROJECTION.ENABLED` / `SCHEDULER_ENABLED` / `PROBE_ENABLED` 默认关；打开是独立步骤，可在不发版情况下关掉 | N9/R9 |
| CL-18 | 迁移：先 expand；`scripts/migrate.sh` 对等 downgrade 封装或文档化命令；发布前记录耗时 | 现脚本只有 upgrade |

### 9.4 回滚（清单 §4，必须实测）

| CL | 必须吸收 | 验收 |
|----|----------|------|
| CL-19 | 代码回滚：旧 tag → `/health/deep` 200 → 一笔真实业务请求 | 未测不得勾 |
| CL-20 | 数据：目标 expand 迁移 CI 或预发 up→down→up；`024`/`027` 类 **不**当本程序必做 contract | 设计只要 expand |
| CL-21 | 配置：flag 关闭步骤 + 耗时上限 ≤ 回滚实测时长 | |
| CL-22 | 补偿：错误 installs 卸载公告；listed 误公开的 unlist + CDN/爬虫缓存声明 | R5 |
| CL-23 | CACHE_DIR：「保留 cache vs 清空」二选一写死；清空=短时空正文 | |
| CL-24 | new-api：先探针只读，再调度；回滚调度 **不能**假设渠道状态自动恢复 | R9 |
| CL-25 | 密钥轮换：导出渠道 → 轮换 CRYPTO → 重建；LiteLLM 已泄漏 Key 的轮换 evidence | R2/R10 |

### 9.5 监控接线（清单 §5）

| CL | 必须吸收 | 验收 |
|----|----------|------|
| CL-26 | 可用性：`/deep`；Worker 心跳；可选 new-api status；CACHE_DIR 可写；公开 capabilities 合成 | 现 `/deep` 不够 |
| CL-27 | 延迟：至少商店列表与任务列表用户可感上限（NFR-01）；P95 仪器可后补但清单要写「用什么代替」 | 无基线则无 canary |
| CL-28 | 饱和度：队列深度、MySQL 池、Redis 内存、CACHE_DIR 磁盘 | |
| CL-29 | **业务**：WACT 依赖的 `task_completed`（排除候选）；`market_subscribe_succeeded`；`quota_exceeded`；`src_sync` 成败。审计日志不得冒充漏斗分母 | 蓝图 NFR-08 |
| CL-30 | §7.2 P0/P1 接到 **非 log** 渠道；每条 runbook 在 **可提交路径**（`deploy/` 或非 gitignore 的 ops），禁止再写 `docs/` | P-SRE-08 |
| CL-31 | liveness vs readiness 分离：依赖挂了不要让编排无限杀 API（watchdog 默认 `RESTART=0` 保留） | P-SRE-04/05 |

### 9.6 灰度（清单 §6）

| CL | 必须吸收 | 验收 |
|----|----------|------|
| CL-32 | 商店面：内部 → 观察公开 5xx 与 listing 计数 → 全量。承认 **全局 listing 无租户爆炸半径** | 产品须接受「一下架全员看见」 |
| CL-33 | 回滚条件预先写死（5xx、listing 计数异常、错误安装数），不临场讨论 | 无 P95 基线时用 flag+人工，不假装 canary |
| CL-34 | 禁止同一发布同时：回填第一方 listed **且** 打开公开 REQUIRE_LISTED | 设计 Rollout |

### 9.7 密钥与配置（贯穿清单）

| CL | 必须吸收 | 验收 |
|----|----------|------|
| CL-35 | litellm 生成文件不在跟踪树；ignore 真生效（`git check-ignore` exit 0） | 本轮 exit 1 |
| CL-36 | MySQL/Redis 密码键名只留一条，且与 `DBManager._get_password` 对齐；prod `.env.example` 补 NEWAPI / POWER_MARKET | R6 |
| CL-37 | 根 compose 开发密钥不得当生产；prod profile 或独立 overlay | |
| CL-38 | new-api 未改密不得发布 3000 到 0.0.0.0 | N5 |
| CL-39 | SQLite compose 打「非生产」标签；CI 或清单显式禁用 | N6 |
| CL-40 | SOURCE.yaml / 指针禁止 token | 设计 Security |

### 9.8 容量 / EOL / 漂移（清单 §7）

| CL | 必须吸收 | 验收 |
|----|----------|------|
| CL-41 | Worker 数相对 `QUEUE_DEPTH_WARN` 与并发 16 的余量；池 `5+10` 无指标则先接指标再扩 | |
| CL-42 | MySQL 8.0 EOL 2026-10 升级窗（平台 + new-api）写进窗口表 | T16，距今约三周 |
| CL-43 | 跨平台：生产镜像在 CI linux/amd64 构建；本机 ARM 不进生产除非 `buildx` | P-SRE-02 |
| CL-44 | lockfile 只用 npm@10 生成（CI Node 20） | P-SRE-01 |
| CL-45 | runbook 真源入库（建议 `deploy/README.md`），所有「见 docs/ops」引用改掉 | T13 |

旧 T-12（FR-14）仍有效，但是 **CL 的子集**：只做离树不够覆盖 Worker/回滚/CACHE_DIR。

---

## 10. 给 v2 spec / contract 的 SRE 约束（非 FR、非 schema）

1. 编排一等公民（CL-11）。市场仍落在同一 FastAPI 单体（ADR-0010 拓扑结论可保留），**不要**用它否决 Worker 进程。
2. new-api 保持旁路隔离；修的是网络与探活，不是合并 compose。
3. 开关默认关；打开可在不发版时关掉。
4. 深探测扩展或独立 `/health/ready`：storage、CACHE_DIR、可选 new-api、Worker 心跳；liveness 不因依赖挂而杀 API。
5. listing/installs 补偿写进 spec「不可撤回副作用」，不要只写 D16 扫描回退。
6. 密钥：FR-14 继续；加上键名唯一契约与 prod 模板补段。
7. 日志：多 Worker 共享或集中采集。
8. 拒绝项（本角色不做）：表结构、listing 状态机、适配器算法、前端交互、具体 SQL、本波次改 deploy 文件、本波次写 `06-deliver/checklist.md`。

---

## 11. 旧方案不得照抄的决策（给 architect）

| 旧句 | 出处 | v2 |
|------|------|-----|
| Worker/前端编排缺口不在本程序实现票 | `contract.md` v2.1 §2 | 记入实现范围或显式「联调编排票」；不得只记风险 |
| `/sre` 有限：W0=T-12，W1=观察 CACHE_DIR，不改 compose | 同文件角色表 | W0 至少 CL-06/35/12；W1 至少 CACHE_DIR 卷 + CI fixture |
| `/sre` 无新进程监控 | ADR-0010 | 市场无新进程；Worker **已是**进程，要监控 |
| 本波不修编排；官网不得假装正在爬 | contract 风险表 | 后半句留；前半句与 Wave 0「停止说谎」冲突时以编排/空态二选一验收 |
| `docs/ops/deploy.md` 作为发布真源 | compose/watchdog 引用 | 路径 gitignore，等于没有 |

可保留：不拆市场微服务；new-api 不并入根 compose；Power Market 默认 `ENABLED=false`；调度先只读再写；AGPL 仅容器化。

---

## 12. open_questions（本帽仍未决，不代选）

1. 生产目标形态：单机 compose、多机+共享 Redis、还是 K8s？无此选择 T1–T7 收不到一份编排。
2. runbook 真源是否改为入库 `deploy/README.md`？（SRE 建议是）
3. CI 是否允许出网 clone 真实 git，还是 **只允许 `file://` + allowlist host**？（设计倾向 fixture）
4. `kimi_home` 是否承诺 Linux/生产索引？若否，spec 写「仅 operator macOS overlay」，CI 永不开。
5. 平台 Redis 是否持久化？无卷则重启=丢队列 + 调度状态。
6. 告警默认接到哪条渠道？谁值班？升级电话是谁？（无答案则 CL-30 无法接线）
7. 双库备份 RPO/RTO？是否接受两套 MySQL/Redis 换隔离？
8. LiteLLM 是否仍要部署？若否：删除并轮换已泄漏 Key；若是：与 new-api 如何分流、密钥如何注入而不入库。
9. 镜像 tag 策略（sha / semver / 浮动 `prod`）？
10. 商店面灰度：按租户 / `ENABLED` / 人工 listing？公开面全局，无租户爆炸半径。
11. 密码键扁平 vs 嵌套：以哪边为唯一契约？
12. 本机 ARM 镜像是否进生产？若要，CI 必须 `buildx`。
13. git 历史是否 filter-repo 剔除 litellm 明文？（T-12 留给机外；清单要 evidence）
14. Wave 0 的「Worker 在编排」是改 compose、改 `run.py all`、还是只做产品空态？SRE 要求三者至少落地 **进程或硬拦截** 之一，不能只改文案。

操作者七问（Q-VOICE/PRICE/RELAY/MARKET-USER/BILL/LLM/AGPL）本帽不代选；Q-LLM 影响 LiteLLM vs new-api 分流（Q8）。

---

## 13. 本轮命令指纹

```
$ git rev-parse --short HEAD
5d2e600

$ docker compose -f docker-compose.yml config --quiet
exit: 0
$ docker compose -f docker-compose.yml config --services
mysql
redis
backend

$ docker compose -f deploy/newapi/docker-compose.yml --env-file /dev/null config --quiet
error while interpolating ... SESSION_SECRET is required
（fail-fast 有效；无 dummy env 故非 0，属预期）

$ git ls-files deploy/litellm/config.gen.yaml
deploy/litellm/config.gen.yaml
$ git check-ignore -v deploy/litellm/config.gen.yaml
exit: 1
$ git grep -l -E 'sk-[A-Za-z0-9]{10,}' -- deploy config/default
deploy/litellm/config.gen.yaml     # 7 处；不粘贴正文

$ git check-ignore -v docs/ops/deploy.md
.gitignore:76:docs/    docs/ops/deploy.md

$ git ls-files '*package-lock.json'
package-lock.json

$ rg POWER_MARKET --glob '!.sdlc/**' --glob '!.venv/**' --glob '!node_modules/**'
（无命中）
```

未跑：`docker build`、alembic up/down、watchdog 真失败轮、任何生产/预发回滚。

---

## 14. 自检（技能）

- [ ] 回滚路径已在真实环境验证？**否**（阻塞「可回滚」发布结论；本波次按指令不改 deploy、不演练）
- [ ] 预发布清单引用闸门指纹？本诊断记录 compose config exit 0 与 HEAD `5d2e600`；**正式清单留给交付帽**
- [ ] 告警有 runbook？**否**（hint 指向缺失 docs）
- [x] 未引入新的硬编码密钥；标出仓库已有问题（不粘贴 litellm 正文）
- [x] 环境漂移已记录（ARM、npm lockfile、Dockerfile vs workspaces、密码键名、APP_ENV、docs gitignore、MySQL EOL）
- [x] 未改 deploy/compose；未写 `06-deliver/checklist.md`
- [x] 未把旧 contract「不改 compose」复制为 v2 现行合同

---

## 15. 引用（绝对路径）

- `/Users/xuyun/Documents/grok-files/feat-four-pillars-sre-diagnosis.md`
- `/Users/xuyun/Documents/grok-files/four-pillars-diagnosis-and-plan.md`（§3.8 SRE、W0-9、W4-6）
- `/Users/xuyun/Documents/grok-files/four-pillars-plan.md`（= 旧 contract v2.1）
- `/Users/xuyun/Documents/grok-files/power-market-design.md`（Observability / Rollout / D13 / D16）
- `/Users/xuyun/Documents/grok-files/feat-four-pillars-spec.md` / `feat-four-pillars-metrics.md`
- `/Users/xuyun/auto_agents/.sdlc/feat-four-pillars/01-define/diagnosis/sre.md`
- `/Users/xuyun/auto_agents/.sdlc/feat-four-pillars/02-shape/contract.md`
- `/Users/xuyun/auto_agents/.sdlc/feat-four-pillars/02-shape/adr-0010-four-pillar-topology.md`
- `/Users/xuyun/auto_agents/.sdlc/feat-four-pillars/02-shape/tickets/T-12.md`
- `/Users/xuyun/auto_agents/docker-compose.yml`
- `/Users/xuyun/auto_agents/Dockerfile`
- `/Users/xuyun/auto_agents/.github/workflows/ci.yml`
- `/Users/xuyun/auto_agents/deploy/newapi/{README.md,docker-compose.yml,docker-compose.sqlite.yml,.env.example}`
- `/Users/xuyun/auto_agents/deploy/litellm/config.gen.yaml`
- `/Users/xuyun/auto_agents/config/__init__.py`
- `/Users/xuyun/auto_agents/config/default/{newapi,notify,settings}.yml`
- `/Users/xuyun/auto_agents/config/prod/.env.example`
- `/Users/xuyun/auto_agents/backend/app/api/v1/health.py`
- `/Users/xuyun/auto_agents/platform_core/db.py`
- `/Users/xuyun/auto_agents/scripts/{watchdog.sh,migrate.sh}`
- `/Users/xuyun/auto_agents/run.py` / `run_spider.py`
- `/Users/xuyun/auto_agents/CONTEXT.md`
- `/Users/xuyun/.zcode/local-plugins/sdlc-workflow/skills/sre/references/auto-agents-pitfalls.md`
