# SRE 第二轮纵深评估 — auto_agents（2026-09-06）

评估人：SDLC SRE（只读评估，未改动任何项目文件；唯一例外为本报告）
评估问题：「从本地可用到 SLA 可承诺还差什么」。一轮遗留核对 + 六个纵深面（备份恢复 / 容量成本 / 发布工程 / 故障演练 / 安全运维 / 投资方向），证据均为文件行号或上轮工单记录。

## 总体判断

一轮交付**真实落地且有两处超预期**：上轮 blocker「迁移门禁假绿」已闭环（`scripts/check-db-migrations.sh` 改 heredoc 计数传回主 shell，脚本 :35 注释与 :162-169 退出码实现可证，且已成为 CI 第 3 job）；T9 的 up→down→up 真库演练不止「跑通」，还**暴露并处置了 020 的预存 down 缺陷**（T9.md:93 exit=1 → 归档/还原路径补齐后 exit=0）。watchdog 十字段 payload + 冷却抑制 + 五步 runbook 实测闭环，安全缺省（只告警不杀）判断正确。

但按「SLA 可承诺」标准衡量，当前系统的风险敞口**从进程层转移到了数据层**：一轮把「进程僵死」这一个故障模式修掉了，而现在最大的三个敞口全是数据性的——**备份机制为零**（mysqldump 只是 downgrade 前的手工提醒，无脚本无 cron 无恢复演练，RTO/RPO 目标全仓不存在）、**计费/配额数据放在无持久化的 Redis 里**（租户月度 LLM 用量仅存 Redis hash，容器重建即清零）、**Fernet 主密钥无托管无轮换**（丢失 = 全部供应商 API Key 报废）。同时 CI 不产可拉取镜像、无 registry、无 staging，回滚凭证（git-<sha> tag）只存在于文档。结论：**现形态可承诺「尽力可用」，不可承诺任何 RTO/RPO/MTTR 数字**；要够到 SLA，缺的不是更多演练，而是数据安全网、镜像产物链、单点架构三件基础设施。

## 一轮遗留核对

| 一轮遗留 | 本轮状态 |
|---|---|
| 容器级回滚实测（无 docker daemon） | **仍遗留**：本机仍无 daemon，deploy.md §6 诚实清单继续挂着；且 CI 不 push 镜像（见 F4），首次部署环境就绪后必须补 |
| 时钟混写 ±8h | **有进展**：ADR-0009 成文（DB 时钟单一事实源 + 全库 DATETIME naive 契约 + 91 列实证），「应用层混写移交独立票」仍开放 |
| 迁移门禁假绿 + 未进 CI | **已闭环**：见总体判断（CI db-migration-gate job + 退出码修复） |
| 监控告警 0 条（P1-7） | **仍 open**（rereview-findings.md:110），仅 watchdog webhook 单通道；本轮 F9 引申：连资源饱和度也是盲区 |

## FINDINGS（10 条）

