# 技术方案 · 四柱收口 + 不好用（feat-product-complete）

> 上游：`01-define/spec.md` **v1.5** + `user-story.md` v1.5 + `metrics-blueprint.md` v1.4 + `05-review/findings-shape-r1.md`（QA-01…QA-10）+ define r3/r6 携带（QA-20…24、QA-40）
> 特征：`feat-product-complete`｜泳道：L4｜appetite：程序 **15–21 人周**（Wave C 6–10 · Wave U 4–7 · Wave A 5–8，重叠禁止加总；**停判线 >21 不抬高**）
> 作者：/architect｜日期：2026-09-11｜版本：**v2**（shape r1 扩展：并入 Wave A，消化 QA-01…QA-10）
> 冻结施工集（**28 FR，>20，本 spawn 只写票表**——票文件归下一 spawn）：Wave C **50, 51, 60, 61, 87**；Wave U **80, 81, 82, 83, 84, 85, 88, 89, 90, 92**；Wave A **93…105**。**不含 FR-91。**
> **扩不是重写：** v1 结构与 T-01…T-23 编号**保持不变**；Wave A 新票从 **T-24** 顺延。018c369 已有 billing/relay 骨架 + Alembic 040；v2 T-01…T-33 不开票。
> **禁止：** 代选 Q-VOICE / Q-PRICE / Q-MARKET-USER / Q-AGPL / Q-OPS-COLLECT / **Q-C-REG**；把四柱标 GA；把 LiteLLM 焊进根 compose；把 `test_billing_relay.py` 四测勾成 FR-50/60 完成；把 `sk-` 验收成 FR-51；本 spawn 写 `tickets/*.md` / 产品代码 / db-spec / edge-states。
> 合主干 / alembic 040 **是交付清单，不是用户故事、不开 FR 票。**

下游：`/dba`（§7、§8 含 Wave A 实体）· `/designer`（可见差，不重排五组）· `/sre`（网关仍独立 compose）· 实现角色（下一 spawn 票文件）· `/qa`（GWT + QA-20…24 注记 + Wave A 抽检）。

---

## 0. 合同声明

这是 **全新 closeout+UX 方案**，不是 v2 contract 补丁。v2 ADR-0010…0018 仍约束已兑面（拓扑、数据面、事件、上架）。本特征 **新增** [ADR-0019](adr-0019-relay-token-litellm-http.md)、[ADR-0020](adr-0020-outbound-key-vs-relay-token.md)、[ADR-0021](adr-0021-menu-single-source.md)；v2 增补 [ADR-0022](adr-0022-admin-single-layout-tree.md)（Wave A 布局）、[ADR-0023](adr-0023-asset-import-sandbox.md)（Wave A 导入）。**ADR-0021 与 FR-95 的和解（QA-02）与 ADR-0019 的 Then 收敛（QA-04）已分别写回两份 ADR。**

出现任一句 = 本合同不合格：

- 四柱 GA / 再选一次 Q-RELAY / 再换网关
- 根 compose 声明 litellm 服务；backend 持 `LITELLM.DB_DSN`
- 在线支付能产生任何单；用户可见 `PAYMENT_NOT_CONFIGURED` / `QUOTA_EXCEEDED` / 裸 `429` / `FORBIDDEN`（只读改套餐）
- 官网「当前可买」或「当前可买中转」；把官网动词改成「提交升级申请」写成已选解法；确认收款 Then = 配额变成专业档三数字
- 出站拉数钥匙 = 渠道组 `sk-`；签发成功但网关不认（本地假成功）
- GET `/relay/groups` 读路径建组导致空态永不到
- 侧栏继续 DB 树优先、静态树回退
- 公开商店仍出现 `nfr01qc2-*` /「NFR卡片」/ `preprod nfr-01 seed`；为翻页再造 21 张商品
- FR-91 进票；代选货架或安装
- 一张「实现四柱 / 实现 Wave C / 实现 Wave A」巨票
- **（Wave A，QA-40）** 票表或本文出现「demo/内部项来源分组展示形态」交付物——那是幽灵项，**不建设**；GWT-104.2（无独立入口）是 FR-104 唯一 Then
- 平台租户身份被写成给超管开企业产品空间（GWT-82.4 语义改变）；恢复软删用户写成物理删除或覆盖现有用户；布局重构顺带改菜单真相（ADR-0021 语义漂移）

**FR-50 完成线（QA-24 / PC-3）：** 停在「我的订单能看见已确认」。确认后用量三数字 **不是** 本 FR 完成条件。

---

## 1. 现状测绘（改造类）

**现有边界（2026-09-11 读码）：** 单进程 FastAPI `:9111` + Scrapy Worker + admin `:9112` + official `:9113`。LiteLLM 独立 `deploy/litellm`（ADR-0010/0014）。018c369：**`/api/v1/billing/*` 线下挂账 + 超管确认会 `_apply_plan`；`/api/v1/relay/*` 组/令牌 CRUD，签发本地 `sk-`，不进网关，`used_tokens` 无写点；`GET /groups` 空则 `_ensure_default`。** 出站拉数仍 `KEY_BINDINGS`，无租户签发。公开市场 API `total=400` 种子、`PAGE_SIZE_MAX=50`、官网无翻页控件。`AdminLayout` 动态菜单优先。登录 `authenticate` 只 `get_by_username`。入队超限 JSON `code=QUOTA_EXCEEDED` HTTP 429。设置 toast「官网内容已实时同步更新」。成员页只读仍见「添加成员」。

**Wave A 现状（2026-09-11 读码，spec §1.5 F1–F13 对照）：**

- `frontend/admin/src/App.tsx` L59–68 `PlatformAdminLayout` 为 `/newapi` `/platform-ops` `/users` **单独再挂一份 `AdminLayout`**（L78–83），主树另挂一份（L85 起）——跨组切换整树卸载重挂、闪「权限加载中」的根因（FR-96）。
- `frontend/admin/src/pages/LlmProviders.tsx` L163–174 列「激活」列 + `已激活/未激活` 开关 + `已激活「name」` toast（FR-97 仅文案与呈现错位）。
- `frontend/admin/src/pages/NewApiOps.tsx` L240–241 三 tab（总览/探针/事件）数据面真，tab 在页内、页头有标题卡（FR-98）。
- `backend/services/skill_import_service.py` 仅 `import_url`（URL/raw/zip/GitHub 子目录），**无本地上传通道**；`_safe_member_path` L60 已有路径安全原语可复用；agents 无任何通道（FR-100）。
- `backend/services/expert_service.py` L80–195 成员引用域仅 `asset_type='expert'`（FR-101 扩 agent）。
- `backend/app/api/deps.py` L127 `task_actor_tenant_id → int|None`，平台超管为 None；`backend/services/spider_common.py` L38 `NO_TENANT_ENQUEUE_MESSAGE = "没有企业身份，无法入队"`（FR-102）。
- `backend/services/alert_service.py` L89–90 **显式跳过 `queue_depth` 规则**；`backend/services/schedule_service.py` L302–311 `_check_queue_depth` 只读配置 `SCHEDULER.QUEUE_DEPTH_WARN` 写 `logger.warning`，不读规则表、不通知（FR-105 死规则）。`platform_core/models/alert_rule.py` L8–15 AlertRule 为 TenantMixin，`rule_type` 枚举已含 queue_depth。
- `backend/services/user_service.py` L223–247 删除仅防「删自己/删最后一个平台超管」——**存在第二个超管时种子 admin 可删**（FR-94）；L81/86/171 列表滤 `deleted_at IS NULL` 但**无「已删除」筛选、无恢复端点**；`platform_core/models/user.py` L22 `uq_users_tenant_username` + L27 email 全局 unique **均含软删行**（FR-93 占用冲突，QA-03）。
- `frontend/admin/src/pages/EnterpriseManagement.tsx` 仅新建公司/部门 + 列表 + 状态 Tag，无改名/停用/启用动作；运营台停用游离在外（FR-95）。`platform_core/models/tenant.py` slug 唯一、status active/expired/disabled、软删 Mixin，无平台租户保护钩子。
- `backend/services/spider_registry_service.py` L120–145 扫 `scrapy/spiders/*.py` 文件清单进列表（demo/收割器/flow 伪爬虫/源码混入，FR-104）；方案编辑面仅 title/description（FR-103，spec F13a file:line）。

**约束：**

| 约束 | 来源 | 影响 |
|---|---|---|
| 017 业务表 `tenant_id` NOT NULL | PIT-4 | 出站钥匙行必须有企业，禁止 NULL=平台 |
| `require_admin` ≠ 超管 | PIT-2 | 组织幽灵页 `requireAdmin` 放行租户公司管理员 |
| 新平台表必须豁免；租户表禁止豁免 | PIT-3 | 出站钥匙 TenantMixin 禁豁免；`plans` 已豁免 |
| 双公开闸 | PIT-5 | 种子过滤必须同时改 skills + capabilities 公开端与两份测试 |
| 静态段注册顺序 | PIT-1 | 出站/订单新静态路由放动态段前 |
| 改守卫同 PR 改测试 | PIT-2 | 只读找管理员 ≠ 403 金标不改 |
| 在线支付空 | Q-BILL | `UnconfiguredOnlineProvider` 保持；不产生单 |
| 不焊根编排 | ADR-0010 | 令牌打网关仍 HTTP 独立 compose |
| 公开 ≤400 P95<2s；页大小≤20 | NFR-01/02 | 查询侧闸；`PAGE_SIZE_MAX` 公开端收到 20 |

**本次不动：**

- Scrapy 管道、Redis 协议、出数环整段（FR-18/19 词已兑；本波只补「去节点」+ 拦住提交）
- 不重开 FR-01…20 / 30…45 / 70…75；不重排五组；不修幽灵成超管功能
- 不代选 Q-PRICE 三项（官网动词、确认后履约三数字、撤 ¥299）
- 不打开 `LLM.ENABLED` / 填上游 key；不把四柱标 GA
- 不实现在线扣款、发票、取消、退款
- 不把平台共享 `/spider/status|results|stats` 改成租户功能
- 不做设置→Hero 真同步；FR-90 只禁说谎
- 不施工 FR-91
- **（Wave A）** 不重排五组（Wave A 增强都在系统管理组既有叶）；不开 C 端个人注册（Q-C-REG）；不开常规企业删除；导入资产不自动上架；不做专家团执行引擎；不重做探针引擎/LLM 选路数据面；不建「demo/内部项来源分组展示形态」（QA-40 幽灵项）

**已知技术债（碰到要小心，不在本轮当用户故事）：**

| 位置 | 债 | 本次 |
|---|---|---|
| alembic 039 vs 040；合主干 | 环境漂移 | **交付清单**，不开 FR 票 |
| `confirm_paid` 已 `_apply_plan` | 骨架副作用，像代选 Q-PRICE | **不**当 FR-50 Then；**不**新开票去实现或删除履约 |
| IM-* 测试/文档债 | qa 账本 | 转 /qa，不升 FR |
| CONTEXT「令牌不发给租户」 | 过期 | 交付改词汇；产品名以 spec §0.4 |

---

## 2. 模块边界

### 2.1 能力聚类

