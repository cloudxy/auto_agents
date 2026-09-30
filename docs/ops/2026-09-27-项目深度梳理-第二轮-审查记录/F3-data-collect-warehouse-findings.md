<!-- manager 落盘：2026-09-28，reviewer（G-fresh）最终交付原文逐字提取自其交付记录；packet 见 ../packets/ -->

# Findings：F3 数据采集（埋点和事件）与数据搭建（指标、计量、对账）

## Snapshot
- HEAD：82259f301c060dbf411424ec8775f29944e313e1。工作区只多了 docs/ops/。
- explore_roots `git ls-files -s` sha256：17b7d9b6084a89b67cdc5c261c27d7457a67355999bdf01ce6861add004ee36b，由 manager 计算，这里原样照抄。
- reviewer：sdlc-workflow:reviewer（G-fresh，只读）。packet：`/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/F3-data-collect-warehouse/packets/2026-09-27-2310-review-reviewer-F3-data-collect-warehouse.md`
- 判据：findings 9 维框架，以 collect 和 warehouse 两个 skill 的优秀标准衡量（粒度、口径、血缘、对账、重放）。
- 做了什么：只做了静态阅读，看了 3 张截图，引用了 manager 已记录的执行（devdb-readonly.txt、ui-runtime-summary.md）。**我没有执行任何命令，下面没有一条是我自己复现的**。需要复现的命令都写在文末。
- 与第一轮去重：R2 的 QA-8（LiteLLM 预算读数为 None 时 fail-open）和 QA-10（月度闸执行两次）不重复报。本报告的 QA-6 和 QA-7 是新的机制（时钟混用；Redis 丢键时返回 0 而不是 None），和它们只是互补。

**结论**：共 14 条，blocker 0 / major 11 / minor 3。
- **核心问题**：埋点有事件，但没有追踪计划，也没有契约。
- **身份与流量**：身份串不起来，内部流量也没有过滤。所以漏斗和北极星目前算不出来。
- **计量**：Redis 计数和数据库各算各的，没有对账。成本口径是空的，中转用量没有进入计量。
- **看板**：时区有三套时钟，质量分只算了字段有没有填。现在的数字不能直接拿来做产品决策。

---

## FINDINGS

### QA-1 没有追踪计划，也没有统一的事件注册表：注册表有两份且内容不一致，服务端对任意事件名都照单全收，同一个动作有两个事件名
- Dimension: 1 / 6 | Severity: **major** | 工作量: M | 核验方式：静态 + devdb 已记录执行
- **现象**：
  - devdb 里有 13 种事件（devdb-readonly.txt:38-50）。
  - 其中 `sync_completed`、`detail_opened`、`market_list_paged`、`outbound_key_issued`、`relay_token_call_succeeded` 这 5 种，不在契约 `platform_core/schemas/product_event.py:7-38` 的任何注册元组里。
  - 代码里还在发、但同样没注册的事件：`payment_succeeded`、`payment_failed`（payment_notify_service.py:175-184、billing_service.py:281）、`offline_order_submitted`（billing_service.py:42）、`sync_failed`、`import_*`（market_events.py:34-38）。
  - 在 docs/ 和 .sdlc/ 下用 Glob 查 `*tracking*|*埋点*|*指标*|*metrics*.md`，结果为空。
- **触发条件**：任何新功能调用 `emit_product_event(session, "<任意字符串>")`。
- **根因**：
  - `backend/services/product_event_service.py:103`：`event_name: str` 不做任何校验。props 没有 schema，也没有版本。
  - 注册表重复且已经分叉：`market_events.py:21-31` 的 `MARKET_EVENT_NAMES` 有 9 个（含 `market_list_paged`），`platform_core/schemas/product_event.py:10-19` 只有 8 个。
  - 同一个动作发两个名字：
    - 打开详情：`market_detail_viewed` 和 `detail_opened` 都发（`backend/app/api/v1/public_skills.py:222-229`）。devdb 里分别是 13 和 8，数量已经对不上。
    - 导出：`results_exported` 和 `data_export_completed` 都发（`spider_query_service.py:200-209`）。
- **后果**：口径靠口口相传。同一个动作按不同事件计数，结果不同。拼错的事件名会静默入库，没法做缺失检测。换人以后改埋点会直接断掉历史口径。
- **修复方案**：
  1. 建立唯一的追踪计划，比如 `config/events.yaml` 或 `platform_core/schemas/events.py`，每个事件写清楚：名字、owner、触发时机、主语（anonymous / actor / tenant）、props schema、版本、是否计入漏斗。
  2. `emit_product_event` 按注册表校验：生产环境遇到未知名字，记 warning 并给 dropped 计数加一；测试环境直接 raise。
  3. 同义事件二选一，另一个标 deprecated，设一个并存期，到期删除。
  4. props 里带 `v`（schema 版本）。
