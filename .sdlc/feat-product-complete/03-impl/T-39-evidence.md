# 实现证据 · T-39 采集方案定义字段可编辑 + 可删除

> 票：contract §11 / spec FR-103（GWT-103.1…103.5 后端半）｜角色：/backend｜日期：2026-09-11

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| PATCH `/spiders/definitions/{name}/meta`（元信息+定义参数） | Router | `backend/app/api/v1/spiders/definitions.py` | 守卫 require_admin → **require_operator**（GWT-103.1 Given=经办；contract §9 租户经办行） |
| DELETE `/spiders/definitions/{name}` | Router | 同上 | 守卫同步放开到经办（GWT-103.2 Given=经办）；create/启停保持 require_admin（票面未要求） |
| 定义参数字段（params dict / URL 形态 / 字段集） | Schema | `platform_core/schemas/spider.py` | `DefinitionUpdateMetaRequest.params`；响应 `SpiderDefinitionResponse.params`、注册表 `SpiderInfo.params`（编辑回显 + 任务表单预填） |
| 类型分派（api/flow/代码型）+ 引用检查 + 越权数据范围 | **Service** | `backend/services/spider_registry_service.py` | `_resolve_definition_params` 三支分派；代码型拒绝句 |
| flow 型流程字段落注册来源计划 | Service | 同上 `_flow_definition_params` | 局部 import 断开 ai_planner→spider_service→registry 的 import 环（同 `create_task_from_template` 先例） |
| 后续任务取新定义（enqueue 默认参数） | Service | `backend/services/spider_task_service.py` | `_definition_default_params`：显式 params 优先，缺省填定义参数（放在 flow 段识别之前，flow 镜像参数可参与 flow_generic 归并） |
| 数据读写 | Repository | `backend/repositories/ai_plan_repository.py`（`get_by_registered_definition`：`plan_json["registered_definition"].as_string()` JSON 路径反查，id 最新优先）；`spider_task_repository.py`（`list_ids_by_spider`：删除拒绝句列举引用任务） | |
| 错误码映射 | 统一异常处理器 | BusinessException/NotFoundException → 400/404 信封（既有） | 跨企业直打 = 404 同形（R13 tenant_scope 行级过滤，B 的方案不变） |
| 定义参数存储 | 迁移 044（expand-only） | `backend/alembic/versions/044_t39_spider_definition_params.py` | `spider_definitions.params` JSON NULL；模型同步 `platform_core/models/spider_definition.py` |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象（响应均经 Pydantic `model_validate`）☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `platform_core/models/spider_definition.py` | 修改 | +`params` JSON 列 |
| `backend/alembic/versions/044_t39_spider_definition_params.py` | 新增 | 加列迁移（down=drop column；单一 head 044） |
| `platform_core/schemas/spider.py` | 修改 | `DefinitionUpdateMetaRequest.params` / `SpiderDefinitionResponse.params` / `SpiderInfo.params` |
| `backend/repositories/ai_plan_repository.py` | 修改 | +`get_by_registered_definition` |
| `backend/repositories/spider_task_repository.py` | 修改 | +`list_ids_by_spider` |
| `backend/services/spider_registry_service.py` | 修改 | `update_definition_meta` 扩容 + 类型分派辅助；`delete_definition` 拒绝句列举任务；`registry()` 透出 params |
| `backend/services/spider_task_service.py` | 修改 | enqueue 缺省 params 填定义参数 |
| `backend/app/api/v1/spiders/definitions.py` | 修改 | meta/delete 守卫 require_operator + 文档串 |
| `backend/tests/test_t39_definition_edit_delete.py` | 新增 | 24 测试（红绿见 §6） |
| `backend/tests/test_b1c_spiders_registry_results_coverage.py` | 修改 | operator 403 钉随 GWT 放开改写为 operator_ok + viewer_403（T-37 同款先例：GWT Then 只锁「拒绝」，经办语义由 FR-103/contract §9 给定） |
| `backend/tests/test_spider_datacenter_crud.py` | 修改 | 删除拒绝断言升级（#id 列举）+ 定义桩补 `params=None` |
| `backend/tests/test_spider_files_management.py` / `test_spider_generic_spider.py` | 修改 | 定义桩补 `params=None`（新列的 mock 桩对齐） |

