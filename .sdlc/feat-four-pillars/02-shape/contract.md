# 技术方案 · 四支柱程序（Wave 0 + Wave 1）

> 上游：PRD `.sdlc/feat-four-pillars/01-define/spec.md` **v1.4**（冻结 **FR-01…FR-36** 与 NFR-01…10；D22–D29 五类平级；Wave 2–4 stub **不进本方案实现**）｜泳道：L4｜appetite：Wave 0 **3.5 人周** · Wave 1 **11 人周**｜作者：/architect｜日期：2026-09-07｜版本：v2.1
> 下游：`/dba`（数据语义 §7）· `/designer`（商店面/治理台 IA）· 实现角色（票 + 契约）· `/qa`（风险点）· `/sre`（密钥与拓扑）
> 产品冻结：Power Market **D1–D29 Accepted**（含 2026-09-07b 五类平级）。本方案 **不重开** D 决策。词汇以 `CONTEXT.md` 为准。
> 操作者七问 **Q-VOICE / Q-PRICE / Q-RELAY / Q-MARKET-USER / Q-BILL / Q-LLM / Q-AGPL** 保持开放：本方案只覆盖不依赖其答案的不变式，**禁止代选**。
> 编排器文件名：本文件即 `contract.md`（内容 = skill 的 `solution.md`）。规范副本：`/Users/xuyun/Documents/grok-files/four-pillars-plan.md`。
> 本文件 **替换** `state.yaml.stale_artifacts` 中的塑形半成品。ADR-0010…0014 整份重写，不是对 stale 正文打补丁。

---

## 0. 执行一页纸：现在 vs 可卖 vs 本程序

四柱已经长在同一套 FastAPI 单体 + 平行 Scrapy Worker + 双前端里。挡住「可卖」的不是缺第四个进程，而是 **对外合同、权限、配额、商店闸门四条裂缝同时开着**。客户工单 = 0；本期成功 = 四周后能判定，不是提升 x%。

| 柱 | 现在实际是什么 | 可对外卖？ | 本程序冻结波交付 |
|---|---|---|---|
| **采集** | 任务/AI 向导/结果/CSV 控制面可用。注册成功进不了后台。调度/模板/AI 试采入队丢租户。Worker 不在根 compose。官网卖 Excel，实现拒 xlsx。 | **否** | **Wave 0**：入队带租户、候选不计配额、导出诚实、出站 Key 无绑定则拒绝。**Wave 4 stub**：第一次出数 / Worker 空态（阻塞执行面，本方案不拆实现票） |
| **SaaS** | 行级隔离 + 成员 + 手改配额 + 免费注册。定价三档都进注册。LLM 套餐数字不挡 `llm_chat`。用量页泄漏 `QUOTA_EXCEEDED`。无支付、无埋点。 | **否** | **Wave 0**：收权、真闸、上海业务日、漏斗事件。**Wave 2 stub**：可售卖环（阻塞 **Q-BILL**） |
| **中转站** | 渠道总览/探针/窗口额度在。守卫是 `require_admin`（租户公司管理员可过）。官网零入口。与规划器零引用。 | **否** | **Wave 0**：写权仅超管；租户导航隐藏、直打同 404。**Wave 3 stub**：租户产品面（阻塞 **Q-RELAY**；对外收费还阻塞 **Q-AGPL**） |
| **能力市场** | P6 目录 + 扫描 + MCP verify + 技能广场能搜。能力广场无搜索无详情。无 `listing_state` / Source / 安装。`POWER_MARKET` 全库 **0 命中**。 | **否** | **Wave 1**：按 D1–D29 升级枢纽（五类平级商店面 + 治理台 + 按卡片订阅）。**不**另起微服务、**不**代写宿主配置、**不**把插件当订阅礼包 |

```
现在能演示          本程序要变成            明确还不做
─────────────       ────────────────        ──────────────
采集控制台          访客不被骗              支付 / 发票 / 工单系统
成员 + 用量条       公司管理员管不了平台     租户渠道组屏（Q-RELAY）
中转值班页          租户能订已上架能力       开发者门户 / 分成
P6 扫描目录         四周后能报 WACT 基线     专家团执行 / 模板店 / xlsx
示意 Hero 大数      公开闸 listed∩发布∩许可  数仓 / 评估集准确率
```

**本轮允许进入实现的冻结 FR：** Wave 0 全部（FR-01…16）+ Wave 1 全部（FR-17…32）。Wave 2–4 只保留 stub 边界，**不拆实现票**。

**Effort（替换 PRD pending 区间）：** Wave 0 **3.5 人周**（16.5 人天）；Wave 1 **11 人周**（实现票 8.5 + 守卫/公开闸测试合同改写与双前端联调 2.5）。合计冻结集 **14.5 人周**。单波超出该波 50% → 停下重判。

---

## 1. 现状测绘（改造类必填）

**现有边界**：单进程 FastAPI（`backend/app/__init__.py` `create_app()` :9111）+ 平行 Scrapy Worker；双前端 official:9113 / admin:9112。四柱能力平铺在 `backend/services/`（上帝包），编排者是「整个 backend」，不是某一柱。宪法 B1–B3（`scripts/check-arch.sh`）挡住 `platform_core ⇄ backend ⇄ scrapy ⇄ config`，**挡不住柱与柱在 services 内互相 import**（无 B4）。

| 柱 | 代码落点 | 本波处置 |
|---|---|---|
| 采集 | `spider_*` / `ai_planner` / `tasks/consumer.py` / `scrapy/` | Wave 0 补租户入队、配额过滤、出站拒绝；**不重写任务状态机**（FR-70 属 Wave 4） |
| SaaS | `tenants` / `members` / `quota_service` / `deps.py` | Wave 0 收权 + 配额真闸 + 埋点 |
| 中转站 | `api/v1/newapi.py` + `NewapiApiClient` | Wave 0 **只收写权 + 租户隐藏**（FR-07）；不改探针熔断 |
| 能力/市场 | `capability_assets` + `public_skills.py` + `Capabilities.tsx` | Wave 0 收权/不泄漏；Wave 1 升级为能力市场（非第五套产品） |

**约束**：

| 约束 | 来源 | 影响 |
|---|---|---|
| 不拆微服务 | 无独立伸缩/发布/团队墙；设计 Alternatives「平行 /market」否决 | 市场落在既有单体 + `power_market` 子包 |
| 不合并 `skills` 三表 | 设计 Non-Goal；改 `uq_asset_type_name_alive` 破坏性 | 目录读 `capability_assets`；技能治理仍走 `/skills` 双写 |
| 爬虫禁止 import backend、禁止直写主库 | R3/R4/B2 | `skill_harvester` 继续 Redis；源索引 **不是** 爬虫 |
| API 禁止 import ORM | R7 | 新路由继续投影 |
| 手写 Alembic SQL 禁止 | ADR-0002 | `/dba` autogenerate；破坏性走 expand-contract |
| `require_admin` ≠ 平台超管 | `backend/app/api/deps.py`：`require_admin = require_role("admin")`；租户公司管理员 `role=admin` | Wave 0 市场/渠道/平台 LLM 写面改 `require_platform_admin` |
| `spider_results.tenant_id` NOT NULL | 迁移 `017_saas_tenant_foundation.py` `TENANT_TABLES` 含 `spider_results`，除 `llm_providers` 外收紧 NOT NULL | **禁止**「平台候选行 tenant_id NULL」。stale ADR-0013 该句作废 |
| Alembic 头 = `027` | dba 诊断；设计稿「030_*」过期 | 权限种子跟 027 之后下一次 autogenerate |
| 操作者七问未关 | spec §9.1 | 不得代选定位句、定价履约、中转 SKU、市场主用户、支付、LLM 网关、AGPL 故事 |
| 本程序不改后台菜单分组 | spec T-31 / §5 | 只改写权、隐藏渠道叶、词表；不修幽灵 `/enterprise` `/rbac` |

