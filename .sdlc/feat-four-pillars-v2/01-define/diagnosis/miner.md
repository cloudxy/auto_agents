# 数据挖掘诊断 · feat-four-pillars-v2

> 作者：/miner（as-of 纪律）｜日期：2026-09-08｜定义帽只读复审  
> 上游：`INPUTS.md` 书单 · 旧 `.sdlc/feat-four-pillars/01-define/diagnosis/miner.md`（2026-09-07 refresh）· `CONTEXT.md` · 本机联调 MySQL/Redis  
> 下游：`/pm`（本程序是否写离线模型 FR）· `/dba`（登录/配额事件 vs 幽灵列）· `/analyst`（WACT ≠ churn）· `/warehouse`（仍无仓）  
> **本文件不是训练产物。未训练、未引入 ML 依赖、未新增产品 FR。**  
> 旧程序工件只作对照，**不复制为现行合同**。

---

## 0. 结论（先说清楚）

**本程序不上预测模型。交付判定 = N/A（规则基线），不是「下一波再训」。**

操作者点名复审的三件事——租户分群 / 行为流失 / 异常（含过期登录）——现网数据**全部撑不住**。不是缺一个算法，是：没有量化动作、没有独立金标、没有 as-of 快照、样本量是个位数、若干「看起来像标签」的列会泄漏或撒谎。

| 检查项 | 2026-09-08 现网证据 | 结果 |
|---|---|---|
| ML 依赖 | 根 / `backend/pyproject.toml` 无 sklearn / xgboost / torch / lightgbm / mlflow / onnx；源码 0 命中 `fit(`/`KMeans` | **无训练栈（正确状态）** |
| 数仓 | 业务库无 `ods_`/`dwd_`/`dws_`/`ads_` 表；仓库无 `metrics.yaml` | **无特征层** |
| 动作定义 | 旧 spec v1.4 范围外：「数仓 + 离线模型 → 下一轮」。v2 尚未冻结新 spec | **pm 未授权建模** |
| 现网样本（本机 `auto_agents`，Alembic stamp **030**） | 租户 **4**（全 `active`，`expires_at` 全 NULL）；用户 **6**；`spider_tasks` **0**；`spider_results` **0**；`llm_token_usage` **0**；`channel_probe_results` **0**；`channel_events` **0** | **租户级 N 不够撑 Precision@K，任务/用量/探针是空集** |
| 现有「分数」 | 质量公式 / 代理加权 / 探针 10 维 / LLM 四维 / `derive_tier` | **全是规则或 LLM，0 个监督模型** |

把其中任何一个分数当监督学习的 y、再用同一套输入当 X，就是标签泄漏。复杂模型必须先证明超过规则基线；四柱里**没有一柱跨过这道门**。v2 全新方案必须把「不上离线模型」写成范围外，而不是漏写成 Wave 某票。

### 0.1 对照旧 miner（仍成立 vs 本机新事实）

旧稿（2026-09-07）主结论全部仍成立。本回合**没有推翻「不训练」**；有三条必须进全新方案的现网更正。

| 旧稿说法 | 2026-09-08 复跑 | 处置 |
|---|---|---|
| 到期租户「登录拒绝」是假测试 | **仍假。** `AuthService.authenticate` / `load_auth_identity` / `get_current_user` / 租户中间件 **均不读** `tenants.status`。`test_expired_tenant_login_rejected` 只断言巡检把 `status` 写成 `expired`，**没有 POST /login**。`TenantExpiryService` **未挂** `create_app` lifespan | 合约状态 ≠ 不能用产品。用 `status=expired` 当 churn y **更错** |
| 「无 `last_login_at`」 | **过时。** 现网 `users.last_login_at` 列已在；git ORM `User` **无此字段**；全库 `last_login` **0 命中**（登录路径不写）。6 人仅 **1** 非空（`admin` = 2026-09-06 18:00:47），其余 NULL | 幽灵列，不是登录事实表。不能当流失特征 |
| Alembic 头 = 027；028/029/030 是无 `.py` 的幽灵 pyc | 工作树 versions **仍无** 028/029/030 `.py`；本机库 `alembic_version=030`。pyc 名 `030_heartbeat_perms_last_login.py`。库内多出 `plans`（2 行套餐种子）/`orders`(0)/`tenant_subscriptions`(0)/`api_keys`(0) | **schema drift**：现网超前于 git。禁止把幽灵 `orders`/`plans` 当付费金标 |
| 质量公式分母/REQUIRED 死配置/content JSON 饱和 | **代码未改**（`quality.py` / `build_item` / `open_spider` 读 `required_fields` 但 `process_item` 不用） | 规则基线仍坏；建模前先修公式 |
| 代理阈 0.5 vs Scrapy 点号键 0.2 | **仍在。** `scrapy/settings.py` 平铺了 `QUALITY_CHECK_*`，**未**平铺 `PROXY_HEALTH_*` | 口径分裂 |
| `listing_state` / `capability_installs` / `POWER_MARKET` 0 命中 | **仍 0** | 无安装转化样本 |
| FR-15 事件名仓库 0 命中 | **仍 0**（`login_succeeded` / `task_completed` / `quota_exceeded` 均无产品埋点） | 行为流失不可标 |
| `check_llm_tokens_month` 只在测试 | **仍只在测试。** 生产调用点：`check_task_concurrency`（入队）、`check_result_storage`（回流）。`llm_chat` 不调月度闸 | 用量预警没有「真撞过」的 429 事件 |
| 无 MCP → 设计 `unknown`、代码 `degraded` | **仍写 `degraded`**（`plugin_service.verify_plugin` L192） | 健康列不能当异常 y |

