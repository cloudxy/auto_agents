# Findings — R1-backend-api（后端 API 与安全面）

## Snapshot
- HEAD: 82259f301c060dbf411424ec8775f29944e313e1（工作区干净）
- slice: `git ls-files -s` over explore_roots(backend/app backend/utils backend/services) + inputs → sha256 ea6fd2583054…（171 条），由 manager 计算
- reviewer: sdlc-workflow:reviewer（G-fresh，只读）；packet: ../packets/2026-09-27-1830-review-reviewer-R1-backend-api.md
- 方式：静态阅读 + 引用 evidence/ 已记录执行（arch / ruff / ruff-extended / pytest）；reviewer 未独立复现任何一条。

**总评**：13 条（blocker 2 / major 5 / minor 6）。最严重：`require_admin` 只判 `role=="admin"`，而每个租户 owner/admin 的 role 都是 `"admin"` → 平台全局面（审计日志、通知渠道 URL、死信队列）与部门 CRUD 对任意租户 owner 开放，部门 CRUD 可跨租户写。

---

## FINDINGS

### QA-1 `require_admin` 放行所有租户 owner/admin，平台全局面对自助注册企业开放
- Dimension: 4 安全 / 8 权限边界 | Severity: **blocker** | 工作量: M
- 违反义务：平台全局数据只允许平台超管访问（项目自述 `members.py:119-121`「平台审计全量仍在 /admin/audit-logs（平台超管）」）。
- Evidence（静态）：
  - 守卫只判 role 不判 `is_platform_admin`：`backend/app/api/deps.py:146` `require_admin = require_role("admin")`；`deps.py:135` `if user.role not in roles`。
  - 租户角色被映射为 `role="admin"`：`backend/services/tenant_signup_service.py:93` `role="admin", tenant_id=tenant.id, tenant_role="owner"`；`backend/services/member_service.py:106,137` `role="viewer" if tenant_role in ("viewer","operator") else "admin"`。
  - 入口匿名：`backend/app/api/v1/tenant_signup.py:63-90`（`POST /api/v1/public/tenant/signup`，无需登录，每 IP 每 15 分钟 5 次）。
  - 受影响端点：
    - `admin.py:136-156` `GET /admin/audit-logs`：`OperationLog` 不继承 TenantMixin（`platform_core/models/operation_log.py:7`），`audit_service.py:83-107` 不带租户过滤 → 任意企业可读全平台审计（含他租户用户名、操作、`tenant.update` body 等 detail）。
    - `admin.py:295-317` `PUT /admin/notify-config`：写全局 `system_configs`（`SystemConfig` 不继承 TenantMixin），URL 只校验 `http(s)://` 前缀（`admin.py:309`）→ 租户 owner 可把平台通知 webhook/钉钉/企微改到自己服务器（通知外泄）；服务端向任意地址发请求（含内网/元数据）→ SSRF。
    - `admin.py:232-271` `GET/DELETE /admin/dead-items`：全局 Redis 死信队列，可读他租户载荷、逐条丢弃或清空（销毁排障证据）。
    - `admin.py:320-340` `GET /admin/webhook-status`：泄露平台密钥配置状态（信息面）。
- 后果：匿名者「注册企业 → 登录」两步即可读全平台审计、劫持平台通知出口、清空死信——直接破坏 SaaS 核心隔离承诺。
- Suggestion：
  1. 上述 4 类端点立即改为 `require_platform_admin_or_404`（与同文件 `/users`、`/tenants` 一致）。
  2. `require_admin` 按原义重命名为 `require_legacy_role_admin` 或删除；新代码按平面选守卫：平台面 `require_platform_admin*`，租户面 `require_tenant_manager`。
  3. `notify-config` 加出站 URL 校验（拒绝私网/回环/链路本地，思路同 `ai_planner/url_guard.py`）。
  4. `tools/check/arch.sh` 加红线：挂在 `/admin/*` 下、或读写非 TenantMixin 全局表的路由禁止用 `require_admin` / `require_login`。
  5. 负向测试：每个端点以「租户 owner」身份断言 404。

