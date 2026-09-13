# 发布清单 · upgrade-four-pillars N1–N4

> 作者：/sre｜日期：2026-09-13｜祖先 commit：`99e2f95`（工作区 N1–N4 **未冻结 SHA**）
> 泳道：L3｜票 T-01…T-27
> 上游：`06-deliver/release-opinion.md`（qc **有条件放行** N1–N4 v1.2）｜`04-verify/coverage.md`｜`02-shape/contract.md`｜T-01…T-27 evidence
> 下游：操作者预发/合入；产品运营 `ops` 做人侧 enablement（**本帽不写用户公告 / CS 话术**）
> **本清单不做放行决策，只陈述检查结果。禁止写成四柱 GA。禁止把结账空态写成支付已通。禁止把 HMAC 夹具写成 live 支付宝/微信。禁止把 FakeRedis 写成 live 120s 北极星。禁止把值班行「活」写成中转 SKU `active`。禁止写 SLA 数字。**

本文件替换盘上 **N1-stale**（045-only / pytest 1570）清单。N1 机器事实仍成立的保留；追加 N2 / N3 / N4 机器步骤。qc 条件 1–9 仍成立（本帽执行面 = **3 / 4 / 5 / 6 / 7 / 9**；条件 1–2 文案面 → ops/pm；条件 8 = 本文件）。**不改** qc 有条件放行。

本轮 deliver 返工关闭 `05-review/findings.md` **QA-01…QA-04**（文档闸，不改产品代码）：

| 编号 | 处置 |
|---|---|
| QA-01 | 046 head **禁止** `alembic downgrade 044`。仅 `alembic current` **= 045** 才允许 `downgrade 044`。046 回滚 = 停工人 / PUT 关市 / DELETE 凭据 / 反代摘 notify。046→044 毁掉商户密文与 SKU 行，不可还原 |
| QA-02 | 租户打 POWER_MARKET 开关期望 **403 FORBIDDEN**（GWT-U11.3）。404 同形只钉 T-09 / T-15 / T-27。预期 403 **不是** P1 泄面 |
| QA-03 | 046 **不是**纯 ADD 可空列+小表：含 ALTER、STORED GENERATED UNIQUE、`plans.updated_at` NOT NULL。低峰跑；不是用户停机公告 |
| QA-04 | **禁止任何** `compose down`（不带 `-v` 已丢 Redis 队列/心跳；带 `-v` 再丢 MySQL） |

本轮 deliver r2 返工关闭 `05-review/findings.md` **QA-05…QA-08**（文档闸，不改产品代码；**不重开** QA-01…QA-04）：

| 编号 | 处置 |
|---|---|
| QA-05 | 订一行 curl 两段 `{asset_type}/{name}`（例 `skill/<name>`）。单段 `<asset>` FastAPI 404，到不了 MARKET_CLOSED 409 |
| QA-06 | 本波 `OPS.DUTY_CONTACT` 空。档 3 开市 **只允许**超管 PUT（进程内 overlay）。`POWER_MARKET.ENABLED=true` 环境变量 + 空值班联系 → lifespan `RuntimeError` 拒启。禁止只靠环境变量重启开市；不代填号码 |
| QA-07 | Caddy 无 `rate_limit` ≡ 无限流，**停在档 4**，notify 不得公网。nginx `limit_req` 仍是公网档 5 条件 |
| QA-08 | 根 compose `networks.litellm-net.external: true`。compose 前置 `docker network create litellm-net`（已存在则跳过） |

范围（本波机器面）：

| 波 | 进 | 不进 |
|---|---|---|
| N1 | Scrapy worker 启停（`run.py start/stop spider`）+ Redis 心跳/队列 + MySQL **045** expand-only | 宣称北极星已在生产出现（GWT-U01.1 = FakeRedis ≠ live 120s）；046 head 上 `downgrade 044`；任何 `compose down` 当回滚 |
| N2 | 市场总开关运行时闸（yaml 默认 false）+ 订一行；租户打开关 **403 FORBIDDEN**；T-09/T-15/T-27 **404 同形** | 把关闭句写成空货架；改 yaml 默认当「已开放」入库；把开关 403 当 P1 泄面 |
| N3 | 046（ALTER + 生成列 UNIQUE + NOT NULL + 凭据/SKU 表）；notify 无 JWT；商户密钥只在 DB 密文；SKU 闸 | live 支付宝/微信收银台；HMAC/`signed_body` 夹具当通道已通；046 down / `downgrade 044` 当随手回滚 |
| N4 | 值班三态（空/降级/活）只读总览 | 值班「活」= SKU 已买；mock 网关 = 生产值班 SLA |

根 `docker-compose.yml` 只有 mysql / redis / backend，**没有** spider 服务、**没有** nginx、**没有** LiteLLM。根声明 `networks.litellm-net.external: true`：任何 `docker compose up` **之前**必须 `docker network create litellm-net`（已存在则跳过；缺网则 compose 失败）。backend 本波 **不**挂进该网。compose up 之后工人默认离线；出数环要额外 `run.py start spider`。`ports` 钉 `127.0.0.1:9111`：实验室通道 IP 打不进。

---

## 1. 变更概要与风险分级

| 项 | 内容 |
|---|---|
| 变更内容 | N1 空非夹具入队/工人句/045；N2 市场运行时闸（租户开关 **403**）+ T-09/T-15/T-27 **404**；N3 046+凭据加密+notify 履约+中转 SKU；N4 值班三态。DDL：Alembic **045** expand-only（ADD 可空+小表）；**046** 含 ALTER / STORED GENERATED UNIQUE / `plans.updated_at` NOT NULL，**不是**纯 ADD |
| 影响面 | `POST /api/v1/spiders/run`、心跳 `spider:worker:*`、`POWER_MARKET.ENABLED`、`POST /api/v1/billing/notify/{alipay\|wechat}`、超管凭据、`relay_sku_entitlements`、`GET /api/v1/newapi/overview` |
| **风险等级** | **高**（公开无 JWT 写口 + 验真通过即履约，开通不可逆；密钥泄漏=停发布；工人入队闸 fail-open 扫描异常） |
| 发布策略 | 045+046 先上、**工人保持停**、市场保持关、两通道凭据 0 行、notify **不对公网** → 再按波次放量。不按支付金额 / 租户百分比切支付流量 |

### 三个风险问题

| 问题 | 答 |
|---|---|
| 出问题多快能发现？ | 编排：`/api/v1/health/deep` 15s（MySQL+Redis，**不含** worker、**不含** notify、**不含** LiteLLM）。工人：心跳 TTL 默认 30s。支付：`payment_failed` vs `payment_succeeded`（notify 失败也 HTTP 200，**不能**用 5xx 当验真失败探针）。市场：关闭 409 是预期。值班：页态 empty/degrade/live，deep 绿 ≠ 网关活。Q-OPS-DUTY：**不写 SLA 数字**；下表持续时长是值班动作线 |
| 出问题多快能回滚？ | **current=046 时**：停工人 / PUT 关市 / DELETE 凭据 / 反代摘 notify。**禁止** `alembic downgrade 044`。**禁止任何** `compose down`。仅 `current==045` 才允许 `downgrade 044`。本 spawn **未**对 live `stop spider` / 反代摘 location 做墙钟计时，不编造分钟数 |
| **出问题数据会不会坏？** | 停工人：**否**（不入队）。`current==045` 再 `downgrade 044`：夹具名单+快照列丢失。从 **046** 执行 `downgrade 044`：046+045 一起撤，**商户密文与 SKU 行不可还原**（再加夹具名单）。046→045 同样丢掉密文/SKU。已 `fulfilled` **不会**随回滚退回。`compose down` 无 `-v` 已丢 Redis 队列/心跳；`-v` 再丢 MySQL。市场关：已安装行仍在。值班无 DDL |

---

## 2. 门禁核对（引用实际输出，不接受「应该没问题」）

来源：`06-deliver/release-opinion.md` §2（qc 2026-09-13 工作区）+ 本 spawn 补跑 build。决策对象 = **工作区**，不是祖先 `99e2f95` 单独。合入前须对**冻结 SHA**重跑四闸（qc 条件 7）。

`sdlc.config.yaml` 四闸：`test` / `lint` / `build` / `migration`；`e2e: null`。

| 闸门 | 命令 | 退出码 | 状态 |
|---|---|---|---|
| 单元/集成 | `uv run pytest -x -q backend/tests` | **0** · **1679 passed / 40 skipped / 7 warnings · 241.54s** | ✅ qc 2026-09-13 |
| T-26 | `uv run pytest -q backend/tests/test_fr_u25_duty.py` | **0** · **10 passed** | ✅ qc |
| 架构 | `bash tools/check/arch.sh` | **0** | ✅ qc |
| 迁移 | `bash tools/check/db_migrations.sh` | **0** | ✅ qc |
| 构建 | `npm run build --prefix frontend/admin && npm run build --prefix frontend/official` | 本 spawn 工作区 **0**（见下）；**冻结 SHA 未跑** | ⚠️ 条件 7 |
| 前端工程门禁 | `bash tools/check/frontend.sh` | **0** | ✅ qc；**不替代 build** |
| T-27 Jest | Overview3q + NewApiOps + App.menu | **0** · **43 passed** | ✅ qc |
| 覆盖矩阵 | `check-matrix.py` | **0** · **13 条 FR-\d+** | ✅ 不抽 FR-U |
| SDLC | `--hat {implement,verify,review}` | **0** | ✅ qc |
| E2E | — | — | ➖ `e2e: null` |