---

## 1. 角色边界与本回合遵守

| 我管 | 不归我 |
|---|---|
| 离线预测 / 分群 / 异常的问题定义、as-of、泄漏、基线、失效边界 | 线上 LLM/RAG（→ `/algo`） |
| 现有启发式是否被误当成「模型」 | 产品 FR 与波次（→ `/pm`） |
| 特征在预测时刻是否可拿到 | 数仓分层与 `metrics.yaml`（→ warehouse / analyst） |
| **本程序该不该上模型** | 实现代码 / 训练作业 / 仪表盘 |

**本回合遵守**

- 不训练，不引入 ML 依赖。仓库无 ML 包是正确状态。
- 不把「建流失 / 分群 / 渠道风控 / 资产 LTR」写成 v2 FR。
- 动作未定义的候选：**只框问题、不建模型**。
- 现网空表不编造正例率。N=4 租户、任务=0 就是结论的一部分。

**miner 输入契约（SKILL.md）**

| 输入 | 现状 |
|---|---|
| 带量化动作的业务问题 | **缺失。** 四柱启发式都有闸门，没有「预测出来做什么、处理能力上限 K、主指标」 |
| 数仓 dwd_/dws_ | **不存在** |
| metrics.yaml | **不存在**（旧蓝图有 WACT / 注册登录率 / TTFV / 订阅；明确禁止单任务质量分、技能平均分当北极星） |

没有数仓与动作定义，任何离线分数都不可部署。下面的特征字典是**候选清单**，不是可训练特征表。

---

## 2. 现网数据审计（分群 / 流失 / 异常能不能撑）

快照：本机联调 MySQL `auto_agents` @ 127.0.0.1:3306，2026-09-08。这是操作者工作区的现网 OLTP，不是另一套生产仓。ops 仍报告 **0 客户工单、无 UV**。

### 2.1 租户状态

| 项 | 现网 |
|---|---|
| 行数 | **4**：`default` / `co-24634` / `co-25727` / `platform` |
| `status` | 4/4 = `active`。**0** 个 `expired`/`disabled` |
| `expires_at` | **全 NULL**（不过期）。到期巡检对这 4 行无事可做 |
| `quota` | 仅 `default` 有 JSON（免费档三键）；两家演示公司 `quota=null`（运行时与 `DEFAULT_QUOTA` 合并）；`platform` NULL |
| 回写路径 | `expire_overdue_tenants`：`expires_at < now AND status=active` → `status=expired`。服务类存在，**lifespan 未 start** |
| 运营改状态 | `tenant_admin_service` 白名单透传 `active/expired/disabled`（当前行，无历史） |

**分群含义：** 状态维没有方差。4 个点不能做 K-Means，也不能做「生命周期阶段」监督学习。可执行的规则分箱（用量/配额比、是否用过采集、是否用过 LLM）在现网也会塌成「全没用过」。

**流失含义：** `status` 今日全是 active，且该列由到期巡检/运营 PATCH 回写。用当前 `status` 当 y = 标签泄漏 + 恒等式（一旦开始写 expired，特征若含 `expires_at` 即满分）。

### 2.2 用量

| 源 | 现网 | 能否当特征 |
|---|---|---|
| `llm_token_usage` | **0 行** | 表结构可用（租户×维×模型×`stat_date`），**没有历史** |
| Redis `llm:usage:*` | **0 键** | 日/月计数未产生 |
| Redis `quota:count:*` | **0 键** | 60s 计数缓存空 |
| `QuotaService.usage_overview` | 即时 `COUNT` 活跃任务 / 结果行 / 当月 token | 看板不是事件；`tenant_usage.py` 用 **`datetime.utcnow()`** 拼 `year_month`，与蓝图 **Asia/Shanghai 业务日** 分裂 |
| `usage_by_member` | `MAX(spider_tasks.created_at)` 当 `last_active_at` | 任务表空 → 成员用量空。这是全历史 MAX，不是登录 |
| 月度 LLM 闸 | `check_llm_tokens_month` **生产 0 调用** | 套餐数字不挡 `llm_chat`。没有「真的撞过配额」的校准样本 |
| 超限 | 抛 429 `QUOTA_EXCEEDED`，**不落事实行** | 配额耗尽预警只能外推规则，不能分类 |

幽灵计费表（git 无 ORM）：`plans` 2 行（free ¥0 / pro ¥29900，与定价页数字同源）；`orders` 0；`tenant_subscriptions` 0。**0 笔支付，不能当「是否续费」金标。** 这些表是 028/029 幽灵迁移留在本机库里的，v2 方案若当付费事件用，会把 drift 写进模型。

### 2.3 任务结果

