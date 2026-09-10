# 发布清单 · feat-four-pillars-v2 冻结施工 Wave 0+L+1

> 作者：/sre｜日期：2026-09-10｜对齐 qc 闸门指纹（pytest **1331** / alembic **039**；旧 sha `c470278` 其后已重跑）
> 泳道：L4
> 上游：`06-deliver/release-opinion.md`（qc **有条件放行**）｜`04-verify/coverage.md`｜T-11 / T-14 证据
> 下游：操作者预发；**本清单不做放行决策，也不把本次写成 Wave 2/3 GA。**
> 范围：FR-01…20 + FR-70…75 + FR-30…45（T-01…T-33）。六问不代选。
> 对齐：条件 1/3/4/5 **satisfied**；条件 2 **satisfied**（18.1 Then PASS +40.56s）；条件 6 **lock**。条件 A **not PASS**（down 半格 PASS / 轮换 pending）。**禁止** LiteLLM/生产 动工。不是四柱 GA。本帽不改 coverage.md。

## 1. 变更概要与风险分级

| 项 | 内容 |
|---|---|
| 变更内容 | Wave 0 SaaS 出数环 + Wave L LiteLLM 独立故障域 + Wave 1 能力市场（listing / installs / sources / aliases） |
| 影响面 | 官网闭集、注册登录、采集出数、平台 LLM 网关 HTTP、能力市场商店/治理/安装、产品事件 |
| **风险等级** | **中**（expand-only 新表/新列；市场与网关默认关；一旦上架/安装，行留下架不清） |
| 发布策略 | 配置默认关 → 预发开 MYSQL_FIDELITY / 真 Worker / 浏览器 NFR-01 → 按租户开 `POWER_MARKET.ENABLED`；根 compose **禁止**焊入 litellm 服务 |

### 三个风险问题

| 问题 | 答 |
|---|---|
| 出问题多快能发现？ | 主站：compose HEALTHCHECK `/api/v1/health/deep` 15s 间隔（MySQL+Redis，**不**绑网关）。网关：LiteLLM `/health/liveliness` 30s。业务：超管查 `product_events`。Q-OPS-DUTY 未关 → 无已登记电话值班。 |
| 出问题多快能回滚？ | 产品面：unlist HTTP + `POWER_MARKET.ENABLED=false` + 卸安装行，SQLite 夹具 **3.29s / 16 passed**。网关：`compose down` 本帽独立 2026-09-10T03:53:38Z **exit 0**（条件 A down 半格 **PASS**）。轮换半格仍 attestation pending → 条件 A 整体 **not PASS**。`:4000` 无监听且 compose ps 空，与 down 0 一致。 |
| **出问题数据会不会坏？** | 正常回滚路径 **否**（unlist 不清 `listed_at`、安装行留、源行留）。**禁止**生产 `alembic downgrade` 过 037：真库实测 errno 1553（先 drop index 后 FK 仍在）。SALT 轮换 ≠ 回滚。 |

## 2. 门禁核对（引用 qc 指纹，不接受口头声称）

来源：`06-deliver/release-opinion.md` §2。决策对象 = 冻结施工工作树（cond 3–5 + 039 + Pricing + D4 conftest 之后）。旧 sha `c470278` **不是**本轮决策对象；qc **已重跑闸门**，不因 sha 漂移阻塞。

| 闸门 | 命令 | 退出码 | 状态 |
|---|---|---|---|
| 单元/集成 | `uv run pytest -x -q backend/tests` | 0（**1331** passed, 35 skipped） | ✅ |
| 架构检查 | `bash tools/check/arch.sh` | 0 | ✅ |
| 构建 | `npm run build --prefix frontend/admin` | 0 | ✅ |
| 构建 | `npm run build --prefix frontend/official` | 0 | ✅ |
| 迁移校验 | `bash tools/check/db_migrations.sh` | 0（head **039**） | ✅ 039 DATETIME(6) 已在 `b8b5f85`。合主干仍须含 **031–038**（039 Revises 038）。生产禁止 down past 037 |
| SDLC 工件 | `check-sdlc.sh --require --hat verify` / `--hat qc` | 0 / 0 | ✅ |
| 覆盖矩阵 | `check-matrix.py coverage.md spec.md` | 0（56 条 FR/NFR 有行） | ✅ 机械有行 ≠ Then 有效 |
| MYSQL_FIDELITY 方言批 | 含 37.6 | 0（22 passed） | ✅ 预发一次性 |
| E2E | — | — | ➖ `e2e: null`；浏览器 NFR-01 不得用 TestClient 顶 |

**门禁指纹**：上表（qc 已重跑）。35 skipped = 默认未开 MYSQL_FIDELITY 的真库 skip。方言批另开开关 22 passed。`downgrade base` 仍 1553 → **生产禁止** downgrade past 037。

