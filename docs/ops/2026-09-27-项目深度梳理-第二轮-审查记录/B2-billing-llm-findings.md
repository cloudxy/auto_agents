<!-- manager 落盘：2026-09-28，reviewer（G-fresh）最终交付原文逐字提取自其交付记录；packet 见 ../packets/ -->

# Findings：B2-billing-llm（计费、套餐、结账、支付、配额、用量、中转、出站 Key、LLM 提供方）

## Snapshot
- HEAD 82259f301c060dbf411424ec8775f29944e313e1（工作区只新增了 docs/ops/）
- explore_roots `git ls-files -s` sha256 d0205d9d4b9fe7c084c5b53175d9f531e125700a2effbe8b43349824c8e0fadd（由 manager 计算，本人只是照录）
- reviewer：sdlc-workflow:reviewer（G-fresh，只读），packet 为 `B2-billing-llm/packets/2026-09-27-2310-review-reviewer-B2-billing-llm.md`
- 核验方式：静态阅读 + 查看 manager 已记录的执行结果（`evidence/ui-runtime-summary.md`、`evidence/devdb-readonly.txt`）+ 看了 7 张截图。本人没有执行任何命令，没有一条结论是自己复现的。
- 第一轮 R1/R2 已报的问题不再重复。与它们相关的地方只做补充或更正，见末尾「对第一轮的补充/更正」。

**总评**：共 11 条，blocker 1 / major 6 / minor 4。

最严重的问题：**账期到期逻辑在生产中从没跑过**。付费档和中转 SKU 买一次等于永久有效。巡检组件 `TenantExpiryService` 定义了，但只有测试引用。如果照原样把它接上，结果会反过来：整个企业被锁在门外，连续费页面都打不开。

另外两处状态机缺陷：
- 待支付单没有取消或超时出口；超管确认时比对的是「现价」而不是下单快照，调价后单子卡死，还一直占着坑位。
- 中转令牌的额度、渠道组停用都没有在 LiteLLM 网关侧生效。

安全方面有一条新问题：租户经办（operator）可以把 LLM 供应商的 base_url 指向内网，形成 SSRF。原因是 `PROVIDER_BLOCK_PRIVATE_URL` 默认 false，prod 也没有覆盖。

**重点问题的回答**：超管打开 `GET /billing/checkout?product=plan_pro` 返回 400，这是设计如此（`CHECKOUT_SUPERADMIN_FORBIDDEN`），不是 bug。真正的问题在前端：定价页和用量页照样给超管显示「去结账」，点进去是死胡同（QA-B2-9）。租户 owner/admin 走 plan_pro 按代码应当返回 200，但没有运行期证据，需要 manager 复现（见验证 V1）。

---

## FINDINGS

### QA-B2-1 账期到期从不执行：付费档与中转 SKU 永不过期；若照原样接上巡检，会把整个企业锁死、无法续费
- Dimension: 1 / 2 / 8 / 9 | Severity: **blocker**（收费上线前必须修） | 工作量: M
- **现象**：确认收款后会写 `tenants.expires_at` 和 `tenant_subscriptions.current_period_end`，但没有任何生产代码读它们去降档。专业档（¥299/月）和中转 SKU（¥199/30 天）付费一次就永久有效。
- **触发条件**：任意租户完成一次 plan_pro 或 relay 履约，30 天后仍然是专业配额，SKU 仍然是 active。
- **根因**：
  - `backend/services/tenant_expiry_service.py:59-93` 定义了 `TenantExpiryService`。全仓 `*.py` 中引用它的只有 `backend/tests/test_product_events.py` 和 `backend/tests/test_saas_signup_expiry.py`，lifespan（`backend/app/__init__.py`）没有启动它。
  - `backend/services/billing_fulfill.py:62-63,72` 写入了到期时间。全仓唯一把状态写成 `expired` 的地方是 `tenant_expiry_service.py:50`；`TenantSubscription.status` 从来不会被改成 expired。
  - 中转 SKU：`backend/services/relay_sku_gate.py:69-76` 的 `load_sku_status` 只读 `row.status`，不比较 `period_end`；`backend/repositories/relay_sku_entitlement_repository.py:22-35` 只会写 `active`。
  - 如果把巡检接上：`tenant_expiry_service.py:44-51` 会把**企业**置为 `status=expired`，而 `backend/app/api/deps.py:100-104` 在每个请求上都调用 `assert_tenant_active` 并返回 401。到期企业因此连 `/billing/checkout` 都进不去，无法续费；配额也不会回到免费档。
- **后果**：现在是每个付费客户都 100% 漏收；接上巡检后则变成客户一到期就被锁在门外。两种状态都不能商用。另外 `test_saas_signup_expiry.py` 测的是一个从没被接上的组件，测试通过无法说明生产行为（空保证）。
- **修复方案**：
  1. 新建「订阅到期」巡检（复用 `platform_core/queues.py` 的 `distributed_lock`）：`current_period_end < now` 时把订阅置 `expired`，按免费档重写 `tenants.quota`（复用 `attach_free_plan` 的写配额逻辑），**企业 `status` 保持 active**。企业停用（disabled）与账期到期要彻底分开。
  2. 中转 SKU 在读取时就判到期（`status=='active' and period_end < now` 视为 `expired`），巡检同步落库，并在网关侧冻结该租户全部 key（见 QA-B2-6）。
  3. 删除或改写 `expire_overdue_tenants`，不再用账期去驱动 `tenant.status`。
  4. 确认「到期是否有宽限期、数据是否保留」：见 Q-B2-2。
