# Backend 深层次问题审查（独立审查 · 2026-09-06）

审查范围：backend/ + platform_core/ + config/ + 测试（未读 .sdlc/.scratch/docs/plan 等）。
透镜：真实生产流量下这段代码会怎么坏。

## 总体判断

这是一个明显经过多轮评审打磨的代码库：分布式锁（token+Lua 原子释放/续期）、bcrypt 转线程池、LLM 故障转移、条件 UPDATE 抢断（AI 计划）、后台副作用脱 ORM 快照等深坑都已被系统性填过。但整条"Redis 队列 ↔ DB"数据闭环仍有两个结构性缺陷：**批量 ingest 无逐条错误隔离（毒消息使整条回流管线永久卡死并丢数据）**，以及**队列消息格式在写入侧与编辑侧不一致（任务编辑对队列永远不生效，DB 与实际执行内容静默漂移）**。此外幂等语义只覆盖了部分写路径（AI 计划用条件 UPDATE，爬虫任务终态/分发仍是 check-then-act），租户级 LLM 预算的读写键错位使租户配额形同虚设。这些问题的共性是：**单测都绿（测试把错误契约固化了），只有多副本/慢响应/异常注入的生产条件下才暴露**。

## 深层次问题清单（按严重度）

### 1. 批量 ingest 无逐条错误隔离：一条毒消息让整条结果回流管线永久卡死
- 严重度：高
- 证据：`backend/tasks/consumer.py:551-578`（flush 异常被捕获但 `batch`/`batch_counts` 未清空，下一轮带着毒消息继续重试）；`backend/tasks/consumer.py:689-694`（`QuotaService.check_result_storage` 对租户超额直接抛 `QuotaExceededException`，整批拒绝）；`platform_core/models/spider_result.py:19-20`（`task_id` FK NOT NULL，`_flush_batch` 不校验任务存在即建实例）；`backend/services/quota_service.py:49-67`（配额计数 60s 缓存还会放大允许超额写入的窗口）。
- 为什么深层：三条独立触发源汇聚到同一个结构缺陷——flush 是"全批单事务、失败整批留在内存重试"：租户结果存储超限（429）、任务在队列滞留期间被 `delete_task` 物理删除（FK IntegrityError）、DB 抖动，任一发生都会让 flush 永远失败。消息已从 Redis lpop 弹出，卡在进程内存中且每轮继续追加新消息：**内存无界增长 + 全部租户的结果落库停摆**，重启后内存批次直接丢失（静默数据丢失）。配额检查本身是 check-then-act（查缓存→判→插），且错误按"批"而非按"条"归责，把一个租户的配额问题放大成全平台事故。
- 解决方案：
  1. flush 改为**分段提交 + 逐条归责**：flush 失败时对批次做二分或逐条重放，失败的单条转入 `spider:item_dead` 死信队列（该队列已存在，`platform_core/queues.py:44`），成功部分照常提交；最小改动是在 `_ingest_loop` 的 except 分支先 `batch.clear()` 并把整批 rpush 回死信队列（保可用、放弃单条精度）。
  2. 配额检查移出事务路径：入库前查 Redis 预估计数（O(1)），超限时只丢**本租户**的消息进死信并告警，不再抛异常炸整批；精确行数由 flush 后的定期对账兜底。
  3. `_flush_batch` 对 `task is None` 的消息直接进死信而不是继续建实例（`consumer.py:617-624`）。
  取舍：逐条归责牺牲少量吞吐（正常路径仍是批量 commit）；死信队列需要配套排查/重放入口，否则只是把"静默丢"变成"存着没人看"。

