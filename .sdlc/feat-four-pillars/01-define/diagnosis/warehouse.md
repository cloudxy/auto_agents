# 数仓诊断 · feat-four-pillars（刷新）

| 字段 | 值 |
|------|----|
| 角色 | data-warehouse-engineer |
| 特征 | `feat-four-pillars` / 定义帽 / L4 |
| 日期 | 2026-09-07 |
| 性质 | 就绪度诊断（分层 / 血缘 / 指标即代码）。**刷新**：对齐已冻结的 `spec.md` + `metrics-blueprint.md` |
| 范围 | 智能采集结果 + SaaS 用量 + 中转站渠道事件 + Power Market 目录；对照北极星 WACT 与 FR-15/16/30 |
| 不做 | 不实现 ETL；不改 OLTP schema（→ dba）；不定业务口径终稿（→ pm）；**本波不发明、不建 `ods_`/`dwd_`/`dws_`/`ads_` 表** |
| 宪法 | `sdlc.config.yaml` → `.claude/rules/project_rule.md`（数据流向不可逆；爬取与存储分离；数据质量先于数量；租户隔离） |

---

## 0. 结论（先说清楚）

**三块就绪度全部未就绪。本波不建仓。**

| 面 | 状态 | 一句话 |
|----|------|--------|
| **分层（warehouse）** | 不存在 | 全库无 `ods_`/`dwd_`/`dws_`/`ads_`/`dim_`/`fct_` 业务表；分析查询打在 OLTP MySQL 8 单实例 |
| **血缘（lineage）** | 不存在 | 无源→变换→消费登记；产品事件查询面未建；Redis/CSV 是易失或非权威副本 |
| **指标即代码** | 不存在 | 仓库无 `metrics.yaml`。产品口径已在蓝图冻结，但看板 SQL 仍是多处手写，且与蓝图不是同一套 id |

pm 已冻结（`metrics-blueprint.md` §6 / `spec.md` T-23）：**数仓分层下一轮**；Wave 0/1 只要求埋点可查（FR-15 / FR-16 / FR-30）。architect 旧诊断把本角色标 N/A 与此一致。

伪仓不得当仓：

- `llm_token_usage` 是 OLTP 日聚合，被配额检查写入路径使用，**不是** DWS（无分层前缀；flush 是业务副作用）。
- `archive_records` 是 OLTP 冷热快照表（021 建表），**生产写入路径零命中**（仅测试插入），**不是** ODS。
- `/admin/stats`、`/tenants/me/usage`、`/newapi/overview` 是服务层即时 `COUNT/AVG/GROUP BY`，**不是** ADS。

同实例约束（skill gotcha，架构已核实、无独立 OLAP 命中）：在线库与任何未来分析表将共用 MySQL。过渡只能是只读账号 + 低峰调度 + 表前缀隔离。禁止分析作业写回 OLTP。未设行量/P95 阈值前不提 ClickHouse/Doris ADR。

**上一稿缺陷（本刷新收回）**：曾列出一整份 `ods_*`/`dwd_*` 候选表和 28 条 `FR-WH-*` 平行指标。那是未签字的数仓侧发明，会与现已冻结的 WACT 蓝图形成**第二套口径**——「同一指标两处定义」正是本角色红线。本文件不再列候选分层表，也不再发明 `FR-WH-*`。

---

## 1. 相对上一稿改了什么

| 上一稿假设 | 现证据 | 处置 |
|------------|--------|------|
| `spec.md` 尚未产出，`fr_anchor` 用 `FR-WH-*` | `spec.md` v1 冻结 Wave 0/1；度量见 §6 + `metrics-blueprint.md` | 口径以蓝图为准；仓侧禁止平行 id |
| 全局北极星未选 | 唯一北极星 = **WACT**（周活跃完成租户数） | 成功率 / 月 token / 正品率 / 可安装资产数 **不得**当北极星 |
| 业务时区未定 | 冻结 **Asia/Shanghai 业务日**；指标用事件发生时间 | FR-16；现网看板仍 `datetime.now()` / `utcnow()`，是实现债不是口径债 |
| 结果存储是否含 marketplace | FR-11：候选不计入租户结果配额、不出现在「我的结果」 | 产品已决；配额 SQL **尚未**过滤 `source`（缺陷 D6 仍在） |
| 市场转化无埋点 FR | FR-15 / FR-30 事件名已冻结 | 仓等查询面；本波不建 ADS |
| 需要先设计 ODS/DWD 才能度量 | 蓝图：本轮不建分层；成功 = 事件可查、四周能报 WACT | **本波零分层表** |