- **应补测试**：时间旅行测试（freezegun）——履约后 +31 天跑巡检，断言配额回到 `DEFAULT_QUOTA`、订阅为 expired、企业仍能登录并打开结账页；SKU 过期后 `GET /relay/sku` 返回 `status=expired`。再加一条 lifespan 测试，断言巡检组件已注册。
- **核验方式**：静态（grep 引用关系）。执行验证见 V3。

### QA-B2-2 待支付单没有出口：没有取消/超时；确认比对的是「现价」而非快照，调价后永久卡死并占坑
- Dimension: 2 / 6 / 8 | Severity: **major** | 工作量: M
- **现象**：`checkout_pending` 只有两个出口：超管确认、在线通道的失败通知。线下单（channel 为 NULL）永远收不到通知；租户和超管都没有取消入口。运营只要调过价，超管确认就会一直报「确认金额与结账页不一致」，租户重新下单则一直 409「已有待支付」。
- **复现步骤**：
  1. 租户 owner `POST /billing/checkout {"product":"plan_pro"}`，得到 29900 的待支付单。
  2. `UPDATE plans SET price_cents=39900 WHERE slug='pro'`（中转则改 `AUTO_AGENTS_BILLING__RELAY_PRICE_CENTS`）。
  3. 超管 `POST /billing/orders/{id}/confirm` 返回 422 `CONFIRM_AMOUNT_MISMATCH`。
  4. 租户再次 POST 返回 409 `ORDER_PENDING_EXISTS`。
- **根因**：
  - `backend/services/billing_service.py:390-395` 拿 `order.amount_cents` 去比 `_amount_snapshot(product)`（现价）；`backend/repositories/order_repository.py:75-80` 的 CAS 也带着现价条件；`billing_service.py:400-407` 在 CAS 返回 0 行时同样抛这条文案。
  - 坑位唯一约束 `platform_core/models/billing.py:11-15,57`，冲突时返回 409（`billing_service.py:239-245`）。
  - 路由里没有取消接口（`backend/app/api/v1/billing.py`，module-inventory 列出 billing 共 10 个 op，没有 cancel）；`order_repository.py:15` 的 `_FAIL_FROM` 只由通道失败通知使用（`payment_notify_service.py:166-179`）。
  - 相关问题：通道未配置时下的单 channel 为 NULL，之后即使配好了通道也无法改走在线支付（`billing_service.py:328` 只处理 `order.channel in _ONLINE` 的情况）。
- **后果**：付款意愿明确的客户在该商品上永久卡住，只能手工改库；字段注释写着「下单时金额快照」，实际却以现价为准，与字段语义冲突。
- **修复方案**：
  1. 确认时以快照 `order.amount_cents` 为准；现价不同时在超管列表里并排显示「下单价/现价」，由超管决定，不再自动拒绝。
  2. 新增 `POST /billing/orders/{id}/cancel`（租户买方和平台超管可用），CAS `checkout_pending → unpaid(fail_reason='cancelled')`。
  3. 按配置自动过期待支付单（例如 `BILLING.PENDING_TTL_DAYS`，由巡检置为 unpaid/timeout）。
  4. 允许对 channel 为 NULL 的待支付单重新选择在线通道。
- **应补测试**：调价后确认成功且金额等于快照；取消后可以重新下单；超过 TTL 自动 unpaid；两个并发取消与确认只有一个生效。
- **核验方式**：静态。复现见 V4。

### QA-B2-3 「已验真待开通」单对超管不可见，确认时报错误文案，没有补偿；套餐行缺失时标成「已开通」但实际没开通
- Dimension: 2 / 8 / 9 | Severity: **major** | 工作量: S–M
- **现象与触发**：在线通道验真后，订单先提交为 `paid_pending_fulfillment`（`backend/services/payment_notify_service.py:140-146`），之后才履约。如果 `_fulfill` 抛异常（DB 抖动、租户行缺失，`billing_fulfill.py:49-53`），订单就停在该状态，只有通道**重复**通知才会补偿（`:163-164`）。
- **根因**：
  - `billing_service.py:349` 的超管待办只查 `checkout_pending/pending`，看不到 `paid_pending_fulfillment`。
  - 超管即使拿到订单号去确认，也走 `_confirm_checkout`，CAS 只接受 `checkout_pending`（`order_repository.py:17`），于是抛出「确认金额与结账页不一致」（`billing_service.py:404-407`），文案与真实原因无关。
  - `billing_fulfill.py:119-122` 找不到套餐时只打 warning 就 return；随后 `payment_notify_service.py:196-201` 仍把订单 CAS 为 `fulfilled`，结果是付了钱、标着已开通、实际什么都没开。
