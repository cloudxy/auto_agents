# 实现证据 · T-35 能力资产一键导入通道（上传/沙箱/四类/部分成功/幂等 + asset_imported）

> 票：contract §11 T-35 + §7.9 / spec FR-100 GWT-100.1…100.8 + GWT-92.9 / ADR-0023 / db-spec §16.5 迁移 043｜角色：/backend｜日期：2026-09-11

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| `POST /capabilities/import`（multipart 文件 或 directory 表单；422/404/200） | Router | `backend/app/api/v1/capabilities.py` | file×N 与 directory 二选一；非 md/zip 文件跳过并留日志 |
| 权限：仅平台超管，直打 404 同形（GWT-100.6） | Router 依赖 | 同上（`require_platform_admin_or_404`） | 不走 403 信封 |
| 大小/条目数上限（NFR-10 配置即代码） | 配置 | `config/default/asset_import.yml` + `backend/config_consts.py`（ASSET_IMPORT_*） | 10MB/条目、50MB/批、200 条目；测试可覆写 |
| 沙箱收容 + 四类判定 + 部分成功 + 幂等 + 批次收口 + 事件 | Service | `backend/services/asset_import_service.py` | 事务自持（ADR-0007 D3），API 直调即完整业务操作 |
| 条目路径收容（`../`/绝对/symlink）、流式限长解压、frontmatter/名称解析 | Service 辅助 | `backend/services/asset_import_sandbox.py` | R10 规避下划线私有（模块级公开函数需 logger） |
| 批次/明细读写 | Service 内联 ORM（跟仓惯例，无独立 Repository） | 同上 | plugin_service/expert_service 同款 |
| 迁移 043 两表（CASCADE/RESTRICT） | Alembic | `backend/alembic/versions/043_t35_asset_import_batches_items.py` | 链：down_revision=042；down 先撤 FK 再撤索引（MySQL 1553） |
| ORM 两表 + TENANT_EXEMPT 登记 | ORM | `platform_core/models/asset_import.py` + `backend/app/tenant_isolation.py` + `platform_core/models/__init__.py` | tenant_id 恒 NULL，禁 TenantMixin（PIT-3，product_events 同款） |
| 错误码映射 | 统一异常处理器 | ValidationException → 422 信封 | 不在 Router 逐个 try/except |

