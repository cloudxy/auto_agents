# 算法诊断 · feat-four-pillars-v2

> 角色：algo（评估集 / 模型选型 / 降级链 / RAG；不写业务 CRUD、不写 UI、不写基础设施）
> 日期：2026-09-08｜版本：v2-define（全新方案输入；**不是**现行合同）
> 泳道：L4 · `feat-four-pillars-v2`（supersedes `feat-four-pillars`）
> 上游：本目录 `INPUTS.md` 全书单 · grok-files `feat-four-pillars-algo-diagnosis.md` · 旧 `.sdlc/feat-four-pillars/01-define/diagnosis/algo.md`（refresh-2）· 旧 spec v1.4 / contract v2.1 / ADR-0014 / T-06 · 仓库现网（2026-09-08 复核）· 宪法 `sdlc.config.yaml` → `.claude/rules/project_rule.md` · `CONTEXT.md`
> 下游：`/pm`（可卖口径与是否冻算法票）· `/architect`（票归属：algo vs backend）· `/backend`（FR-10 闸、入队租户；**本帽不改调用代码**）· `/qa`（效果门 ≠ mock JSON）· `/sre`（成本告警，本波不施工）
> **红线**：无评估集版本的效果数字视为无效；未跑阶梯不得点名厂商为「选定」。本帽不实现代码、不建评估集文件、**不改模型调用路径**。
> **本文件回答三问**：① 哪些 AI 面可卖 ② 哪些是示意 ③ 全新方案该不该冻算法票。

---

## 0. 一句话结论

平台仍是 **5 条线上 LLM 面 + 1 条非 LLM 连通抽样 + 1 条启发式质量分**，**0 份版本化评估集、0 次基线阶梯、0 次 prompt 回归、0 条 RAG**。2026-09-08 现网复核与旧 refresh-2 **主事实未变**。

**效果数字不可报。不得选定供应商。**

**可卖的不是「AI 抽得准 / 评得准 / 渠道是正品」，而是「向导存在 + 人工闸还在 + 套餐 token 数字变成真闸」。示意的是官网四步动画、公开 S/A/B/C、插件 healthy=能干活、探针 original/spoofed、quality_score≥40=抽对。**

**全新方案：不要冻算法施工票。** 冻给 `/pm` 的是「禁止把代理指标当卖点」的产品不变式；冻给 `/backend` 的是配额/入队（旧 T-06 / T-05，**不是** algo）。评估集满 50 并报准确率仍属**下一程序**，与旧 spec T-23 / NFR-06 同向。旧 contract 把 `/algo` 标 Wave 0/1 **N/A** 是对的，v2 应保持，不要倒退成「先建四份空 jsonl 票」。

---

## 0.1 相对旧程序：采信 / 作废 / 改判

旧 feature `status: superseded`。下列是输入，不是 v2 合同。

| 项 | 旧程序（refresh-2 + spec v1.4 + contract v2.1） | v2 采信 |
|---|---|---|
| 0 评估集、不选定模型、不引入 RAG | 主结论 | **采信**；2026-09-08 仓库 `eval/` / `eval-set` **仍零命中** |
| scoring-without-eval | 主缺陷名 | **采信** |
| FR-10 套餐闸未进 `llm_chat` | 失败；T-06 归 `/backend` | **采信**；`check_llm_tokens_month` 生产引用仍 = 定义 + 两份测试 |
| FR-72 试采+人工；官网无准确率 | Wave 4 stub | **采信为产品不变式**；v2 仍不要把「抽对」写进可卖句 |
| T-23 评估集满 50 = 下一轮；空目录契约可并行不挡 Wave 0 | spec §5 / §9 | **改判**：空目录契约**不要**写成实现票。写进范围外即可。并行空 jsonl 不增加可卖性，却会被当成 Wave 0 工作量 |
| `/algo` Wave 0/1 = N/A | contract §8 | **采信并强化**：N/A 的是施工；定义帽仍要交本诊断 |
| 规划 HTML 注释已剥；对抗应走可见文本 | refresh-2 相对初稿的修正 | **采信**（`url_guard._HTML_COMMENT` 仍剥注释） |
| P-AA-01…10 坑点 | `skills/algo/references/auto-agents-pitfalls.md` | **采信**；本轮复验仍锁死，不新开坑条 |
| 旧 Q1/Q6/Q10 已由 spec 关闭 | FR-72 / FR-61 / Q-LLM 不代选 | 旧 spec 关闭 ≠ v2 已冻；v2 `/pm` 需重新写入。algo **建议原样保持**，不重开「未达 80% 是否禁止 register」 |

