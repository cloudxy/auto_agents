# 定义帽 · DBA 诊断（feat-four-pillars）· refresh

| 字段 | 值 |
|------|----|
| 特征 | `feat-four-pillars`（智能采集 + SaaS + 中转站 + 能力市场） |
| 角色 | dba |
| 日期 | 2026-09-07 |
| 泳道 | L4 |
| 上游 | `01-define/spec.md` v1（Wave 0/1 冻结）· `power-market-design.md` Accepted S0 · ORM / Alembic / `queues.py` / `tenant_isolation.py` · `_lessons.md` |
| 宪法 | `sdlc.config.yaml` → `.claude/rules/project_rule.md`；ADR-0002：先访问模式后索引；AI 禁写 Alembic SQL；破坏性 DDL 走 expand-contract |
| 现状 head | **`027_spider_tasks_status_varchar`**（线性 001→027）。仓库内 **无** `*.dbml`。设计稿仍写「头修订已到 030_*」——**与仓库不符** |
| 本文件性质 | **诊断**（S0 输入），不是 db-spec / DBML / 迁移。实现阶段按 S0→S1→S2→S3 autogenerate |
| 相对上一版 | spec 已冻结 dba Q1/Q5；本轮按现码复验，关闭过时阻塞、补 Wave 0 数据面缺口 |

**未写**：Service / Repository 代码、API 形状。业务语义不清处停止并问 pm。

---

## 0. 结论（给 PM / architect 的一页）

能力市场的目标态 **可以落**：四张新表 + `capability_assets` 只加列、**不改** `uq_asset_type_name_alive`、安装行走 `TenantMixin`、目录表进豁免。一期约 300 行资产，无需 gh-ost。spec 已冻结：第三方 **没有**「软删再建同名」产品动作（源消失=missing）；下架后安装行 **保留**。因此上一版 P0「`skills.name` 必须补 `alive_flag`」**不再阻塞 schema**。

**现库仍会在同步/上架/配额当天出错的，不是缺表，是隔离契约与计量键写错。**

| 级别 | 发现 | 为何会炸 | 改进 |
|------|------|----------|------|
| **P0** | `capability_assets` 有 `tenant_id`（恒 NULL）、**不**继承 `TenantMixin`、**未**进 `TENANT_EXEMPT_TABLES`。模型注释却写「豁免白名单」。 | `BaseRepository.update` / `soft_delete` 走 `session.execute(update)` → `do_orm_execute` 对含 `tenant_id` 列且未豁免的表注入 `tenant_id=?`。平台行全是 NULL → **0 行命中**，扫描双写 `upsert_skill_asset` 的 flush 路径与 repository 路径行为还不一致。 | 与 Wave 0 FR-06 同发：豁免 `capability_assets`（及后续 sources/components/aliases/plugins/experts/teams）。**禁止**豁免 `capability_installs`。R13 只校验清单自洽，**不会**发现「有列无 Mixin 未豁免」。 |
| **P0** | 定时 / 模板 / AI 试采入队 **不把** `schedule.tenant_id` / 模板租户写进 `spider_tasks`。DDL 017 起这些表 `tenant_id NOT NULL`；ORM `TenantMixin` 仍可空。 | 真库插入 NULL → 失败或落到无主任务；SQLite `create_all` 按 ORM 可空放行 → 测试绿、MySQL 红。FR-09 要求三条任务都属提交者企业。 | 数据契约：这 9 张表 ORM `tenant_id` 与 DDL 对齐为 NOT NULL（`llm_providers` 除外）。入队必须带租户（实现帽；DBA 只定「一行必须有租户」）。 |
| **P0** | 结果存储配额 `COUNT spider_results WHERE tenant_id=?` **不排除** `source='marketplace'`。 | 市场候选与租户采集共表。FR-11：候选不计存储、不出现在「我的结果」。候选若带某租户 id，会把企业存储顶满。 | 配额与数据中心 WHERE 加 `source <> 'marketplace'`（或 `source IS NULL OR source <> 'marketplace'`）；候选列表继续用 `source='marketplace'`。本波 **不** 迁出采集表（Q-CAND 技术债，产品已要求语义隔离）。 |
| **P1** | Redis 月度用量 **写入** field=`{dim}\|total`（无租户），**读取** 先 `{tenant}\|dim\|total` 再 fallback 全局。 | 实时熔断串租户。日明细 field 已是四段，月度写漏了 tenant。FR-10 会表现为 A 耗尽连累 B 或 B 的熔断读到 A。 | 键内 field expand-contract：双写 `{tenant}\|dim\|total` 与旧 field → 切读去掉 fallback → 停旧 field。常量只从 `queues.py` 引用。 |
| **P1** | `source_type VARCHAR(16)` 装不下 `marketplace_crawled`（20）。 | 采集转正路径 STRICT 截断/报错。 | 同一次市场 DDL 放宽 assets/skills → `VARCHAR(32)`（扩大，非破坏）。 |
| **P1** | 公开限流 `INCR` 与 `EXPIRE` 非原子（`public_skills.py`）；`rate_limiter.py` 已改 pipeline。 | 进程崩溃留下 **无 TTL** 计数键。与 skill 已知坑相同，公开市场将复用此前缀。 | 实现阶段改 `pipeline(transaction=True)`；市场公开面 **复用** `skill:public:rl:`，不要新前缀。 |
| **P1** | FR-16 冻结 Asia/Shanghai 业务日；用量页用 `datetime.utcnow().strftime("%Y-%m")`；Redis `_today()` 用进程本地日；`daily_result_counts` 用 `func.date(created_at)`（会话时区）。 | 上海 00:30 仍可能算上月（FR-16.2）。北极星 WACT / 月度 token 口径不可对账。 | `stat_date` / Redis `llm:usage:m:{yyyymm}` / 看板 year_month **统一上海日历日**。列类型不用改；写路径改日历，不是新表。 |
| **P1** | `departments.tenant_id` NOT NULL、**不**继承 `TenantMixin`、不在豁免清单。 | SELECT 注入只打 Mixin → 部门列表靠 service 手写 `WHERE tenant_id`。漏一处 = FR-08 成员/组织泄漏。写路径 Core UPDATE 会注入（有列未豁免），读路径不会。 | 改为 `TenantMixin`（读注入生效）。不要豁免。 |
| **P2** | `skills.name` UNIQUE 不含 `alive_flag`（025 有意排除）。 | spec 已关：无「删后再用同名重建」用户路径。任何代码路径若仍 `soft_delete(Skill)`，重同步同名 child 必撞键。 | 第三方 child **禁止软删**，只标 `sync_state=missing`。不为本波改 UNIQUE。 |
| **P2** | 采集：`content_hash` 非唯一；`spider_schedules` 无业务唯一；候选 `source` 无索引。中转：`channel_*` 无归档。Redis 键双源。 | 并发双插 / 无主计划 / 候选全表扫 / 事件只增。 | 见 §3.2 / §6；不进市场 PR1。 |
| **P2** | FR-15/FR-30 无事件表。 | 北极星四周后无法判定。审计表 `operation_logs` 无 `tenant_id`、无事件名枚举，不能冒充漏斗分母（analyst）。 | 推定新表 `product_events`（§2.5），保留 90 天。v1 不进 Redis。 |

