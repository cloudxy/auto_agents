# 分析诊断 · 四支柱 v2 可判定性（北极星 / 漏斗 / 护栏）

> 作者：/analyst｜日期：2026-09-08｜口径来源：旧程序 `/pm` 的 `feat-four-pillars/01-define/metrics-blueprint.md` **v1.2**（analyst 复盘唯一口径）；对照 grok-files `feat-four-pillars-metrics.md` 与 `four-pillars-diagnosis-and-plan.md` §8  
> 角色边界：只诊断度量 / 埋点 / 漏斗 / 北极星 **是否可判定**。不排 FR、不设计表、不改口径、**不写 07-retro**。  
> 证据范围：INPUTS 书单 + 2026-09-08 仓库只读检索。**未直连生产主库，无样本 n。**  
> 本文件是诊断，不是现行合同。v2 蓝图由 `/pm` 另写；本稿只回答：旧口径哪些还能用、哪些与代码打架、新方案度量必须写成什么样。

---

## 1. 结论先行

**四周判定今天不可执行。** 仓库仍无 `metrics.yaml`、无产品事件 SDK、无事件表、无查询面。蓝图冻结名（`official_page_viewed` / `task_completed` / `market_subscribe_succeeded` 等）在 `*.py/ts/tsx` 里 **只有** 站内通知类型字符串 `task_completed`，不是分析事件。塑形稿 ADR-0016 / `contracts/product-events.md` / T-13·T-14 存在于已 superseded 的 `feat-four-pillars/02-shape/`，**代码零落地**。

**WACT 作为唯一北极星的产品选择仍成立**（企业完成一次能交差的采集；订阅是驱动不是 OEC）。**grok-files 度量稿不能当 v2 合同原件**：它比仓库蓝图 v1.2 少字段、少护栏、TTFV 更松。**`four-pillars-diagnosis-and-plan.md` §8 的「WAU = 成功任务 ∨ 订阅 ∨ LLM」必须否决**——那是三个核心动作，违反「禁止双北极星」。

**Hero 静态数字（`128,000+` / `12 节点` / `3.2 亿条`）禁止当 OEC、禁止当基线、禁止当四周数字。** 页面仍在渲染（`Home.tsx` `HERO_STATS`，注释写「不依赖后端」）。Dashboard 全历史成功率、单任务质量分、渠道 24h 事件数同禁。

| 项 | 内容 |
|---|---|
| **支撑什么决策** | v2 度量蓝图从哪份旧稿起步；四周钟能不能打响；哪些数字允许进 OEC |
| **决策规则（事前定义）** | ① 蓝图所需事件在运行代码零命中 → 该指标今日 **不可测**。② 验收以事件可查为准 → OLTP 弱重构 **不得**当四周数字。③ grok-files `feat-four-pillars-metrics.md` 与仓库 v1.2 冲突处，**以 v1.2 为底，禁止回退**。④ 诊断稿 §8 的三选一 WAU **不得**写入 v2 北极星。⑤ Hero / `/admin/stats` / 质量分 / 渠道 24h **不得**当 OEC。⑥ 匿名步无法拼到 `tenant_id` → F1 该步转化不可测。⑦ 护栏「相对基线 +10 个百分点」且「基线无」→ 第一轮该停线 **不可操作**。⑧ 无 n → 禁止百分比结论。⑨ Q-VOICE 未关 → 不得假设观察窗内核心动作不变。⑩ 无租户级随机分流 → 只描述变化，不断言「因为上线」 |
| 结论强度 | **描述性盘点**（无对照、无 n、无 CI） |
| 主要不确定性 | 生产租户数未知；会话时区未知；Q-VOICE 可能改核心动作 |

**一句话：** 成功定义仍是「四周能报每周 WACT」；代码仍只能报「这台机器爬虫跑得怎样」。把 grok-files 度量稿原样拷进 v2，会把已经修过的 TTFV / `login_failed` / 失败装空护栏退回去。

可行性总表（引用 v1.2 口径，不另定义）：

| 指标 | 今日代码 | 按 grok-files 度量稿验收 | 按仓库蓝图 v1.2 字段做完 |
|---|---|---|---|
| **WACT（北极星）** | 不可验收。任务表可弱重构，污染 + 时区错 + 无查询面 | **仍不可**（排除靠散文「入站爬虫」，无布尔字段） | **可计数**。内部租户靠手工名单；WACT=0 与 Worker 未启动混淆；无对照不能归因 |
| D1 注册成功数 | 弱：`tenants.created_at` + `logger.success`（无事件） | 可（有事件即可） | 可 |
| D2 168h 首次登录率 | **不可**（登录不落事实；成功页无登录钮） | 部分：grok-files 未冻 `login_failed` / 企业消歧 | 可观测。路径未修则分子可长期为 0（断链，不是「登录率低」） |
| D3 TTFV 中位数 | 弱且时区混用 | **会算错**：未要求候选排除与 `result_count>0` | 可报中位数 + 「四周仍未出数人数」。未出数不进分母 = 选择偏差，必须并列 |
| D4 周订阅租户 | **不可**（无表、无事件、无订阅动作） | Wave 1 前不可 | 可计数。F3 另要浏览/详情；安装表 ≠ 漏斗 |
| 失败率护栏 +10pp | 窗口与「近 7 日结果」不一致 | 第一轮无基线，停线不可用 | 同左；只能先记录同窗口周失败率 |
| 公开页失败装空 | **今日已违反**（见 Q19） | grok-files **没有这条护栏** | 抽检可操作；v2 **必须保留**，不可随 grok-files 删掉 |
| F1 激活漏斗 | 除注册行、任务行外全是洞 | 曝光→注册按企业仍拼不上 | 若注册事件不带同一 `anonymous_id`，步 1–3 仍只是计数不是漏斗 |
| F3 市场漏斗 | 对象不存在 | Wave 1 前不可测；步间窗未冻 | 可测与否取决于事件真落查询面；预告分母必须切 |
| A/B | 无分流面 | 发布开关 ≠ 实验 | 分流单位=企业；n 未知则 **不做 A/B** |

