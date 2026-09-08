# 定义帽 · DBA 诊断（feat-four-pillars-v2）

| 字段 | 值 |
|------|----|
| 特征 | `feat-four-pillars-v2`（supersedes `feat-four-pillars`） |
| 角色 | dba |
| 日期 | 2026-09-08 |
| 泳道 | L4 |
| 上游 | grok-files 设计/复审/计划/spec；旧程序 `feat-four-pillars` 诊断与塑形（**输入，不是现行合同**）；现码 ORM / Alembic / `tenant_isolation.py` / `queues.py` |
| 宪法 | `sdlc.config.yaml` → `.claude/rules/project_rule.md`；ADR-0002：先访问模式后索引；AI 禁写 Alembic SQL；破坏性 DDL 走 expand-contract |
| 现状 head | **`027_spider_tasks_status_varchar`**（线性 001→027，32 个 revision，单头）。仓库内 **0** 个 `*.dbml`。设计稿「头修订已到 030_*」仍过期 |
| 本文件性质 | **诊断**（S0 输入），不是 db-spec / DBML / 迁移。禁止手写迁移 SQL，禁止改 ORM |
| 相对旧 dba（2026-09-07） | 现码 P0 **全部仍在**；产品目标态从「四类目录」升为 **五类平级 + 展示≠停用**；候选行 **禁止 NULL tenant_id**；出站钥匙必须绑单一租户。旧 Q1/Q5 冻结答案仍成立 |

**未写**：Service / Repository 代码、API 形状。业务语义不清处停止并问 pm。旧塑形 ADR/契约只作语义对照，不复制为 v2 合同。

---

## 0. 结论（给 PM / architect 的一页）

现库仍停在 P6 能力目录。Power Market 目标表、`listing_state`、`POWER_MARKET` **代码 0 命中**。能力市场 **可以落**，但不是旧诊断写的「四张新表」：全新方案是 **五张新表** + `capability_assets` 只加列、**不改** `uq_asset_type_name_alive` + **`asset_type` 值域 expand-contract**（`expert`→`agent`，`expert_team`→`team`）+ 安装行走 `TenantMixin`、目录表进豁免。一期约 **320** 行资产，无需 gh-ost。

**现库当天会炸的，不是缺市场表，是隔离契约、入队租户、配额谓词、出站钥匙未绑租户。** 这些与市场 DDL 解耦，属 Wave 0 数据不变量。

### 0.1 哪些 P0 仍在 / 已变 / 不再当 schema 阻塞

| 旧 ID | 2026-09-08 复验 | 状态 | 说明 |
|-------|-----------------|------|------|
| 豁免：`capability_assets` 有 `tenant_id`（恒 NULL）、非 Mixin、**未**进 `TENANT_EXEMPT_TABLES` | **仍在 · P0** | 未变 | 模型注释仍写「豁免白名单」。`tenant_isolation.py` 清单仍只有 `skills` 三表 + 无列防御项。Core UPDATE 0 行。R13 仍不扫「有列无 Mixin 未豁免」 |
| 入队不写 `tenant_id`：门面 `SpiderService.enqueue` 不转发；`schedule_service._fire`、`create_task_from_template` 不传 | **仍在 · P0** | 未变 | `SpiderTaskService.enqueue` 有参数；三条产任务路径丢掉。DDL 017 起 9 表 `tenant_id NOT NULL`；ORM Mixin 仍可空 → SQLite 绿、MySQL 红 |
| 配额 `COUNT spider_results WHERE tenant_id=?` **不排除** `source='marketplace'` | **仍在 · P0** | 未变 | `quota_service.py` `_count_results` 仍全表。新方案 **禁止** 候选 `tenant_id` NULL，因此「带租户的候选顶满存储」从假设变成 **必然**，谓词排除更硬 |
| 幽灵迁移 `028/029/030_*.pyc` + `api_key.pyc` / `billing.pyc`，无对应 `.py` | **仍在 · P0** | **变严重** | 头仍是 027。新方案要出站钥匙绑定，**禁止复活 028 表当捷径**；Q-BILL 未决，**禁止复活 029 billing**；030 含 `uq_spider_results_tenant_spider_hash`，**禁止当 Q7 已决** |
| 回流 `msg.get("tenant_id")`；爬虫消息常无此字段 | **仍在 · P0** | **语义已变** | 旧诊断写成「库内可能 NULL」。017 **禁止** NULL。真库插入失败或 SQLite 放行。新方案：值 = 入队租户；超管无企业空间触发入站 → **占位租户**（见 §2.6），不是放宽列 |
| `skills.name` 无 `alive_flag` | 仍真 | **不阻塞 schema** | 产品无「软删再建同名」路径（旧 Q1）。第三方 child 禁止软删，只标 `missing` |
| 设计稿「头 = 030」 | 过期 | **已关闭为事实** | 单头 027。权限种子跟 027 之后下一次 autogenerate |
| CONTEXT 四类词汇 | **已变** | 词汇已五类 | 仓库 `CONTEXT.md` 2026-09-07b 已改五类平级。旧 dba「四类目录 / 四张新表」作废 |
| Redis 月度 field 无 tenant | **仍在 · P1** | **不再挡 FR-10** | 写入仍 `{dim}\|total`；读取先 `{tenant}\|dim\|total` 再 fallback。计划把 FR-10 闸放到 `QuotaService` + `llm_token_usage` 表。`llm_client.get_month_used` **仍读 Redis**，供应商熔断仍可能串租户。记债，expand-contract field，不挡市场 PR1 |
| `departments` 有列非 Mixin | **仍在** | **本程序降为债** | 计划点名不改组织模型。读不注入仍在。不要豁免。不进 Wave 0/1 市场 DDL |
| `source_type VARCHAR(16)` vs `marketplace_crawled`(20) | **仍在 · P1** | 未变 | 新方案还要加 `source_indexed`(14)。同一次市场 DDL **放宽到 32**（扩大，非破坏） |

**本轮 schema 定性（v2）：**

