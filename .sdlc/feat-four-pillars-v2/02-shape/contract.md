# 技术方案 · 四柱程序 v2（Wave 0 + Wave L + Wave 1）

> 上游：`01-define/spec.md` **v1.6**（G-fresh 第 7 轮 PASS）+ `user-story.md` + `metrics-blueprint.md` v1.4 + `diagnosis/litellm-replace-newapi.md`
> 特征：`feat-four-pillars-v2`｜泳道：L4｜appetite：W0 5–7 人周 · **WL 4–6 人周** · W1 11–14 人周
> 作者：/architect｜日期：2026-09-08｜版本：**v1.8**
> 冻结施工集：FR-01…20 + **FR-70…75** + FR-30…45。Wave 2/3 stub 不发卡。
> **禁止**：复制旧 `.sdlc/feat-four-pillars/02-shape/`；resume 旧 T-01…T-16；把 LiteLLM 写成 Wave 3 / FR-60；代选 Q-VOICE / Q-PRICE / Q-RELAY / Q-MARKET-USER / Q-BILL / Q-AGPL。
> 本 spawn：合同 + ADR + **票表**。冻结 FR>20 → `tickets/T-nn.md` 第二次 spawn。票号 T-nn 与分诊 DMD-nn 分家。
> v1.1：塑形第一 spawn 独立审查 FAIL，**只关 SH-01…SH-06**。
> v1.2：塑形 v1.1 G-fresh r2 FAIL，**只关 SH-07、SH-08、SH-09**。SH-01…06 保持 closed。不重开定义帽 QA-01…37。不代选六问。Wave L 仍第一等波。无豁免。无 `tickets/*.md`。
> v1.3：塑形 v1.2 G-fresh r3 FAIL，**只关 SH-10、SH-11、SH-12**。SH-01…09 保持 closed。不重开定义帽 QA-01…37。不代选六问。Wave L 仍第一等波。无豁免。无 `tickets/*.md`。
> v1.4：塑形 v1.3 G-fresh r4 FAIL，**只关 SH-13、SH-14**。SH-01…12 保持 closed。不重开定义帽 QA-01…37。不代选六问。Wave L 仍第一等波。无豁免。无 `tickets/*.md`。
> v1.5：塑形 v1.4 G-fresh r5 FAIL，**只关 SH-15、SH-16**。SH-01…14 保持 closed。不重开定义帽 QA-01…37。不代选六问。Wave L 仍第一等波。无豁免。无 `tickets/*.md`。
> v1.6：塑形 v1.5 G-fresh r6 FAIL，**只关 SH-17、SH-18**。SH-01…16 保持 closed。不重开定义帽 QA-01…37。不代选六问。Wave L 仍第一等波。无豁免。无 `tickets/*.md`。
> v1.7：票文件 G-fresh FAIL，**只关 TK-01…TK-04**。SH-01…18 保持 closed。不重开 QA-01…37。不代选六问。无豁免。不写实现代码。
> v1.8：票文件 G-fresh r2 FAIL，**只关 TK-05…TK-08**。TK-01…04 独立 closed。SH-01…18 保持 closed。不重开 QA-01…37。不代选六问。无豁免。不写实现代码。
> 词汇：`CONTEXT.md`（中转站 = LiteLLM Proxy + 值班编排；new-api = 已退役运行时）。

下游：`/dba`（数据语义 §8）· `/designer`（可见差与七叶，不重排五组）· `/sre`（独立 compose、钉 tag）· 实现角色（第二次 spawn 的票）· `/qa`（GWT）。

---

## 0. 合同声明

这是 **v2 现行**技术方案，不是旧 contract v2.1 补丁。旧 ADR「LiteLLM 替换不进本特征」**OVERTURN**（见 [adr-0014](adr-0014-litellm-replaces-new-api.md)）。

**Wave L 如何进方案：** 第一等波，插在 Wave 0 之后、不晚于 Wave 1 市场评分依赖稳定平台路径。平台 LLM 数据面 = LiteLLM Proxy；new-api **退出运行时**（退役，不是双通道）。独立 `deploy/litellm` + 自有 PG；backend **禁止**网关 DSN；BYOK 直连。切换窗允许短双跑作回滚。**完成态** = 默认 `LLM.DATA_PLANE=litellm` + 进程停止 + GWT-72.1 **且** GWT-70.1（无自有行 outbound = 网关 URL，不是平台公共 `https://pub`）。

出现任一句 = 本合同不合格：LiteLLM = FR-60；只改值班文案、规划仍直连上游；双通道当长期架构；resume litellm pyc；根 compose 声明 litellm 服务；另起市场微服务；无自有行仍打平台公共 `llm_providers` / yml；T-20 完成态只停 new-api 不验 GWT-70.1；本程序新建聊天 UI 充当第四动作；第四 When 用「测试内 llm_chat」勾 GWT-70.7/70.10/74.6；`similar_suggest` 失败吞成 `SkillJob status=done`；`similar-suggest` 仍 `require_admin` 经办调不通；B4 写「管理客户端」散文或扫整个 `ai_planner` 禁 `llm_gateway`；`/llm` 写与测试连接仍 `require_admin` 且经办 403 当完成态；B4 `power_market/` 行漏 `llm_gateway`（`from llm_gateway.chat import` 过 T-15）；`/llm` 仍 `ProtectedRoute requireAdmin` 或 operator 无 `menu:llm`（HTTP 200 仍勾不了 GWT-73.4「点」）；T-16 只锁第四 When HTTP、规划/试采/评分入队 200 空过；用第四夹具勾 GWT-70.1 / 70.5 / 70.6 族；HTTP 200 / `status=planning|testing` / `queued=true` 勾 70.2/70.8/70.9、74.1/74.4/74.5；失败格用 outbound 当 oracle；试采第一次成功不进 `_repair_flow` 勾 70.5/70.8/74.4（及 73.7/73.10）；评分只入队不 `consume_once` 勾 70.6/70.9/74.5（及 73.8/73.11）；70.2/70.8/70.9 与 74.1/74.4/74.5 Then 写成无绑定的「或」（`error_message in {空模型句, 网关句}` 一张夹具勾两格）；`DATA_PLANE=litellm` 时 `_resolve_llm_runtime_config` except 仍 `resolve_config_from_settings()` / 落到 yml/env / `https://pub`；HTTP 200 + 空 `clusters` 勾 70.10/74.6；只断言 `SkillJob status≠done` 勾 70.10/74.6；resolve 抛错测试只做「不是 pub / 不是 yml」；`in{74.1句, 网关URL}` 一张夹具勾 70.1 与 74.1。

**票文件闸（TK-01…08；SH-01…18 保持 closed）：** T-17 勾 FR-73 必须同 PR 跑四动作夹具（73.6/73.2 When = T-16 ① `POST /api/v1/ai/plans/{id}/plan`；73.10 = ② `/test`；73.11 = ③ `/rescore`；等到 outbound=**本企业行侧**；73.6 族网关停不得勾 74.1）。禁止只靠 `test_create_endpoint_rejects_operator` 变绿勾 FR-73。T-16 禁止用 `test_trigger_plan_endpoint` / `test_rescore_endpoint_pushes_queue` 当 70.1/70.6 完成态；须新增 `backend/tests/test_llm_four_actions_http.py` **分格** `::node`（禁止 `or_cell_failure` 一名三格）：规划至少 `::test_post_plan_outbound_gateway`（只 70.1）、`::test_post_plan_no_model_only_70_2`、`::test_post_plan_unreachable_only_74_1`；试采/评分同构；试采 HTTP 必须进 `_repair_flow`；70.7 成功格在经办 HTTP 上断言 outbound=网关 URL；闸命令在这些新测试未加之前必须红；现网金标不得当绿闸。T-16 禁止单独勾 70.3/70.4/74.3「是」（70.3→T-18；70.4→T-01/T-20；74.3 与 T-09 GWT-12.4 并格）。T-13 闸必须点名 pytest 模块与夹具命令，禁止「相关 pytest」。**TK-05：** T-20 70.1 闸只钉成功格 `::test_post_plan_outbound_gateway`。SH-01 改写点名 `test_saas_byok.py::test_no_own_key_falls_back_to_platform`（outbound=网关 URL）；禁止整文件 `test_saas_byok.py` 当绿闸成员。`test_saas_provider_semantics.py` 的 `https://pub` 同 PR 作废或降级。**TK-06：** T-16 闸加 `::test_operator_similar_suggest_no_model_envelope_only_70_10` 与 `::test_operator_similar_suggest_unreachable_envelope_only_74_6`。**TK-07：** T-16 新增分格 node：满额（网关可达与不可达各一）→ Then 只 12.3 句，不是「平台 LLM 网关不可达」。未加之前不得把 74.2 标「是」。**TK-08：** T-01 70.4 闸加首页/功能介绍机械 node（三个必须存在的 node id）。未加之前不得勾 T-01 侧 70.4。

六问未关：方案不选定对外第一句、定价履约形态、中转租户 SKU、市场主用户、支付、AGPL 收费故事。Q-LLM **不得**再标待确认。

---

## 1. 现状测绘

**现有边界**（2026-09-08 读码）：单进程 FastAPI `:9111` + 平行 Scrapy Worker + 双前端。根 `docker-compose.yml` 仅 mysql / redis / backend。`run.py all` **已** spawn `run_spider.py`（故事「一把梭无工人」过期）；容器联调仍无 Worker。中转：`deploy/newapi/` 独立 compose，默认关；调度持 `NEWAPI.DB_DSN`；规划器零引用 `NewapiApiClient`。LiteLLM：**不是运行时**——仅误跟踪 `deploy/litellm/config.gen.yaml` + `services/litellm/` pyc。市场：四类 `ASSET_TYPES`，无 listing/安装，双公开闸，无 MCP → `degraded`。

**约束**：

| 约束 | 来源 | 影响 |
|---|---|---|
| 017 业务表 `tenant_id` NOT NULL | PIT-4 | 禁止候选 NULL |
| `require_admin` ≠ 超管 | PIT-2 | 守卫与 b1c 同 PR |
| `capability_assets` 带恒 NULL 列未豁免 | PIT-3 | 租户态 UPDATE 0 行 |
| `llm_chat` 已是 `/chat/completions` | `llm_client.py` | 换网关不必换协议 |
| 套餐闸未接线 | `check_llm_tokens_month` 仅测试 | Wave 0 接线，不换出口 |
| check-arch 无 B4 | `scripts/check-arch.sh` | 本程序加 B4 |
| 公开 ≤400、P95<2s | NFR-01 | 查询侧闸，不新开搜引擎 |

**本次不动**：

- Scrapy 管道与 Redis 队列协议；harvester 不直写主库
- 不合并 `skills` 三表；不改 `uq_asset_type_name_alive`；不 rename `capability_experts`
- 不搬 `domains/`；不复活 8765
- 不代写 `~/.zcode`；不把 `mcp_bridge` 扩成工具面
- 不把 LiteLLM Admin UI 当租户产品
- **不新建**平台路径聊天 UI。第四 When 夹具 = 经办 `POST /api/v1/skills/similar-suggest`（`require_operator`）；该端点只是 GWT-70.7 执行夹具，不是聊天产品
- 不重排后台五组；不修幽灵 `/enterprise` `/rbac`
- 不实现支付、租户渠道组、xlsx、候选迁表