- [x] 已配置闸门全绿（qc 已记：pytest 1331 / arch 0 / 双 build 0 / migration 039）
- [x] skipped 已解释
- [x] 未配置 E2E 有理由
- [x] 条件 1 **satisfied**（整跑 pytest + 双前端 build）
- [x] 条件 2 **satisfied**：方言 37.6 + NFR-01 浏览器 **satisfied**；GWT-18.1 Then **PASS**（task#2 completed **+40.56s**，result_count=1，export 200 rows 1）。条件 A 仍 not PASS。不得写四柱 GA / 允许动工
- [x] 条件 3 **satisfied**（IM-24 `asset_type=command` src_sync；非本帽执行）
- [x] 条件 4 **satisfied**（GWT-01.1 Pricing/Usage；Register 手写 = qc 条件 B，投放前）
- [x] 条件 5 **satisfied**（GWT-06.1 OperationLog who/what；非本帽执行）
- [x] 条件 6 **lock**（FR-50/51/60/61 ➖；六问开放；不是四柱 GA）

**门禁未全绿则不把预发当生产。** 豁免只走 qc 已写条件表，不在本帽改结论。GWT-18.1 Then 本轮 PASS 不是脚本闸；qc 矩阵翻格交 `/qa`。Then PASS **不等于** 条件 A PASS，也**不等于**允许 LiteLLM/生产 动工。

### Alembic 031–039（product_events → aliases → listed_at fsp）

| rev | 内容 | 生产回滚 |
|---|---|---|
| 031 | `product_events` CREATE | **保留表**；关上报即可。down = DROP 表（有损） |
| 032 | operator `menu:llm` JSON 追加 | 配 `LLM.ENABLED=false`；不必 down |
| 033 | `capability_commands` / `capability_components` | expand-only；down = DROP 两表 |
| 034 | `listing_state` / license 列 | **unlist**；down = DROP 列（有损） |
| 035 | `capability_installs` + `host_compat` | **卸行**；down = DROP 表+列 |
| 036 | `listed_at`；菜单改「能力市场」 | unlist **不清** `listed_at`；down = DROP 列 |
| 037 | `capability_sources` + origin 列 | **`POWER_MARKET.ENABLED=false`**；**禁止** down（真库 1553） |
| 038 | `capability_aliases` | 商店随 unlist 404；down 仅空库可逆 |
| 039 | `listed_at` DATETIME → DATETIME(6) | expand-only 精度加宽；生产 **不要** down 039（截断微秒）。隔离 039↔038 已由 dba 实测 exit 0 |

head：qc 闸门 **`039`**。039 已在 `b8b5f85`。**031–038 仍未入库** → 合主干对象必须含 027→031…→039 全链。LiteLLM Postgres **不进**本链。业务 eval 库 `upgrade 039` exit 0。生产 **禁止** downgrade past 037。

### LiteLLM 编排钉死

| 项 | 值 |
|---|---|
| 独立 compose | `deploy/litellm/docker-compose.yml` |
| 镜像 | `ghcr.io/berriai/litellm:v1.100.0`（禁 `:latest` / `main-latest` / `main-stable`） |
| 网关库 | `postgres:16.10-alpine`；`./postgres-data/` gitignore |
| 根 `docker-compose.yml` services | mysql / redis / backend **仅此三** |
| 根网络 | `networks.litellm-net.external: true` 仅此；无 litellm 服务 |

## 3. 需真实环境验证清单（qc 条件 2）

coverage §5 方言 + GWT-18.1 + NFR-01 浏览器。**SQLite / TestClient 不得顶真库 / 浏览器。**

| 用例 | 原因 | 本宿主 2026-09-10 结果 |
|---|---|---|
| Alembic upgrade → 039 | 空库全链 | ✅ 本轮 MYSQL_FIDELITY `test_fresh_upgrade_head_matches_create_all` + `test_bootstrapped_db_upgrade_head_is_noop`（head **039**）；先前隔离库 `upgrade 038` exit 0 |
| 038 ↔ 037 | alias 表 expand 可逆 | ✅ `downgrade 037` + `upgrade 038` 各 exit 0（隔离 schema，随后 DROP）。本轮未在业务库 down |
| 039 ↔ 038 | listed_at fsp 可逆（隔离） | ✅ dba 隔离 up-down-up exit **0**。业务库 **禁止** down 039 |
| 037 → 036 及 `downgrade base` | 源表/列 down | ❌ `test_downgrade_base_leaves_nothing`：`DROP INDEX idx_skill_jobs_source` errno **1553**（FK 仍需要该索引）。本轮未重跑。**生产禁止 down 037** |
| TC-37.6 listed_at | DATETIME 精度 | ✅ 本帽独立 MYSQL_FIDELITY=1 `test_gwt_37_6_listed_at_survives_unlist`：**1 passed in 1.86s** exit **0**（业务库当时仍 038；独立 schema `create_all`）。同批方言 **22 passed in 17.79s** exit **0**。dba 039 DATETIME(6)；业务库随后 expand-only `upgrade 039` exit 0，`listed_at`=`datetime(6)`。**未**用编排器口述盖章。详见 `qc-cond-2-preprod.md` §1.1 |
| TC-45.4 存活 alias 唯一 | NULL 唯一 | ✅ 本轮 MYSQL_FIDELITY `test_gwt_45_4_conflict_live_alias_both_unchanged` |
| TC-34.9 `host_compat` NULL vs `[]` | JSON | ✅ 本轮 `test_gwt_34_9_undeclared_host_compat_allows_any` |
| TC-42.2 override TINYINT | 方言 | ✅ 本轮 `test_gwt_42_2_override_appears_still_gated` |
| TC-33.4/33.5 分页 | LIMIT/OFFSET | ✅ 本轮 `test_skill_public_api.py` 随 MYSQL_FIDELITY（同批 22 passed 含分页） |
| ESC-2 NULL 排序 | NULLS LAST | ✅ 本轮 `test_null_aware_sort_roundtrip_mysql_fidelity` |
| TC-18.1 真 Worker 120s | FakeRedis ≠ `run.py spider` | **PASS** live（idle-close 30s + `run.py restart spider` pid=73146 @ 10:40:38）：task **#2** example+httpbin。`result_count=1` @ **+6.1s** 仍 running；**completed +40.56s** result_count=1；export **200** rows **1**。Then「120 秒内任务进入完成且条数>0」**PASS**。对照 task#1 completed +129s（当时 idle 120s）。非 FakeRedis。见 `qc-cond-2-preprod.md` §2。coverage.md 本帽不改 |
| TC-N01 浏览器卡片可见 P95 | TestClient SQLite 400 行 ≠ 浏览器 | ✅ Chrome 152 headless + `/tmp` playwright-core（**未**进仓库）。`http://127.0.0.1:9113/capabilities` 20 次均见 **20** 张 `.capability-market__card`、首卡 `NFR卡片399`。原始样见 `qc-cond-2-preprod.md` §3.3；P95 **1.444558s &lt; 2s**（下标 `int(0.95*(n-1))`）。**未**用 TestClient / API P95 顶格。 |

