<!-- manager 落盘：2026-09-28，reviewer（G-fresh）最终交付原文逐字提取自其交付记录（交付后该 agent 因 API 限流终止，不影响已交付内容）；packet 见 ../packets/ -->

# Findings — B1-identity-tenant（身份 / 租户 / 成员 / RBAC / 企业管理 / 系统设置）第二轮

## Snapshot
- HEAD：82259f301c060dbf411424ec8775f29944e313e1（工作区仅新增 docs/ops/）
- explore_roots `git ls-files -s` sha256：49c48df63620ff7a6a3c97d287862b33ea37302bae6b4fec9f73a2db3569d6e2（manager 计算，此处照录）
- reviewer：sdlc-workflow:reviewer（G-fresh，只读）；packet：`.sdlc/_review/2026-09-27-project-audit-r2/B1-identity-tenant/packets/2026-09-27-2310-review-reviewer-B1-identity-tenant.md`
- 核验方式：静态阅读，加上 manager 已记录的运行结果（`ui-runtime-summary.md`、`devdb-readonly.txt`）和截图（members / enterprise / settings / rbac）。**我没有独立复现任何一条**。每条需要 manager 执行的验证步骤写在该条的「核验」里。
- 交付路径：`/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/B1-identity-tenant/05-review/findings.md`（manager 落盘）

**总评**：共 12 条新问题（blocker 1 / major 5 / minor 6），与 R1 的 13 条不重复，另附 R1 的补充与更正 3 条。
- 最严重（blocker）：成员管理没有保护高权限目标。平台租户里任意一个租户 admin 都能重置平台超管的密码，接管整个平台；普通租户的 admin 也能接管 owner。
- 其次：会话寿命与「记住我（7天）」的说法不符；租户 operator 实际只有只读权限；企业到期状态机整体失效；测试套件把审计写进了 dev 库。

---

## FINDINGS

### QA-B1-1 成员管理不保护高权限目标：租户 admin 可重置 owner 或平台超管的密码、自封 owner，可接管账号
- Dimension：4 安全 / 8 权限边界 | Severity：**blocker**（平台租户场景）；普通租户场景单独看为 major | 工作量：S
- **现象**：`/api/v1/members*` 的写操作只保护「目标是 owner」的角色变更、停用和删除。重置密码不看目标是谁；任命 owner 不受限；目标是平台超管时没有任何保护。前端隐藏了这些入口（`Members.tsx:151` 下拉里没有 owner，`:167` owner 行不给操作），但后端照单全收。
- **触发条件 / 复现步骤**：
  1. 平台超管在 /members 点「添加成员」，在平台租户里建一个 `tenant_role=admin` 的同事。截图显示超管确实能看到这个按钮（`admin_members-1440.png`）。
  2. 用这个同事的账号调 `GET /api/v1/members`，结果里会包含超管本人（超管的 DB 行挂在平台租户下，见 `deps.py:50-52` 注释）。
  3. 调 `POST /api/v1/members/<超管id>/reset-password {"new_password":"xxxxxx"}`，按代码返回 200。
  4. 用新密码登录超管账号，拿到 `is_platform_admin=true`。
  - 普通租户同理：租户 admin 可以重置 owner 的密码，或者 `PATCH /members/<自己id> {"tenant_role":"owner"}` 自封 owner；`POST /members {"tenant_role":"owner",...}` 也能直接建出第二个 owner。
- **根因**：
  - `backend/services/member_service.py:148-161`：`reset_password` 只校验同租户和未删除，不看目标的 tenant_role、`is_platform_admin`，也不看操作者和目标的层级。
  - `member_service.py:25,72-75`：`TENANT_ROLES` 里有 owner，`create_member` 允许直接建 owner。
  - `member_service.py:128-137`：只有目标「当前是 owner」时才禁止改角色，所以把任何人（包括自己）改成 owner 都能通过。
  - `member_service.py:39-44`：`_reject_platform_role` 只拦「设为超管」，不拦「修改超管」。
  - 守卫只分两档（owner/admin 对其他人），没有层级：`members.py:33-43`。
- **后果**：
  - 平台租户内的非超管 admin 可以接管平台超管，拿到全平台控制面（租户、支付凭证、LLM 密钥）。
  - 普通租户里，admin 可以把 owner 锁在门外，或者自封 owner。之后按 `:133`、`:139`、`:180` 的 owner 保护规则，这个人无法被降级、停用或删除，「租户唯一所有者」这个不变量被破坏。
- **修复方案**：
  1. 在 `member_service` 里收口一个 `_assert_can_manage(actor, target)`，所有写操作共用：
     - 目标 `is_platform_admin` → 404 同形（租户面不管超管）。
     - 目标是 owner → 只有 owner 本人能改，且只能改自己的密码。
     - admin 只能管 operator/viewer；管 admin 需要 owner（这是 Q-B1-1 的推荐选项）。
  2. `TENANT_ROLES` 拆成「可分配角色（admin/operator/viewer）」和「owner」两组。owner 只能通过单独的「转让所有权」流程变更（owner 发起、目标确认、原 owner 降为 admin），不允许经 create/patch 设置。
  3. `reset_password` 需要把 actor 传进来（路由 `members.py:108` 补 `actor=user`）。
