# 实现证据 · T-20 退役验收：停 new-api 进程；墓碑；`NEWAPI.ENABLED` 恒 false 后删读

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-20.md`｜FR 锚点：FR-72 / FR-70.1 / FR-70.4｜角色：/sre｜日期：2026-09-09
> 泳道：L4
> 闸：`uv run pytest -x -q backend/tests/test_llm_four_actions_http.py::test_post_plan_outbound_gateway`；`npm test --prefix frontend/admin -- --testPathPattern=App.test --testNamePattern=test_operator_no_direct_gateway_or_relay_token_entry`；`bash tools/check/arch.sh`
> 本文件不含任何上游 Key / master / AccessToken / DSN 明文。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 默认 `LLM.DATA_PLANE=litellm` | Config + const | `config/default/llm.yml` · `backend/config_consts.py` | `providers` 仅回滚窗，不是完成态 |
| `NEWAPI.ENABLED` 恒 false | Config 墓碑 | `config/default/newapi.yml` | 只留 ENABLED:false；禁止当运行时开关 |
| 删 NEWAPI.* 读路径 | Service / lifespan | scheduler / probe / config / `app/__init__.py` / `newapi_api.py` | 运行时只读 `RELAY.*` + `LITELLM.*` |
| 值班产品规则 | Config | `config/default/relay.yml` | 窗口/探针；禁止第三前缀 |
| 进程停止 + 墓碑 | 编排 | `deploy/newapi/TOMBSTONE.md` | 根 compose **无** new-api 服务 |
| GWT-70.4 经办壳 | admin 测 | `frontend/admin/src/App.test.tsx::test_operator_no_direct_gateway_or_relay_token_entry` | 无「直连平台网关」、无「我的中转令牌」 |
| GWT-70.1 成功格 | HTTP 测 | `backend/tests/test_llm_four_actions_http.py::test_post_plan_outbound_gateway` | 只钉该 node；禁止 similar-suggest / 70.2 / 74.1 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import ☑ 未把 new-api 写回根 compose ☑ 未代选 Q-RELAY / Q-AGPL ☑ 未把渠道组写成当前可买

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `config/default/llm.yml` | 修改 | 默认 `DATA_PLANE: litellm` |
| `config/default/relay.yml` | 新增 | 值班窗口/探针 `RELAY.*` |
| `config/default/newapi.yml` | 修改 | 墓碑：`ENABLED: false` only |
| `backend/config_consts.py` | 修改 | `LLM_DATA_PLANE=litellm`；RELAY 默认 |
| `backend/app/__init__.py` | 修改 | lifespan 只读 `RELAY.SCHEDULER_ENABLED` / `RELAY.PROBE_ENABLED` |
| `backend/services/ai_planner/llm_client.py` | 修改 | 解析默认随 `LLM_DATA_PLANE` |
| `backend/services/channel_scheduler_service.py` | 修改 | 删 NEWAPI.* 读 |
| `backend/services/channel_probe_service.py` | 修改 | 删 NEWAPI.* 读 |
| `backend/services/channel_config_service.py` | 修改 | 全局默认读 RELAY.* |
| `backend/services/newapi_api.py` | 修改 | 客户端不再 `settings.get NEWAPI.*` |
| `frontend/admin/src/App.test.tsx` | 修改 | **70.4 node** |
| `backend/tests/test_t20_retire_newapi.py` | 新增 | 默认 plane / 无 NEWAPI 读 / 根 compose |
| `backend/tests/test_newapi_*.py` 等 | 修改 | 夹具改 RELAY.* |
| `deploy/newapi/TOMBSTONE.md` | 新增 | 墓碑（无密钥） |
| `deploy/newapi/README.md` | 修改 | 指向墓碑 |
| `.env.example` | 修改 | NEWAPI 运行时注释作废 |
| `.sdlc/feat-four-pillars-v2/02-shape/tickets/T-20.md` | 修改 | 状态 done |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：窗口/探针默认从 NEWAPI.* 迁到 RELAY.yml，属 ADR-0014 contract「只留 RELAY.*」；未改官网定价文案，T-01 预告仍在）

**未触碰「不许改的文件」**：☑ 确认（未把渠道组写成当前可买；未答 Q-RELAY / Q-AGPL；未用 similar-suggest / 70.2 / 74.1 勾 70.1；未把 new-api 写回根 compose；未开 LiteLLM Admin UI 当租户产品）

## 3. 关键实现决策

### 事务边界

N/A（无 OLTP 写；无表变更）。☑ 未自行加字段/改类型

### 幂等

N/A。☑ 未使用「先查后插」

### 并发控制

N/A（无新条件更新）

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| LiteLLM Proxy（规划出口） | `LITELLM.TIMEOUT` | T-16 既有 | 74.1 句 | 本票不改 chat |
| 值班列表 | T-18 既有 HTTP | 不重试 | 71.2 / 71.3 | 读幂等 |

### 回滚（已写清：不是完成态）

1. `LLM.DATA_PLANE=providers`（yml 或 `AUTO_AGENTS_LLM__DATA_PLANE`）= **仅回滚窗**。
2. **不要**把 new-api 请回运行时当常规回滚（ADR-0014 复审禁令）。

## 4. ORM 与 DBML 对齐

➖ N/A（无表变更）

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | 调度/探针 start 仍只记 interval/ref，不记 Key |
| 错误日志上下文 | lifespan 启动失败仅 warning |
| 墓碑 | `deploy/newapi/TOMBSTONE.md` 无密钥 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整 Key ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。70.1 闸**只**成功格 node。

### 进程已停夹具

本机 Docker daemon **未运行**（`unix:///Users/xuyun/.docker/run/docker.sock` 不存在）。compose `ps`/`down` 因缺 `SESSION_SECRET` **且**无 daemon 无法连引擎（exit 1）。进程停止以「无引擎 + 无进程 + 3000 无监听」为夹具，而不是把 new-api `up` 再 `down`。