### QA-2 `/rbac/departments*` 跨租户越权（IDOR）：列出/创建/改名/软删他企业部门
- Dimension: 4 / 8 | Severity: **blocker** | 工作量: S–M
- Evidence（静态）：
  - `backend/app/api/v1/rbac.py:157-206` 四个端点只挂 `require_admin`（同 QA-1，租户 owner 可过）。
  - `tenant_id` 直接取自 query/body：`rbac.py:159` `tenant_id: int`；`rbac.py:77-80` `DepartmentCreateRequest.tenant_id`。
  - `Department` 不继承 TenantMixin（`platform_core/models/department.py:12`）→ 行级注入与 before_flush 写断言都不生效。
  - Service 无归属校验：`backend/services/rbac_service.py:130-137` 只按传入 tenant_id 过滤；`:145-166` 可向任意存在的租户插入；`:168-178`、`:180-191` update/delete 只按 department_id 查询。
  - 现有测试把该行为当正确契约：`backend/tests/test_b1a_rbac_coverage.py:102-107` 用同一 `admin_client` 给租户 B 建部门并断言 201。
- 后果：租户 owner 可枚举他企业部门名，写入/改名/软删他企业部门，跨租户完整性被破坏。
- Suggestion：非平台超管一律用 `user.tenant_id`、忽略 body/query 的 tenant_id（仅平台超管可指定）；update/delete where 补 `Department.tenant_id == 当前租户`，跨租户 404 同形；`Department` 改继承 TenantMixin（列已存在且 NOT NULL，参照 `User` 覆盖列定义）；`test_b1a:102` 拆成「平台超管跨租户 201」「租户 owner 跨租户 404」两条。

### QA-3 公开 `/auth/register` 把匿名注册者放进共享 `default` 租户，身份为 operator
- Dimension: 4 / 9 | Severity: **major**（若 default 租户有真实业务数据应升 blocker，见 Q-R1-1） | 工作量: S–M
- Evidence：`backend/app/api/v1/auth.py:201-234` 注册端点无功能开关；`backend/services/auth_service.py:228-265` 注册者一律归入 `slug="default"` 租户、写 `tenant_role="viewer"` 但不设 `role`；`platform_core/models/user.py:48` `role` 默认 `"operator"`；`backend/alembic/versions/024_users_tenant_not_null.py:13,65` 历史 tenant_id 为 NULL 的非超管用户被回填到 default；`backend/app/api/v1/api_keys.py:30-41` `require_operator` 即可为 `user.tenant_id` 签发外部数据 API Key。限流失败方向不一致：`/auth/register` 用 `REGISTER_ATTEMPT_POLICY fail_open=True`（`rate_limiter.py:58-60`），企业注册用 `SIGNUP_RATE_POLICY fail_open=False`（`:63-66`）。
- 后果：所有自助注册个人共享一个租户，彼此采集任务/结果可见；能读到迁入 default 的历史账号关联数据，并可为该共享租户签发外部 API Key 导出数据。`role=operator` 与 `tenant_role=viewer` 不一致，同一人在不同守卫下权限不同。
- Suggestion：加开关 `AUTH.PUBLIC_REGISTER_ENABLED` 默认 false，引导走 `/public/tenant/signup`；若必须保留个人注册则每人独立租户；`role` 由 `tenant_role` 派生的逻辑收口为一个函数（注册/成员管理/企业注册共用）；注册限流改 fail-closed 并与 signup 共用 `enforce_request_limit`（感知 XFF）。

### QA-4 登录限流只按用户名计数、且在校验密码前生效：可锁定任意账号，挡不住撞库
- Dimension: 4 / 8 | Severity: **major** | 工作量: S–M
- Evidence：`backend/app/api/v1/auth.py:28-37,69,76` 先按 username `check_rate_limit`，失败后再按 username 计数；`rate_limiter.py:53-55` 15 分钟 5 次、`fail_open=True`；无 IP 维度。
- 后果：对 `admin` 等已知用户名连错 5 次即可让正确密码也被 429 拒绝 15 分钟（可持续锁号 DoS）；换用户名撞库不受限；Redis 故障时限流全失效。
- Suggestion：双维度——`(username, ip)` 负责失败锁定，IP 级负责总失败限流；密码正确的请求不受账号维度锁定（否则改递增延迟/验证码）；平台超管账号单独 fail-closed。