- **应补测试**：`test_saas_members.py` 增加这几条负向用例，全部期望 403/404：
  - 平台租户 admin 重置超管密码
  - 租户 admin 重置 owner 密码
  - 租户 admin 把自己 PATCH 成 owner
  - 租户 admin 用 POST 建 owner
  - 另加一条 owner 转让的正向用例。
- **核验**：静态。manager 请在一次性库或 pytest 夹具里按上面第 1–4 步执行，**不要在 dev 库上跑**。当前预期全部 200/201，修复后应为 403/404。

### QA-B1-2 「记住我（7天）」与实际会话寿命不符：不勾选时刷新即登出，勾选也只有 30 分钟，没有续期
- Dimension：9 产品体验 / 6 契约 / 8 边界 | Severity：major | 工作量：M
- **现象**：
  - 不勾选「记住我」：刷新页面或新开标签页，登录状态立即丢失。manager 的运行记录第 3 行、第 14–36 行显示，第一轮未勾选时，所有租户页都跳回了 /login。
  - 勾选：页面写着「7天」，但令牌 30 分钟就过期，也没有刷新接口。30 分钟后的第一个请求返回 401，前端整体登出。
  - 平台专属页（/users、/settings、/enterprise、/rbac 等）在未登录时不跳登录，而是显示 404 页（运行记录第 19、20、30、33–36 行的最终 URL 停在原路径）。超管刷新之后会落在一个「页面不存在」的死胡同。
- **触发条件**：
  - 登录时不勾「记住我」，然后按 F5。
  - 或者勾选登录后空闲 30 分钟，再点任意操作。
- **根因**：
  - `frontend/admin/src/store/useAuthStore.ts:45-46`：`partialize` 在 `rememberMe=false` 时返回 `{}`，令牌只存在内存里。
  - `frontend/admin/src/pages/Login.tsx:195`：文案写的是「记住我（7天）」。
  - `config/default/jwt.yml:12`：`ACCESS_TOKEN_EXPIRE_MINUTES: 30`，prod/local/dev 都没有覆盖（已 grep config/）。
  - 认证路由只有 login/permissions/menus/register 四个（`module-inventory.md:44-48`），没有 refresh。
  - `frontend/admin/src/components/ProtectedRoute.tsx:26-27`：未登录时，`requirePlatformAdmin` 路由直接渲染 NotFound。
- **后果**：每个管理员最多 30 分钟就被打断一次，未保存的表单（企业编辑、角色矩阵）会丢失。RBAC 页的提示文案「保存后用户刷新页面即生效」（`admin_rbac-1440.png`）对没勾「记住我」的用户来说，等于「刷新就登出」。
- **修复方案**：
  1. 不勾选时改用 `sessionStorage` 持久化（zustand persist 的 `storage: createJSONStorage(() => rememberMe ? localStorage : sessionStorage)`），刷新不丢，关闭浏览器才失效。
  2. 按 Q-B1-2 定会话策略。推荐方案：access token 30 分钟 + refresh token（记住我 7 天，不勾选则按会话），新增 `POST /auth/refresh`，在 axios 401 拦截里先尝试刷新一次再登出。如果不做 refresh，至少把文案改成真实时长。
  3. 未登录访问平台页时，NotFound 上加一个「去登录」入口。所有 404 都带这个入口，所以不会泄露页面是否存在，GWT-07.3 仍然成立。
- **应补测试**：
  - `useAuthStore` 单测：`rememberMe=false` 时写入 sessionStorage，不写 localStorage。
  - Playwright：登录不勾选、reload 后仍在 /dashboard；把 `ACCESS_TOKEN_EXPIRE_MINUTES` 设为 1 跑 E2E，过期后自动续期，无感知。
- **核验**：静态 + 已记录执行（运行记录第 3 行）。30 分钟过期这一点需要 manager 用 `ACCESS_TOKEN_EXPIRE_MINUTES=1` 复现。

### QA-B1-3 成员页可以停用或降级自己，截图里平台超管自己那一行的危险控件全部可用
- Dimension：8 边界 / 9 体验 | Severity：major | 工作量：S
- **现象**：`admin_members-1440.png` 里，平台超管 admin 自己那一行显示了可编辑的角色下拉、启用开关、「重置密码」和「删除」。开关一点就生效，没有二次确认。
- **触发条件**：在 /members 点自己行的开关（停用），或者把下拉改成 viewer。
- **根因**：
  - 前端 `frontend/admin/src/pages/Members.tsx:145,159,167` 只对 owner 行特殊处理，不识别当前用户。
  - 后端 `member_service.py:128-142` 的 `patch_member` 不校验 `member_id == actor_id`；路由 `members.py:81` 也没有传 actor。
  - 对照：平台用户服务有防自锁（`backend/services/user_service.py:219-227`「不能停用自己」「不能降级自己的 admin」）。成员服务没有对齐。删除有自检（`member_service.py:182-183`），但前端仍然显示删除按钮。
- **后果**：
  - 停用自己后，下一个请求就 401（`deps.py:97-98`）。再登录时，`authenticate` 把停用账号当作「用户名或密码错误」（`auth_service.py:111-118` 返回 None，`auth.py:74-77`），提示文案还会误导。如果这是唯一的超管，只能直接改库恢复。
  - 降级自己到 viewer 时，超管的 `role` 被写成 viewer（`member_service.py:137`），所有 `require_admin/require_operator` 端点对他返回 403（平台专属面仍可用，因为看的是 `is_platform_admin`）。
