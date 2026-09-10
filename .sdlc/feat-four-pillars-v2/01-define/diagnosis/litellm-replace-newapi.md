# LiteLLM 替换 new-api · 定义帽输入方案（feat-four-pillars-v2）

> 角色：architect（定义帽输入，**不是**现行合同）  
> 日期：2026-09-08  
> HEAD：`5d2e600`  
> 上游：操作者关闭 **Q-LLM**（`state.yaml` `operator_decisions`：LiteLLM 替换 new-api，必须重构，先出方案再并入未执行的四柱计划）；`01-define/spec.md` v1.3；`diagnosis/{architect,sre,backend}.md`；`CONTEXT.md`；宪法 `project_rule.md`；现码复验  
> 下游：`/pm` 吸收进 spec（关 QA-31 之外的 Q-LLM 合同句）并冻新 FR；塑形帽重写 `02-shape/contract.md` / ADR-0014 **时必须吸收**。  
> **禁区：** 不写 `.sdlc/feat-four-pillars-v2/02-shape/contract.md`（G-fresh 未过，HATADVANCE）。不改业务代码。不发卡。不写表 DDL。不代选 **Q-VOICE / Q-PRICE / Q-RELAY / Q-MARKET-USER / Q-BILL / Q-AGPL**。  
> **已决、禁止再标待确认：** Q-LLM = LiteLLM 成为 LLM 数据面 / 中转运行时；new-api **退出运行时**（退役路径，不是双通道长期并存）。

可行性：读码 + git 跟踪事实（2026-09-08），不是 C4 空想。本轮未跑 LiteLLM 容器 spike（镜像 tag 留给 `/sre` 钉死，不在本文件代选版本号）。

---

## 0. 给 /pm 的一页（必须并入 spec 的句子）

1. **Q-LLM 已关闭。** spec v1.3 §5「LiteLLM 替换 new-api → 不在本 PRD 选择」与 §9.1 Q-LLM「待确认」作废。替换句改为：平台 LLM 数据面 = **LiteLLM Proxy**；new-api 从运行时退役。  
2. **不得做成 Wave 3 stub。** 现 Wave 3（FR-60/61）阻塞于 **Q-RELAY**（租户产品面），与「数据面切换」不是同一件事。把切换塞进 FR-60 stub = 静默永不做。  
3. **建议新增第一等波次 Wave L（LLM 数据面切换）**，插在 Wave 0 诚实波之后、**不晚于** Wave 1 市场评分开始依赖稳定 `llm_chat` 的时刻。Wave 0 **只做**已冻的密钥离树（FR-14）+ 值班写权（FR-06/07），**不**在 5–7 人周里塞完整切换（会超 appetite 50%）。  
4. 规划 / 评分 / 平台路径聊天 **只**经 `llm_chat`，成功路径前仍 `check_llm_tokens_month`（FR-12）。`llm_chat` 的平台出口从「激活 `llm_providers` / yml」改为 **LiteLLM `/v1/chat/completions`**。规划器 **禁止** import 网关管理客户端（今日已零引用 `NewapiApiClient`，保持）。  
5. 租户 **自有** 供应商（BYOK）**不**经 LiteLLM（FR-06.5 / GWT-06.5 已冻）。Q-RELAY 未关前 **不**发租户虚拟令牌、**不**新造「我的渠道组」。  
6. 明确 N/A：不另起市场微服务；**不把 LiteLLM 并进根 `docker-compose.yml`**（故障域见 §3.2）。backend **禁止**再拿一份 `DB_DSN` 直连网关库。

---

## 1. 现状测绘（Current，2026-09-08）

今日是 **三条叙事、两套未接线资产**，不是「已经在跑 LiteLLM」。

### 1.1 部署单元

```
操作者 / 租户 / 匿名访客
        │
        ▼
 frontend/admin:9112          frontend/official:9113
   /llm（供应商）                定价仍写「中转站渠道组」
   /newapi（值班：总览/探针/事件）
        │
        ▼
 FastAPI :9111
   lifespan：consumer / 爬虫调度 / LLM flush / 评分 /
             LLM 巡检 / new-api 调度+探针（NEWAPI.ENABLED 默认 false；失败不阻断）
   /api/v1/newapi/*   require_admin（≠ 超管）
   /api/v1/llm/*      写面 require_admin
        │
        ├──► MySQL 主库（channel_events / channel_probe_results / llm_providers / llm_token_usage）
        ├──► 平台 Redis（newapi:channel:cfg:{id}、调度锁/状态、LLM 月用量）
        └──► llm_chat ──► 激活 llm_providers 或 yml/env ──► 上游 HTTP
                              ▲
                              └── 规划器 / 试采修复 / 技能评分 唯一入口
                              └── 零 import NewapiApiClient

旁路（默认关）：
  deploy/newapi/  独立 compose + newapi-net
    new-api :3000 + newapi-mysql + newapi-redis（或 SQLite ./data）
    backend 用 localhost:3000；根 compose **未**加入 newapi-net

未成为运行时：
  deploy/litellm/config.gen.yaml   git 跟踪 + 明文上游 Key（7 处 sk- 模式）
  backend/services/litellm/        仅 __pycache__（admin_client/admin_service/exporter/guard/shadow）
  backend/scripts/export_litellm_config.py  树内不存在（生成物头仍自称它）
```

