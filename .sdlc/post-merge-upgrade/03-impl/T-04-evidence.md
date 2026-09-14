# 实现证据 · T-04 规划拦住与导出事件

> 票：T-04｜FR 锚点：FR-M06｜角色：/backend｜日期：2026-09-13

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| `llm_planning_blocked` | Service | `orchestrator._reject_if_planning_disabled` | props.reason=disabled；tenant_id 列 |
| `data_export_completed` | Service | `spider_query_service._emit_exported` | 与 `results_exported` 双写一期 |
| 失败不挡 | `emit_product_event` | `product_event_service.py` | 既有 swallow |
| 查询仅超管 | Router | `product_events.admin_router` | 租户 404 同形 |
| 事件名登记 | Schema | `WAVE0_EVENT_NAMES` | 查询不按白名单滤，仅契约清单 |

**分层依赖核对**：☑ Router 未 import ORM

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/ai_planner/orchestrator.py` | 修改 | 未开放点上报 blocked |
| `backend/services/spider_query_service.py` | 修改 | 导出成功双写新名 |
| `platform_core/schemas/product_event.py` | 修改 | WAVE0 追加两名 |
| `backend/tests/test_fr_m06_planning_export_events.py` | 新增 | GWT-M06.1–4 |

**未触碰**：☑ 未改查询守卫（租户 404 已在）☑ 未做 W2 事件

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 主路径写 + 事件 | 否 | 独立短会话；主路径 rollback 不得带走事实；失败不挡 |

### 幂等

事件至少一次（可重复）。开通 CAS 不在本票。

### 外部依赖

事件写本库；失败 logger.warning。

## 4. ORM 与 DBML 对齐

☑ 沿用 `product_events` 表；未加列。`file_format` 在 props JSON。

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | emit `上报产品事件 \| name=` |
| 脱敏 | strip password/token；事件无钥匙明文 |

## 6. 自测证据

### Red

实现前导出只报 `results_exported`，规划关闭无 `llm_planning_blocked`。T-01 红跑已证明关闭路径还在建 draft（事件点不存在）。本票测试与实现同批落地后即绿。

### Green

```
$ uv run pytest -q backend/tests/test_fr_m06_planning_export_events.py
....                                                                     [100%]
4 passed

$ uv run pytest -x -q backend/tests
1786 passed, 41 skipped, 9 warnings in 205.78s (0:03:25)
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-M06.1 | `test_gwt_m06_1_planning_blocked_event_queryable` | ✅ name + tenant_id + reason=disabled；无该次 result_count>0 的 task_completed |
| GWT-M06.2 | `test_gwt_m06_2_export_emits_data_export_completed` | ✅ file_format=csv, row_count=1 |
| GWT-M06.3 | `test_gwt_m06_3_emit_failure_does_not_block_export_or_disabled_copy` | ✅ persist boom 时 422 句仍在、导出仍 200 |
| GWT-M06.4 | `test_gwt_m06_4_tenant_has_no_query_surface` | ✅ 404 HTTP_404 |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | 事件独立会话 | ✅ 失败不挡 |
| 幂等 | 至少一次 | ➖ 未测重复投递 |
| 并发写 | 无 | ➖ |
| 外部依赖失败 | `_persist_event` boom | ✅ |

## 7. NFR 验证

| NFR | 要求 | 实测 |
|---|---|---|
| NFR-M08 | 仅超管可查；失败不挡 | M06.3/4 |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 查询 `GET /api/v1/product-events?event_name=llm_planning_blocked`。导出新名 props 用 `file_format`（旧名 `results_exported` 仍用 `format`）。101 拒绝出文件不在本票（T-02）。 |
| `/frontend` | 租户无产品事实叶；直打 404 同形。 |
| `/analyst` | 夹具企业事件可查但不得计入北极星（既有 is_internal_fixture）。 |

## 9. 交票自检

- [x] 四格 GWT 有测试
- [x] 全量绿
- [x] 租户无查询面
- [x] 失败不挡