**本次不动什么**（防范围蔓延）：

- Scrapy 管道、Redis 队列协议、Worker 调度（Wave 4）
- `platform_core` 感知业务表名（豁免清单继续只活在 `backend/app/tenant_isolation.py`）
- new-api **本体**（转发/计费）；logs SQL 反腐不进本波
- 不把 `plugin-updater` 搬进平台；不代写 `~/.zcode/cli/config.json`（D21）
- 不合并 skills 与 capability_assets；不建 `kimi_plugin` / `capability_listings` 表
- 不实现支付、工单系统、租户渠道组屏、开发者门户、分成、xlsx、模板店、专家团执行
- 不新写并列四柱 Hero 承诺句（Q-VOICE）；不把 ¥299 做成可买（Q-PRICE/Q-BILL）
- LiteLLM 替换 new-api（Q-LLM）；`mcp_bridge.call_tool` 除验证抽样外不扩成 Agent 运行时
- 不把 `backend/services` 一次性搬成 `domains/`
- 不删 `capability-library/backend` 8765 残骸（rabbit hole）

**已知技术债**（碰到就要小心，不在本轮修）：

| 位置 | 债 | 本次是否触碰 |
|---|---|---|
| `backend/services/spider_service.py` R12 门面 | 6 个域外消费者；`enqueue` **不转发** `tenant_id` | 入队补 `tenant_id` 时门面必须转发；不拆门面 |
| `skills` ↔ `capability_assets` 双写 | 治理字段两份 | Wave 1 同步继续双写；禁止第三份 |
| `SkillJob` 兼扫描/评分 | 变成通用 job 表 | Wave 1 短码 `src_sync` 复用；不拆 `capability_jobs` |
| `capability-library/plugins/` symlink + `.grok/plugins` | Catalog/Runtime 糊在一起 | 不扩展森林；指针落 `pointers/`；D16 回退仍走旧根 |
| `llm_usage_service` 月度 hash field 历史无 tenant | dba P1 | Wave 0 LLM 闸走 `QuotaService` + `llm_token_usage` 表；Redis field 演进交 `/dba` 记债，不挡 FR-10 |
| `departments` 有 `tenant_id` 非 Mixin | 读不注入 | 本程序不改组织模型；点名给 `/dba` 债 |
| README V1 路由表过期 | 合同漂移 | 实现票顺手不强制 |

---

## 1.5 分柱：问题 / 为什么 / 改进 / FR 映射

每条：用户能碰到的问题 → 根因（边界错在哪）→ 本程序改进（模块，不是代码）→ 冻结 FR。证据来自诊断 + 本轮读码。

### 柱 A · 智能采集

| | |
|--|--|
| **问题** | 官网说「粘贴链接交给 AI、CSV/Excel」；注册成功主按钮是「再注册一家」。调度/模板/AI 试采入队不带企业。市场候选与采集成果同表，配额 COUNT 全表。平台出站 Key 按爬虫名拉数、无租户维。Worker 不在编排里时任务会一直 pending（Wave 4）。 |
| **为什么** | 官网与后台是两个前端包，卖点不绑定可完成动作。门面 `SpiderService.enqueue` 丢掉 `tenant_id`（`spider_service.py:78-79`），调度 `_fire`（`schedule_service.py:275`）与模板 `create_task_from_template`（`spider_registry_service.py:372-376`）不传。候选被建模成「又一次爬取结果」。外部面是平台共享钥匙。 |
| **改进** | 采集入队编排独占写任务：所有产任务路径带租户并计并发。结果出口过滤 `source <> marketplace`。出站无绑定则拒绝。官网改口（Excel 删除或标预告；100 条上限写在按钮上）。Worker 空态留给 Wave 4。 |
| **FR** | Wave 0：FR-03、FR-08、FR-09、FR-11、GWT-08.4。Wave 4 stub：FR-70…72。 |

### 柱 B · SaaS

| | |
|--|--|
| **问题** | 公司管理员与平台超管在写面上被当成同一类「admin」。套餐 20 万 tokens 不挡规划/评分。用量页写 `429 QUOTA_EXCEEDED`。仪表盘/用量时区口径分裂。零产品事件，WACT 无法判定。 |
| **为什么** | `require_admin = require_role("admin")`（`deps.py:116`）在能力中心/中转/LLM 写面被抄成最宽守卫。`check_llm_tokens_month` 仅测试引用；`llm_chat` 走 `LLM.MAX_TOKENS_BUDGET`。审计日志不是漏斗分母。 |
| **改进** | SaaS 鉴权区分 `is_platform_admin` 与租户 `admin`。配额叶子在真调用前执法。用量词表按 FR-12；业务日 Asia/Shanghai。产品事件叶子追加、失败不挡主路径。 |
| **FR** | Wave 0：FR-04、FR-05、FR-06、FR-07、FR-10、FR-12、FR-15、FR-16。Wave 2 stub：FR-50…51（Q-BILL）。 |

### 柱 C · 中转站

| | |
|--|--|
| **问题** | 租户公司管理员能改全站渠道窗口与平台 LLM 供应商。导航对租户露出「中转站管控」。定价还在卖「渠道组」。探针与规划器不相干。 |
| **为什么** | `newapi.py` 文件头写死全部 `require_admin`。`ProtectedRoute requireAdmin` 只认 `role==='admin' \|\| is_admin`（`ProtectedRoute.tsx:22`），登录快照无 `is_platform_admin`。产品定位（内部成本 vs SKU）未拍板。 |
| **改进** | 写面 `require_platform_admin`。租户：导航不出现渠道/中转；直打 URL 与「页面不存在」相同（不是道歉式 403）。定价空头按 FR-01 不变式撤或标预告（撤 vs 履约 = Q-PRICE，不代选）。探针伪装不自动下线（FR-61，本波不改行为）。 |
| **FR** | Wave 0：FR-07、FR-14（密钥）。Wave 3 stub：FR-60、FR-61（Q-RELAY / Q-AGPL）。 |

### 柱 D · 能力市场

| | |
|--|--|
| **问题** | 两个广场。公开能力只滤 `status=stable`，丢掉 recommended。无上架三态、无订阅、无预告、无许可闸。管理端任意登录可扫目录并拉起 stdio MCP。`capability_assets` 有 `tenant_id` 未豁免 → 租户态 Core UPDATE 0 行。 |
| **为什么** | P6 把 `status` 同时当质量与展示。扫描根钉死 `LIBRARY_ROOT/plugins`。守卫抄了 `require_login`。测试把 viewer 可扫写成绿灯（`test_b1c`）。 |
| **改进** | 升级既有枢纽：Source 索引外部树（不 copy）；`listing_state` 与 `status` 分列；公开闸 SQL 内完成；租户安装表走 TenantMixin；写面仅超管。D1–D21 映射见 §2.5。 |
| **FR** | Wave 0：FR-06、FR-13。Wave 1：FR-17…32。 |

---

## 2. 模块边界

### 2.1 能力聚类

