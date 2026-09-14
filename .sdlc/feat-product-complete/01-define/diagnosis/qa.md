# QA 诊断 · feat-product-complete（覆盖缺口，非矩阵）

> 角色：`sdlc-workflow:qa`｜日期：2026-09-10｜泳道：L4｜阶段：**define**
> 性质：冻结集之后仍未验收 / 仍空洞的 GWT 清单；**不是** `04-verify/coverage.md`，不写新用例正文，不实现，不代选剩余六问，不放行。
> 上游：v2 spec v1.6 · v2 `04-verify/coverage.md` · v2 `state.yaml` open minors · `backend/tests/test_billing_relay.py` · 018c369 账务/渠道组骨架 + Alembic 040
> 词汇：coverage skill — 矩阵有映射 ≠ 有效断言；空心 `assert True` / 自比常量 / 零副作用也能绿 = 缺陷。方言：默认 pytest = SQLite；生产 = MySQL 8。

---

## 0. 结论先行（事实，非放行）

冻结施工集（FR-01…20 / 70…75 / 30…45）v2 矩阵写 **0 条冻结 GWT 硬 ❌**，但 **Wave 2/3 十二格从未按 Then 验收**。本特征里 Q-BILL / Q-RELAY **已决**，骨架已进树，v2 矩阵把 FR-50/51/60/61 整段标 ➖「未施工」**已经过期**。

| 桶 | 事实 |
|---|---|
| GWT-50.* / 51.* / 60.* / 61.* | **12/12 未验收**。实现有 HTTP 骨架 + 部分 UI；夹具未对照冻结 Then；与仍生效的 GWT-12.6 / 72.3 互相否定 |
| v2 coverage 主格仍 ⚠️ | GWT-16.1、32.3、33.4、36.1、45.5；13.3 主格 ✅ 但 SQL 备注 ⚠️ |
| 已实现但夹具空心 | `test_billing_relay.py` 四测钉的是骨架 HTTP，不是 50/51/60/61 Then；Usage「提交升级订单」无 click；PlatformOps 确认收款 0 Jest |
| open minors | IM-02/03/12/13/18/26、C35-QA-05 **仍空洞**。IM-04/05、IM-17/19、C35-QA-03/04 **代码侧已钉、state.yaml 仍 open**（本帽不代关） |
| TestClient 顶不了 | NFR-01 卡片可见、GWT-18.1 真 Worker、NFR-07 Chrome 布局、50/60/61 屏上 CTA、040 方言。见 §6 |

**不是四柱 GA。不代选 Q-VOICE / Q-PRICE / Q-MARKET-USER / Q-AGPL / Q-OPS-COLLECT。**

---

## 1. GWT-50.* / 51.* / 60.* / 61.*（必须点名）

v2 spec 把这四条写成 Wave 2/3 **stub**。v2 coverage §1.4 整段 ➖，备注「满额 CTA 已由 12.6/12.7 覆盖、未绑定已由 FR-13 覆盖、无渠道组已由 72.3/01.2 覆盖、不熔断已由 07.6 覆盖」——那是 **stub 切片**，**不顶**本特征在 Q-BILL/Q-RELAY 关闭后的产品 Then。

本特征已决：

- Q-BILL：支付先空；线下订单；在线通道 `PAYMENT_NOT_CONFIGURED`
- Q-RELAY：租户渠道组 SKU（`relay_groups` + `relay_tokens`）；租户改不了全局熔断

树内已有：`backend/app/api/v1/billing.py` / `relay.py`、Alembic 040、admin `/usage` 提交升级、`/relay` 渠道组、`/platform-ops` 确认收款。**验收格全部空。**

### 1.1 FR-50 满额下一步不是再注册

