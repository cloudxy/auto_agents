# DBA 深层次审查报告 — 数据 10 倍、租户 10 倍之后哪里先坏

- 审查日期：2026-09-06
- 视角：增长动力学 / 租户数据物理分布 / 迁移链长期健康 / 备份恢复 / 完整性边界 / Redis 规模行为 / 时区精度一致性
- 方法：静态分析（迁移链 32 个文件、ORM 34 模型、repositories/services/consumer 查询代码）+ 本机 MySQL 8.0.42 只读验证（SHOW CREATE TABLE / information_schema / EXPLAIN）
- EXPLAIN 说明：本机为近空库，`rows` 列无规模意义；但 `type/key/Extra` 是访问路径的结构性结论（有无可用索引、是否 filesort），不随数据量改变，引用有效。
- 纪律声明：未阅读 .sdlc/、.scratch/、docs/plan/、docs/research/；未修改任何文件。

## 总体判断

这是一套"单机时代为爬虫闭环设计、刚 retrofit 上 SaaS 租户化"的数据层。单链迁移质量不低（019 孤儿归档可回滚、026 有真库 EXPLAIN 证据），但三股结构性欠账会在数据×10、租户×10 时先爆：(1) **租户维度从未进入复合索引设计**——全库唯一以 tenant_id 打头的复合索引只有 spider_tasks 一张，而 017 之后几乎每个查询都注入 `tenant_id = ?`，EXPLAIN 实证跨爬虫时间查询 filesort、按日聚合 temporary+filesort；(2) **最高增长表 spider_results 的每一行都要维护 7 个二级索引，其中两个是 012/019 各建的完全同列 (spider_name, created_at)——迁移链与 ORM 双事实源的漂移已不是风险而是生产 DDL 事实**，而它没有退役路径（INT 主键、归档表零执行器、配额按行数单调只涨）；(3) **Redis 数据面整体无界**——代理池两个 HASH 只增永不 hdel、task_results list 可膨胀到单 key 数百 MB 且读取端 `lrange 0 -1` 全量拉、死信与重试 ZSET 无上限，且实例无持久化、cgroup 256MB。另有无备份/恢复闭环、配额实时 COUNT 错配、去重竞态与跨租户语义分裂三个"现在没疼、十倍后致命"的暗雷。

---

## 深层次问题清单（按严重度排序）

### 1. 迁移链与 ORM 双事实源已经实锤漂移：最高写入表上存在两棵完全相同的二级索引
**严重度：高**

**证据**
- `backend/alembic/versions/012_add_spider_results_created_at_index.py:41-46` 建 `ix_spider_results_spider_created (spider_name, created_at)`；`backend/alembic/versions/019_soft_delete_audit_fk_upgrade.py:146` 又建 `ix_spider_results_name_created (spider_name, created_at)`。本机 SHOW CREATE TABLE 证实两个索引并存（另含 `ix_spider_results_id`——002:39 在 PRIMARY KEY 的 id 上再建单列索引，纯冗余）。
- `platform_core/models/mixins.py:14-20` 自己声明"create_all 与迁移链的此差异为已知豁免（基线对拍口径=列集）"；`backend/tests/conftest.py:251-253` 证实测试库走 `Base.metadata.create_all`、生产走迁移链——两套索引集，测试里的查询计划不能外推到生产。
- `026_index_governance.py` 的索引治理只覆盖 tenant_id/deleted_at/priority 类冗余，未做同列对全量去重；迁移文件命名混用数字序号与 4 个 UUID（8551b2c539b2 等）插在 007→008 之间。

**为什么深层**：spider_results 是全库写入速率最高的表，当前每行 insert 维护 7 个二级索引（task_id、spider_name、content_hash、created_at、tenant_id + 两个同列的 (spider_name, created_at)），其中两棵 B+ 树内容永远一致——纯写放大，且缓冲池被双份索引挤占。"对拍口径=列集"意味着索引层没有任何机制阻止下一次 012/019 式重复：ORM 加 `index=True`、迁移手写名字，两边永远可能再漂。这不是"加索引/删索引"问题，而是 schema 事实源治理缺失。