---

## 2. 就绪度：问题 / 为什么 / 改进

### 2.1 分层（warehouse）

**问题**：没有分析层。所有「指标」都是 OLTP 上的即时聚合，和在线配额、列表分页抢同一实例。

**为什么**：平台从未建仓。采集结果进 `spider_results`、用量进 `llm_token_usage`、中转进 `channel_*`，都是业务表。`archive_records` 只完成 DDL。宪法要求数据单向 `OLTP/Redis → 仓 → 分析`，但第二段不存在，分析直接打第一段。

**改进（下一轮，不本波）**：

1. 等 FR-15/30 的**查询面**稳定（事件能否按时间查出——architect / backend，本角色不选存储）。
2. 再按前缀契约做贴源镜像与主题明细；**禁止**把 `llm_token_usage` 改名为 `dws_*`（它仍被配额写入）。
3. 一期若仍同实例：只读账号、低峰、`platform_scope()` 写仓、含 `tenant_id` 的明细不豁免。
4. 绿 ETL ≠ 正确：对账必须对照源表行数与事件查询面，而不是「job 成功」。

本波改进 = **不建表、不写 ETL、不把 Dashboard 切到不存在的 ADS**。

### 2.2 指标即代码（metrics.yaml）

**问题**：仓库零 `metrics.yaml`。产品口径已有唯一蓝图，运行时却有另一套无 id 的 SQL。analyst 若用 `/admin/stats` 当基线，四周后报出的「成功率」与 WACT 不可比。

**为什么**：蓝图 2026-09-07 才冻结；此前各服务各自 `COUNT`。上一稿若落地 28 条 `FR-WH-*`，会变成第三套。审查 QA-02：GWT-15.1 未写 WACT 排除字段；QA-11：spec 与蓝图护栏第五条不一致。仓侧若再选一套护栏 = 缺陷。

**改进**：

1. **本波不创建** `metrics.yaml`（避免与「下一轮 warehouse」双源）。
2. 下一轮唯一文件从蓝图 **复制 id**，公式写成可复现 SQL/事件过滤，`fr_anchor` 用 FR-15/16/30/11/18/28，owner=`pm`。
3. Wave 0 先修 FR-16：仪表盘窗口与时区跟蓝图对齐，并标明「全历史 vs 近 7 日」——这是后端/前端，不是仓。
4. 落地后禁止 Dashboard / QuotaService / NewapiOverviewService 再手写与 yaml 不等价的公式。

蓝图纪律（仓必须遵守，不得改口径）：

- 判定周期：相关波次对用户可用后 **4 个上海自然周**。
- 无基线 → 目标 = 能报出数字。
- 排除：市场入站候选不得进 WACT；内部测试企业无标记时四周复盘用**手工名单**，不得假装有过滤器。
- 禁止当 OEC：Hero 静态数字、全历史成功率、单任务质量分、扫描成功次数、技能平均分、渠道 24h 事件数。

### 2.3 血缘（lineage）

**问题**：没有血缘登记。WACT 验收「以事件可查为准」，但事件不落任何查询面；任务表只能弱重构且窗口与仪表盘不一致。若干边上的行会消失（增量 skip、死信、flush 崩溃窗口）。

**为什么**：无产品事件 SDK（全库 `track_event` / `product_event` 零命中）。采集闭环在 Redis 队列（符合爬取与存储分离），但队列不是事实表。市场表 `capability_installs` / `listing_state` 代码零命中。

**改进**：

1. Wave 0/1：backend/frontend 按冻结事件名落 **可查询存储**（本角色不选表形；拒绝把 Redis TTL 当事实源）。
2. WACT 排除字段必须进事件（见 QA-02 / 开放问题 Q-W1）。没有该字段，仓以后也无法从事件算北极星，只能错误地扫 `spider_results.source`。
3. 登记非权威副本：`spider:task_results:*`、CSV `storage/exports/`、死信 `spider:item_dead`——ADS 不以它们为源。
4. 下一轮仓消费 **事件查询面 + OLTP 核对**，不让 Scrapy 再写一套。