未改的技术债（P1–P16 孔洞）见 §6。本帽不施工。

---

## 1. 三问正文：可卖 / 示意 / 冻票

### 1.1 判定尺

| 标签 | 含义 | 对外能不能写进官网/定价「当前可买」 |
|---|---|---|
| **可卖（诚实口径）** | 用户今天能走完，且卖点不依赖未校准效果数字 | 可以，句子必须与闸门一致 |
| **实验室** | 代码路径在，默认关或无 Worker/无 Key/无评估 | 只能标预告或内测，不能当已履约 |
| **示意** | 有代理指标或静态动画，看起来像质量 | **禁止**当卖点、当 OEC、当信任徽章 |
| **拒绝引入** | 本程序做了会不可逆且无评估 | 不写 FR、不拆票 |

「可卖」≠「效果达标」。无 `eval-set-*-vN` 就没有达标声明。

### 1.2 AI 面清单（2026-09-08 复核）

| # | 面 | 现网 | 标签 | 可卖句（若写） | 禁止句 |
|---|---|---|---|---|---|
| A | **智能采集规划** | `POST /api/v1/ai/plans/{id}/plan` → `llm_chat`；`LLM.ENABLED` 默认 **false**；prompt 硬编码；无规则兜底 | 实验室 | 「粘贴链接后，向导会生成一份**可编辑**的采集方案，需你确认。」 | 「AI 自动分析页面 / 自动反爬 / 准确抽取 / xx% 成功」 |
| B | **试采自动修复** | `MAX_ITERATIONS=2` 整份 JSON 重写；失败 → plan `failed` | 实验室 / 示意 | 「试采失败会再试有限次；仍失败则停，不会偷偷上线。」 | 「自动修复到能用」 |
| C | **试采闸门** | `_judge_test`：`completed` ∧ `result_count>0` ∧ `avg_score≥40`；`quality.py` = 非空率 | **示意**（冒烟可留） | 「试采通过 = 进程跑通且抽到非空字段，**不是**字段抽对。」注册仍须人工确认 | 「试采通过 = 抽对了」；把 40 分写上官网 |
| D | **资产评分** | worker 默认 `SKILLS.SCORING.ENABLED=false`；四维 1–10；`derive_tier` 无人分则吃 AI 分；公开 `PublicSkillResponse` 含 `score`/`tier` | **示意**（且默认关） | 管理端可写「未校准建议分」。公开卡片：**不展示或标未评** | 「AI 评分 + 人工复核」当已履约（官网 `SkillsSection` 现句）；S/A/B/C 信任徽章 |
| E | **相似聚类** | `similar_suggest` 挤占 `usage_dim=skill_scoring`（单测锁死）；只进 job | **示意** | 无。hash 折叠（D3b）才是基线 | 「智能去重已上线」；同步后对重名自动跑 LLM |
| F | **MCP 验证** | **不调 LLM**。list≥1 后空参 `call_tool`，**无论 sample.ok 都 `healthy`**。无 MCP → `verify_plugin` 写 `degraded`（扫描落库常 `unknown`） | 实验室管道 / **示意能力** | 超管：「我们检查了 stdio 管道能否连上。」 | 「healthy = 插件能干活 / 官方认证」 |
| G | **中转真伪探针** | 内置 **6** 题；`ref_similarity < 0.15` → spoofed；无金标渠道 | **示意分类**（值班旁路） | 值班内部观察。FR-61：伪装**不**自动下线 | 「10 维鉴定正品」；定价卖渠道组（Q-RELAY 未关） |
| H | **LLM 套餐闸** | `QuotaService.check_llm_tokens_month` **从未被 `llm_chat` 调用**；真熔断是 provider 维 `LLM.MAX_TOKENS_BUDGET` | 配额缺口（**backend**） | 接上之后才可卖「月度 token 是真闸」 | 现在用量页的 20 万当已执法 |
| I | **公开检索** | 技能 `LIKE %q%`；公开能力列表 **不传 q**；无向量库 | 词汇检索（产品/API） | Wave 1 落地后：「用短名能搜到已上架项」（FR-19） | 「语义搜索 / RAG」 |
| J | **LiteLLM 网关** | `backend/services/litellm/` 仅 `__pycache__` | **示意** | 无 | 「已切换 LiteLLM」；Q-LLM 未关前当已集成 |
| K | **专家团 / LLM 工具面** | CONTEXT 二期；ADR-0014 禁把 `mcp_bridge.call_tool` 扩成运行时 | **拒绝引入** | 无 | 「平台内召唤专家团」 |
| L | **官网 AI 叙事** | Hero「交给 AI 来完成」；`AiFlowSection` 四步静态；`HERO_STATS` 128,000+ / 3.2 亿 | **示意履约裂缝** | Wave 0 改口后只留**当前能走完**的动作 | 现句整段 |

