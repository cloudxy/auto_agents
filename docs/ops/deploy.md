# 部署 / 回滚手册（backend + 基础设施）

> 维护：SRE ｜ 首版：2026-09-05（工单 T11）
> 关联：`scripts/watchdog.sh`、`docs/ops/incident-2026-08-backend-freeze.md`、`scripts/check-db-migrations.sh`
> 本文档为发布时的一致性基准：**每次发布前核对本文与实际配置是否漂移。**

## 1. 镜像 tag 规范

| tag | 含义 | 谁打 | 用途 |
|---|---|---|---|
| `git-<短sha>`（如 `auto-agents-backend:git-9f3a2b1`） | 构建可追溯：精确对应一个 commit | 每次构建必打（CI 或手动） | 部署与回滚的唯一凭证 |
| `v<语义版本>`（如 `v1.4.0`） | 人工晋升的发布版本（semver：破坏性.功能.修复） | 发布责任人手动 | 对外沟通、变更记录 |
| `latest` | — | — | **禁止用于部署**（不可追溯、不可回滚） |

规则：

1. **部署必须引用不可变 tag**（`git-<sha>` 或 `vX.Y.Z`），禁止 `latest`、禁止
   裸 `image: auto-agents-backend`。
2. 构建命令（在仓库根）：

   ```bash
   SHA=$(git rev-parse --short HEAD)
   docker build -t auto-agents-backend:git-$SHA .
   # 晋升时：
   docker tag auto-agents-backend:git-$SHA auto-agents-backend:v1.4.0
   ```

3. 保留策略：至少保留「当前版本 + 上一版本」两个 `git-<sha>` tag，
   回滚依赖旧 tag 仍存在于镜像仓库/本机。
4. 镜像缺省 `APP_ENV=prod`、`AUTO_AGENTS_API__HOST=0.0.0.0`（见 Dockerfile 注释）；
   部署时 APP_ENV 必须**显式**传入并记录在变更单，不允许"吃缺省"。

## 2. 部署步骤（compose 场景）

前置：门禁全绿（`uv run pytest -x -q backend/tests`、`bash scripts/check-arch.sh`、
`bash scripts/check-db-migrations.sh` 均退出码 0）；镜像已按 §1 打 tag。

```bash
# 0) 记录现状（回滚凭证）
docker compose ps
(cd backend && APP_ENV=prod ../.venv/bin/alembic -c alembic.ini current)
# 记下：当前镜像 tag、alembic 版本号、发布时间

# 1) 迁移先行（expand-only 迁移才允许此顺序；破坏性变更必须走 expand-contract 三步）
#    迁移破坏性检测门禁：bash scripts/check-db-migrations.sh（ADR-0002）
APP_ENV=prod bash scripts/migrate.sh

# 2) 起新版本（compose 场景用 override 把镜像切到不可变 tag，见下方注意 3）
docker compose -f docker-compose.yml -f compose.image.yml up -d backend

# 3) 按 §5 验证清单逐项验证，全过才算发布完成
```

注意：

- 迁移先于切流量的前提是**迁移是 expand-only**（只加不删不改约束）；
  含 remove/drop/改 NULL 约束的迁移必须拆三步（expand → 迁移流量 → contract）。
- `depends_on: condition: service_healthy` 保证 backend 不在 MySQL/Redis
  就绪前启动；backend 自身 healthcheck 为深探测（见 §5）。
- **镜像 override 必须同时重置 build**（B4 在 compose config 层实测发现：
  仅写 `image:` 时 `build:` 仍并存，任何 `up --build` / `compose build` 都会
  以同名 tag 重新构建 → `git-<sha>` 回滚凭证被覆盖，回滚到的其实是新代码）。
  `compose.image.yml`（部署/回滚时随变更单维护，不入库）：

  ```yaml
  services:
    backend:
      image: auto-agents-backend:git-<sha>   # 部署/回滚只改这一行
      build: !reset null                     # 关键：消除 build，保住 tag 不可变
      ports: !override                       # 仅当宿主端口冲突时需要
        - "<宿主端口>:9111"
  ```

## 3. 回滚步骤

> SRE 纪律：**回滚路径必须演练过，而非写过。** 本节为操作基准；每次发布前
> 若引入了 schema 变更，必须在演练环境实际执行一次 §3.1 + §3.2 并记录耗时。

### 3.1 代码/镜像回滚（快，先做——先止损再查因）