| 源 | 现网 |
|---|---|
| `spider_tasks` | **0**。WACT 弱重构分子 = 0。没有 completed∧result_count>0 |
| `spider_results` | **0**。`quality_score` / `content_hash` 无样本可看分布 |
| `spider_schedules` / templates | 0 |
| `ai_plans` | 0 |
| `spider_definitions` | 6 条 yml_seed（openweather/dianping/zhihu/generic/flow_generic/skill_harvester），全挂 `tenant_id=1` |
| `skill_jobs` | 9 行 **全部 done**（扫描类，不是采集任务） |
| Dashboard 质量卡 | `fetchRecentCompletedTasks(5)` 后 **只取 ids[0]**（旧稿「只画最近 1 个完成任务」仍真） |
| 试采闸 | `_judge_test`：`completed ∧ result_count>0 ∧ avg_score≥40`（40 硬编码） |

**异常检测：** 条目空字段/重复的规则基线代码还在，但现网 0 条 item，做不了 Top-N 坏例实证。公式缺陷（§4）在空表上不会被看见，上线后会污染任何「低质率」时间序列。

市场候选与租户结果仍同表（`source=marketplace`）；配额 `COUNT spider_results` **仍不排除** marketplace（旧 dba P0，代码未改）。任务=0 所以今天没爆，方案里必须当数据契约写进去，否则将来候选会顶满存储并污染租户用量特征。

### 2.4 过期登录（本任务点名）

登录链路现网事实：

```
POST /auth/login
  → Redis 失败限流（login_fail:{username} TTL 900s）
  → AuthService.authenticate：只查 users（is_active + 密码），不 JOIN tenants
  → 成功：发 JWT（tenant_id 来自 user 行），不写 last_login_at，不写 operation_logs，不发 login_succeeded
  → 失败：INCR login_fail，401「用户名或密码错误」（不区分过期租户）
```

后续请求：

- `load_auth_identity`：只读 `users`（含软删行），字段无 tenant.status。
- `get_current_user`：停用判定 = `identity.is_active`（用户开关，不是租户到期）。
- `TenantContextMiddleware`：非超管直接用 **JWT 里的 tenant_id** 进 `tenant_scope`，不复核租户 status。过期租户的有效 token 可继续跑任务/打 LLM。

`users.last_login_at`：

| 面 | 事实 |
|---|---|
| 库 | 列存在，可空 |
| ORM / 服务 | **不映射、不更新**（git 0 命中） |
| 现网填充 | 6 人 1 非空 |
| 来源 | 幽灵迁移 `030_heartbeat_perms_last_login`（仅 `__pycache__/*.pyc`，无 `.py`） |
| 当特征？ | **否。** 预测时线上写路径已消失；用当前列 = 用过期脏值；也不是事件流（无失败、无会话） |

Redis：`login_fail:soft-del` 一条（测试残留），不是生产失败事实。

`operation_logs`：**627** 行（2026-09-03 → 2026-09-08），无 `tenant_id`、无登录 action。Top 动作是 `member.create/delete` 与 LLM provider CRUD。不能冒充漏斗或活跃。

**结论：** 「过期登录」在产品文案/测试名里存在，在鉴权事实上**不存在**。流失标签若写成「到期后无法登录」，与现网行为矛盾。这必须进 v2 spec：要么把拒绝登录做成 FR（backend，不是 miner），要么明确 expired = 合约标记、不算停用。

### 2.5 样本构造（若有人仍想训——现在就会停）

| 项 | 内容 |
|---|---|
| as-of 点 | 无日快照，只能用「今天」——必然泄漏当前状态列 |
| 租户样本 | 4 行，其中 1 个是 `platform` 应排除 → 业务租户 ≤3 |
| 正例 | 行为流失：标签窗内任务/token 全 0，但特征窗也全 0 → 新客与流失不可分 |
| 任务/条目样本 | 0 |
| 渠道样本 | 探针 0；`NEWAPI.PROBE_ENABLED` 默认 false |
| 切分 | 时间切分后测试集为空。随机切 4 行是实体泄漏 |

**N/A 判定在样本层就已经成立。** 不必再讨论树模型超参数。

---

## 3. 问题定义（动作优先 · 三问皆 BLOCKED）

模板纪律：没有决策用途的模型不要建。

### 3.1 分群

| 项 | 内容 |
|---|---|
| 业务问题 | 租户用量/生命周期可能不同，运营也许要差异化配额或触达 |
| **预测出来做什么** | **未定义。** 没有「每群一套策略」、没有运营能同时维护的套数 |
| 谁执行 | 未知 |
| 处理能力 | 未知（Q7） |
| 现网 | 4 个 active、0 任务、0 token。规则分箱也会得到同一个「从未出数」群 |
| 方法 | **业务规则分箱优于 K-Means**（SKILL segmentation）。N 个点不够撑聚类 |

**不做算法聚类。** 若 `/pm` 将来要 3 档运营（新客 / 有出数 / 沉默），用 SQL 分箱即可，且必须排除 `platform`、排除市场入站任务。

### 3.2 流失

三个不得混进一个模型的问题：

| 子问题 | 事件定义（需 /pm） | 现在有没有数据 |
|---|---|---|
| 合约流失 | 到期未续费 | `expires_at` 全 NULL；`status` 全 active；幽灵 `orders`/`tenant_subscriptions` 为 0。标签与 `expires_at` 同源则恒等 |
| 行为流失 | as-of 后 N 天无任务、无 token、无登录 | **无登录事件**；任务与 token 表空；`last_login_at` 不可用 |
| 配额耗尽预警 | as-of 后 7 天内撞月 token / 结果行 | 有限额默认值；无用量历史；无 429 事件。这是**外推规则**，不是分类器 |

