# Findings — R6-delivery（交付工程：启停、CI、容器、门禁、运维脚本）

## Snapshot
- HEAD: 82259f301c060dbf411424ec8775f29944e313e1（工作区干净）
- slice: `git ls-files -s` over explore_roots(scripts tools .github/workflows deploy) + inputs → sha256 239faaeca030…（49 条），由 manager 计算
- reviewer: sdlc-workflow:reviewer（G-fresh，只读）；packet: ../packets/2026-09-27-1830-review-reviewer-R6-delivery.md
- 方式：静态阅读 + evidence/ 执行记录（命令与退出码在文件内）；reviewer 未执行任何命令、未独立复现；**[未验证]** 条目文末附命令。

**摘要**：21 条（13 major：QA-1..QA-13，其中 QA-5 待验证；8 minor：QA-14..QA-21，其中 QA-20 为疑问；无 blocker）。建议整体优先级：P0（本周，均 S）QA-1 升级、QA-2、QA-7、QA-8、QA-12；P1 QA-3、4、5、9、10、13；P2 其余。

---

## FINDINGS

### QA-1 依赖中有 45 个已知漏洞（10 个包，含鉴权库 PyJWT 与框架层 starlette），CI 无任何依赖安全门禁
- Dimension: 4 | Severity: **major** | 工作量: M
- Evidence：`evidence/pip-audit.txt:2` "Found 45 known vulnerabilities in 10 packages"，exit=1；pyjwt 2.12.1 有 5 个 advisory 需升 2.13.0（行 22-29）；starlette 1.0.0 需升 1.3.1（行 38-47）；python-multipart 0.0.28 需升 0.0.31（行 30-35）；cryptography 48.0.0 需升 50.0.0（行 7-13）；scrapy `PYSEC-2017-83` 无修复版本（行 36）；twisted 需升 26.4.0（行 48）。`pyproject.toml:16` 已把 `pip-audit` 装进 dev，但 `.github/workflows/ci.yml:63-75` 无审计步骤，也无 npm audit、密钥扫描、镜像扫描。`.github/dependabot.yml:3` 用 `package-ecosystem: pip`，而项目用 uv.lock——多个修复版本早已发布却未升级，说明 Dependabot 实际未起作用。
- 后果：鉴权（JWT）、请求解析（multipart）、框架（starlette）带着已公开漏洞上线，新漏洞进来无机制拦截。
- Suggestion：① 一次性升到修复版本：pyjwt≥2.13、fastapi/starlette≥1.3.1、python-multipart≥0.0.31、cryptography≥50、anyio≥4.14.2、pydantic-settings≥2.14.2、pyasn1≥0.6.4、twisted≥26.4、scrapy≥2.17、protego≥0.6.2；② CI 新增 `security` job：`uv run pip-audit --strict`（允许带过期日期的 ignore 清单）+ `npm audit --omit=dev --audit-level=high`；③ dependabot 改 `package-ecosystem: uv` 并补 `docker` 生态。

### QA-2 覆盖率门槛写在配置里，CI 从不执行
- Dimension: 3 | Severity: **major** | 工作量: S
- Evidence：`pyproject.toml:45-51` `fail_under = 70`，注释「CI 实测约 80%」；`ci.yml:75` 实际命令 `uv run pytest -x -q --tb=short backend/tests` 无 `--cov`，门槛永不触发；manager 实跑覆盖率 81%（`evidence/pytest.txt:339`），1954 passed / 41 skipped（行 364）；`pytest.txt:36-58` 有 4 处 "coroutine ... was never awaited"（`test_llm_provider.py:285,502,526`），这些测试断言可能空转。
- 后果：配置注释描述的「防回退」机制不存在，覆盖率可悄悄下降。
- Suggestion：CI 加 `--cov=backend --cov=platform_core --cov-report=term --cov-report=xml`（由 `[tool.coverage.report]` fail_under 生效）并上传 coverage.xml；`[tool.pytest.ini_options]` 加 `filterwarnings = ["error::RuntimeWarning"]` 让「未 await」直接判红。