| GWT | 冻结 Then | 现网 | 夹具 | 判定 |
|---|---|---|---|---|
| **50.1** | 存储已满 → 去结果库/清理说明，不是注册 | `Usage.tsx` 存储满钮 `href="/data"` 文案「去结果库」 | `Usage.test.tsx`「storage full CTA」钉 `/data`、禁 `/register`。**这是 GWT-12.7 的 Then，被 v2 矩阵用来顶 50.1** | **未单独验收 50.1**。无「清理说明」。无浏览器 |
| **50.2** | token 已满 → 与「再注册」不同的出口（联系说明或运营工单，以 Q-BILL 为准） | 双 CTA：`申请提升配额` → mailto 弹窗（12.6）；另有 **`提交升级订单`** → `POST /billing/orders` channel=offline | Jest **只点 mailto**（`token full CTA does not go to register`）。`createOrder` 已 mock，**零 click「提交升级订单」** | **空洞**。Q-BILL 已决线下单，12.6 mailto 与 50.2 线下单并存，**PM 须重冻出口，QA 不代选** |
| **50.3** | 只读点申请提升 → 说明找管理员，不改套餐 | 只读横幅「只读可见进度，不能改套餐」；`申请提升配额` **未**按只读隐藏；`提交升级订单` 有 `!readonly` | viewer 夹具用量未满，**从不点申请提升**。API：`test_viewer_cannot_create_order_or_token` 钉 POST orders **403** | **半格**：API 拒写下单已钉；UI Then「说明找管理员」未钉 |

与冻结 **GWT-12.6/12.7** 的关系：那两格 Wave 0 已 ✅（不到注册）。**不得**把它们勾成 FR-50 已覆盖。

### 1.2 FR-51 租户自助出站钥匙

冻结正文：**下一轮**。出站拉数钥匙 ≠ 中转虚拟令牌。

| GWT | 冻结 Then | 现网 | 夹具 | 判定 |
|---|---|---|---|---|
| **51.1** | 经办找「自己签发拉数钥匙」→ 无该能力；不得把平台共享钥匙写成租户功能 | 无自助出站钥匙 UI。`/relay` 签发的是 **LLM 渠道组令牌** `sk-…` | `test_billing_relay.py` **零命中** 出站/external API | **未验收**。若有人把 relay token 映射到 51.1 = 合同错误 |
| **51.2** | 出站未绑企业 → 仍走 FR-13 拒绝、0 行 | FR-13 仍在 | `test_external_api.py` 钉 13.2；**不在** billing_relay | stub 切片真；**不是** 51 完成态 |
| **51.3** | A 用未绑定或绑 B 的钥匙拉 A → 0 行；本波无自助签发入口 | 同 FR-13.3 | HTTP 跨租户在 `test_external_api.py:420`；SQL 编译在 `test_spider_datacenter_crud.py:830`（MagicMock） | 越权 HTTP ✅；**无「自助签发入口不存在」正向夹具** |

### 1.3 FR-60 中转对租户可见性

**合同碰撞（PM 必须重冻，本帽不代选）：**

- 冻结 **GWT-60.1 / GWT-72.3**：Q-RELAY **未关** → 无「我的渠道组 / 我的中转令牌」；定价无渠道组当前可买
- 本特征 Q-RELAY **已关**，admin `menuConfig` 已挂 **「渠道组」** `/relay`，`RelayGroups.tsx` 可新建组/签发令牌
- 官网 `Pricing.tsx` 企业档仍把「中转站渠道组分配」标 **预告不可购买**（GWT-01.2 B2 / Q-PRICE 未关）
- `App.test.tsx:96` 仍禁文案「我的中转令牌」（70.4/72.3 冻结句）