- Wave 0：**无** 市场新表。隔离登记 + 入队/配额/出站钥匙的数据不变量 + 用量上海日历 + 推定 `product_events`。出站钥匙 v1 **走配置绑定，不建表**。
- Wave 1：纯加法（**五表** + assets 加列 + `skill_jobs.source_id` + `source_type` 放宽）+ `asset_type` **值域**三步 + 第一方 listed 回填脚本。禁止改 catalog 唯一键。禁止 rename `capability_experts`。禁止手写迁移 SQL。

---

## 1. 现库盘点（2026-09-08 复验）

### 1.1 Alembic 链

单头：`027`。`down_revision` 线性，32 个 `.py`，无分叉：

`001 → 002 → 002a → 003 → 004 → 005 → 006 → 007 → ce5210dedbd4 → 8551b2c539b2 → a1b2c3d4e5f6 → e7a6f5a12bc9 → 008 → … → 027`

`check-db-migrations.sh` 对含 `SM-EXEMPT` 的历史文件跳过；017/018/014 已 grandfathered。

**幽灵修订（勿当 head，勿 `upgrade` 到它们）：**

| pyc（2026-09-07 时间戳） | 无对应 .py | 从字节串看到的对象 | v2 处置 |
|--------------------------|------------|---------------------|---------|
| `028_api_keys_and_fetched_at.pyc` | 是 | 表 `api_keys`（`tenant_id` / `key_prefix` / `key_hash` / `created_by`） | **不要复活**。Wave 0 出站绑定用配置（§2.7） |
| `029_billing_cost_retention.pyc` | 是 | `tenant_subscriptions`、plans/orders、`cost_cents` | Q-BILL 未决，**禁止**进本程序 |
| `030_heartbeat_perms_last_login.pyc` | 是 | `last_login_at`、角色 JSON 种子、`uq_spider_results_tenant_spider_hash` | 权限种子另步 autogenerate；**不要**借 030 加结果 UNIQUE |
| `platform_core/models/__pycache__/api_key.pyc` | 无 `api_key.py` | `ApiKey` + `TenantMixin` | 同 028 |
| `billing.pyc` | 无 `billing.py` | `TenantSubscription` | 同 029 |

若某环境 `alembic_version` 曾打到 028–030：那是「做过又撤」的脏库。SRE 用备份/手工 stamp 回 027，**不要**把 pyc 当迁移源。本诊断不写恢复 SQL。

`scripts/check-db-ir.sh`：无 `*.dbml` 时静默通过。市场实现必须先落 S1 IR，否则闸门假绿。

`alembic/env.py`：未开 `compare_type`。autogenerate 必须 `MYSQL_FIDELITY=1` 对人审，禁止脑补 SQL。

### 1.2 与四支柱直接相关的表（差量：目标表仍不存在）

| 域 | 表 | 一行 = | 租户 | 软删 | 业务唯一键 | Alembic |
|----|----|--------|------|------|------------|---------|
| 采集 | `spider_tasks` | 一次爬取任务 | Mixin；**DDL NOT NULL / ORM 可空** | 有 | 无 | 002a→027 |
| 采集 | `spider_results` | 一条采集 item | Mixin；DDL NOT NULL / ORM 可空 | 有 | **无**（`content_hash` 非唯一） | 002+hash+012 |
| 采集 | `spider_schedules` | 一条 cron 计划 | Mixin | 有 | **无** | 003 |
| SaaS | `tenants` | 一个隔离单元 | 自身 | 有 | `slug` 不含 alive（025：注销不复用） | 017；**024 已种子 `slug=platform`** |
| SaaS | `users` | 一个登录主体 | Mixin **覆盖 NOT NULL** | 有 | `(tenant_id, username)`；email 全局 unique | 001→024 |
| SaaS | `departments` | 租户内一个部门 | 列 NOT NULL，**非 Mixin** | 有 | `(tenant_id, name, alive_flag)` | 022→025 |
| SaaS | `llm_token_usage` | 租户×维×模型×日 | Mixin | 无 | `(tenant_id, provider_name, model, stat_date)` | 013→017 |
| 市场 | `skills` | 一个技能治理行 | 列恒 NULL | 有 | `name` **全局、无 alive_flag** | 014 |
| 市场 | `capability_assets` | **现网四类**目录一行 | **列恒 NULL，非 Mixin** | 有 | `(asset_type, name, alive_flag)` | 018→025 |
| 市场 | `capability_plugins/experts/teams` | 类型化细节 1:1 | 无 tenant 列 | 无 | DDL `uq_*_asset(asset_id)`；**ORM 未声明 UniqueConstraint** | 018 |

**不存在（grep 仅 CONTEXT / 设计稿）：** `listing_state`、`capability_sources`、`capability_components`、`capability_installs`、`capability_aliases`、`capability_commands`、`product_events`、`writable`、`origin_ref`。

现 `ASSET_TYPES = ("skill", "plugin", "expert", "expert_team")`。对外目标枚举是 `skill|plugin|command|agent|team`。库内旧值必须走 D22b，**不能**靠改表名。

`source_type`：assets/skills 均为 `String(16)`；schema 枚举已含 `marketplace_crawled`（20 字符）但 **DDL 装不下**。尚无 `source_indexed`。

横切表（020–021）本程序 Wave 0/1 **不扩**。`system_caches` 与 Redis 并存；市场列表 v1 **不**走这张表。

### 1.3 豁免清单 vs 列事实（P0，与旧诊断逐条复验一致）

`backend/app/tenant_isolation.py` **今日**登记：

`tenants`, `system_configs`, `channel_events`, `channel_probe_results`, `operation_logs`, **`skills`**, `skill_reviews`, `skill_jobs`, `llm_provider_models`。

`PLATFORM_SHARED_READ_TABLES` = `llm_providers`。

注释仍写：「清单内唯一功能必需的豁免是 skills」。这在 P6 双写 `capability_assets` 之后已经是错的。

隔离机制未变：

