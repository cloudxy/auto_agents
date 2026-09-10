# qc 条件 2 预发记录 · feat-four-pillars-v2 冻结施工集

> 作者：/sre｜日期：2026-09-10｜对齐 qc 有条件放行（闸门 pytest **1331** / alembic **039**；旧 sha `c470278` 其后已重跑，不是决策对象）
> 泳道：L4
> 范围：**冻结施工集预发（条件 2）**，**不是**四柱产品 GA。Wave 2/3（FR-50/51/60/61）仍 ➖。六问不代选。
> 上游：`06-deliver/release-opinion.md`（有条件放行）｜`04-verify/coverage.md` §5｜`06-deliver/checklist.md` §3
> 凭据：`MYSQL_FIDELITY_*` 从本机 `config/local/.env` 的 `AUTO_AGENTS_MYSQL_DEFAULT_PASSWORD` 注入；**不写入本文件、不提交。**

本文件是冻结施工集进生产前的条件 2 证据，**不得**写成 Wave 2/3 已 GA。条件 2 预发三项（方言 / 18.1 Then / NFR-01）本轮 **satisfied**。**禁止**把该 satisfied 写成 LiteLLM/生产 动工。条件 A 仍 not PASS。本帽不改 `coverage.md` / `release-opinion.md`。

开放六问（不代选）：Q-VOICE / Q-PRICE / Q-RELAY / Q-MARKET-USER / Q-BILL / Q-AGPL / Q-OPS-DUTY / Q-OPS-COLLECT。

---

## 0. 三项结论（本轮；coverage 翻格交 `/qa`）

| # | 项 | 本轮 | 退出码 | 说明 |
|---|---|---|---|---|
| 1 | MYSQL_FIDELITY=1 coverage §5 / checklist §3 方言批 | **satisfied（37.6 PASS）** | 本帽独立 37.6 **0**（1 passed in 1.86s）；方言批 **0**（**22 passed** in 17.79s）；`downgrade base` **1**（1553，未本轮重跑）；隔离 038↔037 **0**；隔离 039↔038 **0**（dba） | dba 039 `listed_at` DATETIME(6)。**未改产品代码。** 未用编排器口述盖章 37.6。合主干必须含 **039**。生产禁止 down past 037。 |
| 2 | GWT-18.1 真 Worker | **Then PASS**（completed **+40.56s**） | idle-close 30s 后 `run.py restart spider` **0**；入队/回调/导出 HTTP **200** | 非 FakeRedis。编排器 live，本帽核 `logs/api/api.log` + `logs/spider/spider.log`。task **#2** example+httpbin。`result_count=1` @ **+6.1s** 仍 running；webhook completed **+40.56s** `result_count=1`；export **200** rows **1**。满足 Then「120 秒内任务进入完成且条数>0」。对照 task#1 completed **+129s**（当时 IdleAutoClose 120s）只作历史，不作本轮 Then。本帽不改 coverage.md。 |
| 3 | NFR-01 卡片可见 P95&lt;2s | **浏览器 PASS** | Chrome headless + `/tmp/nfr01qc2-browser` playwright-core **0** | 20 次导航均见 **20** 张卡、首卡 `NFR卡片399`；P95 **1.445s**。非 TestClient、非 API 计时顶格。**本轮不改已记 PASS。** |

条件 2 **satisfied**（预发三项）：方言 37.6 + NFR-01 浏览器 + GWT-18.1 Then（completed **+40.56s**）。**不是**四柱 GA。条件 A **not PASS**（down 半格 PASS / 轮换 pending）。**禁止**宣称 LiteLLM/生产 动工。qc 有条件放行文件本帽不改。

条件 1 / 3 / 4 / 5：**satisfied**（qc）。条件 6：**lock**（FR-50/51/60/61 ➖；六问开放；不是四柱 GA）。

qc 条件 A（把预发当生产或打开 LiteLLM 故障域前）：**not PASS**（轮换半格未过）。

| A 半格 | 本轮 | 状态 |
|---|---|---|
| dockerd `compose down --remove-orphans` | 本帽独立 2026-09-10T03:53:38Z **exit 0**（`docker info` **0** ServerVersion=29.4.0；sock `~/.docker/run/docker.sock`；`/var/run/docker.sock` → 该 sock；`config -q` 两条 **0**；`lsof :4000` 无监听；compose ps 空）。先前 02:43:36Z exit 1（当时 daemon 未起）不作本半格 | **PASS** |
| 机外轮换 `44e9446` | `06-deliver/rotation-44e9446.md` 已列 DeepSeek + Moonshot（7 行明文 api_key，值不复制）。`git ls-files deploy/litellm/config.gen.yaml` 空。无 `rotated: YYYY-MM-DD`。本帽 **不自勾** 已轮换。操作者确认证据不得写密钥 | **attestation pending operator** |

