# 实现证据 · T-26 值班行「活」与三句互斥；伪装不自动关渠

> 票：`02-shape/contract.md` §10 T-26｜FR 锚点：FR-U25｜角色：/backend｜日期：2026-09-13

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| GET `/api/v1/newapi/overview` | Router | `backend/app/api/v1/newapi.py` | 既有路径；本票不新开 |
| 页级三态 empty / degrade / live | Schema + Service | `platform_core/schemas/newapi.py` · `gateway_models.page_duty_copy` | 互斥；禁止「暂无渠道」 |
| 行态 `duty_row_status=live` / 文字「活」 | Schema + Service | `GatewayModelResponse` · `apply_duty_row` | 仅探针 original；降级不标活 |
| 权限（仅超管；租户 404 同形） | Router 守卫 | `require_platform_admin_or_404` | GWT-U25.3；未改守卫 |
| 伪装不关渠 | Service（既有） | `channel_probe_service._probe_channel` | GWT-07.6 回归 |
| 本地事件/探针 | Repository | `newapi_repository.latest_result_per_channel` | 按当前 `gateway_ref`→channel_id 集合 + 24h 窗；无集合不扫表。降级仍返回 24h 事件 + 批次 |
| 错误码映射 | 统一异常处理器 | HTTP_404 Not Found | 未新造信封 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `platform_core/schemas/newapi.py` | 修改 | `duty_page_state`；行 `duty_row_status` / `duty_row_status_text` |
| `backend/services/gateway_models.py` | 修改 | 冻结句 + `page_duty_copy` / `apply_duty_row` / `clear_duty_row` |
| `backend/services/newapi_overview_service.py` | 修改 | 可达时按当前 ref 集合+24h 窗标活；降级清活标；三态互斥 |
| `backend/repositories/newapi_repository.py` | 修改 | `latest_result_per_channel(channel_ids, since)`；无集合不扫表 |
| `backend/tests/test_fr_u25_duty.py` | 修改 | GWT-U25.1…U25.4 + 第四态 + 降级非空夹具 + 查询收口 |
| `backend/tests/test_newapi_api.py` | 修改 | PIT-2：mock 新仓储方法；钉 empty/degrade page_state |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：合同未列路径；沿用既有 `/newapi/overview`。未改守卫、未租户化 LiteLLM admin、未加表列。）

**未触碰「不许改的文件」**：☑ 确认（未改 GWT；未改 schema 046；无「当前可买」；未把网关 Admin UI 做成租户菜单。）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 总览读网关 + 本地统计 | 否（只读） | 网关失败降级，本地表独立 |
| 伪装探针落库 | 既有短会话 | 不写渠道开关 / 窗口配置 |

**事务提交后的操作失败怎么办**：网关不可达 → HTTP 200 + `duty_page_state=degrade`，本地事件/探针仍回。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 查询只读；探针伪装路径无关渠副作用 |
| 保证方式 | 不调用 update_model / budget / 状态键 |
| 重复请求返回 | 200 同形 |

☑ 未使用「先查后插」（本票无新写）

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 本票无状态机 UPDATE | — | N/A 只读总览 |

☑ N/A 不对渠道/探针表做条件更新

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| LiteLLM admin `list_models` | `OVERVIEW_TIMEOUT_SECONDS=5` | 无 | `available=false` + 降级句；本地仍可见 | 只读 |
| 探针 chat 适配叶（伪装回归） | 既有 | 无 | 只落库+通知 | 不关渠 |

## 4. ORM 与 DBML 对齐

☑ 本票无新表/新列。读既有 `channel_probe_results`（011）。缺探针 ≡ 行不标活。

结构核对输出：

```
$ 未跑 SHOW CREATE / alembic check（无 DDL）
N/A — 响应字段 duty_page_state / duty_row_status 仅 Pydantic，不落库
```

**未自行加字段/改类型**：☑ 确认（需要变更已回 `/dba`：无）

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `get_overview` 记「聚合 LLM 网关值班总览」；`page_duty_copy` / `apply_duty_row` debug |
| 错误日志上下文 | `_fetch_models` warning 记降级原因；不含 Key |
| 脱敏 | 掩码上游 Key；404 无渠道列表 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整上游 Key ☑ 无「当前可买」

## 6. 自测证据

> 命令与退出码**原样粘贴**。「测试通过」「基本完成」不算证据。

```
$ uv run pytest -q backend/tests/test_fr_u25_duty.py
..........                                                               [100%]
10 passed in 2.27s
T26_EXIT:0
```

```
$ uv run pytest -q backend/tests/test_newapi_api.py backend/tests/test_fr_u25_duty.py
........................                                                 [100%]
24 passed in 2.47s
RELATED_EXIT:0
```

（原 T-26 全量 `1674 passed, 40 skipped` 未在本返工重跑。）

```
$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
ARCH_EXIT:0
```