### 2. 任务编辑的队列搬迁消息格式与 enqueue 不一致：LREM 恒未命中，编辑静默失效
- 严重度：高
- 证据：`backend/services/spider_task_service.py:202-206`（enqueue 消息 = `{task_id, spider_name, params, tenant_id}` 四键，**恒含** `tenant_id` 即使为 null）；`spider_task_service.py:263-270`（update_task 构造的 old/new 消息只有三键）；`spider_task_service.py:306`（`lrem(from_queue, 1, old_message)` 精确成员匹配）；`backend/tests/test_spider_datacenter_crud.py:383-392`（测试用同一错误的三键格式构造断言，把 bug 固化成了"正确行为"）。
- 为什么深层：LREM 要求字符串逐字节相等。enqueue 写进队列的消息永远带 `tenant_id` 字段，update_task 拼的旧消息永远不带——所以对**所有**经 enqueue 入队的任务，LREM 100% 未命中，随后落入"未命中=可能已被消费，不动队列"分支。结果：用户编辑 pending 任务的 params/priority，DB 更新成功、API 返回成功，但队列里还是旧消息；consumer 分发时用**队列消息里的旧 params** 取 start URL（`consumer.py:295-302`），执行内容与 DB 行永久漂移；优先级调整也静默无效。这是典型的"两侧各写各的消息构造器、没有共享的序列化函数 + 测试断言复制了实现"造成契约漂移。
- 解决方案：抽一个模块级 `build_task_message(task_id, spider_name, params, tenant_id=None, priority=None) -> str`，enqueue / update_task / `_reenqueue` / `_requeue_stale_pending` 四处统一调用（消息字段差异用显式参数表达）；加一条**集成级**回归测试：真实 enqueue 后立即 update_task，断言 LREM 命中 1（现有测试是 mock redis，测不出格式不匹配）。取舍：改消息格式需考虑队列中存量旧消息——上线初期 LREM 需同时尝试新旧两种格式，或清空队列发布。

### 3. 任务终态/分发幂等不完整：失败回调重试风暴会让任务被双重执行
- 严重度：高
- 证据：`backend/services/spider_task_service.py:416-446`（finish_task 先 `get_by_id` 读状态再分支，check-then-act；**failed→pending 重试分支无终态守卫**，重入即再 +1 retry_count 并再次 ZADD）；`backend/tasks/consumer.py:266-272`（`_dispatch` 无条件 `update(status="running")`，不校验当前状态，重复消息=重复投递 start URL）；`scrapy/extensions/__init__.py:104-118`（Scrapy 侧 webhook 失败重试 3 次、间隔 2s，Backend 慢响应>10s 即重发）；对照组：`backend/repositories/ai_plan_repository.py:47-68`（同库的 AI 计划已用条件 UPDATE 原子抢断，说明正确范式在库内已有但未推广）。
- 为什么深层：幂等守卫只挡"已终态再回调"，挡不住两个窗口：(a) 第一个 failed 回调已把任务置 pending 进重试 ZSET，Scrapy 因超时重发的第二个回调读到 pending → 再走一次重试分支 → ZSET 里两条消息；(b) ZSET 到期重投 + `_requeue_stale_pending` 对账重投（多副本各自计数，见问题 6）产生的重复消息，`_dispatch` 无条件置 running 并 rpush start URLs → **同任务两份 URL 同时被爬**，结果翻倍、result_count 虚增、双倍 webhook。时钟偏移窗口（`webhooks.py:43-45` 允许 ±300s）内重放 failed 回调同样命中窗口 (a)。这是"恰好一次执行"缺失的通用问题，重试预算（SPIDER_MAX_RETRIES）也会被重复回调白耗。
- 解决方案：① finish_task 重试分支改为条件 UPDATE：`UPDATE spider_tasks SET status='pending', retry_count=retry_count+1 WHERE id=:id AND status='running'`，rowcount=0 直接返回当前快照（对齐 ai_planner 的 claim_status 范式）；② `_dispatch` 置 running 同样加 `WHERE status='pending'` 守卫，rowcount=0 视为重复消息丢弃（终态推进才允许无条件写）；③ 终态分支（448-456）同样收口为 `WHERE status NOT IN ('completed','failed')`。取舍：条件 UPDATE 让"读旧值再决定副作用"变成"写成功才做副作用"，需要把 snapshot 提取移到 update 之后（用 RETURNING 或 update 后二次读），改动集中在一个文件。