### QA-3 Ruff 门禁太弱，且 CI 与 pre-commit 检查范围不一致
- Dimension: 1 / 3 | Severity: **major** | 工作量: 阶段一 S / 阶段二 M
- Evidence：`pyproject.toml:63` 只启用 `["E9", "F401"]`；`ci.yml:67` 只查 `backend platform_core scripts`（不含 `scrapy/`、`run.py`、`tools/`、`config/`），`.pre-commit-config.yaml:19-24` 查所有暂存 Python 文件——两边范围不同。扩展扫描（`evidence/ruff-extended.txt`，exit=1）：10 处 **F821 undefined-name**（行 16，可能是运行时 NameError）、6 处 F811（行 18）、2 处 F841（行 27）、10 处 ASYNC240 + 2 处 ASYNC230（行 14、27，async 内阻塞 IO，违反宪法「异步优先」）、20 处 B904（行 12）、`platform_core/models/llm_provider_model.py:48` 一个无效 noqa（行 2）。
- 后果：真实缺陷（未定义名、阻塞事件循环）被「All checks passed」（`evidence/ruff.txt`）掩盖。
- Suggestion：阶段一 select 改 `["E9","F","ASYNC"]`、先修 10 处 F821，CI 与 pre-commit 统一 `ruff check .`（范围交配置决定）；阶段二为 FastAPI `Depends` 忽略 B008，UP 类自动修复（1151 处）单独一个提交。**[未验证]** 具体文件见命令 1。

### QA-4 后端镜像以 root 运行，镜像与 CI 构建不可复现
- Dimension: 4 | Severity: **major** | 工作量: S
- Evidence：`Dockerfile` 全文无 `USER`；`Dockerfile:28` `pip install uv` 未锁版本；`Dockerfile:37` `uv sync --package auto-agents-backend --no-dev` 无 `--locked/--frozen`，`ci.yml:64,121,189` 与 `init_project.sh:43` 的 `uv sync` 同样没加；`Dockerfile:7,26` 基础镜像 `node:20`、`python:3.13-slim` 为浮动标签、无 digest。
- 后果：容器被攻破即得 root；pyproject 改了而 uv.lock 未提交时，CI 与镜像各自重新解析依赖照样通过——锁文件「必须提交、保证可复现」红线实际无人检查。
- Suggestion：`COPY --from=ghcr.io/astral-sh/uv:<固定版本> /uv /uvx /bin/` 安装 uv；所有 `uv sync` 加 `--locked`；新建 uid 10001 用户、chown 运行期目录后 `USER app`；基础镜像钉 digest 由 dependabot docker 生态更新。

### QA-5 [未验证] 容器用 `uv run` 启动，默认会重新同步根项目（含 dev 组），启动时可能需联网装包
- Dimension: 8 / 1 | Severity: **major**（待验证） | 工作量: S
- Evidence：镜像构建只装 backend 且不含 dev（`Dockerfile:37`）；启动命令 `CMD ["uv","run","python","-m","scripts.runlib.backend","--no-reload"]`（`Dockerfile:60`，`docker-compose.yml:72` 同）无 `--no-sync`、未设 `UV_NO_SYNC`；根项目依赖 backend 与 spider 两成员，默认 dev 组含 pytest、ruff、pip-audit、pre-commit 等（`pyproject.toml:7-10,14-23`）。
- 后果（若属实）：生产容器每次启动联网装开发工具；离线/受限网络起不来；可能超过健康检查 30 秒 start-period；运行环境与构建镜像不一致。
- Suggestion：加 `ENV UV_NO_SYNC=1`，或 CMD 改 `["/app/.venv/bin/python","-m","scripts.runlib.backend","--no-reload"]`。验证见命令 2。

### QA-6 Node.js 20 已停止维护（EOL 2026-04-30），镜像/CI/初始化脚本仍锁 Node 20，本地与 CI 版本会漂移
- Dimension: 4 / 8 | Severity: **major** | 工作量: M
- Evidence：`Dockerfile:7` `FROM node:20`，`ci.yml:177` `node-version: 20`，`init_project.sh:33` 提示「请安装 Node.js 20」；但 `init_project.sh:31` macOS 上 `brew install node` 装最新版，与 CI 的 20 不一致。
- 后果：前端构建链拿不到安全补丁；本地与 CI Node 版本不同，可能「本地能过、CI 挂」。
- Suggestion：升 Node 22 或 24 LTS；根加 `.nvmrc`、`package.json` 加 `engines`，CI 用 `node-version-file: .nvmrc`；init 脚本改为校验 Node 主版本而非直接 `brew install node`。

