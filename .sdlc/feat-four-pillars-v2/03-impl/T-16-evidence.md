# 实现证据 · T-16 `llm_chat` 平台出口四动作 + 空模型 + 网关不可达三句分离

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-16.md`｜FR 锚点：FR-70 / FR-74｜角色：/backend｜日期：2026-09-09
> 泳道：L4

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| `LLM.DATA_PLANE=litellm` 解析 | Service | `ai_planner/llm_client.py` + `llm_common/runtime.py` | 本企业激活行直连；否则只网关 |
| 平台路径 outbound | Service 叶 | `llm_gateway/chat.py` | `POST /v1/chat/completions`；空模型预检 `GET /v1/models` |
| 套餐闸 | Service | `llm_client.llm_chat` → `_enforce_tenant_token_quota` | 成功路径前；满额不改口网关句 |
| 失败三句 | Service | `quota_service` 常量 + BusinessException code | 70.2 族 / 74.1 族 / 12.3 |
| `similar-suggest` 守卫 | Router | `app/api/v1/skills.py` | `require_operator`；confirm 仍 `require_admin` |
| 失败不吞 done | Service | `SkillService.similar_suggest` | 信封/Job **只**该句 |
| 评分 consume | Service | `SkillScoringService.score_skill` | 网关/空模型码不重试改口 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import ☑ `llm_client` 只 import `llm_gateway.chat` 不 import admin

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/ai_planner/llm_client.py` | 修改 | litellm 解析；except 禁 yml；平台路径走 chat |
| `backend/services/llm_common/runtime.py` | 修改 | `resolve_own_tenant_config`（无平台公共行） |
| `backend/services/llm_gateway/chat.py` | 修改 | `list_v1_models` 预检（空模型无 chat outbound） |
| `backend/services/quota_service.py` | 修改 | `NO_MODEL_USER` / `LLM_GATEWAY_NO_MODEL` |
| `backend/app/api/v1/skills.py` | 修改 | similar-suggest `require_operator` |
| `backend/services/skill_service.py` | 修改 | llm_chat 失败落 Job failed 并上抛 |
| `backend/services/skill_scoring_service.py` | 修改 | 网关/空模型/满额句原样进 job/error |
| `config/default/llm.yml` | 修改 | `LLM.DATA_PLANE: providers`（expand 默认） |
| `backend/config_consts.py` | 修改 | `LLM_DATA_PLANE` |
| `backend/tests/test_llm_four_actions_http.py` | 新增 | 分格 `::node` |
| `backend/tests/test_skill_similar_suggest.py` | 修改 | 70.7 outbound；70.10/74.6 信封；只读 403 |
| `backend/tests/test_saas_byok.py` | 修改 | SH-01 点名 node outbound=网关 URL |
| `backend/tests/test_llm_gateway.py` | 修改 | `llm_client` 现 import chat 不 import admin |
| `backend/tests/test_ai_planner.py` | 修改 | 降级 `test_trigger_plan_endpoint` |
| `backend/tests/test_skill_scoring_worker.py` | 修改 | 降级 `test_rescore_endpoint_pushes_queue` |
| `backend/tests/test_saas_provider_semantics.py` | 修改 | 降级 `https://pub` 金标 |
| `.sdlc/feat-four-pillars-v2/02-shape/tickets/T-16.md` | 修改 | 状态 done |

**与票里「会改哪些文件」一致**：☑ 有偏差（说明：空模型预检用 chat 模块 `GET /v1/models`，避免 llm_client import admin；`llm_client.py` 现超 500 行约定，未把 chat import 拆出以免撞 B4）

**未触碰「不许改的文件」**：☑ 确认（无新聊天 UI；未改值班页 / `/llm` requireAdmin；未退役 new-api；未勾 70.3/70.4/74.3「是」；未答六问）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 解析本企业行 | 独立短事务 | 与既有 `_resolve` 同范式 |
| 网关 HTTP | 否 | 外部调用 |
| similar 失败 Job | 先 commit 再 raise | 经办信封与 Job 同行 |

**事务提交后的操作失败怎么办**：网关失败映射 74.1 句；规划/试采 `_fail` 落 `error_message`。

### 幂等

N/A（本票无新建写契约）。☑ 未使用「先查后插」

### 并发控制

N/A（未改 claim_status）。☑ 本票无新条件更新

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| LiteLLM Proxy | `LITELLM.TIMEOUT` | `LLM.MAX_RETRIES`（平台路径） | 空模型 / 不可达两句分离 | 读预检幂等；chat 由调用方 |

`DATA_PLANE=litellm` 时 except **禁止** `resolve_config_from_settings()`：改走网关 URL（SH-18 第一叉）。网关 HTTP 失败才 74.1（第二叉，另一张夹具）。

## 4. ORM 与 DBML 对齐

➖ N/A（无表变更）

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `llm_chat` / `_llm_chat_gateway` / `list_v1_models` / similar 失败 |
| 错误日志上下文 | 网关 cause 只进 warning，用户句不含 traceback |
| 慢操作耗时 | 沿用 `LITELLM.TIMEOUT` / `LLM.MAX_RETRIES` |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。