---

## 2. 口径

> 正式指标引用仓库蓝图 v1.2，不自行定义北极星/驱动。仓库仍无 `metrics.yaml`。下表「今日数字」只说明 Dashboard 在报什么，**不是**正式指标。

### 2.1 三份旧口径源（v2 不得混用）

| 源 | 地位 | 北极星 | 与 v2 的关系 |
|---|---|---|---|
| `.sdlc/feat-four-pillars/01-define/metrics-blueprint.md` **v1.2** | 旧程序 analyst **唯一口径**；spec §6 护栏复制件 | WACT；核心动作 = `completed ∧ result_count>0 ∧ is_marketplace_candidate=false` | **起步底稿**。字段、TTFV、F1 末步、六条护栏、拒绝原因六档，禁止回退 |
| grok-files `feat-four-pillars-metrics.md` | 与 v1.2 同日、**更早**的副本 | WACT；排除写成散文「市场入站 + 明显由平台入站爬虫产生」 | **对照用，不当合同。** 缺布尔字段、缺 `login_failed` GWT、缺失败装空护栏、TTFV 不过滤候选 |
| grok-files `four-pillars-diagnosis-and-plan.md` §8 | 旧 pm 已声明 **非证据链** | 「WAU」= 7 日内成功任务 **或** 订阅 **或** LLM 成功 | **禁止写入 v2。** 三核动作 = 三个北极星 |

grok-files 度量稿相对 v1.2 的具体回退（新蓝图若「结合 grok-files」必须显式拒绝这些回退）：

| 项 | grok-files 度量稿 | 仓库 v1.2 |
|---|---|---|
| WACT 排除 | 散文 + spider/source 标记 | 布尔 `is_marketplace_candidate` + `spider` + `source` |
| TTFV / F1 末步 | 首次 `task_completed`（未要求条数>0、未排除候选） | 首次 `is_marketplace_candidate=false` 且 `result_count>0` |
| `login_failed` | 成功带 `tenant_id`；失败原因分类较粗 | GWT-15.4：凭证/过期/锁定、能消歧才带企业、不含密码 |
| 订阅拒绝原因 | `coming_soon` / `unlisted` / `license` / `auth` | 另加 `host_incompat` / `readonly` |
| 护栏 | 5 条 | 6 条（多「公开页失败装空」） |
| 出站钥匙混拉 | 跨租户可见未写 GWT-08.4 | 护栏含出站钥匙混拉两家企业行 |

### 2.2 蓝图正式指标（四周判定只许用这些；v2 若改必须走变更，不得 silently 换 OEC）

| 指标 | 分子 / 分母 | 去重 | **时间归属** | 计算窗口 | 来源 |
|---|---|---|---|---|---|
| WACT | 上海自然周内 ≥1 次核心动作的企业数（计数，无分母） | 企业 | **事件发生时间** | 上海周一 00:00–周日 24:00 | `task_completed`（FR-15）；任务表仅核对 |
| 核心动作（默认） | `task_completed` 且 `result_count>0`；排除 `is_marketplace_candidate=true` | 企业 | 同上 | 同上 | v1.2 §2；Q-VOICE 若改市场优先则改「订阅成功」，**禁止双北极星** |
| D1 注册成功数 | `tenant_signup_succeeded` 次数 | 按次，不去重邮箱 | 事件时间 | 上海自然周 | FR-15 |
| D2 168h 首次登录率 | 该周注册企业中，注册时刻起 168h 内有 `login_succeeded` 的企业 / 该周注册企业 | 企业 | 注册时刻起滚动 168h | 每企一条观察窗 | 两事件且登录必须能关联企业 |
| D3 TTFV | 已发生首次合格 `task_completed` 的企业：该次 − 注册成功，**中位数** | 企业 | 事件时间 | 四周窗内完成首次出数者；未出数 **不进中位数**，另报人数 | FR-15 |
| D4 周订阅成功租户 | ≥1 次 `market_subscribe_succeeded` 的企业 | 企业 | 事件时间 | 上海自然周 | FR-30 |
| 跨租户可见事故 | 复现确认的跨企读（含出站钥匙混拉） | — | 事故发生 | 持续 | 审计 + 手工；红线 **0** |
| 公开泄漏未上架/黑名单/未放行许可 | 抽检出的公开资产 | — | 抽检日 | 持续 | 对账 + FR-18；红线 **0** |
| 同窗口任务失败率 | 失败 /（完成+失败）；排除候选；窗口与「近 7 日结果」相同 | 任务 | 业务终态时间 | 与结果卡同一窗 | 任务状态；红线 = 相对基线 **+10 个百分点** |
| 非超管改渠道/平台 LLM 成功 | 成功写次数 | — | 审计时间 | 持续 | 审计；红线 **0** |
| 配额拒绝不可理解 | 用户文案含 `QUOTA_EXCEEDED` 或仅错误码 | 次 | 展示时 | 抽检 | FR-12；抽检 **0** |
| 公开页失败装空 | 首页精选或市场列表把加载失败渲染成「暂无/还没有」 | 次 | 展示时 | 抽检 | FR-01.4、FR-28；抽检 **0** |

**禁止当 OEC：** Hero 静态数字、全历史成功率、单任务质量分、扫描成功次数、技能平均分、渠道 24h 事件数、LLM 调用成功次数、listed 资产数、公开 API 5xx（后两项是诊断稿 §8 护栏/驱动，不是北极星）。

### 2.3 今日已有数字（非正式，防误用）

| 已有数字 | 分子 / 分母（代码事实） | 时间归属 | 窗口 | 出处 |
|---|---|---|---|---|
| 任务成功率 | `completed / (completed+failed)`，不含 pending/running | 无窗口 | **全历史** | `spider_query_service.stats` → `GET /admin/stats` |
| 「近 7 日采集结果」 | `SUM(daily_result_counts)`，`created_at >= now()-6d 00:00` | **记录时间** `spider_results.created_at` | 近 7 个本地自然日（`datetime.now()`） | 同上 |
| LLM token 月用量 | `SUM(total_tokens)` where `stat_date` LIKE `{YYYY-MM}-%` | `stat_date` | 日历月；**`datetime.utcnow()` 取月** | `tenant_usage.py:26` |
| 渠道 24h 事件 | `COUNT(channel_events)` since now-24h | `created_at` | 滚动 24h | `GET /newapi/overview` |
| 质量分布 | 单任务 `quality_score` 四档 | 该任务 | **只取最近 1 个已完成任务** | `Dashboard.tsx` `recentTaskIds[0]` |
| Hero「128,000+ / 12 节点 / 3.2 亿」 | 静态文案 | 无 | 无 | `Home.tsx` `HERO_STATS` |

