# 深层次架构审查（独立视角）— 2026-09-06

> 透镜：10 倍流量、10 倍数据、10 人团队协作下，什么先崩。
> 依据：仅仓库事实（代码 / docker-compose / CI / alembic / docs/adr）。未读 .sdlc/.scratch/docs/plan/docs/research。

## 总体判断

这是一个**单机时代长得很好的单体**：分层纪律（R1-R13 机械检查）、事务归属（ADR-0007）、服务依赖解环（ADR-0006）、租户行级隔离（ContextVar 事件钩子）在同规模下都是超配的好工程。但它的**执行拓扑没有演进出口**——8 个后台循环（队列消费者/调度器/探针/评分/巡检/用量聚合）全部内嵌在 FastAPI 进程里，任务终态闭环按「爬虫名」全局归账而非按执行实例归账，结果回流管道把「多租户配额」放进「全局批量提交」路径——这三件事在当前单副本下全部正确，在 10x 流量被迫横向扩容的那一刻同时变成正确性缺陷。第二层风险是**共享命运**：Redis 一个实例同时是队列、分布式锁、限流计数、配额缓存、计费账本（无持久化卷）和 scrapy 调度器，一个故障域承载全部异步链路，且故障语义是 fail-silent（静默跳过）。第三层是**演进速度约束**：可观测性只有文件日志（无 metrics/tracing），测试缝（门面 patch + conftest 与生产行为分叉）被 ADR 明文承认为现状锚——10 人团队并行改结构会大面积红测试，最终学会不改结构。总体：代码质量高于架构可扩展性，瓶颈不在代码在拓扑与数据面。

---

## 深层次问题清单（按严重度排序）

### 1. 结果回流管道：单租户配额超限 = 全平台回流停摆 + 数据丢失窗口 | 严重度：高

**证据**：`backend/tasks/consumer.py:538`（lpop 批量出队，消息已离开 Redis）；`consumer.py:552-559`（`_flush_batch` 抛异常时 `batch.clear()` 不执行，整批留在内存下轮重试）；`consumer.py:688-695`（flush 内逐租户 `check_result_storage`，抛 `QuotaExceededException`）；`backend/services/quota_service.py:113`（超限 raise 429）；死信队列 `DEAD_ITEM_QUEUE` 仅覆盖缺 task_id 消息（`consumer.py:334-346`）。免费档 `result_storage=10000`（`quota_service.py:27`），采集型租户一天可打满。

**为什么深层**：这是失败模式设计缺陷而非 bug——把「单租户策略执行」嵌入「全平台共享管道的原子提交路径」，毒消息使整批（含所有其他租户）无限重试：头部阻塞停摆 + 批次无界增长（内存泄漏）+ 停摆期间进程重启即丢批（消息已出队、无回放日志）。10x 流量下超限租户必然出现，届时现象是「所有用户结果神秘消失」，且因无可观测性（见问题 8）只能靠投诉发现。

**解决方案**：
1. 配额检查失败的消息**单独出队**转 per-tenant 暂存键（`spider:item_hold:{tenant_id}`）并触发告警，批内其余消息照常落库——部分失败隔离到租户粒度；
2. flush 失败的整批先 `LPUSH spider:item_queue:redo`（带重试计数，超过 3 次进 DEAD_ITEM_QUEUE）再放弃内存持有，崩溃可恢复；
3. 配额语义从「提交前硬闸」改为「写入 + 异步对账超额告警」，把停摆从全局事件降级为租户事件。

**取舍**：配额从精确硬闸变软闸（秒级滞后），换取管道可用性。被否决备选：flush 失败整批 rpush 回原队列头——头部阻塞依旧，且需额外延迟队列机制，复杂度更高。

---

### 2. 任务终态闭环按爬虫名全局归账：多 worker 扩容即互相误杀 | 严重度：高

**证据**：`platform_core/queues.py:48`（`ACTIVE_TASK_KEY = "spider:active_tasks:{spider_name}"`，全局 SET）；`scrapy/extensions/__init__.py:60-75`（`spider_closed` 读取该爬虫名下**全部**活跃成员并逐一回调 completed/failed，status 由本进程 close reason 推导）；`backend/services/spider_task_service.py:421-446`（failed 回调触发自动重试重新入队）。`run_spider.py` 有 WORKER_ID 心跳设计，明确预期多 worker。

**为什么深层**：归属模型错了——任务归属「爬虫名」，执行归属「worker 实例」。单 worker 下正确；10x 流量横向扩爬虫后，worker A 关闭（崩溃/手动停止/正常收尾）会把 worker B 在跑的任务标成终态：running 任务被标 failed 还触发自动重试 → 重复采集；被标 completed → 结果继续回流但任务已「完成」，口径错乱。CI 无多 worker 测试，缺陷只在扩容时爆发。

