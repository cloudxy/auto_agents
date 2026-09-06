# 第二轮架构评估 · 首席架构师（2026-09-06）

> 视角：「这个产品要卖给 100 家客户，架构先死在哪」。只读评估，本轮不找 bug，找结构性/演进性短板。
> 基线：bea13b5..d19e57f（上轮 13 票修复 + 7 票清剿已合入）；上轮报告 `.sdlc/assessment-2026-09-05/00-summary.md`。

## 总体判断

上轮整治后，这套架构的**主干是健康的**：分层单向、租户数据隔离（TenantMixin 18/33 模型 + `with_loader_criteria` 自动注入 + R13 防漂移）、Redis 队列契约（死信/重试 ZSET/心跳/积压对账）、分布式锁设施、ADR 治理都在水准之上——**但它是按「单机单产品」形态收敛的健康**。卖给 100 家客户时，最先死的不在数据层（数据隔离已是亮点），而在**计算侧的租户语义缺失**：租户上下文只存在于 HTTP 请求态，队列、调度器、LLM 预算三个后台链路仍是「平台全局一份」的单租户心智（F1/F2/F3），客户之间会互相挤兑且无法按租户套餐计价。第二爆点是部署单元：API 与 8 个后台循环共享单 uvicorn worker 的一个 asyncio loop，故障域整体耦合（F4）。其余（消息契约无版本、配额竞态、双轨 1500 行、前端双轨）是可控的演进债，各有明确修法。

## FINDINGS

| # | 标题 | 严重度 | 证据（文件:行号 / 量化） | 对产品的后果 | 建议方向 |
|---|------|--------|--------------------------|--------------|----------|
| F1 | 定时调度链路租户身份断裂——定时任务裸奔 | **高** | `schedule_service.py:274-275` `_fire` 调 `enqueue` **不传 tenant_id**（全文件 grep `tenant` 零命中）；`spider_task_service.py:152` 签名默认 None → 任务行与消息 `tenant_id=NULL`（:200-206）；`SpiderTask(TenantMixin)`（`models/spider_task.py:25`）；后台循环无请求上下文，`tenant_context.py:137` tenant_id 为 None 即跳过注入 | 定时产生的任务不计租户并发配额、结果回流配额检查拿不到 tid（`consumer.py:694`）、租户侧任务列表/用量看板不可见、计费漏记——SaaS 正确性破口 | `_fire` 平台态扫描后以 `tenant_scope(schedule.tenant_id)` 包装入队；补「定时任务必带租户」负向测试（R13 同款） |
| F2 | 爬虫执行槽位全局独占，无租户公平性 | **高** | `queues.py:40` `ACTIVE_TASK_KEY=spider:active_tasks:{spider_name}`（全局键）；`spider_task_service.py:124` + `config/default/settings.yml:41` `SPIDER_MAX_CONCURRENT_PER_SPIDER=2`；守卫先到先得（:177-196） | 100 家客户共用每爬虫 **2 个全局槽**：一个客户的批量任务可让其余 99 家排队/被拒；租户配额 `task_concurrency=5` 被全局 2 槽事实作废（配额数 > 全局槽数） | 槽位键带租户维度（`{tenant}:{spider}`）+ 全局/租户双层上限；为 worker 池按租户权重调度留接口 |
| F3 | LLM 租户配额定义未接线，实际预算是平台统一阈值 | **高** | `quota_service.py:119` `check_llm_tokens_month` **全仓零调用**（仅定义+测试）；实际熔断在 `ai_planner/llm_client.py:319-335`，budget=`LLM.MAX_TOKENS_BUDGET` 全局值；`Tenant.quota.llm_tokens_month`（`models/tenant.py:20`）无消费方 | 全部客户共享同一预算数字（各自计数、同阈值），无法按租户分级 token 套餐；计费前提（product-review L3 virtual key）缺数据面支撑 | `llm_client` 预算读数改走 `quota_of(tenant)` 合并值；QuotaService 与 llm_usage_service 二者定为唯一配额事实源，落 ADR |
| F4 | API 与 8 个后台循环共享单进程单 worker | 中 | `run_backend.py:163` `uvicorn.run` 未设 workers；`backend/app/__init__.py:84-161` lifespan 内启动 consumer（dispatch/ingest/retry/recover 四循环）/SpiderScheduler/ProxyHealth/LlmUsageFlush/SkillScoring/LlmHealthPatrol/ChannelScheduler/ChannelProbe；`db.py:77,93` 每进程池 5+10 | 消费者/调度器崩溃 = API 全灭（看门狗只能整进程 kill，在途任务断）；API 扩容副本会把 8 循环 ×N 复制（锁互斥部分安全，DB/Redis 连接 ×N）；单 asyncio loop 承载 API 流量 + LLM/代理外呼，单核吞吐封顶 | 后台组件出独立 worker 进程（compose 拆服务）；锁设施已齐（`queues.py distributed_lock`），consumer 是 blpop 天然多消费者，拆分成本低 |
| F5 | 队列消息 schema 无版本化，死信只覆盖缺 task_id | 中 | `spider_task_service.py:200-206` 消息裸 JSON 四字段（无 schema_version）；`consumer.py:334-346` `_accept_message` 仅验 task_id；params 结构（start_urls/selectors/render/flow）靠 `extract_*`（consumer.py:69-131）隐式约定，payload 契约未进 `queues.py`（键名契约已有） | monorepo 内两端同步改契约目前可行，但滚动部署窗口（backend 新/爬虫旧或反之）字段语义漂移会**静默**解析错位且不进死信；契约演化无护栏 | 消息加 `schema_version`；消费端未知版本进 DLQ；params 结构契约文档化并入 queues.py（与键名契约同地位） |
| F6 | 并发配额检查竞态 + 60s 缓存漂移 | 中 | `quota_service.py:80-97` COUNT→enqueue 两步非原子；:57-75 `_cached_count` TTL 60s；并发槽位守卫同样 check-then-act 且 Redis 故障放行（`spider_task_service.py:177-186`） | 爆发窗口可超发（limit 5 实发 6-7）；结果存储行数配额 60s 滞后可超 1-2%（10000 行档）；量级上是配额信誉问题非资损 | 入队原子化（Redis Lua 计数槽 + 与现有 recover loop 对账回收）；或显式声明「软限」语义写进配额文档 |
| F7 | 结果数据无 retention，归档模型是死代码 | 中 | `ArchiveRecord`（`platform_core/models/archive.py:9`）仅测试引用；清理仅单条 `delete_result`（`spider_query_service.py:219-225`）；`spider_results` 无软删/分区（`models/spider_result.py`）；MySQL compose 限 512m（`docker-compose.yml:20`） | 100 客户持续采集 = spider_results 无限增长；配额文案让用户「清理历史结果」却无批量清理/保留策略产品面；行数 COUNT 型配额随表膨胀变慢（有 60s 缓存缓解） | 按租户套餐定 retention（天数/行数），复用 `platform_core/storage` 归档或定时清理；激活或删除 ArchiveRecord |
| F8 | new-api 双轨 ~1500 行待退役，外部库直连是最大单点 | 中 | `product-review.md:121` channel_scheduler_service（515 行）直连 new-api MySQL logs 表（独立 engine）；L2 涉 6 文件 ~1500 行（:122-125）；L1 影子已落地 660 行零外呼（`backend/services/litellm/`），L2-L5 无排期 | 每多养一天双轨 = 测试/配置/认知三重成本；客户私有化部署环境没有 new-api，外部库直连是断腿点 | L5 拆除直连可先行（不依赖 L2）；对 L2-L5 写「双轨退出时间」ADR，哪怕结论是暂缓也要显式 |
| F9 | ADR-0008 触发条件 2 临近：租户自定义角色 | 低 | ADR-0008「触发重评条件」第 2 条：roles 若加 tenant_id，行数膨胀 ∑租户×角色；当前角色为平台级（内置 3 + 自建） | 100 客户 SaaS 化几乎必命中（客户管理员无法自建角色），命中即触发 JSON→关联表的 expand-contract 迁移窗口 | 「租户自定义角色」进 SaaS 路线图时同步启动重评——迁移草案 ADR-0008 已写好，届时按草案三步走 |
| F10 | 前端数据层双轨：react-query 引入但覆盖 3/26 页面 | 低 | admin+official 均装 `@tanstack/react-query ^5.99`（package.json:7），实际仅 6 文件使用（SpiderLogs/Nodes/Spiders）；其余 23 页手写 useState/useEffect + 18 个 service 封装；页面测试 3/26 | 每新增页面重复造 loading/error/缓存轮子；多租户化要补「租户切换全仓失效」态时成本 ×23 | 定 ADR 终结选型：react-query 全覆盖（推荐，配合租户切换 invalidateQueries）或移除依赖 |