| FR | 能力拆解 | 归属模块 |
|---|---|---|
| FR-01/02/05 | 官网承诺与可走完动作对齐；删虚构规模；付费 CTA ≠ 免费注册 | 官网商店面（official） |
| FR-03 | 导出格式/条数上限可见可执行；跨租户导出拒绝+审计 | 采集结果出口 |
| FR-04 | 注册成功主按钮去登录 | 官网 + SaaS 注册（无后端合同变更） |
| FR-06 | 平台目录写（扫描/验证/上架/源）仅平台超管 | SaaS 鉴权 × 能力中心 |
| FR-07 | 平台渠道窗口 / 平台 LLM 供应商写仅超管；租户渠道页同 404 | SaaS 鉴权 × 中转站 × LLM 叶子 × Admin 壳 |
| FR-08 | 租户只见本租户任务/结果/成员 | SaaS 隔离（已有 Mixin；补漏入队） |
| GWT-08.4 | 出站钥匙无租户绑定则拒绝 | 采集结果出口 × 外部 API |
| FR-09 | 定时/模板/AI 试采任务带提交者租户并计配额 | 采集入队编排 |
| FR-10 | 月度 LLM token 挡住真实模型调用 | LLM 运行时叶子 × 配额 |
| FR-11 | 市场候选不计存储配额、不进「我的结果」 | 采集结果出口 × 市场候选缝 |
| FR-12 | 将满/超限文案与下一步，无内部错误码 | SaaS 用量 |
| FR-13 | 公开/管理详情不露本机路径；未上架/黑名单当 404 | 市场公开协议 |
| FR-14 | 公开发布物无明文上游密钥；页上掩码 | 配置/密钥 |
| FR-15 | 获客/激活漏斗事件可查 | 产品事件 |
| FR-16 | 仪表盘/用量同一 Asia/Shanghai 业务日 | SaaS 用量 + 采集仪表盘 |
| FR-17/28 | 单一「能力市场」入口；六态词表；失败不装空 | 官网商店面 |
| FR-18/23/31 | 公开闸：上架 ∩ 治理 ∩ 许可；第一方已发布默认已上架 | 市场公开协议 |
| FR-19 | 短名搜索；目录名或别名打开详情；别名冲突失败 | 市场公开协议 |
| FR-20/21/29 | 租户订阅/启用/信任/卸载；下架后安装保留；只读拒绝 | 租户安装 |
| FR-22/25 | 上架三态；源登记与同步；同步不上架 | 市场 Source / Catalog |
| FR-24 | 捆绑技能独立显隐；父未上架子仍可出现 | 市场 Catalog |
| FR-26 | listed ≠ trusted ≠ enabled ≠ 已订阅；ZCode 只说明；无「启用到宿主」按钮 | 市场 Catalog + 出站说明 |
| FR-27 | 第三方不写回源树；插件重名不静默改名 | 市场 Source |
| FR-30 | 市场发现/订阅事件 | 产品事件 |
| FR-32 | 公开详情不可信正文按纯文本渲染 | 官网商店面 × 市场公开协议 |

**FR 归属核对**：FR-01…FR-32 均有归属。无 Wave 2–4 FR 进入本方案实现票。

### 2.2 模块清单

| 模块 | 一句话职责（不含「和」） | 变更理由 | 新建/既有 |
|---|---|---|---|
| SaaS 鉴权 | 区分平台超管与租户 admin，并把平台写面收口 | FR-06/07；今日 `require_admin` 混用 | 既有（改守卫） |
| SaaS 配额 | 三类配额真闸 + 上海业务日用量 | FR-09…12、FR-16 | 既有（接线） |
| 采集入队 | 所有入队路径带租户并计并发 | FR-08/09 | 既有 |
| 采集结果出口 | 本租户 CSV/JSON 导出；候选不可见；出站无绑定拒绝 | FR-03/11、GWT-08.4 | 既有 |
| 中转站写面 | 渠道窗口仅平台超管可改 | FR-07 | 既有（改守卫，不改探针） |
| LLM 运行时叶子 | 规划/评分/试采走 `llm_providers` + 租户月度闸 | FR-10；ADR-0014 本波冻结 | 既有 |
| 能力中心 Catalog | 五类平级治理行（skill/plugin/command/agent/team） | Wave 1 加 listing/许可/源指针/命令表 | 既有扩展 + `capability_commands` |
| Power Market Source | 登记外部树并幂等索引 | FR-25；禁止 copy 进 git | **新建** `backend/services/power_market/` |
| 市场公开协议 | 匿名可逛的闸后投影 | FR-13/17/18/19/28/31/32 | 既有 `public_skills.py`，升级 |
| 租户安装 | 企业 × 资产 × 宿主订阅行 | FR-20/21/29 | **新建**（表由 /dba） |
| MCP 验证叶子 | 抽样验证插件 MCP | FR-26；一期禁止成长为工具面 | 既有 |
| 产品事件 | 漏斗事件落可查询存储 | FR-15/30 | **新建**（OLTP 追加表） |
| 官网商店面 | 访客看到的承诺与市场 | FR-01…05、17…21、28、32 | 既有 official |
| Admin 治理台 | 超管源/上架/许可；租户用量/采集 | FR-06/07/22…25 | 既有 admin |

### 2.3 依赖图

```
官网商店面 / Admin 治理台
        │
        ▼
编排 API（backend/app/api）——协议与守卫，不持有域知识，不 import ORM
        │
        ├──► 【SaaS 鉴权/配额/成员】
        │         │
        │         └──► 【产品事件】（叶子；失败不挡主路径）
        ├──► 【采集入队/结果出口】
        │         │
        │         └──► 候选只读端口 ──► 【Power Market】（禁止 Market import spider_* 内部）
        ├──► 【中转站】（NewapiApiClient 唯一出站；本波只收权）
        ├──► 【LLM 运行时叶子】（llm_common + llm_providers）
        └──► 【Power Market】
                  ├──► 【能力中心 Catalog】（既有 capability_* / skills 双写）
                  ├──► 【MCP 验证叶子】
                  └──► 【租户安装】──► SaaS 隔离（TenantMixin，禁止豁免）
```

**无环确认**：☑ 已检查。采集 **不知道** 市场；市场 **不写** `spider_results` 业务字段（候选继续只读，见 ADR-0013）；中转站 **不被** 规划器 import；`power_market` **禁止** import `spider_*` / `newapi_*` / `ai_planner` / `channel_*`（B4）。

有环风险（今日）：`SkillService` 直查 `SpiderResult`。解法：Wave 0 起市场只经「候选端口」读（函数放在采集 query 侧，例如 `marketplace_candidates.py` 适配器），`power_market` 包不 import `spider_*`。候选审核 API 仍挂技能域，不搬进市场包。

### 2.4 耦合检查

| 检查项 | 结果 |
|---|---|
| 有无两模块共享表且都写 | **有（记债）**：`spider_results` 今日被采集 consumer 写、被 `SkillService.approve_candidate` 写 `extra.review`。ADR-0013：Wave 0/1 **冻结**为采集独占写、市场只读 + 转正走既有 `approve_candidate`（仍写 extra，不扩展协议）。新表迁出不进本波 |
| 有无模块含其它模块的知识（`if (来源 == X)`） | 公开闸的 `listing ∩ status ∩ license` 放在市场公开协议，不放采集。配额 `source <> marketplace` 是采集出口规则，不放市场包 |
| 边界强制手段 | 目录约定 `backend/services/power_market/` + **静态检查 B4**（`scripts/check-arch.sh`，挂 `sdlc.config.yaml` lint 闸门） |

---

## 2.5 Power Market：D1–D21 → 模块 → PR1–PR9

设计文档 Accepted；评审 Approve、**0 open**。下表是塑形映射，**不是**重开 D。票号见 §10；PR 号保持设计原文，便于对照 `power-market-design.md` PR Plan。