| 路径 | 条件 | 后果 |
|------|------|------|
| SELECT | 仅 `TenantMixin` + `with_loader_criteria` | 非 Mixin 即使有 `tenant_id` 也 **不过滤** |
| UPDATE/DELETE（`session.execute`） | 有 `tenant_id` 列且 **未** 豁免 → `WHERE tenant_id=?` | NULL 平台行 **0 命中** |
| UoW `flush` 脏对象 | **不**经 `do_orm_execute` | setattr+flush 可能成功（与 repository 分叉） |
| before_flush 断言 | 仅 `TenantMixin` 新行 | 非 Mixin 写入不断言 |

| 表 | 有 `tenant_id` | Mixin | 已豁免 | 租户态 |
|----|----------------|-------|--------|--------|
| `skills` | 恒 NULL | 否 | **是** | Core 写不注入 |
| `capability_assets` | 恒 NULL | **否** | **否** | Core UPDATE 0 行；SELECT 不过滤 |
| `capability_plugins/experts/teams` | 否 | 否 | 否 | 无列，注入跳过 |
| `departments` | NOT NULL | **否** | 否 | 写注入碰巧对；**读不注入** |
| 目标 `sources/components/aliases/commands` | 无或恒 NULL | 否 | **必须登记** | 同 assets |
| 目标 `capability_installs` | NOT NULL | **必须 Mixin** | **禁止豁免** | 行级隔离 |

R13 只保证：组装点注册清单、`tenant_context.py` 不含表名字面量。它 **不** 扫描「有 `tenant_id` 列却既非 Mixin 又不在清单」。

### 1.4 入队 / 回流 / 配额（Wave 0 数据面，复验调用点）

| 路径 | 证据 | 后果 |
|------|------|------|
| 门面 `SpiderService.enqueue` | 只转发 `spider_name/params/priority`，**丢掉** `tenant_id` | 调度与 AI 试采经门面 → 任务行 NULL |
| `schedule_service` L275 | `enqueue(...)` 不传 `schedule.tenant_id` | 定时任务无主 |
| `create_task_from_template` L372–376 | 不传模板 `tenant_id` | 模板任务无主 |
| `SpiderTaskService.enqueue` | 有 `tenant_id` 参数，写入任务行并放进 Redis 消息 | 直连 API 路径可用；门面破坏它 |
| consumer 批量路径 | `tenant_id=msg.get("tenant_id")` | 消息无字段 → None → MySQL 拒插 |
| consumer `_ingest` L772 / L778 | `find_by_content_hash` **不传** tenant；`create_for_task` **不传** tenant_id | 跨租户去重 + NOT NULL 失败 |
| `QuotaService.check_result_storage` | `WHERE tenant_id==?` 无 source | 候选计入存储 |
| `daily_result_counts` | `func.date(created_at)`，无 tenant、无 source | 平台看板混候选；会话时区 |
| `query_public_results` | 只按 `spider_name` 分页，**无 tenant** | 出站钥匙一旦非空即混拉（GWT-08.4） |
| `tenant_usage.py` | `datetime.utcnow().strftime("%Y-%m")` | 上海 00:30 可能算上月（FR-16.2） |
| `llm_usage_service._today()` | `date.fromtimestamp(time.time())` 进程本地日 | 与上海日历不一致 |
| 公开限流 | `public_skills.py` L81–83 `INCR` 后条件 `EXPIRE` | 崩溃留下无 TTL 键；`rate_limiter.py` 已 pipeline |

### 1.5 时区 / 主键 / 类型（存量不按教科书改）

- 主键普遍 `Integer` AUTO_INCREMENT。新表跟仓内惯例。
- `DATETIME` 与 `DateTime(timezone=True)` **混用**。新市场表 **跟 assets 走 naive DATETIME + 文档约定 UTC 存储**；业务日历（用量、WACT、事件切日）**Asia/Shanghai**，写路径换算，不改 TIMESTAMP。
- 枚举一律 VARCHAR + 应用校验。`listing_state` / `source.type` / `host` / `asset_type` / `components.role` **禁止** MySQL ENUM。设计稿 DBML 里的 `Enum listing_state_enum` 只作文档，S1 必须落成 varchar。
- 金额：本特征无钱。配额在 `tenants.quota` JSON。订阅 **不占** 三类配额。
- `users.email` 全局 unique：保持。
- `host_compat` JSON：**NULL 与 `[]` 不是一回事**（§2.4）。禁止用空数组当「未声明」。

### 1.6 ORM ↔ 迁移漂移（create_all 测试 vs 真库）

| 对象 | 迁移链 | ORM / create_all |
|------|--------|------------------|
| 9 张业务表 `tenant_id` | 017 NOT NULL | Mixin 可空 |
| `capability_plugins.asset_id` 等 | UNIQUE + 又建 `ix_*_asset_id`（冗余） | 仅 `index=True`，无 UniqueConstraint |
| `spider_results (spider_name, created_at)` | 012 名 `ix_spider_results_spider_created` | ORM 名 `ix_spider_results_name_created` |
| `ix_skills_name` | 014 UNIQUE `uq_skills_name` **另**建单列索引 | `unique=True, index=True` 双份 |
| Mixin `tenant_id index=True` | 026 已删被前缀覆盖的单列 | `create_all` 仍会建 |

S3 对人审时盯这些，避免 autogenerate 再「补」一份真库已有的键，或 drop 018 已有的 `uq_*_asset`。

---

## 2. 全新方案必须钉死的数据语义

旧 dba 按「四类 + 四张新表」写目标态。v2 以 `power-market-design.md` D1–D29 + grok-files 计划 §7 + 仓库 `CONTEXT.md` 为准。下面每条都是 **一行 = ___ / 当时还是现在 / 唯一键 / NULL 含义**。缺一条，S1 DBML 会把下游带偏。

### 2.1 粒度（一行 = ___）

