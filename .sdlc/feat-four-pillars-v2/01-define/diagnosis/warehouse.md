# 数仓诊断 · feat-four-pillars-v2

| 字段 | 值 |
|------|----|
| 角色 | data-warehouse-engineer |
| 特征 | `feat-four-pillars-v2` / 定义帽 / L4 |
| 日期 | 2026-09-08 |
| 性质 | 只读就绪度复审 + 程序裁剪（进本程序 vs 显式 N/A） |
| 范围 | ODS/DWD/DWS/ADS、`metrics.yaml`、血缘、产品事件落点；对照旧 warehouse 诊断与四柱方案 |
| 不做 | **不建仓表**；**不写现行 `metrics.yaml`**（塑形/L4 数据线，且本程序实现面 N/A）；不定口径终稿（→ pm）；不改 OLTP（→ dba） |
| 宪法 | `sdlc.config.yaml` → `.claude/rules/project_rule.md`（数据流向不可逆；爬取与存储分离；租户隔离） |
| 输入 | `01-define/diagnosis/INPUTS.md`；旧 `.sdlc/feat-four-pillars/` 只作输入，**不复制为现行合同** |

---

## 0. 结论（先说清楚）

**实现面：显式 N/A。诊断面：本文件。**

2026-09-08 对现树复验：分层 / 指标即代码 / 血缘 / 产品事件落点 **四块全未就绪**。结合旧程序（spec T-23、蓝图 §6、architect 角色裁剪、ADR-0016、contract §8）与 grok-files 四柱方案（「明确还不做：数仓」），**feat-four-pillars-v2 不进仓**：不建 `ods_`/`dwd_`/`dws_`/`ads_`/`dim_`/`fct_`，不落仓库根或 `02-shape/warehouse/metrics.yaml`，不写 ETL，不登记血缘作业。

L4 数据线在本程序里只保留三件事，**都不是仓票**：

1. 采集入站已走 Redis 队列（collector 运输层；仓接在这条线 **之后**，本程序不接）。
2. 产品事件进 **OLTP 可查询存储**（dba / backend / frontend；FR-15/30 若 pm 仍写进 v2 spec）。
3. 相关波次可用后 4 个上海自然周，analyst 按蓝图复盘（仓不报数）。

| 面 | 状态 | 一句话 |
|----|------|--------|
| **分层（warehouse）** | 不存在 | 业务树无 `ods_`/`dwd_`/`dws_`/`ads_`/`dim_`/`fct_` 表；分析打在 OLTP MySQL 8 单实例 |
| **指标即代码** | 不存在 | 仓库 **0** 个 `metrics.yaml`。旧蓝图是输入口径，不是现行 yaml |
| **血缘（lineage）** | 不存在 | 无源→变换→消费登记；`lineage`/`血缘` 业务树 0 命中 |
| **产品事件落点** | 不存在 | `track_event` / `ProductEvent` / `official_page_viewed` 等 **0** 命中（`notifications.type="task_completed"` 是站内通知，不是漏斗事实） |

伪仓不得当仓：

- `llm_token_usage`：OLTP 日聚合，配额写入路径使用；flush 是 `ON DUPLICATE KEY UPDATE` **累加**，**不是** DWS。
- `archive_records`：迁移 021 建表；生产写入路径 **零命中**（仅测试插入），**不是** ODS。
- `/admin/stats`、`/tenants/me/usage`、`/newapi/overview`：服务层即时 `COUNT/AVG/GROUP BY`，**不是** ADS。

同实例约束（skill gotcha，本轮复验仍成立）：无 ClickHouse/Doris/StarRocks 命中。在线库与任何未来分析表将共用 MySQL 8。过渡只能是只读账号 + 低峰 + 表前缀。禁止分析作业写回 OLTP。未设行量/P95 阈值前 **不** 提 OLAP ADR。

**grok-files `four-pillars-diagnosis-and-plan.md` §3.10 的 ODS 候选表不得进 v2 spec。** 那是未签字的仓侧发明；旧 warehouse 诊断已收回，避免与 WACT 蓝图形成第二套口径（同一指标两处定义 = 本角色红线）。本文件同样不列候选分层表，不发明 `FR-WH-*`。