### QA-7 `run.py stop/restart` 会误杀无关进程
- Dimension: 8 | Severity: **major** | 工作量: S
- Evidence：`scripts/runlib/detect.py:61-65` 用 `lsof -ti tcp:<port>`（无 `-sTCP:LISTEN`，会列出该端口上**所有** TCP 连接进程，含客户端）；`process.py:55-58,63,71` 对这些 PID 不做归属校验，先 `killpg`/`kill` SIGTERM、5 秒后 SIGKILL（`process.py:76-84`）；`detect.py:28-39` 读 PID 文件只查存活不核对是否自己启动（PID 复用会当成自家进程）；`detect.py:77-80` 端口被占即判「已运行」，于是 docker compose 里的 backend（`127.0.0.1:9111`）会让 `run.py start backend` 输出「已经启动，跳过」。
- 后果：`run.py stop backend` 可能把连着 9111/9112 的浏览器、admin dev server 代理进程、甚至 Docker Desktop 端口转发进程一并 SIGKILL。
- Suggestion：改 `lsof -nP -iTCP:<port> -sTCP:LISTEN -t`；核对进程归属（命令行含 `svc.module`，或 pgid 等于记录 pid，或记录 pid + 进程创建时间）；端口被非本项目进程占用时只报占用者、拒绝 kill；补单测。**[未验证]** 见命令 3。

### QA-8 发布冒烟脚本探测的是「永远返回 200」的浅健康端点
- Dimension: 3 / 8 | Severity: **major** | 工作量: S
- Evidence：`scripts/smoke.sh:5` 请求 `${BASE}/api/v1/health/` 并 grep `healthy`；该端点无条件返回 `{"status": "healthy"}`（`backend/app/api/v1/health.py:22-27`）；`docker-compose.yml:95-97` 注释自认浅探测「恒 200，依赖挂掉也'健康'」。
- 后果：发布冒烟（G3/S5）无法发现数据库、Redis 故障或 2026-08 那类冻结，冒烟通过没有信息量。
- Suggestion：改探 `/api/v1/health/deep`、判 HTTP 状态码、失败打印响应体；再加一条鉴权读接口检查；CI docker job 加 `docker compose up -d --wait` 后跑 smoke。

### QA-9 冻结事故的兜底手段（watchdog）没有部署到任何地方
- Dimension: 1 / 8 | Severity: **major** | 工作量: M
- Evidence：`docker-compose.yml:14-15` 注释承认「僵死不退出的场景由 watchdog 兜底，restart 只覆盖'进程退出'型故障」；Docker 非 swarm 模式不重启 unhealthy 容器（`docker-compose.yml:65,94-102`）；仓库 grep `watchdog.sh` 只在 `README.md`、`scripts/README.md:14` 与脚本自身出现——无 compose 服务、无 systemd/launchd 单元、无 cron 引用。
- 后果：唯一的部署清单里，2026-08 冻结这类故障仍无任何缓解。
- Suggestion（三选一，见 Q-2）：(a) `deploy/` 下提供 systemd/launchd 单元模板，宿主机跑 watchdog（`WATCHDOG_RESTART_CMD='docker restart <c>'`）；(b) compose 加 autoheal 类 sidecar（挂 docker.sock，有权限风险）；(c) 进程内检测事件循环卡死后 `os._exit`，让 `restart: unless-stopped` 生效。建议先 (a)，长期 (c)。