**分层依赖核对**：☑ Router 未 import ORM（仅 Service）☑ Service 未把 ORM 活实例传出 commit（P-BE-01：batch_id/asset_id commit 前快照）☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/alembic/versions/043_t35_asset_import_batches_items.py` | 新增 | asset_import_batches/items 两表（db-spec §16.5 SQL 骨架逐列对齐） |
| `platform_core/models/asset_import.py` | 新增 | AssetImportBatch / AssetImportItem |
| `platform_core/models/__init__.py` | 修改 | 导出两模型（create_all 注册面） |
| `backend/app/tenant_isolation.py` | 修改 | TENANT_EXEMPT_TABLES +2（同 PR，PIT-3） |
| `backend/services/asset_import_service.py` | 新增 | 统一导入通道（499 行 ≤500） |
| `backend/services/asset_import_sandbox.py` | 新增 | 沙箱收容/上限执法/四类分类（312 行） |
| `backend/app/api/v1/capabilities.py` | 修改 | +POST /import（静态段先于动态段，文件头顺序约束遵守） |
| `config/default/asset_import.yml` | 新增 | ASSET_IMPORT 上限（NFR-10） |
| `backend/config_consts.py` | 修改 | ASSET_IMPORT_* 兜底常量（B3 单点） |
| `backend/tests/test_t35_asset_import.py` | 新增 | GWT-100.1…100.8 + 92.9 + 整批失败/坏路径口径 |
| `backend/tests/test_t35_migration_043.py` | 新增 | 043 up→down→up + CASCADE/RESTRICT（mysql_fidelity） |
| `backend/tests/test_db_fixtures.py` | 修改 | ALL_ORM_TABLES 注册两新表（等值断言守卫自身要求） |

**与票里「会改哪些文件」一致**：☑ 是（导入 API+解析+沙箱+迁移 043+事件；未触碰导入 UI=T-36）

**未触碰「不许改的文件」**：☑ 确认（relay/llm_gateway 零 import，B4 同口径；未动 skill_import_service URL 通道与扫描端点——ADR-0023「不废不移」）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 批次行 + 明细行 + capability_assets 行（逐条 begin_nested） | 是 | 批次回放与目录行原子；单条失败不拖垮整批（部分成功常态） |
| 落盘（copy/write） | 在 nested 内 | 落盘异常回滚该条目录行（不产生「有行无文件」的成功项） |
| asset_imported 事件 | 否（commit 后独立短会话） | 至少一次；失败不挡主路径（product_event_service 既有语义） |

**事务提交后的操作失败怎么办**：事件失败仅 logger.warning（可接受，至少一次语义由查询面兜底）；沙箱清理失败 ignore_errors（系统 temp，进程可回收）。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 业务自然键 = asset_type + name（db-spec §16.5） |
| 保证方式 | 既有 `uq_asset_type_name_alive` + 逐条 `begin_nested` 捕 IntegrityError |
| 重复请求返回 | 200；该条 status=skipped、不产生第二行（GWT-100.8） |

☑ 未使用「先查后插」当唯一保证（SELECT 仅做 skip 语义；并发安全由唯一键 + savepoint 降级 skipped 承担）

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 同资产并发导入 | 唯一键 uq + nested savepoint | IntegrityError → skipped（见 §6 N/A 注记） |

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 无外部调用（本地上传/本地目录；ADR-0023「Wave A 无新外部依赖」） | — | — | — | — |

## 4. ORM 与 DBML 对齐

☑ 字段名 ☑ 类型 ☑ 可空性 ☑ 默认值 ☑ 索引（idx_import_items_batch）☑ 唯一约束（无新增——幂等键复用既有 uq_asset_type_name_alive）☑ 外键（batch CASCADE / asset RESTRICT）——全部与 db-spec §16.5 一致

结构核对输出（真实 MySQL 8 隔离库，MYSQL_FIDELITY 通道）：

```
$ MYSQL_FIDELITY=1 uv run pytest -q backend/tests/test_t35_migration_043.py
{'CONSTRAINT_NAME': 'fk_import_items_asset', 'DELETE_RULE': 'RESTRICT', 'REFERENCED_TABLE_NAME': 'capability_assets'}
{'CONSTRAINT_NAME': 'fk_import_items_batch', 'DELETE_RULE': 'CASCADE', 'REFERENCED_TABLE_NAME': 'asset_import_batches'}
.  [100%]
1 passed in 3.75s
exit: 0
```

（information_schema 权威口径；SQLAlchemy inspector 不回填 ondelete，测试直读 DELETE_RULE。）

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `import_files/import_directory` 入口记 origin/files/path/actor；`asset_import.done` 记 batch/total/succeeded/failed/skipped；条目拒绝 `logger.warning` 记 entry+reason |
| 审计 | `record_audit(action="asset.import", target="batch#N", detail=计数)` |
| 事件 | `asset_imported`（props: origin/types/succeeded/failed；tenant_id NULL，actor_user_id=操作者） |
| 错误日志上下文 | 失败条目名 + 中文原因；落盘失败记 type/name/err |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无上传内容正文（只记名称/尺寸）

## 6. 自测证据

> 命令与退出码**原样粘贴**。

```
$ cd /Users/xuyun/auto_agents && uv run pytest -q backend/tests/test_t35_asset_import.py backend/tests/test_t35_migration_043.py
.............s                                                           [100%]
13 passed, 1 skipped in 3.33s
exit: 0
（1 skipped = test_t35_migration_043 的 mysql_fidelity 门，下条真库验证）

$ cd /Users/xuyun/auto_agents && MYSQL_FIDELITY=1 MYSQL_FIDELITY_PASSWORD=*** uv run pytest -q backend/tests/test_t35_migration_043.py
.                                                                        [100%]
1 passed in 3.75s
exit: 0
（042→043→042→043 up-down-up 三连 + CASCADE/RESTRICT 实库断言）

$ cd /Users/xuyun/auto_agents && uv run pytest -q backend/tests
1486 passed, 38 skipped, 7 warnings in 176.86s (0:02:56)
exit: 0

$ cd /Users/xuyun/auto_agents && bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0

$ cd /Users/xuyun/auto_agents && bash tools/check/db_migrations.sh
✓ 迁移破坏性变更检测通过
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-100.1 单文件导入未上架 | `test_gwt_100_1_single_zip_import_unlisted`（listing_state=unlisted + 完成反馈含类型与名称） | ✅ |
| GWT-100.2 目录部分成功 | `test_gwt_100_2_directory_partial_success`（2 合法跨类型入库 + 1 不合法列名+中文原因 + 批次/明细行） | ✅ |
| GWT-100.3 空态中性句 | `test_gwt_100_3_nothing_importable`（total=0 + 「没有可导入的资产。」 + completed，非静默非失败句） | ✅ |
| GWT-100.4 四类齐自动判定 | `test_gwt_100_4_four_types_auto_detected`（skill/agent/command/plugin 一批全中，无手工分型） | ✅ |
| GWT-100.5 超大拒绝含上限数字 | `test_gwt_100_5_oversize_rejection_with_limit_number`（zip 内条目 + 独立 .md 两形态；同批合法项继续） | ✅ |
| GWT-100.6 越权 404 同形 | `test_gwt_100_6_non_admin_direct_post_404_shape`（404 + message="Not Found" + 零批次零目录行） | ✅ |
| GWT-100.7 逃逸三形态 + 零新文件 | `test_gwt_100_7_escape_three_forms_zero_leak`（../、绝对、symlink 各一例，原因列条目名，tmp 区快照差集=仅库内合法产物）+ `test_gwt_100_7_directory_channel_symlink_rejected`（目录通道 symlink） | ✅ |
| GWT-100.8 幂等重导 | `test_gwt_100_8_idempotent_reimport`（第二次 skipped=1、目录单行、skipped 行 asset_id/reason=NULL） | ✅ |
| GWT-92.9 asset_imported | `test_gwt_92_9_asset_imported_event_queryable`（props origin/types/succeeded/failed + tenant_id NULL + actor + /product-events 超管查询面可查） | ✅ |
| 迁移 043 up→down→up | `test_migration_043_up_down_up_and_fk_semantics`（真 MySQL；CASCADE/RESTRICT 行为断言）+ `test_migration_043_chain_anchor`（revision=043/down_revision=042） | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | 逐条 nested：逃逸/落盘失败条目不留半行（100.7 断言目录行数=1） | ✅ |
| 幂等 | `test_gwt_100_8_idempotent_reimport` | ✅ |
| 并发写 | ➖ N/A：单写者超管通道；并发撞键由 uq_asset_type_name_alive + savepoint→skipped 兜底（既有 `test_adr_0012_uq_asset_type_name_alive_unchanged` 钉约束存在） |
| 外部依赖失败 | ➖ N/A：ADR-0023「Wave A 无新外部依赖」，本通道零外呼（trust_env 风险面不存在） |