旧稿行为流失 SQL 草稿（间隔 7d、标签窗 30d、排除合约到期）**逻辑仍对**，现网跑出来会是：特征窗全 0、标签窗全 0、人群被「注册满 30 天且曾活跃」滤成空集。

WACT（完成且出数的企业周去重）是**分析北极星**，不是 churn 标签。禁止把「WACT=0」训成流失模型——Worker 未进 compose 时全员 WACT=0（sre 已诊断），模型会学到「平台没启 Worker」。

### 3.3 异常

| 面 | 今日动作 | 能否上异常模型 |
|---|---|---|
| 采集空壳/重复 | 试采 avg&lt;40 失败（硬编码）；无丢条目/抽检队列 | 规则基线先修分母与 JSON 饱和。无金标 |
| 渠道伪装 | 写 `channel_probe_results` + `notify` spoofed；**不下线**（旧 FR-61） | `verdict` 即启发式。蒸馏 = 离线完美。现网 0 行 |
| 渠道额度 | 窗口 SUM≥limit → status=3 | 硬阈值正确；预测「明天超限」无提前量需求 |
| 过期仍登录 | **无检测、无拒绝** | 这是产品缺陷，不是点异常模型。修鉴权 |
| 资产/上架 | listing 未落地 | 禁止 LTR |

无监督异常同样要动作与审核产能。现网没有值班队列 K。

---

## 4. 启发式仍不是模型（四柱分数一览，0 个离线模型）

相对旧稿未变的生产分数，只列 miner 决策需要的：

| 名称 | 实现 | 下游动作 | 是不是模型 |
|---|---|---|---|
| 采集质量分 | `scrapy/pipelines/quality.py` 50/30/20 | 试采 avg&lt;40 失败；Dashboard 最近 **1** 个完成任务 | 否；分母含内部字段；`REQUIRED_FIELDS` 死配置；`build_item` 把字段 JSON 塞进 `content`，空抽取也是 `"{}"` |
| 内容指纹 | consumer `md5(url+title+content)` | 仅 `incremental=true` 跳过入库 | 否 |
| 质量 dup | `md5(url\|title)` 进程内 `_seen` | 重复条 dup_score=0 | 否；offline≠online |
| 代理分 | 全期 success_rate×0.6+延迟；Redis 无快照 | Scrapy 低分阈静默 **0.2**；健康服务 **0.5** | 否 |
| 渠道真伪 | 10 维 + `ref_sim<0.15` | 只通知 | 否；现网 0 行 |
| 技能评分 / tier | LLM 四维；`derive_tier` 人工缺则用 AI | 列表 `sort=score\|tier`；官网 S/A 精选 | 否；无人终评时 AI 排首页 |
| 租户到期 | 巡检回写 status | **登录不消费** | 否 |
| 配额 | 并发/存储有闸；LLM 月度闸未挂推理 | 429 无事件 | 否 |

**规则基线应先修、仍未修（建模前的数据质量，不是本诊断实施）：**

1. 质量分母用 `item.fields.keys()`，含 `task_id/id/created_at/updated_at/extra/_quality_score`；`_quality_score` 写在完整率之后，打分时恒空。
2. `self.required_fields` 只在 `open_spider` 赋值，`process_item` 从未使用。
3. `flow_generic`/`build_item`：`content = json.dumps(fields)` → 核心维 30 分几乎送满。
4. 仓库仍无 `QualityCheckPipeline` 单测；avg&lt;40 只在 planner mock。
5. 代理阈未平铺进 Scrapy Settings。

---

## 5. 泄漏风险（现网对照 · 五类）

### 5.1 时间泄漏

| 风险 | 位置 | 说明 |
|---|---|---|
| 维度表当前状态 | `tenants.status` / `users.is_active` / `users.last_login_at` / 资产 `status` | as-of 之后会被巡检、人工 PATCH、幽灵列停写。必须事件流或日快照 |
| `updated_at` | 几乎所有业务表 | 不能当最后活跃 |
| 代理全期累计 | Redis `spider:proxy:stats`（现网 0 键） | 无 as-of |
| LLM 月用量 | `stat_date`；看板 `utcnow` | 必须 `stat_date < :asof` 且上海日界 |

### 5.2 切分前统计

尚无训练集。对 4 个租户 `scaler.fit(全表)` = 测试集均值即标签。**禁止。**

### 5.3 标签泄漏（最危险）

| 若预测… | 禁止当特征 / 禁止当标签 | 原因 |
|---|---|---|
| 租户流失 | `status`、`expires_at`、`deleted_at`、幽灵 `orders.status` | 标签由这些字段定义或事后回写；expired≠停用 |
| 采集失败 / 试采通过 | `quality_score`、试采 `passed` | 闸门就是分数 |
| 渠道伪装 | `verdict` / `scores.*` | y 由同一函数生成 |
| 渠道将禁用 | 同条 `channel_events.usage` | 动作写入用量上下文 |
| 资产将上架 / 上首页 | `score`/`tier`/`status`/`ai_suggested_score` | 运营与前端按它们曝光 |
| 「最近登录过」 | 当前 `last_login_at` | 列已停写；不是事件 |