| D | 已决（不重开） | 模块 | 落地 PR / 票 |
|---|---|---|---|
| D1 | Source 注册表 + `SOURCE.yaml` 指针；禁止 copy 进 git；不再扩 per-plugin symlink | Source | PR2、PR9（T-19/T-21/T-36） |
| D1b | 指针落 `capability-library/pointers/plugins/`，**不**写进 `plugins/` | Source | PR9（T-36） |
| D2 | 第三方 canonical = 上游工作副本 / `CACHE_DIR` clone | Source | PR2（T-21） |
| D3 | 类型内全局 `name`；bundled slug `{plugin}__{local}`；搜索走短名 | Catalog 身份 | PR3（T-23/T-25）；ADR-0012 |
| D3b | 同 hash 嵌套副本折叠为一条 child | Catalog | PR3（T-23） |
| D3c | `origin_ref` 相对 adapter root；git 单插件 `"."` | Source | PR2（T-21） |
| D4 | bundled 技能提升为 skill 行 + components 边 | Catalog | PR3（T-23/T-29） |
| D5 | 第三方治理只写 DB；`writable=0` 禁止写源树 | Catalog | PR3（T-26） |
| D6 | 新列 `listing_state` ∈ {unlisted, listed, coming_soon}，不复用 `status` | Catalog | PR1、PR4（T-18/T-24） |
| D7 | 第三方同步绝不自动 listed | Source | PR2、PR4（T-23/T-24） |
| D8 | 入站适配器 ≠ 出站适配器 | Source / Runtime | PR2、PR8 缩水（T-21/T-28） |
| D9 | 市场列表/公开面只读 `capability_assets` | 市场公开协议 | PR6（T-25） |
| D10 | 一期做 `capability_installs`；（tenant, asset, host, alive）唯一；enabled 默认开、trusted 默认关 | 租户安装 | PR1、PR4b（T-18/T-27） |
| D11 | 许可黑名单默认不公开；`public_license_override` 仅超管 | Catalog / 公开 | PR4、PR6（T-24/T-25） |
| D12 | 插件撞名 → `parse_error`，不静默加前缀 | Source | PR2（T-23） |
| D13 | v1 做 git 适配器；`type=url` 保留枚举、POST 422 | Source | PR2（T-21） |
| D14 | 市场写 → `require_platform_admin`，不用 `require_admin` | SaaS 鉴权 | **Wave 0 T-02** + PR4（T-24） |
| D15 | 读正文只走 `resolve_origin_path`；禁止把 git URI 当文件系统路径 | Source | PR2/PR3（T-21/T-26） |
| D16 | `ENABLED=false` 或 SOURCES 空时 `scan_plugins` 保持今日 `LIBRARY_ROOT/plugins` 回退 | Source | PR2（T-19/T-21） |
| D17 | `coming_soon` 出现在公开列表；预告不可订 | 市场公开协议 | PR6（T-25/T-30） |
| D18 | 人工 vanity alias；与存活目录名冲突 409 | Catalog | PR1、PR4（T-18/T-24） |
| D19 | `/skills` 并入 `/capabilities?type=skill`；导航只留「能力市场」 | 官网商店面 | PR6（T-30） |
| D20 | `dev-team` 不可上架/预告；`UNLISTABLE_PACKAGES` | Catalog | PR2、PR4（T-23/T-24） |
| D21 | `ZCODE_WRITE=false`；不写 `~/.zcode/cli/config.json` | Runtime 说明 | PR8 **缩水**（T-28）：只返回折叠说明，**不**做 enable-host 按钮（FR-26） |

**PR 顺序（设计冻结，本方案沿用）：** schema（PR1）→ 适配器（PR2）→ 提升 child（PR3）→ 治理 API（PR4）→ 租户安装 API（PR4b）→ Admin UI（PR5）→ 商店面（PR6）→ Kimi（PR7）→ 安装说明（PR8 缩水）→ 指针/词汇（PR9）。

**相对设计 PR Plan 的唯一修订（产品冻结迫使，不是重开 D）：**

- **PR8**：设计写 `POST enable-host` + Admin 按钮。spec FR-26 / GWT-26.1：**Wave 1 商店与治理台不出现「启用到宿主」主按钮**。本方案 PR8 = 详情页折叠「安装到本机」说明 + snippet 字段；**不**挂 `POST /plugins/{name}/enable-host`，**不**建 runtime symlink。完整投影留给后续特征。
- **PR4 守卫收紧**与 Wave 0 T-02 重叠：Wave 0 先把 `scan-plugins` / `verify` 收到 `require_platform_admin`（FR-06 永不砍）；PR4 再加 `btn:market:*` 与 listing 路由。
- **FR-32**（审查补的 XSS）挂 PR6 官网详情，不新开 PR。

---

## 3. C4 模型

### Context

```
匿名访客 ──逛官网/定价/能力市场──► official:9113
刚注册负责人 ──注册成功去登录──► admin:9112 登录
租户经办/负责人 ──采集/用量/订阅──► admin:9112 + /api/v1
租户只读 ──看本企业任务/用量──► admin:9112（订/改安装/提交任务拒绝）
平台超管 ──源/上架/许可/渠道/平台 LLM──► admin:9112 + /api/v1
宿主 Agent 使用者 ──读「安装到本机」说明──► 自己改 Grok/ZCode/Kimi/Claude（平台不代写）

外部系统（我们不拥有）：
  MySQL 主库 · Redis 队列/锁 · Scrapy Worker
  new-api（旁路运维面；本波不接线到规划器）
  ~/.zcode/local-plugins · Kimi managed 树 · git clone → CACHE_DIR
```

边界画在这里：我们负责 **目录、闸门、订阅记录、说明、采集控制面、配额**；不负责在用户机器上启用 Agent，不负责向访客收取 ¥299，不负责 new-api 转发计费。

### Container

```
frontend/official :9113     静态站点；调 /api/v1/public 与注册；无 JWT 商店浏览
frontend/admin    :9112     JWT → /api/v1
FastAPI 单体      :9111     唯一业务进程（采集消费者 / 调度 / 探针 lifespan）
MySQL             主库（含本波 product_events 与 Wave 1 市场新表）
Redis             队列 / 配额计数缓存 / 公开限流
Scrapy Worker     与 backend 平行，禁 import backend
new-api compose   独立网络；本波只收平台写守卫，不并入根 compose
capability-library 第一方技能 + pointers/（指针，非内容）
```

不新增可部署业务进程。理由：无拆服务信号（ADR-0010）。sre 诊断的 Worker/前端编排缺口 **不在本程序实现票**（记入风险；FR-71 属 Wave 4）。

### Component（= §2 模块，不画类）

```
FastAPI 进程内：
  API 编排（v1 routers）
    ├── SaaS 鉴权 / 配额 / 成员
    ├── 采集入队 / 结果出口 / 候选端口
    ├── 中转站写面（NewapiApiClient）
    ├── LLM 叶子（llm_chat）
    ├── Power Market Source（新建包）
    ├── 能力中心 Catalog（既有服务，扩展）
    ├── 租户安装
    ├── MCP 验证叶子
    └── 产品事件叶子
```

**不画类图。** 类的设计归实现角色。

---

## 4. 可行性验证（spike）

本方案 **未引入未验证技术**。可行性来自读现码，不是 C4。无独立实验环境数字；下列均为可判真假的代码事实（2026-09-07 复验）。

