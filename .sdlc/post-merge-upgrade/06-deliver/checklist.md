# 发布清单 · 合入后四角色完备（post-merge-upgrade）

> 作者：/sre｜日期：2026-09-14｜commit：**未冻结**（祖先 `1db6a47` Merge origin/main；工作树 `feat/litellm-l1` 脏）
> 上游：`06-deliver/release-opinion.md`（qc **有条件放行** v1.7）｜`02-shape/contract.md`｜`02-shape/db-spec.md`｜`04-verify/test-report.md`
> 下游：操作者合入/预发；产品运营 `ops` 做人侧 enablement（**本帽不写用户公告 / CS 话术 / 亲爱的用户**）
> **本清单不做放行决策，只陈述检查结果。** 禁止写成四柱 GA。禁止「当前可买」。禁止 HMAC 夹具 = live 支付。禁止签发成功 = C2。禁止 FakeRedis/ingest = C4。

qc 条件 7：本文件存在，并抄条件 1–8；MYSQL_FIDELITY / C2 / C4 / M11.7 在 **qc 决策当时** 未勾。本 spawn 补跑见 §3.1（仅 M11.12）。

---

## 0. qc 有条件放行 — 条件 1–8（原文抄入，本帽不改判）

| # | 条件 | 责任人 | 本清单勾选 |
|---|---|---|---|
| 1 | **不得**标四柱 GA；**不得**宣称支付已通 / 市场已开店 / 北极星已在生产出现 | `/pm` `/ops` | 本帽遵守；不写对外文案 |
| 2 | live 支付通道指纹（非 HMAC 夹具、非超管确认收款）出现前，访客与租户可见面禁止「当前可买」 | `/frontend` `/pm` | 本帽不改可见面；预发抽检仍开 |
| 3 | GWT-M11.12 **不得**当 W2 已兑。须 `MYSQL_FIDELITY=1` 双连接同时 POST | `/sre` + `/backend` | qc 当时未勾。本 spawn 补跑见 §3.1；**不**改 `coverage.md` 为 ✅（条件 8） |
| 4 | C2 真网关轮仍是环境闸。签发成功 ≠ 对租户 live | `/sre` | **本机已勾**（§3.2）；签发成功仍 ≠ 对租户开通文案 |
| 5 | C4 live 工人 120s **本机已勾**（§3.3）；GWT-M11.7 live 收银台、结账 5s 墙钟仍未验证 | `/sre` | C4 **已勾**；收银台/5s **未勾** |
| 6 | 合入前对**冻结 SHA**重跑四闸：全量 pytest + arch.sh + admin/official **build** + `db_migrations.sh` | `/sre` | **未勾**（无冻结 SHA；见 §2） |
| 7 | `/sre` 写 `06-deliver/checklist.md`，抄条件 1–6，并写明 MYSQL_FIDELITY / C2 / C4 / M11.7 未勾 | `/sre` | 本文件 |
| 8 | coverage.md GWT-M11.14 行号下次改；**不得**把 M11.12 改成 ✅ | `/qa` | 本帽不改 coverage.md |

环境闸（合入后仍开，直到各节贴命令+退出码）：

- [ ] **冻结 SHA 四闸**（条件 6）
- [x] **C2** 真网关轮（条件 4）— 本机 2026-09-14，见 §3.2
- [x] **C4** live 工人 120s（条件 5）— 本机 2026-09-14，见 §3.3
- [ ] **GWT-M11.7** live 收银台（条件 5）
- [ ] **结账 5s** 墙钟（条件 5）
- [ ] **047 up→down→up** 真库回滚（§4：**未实测**）
- [x] **MYSQL_FIDELITY GWT-M11.12** 本 spawn 已跑（§3.1）；coverage.md 仍由 /qa 按条件 8 处理

---

## 1. 变更概要与风险分级

| 项 | 内容 |
|---|---|
| 变更内容 | W1–W5 四角色完备：规划未开放金标、导出 100 闸、拆第二套订购、未配通道可 `checkout_pending`、超管确认收款接结账单（ADR-0026）、专业档配额对齐定价页、出站查找只 `outbound_keys`、值班单入口、市场关旗诚实。DDL：**047**（`orders.channel` 放宽 NULL 且 DROP `DEFAULT 'offline'` + `plans.pro.quota_json` UPDATE + `plans.enterprise` INSERT）。**无新表、无新可部署单元。** |
| 影响面 | `POST /api/v1/billing/checkout`、`POST /api/v1/billing/orders/{id}/confirm`、规划/导出/出站/值班/货架；Admin `:9112` / 官网 `:9113`（端口来自 `config/default/{api,admin,official}.yml`） |
| **风险等级** | **中**（确认收款不可逆履约；047 是 expand 放宽+数据，不是删列。live 收银台 **不在本波**。并发 UNIQUE 本 spawn 已在隔离 MySQL 跑过，**不是**生产双 worker） |
| 发布策略 | 先合入代码+047，**市场保持关**（`POWER_MARKET.ENABLED=false`）、**LITELLM.ENABLED=false**、notify **不对公网**、工人不默认当北极星已出现。不按支付金额灰度。禁止印「当前可买」 |