证据：

| 事实 | 路径 |
|------|------|
| new-api 独立编排、不进根 compose | `deploy/newapi/README.md` §1；`docker-compose.yml` 服务仅 mysql/redis/backend |
| 调度/探针在 backend，不在 deploy 目录 | `backend/services/channel_scheduler_service.py`；`channel_probe_service.py`；`config/default/newapi.yml` |
| 调度 **SQL 直连** new-api 库 `logs` | `NEWAPI.DB_DSN` + `_USAGE_SQL`（`channel_scheduler_service.py`） |
| 探针打 `{BASE_URL}/v1/chat/completions` | `channel_probe_service.py` 模块头 |
| 值班 API | `backend/app/api/v1/newapi.py`；前端 `frontend/admin/src/pages/NewApiOps.tsx` |
| 规划只走 `llm_chat` | `ai_planner/llm_client.py` `llm_chat`；`skill_scoring_service.py`；`skill_service.py` |
| 套餐闸未接线 | `check_llm_tokens_month` 仅 `test_saas_quota.py` / `test_saas_byok.py` |
| LiteLLM 生成物在树 | `git ls-files deploy/litellm/config.gen.yaml`；根 `.gitignore` **无** litellm；`git check-ignore` 空 |
| LiteLLM 源码不在树 | `backend/services/litellm/` 仅 pyc；`export_litellm_config.py` 0 命中 |
| 测试已预期替换 | `backend/tests/test_b1c_newapi_channels_coverage.py` L8：「newapi 模块将被 LiteLLM 替换」 |
| 预设文案仍写 new-api | `config/default/llm.yml` `PLATFORM_PRESETS` 末项「中转站（new-api/one-api）」 |
| 词汇仍写 new-api | `CONTEXT.md`「中转站 = 外部 new-api 实例的外挂管控面」 |

**没有** LiteLLM 容器、**没有** `LITELLM.*` yml、**没有** pyproject 依赖。现网「LiteLLM」= 一份误提交的静态 `model_list`（deepseek/kimi 别名），**不是**代理进程。

### 1.2 今日职责分裂（假边界）

| 关注点 | 今日所有者 | 问题 |
|--------|------------|------|
| 上游 Key / 渠道 / 令牌 / 倍率计费 | new-api 内建（未默启） | 与规划零引用；租户产品面未决（Q-RELAY） |
| 窗口用量 → 下线 → 冷却 | backend `ChannelSchedulerService` | 依赖 new-api `logs` 表结构与管理 API 启停语义（status 1/2/3） |
| 真伪探针（10 维指纹） | backend `ChannelProbeService` | 产品逻辑，网关没有等价物 |
| 值班读模型 | backend `NewapiOverviewService` + 本地事件/探针表 | 远端不可达 HTTP 200 + `available=false`（正确降级） |
| 规划/评分调用 | `llm_chat` → `llm_providers` / yml | 可手填 `base_url=http://localhost:3000/v1`，但不是合同路径 |
| 租户套餐 token | `QuotaService`（未接线） | 与 `LLM.MAX_TOKENS_BUDGET` 两本账 |
| 租户 BYOK | `llm_providers.tenant_id=当前` | 必须留下（FR-06.5） |

### 1.3 本次不动（防蔓延）

- Scrapy / Redis 队列协议 / Worker 进程边界。  
- Power Market 包与 B4（市场 **禁止** import `spider_*` / 网关客户端 / `ai_planner`）。  
- 不合并 `skills` 三表；不拆市场微服务。  
- 不代写 `~/.zcode`；不把 `mcp_bridge.call_tool` 扩成工具面。  
- **不**把 LiteLLM Admin UI 当成租户产品（那是 Q-RELAY）。  
- **不**在本文件挑选 Q-RELAY 的 SKU 故事，也不挑选 Q-AGPL 对外收费句。

### 1.4 必须推翻的旧架构句

| 旧句 | 出处 | v2 处置 |
|------|------|---------|
| LiteLLM 替换不进本特征；new-api 保持旁路 | 旧 ADR-0014；architect 诊断 K-LLM | **OVERTURN。** 塑形重写 ADR-0014：数据面 = LiteLLM；new-api 退役 |
| Wave 3 = 中转产品化，数据面可跟着 stub | spec v1.3 FR-60/61 | **禁止。** Wave 3 只留租户可见性（仍 pending Q-RELAY）。运行时切换走 Wave L |
| 调度器直连网关业务库是可复制模式 | `NEWAPI.DB_DSN` | **禁止复制到 LiteLLM。** 用量走网关 HTTP（`/spend` / key info / budget），backend 不再持有网关 DSN |
| 恢复 `backend/services/litellm/*.pyc` 当合同 | 残骸 | **否。** 源码不在树，按新客户端重写 |
| 双通道长期并存（规划走 provider、中转另开） | 旧 K-LLM | 切换窗允许 **短** 双跑；切完 new-api 进程停掉 |

