# db-spec · feat-four-pillars-v2

> 上游：PRD `.sdlc/feat-four-pillars-v2/01-define/spec.md` v1.6（FR-01…20 + FR-70…75 + FR-30…45）｜方案 `02-shape/contract.md` **v1.8** §8｜ADR-0012/0013/0014/0016/0018
> 下游：`schema.dbml` → Alembic **autogenerate**（禁手写 SQL）→ `/backend` ORM
> **已有表 IR**：DBML = live 全列（ORM + 011/014/018/019/025）∪ 本特征加列。禁止「看起来像全表的 stub」。漏 live 列 = autogenerate **DROP**，不是 expand。对齐禁止 DROP 现网列/现网索引。新表不受此条。
> 泳道：L4｜作者：/dba｜日期：2026-09-10
> 本文件是 v2 **现行**数据契约，不是旧 `.sdlc/feat-four-pillars/02-shape/` 的拷贝。旧文件只作输入。
> Alembic 头：**039**（038 之后；`listed_at` DATETIME(6)）。禁止复活 028/029/030 pyc。Q-BILL 未决 → 不建 billing。Q-LLM 已关：LiteLLM 替换 new-api；**LiteLLM Postgres 不进本 Alembic / 不进 `platform_core/models`**。生产 **禁止** downgrade past 037。

## 0. 实体与粒度（建模第一步的产出）

| 实体（表名） | 一行代表什么 | 来源 FR | 别名归并 |
|---|---|---|---|
| `product_events` | 一次已发生的产品事实（追加） | FR-15/16/43；ADR-0016 | 「埋点」「漏斗事件」统一叫 product event |
| `capability_sources` | 一条已登记的外部树（稳定 name + type + uri） | FR-38/41；ADR-0011 | 「源」；plugin-updater **不是**源 |
| `capability_assets` | 五类之一的 catalog 身份（类型内全局 name） | FR-30/33/40/44；ADR-0012/0018 | 已有表；只加列，不改粒度 |
| `capability_commands` | 一条 slash 命令的类型化细节（与 catalog 1:1） | FR-39 | 不是插件 JSON 货架 |
| `capability_components` | 一条出处或运行时引用边（父资产 → 子资产） | FR-34.8/36；ADR-0018 | 「合集边」；**不是**安装礼包 |
| `capability_installs` | 一企业把 **某一行** 资产订到某一宿主 | FR-34/35；ADR-0018 | 「订阅行」「安装行」 |
| `capability_aliases` | 一条人工 vanity slug → 一个资产 | FR-45；ADR-0012 | 同步不自动建 |
| `capability_plugins` / `capability_experts` / `capability_teams` | 已有 1:1 细节（插件 / 智能体人设 / 专家团） | — | **不 rename** `capability_experts`；本特征不加列 |
| `skill_jobs` | 一次扫描/评分/同步作业（已有） | FR-38 | live 全列 ∪ 只加 `source_id`；`job_type` 短码装 `src_sync` |
| `skills` | 一条技能治理+文件镜像（已有细节表） | FR-41 源类型加宽 | **只**加宽 `source_type`；不改粒度、不补 alive |
| `channel_events` | 一次值班启停/配置动作（已有） | FR-71；ADR-0014 | live 全列 ∪ 加 `gateway_ref`；**不改** `channel_id` 类型 |
| `channel_probe_results` | 一次探针批次内对某模型的 10 维体检（已有） | GWT-07.6 | live 全列 ∪ 加 `gateway_ref` |
| `spider_results`（候选非新实体） | `source='marketplace'` 的一条采集 item | FR-09…11；ADR-0013 | 不迁表；`tenant_id` NOT NULL |

**粒度必须能用一句话写出来。**

**被判定为「不是实体」的名词**：

| 名词 | 判定 | 理由 |
|---|---|---|
| `listing_state` | 字段 | 上架三态，禁止 `capability_listings` 表（ADR-0018） |
| 治理 `status` / 许可 / 黑名单 / `health_status` | 字段 | 五闸独立，禁止合成一个 status |
| `host_compat` | JSON 列 | NULL ≠ `[]`（见 §0.1） |
| `alias_origin_refs` | JSON 列 | 折叠路径集，非查询列 |
| 出站钥匙 | 配置绑定 | v1 恰好绑一个 `tenant_id`；**不建表**；禁止复活 028 `api_keys` |
| LiteLLM 模型/Key/spend | 外部引用 | 网关自有 PG；本库只存 `gateway_ref` 字符串 |
| 候选独立表 / 数仓 ODS / billing | 不做 | ADR-0013 / spec §5 / Q-BILL |
| `capability_agents` 表 | 不做 | 智能体细节仍住 `capability_experts` |
| enable-host / 本机投影 | 不做 | X-HOST；安装行可有 enabled/trusted，不写宿主磁盘 |

**FR 覆盖核对**：

| FR | 涉及实体 | 承载字段 | 缺口 |
|---|---|---|---|
| FR-11 | `spider_results` | `source` 谓词排除 marketplace；`tenant_id` NOT NULL | 无 DDL |
| FR-13 | 配置 | key→tenant_id 映射 | 无表 |
| FR-15/16/43 | `product_events` | `event_name` / `occurred_at` UTC / 身份 / `props` | 无 |
| FR-33 | `capability_assets` | `listing_state` ∩ `status` ∩ 许可列；查询侧闸 | 无 |
| FR-34/35 | `capability_installs` | (tenant, asset, host)；enabled/trusted | 无 |
| FR-36 | `capability_components` | parent/child/role；解析忽略 listing | 无 |
| FR-38/41 | `capability_sources` + assets 源列 | 同步不 listed；bundled slug 在 `name` | 无 |
| FR-39 | `capability_commands` + assets `asset_type=command` | 独立卡片 | 无 |
| FR-40 | plugins `health_status` + assets `listing_state` | 分列，无 MCP=`unknown` 可 listed | 无 DDL on health |
| FR-42 | assets `license` + `public_license_override` | 已订/解析不被许可闸拆 | 无许可表 |
| FR-44/30 | assets `asset_type` | 值域 expand-contract | 不改 uq |
| FR-45 | `capability_aliases` | slug 存活全局唯一（应用再挡目录短名） | 无第三张 reserved 表 |
| FR-70…75 | `gateway_ref` 列 | 加列双读；禁改 `channel_id` 类型 | 无网关库表 |

### 0.1 建模决策记录（有取舍的才写）