### QA-5 配额检查读 60 秒缓存计数、入队后不失效，突发提交可绕过并发与存储配额
- Dimension: 5 / 8 并发边界 | Severity: **major** | 工作量: M
- Evidence：`backend/services/quota_service.py:183` `_COUNT_CACHE_TTL = 60`；`:198-209` 缓存命中直接返回；`:222-241` `check_task_concurrency` 先检查后执行（check-then-act），无原子占位；全仓只有测试 `conftest.py:497` 清理 `quota:count:*`，业务代码无失效或自增。
- 后果：60 秒窗口内并发请求读同一旧计数 → 套餐「任务并发」「结果存储」上限可被突破，影响计费边界。下游 `spider_worker_gate` 是否有二次拦截未核实。
- Suggestion：并发配额原子占位（入队 INCR、终态 DECR，或 Lua check-and-incr）；或对租户行 `SELECT … FOR UPDATE` 后实时 COUNT；存储计数在结果回流后主动失效；补「并发 N+k 次入队只放行 N 次」测试。

### QA-6 lint 门禁基本空转，「All checks passed」掩盖 undefined-name 等正确性问题
- Dimension: 3 / 7 | Severity: **major** | 工作量: S（门禁）+ 视修复量
- Evidence：`pyproject.toml:63` `select = ["E9", "F401"]`；`evidence/ruff.txt:2`「All checks passed!」只在此窄规则集下成立；`evidence/ruff-extended.txt` 扩展规则下 F821 10、F811 6、F841 2、B904 20、ASYNC240 10、ASYNC230 2 处，另一条非法 `# noqa`（`platform_core/models/llm_provider_model.py:48`）。R10 偏宽：`evidence/arch.txt:14` 通过，但 `quota_service.py:222-225`（`check_task_concurrency`）、`:263-266`（`check_llm_tokens_month`）第一行不是 `logger.info`，只在末尾 `logger.debug`。
- 后果：F821 在触发路径上即运行时 NameError；ASYNC23x/240 阻塞事件循环；现有门禁输出不能证明这两类问题不存在。F821 具体位置未定位（ruff 默认也扫 scrapy/、run.py），**未验证**。
- Suggestion：`select` 至少扩到 `["E9","F","B","ASYNC"]`（E501、UP 放下一阶段），先清零 F821/F811/F841/ASYNC2xx；arch R10 改 AST 检查每个 public 方法第一条语句。

### QA-7 授权测试只按角色覆盖、不按租户覆盖；核心资金路径覆盖率低
- Dimension: 3 | Severity: **major** | 工作量: M
- Evidence：`backend/tests/test_t10_api_coverage.py:149-223` 只测 admin/operator/匿名，无「租户 owner（role=admin 非超管）」身份 → QA-1/QA-2 未被测出；`test_b1a_rbac_coverage.py:102-107` 把跨租户写当通过条件。覆盖率（`evidence/pytest.txt`）：`external_api/v1/payment_gateways.py` 30%（:116）、`payment_gateways/wechat_gateway.py` 50%（:212）、`payment_notify_service.py` 58%（:213）、`rbac_service.py` 47%（:240）、`tenant_admin_service.py` 51%（:255）、`app/__init__.py` 28%（:73）。总体 81.47% / 1954 passed（`pytest.txt:342,364`）属实，但掩盖了这些安全关键模块的薄弱。
- Suggestion：以 `backend/tests/openapi_routes_golden.txt` 为路由全集，建「路由 × 身份」授权矩阵测试（匿名 / 租户 viewer / 租户 operator / 租户 owner / 他租户 owner / 平台超管），期望状态表格声明，新路由无矩阵行即失败；补支付宝/微信真实通知验签分支（验签失败、金额不符、重复通知、状态闭集外）；安全关键模块单独覆盖率下限（如 ≥80%）。

### QA-8 多个写接口 `body: dict` 无 schema/长度约束，审计直接落原始 body
- Dimension: 4 / 8 | Severity: minor | 工作量: S–M
- Evidence：`admin.py:173,188`（POST/PATCH `/admin/tenants`）、`admin.py:297`（PUT `/admin/notify-config`）；`members.py:61,74,101`（创建成员、修改成员、重置密码）；审计原样落 body：`admin.py:196`（`detail=body`）、`members.py:82`；`admin.py:234` `/admin/dead-items` `limit: int = 100` 无上限（对比 `members.py:124` 手工夹取）。
- 后果：OpenAPI 契约缺失、前端只能手写类型；任意/超大字段进入 service 与审计表；若客户端误把密码类字段放进 patch body 会原样写审计。
- Suggestion：统一 `RequestBody` 子类，`extra="forbid"` + `Field` 长度约束；审计 detail 只写白名单字段；`limit` 统一 `Query(le=...)`。

