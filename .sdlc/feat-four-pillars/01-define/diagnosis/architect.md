# 架构诊断 · 四柱平台（采集 + SaaS + 中转站 + 能力市场）

> 角色：architect（定义帽诊断 **refresh**，泳道 L4）  
> 日期：2026-09-07  
> 上游：冻结 `01-define/spec.md` v1（Wave 0 FR-01…16、Wave 1 FR-17…31）；D1–D21 Accepted；`CONTEXT.md`；`project_rule.md`；Power Market 设计 Accepted + review Approve 0 open；现码 `backend/app` · `backend/services` · `capability-library` · `.sdlc/_lessons.md`  
> 下游：塑形帽写方案书 / ADR / 合同。**本文件不是方案书。**  
> 可行性：读码与测试合同，不是 C4 空想。本轮未跑 spike（无未验证新技术）。  
> 禁区：不写 `02-shape/contract.md`、不写工单、不写实现代码、不写表 DDL。不代选 **Q-VOICE / Q-PRICE / Q-RELAY / Q-MARKET-USER / Q-BILL / Q-LLM**。

**相对上一稿（同路径、定义帽并行诊断、当时尚无冻结 PRD）**

| 变化 | 处置 |
|------|------|
| `appetite: 8h` | 作废。程序按波：Wave 0 2–4 人周、Wave 1 8–16 人周（§6 校准） |
| 给 PM 的「边界输入」 | 已收成冻结 FR。本稿改为 **问题 → 原因 → 改进**，每条锚 FR |
| 旧 Q-AUTH / Q-SCOPE | **关闭**（产品已冻，见 §7） |
| `02-shape/adr-0010…0014` + `contract.md` | `state.yaml.stale_artifacts`。其中 ADR-0013「候选行 `tenant_id` NULL」与迁移 **017 NOT NULL** 冲突，**禁止当现行决策** |
| 操作者六问 | 保持开放；本帽只准备材料 |

**角色裁剪（给后续塑形 / 实现，不是工单）**

| 角色 | Wave 0 | Wave 1 | 理由 |
|------|--------|--------|------|
| `/pm` | 是（修 findings QA-02…12） | 是 | G-fresh blocker 仍 open 时塑形不得发明产品规则 |
| `/dba` | 是（豁免清单 + 若做埋点表；**候选新表不默认做**） | 是（Source / listing 加列 / 安装表，ADR-0002） | 不在本文件写 DDL |
| `/backend` `/frontend` `/qa` | 是 | 是 | 守卫、配额缝、商店面 |
| `/designer` | 有限（官网改口、空态词表） | 是（能力市场 IA） | 设计已定 6 Tab |
| `/sre` `/ops` | 是（FR-14 密钥、编排缺口） | 是（CACHE_DIR、ENABLED） | |
| `/data-collector` | 是（harvester 入站租户/source 缝） | 有限 | 运输层已合规，所有权错 |
| `/algo` | 否 | 有限 | 市场不新增模型；MCP 工具面二期另 ADR |
| `/miner` `/warehouse` `/analyst` | **N/A（实现）** | 埋点查询面验收 | 无仓；FR-15/30 先事件 |
| `/qc` `/reviewer` | 定义帽闸门 | 塑形后再审 | |

---

## 1. 一句话结论

现平台仍是 **单进程 FastAPI + 平行 Scrapy Worker**。四柱已经长在同一套 `backend/services` 里，按技术分层而不是按业务能力切边界。Power Market「升级 P6 枢纽、不另起微服务」**仍然契合**宪法与现部署；**可以落在现架构上**。

挡住 Wave 0/1 的不是缺一个容器，而是 **同一套契约被测试钉死成「错的正确」**：平台目录写过宽、租户写隔离漏网、采集表被市场征用、LLM 套餐闸没接线、调度/模板入队丢租户。check-arch B1–B3 **绿**也拦不住这些——它们不是 import 方向问题。

五条破坏半径最大的缝（与冻结 FR 对齐，现码 2026-09-07 复验仍在）：

1. **平台写面过宽**（FR-06/07）：能力写 `require_login`（viewer 可扫目录、拉起 MCP）；技能/LLM/中转写 `require_admin`（租户公司管理员可过）。测试把这当成成功合同。  
2. **平台目录写隔离缺口**（FR-06 配套）：`capability_assets.tenant_id` 有列、非 `TenantMixin`、未进豁免 → 租户态 Core UPDATE **0 行**。  
3. **入队丢租户 + LLM 套餐未闸**（FR-09/10）：HTTP `/run` 传 `tenant_id`；调度/模板/AI 试采走门面 **不传**；`check_llm_tokens_month` 只有单测在调，规划器走全局 `LLM.MAX_TOKENS_BUDGET`。  
4. **采集表被市场征用**（FR-11）：候选住 `spider_results.source=marketplace`，配额 COUNT 全表；且 **017 起该表 `tenant_id` NOT NULL**，不能靠「平台行 NULL」蒙混。  
5. **目录双真相 + 公开闸半套**（FR-13/17/18/31）：`skills` ↔ `capability_assets` 双写；`/public/capabilities` 写死 `status=stable` 丢掉 `recommended`；无 `listing_state`。

