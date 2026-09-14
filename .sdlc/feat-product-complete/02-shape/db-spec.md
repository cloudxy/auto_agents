# db-spec · feat-product-complete

> 上游：PRD `.sdlc/feat-product-complete/01-define/spec.md` **v1.5**（Wave C 50/51/60/61/87 + Wave U 80…90/92 + **Wave A 93…105**；不含 FR-91）｜方案 `02-shape/contract.md` **v2 §8**｜ADR-0019/0020/**0023**
> 下游：`schema.dbml` → Alembic **autogenerate**（禁手写 SQL）→ `/backend` ORM
> 泳道：L4｜作者：/dba｜日期：2026-09-11｜**版本 v2.1（shape r2 附条件微修：QA-02 读路径对齐 contract §7.4/ADR-0019 v2、QA-06 notifications.user_id 口径，见 §17；无 DDL 变化。v2=shape r1 扩展：并入 Wave A；v1 结构与 C/U 决策原样保持，Wave A 织入并标 `[Wave A]`；六点机制决策见 §16）**
> **扩不是从零：** 018c369 / Alembic **040** 已有 `plans` / `tenant_subscriptions` / `orders` / `relay_groups` / `relay_tokens`。本 IR 是增量，不替换 v2 `feat-four-pillars-v2/02-shape/db-spec.md`。
> 已有表 IR：DBML = **040 live 全列** ∪ 本波加列。禁止「看起来像全表的 stub」。漏 live 列 = autogenerate **DROP**，不是 expand。
> Alembic 头（本特征目标）：**040 → 041（C/U 加法：outbound_keys + relay 两列）→ 042 [Wave A]（users 唯一键在册化）→ 043 [Wave A]（asset_import 两表）**（实现票 autogenerate，本帽不写 `backend/alembic/`）。生产 **禁止 downgrade past 037**（039/040 已记；本特征延续）。
> 环境事实（2026-09-11 实测）：本机库 `alembic current=039`（040 对齐=交付清单，/sre）；relay 表不在本机 → 040 表集以迁移文件为部署事实源。EXPLAIN 取证（§5）在 039 本机库完成（users/alert_rules/tenants 在场）。
> **LiteLLM Postgres 不进本 Alembic / 不进 `platform_core/models`。** 禁止 `LITELLM.DB_DSN`。禁止复活 028 `api_keys` / 029 billing pyc。

## 0.0 expand-only vs 新表

| 对象 | 判定 | 本波动作 |
|---|---|---|
| `outbound_keys` | **新表** | 一行一把本企业出站拉数钥匙。禁止与 `relay_tokens` 混表、禁止加 `kind` 列兼用（ADR-0020） |
| `relay_tokens` | **expand-only** | ADD 可空 `gateway_key_id` + `spend_synced_at`。**禁止**改 `key_hash` 类型/长度。`used_tokens` 列已在 040，本波定义写点 |
| `orders` | **expand-only（无加列）** | 040 列保持。本波开始写入 `idempotency_key`。不建 pending 部分唯一（见 §3） |
| `tenant_subscriptions` / `plans` / `relay_groups` | **不动 DDL** | 订阅 UNIQUE(tenant_id) 已是「两张确认不叠档」的库级底；价目/组无本波列变更 |
| `product_events` | **expand-only（无加列）** | 只追加 `event_name` 合法值五件；不改 WACT；不建仓 |
| `capability_assets` 种子 | **不进 schema** | 无 `is_seed` 列；公开 listed 过滤走治理/同步 + 查询谓词（见 §0 非实体） |
| `users.email` | **不动 DDL** | 已全局 UNIQUE；FR-83 是查找路径，不是加列 |
| LiteLLM `keys` / spend 表 | **禁止** | 外部 PG；本库只存不透明 `gateway_key_id` 字符串 |
| 040 `*.tenant_id` 可空 → NOT NULL | **本波不做** | 破坏性（加 NOT NULL）。新表 `outbound_keys.tenant_id` 从一开始 NOT NULL。040 收紧另开 expand-contract，不搭本波 |
| `users` 唯一键 **[Wave A]** | **唯一键换防（放松方向）** | 042：`alive_flag` VIRTUAL 生成列 + 两新键 `(tenant_id, username, alive_flag)` / `(email, alive_flag)`，撤旧两键。机制沿 025 先例（capability_assets 在用），见 §16.1/§8 |
| `tenants` **[Wave A]** | **不动 DDL** | FR-94/95：slug 守卫（应用层单点）+ name/status 纯 UPDATE；平台租户种子已在（024；本机实证 id=5 slug='platform' name='平台租户'），无迁移无回填，见 §16.2 |
| `asset_import_batches` / `asset_import_items` **[Wave A]** | **新表（043）** | FR-100 / ADR-0023。平台级（tenant_id 恒 NULL，必须登记豁免）；沙箱是文件系统不是库表，见 §16.5 |
| `capability_assets` **[Wave A]** | **复用零扩列** | 导入幂等键=类型+名称即既有 `uq_asset_type_name_alive`；provenance 经 items.asset_id 回放。不加 origin 列，见 §16.5 |
| `alert_rules` / `notifications` **[Wave A]** | **不动 DDL** | FR-105 queue_depth：读规则行评估；命中记录=notifications 行（type='alert'，resource_type='alert_rule'）+ `last_triggered_at` 静默窗，见 §16.6 |
| `spider_tasks.tenant_id` **[Wave A]** | **不动 DDL** | FR-102 平台租户入队=既有列传递 + actor 解析 fail loud，见 §16.4 |

---

## 0. 实体与粒度（建模第一步的产出）

| 实体（表名） | 一行代表什么 | 来源 FR | 别名归并 |
|---|---|---|---|
| `outbound_keys` | 一把本企业出站拉数钥匙（hash 行；明文不落库） | FR-51；ADR-0020 | 「出站钥匙」「拉数钥匙」；**不是**渠道组令牌、**不是**平台 master |
| `orders` | 一次线下升级申请 | FR-50 | 「单」「升级申请」；本波无在线单 |
| `relay_tokens` | 一把渠道组令牌（hash 行 + 网关虚拟 Key 引用） | FR-60；ADR-0019 | 「渠道组令牌」；**不是**出站钥匙 |
| `relay_groups` | 一个租户渠道组 | FR-60（已有） | 本波不加列 |
| `plans` | 一条公开价目档 | FR-50.13/50.14 | 公开仅 free/pro；本波无企业档 SKU 行 |
| `tenant_subscriptions` | 一企业当前订阅（一企业一行） | FR-50.16 不叠档 | 不是订单 |
| `product_events` | 一次已发生的产品事实（追加） | FR-92 | 本波只加事件名（v2 追加 `user_restored` / `asset_imported`，GWT-92.8/92.9） |
| `users` **[Wave A]** | 一个租户内的一个用户账号（含软删态：在册/已删除） | FR-93（83/94 触及） | 「账号」「成员」；软删行不再永久占 username/email |
| `tenants` **[Wave A]** | 一家企业；平台租户=slug `'platform'` 种子行 | FR-94/95/102 | 「平台默认企业」=「平台租户」（§0.4 命名收口；AutoAgents 是站点名不是租户） |
| `asset_import_batches` **[Wave A]** | 一次能力资产导入（含部分成功） | FR-100 | 「导入批次」 |
| `asset_import_items` **[Wave A]** | 一次导入中一个条目的处置结果 | FR-100 | 「导入明细」；provenance 回放入口 |
| `alert_rules` **[Wave A]** | 一条告警规则（TenantMixin） | FR-105 | queue_depth 已在 rule_type 值域 |
| `notifications` **[Wave A]** | 一条站内通知（复用为告警命中记录载体） | FR-105 | 「命中记录」不建第二张表 |

**粒度必须能用一句话写出来。**

**被判定为「不是实体」的名词**：

| 名词 | 判定 | 理由 |
|---|---|---|
| 订单状态 pending/paid | 字段 | `orders.status`；本波无取消（040 列 `cancelled` **保留不写**） |
| 出站/令牌「已签发/已吊销」 | 字段派生 | `revoked_at IS NULL` → active；非空 → revoked。不另建 status 列 |
| 出站明文 | 不落库 | 只在签发响应出现一次；再进页只见 prefix |
| `KEY_BINDINGS` | 配置绑定 | 已兑 FR-13；查找 **先** `outbound_keys` **再** 配置。不建表、不进 Alembic |
| 平台共享 `/spider/status\|results\|stats` 钥匙 | 配置 | spec §5 本波不租户化；禁止收进 `outbound_keys` |
| 测试种子 | **不进 schema、进治理/同步** | 可观测定义在 `name`/`title`/`description`（GWT-80.1）。不加 `is_seed` / `is_fixture` 列（见 §13） |
| LiteLLM Key / spend / 模型 | 外部引用 | `gateway_key_id` 不透明字符串；禁止 Prisma/PG 表 |
| `_apply_plan` 配额履约 | 骨架副作用 | Q-PRICE 未关；不升级成完成条件，也不为「去掉履约」加列/迁掉 |
| 金额「元」 | 展示 | 库内继续 `amount_cents`（分）；GWT 对用户是元 |
| 公开页大小 ≤20 | 查询闸 | 无 DDL |
| 导入沙箱目录 **[Wave A]** | **文件系统，不是库表** | ADR-0023：解包在临时沙箱目录（大小/条目数/耗时上限来自配置，NFR-10）；路径规范化后越界条目拒绝、资产目录外零新文件（GWT-100.7）。库内只有批次/明细行回放结果 |
| 平台租户身份 **[Wave A]** | 现有 `tenants` 行 | FR-102 无新表：actor 解析点把平台超管映到 slug='platform' 行；种子行缺失=配置错误 fail loud，不静默回退 None、不临时建租户 |
| 告警命中记录 **[Wave A]** | `notifications` 行 + `alert_rules.last_triggered_at` | 「谁/何时/深度」=规则身份（resource_type='alert_rule'，resource_id）+ 时刻 + content 文本；静默窗=now-last_triggered_at<window。不建 `alert_hits` 第二张表 |
| 种子 admin 不可删 / 平台租户三名保护 **[Wave A]** | 应用层守卫 | `delete_user` 单点 + tenant 写服务单点；无 DDL、无 `is_protected` 列（§16.2） |
| demo 爬虫 / 源码清单混入 **[Wave A]** | 读侧分流 | FR-104 是 registry 查询谓词；爬虫与文件本身不删（GWT-104.2 本波无独立入口） |

**FR 覆盖核对**：

| FR | 涉及实体 | 承载字段 | 缺口 |
|---|---|---|---|
| FR-50 | `orders` / `plans` / `tenant_subscriptions` | 企业、档、金额分、pending\|paid、channel、`paid_at`、`idempotency_key` | 无新列；写规则 + 唯一策略见 §3 |
| FR-51 | `outbound_keys`（新） | hash、prefix、`revoked_at`、签发者、`tenant_id` NOT NULL | 无表 → 本波新建 |
| FR-60 | `relay_tokens` expand | `used_tokens`（已有）谁写；`gateway_key_id`；吊销 `revoked_at` | 缺网关引用列 → ADD |
| FR-61 | `channel_probe_results` | 已有 `verdict`；无本波 DDL | 无 |
| FR-80/81 | `capability_assets` | listed 谓词 + 种子残差谓词；无新列 | 无 |
| FR-83 | `users` | `email` 已全局 UNIQUE | 无 DDL |
| FR-87/82/84/85/88/89/90 | 无新表 | 文案/菜单/软删已有 | 无 |
| FR-92 | `product_events` | 五件 `event_name` 字面量 | 无 DDL |
| FR-91 | — | 本轮不冻结 | 无 |
| FR-93 **[Wave A]** | `users` | **042 唯一键在册化**（alive_flag）；恢复=UPDATE 置 NULL，竞态由约束兜底（§16.1） | 唯一键换防 → 本波迁移 042 |
| FR-94 **[Wave A]** | `tenants` / `users` | slug 守卫 + `delete_user` 种子守卫（应用层单点） | 无 DDL |
| FR-95 **[Wave A]** | `tenants` | name/status 纯 UPDATE；改名冲突域应用层判定 | 无 DDL |
| FR-96/97/98/99 **[Wave A]** | — | 布局/文案/呈现；98 只读 channel_events/probe | 无 DDL |
| FR-100 **[Wave A]** | `asset_import_batches`/`items`（新）+ `capability_assets` 复用 | §1 字典；幂等=既有 `uq_asset_type_name_alive` | 新表 → 本波迁移 043 |
| FR-101 **[Wave A]** | `capability_assets` | `asset_type` 值域已含 `agent`（ASSET_TYPES 七类） | 无 DDL |
| FR-102 **[Wave A]** | `spider_tasks.tenant_id` | 既有列传递；配额按平台租户执法 | 无 DDL |
| FR-103 **[Wave A]** | `spider_task_templates` | 既有列，定义字段编辑面扩容归应用层 | 无 DDL |
| FR-104 **[Wave A]** | — | registry 读侧分流 | 无 DDL |
| FR-105 **[Wave A]** | `alert_rules` + `notifications` | 读行评估 + 命中载体 + `last_triggered_at` 静默窗（§16.6） | 无 DDL |

### 0.1 建模决策记录（有取舍的才写）

| 决策 | 选了什么 | 备选 | 理由 |
|---|---|---|---|
| 出站凭证 | **新表** `outbound_keys` | `relay_tokens.kind` / 复活 028 `api_keys` / 只写 `KEY_BINDINGS` | ADR-0020：生命周期与登记目标不同；混表必 `if kind` 泄漏；028 禁止复活 |
| 出站明文 | 不落库；只存 SHA-256 hex + prefix | 密文列 / 配置树 | NFR-04；与 `relay_tokens` 同构但 **查找集合不相交** |
| 出站 `tenant_id` | NOT NULL；TenantMixin；**禁止豁免** | NULL=平台 | PIT-4 / 017；禁止 NULL=平台 |
| 令牌打网关 | expand 加 `gateway_key_id` VARCHAR(191) NULL | 改 `key_hash` 类型 / 连网关 PG | ADR-0019；合同锁：expand 加列，禁止一票改 hash |
| `used_tokens` 金标 | 网关 spend/key info HTTP；本地列=缓存 | 本库自增 / 读网关 PG | 租户直打 chat，backend 看不见每次调用 |
| 一企业一张 pending | **不建** 部分 UNIQUE | 生成列 `pending_guard` UNIQUE | GWT-50.16 夹具允许两张 pending；部分唯一会挡住夹具。入口用事务锁 `tenants` 行 + COUNT；`idempotency_key` UNIQUE 挡重试 |
| 两张确认不叠档 | `uq_tenant_subscriptions_tenant` + `_apply_plan` **赋值**不是累加 | 新列 `quota_applied_at` | 一企业一行订阅已防两行；再加「已履约」列会把 Q-PRICE 履约写成完成条件。本波不加该列 |
| 订单金额 | 下单时快照 `amount_cents`（已有） | 每次 JOIN `plans.price_cents` | 价目改价不得改历史申请金额（当时） |
| 测试种子 | **无列** | `is_seed TINYINT` | 可观测定义已在三列文本；加列会把试卷身份写进生产模型 |
| 主键 | INT AUTO_INCREMENT 跟仓 | BIGINT | 与 040 / v2 诊断一致 |
| 时间 | 新表 naive DATETIME 存 UTC；040 列保持 `DateTime(timezone=True)` 映射 DATETIME | 本波改 040 时区类型 | 改类型破坏性；不混用 TIMESTAMP |
| 枚举 | 物理 VARCHAR + 应用校验 | MySQL ENUM | 改值要 DDL |
| 软删 | 出站/令牌/订单 **不加** | 吊销当软删 | 吊销是终态审计；行留；UNIQUE 不带 deleted_at |
| 出站明文前缀 | IR **只禁** `sk-`（ADR-0020） | 冻死 `ok-` 为产品名 | 产品名是「出站拉数钥匙」不是前缀字面量；实现票选非 `sk-` 前缀 |
| users 软删占用/释放（QA-03）**[Wave A]** | **`alive_flag` 虚拟生成列进唯一键**（025 既定机制推到 users） | ①纯判定事务 ②物理删除已删行 ③email 改 NULL+时间戳 | MySQL 8 无部分唯一索引；025 已用同款生成列给 5 张表落地（capability_assets 在用）。①挡不住「判定通过→并发插入→恢复覆盖」竞态；②③断审计链，合同 §8 明令禁止。恢复正确性由 DB 约束兜底（§16.1） |
| 平台租户保护 **[Wave A]** | **slug 守卫**收口在 tenant 写服务单点；种子 admin 守卫在 `delete_user` 单点 | 新列 `is_protected` + 回填 | slug 全局唯一且不可改（025 冻结「slug 是对外路由标识，删除=注销不复用」）；`is_protected` 恰好只有一行有意义、无读模式、消不掉 actor 解析/蓝图排除处的 slug 字面量——零查询收益的迁移成本。**无迁移、无回填**：种子已在（024 幂等 INSERT；本机实证 id=5、name='平台租户' 与 spec §0.4 一致） |
| 导入资产落位 **[Wave A]** | **capability_assets 复用，零扩列**；provenance 经 `asset_import_items.asset_id` 回放 | origin 扩列（source_id/origin_ref 加值域/新列） | origin_* 服务 capability_sources 外部树（URL/扫描通道）；一次性本地上传不是源树。幂等键=类型+名称即既有 `uq_asset_type_name_alive`，目录表不感知通道（§16.5） |
| 导入明细载体 **[Wave A]** | **子表** `asset_import_items`（逐条 succeeded/failed/skipped+中文原因） | 批次行 JSON 列 | 明细要按批查询、逐条呈现（T-36）、状态过滤——查询面不进 JSON（JSON 只放非查询属性） |
| 告警命中记录 **[Wave A]** | `notifications` 行 + `last_triggered_at`（静默窗兼最近命中） | 新表 `alert_hits` | 规则表配置量级；命中频次被静默窗节流；「在规则处可见」=规则详情按 resource_type/resource_id 关联，无第二张表增长面（§16.6） |
| 企业改名冲突域 **[Wave A]** | 应用层判定（既有企业名 ∪ 保留名「平台租户」∪ AutoAgents） | `tenants.name` DB 唯一键 | 保留名不是行（AutoAgents 无租户行），DB 唯一表达不了；tenants 软删行也不该占名。收口在写服务单点 |

时区：存 UTC（naive DATETIME）。用量与近 7 日切日同一套 Asia/Shanghai。新列不混用 `TIMESTAMP`。

---

## 1. 数据字典

物理类型：金额继续 INT 分（040）；布尔 TINYINT(1)；枚举 VARCHAR；JSON 仅非查询灵活属性。时间列 DATETIME。可空字段必须写 NULL 语义。

### outbound_keys（新表）

一行 = 一把本企业出站拉数钥匙。TenantMixin。**禁止**进 `TENANT_EXEMPT_TABLES`。明文不落库。

| 字段 | 类型 | 可空 | 默认 | 说明 / 为什么是这个类型 |
|---|---|---|---|---|
| `id` | INT | 否 | AUTO_INCREMENT | 代理主键（跟仓） |
| `tenant_id` | INT | 否 | — | 隔离列；017 风格 NOT NULL。NULL 语义不存在（禁止平台钥匙） |
| `name` | VARCHAR(64) | 是 | NULL | NULL=未起名；列表主展示仍是 prefix。不进唯一键 |
| `key_prefix` | VARCHAR(16) | 否 | — | 再进页可见的前缀。应用保证 **不以 `sk-` 开头** |
| `key_hash` | VARCHAR(64) | 否 | — | SHA-256 hex（64）。明文只在签发响应。查找用 compare_digest |
| `issued_by_user_id` | INT | 否 | — | 签发者。引用当时用户；**不加 FK**（用户可删，钥匙要留） |
| `revoked_at` | DATETIME | 是 | NULL | NULL=active（可拉数）；非空=已吊销（不可再拉）。终态，禁止清回 NULL |
| `created_at` | DATETIME | 否 | CURRENT_TIMESTAMP | 签发时刻（业务时间≈记录时间） |
| `updated_at` | DATETIME | 否 | CURRENT_TIMESTAMP | 吊销时更新 |

**可空性**：`name` NULL=未起名；`revoked_at` NULL=仍有效。其余 NOT NULL。

**类型选择**：`key_hash` VARCHAR(64) 与 `relay_tokens.key_hash` 同形，但 **不得** 当同一查找集合。出站拉数先查本表，未命中再查 `KEY_BINDINGS`；**永不** JOIN/IN `relay_tokens.key_hash`。

禁止列：plaintext、kind、gateway_key_id、used_tokens（那些是渠道组平面）。

### orders（040 live；本波不加列）

一行 = 一次升级申请。

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | INT | 否 | AUTO_INCREMENT | 代理主键 |
| `tenant_id` | INT | 是 | NULL | **040 live 可空**。业务上申请必有企业；本波写路径必填。NULL=骨架脏行，读路径当缺失拒绝。本波 **不** ALTER NOT NULL |
| `plan_id` | INT | 否 | — | FK → `plans.id`。档位引用（现在） |
| `amount_cents` | INT | 否 | — | **快照**（当时标价，分）。公开展示换算元。禁止 FLOAT |
| `status` | VARCHAR(16) | 否 | `pending` | 本波写 `pending` / `paid`。040 含 `cancelled`：**本波应用不写**；保留列，不 DROP |
| `channel` | VARCHAR(16) | 否 | `offline` | 只有 `offline` 可产生行。`alipay`/`wechat` **零新行**（含不产生 pending） |
| `idempotency_key` | VARCHAR(64) | 是 | NULL | 040 UNIQUE。NULL=尚未写入的骨架行（MySQL UNIQUE 允许多 NULL）。本波入口 **必写**（UUID 或 `offline:{tenant_id}:{uuid}`，付费后可再申请故 **禁止** 永久 `{tenant}:{plan}`） |
| `paid_at` | DATETIME | 是 | NULL | NULL=未确认。确认时刻（业务时间）。报表/「已确认」用这个，不是 `created_at` |
| `created_at` | DATETIME | 否 | CURRENT_TIMESTAMP | 申请写入时刻 |

无 `updated_at`（040 无）。本波不补（非 Top-N、非完成线）。

### relay_tokens（040 live ∪ 本波加列）

一行 = 一把渠道组令牌。

**已有列保持**（040；DBML 必须逐列写出）：`id`, `tenant_id`（live 可空，写路径必填，本波不收紧）, `group_id`, `name`, `key_prefix`, `key_hash`（VARCHAR(64) UNIQUE，**禁止改类型**）, `quota_tokens`, `used_tokens`, `expires_at`, `revoked_at`, `last_used_at`, `created_at`, `note`。

**本波 ADD（接表尾）**：

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `gateway_key_id` | VARCHAR(191) | 是 | NULL | LiteLLM 虚拟 Key 稳定引用（不透明）。NULL=040 骨架签发、从未登记网关的行。新签发应用必写。**不是** DSN、**不是** master |
| `spend_synced_at` | DATETIME | 是 | NULL | 最近一次成功把网关 spend 写入 `used_tokens` 的时刻。NULL=从未同步（骨架 `used_tokens` 恒 0） |

`used_tokens`：INT NOT NULL default 0。**本地缓存**，不是金标。谁写见 §12。

`revoked_at`：NULL=可打网关；非空=已吊销（QA-20 再打拒绝）。禁止清回 NULL。

### relay_groups / plans / tenant_subscriptions（040 live；不加列）

跟 040。要点：

- `plans.slug` UNIQUE；公开种子 `free` / `pro`。`quota_json` 专业档三数字与定价页同一套（GWT-50.13 夹具企业已在专业档，不是确认履约）。
- `plans.is_public`：本波企业档 **无行**。
- `tenant_subscriptions.tenant_id` UNIQUE `uq_tenant_subscriptions_tenant`：一企业一行。
- `relay_groups` UNIQUE `(tenant_id, name)`。GET 路径 **禁止** insert default（T-07；无 DDL）。

### product_events（已有；不加列）

`event_name` VARCHAR(64) 已够。本波追加合法值（蓝图原样，禁止改名）：

`offline_order_submitted` · `offline_order_confirmed` · `outbound_key_issued` · `relay_token_call_succeeded` · `market_list_paged`

`props` 非查询：档位名、page、result_count。**禁止**明文钥匙、密码、master。`market_list_paged` 访客 `tenant_id` NULL，必带 `anonymous_id`。v1 无幂等 UNIQUE（至少一次，允许重复）。

**[Wave A] v2 追加字面量**（GWT-92.8/92.9）：`user_restored`（含 tenant_id、restored_user_id；不含密码/明文）· `asset_imported`（含 origin、types、succeeded、failed）。

### users（live 表，本特征唯一键换防 + 一列生成列；其余列全保持）

一行 = 一个租户内的一个用户账号（含软删态）。既有列集：`id`, `username`, `email`, `password_hash`, `is_active`, `is_admin`, `role`, `tenant_id`（NOT NULL=024）, `tenant_role`, `is_platform_admin`, `deleted_at`, `department_id`, `last_login_at`, `created_at`, `updated_at`。

**本特征 ADD（042）**：

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `alive_flag` | SMALLINT | 是（生成） | — | `GENERATED ALWAYS AS (CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END) VIRTUAL`。存活=1 参与唯一；已删=NULL 脱离唯一（MySQL 唯一索引不对含 NULL 行判重）→ 已删行释放 username（同租户口径）/email（全局口径），GWT-93.5/93.7 |

**唯一键换防（042）**：撤 `uq_users_tenant_username`、唯一键 `` `email` ``（001 部署自动名，本机 SHOW CREATE 实证）、`ix_users_email`（与唯一键纯重复，026 口径不恢复）；建 `uq_users_tenant_username_alive (tenant_id, username, alive_flag)` 与 `uq_users_email_alive (email, alive_flag)`。`ix_users_username` 保留（跨租户 username 消歧，UserRepository.get_by_username R13 单点；不被新键覆盖）。

**ORM 对齐（下游票）**：`platform_core/models/user.py` 加 alive_flag 生成列声明并换唯一约束名——`capability_assets.py` L58 同款写法可抄。

### asset_import_batches（新表 043，Wave A）

一行 = 一次导入（含部分成功）。平台级表。

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | INT | 否 | AUTO_INCREMENT | 代理主键（跟仓） |
| `origin` | VARCHAR(16) | 否 | — | `file` / `directory`（GWT-92.9 同字面量） |
| `status` | VARCHAR(16) | 否 | `running` | running → completed（含部分成功）/ failed（整批失败）。应用层校验 |
| `total_count` | INT | 否 | 0 | = succeeded+failed+skipped；批结束写一次（非增量维护，无漂移） |
| `succeeded_count` | INT | 否 | 0 | 同上 |
| `failed_count` | INT | 否 | 0 | 同上 |
| `skipped_count` | INT | 否 | 0 | 幂等跳过条目（GWT-100.8：目录已有行不产生第二行） |
| `created_by` | VARCHAR(64) | 是 | NULL | 操作者用户名；NULL=系统路径（预留）。仅平台超管可导入（GWT-100.6） |
| `tenant_id` | INT | 是 | NULL | 平台级恒 NULL——**模型禁 TenantMixin 且必须登记 TENANT_EXEMPT_TABLES**（PIT-3；与 product_events 同款同 PR） |
| `created_at` | DATETIME | 否 | CURRENT_TIMESTAMP | 批开始（记录时间） |
| `finished_at` | DATETIME | 是 | NULL | 批结束（业务时间）；NULL=未结束 |

### asset_import_items（新表 043，Wave A）

一行 = 一次导入中一个条目的处置结果。

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | INT | 否 | AUTO_INCREMENT | 代理主键 |
| `batch_id` | INT | 否 | — | FK → asset_import_batches.id，**CASCADE**（明细=批的组合子行，无独立生命周期；capability_plugins 同款。批无删除入口，CASCADE 只为孤儿防御） |
| `asset_type` | VARCHAR(16) | 否 | — | `skill`/`agent`/`command`/`plugin`；类型由导入过程判定（GWT-100.4），四类齐=agent 通道补齐 |
| `name` | VARCHAR(128) | 否 | — | 资产目录名（与 capability_assets.name 同宽同语义=幂等键组件） |
| `status` | VARCHAR(16) | 否 | — | `succeeded` / `failed` / `skipped`（应用层校验） |
| `reason` | VARCHAR(512) | 是 | NULL | 中文失败原因（GWT-100.2/100.3/100.5/100.7：不合法/超大/路径逃逸）；NULL=成功或跳过无需原因 |
| `asset_id` | INT | 是 | NULL | 成功时 FK → capability_assets.id（**RESTRICT**，保回放链）；NULL=失败/跳过。**provenance 回放入口**：资产 ← 哪次导入来的 |
| `created_at` | DATETIME | 否 | CURRENT_TIMESTAMP | 记录时间 |

**两表均不加软删**（审计/子表，豁免矩阵）。

---

## 2. 关系与基数

| 关系 | 基数 | 外键位置 | 可空 | 级联行为 | 说明 |
|---|---|---|---|---|---|
| tenants → outbound_keys | 1:N | `outbound_keys.tenant_id` | 否 | **无 FK**（跟 040 orders/relay：隔离靠 Mixin，不 FK tenants） | 删除企业前应用先吊销/归档钥匙 |
| users → outbound_keys（签发者） | 1:N | `issued_by_user_id` | 否 | 无 FK | 审计留 |
| tenants → orders | 1:N | `orders.tenant_id` | 是（live） | 无 FK | 写路径当 NOT NULL |
| plans → orders | 1:N | `orders.plan_id` | 否 | RESTRICT | 有申请的档不可物理删 |
| plans → tenant_subscriptions | 1:N | `plan_id` | 否 | RESTRICT | |
| tenants → tenant_subscriptions | 1:1 | UNIQUE tenant_id | 是（live） | 无 FK | |
| tenants → relay_groups | 1:N | `tenant_id` | 是（live） | 无 FK | |
| relay_groups → relay_tokens | 1:N | `relay_tokens.group_id` | 否 | RESTRICT | 040 已有 FK |
| relay_tokens → LiteLLM Key | 外部 | `gateway_key_id` 无 FK | 是 | — | 禁止 FK 到网关 PG |
| product_events → tenants/users | 引用无 FK | — | 是 | — | 追加审计 |
| tenants → users **[Wave A]** | 1:N | `users.tenant_id`（无 FK，跟仓） | 否 | — | R13 收口；024 已 NOT NULL |
| asset_import_batches → asset_import_items **[Wave A]** | 1:N | `items.batch_id` | 否 | **CASCADE** | 明细=批的子行；批无删除入口 |
| capability_assets → asset_import_items **[Wave A]** | 1:N | `items.asset_id` | 是 | **RESTRICT** | 目录行被明细引用时不随批删；RESTRICT 保 provenance 回放链 |
| alert_rules → notifications（逻辑）**[Wave A]** | 1:N | `resource_type='alert_rule'` + `resource_id`（无 FK，既有列） | — | — | 命中记录逻辑关联（§16.6） |

默认 RESTRICT。删除逻辑放应用层。

### 2.1 状态流转

```
orders.status（本波）：

（无单）──负责人/公司管理员提交 offline──> pending ──超管确认收款──> paid
在线渠道 ──不 insert──> （无新行；原 pending 若有则保持）
已有 pending 再提交（正常入口）──不 insert──> 原 pending 保持

终态：paid（确认收款不可逆）
本波无取消、无退款。040 cancelled 字面量保留，应用不转入。
```

| 流转 | 触发条件 | 谁能触发 | 副作用 |
|---|---|---|---|
| 无单 → pending | channel=offline 且档=公开付费档（本波 pro） | 负责人、公司管理员 | 本企业多一条；配额不变；写 `idempotency_key`；事件 `offline_order_submitted` |
| pending → paid | 确认收款 | **仅**平台超管 | `status=paid`、`paid_at=now`。不可逆。事件 `offline_order_confirmed`。骨架可 `_apply_plan`（**不是** FR-50 Then） |
| paid → 再确认 | 超管再点 | 超管 | 保持 paid；不新开单；`_apply_plan` 再走也是 SET 同一档，不叠档 |
| 在线渠道 | alipay/wechat | 负责人、公司管理员 | **零新行** |

**非法流转**（交 `/qa`）：

| 非法 | 期望 |
|---|---|
| 租户确认 pending | 保持 pending；配额不变 |
| 只读/经办提交 | 不产生行 |
| paid → pending | 保持 paid |
| 免费档 / 企业档（无 SKU）下单 | 不产生行 |
| 正常入口第二张 pending | 不产生行；`ORDER_PENDING_EXISTS` |
| 夹具两张 pending 都确认 | 两张均为 paid；订阅仍一行；配额不因第二张再叠一档 |

```
outbound_keys 生命周期（无 status 列）：

（无）──签发──> active（revoked_at IS NULL）──吊销──> revoked（revoked_at 非空）
终态：revoked（不可再拉；不可清回 NULL）
```

| 非法 | 期望 |
|---|---|
| 只读签发/吊销 | 不 insert / 不写 `revoked_at` |
| 用 revoked / 未绑定 / 他企业 hash 拉本企业 | 拒绝、0 行 |
| 用 `relay_tokens` 的 sk- 当出站 | 本表与 KEY_BINDINGS 都不命中 → 拒绝、0 行 |
| 出站钥匙打渠道组 Base URL | 网关不认；用量基线不变（非本表） |

```
relay_tokens 生命周期：

（无）──签发（网关 HTTP 成功后 insert）──> active ──吊销──> revoked
终态：revoked（不可再打网关；QA-20）
签发时网关失败 → 不 insert（禁止「列表有、网关无」）
```

| 非法 | 期望 |
|---|---|
| 经办/只读签发或吊销 | 不产生 / 不吊销 |
| 企业 B 改企业 A | 404 同形；A 不变 |
| 清 `revoked_at` | 禁止 |
| 租户改全局熔断 | 无入口；无本表副作用 |

```
users 软删态（[Wave A] FR-93；业务权威=spec §3.1，冲突以 spec 为准）：

active ──平台超管删除──> soft-deleted（deleted_at 非空；alive_flag=NULL，脱离唯一键）
soft-deleted ──平台超管恢复（标识未被在册行占用）──> active（UPDATE deleted_at=NULL）
soft-deleted 的 username/email ──被新建用户占用──> 该已删行恢复被拒（唯一键冲突=占用句，GWT-93.4/93.8）
```

| 流转 | 触发条件 | 谁能触发 | 副作用 |
|---|---|---|---|
| active → soft-deleted | 删除用户（既有软删） | 仅平台超管 | 默认列表不可见；「已删除」筛选可见；标识进入可释放状态 |
| soft-deleted → active | 恢复：`UPDATE … SET deleted_at=NULL WHERE id=? AND deleted_at IS NOT NULL` | 仅平台超管 | rowcount=1 → 回默认列表、状态=启用、上报 `user_restored`；rowcount=0 → no-op（GWT-93.9，不重复上报） |

**非法流转**（交 /qa）：恢复时标识被在册行占用（保持已删+中文占用句，现有用户不变）；非超管删除/恢复（404 同形）；删除种子 admin（拒绝，GWT-94.1——`delete_user` 单点守卫，与「不能删自己」「最后一个超管」并存且判定在前）。

```
tenants 状态（[Wave A] FR-94/95）：

启用 ──超管停用──> 停用 ──超管再启用──> 启用（双向，仅常规企业；GWT-95.2/95.7）
平台租户（slug='platform'）：改名 / 停用 / 删除 三条迁移全部非法（GWT-94.2/94.3/94.4）
```

非法：租户任一角色改企业信息或状态（404 同形）；改名撞保留名「平台租户」/站点名 AutoAgents（应用层拒绝，中文说明）；本波新增企业删除（无入口——将来落地删除前必须先排除平台租户，GWT-94.4 前置冻结）。

```
asset_import_batches.status（[Wave A] FR-100）：

running ──批处理结束──> completed（含部分成功，常态语义）/ failed（整批失败：沙箱/上传层故障）
```

无回退边；GWT-100.3「0 可导入」= completed 且 total_count=0（中性说明，非静默成功非失败句）。

上架三态仍以 v2 为准。本特征只追加：**测试种子即使 listed 也不得出现在公开商店**——查询谓词，不改状态机。

### 2.2 时间字段语义

| 字段 | 类型 | 语义 | 报表口径用哪个 |
|---|---|---|---|
| `orders.created_at` | 记录时间 | 申请写入 | 列表排序 |
| `orders.paid_at` | 业务时间 | 确认收款 | **已确认**判定；PC-3 抽检 |
| `outbound_keys.created_at` | 业务时间 | 签发 | 列表 |
| `outbound_keys.revoked_at` | 业务时间 | 吊销 | 执法：非空即拒 |
| `relay_tokens.revoked_at` | 业务时间 | 吊销 | QA-20 门闩 |
| `relay_tokens.last_used_at` | 业务时间 | 网关侧最近使用（缓存） | 展示 |
| `relay_tokens.spend_synced_at` | 记录时间 | 本地 `used_tokens` 最近一次对账 | 诊断「用量为何仍 0」 |
| `product_events.occurred_at` | 业务时间 UTC | 事件发生 | 超管查询；切日上海 |
| `users.deleted_at` **[Wave A]** | 业务时间 | 删除时刻 | 「已删除」筛选排序键；恢复动作清 NULL |
| `asset_import_batches.finished_at` **[Wave A]** | 业务时间 | 批结束时刻 | 导入耗时审计（finished_at−created_at） |
| `alert_rules.last_triggered_at` **[Wave A]** | 业务时间 | 最近命中时刻（既有列） | 静默窗判定 + 规则处「何时」 |

时区约定：存 UTC。不混用 TIMESTAMP 与 DATETIME（新列）。040 live 列保持。

### 2.3 软删决策

| 表 | 加软删 | 理由 |
|---|---|---|
| `outbound_keys` | 否 | 吊销=终态审计；行留；hash UNIQUE 全局（吊销后也不释放 fingerprint，防重放同一明文） |
| `relay_tokens` | 否 | 同左 |
| `orders` | 否 | 申请史；paid 不可逆 |
| `plans` / `tenant_subscriptions` / `relay_groups` | 否 | 040 已无；本波不补 |
| `product_events` | 否 | 追加审计 |
| `capability_assets` | 已有 | 种子过滤不靠软删 |
| `users` **[Wave A]** | 是（既有保持） | FR-93 恢复语义依赖；042 后软删行不再永久占坑 |
| `tenants` **[Wave A]** | 是（既有保持） | 025 冻结 slug 不复用；本波不碰 |
| `asset_import_batches` / `asset_import_items` **[Wave A]** | **否** | 审计/子表按豁免矩阵 |
| `alert_rules` **[Wave A]** | 是（既有保持） | 治理规则；恢复/收回走既有路径 |

---

## 3. 唯一键

| 唯一约束 | 字段组合 | 业务规则 |
|---|---|---|
| `uk_outbound_keys_key_hash` | `(key_hash)` | 一把明文只对应一行；跨租户也不共享 fingerprint |
| `uk_orders_idempotency_key` | `(idempotency_key)` | **040 已有**。可空。本波入口必写；并发重试靠 UNIQUE 报错当已处理，**先查后插不够** |
| `uq_tenant_subscriptions_tenant` | `(tenant_id)` | **040 已有**。一企业一行当前档。两张 paid 确认不得 insert 第二行订阅 |
| `uq_plans_slug` | `(slug)` | 040 已有 |
| `uq_relay_groups_tenant_name` | `(tenant_id, name)` | 040 已有 |
| `uq_relay_tokens_key_hash` | `(key_hash)` | 040 已有。**不改** |
| `uk_relay_tokens_gateway_key_id` | `(gateway_key_id)` | 本波 ADD UNIQUE。MySQL 多 NULL 合法（骨架行）。新签发非空且不得两行同一网关 Key |
| `product_events` | 无业务唯一键 | 至少一次；允许重复 |
| `outbound_keys (tenant_id)` | **无** | 一企业允许多把（吊销后再签发、多把并存） |
| `uq_users_tenant_username_alive` **[Wave A，042 换防]** | `(tenant_id, username, alive_flag)` | 同租户 username 唯一**只对在册行生效**（GWT-93.5：已删行不阻塞新建；再删再建合法）。最左前缀 (tenant_id, username) 承接旧键查询义务 |
| `uq_users_email_alive` **[Wave A，042 换防]** | `(email, alive_flag)` | email 全局唯一同口径（GWT-93.7）。最左前缀 email 继续服务登录查找（FR-83） |
| `capability_assets.uq_asset_type_name_alive`（既有） | `(asset_type, name, alive_flag)` | 导入幂等键=类型+名称（GWT-100.8）直接复用，零新键 |
| `asset_import_batches` / `asset_import_items` | **无业务唯一键** | 批次=事件流（一次导入天然不重复于"哪一次"）；明细唯一性由 (batch_id, asset_type, name) 业务上成立但不加键——同批同名条目由导入器在批内去重，无并发写方（单调度写者） |

**已评估不建：**

| 候选 | 不建的理由 |
|---|---|
| 生成列 `orders.pending_guard` + UNIQUE(tenant_id, pending_guard) | 会让「同一企业至多一张 pending」成为**行不变量**，挡住 GWT-50.16 夹具两张 pending。该不变量只约束**正常入口**，由事务锁实现（§3.1） |
| UNIQUE(tenant_id, status) on orders | 会只允许一张 paid，与 50.16 两张都确认冲突 |
| 跨表 UNIQUE(outbound.key_hash, relay.key_hash) | 数据库做不到；不相交靠明文前缀禁 `sk-` + 查找不跨表 |
| `outbound_keys (tenant_id, name)` | name 可空、非产品唯一 |

### 3.1 第二张 pending / 两张确认不叠档（实现合同）

**正常入口（GWT-50.15）**

同一事务：

1. `SELECT ... FROM tenants WHERE id=:tenant_id FOR UPDATE`（企业行必有，作互斥；不要指望对空 pending 结果集的 gap lock）
2. `SELECT COUNT(*) FROM orders WHERE tenant_id=:tid AND status='pending'`
3. COUNT≥1 → 不 insert，返回 `ORDER_PENDING_EXISTS`
4. COUNT=0 → insert，`idempotency_key` 非空；撞 UNIQUE → 当已处理

夹具直插第二张 pending **绕过**本入口，故库中允许两行 `status=pending`。这是 spec 写明的，不是漏洞。

**两张都确认（GWT-50.16）**

- 每张：`pending → paid` 且写 `paid_at`（已 paid 再确认：保持 paid，不新开单）。
- `tenant_subscriptions` UNIQUE 保证仍一行；`_apply_plan` 对 `tenants.quota` / `plan_id` **SET** 不是 ADD。第二张确认不得 insert 第二订阅行、不得把三数字再加一档。
- 不把「配额变成专业档」写成 FR-50 完成条件（QA-24 / Q-PRICE）。

**在线通道：** 应用在 insert 前拒绝；零新行。无「在线 pending」状态需要库约束。

---

## 4. 访问模式 Top-N

> 来源：☑ PRD / 方案 / 调用方代码推导（**推定**）。无 production slow_query。
>
> 推定依据：contract §7、billing/relay 现网 list/confirm/issue、出站拉数热路径、公开列表 NFR-01。**上线后按真实慢查询复盘补索引。** 新特征模式一律标 **presumed**。

| ID | 触发场景（FR / 接口） | 过滤字段（等值 / 范围） | 排序 | 返回列 | 频次（次/天） | P95 要求 | 单次行数 |
|---|---|---|---|---|---|---|---|
| P-B01 **presumed** | FR-50 我的订单 | `tenant_id`= | `id` DESC | 订单行 | 低～中 | 100ms | 数十 |
| P-B02 **presumed** | FR-50 超管待确认 | `status`=`pending` | `id` DESC | 订单行 | 低 | 200ms | 数十 |
| P-B03 **presumed** | FR-50 再提交前 COUNT pending | `tenant_id`= `status`= | — | COUNT | 与下单同阶 | 50ms | 标量 |
| P-O01 **presumed** | FR-51 列出本企业出站钥匙 | `tenant_id`= | `created_at` DESC | 前缀/状态 | 低 | 100ms | 数把 |
| P-O02 **presumed** | FR-51/13 拉数验钥 | `key_hash`= | — | id, tenant_id, revoked_at | 出站 QPS | 20ms | 0–1 |
| P-R01 **presumed** | FR-60 列出本企业令牌 | `tenant_id`= | `id` DESC | 令牌行含 used_tokens | 中 | 100ms | 每租户 <100 |
| P-R03 **presumed** | FR-60 按网关引用对账 spend | `gateway_key_id`= | — | id, used_tokens | 随列表刷新 | 50ms | 1 |
| P-M01 **presumed** | FR-80/81 公开列表（listed 闸 **之后** 残差滤种子） | 沿用 v2 listing/status/type；再 NOT 种子谓词 | `id` DESC | 卡片 | ~5k–50k | 2s | ≤20 |
| P-E01 **presumed** | FR-92 超管按事件名+时间 | `event_name`= `occurred_at` 范围 | `occurred_at` DESC | 事件行 | 低 | 200ms | 50 |
| P-A01 **presumed [Wave A]** | FR-93 恢复/新建占用判定 username（GWT-93.4/93.5/93.8；T-24） | `tenant_id`= `username`= | — | id | 低（管理动作） | 200ms | ≤1 |
| P-A02 **presumed [Wave A]** | FR-83 邮箱登录查找 / FR-93 email 占用判定（GWT-83.1/93.7；T-16/T-24） | `email`= | — | id, tenant_id, password_hash | 中（每次登录） | 100ms | ≤1 |
| P-A03 **presumed [Wave A]** | FR-93 用户管理「已删除」筛选（GWT-93.1/93.2；T-25） | `deleted_at` IS NOT NULL | `deleted_at` DESC | 页列 | 低 | 500ms | ≤页 |
| P-A04 **presumed [Wave A]** | FR-105 queue_depth 规则读取（GWT-105.1；T-42 调度周期） | `rule_type`= `enabled`= | — | 规则列 | 周期（分钟级） | 无硬性 | ≤租户数 |
| P-A05 **presumed [Wave A]** | FR-100 导入明细回放（GWT-100.2；T-36 UI） | `batch_id`= | `id` ASC | 全列 | 低 | 500ms | ≤批条目 |
| P-A06 **presumed [Wave A]** | FR-100 导入幂等判定（GWT-100.8；T-35） | `capability_assets.asset_type`= `name`= | — | id | 随导入 | 100ms | ≤1 |

**已知但不进 Top-N（不建索引）：**

- 超管按企业筛订单（低频；`ix_orders_tenant_id` 已有）
- `orders.channel`（在线零行）
- `relay_tokens.used_tokens` / `spend_synced_at` 单列
- `outbound_keys.issued_by_user_id`
- `capability_assets` 种子三列函数索引（400 行残差过滤；P-M01 已有 listing 复合）
- `product_events.anonymous_id` 点查
- 跨表 hash 联合扫描（禁止该查询）
- **[Wave A]** 平台租户入队读 tenants by slug（GWT-102.1）——唯一键单行路径
- **[Wave A]** 中转站总览三问（GWT-98.2）——channel_events/probe 既有读路径，本特征不建索引
- **[Wave A]** 超管按企业筛导入批次历史——批次表极小，倒序扫可接受

---

## 5. 索引设计

| 索引 | 字段顺序 | 服务模式 | 列顺序理由（ESR） |
|---|---|---|---|
| `PRIMARY` | `id` | — | 各表代理主键 |
| `uk_outbound_keys_key_hash` | `(key_hash)` | P-O02 | 等值指纹；业务唯一兼热路径 |
| `idx_outbound_keys_tenant_created` | `(tenant_id, created_at)` | P-O01 | 多租户最左 tenant → 排序 created_at |
| `ix_orders_tenant_id` | `(tenant_id)` | P-B01 / P-B03 | **040 已有**。每租户数十行，pending COUNT 可扫 |
| `uk_orders_idempotency_key` | `(idempotency_key)` | 下单重试 | **040 已有** |
| `uq_relay_tokens_key_hash` | `(key_hash)` | 既有 | **040 已有，不改** |
| `ix_relay_tokens_tenant_id` | `(tenant_id)` | P-R01 | **040 已有** |
| `uk_relay_tokens_gateway_key_id` | `(gateway_key_id)` | P-R03 | 等值网关引用；UNIQUE 兼索引 |
| `idx_product_events_name_occurred` | `(event_name, occurred_at)` | P-E01 | **已有**；新事件名共用 |
| `idx_assets_listing_status_type_cat` | `(listing_state, status, asset_type, category)` | P-M01 | **已有**；种子残差不另建 |
| `uq_users_tenant_username_alive` **[Wave A，042]** | `(tenant_id, username, alive_flag)` | P-A01 | 业务唯一（在册口径）；等值 (tenant_id, username) 定位，alive_flag 尾列只作约束组件 |
| `uq_users_email_alive` **[Wave A，042]** | `(email, alive_flag)` | P-A02 | 业务唯一；email 最左前缀即登录等值查找 |
| `ix_users_username`（既有保留） | `(username)` | 跨租户 username 消歧（R13 单点 get_by_username） | 不被新键覆盖（新键 tenant_id 最左）；026 后存续，不动 |
| `idx_import_items_batch` **[Wave A，043]** | `(batch_id)` | P-A05 | 等值过滤；FK 必带索引 |
| （既有）`uq_asset_type_name_alive` | `(asset_type, name, alive_flag)` | P-A06 | 导入幂等判定直接复用，零新索引 |

**[Wave A] EXPLAIN 证据（2026-09-11 本机 MySQL 8.0.42 / alembic 039，原始输出，未修饰）**：

```
--- EXPLAIN [P-A01 restore occupancy username] ---
SQL: SELECT id FROM users WHERE tenant_id=1 AND username='admin' AND deleted_at IS NULL
id|select_type|table|partitions|type|possible_keys|key|key_len|ref|rows|filtered|Extra
1|SIMPLE|users|None|const|uq_users_tenant_username,ix_users_username|uq_users_tenant_username|206|const,const|1|100.0|None
→ 042 换防后由 uq_users_tenant_username_alive 最左前缀承接（等值两列不变，type=const 预期保持）

--- EXPLAIN [P-A02 email login lookup] ---
SQL: SELECT id, tenant_id, password_hash FROM users WHERE email='a@b.c' AND deleted_at IS NULL
id|select_type|table|partitions|type|possible_keys|key|key_len|ref|rows|filtered|Extra
1|SIMPLE|NULL|None|None|NULL|NULL|NULL|NULL|None|None|no matching row in const table
→ 等值命中唯一键 `email` 的 const 优化形态（无匹配行的短路输出）；042 后由 uq_users_email_alive 最左前缀承接

--- EXPLAIN [P-A03 recycle-bin filter] ---
SQL: SELECT id, username, email, deleted_at FROM users WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC
id|select_type|table|partitions|type|possible_keys|key|key_len|ref|rows|filtered|Extra
1|SIMPLE|users|None|ALL|NULL|NULL|NULL|NULL|6|83.33|Using where; Using filesort
→ type=ALL 全扫 6 行=最优（接受，见下表「已评估不建」）

--- EXPLAIN [P-A04 queue_depth rule read] ---
SQL: SELECT id, tenant_id, threshold, window_minutes, channels, last_triggered_at FROM alert_rules
     WHERE rule_type='queue_depth' AND enabled=1 AND deleted_at IS NULL
id|select_type|table|partitions|type|possible_keys|key|key_len|ref|rows|filtered|Extra
1|SIMPLE|alert_rules|None|ALL|NULL|NULL|NULL|NULL|1|100.0|Using where
→ 配置量级表全扫（现 0 行）=最优（接受）
```

P-A05/P-A06 无本机表（043 未建；capability_assets 在 018+ 链上）——**EXPLAIN 由实现票在 040+041…043 库上补贴原始输出**；P-O02/P-B01/P-R03 沿 v1 口径同样由 S4 真库补。本文件无假 EXPLAIN。

**已评估不建：**

| 候选 | 不建的理由 |
|---|---|
| `idx_orders_status_created` | P-B02 基数 2；订单总量小；filesort 可接受。慢查询再补 |
| `(tenant_id, status)` on orders | P-B03 已有 tenant 前缀；非 Top-N 强制 |
| `(status)` 单列 | 基数 2–3 |
| `(revoked_at)` 单列 | 基数低；过滤在应用命中行之后 |
| `ix_outbound_keys_tenant_id` 单列 | 被 `(tenant_id, created_at)` 最左覆盖 |
| 种子列 / 前缀索引 on `name` | 不进 schema；小表 |
| `users(deleted_at)` 或 `(tenant_id, deleted_at)` **[Wave A]** | 回收站模式（P-A03）全扫 6 行最优（EXPLAIN type=ALL 即证据）；026 已定「不恢复单列」。行数 >1e4 且慢查询出现时再建 (tenant_id, deleted_at) |
| `alert_rules(rule_type)` **[Wave A]** | 基数≈4、配置量级表（本机 0 行）；调度周期分钟级，全扫成本可忽略（EXPLAIN 证据） |
| `tenants(name)` 唯一 **[Wave A]** | 冲突域含保留名「平台租户」与站点名 AutoAgents——保留名不是行，DB 唯一表达不了；收口写服务单点 |
| `orders` 生成列 `pending_flag` + UNIQUE **[Wave A 重申]** | v1 §3.1 已拒（挡 GWT-50.16 夹具两张 pending）；Wave A 不翻案 |
| `asset_import_batches(created_at)` **[Wave A]** | 批次数极小（操作者自用）；倒序扫+filesort 可接受 |
| `asset_import_items(batch_id, asset_type, name)` 唯一 **[Wave A]** | 单写者（导入器批内去重），无并发冲突面；唯一键属过度约束 |

最小索引：新表 = 业务唯一 + 上表 Top-N。容量见 §7，无需 gh-ost。

---

## 6. Redis 键

本特征 **不** 为出站钥匙、订单列表、公开种子、`used_tokens` 建缓存（本地列已是 spend 缓存；种子是查询谓词）。

| 键模式 | 类型 | 值结构 | 写入方 | 读取方 | TTL | 失效路径 | 未命中行为 | 容量估算 |
|---|---|---|---|---|---|---|---|---|
| `billing:order:lock:{tenant_id}` | String（锁） | token | `BillingService.create_order` 入口 | 同路径 | 15s（略大于临界区） | Lua 释放（GET==token 才 DEL）；失败交 TTL | 抢不到=与已有 pending 同句或短暂重试；**仍须** DB `FOR UPDATE`，锁只是快失败 | 租户数 × 1 × <64B |

无 TTL 键：本波不新增。v2 已有 `newapi:channel:cfg:{id}` / `relay:channel:cfg:{ref}` / 配额 COUNT 等 **保持**，本 IR 不改名。

Redis 不可用：下单跳过 SET NX，只走 DB 事务锁；不得因 Redis 挂掉而放行第二张 pending，也不得把 Redis 当唯一防线。

产品事件失败不挡主路径（已冻）。目录列表缓存 v1 仍不建。

---

## 7. 数据量与增长

| 表 | 当前行数 | 日增 | 一年后预估 | 分表/归档策略 |
|---|---|---|---|---|
| `outbound_keys` | 0 | 每企业数把 | 租户数 × <20 | 暂不需要；吊销行不删 |
| `orders` | 骨架级 | 每租户数十/年 | <10 万 | 不删；paid 留史 |
| `relay_tokens` | 骨架级 | 每租户 <100 | <10 万 | 吊销行不删 |
| `plans` | 2（free/pro） | 0 | <20 | — |
| `product_events` | 已有 | 追加五件名 | 仍 ≥90 天窗口 | 归档作业不进本波迁移 |
| `capability_assets` | ~含 400 种子 | 同步 | 清种子后下降 | 无 DDL |
| `users` **[Wave A 实测]** | 6（本机 039） | 0 生产 UV | <1e3 | 无需 |
| `tenants` **[Wave A 实测]** | 4（platform id=5、default id=1、演示×2） | ~0 | <1e2 | 无需 |
| `alert_rules` **[Wave A 实测]** | 0 | 租户配置 | <1e3 | 无需 |
| `asset_import_batches` / `items` **[Wave A]** | 0（新） | 操作者导入 | items <1e5 | 无需；超大目录由上传条目数上限（配置）钳制 |

本期小表，ADD COLUMN / CREATE TABLE：MySQL 8 `ALGORITHM=INPLACE`，秒级，无需维护窗口。

---

## 8. 破坏性变更

**v1 判定（C/U）保持：对生产结构 = 纯加法**（新表 + 两列可空 + 一 UNIQUE 含 NULL）。
**v2 增补 [Wave A]：数据破坏性 = 0**（无删列、无改类型、无 NOT NULL 收紧、无数据丢失）；唯一例外是 **042 users 唯一键替换**——属「唯一键变更」破坏性类别，但方向是**放松**（新键约束的行子集严格小于旧键：旧键保证同键至多一行，新键不可能被存量违反），沿 **025 既定先例**单迁移内 expand→contract 并附 impossible-down 前置校验，不适用三迁移分步（025 模块注释已给判据）。

| 变更 | 类型 | expand-contract |
|---|---|---|
| CREATE `outbound_keys` | 加法 | 单迁移 up/down |
| `relay_tokens.gateway_key_id` VARCHAR(191) NULL | 加法 | 一步加列 |
| `relay_tokens.spend_synced_at` DATETIME NULL | 加法 | 一步加列 |
| UNIQUE `uk_relay_tokens_gateway_key_id` | 加 UNIQUE（可空） | 骨架行全 NULL，MySQL 允许多 NULL。实现票 Step0：`SELECT gateway_key_id, COUNT(*) FROM relay_tokens WHERE gateway_key_id IS NOT NULL GROUP BY 1 HAVING COUNT(*)>1` 期望 0。若有重复 → **停、问 pm**，不要猜留哪行 |
| `product_events.event_name` 新字面量（C/U 五件 + Wave A 两件） | 非 DDL | 应用校验放宽 |
| **users 唯一键换防 + `alive_flag` 生成列 [Wave A，042]** | 唯一键变更（**放松方向**） | expand：加 VIRTUAL 生成列（INSTANT）→ 建两新键（INPLACE）；contract：同迁移撤旧两键+纯重复的 `ix_users_email`。SQL 骨架见 §16.1 |
| CREATE `asset_import_batches` / `asset_import_items` [Wave A，043] | 加法（新表） | 单迁移 up/down；items 先 drop |
| 040 `orders.tenant_id` 等可空 → NOT NULL | **本特征禁止** | 另特征三步：写路径必填 → 回填 NULL → MODIFY NOT NULL |
| 改 `key_hash` 类型 / 改名 | **禁止** | — |
| DROP `orders` 的 cancelled 语义 / 改 ENUM | **禁止** | 物理本就 VARCHAR |
| 物理删除已删 users 行 / email 改 NULL+时间戳 | **禁止 [Wave A]** | 审计链断裂；合同 §8 明令；alive_flag 方案使二者皆无必要 |
| LiteLLM PG 表进链 | **禁止** | — |
| 复活 028/029/030 | **禁止** | — |

生产 **禁止 downgrade past 037**。本波加法修订的 `down` 只允许在隔离库做 `up → down → up`；禁止把业务库 `auto_agents` 降到 037/base。040 `down` 会 DROP 账务/渠道组表——生产同样禁止。

签发补偿（非 DDL）：网关 `/key/generate` 成功但本地 insert 失败 → HTTP 删除该虚拟 Key，本地不留成功行。

---

## 9. 需真库验证的方言特性（交给 /qa）

- `uk_relay_tokens_gateway_key_id` 多 NULL：骨架行共存；SQLite 与 MySQL UNIQUE NULL 语义不一致 → `MYSQL_FIDELITY=1`
- `idempotency_key` UNIQUE 多 NULL：040 已如此；本波写入后非空撞键
- Mixin `tenant_id` ORM 默认可空 vs `outbound_keys` 迁移必须 NOT NULL；SQLite create_all 会骗人
- 出站表 **不在** 豁免清单：租户态 UPDATE/SELECT 必须注入 `tenant_id`；夹具同 PR
- 部分唯一 pending：**故意不建**；夹具两张 pending 可插入；正常入口第二张被拒
- `_apply_plan` 两次确认后 `tenant_subscriptions` 仍 1 行
- EXPLAIN P-O02/P-B01/P-R03：S4 真库补 raw；**本文件无假 EXPLAIN**
- `up → down → up` 下一加法修订退出码 0（实现票跑；本帽禁止写 alembic）
- 生产禁止 `downgrade 037` / `downgrade base`
- **[Wave A]** VIRTUAL 生成列进唯一键（042）：MySQL 8.0.13+ 支持（本机 8.0.42 ✓；capability_assets 025 已生产化）；SQLite/单测库验不出——迁移与「删后同名重建→再删→再建」链必须 MySQL 真库跑
- **[Wave A]** 恢复 UPDATE 触发唯一冲突：`SET deleted_at=NULL` 命中并发占用时抛 1062（pymysql IntegrityError）——qa 并发夹具验「判定通过→并发新建→恢复被拒不覆盖」（SEC-12；QA-03 同事务注记）
- **[Wave A]** 唯一索引多 NULL 判重豁免：已删行（alive_flag=NULL）可多行同 email——get_by_email/get_by_username **必须保持 deleted_at IS NULL 过滤**（Repository 已自动过滤），否则多已删行导致解析歧义（正确性红线，写进 T-24/T-16 注记）
- **[Wave A]** INSTANT/INPLACE DDL 行为复核：users 表本机 6 行/生产 0 租户，042 全部 DDL 秒级（VIRTUAL 加列 INSTANT、二级键 INPLACE）

---

## 10. 开放问题

仅 **dba 仍开放**。不回答、不代选 Q-VOICE / Q-PRICE / Q-MARKET-USER / Q-AGPL / Q-OPS-COLLECT。

| 问题 | 阻塞什么 | 需要谁定 |
|---|---|---|
| 无阻塞的建模问。一企业一张 pending 的**入口**不变量 vs 夹具两行，spec 已写明 | 否 | — |
| 出站明文非 `sk-` 前缀的具体字面量 | 否（IR 只禁 `sk-`） | `/backend` 实现票 |
| `gateway_key_id` 与 LiteLLM OpenAPI 字段对齐（token vs key id） | 否：列不透明 VARCHAR(191)；加宽非破坏 | T-08 对 OpenAPI |
| 040 `tenant_id` 可空收紧 | 否（本波不做） | 另特征 + `/sre` |
| Alembic 头环境是否已 040 | 部署，非本 IR | `/sre` 交付清单 |
| **[Wave A] 无新增阻塞问**（软删唯一性/平台租户保护/导入落位/queue_depth 语义全部已决：spec v1.5 + contract v2 §8 + Q-ADMIN-WAVE/Q-QUEUE-DEPTH 已关） | 否 | — |
| 非阻塞注记：Q-PRICE 若将来把确认收款履约为专业档三数字，落点在 tenants.quota（既有列），无 schema 预留需求 | 否 | /pm（未来轮） |
| 非阻塞注记：种子租户「默认租户」（default，本机 id=1）处置=不做（spec §5，无出处） | 否 | — |

---

## 11. TENANT_EXEMPT_TABLES（隔离契约，与 DDL 同 PR）

| 表 | 本波 | 理由 |
|---|---|---|
| `outbound_keys` | **禁止豁免** | TenantMixin；有企业维；PIT-3 |
| `orders` / `relay_groups` / `relay_tokens` / `tenant_subscriptions` | 保持不豁免 | 已 Mixin |
| `plans` | 保持豁免 | 无 tenant 列；040 已登记 |
| `product_events` | 保持豁免 | 事件主语可 NULL |
| `asset_import_batches` / `asset_import_items` **[Wave A]** | **必须登记豁免** | 平台级（超管专属动作），tenant_id 恒 NULL；PIT-3「新平台表必须豁免」。**模型禁 TenantMixin**，登记与建表同 PR |
| `users` / `tenants` / `alert_rules` / `notifications` **[Wave A]** | 保持不豁免 | 既有隔离/主语语义不变 |
| LiteLLM 表 | 不登记 | 不进本库 |

夹具必须显式：租户态不能读到他企业 `outbound_keys`；超管确认订单走平台态。

---

## 12. `used_tokens` 要走：哪列、谁写、吊销后不可用

| 项 | 合同 |
|---|---|
| 哪列 | `relay_tokens.used_tokens`（040 已有 INT NOT NULL default 0） |
| 金标 | LiteLLM spend / key info **HTTP**（ADR-0019）。禁止 `create_async_engine` 打网关库 |
| 本地列角色 | 缓存。列表/详情展示读本列 |
| 谁写 | **渠道组域** `RelayService`（写方不变）。触发点=**令牌详情 / 显式刷新**（单次或按页批量；contract §7.4 QA-08 / ADR-0019 v2）：对 `gateway_key_id IS NOT NULL` 的行打网关 key info HTTP，写入 `used_tokens` + `last_used_at` + `spend_synced_at=now`。**`list_tokens` 列表渲染只读本地 `used_tokens` 缓存列，禁止每行打网关**。**不是** FastAPI chat 拦截器（租户直打独立网关，backend 无每次 +1） |
| 谁不写 | 出站域；账务；Power Market；GET groups |
| 签发 | insert `used_tokens=0`，`spend_synced_at` NULL，`gateway_key_id`=网关返回值。网关失败 → 不 insert |
| 对账窗口 | 用户按用法打通后，**下一次**打开渠道组页应 ≥1（ADR-0019 最终一致）。期间可能仍见 0；**不得**把 0 写成「已用完」 |
| 事件 | 当本次刷新观察到 0→≥1 时上报 `relay_token_call_succeeded`（含 `tenant_id`，无明文） |
| 吊销后不可用 | 门闩是 `revoked_at IS NOT NULL` **加上** 网关 HTTP 作废该 Key。**不是**把 `used_tokens` 置 -1。再打 Base URL 必须拒绝（QA-20），不是 60.3 成功。本地已吊销的行刷新 spend 可选，但 status 必须是 revoked |
| A 不动 B | UPDATE 带 `tenant_id`；跨企业 404 同形（GWT-60.10） |

---

## 13. 公开商店 listed 过滤测试种子

**不进 schema、进治理/同步。**

不 ADD `is_seed` / `is_nfr` / `is_fixture`。

可观测定义（与 GWT-80.1 同一套，大小写不敏感处按 spec）：

- `capability_assets.name` 匹配 `nfr01qc2-*`（大小写不敏感），**或**
- `title` 以「NFR卡片」开头，**或**
- `description` 含 `preprod nfr-01 seed`

公开 `/public/skills` 与 `/public/capabilities` **同一**谓词（PIT-5），在 FR-33 可见闸（listed/coming_soon ∩ 治理 status ∩ 许可 ∩ 非软删）**之后**再排除。`total` 不含种子。

治理/同步：生产同步 **不得** 把上述行标 listed 当商品；测试夹具可 listed，公开读模型仍滤掉。租户不能把种子改成访客可见（GWT-80.3）——靠读模型谓词，不是靠列。

≥21 张非种子 listed 用**夹具资产**，禁止为翻页再造商店模型，禁止把种子改成商品。

---

## 14. 迁移自检（本帽不落独立 `migration-review.md`；实现票按此跑）

> 变更类型：C/U=纯加法（**041**）；Wave A=加法两表（**043**）+ 唯一键放松换防（**042**，025 先例单迁移 expand→contract）。修订号预计 041/042/043（autogenerate 分配，本帽 **禁止** 写 `backend/alembic/versions/`）。

| 对象 | 操作 | 修订 | 破坏性 |
|---|---|---|---|
| `outbound_keys` | CREATE TABLE | 041 | 否 |
| `relay_tokens.gateway_key_id` | ADD COLUMN NULL | 041 | 否 |
| `relay_tokens.spend_synced_at` | ADD COLUMN NULL | 041 | 否 |
| `uk_relay_tokens_gateway_key_id` | ADD UNIQUE | 041 | 否（全 NULL 骨架；Step0 探测非空重复） |
| `idx_outbound_keys_tenant_created` | ADD INDEX | 041 | 否 |
| `users.alive_flag` | ADD VIRTUAL 生成列 | **042** | 否（INSTANT；025 同款） |
| `uq_users_tenant_username_alive` / `uq_users_email_alive` | ADD UNIQUE | **042** | 否（放松方向；旧键保证下存量必满足） |
| `uq_users_tenant_username` / 唯一键 `` `email` `` / `ix_users_email` | DROP KEY | **042** | 唯一键变更=破坏性类别，但**放松**（025 先例单迁移完成；down 带前置校验，见 §16.1） |
| `asset_import_batches` / `asset_import_items` | CREATE TABLE ×2 | **043** | 否（items 先 drop；豁免登记同 PR） |

**`down` 能恢复数据吗？** 041/043 能结构（行数据 down 即丢，隔离库验证用）；**042 down 有前置校验**——若 042 存续期发生过「删后同名重建」，旧键无法重建 → 显式 raise（impossible-down：先恢复/物理清理软删同名行再回滚；检测 SQL 见 §16.1）。生产禁止 down past 037，本特征 down 也禁止打业务库。

锁与耗时：小表（users 本机 6 行/生产 0 租户），042 全部秒级（VIRTUAL 加列 INSTANT、二级键 INPLACE）；迁移注释记录表规模与预计时长。回填：N/A（无数据迁移；`gateway_key_id` 骨架保持 NULL 直到重新签发，禁止把本地假 sk- 回填成网关 id）。

`up → down → up`：实现票在隔离库对 041/042/043 分别跑三连并粘贴退出码。本帽不跑、不编造 EXPLAIN。

---

## 15. 给下游

| 给谁 | 内容 |
|---|---|
| `/backend` | 按 `schema.dbml` 扩 ORM（`/new-model` 出站表）；禁手写迁移 SQL；出站 Mixin 禁豁免、夹具同 PR；签发明文一次；拉数先本表后 KEY_BINDINGS；禁止 import 把 relay hash 当出站；`used_tokens` 只由 RelayService 在令牌详情/显式刷新（单次或按页批量）对账回写，`list_tokens` 列表渲染只读本地缓存列、禁止每行打网关（contract §7.4 QA-08）；下单锁 tenants + 写 idempotency_key；在线零行 |
| `/qa` | §2.1 负向；50.15/50.16 夹具 vs 入口；吊销后再拉/再打；种子无列仍滤；EXPLAIN 真库；MYSQL_FIDELITY UNIQUE NULL |
| `/sre` | 头对齐 040 再升加法修订；LiteLLM PG 不进本链；生产禁止 down past 037；PUBLIC_BASE_URL；小表秒级 DDL |
| `/architect` | 本文件即 contract §8 落地：新表一张 + relay expand 两列；种子不进 schema。**v2：** Wave A 落地=users 042 换防 + import 043 两表 + 四处 N/A（tenants/spider_tasks/alert_rules/capability 复用） |
| `/backend` **[Wave A]** | user.py 加 alive_flag 生成列+换唯一约束名（照 capability_assets L58）；恢复端点：占用预检只为文案，正确性=捕获 1062→GWT-93.4 句，重复恢复 rowcount=0 no-op 不重复事件；登录/查找保持 deleted_at IS NULL 过滤（红线）；tenant 写服务单点 slug 守卫；import 两表禁 TenantMixin+登记豁免；queue_depth 读 AlertRule 评估+notifications 命中行+静默窗，`SCHEDULER.QUEUE_DEPTH_WARN` 日志路径退役为非评估结果 |
| `/qa` **[Wave A]** | §2.1 users/tenants/import 负向；93.4/93.8 并发占用夹具（SEC-12）；93.5/93.7 删后重建链（MySQL 真库）；105.3 全类型扫描无死规则；100.7 逃逸后资产目录外零新文件；92.8/92.9 事件可查 |
| `/sre` **[Wave A]** | 本机 039 漂移：042/043 实现与验证前先完成 040 对齐（交付清单）；沙箱/上传上限配置项落 config（NFR-10 配置即代码） |

---

---

## 16. Wave A 数据语义 → 机制决策（v2 增补；语义来自 contract v2 §8，机制本帽定）

### 16.1 users 软删占用/释放（FR-93，QA-03）——机制=alive_flag 生成列 + 恢复即约束

- **MySQL 8 无部分唯一索引的等价方案（本仓既定）**：`alive_flag SMALLINT GENERATED ALWAYS AS (CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END) VIRTUAL`，唯一键带尾列 `alive_flag`——存活行=1 参与判重；已删行=NULL，MySQL 唯一索引不对含 NULL 行判重 → 释放。025 已用同机制改造 5 表（capability_assets 生产在用），本特征推到 users，不再新造机制。
- **占用判定各自独立**：username 同租户在册（`uq_users_tenant_username_alive`）；email 全局在册（`uq_users_email_alive`）——与 GWT-93.4/93.5/93.7 的拆格口径一一对应。
- **恢复与占用判定同事务（防「判定通过→并发新建→恢复覆盖」）**：恢复=单条 `UPDATE users SET deleted_at=NULL WHERE id=? AND deleted_at IS NOT NULL`。正确性由新唯一键兜底——并发场景任一串行序都安全：
  - 并发「新建占名」先落 → 恢复 UPDATE 使 alive_flag=1 → 撞唯一键 → 1062 → 映射 GWT-93.4 中文占用句，现有用户行不被触碰（UPDATE 只清本行 deleted_at，**永不覆盖他人**）；
  - 恢复先落 → 并发新建 INSERT 撞唯一键 → 创建侧 422 优雅报错。
  应用层预检（P-A01/P-A02 等值查）只为提前给友好文案；禁止把「先查后写」当正确性依据。
- **重复恢复 no-op（GWT-93.9）**：`WHERE deleted_at IS NOT NULL` 使 rowcount=0 → 不写、不重复上报 `user_restored`。
- **禁物理删除已删行 / 禁 email 改 NULL+时间戳**：§8 已列禁止项；alive_flag 方案使二者皆无必要（占用问题在唯一键层消失，审计行保留）。
- **042 SQL 骨架**（实现票照此落 Alembic；SQL 注释用半角括号）：

```sql
-- upgrade (expand -> contract 单迁移, 025 先例: 放松方向)
ALTER TABLE users ADD COLUMN alive_flag SMALLINT
  GENERATED ALWAYS AS (CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END) VIRTUAL
  COMMENT 'alive marker (042): unique-key component, soft-deleted rows NULL out';
ALTER TABLE users
  ADD UNIQUE KEY uq_users_tenant_username_alive (tenant_id, username, alive_flag),
  ADD UNIQUE KEY uq_users_email_alive (email, alive_flag);
ALTER TABLE users
  DROP KEY uq_users_tenant_username,
  DROP KEY `email`,         -- 001 部署自动名 (本机 SHOW CREATE TABLE users 实证); 实现时按 information_schema.STATISTICS 定位 NON_UNIQUE=0/COLUMN_NAME='email'
  DROP KEY ix_users_email;  -- 与唯一键纯重复 (026 治理口径, 不恢复)

-- downgrade 前置校验 (impossible-down 显式化, 025 同款)
SELECT tenant_id, username, COUNT(*) c FROM users GROUP BY tenant_id, username HAVING c > 1;  -- 任一行 -> raise
SELECT email, COUNT(*) c FROM users GROUP BY email HAVING c > 1;                              -- 任一行 -> raise
ALTER TABLE users
  DROP KEY uq_users_tenant_username_alive, DROP KEY uq_users_email_alive,
  DROP COLUMN alive_flag,
  ADD UNIQUE KEY uq_users_tenant_username (tenant_id, username),
  ADD UNIQUE KEY `email` (email);
```

### 16.2 平台租户/admin 基座保护（FR-94）——机制=slug 守卫，无迁移

- **选 slug 守卫，不选 `is_protected` 新列**（理由见 §0.1）。保护收口在 **tenant 写服务单点**：企业管理页与运营台同走该服务（两处读同一真相，GWT-95.1/95.2/95.7「同显」由此保证）；三条迁移非法=改名（GWT-94.2）/停用（94.3）/删除（94.4 前置冻结，本波无删除入口）。
- **种子与回填：无**。024 已幂等 INSERT `('platform','平台租户','active',NULL,…)`；本机实证 tenants 行 `id=5, slug='platform', name='平台租户', status='active'`，与 spec §0.4 产品名一致——**零迁移、零回填**。
- 种子 admin 守卫在 `delete_user` 单点（与「不能删自己」「最后一个超管」并存、判定在前），拒绝句「平台初始账号不可删除。」——应用层，无 DDL。
- 边界：种子行缺失=配置错误（fail loud），不静默建租户；`slug=='platform'` 字面量按 contract §2.4 只出现在 actor 解析、蓝图排除、tenant 写服务守卫三处，不散落。

### 16.3 企业改名/停用/再启用（FR-95）——schema 变更 N/A（明说）

纯 UPDATE `tenants.name` / `tenants.status`（active⇄disabled 双向，仅常规企业）。改名冲突域（既有企业名 ∪ 保留名「平台租户」∪ 站点名 AutoAgents）是应用层判定（保留名不是行，DB 唯一键表达不了；已评估不建见 §5）。**本条无任何迁移。**

### 16.4 平台租户入队（FR-102）——schema 变更 N/A（确认）

`spider_tasks.tenant_id` 既有列传递：`task_actor_tenant_id` 解析扩展（平台超管→platform 租户行 id）。配额按平台租户执法（tenants.quota 既有列，不因超管身份绕过，GWT-102.3）；WACT/PC 排除在事件消费侧（蓝图 §1），不在写入点过滤。**无迁移。**

### 16.5 导入资产落位（FR-100 / ADR-0023）——结论=capability_assets 复用零扩列；沙箱是文件系统

- **复用**：导入产物=capability_assets 目录行（`listing_state='unlisted'` 入库，不自动上架——PC-2 不动）；agent 是 `asset_type` 既有值（ASSET_TYPES 七类含 agent）。幂等键=类型+名称=既有 `uq_asset_type_name_alive`，**不加列不加键**。origin_*（source_id/origin_ref）服务 capability_sources 外部树（URL 导入/目录扫描保持不废不移），本地上传不是源树——**不扩 origin 列**；provenance（这条目录行哪次导入来的）经 `asset_import_items.asset_id` 反查回放。
- **沙箱边界**：沙箱=临时目录（文件系统），**不是库表**；大小/条目数/耗时上限来自配置（NFR-10）；路径规范化后越界条目（`../`、绝对路径、symlink）拒绝且列入失败原因，资产目录外零新文件（GWT-100.7，NFR-04/SEC-11）。库内只落 043 两表回放结果。
- **043 SQL 骨架**（要点；实现票落 Alembic）：

```sql
CREATE TABLE asset_import_batches (
  id INT NOT NULL AUTO_INCREMENT,
  origin VARCHAR(16) NOT NULL COMMENT 'file/directory',
  status VARCHAR(16) NOT NULL DEFAULT 'running' COMMENT 'running/completed/failed',
  total_count INT NOT NULL DEFAULT 0,
  succeeded_count INT NOT NULL DEFAULT 0,
  failed_count INT NOT NULL DEFAULT 0,
  skipped_count INT NOT NULL DEFAULT 0 COMMENT 'idempotent skips (GWT-100.8)',
  created_by VARCHAR(64) NULL,
  tenant_id INT NULL COMMENT 'platform-level, always NULL (TENANT_EXEMPT)',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at DATETIME NULL COMMENT 'NULL=not finished',
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE asset_import_items (
  id INT NOT NULL AUTO_INCREMENT,
  batch_id INT NOT NULL,
  asset_type VARCHAR(16) NOT NULL COMMENT 'skill/agent/command/plugin',
  name VARCHAR(128) NOT NULL,
  status VARCHAR(16) NOT NULL COMMENT 'succeeded/failed/skipped',
  reason VARCHAR(512) NULL COMMENT 'zh failure reason',
  asset_id INT NULL COMMENT 'capability_assets.id on success',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_import_items_batch (batch_id),
  CONSTRAINT fk_import_items_batch FOREIGN KEY (batch_id)
    REFERENCES asset_import_batches(id) ON DELETE CASCADE,
  CONSTRAINT fk_import_items_asset FOREIGN KEY (asset_id)
    REFERENCES capability_assets(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- down: DROP TABLE asset_import_items; DROP TABLE asset_import_batches;
```

### 16.6 queue_depth 接通（FR-105，Q-QUEUE-DEPTH 已决）——schema 变更 N/A（确认）

- 调度器周期读 `alert_rules` 的 queue_depth 行（`rule_type='queue_depth' AND enabled=1 AND deleted_at IS NULL`，P-A04；评估深度=按规则所属租户的排队任务数，AlertRule 为 TenantMixin）→ 命中 → 经规则已配置渠道发送。
- **命中记录**：`notifications` 行（既有表：type='alert'，resource_type='alert_rule'，resource_id=规则 id，content 含深度与判定）+ `alert_rules.last_triggered_at`（既有列，最近命中时刻）。命中记录仅调度器（经 notify 路径）写；租户只能改本企业规则（105.4）。**无迁移**。
- **`notifications.user_id` 口径（QA-06）**：默认=**规则创建者**——`alert_rules.created_by` 是用户名字符串（AuditMixin），notify 路径按同租户在册行（`deleted_at IS NULL`）解析成 `users.id` 落入该列；列本身 NOT NULL FK「接收人」，无 NULL 态。副作用：每次命中（静默窗节流后的每次发送）给规则创建者收件箱未读徽标 +1，与创建者本人是否有排队任务无关，随已读动作清除。创建者已软删/解析不出在册行 → 不落命中行、不静默改投他人（若业务要改投口径，/pm 定）。
- **静默窗**：`now − last_triggered_at < 窗口` 内重复命中不重复发送——纯读比较，无新列。
- 废弃语义：`SCHEDULER.QUEUE_DEPTH_WARN` 日志路径退役为**非评估结果**（不再是 queue_depth 的输出口径）。
- 唯一新增事件：无（FR-105 不进 FR-92 事件面）。

## 17. 变更记录

| 版本 | 日期 | 变更 | 触发者 |
|---|---|---|---|
| v1 | 2026-09-11 | Wave C/U 增量 IR：outbound_keys 新表、relay expand 两列、orders 写规则（锁+COUNT+idempotency_key）、种子不进 schema、used_tokens 写点合同 | contract v1 → dba spawn |
| v2 | 2026-09-11 | **shape r1 扩展（并入 Wave A）**：users 042 唯一键在册化（alive_flag，QA-03）+ 恢复机制；平台租户 slug 守卫（无迁移）；FR-95/102/105 三处 N/A 确认；导入 043 两表 + capability_assets 复用结论 + 沙箱文件系统边界；P-A01…P-A06 推定模式 + 本机 039 库 EXPLAIN 原始输出四份；破坏性声明细化（042=放松方向 025 先例）。v1 结构与 C/U 决策原样保持 | contract v2 §8 → dba spawn（Wave A） |
| v2.1 | 2026-09-11 | **shape r2 附条件微修（无 DDL/索引/迁移变化）**：QA-02——§12「谁写」与 §15 `/backend` 行对齐 contract §7.4 QA-08 / ADR-0019 v2（触发点=令牌详情/显式刷新，单次或按页批量；`list_tokens` 列表渲染只读本地 `used_tokens` 缓存列，禁止每行打网关）；QA-06——§16.6 补 `notifications.user_id`=规则创建者口径（created_by 用户名→同租户在册 users.id；NOT NULL FK）及未读徽标副作用 | shape r2 QA 微修 spawn（QA-02/QA-06） |

Contract check: entities, expand vs new, outbound_keys, used_tokens writer, pending uniqueness vs 50.16, seed not-in-schema, irreversible confirm/revoke, LiteLLM PG excluded, no handwritten SQL. **v2 追加：** users alive 换防可逆（down 前置校验）、平台租户保护零 DDL、导入四类齐落 043、queue_depth 零 DDL、沙箱非库表、每新索引有模式 ID（P-A01…P-A06）。