### 1.3 按四支柱：能卖什么

| 柱 | 可卖（诚实） | 示意（必须改口或藏） | 卡住可卖的不是缺模型，而是 |
|---|---|---|---|
| **采集** | 控制台任务/结果/CSV（非 AI 效果）。AI 向导只能卖「辅助生成 + 试采冒烟 + 人工上线」 | 官网四步动画、准确率、Excel、任意站反爬 | Worker 不在根 compose；入队丢租户；`quality_score` 代理抽对；无评估集 |
| **SaaS** | 成员/隔离骨架。**token 套餐在接线前不可卖「已限流」** | 用量页 20 万挡规划 | FR-10 未接线（backend） |
| **中转** | 超管值班看渠道/窗口（收权后） | original/spoofed 当事实；租户渠道组 SKU | 6 题 + 0.15；Q-RELAY / Q-AGPL |
| **市场** | 上架闸 + 订阅是产品，不是算法。检索 = SQL | AI 分 / tier / healthy 徽章 | 评分无金标；公开协议已带 `score`/`tier` |

旧 grok-files `four-pillars-plan.md` 执行一页纸已写：**示意 Hero 大数 → 公开闸 listed∩发布∩许可；数仓 / 评估集准确率明确还不做。** v2 沿这条，不要把「还不做」做成票。

### 1.4 全新方案该不该冻算法票 — **否**

**定义**：算法票 = 评估集施工、prompt 抽文件、基线阶梯、换模型、打开评分 worker、改探针阈值、规则规划器、RAG、similar 自动跑、LLM-as-judge 校准。

| 若冻进 v2 第一波 | 后果 |
|---|---|
| 冻「满 50 条并报准确率」 | NFR-06 版权未放行；无生产错例；IAA 未测；appetite 被评估集吃掉；官网会有人把内部百分数抄出去（与 FR-72 冲突） |
| 冻「空目录契约」四份 jsonl | 旧 Wave 0 建议第 1 条。空 README **不增加可卖性**，却占票号、像开工。G-fresh 已证明范围叙事会漂 |
| 冻「选定 gpt-4o-mini / 换 Kimi」 | 配置默认值不是选型。无 `eval-set-*-vN` 换模型 = 盲飞 |
| 冻「打开 SKILLS.SCORING」 | 公开 `tier` 立刻可被未校准 AI 驱动（`derive_tier`） |
| 冻「改 0.15 / 扩探针题」 | 单测把 0.15 锁成金标；无渠道金标会把测试改去迁就代码（P-AA-07） |

**要冻的（给 `/pm` 写进新 spec 的不变式，不是 `/algo` 实现票）：**

