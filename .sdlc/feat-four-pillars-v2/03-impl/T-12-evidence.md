# 实现证据 · T-12 Wave 0 产品事件可查 + 用量上海日

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-12.md`｜FR 锚点：FR-15 / FR-16｜角色：/backend + 双前端｜日期：2026-09-08
> 上游：ADR-0016 · db-spec § product_events · schema.dbml
> 泳道：L4

未建仓；未做精确一次键；未做 T-32 市场事件；未代选六问；未回退 T-01 文案；未改 T-08 候选谓词；未改 T-13 worker idle。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径/方法/状态码 | Router | `backend/app/api/v1/product_events.py` | POST `/public/events` 200；GET `/product-events` 超管 200，租户 404 |
| 字段校验（类型/范围/枚举） | Schema | `platform_core/schemas/product_event.py` | 公开仅 `official_page_viewed` / `official_cta_clicked`；props 剥密码 |
| 跨字段参数约束 | Schema | 同上 | CTA 五档在 props |
| 权限判定（数据范围） | Router | `require_platform_admin_or_404` | 与 T-05 同形 HTTP 404 |
| 业务规则/状态流转 | Service | `product_event_service.emit_product_event` | 至少一次；独立短会话；失败吞掉 |
| 数据读写 | Repository | `product_event_repository.py` | 按 `occurred_at` 倒序；name/tenant 过滤 |
| 错误码映射 | 统一异常处理器 | `HTTPException` 404；限流 `RateLimitException` | Router 无业务 try/except |
| 幂等 | N/A | 无 UNIQUE | 合同禁止精确一次键 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未把 ORM 送出 API ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `platform_core/models/product_event.py` | 新增 | 非 Mixin；`occurred_at` 必填 UTC；无 onupdate |
| `platform_core/schemas/product_event.py` | 新增 | 公开入 / 超管出；五档 CTA 常量 |
| `backend/repositories/product_event_repository.py` | 新增 | 追加写 + 按发生时间查 |
| `backend/services/product_event_service.py` | 新增 | emit 独立会话；查询 DTO |
| `backend/app/api/v1/product_events.py` | 新增 | 公开埋点 + 超管查询 |
| `backend/alembic/versions/031_add_product_events.py` | 新增 | autogenerate CREATE + 两索引；revises 027（跳过 028–030 pyc） |
| `backend/app/tenant_isolation.py` | 修改 | `product_events` 进 TENANT_EXEMPT_TABLES |
| `backend/app/api/v1/__init__.py` | 修改 | 注册 public + admin 路由 |
| `backend/app/api/v1/auth.py` / `auth_service.py` | 修改 | login_succeeded / login_failed（credential/expired/locked） |
| `backend/app/api/v1/tenant_signup.py` / `tenant_signup_service.py` | 修改 | signup 带浏览 `anonymous_id` |
| `backend/services/spider_task_service.py` | 修改 | `task_run_submitted` / `task_completed` |
| `backend/services/spider_query_service.py` | 修改 | `results_exported`；近 7 日与失败率同一 `shanghai_window_start` |
| `backend/services/quota_service.py` | 修改 | 上海日/窗；`quota_exceeded` dimension |
| `backend/services/llm_usage_service.py` | 修改 | `_today()` = 上海业务日 |
| `frontend/official/src/services/beacon.ts` | 新增 | 匿名身份 + fire-and-forget |
| `frontend/official` Home/Pricing/SiteLayout/Register | 修改 | 页浏览 + 五档 CTA + 旁路另报 |
| `frontend/admin/src/pages/ProductEvents.tsx` | 新增 | 超管查询页，挂平台运营台 Tab |
| `backend/tests/test_product_events.py` | 新增 | GWT-15.1–15.19 查询面 |
| `backend/tests/test_llm_usage_service.py` 等 | 修改 | GWT-16.1–16.3 |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：查询面落 `/product-events` + `/platform-ops` Tab，未新建第六组菜单）

**未触碰「不许改的文件」**：☑ 确认（未改 T-08 谓词 / T-13 worker / T-01 卖点文案 / LiteLLM）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 主路径（登录/入队/配额拒绝） | 否 | 上报失败不挡；配额拒绝会 rollback 请求事务 |
| 事件行写入 | 独立短会话 commit | 主路径 rollback 不得带走已发生事实 |

**事务提交后的操作失败怎么办**：记日志，事件可缺失（GWT-15.2 至少一次）

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 无（合同禁止） |
| 保证方式 | 至少一次追加，允许重复 |
| 重复请求返回 | 再插一行 |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 追加写 | INSERT | N/A（无条件更新） |

☑ 无条件更新

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 公开埋点 Redis 限流 | 客户端默认 | 无 | fail-open | N/A |
| 事件落库 | 会话默认 | 无 | 吞异常，主路径成功 | 允许重复 |

## 4. ORM 与 DBML 对齐

☑ 字段名 ☑ 类型 ☑ 可空性 ☑ 默认值 ☑ 索引 ☑ 无唯一约束 ☑ 无 FK —— 与 `schema.dbml` Table product_events 一致

结构核对输出：

```
$ alembic autogenerate (include_object=product_events, live MySQL 无该表)
op.create_table('product_events', id INT PK, occurred_at DATETIME NOT NULL,
  event_name VARCHAR(64) NOT NULL, tenant_id INT NULL, actor_user_id INT NULL,
  anonymous_id VARCHAR(64) NULL, role VARCHAR(32) NULL, props JSON NULL,
  created_at/updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)
