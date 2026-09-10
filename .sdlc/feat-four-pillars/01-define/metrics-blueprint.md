# 度量蓝图 · 四支柱程序

> 作者：/pm｜日期：2026-09-07｜对应 `spec.md` §6｜版本：v1.2  
> **本文件是 analyst 复盘的唯一口径。** spec §6 护栏表复制自第 4 节；北极星/驱动以本文第 2–3 节为准。冲突以本文为准。本文件不要求 spec 自称「逐条一致」。
> 下游：`/analyst` 复盘口径以此为准；`/qa` 验收埋点 FR；`/architect` 只负责「事件能否落查询面」，不改口径
> 约束：仓库无 `metrics.yaml`、无产品事件 SDK、ops 报告 **0 客户工单**、无生产 n。因此 **禁止** 在本文件写转化率提升百分比。本轮成功 = 能判定。

---

## 1. 判定纪律

| 项 | 规则 |
|---|---|
| 判定周期 | 相关波次对用户可用之后 **4 个上海自然周**；中途不下成败结论 |
| 基线 | 无。第一轮目标就是建立基线 |
| 时区 | **Asia/Shanghai 业务日**；指标用 **事件发生时间**，不用「报表生成时间」 |
| 分流 | 无 A/B 面。`市场总开关` 是发布控制，不是实验。若将来做实验，分流单位 = **企业**（analyst） |
| 排除 | 市场入站候选任务不得计入采集北极星。内部测试企业若尚无标记，四周复盘时用手工名单排除并写进备忘——**不得假装已有内部账号过滤器** |
| 禁止当 OEC | Hero 静态数字、全历史成功率、单任务质量分、扫描成功次数、技能平均分、渠道 24h 事件数 |

---

## 2. 北极星（唯一）

| 字段 | 内容 |
|---|---|
| 名称 | 周活跃完成租户数（WACT） |
| 口径 | 一个上海自然周内，至少发生 1 次 **核心动作** 的企业去重数 |
| 核心动作（默认） | 采集任务进入 completed **且** result_count>0。排除 `is_marketplace_candidate=true` 的事件（市场入站候选） |
| 核心动作（待 Q-VOICE） | 若对外第一句改为能力市场优先：用变更流程把核心动作改为「订阅成功」。**禁止同时存在两个北极星** |
| 来源 | 事件 `task_completed`（FR-15 GWT-15.1：`tenant_id`、`result_count`、`spider`、`source`、布尔 `is_marketplace_candidate`）。任务表可作核对，**验收以事件可查为准** |
| 时间窗 | 上海周一 00:00 至周日 24:00，按事件发生时间 |
| 目标值 | 建立基线。四周结束时必须能报出「这四周每周 WACT=？」；报不出 = 埋点 FR 失败 |

北极星选「企业完成了一次能交差的采集」，是因为这是今天唯一可能走完的用户价值。市场订阅是驱动指标，避免「订了很多能力但从来没出过数」被算成程序成功——除非操作者用 Q-VOICE 改主叙事。

---

## 3. 驱动指标（4 个）

### D1 注册成功数

| 字段 | 内容 |
|---|---|
| 口径 | 一周内 `tenant_signup_succeeded` 次数（按次，不去重个人邮箱） |
| 来源 | FR-15 |
| 时间窗 | 上海自然周，事件时间 |
| 目标 | 建基线 |
| 诊断用途 | WACT=0 时：若注册也是 0，获客句失败；若注册>0，断在登录或出数 |

### D2 注册后 168h 首次登录率

| 字段 | 内容 |
|---|---|
| 口径 | 分子：该周注册成功的企业中，注册时刻起 168h 内出现至少一次 `login_succeeded` 的去重企业。分母：该周注册成功企业 |
| 来源 | FR-15 `tenant_signup_succeeded` + `login_succeeded`（必须能把登录关联到企业） |
| 时间窗 | 每家企业从注册时刻起滚动 168h |
| 目标 | 建基线。Wave 0 修好成功页后，此率应可从「几乎无法发生」变为「可观测」——仍不设百分比目标 |
| 诊断用途 | 分母有、分子无 = 仍停在 FR-04 断链 |

### D3 TTFV（注册 → 首次出数）

