# Findings — R2-backend-services（后端服务层、异步任务与共享基建）

## Snapshot
- HEAD: 82259f301c060dbf411424ec8775f29944e313e1（工作区干净）
- slice: `git ls-files -s` over explore_roots(backend/services backend/repositories backend/tasks platform_core) + inputs → sha256 834c80bea40e…（211 条），由 manager 计算
- reviewer: sdlc-workflow:reviewer（G-fresh，只读）；packet: ../packets/2026-09-27-1830-review-reviewer-R2-backend-services.md
- 方式：静态阅读 + 引用 evidence/ 已记录执行（arch / ruff / ruff-extended / pytest）；reviewer 未执行任何命令，无一条为本人复现。
- 备注：首轮因 API 限流中断，额度恢复后经 manager 要求续跑交付。

**结论**：20 条（blocker 1 / major 13 / minor 6）。采集出数环存在一个会卡死回流、并波及其他租户数据的毒消息死循环（QA-1）。主要问题三类：状态机不幂等；槽位与恢复信号失真；LLM 成本闸在目标运行时（LiteLLM）上 fail-open。

---

## FINDINGS

### QA-1 唯一索引 + 非幂等批量 INSERT + 整批回放 = 跨租户毒消息死循环
- Dimension: 5 / 8 / 9 | Severity: **blocker** | 工作量: M
- Evidence：`platform_core/models/spider_result.py:16-19` `UniqueConstraint(tenant_id, spider_name, content_hash)`，`backend/alembic/versions/030_heartbeat_perms_last_login.py:42-45` 已建唯一索引；`backend/tasks/consumer.py:700-706` 每条结果算 `content_hash`，但 `:708-720` 只有 `params.incremental` 为真时查重，批内也不去重；`:779` `session.add_all` 普通 INSERT，`:790` 统一 commit；`backend/tasks` 与 `backend/repositories` 下找不到 `IntegrityError` / `ON DUPLICATE` 处理（仅 `llm_token_usage_repository.py:39` 用了 on_duplicate）。
- 后果：非增量任务重跑（定时调度、热搜类同 url/title/content）或同次采集出现重复条目 → flush 必然 IntegrityError；`:616-622` 把整批最多 50 条（含其他租户正常消息）停放到 `ITEM_REDO_QUEUE`；`:576-578` 主队列空闲时约每 1.2s 取回一次、再次失败，无次数上限、无死信出口；新到的正常消息被拼进同一批一起被污染 → `result_count` 一直回滚，用户「采了但看不到结果」；`:787` `_mirror_batch` 在 commit 前执行，每轮重试都往 `spider:task_results:{id}` 追加重复条目（redis/csv 存储目标重复）。
- Suggestion：① 入库幂等写——MySQL `insert(...).prefix_with("IGNORE")` 或 `on_duplicate_key_update(id=id)`，按实际插入行数回写计数，批内先 `set` 去重；② REDO 消息带 `attempt`，超 N 次转 `DEAD_ITEM_QUEUE`，并逐条隔离（批量失败降级逐条写，只把失败那条送死信）；③ `_mirror_batch` 挪到 commit 之后；④ 唯一键业务语义先定（Q-1）。

### QA-2 租户并发槽在首次分发时从不写入，`SPIDER_MAX_CONCURRENT_PER_SPIDER` 对租户任务不生效
- Dimension: 1 / 6 / 8 | Severity: **major** | 工作量: S
- Evidence：`backend/services/spider_task_service.py:279-283` 入队消息只有 `{task_id, spider_name, params}`（注释「不含 tenant_id」）；`backend/tasks/consumer.py:291-295` 只有 `msg.get("tenant_id")` 为 int 时才 `sadd` 租户槽；`spider_task_service.py:252-257` 入队时对租户槽 `scard`，首次任务永远读到 0，只有重试消息（`:711-720` 带 tenant_id）才占槽；对应测试只断言「用这个 key 调 scard」（`backend/tests/test_spider_flow_engine.py:153`、`test_billing_retention.py:184`），不断言分发后槽里真有成员——空断言。
- 后果：每租户每爬虫 2 并发限制名存实亡，只剩 `QuotaService.check_task_concurrency`（`quota_service.py:222-241`，按租户 DB 总数）兜底；scard 与 create 之间有 TOCTOU（`:256-275`），分发时也不复查，同一秒突发入队都能通过。
- Suggestion：分发时从 `:271` 已取到的任务行读 `tenant_id`（与 `_task_owner_id`「只认任务行」一致）；占槽前移到入队并用 Lua 原子 `SCARD`+`SADD`，或分发时 CAS 占槽、占不到延后重投；测试改断言状态结果。