**时间归属冲突：** 蓝图冻结 **Asia/Shanghai 业务日 + 事件发生时间**。代码里用量月用 UTC，采集趋势用本地 `datetime.now()`，全仓库 `CONVERT_TZ` / `Asia/Shanghai` **零命中**（2026-09-08 复跑）。今日任何「按日/按周」数字都 **不能**当成蓝图周。

---

## 3. 数据范围与质量

| 项 | 内容 |
|---|---|
| 数据源 | 代码与模型只读。无只读副本、无数仓、无产品事件表。下列 SQL 只用于「若打开只读副本，运营计数能否与代码一致」，**不是**蓝图指标 |
| 时间范围 | 诊断日 2026-09-08；生产窗未知 |
| 样本量 | **n 不可得**。全文无「转化率 x% / 提升 y%」 |
| 排除项 | 无内部账号过滤器。种子租户 `slug='platform'`（迁移 024；`User` 文档：平台超管挂此租户）。蓝图要求四周复盘用 **手工名单**，不得假装已有过滤器 |
| **数据质量问题** | 见下表。未修时对应数字不得进决策 |

| ID | 问题 | 证据（2026-09-08） | 对判定的影响 |
|---|---|---|---|
| Q1 | 成功率全历史 vs 结果近 7 日并排 | `stats()`：`success_rate` 无 `since`；`total_results` 是 7 日之和 | 失败率护栏要求与结果卡 **同一窗口**；今日护栏算不出 |
| Q2 | 质量概览 n=1 任务 | `Dashboard.tsx` 只查 `recentTaskIds[0]` | 不能代表租户/平台质量；禁止当 OEC |
| Q3 | `/admin/stats` 随 JWT 变总体 | 超管全库、租户本企；API 无口径字段 | 纵向对比危险；不是 WACT |
| Q4 | 平台入站与租户采集同表 | `skill_harvester` → `spider_results.source=marketplace`；`top_spiders_by_results` 不过滤 spider/source | 不排除则 WACT / 失败率被候选污染 |
| Q5 | Hero 规模静态 | `HERO_STATS` 写死；`Home.tsx` 注释「纯静态展示，不依赖后端接口」 | **不得当基线 / 不得当 OEC** |
| Q6 | 公开技能列表先分页再滤发布态 | `public_list_skills`：`status=None` 后再滤，`total=len(published)` | 不能用 total 当目录规模 |
| Q7 | 公开能力广场只传 `status=stable` | `public_list_capabilities` | 与 `PUBLISHED_STATUSES`、设计 D6/D17 不一致；也不是市场漏斗入口 |
| Q8 | 审计无 `tenant_id`、无匿名访客 | `operation_logs`：actor + action + target | **不得**当漏斗分母 |
| Q9 | 登录成功/失败不落事实 | `auth.py` 失败只走 Redis 15 分钟窗口；`users` 无 `last_login` | D2 今日不可测；失败原因不可分 |
| Q10 | 导出无审计、无事件 | `GET /results/{task_id}/export` 无 `record_audit` | `results_exported` 零 |
| Q11 | 配额拒绝只抛 429 | `QuotaExceededException`，不计数 | `quota_exceeded` 零 |
| Q12 | 市场表与配置未落地 | `listing_state` / `capability_installs` / `POWER_MARKET` 全库 **0 命中** | F3 / D4 对象不存在 |
| Q13 | 定价三档 CTA 同链 `/register` | `Pricing.tsx` 免费/专业/企业 href 全是 `/register` | `cta` 分档不得合并；今日意图不可分 |
| Q14 | 产品事件名与站内通知类型撞名 | `notifications.type` 含 `task_completed` | 查错表会把收件箱当北极星 |
| Q15 | `tenants.created_at` naive vs `spider_tasks.completed_at` tz-aware | 模型列定义不同 | TTFV 弱重构跨日会偏 |
| Q16 | 无内部租户标记列 | `tenants` 无 is_internal | 四周只能手工排除；`platform` 若跑任务会进 WACT |
| Q17 | 注册成功页主按钮是「再注册一家」 | `Register.tsx` | D2 路径结构断；不是「登录率低」 |
| Q18 | 首页主 CTA 不在蓝图枚举 | 「体验 AI 采集流程」页内滚动；「进入管理后台」外链 `ADMIN_URL` | F1 禁止把直达后台算进官网分母；枚举又没有这两键 |
| Q19 | 公开页失败装空（护栏今日已红） | `Capabilities.tsx`：`.catch(() => setItems([]))` → `Empty`「暂无已发布…」；`SkillsSection.tsx`：失败 `setItems([])` 渲染空白网格，无「加载失败+重试」 | grok-files 度量稿 **没有** 这条护栏；v2 若照抄 grok-files 会把已违反的行为从护栏里抹掉 |
| Q20 | 用量页用户可见 `QUOTA_EXCEEDED` | `Usage.tsx` Alert 原文含该错误码 | 护栏「配额拒绝不可理解」抽检今日即可判红（与事件无关） |
| Q21 | 结果配额 COUNT 含 marketplace | `QuotaService.check_result_storage` 不滤 `source` | 不是 WACT，但会让「出数/配额」运营数字与核心动作不一致 |
| Q22 | 塑形事件契约未进运行时 | `02-shape/contracts/product-events.md`、ADR-0016、T-13/T-14 均为 **todo**；`GET /api/v1/admin/product-events` 代码 **0 命中** | 不得把塑形稿当成「已经能查」 |

---