MYSQL_FIDELITY 方言批（含 37.6 / 不含 `downgrade base`）：本帽独立 37.6 **1 passed in 1.86s** exit **0**；同节点全批 **22 passed in 17.79s** exit **0**。`downgrade base` 仍 errno **1553**（本轮未重跑）。隔离库 038↔037 先前各 exit **0**；039↔038 隔离已由 dba exit **0**。

原业务库 stamp 孤儿 `030` → restamp `027` + `upgrade 038` exit **0**（NFR-01 前置）。本轮 expand-only `upgrade 039` exit **0**（live `listed_at` DATETIME(6)）。命令+出口见 `06-deliver/qc-cond-2-preprod.md`。

- [x] 方言清单已在本机真库跑过一遍（含 37.6 本帽独立 PASS；方言批 22 passed exit 0）
- [x] 真 Worker 18.1 已跑（Then **PASS** completed +40.56s；result_count=1；export 200 rows 1）
- [x] 浏览器 NFR-01 卡片可见（Chrome 20× 首卡 `NFR卡片399`；P95 1.445s）
- [ ] 结果回填 `/qa` `test-report.md`（本帽不改 coverage.md；矩阵 18.1 保持 ⚠️）

qc 条件 1–6（与 `release-opinion.md` 对齐；3–5 非本帽执行）：

| # | 条件 | 状态 | 责任 |
|---|---|---|---|
| 1 | 整跑 pytest + 双前端 build | **satisfied**（1331 / 双 build 0） | qc 指纹 |
| 2 | 预发：方言 + 18.1 + NFR-01 | **satisfied**：37.6 + NFR-01 + GWT-18.1 Then **PASS**（+40.56s） | `/sre` |
| 3 | IM-24：同步写入 `asset_type=command` | **satisfied** | `/backend` |
| 4 | 官网投放前 GWT-01.1 定价免费档三数 | **satisfied**（Register 手写 = 条件 B） | `/frontend` |
| 5 | 超管扫描当合规前 GWT-06.1 OperationLog | **satisfied** | `/backend` |
| 6 | Wave 2/3 与六问保持 stub/开放 | **lock**（FR-50/51/60/61 ➖；不是四柱 GA） | 操作者 |
| A | 预发当生产 / 开 LiteLLM 前：dockerd `compose down`；机外轮换 `44e9446` | **not PASS**：down 半格 **PASS**（本帽独立 2026-09-10T03:53:38Z **exit 0**）。轮换 = **attestation pending operator**（`rotation-44e9446.md` 无 `rotated:` 行；本帽不自勾「已轮换」）。证明前 **禁止** `LLM.ENABLED=true` / litellm `compose up`。**动工 = NO** | `/sre` 操作者 |
| B | 官网对外投放前 Register 免费档三数 | 投放前（非本帽） | `/frontend` |

## 4. 回滚方案（**已在本机可执行路径上跑过**）

listing / install / source / alias **只 expand**：生产回滚 = 关可见性与开关，**不是** DROP。

### 4.1 产品回滚（优先，秒级）

