# SRE 深层次问题审查报告 — auto_agents

> 审查日期：2026-09-06 ｜ 审查视角：半夜三点现场 + 平时静默故障
> 依据：仅仓库事实（代码 / compose / Dockerfile / CI / scripts / docs/ops / config），未读 plan/research 类目录。
> 前提事实：该仓库已经历多轮加固（深探测 / watchdog / 迁移门禁 / 异步 Redis 门面），本报告只列**仍然存在的深层问题**。

## 总体判断

这套系统的**"进程死了"类故障已有答案**（深探测 + watchdog + restart 策略 + 一份诚实的 deploy.md），但**"进程活着、业务已死"和"数据没了"两类故障基本没有答案**：8 个后台循环与 API 同进程同生命周期，循环死亡 / 队列堆积 / 死信增长没有任何出口（deep 探测只看 MySQL+Redis，唯一告警通道是 watchdog 的深探测）；MySQL 无任何备份与恢复演练；爬虫 Worker 是游离于 compose 与守护体系之外的手工宿主机进程，断链后任务静默 pending 6 小时；watchdog 的 kill -9 处置本身会造成采集结果静默丢失。另一个系统性风险是**全部运维资产从未在目标环境演练过**（deploy.md §6 自认），CI 构建的镜像不进 registry，回滚凭证只是本机 tag。半夜三点最容易发生的场景不是"backend 挂了"，而是"一切探测皆绿、结果回流已冻结 N 小时、无人知晓"。

---

## 深层次问题清单（按严重度降序）

### 1. 单租户配额熔断会冻结全平台结果回流管道，且全程无任何信号

- **严重度**：高
- **证据**：
  - `backend/tasks/consumer.py:688-695` — `_flush_batch` 在落库事务前对批内每个租户调 `QuotaService.check_result_storage(tid)`；
  - `backend/services/quota_service.py:112-116` — 超限直接 `raise QuotaExceededException`；
  - `backend/tasks/consumer.py:552-559` — `batch` 只在 flush **成功后** clear；`consumer.py:576-578` — flush 异常被 `except Exception` 吞掉、sleep 1s 后带着**同一个毒批次**无限重试。
- **为什么深层**：爆炸半径是级联的——一个租户达到 `result_storage` 配额，其消息让整批 flush 的 commit 永远失败，**所有租户**的结果从此只进进程内存（无上限增长）不再落库；spider 侧照常采集推送，item_queue 表面在消化，DB 里 result_count 停止增长。此时 `/api/v1/health/deep` 返回 200（DB/Redis 均好），watchdog 判定健康，restart 策略不触发——这正是 2026-08 事故"所有自动化信号都是绿的"的复发形态，只是换了故障域。且 kill -9（watchdog 处置）会把这些内存批次**永久蒸发**（见问题 5）。
- **解决方案**（按优先顺序）：
  1. 毒消息隔离：`_flush_batch` 捕获 `QuotaExceededException` 时，仅将**该租户**的消息 rpush 到 `spider:item_queue:quota_suspended:<tid>`（带 TTL 与长度上限），其余消息照常落库；对暂停键长度 >0 打 WARNING 并暴露到健康端点（见问题 4 的 loops 探针）。
  2. 配额检查前移：入队侧（`SpiderService.enqueue` / 调度触发）就拒绝超限租户的新任务，从源头不产生回流。
  3. flush 重试上限（如 3 次失败 → 整批转死信队列 + ERROR 日志），杜绝无限毒批次循环。

### 2. 零备份、零恢复演练：数据资产只有 docker volume 一个副本

- **严重度**：高
- **证据**：全仓库 grep `mysqldump/backup/备份` 仅命中 `docs/ops/deploy.md:109`（downgrade 前的手工提示）；`docker-compose.yml:38-39` 数据仅存 `mysql_data` 本地卷；无 cron / systemd-timer / CI 任务做备份；deploy.md §6 恢复路径仅有"先备份再 downgrade"一句。
- **为什么深层**：恢复手段的真实性=0。这套系统的核心资产是采集结果（spider_results）、SaaS 租户与用量账单（llm_token_usage）——半夜磁盘损坏 / `docker compose down -v` 误操作 / MySQL 数据卷损坏，任何一条都等于**数据不可逆丢失**，且没有任何手段能把 RPO 说清楚。备份与回滚是两件事：deploy.md 的回滚章节再完善，也救不了没有备份的数据。
- **解决方案**：
  1. P0（当天可做）：宿主机 systemd-timer 每日 `mysqldump --single-transaction --routines --triggers auto_agents | gzip` 落 `/var/backups/auto-agents/`，保留 7 天 + 每周 1 份保留 4 周；备份成功/失败均 POST watchdog 同款 webhook（复用其 payload 契约，`event: backup.completed/failed`）——**备份失败必须当 P1 告警**，否则备份会静默烂掉。
  2. P1：每月一次恢复演练（备份恢复到临时容器 `docker run mysql:8` + 跑 `SELECT COUNT` 冒烟），把实测耗时回填 deploy.md §6。
  3. P2：`docker cp` / binlog 复制到非本机路径（哪怕 rsync 到另一台机器），消除单机故障域。

