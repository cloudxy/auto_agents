# 实现证据 · T-12 入队信封用户可见禁配额内码（FR-87）

> 票：contract §11 T-12（FR-87）｜FR 锚点：FR-87（GWT-87.1/87.2/87.3）｜角色：/backend｜日期：2026-09-11
> 依据：contract §7.1 错误码表（`QUOTA_EXCEEDED` 禁止渲染）+ §0 合同声明（用户可见 `QUOTA_EXCEEDED`/裸 `429` = 不合格）+ spec X-QUOTA（内部码留异常类型给验收，不得渲给租户）
> 范围闸：不动配额执法本体（`QuotaService.check_task_concurrency` 抛 `QuotaExceededException` 原样）；只做入队超限信封映射 + 只读拒绝句同族化；不动 admin 前端页面结构（读码确认 toast 走 `data.message`，信封改后自动中文，零前端改动）。

## 1. 契约落位表（实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 入队满额信封映射（GWT-87.1） | **Service 入队边界单点** | `backend/services/spider_task_service.py::_check_enqueue_quota` | 捕获 `QuotaExceededException` → `BusinessException(message="已达配额上限，请联系企业管理员。", code="TASK_QUOTA_LIMIT_REACHED")`（HTTP 400，`from exc` 保留因果）。**所有入队入口汇此单点**：`POST /spiders/run`、`POST /spiders/templates/{id}/run`、调度触发（`schedule_service` 经门面）、`SpiderService` 门面——后两者只 catch `BusinessException`（原异常本就是其子类），行为面不变 |
| 用户可见满额句 | 常量（quota 句族旁） | `backend/services/quota_service.py::TASK_QUOTA_FULL_CONTACT_ADMIN` | 与 `PLAN_FULL_USER` 同块；句式=契约 §7.1 字面：「已达配额上限」+「请联系企业管理员」；**没有**「申请提升配额/提交升级申请」支（经办不能下单，GWT-50.8） |
| 只读提交拒绝句（GWT-87.3 后端配合） | 常量（入队域句族旁） | `backend/services/spider_common.py::READONLY_ENQUEUE_MESSAGE` | 「当前账号不能提交采集任务，请联系企业管理员」——与 `NO_TENANT_ENQUEUE_MESSAGE` 同文件同族 |
| 只读入队守卫 | Router 依赖（spiders 域内） | `backend/app/api/v1/spiders/deps.py::require_enqueue_operator` | 与 `require_operator` **同判据**（`role in ("admin","operator")`），仅信封不同：400 + `TASK_RUN_ROLE_NOT_ALLOWED` + 中文句（无 FORBIDDEN 内码）。只挂两个入队端点；模板 CRUD 等仍走 `require_operator`（403 口径不变） |
| 错误码渲染 | 统一异常处理器（不改） | `platform_core/exceptions/handlers.py` | 信封渲染路径未动；映射后的 code/message 经原有 handler 出 |
| 配额执法本体 | **不改** | `backend/services/quota_service.py::check_task_concurrency` | 内部类型/内部码/429/产品事件（`quota_exceeded`）全部原样保留，留给验收 |