1. 官网与定价 **不得**出现抽取准确率、AI 评分已校准、插件官方认证、渠道正品保证。
2. 采集 AI：**注册 = 最近一次试采冒烟通过 + 人工确认**；`quality_score` 禁止进 OEC / 北极星（与旧度量蓝图一致）。
3. 评分：`ENABLED` 保持 false；公开 `score`/`tier` 未校准不得当信任信号。
4. 探针 verdict **旁路**（伪装不下线）。
5. 不引入向量库 / 微调 / 专家团执行 / 把 MCP verify 扩成工具面。
6. Q-LLM **不代选**；规划继续只走 `llm_providers` + `llm_chat`（旧 ADR-0014 意图）。
7. 评估集满 50 + 报准确率 = **下一程序**；本程序 Wave 0/1 **无 algo 实现票**。

**要冻但归属别人的票：**

| 工作 | 归属 | 为何不是 algo |
|---|---|---|
| `llm_chat` 前 `check_llm_tokens_month`（上海月） | `/backend`（旧 T-06 / FR-10） | 配额正确性，不是效果数字 |
| 定时/模板/AI 试采入队带 `tenant_id` | `/backend`（旧 T-05 / FR-09） | 隔离；`SpiderService.enqueue` 仍不转发；orchestrator 试采仍不传 | 
| 官网删「AI 评分+人工复核 / 交给 AI 来完成」空头 | `/pm` + `/frontend`（FR-01） | 履约诚实 |
| 公开卡片不渲染未校准 tier | `/pm` + `/backend`/`frontend` | 展示闸；algo 只提供「未校准」判据 |

**下一程序才冻算法票的触发（写给 `/pm`，本波不排期）：**

- 操作者要对外承诺字段召回 / 打开评分 / 探针参与熔断 / 换厂商，**三者任一**；**且**
- 评估集 ≥50、分层、IAA≥80%、dev/test 划分、一条命令可跑；**且**
- 版权口径（旧 NFR-06）已放行自有夹具。

未触发前：**roles_skipped 可在实现帽写入 `algo`**（state.yaml 已预留这句）。

---

## 2. 现网技术盘点（只读复核，供不变式引用）

### 2.1 LLM 调用单点

| 项 | 2026-09-08 |
|---|---|
| 统一入口 | `backend/services/ai_planner/llm_client.py::llm_chat` |
| 调用方 | 规划/修复（`ai_planner`）· 评分（`skill_scoring_service`）· 相似（`skill_service.similar_suggest`） |
| 套餐闸 | **未接线**。`check_llm_tokens_month` 命中：`quota_service.py` 定义 + `test_saas_quota.py` + `test_saas_byok.py` |
| 真熔断 | `LLM.MAX_TOKENS_BUDGET`（默认 20 万）+ Redis/内存；月度 hash 写入仍 `{dim}\|total`（dba P1，串租户风险） |
| 默认模型 | `config/default/llm.yml` `MODEL: gpt-4o-mini`，`ENABLED: false`，`TEMPERATURE: 0.2`，`TIMEOUT: 120` — **配置，不是选型** |
| 评分专用 MODEL | 非空只 `warning` 后回退默认（P-AA-04） |
| 评分预算 0 | `budget if budget > 0 else None` → 挤占全局 20 万 |
| 降级 | 同供应商候选链；**无规则层** → 失败即 plan/job failed |
| Prompt 版本 | 规划/修复硬编码 `prompting.py`；评分 `PROMPT_VERSION = "v1"` 不读 yml |

### 2.2 代理指标（禁止当效果）

| 代理 | 公式/判定 | 错在哪 |
|---|---|---|
| Item `quality_score` | 完整率×50 + 核心非空×30 + 去重×20 | 非空垃圾可 ≥40 |
| 试采通过 | 上式均分 ≥40 | FR-72 应降为冒烟 |
| MCP `healthy` | list≥1 后空参 call 返回即健康 | 管道通 ≠ 契约对 |
| 无 MCP | `verify_plugin` → `degraded` | 与 FR-26.2「未知可上架」词表不一致 |
| `derive_tier` | 无人分用 AI 分；S≥8.5 / A≥7 / B≥5 | 未校准分可进公开协议 |
| 探针 spoofed | 相似度 < **0.15** | 过松；6 题含会过期的「2025 年事件」 |
| 连通 ping | 1-token | 只证线路 |

### 2.3 测试锁的是契约，不是任务效果