### QA-10 运维文档引用断链：告警里的「处理指引」指向不存在的文件
- Dimension: 6 | Severity: **major** | 工作量: M
- Evidence：Glob `docs/ops/**` 为空，`docs/**/deploy.md` 与 `incident-2026-08*` 均不存在；但 `docker-compose.yml:9,19,97`、`deploy/watchdog.sh:13,40` 以及 P1 告警 payload 的 `RUNBOOK` 字段（`deploy/watchdog.sh:68`）都把它们当 runbook 引用。
- 后果：值班收到 P1 告警后按指引找不到处理步骤；部署、回滚、迁移顺序无成文依据。
- Suggestion：新建 `docs/ops/` 下 `deploy.md`（镜像 tag、迁移顺序、回滚、验证清单）、`runbook-watchdog.md`、`incident-2026-08-backend-freeze.md`、`backup-restore.md`；CI 加脚本检查 `docs/ops/*.md` 类引用的文件真实存在。

### QA-11 arch.sh 与 db 门禁里有几项「空心」或可绕过，显示 ✓ 但实际未检查
- Dimension: 3 / 7 | Severity: **major** | 工作量: M
- Evidence：
  - **R10 只扫模块顶层函数**：`tools/check/arch.sh:115` `for node in tree.body`；按 Grep 计数 `backend/services` 下 73 个文件共 344 处类/实例方法不在扫描范围，`evidence/arch.txt:13` 「✓ R10」对以类实现的 service 恒为真。
  - **R9 会漏报**：`arch.sh:87` 只 grep `circular|cannot import name`，ModuleNotFoundError、SyntaxError 等其他导入失败判 ✓。
  - **行首锚定可绕过**：R3、B1、B2、B3 正则都以 `^` 开头（`arch.sh:48,225,229,233`），函数内缩进 import 可绕过；测试代码已在这么做并写明原因（`backend/tests/test_spider_generic_spider.py:10,30`、`test_scrapy_store_pipeline.py:4`「避免行首 import scrapy 触发 B2 检查」）；按 grep 非测试代码目前无缩进 import。
  - **DBML lint 空转**：`tools/check/db_ir.sh:21-26` 无 DBML 时静默通过，`evidence/db-gates.txt:2`「无 DBML 文件，跳过」，CI 「DBML IR lint」阶段实际什么也没查。
  - **文档漂移**：`arch.sh:12,36` 写 B1–B4，但 `tools/README.md:7`、`ci.yml:5,105` 仍写 B1–B3；`.pre-commit-config.yaml:1`「对齐 CI 四阶段」而 CI 是五阶段。
- 后果：门禁报告的 ✓ 让人误以为红线已被机械保证，日志、循环依赖、模块边界等规则实际只部分检查。
- Suggestion：R10 同时遍历 `ClassDef` 公开方法，先 warning + 基线文件上线再转阻断；R9 只看 `python -c 'import backend.app'` 退出码；B1–B4 用 import-linter contracts 或 AST 扫描替代 grep（覆盖嵌套 import）；db_ir 二选一——有迁移无 DBML 判红，或 CI 如实标 N/A；统一各文档 B1–B4 与「五阶段」表述。

### QA-12 LiteLLM compose 密钥缺失时静默使用人人可知的默认主密钥、盐与数据库口令
- Dimension: 4 | Severity: **major** | 工作量: S
- Evidence：`deploy/litellm/docker-compose.yml:43` `LITELLM_MASTER_KEY: ${LITELLM_MASTER_KEY:-sk-CHANGE_ME_MASTER}`；`:44` SALT_KEY、`:42,75` `POSTGRES_PASSWORD:-changeme` 同样写法；端口默认绑回环（`:36`）但可被 `LITELLM_BIND` 覆盖，且 litellm-net 上其他容器（按计划 backend 会接入）都能访问网关。
- 后果：`.env` 漏配一个变量，网关即以公开管理员密钥启动，任何人可建虚拟 key、消耗上游额度；SALT_KEY 事后再改，已存模型凭据无法解密。
- Suggestion：改 `${LITELLM_MASTER_KEY:?set in deploy/litellm/.env}` 缺失即报错，SALT_KEY 与 POSTGRES_PASSWORD 同样；`deploy/litellm/README.md` 写明 SALT_KEY 一经设定不可轮换。

