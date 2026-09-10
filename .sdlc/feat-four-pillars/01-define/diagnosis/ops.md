# 运营诊断 · feat-four-pillars（需求信号池 + 竞品拆解 + 增长埋点对照）

> 作者：/ops｜日期：2026-09-07｜稿次：**刷新**（相对同日初稿）｜下游：`/pm`（分诊输入，**不下 RICE / 不排期 / 不设计功能**）
> 范围：四柱——智能采集 + SaaS + 中转站（new-api）+ Power Market
> **无出处的信号不进本文件。** 本期没有工单系统、没有访谈记录、没有生产埋点；能写进池子的只有「仓库可核对的对外承诺 / 已冻结 PRD 与度量蓝图 / 设计文档陈述 / 公开竞品文档」。把它们当信号，不当用户投票。

**刷新相对初稿改了什么：** 初稿写「没有上一轮 P0 度量蓝图可对照」。同日 `/pm` 已冻结 `01-define/spec.md` 与 `01-define/metrics-blueprint.md`。本期仍 **不是 P9**（`hats_done: []`，Wave 0/1 未上线），但可以把「蓝图预测」和「仓库仍交付什么」并排。代码侧承诺/履约在本机复跑后 **未变**（见 §0.1）。新增 S-18 / S-19（增长埋点）。开放问题与 spec §9.1 对齐，ops **不代答**。

---

## 0. 任务边界与本帽能回答的问题

| 问 | 答 |
|---|---|
| 这是 P9 复盘吗 | **否**。`state.yaml`：`hats_done: []`，`tickets: []`，`current_hat: 定义`。没有上线后的四周窗。 |
| 有没有「原假设」可对照 | **有，但是预测尚未发生。** 北极星 WACT、四条驱动、FR-15/FR-30 事件名已冻结。仓库内这些事件 **零命中**。对照结果只能写成「假设已写下、履约未开始」，不能写成「提升失败」。 |
| 有没有增长数字 | **未获取。** 官网 Hero 三卡是「示意数据」（S-03）。后台 `/admin/stats` 是任务计数，不是获客/转化/留存。全库无 `metrics.yaml`、无产品分析 SDK。 |
| 有没有用户原声 | **无。** `.scratch/` 是工程票。定价页写「工单支持」，仓库内无租户工单模块（S-07）。 |
| ops 做什么 | 抽出**证据化缺口**：叙事错位、承诺未兑、竞品位置、埋点相对蓝图的空洞。不排优先级。 |

程序目标：智能采集 + SaaS + 中转站 / new-api + Power Market。  
对照物：官网 Home / Pricing / Features、`README.md` 产品概览、`CONTEXT.md`、`power-market-design.md`（Accepted）+ `power-market-design-review.md`（Approve，0 open）、冻结 `spec.md` / `metrics-blueprint.md`。

宪法：`sdlc.config.yaml` → `.claude/rules/project_rule.md`。本文件不写连接串、不写表结构、不写接口形状。

---

## 0.1 本机复跑（2026-09-07，定义帽只读）

| 核对项 | 结果 | 出处 |
|---|---|---|
| `POWER_MARKET` 配置键 | 全库 **0 命中** | grep `*.{py,yml,yaml,ts,tsx,md,toml}` |
| 产品事件名 / 分析 SDK | `official_page_viewed` / `tenant_signup_succeeded` / gtag / posthog / mixpanel / amplitude **0 命中** | grep |
| `xlsx` 导出 | 服务拒绝；测例期望抛 `BusinessException` | `spider_query_service.py`；`test_export_bad_format_raises` |
| 定价空头词（工单支持 / 渠道组 / stripe / 支付 / billing） | **仅** `Pricing.tsx` 两处卖点；无支付模块 | grep |
| `capability_installs` / `listing_state` / `/tenants/me/installs` | **0 命中** | grep |
| 免费档数字 | 定价「5 / 10,000 / 20 万」= `DEFAULT_QUOTA` | `quota_service.py`；`Pricing.tsx`；`Register.tsx` |
| new-api 默认 | `ENABLED` / `SCHEDULER_ENABLED` / `PROBE_ENABLED` 全 `false` | `config/default/newapi.yml` |
| 外部拉数 Key | `API_KEYS: []`（空=全拒） | `config/default/external_api.yml` |
| 设计评审 | Approve，0 open | `power-market-design-review.md` |
| 定义帽审查 | `fresh-context` **fail**；blocker QA-02 仍 open（WACT 排除字段未进 FR-15 GWT） | `state.yaml`；`05-review/findings.md` |

---

## 渠道与偏差声明

| 渠道 | 本期数据量 | 偏差 |
|---|---|---|
| 客户工单 / 客服 | **0**（无此系统） | 完全缺失；不能从「零投诉」推出「没问题」 |
| 应用商店评论 | **0** | 产品未上架应用商店 |
| 访谈 / NPS / 问卷 | **0** | 无付费用户样本 |
| 使用数据 / 漏斗埋点 | **未获取** | 无产品事件 SDK；后台 `/admin/stats` 不是增长 |
| 官网 / 定价 / README 对外承诺 | 已读且本机复跑 | **销售材料口径**（可靠性：**低～中**）：描述的是「想让用户相信的能力」 |
| 冻结 PRD / 度量蓝图 | 2 份（Wave 0/1 FR 冻结） | **内部预测**，不是市场抽样；Q-VOICE 等 6 问仍待确认 |
| 设计文档 / 设计评审 | Accepted + Approve、0 open | 操作者拍板 + 工程决策；**不是**用户投票「要市场」 |
| 本机插件树盘点 | 设计文档 §本机源盘点（2026-09-07） | 一台开发机；不能外推「市场有多少插件」 |
| 竞品官方文档 | Claude / Kimi / Grok / new-api；采集 SaaS 评测 | 官方文档 **高**；第三方评测 **中**；**未亲自付费试用** |
| 角色诊断（analyst 等） | 只读盘点 | 可作「现有计数器从哪来」的交叉；不是 UV |

**主动反馈用户通常不到 1%。** 本期连这 1% 的通道都没有。下方「影响面」一律标 **未量化**，不编人数。

**P9 对照纪律：** 蓝图目标是「四周后能报出每周 WACT=？」，不是「提升 x%」。今日实际：事件查询面不存在 → **预测未开始检验**。不得把 Hero 三卡、全历史成功率、渠道 24h 事件数写成「已经好于/差于假设」（蓝图 §1 禁止当 OEC）。

---

## 承诺 vs 履约（对外一句话对仓库）

同一访客在四面墙上读到互相打架的「我们是谁」，再点进去发现若干句现在走不完。这不是功能清单，是获客时会撞上的裂缝。

| 对外承诺（原文级） | 写在哪 | 仓库现状 | 信号 |
|---|---|---|---|
| 「AI 驱动的智能数据采集系统」；Hero 只讲爬虫 | `SiteLayout.tsx` `SITE_SLOGAN`；`Home.tsx` | README 四模块含 LLM + 中转；程序目标含 Power Market；官网导航无中转/LLM | S-01 |
| 「支持 CSV / Excel 一键导出」「多格式导出」 | `FeaturesSection.tsx` | 任务导出 `csv`/`json`；`xlsx` 抛错；数据中心最多 100 条 CSV | S-02 |
| `128,000+` 任务 / `12 节点` / `3.2 亿条` | `Home.tsx` `HERO_STATS`（标了「示意数据」） | 无对应 API；蓝图禁止当基线；FR-02 要求删除，**页面仍在** | S-03 |
| 「无需编写任何代码」；CTA「体验 AI 采集流程」 | `AiFlowSection.tsx`；`Home.tsx` | CTA 只 `scrollIntoView('#ai-flow')`；AI 向导要先激活 LLM；Worker 不启则 pending | S-04, S-05 |
| 「注册成功，即可登录开始第一次采集」 | `Register.tsx` `message.success` | 成功主按钮「再注册一家」+「返回官网」；无去登录 | S-05 |
| 专业档 ¥299 / 工单支持；企业档渠道组、私有技能库 | `Pricing.tsx` | 三档 CTA 都进 `/register`；支付/工单/渠道组实现 **0** | S-07 |
| 免费档 5 并发 / 10,000 条 / 20 万 tokens | `Pricing.tsx` / `Register.tsx` | **已对齐** `DEFAULT_QUOTA` | （已兑，记下以免只报缺口） |
| 成员管理 + 用量看板 + BYOK | 专业档卖点 | 页与测例存在 | （已兑部分） |
| 「token 智能调度」 | `README.md` 产品概览 | 官网 0 入口；默认关闭 | S-09 |
| 企业档「中转站渠道组分配」 | `Pricing.tsx` | 全库仅这一句 | S-07, F-R2 |
| 技能广场 + 能力广场 | 导航 | 技能能搜能开正文；能力四 Tab 无搜索无详情无按钮 | S-12, S-15 |
| 能力市场 / 订阅安装（设计 D10/D19） | 设计文档；spec Wave 1 | 无 `POWER_MARKET`、无安装表、无订阅事件 | S-15, S-18 |