- **应补的测试和验收**：
  - 契约测试：AST 扫描所有 `emit_product_event` / `emit_market_event` 调用里的字面量，断言它们都在注册表里。
  - 每个事件的 props 都能通过 schema 校验。
  - 验收：追踪计划文档覆盖 devdb 里现有的 13 种事件。

### QA-2 身份串不起来：市场浏览类事件既没有匿名身份，也没有登录身份；admin 和官网不同源；登录事件不带 anonymous_id
- Dimension: 1 / 9 | Severity: **major** | 工作量: M | 核验方式：静态（需要 manager 用 V2 确认各事件主语空值比例）
- **现象**：devdb 里量最大的 `market_list_viewed`（87 条）和 `market_detail_viewed`（13 条）都是服务端发的。按代码看，它们既没有 anonymous_id，也没有 actor 或 tenant。
- **触发条件**：访客或已登录用户浏览官网市场列表、打开详情、搜索。
- **根因**：
  - `public_skills.py:127-131`：接口里已经拿到了 `user`（:114），却没有传给 `emit_public_list`。`market_events.py:112` 和 `:116-119` 只传了 props。
  - `market_events.py:122-127`：`emit_public_detail` 不带任何主语。
  - 只有翻到第 2 页以后，`market_list_paged` 才带 anonymous_id（`public_skills.py:82-89`，前端 `capabilities.ts:79`）。
  - `auth_service.py:22-31`：`login_succeeded` 不带 anonymous_id。admin 在 :9112，官网在 :9113，两边的 localStorage `aa_anonymous_id` 不共享。
  - `frontend/official/src/services/beacon.ts:37-38`：localStorage 不可用时，**每次调用**都生成一个新的 `anon-${Date.now()}`，同一个访客会被拆成 N 个人。
- **后果**：「官网浏览 → 市场 → 注册 → 登录 → 首任务 → 导出」没法按人串起来。注册转化、市场到订阅的转化、激活率都算不出来。唯一的缝合点是 signup（`tenant_signup_service.py:126-137`，这里带了 aid），但注册前的浏览大部分没有 aid。
- **修复方案**：
  1. 官网所有公开请求统一带 `X-Anonymous-Id` 头。后端用依赖注入把它放进请求上下文，由 `emit_market_event` 自动补上。
  2. 用户已登录时，补齐 `tenant_id`、`actor_user_id`、`role`。
  3. 登录请求带上 anonymous_id，写进 `login_succeeded`。
  4. 建一张 `identity_links(anonymous_id, user_id, first_linked_at)`，在 signup 和登录时写入。
  5. beacon 在 localStorage 不可用时退回 sessionStorage，或者用一个内存单例 id，保证同一会话里 id 稳定。
- **应补的测试和验收**：
  - E2E：官网浏览列表 → 注册 → 登录，然后用 SQL 按 anonymous_id join 到同一个 actor_user_id。
  - 单测：`emit_public_list` 在有 user 时写入 tenant 和 actor。

### QA-3 内部、夹具、自动化流量过滤只覆盖了「有 tenant_id 且在夹具表里」这一种情况；devdb 292 条全部标成真实流量
- Dimension: 8 / 9 | Severity: **major** | 工作量: M | 核验方式：静态 + devdb 已记录执行（需要 V3 确认）
- **现象**：
  - 13 种事件的 `fixture` 全是 0（devdb-readonly.txt:37-50），`internal_fixture_tenants` 是 0 行（:34）。
  - `login_succeeded`、`outbound_key_issued`、`relay_token_call_succeeded` 三个事件的 first 都是 `2026-09-14 09:41:34`，同一秒（:42、49、50），很像脚本或测试写进了 dev 库。
  - 本轮 manager 用 Playwright 巡检（官网 8 页 + admin 登录 + /newapi），也会产生 `official_page_viewed`、`login_succeeded`、`duty_entry_opened`，并且都记成真实流量。
- **根因**：
  - `product_event_service.py:49-52`：`tenant_id is None` 时直接返回 False。所以所有匿名事件、所有平台超管事件都是 0。
  - `newapi.py:62-66`：`duty_entry_opened` 没有 tenant。
  - `public_skills.py:224-229`：管理员 preview 也会发 `detail_opened`。
  - 事件里没有 UA、webdriver、环境（env）这类标记，想事后过滤也没有依据。
- **后果**：样本量小的时候（总共 292 条），内部流量会让指标严重失真，而且事后分不出来。
- **修复方案**：
  1. 新增列 `traffic_class ENUM(real, internal_staff, fixture, automation)`，也可以先放进 props 过渡。
  2. 判定规则：平台超管或 preview 记为 internal_staff；租户在夹具表里记为 fixture；前端上报 `navigator.webdriver` 或 UA 类别，由服务端判为 automation；`APP_ENV != prod` 时一律不是 real。
  3. 查询 API 和指标默认只看 real。
- **应补的测试和验收**：四类流量各一条单测。E2E 用 Playwright 访问后，断言写入的是 automation。