| 对象 | 动作 | 命令 / 接口 | 本宿主 |
|---|---|---|---|
| 上架 | unlist；`listed_at` 保留 | `PATCH /api/v1/capabilities/{type}/{name}/listing` JSON `{"listing_state":"unlisted"}` 仅超管 | ✅ `test_gwt_37_6_listed_at_survives_unlist`（SQLite + MYSQL_FIDELITY 1.86s exit 0） |
| 安装 | 卸这一行；unlist 残留可卸不可新订 | `DELETE /api/v1/capabilities/installs/{install_id}` | ✅ `test_gwt_35_1_two_rows_can_uninstall` + `test_gwt_35_3_unlist_residual_operator_can_uninstall` |
| 源 | **无** HTTP disable；杀开关是配置 | `POWER_MARKET.ENABLED=false`（yml 或 `AUTO_AGENTS_POWER_MARKET__ENABLED=false`）后重启 API。D16：扫描回本机 `plugins/` | ✅ `test_gwt_38_5_d16_fallback_local_scan`；默认 yml 已是 `false` |
| 短名 | 表保留；商店随 unlist 404 | 勿 `downgrade 038` 于有数据的库（DROP `capability_aliases` 有损） | 结构 038↔037 ✅ 仅隔离空库 |

默认已关：`config/default/power_market.yml` `ENABLED: false`；`config/default/llm.yml` `ENABLED: false`。

### 4.2 网关故障域

```
# 语法（不需要 daemon）
docker compose -f deploy/litellm/docker-compose.yml config -q
docker compose -f docker-compose.yml config -q

# 停独立故障域（需要 dockerd）
docker compose -f deploy/litellm/docker-compose.yml down --remove-orphans

# 平台路径回滚窗（不是完成态；禁止把 new-api 请回运行时）
# yml 或：
AUTO_AGENTS_LLM__DATA_PLANE=providers
```

本宿主 2026-09-10T03:53:38Z（本帽独立再跑）：`docker info` **0**（ServerVersion=29.4.0）；sock `~/.docker/run/docker.sock`；两条 `config -q` **exit 0**；`down --remove-orphans` **exit 0**（idempotent 再跑仍 0；compose ps 空）。`lsof :4000` 无监听。SALT **不可**当普通回滚。轮换证据见 `06-deliver/rotation-44e9446.md`（**attestation pending operator**）。条件 A 整体 **not PASS**。

根栈先于网关：`docker network create litellm-net`。backend **尚未**加入该网。

### 4.3 数据回滚（结构，仅隔离库）

```
# 空库 upgrade head = 039（本轮 MYSQL_FIDELITY 方言批含此测，exit 0）
MYSQL_FIDELITY=1 MYSQL_FIDELITY_HOST=127.0.0.1 MYSQL_FIDELITY_PORT=3306 \
  MYSQL_FIDELITY_USER=root MYSQL_FIDELITY_PASSWORD="$MYSQL_FIDELITY_PASSWORD" \
  uv run pytest -q backend/tests/test_alembic_baseline.py::test_fresh_upgrade_head_matches_create_all

# 仅 038↔037 可逆（隔离 schema + ALEMBIC_URL，禁止指向业务库）
cd backend && uv run alembic -c alembic.ini upgrade 038     # exit 0
cd backend && uv run alembic -c alembic.ini downgrade 037   # exit 0  （DROP aliases）
cd backend && uv run alembic -c alembic.ini upgrade 038     # exit 0

# 039↔038 仅隔离库（dba 已 exit 0）。业务库禁止 down 039 / past 037
```

`downgrade base` / `downgrade 036`：**不要在生产跑**。037 `downgrade()` 先 `drop_index idx_skill_jobs_source` 再 drop FK，MySQL 1553。转 `/dba` 修顺序；本帽不改 OLTP。

**数据恢复能力**：生产路径 = 关开关 + unlist + 卸行，表仍在。Alembic down 031–037 = 丢事件/列/表。

### 4.4 配置回滚

| 配置项 | 发布值 | 安全缺省 | 回滚 |
|---|---|---|---|
| `POWER_MARKET.ENABLED` | 预发才可 true | **false** | 改 yml/env + 重启 API |
| `LLM.ENABLED` | 预发才可 true | **false** | 同上 |
| `LLM.DATA_PLANE` | `litellm` | 回滚窗 `providers` | `AUTO_AGENTS_LLM__DATA_PLANE=providers`；**不是** GA |
| `NEWAPI.ENABLED` | tombstone false | false | **不要** up `deploy/newapi` |
| LiteLLM `.env` | 离树 | 不提交 | compose down；勿改 SALT |

### 数据兼容性

- [x] 新列可空或有 server_default（`listing_state=unlisted`）；旧代码忽略新表
- [x] 新枚举 `command/agent/team` + 一周期 `expert`：消费方按合同容忍
- [x] 未做生产收缩 DDL（UNIQUE Step3 仍未升；本冻结只 expand）
- [x] 037 down **不可**当兼容回滚（已实测失败）

### 回滚窗口与限制

| 项 | 内容 |
|---|---|
| 回滚窗口 | 未上架/未开市场：无限制。已 listed / 已订：unlist 后商店消失、安装行残留，事件已追加不可撤回 |
| **不可撤回** | `product_events` / `market_*` 已写入；对外邮件无（本波无）；SALT 一改网关库内上游凭据无法解密 |
| 执行人权限 | 超管才能 PATCH listing / PUT alias / 登记源。经办可卸本企业安装行。Q-OPS-DUTY 未指定电话人 |

