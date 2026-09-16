# db-spec · feat-agents-market（.agents 资产能力市场）

> 上游：PRD `01-define/spec.md` v1.2（FR-01..FR-08 + 附加 a/d/e）｜contract `02-shape/contract.md` §5（数据契约需求）
> 下游：`02-shape/schema.dbml` → 迁移 050（T-05 落地，逐行规格见 §8）→ backend ORM
> 泳道：L3｜作者：dba 帽｜日期：2026-09-15
> 实测环境：本地 MySQL 8.0.42（127.0.0.1/auto_agents），alembic head = **049（单头）**，capability_assets 194 行（live 182：skill 146 / command 18 / agent 18 / plugin 0——bug 态），capability_installs 1 行，product_events 139 行

---

## 0. 实体与粒度

**结论：本轮零新表。** 仅 `capability_assets` 加 2 列（`featured` / `examples`，迁移 050）；其余需求全部由既有表与查询路径承载。

| 实体（表名） | 一行代表什么 | 来源 FR | 本轮变更 |
|---|---|---|---|
| `capability_assets` | 一个存活资产 = (asset_type, name) 当前代（软删后同键可重建新一代，alive_flag 脱离唯一键） | FR-01..07 | **+featured +examples（050）** |
| `capability_installs` | 一企业 × 一资产 × 一宿主的一次订阅（存活代） | FR-04 附加 a | 无（「最热」实时聚合来源） |
| `product_events` | 一次已发生的产品事实（追加，应用永不 UPDATE） | FR-08 | 无（四类事件落点，现表现索引） |
| `capability_plugins` / `capability_experts` / `capability_commands` | 各类型 1:1 细节侧表 | FR-05 | 无（persona_md / body_md 为既有列，缺投影是服务层问题 contract AD-5b，非库） |

**被判定为「不是实体」的名词**（避免评审反复讨论）：

| 名词 | 判定 | 理由 |
|---|---|---|
| 目录导入 job/batch | **不是实体，不建表** | 两段式无状态（contract AD-4d）：判型确定性 ⇒ preview/confirm 各自上传同一棵树结果一致；取消 = 不发 confirm（GWT-07.2 天然满足）。持久化 job 表需 TTL/清理/写放大，单管理员工具无并发争用；失败追溯由 product_events(`import_failed`) 承担。对应 manager 判定「无强理由不建表」——核验后无强理由 |
| 精选位 | 字段 `featured` | 布尔治理标志（GWT-04.5 设/取消），无独立生命周期；精选内部排序已定为 updated_at 倒序（GWT-04.1），无位次需求 |
| 「帮你做」示例 | 字段 `examples`（JSON list[str]） | 0–N 短文本、整体读写（详情 + 行快照）、永不按元素查询/联结 |
| 最热订阅计数 | 聚合查询，不落列 | 实时 COUNT 零漂移，天然满足「不显示假数字」（附加 a）；成本证据见 §5E P-03 |
| 分类 tab / 排序档 / 占位图 | 查询参数 / 前端纯函数 | 无存储参与 |

**FR 覆盖核对**：

| FR | 涉及实体 | 承载字段/路径 | 缺口 |
|---|---|---|---|
| FR-01/02 | capability_assets | upsert 判重 = uq_asset_type_name_alive；prune 候选 = deleted_at/source_id/asset_type 查询（P-04/P-05） | 无 |
| FR-03/04 | capability_assets + capability_installs | 货架过滤链（P-01..03）；`featured` 新列 | featured（050） |
| FR-05 | capability_assets + 侧表 + 文件系统 | `examples` 新列；md 正文 = 磁盘 SKILL.md / persona_md / body_md（既有列） | examples（050） |
| FR-06 | 无 | 前端确定性占位 | 无 |
| FR-07 | capability_assets | confirm 走 upsert 同族（P-05 判重），落盘根 .agents | 无（无 job 表，见名词表） |
| FR-08 | product_events | event_name ≤64 全部容纳（import_completed=17 字符等）；props JSON 装四事件字段；检索走既有 idx_product_events_name_occurred | 无 |

## 0.1 建模决策记录