### QA-4 埋点丢了也看不见，重试会重复计数：CTA 点击走 axios，跨源跳转时可能被取消；没有事件 id；服务端失败只打日志
- Dimension: 3 / 8 | Severity: **major**（丢失率还没测） | 工作量: S–M | 核验方式：静态
- **现象**：devdb 里 `official_cta_clicked` 22 条，`official_page_viewed` 79 条，两者的比例无法判断真假。
- **触发条件**：在官网点「登录」「进入后台」这类 CTA，页面马上跳到 :9112（跨源）。另外，服务端独立会话写入失败时也会丢。
- **根因**：
  - `beacon.ts:48`：用 `api.post` 发送，没有用 `navigator.sendBeacon` 或 `fetch(..., {keepalive:true})`。页面卸载时请求可能被取消。
  - `product_event_service.py:110-111`：失败只打 warning，没有计数、没有死信、也不能重放。
  - `platform_core/models/product_event.py:4`：注释写明「v1 无精确一次键」，客户端或网关重试会产生重复。
- **后果**：转化率被系统性低估。事件是否丢失完全没法观测，违背「日志即证据」。
- **修复方案**：
  1. 前端给每个事件生成 `event_id`（uuid），用 sendBeacon 发送，失败时退回 keepalive。
  2. 后端加一列可空的 `event_id` 和唯一索引，写入用 INSERT IGNORE 去重。
  3. 加 `product_event_dropped_total` 计数（按 event_name 维度），写入失败时把事件推到 Redis 死信，便于重放。
- **应补的测试和验收**：
  - 前端单测：trackCta 调用了 sendBeacon。
  - 后端：同一个 event_id 连发两次，只落一行。
  - 模拟写入失败：dropped 计数加一，死信里有记录。

### QA-5 公开接口的读请求会同步写主库，没有去重，props 大小不设上限，限流故障时直接放行
- Dimension: 4 / 5 | Severity: **major** | 工作量: M | 核验方式：静态
- **现象和触发条件**：
  - 未鉴权的 `GET /public/capabilities`、`/public/skills`、详情页，每次请求同步写 1 到 3 行事件。每行都新开一个会话再 commit（`public_skills.py:127-132`、`218-229`、`288-293`；`product_event_service.py:59-86`）。
  - React Query 重新拉取、预取、爬虫抓取，都会各记一次 `market_list_viewed`。
  - `POST /public/events` 的 props 是 `dict[str, Any]`，没有大小限制，也没有键白名单（schema `product_event.py:56`）。
- **根因**：
  - 限流在 Redis 故障时放行：`public_skills.py:74-75`；`rate_limiter.py:74-77` 设置了 `fail_open=True`。
  - 事件同步直写主库，没有队列缓冲。
- **后果**：
  - 未登录就能每个 IP 每分钟写 120 条任意 JSON 进主库，存储可被滥用，也会被放大写入。
  - 公开读接口的延迟里多了一次连接和提交。
  - 浏览事件数和真实浏览人次脱钩。
- **修复方案**：
  1. props 按注册表（QA-1）只保留白名单字段，序列化后不超过 2KB。
  2. 公开事件先写 Redis Stream 或队列，后台批量落库，和爬虫回流保持「采集与存储分离」。
  3. 服务端按 `(anonymous_id, event_name, 关键 props)` 在 30 秒窗口内去重。
  4. 写路径的限流故障时丢弃事件，而不是放行写入。
- **应补的测试和验收**：
  - 超大 props 返回 422，或被截断。
  - 同一访客 30 秒内重复刷新列表，只记一条。
  - 压测：公开列表 p95 延迟不因事件写入上升。

### QA-6 三套时钟混在一起：Python UTC naive、MySQL 会话本地 NOW()、上海业务日。7 日窗口和按日分桶对不齐，API 把 UTC 时间标成 Asia/Shanghai
- Dimension: 6 / 8 | Severity: **major** | 工作量: M（加上历史数据迁移是 L） | 核验方式：静态（需要 manager 用 V1 确认数据库时区）
- **现象**：packet 提到 devdb 和 UTC 差 8 小时。
  - 数据中心截图里「采集时间 2026-09-14T09:03:03」没有带时区（admin_data-1440.png）。
  - 事件表「发生时间」直接显示原始值（`frontend/admin/src/pages/ProductEvents.tsx:47`）。