op.create_index idx_product_events_name_occurred (event_name, occurred_at)
op.create_index idx_product_events_tenant_occurred (tenant_id, occurred_at)
```

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `emit_product_event` / `query` / 公开埋点 记 name+tenant（无密码） |
| trace_id | 既有中间件 |
| 错误日志上下文 | 上报失败 warning 含 event_name |
| 慢操作耗时 | 未加独立计时（追加写） |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ props 剥 password/admin_password/token/access_token

## 6. 自测证据

```
$ uv run pytest -q backend/tests/test_product_events.py backend/tests/test_llm_usage_service.py backend/tests/test_spider_stats_nodes.py backend/tests/test_saas_quota.py
..................................................                       [100%]
50 passed in 5.95s
exit: 0

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 3 边界 + FR-14 发布物密钥，全部通过）
exit: 0

$ bash tools/check/db_migrations.sh
✓ 迁移破坏性变更检测通过
exit: 0

$ cd frontend/admin && npm test -- --watchAll=false --runInBand --testPathPattern='ProductEvents.test|Usage.test|App.test|usePermission.test'
Test Suites: 4 passed, 4 total
Tests:       16 passed, 16 total
exit: 0

$ cd frontend/official && npm test -- --watchAll=false --runInBand --testPathPattern='beacon'
Test Suites: 3 passed, 3 total
Tests:       8 passed, 8 total
exit: 0
```

全量 `uv run pytest -x -q backend/tests` 会在既有入队夹具碰到采集工人闸（T-13，本票未改）。本票新增/改动模块上表 50 passed。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-15.1 | `test_gwt_15_1_task_completed_non_candidate` | ✅ |
| GWT-15.2 | `test_gwt_15_2_emit_failure_does_not_block_enqueue` | ✅ |
| GWT-15.3 | `test_gwt_15_3_tenant_query_is_404_shell`；admin `App.test` `/platform-ops`；`usePermission.test` 无「产品事实/分析」 | ✅ |
| GWT-15.8 | `test_gwt_15_8_login_succeeded_carries_tenant` | ✅ |
| GWT-15.4 | `test_gwt_15_4_login_failed_reasons_no_password` | ✅ |
| GWT-15.5 | `test_gwt_15_5_signup_keeps_browse_anonymous_id` | ✅ |
| GWT-15.14 | `test_gwt_15_14_signup_without_browse_session` | ✅ |
| GWT-15.9 | `test_gwt_15_9_official_page_viewed`（home/pricing/register） | ✅ |
| GWT-15.6 | `test_gwt_15_cta_literals_not_merged[pricing_pro]` + Pricing.beacon | ✅ |
| GWT-15.15 | `[register_free]` + Pricing.beacon | ✅ |
| GWT-15.16 | `[pricing_enterprise]` + Pricing.beacon | ✅ |
| GWT-15.17 | `[login]` + SiteLayout.beacon | ✅ |
| GWT-15.18 | `[browse_market]` + SiteLayout.beacon | ✅ |
| GWT-15.10 | `test_gwt_15_10_task_run_submitted` | ✅ |
| GWT-15.11 | `test_gwt_15_11_results_exported` | ✅ |
| GWT-15.12 | `test_gwt_15_12_quota_exceeded_dimension` | ✅ |
| GWT-15.7 | `test_gwt_15_7_enter_admin_not_in_f1` + Home.beacon | ✅ |
| GWT-15.19 | `test_gwt_15_19_try_ai_flow_not_funnel_cta` + Home.beacon | ✅ |
| GWT-15.13 | `test_gwt_15_13_filter_by_tenant` | ✅ |
| GWT-16.1 | `test_gwt_16_1_shanghai_month_not_utc_yesterday` | ✅ |
| GWT-16.2 | `test_gwt_16_2_fail_rate_window_matches_last_7_days` | ✅ |
| GWT-16.3 | `test_gwt_16_3_platform_admin_usage_belongs_to_tenant_space` + Usage.test | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | 独立短会话：配额拒绝 rollback 仍能查到 `quota_exceeded` | ✅ |
| 幂等 | ➖ N/A（合同禁止精确一次键，允许重复） | ➖ |
| 并发写 | ➖ N/A（追加表无条件更新） | ➖ |
| 外部依赖失败 | `test_gwt_15_2_emit_failure_does_not_block_enqueue` | ✅ |

## 7. NFR 验证（票里有 NFR 时填）

本票无独立 NFR 数字闸。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 查询 `GET /api/v1/product-events` 仅超管；租户 404 `HTTP_404`。公开 `POST /api/v1/public/events`。事件名原样。live MySQL 若 stamp 030 pyc，需 SRE stamp 回 027 再 upgrade 031。 |
| `/frontend` | 官网 beacon 失败吞掉。超管产品事实在 `/platform-ops` Tab「产品事实」。五档 cta 字面量不可改。旁路 `enter_admin` / `try_ai_flow` 不进五档。 |
| `/architect` | 无新错误码。查询过滤 `tenant_id` 空=不按企业过滤。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 本票新增/改动模块自测全绿
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`（吞异常有 warning）
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