**与票里「会改哪些文件」一致**：☑ 是（票面未列文件清单，按分层落位）。
**未触碰「不许改的文件」**：☑ 确认（未做 T-40 UI、未做 T-41 视图纯净；未改名称/类型可改性）。

## 3. 关键实现决策

### 编辑面（按资产类型最小集，packet 钦定）

| 类型 | 可编辑定义要素 | 存储 | 后续任务生效路径 |
|---|---|---|---|
| api | `urls`（入口地址）+ `headers`（字段集 = yml `SPIDER_TYPES.api.fields` 的 name 集合，运行时读配置，缺省回退 urls/headers） | `spider_definitions.params` | enqueue 未带 params 时填定义参数（显式 params 优先=任务级覆盖） |
| flow | 流程字段（selectors/pagination/detail/filters/render_js 等，FlowConfig 契约校验）+ 入口地址（urls[0]→target_url） | `ai_plans.plan_json["flow"]` + `generated_params` 再生；**镜像**到 `spider_definitions.params` | 后续试采取再生后的 generated_params；enqueue 缺省走镜像 |
| 代码型（web/custom） | 仅元信息（title/description，既有行为不回退） | params 编辑拒绝，可见句含「代码型爬虫请在源码中修改」 | — |

- 名称/类型不可改：保持（请求 schema 无 name/type 字段，服务层只取 title/description/params）。
- 编辑校验：字段类型（urls 非空字符串列表 / headers 字符串键值 dict）+ URL 形态（urlparse scheme ∈ http/https 且有 netloc）；flow 走 FlowConfig（选择器表达式/翻页上限等既有校验全量复用）。
- 在跑任务不受影响：任务 params 在 enqueue 时快照入 `spider_tasks.params`，编辑只写定义/计划行，无回写路径（测试钉住：编辑后存量 running 任务 params/status 不变）。

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| flow 编辑：计划行（plan_json/generated_params/target_url）+ 定义行（镜像 params） | 是 | 两行一致性（镜像与来源计划同 commit，单次 `session.commit()`；`plan.id` commit 前捕获，P-BE-01） |
| api 编辑：定义行 | 是（单行） | |
| 审计（record_audit） | 否 | 既有独立短事务口径（P1-11） |

**事务提交后的操作失败怎么办**：无事务后外部调用（enqueue 投递路径未改）。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | N/A（编辑=last-write-wins 局部更新；删除=既有原子条件删） |
| 保证方式 | 删除沿用 `delete_if_unreferenced`（DELETE ... NOT EXISTS 单语句原子判定，m1 TOCTOU 防护既有） |
| 重复请求返回 | 编辑重复=同值再写（200）；删除重复=404 |

☑ 未使用「先查后插」（无插入路径）。

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 删除被引用 | 既有原子条件 DELETE | rowcount=0 → 二次查询区分 NotFound（404）与被引用（400 中文句，含 count + 至多 5 个 `#task_id`） |
| flow 编辑 vs 并发试采 | last-write-wins | 计划行 update 整体覆盖；任务 params 已快照不受影响（GWT-103.3 编辑半） |

☑ 所有条件更新的返回行数都有处理。

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| N/A（本票无新增外部调用） | — | — | enqueue 定义参数读取失败=记日志跳过填充（与 `_ensure_spider_available` 同口径，DB 故障不阻断入队主流程） | — |

## 4. ORM 与 DBML 对齐