### 4. 租户级 LLM 月度预算读数键错位：所有租户共享一个全局桶，配额函数是死代码
- 严重度：高
- 证据：`backend/services/llm_usage_service.py:100-103`（record_usage 写月度 hash 的 field 是 `{dim}|total`，**无租户段**）；`llm_usage_service.py:118-123`（get_month_used 先读 `{tkey}|{dim}|total`——这个 field 从来没人写过——未命中回退读全局 `{dim}|total`）；`backend/services/ai_planner/llm_client.py:320-334`（熔断判断用这个错位读数）；`backend/services/quota_service.py:119-135`（`check_llm_tokens_month` 是全库唯一按租户算月度用量的函数，grep 全库无任何调用方，纯死代码）；日粒度键倒是带了租户段（`llm_usage_service.py:94-99` 四段 field），说明月度键是遗漏而非设计。
- 为什么深层：结果是双重失效——租户 A 的重消耗会把共享桶打满，租户 B 的合法调用被熔断（429 文案还指着自己的配额说超了）；反向地，只要全局桶没满，单租户可以无限超出自己的 `llm_tokens_month`。而真正按租户聚合的 DB 表（`llm_token_usage`，唯一键含 tenant_id，`platform_core/models/llm_token_usage.py:22`）只在 flush 周期后才有数据，调用时点不用它。熔断这个"成本防线"在多租户语义下基本失真，且 fail-closed 开关（`LLM.BUDGET_FAIL_CLOSED`）只是把一个错的数据变成硬失败。
- 解决方案：record_usage 月度 field 改为 `{tkey}|{dim}|total`（与读取方、与日粒度四段风格对齐），保留对旧两段 field 的读取兼容一个版本周期；同时把 `check_llm_tokens_month` 接入 llm_chat 调用前检查（或删除并注明由 Redis 计数承担）。取舍：改 field 会使上线当月已累计的旧口径用量读不到（预算短暂归零，宁可低估一个月也不双计）；多副本下 Redis INCRBY 本身是原子的，无需引入额外一致性机制。

### 5. AI 计划 tenant_id 恒 NULL：租户用户创建必 500、平台建的行租户用户永不可见
- 严重度：中
- 证据：`backend/services/ai_planner/orchestrator.py:63-69`（create_plan 未传 tenant_id）；`platform_core/models/ai_plan.py:27`（AiPlan 继承 TenantMixin，tenant_id 默认 NULL）；`platform_core/tenant_context.py:120-131`（tenant_scope 下 before_flush 断言 `obj.tenant_id != 当前租户` 即抛 ValueError）；`backend/app/api/v1/ai.py:36-47`（require_operator 放行租户 operator）；`backend/app/api/v1/ai.py` 及 test_ai_planner.py 均无租户态用例。
- 为什么深层：租户用户（role=operator 即可）POST /ai/plans → 中间件进 tenant_scope → 落库断言 `None != tenant_id` 抛 ValueError → 500（错误分类还错了，应为 4xx）；平台管理员创建的行 tenant_id=NULL，租户用户的读注入是 `col == tenant_id`，NULL 行不可见 → 同一模块两类角色互相看不见对方数据且没有一方能正常协作。全链路无测试覆盖，说明该模块在 SaaS 接线时被遗漏（对比：spiders/tasks.py:66 的 enqueue 已正确传 tenant_id）。同构风险存在于所有"TenantMixin + 忘传 tenant_id + require_* 放行租户角色"的组合。
- 解决方案：短期——AI 计划端点收口为 `require_platform_admin`（模块当前事实上是平台域语义）；中期——在 `BaseRepository.create` 统一兜底：TenantMixin 模型且 kwargs 未显式给 tenant_id 时自动填充 `current_tenant_id()`，让断言从"报错"升级为"自动归因"，platform_scope 下保持 NULL。取舍：仓库级自动填充改变"显式传参"惯例，需要在 R13/check-arch 加一条"TenantMixin 写路径必须带 tenant_id 或声明平台域"的机械检查防再次遗漏。

