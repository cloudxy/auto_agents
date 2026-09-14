# db-spec · upgrade-four-pillars

> 上游：PRD `01-define/spec.md` v1.2（覆盖 FR-U01…U04、FR-U10…U15、FR-U20…U25、FR-U30…U38）｜方案 `02-shape/contract.md` §7｜ADR-0024 / ADR-0025
> 下游：`schema.dbml` → Alembic **autogenerate**（禁手写全量 SQL；生成列若 autogenerate 表达不全，只补那一段）→ `/backend` ORM
> 泳道：L3｜作者：/dba｜日期：2026-09-12
> 本文件只补四柱深度调整的数据 GAPS。v2 `feat-four-pillars-v2/02-shape/db-spec.md` 仍是目录/事件基线，**不复制**。
> **已有表 IR**：被改表 = live 全列 ∪ 本特征加列。禁止 stub。漏 live 列 = autogenerate DROP。新表不受此条。
> Alembic 头现行 **044**。本波目标修订 **045+**（N1 与 N3 **不得**挤进同一迁移文件）。禁止复活 028/029/030。生产禁止 downgrade past 037。
> Q-AGPL 待确认：本文件不写「当前可买」语义列。
> 本帽不写 Service / Repository / API。

访问模式先于索引（ADR-0002）。本波无生产 slow_query：§4 全部 **推定**，上线后按真实慢查询复盘。

---

## 0. 实体与粒度（建模第一步的产出）

| 实体（表名） | 一行代表什么 | 来源 FR | 别名归并 |
|---|---|---|---|
| `internal_fixture_tenants` | 一家被超管标为内部测试（夹具）的企业 **当前** 在名单上 | FR-U03 | 「内部测试名单」「夹具企业」 |
| `orders` | 一次结账意图（待支付/支付单据）；**已有表**，本波加列+状态机 widen | FR-U30…U38；ADR-0024 | 「订单」「待支付」「支付单据」 |
| `payment_channel_credentials` | 一个收款通道（支付宝或微信）的一套 **运行凭据**（密文） | FR-U31；ADR-0024 | 「商户凭据」「商户密钥」 |
| `relay_sku_entitlements` | 一企业 **当前** 中转 SKU 买没买、过没过期 | FR-U20…U23；ADR-0025 | 「中转权益」「中转已开通」 |
| `product_events` | 一次已发生的产品事实（追加）；**已有表**，加夹具快照列 | FR-U03 / U14 / U37；ADR-0016 | 不改粒度 |

**粒度必须能用一句话写出来。**

**被判定为「不是实体」的名词**：

| 名词 | 判定 | 理由 |
|---|---|---|
| 夹具布尔 `is_internal_fixture` | **事件上的快照字段**，不是租户行上的活标记 | 北极星读当时快照；事后改名单不得改写历史（contract §7） |
| 支付网关 / 通道 SDK | 外部引用 | 只存通道码 `alipay`/`wechat` + 我方 `order_no`；不建网关表；不把 SDK 名当模块 |
| 通道通知原文 | 不落库 | 可能含签名材料；验真在进程内；开通幂等靠单据状态，不靠再存一份回调体 |
| 迟到回调 | `orders.late_notify_at` 字段 | 不是独立实体 |
| 开通处理中 | `orders.status=paid_pending_fulfillment` | 状态，不是表 |
| 专业档 / 企业档 | `plans` 行（已有）+ 商品码 | 商品码与套餐行分家；`relay` **不是** `plans` 行 |
| `relay_groups` / `relay_tokens` | 已有产品数据 | 有组行 ≠ 已买（ADR-0025）。本波 **不删行、不加权益列** |
| 市场总开关 | 运行配置 | NFR-U10；不新建表 |
| 支付宝/微信密钥的 git/yml 配置 | **禁止存在** | FR-U31.4；A5；不得进 `config/**` 明文 |
| `plan_ent` SKU 码 | N/A | 企业档商品码是 `plan_enterprise` |

**FR 覆盖核对**：

| FR | 涉及实体 | 承载字段 | 缺口 |
|---|---|---|---|
| FR-U01/U02 | 既有任务/结果；本波无新表 | — | 无 DDL |
| FR-U03 | `internal_fixture_tenants` + `product_events.is_internal_fixture` | 名单当前态；事件快照布尔 | 无 |
| FR-U04 / U10…U15 / U24 / U25 | 无新表 | 开关/RBAC/文案 | 无 DDL |
| FR-U20…U23 | `relay_sku_entitlements` | `status`/`period_end`；读路径闸，不 COUNT 组行 | 无 |
| FR-U30 / U32 / U34 / U35 / U36 | `orders` | `product_code`/`channel`/`status`/`open_product_slot` | 无 |
| FR-U31 | `payment_channel_credentials` | `merchant_no` + `secrets_encrypted`（密文） | 无 |
| FR-U33 / U38 | `orders` + 权益/订阅写口 | 验真时间、商户快照、金额快照、开通一次 | 无 |
| FR-U37 | `product_events` | 事件名；props 含 channel/product；**无**密钥 | 无 |
| 企业档价目 | `plans.slug=enterprise` **种子行** | 见 §10：价格/配额待 /pm，不编造 | 种子值缺口 |

### 0.1 建模决策记录（有取舍的才写）