无证明行前 **禁止** `LLM.ENABLED=true` / litellm compose up。默认 `POWER_MARKET.ENABLED=false` / `LLM.ENABLED=false`。根 compose **禁止**焊 litellm。本轮不改 qc 有条件放行结论。Then 操作证据 PASS **不等于** 允许 LiteLLM/生产 动工。compose-down PASS **不等于** 条件 A PASS。不是四柱 GA。**动工 = NO**。

---

## 1. MYSQL_FIDELITY 方言批

宿主：`mysqladmin ping -h 127.0.0.1 -P 3306` 成功；`MYSQL_FIDELITY` 原先未设。本轮：

```
MYSQL_FIDELITY=1
MYSQL_FIDELITY_HOST=127.0.0.1
MYSQL_FIDELITY_PORT=3306
MYSQL_FIDELITY_USER=root
MYSQL_FIDELITY_PASSWORD  # 来自 config/local/.env，未回显
```

`auto_agents@127.0.0.1` 无 CREATE DATABASE，保真通道必须 root。

### 1.1 方言批（checklist §3 节点，含 37.6）

先前（dba 039 前）：37.6 失败 `'…T00:30:47' == '…T00:30:46.681121'`（DATETIME fsp=0 截断/秒取整）；同批 `1 failed, 21 passed in 18.35s` exit **1**。SQLite 同测绿。转 `/dba` 后：039 `listed_at` DATETIME(6) + ORM `MYSQL_DATETIME(fsp=6)`。本帽 **未**改产品代码，**未**用编排器「22 passed / 16.96s」口述盖章。

**本帽独立 37.6**（业务库当时仍 stamp **038** / `listed_at=datetime`；MYSQL_FIDELITY 走独立 schema `create_all`，不打业务库）：

```
$ MYSQL_FIDELITY=1 MYSQL_FIDELITY_HOST=127.0.0.1 MYSQL_FIDELITY_PORT=3306 \
    MYSQL_FIDELITY_USER=root MYSQL_FIDELITY_PASSWORD="$MYSQL_FIDELITY_PASSWORD" \
    uv run pytest -q \
      backend/tests/test_t28_listing.py::test_gwt_37_6_listed_at_survives_unlist
.                                                                        [100%]
1 passed in 1.86s
```

exit code **0**

随后同节点方言批（含 37.6；head 已是 039）：

```
$ MYSQL_FIDELITY=1 MYSQL_FIDELITY_HOST=127.0.0.1 MYSQL_FIDELITY_PORT=3306 \
    MYSQL_FIDELITY_USER=root MYSQL_FIDELITY_PASSWORD="$MYSQL_FIDELITY_PASSWORD" \
    uv run pytest -q \
      backend/tests/test_alembic_baseline.py::test_fresh_upgrade_head_matches_create_all \
      backend/tests/test_alembic_baseline.py::test_bootstrapped_db_upgrade_head_is_noop \
      backend/tests/test_t28_listing.py::test_gwt_37_6_listed_at_survives_unlist \
      backend/tests/test_t33_aliases.py::test_gwt_45_4_conflict_live_alias_both_unchanged \
      backend/tests/test_t25_subscribe.py::test_gwt_34_9_undeclared_host_compat_allows_any \
      backend/tests/test_t31_license.py::test_gwt_42_2_override_appears_still_gated \
      backend/tests/test_skill_public_api.py \
      backend/tests/test_t10_fix_regressions.py::test_null_aware_sort_roundtrip_mysql_fidelity
......................                                                   [100%]
22 passed in 17.79s
```

exit code **0**

同批 22 passed：空库 upgrade **039** ×2、37.6 listed_at 微秒往返、45.4 live alias、34.9 host_compat、42.2 TINYINT、`test_skill_public_api.py`（含 33.4/33.5）、ESC-2 NULL 排序。

### 1.2 `downgrade base`（生产禁止）

```
$ MYSQL_FIDELITY=1 … uv run pytest -q \
    backend/tests/test_alembic_baseline.py::test_downgrade_base_leaves_nothing
FAILED backend/tests/test_alembic_baseline.py::test_downgrade_base_leaves_nothing
1 failed in 11.71s
pymysql.err.OperationalError: (1553, "Cannot drop index 'idx_skill_jobs_source': needed in a foreign key constraint")
```