## 4. 分析

### 4.0 埋点：蓝图事件 vs 仓库（复跑）

字段最低集（v1.2）：`occurred_at`、`anonymous_id` **或** 已登录的 `tenant_id`/`user_id`、`role`。  
检索（2026-09-08）：蓝图事件名在运行代码中 **仅** `platform_core/models/notification.py` 的通知类型；前端无 posthog / mixpanel / amplitude / gtag 产品 SDK（`workbox-google-analytics` 是 PWA 依赖，不是漏斗）。`track_event` / `product_event` / `metrics.yaml` / `is_marketplace_candidate` / `POWER_MARKET` **0 命中**。

| 事件（v1.2 冻结名） | 何时 | 今日落点 | 判定 |
|---|---|---|---|
| `official_page_viewed` | 首页/定价/市场/注册 | 无 | 洞 |
| `official_cta_clicked` | 主按钮，`cta` 五档不得合并 | 无；定价三档同 `/register`；首页主按钮不在五档内 | 洞 |
| `tenant_signup_succeeded` | 企业开通 | `tenants` 行 + `logger.success`；无审计、无事件 | 行可数，事件不可查 |
| `login_succeeded` / `login_failed` | 登录结果；成功须带 `tenant_id` | JWT 响应有 `tenant_id`；失败 Redis 计数易失 | 洞 |
| `task_run_submitted` | 提交采集 | 审计 `task.run` / `task.run_from_template`（写操作，无读分母） | 审计 ≠ 事件 |
| `task_completed` | 完成；`result_count`；候选布尔；spider/source | 任务行 `status/result_count/spider_name`；结果行 `source`；**无事件** | 弱重构有，验收无 |
| `results_exported` | 导出成功 | 流式下载，无审计 | 洞 |
| `quota_exceeded` | 配额拒绝，维度三选一 | 只抛 429 | 洞 |
| `market_*`（FR-30 八个） | 浏览/搜/详情/订/拒/卸/上架/同步 | 官网 `Capabilities.tsx` 四 Tab 网格，无搜索、无详情、无订阅；卡片 `hoverable` 不可点穿 | 洞 |

失败上报不得挡主路径——今日无上报，这条尚未被违反，也尚未被满足。

塑形契约（**非运行态**）：`product-events.md` 已写 `occurred_at` UTC + 报表日上海、超管查询 API、`is_marketplace_candidate`。**仍未**要求 `tenant_signup_succeeded` 带注册前 `anonymous_id`；CTA 五档仍盖不住首页两键。v2 若「结合旧方案」，应把「查询面独立、不混审计」收下，把「signup 不带 anonymous_id」标成 **未关缺口**，不要当成已解决。

### 4.1 北极星：哪些仍成立

| 主张 | 判定 | 理由 |
|---|---|---|
| 唯一北极星 = WACT（周活跃完成租户数） | **仍成立** | 离「企业交差」最近；订阅当北极星会把「订了从未出数」算成成功 |
| 核心动作默认 = 采集 completed 且条数>0 | **仍成立** | 今日唯一可能走完的用户价值；市场对象不存在 |
| 排除市场入站候选 | **仍成立** | `skill_harvester` 与租户采集同表；不排除则平台入站会冒充租户出数 |
| 排除必须是事件上的布尔，不得靠事后猜 spider 名 | **仍成立，且 grok-files 不够** | 散文「明显由平台入站爬虫」不可复现；两人会写出不同 SQL |
| 禁止同时两个北极星；改核心动作走变更 | **仍成立** | Q-VOICE 未关；观察钟在叙事未冻时启动则四周不可比 |
| 目标 = 建基线，不设提升百分比 | **仍成立** | ops 0 工单、0 生产 n |
| 判定周期 = 相关波次对用户可用后 4 个上海自然周 | **仍成立** | 中途不下成败；无对照只描述变化 |
| 验收以事件可查为准，任务表仅核对 | **仍成立** | 否则 Wave 0「埋点 FR 变绿」≠「能报 WACT」 |
| 分流单位若将来做实验 = 企业 | **仍成立** | 市场/SaaS 有交互效应；按用户会让同企看见不同目录 |
| 付费不进 OEC | **仍成立** | Q-BILL 未关；定价三档今天仍进 `/register` |
| 留存本轮不靠登录 D7 | **仍成立** | 登录事实都不存在 |
| 渠道探针伪装次数不进 OEC | **仍成立** | 值班观察项，无误杀金标（algo） |
| 数仓分层本轮不建 | **仍成立** | warehouse 三块未就绪；禁止第二套口径 |
| 诊断稿 WAU = 任务∨订阅∨LLM | **不成立，禁止回流** | 三个核动作；LLM 成功是基础设施不是用户交差 |
| Hero / 全历史成功率 / 质量分当增长 | **不成立** | 蓝图 §1 已禁；代码仍在展示，分析时必须当噪声 |

### 4.2 北极星：与代码的冲突

蓝图：一周内至少一次「采集完成且条数>0」的企业去重；排除市场入站；目标 = 四周结束能报出每周 WACT=？；报不出 = 埋点 FR 失败。

**冲突 1 — 验收对象不存在。** 没有事件、没有按 `event_name + occurred_at` 的查询面。用 `spider_tasks` 重构违反「验收以事件可查为准」。

**冲突 2 — 排除规则未接线。** 代码无 `is_marketplace_candidate`。候选在结果行 `source=marketplace`、任务行常见 `spider_name=skill_harvester`。`top_spiders` 与 `stats()` 不过滤。超管看全库时入站任务会进「完成」。

**冲突 3 — 时区。** 完成时刻在 `completed_at`（tz-aware）；stats 切日用 `datetime.now()`；用量用 `utcnow()`。没有 Shanghai 转换。周界会错。

**冲突 4 — 通知表撞名。** `notifications.type='task_completed'` 是收件箱，不是北极星。

**冲突 5 — 混淆。** Worker 未启动则任务一直 pending。WACT=0 可能是没人来 / 来了没登录 / 登录了跑不起来。驱动指标能拆，但今日后两件是洞。`slug='platform'` 若被拿来试跑，会污染企业去重。