产品 D1–D21 不重开。本诊断只判 **模块边界能否托住已冻 FR**。

---

## 2. 现状测绘（Current，复验）

### 2.1 部署单元

```
操作者 / 租户用户 / 匿名官网访客
        │
        ▼
 frontend/admin:9112     frontend/official:9113
        │ /api/v1 JWT              │ /api/v1/public 无鉴权
        ▼                          ▼
 FastAPI create_app() :9111
   lifespan：采集消费者 / 调度 / 代理健康 / LLM 用量 / 评分
            / LLM 巡检 / new-api 调度+探针（失败不阻断）
   /api/* 内部    /external/*  API Key + HMAC
        │               │                 │
        ▼               ▼                 ▼
   MySQL 主库      Redis 队列/锁      外部 new-api
   (platform_core)  scrapy-redis      HTTP 管理面 + 可选 logs 直连
        ▲               │
        │               ▼
        │         scrapy Worker（禁 import backend，R3/B2）
 capability-library/plugins  = 6 条相对 symlink
 .grok/plugins               = 5 条 runtime 链（无 dev-team，与 D20 磁盘一致）
 deploy/newapi/              = 独立 compose，未并入根编排
```

证据：`backend/app/__init__.py`、`backend/app/api/v1/__init__.py`、`scripts/check-arch.sh`（R1–R13 + B1–B3，**无 B4**）、`capability-library/plugins/` 与 `.grok/plugins/` 实盘。

**没有**第四个可部署业务进程。`capability-library/backend/` 8765 退役物 **仍被 git 跟踪**。`skills-library/` 被 `AGENTS.md` 引用，工作区 **不存在**。全库 **零** `POWER_MARKET` / `listing_state` / `capability_installs` / `power_market.yml`。

### 2.2 四柱落点

| 柱 | 代码落点 | 成熟度 vs 冻结 FR |
|----|----------|-------------------|
| 采集 | `scrapy/`；`spider_{task,query,registry,common}`；`tasks/consumer.py`；`api/v1/spiders/`；`ai_planner/` | 主闭环高。FR-09/71 缺口在入队租户与 Worker 空态（Wave 4 主路径，Wave 0 只修租户/配额） |
| SaaS | `tenants` / `members` / `rbac` / `quota_service` / `TenantContextMiddleware` / `tenant_isolation.py` | 行级机制完整。`require_admin` ≠ 平台超管；计费源码已删、pycache 残留；LLM 套餐闸未接线 |
| 中转站 | `api/v1/newapi.py`（文件头写死全部 `require_admin`）；`NewapiApiClient`；`channel_*`；`deploy/newapi/` | 旁路清楚。写权过宽（FR-07）。与规划器 **零引用** |
| 能力/市场 | `capability_assets` + 细节表；`skills` 三表双写；`plugin_service` / `mcp_bridge` / `public_skills.py` | P6 目录有。Source / listing / 安装 / 指针 **均无**。公开双入口（FR-17） |

`backend/services/` 仍是上帝包（40+ 平铺 + `ai_planner/` `llm_common/` `llm_protocol/`；`litellm/` 仅 pycache）。B1–B3 挡不住柱间 import。

### 2.3 本次不动（防蔓延）

- Scrapy 管道与 Redis 队列协议。  
- `platform_core` 不感知业务表名（豁免清单只活在 `tenant_isolation.py`）。  
- new-api 本体不进本仓库。  
- 不合并 `skills` 三表（设计 Non-Goal）。  
- 不拆微服务（无独立伸缩/发布/团队墙）。  
- 不代写 `~/.zcode`（D21）。  
- Wave 2–4 产品面、支付、渠道组 SKU：阻塞于操作者六问。

---

## 3. 问题 / 为什么 / 改进

按冻结 FR 聚类。每条：现状证据 → 根因（边界错在哪）→ 改进（模块与缝，不是代码）。

### 3.1 Wave 0 — 停止说谎 / 停止泄漏

#### P-W0-A 对外合同与可走完路径分裂（FR-01/02/03/05）

| | |
|--|--|
| **问题** | 官网仍卖四柱完整产品：Hero `128,000+` / `3.2 亿条`；功能区写 CSV/Excel；定价三档主按钮全进 `/register`；专业档「工单支持」、企业档「私有技能库 / 中转站渠道组」。注册成功页主按钮是「再注册一家」。 |
| **证据** | `frontend/official/src/pages/Home.tsx`；`FeaturesSection.tsx`；`Pricing.tsx`（三档 `href: '/register'`）；`Register.tsx` 成功态无登录出口，toast「即可登录开始第一次采集」。数据中心导出硬顶 100 条且只有 CSV（`Data.tsx`）；任务导出 csv/json、无 xlsx（`spider_query_service.export_results`）。 |
| **为什么** | 官网与后台是两个前端包，没有「卖点必须绑定可完成动作」的编排者。定价是静态数组，不读套餐/配额。Q-VOICE / Q-PRICE / Q-BILL **未关闭**，但 FR-01 不变式不依赖它们：未履约不得写成当前可买。 |
| **改进** | 官网商店文案归属 **official 前端**，数据以后台真实能力为准。Wave 0 只做删减/预告/改口，**不**新写并列四柱 Hero（等 Q-VOICE）。导出选项与 100 条上限写在按钮上（FR-03）；xlsx 不进本波。专业/企业档主按钮不得再进注册表（FR-05）——出口文案等 Q-PRICE，架构只要求 **与免费注册分路由**。 |