**本轮 schema 定性：**

- Wave 0：隔离登记 + 入队/配额过滤的数据不变量 + 用量日历；**无** 市场新表。
- Wave 1：纯加法（四表 + assets 加列 + `skill_jobs.source_id` + `source_type` 放宽）+ 一行第一方 listed 回填脚本。禁止改 catalog 唯一键。禁止手写迁移 SQL。

---

## 1. 现库盘点（2026-09-07 复验）

### 1.1 Alembic 链

单头：`027`。`down_revision` 线性：

`001 → 002 → 002a → 003 → 004 → 005 → 006 → 007 → ce5210 → 8551b2c5 → a1b2c3d4 → e7a6f5a1 → 008 → … → 027`

早期混用数字 id 与 hash id，008 之后收成数字。`check-db-migrations.sh` 对含 `SM-EXEMPT` 的历史文件跳过；017/018/014 已 grandfathered。

**幽灵修订（勿当 head）：** `backend/alembic/versions/__pycache__/028_*.pyc`、`029_*.pyc`、`030_*.pyc` 与 `platform_core/models/__pycache__/api_key.pyc`、`billing.pyc` **无对应 .py**。`power-market-design.md`「头修订已到 030_*」过期。权限种子跟 **027 之后下一次 autogenerate**，不要写「023/030 之后」。

`scripts/check-db-ir.sh`：无 `*.dbml` 时静默通过。市场实现必须先落 S1 IR。

`alembic/env.py`：未开 `compare_type`；autogenerate 必须 `MYSQL_FIDELITY=1` 对人审，禁止脑补 SQL。

### 1.2 与四支柱直接相关的表

| 域 | 表 | 一行 = | 租户 | 软删 | 业务唯一键 | Alembic |
|----|----|--------|------|------|------------|---------|
| 采集 | `spider_tasks` | 一次爬取任务 | Mixin；**DDL NOT NULL / ORM 可空** | 有 | 无（日志流） | 002a→027 |
| 采集 | `spider_results` | 一条采集 item | Mixin；DDL NOT NULL / ORM 可空 | 有 | **无**（`content_hash` 非唯一） | 002+hash+012 |
| 采集 | `spider_schedules` | 一条 cron 计划 | Mixin | 有 | **无** | 003 |
| 采集 | `spider_definitions` | 一个可调度爬虫名 | Mixin | 有 | `(tenant_id, name, alive_flag)` | 005→025 |
| 采集 | `spider_task_templates` | 一条可复用任务配置 | Mixin | 有 | `(tenant_id, name, alive_flag)` | e7a6→025 |
| 采集 | `ai_plans` | 一次 URL→flow 规划 | Mixin | 有 | 无 | 009 |
| SaaS | `tenants` | 一个隔离单元 | 自身 | 有 | `slug` 不含 alive（025：注销不复用） | 017 |
| SaaS | `users` | 一个登录主体 | Mixin **覆盖 NOT NULL** | 有 | `(tenant_id, username)`；**email 全局 unique** | 001→024 |
| SaaS | `departments` | 租户内一个部门 | 列 NOT NULL，**非 Mixin** | 有 | `(tenant_id, name, alive_flag)` | 022→025 |
| SaaS | `roles` / `permissions` / `menus` | 平台角色/权限码/菜单树 | 无列（平台目录） | 无 | `role_key` / `code` | 022–023 |
| SaaS | `llm_providers` | 一个供应商渠道 | Mixin 可空（平台行） | 有 | `(tenant_id, name, alive_flag)` | 010→025 |
| SaaS | `llm_token_usage` | 租户×维×模型×日 用量 | Mixin | 无 | `(tenant_id, provider_name, model, stat_date)` | 013→017 |
| 中转 | `channel_events` | 一次渠道启停审计 | 无列 | 无 | 无（事件流） | 011 |
| 中转 | `channel_probe_results` | 一次真伪探针 | 无列 | 无 | 无；`(channel_id, created_at)` / `batch_id` | 011 |
| 市场 | `skills` | 一个技能治理行 | 列恒 NULL | 有 | `name` **全局、无 alive_flag** | 014 |
| 市场 | `skill_reviews` / `skill_jobs` | 一次评分 / 一次作业 | 无 | 无 | 无 | 014 |
| 市场 | `capability_assets` | 四类目录一行 | **列恒 NULL，非 Mixin** | 有 | `(asset_type, name, alive_flag)` | 018→025 |
| 市场 | `capability_plugins/experts/teams` | 类型化细节 1:1 | 无 tenant 列 | 无 | DDL `uq_*_asset(asset_id)`；**ORM 未声明 UniqueConstraint**，create_all 会丢这把键 | 018 |

细节表 `capability_plugins.license` / `health_status` / `verify_detail` 已存在。设计要把 **license 拷到资产行**（公开闸四类共用）；插件细节列 **保留**（快照+引用并存）。

横切表（020–021）：`tags` / `taggings` / `attachments` / `notifications` / `resource_versions` / `workflow_*` / `archive_records` / `i18n_*` / `system_caches`。本程序 Wave 0/1 **不扩**。`system_caches` 是 DB 缓存（`expires_at` NULL=永不过期），与 Redis 并存；市场列表 v1 **不**走这张表。

### 1.3 豁免清单 vs 列事实（P0）

`backend/app/tenant_isolation.py` 今日登记：

`tenants`, `system_configs`, `channel_events`, `channel_probe_results`, `operation_logs`, **`skills`**, `skill_reviews`, `skill_jobs`, `llm_provider_models`。

`PLATFORM_SHARED_READ_TABLES` = `llm_providers`。

隔离机制（`platform_core/tenant_context.py`）：