### 5.4 实体泄漏

租户/渠道/资产会跨 as-of 重复。随机切行会记住「租户 #1 是 default」。切分必须时间顺序 + 实体不跨集。N=4 时这条与样本量冲突 → **停**。

### 5.5 未来聚合

套餐流失率、源级平均质量分、全期 token SUM：小样本下等于泄漏 y。

### 5.6 线上线下口径分裂（现在就有，无模型也会害分析）

| 分裂 | 离线容易用的 | 线上实际 |
|---|---|---|
| 去重 | `content_hash` 跨任务 | 质量管道仅进程内；hash 公式还少 content |
| 质量分母 | 业务字段 | `item.fields` 含内部列 |
| 核心维 | 选择器是否抽对 | `content` 可能是 `"{}"` |
| 代理阈 | Dynaconf 0.5 | Scrapy 0.2 |
| 公开列表 | 管理端全状态 | 技能 `stable+recommended`；能力仅 `stable` |
| 业务日 | 蓝图上海 | 用量 `utcnow`；stats `datetime.now()-6d` |
| 登录活跃 | `last_login_at` 列 | 登录不写；报表用任务 MAX |
| Alembic | git 头 027 | 本机 stamp 030 |

---

## 6. 特征缺口（缺的是事件，不是算法）

### 6.1 SaaS（本任务主面）

| 缺口 | 为什么需要 | 现状 |
|---|---|---|
| 登录成功/失败事实 | 行为流失、蓝图 D2 | Redis TTL 失败；成功不落库；幽灵列停写 |
| 配额超限事件 | 预警校准 | 只 429 |
| 套餐变更事件 | 合约流失 vs 降配 | `quota` JSON 被 PATCH 覆盖；幽灵 `plans` 与租户行未关联 |
| 租户日快照 | as-of 状态 | 无 |
| 到期是否拒绝登录 | 合约流失标签语义 | 现网不拒绝（产品未决） |

### 6.2 采集 / 中转 / 市场

与旧稿相同：无条目金标、无 HTTP/反爬字段、无探针 raw、无人工 spoofed 金标、无安装表、无 git 活跃度。现网对应表还是 0 行。

### 6.3 平台级（阻塞所有建模）

- 无 dwd_/dws_/ads_，无 metrics.yaml。
- 无 as-of 快照。
- 无训练/推理特征存储。不要把模型分写回 `score` / `quality_score` / `last_login_at`。
- 蓝图事件 `task_completed` / `login_succeeded` / `quota_exceeded` / `market_subscribe_succeeded` 仍是名字，不是表。

---

## 7. 现在不该建模的清单（硬 · 进 v2 方案范围外）

| ID | 不要做 | 原因 | 何时可以重新讨论 |
|---|---|---|---|
| N1 | 租户 churn 分类/回归 | 动作未定义；无登录事件；N=4；`status`/`expires_at` 泄漏；expired≠停用 | `/pm` 定义动作与「活跃」；登录事实落地；N 够撑 Precision@K |
| N2 | 用户级流失 | 无会话；`last_login_at` 幽灵列；`updated_at`/`is_active` 泄漏 | 同上 |
| N3 | 用 `quality_score` 当 y | 恒等式 | 独立金标 + 抽检产能 + 先修公式 |
| N4 | 蒸馏渠道 `verdict` | 教师即规则 | 人工金标；spoofed 有复核动作 |
| N5 | 预测渠道将被禁用 | 标签泄漏 | 不要做 |
| N6 | 资产 listing / 首页 LTR | D7 禁止自动上架；score/tier 泄漏 | 永远优先人工闸 |
| N7 | 安装转化 | 无表无流量 | 商店面上线后归 `/analyst` |
| N8 | 租户 K-Means / embedding 分群 | 无用途、N=4、全零用量 | 运营先有 3–6 套策略；规则分箱 |
| N9 | 代理 LTR | Redis 无历史；探索偏差 | 先窗口成功率 + 阈值对齐 |
| N10 | 用 SKILL.md 训 `real_world_effect` | 文案泄漏 | 安装/调用遥测 |
| N11 | 在 OLTP 上 `fit` | 无切分基建；会锁本机 4 行「生产」库 | 数仓 + 只读账号 |
| N12 | 准确率当指标 | 不平衡 | 有 K 时用 Precision@K / lift |
| N13 | WACT / 技能平均分当模型目标 | 蓝图禁止后者当北极星；前者是计数 | `/analyst` |
| N14 | 用幽灵 `orders`/`tenant_subscriptions` 当付费 y | git 无 ORM、0 订单、schema drift | 计费产品落地且与租户行有事件，而不是 stamp=030 的空表 |
| N15 | 用 `last_login_at` 当「活跃」 | 登录不写；6 人 5 空 | 登录事件表 |

**规则优于模型的默认策略：** 四柱先把启发式变成可配置阈值 + 留痕 + 人工复核。这不是失败。v2 方案保持「离线模型下一轮」。

---

## 8. 特征字典（候选 · 每个都有 as-of · 不训练）

