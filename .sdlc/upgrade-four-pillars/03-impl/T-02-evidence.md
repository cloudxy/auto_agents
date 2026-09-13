# 实现证据 · T-02 空非夹具租户入队、本企业结果、工人空态句

> 票：T-02｜FR 锚点：FR-U01 FR-U02｜角色：/backend｜日期：2026-09-12

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| POST `/api/v1/spiders/run` 3s「已入队」 | Router | `backend/app/api/v1/spiders/tasks.py` | `created(..., message=ENQUEUE_ACCEPTED_COPY)`；HTTP 仍 200/`CREATED` |
| 空结果句「还没有结果，去提交采集」 | Service 常量 + Router | `spider_query_service.EMPTY_DATACENTER_COPY` + `spiders/results.py` | 禁止空白 /「加载失败」装 0 |
| 工人拦住 HTTP 400 +「采集未运行，不会出数」 | Service 闸 | `spider_worker_gate.require_online_worker` | 既有 `SPIDER_WORKER_OFFLINE`；工人闸先于配额 |
| 结果只属本企业；跨企 404 同形 | Service + tenant_scope | `spider_query_service` / 既有隔离 | 0 行、无对方字段、无「抱歉您没有权限」 |
| `task_blocked` / `task_completed` / `task_run_submitted` | Service | `spider_task_service._emit_blocked` / `_emit_completed` / `_emit_submitted` | 快照列走 T-01 `_fixture_snapshot` |
| 错误码映射 | 统一异常处理器 | 既有 `BusinessException` | 工人 `SPIDER_WORKER_OFFLINE`；配额仍 T-03 信封 |
| 幂等 | N/A | — | 拦住不写任务行 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/tests/test_fr_u01_enqueue.py` | 新增 | GWT-U01.1/2/3、U02.1、配额拦住事件 |
| `backend/services/spider_common.py` | 修改 | `ENQUEUE_ACCEPTED_COPY` |
| `backend/app/api/v1/spiders/tasks.py` | 修改 | `/run` 用户句「已入队」 |
| `backend/services/spider_query_service.py` | 修改 | 空结果锁句 |
| `backend/services/spider_task_service.py` | 修改 | `_reject_if_blocked` + `task_blocked` |
| `platform_core/schemas/product_event.py` | 修改 | `WAVE0_EVENT_NAMES` 追加 `task_blocked` |
| `backend/tests/test_spider_datacenter_crud.py` | 修改 | PIT-2：空句常量 |
| `backend/tests/conftest.py` | 修改 | 离线真心跳扫描扩到本票测试文件 |
| `backend/tests/test_ai_planner.py` | 修改 | PIT-2：规划前 token 闸，MagicMock session 不能 await |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：conftest autouse 工人在线桩按 `test_spider_worker_offline.py` 同口径扩到本票文件，否则 U02.1 假绿）

**未触碰「不许改的文件」**：☑ 确认（无 Alipay notify；无中转 SKU；未改 GWT/schema 表）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 入队成功：任务行 + Redis 投递 | 任务行先 commit，再 rpush | 既有；投递失败置 failed |
| 拦住：`task_blocked` | 否（emit 独立短会话） | 主路径不写任务；失败不挡拒绝信封 |

**事务提交后的操作失败怎么办**：产品事件 fail-open（既有 warning）；拦住无提交。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | N/A（每次提交一条任务；拦住零行） |
| 保证方式 | N/A |
| 重复请求返回 | 工人/配额拦住重复提交仍 400，不入队 |

☑ 未使用「先查后插」（本票拦住路径无插入）

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 无新条件更新 | — | 未改 finish/claim |

☐ 所有条件更新的返回行数都有处理（未改状态机 UPDATE）

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| Redis 工人心跳扫描 | 既有 scan | 无 | 扫描失败放行（既有） | N/A |
| Redis 任务队列 | 既有 | 投递失败任务 failed | 拒绝入队 | N/A |

## 4. ORM 与 DBML 对齐

☑ 未自行加字段/改类型 — 夹具快照列与名单表是 T-01；本票只 emit。

结构核对输出：

```
$ 本票无迁移
N/A
```

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `_reject_if_blocked` / `_emit_blocked` / `enqueue` |
| trace_id | 既有中间件 `request_id` |
| 错误日志上下文 | tenant + reason + spider；无密钥 |
| 慢操作耗时 | 入队同步拒绝，NFR-U01 3s 由测试 monotonic 钉 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。

### TDD 红（实现前）

```
$ uv run pytest -x -q backend/tests/test_fr_u01_enqueue.py --tb=short
F
=================================== FAILURES ===================================
_____ test_gwt_u01_1_empty_non_fixture_enqueues_and_results_stay_in_tenant _____
backend/tests/test_fr_u01_enqueue.py:209: in test_gwt_u01_1_empty_non_fixture_enqueues_and_results_stay_in_tenant
    assert ENQUEUED in body["message"]