### QA-3 任务消息有三种形状，`update_task` 的 LREM 永远匹配不上，编辑待执行任务不生效
- Dimension: 6 / 9 | Severity: **major** | 工作量: S–M
- Evidence：入队消息 3 键（`spider_task_service.py:280-283`）；`update_task` 的 `old_message` 5 键含 tenant_id、priority（`:349-358`），注释 `:348`「须与 enqueue 完全一致，含 tenant_id」与 `:279`「不含 tenant_id」矛盾；LREM 按字符串整体比对，未命中后查 ZSET 也未命中 → 「不动队列」（`:402-422`）；分发用消息里的 params 而非 DB（`consumer.py:255, 263, 303-304`）；另两种形状 `consumer.py:530-538`（requeue）、`spider_task_service.py:711-720`（retry）。
- 后果：DB 与界面显示新参数/优先级，实际执行旧的；用户看到「已修改」结果却不对，且无任何报错。
- Suggestion：消息只带 `{task_id, attempt}`，分发时从 DB 读 params/priority/tenant（DB 为唯一事实源，编辑无需搬迁消息，仅优先级变化才需）；暂保留现状则至少收口为一个 `build_task_message(task)`。

### QA-4 分发与失败推进是无条件 UPDATE，重复消息把终态任务翻回 running 并再爬一次
- Dimension: 6 / 8 | Severity: **major** | 工作量: M
- Evidence：`consumer.py:271` `repo.update(task_id, status="running", ...)` 无 `only_if_status`；`_fail_task` 在 `:336` 同样无条件；对比 `finish_task` 用了条件更新（`spider_task_service.py:523-530, 569-571`），仓储已支持（`spider_task_repository.py:18-28`）。重复消息来源：`_requeue_stale_pending`（`consumer.py:507-550`）任务积压超 6h（`config/default/settings.yml:27`）即重投（worker 离线或低优先级被 `blpop` 顺序饿死，`:220-223`）；多实例时每进程都跑 `_recover_loop`（`:456-467`）且未用 `distributed_lock`（`queues.py:154-158` 列出的调用方只有三处 tick 循环）；重投计数 `_requeued_counts` 只在进程内存（`:454`），重启清零、多实例不共享。
- 后果：completed/failed 被翻回 running、`started_at` 重置、start_urls 再投递 → 重复采集 → 触发 QA-1；回收循环可能把刚完成任务覆写成 failed；重投 2 次后任务置 failed 但原消息仍在队列，之后分发又翻回 running。
- Suggestion：分发 `only_if_status=("pending",)` CAS，rowcount=0 丢弃并记日志；`_fail_task` 限定 `("pending","running")`；`_recover_loop` 套 `distributed_lock`；重投次数持久化（DB 列或 Redis hash）。

### QA-5 活跃槽泄漏，且孤儿检测依赖的信号会被续期覆盖
- Dimension: 8 / 9 | Severity: **major** | 工作量: M
- Evidence：分发在 `consumer.py:289-295` 先 `sadd` 再投递；投递失败走 `:311-313` `_fail_task`，而 `_fail_task`（`:331-340`）不 `srem`，槽位要等 24h TTL；孤儿判定「超时且不在集合里」（`:469-500`），但 `ACTIVE_TASK_KEY` TTL 每次分发都续期（`:290`）——爬虫只要还在跑别的任务，崩溃任务的成员就一直留在集合里。
- 后果：崩溃任务永久停在 running 并占并发槽；租户侧看到「已有 2 个进行中的任务」无法提交。
- Suggestion：改为按任务租约（`spider:active:{task_id}` 带 TTL、worker 心跳续期，或 ZSET score=到期时间）；孤儿判定改用已有 `WORKER_HEARTBEAT_KEY` / `WORKER_ACTIVE_KEY`（`queues.py:68-82, 105-108`）；所有终态路径统一 `srem`。

