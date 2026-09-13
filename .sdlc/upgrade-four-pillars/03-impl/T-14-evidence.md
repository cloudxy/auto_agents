# 实现证据 · T-14 单据状态机 / 商品码 / 凭据 / SKU 权益语义

> 票：`02-shape/contract.md` §10 T-14｜FR 锚点：FR-U30 FR-U31 FR-U33 FR-U38 FR-U20｜角色：/dba｜日期：2026-09-12

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| `orders` widen + 生成列唯一 | ORM + Alembic 046 | `platform_core/models/billing.py` · `046_n3_…py` | `open_product_slot` STORED；`status` VARCHAR 32；`plan_id` 可空 |
| `payment_channel_credentials` | ORM + 046 | `platform_core/models/payment_channel_credential.py` | 无 `tenant_id`；密文 TEXT；通道 UNIQUE |
| `relay_sku_entitlements` | ORM + 046 | `platform_core/models/relay_sku_entitlement.py` | `tenant_id` UNIQUE NOT NULL；不豁免 |
| 平台豁免 | 组装点 | `backend/app/tenant_isolation.py` | 只登记凭据表 |
| ALL_ORM_TABLES | 测试事实源 | `backend/tests/test_db_fixtures.py` | 两新表；`relay_groups` 仍在 |
| 一待支付 / 开通精确一次 | DB 约束 + CAS | `uk_orders_tenant_open_product`；`UPDATE … status IN (checkout_pending, paid_pending_fulfillment)` | unpaid→fulfilled 无 CHECK，靠 CAS rowcount=0 |