**已知技术债（碰到要小心，本程序只修冻结 FR 碰到的）**：

| 位置 | 债 | 本次 |
|---|---|---|
| ORM Mixin 可空 vs 017 NOT NULL | 测试引擎骗人 | 入队显式传租户 |
| R10 只扫 `services/*.py` 一层 | 子包无入口日志 | 扩递归 |
| `/public/skills` 先分页再内存滤 | PIT-5 | 商店读模型替换 |
| `config.gen.yaml` 明文 Key | FR-14 | Wave 0 离树+轮换证据 |

---

## 2. 模块边界

### 2.1 能力聚类

| FR | 能力 | 归属 |
|---|---|---|
| 01 02 05 | 对外诚实承诺 | 官网商店面（文案） |
| 03 | 导出诚实 | 采集结果出口 |
| 04 | 注册→登录 | SaaS 鉴权 |
| 06 07 17 20 | 平台写权 / 租户壳 / 空缓存 / 目录可见 | SaaS 鉴权 + 目录 |
| 08 | 到期拒绝 | SaaS 鉴权 |
| 09 10 11 | 入队归属 / 回流 / 候选谓词 | 采集入队/结果出口 |
| 12 | 套餐闸 | SaaS 配额（`llm_chat` 前） |
| 13 | 出站绑企业 | 采集结果出口 |
| 14 75 | 密钥离树 | 配置/发布物 + 网关注入 |
| 15 16 43 | 产品事实 + 上海日 | 产品事件叶 |
| 18 19 | 工人可感知 / 零条目收尾 | 采集编排 + Worker |
| 70 73 74 | 平台路径 / BYOK / 失败句 | `llm_chat` + 网关适配叶 |
| 71 07.6 | 值班列表与探针不熔断 | 值班编排 |
| 72 | new-api 退役 | 运行时/SRE |
| 30–33 44 45 | 单一市场、公开闸、alias | Power Market 读模型 |
| 34 35 36 | 订/卸/引用 | Power Market 安装 |
| 37–42 | 七叶、源、许可、命令、第一方 | Power Market 治理 |
| 40 | listed ≠ verify ≠ enable-host | 同左（无宿主投影模块） |

### 2.2 模块清单

| 模块 | 一句话职责 | 独占 | 重写谁碎 | 新建/既有 |
|---|---|---|---|---|
| SaaS 鉴权/配额 | 判定谁能写、企业是否有效、月度 token 是否放行 | tenants/members/quota、`is_platform_admin` | 登录、用量、平台写 | 既有 |
| 采集入队/结果 | 把任务钉在企业上并把条还回去 | spider_tasks/results 写 | 出数、WACT | 既有 |
| `llm_chat` | 发一条 chat 并计 token | 规划/评分/平台聊天唯一出口 | 四动作 | 既有；改出口 |
| 租户 BYOK | 本企业上游密文与直连 | 租户 `llm_providers` 行 | `/llm` 本企业 | 既有；**不搬进网关** |
| LLM 数据面 | 平台上游路由/虚拟 Key/spend | 平台上游 Key、模型别名 | 平台路径 502 | **新建运行时** LiteLLM |
| 网关适配叶 | LiteLLM 聊天+管理 HTTP | 不持有上游 Key、无 DSN | 值班 + 平台路径 | 新建 `llm_gateway/chat.py` 与 `llm_gateway/admin.py`（禁止合成「管理客户端」） |
| 值班编排 | 窗口策略、10 维探针、超管读模型 | 本库 `channel_*` | NewApiOps | 既有；换客户端 |
| Power Market | 目录/上架/订阅/七叶治理 | listing、安装、源、alias | 商店与治理台 | 新建包（目录升级） |
| 产品事件叶 | 追加事实，失败不挡 | 事件表 | WACT/漏斗 | 新建 |
| 官网/Admin 壳 | 渲染与直打同形 | 无业务表 | 履约裂缝 | 既有 |

工人（Scrapy）**不是**本表业务模块：它是独立进程，只消费 Redis，不决定归属。

### 2.3 依赖图

```
官网商店面 / Admin 治理台 / 值班页
        │
        ▼
编排 API（不 import ORM，R7）
        │
        ├──► 【SaaS 鉴权/配额】──► 主库
        ├──► 【llm_chat】
        │         ├──► 【配额闸】（先）
        │         ├──► 【BYOK】──► 租户上游 HTTP
        │         └──► 【网关适配叶】──► LiteLLM Proxy（平台路径）
        ├──► 【值班编排】──► 网关适配叶（管理 HTTP）
        │         └──► 【探针】──► 网关 /v1/chat/completions
        ├──► 【采集入队/结果】──► Redis ──► Scrapy Worker
        │         └──► 候选只读端口 ──► 【Power Market】（只读）
        ├──► 【Power Market】──► 主库目录/安装
        └──► 【产品事件】（叶子；失败不挡）
```

**无环确认**：有向无环。网关适配叶与产品事件为叶子。Power Market **禁止** import 网关（含 `llm_gateway.chat` / `admin`）/规划器/`spider_*`。市场评分只许走 `llm_chat`。`ai_planner/` **只禁** `llm_gateway.admin`；**允许** `llm_client.py` import `llm_gateway.chat`。

**边界强制**：B1–B3 保持；**B4 全表**见 ADR-0010，落地票 **T-15**（禁止只扩 `litellm_*`/`relay_*`；禁止「管理客户端」散文；`power_market/` 行必须含 `llm_gateway`）。B4 grep 写死：

```
# power_market 禁这些前缀（含 llm_gateway：禁 chat/admin 直连）
grep -rnE '^(from|import) backend\.services\.(spider_|newapi_|litellm_|relay_|channel_|ai_planner|llm_gateway)' backend/services/power_market/

# ai_planner 只禁 admin（三模式）
grep -rnE 'from backend\.services\.llm_gateway\.admin|import backend\.services\.llm_gateway\.admin|from backend\.services\.llm_gateway import admin' backend/services/ai_planner/

# ai_planner 除 llm_client.py 禁 chat（三模式）
grep -rnE 'from backend\.services\.llm_gateway\.chat|import backend\.services\.llm_gateway\.chat|from backend\.services\.llm_gateway import chat' backend/services/ai_planner/ --exclude=llm_client.py
```

允许：`backend/services/ai_planner/llm_client.py` 仅 `from backend.services.llm_gateway.chat import ...`。`llm_gateway/__init__.py` 禁止把 `chat` 与 `admin` 打进同一 `__all__`。禁止新代码 `create_async_engine(settings["LITELLM.DB_DSN"])`（lint 可扫 `LITELLM.DB_DSN` 与对网关库的 `create_async_engine`）。T-21 依赖该检查已绿；**T-21 Then**：`grep -rn llm_gateway backend/services/power_market/` **零命中**。市场评分只许走 `llm_chat`，禁止直 import `llm_gateway.chat` / `admin`。

### 2.4 耦合检查

| 检查项 | 结果 |
|---|---|
| 两模块共享表且都写 | 候选/成果：采集 consumer **独占写**；市场只读端口。安装表仅市场写 |
| 模块含其它模块知识 | 禁止 `power_market` 内 `if spider`；禁止 `power_market` import `llm_gateway`（含 chat/admin）；市场评分只走 `llm_chat`；禁止 `llm_chat` 内 new-api 方言；禁止 `ai_planner` 除 `llm_client.py` 外 import `llm_gateway.chat`；禁止任何 `ai_planner` 文件 import `llm_gateway.admin` |
| 强制手段 | **B4 静态检查**（grep 写死，禁「管理客户端」散文）+ 目录约定；挂 `sdlc.config.yaml` lint |

---

## 3. C4（到组件，不到类）

### Context

```
访客 ──► 官网 :9113（逛、注册、定价、市场只读）
租户经办/负责人 ──► 后台 :9112（采集、用量、本企业模型、订/卸）
平台超管 ──► 后台（治理七叶、值班、产品事实查询）
本系统 ──HTTP──► LiteLLM Proxy（平台路径）──► 上游模型供应商
本系统 ──HTTP──► 租户 BYOK 供应商（直连）
本系统 ──不运行──► new-api（Wave L 完成后）
采集 Worker ──► 目标站（夹具 httpbin；不承诺任意站）
```

责任：本系统拥有租户隔离、配额文案、商店闸、值班产品规则（伪装不熔断）。LiteLLM 拥有平台上游凭据与路由。Worker 拥有抓取，不拥有企业。

### Container

```
[frontend/official]  [frontend/admin]
         \              /
          [FastAPI backend :9111]
          /        |         \        \
    [MySQL 主库] [Redis]  [Scrapy Worker 进程]
                              |
                    [LiteLLM compose]
                    litellm :4000 + Postgres [+ 自有 Redis 仅多副本]
                    网络 litellm-net（根 compose external，不声明服务）
```

切分理由：主站故障域（MySQL）≠ 数据面故障域（PG + SALT）。Worker 独立伸缩与反爬生命周期。前端两包独立 npm。

### Component

即 §2.2。不画类图。

---

## 4. 可行性验证

本方案未引入未验证协议。无 LiteLLM 容器 spike（镜像 tag 交 `/sre`）。不确定项下放到 T-14/T-19 只读核对，失败则缩小调度器范围，**不**回退 DSN。