#### P-W0-B 平台写守卫与角色模型裂开（FR-06/07，NFR-05）

| | |
|--|--|
| **问题** | 租户公司管理员（`role=admin`）与平台超管（`is_platform_admin`）在写面上被当成同一类「admin」。任意登录角色可扫插件目录并拉起 stdio MCP。 |
| **证据** | `deps.py`：`require_admin = require_role("admin")`；`require_platform_admin` 已存在且 `/admin/tenants*` 在用。`capabilities.py` 全部 `require_login`。`newapi.py` 文件头「全部 require_admin」。`llm_providers.py` / `skills.py` 写面同。`test_b1c_capabilities_coverage.py` **明文**：viewer 扫描 200、无 403 分支。前端 `Capabilities.tsx` 验证/扫描无 `usePermission`。 |
| **为什么** | SaaS 柱只做了「登录 / 租户 admin / 平台超管」三套助手，能力中心上线时抄了最宽的一套。测试把宽守卫当成回归合同，后续改守卫必红——这是 **合同债**，不是漏写一行 Depends。 |
| **改进** | 平台目录写、渠道窗口写、平台 LLM 写 **一律** `require_platform_admin`（spec §9.2 已冻「不止市场」）。租户 admin 保持成员/本企业配额申请。拒绝时目录/渠道不变 + 审计。前端危险按钮对租户 **隐藏**（§3.2 词表）。**必须同期改** `test_b1c_*` / newapi / llm 写面用例，否则 lint/test 闸门会把正确修复打回去。 |

旧开放问题 Q-AUTH（只收市场 vs 顺带中转/LLM）：**关闭**。产品已选后者。

#### P-W0-C 平台目录表未豁免（FR-06 配套，R13 语义盲区）

| | |
|--|--|
| **问题** | 租户态对 `capability_assets` 的 UPDATE/DELETE 被注入 `tenant_id = 当前租户`，平台行恒 NULL → 0 行。扫描/治理「成功」但不落库。SELECT 不过滤（非 Mixin），租户能读全量目录。 |
| **证据** | `platform_core/models/capability.py` 手写 `tenant_id`，不继承 `TenantMixin`。`tenant_isolation.py` 豁免了 `skills` 三表，**没有** `capability_assets` 及细节表。注释仍写「清单内唯一功能必需的豁免是 skills」——与资产表列事实矛盾。`tenant_context.py` Core UPDATE：有 `tenant_id` 列且未豁免则注入。`test_saas_isolation.py` 只钉 `skills` 豁免 vs `spider_tasks` 注入，**不覆盖** assets。R13 只校验「声明的豁免已注册」，不校验「该豁免的表」。 |
| **为什么** | 隔离机制按「有 `tenant_id` 列」而不是按「是否 Mixin / 是否平台资产」分类。P6 给资产表加了预留列却忘了走 skills 同一登记。机械闸门默认「清单自洽」= 正确。 |
| **改进** | 平台目录表（assets + 未来 sources/components/aliases）进 `TENANT_EXEMPT_TABLES`。安装表（Wave 1）**禁止**豁免、必须 `TenantMixin`。补回归：租户 token 扫目录 → 403（改守卫后）或平台态才写；租户态 UPDATE assets rowcount=0 的夹具在豁免修复后要翻成「可写仅平台态」。不要给 `CapabilityAsset` 加 Mixin 当租户资产——与「平台级公共资产」相反。 |

#### P-W0-D 定时 / 模板 / AI 试采丢租户（FR-09）