| spike | 问题（可判真假） | 时限 | 结论 |
|---|---|---|---|
| 平台超管守卫是否已存在 | `deps.require_platform_admin` 是否可复用 | 读码 | **是**。`/admin/tenants*` 已用；`capabilities.py` 写面 `require_login`；`newapi.py` / `llm_providers.py` 写面 `require_admin` |
| 目录写隔离是否会 0 行 | `capability_assets.tenant_id` 是否在豁免表 | 读码 | **会 0 行**。`tenant_isolation.py` 豁免了 `skills` 三表，**未**登记 `capability_assets`；注释仍写「清单内唯一功能必需的豁免是 skills」 |
| 入队是否丢租户 | 定时/模板/AI 试采是否传 `tenant_id` | 读码 | **丢**。`SpiderTaskService.enqueue` 有参数；门面不转发；`schedule_service._fire` 与 `create_task_from_template` 不传 |
| 017 是否允许结果行 NULL tenant | `spider_results.tenant_id` 可否空 | 读迁移 | **否**。`017` `TENANT_TABLES` 含 `spider_results`，回填 `default` 后 `nullable=False`。stale ADR-0013「平台行 NULL」**不可行** |
| LLM 套餐闸是否挡住真调用 | `check_llm_tokens_month` 的生产引用点 | 读码 | **只被测试调用**（`test_saas_quota.py` / `test_saas_byok.py`）。`llm_chat` 走 Redis/内存 provider 预算 |
| 市场字段是否已有 | 全库 `listing_state` / `POWER_MARKET` / `capability_installs` | grep | **0 命中**。公开列表写死 `status="stable"`（`public_skills.py:174`），丢掉 `recommended` |
| 埋点是否已有 | `official_page_viewed` 等事件名 | grep | **无** 产品事件 SDK/表 |
| 密钥是否在树内 | `deploy/litellm/config.gen.yaml` | sre 诊断 + git | **明文上游 Key 被跟踪**；文件头自称 gitignore，根 ignore 未登记 |
| 前端平台页守卫 | `ProtectedRoute requireAdmin` | 读码 | 只查 `role === 'admin' \|\| is_admin`；`LoginResponse` 有 `is_admin` **无** `is_platform_admin` |
| 出站拉数是否混租户 | `query_public_results` 有无 tenant 参数 | 读码 | **无**。`spider_query_service.py:91-114` 只按 `spider_name` 分页；空 `API_KEYS` 今日全拒（默认安全），**一旦配置字符串钥匙即混拉** |
| B4 是否已存在 | `check-arch.sh` 是否约束 services 内柱间 import | 读脚本 | **无 B4**。仅 B1–B3 |

```
spike：鉴权分层可落
问题：不改 JWT 形状能否把平台写面从租户 admin 拉开
环境：backend/app/api/deps.py CurrentUser.is_platform_admin
结果：字段已在身份快照；require_platform_admin 已实现
结论：Wave 0 改 Depends + 前端登录投影 is_platform_admin，无需新认证协议
```

```
spike：配额接线可落
问题：真实 LLM 调用点是否单点
环境：backend/services/ai_planner/llm_client.py llm_chat；skill_scoring_service 共用
结果：单点 llm_chat；current_tenant_id() 已取到并写入 record_usage
结论：在 llm_chat 调用模型前插入 QuotaService.check_llm_tokens_month 即可覆盖 FR-10；年-月用上海日历
```

```
spike：候选隔离不需要新表也不需要 NULL tenant_id
问题：FR-11 是否能用 source 过滤在 017 NOT NULL 下成立
环境：quota_service.check_result_storage COUNT 不过滤 source；list_candidates 全表 source=marketplace 再 Python 切片
结果：加 WHERE source <> 'marketplace' 即可让租户用量/数据中心不含候选；候选行 tenant_id 保持 NOT NULL（触发者或平台占位租户）
结论：Wave 0/1 不建候选表、不放宽 017。见 ADR-0013 v2
```

**无未验证技术声明**：未使用新语言/新中间件/新搜索引擎。市场列表 NFR-01（打开到可见卡片 ≤2s、目录约现有体量）距已知 MySQL 主键点查能力有数量级余量（设计估折叠后 ~300 行资产）。公开列表必须 **SQL 内闸门后再分页**（今日 `public/skills` 页内过滤是已知错误，Wave 1 修）。

---

## 5. 关键决策

| 决策 | 结论 | ADR |
|---|---|---|
| 部署形态 | 单体内域；新建 `power_market` 子包；不拆市场微服务 | [ADR-0010](adr-0010-four-pillar-topology.md) |
| Source / Catalog / Runtime | 三层不可混；指针 `capability-library/pointers/`；不扩展 symlink 森林 | [ADR-0011](adr-0011-source-catalog-runtime.md) |
| 目录身份 | 保持类型内全局 `name`；child `{plugin}__{local}`；不改唯一键 | [ADR-0012](adr-0012-catalog-identity.md) |
| 市场候选所有权 | 仍住 `spider_results.source=marketplace`；采集独占写；配额与租户列表排除；**tenant_id NOT NULL**（占位或触发者）；不建候选表 | [ADR-0013](adr-0013-candidate-ownership.md) |
| LLM 数据面（本波冻结，不代选 Q-LLM） | 规划/评分走 `llm_providers`；new-api 保持旁路；`mcp_bridge` 仅验证；LiteLLM 替换不进本特征 | [ADR-0014](adr-0014-llm-data-plane-wave-freeze.md) |
| 租户 × 平台目录 | 平台目录表豁免；`capability_installs` 禁止豁免；目录写 `require_platform_admin` | [ADR-0015](adr-0015-tenant-platform-catalog.md) |
| 产品事件存储 | OLTP 追加表；无仓；失败不挡主路径；查询面给平台超管 | [ADR-0016](adr-0016-product-events-oltp.md) |
| 鉴权分层 | 平台写面 = `is_platform_admin`；租户 admin 不再进渠道/平台 LLM/目录写；租户 BYOK 自有行仍可由租户经理写 | [ADR-0017](adr-0017-platform-vs-tenant-admin.md) |
| listed vs verify vs enable-host | 无 MCP ⇒ `unknown` 可上架；Wave 1 不交付 enable-host 按钮；生产默认不开代写 | [ADR-0018](adr-0018-listing-vs-verify.md)（supersedes CONTEXT/ADR-0001「未经 verify 不得分发」该行） |
| 同步 job | 复用 `skill_jobs.job_type=src_sync` | 无需 ADR（可逆短码） |
| 公开列表分页 | offset `page`/`page_size`，默认 20，最大 50（NFR-02） | 契约；沿用现公开 API 习惯 |
| B4 import 闸 | 本特征 lint 必做 | ADR-0010 配套 |
| 出站 Key | 无单一租户绑定则拒绝；不混两家企业行 | 契约 `outbound-data-api.md`；不另开 ADR（产品已冻 GWT-08.4） |

不可逆决策均有 ADR。Q-LLM 长期网关 **不在本表选择**。

---

## 6. 契约

| 契约 | 路径 | 消费方 |
|---|---|---|
| 通用约定 | [contracts/conventions.md](contracts/conventions.md) | 全部实现角色 / qa |
| 鉴权守卫 | [contracts/auth-guards.md](contracts/auth-guards.md) | backend / frontend / qa |
| 配额与隔离 | [contracts/quota-and-isolation.md](contracts/quota-and-isolation.md) | backend / frontend / qa |
| 出站拉数 | [contracts/outbound-data-api.md](contracts/outbound-data-api.md) | backend / qa |
| 获客/激活事件 | [contracts/product-events.md](contracts/product-events.md) | backend / frontend / qa / analyst |
| 市场公开 API | [contracts/market-public-api.md](contracts/market-public-api.md) | backend / official / qa |
| 市场治理 API | [contracts/market-admin-api.md](contracts/market-admin-api.md) | backend / admin / qa |
| 租户安装 API | [contracts/market-installs-api.md](contracts/market-installs-api.md) | backend / frontend / qa |
| 市场事件 | [contracts/market-events.md](contracts/market-events.md) | backend / frontend / qa / analyst |

数据语义给 `/dba`：§7。不在契约里写表结构。

---

## 7. 数据语义诉求（给 /dba，不写表结构）