### QA-9 遗留 newapi 面常驻挂载，与文档「默认关闭」不一致；命名漂移
- Dimension: 6 | Severity: minor | 工作量: S
- Evidence：`backend/app/api/v1/__init__.py:29` 无条件 `include_router(newapi.router, prefix="/newapi")`；`CLAUDE.md` 称「`/api/v1/newapi` … 遗留管控面，默认关闭」；`newapi.py:1-8` 已改作 LiteLLM 值班台，只注「一周期保留」，无下线日期/开关；残留命名 `rbac.py:43` `menu:newapi`「中转站管控」，`app/__init__.py:161-178` 用 `newapi_scheduler/newapi_probe` 承载 `RELAY.*`；同类漂移 `members.py:3`「viewer/operator 403」实际 `require_member_writer` 抛 `BusinessException(MEMBER_ROLE_NOT_ALLOWED)`（`members.py:39-42`）。
- 后果：该面有平台超管 404 守卫，不构成暴露；但文档/路径/变量三处说法不一，退役无抓手。
- Suggestion：新路径 `/api/v1/llm-ops`（或 `/duty`），`/newapi` 作为别名保留并带 `Deprecation` / `Sunset` 头与下线日期；同步 CLAUDE.md、菜单码、变量名，修正 members 注释。

### QA-10 外部 API 不经行级租户隔离、只靠显式传 tenant_id；遗留静态 Key 可跨租户读
- Dimension: 4 | Severity: minor（默认配置关闭） | 工作量: S
- Evidence：`backend/app/middleware/tenant_context.py:129-134` 只处理 Bearer JWT，X-API-Key 请求无 scope；`external_api/v1/public.py:121-141` 隔离仅依赖 tenant_id 显式传递；`public.py:37-39,158-159` 遗留静态 Key 得到 `tenant_id=None`，此时 `/spider/status|results/{task_id}` 可读任意租户任务，`/stats` 返回全平台统计。默认 `API_KEYS: []`（`config/default/external_api.yml:9`）、`API_KEY: ""`（`config/default/api.yml:33`）→ 默认关闭。
- Suggestion：Key 解析成功后经依赖进入 `tenant_scope(tenant_id)`，让 R13 行级注入兜底；给遗留静态 Key 定下线日期，之前 prod 配置遗留 Key 即启动失败（除非显式 `EXTERNAL_API.LEGACY_KEY_ACK`）。

### QA-11 支付通知细节：金额 float 解析、沙箱 HMAC 通道生产常驻、每次通知重建微信网关
- Dimension: 4 / 5 | Severity: minor | 工作量: S
- Evidence：`external_api/v1/payment_gateways.py:94-98` `int(round(float(yuan) * 100))`（`inf` 抛未捕获 `OverflowError` → 500 + 渠道重试；仅在验签通过后，可能性低）；`payment_gateways.py:131-136` 每次通知构造 `WechatGateway`（注释提到证书/网络）；`backend/app/api/v1/billing.py:87-96` `/api/v1/billing/notify/{channel}` 为自定义 HMAC 夹具通道（`payment_gateways.py:3-5` 称「沙箱/CI 用」），生产同样挂载。
- Suggestion：金额用 `Decimal` 精确到分；网关实例按凭据版本缓存；夹具通道由 `PAYMENT.FIXTURE_NOTIFY_ENABLED` 控制，prod 默认 false。

### QA-12 生产 CORS 为占位域名，启动期不拦截
- Dimension: 7 / 4 | Severity: minor | 工作量: S
- Evidence：`config/prod/web.yml:6-7` `https://your-domain.com`、`https://admin.your-domain.com`，并继承 `ALLOW_CREDENTIALS: true`（`config/default/web.yml:8`）；JWT/Webhook 密钥都有占位符拒启（`backend/utils/auth.py:13-18`、`backend/app/__init__.py:31-45`），CORS 无对称检查。
- 后果：部署漏改则前端全部跨域失败；若有人图省事改 `*`，与 credentials 组合形成风险。
- Suggestion：`_validate_runtime_secrets` 加一项：`APP_ENV=prod` 且 ORIGINS 含 `your-domain` / `localhost` / `*` 时拒启。