> 每个特征必须能回答：在 as-of 时刻，这个值是多少？  
> 今日没有打分服务。「预测时可获取」= 若规则引擎要复用，数据在不在。  
> 现网缺失率：任务/用量类特征对全部租户 = 结构性 0，不是「未知」。

### 8.1 SaaS（租户级，as-of = 每日 00:00 **必须与蓝图上海日对齐后才能算**）

| # | 特征名 | 计算逻辑 | as-of 口径 | 来源 | 缺失含义 | 预测时可获取 |
|---|---|---|---|---|---|---|
| S1 | `tasks_30d_before_asof` | 任务数（排除 marketplace 入站） | `created_at < :asof AND >= :asof-30d` | `spider_tasks` | 现网全 0 = 无采集 | ⚠️ 表空；T+1 |
| S2 | `tokens_30d_before_asof` | `SUM(total_tokens)` | `stat_date < DATE(:asof)` 上海日 | `llm_token_usage` | 现网全 0 | ⚠️ 表空；flush 延迟未对齐 |
| S3 | `quota_token_util_at_asof` | 月累计 / `llm_tokens_month` | 月界 &lt; as-of | 用量 + **quota 快照** | 缺 JSON=默认档；当前行会被 PATCH | ❌ 无快照 |
| S4 | `days_since_last_task_at_asof` | as-of − MAX(created_at)&lt;asof | 任务窗 | `spider_tasks` | 从未有任务：新客，排除出流失人群 | ⚠️ 现网全是「从未」 |
| S5 | `active_members_30d_before_asof` | `COUNT DISTINCT created_by` | 任务窗 | `spider_tasks.created_by` | 调度归系统 | ⚠️ 表空 |

**排除**

| 候选 | 原因 |
|---|---|
| `tenants.status` | 标签泄漏；且不代表不能登录 |
| `tenants.expires_at` | 合约问题；与巡检定义 y |
| `users.last_login_at` | 幽灵列，登录不写 |
| `users.updated_at` / `is_active` | 当前状态 |
| 报表 `last_active_at` | 即 MAX(created_at)，与 S4 重复 |
| `orders.status` / `tenant_subscriptions.status` | 幽灵计费；0 行；预测时 git 代码拿不到 |
| 登录次数 | **预测时拿不到**（无事件表） |

### 8.2 采集（任务级，as-of = 提交时刻）

| # | 特征名 | as-of 口径 | 预测时可获取 |
|---|---|---|---|
| C1 | `src_fail_rate_14d_before_asof` | 同 spider_name，`created_at < :asof` | ⚠️ 无 dws；现网 0 任务 |
| C2 | `src_empty_rate_14d_before_asof` | completed∧result_count=0 | ⚠️ |
| C3 | `dup_rate_hash_14d_before_asof` | consumer 公式，`created_at < :asof` | ⚠️ |
| C4 | `core_empty_at_parse` | 选择器字段，**不要看 JSON content** | ✅ 管道内（规则，非模型） |

**排除：** `quality_score`；提交时 `status`（还是 pending）；全期 AVG(quality_score)；进程内 `_seen`；`content` 是否非空。

### 8.3 中转 / 资产

候选 R1–R4 / P1–P4 与旧稿相同（探针 raw 未落库；源表未建）。现网 0 行，全部 ⚠️/❌。排除当次 `verdict`、`listing_state`、AI 分预测 listing。

### 8.4 as-of 核对（候选集）

- [x] 保留项均含 `< :asof` 或「当次输入」
- [x] 无 `CURRENT_DATE` 时间差（已排除 last_login 用「今天」）
- [x] 当前状态字段已列入排除（含幽灵 `last_login_at`）
- [x] 群体统计要求排除自身（未实现，因未训练）
- [ ] T+1 延迟未与 `/backend` 对口径
- [ ] 蓝图 Asia/Shanghai vs `utcnow` **仍未对齐**——阻塞，交给数仓 / analyst

统计变换：无训练，无全量 fit。

---

## 9. 建模前必须存在的清单（缺一则停）

| # | 必须有 | 谁给 | 今日 |
|---|---|---|---|
| M1 | 量化动作 + 每天处理上限 K | `/pm` | 未定义 |
| M2 | 独立金标（不是启发式输出） | `/pm` + `/dba` + 抽检产能 | quality/verdict/expired/tier/last_login_at 都不是 |
| M3 | 登录成功、配额超限、探针 raw 事件 | `/dba` + 产品埋点 FR | 规划中；幽灵列不算 |
| M4 | ODS 镜像 + 状态日快照 | warehouse | 无 |
| M5 | dwd_/dws_ 与 metrics.yaml | warehouse + analyst | 仅有旧蓝图 |
| M6 | 时间切分协议 + 只读账号 | warehouse + dba | 无；禁止对本机 4 行 `fit` |
| M7 | 主指标 Precision@K / lift | `/pm` 给 K | 无 K |
| M8 | 规则基线已修明显缺陷并留下数字 | `/backend` + `/qa` | 分母/死配置/content JSON/代理阈/到期登录 **均未修** |
| M9 | 样本量撑得起 K | `/sre` 给数量级 | 本机租户 4、任务 0；生产 n 未知 |
| M10 | 离线在线同一套特征代码 | `/qa` | 口径分裂已存在（§5.6）；git vs stamp 030 |

