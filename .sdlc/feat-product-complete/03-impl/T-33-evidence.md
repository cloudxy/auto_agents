# 实现证据 · T-33 立即探测手动入口 + 事件跳转聚焦

> 票：contract §11 T-33｜FR 锚点：FR-98（GWT-98.4 / 98.7）｜角色：/frontend（admin）+ 后端最小触发端点（packet 明示允许：lane ui 为主、后端一小口）｜日期：2026-09-11
> 依赖：T-31；与 T-32 同文件（NewApiOps.tsx 及子件）串行，本票在 T-32 之后施工。

## 1. 契约落位表（实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 触发端点 `POST /newapi/probe` | Router | `backend/app/api/v1/newapi.py` | 静态段、置于既有动态段前无冲突；触发即返回 `accepted`+`batch_id`，不阻塞轮询循环 |
| 请求/响应契约 | Schema | `platform_core/schemas/newapi.py` | `ProbeTriggerRequest`（gateway_ref min_length=1）/ `ProbeTriggerResponse`（accepted/gateway_ref/batch_id/reason） |
| 探测执行（引擎复用，不重做） | Service | `backend/services/channel_probe_service.py` | `trigger_manual_probe` → 复用 `_list_mapped` 定位目标 + `_probe_channel(target, ref_results=None, …)`（无参考对比口径与批次路径一致）；**不抢 `NEWAPI_PROBE_LOCK_KEY`**，与轮询互不阻塞 |
| 越权（GWT-98.7） | Router 守卫 | `backend/app/api/v1/newapi.py` | `require_platform_admin_or_404`（GWT-61.3 同形）；守卫在 handler 前失败 → 零渠道/事件副作用（测试断言引擎未被调用） |
| 审计 | Router | 同上 | `record_audit("newapi.probe.trigger", gateway:{ref}, {accepted, batch_id})`，与既有 POST 端点同款 |
| 前端触发入口（GWT-98.4） | 组件 | `frontend/admin/src/components/newapi/OverviewChannels.tsx` | 仅总览每渠道行「立即探测」；行内「探测中…」+ 按钮加载态；网关降级的仅本地探针行（无 gatewayRef）按钮禁用；探针 tab 无第二入口 |
| 完成后行内更新 | 组件 | `frontend/admin/src/components/newapi/Overview3q.tsx` | accepted 后按 `batch_id` 条件轮询探针切片（react-query `refetchInterval` 3s，无手写定时器）；拉到本批次行 → 清在飞 + 行内判定/延迟随数据更新 |
| 事件跳转聚焦（GWT-98.5） | 组件 | `Overview3q.tsx` + `EventsList.tsx` | Top N 行点击（含 Enter）→ `onTabChange('events')` + `highlightId` 高亮（T-32 侧同一机制，本票联测） |
| 服务封装 | Service(fe) | `frontend/admin/src/services/newapi.ts` | `triggerNewapiProbe`（信封只解一层） |

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/app/api/v1/newapi.py` | 修改 | +`POST /probe` 端点（+守卫/审计/文档串），229 行 |
| `platform_core/schemas/newapi.py` | 修改 | +`ProbeTriggerRequest/ProbeTriggerResponse` |
| `backend/services/channel_probe_service.py` | 修改 | +`trigger_manual_probe`/`_run_manual_probe` + `_MANUAL_INFLIGHT`（模块级在飞登记），377 行 |
| `backend/tests/test_t33_probe_trigger.py` | 新增 | API 守卫/受理/未受理/422 + 服务面 2 用例 |
| `frontend/admin/src/services/newapi.ts` | 修改 | +`triggerNewapiProbe`/`ProbeTriggerResult` |
| `frontend/admin/src/components/newapi/OverviewChannels.tsx` | 修改 | 操作列「立即探测」按钮（探测中态） |
| `frontend/admin/src/components/newapi/Overview3q.tsx` | 修改 | 触发/在飞批次/完成检测 + 条件轮询 |
| `frontend/admin/src/components/newapi/EventsList.tsx` | 修改 | +可选 `highlightId`（既有列表不动） |
| `frontend/admin/src/pages/NewApiOps.test.tsx` | 修改 | +立即探测/跳转用例 |

与票表一致（api+ui 双面；后端只加最小触发口，未动探针引擎/轮询/数据面）。未触碰「不许改的文件」：确认。

## 3. 关键实现决策

- **后端口最小化**：不新增锁（手动探测不抢 `NEWAPI_PROBE_LOCK_KEY`，与轮询循环互不阻塞）；同 ref 在飞 → 复用同一 `manual-` 批次 id（不重复 spawn）；目标不在网关列表/网关不可达 → `accepted=false` + 中文原因（200，不 500）；空白 ref 在 Schema（422）与服务（短路于任何网关 IO）双层拒绝。
- **引擎复用不重做**：探测执行走既有 `_probe_channel`（含 spoofed 通知、`_channel_id_from_ref`、落库隔离），`ref_results=None` 与「本批无参考对比」口径一致。
- **前端不阻塞**：行级在飞状态（`probingBatches`）+ `refetchInterval: 有在飞 ? 3000 : false` 的条件轮询；探测中其他区/配置/跳转全部可用；完成提示后按钮复原。
- **守卫选型**：按 spec GWT-98.7 钉「与页面不存在同形」，用 `require_platform_admin_or_404`（既有 GET 同款），非 `require_platform_admin` 的 403 信封。

## 4. 数据契约核对

- 新增端点为动作触发（无表/列/迁移改动）；`alembic` 头不动。
- API 层未 import ORM（R7）；Service 未返回 ORM 对象；密码/Token 不入日志与审计（审计载荷仅 accepted/batch_id）。
- 与 DBML 对齐：N/A（无新字段；给 /dba 的诉求为零）。

## 5. 自测证据（命令 + 退出码原样）

```
$ cd /Users/xuyun/auto_agents && uv run pytest -x -q backend/tests/test_t33_probe_trigger.py
......                                                                   [100%]
6 passed in 1.30s
exit: 0

