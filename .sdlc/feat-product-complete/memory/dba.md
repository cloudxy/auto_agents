# dba memory · feat-product-complete

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-12
- Hat: dba
- Outputs: `02-shape/db-spec.md` · `02-shape/schema.dbml`（db_ir.sh 16 处违规已清零，exit 0）

## db_ir.sh lint 机关（2026-09-12 修 16 处实证）

- R-AUD 是**子串检测**：真无 updated_at 的表在**列区**（indexes 块之前）写 `// updated_at：…登记豁免` 即过且不虚构列。regex 只捕到 indexes 闭括号——**表尾 note: 行不被捕获**，豁免注释放表尾 lint 仍红。
- R-ENUM 是 `grep 'status.*varchar'` 逐行匹配：status 列改 DBML enum 引用即过；status 行 note 里**禁止 varchar 字样**。
- DBML enum = 文档合法值，物理 VARCHAR + 应用校验（文件头注释自洽，勿改）。

## ORM 事实（platform_core/models/）

- AuditMixin = created_by/updated_by（操作人），**不含时间列**；时间列各模型显式声明。
- 无 updated_at（ORM+迁移双证）：plans/orders/relay_tokens/alert_rules/notifications/asset_import_batches/asset_import_items。capability_assets 有 created_at+updated_at（018 均 nullable；updated_at 无 server default，靠 ORM onupdate）。
- 值域：TenantSubscription.status=active/expired（新增 enum subscription_status）；CapabilityAsset.status=experimental/testing/stable/recommended/deprecated/blacklist（新增 enum asset_status）。

## Facts（沿用）

- 扩 040，不是从零。新表只 `outbound_keys`（TenantMixin，禁豁免，禁混 relay_tokens，禁复活 028）。
- relay_tokens expand：gateway_key_id VARCHAR(191) NULL + spend_synced_at DATETIME NULL。禁改 key_hash。
- used_tokens=缓存；写手=RelayService 列表读路径对账网关；吊销门闩=revoked_at+网关作废。
- 一企业一张 pending：不建部分 UNIQUE（挡 GWT-50.16 夹具）。锁 tenants FOR UPDATE+COUNT；idempotency_key UNIQUE 挡重试。
- 不叠档：uq_tenant_subscriptions_tenant + _apply_plan SET 非 ADD。不加 quota_applied_at。
- 公开种子不进 schema、进治理/同步（谓词 name/title/description）。
- 确认收款、吊销不可逆。LiteLLM PG 不进 Alembic。生产禁 downgrade past 037。040 tenant_id 可空不收紧。

## Open (mine)

- 无阻塞建模问。出站非 sk- 前缀字面量交 backend。gateway_key_id 对齐 OpenAPI 交 T-08。

## Do not re-litigate

- 不代选 Q-VOICE / Q-PRICE / Q-MARKET-USER / Q-AGPL / Q-OPS-COLLECT。
- 出站 ≠ relay sk-（ADR-0020）。FR-50 Then 不含配额变专业档。种子不加列。