N/A 理由已给，未空着。

## 7. NFR 验证

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-04/SEC-11 | 导入写入限定资产目录内；逃逸条目拒绝且列入失败原因 | tmp 区文件级快照差集 == 仅 library/ 内合法产物；三形态逃逸各一例拒绝且原因含条目名；沙箱结束即清理 | 本地测试（sqlite 引擎 + 真文件系统） |
| NFR-10 | 上限来自配置不硬编码 | `config/default/asset_import.yml`；测试运行时覆写 MAX_FILE_BYTES/MAX_BATCH_BYTES 生效（100.5 用例即证明读配置） | 同上 |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | (1) 明细/插件细节表不在导入内：文件落盘布局与既有扫描器一致（skills/、plugins/、agents/、commands/），`POST /capabilities/scan-plugins`、scan-experts、技能扫描可对导入产物补全细节表（upsert 语义，不产生第二行）。(2) 非 .md 非 zip 的杂项文件（如 .bin 单传）拒绝只留日志不进 items（GWT-100.3 不可导入语义）；无分组归属的裸 `../x`、裸绝对路径成员同样只拒绝+日志（携带包的逃逸才进 items——类型判定需要包标记，裸条目无诚实类型可写）。(3) 独立 .md 判型规则：SKILL.md→skill、AGENT.md→agent、其余→command。(4) 422 是 ValidationException 信封（跟仓口径，非 400）。(5) 上传总量超限在批次开批前拒绝（无批次行）；解包累计超限开批后整批 failed 留痕。 |
| `/frontend`（T-36） | 契约面：`POST /api/v1/capabilities/import`，multipart `file`（可重复，单 .md 或 zip）或 form `directory`（二选一，同传 422「文件与目录只能二选一」）。响应 data：batch_id/origin/status/total/succeeded/failed/skipped/items[{asset_type,name,status,reason?,asset_id?}]/message?（total=0 时 message=「没有可导入的资产。」）。逐条失败原因已是中文成品句，可直接渲染。 |
| `/architect` | 无契约歧义需裁；一个实现层决策已定死：逃逸/超大**条目**的拒绝归属其顶层分组并使该资产整体失败（不写半份），GWT-100.7「该条目拒绝」+「同批合法项部分成功」同时成立。 |
| `/sre` | 配置项已落 `config/default/asset_import.yml`（ASSET_IMPORT.MAX_FILE_BYTES/MAX_BATCH_BYTES/MAX_ENTRIES/SANDBOX_ROOT）；深度病毒扫描仍记 §13 残留（ADR-0023）。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（1486 passed / 0 failed；arch 0；db_migrations 0）
- [x] 契约落位表已核对，分层无违规（R7 Router 零 ORM；R10 下划线私有；R13 两表豁免登记同 PR）
- [x] ORM 与 db-spec §16.5 一致，未自行加字段；幂等键复用既有 uq，零新键
- [x] 无硬编码连接串/密钥/端口/阈值（上限全走 ASSET_IMPORT.* 配置）
- [x] async 上下文无同步阻塞调用（零 redis、零 httpx）
- [x] 无 `except: pass`（BLE001 均带 logger）
- [x] 日志已脱敏（无内容正文/token）
- [x] 事务里无外部调用（落盘在 nested 内属本地 IO，事件在 commit 后）
- [x] 幂等未用「先查后插」当唯一保证（uq + savepoint）
- [x] 条件更新的 `rows == 0` 已处理（无条件更新场景；IntegrityError→skipped 已处理）
- [x] 外部依赖四件套 N/A（零外呼，ADR-0023 Wave A 口径）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报（无；§8 记下游信息）
- [x] 票状态：done