- **根因**：
  - `product_events.occurred_at` 由 Python 写入 UTC naive（`product_event_service.py:22-24,39`）。同一行的 `created_at` 和 `updated_at` 却用 `CURRENT_TIMESTAMP`（`product_event.py:33-38`），取的是数据库会话时区。`platform_core/db.py` 里没有固定 `time_zone`（Grep `time_zone|init_command` 无匹配）。
  - `spider_tasks` 和 `spider_results` 的 `created_at` 用 `server_default=func.now()`（`spider_task.py:43`、`spider_result.py:35`），也是数据库本地时间。统计窗口 `since` 却是「上海零点转成 UTC naive」（`quota_service.py:67-73`、`spider_query_service.py:380`），然后拿去和数据库本地时间比较。分桶用 `DATE(created_at)`（`spider_task_repository.py:116`、`spider_result_repository.py:191`）。
    - 如果数据库是 +08:00：窗口会提前 8 小时，多算 T-7 那天 16:00–24:00 的数据。
    - 如果数据库是 UTC：分桶是按 UTC 日切的，标签却写着上海日。
    - docstring 声称「同一套上海业务日」（`spider_query_service.py:377`），与实现不符。
  - `ProductEventListOut.timezone` 固定写 `"Asia/Shanghai"`（`platform_core/schemas/product_event.py:82`），但里面的值是 UTC。
  - `PublicEventIn.occurred_at` 接受客户端传入的任意时间，包括带偏移的（schema :55）。pymysql 写 DATETIME 时会丢掉 tzinfo，带 +08:00 的值会按墙钟时间存，偏 8 小时。客户端还能伪造过去或未来的时间。
  - relay 这一张表里就有三种时钟：`last_used_at` 取网关的带时区时间（`relay_usage.py:22,54`），`spend_synced_at` 是 UTC naive（:52），`created_at` 是数据库的 NOW()。
- **后果**：近 7 日趋势、成功率、结果量有 8 小时错位。跨表 join（比如事件和任务）会差 8 小时。凌晨 0–8 点的数据会被算进前一天。
- **修复方案**：
  1. 在连接层固定 `time_zone='+00:00'`（aiomysql `init_command` 或 `connect_args`）。所有 DATETIME 统一存 UTC。
  2. 分桶统一用 `CONVERT_TZ(col,'+00:00','Asia/Shanghai')`，或在 Python 侧切日。
  3. API 输出带 `+00:00` 的 ISO 时间，前端按上海时区渲染。
  4. 公开埋点忽略客户端传来的 occurred_at，或者限制在 ±5 分钟内并归一到 UTC。
  5. 先确认 V1 的结果，再写一次性迁移，把历史数据转换过来。
- **应补的测试和验收**：
  - 冻结时间在上海 2026-09-27 01:00 创建任务，断言它分到 09-27 这一桶，并且在 7 日窗口内。
  - 事件 API 返回的时间带偏移。
  - 回归：`SELECT TIMESTAMPDIFF(MINUTE, occurred_at, created_at)` 约等于 0。

### QA-7 LLM 月度用量有两个事实源，不对账：Redis 月键丢了时，配额读数变成 0 并放行；flush 在提交后、删键前崩溃，会重复累加
- Dimension: 6 / 8 | Severity: **major** | 工作量: M | 核验方式：静态（V4 可以比对两个数据源）
- **现象**：配额闸读 Redis 月 hash，用量看板读 `llm_token_usage` 表，两边的数字没有任何对账。
- **触发条件**：
  - Redis 重启且没开持久化、键被 maxmemory 淘汰、有人执行了 FLUSHDB。
  - flush 在第 262 行和第 264 行之间进程被杀掉。
- **根因**：
  - `llm_usage_service.py:137-144`：`get_tenant_month_used` 在月键不存在时，`hgetall` 返回空，函数于是返回 **0 而不是 None**。`quota_service.py:269-277` 只在 None 时才去数据库查，所以不会回源，本月已用量被当成 0。（这和 R2 QA-8 讨论的 None 分支不是一回事。）
  - `llm_usage_service.py:262` commit，`:264` 才删认领键。docstring（:203）自己也写着 at-least-once；而 `llm_token_usage_repository.py:35-39` 的 upsert 是**累加**，又没有幂等键，重放一次就重复计一次。
- **后果**：租户在月中可以再用满一整个月的配额。看板上的数字会偏高，不能作为计费依据。
- **修复方案**：
  1. 月键不存在时返回 None 并回源数据库：本月 `SUM(llm_token_usage)` 加上还没 flush 的日键。或者在 miss 时用数据库数据重建月键。
  2. 给 flush 加幂等：在同一个事务里写一张 `llm_usage_flush_log(claim_key, stat_date)`，加唯一约束；已经存在就只删键、不再累加。
  3. 每天跑一次对账：Redis 月值、数据库 SUM、LiteLLM spend 三方比对，误差超过 1% 就告警。
- **应补的测试和验收**：
  - fakeredis：删掉月键后，配额读数等于数据库合计。
  - 模拟 commit 成功、delete 抛异常，flush 连跑两次，数据库合计不变。

