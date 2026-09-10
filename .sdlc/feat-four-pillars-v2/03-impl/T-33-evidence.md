# 实现证据 · T-33 人工短名 alias；冲突保存失败；同步不建

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-33.md`｜FR 锚点：FR-45｜角色：/backend｜日期：2026-09-10
> 上游：ADR-0012 · spec v1.6 FR-45 · db-spec `capability_aliases` · T-23 公开详情
> 泳道：L4

未改 `uq_asset_type_name_alive`。同步不 insert alias（T-29 路径无 `CapabilityAlias`）。未给 alias 加 `TenantMixin`。租户/经办不能写 alias。未把 alias 当第一方回填。未复活 028–030。未代选六问。`capability_installs` 仍不在 `TENANT_EXEMPT_TABLES`。

公开 `GET /public/capabilities/aliases` 仍是 PIT-1 静态段 HTML 404（解析走 `/{type}/{name}`）。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径/方法/状态码 | Router | `backend/app/api/v1/capabilities.py` · `public_skills.py` | PUT `/{type}/{name}/alias` 仅超管；公开 GET `/{type}/{name}` 接受目录短名或 alias。静态 `/aliases` 先于动态段 |
| 字段校验（slug 1–128） | Schema | `power_market/types.py` `PutAliasRequest` | strip；空/超长 422 |
| 跨字段：撞存活目录短名或存活 alias | Service | `aliases.py` `AliasWriter` | 先查再写；唯一键兜底 IntegrityError → 409 |
| 权限判定 | **Router 守卫** | `require_platform_admin` | 经办/租户 admin 403 `FORBIDDEN` |
| 业务规则/状态流转 | Service | `aliases.py`；`service.py` `_load_named` | 一资产一条存活 alias；公开先目录短名再 alias |
| 数据读写 | ORM | `CapabilityAlias` | 038；不改 uq |
| 错误码映射 | 统一异常 | `ALIAS_CONFLICT` 409；守卫 403 | Router 无 try/except |
| 幂等 | 唯一约束 + 同 slug 直接返回 | `uq_aliases_slug_alive` / `uq_aliases_asset_alive` | 冲突不写，两边不变 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未把 ORM 送出 API ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `platform_core/models/capability.py` | 修改 | `CapabilityAlias`；无 TenantMixin；**不改** uq |
| `platform_core/models/__init__.py` | 修改 | 导出 `CapabilityAlias` |
| `backend/alembic/versions/038_t33_capability_aliases.py` | 新增 | revises 037；CREATE alias 表 |
| `backend/app/tenant_isolation.py` | 修改 | `capability_aliases` 进 `TENANT_EXEMPT_TABLES` |
| `backend/app/api/v1/capabilities.py` | 修改 | PUT `/{type}/{name}/alias` 于动态 GET 之前 |
| `backend/app/api/v1/public_skills.py` | 修改 | 静态 `/aliases` 仍先注册；详情走 alias 解析 |
| `backend/services/power_market/{aliases,types,service,__init__}.py` | 新增/修改 | 写冲突、请求体、公开解析 |
| `backend/tests/test_t33_aliases.py` | 新增 | GWT-45.1…45.5 + PIT-1 + 038 |
| `backend/tests/test_saas_isolation.py` | 修改 | PIT-3 `capability_aliases` 豁免夹具 |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：admin 写面用 PUT `/{type}/{name}/alias` 三段路径，避免二段静态与动态抢注册；公开解析落在已有 `/{type}/{name}`）

**未触碰「不许改的文件」**：☑ 确认（未改 uq、未在 src_sync insert alias、未豁免 installs、未复活 028–030）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 冲突检查 + insert/update alias | 是 | 失败则两边不变 |
| 审计 alias.set | 否 | 现网独立短事务 |

**事务提交后的操作失败怎么办**：审计失败只记日志（现网 `record_audit`）

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 存活 slug 全局唯一 `uq_aliases_slug_alive`；一资产一条 `uq_aliases_asset_alive` |
| 保证方式 | 应用层挡存活 `assets.name` 与存活 alias；同 slug 直接返回；IntegrityError → 409 回滚 |
| 重复请求返回 | 同 slug 200 现状；冲突 409，两边字节不变 |

☑ 冲突路径禁止「先改后发现再部分提交」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 两超管同时写同一 slug | 唯一约束 + IntegrityError | 回滚 → 409 `ALIAS_CONFLICT` |

☑ 条件更新 N/A（无 status 机）

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 无新外部依赖 | — | — | — | N/A |

## 4. ORM 与 DBML 对齐

☑ 字段名 ☑ 类型 ☑ 可空性 ☑ 默认值 ☑ 索引 ☑ 唯一约束 ☑ 外键 —— `capability_aliases` 与 db-spec 一致：`slug` VARCHAR(128)、`asset_id` RESTRICT、`asset_type` 反规范化、`tenant_id` 可空恒 NULL、软删 + `alive_flag` 生成列、`uq_aliases_slug_alive` / `uq_aliases_asset_alive`。未改 `uq_asset_type_name_alive`。

结构核对输出：

```
$ bash tools/check/db_migrations.sh
迁移破坏性变更检测（strong_migrations 语义）
==============================================
✓ 迁移破坏性变更检测通过
db_exit:0
```

038 revises 037；upgrade 无 INSERT / 无 028_/029_/030_。

**未自行加字段/改类型**：☑ 确认（仅 db-spec 列）

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `set_alias` 记 type/name/slug |
| trace_id | 现网中间件 |
| 错误日志上下文 | 越权走 `require_platform_admin` leftover |
| 慢操作耗时 | N/A 单行点查 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。

TDD 红（PUT alias 路由未建）：

```
$ uv run pytest -x -q backend/tests/test_t33_aliases.py --tb=line
F
E   AssertionError: {"detail":"Not Found"}
    assert 404 == 200
