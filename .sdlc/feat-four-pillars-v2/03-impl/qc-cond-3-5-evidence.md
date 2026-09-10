# 实现证据 · QC 条件 3/5（IM-24 command src_sync + GWT-06.1 审计）

> 票：放行意见条件 3、5｜FR 锚点：FR-39 / FR-38 / GWT-06.1｜角色：/backend｜日期：2026-09-10
> 上游：`06-deliver/release-opinion.md` 条件 3/5 · `04-verify/coverage.md` IM-24 / GWT-06.1 · ADR-0012
> 泳道：L4

未改 `uq_asset_type_name_alive`。未自动建 alias。未执行 slash。订阅仍一行不级联（T-25 / T-30 夹具）。未代选六问。未施工 Wave 2/3。未把 LiteLLM 焊进根 compose。未改 GWT。

TDD 红：command 同步 0 行；`test_scan_plugins_ok` 查 `OperationLog` 0 行（standalone `KeyError 'DEFAULT'`）。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| src_sync 写 `asset_type=command` | Service | `backend/services/power_market/sync.py` | `_sync_package` 在 plugin/skills 之后 `_upsert_commands` |
| plugin.json `commands` + `commands/*.md` | Service walk | `backend/services/power_market/walk.py` `_fold_commands` | 同 `origin_local_name` 合并，文件正文优先 |
| ADR-0012 slug | Service | `identity._bundled_slug` | `{plugin}__{origin_local_name}` |
| 第三方首次 attach unlisted | Service | `_attach_third_party` | 同源再同步不改 listing |
| 主标题短名 | Service | `_display_title` | 禁止长前缀当 title |
| slash 只登记 | 细节表 | `CapabilityCommand.slash/body_md` | 不执行 |
| 扫描审计谁/对什么 | Router 钩子 + Service | `capabilities.py:148` 已 `plugin.scan`/`plugins`；pytest `db_engine` 注入 DEFAULT，standalone 短事务落库 | GWT-06.1 |
| 数据读写 | ORM 既有 | `CapabilityAsset` + `CapabilityCommand` | 未加列、未改 uq |
| 幂等 | 唯一约束 | `uq_asset_type_name_alive` 未改 | 按 (type,name) upsert |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未把 ORM 送出 API ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/power_market/walk.py` | 修改 | `_fold_commands`：manifest dict/list + `commands/*.md` |
| `backend/services/power_market/sync.py` | 修改 | `_upsert_commands` / `_upsert_command_row` / detail |
| `backend/services/audit_service.py` | 修改 | standalone 独立短事务；**删除** `persist_audit_on_session`（C35-QA-02） |
| `backend/app/api/_helpers.py` | 修改 | `record_audit` 只委托 standalone，不 commit 请求 session |
| `backend/tests/conftest.py` | 修改 | `db_engine` 把本测试引擎注入 `async_engines["DEFAULT"]` |
| `backend/tests/test_audit_helpers.py` | 修改 | standalone 假值不得 await 请求 session.commit |
| `backend/tests/test_t29_sources.py` | 修改 | 具名：src_sync command + ADR-0012 + unlisted |
| `backend/tests/test_b1c_capabilities_coverage.py` | 修改 | `test_scan_plugins_ok` 查 OperationLog（who/what 未削弱） |

**与票里「会改哪些文件」一致**：☑ 是（未扩 Wave 2/3 / 未改 schema）

**未触碰「不许改的文件」**：☑ 确认（uq、alias 自动创建、GWT、根 compose、六问）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| src_sync 作业 + plugin/skill/command upsert | 是 | 同包失败不中断整批；成功包内同行提交 |
| 扫描业务 commit 后写审计 | 否（独立短事务） | 仅 `record_audit_standalone`；pytest 经 DEFAULT=测试引擎写入同一库 |

**事务提交后的操作失败怎么办**：审计失败只记日志（不影响 200）

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 目录 `(asset_type,name,alive_flag)`；命令 slug `{plugin}__{origin_local_name}` |
| 保证方式 | upsert 同名行；异源撞名 `PLUGIN_NAME_COLLISION` 计入失败包 |
| 重复请求返回 | 再同步更新正文/slash；仅首次 attach 写 unlisted |

☑ 未静默改名；未改 uq

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 第二 src_sync | 既有 Redis SET NX | 抢不到 → 409 `SYNC_IN_PROGRESS` |

☑ 本票未改锁

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 审计 DEFAULT 引擎 | 现网短事务 | 无 | 引擎空只记日志（不挡 200）；pytest 注入测试引擎 | 是（同 action+target 可多行；本夹具扫一次一行） |

## 4. ORM 与 DBML 对齐

☑ 字段名 ☑ 类型 ☑ 可空性 ☑ 默认值 ☑ 索引 ☑ 唯一约束 ☑ 外键 —— 使用既有 `capability_assets` / `capability_commands`；**未自行加字段**

结构核对：未发新迁移。`inspect(CapabilityAsset)` 夹具仍断言 `uq_asset_type_name_alive` 列为 `asset_type,name,alive_flag`。

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `SourceSync.sync` / `plugin.scan_plugins.start` / 审计 `action+target` |
| trace_id | 现网中间件 |
| 错误日志上下文 | 单包失败 `source+pkg`；审计失败 `action`（无密钥） |
| 慢操作耗时 | 本票无新外部调用 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。

TDD 红（实现前）：

```
$ uv run pytest -x -q backend/tests/test_t29_sources.py::test_src_sync_plugin_json_commands_creates_unlisted_command_adr0012_slug backend/tests/test_b1c_capabilities_coverage.py::test_scan_plugins_ok
F
=================================== FAILURES ===================================
___ test_src_sync_plugin_json_commands_creates_unlisted_command_adr0012_slug ___
>       assert len(rows) == 1
E       assert 0 == 1
FAILED backend/tests/test_t29_sources.py::test_src_sync_plugin_json_commands_creates_unlisted_command_adr0012_slug
1 failed in 1.37s
```

exit: 1

```
$ uv run pytest -q backend/tests/test_b1c_capabilities_coverage.py::test_scan_plugins_ok
F
>       assert len(logs) == 1
E       assert 0 == 1
Captured stderr call:
审计写入失败（已忽略，不影响业务）: action=plugin.scan, error='DEFAULT'
FAILED backend/tests/test_b1c_capabilities_coverage.py::test_scan_plugins_ok
1 failed in 1.18s
```

exit: 1

绿（实现后）：

```
$ uv run pytest -q backend/tests/test_b1c_capabilities_coverage.py backend/tests/test_t29_sources.py backend/tests/test_t30_command_cards.py backend/tests/test_saas_isolation.py
........................................................................ [ 74%]
.........................                                                [100%]
97 passed in 9.37s
```

exit: 0

```
$ bash tools/check/arch.sh
架构合规检查（13 条红线 + 4 条边界）
======================================
✓ R1: 硬编码连接串
✓ R2: 明文 password
✓ R3: scrapy → backend 反向依赖
✓ R4: scrapy 使用 SQLAlchemy
✓ R5: DOWNLOAD_DELAY 已配置
✓ R6: USER_AGENT 配置存在
✓ R7: API 层 import models
✓ R8: models 反向 import schemas
✓ R9: 无循环 import
✓ R10: service 方法入口缺 logger
✓ R11: backend 同步 redis_client() 直调（阻塞事件循环）
✓ R12: spider_service 门面白名单外 import（应直接依赖子 Service）
✓ R13: 租户过滤收口（安装点/裸语句/豁免清单同步）

--- 核心代码边界 ---
✓ B1: platform_core → backend/scrapy 反向依赖
✓ B2: backend → scrapy 直接依赖
✓ B3: config → 业务模块反向依赖
✓ B4: power_market 禁 spider_/newapi_/litellm_/relay_/channel_/ai_planner/llm_gateway 直连
✓ B4: ai_planner 禁 llm_gateway.admin（三模式）
✓ B4: ai_planner 除 llm_client.py 禁 llm_gateway.chat（三模式）
✓ B4: 禁止 LITELLM.DB_DSN
✓ B4: 禁止 create_async_engine 打网关库

--- 发布物密钥（FR-14）---
✓ FR-14: config.gen.yaml 不在跟踪树
✓ FR-14: 跟踪的 deploy/config 无上游 Key 样例模式

✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
```

exit: 0

```
$ uv run ruff check backend/services/power_market/walk.py backend/services/power_market/sync.py backend/services/audit_service.py backend/app/api/_helpers.py backend/tests/test_t29_sources.py backend/tests/test_b1c_capabilities_coverage.py
All checks passed!
```

exit: 0

### 验收项逐条对应

| GWT / 条件 | 覆盖的测试 | 结果 |
|---|---|---|
| Cond 3 / IM-24 src_sync 写 command | `test_src_sync_plugin_json_commands_creates_unlisted_command_adr0012_slug` | ✅ slug `cmd-pack__run-task`；title 短名；unlisted；`CapabilityCommand.slash=run-task`；零 alias |
| Cond 5 / GWT-06.1 谁/对什么 | `test_scan_plugins_ok` | ✅ `action=plugin.scan` `target=plugins` `actor_name=test-platform-admin` `actor_id=1` |
| GWT-39.x 商店不把 JSON 当货架 / 订一行 | `test_t30_command_cards.py` | ✅ 7 项随批绿 |
| ADR-0012 uq 未改 / 第三方不 listed | `test_t29_sources.py` | ✅ 随批绿 |
| PIT-3 豁免 | `test_saas_isolation.py` | ✅ 随批绿 |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | 单包失败不中断（既有 38.2） | ➖ N/A（本票未改包循环） |
| 幂等 | 再同步仍 1 行且 unlisted | ✅ 同具名夹具二次 `_sync` |
| 并发写 | src_sync Redis 锁 | ➖ N/A（本票未改锁） |
| 外部依赖失败 | 审计 DEFAULT 空不挡 200；**不**回写请求 session | ✅ 红测 `error='DEFAULT'` + commit awaited；绿测 OperationLog 1 行且 commit=0 |

## 7. NFR 验证（票里有 NFR 时填）

本票无新 NFR。NFR-01 浏览器卡片可见仍待预发。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | GWT-06.1 现可查 OperationLog；command 目录行由 **src_sync** 生产，本机 `scan-plugins` 仍只写 plugin 行（D16 回退路径未扩 command） |
| `/frontend` | 第三方 command 默认同步 unlisted；商店仍要超管上架后才出卡。主标题是 origin 短名 |
| `/architect` | 无新错误码。slash 不执行 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（具名四文件 97 passed + arch.sh 0）
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`（吞异常）
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」当身份键（uq 未改）
- [x] 条件更新的 `rows == 0` 已处理 / N/A
- [x] 外部依赖四件套齐全或标 N/A
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 未改 GWT / 未代选六问 / 未施工 Wave 2/3

## Debug record

> C35-QA-02 / G-fresh FAIL：GWT-06.1 靠请求 session commit 空心绿。日期：2026-09-10。未改 GWT。未动 leftover 06.3 `record_authz_denied`。

### Reproduce

Standalone 在 pytest 空 DEFAULT 下失败（exit 0 = 探针跑完，业务路径返回 False）：

```
$ uv run python - <<'PY'
# manager.async_engines.clear(); record_audit_standalone(...)
PY
审计写入失败（已忽略，不影响业务）: action=plugin.scan, error='DEFAULT'
standalone_returned= False
DEFAULT_present= False
```

exit: 0

Fallback 提交请求 session：

```
request_session_commit_awaited= 1
request_session_commit_called= True
```

exit: 0

当时扫描格靠该回写绿：

```
$ uv run pytest -q backend/tests/test_b1c_capabilities_coverage.py::test_scan_plugins_ok
.                                                                        [100%]
1 passed in 1.74s
```

exit: 0

TDD 红（钉 ADR-0007 D4：standalone 假值不得 commit 请求 session）：

```
$ uv run pytest -q backend/tests/test_audit_helpers.py::test_api_helper_does_not_commit_request_session_when_standalone_false
F
AssertionError: Expected commit to not have been awaited. Awaited 1 times.
FAILED backend/tests/test_audit_helpers.py::test_api_helper_does_not_commit_request_session_when_standalone_false
1 failed in 1.27s
```

exit: 1

### Eliminated hypotheses

- 扫描 Service 没写 OperationLog → 资产行仍 200 落库，缺的是审计路径 → 否
- leftover 06.3 `record_authz_denied` 是同一缺陷 → 未改该函数，403 leftover 仍绿 → 否
- 必须 `init_all()` 真 MySQL 才能给 DEFAULT → conftest 已证会打真 `llm_providers` → 否
- 削弱 `test_scan_plugins_ok` who/what 才能绿 → 未改那些断言 → 否

### root_cause

pytest `_reset_db_manager` 清空 DEFAULT，`record_audit_standalone` KeyError；为让 GWT-06.1 绿，`record_audit` 在 standalone 假值时对请求 session `commit`，API 钩子抢走了事务生命周期（ADR-0007 D4）。

### Minimal fix

- `_helpers.record_audit` 只委托 `record_audit_standalone`（不再读返回值做降级）
- 删除 `persist_audit_on_session`
- `conftest.db_engine` 把本测试引擎注入 `get_manager().async_engines["DEFAULT"]`（不 `init_all()`）
- leftover `record_authz_denied` 保持原样

### Re-run

```
$ uv run pytest -q backend/tests/test_b1c_capabilities_coverage.py::test_scan_plugins_ok
.                                                                        [100%]
1 passed in 1.27s
```

exit: 0

```
$ uv run pytest -q backend/tests/test_audit_helpers.py backend/tests/test_b1c_capabilities_coverage.py::test_scan_plugins_tenant_admin_403_leftover backend/tests/test_b1c_capabilities_coverage.py::test_scan_plugins_viewer_403_zero_write backend/tests/test_b1c_capabilities_coverage.py::test_listing_tenant_admin_403_row_unchanged backend/tests/test_b1c_capabilities_coverage.py::test_plugin_verify_tenant_admin_403_row_unchanged
........                                                                 [100%]
8 passed in 1.59s
```

exit: 0

Fix 后探针：`request_session_commit_awaited= 0`。`persist_audit_on_session` 仓库内 0 命中。

```
$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
```

exit: 0