### 3. 爬虫 Worker 游离于部署与守护体系之外：断链静默，任务 pending 6 小时才有人看见

- **严重度**：高
- **证据**：
  - `docker-compose.yml` 全部服务 = mysql / redis / backend / litellm（可选）——**没有 spider 服务**；`run_spider.py` 是宿主机手工启动的前台进程（`scripts/run-spider.sh` 仅一行 uv run），无 systemd / 无 restart / 不在 watchdog 视野内；
  - `backend/services/spider_registry_service.py:247-259` — worker 心跳（TTL 30s）只被扫描用于注册表**展示**，无离线告警；入队侧也不校验"是否有存活 worker"；
  - `config/default/settings.yml:18` — `STALE_TASK_HOURS: 6`：worker 全挂后，任务要 pending 满 6 小时才被对账置 failed（`consumer.py:418-429`，默认回收间隔 300s）。
- **为什么深层**：采集是这条产品线的核心业务链路，但它的执行器是全系统**唯一没有任何守护、没有健康信号、不在发布拓扑里**的组件。半夜 worker OOM / 主机重启 / 终端关闭，后果是：调度器每个 cron tick 继续入队 → 任务全部 pending 堆积 → 6 小时后批量置 failed → 用户才可能从任务页发现。这属于"平时你根本不知道它坏了"的最典型样本。
- **解决方案**：
  1. 把 worker 纳入守护：compose 增加 `spider` 服务（复用同一镜像，`command: uv run python run_spider.py --no-...`）或宿主机 systemd unit（`Restart=always`、`RestartSec=5`）。取舍：容器化改动小、与现有栈一致，但宿主机直跑场景用 systemd。
  2. 入队/调度前增加"存活 worker"检查：无 `spider:worker:*` 键且队列 pending>0 时拒绝入队并打 ERROR（防堆积雪崩），这是 10 行内的守门。
  3. 告警接线：把「worker 心跳全灭 + 任务队列非空」做成 watchdog 的**第二个探测目标**（watchdog 支持 PID/URL 多实例部署，直接再起一个实例探一段脚本/端点），P1 webhook 通知到人——不要等 6 小时的 stale 回收兜底。

### 4. 可观测性答不出"什么时候开始坏的、影响谁"：8 个后台循环零指标、零告警出口，deep 探测只覆盖 MySQL+Redis

- **严重度**：高
- **证据**：
  - `backend/app/api/v1/health.py:78-106` — deep = MySQL SELECT 1 + Redis PING，仅此两项（§残留风险 3 自认"存储与下游 LLM 未纳入"）；
  - 消费/调度等循环死亡后**无人拉起、无人知晓**：`backend/app/__init__.py:84-161` 各组件 start 失败仅 warning；循环内部异常全部 `except Exception` 吞掉继续（如 `consumer.py:576-578`），`asyncio.create_task` 无 done-callback（`consumer.py:165-175`）——task 静默消亡是 asyncio 经典故障态；
  - `backend/services/schedule_service.py:294-300` — 队列堆积超过 `QUEUE_DEPTH_WARN` 只打一行 `logger.warning` 落文件，**没有任何告警出口**；死信队列（`DEAD_ITEM_QUEUE`）只有手工浏览/清理 API（`services/dead_item_service.py`），无增长告警；任务失败率、ingest 吞吐、无 metrics 端点。