---

## 3. 源系统事实（只盘点，不建分层表）

数据只允许单向：`OLTP / Redis → 数仓 → 分析`。爬虫已遵守不直写主库（`platform_core/queues.py`：`ITEM_QUEUE` → consumer → `spider_results`）。仓必须接在这条线 **之后**。

### 3.1 今日已有、可当核对源的 OLTP

| 对象 | 粒度 | 租户 | 对 WACT/蓝图的可用性 |
|------|------|------|----------------------|
| `spider_tasks` | 一次任务 | `tenant_id` NOT NULL | 弱重构：`status=completed` 且 `result_count>0`；**无**候选标记列，需 join 结果 `source` 或等事件字段 |
| `spider_results` | 一条 item | `tenant_id` | `source='marketplace'` 是市场候选；与租户采集同表（主题污染，FR-11） |
| `tenants` | 企业 | 自身 | 注册时刻 `created_at` 可对 D1；**无**注册事件 |
| `users` | 登录主体 | Mixin | **无** `last_login_at`；登录不落事实（D2 不可测） |
| `llm_token_usage` | 租户×维×模型×日 | Mixin | 已是日聚合；flush `ON DUPLICATE KEY UPDATE` **累加**（at-least-once 可多计）；非 WACT 源 |
| `channel_events` / `channel_probe_results` | 平台审计/探针 | 无 tenant 列（已豁免） | 蓝图禁止当 OEC；无渠道维表 |
| `capability_assets` + 细节 / `skills` 三表 | 目录/治理 | assets/skills 的 `tenant_id` 恒 NULL | 无 `listing_state`，不能算上架；公开列表口径与设计不一致 |
| `operation_logs` | 高危操作 | 无 tenant 列 | 不能做漏斗 |
| `archive_records` | 冷热快照 | Mixin | **无生产写入** |

时区混用（影响日界，FR-16 要修的是在线看板，仓下一轮必须选定同一业务日）：采集 `DateTime(timezone=True)`；中转/用量 `created_at` 多为 naive；用量月键 `datetime.utcnow()`；stats 近 7 日 `datetime.now()` naive 零点。

### 3.2 易失 / 非权威 / 缺失

| 对象 | 性质 | 仓侧规则 |
|------|------|----------|
| Redis `spider:item_queue` / `spider:item_dead` | 队列；死信无 TTL | 不是 ODS 源；死信条数不可当完整率除非先落库 |
| Redis `llm:usage:d:*` TTL 30d；`llm:usage:m:*` TTL 93d | 日 field 有 tenant 段；**月 field 写入 `{dim}\|total` 无租户** | 禁止当月度指标源（熔断读数 ≠ 看板 DB SUM） |
| Redis `quota:count:*` TTL 60s | 配额短窗缓存 | 禁止当用量事实 |
| 远程 new-api `list_channels` | 不落库 | 历史渠道集合不可重建 |
| `capability_installs` / `capability_sources` / `listing_state` | 设计有、代码零命中 | 订阅漏斗不可测至 Wave 1 表 + FR-30 |
| 产品事件 `task_completed` 等 | FR 已冻、实现零 | WACT 验收源；无查询面 = 埋点 FR 失败 |
| 官网 PV/CTA | 无 | D1 诊断链的曝光步是洞 |

增量去重：consumer `md5(url+title+content)` 命中则**不插行**、只改 `result_count`；无 skip 事实。质量管道指纹是进程内 `md5(url\|title)`。二者不是同一重复（缺陷 D4）。

---

## 4. 蓝图指标 → 将来 `metrics.yaml`（本波不落文件）

下一轮唯一 yaml 只允许这些 id（及 pm 变更流程新增的）。**禁止**再引入 `spider_task_success_rate` 当北极星。