exit code **1**。生产禁止 `downgrade 037` / `downgrade base`。本轮 **未**重跑；1553 记录仍有效。

### 1.3 隔离库 038 ↔ 037（随后 DROP）

schema=`aa_qc_cond2_*`，`ALEMBIC_URL` 指向该库，**未**打业务库。

| 命令 | 退出码 | 耗时 |
|---|---|---|
| `alembic upgrade 038` | **0** | 1.95s |
| `alembic downgrade 037` | **0** | 0.03s |
| `alembic upgrade 038` | **0** | 0.02s |
| `DROP DATABASE` | **0** | — |

039 ↔ 038 隔离 up-down-up 已由 **dba** 实测退出码 **0**。本帽 **未**在业务库做 down；生产禁止 `downgrade` past 037。

### 1.4 业务库补 038（NFR-01 前置，expand-only）

本机 `auto_agents.alembic_version` 原为孤儿 **`030`**（树中无此 revision；`alembic current` → `Can't locate revision identified by '030'`）。表结构停在 **027**（`spider_tasks.status` 已 VARCHAR；无 `product_events` / `listing_state` / 031–038 表）。

**未**发明 DDL。操作：把 stamp 从谎言 `030` 改回真实祖先 `027`，再跑已有链 `027→038`。

```
# 1) restamp 030 → 027（仅 alembic_version 一行；schema 已是 027）
UPDATE alembic_version SET version_num='027' WHERE version_num='030';
# updated 1；after=('027',)

# 2) 业务库 expand-only
$ cd backend && uv run alembic -c alembic.ini upgrade 038
INFO Running upgrade 027 -> 031 …
INFO Running upgrade 037 -> 038, t33 capability_aliases vanity slugs
```

upgrade exit **0**；当时 `alembic current` → `038 (head)`。

### 1.5 业务库补 039（live listed_at，expand-only）

37.6 独立复跑通过后，业务库仍 stamp **038**，`information_schema` `listed_at` = `datetime`（fsp=0）。039 是精度加宽（DATETIME → DATETIME(6)），无 DROP。本帽 **未**发明 DDL，**未** down。

```
$ cd backend && uv run alembic -c alembic.ini upgrade 039
INFO  [alembic.runtime.migration] Running upgrade 038 -> 039, t28 listed_at DATETIME(6)；GWT-37.6 MySQL isoformat 往返
```

upgrade exit **0**；`alembic current` → `039 (head)`；`listed_at` COLUMN_TYPE = `datetime(6)`。

---

## 2. GWT-18.1 真 Worker（非 FakeRedis）

未跑 `backend/tests/test_spider_min_loop.py` 当本格（该测 FakeRedis 注入回流）。本格是 live：signup → login → POST `/api/v1/spiders/run` → Worker 爬 httpbin → StorePipeline → consumer ingest → webhook completed → 导出。

### 2.1 对照（task#1，IdleAutoClose 当时 120s；不作本轮 Then）

```
$ uv run python run.py start backend
backend 已启动  http://127.0.0.1:9111
exit: 0
$ uv run python run.py start spider
spider 已启动
exit: 0
$ curl -sS http://127.0.0.1:9111/api/v1/health/deep
{"status":"healthy","checks":{"mysql":"healthy","redis":"healthy"}}
```

heartbeat：`spider:worker:66d8ed2fb9fb`（pid=42638；含 `example`）。消费者 lifespan：`队列消费者已启动`。httpbin `https://httpbin.org/get` HTTP **200** time=0.84s。

| 步 | HTTP | 事实 |
|---|---|---|
| POST `/api/v1/public/tenant/signup` | **200** CREATED | tenant#6 `qc-cond2-preprod-1789000522` |
| POST `/api/v1/auth/login` | **200** | bearer |
| POST `/api/v1/spiders/run` example + httpbin | **200** CREATED | task **#1** pending @ 08:35:23 |
| 分发 | — | `任务已分发: task_id=1, spider=example, urls=1` |
| 爬取 | — | `Crawled (200) GET https://httpbin.org/get` @ 08:35:28（**+5s**） |
| 回流 | — | `结果已推送队列: spider:item_queue, task_id=1`；任务 `result_count=1` 仍 running |
| webhook | **200** | `POST /external/v1/webhooks/spider/callback` @ 08:37:32（**+129s**，空闲收尾 120s） |
| GET `/api/v1/spiders/results/1` | **200** | total=1 |
| GET `…/export?format=json` | **200** | list len=1 |

