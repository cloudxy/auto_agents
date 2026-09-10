# 数据挖掘诊断 · feat-four-pillars（refresh）

> 上游：`CONTEXT.md` · `01-define/spec.md` v1 · `metrics-blueprint.md` · 现网评分/质量代码  
> 作者：/miner（as-of 纪律）｜日期：2026-09-07｜refresh vs 同日初稿  
> 下游：`/pm`（动作与标签）· `/data-warehouse-engineer`（DWD/DWS，**仍不存在**）· `/analyst`（`metrics.yaml` **仍不存在**；蓝图已有）· `/dba`（事件表）· `/algo`（LLM 评分 prompt，本角色不改）  
> **本文件不是训练产物。未训练、未上线模型、未新增产品 FR。**

---

## 0. 结论（先说清楚）

**本仓库没有可部署的挖掘面。** 有的是启发式打分、LLM 评审、以及按 `score`/`tier` 的列表排序。没有离线模型、没有特征表、没有时间切分、没有独立金标。

| 检查项 | 证据 | 结果 |
|---|---|---|
| ML 依赖 | 根 / `backend/pyproject.toml` 无 sklearn / xgboost / torch / lightgbm / mlflow / onnx；源码 0 命中 `fit`/`KMeans`/`embedding` 训练 | **无训练栈** |
| 数仓 | `dwd_` / `dws_` / `ads_` / `metrics.yaml` 全库 0 命中（warehouse 诊断同结论） | **无特征层** |
| 动作定义 | `spec.md` 范围外：「数仓 ODS/DWD、metrics.yaml 物理层、**离线模型** → 下一轮」 | **pm 已推迟建模** |
| 现有「分数」 | 见 §2：质量公式 / 代理加权 / 探针 10 维 / LLM 四维 / `derive_tier` | **全是规则或 LLM，0 个监督模型** |

把其中任何一个分数当监督学习的 y、再用同一套输入当 X，就是标签泄漏。复杂模型必须先证明超过规则基线；四柱里**没有一柱跨过这道门**。

**建模前必须先有的东西（缺一则停）：** 见 §9。在那之前 miner 只诊断、不训练、不把「流失模型 / 渠道风控模型 / 资产排序模型」写进 spec。

### 0.1 相对初稿的更正（本 refresh 核实）

| 初稿说法 | 现网 | 处置 |
|---|---|---|
| 到期租户「登录拒绝」 | `AuthService.authenticate` / `load_auth_identity` **不读** `tenants.status`。`test_expired_tenant_login_rejected` 只断言巡检把 `status` 写成 `expired`，**没有 POST /login** | 合约状态 ≠ 不能用产品。用 `status=expired` 当 churn y 更错 |
| `RECOVER_SCORE` 写死 0.5 | `ProxyHealthService` 读 `PROXY_HEALTH.RECOVER_SCORE`（默认 0.5） | 可配；仍无历史快照 |
| 公开列表丢掉 `recommended` | 技能公开闸 `PUBLISHED_STATUSES = (stable, recommended)`；**能力广场**仍 `status="stable"` 一种 | 两套公开闸不一致（analyst Q7） |
| 代理剔除阈值单一 | 健康服务 Dynaconf 默认 **0.5**；`ProxyMiddleware` 用 Scrapy Settings 点号键，**静默回退 0.2**，且 `scrapy/settings.py` 未平铺 `PROXY_HEALTH_*` | 线上线下两套阈值 |
| 质量公式只伤 harvester | `flow_generic`/`build_item` 把字段 dict `json.dumps` 进 `content`，空抽取也是 `"{}"`，**核心维饱和** | 新增失效边界 |
| `metrics.yaml` 与蓝图皆无 | `metrics-blueprint.md` 已有；`metrics.yaml` 仍无 | 北极星 WACT 是产品口径，不是特征口径 |

---

## 1. 角色边界与拒绝清单

| 我管 | 不归我 |
|---|---|
| 离线预测 / 分群 / 异常的问题定义、as-of、泄漏、基线、失效边界 | 线上 LLM/RAG（→ `/algo`：采集规划、技能评分 prompt、similar_suggest） |
| 现有启发式是否被误当成「模型」 | 产品 FR（→ `/pm`；Wave 0/1 已冻结且不含离线模型） |
| 特征在预测时刻是否可拿到 | 数仓分层与 metrics.yaml（→ warehouse / analyst） |
| 现在不该建模的清单 | 实现代码 / 训练作业 |

**本回合遵守**

- 不训练，不引入 ML 依赖。仓库无 ML 包是正确状态。
- 不把「建流失 / 渠道风控 / 资产 LTR」写成 FR（spec 已把离线模型放到下一轮）。
- 动作未定义的候选：**只框问题、不建模型**。

**miner 输入契约（SKILL.md）**

| 输入 | 现状 |
|---|---|
| 带量化动作的业务问题 | **缺失。** 四柱启发式都有闸门，没有「预测出来做什么、处理能力上限、主指标」 |
| 数仓 dwd_/dws_ | **不存在** |
| metrics.yaml | **不存在**（有 `metrics-blueprint.md`：WACT / 注册登录率 / TTFV / 订阅；明确禁止单任务质量分、技能平均分当北极星） |

没有数仓与动作定义，任何离线分数都不可部署。下面的特征字典是**候选清单**，不是可训练特征表。

---

## 2. 数据资产盘点（OLTP 即全部）

平台没有分析层。所有「分数」写在业务表或 Redis，和线上动作共用同一时点。

### 2.1 实体与事件（能当样本的东西）