```
$ uv run python /Users/xuyun/.zcode/local-plugins/sdlc-workflow/skills/impl-evidence/scripts/check-layering.py backend/app/api backend/services backend/repositories
✓ 分层依赖检查通过
LAYER_EXIT:0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-U25.1 正常 | `test_gwt_u25_1_live_row_not_empty_or_degrade` | ✅ 行 `duty_row_status=live` / 「活」；页非空/降级句 |
| GWT-U25.2 空态 | `test_gwt_u25_2_empty_reachable_zero_models` | ✅ 「还没有平台模型，去网关登记」；禁「暂无渠道」。Given=0 模型，不把第四态画成空句 |
| GWT-U25.3 越权 | `test_gwt_u25_3_tenant_company_admin_duty_apis_404` | ✅ HTTP_404 / Not Found；无列表/密钥/抱歉 |
| GWT-U25.4 降级 | `test_gwt_u25_4_degrade_unreachable_keeps_local` | ✅ 「LLM 网关管理面不可达，仅本地事件/探针」；本地 24h 仍回；不拉 latest_result |
| GWT-U25.4 非空夹具 | `test_gwt_u25_4_degrade_nonempty_models_not_live` | ✅ 降级若出现 model 行不得 `duty_row_status=live`（QA-03） |
| 第四态（非 GWT-U25.2） | `test_gwt_u25_reachable_registered_no_original_not_empty` | ✅ 可达+≥1 模型+无 original → `duty_page_state is None`；空/降级句均为 null；行不标活；禁「暂无渠道」（QA-04） |
| 查询收口 | `test_overview_latest_probe_scoped_to_current_gateway_refs` · `test_latest_result_per_channel_without_ids_does_not_scan` · `test_latest_result_per_channel_sql_bounded_to_ids_and_since` | ✅ 仅当前 channel_id + 24h `created_at` + LIMIT；无集合不 execute（QA-05） |
| GWT-07.6 伪装不关渠 | `test_gwt_u25_spoofed_does_not_auto_disable_channel` | ✅ spoofed 后窗口/额度不变；无 update_model/budget |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（总览只读；伪装路径无关渠写） |
| 幂等 | 查询只读；伪装重复不关渠 | ✅ 配置 hash 快照不变 |
| 并发写 | — | ➖ N/A（无条件更新） |
| 外部依赖失败 | `test_gwt_u25_4` 网关异常 | ✅ HTTP 200 降级，不 5xx |

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| Q-OPS-DUTY | 本波不承诺 SLA 数字 | 未写 SLA 字段 | pytest |
| FR-U24 | 无「当前可买」 | `_assert_no_banned` | pytest |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | `GET /api/v1/newapi/overview`。三态互斥：`duty_page_state` ∈ empty\|degrade\|live；可达+已登记+无 original 时为 **null**（不是 empty）。租户打 `/overview` `/events` `/probe-results` `/channels` `POST /probe` 与 `/api/v1/admin/tenants` 同形 404。探针查询按当前 gateway_ref 集合 + 24h 窗。 |
| `/frontend`（T-27） | 空句 `empty_state`；降级句 `degrade_state`；活行 `duty_row_status=live` 且 `duty_row_status_text=活`。可达+已登记+无 original 时 `duty_page_state` 为 null（不是 empty）。有任一活行时不要渲染空/降级标题。禁「暂无渠道」。不要租户化网关 Admin。 |
| `/architect` | 响应新增可选字段 `duty_page_state` / `duty_row_status` / `duty_row_status_text`（expand，旧客户端可忽略）。未新造错误码。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」
- [x] 条件更新 N/A
- [x] 外部依赖四件套：超时/无重试/降级/只读
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 票状态：本 spawn 交付 evidence；orchestrator 更新 state

## Rework record

Round 1 · 2026-09-13 · close QA-03 / QA-04 / QA-05（N4 only；未重开 N1–N3；未改 GWT；未弱化 GWT-U25.3 404 同形）。

| QA | 处理 |
|---|---|
| QA-03 | 删空列表上恒真的 `all != live`。非空降级夹具：`_fetch_models` 注入已标 live 的行 → `clear_duty_row`；断言不得 `duty_row_status=live`；本地 24h 仍回；不调用 `latest_result_per_channel`。 |
| QA-04 | 命名测试 `test_gwt_u25_reachable_registered_no_original_not_empty`：可达 ∧ ≥1 模型 ∧ 无 original → `duty_page_state is None`（不是 empty/degrade），`empty_state`/`degrade_state` null，行不标活，正文无「暂无渠道」。不把该态塌成 GWT-U25.2 空句。 |
| QA-05 | `latest_result_per_channel(channel_ids, since)`：无集合直接 `{}` 不 execute；有集合则 `channel_id IN` + `created_at >= since` + `LIMIT len(ids)`。总览传入当前 gateway_ref 映射的 id 与 24h 窗。降级路径仍走 `_local_stats` 24h 事件、不拉 latest。 |

TDD red（实现前，断言失败而非 import 错）：

```
$ uv run pytest -q backend/tests/test_fr_u25_duty.py
..F.FFF...                                                               [100%]
FAILED test_gwt_u25_4_degrade_nonempty_models_not_live — assert False（live 泄漏）
FAILED test_overview_latest_probe_scoped_to_current_gateway_refs — channel_ids is None
FAILED test_latest_result_per_channel_without_ids_does_not_scan — 无界查询仍 execute（初夹具 AttributeError；改为 AsyncMock 后钉 assert_not_awaited）
FAILED test_latest_result_per_channel_sql_bounded_to_ids_and_since — unexpected keyword channel_ids
4 failed, 6 passed, 1 warning in 3.21s
exit: 1
```

Green + 分层：

```
$ uv run pytest -q backend/tests/test_fr_u25_duty.py
..........                                                               [100%]
10 passed in 2.27s
T26_EXIT:0

$ uv run python /Users/xuyun/.zcode/local-plugins/sdlc-workflow/skills/impl-evidence/scripts/check-layering.py backend/app/api backend/services backend/repositories
✓ 分层依赖检查通过
LAYER_EXIT:0
```

未写「当前可买」；未租户化 LiteLLM admin；活 ≠ SKU active；Q-OPS-DUTY 无 SLA 数字；GWT-U25.3 仍 404 同形。