本 spawn 补跑 build（工作区脏树，祖先 `99e2f95`，**不是**冻结 SHA）：

```
$ npm run build --prefix frontend/admin
ADMIN_BUILD_EXIT:0
# Compiled with warnings（eslint unused-vars；Checkout useMemo deps）
$ npm run build --prefix frontend/official
OFFICIAL_BUILD_EXIT:0
# Compiled successfully.
```

本机 `node v25.9.0` / `npm 11.12.1`。CI Node 20 用 **npm@10**（P-SRE-01）。本 spawn **未**改 lockfile。本机 ARM build exit 0 **不等于** CI linux/amd64（P-SRE-02）。合入仍须在冻结 SHA 上重跑四闸（含 build）。

**门禁指纹**：上表。skipped **40** = 默认未开 `MYSQL_FIDELITY` 的真库 skip + 既有 new-api 历史 skip + `downgrade base` errno 1553 记录性 skip。盘上旧指纹 1570/39 已作废。

- [x] pytest / arch / db_migrations / T-26 / T-27 / matrix / frontend.sh：qc 原样退出码
- [x] skipped 已解释
- [x] 未配置 E2E 有理由（`e2e: null`）
- [x] 本 spawn 工作区 admin+official build exit 0
- [ ] **冻结 SHA 上四闸（含 build）未跑** — 合入前阻塞（qc 条件 7）

**门禁未全绿则不把预发当生产。** 豁免只走 qc 已写条件，本帽不改结论。不得用「沙箱没打通」挡合入。

### Alembic 045 + 046（本波仅这两份新修订。045 = expand-only ADD；046 **不是**纯 ADD）

| rev | 文件 | 内容 | 生产回滚 |
|---|---|---|---|
| 044 | 既有 head（T-39 spider_definition params） | **禁止**从 046 执行 `downgrade 044`。生产禁止 downgrade past **037** |
| **045** | `045_n1_internal_fixture_tenants.py` revises 044 | `internal_fixture_tenants` CREATE + UNIQUE `tenant_id`；`product_events.is_internal_fixture` ADD **可空**；`idx_product_events_name_fixture_occurred` | 首选 **留下 045**，只停工人。`alembic downgrade 044` **仅当** `alembic current` **= 045** |
| **046** | `046_n3_checkout_orders_credentials_sku.py` revises 045 | ALTER `orders.status` 16→32、`orders.plan_id` NOT NULL→可空；ADD 可空单据列；STORED GENERATED `open_product_slot` + UNIQUE `uk_orders_tenant_open_product` / `uk_orders_order_no` / `uk_orders_channel_trade`；`orders.updated_at` NOT NULL；`plans.updated_at` NOT NULL；CREATE `payment_channel_credentials` + `relay_sku_entitlements` | 首选 **留下 046**：停工人 / 关市 / DELETE 凭据 / 摘 notify。**禁止** `downgrade 044`。**禁止把 046 down 当随手回滚** |

045 **禁止**含 orders 加列 / 凭据表 / SKU 表。046 **禁止**改 045 对象。head 必须是 046。

**046 head 回滚闸（先 `alembic current`，再动手）：**

```
$ APP_ENV=local bash -lc 'cd backend && uv run alembic -c alembic.ini current'
```

| current | 允许 | 禁止 |
|---|---|---|
| **046** | 停工人 / PUT `enabled=false` / DELETE 凭据 / 反代摘 notify。结构留下 046 | **`alembic downgrade 044`**（线性历史 = 046+045 一起撤：商户密文 + SKU 行 + 夹具名单 **不可还原**）。任何 `compose down` |
| **045** | 才允许 `alembic downgrade 044`（只撤 045 夹具表/列/索引） | 从 045 再往下 past 037；`compose down` |
| 其它 | 停。不要猜目标修订 | 从 046 跳 044 |

抛开库（非 SQLite）。T-01 的 `downgrade 044` 是从 **045** 做 up-down-up，**不是** 046 head 上的操作者命令。

T-01 045：

```
OK upgrade 044 fixture_table=False fixture_col=False
OK upgrade 045 fixture_table=True fixture_col=True
OK downgrade 044 fixture_table=False fixture_col=False
OK upgrade 045 again fixture_table=True fixture_col=True
up-down-up 045 complete
exit: 0
```

T-14 046：

```
OK upgrade 046 cred_table=True sku_table=True open_slot=True relay_groups=True status_len=32
OK downgrade 045 cred_table=False sku_table=False open_slot=False relay_groups=True status_len=16
OK upgrade 046 again cred_table=True sku_table=True open_slot=True relay_groups=True
up-down-up 046 complete
udup_exit:0
```

---

## 3. 需真实环境验证清单（来自 /qa coverage §5）

| 用例 | 原因 | 执行结果 |
|---|---|---|
| T-01 045 up→down→up | SQLite 唯一键 / TINYINT ≠ InnoDB | ✅ T-01 抛开库 exit 0 |
| T-14 046 生成列 UNIQUE | SQLite ≠ InnoDB | ✅ T-14 抛开库 udup_exit 0 |
| P-U03 事件索引 EXPLAIN | 生产计划 SQLite 代替不了 | ⚠️ 未跑 MYSQL_FIDELITY；不阻塞工人启停 |
| GWT-U01.1 live Scrapy 120s | FakeRedis `_ingest_flush` ≠ `run.py spider` | ⚠️ **未执行**。qc 条件 5：禁止宣称北极星已在生产出现 |
| GWT-U02.1 工人离线拦住 | 产品回滚主路径 | ✅ pytest GWT-U02.1 + 锁句已落地 |
| HMAC / `signed_body` notify | 夹具四要素 ≠ 通道收银台 | ⚠️ pytest 已覆盖；**不是** live 支付宝/微信（qc 条件 4） |
| 支付宝/微信 live | 通道 CIDR / 报文 / 证书 | ➖ **不执行、不合入闸** |
| 反代 notify `limit_req` | [SEC-7] 应用层无 `RateLimitPolicy` | ⚠️ 仓库无根 nginx。无 `limit_req` **不得**把 notify 打到公网（qc 条件 9） |
| N4 live LiteLLM 管理面 | monkeypatch / jest mock ≠ 真网关 | ⚠️ **未执行**。mock ≠ 生产值班；**不写 SLA**（qc 条件 6） |

- [x] 方言 045 / 046 抛开库已执行
- [x] 工人空态产品路径有测试（非 live stop 计时）
- [x] HMAC 夹具已标明 ≠ live 通道
- [ ] live 120s 工人未跑 — **不作为合入条件**；只禁止用本格写北极星已出现
- [ ] 生产反代两条 notify — 操作者预发做；无限流不得公网暴露
- [ ] 结果回填 `/qa` test-report.md — 仓库无该文件；覆盖矩阵已记 ⚠️

---

# N1 · 采集工人 / 045

N1 段机器事实（仍真）：compose **无** spider；工人靠宿主 `run.py`；045 expand-only；FakeRedis ≠ live 120s；`/health/deep` **不含** worker。

## N1-1. 回滚（首选停工人，不是 down 045）

工人心跳扫描失败会 **放行入队**（`count_online_workers` 异常返回 `-1`）。因此「弄挂 Redis」**不能**当回滚。

```
$ uv run python run.py stop spider
# 期望：spider 已停止 / 或「未在运行，无需停止」

$ uv run python run.py status spider
# 期望：spider 未运行

# 心跳键过期：WORKER_HEARTBEAT.TTL_SECONDS 默认 30（config/default/settings.yml）
# INTERVAL_SECONDS 默认 10。可选立即清键（密码来自环境，禁止写进 git）：
$ redis-cli -h "$REDIS_HOST" -a "$AUTO_AGENTS_REDIS_DEFAULT_PASSWORD" --scan --pattern 'spider:worker:*'
# 0 键 或 TTL 内消失

$ curl -sS -X POST "$API_BASE/api/v1/spiders/run" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"spider_name":"example","params":"{\"urls\":[\"https://httpbin.org/get\"]}"}'
# 期望 HTTP 400，code=SPIDER_WORKER_OFFLINE，message 含「采集未运行，不会出数」
# 期望：无新 spider_tasks 行；product_events 可有 task_blocked.reason=worker_offline
```

`API_BASE` 来自 `config` `API.HOST`/`API.PORT`（默认 `127.0.0.1:9111`，compose 容器内 HOST=`0.0.0.0`）。禁止把编排探针打到浅 `/api/v1/health/`（P-SRE-04：恒 200）。