| | |
|--|--|
| **问题** | 只有 `POST /spiders/run` 把 `user.tenant_id` 传入队。调度、模板、AI 试采三条产任务路径不传，配额并发闸被跳过；在租户态还可能被 `before_flush` 断言打死，在无上下文的调度循环会把 NULL 打进 NOT NULL 列。 |
| **证据** | `spiders/tasks.py` `enqueue(..., tenant_id=user.tenant_id)`。`SpiderService.enqueue` **没有** `tenant_id` 参数，只转发 name/params/priority。`schedule_service._fire` → `SpiderService.enqueue(...)`，调度器无 `tenant_scope`，计划行自身有 `tenant_id` 却不用。`create_task_from_template` 同。`ai_planner/orchestrator._execute_test` 同。`spider_tasks.tenant_id` 迁移 **017 收紧 NOT NULL**（`llm_providers` 除外）。`TenantMixin.before_flush`：有租户上下文且新行 `tenant_id` 不匹配 → `ValueError`。 |
| **为什么** | 门面 `spider_service` 在拆分子服务时丢掉了租户参数；调度/AI 是 lifespan 后台，不经过 JWT 中间件，调用方以为「计划属于租户」会自动遗传。数据所有权在任务表，触发器在平台进程——缝在「谁是任务的租户」。 |
| **改进** | 采集域独占入队：`SpiderTaskService.enqueue` 为唯一写口；调度从 `SpiderSchedule.tenant_id` 传入；模板/试采从当前用户传入。门面若暂留，必须转发 `tenant_id`，否则新调用方永远漏。配额 `check_task_concurrency` 在 `tenant_id is not None` 才跑——修转发后闸才生效。R12 白名单消费者（`schedule_service` / `ai_planner` / `consumer`）是改造点，不是再扩门面。 |

#### P-W0-E LLM 套餐数字与真调用脱钩（FR-10）

| | |
|--|--|
| **问题** | 套餐写 20 万 tokens，真调用不走 `QuotaService.check_llm_tokens_month`。规划器有另一套全局预算。 |
| **证据** | `check_llm_tokens_month` 定义在 `quota_service.py`；生产引用仅 `test_saas_quota.py` / `test_saas_byok.py`。`llm_chat` 用 `LLM.MAX_TOKENS_BUDGET`（默认同样 200000，**不是** `tenants.quota`），`record_usage` 会带 `current_tenant_id()`。技能评分同样不调套餐闸。 |
| **为什么** | 计量（用量落 Redis/表）与执法（套餐拒绝）做成了两条叶子。数字碰巧相同，联调看起来「有配额」。跨租户时全局预算还会让 A 的消耗挤占 B（或反过来都不挤占套餐）。 |
| **改进** | LLM 运行时叶子在 `llm_chat` 成功路径前调租户套餐闸（无租户则跳过，与并发闸对称）。中转站 **不要**变成这道闸的 backend（Q-LLM 未决；见 §7）。市场验证抽样若走模型，同样过闸，不得另开第四条计数。 |

#### P-W0-F 市场候选占结果配额、混进采集成果（FR-11）

| | |
|--|--|
| **问题** | 候选与采集结果同表。配额按租户 COUNT 全表。列表在 Python 滤 `extra.review`。 |
| **证据** | `skill_service.list_candidates`：`select(SpiderResult).where(source=="marketplace")` 全表再切片。`approve_candidate` 写回 `extra`。`quota_service.check_result_storage` 无 `source` 过滤。`consumer` 落库前按消息 `tenant_id` 做存储闸，不排除 marketplace。`scrapy/spiders/skill_harvester.py` 遵守 B2（运输对、所有权错）。`spider_results.tenant_id` **NOT NULL**（017）。 |
| **为什么** | 候选被建模成「又一次爬取结果」。check-arch 绿，因为没有跨包 import。共享表双方写 = 假边界（见 boundary-derivation「两模块共享表且都写」）。 |
| **改进（材料，本波不锁 ADR）** | 产品只要「不计配额、不出现在我的结果、租户拖不走」。**做不到**「本表 `tenant_id` NULL 当平台行」——除非先 DDL 放宽（破坏性，expand-contract，超出 Wave 0 下限）。可选：**(i)** 仍住此表：写侧继续采集 consumer 独占；读侧/配额 `source <> 'marketplace'`；超管候选 `platform_scope` + SQL 分页，禁止全表进 Python；候选挂在触发者或平台占位租户上（产品不暴露）。**(ii)** 迁出自有表（旧选项 B）。塑形帽在 Q-CAND 二选一；**禁止**再写「NULL tenant_id 落 spider_results」——那是 stale ADR-0013。 |

#### P-W0-G 超限文案与内部码泄漏；时区未标明（FR-12/16）

| | |
|--|--|
| **问题** | 用量页帮助写 `429 QUOTA_EXCEEDED`。70%/90% 只有 Progress 颜色，无「下一步」。无时区标注。调度用 `datetime.now()` 本地时钟。 |
| **证据** | `frontend/admin/src/pages/Usage.tsx`。`QuotaExceededException` `code="QUOTA_EXCEEDED", status_code=429`。`schedule_service.py` 约定「本地时间」。全库无 `Asia/Shanghai` 业务日封装。 |
| **为什么** | 后端把业务码当 API 合同；前端把码展示给用户。统计窗口从未当产品口径。 |
| **改进** | API 可保留内部码；用户可见层用 FR-12 词表。用量页区分三维度 CTA。统计与调度的业务日统一 Shanghai——实现细节归塑形，本诊断只要求 **单一日历规则**，禁止仪表盘与用量各算各的。 |

#### P-W0-H 管理详情泄漏路径；密钥进 git（FR-13/14）