| 决策 | 选了什么 | 备选 | 理由 |
|---|---|---|---|
| 候选 | 仍住 `spider_results.source=marketplace` | 迁表 / `tenant_id` NULL | ADR-0013；017 禁止 NULL |
| 占位企业 | 复用 024 已种子 `tenants.slug=platform` | 第二入站租户 | 合同锁；Q-PLACE 仍开但不发明第二租户 |
| 出站钥匙 | 配置绑定恰好一租户 | 建 `api_keys` / stamp 028 | 合同锁；Q-BILL 未决不借 028 |
| 产品事件 | 主库追加表；v1 无精确一次键 | 数仓 / `operation_logs` / UNIQUE 幂等 | ADR-0016 |
| 目录身份 | 保持 `uq_asset_type_name_alive`；bundled `{plugin}__{origin_local_name}` | 改成 (source, name) | ADR-0012 |
| 安装 | TenantMixin；**禁止豁免** | 平台表 / 级联礼包 | ADR-0018；T-25 |
| 上架时刻 | `listed_at` 快照；unlist **不清空** | unlist 置 NULL | GWT-37.6；合同锁 |
| 安装标题/版本 | **引用** `asset_id`（现在） | 下单快照 | spec 未要求历史小票 |
| 许可 | 资产行 `license`（现在，同步拷贝）+ `public_license_override` | 删 plugins.license | 双写即可；本波不删列 |
| `host_compat` | JSON：NULL=四宿主可订；`[]`=都不可订；非空=仅名单 | 第三种「空」 | QA-04；禁止用 `[]` 当未声明 |
| `gateway_ref` | **加可空列** + 双读；`channel_id` BIGINT 不动 | 一票改类型 / 复制 Prisma 表 | 合同 §8；ADR-0014 |
| 新行无 new-api PK | `channel_id=0` 哨兵 + 必写 `gateway_ref` | 本票把 `channel_id` 改可空 | 禁改类型；0 不是合法自增 PK |
| 主键 | `INT AUTO_INCREMENT` 跟仓 | 教科书 BIGINT | 诊断 1.5；新表跟仓 |
| 时间 | naive `DATETIME` 存 UTC；报表日 Asia/Shanghai。**`listed_at` 用 DATETIME(6)**（见下） | 技能默认 DATETIME(3) / 036 的 DATETIME(fsp=0) / `TIMESTAMP` | 全库不混 TIMESTAMP。`listed_at` 要对 Python `datetime.isoformat()` 微秒往返，见 GWT-37.6 |
| 枚举 | 物理 VARCHAR + 应用校验 | MySQL ENUM | 改值要 DDL；DBML enum 仅文档 |
| `origin_ref` | VARCHAR(256) | 512 | Q6 不阻塞；加宽是非破坏 |
| `source_type` | 16→32（assets **与** skills 同迁） | 保持 16 | `marketplace_crawled`(20) 装不下 |
| `components.role` | VARCHAR(32) | 16 | `bundled_command` 已 16 顶格 |
| 软删 | 源/目录/安装/alias 要；事件/边/命令细节/渠道审计不要 | 一律软删 | 豁免矩阵；安装要才能再订 |
| 合集边删除 | 边 RESTRICT 子**资产**；细节表对自身 asset_id 可 CASCADE | 订插件 CASCADE 安装 | 不是礼包 |

时区：全库新列 UTC 存储，展示/用量/近 7 日切日 **同一套 Asia/Shanghai 业务日**。不混用 `TIMESTAMP` 与 `DATETIME`（存量混用不在本波清理）。`listed_at` 是 DATETIME(6)；其余时间列仍 naive DATETIME（fsp=0），本票不抬全库精度。

## 1. 数据字典

物理类型约定：金额无；布尔 `TINYINT(1)`；枚举 VARCHAR；JSON 仅非查询灵活属性。时间列默认 DATETIME；**`listed_at` 例外 DATETIME(6)**（isoformat 微秒往返）。可空字段必须写 NULL 语义。

### product_events

一行 = 一次已发生的产品事实。追加；保留 ≥90 天；租户无查询面。

| 字段 | 类型 | 可空 | 默认 | 说明 / 为什么是这个类型 |
|---|---|---|---|---|
| `id` | INT | 否 | AUTO_INCREMENT | 代理主键（跟仓） |
| `occurred_at` | DATETIME | 否 | — | **业务时间** UTC。报表切日转 Asia/Shanghai。写入方必须显式传，禁止用服务器本地 now 冒充 |
| `event_name` | VARCHAR(64) | 否 | — | 蓝图字面量，dba 不改口径。见 §2.1 登记 |
| `tenant_id` | INT | 是 | NULL | NULL=匿名页/无法消歧到企业。是**事件主语**，不是行级隔离归属 |
| `actor_user_id` | INT | 是 | NULL | 已登录用户；匿名 NULL。不加 FK（用户可删，事件要留） |
| `anonymous_id` | VARCHAR(64) | 是 | NULL | 浏览会话匿名身份。先逛再注册必须与浏览事件同一值（GWT-15.5） |
| `role` | VARCHAR(32) | 是 | NULL | 已登录才有（admin/operator/viewer/platform_admin…）；匿名 NULL |
| `props` | JSON | 是 | NULL | 非查询列：cta/page/spider/source/result_count/is_marketplace_candidate/dimension/host/q… |
| `created_at` | DATETIME | 否 | CURRENT_TIMESTAMP | 行写入时刻（记录时间） |
| `updated_at` | DATETIME | 否 | CURRENT_TIMESTAMP | IR/R-AUD 必备；应用**永不更新**（追加表） |

**可空性**：`tenant_id` NULL=匿名或登录失败无法消歧；`anonymous_id` NULL=无浏览会话的注册（GWT-15.14 仍记 signup，不进 F1 分母）；已登录优先写 tenant+user，浏览身份在 signup 仍要带。

无 `idempotency_key`。v1 至少一次，允许重复。禁止 UNIQUE 幂等键（合同锁）。

### capability_sources

一行 = 一条已登记的外部树。

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | INT | 否 | AUTO_INCREMENT | 代理主键 |
| `name` | VARCHAR(128) | 否 | — | 源稳定名；存活唯一 |
| `source_kind` | VARCHAR(16) | 否 | — | `local` / `git` / `url`。**禁止**列名 `type` 与 Python 冲突。`url` 创建失败（应用层），本列仍允许该字面量以便拒因可查 |
| `uri` | VARCHAR(512) | 否 | — | 本地路径或 git URL；不是查询列 |
| `is_enabled` | TINYINT(1) | 否 | 1 | 1=参与同步；0=停用**不清行**（配置删除） |
| `last_sync_at` | DATETIME | 是 | NULL | NULL=从未同步成功结束 |
| `last_succeeded` | INT | 否 | 0 | 最近一次同步成功包数 |
| `last_failed` | INT | 否 | 0 | 最近一次失败包数 |
| `last_error` | VARCHAR(512) | 是 | NULL | NULL=最近一次无行内错误摘要 |
| `tenant_id` | INT | 是 | NULL | 平台级恒 NULL；防御列，与 assets 同形 |
| `deleted_at` | DATETIME | 是 | NULL | 软删；NULL=存活 |
| `alive_flag` | SMALLINT | 生成列 | — | `CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END`（与 025 同构） |
| `created_by` / `updated_by` | VARCHAR(64) | 是 | NULL | 超管用户名 |
| `created_at` / `updated_at` | DATETIME | 否 | CURRENT_TIMESTAMP | |

同步**不得**把第三方标 listed。禁止迁移里 attach 源。

### capability_assets（已有；本特征加列 + 值域 expand）

一行 = 五类之一的 catalog 身份。`tenant_id` 恒 NULL。**不要**加 TenantMixin。**不改** `uq_asset_type_name_alive`。

**已有列保持**（不重开；DBML 必须逐列写出，禁止 stub）：`id`, `asset_type`, `name`, `title`, `description`, `category`, `status`, `source_type`, `source_url`, `source_author`, `content_hash`, `score`, `ai_suggested_score`, `tier`, `reviewed_by`, `reviewed_at`, `similar_to`, `file_path`, `sync_state`, `tenant_id`, `detail_id`, `created_at`, `updated_at`（018）+ `deleted_at`, `created_by`, `updated_by`（019）+ `alive_flag`（025）。列序=上述 live 物理序，本特征 ADD 接表尾。`source_type` 在原位加宽，不是新列。