### QA-8 成本口径是空的：config 和网关维度的成本永远是 0，每次 flush 都向上取整，和网关实际花费不对账
- Dimension: 1 / 9 | Severity: **major** | 工作量: M | 核验方式：静态 + 截图
- **现象**：用量看板截图（admin_usage-1440.png）里，「LLM 成本（本月 0.00 元）」，供应商 `config` 用了 786 tokens，金额 0.00。`metrics.yaml:21-26` 的 `llm_cost_cents_month` 在这条路径上没有意义。
- **根因**：
  - `llm_usage_service.py:323, 340-344`：只给有 provider_id 的行计价。`config` 维度（`_parse_provider_id` 在 :66-73）的 provider_id 是 None，所以 cost 为 0。
  - `:316-319`：`(tokens*price+999)//1000` 在每一次 flush、每一行上向上取整。60 秒 flush 一次，每行每次最多多算 1 分，而且用的是 flush 那一刻的单价。
  - LiteLLM 自己的 spend（`/key/info`、`/api/v1/litellm/spend`）从来没有和 cost_cents 对过账。
- **后果**：看板显示成本为 0，对租户和平台都是误导。以后按量计费时，没有可信的来源。
- **修复方案**：
  1. 网关路径的成本以 LiteLLM 每次调用的 `spend` 为准。config 路径维护一张带版本的「模型→单价」价目表。
  2. 用微分（1e-6 元，BigInteger）累计，只在展示或出账时取整。
  3. 每行记录价目版本。
  4. 没配单价时，界面显示「未配置单价」，不显示 0.00。
- **应补的测试和验收**：
  - 同样的 token 分 3 次 flush 和 1 次 flush，算出的成本相等。
  - config 路径配置单价后，成本不为 0。
  - 验收：月度成本和 LiteLLM spend 的误差在阈值内。

### QA-9 中转（relay）用量没有进入租户计量：用量值可能倒退或被截断；每次看详情都全量拉取网关日志；事件名和含义不符
- Dimension: 5 / 6 / 9 | Severity: **major** | 工作量: M–L | 核验方式：静态（需要 V6 确认 LiteLLM `/spend/logs` 是否有条数上限）
- **现象**：
  - 用量看板「LLM Token（本月）」只算平台内部 llm_client 那条路径（`quota_service.py:325-343`），不包含中转令牌的消耗。
  - `relay_tokens.used_tokens` 是累计值，没有按月的粒度。
- **根因**：
  - `llm_gateway/admin.py:163-183`：`list_key_spend_logs` 不把 page/page_size 传给网关。`_normalize_spend_logs`（:132-144）永远返回 `total_pages=1`、`total_is_capped=False`。所以 `relay_usage.py:33-43` 的 10 页循环是死代码，每次都把这个 key 的**全部历史日志**拉下来求和。
  - `relay_usage.py:51`：`row.used_tokens = max(0,int(used))` 是直接覆盖。网关一旦截断列表或按保留期清理，计数就会倒退。
  - 详情页的 GET 也会触发网关调用并提交（`relay_service.py:270-278`）。
  - `relay_usage.py:58`：事件只在「0 变成 ≥1」时发一次，名字却叫 `relay_token_call_succeeded`。实际含义是「首次使用」，不是每次调用成功。
- **后果**：
  - 租户看到的用量偏少，月度配额也管不到中转。
  - 用得越多，详情页越慢（每次 O(调用次数)）。
  - 用量数字可能变小，失去单调性。
- **修复方案**：
  1. 按 `spend_synced_at` 作游标，带起止日期增量拉取。
  2. 落一张 `relay_usage_daily(tenant_id, token_id, stat_date, tokens, spend)` 事实表，累加写入并保持单调。
  3. 用量看板把「平台内部 LLM」和「中转」分两行展示；是否计入配额见 Q-1。
  4. 事件改名为 `relay_token_first_used`，或者改成按日汇总的事件。
- **应补的测试和验收**：
  - 假网关返回截断的列表时，used_tokens 不下降。
  - 跨月时按月切分正确。
  - 详情接口的耗时和历史日志条数无关。

### QA-10 「数据质量评分」算的是字段填了没有，不是数据质量；仪表盘却按优秀、较差来分级展示
- Dimension: 1 / 7 / 9 | Severity: **major** | 工作量: M | 核验方式：静态 + 截图
- **现象**：仪表盘截图（admin_dashboard-1440.png）显示「平均评分 75/100，基于最近完成任务 #3（1 条数据）」。标题是「数据质量概览」，看起来像全局结论。
- **根因**：
  - `scrapy/pipelines/quality.py:38-58`：完整率的分母是 item 声明的**所有**字段，包括内部字段 `task_id`、`id`、`created_at`、`updated_at`、`extra`，甚至包括 `_quality_score` 自己（`scrapy/items/__init__.py:9-31`）。算分时 `_quality_score` 必然是空的，所以 BaseItem 最高只能拿 95 分。子类字段越多，空着的越多，分数越低，这和数据真假无关。
  - 去重只在单个进程里按 url+title 做（:32、50-55），跨任务、跨 worker 都不去重。
  - 没有格式、值域、新鲜度校验。
  - 前端只取「最近完成的 1 个任务」（`Dashboard.tsx:73-82, 280`）。平台超管看到的是跨租户最新的那个任务。