| 实体 | 表 / 键 | 时间列 | 缺什么 |
|---|---|---|---|
| 租户 | `tenants` | `created_at` / `expires_at` / `status` | `status=expired` 由到期巡检回写 **expires_at**；**登录不读该字段**。不能当流失标签，也不能当「已无法使用」 |
| 用户 | `users` | `created_at` / `updated_at` | **无 `last_login_at`**。失败只在 Redis `login_fail:` TTL；成功登录不落事实表。spec FR-15 规划 `login_succeeded`，**未落地** |
| 采集任务 | `spider_tasks` | `created_at` / `started_at` / `completed_at` | 有 `created_by`，弱活跃信号。`status` 提交时还是 pending |
| 采集结果 | `spider_results` | `created_at` | `quality_score` 是管道公式，不是金标。市场候选与租户结果同表（`source=marketplace`） |
| LLM 用量 | `llm_token_usage` | `stat_date`（日聚合） | 无操作人；不能还原单次调用时点 |
| 配额 | `tenants.quota` JSON + Redis `quota:count:*` TTL 60s | 无超限事件表 | 超限抛 429 `QUOTA_EXCEEDED`，**不落事实**。FR-15 规划 `quota_exceeded`，未落地 |
| 渠道探针 | `channel_probe_results` | `created_at` + `batch_id` | `verdict` 由同批启发式产生；**不能当监督标签**。只存 scores，不存 raw 回包 |
| 渠道调度 | `channel_events` | `created_at` | 动作本身（disabled/enabled）+ 当时 usage/limit。用它预测「会不会被禁用」= 标签泄漏 |
| 技能 / 资产 | `skills` / `capability_assets` / `skill_reviews` | `reviewed_at` / `updated_at` | `score` 人工权威；`ai_suggested_score` 是 LLM。**无人工分时 `derive_tier` 用 AI 分**，官网首页按 S/A 精选 |
| 插件验证 | `capability_plugins.health_status` | `last_verified_at` | 无 MCP → 今日写 `degraded`（设计拟 `unknown`） |
| 代理 | Redis `spider:proxy:scores` / `spider:proxy:stats` | `last_check` 字符串 | **无历史快照**；全期累计 success/fail |
| 审计 | `operation_logs` | `created_at` | 无 tenant_id、无会话、无访客 |
| 市场安装 | 设计中的 `capability_installs` | — | **表不存在**（全库 0 命中 `listing_state` / `POWER_MARKET` / `capability_installs`） |

### 2.2 现有「分数」一览（0 个离线模型）

| 名称 | 实现 | 公式 / 规则 | 下游动作（已存在） | 是不是模型 |
|---|---|---|---|---|
| 采集质量分 | `scrapy/pipelines/quality.py` | 字段完整率×50 + 核心非空×30 + 进程内去重×20 | AI 试采 `avg < 40` 失败（硬编码）；后台四档；Dashboard **只画最近 1 个完成任务** | 否 |
| 内容指纹 | consumer `md5(url+title+content)` | 增量跳过入库 | `params.incremental=true` 时丢弃 | 否（去重键） |
| 请求指纹 | `FingerprintMiddleware` | `md5(url)[:8]` | 仅日志 | 否（命名易混） |
| 质量去重指纹 | Quality pipeline | `md5(url\|title)`，**单进程 `_seen`** | 重复条 dup_score=0 | 否 |
| 代理分 | `ProxyMiddleware._update_stats` | 有成功：`success_rate×0.6 + (1-min(lat/10,1))×0.4`；无成功=0 | 加权抽代理；Scrapy 侧低于 **0.2**（点号键 miss）剔除 | 否 |
| 代理恢复 | `ProxyHealthService` | HEAD 成功 → `RECOVER_SCORE`（配置，默认 0.5）；低分阈 **0.5** | 低分代理复活 | 否 |
| 渠道真伪 | `_score_probe_batch` | 10 维 0/0.5/1 + 三态；`ref_sim < 0.15` → spoofed | **只通知** `channel.probe.spoofed`，**不下线**（spec FR-61 冻结） | 否 |
| 渠道额度 | `channel_scheduler_service` | 窗口 `SUM(quota) >= limit` | 自动 status=3 + 冷却恢复 | 否（阈值闸） |
| 技能评分 | `SkillScoringService` | LLM 四维 1–10；**默认 `SKILLS.SCORING.ENABLED=false`** | 只写 `ai_suggested_score` / `rubric_ai` / `reviews(ai)`，永不写人工 `score` | 否（LLM 评审） |
| 档位 | `derive_tier` | 人工分优先，缺则 AI 分；S≥8.5 / A≥7.0 / B≥5.0 / C | 官网首页滤 S/A/`recommended`；列表 `sort=score\|tier` | **排序启发式，不是 LTR** |
| 同类技能 | `SkillService.similar_suggest` | 同 category 喂 LLM 出簇 | 人工 `similar_confirm` 才写 `similar_to` | 否 |
| 插件健康 | `plugin_service.verify_plugin` | MCP list/call；无 MCP → `degraded` | 未接 enable-host 闸 | 否 |
| 租户配额 | `QuotaService` | 并发 / 结果行数 / 月 token | 429；**无事件行** | 否 |
| 租户到期 | `expire_overdue_tenants` | `expires_at < now` → `status=expired` | **登录路径未消费该状态** | 否（合约回写） |
| LLM 巡检 | `llm_health_patrol` | 1-token 真测 | `health_status` 故障转移 | 否 |

**结论：** 平台已经在「打分」和「按分排序」，但全部是**可解释规则或 LLM 评审**。排序面（`sort=score`、首页 S/A）会放大 AI 分在无人终评时的权重，仍不是学习排序。

---

## 3. 四柱问题定义（动作优先）

模板纪律：没有决策用途的模型不要建。每柱先写「预测出来做什么」；做不到的标 **BLOCKED → /pm**。spec 已把离线模型放到下一轮，下面只框问题，防止回流。

### 3.1 智能采集 · 源/任务/条目质量

| 项 | 内容 |
|---|---|
| 业务问题 | 试采与生产任务产出空字段 / 重复 / 反爬空壳；质量分被当成「抽对了」 |
| **预测出来做什么** | **未定义。** 今日唯一动作：试采 `avg_score < 40` 则失败，最多 2 轮修复（`orchestrator._judge_test`）。没有「低分条目丢弃 / 低分源降权 / 人工抽检队列」与产能上限 |
| 谁执行 | 系统闸门（已有）+ 未定义的运营抽检 |
| 标签草稿（**禁止用 quality_score**） | 独立金标：人工「字段是否业务可用」；或 as-of 后 T 日内同选择器任务 `completed ∧ result_count>0` |
| spec 冻结 | FR-72：试采通过 + 人工确认才能上线；**官网不得写准确率**。algo：≥40 是代理指标 |

**规则基线应先修的缺陷（建模前的数据质量，不是 FR）：**