| 路径 | 条件 | 后果 |
|------|------|------|
| SELECT | 仅 `TenantMixin` 子类 + `with_loader_criteria` | 非 Mixin 即使有 `tenant_id` 列也 **不过滤** |
| UPDATE/DELETE（`session.execute`） | 表有 `tenant_id` 列且 **未** 豁免 → `WHERE tenant_id = ?` | NULL 平台行 0 命中 |
| UoW `flush` 脏对象 | **不**经过 `do_orm_execute` | setattr+flush **可能**更新成功（与 repository 路径分叉） |
| before_flush 断言 | 仅 `TenantMixin` 新行 | 非 Mixin 写入不断言 |

| 表 | 有 `tenant_id` | TenantMixin | 已豁免 | 租户态行为 |
|----|----------------|-------------|--------|------------|
| `skills` | 是，恒 NULL | 否 | **是**（功能必需） | Core 写不注入 |
| `capability_assets` | 是，恒 NULL | **否** | **否** | Core UPDATE 0 行；SELECT 不过滤（目录对租户可见，符合平台目录） |
| `capability_plugins/experts/teams` | 否 | 否 | 否（防御性未登记） | 无列，注入跳过 |
| `departments` | NOT NULL | **否** | 否 | 写注入（碰巧正确）；**读不注入** |
| 设计新增 sources/components/aliases | 无或恒 NULL | 否 | **必须登记** | 同 assets |
| 设计新增 `capability_installs` | NOT NULL | **必须 Mixin** | **禁止豁免** | 行级隔离 |

R13 只保证：组装点把清单注册进去、`tenant_context.py` 不含表名字面量。它 **不** 扫描「有 `tenant_id` 列却既非 Mixin 又不在清单」。

### 1.4 时区 / 主键 / 类型（本仓事实，不按教科书改存量）

- 主键普遍 `Integer` AUTO_INCREMENT，不是 BIGINT。新表跟仓内惯例。
- `DATETIME` 与 `DateTime(timezone=True)` **混用**：`SoftDeleteMixin.deleted_at` 带 tz，`capability_assets.created_at` 不带。新市场表 **跟 assets 走 naive DATETIME + 文档约定 UTC 存储**；**业务日历**（用量、WACT）按 spec 用 **Asia/Shanghai 日**，在写路径换算，不把列改成 TIMESTAMP。
- 枚举一律 VARCHAR + 应用校验（027 已放宽 `spider_tasks.status`）。`listing_state` / `source.type` / `host` 同此，**禁止** MySQL ENUM。
- 金额：本特征无钱。配额在 `tenants.quota` JSON。订阅 **不占** 三类配额（spec 9.2 冻结）。
- `users.email` 全局 unique：跨租户不能复用邮箱（017 已决）。保持。

### 1.5 ORM ↔ 迁移漂移（create_all 测试 vs 真库）

Mixin 已承认：026 删掉的 `tenant_id` 单列索引，`create_all` 仍会建（`index=True`）。基线对拍口径=列集。

额外漂移（本轮复验）：

| 对象 | 迁移链 | ORM / create_all |
|------|--------|------------------|
| 9 张业务表 `tenant_id` | 017 NOT NULL | Mixin 可空 |
| `capability_plugins.asset_id` 等 | UNIQUE + 又建 `ix_*_asset_id`（冗余） | 仅 `index=True`，无 UniqueConstraint |
| `spider_results (spider_name, created_at)` | 012 名 `ix_spider_results_spider_created` | ORM 名 `ix_spider_results_name_created` |
| `ix_skills_name` | 014 UNIQUE `uq_skills_name` **另**建单列索引 | `unique=True, index=True` 双份 |

S3 对人审时盯这些，避免 autogenerate 再「补」一份真库已有的键。

---

## 2. 目标态 vs 现库（对齐冻结 spec）

### 2.1 粒度（一行 = ___）

| 实体 | 一行 = | 判定 |
|------|--------|------|
| `capability_sources` | 一条已登记的外部树（稳定 `name` + `type` + `uri`） | 新实体。plugin-updater **不是**源。 |
| `capability_assets` | 四类目录中的一个 catalog 身份（类型内全局 `name`） | **已有**。扩展列，不改粒度和唯一键。 |
| `capability_plugins/experts/teams` / `skills` | 类型化细节 | **已有**。不新建 kimi 第五类。 |
| `capability_components` | 插件资产 → 子资产的一条边（bundled_skill / bundled_expert） | 新实体。 |
| `capability_installs` | 某租户把某资产订到某宿主的一次订阅 | 新实体。`enabled`/`trusted` 是安装属性。 |
| `capability_aliases` | 一条人工 vanity slug → 一个资产 | 新实体。同步不自动建。 |
| `listing_state` | 资产的产品上架态 | **字段**，禁止 `capability_listings` 表。 |
| `status` | 治理/质量生命周期 | **已有字段**。与 listing 分列（D6 / FR-18）。 |
| `product_events` | 一次产品埋点（FR-15/30） | **推定新实体**，Wave 0 就要能按时间查。 |

**不是实体**：SOURCE.yaml 指针、host_compat（JSON 列）、alias_origin_refs（JSON）、UNLISTABLE_PACKAGES（配置）、verify 结果（已在 `verify_detail`）。

### 2.2 列缺口（只加不改唯一键）— Wave 1

现 `CapabilityAsset` **没有**：`listing_state` / `listed_at` / `source_id` / `origin_ref` / `origin_local_name` / `origin_plugin_name` / `host_compat` / `alias_origin_refs` / `license` / `public_license_override` / `writable`。

现 `SkillJob` **没有**：`source_id`。`job_type VARCHAR(16)` 装得下 `src_sync` / `scan_plugins` / `promote`，不必 widen。

现 `source_type`：P1 列宽。

现 `capability_plugins`：**不必加列**。同步把 `content_hash` 写到 **资产行**。`license` 双写到资产行。

### 2.3 快照 vs 引用（「当时 / 现在」）

| 值 | 当时 / 现在 | 落点 |
|----|-------------|------|
| 目录 `name` / 公开 URL | 现在 | 引用；唯一键不改 |
| `listing_state` | 现在 | 资产列；同步 **不得**覆盖 |
| 安装时的标题/版本 | spec 未要求历史小票 | **引用** `asset_id`；商店 JOIN 当前 title |
| 许可 | 公开闸要「现在能不能看」 | 资产行 `license` 为同步拷贝；override 是现在 |
| `content_hash` | 当时那棵树 | 资产列 |
| 插件 manifest | 当时原文 | `capability_plugins.manifest` JSON 快照 |
| `skills.file_path` | 合成指针，不是解析输入 | 满足 NOT NULL；读文件走 `source_id+origin_ref` |
| 下架后的安装行 | spec FR-29：**保留引用** | 不拷贝 listing；unlist 后「我的安装」仍在，标已下架 |

