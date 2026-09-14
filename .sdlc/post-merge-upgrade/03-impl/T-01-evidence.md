# 实现证据 · T-01 智能规划未开放

> 票：T-01｜FR 锚点：FR-M01｜角色：/backend｜日期：2026-09-13

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| `POST /api/v1/ai/plans` 422 | Router + Service | `backend/app/api/v1/ai.py` · `orchestrator.py` | 未开放不建 draft |
| `POST /api/v1/ai/plans/{id}/plan` 422 | Service | `orchestrator.launch_plan` | 闸在 claim 之前 |
| 用户句「智能规划未开放」 | Service | `PLANNING_DISABLED_COPY` | code=`PLANNING_DISABLED` HTTP 422 |
| 只读拒绝句 | Router 守卫 | `require_planning_operator` | 「当前账号不能开始规划」；无 FORBIDDEN |
| GET 列表空态句 | Router | `list_plans` message | 与提交同一句 |
| 业务规则：不抢 planning、不入队 | Service | `_reject_if_planning_disabled` | 先于 token 配额闸 |
| 错误码映射 | 统一异常处理器 | `BusinessException` | 不在 Router try/except |
| 幂等 | N/A | | 拒绝写路径 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/ai_planner/llm_client.py` | 修改 | 金标句 + code；ENABLED=false 不再长说明 |
| `backend/services/ai_planner/orchestrator.py` | 修改 | 创建/触发前闸；不 claim |
| `backend/services/ai_planner/__init__.py` | 修改 | 导出 copy / `planning_is_open` |
| `backend/app/api/v1/ai.py` | 修改 | 只读守卫；列表 message |
| `backend/tests/test_fr_m01_planning_disabled.py` | 新增 | GWT-M01.1/2/3 |
| `backend/tests/test_ai_planner.py` | 修改 | 单测桩闸；LLM 关闭句 |
| `backend/tests/test_fr_u02_quota_copy.py` | 修改 | U02.4 Given=规划已开放 |
| `backend/tests/test_llm_four_actions_http.py` | 修改 | 夹具开 LLM.ENABLED |
| `backend/tests/test_fr73_byok_four_actions_http.py` | 修改 | 同上 |
| `backend/tests/test_t38_platform_tenant_enqueue.py` | 修改 | 建方案时开旗 |

**与票里「会改哪些文件」一致**：☑ 有偏差（PIT-2 同 PR 改规划测夹具，使 U02.4/四动作 Given 含「规划已开放」）

**未触碰「不许改的文件」**：☑ 确认（未改 GWT / 未开工 W2）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 未开放拒绝 | 否 | 零业务写；事件独立短会话（失败不挡） |

**事务提交后的操作失败怎么办**：事件失败只记 warning（GWT-M06.3）

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | N/A（拒绝路径无写） |
| 保证方式 | 不 insert / 不 claim |
| 重复请求返回 | 422 同一句 |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 未开放 | 不进入 claim_status | N/A |

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| LLM / 网关 | 不调用 | — | 本地开关拒绝 | — |

## 4. ORM 与 DBML 对齐

☑ 未自行加字段/改类型（只用既有 `ai_plans`）

结构核对输出：本票无 DDL。

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `_reject_if_planning_disabled` `规划开放闸 \| tenant=` |
| 错误日志上下文 | tenant_id；无 token |
| 事件 | `llm_planning_blocked` props.reason=disabled（T-04） |

**日志脱敏核对**：☑ 无密码 ☑ 无 token

## 6. 自测证据

### Red（TDD，实现前）

```
$ uv run pytest -x -q backend/tests/test_fr_m01_planning_disabled.py --tb=short
F
____________ test_gwt_m01_1_submit_disabled_copy_no_plan_no_enqueue ____________
E   AssertionError: {"success":true,"code":"CREATED",... "status":"draft"...}
E   assert 200 == 422
FAILED backend/tests/test_fr_m01_planning_disabled.py::test_gwt_m01_1_submit_disabled_copy_no_plan_no_enqueue
1 failed in 2.07s
exit: 1
```

Oracle：未开放仍 200 建 draft，不是 422「智能规划未开放」。

### Green

```
$ uv run pytest -q backend/tests/test_fr_m01_planning_disabled.py \
    backend/tests/test_fr_m03_first_collect.py \
    backend/tests/test_fr_m06_planning_export_events.py \
    backend/tests/test_fr_m51_signup_enterprise.py
...............                                                          [100%]
15 passed in 4.73s
exit: 0

$ uv run pytest -x -q backend/tests
1786 passed, 41 skipped, 9 warnings in 205.78s (0:03:25)
exit: 0

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-M01.1 提交 | `test_gwt_m01_1_submit_disabled_copy_no_plan_no_enqueue` · `test_gwt_m01_1_trigger_does_not_claim_planning` | ✅ |
| GWT-M01.2 空态 | `test_gwt_m01_2_open_empty_shows_disabled_copy` | ✅ |
| GWT-M01.3 越权 | `test_gwt_m01_3_viewer_submit_rejected` | ✅ |
| GWT-M01.4/5 | 本票不施工（规划已开放成功/74.1） | ➖ 留给对照 FR-70 |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | 未开放零写 | ➖ N/A（无多步写） |
| 幂等 | 重复提交仍 422 不建行 | ✅ 含在 M01.1 |
| 并发写 | 不进入 claim | ➖ N/A |
| 外部依赖失败 | 不打 LLM | ➖ N/A |

## 7. NFR 验证

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-M01 | 未开放 3s 内金标句 | 测试内 elapsed ≤ 3 | pytest SQLite |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 开关=`LLM.ENABLED`。未开放时 POST 创建与触发都是 422 `PLANNING_DISABLED`。只读 400 `PLANNING_ROLE_NOT_ALLOWED`（禁止把 FORBIDDEN 渲给租户）。GET 列表 message 同句。 |
| `/frontend` | 打开/提交同一句「智能规划未开放」。主操作去采集任务（壳侧）。不要用「还没有规划」。 |
| `/architect` | 无新码歧义。 |

## 9. 交票自检

- [x] 每条本票验收项有 evidence
- [x] 自测全绿（全量 1786 passed）
- [x] 分层无违规（arch.sh 0）
- [x] 未自行加字段
- [x] 无硬编码连接串
- [x] async 无同步 redis 直调
- [x] 日志已脱敏
- [x] 发现的上游问题已回报：只读 HTTP 用 400 而非 403，避免 FORBIDDEN