### 6. 多副本部署下 stale-pending 对账重投会重复投递：计数器是进程内存且无分布式锁
- 严重度：中
- 证据：`backend/tasks/consumer.py:469-512`（`_requeued_counts` 是实例字典，`_MAX_RECOVER..._ATTEMPTS=2` 按进程计；`_recover_loop` 无分布式锁，与 `_scan_retry_zset` 的 zrem 抢占形成对比——注释自己写明"zrem 原子抢占：多实例部署时同一到期成员只被一个消费者搬走"）；`consumer.py:266-272` dispatch 无状态守卫（叠加问题 3）。
- 为什么深层：N 个副本各跑一个 `_recover_loop`，同一 pending 任务被每个副本独立 rpush 一次（每副本最多 2 次）→ 队列里 N×2 条同任务消息 → 全部被消费执行（dispatch 无幂等）。单实例语义下这是精心的自愈设计，多副本下变成放大器。代码库已有 `distributed_lock` 共享设施（`platform_core/queues.py:202-239`）且其它 tick 循环都在用，唯独这条对账路径漏了。
- 解决方案：`_recover_stale_once`/`_requeue_stale_pending` 外层包 `distributed_lock(redis, "spider:stale-recover:lock", ttl=..., renewal=...)`；重投计数从进程内存迁到 Redis（`INCR spider:requeue_cnt:{task_id}` + EXPIRE，或复用重试 ZSET 语义），消除副本间不一致。取舍：锁把对账串行化（本就是低频后台任务，可接受）；Redis 计数键需要 TTL 防永生。

### 7. 时间基准混用：应用本地 naive datetime 直接与 DB `func.now()` 写入的时间列比较
- 严重度：中
- 证据：`backend/tasks/consumer.py:442,477`（`cutoff = datetime.now() - timedelta(...)`，naive 本地时间）；`consumer.py:268`（`started_at=func.now()` = DB 服务器时间）；`backend/repositories/spider_task_repository.py:160-189`（`started_at < cutoff` / `created_at < cutoff` 直接比较）；模型列 `DateTime(timezone=True)` 在 MySQL 上实际是无时区 DATETIME（`platform_core/models/spider_task.py:45`）；`schedule_service.py:12` 注释自己承认"时间比较基于本地时间（与 func.now() 一致）"——这个前提只在 app 与 DB 同 TZ 时成立。
- 为什么深层：config/ 全库无时区配置，容器化部署中 MySQL 镜像默认 UTC、应用 TZ 常被设为 Asia/Shanghai。偏移 8h > STALE_TASK_HOURS(6h) 时，`find_stale_running` 的 DB 侧过滤退化为恒真（回收时机完全由 ACTIVE_TASK_TTL=24h 接管，回收窗口从配置的 6h 静默漂移到 24h）；`find_stale_pending` 的重投窗口同样漂移 8h；LLM 用量的日键（`llm_usage_service.py:53-54` 用本地 `date.fromtimestamp`）与 DB 的 `stat_date`（DB 时间）跨日界对不齐。这类偏移不报错、只让运维参数失真，是排查成本极高的一类问题。
- 解决方案：统一单一时钟源——DB 侧比较一律用 SQL 表达式（`started_at < DATE_SUB(NOW(), INTERVAL :hours HOUR)`，让 cutoff 与写入同源），或应用侧全部用 `datetime.now(timezone.utc)` 且 DB 会话 `SET time_zone='+00:00'`；在 `sdlc.config.yaml`/check-arch 加禁令：业务代码禁止 naive `datetime.now()` 与 ORM 时间列比较。取舍：SQL 内算时间牺牲可测试性（可在 repository 层封装成可注入的表达式工厂）。

### 8. 后台组件 stop() 关闭进程级共享 Redis 客户端，且缓存不清除
- 严重度：中
- 证据：`platform_core/redis_async.py:47-70`（生产态返回进程级缓存实例，注释明确"调用方禁止 close 缓存实例；消费者等需独占生命周期的组件应自建连接"）；`backend/tasks/consumer.py:162,207-209`、`backend/services/schedule_service.py:171,189`、`backend/services/llm_usage_service.py:144,160`（三处都把 `get_async_redis()` 的共享实例存到 self 并在 stop() 中 `aclose()`，缓存 `_clients` 仍持有已关闭实例）。
- 为什么深层：lifespan 正常关停时按顺序 aclose 尚可接受（进程即将退出），但：关停顺序敏感（`app/__init__.py:172-213` 中 scheduler.stop 先于 consumer.stop，前者关闭共享池后 consumer 关停路径内任何 Redis 操作都会 "client is closed"）；in-flight 请求在 shutdown 窗口拿到已关闭客户端报错；任何"组件重启/重开"场景（热重载、测试外脚本里 start→stop→start）第二次 `get_async_redis()` 拿到的是缓存里的关闭实例且无人恢复。测试态无缓存（`_IN_PYTEST` 分支），所以单测永远测不出来。
- 解决方案：三处组件改为启动时自建客户端（`aioredis.from_url(_resolve_url(key), ...)`——redis_async 已暴露 `_resolve_url`，可提为公共函数），或在 `get_async_redis()` 返回前检查 `client.connection_pool` 存活、关闭时同步从 `_clients` 弹出（提供 `release_async_redis(client)` 配对 API）。取舍：自建连接多占一份池（max_connections=100 是池上限非预建，成本可忽略）；共享实例 + 引用计数方案更省但复杂度高。