| 决策 | 选了什么 | 备选 | 理由 |
|---|---|---|---|
| 夹具 | 独立名单表 + **事件快照列** | `tenants.is_internal_fixture` 现场 JOIN | 「当时」：改名单不能改写已发生的北极星行 |
| 夹具移出 | **物理 DELETE** 名单行 | 软删 | 当前在不在名单=有没有行；历史只在事件快照里 |
| 结账意图 | **扩既有 `orders`**，不新建 payment_intents | 第二张单据表 | 现网已有订单+金额分+通道码；再建一张会双写 |
| 商品码 vs `plan_id` | `product_code` 新列；`plan_id` **放宽为可空** | 给 `relay` 造一条 `plans` 行 | 商品与套餐分家（ADR-0024）；中转不是档位 |
| 一企一商品一待支付 | **生成列** `open_product_slot` + UNIQUE `(tenant_id, open_product_slot)` | 只先查后插 / 只靠 `idempotency_key` | 合同禁止只先查后插；MySQL 无部分唯一索引，用 NULL 脱离终态行 |
| 金额 | 继续 `amount_cents` INT（分，快照） | 改 `DECIMAL(12,2)` | 跟仓；单币种 CNY；改类型是破坏性，本波不做 |
| 单据状态 | **同一 VARCHAR 列 widen**，新旧字面量并存映射 | 新列 `status_v2` 再 contract | ADR-0024 已钉读模型双认；本波 **不** DROP 旧字面量 |
| 商户凭据 | 平台表、**无 `tenant_id` 列**、整包密文 | Mixin 恒 NULL 租户列；yml 明文 | PIT-3；FR-U31；密钥不进 git |
| 密文形态 | 单列 `secrets_encrypted` TEXT（不透明 blob） | 密钥/证书口令分列明文 | 超管读回只掩码；本文件 **不选** 算法（FR-U31） |
| 中转已买 | **独立权益表** 一企一行 | 组行 COUNT / 专业档 / `menu:relay` | ADR-0025；专业档履约不得写本表 |
| 权益缺行 | 读路径视为 `none`；开通时 INSERT | 全租户预插 none | 未买不必占行；唯一键仍是 `tenant_id` |
| 组行 | 本波 **不删** | SKU none 时 DELETE 组 | ADR-0025 备选 E 否决 |
| 主键 | 跟仓 **INT** AUTO_INCREMENT | BIGINT | 与 `orders`/`product_events` 一致 |
| 时间 | 被改表跟该表既有方言；新表 naive DATETIME UTC | 本波统一抬 TIMESTAMP | 全库已混；禁止在同一张表混用 |
| 软删 | 四张新/改业务表 **不加** 软删 | 一律 SoftDeleteMixin | 豁免：名单删除即「不在名单」；凭据轮换就地；单据/权益是账本 |
| 产品事件精确一次 | **仍无** 幂等键 | UNIQUE(event, order_id) | ADR-0016 不重开；支付 **开通** 精确一次在 `orders` 状态机 |
| Redis | **本波不引入新键** | 缓存 SKU/夹具/解密凭据 | 点查走唯一键；**禁止**把商户密文放 Redis |

时区：事件 `occurred_at` 仍 UTC，报表切日 Asia/Shanghai（沿用 v2）。`orders` 时间列跟 040 的 `DateTime(timezone=True)` 方言，本波不加第三种。

---

## 1. 数据字典

物理类型：金额继续分 INT；布尔 `TINYINT(1)`；枚举物理 VARCHAR + 应用校验（DBML enum 仅文档）；JSON 仅非查询灵活属性。可空字段必须写 NULL 语义。

### internal_fixture_tenants

一行 = 一家被标为夹具的企业当前在名单上。超管加入 INSERT，移出 DELETE。不加 FK 到 `tenants`（企业软删后名单行仍可被清；事件快照不受影响）。

| 字段 | 类型 | 可空 | 默认 | 说明 / 为什么是这个类型 |
|---|---|---|---|---|
| `id` | INT | 否 | AUTO_INCREMENT | 代理主键（跟仓） |
| `tenant_id` | INT | 否 | — | 被标记的企业。业务唯一。NULL 无意义（PIT-4 禁止平台候选） |
| `created_by` | VARCHAR(64) | 否 | — | 谁标的（超管用户名快照，不加用户 FK） |
| `created_at` | DATETIME | 否 | CURRENT_TIMESTAMP | 何时标上（业务时间=记录时间） |
| `updated_at` | DATETIME | 否 | CURRENT_TIMESTAMP | R-AUD；移出是 DELETE，本列几乎不变 |

**可空性**：无 NULL 列。不在名单 = 没有行，不是 `tenant_id` NULL。

平台级表：禁止 TenantMixin。`tenant_id` 是主语不是隔离归属。同 PR 登记 `TENANT_EXEMPT_TABLES`（PIT-3 同款：有 `tenant_id` 列但不按「当前登录租户」过滤超管维护面）。

### product_events（已有；本特征只加一列）

一行 = 一次已发生的产品事实。追加；应用永不 UPDATE。v1 无精确一次键。

**已有列保持**（DBML 必须写出）：`id`, `occurred_at`, `event_name`, `tenant_id`, `actor_user_id`, `anonymous_id`, `role`, `props`, `created_at`, `updated_at`。

**本特征加列**（接表尾）：

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `is_internal_fixture` | TINYINT(1) | 是 | NULL | **当时**是否夹具企业。`1`=是，`0`=否。`NULL`=本列上线前的旧事件（本特征判定窗不把 NULL 算进非夹具分子） |

