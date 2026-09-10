# 实现证据 · T-19 探针/窗口改管理 HTTP；spend→budget；伪装仍不熔断

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-19.md`｜FR 锚点：FR-07 / FR-71｜角色：/backend｜日期：2026-09-09
> 泳道：L4
> 闸：`uv run pytest -x -q backend/tests/test_llm_probe.py backend/tests/test_llm_cooldown.py`；`bash tools/check/arch.sh`（票仍写 `scripts/check-arch.sh`，该路径已不在）

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 探针 `POST /v1/chat/completions` | Service 叶 | `llm_gateway/chat.py` via `channel_probe_service.py` | 经适配叶；非 new-api 方言 |
| 列表 / spend / budget HTTP | Service 叶 | `llm_gateway/admin.py` | T-15 已有；本票加 `update_budget` |
| GWT-07.6 伪装不熔断 | Service | `channel_probe_service._probe_channel` | spoofed 只落库+通知；不关渠道、不改窗口/额度 |
| spend→budget | Service | `channel_scheduler_service.py` | 先读 `get_spend_logs` 再 `create_budget`/`update_budget` |
| 冷却恢复不覆盖人工禁用 | Service | `channel_scheduler_service._recover_ref` | 官方 budget API 盖不住本条；backend 只留这一条，仍 HTTP |
| Redis expand 双读 | Service | `newapi_api.read_cfg_hash` / `read_state_json` | 旧 `newapi:*` → 新写 `relay:*` |
| `channel_id` BIGINT | Repository | `channel_probe_results.channel_id` | `_channel_id_from_ref` 映射；不加表列 |
| 配置前缀 | Config/Redis | `NEWAPI.*` 读 + `RELAY.*` 写 | 禁止第三前缀 / 禁止 DSN |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/llm_gateway/admin.py` | 修改 | `update_budget` POST `/budget/update` |
| `backend/services/newapi_api.py` | 修改 | string ref 状态双读；`_channel_id_from_ref`；人工禁用标记 |
| `backend/services/channel_probe_service.py` | 修改 | 列表 admin HTTP；采集 chat 适配叶；伪装不熔断 |
| `backend/services/channel_probe_score.py` | 新增 | 10 维评分迁出（阈值仍 0.15，algo 不改） |
| `backend/services/channel_scheduler_service.py` | 修改 | 删 DSN/SQL；spend→budget；只留冷却恢复 |
| `backend/services/channel_config_service.py` | 修改 | `_main_async_session` 改从 `newapi_api` 引 |
| `platform_core/queues.py` | 修改 | 登记 `RELAY_CHANNEL_STATE_PREFIX` |
| `backend/tests/test_llm_probe.py` | 修改 | GWT-07.6；无 DSN；chat 适配叶 |
| `backend/tests/test_llm_cooldown.py` | 修改 | 冷却恢复不覆盖人工禁用；spend→budget |
| `backend/tests/test_channel_config_service.py` | 修改 | 伪装不改 cfg；旧键人工禁用挡住恢复 |
| `backend/tests/test_newapi_services.py` | 修改 | 去掉 DSN 启动；旧 SQL 用例 skip |
| `backend/tests/test_llm_gateway.py` | 修改 | `update_budget` 路径 |
| `.sdlc/feat-four-pillars-v2/02-shape/tickets/T-19.md` | 修改 | 状态 done |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：评分拆到 `channel_probe_score.py` 以满足 ≤500 行；闸路径是 `tools/check/arch.sh`）

**未触碰「不许改的文件」**：☑ 确认（未改探针阈值；未 1:1 复刻 new-api 窗口调度；未加 `gateway_ref` 表列；未改 `channel_id` 类型；未加 DSN；未改 T-16 `llm_chat` resolve；未碰 T-17 `/llm`；未退役 new-api；未代选六问）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 探针落 `channel_probe_results` | 否（独立短事务） | 失败只告警，不回滚采集 |
| spend 读 + budget 写 | 否 | 外部 HTTP；先读后写 |
| 冷却恢复 HTTP + 清 Redis 状态 | 否 | 外部调用 |

**事务提交后的操作失败怎么办**：budget HTTP 失败记 error，Redis 冷却状态仍落（下轮重试写）；事件落库失败 warning。

### 幂等

N/A（无新建业务幂等键；budget_id=`relay:{gateway_ref}` 由网关侧去重，失败则 update）。☐ 未使用「先查后插」

### 并发控制

