# 实现证据 · T-15 `llm_gateway/` 拆 chat vs admin；禁 DSN；禁 pyc；落地 B4 全表

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-15.md`｜FR 锚点：FR-70（基建）｜角色：/backend｜日期：2026-09-09
> 泳道：L4
> 闸：`bash tools/check/arch.sh`（票仍写 `scripts/check-arch.sh`，该路径已不在）

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| `POST /v1/chat/completions` | Service 叶 | `backend/services/llm_gateway/chat.py` | 仅该路径；httpx；虚拟 Key |
| 模型/部署/spend/budget HTTP | Service 叶 | `backend/services/llm_gateway/admin.py` | 与 chat 分模块 |
| 连接键 | Config | `config/default/litellm.yml` | `LITELLM.BASE_URL` / `TIMEOUT`；`MASTER_KEY` 走 .env |
| `__all__` 不同时含 chat+admin | 包 | `backend/services/llm_gateway/__init__.py` | `__all__ = []`，不 re-export |
| B4 全表 | 闸 | `tools/check/arch.sh` | 三条 grep 原文 + DSN/engine |
| R10 递归 | 闸 | `tools/check/arch.sh` | AST 扫 `backend/services/**/*.py` |
| 四动作解析 | **未改** | `ai_planner/llm_client.py` | 仍走 `_resolve_llm_runtime_config`；未 import chat |

**分层依赖核对**：☑ 无新 Router ☑ 无 ORM ☑ 无 Schema ☑ 未 resume `services/litellm/*.pyc` ☑ 未建 `power_market/` 业务

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/llm_gateway/__init__.py` | 新增 | `__all__ = []` |
| `backend/services/llm_gateway/_settings.py` | 新增 | BASE_URL / MASTER_KEY / TIMEOUT；`_http_json` |
| `backend/services/llm_gateway/chat.py` | 新增 | `chat_completions` → `POST /v1/chat/completions` |
| `backend/services/llm_gateway/admin.py` | 新增 | models / deployments / spend / budget HTTP |
| `config/default/litellm.yml` | 新增 | 非敏感默认；无 DSN |
| `.env.example` | 修改 | `AUTO_AGENTS_LITELLM__MASTER_KEY` 等注释 |
| `backend/config_consts.py` | 修改 | `LITELLM_BASE_URL` / `LITELLM_TIMEOUT` |
| `tools/check/arch.sh` | 修改 | B4 全表 + R10 递归 + 禁 DSN/engine |
| `.pre-commit-config.yaml` | 修改 | hook 名 B1–B4 |
| `backend/tests/test_llm_gateway.py` | 新增 | 文件存在 / `__all__` / HTTP 叶 / 未切 T-16 |
| `backend/services/ai_planner/_cooldown.py` 等 | 修改 | R10 递归后补入口 `logger.` |
| `backend/tests/test_spider_task_side_effects.py` | 修改 | 期望快照补 `tenant_id`（同树既有字段；pytest -x） |
| `.sdlc/feat-four-pillars-v2/02-shape/tickets/T-15.md` | 修改 | 状态 done |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：闸路径是 `tools/check/arch.sh` 不是 `scripts/check-arch.sh`；R10 递归要求给嵌套公开函数补 logger；pytest -x 需对齐同树 snapshot 的 `tenant_id`）

**未触碰「不许改的文件」**：☑ 确认（未改四动作解析；未把 `llm_chat` 挪出 `ai_planner/`；未建 `power_market/` 业务；未 resume pyc；未代选六问）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 网关 HTTP | 否 | 外部调用，无本地 OLTP 写 |

**事务提交后的操作失败怎么办**：N/A（无写路径）

### 幂等

N/A（本票无写库）。☐ 未使用「先查后插」

### 并发控制

N/A（无条件更新）

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| LiteLLM Proxy HTTP | `LITELLM.TIMEOUT`（默认 60s） | 本票不重试（T-16 出口再定） | `raise_for_status`；产品句 T-16 | 读幂等；budget POST 由调用方 |

backend 只持虚拟 Key（`LITELLM.MASTER_KEY`）。禁止 DSN。chat 与 admin 不合成单模块。

## 4. ORM 与 DBML 对齐

➖ N/A（无表）

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `chat_completions` / admin 各方法 `logger.info`（只记路径与 model，不记 Key） |
| trace_id | 沿用既有中间件 |
| 错误日志上下文 | httpx 异常上抛，不吞 |
| 慢操作耗时 | 本票无额外计时；超时走配置 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。

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

```
$ uv run pytest -x -q backend/tests/test_llm_gateway.py
........                                                                 [100%]
8 passed in 1.05s
exit: 0
```

```
$ uv run pytest -x -q backend/tests
1168 passed, 12 skipped, 7 warnings in 72.35s (0:01:12)
exit: 0
```

B4 grep（与 `arch.sh` 写死原文一致；`power_market/` 尚未建包，裸跑 exit 2，闸内 `2>/dev/null || true` 视为零命中）：

```
# power_market 禁这些前缀（含 llm_gateway）
grep -rnE '^(from|import) backend\.services\.(spider_|newapi_|litellm_|relay_|channel_|ai_planner|llm_gateway)' backend/services/power_market/

# ai_planner 只禁 admin（三模式）
grep -rnE 'from backend\.services\.llm_gateway\.admin|import backend\.services\.llm_gateway\.admin|from backend\.services\.llm_gateway import admin' backend/services/ai_planner/

# ai_planner 除 llm_client.py 禁 chat（三模式）
grep -rnE 'from backend\.services\.llm_gateway\.chat|import backend\.services\.llm_gateway\.chat|from backend\.services\.llm_gateway import chat' backend/services/ai_planner/ --exclude=llm_client.py
```

本机裸跑：power_market 目录不存在 → grep exit 2；ai_planner 两条零命中 → grep exit 1。闸 exit 0。

### 验收项逐条对应

| Then | 覆盖的测试 | 结果 |
|---|---|---|
| B4 全表已绿 | `bash tools/check/arch.sh` + `test_arch_sh_has_verbatim_b4_greps` | ✅ |
| chat.py / admin.py 存在且非 pyc-only | `test_gateway_source_files_exist` | ✅ |
| `__all__` 不同时含 chat 与 admin | `test_init_all_does_not_export_chat_and_admin_together` | ✅ |
| 适配叶可被 `llm_client` import chat | `test_chat_is_importable_for_llm_client`（本票未改 llm_client 出口） | ✅ |
| 未切四动作解析 | `test_llm_client_not_switched_to_gateway_chat` | ✅ |
| 禁 DSN / engine | arch B4 DSN/engine + `test_chat_and_admin_are_separate_modules` | ✅ |
| R10 递归 | arch R10 | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（无多步写） |
| 幂等 | — | ➖ N/A（无写库） |
| 并发写 | — | ➖ N/A（无并发写） |
| 外部依赖失败 | httpx `raise_for_status`；MockTransport 钉路径 | ✅ 路径契约；失败映射留给 T-16 |

## 7. NFR 验证（票里有 NFR 时填）

本票无独立 NFR 数字。NFR-10 故障域由 T-14 compose 提供，本票只 HTTP。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 本票不勾 GWT-70.* 产品格。夹具：`from backend.services.llm_gateway.chat import chat_completions` 合法；`llm_client.py` 仍走旧 resolve。Mock 了 LiteLLM HTTP。 |
| T-16 | 把 `llm_chat` 出口接到 `chat_completions`；`DATA_PLANE=litellm` 解析顺序仍归 T-16。允许 `llm_client.py`：`from backend.services.llm_gateway.chat import ...` |
| T-18/T-19 | 只 import `llm_gateway.admin`（list_models / list_deployments / spend / budget） |
| T-21 | B4 已绿；建 `power_market/` 时 `grep -rn llm_gateway backend/services/power_market/` 须零命中 |
| `/architect` | 无新错误码。闸路径以 `tools/check/arch.sh` 为准 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿
- [x] 契约落位表已核对，分层无违规
- [x] 无 ORM/DBML 变更
- [x] 无硬编码连接串/密钥/端口（默认 URL 在 yml）
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`
- [x] 日志已脱敏
- [x] 事务里无外部调用（无事务）
- [x] 发现的上游问题已回报：闸脚本路径是 `tools/check/arch.sh`
- [x] 票状态已更新为 done