```
实体诉求：

  产品事件 —— 一行 = 一次已发生的产品事实
    需要记录：event_name、occurred_at（事件发生时刻；存储约定 UTC naive DATETIME，
              切日用 Asia/Shanghai）、anonymous_id 或 tenant_id/user_id（已登录）、
              role、载荷 JSON（cta、format、result_count、spider、source、
              is_marketplace_candidate、host、reason 等）
    生命周期：追加；不改历史行；不软删；保留 ≥ 90 天（复盘 4 周 + 余量）
    访问模式：平台超管按时间窗 + event_name 翻页；按 tenant_id 过滤（验收 FR-15/30）
              禁止租户查他租户用户级事件
    失败语义：写入失败不得回滚业务事务、不得挡主路径
    不是：operation_logs（无事件名、无匿名访客、analyst 禁止当漏斗分母）

  平台目录资产 —— 一行 = 五类之一的 catalog 身份（全局 name；对外 agent/team）
    Wave 1 需要额外记录：上架三态、上架时刻、所属源、origin_ref、短名、
              父插件名、宿主兼容名单、许可、许可放行、是否可写回源树、
              被折叠的 alias_origin_refs
    生命周期：sync upsert 内容派生字段；人工写 listing/status/score/override
              同步不得覆盖 listing/health（MCP 清单 hash 变化除外）
    访问：公开列表 Q = 上架∈{listed,coming_soon} ∩ 治理∈{stable,recommended}
          ∩ (许可不在黑名单 OR override)；按短名/title/name 搜；按页 ≤50
    第一方 source 空：不参与「同步身份」唯一
    宿主名单语义（产品冻结，须能区分）：
              未声明（空缺 / NULL）= 四宿主都可订
              已声明空数组 = 四个都不可订
              已声明非空 = 仅名单内可订

  源 —— 一行 = 一条已登记外部树（稳定 name + type + uri）
    生命周期：配置或 Admin 登记 → 反复 sync → 配置删除只停用不清行
    访问：按 name；列表；最近 jobs（skill_jobs.source_id）
    plugin-updater 不是源

  组件边 —— 一行 = 插件 → 一条 bundled 子资产
    访问：插件详情捆绑列表只出已上架子资产

  租户安装 —— 一行 = 某租户对某资产在某宿主的订阅
    需要记录：enabled（默认开）、trusted（默认关）、软删卸载
    生命周期：见 spec §3.1；下架后行保留；黑名单行只读可卸
              同一能力订到第二宿主 = 新增一行，不覆盖第一行
    访问：本租户列表（可选 host）；按 (tenant, asset, host, 存活) 幂等
    隔离：TenantMixin；禁止进豁免表
    平台超管无 tenant_id → 不能建安装行
    不占三类配额

  别名 —— 一行 = 一条人工 vanity slug
    存活全局唯一；与存活 catalog name 互斥；同步不自动建

  市场候选（本波不新实体）—— 继续「采集结果里 source=marketplace 的行」
    tenant_id NOT NULL（017）。值 = 入队租户（触发者）；若平台超管无企业空间触发，
              使用 /dba 指定的平台占位租户行，禁止 NULL
    配额 COUNT 排除 marketplace；租户结果/导出排除；超管候选审核仍按 source 过滤
    访问：平台态按 source + review 翻页（禁止全表拉进 Python）
    extra.review 协议冻结：本波不得再加新键当市场状态机

约束诉求：
  资产 (type, name, alive) 保持；不改 uq_asset_type_name_alive
  同步身份 (source_id, origin_ref, alive)；第一方 source_id NULL 不参与
  安装 (tenant_id, asset_id, host, alive)
  别名 (slug, alive)
  源 (name, alive)
  listing=listed 与 status=blacklist 互斥（应用拒绝或保存时收回未上架）
  UNLISTABLE_PACKAGES 不可 listed/coming_soon
  source_type 取值将含 marketplace_crawled / source_indexed（>16 字符）
              ——现列 VARCHAR(16) 装不下，属 **放宽** 非收缩
  skills.name 仍全局唯一、无 alive_flag：本波产品无「删除再建同名」路径，
              不在本波改该唯一键；第三方 child 禁止软删，只标 missing
  出站钥匙：必须能表达「这把钥匙绑定且仅绑定一个 tenant_id」；
              未绑定不得查出任何租户行（GWT-08.4）

破坏性：
  无 drop/rename。只加列/新表/类型放宽。一律 expand-contract。
  禁止手写 Alembic SQL。头修订是 027，不要写「023/030 之后」。

明确非目标：
  不建 kimi_plugin、capability_listings、数仓 ODS、候选独立表。
```

采集柱：`spider_results` 继续「一次任务多条结果」。导出单次 **100 条**（NFR-02 现行上限，UI 必须写出）。

SaaS 柱：用量「本月」= **Asia/Shanghai 日历月**，不要 `datetime.utcnow().strftime("%Y-%m")`（今日 `tenant_usage.py` 如此，FR-16.2 会红）。

回填（Wave 1 PR1，设计已写，塑形确认）：仅第一方已发布/推荐 → `listing_state=listed`；**不要**在 schema 迁移里 attach `zcode_local`。

---

## 8. 角色裁剪声明

| 角色 | Wave 0 | Wave 1 | 理由 |
|---|---|---|---|
| `/dba` | **是** | **是** | W0：豁免清单 + 产品事件实体 + 出站钥匙绑定语义。W1：源/上架列/安装/别名/组件。Q1 schema=true |
| `/backend` | 是 | 是 | 守卫、配额接线、市场 API、事件 |
| `/frontend` | 是 | 是 | official 诚实/市场；admin 收权/治理/安装/用量文案 |
| `/designer` | 有限 | **是** | W0：官网删减可跟现组件，不挡 T-09。W1：商店面 + 治理台 6 Tab IA/词表 |
| `/sre` | 是 | 有限 | W0：FR-14 密钥离树。W1：CACHE_DIR / ENABLED 配置观察，不改 compose |
| `/qa` | 是（下游） | 是 | GWT 矩阵；本帽不写用例。守卫合同改写必须与实现同 PR |
| `/ops` | 有限 | 有限 | `POWER_MARKET.ENABLED` 默认 false；切源是配置动作 |
| `/data-collector` | **N/A（实现）** | **N/A** | 不改 Scrapy 管道/反爬；harvester 仍走 Redis；源索引不是爬虫。候选语义由采集结果出口过滤，不改出口 |
| `/algo` | **N/A** | **N/A** | 无新模型；验证/未知态是规则；评分沿用；评估集下一轮 |
| `/miner` | **N/A** | **N/A** | 无离线建模；`similar_to` 聚类不在同步期自动合并 |
| `/data-warehouse-engineer` | **N/A** | **N/A** | 事件进 OLTP；分层下一轮 |
| `/analyst` | 口径已交付 | 不进实现票 | 四周后复盘；不改事件名 |
| `/pm` | 定义已冻 v1.3 | 变更流程 | 七问未关前禁止实现帽发明产品规则 |
| `/qc` | N/A | 塑形后再审 | 无待发布候选 |
| `/designer` 菜单重组 | **跳过** | **跳过** | spec T-31：本程序不改菜单分组 |

用不上的显式声明 N/A。默默跳过无法区分「不需要」和「忘了」。

---

## 9. Rabbit Holes（会掉进去的坑，提前标出）