| FR | 能力拆解 | 归属模块 |
|---|---|---|
| 50 | 线下申请、我的订单、超管确认、一套真相文案、只读找管理员 | **账务出口**（扩）+ 官网/用量壳 |
| 51 | 自助签发出站钥匙、拉本企业行、与中转互否 | **出站拉数钥匙**（新建域，扩 external_api 查找） |
| 60 | Base URL/用法、令牌打网关、用量走、空态、熔断仍拒 | **租户渠道组**（扩）+ 网关适配叶 Key HTTP |
| 61 | 值班看见伪装；空态不第三套 | **值班编排**（扩可见性验收，不换数据面） |
| 87 | 入队信封用户可见禁内码 | **SaaS 配额**（扩入队映射） |
| 80 81 | 公开列表去种子、页大小≤20、夹具第 21 张 | **Power Market 读模型**（扩查询闸） |
| 82 | 侧栏单一真相、组织页 404 同形 | **Admin 壳 / 目录** |
| 83 | 注册邮箱能登录 | **SaaS 鉴权** |
| 84 | 失败≠空（点名屏） | **Admin 壳**（各页同一 Then） |
| 85 | 无工人去节点 + 提交拦住 | **采集编排壳**（不重开出数环） |
| 88 | 技能/插件同步收回；目录不含已删行 | **Power Market 治理** |
| 89 | 只读成员页无写控件 | **成员页壳** |
| 90 | 设置不谎称同步官网 | **设置页壳** |
| 92 | 五件新事件进已有产品事实；失败不挡 | **产品事件叶**（扩事件名，不改 WACT） |
| 93 | 已删筛选、恢复、占用判定与释放 | **用户生命周期**（扩 user_service；平台页） |
| 94 95 | 种子 admin 不可删；平台租户三名保护；企业改名/停用/再启用；默认归属显式化 | **企业管理壳**（tenant 写单点收口，与运营台同一真相） |
| 96 | 单布局树；切换不重挂不闪 | **Admin 壳**（ADR-0022） |
| 97 | 「激活」→「默认」文案与呈现 | **LLM 配置页壳**（纯前端，不动选路） |
| 98 | 三 tab 上提；三问驾驶舱；立即探测；事件跳转 | **中转站呈现**（NewApiOps 呈现层；引擎复用） |
| 99 | 页头冗余移除与规范推广 | **Admin 壳**（designer 输入） |
| 100 | 本地文件/目录四类一键导入 | **能力资产导入**（新建域，沙箱收容；ADR-0023） |
| 101 | 专家团成员域扩 agent | **专家团**（扩成员域） |
| 102 | 平台超管以平台租户身份入队 | **SaaS 鉴权/配额**（扩 actor 解析） |
| 103 104 | 方案定义可编辑可删；视图纯净 | **采集编排壳**（templates 编辑 + registry 分流） |
| 105 | queue_depth 接成活规则 | **告警调度**（alert_service × schedule_service 接线） |

**FR 归属核对：** 28 条均有归属（C 5 + U 10 + A 13）；FR-91 故意无票。

### 2.2 模块清单

| 模块 | 一句话职责 | 独占 | 重写谁碎 | 新建/既有 |
|---|---|---|---|---|
| 账务出口 | 把线下升级申请挂到本企业并让超管确认收款 | plans/orders/subscriptions 写；确认不可逆 | 满额下一步、PC-3 | **既有，扩** |
| 出站拉数钥匙 | 签发只拉本企业结果的钥匙 | 出站凭证行 + `bound_tenant_id` 查找 | 外部拉数、FR-13 | **新建域** |
| 租户渠道组 | 组/令牌库存与页上用法 | relay_groups/tokens 写 | 中转履约、PC-4 | **既有，扩** |
| 网关适配叶 | HTTP 打独立 LiteLLM（chat + **Key 管理**） | 不持 DSN、不持上游 Key | 60.3 打通 | 既有 `llm_gateway/`，**扩 admin Key** |
| SaaS 鉴权/配额 | 谁能写、邮箱登录、入队满额句 | tenants/users/quota | 登录、87 | 既有，扩 |
| Power Market 读/治理 | 公开出现谓词 + 收回 | listing/目录 | 商店诚实、88 | 既有，扩查询闸 |
| 产品事件叶 | 追加事实，失败不挡 | product_events | 四周判定 | 既有，追加事件名 |
| Admin/官网壳 | 渲染；直打同形；失败≠空 | 无业务表 | 履约裂缝 | 既有 |
| 值班编排 | 超管看见伪装；空态两句 | 本库 probe 行 | 61 | 既有，验收可见性 |
| 用户生命周期 | 平台超管筛已删、恢复、占用释放 | users 行写（软删/恢复判定） | 登录、93 | 既有，扩 |
| 企业管理壳 | 企业改名/停用/启用 + 平台租户与 admin 保护 | tenants 行写（单点，两读） | 94 95 | 既有，扩 |
| 能力资产导入 | 本地文件/目录 → 沙箱 → 四类目录行（未上架） | 导入批次与沙箱目录 | 100 | **新建域** |
| 中转站呈现 | 三问驾驶舱/手动探测/事件跳转 | 无新表（读 channel_events/probe） | 98 | 既有，扩呈现 |
| 专家团 | 成员域 expert∪agent（组长仍 expert） | expert_team 成员引用 | 101 | 既有，扩 |
| 告警调度 | queue_depth 规则真实评估+通知+静默 | AlertRule 读 + 命中记录写 | 105 | 既有，接线 |

工人仍不是业务模块。账务 **不** 调网关。出站钥匙 **不** 调 `llm_gateway`。渠道组 **不** 写出站凭证表。Power Market **仍禁** import `relay_*` / `llm_gateway`（B4）。

### 2.3 依赖图

```
官网定价 / Admin 用量·订单·渠道组·出站钥匙·侧栏
        │
        ▼
编排 API（不 import ORM，R7）
        │
        ├──► 【SaaS 鉴权/配额】──► 主库
        ├──► 【账务出口】──► 主库 orders/plans
        │         └──► 【产品事件】（叶子）
        ├──► 【出站拉数钥匙】──► 主库凭证
        │         └──► external_api 拉数（只本企业非候选）
        ├──► 【租户渠道组】──► 主库 relay_*
        │         └──► 【网关适配叶 admin Key + 租户直打 chat】──► LiteLLM
        │                   └──► 【产品事件】relay_token_call_succeeded
        ├──► 【Power Market】──► 主库目录（公开去种子 + 收回）
        │         └──► 【产品事件】market_list_paged
        └──► 【值班编排】──► 网关适配叶（管理 HTTP，已有）
```

**无环确认：** ☑ 已检查。出站与渠道组互不 import；互否靠「查找集合不相交」而不是 `if 来源==relay`。Wave A 追加边（均单向）：`用户生命周期`/`企业管理壳` ──► 主库 users/tenants；`能力资产导入` ──► capability 目录行（**禁** import relay/llm_gateway，B4 同口径）+ 产品事件叶；`中转站呈现` ──► 只读 channel_events/probe（复用探针引擎，不写规则）；`专家团` ──► capability 目录读（asset_type 扩 agent）；`告警调度` ──► 读 AlertRule + notify_service（不反向被 alert_service 调度路径 import）；`SaaS 鉴权/配额`（FR-102）只改 actor→tenant 解析，不新增边。无新增环。

**边界强制：** B1–B4 保持。本特征追加 grep 纪律（挂 lint，实现票落地）：

```
# 出站域禁 import relay / llm_gateway
grep -rnE 'backend\.services\.relay|llm_gateway' backend/services/outbound_keys/ backend/app/api/v1/outbound*.py 2>/dev/null || true

# 渠道组禁把出站凭证当令牌
grep -rnE 'outbound_key|KEY_BINDINGS' backend/services/relay_service.py

# 仍禁 DSN
grep -rnE 'LITELLM\.DB_DSN' backend/ --glob '*.py'
```

### 2.4 耦合检查

| 检查项 | 结果 |
|---|---|
| 两模块共享表且都写 | 无。orders 仅账务写；relay_tokens 仅渠道组写；出站凭证仅出站域写。Wave A：tenants 仅企业管理壳写（运营台读/经同服务）；users 软删/恢复仅用户生命周期写；导入批次仅导入域写；AlertRule 行仍归告警规则既有写路径，调度器只读 + 命中记录 |
| 模块含其它模块知识 | 禁止账务 `if channel==relay`；禁止市场 import relay；公开种子过滤是读模型谓词，不是「if 测试租户」散落。Wave A：导入域不知道 relay；中转站呈现不写熔断规则；平台租户身份只在 actor 解析点出现一次（deps），不得散落 `if slug==platform` |
| 强制手段 | B4 + 上节 grep；目录约定 `outbound` 不进 `relay_service.py`。Wave A 追加：导入域同口径 grep（禁 import relay/llm_gateway）；`slug=='platform'` 字面量只许出现在 actor 解析与蓝图排除口径处 |

---

## 3. C4（到组件，不到类）

### Context

```
访客 ──► 官网（逛已上架无种子、翻页、注册、定价不得当前可买/可买中转）
租户经办 ──► 后台（采集、出站拉数钥匙、看渠道组用法）
租户负责人 ──► 后台（下线申请、签发渠道组令牌、成员）
平台超管 ──► 后台（确认收款、七叶、值班看伪装、产品事实）
外部系统 ──X-API-Key──► 出站拉数（只本企业）
租户 LLM 客户端 ──sk- + Base URL──► LiteLLM Proxy（独立故障域）──► 上游
```

责任：本系统拥有租户隔离、账务骨架、钥匙分平面、商店公开闸、菜单 IA。LiteLLM 拥有虚拟 Key 与平台上游。Worker 拥有抓取。

### Container

```
[frontend/official]  [frontend/admin]
         \              /
          [FastAPI backend :9111]
          /     |      |      \
    [MySQL 主库] [Redis] [Scrapy Worker]
                           |
                    [LiteLLM compose]  ← 不进根编排
                    litellm + Postgres
```

切分理由：与 ADR-0010 相同。本特征 **不** 把 Key 登记改成连网关 PG。

### Component

即 §2.2。不画类图。

---

## 4. 可行性验证

本方案未引入未验证协议。无新付费依赖。未跑 LiteLLM `/key/generate` 容器 spike（交 T-08 只读 OpenAPI；失败则签发失败可见，不回退 DSN，不本地假成功）。Wave A 无新外部依赖（导入走本地上传，不新增第三方）。