| GWT | 冻结 Then | 现网 | 夹具 | 判定 |
|---|---|---|---|---|
| **60.1** | Q-RELAY 未关 → 无「我的渠道组」；定价无渠道组当前可买 | 后台 **有** 渠道组屏；定价 **仍预告** | RelayGroups Jest 只断言页上有 `default` +「改不了」；**未**断言菜单出现/定价仍预告这一对 | **冻结 Then 与已决 Q-RELAY 互否**。未验收 |
| **60.2** | 定为独立 SKU 且已履约 → 只读「我的渠道组」，能看自己用量与状态，**不能改全局熔断**；spec：**Q-RELAY 关闭前不进实现** | Q-RELAY 已关。页 **可写**（新建组/停用组/签发令牌），不是「只读」。令牌 `used_tokens` **无消耗路径**。RPM/TPM **无执法夹具**。令牌 **不打网关鉴权** | `test_relay_group_token_issue_and_revoke` 钉 CRUD+跨租户 PATCH 404+吊销。`test_tenant_still_cannot_write_platform_channels` 只 **GET** `/newapi/channels` ∈ {403,404}，**不是** 改熔断 | **骨架有、SKU Then 空心**。60.2「只读」vs 实现可写 vs Q-RELAY 未写只读 → **回 PM** |
| **60.3** | 任一 Q-RELAY 答案，租户改全局熔断 → 拒绝（Wave 0 已冻） | 写平台渠道仍 `require_platform_admin` | 07.4 HTTP 拒写窗口仍在；billing_relay **未** PATCH 熔断/探针阈值 | **不熔断写权**靠 07.4/07.6；**本 stub 无独立格** |

### 1.4 FR-61 探针伪装不自动下线

| GWT | 冻结 Then | 现网 | 夹具 | 判定 |
|---|---|---|---|---|
| **61.1** | 探针判伪装 → 值班能看到伪装，渠道不因此自动关闭（与 07.6 同一熔断句） | `NewApiOps.tsx` 有 spoofed 计数 | 07.6 `test_llm_probe.py:168` / `test_channel_config_service.py:152` 钉 **不自动关**。**无**「值班页看得见伪装」UI Then。billing_relay **零探针** | 熔断句有；**可见性 Then 空洞** |
| **61.2** | Wave L 完成且网关不可达/未登记 → 走 71.2 或 71.3，不另写第二套空态 | 71.2/71.3 已 ✅ | 不得用 61.2 再造空态 | **不另测**；禁止第二套句 |
| **61.3** | 租户改探针阈值 → 无入口 | 租户 `/newapi` 404 同形（07.3） | 无「探针阈值」控件夹具 | **入口隐藏靠 07.3**；阈值二字未钉 |

---

## 2. v2 coverage 里仍 ⚠️ / 空洞的行

来源：`.sdlc/feat-four-pillars-v2/04-verify/coverage.md`（本帽 **不改** 该文件）。

### 2.1 主格仍 ⚠️

| 格 | 文件:行 | 为什么仍是洞 |
|---|---|---|
| **GWT-16.1** | `test_llm_usage_service.py:172` | 冻 Python `ZoneInfo` 上海月，**不是** MySQL `DATE`/`CONVERT_TZ`。矩阵自标需真库 DATE 语义；CI MYSQL_FIDELITY 子集 **不含** 该 node |
| **GWT-32.3** | `test_skill_public_api.py:158` | 响应字节 `== STORE_NOT_FOUND_HTML.encode()`：**API 自比自己拼的常量**。文案碰巧等于官网 `NotFound.tsx` subTitle，但 HTML 是手搓 `<h1>404</h1>`，**不是** Ant Design Result 真 404 DOM。IM-02 |
| **GWT-33.4** | 技能端 `:242` 钉 `len(items)==20`；能力端 `test_b1c_capabilities_coverage.py:812` **只钉** `total==20` 且 page2 空，**不钉** `len(d1["items"])==20` | IM-03。查询侧 LIMIT vs 内存滤，能力端仍可绿 |
| **GWT-36.1** | `test_t27_references.py:40` | 未上架子技能在引用列表：有。`seed_gift_install` 只断言礼包名 **不在** 列表，**没有**「插件礼包合集边」对照行。IM-18 |
| **GWT-45.5** | `test_t33_aliases.py:199` | `len(after)==before==0`。Then 是「同步不自动建 alias」。**未钉同步实际出数**（源同步若空转，本格仍绿）。IM-26 |
| **GWT-13.3** 备注 | `test_spider_datacenter_crud.py:830` | 主格 HTTP ✅；SQL 格是 **MagicMock compile** 含 `tenant_id`，**不是** 真库绑参 |