| 决策 | 选了什么 | 备选 | 理由 |
|---|---|---|---|
| featured 形态 | 单列布尔标志 | curation 排序表（带 position） | 精选无位次需求（GWT-04.1：精选内部按 updated_at 倒序）；单列零 JOIN，PATCH 一步 |
| examples 形态 | 主表 JSON 列 | 侧表 asset_examples(asset_id, ord, text) | ≤20×200 字、整体读写、无按元素查询；侧表多一次 JOIN + 生命周期管理，零查询收益；与 similar_to / host_compat / alias_origin_refs 同款仓库先例 |
| 最热计数 | 每次实时聚合 installs | assets.install_count 汇总列 | 汇总列需订阅/退订双写并周期对账（会漂移）；实测 1.32ms@181 行（§5E P-03），10x 余量后仍是个位数 ms；「不造假」零成本 |
| 导入 job | 无状态两段式 | import_jobs 持久表 | 见 §0 名词表；无强理由 |
| 治理字段与同步共存 | featured/examples **不进** `_desired` | 同步整行覆盖 | 已核实 agents_hub.py `_desired` 的 17 个键不含 featured/examples → 同步/导入永不重置治理字段。**T-07 树导入必须沿用此纪律：upsert 只 set desired 键**（否则每次同步清空精选/示例，GWT-04.5/05.3 回归） |
| 软删 | 不动 | — | SoftDeleteMixin + alive_flag 生成列：既是唯一键组件（软删脱离约束）又是 prune 后同键重建语义；本轮零改动 |

---

## 1. 数据字典（增量列；既有全列见 schema.dbml）

### capability_assets（迁移 050 增量，物理序接表尾）

一行 = 一个存活资产 (asset_type, name) 当前代。

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| `featured` | smallint（ORM SmallInteger） | 否 | 0（server_default "0"） | FR-04 综合序置顶标志。0=未精选 1=精选；值域 {0,1} 应用层校验。NOT NULL 理由：布尔标志无「未知」态；存量行由 server_default 补 0——**SM-5 门禁要求 NOT NULL 加列必须带 server_default**（db_migrations.sh AST 扫描） |
| `examples` | JSON | 是 | NULL | 附加 d「帮你做」示例 list[str]，≤20 条 × 200 字（应用层 422，AD-7）。NULL = 未维护（投影空列表，抽屉隐藏区块，GWT-05.3）；不设默认值 |

类型取舍：

- `featured` 用 SMALLINT（MySQL 落 smallint，与 §8 迁移规格 / schema.dbml / DDL 实测一致）而非 CHAR(1)/原生布尔：仓库布尔惯例（writable / public_license_override / enabled 同款），MySQL 无原生 bool。
- `examples` 用 JSON 而非 TEXT：结构由应用校验（list[str]），与 similar_to 等 JSON 先例一致；MySQL JSON 无库级长度约束，上限执法归应用层（与 NFR-03 同一位置）。
- 两列均为「现在时」人工治理内容，不存在快照/引用抉择；随行走、无独立生命周期。

---

## 2. 关系与基数

**本轮零新关系、零 FK 变更。** 既有关系（见 schema.dbml Ref 区）：

| 关系 | 基数 | 外键位置 | 可空 | 级联 | 说明 |
|---|---|---|---|---|---|
| capability_assets → capability_installs | 1:N | installs.asset_id | 否 | RESTRICT | 订阅引用资产；prune 软删不动 installs（计数保留，spec §3.1） |
| capability_sources → capability_assets | 1:N | assets.source_id | 是 | RESTRICT | NULL = 第一方窗口（.agents 同步行全部 source_id IS NULL——prune 候选判据之一） |
| capability_assets → 各细节侧表 | 1:1 | 侧表.asset_id | 否 | CASCADE | 既有 |

## 2.1 状态流转

本轮不改状态机（spec §3.1 沿用：`live[unlisted⇄listed/coming_soon] → deleted 仅显式动作可达`）。

`featured` **不是状态机**：0⇄1 双向合法、无非法流转、与 listing_state 零联动。qa 可加负向断言：置/取消 featured 不改变 listing_state（反之亦然）。

## 2.2 时间字段语义

| 字段 | 语义 | 本轮角色 |
|---|---|---|
| `updated_at` | 记录时间（onupdate 跳变） | **latest / smart 排序键**（GWT-04.1/04.2 口径） |
| `listed_at` | 业务时间（最近一次 listed） | 不参与排序 |
| `created_at` | 记录时间 | 不参与排序 |

两个已核实的时效事实（实现须保持）：