**解决方案**
1. 一次性去重迁移（expand 无需，contract 即可）：`ALTER TABLE spider_results DROP INDEX ix_spider_results_spider_created`（MySQL 8 INPLACE, LOCK=NONE），downgrade 重建——保留 ORM 同名者 `ix_spider_results_name_created` 以终结双源歧义。同时删 `ix_spider_results_id`（被 PK 覆盖）。取舍：drop 后若 ORM 侧改名会再次漂移，所以迁移文件注释必须声明"索引名以迁移链为准，ORM index=True 仅为声明"。
2. 建立门禁：CI 中对空库分别执行 `alembic upgrade head` 与 `create_all`，用 information_schema 对拍**索引集**（名称+列序），不一致即失败——把 mixins.py 里"已知豁免"变成显式白名单。这是低成本方案；彻底方案是 alembic autogenerate 单事实源，但迁移链已 32 个节点，改造成本高，可后置。
3. 约定新迁移命名 = `NNN_描述`（递增序号），禁止再插入 UUID 名。

### 2. 备份/恢复/容量面：零备份闭环、零恢复演练，容量上限埋在 compose 注释里
**严重度：高**

**证据**
- `docker-compose.yml`：mysql_data 单卷；MySQL cgroup 512MB（注释自认"跑大迁移 OOM-kill 时上调"）；Redis 256MB；`redis-server --requirepass 123456` 无 appendonly/RDB 参数（**无持久化，重启全丢**）。
- `scripts/` 全目录无 backup/mysqldump/xtrabackup 字样；`.github/` 无备份 job。本机 MySQL 虽 `log_bin=1`（binlog_expire 7 天），compose 容器未显式配置且无任何消费方——PITR 原料存在但无人使用。
- Redis 无 `maxmemory` 配置 + cgroup 硬限：写满即 OOM-kill，队列内任务/结果消息、限流计数、代理池评分全灭，且无恢复手段。

**为什么深层**：spider_results/operation_logs 这类 append-only 表 + 无 binlog 备份消费 = RPO 无穷大；MySQL 8 在 512MB cgroup 下 buffer_pool 缺省 128MB，10 倍数据后热数据全走磁盘；更重要的是**恢复能力从未被演练**——第一次真正需要 restore 的时刻，会同时发现没有备份、没有恢复步骤、没有验证过 restore 的库与迁移链/ORM 兼容。这是数据面最大的单点，且修复成本最低。

**解决方案**
1. 加 `deploy/backup/backup-mysql.sh`：`mysqldump --single-transaction --set-gtid-purged=OFF --routines` 每日全量 + `--source-binlog` 实时 binlog 复制到对象存储/远端卷；compose 挂 cron 或 sidecar。取舍：dump 恢复慢但零运维，若行数上亿再换 XtraBackup/clone plugin。
2. Redis 加 `--appendonly yes --appendfsync everysec --maxmemory 200mb --maxmemory-policy noeviction`（队列类数据宁可拒绝不可静默淘汰；限流/评分这类可丢的与队列数据分 db 评估 policy）。
3. 每季度一次恢复演练（restore 到临时容器 → `alembic upgrade head` → 冒烟查询），脚本化进 `scripts/`。
4. 容量告警：对 information_schema 的 data_length、Redis `used_memory/maxmemory`、磁盘水位做 /health/deep 附带上报。

### 3. Redis 数据面整体无界：只增不减的 HASH/LIST/ZSET + 全量读模式 + 无持久化
**严重度：高**

**证据**
- 代理池：`platform_core/queues.py:78-80` 定义 `spider:proxy:scores`/`spider:proxy:stats` 两个 HASH；全仓 grep 无任何 `hdel`——代理失效后永久留存。`scrapy/middlewares/__init__.py:212` 每次选代理 `hgetall(PROXY_SCORES_KEY)` 全量；`backend/services/proxy_health_service.py:111,197-198` 巡检时两个 HASH 各 hgetall。公共代理池场景每天进几百~几千新 IP，1 年 = 数十万成员、每成员一条 JSON stats——单 key 可到数百 MB，且每个爬虫请求都全量拉。
- 结果缓存：`queues.py:61` `spider:task_results:{task_id}` list，`consumer.py:728-732` 每批 rpush+expire（TTL 7 天滑动）；大任务产 50 万条时单 key ~500MB。读取端 `spider_task_service.py:647` `lrange(key, 0, -1)` 一次性全量拉到内存组装 CSV。
- 死信：`queues.py:44` `spider:item_dead` 注释明说"无 TTL"；`dead_item_service.py` 只读不清理，无上限、无轮转。
- 重试：`spider_task_service.py:561` / `consumer.py:389` RETRY_ZSET 以**完整消息 JSON 作 member**，无 TTL 无总量上限；毒丸消息（task_id 合法但处理恒失败）会无限 1s→5s→15s 循环重投，永不入死信。