### 2.2 曾 ⚠️、预发已翻 ✅、未进仓库 CI（一次性，TestClient 不顶）

| 格 | 证据 | 本特征仍欠 |
|---|---|---|
| GWT-18.1 / TC-18.1 | live Worker +40.56s completed；FakeRedis **不顶** | 未进 CI；Idle 30 ≠ 18.4 窗 120 |
| NFR-01 / TC-N01 | Chrome 卡片可见 P95 1.445s；`test_b1c…:835` TestClient **不顶** | playwright 在 `/tmp`，无仓库 E2E |
| GWT-37.6 | MYSQL_FIDELITY 1.86s；039 DATETIME(6) | CI 保真子集 **不含** `test_t28_listing.py` |
| GWT-34.9 / 42.2 / 45.4 | 预发方言批 22 passed | 同上，未进 `.github/workflows/ci.yml` 保真命令 |

### 2.3 状态流转 / 六态空洞（coverage §3 / §7）

| 洞 | 标记 |
|---|---|
| listed→coming_soon 无独立 HTTP 名 | ⚠️ 非硬缺口 |
| 节点监控 / 运行日志 六态 | ❌（edge-states 有屏，冻结 FR 无 GWT，**不发明 FR**） |
| 成员管理离线 / 数据中心离线 / 系统设置离线 | ❌ |
| 仪表盘六态 | ⚠️ smoke |
| 订阅弹窗离线 / 治理叶离线 | ⚠️ IM-12 / IM-19 |
| 官网首页/市场列表「失败句兼离线」 | ⚠️ 未分格 |

### 2.4 本特征新屏：coverage 根本没有行

`/usage` 提交升级、`/relay` 渠道组、`/platform-ops` 待确认订单、价目 `GET /billing/plans` — v2 矩阵无 FR 行。**不是**「已覆盖」。

---

## 3. open minors（独立核，不代关 state.yaml）

v2 `state.yaml` 仍 `status: open`。下面是 **读测试后的事实**，不是 changelog。

| id | 影响格 | 独立核 | 本特征处置 |
|---|---|---|---|
| **IM-02** | 32.3 | 仍自比 `STORE_NOT_FOUND_HTML`。官网 SPA 404 = antd Result +「返回首页」按钮；API HTML ≠ 该 DOM | **仍空洞**。关法：浏览器打未上架短名，对 **渲染后文案** 与 `NotFound.tsx`，禁止只 `assert content == CONSTANT` |
| **IM-03** | 33.4 能力端 | `:817` 无 `len(d1["items"])==20` | **仍空洞**。LIMIT/OFFSET 方言要 MYSQL_FIDELITY，不能只 SQLite 内存滤 |
| **IM-04** | 33.2 | 六行夹具仍无 `override=1`；许可特例在 42.2 `:97` 且预发方言已过 | 33.2 夹具缺口 **仍在**；Then 已迁 42.2。不升 ❌ |
| **IM-05** | 42.2 | TINYINT vs SmallInteger：预发 MYSQL_FIDELITY PASS | **方言债已过**；state 仍 open，本帽不代关 |
| **IM-12** | 订阅弹窗离线 | `SubscribeModal.test.tsx` **无** `navigator.onLine=false`。兜底句是「订阅失败。检查网络后重试。」冻结句是「订阅失败：网络不可用。连接恢复后再订阅到 {host}。」不关窗 | **仍空洞**。jsdom 可测离线句；**真离线提交**仍要浏览器 |
| **IM-13** | CTA `from` | `CapabilityDetail.test.tsx:152` 负向 `not.toContain('from=/capabilities/')`。实现 `bounce.set('from', …)` 后 `URLSearchParams` **编码**，字面量本来就不会出现。`Register.test.tsx` 用了 `decodeURIComponent`；本格 **未解码** | **空心负向**。须 `decodeURIComponent(href)` 再断言 `from` / `subscribeType` |
| **IM-17** | 37 治理短名 | 现有 `IM-17 open in catalog keeps short name`：`catalogFocusCopy('child-a')` + 页上 `pack-a__child-a` | **代码侧已钉**；state 仍 open |
| **IM-18** | 36.1 | 见 §2.1 | **仍空洞** |
| **IM-19** | 37 分页 | `IM-19 governance catalog table paginates` 钉 `.ant-pagination` +「共 1 条」+ `GOVERNANCE_PAGE_SIZE===20`。**未**测第 2 页 / 真滚动 | **弱钉**；叶级分页 HTTP 仍无。state 仍 open |
| **IM-26** | 45.5 | 见 §2.1 | **仍空洞** |
| **C35-QA-03** | Register copy | `Register.test.tsx:177` 钉 `FREE_TIER_FEATURE_COPY` 三句、禁 `10000`。coverage 已写「已关」 | **代码侧已关**；state 仍 open |
| **C35-QA-04** | src_sync 命令收回 | `test_t29_sources.py:538` `test_src_sync_retracts_commands_removed_from_manifest` 钉软删 + `sync_state=gone` | **代码侧已钉**；state 仍 open |
| **C35-QA-05** | qc-cond-4 证据 | `03-impl/qc-cond-4-evidence.md` §8 仍写「Register.tsx 仍手写」；§9 Debug 仍贴 DEFAULT_QUOTA 空心绿段落，易被当现行绿 | **仍空洞（文档）**。不挡产品 Then，但会骗下一轮 qa |