### QA-13 lifespan 中 9 个后台组件启停复制粘贴，停机顺序未与启动逆序绑定，覆盖率 28%
- Dimension: 6 / 8 | Severity: minor | 工作量: S
- Evidence：`backend/app/__init__.py:100-244` 9 段近似 try/except，停机顺序手写（如 consumer 最后才启动 LLM 用量聚合，却排在它之前停止，依赖未显式表达）；文件头称「不包含任何业务逻辑」，但 `:189-196` 执行 AI 计划对账；覆盖率 28%（`evidence/pytest.txt:73`）。
- Suggestion：组件注册表 `[(flag_key, default, factory)]`，按序启动、逆序停止，可单测；对账移到 service 启动钩子并修正文件头。

---

## Dimensions checked
1. 标准符合 ⚠️ — 无 FR/spec，以宪法与代码自述为基线；自述与实现不一致：members「403」、CLAUDE.md「newapi 默认关闭」（QA-9），members 注释「审计仅平台超管」vs `/admin/audit-logs` 实际守卫（QA-1）。
2. 标准质量 ➖ — review-only 代码审计，范围内无 GWT。
3. 证据有效性 ⚠️ — arch/pytest/ruff 记录含命令与退出码、可引用；ruff 规则过窄、R10 偏宽（QA-6）；授权测试缺租户维度且一条测试把 IDOR 当通过条件（QA-7）。
4. 安全 ⚠️ — QA-1、QA-2（blocker），QA-3、QA-4（major），QA-10/11/12（minor）。已确认正面项：JWT/Webhook 密钥 fail-fast、Webhook 带时间窗 HMAC、常量时间比较、平台面 404 同形并留越权审计。
5. 性能 ⚠️ — QA-5（缓存计数，同时是正确性问题）；`/admin/dead-items` limit 无上限（QA-8）；微信网关每次重建（QA-11）；已读范围未见 N+1。
6. 契约一致性 ⚠️ — QA-9、QA-13；`body: dict` 端点缺 OpenAPI 契约（QA-8）；错误信封经 `platform_core/exceptions/handlers.py:39-57` 统一处理（一致）。
7. 宪法合规 ✅（带说明）— `evidence/arch.txt` R1–R13、B1–B4、FR-14、PL 全过（已记录执行，非本人复现）；抽查输入范围内 API 层未 import ORM，rbac 已下沉 service；R10 弱点并入 QA-6。
8. 边界 ⚠️ — 权限 QA-1/2/3；并发 QA-5；超大/非法输入 QA-8/11；空值由 `platform_core/schemas` 负责，未发现缺口。
9. 产品价值与体验 ⚠️ — 非视觉切片，按 API 行为判断：本 SaaS 核心承诺「企业数据隔离、按套餐计量」，QA-1/2/3 破坏隔离承诺、QA-5 破坏计量承诺；修复前面向多企业开放自助注册会直接损害信任。

## Strengths（改进时应保留）
1. 密钥 fail-fast 对称防线：JWT 占位符导入期即抛错（`backend/utils/auth.py:13-18`）；Webhook 密钥与 LLM Fernet 主密钥启动期校验占位符与格式（`backend/app/__init__.py:31-69`）——建议推广到 CORS、遗留 Key、夹具通道。
2. claims 只承载身份，权限每请求从 DB 快照重算：`deps.py:94-114` 经 `load_auth_identity` 重载身份并校验租户到期/停用；中间件对平台超管 claim 做 DB 复核、失败即拒（fail-closed），撤销超管后立即降级（`middleware/tenant_context.py:105-152`）。
3. 行级租户隔离设计扎实：`with_loader_criteria` 读侧注入 + `before_flush` 写侧断言（`platform_core/tenant_context.py:113-169`）；豁免表只在组装层登记一次并由 R13 同步校验（`evidence/arch.txt:16`）——QA-2 的修复方向是「纳入」而非另起一套。
4. 外部回调与密钥比较规范：Webhook 签名 `HMAC(secret, "{ts}.{raw_body}")` + 时钟偏移窗口 + `compare_digest`（`external_api/v1/webhooks.py:31-50`）；API Key 按字节常量时间比较（`webhooks.py:111-113`）；平台面对非超管 404 同形并写越权审计（`deps.py:190-206`）。
5. 限流策略对象化、失败方向显式：`RateLimitPolicy` 写明 `fail_open` 与 `xff_mode="last"`，uvicorn 只信任 `FORWARDED_ALLOW_IPS` 内反代（`backend/app/core/rate_limiter.py:7-8,45-76`、`scripts/runlib/backend.py:88-89`）；门禁基线真实可用（1954 passed、81.47%、arch 全过）。

