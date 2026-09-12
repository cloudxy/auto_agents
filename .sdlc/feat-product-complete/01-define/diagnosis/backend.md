# 定义帽 · Backend 诊断（feat-product-complete）

| 字段 | 值 |
|------|----|
| 角色 | backend（只读诊断；不实现 API、不写迁移、不改测试、不改 GWT、不写表结构） |
| 日期 | 2026-09-10 |
| 泳道 | L4 |
| 特征 | `feat-product-complete`（upstream 冻结集 = `feat-four-pillars-v2` Wave 0+L+1） |
| 输入 | `state.yaml`；`feat-four-pillars-v2/01-define/spec.md` v1.6 Wave 2/3 stub；`backend/app/api/` + `backend/services/`；`040_billing_and_relay_sku.py`；`test_billing_relay.py`；`payment_provider.py` |
| 宪法 | `.claude/rules/project_rule.md`；契约回 architect / 表结构回 dba / 验收口径回 pm |
| 禁止 | 代选 Q-VOICE / Q-PRICE / Q-MARKET-USER / AGPL |

对照口径：spec v1.6 把 FR-50/51/60/61 写成 stub；`state.yaml` 已继承关闭 **Q-BILL**（线下账务骨架；在线通道 `PAYMENT_NOT_CONFIGURED`）与 **Q-RELAY**（租户渠道组 SKU；租户改不了全局熔断）。本帽按 **现网代码** 对照 stub + 已关闭问，不把未关四问写成已选。

---

## 0. 结论（给 PM / architect 的三句）

1. **Wave 2/3 骨架已挂上主 API，不是 0。** `018c369` 路径现网为：`GET/POST /api/v1/billing/*`、`GET/POST/PATCH/DELETE /api/v1/relay/*`、Alembic `040`、线下挂账 + 超管确认收款改配额。在线通道故意空。探针伪装仍不熔断。出站拉数未绑定仍拒绝。
2. **产品不好用的主因不是「缺表」，是断链与空壳。** 用量告警没有按维度的下一步 URL；只读点「申请提升」拿到的是 `FORBIDDEN` 而不是「找管理员」；渠道组令牌不进 LiteLLM、RPM/TPM/`used_tokens` 不执法；`GET /relay/groups` 读路径会落库建 `default`。
3. **开放 minor 半关。** C35-QA-04 命令收回已有测试+实现；技能/其它类型仍不收回；治理列表不过滤 `deleted_at`。公开商店分页技能端已钉 `len(items)==20`，能力端同实现未钉。公开 alias 可读，治理详情/alias 不跳转、投影无 canonical。

---

## 0.1 已关闭问 vs 仍开放（本帽不代选）

| 问 | 本特征状态 | 对后端的含义 |
|----|------------|--------------|
| Q-BILL | `state.yaml` 已决：支付先空着，线下订单 | 允许账务骨架；禁止把 alipay/wechat 写成可扣款 |
| Q-RELAY | `state.yaml` 已决：租户渠道组 SKU | GWT-60.1「无我的渠道组」被操作者推翻为「有组+令牌」；GWT-60.3 全局熔断仍拒 |
| Q-VOICE / Q-PRICE / Q-MARKET-USER / Q-AGPL | 仍开放 | 本帽不选出口文案、价签履约、市场北极星、对外收费故事 |

spec v1.6 FR-50/60 正文仍写「Q-BILL/Q-RELAY 未决」。塑形时必须以 `state.yaml` 已决句为准，**改 spec 是 pm 的事**，backend 不偷改 GWT。

---

## 1. 总表：已落地 vs 仍缺 vs 不好用