1. **分母稀释（核实）**：`field_completeness` 用 `item.fields.keys()`。`BaseItem` 声明 10 列：`task_id/id/title/url/content/source/created_at/updated_at/extra/_quality_score`。打分时 `id/created_at/updated_at/_quality_score` 恒空（`_quality_score` 写在完整率之后），分母被内部字段系统性拉低。
2. **`REQUIRED_FIELDS` 死配置（核实）**：`QUALITY_CHECK_REQUIRED_FIELDS` 已映射进 Scrapy Settings，`open_spider` 读入 `self.required_fields`，**`process_item` 从未使用**。真正拦 url 的是 `ValidatePipeline`（优先级 300）。
3. **三套指纹（核实）**：质量管道 `md5(url\|title)` 仅进程内；consumer `md5(url+title+content)` 跨任务但只在 `incremental=true`；中间件 `md5(url)[:8]` 只打日志。跨任务重复仍可拿满分。
4. **`skill_harvester` GitHub 目录条目 `content=""`（核实）**：核心三维必伤 content。候选审核**不消费**该分，但分数仍入库，污染任务级 avg / Dashboard 四档。
5. **`build_item` 把字段 JSON 塞进 `content`（本 refresh 新增）**：`scrapy/utils/selector_engine.py`。空抽取也是 `"{}"`，`content` 永真 → 核心维 30 分几乎送满。试采主路径 `flow_generic` 正好走这条。**非空垃圾轻松过 40。**
6. **无单测锁公式（核实）**：仓库无 `QualityCheckPipeline` 测试。`avg<40` 闸只在 `test_ai_planner.py` 用 mock `avg_score` 覆盖。

**建议标签（交给 /pm，不实施）：**

```sql
-- 草稿：任务级「采集失败」——禁止用 quality_score 当 y
SELECT t.id AS task_id,
       CASE WHEN t.status = 'failed'
              OR COALESCE(t.result_count, 0) = 0
            THEN 1 ELSE 0 END AS is_collect_fail
  FROM spider_tasks t
 WHERE t.created_at < :asof
   AND t.created_at >= :asof - INTERVAL 14 DAY
   AND COALESCE(JSON_EXTRACT(t.params, '$.source'), '') <> 'marketplace'  -- 排除入站候选
```

在 `/pm` 给出「失败后谁做什么、每天处理几条」之前：**不建模。** 规则基线 = 修分母（只计业务字段）+ 核心全空拒收 + 跨任务 hash 降权 + 阈值 40 可配。

### 3.2 SaaS · 租户流失 / 用量分群 / 配额耗尽

| 项 | 内容 |
|---|---|
| 业务问题 | CONTEXT 定义配额，未定义 churn。合约到期与行为沉默是两件事 |
| **预测出来做什么** | **未定义。** 发券？CS？升级提示？冻结前预警？产能未知 |
| 标签陷阱 | `status='expired'` = `expires_at` 回写，**不是行为流失**。用它当 y + `expires_at` 当 X = 恒等式。更糟：登录/鉴权**不读**该状态，过期租户仍可能继续产生任务与 token |
| `users.is_active` | 管理员开关，不是流失 |
| 活跃代理 | `QuotaService.usage_by_member`：`last_active_at = MAX(spider_tasks.created_at)`，全历史，不是登录 |

**三个不该混在一个模型里的问题：**

| 子问题 | 事件定义（需 /pm） | 现在有没有数据 |
|---|---|---|
| 合约流失 | 到期未续费 | `expires_at` + `status`（标签与特征同源；且过期≠停用） |
| 行为流失 | as-of 后 N 天无任务、无 token、无登录 | **无登录事实**；任务与 token 日表可用；样本=租户数（小） |
| 配额耗尽预警 | as-of 后 7 天内撞月 token / 结果行数 | 有日用量与限额；这是**外推规则**，不是分类器。无 429 事件无法校准「真的撞过」 |

**分群：无监督用途未定义。** 可执行的规则分箱（不必聚类）：用量/配额比；生命周期（新/活跃/沉默）；产品面（只爬虫 / 只 LLM / 都用）。群数上限 = 运营能同时维护的策略套数（通常 3–6）。**N 个租户不够撑 K-Means。**

**流失标签草稿（行为，排除合约到期）：**

```sql
-- 草稿：需 /pm 确认「活跃」= 提交任务 还是 登录（登录表还不存在）
-- 间隔期 7d，标签窗 30d
SELECT tn.id AS tenant_id,
       CASE WHEN COUNT(t2.id) = 0 AND COALESCE(SUM(u2.total_tokens),0) = 0
            THEN 1 ELSE 0 END AS is_churned
  FROM tenants tn
  LEFT JOIN spider_tasks t1
         ON t1.tenant_id = tn.id
        AND t1.created_at >= :asof - INTERVAL 90 DAY
        AND t1.created_at <  :asof
  LEFT JOIN spider_tasks t2
         ON t2.tenant_id = tn.id
        AND t2.created_at >= :asof + INTERVAL 7 DAY
        AND t2.created_at <  :asof + INTERVAL 37 DAY
  LEFT JOIN llm_token_usage u2
         ON u2.tenant_id = tn.id
        AND u2.stat_date >= DATE(:asof) + INTERVAL 7 DAY
        AND u2.stat_date <  DATE(:asof) + INTERVAL 37 DAY
 WHERE tn.status = 'active'
   AND tn.created_at < :asof - INTERVAL 30 DAY
 GROUP BY tn.id
HAVING COUNT(t1.id) >= 1
```

**硬阻塞：** 动作未定义、无登录事件、租户 N 小、`status`/`expires_at` 泄漏、无数仓 as-of 快照。spec 北极星是 **WACT（完成且出数的企业周去重）**，那是分析指标，不是 churn 标签。

### 3.3 中转站 · 渠道伪装 / 额度异常

两个问题，不要合成一个「渠道分」。

#### A. 真伪（点异常 + 集体异常）

| 项 | 内容 |
|---|---|
| 业务问题 | 渠道声称某模型家族，行为不像 |
| **今日动作** | 写 `channel_probe_results` + 通知。**不自动下线**（FR-61 冻结；下线只属于额度调度器） |
| **模型动作** | **未定义。** 自动 status=3？复核队列？每天几条？ |
| 金标 | **没有。** `verdict` 就是启发式输出。用它训练 = 蒸馏规则，离线会「完美」 |

规则基线已存在且应保持可解释。已知失效边界（代码路径，不是坏例统计）：