**分层依赖核对**：☑ Router 未 import ORM（本票无新 Router）☑ Service 未返回 ORM ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/alembic/versions/046_n3_checkout_orders_credentials_sku.py` | 新增 | revises **045**；N3 单独文件 |
| `platform_core/models/payment_channel_credential.py` | 新增 | 无 TenantMixin |
| `platform_core/models/relay_sku_entitlement.py` | 新增 | TenantMixin + tenant_id NOT NULL |
| `platform_core/schemas/payment_channel_credential.py` | 新增 | Out **不含** `secrets_encrypted` |
| `platform_core/schemas/relay_sku_entitlement.py` | 新增 | |
| `backend/tests/test_t14_n3_schema.py` | 新增 | 唯一键 / CAS 非法开通 |
| `backend/tests/test_t14_migration_046.py` | 新增 | MYSQL_FIDELITY up-down-up |
| `platform_core/models/billing.py` | 修改 | orders expand；`plans.updated_at` |
| `platform_core/models/__init__.py` | 修改 | 导出两新模型 |
| `platform_core/schemas/billing.py` | 修改 | `plan_id` Optional；快照列可空 |
| `platform_core/schemas/__init__.py` | 修改 | 导出凭据/权益 Schema |
| `backend/app/tenant_isolation.py` | 修改 | 凭据进 TENANT_EXEMPT |
| `backend/tests/test_db_fixtures.py` | 修改 | ALL_ORM_TABLES |

**与票里「会改哪些文件」一致**：☑（合同 T-14=/dba 语义；本 spawn 落地 ORM+046。未做 HTTP 结账 / Alipay SDK。）

**未触碰「不许改的文件」**：☑ 确认（未改 045、未 DROP `relay_groups`、无 `config/**` 密钥键、无 checkout Router）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 046 DDL | 单迁移 | expand：加列/放宽/建表；down 先 DROP 生成列唯一再收紧 |

### 幂等

| 项 | 内容 |
|---|---|
| 一企一商品一待支付 | 生成列 UNIQUE `(tenant_id, open_product_slot)`；终态 NULL 不占坑 |
| 一通道一套凭据 | `uk_payment_channel_credentials_channel` |
| 一企一行权益 | `uk_relay_sku_entitlements_tenant` |
| 开通精确一次 | 条件 UPDATE；`rowcount==0` 不再履约（应用原语，本票钉 DB） |

☑ 未使用「先查后插」当唯一保证

## 4. ORM 与 DBML 对齐

☑ 字段名 ☑ 类型 ☑ 可空性 ☑ 默认值 ☑ 索引 ☑ 唯一约束 ☑ 外键（`orders.plan_id` RESTRICT 仍在；凭据/权益无 tenants FK）

抛开库 upgrade 046 后 `SHOW CREATE TABLE`：

```
CREATE TABLE `orders` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键',
  `tenant_id` int DEFAULT NULL COMMENT '所属租户',
  `plan_id` int DEFAULT NULL COMMENT '目标套餐；product_code=relay 时 NULL',
  `amount_cents` int NOT NULL COMMENT '下单金额（分）',
  `status` varchar(32) NOT NULL DEFAULT 'pending' COMMENT '旧 pending/paid/cancelled；新 checkout_pending/paid_pending_fulfillment/fulfilled/unpaid',
  `channel` varchar(16) NOT NULL DEFAULT 'offline' COMMENT 'offline/alipay/wechat',
  `idempotency_key` varchar(64) DEFAULT NULL COMMENT '防重复下单',
  `paid_at` datetime DEFAULT NULL COMMENT '确认收款时间',
  `created_at` datetime DEFAULT (now()) COMMENT '创建时间',
  `product_code` varchar(32) DEFAULT NULL COMMENT '闭集 plan_pro/plan_enterprise/relay。NULL=040 线下单',
  `order_no` varchar(64) DEFAULT NULL COMMENT '我方订单号。NULL=旧行',
  `channel_trade_no` varchar(64) DEFAULT NULL COMMENT '通道侧交易号。NULL=尚未收到',
  `merchant_id_snapshot` varchar(64) DEFAULT NULL COMMENT '当时商户号，不是密钥。NULL=旧线下单',
  `fail_reason` varchar(32) DEFAULT NULL COMMENT 'cancel/timeout/channel_error/unconfigured。NULL=未失败',
  `late_notify_at` datetime DEFAULT NULL COMMENT '迟到回调。NULL=从未记',
  `verified_at` datetime DEFAULT NULL COMMENT 'FR-U38 通过。NULL=从未验真',
  `fulfilled_at` datetime DEFAULT NULL COMMENT '开通完成。NULL=未完成',
  `unpaid_at` datetime DEFAULT NULL COMMENT '进入 unpaid。NULL=未入该终态',
  `open_product_slot` varchar(32) GENERATED ALWAYS AS ((case when ((`product_code` is not null) and (`status` in (_utf8mb4'checkout_pending',_utf8mb4'paid_pending_fulfillment',_utf8mb4'pending'))) then `product_code` else NULL end)) STORED COMMENT 'STORED GENERATED：非终态且有商品码则为 product_code，否则 NULL',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '本波 ADD。R-AUD',
  PRIMARY KEY (`id`),
  UNIQUE KEY `idempotency_key` (`idempotency_key`),
  UNIQUE KEY `uk_orders_order_no` (`order_no`),
  UNIQUE KEY `uk_orders_tenant_open_product` (`tenant_id`,`open_product_slot`),
  UNIQUE KEY `uk_orders_channel_trade` (`channel`,`channel_trade_no`),
  KEY `plan_id` (`plan_id`),
  KEY `ix_orders_tenant_id` (`tenant_id`),
  CONSTRAINT `orders_ibfk_1` FOREIGN KEY (`plan_id`) REFERENCES `plans` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

CREATE TABLE `payment_channel_credentials` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '代理主键',
  `channel` varchar(16) NOT NULL COMMENT 'alipay/wechat；一通道一行',
  `merchant_no` varchar(64) NOT NULL COMMENT '商户号，可掩码；不是密钥',
  `secrets_encrypted` text NOT NULL COMMENT '不透明密文 blob。明文永不落库/git/yml/浏览器/日志/Redis',
  `key_version` int NOT NULL DEFAULT '1' COMMENT '每轮换 +1；旧密文不保留',
  `rotated_at` datetime DEFAULT NULL COMMENT 'NULL=从未轮换',
  `created_by` varchar(64) DEFAULT NULL COMMENT '超管用户名',
  `updated_by` varchar(64) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_payment_channel_credentials_channel` (`channel`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

CREATE TABLE `relay_sku_entitlements` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '代理主键',
  `tenant_id` int NOT NULL COMMENT '本企业；PIT-4 禁止 NULL=平台 SKU',
  `status` varchar(16) NOT NULL DEFAULT 'none' COMMENT 'none/active/expired',
  `period_end` datetime DEFAULT NULL COMMENT '账期结束快照。active 应用必填；expired 保留到期时刻；none 未开通 NULL',
  `activated_at` datetime DEFAULT NULL COMMENT '最近一次进入 active。NULL=从未开通',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_relay_sku_entitlements_tenant` (`tenant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
```

`plans.updated_at` ADD 表尾。`ix_orders_tenant_id` 保留。无 `tenant_id` 列在凭据表。

**未自行加字段/改类型**：☑ 确认（金额仍 INT 分；无 CHECK；无 slug=relay 种子）

Alembic `045 → 046 → 045 → 046`（抛开库 `t14_046_udup`，root）：

```
OK upgrade 046 cred_table=True sku_table=True open_slot=True relay_groups=True status_len=32
OK downgrade 045 cred_table=False sku_table=False open_slot=False relay_groups=True status_len=16
OK upgrade 046 again cred_table=True sku_table=True open_slot=True relay_groups=True
up-down-up 046 complete
udup_exit:0
```

046 由 ORM+DBML 手审写出（生成列补丁）；未让 autogenerate DROP `ix_orders_tenant_id`。

## 5. 可观测性

本票无新 Service 公开方法。密钥列不入日志。

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ Out Schema 无密文全文

## 6. 自测证据

> 命令与退出码**原样粘贴**。

```
$ uv run pytest -q backend/tests/test_t14_n3_schema.py
................                                                         [100%]
16 passed in 4.09s
schema_exit:0
```

```
$ MYSQL_FIDELITY=1 MYSQL_FIDELITY_HOST=127.0.0.1 MYSQL_FIDELITY_USER=root \
  MYSQL_FIDELITY_PASSWORD=*** uv run pytest -q backend/tests/test_t14_migration_046.py
.                                                                        [100%]
1 passed in 5.10s
mig_exit:0
```

```
$ uv run pytest -x -q backend/tests
1602 passed, 40 skipped, 7 warnings in 231.47s (0:03:51)
exit: 0
```

```
$ bash tools/check/db_migrations.sh
✓ 迁移破坏性变更检测通过
dbm_exit:0
```

```
$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
arch_exit:0
```

```
$ uv run python -c "from platform_core.models.payment_channel_credential import PaymentChannelCredential; ..."
OK
```

### 验收项逐条对应

| 项 | 覆盖的测试 | 结果 |
|---|---|---|
| N3 不进 045 | `test_046_revises_045_and_n1_file_has_no_n3_objects` | ✅ |
| 一待支付 UNIQUE | `test_open_product_slot_unique_blocks_second_checkout` + 046 MySQL | ✅ |
| 终态释放坑 | `test_fulfilled_releases_slot_second_checkout_ok` | ✅ |
| 多 NULL 不互撞 | `test_unpaid_and_null_product_do_not_occupy_slot` | ✅ |
| order_no / channel_trade UNIQUE | `test_order_no_and_channel_trade_uniques` / `test_channel_trade_unique_same_channel` | ✅ |
| unpaid 不能 CAS 开通 | `test_illegal_fulfill_cas_unpaid_rowcount_zero` | ✅ |
| 成功通知不开第二份 | `test_cas_fulfill_from_checkout_pending_once` | ✅ |
| 凭据无 tenant_id / 密文≠明文 | `test_credentials_have_no_tenant_id_column` / `test_two_channels_ok_and_blob_ne_plaintext` | ✅ |
| 通道 UNIQUE | `test_channel_unique_and_ciphertext_not_plaintext` | ✅ |
| SKU tenant UNIQUE / NOT NULL | `test_relay_sku_tenant_unique_and_not_null` / `test_relay_sku_null_tenant_rejected` | ✅ |
| 不删 relay_groups | `test_relay_groups_still_insertable` + 046 down 后表仍在 | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | 046 down 清新表/新列 | ✅ 抛开库 |
| 幂等 | UNIQUE IntegrityError | ✅ |
| 并发写 | UNIQUE 兜底（非 gather） | ✅ 约束已在 |
| 外部依赖失败 | — | ➖ N/A（无 SDK / 无 HTTP） |

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-U02 | 同一商品最多 1 笔待支付 | 生成列 UNIQUE | SQLite + MySQL 8 |
| FR-U31.4 | 密钥不进 git/yml | `config/**` 无 alipay/wechat 商户键 | 仓库扫描 |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| T-15 | 凭据表已在；加密落库/轮换/404 同形未做。Out 无密文列。主密钥仍只走环境。 |
| T-16 | 建单占 `open_product_slot`；撞 UNIQUE = 已有未完成支付。`relay` 单 `plan_id` NULL，列表勿 INNER JOIN `plans` 丢行。 |
| T-17 | 开通用 `UPDATE … WHERE status IN ('checkout_pending','paid_pending_fulfillment')`；0 行则停止。迟到回调只写 `late_notify_at`。 |
| T-18 | 读 `relay_sku_entitlements`；缺行≡none。禁止 COUNT `relay_groups`。 |
| `/qa` | 方言：生成列 UNIQUE 已 MYSQL_FIDELITY。非法流转 unpaid→fulfilled 无 CHECK。 |
| `/sre` | 生产禁止 down past 037。046 down 会丢凭据行与新订单列。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口；无 yml 商户密钥
- [x] 幂等未用「先查后插」当唯一保证
- [x] 未做 HTTP 结账 / Alipay SDK verify
- [x] 票状态：本 spawn 交付 evidence；orchestrator 更新 state