---

## 1. 程序裁剪：进本程序 vs 显式 N/A

未用的机制必须写成 N/A，不能 silently skip（SDLC iron rule）。

| 工件 | 本程序（v2） | 归属 | 理由 |
|------|--------------|------|------|
| 定义帽本诊断 | **进**（本文件） | warehouse | 编排器全角色复审；裁剪要有证据 |
| `02-shape/warehouse/` 分层设计 | **N/A** | — | 缺稳定源（事件查询面未建）；缺现行口径文件 |
| 现行 `metrics.yaml` | **N/A** | — | 塑形/L4 数据线。v2 spec 未冻；现在落文件 = 与将来 PRD 双源 |
| ETL / 质量断言 / 血缘登记 | **N/A** | — | 无分层表可跑；绿 ETL ≠ 正确 |
| 产品事件 OLTP 表 + 超管查询面 | **进（若 pm 仍要能判定）** | **dba / backend**，**不是仓** | 旧 ADR-0016 否决「本波建 ODS 从仓查 WACT」；事件是漏斗事实，不是贴源镜像 |
| 官网/后台埋点发射 | **进（同上）** | frontend / backend | FR-15/30；失败不挡主路径 |
| 仪表盘上海日窗口 | **进（若仍写 FR-16）** | backend / frontend | 在线看板债，不是 ADS 切流 |
| 候选不计配额 | **进（若仍写 FR-11）** | backend | 配额 SQL 今日仍全表 COUNT |
| 四周 WACT 复盘 | 上线后，不在实现票 | analyst | 仓不报第一轮数字 |
| 离线模型 / 特征表 | **N/A** | miner | 无 DWD；miner 旧诊断同结论 |

**缺源 → 停，不猜。** 北极星验收源是产品事件，不是任务表弱重构。事件表不存在 = 仓无法幂等入 ODS。本角色不发明事件 schema（→ dba），不改事件名（→ pm / architect）。

**缺语义 → 问 pm，不编公式。** v2 尚无现行 spec。输入蓝图（旧 `metrics-blueprint.md` v1.2 / grok `feat-four-pillars-metrics.md`）可当口径草稿；**不得**在本帽写成 yaml。

实现帽 / 塑形帽建议 `roles_skipped` 写入：

```text
data-warehouse-engineer: 事件进 OLTP；分层 / metrics.yaml / ETL 不在本程序。
诊断见 01-define/diagnosis/warehouse.md。另开 warehouse 程序或由 pm 编号的后续波再请。
```

不要沿用 grok 诊断的「Wave 5」编号，除非 pm 在 v2 spec 里显式编号。旧 spec 写的是「下一轮」，旧 contract 写的是 W0/W1 **N/A**。

### 1.1 将来仓何时才允许进程序（前置，全部满足）

1. 事件查询面已按 `occurred_at` + `event_name` 可查；WACT 能从事件报出（不是任务表凑）。
2. `task_completed` 带布尔 `is_marketplace_candidate`（输入 GWT-15.1 已写此名；仓不另起字段名）。
3. Wave 1 对象存在：`listing_state` + 租户安装行（否则 D4/F3 不可测，仓不得用目录 `status` 冒充上架）。
4. 看板双定义（§5）已修或显式记债；禁止 yaml 与 `/admin/stats` 长期两套成功率。
5. pm 单独立项（新 feature 或本程序后续波），yaml **只复制**蓝图 id，owner=`pm`。
6. ETL：只读源账号、低峰、`platform_scope()` 写仓、分区覆盖、四类质量断言。

未满足前建仓 = 空中楼阁，且与在线配额抢同一 MySQL。

---

## 2. 结合旧诊断与四柱方案（不复制为合同）