### 三个风险问题

| 问题 | 答 |
|---|---|
| 出问题多快能发现？ | API 依赖：编排打 `GET /api/v1/health/deep`（MySQL SELECT 1 + Redis PING，失败 **503**；间隔见 compose 15s）。**不含** worker / LiteLLM / notify / 结账。业务：超管查 `order_status_reached`、`second_checkout_story_submitted`（必须 0）。deep 绿 ≠ 通道活 ≠ 工人活 |
| 出问题多快能回滚？ | **047 down 本 spawn 未实测，不编造分钟数。** 首选留下 047：停新确认（不要让超管点确认）、工人可 `run.py stop spider`、关市 PUT false、反代摘 notify。**禁止** `compose down`。**禁止** downgrade past **037**。current=047 时不要把 down 当随手回滚（见 §4） |
| **出问题数据会不会坏？** | 已 `fulfilled` **不会**随代码/047 回滚退回配额/SKU。047 down 若硬跑：NULL `channel` 行可能让 `MODIFY NOT NULL` 失败；`DELETE enterprise` 可能撞 `orders.plan_id`；`pro.quota_json` **不会**写回 040 种子（现行 `047.downgrade()` 缺这三步，与 db-spec §8 不一致） |

---

## 2. 门禁核对（引用实际输出，不接受「应该没问题」）

决策对象 = **工作树**，祖先 `1db6a47`，**无冻结 SHA**（qc R-06）。`sdlc.config.yaml`：`test` / `lint` / `build` / `migration`；`e2e: null`。

### 2.1 qc 窗指纹（2026-09-14，停在 T-23 前后；实现后又改过代码 → 条件 6）

| 闸门 | 命令 | 退出码 | 状态 |
|---|---|---|---|
| Jest admin | `CI=true npm test -- --maxWorkers=2` 指定文件 | 0 · 196 passed | ✅ qc；**不是**冻结 SHA |
| Jest official | 同上 4 文件 | 0 · 26 passed | ✅ qc |
| pytest FR-M 子集 | `uv run pytest -q` 17 个 `test_fr_m*.py` | 0 · 83 passed | ✅ qc |
| M12.8 | `test_fr_m12_fulfill.py::test_gwt_m12_8_*` | 0 · 2 passed | ✅ qc |
| 全量 pytest | `uv run pytest -x -q backend/tests` | 0 · 1854 passed, 41 skipped（qc：停在 T-23） | ⚠️ 条件 6 |
| arch.sh | `bash tools/check/arch.sh` | 0 | ⚠️ qc 实现期；本 spawn 复跑见下 |
| 前端 build | `npm run build --prefix frontend/{admin,official}` | qc 本窗无 | ⚠️ 条件 6 |
| 迁移 | `bash tools/check/db_migrations.sh` | qc 本窗无 | ⚠️ 条件 6；本 spawn 见下 **exit 1** |
| E2E | — | — | ➖ `e2e: null` |
| check-matrix.py | coverage.md + spec.md | 0 · 「22 条」= FR-\d+ 命名空间 | ✅ 非 FR-M 缺口 |

skipped（qc 全量 41）口径：默认未开 `MYSQL_FIDELITY` 的真库 skip + 既有 new-api 历史 skip + alembic `downgrade base` errno 1553 记录性 skip。**不得**把 skip 当失败，也不得把 skip 当 M11.12 已兑。

### 2.2 本 spawn 工作树补跑（祖先 `1db6a47`，脏树，**不是**冻结 SHA）

```
$ git rev-parse HEAD
1db6a4744662557b0443f8d5e687b2f03291a4c4
# 工作树：大量 M/??（实现未提交）。本帽禁 git commit / push。

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
ARCH_EXIT:0

$ bash tools/check/db_migrations.sh
✗ [SM-8] backend/alembic/versions/047_w2_channel_null_pro_quota.py: op.execute 含裸 SQL 但未标注为数据回填（LLM 禁写迁移 SQL——ADR-0002）
共 1 处违规
DBMIG_EXIT:1
```

SM-8 命中行：`047.downgrade` 的 `op.execute(sa.text("DELETE FROM plans WHERE slug = 'enterprise'"))`（单行 `op.execute(sa.text(...))`，且不是 `UPDATE.*SET` / `INSERT INTO capability` / `SELECT 1`）。046 能过是因为文件内已有 `# 回填:`。处置归 `/backend`（或 `/dba` 注释）：在 047 加 `# 回填` / `backfill` / `migration data` 之一（与 046 L198 同形）。**本帽不改 Alembic。** 合入前该闸必须 exit 0。

全量 pytest / 双 build：**本 spawn 未跑。**

### 2.3 合入前：冻结 SHA 再跑四闸（条件 6，**未勾**）

操作者提交后（本帽不 commit）：