| id（建议 snake_case） | 蓝图名称 | fr_anchor | 公式（事件级，验收以查询面为准） | 粒度 | 维度 | 排除 | 本波可测？ |
|----------------------|----------|-----------|----------------------------------|------|------|------|-----------|
| `wact` | 周活跃完成租户数 | FR-15 | `COUNT(DISTINCT tenant_id) FILTER event=task_completed AND result_count>0 AND NOT is_marketplace_candidate`，上海自然周 | weekly | （企业） | 候选入站；内部测试企业手工名单 | ❌ 无事件；任务表弱重构缺排除字段 |
| `tenant_signup_count` | 注册成功数 | FR-15 | `COUNT(tenant_signup_succeeded)` 按次 | weekly | | 不去重邮箱 | ❌ 仅有 `tenants.created_at`，无事件 |
| `signup_to_login_168h_rate` | 注册后 168h 首次登录率 | FR-15 | 分子：该周注册企业中 168h 内 `login_succeeded` 去重；分母：同期注册企业 | weekly（企业滚动 168h） | | 登录失败不算分子 | ❌ 登录不落事实；GWT-15.1 未列 `login_failed` |
| `ttfv_median` | 注册→首次出数中位数 | FR-15 | `median(first task_completed − signup)`；未出数 **不进** 分母，另报仍未出数企业数 | 四周窗 | | 候选任务 | ❌ 无事件对 |
| `weekly_subscribe_tenants` | 周订阅成功租户数 | FR-30 | 自然周 `market_subscribe_succeeded` 企业去重 | weekly | host（可选） | 预告拒绝不算成功 | ❌ 表与事件都不存在 |
| `cross_tenant_visibility_incidents` | 跨租户可见事故 | FR-08 等 | 经复现确认的次数 | daily | | | 护栏，靠审计+手工，不是仓聚合 |
| `public_listing_leak_incidents` | 公开泄漏未上架/黑名单/未放行许可 | FR-18 | 抽检公开列表出现禁出资产的次数 | daily | | | Wave 1 对账；无 listing 列则不可自动 |
| `same_window_task_fail_rate` | 同窗口任务失败率 | FR-16 | `failed/(completed+failed)`，窗口与「近 7 日结果」相同；排除候选 | daily | tenant_id | pending/running；候选 | ⚠️ OLTP 能算，但现网成功率是**全历史**（D1），与蓝图窗口不一致 |
| `non_platform_admin_channel_or_llm_writes` | 非超管改渠道/平台 LLM 成功次数 | FR-07 | 成功写次数 | daily | | | 护栏红线 0；靠审计，现守卫过宽是实现债 |
| `quota_exceeded_unreadable` | 配额拒绝不可理解（蓝图护栏） | FR-12 / FR-15 | 用户可见文案含 `QUOTA_EXCEEDED` 或仅错误码的抽检次数 | daily | dimension | | 蓝图有、spec 护栏第五条是「失败装空」——**仓不得选第三套**（QA-11） |
| `public_market_fail_as_empty` | 公开市场失败装空（spec 护栏） | FR-28 | 失败必须失败态；抽检 0 次当空 | daily | | | 产品验收，不是仓指标 |

驱动 D1–D4 与护栏的 owner 是 pm；仓只负责下一轮把公式落到一层 SQL。Q-VOICE 若改核心动作为订阅成功，走变更流程改 `wact` 定义，**禁止**并存两个北极星。

---

## 5. 仍存活的伪指标双定义（消灭时对齐蓝图，不要写第三份）

这些是**现在**的缺陷：看板已在用，没有 yaml id。FR-16 修窗口；yaml 落地后服务层改读同一 id。

