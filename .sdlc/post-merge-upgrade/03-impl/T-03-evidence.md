# 实现证据 · T-03 第一次采集无付费墙

> 票：T-03｜FR 锚点：FR-M03｜角色：/backend｜日期：2026-09-13

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| `POST /api/v1/spiders/run` | Router | `spiders/tasks.py` | 已入队 copy |
| 无付费/订阅/中转前置 | Service | `spider_task_service.enqueue` | 只工人闸+三类配额 |
| 只读拒绝 | Router 守卫 | `require_enqueue_operator` | 「当前账号不能提交采集…」 |
| 租户过滤 | Service + Mixin | R13 | 结果只本企业 |

**分层依赖核对**：☑ Router 未 import ORM ☑ 本票无新分层

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/tests/test_fr_m03_first_collect.py` | 新增 | GWT-M03.1/2/3 对照 |

**与票一致**：☑ 产品入队路径已满足 FR-M03（无付费墙）；本票补可回归测试，未改 enqueue 本体。

**未触碰**：☑ 未开工 W2 checkout；未改 Scrapy。

## 3. 关键实现决策

入队前置仍是：在线工人 → 并发/存储配额 → 注册表。**没有**订单/订阅/SKU 闸。免费空企业即可 200「已入队」。

北极星 GWT-M03.1 的 120s completed：pytest 用 FakeRedis 心跳 + ingest flush + webhook（与 FR-U01 同缝）。**C4 真 Scrapy 工人是环境闸**，本套件不假装 live worker。

### 事务 / 幂等 / 并发

入队既有路径；本票无新写模型。

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| Redis 队列 | 既有 | 既有 | 工人离线句 | 任务 id |

## 4. ORM 与 DBML 对齐

☑ 未改表。

## 5. 可观测性

沿用 `task_run_submitted` / `task_completed`（非本票新名）。

## 6. 自测证据

### Red

入队路径读码已无付费墙。本票测试是**对照/表征**：写成后即绿，没有「先红的产品缺陷」。TDD 红在 T-01/T-24/T-04 的新闸与新事件。

### Green

```
$ uv run pytest -q backend/tests/test_fr_m03_first_collect.py
...                                                                      [100%]
3 passed

$ uv run pytest -x -q backend/tests
1786 passed, 41 skipped, 9 warnings in 205.78s (0:03:25)
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-M03.1 | `test_gwt_m03_1_empty_free_non_fixture_enqueues_without_paywall` | ✅ 3s 已入队；本企业结果；断言无安装行/无 active SKU/无已开通单。完成态=ingest+webhook，非 live worker |
| GWT-M03.2 | `test_gwt_m03_2_task_list_has_no_paywall_copy` | ✅ 无「请先开通专业档」「请先订阅能力」 |
| GWT-M03.3 | `test_gwt_m03_3_viewer_submit_rejected_no_enqueue` | ✅ 拒绝不入队。HTTP **400** `TASK_RUN_ROLE_NOT_ALLOWED`（不是 403 FORBIDDEN） |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | 只读零写 | ➖ N/A |
| 幂等 | 本票不改入队幂等 | ➖ 既有 |
| 并发写 | 无 | ➖ |
| 外部依赖失败 | 工人离线仍走 FR-U02 | ➖ 对照票 |

## 7. NFR 验证

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-M01 入队 3s | 已入队或拦住 | elapsed ≤ 3 | pytest + FakeRedis |
| C4 真工人 120s | 环境闸 | **跳过 live worker** | 见 §8 |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` `/sre` | 北极星 120s 出数需 C4 真工人。本证据只保证 API 入队无付费墙 + 本进程 ingest 出数。 |
| `/frontend` | 采集任务空表不得画付费/订阅前置。只读句沿用「当前账号不能提交采集任务…」。 |
| `/architect` | 包描述「viewer 403」与现网 400 信封冲突；本票保持 FR-87 400，避免用户可见 FORBIDDEN。 |

## 9. 交票自检

- [x] GWT-M03 三条有测试
- [x] 全量 pytest 0
- [x] 未改 GWT / 未接支付
- [x] C4 跳过写清楚