- **后果**：客户已付款但没开通，平台侧看不到，也没有正确的操作入口，属于资损与客诉风险。
- **修复方案**：
  - 超管列表加入 `paid_pending_fulfillment`，状态显示为「已付款待开通」；
  - `confirm_paid` 遇到该状态时直接调用幂等的 `_fulfill`；
  - `fulfill_checkout_product` 找不到套餐时抛异常，而不是静默返回；
  - 增加对账巡检，把停留超过 N 分钟的 `paid_pending_fulfillment` 单补一次履约。
- **应补测试**：mock `apply_plan_quota` 抛异常，断言订单停在 `paid_pending_fulfillment`、出现在超管列表、超管确认后变为 fulfilled；删除套餐行后通知，断言订单**不是** fulfilled。
- **核验方式**：静态。

### QA-B2-4 续费与换档语义错误：提前续费丢失剩余天数；企业档可被专业档降级覆盖；履约整块覆盖租户配额，还会回写平台价目表
- Dimension: 1 / 6 / 8 | Severity: **major** | 工作量: M
- **现象与根因**：
  - 续费：`billing_fulfill.py:62` 的 `end = now + 30d`，不是 `max(now, current_period_end) + 30d`。第 20 天续费会丢掉剩余 10 天。
  - 年付失效：`fulfill_checkout_product` 调用 `apply_plan_quota` 时没传 `period_days`，默认值 0，`:57,62` 的 `days or 30` 让 `period=year` 也只给 30 天。
  - 降级：结账没有「当前档位」校验（`billing_service.py:64-89,164-192`）。企业档租户买专业档，会立刻被 `billing_fulfill.py:127` 覆盖为专业配额（存储从 2,000,000 降到 200,000），而中转 SKU 仍然有效。
  - 配额整块覆盖：`billing_fulfill.py:55-56` 的 `tenant.quota = blob` 会丢掉 `result_retention_days`，以及运营通过 `tenant_admin_service` 单独调的值。
  - 回写目录：`billing_fulfill.py:123-126` 在租户 plan_pro 履约时改写平台价目 `plans.quota_json`，运营对专业档配额的修改会在下一单被静默还原。
- **后果**：续费客户吃亏；误操作即降级；运营配置被覆盖。
- **修复方案**：
  - 续费从 `max(now, current_end)` 起算，并传入 `plan.period`；
  - 结账预览返回当前档位，禁止同档之外的降级（或走 Q-B2-3 的规则）；
  - 配额合并只覆盖套餐管理的三个键；
  - 删除履约里写 `plans` 的代码，由迁移或运营台负责价目。
- **应补测试**：提前续费后到期日 = 原到期日 + 30 天；企业档买专业档被拒绝（或按规则处理）；运营改过的 `result_retention_days` 在履约后保留；履约前后 `plans` 行不变。
- **核验方式**：静态。

### QA-B2-5 定价页硬编码，与价目表和结账价不一致；企业档写着「定制」，按钮却直通结账
- Dimension: 6 / 9 | Severity: **major**（涉及定价这类战略决定） | 工作量: S
- **现象**：截图 `admin_pricing-1440.png` 中企业档显示「定制」，并配有「去结账」按钮。
- **根因**：
  - `frontend/admin/src/pages/Pricing.tsx:32-57` 把价格和权益写死（¥299/月、定制），没有调用已经存在的 `GET /billing/plans`（`billing.py:39-41`）。
  - 迁移 `backend/alembic/versions/047_w2_channel_null_pro_quota.py:38-39` 插入了 `enterprise` 99900、`is_public=1` 的价目行。
  - 因此存在两种结果：enterprise 行存在时，结账页显示并收取 ¥999（`billing_service.py:144-149,158-162`），与「定制」矛盾；行不存在时，预览不显示金额，提交后报 `CHECKOUT_PRICE_MISSING`，是死胡同。
  - dev 库 `plans` 行数估计为 2（information_schema 估计值，无法判断是哪两行），需要 V2 核实。
- **后果**：展示价与收费价不是同一个来源，存在误导或无法成交的风险；超管在后台改价后，定价页也不会跟着变（还会叠加 QA-B2-2 的卡单问题）。
- **修复方案**：定价页从 `/billing/plans` 读取；企业档如定为「定制」，则 CTA 改为「联系销售」并下架 enterprise 的 `is_public`；如定为标价，页面显示真实价格。见 Q-B2-1。
- **应补测试**：Pricing 页用 mock `/billing/plans` 渲染价格；`is_public=0` 的档位不出现结账按钮。
- **核验方式**：截图 + 静态。

### QA-B2-6 中转令牌额度与渠道组停用都没有在网关执行；SKU 非 active 时租户看不到、也吊销不了仍然可用的令牌
- Dimension: 4 / 8 / 9 | Severity: **major** | 工作量: M
- **现象**：`quota_tokens` 只存在本地，只起展示作用；组停用只影响新签发；SKU 一旦不是 active，令牌列表就返回空，吊销被拒绝，但网关上的 key 仍然有效。
- **根因**：
  - `backend/services/relay_service.py:369-384` 调用网关 `generate_key` 时没有带预算、有效期或阻断字段；`quota_tokens` 只写入本地（`:209`）。
  - `backend/services/relay_usage.py:48-58` 的 `apply_usage` 只回写用量；`relay_service.py:97-102` 的 `_token_status` 不考虑 `used >= quota`。
  - `relay_service.py:155-177` 组停用时不处理已签发的 key，只有 `:199-200` 拦住新签发。
  - `relay_service.py:235` 吊销前要求 SKU 为 active；`:179-182`、`:188` 在 SKU 不是 active 时列表返回 `[]`。
  - `config/default/relay.yml:12` 的窗口调度 `SCHEDULER_ENABLED: false`。
