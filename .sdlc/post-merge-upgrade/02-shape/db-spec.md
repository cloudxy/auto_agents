# db-spec · post-merge-upgrade

> 上游：PRD `01-define/spec.md` **v1.7**（FR-M10…M15、M20/M26、M31、M12；[SEC-3]）｜方案 `02-shape/contract.md` §7｜[ADR-0026](adr-0026-two-legal-fulfill-paths.md)
> 下游：`schema.dbml` → Alembic **autogenerate**（禁手写全量 SQL；本帽 **不写** `backend/alembic/`）→ `/backend` ORM
> 泳道：L3｜作者：/dba｜日期：2026-09-13｜修订：shape r1 QA-03/QA-04
> 本文件只补合入后 W2 两条合法开通 + 价目/配额对齐 + 出站查找集合。upgrade `02-shape/db-spec.md`（046）仍是结账单据/凭据/SKU 基线，**不复制**。
> **已有表 IR**：被改表 = live（046）全列 ∪ 本特征变更。禁止 stub。漏 live 列 = autogenerate DROP。
> Alembic 头现行 **046**。本波目标修订 **047**（数据 + 一处放宽）。禁止复活 028/029/030。生产禁止 downgrade past 037。
> 通道闭集仍 `alipay`/`wechat` + 确认收款。**禁止** Stripe / 兑换码 / 易支付 表或列。
> 本帽不写 Service / Repository / API。

访问模式先于索引。本波无生产 slow_query：§4 全部 **推定**；§9 EXPLAIN 在本机 046 形抛掷表跑过（live 库 `alembic_version=039`，不能当 046 证据）。上线后按真实慢查询复盘。

**本波结论：不新建表。** 改编排既有 `orders` / `plans` / `relay_sku_entitlements` / `outbound_keys` / `tenants.quota`。

---

## 0. 实体与粒度（建模第一步的产出）

| 实体（表名） | 一行代表什么 | 来源 FR | 别名归并 |
|---|---|---|---|
| `orders` | 一次结账意图（商品码闭集） | FR-M11/M31；ADR-0026 | 「待支付」「结账单据」；**不是**用量页第二套线下单 |
| `plans` | 一条平台价目（档位） | FR-M12；[SEC-3] | 「专业档/企业档标价+执法配额」；`slug=relay` **禁止** |
| `relay_sku_entitlements` | 一企业当前中转买没买 | FR-M12/M23；ADR-0026 | 「中转已开通」；有组行 ≠ 已买 |
| `outbound_keys` | 一把在出站入口签发的本企业钥匙 | FR-M20/M26；[SEC-2] | 「出站拉数钥匙」；**不是** `api_keys` / `relay_tokens` |
| `tenant_subscriptions` | 一企业当前订阅（一企一行） | FR-M12 | 履约写档；本波不改表 |
| `tenants` | 一家企业；`quota` JSON 是执法上限 | FR-M12.6/12.8 | 入队/规划读这里，不读订单文案 |
| `product_events` | 一次产品事实（追加） | FR-M14/M06/M26 | 本波只加事件名字面量，不加列 |

**粒度必须能用一句话写出来。**

**被判定为「不是实体」的名词**：

| 名词 | 判定 | 理由 |
|---|---|---|
| 待支付 / 已开通 | `orders.status` 字段 | W2 闭集两态；不是两张表 |
| 确认收款 | 对 `orders` 的 CAS 写 | 不建 `confirmations` 表；精确一次靠 `status` |
| 支付网关 / Stripe | 外部；本波不做 | 通道闭集 alipay/wechat；确认路径不读密钥 |
| 官网「定制」 | 营销文案 | **不是** SEC-3 比对面；比对面 = 存储分 |
| 中转展示价 | 运行配置整数分 | `BILLING.RELAY_PRICE_CENTS`（配置价，非密钥）。禁止 `plans.slug=relay` |
| 迟到回调 | `orders.late_notify_at` | 已有列 |
| 出站明文 | 不落库 | 只存 hash+prefix |
| `api_keys` / `relay_tokens` | 已有别平面 | 拉数命中集合 **不含** 这两张；本波不 DROP |
| 第二套 `POST /orders` 单据 | 停写 | 旧 `pending`+`product_code` NULL 行保留；不占 `open_product_slot` |

**FR 覆盖核对**：