| 假设 | 怎么验证 | 结论 |
|---|---|---|
| billing 骨架可扩 | 读 `billing_service.py` / `040` / `test_billing_relay.py` | **成立**；缺：单 pending、我的订单空态、只读找管理员句、金额元、事件、在线码可见 |
| confirm 已写配额 | `_apply_plan` L108–136 | **现网成立**；**不得**当 FR-50 Then（Q-PRICE） |
| relay 令牌进网关 | `issue_token` 只 sha256；admin.py 无 /key | **不成立** → ADR-0019 |
| GET groups 建 default | `list_groups` L62–64 | **现网成立（有害）** → T-07 去掉读路径写库 |
| 出站自助 | 无 api_keys 路由；KEY_BINDINGS | **不成立** → ADR-0020 新建域 |
| 登录邮箱 | `authenticate` 只 username；signup username=local-part | **不成立** → T-16 |
| 公开翻页 | API 有 page/has_more；官网无 Pagination；MAX=50 | **半成立** → T-13/T-14 |
| 菜单双源 | AdminLayout 动态优先 | **现网成立（有害）** → ADR-0021 |
| 入队内码 | QuotaExceededException code+429 | **现网成立（有害）** → T-12 |
| 值班伪装字样 | VERDICT_TAG spoofed=「伪装」 | **词在**；缺 GWT-61.1 夹具 |
| 页大小≤20 | PAGE_SIZE_DEFAULT=20 MAX=50 | 公开端必须把 MAX 收到 20 |
| 软删行已在、缺筛/恢复 | user_service L81/86/171 滤已删；L247 软删 | **成立**；缺「已删除」筛选参数、恢复端点、占用/释放语义（QA-03 → §8） |
| 唯一键含软删行 | user.py L22 `uq_users_tenant_username` + L27 email 全局 unique | **现网成立（有害）** → §8 给 dba（在册行口径） |
| admin 种子可删 | delete_user L223–247 仅「自己/最后超管」两守卫 | **成立** → T-26 加种子守卫 |
| 平台页双挂载 | App.tsx L59–83 双 `AdminLayout` 分支 | **成立（有害）** → ADR-0022 / T-29 |
| 激活仅文案 | LlmProviders L163–174；后端租户域互斥默认已在 | **成立** → T-30 纯前端 |
| 三 tab 数据真 | NewApiOps L240–241 + probe/channel_events 读路径 | **成立** → T-31/32/33 呈现与手动探测 |
| 导入无上传通道 | skill_import_service 仅 `import_url`；`_safe_member_path` L60 路径安全原语在 | **不成立** → ADR-0023 / T-35 新建上传+沙箱 |
| 成员域仅 expert | expert_service L80–195 `asset_type='expert'` | **成立可扩** → T-37 |
| 平台入队被拒 | deps.py L127 返回 None → spider_common L38 拒绝句 | **成立** → T-38 改解析 |
| 方案仅元信息可编 | templates.py update 面窄（spec F13a file:line） | **成立** → T-39 扩定义字段 |
| 混入源码清单 | spider_registry_service L120–145 扫 `scrapy/spiders/*.py` | **成立（有害）** → T-41 分流 |
| queue_depth 死规则 | alert_service L89–90 跳过；schedule L302–311 只读配置 | **现网成立（有害）** → T-42 接线 |
| 企业页仅新建+列表 | EnterpriseManagement.tsx；tenant.py 无保护钩子 | **成立** → T-26/27/28 |

**无未验证新技术。** 性能：公开列表去种子后体量下降；P95 闸仍查询侧。

---

## 5. 关键决策

| 决策 | 结论 | ADR |
|---|---|---|
| 拓扑 / 不焊根编排 | 沿用 | 0010（不新写） |
| 令牌打网关 | LiteLLM 虚拟 Key + 租户直打 chat；禁 DSN；禁本地假成功 | [0019](adr-0019-relay-token-litellm-http.md) |
| 三钥匙分平面 | 出站新域 ≠ relay_tokens ≠ master | [0020](adr-0020-outbound-key-vs-relay-token.md) |
| 菜单 | menuConfig + 权限过滤为侧栏唯一输入 | [0021](adr-0021-menu-single-source.md)（v2 已与 FR-95 和解，QA-02） |
| Admin 布局 | 单布局树；平台页并入主路由树，页级守卫；切换不重挂 | [0022](adr-0022-admin-single-layout-tree.md) |
| 资产导入 | 统一上传通道 + 沙箱解包 + 四类分发 + 部分成功/幂等 | [0023](adr-0023-asset-import-sandbox.md) |
| 平台租户身份 | 超管 actor→平台租户，仅在入队/方案归属点解析；不绕配额 | spec v1.5 已钉（GWT-82.4×102）；不单开 ADR |
| queue_depth 接通 | 调度器读 AlertRule 真实评估+通知+静默窗 | Q-QUEUE-DEPTH 已决；可逆接线，不单开 ADR |
| 60.3 Then 口径 | 以 spec GWT-60.2/60.3 为唯一 Then；ADR-0019 已收敛 | QA-04（ADR-0019 v2 修订） |
| 60.3 夹具口径 | 必须网关认证 chat 真实响应；裸 200 不算 | QA-05（§7.4） |
| list_tokens 读模型 | 列表读本地缓存；禁止每行打网关 | QA-08（§7.4） |
| 只读出站页 Then | 钉「控件隐藏 + 找管理员句」一支 | QA-09（§7.3） |
| 在线支付 | 保持空；不产生任何单 | Q-BILL；无需新 ADR |
| 确认后配额 | 骨架可写库；**不是** FR-50 完成条件 | 不代选 Q-PRICE |
| 公开分页 | 查询侧去种子后再 OFFSET；页大小≤20 | 可逆；不单开 ADR |
| 产品事件 | 仍 OLTP 追加；仅超管查询 | 0016 |
| Q-VOICE 等五问 | **不代选** | spec §9.1 |

---

## 6. 波次与并行

```
Wave C ∥ Wave U（同一屏 Then 以 spec 为准，不得互否）
P0 无依赖：T-01 04 07 08 11 12 13 15 16 17 18 19 20 21 23
P1：T-02←01；T-03←01；T-05/06←04；T-09←08；T-10←07+08；T-14←13
P2：T-22←02+05+09+14（事件查询面与 fail-open）

Wave A（可与 C/U 并行；采集任务屏 FR-85/87 与 FR-103…105 同屏不同动作，各自 Then 不互否）
P0 无依赖：T-24 26 27 29 30 31 35 37 38 39 41 42
P1：T-25←24；T-28←27；T-32←31；T-33←31；T-36←35；T-40←39
同文件串行（不要同会话并行）：
  T-24×T-26（都动 user_service.py）
  T-31→T-32→T-33（都动 NewApiOps.tsx，同作者连续或串行）
  T-29×T-34（布局树 × 点名六页页头，先 T-29 定树再 T-34 铺页）
  T-30 并入 T-34 时注意 LlmProviders.tsx 只动一次（文案票可先行独立）
  T-26×T-27（user/tenant 保护与 tenant_service 编辑可并行，守卫测试同 PR）
```

超出程序合计（architect 校正后 **>21 人周**）→ 停下重判。v1 粗估 C+U 约 26–38 人日；Wave A 19 票约 **20–24 人日**；三波合计约 **46–62 人日 ≈ 9–12.5 人周**，落在 15–21 内，未触停判线。

---

## 7. 契约要点（本 spawn 不落 `contracts/*.md`）

### 7.1 错误码（`code` 判断，禁止用 `message` 分支）

| code | 何时 | 用户可见 |
|---|---|---|
| `QUOTA_EXCEEDED` | 内部异常类型可留 | **禁止渲染**；入队页「已达配额上限」+「请联系企业管理员」（经办，GWT-87.1 **没有**提交升级申请） |
| `PAYMENT_NOT_CONFIGURED` | 在线通道 | **禁止渲染**；「在线支付尚未开通，请改用线下对公。」；**不产生任何单** |
| `FORBIDDEN` / 裸 `429` | 只读改套餐 / HTTP | **禁止渲染**；「请联系企业管理员」 |
| `ORDER_PENDING_EXISTS` | 已有 pending 再提交 | 「已有待确认的升级申请」 |
| `ORDER_FREE_PLAN` | 对免费档下单 | 中文「免费档无需下单」，无内部码 |
| `AUTH_BAD_CREDENTIALS` | 错密码或未知标识 | 「用户名或密码不正确。核对后再登录。」（邮箱/短名填错 **同句**，GWT-83.2） |
| `AUTH_TENANT_EXPIRED` | 到期 | 与 83.2 **不同句**（已兑 FR-08） |
| `LLM_GATEWAY_UNREACHABLE` | 60.5 / 已兑 74 | 「平台 LLM 网关不可达」；不是套餐句；用量不显示「已用完」 |
| `ORDER_ROLE_NOT_ALLOWED` | 经办/只读下单（v2.1 追加，implement 已落地） | 用户可见中文句=找管理员句「请联系企业管理员」；code 不渲染（IMPL 终审 a 项追认） |
| `ORDER_ONLINE_UNAVAILABLE` | 在线通道（v2.1 追加，implement 已落地） | 用户可见中文句「在线支付尚未开通，请改用线下对公。」；code 不渲染（IMPL 终审 a 项追认） |
| `TASK_QUOTA_LIMIT_REACHED` | 入队满额（v2.1 追加，implement 已落地） | 用户可见中文句「已达配额上限，请联系企业管理员。」；code 不渲染（IMPL 终审 a 项追认） |
| `TASK_RUN_ROLE_NOT_ALLOWED` | 只读提交采集（v2.1 追加，implement 已落地） | 用户可见中文句=找管理员句；code 不渲染（IMPL 终审 a 项追认） |
| `RELAY_TOKEN_ROLE_NOT_ALLOWED` | 经办签发渠道组令牌（v2.1 追加，implement 已落地） | 用户可见中文句=找管理员句；code 不渲染（IMPL 终审 a 项追认） |
| `RELAY_GROUP_ROLE_NOT_ALLOWED` | 经办建组（v2.1 追加，implement 已落地） | 用户可见中文句=找管理员句；code 不渲染（IMPL 终审 a 项追认） |
| `OUTBOUND_KEY_ROLE_NOT_ALLOWED` | 只读写出站钥匙（v2.1 追加，implement 已落地） | 用户可见中文句=找管理员句（QA-09 同构）；code 不渲染（IMPL 终审 a 项追认） |
| `RELAY_GATEWAY_UNAVAILABLE` | 渠道组网关不可达（v2.1 追加，implement 已落地） | 用户可见中文句=网关不可达句族（与 60.5/61.2/98.6 已冻句同族，非套餐超限句）；code 不渲染（IMPL 终审 a 项追认） |

HTTP：业务拒绝用稳定 code。租户直打平台专属 / 组织幽灵 = **真 404 同形**。值班远端不可达 = 200 + 已冻 71.3，不 500。

### 7.2 账务（扩 018c369）

- `POST /billing/orders`：仅负责人/公司管理员；channel=offline 才可能产生 pending；alipay/wechat **零新行**（含不产生 pending）。
- 公开价目仅 free/pro；企业档 **不得**同一申请动作（GWT-50.14）。
- 已有 pending → 不产生第二张（GWT-50.15）。夹具两张 pending 都确认 → 两张 paid、配额不叠档（GWT-50.16）；**不**验收履约三数字。
- `GET /billing/orders`：本企业单；金额用户可见为 **元**（与定价页同一数字，不必心算分）。空态句「还没有升级申请。」
- 超管确认不可逆；租户确认拒绝、仍 pending。
- **FR-50 Then 不包含** `tenants.quota` 变为专业档。现网 `_apply_plan` 视为骨架副作用：实现票不得把它写成 GWT-50.10 通过条件，也不得单开票删除它来「代选不履约」。
- **GWT-50.13（QA-23）：** Given **该企业套餐已是专业档夹具**（不是靠本波确认履约），对照定价页与用量执法三数字同一套。
- 事件：`offline_order_submitted` / `offline_order_confirmed`（无明文、无支付通道密钥）。