## 「架构层最值得花一周」投资方向（按优先级）

1. **租户计算侧贯通（F1+F2+F3 合并票组）**——三个断点同一根因：租户上下文只活在 HTTP 请求态，把租户身份/配额贯通到调度器、队列槽位、LLM 预算三处。不修则「卖给 100 家」在计价与公平性两个商业前提上不成立；这是解锁按租户套餐定价的第一前提。
2. **部署单元拆分（F4）**——后台循环出 API 进程，compose 拆 worker 服务。锁/blpop/心跳设施全部现成，约一周工作量换故障域隔离 + API 水平扩展路径，是所有后续扩容的地基。
3. **契约与观测补强（F5+F6）**——消息 schema_version + 未知版本死信 + 配额入队原子化 + 队列深度 LLEN 接入 alert_rules 采集（`models/alert_rule.py:14` 已有 queue_depth 类型，差采集端）。收益：滚动发布安全网 + 配额可信度。
4. **LiteLLM L5 先行（F8）**——先做 L5 拆除 channel_scheduler 对 new-api 库的直连（L2 可后置），启动双轨退出。收益：私有化部署可行性 + 1500 行高风险代码的退役路径落地。
5. **（可选）结果数据 retention（F7）**——按租户套餐的保留策略 + 归档启用。收益：MySQL 存活 + 「存储配额」从拒绝式检查变成可运营的产品面。

## 边界与遗留说明

- 本机无运行环境，DB 连接池/缓存竞态结论来自静态代码证据（F6 未做压测复现）；F1 的 `tenant_id=NULL` 推断链条完整（enqueue 签名→调用点→消息体→模型），但未跑真库取证，建议修复票先写一条失败的红测再动手。
- `docs/adr/`（ADR-0001~0009）不在 git 追踪范围（docs/ 为本地私有），其「触发重评条件」质量很高（0008/0009 均带量化触发线与迁移草案），但**触发条件无人值守**——建议给 F9 这类「条件临近」建一个季度性巡检项。
- 上轮遗留中未在本轮重复评估的：监控告警外部落地、E2E 缺失、CI MySQL 保真通道 8/87（属 qa/sre 域，本轮仅在与 F4/F7 相关时引用）。