| FR | 涉及实体 | 承载字段 | 缺口 |
|---|---|---|---|
| FR-M10 / M13 | `orders` 停写第二套 | 旧入口不 INSERT | 无 DDL |
| FR-M11 | `orders` | `checkout_pending`/`fulfilled`；`open_product_slot` 唯一；通道可空 | 046 已有生成列；本波放宽 `channel` NULL |
| FR-M11 [SEC-3] / M31 | `orders.amount_cents` + `plans.price_cents` + 中转配置分 | 确认：本笔 id + 快照分 = 当前展示分 | 企业档种子行缺失；040 `pro.quota_json` 错 |
| FR-M12 | `plans.quota_json` → `tenants.quota`；SKU 表 | 专业档 50/200000/5000000；`plan_pro` 不写 SKU；`plan_enterprise`/`relay` 写 SKU | 040 种子 20/500000/5000000；企业档履约未写 SKU（应用） |
| FR-M14 | `product_events.event_name` | 字面量；无新列 | 无 DDL |
| FR-M20/M26 | `outbound_keys` | `key_hash` 等值 + `revoked_at IS NULL` | 查找集合收口（应用）；表已有 |
| FR-M23 | `relay_sku_entitlements.status` | 读路径按企业点查 | 无 DDL |

### 0.1 建模决策记录（有取舍的才写）

| 决策 | 选了什么 | 备选 | 理由 |
|---|---|---|---|
| 结账意图 | **扩既有 `orders`**，不新建表 | `payment_intents` / 确认流水表 | 046 已有单据+生成列唯一；再建一张会双写 |
| 金额「当时」 | `orders.amount_cents` **快照**（分，INT） | 每次 JOIN 价目 | 价目改价不得改历史单；通道通知 [SEC-1] 对快照 |
| 金额「现在」[SEC-3] | 确认时把快照与 **当前展示分** 比较 | 只信快照 / 只信官网「定制」 | GWT-M31.4/6：不符则保持待支付。展示分：`plan_pro`=`plans.pro.price_cents`=29900；`plan_enterprise`=`plans.enterprise.price_cents`≠29900；`relay`=`BILLING.RELAY_PRICE_CENTS`≠29900 |
| 企业档标价 | **种子 `plans.slug=enterprise`**，`price_cents=99900` | 继续只靠测试夹具 / 把「定制」当金额 | 夹具已用 99900；本帽不把该数字升格为官网营销价。pm 可 UPDATE 一行，列不改。禁止 0 或 29900 |
| 中转展示分 | **配置整数**，不进 `plans` | `plans.slug=relay` / 新价目表 | ADR-0026「配置价」+ 禁止 slug=relay。密钥不进 git；价格不是密钥，可进 `config/<env>` 或 `AUTO_AGENTS_BILLING__RELAY_PRICE_CENTS` |
| 专业档执法 | **UPDATE** `plans.pro.quota_json` 为定价页三数字 | 改 040 已应用迁移 / 回放历史订单 | 禁止改已应用迁移。合同：旧租户不靠改历史订单回放；新确认从价目 JSON 写入 `tenants.quota` |
| 一企一商品一待支付 | **沿用** 046 生成列 UNIQUE | 只先查后插 | GWT-M11.12；冲突 = IntegrityError →「已有待支付」 |
| 未配通道 | `orders.channel` **放宽 NULL 且 DROP DEFAULT** | 留 `server_default=offline` / 省略列靠默认 | 合同 §7「通道可空」。W2 未配 INSERT **必须显式** `channel=NULL`。`offline` **只**留 040 存量行，047 不回写、W2 不新写 |
| 确认精确一次 | `UPDATE ... WHERE id=? AND status='checkout_pending' AND amount_cents=?` 影响 0 行则不再履约 | 新 `version` 列 | 已有状态机足够；金额谓词挡住改行套 ¥299 |
| 企业档写 SKU | **同一张** `relay_sku_entitlements` | 企业档另表 | ADR-0026 supersede「仅 relay 写 SKU」。`plan_pro` 仍不得写 |
| 出站命中集合 | 只 `outbound_keys` | 三环（+`api_keys`+KEY_BINDINGS） | [SEC-2]；KEY_BINDINGS 保持平台绑定，不进租户产品名、不进拉数命中 |
| 主键 / 金额类型 | 跟仓 INT；分 INT | BIGINT / DECIMAL | 改类型破坏性，本波不做 |
| Redis | **不引入新键** | 缓存价目/SKU/确认锁 | 占坑真相是 UNIQUE；禁止缓存商户密文 |

时区：`orders` 跟 040 `DateTime(timezone=True)` 方言。新语义不引入第三种。事件 UTC，报表切日 Asia/Shanghai（沿用）。

---

## 1. 数据字典

物理类型：金额继续分 INT；枚举物理 VARCHAR + 应用校验；JSON 仅非查询灵活属性（`quota_json` / `tenants.quota` 是履约写入的整包，点查按租户 PK，不按 JSON 键索引）。

### orders（已有；本特征放宽 `channel`）

一行 = 一次结账意图。W2 新写只 `checkout_pending` / `fulfilled`。读模型仍认识旧 `pending`/`paid`/`cancelled`。