### 2.4 状态机（给 qa；与 spec §3.1 对齐）

```
listing_state: unlisted | listed | coming_soon
  默认同步插入 = unlisted
  三态可互转（UNLISTABLE_PACKAGES 除外）
  同步不得改 listing
  listed + status=blacklist → 拒绝该组合或收回 unlisted；公开当 404

status（已有，不改值集）:
  experimental/testing/stable/recommended/deprecated/blacklist
  公开允许：stable | recommended

capability_installs:
  无记录 ──订阅成功──► 存活行（enabled=1, trusted=0）
  关启用 / 开信任（需确认）不改资产行
  卸载 = 软删（可再订）
  预告/未上架/未过闸：保持无记录
  unlist 后：行保留，不可新订
  blacklist 后：行只读可卸，不可改信任/启用

skill_jobs.status: running/done/failed
sync_state: ok/hash_changed/missing/parse_error
  missing ≠ 删除（spec 答 dba Q1）
```

### 2.5 `product_events`（推定，Wave 0 FR-15 / Wave 1 FR-30）

无 production 埋点表。`operation_logs` 是操作审计（actor + action + target），无事件名、无匿名访客、无 `tenant_id`，analyst 禁止当漏斗分母。

| 字段意图 | 建议 |
|----------|------|
| 一行 | 一次已发生的产品事件 |
| 软删 | **不要**（审计/事件流） |
| `event_name` | VARCHAR(64)，应用枚举（`official_page_viewed` 等） |
| `occurred_at` | DATETIME，**写入即上海墙钟或明确 UTC 并在查询换算**；与 FR-16 同一规则 |
| `tenant_id` | 可空（匿名页无企业） |
| `actor_user_id` | 可空 |
| `props` | JSON，非查询列（cta、format、result_count、host、reason） |
| 索引（推定 Top-N） | `(event_name, occurred_at)`；`(tenant_id, occurred_at)`（tenant 可空，MySQL NULL 不挡） |
| TTL | 表内保留 **90 天**；超期归档到 `archive_records` 或删。无 TTL 会把主库变成日志库 |
| 失败 | 写失败不得挡主路径（spec）；因此这张表 **不是** 配额闸的依赖 |

保留策略与是否改用外部查询面 → 开放问题 Q-EVENTS（不阻塞「先有一张可查表」的默认）。

---

## 3. 访问模式（全部 **推定** — 无 production slow_query）

来源：设计 Q1–Q12、spec FR、repository 调用点。上线后用 `performance_schema` 复盘。**Top-N 之外不建索引。**

现有 EXPLAIN 证据（`test_db_behavior_loop.py`，需 `MYSQL_FIDELITY=1`）：

- `spider_results WHERE spider_name=? ORDER BY created_at DESC` → 断言 `type != ALL`（012 复合）
- `capability_assets WHERE asset_type=? AND name=?` → 断言走 UNIQUE

**没有** 租户列表、配额 SUM、候选 `source=`、市场 listing 过滤的 EXPLAIN。S4 真库补。

### 3.1 Power Market（设计已给，DBA 复核 ESR）

| ID | 场景 | 过滤 | 排序 | 返回 | 频次 | P95 | 行数 | 索引 |
|----|------|------|------|------|------|-----|------|------|
| Q1 | 管理目录 type+listing+status 翻页 | eq: asset_type, listing_state, status | updated_at DESC | 目录列 | 高 | 100ms | 20 | `(asset_type, listing_state, status, updated_at)` |
| Q1b | 管理按源筛 | eq: source_id | — | 同 | 中 | 100ms | 50 | **单列** `source_id` |
| Q2 | 公开市场 listing IN + 发布态 + type + category | eq/IN: listing_state, status, asset_type, category | 分页 | 白名单 | 高 | 100ms | 20 | `(listing_state, status, asset_type, category)`。`JSON_CONTAINS(host_compat)` **不建函数索引** |
| Q3 | 详情 (type, name) | 已有唯一键 | — | 1 | 高 | 50ms | 1 | 不新建 |
| Q4 | `q` 搜 name/title/origin_local_name | LIKE；等值 origin_local_name | — | 20 | 中 | 150ms | 20 | 仅 `(origin_local_name)`。不为 description/title 建 BTree（`%q%`；300 行可扫） |
| Q5 | 同步 upsert (source_id, origin_ref) | 等值 | — | 1 | 中 | 50ms | 1 | UNIQUE 即索引 |
| Q6 | 插件组件 parent→children | eq: parent_asset_id | — | ~80 | 中 | 50ms | <100 | UNIQUE(parent, child) 最左前缀已覆盖 → **不重复建 ix_parent** |
| Q7 | 子反查父 | eq: child_asset_id | — | 1–2 | 低 | — | 1 | `(child_asset_id)` |
| Q8 | 源按 name | UNIQUE(name, alive_flag) | — | 1 | 低 | — | 1 | UNIQUE |
| Q9 | 某源最近 jobs | eq: source_id | started_at DESC | 20 | 低 | — | 20 | `(source_id)` |
| Q10 | 租户我的安装 | eq: tenant_id, 可选 host | updated_at DESC | 20 | 高 | 100ms | 20 | `(tenant_id, host, updated_at)` |
| Q11 | 安装 upsert | UNIQUE(tenant_id, asset_id, host, alive_flag) | — | 1 | 高 | 50ms | 1 | UNIQUE |
| Q12 | 公开 vanity slug | UNIQUE(slug, alive_flag) | — | 1 | 高 | 50ms | 1 | UNIQUE；另 `(asset_id)` 管理端列 alias |
| E1 | 埋点按事件+时间 | eq event_name + range occurred_at | occurred_at | 页 | 中 | 200ms | 50 | `(event_name, occurred_at)` 推定 |
| E2 | 埋点按租户时间 | eq tenant_id + range occurred_at | occurred_at | 页 | 中 | 200ms | 50 | `(tenant_id, occurred_at)` 推定 |

**评估不建：**

| 候选 | 理由 |
|------|------|
| `(status)` / `(listing_state)` 单列 | 基数 ≤ 6；现 `ix_capability_assets_status` 已是低基数，**新列不要再单列**；旧单列不为本波 drop（026 未纳入，行数小） |
| `host_compat` 函数索引 | 300 行；过万再议 |
| `alias_origin_refs` 多值索引 | 次级 upsert 同源内扫描可接受 |
| `description` 全文 | LIKE `%q%`；过万再 FULLTEXT |
| `ix_components_parent` 若已有 UNIQUE(parent, child) | 最左前缀重复 |
| 给 `skills` 加 `(source_type)` | 低频 |
| 任务默认列表 `(tenant_id, id)` | 026 用 `(tenant_id, status, priority)` 最左 `tenant_id` 承接；ORDER BY id DESC 可能 filesort。现体量评估不建，等慢查询 |