**M8 未完成时不要谈 M1 之后的模型。** 规则坏了，模型会学坏规则。M9 在本机已经失败。

---

## 10. Model Card · 预训练（N/A · 不填假数）

选定方案一律是 **规则基线**。无基线数字、无坏例 Top-10 实证（任务 0 / 探针 0）、无离线在线比对脚本。

### 10.1 租户行为流失 — 不训练

| 项 | 内容 |
|---|---|
| 预测目标 | 草稿：as-of 后 7–37 天无任务且无 token（**未批准**） |
| 决策用途 | **BLOCKED /pm** |
| 模型类型 | **不训练** |
| 基线① | 常量：全不流失 |
| 基线② | 规则「30 天无任务」——现网全员命中，Precision@K 无意义 |
| 切分 | 未做（样本不够切） |
| 泄漏排查 | `status`/`expires_at`/`last_login_at` 未通过 |
| 失效边界 | 新租户；合约到期仍可登录；纯登录型用户不可见；Worker 未启导致全员无任务 |
| 样本量 | 业务租户 ≤3 |

### 10.2 租户分群 — 不训练

| 项 | 内容 |
|---|---|
| 决策用途 | **BLOCKED /pm**（无每群策略） |
| 模型类型 | **不训练。** 若要运营可见：规则三档（新客 / 有出数 / 沉默），不要 K-Means |
| 失效边界 | 现网用量全零 → 一档；`platform` 必须排除 |

### 10.3 过期登录 / 异常 — 不训练

| 项 | 内容 |
|---|---|
| 决策用途 | 今日无拒绝、无告警 |
| 模型类型 | **不训练。** 产品规则：鉴权读 `tenants.status` 或明确「到期仍可用」 |
| 失效边界 | 把 expired 当异常分数 = 把巡检输出当 y |

### 10.4 采集质量 / 渠道伪装 / 资产 — 不训练

与旧稿 10.1/10.3/10.4 相同：保留规则；禁止用质量分/verdict/tier 当监督 y。现网无坏例可统计，只列机制性失效：JSON `"{}"` 过 40；未知家族漏报；无人终评 AI 上首页；无 MCP 标 degraded。

### 10.5 监控（无模型作业，不给 PSI）

规则侧可观察（归 /sre /analyst，不是 miner 上线）：试采因 &lt;40 失败比例；探针 spoofed 率（现网 0）；代理全员 0 分（探测 URL 默认 httpbin）；LLM 评分队列（worker 默认关）。

---

## 11. 基线阶梯（只评价规则，不上④）

| 级 | 方案 | 现状 |
|---|---|---|
| ① 常量 | 全不流失 / 全 original | 现网无正例，常量即「全部」 |
| ② 单规则 | 30 天无任务；核心字段全空；许可黑名单 | **应作为正式基线**；现网「30 天无任务」= 全体 |
| ③ 多规则打分 | 质量 50/30/20；探针 10 维；配额三闸 | **已在生产，修缺陷优先** |
| ④ 树模型 | — | **不进入。** 无动作、无金标、无数仓、N 不够 |

复杂模型必须证明超过简单基线且好得值那份特征管线。当前**没有一柱跨过这道门**。

---

## 12. 必须进全新方案的现网事实

v2 方案 / spec **必须写进范围外或 Wave 契约**，不得靠「默认不提」漏回去：

1. **本程序不交付离线模型**（流失 / 分群 / 异常检测 / 渠道分类 / 资产 LTR）。旧 spec「数仓 + 离线模型 → 下一轮」在 v2 保持。成功标准仍是四周能判定 WACT，不是 AUC。
2. **到期 ≠ 不能登录。** 巡检可写 `expired`，鉴权不读；测试名 `test_expired_tenant_login_rejected` 不测登录。`TenantExpiryService` 未进 lifespan。合约流失标签在产品拍板「到期是否拒绝」之前禁止使用。
3. **`users.last_login_at` 是幽灵列。** 本机 stamp 030 有列、git ORM/登录 0 写入、6 人 5 空。不得当活跃特征，也不得当 FR-15 已落地的证据。蓝图 D2 仍要 `login_succeeded` 事件。
4. **本机现网样本：租户 4（全 active、expires 全空）、用户 6、任务 0、结果 0、token 0、探针 0、订单 0。** 任何「先训一个看看」都会在 4 行上过拟合。生产 n 未知，不得用 Hero 示意数字当 n。
5. **LLM 月配额函数未挂 `llm_chat`；429 不落库。** 用量看板 `utcnow` 月界 ≠ 上海业务日。配额预警用规则外推即可，不要分类器。
6. **质量分 / 探针 verdict / derive_tier 不是金标。** 公式缺陷与口径分裂（代理 0.5 vs 0.2、公开闸两套、content JSON 饱和）未修之前，禁止学习排序。
7. **git Alembic 头与本机库不一致（027 vs stamp 030）。** `plans`/`orders`/`tenant_subscriptions`/`api_keys` 无 ORM。方案不得把这些空表当付费/续费事件源。
8. **`operation_logs` 627 行不能当活跃或漏斗。** 无 tenant_id、无登录 action。
9. **Power Market 安装/上架表仍不存在**（`listing_state` / `capability_installs` / `POWER_MARKET` 0 命中）。无转化样本。
10. **规则基线修缺陷（质量分母、REQUIRED 死配置、`"{}"` 不当 content、代理阈平铺、到期登录语义）属于 backend/qa，不转化为「质量模型」票。**