**为什么深层**：共性是**把 Redis 当无界存储 + 全量集合读**。Redis 数据结构的成本模型（单线程 O(N) 命令、cgroup 内存硬限）决定了：hgetall/lrange 全量在成员数线性增长时，延迟与内存同步线性恶化，最终表现为 Redis 单点拖垮整个采集链路（所有队列都在同一个实例）。叠加问题 2 的"无持久化+无 maxmemory"，OOM 后连降级读 DB 的兜底都没有。

**解决方案**
1. 代理池改 ZSET（member=proxy, score=健康分）+ 每轮巡检 `zremrangebyscore 0 0.1`（或长期未检活成员 HDEL）；scraper 侧选代理改 `zrangebyscore` 取 top-N 而非 hgetall。迁移路径：新键双写→切换→删旧键（Redis 键无 schema 迁移成本，直接上线即可，旧键设 TTL 自然过期）。
2. task_results：写侧每批后 `LTRIM key -N -1`（保留最近 N=10 万或按任务结果上限）；读取端改 `lrange` 分批循环或直接改读 DB（DB 已有全部数据，Redis 只是镜像——csv 落盘场景建议直接走 `iter_by_task` DB 流式，与现有 EXPORT_BATCH_SIZE=5000 先例一致）。
3. 死信队列：上限 + `LTRIM`，或给键设 30 天 TTL + 落库留档（已有一条 DB 留档路径即可）。
4. 重试 ZSET：`zcard` 超阈值告警；重试次数超限的消息转 `spider:item_dead`；member 只存消息 ID、payload 留 DB/Hash。
5. 每个新键登记 TTL/淘汰策略到 `queues.py` 注释契约（该文件已有此文化，补齐缺口即可）。

### 4. spider_results 增长无退役路径：INT 主键 + 归档机制零接线 + 配额行数永不释放
**严重度：高**

**证据**
- 全库 40 个 `primary_key=True` 均为 `Integer`（`grep platform_core/models` 统计），无一处 BigInteger 主键；spider_results.id、task_id、channel_events.id 全部 INT（上限 21.4 亿）。
- `platform_core/models/archive.py` 定义了归档快照表（docstring 自述"spider_results 等增长表的冷热分离"），但 backend/services、backend/tasks 中 **ArchiveRecord 零引用——归档没有执行器**，冷热分离是空架子。
- `quota_service.py:100-117` 配额按"租户 spider_results 行数"计，而全仓无任何针对 spider_results 的物理删除调度（仅 task 删除时 `delete_by_task` 级联）——配额消耗单调只涨，免费租户到 1 万行后永久 429，且计数成本随行数上涨（见问题 6）。
- 行宽：title/content/extra 三个 TEXT 与主表同体，列表查询 `query_by_spider`（spider_result_repository.py:191-206）逐行携带 content 大字段返回。

**为什么深层**：增长表的寿命 = min(PK 溢出时间, 运维容忍的表体积)。当前三道防线（BIGINT、归档、配额回收）一道都没有，而三者的改造成本都随行数超线性上升：PK 改型牵动全部 FK（task_id 等），归档接线要补"删除不影响 result_count 语义"的口径，越晚越贵。10 倍增长下（例如 3 租户×10 万条/日×10 = 30 万条/日），**约 2 年逼近 INT 上限**；表体积上亿行后 buffer pool（问题 2 的 128MB/512MB 环境）完全无法容纳热索引。

