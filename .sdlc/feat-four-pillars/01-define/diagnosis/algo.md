# 算法诊断 · feat-four-pillars（刷新）

> 角色：algo（评估集 / 模型选型 / 降级链 / RAG；不写业务 CRUD、不写 UI、不写基础设施）
> 日期：2026-09-07｜版本：refresh-2（定义帽；对照冻结 `spec.md` v1 + 现网代码复核）
> 泳道：L4 · `feat-four-pillars`
> 上游：本目录上一稿 `algo.md` · `spec.md` · `metrics-blueprint.md` · `/Users/xuyun/Documents/grok-files/power-market-design.md`（Accepted，D1–D21）· 仓库 `backend/services/ai_planner*` / `llm_*` / `skill_scoring*` / `mcp_bridge.py` / `channel_probe_service.py` · `backend/tests` 中 LLM 相关用例 · 宪法 `sdlc.config.yaml` → `.claude/rules/project_rule.md`
> 下游：`/pm`（质量承诺边界）· `/architect`（是否引入向量库 / 新 LLM SDK / ADR）· `/backend`（调用契约、配额闸、降级第三层）· `/qa`（评估脚本与下限）· `/sre`（成本告警）· `/analyst`（离线 vs 线上分叉）
> **红线**：无评估集版本的效果数字视为无效；未跑评估阶梯不得点名厂商/模型为「选定」。本帽不实现代码、不建评估集文件（spec T-23：满 50 条并报准确率 = **下一轮**）。

---

## 0. 一句话结论

平台已有 **5 条线上推理面**（采集规划、试采修复、资产评分、相似聚类、中转站真伪探针）+ **1 条非 LLM 连通抽样**（MCP verify）+ **1 条启发式质量分**，但 **0 份版本化评估集、0 次基线阶梯、0 次 prompt 回归、0 条 RAG 管线**。智能采集的「试采通过」、Power Market 的「AI 建议分 / tier」、插件「healthy」、渠道「original/spoofed」目前都是 **无标签的代理指标**。

四支柱里 AI 能交付的上限，被「scoring-without-eval」卡住，而不是被缺某个模型卡住。

**当前评估集条数 = 0。效果数字不可报。不得在本诊断中选定任何供应商。**

冻结 spec 已吸收上一稿的产品边界，algo 不再重开：

| spec 已冻 | 对 algo 的含义 |
|---|---|
| FR-72 | 注册仍须最近一次试采通过 + 人工确认；**官网不得写准确率百分比** |
| FR-10 | 套餐 `llm_tokens_month` 必须挡住真 `llm_chat`（规划 / 修复 / 评分）；今日 **未接线** |
| FR-61 | 探针判「伪装」**不**自动下线渠道；verdict 在评估达标前保持旁路 |
| T-23 / §9 | 评估集满 50 条并报准确率 = **下一轮**；目录契约可并行，**不挡 Wave 0** |
| NFR-06 | 评估集/爬取版权不进 Wave 0/1 |
| Q-LLM | 长期网关（LiteLLM vs new-api vs 现状）**本 PRD 不选**；Wave 0/1 规划只走 `llm_providers`（ADR-0014 意图，02-shape 标 stale 但不改这条冻结） |
| 度量蓝图 | `quality_score`、技能平均分、探针伪装次数 **禁止当 OEC** |

---

## 0.1 相对上一稿：复核后改了什么

| 项 | 上一稿 | 本刷新（代码复核） |
|---|---|---|
| HTML 注释注入 | 对抗层样本写「注释里藏指令」 | **注释在 `_clean_html_sync` 已被剥掉**（`_HTML_COMMENT`）。剩余注入面 = 可见 HTML 文本 + 用户 `html_snippet` 无数据区隔离 |
| `javascript:` 选择器 | 列入对抗样本 | schema `_XSS_PATTERNS` 已拒 `javascript:` / `<script` / `onerror=` / `onload=`。对抗应改测「隐藏节点可见文本改写系统指令」与「合法 css 过宽」 |
| 能力广场搜索 | 未单列 | `CapabilityService.list_assets(q=)` 只 `name LIKE`；**公开** `GET /public/capabilities` **不传 q**。技能公开面有 `q`（name/title/description `LIKE`）。`origin_local_name` **仓库零命中** |
| 温度 | 规划 `TEMPERATURE: 0.2` | **仅 openai_compatible 路径写入 payload**。anthropic / gemini 适配器 `build_chat` 不收温度；gemini 还把 `role=system` 塞进 `contents`（原生协议要 `systemInstruction`） |
| 评分预算 | 提到独立 `budget_override` | `SKILLS.SCORING.MAX_TOKENS_BUDGET: 0` → 代码把 0 当成「不覆盖」→ **走全局 20 万**，不是「评分不限」也不是「评分独立闸」 |
| MCP 无工具链 | 设计拟加 `unknown` | 扫描落库 `health_status=unknown`（`test_mcp_bridge`）；`verify_plugin` 无 `mcp_servers` 写 **`degraded`**。`verify_plugin_server` 在 list≥1 后 **无论 sample.ok 都标 healthy** |
| 评估集落地波次 | 定义帽排目录契约 | spec 明确：满 50 + 报准确率下一轮；Wave 0 只允许 **空目录契约**，禁止对外报分 |
| 探针 | 建议先扩题再动阈值 | 与 FR-61 / 度量蓝图一致：伪装次数不是北极星；0.15 阈值测试锁死但无金标渠道 |

未改的主结论：0 评估集、不选定模型、不引入向量库。

---

## 1. 现状：AI 面盘点

### 1.1 线上推理面（algo 管辖）