| 来源 | 仓侧取什么 | 不取什么 |
|------|------------|----------|
| 旧 `diagnosis/warehouse.md`（2026-09-07） | 三块未就绪；伪仓清单；本波不建表、不写 yaml、不发明 `FR-WH-*` | 不把旧开放问题当 v2 已冻结答案 |
| 旧 `spec.md` T-23 / 范围外 | 「数仓 ODS/DWD、metrics.yaml 物理层 → 下一轮」 | 不把 v1.4 FR 编号当作 v2 已过闸合同 |
| 旧 `metrics-blueprint.md` v1.2 | 唯一北极星 WACT；事件名；排除候选；上海业务日；护栏第五条已与 spec 对齐（QA-11/22） | 不落成现行 yaml |
| 旧 GWT-15.1（v1.4） | `is_marketplace_candidate` / `login_failed` / 登录-企业 — QA-02 在旧程序已补。**旧 warehouse Q-W1 在输入层关闭** | v2 spec 未写前，仓仍要求 pm **抄此字段集**，禁止另起名 |
| 旧 `contract.md` §8 / grok `four-pillars-plan.md` | `/data-warehouse-engineer` W0/W1 **N/A**；事件进 OLTP；明确还不做：数仓 | 不把 14.5 人周票单当 v2 已排期 |
| 旧 ADR-0016 | 否决：审计冒充漏斗、本波 ODS、只 grep 日志、上外部分析 SDK | **不是** v2 现行 ADR；存储形状仍由 v2 architect/dba 选。仓只约束：可按时间查、租户不可互读、禁止 Redis TTL 当事实源 |
| grok `four-pillars-diagnosis-and-plan.md` | 「第一可卖切片不是数仓」；「数据中心 ≠ 数仓」；Wave 5 之前不要建仓（**时机**） | **丢弃** §3.10 的 ODS/DWD/ADS 表清单 |
| 旧 architect 诊断 | 实现帽 warehouse N/A；FR-15 先事件 | 不把「FR-15 做成数仓」当反例目标（那是旧稿明确禁止的） |

相对旧 warehouse 诊断，本轮代码事实 **未改善**：Alembic 头仍 `027`；`listing_state` / `capability_installs` / `POWER_MARKET` 仍 0 命中；`capability_assets` 仍未进豁免清单；stats 仍 `datetime.now()` naive；配额仍不过滤 `source`。

旧开放问题处置：

| 旧题 | 2026-09-08 |
|------|------------|
| Q-W1 候选排除字段名 | **输入层已关**（GWT-15.1 布尔 `is_marketplace_candidate`）。v2 pm 须抄，仓不重开命名争论 |
| Q-W2 护栏第五条双源 | **输入层已关**（蓝图 v1.2 / QA-11/22）。仓拒绝第三套 |
| Q-W5 看板双窗 | 仍是 Wave 0 在线债（backend），不是仓切流 |
| Q-VOICE | 仍开放。改核心动作走变更流程；**禁止双北极星** |

---

## 3. 现树复验（2026-09-08，只盘点）

检索范围：仓库业务树（`backend/` `platform_core/` `scrapy/` `frontend/` `config/` `scripts/`）。`.sdlc/` 与 grok-files 是输入，不是运行时。

| 检查 | 命令级事实 | 结果 |
|------|------------|------|
| 分层前缀表 | `__tablename__` 无 `ods_`/`dwd_`/`dws_`/`ads_`/`dim_`/`fct_`（`uploads_dir` / 测试 `dim` 是假阳性） | **无仓表** |
| `metrics.yaml` | 全库 0 命中 | **无** |
| 血缘登记 | `lineage`/`血缘` 业务树 0 | **无** |
| 产品事件 SDK | `track_event` / `product_event` / `ProductEvent` 0；前端无 posthog/segment/gtag | **无** |
| 蓝图事件名 | `official_page_viewed` 等在 `*.py/ts/tsx` 仅通知类型 `task_completed` | **无落点** |
| OLAP | ClickHouse/Doris/StarRocks 0 | **同实例 MySQL** |
| `check-arch.sh` | 无数仓前缀机械检查 | 下一轮建表才补；本程序不补 |
| Alembic 头 | `027_spider_tasks_status_varchar` | 事件表未迁 |