- **后果**：「令牌额度」只是摆设，租户可以无限消耗平台 LiteLLM 成本；泄露的 key 在 SKU 失效后租户吊销不了，也看不到，但它仍能调用。
- **修复方案**：
  - 签发时在 LiteLLM 上设置 `max_budget/budget_duration/tpm_limit`（LiteLLM 的预算以金额计，需要定义 token→金额的换算，或由巡检按观察到的用量 `key/update blocked=true`）；
  - 组停用、SKU 到期时批量 block 该组或该租户的 key；
  - 吊销和只读列表不受 SKU 状态限制（吊销是止损操作，必须始终可用）。
- **应补测试**：fake gateway 断言 `generate_key` body 含预算字段；组停用后对每个 key 调用 update/block；SKU 置 expired 后 `DELETE /relay/tokens/{id}` 仍返回 200，且网关收到 delete。
- **核验方式**：静态。V6 可以快速确认。

### QA-B2-7 LLM 供应商 base_url SSRF：私网拦截默认关闭且 prod 未覆盖，租户经办即可建连内网；只做静态校验，不解析 DNS
- Dimension: 4 | Severity: **major** | 工作量: S–M
- **现象与触发**：租户 operator 调 `POST /llm/providers {"base_url":"http://127.0.0.1:<port>/v1",...}`，再调 `POST /llm/providers/{id}/test`；服务端会向该地址发 POST，并把 `HTTP <code> <reason>` 或异常文本返回。
- **根因**：
  - `config/default/llm.yml:31` 为 `PROVIDER_BLOCK_PRIVATE_URL: false`，`config/` 下其他文件都没有覆盖（grep 只命中这一处）。
  - `backend/services/llm_secret_vault.py:84-92` 开关关闭时直接 return。
  - `platform_core/schemas/llm_provider.py:60-81` 只判断 host 字面量；遇到域名直接返回 False，所以 `*.nip.io` 这类解析到内网的域名，以及 DNS rebinding，都能绕过。
  - `backend/app/api/v1/llm_providers.py:152-163,219-230` 使用 `require_operator`，租户 admin 和 operator 都能通过；`:71-97` 的 probe 端点入参为 `body: dict`。
  - `backend/services/llm_probe_engine.py:88-110` 发送时不再校验，并把 `str(e)[:500]` 回显给调用方，可以当端口探测的判别依据。
  - 运行期 BYOK 调用同样会打到这个地址。
- **后果**：租户可以探测和访问平台内网 HTTP 服务（例如 LiteLLM admin、内部 API）。与 R1 QA-1（notify-config）、R2 QA-7（交付 webhook）是**同类第三处**，不算重复。
- **修复方案**：
  - prod 强制 `PROVIDER_BLOCK_PRIVATE_URL=true`，并在启动时校验；
  - 在所有出站 URL 上统一使用 `ai_planner/url_guard.py`：发送时解析 DNS、逐个 IP 校验，并用自定义 transport 固定已校验的 IP；
  - 私网地址只对平台超管开放；
  - 错误回显统一成「连接失败/超时」。
  - 三处 SSRF 合并用一个 `outbound_url_guard`，并在 `arch.sh` 加红线，禁止绕过它直接出站。
- **应补测试**：租户 operator 分别用 `127.0.0.1`、`10.x`、`localtest.me` 创建或测试，均被拒绝；平台超管在显式开关下允许。
- **核验方式**：静态。V5 只能在本机环境执行。

### QA-B2-8 出站拉数钥匙：经办可以吊销负责人签发的钥匙；无数量上限、无过期；成员离开后其签发的钥匙仍然有效
- Dimension: 4 / 8 | Severity: minor | 工作量: S
- **根因**：
  - `backend/services/outbound_key_service.py:38` 的 `_ISSUER_ROLES` 包含 operator；`:121-134` 允许吊销本企业任意钥匙。
  - `:90-119` 签发没有数量上限，也没有 `expires_at`。
  - `issued_by_user_id` 只记录，`resolve_active_tenant`（`:73-88`）不看签发人是否仍在职或有效。
- **后果**：离职的经办仍握有企业数据导出凭据；经办可以吊掉负责人的集成钥匙，造成停摆。
- **修复方案**：删除或停用成员时，列出该成员签发的钥匙，由负责人决定吊销（或默认吊销）；吊销他人签发的钥匙需要 owner/admin；每个企业设 active 钥匙上限（配置化）；可选过期时间。是否属于产品规则见 Q-B2-4。
- **应补测试**：operator 吊销 owner 签发的钥匙应被拒绝；第 N+1 把签发被拒绝；删除成员后其钥匙的状态。
- **核验方式**：静态。