**本特征变更列**：

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `asset_type` | VARCHAR(16) | 否 | — | **值域** expand：读写接受 `skill\|plugin\|command\|agent\|team` **以及** 一周期 `expert\|expert_team`。公开 JSON 只出新五类。不改列类型、不改 uq 列集 |
| `source_type` | VARCHAR(32) | 否 | `self_built` | **加宽** 16→32（非破坏）。合法值含 `self_built` / `network_imported` / `marketplace_crawled`(20) / `source_indexed`(14) |
| `listing_state` | VARCHAR(16) | 否 | **server_default `unlisted`** | `unlisted` / `listed` / `coming_soon`。与 `status` / 许可 / 黑名单独立 |
| `listed_at` | DATETIME(6) | 是 | NULL | 最近一次进入 `listed` 的时刻（当时）。NULL=从未 listed。**unlist 不清空**。精度见下「listed_at 精度」 |
| `source_id` | INT | 是 | NULL | NULL=尚未 attach 源（第一方窗口）。禁止代码假设「NULL ⇒ 永远第一方」 |
| `origin_ref` | VARCHAR(256) | 是 | NULL | 源内路径。NULL=无源路径。Q6 默认 256 |
| `origin_local_name` | VARCHAR(128) | 是 | NULL | 插件内短名；bundled slug 用 `{origin_plugin_name}__{origin_local_name}` |
| `origin_plugin_name` | VARCHAR(128) | 是 | NULL | 父插件目录名；第一方无父插件则 NULL |
| `host_compat` | JSON | 是 | NULL | **NULL=四宿主可订**；`[]`=都不可订；非空数组=仅名单。第一方回填必须保持 NULL |
| `alias_origin_refs` | JSON | 是 | NULL | 被折叠的路径集，供次级 upsert，**非查询列** |
| `license` | VARCHAR(64) | 是 | NULL | 同步拷贝的许可标识（现在）。NULL=未声明 |
| `public_license_override` | TINYINT(1) | 否 | 0 | 超管特例放行（现在）。0=未放行 |
| `writable` | TINYINT(1) | 否 | 1 | 1=第一方可写库+源树；0=第三方。attach 源时改 0 |

`skills.source_type` 同步加宽到 VARCHAR(32)（同一 DDL 波，非破坏）。`skills.name` **不**补 `alive_flag`。见下节 `skills` 已有列保持。

**listed_at 精度（QC 条件 2 / GWT-37.6）**：选 **DATETIME(6)**。不选技能默认 `DATETIME(3)`，也不保留 036 的 `DATETIME`（fsp=0）。

| 候选 | 存什么 | 读回 `isoformat()` | GWT-37.6 Then |
|---|---|---|---|
| `DATETIME`（036 / fsp=0） | 秒；MySQL 对 ≥0.5s 四舍五入 | `2026-09-10T00:30:47` | 失败（MYSQL_FIDELITY 实测：`…:47` ≠ `…:46.681121`） |
| `DATETIME(3)`（技能默认） | 毫秒 | `…46.681000` | 失败（丢微秒 3 位） |
| **`DATETIME(6)`（本列）** | 微秒，与 Python `datetime` 同位 | `…46.681121` | **稳定** |

理由：PATCH listed 在 `commit` 前投影内存 `datetime.isoformat()`（微秒非 0 时 6 位）；unlist 再读库。Then 是「unlist 后 `listed_at` 仍在且与 listed 时相同」，不改 Then、不改测试。只有 fsp=6 让这条 round-trip 在 MySQL 上成立。精度加宽是 **expand**：列仍在，无 DROP。039 down 回到 `DATETIME`（丢小数）；生产仍 **禁止** downgrade past 037。隔离库名 `aa_qc_cond2_039_*`，禁止把 `ALEMBIC_URL` 指到业务库 `auto_agents` 做 down 实验。

### capability_commands

一行 = 一条 slash 命令的细节（catalog 行 `asset_type=command` 的 1:1）。

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | INT | 否 | AUTO_INCREMENT | |
| `asset_id` | INT | 否 | — | FK → `capability_assets.id` ON DELETE CASCADE（仅细节行） |
| `slash` | VARCHAR(64) | 否 | — | 如 `sdlc`。**不要**全局 UNIQUE（两插件可同 slash）；catalog `name` 才是 `{plugin}__{stem}` |
| `description` | VARCHAR(512) | 是 | NULL | 卡片摘要 |
| `body_md` | TEXT | 是 | NULL | 命令正文；本表即侧表 |
| `created_at` / `updated_at` | DATETIME | 否 | CURRENT_TIMESTAMP | |

无软删（随资产软删/物理删清细节）。无 `tenant_id` 列。

### capability_components

一行 = 一条出处或运行时引用边。

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | INT | 否 | AUTO_INCREMENT | |
| `parent_asset_id` | INT | 否 | — | FK → assets RESTRICT |
| `child_asset_id` | INT | 否 | — | FK → assets RESTRICT |
| `role` | VARCHAR(32) | 否 | — | `bundled_skill` / `bundled_command` / `bundled_agent` / `uses_skill` / `team_member`。不进唯一键 |
| `created_at` / `updated_at` | DATETIME | 否 | CURRENT_TIMESTAMP | |

无软删。子行 `missing`：**保留边**，列表 JOIN 过滤。`role` 不进 UNIQUE：同一父子只一条边。

三张查询脸（同一表，三个谓词）——不是三张表：

| 脸 | 过滤 listing？ | 过滤 blacklist/软删？ |
|---|---|---|
| 运行时引用 | **否** | **是**（跳过并审计） |
| 治理台 components | **否** | 给超管看量子行 |
| 公开「包含」 | **只要** listed/coming_soon | 是 |

### capability_installs

一行 = 一企业 × 一资产 × 一宿主。**TenantMixin。禁止进 `TENANT_EXEMPT_TABLES`。**

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | INT | 否 | AUTO_INCREMENT | |
| `tenant_id` | INT | 否 | — | 隔离列；017 风格 NOT NULL（迁移层收紧；禁止靠 Mixin 默认可空） |
| `asset_id` | INT | 否 | — | FK → assets **RESTRICT**（订阅史不随物理删消失；产品路径软删资产） |
| `host` | VARCHAR(16) | 否 | — | `grok` / `zcode` / `kimi` / `claude` |
| `enabled` | TINYINT(1) | 否 | 1 | 「我的安装」启用开关。**不是** enable-host（不写磁盘） |
| `trusted` | TINYINT(1) | 否 | 0 | 信任（开须确认）。黑名单/软删后应用禁止改这两列，仍可卸 |
| `deleted_at` | DATETIME | 是 | NULL | 卸载=软删；可再订 |
| `alive_flag` | SMALLINT | 生成列 | — | 与 025 同构 |
| `created_by` / `updated_by` | VARCHAR(64) | 是 | NULL | |
| `created_at` / `updated_at` | DATETIME | 否 | CURRENT_TIMESTAMP | `created_at`=订阅成功时刻 |

unlist 后行留。订/卸**不**沿合集边级联。不占三类配额。幂等键语义=(tenant_id, asset_id, host)。

### capability_aliases