- **为什么深层**：现状唯一 7x24 自动信号是 watchdog→深探测，它能回答"backend 进程/DB/Redis 死没死"，回答不了"数据管道还通不通、从几点开始不通、波及哪些租户"。日志 WARNING 不是告警——半夜没人 grep 文件。
- **解决方案**（具体到测什么/怎么告/谁处理）：
  1. 新增 `GET /api/v1/health/loops`：返回各 lifespan 组件（consumer/scheduler/usage_flush/scoring/patrol/newapi）的 `{alive, last_tick_at}` + `queues: {task_high/normal/low 的 LLEN, retry_zset ZCARD, dead_letter LLEN, pending 任务数}`。实现要点：各循环每次迭代更新进程内 `_last_tick`（或 Redis 心跳键），done-callback 捕获 task 异常置 alive=false。
  2. 判定与告警：`alive=false` 或 `dead_letter>0` 或 `task_normal LLEN>50 持续 2 轮` → 503。watchdog 起第二个实例探它（`WATCHDOG_URL=.../health/loops`），payload 契约复用，`hint` 指明"看 loops body 中 alive=false 的组件名 + 对应日志文件"。
  3. 升级闭环：通知人固定（值班表哪怕是同一个人），P1 处理动作写进 deploy.md §4 的指引表（重启 backend 可恢复循环；dead_letter 用现有 API 排查重放）。
  4. 暂不引 Prometheus——单机 compose 下 health/loops + watchdog 双实例已覆盖"发现"问题，等上监控栈工单再迁移。

### 5. watchdog 的 kill -9 处置本身制造静默数据丢失与 6 小时任务悬挂（恢复手段与数据安全未对齐）

- **严重度**：中高
- **证据**：
  - `backend/tasks/consumer.py:538` — ingest 用 `lpop` 弹出后消息在内存批次中（最多 50 条 / 2s flush 窗口），`kill -9` 直接蒸发；
  - `backend/tasks/consumer.py:220` — dispatch `blpop` 弹出后若未处理完即被杀，消息丢失，任务卡 pending 直到 6h 对账（`_requeue_stale_pending`）；
  - `scripts/watchdog.sh:202-204` — `kill -9` 是唯一处置手段，无 SIGTERM 宽限；`docs/ops/deploy.md:147-159` 文档化该行为但未声明 RPO 影响。
- **为什么深层**：恢复动作的副作用没有被建模——watchdog 把可用性问题（僵死）转换成数据问题（丢批次、任务悬挂），而后者无信号、无告警，是典型的"修好了但不知道丢了什么"。代码其实已经有优雅退出路径（`_ingest_loop` 的 CancelledError 分支会 flush 残余批次，`consumer.py:565-575`），但 SIGKILL 让它永远走不到。
- **解决方案**：
  1. watchdog 处置顺序改为 SIGTERM → 宽限 10s（uvicorn 优雅停机会走 lifespan shutdown → consumer.stop() → flush）→ 再 kill -9。改动约 5 行，RPO 从"最多 50 条 + 消息"收敛到接近零。
  2. ingest 加中转确认（可选、后置）：lpop 后先 rpush 到 `spider:item_queue:processing`，flush 成功后 lrem；启动时把 processing 回灌主队列。彻底防丢但增加每次 flush 的往返，等出现真实丢数据诉求再做。
  3. deploy.md §4 补一行 RPO 声明："kill 处置的丢失窗口 = 批次大小 × flush 间隔"，让开启 `WATCHDOG_RESTART=1` 的人知情。

### 6. 生产部署路径从未演练，且 CI 不产出可部署工件（无 registry）：回滚凭证是"本机 image tag"

- **严重度**：中
- **证据**：
  - `docs/ops/deploy.md:212-216`（§6）自认"回滚步骤未在生产/演练环境完整实测""容器级回滚实测仍未做"；
  - `.github/workflows/ci.yml:165-175` — docker-validate 只 `docker build` 本地打 tag，**不 push 任何 registry**；deploy.md §1 的回滚依赖 `git-<sha>` tag"仍存在于镜像仓库/本机"——实际只有本机，主机重装/磁盘损坏 = 全部回滚凭证蒸发；
  - `config/prod/web.yml` — CORS 仍是 `https://your-domain.com` 占位符，佐证 prod 环境未真正立起。
- **为什么深层**：deploy.md 是"发布时的一致性基准"，但它的每一步都建立在"目标环境有一份能跑 docker 的主机 + 仓库 + 本机构建的镜像"这个未验证假设上。首次真实发布 = 未演练流程 + 手工步骤 + 半夜执行，这是变更事故的标准配方；compose override（`build: !reset null`）这类精细语义一旦在目标环境行为不符，回滚就会以最坏方式失败（§2 注意 3 自己都发现了同名 tag 覆盖陷阱）。
- **解决方案**：
  1. CI 增加 publish 阶段：push `ghcr.io/<org>/auto-agents-backend:git-<sha>`（GHA 内建 GITHUB_TOKEN 即可，零新增基础设施）；部署与回滚统一改 pull-by-digest。取舍：需要目标机可出网，若纯内网则至少在 CI 产 `docker save` tar 工件并归档。
  2. 发布前必须完成一次演练机全流程实跑（build→tag→up→验证→回滚→验证），把耗时回填 deploy.md §3/§6——这已是文档承诺，缺的是强制门（建议写进发布 checklist 第 0 项）。
  3. `config/prod/web.yml` 占位符换真实域名前，prod 环境禁止放流量（否则 CORS 静默放行走 your-domain.com 的任意来源）。