**产品路径实测**：pytest GWT-U02.1（3s 内拦住 + `task_blocked`）。**live stop 墙钟本 spawn 未测** — 不编造分钟数。TTL 上限 = 配置 30s，不是 SLA。

恢复工人（非回滚，是放量）：

```
$ uv run python run.py start spider
$ uv run python run.py status spider
# 期望：运行中；runtime/run/spider.pid 存活
$ curl -sS "$API_BASE/api/v1/spiders/nodes" -H "Authorization: Bearer $TOKEN"
# 期望：至少 1 个心跳节点
```

日志：`runtime/run/spider.log`；Scrapy 落盘 `logs/spider/spider.log`。

045 schema down（**非首选**；**先看 current**）：

```
$ APP_ENV=local bash -lc 'cd backend && uv run alembic -c alembic.ini current'
```

- **current = 046**（N1–N4 已上）：**不要**跑下一行。回滚 = `run.py stop spider`（以及关市 / 删凭据 / 摘 notify）。从 046 执行 `downgrade 044` = 046+045 一起撤，**商户密文与 SKU 行不可还原**。
- **current = 045**（仅 N1 结构）才允许：

```
$ APP_ENV=local bash -lc 'cd backend && uv run alembic -c alembic.ini downgrade 044'
# DROP index idx_product_events_name_fixture_occurred；DROP 列 is_internal_fixture；DROP 表 internal_fixture_tenants
# 夹具名单没了。事件快照值没了。再 upgrade：列全 NULL
```

生产优先 **停工人、保留 045（以及已上的 046）**。禁止为 N1 从 046 去 `downgrade 044`。根 compose Redis **无数据卷**；**禁止任何 `compose down` 当回滚**（不带 `-v` 已丢队列与心跳；带 `-v` 再丢 MySQL `mysql_data`）。

### N1 配置回滚

| 配置项 | N1 值 | 回滚 | 备注 |
|---|---|---|---|
| Scrapy worker 进程 | 启 1 个 | `run.py stop spider` | **主开关**。无 feature flag 名 |
| `WORKER_HEARTBEAT.TTL_SECONDS` | 30（既有） | 改 yml + 重启 worker | 不要改成 21600（渠道探针锁） |
| `SPIDER_WORKER_OFFLINE_SECONDS` | 120（既有） | 改 yml + 重启 API | 只影响已入队非终态标注 |
| `TASKS.CONSUMER_ENABLED` | true（既有） | 不作为 N1 回滚 | 关消费者会换失败模式 |

---

# N2 · Power Market 总开关 / RBAC

N2 **无新 DDL**。总开关 = 运行配置 `POWER_MARKET.ENABLED`（`config/default/power_market.yml` 默认 **false**）。超管 PUT 走 Dynaconf `settings.set`，**只活在当前进程**；重启回到 yaml false（关市）。本波 `OPS.DUTY_CONTACT` 空：禁止用环境覆盖 `AUTO_AGENTS_POWER_MARKET__ENABLED=true` 当持久开市（lifespan 拒启）。不代填号码。

## N2-1. 机器步骤