| # | 标题 | 严重度 | 证据（文件:行号） | 建议 |
|---|------|--------|-------------------|------|
| 1 | 备份机制为零：mysqldump 只存在于两处「提醒」，无脚本无调度无演练。全仓无 backup 脚本/cron/systemd timer（scripts/ 全目录核对）；deploy.md §3.2 仅「先备份再 downgrade」手工指令；deploy/newapi/README.md:106,169 是对另一套栈的「建议定期」表格；RTO/RPO/SLO 全仓零命中（docs/plan 仅方法论引用）。迁移 up→down→up 演练（T9）是 schema 回滚，**数据恢复从未演练**——备份的可用性未经证明等于没有备份 | blocker（对 SLA 而言） | scripts/（无 backup*）；docs/ops/deploy.md §3.2 注意 2；grep RTO/RPO 全仓空 | 最小闭环三件套：① `scripts/backup-mysql.sh`（mysqldump --single-transaction + gzip + 保留 7 天日备/4 周周备 + 备份后 `mysql --execute="SELECT 1"` 空跑校验）② 宿主 cron/launchd 调度 + 副本出宿主机 ③ 在演练环境做一次「drop 库 → 从备份恢复 → 深探测 + 冒烟通过」，回填实测耗时作为 RTO 基线（目标建议 RTO≤4h / RPO≤24h 起步） |
| 2 | 计费/配额数据在易失存储：Redis 无命名卷（compose 全部卷只有 mysql_data）+ command 未开 AOF，官方镜像匿名卷**每次容器重建即更替**；而租户**月度** LLM 用量仅存 Redis hash（llm_usage_service.py:118-122 直读 Redis，月 hash 带 TTL）、日明细 30 天 TTL（:47）、quota:count 配额计数、spider:task_queue 派单队列、四类限流计数全在其中。Redis 丢失 = 月度账单清零 + 预算熔断重置 + queued 任务卡死待人工；cooldown/缓存类可自愈（fail-open 设计正确） | blocker | docker-compose.yml:41-55（redis 无 volumes、command 无 appendonly）；llm_usage_service.py:47,102-103,118-122；platform_core/queues.py:29,99,104-105 | 三选一按数据分级：**月用量/配额改以 MySQL 为事实源**（Redis 只做加速缓存，flush 频率 → 计费容忍度）；或 redis 加命名卷 + `--appendonly yes`；或书面声明「用量数据可丢」并获业务确认。同时加 `--maxmemory 200mb --maxmemory-policy noeviction`（与 256m limit 对齐），把 OOM 行为从默认变显式 |
| 3 | Fernet 主密钥单点无托管无轮换：LLM_ENCRYPTION_KEY 丢失/轮换后解密一律按缺失处理（llm_secret_vault.py:75 注释自认），**无 re-encrypt 工具、无轮换流程、无托管要求**——密钥丢了 = 所有供应商 API Key 报废且不可恢复。配套：LiteLLM 导出器把明文 key 写到 config.gen.yaml（mode 600 + gitignore 登记是好实践，但明文落盘、无加密、且会被「备份整个目录」类操作无意识带走） | major | backend/services/llm_secret_vault.py:26-40,75；backend/scripts/export_litellm_config.py:13,50-52；deploy/litellm/config.gen.yaml（本机存在） | ① deploy.md 增「密钥清单」节：LLM_ENCRYPTION_KEY 必须与 DB 备份分开托管（密码管理器/离线），恢复演练必须包含「新机配主密钥」步骤 ② 提供 `re-encrypt.py`（旧钥解密→新钥加密单事务回写）支撑轮换 ③ config.gen.yaml 写入部署机受控目录而非仓库工作区 |
| 4 | CI 不产可回滚产物：docker-validate 只 `docker build -t auto-agents-backend .` 即丢（ci.yml:148），不 push 不打 tag；deploy.md §1 的 git-<sha> tag 规范因此**没有产物载体**，回滚凭证依赖「部署机手工 build 并记得保留旧 tag」。staging 概念不存在（config 有 local/dev/prod，部署场景只有 compose 单机一节）；§5 验证清单 8 项全手工，migrate.sh 仍只有 `upgrade head`（无 down/status 子命令，一轮 #9 建议未落地）。发布工程现状 = 文档优秀的一次性手工流程 | major | .github/workflows/ci.yml:148；docs/ops/deploy.md §1 vs CI 全文；scripts/migrate.sh:3-4 | ① CI 增 push job（tag `git-<sha>` 推 GitHub GHCR，零成本起步）② migrate.sh 补 `up/down/status` 三子命令 ③ §5 清单脚本化为 `scripts/smoke.sh`（curl 断言 + 退出码），发布执行从 checklist 变成命令 |
| 5 | 全栈单机单点无切换路径：MySQL 单实例（无主从/云 RDS 概念）、Redis 单实例、backend 单 uvicorn 进程（run_backend.py 非 reload 路径无 workers 参数）三单点同居一个 compose。MySQL 512m limit 被 compose 注释自认会顶（「跑大迁移 OOM-kill 时按 deploy.md 上调」）——即作者已预期该 limit 会被突破，但没有自动上调机制也没有告警。DB 主库故障 = 全站停，无降级路径可言（切换路径都不存在，谈不上演练） | major | docker-compose.yml:13-21,41-55；run_backend.py:140-147；platform_core/db.py:77,93 | 分两步：**≤20 客户**：把 MySQL 挪到托管（云 RDS 或至少独立卷+每日备份+快照），compose 保留应用层；**>20 客户前**：出一份「DB 故障 runbook」（从备份恢复 + RTO 数字），无需主从但有恢复路径即比现在强。pool_size/max_overflow 移入 config（一轮 #11 残留） |
| 6 | 爬虫节点失联不可见：worker 心跳键（spider:worker:{id}）**全仓无写入者**——queues.py:73-74 定义、spider_registry_service.py:247-259 扫描读取，但 backend/scrapy/scripts 均无 hset 写入 → Worker 列表恒为空，节点失联无信号。任务级兜底存在且真实（running 超时回收 consumer.py:170,406 STALE_TASK_HOURS + 重试重入队 :384-403），但「节点死了」这件事对管理员不可见，只能在任务超时后间接推断 | major | platform_core/queues.py:73-74；backend/services/spider_registry_service.py:247-259；全仓 grep WORKER_HEARTBEAT 无写入方；scrapy/extensions/ 仅 \_\_init\_\_.py | ① scrapy 侧（或 run-spider.sh）启动时 hset 心跳 + 周期刷新 + TTL ② registry/管理页对「心跳过期」节点标 offline 并入 watchdog 同款 webhook 告警 ③ 演练：kill 爬虫节点 → 验证任务回收时限 + 告警到达 |
| 7 | Redis 故障的运行时联动未演练，含一个误处置陷阱：fail-open 有单测（test_auth_rate_limit_failopen.py、test_b1_rate_limiter.py），但运行时全链未验——Redis 宕 → /health/deep 503（含 Redis PING）→ watchdog 判定失败；**WATCHDOG_RESTART=1 的环境会反复 kill -9 一个无辜的 backend**（安全缺省 =0 规避了它，但开启自动处置正是为了「无人值守」，两者组合的语义未演练过）。叠加 F2 无持久化：Redis 重启后限流计数清零（暴力尝试窗口重置）+ 月用量清零 | major | docker-compose.yml:90（深探测含 Redis）；deploy.md §4 RESTART 语义；backend/app/core/rate_limiter.py:24-26（fail-open 双向策略已设计） | 演练两条：① 停 redis 容器 5 分钟 → 记录 deep 503 → watchdog 行为（RESTART=0/1 各一次）→ 恢复后验证用量/队列现状，把「Redis 故障时应 RESTART=0」写进 deploy.md §4 ② 补集成测试：deep 503 的 body 中 checks.redis 标记应让看门狗 hint 指向依赖方向而非杀进程（deploy.md 五步表第 1 步已区分 503/超时，脚本侧可复用该判据） |
| 8 | 审计链有两个洞：① 审计失败静默丢弃——record_audit_standalone 捕获一切异常仅 logger.error（audit_service.py:32-34），DB 抖动期间的高危操作（改密钥/删租户）可无痕通过，这是可用性取舍但**无补偿机制**（无重试队列/无落盘兜底）；② 防篡改为零——operation_log 是普通表（platform_core/models/operation_log.py），无 hash 链、无导出、无保留策略，DBA/入侵者可直接 UPDATE。正面确认：llm_providers 写操作 require_admin + 审计齐全（llm_providers.py:16） | major | backend/services/audit_service.py:30-34,63-66；platform_core/models/operation_log.py:7-17 | 分级处理：① 审计失败兜底改双写——DB 失败时追加写本地 JSONL 文件（与日志同权限），运维定期比对补录 ② operation_log 行加写入时 hash(prev_hash+payload) 链式校验列（迁移 + 一个校验脚本即可，不必上外部系统）③ 写明保留策略（如 180 天）并入备份范围 |
| 9 | 容量与成本模型缺位，但「谁最先到顶」可以从现有证据排出序：现 compose 总 limit ≈ 2.3GB（+litellm 512m = 2.8GB），deploy.md §6 自认 dev 量级、需峰值×1.5。按 5→100 客户的资源曲线（SaaS 多租户 + LLM 中转 + 爬虫库，product-review 口径）：**最先到顶 = MySQL 512m**（数据量 GB 级后 mysqldump/ALTER 的内存尖峰，compose 注释已自认 OOM 场景）；**第二 = Redis 256m**（队列 + 计数 + 无 maxmemory 策略 → noeviction 写错，fail-open 面静默放行）；**第三 = backend 单进程**（1 CPU + async pool 5+10，扩 workers 后 pool×N 撞 MySQL 默认 max_connections=151）。LiteLLM sidecar 增量：+512MB/1CPU、无 DB（静态模式无 Postgres）、连接增量为短连接两跳，**影子期绑 127.0.0.1 零生产流量**（设计克制，L2 接管时总内存预算 ~4GB 宿主）。成本文档零：无任何估算 | major | docker-compose.yml:19-21,45-48,60-64,115-118；deploy.md §6；platform_core/db.py:77,93；config/default/（无 mysql.yml，池参数未外置） | ① 把 compose limit 表 + 「到顶顺序 + 扩容动作」写进 deploy.md 新节「容量基线」（每级客户数对应的 limit 值，替代「×1.5」一句话）② pool 参数进 config/default/mysql.yml（一轮 #11 收尾）③ 100 客户前强制项：MySQL 出 compose（托管或独立机），这同时解决 F5 的单点 |
| 10 | 故障演练矩阵止步于两个进程级场景：已练（watchdog kill 9 秒闭环 / 024-025 迁移 up-down-up / 020 down 缺陷处置）都是「本进程/本 schema」故障；数据级（备份恢复 F1）、依赖级（Redis F7、MySQL F5）、拓扑级（爬虫节点 F6）三类全部未演练，且演练环境本身不存在（staging = 开发机）。另：logs 有上限（compose 10m×3 + app 100MB 轮转，logger.py:10-35）但轮转后旧文件**无保留上限**，mysql_data 卷增长无水位告警——磁盘满这个最经典的故障无探测 | minor | docs/ops/deploy.md §6（诚实清单）；platform_core/logger.py:10-35；docker-compose.yml（无磁盘探测） | 建立最小演练矩阵并排期（每季度一轮）：备份恢复 / Redis 宕 5min / 爬虫节点 kill / 磁盘 90% 注入（dd 占满演练盘）。磁盘水位进 watchdog 同款 webhook（df 探测 + 85% 告警 + 处理指引一行） |