### 7.3 出站拉数钥匙（新域）

- 经办/负责人签发与吊销；只读无控件。明文一次；再进页只见前缀/状态。
- **GWT-51.5/51.9（QA-09，钉一支）：** 只读打开本入口 = **无签发/吊销控件 + 页上「请联系企业管理员」说明句**（控件隐藏支，与 FR-89 / GWT-60.7 同构）。「点了说明找管理员」支不施工、不验收。
- 拉数：已兑路径，绑定本企业，`source <> marketplace`。未绑定/revoked/他企业/渠道组 `sk-` → 拒绝、0 行。
- 出站钥匙打页上 Base URL → 拒绝；不是套餐超限；渠道组用量相对基线不变（GWT-51.10）。
- 事件：`outbound_key_issued` 含 `tenant_id`，**不含明文**。

### 7.4 渠道组（扩 018c369 + ADR-0019）

- **禁止** `list_groups` 读路径 `_ensure_default`。无令牌空态必须走得到（GWT-60.4）。默认组若产品需要，只允许 **显式写**（负责人建组），不得因 viewer GET 落库。
- 签发：LiteLLM Key HTTP；失败则签发失败。页上 Base URL + 三步用法。不得把出站拉数地址写成 Base URL。不得出现 master。
- **GWT-60.3（QA-21 + QA-05 夹具口径）：** Given **夹具网关可达**。Then 同时：不是无效平台钥匙、不是套餐超限、用量 0→≥1。闸关/上游空/网关不可达 **不得**勾 60.3，走 60.5。**夹具必须用签发令牌对 Base URL 的 chat 路径（`/v1/chat/completions`）发起真实请求，且网关认证通过（非 401/403）并返回真实响应体**；对任意端点的裸 httpx 200（如 `/health`）不算 60.3 通过（QA-05 空心勾封死）。
- **QA-20：** 吊销后再对 Base URL 发请求 → 拒绝；不是 60.3 成功。不新开 FR。
- 经办：能看不能签；缺写权句，不是空表。跨企业 404 同形。A 调用不动 B（60.10）。
- 官网 0 次「当前可买中转」。**不**验收官网句 vs 后台能否管理互否。
- 事件：`relay_token_call_succeeded` 在用量 0→≥1 时，含 `tenant_id`。
- **QA-08 读模型收敛：** `list_tokens` 列表页 **禁止每行打一次网关**（P95 不可承受）。列表读本地 `used_tokens` 缓存列；令牌详情/显式刷新走网关 key info HTTP（单次或按页批量），回填本地列。用户可见的「用量数字」以本地缓存 + 刷新为准，对账用 key info（ADR-0019）。
- **GWT-60.6 写面例外（IMPL-QA-1 裁决注记，v2.1）：** 页面/GET 面 = 404 同形；API 写面（改窗口/冷却/熔断）= 既有 **403**（GWT-70.3 金标钉住，不破）。分裂形态为已裁决口径。

### 7.5 公开商店

- 测试种子定义与 GWT-80.1 同：短名 `nfr01qc2-*`（大小写不敏感）∨ 标题以「NFR卡片」开头 ∨ 描述含 `preprod nfr-01 seed`。列表/精选/total **都不含**。
- 页大小 **≤20**（公开端 `PAGE_SIZE_MAX` 收到 20）。当且仅当非种子 listed>20 时第 21 张可到；≥21 **用夹具资产**，禁止再造商店模型、禁止把种子改成商品。
- listed≤20 无假下一页。0 上架走空态句，不是失败句。
- 事件：`market_list_paged`：`page`、`result_count`、`anonymous_id`；访客无 `tenant_id`。
- PIT-5：`/public/skills` 与 `/public/capabilities` **同一**种子谓词，两份测试同 PR。

### 7.6 登录

- 主字段填 **注册邮箱** + 正确密码 → 进该企业（GWT-83.1）。实现：标识含 `@` 走 email 查找（全局唯一），否则仍 username 消歧。
- 未知标识与错密码 **同句**；到期不同句。
- 注册成功屏写明「登录时请填写注册邮箱」。

### 7.7 产品事件

蓝图事件名原样。至少一次。失败不挡主路径。查询面仅超管；租户直打 404 同形。不含明文钥匙/密码/master。

### 7.8 分页 / 幂等 / 时间

- 公开市场 offset：`page`/`page_size` 默认 20、**最大 20**、返回 `total`（仅 FR-33 可见谓词之后）。
- 下单幂等：业务键「同一企业同一时刻最多一张 pending」；`idempotency_key` 列已在 040，本波开始写入/查重（先查后插不够）。
- 时间 ISO 8601 UTC；报表日上海。

### 7.9 Wave A 契约要点

**用户软删与恢复（FR-93）：**

- 列表：用户管理读模型加状态筛选（`active` 默认 / `deleted`），默认视图行为保持（GWT-93.2）；仅平台超管。
- 恢复：`POST` 恢复端点，仅平台超管；恢复前置占用判定——**username 按同租户在册（`deleted_at IS NULL`）判、email 按全局在册判，任一冲突即拒绝**（GWT-93.4/93.8），可见中文「用户名或邮箱已被现有用户占用」；成功 → 回默认列表、状态=启用、上报 `user_restored`（GWT-92.8）。
- 释放：新建查重口径 = 在册行；已删行不阻塞新 username（同租户）/新 email（全局）（GWT-93.5/93.7 各自独立判定）。**不得**用物理删除已删行实现释放。
- 重复恢复（已启用）= no-op：状态保持启用、不重复上报事件、无新副作用（GWT-93.9）。
- 越权：租户直打用户管理或恢复 = 页面不存在同形（GWT-93.6；FR-82 语义，用户管理是平台页）。**IMPL-QA-3 裁决注记（v2.1）：** `GET /admin/users` 维持 `require_admin` 既有行为（r13 金标；列表限本租户行），GWT-93.6 同形语义由平台页守卫 + 恢复动作面兑现，不改既有 API 鉴权。

**基座保护与企业管理（FR-94/95）：**

- 种子 admin 守卫加在 `delete_user` 单点（与「不能删自己」「最后一个超管」并存、判定在前）；拒绝句「平台初始账号不可删除。」（GWT-94.1）。
- 平台租户三名保护（改名/停用/删除）收口在 tenant 写服务单点——企业管理页与运营台 **同走该服务**，两处读同一真相（GWT-95.1/95.2/95.7 的「同显」由此保证）；「不可删」为前置冻结：本波无删除企业入口（GWT-94.4）。
- 企业改名冲突域：既有企业名 ∪ 保留名「平台租户」∪ 站点名 AutoAgents；冲突拒绝中文说明（GWT-95.1）。
- 平台租户显式化：列表行带「默认归属」标注；「AutoAgents」不出现在任何归属列/企业名（GWT-95.3，§0.4 命名收口）。无归属新用户默认挂平台租户（GWT-95.4，既有规则显式化）。
- 停用/再启用双向，仅常规企业（GWT-95.2/95.7）；列表失败走 FR-84 同句式（GWT-95.5）。
- 越权：租户直打企业编辑/停用 = 页面不存在同形（GWT-94.5/95.6；**/enterprise 对租户的 404 同形语义不变**，ADR-0021 v2 和解）。

**布局与呈现（FR-96/97/98/99）：**

- 单布局树按 [ADR-0022](adr-0022-admin-single-layout-tree.md)：撤 `PlatformAdminLayout` 双挂载，平台页并入主路由树 + 页级守卫（非超管 = NotFound 同形，不进 Unauthorized）；`AdminLayout` 全应用唯一挂载；权限快照在布局生命周期内只加载一次（首次「权限加载中」= GWT-96.3 与 82.2 同句，此后切换不再出现）。GWT-96.4 钉住：菜单真相仍是 ADR-0021（menuConfig + filteredMenus），布局重构不改菜单语义。
- LLM「默认」：仅文案与呈现（`已激活/未激活` → `默认/设为默认` + 说明句「未指定模型时，默认使用该模型，可按需更换」）；同域互斥标记呈现（GWT-97.2）；`is_active` 内部字段名可留；选路数据面不动。
- 中转站三 tab 上提到与欢迎语同一行；内容区直接开始（GWT-98.1 = FR-99 同规范）。总览三问（Q-OVERVIEW-3Q 已决）：网关健康+模型数 / 每渠道最新判定+延迟+24h 事件数+预算窗口用量 / 最近事件 Top N，同屏（GWT-98.2）；问题渠道（spoofed/offline）置顶（GWT-98.3）；事件行点击切「事件」tab（GWT-98.5）。**立即探测** = 对渠道发起一次探测（复用探针引擎），页上可见进行中，完成后判定/延迟更新（GWT-98.4）；越权与副作用边界 = GWT-98.7。网关不可达走已冻空态句，不出现第三套（GWT-98.6 = 61.2 同句）。
- 页头规范（FR-99）：点名六页（LLM 配置、采集任务、AI 方案、系统设置、用户管理 + 中转站管控）；顶栏页名与页内标题不重复；失败句/动作/写控件隐藏不因精简回退（GWT-99.2/99.3/99.4）。横幅中非冗余信息的安置归 designer，不借机删信息也不加新横幅。

**能力资产导入与专家团（FR-100/101）：**

- 导入按 [ADR-0023](adr-0023-asset-import-sandbox.md)：统一上传通道（文件/目录压缩包）→ 服务端沙箱解包 → 四类判定分发 → 目录行（**未上架**）；部分成功为常态语义（逐条成功/失败+中文原因，GWT-100.2/100.3）；超大文件拒绝含上限数字、其余继续（100.5）；路径逃逸条目拒绝且资产目录外零新文件（100.7，NFR-04）；幂等 = 类型+名称不产生第二行（100.8）；一次导入（含部分成功）上报 `asset_imported`（GWT-92.9）。导入不触发资产执行、不自动上架（PC-2 不动）。agents 通道 = 同一通道新类型分支，不另开第二入口。
- 专家团：成员可选域 = 专家 ∪ 智能体（capability 目录 asset_type），成员行标注类型；组长仍从专家选（GWT-101.3）；目录 agent 资产为 0 时空态句仍可仅用专家组建（101.4）；不引入执行引擎。

**平台租户入队（FR-102）：**

- `task_actor_tenant_id` 解析扩展：平台超管 → 平台租户（slug=platform 种子行）；平台租户行缺失 = 配置错误、入队失败可见（**不**静默回退 None/不临时建租户）。普通用户解析不变（GWT-102.4）。
- 配额按平台租户执法，不因超管身份绕过（GWT-102.3，X-QUOTA 同句式满额句）；非超管冒名直打拒绝（102.5）。
- 边界（GWT-82.4 钉住，QA-07）：该身份**仅用于** AI 采集规划入队与方案归属；**不给**超管开渠道组/我的安装等企业产品空间——超管无企业空间打开这些页仍是「用量/安装属于企业空间」说明。
- 平台租户（slug=platform）的任务与事件不计入 WACT / PC-1…PC-4（蓝图 §1 排除，事件消费侧口径，不在入队点过滤）。