### 7. 变更安全：迁移入口环境缺省是 local，且爬虫配置存在"双事实源"漂移

- **严重度**：中
- **证据**：
  - `scripts/migrate.sh:4` — `APP_ENV="${APP_ENV:-local}"`，且不打印目标库；deploy.md §2 要求 `APP_ENV=prod bash scripts/migrate.sh`，全靠操作者记住前缀——漏掉即对 local 库执行迁移（或因 prod 密码缺失半途失败，留下半套环境认知）；
  - `backend/alembic/env.py:26` — 密码只读裸键 `MYSQL_DEFAULT_PASSWORD`，而 compose/文档主推 `AUTO_AGENTS_MYSQL_DEFAULT_PASSWORD` 双轨并存，prod .env 若只写带前缀键，alembic 会拿空密码连库；
  - `config/scrapy/default/settings.yml:24` — 仍声明 `scrapy_redis.pipelines.RedisPipeline: 100`，而真实生效的 `scrapy/settings.py:79` 已将其置 None（P1-8 修复：该管道无消费者无 TTL 会撑爆内存）。这份 yml 会被 Dynaconf 加载（`config/__init__.py:39`）但对 ITEM_PIPELINES 无效——它是死配置，却是误导性最强的那种。
- **为什么深层**：半夜执行 `bash scripts/migrate.sh` 是最自然的肌肉记忆；配置双源则保证未来某次"照 yml 改配置"的变更静默不生效或反向生效（比如有人"照文件"把 RedisPipeline 改回去）。
- **解决方案**：
  1. migrate.sh 开头：`APP_ENV` 未显式设置即 `die`（列出 local/dev/prod 三选一），并打印解析后的目标 `HOST/PORT/DB_NAME`（密码掩码）+ 5s 确认；alembic env.py 密码读取与 db.py `_get_password` 对齐（补 `AUTO_AGENTS_` 前缀剥离逻辑）。
  2. 删除 `config/scrapy/default/settings.yml` 中与 `scrapy/settings.py` 重复的 DOWNLOADER_MIDDLEWARES / ITEM_PIPELINGS 段（文件头加注释"中间件与管道唯一定义在 scrapy/settings.py"），或在 check-arch.sh 加一条 grep 断言防复活。

### 8. 日志基建两处暗雷：生产 traceback 回显局部变量（密钥入日志）+ 容器内文件日志随容器蒸发、docker 日志总上限 30MB

- **严重度**：中
- **证据**：
  - `platform_core/logger.py:81` — `diagnose=True` 对所有环境无条件生效（loguru 官方文档明确生产禁用：traceback 会渲染变量值）；叠加 `health.py:39` 自述"日志记录含连接串等敏感信息"、异常处理器大量 `logger.error(f"...{e}")`，密码/api_key 出现在 traceback 变量区的概率极高；
  - `docker-compose.yml:23-27` — json-file `max-size 10m × max-file 3` = 每服务 **30MB** 硬顶；loguru 文件 sink 写容器内 `/app/logs/`，未挂卷——`docker compose up -d` 升级即蒸发；deploy.md §5 发布清单第 5 项"日志巡检"依赖的恰恰是这 30MB / 容器内文件；
  - `scripts/watchdog.sh:74-75` — watchdog 自身日志 `>>` 追加，无轮转（`WATCHDOG_LOG=/var/log/auto-agents/watchdog.log` 长期运行无限增长）。
- **为什么深层**：日志是"什么时候开始坏的"的唯一考古现场（2026-08 复盘就靠它），但当前配置让现场既容易被抹掉（30MB / 容器重建）又容易变成泄密源（diagnose）。这两个问题平时完全无感，出事时同时爆发。
- **解决方案**：
  1. `init_log` 按 `APP_ENV != "local"` 关闭 `diagnose`（保留 backtrace=False/True 取舍：建议 backtrace=True、diagnose=False），一行改动，消除最大泄密面。
  2. compose backend 服务挂 `- ./logs:/app/logs`；docker logging 提到 `max-size 50m, max-file 5`（磁盘换考古窗口）；watchdog 日志按 `logrotate` 配一周轮转（deploy.md 部署示例补一行）。

### 9. Redis 容量饱和无策略、无信号：dupefilter/调度队列永生 + compose 256m 硬顶 → 满盘后入队全面失败