- **修复方案**：
  1. 后端 `patch_member` 增加 `actor_id` 参数，禁止停用或降级自己，文案对齐 user_service。
  2. 前端：自己那一行只读，显示「当前账号」。停用操作改为 Popconfirm 二次确认。
  3. 与 QA-B1-1 一起，把平台超管从租户成员列表中排除，或者只读展示。
- **应补测试**：API 层自停用、自降级返回 422；`Members.test.tsx` 断言当前用户行不渲染 Switch、Select 和删除按钮。
- **核验**：截图 + 静态。

### QA-B1-4 租户 operator 实际只有只读权限：role 与 tenant_role 有四套映射，彼此不一致
- Dimension：1 标准符合 / 6 契约一致 / 9 产品价值 | Severity：major | 工作量：S–M（含存量数据修正）
- **现象**：成员页建成员时写着「operator（可操作任务）」（`Members.tsx:221`）。但这样建出的成员 `role="viewer"`，所以：
  - 所有 `require_operator` 端点（43 处：`spiders/tasks.py:93,123` 修改和控制任务，以及 ai、templates、schedules、definitions、api_keys、llm_providers）都返回 403。
  - `/auth/permissions` 按 `user.role` 下发，给的是 viewer 权限码（`auth.py:136-143`），没有 `btn:create`。
  - RBAC 页「操作员 operator」那一行勾选的 11 项权限（`admin_rbac-1440.png`）对租户 operator 完全不生效。
- **触发条件**：owner 在 /members 建一个 operator 成员，这个成员登录后尝试编辑或暂停任务、创建 AI 方案。
- **根因**：role 由 tenant_role 派生，但散落在 4 处，每处规则不同：
  - `backend/services/member_service.py:106,137`：`role="viewer" if tenant_role in ("viewer","operator") else "admin"`，operator 被降成 viewer。
  - `backend/services/user_service.py:221-224`：平台用户页反过来把 `tenant_role = role` 原样复制，operator 在这里是真 operator，而且会**覆盖 owner**。平台超管编辑某租户 owner 的角色时，owner 会消失。
  - `user_service.py:237`：跨租户迁移时 `tenant_role = user.role or "operator"`，owner 迁出后原租户没有 owner。
  - `backend/services/tenant_signup_service.py:93`：owner 映射为 `role="admin"`。
  - `auth_service.py:264` 加上 `platform_core/models/user.py:48`：公开注册得到 `tenant_role=viewer`、`role` 默认 operator（R1 QA-3 已提到）。
- **后果**：
  - 「可操作任务」这个卖点对租户不成立。
  - 同一个 tenant_role 从不同入口建出来，权限不同。
  - RBAC 矩阵按 role 维度设计，租户 owner 和平台超管共用同一条「管理员 admin」（21 项，含 menu:users/settings/platform-ops），改其中一方就会影响另一方。
- **修复方案**：
  1. 在 `platform_core` 或 `backend/services` 新增唯一函数 `derive_legacy_role(tenant_role) -> str`（owner/admin→admin，operator→operator，viewer→viewer），4 处统一调用。
  2. user_service 改角色时不得覆盖 owner（owner 只能走转让流程）；跨租户迁移时，被迁的人如果是 owner，必须先转让。
  3. 迁移修正存量数据：`UPDATE users SET role='operator' WHERE tenant_role='operator' AND role='viewer' AND is_platform_admin=0`（先 SELECT 计数）。
  4. 长期方向（接 R1 T1）：`/auth/permissions` 改为按 (平面, tenant_role) 取矩阵。
- **应补测试**：以租户 operator 身份执行 `PATCH /spiders/tasks/{id}`，期望 200；`GET /auth/permissions` 包含 `btn:create`。平台用户页改 owner 的角色期望被拒。
- **核验**：静态。manager 请复现：建 operator 成员 → 登录 → `GET /api/v1/auth/permissions`（预期现在返回 viewer 那套）→ `POST /api/v1/spiders/tasks/<id>/control`（预期现在 403）。

### QA-B1-5 企业到期状态机整体失效：巡检从未启动，续期和支付都不恢复状态，界面无法清除到期时间
- Dimension：1 / 8 状态流转 / 9 | Severity：major | 工作量：M
- **现象**：
  - 设了 `expires_at` 的企业，过期后依然可以正常登录和使用。
  - 反过来，一旦状态变成 expired（目前只能手工改），在运营台设一个新的未来到期日不会恢复访问；支付履约只延长 `expires_at`，也不恢复访问。
  - 运营台表单写着「到期时间（留空=不过期）」，但清空后保存不起任何作用。
- **触发条件**：
  - `PATCH /api/v1/admin/tenants/{id} {"expires_at":"2020-01-01T00:00:00Z"}` 后，用该租户成员登录，按代码仍然成功。
  - 或者先把 status 设为 expired，再设一个未来的 `expires_at`（或确认一笔付费订单），该租户仍然被拒绝登录。