一行 = 一条人工短名。

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | INT | 否 | AUTO_INCREMENT | |
| `slug` | VARCHAR(128) | 否 | — | 人工短名；存活全局唯一 |
| `asset_id` | INT | 否 | — | FK → assets RESTRICT。v1 一资产至多一条存活 alias |
| `asset_type` | VARCHAR(16) | 否 | — | 反规范化，公开路由第一段；D22b 回填须同步 |
| `tenant_id` | INT | 是 | NULL | 平台级恒 NULL |
| `deleted_at` / `alive_flag` | 同 025 | | | 软删后可重建同 slug |
| `created_by` / `updated_by` / `created_at` / `updated_at` | | | | |

写入时应用层再查存活 `capability_assets.name`：冲突 → 保存失败、两边不变（409）。**不**建 `reserved_slugs` 第三表。同步不 insert alias。

### capability_plugins / capability_experts / capability_teams（已有；本特征不加列）

DBML 必须 live 全列，禁止写成 `id/asset_id/timestamps` stub。018 UniqueConstraint **与** `ix_*_asset_id` 并存于真库，禁止为对齐 stub 而 DROP。

**capability_plugins 已有列保持**（018）：`id`, `asset_id`, `version`, `author`, `license`, `manifest`, `bundled_skills`, `mcp_servers`, `hooks`, `commands`, `health_status`（NOT NULL default `unknown`）, `last_verified_at`, `verify_detail`, `created_at`, `updated_at`。约束/索引：`uq_capability_plugins_asset`、`ix_capability_plugins_asset_id`。本波不删 `license`。

**capability_experts 已有列保持**（018）：`id`, `asset_id`, `persona_md`, `tools`, `bundled_skills`, `mcp_refs`, `model_pref`, `created_at`, `updated_at`。`uq_capability_experts_asset`、`ix_capability_experts_asset_id`。**不 rename**。

**capability_teams 已有列保持**（018）：`id`, `asset_id`, `leader_expert`, `members`, `workflow_md`, `created_at`, `updated_at`。`uq_capability_teams_asset`、`ix_capability_teams_asset_id`。

### channel_events / channel_probe_results（已有；只加列）

**channel_events 已有列保持**（011 + ORM；DBML 必须逐列写出）：`id`, `channel_id`（BIGINT，禁改类型）, `action`, `usage`, `limit_quota`, `window_hours`, `reason`, `source`, `created_at`。索引保持：`ix_channel_events_channel_created`、`ix_channel_events_created_at`。无 `updated_at` 列，本特征禁止 ADD。

**channel_probe_results 已有列保持**（011 + ORM）：`id`, `channel_id`（BIGINT，禁改类型）, `model`, `verdict`, `scores`, `latency_ms`, `batch_id`, `created_at`。索引保持：`ix_channel_probe_results_channel_created`、`ix_channel_probe_results_batch_id`。无 `updated_at` 列，本特征禁止 ADD。

**本特征加列**（接表尾）：

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `channel_id` | BIGINT | 否 | — | **本特征禁止改类型**。今日=new-api PK。新 LiteLLM 事件写 **0**（哨兵：无 new-api PK） |
| `gateway_ref` | VARCHAR(191) | 是 | NULL | 稳定字符串（模型/deployment/key，不透明）。NULL=尚未回填的历史行，读路径回退 `CAST(channel_id AS CHAR)`（0 除外：0 必须已写 ref） |

不把 LiteLLM Prisma 表写入本 IR。backend 禁止网关 DSN。

### skill_jobs（已有；只加列）

**已有列保持**（014；DBML 必须逐列写出）：`id`, `job_type`, `status`, `total`, `succeeded`, `failed`, `detail`, `started_at`, `finished_at`。无 `created_at`/`updated_at`，禁止为 lint 补列。

**本特征加列**（接表尾）：

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `source_id` | INT | 是 | NULL | `src_sync` 作业指向源；其它 job_type 为 NULL。FK ON DELETE SET NULL |
| `job_type` | VARCHAR(16) | 否 | — | **不加宽**；`src_sync` / `scan_plugins` / `promote` 装得下 |

### skills（已有；本特征只加宽 `source_type`）

一行 = 一条技能治理 + 文件镜像（014 细节表，与 `capability_assets` skill 行并存）。**不改粒度。**

**已有列保持**（014+019；026 已删 `ix_skills_deleted_at`；DBML 必须逐列写出）：`id`, `name`, `title`, `description`, `category`, `industries`, `status`, `source_type`, `source_url`, `source_author`, `imported_at`, `content_hash`, `score`, `ai_suggested_score`, `tier`, `reviewed_by`, `reviewed_at`, `review_notes`, `similar_to`, `file_path`（NOT NULL，禁止改可空）, `sync_state`, `tenant_id`, `raw_meta`, `created_at`, `updated_at`, `deleted_at`, `created_by`, `updated_by`。

**本特征变更列**：仅 `source_type` VARCHAR(16)→32（与 assets 同 DDL 波，非破坏）。禁止给 `name` 补 `alive_flag`。禁止其它列变更。索引保持：`uq_skills_name`、`ix_skills_name`、`ix_skills_category`、`ix_skills_status`。不建 `(source_type)` 单列。

## 2. 关系与基数

| 关系 | 基数 | 外键位置 | 可空 | 级联行为 | 说明 |
|---|---|---|---|---|---|
| sources → assets | 1:N | `assets.source_id` | 是 | RESTRICT | 源软删不清资产；物理删源前先卸 attach |
| assets → commands | 1:1 | `commands.asset_id` | 否 | CASCADE | 仅细节行 |
| assets → plugins/experts/teams | 1:1 | 已有 `asset_id` | 否 | CASCADE | 已有；ORM 补 UniqueConstraint 时禁止再 create（018 已有 `uq_*_asset`） |
| assets → components（父） | 1:N | `parent_asset_id` | 否 | RESTRICT | 删父资产前先删边；不 CASCADE 子资产 |
| assets → components（子） | 1:N | `child_asset_id` | 否 | RESTRICT | |
| tenants → installs | 1:N | `installs.tenant_id` | 否 | RESTRICT | |
| assets → installs | 1:N | `installs.asset_id` | 否 | RESTRICT | |
| assets → aliases | 1:0..1 | `aliases.asset_id` | 否 | RESTRICT | v1 一资产一条存活 alias |
| sources → skill_jobs | 1:N | `skill_jobs.source_id` | 是 | SET NULL | 作业留史 |
| events/probes → 网关 | 外部 | `gateway_ref` 无 FK | 是 | — | 外部系统，禁止 FK 到网关 PG |
| product_events → tenants/users | 引用无 FK | — | 是 | — | 审计/事件不加 FK |

默认 RESTRICT。删除逻辑放应用层。

### 2.1 状态流转

```
capability_assets.listing_state：

unlisted ──超管上架──> listed ──超管下架──> unlisted
   └──超管标预告──> coming_soon ──上架──> listed
listed ──标预告──> coming_soon
coming_soon ──超管撤回预告──> unlisted

终态：无。黑名单在治理 status，不是本列。
```

| 流转 | 触发条件 | 谁能触发 | 副作用 |
|---|---|---|---|
| → listed（第三方） | 二次确认 | 超管 | 记下 `listed_at`；unlist 后该时刻不清空 |
| → listed（第一方回填） | 已发布/推荐 + 无第三方源 | 回填脚本（非迁移） | `writable=1`；`host_compat` 保持 NULL |
| 同步 | upsert 目录 | 系统 | **不得**把第三方标 listed |
| listed + 同时 blacklist | — | — | **拒存**；两态保持动作前（不改写成 unlisted） |