写入方在 emit 时 **点查** `internal_fixture_tenants`，把结果快照进本列。禁止查询北极星时 JOIN 名单表。

`is_marketplace_candidate` **仍在 `props` JSON**（v2 合同，本波不升列）。`result_count` / `channel` / `product` / `reason` 仍在 `props`（非查询列）。本波新增事件名（字面量，dba 不改口径）：`task_blocked`、`payment_succeeded`、`payment_failed`。

**可空性**：`is_internal_fixture` NULL=旧行未快照。本波 **不加** NOT NULL（加非空是破坏性，要 expand-contract 第 3 步；判定窗在本列上线之后）。

类型：`TINYINT(1)` 而非 JSON 内布尔——北极星过滤是 Top-N 等值谓词，需要真列。

### orders（已有；本特征加列 + 放宽 + 生成列）

一行 = 一次结账意图。终态 `fulfilled` / `unpaid`（读模型把旧 `paid` 当 fulfilled、旧 `cancelled` 当 unpaid、旧 `pending` 当 checkout_pending）。

**已有列保持**（live 物理序）：

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | INT | 否 | AUTO_INCREMENT | 代理主键 |
| `tenant_id` | INT | **是（live）** | NULL | 所属企业。新结账 **应用必填**。本波 **不**收紧 NOT NULL（存量/040 可空；收紧是破坏性） |
| `plan_id` | INT | **本波放宽为是** | — | FK → `plans.id`。`product_code=relay` 时 NULL。旧行仍有值 |
| `amount_cents` | INT | 否 | — | **下单时金额快照**（分）。通道通知必须与本列一致。不用 FLOAT |
| `status` | VARCHAR(**32**) | 否 | `pending` | **本波 16→32**（`paid_pending_fulfillment` 25 字符）。合法值见 §2.1 |
| `channel` | VARCHAR(16) | 否 | `offline` | 新结账闭集 `alipay`/`wechat`；`offline` 仅存量线下单 |
| `idempotency_key` | VARCHAR(64) | 是 | NULL | 请求级去重（live 全局 UNIQUE）。终态后改键以释放旧 pending 占位。NULL=未用该机制的行 |
| `paid_at` | DATETIME | 是 | NULL | 业务时间：验真通过时刻（与 `verified_at` 同义可双写）；NULL=从未验真通过 |
| `created_at` | DATETIME | 否 | CURRENT_TIMESTAMP | 记录时间（建单） |

**本特征加列**（接表尾）：

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `product_code` | VARCHAR(32) | 是 | NULL | 闭集 `plan_pro` / `plan_enterprise` / `relay`。NULL=040 线下单（无商品码）。**新结账应用必填**（expand 一期可空） |
| `order_no` | VARCHAR(64) | 是 | NULL | 我方送给通道的订单号（通知点查）。NULL=旧行。新结账必填。全局 UNIQUE（多 NULL 合法） |
| `channel_trade_no` | VARCHAR(64) | 是 | NULL | 通道侧交易号。NULL=尚未收到可解析的通知 |
| `merchant_id_snapshot` | VARCHAR(64) | 是 | NULL | **当时**商户号（不是密钥）。验真比「通知商户 / 本列 / 当前凭据商户」。NULL=旧线下单 |
| `fail_reason` | VARCHAR(32) | 是 | NULL | 闭集 `cancel`/`timeout`/`channel_error`/`unconfigured`。NULL=未失败或旧取消单未分类 |
| `late_notify_at` | DATETIME | 是 | NULL | 迟到成功通知到达时刻。NULL=从未记迟到回调 |
| `verified_at` | DATETIME | 是 | NULL | FR-U38 四要素通过时刻。NULL=从未验真通过 |
| `fulfilled_at` | DATETIME | 是 | NULL | 开通完成时刻。NULL=未开通完成 |
| `unpaid_at` | DATETIME | 是 | NULL | 进入 unpaid 时刻。NULL=未入该终态 |
| `open_product_slot` | VARCHAR(32) | 是 | 生成列 | **STORED GENERATED**：`product_code` 非空且 `status IN ('checkout_pending','paid_pending_fulfillment','pending')` 则为 `product_code`，否则 NULL。UNIQUE 与 `tenant_id` 组合 |
| `updated_at` | DATETIME | 否 | CURRENT_TIMESTAMP | R-AUD；状态流转时更新 |

**可空性**：新列一期可空 = expand。NULL 语义见上。禁止把密钥、支付口令、证书口令放进本表任何列或 JSON。

**类型选择**：
- `status` 加宽 16→32 是 **非破坏扩大**（装得下新字面量）。
- `plan_id` NOT NULL→NULL 是 **放宽**，旧代码仍可写该列；新 `relay` 单必须能 NULL。
- 金额不改 DECIMAL：避免类型换族。
- `open_product_slot` 生成列而不是应用双写：唯一约束不能靠「记得去改」。

### payment_channel_credentials