**解决方案**：活跃键成员改为 `{worker_id}:{task_id}`（或键加 worker 维度），`spider_closed` 只回调本实例成员；backend 侧 `finish_task` 以 DB 行状态为唯一事实源（幂等守卫已有）。迁移路径复用既有 `_purge_legacy_active_keys` 模式：启动时清理旧格式键，双格式兼容一个版本周期。

**取舍**：键格式变更需要一次灰度（新旧 worker 混跑期间终态语义混合）。被否决备选：废弃 webhook 改心跳对账推终态——即时性有价值且对账循环已有 STALE 兜底，webhook 应保留而非替换。

---

### 3. Redis 一个实例承载队列/锁/计费/调度，无持久化无 HA，故障语义 fail-silent | 严重度：高

**证据**：`docker-compose.yml` redis 服务（无 volumes、无 appendonly 配置，仅 requirepass）；`platform_core/queues.py` 同一实例承载任务/结果/死信/评分队列 + 6 把分布式锁 + 限流/配额计数 + 渠道配置 + 代理池；`scrapy/settings.py:52-56`（scrapy-redis 调度器与 dupefilter，`SCHEDULER_PERSIST=True`）；`backend/services/llm_usage_service.py`（Redis hash 为日/月用量**主账本**，月键 TTL 93 天，是预算熔断读数与计费依据）；`queues.py:227` 锁获取「Redis 故障按未抢到处理」、`redis_async.py:66` max_connections=100。

**为什么深层**：「B2 边界（爬虫与 backend 经 Redis 解耦）」实际制造了单一共享命运体：Redis 重启 = 在途任务/结果消息蒸发（采集白跑）+ 用量账本回退（计费纠纷）+ dupefilter 清零（全量重爬打目标站）+ 全部后台循环静默停摆（锁拿不到 → 跳过本轮 → 无告警）。MySQL 有 pool_pre_ping/健康深探测，Redis 没有任何同级待遇。10x 下 Redis 既是吞吐瓶颈也是可用性单点。

**解决方案**（分级，10x 前不必上集群）：
1. Redis 开 AOF（`appendonly yes, appendfsync everysec`）+ 挂数据卷——一行配置消除账本/队列蒸发；
2. 键分域：队列/调度（延迟敏感、可丢秒级）与计数/账本/锁（不可丢）拆 DB 或拆实例，爆炸半径分离；
3. 后台循环锁获取失败连续 N 次即打结构化告警（fail-silent → fail-visible），`/health/deep` 增加 Redis 写探针。

**取舍**：拆实例增加一个运维对象，换故障隔离。被否决备选：直接上 Redis Cluster/Sentinel——当前规模运维成本先行、收益为负，分域后若仍不够再上。

---

### 4. 执行拓扑：8 个后台循环内嵌 API 进程，水平扩容路径被锁死 | 严重度：高

**证据**：`backend/app/__init__.py` lifespan 依次启动 consumer / scheduler / proxy_health / llm_usage_flush / skill_scoring_worker / llm_health_patrol / newapi_scheduler / newapi_probe（每个独立开关，默认随 API 全开）；`consumer.py:416` `_requeued_counts` 进程内存计数（多副本下重投上限 2 变 2×N）；docker-compose 仅单 backend 服务，无 worker 角色。10x 流量第一反应「API 多副本」会同时复制全部后台组件。

**为什么深层**：API（短请求、低内存）与后台循环（blpop 长阻塞、批量落库、HTTP 探针、评分 CPU）资源画像完全不同，共享进程使：无法独立伸缩/发布/回滚；消费者的 OOM/GC 停顿直接损伤 API P99；多副本后「副本数 = 消费者数 = 调度器候选数」不可控。问题 1/2/3 的爆炸半径都以此为放大器。当前 8 个独立开关可以手工拼出角色，但没有一等公民的部署角色 = 每次扩容都是一次手工易错配置演练。

**解决方案**：引入 `APP_ROLE=api|worker|all`（默认 all 零迁移成本），lifespan 按 role 装配组件；compose/Dockerfile 增加同镜像 worker 服务（command 注入角色）。现有 asyncio 循环 + `distributed_lock`（自动续期 + lost 感知）已天然支持多实例，**不需要引入任务队列框架**。迁移路径：先拆 consumer+usage_flush（数据面），调度/探针/评分渐进跟进。

**取舍**：多一类部署对象与配置矩阵。被否决备选：引入 Celery/Arq 替换自研循环——现有锁设施已解决多实例互斥，换框架是以 10 倍迁移成本买已具备的能力。

---

### 5. 数据面租户完整性不设防：tenant_id 由消息自报，入队即信任 | 严重度：中