### QA-13 备份不可验证、不可恢复、无调度，网关数据库也无备份
- Dimension: 8 / 4 | Severity: **major** | 工作量: M
- Evidence：`scripts/backup-mysql.sh:14` `-p"${MYSQL_PASSWORD}"`（口令出现在 `ps`）；顺序错误——`:16` 先更新 `latest` 软链，`:24` 打印「backup ok」，`:26` 才 `gzip -t` 校验；dump 失败时 `:15` 的重定向已生成残缺文件并留在 daily 目录；无 restore 脚本、无恢复演练、无 cron/compose 引用；LiteLLM Postgres 存虚拟 key 与 spend（`deploy/litellm/docker-compose.yml:24-26,79`），完全无备份。
- 后果：「有备份」停留在纸面，出事时备份可能是坏的或根本不存在。
- Suggestion：口令用 `MYSQL_PWD` 环境变量或 0600 `--defaults-extra-file`；流程改为先写 `.tmp` → `gzip -t` 通过 → `mv` → 最后更新软链，trap 清理残缺文件；新增 `restore-mysql.sh` 并每月往临时库恢复演练；新增 `pg_dump` 备份 LiteLLM 库；`docs/ops/backup-restore.md` 写明调度（cron/launchd）。

### QA-14 后端运行时依赖夹带整套爬虫栈（疑似未使用），爬虫成员自身却无测试、lint 与部署产物
- Dimension: 7 / 1 | Severity: minor | 工作量: M
- Evidence：`backend/pyproject.toml:14,31-33` 声明 drissionpage、scrapy、scrapy-redis、selenium；Grep 显示 backend 非测试代码未 import 这些包，只有 `backend/tests` 在用；`passlib`（`:21`）与 `cachetools`（`:11`）在 backend/platform_core 也未 import；`scrapy/tests` 不存在，scrapy 不在 CI ruff 范围（`ci.yml:67`），无 spider 镜像或 compose 服务。
- 后果：API 镜像平白多出 scrapy、twisted、protego 漏洞面（见 QA-1，scrapy PYSEC-2017-83 无修复版本）且更大；与宪法「独立部署优于耦合 / 部署时 `uv sync --package`」不符。
- Suggestion：爬虫测试迁到 `scrapy/tests` 用 `uv run --package auto-agents-spider pytest scrapy/tests` 跑，从 backend 运行时依赖移除爬虫栈；deptry 确认 passlib、cachetools 是否无用（命令 4）；spider 是否需独立镜像见 Q-3。

### QA-15 CI 耗时重复、权限未收紧
- Dimension: 5 / 4 | Severity: minor | 工作量: S
- Evidence：`ci.yml:228` `--no-cache` 构建镜像会把两个前端再编一遍，与 frontend-build job 重复；镜像里 `COPY` 的 frontend-dist（`Dockerfile:42-44`）写着「供后续 nginx 接入」，目前无人使用；只有第一个 job 开了 uv 缓存（`ci.yml:58`，`:115,:183` 没开）；无 `permissions:` 块；除 frontend-build 外其余 job 无 `timeout-minutes`；actions 未钉 SHA。
- Suggestion：在有静态服务前把前端阶段移出后端镜像，或 buildx + `cache-from/to type=gha`；所有 setup-uv 加 `enable-cache: true`；顶层 `permissions: contents: read`，每 job 设超时。

### QA-16 `.dockerignore` 黑名单式且覆盖不全
- Dimension: 4 | Severity: minor | 工作量: S
- Evidence：`.dockerignore:26-28` 只排除三个 `.env`；未排除 `config/.secrets.yml`（`.gitignore:43` 有对应规则）、`**/.env`、`deploy/litellm/.env`、本地已存在的 `deploy/litellm/config.gen.yaml`（按 `.gitignore:62` 说明含明文 Key），以及 `.scratch`、`.sdlc`、`storage`；`.dockerignore:18` `logs` 只匹配根目录，`COPY backend/ backend/`（`Dockerfile:34`）会把 `backend/logs` 带进镜像。
- 后果：敏感文件进入构建上下文（远程/云构建会被上传）；以后若有人写 `COPY . .` 会直接进镜像。
- Suggestion：改白名单（先 `*`，再逐个 `!backend/`、`!platform_core/` 等放行）+ `**/.env`、`**/*.gen.yaml`、`**/logs`。