闸门：`uv run pytest -x -q backend/tests`。规划/评分/相似均 mock `llm_chat` 回手写 JSON（P-AA-01）。`test_newapi_services.py` 把 0.15 锁成回归。`test_skill_similar_suggest.py` 把 `usage_dim=="skill_scoring"` 锁死（P-AA-06）。

**把 mock JSON 当「AI 测过了」= 自欺。** `/qa` 效果门必须另挂评估脚本；本程序不建该脚本。

### 2.4 RAG

仓库无向量库 / chunk / rerank。`text-embedding-*` 只出现在模型列表过滤测试。资产约百～300 行：SQL `LIKE` + 短名/别名足够。**拒绝为本特征引入 RAG**（不可逆，需 ADR + Recall@5 检索评估集）。公开能力无 `q` 是 API/产品缺口，不是缺向量。

---

## 3. LLM 配额：算法约束，backend 票

旧 FR-10 / ADR-0014 / T-06 对 algo 的含义：

- 规划 / 修复 / 评分 **必须**走同一 `llm_chat` 闸。市场 verify **不调**模型，不要为 FR-10 去扩 `call_tool`。
- 套餐闸与 provider 预算两本账：用户看见套餐文案；provider 尽且套餐未尽 **不得**映射成 `QUOTA_EXCEEDED` 字样（旧 ADR-0014）。
- 效果评估（下一程序）必须 **按租户分流**：BYOK 与平台 Key 不得混成一个准确率。
- 租户换 Key = 静默换效果；无 per-tenant 评估门。v2 第一波不建该门，只建套餐闸。

algo **不实现**接线，也不把 T-06 改写成算法票。

---

## 4. 评估集：现状与「下一程序」草稿（本波不施工）

**当前条数 = 0。禁止报准确率。**

若（且仅若）§1.4 触发条件满足，四份集的**最低契约**如下——复制旧诊断计划，**不是**本程序票：

| 集 | 任务 | 主指标 | 基线① | 规模 |
|---|---|---|---|---|
| `eval-set-planner-v1` | HTML 快照 → FlowConfig → 快照上执行选择器 | 字段级 Recall@required_fields | 规则 `h1/h2` + `a[href]` + `rel=next` | ≥60（复杂抽取） |
| `eval-set-scoring-v1` | SKILL.md → 四维；对齐 `capability-library/taxonomy/rubric.md` | 维级二次加权 kappa + overall MAE | 章节/字数/Example 启发式 | ≥50 |
| `eval-set-mcp-verify-v1` | server **夹具**（非 50 个真进程） | L0/L1 与金标 health 一致 | 确定性夹具 | ≥50 |
| `eval-set-probe-v1` | 题 + 已知真伪渠道 | spoofed 召回（漏套壳代价高） | 现 6 题启发式 | ≥50 题 + 金标渠道 |

纪律（skill 红线，写入下一程序）：分层（典型/边界/困难/对抗/历史）；dev 70 / test 30 test 冻结；IAA≥80%；分数绑版本；每轮只改一个变量；负向轮保留；禁止 ROUGE 评选择器；禁止未校准 LLM-as-judge。

规划对抗样本：**不要**主打已剥掉的 HTML 注释；用可见文本 / `html_snippet` 角色覆盖（P-AA-09）。

`real_world_effect` 无运行痕迹时应允许「证据不足」，禁止强迫 1–10（开放问题 Q-A2）。

---

## 5. 降级链与选型（纪律，非本波实现）

```
主：租户激活模型或平台公共默认 + 任务 prompt vN
 ↓ 超时 / 5xx / 429 / JSON 校验失败（现有候选链）
备：同供应商下一候选（已有；跨级降质要记评估分——下一程序）
 ↓ 耗尽
兜底（现网缺失）：
  规划 → 规则选择器，标 uncertain，禁止自动 register
  评分 → 跳过，AI 字段保持空
  相似 → 只跑 content_hash
  MCP → unknown/down，不假装 healthy
  探针 → offline
```

候选链 **不是**规则层。无第三层 = 外部 API 抖动时向导停。是否对用户展示「简易规则模式」问 `/pm`（Q-A1），**本波不实现规则规划器**。