**046 live 列保持**（物理序）：

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | INT | 否 | AUTO_INCREMENT | 代理主键。确认按主键点查 [SEC-3] |
| `tenant_id` | INT | **是（live）** | NULL | 新结账应用必填。本波 **不**收紧 NOT NULL |
| `plan_id` | INT | 是 | — | FK → `plans.id`。`product_code=relay` 时 NULL |
| `amount_cents` | INT | 否 | — | **下单时展示金额快照（分）**。确认必须与当前价目展示分相等 |
| `status` | VARCHAR(32) | 否 | `pending` | 见 §2.1。W2 写 `checkout_pending`/`fulfilled` |
| `channel` | VARCHAR(16) | **本波放宽为是** | **无（DROP `DEFAULT 'offline'`）** | 闭集 `alipay`/`wechat`。**NULL=W2 未选通道/两通道未配**（INSERT 必须写出 `channel=NULL`，禁止省略列、禁止新写 `offline`）。字面量 `offline` **只**出现在 040 第二套存量行 |
| `idempotency_key` | VARCHAR(64) | 是 | NULL | 请求去重。新结账用 `order_no`，禁止复用 `pending:{tenant_id}` |
| `paid_at` | DATETIME | 是 | NULL | 确认收款或通道验真通过。NULL=从未 |
| `created_at` | DATETIME | 否 | CURRENT_TIMESTAMP | 建单记录时间 |
| `product_code` | VARCHAR(32) | 是 | NULL | 闭集 `plan_pro`/`plan_enterprise`/`relay`。NULL=040 线下单 |
| `order_no` | VARCHAR(64) | 是 | NULL | 我方订单号。NULL=旧行 |
| `channel_trade_no` | VARCHAR(64) | 是 | NULL | 通道侧交易号。W2 确认路径保持 NULL |
| `merchant_id_snapshot` | VARCHAR(64) | 是 | NULL | 当时商户号，不是密钥。未配通道 NULL |
| `fail_reason` | VARCHAR(32) | 是 | NULL | W2 写路径不产生 `unpaid`，本列 W2 保持 NULL |
| `late_notify_at` | DATETIME | 是 | NULL | 迟到回调。GWT-M11.11/18 |
| `verified_at` | DATETIME | 是 | NULL | FR-U38 通道路径。确认收款 **不**要求本列 |
| `fulfilled_at` | DATETIME | 是 | NULL | 开通完成 |
| `unpaid_at` | DATETIME | 是 | NULL | W2 不写入 |
| `open_product_slot` | VARCHAR(32) | 是 | 生成列 | STORED：`product_code` 非空且 `status IN ('checkout_pending','paid_pending_fulfillment','pending')` 则为 `product_code`，否则 NULL |
| `updated_at` | DATETIME | 否 | CURRENT_TIMESTAMP | R-AUD |

**本特征变更**：`channel` 可空 **且** 去掉 `DEFAULT 'offline'`。禁止密钥/口令入任何列。

**可空性**：`channel` NULL = 未选在线通道（W2 未配仍可待支付）。不是「未知历史」，也不是省略列撞上旧默认。ORM/迁移不得再带 `server_default='offline'` 或 Python `default='offline'`。

W2 未配通道建单（库级，非 API 形状）：

```sql
INSERT INTO orders (tenant_id, plan_id, amount_cents, status, channel, product_code, order_no, ...)
VALUES (?, ?, ?, 'checkout_pending', NULL, ?, ?, ...);
-- channel 列必须出现在列清单里，值必须是 SQL NULL
-- 禁止：省略 channel（旧 DEFAULT 会写成 offline）
-- 禁止：W2 新行 channel='offline'
```

### plans（已有；本波数据，不加列）

一行 = 一条平台价目。TENANT_EXEMPT。live 列：`id, slug, name, price_cents, period, quota_json, is_public, created_at, updated_at`。

| slug | `price_cents` | `quota_json` 执法 | 本波动作 |
|---|---|---|---|
| `free` | 0 | 5 / 10000 / 200000 | 不动 |
| `pro` | **29900** | **50 / 200000 / 5000000**（定价页；FR-M12 金标） | **UPDATE** 040 种子 20/500000/5000000 |
| `enterprise` | **99900**（≠29900；SEC-3 展示分） | **必须存在且 ≠ 专业档三数字**。具体三数 **未冻**（见 §10） | **INSERT** 若缺行 |
| `relay` | — | — | **禁止**插入 |

`quota_json` 键：`task_concurrency` / `result_storage` / `llm_tokens_month`。履约整包写入 `tenants.quota`。再确认不叠（CAS 0 行）。

**不编造新标价**：99900 来自现网测试夹具（contract 已点名 ¥999）。官网「定制」不是结账展示。pm 改价 = UPDATE 这一行。

**企业档配额（QA-04）**：T-08 **只**保证履约写入的 JSON **不等于**专业档 `{50, 200000, 5000000}`。测试夹具 `50/2000000/20000000` **不是** T-08 金标、**不**写入冻结 FR。047 种子用任一键齐全、正整数、且 ≠ 专业档三数字的占位包；`/pm` 写出句子后再 UPDATE 一行。