| | |
|--|--|
| **问题** | 任意登录可读 `file_path`。公开发布树含可连上游的明文 Key。 |
| **证据** | `capabilities.get_capability_detail` 投影含 `file_path`。公开技能详情 404 未发布（`public_skills.py` + `test_skill_public_api.py`）——这条 **已经对**。`git ls-files deploy/litellm/config.gen.yaml` 命中；文件内 `sk-` 明文。`capability-library/backend/` 仍跟踪。 |
| **为什么** | 管理详情当内部调试协议用。生成配置自称为 gitignore，根 ignore 未登记（sre P0）。 |
| **改进** | 管理详情对非平台超管不回传本机路径；公开面保持「未发布=不存在」。密钥移出跟踪并轮换（sre）。8765 残骸与 `skills-library` 幽灵目录：Wave 0 卫生票，不挡 FR-06。 |

#### P-W0-I 零产品事件，北极星无法判定（FR-15/30）

| | |
|--|--|
| **问题** | 全库无 `official_page_viewed` / `task_completed` 等事件名。WACT / 注册→登录 / 订阅漏斗不可测。 |
| **证据** | 对 `official_page_viewed|product_event|track_event` 的 py/ts 检索为空。 |
| **为什么** | 审计日志按操作者留痕，不是漏斗分母（analyst 已禁混用）。 |
| **改进** | 单体内加 **产品事件** 叶子（谁调用：官网/后台/API 编排；独占：事件追加与按时间查询）。失败不得挡主路径。表结构归 dba。**QA-02 仍 open**：FR-15 GWT 尚未写清 WACT 排除字段——塑形不得发明 `is_marketplace_candidate` 是否存在；先逼 PM 补 GWT 或改蓝图。 |

#### P-W0-J 平台出站 Key 无租户维（spec QA-12，非本帽代决）

`/external/v1/data/{spider_name}` 的 `X-API-Key` 命中平台配置名单即拉数，无租户绑定。T-06 把租户自助 Key 放到 Wave 2。这是 **产品规则缺口**（默认全拒绝 / 绑定租户 / 写入范围外）。架构只指出：外部面今天是平台后门，与 FR-08 精神冲突；不在本文件选分支。

---

### 3.2 Wave 1 — 能力市场（D1–D21 用户可见行为）

#### P-W1-A 商店不是市场（FR-17…21, 28, 31）

| | |
|--|--|
| **问题** | 双广场导航；公开能力列表丢掉 recommended；无上架三态、无订阅、无搜索短名合同。 |
| **证据** | `SiteLayout.tsx`「技能广场」「能力广场」。`public_list_capabilities` `status="stable"`；`test_b1c_capabilities_coverage.py` 把「仅 stable」写成合同。`public_list_skills` 用 `PUBLISHED_STATUSES` 但 **先分页再内存滤**，`total=len(published)`。无 `/tenants/me/installs`。 |
| **为什么** | P6 把「发布态」当成「商店可见」。设计 D6 把上架从 `status` 拆出后，代码与测试仍焊在旧语义。两个公开端点两套闸 = 双真相。 |
| **改进** | 公开协议只留「能力市场」一条读模型（资产表 + 上架∩治理∩许可）。旧 `/public/skills` 转调或 301，禁止两套过滤。第一方已发布在闸门切换时回填已上架（FR-31），第三方保持未上架（D7）。列表过滤进 SQL，禁止页内滤。安装表是 **第一张「租户拥有、指向平台资产」的跨柱表**：SaaS 提供 `tenant_scope`，市场提供资产身份，安装行不得进豁免清单。 |

#### P-W1-B Source / Catalog / Runtime 三层已糊（FR-22/25/26/27，D1/D16）

| | |
|--|--|
| **问题** | 扫描根是 6 条 symlink 森林；runtime `.grok/plugins` 5 条人工链；设计要 `pointers/` + 源注册表。`scan_library` 按第一方磁盘目录标 missing，会把 D4 提升的第三方 child 标丢并 `_write_back_meta` 写源树。无 MCP ⇒ `health_status=degraded`（测试钉死），与「可 listed」冲突。 |
| **证据** | `capability-library/plugins/README.md` 仍教 `ln -s`。实盘 6 链；`.grok/plugins` 无 `dev-team`。`skill_service.scan_library` `missing_names = existing - dir_names`；`_write_back_meta` 无 `writable`。`plugin_service.verify_plugin` 无 MCP → degraded；`test_b1c` 文档合同。CONTEXT：「未经 verify 不得分发」。 |
| **为什么** | Catalog 用 runtime 布局当扫描根。ADR-0001 把验证等同分发。技能扫描假设「磁盘目录 = 全部技能身份」。 |
| **改进** | 三层不可混（应升 ADR-0011，由塑形写）：Source 外部树；Catalog DB + 指针；Runtime 仅显式 enable-host。入站适配器进 `backend/services/power_market/`（设计已写对），出站留 `capability-library/adapters/`（D8）。`scan_plugins(root=)` 在 `ENABLED=false` 保持今日行为（D16），避免砸 `test_b1c` / `test_mcp_bridge`。ADR-0001 **必须 superseded**（listed ≠ verify ≠ enable-host；无 MCP ⇒ `unknown`）——CONTEXT 那一行与 GWT-26.2 双源，QA-10 仍 open，塑形写 ADR 时点名 supersede，不静默改枚举。 |