| 字段 | 内容 |
|---|---|
| 口径 | 对已发生首次 **`is_marketplace_candidate=false` 且 `result_count>0`** 的 `task_completed` 的企业：该次时间 − 注册成功时间 的 **中位数**（不用平均数）。市场入站候选不构成首次出数 |
| 来源 | FR-15 |
| 时间窗 | 四周观察窗内完成首次出数的企业；未出数的企业 **不进入中位数分母**（另报「四周内仍未出数的注册企业数」） |
| 目标 | 建基线 |
| 诊断用途 | 登录率高但 TTFV 无穷 = Worker/配额/LLM 前置（Wave 4） |

### D4 周订阅成功租户数

| 字段 | 内容 |
|---|---|
| 口径 | 自然周内至少一次 `market_subscribe_succeeded` 的企业去重 |
| 来源 | FR-30 |
| 时间窗 | 上海自然周 |
| 目标 | Wave 1 对用户可用后建基线 |
| 诊断用途 | 列表浏览高、订阅 0 = 预告太多、许可闸、或登录回跳失败 |

---

## 4. 护栏指标

| 指标 | 口径 | 红线 | 来源 | 超线 |
|---|---|---|---|---|
| 跨租户可见事故 | 经复现确认：企业 A 读到 B 的任务/结果/安装/成员；含出站钥匙混拉两家企业行（GWT-08.4） | **0** | 越权审计 + 手工复现 | 停发布，先修隔离 |
| 公开泄漏未上架/黑名单/未放行许可 | 抽检公开列表/详情出现上述资产 | **0** | 对账 + FR-18 | 关公开市场或回滚上架 |
| 同窗口任务失败率 | 失败 /（完成+失败）；窗口与「近 7 日结果」相同；排除候选任务 | 相对基线 **上升 10 个百分点** | 任务状态（须与 FR-16 同一窗口） | 停止市场大推与采集对外承诺 |
| 非超管改渠道或平台 LLM 成功 | 成功写次数 | **0** | 审计 | 视为 Wave 0 未完成 |
| 配额拒绝不可理解 | 用户可见文案含 `QUOTA_EXCEEDED` 或仅错误码 | 抽检 **0 次** | FR-12 验收 | 不作为增长手段上线 |
| 公开页失败装空 | 首页精选或市场列表把加载失败渲染成「暂无/还没有」 | 抽检 **0 次** | FR-01.4、FR-28 | 阻止发布 |

渠道探针「伪装」次数 **不是** 产品北极星，也不进 OEC；只作值班护栏的观察项，无红线数字（无误杀金标，algo）。

---

## 5. 埋点契约（事件名冻结）

字段最低集：`occurred_at`、`anonymous_id` 或 `tenant_id`/`user_id`（已登录）、`role`（若已登录）。

| 事件 | 何时 | 关键字段 | 对应 FR |
|---|---|---|---|
| `official_page_viewed` | 打开首页/定价/市场/注册 | `page` | FR-15 |
| `official_cta_clicked` | 点主按钮 | `cta`：`register_free` / `pricing_pro` / `pricing_enterprise` / `login` / `browse_market` **分档不得合并** | FR-15 |
| `tenant_signup_succeeded` | 企业开通成功 | `tenant_id` | FR-15 |
| `login_succeeded` / `login_failed` | 登录结果 | `login_succeeded` 必须带 `tenant_id`；`login_failed` 含原因分类（凭证/过期/锁定）不含密码，能消歧到企业时带 `tenant_id`（GWT-15.4） | FR-15 |
| `task_run_submitted` | 提交采集 | `tenant_id`、`spider` | FR-15 |
| `task_completed` | 任务完成 | `tenant_id`、`result_count`、`spider`、`source`、`is_marketplace_candidate`（布尔；候选入站=true） | FR-15 |
| `results_exported` | 导出成功 | `format`、`row_count` | FR-15 |
| `quota_exceeded` | 配额拒绝 | `dimension`：concurrency / storage / llm_tokens | FR-15 |
| `market_list_viewed` | 打开市场列表 | 筛选：类型/宿主/分类 | FR-30 |
| `market_search_submitted` | 搜索 | `q`、`result_count` | FR-30 |
| `market_detail_viewed` | 打开详情 | 类型、上架态 | FR-30 |
| `market_subscribe_succeeded` / `rejected` | 订阅结果 | `host`、拒绝原因（`coming_soon` / `unlisted` / `license` / `auth` / `host_incompat` / `readonly`） | FR-30 |
| `market_uninstalled` | 卸载 | `host` | FR-30 |
| `market_listing_changed` | 超管改上架 | 新态/旧态 | FR-30 |
| `market_source_sync_completed` | 同步结束 | 成功数/失败数 | FR-30 |