| 坑 | 为什么危险 | 边界 |
|---|---|---|
| 把 `backend/services` 一次性拆成 `domains/` | 测试 patch 路径全碎 | 只新建 `power_market/` + B4 |
| 候选迁出自有表（Q-CAND） | 多实体 + 投影延迟 + 前端候选 Tab | Wave 0/1 过滤+排除配额；迁表下一轮 |
| 合并 skills 与 assets | 全 URL 与评分 | Non-Goal |
| 通用 job 框架 | 过度设计 | `src_sync` 短码 |
| 代写宿主配置 / 完整 PR8 enable-host | 已决否；与 FR-26 冲突 | 生产投影关；Wave 1 只折叠说明 |
| LiteLLM / new-api 并入规划器 | Q-LLM 未决 | ADR-0014 冻结旁路 |
| 公开全文检索 description | 过万再上 | `q` 匹配 name/title/origin_local_name |
| 删 8765 残骸与 symlink 森林 | 易变成清仓 PR | 不进本波 |
| 把 Hero 改写成四柱定位 | **Q-VOICE** | 只删空头与虚构数字 |
| 专业档做成支付 / 履约空头卖点 | **Q-PRICE / Q-BILL** | CTA 去「联系」页，不是注册，也不是收银台 |
| 给租户做渠道组屏 | **Q-RELAY** | Wave 0 只隐藏+收写权 |
| 中转对外收费文案 | **Q-AGPL** | Q-RELAY=SKU/附加且收费前必须先关 AGPL；本方案不写可买 |
| 官网 CTA 主次（逛市场 vs 注册采集） | **Q-MARKET-USER** | 不重开 D10/D14/D21；不改冻结商店行为 |
| 到期租户登录拒绝 | miner vs 非 pm 草稿互殴；spec 未冻 | **不进 Wave 0 票**；记债 |
| 按钮码 FastAPI Depends | 今日无 `require_permission` | Wave 0 用户可见行为只需超管拒绝；`btn:market:*` 随 PR4 种子，执法可先前端 `usePermission` + 后端超管 |

**操作者必须回答、本方案禁止代选（原样列出）：**

| ID | 问题 | 阻塞什么 |
|---|---|---|
| **Q-VOICE** | 对外第一句话是采集、四柱平台，还是给 Agent 用的能力市场？ | FR-01 首屏那一句；北极星是否改核心动作 |
| **Q-PRICE** | 定价空头（工单支持 / 渠道组 / 私有技能库 / ¥299）是撤文案还是履约？ | FR-01.2、FR-05 的「预告 vs 删除 vs 做出来」 |
| **Q-RELAY** | 中转站是独立 SKU、采集附加、还是仅内部成本控制？官网零入口是否有意？ | FR-60；定价是否允许出现中转 |
| **Q-MARKET-USER** | 能力市场对外主用户是平台超管、租户，还是各宿主 Agent 使用者？ | 官网 CTA 主次；不重开 D10/D14/D21 |
| **Q-BILL** | 付费是 v1 在线账单，还是只联系销售？ | Wave 2 是否出现支付 FR |
| **Q-LLM** | 长期 LLM 数据面是 LiteLLM 还是 new-api（或继续现状）？ | 中转是否变成规划依赖 |
| **Q-AGPL** | 中转若对外作为独立 SKU 或采集附加收费，AGPLv3 商用故事如何对外陈述？ | Q-RELAY=SKU/附加且收费时的定价文案 |

**「第二次出现时再抽象」是防过度设计的默认纪律。**

---

## 10. 任务拆解

粒度：一票 = 一会话可完成「实现 + 自测 + 交付」。人天为 architect 粗估（**替换** PRD pending 区间）。每票必须有 FR 锚点。

### Wave 0 — 停止说谎 / 停止泄漏（3.5 人周）

票文件：`02-shape/tickets/T-nn.md`。

| 票 | 标题 | FR 锚点 | 依赖 | 角色 | 粗估 |
|---|---|---|---|---|---|
| T-01 | 平台目录豁免登记（capability_*） | FR-06 | — | `/dba` | 0.5d |
| T-02 | 能力/技能目录写面收权 | FR-06 | T-01 | `/backend` | 1d |
| T-03 | 中转站与平台 LLM 写面收权 | FR-07 | — | `/backend` | 1d |
| T-04 | Admin 平台页按 is_platform_admin；渠道页对租户同 404 | FR-06 FR-07 | T-02 T-03 契约 | `/frontend` | 1.5d |
| T-05 | 定时/模板/AI 试采入队带租户 | FR-08 FR-09 | — | `/backend` | 1d |
| T-06 | 真实 LLM 调用走租户月度配额 | FR-10 | — | `/backend` | 1d |
| T-07 | 市场候选排除配额与租户结果 | FR-11 FR-08 | T-05 | `/backend` | 1d |
| T-08 | 用量将满文案 + 上海业务日 | FR-12 FR-16 | T-06 | `/backend` `/frontend` | 1.5d |
| T-09 | 官网诚实与注册去登录 | FR-01 FR-02 FR-04 FR-05 | — | `/frontend` | 1.5d |
| T-10 | 导出格式/100 条上限可见 | FR-03 | T-07 | `/frontend` `/backend` | 1d |
| T-11 | 管理详情去路径、未发布当 404 | FR-13 | — | `/backend` | 0.5d |
| T-12 | 明文密钥离树与掩码 | FR-14 | — | `/sre` `/backend` | 1d |
| T-13 | 产品事件存储与查询面 | FR-15 | — | `/dba` `/backend` | 1.5d |
| T-14 | 获客/激活漏斗埋点 | FR-15 | T-13 | `/frontend` `/backend` | 1.5d |
| T-15 | B4 域 import 闸 + R10 扫子包 | NFR-10 | — | `/backend` | 0.5d |
| T-16 | 出站 Key 无租户绑定则拒绝 | GWT-08.4 FR-08 | — | `/backend` | 0.5d |

**并行**：T-01∥T-03∥T-05∥T-06∥T-09∥T-11∥T-12∥T-13∥T-15∥T-16。T-02 等 T-01。T-04 等守卫契约。T-07 等 T-05 入队语义。T-08 等 T-06。T-10 等导出过滤。T-14 等查询面。

**小计**：16.5 人天 ≈ **3.5 人周**（PRD 原 2–4 pending → 校准 3.5；下限仍覆盖权限与一致性）。

### Wave 1 — 能力市场（11 人周）

票以本表为权威；时间盒内不强制落 `tickets/` 文件。PR 号对照设计，禁止打乱 PR1→PR2 的 schema-before-origin 顺序。

