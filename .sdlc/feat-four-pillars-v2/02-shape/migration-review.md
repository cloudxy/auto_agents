# 迁移自检 · feat-four-pillars-v2 数据契约

> 泳道：L4｜上游：`db-spec.md` / `schema.dbml`｜作者：/dba｜日期：2026-09-10
> 变更类型：分波 — Wave 0 纯加法；Wave L 纯加法（加列）；Wave 1 加法 + **加 UNIQUE 三步** + **值域数据三步** + **039 listed_at 精度 expand**
> 头修订今天 = **039**。禁止复活 028/029/030 pyc。LiteLLM PG 不进本链。生产 **禁止** downgrade past 037。
> 039 用 `op.alter_column` + `mysql.DATETIME(fsp=6)`（精度加宽 expand）。ORM `listed_at` 对齐 DATETIME(6)。GWT-37.6 测试不改。

## 0.1 本轮 039 · `capability_assets.listed_at` DATETIME → DATETIME(6)

| 对象 | 操作 | 破坏性 |
|---|---|---|
| `capability_assets.listed_at` | ALTER 精度 DATETIME → DATETIME(6) | 否（expand：列仍在，fsp 加宽） |

回滚：列仍在。039 down 回到 DATETIME（丢微秒）。生产仍 **禁止** downgrade past 037（037 down 的 FK/index 债不在本票）。隔离库可 039 ↔ 038。禁止把 `ALEMBIC_URL` 指到业务库 `auto_agents` 做 down 实验。

隔离 schema=`aa_qc_cond2_039_listed_at`（root@127.0.0.1:3306；随后 DROP）。未打业务库。

```
$ cd backend && ALEMBIC_URL=<isolated> uv run alembic -c alembic.ini upgrade 039
INFO Running upgrade 038 -> 039, t28 listed_at DATETIME(6)；GWT-37.6 MySQL isoformat 往返
exit: 0
after_up1 listed_at=datetime(6) alembic_version=039

$ ALEMBIC_URL=<isolated> uv run alembic -c alembic.ini downgrade 038
INFO Running downgrade 039 -> 038, t28 listed_at DATETIME(6)；GWT-37.6 MySQL isoformat 往返
exit: 0
after_down listed_at=datetime alembic_version=038

$ ALEMBIC_URL=<isolated> uv run alembic -c alembic.ini upgrade 039
INFO Running upgrade 038 -> 039, t28 listed_at DATETIME(6)；GWT-37.6 MySQL isoformat 往返
exit: 0
after_up2 listed_at=datetime(6) alembic_version=039

$ DROP DATABASE aa_qc_cond2_039_listed_at
exit: 0
```

**`down` 能恢复数据吗？** 列仍在。down 把 fsp 收成秒（微秒丢失，值不丢）。这是 expand 的反向，不是 DROP COLUMN。生产不跑这条 down。

锁：assets 小表（含 NFR 夹具约数百行）。MySQL 8 DATETIME fsp 加宽为列宽增加（5→8 字节），秒级。无需维护窗口 / gh-ost。

回填：N/A（无数据脚本）。存量秒级值读回为 `.000000`。

## 0. 分票（破坏性必须一文件一步）

| 迁移（建议 message） | 波 / 票 | 操作 | 破坏性 |
|---|---|---|---|
| `product_events` | W0 T-12 | CREATE TABLE + P-E01/P-E02 索引 | 否 |
| `gateway_ref` 加列 | W L（dba 列；T-18/T-19 不改类型） | ADD `gateway_ref` VARCHAR(191) NULL + (ref, created_at) 于 `channel_events` / `channel_probe_results` | 否 |
| `power_market_expand` | W1 T-21/T-29/T-25/T-33 可拆 PR 但 DDL 与豁免同 PR | 五表 CREATE；assets 加列（`listing_state` **server_default**）；`skill_jobs.source_id`；`source_type` 16→32（assets **和** skills） | 否（加宽非破坏） |
| `assets_source_origin_idx` | W1 UNIQUE Step1 | 普通索引 `(source_id, origin_ref, alive_flag)` | 否 |
| （数据脚本，非迁移） | W1 UNIQUE Step2 / D22b / 第一方 listed | 重复探测 + 回填 | 数据 |
| `assets_source_origin_uk` | W1 UNIQUE Step3 | 普通索引 → UNIQUE `uq_asset_source_origin_alive` | **是**（第 3/3 步） |
| （数据脚本）D22b contract | W1 值域 Step3 | 写路径拒 `expert`/`expert_team` | 数据，无 DDL |
| `listed_at_datetime_fsp` | QC cond-2 / 039 | `listed_at` DATETIME → DATETIME(6) | 否（精度 expand） |