- **后果**：宪法里「数据质量先于数量」没法度量。租户会根据一个结构性分数去判断数据能不能用。
- **修复方案**：
  1. 按爬虫定义里的 required 和 core 字段计算，排除内部字段。
  2. 拆成完整性、有效性（schema、正则、值域）、唯一性（content_hash 和库内比对）、新鲜度四个分项，并带规则版本。
  3. 看板改成近 7 日按租户的加权平均，再加一个最差任务列表，并注明口径。
- **应补的测试和验收**：
  - 业务字段全填时得 100 分，内部字段不影响分数。
  - 同一 URL 跨任务重复时，唯一性分项降低。

### QA-11 指标注册表 metrics.yaml 和实现、看板脱节，也没有北极星和漏斗指标；仪表盘一排 KPI 混用了不同时间窗口却没标注
- Dimension: 1 / 2 / 6 | Severity: **major** | 工作量: M | 核验方式：静态 + 截图
- **现象**：
  - `config/metrics.yaml:2-32` 只有 5 个运维和资源指标。没有北极星，也没有「注册 → 首任务 → 首结果 → 导出」「市场浏览 → 订阅」这些驱动指标，尽管对应事件已经存在。
  - 仪表盘截图里：「任务总数 1」「平均运行时长 4.0s」是全量口径（`spider_query_service.py:381, 400`）；「成功率 -」「近 7 日采集结果 0」是 7 日口径（:382-385, 402）。卡片上都没写窗口。
- **根因**：
  - 全仓只有 `backend/tests/test_metrics_registry.py` 读 metrics.yaml，而且只检查六个字段在不在（:9-15），是空断言。看板上的每个数都是各个 service 手写 SQL 算出来的。
  - 已经出现漂移：
    - `result_volume` 定义为 `COUNT(spider_results)`，用量页「结果存储」却用 `count_owned_by_tenant`，排除了候选数据（`quota_service.py:244-252`）。
    - `llm_tokens_month` 没写时区（实现是 Asia/Shanghai 月），也没写是否包含中转。
    - 所有指标都没有粒度（租户还是平台）、内部流量排除规则、owner 和版本。
- **后果**：定义和数字各说各的，每次复盘都要重新讨论口径。产品价值没有可追踪的主指标。
- **修复方案**：
  1. 把 metrics.yaml 升级成语义层：加上 grain、timezone、filters（排除内部流量）、source_events、owner、version。
  2. 补上北极星和漏斗指标，选择见 Q-3。
  3. 看板上的每个数字引用一个 metric id，由契约测试比对 SQL 和 yaml。
  4. KPI 卡片标注窗口。
- **应补的测试和验收**：契约测试：看板接口字段和 metric id 一一对应。北极星能按周算出来，并且排除内部流量。

### QA-12 隐私和 PII：敏感字段只按 4 个精确键名过滤；搜索词原样存储；没看到事件保留期
- Dimension: 4 | Severity: minor | 工作量: S | 核验方式：静态（保留期需要 V7）
- **根因**：
  - `platform_core/schemas/product_event.py:41-47`：只删 `password`、`admin_password`、`token`、`access_token` 这 4 个精确键。大小写不同、嵌套的、`api_key`、`secret`、`phone`、`email` 都照样入库。
  - `market_events.py:116-119`：`market_search_submitted` 原样存了搜索词 `q`。
  - `newapi.py:65`：props 里又冗余存了一遍 `user_id`。
- **修复方案**：props 默认拒绝，只保留注册表白名单里的字段。搜索词截断，并对邮箱、手机号脱敏。给 product_events 设保留期（比如 180 天）。
- **应补的测试和验收**：嵌套的 `{"Password": ...}`、`{"meta": {"api_key": ...}}` 会被剥离。含邮箱的搜索词会被脱敏。

### QA-13 用量看板直接露出内部维度标识；「成员用量分摊」只算了任务创建数，标题承诺过度
- Dimension: 9 | Severity: minor | 工作量: S | 核验方式：截图 + 静态
- **现象**：截图里「供应商」一列显示 `config`（`Usage.tsx:186` 直接渲染内部维度，`provider:<id>` 也会原样显示）。「成员用量分摊（任务创建数）」一栏显示暂无数据。
- **根因**：`quota_service.py:286-309` 只按 `created_by` 聚合任务数，LLM 用量没有成员维度（docstring :289-290 自己也承认）。
- **修复方案**：维度键映射成供应商显示名，`config` 显示为「平台默认模型」。卡片改名为「成员任务创建数」，或者在 `record_usage` 里补上 actor 维度。

### QA-14 【待验证】「质量分布」图截图里一根柱子都没有，但按数据「良好(60-80)」应该是 1
- Dimension: 9 | Severity: minor | 工作量: S | 核验方式：截图（静态无法定位原因）
- **现象**：平均分、最低分、最高分都是 75，总共 1 条，那么良好档应该计 1。后端键（`spider_query_service.py:299-304`）和前端键（`Dashboard.tsx:292-295`）是一致的。截图里没有柱子，可能是截图时柱子动画还没播完，也可能真的没渲染出来。
- **需要 manager 复核**：见 V5。如果确认没有渲染，再定位 Recharts 里 `Bar` 和 `Cell` 的用法。