### 3.2 智能采集 — 现模式缺口（推定）

| ID | 调用点 | 过滤 | 现索引 | 缺口 |
|----|--------|------|--------|------|
| C1 | `list_by_task` / 导出游标 | eq task_id，id 游标 | `task_id` FK 索引 | 无 |
| C2 | 数据中心 `query_by_spider` | 可选 spider_name + created_at 范围 + ORDER created_at DESC | `(spider_name, created_at)`；`created_at` 单列（012） | 租户注入后理想 `(tenant_id, spider_name, created_at)`。Mixin 保留了 `tenant_id` 单列。百万行再升。**本轮不建。** |
| C3 | keyword `LIKE %kw%` | 无索引可用 | 应用层 200 行窗口 | 正确：不建 |
| C4 | `find_by_content_hash(hash, tenant_id)` | eq hash + tenant | **仅** `content_hash` 单列 | 缺 `(tenant_id, content_hash)`；非 UNIQUE → 并发双插。consumer **第二条路径**（约 L772）调用 **不传 tenant_id** → 跨租户去重。 |
| C5 | 候选 `source='marketplace'` 全表 id DESC | eq source | `source` 无索引 | 千到万可扫；过万补 `(source, id)`。Wave 0 先靠过滤正确，不建。 |
| C6 | 调度 `list_due` enabled + next_run_at<=now | next_run_at 范围 | `next_run_at` 单列 | 够用 |
| C7 | `find_by_spider(name)` | eq name | `spider_name` 单列 | **无唯一** → 同租户可插两条计划 |
| C8 | 配额 COUNT results WHERE tenant_id | eq tenant_id | tenant_id 单列 | Redis 60s 缓存；**必须加 source 排除**（P0） |
| C9 | 任务列表 tenant + ORDER id DESC | eq tenant（注入） | `(tenant_id, status, priority)` | 见上，评估不建 |
| C10 | 月度 token SUM(tenant, month) | eq tenant + stat_date 范围 | UNIQUE 最左 tenant_id，第四列才是 stat_date | `LIKE 'YYYY-MM-%'` 无法用日期范围。改为 `stat_date >= 月初 AND stat_date < 下月初` 后，小表用 tenant 前缀可接受。**不建** `(tenant_id, stat_date)` 除非慢查询 |

### 3.3 SaaS / 中转站

| ID | 场景 | 现索引 | 备注 |
|----|------|--------|------|
| S1 | 登录 `(tenant_id, username)` | UNIQUE | email 另全局 unique |
| S2 | 配额 active tasks | `(tenant_id, status, priority)` | 026 ESR 已对齐 |
| S3 | 用量日聚合 upsert | `uq_llm_usage_dim` | DB 侧租户正确；Redis 月度 field 不正确（§6） |
| S4 | 部门列表 tenant | UNIQUE 最左 tenant_id | 读路径缺 Mixin（P1） |
| R1 | 渠道事件按 channel+时间 | `(channel_id, created_at)` | 无归档 → 行只增 |
| R2 | 探针按 batch / channel | `batch_id`；`(channel_id, created_at)` | 同 R1 |

---

## 4. 唯一键碰撞（Power Market 身份）

设计 D3 / spec FR-19/27：**保持** `(asset_type, name, alive_flag)` 与 `skills.name` 全局唯一，bundled 用 `{plugin}__{local}`。改成 `(source, name)` 是破坏性 UNIQUE + 全部 URL。

### 4.1 会撞的场景（同步必须 parse_error / 折叠，不能静默改名）

| 场景 | 撞哪把键 | 设计对策 | DBA 风险 |
|------|----------|----------|----------|
| 跨插件 51 个短名 | `skills.name` + `uq_asset_type_name_alive` | 前缀 `{plugin}__{local}` | 前缀算法必须稳定 |
| 插件内扁平+分类同 hash | 同上 | D3b 折叠一行，`alias_origin_refs` 记路径 | JSON 不含则次级 upsert 插第二行 |
| 同插件同名不同 hash | 同上 | `{plugin}__{seg}__{name}` | 路径段规则冻结进适配器测试 |
| 两源同一插件目录名 | catalog `name` 全局 | D12：第二条 `parse_error` | 源 `name` 与插件目录名配置层错开 |
| git `origin_ref="."` vs monorepo 目录 | `(source_id, origin_ref, alive_flag)` | 不同字符串 | 禁止混用 |
| 子资产 `origin_ref` 写成插件短名 | `(source_id, origin_ref)` | D3c 完整相对路径 | 漏了会插件行与 child 互撞 |
| `source_id` NULL 的第一方 | UNIQUE 含 NULL | MySQL NULL 不判重 | 正确；禁止「NULL 永远第一方」的代码假设 |
| vanity slug = 存活 catalog `name` | 跨表 | 应用 409 | 不能用单表 UNIQUE。事务内锁 name 再插 alias |
| 软删技能后重同步同名 | `skills.name` 仍占坑 | spec：不提供该用户路径 | 实现禁止 soft_delete child |
| `dev-team` 与 `mattpocock-skills` | 前缀不同 | 不自动合并 | `similar_to` 是 JSON，非唯一 |

### 4.2 现库其它唯一键债（本特征可不同时改）

| 表 | 问题 | 建议 |
|----|------|------|
| `users.email` 全局 unique | 同人多租户无法复用邮箱 | 保持（017） |
| `users` / `tenants.slug` 无 alive_flag | 025 有意：占坑、slug 不复用 | 保持 |
| `tags (tenant_id, name)` | 无软删；全局标签 `tenant_id` NULL 在 MySQL 不判重 | 保持 |
| `workflow_definitions (tenant_id, name)` | 无软删 | 保持 |
| `spider_schedules` 无业务唯一 | 同租户同爬虫可多计划 | 采集域；PM 确认「一爬虫一计划」再加 UNIQUE（先查重复） |
| `spider_results.content_hash` 非唯一 | 并发双插 | C4；加 UNIQUE 前必须查重复（破坏性） |
| `llm_providers.is_active` 「全表至多一行」 | 无 UNIQUE | 应用层；多租户后语义应是 **每租户** 至多一行激活——现注释仍写「全表」。问 architect（Q8） |

### 4.3 新表唯一键（落地必须带 alive 的）

与 025 同款：`alive_flag` 生成列 `CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END`。