三步写进一个文件 = 不通过。D22b UPDATE **不进** Alembic。

## 1. 变更清单（目标态，待 autogenerate）

| 对象 | 操作 | 破坏性 |
|---|---|---|
| `product_events` | CREATE | 否 |
| `capability_sources` / `capability_commands` / `capability_components` / `capability_installs` / `capability_aliases` | CREATE | 否 |
| `capability_assets.listing_state` 等新列 | ADD（listing_state NOT NULL + server_default `unlisted`） | 边界：有 default 的小表（~320 行），允许单步 |
| `capability_assets.source_type` / `skills.source_type` | VARCHAR(16)→32 | 否（扩大） |
| `skill_jobs.source_id` | ADD NULL + FK SET NULL | 否 |
| `channel_events.gateway_ref` / `channel_probe_results.gateway_ref` | ADD NULL + 索引 | 否 |
| `uq_asset_source_origin_alive` | 加 UNIQUE | **是**（拆三步） |
| `uq_asset_type_name_alive` | **禁止改** | — |
| `channel_id` 类型 | **禁止改** | — |
| `capability_assets.listed_at` | ALTER DATETIME → DATETIME(6)（039） | 否（expand） |
| LiteLLM Prisma 表 | **禁止进本链** | — |
| `capability_installs` 进豁免 | **禁止** | — |

`env.py` 未开 `compare_type`：`source_type` 加宽必须 `MYSQL_FIDELITY=1` 对人审。018 `uq_*_asset` 已在真库：autogenerate **禁止再 create_unique**。禁止为 R-AUD 给 channel_*/skill_jobs 补 `updated_at`。

## 2. 可逆性验证（必跑，不是必写 — S3 之后粘贴）

```
$ cd backend && MYSQL_FIDELITY=1 uv run alembic -c alembic.ini upgrade +1
exit: <S3 后粘贴>
$ MYSQL_FIDELITY=1 uv run alembic -c alembic.ini downgrade -1
exit: <S3 后粘贴>
$ MYSQL_FIDELITY=1 uv run alembic -c alembic.ini upgrade +1
exit: <S3 后粘贴>
```

本帽未跑。实现帽每条迁移必须三段退出码 0。

**`down` 能恢复数据吗？**
- ☑ 纯加法（新表/可空列/新索引）：能（drop）
- ☑ `listing_state` NOT NULL default：down 丢列；默认回填的 `unlisted` 随列消失
- ☐ UNIQUE Step3：down 回到普通索引；数据仍在
- ☐ D22b 回填脚本 down：不能自动还原旧枚举 — 声明「数据脚本不可逆」，交付前备份
- ☐ 第一方 listed 回填：可按守卫重跑；unlist 不清空的 `listed_at` 不因 down DDL 丢失（列还在）
- ☑ 039 `listed_at` fsp 加宽：隔离库 up→down→up 三段 exit 0；down 列仍在、精度回到秒；生产禁止 downgrade past 037

## 3. 结构验证（S3 后）

闸门：**已有表 SHOW CREATE 列集 = live 全列 ∪ 本特征加列**。禁止为对齐「看起来像全表的 stub」而 **DROP** 现网列或现网索引。允许：ADD 本特征列；`source_type` 原位 16→32。新表（`product_events` + 五市场表）按 DBML 全列 CREATE。

```
$ mysql -e "SHOW CREATE TABLE product_events\G"
$ mysql -e "SHOW CREATE TABLE capability_installs\G"
$ mysql -e "SHOW CREATE TABLE capability_assets\G"
$ mysql -e "SHOW CREATE TABLE channel_events\G"
$ mysql -e "SHOW CREATE TABLE channel_probe_results\G"
$ mysql -e "SHOW CREATE TABLE capability_plugins\G"
$ mysql -e "SHOW CREATE TABLE capability_experts\G"
$ mysql -e "SHOW CREATE TABLE capability_teams\G"
$ mysql -e "SHOW CREATE TABLE skill_jobs\G"
$ mysql -e "SHOW CREATE TABLE skills\G"
```

对齐 `schema.dbml`：字段名 / 类型 / 可空 / 索引名 / 列顺序。漏 live 列 = FAIL。DROP 现网列来对齐 stub = FAIL。