- `family=None` 时身份矛盾不参与 verdict（防误杀）→ 未知厂商**漏报**
- `ref_similarity < 0.15` 才 spoofed → 弱伪装判 `original`
- 知识截止题写死「2025 年事件」：日历过了正品也会「知道」，该维失效
- 无参考渠道时只靠身份词 + 逐字重复
- spoofed **不驱动调度器**（产品选择；误杀正品会掉网关容量）

#### B. 额度

调度器已用窗口用量硬阈值。预测「明天会超限」只有在动作是「提前切流 / 提额」且有处理上限时才有价值。今日动作是超限当下线，**没有提前量需求 → 不建模。**

**禁止：** 用 `channel_events.action='disabled'` 当 y、用同条 `usage/limit_quota` 当 X——同一动作写入。

### 3.4 Power Market · 资产评分 / 源质量 / 上架

设计把 `listing_state` 与 `status`/`score` 分列（D6/D7）：第三方同步**绝不自动 listed**。这是产品闸门，不是排序学习。代码里 **`listing_state` / 安装表仍未建**。

| 子问题 | 动作 | 能否建模 |
|---|---|---|
| 资产质量评分 | LLM 建议 + 人工终评；tier 派生 | **不要用模型替代人工权威。** 「LLM vs 人工」校准归 `/analyst`，不是训练任务 |
| 上架预测 | 平台超管 PATCH listing；D7 禁止自动 listed | **不要建模。** 学的是运营偏好，上线会绕过人工闸 |
| 安装/转化 | 设计有安装表；商店面默认关 | 无样本 |
| 源质量 | sync_state / parse_error / hash 历史未落地 | 先规则 |
| 重复技能 | LLM similar_suggest + 人工确认；hash 折叠 | 哈希折叠是正确基线。near-dup embedding **无动作**（unlist 哪一侧？） |

**资产排序 / 标签泄漏：**

- 技能公开响应含 `score`/`tier`。列表支持 `sort=score|tier`。官网首页用 `tier ∈ {S,A} ∨ status=recommended` 精选 6 条。若用「是否出现在首页」当转化 y，特征里的 `tier`/`score` 就是答案。
- **无人终评时 `derive_tier(None, ai_score)` 仍出 S/A**，首页会被 AI 文案分驱动。这是治理泄漏，不是 LTR 机会。
- `real_world_effect` 由 LLM **读 SKILL.md 文案**打出，无安装/成功率/卸载。文档自夸抬该维 = **文案泄漏**。
- `maintenance` 只靠 prompt 里一句 `source_url` 提示，无 git 活跃度。
- `SKILLS.SCORING.MODEL` 配置了但被忽略（回退默认供应商）；`PROMPT_VERSION = "v1"` 硬编码，yml 的 `PROMPT_VERSION` 不读。改 prompt 分数漂移无法对齐版本。
- 能力公开列表只滤 `stable`，技能公开滤 `stable+recommended`：同一套 `score` 在两个入口样本不同。用公开曝光当 y 会混总体。

---

## 4. 启发式 vs 模型：决策矩阵

| 场景 | 规则基线够不够 | 上模型的前提 | 现在做不做 |
|---|---|---|---|
| 条目空字段 / 进程内重复 | 够；先修分母与 content JSON 饱和 | 金标「业务可用」+ 抽检产能 | **不做模型** |
| 代理选择 | 够；缺窗口衰减、快照、阈值对齐 | 多站点差异大到规则误伤 | **不做**；先窗口成功率 + 平铺 Scrapy 配置 |
| 渠道真伪 | 10 维规则 + 通知 | 人工确认的 spoofed 金标、误杀成本、自动下线权 | **不做**（FR-61 已冻结不下线） |
| 渠道额度 | 硬阈值正确 | 只有「提前切流」动作时才要预测 | **不做** |
| 租户配额耗尽 | 用量/限额外推 | 429 事件落地后可校准规则 | **规则即可** |
| 租户行为流失 | 数据与动作都缺 | 登录事件 + 动作 + N 足够 | **不做** |
| 租户分群 | 规则分箱即可 | 运营要差异化策略 | **不做算法聚类** |
| 技能/资产分数 | LLM+人工是治理流程 | 不得用公开曝光当 y | **不做排序模型** |
| 源质量 | 事件还没有 | 源表 + job 历史落地后先规则 | **不做** |
| 安装转化 | 无表无流量 | 商店面上线后的漏斗归 `/analyst` | **不做** |

---

## 5. 泄漏风险清单（五类对照）

### 5.1 时间泄漏

| 风险 | 位置 | 说明 |
|---|---|---|
| 维度表当前状态 | `tenants.status` / `users.is_active` / `capability_assets.status` / 设计列 `listing_state` | as-of 之后会被巡检、人工上下架、矫正 API 改写。必须用事件流或日快照重建，禁止 JOIN 当前行 |
| `updated_at` | 几乎所有业务表 | 未来事件会刷新，不能当「最后活跃」 |
| 代理全期累计 | `spider:proxy:stats` | 无 as-of；线上也对「曾经很好、最近全死」反应慢 |
| LLM 月用量 | `llm_token_usage.stat_date` | 必须 `stat_date < :asof`；SUM 全期则泄漏 |
| 质量分四档 | 入库时冻结的 `quality_score` | 分数本身时点安全；危险的是事后用「任务最终 status」解释当时分数 |

### 5.2 切分前统计

尚无训练集。若有人 `scaler.fit(全表租户用量)`：租户极少，测试集均值几乎等于泄漏标签。**任何群体统计必须 as-of 且排除自身。**

### 5.3 标签泄漏（本平台最危险）

| 若预测… | 禁止当特征 / 禁止当标签 | 原因 |
|---|---|---|
| 租户流失 | `status`、`expires_at`、`deleted_at` | 标签由这些字段定义或事后回写；且 expired≠停用 |
| 采集失败 / 试采通过 | `quality_score`、试采 `passed` | 规划器已用分数当闸；用分数预测「是否通过」是恒等式 |
| 渠道伪装 | `verdict`、`scores.*` 再当 X | y 由同一函数生成 |
| 渠道将禁用 | `channel_events.usage` 与 action 同事务 | 动作写入用量上下文 |
| 资产将上架 / 上首页 | `score`/`tier`/`status`/`ai_suggested_score` | 运营与前端按它们决定曝光；D7 禁止自动 listed |
| 插件可分发 | `health_status` 当前值 | 验证管线事后写入 |
| 实测效果 | SKILL.md 里的效果陈述 | 与 `real_world_effect` 同源 |