| 切片 | 已落地（入口 / 证据） | 仍缺 | 不好用 |
|------|----------------------|------|--------|
| FR-50 满额下一步 | 用量告警句 `PLAN_FULL_USER`；存储拒绝句含「去结果库」；token 拒绝句含「申请提升配额」；`PATCH /tenants/me/quota` 锁死；线下 `POST /billing/orders`；只读不能下单 | 用量 JSON 无 `cta`/`href`；只读无「找管理员」句；无「去结果库」结构化下一步；订单列表无空态 | 内部码 `QUOTA_EXCEEDED` / HTTP 429 进租户信封；前端 CTA 靠硬编码 |
| FR-51 自助出站钥匙 | FR-13 拒绝仍真：`KEY_BINDINGS` 恰好一租户，否则 401、0 行 | **无**租户签发入口（无 `/api-keys` 路由） | 出站钥匙仍是平台配置，不是产品面；`/spider/status|results|stats` 仍走未绑定 `API_KEYS` |
| FR-60 租户渠道组 | `/api/v1/relay/groups|tokens` CRUD；跨租户 404；只读不能签发；`/newapi` 写 `require_platform_admin` | 令牌不接网关；配额字段不计数；无只读「用量与状态」独立于写 | `GET /groups` 读时建组；`menu:relay` 给 viewer；tenant `admin` 回退映射仍含 `menu:newapi` |
| FR-61 探针伪装 | spoofed 只落库+通知，不改 Redis 窗口/额度、不调网关预算 | 值班「能看到伪装」是前端/overview 字段，本帽不验 UI | 阈值写死 `_REF_SIMILARITY_SPOOF_THRESHOLD = 0.15`，租户无入口（符合 61.3） |
| 支付通道 | `OfflinePaymentProvider` 挂账；`UnconfiguredOnlineProvider` 拒 | 无回调、无 webhook、无发票 | `PAYMENT_NOT_CONFIGURED` 进 JSON `code` |
| C35-QA-04 | 命令 `_retract_missing_commands` + `test_src_sync_retracts_commands_removed_from_manifest` | 技能/插件源文件删除不收回 | 治理 `list_assets` 仍列出软删行 |
| 治理分页 | 公开 `list_public` 查询侧闸再 OFFSET | 能力端 GWT-33.4 未钉 `len(items)==page_size`（IM-03） | 治理列表无 `has_more`、不过滤 `deleted_at` |
| alias 跳转 | 公开 `_load_named` 解析 alias；GWT-45.1 同字节 | 治理 `GET /capabilities/{type}/{name}` 不解析 alias；投影无 alias 字段；无 302/canonical | `GET /public/capabilities/aliases` 恒商店 404 HTML |

路由挂载：`backend/app/api/v1/__init__.py:32-33` `prefix=/billing`、`prefix=/relay`。

---

## 2. FR-50 满额下一步（Usage CTA、订单、只读角色）

### 2.1 已落地

| GWT | 现网 | 证据 |
|-----|------|------|
| 超限用户可见句 | `PLAN_FULL_USER = "已达配额上限"`；token CTA `PLAN_FULL_CTA`；存储 CTA `STORAGE_CLEANUP_CTA = "去结果库"` | `quota_service.py:27-34` |
| 用量告警不含内部码 | ≥90% `NEAR_LIMIT_USER`；满额 `level=full` 且 `message=PLAN_FULL_USER`；overview 字符串断言无 `QUOTA_EXCEEDED` | `quota_service.py:77-109`；`test_saas_quota.py::test_usage_overview_near_limit_alert_has_no_internal_code` / `test_usage_overview_full_alert_is_plan_full_sentence` |
| 闸接到打模型前 | `llm_chat` 出站前 `_enforce_tenant_token_quota`；满额计划 `error_message` 含满额句、无 `QUOTA_EXCEEDED`、不出站 | `llm_client.py:394-458`；`test_llm_four_actions_http.py::test_post_plan_quota_full_gateway_reachable_only_12_3` |
| 入队并发闸 | `enqueue` 超并发抛 `QuotaExceededException`，message 含满额句+申请提升 | `quota_service.py:189-194`；`test_saas_wiring.py::test_enqueue_carries_tenant_and_quota_rejects` |
| 本波不能自助改套餐 | `PATCH /tenants/me/quota` → 400 `QUOTA_PLAN_LOCKED`「本波不可自助改套餐。请申请提升配额。」守卫 `require_tenant_manager` | `tenant_usage.py:64-73` |
| 只读可见用量 | `GET /tenants/me/usage` `require_login`；viewer 200；viewer PATCH quota 403；viewer 打 `/admin/tenants/{id}` 404 | `tenant_usage.py:36-41`；`test_saas_quota.py::test_readonly_usage_cannot_change_plan_and_cannot_render_gateway_failure_as_quota` |
| 线下订单 | 公开 `GET /billing/plans`；owner `POST /billing/orders` channel=offline → 201 pending；超管 `POST /billing/orders/{id}/confirm` → paid 并写 `tenants.quota` | `billing.py:21-77`；`billing_service.py:39-96`；`test_billing_relay.py::test_list_plans_and_offline_order` |
| 只读不能下单 | viewer `POST /billing/orders` 403 | `test_billing_relay.py::test_viewer_cannot_create_order_or_token` |
| 注册挂免费档 | `TenantSignupService` 调 `attach_free_plan` | `tenant_signup_service.py:99`；`billing_service.py:98-106` |