```
SHA=$(git rev-parse HEAD)   # 钉进本清单后再跑，禁止先跑后改代码

uv run pytest -x -q backend/tests
# 贴：exit / passed / skipped

bash tools/check/arch.sh
# 期望 exit 0

npm run build --prefix frontend/admin
npm run build --prefix frontend/official
# 期望双 build exit 0。本机 Node 25 / npm 11 ≠ CI Node 20 npm@10（P-SRE-01）。
# 本机 ARM64 build 绿 ≠ linux/amd64（P-SRE-02）。

bash tools/check/db_migrations.sh
# 期望 exit 0。今日工作树 = 1（SM-8）。未修注释就冻结 = 该闸仍红。
```

- [ ] 冻结 SHA 已写入本清单 header
- [ ] 四闸命令 + 退出码贴在冻结 SHA 上
- [ ] skipped 数量已解释
- [ ] E2E 未配置有理由（`e2e: null`）

**门禁未全绿则不把预发当生产。** 豁免只走 qc 已写条件，本帽不改结论。

本机 `alembic_version=039`（`auto_agents` 库）。**039 ≠ 046 证据，更不是 047 已上。** 实现帽不得在本机未迁库上宣称 047 完成（db-spec §7）。

---

## 3. 需真实环境验证清单（来自 /qa + qc R-01…R-05）

| 用例 | 原因 | 执行结果 |
|---|---|---|
| GWT-M11.12 两买方并发 | SQLite ThreadPool ≠ InnoDB 生成列 UNIQUE | **本 spawn 已跑** MYSQL_FIDELITY，见 §3.1。coverage.md **不**由本帽改 ✅ |
| GWT-M31.4 双超管同时确认 | 行锁 CAS | ⚠️ 未跑 |
| C2 真网关轮 GWT-M34.2 | mock LiteLLM ≠ 上游 | **本机已勾**（§3.2）。签发 ≠ 对租户开通文案 |
| C4 live worker 120s | ingest+webhook 夹具 ≠ `run.py spider` | **本机已勾**（§3.3）。禁止写北极星已在生产出现 |
| GWT-M11.7 live 收银台 | HMAC/`signed_body` 夹具 ≠ 支付宝/微信 | ⚠️ **未勾**。HMAC ≠ 支付已通 |
| NFR-M01 结账 5s 墙钟 | Jest 路由跳转不代替 | ⚠️ **未勾** |
| 047 up→down→up | SQLite 无 `MODIFY NULL` 方言；down 与 db-spec 不一致 | ⚠️ **未实测**（§4） |
| 支付宝/微信 live | 通道 CIDR / 证书 / 报文 | ➖ 本波不执行、不合入闸 |

- [x] HMAC 夹具已标明 ≠ live 通道指纹（确认收款也 ≠ live 指纹）
- [x] C2、C4 本机已勾（§3.2 / §3.3）
- [ ] M11.7 / 结账 5s / 047 回滚 — 未勾
- [ ] 结果回填 `/qa` coverage.md — **禁止本帽把 M11.12 改成 ✅**（条件 8）

### 3.1 MYSQL_FIDELITY · GWT-M11.12（本 spawn 补跑）

凭据只走 `MYSQL_FIDELITY_*` 环境变量，**不落 yml / 不进 git**（`conftest.py`）。需要 `CREATE DATABASE`（应用用户 `auto_agents` 常无 1044 → 用 root 或预授权）。默认 host/port 与 conftest 一致：`127.0.0.1` / `3306`。

```
$ MYSQL_FIDELITY=1 \
  MYSQL_FIDELITY_HOST=127.0.0.1 \
  MYSQL_FIDELITY_PORT=3306 \
  MYSQL_FIDELITY_USER=root \
  MYSQL_FIDELITY_PASSWORD="$MYSQL_FIDELITY_PASSWORD" \
  uv run pytest -q \
    backend/tests/test_fr_m11_checkout_pending.py::test_gwt_m11_12_concurrent_same_product_one_pending \
    --tb=short
.                                                                        [100%]
1 passed in 1.99s
exit: 0
```

口径（诚实）：

- 真 MySQL 8、每测试独立 schema、`uk_orders_tenant_open_product` 在 InnoDB 上。
- 仍是 **同一 TestClient + ThreadPool 双 POST**，不是两个 uvicorn worker、不是生产双连接池。
- 走 ORM `create_all`，**不是** 047 迁移链。
- 本机 `auto_agents.alembic_version=039` 未参与本测。
- **不得**据此宣称 W2 生产并发已兑；**不得**由本帽改 coverage.md。

复跑时密码从环境注入，禁止把口令写进本文件。

### 3.2 C2 真网关轮 — 本机已勾（2026-09-14）