**分层依赖核对**：☑ Router 未 import ORM（守卫只依赖 `CurrentUser` 快照 + `BusinessException`） ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import（arch.sh 绿）

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/quota_service.py` | 修改 | +1 用户可见句常量 `TASK_QUOTA_FULL_CONTACT_ADMIN`（含 FR-87 注记） |
| `backend/services/spider_task_service.py` | 修改 | `_check_enqueue_quota` 增信封映射（try/except + `raise ... from exc` + warning 日志）；docstring 注 FR-87/GWT-87.1 |
| `backend/services/spider_common.py` | 修改 | +1 只读拒绝句常量 `READONLY_ENQUEUE_MESSAGE` |
| `backend/app/api/v1/spiders/deps.py` | 修改 | +`require_enqueue_operator` 守卫（GWT-87.3） |
| `backend/app/api/v1/spiders/tasks.py` | 修改 | `POST /run` 守卫 `require_operator` → `require_enqueue_operator`（匿名 401 路径不变：守卫仍叠在 `require_login` 上） |
| `backend/app/api/v1/spiders/templates.py` | 修改 | `POST /templates/{id}/run` 同上（另一入队入口，GWT-87.3 同口径） |
| `backend/tests/test_fr87_enqueue_envelope.py` | 新增 | GWT-87.1/87.2/87.3 三测（HTTP 面 + 可见处断言） |
| `backend/tests/test_saas_wiring.py` | 修改 | **PIT-2 金标改写**：入队满额用例改断言用户可见信封 + 执法本体内部码（直调 `QuotaService` 仍 `QUOTA_EXCEEDED`） |
| `backend/tests/test_t10_api_coverage.py` | 修改 | **PIT-2 金标改写**：`test_run_spider_viewer_403` → 400 中文句版（匿名 401、admin 端点 403 断言原样） |
| `backend/tests/test_b1b_templates_coverage.py` | 修改 | **PIT-2 金标改写**：模板 run viewer 403 → 400 中文句版 |

**与票面范围一致**：☑（信封映射 + 金标同 PR + admin toast 零改动的读码结论都落在本票内）
**未触碰**：`quota_service` 执法三检查、统一异常处理器、`require_operator` 本体、admin/official 前端任何文件、ORM/迁移。**未 git commit**（票禁令）。

## 3. 关键实现决策

- **映射点选在 `_check_enqueue_quota`（Service 入队边界）而非全局异常处理器**：全局映射会波及结果存储/LLM token 两条执法路径的信封（他 FR 面），且 contract §7.1 的错误码机制本身保留；入队单点即 ticket 范围「入队信封」。调度触发路径只 catch `BusinessException`（`schedule_service.py:289`），`QuotaExceededException` 本是其子类——映射前后同一 handler 吃到，调度行为不变。
- **新信封 code 取 `TASK_QUOTA_LIMIT_REACHED` / `TASK_RUN_ROLE_NOT_ALLOWED`**：沿用 T-01 先例（`ORDER_ROLE_NOT_ALLOWED`/`ORDER_ONLINE_UNAVAILABLE`——新造稳定非内码 code，**待 architect 追认**）。两码均不在 X-QUOTA 禁集 `{FORBIDDEN, QUOTA_EXCEEDED, QUOTA_PLAN_LOCKED, HTTP_403, HTTP_429}`，也不含 `QUOTA_EXCEEDED` 子串。
- **满额句不带数字**：契约 §7.1 字面「已达配额上限」+「请联系企业管理员」；原句的 `（active/limit）` 与「申请提升配额」留在内部异常 message（只进日志），不进信封——杜绝 `429` 数字串与「提交升级申请」支的任何渗出面。
- **守卫只挂两个 run 端点**：`require_operator` 全局不动（模板 CRUD/审计/notify 等 403 金标原样）；平台超管 role="admin" 照旧过守卫 → 后续「没有企业身份」400（GWT-09.4 金标不变，全量绿）。
- **admin 前端零改动（读码结论）**：入队 toast 两条路径（`TaskModal.tsx:97`、`TemplateTab.tsx:54`）都走 `apiErrorMessage` → `response.data.message`（`frontend/shared/src/utils/errors.ts:28`），不渲 `code`；信封 message 改中文后 toast 自动显示新句。`Usage.tsx` 已有自身的 X-QUOTA 映射（v2 已兑），Login 页 code 分支仅 AUTH 族——均非入队面，不动。

### 事务/幂等/并发/外部依赖

| 项 | 结论 | 理由 |
|---|---|---|
| 事务 | N/A | 纯信封映射，零新增写操作（拒绝路径在执法点已无副作用） |
| 幂等 | N/A | 无新增写入口 |
| 并发 | N/A | 无写竞争面 |
| 外部依赖 | N/A | 未新增外部调用 |

## 4. ORM 与 DBML 对齐

N/A——零模型/迁移改动。

## 5. 可观测性

映射点新增 `logger.warning`（`入队配额满（信封转用户可见句）| tenant=… | inner_code=…`）；守卫新增 `logger.warning`（user/role）。**脱敏核对**：☑ 无密码 ☑ 无 token ☑ 内部码只进日志（服务端），不进信封。

## 6. 自测证据（原样粘贴）

**红（TDD：实现前）——新增 GWT 三测**：

```
$ uv run pytest -q backend/tests/test_fr87_enqueue_envelope.py
FAILED backend/tests/test_fr87_enqueue_envelope.py::test_gwt_87_1_quota_full_envelope_is_user_visible
FAILED backend/tests/test_fr87_enqueue_envelope.py::test_gwt_87_3_viewer_submit_rejected_user_visible
2 failed, 1 passed in 2.43s
（GWT-87.2 为回归守卫：未满放行行为改前改后一致，红不存在——非空态缺陷）
```

**红（TDD：实现前）——改写后金标（PIT-2）**：

```
$ uv run pytest -q backend/tests/test_saas_wiring.py::test_enqueue_carries_tenant_and_quota_rejects backend/tests/test_t10_api_coverage.py::test_run_spider_viewer_rejected_user_visible
FAILED backend/tests/test_saas_wiring.py::test_enqueue_carries_tenant_and_quota_rejects
FAILED backend/tests/test_t10_api_coverage.py::test_run_spider_viewer_rejected_user_visible
2 failed in 2.10s
exit: 1
```

**绿（实现后）——本票全部相关测试**：

```
$ uv run pytest -q backend/tests/test_fr87_enqueue_envelope.py backend/tests/test_saas_wiring.py::test_enqueue_carries_tenant_and_quota_rejects backend/tests/test_t10_api_coverage.py
25 passed in 4.50s
exit: 0
```

**全量后端**：

```
$ uv run pytest -x -q backend/tests
1414 passed, 37 skipped, 7 warnings in 523.98s (0:08:43)
exit: 0
```

（过程注记：前两轮全量各撞 1 个**他票在途文件**的瞬时态——`relay_service.py` 中途保存致 `NameError`（T-08 域）、`power_market` 种子过滤瞬时失效（T-13/T-19 域）；两者 standalone 均 exit 0，且未改任何一行即在后一轮全量转绿，与本票改动文件零交集。）

**架构红线**：

```
$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0
```

**Lint**：

```
$ uv run ruff check backend platform_core scripts
All checks passed!
exit: 0
```

### 信封前后对照（经真实统一异常处理器渲染，verbatim）

```
/before -> HTTP 429
{"success":false,"code":"QUOTA_EXCEEDED","message":"任务并发已达配额上限（1/1）：请等待运行中任务完成，或申请提升配额","data":{},"request_id":"05a5065c"}