### QA-B2-9 （重点问题）超管结账返回 400 是设计行为，但定价页和用量页照样给超管显示「去结账」，点进去是死胡同；GET 结账每次都写埋点
- Dimension: 6 / 9 | Severity: minor | 工作量: S
- **现象**：`ui-runtime-summary.md:49` 记录了 `400 GET /api/v1/billing/checkout?product=plan_pro`。截图 `admin_billing_checkout-1440.png` 整页只有一行「超管不能代企业支付」；`admin_pricing-1440.png` 和 `admin_usage-1440.png` 都给超管显示「去结账」。
- **根因**：
  - `backend/services/billing_service.py:134-138` 有意拒绝平台超管（`CHECKOUT_SUPERADMIN_FORBIDDEN`）。`BusinessException` 默认 `status_code=400`（`platform_core/exceptions/business.py:12`），策略性拒绝本应是 403。
  - 前端 `frontend/admin/src/pages/Pricing.tsx:62` 用 `tenant_role ∈ {owner, admin}` 判定买方，没有排除 `is_platform_admin`。超管在平台租户里是 owner，所以按钮可见。
- **租户是否也失败**：按代码不会。owner/admin 通过 `_assert_checkout_actor`；plan_pro 对应迁移 `040_billing_and_relay_sku.py:146` 的 `pro`/29900。经办/只读返回 `ORDER_ROLE_NOT_ALLOWED`，前端显示「联系管理员」（`Checkout.tsx:195-199`）。企业档见 QA-B2-5。**以上未经运行验证**，见 V1。
- **附带问题**：`billing_service.py:84-86` 在每次 GET 预览时都写 `checkout_story_started`；前端 `Checkout.tsx:116-121` 用的 react-query 默认在窗口重新聚焦时 refetch，会重复计数，放大漏斗入口指标。
- **修复方案**：`buyer` 判定加上 `!user.is_platform_admin`，超管的 CTA 改为「查看待确认订单」（指向 `/billing/admin/orders` 对应页面）；拒绝码改为 403；埋点按「会话 + 商品」去重，或改由前端在进入页面时报一次。
- **应补测试**：超管身份下定价页和用量页不渲染结账 CTA；多次 GET 预览只产生 1 条 `checkout_story_started`。
- **核验方式**：截图 + 已记录执行 + 静态。

### QA-B2-10 在目标数据面（LiteLLM）上，LLM 成本口径恒为 0；用量看板把内部维度名 "config" 直接给用户看
- Dimension: 6 / 9 | Severity: minor | 工作量: S–M
- **现象**：截图 `admin_usage-1440.png` 的「LLM 成本（本月 0.00 元）」表里，供应商显示 `config`，786 tokens，金额 0.00。
- **根因**：
  - `backend/services/ai_planner/llm_client.py:230` 网关路径的 `dim = usage_dim or "config"`，没有模型或单价信息；`backend/services/llm_usage_service.py:316` 的 `_cost_cents(total, unit_price_per_1k_cents)` 在缺单价时得 0。缺单价这一环是**推断，未逐行核实**。
  - 指标注册表里的 `llm_cost_cents_month`（module-inventory:317-322）在默认 `DATA_PLANE: litellm` 下没有意义。
- **后果**：成本看板和 R2 QA-8 的成本闸口径都失真，运营无法按成本定价。
- **修复方案**：网关路径记录真实模型名，并采用 LiteLLM 响应里的 `response_cost` 或 spend 日志作为成本；前端把维度名映射成可读名称（「平台网关 / 模型名」）。
- **应补测试**：网关路径调用一次后 `cost_cents > 0`（fake gateway 返回 cost）；看板不出现 "config" 字面量。
- **核验方式**：截图 + 静态（部分推断）。

### QA-B2-11 计费服务里的死代码与停用路由
- Dimension: 1 / 7 | Severity: minor | 工作量: S
- **根因**：
  - `backend/services/billing_service.py:263-290` 的 `_fail_unconfigured` 和 `:292-301` 的 `_assert_order_allowed` 在全仓（含 tests）没有调用方（grep 只命中定义处）。
  - `POST /billing/orders`（`billing.py:109-127`）永远返回 422 `ORDER_STORY_CLOSED`（`billing_service.py:303-313`），但依然挂载，并在异常前后写审计。
  - 前端 `confirmOrder`（`frontend/admin/src/services/billing.ts:101-102`）不发 body，后端 `expected_order_id` 的防误点校验（`billing_service.py:363-366`）因此永远不生效。
- **修复方案**：删除两个死方法；`/billing/orders` POST 加 `Deprecation`/`Sunset` 头后下线；前端确认时带上 `{order_id}`，让防误点校验生效。
- **核验方式**：静态（grep）。

---