### relay_sku_entitlements（已有；本波不改列）

一行 = 一企业当前中转买没买。`tenant_id` NOT NULL，不进 TENANT_EXEMPT。缺行 ≡ `none`。

写入者（ADR-0026）：商品=`relay` **或** `plan_enterprise` 履约 → `active`。商品=`plan_pro` **不得**改本行。不 FK 到 `relay_groups`；不删组行。

列保持 046：`id, tenant_id, status, period_end, activated_at, created_at, updated_at`。

### outbound_keys（已有；本波不改列）

一行 = 一把本企业出站拉数钥匙。`tenant_id` NOT NULL，禁止豁免。明文不落库。

拉数命中：**只** `key_hash` 等值且 `revoked_at IS NULL`。命中集合不含 `relay_tokens` / `api_keys`。KEY_BINDINGS 不是本表行。

### tenants.quota / tenant_subscriptions

不改表。履约：`plan_pro`/`plan_enterprise` 写订阅 + `tenants.quota`；`relay` 只写 SKU，免费三数字保持。

### 中转展示分（非表）

| 键 | 类型 | 约束 |
|---|---|---|
| `BILLING.RELAY_PRICE_CENTS` | INT 分 | **>0 且 ≠29900**。未设或 0 = 结账/确认不可构造（非法）。现网夹具 19900。不是密钥，禁止与商户密文放同一 blob |

---

## 2. 关系与基数

| 关系 | 基数 | 外键位置 | 可空 | 级联 | 说明 |
|---|---|---|---|---|---|
| `plans` → `orders` | 1:N | `orders.plan_id` | 是 | RESTRICT | relay 单无套餐行 |
| 企业 → `orders` | 1:N | `orders.tenant_id` | live 可空 | 无 FK | 跟仓 |
| 企业 → `relay_sku_entitlements` | 1:0..1 | `tenant_id` UNIQUE | 否 | 无 FK | |
| 企业 → `outbound_keys` | 1:N | `tenant_id` | 否 | 无 FK | |
| `plans` → `tenant_subscriptions` | 1:N | `plan_id` | 否 | RESTRICT | 一企一行订阅 |

运营台列表必须 **LEFT JOIN** `plans`（relay 单 `plan_id` NULL，INNER JOIN 会丢行）。JOIN `tenants` 取企业名。返回列含 `amount_cents`（展示金额）。

### 2.1 状态流转

与 spec §3.1 / ADR-0026 **同一张**。不一致以 spec 为准，本文件已同步。

#### orders.status

| 值 | 角色 | W2 写路径 |
|---|---|---|
| `pending` | 旧写；读作待支付 | 不新写 |
| `paid` | 旧写；读作已开通 | 不新写 |
| `cancelled` | 旧写；读作 unpaid | 不新写 |
| `checkout_pending` | 待支付 | **是** |
| `fulfilled` | 已开通（终态） | **是** |
| `paid_pending_fulfillment` | live 处理中 | **否** |
| `unpaid` | live 未完成 | **否** |

```
（无单）──买方结账提交──> checkout_pending
checkout_pending ──超管确认本笔且 amount_cents=当前展示分──> fulfilled
checkout_pending ──FR-U38 验真且开通完成──> fulfilled     （live；W2 不放行此边）
checkout_pending ──金额/错单──> checkout_pending（保持）
fulfilled ──再确认──> fulfilled（no-op，不叠配额）
fulfilled ──迟到通道成功通知──> fulfilled（记 late_notify_at；不叠）
```

终态（W2）：`fulfilled`。`checkout_pending` 可被确认，不是终态。

| 流转 | 触发 | 谁 | 副作用 |
|---|---|---|---|
| 无行 → checkout_pending | 买方提交；未配通道仍建行 | 买方 | 快照金额/商品码；占 `open_product_slot`；**显式** `channel=NULL`（不是省略列、不是 `offline`） |
| checkout_pending → fulfilled | 超管确认 **本 id** 且快照分=当前展示分 | 超管 | 按商品码履约一次；`fulfilled_at`/`paid_at`；`plan_pro` 写专业档三数字、SKU 不变；`plan_enterprise` 写企业档配额 **且** SKU active；`relay` 只 SKU active |
| checkout_pending 保持 | 金额不符 / 错单 / 非超管 | 系统 | 配额/SKU 不变 |
| fulfilled 保持 | 再确认 / 迟到通知 | 系统 | 不叠；迟到写 `late_notify_at` |

**非法流转**（交 `/qa`）：租户自标 fulfilled；错单确认；企业档/`relay` 写成 29900 却开通；`plan_pro` → SKU active；两笔同企同商品同时 pending；已开通再叠配额；W2 写出 `unpaid`/`paid_pending_fulfillment`；未验真通道通知 → fulfilled（通道路径，不覆盖确认边）。

