# 实现证据 · T-29 源登记/同步；第三方不自动 listed；第一方夹具回填；D16 回退

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-29.md`｜FR 锚点：FR-38 / FR-41｜角色：/backend｜日期：2026-09-10
> 上游：ADR-0012 / ADR-0011 · spec v1.6 · db-spec capability_sources + origin_* · T-28
> 泳道：L4

未实现 T-30 命令货架。未自动建 alias（T-33）。未 attach 源进 Alembic。未改 `uq_asset_type_name_alive`。未复活 028–030。未改 T-27 引用 / T-26 卸载 / T-22 official 列表 UI。未代选六问 / Q-OPS-DUTY。指针未进 `capability-library/plugins/`。

TDD 红：`test_gwt_38_3_tenant_cannot_register` 在源路由落地前断言 403，现网走 `/{asset_type}/{name}` 得到 404。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径/方法/状态码 | Router | `backend/app/api/v1/capabilities.py` | GET/POST `/sources`；POST `/sources/{name}/sync`；POST `/backfill-first-party`；POST `/{type}/{name}/correct`。静态段先于动态段 |
| 字段校验（kind/uri） | Schema | `power_market/types.py` `CreateSourceRequest` | `local/git/url` |
| 跨字段：url/git 类创建失败 | Service | `sources.py` `SourceRegistry.register` | 400 `SOURCE_KIND_UNSUPPORTED`，不爬 |
| 权限判定 | **Router 守卫** | `require_platform_admin` | 租户登记/同步/纠正 403 |
| 业务规则/状态流转 | Service | `sync.py` `SourceSync`；`identity.py` | bundled slug；撞名失败；同步不 listed；D16 扫描仍 local |
| 数据读写 | ORM | `CapabilitySource` + assets 源列 + `skill_jobs.source_id` | 037；不改 uq |
| 错误码映射 | 统一异常 | `SOURCE_KIND_UNSUPPORTED` 400；`CORRECT_THIRD_PARTY` 409；`PLUGIN_NAME_COLLISION` 计入失败行 | Router 无 try/except |
| 幂等 | 唯一约束 | `uq_sources_name_alive`；目录 `uq_asset_type_name_alive` 未改 | 同步按 (type,name) upsert；异源撞插件名失败 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未把 ORM 送出 API ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `platform_core/models/capability.py` | 修改 | `CapabilitySource`；assets `source_id/origin_*/alias_origin_refs/writable`；`source_type` 32；**不改** uq |
| `platform_core/models/skill.py` | 修改 | `source_type` 32；`skill_jobs.source_id` |
| `platform_core/models/__init__.py` | 修改 | 导出 `CapabilitySource` |
| `backend/alembic/versions/037_t29_capability_sources.py` | 新增 | revises 036；无 attach 源；Step1 普通索引 |
| `backend/app/tenant_isolation.py` | 修改 | `capability_sources` 进 `TENANT_EXEMPT_TABLES` |
| `backend/app/api/v1/capabilities.py` | 修改 | 源/同步/回填/纠正路由 |
| `backend/services/power_market/{identity,walk,sources,sync,correct}.py` | 新增 | 身份/遍历/登记/src_sync/D5 |
| `backend/services/power_market/{types,service,listing,__init__}.py` | 修改 | 请求体、委托、第三方判定、公开 q 叠 origin_local_name |
| `backend/services/plugin_service.py` | 修改 | D16 `scan_mode=local_plugins` |
| `backend/services/skill_service.py` | 修改 | 第三方不写源树 |
| `backend/config_consts.py` + `config/default/power_market.yml` | 新增/修改 | `POWER_MARKET.ENABLED` 默认 false |
| `backend/tests/test_t29_sources.py` | 新增 | GWT-38.1–38.7 / 41.1–41.4 + ADR-0012 三断言 |
| `backend/tests/test_saas_isolation.py` | 修改 | PIT-3 `capability_sources` 豁免夹具 |
| `frontend/admin/src/pages/market/SourceTab.tsx` | 修改 | 源叶登记/同步（本票拥有 admin 源叶） |
| `frontend/admin/src/services/capabilities.ts` | 修改 | list/register/sync sources |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：admin 源叶按 packet 文件所有权一并落地；命令卡留给 T-30）

**未触碰「不许改的文件」**：☑ 确认（未改 uq、T-27 references、T-26 MyInstalls、official T-22 列表、028–030、plugins/ 指针）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| src_sync 作业 + 目录 upsert + 源计数 | 是 | 成功/失败数与目录同行提交 |
| 审计 source.register/sync | 否 | 现网独立短事务 |
| 第一方回填 | 是 | 多行 listing_state |

**事务提交后的操作失败怎么办**：审计失败只记日志（现网 `record_audit_standalone`）

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 源名存活唯一 `uq_sources_name_alive`；目录 `(asset_type,name,alive_flag)` |
| 保证方式 | 同名源 409；同名目录 upsert；异源同插件名失败且已有行 name 不变 |
| 重复请求返回 | 再同步更新内容；仅首次 attach 写 unlisted；同源再同步不改 listing_state/listed_at |

☑ 源名预查仅用于 409 文案；目录身份仍靠未改的 uq，禁止静默改名

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 第二同步 | Redis `market:src_sync:{name}` SET NX；故障放行 | 抢不到 → 409 `SYNC_IN_PROGRESS` |

☑ Redis 故障 fail-open（测试/降级），不是吞掉业务写

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| Redis 同步锁 | 配置 TTL 900s | 否 | 故障放行 | NX |
| url 类源 | 不发起 HTTP | — | 创建即失败「未支持」 | N/A |

## 4. ORM 与 DBML 对齐

☑ 字段名 ☑ 类型 ☑ 可空性 ☑ 默认值 ☑ 索引 ☑ 唯一约束 ☑ 外键 —— `capability_sources` 与 db-spec 一致；assets 只 ADD 源列；`host_compat` 已在 035，回填保持 NULL；`uq_asset_type_name_alive` 列集/列序未改；`idx_assets_source_origin_alive` 本波普通索引（Step1）

结构核对：037 revises 036；upgrade 无 `INSERT INTO` / 无 `listing_state` / 无 `zcode_local`。

**未自行加字段/改类型**：☑ 确认（仅 db-spec 列；未发明列）

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `register_source` / `src_sync` / `backfill_first_party` / `correct` 记 name/kind |
| trace_id | 现网中间件 |
| 错误日志上下文 | 单包失败 `logger.warning` 含 source/pkg；越权守卫 leftover |
| 慢操作耗时 | N/A 本地树扫描 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。

TDD 红（源路由未建，租户 POST `/sources` 被动态段吞成 404，不是 403）：

```
$ uv run pytest -x -q backend/tests/test_t29_sources.py --tb=line
.F
E   assert 404 == 403
FAILED backend/tests/test_t29_sources.py::test_gwt_38_3_tenant_cannot_register
1 failed, 1 passed in 1.83s
exit: 1
```

绿：

```
$ uv run pytest -q backend/tests/test_t29_sources.py backend/tests/test_saas_isolation.py::test_t29_sources_table_exempt
..................                                                       [100%]
18 passed in 4.35s
pytest_exit:0

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
arch_exit:0