**仍 KEEP（与替换正交）：** `llm_chat` 单入口；套餐闸在调用前；mcp 仅验证；两本账（套餐文案 ≠ 成本熔断）；探针伪装不自动关渠道（GWT-07.6）；渠道页对租户与 404 同形（FR-07.3）；密钥不进发布物（FR-14）。

---

## 2. 目标拓扑

### 2.1 目标运行时（Wave L 完成后）

```
规划 / 试采修复 / 技能评分 / 平台路径聊天
        │  仅 llm_chat
        ▼
 FastAPI
   ├── QuotaService.check_llm_tokens_month（租户套餐，上海月）──► 主库 llm_token_usage
   ├── 租户 BYOK 激活行 ──► 直连该行 base_url（不经网关）
   └── 平台路径（无租户激活行 / 平台公共行）──► LiteLLM Proxy :4000
                                                      /v1/chat/completions
        │
        ▼
 deploy/litellm/（独立 compose，独立网络 litellm-net）
   litellm（钉 tag，禁 :latest）
   postgres（虚拟 Key / spend / 模型配置；LITELLM_SALT_KEY 加密上游凭据）
   redis（限流/路由状态；多副本才必须）
        │
        ▼
   上游官方 / 已授权渠道（Key 只活在 LiteLLM 密钥面，不进 git、不进 backend yml）

值班面（平台超管）
   /api/v1/newapi/*  （expand 期别名）或新前缀 /relay
        │  管理 HTTP，无 DSN
        ▼
   LiteLLM 管理面（模型列表 / key info / spend / 启停或 budget）
        │
        ▼
   本地主库 channel_events / channel_probe_results（探针与窗口事件仍归本平台）

new-api 进程：停止。deploy/newapi 留墓碑文档至清理 PR。NEWAPI.ENABLED 恒 false 后删除读取。
```

### 2.2 容器边界：为什么 **不** 并进根 compose

宪法「独立部署优于耦合」。下列故障域 **同时成立**，足以否决「一张 compose 好看」：

| 域 | 根 compose（mysql+redis+backend） | LiteLLM |
|----|-----------------------------------|---------|
| 数据引擎 | 平台 MySQL 8 | **Postgres**（虚拟 Key / spend 的硬依赖） |
| 密钥域 | JWT / LLM_ENCRYPTION_KEY / Webhook | `LITELLM_MASTER_KEY` + **不可轮换**的 `LITELLM_SALT_KEY` |
| 故障 | 主站挂 ≠ 模型调用挂 | 数据面挂 = 规划/评分全停，但不应拖死 `/health/deep` 的 MySQL/Redis 判定 |
| 回滚 | Alembic 027 链 | 镜像 tag + Postgres 卷；SALT 换了上游 Key 全部不可解密 |
| 伸缩 | 1 个 backend | 网关可单独加副本（此时才需要它自己的 Redis） |

要做的是 **网络契约**（与今日 new-api README §5.2 同构）：backend 容器 `external: litellm-net`，`BASE_URL=http://litellm:4000`。**禁止**容器内 `localhost:4000` 当生产默认。根文件只声明外部网络，不声明 litellm 服务。

反例：并进根 compose → 一次 `compose down` 同时砍主站与数据面；密钥与卷混在同一文件；Postgres+MySQL 升级窗糊在一起。这不是「少一个目录」，是把两个故障域焊死。

### 2.3 切换窗（短双跑 ≠ 产品双通道）

| 阶段 | new-api | LiteLLM | `llm_chat` 平台出口 | 值班 |
|------|---------|---------|---------------------|------|
| 今 | 可启、默认关 | 仅误跟踪 yaml | providers / yml | new-api 管理面 |
| Wave 0 | 保持默认关 | yaml **离树+轮换**（FR-14） | 不变 | 只收权（FR-06/07） |
| Wave L expand | 仍可启作回滚件 | 独立 compose 起来 | flag `LLM.DATA_PLANE=providers\|litellm` | 客户端换 LiteLLM；`/newapi` URL 保留 |
| Wave L contract | **停进程、关端口、文档墓碑** | 唯一数据面 | 只 litellm（BYOK 除外） | 同一 URL 或发别名 |
| 禁止 | 长期「规划走 A、租户走 B」当卖点 | 与 new-api 同时写进定价 | 规划器直 import 网关 | 两套值班页 |

回滚：expand 期内关 flag 回到 providers。new-api 一旦停卷，回滚 = 恢复 compose + 备份（RPO 由 `/sre` 写清单，本帽不估秒数——现网回滚 **未实测**）。

---

## 3. 模块边界

聚类：共享生命周期 = 一次 LLM 调用；共享所有权 = 上游凭据；共享团队 = 平台值班。按能力切，不按 Controller。

### 3.1 模块清单