开通 CAS（库级，非 Service 形状）：

```sql
UPDATE orders
   SET status = 'fulfilled',
       fulfilled_at = ?,
       paid_at = ?,
       updated_at = ?
 WHERE id = ?
   AND status = 'checkout_pending'
   AND amount_cents = ?;   -- ? = 当前展示分（pro=plans.pro.price_cents 等）
-- rowcount=0 → 拒绝；不得 _apply_plan / 不得 activate SKU
```

#### relay_sku_entitlements.status

```
（缺行 ≡ none）
none ──商品=relay 或 plan_enterprise 履约──> active
active ──到期/停用──> expired
expired ──续费履约──> active
```

**非法**：`plan_pro` → active；未开通 none→active；租户自助标 active。

### 2.2 时间字段语义

| 字段 | 语义 | 报表 |
|---|---|---|
| `orders.created_at` | 建单 | 待支付库存，不是收入 |
| `orders.paid_at` / `fulfilled_at` | 确认或通道开通完成 | 「已开通」以 `fulfilled_at` 为准 |
| `orders.late_notify_at` | 迟到回调 | 护栏 |
| `product_events.occurred_at` | 事实发生 | 事件查询 |

### 2.3 软删决策

| 表 | 软删 | 理由 |
|---|---|---|
| `orders` | 否 | 账本 |
| `plans` | 否 | 价目 |
| `relay_sku_entitlements` | 否 | 生命周期在 status |
| `outbound_keys` | 否 | 吊销= `revoked_at` 终态 |

---

## 3. 唯一键

| 唯一约束 | 字段 | 业务规则 |
|---|---|---|
| `uk_orders_tenant_open_product` | `(tenant_id, open_product_slot)` | **同一企业同一商品同时最多 1 笔非终态待支付**。终态生成 NULL。禁止只先查后插 |
| `uk_orders_order_no` | `(order_no)` | 通知点查；多 NULL=旧行 |
| `uk_orders_channel_trade` | `(channel, channel_trade_no)` | 通道交易号不重复；多 NULL 合法。`channel` NULL 时本约束不挡（MySQL UNIQUE 遇 NULL 失效）——W2 确认路径无 `channel_trade_no` |
| `idempotency_key` | `(idempotency_key)` | live 请求去重 |
| `plans.slug` | `(slug)` | `enterprise` 不得撞 `pro`/`free` |
| `uk_relay_sku_entitlements_tenant` | `(tenant_id)` | 一企一行 |
| `uk_outbound_keys_key_hash` | `(key_hash)` | 拉数点查 |
| `uq_tenant_subscriptions_tenant` | `(tenant_id)` | 一企一行订阅；再确认不插第二行 |

新结账 `idempotency_key` 不得用 `pending:{tenant_id}`（与商品维度唯一打架）。

---

## 4. 访问模式 Top-N

> 来源：☐ 真实负载  ☑ 调用方代码（`billing_service` / `order_repository` / `outbound_key_service`）☑ PRD 推导（**推定**）
>
> 推定依据：contract §7、GWT-M11/M12/M20/M31、现网 `confirm_paid` 拒结账单、`list_pending_orders` 只查 `pending`。无生产 n。**上线后按真实慢查询复盘。**

| ID | 触发场景 | 过滤 | 排序 | 返回 | 频次 | P95 | 行数 |
|---|---|---|---|---|---|---|---|
| P-M01 | GWT-M11.12 建单占坑 | `tenant_id`= , `open_product_slot`= | — | id, status | 结账 | 5s 预算 | 0–1 |
| P-M02 | FR-M11 确认本笔+金额 | `id`= , `status`= , `amount_cents`= | — | 单据 | 超管确认 | 同步 | 0–1 |
| P-M03 | FR-M31 运营台待确认 | `status IN ('checkout_pending','pending')` | `id` DESC | 单+企业名+展示分 | 低 | 200ms | ≪100 |
| P-M04 | 结账预览/SEC-3 展示分 | `plans.slug`= | — | price_cents, quota_json | 结账/确认 | 5s | 0–1 |
| P-M05 | FR-M20 出站拉数 | `key_hash`= (`revoked_at` 应用滤) | — | tenant_id | 拉数 | 页预算 | 0–1 |
| P-M06 | FR-M23 中转闸 | `tenant_id`= | — | status, period_end | 渠道组 | 200ms | 0–1 |
| P-M07 | FR-M12 执法读配额 | `tenants.id`= | — | quota | 入队/规划 | 3s | 1 |
| P-M08 | FR-M14 超管查事件 | `event_name`= , `occurred_at` 范围 | `occurred_at` | 事件行 | 运营 | 500ms | ≤100 |
| P-M09 | 本企业订单列表 | `tenant_id`= | `id` DESC | 订单 | 低 | 200ms | ≪100 |