**解决方案**
1. PK 改型走 expand-contract 三迁移：① 新列 `id BIGINT UNSIGNED`（或先新增 `id_bigint` 双写）；② backfill + FK 列同步改型（gh-ost/INPLACE，低峰执行，迁移注释记录表体积与预估时长——012 已有此注释文化）；③ 切换收旧列。若近期启动成本过高，最低限度：**立即停止在新表上用 Integer PK**（channel_events/channel_probe_results 等新表先 BIGINT 化），存量 spider_results 单独立项。
2. 归档接线：加 `backend/tasks/archiver.py` 定时任务（复用 schedule/锁设施），按 `(tenant_id, created_at < 保留窗)` 游标批量（每批 5000，同 iter_by_task 模式）写入 archive_records.snapshot 后物理删除 spider_results 行，同步扣减问题 6 的配额计数。取舍：软删除语义改为"归档即离场"，回收站需求由 archive_records 承接；`retention_until` 字段现成，顺带解决快照的二级 TTL。
3. 列表接口停拉 content：`query_by_spider` 的 items 不返回 content（详情页单条再取），即可用 `(tenant_id, spider_name, created_at)` 覆盖索引承接列表页（与问题 5 合并实施）。

### 5. 租户维度从未进入索引设计：SaaS 化是 retrofit，索引还是单机时代的形状
**严重度：中高**

**证据**
- EXPLAIN（本机，结构结论可信）：
  - 跨爬虫+时间+租户查询（`query_by_spider` spider_name=None 时注入租户后的形态）：`type=ref key=ix_spider_results_tenant_id Extra=Using where; Using filesort`——走单列租户索引后回表全租户行，再 filesort；
  - 按日聚合（`daily_result_counts` 注入租户后）：`Using temporary; Using filesort`。
- 全库以 tenant_id 打头的复合索引仅 `ix_spider_tasks_tenant_status_priority` 一张（026:108）；spider_results 的索引全部以业务维度为先（spider_name、content_hash、task_id），tenant_id 只有单列（017:78 建，026 保留）。
- `daily_result_counts`、`check_result_storage`、`usage_by_member` 等全部依赖"tenant_id 单列索引 + 回表"。

**为什么深层**：017 把 tenant_id 以"加一列+加一个单列索引"的方式 retrofit 进 9 张表，而真实访问模式 100% 是 `tenant_id + <业务维度>` 复合条件。租户×10 之后，单列 tenant_id 索引的选择性不变（还是等值），但**每次等值命中后的回表行数 = 该租户全部行数**——即查询成本从 O(库) 变成 O(租户)，看着隔离了，实际复杂度没变。filesort/temporary 出现的位置（列表排序、按日聚合）正是管理端最高频页面。

**解决方案**
1. 对 spider_results 建 `(tenant_id, created_at)`（承接 daily_result_counts 的范围聚合与跨爬虫时间列表，消除 filesort）与 `(tenant_id, spider_name, created_at)`（承接数据中心按爬虫页，同时顶替两个重复索引——与问题 1 的去重合并为一次迁移）；新索引建立后 drop 单列 tenant_id 索引（被最左前缀覆盖，026 同一处置逻辑）。均 INPLACE。
2. 将"ESR + tenant_id 最左"写进 `/new-model` skill 的索引规约（项目已有 026 的 ESR 先例，缺的是租户维度这一条），并要求 db-spec Top-N 模式全部以注入租户后的最终 SQL 形态书写（现在的模式描述漏掉了 do_orm_execute 注入这一层）。
3. 取舍说明：每张表多 1 个租户前缀索引 = 每行写放大 +1。对 spider_results 值得（读频最高）；对 llm_token_usage 这类已有 uq (tenant_id, ...) 唯一键覆盖的表不必再加。

### 6. 配额与用量 = O(租户行数) 的实时 COUNT：检查成本随业务增长单调上升
**严重度：中高**