**采集方案与告警（FR-103/104/105）：**

- 方案可编辑：向用户呈现的定义字段（入口地址、采集项/参数、调度）可编辑保存并对后续任务生效（GWT-103.1）；标识字段（name、爬虫类型）不可改保持现状；删除被未结束任务引用时拒绝并列出引用任务（103.3）；空态句不把 demo 填回去（103.4）。
- 方案视图纯净：过滤 demo 爬虫 / 能力资产收割器 / flow 伪爬虫 / scrapy 源码文件清单（GWT-104.1）；**GWT-104.2 是 FR-104 唯一「独立入口」Then：本波不保留 demo/内部项独立入口**；不删除爬虫与文件本身；总件不被混入项顶满（104.3）。**QA-40：不建设「demo/内部项来源分组展示形态」——该交付物不得出现在任何票或文本。**
- queue_depth 接通（Q-QUEUE-DEPTH 已决，单支）：调度器周期内读取 AlertRule 的 queue_depth 行 → 真实评估（队列深度超阈值）→ 经规则已配置通知渠道发送 + 静默窗内不重复发送 + 命中记录在规则处可见（GWT-105.1）；通用不变式 GWT-105.3：**可选告警类型中不存在「配了规则却无触发路径」的类型**（不许第三态）；越权 = 105.4。评估深度口径：按规则所属租户的排队任务数（AlertRule 为 TenantMixin）；现 `_check_queue_depth` 读 `SCHEDULER.QUEUE_DEPTH_WARN` 的日志路径**不得**再当评估结果。

---

## 8. 数据语义诉求（给 `/dba`，不写表结构）

```
实体：线下升级申请（已有 orders）
  一行 = 一次申请
  需要：企业、档位、金额、状态 pending|paid、channel、确认时刻
  生命周期：无单→pending→paid（不可逆）；本波无取消
  访问：租户列本企业；超管列 pending
  约束：正常入口同一企业最多一张 pending；在线通道零行；
        夹具两张 pending 都确认不叠档
  金额：库内可继续分；对用户/GWT 是元
  确认写配额：现网副作用；本特征不把它升级成产品完成条件，也不要求迁移去掉

实体：出站拉数钥匙（新）
  一行 = 一把本企业钥匙
  TenantMixin；禁止 TENANT_EXEMPT
  需要：hash、prefix、吊销时刻、签发者
  明文不落库
  查找：拉数先本表后 KEY_BINDINGS；与 relay hash 不相交
  非法：只读签发/吊销；用 relay sk-；跨企业

实体：渠道组令牌（已有，扩）
  需要增加：网关侧稳定字符串引用（expand 加列，禁止一票改类型乱改 key_hash）
  used_tokens：以网关 spend HTTP 为观察点；本地列可缓存
  签发失败不得留下「列表有、网关无」的成功行

实体：套餐价目（已有 plans）
  公开仅 free/pro；企业档本波无 SKU 行
  专业档 quota_json 三数字必须与定价页印的同一套（50.13 夹具企业已在专业档）

实体：产品事实
  追加五件事件名；不改 WACT；不建仓
  新平台表若 tenant_id 恒 NULL 必须登记豁免；本波五件仍走已有 product_events

日历：用量与近 7 日同一套 Asia/Shanghai；存 UTC

实体：用户（已有 users，扩软删语义 —— QA-03 给 /dba）
  现状：uq_users_tenant_username(tenant_id,username) + email 全局 unique，均含软删行 → 死占用
  诉求：username 唯一只对在册（deleted_at IS NULL）生效（同租户）；email 全局同口径
  恢复：前置占用判定（username 同租户在册 / email 全局在册，任一冲突拒绝，GWT-93.4/93.8）
        判定与恢复写入须同事务，防「判定通过→并发新建→恢复覆盖」竞态
  释放：新建/查重口径 = 在册行；已删行不阻塞（GWT-93.5/93.7，username/email 各自独立）
  机制（部分唯一索引 / 事务内应用层判重+锁）由 /dba 定；
        禁止用「物理删除已删行」或「改 email 为 NULL+时间戳」当解法（审计链断裂）
  恢复动作仅平台超管；重复恢复 no-op、不重复事件（GWT-93.9）

实体：租户（已有 tenants，扩保护与编辑语义）
  平台租户（slug=platform，种子行）：改名/停用/删除三条迁移非法；保护收口在 tenant 写服务单点
  常规企业：改名（名称唯一域含保留名「平台租户」与站点名 AutoAgents）、停用⇄启用双向
  企业管理页与运营台：一处写（同服务），两处读同一真相（GWT-95.1/95.2/95.7「同显」）
  本波无删除企业入口；将来落地删除前必须先排除平台租户（GWT-94.4 前置冻结）

实体：导入批次（新，给 /dba 语义）
  一行 = 一次导入（含部分成功）；明细可回放（逐条 成功/失败+原因）
  产物 = capability 目录行（未上架）；不自动上架、不触发执行
  幂等键 = 类型 + 名称（重导不产生第二行，GWT-100.8）
  沙箱 = 临时目录，解析在沙箱内完成；路径规范化后越界条目拒绝（GWT-100.7）
  上传大小上限来自配置（NFR-10 配置即代码，不硬编码）

实体：告警规则（已有 alert_rules，接线 —— FR-105）
  queue_depth：调度器读规则行真实评估（按规则所属租户的排队任务深度）
  命中记录在规则处可见（谁/何时/深度）；静默窗内重复命中不重复发送
  命中记录仅调度器写；租户只能改本企业规则（105.4）
  废弃语义：SCHEDULER.QUEUE_DEPTH_WARN 日志告警不再是 queue_depth 的评估结果

实体：平台租户身份（FR-102，无新表）
  平台超管 actor → 平台租户（slug=platform 种子行）；解析点单一（task_actor_tenant_id）
  种子行缺失 = 配置错误（fail loud）；配额按平台租户执法
  事件消费侧排除 slug=platform 出 WACT / PC（蓝图 §1），不在写入点过滤
```

破坏性变更必须 expand-contract 分票。Alembic **头修订 040 的环境对齐是交付清单**，不是本表实体。

---

## 9. 角色裁剪声明

| 角色 | 参与 | 理由 |
|---|---|---|
| `/backend` | 是 | 账务扩、出站新域、令牌进网关、种子闸、登录、入队信封、收回 |
| `/frontend` | 是 | 用量/订单/渠道组/出站页、菜单、失败≠空、商店翻页、设置/成员 |
| `/dba` | 是 | 出站实体 + relay 网关引用 expand；不写网关 PG。**v2 追加：** users 在册行唯一语义（QA-03）、租户保护/编辑语义、导入批次实体、queue_depth 规则接线语义 |
| `/designer` | 有限 | 空态/失败句、找管理员；不重排五组；不定新定价策略。**v2 追加（Wave A 可见差）：** 总览三问布局、页头规范（点名六页）、「默认」模型交互、导入 UX（进度/部分成功呈现）、恢复冲突句、企业管理空态/「默认归属」标注 |
| `/qa` | 是 | 全冻结 GWT；QA-20…24 注记；禁止四测当完成。**v2 追加：** Wave A GWT（93.1…93.9 / 95.1…95.7 / 100.1…100.8 / 105.1…105.4）+ 蓝图 §4 Wave A 护栏行；60.3 夹具按 QA-05 口径审 |
| `/sre` | 有限 | 独立 compose 仍在；PUBLIC_BASE_URL；**040/合主干交付清单** |
| `/ops` | 有限 | 不发明电话 |
| `/analyst` | 口径已冻 | 四周后复盘；不进实现票 |
| `/algo` `/miner` `/warehouse` `/data-collector` | **N/A** | state.yaml 已 skip；无评估集/数仓/采集票 |

---

## 10. Rabbit holes

| 坑 | 为什么危险 | 边界 |
|---|---|---|
| 把 `_apply_plan` 写成 50.10 通过 | 代选 Q-PRICE | Then 只「我的订单已确认」（QA-24） |
| 为 50.13 用确认后企业当夹具 | 同一代选 | Given 预先专业档（QA-23） |
| 本地 sk- 201 当 60.3 | 空壳 | ADR-0019；网关 HTTP 失败则签发失败 |
| GET 建 default | 空态永不到 | T-07 |
| sk- 当 FR-51 | X-KEY | ADR-0020 |
| 动态菜单回填当 82 完成 | 双源还在 | ADR-0021 停读 |
| 公开 MAX=50 | 违反 ≤20 | 公开端收到 20 |
| 为翻页 listed 21 张商品 | 重开市场模型 | 夹具资产 |
| 种子只滤一边 | PIT-5 | 双公开端同 PR |
| 出站表漏 TenantMixin / 误豁免 | PIT-3/4 | 与夹具同 PR |
| 改守卫不改 403 金标 | PIT-2 | 找管理员句 + 测试同 PR |
| 60.3 无网关夹具 | QA-21 空心 | Given 网关可达 |
| 90.2 两支 Then | QA-22 | 本票只留一支（见 T-21） |
| FR-91 顺手改落点 | 代选 Q-MARKET-USER | 不进票表 |
| 焊根编排 / DSN | 故障域 | ADR-0010/0014/0019 |
| 打开 LLM.ENABLED 勾 60.3 | spec §5 | 走 60.5 |
| 入队 toast 仍 正在排队 | 85.2 | 拦住且无该 toast |
| **（Wave A）** 建「demo/内部项来源分组展示形态」 | QA-40 幽灵项 | 不建设；GWT-104.2 唯一 Then |
| 借 FR-95 重排五组 / 新开第二企业管理入口 | X-IA；GWT-95 前言 | 增强既有 /enterprise；运营台两读一写 |
| 借 FR-96 改菜单真相 | ADR-0021 漂移 | GWT-96.4 钉住；布局≠菜单 |
| 借 FR-97 重做选路数据面 | 范围爆炸 | 仅文案与呈现；is_active 语义不动 |
| 借 FR-100 自动上架 / 触发执行 | PC-2 污染 | 导入未上架；上架走治理台 |
| 借 FR-102 开企业产品空间 | GWT-82.4 | 仅入队与方案归属 |
| 物理删除已删行解占用 | 审计链断裂 | 在册行口径 + 恢复拒绝（§8） |
| queue_depth 仍读配置不读规则 | 死规则回潮 | GWT-105.3 可失败验收 |
| list_tokens 每行打网关 | QA-08 P95 | 本地缓存 + 显式刷新 |
| 60.3 用裸 httpx 200 夹具 | QA-05 空心勾 | chat 路径真实认证响应 |
| 平台页守卫改「无权限」页 | X-IA 同形 | NotFound 同形保持 |

---

## 11. 任务拆解（票表）

> 本表 T-nn **仅属** `feat-product-complete`。不是 v2 T-01…T-33。
> 一票 = 一会话「实现 + 自测 + 交付」。下一 spawn 才写 `tickets/T-nn.md`。
> 列：id、title、FR、lane（ui\|api）、并行组。附依赖/角色/粗估/验收注记（含 QA-20…24）。
> **禁止**一张「实现四柱」巨票。

粗估：人日。不可加总对 appetite。

### Wave C