### QA-6 配额超限的 hold 队列没有消费者
- Dimension: 9 / 5 | Severity: **major** | 工作量: M
- Evidence：`consumer.py:780-781` 把超额结果写 `spider:item_hold:<tid>`（`queues.py:49-54`）；全仓 `*.py` 除测试（`backend/tests/test_p0_plan_execution.py:54`）外无任何读取方；队列无 TTL；`DeadItemService` 只管 `DEAD_ITEM_QUEUE`。
- 后果：租户升级或清理后结果不回放、也无处可见——对用户是静默丢失；Redis 内存无界增长。
- Suggestion：先定产品语义（Q-2）；配额变更/升级事件时 drain 回放；租户与后台展示「待入库 N 条」；设上限与 TTL，溢出转死信。

### QA-7 租户交付 webhook：SSRF，且与内部回调共用签名密钥
- Dimension: 4 | Severity: **major** | 工作量: M
- Evidence：`backend/services/tenant_settings_service.py:20-22` 只查 URL 以 `http(s)://` 开头；`delivery_webhook_service.py:30-48` 直接 POST；调用方 `spider_task_service.py:666` 不传 secret → 退回 `WEBHOOK.SECRET_KEY`，签名为 HMAC(`ts.body`)；内部 worker 回调验签同一密钥同一构造（`backend/app/external_api/v1/webhooks.py:44-50`），请求体字段 `task_id:int`、`status:completed|failed` 也正好满足 `:73-78` 校验。
- 后果：**SSRF**——租户管理员可让后端向 127.0.0.1、云元数据、内网 LiteLLM admin 等发 POST（盲 SSRF）。**签名密钥复用**——每次交付给租户的请求都是 300s 内能被 `/spider/callback` 接受的合法签名请求；今天重放只打到自己已终态任务（幂等空操作，`:516-517`），但租户要验签就必须拿到平台密钥，一旦给了，任何租户都能伪造任意 task_id 的跨租户终态回调。
- Suggestion：每租户独立交付密钥（生成后加密存储、只展示一次），签名头与内部回调区分命名空间；设置时与发送时都复用 `backend/services/ai_planner/url_guard.py` 做内网/保留地址校验，发送时先解析 DNS 再校验 IP（防 DNS rebinding）。
- 威胁模型：reviewer 未加载 architecture/threat-model 参考，未做逐条 STRIDE，仅按边界、缓解、测试锚点定性判断。

### QA-8 LiteLLM 网关路径忽略 `BUDGET_FAIL_CLOSED`，生产成本闸 fail-open
- Dimension: 4 / 6 | Severity: **major** | 工作量: S
- Evidence：`backend/services/ai_planner/llm_client.py:236-238` Redis 读数为 None 时直接退回进程内存计数；provider 路径遵守 fail-closed（`:515-522`）；`config/prod/llm.yml:5` `BUDGET_FAIL_CLOSED: true`，默认数据面 `DATA_PLANE: "litellm"`（`config/default/llm.yml:14`）。
- 后果：目标运行时恰是 fail-open 的那条路径；Redis 故障时预算按每副本、重启即清零的内存值判断，熔断失效。
- Suggestion：抽 `_budget_guard(dim, budget)` 两路径共用。

### QA-9 LLM 调用无总时限，重试、故障转移与模型探测放大延迟
- Dimension: 5 / 8 | Severity: **major** | 工作量: M
- Evidence：超时 120s、重试 3 次（`config/default/llm.yml:19-20`），最后一次失败后仍 sleep（`llm_client.py:604-609, 272-277`）；故障转移时每个候选模型重新完整执行 `llm_chat`（含配置解析、配额检查、3 次重试，`:368-374`）；候选链在 `:354`、`:362` 各查一次；网关路径每次调用先探测 `/v1/models` 且探测在重试循环外（`:201-209, 224`），探测抖一次即判「网关不可达」；429 不看 Retry-After；主模型不做冷却检查，冷却过滤只作用于候选链（`:335-343`）。
- 后果：最坏耗时约 (1+候选数)×(3×120s+7s)，调用方与后台协程长时间被占，网关多承受一倍请求。
- Suggestion：`llm_chat` 套 `asyncio.timeout` 做整体截止；最后一次失败后不 sleep；模型列表 TTL 缓存（如 60s）；遵守 Retry-After；主模型先查冷却；候选链只查一次。