### QA-17 `.gitignore` 规则与实际跟踪内容自相矛盾
- Dimension: 7 | Severity: minor | 工作量: S
- Evidence：`.gitignore:65-73` 忽略 `.claude/*`、`.agents/*`、`.github/*`，但 `.github/workflows/ci.yml` 在跟踪快照里，`.agents/` 也是 CLAUDE.md 声明的协作中枢；`:46` 与 `:63` 重复写 `config.gen.yaml`；`:42` 取反 `!config/prod/.env.example` 多余；`:35 files/`、`:76 storage/`、`:9-10 dist/ build/` 无前导 `/`，会匹配任意层级同名目录（目前 `platform_core/storage.py` 是文件不受影响，改成包目录会被静默忽略）。
- 后果：这些目录下新建的文件（如本报告建议的 `security.yml` workflow）不会被 `git add -A` 收进来且无提示。
- Suggestion：只忽略具体生成物（如 `.claude/settings.local.json`）；删重复与多余行；运行期目录加前导 `/`。验证见命令 5。

### QA-18 `run.py start` 每次都写数据库同步 `.agents`，进程日志不轮转
- Dimension: 8 | Severity: minor | 工作量: S
- Evidence：`scripts/runlib/ctl.py:72-76` 不论启动哪个服务（含只启 `frontend` 或 `spider`）都先执行 `sync_agents_hub.py`，对数据库初始化并写入（`scripts/sync_agents_hub.py:25-32`），数据库不可用时要等连接超时；`process.py:19` 追加模式打开 `runtime/run/<svc>.log`，无轮转。
- Suggestion：只在 targets 含 backend 时同步，或改显式 `run.py sync-agents`；日志按大小轮转，或启动时截断并保留一个 `.1`。

### QA-19 `init_project.sh` 在非 local 环境也写弱口令，默认管理员 admin/123456
- Dimension: 4 | Severity: minor | 工作量: S
- Evidence：`init_project.sh:10,57-64` 与 `scripts/lib/common.sh:6`——外部导出 `APP_ENV=prod`/`dev` 时，脚本把 MySQL/Redis 口令 `123456` 写进对应环境 `.env`（本地已存在 `config/prod/.env`，Glob 可见、已 gitignore）；`:137` 固定 admin/123456；`:20` 用 `curl | sh` 装 uv 未锁版本。
- Suggestion：非 local 直接拒绝执行或随机生成口令；首次登录强制改密（需后端切片确认）。

### QA-20 [未验证] 根 compose 声明了无服务使用的 external 网络，可能让新人初始化失败
- Dimension: 8 | Severity: minor（疑问） | 工作量: S
- Evidence：`docker-compose.yml:117-120` 声明 `litellm-net`（external: true）但无服务挂上；注释「若根栈先启动，先执行 docker network create litellm-net」；若 compose 校验该网络存在，`init_project.sh:118` `docker compose up -d mysql redis` 在新机器上会失败。
- Suggestion：backend 真正接入前删掉声明（ADR 留说明）或放进 profile。验证见命令 6。

### QA-21 post-checkout 钩子切换分支时自动合并 main
- Dimension: 7 | Severity: minor | 工作量: S
- Evidence：`tools/git/sync_main.sh:43-63` 切到任何非 main 分支（含 release、hotfix、审阅他人 PR 分支）都执行 `git merge --no-edit origin/main`，悄悄生成本地 merge 提交。
- Suggestion：只对 `feature/*` 生效且只允许 fast-forward；其他情况只 fetch 并提示。

---