## Dimensions checked
1. 标准符合 ⚠️：没有 spec，以代码自述和 docstring 为基线。自述与实现矛盾的地方：「巡检 lifespan 可选挂载」实际从未挂载（QA-B2-1）；「amount_cents 为下单时金额快照」实际按现价确认（QA-B2-2）；「plan_pro 永不写 SKU」成立。
2. 标准质量 ⚠️：订单状态机缺少取消、超时、待开通补偿三条迁移（QA-B2-2/3）；订阅没有 expired 迁移（QA-B2-1）；续费和换档没有定义（QA-B2-4）。
3. 证据有效性 ⚠️：`test_saas_signup_expiry.py` 测的是未接线的组件，是空保证（QA-B2-1）；运行期证据只有超管视角，缺租户负责人视角，租户结账是否 200 未验证（V1）。本人没有复现任何一条。
4. 安全 ⚠️：QA-B2-7（SSRF，租户可达）；QA-B2-6（泄露令牌吊销不了，额度不在网关执行）；QA-B2-8（钥匙生命周期）。确认做得好的点：LLM key 用 Fernet 且无主密钥时拒绝保存；出站和中转令牌只存 SHA-256、明文只返回一次；中转跨租户统一 404；平台行写入有守卫并记审计。
5. 性能 ✅（带说明）：本切片没有看到 N+1 或全表扫描。`list_pending_orders` 没有分页（`billing_service.py:343-356`），以当前量级可以接受；`observe_gateway_usage` 分页有上限（`relay_usage.py:33`）。
6. 契约一致性 ⚠️：定价页与价目表（QA-B2-5）、成本维度（QA-B2-10）、超管拒绝用 400（QA-B2-9）、确认防误点字段前端不发（QA-B2-11）。
7. 宪法合规 ⚠️：配置即代码被违反——定价页写死价格（QA-B2-5）；日志即证据基本满足（billing 和 relay 的 public 方法首行都有 logger.info，但 `BillingService.list_orders` 等以外，`_confirm_checkout` 失败分支没有 warning）。其余红线以 R1 引用的 arch 记录为准，未重跑。
8. 边界 ⚠️：并发确认靠 CAS 是正确的；但调价、到期、续费、降级、SKU 失效后吊销这些边界都有缺口（QA-B2-1/2/4/6）。
9. 产品价值与体验 ⚠️：核心承诺「按套餐付费、按账期计量」在代码里不能闭环（QA-B2-1/2/3）。截图显示超管在定价页和用量页会走进死胡同（QA-B2-9），成本看板恒为 0（QA-B2-10）；没有租户负责人视角的截图，租户侧结账体验➖（缺证据，不是不适用）。

## Strengths（改进时应保留）
1. **订单状态迁移全部走 CAS**，并有唯一约束兜底：`order_repository.py:59-107` 统一使用 `cas_status(from_statuses)`；`orders` 有 `uk_orders_tenant_open_product`（STORED GENERATED 坑位列）、`uk_orders_order_no`、`uk_orders_channel_trade`（`platform_core/models/billing.py:11-15,55-59`），重复确认和重复通知都是幂等空操作。
2. **两条验真前门共用同一状态机**：HMAC 夹具和真实网关 RSA2/APIv3 都汇入 `handle_verified_fields`（`payment_notify_service.py:60-89`），并做四要素核对（通道/单号/商户快照/金额，`:115-130`）；迟到通知只打标，不改状态（`:149-162`）。
3. **密钥卫生**：LLM key 用 Fernet 加密，未配置主密钥时拒绝保存，不会退化成明文入库（`llm_secret_vault.py:52-62`）；列表只返回掩码；出站和中转令牌只存 SHA-256 与前缀，明文只在签发响应里出现一次（`outbound_key_service.py:98-119`、`relay_service.py:203-222`）；查找用 `compare_digest`（`outbound_key_service.py:86`）。
4. **网关与本地的一致性顺序明确**：先在网关登记再落本地，本地失败则尽力作废网关侧 key（`relay_service.py:201-219`）；吊销时先作废网关、失败就不在本地假吊销（`:238-253`）；刷新用量是整批观察后再写，没有半批状态（`:305-332`）。
5. **租户隔离与越权形态一致**：中转跨租户、令牌凭证失败都返回 404（`relay_sku_gate.py:41-44`）；LLM 平台行写入有守卫并记审计（`llm_provider_service.py:69-101`）；激活互斥按租户分域（`llm_provider_repository.py:39-56`）。

## Improvement themes
- **T1 订阅生命周期闭环**（QA-B2-1、4）：目标是订阅有 active→expired→（续费）active 的完整迁移，到期只降档不锁企业，续费顺延，换档规则明确。落地顺序：① 规则拍板（Q-B2-2/3）→ ② 订阅到期巡检 + SKU 读时判到期（M）→ ③ 续费顺延与配额合并（S）→ ④ 删除 `expire_overdue_tenants` 的 tenant.status 语义（S）→ ⑤ 时间旅行测试和 lifespan 注册断言（S）。
- **T2 订单状态机补全**（QA-B2-2、3、11）：目标是每个非终态都有超时/取消出口，每个「已付款」都有补偿路径，并且对超管可见。顺序：确认按快照 → 取消接口 → 待开通纳入超管列表并可确认 → 对账巡检 → 待支付 TTL → 清理死代码。
- **T3 网关侧强制执行**（QA-B2-6、10）：目标是本地展示的额度、停用、到期都在 LiteLLM 侧有对应的阻断，成本以网关 spend 为唯一口径。顺序：吊销不受 SKU 限制（S，立即）→ 组停用/SKU 失效时 block key → 预算下发 → 成本口径改用 `response_cost`。
- **T4 统一出站 URL 守卫**（QA-B2-7，并收拢 R1 QA-1、R2 QA-7）：一个 `outbound_url_guard`（发送时解析 DNS + 固定 IP），加上 prod 启动期强制开关和 arch 红线。顺序：prod 开关 → 三处接入 → 红线。
- **T5 价目单一来源**（QA-B2-5、9）：定价页和官网读 `/billing/plans`，CTA 按身份（超管/买方/非买方）和价目状态（标价/定制）渲染；埋点去重。

