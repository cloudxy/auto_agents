# 运维手册：部署 / 迁移 / 回滚 / 看门狗

本文只写仓库里能对上实现的内容；每节列出对应的文件，改实现时同步改这里。
被引用处：`docker-compose.yml`、`Dockerfile`、`deploy/watchdog.sh`、`backend/app/api/v1/health.py`、`/deploy` skill。

## 1. 镜像与运行时

| 项 | 现状 | 依据 |
|---|---|---|
| 构建 | 两阶段：`node` 阶段 `npm ci` → shared → admin → official；`python:3.13-slim` 阶段 `uv sync --locked --package auto-agents-backend --no-dev` | `Dockerfile` |
| 运行期依赖 | `UV_NO_SYNC=1`：`uv run` 只用构建好的 `.venv`，启动时不联网、不补装根项目的爬虫包与 dev 组 | `Dockerfile` ENV |
| 缺省环境 | `APP_ENV=prod`、`AUTO_AGENTS_API__HOST=0.0.0.0`（容器内必须监听全网卡，对外暴露由端口映射决定） | `Dockerfile`、`docker-compose.yml` |
| 端口 | `9111`；改端口须三处同步：`config/default/api.yml` 的 `API.PORT`、`EXPOSE`、`HEALTHCHECK` | `Dockerfile` |
| 前端产物 | `/app/frontend-dist/{admin,official}`，供 nginx / 静态服务接入 | `Dockerfile` |
| 必填密钥 | `AUTO_AGENTS_JWT__SECRET_KEY`、`AUTO_AGENTS_WEBHOOK__SECRET_KEY`（缺省占位符会拒绝启动）；`AUTO_AGENTS_MYSQL_DEFAULT_PASSWORD`、`AUTO_AGENTS_REDIS_DEFAULT_PASSWORD` | `backend/utils/auth.py`、`backend/app/__init__.py`、`.env.example` |
| 跨域 | 生产 `CORS.ORIGINS` 缺省为空（只允许同源）；分域部署注入 `AUTO_AGENTS_CORS__ORIGINS='["https://admin.<域名>"]'`，启动日志有自检告警 | `config/prod/web.yml`、`backend/app/cors_check.py` |

镜像 tag：用不可变 tag（提交短 SHA，如 `auto-agents-backend:c21b643`），不要只发 `latest`——回滚靠的是「上一个 tag 还在」。

## 2. 资源上限（compose 联调栈）

`docker-compose.yml` 给每个服务设了 `deploy.resources.limits` 与 json-file 日志轮转（10m × 3）：

| 服务 | 内存 | CPU |
|---|---|---|
| mysql | 512m | 1.0 |
| redis | 256m | 0.5 |
| backend | 1g | 1.0 |

跑大迁移或回填时 MySQL 被 OOM-kill（`docker inspect <容器> --format '{{.State.OOMKilled}}'` 为 `true`），临时把 mysql 的 `memory` 调到 1g–2g 再跑，跑完改回。这是联调量级的上限，不是生产容量规划。

## 3. 发布顺序（含迁移）

1. **备份**：`MYSQL_PASSWORD=... bash scripts/backup-mysql.sh`（`--single-transaction` + gzip，日备 7 天、周备 4 周，产物 `runtime/backups/mysql/`，脚本末尾 `gzip -t` 自检）。
2. **迁移门禁**：`bash tools/check/db_ir.sh && bash tools/check/db_migrations.sh`（CI 的 db-migration-gate 同款，拦破坏性 DDL）。
3. **迁移**：`APP_ENV=<env> bash scripts/db/migrate.sh`（= `alembic upgrade head`）。迁移按 expand → 发布 → contract 拆分，先上只加不删的迁移，再上新镜像。
4. **发布新镜像**：`docker compose up -d backend`（或编排器滚动更新）。
5. **验证清单**：
   - `curl -fsS http://127.0.0.1:9111/api/v1/health/deep` 返回 200（MySQL `SELECT 1` + Redis `PING`，任一失败 503）；
   - `docker compose ps` 中 backend 为 `healthy`；
   - 启动日志无 `拒绝启动`、无 `CORS 配置自检` 告警；
   - 管理后台登录、首页数据加载正常。

## 4. 回滚

| 情形 | 做法 |
|---|---|
| 新镜像有问题、迁移未改结构 | 切回上一个镜像 tag 重启 backend |
| 迁移已执行 | 先切回旧镜像，再按需 `cd backend && APP_ENV=<env> uv run alembic downgrade <上一版本号>`。**禁止降级越过 037**（MySQL errno 1553：索引仍被外键占用，见 `backend/tests/test_alembic_baseline.py`）；041 / 042 / 043 / 046 / 051–053 在 MySQL 保真通道里有 up → down → up 往返测试，其余迁移降级前先在备份库上演练 |
| 数据被破坏 | 停写，用第 3 步的备份恢复：`gunzip -c runtime/backups/mysql/latest.sql.gz \| mysql -h <host> -u <user> -p <库名>` |

## 5. 看门狗（`deploy/watchdog.sh`）

**为什么需要**：后端曾出现「进程僵死但不退出」——compose 的 `restart: unless-stopped` 只处理进程退出，永远不触发；而旧的浅探测 `/api/v1/health` 恒返回 200，依赖挂掉也显示健康。由此有了深探测端点 `/api/v1/health/deep`（503 语义，提交 950635e）、`run.py` 子进程输出排水防僵死（提交 9a666ec）和这个看门狗。

**用法**（全部环境变量，详见脚本头注释）：