**冲突 6 — grok-files 字段不够判。** 即便将来按 grok-files GWT（无布尔候选字段、无 `login_failed`）把事件落库，WACT 仍要靠 spider 名猜测。仓库 spec v1.4 的 GWT-15.1 **已经**写上布尔字段（QA-02 在旧 `state.yaml` 标 fixed）——那是规格文字，**不是**代码。v2 不得把 grok-files spec 的旧 GWT-15.1 当成「更简洁的验收」。

任务表核对（**非正式**，禁止复制进口径）：

```sql
-- 核对用：上海周 × 企业去重的「完成且有条数」任务。
-- 不是 WACT。缺事件、缺候选标记、会话时区未知。
-- 假设 completed_at 存 UTC；若实际是 naive 本地，CONVERT_TZ 会错。
SELECT
  YEARWEEK(CONVERT_TZ(completed_at, '+00:00', '+08:00'), 1) AS iso_week_mon,
  COUNT(DISTINCT tenant_id) AS oltp_proxy_not_wact
FROM spider_tasks
WHERE deleted_at IS NULL
  AND status = 'completed'
  AND COALESCE(result_count, 0) > 0
  AND spider_name <> 'skill_harvester'
GROUP BY 1
ORDER BY 1;
```

候选污染检查：

```sql
SELECT COALESCE(source, '(null)') AS source, COUNT(*) AS n
FROM spider_results
WHERE deleted_at IS NULL
GROUP BY COALESCE(source, '(null)');
```

### 4.3 漏斗 F1 · 官网 → 第一次出数

#### 步骤定义（v1.2 §7，本角色不改）

| 项 | 规则 |
|---|---|
| 允许跳步 | 否。直接打开后台登录 **不算** 官网漏斗分母（分开报） |
| 回退 | 按企业取 **首次** 到达该步的时间 |
| 多次尝试 | 企业去重，首次 |
| 时间窗 | 步间 168h（与 D2 一致） |

步骤：曝光 → CTA → 注册成功 → 首次登录 → 首次提交任务 → 首次合格 `task_completed`。

| 步骤 | 今日观测 |
|---|---|
| `official_page_viewed` | 无事件 |
| `official_cta_clicked` | 无事件；首页主按钮不在枚举；定价三档合并 |
| 注册成功 | 可数行、不可数曝光分母 |
| 首次登录 | 无登录事实；成功页无「去登录」 |
| 首次 `task_run_submitted` | 审计 `task.run`，无打开任务页分母 |
| 首次合格 `task_completed` | 任务表弱重构 |

无 n，不按转化率排序。语言上：**最大不可观测段仍是曝光→注册、注册→登录**。没有分母就没有绝对流失，优先级公式用不了。

**身份拼接。** 蓝图字段是 `anonymous_id` **或** `tenant_id`。F1 按企业去重。曝光发生在注册前。`tenant_signup_succeeded` 若不准入同一 `anonymous_id`，步 1–3 无法按企业连成漏斗。计数 ≠ 漏斗。塑形 `product-events.md` 仍只要求 signup 带 `tenant_id`。

**双入口。** Hero「进入管理后台」正是要从 F1 拿掉的那条路。必须另报「后台直达」序列，否则修好注册页之后，登录成功会看起来像从官网漏斗来的。

**CTA 枚举盖不住 UI。** 五档没有 `enter_admin` / 页内锚点。不补枚举又不分报，四周 CTA 表是空的。

**grok-files 的 F1 末步更松**（任意 `task_completed`）。v2 末步必须与 WACT 核心动作同一过滤，否则漏斗终点会比北极星宽。

### 4.4 漏斗 F3 · 市场浏览 → 订阅

设计：公开列表（listed ∪ coming_soon）→ 搜索 → 详情 → 登录 → `POST /tenants/me/installs`（仅 listed）。安装表是 **存量状态**，不是浏览事件。

v1.2 F3：`list_viewed` → search（可选）→ `detail_viewed` → `subscribe_succeeded`。预告拒绝进 `rejected`。Wave 1 前全部不可测。今日：无表、无 API、无前端动作、无事件。

把今日广场请求当市场入口会高估「市场」——那是目录陈列。`coming_soon` 可见不可订（D17）：列表 UV 含预告，订阅分母若用 `list_viewed` 会系统性偏低，**必须**按详情上架态切片。

**未冻（v2 蓝图必须补，本角色不代选小时数）：** F3 步间时间窗；search 可选时 list→detail 是否允许跳过 search；预告浏览是否计入订阅分母。

### 4.5 驱动指标

| 指标 | 与代码 | 仍成立的诊断用途 | v2 写法约束 |
|---|---|---|---|
| D1 | 能数行、不能验收 | WACT=0 时：注册也是 0 → 获客句失败；注册>0 → 断在登录或出数 | 按次计，不去重邮箱 |
| D2 | 结构零风险 | 分母有、分子无 = 仍停在注册成功页 | 分子≈0 在 FR-04 落地前解释为路径断裂，**禁止**写成「登录率低」 |
| D3 | 中位数会看起来「很快」 | 登录率高但 TTFV 无穷 = Worker/配额/LLM | 必须两列：中位数 + 四周仍未出数人数。过滤条件与 WACT 相同 |
| D4 | 对象不存在 | 列表高、订阅 0 = 预告/许可/回跳 | 用 `rejected` 原因切片；安装行只做存量核对 |

付费意向今天会污染 D1（三档 CTA 同注册）。定价专业/企业档在 Q-PRICE 关闭前不得被解释成「付费转化」。

### 4.6 护栏