| # | 面 | 入口 | 输入 | 输出 | 模型路径 | 降级 | 评估集 |
|---|---|---|---|---|---|---|---|
| A | **智能采集规划** | `POST /api/v1/ai/plans/{id}/plan` → `AiPlannerService._execute_plan` | `target_url` + 清洗 HTML（≤15 000 字）；或用户 `html_snippet`（schema 上限 200 000，清洗后再截断） | `FlowConfig` JSON（selectors / pagination / detail / filters） | `llm_chat`：本租户激活行 → 平台公共行 → yml/env；默认配置 `LLM.MODEL=gpt-4o-mini`（**不是选型结论**） | 同供应商候选链 failover；**无规则兜底**（失败 → plan `failed`） | **无** |
| B | **试采自动修复** | `POST .../test` → `_execute_test` / `_repair_flow` | 失败原因 + 原 flow + `html_sample` | 完整 JSON（非 diff） | 同上 | `LLM.MAX_ITERATIONS=2` 后失败 | **无**（试采是线上代理，不是评估集） |
| C | **资产评分** | Redis `skill:score_queue` → `SkillScoringService.score_skill` | `SKILL.md` 全文 + `source_url` | 四维 1–10 JSON → `ai_suggested_score` / `rubric_ai` / `skill_reviews(ai)` | 同上；`usage_dim=skill_scoring`；`SKILLS.SCORING.MODEL` **配置了但被忽略** | JSON 校验失败重试 1 次 → `skill_jobs` failed；**无规则分** | **无** |
| D | **相似技能聚类** | `POST /api/v1/skills/similar-suggest` | 同 category 的 name/title/description | `{"clusters":[[name,...]]}` 只进 job detail | 同上，**挤占 `skill_scoring` 预算**（单测锁死 `usage_dim`） | 单分类失败跳过 | **无** |
| E | **MCP 验证抽样** | `POST /capabilities/plugins/{name}/verify` → `mcp_bridge.verify_plugin_server` | `mcp_servers` stdio 配置 | `health ∈ {healthy,degraded,down}`（扫描默认 `unknown`；设计稿拟让无 MCP = `unknown`） | **不调 LLM**；抽样 = **首个工具空参 call** | 白名单拒绝 / 连接失败 → down | **无能力评估集**（只有管道单测） |
| F | **中转站真伪探针** | `ChannelProbeService` 周期任务 | 内置 6 题 ± `NEWAPI.PROBE_QUESTIONS_FILE` | 10 维启发式 + `original/spoofed/offline` | 打 new-api 渠道 chat；有参考渠道才比相似度 | 问题文件坏了回退内置 6 题 | **6 题，远低于 50；无冻结 test 集、无已知真伪金标渠道** |

### 1.2 非 LLM、但被当成「质量」的代理（易与 AI 效果混淆）

| 面 | 位置 | 公式 / 判定 | 问题 |
|---|---|---|---|
| Item 质量分 | `scrapy/pipelines/quality.py` | 字段完整率×50 + 核心字段非空×30 + 去重×20 | **不验证选择器是否抽对**。非空垃圾也能 ≥40 |
| 试采闸门 | `orchestrator._judge_test` | `completed` 且 `result_count>0` 且 `avg_score≥40` | 用上式代理「规划是否正确」。FR-72 把它降为**冒烟 + 人工确认**，algo 仍禁止把它当主指标 |
| 连通探测 | `LlmProbeEngine` | 1-token `ping`（适配器路径 `max_tokens=16`） | 只证线路，不证任务质量 |
| 候选采集 | `scrapy/spiders/skill_harvester.py` | GitHub contents / awesome README 正则 | 规则解析，**无质量/许可/注入预筛模型** |
| 公开技能搜索 | `skill_repository.list_skills` | `name/title/description LIKE %q%` | 词汇检索，非 RAG。对 D3 前缀名 `plugin__code-review` 搜短名 **碰巧能命中**（子串） |
| 公开能力列表 | `public_list_capabilities` | 只滤 `status=stable` + type/category/分页 | **不传 q**；丢掉 `recommended`（ops S-13 / FR-18）。检索评估无从谈起 |

### 1.3 运行时与配置（供应商耦合点）

| 项 | 现状 | 风险 |
|---|---|---|
| 消费统一入口 | `backend/services/ai_planner/llm_client.py::llm_chat` | 规划 / 评分 / 相似 **共用** 激活供应商；任务没有独立模型槽（评分 MODEL 开关是空壳） |
| 激活语义 | `llm_common/runtime.py`：本租户激活行 → 平台公共行 → `config/default/llm.yml` | SaaS BYOK 已测隔离；**租户换 Key = 静默换效果**，无 per-tenant 评估门 |
| 默认模型 | `LLM.MODEL: gpt-4o-mini`，`TEMPERATURE: 0.2`，`ENABLED: false` | **未在任何评估集上证明**；点名它当「选定」违规 |
| 协议温度 | openai 路径写 `temperature`；anthropic/gemini `build_chat` **丢温度** | 换协议 = 静默换采样行为。gemini 把 system 当 contents.role，原生协议可能拒或忽略系统约束 |
| 候选链 | `llm_provider_models` priority + health≠down + 冷却 | 同供应商换 model_id；**strong→basic 只告警，不冻结质量 SLO** |
| Prompt 版本 | 规划/修复 prompt **硬编码**在 `prompting.py`；评分 `PROMPT_VERSION = "v1"` **不读** `SKILLS.SCORING.PROMPT_VERSION` | 改 prompt 无回归；线上无法回答「现在跑的是哪一版、分数多少」 |
| Rubric 双源 | `capability-library/taxonomy/rubric.md`（1–3/4–6/7–10 分档）vs 评分 system prompt（只列维名） | 人工与 AI **不是同一套标注口径** |
| LiteLLM | `backend/services/litellm/` **仅剩 `__pycache__`，无源码** | 测试注释写「newapi 将被 LiteLLM 替换」——**替换没有评估计划**。Q-LLM 未关前 **禁止当已集成** |
| 租户配额 | `QuotaService.check_llm_tokens_month` | **从未被 `llm_chat` 调用**（仅 `test_saas_quota.py` / `test_saas_byok.py`）。`llm_chat` 熔的是 provider 维 Redis / 进程内存 vs `LLM.MAX_TOKENS_BUDGET`。FR-10 今日失败 |
| 用量记录 | `record_usage(..., tenant_id=_tid)` 已有 | 记账有、套餐闸无。两本账（套餐 vs provider 预算）ADR-0014 要求 Wave 0 先接套餐闸，不在本波统一文案账本 |
| MCP 传输 | 仅 stdio + 可执行白名单；无 HTTP/SSE | 二期「LLM 工具面」尚未存在，不可当已交付能力 |
| 评分默认关 | `SKILLS.SCORING.ENABLED: false` | 生产未开；一旦打开即对全库打分且无校准。公开 `PublicSkillResponse` **已含 `score`/`tier`**，`derive_tier` 缺人工分时用 AI 分 |
| 试采入队 | `orchestrator` 调 `SpiderService.enqueue` **不传 `tenant_id`** | 配额/隔离是 backend FR-09；algo 侧后果 = 规划消耗与试采结果可能记错租户，评估分流会脏 |

### 1.4 测试覆盖了什么、没覆盖什么

现有 pytest 锁的是 **契约与管道**，不是 **任务效果**。闸门命令（宪法）：`uv run pytest -x -q backend/tests`。