### 2.2 仍缺

- **用量 overview 没有下一步字段。** `build_usage_alerts` 满额只给 `message: PLAN_FULL_USER`，不按维度带 `cta`/`href`（存储应去结果库、token 应去联系说明/订单）。`quota_service.py:97-102`。GWT-50.1/50.2 的「点下一步」在 API 上无对象。
- **GWT-50.3 文案未落地。** 只读点申请提升：`POST /billing/orders` / `PATCH /quota` 都是 `AuthorizationException`「需要租户 owner/admin 权限」`code=FORBIDDEN`（`members.py:28-29`），不是「说明找管理员，不改套餐」。市场订阅只读句「当前账号不能订阅，请联系企业管理员」在 `power_market/types.py` `MSG_READONLY_ROLE`，**没有**套到用量/订单。
- **operator（tenant_role=operator）也不能下单**（同一 `require_tenant_manager`）。spec 负责人能走下一步；经办满额只能看用量。
- **订单空态/分页/幂等未做。** `GET /billing/subscription` 无行 → `data: null`（`billing.py:26-33`）；`GET /billing/orders` 空数组无 message（`billing_service.py:66-71`）。`orders.idempotency_key` 列在 `040:57` 存在，`create_order` 不写、不查。
- **无取消订单。** pending 只能等超管 confirm。

### 2.3 不好用 / 断链

- 入队超限走统一信封：HTTP **429** + `code: QUOTA_EXCEEDED`（`QuotaExceededException` `quota_service.py:119-123`；handler `handlers.py:28-36` 原样把 `exc.code` 塞进 JSON）。X-QUOTA 允许内部码存在、禁止渲给租户；**租户 SPA 的 API 契约已经渲了。** 规划失败路径把句子写进 `error_message`、不走该信封（较好）；爬虫入队没有同等映射。
- `GET /tenants/me/usage` 无企业空间：200 + `message: 用量属于企业空间`（`tenant_usage.py:42-48`，GWT-16.3）。`GET /usage/by-member` 同条件却是 400 `USAGE_NEEDS_TENANT`（`tenant_usage.py:30-32,60`）。同一资源两种空态。
- 确认收款挂在租户前缀 `POST /billing/orders/{id}/confirm`（`billing.py:68-77`），不是 `/admin/orders/{id}/confirm`。租户误打 = `FORBIDDEN`，不是 404 同形。

---

## 3. FR-51 租户自助出站钥匙（签发入口；FR-13 拒绝是否仍真）

### 3.1 FR-13 拒绝仍真（GWT-51.2）

| 行为 | 证据 |
|------|------|
| 出站 `GET /external/v1/public/data/{spider_name}` 必须 `bound_tenant_id` | `public.py:36-41,67-80` |
| 未绑定 / 空名单 / 旧字符串列表钥匙 → `None` → 401，不查库 | `webhooks.py:116-132,167-174`；`test_external_api.py` `test_string_list_in_bindings_is_unbound`、GWT-13.2/13.3、`test_unbound_service_returns_zero_rows_without_query` |
| 默认配置 `KEY_BINDINGS: []` | `config/default/external_api.yml:14` |

**GWT-51.2 Then 仍成立：** 未配置绑定，任意钥匙拉数拒绝、0 行。本 stub 没有把 Wave 0 拒绝改掉。