- **根因**：
  - `backend/services/tenant_expiry_service.py:59-93`：`TenantExpiryService` 在整个仓库里没有被实例化或启动（grep `TenantExpiryService(` 和 `expire_overdue_tenants(` 只命中服务自身和测试 `test_saas_signup_expiry.py:247`、`test_product_events.py:207`）。注释 `:60` 写「默认手动/登录时触发」，但登录路径并不会触发。
  - `tenant_expiry_service.py:27-37`：`assert_tenant_active` 只看 `status`，不看 `expires_at`。
  - `backend/services/tenant_admin_service.py:126-132`：只有「清空 expires_at」才会把状态恢复为 active；设了新日期，状态不变。
  - `backend/services/billing_fulfill.py:58-63`：付费履约写了 `tenant.expires_at`，但没有写 `tenant.status`。
  - `frontend/admin/src/pages/PlatformOps.tsx:54`：只有选了日期才发送 `expires_at`，清空不发送，所以 `:231` 写的「留空=不过期」和后端 `:130-132` 的「清除=续期恢复」分支从界面上走不到。
  - `auth_service.py:167-179` 和 `auth.py:79` 的 `assert_tenant_login_allowed` 与 `assert_tenant_active` 重复，并且只认 expired。
- **后果**：套餐到期不会被执行（收入漏洞）。一旦把巡检接上，已付费续期的客户会因为 status 不恢复而被锁住。截图 `admin_enterprise-1440.png` 里所有企业都是「不过期」，说明这条路径从没在真实数据上跑过。
- **修复方案**：
  1. 以 `expires_at` 作为真相，读取时计算状态：`effective_status = disabled if status=='disabled' else ('expired' if expires_at and expires_at < now else 'active')`，`assert_tenant_active` 用这个结果判断，巡检只负责回写和发事件。
  2. 如果保留巡检，就在 lifespan 里按配置开关 `TENANT.EXPIRY_PATROL_ENABLED` 启动（默认 true）。
  3. `patch_tenant` 在 `expires_at > now` 且当前 status 为 expired 时恢复为 active；`billing_fulfill` 同样处理（disabled 不自动恢复）。
  4. PlatformOps 清空日期时发送 `expires_at: null`。
  5. 删除 `assert_tenant_login_allowed`，统一走 `assert_tenant_active`。
- **应补测试**：
  - 过去日期 + active → 登录返回 401 `AUTH_TENANT_EXPIRED`。
  - expired + 设未来日期 → 可以登录。
  - 付费履约后 status 为 active。
  - PlatformOps 单测：清空日期时 payload 包含 `expires_at: null`。
- **核验**：静态（grep 结果如上）。manager 请在一次性库执行上面的触发步骤。

### QA-B1-6 测试套件把审计日志写进了 dev 库；租户审计按 actor_id 归因，测试行被算到平台租户名下
- Dimension：3 证据有效性 / 4 审计完整性 | Severity：major | 工作量：S
- **现象**：`admin_members-1440.png` 的「成员操作审计（本租户）」里出现了 `m-owner` 的 `member.create`、`member.delete`，对象都是 `user#4`，时间是 2026/9/17 16:31、16:35 和 9/27 18:23:58，每次创建和删除都在同一秒。`m-owner` 是测试夹具的用户名（`backend/tests/test_saas_members.py:28`）。夹具在一个全新的库里依次建 m-owner、m-viewer、m-other，所以测试里新建的成员 id 总是 4，与截图吻合。dev 库 `operation_logs` 共 824 行（`devdb-readonly.txt:6`）。
- **触发条件**：在本机 `APP_ENV=local`（`conftest.py:35`）下运行 pytest，并且在某个请求路径中触发了 DBManager 的惰性初始化。
- **根因（静态推导，需复现确认）**：
  - `backend/tests/conftest.py:396-397` 只注入了 `async_engines["DEFAULT"] = test engine`，没有把 `_ready` 置为 True。
  - `conftest.py:460` 每个测试开始前又把 `_ready` 置为 False。
  - 请求中任何 `get_redis`、`get_async_session`、`get_mysql` 调用（`platform_core/db.py:147,166,176`）都会触发 `init_all()`，`platform_core/db.py:96` 用真实 dev MySQL 引擎**覆盖**了注入的 DEFAULT。
  - 之后 `record_audit_standalone` 按 `backend/services/audit_service.py:30-31` 取 DEFAULT，写进了 dev 库。
  - 归因问题：`OperationLog` 不存 tenant_id，租户视角用 `JOIN users ON actor_id` 按当前租户过滤（`member_service.py:209-216`）。测试库的 actor_id=1 在 dev 库里对应平台租户的 admin，所以测试行出现在平台租户的审计里。
- **后果**：
  - dev 或共享库的审计证据被测试数据污染，排障和合规审计都不可信。
  - 同一机制也可能让测试读到真库的配置，`conftest.py:440-448` 已经记录过这种风险，包括发起真实付费的 LLM 调用。
  - 审计行不带租户，只要用户 id 重用或错配，就会跨租户展示。