| 假设 | 怎么验证 | 结论 |
|---|---|---|
| `llm_chat` 方言匹配 LiteLLM | 读 `llm_client.py` L293–297 | **成立** |
| 无自有行打平台公共 / yml | 读 `runtime.py` 三段；`test_no_own_key_falls_back_to_platform` 金标 `https://pub` | **现网成立**；`DATA_PLANE=litellm` 时必须作废（SH-01 / T-16） |
| 平台路径聊天有 C 端页 | grep 前端聊天页；`llm_chat` 余下调用方 | **不成立** → 第四 When = 经办 `POST /api/v1/skills/similar-suggest`（`require_operator`；失败不得吞成 done；Then 与 70.9 同级：经办 HTTP 响应（及 Job）**只**该格那一句）。**删掉**「或测试内 llm_chat」可勾选项。只是 70.7 执行夹具，不是聊天产品。禁止新建聊天 UI（SH-05 夹具名保留；SH-07 锁 HTTP）。SH-12：规划/试采/评分另钉现网 HTTP，禁止用本夹具勾 70.1/70.5/70.6 族 |
| B4 `power_market/` 不含 `llm_gateway` | 读 ADR-0010 / T-15 grep | **现网成立（漏）**；拆 chat.py 后 `from llm_gateway.chat import` 过 T-15（SH-10）→ 同一条 grep 加 `llm_gateway`；T-21 零命中 |
| 经办能「点」`/llm` 测试连接 | `App.tsx` `/llm` `ProtectedRoute requireAdmin`；`_ROLE_PERMISSIONS["operator"]` 无 `menu:llm`；022 种子同缺；`LlmProviders.test.tsx` 只钉 viewer | **不成立**（SH-11）→ T-17 同 PR 去掉 requireAdmin（或经办可进）+ operator 加 `menu:llm`（不加 `menu:newapi`）+ 改测试：经办见本企业行保存/测试，只读仍无 |
| 规划/试采/评分 POST 200 即 outbound | `ai.py` `/plan` `/test` `create_task` 立即 snapshot；`skills.py` `/rescore` `enqueue_rescore` 立即 queued | **不成立**（SH-12）→ 成功格等到 outbound URL；禁止入队 200 勾 70.1/70.5/70.6 族 |
| 空模型/网关不可达 ①②③ 用 200/planning/queued 勾 | 现网 `/plan` `/test` 立即 snapshot，`/rescore` 立即 queued；空模型没有 outbound | **不成立**（SH-13）→ 与第四 When 对齐：When=该动作自己的 HTTP；Then=等到该次结果上出现与**该格** GWT 同一句。禁止 HTTP 200 / `status=planning|testing` / `queued=true` 勾这些格。成功格继续等 outbound；**失败格禁止用 outbound 当 oracle** |
| 试采第一次成功 / 评分只入队即打 `llm_chat` | `_execute_test` 第一次通过则 return，不进 `_repair_flow`；`SKILLS.SCORING.ENABLED` 默认关，`/rescore` 只入队 | **不成立**（SH-14）→ 与 ≥2 技能对称：试采夹具必须第一次失败并进入 `_repair_flow`，否则不得勾 70.5/70.8/74.4（及 T-17 的 73.7/73.10）；评分夹具必须 `consume_once`（或打开 `SKILLS.SCORING.ENABLED` 并等到消费），否则不得勾 70.6/70.9/74.5（及 73.8/73.11） |
| 失败格 Then 无绑定「或」一张夹具勾 70.2 与 74.1 | 票表 T-16 丢掉括号，写成 `error_message` 为 A 或 B；实现按 `in{空模型句, 网关句}` 可一张夹具勾两格 | **不成立**（SH-15）→ T-16 票表按 GWT 拆开：70.2/70.8/70.9 Then **只**「还没有平台模型」；74.1/74.4/74.5 Then **只**「平台 LLM 网关不可达」；写进不得互勾。与 §7.2 括号、第四 When 同一写法。禁止无绑定的「或」 |
| `llm_chat` except 仍 yml/env 直连 | 读 `llm_client.py` `_resolve_llm_runtime_config`：resolve 抛错则 `return resolve_config_from_settings()` | **现网成立**（SH-16）→ `DATA_PLANE=litellm` 时 except **禁止** `resolve_config_from_settings()`（应失败成 74.1 句，或仍解析到网关 URL） |
| 70.10/74.6 只锁句子和 Job 非 done | similar-suggest 现网恒 200 + 空 `clusters`；T-16 测试清单只写「失败非 done」。经办看见的是响应，不是 Job 行 | **不成立**（SH-17）→ T-16 / §7.2 把 70.10/74.6 写到与 70.9 同级：经办 HTTP 响应（及 Job）**只**该格那一句（`LLM_GATEWAY_NO_MODEL` / `LLM_GATEWAY_UNREACHABLE`）。禁止 HTTP 200 + 空 `clusters` 勾 70.10/74.6。禁止只断言 `SkillJob status≠done`。同票改 `test_skill_similar_suggest.py`：失败格断言信封/正文 **只**该句，不是 done、不是空成功 |
| resolve 抛错测试只做负向「不是 pub / 不是 yml」 | except 可返回空配置、不调 `resolve_config_from_settings()`，负向测试仍绿，两个允许结果都不出现 | **不成立**（SH-18）→ 同 PR 测试必须正断言：resolve 抛错后 outbound **是**网关 URL，**或**该次结果 **只**「平台 LLM 网关不可达」。禁止只做「不是 pub / 不是 yml」。不要把「或」写成 `in{74.1句, 网关URL}` 去勾 70.1 与 74.1 两格 |
| 规划器未绑死 new-api | grep `NewapiApiClient` | **成立** |
| 值班信封可换血不换 URL | `test_b1c_newapi_*` 锁信封 | **成立**（URL 一周期） |
| 调度 SQL 可原样迁网关库 | LiteLLM spend 在 PG | **不成立** → HTTP |
| `config.gen.yaml` 可当生产配置 | 明文 Key、无 compose | **不成立** → 离树 |
| pyc 可 resume | 无 `.py` | **不成立** |
| 套餐闸已挡住真调用 | 生产 0 引用 | **不成立** → T-09 |
| 根 compose 并入更简单 | 双引擎双密钥 | **不成立** |
| 8h / 把 Wave L 塞进 W0 5–7 人周 | 新进程+新库+退役 | **不成立** |
| `run.py all` 无工人 | `run.py` L148 已 spawn | **故事过期**；compose 仍无工人 → FR-18 空态仍要 |
| 公开 400 行 P95<2s | 查询侧闸 + 现网列表量级 | 距已知 MySQL 点查有余量；verify 用浏览器/curl 计时，禁止「有余量」口头过 |

```
spike：Wave L spend HTTP（T-19 前置，只读 curl 官方 OpenAPI）
问题：网关 spend/budget 是否覆盖「冷却到期自动恢复且不覆盖人工禁用」
环境：/sre 钉的 tag；无生产 Key
结果：本 spawn 未跑
结论：盖不住则 backend 只保留这一条恢复，仍 HTTP；禁止 DSN
```

---

## 5. 关键决策

| 决策 | 结论 | ADR |
|---|---|---|
| 拓扑 | 单体内域；不拆市场服务；网关不进根 compose | [0010](adr-0010-four-pillar-topology.md) |
| Source/Catalog/Runtime | 三层不可混；同步不 listed；D16 回退 | [0011](adr-0011-source-catalog-runtime.md) |
| 目录身份 | bundled slug；不改 uq；撞名失败 | [0012](adr-0012-catalog-identity.md) |
| 候选归属 | 仍住结果表；tenant_id NOT NULL；谓词隔离 | [0013](adr-0013-candidate-ownership.md) |
| LLM 数据面 | LiteLLM；new-api 退役；无 DSN；BYOK 直连；否决平台公共/yml 直连 | [0014](adr-0014-litellm-replaces-new-api.md) |
| 产品事件 | OLTP 追加；仅超管查询；不建仓 | [0016](adr-0016-product-events-oltp.md) |
| 平台 vs 租户 admin | `require_platform_admin`；直打同 404 | [0017](adr-0017-platform-vs-tenant-admin.md) |
| 上架 vs 运行时 | unlist≠停用；不礼包；listed≠verify≠enable-host；七叶 | [0018](adr-0018-listing-vs-runtime.md) |
| 公开列表分页 | **查询侧**完成 FR-33 闸再分页 | 可逆，不单开 ADR |
| 配置前缀 | `LITELLM.*` 连接；`LLM.DATA_PLANE` 旗标（T-20 默认 `litellm`）；值班 expand 只允许 `NEWAPI.*` 读 + `RELAY.*` 写，禁止第三前缀 | 0014 |
| 适配包名 | `backend/services/llm_gateway/chat.py` + `admin.py`（B4 grep 写死；禁「管理客户端」散文） | 0010 / 0014 |
| 镜像 tag | **不代选**；禁 `:latest` | 交 `/sre` |
| Q-VOICE 等六问 | **不代选** | spec §9.1 |

KEEP（与替换正交，写入 0014）：`llm_chat` 单入口；闸在调用前；mcp 仅验证；两本账（套餐 ≠ 成本熔断）；伪装不熔断。

---

## 6. 波次与并行

```
Wave 0（诚实 + FR-12 闸 + 密钥离树 + 值班写权 + 出数环）
    └──► Wave L 启动（数据面切换）
              └── 后半可与 Wave 1 并行，条件：llm_chat 签名不变、套餐闸仍在前
Wave 1 禁止先接第四条调用链等 Wave L
禁止「先做完市场再换网关」
```

超出单波 appetite 50% → 停下重判。RICE Effort 不可加总。

---

## 7. 契约要点（本 spawn 不落 `contracts/*.md`；实现前第二次 spawn 可拆文件）

### 7.1 错误码（`code` 判断，禁止用 `message` 分支）

| code | 何时 | 用户可见 |
|---|---|---|
| `QUOTA_EXCEEDED` | 内部业务码，套餐闸 | **禁止渲染**；页上「已达配额上限」+ 下一步 |
| `LLM_GATEWAY_UNREACHABLE` | 平台路径且网关不可达 | 「平台 LLM 网关不可达」 |
| `LLM_GATEWAY_NO_MODEL` | 网关可达但未登记模型 | 「还没有平台模型」 |
| `LLM_PROVIDER_ERROR` | BYOK 该行失败 | 该行自己的失败句，不是 74.1 / 不是套餐句 |
| `LLM_COST_FUSE` | 平台成本熔断 | 不是套餐超限句（GWT-12.5） |
| `MARKET_NOT_FOUND` | 订阅从不存在/未上架/黑名单短名 | 与从不存在短名相同；无「已下架」 |
| `MARKET_COMING_SOON` | 预告项提交订阅 | 无新行 |
| `MARKET_HOST_INCOMPAT` | 已声明名单不含该宿主 | 提交前 UI 已禁用 |
| `MARKET_READONLY_ROLE` | 只读角色订/卸/改启用 | 「当前账号不能订阅…」 |
| `MARKET_NEEDS_TENANT` | 超管无企业空间订阅 | 「需要企业空间才能订阅」 |
| `AUTH_TENANT_EXPIRED` | 到期/停用登录 | 「企业已到期或停用，请联系平台」≠ 密码错误 |
| `SPIDER_WORKER_OFFLINE` | 无在线工人提交 | 「采集未运行，不会出数」 |

HTTP：业务拒绝用稳定 `code`；公开详情未上架 = **真 404 同形**（不是本表 JSON）。值班远端不可达 = **200** + `available=false`，不 500。

### 7.2 平台路径解析（四动作同一函数，禁止抄四份）

`LLM.DATA_PLANE=litellm` 时（T-20 完成后默认）：