Top-N 进索引：**P-M01/M02/M04/M05/M06/M07** 由已有 UNIQUE/PK 覆盖；**P-M08** 已有 `idx_product_events_name_occurred`。

**已知但不进 Top-N**：
- P-M03 运营台按 status —— 基数低、表小；走 PRIMARY 倒扫（见 §9）。不建 `(status)`
- P-M09 企业列表 —— `ix_orders_tenant_id` 已有；不建 `(tenant_id, id)`（filesort 在单企行数下可接受）
- 按 `fail_reason` / `late_notify_at` —— 人工对账
- 出站 `(tenant_id, created_at)` —— 已有，服务列表不服务拉数点查

---

## 5. 索引设计

| 索引 | 字段顺序 | 服务模式 | ESR |
|---|---|---|---|
| `PRIMARY` `orders.id` | `id` | P-M02 | 确认点查 |
| `uk_orders_tenant_open_product` | `(tenant_id, open_product_slot)` | P-M01 | 等值+等值 |
| `uk_orders_order_no` | `(order_no)` | 通道路径（live） | 等值 |
| `ix_orders_tenant_id` | `(tenant_id)` | P-M09 | **046 保留**，禁止 DROP |
| `plans.slug` | `(slug)` | P-M04 | 等值 |
| `uk_relay_sku_entitlements_tenant` | `(tenant_id)` | P-M06 | 等值 |
| `uk_outbound_keys_key_hash` | `(key_hash)` | P-M05 | 等值 |
| `idx_outbound_keys_tenant_created` | `(tenant_id, created_at)` | 出站列表 | **041 保留** |
| `tenants PRIMARY` | `id` | P-M07 | |
| `idx_product_events_name_occurred` | `(event_name, occurred_at)` | P-M08 | 等值→范围/排序 |

**本波不新建索引。**

**已评估不建**：

| 候选 | 不建的理由 |
|---|---|
| `(status)` on orders | 基数 ≤7；P-M03 非高频；§9 `type=index` PRIMARY 倒扫可接受 |
| `(tenant_id, id)` | P-M09 非 Top-N 敏感；filesort 单企可接受 |
| `(status, period_end)` on SKU | 表一行一企 |
| 出站 `(key_hash, revoked_at)` | `uk` 已 const；吊销在取行后滤 |
| `tenants.quota` 函数索引 | JSON 整包读写，点查走 PK |
| 价目 `(price_cents)` | 无按价格扫 |

---

## 6. Redis 键

本特征 **不引入新 Redis 键**。

| 候选 | 不建 |
|---|---|
| `billing:open:{tenant}:{product}` | UNIQUE 生成列是占坑真相 |
| `billing:catalog:pro` | `plans.slug` const 点查 |
| `billing:relay_price` | 配置整数，禁止再缓存一份与库/配置分叉 |
| `billing:cred:*` | **禁止**缓存可解密材料 |

Redis 不可用：直接查库。

---

## 7. 数据量与增长

无生产 n。

| 表 | 当前（本机 039 库） | 日增（推定） | 一年 | 归档 |
|---|---|---|---|---|
| `orders` | 0 行 | 结账次数 | 万级以下 | 不必 |
| `plans` | 2 行（缺 enterprise） | 0 | 3 | 不必 |
| `relay_sku_entitlements` | 表在 046，本机未迁 | ≤租户数 | ≤租户数 | 不必 |
| `outbound_keys` | 表在 041，本机未迁 | 签发 | 千级 | 不必 |

本机 `alembic_version=039` 且已有 040 形 `plans`/`orders`（无 046 列）。部署事实源是迁移文件 046，不是本机漂移。实现帽不得在本机未迁库上「已完成」047。

---

## 8. 破坏性变更

**无新表。无 DROP 列。** 旧 `pending`/`paid` 读模型仍认识——收缩旧字面量 **本波不做**。

| 变更 | 类型 | 步骤 |
|---|---|---|
| `orders.channel` NOT NULL → NULL，**同时 DROP DEFAULT 'offline'** | **放宽（expand）** | 单步 `MODIFY channel VARCHAR(16) NULL`（不写 DEFAULT = 去掉旧默认）。W2 未配 INSERT 显式 NULL。040 已有 `offline` 行不 UPDATE。down：先 `UPDATE channel='offline' WHERE channel IS NULL`，再 `MODIFY ... NOT NULL DEFAULT 'offline'` |
| `plans.pro.quota_json` 20/500k/5M → 50/200k/5M | 数据，可逆 | `UPDATE ... WHERE slug='pro'`。down 写回 040 种子。**不** UPDATE 已有 `tenants.quota`（不靠回放历史订单） |
| `plans` INSERT `enterprise` 99900 | 数据加法 | `INSERT ... WHERE NOT EXISTS (slug='enterprise')`。`quota_json` 占位包 ≠ 专业档三数字，**不是** T-08 金标。down：无订单引用才 DELETE；有 FK 引用则保留行（声明不可无痕删） |
| 旧 status 收缩 | 破坏性 | **本波不做** |
| `orders.tenant_id` 收紧 NOT NULL | 破坏性 | **本波不做** |
| DROP `api_keys` / `relay_groups` | 破坏性 | **禁止** |
| 改 `amount_cents` 为 DECIMAL | 破坏性换族 | **本波不做** |