## Dimensions checked
1. 标准符合 ⚠️ — 配置与注释声称的能力（覆盖率门槛、watchdog 兜底、`docs/ops` runbook、「独立部署」）与实现不一致（QA-2、9、10、14）。
2. 标准质量 ⚠️ — 无 FR/GWT，判断对象为「门禁定义本身是否可测」：R9、R10、db_ir 与行首锚定的边界检查不能真正证伪（QA-11）。
3. 证据有效性 ⚠️ — `evidence/*` 命令与退出码原样记录（合格）；但「✓ R10」「✓ DBML IR」、smoke 通过、`ruff.txt` All passed 都是空心结论（QA-2、3、8、11）。
4. 安全 ⚠️ — 45 个依赖漏洞（QA-1）、容器 root（QA-4）、Node EOL（QA-6）、LiteLLM 默认密钥（QA-12）、备份口令进 argv（QA-13）、构建上下文（QA-16）、init 弱口令（QA-19）。
5. 性能 ⚠️ — CI 重复构建、缓存不全（QA-15）；运行时查询性能不在本切片 ➖。
6. 契约一致性 ⚠️ — runbook 断链（QA-10）；B1–B3 vs B1–B4、「四阶段」vs「五阶段」漂移（QA-11）；CI 与 pre-commit ruff 范围不一致（QA-3）。
7. 合规 ⚠️ — `evidence/arch.txt` exit=0 机械红线全过；但 R10 只部分覆盖，宪法「独立部署」与 backend 依赖声明相悖（QA-11、14），`.gitignore` 与实际跟踪不一致（QA-17）。
8. 边界 ⚠️ — run.py 误杀（QA-7）、离线启动（QA-5）、备份失败路径（QA-13）、新机器网络（QA-20）。
9. 产品价值与体验 ⚠️ — 本切片「用户」是开发者与运维：新人入口（`init_project.sh` → `run.py`）链路清晰可用；运维体验有缺口——告警指引断链、冒烟无信息量、冻结故障无兜底；截图与 E2E 不适用 ➖。

## Strengths（改进时应保留）
1. Compose 防御性默认值扎实：端口全钉 `127.0.0.1` 并写明理由（`docker-compose.yml:40-43,60-61,74`）；json-file 日志有上限（`:22-27`）；资源限制；健康检查走深探测并用环境变量拼端口避免两处漂移（`:94-102`、`Dockerfile:56-58`）。
2. arch.sh 是可复用机械门禁：退出码 = 违规数，pre-commit 与 CI 共用；R10/R13 Python 段执行失败显式报红不静默通过（`arch.sh:99,185`）；R7 正则专门加固；FR-14 密钥样例由片段拼接并用 `-l` 只打文件名，避免 CI 日志泄密（`arch.sh:272-274`）。
3. 测试与 CI 基础扎实：1954 passed / 41 skipped、覆盖率 81%（`evidence/pytest.txt:339,364`）；真实 MySQL 保真通道（`ci.yml:31-42,77-102`）；concurrency 取消同分支旧 run（`ci.yml:22-24`）；dev 依赖有 pytest-socket 断网防护。
4. watchdog.sh 设计成熟：默认只告警（`:25-29`）、告警冷却（`:182-195`）、先 SIGTERM 排空再 SIGKILL（`:202-221`）、dry-run、兼容 bash 3.2、配置全走环境变量——缺的只是部署（QA-9），无需重写。
5. LiteLLM 独立故障域、镜像版本钉死：精确 tag + 查询日期 + 禁用浮动 tag 清单（`deploy/litellm/docker-compose.yml:14-19,31,70`）；生成配置有 `.gitignore` + CI 双重拦截（`ci.yml:127-144`、`deploy/litellm/.gitignore`）。