| 模块 | 一句话职责 | 独占 | 重写谁碎 | 新建/既有 |
|------|------------|------|----------|-----------|
| **LLM 调用叶** `llm_chat` | 发一条 chat，计 token，做重试 | 规划/评分/平台路径的唯一出口 | 采集规划、技能评分 | 既有；改出口 |
| **SaaS 配额闸** | 租户月度 token 是否放行 | `tenants.quota` / `llm_token_usage` | 用量页、FR-12 文案 | 既有；Wave 0 接线 |
| **租户 BYOK** `llm_providers` 租户行 | 本企业自己的上游 | 租户密钥密文 | `/llm` 本企业写 | 既有；**不搬进网关** |
| **LLM 数据面** LiteLLM Proxy | 平台上游路由、虚拟 Key、spend、限流 | 平台上游 Key、模型别名 | 平台路径全部 502 | **新建运行时** |
| **值班编排** backend 渠道服务 | 探针策略、窗口策略、给超管看的读模型 | 本库 `channel_*` 表、Redis 窗口配置 | 值班页 | 既有；**换客户端、删 DSN** |
| **真伪探针** | 10 维指纹 → original/spoofed/offline | 问题集、判定启发式 | 探针 Tab | 既有；采集 URL 改网关 |
| **网关适配叶** | LiteLLM 管理/聊天 HTTP | 不持有上游 Key | 值班 + `llm_chat` 平台路径 | 新建（禁止复活 pyc） |

### 3.2 三问

**LLM 数据面（LiteLLM）**

| 问 | 答 |
|----|----|
| 谁调用 | 仅 backend：`llm_chat` 平台路径、探针采集、值班编排。租户浏览器 **不** 直打 4000（Q-RELAY 未关） |
| 独占 | 平台上游凭据、模型路由、网关侧 budget/rate limit、spend 日志 |
| 重写碎什么 | 平台路径规划/评分；值班渠道列表 |

**值班编排（留在 backend）**

| 问 | 答 |
|----|----|
| 谁调用 | Admin `/newapi`（超管）；lifespan 调度/探针 task |
| 独占 | 窗口配额产品规则、伪装不熔断、本地事件/探针表、Notify |
| 重写碎什么 | `NewApiOps.tsx`；GWT-07.1/07.6 |

**不把探针搬进 LiteLLM：** 10 维指纹是本产品规则（知识截止/reasoning_tokens/逐字缓存），网关没有等价物。探针 **调用** 数据面，不 **成为** 数据面。

### 3.3 依赖方向（无环）

```
官网 / Admin
        │
        ▼
编排 API（不 import ORM）
        │
        ├──► 【SaaS 鉴权/配额】──► 主库
        ├──► 【llm_chat】
        │         ├──► 【配额闸】（先）
        │         ├──► 【BYOK】──► 租户上游
        │         └──► 【网关适配叶】──► LiteLLM（平台路径）
        ├──► 【值班编排】──► 网关适配叶（管理 HTTP）
        │         └──► 【探针】──► 网关 /v1/chat/completions
        └──► 【Power Market】  禁止 import 网关适配叶 / ai_planner / spider_*
```

强制手段（塑形写进 lint，本文件只点名）：

- 已有：规划器零引用 `NewapiApiClient`（保持；换成 `LiteLLMAdminClient` 同样禁止规划器 import）。  
- 将有：B4 把 `litellm_*` / `relay_*` 与 `newapi_*` 并列，禁止 `power_market` import。  
- 禁止：`backend/services/ai_planner/**` import 网关管理客户端。  
- 禁止：新代码 `create_async_engine(settings["LITELLM.DB_DSN"])`。

### 3.4 什么从 backend 搬走 / 留下

| 搬走（不再由 backend 持有） | 留下 |
|------------------------------|------|
| 平台上游 Key 明文/密文作为**调用凭据**（改由 LiteLLM 存；backend 只持 **网关虚拟 Key**） | 租户 BYOK 密文（`LlmSecretVault`） |
| new-api 管理 API 方言（`/api/channel/`、`New-Api-User`、status 1/2/3） | 值班 UX、降级信封、`require_platform_admin` |
| `NEWAPI.DB_DSN` 与 `logs` SQL | `channel_events` / `channel_probe_results`（本平台审计） |
| 把 new-api 当规划 backend 的隐式可能 | `llm_chat` 重试、协议适配器、failover 冷却 |
| `deploy/newapi` 运行时 | 探针启发式、伪装不熔断 |

窗口调度：LiteLLM OSS 已有 key/team budget 与 router cooldown。Wave L **优先把「窗口额度」映射为网关 budget**，backend 调度器降级为「读 spend + 调管理面暂停模型/key」。不要再写一套 SQL 聚合。若网关 API 盖不住「冷却到期自动恢复且不覆盖人工禁用」，**只保留这一条** 在 backend，仍走 HTTP 不走 DSN。

### 3.5 身份与配置 expand-contract（给塑形，不写 DDL）