$ cd /Users/xuyun/auto_agents && uv run pytest -x -q backend/tests/test_newapi_api.py backend/tests/test_newapi_services.py backend/tests/test_llm_probe.py
54 passed, 23 skipped in 1.89s
exit: 0

$ cd /Users/xuyun/auto_agents && uv run pytest -x -q backend/tests
1473 passed, 37 skipped in 145.59s (0:02:25)
exit: 0

$ cd /Users/xuyun/auto_agents && bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0

$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npm test -- --watchAll=false --maxWorkers=2
Test Suites: 25 passed, 25 total
Tests:       149 passed, 149 total
Time:        420.012 s
exit: 0

$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/admin
Compiled with warnings.   # 仅存量五文件，本次新增文件零警告
exit: 0

$ bash tools/check/frontend.sh
✓ 前端工程门禁通过
exit: 0
```

注：满载并行下曾观察到一次 jest worker 偶发失败（非断言）；改用「页面刷新即时取回批次行」替代真实 3s 轮询等待后，定向与全量连续两轮全绿（上述输出为最终轮原样）。

## 6. 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-98.4 立即探测（页上可见进行中 + 完成行内更新） | `NewApiOps.test.tsx` `GWT-98.4 manual probe: in-flight row state, then verdict/latency update from this round`（触发参数/探测中…/其他区不受锁/伪装+333ms 更新/按钮复原） | ✅ |
| GWT-98.7 越权（404 同形、零副作用） | `test_t33_probe_trigger.py` `test_operator_trigger_is_404_shape_without_side_effects`（404 同形 + 引擎未调用） | ✅ |
| 受理面（触发即返回） | `test_platform_admin_trigger_returns_accepted_batch` / `test_target_missing_returns_not_accepted_with_reason` / `test_blank_ref_rejected_by_schema` | ✅ |
| 引擎复用 + 在飞复用 | `test_trigger_manual_probe_reuses_engine_and_inflight_batch`（`_probe_channel(ref_results=None)` + 同批次 id）/ `test_trigger_manual_probe_blank_ref_short_circuits` | ✅ |
| GWT-98.5 事件跳转（本票联测） | `NewApiOps.test.tsx` `GWT-98.5 clicking a top event row switches to the events tab and highlights the row` | ✅ |

## 7. 给下游的信息

| 给谁 | 内容 |
|---|---|
| /qa | 手动探测批次 id 前缀 `manual-`；探针 tab 列表能看到手动行（与轮询行同表同构）；探测中若离开总览再回来，在飞状态在内存（不跨页持久）——验收按同屏会话口径。 |
| /qa | GWT-98.4 真机验收：点击后行内「探测中…」，完成依赖轮询（≤3s+探针耗时）；组件测试用「刷新」同路径取数避免满载超时（见 §5 注）。 |
| /backend | 在飞登记 `_MANUAL_INFLIGHT` 为进程内存——多 worker 部署下同渠道不同进程可各触发一次（探针幂等落库、无副作用冲突）；如需全局去重可换 Redis SETNX，本票未做（最小口）。 |
| /architect | 无契约歧义新增；`ProbeTriggerResponse.reason` 为用户可见中文（前端直出），与「入队满额中文句」同族处理。 |

## 8. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（后端全量 1473 passed；admin 全量 25 套件/149 测；构建/双门禁 0）
- [x] 分层核对（Router 无 ORM import；Service 无 ORM 返回；`scripts/check-layering` 面 = arch.sh 0 违规覆盖）
- [x] 未自行加表/字段（schema 仅请求响应模型，无迁移）
- [x] 无硬编码连接串/密钥/端口；async 上下文无同步阻塞；无 `except: pass`（后台任务失败 logger.error）
- [x] 日志/审计脱敏（无 Key/Token）
- [x] 四类易漏测试：事务回滚 N/A（单表追加写）；幂等=在飞批次复用（✅ 服务面用例）；并发写 N/A（探针结果追加表 + 进程内去重）；外部依赖失败=网关列表不可达 accepted=false（✅）
- [x] .py ≤500 行（最大 377）；.tsx ≤400 行（最大 323）；未 git commit（按 packet 禁令）