| 护栏 | 今日 | 第一轮四周 | v2 必须 |
|---|---|---|---|
| 跨租户可见 = 0 | 审计 + 手工复现 | **可操作** | 保留；含出站钥匙混拉 |
| 公开泄漏 = 0 | 无上架字段 | Wave 1 闸门落地后可抽检 | 保留 |
| 失败率相对基线 +10pp | 窗口错、含候选、总体混 | 蓝图「基线无」与本条 **互相否定** | 第一轮只 **记录** 同窗口周值，**不能**用 +10pp 停推 |
| 非超管改渠道/LLM = 0 | 审计有写；权限是否收口是产品问题 | 有审计即可计数 | 保留 |
| 配额文案抽检 = 0 | `Usage.tsx` 已展示 `QUOTA_EXCEEDED`；429 消息本身不含该码 | **今日可抽检、可判红** | 保留；与 `quota_exceeded` 事件分开（事件是增长诊断） |
| 公开页失败装空 = 0 | `Capabilities.tsx` / `SkillsSection.tsx` 已装空或装白 | **今日可抽检、可判红** | **必须保留**。grok-files 度量稿没有它，照抄即漏判 |
| 诊断稿：公开 API 5xx / src_sync 失败 / 架构检查 | SRE/CI 观察 | 不是产品 OEC | 可留值班，不进北极星、不进失败率护栏替代 |

渠道探针「伪装」次数：不进 OEC、无红线。继续留在值班观察。

### 4.7 分维度：切不出产品切片

| 维度 | 是否存在 | 蓝图四周是否需要 |
|---|---|---|
| 设备 / UA / 官网会话 | 无 | F1 匿名步需要会话级 `anonymous_id`，不是 UA |
| 获客渠道 / UTM | 无 | 本轮建基线可不切渠道；没有也不挡 WACT |
| 新老 | 无首次核心动作事件 | WACT 本身是周活跃；新老要用注册队列 |
| 租户规模 / 套餐 | `quota` JSON 是手改运营值，不是付费档 | 不要当实验分层 |
| 宿主 grok/zcode/kimi/claude | 设计在 `installs.host`；未建表 | D4 / F3 切片 Wave 1 才有对象 |
| 上架态 listed vs coming_soon | 列不存在 | F3 分母必须切，否则预告稀释订阅率 |

### 4.8 无 A/B 面

实验六项：无预注册假设、无 assignment、无 MDE、无停止规则、无实验平台。`POWER_MARKET.ENABLED`（设计，代码未落地）是总开关，不是 50/50。

n 未知。技能要求算不清样本量就放弃实验。**本轮四周判定本来就不是实验。** 不做 `experiment-design.md`、不写 07-retro。

### 4.9 审计 ≠ 产品事件

`record_audit` 覆盖任务/定义/调度/模板/告警、AI 计划、LLM、成员、RBAC、租户 CRUD、技能扫描/候选/评分、插件 verify、渠道、通知、死信。

它不是分析事件流：只写高危写，不写读；不写登录、导出、配额拒绝、公开页浏览；无 `anonymous_id`；`operation_logs` 按 actor 不按 tenant；`record_audit_standalone` 失败吞掉。

**决策规则：** `COUNT(operation_logs WHERE action='task.run')` 不得当采集使用率。

### 4.10 全新方案度量必须怎么写

交给 `/pm` 写 v2 `metrics-blueprint.md` 的硬约束（analyst 不代写蓝图、不排 FR）：

1. **只许一个北极星，名字继续叫 WACT。** 核心动作默认 = 采集 `completed ∧ result_count>0 ∧ is_marketplace_candidate=false`。订阅、LLM 成功、listed 资产数、安装行数 **只能当驱动或核对，不能 OR 进北极星**。禁止把诊断稿 §8 WAU 写回来。
2. **成功 = 能判定，不是提升 x%。** 四周结束必须能报「每周 WACT=？」；报不出 = 埋点失败。禁止写转化率目标百分比。
3. **口径底稿 = 仓库 v1.2，不是 grok-files 度量稿。** 结合 grok-files 时只吸收「无 n / 禁止 Hero OEC / 上海周 / 事件发生时间」这些已对齐句；拒绝 TTFV 回退、拒绝删失败装空、拒绝散文排除、拒绝砍掉 `login_failed` 与六档拒绝原因。
4. **事件名冻结。** 沿用 v1.2 §5 名称。architect 不改名。查询面必须是独立事件流（ADR-0016 决策可吸收），禁止 `operation_logs` / `notifications` / `/admin/stats` 顶替。
5. **WACT 可计算字段写进同一条 GWT。** `task_completed`：`tenant_id`、`result_count`、`spider`、`source`、布尔 `is_marketplace_candidate`。不得写成「FR-15 已含」却让 GWT 缺字段（grok-files spec 的旧 GWT-15.1 就是这个坑）。
6. **F1 要漏斗不要计数。** `tenant_signup_succeeded` 必须带注册前 `anonymous_id`（cookie 贯穿）。官网漏斗与「后台直达」**两张表**。CTA 枚举要么扩到真实主按钮（体验 AI 流程 / 进入管理后台），要么改 UI 去就现有五档——产品二选一，蓝图必须覆盖现状，禁止四周 CTA=0。
7. **F1 末步 = WACT 核心动作。** 禁止 grok-files 那种「任意 task_completed」。
8. **D2 / D3 的解读规则写进蓝图，不只写公式。** D2 分子在注册成功页无登录出口时解释为断链。D3 强制两列（中位数 + 仍未出数人数）。未出数不进中位数分母这条保留，但必须并列，防止选择偏差装成「TTFV 很快」。
9. **F3 补三句步骤规则。** 步间时间窗；search 可选是否允许跳过；预告是否进订阅分母。安装表 / `capability_installs` 不得当 F3 完成。
10. **护栏六条全留。** 失败装空、配额文案、跨租户 0、泄漏 0、非超管写 0 是抽检/事故，第一轮就可操作。失败率 +10pp **降级为记录项**，直到四周基线存在。不要用公开 5xx 或 CI 违规数替换产品护栏。
11. **禁止当 OEC 清单写死，含 Hero。** 即便 FR-02 删掉页面，历史截图里的 12.8 万也不得回填基线。
12. **时间。** `occurred_at` = 事件发生时间（瞬时，建议 UTC）；报表日 = 上海日历。禁止把 `datetime.now()` / `utcnow()` 的 Dashboard 公式复制进蓝图 SQL。
13. **排除。** 内部测试企业第一轮手工名单 + 备忘；不得假装有 `is_internal`。`slug='platform'` 默认进排除候选名单，由操作者确认。
14. **不做 A/B。** 若将来做，分流单位=企业。n 与 MDE 未知时 5 个租户走完「注册→第一次合格 completed」只解释机制，不估计规模。
15. **Q-VOICE 关闭前不打观察钟。** 核心动作中途切换会使 WACT 序列断裂。
16. **`metrics.yaml` / ODS 不本波。** 本轮 OLTP 事件查询面必须够四周手查；禁止分析打生产主库重查询。下一轮 yaml 从蓝图 **复制 id**，禁止仓侧发明平行指标。
17. **WACT=0 的诊断顺序写进蓝图（不是因果）：** D1 → D2 → 节点是否在线 → 再谈产品激活失败。基础设施离线不得写成漏斗结论，除非事前约定。