| 文件 | 锁住的 | 锁不住的 |
|---|---|---|
| `test_ai_planner.py` | mock `_llm_chat` 返回 `GOOD_LLM_JSON`；状态机 / FlowConfig 白名单 / 4xx 不重试 | 选择器是否抽对字段 |
| `test_skill_scoring_worker.py` / `test_skill_scoring_plumbing.py` | mock `llm_chat` 返回合法 JSON；AI **不写** `score`/`rubric_human`；`usage_dim` | 分数与 rubric.md 是否一致 |
| `test_skill_similar_suggest.py` | 建议只进 job；`usage_dim=="skill_scoring"`（**把预算耦合写进回归**） | 簇是否真等价 |
| `test_mcp_bridge.py` | 白名单拒 `/bin/sh`；连接失败 → down；扫描后 health=`unknown` | 空参失败不得标 healthy（今日代码正是如此，**无反例测试**） |
| `test_skill_harvester.py` | 离线 Response 解析 | 许可/注入/质量 |
| `test_newapi_services.py` | `_score_probe_batch` 三分支；`ref_similarity < 0.15` → spoofed | 阈值是否该是 0.15；无金标渠道 |
| `test_llm_client_routing.py` / `test_llm_failover.py` / `test_llm_protocol.py` / `test_llm_probe.py` | 协议路由、failover、embedding 过滤、1-token ping | 任务质量 |
| `test_saas_quota.py` / `test_saas_byok.py` | `check_llm_tokens_month` **本身** | 它被 `llm_chat` 调用（没有这条测试，因为没接线） |

**仓库内 `eval/`、`eval-set`、golden HTML、标注规范：零命中。**

这是合格的工程回归，**不能替代** algo 评估集。把 mock JSON 当「AI 测过了」= 自欺。

---

## 2. 评估缺口总表（按四支柱）

| 支柱 | 现有「质量」信号 | 缺什么 | 若不上评估集的产品后果 | 本程序波次 |
|---|---|---|---|---|
| **智能采集** | 试采条数 + `quality_score≥40` | 字段级金标、选择器正确性、分层页面、对抗 HTML | 上线「能抽到东西」的爬虫，字段错位无人知 | Wave 4 只冻试采+人工（FR-72）；评估集 **下一轮** |
| **SaaS** | BYOK 隔离单测、token 计量 Redis | 租户换模型后的效果门、配额接入调用路径、跨租户 prompt 不串 | 免费档与 BYOK 档体验不可比；超配额仍能打模型（FR-10 缺口） | Wave 0 接线配额（backend）；效果门下一轮 |
| **中转站 / relay** | 6 题启发式探针 | ≥50 题冻结集、已知真伪渠道金标、LiteLLM 迁移前后同题对比 | 把渠道判 original/spoofed 当事实，阈值 0.15 极松 | FR-61 保持旁路；扩题下一轮 |
| **Power Market** | AI 四维建议分；`derive_tier` 在人工矫正时 **AI 分可驱动 S/A/B/C** | 与 rubric.md 对齐的标注集、IAA、按资产类型维度、注入对抗 | 未审第三方技能被 AI 打到 S 档进入目录排序 / 公开卡片 | 评分 `ENABLED` 保持 false；公开不得把未校准分当信任信号 |

「评分而无评估」是本诊断的主缺陷名：**scoring-without-eval**。

---

## 3. 智能采集 — 任务定义（task-spec 草稿）

> 对应 FR-70/72（Wave 4 stub）与采集向导「URL → 规划 → 试采 → 修复 → 注册 `flow_generic`」。
> 本节省于定义帽：给 `/pm` 量化边界，给 `/qa` 判据；**不是**产品需求清单，也不是本波施工单。

### 3.1 任务四要素

**输入**

| 项 | 内容 |
|---|---|
| 字段 | `target_url` + 可选 `html_snippet`；服务层抓取后经 `_clean_html_sync`（去 script/style/noscript/注释，截断 15 000 字符） |
| 长度 | 清洗后 P99 未知（无线上分布）；截断会切掉页尾翻页/页脚。snippet schema 上限 200 000 |
| 语言 | 中文站点为主，夹英文类名/价格；未声明多语言 SLO |
| 来源 | 用户给 URL（不可信）或用户贴 HTML；**HTML 正文与指令同一条 user 消息，无分隔标签** |
| 异常 | 空 body、纯登录墙、JS 渲染空壳、验证码、列表+详情、反爬骨架屏 |

**输出**

| 项 | 内容 |
|---|---|
| 结构 | 严格 `FlowConfig`：`selectors[]` 必填；`pagination`/`detail`/`filters` 可空 |
| 约束 | css/xpath/regex 白名单（已有 schema）；`detail.url_selector` 必须 xpath；prompt 把 `max_pages` 钉死为 2，**schema 仍允许 1–100**（只靠 prompt 的约束不是约束） |
| 附加 | `generated_params` 供 `flow_generic`；`test_history[]` |

**怎么算对（判据）** — 现网用错了指标

| 现网 | 应该 |
|---|---|
| `result_count>0` 且 `avg_score≥40` | **字段级抽取准确**：金标字段值 ⊆ 抽取值（允许空白规范化） |
| 结构能过 Pydantic | 结构校验是门槛，**不是**主指标 |

- **主指标**：字段级 **Recall@required_fields**（漏抽代价高：注册出去的爬虫静默缺字段）。
- **次指标**：字段级 Precision（多抽噪声）；JSON 合法率；选择器在 **冻结 HTML 快照** 上的稳定命中（不依赖线上 DOM 漂移）。
- **目标（待 `/pm` 确认，勿对外承诺）**：在 eval-set-planner-v1 上 Recall ≥ 80%、Precision ≥ 70%、JSON 合法率 ≥ 95%。天花板估计见 §3.4。
- **禁止**用 ROUGE/BLEU 评选择器；禁止用 LLM-as-judge 当主指标，除非 judge 与人标 IAA≥80%。
- **禁止**把该目标写上官网（FR-72 已冻）。

**错了会怎样**

| 错误 | 后果 | 代价 |
|---|---|---|
| **漏抽核心字段**（标题/价格/链接） | 注册爬虫持续产出残缺数据 | **高** |
| 抽到但选择器过宽 | 噪声进主库，质量分仍可能 ≥40 | 高（隐蔽） |
| JSON 不合法 / 非法表达式 | 规划失败，用户重试 | 中 |
| 对抗 HTML 改写系统指令 | 输出非采集规则 / 外呼 | **高**（安全） |

**自动化程度**：中代价。规划可自动，**注册必须保留试采+人工确认**（FR-72）。高代价（对公承诺字段口径）不能全自动。

