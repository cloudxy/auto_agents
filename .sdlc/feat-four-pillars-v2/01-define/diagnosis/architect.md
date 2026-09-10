# 架构诊断 · 四柱平台（feat-four-pillars-v2）

> 角色：architect（定义帽诊断，泳道 L4）  
> 日期：2026-09-08  
> 上游：编排器书单 `INPUTS.md`；grok-files 方案与设计；旧程序 `.sdlc/feat-four-pillars/`（`status: superseded`，G-fresh 未过）；宪法 `sdlc.config.yaml` → `project_rule.md`；词汇 `CONTEXT.md`；现码复验  
> 下游：塑形帽写 **本特征** `02-shape/contract.md` / ADR / 契约 / 票。**本文件不是方案书，不是现行合同。**  
> 可行性：读码与测试合同（2026-09-08），不是 C4 空想。本轮未跑 spike（无未验证新技术）。  
> 禁区：不写 `02-shape/contract.md`、不写工单正文、不写实现、不写表 DDL。不代选 **Q-VOICE / Q-PRICE / Q-RELAY / Q-MARKET-USER / Q-BILL / Q-LLM / Q-AGPL**。不重开 Power Market **D1–D29**。

**相对旧程序（`.sdlc/feat-four-pillars/`）**

| 变化 | 处置 |
|------|------|
| 旧 `state.yaml` `status: superseded` | 旧 `02-shape/` **只作输入**。禁止复制为 v2 现行合同、禁止在旧 ADR 文件上打补丁 |
| 旧定义帽 architect.md（2026-09-07） | 边界判断大体仍对；**过期**：只冻 D1–D21、治理台「6 Tab」、Q-CAND 仍开放、QA-02 仍 open |
| 旧 `contract.md` v2.1 + ADR-0010…0018 + T-01…T-16 | **决策**多数可保留（见 §4）；**工件**全部过期（见 §3）。Wave 1 T-17…T-36 只有表、无票文件 |
| grok-files `feat-four-pillars-spec.md` | **v1 / D1–D21**，落后仓库旧 spec **v1.4（FR-33…36 / D22–D29）**。v2 PRD 以即将冻结的 spec 为准，设计权威仍是 `power-market-design.md` 2026-09-07b |
| grok-files `four-pillars-plan.md` | 自称与旧 `contract.md` v2.1 同步 → **同过期** |
| `CONTEXT.md` | 已收 D22–D29 词汇（五类平级、展示≠停用、上架≠verify）。代码仍 `ASSET_TYPES = skill/plugin/expert/expert_team` |

**角色裁剪（给后续塑形 / 实现，不是工单）**

| 角色 | Wave 0 | Wave 1 | 理由 |
|------|--------|--------|------|
| `/pm` | 是（v2 spec 冻结） | 变更流程 | 七问未关前塑形不得发明产品规则 |
| `/dba` | 是（豁免 + 事件实体 + 出站钥匙绑定语义） | 是（源/listing/安装/别名/组件/`capability_commands` + `asset_type` expand-contract） | 不在本文件写 DDL |
| `/backend` `/frontend` `/qa` | 是 | 是 | 守卫、配额缝、商店面；测试合同与守卫同 PR |
| `/designer` | 有限（官网改口） | 是（商店面 + **7 Tab** 治理台：源+目录+五类） | 设计修订已废「最多 6 Tab」 |
| `/sre` `/ops` | 是（FR-14 密钥、编排缺口记风险） | 有限（CACHE_DIR、ENABLED） | 不把 Worker/new-api 并进本波实现票 |
| `/data-collector` | 诊断有限；实现 N/A | N/A | 运输层合规；候选所有权在结果出口，不改 harvester |
| `/algo` `/miner` `/warehouse` | N/A | N/A | 无新模型、无仓；事件进 OLTP |
| `/analyst` | 口径已有蓝图 | 不进实现票 | 不改事件名 |
| `/qc` | 定义帽覆盖缺口 | 塑形后再审 | 本文件不放行 |

---

## 1. 一句话结论

现平台仍是 **单进程 FastAPI + 平行 Scrapy Worker**。四柱已经长在同一套 `backend/services` 里。Power Market「升级 P6 枢纽、不另起微服务」**仍然契合**宪法与现部署。挡住可卖的不是缺容器，而是 **合同被测试钉死成错的正确** + **Catalog 仍是四类、商店仍无 listing/安装**。

旧塑形 **ADR-0010…0018 的决策方向应保留**，整份 **重写进 v2 `02-shape/`**，不要当已过闸合同。必须推翻的只有：候选 `tenant_id` NULL、四类目录、6 Tab 上限、订插件=礼包、unlist=停用、「未 verify 不得上架」、把旧 T-01…T-16 当现行票。

五条破坏半径最大的缝（2026-09-08 复验 **仍在**）：