### 3.2 仍缺签发入口（GWT-51.1 / 51.3）

- `backend/app/api/v1/` **没有** `api_keys.py`（`__pycache__/api_keys.cpython-313.pyc` 是陈旧字节码，路由聚合 `__init__.py:9` 不 import）。
- 全仓无租户「签发拉数钥匙」Service。绑定只来自 Dynaconf `EXTERNAL_API.KEY_BINDINGS`。
- **不得把平台共享钥匙写成租户功能：** `validate_api_key` 仍给 `/spider/status|results|stats` 用（`public.py:26-33,101-144`）。这三条 **不**走 `bound_tenant_id`。GWT-13 只冻出站拉数；状态/结果/统计仍是平台共享钥匙面——FR-51 若做自助钥匙，必须先收这三条，否则「租户钥匙」会和共享钥匙双轨。

### 3.3 不要和 FR-60 令牌混为一谈

`relay_tokens.plaintext_key` 是 `sk-` 虚拟中转钥匙（`relay_service.py:122-135`），**不是**出站拉数 `X-API-Key`。签发中转令牌 ≠ FR-51。

---

## 4. FR-60 租户渠道组（relay API；租户改全局熔断是否仍拒）

### 4.1 已落地（相对 spec stub：操作者已选 SKU）

Q-RELAY 已决后，GWT-60.1「无我的渠道组」不再是现网目标。现网：

| 能力 | 证据 |
|------|------|
| 列表/建组/改组 | `relay.py:22-55`；`relay_service.py:57-108` |
| 列/签发/吊销令牌 | `relay.py:58-90`；明文只在签发响应一次（`plaintext_key`），列表为 `None`（`relay_service.py:134-135,181`） |
| 跨租户改组 404 | `test_billing_relay.py::test_relay_group_token_issue_and_revoke` stolen PATCH → 404 |
| 只读不能签发 | `test_viewer_cannot_create_order_or_token` POST tokens 403；GET groups 200 |
| 写守卫 | 写：`require_tenant_manager`（owner/admin）；读：`get_current_user` |
| 菜单回填 | `040:109-114` 给 `viewer/operator/admin` 追加 `menu:relay`；硬编码回退 `_ROLE_PERMISSIONS` 三档都有 `menu:relay`（`auth.py:98-116`） |
| 无企业空间 | `require_tenant_id` → `AuthorizationException`「需要企业空间」（`relay_service.py:185-189`） |

### 4.2 全局熔断 / 平台渠道：租户仍拒（GWT-60.3，Wave 0 已冻）

| 路径 | 守卫 | 租户结果 |
|------|------|----------|
| `GET /newapi/channels\|overview\|probe-results` | `require_platform_admin_or_404` | JSON 404 `HTTP_404` / `Not Found`（`newapi.py:47-91`；`deps.py:153-169`） |
| `PUT/DELETE /newapi/channels/{id}/config`、`/models/{ref}/config` | `require_platform_admin` | 403 + 越权审计（`newapi.py:97-171`；`deps.py:134-150`） |
| `POST /newapi/models\|upstreams` | `require_platform_admin` | 同上（`newapi.py:173-202`） |

`test_tenant_still_cannot_write_platform_channels` **只打 GET** `/newapi/channels`，断言 `403 or 404`（`test_billing_relay.py:158-163`）。**未覆盖 PUT config / 熔断字段。** GWT-60.3 写路径金标偏空；实现守卫在，测试不够。

平台成本熔断仍是全局 `LLM.MAX_TOKENS_BUDGET`（`llm_client.py:460-462`），租户 relay 表碰不到它。

### 4.3 仍缺 / 空壳 SKU（GWT-60.2「能看自己的用量与状态」）

- `used_tokens` 只回读、签发后永不递增（`relay_service.py:175-176`；全仓无其它写点）。
- `rpm_limit` / `tpm_limit` / `models_json` 只存库，**不**注入 LiteLLM、不进 `llm_gateway`。
- `plaintext_key` 不能当网关 Key：网关虚拟 Key 走 `_virtual_key()`（`llm_gateway/_settings.py:20`），与 `relay_tokens.key_hash` 无关联。
- 无「令牌调用记录 / 组级用量」查询面。GWT-60.2 只读用量 **未履约**。