| 表 | UNIQUE | 软删 |
|----|--------|------|
| `capability_sources` | `(name, alive_flag)` | 要（删后可重建同名源） |
| `capability_assets` | 保持 `(asset_type, name, alive_flag)`；**新增** `(source_id, origin_ref, alive_flag)` | 已有 |
| `capability_components` | `(parent_asset_id, child_asset_id)` | **不要**软删（边表；列表 JOIN 过滤 missing） |
| `capability_installs` | `(tenant_id, asset_id, host, alive_flag)` | 要（卸载后可再订） |
| `capability_aliases` | `(slug, alive_flag)` | 要 |
| `product_events` | 无业务唯一（事件流） | 不要 |

`components.role` 不进唯一键：同一父子只允许一条边。

---

## 5. Expand-contract 风险

### 5.1 Wave 0（无市场新表）

| 变更 | 类型 | 做法 |
|------|------|------|
| 豁免清单 + Department→Mixin | 行为/ORM，不是 DDL | 与权限收口同发 |
| 入队 `tenant_id` 必填 | 数据不变量 | ORM 与 DDL 对齐 NOT NULL 是 **收紧** → 若改 ORM 不改库则只是模型；若有真库 NULL 行，先 backfill 再收紧（017 已收紧，真库不应有 NULL；SQLite 测试库会有） |
| 配额/列表排除 marketplace | 查询谓词 | 无 DDL |
| 用量上海日历 | 写路径 | 无 DDL |
| `product_events` 新表 | 纯加法 | 单迁移 up/down；autogenerate |

### 5.2 Wave 1 纯加法（单迁移，up/down，autogenerate）

- 四张新表 + FK + UNIQUE + 访问模式索引
- `capability_assets` 新列：`listing_state` **必须** `server_default='unlisted'`（SM-5 可能报警 → 注释写明 INSTANT / `SM-EXEMPT` 理由，不要拆成先空后收紧除非 lint 强制）
- `writable` default 1、`public_license_override` default 0
- 可空：`listed_at` / `source_id` / `origin_*` / `host_compat` / `alias_origin_refs` / `license` / `skill_jobs.source_id`
- 新 UNIQUE `(source_id, origin_ref, alive_flag)`：存量 `source_id` 全 NULL → MySQL 不判重。仍属「加 UNIQUE」，S3 前跑重复探测（非 NULL 重复应 0 组）
- `source_type` VARCHAR(16)→(32)：扩大，同文件可做，**不要**同文件改列名

### 5.3 不要做的破坏性变更

| 变更 | 为何禁止（本轮） |
|------|------------------|
| 改 `uq_asset_type_name_alive` 为 `(source, name, …)` | 破坏性 UNIQUE + 全部 URL |
| 改 `skills.name` 为含 alive / 非全局 | spec 已关重建路径；改键仍破坏 URL |
| 删 `capability_plugins.license` | 删列 = contract；双写即可 |
| 把 `skills.file_path` 改可空 | 设计 D15 明确不改 |
| 把 `job_type` 从 16 放宽 | 不需要 |
| MySQL ENUM for listing_state | 改值要 DDL |
| PR1 回填里 UPDATE 第三方 listing | 同步永不 auto-list |
| 把候选迁出 `spider_results` | 产品只要语义隔离；迁表是 Q-CAND，非本波 |

### 5.4 回填（DDL 与数据分离）

大回填不进迁移文件。第一方 listed 是配置表量级：

1. autogenerate **只 DDL**
2. 独立幂等脚本：第一方（`source_id IS NULL` 且 `asset_type='skill'` 且 `source_type='self_built'`）且 `status IN ('stable','recommended')` → `listing_state='listed'`，`writable=1`（FR-31）
3. 校验：`SELECT COUNT(*) FROM capability_assets WHERE listing_state='listed' AND source_id IS NOT NULL` → 0（PR1 不得 attach 源）

`sdlc-workflow` 保持 `self_built` + `writable=1` 直到第一次 `src_sync` attach（Q2 窗口期）。

### 5.5 权限码种子

`btn:market:*` / `btn:plugin:verify` / `btn:plugin:enable` 是 **数据**。autogenerate 之后的种子，不要手搓 INSERT DDL。角色 `admin` JSON 追加市场码——这是 022 种子的 **后续数据迁移**，expand：新码 INSERT permissions + 更新 roles.permissions JSON（JSON 追加可逆：downgrade 删码）。

### 5.6 行为验证环（S4，给 qa）

真库 `MYSQL_FIDELITY=1`：

- `upgrade → downgrade → upgrade` 退出码 0
- EXPLAIN Q1 / Q1b / Q2 / Q3 / Q5 / Q6 / Q10 / Q11 / Q12 / E1：`type != ALL`（300 行时 ALL 也可能「够快」，仍要证明走了键）
- 约束注入：重复存活 `(asset_type,name)`、重复非空 `(source_id, origin_ref)`、重复安装、重复 slug、alias=存活 name（应用 409）、installs 缺 tenant_id、`listing_state` 空串
- 租户态 `update(CapabilityAsset)` 豁免前后 rowcount（0 → 1）
- 配额 COUNT 含/不含 marketplace 行

容量：无需 gh-ost。`spider_results` 不在本 DDL 集合。

---

## 6. Redis 键

治理：每个键 **name + TTL + 失效路径**。唯一契约源 `platform_core/queues.py`。

### 6.1 已声明 vs 实况