**非法**：租户改上架；同步自动 listed；已黑名单再标 listed；因无 MCP 禁止 listed。

```
capability_assets.status（治理，已有）：
experimental / testing / stable / recommended / deprecated / blacklist
与 listing 分列。公开出现 = listing∈{listed,coming_soon} ∩ status∈{stable,recommended} ∩ 许可过闸 ∩ 非软删。
```

```
capability_installs 生命周期（行存在性，不是 status 列）：

无行 ──订阅成功──> 已订（enabled/trusted 可改）
已订 ──卸载（软删）──> 无存活行（可再订）
已订 + unlist ──行留，标已下架，可卸不可新订
已订 + 黑名单/资产软删 ──行只读（经办可卸，不可改 enabled/trusted）
```

**非法**：只读角色订/卸/改启用；预告新订；unlisted/黑名单新订；跨企业改安装行；沿边级联插/删安装。

```
tenants.status（已有，本波不改列）：
active ──到期/停用──> expired|disabled
到期企业不得发新会话；已有会话后续写拒绝。占位 slug=platform 不进「我的结果」。
```

**product_events.event_name 合法值（蓝图原样，禁止改名）**：

`official_page_viewed` · `official_cta_clicked` · `tenant_signup_succeeded` · `login_succeeded` · `login_failed` · `task_run_submitted` · `task_completed` · `results_exported` · `quota_exceeded` · `market_list_viewed` · `market_search_submitted` · `market_detail_viewed` · `market_subscribe_succeeded` · `market_subscribe_rejected` · `market_uninstalled` · `market_listing_changed` · `market_source_sync_completed`

`cta` 五档字面量（在 `props`）：`register_free` / `pricing_pro` / `pricing_enterprise` / `login` / `browse_market`。首页「进入管理后台」「体验 AI 采集流程」另报，不进五档。通知类型字符串 `task_completed` **禁止**当本事件。

### 2.2 时间字段语义

| 字段 | 类型 | 语义 | 报表口径用哪个 |
|---|---|---|---|
| `product_events.created_at` | 记录时间 | 行写入 | 一般不用 |
| `product_events.occurred_at` | 业务时间 UTC | 事件发生 | **漏斗/WACT/超管查询用这个**；切日 Asia/Shanghai |
| `listed_at` | 业务时间 DATETIME(6) UTC | 最近一次上架（微秒） | 治理台展示；unlist 后仍用这个；isoformat 往返必须与 listed 时相同 |
| `installs.created_at` | 业务时间 | 订阅成功 | 「我的安装」排序 |
| `llm_token_usage.stat_date` | 业务日 | 上海日历日（写路径换算） | 用量「本月」/近 7 日与此同一套 |
| `channel_*.created_at` | 记录时间 | 事件/探针时刻 | 值班近 24h |

时区约定：存 UTC（naive DATETIME）。用量与近 7 日失败率窗口同一套 Asia/Shanghai 业务日。**不混用 TIMESTAMP 与 DATETIME（新列）**。`listed_at` 精度 DATETIME(6)，其余仍 DATETIME。

### 2.3 软删决策

| 表 | 加软删 | 理由 |
|---|---|---|
| `capability_sources` | 是 | 删后可重建同名源；UNIQUE 带 `alive_flag` |
| `capability_assets` | 已有 | 不改 |
| `capability_aliases` | 是 | 删后可重建同 slug |
| `capability_installs` | 是 | 卸载后可再订；UNIQUE 带 `alive_flag` |
| `capability_commands` | 否 | 细节随资产 |
| `capability_components` | 否 | 边；missing 保留 |
| `product_events` | 否 | 追加审计 |
| `channel_events` / `channel_probe_results` | 否 | 已有审计表 |
| `skill_jobs` | 否 | 已有 |

加了软删的表，唯一键必须带删除标记（MySQL 用生成列 `alive_flag`，与 025 同构）。

## 3. 唯一键

| 唯一约束 | 字段组合 | 业务规则 |
|---|---|---|
| `uq_asset_type_name_alive` | `(asset_type, name, alive_flag)` | **保持原样**：不加 source、不改列序、不拆键。类型内全局 name。撞名 → 后一次失败，已有行 name 不变 |
| `uq_asset_source_origin_alive` | `(source_id, origin_ref, alive_flag)` | 同步身份。存量 `source_id` 全 NULL 时 MySQL **不判重**。仍按加 UNIQUE 走 expand-contract |
| `uq_sources_name_alive` | `(name, alive_flag)` | 源名存活唯一 |
| `uq_commands_asset` | `(asset_id)` | 命令细节 1:1 |
| `uq_components_parent_child` | `(parent_asset_id, child_asset_id)` | 同一父子一条边；role 不进键 |
| `uq_installs_tenant_asset_host_alive` | `(tenant_id, asset_id, host, alive_flag)` | 一企业×一资产×一宿主一行；再订另一宿主=新行 |
| `uq_aliases_slug_alive` | `(slug, alive_flag)` | 存活 alias 全局唯一 |
| `uq_aliases_asset_alive` | `(asset_id, alive_flag)` | v1 一资产一条存活 alias |
| `skills.name` | 全局、无 alive | **不改** |
| `product_events` | 无业务唯一键 | 至少一次投递，允许重复 |
| `commands.slash` | **无**全局唯一 | 正确；跨插件可同 slash |
| `spider_results (tenant, hash)` | **本波不加** | 禁止借 030 pyc；Q7 未决 |

`source_id` NULL 的第一方行：禁止假设 UNIQUE 会去重。

## 4. 访问模式 Top-N

> 来源：☑ PRD / 方案 / 调用方代码推导（**推定**）。无 production slow_query。
>
> 推定依据：contract §8、ADR-0016 查询面、公开列表 NFR-01（≤400 行 P95<2s）、值班按渠道/ref 拉事件。**上线后按真实慢查询复盘补索引。** 新特征模式一律标 **presumed**。