**证据**
- `quota_service.py:104-111`：`check_result_storage` 每次 miss（60s TTL 缓存，`_COUNT_CACHE_TTL=60`）执行 `COUNT(*) WHERE tenant_id=?` 全租户扫描；写入路径（consumer.py:694）每个回流批次都触发。
- `quota_service.py:124-128`：`check_llm_tokens_month` 用 `CAST(stat_date AS CHAR) LIKE '2026-09%'`——函数包裹列的反模式（EXPLAIN E：uq 前缀 ICP 命中，日聚合表行数尚可控，但语义上应走范围条件）；`usage_overview:172-176` 同样全租户 COUNT。
- 配额结果不随删除/归档联动（问题 4），计数只涨不跌。

**为什么深层**：用实时 COUNT 做"资源水位"是把 O(行数) 的计算挂在了写入热路径上。缓存只是把常数砍成 1/60，未改变复杂度；租户×10（每个租户一个 `quota:count:results:{tid}` 缓存键 + miss 时一次全租户 COUNT）后，DB 每分钟要承受 10 倍个"全租户 COUNT"。结构性修法是**把水位从查询变成维护量**（计数器），这同时解决归档回收的扣减问题——COUNT 无法扣减，计数器可以。

**解决方案**
1. tenants 表加冗余计数列 `result_count BIGINT DEFAULT 0`（与行同事务 INCR/DECR，归档任务 DECR），配额检查读列值；每日低峰 `COUNT(*)` 对账任务修正漂移（方法论"summary field + periodic reconciliation"标准配方）。取舍：列值有短暂漂移窗口，对配额这种容忍 60s 滞后的语义无害。
2. `check_llm_tokens_month` 改 `stat_date >= :month_start AND stat_date < :next_month`（uq_llm_usage_dim 前缀命中，range 可 sargable），顺带把月累计也换成日聚合行的轻量 SUM（行数 = 租户×provider×模型×31 天，天然有界，保留 SUM 合理）。
3. `usage_by_member`/`usage_overview` 属低频看板，可接受租户内聚合，但应加 60s 缓存与超时，避免看板成为 DDoS 面。

### 7. 增量去重的完整性边界：无 DB 约束兜底 + 两条路径租户语义分裂 + 软删行挡新数据
**严重度：中高**

**证据**
- 写入端只有"先查后插"：`consumer.py:653-655`（批量路径带 tenant_id）与 `consumer.py:771-772`（兼容单条路径 `_ingest`，`find_by_content_hash(content_hash)` **不带 tenant_id**——跨租户全库查重：A 租户采过的内容会静默吞掉 B 租户的增量结果，数据正确性问题）。
- `spider_result_repository.py:121-129`：查重无 `deleted_at IS NULL` 过滤——已软删的行会永久挡住同内容的重新采集；且 content_hash 只有单列索引，无 UNIQUE(tenant_id, content_hash) 兜底，并发消费/flush 重试窗口内重复行可插入（consumer.py:595-607 的幂等修正只覆盖同批次）。
- md5(url+title+content)（consumer.py:647-649）不含 tenant 维度，跨租户 hash 相同——依赖查询侧带租户条件，但 772 行恰恰没带。

**为什么深层**：唯一性是数据库约束的事，"先查后插"在并发下永远存在 TOCTOU；而多租户改造后同一条业务规则在两条代码路径中出现两种语义（一租户感知、一全库），正是 retrofit 系统的典型完整性裂缝——它不是慢，是**错**，且静默（吞数据只打 debug 日志）。

**解决方案**
1. 唯一约束兜底：`(tenant_id, content_hash)` 唯一索引。软删复用冲突的处理取舍：spider_results 的软删行会占住唯一键——建议该表**不做软删除**（采集结果属"子表/历史数据"豁免类，符合项目自己的豁免矩阵逻辑；恢复需求由 archive_records 承接），或软删时将 content_hash 置 NULL 保留原值进 extra。存量重复行先跑对账清理（GROUP BY 找重，保留最新）再建唯一索引（建失败即说明有脏数据，天然的对账闸门）。
2. 统一去重入口：删除 `_ingest` 旧路径或将其收敛为调用 `_flush_batch([msg])`，消灭 772 行的全库查重语义；`find_by_content_hash` 强制 tenant_id 参数（None 抛错）并补 `deleted_at IS NULL`。
3. 插入侧捕获 IntegrityError 计入去重日志，把"查了再插"降级为快路径优化、约束为最终防线。