### 4.4 不好用

- **读路径写库：** `list_groups` 空则 `_ensure_default` + `commit`（`relay_service.py:62-65,152-159`）。viewer GET 也会建 `default`。空态永远走不到。`test_viewer_cannot_create_order_or_token` 依赖这次副作用取 `data[0].id`。
- **租户 `users.role=admin` 回退权限仍含 `menu:newapi` / `menu:platform-ops`**（`auth.py:110-115`）。DB `roles` 若未收口，公司管理员导航仍可能露出值班页；直打 GET 已 404，写 403——壳与守卫不一致。
- 组名冲突 `RELAY_GROUP_EXISTS`、停用组签发 `RELAY_GROUP_DISABLED` 进租户 JSON `code`（`relay_service.py:75,121`）。

---

## 5. FR-61 探针伪装不熔断

### 5.1 已落地（与 GWT-07.6 同一句）

`channel_probe_service.py:277-308`：采集 → 评分 → `_record_probe_result`；`verdict == "spoofed"` 只 `NotifyService.notify_text("channel.probe.spoofed", …)`。**不**改 Redis cfg、**不**写 `RELAY_CHANNEL_STATE`、**不**调 `create_budget/update_budget/update_model`。

金标：`test_llm_probe.py::test_gwt_07_6_spoofed_keeps_channel_usable_window_quota_unchanged`（cfg 快照不变、`budget_calls == []`、state key 不出现）。

GWT-61.2 值班空态走 FR-71：`DUTY_EMPTY_71_2` / 降级句在 `gateway_models.py` + `newapi_overview_service.py:68`；`test_newapi_api.py` 钉 `empty_state`。本 stub 未另写第二套空态。

### 5.2 越权（GWT-61.3）

探针阈值是模块常量 `_REF_SIMILARITY_SPOOF_THRESHOLD = 0.15`（`channel_probe_score.py:11`；`test_llm_probe.py:164` 钉源码字符串）。**无**租户/超管 HTTP 改阈值入口。符合「租户改探针阈值 → 无入口」。

### 5.3 缺口（产品可见性，不是熔断）

GWT-61.1「值班看页能看到伪装」= overview/probe-results 的 `verdict=spoofed` 字段（`newapi.py:71-79`）。本帽不验前端是否渲染。后端列表对超管存在。

---

## 6. payment_provider 空在线通道

`payment_provider.py:24-49`：

| channel | 行为 |
|---------|------|
| `offline`（默认） | `OfflinePaymentProvider.collect` → pending，不打第三方 |
| `alipay` / `wechat` | `UnconfiguredOnlineProvider.collect` → `BusinessException` message「在线支付尚未开通，请改用线下对公。」`code=PAYMENT_NOT_CONFIGURED` |

`billing_service.create_order` 对在线通道 **先** `collect(order_id=0)` 再查套餐（`billing_service.py:41-44`），因此 alipay **不落 orders 行**。`test_billing_relay.py:40-46` 钉 400 + `PAYMENT_NOT_CONFIGURED`。

`PlanOut.quota_json` 公开价目原样吐配额 JSON（`schemas/billing.py:10-19`）。不是密钥，但是内部配额契约暴露给匿名 `GET /billing/plans`。

无：支付回调路由、签名校验、渠道密钥配置、发票。与 Q-BILL 已决句一致。**不要**把空通道填成真扣款。

---

## 7. 开放 minor

### 7.1 C35-QA-04 src_sync retract — 命令已关，其余仍开

**已关（命令）：** `sync.py:221-251` `_upsert_commands` 后 `_retract_missing_commands`：同源同插件、不在 keep 集合的 command 行 `deleted_at=now`、`sync_state=gone`。  
金标 `test_t29_sources.py::test_src_sync_retracts_commands_removed_from_manifest`（C35-QA-04 docstring）。