---

## 四柱对外叙事错位（总览，不当一条因果）

| 面 | 自称 | 来源 |
|---|---|---|
| 官网 Slogan | 「AI 驱动的智能数据采集系统」；Hero 只讲爬虫 + AI 规划 | `SiteLayout.tsx`；`pages/Home.tsx` |
| README 产品概览 | 智能爬虫 + 大模型管理 + token 智能调度 + 官网与后台 | `README.md` §产品概览（**未列 Power Market**） |
| CONTEXT 词汇 | 能力资产四类 + 中转站 + 租户/配额 | `CONTEXT.md` |
| 本程序 | 采集 + SaaS + 中转站 + Power Market | `state.yaml` `lane_judge.reason` |
| Power Market 设计 | 把能力中心升级为跨宿主商店面 | `power-market-design.md` Overview |
| 冻结 PRD | Wave 0「停止说谎」；首屏那一句 **阻塞于 Q-VOICE** | `spec.md` FR-01 |

官网导航只有：技能广场 / 能力广场 / 定价 / 注册（`NAV_LINKS`）。**中转站、LLM、租户用量、Power Market / 能力市场一词均未出现在官网首页。**

spec 已禁止在 Q-VOICE 关闭前新写并列四柱 Hero。今日页面仍是采集主叙事 + 定价塞进中转/技能库——**冻结 FR 尚未改页面**。

---

## 增长埋点对照（蓝图预测 vs 仓库）

> 时间窗纪律（蓝图）：Asia/Shanghai 业务日；用事件发生时间。判定周期：相关波次对用户可用后 **4 个上海自然周**。无基线 → 目标 = 能报出数字。  
> 本表不是「增长差」，是「现在无法判定」。

### 北极星 / 驱动 / 护栏

| 蓝图项 | 预测口径 | 仓库能否报 | 缺口 |
|---|---|---|---|
| WACT | 上海自然周内 ≥1 次「任务 completed 且 result_count>0」的企业去重；**排除**市场入站候选 | **不能**按事件验收。任务表可弱重构，但无 `task_completed` 事件、无候选排除字段进 FR-15 GWT（QA-02 blocker） | S-18 |
| D1 注册成功数 | `tenant_signup_succeeded` 按次 | 租户行有 `created_at`，**无事件** | S-18 |
| D2 168h 首次登录率 | 注册成功 ∩ `login_succeeded` 能关联到企业 | 登录成功/失败 **不落事实表**（analyst Q9） | S-05, S-18 |
| D3 TTFV | 首次 `task_completed` − 注册成功，中位数 | 两端事件都缺；未出数企业不得进分母 | S-05, S-18 |
| D4 周订阅成功租户 | `market_subscribe_succeeded` | 安装对象不存在，事件不存在 | S-15, S-18 |
| 护栏：跨租户可见 = 0 | 越权审计 + 复现 | 有 `operation_logs`，**无 tenant_id / 会话 / 匿名访客**（analyst Q8） | 转 `/analyst` |
| 护栏：配额拒绝文案 | 抽检 0 次露出 `QUOTA_EXCEEDED` | 用量页 Alert **明文**「429 QUOTA_EXCEEDED」 | S-08；与 FR-12 冲突，转 `/pm` |
| 禁止当 OEC | Hero / 全历史成功率 / 单任务质量 / 扫描成功 / 技能均分 / 渠道 24h | 这些数字 **今天就能看见**，且并排在仪表盘上 | S-03, S-19 |

### 冻结事件名（蓝图 §5）→ 仓库

字段最低集：`occurred_at` + 匿名或租户/用户。失败上报不得挡主路径；验收以查询面为准。

| 事件 | 对应 FR | 仓库命中 |
|---|---|---|
| `official_page_viewed` | FR-15 | 0 |
| `official_cta_clicked`（`register_free` / `pricing_pro` / `pricing_enterprise` / `login` / `browse_market` **分档不得合并**） | FR-15 | 0；三档 CTA 今日都进 `/register`（S-07）——即使埋点落地，当前 UI 也会把付费意向写成免费注册 |
| `tenant_signup_succeeded` | FR-15 | 0 |
| `login_succeeded` / `login_failed` | FR-15 | 0；蓝图含 `login_failed`，GWT-15.1 **未列**（QA-02） |
| `task_run_submitted` | FR-15 | 0（任务行可弱核对） |
| `task_completed`（含 result_count、是否候选入站） | FR-15 | 0；GWT-15.1 **无**候选标记字段（QA-02） |
| `results_exported` | FR-15 | 0；导出无 `record_audit`（analyst Q10） |
| `quota_exceeded`（dimension） | FR-15 | 0；只抛 429（analyst Q11） |
| `market_list_viewed` / `search_submitted` / `detail_viewed` / `subscribe_*` / `uninstalled` / `listing_changed` / `source_sync_completed` | FR-30 | 0；对象未落地 |

漏斗 F1（官网→第一次出数）与 F3（浏览→订阅）：今日除「注册行、任务行」可事后数以外 **全是洞**。不允许把「直接打开后台登录」算进官网漏斗分母（蓝图 §7）——这条现在也无法执行，因为没有 `official_page_viewed`。

**现有计数器为什么不能顶替（S-19）：**

- 成功率 = `completed/(completed+failed)`，**全历史、无 since**；「近 7 日结果」却是 `datetime.now()-6d`——同一仪表盘两个窗（`spider_query_service.py` stats；`Dashboard.tsx`）。
- 用量「本月」token = `datetime.utcnow()` 取 `YYYY-MM`（`tenant_usage.py` L26）；蓝图冻结 **Asia/Shanghai**。跨日界会对不齐。
- `/admin/stats` 随 JWT 的 tenant/platform scope 变总体，API 无口径字段（analyst Q3）。
- `skill_harvester` 写入 `spider_results.source=marketplace`，任务仍进 `spider_tasks`；不排除则会污染 WACT（蓝图已写排除；实现未写）。
- 质量概览只用最近 **1** 条已完成任务（`Dashboard.tsx`）。

**改进方向（观察，不排序）：** ① 先让 FR-15 GWT 字段集盖住 WACT 排除与 `login_failed`（否则四周后仍不能判定，QA-02）② 页面侧把付费 CTA 与免费注册拆开，否则 `official_cta_clicked` 分档会是假的 ③ 在查询面可查之前，不要用 Hero/成功率讲增长故事。交 `/pm`；ops 不选实现。

---

## 信号清单

### S-01 官网只卖「采集」，四柱有三柱在对外面消失

| 项 | 内容 |
|---|---|
| 提及次数 | 文档/页面交叉 ≥4 处口径不一致（官网、README、CONTEXT、state.yaml）；spec 已收成 T-01 |
| 影响用户数 | **未量化**（无访问日志） |
| 行为数据交叉验证 | **未获取**——无 `official_page_viewed` / CTA |
| 实际影响面 | **未量化** |
| 频次 | 每个新访客第一次接触即遇到 |
| 信号强度 | **中**（文案冲突，不是用户抱怨） |
| 用户特征 | 未知；定价页承诺对象是「企业租户」 |
| spec 去向 | T-01 真；FR-01；首屏句阻塞 Q-VOICE |

**原文样本**（未改写）：

> 「AutoAgents 是一个 AI 驱动的爬虫管理平台：粘贴目标链接，AI 自动规划采集方案」——`frontend/official/src/pages/Home.tsx` Hero 正文  
> 「综合数据智能平台：**智能爬虫 + 大模型管理（cc-switch 式）+ new-api token 智能调度 + 官网与后台**」——`README.md` L3  
> 「智能采集 + SaaS 多租户 + 中转站外部契约 + Power Market schema」——`state.yaml` `lane_judge.reason`