选型：先有评估集版本，再比主指标 / 次指标 / P95 / 单次成本。「换 GPT-4o / Kimi / DeepSeek」若说不出「当前方案在 vN 哪项不达标」，回答是 **不换**。换协议（openai → anthropic/gemini）视为换模型：原生适配器丢温度、gemini 把 system 塞进 contents（P-AA-10）。

---

## 6. 孔洞清单（实现债；v2 第一波不要修算法孔）

与旧 P1–P16 同向，2026-09-08 仍在。摘与冻票相关的：

| ID | 孔 | 本程序处置 |
|---|---|---|
| P6 | 试采主指标错误 | 产品：FR-72 冒烟+人工。**不**在本波改成字段级评估 |
| P7 | MCP 空参即 healthy | 不改判定，除非带 mcp-verify 评估 diff（下一程序） |
| P8 | 评分 MODEL 忽略 | `ENABLED` 保持 false |
| P9 | similar 挤占 scoring 预算 | 不要自动跑；拆 `usage_dim` 下一程序 |
| P10 | 套餐闸未进 `llm_chat` | **backend 票**，本波应冻 |
| P11 | 探针 6 题 / 0.15 | 保持旁路；改阈值先换评估 |
| P15 | 公开 score/tier 可来自 AI | 产品不变式：未校准不展示 |
| P4/P16 | HTML 无隔离；`max_pages` 只靠 prompt | 安全债，可跟采集 Wave stub，**不是**评估集票 |

**迭代纪律**（有评估集之后才适用）：一变量一轮；分数写 `xx%（eval-set-planner-v1）`。

---

## 7. 给下游（非 FR，是约束）

| 给谁 | 内容 |
|---|---|
| `/pm` | **不要冻算法施工票。** 冻「禁止效果数字 / 禁止校准前开评分 / 探针旁路 / 评估集下一程序」。不要承诺 95% 召回。天花板经验约 90%，先有 IAA 再谈。官网 AI 句按 §1.2 改口。 |
| `/architect` | Wave 0/1 角色裁剪：`/algo` = N/A（施工）。不要把空 eval 目录写进 T-xx。向量库/微调/新 LLM SDK/LiteLLM 替换：**拒绝**。规划只见 `llm_chat`。FR-10 留在 backend 配额叶子。 |
| `/backend` | 只接套餐闸与入队租户。**不要**「顺便」改 prompt、打开评分、改 0.15、改 MCP healthy 判定。本帽未改任何调用代码。 |
| `/qa` | 本波仍是契约测试。不要把 mock JSON 标成效果门。GWT-10.* 必须经 `ai/plans` 真路径测闸，禁止只测 `QuotaService`。 |
| `/sre` | 评分打开前要有预算熔断演练——本程序默认不开。成本告警阈值无月调用量（Q-A6）则不做贵模型阶梯。 |
| `/frontend` `/designer` | 公开卡片：未校准分不要做成徽章。向导文案对齐「辅助 + 确认」。 |
| `/analyst` | 质量分 / 技能均分 / 探针伪装次数 **禁止当 OEC**（旧蓝图 §1/§4）。上线后评估召回 vs 试采通过率会分叉 = 漂移信号（下一程序）。 |
| `/data-collector` | 本波不采评估 HTML（版权）。 |
| `/miner` | 评分/similar 仍是线上 LLM，不是离线模型。hash 折叠基线归确定性同步，不归 miner 训练。 |

---

## 8. 开放问题（仍归本角色或必须问人）

旧 spec 已关、v2 建议 **不要重开**：规划未达 80% 是否禁止 register（用试采+人工）；探针是否熔断（旁路）；LiteLLM 是否已集成（否，Q-LLM 不代选）。