## Improvement themes
- **T1 授权模型两轴收口：平台 × 租户**（QA-1、2、3、7）— 目标：每个路由声明所属平面（platform / tenant / public / external），守卫由平面唯一决定；`role` 由 `tenant_role` 经唯一映射函数派生；带 tenant_id 的业务表一律继承 TenantMixin。顺序：① 当天热修 4 个 admin 全局端点与 departments 守卫、departments tenant_id 从身份推导（S）→ ② 关闭或隔离 `/auth/register`（S）→ ③ `Department` 纳入 TenantMixin（S）→ ④ 路由 × 身份授权矩阵测试（M）→ ⑤ arch.sh 平面守卫红线（S）。
- **T2 反滥用与计量原子性**（QA-4、5）— 目标：无鉴权写面一律 fail-closed 且 IP + 账号双维度；配额原子占位、与缓存解耦。顺序：登录双维度限流 → 并发配额原子化 → 存储配额写后失效 → 并发测试。
- **T3 输入契约与审计卫生**（QA-8、11、12）— 目标：所有写接口有 Pydantic 模型（`extra=forbid` + 长度约束）；审计只写白名单字段；金额一律 Decimal；prod 占位配置启动期拒绝。顺序：admin/members `body: dict` 模型化 → 审计白名单 → 支付金额 Decimal + 关夹具通道 → CORS 启动校验。
- **T4 门禁真实性**（QA-6、7）— 目标：门禁通过 = 正确性规则真实执行；安全关键模块单独覆盖率下限。顺序：ruff 扩 F/B/ASYNC 并清零 → R10 改 AST → 支付与 RBAC 补测至 ≥80% → CI 按模块设覆盖率下限。
- **T5 遗留面退役与命名一致**（QA-9、10、13）— 目标：每个遗留面有开关、下线日期与别名期响应头；文档/路径/变量一致；外部 API 进入 `tenant_scope`；lifespan 组件化。顺序：外部 API 进 tenant_scope + 遗留 Key prod 拒启 → newapi 改名 + Sunset → lifespan 注册表化。

## 待 manager 执行的验证（reviewer 未执行）
1. QA-6：`uv run ruff check --select F821,F811,F841,ASYNC230,ASYNC240 backend platform_core --output-format concise`
2. QA-1/QA-2 复现（本地 :9111 或 pytest + signup 夹具）：注册企业甲并登录 → 用其 token 调 `GET /api/v1/admin/audit-logs`、`PUT /api/v1/admin/notify-config {"webhook_url":"http://127.0.0.1:1"}`、`GET /api/v1/admin/dead-items`、`GET /api/v1/rbac/departments?tenant_id=<企业乙>`、`POST /api/v1/rbac/departments {"tenant_id":<企业乙>,"name":"x"}`；当前预期 200/201，修复后应 404。
3. QA-3：`POST /api/v1/auth/register` 后登录，看 `role`（预期 operator）与 `tenant_id`（预期 default）；`POST /api/v1/api-keys {"name":"x"}` 预期 201。
4. QA-5：确认 `backend/services/spider_worker_gate.py` 是否对租户级并发有二次原子拦截（有则 QA-5 降 minor）。

## Decisions
- 严重度 = 影响面 × 可达性：QA-1/2 从匿名企业注册两步可达、跨租户读写 → blocker；QA-3 取决于 default 租户现存数据 → 暂 major。全部基于静态阅读与已记录执行，未声称复现。

## Open questions
- **Q-R1-1（战略，待确认）** `/auth/register` 个人自助注册是否仍是产品一部分？A 关闭、只保留企业注册（**推荐**：企业注册链路已完整，个人注册是 SaaS 化前遗留）；B 保留但每人独立租户；C 保留现状（前提 default 租户无业务数据，需先盘点 prod）。
- **Q-R1-2（运营，已按默认）** `/api/v1/newapi` 改名后别名保留一个发布周期（2 个迭代）后移除。

## Product-delta rows
- 无（产品层未建立）。

## Lesson rows（静态核实）
- L-R1-1：SaaS 化后旧 RBAC `role=="admin"` 语义被租户 owner/admin 复用（`tenant_signup_service.py:93`、`member_service.py:106`），原「管理员专属」全局端点静默向所有企业开放；引入新身份轴时必须全量排查旧守卫使用点。
- L-R1-2：表不继承 TenantMixin（如 `Department`）时行级隔离不会自动兜底；路由允许调用方指定 tenant_id 即形成 IDOR。「有 tenant_id 列却无 TenantMixin」应作为 R13 检查项。