数据只允许单向：`OLTP / Redis → 数仓 → 分析`。爬虫已遵守不直写主库（`platform_core/queues.py`：`ITEM_QUEUE` → consumer → `spider_results`）。仓必须接在 **之后**。本程序不接第二段，分析继续打第一段——这是已知债，用事件查询面止血，不用仓。

### 3.1 可当核对源的 OLTP（将来贴源，本程序不镜像）

| 对象 | 粒度 | 租户 | 对 WACT/蓝图 |
|------|------|------|----------------|
| `spider_tasks` | 一次任务 | Mixin；DDL NOT NULL / ORM 可空 | 弱重构：`status=completed` 且 `result_count>0`；**验收不得用此冒充事件** |
| `spider_results` | 一条 item | Mixin | `source='marketplace'` 与租户采集同表（FR-11 主题污染） |
| `tenants` | 企业 | 自身 | `created_at` 可对 D1；**无**注册事件 |
| `users` | 登录主体 | Mixin | **无** `last_login_at` |
| `llm_token_usage` | 租户×维×模型×日 | Mixin | 非 WACT 源；ADD upsert 非幂等快照 |
| `channel_events` / `channel_probe_results` | 平台审计/探针 | 无 tenant 列（已豁免） | 蓝图禁止当 OEC |
| `capability_assets` + 细节 / `skills` | 目录/治理 | assets `tenant_id` 恒 NULL **未豁免**（注释谎称白名单） | 无 `listing_state`，不能算上架 |
| `operation_logs` | 高危操作 | 无 tenant 列 | **禁止**当漏斗分母 |
| `notifications` | 收件箱 | Mixin | `type=task_completed` **禁止**当北极星 |
| `archive_records` | 冷热快照 | Mixin | 无生产写入 |

### 3.2 易失 / 非权威 / 缺失

| 对象 | 性质 | 仓侧规则 |
|------|------|----------|
| Redis `spider:item_queue` / `spider:item_dead` | 队列；死信无 TTL | 不是 ODS 源 |
| Redis `llm:usage:d:*` / `m:*` | 日 field 四段含 tenant；**月写入仍 `{dim}\|total` 无租户**；读先 `{tenant}\|dim\|total` 再回退无租户 | 禁止当月度指标源（D7 仍在） |
| Redis `quota:count:*` TTL 60s | 短窗缓存 | 禁止当用量事实 |
| CSV `storage/exports/`、`spider:task_results:*` | 平行副本 | 非权威 |
| 远程 new-api `list_channels` | 不落库 | 历史渠道集合不可重建 |
| `capability_installs` / `listing_state` / `POWER_MARKET` | 设计有、代码 0 | 订阅漏斗不可测 |
| 产品事件 | FR 已冻于**输入**、实现 0 | WACT 验收源 |
| 官网 PV/CTA | Hero 静态 `128,000+`（`Home.tsx` `HERO_STATS`） | 不可作基线 |

增量去重：consumer `md5(url+title+content)` 命中则不插行；QualityCheckPipeline `md5(url\|title)` 进程内。二者不是同一重复（D4）。skip **无事实行**。

---

## 4. 血缘空洞（源 → 查询面 断边）

```
[Scrapy StorePipeline] --Redis ITEM_QUEUE--> [consumer] --> spider_results
        |                                      |  `-- 增量 skip：行不插，无 skip 事实
        |                                      `-- DEAD_ITEM_QUEUE：仅 Redis
        `-- redis/csv 平行副本，非权威

[任务终态] --> spider_tasks.status/result_count
        `-- 产品事件 task_completed  ✖  无查询面  ✖ WACT 无源

[注册] --> tenants 行 + logger.info     `-- tenant_signup_succeeded ✖
[登录] --> JWT；失败 Redis 限流         `-- login_succeeded/failed ✖
[QuotaExceededException] --> 429        `-- quota_exceeded ✖
[导出] --> 流式下载                     `-- results_exported ✖

[llm_client] --Redis 日/月 hash--> [flush ADD upsert] --> llm_token_usage
        `-- 月键写入无 tenant；日键 TTL；无请求级 WAL

[channel_* 本地表] 有
[new-api HTTP 渠道列表]  ✖ 不落库