| ID | 问题 | 阻塞 | 需要谁 | v2 建议 |
|---|---|---|---|---|
| Q-A1 | 规则规划兜底是否对用户可见 | 降级 UX | `/pm` `/designer` | 本波不实现兜底；只问要不要写进下一程序 |
| Q-A2 | `real_world_effect` 无证据：禁维 / null / 强制低分 | 评分 schema | `/pm` | 评分未开，不挡 Wave 0/1 |
| Q-A3 | BYOK 模型不在评估白名单：拒 / 警告 / 强制平台模型评分 | SaaS 质量隔离 | `/pm` `/architect` | 本波只做套餐闸，不做效果白名单 |
| Q-A4 | MCP 空参失败落哪一档（healthy/degraded/unknown）及是否影响 enable-host | 徽章 | `/pm` | FR-26.2 已给无 MCP=未知可上架；空参失败未写。本波不改代码 |
| Q-A5 | 同步后是否对重名自动跑 `similar_suggest` | 误合并 + 烧评分预算 | `/pm` | **否** |
| Q-A6 | 月成本上限与调用量 | 选型阶梯 | `/pm` | 无数字则不做贵模型；本波无选型 |
| Q-A7 | 公开卡片是否展示 `score`/`tier` | 商店信任 | `/pm` `/designer` | **不展示或标未评** |
| Q-A8 | 评估集版权：自有夹具 vs 公开页快照 | 满 50 | `/pm` 法务 | 踢出本程序（同旧 NFR-06） |

---

## 9. 自检

| 项 | 状态 |
|---|---|
| 评估集 ≥50 带标注口径 | **计划仅作下一程序草稿；文件未建**（正确） |
| 最便宜基线先跑 | 规定了①；**未跑数** |
| 降级链主→备→规则 | 写下；现网缺规则层；本波不施工 |
| 效果数字带评估集版本 | **无数字可报**（正确） |
| 每轮单变量 | 纪律已写，待有评估脚本 |
| 未点名选定厂商 | **遵守**（`gpt-4o-mini` 仅现网默认配置） |
| 未写 CRUD/UI | 遵守 |
| 未改模型调用代码 | **遵守** |
| 未引入 RAG | **拒绝** |
| 三问已答 | 可卖=诚实流程+配额真闸；示意=代理质量；**不冻算法施工票** |
| 坑点 | 仅复验已有 P-AA-01…10，不新开无新锁项的条目 |

---

## 10. 关键代码锚点

| 主题 | 路径 |
|---|---|
| 规划 prompt / JSON | `backend/services/ai_planner/prompting.py` |
| LLM 调用与 failover | `backend/services/ai_planner/llm_client.py` |
| 试采判定 | `backend/services/ai_planner/orchestrator.py` `_judge_test`；试采 `enqueue` **不传** `tenant_id` |
| 入队门面丢租户 | `backend/services/spider_service.py` `enqueue` 未转发 `tenant_id` |
| HTML 截断与剥注释 | `backend/services/ai_planner/url_guard.py` |
| 协议温度 / gemini system | `backend/services/llm_protocol/adapters.py` |
| 资产评分 | `backend/services/skill_scoring_service.py` |
| rubric | `capability-library/taxonomy/rubric.md` |
| tier 派生 | `backend/services/skill_service.py` `derive_tier` |
| 相似 | `backend/services/skill_service.py` `similar_suggest` |
| 公开 score/tier | `backend/app/api/v1/public_skills.py` `PublicSkillResponse` |
| MCP 抽样 | `backend/services/mcp_bridge.py` `verify_plugin_server` |
| 无 MCP → degraded | `backend/services/plugin_service.py` `verify_plugin` |
| Item 质量分 | `scrapy/pipelines/quality.py` |
| 探针 6 题 / 0.15 | `backend/services/channel_probe_service.py` |
| LLM / 评分配置 | `config/default/llm.yml` · `config/default/skills.yml` |
| 配额未接线 | `backend/services/quota_service.py` `check_llm_tokens_month` |
| 官网示意句 | `frontend/official/src/pages/Home.tsx` · `components/home/AiFlowSection.tsx` · `SkillsSection.tsx` |
| 旧产品边界（输入） | `.sdlc/feat-four-pillars/01-define/spec.md` FR-10/61/72、T-23、NFR-06 |
| 旧方案裁剪（输入） | `.sdlc/feat-four-pillars/02-shape/contract.md` §8 `/algo` N/A；ADR-0014；T-06 |
| 度量禁区（输入） | `.sdlc/feat-four-pillars/01-define/metrics-blueprint.md` §1/§4 |