| id | title | FR | lane | 并行组 | 依赖 | 角色 | 粗估 | 验收注记 |
|---|---|---|---|---|---|---|---|---|
| T-01 | 扩线下订单写规则：在线零单、单 pending、角色找管理员 | 50 | api | P0 | — | backend | 1–2 | GWT-50.2/5/7/8/14/15。经办/只读不产生单，可见「请联系企业管理员」，不含 `FORBIDDEN`/`QUOTA_EXCEEDED`。在线通道 **不产生任何单**；可见句无 `PAYMENT_NOT_CONFIGURED`。企业档无 SKU 申请。免费档不下单。**禁止**把四测当完成。 |
| T-02 | 扩我的订单读模型 + 超管确认不可逆 + 提交/确认事件 | 50 92 | api | P1 | T-01 | backend | 1–2 | GWT-50.3/4/9/10/11/16；GWT-92.1/92.2。金额 **元**。空态句不是「暂无数据」。确认不可逆。租户确认拒绝仍 pending。**完成线=租户能读到已确认（QA-24/PC-3）**；**Then 不含配额变专业档**。50.16 不叠档。fail-open 见 T-22。 |
| T-03 | 用量/定价一套真相 + 我的订单 UI | 50 | ui | P1 | T-01 | frontend admin+official | 2 | GWT-50.1/6/12/13。满额不到注册；无「没有下一步」否定骨架。购买形「提交升级订单」改为骨架「提交升级申请」（**不**改官网成该动词、**不**撤 ¥299、**不**写当前可买）。**GWT-50.13 Given=该企业已按专业档执法夹具（QA-23）**，不是确认后履约。只读找管理员。listMyOrders 必须渲染。 |
| T-04 | 新建出站拉数钥匙签发/吊销（hash，明文一次） | 51 | api | P0 | — | backend + dba 语义 | 2 | GWT-51.1 签发半格、51.2/5/8/9。产品名「出站拉数钥匙」。只读无签发/吊销。TenantMixin 禁豁免。**不是** relay `sk-`。 |
| T-05 | 出站拉数执法 + 与渠道组互否 + 签发事件 | 51 92 | api | P1 | T-04 | backend | 2 | GWT-51.1 拉到行、51.3/4/6/7/10；GWT-92.3。FR-13 保持。relay 令牌当出站 → 0 行。出站钥匙打 Base URL → 拒绝、非套餐句、用量不变。吊销后再拉 0 行。事件无明文。 |
| T-06 | 出站拉数钥匙页 | 51 | ui | P1 | T-04 | frontend admin | 1 | 空态句；签发/吊销控件按角色；再进页不见明文；入口不得画成渠道组。 |
| T-07 | 渠道组空态可达：禁止 GET 建组；经办只读 | 60 | api | P0 | — | backend | 1 | GWT-60.4/60.7。viewer GET **不得** insert default。经办无签发控件 API。作废「GET 必有 data[0]」金标。 |
| T-08 | 签发/吊销登记独立 LiteLLM 虚拟 Key（HTTP，禁 DSN） | 60 | api | P0 | — | backend | 2–3 | ADR-0019。OpenAPI 核对 `/key/generate` 等价路径。失败=签发失败，**禁止本地假成功**。明文一次。gateway 引用 expand 列等 /dba。lint 零 `LITELLM.DB_DSN`。 |
| T-09 | 令牌打网关用量走；吊销后再打拒绝 | 60 92 | api | P1 | T-08 | backend | 2–3 | **GWT-60.3 Given 夹具网关可达（QA-21）**；Then 三同时。60.2 用量≥1（只读也能看）。**QA-20：revoked 后再打 Base URL 拒绝**（不新 FR）。60.5 与套餐句分离。60.10 A 不动 B。60.6/8 熔断/跨企业。GWT-92.4 在 0→≥1 时。不得打开 `LLM.ENABLED` 勾 60.3。 |
| T-10 | 渠道组页 Base URL/用法/用量；官网 0 次可买中转 | 60 | ui | P1 | T-07 T-08 | frontend admin+official | 2 | GWT-60.1/2/4/9/11。三步用法。无 master。无出站地址冒充 Base URL。经办找管理员句不是空表。GWT-60.9 **不**验收对外互否。70.4「无我的中转令牌」不得挡住本页产品名「渠道组令牌」。 |
| T-11 | 值班页看得见伪装；空态不第三套 | 61 | ui | P0 | — | frontend admin + 夹具 backend | 0.5–1 | GWT-61.1/2/3。词「伪装」已在 VERDICT_TAG；本票钉 **探针刚判伪装后页上可见** 且渠道不自动关。空态只 71.2/71.3。租户无入口、直打 404 同形。 |
| T-12 | 入队信封用户可见禁配额内码 | 87 | api | P0 | — | backend + admin toast | 1 | GWT-87.1/2/3。经办满额可见「已达配额上限」+「请联系企业管理员」；**没有**提交升级申请。可见处无 `QUOTA_EXCEEDED`、无裸 `429`。只读无提交。同 PR 改入队 429 金标（PIT-2）。 |

### Wave U

| id | title | FR | lane | 并行组 | 依赖 | 角色 | 粗估 | 验收注记 |
|---|---|---|---|---|---|---|---|---|
| T-13 | 公开商店/精选过滤测试种子 | 80 | api | P0 | — | backend | 1 | GWT-80.1…80.4。PIT-5 双公开端+两份测试同 PR。租户不能把种子改成访客可见。夹具 `example-pdf-extractor` 清污染后可搜（对照，不新开模型）。 |
| T-14 | 公开列表页大小≤20 + 夹具第 21 张 + 翻页事件 | 81 92 | ui | P1 | T-13 | official + backend | 1–2 | GWT-81.1…81.4；GWT-92.5。公开 `PAGE_SIZE_MAX=20`。仅当非种子 listed>20 有下一页。≥21 用夹具，不造商品。`market_list_paged` 含 `anonymous_id`。NFR-01 计时交 verify。 |
| T-15 | 侧栏单一真相；组织页 404 同形 | 82 | ui | P0 | — | frontend admin | 2 | ADR-0021。GWT-82.1…82.4。**停用** `/auth/menus` 驱动侧栏。脏 DB 树时仍能找到渠道组/我的安装。直打 `/rbac` `/enterprise` 与 NotFound 同形，不是「抱歉您没有权限」。不重排五组。**不**做 FR-91。 |
| T-16 | 注册邮箱能登录 | 83 | api | P0 | — | backend + official | 1 | GWT-83.1…83.5。主字段填邮箱。未知标识=错密码同句。到期不同句。成功屏「登录时请填写注册邮箱」。进企业 A 不进 B。PC-1 不把短名成功算邮箱已修。 |
| T-17 | 失败≠空：节点/仪表盘/数据/渠道组/LLM | 84 | ui | P0 | — | frontend admin | 2 | GWT-84.1/84.2 点名屏。失败句+重试；禁止「暂无数据/暂无在线节点/还没有采集结果/暂无 LLM 供应商，点击新建」；仪表盘 0 不得冒充没跑过。真 0 走「还没有…」。渠道组无令牌走 60.4。 |
| T-18 | 无工人：去节点 + 新建提交被拦住 | 85 | ui | P0 | — | frontend admin | 1 | GWT-85.1/2/3。打开任务页立即「采集未运行，不会出数」**并且**「去节点」打开节点页。新建提交 **拦住**、任务未入队、**不得** toast「正在排队执行」。**没有**「提交后立即可见」支。只读无提交。不重开出数环。 |
| T-19 | 治理收回技能/插件；目录不含已删行 | 88 | api | P0 | — | backend | 1–2 | GWT-88.1…88.5。与已兑命令收回同构。公开商店无已删行。租户不能改收回。空目录总件不被 gone 行顶满。 |
| T-20 | 只读成员页隐藏写控件 | 89 | ui | P0 | — | frontend admin | 0.5–1 | GWT-89.1…89.3。看不见添加/角色下拉/重置密码/删除；名单仍可见。强提交仍拒。点了再失败不算藏。 |
| T-21 | 设置页不得声称官网已同步 | 90 | ui | P0 | — | frontend admin | 0.5 | GWT-90.1/90.3。保存后无「官网已同步」「官网内容已实时同步更新」；Hero 不变。**GWT-90.2 本票只留一支 Then（QA-22）：经办/只读打开系统设置 →「当前账号不能改系统设置」（设置不是组织幽灵，不用 404 同形）。** 不做真同步。 |
| T-22 | 产品事实：fail-open + 租户无查询面 | 92 | api | P2 | T-02 T-05 T-09 T-14 | backend | 1 | GWT-92.6/92.7。上报失败主路径仍成功。租户打开查询面 404 同形。不改事件名/WACT。PC-3 完成线与 T-02 同（看见已确认，不是任意一条）。 |
| T-23 | 失败≠空：超管待确认收款 + 产品事实 Tab | 84 | ui | P0 | — | frontend admin | 1 | GWT-84.3/84.4。租户打开这两处 404 同形不是空表。超管列表失败 ≠ 默认「暂无数据」。 |

### Wave A（T-24…T-42，2026-09-11 增补；列与 v1 惯例一致）