## Improvement themes
- **T1 供应链与依赖安全**（QA-1、6、14、QA-4 锁定部分）— 目标：无已知高危漏洞依赖；CI 有 pip-audit + npm audit 两道门禁；dependabot 用 uv 生态；Node 升到维护中 LTS；backend 运行时不含爬虫栈；所有安装 `--locked`。顺序：升级 QA-1 包并跑全量测试 → security job → dependabot 改 uv + docker → 一律 `--locked` → Node 22、前端测试过后合并 → 爬虫依赖与测试迁到 scrapy 成员。
- **T2 门禁去空心化**（QA-2、3、8、11）— 目标：每个 ✓ 背后有真实检查；覆盖率门槛生效；ruff 至少 F + ASYNC；冒烟走深探测；边界检查基于 AST 或 import-linter；文档对门禁描述一致。顺序：覆盖率（S）→ smoke 深探测（S）→ ruff 阶段一 + 修 F821（S）→ R9 看退出码、db_ir 如实标注（S）→ R10 覆盖类方法 + 基线过渡（M）→ import-linter 替代 grep（M）。
- **T3 部署产物生产化**（QA-4、5、12、15、16、20）— 目标：非 root；镜像与工具版本钉死；运行时不做依赖同步；`.dockerignore` 白名单；CI 只构建一次并用缓存、权限最小化；网关密钥缺失即启动失败；compose 不声明未用资源。顺序：LiteLLM 缺失即报错（S，安全收益最高）→ `UV_NO_SYNC` + 非 root（S）→ `.dockerignore` 白名单（S）→ 移除镜像前端阶段 + CI 缓存与 permissions（S）→ 处理 external 网络（S）。
- **T4 运行可恢复性与运维文档**（QA-9、10、13）— 目标：冻结类故障能被自动发现与处置；MySQL 与网关 Postgres 定时备份、校验、演练；`docs/ops/` 有 deploy、runbook、incident、backup-restore 四份并由 CI 检查引用存在。顺序：先补 `docs/ops/`（与用户要求产出目录一致）→ 修备份流程 + restore 脚本 → pg_dump → 按 Q-2 部署 watchdog → 恢复演练并留证据。
- **T5 本地启停与仓库卫生**（QA-7、17、18、19、21）— 目标：run.py 只杀自己启动的进程；启动路径无无关 DB 写入；日志轮转；`.gitignore` 与实际跟踪一致；init 只允许 local；git 钩子不自动产生合并提交。顺序：QA-7（S，风险最高）→ QA-17 → QA-18 → QA-19 → QA-21。

## Return
- Decisions：未替 owner 做决定；报告写法层面的默认——QA-1 定 major 而非 blocker（可利用性未核实）；QA-5、QA-20 验证前按「待验证」处理。
- 待确认问题（operational，附推荐）：**Q-1** 根 Dockerfile 是生产部署产物还是只供开发联调？A 生产化（非 root、去前端阶段、去爬虫栈）；B 只供开发、另建 `Dockerfile.prod`。推荐 A（compose 头部已把生产部署指向这一套）。**Q-2** watchdog 部署形态？(a) 宿主机 systemd/launchd；(b) 挂 docker.sock 的 sidecar；(c) 进程内检测事件循环卡死。推荐先 (a) 长期 (c)。**Q-3** spider 是否要独立镜像与独立 CI job？推荐要（宪法「独立部署」要求，M）。
- Product-delta：无（产品层 N/A）。
- Lessons（已由记录执行或静态证据证实）：`smoke.sh` 探测的 `/api/v1/health/` 无条件返回 healthy（`health.py:22-27`），发布冒烟必须走 `/health/deep`；`db_ir.sh` 无 DBML 时静默 exit 0（`evidence/db-gates.txt:2`），门禁报告的 ✓ 要与「跳过」区分输出。

## 需要 manager 执行的验证命令
1. QA-3：`uv run ruff check --select F821,F811,F841,ASYNC230,ASYNC240 --output-format concise backend platform_core scrapy scripts run.py`
2. QA-5：`docker build -t aa-review . && docker run --rm --network none -e AUTO_AGENTS_JWT__SECRET_KEY=x -e AUTO_AGENTS_WEBHOOK__SECRET_KEY=x aa-review uv run python -c "print('ok')"`（出现 Resolved/Installed 或网络报错即证实）；对照 `docker run --rm --network none aa-review uv run --no-sync python -c "print('ok')"`
3. QA-7：`uv run python run.py start backend admin`，浏览器打开 `http://127.0.0.1:9112`，对比 `lsof -ti tcp:9111` 与 `lsof -nP -iTCP:9111 -sTCP:LISTEN -t`
4. QA-14：`uvx deptry backend`，或 `grep -rnE "passlib|cachetools|selenium|DrissionPage|scrapy_redis" backend platform_core --include=*.py | grep -v /tests/`
5. QA-17：`git check-ignore -v .github/workflows/security.yml .agents/skills/_probe/SKILL.md .claude/rules/new.md`
6. QA-20：无 litellm 栈的机器上 `docker network inspect litellm-net || (docker compose up -d mysql redis; echo exit=$?)`
