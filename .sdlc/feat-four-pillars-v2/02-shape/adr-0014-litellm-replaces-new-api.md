# ADR-0014：平台 LLM 数据面 = LiteLLM Proxy；new-api 退出运行时

> 状态：**accepted**（**OVERTURN** 旧特征「LiteLLM 替换不进本特征 / new-api 保持旁路」）
> 日期：2026-09-08｜决策者：/architect｜相关：Q-LLM 已决；FR-70…75；FR-12；FR-06/07/14；`01-define/diagnosis/litellm-replace-newapi.md`

## 背景

操作者关闭 Q-LLM：LiteLLM 必须替换 new-api，且必须重构。旧 ADR-0014 把替换排除出本特征，会使切换落入 Wave 3 / FR-60 stub（租户产品面，阻塞 Q-RELAY）而永不做。现网是三条叙事、两套未接线资产：规划走 `llm_chat` → `llm_providers`/yml；值班走 `NewapiApiClient` + 可选 `NEWAPI.DB_DSN` SQL；`deploy/litellm/config.gen.yaml` 被 git 跟踪且含明文 Key，**没有** LiteLLM 进程。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 平台路径四动作同一解析顺序 | FR-70 / FR-73；QA-36 |
| new-api 退出运行时，不是长期双通道 | FR-72；spec §0 X-FR36 |
| backend 禁止网关 DSN | 诊断 §3.4；今日 `channel_scheduler_service.py` `_USAGE_SQL` |
| BYOK 直连，不要求网关存活 | FR-73；GWT-06.5 |
| 套餐闸在成功路径前；网关挂 ≠ 套餐句 | FR-12 / FR-74 |
| 密钥不进 git | FR-14 / FR-75 |
| 不发租户虚拟令牌、不造「我的渠道组」 | Q-RELAY 未关；X-SLICE |

## 决策

1. **数据面（`LLM.DATA_PLANE=litellm`）**：解析 **只**两段——有本企业激活行 → 直连该行 `base_url`（不经网关、不打平台供应商、不打 new-api）；**否则只**经 `llm_chat` 打 LiteLLM Proxy `POST /v1/chat/completions`。禁止第三段：平台公共 `llm_providers`（`tenant_id` NULL）直连、yml/env `LLM.BASE_URL` 直连、手填 new-api URL。`DATA_PLANE=litellm` 时 `_resolve_llm_runtime_config` 的 except **禁止** `resolve_config_from_settings()`（应失败成 74.1 句，或仍解析到网关 URL）；禁止 resolve 抛错落到 yml/env / `https://pub`。同 PR 测试必须正断言：resolve 抛错后 outbound **是**网关 URL，**或**该次结果 **只**「平台 LLM 网关不可达」。禁止只做「不是 pub / 不是 yml」。不要把「或」写成 `in{74.1句, 网关URL}` 去勾 70.1 与 74.1 两格。`DATA_PLANE=providers` **仅** expand 回滚窗，不是完成态。禁止第四条调用链。`ai_planner/` **只禁** import `llm_gateway.admin`（grep 写死三模式，见 ADR-0010）；**允许** `llm_client.py` import `llm_gateway.chat`。禁止「规划器禁 import 网关管理客户端」散文。
2. **部署**：`deploy/litellm/` 独立 compose + 自有 Postgres（虚拟 Key / spend / 模型配置）+ 需要多副本时才起自有 Redis。根 compose 不声明该服务（ADR-0010）。backend 只持 **网关虚拟 Key**，上游 Key 只活在 LiteLLM 密钥面。
3. **适配叶**：新建 `backend/services/llm_gateway/`（httpx），**拆两个模块**（落地 T-15）：
   - `llm_gateway/chat.py` — 仅平台路径 `POST /v1/chat/completions`
   - `llm_gateway/admin.py` — 模型/部署/spend/budget 管理 HTTP
   `llm_gateway/__init__.py` 禁止把 `chat` 与 `admin` 打进同一 `__all__`。值班/探针（T-18/T-19）只 import `admin`。`llm_chat`（`ai_planner/llm_client.py`）只 import `chat`。**禁止** resume `backend/services/litellm/*.pyc`。**禁止** `LITELLM.DB_DSN` / `create_async_engine` 打网关库。用量/窗口优先映射网关 budget + 管理 HTTP；盖不住的「冷却到期自动恢复且不覆盖人工禁用」**只留这一条**在 backend，仍走 HTTP。