```
check_llm_tokens_month（上海月）→ 满则停（FR-12）
若本企业有激活供应商 → 直连该行（FR-73）
否则 → **只** LiteLLM /v1/chat/completions（FR-70）
禁止：平台公共 llm_providers 直连、yml/env 直连、手填 new-api URL
测试观察点 = 捕获 outbound URL + 侧用量，禁止「进入 LiteLLM」空心句
同 PR 改写 `test_saas_byok.py::test_no_own_key_falls_back_to_platform`：无自有行 → outbound 为网关 URL，不是 https://pub。禁止整文件 `test_saas_byok.py` 当绿闸成员。`test_saas_provider_semantics.py` 的 `https://pub` 同 PR 作废或降级
DATA_PLANE=litellm 时 `_resolve_llm_runtime_config` 的 except **禁止** `resolve_config_from_settings()`（应失败成 74.1 句，或仍解析到网关 URL）（SH-16）。同 PR 测试必须正断言：resolve 抛错后 outbound **是**网关 URL，**或**该次结果 **只**「平台 LLM 网关不可达」（SH-18）。禁止只做「不是 pub / 不是 yml」。不要把「或」写成 `in{74.1句, 网关URL}` 去勾 70.1 与 74.1 两格。该「或」是 except 路径两个允许实现结果：一张夹具只钉其中一个（outbound=网关 URL 可勾 70.1、不可勾 74.1；该次结果只「平台 LLM 网关不可达」可勾 74.1、不可勾 70.1）。负向「不是 pub / 不是 yml」可作辅证，不得单独过闸。
```

`DATA_PLANE=providers` **仅** expand 回滚窗，不是完成态。

覆盖四动作：规划、试采修复、技能评分、平台路径聊天。

**T-16 Then 分四条 When（SH-12；与 GWT-70.1 / 70.5 / 70.6 / 70.7 同一动作名），各钉现网 HTTP：**

| When | 现网 HTTP | 守卫（经办能过） |
|---|---|---|
| 规划（70.1 族） | `POST /api/v1/ai/plans/{id}/plan` | 现网已 `require_operator` |
| 试采修复（70.5 族） | `POST /api/v1/ai/plans/{id}/test` | 现网已 `require_operator` |
| 技能评分（70.6 族） | `POST /api/v1/skills/{name}/rescore` | 现网已 `require_operator` |
| 平台路径聊天（70.7 族） | `POST /api/v1/skills/similar-suggest` | 同票改 `require_operator`（SH-07） |

**成功格继续等 outbound（SH-12 保持）：** `/plan` `/test` 现网 `asyncio.create_task` 立即返回 snapshot（`status=planning|testing`）；`/rescore` 现网 `enqueue_rescore` 立即 `{queued}`。Then **禁止**仅 HTTP 200 / 入队成功 / 快照 busy 勾 70.1 / 70.5 / 70.6 族。成功格必须等到该次 outbound URL（网关侧或本企业行侧）出现。

**失败格（SH-13 保持；SH-15 按 GWT 拆开，禁止无绑定的「或」）：** When = 该动作自己的 HTTP；Then = **等到该次结果上出现**与**该格** GWT 同一句。与本节括号、第四 When 同一写法。**不得互勾。**

- **70.2 / 70.8 / 70.9 Then 只「还没有平台模型」**（空模型；`LLM_GATEWAY_NO_MODEL`）：规划/试采（70.2/70.8）计划 `status=failed` 且 `error_message` **只**该句；评分（70.9）job/响应 **只**该句（`SkillJob status=failed` 的 `detail.reason` 或 `consume_once` 返回的 `error`）。禁止用「平台 LLM 网关不可达」勾这些格。
- **74.1 / 74.4 / 74.5 Then 只「平台 LLM 网关不可达」**（网关不可达；`LLM_GATEWAY_UNREACHABLE`）：规划/试采（74.1/74.4）计划 `status=failed` 且 `error_message` **只**该句；评分（74.5）job/响应 **只**该句。禁止用「还没有平台模型」勾这些格。

**禁止** `error_message in {「还没有平台模型」, 「平台 LLM 网关不可达」}` 一张夹具勾两格。**禁止** HTTP 200 / `status=planning|testing` / `queued=true` 勾这些格。**失败格禁止用 outbound 当 oracle**（空模型没有 outbound）。空模型 / 网关不可达 / BYOK 四动作的 When 必须是**该动作自己的 HTTP**。

**夹具前置（SH-14，与第四 When ≥2 同 category 对称写进 Then）：** 试采夹具必须第一次失败并进入 `_repair_flow`，否则不得勾 70.5/70.8/74.4（及 T-17 的 73.7/73.10）。评分夹具必须 `consume_once`（或打开 `SKILLS.SCORING.ENABLED` 并等到消费），否则不得勾 70.6/70.9/74.5（及 73.8/73.11）。现网：`_execute_test` 第一次通过则不进 `_repair_flow`（不打 `llm_chat`）；`SKILLS.SCORING.ENABLED` 默认关，`/rescore` 只入队。

**禁止用第四夹具勾 70.1 / 70.5 / 70.6 族**（含 70.2 / 70.8 / 70.9、74.1 / 74.4 / 74.5）。similar-suggest 只覆盖 70.7 / 70.10 / 74.6（T-17 的 73.9 / 73.12 同一夹具）。

**第四 When（SH-07，GWT-70.7 / 70.10 / 74.6；T-17 的 73.9 / 73.12 同一夹具）：** 经办能过的 HTTP = `POST /api/v1/skills/similar-suggest`，守卫 `Depends(require_operator)`（`admin`+`operator` 过，只读拒）。夹具必须有 ≥2 条同 `category` 技能，否则 POST 不打 `llm_chat`，**不得**勾 70.7 族。

失败不得吞成 done：去掉 `similar_suggest` 里 `except Exception` 把 `llm_chat` 失败写成 `SkillJob status="done"`。

**70.10 / 74.6 写到与 70.9 同级（SH-17）：** 经办 HTTP 响应（及 Job）**只**该格那一句。与本节括号、70.9「job/响应 **只**该句」同一写法。**不得互勾。**

- **GWT-70.10 Then 只「还没有平台模型」**（空模型；`LLM_GATEWAY_NO_MODEL`）：经办 HTTP 响应（及 Job）**只**该句；不是假装平台路径聊天成功；不是套餐超限句。禁止用「平台 LLM 网关不可达」勾。
- **GWT-74.6 Then 只「平台 LLM 网关不可达」**（网关不可达；`LLM_GATEWAY_UNREACHABLE`）：经办 HTTP 响应（及 Job）**只**该句；不是套餐超限句；无 `QUOTA_EXCEEDED`。禁止用「还没有平台模型」勾。

**禁止 HTTP 200 + 空 `clusters` 勾 70.10/74.6。禁止只断言 `SkillJob status≠done`。** 禁止无绑定的「或」。同票改 `test_skill_similar_suggest.py`：失败格断言信封/正文 **只**该句，不是 done、不是空成功（经办成功格仍 200；只读 403）。

**删掉**「或测试内 llm_chat」作为可勾选项：禁止用单测直调 `llm_chat` 勾 GWT-70.7 / 70.10 / 74.6 / 73.9 / 73.12（`llm_chat` 仍可 mock 为缝，但 When 必须是经办 HTTP）。本端点只是 70.7 执行夹具，**不是**聊天产品。**禁止**本程序新建聊天 UI。`similar-confirm` 仍 `require_admin`（确认簇不是第四动作）。

供应商「测试连接」测该行自己，不强制网关（守卫见 T-17：本企业写与 test = `require_operator`；经办能进 `/llm` 页见 SH-11）。

### 7.3 值班 HTTP

路径 `/api/v1/newapi/*` 一周期保留。守卫改为 `require_platform_admin`（与测试同 PR）。列表字段映射网关模型/部署；无完整上游 Key。空态/降级句冻结：GWT-71.2 / 71.3。

**T-18 / T-19 锁（SH-06）：** HTTP 与 Redis **用 string `gateway_ref`**（expand：`newapi:channel:cfg:{id}` 双读 → `relay:channel:cfg:{ref}`）。表列 `gateway_ref` **等 `/dba`**，本两票禁止改 `channel_id` 类型（今日 BIGINT = new-api PK）。配置 **只允许** `NEWAPI.*` 读 + `RELAY.*` 写，禁止第三前缀。

### 7.4 市场 HTTP（形状级，非 OpenAPI 全文）

- 公开列表：`page`/`page_size`（默认 20，最大 50）+ `total`（仅 FR-33 可见）。筛选项进 URL。非法 `asset_type` → 校验失败，不返回技能列表。
- 公开详情：`/ {type}/{name}` 接受目录短名或 alias。静态段必须注册在动态段之前（PIT-1）。
- 订阅 POST：幂等键 = (tenant_id, asset_id, host)。重复订同一宿主返回已订阅。不占三类配额。
- 安装行 GET/DELETE 在后台鉴权。unlist 后行仍返回，标已下架，可 DELETE。

### 7.5 产品事件

蓝图事件名原样。投递至少一次。`occurred_at` UTC。消费方 = 超管查询面（无其它消费者本程序）。signup 必须带浏览 `anonymous_id`（有浏览会话时）。

### 7.6 出站拉数

未绑定单一企业 → 拒绝、0 行。绑定后 `source <> marketplace`。旧字符串列表钥匙视为未绑定。

---

## 8. 数据语义诉求（给 `/dba`，不写表结构）

```
实体：产品事实
  一行 = 一次事件
  需要：event_name、occurred_at UTC、anonymous_id 或 tenant_id/user_id、role、蓝图关键字段
  生命周期：追加；保留 ≥90 天
  访问：超管按时间/企业/事件名查；租户无查询
  约束：v1 不要求精确一次键；失败不挡主路径

实体：网关引用（expand）
  今日 channel_events/probe.channel_id = new-api PK（BIGINT）
  目标：稳定字符串 gateway_ref（模型/deployment/key）
  路径：加列、读双写；禁止一票改类型
  T-18 / T-19：HTTP/Redis 用 string ref；表列等 /dba；本票禁止改 channel_id 类型
  禁止：LiteLLM Prisma 表进入 platform_core/models；禁止 Alembic 管网关 PG

实体：平台目录行
  tenant_id 恒 NULL；必须登记 TENANT_EXEMPT_TABLES（PIT-3）
  不要给 CapabilityAsset 加 TenantMixin
  listing_state / 治理 status / 许可 / 黑名单 独立
  listed_at：unlist 不清空
  公开出现谓词 = FR-33（查询侧）
  asset_type expand：加 command/agent/team；expert/expert_team 一周期可读
  不改 uq_asset_type_name_alive
  身份见 ADR-0012：bundled slug = {plugin}__{origin_local_name}；撞名失败、已有行 name 不变
  T-21 / T-29 / T-33 新平台表与 TENANT_EXEMPT_TABLES + 夹具同 PR

实体：安装行
  一行 = 一企业 × 一资产 × 一宿主
  TenantMixin；禁止豁免（T-25 同票写死；禁止进 TENANT_EXEMPT_TABLES）
  生命周期：订阅→已订；卸载→无行；unlist 后行留；黑名单/软删 → 行只读（经办可卸）
  订/卸不沿合集边级联

实体：合集边
  出处 + 引用；不是礼包
  解析忽略子行 listing；跳过黑名单/软删并审计

实体：源
  超管登记；同步计数；url 类创建失败
  同步不得把第三方标 listed

实体：alias
  人工短名；与存活目录短名或存活 alias 冲突则两边不变
  同步不自动建

实体：候选
  仍住 spider_results.source=marketplace
  tenant_id NOT NULL（触发者或占位企业）
  配额/我的结果/导出/出站排除

实体：出站钥匙
  必须绑定恰好一家企业；未绑定拒绝

约束：到期企业不得发新会话、已有会话后续写拒绝
日历：用量与近 7 日同一套 Asia/Shanghai 业务日；存 UTC
```

Alembic 头修订现为 **027**。破坏性变更必须 expand-contract 分票。

---

## 9. 角色裁剪

| 角色 | Wave 0 | Wave L | Wave 1 | 理由 |
|---|---|---|---|---|
| `/backend` | 是 | 是 | 是 | 守卫、闸、适配叶、市场 |
| `/frontend` | 是 | 是（值班空态） | 是 | 官网诚实、七叶、安装 |
| `/dba` | 是 | 语义 only（gateway_ref） | 是 | 豁免、事件、listing/安装 |
| `/sre` | 是（密钥、工人编排说明） | **是** | 有限 | 独立 compose、钉 tag、退役 |
| `/qa` | 是 | 是 | 是 | GWT；b1c 同 PR |
| `/designer` | 有限（官网闭集、空态） | 有限（值班 71.2/71.3） | 是（七叶、商店） | 不重排五组 |
| `/ops` | 有限 | 有限 runbook | 有限 | **不指定人名**（Q-OPS-DUTY） |
| `/data-collector` | N/A | N/A | N/A | 归属在结果出口 |
| `/algo` | N/A | N/A | N/A | 不改探针阈值、无评估集 |
| `/miner` `/warehouse` | N/A | N/A | N/A | spec §5 |
| `/analyst` | 口径已冻 | 不进实现票 | 四周后复盘 | 不改事件名 |

实现帽按票再裁。qc 塑形后再审。

---

## 10. Rabbit holes

| 坑 | 为什么危险 | 边界 |
|---|---|---|
| 把 Wave L 当 FR-60 | 永不做 | 票必须锚 FR-70…75 |
| 无自有行打平台公共 / yml | 空过 GWT-70.1 | T-16 作废 `https://pub` 金标；T-20 Then=72.1∧70.1 |
| 本程序新建聊天 UI | 超范围；第四动作无夹具 | T-16 夹具=经办 `POST /skills/similar-suggest`（`require_operator`）；只是 70.7 执行夹具，不是聊天产品 |
| 「或测试内 llm_chat」勾 70.7 族 | 经办 HTTP 可空过 | **删掉**该可勾选项；When 必须是经办能过的 HTTP |
| `similar_suggest` 吞异常 Job 仍 done | 70.10/74.6 失败句测不到 | 同票去掉吞异常；Then 与 70.10/74.6 同一句 |
| 70.10/74.6 只锁句子和 Job 非 done | 现网恒 200 + 空 `clusters`；只断言 `status≠done` 空过（SH-17） | 写到与 70.9 同级：经办 HTTP 响应（及 Job）**只**该格那一句。禁止 HTTP 200 + 空 `clusters`。禁止只断言 `SkillJob status≠done`。同票改 `test_skill_similar_suggest.py`：失败格断言信封/正文 **只**该句，不是 done、不是空成功 |
| B4「管理客户端」散文 / 扫整个 ai_planner 禁 llm_gateway | 不可 grep；误伤 T-16 `llm_client` import chat | 拆 `chat.py` vs `admin.py`；ai_planner 只禁 admin；允许 `llm_client` import chat |
| B4 `power_market/` 漏 `llm_gateway` | 拆 chat.py 后直 import 过 T-15 | T-15 同一条 grep 加 `llm_gateway`；T-21 Then 零命中；评分只走 `llm_chat` |
| T-16 只锁 similar-suggest；入队 200 勾 Then | 规划/试采/评分空过 70.1/70.5/70.6 | 四条 When 各钉现网 HTTP；成功格等到 outbound URL；禁第四夹具勾 70.1/70.5/70.6 族 |
| 失败格用 200 / planning 或 testing / queued 或 outbound 勾 70.2/70.8/70.9、74.1/74.4/74.5 | 空模型无 outbound；入队即「过」（SH-13） | When=该动作 HTTP；Then=等到该次结果上出现与**该格** GWT 同一句；失败格禁 outbound oracle |
| 失败格 Then 写成无绑定的「或」（`in{空模型句, 网关句}`） | 一张夹具勾 70.2 与 74.1（SH-15） | 按 GWT 拆开：70.2/70.8/70.9 Then **只**「还没有平台模型」；74.1/74.4/74.5 Then **只**「平台 LLM 网关不可达」；写进不得互勾。与 §7.2 括号、第四 When 同一写法。禁止无绑定的「或」 |
| `DATA_PLANE=litellm` 时 resolve except 仍 yml/env | `llm_chat` 真入口落到 `https://pub`（SH-16） | except **禁止** `resolve_config_from_settings()`；应失败成 74.1 句，或仍解析到网关 URL |
| resolve 抛错测试只做负向「不是 pub / 不是 yml」 | except 可返回空配置、不调 `resolve_config_from_settings`，负向仍绿，两个允许结果都不出现（SH-18） | 同 PR 测试必须正断言：resolve 抛错后 outbound **是**网关 URL，**或**该次结果 **只**「平台 LLM 网关不可达」。禁止只做「不是 pub / 不是 yml」。不要把「或」写成 `in{74.1句, 网关URL}` 去勾 70.1 与 74.1 两格 |
| 试采第一次成功 / 评分只入队勾 70.5/70.6 族 | 不打 `llm_chat`（SH-14） | 试采第一次失败进 `_repair_flow`；评分 `consume_once` 或开 `SKILLS.SCORING.ENABLED` 等到消费 |
| `/llm` 写与 test 仍 `require_admin` | GWT-73.4 经办调不通 | T-17：本企业写与测试连接=`require_operator`；只读仍拒；平台级行仍 06.6 / 73.3；同 PR 改测试合同 |
| `/llm` 仍 `ProtectedRoute requireAdmin` / operator 无 `menu:llm` | HTTP 200 勾不了「点」 | T-17 同 PR 去掉 requireAdmin（或经办可进）；022 / `_ROLE_PERMISSIONS` / `roles` 给 operator 加 `menu:llm`（不加 `menu:newapi`）；改 `LlmProviders.test.tsx` |
| T-15 只扩两个 B4 前缀 | 柱间 import 漏检 | 落地 ADR-0010 全表 + R10 递归 |
| 新平台表漏豁免 / 安装表进清单 | PIT-3 UPDATE 0 或租户数据被豁免 | T-21/29/33 同 PR 登记；T-25 禁豁免 |
| 同步改 uq 或静默改名 | 公开 URL 破坏性收缩 | ADR-0012；T-29 Then |
| T-18/19 改 `channel_id` 类型 | 一票破坏性 | HTTP/Redis string ref；表列等 /dba |
| 第三配置前缀 | 与 0014 互否 | 只允许 `NEWAPI.*` 读 + `RELAY.*` 写 |
| DSN 抄到 LiteLLM | 外部表不可控 | lint 禁 `LITELLM.DB_DSN` |
| resume litellm pyc | 无源码 | 新包名 `llm_gateway/` |
| 一刀切全部进网关 | 误伤 BYOK | FR-73 四动作 |
| 「进入 LiteLLM」当观察点 | QA-36 空心 | outbound URL |
| 改守卫不改 b1c | PIT-2 CI 红或假绿 | 同 PR |
| 目录未豁免 | PIT-3 UPDATE 0 | T-04 同交 |
| 候选 NULL | PIT-4 真库炸 | ADR-0013 |
| 双公开闸只修一边 | PIT-5 | 单一读模型 |
| 无 MCP 仍 degraded | PIT-6 | 与测试同 PR |
| 动态路由吞静态段 | PIT-1 | 注册顺序 |
| 迁市场删 XSS 测试 | 正文脚本执行 | 迁合同不删 |
| 礼包 / unlist=停用 | 客服说错 | ADR-0018 |
| 六 Tab | 砍命令叶 | 七叶 |
| 根 compose 加 litellm | 故障域焊死 | ADR-0010 |
| 精确一次 / 建仓 | 超范围 | ADR-0016 |
| 窗口调度 1:1 复刻 new-api | 过载 | 优先 budget；一条恢复留 backend |
| filter-repo 清 git 史 | 操作者机外 | 清单要 evidence，正文不写密钥 |
| SALT 当普通回滚 | 上游 Key 全不可解密 | runbook |

**第二次出现再抽象**：市场读模型只做这一条闸；第二种公开端出现时再提接口。

---

## 11. 票表

> 本表 T-nn **仅属** `feat-four-pillars-v2`。不是旧特征 T-01…T-16，不是 DMD-nn。
> 一票 = 一会话「实现 + 自测 + 交付」。跨模块票写清接口。破坏性变更写 expand-contract。
> **第二次 spawn** 才写 `tickets/T-nn.md`。本表覆盖全部冻结 FR。

粗估单位：人日（实现+自测）。不可加总去对 appetite 人周（重叠施工）。

### Wave 0

| 票 | 标题 | FR | 依赖 | 角色 | 粗估 | expand-contract / 接口 |
|---|---|---|---|---|---|---|
| T-01 | 官网卖点闭集；删虚构规模；定价主按钮分档 | 01 02 05（70.4） | — | frontend official | 1–2 | 不选 Q-VOICE 首句；B1–B6 撤或预告，禁止写成当前可买；失败装空。**TK-03**：收到 GWT-70.4（与 T-20 并收；官网无「直连平台网关 / 我的中转令牌」；不得与 72.3 写成同一句；T-16 禁止单独勾「是」）。闸含三个必须存在的 node：**TK-08** `frontend/official/src/pages/Home.test.tsx::test_no_direct_gateway_or_relay_token_copy`、`frontend/official/src/components/home/FeaturesSection.test.tsx::test_no_direct_gateway_or_relay_token_copy`、`frontend/official/src/pages/Pricing.test.tsx::test_no_direct_gateway_or_relay_token_copy`。未加之前不得勾 T-01 侧 70.4。禁止只跑 `Pricing.test` |
| T-02 | 导出仅 CSV/JSON；单次 100 条 | 03 | — | backend + admin | 1 | 列表与导出同一上限；xlsx 不进选项 |
| T-03 | 注册成功主按钮去登录；企业名非空 | 04 | — | official + backend | 1 | 次钮才「再注册」；登录页回链 |
| T-04 | 平台写面 `require_platform_admin`；目录豁免；超管刷新可见 | 06 20 | — | backend | 2 | **守卫+豁免+b1c 同 PR**（PIT-2/3）；扫描空态 |
| T-05 | 租户壳隐藏；直打同 404；空缓存；`/llm` 不整页 404 | 07 17 | T-04 | backend + admin | 2 | 渠道 404 无密钥（勿用掩码当 Then）；登录投影 `is_platform_admin`；GWT-07.6 行为保持；GWT-06.5 本票只验企业负责人保存本企业行；**禁止**把 operator 403 写成 `/llm` 写面完成态（经办写与 test 的 `require_operator` 在 T-17） |
| T-06 | 到期/停用拒绝登录与后续写 | 08 | — | backend | 0.5–1 | 文案≠密码错误；占位企业不进我的结果 |
| T-07 | 全部产任务路径带企业；回流归属=入队企业 | 09 10 | — | backend | 2 | 无企业不入队；无主不写结果；显式传 tenant_id |
| T-08 | 候选不计配额、不进我的结果/导出/出站 | 11 | T-07 | backend | 1 | 谓词 `source<>marketplace`；超管候选 SQL 分页 |
| T-09 | `check_llm_tokens_month` 接到 `llm_chat` 成功路径前 | 12（74.3 并格 12.4） | — | backend | 1 | **不改出口**；用户无 `QUOTA_EXCEEDED`；满额 CTA 不到注册；熔断≠套餐句。**TK-03**：GWT-74.3 与 GWT-12.4 并格（只读打开用量不能改套餐；不能把网关失败写成套餐已满）。闸含 `backend/tests/test_saas_quota.py::test_readonly_usage_cannot_change_plan_and_cannot_render_gateway_failure_as_quota`。T-16 禁止单独勾 74.3「是」 |
| T-10 | 出站钥匙必须绑恰好一家企业 | 13 | T-08 | backend | 1 | 未绑定 0 行；旧字符串钥匙当未绑定 |
| T-11 | 密钥离树：含 `deploy/litellm/config.gen.yaml`；ignore + 扫描 0 命中 | 14 | — | sre + backend | 1 | 轮换证据在交付清单，正文不写密钥；**不**启网关、**不**改 llm_chat 出口 |
| T-12 | Wave 0 产品事件可查 + 用量上海日 | 15 16 | T-03 T-07 T-09 | backend + 双前端 | 2 | 事件名原样；查询面仅超管；signup 匿名身份；五档 cta 各一格 |
| T-13 | 最小出数环：无工人拦住；夹具出数；零条目收尾 | 18 19 | T-07 | sre + scrapy + backend + admin | 2–3 | 夹具 `example` + `https://httpbin.org/get` + 120s；IdleAutoClose 产品窗≠21600；compose 无工人=空态。**TK-04**：闸点名 `backend/tests/test_spider_worker_offline.py`、`test_spider_min_loop.py`、`test_scrapy_idle_autoclose.py`、`test_spider_zero_items.py`；夹具命令 `uv run pytest -x -q backend/tests/test_spider_min_loop.py::test_example_httpbin_get_completes_with_items_within_120s`。禁止「相关 pytest」当闸 |

### Wave L

| 票 | 标题 | FR | 依赖 | 角色 | 粗估 | expand-contract / 接口 |
|---|---|---|---|---|---|---|
| T-14 | LiteLLM 独立 compose + 密钥注入 + 禁 :latest；生成配置不进跟踪树 | 75 | T-11 | sre | 2 | 根 compose 只 external 网；PG 不进 Alembic；tag 本票钉死 |
| T-15 | `llm_gateway/` 拆 `chat.py` vs `admin.py`；禁 DSN；禁 pyc | 70（基建） | T-14 | backend | 2 | **落地 ADR-0010 全表 B4**：`power_market/` 禁 import `spider_*`/`newapi_*`/`litellm_*`/`relay_*`/`channel_*`/`ai_planner`/`llm_gateway`（**同一条 grep** 加 `llm_gateway`，禁 `llm_gateway.chat` / `admin`）；`ai_planner/` **只禁 admin**（grep 写死 `from backend.services.llm_gateway.admin` / `import backend.services.llm_gateway.admin` / `from backend.services.llm_gateway import admin`）；**允许** `ai_planner/llm_client.py` `from backend.services.llm_gateway.chat import`；`ai_planner/` 其它文件禁 `llm_gateway.chat`（同上三模式 `--exclude=llm_client.py`）。禁止「管理客户端」散文。`llm_gateway/__init__.py` 禁止 chat+admin 同 `__all__`。**R10 递归** `backend/services/**/*.py` + 禁网关 DSN / `create_async_engine` 打网关（lint 扫 `LITELLM.DB_DSN`）；禁 pyc |
| T-16 | `llm_chat` 平台出口四动作 + 空模型 + 网关不可达三句分离 | 70 74 | T-09 T-15 | backend | 2–3 | `DATA_PLANE=litellm` 时解析=本企业激活行直连，否则**只** LiteLLM；同 PR 改写 `test_no_own_key_falls_back_to_platform`（无自有行 outbound=网关 URL，不是 `https://pub`）。**SH-16**：`DATA_PLANE=litellm` 时 `_resolve_llm_runtime_config` 的 except **禁止** `resolve_config_from_settings()`（应失败成 74.1 句，或仍解析到网关 URL）。**SH-18**：同 PR 测试必须正断言：resolve 抛错后 outbound **是**网关 URL，**或**该次结果 **只**「平台 LLM 网关不可达」。禁止只做「不是 pub / 不是 yml」。不要把「或」写成 `in{74.1句, 网关URL}` 去勾 70.1 与 74.1 两格。**Then 分四条 When 各钉现网 HTTP**：①规划 `POST /api/v1/ai/plans/{id}/plan`；②试采修复 `POST /api/v1/ai/plans/{id}/test`；③技能评分 `POST /api/v1/skills/{name}/rescore`；④平台路径聊天 `POST /api/v1/skills/similar-suggest`。**成功格继续等 outbound**：①②现网 `create_task` 立即 snapshot、③现网 `enqueue_rescore` 立即 queued，禁止仅 HTTP 200 / `status=planning|testing` / `queued=true` 勾 70.1/70.5/70.6 族。**失败格（SH-13 保持；SH-15 按 GWT 拆开）**：When=该动作自己的 HTTP；Then=等到该次结果上出现与**该格** GWT 同一句。**70.2/70.8/70.9 Then 只**「还没有平台模型」（规划/试采：计划 `status=failed` 且 `error_message` **只**该句；评分：job/响应 **只**该句；`LLM_GATEWAY_NO_MODEL`）。**74.1/74.4/74.5 Then 只**「平台 LLM 网关不可达」（规划/试采：计划 `status=failed` 且 `error_message` **只**该句；评分：job/响应 **只**该句；`LLM_GATEWAY_UNREACHABLE`）。**不得互勾**（禁止无绑定的「或」；禁止 `error_message in {空模型句, 网关句}` 一张夹具勾两格）。与 §7.2 括号、第四 When 同一写法。**禁止** HTTP 200 / `status=planning|testing` / `queued=true` 勾这些格。**失败格禁止用 outbound 当 oracle**。**夹具前置（SH-14，与 ≥2 技能对称）**：试采夹具必须第一次失败并进入 `_repair_flow`，否则不得勾 70.5/70.8/74.4（及 T-17 的 73.7/73.10）；评分夹具必须 `consume_once`（或打开 `SKILLS.SCORING.ENABLED` 并等到消费），否则不得勾 70.6/70.9/74.5（及 73.8/73.11）。**禁止用第四夹具勾 70.1 / 70.5 / 70.6 族**（含 70.2/70.8/70.9、74.1/74.4/74.5）。**第四 When** = 经办 `POST /api/v1/skills/similar-suggest`（同票改 `require_operator`：admin+operator 过，只读拒）；夹具须 ≥2 同 category 技能否则不打 `llm_chat`、不得勾 70.7；去掉吞异常：`llm_chat` 失败不得写 `SkillJob status=done`；**SH-17**：70.10/74.6 写到与 70.9 同级：经办 HTTP 响应（及 Job）**只**该格那一句。Then：**GWT-70.10 Then 只**「还没有平台模型」（空模型；`LLM_GATEWAY_NO_MODEL`）；**GWT-74.6 Then 只**「平台 LLM 网关不可达」（网关不可达；`LLM_GATEWAY_UNREACHABLE`）；**不得互勾**。禁止 HTTP 200 + 空 `clusters` 勾 70.10/74.6。禁止只断言 `SkillJob status≠done`。**删掉**「或测试内 llm_chat」作为可勾选项；本端点只是 70.7 执行夹具、不是聊天产品；**禁止**本程序新建聊天 UI；同 PR 改 `test_skill_similar_suggest.py`：只读 403；失败格断言信封/正文 **只**该句，不是 done、不是空成功。**70.7 成功格在经办 HTTP 上断言 outbound=网关 URL**（禁止仅 HTTP 200 勾 70.7）。**TK-02**：作废或降级 `test_trigger_plan_endpoint` / `test_rescore_endpoint_pushes_queue`（不得当 70.1/70.6 完成态）。**TK-05**：闸改成**分格** `::node`，禁止 `or_cell_failure` 一名三格。规划至少 `backend/tests/test_llm_four_actions_http.py::test_post_plan_outbound_gateway`（只 70.1）、`::test_post_plan_no_model_only_70_2`、`::test_post_plan_unreachable_only_74_1`；试采/评分同构；试采须 `_repair_flow`。SH-01 改写点名 `test_saas_byok.py::test_no_own_key_falls_back_to_platform`（outbound=网关 URL）；禁止整文件 `test_saas_byok.py` 当绿闸成员。`test_saas_provider_semantics.py` 的 `https://pub` 同 PR 作废或降级。闸命令在这些 `::node` 未加之前必须红；现网金标不得当绿闸。**TK-06**：闸加 `::test_operator_similar_suggest_no_model_envelope_only_70_10` 与 `::test_operator_similar_suggest_unreachable_envelope_only_74_6`。**TK-07**：新增分格 node 满额（网关可达与不可达各一：`::test_post_plan_quota_full_gateway_reachable_only_12_3` / `::test_post_plan_quota_full_gateway_unreachable_only_12_3`）→ Then 只 12.3 句，不是「平台 LLM 网关不可达」。未加之前不得把 74.2 标「是」。**TK-03**：70.3 收到 T-18；70.4 收到 T-01/T-20；74.3 与 T-09 GWT-12.4 并格。禁止 T-16 单独勾「是」 |
| T-17 | BYOK 直连四动作；保存/测试连接不要求网关活；本企业写与 test=`require_operator` | 73 | T-16 | backend + admin | 2 | 网关停仍直连；不是 74.1、不是套餐句；**73.5/73.7/73.8 When HTTP 跟 T-16 ①②③**，不得用第四夹具勾；**73.7/73.10 跟 T-16 试采夹具**（第一次失败进 `_repair_flow`，否则不得勾）；**73.8/73.11 跟 T-16 评分夹具**（`consume_once` 或打开 `SKILLS.SCORING.ENABLED` 并等到消费，否则不得勾）；**73.9/73.12 跟 T-16 第四夹具**（经办 `POST /api/v1/skills/similar-suggest`）；本企业供应商写与测试连接 = `require_operator`（admin+operator）；只读仍拒；**平台级行仍 GWT-06.6 / 73.3**；同 PR 改现网 `/llm` 测试合同（作废 `test_create_endpoint_rejects_operator` 金标；经办对本企业行写/test 200；viewer 403；平台行 403）。**同 PR 露出（SH-11）**：去掉 `frontend/admin/src/App.tsx` `/llm` 的 `ProtectedRoute requireAdmin`（或改成经办可进）；`/newapi` 仍 `requireAdmin`。`_ROLE_PERMISSIONS["operator"]` + Alembic `022` `_SEED_ROLES` operator + `roles` 表 operator 行同 PR 加 `menu:llm`（**仍不加 `menu:newapi`**；022 已 applied 则数据回填 UPDATE JSON，禁止改表结构）。同 PR 改 `LlmProviders.test.tsx`：经办看得到本企业行保存/测试，只读仍无。**TK-01**：73.6/73.2 When = T-16 ① `POST /api/v1/ai/plans/{id}/plan`（与 73.5 同级）；73.10=② `/test`；73.11=③ `/rescore`。同 PR 闸必须跑 `backend/tests/test_fr73_byok_four_actions_http.py`（等到 outbound=**本企业行侧**；73.6 族网关停不得勾 74.1）。禁止只靠 `test_create_endpoint_rejects_operator` 变绿勾 FR-73 |
| T-18 | 值班页列表改网关模型；空态 71.2 / 降级 71.3；URL `/newapi` 保留 | 71（70.3） | T-05 T-15 | backend + admin | 2 | HTTP/Redis 用 string `gateway_ref`；表列等 `/dba`；**本票禁止改 `channel_id` 类型**；配置只允许 `NEWAPI.*` 读 + `RELAY.*` 写，禁止第三前缀；信封 `available=false`；页上无完整 Key。**TK-03**：收到 GWT-70.3（租户公司管理员或经办改平台网关模型或登记平台上游 → 拒绝；列表不变）。闸含 `backend/tests/test_newapi_api.py::test_operator_or_tenant_admin_write_gateway_model_rejected_list_unchanged`。T-16 禁止单独勾「是」 |
| T-19 | 探针/窗口改管理 HTTP；spend→budget；伪装仍不熔断 | 07.6 | T-15 T-18 | backend | 2 | HTTP/Redis 用 string `gateway_ref`；表列等 `/dba`；**本票禁止改 `channel_id` 类型**；配置只允许 `NEWAPI.*` 读 + `RELAY.*` 写，禁止第三前缀；先只读 spend 再打开写；失败则只留「冷却恢复」一条在 backend；**禁止 DSN** |
| T-20 | 退役验收：停 new-api 进程；墓碑文档；`NEWAPI.ENABLED` 恒 false 后删读 | 72（70.4） | T-16 T-18 T-19 | sre + backend | 1 | 默认 `LLM.DATA_PLANE=litellm`；完成态 Then = **GWT-72.1 且 GWT-70.1**（无自有行 outbound=网关 URL）；夹具=进程已停+值班已是网关列表；定价仍无渠道组当前可买。**TK-03**：收到 GWT-70.4（与 T-01 并收；不得与 72.3 写成同一句；T-16 禁止单独勾「是」）。闸含 `frontend/admin/src/App.test.tsx::test_operator_no_direct_gateway_or_relay_token_entry`。**TK-05**：70.1 闸只钉成功格 `backend/tests/test_llm_four_actions_http.py::test_post_plan_outbound_gateway`（禁止 `or_cell_failure` / 70.2/74.1 失败格 node 当本票 70.1） |