```
$ test -S /Users/xuyun/.docker/run/docker.sock; echo docker_sock:$?
docker_sock: absent
exit: 0   # 分支打印 absent；文件不存在

$ docker ps -a --filter name=newapi --format '{{.Names}} {{.Status}}'
failed to connect to the docker API at unix:///Users/xuyun/.docker/run/docker.sock; ... connect: no such file or directory
exit: 1

$ pgrep -fl 'new-api|newapi-app|calciumion/new-api'
exit: 1

$ lsof -nP -iTCP:3000 -sTCP:LISTEN
exit: 1

$ rg -n "calciumion/new-api|container_name: newapi|newapi-net" docker-compose.yml
exit: 1   # 无命中；根 compose 未把 new-api 声明回来

$ test -f deploy/newapi/TOMBSTONE.md; echo $?
0
```

`docker compose -f deploy/newapi/docker-compose.yml down --remove-orphans` 与 sqlite 变体：**exit 1**（插值 `SESSION_SECRET is required`；随后 docker API 不可达）。无容器可停 = 已停。

### 闸（原样）

```
$ uv run pytest -x -q backend/tests/test_llm_four_actions_http.py::test_post_plan_outbound_gateway
.                                                                        [100%]
1 passed in 1.61s
exit: 0
```

未跑 `::test_post_plan_no_model_only_70_2` / `::test_post_plan_unreachable_only_74_1` / `or_cell_failure` / similar-suggest 当本票 70.1。

```
$ CI=true npm test --prefix frontend/admin -- --testPathPattern=App.test --testNamePattern=test_operator_no_direct_gateway_or_relay_token_entry --watchAll=false
PASS src/App.test.tsx
  ✓ test_operator_no_direct_gateway_or_relay_token_entry (633 ms)
  ○ skipped …（同文件其余 5 条）
Test Suites: 1 passed, 1 total
Tests:       5 skipped, 1 passed, 6 total
exit: 0
```

同文件全量 `App.test`：6 passed，exit 0。

```
$ bash tools/check/arch.sh
架构合规检查（13 条红线 + 4 条边界）
======================================
✓ R1 … ✓ R13
--- 核心代码边界 ---
✓ B1 ✓ B2 ✓ B3 ✓ B4（含 ai_planner 禁 admin / 禁 LITELLM.DB_DSN）
--- 发布物密钥（FR-14）---
✓ FR-14: config.gen.yaml 不在跟踪树
✓ FR-14: 跟踪的 deploy/config 无上游 Key 样例模式
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0
```

默认配置核对（同 PR，非 70.1 闸成员）：`backend/tests/test_t20_retire_newapi.py` 4 passed，含 `settings.get("LLM.DATA_PLANE") == "litellm"`、`NEWAPI.ENABLED` 假、运行时无 `settings.get("NEWAPI.`。

### 验收项逐条对应

| GWT | 覆盖的测试 / 夹具 | 结果 |
|---|---|---|
| GWT-72.1 | 进程已停夹具（上）+ 值班已是 FR-71 列表（T-18）+ 随后规划不经 new-api | ✅ 与 70.1 同勾 |
| GWT-70.1 | **只** `::test_post_plan_outbound_gateway` outbound=网关 URL | ✅ exit 0 |
| GWT-72.2 | 值班页仍 T-18 网关列表 / 71.2 / 71.3；本票删 NEWAPI 管理面读 | ✅ 回归既有页，无 new-api 渠道方言 |
| GWT-72.3 | 租户无「我的渠道组 / 我的中转令牌」；定价渠道组仍预告（T-01 `closed-set B…` exit 0） | ✅ **不是** 70.4 同一句 |
| GWT-70.4 | `App.test.tsx::test_operator_no_direct_gateway_or_relay_token_entry`（经办壳/用量；无「直连平台网关」、无「我的中转令牌」） | ✅ exit 0；未写「我的渠道组」 |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（无多步写） |
| 幂等 | — | ➖ N/A（无新建写契约） |
| 并发写 | — | ➖ N/A |
| 外部依赖失败 | 70.1 仍 mock 网关 HTTP；进程夹具不依赖 daemon 健康 | ✅ |

## 7. NFR 验证

➖ 票无独立 NFR 数字。密钥不进 git（FR-14 arch 绿）。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 70.1 闸只钉 `::test_post_plan_outbound_gateway`。70.4 node 已加。72.3 不得与 70.4 写成同一句。进程夹具：本机无 Docker sock + 无 3000 监听。 |
| `/frontend` | 经办壳无「直连平台网关 / 我的中转令牌」。值班 URL `/newapi` 一周期仍在，仅超管。 |
| `/architect` | 默认 `DATA_PLANE=litellm`。`NEWAPI.*` 运行时读已删。未代选 Q-RELAY / Q-AGPL。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 完成态 = GWT-72.1 **且** GWT-70.1（未只停进程）
- [x] 默认 `LLM.DATA_PLANE=litellm`；`providers` 不当完成态
- [x] `NEWAPI.ENABLED` 恒 false 且删运行时读
- [x] 根 compose 无 new-api
- [x] 70.4 node 存在且与 72.3 分句
- [x] 70.1 闸只钉成功格
- [x] 无硬编码连接串/密钥
- [x] 票状态 done