向租户开放渠道组/令牌 **之前**。`LITELLM.ENABLED` 默认 false（`config/default/litellm.yml`）。密钥：`AUTO_AGENTS_LITELLM__MASTER_KEY` / `AUTO_AGENTS_LITELLM__ADMIN__MASTER_KEY`，**不进 git**。根 compose **无** litellm 服务；独立 `deploy/litellm`。前置：`docker network create litellm-net`（已存在则跳过）。`LITELLM.BASE_URL` 默认 `http://127.0.0.1:4000`（`LITELLM.PROXY.PORT`）。

```
# 1) 超管唯一值班入口签发一把租户令牌（明文只一次）。签发成功到此为止。
# 2) 用该明文打真实对话（页上用法 / LiteLLM chat），不是套餐超限句。
# 3) 该企业中转用量 0 → ≥1。
# 4) 出站钥匙打同一 Base URL → 拒绝、0 行；用量基线不变。
```

失败 = 环境闸未过。**不得**把「令牌已签发」写成「网关已对租户开通」。

本机实测（`deploy/litellm` 独立 compose，非根 compose；Homebrew MySQL + 本机 backend `:9111`）：

```
# 网关
docker ps → litellm-proxy Up (healthy) 127.0.0.1:4000
GET http://127.0.0.1:4000/health/liveliness → 200 I'm alive!
GET /v1/models → deepseek-pro/* + kimi3/*（上游 Key 从本机 llm_providers 解密写入 deploy/litellm/.env，不进 git）

# 1) 签发（明文只一次）
POST /api/v1/relay/tokens group_id=1 name=c2-live-2 → 201 前缀 sk-  used_tokens=0  token_id=2

# 2) 真对话（不是套餐超限句）
POST :4000/v1/chat/completions  Bearer <签发明文>
  model=deepseek-pro/deepseek-v4-flash  max_tokens=8
  → 200  total_tokens=39

# 3) 用量 0→≥1 + 恰 1 条事件（spend 日志落盘后再 GET）
GET /api/v1/relay/tokens/2 → used_tokens=39  message=操作成功（非 60.5）
product_events：恰 1 行 event_name=relay_token_call_succeeded
  tenant_id=10  props={token_id:2, group_id:1, used_tokens:39}（无明文）

# 4) 出站钥匙打同一 Base URL → 拒绝；用量不变
POST /api/v1/outbound/keys → 201 前缀 ok-
POST :4000/v1/chat/completions Bearer <出站明文> → 401
  "LiteLLM Virtual Key expected. Received=ok-…, expected to start with 'sk-'."
GET /api/v1/relay/tokens/2 → used_tokens 仍 39
```

口径：真 LiteLLM v1.100.0 + 真上游 DeepSeek，不是夹具网关。签发成功 ≠ 本格；本格四步都过。本格绿 ≠ 四柱 GA、≠「当前可买」、≠ 对租户开通文案。

为让观察/事件在真网上成立，本机改了两处（合入前随工作树走，无冻结 SHA）：

1. `list_key_spend_logs` 改打 `GET /spend/logs?api_key=<key_hash>`。v1.100.0 `GET /spend/logs/v2` 无起止日期会 400，且行上常缺 `api_key` / `total_tokens`。
2. `_persist_event` 复用 `session.bind`（AsyncEngine）。原先 `create_async_engine(str(bind.url))` 把密码打成 `***`，独立会话 `auto_agents@localhost` 1045，主路径能写令牌、事件表一直 0 行。

### 3.3 C4 live 工人 120s — 本机已勾（2026-09-14）

根 compose **没有** spider。工人：`uv run python run.py start spider`。完成态必须是真 Scrapy + Redis，不是测试 ingest+webhook。

本机实测（Homebrew MySQL 8 + Redis 7，非 compose）：

```
$ uv run python run.py start backend --env local
$ uv run python run.py start spider --env local
$ uv run python run.py status --env local
# spider 运行中；heartbeat key spider:worker:* 在场
# POST /api/v1/public/tenant/signup 新建免费企业（非夹具）
# POST /api/v1/spiders/run spider_name=example params={"urls":["https://httpbin.org/get"]} priority=high
# GET /api/v1/spiders/tasks → id=3 status=completed result_count=1
# created_at 09:02:53 → completed_at 09:02:57（约 4s，≤120s）
```

口径：真 worker 消费 Redis 队列 + httpbin 出 1 条。**不是** FakeRedis / ingest+webhook。本格绿 ≠ 北极星已在生产出现。

回滚工人：`uv run python run.py stop spider`（不要 `compose down`）。

### 3.4 GWT-M11.7 live 收银台 + 结账 5s（未勾）— 怎么验

```
# Given 支付宝已配置（密文在 payment_channel_credentials，不进 git）
# When 买方结账选支付宝并去支付
# Then 进入通道 或 5 秒内见通道句 / FR-U32
# 开通仍须 FR-U38 验真。W2 合法开通边仍是超管确认，不靠本格。
```

`backend/tests/test_fr_u33_notify.py` 的 `signed_body` / HMAC **不是**本格。结账 5s：对 `POST /api/v1/billing/checkout` 墙钟，Jest 不算。

---