### QA-10 月度 token 闸执行两次，且两次月份口径不同
- Dimension: 6 / 8 | Severity: **major**（前提：部署时区不是 Asia/Shanghai，未核实） | 工作量: S
- Evidence：`llm_client.py:415-423` 用 `shanghai_year_month()`；重试循环每次尝试又用 `_date.today()` 查一遍（`:529-548`），取引擎用 `next(iter(_engines.values()))` 而非 DEFAULT，基础设施异常只在 debug 级吞掉。
- 后果：服务器为 UTC 时每月前 8 小时第二次检查查的是上个月，上月已用尽的租户会被误拦。
- Suggestion：删掉循环内那次检查，统一上海口径；异常按 fail-closed 配置处理。

### QA-11 会话与事务的「深模块」契约未落实，后台路径绕过租户作用域
- Dimension: 1 / 4 / 7 | Severity: **major** | 工作量: M
- Evidence：`backend/services/background_session.py:1-10` 规定后台组件（点名 consumer）必须经它拿会话并进入 tenant/platform scope，「禁止拆回各自开 session」；实际 `consumer.py` 8 处直接 `AsyncSession(self._engine())`（`:258, 269, 282, 334, 481, 516, 659, 863`），`spider_task_service.py:663, 686` 与 `llm_client.py:175, 194, 315, 541` 也直开；无 scope 时写入断言与读侧注入全部跳过（`platform_core/tenant_context.py:122-124, 138-140`）；事务提交点分散：`services/tasks/api` 下共 153 处 commit、50 个文件，辅助方法内部也提交（`spider_task_service.py:291, 730`）。
- 后果：纵深防御形同虚设，今天正确完全依赖每处手工传 tenant_id；R13 检查不到这种情况。
- Suggestion：后台路径全部改用 `background_session(anchor)`；`arch.sh` 加规则——`platform_core/db.py` 与 `background_session.py` 之外禁止 `AsyncSession(`；明确「只有 public 用例方法提交，私有辅助方法不提交」。

### QA-12 消费者关闭了进程级共享的异步 Redis 客户端
- Dimension: 6 | Severity: minor | 工作量: S
- Evidence：`platform_core/redis_async.py:12-14` 明确禁止关闭缓存实例；`consumer.py:165` 拿的正是共享实例，`:210-212` 却关掉；之后 `backend/app/__init__.py:225-233` 还要停止 `llm_usage_flush` 与 `llm_health_patrol`。
- 后果：连接池在停机阶段被提前断开（redis-py 惰性重连，实际影响有限），属违反契约。
- Suggestion：消费者自建连接，或 stop 时不关共享实例。

### QA-13 async 方法里做同步文件 IO 与无超时子进程，阻塞事件循环
- Dimension: 5 | Severity: **major**（库规模未核实） | 工作量: M
- Evidence：`skill_service.py:151` `scan_library` 里 `iterdir`，`:201` 同步 `read_text`，`:84-91` `_content_hash` 用 `rglob` 同步读出每个文件全部字节；`list_manifests` / `update_manifest` 同步读写（`:622-654`）且非原子写（`_write_back_meta` 反而用了 tmp+rename，`:713-718`）；`sync_adapters` 的 `communicate()` 无超时（`:666-672`）；`power_market/hub_import.py:141-143, 288-290` `shutil.copytree`（是否处在 async 上下文未核实）；ruff ASYNC240=10、ASYNC230=2（`evidence/ruff-extended.txt:14,27`）低估了问题——阻塞调用藏在同步辅助函数里 ruff 看不到。
- 后果：`APP_ROLE=all` 时消费者循环、webhook、健康检查与扫描同在一个事件循环（`app/__init__.py:101-108`），一次扫描即可卡住整个进程，包括数据闭环。
- Suggestion：扫描单元整体放进 `asyncio.to_thread`；子进程加 `asyncio.wait_for` 且超时 kill；清单写入改原子写。

### QA-14 回流与 LLM 路径的 N+1 查询，以及软删除语义
- Dimension: 5 | Severity: minor | 工作量: S
- Evidence：`consumer.py:665-666` 逐个 `get_by_id`（仓储已有 `get_by_ids`，`spider_task_repository.py:30-36`）；增量任务每条消息一次 `find_by_content_hash`，一批最多 50 次（`consumer.py:710-713`）；`find_by_content_hash` 不过滤 `deleted_at`（`spider_result_repository.py:201-214`，模型带 `SoftDeleteMixin`，`spider_result.py:12`）；`_failover` 查两次候选链。
- 后果：多余查询往返；用户软删的结果永远无法再被采集且静默跳过。
- Suggestion：`get_by_ids` 一次取；`IN` 一次查重或直接依赖 QA-1 的 INSERT IGNORE；软删后能否重采需产品明确。