- 本票 schema 变更 = `spider_definitions.params` JSON NULL（expand-only，迁移 044 与模型同 PR）。contract §8 未单列 spider_definitions 语义（编辑面字段集由 packet 钦定「读 spider_definition 模型与 yml_seed 结构定字段集」）；未改既有字段/键。
- 单一迁移头：离线修订图分析 `heads: ['044']`（46 revisions）。
- 方言核验：JSON 路径反查在 SQLite（测试默认）实测通过；MySQL 方言离线编译为 `JSON_EXTRACT`+`JSON_UNQUOTE`（MySQL 8 有效）。
- **MYSQL_FIDELITY 本机未跑**：当前 shell 无 MySQL root 口令（`Access denied`），迁移/JSON 查询的 MySQL 实测留给 qa/sre 环境复验。

```
$ uv run alembic -c backend/alembic.ini heads（离线图分析替代：46 revisions，heads=['044']）
```

**未自行加字段/改类型**：☑ 确认（仅 packet 钦定的 params 列；已在上表说明）

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `update_definition_meta` 入口记 name + 变更字段名集（sorted，不含值）；`delete_definition`/`enqueue` 既有入口日志保持 |
| trace_id | 既有中间件链（未动） |
| 错误日志上下文 | `_definition_default_params` 失败记 spider 名 + error（脱敏：不落 headers 值/Authorization 内容，只落字段名） |
| 慢操作耗时 | 既有（本票无新增慢路径） |

**日志脱敏核对**：☑ 无密码 ☑ 无 token（headers 只记字段名不记值）

## 6. 自测证据

### TDD 红绿（companion tdd）

```
$ uv run pytest -x -q backend/tests/test_t39_definition_edit_delete.py   # 实现前（红）
E   AttributeError: 'NoneType' object has no attribute 'kwargs'
FAILED backend/tests/test_t39_definition_edit_delete.py::TestApiParamsEdit::test_api_params_saved_and_echoed
1 failed in 1.33s
（红因：DefinitionUpdateMetaRequest 尚无 params 字段，pydantic 忽略未知键 → repo.update 未被调用）

$ uv run pytest -q backend/tests/test_t39_definition_edit_delete.py      # 实现后（绿）
24 passed in 2.54s
exit: 0
```

### 全量

```
$ cd /Users/xuyun/auto_agents && uv run pytest -q backend/tests
1519 passed, 38 skipped, 7 warnings in 148.83s
PYTEST_EXIT=0

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
ARCH_EXIT=0

$ uv run ruff check backend platform_core scripts
All checks passed!
```

（基线对照：T-37 后 1493 passed/38 skipped → 本票 1519 = +24 新测试 + b1c 钉改写净 +2，无既有测试流失。）

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-103.1 api 型编辑生效 | `TestApiParamsEdit::test_api_params_saved_and_echoed`（保存+回显）+ `TestEnqueueTakesDefinitionParams::test_enqueue_without_params_uses_definition_params`（后续任务按新参数）+ HTTP `test_operator_can_edit_params`（经办 200 落库） | ✅ |
| GWT-103.1 校验（字段类型/URL 形态/字段集） | `test_api_params_rejects_bad_url_shape` / `test_api_params_rejects_unknown_field` / `test_api_params_rejects_wrong_types` | ✅ |
| GWT-103.1 flow 型编辑生效 | `TestFlowParamsEdit::test_flow_edit_updates_plan_and_mirrors`（plan_json.flow 更新 + generated_params 再生 + 入口地址同步 + 定义镜像）+ `TestGetByRegisteredDefinition::test_finds_latest_registered_plan`（JSON 路径反查，DB 级） | ✅ |
| GWT-103.1 代码型受限 | `TestCodeTypeLimited::test_code_type_params_rejected_with_sentence`（web/custom 双参，「代码型爬虫请在源码中修改」）+ `test_meta_only_edit_still_works_for_code_type`（元信息不回退） | ✅ |
| GWT-103.2 未引用删除 | `test_unreferenced_delete_still_succeeds`（服务）+ `test_operator_can_delete_unreferenced`（HTTP，从方案列表消失）+ b1c `test_definition_delete_operator_ok` | ✅ |
| GWT-103.3 被引用删除拒绝 | `test_reject_message_names_tasks`（#id 列举）+ HTTP `test_delete_referenced_rejected_lists_tasks`（400 + 方案保持）+ 既有 m1 原子条件删回归（test_spider_datacenter_crud） | ✅ |
| GWT-103.3 编辑半·在跑任务不受影响 | `TestRunningTaskUnaffected::test_edit_does_not_touch_existing_tasks`（编辑后存量任务 params/status 不变）+ `test_explicit_params_win_over_definition`（显式 params 优先） | ✅ |
| GWT-103.4 空态 | ➖ UI 半（空态句「还没有采集方案。」归 T-40；后端列表数据面既有） | |
| GWT-103.5 越权 | HTTP `test_cross_tenant_edit_404_and_target_unchanged` / `test_cross_tenant_delete_404_and_target_kept`（A 直打 B → 404 同形，B 行不变）+ `test_viewer_edit_rejected_403` / `test_viewer_delete_rejected_403` + b1c viewer_403 钉 | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（flow 双行写为同 session 单 commit，无部分提交窗口；无独立回滚路径测试——沿用 Service 自持事务既有口径 test_transaction_ownership） | |
| 幂等 | `test_unreferenced_delete_still_succeeds` + 既有 m1 重复删除 404 | ✅ |
| 并发写 | ➖ N/A（编辑 last-write-wins；删除原子条件删既有 m1 TOCTOU 测试钉住） | |
| 外部依赖失败 | `_definition_default_params` DB 故障跳过填充（日志路径；与 `_ensure_spider_available` 同款 fail-open，既有 `test_db_error_skips_validation` 模式） | ✅ |