| 今日 | 目标 | 迁移 |
|------|------|------|
| `channel_id` BIGINT = new-api 渠道 PK | 网关模型/deployment/key 的稳定字符串 | **加列** `gateway_ref`，读双写；禁止原地改类型当一票 |
| Redis `newapi:channel:cfg:{id}` | `relay:channel:cfg:{ref}` 或同等 | 双读旧键一发布周期 |
| `NEWAPI.*` yml | `LITELLM.*` 或 `RELAY.*`（塑形选一名，全仓一处） | 新键；旧键只作 deprecate 读 |
| `/api/v1/newapi` + `menu:newapi` | 实现换血；**URL 至少保留一个发布周期** | 测试已锁 HTTP 语义（`test_b1c_newapi_*`），换客户端不换信封 |
| `PLATFORM_PRESETS` new-api 字样 | 「平台网关」或删该项（平台路径不再靠手填 3000） | 文案随 FR-01 诚实波，不单开卖点 |

`channel_id` 类型是 `/dba` 的 expand-contract，本文件不写 ALTER。

---

## 4. 对用户可见行为的建议（给 /pm 冻 FR）

下列是 **建议句**，不是已冻 FR。Q-VOICE / Q-RELAY / Q-PRICE 未关的句子保持开放。

### 4.1 值班面（平台超管）

| 建议 | 对齐已冻 | 失败/空态 |
|------|----------|-----------|
| 仍有一页值班：总览 / 探针 / 事件。标题可改口，但 **不得** 在 Q-VOICE 未关时写成对外 Hero | FR-07.1 | 网关不可达：**降级说明**（「LLM 网关管理面不可达，仅本地事件/探针」），**禁止**「暂无渠道」装成没配过 |
| 列表来自 LiteLLM 模型/部署，不是 new-api channel | — | 网关空配置：可行动空态「还没有平台模型，去网关登记」，不是加载失败 |
| 改窗口额度 = 超管；租户直打与 404 同形 | FR-06 / FR-07.3 | 越权零落库 |
| 探针判伪装：**看见、不自动关** | GWT-07.6；FR-61 可见性仍可 stub 到 Q-RELAY | 与今日一致 |
| 页上无完整上游 Key | FR-14；租户根本看不到该页 | 超管若见密钥字段仅掩码 |

### 4.2 租户面

| 建议 | 对齐 | 不得写成 |
|------|------|----------|
| `/llm` 仍管 **本企业** 供应商；平台行写控件不出现 | FR-07、GWT-06.5/06.6 | 「整页 404」 |
| **没有**「我的渠道组 / 我的中转令牌」直到 Q-RELAY 关闭 | FR-60、X-SLICE | 定价「渠道组当前可买」 |
| 规划/对话走平台路径时，经 LiteLLM；走 BYOK 时直连本企业行 | 本方案 §3 | 「所有调用都进中转」当已选 SKU |
| 套餐满：已达配额上限 + 申请提升；**不是** `QUOTA_EXCEEDED` | FR-12 | 网关挂了却套用套餐句（GWT-12.5 同类：成本/网关熔断 ≠ 套餐） |

### 4.3 规划 / 评分 / 聊天走哪条网关

| 调用 | 网关 |
|------|------|
| AI 规划、试采修复 | `llm_chat` → 平台路径 **LiteLLM**；若该租户有激活 BYOK → **直连 BYOK** |
| 技能评分 worker | 同上（`usage_dim=skill_scoring` 保留独立预算） |
| 供应商「测试连接」 | 测的是 **该行** 自己的 base_url，不强制套网关 |
| MCP `call_tool` | **仍只验证抽样**，不经 LiteLLM 当 Agent 运行时 |
| 租户浏览器 → LiteLLM:4000 | **本期禁止**（Q-RELAY 未关） |

「聊天」今日没有独立 C 端聊天产品；本句覆盖 `llm_chat` 的全部生产调用方。不要发明第四条链。

### 4.4 建议新增 FR（编号建议 FR-70…，v2 未占用；旧程序 70–73 已声明不进入 v2）

| ID | 用户能做到什么 | 建议波次 |
|----|----------------|----------|
| **FR-70** | 经办在平台路径做规划/评分时，请求进入 LiteLLM；成功/失败可感知 | Wave L |
| **FR-71** | 超管打开值班页看到的是网关侧模型/部署；不可达走 §4.1 降级句 | Wave L |
| **FR-72** | 打开平台后 new-api 端口与进程不在运行时；值班不再依赖 new-api 管理面 | Wave L（退役验收） |
| **FR-73** | 企业负责人仍能保存 **本企业** 供应商；该路径不要求 LiteLLM 存活 | Wave L（BYOK 回归） |
| **FR-74** | 网关挂或平台成本熔断时，文案 **不是** 套餐超限那句 | Wave L（补强 GWT-12.5） |
| **FR-75** | 发布物与 git 跟踪文件无 LiteLLM/上游明文 Key；生成配置不在树内 | Wave 0 已有 FR-14；Wave L 验收网关 env 注入 |

GWT 由 `/pm` 写（每条 ≥3，含空态/越权）。本帽不代写验收格子，避免与 QA-31 返工抢合同。