4. **值班**：超管页列表来自 LiteLLM 模型/部署。管理面不可达：HTTP 200 + `available=false` 类降级信封（禁止 500 拖死页；禁止「暂无渠道」）。`/api/v1/newapi` 与前端 `/newapi` **保留一个发布周期**（b1c 锁信封）。探针 10 维指纹留 backend，调用网关 `/v1/chat/completions`，伪装 **不**自动关（GWT-07.6）。
5. **配置名（全仓这一处）**：网关连接 = `LITELLM.BASE_URL` / `LITELLM.MASTER_KEY` / `LITELLM.TIMEOUT`。切换旗标 = `LLM.DATA_PLANE` ∈ {`providers`, `litellm`}。**T-20 完成后默认 `litellm`**。值班产品规则（窗口/探针）expand 期读 `NEWAPI.*`，新键 `RELAY.*`；contract 后只留 `RELAY.*`。禁止第三套前缀。
6. **切换窗**：expand 短双跑（new-api 可启作回滚件，`LLM.DATA_PLANE=providers` 可回）。**完成态** = 默认 `LLM.DATA_PLANE=litellm` + new-api **进程停止** + GWT-72.1 **且** GWT-70.1（无自有行 outbound = 网关 URL，不是平台公共行 `https://pub`）。短双跑不是卖点，不进 Non-Goal 以外的「长期架构」。只停 new-api、规划仍打平台公共 `llm_providers` / yml = 未完成。
7. **观察点（禁止空心句）**：平台路径成功 = 该次出现在 **网关侧**调用或用量，且不打本企业供应商直连、不打平台供应商直连、不打 new-api。BYOK 成功 = 出现在 **本企业供应商侧**调用或用量，不出现在网关侧。**成功格**测试钉捕获的 outbound URL。**失败格**观察点 = 该次结果上与**该格** GWT 同一句。按 GWT 拆开（与 §7.2 括号、第四 When 同一写法；禁止无绑定的「或」）：**70.2/70.8/70.9 Then 只**「还没有平台模型」（规划/试采：计划 `status=failed` 且 `error_message` **只**该句；评分：job/响应 **只**该句）；**74.1/74.4/74.5 Then 只**「平台 LLM 网关不可达」（规划/试采：计划 `status=failed` 且 `error_message` **只**该句；评分：job/响应 **只**该句）。**70.10/74.6 写到与 70.9 同级**：经办 HTTP 响应（及 Job）**只**该格那一句（**70.10 Then 只**「还没有平台模型」/`LLM_GATEWAY_NO_MODEL`；**74.6 Then 只**「平台 LLM 网关不可达」/`LLM_GATEWAY_UNREACHABLE`）。禁止 HTTP 200 + 空 `clusters` 勾 70.10/74.6。禁止只断言 `SkillJob status≠done`。**不得互勾**（禁止 `error_message in {空模型句, 网关句}` 一张夹具勾两格）。失败格 **禁止** 用 outbound 当 oracle。禁止 HTTP 200 / `status=planning|testing` / `queued=true` 勾失败格。用户可见失败三句不得互勾：还没有平台模型 / 平台 LLM 网关不可达 / 已达配额上限。
8. **MCP**：`mcp_bridge.call_tool` 仍只验证抽样，不经 LiteLLM 当 Agent 运行时。
9. **租户浏览器** 禁止直连网关端口。Q-RELAY 未关：无「我的中转令牌」、无「我的渠道组」。换网关 **不等于** 定价 B2 当前可买。

镜像 tag **本 ADR 不代选**（禁 `:latest`），交 `/sre` 钉死。

## 备选与否决理由

### 备选 A：替换不进本特征；new-api 保持旁路（旧 ADR-0014）

