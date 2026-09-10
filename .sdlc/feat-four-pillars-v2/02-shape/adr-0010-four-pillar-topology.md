# ADR-0010：四柱单体内域；市场不拆服务；网关不进根编排

> 状态：**accepted**
> 日期：2026-09-08｜决策者：/architect｜相关：PRD v1.6 FR-01…20 / FR-70…75 / FR-30…45；`contract.md`

## 背景

四柱（采集 / SaaS / 中转数据面 / 能力市场）已长在同一 FastAPI 进程与平行 Scrapy Worker 上。旧特征 `feat-four-pillars` 的拓扑决策方向仍对，但旧 `02-shape/` 不得当现行合同。本 ADR 在 v2 重写：部署切分与模块切分分开，避免「换网关」被理解成「拆市场微服务」或「把 LiteLLM 焊进根 compose」。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 独立部署优于耦合 | `project_rule.md` |
| 不另起市场微服务 | spec §5；无独立伸缩/发布/团队墙 |
| 平台 LLM 网关不并进根编排 | spec §5 / NFR-10；诊断 `litellm-replace-newapi.md` §2.2 |
| B1–B3 挡不住柱间 import | `scripts/check-arch.sh` 仅 B1–B3；`backend/services/` 上帝包 |
| 公开目录体量 ~400 行量级 | NFR-01；现网公开列表非独立负载域 |

## 决策

**业务四柱继续住在单一 FastAPI 应用 + 平行 Scrapy Worker + 平台 MySQL/Redis。** 能力市场升级为包 `backend/services/power_market/`（单体内域），**不**新建可部署业务进程。平台 LLM 网关（LiteLLM Proxy）是 **独立故障域**：独立目录 `deploy/litellm/`、独立 compose、独立网络 `litellm-net`、自有 Postgres；根 `docker-compose.yml` **只允许**声明 `external: litellm-net`，**禁止**声明 litellm 服务。Scrapy Worker 保持独立进程（B2）；根 compose 本程序 **不**把 Worker 焊进去——`run.py all` 已 spawn `run_spider.py`，容器联调无工人走 FR-18 空态。

柱间强制手段：新增 **B4**（`scripts/check-arch.sh`，挂 lint），**全表**如下（落地票 **T-15**，禁止只扩两个前缀）。**禁止**把 B4 写成「禁 import 网关管理客户端」散文。适配叶必须拆 `llm_gateway/chat.py` vs `llm_gateway/admin.py`（见 ADR-0014）。

| 主体 | grep 写死（T-15 抄进 `scripts/check-arch.sh`） | 允许 |
|---|---|---|
| `power_market/` | `grep -rnE '^(from\|import) backend\.services\.(spider_\|newapi_\|litellm_\|relay_\|channel_\|ai_planner\|llm_gateway)' backend/services/power_market/` | —（评分只走 `llm_chat`；禁直 import `llm_gateway.chat` / `admin`） |
| `ai_planner/` **只禁 admin** | `grep -rnE 'from backend\.services\.llm_gateway\.admin\|import backend\.services\.llm_gateway\.admin\|from backend\.services\.llm_gateway import admin' backend/services/ai_planner/` | — |
| `ai_planner/` 除 `llm_client.py` 禁 chat | 同上三模式把 `admin` 换成 `chat`，加 `--exclude=llm_client.py` | `backend/services/ai_planner/llm_client.py` **仅** `from backend.services.llm_gateway.chat import ...` |

`llm_gateway/__init__.py` 禁止把 `chat` 与 `admin` 打进同一 `__all__`（防 `from backend.services.llm_gateway import *` 偷渡 admin）。

同票：**R10** 扫描从 `backend/services/*.py` 一层扩到 `backend/services/**/*.py`；**禁止**网关 DSN / `create_async_engine` 打网关（lint 扫 `LITELLM.DB_DSN` 与对网关库的 `create_async_engine`）。T-21 依赖该检查已绿；**T-21 Then**：`grep -rn llm_gateway backend/services/power_market/` 零命中。现网 `check-arch.sh` 文首仍只 B1–B3，R10 仍一层。

本期不搬 `domains/` 物理拆包。8765 技能治理后台保持退役，不复活。

## 备选与否决理由

### 备选 A：能力市场独立微服务

**否决理由**：无独立伸缩（NFR-01 上限 400 listed）、无独立发布节奏、无团队墙、无「市场挂了采集必须活」的进程隔离硬需求。拆服务会引入跨库事务与第二套鉴权，和宪法「默认不拆」冲突。设计 Alternatives 已否。

### 备选 B：LiteLLM 服务写入根 `docker-compose.yml`

**否决理由**：根栈是 MySQL 8 + Redis + backend；LiteLLM 硬依赖 **Postgres** + 不可轮换 `LITELLM_SALT_KEY`。一次 `compose down` 同时砍主站与数据面；`/health/deep` 今日只探 MySQL/Redis，并进后会把两个故障域焊死。与 new-api 已验证的「独立 compose + external 网络」同构，见 `deploy/newapi/README.md` §1。细节见 ADR-0014。