### Wave 1

| 票 | 标题 | FR | 依赖 | 角色 | 粗估 | expand-contract / 接口 |
|---|---|---|---|---|---|---|
| T-21 | 单一「能力市场」；五类枚举；非法类型失败；`/skills` 映射 | 30 44 | T-15 | backend + official | 2 | 依赖 T-15 B4+R10+禁 DSN 检查**已绿**；**Then**：`grep -rn llm_gateway backend/services/power_market/` **零命中**（含 `llm_gateway.chat` / `admin`）；市场评分只许走 `llm_chat`（T-16 `POST /api/v1/skills/{name}/rescore`），禁止直 import `llm_gateway.chat` / `admin`；不新开评分链；新平台表与 `TENANT_EXEMPT_TABLES` + 夹具**同 PR**；`asset_type` expand 双值；作废 bogus→skill 金标；旧专家地址一周期 |
| T-22 | 列表可搜可筛；预告无按钮；失败≠空 | 31 | T-21 T-23 | official + backend | 2 | 筛选项进 URL；未上架/黑名单不出现 |
| T-23 | 查询侧 FR-33 闸+分页 total；详情包含闸；商店不存在句 | 32 33 | T-21 | backend | 2–3 | GET 404 同形 vs POST `MARKET_NOT_FOUND` 拆开；包含 GWT-32.9…32.12 |
| T-24 | 详情正文纯文本；迁 XSS 合同；出处不泄漏未上架父插件 | 32.4 32.5 | T-23 | official | 1 | **禁止**删 `SkillsSquare` XSS 测试而不迁 |
| T-25 | 订阅只作用于这一行；不礼包；宿主两态；不占配额 | 34 | T-23 | backend + admin | 2 | 安装表 **TenantMixin 且禁止豁免**（禁止进 `TENANT_EXEMPT_TABLES`）；唯一（企业,资产,宿主）；未登录回跳尚未订 |
| T-26 | 「我的安装」；unlist 残留可卸；安装行只读 vs 只读角色 | 35 | T-25 | backend + admin | 2 | 卸插件不连坐；无 enable-host |
| T-27 | 引用解析忽略子行上架；黑名单跳过+审计 | 36 | T-25 | backend | 1 | 观测=超管/系统引用列表，非执行引擎 |
| T-28 | 治理台七叶；listed≠verify；无上架全部子资产；`dev-team` 句 | 37 40 | T-21 | admin + backend | 2–3 | 无 MCP=`unknown` 可上架；与 PIT-6 测试同 PR；listed_at unlist 不清空 |
| T-29 | 源登记/同步；第三方不自动 listed；第一方夹具回填；D16 回退 | 38 41 | T-28 | backend | 2–3 | Then（ADR-0012）：bundled slug=`{plugin}__{origin_local_name}`；**不改** `uq_asset_type_name_alive`；两源撞插件名 → 后一次失败、已有行 name 不变；新平台表与 `TENANT_EXEMPT_TABLES` + 夹具同 PR；迁移里禁止 attach 源；纠正对第三方不可用；夹具 `example-pdf-extractor` |
| T-30 | 命令独立可订卡片 | 39 | T-21 T-25 | backend + 双前端 | 1–2 | 不是插件 JSON 货架 |
| T-31 | 许可闸；已订与解析不被拆；特例仅超管 | 42 | T-25 T-27 | backend | 1 | 租户不能拆 B 的已订行 |
| T-32 | 市场事件可查 | 43 | T-12 T-25 | backend + 双前端 | 1–2 | `coming_soon` 字面量；租户无查询面 |
| T-33 | 人工短名 alias；冲突保存失败；同步不建 | 45 | T-23 | backend | 1 | 新平台表与 `TENANT_EXEMPT_TABLES` + 夹具同 PR；alias 撞存活目录短名或存活 alias → 保存失败、两边不变；PIT-1 路由顺序 |