---

## 5. 反驳自检（≥2，必做）

### 替代解释 1：「塑形已经有 ADR-0016 和 product-events.md，可判定性已解决」

| 项 | 内容 |
|---|---|
| 检验 | 检索运行代码中的查询 API、模型、事件名；对照 T-13/T-14 状态 |
| 结果 | 契约与票都在 `.sdlc/feat-four-pillars/02-shape/`，状态 **todo**；运行时代码 0 命中。旧 feature 已 `superseded` |
| 判定 | **可排除「塑形稿 = 能判定」**。v2 可以吸收决策（独立事件表、不混审计），不能吸收「已经落地」 |

### 替代解释 2：「内部其实有埋点，只是不叫 analytics」

| 项 | 内容 |
|---|---|
| 检验 | 检索 audit / logger / Redis 限流 / skill_jobs / channel_events / llm_token_usage / admin stats / notifications / 前端 SDK |
| 结果 | 有运营与合规痕迹；通知类型碰巧叫 `task_completed`；**无读路径、无官网、无 assignment、无事件查询面** |
| 判定 | **不能排除「运营可观测」**；**可排除「产品漏斗可测」** |

### 替代解释 3：「租户量太小，看表就够」

| 项 | 内容 |
|---|---|
| 检验 | 本诊断无生产 n；蓝图验收以事件可查为准 |
| 结果 | n 小应放弃 A/B，**仍要**注册/登录/首次成功的行级时间。看表填不上官网分母，也过不了「事件可查」 |
| 判定 | **无法排除「现在 n 很小」**；可排除「看表 = 能判定 WACT」 |

### 替代解释 4：「grok-files 度量稿与仓库蓝图差不多，v2 拷 grok-files 更快」

| 项 | 内容 |
|---|---|
| 检验 | 逐项对照 §2.1：TTFV 过滤、候选布尔、login_failed、失败装空、拒绝原因 |
| 结果 | grok-files 更早、更松。失败装空是 **今日代码已违反** 的护栏，grok-files 没有它 |
| 判定 | **可排除「两份度量稿可互换」**。拷 grok-files = 规格回退 |

### 替代解释 5：「Dashboard 已有成功率/质量，北极星已在」

| 项 | 内容 |
|---|---|
| 检验 | Q1–Q5：窗口不一致、n=1 质量、source 污染、Hero 静态、总体混用 |
| 结果 | 运维健康，离「企业完成一次能交差的采集」远 |
| 判定 | **可排除「现有 Dashboard = WACT」**。Hero 尤其不得当 OEC |

### 替代解释 6：「Power Market 设计已含安装访问模式，市场漏斗可等表」

| 项 | 内容 |
|---|---|
| 检验 | 设计 D10 / Q10 vs 蓝图 F3 事件 |
| 结果 | 安装表是状态；F3 要浏览/搜索/详情。等表不会自动出现转化 |
| 判定 | **可排除「有 installs 就能做 F3」** |

### 修正后的结论

v2 不是从零发明北极星：WACT / D1–D4 / 上海周 / 禁止 Hero OEC **继续成立**。可测性相对 2026-09-07 **没有变好**——代码仍无产品事件。把 grok-files 度量稿或诊断稿 §8 当新合同，会分别造成「字段不够判」和「三个北极星」。四周「能判定」仍被三道闸卡住：① 事件真的进查询面；② GWT 字段覆盖 WACT 排除与登录-企业（以仓库 spec v1.4 为准，不以 grok-files spec 为准）；③ 匿名 ID 贯穿到注册，且官网/后台入口分报。第一轮失败率 +10pp 停线、Q-VOICE 未关就启动观察钟，都会让「判定」名不副实。无对照，任何上线前后差异只许说「变化」。

---

## 6. 因果性声明

| 项 | 内容 |
|---|---|
| 有对照组吗 | 无 |
| **能得出什么结论** | 只能说「观测面缺口存在（代码证据）」；**不能说「因为缺埋点所以增长差」**——增长未知 |
| 同期其它变更 | v2 定义帽复审，无上线窗 |
| 季节性 | 不适用 |
| 选择偏差 | ① 用「有 completed 任务的租户」当活跃，会把 Worker 未启动当成产品失败。② TTFV 中位数丢掉未出数企业，会偏快。③ 能跑通采集的人本来就不是全体注册企业。④ 从后台直达进来的登录，不能算官网漏斗转化 |
| 若要确认因果 | 先有与蓝图一致的事件 + 租户级 assignment；n 与 MDE 算不清之前不要开 A/B |

**无对照组时只说「缺口/差异」，不说「因为」。**

---

## 7. 数字的完整呈现