## 7. NFR 验证（票里有 NFR 时填）

➖ 本票无 NFR 行。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | ① MYSQL_FIDELITY 未在本 shell 跑（无口令）：迁移 044 与 `plan_json` JSON 路径查询需真 MySQL 复验（SQLite 实测过、MySQL 方言已离线编译核验）。② 编辑面字段集运行时读 yml `SPIDER_TYPES.api.fields`——改 yml 即扩字段集（无代码改动）。③ 删除拒绝句含至多 5 个 `#task_id`。④ 守卫变更：meta/delete 由 require_admin → require_operator（经办）；create/启停仍 require_admin。 |
| `/frontend`（T-40） | ① `PATCH /spiders/definitions/{name}/meta` 现收 `{title?, description?, params?}`；响应/注册表（`GET /spiders/registry` 的 spiders[].params）回显 params 供表单预填。② api 型 params=`{urls, headers}`；flow 型 params=`{urls, selectors, pagination?, detail?, filters?, render_js?...}`（FlowConfig 契约）。③ 代码型（web/custom）params 编辑=400，message 含「代码型爬虫请在源码中修改」可直投页面。④ 删除被引用=400，message 含任务号（如 `#12、#15`）。⑤ 越权=404 同形；只读=403。契约无偏差（未回 architect）。 |
| `/architect` | 无契约歧义。一处 GWT 标签勘误供记录：packet 把「在跑任务不受影响」标注为 GWT-103.3，spec 正文 GWT-103.3 是被引用删除——两者都已实现，仅标签口径以 spec 为准。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（1519 passed / 0 failed；arch 0；ruff 0）
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与迁移一致（params 列 expand-only；未改既有字段）
- [x] 无硬编码连接串/密钥/端口/阈值（api 字段集回退元组是 yml 缺省口径，非阈值）
- [x] async 上下文无同步阻塞调用（无 redis 同步链式直调；JSON/URL 校验纯 CPU 微秒级）
- [x] 无 `except: pass`（唯一宽 except 记 warning 后走降级分支，与既有 `_ensure_spider_available`/`registry` 同款）
- [x] 日志已脱敏（headers 只记字段名）
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」
- [x] 条件更新的 `rows == 0` 已处理（删除路径二分 NotFound/被引用）
- [x] 外部依赖四件套（N/A，无新增外部依赖；降级口径已注明）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报（GWT 标签勘误入 §8，未自行改 spec）
- [x] 票状态已更新为 done（本 evidence 即交付物；issues 目录未列本票单独文件）