## 运维最值得投资的五个方向（按杠杆排序）

1. **备份与恢复最小闭环**（F1+F3+F2 的数据面）：一个备份脚本 + 一个 cron + 一次真恢复演练 + 主密钥托管清单。这是把「尽力可用」变成「可承诺 RTO/RPO」的唯一路径，且成本是五个方向里最低的。
2. **镜像产物链**（F4）：CI push GHCR（git-<sha>）+ migrate.sh 三子命令 + smoke.sh。它同时解决一轮遗留的「容器级回滚实测」——有了可拉取的旧镜像，回滚演练在任意一台有 docker 的机器上 30 分钟内可完成。
3. **数据出单机**（F2+F5+F9）：MySQL 挪出 compose（托管起步）、Redis 加持久化或降级为纯缓存、月用量落 MySQL。这是 20→100 客户的硬前置，也是 F6/F7 演练有意义的前提。
4. **监控栈落地 + 资源告警**（一轮 P1-7 open 项）：watchdog 已验证的 webhook 通道直接复用，加三类探测——磁盘水位、容器 OOM/重启事件、Redis maxmemory；每条带 deploy.md §4 同款五步指引。监控栈就绪前不放大流量（deploy.md §6 已自我约束，保持）。
5. **staging 概念落到最便宜形态**（F10）：第二台机器或同机第二套 compose project（不同端口 + 独立卷），发布前在该环境跑「备份恢复 + 回滚 + 冒烟」三连。有它，F1/F4/F7 的演练才有可重复的场地。

## 给下游的交接

- /dba：月度用量事实源迁 MySQL 需要表设计评审（F2）；operation_log hash 链列是一个小迁移（F8）。
- /cicd：GHCR push job 与 smoke.sh 归 CI（F4）；check-db-migrations.sh 修复后 CI 五阶段已绿，无需动作。
- /pm：SLA 承诺前的前置清单 = 本报告 F1/F2/F4 三条 blocker/major 关闭；「用量数据可丢」若业务接受，F2 可降级为文档声明。
- 边界与不确定：①queued 任务丢失后的自动重派未见实现，F2 影响描述中「待人工」为代码走读推断，未实测；②容器重建后匿名卷更替的行为基于 Docker 官方 redis 镜像 VOLUME /data 声明 + compose 无显式卷推断，建议首次部署环境就绪时实测确认（与容器级回滚实测同场补做）。