| 键模式 | 类型 | TTL | 失效 | 问题 |
|--------|------|-----|------|------|
| `spider:task_queue:{high\|normal\|low}` | List | 无（队列） | blpop | 正当无 TTL |
| `spider:item_queue` | List | 无 | blpop | 正当 |
| `spider:item_dead` | List | **明确无 TTL** | 人工 | 正当；要容量告警。常量 **未进** `__all__`（调用方仍直接 import，属契约卫生） |
| `spider:active_tasks:{spider}` | Set | 86400 | 任务结束删成员 | 有 |
| `spider:task_log_offset:{id}` | String | 写入时 `ex=ACTIVE_TASK_TTL` | 过期 | 有 |
| `spider:task_results:{id}` | List | 默认 7 天 | 过期 | 有 |
| `spider:scheduler:lock` | String | lock TTL | Lua 释放 | 有 |
| `spider:task_control:{id}` | String | 停爬后应 EXPIRE | resume DELETE | 注释未写 TTL；防永生 |
| `spider:worker:{id}` | Hash | 心跳 ~30s | 过期=离线 | 有 |
| `spider:proxy:scores` / `stats` | Hash | **无** | 覆盖写 | 永生 hash；代理数少可接受，须写容量 + `maxmemory-policy` |
| `skill:score_queue` | List | 无 | blpop | 正当 |
| `skill:scorer:lock` / `skill:scan:lock` | String | lock TTL | Lua | 有 |
| `skill:public:rl:{ip}` | String | 60s | 窗口过期 | **公开面 INCR 与 EXPIRE 非原子**（`public_skills.py` L81–83）；登录限流已 pipeline |
| `login_fail:` / `register_fail:` / `tenant:signup:rl:` | String | 策略窗口 | 过期 | 走 rate_limiter；signup fail-closed |
| `quota:count:{k}` | String | 60s | 过期 | `quota_service` **重写字面量** `_QUOTA_COUNT_PREFIX`，未 import 常量 |
| `llm:cooldown:` | String | 冷却窗 | 过期 | 有 |
| `llm:usage:d:{yyyymmdd}` | Hash | 30 天 | 过期 | 服务内重写前缀；field 含 tenant |
| `llm:usage:m:{yyyymm}` | Hash | 93 天 | 过期 | **写入 field=`{dim}\|total` 无 tenant**；读 `{t}\|dim\|total` 再 fallback → 串租户 |
| `llm:usage:flush:lock` | String | lock | Lua | 服务内重写 |
| `newapi:channel:cfg:{id}` | Hash | **无** | `clear_config` DELETE | 永生；`newapi_api.py` 再定义一份 |
| `newapi:scheduler:lock` / `probe:lock` | String | 配置 TTL | Lua | 双定义 |
| `newapi:scheduler:state`（queues 单键） vs `newapi:scheduler:state:{id}`（服务前缀） | String | ? | 调度器删 | **契约名与实键不一致**；死常量 |
| `llm:patrol:lock` | String | lock | Lua | 有 |

### 6.2 不在 queues.py 的键

| 键 | 来源 | TTL | 风险 |
|----|------|-----|------|
| `{spider}:start_urls` | scrapy-redis | 无 | 正当队列；应在 queues **文档化** |
| `{spider}:dupefilter` / `{spider}:requests` | `SCHEDULER_PERSIST=True` | **无、且持久** | 指纹/请求队列只增；多爬虫 × 长期运行 = Redis 内存主凶 |
| `{spider}:items` | RedisPipeline（已禁用） | — | 保持禁用 |
| `PROXY_REDIS_KEY` | 配置 | ? | 第三套代理键，与 `spider:proxy:*` 并行 |

### 6.3 Power Market 需要的新键（推定）

| 键 | 类型 | TTL | 失效 | 理由 |
|----|------|-----|------|------|
| `market:src_sync:{source_name}` | 锁 String | ≥ 最长同步 + 续期 | Lua 释放 / TTL 兑底 | 防并发 POST sync 双 upsert。仅靠 `skill_jobs.status=running` 有竞态。 |
| 公开市场限流 | 复用 `skill:public:rl:` | 60s | 过期 | **不要**再发明 `market:public:rl:`；修原子 EXPIRE |
| 目录列表缓存 | — | — | — | **v1 不建**（300 行 SQL 即可） |
| 埋点缓冲 | — | — | — | **v1 不建**；直接写 `product_events`，失败丢事件不挡主路径 |

不要把 `SOURCE.yaml` / clone 放进 Redis。

### 6.4 建议（非市场 PR1 阻塞，Wave 0 配额相关是阻塞）

1. 所有业务键从 `queues.py` import，删除 `_QUOTA_COUNT_PREFIX`、`_DAILY_KEY_PREFIX`、`NEWAPI_*` 重复；`DEAD_ITEM_QUEUE` 补进 `__all__`。
2. 月度用量 field expand-contract（P1，**FR-10 阻塞**）。
3. `SCHEDULER_PERSIST`：产品决策（按任务清空 vs 按天 EXPIRE vs 永生+监控）。Q9。
4. `newapi:channel:cfg:*`：补长 TTL（如 30d）作兜底，或文档「永不过期 + 渠道数上限」。
5. 公开 INCR+EXPIRE 改 pipeline。

---

## 7. 四支柱其余域

### 7.1 智能采集（Wave 0/4）

- 结果表 `content`/`title` 为 TEXT 主表宽行；过百万应拆正文侧表。本特征不拆。
- 候选入站 `spider_results.source='marketplace'`，不改爬虫写主库（R 红线）。转正 `source_type=marketplace_crawled` 依赖列宽。
- `daily_result_counts` 无 tenant 过滤、无 source 排除、按 `func.date(created_at)`。平台态看全库；租户态靠 Mixin 注入但仍会计入候选。FR-16 + FR-11 都要改这条聚合（查询谓词，非新索引）。
- `count_by_status` 无 tenant：平台看板 vs 企业看板必须标「平台合计 / 本企业」（FR-16.3），查询侧分流，不是两张表。

### 7.2 SaaS（Wave 0/2）

- 隔离模型正确：共享表 + `tenant_id` 最左。026 已删无模式索引。
- **平台目录 vs 租户安装** 是本特征隔离主轴：目录 NULL + 豁免；安装 NOT NULL + Mixin。不要给 assets 加「租户私有资产」。
- 配额三类 JSON。安装数不占配额（冻结）。
- `roles` 是平台三角色目录，不是每租户一份角色表。`users.tenant_role` / `role` 两列并存（owner/admin/operator/viewer vs admin/operator/viewer）。本波不合并列（破坏性 + 双写窗口），记作命名债。
- Wave 2 支付未决（Q-BILL）：**不要**提前建 billing 表。pycache 里的 `billing.py` / `029_*` 是撤回痕迹，禁止复活进本程序。

### 7.3 中转站（Wave 0 权限 / Wave 3 产品）

- `channel_id` 外部主键、无 FK：正确。
- 事件/探针只增不归档：R1/R2 已有时间复合索引。给 sre 的保留策略：按月归档或分区，**不是**本 PR。
- Redis 调度状态键名分裂见 §6。修命名比加表优先。
- FR-61：探针伪装不改渠道启用态——渠道启用真相在 **new-api 库**，本库只记 `channel_events` / `channel_probe_results`。不要在本库加 `channels` 镜像表。

---

## 8. 推荐落地顺序（给 architect / backend，无 SQL）

**Wave 0（冻结 FR-06…16）**

1. 隔离登记：豁免 assets（及已有细节表防御性登记）；Department 改 Mixin；R13 仍不够，S4 加「有 tenant_id 列 ⇒ Mixin 或豁免」的检查更好，但那是闸门，不是本文件。
2. 入队/回流：任务行必须带租户；结果配额与数据中心排除 marketplace。
3. Redis 月度 field 双写切读（FR-10）。
4. 用量/看板日历改为上海日（FR-16）。
5. 若做埋点：`product_events` 走 ADR-0002（S1 小 DBML → autogenerate）。公开限流修原子性。