必须仍在 SHOW CREATE 里的 live 列（非穷尽，抽查闸）：
- `capability_assets`：`ai_suggested_score` / `tier` / `reviewed_by` / `reviewed_at` / `similar_to`
- `channel_events`：`usage` / `limit_quota` / `window_hours` / `reason`；另 `ix_channel_events_created_at`
- `channel_probe_results`：`scores` / `latency_ms`
- `capability_plugins`：`license` / `health_status` / `manifest` / `mcp_servers`（及 018 其余 live 列）
- `capability_experts` / `capability_teams`：018 全列，不是 id/asset_id/timestamps
- `skill_jobs`：`total` / `succeeded` / `failed` / `detail`
- `skills`：014+019 全列；本特征只加宽 `source_type`

`uq_asset_type_name_alive` 字节不变。`channel_id` 仍 BIGINT。`gateway_ref` VARCHAR(191) NULL。`skills.file_path` 仍 NOT NULL。

## 4. 锁与耗时评估

| 项 | 值 |
|---|---|
| 目标表当前行数 | assets ~320；channel_* 小；events/市场表 0 |
| 在线 DDL 算法 | 加列/加宽：MySQL 8 `ALGORITHM=INPLACE, LOCK=NONE`（S4 真库确认） |
| 预计耗时 | 秒级；无需维护窗口；无需 gh-ost |
| `spider_results` | **本波不加 DDL** |

## 5. 回填（DDL 与数据分离）

| 项 | 内容 |
|---|---|
| 第一方 listed | 独立脚本：第一方 ∧ status∈{stable,recommended} → `listing_state=listed`，`writable=1`，`host_compat` **保持 NULL**。禁止写成 `[]` |
| 幂等守卫 | `WHERE listing_state='unlisted' AND <第一方谓词>` |
| 完成校验 | `listing_state='listed' AND source_id IS NOT NULL` → **0**（PR1 不得 attach 源） |
| D22b | 探测 `expert`/`agent` 同名存活撞 uq（期望 0）→ UPDATE 值 → alias.asset_type 同步。不进迁移 |
| gateway_ref | `WHERE gateway_ref IS NULL AND channel_id <> 0` → `CAST(channel_id AS CHAR)`。`channel_id=0` 不得靠这条回填 |
| UNIQUE Step2 | `SELECT source_id, origin_ref, COUNT(*) FROM capability_assets WHERE source_id IS NOT NULL AND deleted_at IS NULL GROUP BY 1,2 HAVING COUNT(*)>1` → 0 |

批大小 1000–5000；按 id 区间；中断可续。

## 6. EXPLAIN 证据（S4 真库，本帽无假输出）

模式均为 **presumed**。S4 对 P-M01 / P-M02 / P-M05 / P-M07 / P-M08 / P-E01 / P-E02 / P-G01 / P-G02 跑 `EXPLAIN`，断言 `type != ALL`。未跑不得勾。

```
-- P-E01（表创建后）
EXPLAIN SELECT id, event_name, occurred_at FROM product_events
 WHERE event_name = 'task_completed' AND occurred_at >= ? AND occurred_at < ?
 ORDER BY occurred_at DESC LIMIT 50;
-- 期望 key=idx_product_events_name_occurred  type=ref|range
```

## 7. 自检清单

- [x] 变更与 `schema.dbml` 一致（已有表 = live ∪ 加列，不是 stub；ORM 未改）
- [x] 破坏性已拆三步；UNIQUE 不与 CREATE 同文件
- [x] `up → down → up` 实跑 — 039 隔离库 `aa_qc_cond2_039_listed_at` 三段 exit 0（随后 DROP）
- [x] `down` 数据恢复能力已声明
- [x] 大表锁：无需窗口
- [x] 回填脚本要求：分批、幂等、可续、归零校验
- [ ] 新增索引 EXPLAIN — **S4 后**
- [x] 无硬编码连接串 / 密钥
- [x] 无大回填写进迁移
- [x] 方言已标需真库验证
- [x] 安装表不进豁免；新平台表与清单+夹具同 PR
- [x] 不改 `channel_id` 类型；不加网关 PG

## 8. 交付给下游

| 给谁 | 内容 |
|---|---|
| `/backend` | DBML + 枚举合法值 + 豁免表名单 + `channel_id=0` 哨兵 + host_compat NULL vs `[]` |
| `/qa` | §9 真库清单；豁免 rowcount 方向；D22b 后公开无 expert |
| `/sre` | 头 039；秒级 DDL；脏库 stamp；网关库不在本链；生产禁止 downgrade past 037 |