**用户提的解法 vs 观察到的问题：**

| 项 | 内容 |
|---|---|
| 用户提的解法 | 无用户原声 |
| 观察到的问题 | 获客页只讲采集；付费页塞进 BYOK / 中转站渠道组 / 私有技能库；README 把中转当第三模块；Power Market 只存在于设计与 PRD |
| 可能的原因/方向 | ① 官网滞后于产品 ② 四柱尚未形成单一价值主张 ③ 有意先用采集获客再交叉销售（无数据可证） |

判断交 `/pm` 做三连问（Q-VOICE）。ops 不选「正确定位」。

---

### S-02 采集导出承诺「CSV / Excel」，实现拒 xlsx、数据中心最多 100 条 CSV

| 项 | 内容 |
|---|---|
| 提及次数 | 对外 1 处 + 实现/测例 3 处互证 |
| 影响用户数 | **未量化** |
| 行为数据交叉验证 | **未获取**——无 `results_exported` |
| 实际影响面 | **未量化** |
| 频次 | 未知 |
| 信号强度 | **强**（承诺与测例可并排核对） |
| spec 去向 | T-02；Wave 0 FR-03 改口或标边界；xlsx **下一轮** |

**原文样本：**

> 「采集结果结构化入库，内置清洗与去重管线，支持 CSV / Excel 一键导出。」——`FeaturesSection.tsx` FEATURES「数据管理」；同卡 points「多格式导出」  
> 「导出：按当前筛选条件拉取最多 100 条生成 CSV 下载」——`frontend/admin/src/pages/Data.tsx` 文件头；`page_size: 100`  
> `if fmt not in ("csv", "json"): raise BusinessException("导出格式仅支持 csv/json")`——`spider_query_service.py`  
> `test_export_bad_format_raises`：`export_results(1, "xlsx")` 期望抛 `BusinessException`  
> `test_export_csv_with_bom`：CSV 以 `\xef\xbb\xbf` 开头，注释「utf-8-sig BOM（Excel 兼容）」

**用户提的解法 vs 观察到的问题：**

| 项 | 内容 |
|---|---|
| 用户提的解法 | 无 |
| 观察到的问题 | 官网把 Excel 当能力卖点；任务导出测例明确拒绝 `xlsx`；数据中心硬顶 100 行且仅 CSV（BOM 让 Excel **能打开 CSV**，不是 xlsx） |
| 可能的原因/方向 | ① 文案把「Excel 能打开 CSV」写成了 Excel 导出 ② 真的缺 xlsx ③ 100 条上限是临时保护 |

---

### S-03 增长数字是示意；真实增长仪表不存在

| 项 | 内容 |
|---|---|
| 提及次数 | Hero 三卡 + 标注 1 处 + 蓝图明文禁止当基线 |
| 影响用户数 | **未量化** |
| 行为数据交叉验证 | **未获取** |
| 实际影响面 | **未量化**（同时暴露埋点缺口） |
| 信号强度 | **强**（作为「我们没有增长数据」的元信号） |
| spec 去向 | T-03；FR-02 删除虚构规模；**首页仍渲染三卡** |

**原文样本：**

> `HERO_STATS`：`128,000+` 累计执行任务 / `12 节点` 分布式 Worker 在线 / `3.2 亿条` 累计采集数据  
> 「* 示意数据，非实时统计」——`Home.tsx`（UX-B7 注释）  
> 「不要当北极星：Hero 数字、全历史成功率…」——`spec.md` §6；`metrics-blueprint.md` §1

**未量化说明：** 无 session、无注册转化、无任务创建率、无 Worker 在线数对外 API。Hero「12 节点」与架构示意 Worker A/B/C 同属装饰。  
**建议：** 不得用 Hero 做基线。FR-02 未落地前，对外材料若引用这些数，视为销售口径（低可靠性）。

---

### S-04 「免代码采集」停在自建规则，没有站点模板商店

| 项 | 内容 |
|---|---|
| 提及次数 | README 1 + 官网 AI 流程 1 + 竞品 F-C1 |
| 影响用户数 | **未量化** |
| 行为数据交叉验证 | **未获取** |
| 信号强度 | **中**（竞品主路径差异；**无**用户求模板原声） |
| spec 去向 | T-04 **伪解法** / 真问题是第一次出数难；模板店 **下一轮**；主路径 Wave 4 stub |

**原文样本：**

> 「免代码采集：通用选择器爬虫（generic）与流程爬虫」——`README.md` §产品概览  
> 「输入目标页面地址，用一句话描述你想提取的字段，无需编写任何代码。」——`AiFlowSection.tsx` 步骤 01  
> 预置爬虫：example / zhihu_feed / dianping_home / openweather + generic / flow_generic——`README.md` 项目结构  
> `skill_harvester` 只采 GitHub contents API 与 awesome README，产出 `source=marketplace` 技能候选——`scrapy/spiders/skill_harvester.py`

**观察到的问题：** 采集侧没有「别人做好的亚马逊/地图 Actor 一键跑」的商店；市场采集爬虫服务于**技能候选**，不服务于采集模板。官网 CTA「体验 AI 采集流程」只滚到 CSS 模拟界面，不创建试用任务。

不要写成「用户都要 Actor 店」。

---

### S-05 激活路径：注册成功仍进不了产品；AI 采集还有 LLM 前置

| 项 | 内容 |
|---|---|
| 提及次数 | 注册成功态 1 + README 启动 1 + AI 前置 1 |
| 影响用户数 | **未量化** |
| 行为数据交叉验证 | **未获取**——D2/D3 所需事件均为 0 |
| 信号强度 | **中**（路径可走查；流失率未知） |
| spec 去向 | T-05 真；FR-04；驱动 D2 预期「断链修好后可从几乎无法发生变为可观测」——**不设百分比** |

**原文样本：**

> 「注册成功，即可登录开始第一次采集」——`Register.tsx` `message.success`  
> 成功态按钮：「再注册一家」「返回官网」——**无「去登录 / 打开后台」**  
> `ADMIN_URL = process.env.REACT_APP_ADMIN_URL || 'http://localhost:9112'`——`SiteLayout.tsx` / `Home.tsx`  
> 「需先在「LLM 配置」激活一个供应商」——`README.md` §第一个采集任务  
> 「Worker 不启动，任务会一直停在 pending」——`README.md` 双进程心智模型

**观察到的问题：** 自助注册创建免费档后，成功页把人送回官网或再开一家企业。后台入口默认 localhost。AI 采集要配 LLM；任务要另开 Worker。官网却说「粘贴链接，交给 AI」。蓝图 D2 把「注册后 168h 登录」当激活诊断——今日登录事件都不落，修好成功页之前此率在查询面上也是空。

---

### S-06 结果出站是平台级 API Key，不是租户自助凭证

| 项 | 内容 |
|---|---|
| 提及次数 | 外部 API 模块 1 + 配置默认空数组 |
| 影响用户数 | **未量化** |
| 信号强度 | **中**（SaaS 数据产品常见期望 vs 当前实现；**无原声**） |
| spec 去向 | T-06 场景推断；Wave 2 stub；不进 Wave 0/1 |

**原文样本：**

> 「外部 API：API Key 数据查询 + Webhook 回调」——`README.md`  
> `EXTERNAL_API.API_KEYS: []`；「默认空数组 = 全部拒绝」——`config/default/external_api.yml`

**观察到的问题：** 定价/SaaS 叙事是租户隔离；拉数钥匙是部署级配置，租户控制台看不见、不能轮换。无用户原声要求「我要自己的 Key」——标为场景推断。

---

### S-07 定价页卖了尚未存在的履约项（支付、工单支持、渠道组、私有技能库）

| 项 | 内容 |
|---|---|
| 提及次数 | 定价 3 档；代码侧支付/工单/渠道组 **仅定价页** |
| 影响用户数 | **未量化** |
| 信号强度 | **强**（对外承诺 vs 仓库可证伪） |
| spec 去向 | T-07；FR-01 / FR-05 不变式；撤 vs 履约 = **Q-PRICE**；支付形态 = **Q-BILL** |

**原文样本：**