一行 = 一个通道的一套运行凭据。通道闭集两行上限。从未配置 = **零行**（不是空密钥行）。平台级：**不要 `tenant_id` 列**。同 PR 登记 `TENANT_EXEMPT_TABLES`。

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | INT | 否 | AUTO_INCREMENT | 代理主键 |
| `channel` | VARCHAR(16) | 否 | — | `alipay` / `wechat`。业务唯一 |
| `merchant_no` | VARCHAR(64) | 否 | — | 商户号（可掩码展示）。**不是密钥** |
| `secrets_encrypted` | TEXT | 否 | — | 不透明密文 blob（密钥、证书口令等整包）。明文 **永不** 落库、不进 git、不进 yml、不进浏览器、不进日志、不进 Redis |
| `key_version` | INT | 否 | 1 | 每轮换 +1。旧密钥不保留；旧密钥不能履约 **新** 支付（FR-U31.5） |
| `rotated_at` | DATETIME | 是 | NULL | 最近一次轮换。NULL=从未轮换（仅首次保存） |
| `created_by` / `updated_by` | VARCHAR(64) | 是 | NULL | 超管用户名；NULL 仅防御 |
| `created_at` / `updated_at` | DATETIME | 否 | CURRENT_TIMESTAMP | |

**可空性**：`rotated_at` NULL=只有初配没有轮换。行存在则 `merchant_no` 与密文都 NOT NULL（未配 = 删行或根本不插，本波选 **不插**）。

主密钥只在环境/运行配置（与现网 LLM 保险库同级）。本文件 **不选** 算法、不选证书格式、不选回调路径。禁止新增 `config/default/*.yml` 明文商户密钥键。

### relay_sku_entitlements

一行 = 一企业当前中转买没买。`tenant_id` NOT NULL（PIT-4）。**禁止** NULL 表示平台公共 SKU。收款履约 **独占写**；中转产品面只读。专业档/企业档履约 **不得** UPDATE 本表。

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | INT | 否 | AUTO_INCREMENT | 代理主键 |
| `tenant_id` | INT | 否 | — | 本企业。业务唯一 |
| `status` | VARCHAR(16) | 否 | `none` | `none` / `active` / `expired`。见 §2.1 |
| `period_end` | DATETIME | 是 | NULL | 账期结束（当时）。`active` 应用必填。`expired` **保留**到期时刻（快照）。`none` 且从未开通 = NULL |
| `activated_at` | DATETIME | 是 | NULL | 最近一次进入 active。NULL=从未开通 |
| `created_at` / `updated_at` | DATETIME | 否 | CURRENT_TIMESTAMP | |

**可空性**：缺行 ≡ `none`（读路径）。`period_end` NULL 在 `active` 非法（应用拒绝，本波不加 CHECK）。

不加 FK 到 `relay_groups`。组行生命与权益分家。

### plans（已有；本波不加列，只可能种子一行）

一行 = 一条平台价目。live 列：`id, slug, name, price_cents, period, quota_json, is_public, created_at`。DBML 为 R-AUD 与 FK 完整性列出，并 **ADD `updated_at`**（纯加法，无业务语义变化）。

`slug=enterprise` 种子：**价格与配额本帽不编造**，见 §10。`slug=relay` **禁止**插入（中转不是套餐行）。

`tenant_subscriptions` 本波 **不改表**。`plan_pro` / `plan_enterprise` 履约仍写该表 + `tenants.quota`；`relay` 履约只写权益表。

---

## 2. 关系与基数

| 关系 | 基数 | 外键位置 | 可空 | 级联行为 | 说明 |
|---|---|---|---|---|---|
| `plans` → `orders` | 1:N | `orders.plan_id` | 是（本波） | RESTRICT | `relay` 单无套餐行；有 `plan_id` 的单禁止因删价目丢账 |
| 企业 → `orders` | 1:N | `orders.tenant_id` | live 可空 | 无 FK | 跟仓：业务表普遍不加 tenants FK |
| 企业 → `relay_sku_entitlements` | 1:0..1 | `entitlements.tenant_id` | 否 | 无 FK | 一企至多一行 |
| 企业 → `internal_fixture_tenants` | 1:0..1 | `internal_fixture_tenants.tenant_id` | 否 | 无 FK | 在名单或不在 |
| `payment_channel_credentials` | 与租户无关 | — | — | — | 平台 1 通道 1 行 |
| 权益 → 组/令牌 | 无 FK | — | — | — | 读路径闸；隐藏 ≠ 删除 |

默认 RESTRICT。删除逻辑放应用层。凭据表删除通道行 = 该通道回到未配置（结账走 FR-U32），不 CASCADE 订单。

### 2.1 状态流转（有 status 字段的表必填）

与 spec §3.1 / contract §6.4 **同一张**。不一致以 spec 为准，本文件已同步。

#### orders.status

合法值（物理 VARCHAR；DBML enum 仅文档）：

| 值 | 角色 |
|---|---|
| `pending` | **旧**写；读模型视为 `checkout_pending` |
| `paid` | **旧**写；读模型视为 `fulfilled` |
| `cancelled` | **旧**写；读模型视为 `unpaid` |
| `checkout_pending` | 新待支付 |
| `paid_pending_fulfillment` | 验真通过、开通未完成 |
| `fulfilled` | 开通完成（终态） |
| `unpaid` | 取消/超时/通道失败/未配置（终态） |

```
checkout_pending ──FR-U38 验真通过且开通完成──> fulfilled
checkout_pending ──取消/超时/通道失败/未配置──> unpaid
checkout_pending ──验真通过但开通未完成──> paid_pending_fulfillment ──开通完成──> fulfilled
checkout_pending ──伪造或金额/商户/订单号不符──> checkout_pending（保持）
unpaid ──迟到成功通知──> unpaid（记 late_notify_at；不开通）
fulfilled ──重复成功通知──> fulfilled（不开第二份上限）
```