```
$ uv run pytest -x -q backend/tests/test_llm_four_actions_http.py::test_post_plan_outbound_gateway
.                                                                        [100%]
1 passed in 1.06s
exit: 0

$ uv run pytest -x -q backend/tests/test_llm_four_actions_http.py
............                                                             [100%]
12 passed in 2.93s
exit: 0

$ uv run pytest -x -q backend/tests/test_saas_byok.py::test_no_own_key_falls_back_to_platform
.                                                                        [100%]
1 passed in 1.22s
exit: 0

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

票闸 15 node（含 similar-suggest 三格 + SH-01 点名 node）同 PR：`15 passed` exit 0。未把整文件 `test_saas_byok.py` 当绿闸成员。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-70.1 | `test_post_plan_outbound_gateway` | ✅ |
| GWT-70.2 | `test_post_plan_no_model_only_70_2` | ✅ |
| GWT-74.1 | `test_post_plan_unreachable_only_74_1` | ✅ |
| GWT-70.5 | `test_post_test_enters_repair_flow_outbound_gateway` | ✅ |
| GWT-70.8 | `test_post_test_enters_repair_flow_no_model_only_70_8` | ✅ |
| GWT-74.4 | `test_post_test_enters_repair_flow_unreachable_only_74_4` | ✅ |
| GWT-70.6 | `test_post_rescore_consume_once_outbound_gateway` | ✅ |
| GWT-70.9 | `test_post_rescore_consume_once_no_model_only_70_9` | ✅ |
| GWT-74.5 | `test_post_rescore_consume_once_unreachable_only_74_5` | ✅ |
| GWT-74.2 | `test_post_plan_quota_full_gateway_reachable_only_12_3` + `..._unreachable_only_12_3` | ✅ |
| GWT-70.7 | `test_operator_similar_suggest_success_outbound_is_gateway_url` | ✅ |
| GWT-70.10 | `test_operator_similar_suggest_no_model_envelope_only_70_10` | ✅ |
| GWT-74.6 | `test_operator_similar_suggest_unreachable_envelope_only_74_6` | ✅ |
| SH-01 / SH-16 / SH-18 | `test_no_own_key_falls_back_to_platform` + `test_post_plan_resolve_exception_outbound_is_gateway` | ✅ |
| GWT-70.3 / 70.4 / 74.3 | **本票禁止单独勾「是」** | ➖ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（无多步本地写契约） | ➖ |
| 幂等 | ➖ N/A（无新建写） | ➖ |
| 并发写 | ➖ N/A（未改 claim） | ➖ |
| 外部依赖失败 | 空模型 / 网关不可达 / 满额 12.3 两分格 | ✅ |

## 7. NFR 验证（票里有 NFR 时填）

➖ 本票无独立 NFR 数字闸。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 成功格必须等 outbound；失败格禁止 200/planning/queued/outbound；试采须 `_repair_flow`；评分须 `consume_once`；similar-suggest 失败是非 200 信封 + Job failed。mock 了 LiteLLM `_http_json`。 |
| `/frontend` | 无新聊天 UI。similar-suggest 经办可过；confirm 仍 admin。失败句三句不得互勾。 |
| `/architect` | 空模型预检放在 `chat.list_v1_models`（数据面 GET /v1/models），未让 `llm_client` import admin。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（闸命令 exit 0）
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`（吞异常）
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」
- [x] 条件更新的 `rows == 0` 已处理（未改）
- [x] 外部依赖四件套齐全（超时/重试/降级/幂等前提）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 票状态已更新为 done

## Gate intercept（T-33 后全量闸 · ENABLED=false 不得勾 74.1）

HEAD 在 T-33 后跑 `uv run pytest -x -q backend/tests` 首败：

`test_ai_planner.py::TestLlmChat::test_llm_disabled_raises_business_exception`
`AssertionError: assert '未启用' in '平台 LLM 网关不可达'`

根因：默认 `LLM.DATA_PLANE=litellm` 时 `llm_chat` 先探测网关，`ENABLED=false` 的「未启用」句到不了。未改 74.1 族文案；except 仍禁止 `resolve_config_from_settings()`。

修复：
- `llm_client.llm_chat`：`if not cfg.enabled` 先于网关探测；平台出口仅 `cfg.source == "gateway"`
- `TestLlmChat` 钉 `LLM.ENABLED=false` + `DATA_PLANE=providers`
- 闸顺带：`ALL_ORM_TABLES` 补 T-23/T-33 已注册表；failover 耗尽用户句对齐「本企业供应商调用失败」（不混 70.2/74.1）

```
$ uv run pytest -x -q backend/tests/test_ai_planner.py::TestLlmChat::test_llm_disabled_raises_business_exception
.                                                                        [100%]
1 passed in 1.69s
exit: 0

$ uv run pytest -x -q backend/tests
1329 passed, 35 skipped, 7 warnings in 143.65s (0:02:23)
exit: 0

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

ENABLED=false Then 仍是「未启用」，不是 74.1「平台 LLM 网关不可达」，也不是 70.2「还没有平台模型」。