| 结论 | 效应 | 样本量 | 置信区间/波动 |
|---|---|---|---|
| 产品事件 SDK / 事件表 / 查询面 / `metrics.yaml` | 存在性 = 0（代码检索，2026-09-08） | 检索范围 = 本仓库当前树 | 不适用（不是抽样） |
| 蓝图事件名在运行代码中的产品落点 | 0 条（通知类型字符串除外） | 同上 | 不适用 |
| `POWER_MARKET` / `listing_state` / `capability_installs` / `is_marketplace_candidate` / `Asia/Shanghai` | 0 命中 | 同上 | 不适用 |
| 官网 Hero「128,000+ / 12 节点 / 3.2 亿条」 | 与 API 无连接；**禁止当 OEC** | n/a | 不得当基线 |
| 定价三档 CTA 目标 URL | 3/3 为 `/register` | n=3 档（页面常量，非用户样本） | 不适用 |
| 公开页失败装空 | Capabilities 失败→「暂无」；首页精选失败→空白网格 | n=2 个页面实现 | 护栏今日可抽检判红 |
| 任一转化率 / 提升 / 「登录率几乎为 0」的百分比 | **不下结论** | n 不可得 | 无 CI → 无百分比 |
| 失败率护栏「+10 个百分点」 | 第一轮不可操作 | 基线未定义 | 无 |

---

## 8. 建议与后续（交接，不排期、不排 FR 优先级）

| # | 建议 | 支撑的决策 | 需要谁 |
|---|---|---|---|
| 1 | v2 度量蓝图以仓库 v1.2 为底；grok-files 度量稿只作对照；诊断稿 §8 WAU **删除** | 新方案从哪份口径起步 | `pm` |
| 2 | 禁止清单写进 v2 第 1 节：Hero、全历史成功率、单任务质量分、扫描成功、技能平均分、渠道 24h、LLM 成功次数 | 防止 OEC 漂移 | `pm` |
| 3 | 四周判定时钟：Q-VOICE 关闭 **且** 查询面能按上海周查出带候选标记的 `task_completed` 之后再开始 | 观察钟何时打响 | `pm` / 操作者 |
| 4 | GWT 用仓库 spec v1.4 的 15.1/15.4（布尔候选、`login_failed`、企业关联），不要用 grok-files spec 的旧 GWT | FR-15 验收是否等于能报 WACT | `pm` / `qa` |
| 5 | 注册事件写入同一 `anonymous_id`；F1 与「后台直达」分报；CTA 枚举覆盖真实主按钮或改 UI | F1 步 1–3 是否可按企业转化 | `pm` |
| 6 | 第一轮护栏：跨租户 0、泄漏 0、非超管改渠道 0、配额文案抽检 0、失败装空 0 **可用**（后两条今日已可判红）。失败率只记录 | 什么时候允许「停市场大推」 | `pm` / `sre` |
| 7 | 四周报告强制两列：每周 WACT；每周「注册后仍未出数企业数」。禁止只报 TTFV 中位数 | 避免选择偏差装成激活成功 | `analyst`（届时复盘） |
| 8 | 不要用 installs / 审计 / notifications / `/admin/stats` / Hero 当漏斗或北极星 | 防止口径漂移 | 实现帽 + qa |
| 9 | 不做 A/B。分流单位若将来做 = 企业 | 证据等级 | 操作者 |
| 10 | 中转站数字留值班护栏，不进 OEC | 避免熔断次数被当成增长 | `pm` / `sre` |
| 11 | `metrics.yaml` / 数仓：下一轮。本轮 OLTP 事件查询面必须够四周手查 | 复盘能不能跑 | warehouse 下一轮；本轮 `architect` 只保证事件能查 |

**analyst 拒绝：** 实现埋点、建数仓星型、给 FR 排优先级、发明未在蓝图中的正式 SQL 指标、把 superseded `02-shape` 当已落地、写 07-retro、把 Hero 静态数字当 OEC。

---

## 9. 自检

- [x] 结论先行
- [x] 说清支撑什么决策；决策规则事前定义
- [x] 口径引用旧 `/pm` 度量蓝图 v1.2，未自行定义北极星；标出 grok-files / 诊断稿冲突
- [x] 时间归属明确
- [x] 漏斗步骤规则已引用；F3 未冻处已标
- [x] 分母缺失处标「洞」，无 n 不排序
- [x] 分维度看过
- [x] 反驳自检 ≥2（实际 6）
- [x] 无对照组未说「因为」
- [x] 无生产 n，无百分比结论
- [x] **未把 Hero 静态数字当 OEC**
- [x] **未写 07-retro**
- [x] 推测已标明
- [x] 数据质量问题已披露
- [x] 未直连生产主库
- [x] 无 PII
- [x] SQL 标明非正式 / 仅核对
- [x] 未设计数仓 schema、未给 FR 排优先级

---

## open_questions

已由旧蓝图关闭、不再问：单一北极星=WACT（默认出数）；付费不进 OEC；留存本轮不靠登录 D7；市场要匿名浏览事件（F3）；时区=上海；内部账号第一轮手工名单；中转因果不进 OEC。

仍开放（挡判定或挡解读）：

1. **操作者 / pm：** Q-VOICE 未关时，四周钟是否允许启动？核心动作中途切换会使 WACT 序列断裂。
2. **pm：** v2 蓝图是否确认以仓库 v1.2 为底、明确拒绝诊断稿 §8 WAU 与 grok-files TTFV 回退？（本诊断的决策规则假设「是」；pm 若另选必须重写本文件的「仍成立」表。）
3. **pm：** `tenant_signup_succeeded` 是否必须带注册前 `anonymous_id`？不带则 F1 曝光→注册不能按企业转化。塑形契约现在没写死。
4. **pm：** 首页「进入管理后台」「体验 AI 采集流程」记入哪一档 `cta`，或是否另报「后台直达」漏斗？
5. **pm：** F3 步间时间窗？search 可选是否允许 list→detail 跳过 search？预告浏览是否计入订阅分母？
6. **pm：** 失败率护栏第一轮是否降级为「只记录、不停推」，直到四周基线存在？
7. **实验：** 可随机的企业 n 与最小可关心的绝对提升（MDE）仍未知。算不清则维持「不做 A/B」。
8. **口径：** `DATE(created_at)` / 事件存储的时区约定（UTC 瞬时 vs 上海墙钟）。会话时区未知时，上海周 SQL 会静默错一周界。塑形写 `occurred_at` UTC + 报表上海，v2 需冻结这一句。
9. **排除表：** 除 `slug='platform'` 外，操作者四周要排除的测试企名单何时提供？
10. **解读：** WACT=0 且 D1>0 且节点离线时，是否预先约定「不算产品激活失败」？