### 3.2 NFR（从现配置读出，不是新 FR）

| 项 | 现状 | 评估含义 |
|---|---|---|
| 超时 | `LLM.TIMEOUT=120` | P95 规划延迟无实测；120s 远超常见交互 SLO，需 `/pm` 拍板 |
| 预算 | `MAX_TOKENS_BUDGET=200000`/月（provider 维）；套餐 `llm_tokens_month` 未进调用路径 | 无单次成本实测；FR-10 未履约 |
| 迭代 | `MAX_ITERATIONS=2` | 修复轮次本身不是评估集 |
| 可用性 | 候选链 failover；yml 兜底 | **无规则规划器**，模型全挂 = 功能挂 |
| 合规 | HTML/技能正文进外部 API | 评估集需脱敏；BYOK 与平台 Key 分流要在评估报告里分开计分。NFR-06：版权夹具不进本波 |

### 3.3 已知能力边界（交 `/qa`，避免把边界当缺陷）

| 场景 | 预期 | 是否缺陷 |
|---|---|---|
| JS 渲染空壳且 `render_js` 未开 | 抽空 → 规划/试采失败 | 否（能力外，除非评估集标了 render_js） |
| 登录墙 / 验证码 | 失败 | 否（FR-70 不承诺） |
| 截断丢掉页尾翻页链 | pagination=null 或错误 | **评估集要单独分层**；截断策略是可迭代变量 |
| 站点 DOM 相对快照已变 | 冻结 HTML 上对、线上错 | 否（分布漂移，刷新评估集） |
| 真实歧义（列表项结构不统一） | 部分字段召回下降 | 否，计入天花板 |
| HTML 注释里的指令 | 清洗后模型看不见 | 否（已剥注释）；不要当对抗样本的主路径 |

### 3.4 天花板

无人工标注一致率。经验值：列表页选择器任务人工 IAA 约 85–90%，真实歧义约 10–15% → **不要承诺 95% 字段召回**。先建评估集再测 IAA。

### 3.5 评估集建设计划 — `eval-set-planner-v1`（尚未存在）

**规模 ≥ 60**（复杂抽取，目标 80 更稳；下限 50）。**本波只允许写目录契约与标注规范，禁止报准确率。**

| 层 | 占比 | 条数（v1） | 样本从哪来 |
|---|---|---|---|
| 典型 | 40% | 24 | 静态列表页（新闻/文档/商品卡片）、字段 3–8 个 |
| 边界 | 25% | 15 | 超长 HTML（触发 15k 截断）、超短、缺分页、中英混排、regex 价格 |
| 困难 | 20% | 12 | 列表+详情两跳、条件过滤、骨架屏+部分 SSR |
| 对抗 | 10% | 6 | **可见文本 / 隐藏节点**里的「忽略以上指令」；过宽 css；`html_snippet` 角色覆盖。不要主打已剥掉的 HTML 注释 |
| 历史失败 | 5% | 3 | 上线后错例（v1 可先空，v2 补） |

**金标格式（建议）**

```jsonl
{"id":"p-001","layer":"typical","url":"https://example.local/list","html_path":"eval/planner-v1/html/p-001.html","required_fields":{"title":["..."],"link":["https://..."]},"optional_fields":{"date":["2026-01-02"]},"notes":"标准卡片列表"}
```

冻结的是 **HTML 快照 + 字段值**，不是线上 URL（防漂移）。跑评估时：规划 →（可选）在快照上执行选择器 → 与金标比，**不要**用 `quality_score`。

**划分**：dev 70% / test 30%，test 冻结。跑 test 节点：方案定型、上线前、换模型、改 prompt。

**标注规范（字段「抽对」）**

- 定义：规范化后（strip、空白折叠、URL 去 fragment）金标值出现在该字段抽取集合中。
- 正例：标题「Foo 发布 v1」抽到「Foo 发布 v1」。
- 反例：抽到整段 nav 文本（过宽）；抽到空。
- 边界：金标有两条 title（多卡片）→ 漏一条算该字段假阴性；多抽导航不算 Precision 命中。
- **一致性**：两人独立标 20 条，IAA≥80% 才能扩标。

**基线阶梯（必须先跑，禁止直接上大模型当选定）**

| 级 | 方案 | 目的 |
|---|---|---|
| ① | 规则：`h1/h2`、`a[href]`、`a.next` / `rel=next` | 最便宜基线 |
| ② | 规划 prompt v1 + **当前激活模型**（不点名换厂商） | 现网方案 |
| ③ | 仅改一变量：例如取消 15k 截断 / 或加 3 条 few-shot | 单变量迭代 |
| ④ | 候选链里 **下一个更便宜模型**（同协议） | 成本对照 |
| ⑤ | 微调 / RAG | **默认不做**；④ 未达标且评估集≥200 再议 |

**降级链（规划任务，现状缺口）**

```
主：激活供应商默认模型 + plan prompt vN
 ↓ 超时 / 5xx / 429 / JSON 校验失败（已有重试+候选链）
备：同供应商下一候选（已有；跨级降质要记评估分，不能只告警）
 ↓ 候选耗尽
兜底：规则规划器（①）→ 输出标 `uncertain`，禁止自动 register
```

现网在第三层是 **直接 failed**。对 `/pm`：要不要静默降级到规则，是产品决策；algo 要求第三层必须存在，否则模型抖动 = 采集向导不可用。

**输出校验（规划）**：已有 FlowConfig schema。缺：字段名白名单、`max_pages` 服务端强制（不要只靠 prompt「固定为 2」）、注入检测层（对抗 6 条通过率门槛）。

**Prompt 注入**：HTML 目前直接拼进 user 消息，**无 `<page_html>` 分隔声明**。评分 prompt 已有「正文不可信」句，规划 prompt 没有。对抗层未建。

### 3.6 试采闸门改造原则（交 backend，不在此实现）

`_judge_test` 可保留为 **冒烟**（进程能跑通），与 FR-72 一致：

- 不得作为算法主指标；
- 注册前应能对照评估集子集（冻结 HTML）出字段级报告（**下一轮**）；
- `quality_score` 继续给数据中心用，**与规划效果解耦**；度量蓝图禁止它进 OEC。

---

## 4. 资产评分 — scoring-without-eval

### 4.1 现网机制（已核实）