**仍开：** 全仓只有这一处 `_retract_missing_*`。技能/插件源文件删除 **不**软删治理行。coverage.md 旧注「删除源文件不收回」对命令过时，对其它类型仍真。

**治理面副作用：** `CapabilityService.list_assets`（`capability_service.py:32-59`）**不过滤** `deleted_at`。收回的命令仍占治理分页 `total`/`items`。公开 `list_public` / `_load_named` 有 `deleted_at.is_(None)`（`service.py:83,341`）。同一收回，商店消失、治理还在。

### 7.2 治理分页（IM-03）

| 面 | 分页 | 证据 |
|----|------|------|
| 公开技能 | 查询侧闸 + OFFSET；GWT-33.4 **钉** `len(d1["items"])==20`、page2 空、`has_more is False` | `test_skill_public_api.py:242-251` |
| 公开能力 | 同一 `list_public`；GWT-33.4 **未钉** page1 长度 | `test_b1c_capabilities_coverage.py:812-819` 只断言 `total==20`、page2 `items==[]` |
| 治理 `GET /api/v1/capabilities` | SQL offset/limit；无 `has_more`；空目录才 `empty+message` | `capabilities.py:39-76` |

IM-03 仍是测试缺口（能力端），不是第二套实现。治理列表与公开闸不是同一谓词（无 FR-33、无软删过滤）——超管目录翻页会被 gone 行顶满。

### 7.3 alias 跳转

| 路径 | 行为 | 证据 |
|------|------|------|
| 公开详情目录短名或 alias | `_load_named` 先 name 再 `_load_by_alias`；GWT-45.1 两 URL 同一 `name` | `service.py:333-365`；`test_t33_aliases.py::test_gwt_45_1_alias_url_same_row_as_catalog_slug` |
| 公开投影 | `_project` 无 alias/canonical 字段 | `service.py:394-405` |
| `GET /public/capabilities/aliases` | PIT-1 占位，恒商店不存在句 HTML | `public_skills.py:79-83` |
| 治理 `GET /capabilities/{type}/{name}` | `CapabilityService.get_asset` **精确 name**，alias 404 | `capability_service.py:61-70`；`capabilities.py:397-410` |
| 写 alias | `PUT /capabilities/{type}/{name}/alias` 仅超管；冲突 409 | `capabilities.py:347-365`；`aliases.py:29-32` |

「跳转」未做：无 302、无 Location、治理详情不能用 alias 打开、公开 JSON 不回 alias。访客打开 alias URL 能读（前端用 URL slug 打公开 API 即可），但响应 `name` 是目录短名，SPA 不替换地址。

---

## 8. 租户路径 API：空态 / 内部码 / 越权 / 断链

信封一律 `success/code/message/data`（`handlers.py:28-36`）。内部码 **默认渲给调用方**。

### 8.1 租户 JSON 里会出现的内部码

| code | 何时 | 用户可见 message | 问题 |
|------|------|------------------|------|
| `QUOTA_EXCEEDED` | 入队/存储/token 闸抛 `QuotaExceededException` | 满额中文句（可） | HTTP **429** + code 字面量；X-QUOTA 禁裸 429 |
| `QUOTA_PLAN_LOCKED` | PATCH `/tenants/me/quota` | 「本波不可自助改套餐…」 | 开发态口吻 |
| `USAGE_NEEDS_TENANT` | GET `/usage/by-member` 无企业 | 「用量属于企业空间」 | 与 overview 200 不一致 |
| `PAYMENT_NOT_CONFIGURED` | 在线渠道下单 | 「在线支付尚未开通…」 | 码是工程师词 |
| `ORDER_FREE_PLAN` | 免费档下单 | 「免费档无需下单」 | |
| `RELAY_GROUP_EXISTS` / `RELAY_BAD_STATUS` / `RELAY_GROUP_DISABLED` | 渠道组写 | 中文句 | |
| `FORBIDDEN` | 只读下单/改套餐/签发令牌 | 「需要租户 owner/admin 权限」或「需要角色 …」 | 不是 GWT-50.3 / 市场只读句 |
| `HTTP_404` | 租户 GET `/newapi/*` | `Not Found`（英文） | 与官网「页面不存在，可能已被移除或地址有误」不同形 |
| `MARKET_*` | 订阅/安装 | 中文产品句 | 码仍在 JSON；安装空列表 **故意**不含「还没有订阅的能力」（`test_t26_installs.py:114-123`，空句在 UI） |
| `BUSINESS_ERROR` | 安装行 flags 锁 | `MSG_FLAGS_LOCKED` | 通用码 |