| id | title | FR | lane | 并行组 | 依赖 | 角色 | 粗估 | 验收注记 |
|---|---|---|---|---|---|---|---|---|
| T-24 | 用户已删筛选 + 恢复端点 + 占用判定/释放语义 + user_restored | 93 92 | api | P0 | — | backend + dba 语义 | 1.5–2 | GWT-93.1…93.9（API 面）；GWT-92.8。默认列表不含已删（93.2 既有保持）。占用判定 username 同租户在册 / email 全局在册，任一冲突拒绝（93.4/93.8）；释放=新建查重在册行（93.5/93.7 各自独立）；重复恢复 no-op 不重复事件（93.9）。判定与写入同事务。**禁止物理删除已删行**。唯一键在册行口径由 /dba 落（§8，QA-03）。 |
| T-25 | 用户管理页「已删除」筛选 + 恢复按钮 | 93 | ui | P1 | T-24 | frontend admin | 0.5–1 | GWT-93.1/93.2/93.3 UI 面 + 93.4 冲突中文句呈现。已删标记可见。恢复成功回默认列表。X-QUOTA：可见处无内码。 |
| T-26 | 基座保护：种子 admin 不可删 + 平台租户三名守卫 | 94 | api | P0 | — | backend | 0.5–1 | GWT-94.1…94.5。`delete_user` 加种子 admin 守卫（与既有两守卫并存、判定在前）；平台租户改名/停用/删除拒绝句（94.2/94.3）；无删除企业入口（94.4）；越权 404 同形（94.5）。**与 T-24 同文件（user_service.py）——不同会话施工**。 |
| T-27 | 企业编辑收口：改名（保留名冲突）/停用/再启用 + 平台租户显式化 | 95 | api | P0 | — | backend | 1–1.5 | GWT-95.1/95.2/95.4/95.6/95.7（API 面）。改名冲突域=既有企业名∪「平台租户」∪AutoAgents。停用/启用双向仅常规企业；企业管理页与运营台同走一个写服务、两处同显（同真相）。无归属新用户挂平台租户（95.4 显式化）。越权 404 同形（95.6；**/enterprise 租户 404 语义不变**，QA-02/ADR-0021 v2）。 |
| T-28 | 企业管理页增强 UI | 95 | ui | P1 | T-27 | frontend admin | 1 | GWT-95.1/95.2/95.3/95.5/95.7 UI 面。平台租户行「默认归属」标注；「AutoAgents」不出现在归属列；列表失败走 FR-84 同句式（95.5）。不重排五组、不新开第二入口。 |
| T-29 | 单布局树：撤平台页双挂载，切换不重挂不闪 | 96 | ui | P0 | — | frontend admin | 1.5–2 | **ADR-0022**。GWT-96.1/96.2/96.3。撤 `PlatformAdminLayout` 分支，/newapi /platform-ops /users 并入主路由树 + 页级守卫（非超管 NotFound 同形）。权限快照只加载一次（96.3=82.2 同句）。**GWT-96.4 钉住：菜单真相仍是 ADR-0021，本票不改 menuConfig/filteredMenus 语义**（QA-02/QA-07 边界）。 |
| T-30 | LLM「激活」→「默认」文案与互斥呈现 | 97 | ui | P0 | — | frontend admin | 0.5–1 | GWT-97.1…97.4。动作用词「默认 / 设为默认」；说明句照 spec；同域至多一个默认标记（97.2）；只读无「设为默认」控件（97.4）；空态/失败句走 FR-84（97.3）。**不重做选路数据面、不加请求级参数**。 |
| T-31 | 中转站三 tab 上提 + 页头精简 | 98 99 | ui | P0 | — | frontend admin | 1 | GWT-98.1（=FR-99 同规范）。三 tab 与欢迎语同一行；去页内标题卡/横幅；内容区直接开始。本票只动结构，数据装配不动。 |
| T-32 | 总览三问驾驶舱 + 问题渠道置顶 + 事件跳转 | 98 | ui | P1 | T-31 | frontend admin | 1–1.5 | GWT-98.2/98.3/98.5/98.6。同屏三问（Q-OVERVIEW-3Q 已决）：网关健康+模型数 / 每渠道判定+延迟+24h 事件+预算窗口 / 最近事件 Top N；spoofed/offline 置顶；事件行点击切「事件」tab。网关不可达走已冻空态句（98.6=61.2 同句，无第三套）。引擎复用，不重做探针。 |
| T-33 | 立即探测手动入口 | 98 | api+ui | P1 | T-31 | backend + frontend admin | 0.5–1 | GWT-98.4/98.7。对单渠道发起一次探测（复用探针引擎），页上可见进行中，完成后判定/延迟更新。仅平台超管；越权 404 同形且无渠道/事件副作用（98.7）。**与 T-31/32 同文件（NewApiOps.tsx）——串行或同作者连续**。 |
| T-34 | 页头规范推广：点名六页 | 99 | ui | P1 | T-29 | frontend admin | 1–1.5 | GWT-99.1…99.4。点名：LLM 配置、采集任务、AI 方案、系统设置、用户管理（中转站= T-31）。页名与页内标题不重复；失败句/动作/只读写控件隐藏不回退（99.2/99.3/99.4）。**先 T-29 定树再铺页**；LlmProviders.tsx 与 T-30 合并施工时只动一次。 |
| T-35 | 能力资产一键导入通道：上传/沙箱/四类/部分成功/幂等 + asset_imported | 100 92 | api | P0 | — | backend + dba 语义 | 2–2.5 | **ADR-0023**。GWT-100.1…100.8；GWT-92.9。上传通道（文件/目录压缩包）→ 沙箱解包 → 类型判定分发四类（agent 通道补齐）→ 目录行未上架；部分成功逐条中文原因（100.2/100.3）；超大拒绝含上限数字（100.5，上限来自配置）；**路径逃逸拒绝且资产目录外零新文件（100.7，NFR-04）**；幂等=类型+名称（100.8）。导入不触发执行、不自动上架。事件含 origin/types/succeeded/failed。 |
| T-36 | 导入入口 UI | 100 | ui | P1 | T-35 | frontend admin | 1 | GWT-100.1…100.5 UI 面。选择文件/目录、进度与逐条结果呈现（含失败原因）；空批次「没有可导入的资产。」非静默非失败句。入口仅超管（100.6 的无入口面）。 |
| T-37 | 专家团成员域扩 agent | 101 | api+ui | P0 | — | backend + frontend admin | 1 | GWT-101.1…101.5。成员可选域=专家∪智能体、成员行标注类型；组长仍专家（101.3 不扩）；agent 资产 0 时空态句仍可纯专家组建（101.4）；越权 404 同形（101.5）。**不引入执行引擎**（「一期无执行态」保持）。 |
| T-38 | 平台超管以平台租户身份入队 | 102 | api | P0 | — | backend | 0.5–1 | GWT-102.1…102.5。`task_actor_tenant_id` 解析扩展：超管→平台租户（slug=platform 种子行；缺失=入队失败可见，不静默回退）。不绕配额（102.3 满额中文句，X-QUOTA）；企业 A 归属语义不变（102.4）；冒名直打拒绝（102.5）。**边界（QA-07）：仅入队与方案归属，不开渠道组/我的安装产品空间（GWT-82.4 语义不变）**。WACT/PC 排除在事件消费侧（蓝图 §1）。 |
| T-39 | 采集方案定义字段可编辑 + 可删除 | 103 | api | P0 | — | backend | 1–1.5 | GWT-103.1…103.5（API 面）。定义字段（入口地址/采集项/调度）保存并对后续任务生效；标识字段不可改保持；被未结束任务引用删除拒绝并列引用（103.3）；空态句（103.4）。越权/只读（103.5）。 |
| T-40 | 方案编辑/删除 UI | 103 | ui | P1 | T-39 | frontend admin | 1 | GWT-103.1/103.4/103.5 UI 面。编辑表单覆盖定义字段；删除确认与引用拒绝句呈现；空态不把 demo 填回。 |
| T-41 | 方案视图纯净：分流 demo/收割器/flow 伪爬虫/源码清单 | 104 | api | P0 | — | backend | 0.5–1 | GWT-104.1/104.3/104.4。方案视图与治理目录均**无** demo/内部项独立入口（GWT-104.2 唯一 Then）。**QA-40：不建「demo/内部项来源分组展示形态」——任何票/文本不得出现该交付物**。不删除爬虫与文件本身；总件不被混入项顶满。只读同口径（104.4）。 |
| T-42 | queue_depth 接通：调度器读 AlertRule 真实评估+通知+静默窗 | 105 | api | P0 | — | backend | 1–1.5 | GWT-105.1/105.3/105.4。调度器读 queue_depth 规则行→评估（按规则所属租户排队任务深度超阈值）→已配置渠道通知 + 静默窗内不重复 + 命中记录规则处可见。**GWT-105.3 可失败验收：可选类型零「配了规则无触发路径」**；GWT-105.2 已作废不验收。越权=105.4。现读 `SCHEDULER.QUEUE_DEPTH_WARN` 的日志路径退役为非评估结果。 |

**Wave A 并行注记：** P0 各票文件面基本不相交（user_service / tenant 写服务 / App.tsx / LlmProviders / NewApiOps / 导入新域 / expert / deps+入队 / templates / registry / schedule+alert）。例外：T-24×T-26（user_service.py）不同会话；T-31→T-32→T-33（NewApiOps.tsx）同作者连续；T-29 先于 T-34；T-27 与 T-26 在 tenant/user 边界可并行但守卫测试各随各票。

**总粗估（v2）：** C+U 26–38 人日 + Wave A 约 20–24 人日 ≈ **46–62 人日（9–12.5 人周）**，落在程序 15–21 内；未触发 >21 停判线。

**并行度（C/U）：** P0 多数不改同一文件（T-01 billing ≠ T-04 outbound ≠ T-08 llm_gateway ≠ T-13 power_market ≠ T-15 AdminLayout ≠ T-16 auth ≠ T-17/20/21 各页）。T-07 与 T-08 都动 `relay_service.py` → **不要同会话并行**；T-08 可先扩 admin.py，合入 issue_token 时串 T-07 之后或同一作者连续。T-17 与 T-10 都动 RelayGroups → T-10 在 P1，错开。

**不在本表：** FR-91；在线支付；合主干；alembic 039→040（交付清单）；打开 LLM 闸；真同步 Hero。**（Wave A 追加）** C 端个人注册（Q-C-REG）；常规企业删除；专家团执行引擎；导入自动上架；「demo/内部项来源分组展示形态」（QA-40 幽灵项）；重排五组。

---

## 12. FR → 票 覆盖（自检）

| FR | 票 |
|---|---|
| 50 | T-01 T-02 T-03（完成线 T-02/T-03 = 我的订单已确认；50.13→T-03 QA-23） |
| 51 | T-04 T-05 T-06 |
| 60 | T-07 T-08 T-09 T-10（60.3/QA-21/QA-20→T-09） |
| 61 | T-11 |
| 87 | T-12 |
| 80 | T-13 |
| 81 | T-14 |
| 82 | T-15 |
| 83 | T-16 |
| 84 | T-17 T-23 |
| 85 | T-18 |
| 88 | T-19 |
| 89 | T-20 |
| 90 | T-21（90.2 单 Then QA-22） |
| 92 | T-02 T-05 T-09 T-14 生产事件；T-22 查询/fail-open（QA-24 完成线与 T-02 对齐）；**T-24 = 92.8 user_restored；T-35 = 92.9 asset_imported** |
| 91 | **无票** |
| 93 | T-24 T-25（92.8→T-24；QA-03 唯一语义→§8/dba） |
| 94 | T-26（与 T-24 不同会话） |
| 95 | T-27 T-28（QA-02：/enterprise 租户 404 语义不变，ADR-0021 v2） |
| 96 | T-29（ADR-0022；96.4 钉 FR-82 不变） |
| 97 | T-30 |
| 98 | T-31 T-32 T-33（98.1 与 FR-99 同规范；Q-OVERVIEW-3Q 已决） |
| 99 | T-34（+98.1→T-31；点名六页） |
| 100 | T-35 T-36（ADR-0023；92.9→T-35；100.7 路径逃逸→SEC-11） |
| 101 | T-37 |
| 102 | T-38（QA-07：82.4 边界钉住） |
| 103 | T-39 T-40 |
| 104 | T-41（**104.2 唯一 Then；QA-40 无幽灵交付物**） |
| 105 | T-42（Q-QUEUE-DEPTH 已决接通；105.2 作废不验收） |

NFR-01→T-14/verify；NFR-02→T-14；NFR-03→T-17 T-18 T-23 **T-29**；NFR-04→T-04 T-05 T-08 T-09 **T-24 T-35（100.7 收容）**；NFR-05→T-15 T-20 **T-24 T-26 T-27 T-33 T-35**；NFR-06→T-10；NFR-07→不改已兑 404 句；NFR-08→T-22 **T-24 T-35**；NFR-09 N/A；NFR-10→T-08 不并根编排 **+ T-35 上传上限走配置**。

---

## 13. 威胁模型（STRIDE，Q2/Q3/Q4 = yes）

数据流：浏览器 JWT → API；外部 X-API-Key → 出站拉数；租户客户端 sk- → LiteLLM chat；backend master → LiteLLM admin HTTP；超管确认收款。**Wave A 追加：** 超管浏览器上传文件/目录 → 导入沙箱；超管恢复软删用户；平台超管以平台租户身份入队；调度器读 AlertRule → 外发通知。