1. **平台写面过宽**：能力写 `require_login`；技能/LLM/中转写 `require_admin`。`test_b1c` 把 viewer 扫描 200 钉成成功。  
2. **平台目录未豁免**：`capability_assets.tenant_id` 手写列、非 Mixin、不在 `TENANT_EXEMPT_TABLES` → 租户态 Core UPDATE **0 行**。注释仍写「唯一功能必需豁免是 skills」。  
3. **入队丢租户 + LLM 套餐未闸**：门面 `SpiderService.enqueue` 不转发 `tenant_id`；调度/模板/AI 试采不传；`check_llm_tokens_month` 仅测试引用。  
4. **采集表被市场征用**：候选住 `spider_results.source=marketplace`，配额 COUNT 全表；**017 起 `tenant_id` NOT NULL**。  
5. **目录双真相 + 公开闸半套**：`/public/capabilities` 写死 `status=stable`；无 `listing_state` / `POWER_MARKET` / `capability_installs`（全库 **0 命中**）。官网双广场。代码 `ASSET_TYPES` 仍四类，与 CONTEXT 五类平级冲突。

---

## 2. 现状测绘（Current，2026-09-08 复验）

### 2.1 部署单元 — **边界仍对**

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
 capability-library/plugins  = 6 条相对 symlink（含 dev-team）
 .grok/plugins               = 5 条 runtime 链（无 dev-team）
 deploy/newapi/              = 独立 compose，未并入根编排