**证据**：`consumer.py:671`（`tenant_id=msg.get("tenant_id")` 直接入库 SpiderResult）；flush 内加载 task 行（`consumer.py:614-627`）但从不校验 `msg.tenant_id == task.tenant_id`；配额检查同样基于该自报值（`consumer.py:690-694`）。R13 行级隔离与越权测试全部在 API 面，异步数据面无任何归属断言（`tenant_context.py` 断言仅在 tenant_scope 生效，消费者跑在无上下文态）。

**为什么深层**：租户隔离被实现为「API 层 ContextVar」而非「数据归属不变量」。spider 侧归属逻辑的回退路径（多活跃成员置 None、单成员归属——`scrapy/pipelines/__init__.py` StorePipeline）本身承认归属不可靠；Redis 访问权 = 跨租户写原语。结果写错租户无任何检测手段，SaaS 隔离承诺在数据面是敞开的。

**解决方案**：flush 内以 task.tenant_id 为唯一事实源派生 `SpiderResult.tenant_id`，msg 自报值仅用于不一致告警（一次字典查找的成本）；配额检查同步改用派生值。被否决备选：队列消息加 HMAC 签名——共享内网下攻击面收益低，先做派生校验这个零成本不变量。

---

### 6. spider_results 无界增长：Integer 主键天花板 + 软删除只增不减 + LIKE 全表扫 | 严重度：中

**证据**：`platform_core/models/spider_result.py`（`id Integer` 主键、`task_id Integer` FK、content/extra 均 Text、SoftDeleteMixin）；`spider_result_repository.py:152-156`（keyword 检索 `LIKE '%kw%'` 打 title/url/content 三列，前导通配不可走索引）；`:159-167`（每页请求伴随全量 `COUNT(*)`）；全仓无任何 retention/cleanup/归档执行器（grep 0 hit，ADR-0002 的「保留策略」仅停留在 Spec 概念）。

**为什么深层**：最大的表决定库的运维上限。10x 数据下：COUNT 每请求扫索引树、LIKE 检索实际不可用（KEYWORD_SEARCH_MAX_ROWS 只限制结果窗口不限制扫描代价）、软删行永不物理清理、INT 主键 21.4 亿上限且在最大表上改类型 = 全表重建级迁移。ADR-0002 辛苦建立的 expand-contract 纪律没有覆盖「主键类型」这种最贵的情形。

**解决方案**：1) 落地保留策略执行器：按租户套餐 TTL 批量物理删除/归档（复用 lifespan 循环基建 + 分批 DELETE，soft-delete 行同样纳入）；2) 分页改 keyset（`WHERE id < ? ORDER BY id DESC`），total 改缓存或估算；3) keyword 切 MySQL 8 ngram FULLTEXT（`WITH PARSER ngram`）；4) 治理窗口内评估主键 BIGINT 化（新表一律 BIGINT 写入规范）。被否决备选：立即按月 RANGE 分区——MySQL 分区与 task_id FK 互斥，先删 FK 的代价大于收益，保留策略先行。

---

### 7. 配额与并发槽位是 check-then-act + 60s 缓存：负载越高越不可信 | 严重度：中

**证据**：`quota_service.py:56-67`（COUNT 缓存 60s TTL，Redis 故障回源 DB COUNT）；`:80-100`（读计数后比较，无原子扣减）；`spider_task_service.py:179`（并发槽位 `scard` 后比较，同型竞态）；多副本下无跨实例原子性。

**为什么深层**：配额是 SaaS 商业承诺，实现却是概率性的：竞态窗口随并发线性放大（10x 流量下两个请求同时读到 `active = limit-1` 全部通过是常态而非边缘）；60s 缓存窗口内超限租户可继续写入 60s×QPS 条。且结果存储配额依赖对最大表的 COUNT——问题 6 的放大器。

**解决方案**：Redis 原子计数器做配额槽（入队前 `INCR` + 拒绝时 `DECR` 回滚，TTL 兜底防泄漏），现有 60s COUNT 缓存降级为周期对账修正漂移；并发槽位同理（sard → 原子 `SADD` 后判 `SCARD` 已是原子，需把「检查+写入」合并为一次 SADD 判定）。**取舍**：接受「最终一致配额」并把语义写进产品文案（超额部分事后结算/告警）。被否决备选：DB 计数行 `SELECT FOR UPDATE`——把热点写集中到单行锁，10x 下反而成为串行瓶颈。

---

### 8. 可观测性只有文件日志：停摆类故障无主动信号 | 严重度：中

**证据**：全仓 grep prometheus/opentelemetry/statsd = 0 hit；`backend/app/middleware/` 仅 request_id + process_time（日志维度）；后台循环所有失败路径只 `logger.error/warning`（`consumer.py:576-578`、`queues.py:167-170` 等）；docker 日志上限 10m×3（`docker-compose.yml` logging 块）；`/health/deep` 只探 MySQL SELECT 1 + Redis PING，不探队列积压与循环存活。