IM-24 过时注：coverage 已改写；删除源文件收回 = C35-QA-04，现有测试。

---

## 4. `test_billing_relay.py` 实际钉了哪些 Then

文件：`backend/tests/test_billing_relay.py`。层：FastAPI **TestClient** + 默认 **SQLite** `create_all`。**不跑 Alembic 040。不打浏览器。不打 LiteLLM。**

### 4.1 钉了（骨架事实，不是 50/51/60/61 冻结句）

| 测试 | 钉住的断言 | 能勾的产品句 |
|---|---|---|
| `test_list_plans_and_offline_order` | GET `/billing/plans` 200 含 `free`/`pro`；POST alipay → **400 `PAYMENT_NOT_CONFIGURED`**；POST offline → **201 pending**；超管 GET `/billing/admin/orders` 见该单；POST `…/confirm` → **paid**；租户 `quota.task_concurrency==20` 且 `TenantSubscription.plan_id==pro` | Q-BILL「在线未开通 + 线下挂账 + 人工确认改配额」。**不是** 50.1/50.2 CTA |
| `test_viewer_cannot_create_order_or_token` | viewer POST `/billing/orders` **403**；GET `/relay/groups` **200**；POST `/relay/tokens` **403** | 只读不能下单/发令牌（50.3 / 60 写权的 **API 半格**） |
| `test_relay_group_token_issue_and_revoke` | 默认组名 `default`；POST 组 201；POST token 201 且 `plaintext_key`/`key_prefix` 以 `sk-` 起；列表后再读 `plaintext_key is None`；跨租户 PATCH 组 **404**；DELETE token → `revoked` | 租户 SKU CRUD + 跨租户隔离 + 明文只出现一次。**不是** 60.2 用量、熔断、网关鉴权 |
| `test_tenant_still_cannot_write_platform_channels` | GET `/newapi/channels` ∈ **{403,404}** | 07.3 切片；**不是** 60.3「改全局熔断」 |

### 4.2 没钉（空洞 / 缺失）

**计费**

- 50.1 去结果库 / 清理说明（UI）
- 50.2 点「申请提升」或「提交升级订单」的 **屏上出口**（mailto vs 线下单 vs 注册）
- 50.3 只读点申请提升 → 「找管理员」
- GET `/billing/subscription`、租户 GET `/billing/orders`
- 租户 POST confirm（应 403）
- `wechat` 通道、`ORDER_FREE_PLAN`、`idempotency_key` 唯一、cancel、账期 `current_period_end`
- 确认后 Usage 页数字变为专业档（Jest mock 配额仍 100/100 将满夹具）
- 定价页专业档仍「预告不可购买」vs API 已能线下买 pro — **与 Q-PRICE 未关撞车，不代选**