| ID | 触发场景（FR / 接口） | 过滤字段（等值 / 范围） | 排序 | 返回列 | 频次（次/天） | P95 要求 | 单次行数 |
|---|---|---|---|---|---|---|---|
| P-M01 **presumed** | FR-33 公开列表（查询侧闸再分页） | `listing_state` IN (listed,coming_soon) 等值小集合；`status` IN (stable,recommended)；`asset_type`=可选；`category`=可选；`deleted_at` IS NULL | `id` DESC | 卡片列 | ~5k–50k | 2s（NFR-01） | 20（max 50） |
| P-M02 **presumed** | 公开详情 `/{type}/{name}` | `asset_type`= `name`= 存活 | — | 详情 | ~2k–20k | 200ms | 1 |
| P-M03 **presumed** | 公开详情走 alias | `slug`= 存活 | — | 转资产 | 低于 P-M02 | 200ms | 1 |
| P-M04 **presumed** | 治理台按类型翻页 | `asset_type`= 存活 | `id` DESC | 目录行 | ~500 | 200ms | 20 |
| P-M05 **presumed** | 同步 upsert 次级查找 | `source_id`= `origin_ref`= 存活 | — | id,name | 同步时数百 | 50ms | 1 |
| P-M06 **presumed** | 我的安装 | `tenant_id`= 存活 | `created_at` DESC | 安装行 | ~1k | 100ms | 数十 |
| P-M07 **presumed** | 订阅幂等 | `tenant_id`= `asset_id`= `host`= | — | 一行 | ~500 | 50ms | 0–1 |
| P-M08 **presumed** | 引用解析 / 包含 | `parent_asset_id`= | — | child_id, role | ~1k | 50ms | 数条～数十 |
| P-E01 **presumed** | 超管按事件名+时间 | `event_name`= `occurred_at` 范围 | `occurred_at` DESC | 事件行 | ~200 | 200ms | 50 |
| P-E02 **presumed** | 超管按企业+时间（GWT-15.13/43.10） | `tenant_id`= `occurred_at` 范围 | `occurred_at` DESC | 事件行 | ~100 | 200ms | 50 |
| P-G01 **presumed** | 值班按 gateway_ref 拉事件 | `gateway_ref`= `created_at` 范围 | `created_at` DESC | 事件 | ~200 | 100ms | 数十 |
| P-G02 **presumed** | 值班按 gateway_ref 拉探针 | `gateway_ref`= | `created_at` DESC | 探针 | ~50 | 100ms | 一批 |
| P-G03 | 值班按旧 channel_id 拉事件（expand 双读） | `channel_id`= | `created_at` DESC | 事件 | 过渡 | 100ms | 数十 |
| P-C01 **presumed** | 配额存储 COUNT（FR-11） | `tenant_id`= 且 (`source` IS NULL OR `source`<>'marketplace') | — | COUNT | 回流路径高 | 100ms | 标量 |
| P-C02 **presumed** | 超管候选列表 | `source`='marketplace' | `id` DESC | 候选 | 低 | 200ms | 20 SQL 分页 |

**已知但不进 Top-N（不建索引）**：

- 按 `slash` 全局搜命令（GWT-39.3 是商店侧，走 catalog name/公开闸；~300 行可扫）
- `JSON_CONTAINS(host_compat)`（应用过滤；一期 320 行）
- `alias_origin_refs` 多值
- `description` 全文（公开 `q` 走应用/LIKE，NFR 余量内）
- 给 `skills` 单列 `(source_type)`
- 子→父 components（无 FR）
- `spider_results (source, id)` 候选专用（Wave 0 先谓词；千到万可扫）
- `uq_spider_results_tenant_spider_hash`（030 幽灵；Q7 未决）
- `product_events.anonymous_id` 点查（signup 相关在写入时比对，不是超管 Top-N）
- 任务默认 `(tenant_id, id)`（026 已治理；本波不补）

## 5. 索引设计

| 索引 | 字段顺序 | 服务模式 | 列顺序理由（ESR） |
|---|---|---|---|
| `PRIMARY` | `id` | — | 各表代理主键 |
| `uq_asset_type_name_alive` | `(asset_type, name, alive_flag)` | P-M02 | **已有，不改**。等值类型+名 |
| `idx_assets_listing_status_type_cat` | `(listing_state, status, asset_type, category)` | P-M01 | 等值小集合 listing/status → 等值 type/category。320 行；排序 filesort 可接受 |
| `idx_assets_source_origin_alive` → 收缩为 `uq_asset_source_origin_alive` | `(source_id, origin_ref, alive_flag)` | P-M05 | 等值同步身份。Step1 普通索引 / Step3 UNIQUE |
| `uq_sources_name_alive` | `(name, alive_flag)` | 源登记 | 业务唯一兼点查 |
| `uq_commands_asset` | `(asset_id)` | 1:1 | FK+唯一 |
| `uq_components_parent_child` | `(parent_asset_id, child_asset_id)` | P-M08 | 等值父 → 子；最左前缀覆盖 parent 点查，**不**再单建 parent |
| `idx_components_child` | `(child_asset_id)` | FK 支撑 | InnoDB FK 必须有索引；非 Top-N 反向脸 |
| `uq_installs_tenant_asset_host_alive` | `(tenant_id, asset_id, host, alive_flag)` | P-M06/P-M07 | 多租户最左 tenant；幂等三元组。P-M06 数十行 filesort 可接受 |
| `idx_installs_asset` | `(asset_id)` | FK 支撑 | |
| `uq_aliases_slug_alive` | `(slug, alive_flag)` | P-M03 | |
| `uq_aliases_asset_alive` | `(asset_id, alive_flag)` | 治理改 alias | 1:1 |
| `idx_product_events_name_occurred` | `(event_name, occurred_at)` | P-E01 | 等值 name → 范围/排序 occurred_at |
| `idx_product_events_tenant_occurred` | `(tenant_id, occurred_at)` | P-E02 | 等值 tenant → 范围 occurred_at |
| `ix_channel_events_channel_created` | `(channel_id, created_at)` | P-G03 | **已有，expand 期保留** |
| `idx_channel_events_gateway_ref_created` | `(gateway_ref, created_at)` | P-G01 | 等值 ref → 排序时间 |
| `ix_channel_probe_results_channel_created` | `(channel_id, created_at)` | 旧探针 | **已有，保留** |
| `idx_channel_probe_gateway_ref_created` | `(gateway_ref, created_at)` | P-G02 | |
| `ix_channel_probe_results_batch_id` | `(batch_id)` | 已有批次 | 保留 |

**已评估不建**：

| 候选 | 不建的理由 |
|---|---|
| `(listing_state)` / `(status)` 单列 | 基数 ≤6；已作 P-M01 非最左列 |
| `ix_components_parent` | UNIQUE(parent, child) 最左前缀已覆盖（026 刚删过这类重复） |
| `ix_commands_slash` | 非 Top-N；slash 非全局唯一 |
| `host_compat` 函数索引 | 一期 320 行；NULL vs `[]` 是数据夹具不是索引 |
| `(tenant_id, source)` on `spider_results` | P-C01 先谓词正确；现有 tenant 前缀+小表；慢查询再补 |
| `product_events` 幂等 UNIQUE | 合同禁止 |
| `gateway_ref` 单列无时间 | 已被 (ref, created_at) 最左覆盖 |

最小索引原则：新表 = 业务唯一 + FK + 上表 Top-N。P-M01 是商店读模型关键路径，允许这一条非唯一复合。容量 ~320 行资产，无需 gh-ost。

## 6. Redis 键