终态：`fulfilled`、`unpaid`。旧值 `paid`/`cancelled` 读作终态，本波不回写改字面量（contract 另波）。

| 流转 | 触发条件 | 谁 | 副作用 |
|---|---|---|---|
| （无行）→ checkout_pending | 买方 POST 结账且非「两通道均未配仅打开」 | 买方 | 写商品码/金额快照/商户快照/`order_no`；占 `open_product_slot` |
| checkout_pending → unpaid | 取消 / 超时 / 通道失败 / 选未配通道去支付 | 系统 | `fail_reason`；`payment_failed`；不改档位/SKU |
| checkout_pending → paid_pending_fulfillment | FR-U38 四要素通过、开通未完成 | 系统 | `verified_at`/`paid_at`；可查 `payment_succeeded`；档位/SKU 仍开通前 |
| paid_pending_fulfillment → fulfilled | 按商品码开通完成 | 系统 | `plan_pro`/`plan_enterprise` 只写订阅；`relay` 只写权益；`fulfilled_at` |
| checkout_pending → fulfilled | 验真+开通在同一临界区完成 | 系统 | 可跳过中间态，仍只开通一次 |
| unpaid 保持 unpaid | 迟到成功通知 | 系统 | `late_notify_at`；无 `payment_succeeded` 因本单；不开通 |

**非法流转**（交 `/qa`）：`unpaid → fulfilled`；伪造/四要素不符 → fulfilled；`fulfilled → unpaid`（本波无退款）；只读/超管代付标 fulfilled；同一成功通知叠加上限；`product=plan_pro` 的开通去写 `relay_sku_entitlements`。

旧 `pending`/`paid`/`cancelled` 本波 **继续可读**。新结账 **只写新字面量**。线下 `confirm_paid` 不勾 GWT-U33/U38。

#### relay_sku_entitlements.status

```
（缺行 ≡ none）
none ──商品=relay 且验真通过且开通完成──> active
active ──到期巡检或运营停用──> expired
expired ──续费且验真通过且开通完成──> active
none ──支付失败/取消/超时──> none
```

终态：无（可续费）。

| 流转 | 触发 | 谁 | 副作用 |
|---|---|---|---|
| none→active（缺行则 INSERT） | 商品=`relay` 履约完成 | 系统 | 可开「我的渠道组」；可签发 |
| active→expired | 到期或停用 | 系统/超管 | 不能签发；旧令牌不可再用（读路径三闸，不 DELETE 令牌行） |
| expired→active | 续费履约完成 | 系统 | 恢复签发 |

**非法**：未支付 none→active；`plan_pro` 成功 → SKU active；伪造通知 → active；租户自助标 active；企业 B 的支付开通 A；超管代付。

`relay_groups.status`（enabled/disabled）**不是**本状态机。

### 2.2 时间字段语义

| 字段 | 类型 | 语义 | 报表口径用哪个 |
|---|---|---|---|
| `orders.created_at` | 记录时间 | 建单 | 待支付库存，不是收入 |
| `orders.verified_at` / `paid_at` | 业务时间 | 验真通过 | 驱动指标 D1 事件用 `product_events.occurred_at`；对账可用本列 |
| `orders.fulfilled_at` | 业务时间 | 开通完成 | 套餐/SKU「已买」以本列为准，不是回跳时间 |
| `orders.unpaid_at` | 业务时间 | 进入未开通终态 | 失败漏斗 |
| `orders.late_notify_at` | 业务时间 | 迟到回调 | 护栏 |
| `product_events.occurred_at` | 业务时间 | 事实发生 | **北极星/D1/D3 用这个** |
| `product_events.created_at` | 记录时间 | 入库 | 一般不用 |
| `relay_sku_entitlements.period_end` | 业务时间 | 账期结束（当时） | 到期巡检 |
| `payment_channel_credentials.rotated_at` | 业务时间 | 轮换 | 旧密钥失效边界 |
| `internal_fixture_tenants.created_at` | 业务时间 | 标上名单 | 不用于北极星（北极星用事件快照） |

时区约定：事件 UTC + 报表 Asia/Shanghai。订单表跟 040 方言。不在同一张表混 `TIMESTAMP` 与 `DATETIME`。

### 2.3 软删决策

| 表 | 加软删 | 理由 |
|---|---|---|
| `internal_fixture_tenants` | 否 | 移出=DELETE；当前态=有没有行。审计靠 `created_by`+事件快照 |
| `orders` | 否 | 账本/历史；豁免矩阵 |
| `payment_channel_credentials` | 否 | 平台配置就地轮换 |
| `relay_sku_entitlements` | 否 | 生命周期在 `status` |
| `product_events` | 否 | 追加表（已有） |
| `plans` | 否 | 价目 |

---

## 3. 唯一键

**业务唯一 ≠ 主键。**