---

## 13. 交给下游

| 给谁 | 内容 |
|---|---|
| `/pm` | 本程序模型面 = **N/A**。Q1–Q7、Q13（到期是否拒登）未答之前停在规则。不要在 v2 spec 写流失/风控/推荐模型。WACT 不是 churn |
| `/analyst` | 先落 `metrics.yaml`。不要用两套 SQL 定义活跃。本机任务 0 → 四周 WACT 基线从 0 起，须与 Worker 未编排区分 |
| `/data-warehouse-engineer` | 本波仍不建仓。没有 ODS/快照 miner 不能 feature-as-of。时区：蓝图上海 vs 用量 UTC |
| `/dba` | 登录事实 ≠ `last_login_at` 列。配额超限事件。**不要**把模型分写入 `score`/`quality_score`/`last_login_at`。幽灵 030 与 git 头对账归你，不归 miner 训 |
| `/algo` | LLM 评分 / similar_suggest / 探针题仍归你。miner 不替代人工权威 |
| `/backend` | 到期登录语义、月度闸挂推理、质量公式、Scrapy 平铺代理阈——本诊断不实施 |
| `/qa` | 无模型一致性脚本。若修质量公式：内部字段不进分母；`"{}"` 不算有正文；补管道单测；到期登录测试必须 POST /login |
| `/sre` | 无模型作业。本机 n：租户 4 / 任务 0。代理探测默认 httpbin |
| `/ops` | 分群策略套数未定；0 工单不能推出「无需触达」 |

---

## 14. 自检（SKILL.md）

| 项 | 状态 |
|---|---|
| 特征字典含 as-of | 候选表有；未落地计算 |
| 时间切分非随机 | 约定了；未执行（无训练） |
| 无全量统计再切分 | 遵守（未 fit） |
| 基线对比 | §11 规则阶梯；无模型数字 |
| 坏例 Top-10 | **无金标且任务/探针为 0，未做。** 写了机制性失效 |
| 失效边界 | 各卡已写 |
| 离线在线一致性 | 未测模型；§5.6 记录已存在分裂 |
| 无动作则停 | 遵守；未训练 |
| 分群用途 | 未定义 → 不聚类 |
| 异常类型 | 过期登录是产品闸，不是点异常模型 |

未完成不等于半成品隐瞒：训练类格子是 **N/A + 阻塞原因**，诊断类格子已交付。

---

## 15. 开放问题（阻塞建模；不代答）

| ID | 问题 | 阻塞什么 | 需要谁 |
|---|---|---|---|
| Q1 | 采集低质量之后的动作？丢条目 / 重跑 / 抽检？每天上限？ | Precision@K vs 全量阈值 | `/pm` |
| Q2 | 「租户活跃」是登录、提交任务，还是消耗 token？行为流失是否排除合约到期？ | 标签 SQL | `/pm` |
| Q3 | 高流失风险租户要做什么？谁执行？每天几户？ | 是否建流失模型（默认否） | `/pm` |
| Q4 | 渠道 spoofed 后：只通知、进复核，还是自动下线？误杀成本？每天复核条数？ | 探针升级前提 | `/pm` |
| Q5 | `score`/`tier` 是否允许影响 listing / 首页？无人终评时 AI 已在排首页，可接受吗？ | 曝光当 y 与 D7 冲突 | `/pm` |
| Q6 | 源质量动作：停 sync / 保持 unlisted / 只告警？ | 规则阈值 | `/pm` |
| Q7 | 运营能同时维护几套租户策略？ | 分群数上限；默认规则三档 | `/pm` |
| Q8 | 是否建设登录 / 配额超限 / 探针 raw 事件表？（幽灵 `last_login_at` 不算） | 所有 as-of 特征 | `/dba` + `/pm` |
| Q9 | 生产租户数、渠道数、日任务量？本机是 4 / 0 / 0 | 除规则外任何模型 | `/pm` / `/sre` |
| Q10 | LLM 分与人工分不一致时谁赢？校准报表要不要做？ | `/analyst` vs 只展示 | `/pm` |
| Q11 | 试采 40、探针 0.15、代理 0.5/0.2 是否升配置并对齐 Scrapy？ | 规则产品化，仍不建模 | `/pm` → `/backend` |
| Q12 | metrics.yaml 第一批谁拍板？蓝图已有 WACT | 分析与特征对齐 | `/pm` + `/analyst` + 仓 |
| Q13 | 到期租户是否应该被登录拒绝？现网未拒 | `status=expired` 不能当「已离开」 | `/pm` + `/backend` |
| Q14 | 本机 stamp 030 幽灵表（plans/orders/subscriptions/api_keys/last_login_at）是否回滚、补 `.py`、还是当不存在？ | 禁止当付费/登录金标 | `/dba`（miner 只拒绝拿来训） |

**miner 立场：** Q1–Q7、Q13 未答之前，四柱全部停在规则基线。v2 全新方案不要写「本期交付流失模型 / 分群模型 / 渠道风控模型 / 资产推荐模型」。本程序模型面 = **N/A**。