---

## Dimensions checked
1. 标准符合 ⚠️：没有追踪计划，注册表分叉（QA-1）。docstring 说「同一套上海业务日」与实现不符（QA-6）。质量分数名不副实（QA-10）。metrics.yaml 没被实现采用（QA-11）。
2. 标准质量 ⚠️：没有埋点相关的 GWT。`test_metrics_registry` 是空断言（QA-11）。去重、重放、时区都没有测试（QA-4、6、7）。
3. 证据有效性 ⚠️：只有静态阅读，加上 manager 的 devdb 和截图记录。埋点丢失没法观测（QA-4）。本人没有复现任何一条。
4. 安全 ⚠️：未鉴权写路径被放大、props 无上限、限流故障放行（QA-5）；PII（QA-12）。产品事件查询只对超管开放，非超管返回 404 同形（`product_events.py:49-69`），这一点是合格的。
5. 性能 ⚠️：中转每次全量拉日志（QA-9）；公开读请求同步写库（QA-5）。
6. 契约一致性 ⚠️：时区标签写错（QA-6）；同义事件和事件含义不符（QA-1、QA-9）；Redis 和数据库口径不一致（QA-7）。
7. 合规（宪法）⚠️：「数据质量先于数量」无法度量（QA-10）；「日志即证据」下埋点丢失看不见（QA-4）。补充 R2 QA-20 的证据：`QuotaService.check_task_concurrency`、`check_llm_tokens_month`、`usage_overview`、`usage_by_member`（`quota_service.py:222, 263, 286, 311`）第一行不是 `logger.info`。本切片没有重跑 arch.sh。
8. 边界 ⚠️：Redis 丢键（QA-7）；提交和删键之间崩溃（QA-7）；网关截断（QA-9）；localStorage 不可用（QA-2）；客户端传入时间（QA-6）。
9. 产品价值与体验 ⚠️：漏斗和北极星算不出来（QA-2、3、11）；用量看板上的成本和中转用量有误导（QA-8、9、13）；质量分有误导（QA-10、14）。➖ 部分：只有平台超管视角的截图，没有租户负责人视角，所以租户侧的体验没有判断。

## Strengths（改进时应保留）
1. 事实不跟着主路径回滚：产品事件用独立短会话写入；SQLite 写锁时退回主会话兜底；MySQL 会话级 `innodb_lock_wait_timeout=1`（`product_event_service.py:59-100`）。
2. LLM 用量聚合的骨架是对的：rename 认领加分布式锁，ON DUPLICATE 累加，日键设了 TTL（`llm_usage_service.py:196-267`、`llm_token_usage_repository.py:24-41`）。只差一个幂等键（QA-7）。
3. 业务日和业务月统一由 `shanghai_*` 函数产生（`quota_service.py:52-73`）。用量页明确写着「本月按 Asia/Shanghai 日历」（截图）。
4. 事件写入时就固化夹具标记，并定义了 NULL 表示「列上线前的旧事件」（`product_event.py:40-43`、`product_event_service.py:83`）。这个设计是对的，只是覆盖面太窄（QA-3）。
5. 公开埋点入口有收口：`Literal` 只允许两种公开事件，有限流，有敏感键剥离（schema :53、:58-61）。仪表盘区分了加载失败和真零（`Dashboard.tsx:104-111, 157-160`）。

## Improvement themes
1. **T1 追踪计划与事件契约**（QA-1、2、3、4、5、12）
   - 目标：只有一个事件注册表（名字、主语、props schema、版本）；每个事件有 event_id 用来去重；每个事件都有 traffic_class；公开事件经队列异步落库；丢失可以计数。
   - 顺序：QA-1 注册表和校验 → QA-4 event_id 和 sendBeacon → QA-2 身份头和 identity_links → QA-3 traffic_class → QA-5 队列化 → QA-12。
2. **T2 统一时钟**（QA-6）
   - 目标：连接层固定 UTC，所有落库都是 UTC，只在展示和分桶时转换到上海时区，API 输出带偏移。
   - 顺序：先跑 V1 → 固定连接层时区 → 修分桶和窗口 → 迁移历史数据 → 前端渲染。
3. **T3 计量事实表与对账**（QA-7、8、9）
   - 目标：内部 LLM 和中转各有一张日粒度事实表，写入幂等且单调；成本用微分并带价目版本；每天三方对账（Redis、数据库、LiteLLM）并告警。
   - 顺序：QA-7（S，改完就能止血）→ QA-9 → QA-8。
4. **T4 指标语义层与北极星**（QA-11、13）
   - 目标：metrics.yaml 带上粒度、时区、过滤条件和来源事件；看板数字都引用 metric id；补上北极星和漏斗；KPI 标注窗口。
   - 依赖：T1、T2。北极星要等 Q-3 决定。