**实测耗时（本宿主，非预发 SLA）**：产品夹具 3.29s；隔离库 038 全链 upgrade ~7s；038↔037 秒级。GWT-18.1 Then completed **+40.56s**。compose down **exit 0**（2026-09-10T03:53:38Z；条件 A down 半格 **PASS**；栈本已停，命令秒级返回）。轮换半格未过。

## 5. 监控接线

本冻结 **无** 独立 Grafana/Prometheus 面板。值班看进程日志 + 深探测 + 超管事件查询。Q-OPS-DUTY / Q-OPS-COLLECT 未关，接收人不得发明。

| 类 | 指标 | 已接 | 面板 |
|---|---|---|---|
| 可用性 | `GET /api/v1/health/deep` → 200 且 `checks.mysql/redis=healthy`；失败 **503**（P-SRE-04） | ☑ compose HEALTHCHECK | 无；watchdog 打 deep |
| 可用性 | LiteLLM `GET /health/liveliness`（**不要**并进 deep） | ☑ 独立 compose healthcheck | 无 |
| 延迟 | 市场列表 / 官网卡片 P95（NFR-01 红线 2s **浏览器**） | ☑ 预发 Chrome P95 **1.445s**（20 张卡可见） | 无持续面板；本轮一次性 |
| 饱和度 | Redis 队列深度（采集 Worker）；MySQL 连接 | ☐ 无导出 | `run.py status` / `lsof` |
| 饱和度 | LiteLLM 单副本、无 Redis；多副本前勿扩 | ☑ README §1.1 | — |
| **业务** | `product_events.event_name`：`task_completed` / `market_subscribe` / `market_listing_changed`；超管可查，租户 404 | ☑ FR-15/43 | 无看板 |

### 告警（每条带处理指引）

接收：Q-OPS-DUTY 未决 → 暂「操作者 / 超管」；升级条件同样待该问。

| 告警 | 级别 | 阈值+持续时间 | 处理指引 |
|---|---|---|---|
| 主站 deep 503 | P0 | HEALTHCHECK 连续 3 次失败（compose retries=3，~45s） | 1) `curl -i $API/api/v1/health/deep` 看 checks。2) MySQL/Redis `ping`。3) 僵尸端口：`lsof -iTCP:9111`（P-SRE-06）。4) 先停发布/回滚配置，再查日志。**不要**把网关 liveliness 并进此告警。 |
| 网关 liveliness 失败 | P1 | compose retries=5 / start_period 90s | 1) `docker compose -f deploy/litellm/docker-compose.yml ps`。2) 四动作应走 GWT-74.x 句，主站 deep 仍须绿。3) 缓解：`DATA_PLANE=providers` 或 `LLM.ENABLED=false`。4) 15min 不恢复升 P0（仅当平台路径已对租户打开）。 |
| 采集无工人 | P1 | 任务停在 queued；GWT-18.2 句 | 1) `uv run python run.py status`。2) 起 Worker。3) 禁止把 FakeRedis 回流当已恢复。 |
| 市场误上架 | P1 | 商店出现未确认第三方 / 命令卡 | 1) unlist 该行。2) `POWER_MARKET.ENABLED=false`。3) IM-24：同步不得写 command。 |
| 密钥进树 | P0 | `arch.sh` FR-14 红 / `git ls-files deploy/litellm/config.gen.yaml` 非空 | 1) `git rm --cached`。2) **机外轮换**曾进 `44e9446` 的上游凭据（证据只写「已轮换」）。3) 可选 filter-repo，本清单不执行。 |

- [x] 每条有原因 + 步骤 + 缓解 + 升级
- [x] 非全 P0
- [ ] 抑制/聚合：无告警网，预发用手工
- [x] 阈值带 retries/start_period

## 6. 灰度与放量判据（提前定）

| 档 | 范围 | 观察时长 |
|---|---|---|
| 0 | 生产配置保持 `POWER_MARKET.ENABLED=false` + `LLM.ENABLED=false`；只上代码+039 | 门禁指纹对齐 |
| 1 | 预发：MYSQL_FIDELITY 方言 37.6 PASS + 浏览器 NFR-01 PASS + 真 Worker 18.1 Then **PASS**（completed +40.56s）。**禁止**进档 2 开 LiteLLM/生产 | 覆盖一次完整出数 + 一次列表打开 |
| 2 | 单内部租户开市场；网关独立 compose；根仍无 litellm 服务 | ≥2h，含一次 src_sync（若开源） |
| 3 | 更多租户；**仍非** Wave 2/3 GA | 持续；支付/渠道组/令牌仍 stub |

### 基线

本波无生产同期流量。预发用档 1 实测填 P95 / 错误率，禁止用「发布前一分钟」。

### 放量（全部满足）

- ✅ deep 非 503；无新增未知异常类型
- ✅ 浏览器列表卡片可见 P95 ≤ 2s（NFR-01）
- ✅ 无 P0；市场无未确认 listed 第三方
- ✅ 六问仍开放；定价付费档仍「预告不可购买」