| 唯一约束 | 字段组合 | 业务规则 |
|---|---|---|
| `uk_internal_fixture_tenants_tenant` | `(tenant_id)` | 一企至多一条「在名单」 |
| `uk_orders_idempotency_key` | `(idempotency_key)` | **live**：请求去重；多 NULL 合法 |
| `uk_orders_order_no` | `(order_no)` | 通道通知按我方订单号点查；多 NULL=旧行 |
| `uk_orders_tenant_open_product` | `(tenant_id, open_product_slot)` | **同一企业同一商品同时最多 1 笔非终态待支付**（含旧 `pending` 字面量）。终态行生成 NULL，不占坑。多 NULL 合法 |
| `uk_orders_channel_trade` | `(channel, channel_trade_no)` | 同一通道交易号只绑一单；多 NULL=尚未收到 |
| `uk_payment_channel_credentials_channel` | `(channel)` | 一通道一套运行凭据 |
| `uk_relay_sku_entitlements_tenant` | `(tenant_id)` | 一企一行权益 |
| `plans.slug` | `(slug)` | live；`enterprise` 种子不得撞 `pro`/`free` |

旧 `idempotency_key=pending:{tenant_id}` 仍挡住「每企一笔线下 pending」。新结账 **不得**复用该键格式（否则与商品维度唯一打架）。新键建议 `checkout:{tenant_id}:{product_code}`，终态后改 `fulfilled:{id}` / `unpaid:{id}`（应用约定，非本列 CHECK）。

生成列唯一是「一待支付」的 **约束兜底**；并发下捕获 IntegrityError = 已有未完成支付（GWT-U30.2）。

支付开通精确一次：`UPDATE ... WHERE id=? AND status IN ('checkout_pending','paid_pending_fulfillment')` 影响 0 行则不再 `_apply_plan` / 不再写权益。

---

## 4. 访问模式 Top-N

> 来源：☐ 真实负载  ☐ 调用方代码（billing 现网 list/create/confirm）☑ PRD 推导（**推定**）
>
> 推定依据：contract §7 + spec GWT + 现网 `BillingService.create_order` / `list_orders` / emit 点查。无生产 n。**上线后按真实慢查询复盘补索引。**

| ID | 触发场景（FR / 接口） | 过滤字段（等值 / 范围） | 排序 | 返回列 | 频次（次/天） | P95 要求 | 单次行数 |
|---|---|---|---|---|---|---|---|
| P-U01 | FR-U03 emit 点查是否夹具 | `tenant_id`= | — | tenant_id | 推定：入队/完成每次 1 | 随入队 3s 预算 | 0–1 |
| P-U02 | FR-U20/U23 `/relay` 与令牌闸 | `tenant_id`= | — | status, period_end | 推定：渠道组页+校验 | 页 200ms | 0–1 |
| P-U03 | FR-U03 北极星：超管按发生时间 + 非夹具 | `event_name`= , `is_internal_fixture`= , `occurred_at` 范围 | `occurred_at` | 事件行 | 推定：运营查询 ≪ 1k | 500ms | 页 ≤100 |
| P-U04 | GWT-U30.2 建单占坑 | `tenant_id`= , `open_product_slot`= | — | id, status | 推定：结账 | 去支付 5s | 0–1 |
| P-U05 | FR-U38 通知按订单号点查 | `order_no`= | — | 单据全列（无密钥） | 推定：通道回调 | 验真路径短 | 0–1 |
| P-U06 | GET 本企业订单列表 | `tenant_id`= | `id` DESC（现网） | 订单+套餐名 | 低 | 200ms | ≪100 |
| P-U07 | 验真下单读凭据；超管读回掩码 | `channel`= | — | 行（服务端解密；API 无全文） | 低 | 5s 预算内 | 0–1 |
| P-U08 | 到期巡检 SKU | `status`=active , `period_end`< now | `period_end` | id, tenant_id | 推定：日批 | 批处理 | 开通企业数 |
| P-U09 | 超管维护夹具名单 | 全表 | `created_at` DESC | 名单行 | 极低 | — | 名单长度 |
| P-U10 | FR-U37 支付事件 | `event_name`= , `occurred_at` 范围 | `occurred_at` | 事件行 | 同 P-U03 | 500ms | 页 ≤100 |

排序依据：`频次 × 延迟敏感度`。Top-N 进索引的：**P-U01、P-U02、P-U04、P-U05、P-U07**（均由唯一键覆盖）、**P-U03**（新复合索引）、**P-U10**（已有 `idx_product_events_name_occurred`）。

**已知但不进 Top-N**：
- P-U06 企业订单列表——现网已有 `ix_orders_tenant_id`，单企行数极小，不新建 `(tenant_id, created_at)`
- P-U08 到期扫描——权益表一行一企，全表很小；不建 `(status, period_end)`（status 基数 3）
- P-U09 名单全表——行数=夹具企业数
- 超管 `list_pending_orders` 按 `status=pending`——基数低且本波双读新状态；不单列索引 status
- 按 `fail_reason` / `late_notify_at` 筛——护栏人工对账，非 Top-N

---

## 5. 索引设计

