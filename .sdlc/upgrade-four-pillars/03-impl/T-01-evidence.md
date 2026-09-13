# 实现证据 · T-01 夹具名单与合格出数/拦住事件语义

> 票：`02-shape/contract.md` §10 T-01｜FR 锚点：FR-U03 FR-U01｜角色：/backend｜日期：2026-09-12

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| GET `/api/v1/product-events?is_internal_fixture=` | Router | `backend/app/api/v1/product_events.py` | 北极星等值谓词；NULL 旧行不进 false |
| GET/POST `/api/v1/admin/internal-fixture-tenants`；DELETE `/{tenant_id}` | Router | `backend/app/api/v1/internal_fixture_tenants.py` | 合同 §6 未给名单路径；按超管维护面落地 |
| `tenant_id` ge=1 | Schema | `platform_core/schemas/internal_fixture_tenant.py` | |
| 权限（仅超管；租户 404 同形） | Router | `require_platform_admin_or_404` | 数据范围=平台名单，不是本企业行 |
| 写入当时快照；移出不改历史 | Service | `product_event_service._fixture_snapshot` | emit 点查名单，禁止查询 JOIN |
| 加入/移出/列表 | Service | `backend/services/internal_fixture_tenant_service.py` | 移出=DELETE |
| 数据读写 | Repository | `internal_fixture_tenant_repository.py` + `product_event_repository.py` | |
| 错误码映射 | 统一异常处理器 | 既有 HTTP 404 同形 | 未新造 code |
| 幂等 | Service + 唯一约束 | 迁移 `045` `uk_internal_fixture_tenants_tenant` | IntegrityError → 返回已有行 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `platform_core/models/internal_fixture_tenant.py` | 新增 | 名单 ORM；无 TenantMixin / 无软删 |
| `platform_core/schemas/internal_fixture_tenant.py` | 新增 | Create / Out / ListOut |
| `backend/repositories/internal_fixture_tenant_repository.py` | 新增 | tenant_id 点查、物理删除 |
| `backend/services/internal_fixture_tenant_service.py` | 新增 | 加入（唯一键兜底）/ 移出 / 列表 |
| `backend/app/api/v1/internal_fixture_tenants.py` | 新增 | 超管维护面 |
| `backend/alembic/versions/045_n1_internal_fixture_tenants.py` | 新增 | N1 expand-only；revises 044 |
| `backend/tests/test_t01_internal_fixture.py` | 新增 | GWT-U03 + 快照不变 + 唯一键 |
| `platform_core/models/product_event.py` | 修改 | `is_internal_fixture` + P-U03 索引 |
| `platform_core/schemas/product_event.py` | 修改 | Out 加可空快照列 |
| `platform_core/models/__init__.py` | 修改 | 导出 InternalFixtureTenant |
| `platform_core/schemas/__init__.py` | 修改 | 导出名单 Schema |
| `backend/services/product_event_service.py` | 修改 | emit 点查快照 |
| `backend/repositories/product_event_repository.py` | 修改 | 等值过滤 `is_internal_fixture` |
| `backend/app/api/v1/product_events.py` | 修改 | Query 参数 |
| `backend/app/api/v1/__init__.py` | 修改 | 注册名单路由 |
| `backend/app/tenant_isolation.py` | 修改 | `internal_fixture_tenants` 进 TENANT_EXEMPT |
| `backend/tests/test_db_fixtures.py` | 修改 | ALL_ORM_TABLES 登记新表 |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：合同票表 T-01 标 /dba；本 spawn 为 backend+api，按 db-spec N1 落地 ORM/迁移/维护面/快照。未改 `040` 账单、未加凭据/SKU 表。）

**未触碰「不许改的文件」**：☑ 确认（未改 billing / payment / relay SKU / Scrapy）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 名单 INSERT/DELETE | 是（单表） | 当前态=有没有行 |
| 产品事件 persist + 夹具点查 | 是（独立短会话） | 沿用既有 extra session；快照与事件同行 |

**事务提交后的操作失败怎么办**：产品事件失败不挡主路径（既有 fail-open 记 warning）。名单维护无外部调用。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 业务自然键 `tenant_id` |
| 保证方式 | 唯一约束 `uk_internal_fixture_tenants_tenant` + 捕获 IntegrityError |
| 重复请求返回 | 已有行（200） |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 重复加入名单 | UNIQUE + IntegrityError | 回滚后按 tenant_id 读回已有行；读回空则原异常上抛 |
| 移出不存在 | DELETE rowcount 任意 | 幂等 200（不在名单=目标态） |

☑ 所有条件更新的返回行数都有处理（本票无状态机 UPDATE）

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 无新外部依赖 | — | — | — | — |

## 4. ORM 与 DBML 对齐

☑ 字段名 ☑ 类型 ☑ 可空性 ☑ 默认值 ☑ 索引 ☑ 唯一约束 ☑ 外键 —— 全部与 `schema.dbml` N1 段一致（无 tenants FK，按 db-spec）

结构核对输出（抛开库 upgrade 045 后 `SHOW CREATE TABLE`）：