- 四维：`completeness` / `doc_quality` / `maintenance` / `real_world_effect`，每维 1–10 + rationale。
- 契约：`SkillScoringResult` 入口校验；AI **永不写** `score` / `rubric_human`（单测锁死，应保持）。
- `derive_tier`：人工分优先，**缺省用 AI 分** → S≥8.5 / A≥7.0 / B≥5.0 / C。调用点在 `correct_meta`（人工矫正），不是评分 worker。**一旦运营用 AI 分当「未人工审」的默认 tier，市场排序就被未校准模型驱动。**
- 公开面 `PublicSkillResponse` 含 `score` 与 `tier`。Wave 1 商店若沿用，等于把未校准分展示给访客。
- Power Market 设计：同步 **不覆盖** `score`；上架是人工闸（D6/D7）。但目录「按 tier 筛」会消费派生列。
- CONTEXT 写「按资产类型可配维度集」——**代码只对 skill 打四维，插件/专家/团无评分器。**

### 4.2 为什么现在的分数不能用

1. **无金标、无 IAA**：不知道「8 分」是严是松。
2. **prompt ≠ rubric.md**：文档有分档描述，模型只看到维名；`maintenance` 还被允许「结合 source_url 推断」——URL 字符串不是 git log，是幻觉源。
3. **`real_world_effect` 在无运行痕迹时不可评**：第三方 SKILL.md 大多没有实测笔记。模型会编一个 6–8 分。该维应允许 `null`/「证据不足」而不是强迫 1–10。
4. **PROMPT_VERSION 双源**：yml `v1` 与代码常量 `v1` 未接线；改 yml 不会改线上。
5. **`SKILLS.SCORING.MODEL` 被显式忽略**（打 warning 后走默认模型）→ 评分与规划 **强制同模型**，无法用小模型做便宜评审。
6. **注入面**：SKILL.md 全文进 user 消息。有「忽略指令」句，但 **对抗层 0 条**。市场入站（harvester → import）会把第三方文档送进同一 prompt。
7. **similar_suggest 挤占 `skill_scoring` 预算**，且无聚类评估（应另开 `usage_dim` + 独立评估集）。
8. **读盘路径**：`LIBRARY_ROOT / file_path / SKILL.md`。Power Market D15 禁止持久化绝对路径、第三方无 `meta.yaml`；评分器在源不可写/指针化之后会读空正文仍打 1–10。

### 4.3 任务定义（评分器）

| 项 | 内容 |
|---|---|
| 输入 | SKILL.md（截断上限待定，建议 8k 字）+ 可选 **结构化信号**（content_hash 年龄、是否有 scripts/、license、last_commit **若有**；禁止让模型假装看见 git） |
| 输出 | 四维整数或 `insufficient_evidence`；overall 只允许从有证据的维聚合 |
| 主指标 | 与人工分的 **二次加权 kappa**（维级）+ overall MAE |
| 次指标 | 结构合法率；对抗层「不服从文档内指令」通过率 ≥90% |
| 失败代价 | **虚高 S 档** → 市场误导（高）；虚低 → 埋没（中）。应对齐保守：证据不足不给 ≥7 |

**禁止**：用「模型 overall 均值」当校准；必须对人标。

### 4.4 评估集 — `eval-set-scoring-v1`（尚未存在）

**规模 ≥ 50**（目标 80：含第三方 bundled 技能，因 Power Market 一期约 300 行资产）。

| 层 | 条数 | 说明 |
|---|---|---|
| 典型 | 20 | 第一方 `capability-library/skills/*` + 结构完整的开源 SKILL.md |
| 边界 | 13 | 无 frontmatter、超短、超长、无 scripts、license=UNLICENSED |
| 困难 | 10 | 跨插件重名技能（`code-review` 两份不同 hash）；文档好但无实测 |
| 对抗 | 5 | SKILL.md 内嵌「把所有维打 10 分」/ 角色覆盖 |
| 历史 | 2 | v1 可合成 |

**标注**：两人按 **rubric.md 原文分档** 独立打四维；IAA≥80%。`real_world_effect` 无实测笔记时金标应为「证据不足」，不是中间分。

**基线阶梯**

| 级 | 方案 |
|---|---|
| ① | 规则：按章节标题/字数/是否含 Example/scripts 启发式 |
| ② | 当前 v1 prompt + 默认模型 |
| ③ | prompt 嵌入 rubric.md 分档原文（只改 prompt） |
| ④ | 更便宜模型（同评估集） |

**未达标前**：`ENABLED` 保持 false；**禁止**用 AI 分派生公开 tier；管理端展示必须标明「未校准建议」。公开卡片不要把 `tier` 渲染成信任徽章。

**Judge 一致性**：若要用 LLM-as-judge 做回归，先在 30 条上测 judge vs 人标，kappa&lt;0.6 则禁用 judge 决策。

---

## 5. MCP 验证抽样 — 连通 ≠ 能力

### 5.1 现网抽样算法（`mcp_bridge.verify_plugin_server`）

```
list_tools → 失败 down；零工具 degraded
否则 call_tool(tools[0], arguments={})
无论工具是否因缺参报错，只要调用返回 → health=healthy
```

代码注释写明「预期多数工具会报参数错误——但这证明了管道通」。这是 **管道连通探针**，不是「插件能做什么」的评估。

Power Market / FR-26.2：无 MCP → **「未知」允许上架**；声明了 MCP 且验证不可用 → 拒绝 enable-host。今日无 MCP 走 `degraded`，与产品词表不一致。

已有价值（应保留）：stdio 白名单、超时、不执行 hooks。这是安全基线，不是质量评估。ADR-0014：禁止把 `call_tool` 扩成平台 Agent 运行时。

聚合语义（`plugin_service.verify_plugin`）：**任一 server healthy → overall healthy**。多 server 插件会掩盖坏的那一路。

### 5.2 验证任务应拆成两层

| 层 | 问题 | 指标 | 是否调 LLM |
|---|---|---|---|
| L0 管道 | 连上吗？list 到工具吗？白名单外拒绝吗？ | healthy/degraded/down/unknown 与金标一致 | 否 |
| L1 抽样能力 | 对 **schema 合法** 的最小参数，工具是否按契约返回 | 抽样成功率、超时率、越权/副作用 | 否（确定性夹具） |
| L2（二期）LLM 工具面 | 模型是否选对工具、参数是否合法 | 工具选择准确率 / 参数 schema 合法率 | 是，需独立评估集 |

一期只承诺 L0+L1。L2 在 CONTEXT 写明「专家执行引擎二期」，**不要把 MCP 当规划器工具直到 L2 评估集存在。**

### 5.3 评估集 — `eval-set-mcp-verify-v1`（尚未存在）

**规模 ≥ 50** 条 **server 夹具**（不是 50 个真实第三方进程）。每条：