| 实体 | 一行 = | 判定 |
|------|--------|------|
| `capability_sources` | 一条已登记的外部树（稳定 `name` + `type` + `uri`） | 新实体。plugin-updater **不是**源。配置删除 = **停用不清行** |
| `capability_assets` | 五类之一的 catalog 身份（类型内全局 `name`） | **已有**。扩展列，不改粒度。对外 `agent`/`team`；库内存活值回填后拒绝 `expert`/`expert_team` |
| `capability_plugins` | 一个分发单位的细节（MCP/hooks/版本） | **已有**。**不是**订阅礼包 |
| `capability_experts` | 一份智能体人设（表名≠产品名词） | **已有，不 rename** |
| `capability_teams` | 一团长 + 成员智能体[] | **已有**。同步不造团 |
| `capability_commands` | 一条 slash 命令 | **新细节表**。无软删；随资产软删（FK CASCADE 仅细节行） |
| `skills` / `skill_reviews` / `skill_jobs` | 技能治理 / 一次评分 / 一次作业 | **已有**。不合并进 assets |
| `capability_components` | 一条 **出处或运行时引用** 边 | 新实体。**不是**安装礼包。角色 ∈ `bundled_skill\|bundled_command\|bundled_agent\|uses_skill\|team_member` |
| `capability_installs` | 某租户把 **某一行** 资产订到某宿主的一次订阅 | 新实体。同一能力第二宿主 = **新行**，不覆盖第一行 |
| `capability_aliases` | 一条人工 vanity slug → 一个资产 | 新实体。同步不自动建 |
| `listing_state` | 资产的产品上架态 | **字段**，禁止 `capability_listings` 表 |
| `status` | 治理/质量生命周期 | **已有字段**。与 listing 分列 |
| `health_status` | 插件验证态 | **已有**。上架 **不**要求 healthy（无 MCP = `unknown` 可 listed） |
| `product_events` | 一次已发生的产品事实 | **推定新实体**，Wave 0 就要能按时间查 |
| 市场候选 | `spider_results` 中 `source='marketplace'` 的一行 | **不新实体**。`tenant_id` NOT NULL |

**不是实体：** SOURCE.yaml 指针、`host_compat`（JSON 列）、`alias_origin_refs`（JSON）、UNLISTABLE_PACKAGES（配置）、verify 结果（已在 `verify_detail`）、kimi 第五类表、`capability_agents` 表、数仓 ODS、候选独立表、billing 表。

计划 §7 把组件边写成「插件 → bundled 子资产」——相对 D28 **过窄**。DBA 按 D28：插件→skill/command/agent；智能体→skill；专家团→agent。

### 2.2 三道闸（展示 / 新订 / 运行）不得合成一列

```
listing_state          新订                         运行时引用 / 已订
────────────────       ────────────────────────     ────────────────────────
listed                 可（再过治理+许可+宿主）      是
coming_soon            否（商店可见、无按钮）         已订仍有效
unlisted               否（商店 404/同形 422）        已订仍有效；引用仍解析
status=blacklist       公开 404                      解析跳过；安装只读可卸
软删                   不存在                        解析跳过
```

同步 **不得**改 `listing_state`（UNLISTABLE 只把误标 listed 的 **插件行** 收回，不连坐子卡）。

`listed` + `status=blacklist`：应用拒绝或保存时收回 unlisted。不要用 CHECK 约束（改值要 DDL）。

### 2.3 快照 vs 引用（「当时 / 现在」）

| 值 | 当时 / 现在 | 落点 |
|----|-------------|------|
| 目录 `name` / 公开 URL | 现在 | 引用；唯一键不改 |
| `listing_state` | 现在 | 资产列；同步不得覆盖 |
| `listed_at` | 当时（最近一次上架时刻） | 资产列；**unlist 不清空**（默认；pm 可一票否决） |
| 安装时的标题/版本 | spec 未要求历史小票 | **引用** `asset_id`；商店 JOIN 当前 title |
| 许可 | 公开闸要「现在能不能看」 | 资产行 `license` = 同步拷贝（现在）；`public_license_override` 是现在。插件细节列 **保留**（快照+引用并存） |
| `content_hash` | 当时那棵树 | 资产列 |
| 插件 manifest | 当时原文 | `capability_plugins.manifest` JSON 快照 |
| `skills.file_path` | 合成指针，不是解析输入 | 满足 NOT NULL；读文件走 `source_id+origin_ref` |
| 下架后的安装行 | FR-29 / D23：**保留引用** | 不拷贝 listing；unlist 后「我的安装」仍在 |
| `host_compat` | 现在 | JSON；见 §2.4 |
| `writable` | 现在 | 资产列；第一方 1 / 第三方 0。attach 源时改 0 |
| `alias_origin_refs` | 当时被折叠的路径集 | JSON，供次级 upsert，**非**查询列 |
| `capability_aliases.asset_type` | 现在（反规范化） | 公开路由第一段；D22b 回填时若已有行必须同步。PR1 别名表空，无存量 |

### 2.4 `host_compat` 的 NULL 含义（已冻结，实现最容易写反）

| JSON | 产品含义 |
|------|----------|
| `NULL` / 缺列（未声明） | **四个宿主都可订**（Grok / ZCode / Kimi / Claude） |
| `[]`（已声明空数组） | **四个都不可订** |
| 非空数组 | 仅名单内可订 |

第一方 listed 回填必须走 **未声明（NULL）**，禁止写成 `[]`（否则 FR-31 全不可订）。这不是「空值优化」，是业务正确性。

### 2.5 组件边的三张查询脸（同一张表，三个谓词）

| 脸 | 过滤 listing？ | 过滤 blacklist/软删？ | 调用方 |
|----|----------------|------------------------|--------|
| 运行时 `resolve_runtime_refs` | **否** | **是**（跳过并记审计） | 执行/依赖解析 |
| 管理 `GET .../components` | **否**（含 unlisted 子行） | 给治理台看量子行 | 超管 |
| 公开详情「包含」 | **只要** listed/coming_soon | 是 | 商店 |