## 4. 回滚方案（**必须实测** → 本波数据回滚 = **未实测**）

### 代码回滚

无本 spawn 的「部署新版 → health → 回滚 → health + 业务请求」墙钟。**不编造耗时。**

首选（047 已上、要停新履约，**不要 down**）：

```
$ uv run python run.py stop spider
$ uv run python run.py status spider
# 期望：未运行

# 关市（进程内 overlay；yaml 默认 false）
$ curl -sS -X PUT "$API_BASE/api/v1/admin/power-market" \
    -H "Authorization: Bearer $PLATFORM_ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"enabled":false}'

# 反代摘 /api/v1/billing/notify/alipay 与 /wechat（无 JWT 写口）
# DELETE 凭据（挡通道路径；不撤销已 fulfilled）

$ curl -fsS "http://${API_HOST}:${API_PORT}/api/v1/health/deep"
# 编排探针必须 deep。浅 /api/v1/health 恒 200（P-SRE-04）。
# API_HOST/API_PORT 来自 config/default/api.yml（默认 127.0.0.1:9111）
# 或 AUTO_AGENTS_API__HOST / AUTO_AGENTS_API__PORT
```

**禁止任何 `compose down`**（不带 `-v` 已丢 Redis 队列/心跳；带 `-v` 再丢 MySQL）。已 `fulfilled` 不会退回。

### 数据回滚 · 047（expand：channel NULL + 两行价目）

文件：`backend/alembic/versions/047_w2_channel_null_pro_quota.py` revises **046**。生产禁止 downgrade past **037**。无 047 的 pytest 迁移三连（仓库无 `test_*047*`）。

**现行 `downgrade()` 与 db-spec §8 不一致（写下来的步骤 ≠ 可跑步骤）：**

| db-spec §8 要求 | 047.py 实际 |
|---|---|
| 先 `UPDATE channel='offline' WHERE channel IS NULL`，再 `NOT NULL DEFAULT 'offline'` | **无** NULL 回填，直接 `nullable=False` + `DEFAULT 'offline'` |
| `pro.quota_json` down 写回 040 种子 | **无** |
| enterprise：无订单引用才 DELETE；有 FK 则保留并声明 | 无条件 `DELETE FROM plans WHERE slug='enterprise'` |

因此：**不得声称 047 回滚已验证。** 有 W2 `channel IS NULL` 行时，MySQL `MODIFY NOT NULL` **预期失败**。有 `orders.plan_id` 指向 enterprise 时，DELETE **预期失败或破坏引用**。

#### 如何验证（隔离库；不要在 `alembic_version=039` 的 `auto_agents` 上试）

```
$ APP_ENV=local bash -lc 'cd backend && uv run alembic -c alembic.ini current'
```

| current | 允许 | 禁止 |
|---|---|---|
| **047** | 停确认 / 停工人 / 关市 / 摘 notify。结构留下 047 | 把 `downgrade 046` 当随手回滚；`compose down`；past 037 |
| **046** | 才允许在 **抛开库** 做 047 up→down→up | 在 039 库上 upgrade 047 当「已验证」 |
| **039** 或其它 | **停**。先把链走到 046，再谈 047 | 跳修订；在漂移库上宣称 047 |

抛开库（非本机 039）步骤：

```
# current 必须先 = 046
APP_ENV=local bash -lc 'cd backend && uv run alembic -c alembic.ini upgrade 047'
# SHOW CREATE TABLE orders → channel VARCHAR(16) NULL，且不得再出现 DEFAULT 'offline'
# SELECT quota_json FROM plans WHERE slug='pro';     -- 50/200000/5000000
# SELECT price_cents FROM plans WHERE slug='enterprise'; -- 99900（≠0、≠29900）

# W2 未配通道：INSERT 必须列出 channel，值必须是 SQL NULL（禁止省略列）
# SELECT channel ... → 仍是 NULL，不是被默认成 offline

APP_ENV=local bash -lc 'cd backend && uv run alembic -c alembic.ini downgrade 046'
# 今日脚本：可能在 NULL channel 或 enterprise FK 上失败。失败 = 回滚方案未就绪，不是「已验证可逆」。
# 若要按 db-spec 可逆，须改 047.downgrade（/backend），本帽不改。

APP_ENV=local bash -lc 'cd backend && uv run alembic -c alembic.ini upgrade 047'
```

本 spawn **未**执行上述三连。记录：

```
047 up→down→up：未跑
数据恢复能力：❌ 未验证（down 与 spec 不一致；SM-8 仍红）
```

### 配置回滚