**中转**

- 60.1 菜单有/无「渠道组」；定价「当前可买」
- 60.2 只读看用量/状态；**RPM/TPM 执法**；**used_tokens 增加**；token 打网关
- 60.3 PATCH 熔断/窗口/探针阈值
- 61.1 值班看得见 spoofed
- 61.3 探针阈值入口
- 明文 token 再 GET 不回放（已钉列表 None，未钉二次 issue 日志/审计）
- 组名冲突 `RELAY_GROUP_EXISTS`、停用组再签发 `RELAY_GROUP_DISABLED`

**出站钥匙（51.*）** — 本文件 **零断言**。

**前端**

- `Usage.test.tsx` mock 了 `createOrder` **从未调用**
- `RelayGroups.test.tsx` 不点新建/签发/停用/只读
- `PlatformOps.tsx` 确认收款 **0 测试文件**
- `App.test.tsx` 仍禁「我的中转令牌」，与 `/relay` 菜单并存

---

## 5. 已实现但夹具空心（冻结集外落地）

| 实现 | 夹具为何空心 |
|---|---|
| Alembic **040** `JSON_ARRAY_APPEND` / `JSON_CONTAINS` 回填 `menu:relay` | pytest 默认 `create_all`，**绕过** 该 SQL。SQLite 跑不了这句 |
| `ALL_ORM_TABLES`（`test_db_fixtures.py`） | **无** `plans` / `tenant_subscriptions` / `orders` / `relay_groups` / `relay_tokens`。MYSQL_FIDELITY `test_all_orm_tables_on_mysql` 与 `test_fresh_upgrade_head_matches_create_all` **会按缺表红**（未跑本帽，标风险） |
| `quota_json` TEXT；`models_json` JSON；`is_public` Integer | SQLite 不检 JSON/TINYINT |
| `uq_relay_groups_tenant_name`、`orders.idempotency_key` 唯一 | 无并发/撞键夹具 |
| 令牌 `key_hash` SHA-256 | 未钉「列表不回放明文」以外的哈希往返 |
| 确认收款改 `Tenant.quota` | 未钉 Usage 页 / 套餐闸随后一笔 LLM 用新上限 |

空心定义（coverage skill）：有 file:line 但断言不对照 Then，或零副作用也能绿。

---

## 6. 哪些必须 MYSQL_FIDELITY / 浏览器 — 不能用 TestClient 顶

### 6.1 MYSQL_FIDELITY（真 MySQL 8）

| 项 | 为什么 SQLite / TestClient 不够 |
|---|---|
| Alembic 040 | `JSON_ARRAY_APPEND`、`JSON_CONTAINS`、InnoDB FK、`DATETIME(timezone=True)` |
| create_all ↔ upgrade head | `ALL_ORM_TABLES` 必须含五张新表，否则保真通道假绿或假红 |
| IM-03 / 33.4 能力端 | LIMIT/OFFSET + 查询侧闸 vs 内存滤 |
| IM-05 / 42.2 | 已过预发；回归须留在保真集 |
| 37.6 listed_at | 已过预发；CI 子集仍无 `test_t28_listing.py` |
| 16.1 | 若验收的是 **SQL 月界**，Python `ZoneInfo` 单测不顶 |
| 13.3 SQL 绑 tenant | MagicMock 不顶 `execute` 绑参 |
| 60.2 组名唯一 / 订单幂等键 | 真唯一约束 + 并发 |
| billing confirm 改 JSON 配额 | MySQL JSON/TEXT 往返 |

CI 保真命令（`.github/workflows/ci.yml`）仍是 8 文件旧子集：**不含** `test_billing_relay.py`、`test_t28_listing.py`、`test_skill_public_api.py`、`test_b1c_capabilities_coverage.py`。预发方言批未入库。