FAILED backend/tests/test_t33_aliases.py::test_gwt_45_1_alias_url_same_row_as_catalog_slug
1 failed in 1.93s
exit: 1
```

绿：

```
$ uv run pytest -q backend/tests/test_t33_aliases.py backend/tests/test_b1c_capabilities_coverage.py backend/tests/test_saas_isolation.py
........................................................................ [ 87%]
..........                                                               [100%]
82 passed in 11.97s
pytest_exit:0

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
arch_exit:0

$ bash tools/check/db_migrations.sh
✓ 迁移破坏性变更检测通过
db_exit:0

$ uv run python /Users/xuyun/.zcode/local-plugins/sdlc-workflow/skills/impl-evidence/scripts/check-layering.py
✓ 分层依赖检查通过
layering_exit:0

$ rg 'uq_asset_type_name_alive' platform_core/models/capability.py
UniqueConstraint("asset_type", "name", "alive_flag", name="uq_asset_type_name_alive")
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-45.1 到达详情，与目录短名同一行 | `test_gwt_45_1_alias_url_same_row_as_catalog_slug` | ✅ |
| GWT-45.2 无 alias 时目录短名仍达详情 | `test_gwt_45_2_catalog_slug_works_without_alias` | ✅ |
| GWT-45.3 经办/租户拒绝；公开地址集合不变 | `test_gwt_45_3_tenant_operator_cannot_set_alias` | ✅ |
| GWT-45.4 冲突失败；两边短名不变 | `test_gwt_45_4_conflict_catalog_name_both_unchanged` · `test_gwt_45_4_conflict_live_alias_both_unchanged` | ✅ |
| GWT-45.5 同步零新建 alias | `test_gwt_45_5_src_sync_creates_zero_aliases` · `test_sync_path_does_not_insert_alias` · T-29 `test_no_auto_alias_on_sync` | ✅ |
| PIT-1 静态段先于动态段；b1c F-1 仍 200 | `test_pit1_public_aliases_registered_before_dynamic` · `test_pit1_admin_alias_write_before_dynamic_detail` · `test_plugin_detail_contract` / expert / team | ✅ |
| PIT-3 豁免同 PR；installs 仍不豁免 | `test_t33_aliases_table_exempt` | ✅ |
| PIT-2 超管可写、经办拒 | 45.3 403 `FORBIDDEN` | ✅ |
| Alembic 038 revises 037 | `test_migration_038_revises_037` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | 45.4 两夹具：失败后 alias 快照与目录短名字节不变 | ✅ |
| 幂等 | 同 slug 直接返回；冲突不写 | ✅ 45.4 |
| 并发写 | 唯一约束 IntegrityError → 409 | ➖ 单测走应用层预查；约束在 ORM/038 |
| 外部依赖失败 | ➖ N/A | 无新外部依赖 |

## 7. NFR 验证（票里有 NFR 时填）

票无独立 NFR 编号。公开详情仍走 T-23 商店不存在句 HTML 404。无硬编码连接串。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 超管 `PUT /api/v1/capabilities/{type}/{name}/alias` body `{slug}`。冲突 409 `ALIAS_CONFLICT`「该短名已被占用，两边都未改动」。公开详情 JSON 的 `name` 仍是目录短名（alias 只是 URL）。`GET /public/capabilities/aliases` 仍 HTML 404。经办 403。src_sync 后 alias 表 0 行。 |
| `/frontend` | 访客打开 `/{type}/{alias}` 与 `/{type}/{catalogName}` 同一卡片。admin 写 alias 仅超管；租户页不要放入口。 |
| `/architect` | 新码：`ALIAS_CONFLICT` 409。未改公开 GET 404 信封。 |
| `/dba` | 038 只建 `capability_aliases`；uq 未改。 |
| `/backend` | 同步路径禁止 import/insert `CapabilityAlias`（测试锁）。 |

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
- [x] 外部依赖：本票无
- [x] 四类易漏测试已标 N/A 并给理由
- [x] 发现的上游问题已回报（`ALIAS_CONFLICT` 新码）
- [ ] 票状态仍 todo（交 orchestrator 改 done）