### QA-15 死代码、重复实现与过渡门面残留
- Dimension: 1 / 7 | Severity: minor | 工作量: S
- Evidence：`consumer.py:840-925` `_ingest` / `_mirror_result` 生产代码无调用方，重复了哈希与 extra 处理且绕过配额检查；`platform_core/db.py:72-82, 146-151, 231-232` 同步引擎与 `mysql_session` 在 backend/platform_core/scrapy/scripts 下无调用方，但启动时仍建连接池并同步连接一次；`_create_redis_client_for_db`（`:185-204`）无调用方，每次调用新建 100 连接的池；`consumer.py:49-54` 仍经 `spider_service` 门面导入再导出的符号（应直接用 `spider_common`）；`spider_service.py:24` 写 `app/external_api/webhooks.py:81`，实际为 `backend/app/external_api/v1/webhooks.py:80-82`；`consumer.py:450` `__init__` 放在各方法之后，`:402` 引用的类常量定义在 `:559`。
- Suggestion：删死代码；门面剩余调用方迁移后删除 `spider_service.py` 并从 R12 白名单移除。

### QA-16 用 `"pytest" in sys.modules` 切换生产/测试行为；异步 Redis 无 socket 超时
- Dimension: 3 / 8 | Severity: minor | 工作量: S
- Evidence：`platform_core/db.py:16, 90-93` 与 `redis_async.py:24, 56-70` 靠 pytest 是否已导入切换行为，1954 个测试都不经过生产态连接池与缓存路径；覆盖率 redis_async 51%、db 70%、logger 17%（`evidence/pytest.txt:265, 271, 315`）；`redis_async.py:65-67` 无 `socket_timeout` / `socket_connect_timeout` / `health_check_interval`。
- 后果：生产依赖只要导入了 pytest 就会悄悄切到 NullPool；半开连接可能让命令无限挂起。
- Suggestion：显式配置开关（由 conftest 设置）；补超时与健康检查；给生产路径补单测。

### QA-17 可观测性：拿不到跨队列关联 ID，日志无结构化字段
- Dimension: 3 / 8 | Severity: minor | 工作量: M
- Evidence：消费者、任务服务、LLM 客户端都用 `get_logger("api")`（`consumer.py:57`、`spider_task_service.py:56`、`llm_client.py:38`），后台与请求日志混在一起；后台循环 `request_id` 恒为 `"-"`（`platform_core/logger.py:42`），入队消息不带关联 ID，无法从 API 请求追到分发/回流/回调；所读文件全是 f-string，未见 `bind(task_id=, tenant_id=)`；`_flush_batch` 成功只打 debug（`consumer.py:797-800`），INFO 看不到吞吐；`llm_chat` 入口日志无租户/维度/模型/耗时（`:453`）；轮转函数每写一行做一次 `os.stat`（`logger.py:14-32`）。
- Suggestion：入队时生成 `trace_id` 写进消息与任务行、后台用 `logger.contextualize`；拆独立 logger 名（worker / llm）；关键字段 bind 结构化；轮转改 loguru 内置 `rotation="00:00"` + 大小限制。

### QA-18 回流窗口是「至多一次」但文档未说明
- Dimension: 8 | Severity: minor | 工作量: L（若迁 Streams）
- Evidence：`consumer.py:576-599` 先 `lpop` 移除消息再在内存攒批；进程被 SIGKILL/OOM 时最多丢 50 条或 2s 数据，只有取消路径补 flush（`:605-615`）。
- Suggestion：短期 `LMOVE` 到 processing 列表、commit 成功后删除；长期 Redis Streams + XACK + 消费组。

### QA-19 入队注册表校验在 DB 异常时放行
- Dimension: 8 | Severity: minor | 工作量: S
- Evidence：`spider_task_service.py:188-193` 查注册表抛异常直接 return 放行；`_reject_if_blocked` 前的定义参数读取同样失败即放行（`:213-217`）。
- 后果：停用爬虫在 DB 抖动期间可入队。
- Suggestion：写入面注册表校验改 fail-closed，或明确注明为可接受风险。