```

证据：`backend/app/__init__.py`；`scripts/check-arch.sh` 仍是 **R1–R13 + B1–B3，无 B4**；R10 仍只扫 `backend/services/*.py` 一层。`config/` **无** `power_market.yml`。`docs/` 整树不存在（gitignore）。

**没有**第四个可部署业务进程。`capability-library/backend/` 8765 退役物 **仍被 git 跟踪**。`skills-library/` 被 `AGENTS.md` 引用，工作区 **不存在**。Alembic 头修订 **027**（不要写「023/030 之后」）。

### 2.2 四柱落点 — **模块归属仍对，成熟度未变**

| 柱 | 代码落点 | 成熟度 |
|----|----------|--------|
| 采集 | `scrapy/`；`spider_*`；`tasks/consumer.py`；`api/v1/spiders/`；`ai_planner/` | 控制面高。入队租户/配额/Worker 空态仍缺 |
| SaaS | `tenants` / `members` / `quota_service` / `TenantContextMiddleware` / `tenant_isolation.py` | 行级机制完整。`require_admin` ≠ 平台超管；LLM 套餐闸未接线 |
| 中转站 | `api/v1/newapi.py`（文件头写死全部 `require_admin`）；`NewapiApiClient`；`deploy/newapi/` | 旁路清楚。写权过宽。与规划器 **零引用** |
| 能力/市场 | `capability_assets` + 细节表（**四类** `expert`/`expert_team`）；`skills` 双写；`plugin_service` / `mcp_bridge` / `public_skills.py` | P6 目录有。Source / listing / 安装 / 指针 / `command` 行 **均无** |

`backend/services/` 仍是上帝包。B1–B3 挡不住柱间 import。

### 2.3 本次不动（防蔓延）— **仍对**

- Scrapy 管道与 Redis 队列协议；harvester 继续 Redis，不直写主库。  
- `platform_core` 不感知业务表名（豁免清单只活在 `tenant_isolation.py`）。  
- new-api 本体不进本仓库、不并入根 compose。  
- 不合并 `skills` 三表；不改 `uq_asset_type_name_alive`。  
- 不拆微服务；不一次性搬 `domains/`。  
- 不代写 `~/.zcode/cli/config.json`（D21）。  
- 不扩展 per-plugin symlink 森林（D1 / D16 回退承认现链为库存）。  
- Wave 2–4 支付 / 租户渠道组 SKU / 采集执行面：阻塞于操作者七问或独立波次。

---

## 3. 旧合同 / ADR / 票：哪些过期

旧程序定义帽 G-fresh **未过**，塑形稿不得当过闸。分类：

| 工件 | 状态 | 新方案怎么用 |
|------|------|----------------|
| `02-shape/contract.md` v2.1 | **过期作为现行合同** | 作材料：模块表、依赖图、Effort 校准、D→PR 映射。§8 仍写「治理台 6 Tab」→ **与 D22/FR-33 冲突，禁止抄** |
| `adr-0010`…`0018` | **决策可保留，文件过期** | 在 **v2** `02-shape/` **整份重写**（同一决策 + 否决项）。禁止改旧文件、禁止「accepted 打补丁」 |
| `tickets/T-01.md`…`T-16.md` | **过期作为现行票** | Wave 0 缝仍在，分解模式可参考。v2 spec 冻结后 **重新发卡**，不要 resume 旧 id |
| `tickets/T-17`…`T-36` | **从未落盘**（仅合同表） | 合法（FR>20 先表后文件），但表对 FR-34/35/36 锚不足；塑形按 v2 spec 重切 |
| `contracts/*.md` | **过期作为现行契约** | 鉴权映射、公开闸、安装语义可作草稿；须对齐五类枚举与 7 Tab |
| 旧 `01-define/diagnosis/architect.md` | **过期提问** | Q-CAND / Q-AUTH / Q-SCOPE 已在后续稿关闭或选定；不要再问 |
| grok-files `feat-four-pillars-spec.md` v1 | **过期 PRD 副本** | 缺 FR-32…36。以设计 D1–D29 + v2 即将冻结 spec 为准 |
| grok-files `four-pillars-plan.md` / `four-pillars-diagnosis-and-plan.md` | **过期方案/综述** | 拓扑与 P0 缝仍有用。DBA-5「回流 tenant_id 可能 NULL」与 **017 NOT NULL** 不是同一命题：入队丢租户会在真库 **INSERT 失败或挂 default**，不能靠 NULL 表达平台行 |
| `05-review/findings.md` | **审查账本，不是现行 spec** | QA-01…30 在旧 state 标 fixed，但 **未对 v1.4 再跑 G-fresh**。架构约束（只读拒绝、XSS、出站 Key、host_compat NULL=四宿主）应保留；是否写进 v2 FR 归 `/pm` |
| `docs/adr/` | **不存在** | v2 ADR 落 `.sdlc/feat-four-pillars-v2/02-shape/`。CONTEXT 已指向 ADR-0001 修订语义，代码未跟 |

**票级过期细节（塑形不得原样重开）：**

| 旧票 | 问题 |
|------|------|
| T-01 | 清单含 `capability_commands`——**表尚不存在**。Wave 0 只豁免 **已有** 且带 `tenant_id` 的平台表（至少 `capability_assets`）。新表在创建票里同步登记 |
| T-01 ∥ T-02 拆开 | PIT-3：豁免与守卫不同 PR 会出现「扫描 403 了但平台态仍 0 行」或相反。建议同波紧耦合，测试夹具一次交齐 |
| T-33 锚 FR-33 | 五类不只是 Admin Tab：公开枚举、`ASSET_TYPES`、expand-contract `expert`→`agent` 必须进 Catalog/公开 API 票 |
| T-27 标题 | 有订/卸/只读/多宿主，**未写** FR-34「订插件不级联」与 FR-35「unlist 后已订仍在、引用仍解析」 |
| T-18/T-21/T-25/T-27/T-34 粗估 2.5d | 超过「一会话实现+自测+交付」。塑形按会话切开或标明必须拆文件 |
| 合同 §8「6 Tab」 | **作废**。设计审查：顶栏 源+目录+五类 = **7**，旧「最多 6」已废 |

---

## 4. 全新方案必须保留 / 推翻的架构决策

产品 D1–D29 **不重开**（设计 Accepted + 审查 0 open）。下面只判 **架构**。

### 4.1 必须保留（KEEP）— 塑形重写成 v2 ADR，不发明第三套拓扑

| ID | 决策 | 否决项 | 证据（仍成立） |
|----|------|--------|----------------|
| **K-TOPO**（旧 0010） | 单体内域；新建 `backend/services/power_market/`；**B4** 禁止该包 import `spider_*` / `newapi_*` / `ai_planner` / `channel_*`；R10 扩到 `services/**/*.py` | 市场微服务；按 Controller 切；本期搬 `domains/` | 无独立伸缩/发布/团队墙；公开目录体量 ~300 行；B1–B3 绿也拦不住柱间 import |
| **K-3LAYER**（旧 0011） | Source / Catalog / Runtime 不可混。指针 `capability-library/pointers/`，**不**进 `plugins/`。D16：`ENABLED=false` 或 SOURCES 空 → 今日 `LIBRARY_ROOT/plugins` 回退 | 继续扩 symlink；指针写入 `plugins/`；切源前清仓收回 6 链 | 实盘仍 6+5 链；`scan_plugins` 对 `plugins/` `iterdir`；全库无 `POWER_MARKET` |
| **K-ID**（旧 0012） | 类型内全局 `name`；child `{plugin}__{local}`；不改 `uq_asset_type_name_alive`；插件撞名 `parse_error` 不静默改名 | `(source,name)` 改唯一键；同步给插件加源前缀 | D3/D12；51 个短名冲突仍是身份事实 |
| **K-CAND**（旧 0013 **v2**） | 候选仍住 `spider_results.source=marketplace`；采集 consumer **独占写**；配额/「我的结果」/导出 `source <> marketplace`；**tenant_id NOT NULL**（触发者或平台占位租户）；超管列表 SQL 分页；`extra.review` 协议冻结 | 本波建候选表；**NULL tenant_id**；放宽 017；harvester 直写主库；`power_market` import `spider_*` | 017 除 `llm_providers` 外收紧 NOT NULL；`list_candidates` 仍全表进 Python；`check_result_storage` 仍不过滤 source |
| **K-LLM**（旧 0014） | Wave 0/1：规划/评分只经 `llm_chat`→`llm_providers`；调用前 `check_llm_tokens_month`（上海自然月）；new-api 旁路；`mcp_bridge` **仅验证**；LiteLLM 替换不进本特征 | 本波把中转接成规划 backend；把 verify 扩成工具面；切换 LiteLLM | `llm_chat` 仍走 `LLM.MAX_TOKENS_BUDGET`；`check_llm_tokens_month` 仅 `test_saas_quota` / `test_saas_byok`；规划器零引用 `NewapiApiClient` |
| **K-TENANT×CAT**（旧 0015） | 平台目录表进豁免；**不要**给 `CapabilityAsset` 加 Mixin；`capability_installs` **禁止豁免**、必须 `TenantMixin`；目录写 `require_platform_admin` | 每租户一份目录；安装表豁免靠手写 WHERE | `tenant_isolation.py` 仍无 `capability_assets`；CONTEXT 已写恒 NULL |
| **K-EVENTS**（旧 0016） | 产品事件 **OLTP 追加表**；失败不挡主路径；不混 `operation_logs`；不建仓；保留 ≥90 天 | 审计冒充漏斗；本波 ODS；只打日志 grep；上外部分析 SDK | 事件名 grep 仍 0；`operation_logs` 无事件名/匿名访客 |
| **K-AUTH**（旧 0017） | 平台写面 = `is_platform_admin`；租户 admin ≠ 超管；租户 **自有** LLM 行仍经理可写；渠道页对租户 **同 404** 不是道歉 403；登录投影 `is_platform_admin` | 只收市场、中转仍 `require_admin`；租户完全不能进 `/llm`；Wave 0 先做完整 `require_permission` | `require_platform_admin` 已存在且 `/admin/tenants*` 在用；`capabilities.py` 全部 `require_login`；`newapi.py` 全部 `require_admin`；前端 `LoginResponse` **无** `is_platform_admin`；`ProtectedRoute` 认 `role==='admin' \|\| is_admin` |
| **K-LISTED**（旧 0018） | 分发=商店上架；无 MCP ⇒ `unknown` 可 listed；`degraded` 仅「声明了 MCP 但探测失败」；Wave 1 **不**交付 enable-host 按钮/API；生产投影默认关 | 「未 verify 不得 listed」；Wave 1 做完整 PR8；无 MCP 标 healthy | `plugin_service` 无 MCP → 仍 `health_status="degraded"`；`test_b1c` 钉死该合同。CONTEXT 该行 **已**改成「上架是独立闸门」——代码/测试未跟 |
| **K-PR8** | PR8 **缩水**：详情折叠「安装到本机」说明 + snippet；不挂 `POST enable-host`、不建 runtime symlink | 设计原文 PR8 按钮 | FR-26 / D21；与「平台不代启用」同动词 |
| **K-PR-ORDER** | schema（PR1）→ 适配器（PR2）→ child（PR3）→ 治理 API（PR4）→ 安装 API（PR4b）→ Admin（PR5）→ 商店（PR6）… | 先开商店再补闸；先 attach `zcode_local` 再回填 listing | D7/D16/FR-31；`ENABLED` 默认 false |
| **K-BACKFILL** | 仅第一方已发布/推荐 → `listing_state=listed`；**不要**在 schema 迁移里 attach 源 | 迁移里挂 `zcode_local`；第三方默认同步 listed | 设计硬约束 |
| **K-D22…29 架构含义** | 五类平级行（含 `capability_commands`）；公开枚举 `skill\|plugin\|command\|agent\|team`；库内 `expert`→`agent` **expand-contract、不 rename** `capability_experts`；订/卸不沿 `capability_components` 级联；unlist ≠ 停用；`resolve_runtime_refs` 忽略子行 listing、跳过 blacklist/软删 | 四类；commands 只进插件 JSON；订插件=礼包；unlist 拆已订行；UNLISTABLE 连坐子卡 | 设计修订 + 审查废句表；代码 `ASSET_TYPES` 仍四类 |
| **K-PIT** | PIT-1…6 全保留：动态路由注册顺序；守卫与测试同 PR；豁免漏登 0 行；017 NOT NULL；双公开闸；无 MCP≠degraded | 「改 Depends 测试会跟着绿」 | `auto-agents-pitfalls.md` 2026-09-07 核实，现码仍命中 |
| **K-XSS** | 迁市场 **禁止丢掉** `SkillsSquare.test.tsx` 纯文本合同 | 删技能广场时连 XSS 测试一起删 | FR-32 |
| **K-OUTBOUND** | 出站 Key 无单一租户绑定则拒绝（GWT-08.4） | 空 `API_KEYS` 今日全拒当作永久安全；配置字符串钥匙后混拉 | `query_public_results` 仍无 tenant 参数 |
| **K-JOB** | `src_sync` 复用 `skill_jobs.job_type`（`String(16)` 装得下短码） | 本波建通用 job 框架 | 可逆，不必 ADR |
| **K-CAL** | 用量/仪表盘业务日 **Asia/Shanghai** | 仪表盘 UTC、用量本地各算 | `tenant_usage.py` 曾用 utcnow 月（交塑形核对） |
| **K-MENU** | 本程序不改 **后台菜单分组**（侧栏信息架构）；**改** 能力页叶内 IA 与官网导航 | 借市场票重排整个 admin 分组 | 旧 spec T-31；与 7 Tab **页内** 不冲突 |

### 4.2 必须推翻（OVERTURN）— 写进新 ADR 的否决项，禁止回流

| 旧说法 | 为何推翻 | 正确替代 |
|--------|----------|----------|
| 8h 做完四柱 | 体量差一个数量级 | 程序、按波 |
| 候选 / 平台入站行 `tenant_id` NULL | 017 NOT NULL；SQLite create_all 会骗人 | K-CAND |
| 能力资产四类；`asset_type=expert` 对外 | D22；CONTEXT 已改 | 五类；对外 agent/team |
| 治理台最多 6 Tab / 合同 §8「6 Tab」 | 审查已废上限 | 7 Tab（源+目录+五类） |
| `commands/` 不上独立资产 | D26 / FR-36 | `capability_commands` + 独立 listing |
| 订插件获得 bundled | D24 / FR-34 | 安装 API 禁止级联 insert |
| unlist 后不可使用 | D23 / FR-35 | 商店 404/不可新订；已订行与引用仍解析 |
| UNLISTABLE 连坐子卡片 | D25 收窄 D20 | 只挡 `dev-team` **插件行** |
| 「未经 verify 不得分发/上架」 | ADR-0018；Kimi 多数无 MCP | listed ≠ verify ≠ enable-host |
| 平行 `/market` 微服务 | 无拆分信号；设计 Alternatives 已否 | 升级枢纽 |
| 给 `CapabilityAsset` 加 TenantMixin | 与平台公共目录相反 | 豁免 + 安装表隔离 |
| 本波合并 `skills` 与 assets | Non-Goal；破坏全部 `/skills/{name}` | 继续双写，禁止第三份 |
| 把 `mcp_bridge.call_tool` 当 Agent 运行时 | NFR-04；第四条 LLM 链 | 仅验证抽样 |
| 代写宿主配置 / 完整 enable-host | D21 / FR-26 | 折叠说明 |
| 复制旧 `02-shape` 当 v2 合同 | 旧特征 superseded、G-fresh 未过 | 重写 |
| resume 旧 T-01…T-16 为当前票 | 锚的是旧 spec 路径 | v2 spec 冻结后重切 |
| 把 grok-files spec v1 当冻结 FR | 缺 FR-33…36 | 设计 D1–D29 + v2 spec |

### 4.3 目标依赖方向（材料，非本波 ADR 正文）

```
官网商店面 / Admin 治理台
        │
        ▼