失败上报 **不得** 挡住用户主路径；但验收时查询面必须能查到成功路径事件。

---

## 6. 缺口盘点

| 指标 | 需要 | 现有 | 状态 | 处理 |
|---|---|---|---|---|
| WACT | `task_completed` + `is_marketplace_candidate` + `spider`/`source` | 任务表可弱重构，无事件、窗口与仪表盘不一致 | ❌ | FR-15 GWT-15.1 + FR-16 |
| 登录率 | `login_succeeded` 关联企业；`login_failed` 可查 | 登录不落事实表（analyst Q9） | ❌ | FR-15 GWT-15.1 / GWT-15.4 |
| CTA 分档 | 分档 cta | 三档曾进同一注册 | ❌ | FR-15 |
| 订阅漏斗 | 浏览→详情→订 | 无表无事件 | ❌ | FR-30 |
| 配额拒绝 | 计数 | 只抛拒绝 | ❌ | FR-15 |
| 导出 | 发生 | 无审计 | ❌ | FR-15 |
| Hero 规模 | — | 静态文案 | ⚠️ 不可作基线 | FR-02 删除 |
| 渠道×采集因果 | 联接 | 无 | ⚠️ 不可测 | 不进 OEC；访谈替代 |
| 数仓分层 | ODS/DWD | 不存在 | ⚠️ 本轮不建 | 下一轮 warehouse |

---

## 7. 漏斗（步骤规则，供 analyst 复盘）

### F1 激活（官网 → 第一次出数）

- 不允许把「直接打开后台登录」算进官网漏斗分母（那是另一条入口，分开报）。
- 回退再前进：按企业取 **首次** 到达该步的时间。
- 步间时间窗：168h（与 D2 一致）。

步骤：曝光（page_viewed）→ CTA → 注册成功 → 首次登录 → 首次提交任务 → 首次 `is_marketplace_candidate=false` 且 `result_count>0` 的 `task_completed`。今日除注册行与任务行外 **全是洞**；Wave 0 后应可数。

### F3 市场（浏览 → 订阅）

步骤：list_viewed → search（可选）→ detail_viewed → subscribe_succeeded。预告详情的订阅拒绝进 `rejected`，不算成功。Wave 1 前全部不可测。

---

## 8. 交给下游

| 谁 | 内容 |
|---|---|
| architect | 事件能否进可查询存储；不改事件名与口径 |
| backend / frontend | 上表事件名与字段即验收契约 |
| qa | FR-15 / FR-30 GWT：查询面真能查到 |
| analyst | 四周后只描述变化，无对照不断言「因为上线」 |
| dba | `occurred_at` 的业务语义 = 事件发生时间；报表日 = 上海日历日 |

---

## 9. 自检

- [x] 北极星 1 个，离用户价值（出数）最近
- [x] 驱动 4 个，能解释断在获客/登录/出数/订阅哪一环
- [x] 护栏有红线，含隔离与泄漏 = 0
- [x] 四要素：口径/来源/时间窗/目标
- [x] 时间窗：事件发生时间 + 上海业务日
- [x] 缺口逐条；缺的写成 FR
- [x] 不可测给了替代（因果、Hero）
- [x] 无基线 → 目标=建基线
- [x] 判定周期 4 周
- [x] TTFV 排除市场候选（`is_marketplace_candidate=false` 且 `result_count>0`）

## 10. 版本

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.1 | 2026-09-07 | 护栏为 analyst 唯一口径；WACT 排除候选 |
| v1.2 | 2026-09-07 | QA-22：spec 护栏改为复制第 4 节，删「逐条一致」。QA-26：TTFV 与 F1 末步排除市场候选且要求 result_count>0 |