> 免费档：5 并发 / 10,000 条 / 20 万 tokens / 平台公共 LLM / 社区支持  
> 专业档：¥299/月 · 50 并发 / 200,000 条 / 500 万 tokens / BYOK / 成员管理 + 用量看板 / **工单支持**；CTA「联系升级」`href: '/register'`  
> 企业档：定制 · **私有技能库（评估开通）** / **中转站渠道组分配** / 专属客户成功；CTA「联系销售」`href: '/register'`  
> 注释：「定价页（SaaS S5-2）：三档**示意**套餐」——`Pricing.tsx`  
> 页眉：「从免费档开始，随时升级；配额可在租户管理台调整」——同文件（运营台手改，不是自助 SKU）

**已兑部分**（避免只报缺口）：

- 免费档数字与 `DEFAULT_QUOTA` 一致（5 / 10000 / 200000）——`quota_service.py`；`test_saas_quota.py` 读默认并发
- BYOK 有测试 `backend/tests/test_saas_byok.py`
- 成员管理页、用量看板存在——`Members.tsx` / `Usage.tsx`

**未兑部分：** 支付闭环、工单系统、渠道组分配、私有技能库、客户成功流程、专业/企业档配额自动套用。升级点击 = 再注册。蓝图：三档曾进同一注册 → CTA 分档不可测（S-18）。

---

### S-08 SaaS 配额是硬闸，但没有「快到上限」的运营动作

| 项 | 内容 |
|---|---|
| 提及次数 | 用量页 1 + 配额服务 1 + 蓝图护栏 1 |
| 信号强度 | **弱**（无超限工单；只有实现与文案） |
| spec 去向 | T-08 弱真；FR-12 文案+埋点；升级支付阻塞 Q-BILL |

**原文样本：**

> 「超配额的操作会被拒绝（429 QUOTA_EXCEEDED），文案含可行动建议」——`Usage.tsx` Alert  
> 三类检查点：任务并发 / 结果存储 / LLM token 月度——`quota_service.py`  
> FR-12：**不出现** `QUOTA_EXCEEDED` / `429` 字样——`spec.md` GWT-12.2

**未量化说明：** 无 `quota_exceeded` 事件。Progress ≥90% 变红，未见升级深链到支付（支付也不存在）。  
**额外观察（非用户原声）：** 用量页把内部错误码展示给租户，与已冻结 FR-12 相反。这是履约裂缝，不是「用户嫌配额严」。

---

### S-09 中转站在官网为零曝光；默认关闭；管控面偏运维

| 项 | 内容 |
|---|---|
| 提及次数 | README 定位 1 + deploy README 1 + 配置默认 false + 官网 0 |
| 信号强度 | **中** |
| spec 去向 | T-09；曝光取决于 **Q-RELAY**；Wave 0 先删空头 |

**原文样本：**

> 「token 调度模块是 new-api 实例的**外挂巡检器**（额度熔断 + 真伪探针 + 只读总览），请求转发/计费由 new-api 本体承担」——`README.md`  
> `NEWAPI.ENABLED / SCHEDULER_ENABLED / PROBE_ENABLED` 全部 **false**——`config/default/newapi.yml`  
> 文件头：「约定：全只读无写操作」——`NewApiOps.tsx`（同页另有渠道额度配置 Modal 与 `setChannelConfig`，与「纯只读」注释不完全一致，**以代码为准**）

**观察到的问题：** 增长故事若含「中转站」，用户在官网上找不到入口与定价动作。新部署默认没有中转能力。Q-RELAY 未拍板前，ops 不建议把探针当获客主句——也没有数据证明有人在找探针。

---

### S-10 两本账：租户 SaaS 配额 vs new-api 令牌额度，对外未解释

| 项 | 内容 |
|---|---|
| 提及次数 | 部署文档「双层熔断」1 + CONTEXT 配额定义 1 |
| 信号强度 | **中** |
| spec 去向 | T-10；Wave 0 不在定价里混写；Wave 3 stub |

**原文样本：**

> 「双层熔断：本项目 `MAX_TOKENS_BUDGET` + new-api 令牌限额」——`deploy/newapi/README.md` §5.1  
> 「配额：tenants.quota 三类：任务并发 / 结果存储 / LLM token 月度」——`CONTEXT.md`  
> 企业档卖点「中转站渠道组分配」——`Pricing.tsx`（实现未见）

**观察到的问题：** 若真付 ¥299，付的是并发/存储/tokens，**不是** new-api 余额。渠道组、分组倍率、令牌白名单活在 new-api 后台。两套租户模型并立。

---

### S-11 AGPLv3 与「对外 SaaS / 收费分发」是运营约束，不是需求

| 项 | 内容 |
|---|---|
| 类型 | **约束**（给 `/pm`，不进 RICE 当用户信号） |
| 来源 | `deploy/newapi/README.md` §七 |
| spec 去向 | T-11；审查 QA-08：该约束写成开放问题却不在 §9.1 必答表 |

**原文样本：**

> 「对外商用（SaaS/收费分发）：若修改了 new-api 源码或形成衍生作品，需按 AGPLv3 开源衍生代码」  
> 「本项目当前仅容器化集成，**未修改上游源码**，无衍生义务。」  
> 「不做『套壳倒卖』：若对外收费，确认合规边界，做好实名、审计与投诉通道。」

日历压力不是信号。投诉通道在定价「工单支持」里被暗示，系统不存在（S-07）。是否增 Q-AGPL 交 `/pm`，ops 不代列进必答。

---

### S-12 技能广场与能力广场双入口，能力广场比技能广场更「空」

| 项 | 内容 |
|---|---|
| 提及次数 | 导航 2 项 + 两页实现差 + 设计 D19 |
| 信号强度 | **强**（页面可点、差异可复核） |
| spec 去向 | T-12；Wave 1 FR-17（导航只留「能力市场」） |

**原文样本：**

> 导航「技能广场」`/skills` + 「能力广场」`/capabilities`——`SiteLayout.tsx`  
> 能力广场：四 Tab 卡片网格，无搜索、无详情、无来源/许可证/验证徽章、无订阅按钮——`Capabilities.tsx` 全文  
> 设计 D19：「`/skills` 并入 `/capabilities?type=skill`；导航只留『能力市场』」——`power-market-design.md`  
> 产品名对用户：**能力市场**（中文）。英文 Power Market 不作为导航名。——`spec.md` Wave 1

**观察到的问题：** 用户会看到两个广场。技能侧能搜能打开正文；能力侧只能扫卡片。设计要把它们收成市场，**当前分支尚未做**。

---

### S-13 公开能力列表丢掉 `recommended`；与技能公开闸门不一致

| 项 | 内容 |
|---|---|
| 提及次数 | 实现 1 + 两侧测例 + 设计 Risks |
| 信号强度 | **中**（行为差可测；`recommended` 资产条数 **未量化**） |
| spec 去向 | T-13；Wave 1 可见性闸 FR-18；qa 点名旧用例会红 |

**原文样本：**

> 技能公开：`PUBLISHED_STATUSES = ("stable", "recommended")`——`public_skills.py`  
> `test_public_list_only_published`：`names == {"pub-stable", "pub-rec"}`  
> 能力公开：`svc.list_assets(..., status="stable")`——`public_list_capabilities`  
> `test_public_capabilities_only_stable`：只断言 stable；experimental 不外泄；**夹具不含 recommended**  
> 设计：「公开能力广场今日漏掉 `recommended`」列入 Risks  

首页精选含 `status === 'recommended'`（`SkillsSection.tsx`），走的是 `/public/skills` 不是 `/public/capabilities`。两套公开面。

---

### S-14 第三方能力进目录的路：本机 symlink 森林 + GitHub 候选；Kimi 主市场未接

| 项 | 内容 |
|---|---|
| 提及次数 | 设计痛点 5 条 + README/AGENTS 插件表 + capability-library 适配表 |
| 信号强度 | **强**（设计已用本机盘点数字；那是操作者机器，不是市场规模） |
| spec 去向 | T-14；Wave 1 按 D1–D4；本机盘点 **一次性**，不外推 Reach |

**原文样本**（设计文档，操作者本机 2026-09-07）：

> `~/.zcode/local-plugins` 6 个真实插件；跨插件 SKILL.md 父目录名约 94，其中 **51 个重名**  
> Kimi 托管插件 16 个，约 12×`UNLICENSED`、3×`LicenseRef-Moonshot-AI-Skill`、1×`MIT`  
> 扫描器 `_MANIFEST_CANDIDATES` 不含 `kimi.plugin.json`，「会全部漏掉」

仓库现状：