官网定价 B2「中转站渠道组分配」仍走 FR-01 闭集 B（撤或预告）。**不**因换网关就改成当前可买——那是 Q-RELAY +（若收费）Q-AGPL。

---

## 5. 与 Wave 0/1 冻结集如何并入

### 5.1 冻结集里 **已经** 管中转、但 **不是** 数据面切换的

| 已冻 FR | 替换后仍真 | Wave 0 要做的 | Wave L 要做的 |
|---------|------------|---------------|---------------|
| FR-06 渠道窗口仅超管 | 是（换后端不换守卫） | `require_platform_admin` + 同 PR 改测试 | 客户端换血，守卫不变 |
| FR-07 租户壳 / 直打 404 | 是 | 藏菜单 + 同形 404 | URL 别名期仍同形 |
| GWT-07.6 伪装不熔断 | 是 | 不改探针熔断行为 | 移植到 LiteLLM 调用后仍不自动关 |
| FR-12 套餐闸 | 是；接线点仍 `llm_chat` 前 | **必须在 Wave 0 接线**（与网关无关） | 出口改网关后闸仍在前 |
| FR-14 密钥离树 | **Wave 0 就必须做完 litellm yaml** | 轮换 + 移出跟踪 + ignore + scan | 网关只走 env/secret |
| FR-01 B2 渠道组空头 | 是 | 撤或预告 | 不借切换写成可买 |
| FR-60/61 | 租户产品面仍 stub | 不动 | **不**把 FR-72 塞进 60 |

### 5.2 建议波次（人周 = 实现+自测；不含 PM 等待）

| 波 | 是否冻切换 | 做什么 | 砍什么 | appetite 影响 |
|----|------------|--------|--------|----------------|
| **Wave 0** | 不冻切换 | FR-14 含 `deploy/litellm/config.gen.yaml`；FR-06/07 收权；FR-12 接线；值班仍可对 **关着的** new-api 降级 | 不启 new-api；不写 LiteLLM compose；不改 `llm_chat` 出口 | **不涨** 5–7（FR-14 已在） |
| **Wave L（新，第一等）** | **冻 FR-70…75** | 独立 compose；适配叶；`llm_chat` 平台出口；探针/窗口改 HTTP；值班换血；停 new-api | 租户令牌、渠道组屏、根 compose、DSN、Enterprise Org、1:1 复刻 new-api 分组/邀请码 | **+4–6 人周**（建议写入程序 appetite；超 50% 停下） |
| **Wave 1** | 不承担切换 | 市场仍只经 `llm_chat`；B4 禁 import 网关 | 不把 verify 当工具面 | 11–14 **不涨** |
| **Wave 2** | 无 | 支付仍 Q-BILL | 不把网关 spend 当套餐账单 | 不变 |
| **Wave 3** | **禁止**把切换放这里 | 仅租户可见性（Q-RELAY）；值班伪装可见可留 | 不得再写「中转运行时以后再说」 | 2–6 仍 pending Q-RELAY |

**顺序：** Wave 0（诚实+FR-12 闸）→ Wave L 启动。Wave 1 **可以**与 Wave L 后半并行，条件是 `llm_chat` 签名与套餐闸不变。 **禁止** Wave 1 先接第四条链再等 Wave L。 **禁止**「先做完市场再换网关」把 Wave L 推到程序外。

### 5.3 不得静默做成「Wave 3 stub」的检查句（给 G-fresh / 塑形）

出现任一句 = 合同不合格：

- 「LiteLLM 替换 = FR-60」或写进 Wave 3 索引而不进冻结实现波。  
- 「本程序不改 compose / 不启网关」却把 FR-70 标完成。  
- 只改值班文案、`llm_chat` 仍直连上游、new-api 目录仍当运行时。  
- 双通道（new-api + LiteLLM）写进 Non-Goal 以外的「长期架构」。  
- 用旧 ADR-0014「替换不进本特征」挡操作者已关闭的 Q-LLM。

### 5.4 角色裁剪（Wave L；实现帽再裁）

| 角色 | Wave L | 理由 |
|------|--------|------|
| `/pm` | 是 | 冻 FR-70…；改 CONTEXT 中转站词条；删 spec §9.1 Q-LLM 行 |
| `/architect` | 塑形 | 重写 ADR-0014；B4 扩网关包名；票表 |
| `/backend` | 是 | 适配叶、`llm_chat` 出口、删 DSN、lifespan |
| `/frontend` | 是 | 值班页文案/空态；预设项；菜单 permission 仍超管 |
| `/sre` | 是 | 独立 compose、钉 tag、网络、探活、密钥注入、退役步骤 |
| `/qa` | 是 | FR-70… 与 FR-12.5/07 回归；b1c HTTP 语义 |
| `/ops` | 有限 | 值班 runbook；不指定人名（Q-OPS-DUTY） |
| `/dba` | 语义 only | `gateway_ref` expand；**不**把 LiteLLM Postgres 纳入 Alembic |
| `/designer` | 有限 | 值班降级/空态句；不重排五组 IA |
| `/algo` | N/A | 不改探针阈值、不做评估集 |
| miner / warehouse | N/A | |