许可黑名单 **不**挡已安装行与引用解析（挡住的是新订阅与公开展示）。

删除父资产：**RESTRICT 子资产行**（D28）；只删边。不要 `ON DELETE CASCADE` 到 child **资产**。细节表（plugins/experts/teams/commands）对 **自己的** `asset_id` 可 CASCADE（随资产软删/物理删清细节）。安装行对资产：**RESTRICT**（订阅史不随物理删消失；产品路径是软删资产）。

`components` **不要**软删。`missing` 子行：默认 **保留边**，列表 JOIN 过滤。同步不删行。

### 2.6 候选所有权（相对旧诊断的硬变化）

旧诊断：候选若带某租户 id 会把存储顶满 → 用 `source <> 'marketplace'` 隔离；并讨论「平台行 NULL」。

v2 钉死：

1. **不**迁出 `spider_results`（Q-CAND 债）。
2. **不**放宽 017。`tenant_id` NOT NULL。
3. 值 = 入队租户（触发者）。
4. 平台超管无企业空间触发入站：使用 **占位租户**，禁止 NULL。
5. 配额 / 我的结果 / 数据中心 / 导出 / 出站拉数：`source IS NULL OR source <> 'marketplace'`。
6. 超管候选列表：`source='marketplace'` SQL 分页。
7. `extra.review` 协议冻结，不得再加键当市场状态机。
8. WACT 用事件字段 `is_marketplace_candidate`，不得靠事后猜 `source`。

**占位租户默认（DBA，不发明第三租户）：** 复用 024 已种子的 `tenants.slug='platform'`。产品面永不把该行的 marketplace 结果展示为「我的结果」（靠 source 过滤）。若 pm 要求「入站并发与平台超管自己的任务分账」，再单开 `slug=marketplace-inbound`——那是新产品实体，本波不默认建。

### 2.7 出站钥匙绑定（Wave 0，无表）

今日 `EXTERNAL_API.API_KEYS: []`（空 = 全拒，安全）。非空字符串列表命中后 `query_public_results` **无 tenant** → 混拉。

数据语义：一把钥匙 **恰好** 绑定一个 `tenant_id`。未绑定 = 拒绝，响应 0 行。绑定后仍排除 marketplace。

v1 **不要**建 `api_keys` 表、**不要** stamp 028。配置从「字符串列表」扩成「key → tenant_id」映射；旧列表在 expand 期视为未绑定。FR-52 租户自助钥匙才是新实体（TenantMixin、不豁免、UNIQUE `key_hash`），不在本波。

### 2.8 `product_events`（Wave 0 度量；推定表名）

`operation_logs` 不能当漏斗分母（无事件名、无匿名访客、无 `tenant_id`）。

| 决策 | 值 |
|------|----|
| 一行 | 一次已发生的产品事实 |
| 软删 | **不要** |
| 改历史 | **不要**（只追加） |
| `event_name` | VARCHAR(64)，应用枚举（蓝图冻结名，dba 不改口径） |
| `occurred_at` | naive DATETIME，**存 UTC**；切日 Asia/Shanghai |
| `tenant_id` | 可空（匿名页） |
| `actor_user_id` / `anonymous_id` | 可空；已登录优先租户+用户 |
| `props` | JSON，非查询列 |
| 幂等 | 契约写「至少一次」。v1 **不**建 UNIQUE(`idempotency_key`)（漏斗可接受重复；去重在查询）。若 pm 要精确一次，再加键 |
| 索引（推定 Top-N） | `(event_name, occurred_at)`；`(tenant_id, occurred_at)` |
| TTL | 表内 ≥ **90 天**；超期归档/删。无 TTL 会把主库变成日志库 |
| 失败 | **不得**挡主路径；此表不是配额闸依赖 |
| v1 | 不进 Redis、不上外部 SDK |

### 2.9 身份与唯一键（保持全局 name）

| 表 | UNIQUE | 软删 |
|----|--------|------|
| `capability_sources` | `(name, alive_flag)` | 要（删后可重建同名源） |
| `capability_assets` catalog | **保持** `(asset_type, name, alive_flag)` | 已有 |
| `capability_assets` 同步身份 | **新增** `(source_id, origin_ref, alive_flag)` | 已有 |
| `capability_components` | `(parent_asset_id, child_asset_id)` | **不要** |
| `capability_installs` | `(tenant_id, asset_id, host, alive_flag)` | 要（卸载后可再订） |
| `capability_aliases` | `(slug, alive_flag)`；写入另查存活 `assets.name` → 应用 409 | 要 |
| `capability_commands` | `(asset_id)` 1:1 | 不要（随资产） |
| `skills.name` | 全局、无 alive | 已有；本波不改 |
| `product_events` | 无业务唯一 | 不要 |

`source_id` NULL 的第一方行：MySQL UNIQUE 含 NULL **不判重**。禁止代码假设「NULL source_id ⇒ 永远第一方」。

`commands.slash`：**不要**全局 UNIQUE（两插件都可以有 `sdlc`）。catalog 身份是 `{plugin}__{stem}`。

`components.role` **不**进唯一键：同一父子只允许一条边。

`bundled_command` = 16 字符。设计稿 `role VARCHAR(16)` 顶格。S1 **放宽到 VARCHAR(32)**（扩大），避免下一个 role 再改列。

### 2.10 D22b：`asset_type` 值域是破坏性 **数据** 变更，不是 rename 表

现网允许值：`skill|plugin|expert|expert_team`。目标对外：`skill|plugin|command|agent|team`。

这是 **UNIQUE 键左列的取值改写**。结构不变，判重集合变了。

三步（跨发布，数据脚本不进 autogenerate DDL）：

1. **Expand：** 应用读写同时接受旧值与新值；公开 JSON 只出新枚举（读映射 `expert`→`agent`）。
2. **Migrate：** 回填 `expert`→`agent`、`expert_team`→`team`。前置探测：同名存活行在新旧取值下会不会撞 `uq_asset_type_name_alive`（现网无 `agent`/`team` 行 → 期望 0 组）。别名表若已有行同步 `asset_type`。
3. **Contract：** 写路径拒绝旧值。不 rename `capability_experts`。不改唯一键列集。