poll 首轮曾被环境变量 `HTTP_PROXY=http://127.0.0.1:7897` 打到 **502**（系统 Python urllib）；改 `curl --noproxy 127.0.0.1` 后直打 uvicorn。**skip ≠ pass**；本格未 skip。

对照结论：出数+导出成立；当时 IdleAutoClose **120s**，completed **+129s**，**不**作本轮 Then。completed 129s 是 RedisSpider 空闲收尾，不是 FakeRedis。未把 TestClient 当 18.1。

### 2.2 本轮 Then（idle-close 30s + `run.py restart spider`；task#2）

配置：`config/scrapy/default/settings.yml` 与 `config/scrapy/local/settings.yml` 均为 `SPIDER_IDLE_CLOSE_SECONDS: 30`。backend 未杀（pid=42633，08:32:49 起）。spider **restart**：pid=**73146** STARTED **10:40:38**；`runtime/run/spider.log` init @ 10:40:39。

编排器 live GWT-18.1（example+httpbin）。本帽核 `logs/api/api.log` + `logs/spider/spider.log`，**未**再 POST 新任务。

```
$ uv run python run.py status
backend  运行中  pid=42633  http://127.0.0.1:9111
spider  运行中  pid=73146
official  运行中  pid=42657  http://127.0.0.1:9113
$ curl -sS --noproxy 127.0.0.1 http://127.0.0.1:9111/api/v1/health/deep
{"status":"healthy","checks":{"mysql":"healthy","redis":"healthy"}}
```

deep HTTP **200**。

| 步 | 墙钟 | HTTP | 事实 |
|---|---|---|---|
| spider restart | 10:40:38 | — | pid=73146；IdleAutoClose **30s** |
| POST `/api/v1/public/tenant/signup` | 10:41:25 | **200** | tenant#7；user `qc181-1789008085` |
| POST `/api/v1/auth/login` | 10:41:26 | **200** | bearer user_id=12 |
| POST `/api/v1/spiders/run` example + httpbin | 10:41:26 | **200** CREATED | task **#2**；`urls=["https://httpbin.org/get"]` |
| 分发 | 10:41:26 | — | `任务已分发: task_id=2, spider=example, urls=1` |
| 爬取 | 10:41:30 | — | `Crawled (200) <GET https://httpbin.org/get>` |
| 回流 | 10:41:30 | — | `结果已推送队列: spider:item_queue, task_id=2`；consumer `批量落库完成: 1 条` |
| poll 出数仍 running | **+6.1s** | **200** | 编排器：`result_count=1` 仍 running（墙钟约 10:41:32 起持续 GET `/api/v1/spiders/tasks`） |
| IdleAutoClose | 10:42:04 | — | `连续空闲 30s，自动收尾: example items=1` |
| webhook completed | 10:42:05 | **200** | `POST /external/v1/webhooks/spider/callback`；`status=completed, result_count=1`。编排器时钟 **+40.56s**（墙钟 POST 10:41:26 → 回调 10:42:05 = 39s） |
| GET `…/results/2/export?format=json` | 10:42:06 | **200** | `_emit_exported … task=2 rows=1` |

Then「120 秒内任务进入完成且条数>0」：**PASS**（completed **+40.56s** &lt; 120s；`result_count=1`；export **200** rows **1**）。非 FakeRedis。本帽不改 coverage.md（翻格交 `/qa`）。Then PASS **不等于** 条件 A PASS，也**不等于**允许 LiteLLM/生产 动工。不是四柱 GA。

---

## 3. NFR-01（运行中 official + API；非 TestClient）

`test_nfr01_list_400_listed_p95_under_2s` **未**当作过章。

前置：§1.4 把业务库升到 038 之前，运行中 API 对该 URL 返回 **500**（`Unknown column 'capability_assets.listing_state'`）。升 038 后列表 200 / total=0。再插入 400 行 FR-33 过闸夹具（`nfr01qc2-000…399`，listed + stable + MIT）。

### 3.1 运行中 API（官网列表实际请求）

```
$ curl -sS --noproxy 127.0.0.1 --max-time 15 \
    -o /tmp/nfr01-sample.json -w "%{http_code} %{time_total}" \
    "http://127.0.0.1:9111/api/v1/public/capabilities?page=1&page_size=20"
```