| 键模式 | 类型 | 值结构 | 写入方 | 读取方 | TTL | 失效路径 | 未命中行为 | 容量估算 |
|---|---|---|---|---|---|---|---|---|
| `newapi:channel:cfg:{id}` | Hash | `limit_quota` / `window_hours` / `cooldown_seconds` / `updated_at` | 值班写面（T-18 expand 仍写） | 调度器双读旧键 | **无 TTL**（配置；`clear_config` DEL） | 清除配置时 DEL；改配置 HSET 覆盖 | 无键=未纳管，回全局默认 | 数十键 × <1KB。无 TTL 理由=显式生命周期+容量上限小；不依赖 maxmemory 淘汰 |
| `relay:channel:cfg:{ref}` | Hash | 同上 | T-18/T-19 新写只走此键（`RELAY.*` 配置前缀） | 调度器**先读此键，miss 再读旧键** | 无 TTL（同左） | 同左，按 `gateway_ref` DEL | 回旧键；两键都无=未纳管 | 与模型/deployment 数同阶 |
| `market:src_sync:{source_name}` | String（锁） | token | 同步作业 | 同步作业 | ≥ 最长同步 + 续期（建议 900s，Lua 续期） | Lua 释放（GET==token 才 DEL）；失败交 TTL | 抢不到=拒绝第二同步 | 源数（个位数） |
| `skill:public:rl:{ip}` | String | 计数 | 公开市场/旧公开技能 | 限流引擎 | 60s（窗口） | 窗口过期；**必须 pipeline INCR+EXPIRE** | 回源放行（fail_open） | IP×窗口，小 |
| `quota:count:{tenant_id}:results:v2` | String | COUNT 标量 | QuotaService | QuotaService | 60s | 结果写入后 DEL（Cache-Aside）；谓词必须含「排除 marketplace」 | 回源 COUNT | 租户数 |
| `llm:usage:m:{yyyymm}` | Hash | field **目标** `{tenant_id}\|{dim}\|total`；expand 双写旧 `{dim}\|total` | `record_usage` | 熔断读 | 93d | 纯 TTL + 月切；切读后停写旧 field | Redis 故障回表/内存 | 月×维 |
| `llm:usage:d:{yyyymmdd}` | Hash | `{tenant}\|{dim}\|{model}\|{metric}` | 同上 | flush | 30d | TTL | 跳过 flush | 日×维×模型 |

**禁止**新键 `market:public:rl:`（复用 `skill:public:rl:`）。**禁止**第三配置前缀（只允许读 `NEWAPI.*` + 写 `RELAY.*`）。

`newapi:probe:lock` / `newapi:scheduler:lock` / `newapi:scheduler:state`：Wave L 键名 expand 与 cfg 同构（读旧写新）；TTL 跟现锁（略大于临界区）。细节归 T-18/T-19 实现，本契约锁的是 **string ref** 与双读顺序。

目录列表缓存 v1 **不建**。埋点缓冲 v1 **不建**（直写 `product_events`，失败吞掉）。

Redis 不可用：配额/限流按现网 fail-open 或回源 DB；产品事件失败不挡主路径；渠道配置读失败=未纳管/降级信封（值班 200 + `available=false`）。

**月度 field expand-contract（P1 债，不挡市场 PR1，建议 Wave 0 顺手）**：双写新 field → 切读去掉 fallback → 停旧 field。供应商熔断仍串租户直到切读完成。

## 7. 数据量与增长

| 表 | 当前行数 | 日增 | 一年后预估 | 分表/归档策略 |
|---|---|---|---|---|
| `capability_assets` | ~现网四类，目标 ~320 一期 | 同步批次 | <1 万 | 暂不需要 |
| `capability_installs` | 0 | 订阅 | 租户数 × 订阅数，<10 万 | 暂不需要 |
| `product_events` | 0 | 页浏览主导（推定 10^3–10^5/日） | 90 天窗口 | **保留 ≥90 天**；超期归档/删（独立作业，不进迁移）。不分区直到量使备份/锁成为问题 |
| `channel_events` / probes | 小 | 值班 | 小 | 已有；加列秒级 |
| `spider_results` | 未知 | 采集 | 本波不加 DDL | 候选不迁出 |

千万行以上才考虑分区。本期无需 gh-ost / pt-osc。`source_type` 加宽、加可空列：MySQL 8 INPLACE，320 行秒级。

## 8. 破坏性变更

本次 **不是**「全部纯加法」。分波：

### Wave 0 — 纯加法 + 行为不变量（无市场新表）

| 变更 | 类型 | 做法 |
|---|---|---|
| `TENANT_EXEMPT_TABLES` + 夹具 | 行为，非 DDL | T-04：`capability_assets`（功能必需）+ plugins/experts/teams 防御性。T-12：`product_events` 同 PR 登记 |
| 入队 `tenant_id` 必填 | 不变量 | 017 已 NOT NULL；无企业不入队；占位=`platform` |
| 配额/我的结果/导出/出站排除 marketplace | 谓词 | 无 DDL |
| 出站钥匙绑一租户 | 配置 | 无表；旧字符串列表=未绑定 |
| 用量上海日 | 写路径 | 无 DDL；`stat_date` 口径 |
| `product_events` 新表 | 纯加法 | 单迁移 autogenerate；up/down |
| Redis 月度 field | 键内 expand-contract | 见 §6 |

### Wave L — `gateway_ref` 只加列

| 变更 | 类型 | expand-contract |
|---|---|---|
| `channel_events.gateway_ref` / `channel_probe_results.gateway_ref` | 加法（可空 VARCHAR） | **一步加列+索引**。读双写：优先 `gateway_ref`，NULL 则回退 `channel_id` 字符串（`channel_id=0` 视为无旧身份，必须已有 ref） |
| HTTP/Redis string ref | 非 DDL | T-18/T-19：`newapi:channel:cfg:{id}` 双读 → `relay:channel:cfg:{ref}` |
| `channel_id` BIGINT → 字符串 / 改可空 | **禁止本特征** | 收缩（改类型/丢列）另开特征，三迁移 |

### Wave 1 — 五表 + 加列 + 值域三步 + UNIQUE 三步

| 变更 | 类型 | expand-contract 三步 |
|---|---|---|
| 五新表 + assets 加列 + `skill_jobs.source_id` + `source_type` 16→32 | 加法 / 类型扩大 | 单波 autogenerate；`listing_state` **必须** server_default；`source_type` 加宽非破坏，**不要**同文件改列名 |
| `uq_asset_source_origin_alive` | 加 UNIQUE | Step1 普通索引 `idx_assets_source_origin_alive` ｜ Step2 非 NULL 重复探测期望 0 + 应用拒重 ｜ Step3 UNIQUE。三文件三发布窗口；回填不进迁移 |
| `asset_type` 值域 `expert`→`agent`、`expert_team`→`team` | **数据**破坏（uq 左列取值改写） | Step1 应用双值可读，公开只出新枚举 ｜ Step2 独立幂等脚本回填（探测撞 `uq_asset_type_name_alive`，现网无 agent/team 行期望 0；alias.asset_type 同步） ｜ Step3 写路径拒旧值。**不 rename** `capability_experts`。**不改** uq 列集。UPDATE **不进** Alembic |
| 第一方 listed 回填 | 数据 | 独立脚本：`source_id IS NULL` 且第一方规则且 `status IN (stable,recommended)` → `listing_state=listed`，`writable=1`，`host_compat` **保持 NULL**。校验：`listing_state=listed AND source_id IS NOT NULL` → 0（PR1 不得 attach 源） |

### 039 hotfix — `listed_at` DATETIME → DATETIME(6)（expand）

| 变更 | 类型 | 做法 |
|---|---|---|
| `capability_assets.listed_at` | 精度加宽（expand） | 039 单步 `ALTER` 为 DATETIME(6)。列仍在。存量秒级值补 `.000000`。down 回到 DATETIME（丢微秒）。生产 **禁止** downgrade past 037 |

**本特征禁止**：改 `uq_asset_type_name_alive`；给 `skills.name` 补 alive；rename experts；删 `capability_plugins.license`；把 `skills.file_path` 改可空；MySQL ENUM；候选迁表；放宽 `spider_results.tenant_id`；复活 028/029/030；Prisma/LiteLLM 表进 models；安装表进豁免清单。039 用 `op.alter_column` + `mysql.DATETIME(fsp=6)`，不是裸 `op.execute` SQL。

## 9. 需真库验证的方言特性（交给 /qa）