商店面打开前必须完成回填。与「加 listing 列」同波可以，但 **不要**把 UPDATE 写进 Alembic 业务 SQL。

### 2.11 列缺口（Wave 1，只加不改唯一键）

现 `CapabilityAsset` **没有：** `listing_state` / `listed_at` / `source_id` / `origin_ref` / `origin_local_name` / `origin_plugin_name` / `host_compat` / `alias_origin_refs` / `license` / `public_license_override` / `writable`。

现 `SkillJob` **没有：** `source_id`。`job_type VARCHAR(16)` 装得下 `src_sync` / `scan_plugins` / `promote`，不必 widen。

`listing_state VARCHAR(16) NOT NULL` 必须 `server_default='unlisted'`（SM-5）。`writable` default 1；`public_license_override` default 0。

`origin_ref VARCHAR(256)`：现盘子路径远小于 256。若适配器允许任意深度，改为 512 与 `file_path` 对齐（Q6，不阻塞）。

### 2.12 第一方回填（DDL 与数据分离）

大回填不进迁移文件。

1. autogenerate **只 DDL**。
2. 独立幂等脚本：第一方（`source_id IS NULL` 且 `asset_type='skill'` 且 `source_type='self_built'`，或 `file_path` 以 `skills/` 开头）且 `status IN ('stable','recommended')` → `listing_state='listed'`，`writable=1`，`host_compat` **保持 NULL**。
3. 校验：`listing_state='listed' AND source_id IS NOT NULL` → 0（PR1 不得 attach 源）。
4. 存量 `sdlc-workflow` 插件行保持 `self_built`+`writable=1` 直到第一次 `src_sync` attach（窗口期，Q2）。

禁止「NULL source_id ⇒ 永远当成第一方」的代码假设。

---

## 3. 访问模式（全部 **推定** — 无 production slow_query）

来源：设计 Q1–Q14、计划 §7、FR、repository 调用点。上线后用 `performance_schema` 复盘。**Top-N 之外不建索引。**

现有 EXPLAIN 证据（`test_db_behavior_loop.py`，需 `MYSQL_FIDELITY=1`）：

- `spider_results WHERE spider_name=? ORDER BY created_at DESC` → 断言 `type != ALL`（012 复合）
- `capability_assets WHERE asset_type=? AND name=?` → 断言走 UNIQUE

**没有** 租户列表、配额 SUM、候选 `source=`、市场 listing 过滤的 EXPLAIN。S4 真库补。

### 3.1 Power Market（相对旧诊断的差）

旧 Q1–Q12 仍成立；新增：

| ID | 相对旧稿 | 索引 |
|----|----------|------|
| Q13 | 运行时 parent→children，**不**滤 listing | **复用** UNIQUE(parent, child) 最左前缀。设计稿 `ix_components_parent` = 重复 → **不建** |
| Q14 | 管理 `asset_type=command` 翻页 | 走 Q1，无新索引 |
| Q2 | 公开五类 + coming_soon | 仍 `(listing_state, status, asset_type, category)`。`JSON_CONTAINS(host_compat)` **不建函数索引** |
| 命令 `slash` 全局查找 | 设计稿 `ix_commands_slash` | **评估不建**：无 Top-N；slash 非全局唯一；300 行可扫 |

其余 Q1 / Q1b / Q3 / Q4 / Q5 / Q6 / Q7 / Q8 / Q9 / Q10 / Q11 / Q12 与旧诊断一致（Q6 不重复建 parent 单列）。E1/E2 埋点索引仍推定。

**评估不建（沿用 + 新）：** `status`/`listing_state` 单列；`host_compat` 函数索引；`alias_origin_refs` 多值；`description` 全文；给 `skills` 加 `(source_type)`；`ix_commands_slash`；任务默认 `(tenant_id, id)`。

### 3.2 智能采集缺口（推定，Wave 0 先谓词后索引）

C4：`find_by_content_hash` 批量路径传 tenant，**单条 `_ingest` 仍不传** → 跨租户去重。C5：`source` 无索引；千到万可扫，Wave 0 先过滤正确。C8：配额必须加 source 排除（P0）。**本轮不**为候选建 `(source, id)` 除非慢查询。

不要复活 030 的 `uq_spider_results_tenant_spider_hash`：加 UNIQUE 前必须查重复，且 Q7 未决。

---

## 4. 撞键场景（同步必须 parse_error / 折叠）

与旧诊断 4.1 相同，外加：

| 场景 | 键 | 对策 |
|------|----|------|
| D22b 回填后 `expert` 与已有 `agent` 同 name | `uq_asset_type_name_alive` | 回填前探测；现网无 agent 行 |
| 命令短名跨插件相同 | catalog `name` | 前缀 `{plugin}__{stem}`，与 skill 同一规则 |
| `commands.slash` 跨插件相同 | 无全局 UNIQUE | **正确**；不要加 |
| git `origin_ref="."` vs monorepo 目录 | `(source_id, origin_ref)` | 不同字符串；禁止混用 |

`dev-team`：D20 只禁 **插件行** listing，不连坐子卡。同步不自动合并双份 `tdd`——运营 unlist，不是 UNIQUE 故事。

---

## 5. Expand-contract 风险

### 5.1 Wave 0（无市场新表）

| 变更 | 类型 | 做法 |
|------|------|------|
| 豁免清单 +（可选）Department Mixin | 行为/ORM，不是 DDL | 与权限收口同发。本程序计划 **不改** Department，市场豁免仍必须做 |
| 入队 `tenant_id` 必填 | 数据不变量 | 017 已收紧；真库不应有 NULL。SQLite 测试库会有。拒绝无主入队 |
| 配额/列表/出站排除 marketplace | 查询谓词 | 无 DDL |
| 出站钥匙绑定 | 配置契约 | 无表 |
| 用量上海日历 | 写路径 | 无 DDL |
| `product_events` 新表 | 纯加法 | 单迁移 up/down；autogenerate |
| Redis 月度 field | 键内 expand-contract | 双写新 field → 切读去掉 fallback → 停旧 field。不挡 FR-10，仍应做 |