| ID | 边界 | 类 | 缓解 | 锚 |
|---|---|---|---|---|
| [SEC-1] | B-出站 | S/E | hash 存；compare_digest；跨企业 0 行 | T-05；NFR-04 |
| [SEC-2] | B-中转 chat | S | 虚拟 Key ≠ master；revoked 拒绝 | T-08 T-09；QA-20 |
| [SEC-3] | B-中转 chat | I | 页上无 master；日志/事件无明文 | T-10；FR-92 |
| [SEC-4] | B-出站×中转 | E | 查找集合不相交；51.6/51.10 | T-05；ADR-0020 |
| [SEC-5] | B-确认收款 | E | 仅 `require_platform_admin`；租户确认拒绝 | T-02；GWT-50.9 |
| [SEC-6] | B-登录 | I | 未知标识与错密码同句 | T-16 |
| [SEC-7] | B-admin HTTP | I | master 仅服务端；禁 DSN | T-08；ADR-0019 |
| [SEC-8] | B-公开列表 | D | 页大小≤20；种子不进 total | T-13 T-14 |
| [SEC-9] | B-确认 | R | 已有 `order.confirm` 审计；保持 | T-02 |
| [SEC-10] | B-跨租户用量 | E | A 调用后 B 基线不变 | T-09；GWT-60.10 |
| [SEC-11] | B-导入上传 | S/E/T | 沙箱解包；路径规范化收容（`../`/绝对路径/symlink 拒绝）；资产目录外零新文件；不自动上架不执行；仅超管 | T-35；GWT-100.6/100.7；ADR-0023；NFR-04 |
| [SEC-12] | B-恢复 | E/R | 恢复仅平台超管；占用冲突拒绝不覆盖现有用户；判定与写入同事务；租户直打 404 同形 | T-24；GWT-93.4/93.6/93.8 |
| [SEC-13] | B-平台租户身份 | E | 身份仅采集入队/方案归属；不绕配额；不开企业产品空间；非超管冒名拒绝 | T-38；GWT-82.4/102.3/102.5 |
| [SEC-14] | B-告警通知 | I/S | 规则仅本租户可改（105.4）；命中记录仅调度器写；通知内容无内码/明文；静默窗防风暴 | T-42；GWT-105.1/105.4 |

残留：LiteLLM chat 端口对租户网络暴露（常见中转站代价）；管理端口仍隔离。不静默接受 master 泄漏。**Wave A 残留：** 上传面天然扩大攻击面（恶意压缩包/炸弹）——沙箱 + 大小上限 + 不执行缓解，深度扫描（病毒扫描等）本波不做、记 /sre 账本。

---

## 14. 风险点（给 `/qa` `/sre`）

| 风险 | 影响 | 给谁 | 建议关注 |
|---|---|---|---|
| 四测勾 50/60 | 空心完成 | qa | 必须对 Then，禁止 `test_billing_relay` 当绿闸 |
| 本地假成功令牌 | PC-4 假绿 | qa | 签发失败可见；60.3 网关可达夹具 |
| 确认当履约 | 代选 Q-PRICE | qa | 50.10 只看已确认 |
| 种子仍在精选 | PC-2 护栏 | qa | 列表+首页 |
| GET 建组 | 60.4 测不到 | qa | viewer GET 前后组数 |
| 菜单双源回潮 | 82.1 | qa | 给脏 `/auth/menus` 仍见渠道组 |
| 入队仍渲内码 | X-QUOTA | qa | toast + JSON 可见处 |
| 网关不可达当满额 | 护栏 | qa | 60.5 vs 12.3 |
| 040 未迁环境 | 表不存在 | sre | **交付清单** |
| PUBLIC_BASE_URL 指到 docker 内网 | 租户客户端打不通 | sre | 夹具用可达 URL |
| 导入沙箱逃逸 / 压缩炸弹 | 资产目录外写文件 | qa sre | 逃逸条目抽检；大小上限；解包超时（T-35） |
| 恢复×新建同标识并发竞态 | 覆盖现有用户 | qa | 判定与写入同事务；/dba 唯一机制（§8） |
| 布局重构让平台页对租户可达 / 菜单语义漂移 | X-IA 回潮 | qa | 直打 /users /platform-ops /newapi /enterprise /rbac 仍 404 同形；脏 /auth/menus 下 82.1 重跑 |
| queue_depth 通知风暴 / 死规则回潮 | 值班被刷屏或形同虚设 | qa sre | 静默窗；GWT-105.3 全类型扫描 |
| WACT 混入平台租户任务 | 北极星失真 | analyst | 蓝图 §1 排除口径；消费侧过滤 |

回滚：代码回 tag；orders/paid 不可逆（业务）；LiteLLM Key 作废走 HTTP。SALT 轮换仍不是普通回滚。

---

## 15. 交付清单（不是用户故事）

- 预发/本机 alembic **升级到 040**（plans/orders/relay 表）；禁止把「current=039」写成 FR。
- 合主干 / 分支 ahead：发布检查，不开票。
- CONTEXT 过期「令牌不发给租户」改成 spec §0.4 三名。
- `LLM.ENABLED` / 上游 key 保持机外。
- 不标四柱 GA。

---

## 16. 给下一 spawn 的清单

1. 按本表写 `tickets/T-01.md`…`T-23.md`（FR+GWT、同 PR 测试、expand-contract、QA-20…24 注记）与 `tickets/T-24.md`…`T-42.md`（Wave A；T-24 带 QA-03 同事务注记、T-29 带 ADR-0022、T-35 带 ADR-0023 与 100.7 收容、T-38 带 GWT-82.4 边界、T-41 带 QA-40 禁幽灵项注记）。
2. `/dba` 按 §8 出 db-spec；出站实体 + relay 网关引用 expand；**v2 追加：** users 在册行唯一（QA-03）、租户保护/编辑、导入批次、queue_depth 命中记录语义；**不要**网关 PG。
3. `/designer` 空态/找管理员句；不重排五组。**v2 追加：** 总览三问布局、页头规范（点名六页）、「默认」交互、导入 UX、恢复冲突句、企业管理「默认归属」标注。
4. 实现帽：billing/relay **扩**；禁止从零重写 040。Wave A：user_service/tenant 写服务单点收口；布局重构不动菜单真相。

---

## 17. G-self-check

- [x] 模块单方向依赖（含 Wave A 追加边，无新环）
- [x] 28 FR 均有票；FR-91 无票；每票有 FR；92.8/92.9 落 T-24/T-35
- [x] 无巨票；一票一会话（Wave A 最大 T-35 ≈ 2–2.5 人日，含沙箱+四类，仍单会话可交付；若实现中爆量按 100 安全壳/101 分发拆分，票号顺延）
- [x] 不可逆：0019/0020/0021 + **0022/0023**；确认收款不可逆写在 T-02
- [x] 破坏性：菜单停读 expand；page_size 收紧写明；relay 加引用列 expand；**布局双挂载撤除 = expand-contract（先并树后清分支）**
- [x] 可行性读码（§4 含 Wave A 14 行，file:line）
- [x] 角色裁剪含 N/A
- [x] C4 到组件
- [x] 本 spawn 不写 tickets/*.md（28 FR > 20，票表制）
- [x] 不代选六问（含 Q-C-REG）；不标 GA；不焊根编排
- [x] shape-r1 QA-01…QA-10 全处置（QA-02/04 写回 ADR；QA-03→§8；QA-05/08/09→§7；QA-06→§13；QA-07→T-38；QA-10→§18）
- [x] QA-20…24 原位保持（T-09/T-21/T-03/T-02，未丢）；QA-40 幽灵项零出现（§0/§7.9/§10/T-41 均为禁令）

---

## 18. 开放问题（本帽不答）

| ID | 状态 | 本方案 |
|---|---|---|
| Q-VOICE | 待确认 | 不改对外第一句 |
| Q-PRICE | 待确认 | 不选撤/履约/预告；确认 Then 不含三数字履约 |
| Q-MARKET-USER | 待确认 | FR-91 无票 |
| Q-AGPL | 待确认 | 0 次「当前可买中转」；不冻对外互否 |
| Q-OPS-COLLECT | 待确认 | 不发明电话 |
| Q-C-REG | 待确认（QA-10 补行） | 不开 C 端个人注册；无企业归属挂平台租户的**管理规则已冻**（GWT-95.4），本方案只显式化不新开路径 |

已关勿再问：Q-LLM / Q-BILL / Q-RELAY / Q-OPS-DUTY / **Q-ADMIN-WAVE / Q-QUEUE-DEPTH / Q-OVERVIEW-3Q**。

---

## 19. 变更记录

| 版本 | 日期 | 变更 | 触发者 |
|---|---|---|---|
| v1 | 2026-09-11 | 初版。冻结 15 FR 票表 T-01…T-23。ADR-0019/0020/0021。携带 QA-20…24。无 tickets/*.md | define r3 PASS → 塑形第一 spawn |
| v2 | 2026-09-11 | **shape r1 扩展**：并入 Wave A（FR-93…105 → T-24…T-42，19 票）；上游升 spec v1.5 / user-story v1.5 / 蓝图 v1.4。消化 findings-shape-r1 QA-01…QA-10：QA-02/04 写回 ADR-0021/0019（两 ADR 升 v2 修订）；QA-03 users 唯一语义入 §8；QA-05 夹具口径、QA-08 list_tokens 读模型、QA-09 只读单 Then 入 §7；QA-06 追加 SEC-11…14；QA-07 钉 T-38；QA-10 补 §18 Q-C-REG。携带 QA-40（幽灵项不建设，GWT-104.2 唯一 Then）。新增 ADR-0022（单布局树）/ADR-0023（导入沙箱）。QA-20…24 原位核对未丢。appetite 校正：三波合计约 9–12.5 人周 < 21，不停判 | shape r1 fail（blocker 3/major 6/minor 1）→ 塑形扩展 spawn |
| v2.1 | 2026-09-11 | **implement 终审微补**：§7.1 追加 8 个已实现错误码（`ORDER_ROLE_NOT_ALLOWED` / `ORDER_ONLINE_UNAVAILABLE` / `TASK_QUOTA_LIMIT_REACHED` / `TASK_RUN_ROLE_NOT_ALLOWED` / `RELAY_TOKEN_ROLE_NOT_ALLOWED` / `RELAY_GROUP_ROLE_NOT_ALLOWED` / `OUTBOUND_KEY_ROLE_NOT_ALLOWED` / `RELAY_GATEWAY_UNAVAILABLE`，均用户可见中文句、code 不渲染，IMPL 终审 a 项追认）；§7.4 补 GWT-60.6 写面例外注记（页面/GET 面=404 同形、API 写面=既有 403，GWT-70.3 金标不破，IMPL-QA-1）；§7.9 GWT-93.6 越权行补 IMPL-QA-3 注记（`GET /admin/users` 维持 `require_admin` 既有行为，同形语义由平台页守卫+恢复动作面兑现）。**其他零改动** | implement 终审回写（IMPL-QA-1/3 + 终审 a 项追认） |