| 配置项 | 本波值 | 回滚 | 备注 |
|---|---|---|---|
| `POWER_MARKET.ENABLED` | false（`config/default/power_market.yml`） | PUT false；重启回到 yaml | 本波 `OPS.DUTY_CONTACT` 空：禁止 `AUTO_AGENTS_POWER_MARKET__ENABLED=true` 重启开市（lifespan 拒启） |
| `LITELLM.ENABLED` | false | 保持 false | C2 未过不得对租户开 |
| `LLM.ENABLED` | 运行配置 | 关则规划金标「智能规划未开放」 | 不是支付回滚 |
| `BILLING.RELAY_PRICE_CENTS` | 19900（`config/default/billing.yml`；**价格不是密钥**） | 改配置 + 重启 API | 必须 `>0` 且 `≠29900`。覆盖：`AUTO_AGENTS_BILLING__RELAY_PRICE_CENTS` |
| Scrapy worker | 默认不在根 compose | `run.py stop spider` | C4 未过时保持停是合法 |
| 商户凭据 | 0 行或仅超管密文 | DELETE 通道凭据 | 确认收款 **不**读密钥全文 |

`.env` **不做** `${VAR}` 展开（P-SRE-07）。密钥用 `AUTO_AGENTS_MYSQL_DEFAULT_PASSWORD` / `AUTO_AGENTS_REDIS_DEFAULT_PASSWORD` / `AUTO_AGENTS_JWT__SECRET_KEY`（双下划线嵌套）。

### 数据兼容性

- [ ] 新版写入的 `checkout_pending` + `channel NULL`，旧版代码能读 — **未用旧版镜像验证**
- [x] 本波 `channel` 放宽为可空（expand）；不是加 NOT NULL
- [x] 新状态字面量 `checkout_pending` / `fulfilled`：读模型仍认识旧 `pending`/`paid`（contract）。旧代码遇新字面量须有 default；**未**用旧镜像打过
- [x] 无删列 / 无收紧 tenant_id NOT NULL / 不 DROP `open_product_slot`（046 生成列禁止 047 动）
- [ ] 047 down 按 spec 可逆 — **未验证**

### 回滚窗口与限制

| 项 | 内容 |
|---|---|
| 回滚窗口 | 结构：047 留下则代码可回。**一旦超管确认 → fulfilled，配额/SKU 不可随回滚撤回** |
| **不可撤回的副作用** | `offline_order_confirmed` / `order_status_reached.status=fulfilled` 已消费不可撤回；出站明文只显示一次 |
| 执行人权限 | 本 spawn **未**验证值班角色具备 alembic / 反代摘 location 权限 |

---

## 5. 监控接线

端口与探针一律来自 `config/`，禁止在 runbook 里写死另一套口。

| 类 | 指标 | 已接 | 面板 |
|---|---|---|---|
| 可用性 | `/api/v1/health/deep`（MySQL+Redis；失败 503） | ☐ 编排 HEALTHCHECK 已有；**不含** 结账/工人/网关 | compose / watchdog |
| 可用性 | 浅 `/api/v1/health` | ➖ **禁止**给编排用 | — |
| 延迟 | `POST /billing/checkout` 墙钟（NFR-M01 5s） | ☐ 未测 | — |
| 饱和度 | MySQL 连接池 / Redis | ☐ | — |
| 饱和度 | `spider:worker:*` 心跳（TTL 默认 30s，`WORKER_HEARTBEAT`） | ☐ C4 未开时不要当 P0 | — |
| **业务** | `order_status_reached`（`pending`/`fulfilled`，非夹具） | ☐ 超管事件查询面 | D1 |
| **业务** | `second_checkout_story_submitted` **必须 0** | ☐ | D2 护栏 |
| **业务** | `task_completed` 且 `result_count>0` 非夹具 | ☐ **不得**在 C4 未跑时当北极星已出现 | 北极星 |
| **业务** | `llm_planning_blocked` / `data_export_completed` | ☐ | FR-M06 |

**不要告警：** 关市 409 `MARKET_CLOSED`；规划未开放 422 `PLANNING_DISABLED`；未配通道 201 待支付；HMAC 夹具 notify 测试流量。

### 告警（每条带处理指引）

| 告警 | 级别 | 阈值+持续时间 | 处理指引 |
|---|---|---|---|
| API deep 非 2xx | P0 | `/api/v1/health/deep` 非 200 **持续 > 2 分钟**（与既有 watchdog 口径） | 1) 看 body `checks.mysql/redis` 2) 不是浅 health 3) 僵尸口：`lsof -i :$API_PORT`（PORT 来自配置）再 `kill`；SIGTERM 可能被忽略（P-SRE-06） 4) **禁止** `compose down` 当恢复。升级：deep 红且确认收款写失败 → 停超管确认 |
| D2 非 0 | P1 | 任意 `second_checkout_story_submitted` > 0 持续 10 分钟 | 1) 查是否旧 `POST /billing/orders` 又建行 2) 用量页是否仍可提交订购 3) 临时缓解：关旧入口流量（反代），**不**编用户公告。升级：持续写入 → backend 逃逸，本帽不改业务代码 |
| 同企同商品两笔待支付 | P0 | `open_product_slot` 非空行按 `(tenant_id, product)` count>1 | 1) 先停 checkout POST（反代）2) 不要让超管确认其中一笔 3) 查 UNIQUE 是否在该库 4) 本 spawn MYSQL_FIDELITY 绿 ≠ 该环境已迁 047/046。升级：数据不一致 → 人工对账，不 down 047 |
| 误标 live / 当前可买 | P1 | 访客/租户面出现「当前可买」「支付已通」或四柱 GA 句 | 1) 撤该构建前端 2) 确认无 live 通道指纹（HMAC 与确认收款都不是指纹）3) 文案归 `/ops` `/pm`，本帽不写 亲爱的用户 |
| C2 未过却有租户 chat 成功 | P1 | C2 记录未写完，中转用量 0→≥1 | 1) 关 `LITELLM.ENABLED` / 停签发 UI 2) 值班入口保持只读 3) 签发成功本来就不是 live——若已对租户宣传开通，交 ops 停传播，本帽不写话术 |