| 索引 | 字段顺序 | 服务模式 | 列顺序理由（ESR） |
|---|---|---|---|
| `PRIMARY`（各表 `id`） | `id` | — | 代理主键 |
| `uk_internal_fixture_tenants_tenant` | `(tenant_id)` | P-U01 | 等值点查；兼业务唯一 |
| `uk_relay_sku_entitlements_tenant` | `(tenant_id)` | P-U02 | 等值点查；兼业务唯一 |
| `uk_payment_channel_credentials_channel` | `(channel)` | P-U07 | 等值点查；兼业务唯一 |
| `uk_orders_order_no` | `(order_no)` | P-U05 | 等值点查 |
| `uk_orders_tenant_open_product` | `(tenant_id, open_product_slot)` | P-U04 | 等值+等值；多租户最左 tenant |
| `uk_orders_channel_trade` | `(channel, channel_trade_no)` | 约束（非 Top-N 查询） | 通道侧交易号不重复 |
| `uk_orders_idempotency_key` | `(idempotency_key)` | live 请求去重 | 已有 |
| `ix_orders_tenant_id` | `(tenant_id)` | P-U06 | **live 保留**，禁止 DROP |
| `idx_product_events_name_occurred` | `(event_name, occurred_at)` | P-U10（v2 P-E01） | **live 保留** |
| `idx_product_events_tenant_occurred` | `(tenant_id, occurred_at)` | v2 P-E02 | **live 保留** |
| `idx_product_events_name_fixture_occurred` | `(event_name, is_internal_fixture, occurred_at)` | P-U03 | 等值 event_name → 等值夹具 → 范围/排序 occurred_at |

**已评估不建的索引**：

| 候选 | 不建的理由 |
|---|---|
| `(status)` on orders / entitlements | 基数 ≤7 / 3；不单独作最左列 |
| `(tenant_id, created_at)` on orders | P-U06 非 Top-N；已被 `ix_orders_tenant_id` 前缀 |
| `(status, period_end)` on entitlements | P-U08 非 Top-N；表小 |
| `product_events` 上 `props` 函数索引 | JSON 非查询列；`result_count` 过滤在应用/JSON，本波量级为运营查询 |
| 凭据表按 `key_version` | 无按版本列表模式 |
| 名单表 `(created_by)` | 无按人查模式 |
| 单列 `is_internal_fixture` | 基数 3（0/1/NULL）；只作 P-U03 复合非最左 |

---

## 6. Redis 键

本特征 **不引入新 Redis 键**。

| 候选 | 不建的理由 |
|---|---|
| `relay:sku:{tenant_id}` | P-U02 是唯一键点查，一行一企 |
| `saas:fixture_tenants` | P-U01 唯一键点查；名单极短 |
| `billing:cred:{channel}` | **禁止**缓存可解密材料；验真走库内密文+进程内保险库 |
| `billing:open:{tenant}:{product}` | 占坑真相是 UNIQUE 生成列，不是锁键 |

无 TTL 例外需要声明。Redis 不可用：直接查库（本波本就无缓存依赖）。

---

## 7. 数据量与增长

无生产 n。推定（Reach 未量化）：

| 表 | 当前行数 | 日增 | 一年后预估 | 分表/归档策略 |
|---|---|---|---|---|
| `internal_fixture_tenants` | 0 | ≈0 | ≪100 | 不需要 |
| `payment_channel_credentials` | 0 | ≈0 | 2 | 不需要 |
| `relay_sku_entitlements` | 0 | 开通企业数 | ≤租户数 | 不需要 |
| `orders` | 现网线下单极少 | 结账次数 | 万级以下仍不必分 | 不需要；事件 90d 沿用 v2 |
| `product_events` | v2 已有 | 完成/拦住/支付 | 沿用 v2 ≥90d 保留 | 本波不加分区 |

---

## 8. 破坏性变更

**本波不对应用代码构成「一步改枚举」**：旧 `pending/paid/cancelled` 仍在列中。下列是 **expand / 放宽**，不是 DROP 列。

| 变更 | 类型 | 步骤 |
|---|---|---|
| `orders.status` VARCHAR(16)→(32) | 非破坏扩大 | 单步 MODIFY。先于写入 `paid_pending_fulfillment` |
| `orders.plan_id` NOT NULL→NULL | 放宽 | 单步 MODIFY NULL。先于 `relay` 建单 |
| `orders` 新可空列 + 生成列唯一 | 纯加法 | 单步 ADD。生成列依赖 `status`/`product_code`，与加列同迁移 **可以**（无旧 `product_code`，槽全 NULL） |
| `product_events.is_internal_fixture` 可空 | 纯加法 | 单步 ADD + 新索引 |
| 三张新表 | 纯加法 | CREATE |
| `plans.updated_at` | 纯加法 | ADD，服务 R-AUD / 跟仓审计 |
| 旧 status 字面量收缩（不再认 `pending`） | **破坏性** | **本波不做**。他日 3 步：双写已稳 → 回填 UPDATE → 文档去掉旧值。禁止本波 DROP 旧值 |
| `orders.tenant_id` 收紧 NOT NULL | **破坏性** | **本波不做**（040 可空；先查孤儿再 contract） |
| `product_code` 收紧 NOT NULL | **破坏性** | **本波不做**（expand 一期可空） |
| 删除 `relay_groups` 骨架行 | **破坏性** | **本波禁止**（ADR-0025） |

N1 迁移（T-01）与 N3 迁移（T-14）**拆文件**：禁止把凭据/SKU/订单状态机放进采集 2 人周。

`up → down → up` 证据：本帽不写 Alembic 文件（ADR-0002：路径由 autogenerate 产出）。交下游 migration-review 实跑三段并贴退出码。生成列 `down` = DROP 生成列/唯一键再 DROP 基列。

加唯一键前重复检查（合同要求，本波新列全 NULL，预期 0 行重复）：

```sql
SELECT tenant_id, open_product_slot, COUNT(*) c
  FROM orders
 GROUP BY tenant_id, open_product_slot
HAVING c > 1 AND open_product_slot IS NOT NULL;
-- 期望 0
```