> Grok enabled：`sdlc-workflow` / `superpowers` / `mattpocock-skills` / `drama-skills` / `oh-story`（无 `dev-team`）——`.grok/config.toml`  
> 「Kimi / workbuddy / zcode / traework / Qoder | 未知…」——`capability-library/README.md` §各工具适配情况（**文档漂移**：同表 Grok 行已写 symlink；Kimi/zcode 仍「未知」，与 `AGENTS.md` / 设计本机盘点冲突）

设计 Non-Goals（不是需求，是增长通道上限）：

> 「公开第三方开发者门户、计费、分成。」——`power-market-design.md` Non-Goals

---

### S-15 「订阅/安装」被设计成一期，当前商店面零动作

| 项 | 内容 |
|---|---|
| 提及次数 | 设计 D10 / D17 / 官网现况表 / spec FR-20 |
| 信号强度 | **中**（有产品决议，**无**「我想安装」原声） |
| spec 去向 | T-15；Wave 1；不得写成用户强烈要求 |

**原文样本：**

> 官网现况「无租户动作」→ 目标「登录租户：订阅/安装 → POST `/api/v1/tenants/me/installs`」——设计 §8  
> D10：一期必须做 `capability_installs`——操作者 2026-09-07  
> 现 `Capabilities.tsx`：卡片不可点进详情，无按钮  
> 本机复跑：`capability_installs` / `listing_state` / `tenants/me/installs` **0 命中**

**不要写成「用户强烈要求安装按钮」。** 写成：设计把租户安装当市场成立条件；当前公开面是浏览目录。D4 订阅成功租户数在 Wave 1 可用前不可测。

---

### S-16 管理端能力中心仍是「扫描 + 验证」，文案还是「验证后方可分发」

| 项 | 内容 |
|---|---|
| 提及次数 | Admin 插件 Tab + 菜单名 + 设计 §7 |
| 信号强度 | **中** |
| spec 去向 | T-16；Wave 1 治理台 |

**原文样本：**

> 「插件经 MCP 验证后方可分发（ADR-0001）」——`frontend/admin/src/pages/Capabilities.tsx` PluginTab  
> 设计：改为「能力市场」；验证按钮今日未走 `usePermission`（R5 缺口）——`power-market-design.md` §7  

候选审核文案：「来源：skill_harvester 采集，source=marketplace」。与宿主官方市场（Claude Discover / Kimi Official / Grok `/marketplace`）不是同一类「市场」。

---

### S-17 评分/治理已有，公开信任信号不足

| 项 | 内容 |
|---|---|
| 提及次数 | CONTEXT 资产评分 + 公开白名单字段 |
| 信号强度 | **弱**（无用户问「这插件安全吗」的原声；竞品把信任当安装门槛） |
| spec 去向 | T-17 弱；Wave 1 展示来源/许可/预告；不承诺平台担保 |

**原文样本：**