- [x] 每条有可能原因 + 排查 + 临时缓解 + 升级
- [x] 不是全 P0
- [x] 关市 409 / 规划未开放 422 抑制为预期
- [x] 阈值带持续时间

---

## 6. 灰度与放量判据（提前定，不临场判断）

无支付流量百分比。多租户按 **企业** 观察。本波 **不**放 live 收银台。

| 档 | 范围 | 观察时长 |
|---|---|---|
| 1 | 内部非夹具 1 企；市场关；notify 不对公网；工人按需 | 覆盖一次确认收款 **或** 明确不确认；覆盖一次规划未开放提交 |
| 2 | 更多内部企；仍禁止「当前可买」 | 1 个上海自然日 |
| 3 | 代码全量（仍非 GA、仍非 live 支付） | 持续；C2/C4 另闸 |

### 基线

无生产 n（蓝图：第一轮建立基线）。不得用 qc pytest 条数、官网 Hero、HMAC 成功当基线。

| 指标 | 基线值 | 取法 |
|---|---|---|
| `second_checkout_story_submitted` | **0** | 超管事件查询，上海自然周 |
| deep 5xx | 0（实验室） | 编排探活，不是浅 health |
| D1 `order_status_reached` | 无 | 建基线，不报转化率 |

### 放量条件（全部满足才从档 1 往下）

- ✅ 无 P0
- ✅ D2 = 0
- ✅ 访客/租户面无「当前可买」/「支付已通」/四柱 GA
- ✅ deep 绿（只说明 API+MySQL+Redis）
- ✅ 047 仅在 `alembic current` 已是 046 的库上 upgrade；本机 039 **先对齐**
- ❌ 不要求 C2/C4/M11.7 作为 **代码合入** 条件（qc：环境闸，不得宣称完成）
- ❌ 不要求 HMAC notify 当支付已通

### 回滚条件（任一满足即停新履约，**不讨论**）

- ❌ 同企同商品两笔待支付
- ❌ 确认金额不符却开通 / 企业档或 relay 写成 29900
- ❌ D2 > 0
- ❌ P0 deep
- ❌ 密钥进 git / 进租户响应 / 进日志
- ❌ 对外出现四柱 GA 或「当前可买」且无 live 通道指纹

### 低频路径

| 路径 | 观察窗口是否覆盖 |
|---|---|
| 超管确认收款（不可逆） | ☐ 档 1 应用内部单测过；预发真正确认 **未**作为本 spawn 步骤 |
| 迟到通道通知 `late_notify_at` | ☐ pytest 有；live notify 未开 |
| 工人心跳 TTL 后离线句 | ☐ C4 未跑 |
| 缓存 / 报表切日 | ➖ 本波无新 Redis 键 |

---

## 7. 容量评估

无生产 n。本波 **不新建** worker / 表 / Redis 键。047 = 小表 `MODIFY` + 两行价目；dba：无维护窗口。

| 项 | 数字 |
|---|---|
| 单次操作消耗 | 结账/确认为本进程同步（contract：距已知 p95 有余量；**结账 5s 墙钟未测**） |
| 预估调用量 | 无生产 n；不编造 |
| 峰值并发 | GWT-M11.12 靠 UNIQUE，不靠多 worker 排队 |
| **当前配置** | 根 compose：mysql 512m / redis 256m / backend 1g（`docker-compose.yml`）；无 spider 服务 |
| **调整** | 本波不扩。C4 要工人时用宿主 `run.py start spider`，不要为工人 `compose down` 重来 |
| 余量 | 无生产基线 → 不声称 50% 余量已验证 |

### 瓶颈资源核对

| 资源 | 当前 | 变更后预估 | 上限 | 余量 |
|---|---|---|---|---|
| DB 连接池 | 未知（无生产 n） | 确认 CAS 单行 | — | 未评估 |
| Scrapy worker | 0（compose 无） | C4 才需要 1 | — | — |
| LiteLLM | 独立故障域，默认关 | C2 才需要 | — | — |

---

## 8. 部署步骤