### 8. 平台态后台查询在全库索引计划外：状态机扫描只能 PRIMARY 全序扫 + 隔离上下文 fail-open
**严重度：中**

**证据**
- EXPLAIN B：`find_stale_running`（spider_task_repository.py:160-173，`WHERE status='running' AND started_at < cutoff`）`type=index key=PRIMARY`——唯一 (tenant_id,status,priority) 复合索引最左是 tenant_id，platform 态（无租户注入，`tenant_context.py:34,95-97` 后台组件/定时器不落 tenant_scope）时完全不可用，优化器退化为 PK 全索引序扫 + where 过滤；`find_stale_pending` 同构。
- `tenant_context.py:7-8,122-124`：无上下文 = 不过滤不断言（fail-open），安全性靠"真实请求必经中间件 + R13 越权套件"两个应用层纪律；任何新写的后台脚本/CLI 若忘记 `platform_scope()` 或 `tenant_scope()`，读侧注入与写侧断言同时失效。

**为什么深层**：026 的 ESR 治理覆盖的是"租户态 API 模式"，而**平台态后台模式（超时回收、积压对账、巡检）从未进过 Top-N 访问模式清单**——这类查询无租户前缀，全库所有复合索引对它失效。任务表×10 后，每次超时回收循环都是百万行级全序扫描，且与业务写入抢 buffer pool。fail-open 则是同根的另一半：平台态没有一等公民的显式契约，只能靠"记得声明上下文"。

**解决方案**
1. 补平台态扫描索引：`spider_tasks (status, started_at)`（pending 用 (status, created_at) 或统一 (status, started_at) 加 `started_at IS NULL` 语义统一）；status 基数=4 但第二列 range 使其成为正确的 ESR 组合（等值+范围），且这是有明确访问模式的 Top-N 后台模式。INPLACE 迁移，up/down 成对。
2. 把"平台态后台查询"列为 db-spec Top-N 的一等模式类别（与租户态并列），凡 platform_scope 下执行的循环查询必须出现在模式清单里。
3. fail-open 收口（低成本高收益）：在 DBManager 的 async session 工厂（db.py:152-160）加一行守卫日志/断言——`mode=none` 且非 pytest 环境时记 WARN（保留兼容但可观测），让"忘声明上下文"从静默变成监控事件；中期把脚本入口统一包上 `platform_scope()`。

### 9. 分页协议 = OFFSET 页码 + 每请求精确 COUNT：深翻页与全表 LIKE COUNT 是协议内建成本
**严重度：中**

**证据**
- `spider_result_repository.py:171-187`：keyword 检索护栏（KEYWORD_SEARCH_MAX_ROWS=200）只限制**取数窗口**，注释自认"total 仍为真实计数"——每次翻页请求的 COUNT 仍是对 title/url/content 三列 LIKE '%kw%' 的全表扫描（EXPLAIN A：type=ALL）。非 keyword 分支无任何护栏，OFFSET 深翻照扫。
- `platform_core/repository.py:39-46`：`get_all(skip, limit)` OFFSET 分页且**无 ORDER BY**——MySQL 下无稳定序，翻页可重复/漏行。
- `operation_log_repository.py`：同 OFFSET+COUNT 模式，action/actor_name/时间任意组合过滤，审计表 append-only 只涨。
- 已有正例：`iter_by_task`（id 游标）、`list_tasks`（id 排序），说明游标协议在团队内已被接受过。

**为什么深层**：OFFSET 分页的成本 O(offset) 是协议固有的；而"必须返回精确 total"的前端契约迫使每页都付一次全量 COUNT——keyword 场景下这次 COUNT 是全表 LIKE，护栏救了取数救不了计数。数据×10 后，数据中心搜索页的每次翻页 = 一次全表三列扫描，比取数本身贵 100 倍。这不是缺索引能救的（前导通配符 LIKE 无索引可走），是**检索协议**错配。