**为什么深层**：问题 1/2/3 的故障形态全是 fail-silent（循环活着但不干活、锁拿不到就跳过、批次卡在内存）。当前发现它们的唯一途径是用户投诉。可观测性不是独立问题，是其他所有问题能否被管理的乘数；10 人团队并行排障时「定位一次线上问题的时间」直接决定演进速度。

**解决方案**（最小闭环，不上 APM）：1) prometheus-client 暴露 /metrics：队列深度（LLEN/ZCARD）、flush 批次大小与延迟、循环 last_success_at、锁丢失计数；2) 每个后台循环把心跳时间戳写 Redis 键，`/health/deep` 聚合判定「stale 循环」返回 503；3) 日志 JSON 结构化（loguru 基建已有）+ request_id 已有，跨进程串 request_id 贯通 dispatch→ingest 链路。**取舍**：metrics 自维护 vs 全托管 APM。被否决备选：直接上 OTel collector + Jaeger 全链路追踪——10 人团队初期维护成本大于收益，指标先行、trace 缓行。

---

### 9. 测试缝锁死物理布局：门面 patch + conftest 行为分叉使重构 = 大面积红 | 严重度：中

**证据**：ADR-0006 自认「llm_chat/cooldown 物理迁入 llm_common 被否决，因为存量单测以模块命名为 patch 缝」（否决备选表第 3 行）；ADR-0007 自认「conftest `expire_on_commit=False` 掩盖 commit 后读属性缺陷，快照形态是唯一防线」（D2）；`llm_usage_service.py:33` 测试态直接 return（用量路径测试不触真 Redis）；CI MySQL 保真通道仅 39 用例、无 Redis 真实实例（`.github/workflows/ci.yml` 仅 mysql service）。

**为什么深层**：ADR 已经把退役条件写清（「测试面完成迁移后可退役门面与 seam」）但没有执行机制与度量——10 人团队并行演进时，移动文件/改 session 语义会红一片测试，团队学会「不改结构」，架构熵化不可逆。测试从安全网退化为现状锚，这是对演进速度最隐蔽的税。

**解决方案**：1) 立「测试面迁移」专项：新增测试禁止 patch 门面（check-arch 可加一条 grep `patch.*ai_planner_service`），存量按域分批迁移，完成后删 seam——把 ADR 的「届时」变成有度量的工单；2) CI 增加真实 Redis service 容器（一分钟成本），覆盖 consumer flush / usage flush / 锁语义路径；3) 「patch 定义模块而非门面」写入 coding-style skill。

**取舍**：迁移期双轨（新旧 patch 方式并存）增加 review 负担。被否决备选：存量测试一次性重写——增量迁移可分批验证，全量重写风险不可控。

---

### 10. 多态关联把引用完整性永久外包给应用纪律 | 严重度：低

**证据**：ADR-0004 决策 3：tags/taggings/attachments/notifications/resource_versions/i18n_translations 六表统一 `resource_type + resource_id` 字符串对；无 FK、无唯一性约束可表达；全仓无孤儿清理周期作业（grep cleanup/orphan 仅 member_service 一处注释性物理删）；`resource_type` 取值 = 模型名小写下划线（隐式命名契约，无机械检查）。

**为什么深层**：10x 数据 + 10 人团队下，各域删除策略自行实现（软删/硬删/级联口径本就分裂，ADR-0004 豁免矩阵可见），多态表必然累积孤儿（任务删除后 tagging 残留 → 前端幽灵标签）；每新增一种可 tagged 资源都是无检查的隐式契约，模型重命名即静默数据漂移。

**解决方案**：短期：孤儿清理周期作业挂入现有 lifespan 循环基建 + `resource_type` 收敛为权限表同款枚举注册表（check-arch 校验模型名↔注册表同步）；长期：读路径高频的 tagging 关系改 per-type FK 列或独立关联表。**取舍**：枚举注册表增加一次注册手续，换命名漂移可检。被否决备选：立即全量改 per-type FK——六表一次性迁移成本过高，先治读面、孤儿可见后再动结构。

---

## 附：问题间依赖（修复顺序建议）

```
问题 8（可观测性）是 1/2/3 的前置——先有信号再动管道
问题 4（进程拓扑）是 1/2 的放大器——先拆角色再修管道语义
建议批次：P0 = 8 → 1 → 3(a/c) ；P1 = 4 → 2 → 5 ；P2 = 6/7/9/10 按域排票
```

## 遗留与未深入

- LLM 网关韧性（cooldown/探针/渠道调度）有独立回路设计，本轮只验证了超时与连接池上限存在，未压测其并发语义；
- frontend 双应用 + shared workspace 形态对 10 人团队足够，未深查；
- `ai_planner` 状态机（state/orchestrator 包内环已由 ADR-0006 seam 解除）运行时正确性依赖 seam 装配顺序，建议随问题 9 一并收口。