$ bash tools/check/db_migrations.sh
✓ 迁移破坏性变更检测通过
db_exit:0

$ rg 'uq_asset_type_name_alive' platform_core/models/capability.py
UniqueConstraint("asset_type", "name", "alive_flag", name="uq_asset_type_name_alive")
```

回归（listing + 公开 q + 矫正 + b1c 扫描，此前同批）：105 passed。admin 治理台 jest：12 passed。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-38.1 成功/失败数；第三方非 listed | `test_gwt_38_1_sync_counts_third_party_unlisted` | ✅ |
| GWT-38.2 12 包在目录；失败原因在行内 | `test_gwt_38_2_partial_failure_keeps_success` | ✅ |
| GWT-38.3 租户登记 403；超管 GET 源列表前后一致 | `test_gwt_38_3_tenant_cannot_register` | ✅ |
| GWT-38.4 url 类未支持 | `test_gwt_38_4_url_kind_unsupported` | ✅ |
| GWT-38.5 D16 本机扫描回退 | `test_gwt_38_5_d16_*` | ✅ |
| GWT-38.6 纠正第三方不写源树；category 字节不变 | `test_gwt_38_6_correct_third_party_no_source_tree` | ✅ |
| GWT-38.7 租户纠正 403 | `test_gwt_38_7_tenant_correct_rejected` | ✅ |
| GWT-41.1 夹具短名可搜可订 | `test_gwt_41_1_fixture_searchable_and_subscribable` | ✅ |
| GWT-41.2 `mattpocock-skills__` 不公开 | `test_gwt_41_2_prefixed_third_party_not_public` | ✅ |
| GWT-41.3 租户上架第三方 403 | `test_gwt_41_3_tenant_cannot_list_third_party` | ✅ |
| GWT-41.4 attach 后不自动 listed | `test_gwt_41_4_attach_source_does_not_auto_list` | ✅ |
| ADR-0012 ① uq 未改 | `test_adr_0012_uq_asset_type_name_alive_unchanged` | ✅ |
| ADR-0012 ② bundled slug | 38.1 `pack-ok__short-name`；主标题非长前缀 | ✅ |
| ADR-0012 ③ 撞名失败、已有 name 不变 | `test_adr_0012_collision_second_source_fails` | ✅ |
| ADR-0012 ④ 夹具 example-pdf-extractor | 41.1 回填 listed 且 host_compat NULL | ✅ |
| PIT-3 豁免同 PR | `test_t29_sources_table_exempt` | ✅ |
| 迁移无 attach | `test_migration_037_has_no_attach_source` | ✅ |
| 同步不建 alias | `test_no_auto_alias_on_sync` | ✅ |
| content_hash 折叠 | `test_hash_fold_nested_copies` | ✅ |
| IM-20 超管 confirm listed → 再 src_sync 仍 listed | `test_im20_confirm_listed_src_sync_still_listed` | ✅ |
| IM-21 vendor/ 无 plugin.json 不入目录 | `test_im21_vendor_without_manifest_not_upserted` | ✅ |
| IM-23 git 类创建失败 | `test_im23_git_kind_unsupported` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A | 单次 src_sync 同会话提交；单包失败不中断整批，失败计入 job.detail |
| 幂等 | 同名源 409；再同步不改已有插件 name | ✅ 撞名测试 |
| 并发写 | Redis NX；故障放行 | ➖ 锁在无 Redis 测试里 fail-open |
| 外部依赖失败 | url 类不爬；纠正不写盘 | ✅ 38.4 / 38.6 |

## 7. NFR 验证（票里有 NFR 时填）

票无独立 NFR 编号。配置外置 `POWER_MARKET.ENABLED` / `SRC_SYNC_LOCK_TTL`。无硬编码连接串。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 源 API 仅超管。第三方**新行** `listing_state=unlisted`；同源再同步不改 listing_state/listed_at。url/git 创建 400「尚未支持」。D16 扫描永不声称已切源。夹具回填走 POST `/backfill-first-party`，不进迁移。无清单子目录（如 `vendor/`）不同步。 |
| `/frontend` | admin 源叶已接 list/register/sync。卡片主标题用 origin 短名，不要把 `{plugin}__{origin}` 当主标题。命令卡仍 T-30。 |
| `/architect` | 新码：`SOURCE_KIND_UNSUPPORTED` / `CORRECT_THIRD_PARTY` / `PLUGIN_NAME_COLLISION`（失败行内）/ `SYNC_IN_PROGRESS`。未改公开 GET 404。 |
| `/dba` | 037 加表加列 + source_type 加宽；uq 未改；UNIQUE 升格 `uq_asset_source_origin_alive` 仍 Step3 未做。 |
| `/backend` T-30 | 同步已写 bundled 技能行；命令独立卡片未做。 |
| `/backend` T-33 | 同步结束断言无自动 alias。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未靠静默改名
- [x] 条件更新 N/A
- [x] 外部依赖：url 不爬；Redis 锁故障放行
- [x] 四类易漏测试已标 N/A 并给理由
- [x] 发现的上游问题已回报（命令卡 T-30；alias T-33；UNIQUE Step3 未升）
- [ ] 票状态仍 todo（交 orchestrator 改 done）

## Rework · IM-20 / IM-21 / IM-22 / IM-23 / IM-25

会话 `01a08731-cca3-78b2-a073-153708a08ea4` G-fresh FAIL。未改 uq；未 attach 源进 Alembic；未写命令卡（IM-24 / T-30）；未代选六问。第三方**新行**仍 unlisted。

| IM | 根因 | 最小修复 |
|---|---|---|
| IM-20 major | `_attach_third_party` 每次 upsert 写 `listing_state=unlisted` | 仅 `source_id is None or source_id != this source` 写 unlisted；同源再同步不碰 listing_state/listed_at |
| IM-21 major | `_iter_packages` 子目录未 `_is_package`；无 plugin.json 仍 stub upsert | 子目录同样 `_is_package`（须有清单）；`vendor/` 跳过 |
| IM-22 minor | GWT-38.6 `or status in (400,409)` 永真 | 钉 409；`category` 与纠正前字节相同 |
| IM-23 minor | git 可登记，同步把 URI 当本地 Path 空转 200/0 包 | 创建失败，同 url，`SOURCE_KIND_UNSUPPORTED` |
| IM-25 minor | 38.3 用租户 GET（恒 403）比源列表 | 租户 POST 前后用超管 Bearer GET `/sources` 比 items |

未做 IM-24（T-30 命令卡）。

TDD 红（产品码未改）：

```
$ uv run pytest -x -q backend/tests/test_t29_sources.py::test_im20_confirm_listed_src_sync_still_listed backend/tests/test_t29_sources.py::test_im21_vendor_without_manifest_not_upserted backend/tests/test_t29_sources.py::test_im23_git_kind_unsupported --tb=short
F
E   AssertionError: assert 'unlisted' == 'listed'
FAILED backend/tests/test_t29_sources.py::test_im20_confirm_listed_src_sync_still_listed
1 failed in 2.38s
exit: 1

$ uv run pytest -q backend/tests/test_t29_sources.py::test_im21_vendor_without_manifest_not_upserted backend/tests/test_t29_sources.py::test_im23_git_kind_unsupported --tb=line
FF
E   AssertionError: assert 'vendor' not in {'real-pack', 'vendor'}
E   assert 200 in (400, 422)
FAILED backend/tests/test_t29_sources.py::test_im21_vendor_without_manifest_not_upserted
FAILED backend/tests/test_t29_sources.py::test_im23_git_kind_unsupported
2 failed in 2.31s
exit: 1
```

绿：

```
$ uv run pytest -x -q backend/tests/test_t29_sources.py backend/tests/test_saas_isolation.py
..................................                                       [100%]
34 passed in 7.36s
pytest_exit:0

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
arch_exit:0
```