- 生成列 `alive_flag` + UNIQUE 含 NULL：软删后可重建；SQLite 与 MySQL 不一致 → `MYSQL_FIDELITY=1`
- UNIQUE 含 `source_id` NULL：**不判重**；夹具禁止当去重
- `host_compat` NULL vs `[]` vs 非空：JSON 字面量，不是约束
- `listing_state` server_default：旧行回填为 `unlisted`（ADD NOT NULL DEFAULT）
- `source_type` VARCHAR(16)→32：`alembic/env.py` 未开 `compare_type`，必须 `MYSQL_FIDELITY=1` 对人审，禁止脑补漏加宽 `skills`
- 018 已有 `uq_capability_plugins_asset` 等：autogenerate 禁止再 create_unique
- Mixin `tenant_id` ORM 可空 vs 017 NOT NULL：安装表迁移必须 NOT NULL；SQLite create_all 会骗人
- EXPLAIN P-M01/P-E01/P-E02/P-G01：S4 真库补 raw 输出；本文件无假 EXPLAIN
- 租户态 `update(CapabilityAsset)` 豁免前后 rowcount（0 → 1）
- 安装表 **不在** 豁免清单：租户态 UPDATE 注入 `tenant_id`
- 配额 COUNT 含/不含 marketplace；出站未绑定 0 行
- D22b 回填后公开无 `expert` 字面量（或映射到 agent 且 uq 未改）
- `up → down → up` 每条迁移退出码 0（S3 之后，本帽不跑）
- `listed_at` DATETIME(6)：GWT-37.6 MYSQL_FIDELITY=1；SQLite 同测已绿；fsp=0 截到秒并四舍五入。隔离库 `aa_qc_cond2_039_*` 验证 039↔038，禁止打业务库
- 生产禁止 `downgrade 037` / `downgrade base`（037 down 先 index 再 FK 的债不在本票）

## 10. 开放问题

仅 **dba 仍开放**。不回答 Q-VOICE / Q-PRICE / Q-RELAY / Q-MARKET-USER / Q-BILL / Q-AGPL。Q-LLM 已关。Q-LISTED-AT / Q-IDEM 合同已锁，不重开。

| 问题 | 阻塞什么 | 需要谁定 |
|---|---|---|
| **Q-PLACE**：入站占位是否就是 `slug=platform`，还是单独 inbound 租户（并发/配额分账）？本 IR **默认 platform、不建第二租户** | 否（有默认） | /pm 若要分账再开实体 |
| **Q6**：`origin_ref` 256 是否够深？默认 256，加宽非破坏 | 否 | /architect（适配器） |
| **Q2**：PR1 结束到第一次 src_sync，存量 `sdlc-workflow` 保持 `writable=1` 是否可接受？ | 否（窗口期） | /pm |
| **Q7**：`(tenant_id, content_hash)` 是否 UNIQUE？**不要用 030 pyc** | 否 | /pm |
| 脏库是否 stamp 过 028–030 | 部署，非设计 | /sre stamp 回 027 |
| `gateway_ref` 字符串内部结构（model vs deployment vs key 前缀） | 否：列是不透明 VARCHAR(191)；T-18 写入约定 | /backend 与网关 ID 对齐；加宽非破坏 |
| 90 天事件归档作业归属 | 否 | /sre + /backend 实现帽 |

## 11. TENANT_EXEMPT_TABLES（隔离契约，与 DDL 同 PR）

今日清单：`tenants`, `system_configs`, `channel_events`, `channel_probe_results`, `operation_logs`, `skills`, `skill_reviews`, `skill_jobs`, `llm_provider_models`。**缺** `capability_assets`（有 `tenant_id` 恒 NULL、非 Mixin）→ Core UPDATE 0 行（PIT-3）。

**目标清单（波次追加，夹具同 PR）**：

| 波 / 票 | 加入 | 理由 |
|---|---|---|
| Wave 0 T-04 | `capability_assets` | **功能必需**（恒 NULL）。不要加 TenantMixin |
| Wave 0 T-04 | `capability_plugins`, `capability_experts`, `capability_teams` | 防御性（无 tenant 列） |
| Wave 0 T-12 | `product_events` | `tenant_id` 是事件主语可 NULL；非 Mixin；不豁免则租户态 UPDATE 注入会打不中匿名行，且「有列⇒Mixin或豁免」S4 会红 |
| Wave 1 T-21 | `capability_commands`, `capability_components` | 平台目录/边；tenant 恒 NULL 或无列 |
| Wave 1 T-29 | `capability_sources` | 平台源 |
| Wave 1 T-33 | `capability_aliases` | 平台 alias |
| **禁止任何票** | `capability_installs` | T-25 写死：TenantMixin 且 **不得**出现在本清单 |

`PLATFORM_SHARED_READ_TABLES` 仍仅 `llm_providers`。本特征不把目录表改成共享读（目录不是租户可见公共行语义；公开走单独读模型）。

R13 不扫「有列无 Mixin 未豁免」——夹具必须显式覆盖新表。

## 12. gateway_ref 计划（Wave L，给 T-18/T-19）

```
今日：channel_events.channel_id / channel_probe_results.channel_id = BIGINT new-api PK
目标：稳定字符串身份（模型 / deployment / key）
本特征路径：ADD COLUMN gateway_ref VARCHAR(191) NULL
            + idx (gateway_ref, created_at)
禁止：一票 ALTER channel_id 类型；禁止 backend 持 LITELLM.DB_DSN；禁止 Prisma 表进 Alembic
```

双读：`gateway_ref IS NOT NULL` → 用字符串；否则若 `channel_id <> 0` → 用十进制字符串；`channel_id=0` 且 ref NULL = 脏行，读路径跳过/记错误，禁止当成 new-api 0。

双写：新行必写 `gateway_ref`；无 new-api PK 时 `channel_id=0`。旧调度仍写 BIGINT 时同时填 ref（能映射则填，不能则只写 id，ref 留 NULL 等回填）。

回填：独立可重跑脚本，`WHERE gateway_ref IS NULL AND channel_id <> 0` 设为 `CAST(channel_id AS CHAR)`。不进迁移。校验：新代码路径写入 ref NOT NULL。

Redis：见 §6 双读顺序。表列由本 IR 锁定；T-18/T-19 **禁止**改列类型。

收缩（改类型/丢 `channel_id`）= 另开特征的 3 迁移，不在 T-18/T-19/本 IR。

## 13. 给下游

| 给谁 | 内容 |
|---|---|
| `/backend` | 按 `schema.dbml` 建 ORM（`/new-model`）；禁手写迁移 SQL；豁免与夹具同 PR；安装表 Mixin 禁豁免；入队显式 `tenant_id`；consumer 禁止 NULL；候选谓词；出站配置绑定 |
| `/qa` | §2.1 负向；NULL vs `[]`；豁免 rowcount；安装表注入方向相反；上海切日；D22b 后无公开 `expert`；gateway_ref 双读；事件无租户查询面 |
| `/sre` | 头=039；脏库 stamp；LiteLLM PG 不进本链；S4 需 MYSQL_FIDELITY；小表秒级 DDL；生产禁止 downgrade past 037 |
| `/architect` | 本文件即 §8 落地；五新表+事件表+gateway_ref 加列 |

---

Contract check: entities, uniqueness, Top-N presumed indexes, gateway_ref expand, exempt list, Redis name+TTL+invalidation, expand-contract, no handwritten SQL.
