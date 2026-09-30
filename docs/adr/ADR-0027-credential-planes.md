# ADR-0027：凭据平面（五种 Key 的边界、生命周期与执法点）

- **状态**：已采纳（2026-09-28）
- **决策依据**：D19 答复（2026-09-28）「中转 / 网关卖给企业：卖；按照建议执行」；审计 F6-8、BUG-28、B2-6
- **取代**：`CONTEXT.md` 中「中转令牌不发给租户」「租户渠道组 / 虚拟令牌仍待产品拍板」两句——D19 已拍板为卖，令牌按本 ADR 发放
- **相关**：ADR-0019（渠道组令牌经网关登记）、ADR-0020（出站拉数钥匙）、ADR-0025（中转 SKU 权益表）——三者在代码中被引用但文档未入库，本 ADR 汇总其约束，作为当前唯一的凭据真相源

## 背景

平台同时存在五种凭据，外观都是一串 Key，但用途、签发者与执法点完全不同。审计发现：

1. 同一个外部路由上并存两套鉴权函数；
2. 领域词汇表与实现冲突（文档说不给租户发令牌，代码已在发）；
3. 中转令牌的额度、渠道组停用、SKU 到期只在本地门控，网关上的 key 始终有效（BUG-28）；
4. 引用的 ADR 编号不在仓库里，新人无从判断某把 Key 能访问哪里。

## 决策

### 1. 五个凭据平面

| 平面 | 用途 | 签发者 | 持有者 | 存储 | 鉴权入口 | 吊销 | 到期 / 额度 | 审计事件 |
|---|---|---|---|---|---|---|---|---|
| **会话 JWT** | 后台与官网登录态 | `/auth/login` | 用户（浏览器） | 不落库（HS256 签名） | `Authorization: Bearer`，`deps.get_current_user` 每请求按库重算身份 | 停用账号 / 删账号即时失效（快照复查） | `JWT.EXPIRE_MINUTES` | `auth.login`、授权拒绝记录 |
| **租户 API Key**（`/api/v1/api-keys`） | 外部读数据（`/external/v1/public/spider/*`、`/stats`） | 企业 owner / admin | 企业系统 | SHA-256（明文只返回一次） | `X-API-Key`，`ApiKeyService.authenticate` | 软删 | 无（按需吊销） | `api_key.create` / `revoke` |
| **出站拉数钥匙**（`/api/v1/outbound/keys`，ADR-0020） | 按爬虫拉取本企业数据（`/external/v1/public/data/{spider}`） | 企业 owner / admin | 企业系统 | SHA-256 | `X-API-Key`，`OutboundKeyService.resolve_active_tenant`；其它平面的 Key 一律 401 并记 `wrong_plane_rejected` | 吊销即失效 | 无 | `outbound_key.*`、`wrong_plane_rejected` |
| **中转令牌**（`/api/v1/relay/tokens`，ADR-0019 / 0025） | 企业经平台 LLM 网关（LiteLLM）调用模型 | 企业 owner / admin，**须 SKU active** | 企业系统 | 本地 SHA-256（= LiteLLM token 列），网关持有虚拟 Key | 调用直达 LiteLLM，由网关鉴权；本地只做签发 / 观察 / 吊销 | 网关 `/key/delete` 在前、本地 `revoked_at` 在后；**不受 SKU 状态限制** | 令牌额度 `quota_tokens`、渠道组停用、SKU 到期、企业月度中转额度——**全部在网关侧以 block 执行**（见第 2 节） | `relay_token_call_succeeded`、`relay.*` 审计 |
| **平台 LiteLLM Key**（`/api/v1/litellm/keys`） | 平台自身调用网关（AI 规划、技能评分等） | 平台超管 | 平台后端 | LiteLLM 库 | LiteLLM | 超管删除 | 平台预算闸 `_budget_guard`（`LLM.BUDGET_FAIL_CLOSED`） | `litellm_key.*` |

**旧的平台静态 Key**（`API.KEY_BINDINGS`，`external_api/v1/public.py` 的 `validate_api_key` 分支）：退役中，仅为运维过渡保留，命中时记警告且无租户过滤。下线日期随 P1 排期确定，届时删除该分支。

### 2. 中转令牌的网关执法（BUG-28）

`backend/services/relay_enforcement.py` 把「令牌此刻应不应该被封」收成纯判定，再与网关对齐：

```
desired_block_reason(token) =
    sku_expired      若 SKU 非 active（含账期已过读时判到期）
    group_disabled   若所属渠道组停用
    tenant_quota     若企业本月中转用量 ≥ 企业月度中转额度
    quota_exhausted  若令牌 used ≥ quota_tokens（quota ≥ 0）
    None             其余
```

- `reconcile_tokens` 对比 `relay_tokens.blocked_reason`，差异时调用 LiteLLM `/key/block` 或 `/key/unblock`，幂等。
- 触发点：渠道组启停（strict：网关失败则整次不生效，返回 502）；令牌详情 / 批量刷新用量之后；中转续费之后；执法巡检（`RELAY.ENFORCE_INTERVAL_SECONDS`，默认 600 秒，未配置网关时不启动）。
- 吊销是止损操作，永远可用；SKU 非 active 时列表隐藏（GWT-U23.4），但对应 key 已在网关侧被封。

### 3. 计量

- 中转用量由网关 spend 日志按 (令牌, 业务日 Asia/Shanghai) 聚合写入 `relay_usage_daily`（与月度配额同一切日口径），只增不减；令牌 `used_tokens` 取单调累计。
- 企业月度中转用量与 LLM 月度 token **分开计**（D19）。额度：`tenants.quota.relay_tokens_month` 优先，否则 `RELAY.SKU_MONTHLY_TOKENS`（默认 10,000,000，运营参数）。
- 租户侧只显示 token，不显示平台成本（D19）；成本口径属运营侧。

### 4. 平面隔离的不变量

- 每种 Key 只能访问自己平面的端点；跨平面一律 401（出站拉数已有 `wrong_plane_rejected` 记录）。
- 明文只在签发响应里出现一次；库内只存 SHA-256；日志与事件不得出现明文。
- 平台超管不代企业签发任何企业平面的 Key。

## 后果

- 正面：泄露或超额的中转 key 会在网关侧失效；续费、重新启用、额度调整后自动解封；凭据边界有了单一文档。
- 代价：执法依赖巡检与网关可用性；巡检间隔内存在最多一个周期的超额窗口。网关不可用时，改组动作会失败而不是假成功。
- 待办：凭据矩阵测试（每种 Key 访问全部外部端点，断言只有本平面通过）列入 P1-1；旧平台静态 Key 下线日期待定。