**并行度**：T-01∥T-02∥T-03∥T-04∥T-06∥T-11；T-09 不依赖网关。T-16 依赖 T-09（闸已在）。Wave 1 T-21 **依赖 T-15 检查已绿**，可与 T-16 后半并行，不得早于 T-15；**禁止**市场评分另开链。T-23 是商店读模型关键路径，T-22/T-25 依赖它。

**不在本表**：FR-50/51、FR-60/61（stub）。切片「定价无渠道组当前可买」由 T-01 + T-20 回归，不单开 Wave 3 票。

---

## 12. FR → 票 覆盖（自检）

| FR | 票 |
|---|---|
| 01 02 05 | T-01（**70.4 与 T-20 并收**；T-01 侧 70.4 闸须 Home/Features/Pricing 三个 node；未加之前不得勾 T-01 侧 70.4） |
| 03 | T-02 |
| 04 | T-03 |
| 06 20 | T-04 |
| 07 17 | T-05（07.6 行为 T-05 保持、T-19 换调用后仍真） |
| 08 | T-06 |
| 09 10 | T-07 |
| 11 | T-08 |
| 12 | T-09（**74.3 与 GWT-12.4 并格**） |
| 13 | T-10 |
| 14 | T-11 |
| 15 16 | T-12 |
| 18 19 | T-13（闸点名 `test_spider_worker_offline.py` / `test_spider_min_loop.py` / `test_scrapy_idle_autoclose.py` / `test_spider_zero_items.py`；夹具 `test_spider_min_loop.py::test_example_httpbin_get_completes_with_items_within_120s`；禁止「相关 pytest」） |
| 70 | T-16（70.1/70.5/70.6/70.7 族 + 70.2/70.8/70.9/70.10；基建 T-15；T-20 完成态叠 GWT-70.1；四条 When 各钉现网 HTTP；成功格等到 outbound；失败格按 GWT 拆开：70.2/70.8/70.9 Then **只**「还没有平台模型」、不得互勾、禁 outbound oracle；70.10 与 70.9 同级；except 禁 `resolve_config_from_settings()`；试采须进 `_repair_flow`；评分须 `consume_once`；**70.3 收到 T-18；70.4 收到 T-01/T-20**；禁止 T-16 单独勾 70.3/70.4「是」；闸=分格 `::node`（`::test_post_plan_outbound_gateway` 只 70.1 / `::test_post_plan_no_model_only_70_2` / `::test_post_plan_unreachable_only_74_1`；试采/评分同构），禁止 `or_cell_failure` 一名三格；禁止整文件 `test_saas_byok.py`；SH-01 点名 `::test_no_own_key_falls_back_to_platform`；T-20 70.1 只钉成功格；禁止 `test_trigger_plan_endpoint` / `test_rescore_endpoint_pushes_queue` / `test_saas_provider_semantics.py` `https://pub` 当绿闸） |
| 74 | T-16（74.1/74.4/74.5/74.6 Then **只**「平台 LLM 网关不可达」；**74.2** Then **只** 12.3 句，须两满额分格 node（网关可达/不可达各一），未加之前不得标「是」；**74.3 与 T-09 GWT-12.4 并格**；禁止 T-16 单独勾 74.3「是」；闸加 `::test_operator_similar_suggest_unreachable_envelope_only_74_6`） |
| 73 | T-17（73.6/73.2 When=T-16 ① `POST /plan`；73.10=② `/test`；73.11=③ `/rescore`；同 PR 闸跑 `test_fr73_byok_four_actions_http.py` 等到 outbound=本企业行侧；73.6 族网关停不得勾 74.1；禁止只靠 `test_create_endpoint_rejects_operator` 勾 FR-73；73.7/73.10 须 `_repair_flow`；73.8/73.11 须 `consume_once`；73.9/73.12 第四夹具；本企业写与 test=`require_operator`；经办 `menu:llm` + `/llm` 可进；平台级行 73.3） |
| 71 | T-18（**收到 GWT-70.3**） |
| 72 | T-20（**70.4 与 T-01 并收**；不得与 72.3 写成同一句；70.1 闸只钉 `::test_post_plan_outbound_gateway`） |
| 75 | T-14（T-11 离树前置） |
| 30 44 | T-21 |
| 31 | T-22 |
| 32 33 | T-23 T-24 |
| 34 | T-25 |
| 35 | T-26 |
| 36 | T-27 |
| 37 40 | T-28 |
| 38 41 | T-29 |
| 39 | T-30 |
| 42 | T-31 |
| 43 | T-32 |
| 45 | T-33 |