---

## 9. 需真库验证的方言特性（交给 /qa）

- **STORED GENERATED + UNIQUE**（`orders.open_product_slot`）：SQLite 测试库与 MySQL 8 生成列/NULL 唯一语义不完全同构。必须 MYSQL_FIDELITY：两笔同企同商品 `checkout_pending` 第二笔 IntegrityError；一笔 `fulfilled` 后可再插。
- **UNIQUE 多 NULL**：`order_no` / `channel_trade_no` / `open_product_slot` 旧行全 NULL 不得互撞。
- **VARCHAR(16)→(32) INPLACE**：`SHOW CREATE TABLE orders` 确认 `paid_pending_fulfillment` 可写入。
- **`plan_id` NULL + LEFT JOIN**：`product_code=relay` 列表不得因 INNER JOIN `plans` 丢行（实现帽；本帽不写查询代码）。
- **加密列**：库内 `secrets_encrypted` 不得等于任何明文密钥；超管读模型无全文（行为测，不是 EXPLAIN）。
- **禁止 git/yml 明文**：GWT-U31.4 仓库跟踪文件扫描，不是 SQLite 能代替。
- EXPLAIN 本波 **未跑真库**（无生产负载、本帽不改运行库）。下列 SQL 交 S4 行为环贴 raw 输出。

推定计划（不是证据）：

```sql
-- P-U01
EXPLAIN SELECT tenant_id FROM internal_fixture_tenants WHERE tenant_id = ?;
-- 期望 type=const/eq_ref key=uk_internal_fixture_tenants_tenant

-- P-U02
EXPLAIN SELECT status, period_end FROM relay_sku_entitlements WHERE tenant_id = ?;
-- 期望 eq_ref uk_relay_sku_entitlements_tenant

-- P-U03
EXPLAIN SELECT id, tenant_id, occurred_at, is_internal_fixture
  FROM product_events
 WHERE event_name = 'task_completed'
   AND is_internal_fixture = 0
   AND occurred_at >= ? AND occurred_at < ?
 ORDER BY occurred_at;
-- 期望 key=idx_product_events_name_fixture_occurred 无 Using filesort（排序列在索引内）

-- P-U04
EXPLAIN SELECT id, status FROM orders
 WHERE tenant_id = ? AND open_product_slot = 'plan_pro';
-- 期望 eq_ref uk_orders_tenant_open_product

-- P-U05
EXPLAIN SELECT * FROM orders WHERE order_no = ?;
-- 期望 const/eq_ref uk_orders_order_no

-- P-U07
EXPLAIN SELECT id, merchant_no, secrets_encrypted, key_version
  FROM payment_channel_credentials WHERE channel = 'alipay';
-- 期望 const uk_payment_channel_credentials_channel

-- P-U10（live）
EXPLAIN SELECT id FROM product_events
 WHERE event_name = 'payment_succeeded' AND occurred_at >= ?
 ORDER BY occurred_at;
-- 期望 idx_product_events_name_occurred
```

判读红线：大表 `type=ALL` 且无说明；意外 `Using filesort` / `Using temporary`。P-U03 在事件量小的判定窗即使 ALL 也可接受——仍要贴 raw。

---

## 10. 开放问题

| 问题 | 阻塞什么 | 需要谁定 |
|---|---|---|
| `plans.slug=enterprise` 的 `price_cents` 与 `quota_json` | 企业档种子行与金额快照从哪来。**不阻塞表结构**。阻塞把 0 元当可履约价 | /pm（本帽不编造标价） |
| 中转 SKU 账期长度（月/年/与套餐是否相同） | 不阻塞列；阻塞 `period_end` 的计算。未答前履约不得发明第二套日历 | /pm；未答则不得把「专业档 30 天」偷偷套到 relay |
| 旧 `orders.pending` 是否回填 `product_code` | 不回填则旧线下 pending **不占** `open_product_slot`（因 product_code NULL） | /pm；建议不回填、线下与在线坑分开 |
| Q-AGPL | 不阻塞本 schema | operator（非本帽） |

---

## 11. 给下游的手递（非 API、非 Service）

| 谁 | 必须知道 |
|---|---|
| `/backend` ORM | 三新表；`orders`/`product_events`/`plans` 只加列+放宽；`payment_channel_credentials` 与 `internal_fixture_tenants` **无 TenantMixin**、同 PR 进 `TENANT_EXEMPT_TABLES`；`relay_sku_entitlements` **有** `tenant_id` NOT NULL、**不**豁免；读订单双认旧 status；`relay` 单 `plan_id` NULL → 列表不可 INNER JOIN 丢行；emit 写 `is_internal_fixture` 快照；履约按 `product_code` 分支，禁止专业档写权益 |
| `/qa` | §2.1 非法流转；§9 方言；夹具改名单后旧事件快照不变；组行仍在但 SKU≠active 时产品面当不存在 |
| `/sre` | 密钥不进镜像/yml；通知幂等在单据状态；无新 Redis 键 |
| 实现迁移 | N1≠N3 文件；autogenerate；生成列补丁允许；`up→down→up` 贴退出码 |

**配置红线**：支付宝/微信商户密钥、证书口令 **不得** 出现在 git 跟踪文件、`config/default|local|dev|prod`、`.env.example`。主密钥只走环境。本文件不新发明文配置键名。