---

## 6. 可行性预检（读码，不是「应该能」）

| 假设 | 怎么验证 | 结论 |
|------|----------|------|
| `llm_chat` 已是 OpenAI 兼容 POST `/chat/completions` | `llm_client.py` L293–297 | **成立。** LiteLLM 数据面方言匹配，不必换协议适配器 |
| 规划器未绑死 new-api | grep：`NewapiApiClient` 仅 newapi/channel_* | **成立。** 出口可换 |
| 值班 HTTP 语义可保 | `test_b1c_newapi_channels_coverage.py` 只锁信封/Redis 副作用 | **成立。** 换客户端不换 URL 则测试可迁 |
| 调度 SQL 可原样迁到 LiteLLM | LiteLLM spend 在 Postgres 表，且官方要 `DATABASE_URL` | **不成立。** 必须弃 DSN |
| 现 `config.gen.yaml` 可当生产配置 | 明文 Key、无 compose、无 Postgres | **不成立。** 只能当「曾经有过导出」的罪证；离树 |
| pycache 可 resume | 无对应 `.py`、无 git 历史删除记录 | **不成立。** 重写 |
| 套餐闸已挡住真调用 | 生产 0 引用 `check_llm_tokens_month` | **不成立。** Wave 0 先接线，与 Wave L 解耦 |
| 根 compose 并入更简单 | 双引擎 + 双密钥域 + 独立回滚 | **不成立**（§2.2） |
| 8h / Wave 0 5–7 人周内切完 | 新进程+新库+客户端+探针+退役 | **不成立** |
| LiteLLM OSS 够平台路径 | 虚拟 Key / spend / budget 在 OSS；Org 层级是 Enterprise | **平台路径够用。** 租户 Org 层级绑 Q-RELAY，本期不用 |

无 spike：协议已对齐；不确定的是 **钉哪一个镜像 tag** 与 **spend HTTP 是否覆盖窗口冷却**——塑形第一张票用只读 curl 对官方 OpenAPI 核对，失败则缩小调度器范围，不回退到 DSN。

---

## 7. 风险

| ID | 风险 | 缓解 |
|----|------|------|
| R-KEY | `config.gen.yaml` 7 处明文 Key 已在 git | Wave 0 FR-14：轮换（**正文不写密钥**）+ 移出跟踪 + ignore + CI `git grep` 0 命中。历史 `filter-repo` = 操作者机外拍板，清单要 evidence |
| R-SALT | `LITELLM_SALT_KEY` 不可轮换 | 与 new-api `CRYPTO_SECRET` 同类；生成一次进 secret manager；runbook 写「先导出模型再动 SALT」 |
| R-AGPL | new-api 退役后 AGPLv3 面消失 | **影响陈述、不代选收费故事：** 运行时换成 LiteLLM 后，中转 SKU 不再绑 new-api AGPL 容器条款。LiteLLM 根 LICENSE 为 MIT，`enterprise/` 另授权。Q-AGPL 仍开放：若 Q-RELAY=独立 SKU **且对外收费**，仍须先关 Q-AGPL 才能写「当前可买」——只是条款对象从 AGPL 容器变为「是否动用 Enterprise / 如何陈述 OSS 网关」。Wave 0/1 不收费则 Q-AGPL 仍不阻塞 |
| R-DUALDB | 切换窗最多三套库（平台 MySQL + new-api MySQL + LiteLLM PG） | 窗短；禁止平台 MySQL 兼网关库；new-api 停后剩两套。备份 runbook 分域。**不**把网关 PG 纳入 `scripts/migrate.sh` |
| R-DSN | 把 `DB_DSN` 抄到 LiteLLM | 合同禁止；lint 可扫 `LITELLM.DB_DSN` / `create_async_engine` 对网关 |
| R-FLAG | `SCHEDULER_ENABLED` 今日会写渠道下线 | 先只读 spend，再打开写；回滚 flag **不能**假设渠道状态自动恢复（sre CL-24 仍真，对象换成网关） |
| R-HEALTH | `/health/deep` 仍只有 MySQL+Redis | 数据面挂主站仍 200。Wave L：可选独立 ready（网关 `/health/readiness`），liveness **不**因网关挂杀 API |
| R-BYOK | 一刀切「全部进网关」误伤租户供应商 | FR-73；解析顺序保持：租户激活行 → 否则平台路径网关（不再落到「手填 new-api URL」） |
| R-STUB | 合同写进 Wave 3 | §5.3 检查句；塑形票必须锚 FR-70… 不是 FR-60 |
| R-ENT | 误用 LiteLLM Enterprise 当默认 | Wave L 只用 OSS（Key/team/spend）。Org Admin / SSO / 部分 spend report = 另一决策，绑 Q-RELAY/Q-BILL |
| R-PYC | 实现帽「修复」litellm pyc | 删除残骸；新包名 `backend/services/llm_gateway/`（或塑形命名），不要叫 `newapi` 混三年 |

回滚三类（均未实测，交付清单不得勾「可回滚」除非演练）：