| 票 | PR | 标题 | FR 锚点 | 依赖 | 角色 | 粗估 |
|---|---|---|---|---|---|---|
| T-17 | — | 商店面/治理台 IA 与词表 | FR-17 FR-28 | 契约 | `/designer` | 2d |
| T-18 | PR1 | 市场实体 db-spec + autogenerate + 第一方 listed 回填 | FR-18…31 数据面 | T-01 惯例 | `/dba` | 2.5d |
| T-19 | PR2 | `power_market` 包 + `power_market.yml` + D16 回退骨架 | FR-25 NFR-10 | T-15 T-18 | `/backend` | 1d |
| T-20 | PR4 | 源登记/同步 API | FR-25 | T-19 | `/backend` | 1.5d |
| T-21 | PR2 | zcode_local + git 适配器 + `resolve_origin_path` | FR-25 FR-27 | T-19 | `/backend` | 2.5d |
| T-22 | PR7 | kimi_home 适配器 | FR-25 | T-21 | `/backend` | 1.5d |
| T-23 | PR2/PR3 | src_sync：未上架默认、重名 parse_error、hash 折叠、部分失败 | FR-22 FR-25 FR-27 | T-20 T-21 | `/backend` | 2d |
| T-24 | PR4 | 上架/许可放行/别名 API；`UNLISTABLE` 422；同 PR 改 `test_b1c` | FR-22 FR-23 FR-19.4 | T-18 | `/backend` | 2d |
| T-25 | PR6 API | 公开闸 SQL + 短名搜索 + 别名详情 + 纯文本正文 | FR-18 FR-19 FR-28 FR-31 FR-32 | T-24 T-26 | `/backend` | 2.5d |
| T-26 | PR3 | scan_library 只扫第一方；writable=0 不写盘 | FR-27 FR-31 | T-18 T-23 | `/backend` | 1.5d |
| T-27 | PR4b | 租户安装 API（订/改/卸/下架保留/只读拒绝/多宿主多行/NULL vs 空名单） | FR-20 FR-21 FR-29 | T-24 | `/backend` | 2.5d |
| T-28 | PR8 缩水 | 安装到本机折叠说明；无 enable-host 按钮；ZCode 不写配置 | FR-26 | T-24 | `/backend` `/frontend` | 1d |
| T-29 | PR3 | 捆绑技能独立显隐 | FR-24 | T-23 T-24 | `/backend` | 1d |
| T-30 | PR6 UI | 官网单一能力市场：导航/重定向/列表/搜索/失败不装空 | FR-17 FR-18 FR-19 FR-28 | T-17 T-25 | `/frontend` | 2d |
| T-31 | PR6 UI | 官网详情 + XSS 纯文本 + 订阅 CTA | FR-19 FR-20 FR-32 | T-17 T-25 T-27 T-30 | `/frontend` | 2d |
| T-32 | PR5 | Admin 源 Tab + 目录 listing/alias/override | FR-22 FR-23 FR-25 | T-17 T-20 T-24 | `/frontend` | 2d |
| T-33 | PR5 | Admin 五类治理台（含命令/智能体）+ usePermission | FR-06 FR-22 FR-26 FR-33 | T-17 T-24 | `/frontend` | 2d |
| T-34 | PR6 UI | 我的安装：启用/信任确认/卸载 | FR-20 FR-21 FR-29 | T-17 T-27 T-31 | `/frontend` | 2.5d |
| T-35 | — | 市场埋点 | FR-30 | T-13 T-30 T-32 T-34 | `/frontend` `/backend` | 1.5d |
| T-36 | PR9 | SOURCE.yaml 指针 + CONTEXT 分发合同修订 | FR-25 D1b | T-23 | `/backend` `/ops` | 1d |

**并行**：T-17∥T-18。T-21∥T-24（契约已定）。T-22 在 T-21 接口稳定后。T-30 可在 T-25 契约冻结后用 mock 开工。T-32∥T-30。**禁止只上目录不上闸**：T-30 不得在 T-25 闸门前对用户开放（`POWER_MARKET.ENABLED` 默认 false，T-30 发布与 T-25/T-26 同波）。

**小计**：约 42.5 人天实现 + 联调缓冲 ≈ **11 人周**（PRD 原 8–16 pending → 校准 11）。超出本波 50%（>16.5 人周）→ 停下重判。

### Wave 2–4（stub / blocked）

| 波 | 状态 | 阻塞 | 本方案 |
|---|---|---|---|
| Wave 2 SaaS 可售卖环 | stub | **Q-BILL**（及 Q-PRICE 履约分支） | 不拆实现票；FR-50/51 仅切片必须为真的规则已写在 PRD |
| Wave 3 中转租户产品 | stub | **Q-RELAY**；对外收费另阻塞 **Q-AGPL** | 权限已在 Wave 0 冻结；不新造租户渠道组屏 |
| Wave 4 第一次出数 | stub | 非开放问题；appetite 6–12 人周未校准为实现票 | 不重写任务状态机；FR-71 Worker 空态下一波 |

**总粗估（冻结集）**：**14.5 人周**。给 `/pm` 作 RICE 的 Effort 输入。

**四柱不得合成一张巨票**：上表已按能力纵向切。

**并行度检查**：Wave 0 多票不改同一文件（官网 T-09 vs 后台守卫 T-02/T-03 vs 入队 T-05）。Wave 1 T-21 与 T-24 不改同一路由文件。若所有票串成一条线，说明按技术分层切了——本表不是。

---

## 11. 风险点（给 /qa 与 /sre）

| 风险 | 影响 | 给谁 | 建议关注 |
|---|---|---|---|
| 租户态扫描显示成功、DB 0 行 | 治理假成功 | `/qa` | T-01 后：租户 token 调 scan → 403；平台态才写 |
| 登录用户拉起 stdio MCP | 任意代码执行面 | `/qa` `/sre` | T-02：viewer/租户 admin → 403；同 PR 改 `test_b1c` viewer 200 |
| 只改市场、中转仍松 | 护栏「非超管改渠道=0」失败 | `/qa` | T-03/T-04 与 T-02 同波验收 |
| 租户直打 `/newapi` 看到道歉 403 或渠道数据 | 违反 GWT-07.3 | `/qa` `/frontend` | 必须与「页面不存在」相同，不是 Unauthorized 页 |
| `scan_library` 把第三方 child 标 missing 并写盘 | 污染 updater 副本 | `/qa` | T-26 夹具：promote 后 scan 仍 ok |
| 公开列表补 recommended + 预告 | 卡片变多；旧用例会红 | `/qa` | 白名单无 `file_path`；黑名单 404 与不存在相同 |
| 闸门切换空窗 | 第一方已发布技能从商店消失 | `/qa` | T-18 回填与 T-25 同发布；FR-31 |
| 宿主名单 NULL 被当成空数组 | 第一方不可订 | `/qa` | GWT-20.7 vs 20.8；FR-31.4 |
| 再订第二宿主覆盖第一行 | 违反 GWT-20.9 | `/qa` | 唯一键含 host |
| 只读成员改安装成功 | 违反 GWT-21.4 | `/qa` | 订阅/启用/信任/卸载均拒绝 |
| 候选仍占配额 | 租户存储被平台入站打满 | `/qa` | T-07：用量数字不含 marketplace |
| 事件写入挡主路径 | 注册/订阅变慢或失败 | `/qa` | 人为让事件库失败，主路径仍 2xx |
| 密钥回潮 | FR-14 回滚 | `/sre` | CI 扫 `sk-` 于 deploy/ 与 config/default |
| ENABLED=false 时把未上架当全部已上架 | NFR-03 | `/qa` | 回退扫描 ≠ 公开闸全开 |
| 配置了无绑定的出站 Key | 混拉两家企业 | `/qa` | T-16：有 Key 无 tenant 绑定 → 拒绝，响应 0 行 |
| 公开详情把 SKILL.md 当 HTML | XSS（FR-32） | `/qa` | 迁市场后 SkillsSquare 纯文本测试必须仍绿 |
| Worker 不在 compose | 采集主路径 pending（Wave 4） | `/sre` | 本波不修编排；官网不得假装正在爬 |
| 失败率护栏 +10pp 第一轮无基线 | 停线不可用 | `/analyst` | 先把周失败率记下来，不装精确红线 |

---

## 12. 变更记录

| 版本 | 日期 | 变更 | 触发者 |
|---|---|---|---|
| v1 | 2026-09-07 | 塑形半成品（stale）：缺执行一页纸、缺 D→PR 全表、ADR-0013 写 NULL tenant_id、契约/票目录空 | /architect 中断稿 |
| v2 | 2026-09-07 | 程序级方案书：对齐 spec v1.2（含 FR-32、GWT-08.4、渠道页 404、只读安装、多宿主多行、NULL vs 空名单）；替换 ADR-0010…0014；补 ADR-0015…0018；落地契约与 Wave 0 票；Effort 3.5+11 人周 | /architect |
| v2.1 | 2026-09-07 | 对齐 spec v1.4 / D22–D29：五类平级、订插件不级联、未上架≠停用、命令独立行 | /architect 同步词汇 |