### 5.2 Wave 1 纯加法 + 值域三步

- 五张新表 + FK + UNIQUE + 访问模式索引
- assets 新列：`listing_state` **必须** server_default；可空 origin/license/host_compat
- 新 UNIQUE `(source_id, origin_ref, alive_flag)`：存量 `source_id` 全 NULL → MySQL 不判重。仍属「加 UNIQUE」，S3 前跑非 NULL 重复探测（期望 0）
- `source_type` 16→32：扩大，同文件可做，**不要**同文件改列名
- `components.role` 直接 VARCHAR(32)
- D22b 回填：**独立幂等脚本**，不是 autogenerate
- 细节表 ORM 补 `UniqueConstraint(asset_id)` 时：真库 018 已有 → S3 审查禁止再 `create_unique`

### 5.3 本轮禁止的破坏性变更

| 变更 | 为何禁止 |
|------|----------|
| 改 `uq_asset_type_name_alive` 为 `(source, name, …)` | 破坏性 UNIQUE + 全部 URL |
| 改 `skills.name` 含 alive / 非全局 | 无重建路径；改键仍破坏 URL |
| rename `capability_experts` → agents | 无访问模式的改表名 |
| 删 `capability_plugins.license` | 删列 = contract；双写即可 |
| 把 `skills.file_path` 改可空 | 设计 D15 明确不改 |
| MySQL ENUM for listing/asset_type/role | 改值要 DDL |
| PR1 回填里 UPDATE 第三方 listing / attach 源 | 同步永不 auto-list |
| 候选迁出 `spider_results` | Q-CAND |
| 放宽 `spider_results.tenant_id` 为 NULL | 与 017 不变量相反 |
| 复活 028/029/030 | 幽灵；billing 未决；结果 UNIQUE 未决 |
| 设计稿重复的 `ix_components_parent` | 最左前缀重复（026 刚删过这类键） |

### 5.4 权限码种子

`btn:market:*` 等是 **数据**。autogenerate 之后的种子，不要手搓 INSERT DDL。不要把 030 pyc 里的角色 JSON 当现行矩阵。

### 5.5 行为验证环（S4，给 qa）

真库 `MYSQL_FIDELITY=1`：

- `upgrade → downgrade → upgrade` 退出码 0
- EXPLAIN Q1 / Q1b / Q2 / Q3 / Q5 / Q6 / Q10 / Q11 / Q12 / Q13 / E1：`type != ALL`
- 约束：重复存活 `(asset_type,name)`、重复非空 `(source_id, origin_ref)`、重复安装、重复 slug、alias=存活 name（应用 409）、installs 缺 tenant_id、`listing_state` 空串、D22b 回填后旧枚举 0 行
- 租户态 `update(CapabilityAsset)` 豁免前后 rowcount（0 → 1）
- 配额 COUNT 含/不含 marketplace；出站无绑定 → 0 行
- `host_compat` NULL 可订 vs `[]` 不可订（数据夹具，不是索引）

容量：无需 gh-ost。`spider_results` 不在本 DDL 集合。

---

## 6. Redis 键

治理：每个键 **name + TTL + 失效路径**。唯一契约源 `platform_core/queues.py`。

相对旧诊断 **未修好** 的阻塞项：

| 键 | 问题 | v2 |
|----|------|----|
| `llm:usage:m:{yyyymm}` field `{dim}\|total` | 写无租户，读有 fallback | P1 债；FR-10 改走表闸后不挡发布，**供应商熔断仍串租户** |
| `quota:count:` | 服务内重写字面量 | 卫生；排除 marketplace 后缓存 key 必须带同一谓词语义 |
| `skill:public:rl:{ip}` | 公开面 INCR/EXPIRE 非原子 | 市场公开面 **复用**此前缀，修 pipeline；不要 `market:public:rl:` |
| `{spider}:dupefilter` persist | 无 TTL 只增 | Q9，非市场 PR1 |

Power Market 新键（推定）：`market:src_sync:{source_name}` 锁，TTL ≥ 最长同步 + 续期，Lua 释放。目录列表缓存 v1 **不建**。埋点缓冲 v1 **不建**。

不要把 `SOURCE.yaml` / clone 放进 Redis。

---

## 7. 推荐落地顺序（给 architect / backend，无 SQL）

**Wave 0**

1. 豁免 `capability_assets`（及 plugins/experts/teams 防御性）。R13 不够：S4 加「有 tenant_id 列 ⇒ Mixin 或豁免」。
2. 入队必须带租户；consumer 优先消息，缺失则 join `spider_tasks.tenant_id`；仍无则 **拒绝落库**（死信），禁止 NULL。占位租户 = `platform`。
3. 配额 / 结果列表 / 导出 / 出站：排除 marketplace。出站钥匙配置绑定；未绑定拒绝。
4. 用量/看板日历改为上海日。
5. `product_events`：S1 小 DBML → autogenerate。公开限流修原子性。
6. Redis 月度 field 双写切读（债，建议同波，不挡市场 PR1）。

**Wave 1**

1. S1 `capability-market.dbml`：五表 + assets 新列 + skill_jobs.source_id + source_type(32) + role(32)。Q6/Q13 去掉重复 parent 索引。过 `check-db-ir`。
2. S2 `/new-model` 扩 `capability.py`；`ASSET_TYPES` 先收新值；Pydantic 只加 schema。
3. 隔离登记 sources/components/aliases/commands；**installs 不豁免**。与 DDL 同发。
4. S3 `MYSQL_FIDELITY=1 uv run alembic revision --autogenerate -m "power_market_sources_listing"`。人工审查：无 drop、无改旧 UNIQUE、NOT NULL 必有 server_default。权限种子另步。
5. 回填脚本：第一方 listed（host_compat 保持 NULL）+ D22b 值域。
6. S4 EXPLAIN + up/down/up + 豁免 rowcount + NULL vs `[]`。
7. Redis：只加 `market:src_sync:` 到 `queues.py`。