规划满额：**不**把 `QUOTA_EXCEEDED` 放进 `error_message`（`test_llm_four_actions_http.py:532`）。入队满额：**会**把该码放进 HTTP 信封。

### 8.2 空态不一致

| API | 空时 | 可行动？ |
|-----|------|----------|
| `GET /tenants/me/usage` 零用量 | 三指标 0，无 `empty` | 前端自编「还没有用量」 |
| `GET /billing/subscription` | `null` | 无 |
| `GET /billing/orders` | `[]` | 无 |
| `GET /relay/groups` | **永不空**（GET 建 default） | 假满 |
| `GET /relay/tokens` | `[]` | 无 |
| `GET /capabilities/installs` | `{total:0,items:[]}` 无 message | 空句在 UI |
| `GET /capabilities` 治理 | `empty+message`「还没有目录项…」 | 有 |
| `GET /newapi/overview` 超管 | `empty_state` 71.2/71.3 | 有 |

### 8.3 越权残留（租户路径仍能碰到的平台面）

- `GET/POST/PATCH/DELETE /admin/users*` 仍 `require_admin` = `users.role==admin`（`admin.py:58-107`），**不是** `require_platform_admin`。租户公司管理员与平台超管在用户管理写面上仍可能同类。运营台 `/admin/tenants*` 已 404 同形（`admin.py:136-148`）。
- 回退 `_ROLE_PERMISSIONS["admin"]` 含 `menu:newapi`（`auth.py:114`）。
- 外部 `/spider/results/{task_id}` 未绑企业维（见 §3.2）。

### 8.4 断链（API 有、产品环没有）

1. 用量满额 CTA → 无后端 `href`；订单是另一资源，只读 403。
2. 线下订单 confirm 后改 `tenants.quota`（`billing_service.py:116-118`），用量页下一请求才看到；无事件 `quota_upgraded`。
3. 中转令牌签发成功但 **不能**打平台网关、不能拉数。
4. alias 公开能开、治理不能开、无 canonical。
5. 命令源侧收回、治理列表仍在。

---

## 9. 给下游（本帽不写表、不改 GWT、不代选）

| 给谁 | 内容 |
|------|------|
| `/pm` | 用 `state.yaml` 已决句改写 spec FR-50/60 stub 头，避免塑形再抄「Q-RELAY 未关则无渠道组」。FR-51 仍「下一轮」——现网无签发。四问保持开放。 |
| `/architect` | Wave 2 最小可卖环 = 用量下一步结构化 + 线下订单（已有）+ 只读文案。Wave 3 SKU 若声称可买，必须有「令牌真正能打网关」或公开标预告；禁止再扩表冒充履约。收 `GET /relay/groups` 副作用。入队 429/`QUOTA_EXCEEDED` 映射成与规划失败同一用户句。 |
| `/dba` | **不要**为本诊断加表。`040` 已够骨架。`idempotency_key` / `used_tokens` 是未接线列，不是缺列。 |
| `/frontend` | 用量 CTA、只读「找管理员」、安装空句目前在 UI；后端未给 `cta`。`menu:relay` 已回填；`menu:newapi` 回退仍危险。 |
| `/qa` | 补：viewer/operator 点申请提升的 oracle；租户 PUT `/newapi/.../config`（不要停在 GET）；GET `/relay/groups` 是否写库；能力端 33.4 `len==page_size`；治理列表是否含 `deleted_at` 行。 |
| `/qc` | 本文件是诊断不是放行。不要把 `test_billing_relay.py` 绿当成 FR-50/60 产品完成。 |

**本帽 open_questions（后端不能答）：** 无。Q-VOICE/PRICE/MARKET-USER/AGPL 不是本角色的题。