```
CREATE TABLE `internal_fixture_tenants` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '代理主键，跟仓 INT',
  `tenant_id` int NOT NULL COMMENT '被标为夹具的企业；PIT-4 禁止 NULL=平台',
  `created_by` varchar(64) NOT NULL COMMENT '谁标的（超管用户名快照，无用户 FK）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '何时标上',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'R-AUD；移出为 DELETE',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_internal_fixture_tenants_tenant` (`tenant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

product_events 表尾：
  `is_internal_fixture` tinyint(1) DEFAULT NULL COMMENT '当时是否夹具企业。1=是 0=否 NULL=本列上线前旧事件',
  KEY `idx_product_events_name_occurred` (`event_name`,`occurred_at`),
  KEY `idx_product_events_tenant_occurred` (`tenant_id`,`occurred_at`),
  KEY `idx_product_events_name_fixture_occurred` (`event_name`,`is_internal_fixture`,`occurred_at`)
```

**未自行加字段/改类型**：☑ 确认

Alembic `044 → 045 → 044 → 045`（抛开库）：

```
OK upgrade 044 fixture_table=False fixture_col=False
OK upgrade 045 fixture_table=True fixture_col=True
OK downgrade 044 fixture_table=False fixture_col=False
OK upgrade 045 again fixture_table=True fixture_col=True
up-down-up 045 complete
exit: 0
```

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `InternalFixtureTenantService.add/remove/list_all`；`emit_product_event`；Router 记 username+tenant |
| trace_id | 沿用既有中间件 |
| 错误日志上下文 | 名单 tenant_id；事件 name+tenant |
| 慢操作耗时 | 点查唯一键，无新外部调用 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。

### TDD red（实现前）

```
$ uv run pytest -x -q backend/tests/test_t01_internal_fixture.py
F
=================================== FAILURES ===================================
_____________ test_gwt_u03_1_non_fixture_completed_snapshot_false ______________
...
>       assert row["is_internal_fixture"] is False
               ^^^^^^^^^^^^^^^^^^^^^^^^^^
E       KeyError: 'is_internal_fixture'
backend/tests/test_t01_internal_fixture.py:79: KeyError
=========================== short test summary info ============================
FAILED backend/tests/test_t01_internal_fixture.py::test_gwt_u03_1_non_fixture_completed_snapshot_false
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 7.52s
exit: 1
```

### TDD green

```
$ uv run pytest -q backend/tests/test_t01_internal_fixture.py
.........                                                                [100%]
9 passed in 3.66s
exit: 0
```

```
$ uv run pytest -x -q backend/tests
1555 passed, 39 skipped, 7 warnings in 230.53s (0:03:50)
exit: 0
```

```
$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0
```

```
$ uv run python PLUGIN_ROOT/skills/impl-evidence/scripts/check-layering.py backend/app/api backend/services backend/repositories
✓ 分层依赖检查通过
exit: 0
```

```
$ bash tools/check/db_migrations.sh
✓ 迁移破坏性变更检测通过
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-U03.1 正常 | `test_gwt_u03_1_non_fixture_completed_snapshot_false` | ✅ |
| GWT-U03.2 空态 | `test_gwt_u03_2_fixture_excluded_from_north_star` | ✅ |
| GWT-U03.3 越权 | `test_gwt_u03_3_tenant_query_and_membership_are_404` | ✅ |
| GWT-U03.4 边界 | `test_gwt_u03_4_blocked_distinct_from_completed` | ✅ emit 语义；入队拦住接线留给 T-02 |
| GWT-U03.5 正常 | `test_gwt_u03_5_completed_not_in_blocked_numerator` | ✅ |
| FR-U01 非夹具定义 | 名单 + 快照列；入队/本企业结果是 T-02 | ➖ 本票只提供判定输入 |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（名单单表写；事件独立短会话既有 fail-open） |
| 幂等 | `test_add_fixture_is_idempotent_unique_tenant` | ✅ |
| 并发写 | 同上 UNIQUE 兜底（SQLite 串行双 POST） | ✅ 未跑 gather 双写；约束已在 |
| 外部依赖失败 | — | ➖ N/A（无新外部依赖） |

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-U01 | 入队 3s | 本票不改入队路径 | — |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 北极星必须 `is_internal_fixture=false` 等值，勿 JOIN 名单。NULL=上线前旧事件，不进非夹具分子。GWT-U03.4 本票用 `emit_product_event("task_blocked")` 钉口径；工人/配额拦住接线是 T-02。MySQL 045 up→down→up 已在 root 抛开库跑过；`auto_agents` 用户无 CREATE DATABASE。 |
| `/frontend` | 超管名单：`GET/POST /api/v1/admin/internal-fixture-tenants`，`DELETE /api/v1/admin/internal-fixture-tenants/{tenant_id}`。查询：`GET /api/v1/product-events?is_internal_fixture=false`。合同 §6 未写名单 URL，若要改路径回 architect。 |
| `/architect` | 夹具维护 HTTP 路径合同未列；本票选用 `/admin/internal-fixture-tenants` + 404 同形。未新造错误码。 |
| T-02 / T-05 | 可直接依赖 `_fixture_snapshot`；拦住事件名 `task_blocked` + props.reason 已可查。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（不是「大部分通过」）
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`（吞异常）
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」
- [x] 条件更新的 `rows == 0` 已处理
- [x] 外部依赖四件套齐全（超时/重试/降级/幂等前提）— N/A 无新外部依赖
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 票状态：本 spawn 交付 evidence；orchestrator 更新 state