E   AssertionError: assert '已入队' in '创建成功'
=========================== short test summary info ============================
FAILED backend/tests/test_fr_u01_enqueue.py::test_gwt_u01_1_empty_non_fixture_enqueues_and_results_stay_in_tenant
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 2.18s
exit: 1
```

### 绿

```
$ uv run pytest -q backend/tests/test_fr_u01_enqueue.py --tb=short
.....                                                                    [100%]
5 passed in 3.02s
exit: 0

$ uv run pytest -q backend/tests/test_fr_u01_enqueue.py backend/tests/test_fr_u02_quota_copy.py backend/tests/test_spider_worker_offline.py backend/tests/test_t01_internal_fixture.py backend/tests/test_fr87_enqueue_envelope.py backend/tests/test_t38_platform_tenant_enqueue.py backend/tests/test_product_events.py backend/tests/test_spider_datacenter_crud.py backend/tests/test_spider_zero_items.py backend/tests/test_spider_min_loop.py --tb=line
........................................................................ [ 66%]
.....................................                                    [100%]
109 passed in 19.20s
exit: 0

$ uv run pytest -q backend/tests/test_saas_wiring.py backend/tests/test_spider_task_flow.py --tb=line
.................................................                        [100%]
49 passed in 4.45s
exit: 0

$ uv run pytest -q backend/tests --tb=line
1570 passed, 39 skipped, 7 warnings in 224.47s (0:03:44)
exit: 0

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0

$ uv run python PLUGIN_ROOT/skills/impl-evidence/scripts/check-layering.py backend/app/api/v1/spiders/tasks.py backend/app/api/v1/spiders/results.py backend/services/spider_task_service.py backend/services/spider_query_service.py
✓ 分层依赖检查通过
exit: 0

$ uv run ruff check backend/tests/test_fr_u01_enqueue.py backend/services/spider_task_service.py backend/services/spider_query_service.py backend/services/spider_common.py backend/app/api/v1/spiders/tasks.py platform_core/schemas/product_event.py backend/tests/conftest.py backend/tests/test_spider_datacenter_crud.py
All checks passed!
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-U01.1 空非夹具入队+本企业出数 | `test_gwt_u01_1_empty_non_fixture_enqueues_and_results_stay_in_tenant` | ✅ 3s「已入队」；回流后条数>0 只在 A；`task_completed` 且 `is_internal_fixture=false` |
| GWT-U01.2 空结果 | `test_gwt_u01_2_empty_results_copy_is_actionable` | ✅ |
| GWT-U01.3 跨企 | `test_gwt_u01_3_cross_tenant_result_same_as_missing` | ✅ 404 同形，无 A 字段 |
| GWT-U02.1 无工人 | `test_gwt_u02_1_worker_offline_blocks_within_3s_and_emits_task_blocked` | ✅ 3s 工人句；零任务；`task_blocked.reason=worker_offline` |
| 拦住 vs 完成（供 T-05） | `test_storage_full_emits_task_blocked_not_completed` | ✅ `quota_storage`；无 `result_count>0` 的 completed |
| GWT-U02.2…U02.7 | T-03 `test_fr_u02_quota_copy.py` 回归 | ✅ 本票未改配额句 |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | 拦住不写任务行（U02.1 / 存储满） | ✅ 零新任务；事件独立短会话 |
| 幂等 | 拦住重复提交仍拒绝 | ➖ N/A（无写单；重复拦住不入队） |
| 并发写 | — | ➖ N/A（本票无新建支付单/无条件 UPDATE） |
| 外部依赖失败 | Redis 心跳扫描失败放行（既有）；投递失败既有 failed | ➖ N/A（本票未改降级语义） |

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-U01 | 提交 3s 内见「已入队」或工人拦住句 | pytest monotonic ≤3s | SQLite + FakeRedis |
| NFR-U07 | 不破坏夹具出数环 | `test_spider_min_loop.py` 随回归绿 | 同上 |
| NFR-U08 | 拦住 vs 完成可区分 | `task_blocked` ≠ `task_completed` 且 count>0 | 同上 |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | `/run` 成功 message=`已入队`（code 仍 `CREATED`）。空列表 message=`还没有结果，去提交采集`。工人拦住仍 400/`SPIDER_WORKER_OFFLINE`。`task_blocked.props.reason` ∈ `worker_offline`/`quota_storage`/`quota_concurrency`（token 满规划仍走 T-03 `quota_exceeded`，入队不查 token）。查询面仅超管。 |
| `/frontend`（T-04） | 入队 Toast 用响应 `message`「已入队」。数据中心空态以后端 message 为准（现网 Data.tsx 仍是旧句，属 T-04）。工人句不变。 |
| `/architect` | `/run` 未改 HTTP 201；仍 200 + `CREATED` + 新 message。`WAVE0_EVENT_NAMES` 追加 `task_blocked`，未新造错误码。 |
| T-05 | 入队拦住已 emit `task_blocked`（含 `is_internal_fixture` 快照）；完成仍 `task_completed`。autouse `_workers_online_unless_offline_node` 对本票测试文件跳过。 |

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
- [x] 条件更新的 `rows == 0` 已处理（未改 claim）
- [x] 外部依赖四件套齐全或 N/A
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 票证据已落盘