| 缺陷 | 定义 A | 定义 B | 后果 |
|------|--------|--------|------|
| **D1 成功率** | `/admin/stats`：全表 `completed/(completed+failed)`，无时间窗 | `recent_stats_by_spider`：最近 N 条终态 | 与蓝图「同窗口失败率」都不同；禁止当 OEC |
| **D2 total_results 名不副实** | `stats.total_results = sum(近 7 日 daily_results)` | 名像全量；配额用全表 COUNT | 运营把 7 日当总量 |
| **D3 近 7 日切点** | `datetime.now() - 6 days` 本地 naive 零点 | 任务列 `timezone=True`；蓝图要上海日 | FR-16 未实现则日界错 |
| **D4 去重指纹** | QualityCheckPipeline：`md5(url\|title)` 进程内 | consumer：`md5(url+title+content)` 按租户查库 | 「质量去重分」≠「增量跳过」 |
| **D5 质量四档** | repository `≥80/60/40` | Dashboard 只取最近 1 个完成任务 | 概览 ≠ 全量；蓝图禁止单任务质量分当 OEC |
| **D6 结果存储含候选** | 配额 `COUNT(spider_results)` 无 source 过滤 | FR-11 要求不含 marketplace | 产品已决、SQL 未改；WACT 排除与配额口径会再漂 |
| **D7 月度 token 三源** | 看板/配额：DB `SUM` + `CAST(stat_date AS CHAR) LIKE 'YYYY-MM-%'`，月取 `utcnow()` | Redis 月键写入 `{dim}\|total` **无租户**；`get_month_used` 先找 `{tenant}\|dim\|total` 再回退无租户 | 熔断 ≠ 看板；多租户串用量。**不是 WACT 源** |
| **D8 LLM 原子事件易失** | 请求级只在 Redis 日 hash，TTL 30d | 表内日聚合，`ON DUPLICATE` **累加**（认领崩溃 at-least-once 可多计） | 不能还原请求；不能当幂等 DWS |
| **D9 成员用量** | `usage_by_member` 只有任务数、全历史 | token 无 `created_by` | 两张表不可加总 |
| **D10 中转 24h** | `datetime.now() naive - 24h` | 蓝图禁止渠道 24h 事件数当 OEC | 值班观察项，不要进 yaml 北极星 |
| **D11 远程渠道** | overview 每次现场拉 | 本地无快照 | 历史渠道集合不可重建 |
| **D12 公开技能 vs 广场** | 公开技能滤 `stable\|recommended`（内存滤）；广场只传 `stable` | 设计/FR-18：上架∩治理∩许可 | 目录规模 API 不能当基线 |
| **D13 候选审核** | `extra` JSON 的 review；Python 滤 pending | 无列、无索引 | 转正率只能扫 JSON；WACT 排除也难 |
| **D14 result_count vs 行数** | 任务 `result_count` 累加（skip 会减回） | `COUNT(spider_results)` | 蓝图 WACT 用事件上的 `result_count>0`；对账须写明以事件为准 |

Hero 数字（`frontend/official` 静态 128,000+）与任何表无关——FR-02 删除，仓不收录。

---

## 6. 血缘空洞（源 → 查询面 之间断掉的边）

```
[Scrapy StorePipeline] --Redis ITEM_QUEUE--> [consumer] --> spider_results
        |                                      |  `-- 增量 skip：行不插，无 skip 事实
        |                                      `-- DEAD_ITEM_QUEUE：仅 Redis，无 TTL
        `-- store_to redis/csv：平行副本，非权威

[任务终态 webhook] --> spider_tasks.status/result_count
        `-- 产品事件 task_completed  ✖ 不存在查询面  ✖ WACT 无源

[注册] --> tenants 行；logger.info
        `-- tenant_signup_succeeded  ✖
[登录] --> JWT；失败进 Redis 限流
        `-- login_succeeded/failed  ✖

[QuotaExceededException] --> 429
        `-- quota_exceeded  ✖

[llm_client] --Redis 日/月 hash--> [flush ADD upsert] --> llm_token_usage
        `-- 月键无 tenant；日键 TTL 30d；无请求级表

[channel_* 本地表] 有
[new-api HTTP 渠道列表]  ✖ 不落库

[skill_harvester] --> spider_results(source=marketplace) --> extra.review JSON
[Power Market 设计] installs / sources / listing_state  ✖ ORM 不存在
[FR-30 市场事件]  ✖
[官网 page/cta]  ✖
```

必须先有、否则对应蓝图指标标不可测（不许用 OLTP 凑成「已能判定」）：

1. **事件查询面**（FR-15/30）含 `occurred_at`、租户/匿名、以及 WACT 排除用的候选标记。  
2. **登录事实**（成功须能关联企业）。  
3. **配额拒绝事件**（维度 concurrency/storage/llm_tokens）。  
4. Wave 1：`listing_state` + `capability_installs` + 市场事件。  
5. 候选 `review` 一等列或旁表——JSON 不能当核对键。  
6. （下一轮仓）LLM 若要进 yaml，需幂等日快照或请求级 WAL；现 `ADD` 路径不可当仓源。