1. **同步幂等不跳变 updated_at**：`_upsert_item` 先 `_same()` 判等，unchanged 行不产生 UPDATE → 连续同步不会把资产顶进「最新」前排（GWT-01.2 行数稳定的伴生不变量）。已读 agents_hub.py:56-106 核实。
2. **featured/examples PATCH 会触发 onupdate 跳变** → 资产进入「最新」档前排。默认接受（运营动作也是更新；无 GWT 反例约束），已列 §10 开放问题交 pm 备案。

时区：全库 naive DATETIME 存 UTC（仓库既例），不混用 TIMESTAMP。

## 2.3 软删决策

不变。capability_assets / capability_installs 现状带软删 + alive_flag（豁免矩阵外）；product_events 追加表按豁免矩阵本就不加。新列随行，无独立删除语义。

---

## 3. 唯一键

**零新增。** `uq_asset_type_name_alive (asset_type, name, alive_flag)` 本轮继续承担三职：

1. 同步/导入 upsert 判重（GWT-01.2 幂等、GWT-07.3 同名 update 不建新行）；
2. 并发同步兜底（GWT-01.7：双请求撞唯一键 → IntegrityError → 重读记 unchanged，contract AD-2）；
3. (asset_type, name) 点查索引（P-05/P-06，EXPLAIN type=ref rows=1 证据 §5E）。

featured / examples 不参与任何唯一性（无业务唯一语义）。

---

## 4. 访问模式 Top-N

> 来源：☑ 调用方代码（power_market/service.py `_list_fr33`、agents_hub.py `_load`、capability_service.py `list_assets`）☑ PRD 推导（**presumed**——无生产负载数据；闸关 + 单管理员为频次上界）
> 全部标注 presumed：上线后按真实慢查询复盘补索引（spec 护栏：list_public/list_assets P95 > 800ms 回滚拖慢变更）。

| ID | 场景（FR / 端点） | 过滤（等值/范围） | 排序 | 频次/天（presumed） | P95 | 单次行 |
|---|---|---|---|---|---|---|
| P-01 | 货架列表 latest / smart（FR-03/04，GET /public/capabilities?sort=…；admin 预览同源） | asset_type IN ≤5 + listing_state IN 2 + status IN 2 + deleted_at IS NULL + 许可 OR 子句 | updated_at DESC（smart 前置 featured DESC） | <100（闸后随 T_gate 放大） | <800ms（NFR-01） | 20 |
| P-02 | 同 P-01 的 COUNT（total 页信息） | 同上 | — | 同上 | 同上 | 1 |
| P-03 | 货架 hot（FR-04 附加 a） | 同 P-01 + installs 派生表 LEFT JOIN | COALESCE(cnt,0) DESC, updated_at DESC | 同上 | 同上 | 20 |
| P-04 | 失源行清理候选（FR-02，POST assets/prune-missing） | deleted_at IS NULL + source_id IS NULL + asset_type IN 4 | — | <1 | 无 | ~200 |
| P-05 | 同步/导入 upsert 判重（FR-01/07，agents_hub._load，每资产一次） | asset_type= + name= + deleted_at IS NULL | — | ~200 × 同步次数（<10 同步/天） | 无 | 1 |
| P-06 | 公开详情 + featured/examples PATCH 点查（FR-05/04，name 路由） | name= + asset_type IN 1..2 + deleted_at IS NULL | — | <500 | <800ms（NFR-02） | 1 |
| P-07 | 治理表格 list_assets（7-tab） | deleted_at IS NULL + asset_type=（可选 category/status/listing_state/name LIKE） | updated_at DESC, id ASC | <50 | <800ms | 50 |
| P-08 | 事件检索（FR-08，product_events 复盘） | event_name= + occurred_at 范围 | occurred_at DESC | 周频 | 无 | ~10² |

**不进 Top-N 的模式**（评审预案）：

- 导入 preview/confirm 判型 —— 纯内存 + 文件系统，零库读（无状态两段式）；confirm 只产生 P-05 点查与行写入。
- media 端点 —— 复用 P-06 点查后读文件系统（get_media_path 校验），无独立模式。
- 搜索 q（_q_clause LIKE + command 子查询）—— 既有能力、非本轮 FR，不动索引。
- export 全量导出 —— 管理员低频全扫，可接受。

---

## 5. 索引设计（结论：**零新增、零变更**）