建议迁移文件 **047**（revises 046），单文件可含：channel 放宽 + 两处数据。不是 expand-contract 三文件（无删列/无加 NOT NULL/无改唯一键）。

**本帽不写 Alembic，故无 `up→down→up` 退出码。** 实现帽必须在隔离 MySQL 实跑三段并贴退出码（见 §11 清单）。生成列 down 已在 046，047 不得 DROP `open_product_slot`。

加数据前重复检查（enterprise slug）：

```sql
SELECT slug, COUNT(*) c FROM plans GROUP BY slug HAVING c > 1;
-- 期望 0
SELECT price_cents FROM plans WHERE slug='pro';     -- 期望 29900
SELECT quota_json FROM plans WHERE slug='pro';      -- 047 后期望 50/200000/5000000
```

---

## 9. 需真库验证的方言特性（交给 /qa）

- **STORED GENERATED + UNIQUE**（046 已有）：两笔同企同商品 `checkout_pending` 第二笔 IntegrityError；`fulfilled` 后可再插。W2 不得改表达式。
- **`channel` NULL + 无 DEFAULT + UNIQUE(channel, channel_trade_no)**：多行 `(NULL, NULL)` 合法。`SHOW CREATE TABLE orders` 的 `channel` 行不得再出现 `DEFAULT 'offline'`。W2 未配 INSERT 显式 NULL 后读回仍是 NULL（不是被默认成 offline）。
- **LEFT JOIN plans**：`product_code=relay` 运营台不得丢行。
- **047 数据**：`pro.quota_json` = 定价页 50/200000/5000000；`enterprise.price_cents NOT IN (0,29900)`；`enterprise.quota_json` ≠ 专业档三数字（具体数字未冻）。
- EXPLAIN：live 库停在 039，**不能**当 046 证据。下列为 2026-09-13 本机抛掷表（046 形）+ live `tenants`/`product_events` 的 raw 输出。

```
-- P-M01：一企一商品占坑
EXPLAIN SELECT id, status, amount_cents FROM _dba_explain_orders
 WHERE tenant_id = 1 AND open_product_slot = 'plan_pro';
type=const  key=uk_orders_tenant_open_product  key_len=136  rows=1  Extra=NULL
判读：等值命中生成列唯一。通过。

-- P-M02：确认本笔+金额
EXPLAIN SELECT id, status, amount_cents, product_code, tenant_id FROM _dba_explain_orders
 WHERE id = 1 AND status = 'checkout_pending' AND amount_cents = 29900;
type=const  key=PRIMARY  key_len=4  rows=1  Extra=NULL
判读：PK const；金额谓词在单行上滤。通过。CAS UPDATE 同谓词。

-- P-M03：运营台待确认（不建 status 索引）
EXPLAIN SELECT id, tenant_id, product_code, amount_cents, status FROM _dba_explain_orders
 WHERE status IN ('checkout_pending','pending') ORDER BY id DESC;
type=index  key=PRIMARY  key_len=4  rows=1  Extra=Using where; Backward index scan
判读：小表 PRIMARY 倒扫。有意不建 (status)。表到万级再复盘。通过（当前）。

-- P-M04：专业档展示分
EXPLAIN SELECT slug, price_cents, quota_json FROM _dba_explain_plans WHERE slug = 'pro';
type=const  key=slug  key_len=130  rows=1  Extra=NULL
通过。

-- P-M05：出站 hash
EXPLAIN SELECT tenant_id, key_hash, revoked_at FROM _dba_explain_outbound
 WHERE key_hash = REPEAT('a',64) AND revoked_at IS NULL;
type=const  key=uk_outbound_keys_key_hash  key_len=258  rows=1  Extra=NULL
通过。

-- P-M06：SKU
EXPLAIN SELECT status, period_end FROM _dba_explain_sku WHERE tenant_id = 1;
type=const  key=uk_relay_sku_entitlements_tenant  key_len=4  rows=1  Extra=NULL
通过。

-- P-M07：配额执法（live tenants）
EXPLAIN SELECT id, quota FROM tenants WHERE id = 1;
type=const  key=PRIMARY  key_len=4  rows=1  Extra=NULL
通过。

-- P-M08：事件（live product_events，无 is_internal_fixture 列因本机 039）
EXPLAIN SELECT id, tenant_id, occurred_at, event_name FROM product_events
 WHERE event_name = 'order_status_reached'
   AND occurred_at >= '2026-09-01' AND occurred_at < '2026-09-14'
 ORDER BY occurred_at;
type=range  key=idx_product_events_name_occurred  key_len=263  rows=1  Extra=Using index condition
判读：无 Using filesort（occurred_at 在索引内）。通过。

-- P-M09：本企业列表
EXPLAIN SELECT id, status, product_code, amount_cents FROM _dba_explain_orders
 WHERE tenant_id = 1 ORDER BY id DESC;
type=ref  key=uk_orders_tenant_open_product  key_len=5  rows=1  Extra=Using filesort
判读：只用 tenant_id 前缀；filesort 因排序列不在该唯一键。单企行少，不建新索引。通过（有意）。

-- P-M10：企业档展示分
EXPLAIN SELECT slug, price_cents FROM _dba_explain_plans WHERE slug = 'enterprise';
type=const  key=slug  key_len=130  rows=1  Extra=NULL
通过。
```