### 9. 共享 LLM httpx AsyncClient 缓存无并发保护：并发首调泄漏连接池
- 严重度：中
- 证据：`backend/services/ai_planner/llm_client.py:67-95`（`get_shared_client` 为 async 函数但全程无 await 点，`_HTTP_CLIENTS[key] = client` 覆盖写，无锁）；`llm_client.py:74-76`（对"已关闭残留条目"有清理，但对并发创建的孤儿条目无感知）。
- 为什么深层：两个协程在事件循环交错执行 `get_shared_client`（函数虽无 await，但 `llm_chat` 在调用它之前有多个 await 点，两个请求完全可能同时进入）→ 各建一个 AsyncClient → 后写者覆盖 dict → 先建者的连接池失去所有引用，其 keep-alive 连接（最多 20 个/池）只能等 GC 兜底关闭。LLM 调用是低频路径所以平时无害，但技能评分 worker + 巡检 + 用户请求并发命中冷缓存时会稳定复现；`invalidate_client_cache` 关闭的是 dict 里的那个，孤儿池永不失效。同类问题：多实例下 `_TOKEN_USAGE` 内存计数已被 P0-3 的 Redis 聚合修复，这个 client 缓存是同一"单进程假设"下剩下的死角。
- 解决方案：加 `asyncio.Lock`（per-key 或全局，创建路径包 double-check）；或更简单——把函数改为纯同步 `def`（它没有任何 await 语义），明确其非原子性由"创建顺序无关紧要 + 重复创建由 GC 兜底"注释背书，同时在创建前对旧 client `aclose()`。取舍：锁在热路径引入一次 await（可忽略）；真正根治可换 `functools.lru_cache` 式的不可变 client（api_key 变化即新 key，旧条目由 TTL 任务关闭）。

### 10. 结果双写/双计数跨存储一致性：Redis 镜像先于 DB commit、result_count 双口径竞态
- 严重度：低
- 证据：`backend/tasks/consumer.py:700-704`（`_mirror_batch` 在 `session.commit()` 之前 rpush 到 `TASK_RESULTS_KEY`，commit 失败则 Redis 已多出 DB 不存在的"结果"，csv 落盘（`spider_task_service.py:647` 直接 lrange 该键）与 redis 直读会带出未落库数据）；`spider_task_service.py:453-455`（webhook 的 `item_count` 覆盖写 result_count）vs `consumer.py:697-698`（consumer 增量累加）——webhook 先到、最后一批 item 后落库时，最终 result_count = item_count + 迟到增量，与行数漂移；`llm_usage_service.py:201-244`（rename 认领 + upsert 累加 = at-least-once，crash 在 commit 后 delete 前则下轮双计，注释已自知）。
- 为什么深层：三个存储（MySQL、Redis 结果键、CSV 文件）之间没有任何以 DB 为准的对账/补偿路径，一致性完全依赖"顺序运气"。单看每处都是小概率，叠加"store_to=redis 直读给下游消费"的场景时，脏读会跨系统传播。
- 解决方案：镜像写移到 commit 成功之后（flush 失败的代价只是 Redis 少几条缓存，方向安全）；result_count 以 DB 行数为准——webhook 的 item_count 仅作告警对照（差异超阈值记日志），或 consumer 在收到该任务终态后做一次 `count_by_task` 校准；用量双计可接受（预算熔断方向保守）但应加注释声明"计费场景不可用本表"。取舍：镜像后置让"直读"结果在 commit 瞬间有一致性，代价是每批多一次往返；计数校准每任务一次 O(count) 查询，大任务需限流。