NFR-01…08 分别由 T-23 计时、T-02 100 条、T-01/T-22 失败装空、T-11/T-14 密钥、T-04/T-05 权限、T-17 本企业 `/llm` 写与 test=`require_operator`（经办 `menu:llm`，平台级行仍 73.3）、T-31 许可、T-21 兼容（`power_market/` 零命中 `llm_gateway`）、T-12/T-32 可观测覆盖。NFR-09 国际化 N/A。NFR-10：T-14 不并根编排。

---

## 13. 风险点（给 `/qa` `/sre`）

| 风险 | 影响 | 给谁 | 关注 |
|---|---|---|---|
| 平台路径仍打 new-api | 护栏红线；Wave L 未完成 | qa | GWT-72.1 夹具必须停进程 |
| 网关挂渲染成套餐满 | 护栏；FR-74 | qa | 四动作分格，不与 12.5 互勾 |
| 非超管写渠道成功 | Wave 0 未完成 | qa | 公司管理员 + 直打 |
| 跨租户可见 / 出站混拉 | 停发布 | qa | GWT-13.3 |
| 公开泄漏未上架 | 关商店 | qa | 列表第 2 页 + 包含 + 详情 404 |
| 密钥进 git | FR-14/75 | sre | CI `git grep` 0；生成配置不跟踪 |
| SALT 误轮换 | 上游 Key 全废 | sre | runbook |
| `/health/deep` 不反映网关 | 有意 | sre | 独立 ready，勿把 liveness 绑网关 |
| 工人空洞解释成获客失败 | WACT=0 误诊 | analyst | 拆 FR-18 |
| 镜像 tag 漂移 | 不可复现 | sre | 禁 latest |