**否决理由**：Q-LLM 已决「必须重构」。旁路与规划零引用，值班页对关着的 new-api 降级，会造成「看起来有中转、规划仍直连上游」。

### 备选 B：把切换写成 Wave 3 / FR-60 stub

**否决理由**：FR-60 阻塞 Q-RELAY（租户产品面）。数据面与 SKU 不是同一件事。写成 stub = 静默永不做（spec X-FR36）。

### 备选 C：长期双通道（规划走 provider，中转另开当卖点）

**否决理由**：操作者要求退出运行时。切换窗允许短双跑作回滚，切完必须停 new-api。

### 备选 D：把 LiteLLM Python SDK 嵌进 FastAPI 进程内路由

**否决理由**：上游 Key 回到 backend 内存，毁掉数据面边界。用 httpx 打 Proxy。

### 备选 E：调度器继续 `NEWAPI.DB_DSN` / 复制为 `LITELLM.DB_DSN`

**否决理由**：LiteLLM spend 在自有 Postgres，官方契约是 `DATABASE_URL` 给 **网关进程**，不是给 backend。外部表结构不可控（与今日 `created_at` 类型债同类）。合同禁止 backend 持网关 DSN。

### 备选 F：一刀切「全部调用进中转」，含 BYOK

**否决理由**：GWT-06.5 / FR-73 已冻本企业行直连；网关挂时 BYOK 仍须能保存与调用。强迫租户 Key 上传网关 = 另开 Q-RELAY FR。

### 备选 G：resume `services/litellm/*.pyc` 或 `export_litellm_config.py` 残骸

**否决理由**：树内无对应 `.py`、无 git 删除史可还原。按新客户端重写。

### 备选 H：并进根 compose / 与平台 MySQL 共用网关库

**否决理由**：见 ADR-0010 备选 B；双引擎 + 双密钥域 + SALT 不可轮换。

### 备选 I：无本企业行则平台公共 `llm_providers` / yml 直连（现网三段）

现网 `resolve_runtime_config`：本租户激活行 → 平台公共行（`tenant_id` NULL）→ yml/env。`test_no_own_key_falls_back_to_platform` 金标 `base_url == "https://pub"`。

**否决理由**：GWT-70.1 要求无自有行打 LiteLLM，**不打平台供应商直连**。三段解析与「平台路径只经网关」互否。`DATA_PLANE=litellm` 时该测试必须改写：无自有行 outbound = 网关 URL，不是 `https://pub`。保留三段 = Wave L 未完成。

### 备选 J：把 `llm_chat` 挪出 `ai_planner/`（SH-08 的 OR）

**否决理由**：存量 patch 路径整片红。拆 `chat.py` vs `admin.py` 后 B4 只禁 admin、允许 `llm_client` import chat，不必搬家。

### 备选 K：第四 When 用「测试内直接调 `llm_chat`」勾 GWT-70.7 族

**否决理由**：经办 HTTP 可空过（SH-07）。When 必须是经办能过的 HTTP（`require_operator`）。坚持 `similar_suggest`：同票改守卫 + 去掉吞异常；Then 与 70.10/74.6 同一句；只是 70.7 执行夹具，不是聊天产品。禁止新建聊天 UI。

### 备选 L：T-16 只锁第四 When HTTP；入队 200 勾 70.1/70.5/70.6；用 similar-suggest 勾规划/试采/评分

**否决理由**：现网 `/plan` `/test` `asyncio.create_task` 立即返回 snapshot；`/{name}/rescore` `enqueue_rescore` 立即 queued。只锁 similar-suggest 则规划/试采/评分空过（SH-12）。T-16 Then 分四条 When 各钉现网 HTTP：`POST /api/v1/ai/plans/{id}/plan`、`POST /api/v1/ai/plans/{id}/test`、`POST /api/v1/skills/{name}/rescore`、`POST /api/v1/skills/similar-suggest`。**成功格**异步/入队必须等到 outbound URL。禁止用第四夹具勾 70.1 / 70.5 / 70.6 族。