```bash
# 1) 切回上一个已知良好 tag（§1 保留策略保证它还在）
#    改 compose.image.yml 的 image 行 → auto-agents-backend:git-<旧sha>（build 保持 !reset）
docker compose -f docker-compose.yml -f compose.image.yml up -d backend

# 2) 验证（§5 清单）：health 深探测 200 + 冒烟 + 日志无新异常
# 3) 禁止在本机执行 compose build / up --build（同名 tag 会被覆盖，
#    回滚凭证失效——见 §2 注意 3）
```

预期耗时：分钟级（拉镜像 + 重启 + 深探测恢复）。
> 本节 compose config 层已验证（override 合并语义、build 重置，见工单 B4）；
> 容器级实测（build → tag → 起服务 → 切换 → 验证）因本机无 docker daemon 未做，
> 首次部署环境就绪后必须补一轮并回填实测耗时（§6）。

### 3.2 数据回滚（慢且危险，仅在旧代码无法读新数据时做）

```bash
# 回退一个迁移版本
cd backend && APP_ENV=prod ../.venv/bin/alembic -c alembic.ini downgrade -1
```

注意事项（**全部读过再动手**）：

1. **down 可靠性在途修复（T9）**：downgrade 链未逐版实测（个别历史迁移的
   down 路径已修——如 002a 补链外表、013 kwarg 修复——但**全量
   `up → down → up` 逐版验证是 T9 工单范围，未完成前本命令不保证成功**）。
   执行前先看该版本 down 函数内容，确认可逆再执行。
2. **先备份再 downgrade**：`mysqldump` 全量或至少受影响表；downgrade 丢掉的
   数据不可再通过 upgrade 找回。
3. **数据兼容性是隐藏杀手**：新版若已写入旧版不认识的行（新表/新 NOT NULL
   列），仅回滚镜像不回滚 schema 时——旧代码忽略新表通常无害；但若新版
   **修改**了既有列语义，旧代码读出的数据可能是错的。判断顺序：
   - 新增表/新增可空列 → 只回镜像，不动 schema（最安全）
   - 改既有列 → 回镜像 + 评估数据兼容，必要时 §3.2
4. **回滚窗口**：新版运行期间业务已写入的数据，downgrade 会被丢弃；
   跨过「下游已消费/对外已发出」的数据**不可简单回滚**，需人工对账。

### 3.3 回滚判据（任一满足即回滚，不讨论）

- 深探测 `/api/v1/health/deep` 非 200 持续 > 2 分钟（watchdog 已告警）
- 冒烟用例（登录 + 一条核心业务读）失败
- 日志出现发布前不存在的异常类型
- 数据一致性异常（立即回滚 + 冻结写入，升级 P0）

## 4. 看门狗（scripts/watchdog.sh）

**为什么需要**：compose `restart: unless-stopped` 只覆盖"进程退出"型故障；
2026-08 冻结事故的形态是**进程不退出但整进程僵死**，restart 永不触发
（复盘：`incident-2026-08-backend-freeze.md`）。看门狗轮询深探测端点，
连续 N 次失败即判定僵死嫌疑。

**宿主机部署示例（后台常驻）**：

```bash
WATCHDOG_URL=http://127.0.0.1:9111/api/v1/health/deep \
WATCHDOG_INTERVAL=10 \
WATCHDOG_FAILURES=3 \
WATCHDOG_PID_PATTERN="run_backend.py" \
WATCHDOG_LOG=/var/log/auto-agents/watchdog.log \
nohup bash scripts/watchdog.sh > /dev/null 2>&1 &
```

**开启自动处置（默认关闭）**：`WATCHDOG_RESTART=0`（缺省）= **只告警，不 kill
不拉起**（安全缺省：深探测失败也可能是 MySQL/Redis 挂了，此时杀 backend
无益且掩盖问题；且宿主机直跑场景杀了没人拉起 = 把僵死升级成宕机）。
`WATCHDOG_RESTART=1` = kill -9 目标 PID + 执行拉起命令：

```bash
WATCHDOG_RESTART=1 \
WATCHDOG_RESTART_CMD='docker compose -f /path/to/docker-compose.yml up -d backend'
# 拉起命令须幂等（容器 restart 策略与该命令双保险）
WATCHDOG_ALERT_COOLDOWN=300   # 同一持续故障的告警冷却秒数（防轰炸）
```

B4 已在本机受控环境完整演练「SIGSTOP 僵死 → 判定 → kill -9 → 拉起 →
深探测恢复」闭环（实测 9 秒，证据见工单 B4）；生产首次开启前仍应在
目标环境再演练一次（compose restart 策略与 RESTART_CMD 的接力行为
依赖具体编排器）。

**告警动作**（B4 起 payload 已规范化；完整监控栈另立工单）：