5. **T5 数据质量可信度**（QA-10、14）
   - 目标：按四个分项评分，带规则版本，按租户和时间窗口聚合。
   - 顺序：先修公式、排除内部字段 → 再拆分项 → 最后改看板。

## 需要 manager 执行的验证（以上都是静态结论，未复现）
- **V1 时区**：
  ```
  mysql auto_agents -e "SELECT @@global.time_zone, @@session.time_zone, @@system_time_zone; SELECT id, event_name, occurred_at, created_at, TIMESTAMPDIFF(MINUTE, occurred_at, created_at) AS drift_min FROM product_events ORDER BY id DESC LIMIT 5;"
  ```
  如果数据库是 +08:00，drift_min 应该约为 480。
- **V2 事件主语**：
  ```
  SELECT event_name, COUNT(*) n, SUM(anonymous_id IS NULL) no_anon, SUM(actor_user_id IS NULL) no_actor, SUM(tenant_id IS NULL) no_tenant FROM product_events GROUP BY event_name;
  ```
- **V3 同秒种子**：
  ```
  SELECT id, event_name, tenant_id, actor_user_id, role, props FROM product_events WHERE occurred_at = '2026-09-14 09:41:34';
  ```
  然后看这些行是不是测试或脚本写入的。
- **V4 两个数据源比对**：
  ```
  redis-cli HGETALL llm:usage:m:202609
  SELECT tenant_id, SUM(total_tokens) FROM llm_token_usage WHERE stat_date >= '2026-09-01' GROUP BY tenant_id;
  ```
- **V5 质量分布**：
  ```
  curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:9111/api/v1/spiders/tasks/3/quality
  ```
  再用 Playwright 打开 /dashboard，等 2 秒后执行 `document.querySelectorAll('.recharts-bar-rectangle').length`。
- **V6**：确认 LiteLLM v1.100.0 的 `GET /spend/logs?api_key=` 有没有默认条数上限或保留期。
- **V7**：
  ```
  grep -n "product_event" backend/services/retention_service.py config/default/retention.yml
  ```

## Decisions
- 本轮只做审查，没有推进任何状态，也没有采用任何默认值。
- 严重度按影响和发生可能性来定，不是按数量凑的。

## Open questions（战略问题，待确认）
- **Q-1（战略，待确认）中转用量要不要计入租户的月度 token 配额和用量看板？**
  - (a) 并入同一个 `llm_tokens_month` 配额。
  - (b) 单独设配额，看板上单独一行。
  - (c) 只在中转页展示，看板不展示。
  - 推荐 (b)：两者的计费和成本结构不一样，合在一起会互相挤占配额。
- **Q-2（战略，待确认）租户侧要不要展示「LLM 成本（元）」，按什么口径？**
  - (a) 按网关实际 spend。
  - (b) 按平台价目表（带版本）。
  - (c) 不展示金额，只展示 token。
  - 推荐：如果目前不向租户按量收费，选 (c)。如果要收费，选 (b)，并和 (a) 每天对账。
- **Q-3（战略，待确认）北极星指标定什么？**
  - (a) 周有效交付租户数：本周至少有 1 个任务完成，且结果被导出或经 webhook 交付的租户（排除内部流量）。
  - (b) 周新增有效结果条数。
  - (c) 周市场订阅数。
  - 推荐 (a)：它直接对应「采集出数环」这个核心价值，而且现有事件（task_completed、results_exported）已经能支撑。
- **Q-4（战略，待确认）内部、夹具、自动化流量怎么处理？**
  - (a) 保留，用 traffic_class 标注，指标默认排除。
  - (b) 写入时直接丢弃。
  - 推荐 (a)：保留下来可以审计，也方便排查。

## Product-delta
- 无（产品层 docs/product 还没建立，N/A）。

## Lessons（只列已经从代码核实过的坑）
- 缓存读数用 0 同时表示「键不存在」和「真的是 0」，会让回源数据库的分支永远走不到（`llm_usage_service.py:137-144` 对照 `quota_service.py:269-270`）。
- 有的列用 `server_default=func.now()`（数据库会话时区），有的用 Python 的 UTC naive。在这种情况下，拿 UTC 的窗口起点去比较，再用 `DATE(col)` 分桶，结果会错位（`spider_task.py:43`、`quota_service.py:67-73`、`spider_task_repository.py:116`）。
- 分页参数在 normalize 这一层被吞掉以后，外层的分页循环就成了死代码，还会让人误以为调用是有界的（`llm_gateway/admin.py:132-144, 177-183` 对照 `relay_usage.py:33-43`）。

## 输出路径
- 需要 manager 保存：`/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/F3-data-collect-warehouse/05-review/findings.md`（reviewer 没有写任何文件）。
- success_check 命令需要 manager 在保存后执行：`python3 /Users/xuyun/.zcode/local-plugins/sdlc-workflow/scripts/workflow.py check-task --role reviewer --stage review --task G-fresh --root /Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/F3-data-collect-warehouse`