#### P-W1-C 身份与 Job 表（FR-19/27，D3）

保持类型内全局 `name` + child `{plugin}__{local}`（D3），不改 `uq_asset_type_name_alive`。`src_sync` 短码可进现 `SkillJob.job_type VARCHAR(16)`；是否永久复用 = Q-JOB。插件重名 `parse_error`、不静默改名（D12）。

#### P-W1-D XSS / host_compat / 只读订阅（QA-03/04/05）

技能广场已有纯文本 XSS 测试（`SkillsSquare.test.tsx`）。迁市场时 **禁止丢掉这条合同**。host 与 `host_compat` 不匹配、只读成员能否订阅：spec 自相或未冻，**本帽不选**。塑形若写合同，只能引用 PM 补丁后的 GWT。

---

### 3.3 跨波结构债（本波只挡新耦合，不搬完）

| 问题 | 为什么 | 改进 |
|------|--------|------|
| 上帝包 `backend/services` | B1–B3 只约束子项目，不约束柱 | 新建 `power_market/` + **B4** import 闸（禁止 import `spider_*` / `newapi_*` / `ai_planner` / `channel_*`）。不一次性搬 `domains/` |
| R10 只扫 `services/*.py` 一层 | 子包无入口日志也能过 CI | 扩到 `services/**/*.py`（与 B4 同闸） |
| R12 门面 6 个域外消费者 | 调度/AI 仍经门面丢租户 | Wave 0 修转发；不在市场 PR 拆门面 |
| LLM 三套叙事 | 规划走 `llm_providers`；中转旁路；LiteLLM 源码删、测试仍写「将被替换」 | 市场一期禁止把 `mcp_bridge` 扩成工具面。Q-LLM **不选** |
| new-api logs SQL | 第二出站缝，绕过 HTTP 反腐 | 与市场无关；SRE 盯；市场 PR 不改 |

---

## 4. 目标依赖方向（材料，非本波 ADR）

```
官网 / Admin
    ▼
编排 API（协议+守卫，不 import ORM，R7）
    ▼
【SaaS】租户/配额/成员/事件     【采集】任务/结果/规划
    │                              │
    │         候选端口（只读或投影） │
    ▼                              ▼
【Power Market】Source/Catalog/listing/installs
    ├──► 【MCP 桥】叶子（仅验证）
    └──► 出站适配器 capability-library/adapters
    ▼
【LLM 运行时】叶子（ADR-0006）
【中转站】ACL+巡检（旁路；是否成为 LLM backend = Q-LLM，人决）
```

规则：编排者知道流程，能力不知道自己被谁用。采集不知道市场。市场不写采集业务字段（若候选暂留，采集 consumer 仍独占写）。中转不被规划器直接 import。`platform_core` 只依赖 `config`（B1）。

模块三问（Wave 1 市场包）：

| 问 | 答 |
|----|----|
| 谁调用 | Admin 治理台、官网商店、scan 回退、租户 installs |
| 独占 | Source 注册、listing、origin 解析、指针、bundled 提升、公开闸 |
| 重写谁碎 | `/public/capabilities`、能力中心 UI、ADR-0001 验证按钮 |

拆微服务：否决（无拆分信号）。按 Controller/Service 切市场：否决（变更横切）。本期搬 `domains/`：否决（超 50% 重判）。

---

## 5. 可行性预检（读码，不是画图）

| 假设 | 怎么验证 | 结论 |
|------|----------|------|
| 单体内能放下市场 | 已有四类资产 + `/public/capabilities` + `Capabilities.tsx` | 成立；缺 Source/listing/installs 缝 |
| 不改唯一键能消化重名 | D3 前缀；现 `uq_asset_type_name_alive` | 成立；代价丑 slug + alias |
| 租户隔离能表达「平台目录 + 租户安装」 | skills 豁免先例；安装表用 Mixin | 成立，**必须先补 assets 豁免**，否则 listing PATCH 租户态 0 行 |
| 爬虫不 import backend 仍能供市场 | `test_skill_harvester.py` | 运输成立；所有权不成立 |
| FR-11 用 NULL tenant_id 表达平台候选 | 017 `spider_results.tenant_id` NOT NULL | **不成立**。须过滤或迁表，禁止 stale ADR-0013 |
| 改守卫不改测试能过 CI | `test_b1c` viewer 扫描 200；公开能力「仅 stable」 | **不成立**。守卫/闸门与测试合同必须同 PR |
| new-api 可继续旁路 | 规划器零引用 `NewapiApiClient`；`NEWAPI.ENABLED` 默认 false | 市场不阻塞中转；FR-07 仍要收权 |
| check-arch 能保护新边界 | 无域级规则；R10 一层；R13 不查漏豁免 | 必须加 B4 + R10 递归 + 豁免漏登夹具 |
| 8h 做完四柱 | 设计自身 9+1 PR；spec 已否定 | **不成立** |
| Wave 0 区间 2–4 人周 | 见 §6 | 上限紧，FR-15 与测试合同改写是 overrun 点 |
| Wave 1 区间 8–16 人周 | 见 §6 | 枢纽扩展成立；拆服务或合并三表不成立 |