### 5.4 实体泄漏

租户 / 渠道 / 资产会跨多个 as-of 点重复出现。随机切行会让模型记住「渠道 #12 经常 spoofed」。切分必须：**时间顺序 + 实体不跨集**。

### 5.5 未来聚合

| 风险 | 例子 |
|---|---|
| 套餐流失率 | 全期租户算「同类套餐流失率」且不排除自身，小样本下等于泄漏 y |
| 源级平均分 | 含未来任务的 `AVG(quality_score)` 预测本任务质量 |
| 插件安装数 | 表还不存在；一旦有，必须 as-of 前累计 |

### 5.6 线上线下一致性（现在就存在的口径分裂）

这些不是训练泄漏，但若将来做特征，会直接造成 offline≠online：

| 分裂 | 离线容易用的 | 线上实际 |
|---|---|---|
| 去重 | `spider_results.content_hash` 跨任务 | 质量管道 `_seen` 仅进程内；hash 公式还少 `content` |
| 质量分母 | 业务字段 | `item.fields` 含内部列 |
| 核心维 | 选择器字段是否抽对 | `content` 可能是 JSON 整包，永非空 |
| 「指纹」一词 | 探针 10 维 / 条目 md5 / 中间件 8 位 url hash | 三套完全不同 |
| 代理阈 | Dynaconf `PROXY_HEALTH.LOW_SCORE_THRESHOLD=0.5` | Scrapy 点号键 miss → 0.2 |
| 代理分 | 若从 DB 重建 | 只在 Redis，重启即丢 |
| 技能正文路径 | `skills.file_path` | Power Market 设计改为 `resolve_origin_path`；用错列读空文案，分数漂移 |
| 公开列表 | 管理端全状态 | 技能：`stable+recommended`；能力：仅 `stable`；Wave 1 还要 listing∩许可 |
| 评分 worker | 离线可对全库打分 | 默认 `SKILLS.SCORING.ENABLED=false`；打开后无校准 |

**时间倒推测试：** 本回合无模型，未做。将来任何分数若把特征窗前移一个月就崩，先查紧邻 as-of 的状态字段。

---

## 6. 特征缺口（按柱）

缺的是事件，不是算法。

### 6.1 采集

| 缺口 | 为什么需要 | 现状 |
|---|---|---|
| 条目级金标 | 与公式独立的 y | 无；也无质量管道单测 |
| HTTP 状态 / 反爬命中 | 区分空壳与选择器错 | 未进 `spider_results` |
| 选择器版本 as-of | 特征必须是当时的 params | `params` 是任务 JSON 全文，无版本表 |
| 站点级窗口成功率 | 源质量 | 无 dws |
| 跨任务重复率 | 替代进程内 dup_score | `content_hash` 有，缺 as-of 窗口聚合 |
| Worker / 代理当时分 | 失败归因 | Redis 无历史 |

### 6.2 SaaS

| 缺口 | 为什么需要 | 现状 |
|---|---|---|
| 登录成功/失败事实 | 行为流失、激活（蓝图 D2） | Redis TTL 失败计数；成功不落库 |
| 配额超限事件 | 预警与分群 | 只 429 |
| 套餐变更事件 | 合约流失 vs 降配 | `quota` JSON 被 PATCH 覆盖，无历史 |
| 成员级 LLM 用量 | 用量分摊 | `llm_token_usage` 按 provider/model/日 |
| 租户日快照 | as-of 状态 | 无 ods/dwd |

### 6.3 中转站

| 缺口 | 为什么需要 | 现状 |
|---|---|---|
| 人工确认的真伪金标 | 有监督优于蒸馏规则 | 只有启发式 verdict |
| 探针 raw / 题版本 | 复现与日历漂移 | 只存 scores；2025 题写死 |
| 按模型家族的延迟基线 | 上下文异常 | 只有单次 vs 参考渠 |
| spoofed→动作闭环 | 否则预测无决策用途 | 仅 notify（FR-61） |

### 6.4 Power Market

| 缺口 | 为什么需要 | 现状 |
|---|---|---|
| 源/组件/安装表 | 源质量与转化 | 设计有，ORM 未扩 |
| git 活跃度 | maintenance 金标 | LLM 猜 |
| 安装后启用/卸载 | real_world_effect | 无 |
| 人工 rubric 覆盖率 | 校准 LLM | `score` 可空；AI 可单独存在并驱动 tier |
| 跨插件 near-dup | 折叠只解字节相同 | hash 不同的真分叉无度量 |

### 6.5 平台级（阻塞所有建模）

- **无 dwd_/dws_/ads_，无 metrics.yaml。** 特征表访问模式无从交给 `/dba`。
- **无 as-of 快照。** 所有状态列都是当前值。
- **无训练/推理特征存储。** 不要把模型分写回现有 `score` / `quality_score` 列（已经 overloaded）。
- **无产品事件。** 蓝图要的 `task_completed` / `login_succeeded` / `quota_exceeded` / `market_subscribe_succeeded` 都还是 FR，不是表。

---

## 7. 现在不该建模的清单（硬）

| ID | 不要做 | 原因 | 何时可以重新讨论 |
|---|---|---|---|
| N1 | 租户 churn 分类/回归 | 动作未定义；无登录；N 小；`status`/`expires_at` 泄漏且 expired≠停用 | `/pm` 定义动作与「活跃」；`/dba` 登录事实；样本量够撑 Precision@K |
| N2 | 用户级流失 | 无会话；`updated_at` 会泄漏 | 同上 |
| N3 | 用 `quality_score` 当 y 的质量模型 | 恒等式（闸门就是它） | 独立金标 + 抽检产能 |
| N4 | 蒸馏渠道 `verdict` 的分类器 | 教师即规则；离线 AUC 会好看 | 人工金标；spoofed 有自动/复核动作（与 FR-61 冲突时先改产品） |
| N5 | 预测渠道将被调度器禁用 | 标签泄漏 | 不要做；阈值已是正确产品 |
| N6 | 资产 listing / 公开曝光 / 首页精选 LTR | D7 禁止自动上架；status/score/tier 泄漏 | 永远优先人工闸；最多做「LLM vs 人工」校准报表 |
| N7 | 安装转化模型 | 无安装表、商店面关闭 | 上线后漏斗归 `/analyst` |
| N8 | 租户 K-Means / embedding 分群 | 无用途、N 小、量纲混乱 | 运营先有 3–6 套策略；规则分箱先跑 |
| N9 | 代理分 learning-to-rank | Redis 无历史；成功标签与抽中代理纠缠（探索偏差） | 先窗口统计规则 + 阈值对齐 |
| N10 | 用 SKILL.md 训练 `real_world_effect` | 文案泄漏 | 安装/调用/卸载遥测 |
| N11 | 在 OLTP 上直接 `fit` | 无时间切分基础设施；会锁生产库 | 数仓 + 只读账号 + 时间切分 |
| N12 | 准确率作为指标 | 流失/伪装/低质都是不平衡问题 | 有动作上限时用 Precision@K / lift |
| N13 | 把 WACT / 技能平均分当模型目标 | 蓝图明确禁止后者当北极星；前者是分析计数 | 分析归 `/analyst` |