> 四维 rubric + 人工终评 + tier S/A/B/C——`CONTEXT.md`  
> 公开能力字段：`name, title, description, category, tier, score, status, source_url, source_author, updated_at, asset_type`——`_PUBLIC_ASSET_FIELDS`  
> **无** license / health_status / host_compat / listing_state  
> Grok 文档：第三方插件由作者负责，xAI 不担保——[xai-org/plugin-marketplace README](https://github.com/xai-org/plugin-marketplace)（官方，高）

---

### S-18 度量蓝图事件名已冻结，查询面为零（增长元信号）

| 项 | 内容 |
|---|---|
| 提及次数 | 蓝图事件表 16 行 + 本机 grep 0 + 审查 QA-02 |
| 影响用户数 | **未量化**（且当前无法量化任何漏斗） |
| 行为数据交叉验证 | **不适用**——要验证的就是「没有行为数据」 |
| 信号强度 | **强**（内部契约 vs 仓库；不依赖用户口述） |
| 用户特征 | 无；这是运营/产品自己不能判定成败 |
| spec 去向 | T-23；FR-15 / FR-16 / FR-30；QA-02 **仍 open** |

**原文样本：**

> 「本轮成功 = 能判定。」——`metrics-blueprint.md` 文首  
> 「四周结束时必须能报出『这四周每周 WACT=？』；报不出 = 埋点 FR 失败」——蓝图 §2  
> GWT-15.1 字段无候选入站标记、无 `login_failed`——`05-review/findings.md` QA-02  
> `fresh-context` result: fail；blocker: 2（QA-01 已修，QA-02 仍 open）——`state.yaml`

**用户提的解法 vs 观察到的问题：**

| 项 | 内容 |
|---|---|
| 用户提的解法 | 无（用户看不见埋点契约） |
| 观察到的问题 | 预测已经写细到事件名，履约未开始；且冻结 GWT 与北极星排除条件对不齐，即使仓促埋点也会「报不出合格 WACT」 |
| 可能的原因/方向 | ① 定义帽审查未关就进实现 ② 用任务表冒充事件（蓝图禁止验收这么做） ③ 先修 GWT 再谈四周窗 |

---

### S-19 现有后台数字不能当驱动指标（窗口 / 时区 / 总体混用）

| 项 | 内容 |
|---|---|
| 提及次数 | analyst 诊断 Q1–Q5、Q9–Q11；代码 3 处 |
| 信号强度 | **中**（盘点可复核；无用户被数字误导的原声） |
| spec 去向 | FR-16 时区口径；FR-02 删 Hero；FR-11 候选不计入租户成果 |

**原文样本：**

> 成功率无 `since`；近 7 日结果用 `datetime.now() - timedelta(days=6)`——`spider_query_service.py`  
> `year_month = datetime.utcnow().strftime("%Y-%m")`——`tenant_usage.py` L26  
> 「时区：**Asia/Shanghai 业务日**」——`metrics-blueprint.md` §1  
> `HERO_STATS` 写死且标注示意——`Home.tsx`

**观察到的问题：** 值班能看见「成功率 / 近 7 日 / 本月 tokens」，读者会以为那是增长仪表。蓝图已点名这些 **禁止当 OEC**。改进：对外与对内运营材料分开；对内卡片标明窗口与总体（平台合计 vs 本企业）——FR-16 已写，未落地。

---

## 已转出的非需求项

| 项 | 类型 | 转给谁 | 时间 |
|---|---|---|---|
| 公开 `/public/capabilities` 只滤 `stable`、丢掉 `recommended`（S-13） | 行为不一致 / 可能缺陷 | `/backend`（设计已视为修复项；Wave 1 闸） | 2026-09-07 |
| Admin 插件「验证」按钮未走 `usePermission` | 权限红线 R5 | `/frontend` + `/backend` | 设计 §7 |
| `capability-library/README.md` 仍写 Kimi/zcode「未知」，与 `AGENTS.md` / 设计本机盘点冲突 | 文档漂移 | 文档维护（非产品需求） | 2026-09-07 |
| 官网 Hero 示意数据绝对值极大（3.2 亿条） | 品牌/合规风险 | `/pm` 约束（FR-02），不是功能 | 2026-09-07 |
| new-api AGPLv3 对外商用边界 | 法律约束 | `/pm` + 法务；审查建议 Q-AGPL | `deploy/newapi/README.md` §七 |
| `NEWAPI.*.ENABLED=false` 默认 | 发布开关 | `/sre` 配置，不是用户需求 | `config/default/newapi.yml` |
| 任务一直 pending（Worker 未启） | 运维 FAQ | `/sre` 已有文档 | `README.md` FAQ |
| 数据中心导出顶 100 条 | 可能是保护上限也可能是缺陷 | `/backend` 核实后决定是否当故障 | `Data.tsx` |
| 用量页 Alert 展示 `429 QUOTA_EXCEEDED` | 与冻结 FR-12 冲突 | `/pm`（GWT）+ `/frontend` | `Usage.tsx` |
| FR-15 GWT 缺 WACT 排除字段 / `login_failed` | 度量契约裂口（blocker） | `/pm` 修 findings QA-02 | `05-review/findings.md` |
| 租户 admin 可改平台渠道 / 目录验证 | 泄漏 | Wave 0 FR-06/07；非增长需求 | spec T-18 |
| 明文上游 Key 被 git 跟踪 | 泄漏 | Wave 0 FR-14；`/sre` | spec T-22 |
| `NewApiOps.tsx`「全只读」注释 vs 渠道配置写入口 | 文档/实现不一致 | `/frontend` | 本文件 S-09 |

**故障不走信号池。** S-13 若被判定为 bug，从本池移除。QA-02 未关不得宣称「四周后能判定」。

---

## 本期汇总

| 信号强度 | 数量 | 编号 |
|---|---|---|
| 强 | 8 | S-02, S-03, S-07, S-12, S-14, S-18 |
| 中 | 10 | S-01, S-04, S-05, S-06, S-09, S-10, S-13, S-15, S-16, S-19 |
| 弱 | 2 | S-08, S-17 |
| 约束（非需求） | 1 | S-11 |
| 已转出 | 13 | 上表 |

初稿强信号 6 条；本期因度量蓝图落地，把「没有增长数据」拆成 S-03（示意数字）+ S-18（冻结事件零落点）+ S-19（旧计数器不可顶替）。**不是用户突然变多，是内部契约变清楚。**

## 与上期对比

| 主题 | 上期（同日初稿） | 本期 | 变化 | 说明 |
|---|---|---|---|---|
| 客户工单 / UV | 0 / 未获取 | 0 / 未获取 | — | 无使用量，提及量不能归一化 |
| P0 假设 | 无 | spec + metrics 已冻结 | 新增对照物 | 仍无上线后实际值 |
| 承诺/履约代码事实 | S-01…S-17 | 复跑未变 | — | Hero / 定价 / xlsx / 双广场仍在 |
| 增长可判定性 | 「没有埋点」 | 事件名已冻结且 0 命中；QA-02 指出 GWT 仍盖不住 WACT | ↑ 作为元信号变强 | 不是市场变差 |
| 开放问题 | ops 自列 7 问 | 与 spec Q-VOICE…Q-LLM 对齐 | 收口 | ops 仍不代答 |

---

## 竞品拆解

> 每个功能必须给出三层结论之一：借鉴 / 回避 / 差异化。「它有我们没有」不是分析。  
> 可靠性：官方文档 **高**；第三方评测 **中**；销售材料 **低**（定价页自己也是示意）。  
> **未亲自付费试用** Claude/Kimi/Grok 市场与 Apify——结论不得写成「我们用过」。  
> spec §1「未采纳的解法」已吸收 F-01 / F-02 / F-05 / F-06 / F-R1。本表仍给信号，**不排序**。

分层：

| 层 | 对象 | 与我们重叠 | 依据 |
|---|---|---|---|
| 直接（采集 SaaS） | Apify、Octoparse 类无代码云采集 | 任务、调度、导出、API | 官网/README 主叙事就是采集平台 |
| 直接（中转） | new-api 本体（QuantumNous） | 令牌/渠道/计费 | 我们是外挂，不是替代 |
| 直接（能力分发，未来） | Claude / Kimi / Grok **官方市场** | 插件/技能发现与安装 | Power Market 要把它们当**源**而不是当宿主 UI |
| 间接 | Firecrawl、Bright Data、Zyte | LLM 就绪抓取 / 代理网 / Scrapy 云 | 评测文（中） |
| 基准 | 各宿主 Discover / Official / `/marketplace` | 商店面信息架构 | 官方文档（高） |

---

### 基本信息 · 宿主插件市场（Power Market 柱）

| 项 | Claude | Kimi | Grok |
|---|---|---|---|
| 定位 | 宿主内市场：`/plugin` Discover；官方 `claude-plugins-official` + 社区 marketplace | 宿主内：Official / Curated / Custom；桌面 Plugin Center；金融数据类官方插件 | Grok Build 内 `/marketplace`；目录仓是 **index**（pin SHA） |
| 目标用户 | Claude Code / Claude 付费档知识工作者 | Kimi Code / Kimi Work 用户；分国内/海外 | SuperGrok / X Premium Plus（第三方报道，中） |
| 与我们重叠 | 技能/插件/agents/hooks/MCP 包格式相近 | `kimi.plugin.json` 不同清单；superpowers 已在其 curated | `.grok-plugin`；本仓库已 symlink 启用 5 个插件 |
| 我们的信息获取 | [code.claude.com/docs/en/discover-plugins](https://code.claude.com/docs/en/discover-plugins)（高） | [kimi.ai/help/features/plugins](https://www.kimi.ai/help/features/plugins) + [kimi-code plugins docs](https://moonshotai.github.io/kimi-code/en/customization/plugins.html)（高）；本机 16 托管包（设计，高，单机） | [xai-org/plugin-marketplace](https://github.com/xai-org/plugin-marketplace) + [x.ai/docs/build/features/skills-plugins-marketplaces](https://x.ai/docs/build/features/skills-plugins-marketplaces)（高） |

---

### F-01 宿主内一键安装——结论：**回避当主路径；借鉴「安装是独立动作」**

| 项 | 内容 |
|---|---|
| 他们怎么做的 | 安装发生在**已经打开的宿主**里。Claude：`/plugin install github@claude-plugins-official`。Kimi：市场点安装或 `/plugins install <url>`。Grok：`/marketplace` 或 CLI，`--trust` 强制确认，远程源 pin 40 位 SHA。 |
| 他们的场景 | 用户已付宿主订阅，要的是「让当前 Agent 立刻多一个技能」。 |
| 我们的场景 | 平台要索引**多个**宿主的包，治理后再投影；设计 D21：**不写** `~/.zcode/cli/config.json`。 |
| 场景差异 | 他们是 runtime；我们是 catalog。在网页商店里模仿 `/plugin install` 装不到用户的 Claude。 |
| **借鉴什么** | listed ≠ installed ≠ trusted；安装确认（Grok `--trust`）；目录是指针不是 vendor。 |
| **不借鉴什么** | 把网页做成第四个宿主市场去抢 `/plugin` 入口；平台代改宿主 config。 |
| 对应信号 | S-15, S-14 |
| 来源 | 官方文档（高）；`power-market-design.md` D8/D21/PR8 |
| 复审条件 | 若出现「平台自己的执行引擎」把专家团跑在站内（CONTEXT：执行引擎二期），再评估站内 enable。 |

---

### F-02 官方 / 社区 / 第三方分层目录——结论：**借鉴分层语义；回避做「官方认证替代 Anthropic」**

| 项 | 内容 |
|---|---|
| 他们怎么做的 | Claude：official vs community vs 自建 git marketplace。Kimi：Official vs Curated vs Custom。Grok：first-party `plugins/` vs third-party `external_plugins/` + PR 进 index。 |
| 我们的场景 | 源是操作者本机 zcode/kimi + git；上架闸是 `listing_state` + 许可黑名单 + 人工。无开发者门户。 |
| **借鉴什么** | 质量层（status/verify）与产品层（listed/unlisted/coming_soon）分开——设计 D6 已选；公开卡片要能看出「第一方 / 已验证第三方 / 预告」。 |
| **不借鉴什么** | 开放 PR 进我们 git 当货架；承诺「官方认证」却没有同等审查产能。 |
| 对应信号 | S-14, S-16, S-17 |
| 来源 | 官方文档（高）；设计 D6/D7/Non-Goals |

---

### F-03 跨宿主同一技能名——结论：**差异化（治理索引）；回避静默改名当商店品牌**

| 项 | 内容 |
|---|---|
| 他们怎么做的 | 各市场用自己的 id。superpowers 同时出现在 Kimi curated 与 zcode/Grok 本地。 |
| 同一个用户问题 | 「我想装 code-review」——跨宿主会撞短名（设计本机 51 个）。 |
| **我们的差异化解法（已在设计，非本文件发明）** | catalog 全局 slug + `{plugin}__{local}` + 搜索走 `origin_local_name` + 人工 vanity alias。 |
| 为什么我们能、他们不能 | 他们各自只需自己的命名空间；我们若当**跨宿主索引**就必须处理碰撞。 |
| 代价 | slug 难看；用户搜短名要靠搜索字段；dev-team 禁止独立上架（D20）。 |
| 对应信号 | S-14 |
| 来源 | `power-market-design.md` D3/D18/D20（高，本机事实） |

---

### F-04 Kimi 金融/数据官方插件 + 地区分发——结论：**回避当可运行货上架到 Grok/ZCode；借鉴「host_compat + 许可闸」**

| 项 | 内容 |
|---|---|
| 他们怎么做的 | Kimi 官方插件含 Wind / S&P / 浏览器 WebBridge；市场按国内/海外分区；多数桌面托管包 UNLICENSED 或 Moonshot LicenseRef（设计抽样 16 个）。 |
| 我们的场景 | 设计：`host_compat=["kimi"]`，许可黑名单默认藏 UNLICENSED。 |
| **为什么回避** | ① 无 Kimi `agent-gw` 则包在他宿主跑不起来 ② 专有许可公开分发有合规风险 ③ 金融数据插件是 Kimi 的护城河，不是我们的供给 |
| 替代方案 | 索引 + 安装说明，不假装可 enable-host |
| 复审条件 | 若拿到可再分发许可，或用户明确只要「Kimi 桌面安装说明」的流量数据 |
| 对应信号 | S-14 |
| 来源 | 设计本机许可抽样（高，n=16）；Kimi Help Center（高） |

---

### F-05 供给链：SHA pin / 内容哈希 / 不担保声明——结论：**借鉴信任 UI 与 pin；回避「平台担保第三方 MCP」**

| 项 | 内容 |
|---|---|
| 他们怎么做的 | Grok：远程源 pin commit SHA。Claude official：「Anthropic does not control MCP servers」。 |
| 我们的场景 | 设计 `content_hash` + MCP verify + listed≠trusted。Admin 现文案「验证后方可分发」比竞品免责**更重**。 |
| **借鉴什么** | 公开页免责 + 哈希/版本可见；enable 与上架分离。 |
| **不借鉴什么** | 用「平台已验证」暗示法律担保。 |
| 对应信号 | S-16, S-17 |
| 来源 | xAI marketplace README（高）；Claude plugins-official README（高）；设计 Security |

---

### F-06 开发者门户与分成——结论：**回避一期；记下增长通道缺口**

| 项 | 内容 |
|---|---|
| 他们怎么做的 | Claude 可自建 marketplace git；Kimi 有提交表与 Plugin Builder；Grok 用 PR 进 index。第三方目录自称月访（**销售口径，低**，不当市场规模）。 |
| 我们的场景 | Non-Goals：无门户、无计费、无分成。入站是本机源 + `skill_harvester` GitHub。 |
| **为什么回避** | 设计已否；审查产能、许可、MCP 执行面都未准备好。 |
| 替代方案 | 人工候选闸门 + 源注册表（设计） |
| 复审条件 | 若商店面出现稳定安装量（当前安装量=0，未上线） |
| 对应信号 | S-14, S-15 |
| 来源 | 设计 Non-Goals（高）；Kimi 提交指南（高） |

---

### 基本信息 · 通用采集 SaaS（采集柱）

| 项 | 内容 | 来源可靠性 |
|---|---|---|
| Apify | Actor 商店（评测口径从「数千」到「数万」不等，**数字不互证，不当事实**）+ 云运行 + API + 用量计费 | 官方定位经第三方评测转述（中） |
| Octoparse 类 | 点选无代码 + 模板站点 + 云任务 + 席位套餐 | 评测（中） |
| 我们 | Scrapy 集群 + 选择器/流程 + AI 规划试采 + 租户配额；**无站点 Actor 店** | 本仓库（高） |
| 重叠 | 调度、导出、重试、API 出数 | — |
| 未试用 | 未登录 Apify/Octoparse 付费档 | 明确 |

---

### F-C1 预置刮削器商店——结论：**借鉴「可运行模板是获客钩子」；回避堆 10k 站点覆盖**

| 项 | 内容 |
|---|---|
| 他们怎么做的 | 用户为「亚马逊/地图/某站」而来，跑别人维护的 Actor，按计算单元付费。 |
| 我们的场景 | 用户被要求填 CSS/XPath 或等 AI 规划；预置爬虫是 example/zhihu/dianping/openweather。 |
| **借鉴什么** | 把「第一次成功出数」当作激活事件（与 WACT 默认核心动作一致）；模板哪怕很少，也要可发现。 |
| **不借鉴什么** | 用覆盖站点数量当 KPI；建设住宅代理网。 |
| 对应信号 | S-04, S-05 |
| 来源 | 评测综述（中）；本仓库爬虫列表（高） |

---

### F-C2 自助计费与用量即套餐——结论：**借鉴计量语言；回避未履约先标价**

| 项 | 内容 |
|---|---|
| 他们怎么做的 | 免费额度 → 信用卡升级；并发/计算可见。 |
| 我们的场景 | 配额三件套已实现；定价 ¥299 是示意；升级按钮去注册。 |
| **借鉴什么** | 免费档数字与真实 `DEFAULT_QUOTA` 对齐（已经对齐，应保持）。 |
| **不借鉴什么** | 在无支付、无工单、无渠道组的情况下继续把它们印在定价卡上（S-07）。 |
| 对应信号 | S-07, S-08 |
| 来源 | 定价页（本仓库，高）；评测价格（中，易过期） |

---

### F-C3 AI 规划采集 vs Firecrawl「LLM 就绪网页」——结论：**差异化叙事可用；未验证留存**

| 项 | 内容 |
|---|---|
| 他们怎么做的 | Firecrawl 等卖 Markdown/JSON API 给 RAG，不是「给你一个爬虫管理后台」。 |
| 同一个用户问题 | 非工程师想从 URL 拿到结构数据。 |
| **我们能不同的点** | 已有：试采、质量分、任务状态机、租户隔离、失败重试——偏「运营采集」而非「单次抽页」。 |
| 为什么我们能、他们不能 | 我们已有 Scrapy 工人与结果表；他们优化的是 API 延迟与 md 质量。 |
| 代价 | 激活路径长（S-05）；官网把差异讲成「粘贴链接」，更像 Firecrawl 而不是「管理全链路」。 |
| 对应信号 | S-01, S-05 |
| 来源 | 官网文案（高）；Firecrawl 定位来自评测（中） |

---

### F-C4 代理/反爬基础设施——结论：**回避当对外卖点，直到有能力数字**

| 项 | 内容 |
|---|---|
| 他们怎么做的 | Bright Data / ScraperAPI 卖成功率和住宅 IP。 |
| 我们的场景 | 中间件：UA 轮换、代理评分、账号会话、Playwright——`README.md` 反爬列表。 |
| **为什么回避** | 官网未展示成功率/解锁率；Hero 节点数是示意。拿基础设施硬碰没有证据。 |
| 替代方案 | 继续当采集可靠性的内部能力；对外先兑现导出与激活（S-02, S-05） |
| 复审条件 | 有生产成功率、代理池规模、对比探针 |
| 来源 | README（高）；竞品评测（中） |

---

### 基本信息 · new-api 本体（中转柱）

| 项 | 内容 | 来源 |
|---|---|---|
| 定位 | 多协议网关：令牌、分组、倍率、渠道故障转移 | `deploy/newapi/README.md`（高） |
| 与我们重叠 | 我们**刻意不重叠**转发面；重叠在「渠道健康」 | 同文档职责边界 |
| 我们多出来的 | 额度窗口调度、10 维真伪探针、事件时间线 | README + `NewApiOps.tsx` |

---

### F-R1 网关控制台 vs 外挂巡检——结论：**差异化（探针/熔断）；回避再做一套令牌收银台**

| 项 | 内容 |
|---|---|
| 他们怎么做的 | 用户在 :3000 管 Key、余额、模型白名单。 |
| 我们的场景 | 9112「中转站管控」看健康与调度。 |
| **差异化** | 真伪探针（降智/套壳）是 new-api 没有、我们文档当作卖点的东西。 |
| 为什么我们能、他们不能 | 探针是行为指纹，不是网关核心路径；放在外挂避免改 AGPL 源码（S-11）。 |
| **不借鉴什么** | 在 auto_agents 里再做一遍充值/令牌签发（会与 new-api 双收银台）。 |
| 对应信号 | S-09, S-10, S-11 |
| 来源 | deploy README §1.2 / §八（高） |

---

### F-R2 「渠道组分配」当企业档卖点——结论：**回避对外承诺，直到有映射实现**

全库「渠道组」只出现在 `Pricing.tsx`。new-api 自己有分组（deploy README §三②）。  
**回避：** 把尚未接线的企业档特性印出去。  
**替代：** 定价只写已有能力（配额、BYOK、成员、探针只读——且探针默认关，不宜当「当前可买」）。  
**复审：** 若 `/pm` 确认要卖渠道组（Q-RELAY），那是新需求，不是现成功能。  
对应 S-07, S-10。

---

## 汇总（竞品 → 信号；**无优先级列**）

| 编号 | 主题 | 结论 | 对应信号 |
|---|---|---|---|
| F-01 | 宿主内一键安装 | 回避当主路径；借鉴安装独立于上架 | S-15, S-14 |
| F-02 | 官方/社区分层 | 借鉴分层语义；回避冒充官方认证 | S-14, S-16, S-17 |
| F-03 | 跨宿主重名 | 差异化（索引+别名） | S-14 |
| F-04 | Kimi 专有/金融包 | 回避可运行上架；借鉴 host_compat | S-14 |
| F-05 | SHA/免责/验证 | 借鉴信任展示；回避法律担保 | S-16, S-17 |
| F-06 | 开发者门户分成 | 回避一期 | S-14, S-15 |
| F-C1 | Actor 模板店 | 借鉴激活钩子；回避覆盖竞赛 | S-04, S-05 |
| F-C2 | 自助计费 | 借鉴计量诚实；回避空头标价 | S-07, S-08 |
| F-C3 | AI 抽页 vs 采集运营 | 差异化未讲清 | S-01, S-05 |
| F-C4 | 代理网 | 回避当卖点 | S-03 |
| F-R1 | 探针外挂 | 差异化 | S-09, S-10 |
| F-R2 | 渠道组卖点 | 回避空头 | S-07 |

决策权在 `/pm`。上表不是 backlog 顺序。spec 已否决：第四宿主市场、开发者门户/分成、Hero 大数当增长、双收银台、把验证写成法律担保。

---

## 我们已有、竞品不一定有的（避免只看差距）

| 我们有他们没有的 | 说明 | 是否该强化（观察，非优先级） |
|---|---|---|
| 渠道真伪探针 + 额度熔断外挂 | 相对 new-api 本体、相对采集 SaaS | 官网完全没讲；默认关——强化与否交 `/pm`（Q-RELAY） |
| AI 规划 → 试采 → 注册为 flow_generic | 相对纯 Actor 店、相对纯点选 | 官网有模拟 UI，无试用闭环 |
| 技能四维人工评分 + 候选人工闸 | 相对 Grok「index + SHA、不审查内容」 | 公开面几乎不展示 |
| 多租户配额三件套 + 成员 + 用量看板 | 相对「只有后台的爬虫项目」 | 定价已写，支付未接；用量页还把内部错误码亮给用户 |
| 跨宿主适配器方向（设计） | Claude/Kimi/Grok 各自只顾自己 | 实现未进分支 |
| 冻结的诚实履约 FR（Wave 0） | 竞品少把「停止说谎」写成程序第一波 | **页面尚未改**；这是内部承诺，访客看不到 |

---

## 观察到的他们的问题（公开渠道，中可靠性）

| 问题 | 来源 | 我们的机会（观察） |
|---|---|---|
| 第三方插件安全免责、用户必须自己信 | Claude/Grok 官方 README（高） | 我们已有 MCP verify 与评分；公开面没把「验过/没验过」当信任商品 |
| 采集 SaaS 评测互相打架的 Actor 数量、价格易过期 | 第三方评测（中） | 不要用「最大市场」语言；用可核对的能力 |
| Octoparse 类：点选难搞 JS、API 锁高档（评测转述） | 评测（中） | 我们本就 API/Scrapy 向；但官网在学无代码语言 |
| Kimi 大量 UNLICENSED | 设计本机抽样 n=16（高，样本小） | 许可闸是差异化，不是障碍文案 |

---

## 四柱缺口对照（给 `/pm` 的一页纸，仍不排序）

| 柱 | 对外是否存在 | 仓库是否可演示 | 蓝图能否判定 | 最大证据化缺口 |
|---|---|---|---|---|
| 智能采集 | 官网主叙事 | 是（任务/AI/结果） | WACT 事件缺；任务表可弱重构但不能验收 | Excel vs 拒 xlsx；激活链长；无模板店；Hero 示意 |
| SaaS | 定价+注册 | 部分（配额/成员/用量/注册） | 注册事件缺；登录事件缺；CTA 三档并成注册 | 支付/工单/升级 CTA 空转；套餐 SKU 不是系统对象 |
| 中转站 | 官网无 | 默认关；后台有只读+配置写入口 | 渠道 24h **禁止当 OEC** | 获客面为零；双账本未解释；渠道组空头 |
| Power Market | 两个「广场」 | P6 目录，非市场 | 订阅漏斗对象与事件均为 0 | 无搜索详情（能力页）、无安装、无 Kimi、无 `POWER_MARKET`、文档漂移 |

---

## 缺失证据清单（请 `/pm` / `/analyst` 不要把下面当成已验证需求）

1. 任意生产环境 UV / 注册数 / 付费转化 / 流失原因  
2. 租户工单、访谈、NPS  
3. 导出、安装、升级、探针查看的行为埋点（事件名已冻结，查询面未建）  
4. 亲自试用 Apify / Octoparse / Claude Discover / Kimi Plugin Center / Grok `/marketplace` 的操作记录  
5. 技能广场 vs 能力广场的点击占比  
6. `recommended` 资产实际条数（S-13 影响面）  
7. 超限 429 是否真实发生过  
8. new-api 是否已有外部租户在用（`ENABLED=false` 暗示可能没有）  
9. QA-02 关闭后的 FR-15 字段集是否真能支撑 WACT 排除候选  

没有这些，**不能**写「用户都要 Power Market」或「采集 SaaS 必须做 Actor 店」。只能写：对外承诺、内部设计、冻结蓝图、竞品主路径之间的空洞。

---

## open_questions

ops **不答**。下列 1–6 与 `spec.md` §9.1 同编号语义；7–8 是运营收集手段，仍交 `/pm`。

1. **Q-VOICE** 对外第一句话到底是采集、四柱平台，还是「给 Agent 用的能力市场」？未关前不得新写并列四柱 Hero；北极星核心动作是否改「订阅成功」也绑在这里。  
2. **Q-PRICE** 定价空头（工单支持 / 渠道组 / 私有技能库 / ¥299）是先撤文案还是先履约？  
3. **Q-RELAY** 中转站是独立 SKU、采集附加、还是仅内部成本控制？官网零入口是否有意？  
4. **Q-MARKET-USER** Power Market 的获客主用户是平台超管、租户，还是各宿主 Agent 使用者？一期 Non-Goals（无门户无分成）下获客如何发生？  
5. **Q-BILL** 付费是 v1 在线账单还是只联系销售？专业档按钮出口绑在这里。  
6. **Q-LLM** 长期 LLM 数据面是 LiteLLM 还是 new-api（或继续旁路）？ops 无市场数据可贡献，只标：中转若变规划依赖，S-09/S-10 的对外解释必须重写。  
7. 成功激活事件定义：蓝图默认「出数」；Q-VOICE 可能改成「订阅」。本期全无基线。是否允许 ops 下轮**主动**收集（注册页一题、后台「你希望我们做什么」）——样本可能仍为 0。  
8. AGPLv3 + 「不做套壳倒卖」下，中转柱对外收费的合规故事谁写？投诉通道对应定价「工单支持」——做还是删？（审查 QA-08 建议升为必答，ops 不代列入 §9.1。）

---

## 自检

- [x] 每条信号有出处（文件路径 / 设计章节 / 官方 URL / spec 章节）；无工单号则显式写「无用户原声」
- [x] 原文未改写
- [x] 提及次数与影响用户数分开；影响面未编数字
- [x] 行为数据交叉验证：全部未获取，并指出缺哪些冻结事件
- [x] 信号弱如实标注
- [x] 用户解法 vs 观察分开；未在归纳阶段下因果
- [x] 故障/权限/文档漂移/度量契约裂口已转出
- [x] 渠道偏差已声明
- [x] 与上期对比：无使用量，未假装归一化；新增的是内部契约不是用户暴增
- [x] 竞品每项借鉴/回避/差异化之一；回避有复审条件
- [x] 未替 `/pm` 做 RICE / 优先级 / 功能设计
- [x] P9：明确无法对照实际值；只对照「预测写下 vs 仓库仍零落点」
- [x] 增长数据：时间窗与口径来自蓝图；实际值标未获取
- [x] 四柱均覆盖
- [x] Claude / Kimi / Grok 插件市场 + 通用采集 SaaS + new-api 本体均有 borrow/avoid/differentiate
- [x] 未写实现、表结构、接口形状