CSV/Redis 镜像：血缘登记为非权威副本。

---

## 7. 租户隔离与同实例

| 将来对象 | 策略（下一轮才建表） |
|----------|----------------------|
| 租户采集/用量/安装明细 | 必须带 `tenant_id`，**不豁免** |
| 中转、平台目录、skill 治理 | 无租户或恒 NULL → **豁免清单** |
| ETL 写入 | `platform_scope()`，避免 `before_flush` 租户断言 |
| 源读取 | 只读账号、低峰 |

在线侧已知偏差（影响未来贴源同步，交 dba，仓不改 OLTP）：

- `capability_assets.tenant_id` 恒 NULL **未**进 `TENANT_EXEMPT_TABLES`（`skills` 已进）。租户态 Core UPDATE 0 行命中。  
- 设计要求豁免 sources/components/aliases，**禁止**豁免 installs。

`scripts/check-arch.sh` 闸门不含数仓前缀——下一轮建表时要补机械检查，防止业务表冒充 `dwd_`。

---

## 8. 给下游（本角色拒绝设计在线 schema、拒绝改口径）

| 谁 | 内容 |
|----|------|
| **pm** | 口径以蓝图为准。请关闭 QA-02（FR-15 GWT 补候选标记 / `login_failed` / 登录-企业）与 QA-11（护栏第五条 spec vs 蓝图）。未关前仓不把「能判定 WACT」写成已满足。Q-VOICE 未关前 `wact` 核心动作保持采集出数。 |
| **architect** | 事件能否进可查询存储；不改事件名。本角色不选 ClickHouse，也不在本波提 ODS DDL。 |
| **dba** | 事件表/列是在线契约，不是仓表。`listing_state` / installs 按设计 PR1。只读账号给未来 ETL。时区：报表日 = 上海日历日（蓝图交给 dba 的那句）。 |
| **backend / frontend** | FR-15/16/30 是验收契约；FR-11 配额过滤与 WACT 排除同一句话。不要把 `/admin/stats` 成功率改名为 WACT。 |
| **analyst** | 四周后只描述变化。禁止用 Hero、全历史成功率、渠道 24h、单任务质量分当基线。内部租户用手工名单。 |
| **miner** | 无 DWD。不要把质量分/探针 verdict 当监督标签。 |
| **sre** | 无仓作业可调度。同实例分析查询会打在线库；P95 阈值未定（开放问题）。 |
| **qa** | 埋点 GWT：查询面真能查到；失败不得挡主路径。 |

缺源 → 标不可测，停等，不猜。缺语义 → 问 pm，不编公式。

---

## 9. 落地顺序（仍不实现）

1. **本波（Wave 0/1）**：FR-15/16/30 事件可查 + FR-11 配额与候选分离 + FR-16 上海日窗口。无数仓表。  
2. **下一轮 warehouse**：唯一 `metrics.yaml`（§4 的 id）→ 贴源镜像已有 OLTP + 事件查询面 → 主题明细（采集 vs marketplace **分主题**）→ 日/周汇总 → 看板改读汇总或引用同一 id。  
3. 行量或 `/admin/stats` P95 越线 → OLAP ADR；前缀契约保持。  
4. 阈值未写进蓝图前，不发明护栏 id `warehouse_oltp_query_p95_ms` 当产品指标。

---

## 10. 角色自检

**建模**

- [x] 本波 **不发明、不建** `ods_`/`dwd_`/`dws_`/`ads_` 表
- [x] 前缀契约仍有效，留给下一轮
- [x] 未把 `archive_records` / `llm_token_usage` / 即时 stats 误认为数仓层
- [x] 未提出跨主题宽表

**指标**

- [x] 不以仓侧平行 id 覆盖蓝图；建议 yaml id 与 WACT/驱动/护栏 1:1
- [x] `fr_anchor` 使用已冻结 FR，不造 `FR-WH-*`
- [x] 不可测已标明；排除口径引用蓝图
- [x] 指出 OLTP 双定义 D1–D14

**ETL**