锁：`distributed_lock`（既有探针/调度锁）。人工禁用以 Redis cfg `manual_disabled` 为准，恢复前再 GET 模型列表。

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| LiteLLM `POST /v1/chat/completions` | `LITELLM.TIMEOUT` | 不重试 | 单题 ok=False，过半失败 → offline | 读采集 |
| LiteLLM GET `/spend/logs` | 同上 | 不重试 | 空 map，本轮不写 budget | 读幂等 |
| LiteLLM POST `/budget/new` `/budget/update` | 同上 | new 失败改 update | 记 error，不 DSN | budget_id 自然键 |

**Spike（官方 OpenAPI，无生产 Key）**：LiteLLM OSS budget/spend **没有**「自动禁用 vs 人工禁用」状态，也没有「冷却到期自动恢复且跳过人工禁用」。因此 backend **只保留**该恢复条，仍走 admin HTTP；窗口策略映射 budget，不 1:1 PUT 渠道 status。

## 4. ORM 与 DBML 对齐

➖ N/A（未改表、未加 `gateway_ref` 列、`channel_id` 仍 BIGINT）

**未自行加字段/改类型**：☑ 确认（表列等 `/dba`）

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | 探针/调度 start、批次、budget 写、恢复；只记 ref/model，不记 Key |
| trace_id | 沿用中间件 |
| 错误日志上下文 | spend/budget/落库失败 warning/error |
| 慢操作耗时 | 探针 latency_ms 记身份题 RTT |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整 Key ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

```
$ uv run pytest -x -q backend/tests/test_llm_probe.py backend/tests/test_llm_cooldown.py
..................                                                       [100%]
18 passed in 1.86s
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
exit: 0
```

同票列出的第三文件（非票闸命令，已绿）：

```
$ uv run pytest -x -q backend/tests/test_channel_config_service.py
.........                                                                [100%]
9 passed in 1.13s
exit: 0
```

### 验收项逐条对应

| GWT / Then | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-07.6 伪装不熔断；窗口与额度不变；Wave L 后探针仍走平台网关 | `test_gwt_07_6_spoofed_keeps_channel_usable_window_quota_unchanged` + `test_spoofed_probe_does_not_rewrite_relay_cfg` | ✅ 渠道仍可用；cfg 快照不变；无 budget/state 写 |
| 探针经适配叶 `/v1/chat/completions`，非 new-api，非 DSN | `test_probe_collects_via_gateway_chat_completions_not_newapi` + `test_t19_probe_source_no_dsn_uses_gateway_chat` | ✅ |
| spend→budget；先读 spend 再写 | `test_over_limit_maps_spend_to_budget_not_dsn` | ✅ `budget_id=relay:{ref}` |
| 冷却到期自动恢复且不覆盖人工禁用 | `test_cooldown_recovery_skips_manual_disable_http` + `test_manual_disabled_on_old_cfg_key_blocks_recovery` + `test_cooldown_recovery_writes_budget_when_not_manual` | ✅ |
| 禁止 `LITELLM.DB_DSN` / `create_async_engine` | arch B4 + 源码断言 | ✅ |
| 阈值不改 | `_REF_SIMILARITY_SPOOF_THRESHOLD = 0.15` 仍在 `channel_probe_score.py` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（无多步 OLTP 同事务） | ➖ |
| 幂等 | ➖ N/A（无新建幂等键；budget_id 自然键） | ➖ |
| 并发写 | 既有 `distributed_lock`；本票未加条件更新行 | ➖ N/A（无 `rows==0` 条件更新） |
| 外部依赖失败 | spend 失败空 map 不写；chat 失败 ok=False → offline | ✅ |

## 7. NFR 验证（票里有 NFR 时填）

➖ 本票无独立 NFR 数字闸。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | GWT-07.6 夹具：spoofed 后 Redis cfg 不变、无 budget 写、渠道仍在列表。冷却：`manual_disabled=1`（含旧 `newapi:channel:cfg:{id}` 双读）不恢复。mock 了 LiteLLM HTTP。阈值仍 0.15。 |
| `/dba` | 表列 `gateway_ref` 仍等；`channel_id` 仍 BIGINT，探针用 sha256 截断映射非数字 ref。 |
| `/architect` | 官方 budget API 盖不住「冷却到期且不覆盖人工禁用」→ backend 只留该条 HTTP 恢复。未改 GWT。 |
| T-17 / T-20 | 本票未碰 `/llm` 经办点击；未退役 new-api。 |

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
- [x] 未改探针阈值；未改 T-16 resolve；未代选六问
- [x] 票状态已更新为 done
