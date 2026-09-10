# 实现证据 · T-18 值班页列表改网关模型；空态 71.2 / 降级 71.3；URL `/newapi` 保留

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-18.md`｜FR 锚点：FR-71 / FR-70.3 / FR-07.1 / FR-75.2｜角色：/backend + admin 页｜日期：2026-09-09
> 泳道：L4

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径 `/api/v1/newapi/*` 一周期保留 | Router | `backend/app/api/v1/newapi.py` | 页 URL `/newapi` 未改 |
| GET 存在性隐藏 404 | Router | 同上 `require_platform_admin_or_404` | GWT-71.4 / 07.3 |
| 写面 `require_platform_admin` | Router | POST `/models` `/upstreams`；PUT/DELETE config | GWT-70.3 与测试同 PR |
| 空态/降级句 71.2 / 71.3 | Service + Schema | `gateway_models.py` + `NewapiOverviewResponse` | HTTP 200 + `available=false` |
| 列表映射网关模型/部署；无完整 Key | Service | `newapi_overview_service.py` + `gateway_models.py` | 仅 `api_key_masked` |
| Redis expand 双读 | Service | `newapi_api.read_cfg_hash` | 旧 `newapi:channel:cfg:{id}` → `relay:channel:cfg:{ref}` |
| 新写只 relay | Service | `write_cfg_hash` | 不改 `channel_id` 类型；无表列 `gateway_ref` |
| 权限判定 | Router 守卫 | `require_platform_admin` / `_or_404` | 写 403；读非超管 404 |
| 页空态/降级 | admin | `NewApiOps.tsx` | 禁止「暂无渠道」 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/gateway_models.py` | 新增 | 71.2/71.3 冻结句；映射；掩码 |
| `backend/services/llm_gateway/admin.py` | 修改 | `create_model` / `update_model` |
| `backend/services/newapi_overview_service.py` | 修改 | 列表改 LiteLLM；信封 71.2/71.3；写模型/上游 |
| `backend/services/channel_config_service.py` | 修改 | 列表改网关模型；双读；写 relay |
| `backend/services/newapi_api.py` | 修改 | `RELAY_CHANNEL_CFG_PREFIX` + 双读写 |
| `backend/services/channel_scheduler_service.py` | 修改 | `_channel_cfg` 双读（expand） |
| `backend/app/api/v1/newapi.py` | 修改 | 守卫拆分；POST models/upstreams |
| `platform_core/schemas/newapi.py` | 修改 | `GatewayModel*`；overview `models`/`empty_state`/`degrade_state` |
| `platform_core/queues.py` | 修改 | 登记 `RELAY_CHANNEL_CFG_PREFIX` |
| `backend/tests/test_newapi_api.py` | 修改 | 71.1–71.3；**70.3 node** |
| `backend/tests/test_b1c_newapi_channels_coverage.py` | 修改 | 双读；写 403；不可达 200 空 |
| `backend/tests/test_channel_config_service.py` | 修改 | 对齐 relay 写与空列表降级 |
| `frontend/admin/src/pages/NewApiOps.tsx` | 修改 | 71.2/71.3 文案；模型列；无完整 Key |
| `frontend/admin/src/pages/NewApiOps.test.tsx` | 新增 | 71.2/71.3/71.1 页测 |
| `frontend/admin/src/services/newapi.ts` | 修改 | GatewayModel 类型 |
| `frontend/admin/src/components/newapi/newapiShared.ts` | 修改 | 冻结句；verdict 去叠词 |
| `frontend/admin/src/components/newapi/ProbeResults.tsx` | 修改 | 本地空探针句 |
| `.sdlc/feat-four-pillars-v2/02-shape/tickets/T-18.md` | 修改 | 状态 done |

**与票里「会改哪些文件」一致**：☑ 是（未改 `channel_id` 类型；未加表列 `gateway_ref`；未引入第三配置前缀；未改 `llm_client.py` 四动作；未开 LiteLLM Admin UI；未代选 Q-VOICE；未重排五组）

**未触碰「不许改的文件」**：☑ 确认

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 网关 HTTP 写模型/上游 | 否 | 外部调用 |
| Redis 窗口配置 + channel_events | 否 | 事件失败只告警（既有口径） |

**事务提交后的操作失败怎么办**：配置已落 Redis；事件落库失败记 warning。

### 幂等

N/A（本票无新建幂等键）。守卫拒绝路径零副作用。☐ 未使用「先查后插」

### 并发控制

N/A（无条件更新行）

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| LiteLLM `/model/info` `/v2/model/info` | 5s overview | 不重试 | 200 + `available=false` + 71.3 句 | 读幂等 |
| LiteLLM POST `/model/new` | `LITELLM.TIMEOUT` | 不重试 | 守卫先拒租户写 | 由网关侧 |

配置：读 `NEWAPI.*`（全局默认窗口）；写 Redis `relay:channel:cfg:{ref}`。`LITELLM.*` 沿用 T-15，本票未加第三前缀。

## 4. ORM 与 DBML 对齐

➖ N/A（未改表、未加 `gateway_ref` 列、`channel_id` 仍 BIGINT）

**未自行加字段/改类型**：☑ 确认（表列等 `/dba`）

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | overview / register_model / register_upstream / set_config* 记 model_name/ref，不记 Key |
| trace_id | 沿用中间件 |
| 错误日志上下文 | 网关拉取失败 warning，不 500 |
| 慢操作耗时 | overview `wait_for` 5s |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整 Key ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

```
$ uv run pytest -x -q backend/tests/test_b1c_newapi_channels_coverage.py backend/tests/test_newapi_api.py backend/tests/test_newapi_api.py::test_operator_or_tenant_admin_write_gateway_model_rejected_list_unchanged
...................................                                      [100%]
35 passed in 1.31s
exit: 0
```

```
$ uv run pytest --collect-only -q backend/tests/test_newapi_api.py::test_operator_or_tenant_admin_write_gateway_model_rejected_list_unchanged
backend/tests/test_newapi_api.py::test_operator_or_tenant_admin_write_gateway_model_rejected_list_unchanged

1 test collected in 0.07s
exit: 0
```

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
✓ R11: backend 同步 redis_client() 链式直调（阻塞事件循环）
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
exit: 0
```

```
$ npm test --prefix frontend/admin -- --watchAll=false --testPathPattern='NewApiOps.test|App.test'
PASS src/pages/NewApiOps.test.tsx
PASS src/App.test.tsx
Test Suites: 2 passed, 2 total
Tests:       7 passed, 7 total
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-71.1 | `test_normal_aggregation_maps_and_strips_secrets` + `NewApiOps.test` 列表无完整 Key | ✅ |
| GWT-71.2 | `test_empty_models_is_71_2_not_load_failure` + 页测空态句 | ✅ 「还没有平台模型，去网关登记」 |
| GWT-71.3 | `test_client_exception_degrades_200` + 页测降级句 | ✅ 「LLM 网关管理面不可达，仅本地事件/探针」；HTTP 200 `available=false` |
| GWT-71.4 | `test_overview_requires_platform_admin` + `App.test` 租户 `/newapi` 404 壳 | ✅ |
| GWT-70.3 | `test_operator_or_tenant_admin_write_gateway_model_rejected_list_unchanged` | ✅ node 已存在 |
| GWT-75.2 | 映射剔除 Key；页仅掩码 | ✅ |
| GWT-07.3 | GET 404 同形（无渠道/无密钥） | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（无多步 OLTP 写） | ➖ |
| 幂等 | ➖ N/A（无新建幂等键；守卫拒绝零副作用） | ➖ |
| 并发写 | ➖ N/A（无条件更新） | ➖ |
| 外部依赖失败 | `test_client_exception_degrades_200` / `test_timeout_degrades` / `test_channels_remote_unreachable_200_empty` | ✅ |

## 7. NFR 验证（票里有 NFR 时填）

➖ 本票无独立 NFR 数字闸。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 71.2/71.3 句冻结在 overview `empty_state`/`degrade_state` 与页 copy。GET `/channels` 不可达现为 **200 空列表**（不再 502）。写模型 `POST /api/v1/newapi/models`，登记上游 `POST /api/v1/newapi/upstreams`，非超管 403。70.3 node 已挂。mock 了 LiteLLM HTTP。 |
| `/frontend` | 页已改：Card「LLM 网关值班」；菜单叶仍「中转站管控」。未外链 Admin UI。 |
| `/dba` | 表列 `gateway_ref` 仍等；本票 HTTP/Redis 已用 string ref。 |
| `/architect` | GET 仍 `require_platform_admin_or_404`（71.4 同形）；写面改为 `require_platform_admin`（70.3）。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿
- [x] 契约落位表已核对，分层无违规
- [x] 未自行加字段/改 `channel_id` 类型
- [x] 无硬编码连接串/密钥/端口
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 外部依赖四件套齐全
- [x] 四类易漏测试已覆盖或标 N/A
- [x] 未改 `llm_client.py` 四动作；未代选 Q-VOICE
- [x] 票状态已更新为 done