**规则优于模型的默认策略：** 四柱先把启发式变成**可配置阈值 + 留痕 + 人工复核**。这不是失败，是省掉特征平台与监控的成本。spec 已同意下一轮再谈离线模型。

---

## 8. 特征字典（候选 · 每个都有 as-of · 不训练）

> 每个特征必须能回答：在 as-of 时刻，这个值是多少？  
> 今日**没有打分服务**。「预测时可获取」= 若规则引擎要复用，数据在不在。

### 8.1 采集（任务级，as-of = 任务提交时刻）

| # | 特征名 | 计算逻辑 | as-of 口径 | 来源 | 缺失含义 | 预测时可获取 |
|---|---|---|---|---|---|---|
| C1 | `src_fail_rate_14d_before_asof` | 同 `spider_name` 失败 / 总任务 | `created_at < :asof AND >= :asof-14d` | `spider_tasks` | 无历史=新爬虫，不是 0 失败 → 缺失标记 | ⚠️ 需聚合；现无 dws |
| C2 | `src_empty_rate_14d_before_asof` | `result_count=0` 且 completed 的比例 | 同上 | `spider_tasks` | 同上 | ⚠️ |
| C3 | `dup_rate_hash_14d_before_asof` | 同租户同 hash 重复 / 总条 | `spider_results.created_at < :asof` | `content_hash` | 无结果=0 | ⚠️ 重查询 |
| C4 | `core_empty_at_parse` | 核心字段全空（规则，**不要看 JSON 包装后的 content**） | 条目产生时 | 选择器字段，不是 `item['content']` | 结构性空 | ✅ 管道内 |

**排除**

| 候选 | 原因 |
|---|---|
| `quality_score` | 标签泄漏 / 与闸门恒等 |
| `spider_tasks.status` 当前值 | 提交时刻还是 pending |
| `AVG(quality_score)` 全期 | 未来聚合 |
| 进程内 `_seen` 去重分 | 不可跨任务复现，offline≠online |
| `content` 是否非空（flow 路径） | JSON 包装后恒真 |

### 8.2 SaaS（租户级，as-of = 每日 00:00 UTC；蓝图业务日是上海，**两套时区未对齐**）

| # | 特征名 | 计算逻辑 | as-of 口径 | 来源 | 缺失含义 | 预测时可获取 |
|---|---|---|---|---|---|---|
| S1 | `tasks_30d_before_asof` | 任务数（排除 marketplace 入站） | `created_at < :asof AND >= :asof-30d` | `spider_tasks` | 0=无采集，信息量 | ✅ T+1 |
| S2 | `tokens_30d_before_asof` | `SUM(total_tokens)` | `stat_date < DATE(:asof)` | `llm_token_usage` | 0=未用 LLM | ✅ T+1（flush 延迟需与 `/backend` 对齐） |
| S3 | `quota_token_util_at_asof` | 月累计 / `llm_tokens_month` | 月界 < as-of | 用量 + `tenants.quota` **快照** | 缺 quota JSON=默认档 | ⚠️ **当前行会被 PATCH** |
| S4 | `days_since_last_task_at_asof` | as-of − 最后任务时间 | `MAX(created_at) WHERE < :asof` | `spider_tasks` | 从未有任务：新客，排除出流失人群 | ✅ |
| S5 | `active_members_30d_before_asof` | `COUNT DISTINCT created_by` | 任务窗 | `spider_tasks.created_by` | 调度触发归「系统」 | ✅ |

**排除**

| 候选 | 原因 |
|---|---|
| `tenants.status` | 标签泄漏；且不代表不能登录 |
| `tenants.expires_at` | 合约问题；与巡检定义 y |
| `users.updated_at` / `is_active` | 当前状态 |
| 报表 `last_active_at` | 即 MAX(created_at)，与 S4 重复；窗口是「现在」 |
| 登录次数 | **预测时拿不到**（无表） |

### 8.3 中转站（渠道×批次，as-of = 批次开始前）

| # | 特征名 | 计算逻辑 | as-of 口径 | 来源 | 缺失含义 | 预测时可获取 |
|---|---|---|---|---|---|---|
| R1 | `identity_other_family` | 身份回答是否提他族 | 当次探针输入文本 | 探针 **raw**（今只存 scores） | 无 identity 题 | ⚠️ raw 未落库 |
| R2 | `verbatim_repeat_flag` | 知识截止题复问逐字相同 | 当次 | 同上 | 无复测 | ⚠️ |
| R3 | `ref_sim_vs_family_baseline` | 与**同家族历史参考**的相似，不是全局 0.15 | 仅用 as-of 前批次 | `channel_probe_results` | 无参考=不判罚 | ⚠️ 阈值现写死 |
| R4 | `disable_count_14d_before_asof` | 调度器 disabled 次数 | `channel_events.created_at < :asof` | 事件表 | 0=未超限过 | ✅ 但**不要用来预测本次是否禁用** |

**排除：** 当次 `verdict` / `scores`；当次 `usage` 与 disabled 事件；`NOW()` 延迟。

### 8.4 资产 / 源（资产级，as-of = 评审或 sync 时刻）