## 待 manager 执行的验证（reviewer 未执行）
- **V1 租户结账**：用租户 owner 登录，执行 `curl -s -H "Authorization: Bearer $T" 'http://127.0.0.1:9111/api/v1/billing/checkout?product=plan_pro'`，预期 200 且 `amount_cents=29900`；把 product 换成 `plan_enterprise` 和 `relay`，记录 `amount_cents`；再用经办 token 执行一次，预期 `ORDER_ROLE_NOT_ALLOWED`。
- **V2 价目实表**：`SELECT slug,name,price_cents,period,is_public FROM plans; SELECT id,tenant_id,product_code,status,channel,amount_cents FROM orders;`
- **V3 到期未接线**：`grep -n "tenant_expiry\|TenantExpiry" backend/app/__init__.py`，预期无输出。
- **V4 调价卡单**（pytest，需要新写）：建待支付单 → 改 `plans.price_cents` → `confirm_paid` 预期 422 → 再 `create_checkout` 预期 409。
- **V5 SSRF**（只在本机执行，不要打生产）：租户 operator `POST /api/v1/llm/providers {"name":"ssrf","provider_type":"openai","base_url":"http://127.0.0.1:9111/api/v1","model":"x"}` → `POST /api/v1/llm/providers/{id}/test`，观察返回的 `error` 中的 HTTP 状态码。
- **V6 网关预算**：`grep -n "max_budget\|budget_duration\|blocked" backend/services/relay_service.py`，预期无输出。
- **V7 成本口径**：阅读 `backend/services/llm_usage_service.py:300-340`，确认 dim 为 "config" 时 `unit_price_per_1k_cents` 的来源。

## 对第一轮的补充/更正
- R1 QA-11（夹具通知通道在生产常驻）：补充一点，该通道用的是与真实网关同一份商户密钥（`payment_notify_service.py:107-113`），prod 关闭夹具通道的优先级应当提高。
- R1 QA-7（资金路径覆盖率低）：补充空保证实例——到期测试覆盖的是未接线组件（QA-B2-1）。
- R2 QA-8（LiteLLM 路径预算 fail-open）：与 QA-B2-6、QA-B2-10 同根，都是网关路径缺少执行与成本口径，建议在 T3 一并处理。

## Decisions
- 严重度按「影响面 × 必然性」判定：QA-B2-1 对每个付费客户必然发生，且直接破坏收费模型，定为 blocker；QA-B2-7 默认配置下租户可达，但限于内网 HTTP，定为 major。全部结论来自静态阅读、截图和已记录执行，没有声称复现。

## Open questions
- **Q-B2-1（战略，待确认）企业档怎么卖？** A 定为「定制」：页面 CTA 改为联系销售，enterprise 设 `is_public=0`，由超管线下建单（**推荐**，与当前页面和权益描述「协商/专属」一致）；B 标价 ¥999/月自助购买：页面改读价目表；C 两者都保留（标价 + 定制咨询）。
- **Q-B2-2（战略，待确认）账期到期后怎么处理？** A 降为免费档，数据保留，超出免费配额的写入被拒绝，可随时续费（**推荐**）；B 设 N 天宽限期后再降档；C 停用企业（当前 `expire_overdue_tenants` 的语义，不推荐：会连续费一起挡住）。
- **Q-B2-3（战略，待确认）续费与换档规则？** A 同档续费从原到期日顺延，升档立即生效并按剩余天数折算，降档在下个账期生效（**推荐**）；B 一律立即生效、不折算（当前行为）。
- **Q-B2-4（运营，已按默认处理）出站钥匙**：吊销他人签发的钥匙需要 owner/admin；删除成员时提示负责人处理其签发的钥匙，不自动吊销。

## Product-delta rows
- 无（产品层 `docs/product` 未建立）。

## Lesson rows（静态核实）
- L-B2-1：定义了巡检组件、写了测试，但没有接进 lifespan，结果测试全绿、生产零执行。后台组件应在注册表中登记，并用测试断言「已注册」，而不是只测函数本身（`tenant_expiry_service.py:59` 只被 tests 引用）。
- L-B2-2：用来防篡改的金额比对拿的是「现价」而不是快照，一次调价就能把状态机卡死。快照字段一旦存在，就应当是唯一事实源（`billing_service.py:390-395`）。
- L-B2-3：在本地门控（SKU/组状态/额度）上叠加外部网关时，只有网关侧也同步阻断，门控才真正生效；止损类操作（吊销）不能挂在权益门控后面（`relay_service.py:235`）。