抛掷表已 `DROP`。红线：大表 `type=ALL` 无说明；意外 filesort 未记录。P-M03/P-M09 的 Extra 已说明。

---

## 10. 开放问题

本特征 Q-* 已答，禁止重开。下列是 **数据值**，不阻塞表结构；阻塞「没有存储分可做 SEC-3」。

| 问题 | 阻塞什么 | 需要谁定 | 本波处置 |
|---|---|---|---|
| 企业档对外标价是否就是 ¥999 | 官网仍印「定制」；结账必须有存储分 | /pm 若要改数字 | **种子 99900**（夹具已有，SEC-3 用）。改价=UPDATE，不加列 |
| 企业档配额三数字是哪三个 | 履约写入哪一包；T-08 金标 | **/pm 必须写一句** | **本波不冻**。T-08 只断言 ≠ 专业档 50/200000/5000000。禁止把夹具 50/2M/20M 当金标 |
| 中转展示分是否 19900 | 配置键必须非 0、≠29900 | /pm 若要改 | 配置 `BILLING.RELAY_PRICE_CENTS`；本帽不建表 |
| 中转账期长度 | `period_end` 计算 | /pm | 不阻塞列；未答则不得发明第二套日历（沿用现网 30 天应用约定） |
| 旧 `pending` 是否回填 `product_code` | 旧线下单不占 slot | — | **不回填**（与 upgrade dba 建议一致） |

---

## 11. 给下游的手递（非 API、非 Service）

| 谁 | 必须知道 |
|---|---|
| `/backend` ORM | **无新表**。`Order.channel` 可空，**去掉** `server_default='offline'` 与 Python `default='offline'`。W2 未配建单 INSERT **显式** `channel=NULL`。确认 CAS 带 `id+status+amount_cents`；`confirm_paid` 必须接 `checkout_pending`（现码 `ORDER_CONFIRM_OFFLINE_ONLY` 作废）；运营台 WHERE 含 `checkout_pending`，LEFT JOIN plans；`_fulfill_product`：`plan_enterprise` 写 SKU **且** 配额 JSON ≠ 专业档三数字（具体三数等 pm，T-08 不冻夹具 50/2M/20M）；`plan_pro` 从 **更新后** 的 `pro.quota_json` 写 `tenants.quota`；出站拉数只查 `outbound_keys` |
| `/qa` | §2.1 非法流转；GWT-M11.12 UNIQUE；GWT-M31.4/6 29900 套企业档/中转；MYSQL_FIDELITY 生成列；本机 039 ≠ 已迁 046 |
| `/sre` | 047 无维护窗口（小表 MODIFY NULL + 两行价目）。密钥仍不进镜像。`BILLING.RELAY_PRICE_CENTS` 必须在运行配置里给出 ≠29900 的正整数 |
| 实现迁移 | revises 046；autogenerate + 数据 UPDATE/INSERT；`up→down→up` 贴退出码；禁止改 040 文件；禁止 DROP live 索引 |

**配置红线**：商户密钥仍不得进 git/yml。中转 **价格分** 不是密钥，必须有存储值（配置整数），禁止只靠「定制」文案做确认比对。

### 047 迁移自检（实现帽落地时填退出码）

变更类型：☐ 纯加法 ☑ 放宽 + 数据（非破坏三步）

| 对象 | 操作 | 破坏性 |
|---|---|---|
| `orders.channel` | MODIFY NULL **并 DROP DEFAULT** | 否（放宽） |
| `plans` slug=pro | UPDATE quota_json | 否 |
| `plans` slug=enterprise | INSERT（配额占位 ≠ 专业档；非 T-08 金标） | 否 |

`down` 能恢复数据吗？pro `quota_json` **能**（写回 040 种子）。enterprise 行：无订单引用可 DELETE；有引用则 **不能**无痕删——注释声明。channel：先把 NULL 回填 `offline`，再 `NOT NULL DEFAULT 'offline'`（恢复 046 形状，不是把 W2 语义留在 down 后的库里）。