| # | 特征名 | 计算逻辑 | as-of 口径 | 来源 | 缺失含义 | 预测时可获取 |
|---|---|---|---|---|---|---|
| P1 | `parse_error_rate_source_30d` | 该源 jobs 失败比 | `skill_jobs.started_at < :asof` | 设计中 `source_id` | 源未落地 | ❌ |
| P2 | `hash_change_count_90d` | as-of 前 hash 变更次数 | 需 hash 历史 | 今只有当前 `content_hash` | 无历史 | ❌ |
| P3 | `human_score_at_asof` | 人工分 | `reviewed_at < :asof` | `skills.score` | 未评=缺失，**禁止用 AI 分填** | ✅ 但不得用来预测 listing/首页 |
| P4 | `mcp_declared_at_asof` | manifest 是否声明 MCP | 同步当时 manifest | 插件细节 | 无 MCP≠不健康 | ⚠️ 当前行 |

**排除：** `listing_state` / `listed_at`；`ai_suggested_score` 预测 `score`（可校准，不可部署）；公开曝光 / 安装数；`file_path` 绝对路径；SKILL.md 自述效果。

### 8.5 as-of 核对（候选集）

- [x] 上表保留项均含 `< :asof` 或「当次输入」
- [x] 无 `CURRENT_DATE` 时间差
- [x] 当前状态字段已列入排除
- [x] 群体统计要求排除自身（尚未实现，因未训练）
- [ ] T+1 延迟（LLM flush、结果回流）未与 `/backend` 对口径
- [ ] 蓝图业务日 Asia/Shanghai vs 用量 `datetime.utcnow()` 未对齐——**阻塞项，交给数仓 / analyst**

统计变换：无训练，无全量 fit。保持这条红线。

---

## 9. 建模前必须存在的清单（缺一则停）

SKILL.md 输入契约 + 本仓库核实。全部满足之前 **拒绝训练**。

| # | 必须有 | 谁给 | 今日 |
|---|---|---|---|
| M1 | 量化动作：预测出来谁做什么、每天处理上限 K | `/pm` | 四柱均未定义；spec 把离线模型放到下一轮 |
| M2 | 独立金标（不是现有启发式输出） | `/pm` 定义 + `/dba` 落表 + 抽检产能 | `quality_score` / `verdict` / `status=expired` / `tier` 都不是 |
| M3 | 事件事实：登录成功、配额超限、探针 raw、hash 历史 | `/dba` + FR-15 | 规划中，未建 |
| M4 | ODS 镜像 + 状态日快照（租户/资产/渠道） | warehouse | 无 |
| M5 | `dwd_`/`dws_` 与 `metrics.yaml`（特征口径对齐业务口径） | warehouse + analyst | 仅有 metrics-blueprint |
| M6 | 时间切分协议 + 只读账号（禁止 OLTP `fit`） | warehouse + dba | 无 |
| M7 | 主指标 = Precision@K / lift，不用准确率 | `/pm` 给 K | 无 K |
| M8 | 规则基线已修明显缺陷并留下数字 | `/backend` 修公式；`/qa` 锁回归 | 分母/死配置/content JSON/代理阈 均未修；质量管道 0 测试 |
| M9 | 样本量：租户级 N 要撑得起 K；渠道/资产要实体不跨集 | `/sre` 给数量级 | 未知（ops：0 工单、无 UV） |
| M10 | 离线在线同一套特征代码或一致性脚本 | `/qa` | 无模型可测；口径分裂已存在（§5.6） |

**M8 未完成时不要谈 M1 之后的模型。** 规则坏了，模型会学坏规则。

---

## 10. Model Card · 预训练（四份都不训练）

> 无基线数字、无坏例 Top-10 实证、无离线在线比对脚本。这些格子填假数比留空更有害。选定方案一律是 **规则基线**。

### 10.1 采集质量 — 不训练

| 项 | 内容 |
|---|---|
| 预测目标 | 未定义（禁止用 quality_score） |
| 决策用途 | 今日仅试采 avg&lt;40 失败；产能未知 |
| 模型类型 | **不训练。** 规则：核心选择器字段全空拒收；跨任务 hash 重复降权；`content` 不要当核心维（flow 路径） |
| 基线 | 现公式 50/30/20（分母有缺陷；flow 核心维饱和） |
| 切分 | 未做 |
| 失效边界 | 市场候选 content 空；内部字段稀释；JSON 包装骗过核心维；JS 渲染延迟；非空垃圾 ≥40 |
| 天花板 | 选择器对但站点反爬变空壳——行为特征无信号 |
| 阈值 | 40 硬编码在 orchestrator——**应可配**，不该变成模型分 |

### 10.2 租户行为流失 — 不训练

| 项 | 内容 |
|---|---|
| 预测目标 | as-of 后 7–37 天无任务且无 token（草稿，未批准） |
| 决策用途 | **BLOCKED /pm** |
| 基线① | 常量：全不流失 |
| 基线② | 规则「30 天无任务」——若要做，先测 Precision@K，K=每日能触达的租户数 |
| 泄漏排查 | `status`/`expires_at` 未通过；expired 租户仍可能登录 |
| 失效边界 | 新租户 &lt;30d；合约到期；纯登录型用户在当前数据里不可见 |
| 样本量 | 租户级，预计不足以撑树模型 |

### 10.3 渠道伪装 — 不训练

| 项 | 内容 |
|---|---|
| 决策用途 | 今日通知；自动下线未授权（FR-61） |
| 模型类型 | 不训练；保留 10 维规则 |
| 主指标（若将来有复核队列） | Precision@K，K=每天能人工看的渠道数；**不用准确率** |
| 失效边界 | 未知家族；无参考渠；知识截止题过期；弱伪装 ref_sim≥0.15 |
| 误报成本 | 下线正品 → 网关容量跌；故今日不下线是合理产品选择 |

无监督路径（仅当有复核产能）：规则初筛 → 人工确认 → **积累金标后**再讨论有监督。金标不得等于旧 verdict。

### 10.4 资产质量 / 源质量 — 不训练

| 项 | 内容 |
|---|---|
| 决策用途 | listing 人工；第三方默认 unlisted（D7） |
| 基线 | 许可黑名单 SQL；MCP verify；hash 折叠；LLM 建议 + 人工权威 |
| 失效边界 | 无 MCP 标 degraded ≠ 设计 unknown；文案驱动的 real_world_effect；无人终评时 AI 分驱动首页 S/A |
| 阈值 | listing 不是阈值问题；首页精选也不是 LTR |

### 10.5 公共监控（将来若有任一模型才交给 /sre）

现在没有模型作业。不要为不存在的 PSI 告警。  
**规则侧**可监控（归 /sre 与 /analyst）：