```result
{
  "methods_used": [
    {"skill": "sdlc-workflow:findings", "reason": "packet primary_skill；9 维 G-fresh 审查格式与判定标准", "provenance": "reported"}
  ],
  "reported_reads": [
    "/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/evidence/module-inventory.md",
    "/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/evidence/ui-runtime-summary.md",
    "/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/evidence/devdb-readonly.txt",
    "/Users/xuyun/auto_agents/backend/app/api/v1/billing.py",
    "/Users/xuyun/auto_agents/backend/services/billing_service.py",
    "/Users/xuyun/auto_agents/backend/services/quota_service.py",
    "/Users/xuyun/auto_agents/backend/app/api/v1/relay.py",
    "/Users/xuyun/auto_agents/backend/app/api/v1/llm_providers.py",
    "/Users/xuyun/auto_agents/backend/app/api/v1/outbound_keys.py",
    "/Users/xuyun/auto_agents/config/default/billing.yml",
    "/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/evidence/screens/admin_billing_checkout-1440.png",
    "/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/evidence/screens/admin_pricing-1440.png",
    "/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/evidence/screens/admin_usage-1440.png",
    "/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/evidence/screens/admin_relay-1440.png",
    "/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/evidence/screens/admin_outbound-keys-1440.png",
    "/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/evidence/screens/admin_llm-1440.png",
    "/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/evidence/screens/admin_payment-credentials-1440.png",
    "/Users/xuyun/auto_agents/docs/ops/2026-09-27-项目深度梳理-审查记录/R1-backend-api-findings.md",
    "/Users/xuyun/auto_agents/docs/ops/2026-09-27-项目深度梳理-审查记录/R2-backend-services-findings.md"
  ],
  "unresolved": [
    {"id": "Q-B2-1", "owner": "operator/pm", "blocks": "QA-B2-5", "item": "企业档定制 vs 标价自助", "severity": "major"},
    {"id": "Q-B2-2", "owner": "operator/pm", "blocks": "QA-B2-1", "item": "账期到期处置：降档/宽限/停用", "severity": "blocker"},
    {"id": "Q-B2-3", "owner": "operator/pm", "blocks": "QA-B2-4", "item": "续费顺延与升降档生效规则", "severity": "major"},
    {"id": "V1", "owner": "manager", "blocks": "QA-B2-9 租户侧结论", "item": "租户 owner/经办 GET /billing/checkout 运行期结果未验证", "severity": "minor"},
    {"id": "V2", "owner": "manager", "blocks": "QA-B2-5", "item": "plans 实表行（enterprise 是否存在及价格）", "severity": "major"},
    {"id": "V7", "owner": "manager", "blocks": "QA-B2-10", "item": "_cost_cents 单价来源未逐行核实", "severity": "minor"}
  ],
  "proposed_changes": [
    {"target": "backend/services/tenant_expiry_service.py + backend/app/__init__.py", "change": "新增订阅到期巡检（降档不锁企业）并注册到 lifespan；SKU 读时判到期", "evidence_refs": ["backend/services/tenant_expiry_service.py:44-93", "backend/app/api/deps.py:100-104", "backend/services/relay_sku_gate.py:69-76", "backend/services/billing_fulfill.py:62-72"]},
    {"target": "backend/services/billing_service.py + backend/app/api/v1/billing.py", "change": "确认以快照金额为准；新增取消接口与待支付 TTL；paid_pending_fulfillment 纳入超管列表并可确认", "evidence_refs": ["backend/services/billing_service.py:349,372-373,390-407", "backend/repositories/order_repository.py:15-17,75-80", "backend/services/payment_notify_service.py:140-146,196-201"]},
    {"target": "backend/services/billing_fulfill.py", "change": "续费从 max(now,current_end) 顺延并传 plan.period；配额按键合并；删除回写 plans.quota_json；缺套餐时抛异常", "evidence_refs": ["backend/services/billing_fulfill.py:55-63,119-127"]},
    {"target": "frontend/admin/src/pages/Pricing.tsx", "change": "价格从 /billing/plans 读取；超管与定制档不显示结账 CTA", "evidence_refs": ["frontend/admin/src/pages/Pricing.tsx:32-62", "backend/alembic/versions/047_w2_channel_null_pro_quota.py:38-39"]},
    {"target": "backend/services/relay_service.py", "change": "签发时下发网关预算；组停用/SKU 失效时 block key；吊销与只读列表不受 SKU 限制", "evidence_refs": ["backend/services/relay_service.py:155-188,235,369-384", "backend/services/relay_usage.py:48-58"]},
    {"target": "config/prod/llm.yml + backend/services/llm_secret_vault.py", "change": "prod 强制 PROVIDER_BLOCK_PRIVATE_URL=true；发送时解析 DNS 校验并固定 IP；错误回显脱敏；与 webhook/notify 共用出站守卫", "evidence_refs": ["config/default/llm.yml:31", "backend/services/llm_secret_vault.py:84-92", "platform_core/schemas/llm_provider.py:60-81", "backend/services/llm_probe_engine.py:88-110"]}
  ],
  "product_delta": [],
  "lessons": [
    "后台巡检组件定义并测试但未注册进 lifespan，测试全绿而生产零执行；应断言组件已注册（tenant_expiry_service.py:59 仅被 tests 引用）",
    "存在金额快照字段却按现价确认，调价即卡死订单状态机并占坑（billing_service.py:390-395）",
    "本地门控叠加外部网关时，网关侧必须同步阻断；止损操作（吊销）不得挂在权益门控之后（relay_service.py:235）"
  ],
  "check_records": [
    "/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/evidence/ui-runtime-summary.md",
    "/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/evidence/devdb-readonly.txt"
  ]
}
```