```json
{"id":"m-014","layer":"boundary","server":"fixture://echo-required-arg","expect_health":"healthy","sample_tool":"echo","sample_args":{"text":"ping"},"expect_call_ok":true}
```

| 层 | 条数 | 用例 |
|---|---|---|
| 典型 | 20 | list≥1、有无参工具、合法最小参调用成功 |
| 边界 | 13 | 零工具；仅 required 参数工具（**空参应记 sample_failed，不得因此标 healthy**）；超时；非 JSON stdout |
| 困难 | 10 | 多 server 一插件（现网：任一 healthy 则 overall healthy——要锁这个聚合语义是否合理）；HTTP MCP（今日不支持，金标应为 skip/unsupported） |
| 对抗 | 5 | command=`/bin/sh`；args 带外带环境；symlink 逃出 |
| 历史 | 2 | 预留 |

**必须改的判定（评估驱动，不是先改代码）**：空参调用失败且 schema 显示 required 时，应标 `degraded` 或 `sample_failed`，而不是 `healthy`。用评估集锁回归，再交给 `/backend`。

**Kimi 无 mcpServers**：金标 `unknown` + `reason=no_mcp`，与 FR-26.2 一致；今日代码是 `degraded`，评估集要单独标「迁移前/后」两列。

---

## 6. 中转站探针 — 最接近评估集、仍然不合格

`DEFAULT_PROBE_QUESTIONS` 共 **6** 条（身份中英、知识截止中英、137×89−2048、RED/BLUE 两行）。10 维分数里多半是启发式（延迟比、逐字重复、reasoning_tokens）。

缺口：

| 项 | 现状 | 需要 |
|---|---|---|
| 规模 | 6 | ≥50，含格式/拒答/长上下文/工具调用声明 |
| 金标渠道 | 无「已知正品 / 已知套壳」清单 | 每题在参考渠道上的冻结回答（版本化） |
| 知识截止题 | 「说出 2025 年事件」 | 会随时间变；应改为 **冻结事实卡** 或标注有效期 |
| spoof 阈值 | 参考相似度 &lt; **0.15** 才 spoofed | 过松；阈值必须在评估集上调，禁止拍脑袋。`test_newapi_services.py` 把 0.15 **锁成回归金标**，改阈值必须先换评估而非改测试迁就代码 |
| LiteLLM 替换 | 测试写「将被替换」 | **迁移 = 换调用面**：必须用同一问题集 A/B，否则真伪口径断裂。Q-LLM 未关前不做 |

探针是 **分类任务**（original / spoofed / offline）。主指标：对金标渠道的 **spoofed 召回**（漏判套壳代价高），次指标：original 精确（误杀正品）。

FR-61 + 度量蓝图：verdict **不是**计费/熔断/北极星。保持旁路直到评估达标。

---

## 7. 技能市场采集（harvester）与相似 — 先别上模型

`skill_harvester` 是规则抽取，测试覆盖 JSON/README 解析。Power Market 把它标为 crawl 源 → 候选人工闸（D7：同步不自动 listed）。

**现在不要**对候选做 LLM 预打分。若 `/pm` 要「智能排序候选」，必须先：

1. 独立任务：输入=候选 url+README 摘要，输出=`promote | reject | uncertain`；
2. 评估集 ≥50（含 UNLICENSED、重名、注入 README、非 SKILL 目录）；
3. 基线 = 许可黑名单 + 域名白名单规则。

否则又是 scoring-without-eval，且会把第三方注入推进评分 prompt。

相似聚类（`similar_suggest`）同理：Power Market D3b **hash 折叠**是确定性的，应作为基线；LLM 簇只允许建议。评估集 = 已知等价对 / 非等价对（mattpocock vs superpowers 的 `tdd` 等），指标用 pair F1，不要用「簇数量」。无 pair 评估集前 **不要**在同步后对 51 个重名自动跑 LLM。

解析脆弱点（实现债，交给 backend）：`json.loads(text.strip().removeprefix("```json").removesuffix("```"))` 比规划侧 `_parse_llm_json` 更脆。

---

## 8. RAG — 本程序明确不做

仓库 **没有** 向量库、embedding 索引、chunk、rerank、引用校验。出现的 `text-embedding-*` 只出现在 **模型列表过滤测试**（对话模型要排除 embedding），不是检索管线。

Power Market FR-19 是「按短名搜到」。现网：

| 面 | 检索 | 够不够 |
|---|---|---|
| 公开技能 | `LIKE %q%` on name/title/description | 体量约百级；D3 前缀名子串能命中短名 |
| 能力资产服务 | `list_assets(q)` 只 `name LIKE` | 不搜 title / 短名列（列还不存在） |
| 公开能力广场 | **不传 q** | FR-19 今日失败（产品/API，不是缺向量） |

**生成质量的上限由检索质量决定。** 这里的「检索」是 SQL 词汇，不是 RAG。调优顺序：先把公开列表接上 `q` 并覆盖 `origin_local_name` / alias（Wave 1 契约），再谈要不要混合检索。

引入向量库是不可逆决策（要 ADR + 检索评估集 Recall@5）。资产约 300 行时 SQL `LIKE` + 短名/别名列足够。algo **拒绝**为本特征引入 RAG。

若将来做文档问答（非本程序）：先建「问题 → 块 ID」50–100 对，Recall@5&lt;80% 不准碰生成。

---

## 9. 供应商耦合与模型选型（不选定厂商）

### 9.1 耦合清单

1. **单激活供应商**驱动所有任务维度（规划/评分/相似）。
2. 评分专用模型配置是死代码。
3. 默认 `gpt-4o-mini` 写在 `config/default/llm.yml`，无评估绑定。
4. 协议适配器有三套（openai_compatible / anthropic / google_gemini），**效果评估未按协议分层**；温度与 system 角色在原生协议上丢失。
5. LiteLLM 生成配置点了 DeepSeek / Kimi 一串 id——**这是部署清单，不是选型结论**。源码目录空，不能当已集成。
6. new-api 渠道探针打的是网关后的模型，与平台 `llm_chat` 不是同一条路径 → 探针合格 ≠ 规划合格。

### 9.2 选型纪律（本特征必须遵守）

- 先有 `eval-set-*-vN`，再在 **同一版本** 上跑阶梯。
- 比较维度：主指标 / 次指标 / P95 延迟 / 单次成本（token×单价）。
- 「换 GPT-4o / 换 Kimi / 换 DeepSeek」若没有「当前方案在 vN 上的哪项不达标」，回答是：**不换。**
- 租户 BYOK：平台兜底模型与租户自带模型必须 **分开出分**，不能混成一个 91%。
- 换协议（openai → anthropic/gemini）视为换模型：必须单变量重跑评估（温度/系统指令语义已变）。