| 类 | Wave L 含义 |
|----|-------------|
| 代码 | 钉 tag；回上一 tag；`/health/deep` 200 **且** 一笔 `llm_chat` 平台路径 |
| 数据 | 平台表只 expand；网关 PG 回卷/备份。SALT 轮换 **不可**当普通回滚 |
| 配置 | `LLM.DATA_PLANE=providers`；`NEWAPI.*` 不再作为正向路径 |

---

## 8. 明确 N/A

| 项 | 为什么不做 |
|----|------------|
| 另起市场微服务 | 与 K-TOPO / 设计 Alternatives 冲突；本替换不创造拆分信号 |
| LiteLLM 并进根 `docker-compose.yml` | §2.2 故障域；只允许 `external` 网络 |
| 把 LiteLLM Python SDK 嵌进 FastAPI 当进程内路由 | 上游 Key 回到 backend 内存，毁数据面边界；用 httpx 打 Proxy |
| 长期双通道产品 | 操作者：退出运行时 |
| 租户虚拟令牌 / 渠道组屏 | Q-RELAY |
| 对外收费故事 / 投诉通道文案 | Q-AGPL |
| 支付与网关 spend 对账 | Q-BILL |
| 1:1 复刻 new-api 用户组/邀请码/倍率 UI | 过载；平台路径不需要 |
| SQL 网关库 | 外部契约不可控（与今日 `created_at` 类型债同类） |
| 恢复 billing_service.pyc / litellm pyc | 幽灵，不当计费已落地 |
| 本文件写 `02-shape/contract.md` / 票文件 | HATADVANCE |

---

## 9. 塑形必须吸收的 ADR / 契约点（本文件不写 ADR 正文）

在 **v2** `02-shape/` 重写，建议：

| ADR | 决策 | 否决 |
|-----|------|------|
| **0014 v3** | 数据面 = LiteLLM Proxy；`llm_chat` 单入口；套餐闸在前；mcp 仅验证 | 规划 import 管理客户端；Wave 0/1 再开第四条链；替换进 Wave 3 stub |
| **00xx 故障域** | LiteLLM 独立 compose + 独立 PG/Redis；根 compose 只挂外部网 | 并进根文件；与平台 MySQL 共用 |
| **00xx 无 DSN** | backend 只 HTTP | `LITELLM.DB_DSN` |
| **00xx BYOK** | 租户激活行直连 | 强迫租户 Key 上传网关（除非日后 Q-RELAY 另开 FR） |
| **00xx 退役** | expand 短双跑 → 停 new-api；`/newapi` URL 一周期 | 永久双通道；无墓碑删目录导致值班 404 无说明 |

契约：值班信封保持 `available=false` 降级（不要改成 500 拖死页）。`NEWAPI_UNREACHABLE` 业务码可 rename 但前端要同 PR。

数据语义给 `/dba`：`channel_events.channel_id` 今日语义 = new-api PK；目标 = 外部稳定 ref。探针表同。**不要**把 LiteLLM 的 Prisma 表写进 `platform_core/models`。

---

## 10. CONTEXT / spec 词汇（给 /pm，本帽不改那些文件）

| 词 | 今日 | 建议改成 |
|----|------|----------|
| 中转站 | 外部 new-api 的外挂管控面 | 平台 LLM 网关（LiteLLM Proxy）+ backend 值班编排；new-api 为已退役运行时 |
| 渠道 | new-api channel | 网关侧模型/部署；用户文案可仍叫「渠道」 |
| 令牌 | new-api 令牌层 | 平台路径 = 网关虚拟 Key（**不发给租户** 直至 Q-RELAY） |

spec §9.1 删除 Q-LLM 行，移入 `closed_questions`。§5 范围外表「LiteLLM 替换」改为「已选：见 Wave L」。QA-31（合集包含闸）与本方案正交，**不要**绑在同一句里修。

---

## 11. 自检

- [x] 依赖有向无环；网关适配叶为叶子；市场/规划不 import 管理客户端  
- [x] 未写 `02-shape/contract.md`、未写票文件、未写实现、未写 DDL  
- [x] Q-LLM 当已决执行，不标待确认  
- [x] 未代选 Q-VOICE / Q-PRICE / Q-RELAY / Q-MARKET-USER / Q-BILL / Q-AGPL；AGPL 只陈述退役影响  
- [x] 可行性来自现码与 git（DSN、零引用、pyc、yaml 跟踪、b1c 预期替换）  
- [x] Wave 3 stub 检查句已写；Wave L 为第一等波  
- [x] N/A：市场微服务、根 compose 合并  
- [x] 破坏性路径要求 expand-contract（URL、Redis 键、channel ref）  
- [x] 角色裁剪已声明  

---

*定义帽输入结束。`/pm`：把 §0 与 §4.4 / §5 并进 spec，关闭 Q-LLM 合同句，Wave L 进波次表（不是 FR-60）。塑形：抛弃旧 ADR-0014「替换不进本特征」；按 §9 重写。禁止 resume litellm pyc 与 new-api DSN 模式。*