- [x] 本轮不实现
- [x] 要求将来分区覆盖、四类断言、血缘、禁止写回、PII 在明细层

**基础设施**

- [x] 同实例 MySQL：只读 + 低峰 + 前缀
- [x] 租户策略已分
- [x] 未写 OLTP DDL / 未改产品 FR / 未提交可运行 ETL

---

## 11. open_questions

仅列仓侧仍阻塞、且 **pm 蓝图未写死** 的项。已冻结的不再问。

1. **Q-W1（阻塞「能判定 WACT」）**：事件 `task_completed` 的候选排除字段以何名为准（`is_marketplace_candidate` / `source` / spider 名）？GWT-15.1 今日未写。未补则四周后只能弱扫任务表，验收失败。→ pm 修 FR-15（QA-02）。  
2. **Q-W2**：spec 护栏第五条（失败装空）与蓝图第五条（配额文案）以谁进将来 yaml？仓拒绝第三套。→ pm（QA-11）。  
3. **Q-W3**：任务表弱核对 WACT 时，软删任务、`result_count>0` 但结果已归档/软删，算不算完成？蓝图写事件 `result_count`，未写对账冲突。→ pm。  
4. **Q-W4**：内部测试企业手工名单的维护者与格式？蓝图禁止假装有过滤器。→ pm / 运营。  
5. **Q-W5**：Dashboard 何时停止把全历史成功率与近 7 日结果并排（FR-16）？这是 Wave 0 实现，不是仓切流。ADS 切流留下一轮。→ backend。  
6. **Q-W6**：事件查询面是 OLTP 表、日志外挂，还是直接进将来 ODS？本角色不选；但必须可按 `occurred_at` 范围查询且租户不可互读。→ architect。  
7. **Q-W7**：`llm_token_usage` 的 at-least-once ADD 是否在某一波改为幂等快照？不影响 WACT；影响将来若把月 token 写入 yaml。→ dba / backend。  
8. **Q-W8**：OLAP 触发阈值（`spider_results` 行数或分析 P95）？未定则下一轮仍同实例前缀。→ sre / operator。  
9. **Q-VOICE**（产品，仓遵守）：若改市场优先，WACT 核心动作改为订阅成功——变更流程改 yaml，禁止双北极星。

已关闭、仓遵守：时区 = Asia/Shanghai；北极星 = WACT；候选不占配额（FR-11）；订阅不占三类配额；探针伪装不是 OEC。

---

## 12. 输入与证据路径

- 产品：`.sdlc/feat-four-pillars/01-define/spec.md`（T-23、§6、FR-11/15/16/30）
- 口径：`.sdlc/feat-four-pillars/01-define/metrics-blueprint.md`（全文）
- 审查：`.sdlc/feat-four-pillars/05-review/findings.md`（QA-02、QA-11）
- 特征状态：`.sdlc/feat-four-pillars/state.yaml`
- 宪法：`sdlc.config.yaml` → `.claude/rules/project_rule.md`
- 设计：`/Users/xuyun/Documents/grok-files/power-market-design.md`
- OLTP：`platform_core/models/{spider_task,spider_result,llm_token_usage,channel_event,channel_probe_result,capability,tenant,skill,archive}.py`
- 队列：`platform_core/queues.py`（`ITEM_QUEUE` / `DEAD_ITEM_QUEUE` / `llm:usage:*`）
- 伪指标：`backend/services/{quota_service,spider_query_service,llm_usage_service,newapi_overview_service}.py`；`backend/repositories/{spider_task_repository,spider_result_repository,llm_token_usage_repository}.py`；`backend/app/api/v1/tenant_usage.py`；`scrapy/pipelines/quality.py`；`frontend/admin/src/pages/Dashboard.tsx`
- 隔离：`backend/app/tenant_isolation.py`（未豁免 `capability_assets`）
- 方言事故（仓 SQL 会再踩）：`backend/tests/test_t10_fix_regressions.py`（0e0aaf8 NULLS LAST）
- 检索（本刷新）：业务树无 `metrics.yaml`；无 `ods_`/`dwd_`/`dws_`/`ads_` 表名；无 `listing_state` / `capability_installs`；无 ClickHouse/Doris；无产品事件 SDK