- **修复方案**：
  1. conftest 注入 DEFAULT 后设置 `manager._ready = True`；或者给 `init_all` 加一条：pytest 下遇到已注入的键不覆盖。
  2. pytest 下如果解析出的 MySQL DB 名不是测试 schema，直接 fail（护栏）。
  3. `OperationLog` 增加 `tenant_id` 列，写入时从 `CurrentUser.tenant_id` 固化，租户视角改为按列过滤。
  4. 清理 dev 库里的污染行（先 SELECT 确认）。
- **应补测试 / 核验命令**（manager 执行）：
  - `SELECT id, actor_id, actor_name, action, target, created_at FROM operation_logs WHERE actor_name LIKE 'm-%' ORDER BY id DESC LIMIT 20;`
  - 记下计数，运行 `uv run pytest backend/tests/test_saas_members.py -q`，再查一次计数。计数增加即可确认。
  - 修复后加一个回归测试：跑完测试后断言真库计数不变，或者断言 `get_manager().async_engines["DEFAULT"].url` 是测试 schema。
- **核验**：截图 + 静态。根因链需要上面的命令确认。

### QA-B1-7 登录时先拉权限、后存令牌：/auth/permissions 不带令牌返回 401，并触发全局登出回调
- Dimension：6 / 8 | Severity：minor | 工作量：S
- **现象**：每次登录都有 `401 GET /api/v1/auth/permissions`，console 报错（运行记录第 13、37 行）。之后页面靠 `usePermission` 的 effect 再拉一次才恢复。
- **根因**：
  - `frontend/admin/src/store/useAuthStore.ts:25-28` 调用 `refreshPermissions()` 时，`:29` 的 `set({token})` 还没执行。
  - 请求拦截器从 store 取令牌，此时为空（`services/api.ts:13`）。
  - 返回 401 后，`api.ts:14-18` 的 `onUnauthorized` 执行 `logout()`（异步清空权限缓存）；因为当前在 /login，所以不跳转。
  - `hooks/usePermission.ts:26-28` 把 `loadState` 置为 'error'，`:64-69` 再补拉一次。
  - 同一行运行记录里的 antd 警告「Static function can not consume context」来自 `Login.tsx:124` 的静态 `message.success`。
- **后果**：每次登录都多一个 401 和一次多余的权限请求，菜单短暂处于「权限加载中」，日志和监控被噪声污染。在登录流程里触发全局登出回调也很脆弱：以后只要登录流程不在 /login 路径上，就会被直接登出。
- **修复方案**：先 `set({token, user, isAuthenticated, rememberMe})`，再 `await refreshPermissions()`；或者让 `refreshPermissions(token)` 显式带上令牌。消息提示改用 `App.useApp()` 的 message。
- **应补测试**：`Login.test.tsx` 或 store 单测，mock api，断言 `/auth/permissions` 请求带 `Authorization`，并且 `logout` 没有被调用。
- **核验**：已记录执行 + 静态。

### QA-B1-8 设置页 useForm 未连接告警；加载失败时永久转圈；拉配置失败后「保存并发布」可能用默认值覆盖
- Dimension：8 空/错状态 / 6 | Severity：minor | 工作量：S
- **现象**：/settings 出现 `Instance created by useForm is not connected to any Form element`（运行记录第 60 行）。截图显示表单值已经回填（例如 webhook_url 为 `https://hooks.example.com/test`），所以告警本身没有丢数据。更实际的问题在错误分支。
- **根因**：
  - `frontend/admin/src/pages/Settings.tsx:36`：`notifyForm.setFieldsValue(cfg)` 调用时，`<Form form={notifyForm}>` 只在 `notifyCfg !== null` 时才渲染（`:149`），还没挂载。
  - `:43`：`form.setFieldsValue` 在 `fetching=true` 期间调用，此时整个表单被 `:90-92` 的 Spin 分支替换。
  - 错误分支：`:35`、`:37` 失败时把状态设为 null，而 `:138`、`:149` 把 null 当作「加载中」，结果永久转圈，没有错误提示。`:44-47` 拉站点配置失败只弹一次 toast，表单仍显示 `initialValues`（`site_title: 'AutoAgents'`），这时点「保存并发布」会用默认值覆盖真实配置。
  - 文案矛盾：按钮写「保存并发布」、顶部写「修改后立即生效」（`:99`、`:131`），而 `:78` 的注释说 FR-90 只能声明「已保存」，不能声明官网已同步。
- **修复方案**：
  1. 用 `'loading' | 'error' | 'ready'` 三态替代 null 判断，error 显示 Alert 和「重试」。
  2. 表单常驻挂载，用 `<Spin spinning>` 包裹；或者数据到位后通过 `initialValues` 加 `key` 重建表单。
  3. 拉取失败时禁用「保存」。
  4. 按钮改为「保存」，并删除「立即生效」的说法，或者核实官网确实读取这项配置后再保留。
- **应补测试**：`Settings.test.tsx` 中 mock `fetchNotifyConfig` 和 `fetchWebhookStatus` 失败，断言出现错误 Alert 而不是 Spin；mock `fetchSiteConfigs` 失败，断言保存按钮被禁用；用 `console.error` spy 断言没有 useForm 告警。
- **核验**：已记录执行 + 截图 + 静态。