[skill_harvester] --> spider_results(source=marketplace) --> extra JSON
[Power Market] listing / installs / sources  ✖ ORM 不存在
[FR-30 市场事件]  ✖
[官网 page/cta]  ✖  静态 Hero
```

没有事件查询面，对应蓝图指标必须标 **不可测**。不许用 OLTP 凑成「已能判定」。这是 pm/qa 验收纪律，不是仓用任务表救场。

CSV/Redis 镜像：将来血缘登记为 **非权威副本**。本程序不登记（无仓作业）。

---

## 5. 仍存活的伪指标双定义（在线债，不是仓票）

消灭时对齐 **输入蓝图**，不要写第三份。yaml 落地（将来程序）后，服务层改读同一 id。

本轮复验仍在：

| 缺陷 | 定义 A | 定义 B | 证据（2026-09-08） |
|------|--------|--------|-------------------|
| **D1 成功率** | `/admin/stats`：全表 `completed/(completed+failed)`，无时间窗 | 蓝图：与「近 7 日结果」同窗失败率 | `spider_query_service.py` `stats()` |
| **D2 total_results** | `sum(近 7 日 daily_results)` | 名像全量；配额用全表 COUNT | 同文件 `total_results=sum(...)` |
| **D3 近 7 日切点** | `datetime.now() - 6 days` 本地 naive 零点 | 任务列 `timezone=True`；蓝图上海日 | `since = datetime.now() - timedelta(days=6)` |
| **D4 去重指纹** | Quality：`md5(url\|title)` 进程内 | consumer：`md5(url+title+content)` 按租户 | `scrapy/pipelines/quality.py` vs `backend/tasks/consumer.py` |
| **D6 结果存储含候选** | `COUNT(spider_results)` 无 source 过滤 | FR-11 不含 marketplace | `quota_service.py` `check_result_storage` |
| **D7 月度 token** | 看板/配额：DB `SUM` + `LIKE 'YYYY-MM-%'`；月取 `utcnow()` | Redis 月写入 `{dim}\|total` 无租户；读先带租户再回退 | `tenant_usage.py:26`；`llm_usage_service.py:102,120-122` |
| **D8 请求级易失** | Redis 日 hash TTL 30d | 表内日聚合 ADD 累加 | `llm_token_usage_repository.py` |
| **D10 中转 24h** | `datetime.now() naive - 24h` | 蓝图禁止当 OEC | `newapi_overview_service.py` |

旧诊断 D5/D9/D11–D14（质量四档、成员用量、远程渠道、公开闸双标准、候选 JSON、result_count vs 行数）本轮未逐行重拆，**视为仍适用**，直到对应角色证伪。Hero 静态数与任何表无关——仓不收录。

---

## 6. 将来 `metrics.yaml` 纪律（本程序不落文件）

下一轮（另程序）唯一 yaml **只允许**输入蓝图已有的 id（及 pm 变更流程新增的）。禁止再引入 `spider_task_success_rate` 当北极星。禁止仓侧平行 `FR-WH-*`。

输入蓝图 id（**抄，不改**；此处不是现行合同）：

| id | 蓝图名称 | 输入 fr_anchor | 本程序可测？ |
|----|----------|----------------|--------------|
| `wact` | 周活跃完成租户数 | FR-15 | ❌ 无事件 |
| `tenant_signup_count` | 注册成功数 | FR-15 | ❌ 仅有 `tenants.created_at` |
| `signup_to_login_168h_rate` | 注册后 168h 首次登录率 | FR-15 | ❌ 登录不落事实 |
| `ttfv_median` | 注册→首次出数中位数 | FR-15 | ❌ 无事件对；未出数不进分母 |
| `weekly_subscribe_tenants` | 周订阅成功租户数 | FR-30 | ❌ 表与事件都不存在 |
| `cross_tenant_visibility_incidents` | 跨租户可见事故 | 隔离 FR | 护栏，审计+手工，不是仓聚合 |
| `public_listing_leak_incidents` | 公开泄漏 | FR-18 | Wave 1 对账；无 listing 列则不可自动 |
| `same_window_task_fail_rate` | 同窗口任务失败率 | FR-16 | ⚠️ OLTP 能算，现网是全历史（D1） |
| `non_platform_admin_channel_or_llm_writes` | 非超管改渠道/平台 LLM | FR-07 | 护栏红线 0 |
| `quota_exceeded_unreadable` | 配额拒绝不可理解 | FR-12 | 抽检，不是仓 |
| `public_market_fail_as_empty` | 公开失败装空 | FR-28 | 产品验收，不是仓 |

公式、粒度、排除以输入蓝图为准。仓只在将来把公式落一层 SQL。Q-VOICE 若改核心动作为订阅成功，变更流程改 `wact`，禁止并存两个北极星。

---

## 7. 租户隔离与同实例

| 将来对象 | 策略（另程序才建表） |
|----------|----------------------|
| 租户采集/用量/安装/事件明细 | 必须带 `tenant_id`，**不豁免** |
| 中转、平台目录、skill 治理 | 无租户或恒 NULL → **豁免清单** |
| ETL 写入 | `platform_scope()`，避免 `before_flush` 租户断言 |
| 源读取 | 只读账号、低峰 |

在线侧已知偏差（交 dba，仓不改 OLTP）：

- `capability_assets.tenant_id` 恒 NULL **未**进 `TENANT_EXEMPT_TABLES`（`skills` 已进）。模型注释写「豁免白名单」与代码不符。
- 设计要求豁免 sources/components/aliases，**禁止**豁免 installs。
- 方言事故：MySQL 不支持 `NULLS LAST`（P-WH-01，`test_t10_fix_regressions.py`）。将来仓 SQL 禁止抄 PostgreSQL 方言。

`scripts/check-arch.sh` 不含数仓前缀——**本程序不改闸门**（无表可扫）。另程序建表时再补，防止业务表冒充 `dwd_`。

---

## 8. 给下游（拒绝设计在线 schema、拒绝改口径）

| 谁 | 内容 |
|----|------|
| **pm** | v2 spec 范围外写明：数仓分层 / `metrics.yaml` 物理层 / ETL。能判定 ≠ 建仓。产品事件是 OLTP 叶子。GWT 抄旧 15.1 字段集（含 `is_marketplace_candidate`）。Q-VOICE 未关前核心动作保持采集出数。不要把 grok §3.10 表清单写进 PRD。 |
| **architect** | 实现帽跳过 warehouse。事件能否进可查询存储；不改事件名。本角色不选 ClickHouse，也不在本程序提 ODS DDL。旧 ADR-0016 可作材料，不是现行决策。 |
| **dba** | 事件表/列是在线契约，不是 `ods_`。只读账号给未来 ETL（可记债，本程序可不建）。报表日 = 上海日历日。 |
| **backend / frontend** | 埋点名与字段是验收契约。不要把 `/admin/stats` 成功率改名为 WACT。FR-16 修窗口。D6 配额过滤与 WACT 排除同一句话。 |
| **analyst** | 四周后只描述变化。禁止用 Hero、全历史成功率、渠道 24h、单任务质量分当基线。内部租户用手工名单。 |
| **miner** | 无 DWD。不要把质量分/探针 verdict 当监督标签。 |
| **sre** | 无仓作业可调度。同实例分析查询会打在线库；P95 阈值未定。 |
| **qa** | 埋点 GWT：查询面真能查到；失败不得挡主路径。过仓分层用例 **N/A**。 |
| **ops** | 0 工单 ≠ 0 问题。没有事件就不能用「没人叫」为 Hero 辩护。 |

缺源 → 标不可测，停等，不猜。缺语义 → 问 pm，不编公式。

---

## 9. 角色自检

**建模**

- [x] 本程序 **不发明、不建** `ods_`/`dwd_`/`dws_`/`ads_` 表
- [x] 未把 `archive_records` / `llm_token_usage` / 即时 stats 误认为数仓层
- [x] 未提出跨主题宽表；未抄 grok §3.10 候选表
- [x] 前缀契约留给另程序

**指标**

- [x] 不写现行 `metrics.yaml`
- [x] 不以仓侧平行 id 覆盖蓝图
- [x] 不可测已标明
- [x] 指出仍存活的 OLTP 双定义

**ETL**

- [x] 本程序不实现
- [x] 要求将来分区覆盖、四类断言、血缘、禁止写回、PII 在明细层

**基础设施 / 裁剪**

- [x] 同实例 MySQL：只读 + 低峰 + 前缀（将来）
- [x] 租户策略已分
- [x] **显式 N/A** 实现面，不是沉默跳过
- [x] 未写 OLTP DDL / 未改产品 FR / 未提交可运行 ETL

---

## 10. open_questions

仅列仓侧仍阻塞、且 **输入蓝图未写死或 v2 必须重裁** 的项。已冻结的不再问。

1. **Q-WH-STORE**（不阻塞 N/A 裁剪；阻塞「能判定」）：事件查询面是 OLTP 追加表、日志外挂，还是直接进将来 ODS？本角色 **不选**。约束：按 `occurred_at` 范围可查；租户不可互读；禁止 Redis TTL / `operation_logs` / `notifications` 当事实源。→ architect / dba。
2. **Q-WH-INTERNAL**：内部测试企业手工名单的维护者与格式？蓝图禁止假装有过滤器。→ pm / 运营。
3. **Q-WH-RECON**：任务表弱核对 WACT 时，软删任务、`result_count>0` 但结果已归档/软删，算不算完成？蓝图写事件 `result_count`，未写对账冲突。→ pm（另程序才需要）。
4. **Q-WH-LLM**：`llm_token_usage` 的 at-least-once ADD 是否改为幂等快照？不影响 WACT；影响将来若把月 token 写入 yaml。→ dba / backend。
5. **Q-WH-OLAP**：OLAP 触发阈值（`spider_results` 行数或分析 P95）？未定则另程序仍同实例前缀。→ sre / operator。
6. **Q-VOICE**（产品，仓遵守）：若改市场优先，变更流程改 `wact`，禁止双北极星。

已关闭、仓遵守（输入层）：时区 = Asia/Shanghai；北极星 = WACT；候选排除字段名 = `is_marketplace_candidate`；候选不占配额（FR-11）；护栏第五条以蓝图为准；探针伪装不是 OEC。

---

## 11. 输入与证据路径

- 书单：`.sdlc/feat-four-pillars-v2/01-define/diagnosis/INPUTS.md`
- 旧仓诊：`.sdlc/feat-four-pillars/01-define/diagnosis/warehouse.md`
- 旧口径：`.sdlc/feat-four-pillars/01-define/metrics-blueprint.md` v1.2；grok `feat-four-pillars-metrics.md`
- 旧 PRD/方案：`spec.md` T-23 范围外；`contract.md` §8 角色裁剪；`adr-0016-product-events-oltp.md`；`tickets/T-13.md`（明确「本票不做什么：数仓」）
- grok：`four-pillars-plan.md`（N/A + 明确还不做数仓）；`four-pillars-diagnosis-and-plan.md`（时机：非第一切片；**丢弃** §3.10 表清单）
- 宪法：`sdlc.config.yaml` → `.claude/rules/project_rule.md`；词汇 `CONTEXT.md`
- OLTP：`platform_core/models/{spider_task,spider_result,llm_token_usage,channel_event,capability,tenant,archive,notification}.py`
- 队列：`platform_core/queues.py`
- 伪指标：`backend/services/{quota_service,spider_query_service,llm_usage_service,newapi_overview_service}.py`；`backend/repositories/llm_token_usage_repository.py`；`backend/app/api/v1/tenant_usage.py`；`scrapy/pipelines/quality.py`；`frontend/official/src/pages/Home.tsx`
- 隔离：`backend/app/tenant_isolation.py`（未豁免 `capability_assets`）
- 方言：`backend/tests/test_t10_fix_regressions.py`（P-WH-01）
- 本轮检索：业务树无 `metrics.yaml`；无分层前缀表；无产品事件 SDK；无 ClickHouse/Doris；无 `listing_state` / `capability_installs` / `POWER_MARKET`