**Wave 1（冻结 FR-17…31）**

1. S1 `capability-market.dbml`：新四表 + assets 新列 + skill_jobs.source_id + source_type(32)。Q6 去掉重复 parent 索引。过 `check-db-ir`。
2. S2 `/new-model` 扩 `capability.py`；Pydantic 只加 schema。
3. 隔离登记 sources/components/aliases；installs 不豁免。与 DDL 同发。
4. S3 `MYSQL_FIDELITY=1 uv run alembic revision --autogenerate -m "power_market_sources_listing"`。人工审查：无 drop、无改旧 UNIQUE、NOT NULL 必有 server_default。权限种子另步。
5. 回填脚本第一方 listed（§5.4）。
6. S4 EXPLAIN + up/down/up。
7. Redis：`market:src_sync:` 只加 `queues.py`；公开限流复用。

**拒绝**：诊断或实现阶段手写 `op.execute("""ALTER…""")` 业务 DDL。

---

## 9. 开放问题

spec 已冻结、不再问：

| 原 ID | 冻结答案 | 对 schema 的含义 |
|-------|----------|------------------|
| Q1 | 无「删除再建同名」；源消失=missing，不自动下架 | **不**给 `skills` 补 alive_flag；禁止 soft_delete child |
| Q5 | unlist 后安装保留、不可新订；黑名单只读可卸 | installs **不** ON DELETE CASCADE 软删；无级联 UNIQUE 故事 |
| 订阅配额 | 不占三类 | 不要 COUNT installs 进 result_storage |
| 时区 | Asia/Shanghai 业务日 | 用量/事件日历，不是列类型变更 |

仍开放：

| ID | 问题 | 阻塞 | 需要谁 |
|----|------|------|--------|
| Q2 | PR1 结束到第一次 src_sync，存量 `sdlc-workflow` 保持 `writable=1` 是否可接受（治理写回可能打到本机树）？ | 否（窗口期） | pm |
| Q3 | alias slug 与存活 `capability_assets.name` 冲突：仅事务内应用 409，还是要 `reserved_slugs` 表？DBA **不要第三张表**。 | 否 | pm |
| Q4 | child `sync_state=missing` 时 `capability_components` 边保留还是删？DBA **保留**（同步不删行；列表 JOIN 过滤）。spec 的 missing≠删除支持保留。 | 否 | 默认保留；pm 可一票否决 |
| Q6 | `origin_ref VARCHAR(256)` 是否覆盖最深 SKILL 路径？现盘点子路径远小于 256。若适配器允许任意深度，改为 512 与 `file_path` 对齐。 | 否 | architect（适配器） |
| Q7 | `spider_results` 去重：同一 `(tenant_id, content_hash)` 留谁？本轮是否加 UNIQUE？ | 否 | pm |
| Q8 | `llm_providers.is_active` 语义是「全平台一行」还是「每租户一行」？注释与多租户矛盾。 | 否 | architect |
| Q9 | scrapy-redis `SCHEDULER_PERSIST` 永生 dupefilter：接受监控，还是按任务/按天过期？ | 否 | pm + data-collector |
| Q10 | 平台态 `daily_result_counts` 是否应跨租户？候选是否计入平台合计？ | 否 | pm（口径）；实现必须与 FR-16.3 标签一致 |
| Q11 | 是否需要 `src_sync` Redis 锁，或接受 jobs 行 running 检查的竞态窗口？DBA **要锁**。 | 否 | architect |
| Q12 | `source_type` 放宽到 32 是否纳入市场同一 DDL？DBA **纳入**，否则转正无法落库。 | 建议纳入 | 默认纳入 |
| **Q-EVENTS** | FR-15/30 事件留 MySQL `product_events` 90 天，还是只打日志/外部查询面？ | Wave 0 度量（有默认：MySQL 90 天） | pm 若反对默认再选 |
| **Q-CAND** | 候选是否迁出 `spider_results`？ | 否（spec 9.3 技术债） | 本波谓词隔离即可 |

Q1/Q5 已关，installs 的 ON DELETE 与 skills UNIQUE **按冻结答案写进 DBML**，不再等 pm。

---

## 10. 给下游

| 角色 | 内容 |
|------|------|
| **pm** | Q2/Q-EVENTS/Q10 可进 spec 默认列；Q-CAND 保持技术债。Wave 0 永不砍隔离/配额 |
| **architect** | 目标态=§2–3；豁免清单是隔离契约一部分；模块边界：适配器写 DB 不写绝对路径 |
| **backend** | 按 DBML 建 ORM；禁止 API import ORM；豁免落地前不要在租户态依赖 assets 的 Core UPDATE；入队必须带 tenant_id |
| **qa** | §2.4 负向；§5.6 方言（生成列 UNIQUE、NULL 不判重、JSON_CONTAINS）；豁免前后 rowcount；配额含候选；上海月切 |
| **sre** | PR1 DDL 小表秒级。Redis：scrapy persist 与无 TTL hash。S4 需 MYSQL_FIDELITY。幽灵 028–030 pyc 勿当已迁 |
| **data-collector** | 候选仍 `spider_results`；转正依赖 source_type 列宽；不要为 marketplace 源建 `capability_sources` 行（D16） |
| **analyst** | 漏斗用 `product_events`，不用 `operation_logs` |

---

## 11. DBA 自检

- [x] 新表均有「一行 = ___」（含推定 `product_events`）
- [x] 快照 vs 引用已按「当时/现在」判定（安装默认引用；FR-29 保留）
- [x] 索引只从推定 Top-N 来；重复 parent 索引已标评估不建
- [x] 破坏性 DDL：本轮不做 catalog 唯一键改造；skills alive_flag 按 spec 不做
- [x] 无手写迁移 SQL
- [x] 无新的 production EXPLAIN（已标推定；引用现有两则 MYSQL_FIDELITY 断言；S4 真库补）
- [x] Redis：现键点名 TTL/失效缺口；新键给出 name+TTL+失效
- [x] 未写 Service/Repository，未选 API 形状
- [x] 业务语义已冻结的不再问；其余停止并问 pm
- [x] 坑点文件：本轮 **无** 新的 EXPLAIN/测试/ESC/迁移演练证据达到「实战已验证」门槛，不创建 `auto-agents-pitfalls.md`（不复制 SKILL.md 已有 INCR/NULLS LAST 等）