- **严重度**：中
- **证据**：
  - `scrapy/settings.py:54-56` — `SCHEDULER_PERSIST = True`（队列 + dupefilter 键跨任务持久，无 TTL）；全仓库无任何清理 `spider:*:dupefilter` / 调度队列键的代码（grep 无命中）；
  - `docker-compose.yml:44-48` — redis 硬限 256m，`command` 仅 `--requirepass`，**无 maxmemory / 无淘汰策略** → 默认 noeviction，写满即 OOM 拒写；
  - 全系统无 `used_memory` 采集与告警（问题 4 的盲区在容量维度的具体化）。
- **为什么深层**：这是"什么先到顶"的答案——Redis 大概率先满（dupefilter 随爬取 URL 数单调增长），而满盘的形态是：调度入队报错（`schedule_service.py` 仅 warning"调度触发被拒绝"）、任务重试 zadd 失败、结果回流失败——多路同时退化但进程全绿，最后被当成"爬虫又失败了"排查半天。容量问题没有信号 = 慢性故障按急性事故发作。
- **解决方案**：
  1. 立刻可做：`command: redis-server --requirepass ... --maxmemory 200mb --maxmemory-policy noeviction` 显式声明策略（noeviction 保数据正确性，宁可拒绝写入），并在 health/loops（问题 4）里加 `used_memory / maxmemory` 比值，>80% P1 告警。
  2. 任务终态回调时清理该爬虫 dupefilter（`del <spider>:dupefilter`，需确认增量去重不受影响——SCHEDULER_PERSIST 保留队列、只清 dupefilter 是常见折中），或每日低峰定时按 spider 前缀清理。
  3. 生产容量评估时把 Redis 峰值 ≈ 「7 日去重指纹量 × ~100B + 队列」算进 deploy.md §6 的容量清单。

### 10. watchdog 无人守护、告警无升级链；API 裸暴露无 TLS：运维兜底组件自身是单点

- **严重度**：低（单项低，合并后是真实的半夜风险）
- **证据**：
  - `docs/ops/deploy.md:133-142` — watchdog 部署方式是 `nohup ... &`，无 systemd、无自监控（它挂了等于告警体系整体下线，且无任何信号）；
  - `watchdog.sh:182-195` — 冷却 300s 内只发一条 webhook，持续故障 = 每 5 分钟重发一条，无聚合、无 P1→P0 自动升级（"10 分钟两次升 P0"写在 runbook 里靠人执行）；
  - `docker-compose.yml:67-68` — `9111:9111` 默认绑宿主机 0.0.0.0；仓库内无 nginx/反代/TLS 任何痕迹（grep 无命中），deploy.md 也无接入层章节；`/api/docs` 未在任何环境关闭（`backend/app/__init__.py:215` 未传 `docs_url`）。
- **为什么深层**：告警链的第一环（watchdog）自己就是"进程退出型故障 + 无人拉起"的裸进程——用它去兜别人僵死的风险，自身却处于它本该防住的故障域里。而 API 直暴 + 无 TLS 意味着 JWT/外部 API key 明文过局域网，审计面（谁在半夜调了删除接口）无法建立。
- **解决方案**：
  1. watchdog 交给 systemd（`Restart=always` + `WatchdogSec` 可选），deploy.md 部署示例替换 nohup；
  2. 告警接收端（钉钉/企微机器人）做侧聚合：同 event 10 分钟内 ≥2 次自动 @所有人 并标记 P0——不需要改 watchdog，在接收端脚本实现；
  3. 接入层补齐：宿主机 nginx/caddy 反代 9111（TLS + 仅监听 127.0.0.1 的 compose ports 映射改 `127.0.0.1:9111:9111`），`FORWARDED_ALLOW_IPS` 同步收紧（api.yml 已预留）；生产 `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` 按 `APP_ENV` 关闭。

---

## 附：本报告未列为问题但值得知道的边界

- `docker-compose.yml` 的 MySQL 512m / backend 1g 资源上限是 dev 量级，deploy.md §6 已自认生产需重估——未单列，因为它已被文档诚实记录，且在问题 4/9 的容量信号落地前放大流量本身就不该发生。
- alembic downgrade 全链可靠性（T9 在途）未单列：deploy.md §3.2 已如实标注"不保证成功"，本报告问题 2（备份）是其前置解。
- Scrapy 侧反爬红线（DOWNLOAD_DELAY + UA 轮换中间件）核实存在（`middlewares/__init__.py:90-111`、`scrapy/settings.py:34-42`），未发现问题。