无外部新技术。git clone → CACHE_DIR 常规。Kimi 路径仅 local overlay。

---

## 6. Appetite 校准（替换 spec「pending architect」）

人周 = 一人专注实现+自测+改测试合同，不含 PM 补 findings 的等待。超出单波上限 50% → 停下重判。

| 波 | spec 区间 | 本诊断 | 主要工作 | overrun 触发 |
|----|-----------|--------|----------|--------------|
| Wave 0 | 2–4 | **3–4**（取上限仍必须做完权限与一致性） | 官网改口 FR-01…05；守卫 FR-06/07 + 重写 b1c；豁免 FR-06；入队租户 FR-09；LLM 套餐闸 FR-10；候选过滤/配额 FR-11；文案 FR-12；路径/密钥 FR-13/14；薄事件 FR-15 | FR-15 做成数仓；Q-CAND 选新表并在 Wave 0 做完；不改测试只改守卫 |
| Wave 1 | 8–16 | **10–14** | 源同步+指针；listing/许可/alias；公开闸+搜索；租户安装；治理台；第一方 listed 回填；ADR-0001 superseded | 代写宿主配置；开发者门户；合并 skills 三表；ENABLED 默认 true 砸旧扫描测试 |

Wave 2–4 仍 pending 操作者六问，本帽不估死。

---

## 7. 开放问题

### 7.1 本帽关闭（不再问）

| ID | 关闭为 | 依据 |
|----|--------|------|
| Q-AUTH（旧诊断） | Wave 0 **同时**收紧市场写 + 中转写 + 平台 LLM 写 + 技能库扫描写 | spec FR-06/07、§9.2 |
| Q-SCOPE（旧诊断） | 本特征是程序：Wave 0+1 冻结交付，不是 8h 四柱 | spec §0 |

### 7.2 禁止本帽代选（操作者）

Q-VOICE、Q-PRICE、Q-RELAY、Q-MARKET-USER、Q-BILL、Q-LLM。

架构约束（不是答案）：Q-LLM 未决期间，市场不得把 `mcp_bridge.call_tool` 扩成通用工具面；规划器继续只见 `LlmRuntimeConfig`。Q-RELAY 未决期间，不新造租户渠道组屏（FR-60），但 FR-07 写权已冻。

### 7.3 交给塑形帽（架构，本文件只给约束）

| ID | 问题 | 约束（已从代码核实） | 建议材料（非决定） |
|----|------|----------------------|--------------------|
| **Q-CAND** | 候选迁表 vs 过滤留在 `spider_results` | 不能用 NULL `tenant_id`；全表 Python 滤不合法 | Wave 0 用 source 过滤即可证伪 FR-11；迁表放到「候选要独立生命周期」第二次 |
| **Q-SYMLINK** | 切源前是否收回 6 条 catalog 链 | 实盘已是 6+5；README 仍教 ln -s | Wave 1 指针与旧根隔离；D16 回退承认森林为库存，不在 Wave 0 删链 |
| **Q-B4** | 域 import 闸是否进本特征 lint | 现闸无域规则 | **推荐做**（否则 A 腐烂）。只约束新包 |
| **Q-ADR-HOME** | ADR 落点 | `docs/adr/` 不在仓库；`02-shape/adr-*` 已 stale | 可审路径：`.sdlc/feat-four-pillars/02-shape/`；重写而非在 stale 上打补丁 |
| **Q-JOB** | `src_sync` 是否永久住 `skill_jobs` | `VARCHAR(16)` 装得下短码 | 一期复用；二期再拆表 |
| **Q-HARVEST-SCOPE** | 入站任务平台级 vs 租户 | 结果表 NOT NULL | 并入 Q-CAND；不要单独承诺 NULL 行 |
| **Q-8765** | 是否本波删退役后台 | 仍被 git 跟踪 | 与 FR-14 卫生同票；不挡市场 |

### 7.4 回 PM、塑形不得发明

QA-02（FR-15 WACT 字段）、QA-03（host_compat）、QA-04（只读订阅，权限矩阵自相）、QA-05（市场 XSS GWT）、QA-06（「测试中」矩阵列）、QA-07（租户能否 **看** 渠道页）、QA-08（AGPL）、QA-09（首页精选失败装空）、QA-10（CONTEXT vs listed）、QA-11（护栏两份清单）、QA-12（平台出站 Key）。

---

## 8. 需要的 ADR（塑形写；本文件只列不可逆点）