### 6.2 浏览器（非 TestClient，非仅 jsdom 令牌）

| 项 | 为什么 |
|---|---|
| **NFR-01** | 卡片可见 P95；coverage 已写 TestClient 不顶。一次性预发，未进 CI |
| **GWT-18.1** | 真 Worker + 真 Redis；FakeRedis / TestClient 入队 200 **不顶** completed+条数 |
| **GWT-50.1/50.2/50.3** | CTA 是按钮/mailto/路由，不是 JSON。jsdom 可点 mailto；**提交升级订单 → 人工确认 → 用量数字变** 是跨页旅程 |
| **GWT-60.1/60.2** | 菜单「渠道组」、页上「改不了」熔断、只读看不见签发。`App.test` jsdom 壳 **可以**测菜单有无；**不能**测令牌用量 |
| **GWT-61.1** | 值班页看见伪装色/字，不是 GET JSON |
| **IM-12** | 冻结离线句；真 `navigator.onLine` + 不关窗 |
| **NFR-07 真布局** | 现 Jest 只量 CSS 令牌 44px，coverage 自承非 Chrome 实验室 |
| Pricing「渠道组当前可买」 | 静态 Jest 已能测预告 Tag；**与后台已卖 SKU 是否同屏撒谎** 要对照官网+后台两棵树，仍不是 TestClient |

`db_client` = Starlette TestClient。它合法覆盖：**状态码、信封 code、落库字段**。它 **非法顶**：方言 SQL、浏览器 CTA、真 Worker、真 404 DOM、触摸布局。

---

## 7. 给下游（本帽不修、不写矩阵）

| 给谁 | 内容 |
|---|---|
| `/pm` | 重冻 50.2 出口（mailto vs 线下单）；重冻 60.1/72.3（Q-RELAY 已关 vs「无渠道组」）；60.2 只读 vs 可写组/令牌。Q-PRICE 未关：定价专业档预告 vs API 可买 pro。**不代选** Q-VOICE/Q-PRICE/Q-MARKET-USER/Q-AGPL/Q-OPS-COLLECT。GWT-51 是否进本特征 |
| `/qa` 验证帽 | 本文件是缺口清单。**禁止**把 `test_billing_relay.py` 四测勾成 50/51/60/61 ✅。**禁止**写 `04-verify/coverage.md` 直到塑形票有新 GWT |
| `/backend` | 保真集扩 040 + billing_relay；`ALL_ORM_TABLES` 五表；33.4 能力端 `len==page_size`；45.5 先钉同步出数再钉零 alias；13.3 真库绑参；relay 令牌运行时/配额执法若在范围内 |
| `/frontend` | 提交升级订单 click；只读申请提升句；PlatformOps 确认；RelayGroups 只读/写；IM-12 冻结离线句；IM-13 decode `from` |
| `/dba` | 040 空库 upgrade head；JSON_ARRAY_APPEND 回填；downgrade 仍 1553 禁过 037 |
| `/sre` | 18.1 / NFR-01 一次性证据未入库 CI；新屏无 E2E（state.yaml `e2e: null`） |
| `/qc` | 不放行。v2 条件 6 lock「50/51/60/61 ➖」与本特征「骨架已落地」冲突，须新条件表 |

---

## 8. 自检

- [x] 点名 GWT-50.1–50.3 / 51.1–51.3 / 60.1–60.3 / 61.1–61.3
- [x] 点名 v2 coverage ⚠️ 与空心行
- [x] 点名 IM-02..05 / 12 / 13 / 17..19 / 26 / C35-QA-03/04/05
- [x] 拆 `test_billing_relay.py` 钉了什么 / 没钉什么
- [x] 列出 MYSQL_FIDELITY vs 浏览器，禁止 TestClient 顶
- [x] 未写 `04-verify/coverage.md`，未写 `backend/tests` 新用例，未代选剩余 Qs
- [x] 空心断言当缺陷，不当覆盖