编排 API（协议+守卫，不 import ORM，R7）
        │
        ├──► 【SaaS 鉴权/配额/成员】──► 【产品事件】（叶子；失败不挡主路径）
        ├──► 【采集入队/结果出口】──► 候选只读端口 ──► 【Power Market】
        ├──► 【中转站】（NewapiApiClient；本波只收权）
        ├──► 【LLM 运行时叶子】
        └──► 【Power Market】
                  ├──► 【Catalog】（capability_* / skills 双写；五类）
                  ├──► 【MCP 验证叶子】
                  └──► 【租户安装】──► SaaS 隔离（Mixin，禁止豁免）
```

无环规则：**采集不知道市场**；市场 **不写** `spider_results` 业务字段（候选审核留技能/采集侧端口）；中转 **不被** 规划器 import；`power_market` **禁止** import `spider_*` / `newapi_*` / `ai_planner` / `channel_*`。编排者知道流程，能力不知道自己被谁用。

模块三问（Wave 1 `power_market` 包）：

| 问 | 答 |
|----|----|
| 谁调用 | Admin 治理台、官网商店、scan 回退、租户 installs |
| 独占 | Source 注册、listing、origin 解析、指针、bundled 提升、公开闸 |
| 重写谁碎 | `/public/capabilities`、能力中心 UI、验证按钮语义 |

拆微服务：否决。按 Controller 切市场：否决。本期搬 `domains/`：否决。

---

## 5. 问题 / 为什么 / 改进（缝仍在，按柱）

以下不锁 v2 FR 号（`/pm` 尚未冻结 v2 spec）。括号内为旧 spec 锚，便于塑形对照，**不是**授权抄旧 FR 清单。

### 5.1 Wave 0 — 停止说谎 / 停止泄漏

与旧诊断 P-W0-A…J **同一组根因**，2026-09-08 复验未修：

| 缝 | 证据 | 根因（边界） | 改进（模块，不是代码） |
|----|------|--------------|------------------------|
| 官网卖点与可走完路径分裂 | `SiteLayout` 双广场；Hero/Pricing 空头 | 双前端包无「卖点必须绑定可完成动作」编排者 | official 改口/预告；付费 CTA ≠ `/register`（出口等 Q-PRICE） |
| 平台写守卫裂开 | `capabilities.py` `require_login`；`newapi.py`/`llm_providers` `require_admin` | SaaS 三套助手被抄成最宽一套；测试合同债 | 一律 `require_platform_admin`；同 PR 改 `test_b1c` / newapi / llm 写面 |
| 目录未豁免 | `tenant_isolation.py` 无 assets；注释过时 | 隔离按「有 tenant_id 列」注入，P6 忘登记 | 豁免平台目录；安装表反向禁止豁免 |
| 入队丢租户 | 门面不转发；`schedule_service._fire`；`create_task_from_template`；`orchestrator._execute_test` 走门面 | 数据所有权在任务表，触发器在 lifespan | `SpiderTaskService.enqueue` 唯一写口；调度用计划行 `tenant_id` |
| LLM 套餐脱钩 | 生产 0 引用 `check_llm_tokens_month` | 计量与执法两条叶子 | `llm_chat` 成功路径前套餐闸；无租户跳过 |
| 候选占配额 | COUNT 无 source；list 全表 Python 滤 | 共享表双方写 = 假边界 | 过滤留表（K-CAND）；禁止 NULL 方案 |
| 超限码泄漏 / 时区 | 用量页；`datetime.now()` 调度 | 内部码当 UX | 用户层词表；单一上海日历 |
| 详情路径 / 密钥进 git | `get_capability_detail` 含 `file_path`；`deploy/litellm/config.gen.yaml` **仍跟踪且含明文 sk-** | 管理详情当调试协议；gitignore 自称未登记 | 非超管不回本机路径；密钥离树并轮换（sre） |
| 零产品事件 | 事件名 0 命中 | 审计 ≠ 漏斗 | OLTP 事件叶子 |
| 出站 Key 无租户维 | `query_public_results` 只按 spider_name | 外部面是平台后门 | 无绑定则拒绝 |

前端登录投影：后端 `auth_service` 已出 `is_platform_admin`；`frontend/admin/src/services/auth.ts` `LoginResponse` **未声明该字段**。K-AUTH 必须含前端类型与 `ProtectedRoute`。

### 5.2 Wave 1 — 能力市场

| 缝 | 证据 | 根因 | 改进 |
|----|------|------|------|
| 商店不是市场 | 双广场；公开能力仅 stable；无 installs | `status` 兼质量与展示 | 一条公开读模型：listing ∩ 治理 ∩ 许可；SQL 内过滤再分页 |
| Source/Catalog/Runtime 糊 | 6+5 链；README 仍教 ln -s | 扫描根=开发机布局 | K-3LAYER；入站 `power_market/`，出站 `capability-library/adapters/` |
| 代码四类 vs 词汇五类 | `ASSET_TYPES`；官网 Capabilities「四类」 | P6 模型未跟 D22 | expand-contract 枚举 + `capability_commands`；公开 JSON 只出新枚举 |
| 无 MCP=degraded | `plugin_service.py:192`；test_b1c | ADR-0001 旧行 | K-LISTED；与测试同 PR |
| 扫描写盘风险 | `scan_library` missing = existing − dir_names | 磁盘目录=全部技能身份 | 只扫第一方；`writable=0` 禁止写源树 |

### 5.3 跨波结构债（只挡新耦合）

| 问题 | 改进 |
|------|------|
| 上帝包 `backend/services` | 只新建 `power_market/` + B4 |
| R10 一层 | 扩 glob |
| R12 门面丢租户 | Wave 0 转发；不在市场 PR 拆门面 |
| LLM 三套叙事 | 市场禁止第四条链；Q-LLM 人决 |
| new-api logs SQL | 市场 PR 不改 |

---

## 6. 可行性预检（读码，不是画图）

| 假设 | 怎么验证 | 2026-09-08 结论 |
|------|----------|-----------------|
| 单体内能放下市场 | 四类资产 + `/public/capabilities` + `Capabilities.tsx` | **成立**；缺 Source/listing/installs/`command` 缝 |
| 不改唯一键能消化重名 | D3 前缀；现 `uq_asset_type_name_alive` | **成立** |
| 租户隔离能表达「平台目录 + 租户安装」 | skills 豁免先例 | **成立，必须先补 assets 豁免** |
| 爬虫不 import backend 仍能供市场 | harvester 走 Redis | 运输成立；所有权靠结果出口过滤 |
| FR-11 用 NULL tenant_id | 017 `spider_results` NOT NULL | **不成立** |
| 改守卫不改测试能过 CI | `test_b1c` viewer 200；无 MCP=degraded；公开仅 stable | **不成立** |
| new-api 可继续旁路 | 规划器零引用；`NEWAPI.ENABLED` 默认 false | 市场不阻塞中转；写权仍要收 |
| check-arch 能保护新边界 | 无 B4；R10 一层；R13 不查漏豁免 | 必须加 B4 + R10 递归 + 豁免夹具 |
| CONTEXT 已五类则代码已五类 | `ASSET_TYPES` | **不成立**。词汇超前于 ORM |
| 前端已能按超管藏渠道页 | `LoginResponse` / `ProtectedRoute` | **不成立**。缺 `is_platform_admin` |
| 8h 做完四柱 | 设计 9+1 PR | **不成立** |
| `source_type` VARCHAR(16) 装 `marketplace_crawled` | 现列 `String(16)` | **不成立**（19 字符）。属 **放宽** 非收缩，交 `/dba` |
| Alembic 头 027 | `027_spider_tasks_status_varchar.py` | **成立**。禁止写 030_* |

无外部新技术。git clone → CACHE_DIR 常规。Kimi 路径仅 local overlay。

---

## 7. Appetite 校准（候选，待 v2 spec 冻结后塑形落死）

人周 = 一人专注实现+自测+改测试合同，不含 PM 等待。超出单波上限 50% → 停下重判。

| 波 | 旧 spec 区间 | 旧合同 | 本诊断 | overrun 触发 |
|----|--------------|--------|--------|--------------|
| Wave 0 | 2–4 | 3.5 | **3–4**（取上限仍必须做完权限与一致性） | 事件做成数仓；Wave 0 建候选表；不改测试只改守卫 |
| Wave 1 | 8–16 | 11 | **11–14**（D22–D29 不是「改文案」：枚举 expand-contract + commands 表 + 7 Tab + 不级联安装 + unlist 引用） | 代写宿主；开发者门户；合并三表；ENABLED 默认 true 砸旧扫描测试；把 2.5d 票当一会话硬塞 |

Wave 2–4 仍 pending 七问，本帽不估死。

---

## 8. 开放问题

### 8.1 本帽关闭（不再问）

| ID | 关闭为 |
|----|--------|
| Q-AUTH | Wave 0 **同时**收紧市场写 + 中转写 + 平台 LLM 写 + 技能扫描写 |
| Q-SCOPE | 本特征是程序，不是 8h |
| Q-CAND（旧定义帽） | **过滤留表 + NOT NULL**（K-CAND）。迁表等到「候选要独立生命周期」第二次 |
| Q-SYMLINK | Wave 0 **不**收回 6 链；Wave 1 指针与旧根隔离 |
| Q-B4 | **做**（否则市场包必腐烂）。只约束新包 |
| Q-ADR-HOME | v2 ADR 写 `.sdlc/feat-four-pillars-v2/02-shape/`；旧 0010–0018 整份重写 |
| Q-JOB | 一期复用 `skill_jobs` |
| Q-HARVEST-SCOPE | 并入 K-CAND；禁止 NULL 行 |
| Q-8765 | 卫生兔洞，不挡市场 |

### 8.2 禁止本帽代选（操作者）

Q-VOICE、Q-PRICE、Q-RELAY、Q-MARKET-USER、Q-BILL、Q-LLM、Q-AGPL。

约束（不是答案）：Q-LLM 未决期间市场不得把 `mcp_bridge.call_tool` 扩成工具面；规划器只见 `llm_providers`。Q-RELAY 未决期间不新造租户渠道组屏，但写权已冻。Q-AGPL 在中转对外收费前必须先关。

### 8.3 交给塑形（架构约束已写在 §4）

- 票粒度：2.5d 会话切分；T-01 不预登记不存在的表；FR-33…36 必须有唯一归属。  
- 契约：公开 `asset_type` 旧值 `expert`/`expert_team` 读映射一个发布周期、写 400。  
- `source_type` 列放宽。  
- 占位租户语义交给 `/dba`，产品面永不展示其 marketplace 行为「我的结果」。

### 8.4 回 PM（塑形不得发明）

v2 spec 未冻。七问保持开放。host_compat NULL vs 空数组、只读订阅、WACT 排除字段等：若 v2 spec 继承旧 v1.4 则已有句；若重写必须再写清。**本帽不选。**

G1–G4（换 LLM 网关 / 拆服务）：只备材料，人决。

---

## 9. 需要的 ADR（塑形写；本文件只列不可逆点）

在 **v2** `02-shape/` 重写，建议编号仍 0010–0018（或新号但一对一映射），每份含否决项：

| 编号 | 决策 | 相对旧稿 |
|------|------|----------|
| 0010 | 单体 + `power_market` + B4 | 补 D22 五类仍在同一包，不按类型拆服务 |
| 0011 | 三层 + 指针不进旧根 | 不变 |
| 0012 | 全局 name + 前缀 | 命令/智能体同样前缀；不改唯一键 |
| 0013 | 候选过滤 + NOT NULL | **禁止**任何 NULL 回流句 |
| 0014 | LLM 数据面冻结 | 不变；不代选 Q-LLM |
| 0015 | 目录豁免 / 安装禁止豁免 | 新表 `capability_commands` / sources / components / aliases 随创建登记豁免 |
| 0016 | 产品事件 OLTP | 不变 |
| 0017 | 平台超管 vs 租户 admin | 补：前端必须投影 `is_platform_admin` |
| 0018 | listed ≠ verify ≠ enable-host | CONTEXT 已改；supersede 的是 **代码+测试+Admin 文案** |

破坏性路径：无 drop/rename 表。`asset_type` 值域 **expand-contract**（加 `command`/`agent`/`team` → 回填 → 写路径拒旧值）。`/skills` → 市场筛选是对外合同。`source_type` 放宽。禁止手写 Alembic SQL（ADR-0002）。头修订 027。

---

## 10. 数据语义诉求（给 `/dba`，不写表结构）

与旧合同 §7 同族，**加上 D22–D29**：

- 平台目录：五类身份；`listing_state` 三态；`source_id` / `origin_ref` / `writable` / 许可 override / `host_compat`（NULL=四宿主可订，空数组=都不可订）。  
- `capability_commands` 新细节表；`capability_experts` **不改名**。  
- 源 / 组件边 / 别名 / 租户安装（Mixin，禁止豁免，不占三类配额）。  
- 产品事件追加表（UTC naive DATETIME 存储，切日上海）。  
- `spider_results` / `spider_tasks` **不能**靠 NULL `tenant_id` 表达平台入站。  
- 过滤方案：平台态 `source=marketplace` SQL 分页；配额 COUNT 排除。  
- 第一方 `source_id` NULL 不参与同步唯一键（MySQL NULL 语义用夹具钉死）。  
- 现 `capability_assets.source_type` VARCHAR(16) **装不下**设计长枚举 → 放宽。  
- 安装唯一键含 host；unlist 不删安装行。

---

## 11. 风险

| ID | 风险 | 缓解 |
|----|------|------|
| R-A | 租户态扫描静默 0 行 | 豁免 + 守卫同波 |
| R-B | 登录用户触发 MCP stdio | `require_platform_admin`；b1c viewer→403 |
| R-C | scan_library 标 missing 并写盘 | D5；promote 后 scan 仍 ok |
| R-D | symlink 森林 + D16 双轨 | 指针与旧根隔离；ENABLED 默认 false |
| R-E | 改闸门不改测试 | 测试合同同 PR（PIT-2/5/6） |
| R-F | 把旧 ADR-0013 第一版 / grok-files DBA-5 当已决 NULL | 本诊断否决；塑形重写 0013 v2 |
| R-G | 抄合同「6 Tab」砍掉命令 Tab | 7 Tab；FR-36 |
| R-H | 词汇五类、代码四类，公开 API 混 `expert` | expand-contract + 读映射一期 |
| R-J | R10 不扫子包 | 扩 glob |
| R-K | 候选打满存储 | K-CAND 过滤 |
| R-L | 明文 Key 仍在树内 | FR-14 + 轮换（**不要把密钥写入方案正文**） |
| R-M | 旧 T-01 预登记不存在的表 | Wave 0 只登现表 |
| R-N | SQLite 测豁免/唯一键，MySQL 才是 017/生成列真相 | 关键夹具进 MySQL 子集或行为环 |

---

## 12. Rabbit holes（不深挖）

| 坑 | 本期边界 |
|----|----------|
| `backend/services` → `domains/` | 只新建 `power_market` + B4 |
| 合并 skills 与 capability_assets | Non-Goal |
| 代写宿主配置 | D21 |
| 自动执行第三方 hooks | 只登记；verify 除外 |
| LiteLLM 替换 new-api | Q-LLM 人决 |
| 专家团执行引擎 | CONTEXT 二期 |
| 通用 job 框架 | 短码复用 |
| 计费/分成/门户 | Non-Goal |
| 删 8765 / 收回 symlink 森林 | 易变清仓 PR |
| 把 017 NOT NULL 放宽 | 与候选绑死会炸隔离测试 |
| 到期租户登录拒绝 | 旧 miner vs 草稿互殴；**不进 Wave 0** |
| 把 Hero 改写成四柱定位句 | Q-VOICE |

---

## 13. 自检

- [x] 目标依赖有向无环；指出今日共享表与假边界  
- [x] 未写无 FR 锚点的工单；未写 `02-shape/contract.md`  
- [x] 不可逆点列出 ADR 与否决项；G1–G4 不代决  
- [x] 破坏性路径要求 expand-contract  
- [x] 可行性来自 2026-09-08 读码（豁免、守卫、公开闸、017、b1c、密钥跟踪、6+5 链、无 B4、LoginResponse、ASSET_TYPES 四类、POWER_MARKET 0 命中）  
- [x] 角色裁剪已声明  
- [x] C4 停在组件  
- [x] 无实现代码、无表 DDL  
- [x] 未代选七问；未重开 D1–D29  
- [x] 旧合同/ADR/票已标过期 vs 决策 KEEP/OVERTURN  

---

*诊断结束。塑形帽：抛弃旧 `02-shape` 作为现行合同；保留 §4.1 决策并整份重写 ADR；推翻 §4.2；Wave 0/1 仍落在现单体。先等 v2 spec 冻结后再发卡，禁止 resume 旧 T-01…T-16。*