### 备选 M：失败格（70.2/70.8/70.9、74.1/74.4/74.5）用 HTTP 200 / `planning|testing` / `queued` 勾，或用 outbound 当 oracle

**否决理由**：现网 `/plan` `/test` 立即 snapshot，`/rescore` 立即 queued；空模型没有 outbound。第四 When 已钉 Then = 该格 GWT 同一句。T-16 把这些格与第四 When 对齐：When = 该动作自己的 HTTP；Then = 等到该次结果上出现与**该格** GWT 同一句。成功格继续等 outbound；失败格禁止 outbound 当 oracle。禁止 HTTP 200 / `status=planning|testing` / `queued=true` 勾这些格（SH-13）。失败句按 GWT 拆开见备选 O（SH-15）。

### 备选 N：试采第一次成功 / 评分只入队即可勾 70.5/70.6 族

**否决理由**：`_execute_test` 第一次通过则不进 `_repair_flow`，不打 `llm_chat`。`SKILLS.SCORING.ENABLED` 默认关，`/rescore` 只入队。与 ≥2 同 category 对称：试采夹具必须第一次失败并进入 `_repair_flow`，否则不得勾 70.5/70.8/74.4（及 T-17 的 73.7/73.10）；评分夹具必须 `consume_once`（或打开 `SKILLS.SCORING.ENABLED` 并等到消费），否则不得勾 70.6/70.9/74.5（及 73.8/73.11）（SH-14）。

### 备选 O：T-16 Then 把 70.2 与 74.1 写成无绑定的「或」（`in{空模型句, 网关句}` 一张夹具勾两格）

票表丢掉 §7.2 括号，写成 `error_message` 为 A 或 B。

**否决理由**：spec 不得互勾；§7.2 括号绑定（空模型句 vs 网关不可达句）；第四 When 已拆。T-16 票表、本 ADR 观察点与抄票清单按 GWT 拆开：70.2/70.8/70.9 Then **只**「还没有平台模型」；74.1/74.4/74.5 Then **只**「平台 LLM 网关不可达」；写进不得互勾。与 §7.2 括号、第四 When 同一写法。禁止无绑定的「或」（SH-15）。

### 备选 P：`DATA_PLANE=litellm` 时 `_resolve_llm_runtime_config` except 仍 `resolve_config_from_settings()`（yml/env / `https://pub`）

现网 `llm_chat` 走 `_resolve_llm_runtime_config`：resolve 抛错则 `return resolve_config_from_settings()`。T-16 只作废 `resolve_runtime_config` 三段 + `https://pub` 金标，未钉该缝。

**否决理由**：SH-01 杀掉三段解析，但 `llm_chat` 真入口 except 仍 yml/env 直连，空过 GWT-70.1 / 可落到 `https://pub`。T-16 Then：`DATA_PLANE=litellm` 时 except **禁止** `resolve_config_from_settings()`（应失败成 74.1 句，或仍解析到网关 URL）。同 PR 加测试：resolve 抛错时不得落到 yml/env / `https://pub`（SH-16）。正断言见备选 R（SH-18）。

### 备选 Q：70.10/74.6 Then 只锁句子和「Job 非 done」，不锁经办 HTTP 落点

similar-suggest 现网恒 200 + 空 `clusters`。T-16 测试清单只写「失败非 done」。经办看见的是响应，不是 Job 行。只断言 `SkillJob status≠done` 或 HTTP 200 + 空 `clusters` 可勾 70.10/74.6。

**否决理由**：70.9 已是 job/响应 **只**该句。70.10/74.6 必须同级：经办 HTTP 响应（及 Job）**只**该格那一句（`LLM_GATEWAY_NO_MODEL` / `LLM_GATEWAY_UNREACHABLE`）。禁止 HTTP 200 + 空 `clusters` 勾 70.10/74.6。禁止只断言 `SkillJob status≠done`。同票改 `test_skill_similar_suggest.py`：失败格断言信封/正文 **只**该句，不是 done、不是空成功（SH-17）。