### QA-20 R10 与 R11 门禁空通过
- Dimension: 3 / 7 | Severity: minor | 工作量: S
- Evidence：宪法要求每个 public 方法第一行 `logger.info`，但 `spider_task_service.delete_task`（`:733-735`，日志在方法末尾 `:755`）、`skill_service.list_manifests` / `update_manifest` / `sync_adapters`（`:622, 637, 656`）无入口日志，而 `evidence/arch.txt:14` R10 为 ✓；R11 正则只抓 `redis_client(...).` 链式调用，看不到藏在同步辅助函数里的阻塞 IO（见 QA-13）。
- Suggestion：R10 改 AST；新增「async 调用链中的同步 IO」检查（ruff ASYNC + 白名单）。

---

## Dimensions checked
1. 标准符合 ⚠️ — 代码与自身 docstring 契约多处矛盾：background_session（QA-11）、redis_async（QA-12）、update_task 消息（QA-3）、门面文档（QA-15）。
2. 标准质量 ⚠️ — 无 GWT，按模块 docstring 契约与测试判：租户槽测试为空断言（QA-2）；毒消息、重复消息、崩溃恢复的状态迁移无测试（QA-1、4、5）。
3. 证据有效性 ⚠️ — evidence 命令与退出码齐全有效（arch 0、ruff 0、ruff-extended 1 / 4753 条、pytest 1954 通过 / 41 跳过 / 81.47%）；但生产态路径测试不可达（QA-16），R10/R11 空通过（QA-20），ruff ASYNC 低估（QA-13）；本人全部为静态检查。
4. 安全 ⚠️ — QA-7（SSRF + 签名密钥复用）、QA-11（租户作用域被绕过）、QA-8（成本闸 fail-open）；可取：回流归属只认任务行。
5. 性能 ⚠️ — QA-9、13、14；回流批量化与计数缓存做得好。
6. 契约一致性 ⚠️ — QA-2、3、4、10、12。
7. 合规（宪法）⚠️ — `arch.sh` 13 红线 + 4 边界全过（`evidence/arch.txt:4-35`），但 R10 实际不成立（QA-20），background_session 仓内约定未被遵守（QA-11）；B1–B4 在已读文件未见违例。
8. 边界 ⚠️ — 并发 QA-2/4/5/19；重复/毒数据 QA-1；崩溃窗口 QA-18；超大扫描 QA-13；空 urls 已处理（`consumer.py:263-266`）。
9. 产品价值与体验 ⚠️ — 产品层 N/A、无截图（➖）；按用户可见行为：结果静默丢失或卡住（QA-1、6）、编辑不生效（QA-3）、任务永久停在「采集中」且占槽（QA-5）——直接伤害「采集出数环」核心价值。

## Strengths（改进时应保留）
1. 共享分布式锁实现正确：token + Lua 原子释放与续期，异常保守跳过，有 `lost` 感知（`platform_core/queues.py:154-277`）——QA-4 应直接复用。
2. 租户归属只认任务行：无主回流进死信留档，缺 task_id 的消息也进死信而非静默丢弃（`consumer.py:342-384`）。
3. 终态推进幂等：条件 UPDATE（`spider_task_service.py:516-530, 569-578`）；副作用放后台、强引用集合持有并传标量快照避开已关闭 session（`:84-103, 596-611`）；CSV 落盘放线程池（`:837`）。
4. 键名契约单一来源：集中在 `queues.py`；门禁基线全绿（arch 0、ruff 基线 0、1954 通过、81.47%）。
5. LLM HTTP 客户端卫生良好：共享连接池、connect/read 超时拆分、`trust_env=False`、`follow_redirects=False`、密钥用指纹作缓存键、4xx 不重试（`llm_client.py:58-102, 591-596`）；READ ONLY 会话布防/撤防失败时 invalidate、不把只读连接放回池（`platform_core/db.py:239-273`）。