```
# 读开关（仅超管）
$ curl -sS "$API_BASE/api/v1/admin/power-market" \
    -H "Authorization: Bearer $PLATFORM_ADMIN_TOKEN"
# 期望 200；默认 enabled=false

# 公司管理员不得改开关（GWT-U11.3；守卫 `require_platform_admin`）
$ curl -sS -X PUT "$API_BASE/api/v1/admin/power-market" \
    -H "Authorization: Bearer $TENANT_ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"enabled":true}'
# 期望 HTTP 403，code=FORBIDDEN。随后超管 GET 仍 false；listing/安装行不变。
# 403 是本路径合同 Then，**不是** 404 同形，**不是** P1 泄面。

# 关闭时订一行必须失败、不写安装行
# 路由：public_skills.py POST /capabilities/{asset_type}/{name}/subscribe
$ curl -sS -X POST "$API_BASE/api/v1/public/capabilities/{asset_type}/{name}/subscribe" \
    -H "Authorization: Bearer $BUYER_TOKEN"
# 例：.../public/capabilities/skill/<name>/subscribe
#     asset_type ∈ skill|plugin|command|agent|team
# 期望 409 code=MARKET_CLOSED message=能力市场未开放
# 期望：无新安装行；无 market_subscribe_succeeded
# 单段 POST /public/capabilities/<asset>/subscribe → FastAPI 404（无此路由），
# 到不了 run_subscribe / MARKET_CLOSED 409。不要用单段当关市探针。

# 打开（进程内 overlay；本波档 3 **只允许**这条）
$ curl -sS -X PUT "$API_BASE/api/v1/admin/power-market" \
    -H "Authorization: Bearer $PLATFORM_ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"enabled":true}'
# PUT 走 settings.set，不跑 lifespan 守卫。重启且未 overlay → 回到 yaml false。
# 本波 OPS.DUTY_CONTACT 为空（config/default/settings.yml）。**不代填号码。**
# 禁止：AUTO_AGENTS_POWER_MARKET__ENABLED=true 后重启开市。
# 机制：lifespan _validate_enablement_duty_contact —— POWER_MARKET.ENABLED=true
# 且联系人为空 → RuntimeError 拒绝启动。ops 未填 DUTY_CONTACT 之前，
# 环境变量持久开市 **禁止**。

# 打开且 0 行：空货架句「暂无已上架能力」，禁止与关闭句混用
# 404 同形 **只**钉下列路径（不要套到开关）：
#   T-09 上架/扫描/平台渠道/RBAC（公司管理员）
#   T-15 GET/PUT/DELETE `/api/v1/admin/payment-credentials`（租户）
#   T-27 值班/overview 壳（租户直打 `/newapi/*`）
```

yaml 保持默认 false。本波 **不要**设 `AUTO_AGENTS_POWER_MARKET__ENABLED`（空 DUTY_CONTACT 会拒启）。

## N2-2. 回滚

| 手段 | 命令 | 数据 |
|---|---|---|
| **首选** | 超管 PUT `{"enabled":false}` | 已安装行保留；新订 409 |
| 硬回滚 | `run.py stop/start backend` 且 **不**设开市环境变量 | 回到 yaml false（本波 DUTY_CONTACT 空：重启后 **必须**关市才能起来） |
| schema | ➖ 无 045/046 动作 | 不要为 N2 去 down 任何修订 |
| **禁止** | 只靠 `AUTO_AGENTS_POWER_MARKET__ENABLED=true` 重启开市 | 本波联系人为空 → 启动 `RuntimeError`。不代填号码 |

关闭 ≠ 空货架。PIT-5：`/public/capabilities` 与 `/public/skills` 关闭句必须同形。商店详情 `<script>` 必须纯文本（T-11），不是本帽改前端。

## N2-3. 监控（N2 专用）

| 类 | 指标 | 说明 |
|---|---|---|
| 业务 | `market_subscribe_succeeded` | 关市期间应为 0 |
| 业务 | 409 `MARKET_CLOSED` | 关市 = 预期；**开市后**持续 409 = P1（开关没写进该进程） |
| 可用性 | 公司管理员 PUT `/admin/power-market` | **403 FORBIDDEN**（GWT-U11.3）。预期。**不是** P1 泄面 |
| 可用性 | T-09 上架/扫描/RBAC/平台渠道；T-15 凭据；T-27 值班 overview | **404 同形**，不得 403。开关不在此列 |

**P1 — 开市后订阅全 409 / 关市后出现 succeeded**

- 阈值：PUT 后 10 分钟内方向反了
- 可能原因：① 多进程只写到其中一个 ② 重启丢 overlay ③ 打到另一套 API ④ 误设开市环境变量导致进程拒启（本波 DUTY_CONTACT 空）
- 排查：1) 超管 GET 开关 2) **不要**用开市环境变量当本波探针（空 DUTY_CONTACT 会拒启） 3) 日志 `power_market.flag.write`
- 临时缓解：需要关 → PUT false + 确认无开市环境变量。本波需要开 → **只**对每个仍在跑的 API 进程超管 PUT true（进程内）。禁止设 `AUTO_AGENTS_POWER_MARKET__ENABLED=true` 再重启。ops 填好 `OPS.DUTY_CONTACT` 之前，环境变量持久开市 **禁止**
- 升级：出现关市 succeeded → 当逃逸给 backend，本帽不改业务代码
- 抑制：变更窗标注「故意关市」时 409 静默

**不要告警：** 默认关市 + 409；打开且 0 行空货架句；租户 PUT 开关 **403 FORBIDDEN**（预期，不是泄面）。

---

# N3 · notify / 046 / 密钥 / 中转 SKU

N3 段机器事实（仍真）：notify **无 JWT**；根 compose 无 nginx；商户密钥只在 `payment_channel_credentials.secrets_encrypted`；HMAC 夹具 ≠ live 通道；046 **不是**纯 ADD（ALTER + STORED GENERATED UNIQUE + `plans.updated_at` NOT NULL）；已开通不可撤回。

## N3-1. 回滚（首选停新履约，不是 down 046）

已 `fulfilled` 的档位/SKU **不会**随回滚退回。停凭据/摘 notify 只挡住 **新** 履约。

```
# 1) 某通道打回未配置
$ curl -sS -X DELETE "$API_BASE/api/v1/admin/payment-credentials/alipay" \
    -H "Authorization: Bearer $PLATFORM_ADMIN_TOKEN"
# 期望 HTTP 200；随后 GET 该通道 configured=false

# 2) 结账非 5xx
$ curl -sS "$API_BASE/api/v1/billing/checkout?product=plan_pro" \
    -H "Authorization: Bearer $BUYER_TOKEN"
# 期望 200。两通道都未配 →「收款通道未开通」。单通道未配 →「该通道未开通」，另一通道仍可选

# 3) 无 JWT 通知仍必须 200、不开通
$ curl -sS -X POST "$API_BASE/api/v1/billing/notify/alipay" \
    -H "Content-Type: application/json" \
    -d '{"order_no":"no-such","merchant_no":"x","amount_cents":1,"trade_status":"success"}'
# 期望 HTTP 200 accepted；无 payment_succeeded；档位不变
# 日志禁止出现密钥全文 / sign / PEM

# 4) 紧急：反代摘掉两条 location（实验室 compose 无 nginx）
```

**产品路径实测**：pytest U31.5 / U32.1 / U32.2 / U38.3；T-24 七条 `7 passed in 2.12s`，`post_notify` **不带** Bearer；`channel_notify` 无 `user`。对照结账匿名 401。**live DELETE + 反代摘 location 墙钟未测**。

046 down（**禁止当随手回滚**；且 **先看 current**）：

```
$ APP_ENV=local bash -lc 'cd backend && uv run alembic -c alembic.ini current'
# 必须是 046 才谈下一行。current=046 时产品回滚仍是 DELETE 凭据 / 摘 notify，不是 schema。
```

仅当必须撤 046 **结构**、且 current **= 046**（相邻一步，目标 045）：

```
$ APP_ENV=local bash -lc 'cd backend && uv run alembic -c alembic.ini downgrade 045'
# 这是 046→045，**不是** 044。密文表 + SKU 表仍会 DROP，不可还原。
$ APP_ENV=local bash -lc 'cd backend && uv run alembic -c alembic.ini upgrade 046'
```

| 项 | 事实 |
|---|---|
| `downgrade 045`（046→045）做什么 | DROP 凭据表、SKU 表；收回 orders 新列/生成列 UNIQUE；ALTER 收回 status 宽度与 plan_id NOT NULL；DROP `plans.updated_at`；`relay_groups` 仍在 |
| 046→045 后数据 | **商户密文不可还原**（明文从不进 git）。SKU 行丢失。新结账单据列丢失 |
| 046→044 | 上表全部 + DROP 045 夹具名单/快照列。**不可还原**。current=046 时 **禁止**这条命令 |
| 推荐 | 留 046 + DELETE 凭据行 / 摘 notify / 停工人 / 关市 |
| 禁止 | 从 046 执行 `downgrade 044`；`downgrade` past **037**；把商户明文写进 compose 当「回滚」；任何 `compose down` |

生产若必须 down：先 `SELECT channel, merchant_no, key_version FROM payment_channel_credentials`（**不要** SELECT `secrets_encrypted` 进工单）。

中转 SKU：权益在 `relay_sku_entitlements`；组行 `relay_groups` 不是已买。SKU≠active：列表空 +「未开通中转」/「中转已到期」；签发 422。**值班行「活」不是这条路径。**

### N3 配置回滚

| 配置项 | N3 值 | 回滚 | 备注 |
|---|---|---|---|
| 通道凭据行 | 超管 PUT 密文 | DELETE 该通道 | **主开关** |
| `LLM_ENCRYPTION_KEY` | 运行时 Fernet 主密钥 | 不撤（LLM 共用保险库） | **不是**商户密钥；禁止进 git/compose 样例明文 |
| 反代 notify location | 对通道网段放行、无 JWT、`limit_req` | 删 location / `deny all` | 无 `limit_req` 不得公网暴露 |
| `ALIPAY_*` / `WECHAT_*` | **禁止出现** | 发现即泄漏：轮换 + 删 env | 不是回滚项，是事故 |

## N3-2. 密钥扫描（合入闸，live 沙箱不是）

```
$ rg -n -i --hidden --glob '!**/postgres-data/**' \
    'ALIPAY_|WECHAT_PAY|WECHAT_MCH|alipay_private_key|alipay_app_secret|wechat_mch_key|wechat_api_v3_key|wxpay_key|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY' \
    deploy docker-compose.yml Dockerfile .env.example config
# 期望：无命中，rg exit 1
```

T-24 本扫描：`rg_exit:1`；`git grep` 无命中。允许：DB 密文 + 环境中的 `LLM_ENCRYPTION_KEY`。禁止：compose / Dockerfile / `.env.example` / git 跟踪文件里的商户明文。

## N3-3. notify 反代（[SEC-7]；无此项不得公网暴露）

应用层 **无** `BILLING_NOTIFY` `RateLimitPolicy`（signup/public events 有，notify 没有）。通道服务器不带本站 JWT。必须用 **精确 location**，禁止 `auth_request` / Basic / JWT 插件。`deploy/litellm` 与 `deploy/newapi` 的 nginx 示例是网关 SSE，**不要**拿来挂 billing。

```
# limit_req_zone $binary_remote_addr zone=pay_notify:10m rate=5r/s;
# 上式 rate/burst 是值班动作线，不是 SLA、不是 NFR

server {
    listen 443 ssl;
    server_name TARGET_HOST;

    location = /api/v1/billing/notify/alipay {
        limit_req zone=pay_notify burst=20 nodelay;
        proxy_pass http://127.0.0.1:9111;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # 不要: auth_request; 不要: proxy_set_header Authorization ...
        # 可选（非合入闸）: allow CHANNEL_CIDR; deny all;
    }

    location = /api/v1/billing/notify/wechat {
        limit_req zone=pay_notify burst=20 nodelay;
        proxy_pass http://127.0.0.1:9111;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:9111;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Caddy **不是**「去掉 JWT 再 reverse_proxy」就算等价。nginx 档 5 条件是精确 location **加** `limit_req`。Caddy 必须带 `rate_limit` 才算公网档 5；**无 `rate_limit` ≡ 停在档 4**，notify 不得公网。

```
# 需 Caddy 带 rate_limit 模块（非默认官方二进制必有）。没有该模块 → 停在档 4。
# events/window 是值班动作线，不是 SLA。
handle /api/v1/billing/notify/alipay {
    rate_limit {
        zone pay_notify {
            key {remote_host}
            events 5
            window 1s
        }
    }
    reverse_proxy 127.0.0.1:9111
    # 不要: basicauth; 不要: JWT 插件; 不要: Authorization 头改写
}
handle /api/v1/billing/notify/wechat {
    rate_limit {
        zone pay_notify {
            key {remote_host}
            events 5
            window 1s
        }
    }
    reverse_proxy 127.0.0.1:9111
}
```

根 compose：`backend.environment` 无 `ALIPAY_*`/`WECHAT_*`；Dockerfile `ENV` 只有 `APP_ENV` / `AUTO_AGENTS_API__HOST`。HEALTHCHECK 打 `/api/v1/health/deep`，**不要**改成 notify。

---

# N4 · 值班三态（活 ≠ SKU）

N4 **无新 DDL**。`duty_page_state` / `duty_row_status` 只在响应 schema，不落库。网关测是 monkeypatch / jest mock，**不是** live LiteLLM。Q-OPS-DUTY：**不写 SLA 数字**。

**禁止混用：**

| 符号 | 含义 | 不是 |
|---|---|---|
| `duty_row_status=live` / 文案「活」 | 超管值班：网关可达 ∧（API live ∨ 本地 original 探针） | 中转 SKU `active`、已买、可签发令牌 |
| `relay_sku_entitlements.status=active` | 该企业中转买了且未到期 | 值班行「活」、网关探针绿 |
| `payment_succeeded` | 验真通过（夹具或真通道） | 可见面可售卖文案 |

## N4-1. 机器步骤

```
# 仅超管
$ curl -sS "$API_BASE/api/v1/newapi/overview" \
    -H "Authorization: Bearer $PLATFORM_ADMIN_TOKEN"
# 期望 200；duty_page_state ∈ empty|degrade|live（互斥）
# 降级句：「LLM 网关管理面不可达，仅本地事件/探针」——本地 24h 仍可有
# 空句：「还没有平台模型，去网关登记」
# 有活行时不得同时出空/降级句；禁止「暂无渠道」

# 租户直打必须 404 同形（不是 403 泄面）
$ curl -sS -o /tmp/n4.json -w "%{http_code}" \
    "$API_BASE/api/v1/newapi/overview" \
    -H "Authorization: Bearer $TENANT_TOKEN"
# 期望 404；body 无渠道列表

# 不要用 deep 判断值班
$ curl -sS -o /tmp/deep.json -w "%{http_code}" "$API_BASE/api/v1/health/deep"
# 2xx 只说明 MySQL+Redis。LiteLLM 挂了 deep 仍可绿、overview 应为 degrade
```

根 compose **不**声明 litellm 服务（ADR-0010）。根 **确实**声明 `networks.litellm-net.external: true`。`deploy/litellm` 是独立故障域。本波不把 backend 挂进 `litellm-net` 当合入闸。compose 前置：

```
$ docker network create litellm-net
# 已存在：Error: network with name litellm-net already exists → 忽略并继续
# 缺这一步：根 `docker compose up` 失败（external 网不存在）
```

## N4-2. 回滚

| 手段 | 效果 |
|---|---|
| 停独立 LiteLLM compose | overview → degrade；**SKU 不变**；采集工人不受影响 |
| 回滚应用二进制 | 无 N4 列可丢 |
| schema | ➖ 不要为 N4 去 down 046 |

伪装探针 **不得**把渠道打成自动禁用（GWT-07.6 回归，本波不重测 v2 FR-nn）。

## N4-3. 监控（N4 专用）

| 类 | 指标 | 说明 |
|---|---|---|
| 业务 | `duty_page_state` | empty / degrade / live 互斥 |
| 业务 | 行 `duty_row_status=live` | 仅网关可达时；降级必须清活标 |
| 可用性 | 租户 `/newapi/*` | 404 同形 |
| 可用性 | `/health/deep` | **不是**值班探针 |

**P1 — 网关可达却长期 empty，或不可达却标 live**

- 阈值：超管确认网关已登记后 10 分钟态反了（动作线，不是 SLA）
- 可能原因：① overview 打到错环境 ② 探针集合空仍扫错 ③ 前端 hasLiveRow 与 API 不一致
- 排查：1) 超管 GET overview 原样 `duty_page_state` / `duty_row_status` 2) 不要把「活」写成 SKU 已开通 3) `runtime/run/backend.log` 降级原因（无 Key）
- 临时缓解：不可达 → 接受 degrade（护栏成功态）。不要重启 Redis 当修网关
- 升级：租户看到渠道列表 → P0 鉴权逃逸 → backend，本帽不改守卫
- 抑制：变更窗「故意停 LiteLLM」时 degrade 静默

**不要告警：** mock 测绿；deep 绿 + degrade（网关独立域）；空态「还没有平台模型」。

---

## 5. 监控接线（四类；无 SLA）

`/api/v1/health/deep` **只**查 MySQL + Redis。工人 0 心跳、两通道未配、LiteLLM 挂、notify 验真失败时 deep 仍可 200。编排全绿 ≠ 能出数 ≠ 能收款 ≠ 值班活。

| 类 | 指标 | 已接 | 取数 |
|---|---|---|---|
| 可用性 | `GET /api/v1/health/deep` HTTP≠2xx | ☐ compose HEALTHCHECK 15s；`scripts/watchdog.sh`（默认 `WATCHDOG_RESTART=0` 只告警） | 编排器 |
| 可用性 | 浅 `/api/v1/health/` | 🚫 **禁止**给 Docker/K8s/watchdog | P-SRE-04 |
| 可用性 | 工人心跳个数 `SCAN spider:worker:*` | ☐ `GET /api/v1/spiders/nodes` 或 Redis | 无外部面板 |
| 可用性 | `POST /billing/notify/{alipay\|wechat}` **5xx/401** | ☐ 访问日志 | 应为≈0（失败也 200）。5xx=通道狂重试 |
| 延迟 | `POST /spiders/run` 入队/拦住 | ☐ pytest monotonic ≤3s；无 APM | 应用日志 `request_id` |
| 饱和度 | `LLEN spider:task_queue:{high,normal,low}`、`item_queue`、`item_dead` | ☐ Redis | 无新键 |
| 饱和度 | 反代 notify QPS | ☐ 无应用层限流 | nginx `limit_req` |
| **业务** | 非夹具 `task_completed` 且 `result_count>0` 且 `is_internal_fixture=false` | ☐ 产品事件 | **不得宣称生产北极星已出现** |
| **业务** | `task_blocked.reason=worker_offline` | ☐ 同查询面 | 停工人时此数应升 |
| **业务** | `payment_succeeded` vs `payment_failed.reason` | ☐ `GET /api/v1/product-events?event_name=payment_succeeded\|payment_failed` | 夹具/伪造不得当 live 已通。`unconfigured` 在未配档是预期 |
| **业务** | `market_subscribe_succeeded` | ☐ 产品事件 | 关市应为 0 |
| **业务** | `duty_page_state` / 行「活」 | ☐ overview JSON | **≠** SKU `active` |

Q-OPS-COLLECT / Q-OPS-DUTY：下列阈值是值班动作线，**不是 SLA**。

### 告警（每条带处理指引）

**P0 — deep 探测失败（MySQL 或 Redis）**

- 阈值：`/api/v1/health/deep` 非 2xx，持续 2 个 HEALTHCHECK 周期（compose 15s ×2）
- 可能原因：① MySQL 进程/网络 ② Redis AUTH/进程 ③ 主机名漂移（compose 服务名 vs 127.0.0.1）④ Dynaconf `.env` 字面 `${VAR}`（P-SRE-07）
- 排查：1) `curl -sS -o /tmp/deep.json -w "%{http_code}" $API_BASE/api/v1/health/deep` 2) JSON `checks.mysql` / `checks.redis` 3) `runtime/run/backend.log` 4) **不要**用浅 `/health/` 当活
- 临时缓解：修依赖；watchdog 默认不 kill（P-SRE-05）
- 升级：仍 503 → 叫能碰 MySQL/Redis 的人。`OPS.DUTY_CONTACT` 空则操作者
- 抑制：deep 红时抑制入队失败率 / notify 5xx（派生）

**P0 — notify 出现 5xx 或 401**

- 阈值：`POST /api/v1/billing/notify/alipay|wechat` 非 2xx，持续 2 分钟（动作线）
- 可能原因：① 反代误加 JWT/`auth_request` ② 失败未吞 ③ 打到错端口
- 排查：1) 无 Bearer POST `{}` 期望 200/422 信封，**不是** 401 2) location 是否精确相等 3) 日志有无密钥/PEM
- 临时缓解：改回无鉴权；必要时摘 location（开通会停，结账走未配置句）
- 升级：仍 401/5xx → 改反代的人
- 抑制：deep 红时先修依赖

**P0 — 商户密钥出现在 git / compose / 日志**

- 阈值：跟踪文件、镜像 env、日志行出现商户密钥全文或 `ALIPAY_*`/`WECHAT_*` 赋值
- 排查：本清单扫描命令；`docker inspect` backend env；日志 rg 禁名
- 临时缓解：**停发布**；超管轮换凭据（U31.5）；从镜像/compose 删除该键；轮换通道侧密钥
- 升级：一经确认即 P0。不得用「只是沙箱」降级
- 抑制：无

**P1 — 本应出数时心跳为 0**

- 阈值：已 `start spider` 之后，`SCAN spider:worker:*` = 0 持续 2 分钟（> 2×TTL 30s）
- 可能原因：① 进程被停 ② Redis AUTH ③ pid 僵死但键过期 ④ 误把 21600 当 TTL
- 排查：1) `run.py status spider` + `runtime/run/spider.pid` 2) spider **无** listen 口，不要看 9111 3) `logs/spider/spider.log` 4) Redis 键
- 临时缓解：需要出数 → `start spider`。需要空态 → **保持 0 心跳**（回滚成功态，不要当 P1）
- 升级：放量档重启一次仍 0 键 → P0 依赖面
- 抑制：变更窗「工人故意停」静默

**P1 — 队列积压**

- 阈值：`LLEN spider:task_queue:normal` 或 `spider:item_queue` 持续 10 分钟上升且心跳 ≥1
- 排查：心跳；`TASKS.CONSUMER_ENABLED`；`LLEN spider:item_dead`；任务是否卡 `running`
- 临时缓解：停工人止入队；**禁止任何** `compose down`（无 `-v` 已丢 Redis 队列/心跳；`-v` 再丢 MySQL）
- 升级：死信持续涨或 running 超过 `TASKS.STALE_TASK_HOURS`（默认 6h）仍不回收 → 记缺陷给 backend

**P1 — 已配通道却持续 `payment_failed.reason=unconfigured`**

- 阈值：该通道 `configured=true` 之后 10 分钟内新失败仍 unconfigured
- 排查：超管 GET 凭据（只见掩码）；`configured_channels` 与结账 preview；**不要**把密钥贴进工单
- 临时缓解：未配侧保持「该通道未开通」。不要重启 Redis
- 升级：买方已付款但本站一直 unconfigured → P0 对账；**不**用 `confirm_paid` 当在线履约（ADR-0024）

**P1 — 验真失败率异常（无 `payment_succeeded`、日志「未视为真通知」）**

- 阈值：已放量通道上连续 10 分钟只有失败日志、零 succeeded，而通道侧声称已付款
- 可能原因：① 缺签（U38.3）② 金额/商户/订单号不符 ③ 轮换后仍签旧密钥 ④ 伪造
- 临时缓解：保持未开通（护栏成功态）。人工对账，不走 confirm 开通
- 升级：轮换不同步 → 超管再 PUT 当前密钥；伪造 → 只记安全事件

**P2 — 两通道都不可用时结账 5xx**

- 阈值：GET `/billing/checkout` 5xx（应为 200 空态句）
- 临时缓解：deep 红先修依赖；deep 绿而结账 5xx → backend，本帽不改业务代码

**不要告警（预期态）**

| 现象 | 为什么不是告警 |
|---|---|
| GET checkout「收款通道未开通」 | 两通道未配空态（NFR-U03） |
| 单通道「该通道未开通」、另一可选 | 灰度设计态 |
| notify HTTP 200 但不开通 | 验真失败/迟到/缺签合同 |
| HMAC 夹具 succeeded | **不是** live 收银台 |
| 无支付宝/微信 live 回调 | 合入不要求沙箱 |
| deep 绿 + 工人 0 | compose 默认；只在已 start spider 后才用 P1 |
| deep 绿 + 值班 degrade | LiteLLM 独立域 |
| 值班「活」但 SKU ≠ active | **正确**，两套语义 |
| 官网无 FR-U24 四字 | 禁写，不是漏文案 |
| FakeRedis 测试完成事件 | **不是**北极星已出现 |

- [x] 分级不是全 P0
- [x] 阈值带持续时间（动作线，不是 SLA）
- [x] 停工人 / 关市 / 未配置 / degrade 用变更窗抑制
- [ ] 外部值班面板本波未接
- [ ] 应用层 notify 限流键 **未**接（[SEC-7] → 反代 `limit_req`，否则不得公网）

---

## 6. 灰度与放量判据（提前定，不临场判断）

无支付金额百分比。维度 = **工人进程 × 市场开关 × 凭据行 × notify 是否对通道网段暴露**。值班无租户流量百分比（仅超管页）。

| 档 | 范围 | 观察 |
|---|---|---|
| 0 | 045+046 已 upgrade；**spider 停**；市场 **关**；两通道凭据 **0 行**；notify 不对公网 | deep 绿；`POST /run` → 工人句；checkout 空态 200；无 JWT notify → 200 不开通；公开市场关闭句；overview 允许 empty/degrade |
| 1 | `run.py start spider`；只允许 **夹具企业** 提交；市场仍关；凭据仍 0 | 夹具完成 **不得** 计入北极星分子 |
| 2 | 一户 **非夹具** 提交。**不得**把 FakeRedis 当本档 | 该任务终态。仍不是四柱 GA |
| 3 | 超管 **PUT** 开市场（进程内 overlay；先内网）。本波 **禁止**环境变量持久开市 | 关闭句不再出现；空货架句仅 0 行时；公司管理员改开关 → **403 FORBIDDEN**（不是 404，不是 P1）。重启丢 overlay 回 yaml false。`POWER_MARKET.ENABLED=true` 环境变量 + 空 `OPS.DUTY_CONTACT` → 拒启 |
| 4 | 超管只配 **一个**通道；notify **尚未**对公网（仅内网 HMAC 夹具） | 另一通道「该通道未开通」；夹具验真 1 笔 **非 live**；伪造/缺签不开通 |
| 5 | 反代对通道网段放行两条 notify，**必须** nginx `limit_req` 或 Caddy `rate_limit`、无 JWT | 有无 live 都不挡本档；**没有** `limit_req`/`rate_limit` → **停在档 4**。Caddy 只 reverse_proxy **不是**公网等价 |
| 6 | 第二通道凭据 | 仅当档 4–5 无 P0、无密钥泄漏、NFR-U03 仍成立 |
| D | 值班页（可与档 0 并行） | 三态互斥；租户 404；「活」≠ SKU。不把 mock 可达写成值班承诺 |

### 基线（同期对比，不用发布前一分钟）

本波无生产 n。用档 0 窗口当对照。

| 指标 | 档 0 对照 |
|---|---|
| deep 5xx | 应为 0（依赖活） |
| 工人句入队 400 | 无工人时 **全部** 拦住 |
| 非夹具 `task_completed` | 档 0–1：0 |
| checkout 5xx | 0（空态 200） |
| `payment_succeeded` | 0；档 4 仅夹具 |
| notify 401 | 全程 **0** |
| compose 商户键 | 全程 **0** |
| `market_subscribe_succeeded` | 关市：0 |

### 放量条件（全部满足才从档 n → n+1）

- ✅ deep 持续 2xx
- ✅ 档 0：无工人时无新任务行；关市无 succeeded；无 JWT notify 不 401
- ✅ 档 1：夹具完成不出现在 `is_internal_fixture=false` 分子
- ✅ 档 2：非夹具结果只在本企业；**不是** FakeRedis 证据
- ✅ 档 3：超管 PUT 开市（非环境变量）；关闭句/空货架句分家；租户 PUT 开关 **403 FORBIDDEN**（不是 404）。本波 DUTY_CONTACT 空：禁止 `AUTO_AGENTS_POWER_MARKET__ENABLED=true` 重启
- ✅ 档 4：未配通道不可履约；日志/事件无密钥全文
- ✅ 档 5：反代有 nginx `limit_req` 或 Caddy `rate_limit`（无则停档 4）；git/compose/Dockerfile 扫描仍无命中
- ✅ 无 P0
- ✅ **不**把 live 沙箱到账 / live 120s / live LiteLLM 列为必须
- ✅ 值班「活」未写成 SKU `active`

### 回滚条件（任一满足即执行对应回滚，**不讨论**）

- ❌ deep 非 2xx 超过 2 个探测周期 → 修依赖
- ❌ 档 1+ 心跳非预期掉 0 → `stop spider`（若不是变更窗故意停）
- ❌ 非夹具完成事件夹具标错 → 停工人
- ❌ 他企结果泄漏 → 停工人
- ❌ notify 401/5xx 超过 2 分钟 → 摘 location / 删凭据
- ❌ 跟踪文件或镜像 env 出现商户密钥 → **停发布**
- ❌ 未验真出现 `payment_succeeded` 或档位被开通 → 删凭据 + 摘 notify
- ❌ 关市出现 `market_subscribe_succeeded` → PUT false
- ❌ 结账未配置变成服务器错误页
- ❌ 用 `confirm_paid` 给在线单开通
- ❌ 租户看到值班渠道列表
- ❌ 任何把 046 down 当成「先撤库再说」的现场冲动 → **禁止执行**
- ❌ current=046 时 `alembic downgrade 044` → **禁止执行**（密文+SKU 不可还原）
- ❌ 任何 `compose down`（含不带 `-v`）当回滚 → **禁止执行**（无 `-v` 已丢 Redis；`-v` 再丢 MySQL）

### 低频路径覆盖

| 路径 | 观察窗口是否覆盖 |
|---|---|
| 心跳 TTL 到期判离线 | 档 0：停工人后等 ≤30s |
| 已入队后掉线 120s 标注 | `SPIDER_WORKER_OFFLINE_SECONDS`；本波不强制 live 120s 出数 |
| 过期 running 回收 `STALE_TASK_HOURS=6` | 默认 **不**覆盖 6h |
| 轮换后旧密钥不能新履约 | 档 4 夹具 U31.5；live 轮换不强制 |
| 迟到成功回调 / 重复通知 | pytest U34.4 / U33.6；live ➖ |
| 市场进程重启丢 overlay | 档 3：重启后应关。本波 DUTY_CONTACT 空，禁止用环境变量持久开市（设了拒启） |
| 支付迟到回调 live | ➖ 本波无 |

---

## 7. 容量评估

Q-OPS-COLLECT / Q-OPS-DUTY：本波 **不承诺** 支持负荷数字与 SLA。下列是配置事实，不是压测报告。**未做**支付宝沙箱压测、**未做** live 120s 工人压测。

| 项 | 数字 |
|---|---|
| 单 worker | 1 个 `scripts.runlib.spider` 进程；心跳 interval 10s / TTL 30s |
| 同爬虫并发 | `SPIDER_MAX_CONCURRENT_PER_SPIDER` 默认 2 |
| 消费者 | backend lifespan，`TASKS.CONSUMER_ENABLED` 默认 true |
| notify | 本进程验真 + CAS；**无**通道 SDK 外呼、无新 worker |
| 应用层 notify 限流 | **无** |
| 市场开关 | 进程内 Dynaconf；默认 false |
| 值班 | 只读 overview；LiteLLM 超时 `OVERVIEW_TIMEOUT_SECONDS=5` |
| compose 限额 | mysql 512m / redis 256m / backend 1g（联调量级） |
| **当前配置** | compose **无** spider / **无** nginx / **无** 支付 sidecar / **无** litellm |
| **调整** | 本波不扩 worker 池、不加 compose spider、不扩 replica 当收款容量 |
| 余量 | 未承诺；夹具 1 笔 / 一户非夹具不构成容量验收 |

### 瓶颈资源核对

| 资源 | 当前 | 变更后预估 | 上限 | 余量 |
|---|---|---|---|---|
| MySQL 045+046 | 045：+1 表 + 可空列 + 索引。046：**不是**纯 ADD——ALTER 既有列 + STORED GENERATED UNIQUE + NOT NULL `updated_at` + 2 表 | 点查名单/凭据/SKU/`order_no` | 抛开库已跑；低峰跑 046 | 推定够夹具 |
| Redis | 无新键名；心跳 hash + 既有队列 | 工人 1 个 hash | compose 256m | 队列无持久化 |
| CPU | notify 验真 MAC | 公开口可被打满（[SEC-7]） | 无应用限流 | 靠反代，否则不暴露 |
| worker | 0（compose 默认）→ 1 | 1 | 本波不水平扩 | — |

---

## 8. 部署步骤

环境变量（已有；N3 **只允许**再加 vault 主密钥，**禁止**商户明文）：

- `AUTO_AGENTS_MYSQL_DEFAULT_PASSWORD`
- `AUTO_AGENTS_REDIS_DEFAULT_PASSWORD`
- `AUTO_AGENTS_JWT__SECRET_KEY`
- `AUTO_AGENTS_WEBHOOK__SECRET_KEY`（工人完成回调既有守卫；不是支付宝密钥）
- `LLM_ENCRYPTION_KEY` — Fernet 主密钥（与 LLM 保险库同一把；未配则拒保存商户明文）
- **本波禁止**：`AUTO_AGENTS_POWER_MARKET__ENABLED=true`（`OPS.DUTY_CONTACT` 空 → lifespan 拒启）。ops 填好值班联系之前，环境变量持久开市禁止。不代填号码
- `.env` **禁止** `${VAR}` 占位（P-SRE-07）

禁止出现：`ALIPAY_*` / `WECHAT_*` / `WECHAT_MCH*` / `alipay_private_key` / `wechat_api_v3_key` / 证书口令 / 把 `secrets_encrypted` 明文写进 env。

```
0. 根 compose 前置（`networks.litellm-net.external: true`；缺网则 compose up 失败）
   docker network create litellm-net
   # 已存在：Error: network with name litellm-net already exists → 忽略并继续
   # 然后才允许 docker compose up --build。不要用 compose down 清网。
1. 冻结 SHA；重跑 sdlc.config.yaml 四闸
   uv run pytest -x -q backend/tests
   bash tools/check/arch.sh
   bash tools/check/db_migrations.sh
   npm run build --prefix frontend/admin && npm run build --prefix frontend/official
   期望：全部 exit 0。不要加 live 沙箱 job、不要加 live 120s job
2. 扫描商户禁名（§N3-2）；期望无命中
3. 确认 alembic head 文件是 046_n3_checkout_orders_credentials_sku.py，revises 045
4. MySQL 8 已活：bash scripts/db/migrate.sh
   期望 current = 046
   核对：SHOW CREATE TABLE internal_fixture_tenants
         SHOW CREATE TABLE payment_channel_credentials（有 secrets_encrypted，无 tenant_id）
         SHOW CREATE TABLE relay_sku_entitlements
         product_events 表尾 is_internal_fixture 可空
5. Redis 7 已活。不要为本波新建键前缀。**禁止任何** `compose down`（无 `-v` 已丢 Redis 队列/心跳；`-v` 再丢 MySQL）
6. 运行时注入 LLM_ENCRYPTION_KEY（生成：python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"）
   不要注入商户明文；不要默认打开 POWER_MARKET；**不要**设 AUTO_AGENTS_POWER_MARKET__ENABLED=true
   （本波 OPS.DUTY_CONTACT 空 → 设了 lifespan RuntimeError 拒启。不代填号码）
7. 启动 backend（消费者随 lifespan）
   uv run python run.py start backend
   curl -f http://127.0.0.1:9111/api/v1/health/deep
8. 档 0：确认 spider 仍停
   uv run python run.py status spider
   POST /api/v1/spiders/run → 400「采集未运行，不会出数」
   GET checkout → 200 空态
   POST notify 无 Bearer → 200 不开通
   市场关闭句；overview 允许 empty/degrade
9. 档 1：uv run python run.py start spider
   GET /api/v1/spiders/nodes 有心跳
   仅夹具企业提交；is_internal_fixture=true 不进北极星分子
10. 档 2：一户非夹具提交。不把 FakeRedis 当本步证据
11. 档 3：超管 PUT 开市场（进程内 overlay **only**）。禁止环境变量持久开市。验证关闭/空货架分家；租户 PUT 开关期望 **403 FORBIDDEN**（不是 404，不是 P1）
12. 档 4：超管 PUT 凭据（响应只有掩码）；内网 HMAC 夹具 POST notify。不要去开放平台点「沙箱到账」当闸
13. 档 5：反代按 §N3-3 两条 location + nginx `limit_req`（或 Caddy `rate_limit`）。无 limit_req / 无 rate_limit 则停在档 4，notify 不对公网。Caddy 只 reverse_proxy 去掉 JWT **不是**等价
14. 档 D（可与 8 并行）：超管打开值班页；确认「活」未写成 SKU；租户 404
15. 全程禁止用户公告（→ ops）；禁止可见面 FR-U24 四字；禁止 SLA 数字
```

前端：admin/official 静态资源随既有 9112/9113。本波无单独 CDN 步骤。

跨平台：lockfile 用 **npm@10**（P-SRE-01）。镜像在 CI linux/amd64 建（P-SRE-02）。Dockerfile 前端 Stage 必须用根 `package-lock.json`（P-SRE-03）。

**每步的回退动作**：

| 步 | 回退 |
|---|---|
| 0 | 网留下即可。**不要** `docker network rm litellm-net`（LiteLLM 独立域可能还在用）。**禁止** `compose down` |
| 4 | 首选保留 045+046 + 停工人/关市/删凭据/摘 notify。若必须撤 046 结构：仅 `current==046` 时 `downgrade 045`（密文+SKU 丢失，**非随手**）。**禁止** `downgrade 044`。**禁止** `compose down` |
| 6–7 | `uv run python run.py stop backend`；不要 kill Redis |
| 8 | 已是回滚态（工人停、市关、凭据空） |
| 9–10 | `uv run python run.py stop spider` |
| 11 | PUT `enabled=false` 或重启且 **不**设开市环境变量。禁止设 `AUTO_AGENTS_POWER_MARKET__ENABLED=true` 当「硬开市」（本波拒启） |
| 12 | `DELETE .../payment-credentials/{channel}` |
| 13 | 反代删 location / deny all |
| 14 | 停 LiteLLM → degrade；不要 down 046 |

---

## 9. 发布窗口与人员

| 项 | 内容 |
|---|---|
| 建议窗口 | 工作日。工人启停不需要支付对账窗。合入不跑 live 支付，**不必**等通道对账窗 |
| 需要维护窗口 | **是，低峰**（不是用户停机公告，本帽不写公告）。045 = ADD 可空列+小表。**046 不是纯 ADD**：ALTER `orders.status` 16→32、`orders.plan_id` 可空；STORED GENERATED `open_product_slot` + UNIQUE；`orders.updated_at` / `plans.updated_at` NOT NULL（有 server_default）。InnoDB metadata lock — 低峰跑，不是支付切流 |
| 值班人 | `OPS.DUTY_CONTACT` 当前空；本波不编造姓名/电话、不写 SLA |
| 回滚决策人 | 能 `run.py stop spider` + 能 DELETE 凭据或改反代的部署角色。本帽未在生产核验值班账号 |
| 相关方通知 | **本帽不写**用户公告 / CS 话术 → `ops` enablement |

---

## 10. 检查结论（陈述事实，不做放行决策）

| 项 | 状态 |
|---|---|
| 门禁 | qc：pytest **1679/40** EXIT 0；arch 0；mig 0；T-26 **10**；T-27 Jest **43**；matrix 13 FR-\d+；frontend.sh 0。本 spawn 工作区 admin+official **build EXIT 0**。**缺**冻结 SHA 四闸。live 沙箱 / live 120s **不是**缺项 |
| 需真实环境 | 045/046 抛开库 ✅；live 120s ⚠️；HMAC ≠ live ✅已标明；反代 limit_req ⚠️ 未测；live LiteLLM ⚠️ |
| 回滚方案 | 046 head：停工人 / 关市 / 删凭据 / 摘 notify。**禁止** `downgrade 044`。**禁止任何** `compose down`。仅 `current==045` 才允许 `downgrade 044`。live stop / 摘 location 墙钟 **未**本 spawn 实测 |
| 数据兼容性 | 045 expand-only ADD。046 含 ALTER + 生成列 UNIQUE + NOT NULL；推荐留库 + 停进程/删凭据。046→044 毁掉密文与 SKU，不可还原。已开通不可撤回 |
| 监控接线 | deep **不含** worker / notify / LiteLLM。业务看心跳 TTL、`payment_failed` vs `payment_succeeded`、市场 succeeded、值班页态。无 SLA |
| 告警 | 动作告警 + 明确不告警项；「活」≠ SKU |
| 灰度判据 | 档 0…6 + D 已定 |
| 容量 | 未承诺负荷数字 |
| 密钥 | 只允许 DB 密文 + 环境 vault 主密钥 |
| **阻塞发布的项** | ① 冻结 SHA 重跑四闸（含 admin+official build，qc 条件 7）② 无反代 `limit_req` 则 notify 不得公网（条件 9）。**支付宝/微信 live、live 120s、live LiteLLM 不是阻塞项** |

**放行决策 → `/qc`（已出有条件放行）。** 本帽只提供机器检查结果，不批准自己的工件，不把 N1–N4 标成四柱 GA。

---

## 11. 自检

- [x] 风险已分级（高 / 先空态再按档放量）
- [x] 三个风险问题已回答
- [x] 门禁引用 qc 原样指纹 + 本 spawn build 退出码；缺冻结 SHA 标 ⚠️
- [x] 需真实环境清单已回填（045/046 ✅；live 120s ⚠️；live 支付 ➖；limit_req ⚠️）
- [ ] **三类回滚未全部在生产计时**：schema 抛开库 ✅；进程 live 墙钟 ❌；反代摘 location ❌
- [x] 未编造回滚耗时分钟数
- [x] 未写 SLA 数字
- [x] 数据兼容性按 expand-contract 写清；046 禁止当随手回滚；046 **不是**纯 ADD（QA-03）
- [x] 不可撤回副作用已列出（开通、事件追加、046→044 毁掉密文+SKU）
- [x] QA-01：046 head 禁止 `downgrade 044`；仅 `current==045` 才允许
- [x] QA-02：开关 curl 钉 403 FORBIDDEN；404 只钉 T-09/T-15/T-27；403 不是 P1
- [x] QA-04：禁止任何 `compose down`（无 `-v` 已丢 Redis；`-v` 再丢 MySQL）
- [x] QA-05：订一行 curl 两段 `{asset_type}/{name}`；单段 404 到不了 MARKET_CLOSED
- [x] QA-06：档 3 只允许超管 PUT；本波 DUTY_CONTACT 空，禁止环境变量重启开市；不代填号码
- [x] QA-07：Caddy 无 `rate_limit` ≡ 停在档 4，不得公网
- [x] QA-08：compose 前置 `docker network create litellm-net`（已存在则跳过）
- [x] 执行人权限未假装已在生产核验
- [x] 监控四类有业务指标；deep 不含 worker 已点名；`payment_failed` vs `payment_succeeded` 已分
- [x] 告警有处理指引；空态/夹具/degrade/关市不告警
- [x] 放量与回滚判据提前写定
- [x] 基线不用发布前一分钟
- [x] 低频路径：TTL 30s 覆盖；6h stale 未覆盖已声明
- [x] 容量不编造 Q-OPS-COLLECT 数字
- [x] 每个部署步骤有回退动作
- [x] 未做放行决策
- [x] 未写用户公告 / CS 话术
- [x] 未要求支付宝/微信 live 作为合入闸
- [x] 未把 HMAC 夹具写成 live 收银台
- [x] 未把 FakeRedis 写成 live 120s 北极星
- [x] 未把值班「活」写成 SKU `active`
- [x] 商户密钥未列入 compose/Dockerfile/git；只允许 DB 密文
- [x] N1 仍真事实已保留（无 spider 服务、stop/start、045、心跳 TTL）
- [x] N2/N3/N4 机器步骤已追加

---

## Debug record

deliver r2 · QA-05…QA-08 · 2026-09-13

### Reproduce

```
$ rg -n 'capabilities/<asset>/subscribe|AUTO_AGENTS_POWER_MARKET__ENABLED|Caddy 等价|litellm-net|档 3|或环境变量' \
    .sdlc/upgrade-four-pillars/06-deliver/checklist.md
257:$ curl -sS -X POST "$API_BASE/api/v1/public/capabilities/<asset>/subscribe" \
275:若要重启后仍开：运行时 `AUTO_AGENTS_POWER_MARKET__ENABLED=true`（环境，**不进 git / 不进 compose 样例当默认开**）。yaml 保持默认 false。
300:- 排查：1) 超管 GET 开关 2) 该进程环境有无 `AUTO_AGENTS_POWER_MARKET__ENABLED` 3) 日志 `power_market.flag.write`
426:Caddy 等价：`handle /api/v1/billing/notify/alipay` / `.../wechat` 无 `basicauth`、无 JWT 插件，再 `reverse_proxy 127.0.0.1:9111`。
466:根 compose **不**声明 litellm 服务（ADR-0010）。`deploy/litellm` 是独立故障域。本波不把 backend 挂进 `litellm-net` 当合入闸。
643:- ✅ 档 3：关闭句/空货架句分家；租户 PUT 开关 **403 FORBIDDEN**（不是 404）
676:| 市场进程重启丢 overlay | 档 3：重启后应关，除非环境变量 |
719:- 可选：`AUTO_AGENTS_POWER_MARKET__ENABLED`（仅当要重启后仍开市；默认不要设）
755:11. 档 3：超管 PUT 开市场（或环境变量）。验证关闭/空货架分家；租户 PUT 开关期望 **403 FORBIDDEN**（不是 404，不是 P1）
RG_EXIT:0

$ python3 -c '...'  # router / lifespan / compose / DUTY_CONTACT
HAS_TWO_SEG True
HAS_ONE_SEG_CAP False
HAS_DUTY_GUARD True
RAISES_ON_MARKET True
EXTERNAL_NET True
DUTY_EMPTY True
PY_EXIT:0
```

G-fresh `05-review/findings.md` decision: fail · blocker 0 · major 2（QA-05、QA-06）· minor 2（QA-07、QA-08）。

### Eliminated hypotheses

- H1 公开订一行路由是单段 `/capabilities/{name}/subscribe` → `public_skills.py:126` 是 `{asset_type}/{name}`；单段 POST 无匹配 → 404，到不了 `MARKET_CLOSED` → 否
- H2 本波可用 `AUTO_AGENTS_POWER_MARKET__ENABLED=true` 重启持久开市 → `create_app` lifespan 调 `_validate_enablement_duty_contact`；`OPS.DUTY_CONTACT: ""`；ENABLED=true 且联系人为空 → `RuntimeError` 拒启。超管 PUT 只 `settings.set`，不跑该守卫 → 否（环境变量路径本波不可执行）
- H3 Caddy 去掉 JWT 的 reverse_proxy 等于 nginx `limit_req` 档 5 → Caddy 段无限流；[SEC-7] 公网条件是反代限流 → 否
- H4 根 compose 会自建 `litellm-net` → `networks.litellm-net.external: true`；缺网 `compose up` 失败；backend 未 attach 不改变「先建网」→ 否
- H5 应改产品代码迁就清单 → findings owner=sre；路由/守卫/external 网是既有合同 → 否（文档闸）

### Root cause

checklist operator steps were written from intended outcomes, not the FastAPI/lifespan/compose contracts those steps invoke.

### Minimal fix

只改 `06-deliver/checklist.md`：订一行 curl 两段路径；档 3 仅超管 PUT、禁止空 DUTY_CONTACT 时环境变量开市；Caddy 补 `rate_limit` 并写明无限流 ≡ 档 4；compose 前置 `docker network create litellm-net`。不重开 QA-01…QA-04。不改 qc 有条件放行。不标 GA。不写 SLA / 当前可买。不代填号码。

### Re-check

清单正文（`## Debug record` 之前）不再含旧失败句。live curl 两段路径。`check-sdlc.sh --hat deliver` EXIT 0。

```
BODY_HAS_TWO_SEG True
BODY_HAS_CREATE_NET True
BODY_HAS_RATE_LIMIT True
BODY_HAS_STAY_TIER4 True
BODY_HAS_PUT_ONLY True
BODY_HAS_NO_INVENT True
BODY_OLD capabilities/<asset>/subscribe curl False
BODY_OLD 'Caddy 等价：' False
BODY_OLD '超管 PUT 开市场（或环境变量）' False
BODY_OLD '若要重启后仍开：运行时' False
BODY_OLD '仅当要重启后仍开市' False
BODY_OLD '除非环境变量' False
PY_EXIT:0

$ rg -n '^\s*\$ curl -sS -X POST .*subscribe' 06-deliver/checklist.md
267:$ curl -sS -X POST "$API_BASE/api/v1/public/capabilities/{asset_type}/{name}/subscribe" \

$ bash /Users/xuyun/.zcode/local-plugins/sdlc-workflow/scripts/check-sdlc.sh --require --hat deliver /Users/xuyun/auto_agents/.sdlc/upgrade-four-pillars
✓ 泳道声明
----------------------------------------
✓ SDLC 工件合规通过
SDLC_EXIT:0
```