### QA-B1-9 会话中企业被停用或到期时，前端显示「登录已过期」，而不是「企业已停用」
- Dimension：9 / 6 | Severity：minor | 工作量：S
- **现象 / 触发条件**：平台停用某企业后，该企业在线成员的下一个请求收到 401 `AUTH_TENANT_EXPIRED`（`tenant_context.py:74-85`、`deps.py:100-104`）。前端跳到登录页，显示「登录已过期。重新登录后回到刚才的页面。」，用户会反复尝试登录。
- **根因**：`frontend/admin/src/services/api.ts:14-18` 的 `onUnauthorized` 不区分错误码；`services/navigation.ts:24` 一律设置 `sessionExpired: true`。`Login.tsx:16` 虽然有 `COPY_EXPIRED`，但只在登录失败时使用。
- **修复方案**：`onUnauthorized(error)` 把 `code` 传给 `navigateToLogin(from, reason)`；Login 在 `reason==='AUTH_TENANT_EXPIRED'` 时显示「企业已到期或停用，请联系平台」，并且不提示回跳。
- **应补测试**：api 拦截器单测，401 加上该 code 时导航 state 带 reason；`Login.test.tsx` 断言显示对应文案。
- **核验**：静态。

### QA-B1-10 自定义角色建得出来，但分配不了；即使分配了也会被所有登录守卫拒绝
- Dimension：6 / 1 | Severity：minor | 工作量：S
- **现象**：`POST /api/v1/rbac/roles` 可以新建角色（`rbac.py:68-74,112-122`），但用户的创建和更新 schema 把 role 限定为三个值；删除角色时的「有用户在用禁删」检查（`rbac_service.py:90`）对自定义角色永远不会命中。
- **根因**：
  - `platform_core/schemas/auth.py:73,82`：`pattern="^(admin|operator|viewer)$"`。
  - `backend/app/api/deps.py:37`：`ROLE_ALL = ("admin","operator","viewer")`，如果直接改库分配自定义 role，`require_login` 会一律 403。
  - `/auth/permissions` 对未知 role 回退到 viewer（`auth.py:143`）。
- **后果**：运营可以配置一个永远不起作用的角色，RBAC 页给出的承诺是假的。
- **修复方案**：二选一。
  - A：暂时下线自定义角色，隐藏入口或 API 返回 410，只保留三个内置角色的权限编辑。
  - B：打通。schema 改为校验 role 存在于 roles 表，`require_login` 改为「任意有效角色」，operator/admin 类守卫改为按权限码判断。
  - 这一条依赖 R1 T1 的两轴授权收口，建议选 A 直到两轴收口完成。
- **核验**：静态。API 存在；RBAC 页截图未显示新建入口，界面是否暴露待确认。

### QA-B1-11 删除成员提示「不可恢复」，但平台可以恢复；邮箱唯一性在不同入口口径不一致
- Dimension：6 契约一致 | Severity：minor | 工作量：S
- **现象 / 根因**：
  - `Members.tsx:33-36,174` 告诉租户「删除不可恢复、用户名和邮箱不可复用」，但平台有恢复能力（`user_service.py:313-351`，页面 `UsersRestore.tsx`）。
  - 成员创建的邮箱查重包含已软删的行，范围是全局（`member_service.py:97-101`）；公开注册按「在册」口径查（`auth_service.py:239-254`，迁移 042 释放了软删行）。结果：同一个邮箱，被某租户删除后，不能再被任何租户加为成员，却可以走 `/auth/register` 注册。
- **修复方案**：统一采用 042 的「在册」口径（用 `user_repo.exists_by_email` 和 `exists_username_in_tenant`）；文案改为「删除后可联系平台恢复」，或者平台恢复也按不可恢复处理。两者必须一致。
- **应补测试**：删除成员后用同一邮箱新建成员的行为，与 `/auth/register` 的行为一致。
- **核验**：静态。

### QA-B1-12 前端身份快照不会刷新；重置密码不吊销现有会话
- Dimension：4 / 8 | Severity：minor | 工作量：M
- **现象 / 根因**：
  - 登录响应被当作 `user` 持久化（`useAuthStore.ts:29-33,47-52`），菜单和写控件据此判断（`Members.tsx:50`、`ProtectedRoute.tsx:31-35`、`usePermission.ts:60-61`）。没有 `/auth/me` 接口（`module-inventory.md:44-48`）。成员被降级后，界面继续显示写控件，操作后后端返回 403（后端的防线是正确的，`deps.py:105-114`）。
  - `member_service.py:148-161` 改密码后，已签发的 JWT 继续有效，直到过期（没有 token_version 或 password_changed_at，`get_current_user` 只看 `is_active`）。账号被盗后，靠重置密码踢不掉攻击者（30 分钟窗口；如果 QA-B1-2 引入 7 天 refresh，这个窗口会被放大）。
- **修复方案**：
  - 新增 `GET /auth/me`，每次页面加载和 `/auth/permissions` 刷新时一并更新 user。
  - users 增加 `token_version`（或 `password_changed_at`），写入 JWT claim，`get_current_user` 比对。重置密码、降级、停用时加一。
  - 这条必须和 QA-B1-2 的 refresh 方案一起设计。
- **核验**：静态。

---