### 备选 C：按 Controller/Service/Repository 切「四柱模块」

**否决理由**：一次「订这一行」会同时改 MarketController + MarketService + MarketRepository，边界是假的。按能力切：SaaS 鉴权/配额、采集入队/结果、`llm_chat`、网关适配叶、值班编排、Power Market、产品事件叶。

### 备选 D：把 Scrapy Worker 并进根 compose 当「出数环交付」

**否决理由**：B2 与「爬取与存储分离」要求 Worker 独立进程、禁 import backend。FR-18 验收的是「无工人可感知 / 有工人夹具出数」，不是「一张 compose 好看」。`run.py all`（2026-09-08）已 spawn Worker；根 compose 仍无 Worker——这是空态，不是漏实现。

### 备选 E：把 `llm_chat` 挪出 `ai_planner/` 以免 B4 误伤 T-16

**否决理由**：存量单测 patch `backend.services.ai_planner_service.llm_chat` / `ai_planner.llm_client`（`test_ai_planner.py`、`test_llm_provider.py`、`test_llm_client_routing.py` 等）。本程序不搬函数。拆 `llm_gateway/chat.py` vs `admin.py` 后 B4 **只禁 admin**、允许 `llm_client.py` import chat，误伤消失。

### 备选 F：B4 写「ai_planner 禁 import 网关管理客户端」

**否决理由**：不可 grep（SH-08）。扫整个 `ai_planner/` 禁 `llm_gateway` 会误伤 T-16。必须写死 admin/chat 三模式。

### 备选 G：B4 `power_market/` 行不扫 `llm_gateway`

**否决理由**：拆 `chat.py` 后 `from llm_gateway.chat import` 过得了 T-15（SH-10）。市场评分只许走 `llm_chat`，禁止直 import `llm_gateway.chat` / `admin`。T-15 / 本表 `power_market/` 行把 `llm_gateway` 加进**同一条** grep。T-21 Then：`power_market/` 零命中 `llm_gateway`。

## 证据

```
读码：docker-compose.yml 服务仅 mysql / redis / backend
读码：run.py all 于 2026-09-08 已 _spawn("run_spider.py")
读码：scripts/check-arch.sh 文首「B1-B3」，无 B4、无 power_market 禁 import
读码：v1.2 B4 `power_market/` grep 无 `llm_gateway`；拆 chat.py 后 `from llm_gateway.chat import` 过 T-15（SH-10）
读码：deploy/newapi/ 独立网络，根文件未加入 newapi-net
无第四个业务进程；capability-library/backend 8765 为退役物
```

无容器 spike：拓扑沿用已部署形态；LiteLLM 镜像 tag 交 `/sre`（ADR-0014）。

## 代价与风险

| 代价 | 缓解 |
|---|---|
| 单体内仍有上帝包 `backend/services/` | B4 + 新包目录约定；不在本程序做 domains 大搬迁 |
| 根 compose 无 Worker，容器联调默认走 FR-18 空态 | 文档与 UI 空态；`run.py all` 为最小出数编排 |
| 运维多一份 LiteLLM compose | 故障域隔离的本意；runbook 分域备份 |

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/backend` | 建 `power_market/`、`llm_gateway/chat.py` 与 `admin.py`；遵守 B4 全表（grep 写死；禁「管理客户端」散文） |
| `/sre` | LiteLLM 独立 compose；根文件只挂外部网；不把网关/Worker 并进根服务表 |
| `/qa` | 回归：无工人空态 ≠ 编排漏 spawn（夹具分 `run.py all` vs `compose`） |
| 闸门 | **T-15** 落地 B4 全表（`power_market/` 同一条 grep 含 `llm_gateway`；ai_planner 只禁 admin；允许 `llm_client` import chat）+ R10 递归 + 禁网关 DSN/`create_async_engine`；**T-21 依赖该检查已绿** 且 Then 零命中 `llm_gateway` |

## 后续复审条件

公开 listed 资产持续 > 400 且 NFR-01 被打破；或市场与采集必须独立发布；或操作者关闭 Q-RELAY 并要求租户直连网关——届时另开 ADR，不在本程序内拆服务。

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-08 | proposed → accepted | v2 重写；吸收 Wave L 故障域。旧特征 adr-0010 不是本合同 |
| 2026-09-08 | accepted（补） | SH-02：B4 全表落地票钉 T-15（含 R10 递归、禁网关 DSN）；T-21 依赖已绿 |
| 2026-09-08 | accepted（补） | SH-08：B4 grep 写死；`ai_planner/` 只禁 `llm_gateway.admin`；允许 `llm_client.py` import `llm_gateway.chat`；否决「管理客户端」散文与把 `llm_chat` 挪出 `ai_planner/` |
| 2026-09-08 | accepted（补） | SH-10：`power_market/` 同一条 grep 加 `llm_gateway`；T-21 Then 零命中；市场评分只走 `llm_chat`，禁直 import `llm_gateway.chat` / `admin`；否决备选 G |