### 回滚（任一即回，**不讨论**）

- ❌ deep 503 持续 > 2min
- ❌ 浏览器 P95 > 4s（2× 红线）
- ❌ 商店出现应付费可买 / 渠道组令牌（六问被偷关）
- ❌ FR-14 跟踪树出现 `config.gen.yaml` 或明文 Key
- ❌ 数据不一致（安装行跨租户、alias 双活）

### 低频路径

| 路径 | 观察 |
|---|---|
| 真 Worker 入队→回流→导出 | **PASS** 档 1：task#2 +6.1s 出数仍 running；completed **+40.56s** result_count=1；export 200 rows 1 |
| 网关停 vs 满额分格（74.x） | 集成已有；预发可抽一条规划 |
| src_sync 第三方保持 unlisted | ☐ 仅当档 2 打开 ENABLED |

## 7. 容量评估

| 项 | 数字 |
|---|---|
| 目录规模 | db-spec：assets ~320；事件/市场表从 0 长 |
| LiteLLM | 单副本、无 Redis；限流跨实例前不要扩副本 |
| 根栈 | mysql 512m / redis 256m / backend 1g（compose deploy.limits，联调量级） |
| 采集 Worker | 本宿主 0；预发按队列深度加，禁止用假回流估容量 |
| **当前配置** | 默认关市场/LLM → 增量接近 0 |
| 余量 | 开市场前用档 1 P95 再估；不足则先关 ENABLED 而非扩网关进根 compose |

跨 arch：镜像必须在 CI linux/amd64 构建（P-SRE-02）。lockfile 用 npm@10（P-SRE-01）。

## 8. 部署步骤

```
1. 确认门禁指纹与 qc 已重跑闸门对齐（pytest 1331 / arch 0 / 双 build 0 / migration **039**；旧 sha `c470278` 不是决策对象）
2. 密钥：.env / deploy/litellm/.env / config.gen.yaml 离树；确认 git ls-files config.gen.yaml 空
3. 轮换 44e9446 曾跟踪生成配置里的上游凭据（机外 DeepSeek + Moonshot）。证据只许 `06-deliver/rotation-44e9446.md`（或 ignore sibling）一行 `rotated: YYYY-MM-DD`。**无该行则禁止 `LLM.ENABLED=true` / litellm compose up。本帽不自写已轮换。**
4. 业务库：alembic upgrade 039（expand-only；039 = listed_at DATETIME(6)）。**合主干必须含 039 文件**。禁止 stamp 028/029/030。禁止 down past 037。禁止把 LiteLLM PG 写进 Alembic
5. 根 compose：只 mysql/redis/backend + networks.litellm-net.external；若网不存在则 docker network create litellm-net
6. 保持 POWER_MARKET.ENABLED=false、LLM.ENABLED=false 直到档 1 过
7. 需要网关时：cp deploy/litellm/.env.example .env（占位全改）→ compose -f deploy/litellm/docker-compose.yml up -d
8. 验证：curl -f $API/api/v1/health/deep ；不要用网关 liveliness 当主站活
9. 档 1：MYSQL_FIDELITY 方言 + 真 Worker 18.1 Then PASS（+40.56s）+ 浏览器 NFR-01。**禁止**宣称四柱 GA / LiteLLM 动工
10. 档 2：单租户开市场；出问题走 §4.1 unlist / ENABLED=false / compose down
```

**每步回退**：

| 步 | 回退 |
|---|---|
| 4 | **不要** down 037；代码回退到只读旧应用（新列可空/有 default） |
| 6–7 | ENABLED=false；`compose down` litellm；`DATA_PLANE=providers` |
| 10 | unlist + 卸行 + ENABLED=false |

## 9. 发布窗口与人员

| 项 | 内容 |
|---|---|
| 建议窗口 | 工作日。条件 4 GWT-01.1 **satisfied**。官网对外投放前仍走 qc 条件 B：Register 手写三数未对齐则投放范围不含注册页卖点三数。对外/发布说明不得写四柱 GA / LiteLLM 已开 |
| 维护窗口 | 038 expand 秒级，无需 gh-ost（migration-review §4） |
| 值班 | Q-OPS-DUTY 未决 |
| 回滚决策 | 操作者；超管执行 unlist |
| 相关方 | 不得对外说四柱 GA / 支付已开 / 渠道组可买 |

## 10. 检查结论（事实，不做放行）