回滚三类均 **未实测**：代码回 tag + 一笔平台路径；数据平台表只 expand、网关 PG 回卷；配置 `LLM.DATA_PLANE=providers`（仅 expand 窗；T-20 完成后默认 `litellm`）。SALT 轮换不可当普通回滚。

---

## 14. 给第二次 spawn 的清单

1. 按本表写 `tickets/T-01.md`…`T-33.md`（每张：FR 锚点、验收 GWT 列表、同 PR 测试、expand-contract）。**须**把 v1.1 SH-01…SH-06、v1.2 SH-07…SH-09、v1.3 SH-10…SH-12、v1.4 SH-13…SH-14、v1.5 SH-15…SH-16、**v1.6 SH-17…SH-18** 锁进对应票 Then（T-05/15/16/17/18/19/20/21/25/29/33），不得回退到 v1 / v1.1 / v1.2 / v1.3 / v1.4 / v1.5 票表短句（尤其不得把「或测试内 llm_chat」或「管理客户端」写回 T-15/T-16；不得漏 `power_market` 的 `llm_gateway` grep；不得只锁 similar-suggest；不得留下 `/llm` `requireAdmin` 挡经办；不得用 HTTP 200 / `planning|testing` / `queued` / outbound 勾失败格；不得用第一次成功的试采或只入队的评分勾 70.5/70.6 族；**不得**把 70.2/70.8/70.9 与 74.1/74.4/74.5 Then 写成无绑定的「或」；**须**按 GWT 拆开：70.2/70.8/70.9 Then **只**「还没有平台模型」、74.1/74.4/74.5 Then **只**「平台 LLM 网关不可达」、写进不得互勾、与 §7.2 括号/第四 When 同一写法；**不得**让 `_resolve_llm_runtime_config` except 落到 `resolve_config_from_settings()` / yml/env / `https://pub`；**不得**用 HTTP 200 + 空 `clusters` 或只断言 `SkillJob status≠done` 勾 70.10/74.6（须断言信封/正文 **只**该句，不是 done、不是空成功）；**不得**只做 resolve 抛错「不是 pub / 不是 yml」（须正断言 outbound **是**网关 URL，**或**该次结果 **只**「平台 LLM 网关不可达」；禁止 `in{74.1句, 网关URL}` 勾 70.1 与 74.1 两格））。
2. 如实现帽需要并行，再拆 `contracts/`（事件 / 市场公开 / 安装 / 值班信封 / 配额）。
3. `/dba` 按 §8 出 db-spec；**不要**把网关 PG 纳入迁移链；`gateway_ref` 加列、禁止一票改 `channel_id` 类型。
4. `/sre` 钉 LiteLLM 镜像 tag，写 `deploy/litellm` README（网络契约同 new-api §5.2 同构，对象换成 litellm）。

---

## 15. 变更记录

| 版本 | 日期 | 变更 | 触发者 |
|---|---|---|---|
| v1 | 2026-09-08 | 初版。按 spec v1.6 重写。吸收 Wave L。票表 T-01…T-33。无 tickets/*.md | G-fresh r7 PASS → 塑形第一 spawn |
| v1.1 | 2026-09-08 | 只关 SH-01…SH-06。ADR-0014 否决备选 I；新 ADR-0012；T-15 全表 B4；T-16/20 完成态；T-21/25/29/33 PIT-3；T-18/19 string ref。不重开 QA-01…37。不代选六问。Wave L 仍第一等。无 tickets/*.md | 塑形第一 spawn 独立审查 FAIL |
| v1.2 | 2026-09-08 | 只关 SH-07…SH-09。T-16 第四 When=经办 POST similar-suggest（require_operator；失败不吞 done；Then=70.10/74.6 同一句；删「或测试内 llm_chat」）。T-15 拆 chat.py/admin.py；B4 grep 写死 ai_planner 只禁 admin、允许 llm_client import chat。T-17 本企业写与 test=require_operator；73.9/73.12 同一夹具；同 PR 改 /llm 测试合同。不重开 QA-01…37。不代选六问。Wave L 仍第一等。无 tickets/*.md | 塑形 v1.1 G-fresh r2 FAIL |
| v1.3 | 2026-09-08 | 只关 SH-10…SH-12。T-15/ADR-0010 `power_market/` 同一条 grep 加 `llm_gateway`；T-21 Then 零命中 `llm_gateway`，评分只走 `llm_chat`。T-17 同 PR 去掉 `/llm` `ProtectedRoute requireAdmin`（或经办可进）；operator 加 `menu:llm`（022 / `_ROLE_PERMISSIONS` / `roles` 表；不加 `menu:newapi`）；平台级行仍 73.3；改 `LlmProviders.test.tsx`。T-16 Then 分四条 When 各钉现网 HTTP；异步等到 outbound URL；禁第四夹具勾 70.1/70.5/70.6 族。SH-01…09 保持 closed。不重开 QA-01…37。不代选六问。Wave L 仍第一等。无 tickets/*.md | 塑形 v1.2 G-fresh r3 FAIL |
| v1.4 | 2026-09-08 | 只关 SH-13、SH-14。T-16 把 70.2/70.8/70.9、74.1/74.4/74.5 与第四 When 对齐：When=该动作自己的 HTTP；Then=等到该次结果上出现与 GWT 同一句（规划/试采：计划 `failed` + `error_message`；评分：job/响应）。禁止 HTTP 200 / `status=planning|testing` / `queued=true` 勾这些格。成功格继续等 outbound；失败格禁止 outbound 当 oracle。试采夹具必须第一次失败进 `_repair_flow`，否则不得勾 70.5/70.8/74.4（及 73.7/73.10）；评分夹具必须 `consume_once`（或打开 `SKILLS.SCORING.ENABLED` 并等到消费），否则不得勾 70.6/70.9/74.5（及 73.8/73.11）。SH-01…12 保持 closed。不重开 QA-01…37。不代选六问。Wave L 仍第一等。无 tickets/*.md | 塑形 v1.3 G-fresh r4 FAIL |
| v1.5 | 2026-09-08 | 只关 SH-15、SH-16。T-16 票表/§7.2/抄票清单按 GWT 拆开：70.2/70.8/70.9 Then **只**「还没有平台模型」；74.1/74.4/74.5 Then **只**「平台 LLM 网关不可达」；写进不得互勾。与 §7.2 括号、第四 When 同一写法。禁止无绑定的「或」。T-16 Then：`DATA_PLANE=litellm` 时 `_resolve_llm_runtime_config` 的 except **禁止** `resolve_config_from_settings()`（应失败成 74.1 句，或仍解析到网关 URL）。同 PR 加测试：resolve 抛错时不得落到 yml/env / `https://pub`。SH-01…14 保持 closed。不重开 QA-01…37。不代选六问。Wave L 仍第一等。无 tickets/*.md | 塑形 v1.4 G-fresh r5 FAIL |
| v1.6 | 2026-09-08 | 只关 SH-17、SH-18。T-16 / §7.2 把 70.10/74.6 写到与 70.9 同级：经办 HTTP 响应（及 Job）**只**该格那一句（`LLM_GATEWAY_NO_MODEL` / `LLM_GATEWAY_UNREACHABLE`）。禁止 HTTP 200 + 空 `clusters` 勾 70.10/74.6。禁止只断言 `SkillJob status≠done`。同票改 `test_skill_similar_suggest.py`：失败格断言信封/正文 **只**该句，不是 done、不是空成功。同 PR 测试必须正断言：resolve 抛错后 outbound **是**网关 URL，**或**该次结果 **只**「平台 LLM 网关不可达」。禁止只做「不是 pub / 不是 yml」。不要把「或」写成 `in{74.1句, 网关URL}` 去勾 70.1 与 74.1 两格。SH-01…16 保持 closed。不重开 QA-01…37。不代选六问。Wave L 仍第一等。无 tickets/*.md | 塑形 v1.5 G-fresh r6 FAIL |
| v1.7 | 2026-09-08 | **只关 TK-01…TK-04**。SH-01…18 保持 closed。不重开 QA-01…37。不代选六问。无豁免。不写实现代码。TK-01：T-17 73.6/73.2 When=T-16 ① `POST /plan`；73.10=② `/test`；73.11=③ `/rescore`；同 PR 闸跑 `test_fr73_byok_four_actions_http.py` 等到 outbound=本企业行侧；73.6 族网关停不得勾 74.1；禁止只靠 `test_create_endpoint_rejects_operator` 勾 FR-73。TK-02：T-16 作废或降级 `test_trigger_plan_endpoint` / `test_rescore_endpoint_pushes_queue`；新增 `test_llm_four_actions_http.py` POST `/plan` `/test` `/rescore` 等到 outbound 或该格失败句；试采须 `_repair_flow`；70.7 经办 HTTP 断言 outbound=网关 URL；新测试未加之前闸必须红。TK-03：70.3→T-18；70.4→T-01/T-20；74.3 与 T-09 GWT-12.4 并格；禁止 T-16 单独勾「是」。TK-04：T-13 闸点名 pytest 模块与夹具命令，禁止「相关 pytest」。 | 票文件 G-fresh FAIL |
| v1.8 | 2026-09-08 | **只关 TK-05…TK-08**。TK-01…04 独立 closed。SH-01…18 保持 closed。不重开 QA-01…37。不代选六问。无豁免。不写实现代码。TK-05：T-16 闸改成分格 `::node`，禁止 `or_cell_failure` 一名三格；规划 `::test_post_plan_outbound_gateway`（只 70.1）/`::test_post_plan_no_model_only_70_2`/`::test_post_plan_unreachable_only_74_1`，试采/评分同构；T-20 70.1 闸只钉成功格；SH-01 点名 `test_saas_byok.py::test_no_own_key_falls_back_to_platform`（outbound=网关 URL）；禁止整文件 `test_saas_byok.py` 当绿闸；`test_saas_provider_semantics.py` `https://pub` 同 PR 作废或降级。TK-06：闸加 `::test_operator_similar_suggest_no_model_envelope_only_70_10` 与 `::test_operator_similar_suggest_unreachable_envelope_only_74_6`。TK-07：T-16 满额两分格 node（网关可达/不可达）Then 只 12.3 句，不是「平台 LLM 网关不可达」；未加之前不得把 74.2 标「是」。TK-08：T-01 70.4 闸加 Home/Features/Pricing 三个必须存在的 node；未加之前不得勾 T-01 侧 70.4。 | 票文件 G-fresh r2 FAIL |