## Improvement themes
1. **T1 数据闭环消息语义与幂等**（QA-1、3、4、6、18）— 目标：消息只带 `{task_id, attempt}`、DB 为唯一事实源；状态迁移全走 CAS；入库依赖唯一键幂等；REDO 有次数上限通向死信；hold 队列可回放可观测。顺序：QA-1（止血：INSERT IGNORE + 逐条隔离 + 死信）→ QA-4 → QA-3 → QA-6 → QA-18（Streams）。
2. **T2 并发槽与崩溃恢复**（QA-2、5、19）— 目标：按任务租约键由心跳续期；租户从 DB 读；原子占槽；回收循环受分布式锁保护。顺序：QA-2（S，立即可做）→ QA-5。
3. **T3 LLM 调用韧性与成本闸一致**（QA-8、9、10）— 目标：统一 `_budget_guard` 与月份口径；整体时限；模型列表缓存；遵守 Retry-After；主模型也查冷却。顺序：QA-8 → QA-10 → QA-9。
4. **T4 会话、事务与基建契约收口**（QA-11、12、13、15、16、20）— 目标：后台会话只走 background_session 且门禁强制；阻塞 IO 全部移出事件循环；清死代码与过渡门面；测试模式显式开关；R10 AST。顺序：QA-13 → QA-11（带门禁）→ QA-16 → QA-15 → QA-20 → QA-12。
5. **T5 安全与可观测**（QA-7、17）— 目标：每租户独立交付密钥 + SSRF 防护；`trace_id` 贯穿入队/分发/回流/回调；日志结构化。顺序：QA-7 → QA-17。

## 待 manager 执行的验证（静态结论，未复现）
- QA-1：新增测试——SQLite 按 metadata 建表，对同一非增量任务消息调两次 `SpiderTaskConsumer._flush_batch`，预期第二次 IntegrityError；再断言 `_ingest_loop` 异常分支把整批写进 `ITEM_REDO_QUEUE`（测试需先编写）。
- QA-2：fakeredis 跑 enqueue → `_dispatch`，断言 `sismember(tenant_active_key(tid, spider), task_id)` 为真（预期当前失败）。
- QA-3：enqueue 后 `update_task(params=新值)`，再 `lpop` 主队列断言消息 params 为新值（预期当前失败）。
- QA-10：`grep -nE "TZ|timezone" Dockerfile docker-compose.yml` 确认容器时区。
- QA-13：核实 `power_market/hub_import.py:141, 288` 所在函数是否为 async，以及 capability-library 技能目录数量与体积。
- QA-7：确认生产是否已向任何租户提供过 `WEBHOOK.SECRET_KEY` 用于验签。

## Decisions
- 仅审查，未推进 feature 状态，未采用任何默认值。

## Open questions（战略，需 PM / owner）
- **Q-1 非增量任务重复采到相同内容的产品语义？** (a) 按「租户+爬虫」全局去重：保留唯一键、INSERT IGNORE、只计新增；(b) 每任务各存一份：唯一键加 `task_id`；(c) 去掉唯一约束只留索引。推荐 (a) 并在界面标「本次新增 N / 重复 M」；若「我的结果」按任务查看则选 (b)，需评估存储配额影响。
- **Q-2 配额超限被 hold 的结果如何处置？** (a) 升级或清理后自动回放、7 天 TTL、租户可见计数；(b) 丢弃并通知。推荐 (a)。

## Product-delta
- 无（产品层 N/A）。

## Lessons（代码与迁移互证）
- 已有唯一索引的表 + 非幂等批量 INSERT + 失败后整批回放 = 跨租户毒消息死循环；幂等写与逐条隔离必须同时落地（`spider_result.py:16-19`、`030_*.py:42-45`、`consumer.py:616-622`）。
- 队列消息靠 LREM 按字符串整体匹配时，必须由唯一构造函数生成消息，否则编辑/搬迁静默失效（`spider_task_service.py:280-283` vs `:349-358`）。
- 只断言「用了哪个 key 调用」的测试是空断言，应断言状态结果（`test_spider_flow_engine.py:153` vs `consumer.py:291-295`）。

---

## Manager 注（2026-09-27）
- 自报严重度「1/13/6」与 QA 标题不符，按标题重新统计为 **blocker 1 / major 11（QA-2~11、13）/ minor 8（QA-12、14~20）**（R0 复核 QA-7 指出，manager 已核对）。
- QA-1 核心已复现：重复内容 flush → IntegrityError（`evidence/verify-R2-repro.txt`）；整批回放到 REDO、无上限为代码确认。