| 项 | 状态 |
|---|---|
| 门禁 | qc 已重跑全绿：pytest **1331** / arch 0 / 双 build 0 / migration **039** |
| 需真实环境 | 方言 37.6 **PASS**（1 passed in 1.86s exit 0）；同批 **22 passed in 17.79s** exit **0**。GWT-18.1 Then **PASS**（task#2 completed **+40.56s**，result_count=1，export 200 rows 1）。NFR-01 浏览器卡片可见 P95=**1.445s**（20 张 `NFR卡片*`；非 TestClient） |
| 回滚方案 | 产品路径已实测（unlist / 卸安装 / ENABLED=false）；038↔037 隔离库已实测；039↔038 隔离 dba exit 0；037 down **失败已记录**；compose down **PASS**（exit 0，2026-09-10T03:53:38Z） |
| 数据兼容 | expand-only；生产禁止收缩 down；生产禁止 down past 037 |
| 监控 | deep + liveliness + 事件查询；无独立面板；值班问未关 |
| 告警 | 5 条带指引；无抑制网 |
| 灰度判据 | 已定；默认 `POWER_MARKET.ENABLED=false` / `LLM.ENABLED=false` |
| 容量 | 默认关时可上代码；开市场前要档 1 |
| 密钥 | `git ls-files deploy/litellm/config.gen.yaml` **空**；arch FR-14 ✓。HEAD blob 仍在（staged `D`，本帽不 commit）。史 `44e9446` 7 行明文 api_key。轮换 = **attestation pending operator**（`rotation-44e9446.md` 无 `rotated:`；本帽不自勾已轮换） |
| **阻塞预发当生产的项** | 条件 2 **satisfied**（Then PASS +40.56s）。**仍禁止** LiteLLM/生产 动工（**动工 = NO**）。条件 1/3/4/5 **satisfied**。条件 6 **lock**。条件 A **not PASS**：compose down **PASS**（exit 0，2026-09-10T03:53:38Z）；轮换 **attestation pending operator**。合主干须含 **039**（工作树 `039_listed_at_datetime_fsp.py` 仍 `??`）以及 staged untrack `config.gen.yaml`。生产禁止 down past 037。默认 ENABLED=false。根 compose **无** litellm 服务。孤儿 stamp `030` 已 restamp→038→**039**（仅本机 eval 库）。**不是**四柱 GA。qc **有条件放行**（本帽不改 release-opinion） |
| Wave 2/3 | **未 GA**。FR-50/51/60/61 仍 ➖ |
| 六问 | Q-VOICE / Q-PRICE / Q-RELAY / Q-MARKET-USER / Q-BILL / Q-AGPL / Q-OPS-DUTY / Q-OPS-COLLECT **开放，不代选** |

**放行决策 → `/qc`（已：有条件放行）。** 本文件只把条件变成可执行回滚与预发步骤。

## 11. 自检

- [x] 风险已分级
- [x] 三个风险问题已答
- [x] 门禁引用命令+退出码+sha
- [x] 真环境清单已跑能跑的，未跑的未勾
- [x] 回滚是命令+出口，不是只散文；037 失败未粉饰
- [x] 不可撤回副作用已列
- [x] 未硬编码密钥；端口来自 compose/yml
- [x] 未宣称 Wave 2/3 GA；六问未代选；条件 6 lock
- [x] 根 compose 无 litellm 服务；默认 ENABLED=false
- [x] QA-01：§0 / 清单已改写；task#2 completed +40.56s Then PASS；对照 +129s 不作本轮 Then。不得把条件 2 satisfied 写成四柱 GA / 允许动工
- [x] qc 条件 A：dockerd `compose down`（本轮 **exit 0**，down 半格 **PASS**）
- [ ] qc 条件 A：机外轮换 `44e9446`（**attestation pending operator**；本帽不自勾已轮换）
- [x] 未做放行决策

## 12. 自测证据

### 产品回滚夹具（SQLite）

```
$ uv run pytest -x -q \
  backend/tests/test_t28_listing.py::test_gwt_37_6_listed_at_survives_unlist \
  backend/tests/test_t29_sources.py::test_gwt_38_5_d16_fallback_local_scan \
  backend/tests/test_t26_installs.py::test_gwt_35_1_two_rows_can_uninstall \
  backend/tests/test_t26_installs.py::test_gwt_35_3_unlist_residual_operator_can_uninstall \
  backend/tests/test_fr14_secrets_off_tree.py \
  backend/tests/test_t20_retire_newapi.py
................
16 passed in 3.29s
```

exit 0

### FR-14

```
$ git ls-files deploy/litellm/config.gen.yaml
```

（空，0 行）exit 0

```
$ git grep -lE 'sk-[A-Za-z0-9]{10,}' -- deploy/ config/
```

无命中；git grep exit 1

```
--- 发布物密钥（FR-14）---
✓ FR-14: config.gen.yaml 不在跟踪树
✓ FR-14: 跟踪的 deploy/config 无上游 Key 样例模式
```

`arch.sh` 该段 ✓。史：`44e9446` 曾 `create mode deploy/litellm/config.gen.yaml`（轮换机外）。

### compose 语法 vs down（条件 A down 半格，本帽独立 2026-09-10T03:53:38Z）

先前 02:43:36Z `down` exit 1（当时 sock 缺）**不作本半格**。本轮 dockerd 已起：