20 次，P95 取 `samples[int(0.95*(n-1))]`（与单元测同一下标）：

```
i=00 http=200 t=0.020415 total=400 nitems=20
i=01 http=200 t=0.017661 total=400 nitems=20
…
i=19 http=200 t=0.020032 total=400 nitems=20
NFR01_API_P95 0.020032
min 0.014790 max 0.020415
codes {200} totals {400}
```

API P95 **0.020s &lt; 2s**。样例卡 `nfr01qc2-399` title=`NFR卡片399` listing_state=`listed`。

### 3.2 官网页（CRA 壳，不是卡片 paint）

```
$ uv run python run.py start official    # exit 0；http://127.0.0.1:9113
$ curl --noproxy 127.0.0.1 http://127.0.0.1:9113/capabilities
path=/capabilities http=200 time=0.001017 size=1905
```

20 次 HTML 壳 P95 **0.000786s**。壳含 `id="root"` + `static/js`，**不含** `capability-market` / `NFR卡片`（需 JS 再打 API）。

### 3.3 浏览器卡片可见（本轮；非 TestClient、非 API 顶格）

宿主现有 Chrome：`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`（**152.0.7977.83**）。未杀运行中 backend **42633** `:9111` / official **42676** `:9113`。未把 `test_nfr01_list_400_listed_p95_under_2s` 当本格。未加仓库 playwright 依赖：一次性装在 `/tmp/nfr01qc2-browser`。

计时定义：`page.goto(http://127.0.0.1:9113/capabilities, waitUntil=commit)` 起到 **`.capability-market__card` visible**。PASS 另要求首卡标题含 `NFR卡片`（夹具 `nfr01qc2-%`），空态「还没有上架的能力」或「市场列表加载失败」= 不能标 PASS。P95 下标与单元测相同：`samples[int(0.95*(n-1))]`。

```
$ "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version
Google Chrome 152.0.7977.83
exit: 0

$ mkdir -p /tmp/nfr01qc2-browser && cd /tmp/nfr01qc2-browser \
    && npm init -y && npm install --no-fund --no-audit playwright-core@1.49.1
added 1 package in 2s
exit: 0

$ node --version
v25.9.0
exit: 0

$ cd /tmp/nfr01qc2-browser && node measure.mjs
i=00 t=0.918163 cards=20 title=NFR卡片399 nfr=true
i=01 t=0.920240 cards=20 title=NFR卡片399 nfr=true
i=02 t=1.444558 cards=20 title=NFR卡片399 nfr=true
i=03 t=0.923827 cards=20 title=NFR卡片399 nfr=true
i=04 t=1.440300 cards=20 title=NFR卡片399 nfr=true
i=05 t=0.919619 cards=20 title=NFR卡片399 nfr=true
i=06 t=0.930203 cards=20 title=NFR卡片399 nfr=true
i=07 t=0.924314 cards=20 title=NFR卡片399 nfr=true
i=08 t=0.923113 cards=20 title=NFR卡片399 nfr=true
i=09 t=0.927096 cards=20 title=NFR卡片399 nfr=true
i=10 t=1.439944 cards=20 title=NFR卡片399 nfr=true
i=11 t=0.923745 cards=20 title=NFR卡片399 nfr=true
i=12 t=0.916092 cards=20 title=NFR卡片399 nfr=true
i=13 t=1.445863 cards=20 title=NFR卡片399 nfr=true
i=14 t=0.923327 cards=20 title=NFR卡片399 nfr=true
i=15 t=0.921751 cards=20 title=NFR卡片399 nfr=true
i=16 t=1.433630 cards=20 title=NFR卡片399 nfr=true
i=17 t=1.433926 cards=20 title=NFR卡片399 nfr=true
i=18 t=0.911064 cards=20 title=NFR卡片399 nfr=true
i=19 t=0.910927 cards=20 title=NFR卡片399 nfr=true
NFR01_BROWSER_P95 1.444558
min 0.910927 max 1.445863 n=20
warmup 0.923515 (discarded; cards=20 first=NFR卡片399)
idx=int(0.95*(20-1))=18
exit: 0
```

`measure.mjs`：`playwright-core` `chromium.launch({ executablePath: Chrome, headless: true })`；每样本新 `page`；等 `.capability-market__card, .capability-market__empty, .capability-market__error` 再确认卡 visible。warmup 见卡后 20 次计入 P95。空态/error/无 `NFR卡片` → exit 2，不标 PASS。