| 编号 | 决策 | 否决项 | 为何不可逆 |
|------|------|--------|------------|
| 0001 superseded | listed ≠ verify ≠ enable-host；无 MCP⇒unknown | 维持「未验证不得分发」（Kimi 无法上架） | CONTEXT + 文案 + health 枚举 + test_b1c |
| 0010 四柱拓扑 | 单体 + `power_market` 子包 + B4 | 市场微服务；按 Controller 切；本期搬 domains/ | 目录与 import 闸 |
| 0011 三层 | Source / Catalog / Runtime | 继续扩 symlink 当目录 | 已 6+5 条链 |
| 0012 身份 | 保持全局 name；child 前缀 | `(source,name)` 改唯一键 | D3；破坏性收缩 |
| 0013 候选所有权 | 过滤留表 **或** 自有表；**禁止** NULL tenant_id 方案 | 继续双方写 extra 当状态机 | 表所有权会焊前端 Tab |
| 0014 LLM 数据面 | 规划器只走 llm_providers；new-api 旁路；mcp 一期仅验证 | 静默第四条调用链 | 测试已埋 LiteLLM 雷；G1 人决 |
| 0015 租户×目录 | 目录豁免；安装表禁止豁免；写面平台超管 | 给资产加 Mixin 当租户资产 | 漏登=0 行；错豁免=跨租户安装 |

G1–G4（换 LLM 网关 / 拆服务）：只备材料，人决。

破坏性路径：无 drop/rename。加列+新表 expand-contract。`/skills` → 市场筛选是对外合同。

---

## 9. 数据语义诉求（给 `/dba`，不写表结构）

与上一稿 §8 相同的实体诉求（Source / Catalog asset / Component / Tenant install / Alias / 可选 Candidate），外加：

- `spider_results` / `spider_tasks` **不能**靠 NULL `tenant_id` 表达平台入站。  
- 若选过滤方案：必须有访问模式「平台态 `source=marketplace` + review 分页」，禁止全表 + Python。配额 COUNT 排除该 source。  
- 安装表是跨柱 FK：隔离测试覆盖租户 A 不见 B；纯平台超管无企业空间订阅 → 拒绝（FR-20.3）。  
- 第一方 `source_id` NULL 不参与同步唯一键（MySQL NULL 语义用夹具钉死）。

---

## 10. 风险

| ID | 风险 | 缓解 |
|----|------|------|
| R-A | 租户态扫描静默 0 行（P-W0-C） | 豁免 + 守卫同 PR |
| R-B | 登录用户触发 MCP stdio | `require_platform_admin`；b1c viewer→403 |
| R-C | scan_library 标 missing 并写盘 | D5 守门；promote 后 scan 仍 ok 的夹具 |
| R-D | symlink 森林 + D16 双轨 | 指针与旧根隔离；测试 overlay |
| R-E | 改闸门不改测试，CI 把修复打回 | 测试合同与守卫同票（pitfalls） |
| R-F | stale ADR-0013 被当成已决 | 塑形重写；本诊断否决 NULL 行方案 |
| R-G | FR-15 字段未冻就落库 | 等 QA-02 |
| R-K | 候选打满存储配额 | Q-CAND 过滤或迁表 |
| R-J | R10 不扫子包 | 扩 glob |
| R-L | 8765 / 密钥跟踪 | FR-14 + 卫生 |

---

## 11. Rabbit holes（不深挖）

| 坑 | 本期边界 |
|----|----------|
| `backend/services` → `domains/` | 只新建 `power_market` + B4 |
| 合并 skills 与 capability_assets | Non-Goal |
| 代写宿主配置 | D21 |
| 自动执行第三方 hooks | 只登记；verify 除外 |
| LiteLLM 替换 new-api | Q-LLM 人决，市场不接 |
| 专家团执行引擎 | CONTEXT 二期 |
| 通用 job 框架 | 短码复用 |
| 计费/分成/门户 | Non-Goal |
| 把 017 NOT NULL 一次性放宽所有采集表 | 与候选问题绑死会炸隔离测试 |

---

## 12. 自检

- [x] 目标依赖有向无环；指出今日共享表与假边界  
- [x] 未写无 FR 锚点的工单；未写 `02-shape/contract.md`  
- [x] 不可逆点列出 ADR 与否决项；G1–G4 不代决  
- [x] 破坏性路径要求 expand-contract  
- [x] 可行性来自读码与测试合同（豁免、守卫、公开闸、017 NOT NULL、b1c、密钥跟踪、6+5 链）  
- [x] 角色裁剪已声明  
- [x] C4 停在组件  
- [x] 无实现代码、无表 DDL  
- [x] 未代选 Q-VOICE/PRICE/RELAY/MARKET-USER/BILL/LLM  
- [x] D1–D21 当 Accepted 约束，不重开  

---

*诊断 refresh 结束。塑形帽只对 Wave 0+1 冻结 FR 出方案与人周；先消化 QA-02 等 spec 缺口，并抛弃 stale `02-shape` 里与 017 冲突的候选 NULL 方案。*