```
1. 冻结 SHA；四闸全绿（含 db_migrations SM-8 已灭）。本帽不 commit。
2. docker network create litellm-net（已存在则跳过）。不要把 litellm 焊进根 compose。
3. alembic current。039 → 先走到 046，禁止直接当 047 已验证。046 → upgrade 047。
4. 部署 backend / admin / official。端口来自配置：
   API 127.0.0.1:9111（AUTO_AGENTS_API__HOST/PORT；compose 容器内 HOST=0.0.0.0，对外仍 127.0.0.1 映射）
   ADMIN 9112 / OFFICIAL 9113
5. curl -fsS http://$API_HOST:$API_PORT/api/v1/health/deep  → 200 且 mysql/redis healthy
6. 抽检：访客面无「当前可买」；旧 POST /billing/orders 不建行；未配通道可待支付。
7. 不开启公网 notify；不把 HMAC 成功当指纹；不对租户称网关已开通（C2 未勾）。
8. 工人保持按需；C4 未跑不得写北极星已出现。
```

**每步回退：**

| 步 | 回退 |
|---|---|
| 3 | **不要**随手 `downgrade 046`。停在 047 结构 + 停确认。down 未验证 |
| 4 | 回上一构建；已 fulfilled 不退 |
| 5 | 查依赖；禁止浅 health；禁止 compose down |
| 7 | 反代摘 notify + DELETE 凭据 |

密钥三件套（机外，仓库零明文）：`AUTO_AGENTS_MYSQL_DEFAULT_PASSWORD`、`AUTO_AGENTS_REDIS_DEFAULT_PASSWORD`、`AUTO_AGENTS_JWT__SECRET_KEY`。Webhook：`AUTO_AGENTS_WEBHOOK__SECRET_KEY`。LiteLLM master **不**进租户复制框。

---

## 9. 发布窗口与人员

| 项 | 内容 |
|---|---|
| 建议窗口 | 工作日低峰。047 无用户维护窗（dba：小表 MODIFY NULL + 两行价目），但仍避开确认收款高峰 |
| 需要维护窗口 | **否**（db-spec §11） |
| 值班人 | 操作者指定；本 spawn 未点名 |
| 回滚决策人 | 操作者；current=047 时默认 **留下结构、停确认** |
| 相关方通知 | **不**由本帽写用户公告 / 亲爱的用户 / CS 话术 → `/ops` |

---

## 10. 检查结论（陈述事实，不做放行决策）

| 项 | 状态 |
|---|---|
| 门禁 | **未全绿**：无冻结 SHA；全量 pytest/双 build 未在冻结对象重贴；工作树 `db_migrations.sh` **exit 1**（047 SM-8）；arch 工作树 exit 0 |
| 需真实环境 | MYSQL_FIDELITY M11.12 本 spawn **1 passed / 1.99s / exit 0**。C2 / C4 / M11.7 / 结账 5s / 047 回滚 **未勾** |
| 回滚方案 | 代码路径有命令。**047 数据回滚未实测**；down 与 db-spec 不一致 |
| 数据兼容性 | expand 方向已写；旧镜像未验 |
| 监控接线 | 四类列出；业务指标有 D1/D2/北极星口径；编排 deep 已有。结账/工人/网关 **未**进 deep |
| 告警 | 5 条带指引 |
| 灰度判据 | 已定；live 支付不进本波放量 |
| 容量 | 无生产 n，未扩容 |
| **阻塞合入的项** | ① 冻结 SHA 四闸（含 SM-8 必须先灭）② 本帽不阻塞 qc 已声明的环境闸 C2/C4/M11.7（不得宣称完成） |
| **阻塞对租户称 live 的项** | C2、C4、live 通道指纹、047 回滚未验证（若要用 down） |

**放行决策 → `/qc`（已有条件放行）。** 本帽不改该结论，不标 GA，不印当前可买。

---

## 11. 自检

- [x] 风险已分级，策略与之匹配（中；确认不可逆；live 支付不放）
- [x] 三个风险问题已回答（回滚不编造分钟数）
- [x] 门禁引用实际输出（arch 0、db_migrations 1、M11.12 MYSQL_FIDELITY 0）
- [x] 需真实环境清单已列；C2/C4/M11.7 **未勾**
- [ ] **三类回滚全部实测** — 否；047 **未实测**
- [x] 回滚耗时未编造
- [x] 数据兼容性：旧镜像未验，已标明
- [x] 不可撤回的副作用已列出（fulfilled / 事件）
- [ ] 执行人权限未验证
- [x] 监控四类含业务指标
- [x] 每条告警有处理指引
- [x] 放量与回滚判据已写死
- [x] 基线不使用发布前一分钟 / 不使用 HMAC
- [x] 低频路径标明未覆盖
- [x] 容量未假装有 50% 实测余量
- [x] 每个部署步骤有回退
- [x] 未做放行决策
- [x] 无 亲爱的用户 / 无用户公告
- [x] 端口/密钥来自 `config/` 与 `AUTO_AGENTS_*`
- [x] HMAC ≠ live 支付指纹；确认收款 ≠ live 指纹