### 9.3 降级链（平台级，补全现状）

```
主：租户激活模型（BYOK）或平台公共默认
 ↓ 冷却 / health=down / 超时 / 校验失败
备：同供应商候选链（已有）或平台公共行（SaaS 已有解析顺序）
 ↓ 全失败
兜底：
  规划 → 规则选择器（§3.5 ①），禁止自动 register
  评分 → 规则启发式分或跳过（保持 AI 字段空）
  相似 → 只跑 content_hash / 名称规则
  MCP → 维持 unknown/down，不假装 healthy
  探针 → offline
```

**无规则兜底上线 = 外部 API 抖动时向导与评分直接停。** 候选链不是规则层。

### 9.4 不引入的东西（定义帽即拒绝）

| 提议 | 原因 |
|---|---|
| 向量库 / RAG 搜技能 | 资产约 300 行，SQL `LIKE` + 短名/别名足够；引入向量库不可逆，需 ADR + 检索评估集 Recall@5。现在 **没有检索评估集** |
| 微调评分器 | 标注 &lt;200 且口径未稳 |
| LLM 执行专家团 / MCP 当规划工具 | 二期；缺 L2 评估集；ADR-0014 禁止 |
| 用 LiteLLM 替换 new-api 而不做探针 A/B | 口径断裂；Q-LLM 未关 |
| 对 harvester 候选做 LLM 预打分 | scoring-without-eval + 注入面 |

---

## 10. Prompt / 回归孔洞清单（给实现阶段当债）

| ID | 孔 | 位置 | 回归方式 |
|---|---|---|---|
| P1 | 规划/修复 prompt 硬编码，无 `prompts/*.txt` 版本 | `prompting.py` | 抽文件 + eval-set-planner-vN |
| P2 | 评分 prompt 不嵌入 rubric 分档 | `skill_scoring_service.py` `_SYSTEM_PROMPT` | 与 rubric.md 同 hash 绑定 |
| P3 | `SKILLS.SCORING.PROMPT_VERSION` 未读 | yml vs 常量 | 单一事实源 |
| P4 | HTML 无数据区隔离 | `_build_plan_messages` | 对抗层（可见文本，不是注释） |
| P5 | 15k 截断无评估 | `url_guard._MAX_HTML_CHARS` | 边界层样本 |
| P6 | 试采主指标错误 | `_judge_test` | 字段级评估；产品侧 FR-72 已降为冒烟 |
| P7 | MCP 空参即 healthy | `verify_plugin_server` | mcp-verify-v1 |
| P8 | 评分 MODEL 忽略 | `score_skill` | 接线后必须 **重新** 跑 scoring-v1（换模型=一变量） |
| P9 | similar 与 scoring 同预算维 | `similar_suggest` | 拆 `usage_dim` |
| P10 | 租户 LLM 配额未进 `llm_chat` | `quota_service` vs `llm_client` | FR-10；效果评估要按租户分流 |
| P11 | 探针 6 题 / 阈值 0.15 | `channel_probe_service` | probe-v1；改阈值先换评估 |
| P12 | 无线上抽样回灌 | 全部 AI 面 | 错例进评估集 v2+ |
| P13 | 原生协议丢温度 / gemini 丢 system | `llm_protocol/adapters.py` vs `llm_client` | 协议分层评估；换协议当换模型 |
| P14 | 评分预算 0 被当成「不覆盖」 | `score_skill` `budget if budget > 0 else None` | 配置语义写进测试 |
| P15 | 公开 score/tier 可来自未校准 AI | `PublicSkillResponse` + `derive_tier` | 未校准前公开字段为空或标「未评」 |
| P16 | `max_pages` 只靠 prompt | `prompting._CONSTRAINTS` vs schema 1–100 | 服务端强制 |

**迭代纪律**：每轮只改一个变量（prompt **或** 截断 **或** 模型 **或** 闸门阈值）。证据保留负向轮。分数必须写 `xx%（eval-set-planner-v1）`。

---

## 11. 给下游的接口（非 FR，是约束）

| 给谁 | 内容 |
|---|---|
| `/pm` | 不要承诺采集「AI 自动生成可用爬虫 95% 成功」。FR-72 已冻：试采+人工，官网无准确率。市场 AI 分未校准前 UI 必须写「建议分」或隐藏。天花板约 90%。评估集满 50 不挡 Wave 0。 |
| `/architect` | 不引入向量库/微调/新 LLM SDK。LiteLLM 若复活算新依赖，先 ADR + 探针/规划 **两套** 评估对照（Q-LLM）。MCP HTTP 传输是能力扩展，要进 L0 评估夹具。规划继续只走 `llm_chat`（ADR-0014）。 |
| `/backend` | FR-10：`llm_chat` 前套餐检查；降级链第三层；评分读配置版 prompt/模型；MCP 抽样判定与评估集对齐；规划 HTML 分隔；试采闸门与字段评估解耦；公开 capabilities 接上 `q`（词汇，不是向量）；公开 score/tier 未校准不高亮。 |
| `/qa` | 评估脚本一条命令出分层分（下一轮）；本波回归仍是契约测试。降级链每层都要测；对抗层；不要把 mock JSON 当效果门。改 0.15 必须带评估 diff。 |
| `/sre` | 成本告警（日预算、单租户 QPS）；生成 LiteLLM 配置的密钥不得入库；评分 worker 打开前要有预算熔断演练。 |
| `/data-collector` | 规划评估集的 HTML 快照采集规范（只收可公开/自有夹具页，脱敏）。本波版权未放行则不采。 |
| `/analyst` | 上线后对比：评估集召回 vs 线上试采通过率（会分叉，分叉即漂移信号）。禁止用质量分/技能均分/探针伪装次数当 OEC。 |

---

## 12. 建议落地顺序（对照冻结波次）

Wave 0（不挡、可并行的 **目录契约**，空 jsonl 也比继续盲飞好）：

1. 建四份评估集目录契约（**不报准确率**）：`eval/planner-v1`、`eval/scoring-v1`、`eval/mcp-verify-v1`、`eval/probe-v1`（各含 README 标注规范）。规模未满 50 之前，**禁止**报准确率。
2. backend 接 FR-10（套餐闸进 `llm_chat`）。这是配额正确性，不是效果数字。
3. 公开面：未校准 AI 分/tier 不作为信任信号；评分 `ENABLED` 保持 false。