### 备选 R：同 PR 测试只做负向「不是 pub / 不是 yml」，或把「或」写成 `in{74.1句, 网关URL}` 勾 70.1 与 74.1

except 可返回空配置、不调 `resolve_config_from_settings()`，负向测试仍绿，两个允许结果都不出现。一张夹具 `in{74.1句, 网关URL}` 可同时勾 70.1 与 74.1。

**否决理由**：同 PR 测试必须正断言：resolve 抛错后 outbound **是**网关 URL，**或**该次结果 **只**「平台 LLM 网关不可达」。禁止只做「不是 pub / 不是 yml」。不要把「或」写成 `in{74.1句, 网关URL}` 去勾 70.1 与 74.1 两格。该「或」是 except 路径两个允许实现结果：一张夹具只钉其中一个（SH-18）。

## 证据

```
读码：backend/services/ai_planner/llm_client.py llm_chat → POST {base}/chat/completions（OpenAI 方言已对齐）
读码：backend/services/llm_common/runtime.py 三段：本租户激活行 → 平台公共行 → yml/env
读码：backend/tests/test_saas_byok.py test_no_own_key_falls_back_to_platform 金标 https://pub（T-16 同 PR 作废）
读码：llm_chat 余下调用方 SkillService.similar_suggest（POST /api/v1/skills/similar-suggest，现网 `require_admin`，`except Exception` 后 SkillJob status=done + `return {"clusters": clusters}`，失败时常空；HTTP `return ok(data=result)` 恒 200）。全仓无 C 端聊天页。`test_skill_similar_suggest.py` 只钉成功 200 + clusters。第四 When 锁经办 HTTP：同票改 `require_operator`、去掉吞异常；**SH-17**：70.10/74.6 写到与 70.9 同级：经办 HTTP 响应（及 Job）**只**该格那一句；禁止 HTTP 200 + 空 `clusters`；禁止只断言 `SkillJob status≠done`；同票改 `test_skill_similar_suggest.py` 失败格断言信封/正文 **只**该句，不是 done、不是空成功。禁止「或测试内 llm_chat」勾 70.7 族；该端点只是 70.7 执行夹具，不是聊天产品
读码：POST /api/v1/ai/plans/{id}/plan 与 /test 现网 require_operator + create_task 立即 snapshot；POST /api/v1/skills/{name}/rescore 现网 require_operator + enqueue_rescore 立即 queued。T-16 Then 分四条 When 各钉上述 HTTP；成功格等到 outbound URL；禁止用第四夹具勾 70.1/70.5/70.6 族
读码：orchestrator._execute_plan / _execute_test 失败走 `_fail`（`status=failed` + `error_message`）；空模型没有 outbound。失败格 Then = 该次结果上与**该格** GWT 同一句，禁止 HTTP 200 / planning|testing / queued / outbound 勾 70.2/70.8/70.9、74.1/74.4/74.5（SH-13）。SH-15：按 GWT 拆开，70.2/70.8/70.9 Then **只**「还没有平台模型」；74.1/74.4/74.5 Then **只**「平台 LLM 网关不可达」；不得互勾；禁止无绑定的「或」
读码：_execute_test 第一次通过则 return，不进 `_repair_flow`（不打 llm_chat）；SkillScoringService.enqueue_rescore 只 lpush；SKILLS.SCORING.ENABLED 默认 false；consume_once 才 score_skill → llm_chat。试采夹具必须第一次失败进 `_repair_flow`；评分夹具必须 consume_once（或开开关等到消费）（SH-14）
读码：llm_client.py `_resolve_llm_runtime_config` except Exception → `return resolve_config_from_settings()`（yml/env）。`llm_chat` 真入口走该函数。`DATA_PLANE=litellm` 时该 except **禁止**该回退（SH-16）：应失败成 74.1 句，或仍解析到网关 URL。**SH-18**：同 PR 测试必须正断言：resolve 抛错后 outbound **是**网关 URL，**或**该次结果 **只**「平台 LLM 网关不可达」。禁止只做「不是 pub / 不是 yml」。不要把「或」写成 `in{74.1句, 网关URL}` 去勾 70.1 与 74.1 两格
读码：NewapiApiClient 引用仅 newapi/channel_*；规划器零引用
读码：check_llm_tokens_month 仅测试引用（Wave 0 T-09 接线，与本 ADR 解耦）
读码：channel_scheduler_service.py NEWAPI.DB_DSN + _USAGE_SQL
读码：git ls-files deploy/litellm/config.gen.yaml；services/litellm 仅 pyc
读码：test_b1c_newapi_channels_coverage.py 文首预期「newapi 模块将被 LiteLLM 替换」；信封可迁
无容器 spike：镜像 tag 与 spend HTTP 覆盖窗口冷却 → T-14/T-19 只读核对；失败则缩小调度器，不回退 DSN
```