**拒绝：** 诊断或实现阶段手写 `op.execute("""ALTER…""")` 业务 DDL。

---

## 8. 开放问题

已冻结、不再问（旧 Q1/Q5 + D22–D29 + 计划 §7）：

| 项 | 答案 | schema 含义 |
|----|------|-------------|
| 无「删除再建同名」 | 源消失=missing，不自动下架 | **不**给 `skills` 补 alive_flag |
| unlist 后安装 | 保留、不可新订；黑名单只读可卸 | installs **不** ON DELETE CASCADE 软删 |
| 订阅配额 | 不占三类 | 不要 COUNT installs 进 result_storage |
| 时区 | Asia/Shanghai 业务日 | 日历不是列类型 |
| 五类平级 | command 新表；experts 不改名 | D22b 值域三步 |
| 订插件 | 不平级礼包 | 不沿边 insert 安装 |
| 候选 | 仍住结果表；tenant_id NOT NULL | 占位租户 + source 谓词 |
| 出站钥匙 | 必须绑单一 tenant_id | v1 配置，不复活 028 |
| host_compat | NULL=全可订；`[]`=全不可订 | JSON 语义，不是约束 |

仍开放：

| ID | 问题 | 阻塞 | 需要谁 |
|----|------|------|--------|
| Q2 | PR1 结束到第一次 src_sync，存量 `sdlc-workflow` 保持 `writable=1` 是否可接受？ | 否（窗口期） | pm |
| Q3 | alias 与存活 `name` 冲突：仅事务内 409，还是 `reserved_slugs` 表？DBA **不要第三张表** | 否 | pm |
| Q4 | child `missing` 时边保留还是删？DBA **保留** | 否 | 默认保留 |
| Q6 | `origin_ref VARCHAR(256)` 是否够深？ | 否 | architect（适配器） |
| Q7 | `(tenant_id, content_hash)` 留谁？本轮是否加 UNIQUE？**不要用 030 pyc** | 否 | pm |
| Q8 | `llm_providers.is_active` 全平台一行还是每租户一行？ | 否 | architect |
| Q9 | scrapy-redis `SCHEDULER_PERSIST` 永生 dupefilter | 否 | pm + data-collector |
| Q10 | 平台态 `daily_result_counts` 是否跨租户？候选是否进平台合计？ | 否 | pm（口径） |
| Q11 | `src_sync` 是否要 Redis 锁？DBA **要锁** | 否 | architect |
| Q12 | `source_type` 放宽到 32 是否纳入市场同一 DDL？DBA **纳入** | 建议纳入 | 默认纳入 |
| Q-EVENTS | 默认 MySQL `product_events` 90 天（与旧 ADR-0016 同向）。pm 若改外部查询面再选 | 有默认 | pm 反对默认时 |
| Q-CAND | 候选是否迁出结果表？ | 否 | 本波谓词隔离 |
| **Q-PLACE** | 入站占位是否就是 `slug=platform`，还是单独 `marketplace-inbound`（并发/配额分账）？DBA **默认 platform** | 否（有默认） | pm 若要分账 |
| **Q-IDEM** | 产品事件是否要 UNIQUE 幂等键？DBA **v1 不要** | 否 | pm / analyst |
| **Q-LISTED-AT** | unlist 是否清空 `listed_at`？DBA **不清空** | 否 | pm 可否决 |

幽灵库是否有人 `upgrade` 过 028–030 → **sre** 盘点，不是 schema 设计问题。

---

## 9. 给下游

| 角色 | 内容 |
|------|------|
| **pm** | 钉 Q-PLACE / Q-LISTED-AT / Q-IDEM 或接受默认。Wave 0 永不砍隔离/配额/出站绑定。组件边按 D28 不是「仅插件 bundled」 |
| **architect** | 目标态=§2–3；豁免清单是隔离契约；五表不是四表；D22b 是数据三步；出站 v1 无表 |
| **backend** | 按未来 DBML 建 ORM；豁免落地前不要在租户态 Core UPDATE assets；入队必须带 tenant_id；consumer 禁止 NULL |
| **qa** | §2.2 负向；NULL vs `[]`；豁免前后 rowcount；配额含候选；出站未绑定 0 行；上海月切；D22b 回填后公开无 `expert` |
| **sre** | PR1 DDL 小表秒级。幽灵 028–030 勿当已迁；脏库 stamp 回 027。S4 需 MYSQL_FIDELITY |
| **data-collector** | 候选仍 `spider_results`；转正依赖 source_type 列宽；不要为 marketplace 源建 `capability_sources` 行（D16） |
| **analyst** | 漏斗用 `product_events`，不用 `operation_logs`；WACT 排除候选看事件字段 |
| **algo** | 无新表需求；评分仍双写 assets，勿写绝对路径 |

---

## 10. DBA 自检

- [x] 新表均有「一行 = ___」（含 commands / product_events / 候选非实体）
- [x] 快照 vs 引用已按「当时/现在」判定（安装默认引用；FR-29 保留；listed_at 默认保留）
- [x] 索引只从推定 Top-N 来；重复 parent 索引与 slash 单列已标评估不建
- [x] 破坏性：本轮不做 catalog 唯一键改造；D22b 按值域三步而非 rename 表
- [x] 无手写迁移 SQL、无改 ORM
- [x] 无新的 production EXPLAIN（已标推定）
- [x] Redis：现键点名 TTL/失效缺口；新键给出 name+TTL+失效
- [x] 未写 Service/Repository，未选 API 形状
- [x] 业务语义已冻结的不再问；其余停止并问 pm
- [x] 坑点文件：本轮无新的 EXPLAIN/测试/ESC/迁移演练达到「实战已验证」，不创建 pitfalls 文件