## 对 R1 的补充与更正（不重复报告）
- **R1 QA-1 补充证据**：`admin_rbac-1440.png` 显示「管理员 admin」这一行的 21 项权限里包含 `menu:users`、`menu:settings`、`menu:platform-ops`、`menu:newapi`。所有租户 owner 和租户 admin 的 `role=admin`，所以 `/auth/permissions`（`auth.py:136-143`）会把平台菜单权限码下发给每个租户 owner（前端靠 `platformOnly` 兜底隐藏）。平台超管和全部租户管理员共用一条可编辑的权限行，这进一步说明 R1 T1「两轴收口」的必要性。
- **R1 QA-3 升级为具体缺陷**：R1 只建议「把 role 派生逻辑收口」，本轮确认已经造成功能失效（租户 operator 只读、平台用户页改角色会覆盖 owner），见 QA-B1-4。
- **R1 Strength 2 部分更正（待核）**：R1 说「claims 只承载身份，权限每请求从 DB 快照重算」。但非超管令牌的 `tenant_scope` 取的是 JWT claim 里的 `tenant_id`（`middleware/tenant_context.py:154`），不是 DB 行。平台用户页把用户迁到别的租户（`user_service.py:229-237`）后，旧令牌的作用域仍是原租户，与 deps 里从 DB 读出的 `tenant_id` 不一致。我没有读 `tenant_context.py:159` 之后的代码，请 manager 确认后决定是否在迁移租户时吊销令牌（可以和 QA-B1-12 的 token_version 一起做）。

---

## Dimensions checked
1. 标准符合 ⚠️：没有 FR/spec，以界面文案和代码自述为基线。「operator（可操作任务）」（QA-B1-4）、「记住我（7天）」（QA-B1-2）、「留空=不过期」（QA-B1-5）、「不可恢复」（QA-B1-11）、「租户唯一所有者」（QA-B1-1）都与实现不符。
2. 标准质量 ➖：这是 review-only 代码审计，范围内没有 GWT。状态流转并入第 8 维评判。
3. 证据有效性 ⚠️：测试的审计写入泄漏到 dev 库（QA-B1-6），dev 界面上的审计证据不可信。越权和自锁类负向用例是否已存在未逐一核实，按「应补」列出。
4. 安全 ⚠️：QA-B1-1（blocker，接管超管或 owner）、QA-B1-12（会话吊销）、QA-B1-6（审计归因）。正面项：每个请求都从 DB 重载身份并复核租户状态，失败即拒（fail-closed）。
5. 性能 ✅（附说明）：租户审计 limit 夹在 1–200（`members.py:124`）；改名判重会全量读取企业名（`tenant_admin_service.py:49-50`），已注明是管理面小表；成员列表不分页（单租户规模小，可接受）。已读范围内未见 N+1。
6. 契约一致性 ⚠️：QA-B1-4、QA-B1-10、QA-B1-11、QA-B1-8 的文案矛盾。另外内置权限目录 `rbac.py:29-51` 缺少截图中 DB 已有的 `menu:rbac`、`menu:enterprise`（以及 auth 内置映射里的 `menu:relay`），存在回退漂移。
7. 宪法合规 ✅（附说明）：抽查范围内 API 层没有 import ORM（rbac/members 已下沉到 service）。`member_service` 的公开方法首行都是 `logger.info`。其余沿用 R1 已记录的 arch 结果，我没有复跑。
8. 边界 ⚠️：权限层级和自身边界（QA-B1-1/3）；会话过期（QA-B1-2/9）；到期状态流转（QA-B1-5）；空状态和错误状态（QA-B1-8）；并发删除已有乐观条件（`member_service.py:186-194`，正面）。
9. 产品价值与体验 ⚠️：截图显示成员页把超管自己的危险操作全部暴露，审计区混入测试数据；企业管理页所有企业都是「不过期」，到期能力从未在真实数据上走通；设置页展示正常。**没有租户 owner、admin、operator 视角的截图**，租户侧旅程（邀请、授权、到期、续费）在界面上尚未验证，建议 manager 补一组租户 owner 视角截图（/members、/usage、/billing/checkout）。

## Strengths（改进时应保留）
1. 每个请求都从 DB 重载身份并复核租户可用性：`deps.py:94-114` 经 `load_auth_identity` 取权限，`deps.py:100-104` 与中间件 `tenant_context.py:87-103` 双重拦截到期或停用企业，异常时按拒绝处理。停用成员下一个请求立即 401。
2. 成员写操作的并发与隔离做得扎实：软删带乐观条件，rowcount 为 0 时返回 404 而不是 500（`member_service.py:186-194`）；跨租户 id 统一 404（`:35-36`）；收件箱清理和软删在同一事务里（`:184-196`）。
3. 登录防枚举与分级文案：不存在的用户也跑一次等代价哈希（`auth_service.py:42-44,104-109`）；密码命中后才判断企业状态，并使用单独文案（`auth_service.py:133-146`、`Login.tsx:68-85`）。
4. 平台租户的「三名保护」由服务层单点实现，并在界面上说明原因：`tenant_admin_service.py:111-116`；截图 `admin_enterprise-1440.png` 中平台租户的改名和停用按钮置灰，附带说明。
5. 回跳路径防开放重定向：`Login.tsx:44-52`、`navigation.ts:16-22` 只接受站内相对路径。