- 本地留痕：WATCHDOG_LOG（或 stdout，由 docker/系统日志接管）
- 可选 webhook：`WATCHDOG_WEBHOOK_URL`（POST JSON）；投递失败不影响看门狗主流程

**告警 payload 契约**（接收端断言以此为准，B4 已实测）：

| 字段 | 含义 | 示例 |
|---|---|---|
| `event` | 固定 `watchdog.frozen-suspected` | |
| `severity` | 固定 `P1`（10 分钟两次触发升 P0，见下方指引第 5 步） | |
| `timestamp` | 判定时刻 ISO8601（本地时区带偏移） | `2026-09-05T21:30:00+0800` |
| `host` | 看门狗所在主机名 | |
| `url` | 深探测 URL（WATCHDOG_URL 原值） | |
| `pid` | 被处置进程 PID（未解析到为 null） | |
| `failures` | 判定阈值（连续失败次数） | `3` |
| `action` | `kill+restart` 或 `alert-only` | |
| `detail` | 判定摘要 | deep probe failed 3 times in a row |
| `hint` | 处理指引（即下方五步表的入口提示） | |

> watchdog 的 webhook 不复用 backend 的 NotifyService：NotifyService 运行在
> 被监控进程内部，backend 僵死时恰是最需要告警的时刻、通道随之不可用
> （评估证据见工单 B4）。钉钉/企微等渠道由 webhook 接收端（告警网关）二次分发。

### 看门狗告警处理指引（收到告警的人按此走）

| 步骤 | 动作 |
|---|---|
| 1 | `curl -fsS <WATCHDOG_URL>` 手工复核：503 → 依赖故障方向；超时/拒连 → 进程僵死方向 |
| 2 | 看后端日志尾部（logs/ 或 `docker compose logs backend --tail 100`）：最后一条日志停在什么操作 |
| 3 | 复核依赖：MySQL/Redis 容器健康（`docker compose ps`）、宿主机磁盘/内存 |
| 4 | 若确认僵死且未开自动处置：手工 `kill -9 <pid>` 让 restart 策略拉起，观察深探测恢复 |
| 5 | 升级条件：10 分钟内两次触发或杀后不恢复 → 升 P0，冻结发布，按 incident 流程止损（回滚优先） |

## 5. 发布验证清单

| # | 检查 | 命令/位置 | 通过标准 |
|---|---|---|---|
| 1 | 深探测健康 | `curl -fsS http://127.0.0.1:9111/api/v1/health/deep` | 200，body `checks.mysql/redis == healthy` |
| 2 | 依赖探活（细分） | `/api/v1/health/db`、`/api/v1/health/redis` | 均返回 healthy（失败时看 body 的 error 类型名） |
| 3 | 冒烟：认证 | `POST /api/v1/auth/login`（测试账号） | 200 + token |
| 4 | 冒烟：核心读 | 任一核心列表接口（如 skills 列表） | 200 |
| 5 | 日志巡检 | logs/ 或 `docker compose logs backend` | 无发布前不存在的异常类型；无连续 ERROR 刷屏 |
| 6 | 迁移版本 | `alembic current`（backend/ 下） | 与发布单记录一致 |
| 7 | 看门狗 | watchdog 日志尾行 | `探测恢复`/无 ALERT；或 dry-run 单轮判定健康 |
| 8 | 容器状态 | `docker compose ps` | 三服务 healthy（backend 深探测生效） |
| 9 | 前端门禁（含前端的发布） | `bash scripts/check-frontend.sh`；admin 登录/用量/成员改动再 `CI=1 npm run e2e -w admin` | 退出码 0 |

> 1、3、4 任一失败 → 按 §3.3 判据处理，不讨论。

## 6. 已知限制（诚实清单）

- 本手册首版（T11）的回滚步骤**未在生产/演练环境完整实测**；B4（2026-09-05）
  补充：本机无 docker daemon（CLI 在但 Docker Desktop/colima 均未安装），
  已完成 compose config 层验证（§2 注意 3 的 override 语义 + build 重置）与
  本节步骤 dry-run 走查；**容器级回滚实测仍未做**，首次部署环境就绪后必须
  补做并回填实测耗时。watchdog kill 闭环已在本地受控环境实测通过（工单 B4）。
- `alembic downgrade -1` 的逐版可靠性依赖 T9 在途工单（见 §3.2 注意事项 1）。
- 资源上限（backend 1g / mysql 512m / redis 256m）为 dev 联调量级；
  生产容量需按峰值 × 1.5 余量单独评估（监控栈就绪前不放大流量）。
- watchdog 告警为单通道 webhook（B4 已实测 payload 契约与冷却抑制）；
  四类监控与分级值班体系仍属独立工单（复盘 §6 改进项 4）。