- 试采因 avg&lt;40 失败的比例暴涨（公式一改就会跳）
- 探针 spoofed 率按批（暴涨=题库失效或参考渠挂了）
- 代理分全员被打到 0（探测 URL 挂了；默认 httpbin）
- LLM 评分队列积压 / 预算打满（worker 默认关）

---

## 11. 基线阶梯（只评价规则，不上④）

| 级 | 方案 | 四柱现状 |
|---|---|---|
| ① 常量 | 全判负例 / 全 original / 全 listed | 无意义；正例稀疏 |
| ② 单规则 | 空字段；30 天无任务；身份他族词；许可黑名单 | **应作为正式基线留下** |
| ③ 多规则打分 | 质量 50/30/20；探针 10 维；代理 0.6/0.4；配额三闸 | **已在生产，修缺陷优先于换模型** |
| ④ 树模型 | — | **不进入。** 无动作、无金标、无数仓、无切分；spec 下一轮 |

复杂模型必须证明超过简单基线且好得值那份特征管线。当前四柱里，**没有一柱跨过这道门。**

---

## 12. 交给下游（不是 FR，是建模阻塞与口径）

| 给谁 | 内容 |
|---|---|
| `/pm` | 四柱动作未定义；处理能力上限未知；「活跃」事件未选；spoofed 误杀成本；listing/首页不得交给模型。spec 已推迟离线模型——保持。开放问题 §14 |
| `/analyst` | 先把 metrics-blueprint 落成 `metrics.yaml`。不要用两套 SQL 定义「活跃」。质量分、技能平均分、渠道 24h 事件数禁止当北极星（蓝图已写） |
| `/data-warehouse-engineer` | ODS 镜像 + 状态日快照 + 事件事实。没有这些 miner 不能 feature-as-of。时区：蓝图上海日 vs 用量 UTC |
| `/dba` | OLTP 缺：登录事实、配额超限事件、探针 raw/题版本、套餐变更史。**不要**把模型分写进现有 `score`/`quality_score` |
| `/algo` | 技能 LLM 评分与 similar_suggest 仍归你。注意：无人终评时 AI 分已经在排首页；文案驱动 `real_world_effect`；PROMPT_VERSION 硬编码 |
| `/backend` | 阈值（40、0.15、代理 0.5 vs 0.2）应可配且 Scrapy 平铺；质量分母排除内部字段；`build_item` 的 content JSON 不要当核心维——**本诊断不实施** |
| `/qa` | 无一致性脚本可交。若修质量公式：内部字段不再进分母；`"{}"` 不算 content 有值；harvester 空 content 不误杀候选闸（候选本不消费该分）；补 QualityCheckPipeline 单测 |
| `/sre` | 无模型作业。规则侧监控见 10.5。代理探测 URL 默认 httpbin，挂了会把全池打到 0 |
| `/data-collector` | harvester 空 content 会拉低质量分；不要把该分当候选排序。flow 路径核心维被 JSON 包装骗过 |

---

## 13. 自检（SKILL.md）

| 项 | 状态 |
|---|---|
| 特征字典含 as-of | 候选表有；未落地计算 |
| 时间切分非随机 | 约定了；未执行切分（无训练） |
| 无全量统计再切分 | 遵守（未 fit） |
| 基线对比 | §11 规则阶梯；无模型数字 |
| 坏例 Top-10 | **无金标，未做。** §3.3 / §10 写了机制性失效模式 |
| 失效边界 | 各卡已写 |
| 离线在线一致性 | 未测模型；§5.6 记录了已存在的口径分裂 |
| 无动作则停 | 遵守；未训练 |

未完成不等于半成品隐瞒：训练类格子是 **N/A + 阻塞原因**，诊断类格子已交付。

---

## 14. 开放问题（阻塞建模）

| ID | 问题 | 阻塞什么 | 需要谁 |
|---|---|---|---|
| Q1 | 采集低质量之后的动作是什么？丢条目 / 重跑 / 人工抽检？每天处理上限？ | 主指标（Precision@K vs 全量阈值） | `/pm` |
| Q2 | 「租户活跃」是登录、提交任务，还是消耗 token？行为流失是否排除合约到期？ | 标签 SQL | `/pm` |
| Q3 | 高流失风险租户要做什么？谁执行？每天几户？ | 是否建流失模型（默认否） | `/pm` |
| Q4 | 渠道 spoofed 后：只通知（FR-61）、进复核，还是将来自动下线？误杀正品的成本？每天复核条数？ | 探针从启发式升级的前提 | `/pm` |
| Q5 | 资产 `score`/`tier` 是否允许影响 listing / 首页精选？D6/D7 说分列——无人终评时 AI 分已经在排首页，这是否可接受？ | 若要把曝光当学习目标，与 D7 冲突，且不可建模 | `/pm` |
| Q6 | 源质量动作：停 sync、保持 unlisted、还是只告警？ | 源质量规则阈值 | `/pm` |
| Q7 | 运营能同时维护几套租户策略？ | 分群数上限；默认规则三档 | `/pm` |
| Q8 | 是否建设登录 / 配额超限 / 探针 raw 事件表？（FR-15 已规划登录与配额，未落地） | 所有 as-of 特征 | `/dba` + `/pm` |
| Q9 | 生产租户数、渠道数、日任务量数量级？ | 能否承受除规则外的任何模型 | `/pm` / `/sre` |
| Q10 | LLM 技能分与人工分不一致时，谁赢？（代码：人工赢；无人终评时 AI 赢）校准报表要不要做？ | 归 `/analyst` 还是继续只展示 | `/pm` |
| Q11 | 试采阈值 40、探针 0.15、代理 0.5/0.2 是否升为配置并对齐 Scrapy 平铺？ | 规则产品化，仍不建模 | `/pm` → `/backend` |
| Q12 | metrics.yaml 的第一批指标谁拍板？蓝图已有 WACT | 没有指标定义，分析与特征会对不齐 | `/pm` + `/analyst` + 数仓 |
| Q13 | 到期租户是否应该被登录拒绝？现网未拒。这会改变「合约流失」标签含义 | 不能把 `status=expired` 当成「已离开」 | `/pm` + `/backend`（实现不在 miner） |

**miner 立场：** Q1–Q7 未答之前，四柱全部停在规则基线。不要在 spec 里写「本期交付流失模型 / 渠道风控模型 / 资产推荐模型」。spec v1 已经把离线模型放到下一轮——**保持。**