## Improvement themes
- **T1 成员权力模型单点化**（QA-B1-1、3、4）：目标是一个 `MemberPolicy` 统一定义层级（owner > admin > operator/viewer）、自身保护、超管排除、owner 转让，以及 tenant_role 到 role 的唯一映射。落地顺序：① 当天热修 reset、patch 的目标与自身校验（S）→ ② 唯一映射函数和存量数据修正（S）→ ③ owner 转让流程（M）→ ④ 并入 R1 的「路由 × 身份」矩阵测试。
- **T2 会话生命周期**（QA-B1-2、7、9、12）：目标是 access + refresh 双令牌、非记住模式用 sessionStorage、`/auth/me`、token_version 吊销、401 按错误码分流。顺序：先调整登录时序（S）→ sessionStorage（S）→ 按错误码分流（S）→ refresh 与 token_version（M）。
- **T3 企业生命周期状态机**（QA-B1-5）：目标是以 `expires_at` 为真相、读取时计算状态，续期或支付即恢复，停用只能手工，界面可以清除到期。顺序：改判定口径 → 续期和履约恢复状态 → PlatformOps 发送 null → 可选巡检回写和事件。
- **T4 测试与审计卫生**（QA-B1-6）：目标是 pytest 永远不能连到非测试库，审计行自带 tenant_id。顺序：修 conftest 的 `_ready` 并加 URL 护栏（S）→ 清理 dev 污染行 → 加 `operation_logs.tenant_id` 迁移（S）。
- **T5 前端状态规范**（QA-B1-8、10、11）：目标是加载、错误、就绪三态分离，表单常驻挂载，文案只声明已发生的事，未打通的能力不暴露入口。

## 待 manager 执行的验证（reviewer 未执行）
1. QA-B1-1：在一次性库或 pytest 里按该条第 1–4 步执行（**不要在 dev 库上**）。
2. QA-B1-4：建 operator 成员 → 登录 → `GET /api/v1/auth/permissions`、`POST /api/v1/spiders/tasks/<id>/control`。
3. QA-B1-5：`PATCH /api/v1/admin/tenants/<测试租户> {"expires_at":"2020-01-01T00:00:00Z"}` → 用该租户成员登录（预期现在成功）；另外 grep `TenantExpiryService(` 确认 backend/app 下没有调用。
4. QA-B1-6：该条中的 SELECT 计数 → `uv run pytest backend/tests/test_saas_members.py -q` → 再计数。
5. QA-B1-2：用 `ACCESS_TOKEN_EXPIRE_MINUTES=1` 启动后端，登录并勾选记住我，等 70 秒后点任意操作，观察是否被登出。

## Decisions
- 严重度按「影响 × 可达性」判定。QA-B1-1 的平台租户变体可以接管最高权限账号，入口就是可见的「添加成员」按钮，所以定为 blocker。QA-B1-2/4/5 影响所有用户或收入执行，定为 major。QA-B1-6 破坏证据可信度，定为 major。
- 所有结论都来自静态阅读和已记录的运行结果与截图，没有声称复现。

## Open questions
- **Q-B1-1（战略，待确认）租户 admin 与 owner 的权力边界**
  - A（**推荐**）：admin 只能管 operator/viewer；管理 admin 和 owner 转让只能由 owner 做。
  - B：admin 可以管其他 admin，但不能碰 owner。
  - C：维持现状（不推荐，存在接管路径）。
- **Q-B1-2（战略，待确认）会话策略**
  - A（**推荐**）：access 30 分钟 + refresh（记住我 7 天，不勾选则按会话）。
  - B：不做 refresh，文案改为真实时长，非记住模式改用 sessionStorage。
  - C：把 access token 直接延长到 7 天（不推荐，吊销窗口过大）。
- **Q-B1-3（战略，待确认）企业到期后的策略**
  - A（**推荐**）：到期后只读，保留账单和续费入口，客户可以自助续费。
  - B：维持禁止登录、联系平台（现状文案），但必须修复续期后恢复状态的问题。
  - 另需确认是否设宽限期。
- **Q-B1-4（战略，待确认）租户 operator 应有的能力**
  - A（**推荐**）：与平台 operator 相同（可以建和控制任务、方案），与界面文案一致。
  - B：维持只读，界面文案改为只读。

## Product-delta rows
- 无（`docs/product` 产品层未建立）。

## Lesson rows（仅静态核实的陷阱）
- **L-B1-1**：DBManager 的惰性 `init_all()` 在 `_ready=False` 时会覆盖测试注入的 `async_engines["DEFAULT"]`（`platform_core/db.py:96,147,166,176`，配合 `conftest.py:397,460`）。只注入引擎不设 `_ready`，测试就会写进真库。凡是「注入单例资源」的测试夹具，都必须同时冻结初始化标志。
- **L-B1-2**：通过带鉴权的 axios 客户端发出的任何「令牌落库之前」的请求，都会触发全局 401 登出回调（`useAuthStore.ts:25-29`、`api.ts:14-18`）。登录流程里必须先存令牌再发请求，或者用不挂回调的客户端。
- **L-B1-3**：role 与 tenant_role 这类派生字段一旦在多处手写映射（本轮发现 4 处），各入口会各自漂移，出现「同一个角色、不同权限」和「owner 被覆盖」。派生字段必须只有一个函数负责。