| 索引（既有） | 字段 | 服务模式 | 证据 / 理由 |
|---|---|---|---|
| PRIMARY | id | — | 代理主键 |
| uq_asset_type_name_alive | (asset_type, name, alive_flag) | P-05 / P-06 + §3 三职 | EXPLAIN type=ref key_len=580 rows=1（§5E） |
| idx_assets_listing_status_type_cat | (listing_state, status, asset_type, category) | P-01..03 候选（194 行下优化器弃用、选全表扫——**正确决策**，过滤命中 93%） | possible_keys 命中而 key=NULL；ANALYZE 0.587ms（§5E） |
| ix_capability_assets_asset_type | (asset_type) | P-07 | EXPLAIN type=ref key_len=66 rows=12（§5E） |
| idx_installs_asset | (asset_id) | P-03 派生表 GROUP BY | EXPLAIN type=index Using where（§5E） |
| idx_product_events_name_occurred | (event_name, occurred_at) | P-08 | 既有，无变更 |

**已评估不建**（防「凭想象建索引」）：

| 候选 | 不建理由 |
|---|---|
| (featured) / (featured, updated_at) | featured 基数≈2；过滤集 181/194 = 93% 命中——索引筛选后仍回表绝大多数行；排序 194（10x = 2000）行在 sort_buffer 内存完成（ANALYZE 实测 filesort 0.58ms）。加索引 = 纯写放大 |
| (updated_at) 单列 | 无按时间过滤的模式；排序由全表扫 + filesort 覆盖（同上实测） |
| (listing_state, asset_type, updated_at) 窄化键 | 同 93% 命中率理由；优化器已实测拒绝既有候选键 |
| installs (asset_id, deleted_at) 覆盖索引 | 表 1 行（10x = 两位数）；idx_installs_asset 已以 type=index 服务 GROUP BY |
| examples 生成列 / 多值索引 | 非查询列（整体读写） |

---

## 5E. EXPLAIN 证据（本地 MySQL 8.0.42 实测，2026-09-15，原始输出）

查询形态逐条对应 service.py `_list_fr33`（FR-33 五条件链）与 agents_hub.py `_load` 的真实谓词。

**P-01 货架 latest 排序**（`ORDER BY updated_at DESC LIMIT 20`）：

```
+----+-------------+-------------------+------------+------+-------------------------------------------------------------------------------------------------------------------------+------+---------+------+------+----------+-----------------------------+
| id | select_type | table             | partitions | type | possible_keys                                                                                                           | key  | key_len | ref  | rows | filtered | Extra                       |
+----+-------------+-------------------+------------+------+-------------------------------------------------------------------------------------------------------------------------+------+---------+------+------+----------+-----------------------------+
|  1 | SIMPLE      | capability_assets | NULL       | ALL  | uq_asset_type_name_alive,ix_capability_assets_asset_type,ix_capability_assets_status,idx_assets_listing_status_type_cat | NULL | NULL    | NULL |  194 |     1.10 | Using where; Using filesort |
+----+-------------+-------------------+------------+------+-------------------------------------------------------------------------------------------------------------------------+------+---------+------+------+----------+-----------------------------+
```

**P-02 货架 COUNT**：`type=ALL, key=NULL, rows=194, Extra: Using where`（同上表结构，仅去 filesort）。

**P-03 货架 hot**（installs 派生表 LEFT JOIN，`ORDER BY COALESCE(t.cnt,0) DESC, updated_at DESC LIMIT 20`）：

```
+----+-------------+---------------------+------------+-------+-------------------------------------------------------------------------------------------------------------------------+--------------------+---------+------------------+------+----------+----------------------------------------------+
| id | select_type | table               | partitions | type  | possible_keys                                                                                                           | key                | key_len | ref              | rows | filtered | Extra                                        |
+----+-------------+---------------------+------------+-------+-------------------------------------------------------------------------------------------------------------------------+--------------------+---------+------------------+------+----------+----------------------------------------------+
|  1 | PRIMARY     | a                   | NULL       | ALL   | uq_asset_type_name_alive,ix_capability_assets_asset_type,ix_capability_assets_status,idx_assets_listing_status_type_cat | NULL               | NULL    | NULL             |  194 |     1.10 | Using where; Using temporary; Using filesort |
|  1 | PRIMARY     | <derived2>          | NULL       | ref   | <auto_key0>                                                                                                             | <auto_key0>        | 4       | auto_agents.a.id |    2 |   100.00 | NULL                                         |
|  2 | DERIVED     | capability_installs | NULL       | index | uq_installs_tenant_asset_host_alive,idx_installs_asset                                                                  | idx_installs_asset | 4       | NULL             |    1 |   100.00 | Using where                                  |
+----+-------------+---------------------+------------+-------+-------------------------------------------------------------------------------------------------------------------------+--------------------+---------+------------------+------+----------+----------------------------------------------+
```