## 代价与风险

| 代价 | 缓解 |
|---|---|
| 切换窗最多三套库 | 窗短；禁止平台 MySQL 兼网关库；new-api 停后剩两套 |
| `LITELLM_SALT_KEY` 不可轮换 | 生成一次进 secret manager；runbook「先导出模型再动 SALT」 |
| `/health/deep` 不因网关挂变红 | 有意：数据面挂主站仍 200；可选独立 ready，liveness 不杀 API |
| 回滚未实测 | 交付清单不得勾「可回滚」除非演练；expand 期内关 `LLM.DATA_PLANE` |
| new-api AGPL 面消失 | **影响陈述、不代选 Q-AGPL**：运行时不再绑其 AGPL。对外收费故事仍待 Q-AGPL |
| 误用 Enterprise Org | Wave L 只用 OSS（Key/team/spend）。Org/SSO 绑 Q-RELAY |

**最终一致**：网关 spend 与主库 `llm_token_usage` 不是同一本账（套餐文案 ≠ 成本熔断）。可接受延迟 = 一次调用 round-trip 内套餐闸已在调用前完成；spend 仅值班/窗口。不对账到租户账单（Q-BILL 未关）。

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/backend` | 适配叶拆 `chat.py`/`admin.py`、`llm_chat` 出口、删 DSN、lifespan 探针改 URL、B4 grep 写死（ai_planner 只禁 admin）；`DATA_PLANE=litellm` 时 `_resolve_llm_runtime_config` except **禁止** `resolve_config_from_settings()`；similar-suggest 失败格经办 HTTP 响应（及 Job）**只**该格那一句（禁 200+空 `clusters`、禁只断言 ≠done） |
| `/frontend` | 值班空态/降级句；预设去 new-api 字样；菜单仍超管；URL 一周期不改 |
| `/sre` | 独立 compose、钉 tag、网络、密钥注入、退役步骤、墓碑文档 |
| `/dba` | `gateway_ref` expand；**不**把 LiteLLM Prisma 表写入 `platform_core/models` |
| `/qa` | 四动作 × 平台路径/BYOK/空模型/网关不可达，**各钉该动作现网 HTTP**（规划 `/ai/plans/{id}/plan`、试采 `/ai/plans/{id}/test`、评分 `/skills/{name}/rescore`、聊天 `/skills/similar-suggest`）；**成功格**等到 outbound URL，禁止入队 200 勾 Then；**失败格按 GWT 拆开**：70.2/70.8/70.9 Then **只**「还没有平台模型」；74.1/74.4/74.5 Then **只**「平台 LLM 网关不可达」；写进不得互勾；与 §7.2 括号、第四 When 同一写法；禁止无绑定的「或」；禁止 HTTP 200 / `planning|testing` / `queued` / outbound 勾这些格；试采夹具必须第一次失败进 `_repair_flow` 否则不得勾 70.5/70.8/74.4/73.7/73.10；评分夹具必须 `consume_once`（或开 `SKILLS.SCORING.ENABLED` 等到消费）否则不得勾 70.6/70.9/74.5/73.8/73.11；**禁止**用第四夹具勾 70.1/70.5/70.6 族；GWT-72.1 夹具=进程已停；GWT-70.1 与 T-20 同勾；70.7/70.10/74.6/73.9/73.12 夹具=经办 `POST /api/v1/skills/similar-suggest`（`require_operator`；失败不得吞成 done；**70.10/74.6 与 70.9 同级**：经办 HTTP 响应（及 Job）**只**该格那一句；**70.10 Then 只**「还没有平台模型」；**74.6 Then 只**「平台 LLM 网关不可达」；不得互勾；禁止 HTTP 200 + 空 `clusters`；禁止只断言 `SkillJob status≠done`；同票改 `test_skill_similar_suggest.py`：失败格断言信封/正文 **只**该句，不是 done、不是空成功）；**禁止**测试内 `llm_chat` 勾这些格；禁止新建聊天 UI；该端点只是 70.7 执行夹具，不是聊天产品；`DATA_PLANE=litellm` 时 except 禁 `resolve_config_from_settings()`；同 PR 测试必须正断言：resolve 抛错后 outbound **是**网关 URL，**或**该次结果 **只**「平台 LLM 网关不可达」；禁止只做「不是 pub / 不是 yml」；不要把「或」写成 `in{74.1句, 网关URL}` 去勾 70.1 与 74.1 两格 |
| `/ops` | 值班 runbook；不指定人名（Q-OPS-DUTY） |

## 后续复审条件

Q-RELAY 关闭且要发租户虚拟令牌 / 渠道组屏；或 OSS spend HTTP 长期盖不住窗口产品规则；或 LiteLLM 许可证/Enterprise 边界变化——另开 ADR。不得借复审把 new-api 请回运行时。

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-08 | proposed → accepted | v2 重写并 OVERTURN 旧「替换不进本特征」。KEEP：`llm_chat` 单入口、闸在前、mcp 仅验证、伪装不熔断 |
| 2026-09-08 | accepted（补） | SH-01：否决备选 I（无本企业行→平台公共 llm_providers / yml 直连）。完成态 = 默认 DATA_PLANE=litellm + GWT-72.1 ∧ GWT-70.1 |
| 2026-09-08 | accepted（补） | SH-07/SH-08：适配叶拆 chat.py vs admin.py；70.7 夹具=经办 POST similar-suggest（require_operator，失败不吞 done，删测试内 llm_chat 可勾）；否决备选 J/K |
| 2026-09-08 | accepted（补） | SH-12：T-16 Then 分四条 When 各钉现网 HTTP；异步/入队等到 outbound URL；禁止用第四夹具勾 70.1/70.5/70.6 族；否决备选 L |
| 2026-09-08 | accepted（补） | SH-13：失败格与第四 When 对齐（Then=该次结果 GWT 同一句；禁 200/planning/queued/outbound oracle）。SH-14：试采须进 `_repair_flow`；评分须 `consume_once`。否决备选 M/N |
| 2026-09-08 | accepted（补） | SH-15：观察点/T-16 按 GWT 拆开：70.2/70.8/70.9 Then **只**「还没有平台模型」；74.1/74.4/74.5 Then **只**「平台 LLM 网关不可达」；写进不得互勾；禁止无绑定的「或」。否决备选 O。SH-16：`DATA_PLANE=litellm` 时 `_resolve_llm_runtime_config` except **禁止** `resolve_config_from_settings()`（应失败成 74.1 句，或仍解析到网关 URL）；同 PR 测试 resolve 抛错不得落到 yml/env / `https://pub`。否决备选 P |
| 2026-09-08 | accepted（补） | SH-17：70.10/74.6 写到与 70.9 同级：经办 HTTP 响应（及 Job）**只**该格那一句；禁止 HTTP 200 + 空 `clusters`；禁止只断言 `SkillJob status≠done`；同票改 `test_skill_similar_suggest.py` 失败格断言信封/正文 **只**该句。否决备选 Q。SH-18：同 PR 测试必须正断言 resolve 抛错后 outbound **是**网关 URL，**或**该次结果 **只**「平台 LLM 网关不可达」；禁止只做「不是 pub / 不是 yml」；不要把「或」写成 `in{74.1句, 网关URL}` 去勾 70.1 与 74.1。否决备选 R |