Wave 1（市场）：不上评分器、不上 RAG、不对 51 个重名自动跑 similar。检索 = SQL + 短名/别名。

Wave 4（采集执行）：FR-72 试采+人工。字段级评估仍下一轮。

下一轮（spec §9 点名 algo）：

1. 规划：标满 60 条快照 → 跑规则基线 → 再跑现网 prompt。用结果决定要不要改截断/prompt（一次一个）。
2. 评分：标满 50 条 → 校准前 UI 降级为「未校准」；`ENABLED` 默认 false 直到 MAE 达标（阈值由 `/pm` 拍，建议 overall MAE≤1.5/10）。
3. MCP：夹具 50 条锁 L0/L1；改空参判定 **必须** 带评估 diff。
4. 探针：扩题+金标渠道后再动 0.15 阈值；若关 Q-LLM 做 LiteLLM 迁移，迁移日跑同一版本。

超出单波 appetite 50% → 停下重判。评估集施工不得塞进 Wave 0 的「停止说谎」票。

---

## 13. 开放问题

| ID | 问题 | 阻塞 | 需要谁 | 相对上一稿 |
|---|---|---|---|---|
| Q-A1 | 规则规划兜底是否对用户可见（「简易规则模式」）？ | 降级 UX | `/pm` `/designer` | 仍开（原 Q3） |
| Q-A2 | `real_world_effect` 无证据时：禁止该维 / 允许 null / 强制低分？ | 评分 schema | `/pm` + 本角色下一轮 task-spec | 仍开（原 Q2） |
| Q-A3 | 租户 BYOK 模型不在平台评估白名单时：拒绝 / 仅警告 / 强制走平台模型做评分？ | SaaS 质量隔离 | `/pm` `/architect` | 仍开（原 Q4） |
| Q-A4 | MCP 空参失败是否改变公开 `installable` / enable-host？FR-26.2 已冻「无 MCP=未知可上架；MCP down 拒 enable-host」，空参失败落哪一档未写 | 商店徽章 | `/pm` | 收窄（原 Q5） |
| Q-A5 | `similar_suggest` 要不要在 Power Market 同步后对 51 个重名自动跑？无 pair 评估集前 algo **建议否** | 误合并 | `/pm` | 仍开（原 Q8） |
| Q-A6 | 月成本上限与调用量（规划+评分+探针）？无数字则不做贵模型阶梯 | 选型 | `/pm` | 仍开（原 Q9） |
| Q-A7 | 公开卡片是否展示 `score`/`tier`？未校准前 algo **建议不展示或标未评** | 商店信任信号 | `/pm` `/designer` | **新增** |
| Q-A8 | 评估集 HTML/SKILL.md 版权：只用自有夹具，还是可引用公开页快照？NFR-06 把它踢出 Wave 0/1，下一轮仍要口径 | 评估集能否满 50 | `/pm` 法务口径 | 推迟（原 Q7） |

**已由冻结 spec 关闭、不再问：**

| 原 ID | 关闭方式 |
|---|---|
| 原 Q1 规划未达 80% 是否禁止 register | FR-72：试采通过 + 人工；不对外报准确率；评估集下一轮 |
| 原 Q6 探针是否参与熔断 | FR-61：伪装不自动下线 |
| 原 Q10 LiteLLM 是否已撤销 | Q-LLM 仍是操作者问题；本程序不选；Wave 0/1 不替换 |

---

## 14. 自检（本诊断）

| 项 | 状态 |
|---|---|
| 评估集 ≥50 带标注口径 | **计划已写，文件未建**（spec 把施工放到下一轮；定义帽禁止冒充已完成） |
| 最便宜基线先跑 | 已规定阶梯 ①；**尚未跑数** |
| 降级链主→备→规则 | 规划/评分/MCP/探针均已写；现网缺规则层 |
| 效果数字带评估集版本 | **无数字可报**（正确） |
| 每轮单变量 | 已写入纪律 |
| 证据含负向轮 | 待有评估脚本后执行 |
| 未点名选定厂商 | **遵守**（`gpt-4o-mini` 仅作为现网默认配置被点名，不是选型结论） |
| 未写 CRUD/UI/训练 | 遵守 |
| 未实现代码 | 遵守 |
| 未引入 RAG | **遵守并明确拒绝** |
| 坑点文件 | 仅收录代码+测试锁死项 → `skills/algo/references/auto-agents-pitfalls.md` |

---

## 15. 关键代码锚点

| 主题 | 路径 |
|---|---|
| 规划 prompt / JSON 解析 | `backend/services/ai_planner/prompting.py` |
| LLM 调用与 failover | `backend/services/ai_planner/llm_client.py` |
| 试采判定 | `backend/services/ai_planner/orchestrator.py` `_judge_test` |
| HTML 截断与剥注释 | `backend/services/ai_planner/url_guard.py` `_MAX_HTML_CHARS` / `_HTML_COMMENT` |
| 运行时供应商解析 | `backend/services/llm_common/runtime.py` |
| 协议适配器（温度/system） | `backend/services/llm_protocol/adapters.py` |
| 资产评分 | `backend/services/skill_scoring_service.py` |
| rubric 文档 | `capability-library/taxonomy/rubric.md` |
| tier 派生 | `backend/services/skill_service.py` `derive_tier` |
| 相似建议 | `backend/services/skill_service.py` `similar_suggest` |
| 技能词汇检索 | `backend/repositories/skill_repository.py` `list_skills` |
| 能力 list q | `backend/services/capability_service.py` `list_assets`（公开面未传 q） |
| 公开投影含 score/tier | `backend/app/api/v1/public_skills.py` `PublicSkillResponse` |
| MCP 抽样 | `backend/services/mcp_bridge.py` `verify_plugin_server` |
| 插件 verify 聚合 | `backend/services/plugin_service.py` `verify_plugin` |
| 市场采集 | `scrapy/spiders/skill_harvester.py` |
| Item 质量分 | `scrapy/pipelines/quality.py` |
| 渠道探针 | `backend/services/channel_probe_service.py` |
| LLM 默认配置 | `config/default/llm.yml` |
| 评分开关 | `config/default/skills.yml` |
| 配额未接线 | `backend/services/quota_service.py` `check_llm_tokens_month` |
| FlowConfig / XSS 白名单 | `platform_core/schemas/ai_plan.py` |
| 冻结产品边界 | `.sdlc/feat-four-pillars/01-define/spec.md` FR-10/61/72、T-23、NFR-06 |
| 度量禁区 | `.sdlc/feat-four-pillars/01-define/metrics-blueprint.md` §1/§4 |