/after -> HTTP 400
{"success":false,"code":"TASK_QUOTA_LIMIT_REACHED","message":"已达配额上限，请联系企业管理员。","data":{},"request_id":"b2acd761"}
```

（before=原 `QuotaExceededException` 走 `app_exception_handler` 的渲染；after=映射后 `BusinessException` 同 handler。admin toast 显示 `message` 字段 → 改后即显示「已达配额上限，请联系企业管理员。」）

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-87.1 满额（经办） | `test_fr87_enqueue_envelope.py::test_gwt_87_1_quota_full_envelope_is_user_visible`（HTTP：中文两句 + 无 QUOTA_EXCEEDED/裸 429 + 无「提交升级」+ 零新任务）；`test_saas_wiring.py::test_enqueue_carries_tenant_and_quota_rejects`（服务层信封 + 执法本体内部码仍 QUOTA_EXCEEDED） | ✅ |
| GWT-87.2 空态（未满） | `test_fr87_enqueue_envelope.py::test_gwt_87_2_under_quota_enqueues_normally`（200 + 无满额句 + 落库 pending，出数环继续） | ✅ |
| GWT-87.3 越权（只读强提交） | `test_fr87_enqueue_envelope.py::test_gwt_87_3_viewer_submit_rejected_user_visible`（真链路 viewer JWT：400 同族中文 + 无内码 + 零落库）；`test_t10_api_coverage.py::test_run_spider_viewer_rejected_user_visible`、`test_b1b_templates_coverage.py::test_run_from_template_viewer_403`（两入口金标） | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（纯拒绝信封，无多步写） | |
| 幂等 | ➖ N/A（无新增写入口） | |
| 并发写 | ➖ N/A（无写竞争面） | |
| 外部依赖失败 | ➖ N/A（未新增外部调用） | |

## 7. NFR 验证

票面无 NFR 指派（NFR-05 越权同形属既有 401/403 口径，本票只换拒绝信封）。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 入队满额与只读拒绝的**信封 code 已换**（`TASK_QUOTA_LIMIT_REACHED`/`TASK_RUN_ROLE_NOT_ALLOWED`，均 HTTP 400）；按 message 分支的旧断言会假绿/假红。执法本体内部码仍 `QUOTA_EXCEEDED`（429）——`test_saas_quota.py` 直调路径未动。调度触发满额只进日志（无用户面）。 |
| `/frontend`（admin） | 零改动即达标：入队 toast 走 `data.message`，自动显示新中文句。T-17/T-18 大改不受本票影响；T-18「拦提交」与本票不同批不冲突（本票只管 API 信封）。 |
| `/architect` | **待追认两个新信封 code**：`TASK_QUOTA_LIMIT_REACHED`（入队满额）、`TASK_RUN_ROLE_NOT_ALLOWED`（只读提交入队）——同 T-01 先例（`ORDER_ROLE_NOT_ALLOWED` 等亦待追认）。§7.1 错误码表可补两行。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（全量 1414 passed / exit 0；arch.sh exit 0；ruff exit 0）
- [x] 契约落位表已核对，分层无违规（守卫在 Router 依赖层，业务句在 Service/常量层）
- [x] ORM 与 DBML 一致（零模型改动）
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用（映射点纯异常转换）
- [x] 无 `except: pass`（捕获后必然 re-raise，`from exc` 保留因果链）
- [x] 日志已脱敏（内部码只进服务端日志）
- [x] 事务里无外部调用（无事务）
- [x] 幂等未用「先查后插」（N/A）
- [x] 条件更新 `rows == 0`（N/A）
- [x] 外部依赖四件套（N/A，未新增外部依赖）
- [x] 四类易漏测试已标 N/A 并给理由
- [x] 发现的上游问题已回报（两个新 code 待 architect 追认，见 §8）
- [x] 票状态：T-12 done（evidence 本文件）