**解决方案**
1. keyword 检索改 FULLTEXT（MySQL 8 内置 ngram 分词器适配中文）：`ALTER TABLE spider_results ADD FULLTEXT ft_result_text (title, content) WITH PARSER ngram`（INPLACE），repository 改 `MATCH...AGAINST`；url 前缀搜索改 `LIKE 'kw%'` 命中现有索引。取舍：FULLTEXT 不支持任意子串，需产品侧确认"词搜索"可接受；不可接受则引入 ES/Meilisearch（当前规模可先不上）。
2. total 协议改三档：keyword 场景返回估算值（EXPLAIN rows 或采样 COUNT）+ "结果超过 N 截断"文案；管理列表场景保留精确 COUNT 但加 5s 结果缓存；游标场景（导出/日志）彻底去 total。
3. `BaseRepository.get_all` 强制 `order_by(模型.id.desc())` 缺省（现有调用方多为"最新优先"语义，改动无行为损失），并为列表接口统一切 `WHERE id < :cursor` 游标参数（API 层兼容：有 page 参数走旧路径，有 cursor 走新路径，双轨一个版本后下线 page）。

### 10. 时区与精度的一致性：CST 本地时间落盘 + timezone=True 的假象 + 无小数秒
**严重度：中低**

**证据**
- 本机 `@@time_zone=SYSTEM, @@system_time_zone=CST`（+08:00）；全库列类型为 DATETIME（无时区语义），`DateTime(timezone=True)`（mixins.py:37、spider_result.py:30 等）在 MySQL 驱动上不产生任何 UTC 转换——存的是**服务器本地时间**，注释里"NULL=平台级"之外的时间语义（UTC）从未成立。
- `func.now()`（server_default，DB 侧 CST）与 Python `onupdate=func.now()`（spider_task.py:44，SQL 表达式仍是 DB 端，但部分服务层传 Python datetime 的是客户端时钟）混用；`system_configs.updated_at` 曾因 Python utcnow 漂移在 019 修过一次（019:23-24），说明该坑已咬过。
- 所有 DATETIME 无小数秒：同秒内 result_count 累加、审计、状态流转的时间戳排序歧义。
- compose 未设 TZ，容器与宿主机/本机（CST）之间迁移部署时，同一列的"本地时间"基准会漂移。

**为什么深层**：时区坑平时不可见（全栈同机器），第一次跨机部署/跨时区客户端/DST 类事件时以"时间平移 8 小时"的形式整体爆发，且**无法事后修复**（已落盘的本地时间分不清是哪个基准）。归档 `retention_until`、租户 `expires_at`（到期降级判定）这类"时间阈值驱动的业务语义"受影响最大——到期判定偏差会直接影响计费公平性。

**解决方案**
1. 定基准：会话级固定 UTC——在 db.py 两个连接 URL 加 `init_command`（或引擎 `connect_args`）执行 `SET time_zone='+00:00'`，同时容器设 `TZ=UTC`，全链路（DB/应用/日志）UTC 落盘、展示层转租户时区。这是单次配置收口，不改列类型。
2. 精度：新列统一 `DATETIME(3)`；存量列不动（毫秒缺失无害，改型收益低）。软删/审计等已用 timezone=True 的列删除该参数避免假象（MySQL 方言下无操作，纯注释性清理）。
3. 若未来引入跨区部署再评估 TIMESTAMP(3)（带转换语义但有 2038 与隐式转换坑）；当前"UTC 约定 + DATETIME(3)"是方法论文档推荐的最稳组合。迁移路径：纯配置变更 + 一次重启，无数据改写——但必须在**数据量还小、无需 double-write 存量列**的现在做。

---

## 交接说明（给下游 /architect、/backend、/sre）

- **立刻可做（低成本高杠杆）**：#2 备份脚本与 Redis 持久化；#1 去重索引迁移；#7 的 `_ingest` 路径收敛；#8 的 (status, started_at) 索引。
- **需立项（expand-contract 三迁移）**：#4 BIGINT 主键链、归档执行器；#5 租户前缀复合索引（可与 #1 合并为一次 spider_results 迁移）；#6 计数器化。
- **产品/前端联动**：#9 的 total 协议（估算/游标）需前端配合改分页交互；#10 的 UTC 基准需全栈统一。
- 验证口径：本报告 EXPLAIN 基于近空库，#1/#5/#8 三个索引迁移上线前后应分别在预发灌量（≥百万行 spider_results）后复跑 EXPLAIN 留档。