**P-04 prune 候选**（`deleted_at IS NULL AND source_id IS NULL AND asset_type IN (skill,plugin,command,agent)`）：

```
|  1 | SIMPLE | capability_assets | NULL | ALL  | uq_asset_type_name_alive,ix_capability_assets_asset_type,idx_assets_source_origin_alive | NULL | NULL | NULL | 194 |   10.00 | Using where |
```

**P-05 同步 upsert 判重**（`asset_type='skill' AND name='check-arch' AND deleted_at IS NULL`）：

```
|  1 | SIMPLE | capability_assets | NULL | ref  | uq_asset_type_name_alive,ix_capability_assets_asset_type | uq_asset_type_name_alive | 580 | const,const |    1 |   10.00 | Using where |
```

**P-06 详情/治理点查**（`name='check-arch' AND asset_type IN ('skill') AND deleted_at IS NULL`）：

```
|  1 | SIMPLE | capability_assets | NULL | ref  | uq_asset_type_name_alive,ix_capability_assets_asset_type | uq_asset_type_name_alive | 580 | const,const |    1 |   10.00 | Using where |
```

**P-07 治理列表**（`asset_type='plugin' 存活行 ORDER BY updated_at DESC, id ASC LIMIT 50`）：

```
|  1 | SIMPLE | capability_assets | NULL | ref  | uq_asset_type_name_alive,ix_capability_assets_asset_type | uq_asset_type_name_alive |  66 | const |   12 |   10.00 | Using where; Using filesort |
```

**EXPLAIN ANALYZE 实测计时**（行为证据，非结论）：

- P-01 latest：`Limit: 20 row(s) (actual time=0.578..0.587 rows=20)` ← Filter 实际命中 181 行 / Table scan 194 行。**端到端 0.587ms**，NFR-01 预算 800ms，余量 >1000x。
- P-03 hot：`Limit: 20 row(s) (actual time=1.32..1.32 rows=20)`；派生表 `Index scan on capability_installs using idx_installs_asset (actual time=0.299..0.302 rows=1)`。**端到端 1.32ms**。10x 余量（≈2000 资产 / 数百 installs）下线性外推仍在个位数 ms。

**注**：`filtered=1.10` 是优化器多列独立统计的低估；实测过滤命中 181/194 = 93%（ANALYZE Filter rows=181）——这正是全表扫优于索引的计划依据，与 §5「已评估不建」互证。

命令与退出码：`mysql -h 127.0.0.1 -u auto_agents auto_agents -e "EXPLAIN …; EXPLAIN ANALYZE …"` → 逐批 exit 0（本机 2026-09-15，完整命令在会话记录）。

---

## 6. Redis 键

**本特性不涉及 Redis。** 闸 = Dynaconf 配置读（POWER_MARKET.ENABLED，保持配置即代码 R1）；同步/导入/清理零缓存键；事件走 product_events 表。

## 7. 数据量与增长

| 表 | 当前行数（实测） | 日增 | 一年后 | 归档 |
|---|---|---|---|---|
| capability_assets | 194（live 182；bug 修复后 plugin +6） | ≈0（同步幂等，仅内容变更时 UPDATE） | <500 | 不需要 |
| capability_installs | 1（live 1） | 闸关 = 0；闸后随订阅 | 低两位数 | 不需要 |
| product_events | 139 | +四事件低频 | 数千 | 追加表，按既有策略 |

**10x 余量口径**：货架/治理查询按 2000 行、installs 按数百行设计——全部模式在余量内仍是全表扫/内存排序，零索引需求（§5 依据）。

---

## 8. 变更与迁移 050 规格（T-05 落地件；本帽交付物不含迁移文件，此节为逐行规格）

**本次为纯加法变更**：两条 `add_column`（一条 NOT NULL 带 server_default，一条 nullable）。无 drop / alter / rename / raw SQL ⇒ 无破坏性 DDL，无 expand-contract 需要。

文件 `backend/alembic/versions/050_asset_featured_examples.py`：