```bash
WATCHDOG_URL=http://127.0.0.1:9111/api/v1/health/deep \
WATCHDOG_DRY_RUN=1 bash deploy/watchdog.sh        # 先空跑：只打印判定与将执行的动作
WATCHDOG_URL=http://127.0.0.1:9111/api/v1/health/deep bash deploy/watchdog.sh   # 只告警（缺省）
```

- 缺省 `WATCHDOG_RESTART=0` 只告警不杀进程：深探测失败也可能是 MySQL / Redis 挂了，此时杀 backend 无益；宿主机直跑时杀了没人拉起，会把僵死升级成宕机。
- 开自动处置：`WATCHDOG_RESTART=1` + `WATCHDOG_RESTART_CMD='docker compose -f <compose 文件> up -d backend'`（幂等命令，与容器 restart 策略双保险）；目标进程由 `WATCHDOG_PID` → `WATCHDOG_PID_FILE` → `pgrep -f scripts.runlib.backend` 依次解析（slim 镜像没有 pgrep，容器内前两者必填其一）。
- 连续 `WATCHDOG_FAILURES`（缺省 3）次失败判定僵死嫌疑；同一持续故障在 `WATCHDOG_ALERT_COOLDOWN`（缺省 300s）内不重复告警，kill / 拉起不受冷却影响。

### 告警 payload 契约

`WATCHDOG_WEBHOOK_URL` 收到的 `POST application/json`（尽力投递，失败只记 WARN）：

| 字段 | 值 |
|---|---|
| `event` | `watchdog.frozen-suspected` |
| `severity` | `P1` |
| `timestamp` | ISO8601，带时区偏移 |
| `host` | `$HOSTNAME` 或 `hostname` |
| `url` | 被探测的健康端点 |
| `pid` | 目标 PID 字符串；未解析到时为 `null` |
| `failures` | 判定阈值（字符串） |
| `action` | `kill+restart` 或 `alert-only` |
| `detail` | `deep probe failed <N> times in a row` |
| `hint` | 处理指引：先看后端日志尾部与 MySQL / Redis 状态（本节） |

**收到告警后**：`docker compose logs --tail 200 backend` 看最后的请求与异常 → 分别 `mysqladmin ping`、`redis-cli ping` 确认依赖 → 依赖正常而 backend 不响应时再重启 backend，并保留重启前的日志用于复盘。

## 6. 能力市场 hub 根（D2：与开发中枢 `.agents/` 分离）

| 项 | 现状 | 依据 |
|---|---|---|
| 根 | `SKILLS.AGENTS_ROOT`，缺省 `runtime/agents-hub`（`runtime/` 不入库；相对路径按进程 cwd 即仓库根解析）。覆盖：`AUTO_AGENTS_SKILLS__AGENTS_ROOT=/data/agents-hub` | `config/default/skills.yml`、`backend/services/power_market/hub_paths.py` |
| 谁读写 | `run.py start/restart` 与 `POST /api/v1/capabilities/sync-agents-hub` 同步；目录导入 / legacy 导入落盘；`assets/prune-missing` 失源清理——都只认这个根，不扫 `.agents/` | `scripts/sync_agents_hub.py`、`backend/app/api/v1/capabilities_gov.py` |
| 根不存在 | 同步按零项完成；导入落盘时自动创建；失源清理**拒绝剪除**（返回 `skipped_reason=hub_root_empty`），根配错不会把整个目录判失源 | `backend/services/power_market/agents_hub.py` |
| 入库路径 | `capability_assets.file_path / origin_ref / logo / background` 写 `agents-hub/<相对根>`，与根的物理位置无关（挪根不改库）；D2 前的 `.agents/...` 只读兼容：先找根下同位置，再回落仓库 `.agents/` | `hub_paths.py` |
| 许可 | 插件取清单 `license`；其余资产先读自身 frontmatter `license`，插件内资产未声明时继承插件清单；缺失 = NULL（不再默认 MIT），不在默认允许集且无 `public_license_override` 的资产同步时落 `unlisted` | `agents_hub_scan.py`、`agents_hub._license_allows_listing` |
| 容器 | `.dockerignore` 排除 `runtime/` 与 `.agents/`：容器里的根是空目录，导入内容随容器销毁——要保留就把 `AGENTS_ROOT` 指到挂载卷 | `.dockerignore` |

**一次性迁移**（D2 前导入进 `.agents/` 的产品内容 + 库内 `.agents/` 前缀；先停后端，先备份，见第 3 节）：

```bash
uv run python scripts/db/migrate_agents_hub_root.py --env <env>            # dry-run：打印 [move]/[keep]/[conflict]/[db] 计划
uv run python scripts/db/migrate_agents_hub_root.py --env <env> --apply    # 执行；可重复跑（幂等）
```

- `[keep]`：git 跟踪的开发内容、`plugins-lock.json` 插件、符号链接——留在中枢；它们在库里的存活上架行会被下架为 `unlisted`（不删行，超管可再上架）。
- `[move]`：其余条目搬进 hub 根，库里对应行的前缀改写为 `agents-hub/`。本机未 `git add` 的开发中 skill 也会被判 `[move]`，dry-run 时先核对。
- `[conflict]`：hub 根已有同名项，跳过，人工合并后重跑。
- 文件先搬、库后改（单事务）；库这步失败时 legacy 前缀仍解析到搬后的位置，不断读，修好连接重跑即可。
- 迁移后跑一次 `POST /api/v1/capabilities/assets/prune-missing?dry_run=true` 看孤儿清单（库里有、磁盘哪里都没有的行），确认后再去掉 `dry_run` 执行。