| 项 | 值 |
|---|---|
| 导航 | `http://127.0.0.1:9113/capabilities` |
| 每样本卡数 | **20**（page_size 默认 20；API total 仍 400） |
| 首卡 | `NFR卡片399`（`nfr01qc2-399` / listed） |
| 空态 / 错误 | **无** |
| 原始 20 样（s） | 0.918163 0.920240 **1.444558** 0.923827 1.440300 0.919619 0.930203 0.924314 0.923113 0.927096 1.439944 0.923745 0.916092 **1.445863** 0.923327 0.921751 1.433630 1.433926 0.911064 0.910927 |
| P95 | **1.444558s &lt; 2s** |
| 未测 | 筛选、详情、订阅点击（本格只要求列表卡片可见） |

未用 API P95 0.020s 顶本格。未改 MYSQL_FIDELITY §1。NFR 当时未重跑 18.1；18.1 Then 见 §2.2（completed +40.56s **PASS**）。

---

## 4. 本轮未做 / 仍开放

| 项 | 状态 |
|---|---|
| 37.6 DATETIME(6) 产品改动 | dba 已落 039 + ORM `MYSQL_DATETIME(fsp=6)`。本帽 **未**改产品代码。业务库 expand-only `upgrade 039` exit 0 |
| 037 down 先 drop FK 再 index | **不做**（dba）。`downgrade base` 仍 1553 |
| dockerd `compose down` | **PASS**：本帽独立 2026-09-10T03:53:38Z **exit 0**。命令见 §4.1。轮换半格仍 pending → 条件 A 整体 **not PASS**。不得把无 :4000 监听单独当 PASS；本轮 down 0 + ps 空 + info 0 |
| 机外轮换 `44e9446` | **attestation pending operator**。证据文件 `06-deliver/rotation-44e9446.md`（仅提供商名单）。无 `rotated:` 行。本帽不自勾已轮换、不代写日期。开网关前禁止 |
| Alembic 039 文件 | 确认存在：`backend/alembic/versions/039_listed_at_datetime_fsp.py`（工作树 `??`，未入库）。合主干必须含此文件。本帽不 commit |
| 条件 1 / 3 / 4 / 5 | qc **satisfied**（本帽不代跑） |
| 条件 6 | **lock**：FR-50/51/60/61 ➖；六问开放；不是四柱 GA |
| 合主干 039 | **必须**随 merge 上（`listed_at` DATETIME(6)）。生产禁止 down past 037 |
| Wave 2/3 GA | **禁止宣称** |
| 六问 | **不代选** |
| 默认 ENABLED | `POWER_MARKET.ENABLED=false` / `LLM.ENABLED=false` 直至档 2 |
| 根 compose 焊 litellm | **未焊** |
| `nfr01qc2-%` 400 行 | 已用于 Chrome 卡片可见；仍留本机。清理：`DELETE FROM capability_assets WHERE name LIKE 'nfr01qc2-%'` |
| `product_events` 1045 | `auto_agents@localhost` 无授权（授权在 `@127.0.0.1`）；事件 fail-open 不挡出数 |

---

## 4.1 条件 A 原样命令（2026-09-10）

先前 02:43:36Z / 02:31:34Z `down` **exit 1**（当时 sock 缺）**不作本半格**。本帽独立再跑 2026-09-10T03:53:38Z（dockerd 已起）：

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

idempotent 再跑仍 `DOWN_EXIT:0`。随后：

```
$ docker compose -f /Users/xuyun/auto_agents/deploy/litellm/docker-compose.yml ps -a
NAME      IMAGE     COMMAND   SERVICE   CREATED   STATUS    PORTS
PS_EXIT:0
```

条件 A compose-down 半格 **PASS**（exit 0）。

```
$ ls -la backend/alembic/versions/039_listed_at_datetime_fsp.py
-rw-r--r--  … backend/alembic/versions/039_listed_at_datetime_fsp.py
$ git status --short backend/alembic/versions/039_listed_at_datetime_fsp.py
?? backend/alembic/versions/039_listed_at_datetime_fsp.py
```

轮换证明：`rotation-44e9446.md` **无** `rotated:` 行 → attestation pending operator。条件 A 整体 **not PASS**。**动工 = NO**。

---

## 5. 条件 6 声明

本记录只覆盖冻结施工集（FR-01…20 + 70…75 + 30…45）的 **预发条件 2**。  
**不是**四柱产品 GA。条件 6 **lock**：FR-50/51/60/61 仍 ➖。Wave 2/3 stub 保持。六问保持开放、不代选。