- `revision = "050"`，`down_revision = "049"`（实测 alembic head = 049 单头；**049 为 WIP 基底不可重写**，050 只追加）。
- upgrade（顺序 featured → examples）：

```python
op.add_column(
    "capability_assets",
    sa.Column("featured", sa.SmallInteger(), nullable=False, server_default="0",
              comment="FR-04 精选置顶标志 0/1"),
)
op.add_column(
    "capability_assets",
    sa.Column("examples", sa.JSON(), nullable=True,
              comment="帮你做示例 list[str]；NULL=未维护"),
)
```

- downgrade（**反序** examples → featured，非 pass）：

```python
op.drop_column("capability_assets", "examples")
op.drop_column("capability_assets", "featured")
```

门禁自检（tools/check/db_migrations.sh）：SM-1 无 drop ✓｜SM-3/4 无类型收窄/rename ✓｜**SM-5 NOT NULL + server_default="0" ✓**｜SM-6 capability_assets 不在大表清单（194 行，INPLACE 即时）✓｜SM-7 downgrade 非 pass ✓｜SM-8 无 raw SQL ✓。

**DDL 可逆性证明（up → down → up，会话级临时表克隆 `CREATE TEMPORARY TABLE _dba050 LIKE capability_assets`，不触碰真表与 alembic_version）**：

```
up   #1: SHOW COLUMNS LIKE 'featured' → featured smallint NO Default 0
          SHOW COLUMNS LIKE 'examples' → examples json    YES Default NULL
down  : SHOW COLUMNS LIKE 'featured' → 空结果集（两列已消失）
up   #2: SHOW COLUMNS LIKE 'featured' → featured smallint NO Default 0
          SHOW COLUMNS LIKE 'examples' → examples json    YES Default NULL
mysql_exit=0
```

ORM 对齐（platform_core/models/capability.py `CapabilityAsset`，随 050 同票；JSON 沿用 `from sqlalchemy.dialects.mysql import JSON` 惯例）：

```python
featured = Column(SmallInteger, nullable=False, default=0, server_default="0",
                  comment="FR-04 精选置顶标志 0/1")
examples = Column(JSON, nullable=True, comment="帮你做示例 list[str]；NULL=未维护")
```

T-05 验收命令：`uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`（三连 exit 0）+ `bash tools/check/db_migrations.sh` + `bash tools/check/db_ir.sh`（均 exit 0）。

---

## 9. 需真库验证的方言特性（交 /qa）

- **`NULLS LAST` 是 PostgreSQL 语法，MySQL 运行时报语法错**（项目已知事故模式）。contract AD-6 原文「计数 DESC NULLS LAST」**不可照抄进 sorting.py**——必须写 `COALESCE(cnt, 0) DESC`（左联无订阅行的 NULL 归零；语义与「无数据降级不显示数字」一致）。§5E 的 P-03 EXPLAIN 即按 COALESCE 形态验证通过。
- MySQL `ORDER BY … DESC` 将 NULL 排最后：本轮排序列（updated_at / featured）均 NOT NULL 无影响；installs 计数 NULL 已由 COALESCE 消除——不依赖方言巧合。
- P-03 出现 `Using temporary; Using filesort`：实测 1.32ms@181 行，可接受；资产上四位数（>10x 余量）时复查（spec 护栏 P95>800ms 回滚）。
- 生成列 alive_flag + 含生成列的唯一索引：SQLite/测试基建与 MySQL 行为差异——GWT-01.7 并发 IntegrityError 兜底只能真库 MySQL 验；qa 核对 backend/tests 的 DB 方言。
- JSON 列不依赖表达式默认值（MySQL 8 允许 JSON 默认 NULL；5.7 不允许表达式 default——本设计零默认值，规避差异）。

## 10. 开放问题

| 问题 | 阻塞什么 | 需谁定 |
|---|---|---|
| featured/examples PATCH 触发 updated_at onupdate 跳变 → 资产进入「最新」档前排。默认接受（运营也是更新，无 GWT 反例）；若 pm 要「内容时间」语义，需 PATCH 显式保持旧 updated_at 或改排序键 | T-06 排序细节（不阻塞 050 建列与迁移） | pm |
| 目录导入 batch_id 为应答内生成回执号、不入库（无状态两段式既定）。若操作者要事后审计单次导入明细，写 product_events.props.batch_id 即可（仍不建表） | 无（默认已定，可事后追加） | operator |