```
$ date -u +%Y-%m-%dT%H:%M:%SZ
2026-09-10T03:53:38Z

$ docker info --format 'ServerVersion={{.ServerVersion}} Server={{.Name}}'
ServerVersion=29.4.0 Server=docker-desktop
INFO_EXIT:0

$ ls -la ~/.docker/run/docker.sock /var/run/docker.sock
srwxr-xr-x@ 1 xuyun  staff  0  9月 10 11:50 /Users/xuyun/.docker/run/docker.sock
lrwxr-xr-x@ 1 root   daemon 36  9月 10 11:50 /var/run/docker.sock -> /Users/xuyun/.docker/run/docker.sock

$ docker compose -f /Users/xuyun/auto_agents/deploy/litellm/docker-compose.yml down --remove-orphans
DOWN_EXIT:0

$ docker compose -f /Users/xuyun/auto_agents/deploy/litellm/docker-compose.yml config -q
LITELLM_CONFIG_EXIT:0
$ docker compose -f /Users/xuyun/auto_agents/docker-compose.yml config -q
ROOT_CONFIG_EXIT:0
$ lsof -nP -iTCP:4000 -sTCP:LISTEN
lsof :4000 none
$ git ls-files deploy/litellm/config.gen.yaml
```

（空，0 行）LSFILES_EXIT:0

idempotent 再跑仍 `DOWN_EXIT:0`。`compose ps -a` 空表，PS_EXIT:0。

条件 A compose-down 半格 **PASS**。轮换半格仍 **not PASS** → 条件 A 整体 **not PASS**。**动工 = NO**。

镜像钉死（文件）：`image: ghcr.io/berriai/litellm:v1.100.0`；根 `litellm-net.external: true`。

### 44e9446 轮换（条件 A）

见 `06-deliver/rotation-44e9446.md`。提供商：DeepSeek、Moonshot。7 行明文 `api_key`（值不复制）。

```
$ git ls-files deploy/litellm/config.gen.yaml
```

（空，0 行）exit 0。arch FR-14 ✓。证明行 `rotated: YYYY-MM-DD`：**无**。状态 = **attestation pending operator**。本帽 **未** 勾已轮换。无证明前禁止 `LLM.ENABLED=true` / litellm compose up。

### Alembic

```
$ cd backend && uv run alembic -c alembic.ini heads
039 (head)
exit: 0
```

隔离库：upgrade 038 exit 0；downgrade 037 exit 0；upgrade 038 exit 0；随后 DROP DATABASE。039↔038 隔离 up-down-up 已由 dba exit 0。业务库 **未** down。

```
FAILED test_downgrade_base_leaves_nothing
OperationalError: (1553, "Cannot drop index 'idx_skill_jobs_source': needed in a foreign key constraint")
1 failed, 2 passed in 13.42s
```

`downgrade base` 仍禁止（1553）；本轮未重跑。

MYSQL_FIDELITY 37.6 本帽独立：`1 passed in 1.86s` exit **0**。同节点方言批：`22 passed in 17.79s` exit **0**。业务库 `upgrade 039` exit **0**；`listed_at`=`datetime(6)`。

### 本宿主过程（条件 2 再跑前）

`:3306` mysqld LISTEN；`:6379` redis LISTEN；`:9111` / `:4000` 无监听；无 scrapy worker。

### 条件 2 再跑（2026-09-10 同日第二轮）

原样命令+退出码：`06-deliver/qc-cond-2-preprod.md`（冻结施工集预发，**非**四柱 GA）。

```
MYSQL_FIDELITY 37.6 本帽独立：1 passed in 1.86s
exit: 0
MYSQL_FIDELITY 方言批（含 37.6）：22 passed in 17.79s
exit: 0
alembic upgrade 039（业务库 auto_agents，expand-only）：exit 0；current 039；listed_at=datetime(6)
test_downgrade_base_leaves_nothing：仍 1553（本轮未重跑）
隔离库 038↔037：先前各 exit 0；039↔038 隔离：dba exit 0
run.py start backend / official：各 exit 0（先前轮；本轮未杀 backend）
run.py restart spider：pid=73146 STARTED 10:40:38（IdleAutoClose 30s）
GWT-18.1 live task#2：result_count=1 @ +6.1s 仍 running；completed +40.56s result_count=1；export 200 rows 1；Then PASS
对照 task#1：completed +129s（当时 idle 120s；不作本轮 Then）
NFR-01 API 20× GET /api/v1/public/capabilities?page=1&page_size=20：P95=0.020032s total=400（不顶格）
NFR-01 浏览器 20× Chrome 152 headless /capabilities：20 卡可见 首卡 NFR卡片399；P95=1.444558s exit 0（本轮不改）
compose down --remove-orphans（本帽独立 2026-09-10T03:53:38Z）：exit 0（条件 A down 半格 PASS）
```

条件 2 **satisfied**：37.6 + NFR-01 浏览器 + GWT-18.1 Then PASS（+40.56s）。条件 1/3/4/5 satisfied。条件 6 lock。条件 A **not PASS**（compose down PASS；轮换 attestation pending operator）。**禁止** LiteLLM/生产 动工（**动工 = NO**）。合主干须含 039（文件在工作树、仍 `??`）。生产禁止 down past 037。默认 ENABLED=false。根 compose 无 litellm。非四柱 GA。qc **有条件放行**（本帽不改 release-opinion）。
