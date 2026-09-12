# 实现证据 · T-16 注册邮箱能登录

> 票：`02-shape/tickets-v1.2-stale-archived/T-16.md`（v1.2 归档版，本轮以 packet + contract §7.6 + spec FR-83 为准）｜FR 锚点：FR-83｜角色：/backend｜日期：2026-09-11

## 1. 契约落位表

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 标识解析规则（含 `@` → email 全局唯一；否则 username 消歧） | Service | `backend/services/auth_service.py` | `authenticate` 入口分支；email 小写匹配（signup/validate_email 均小写落库） |
| email 候选读取（软删行不参与） | Repository | `backend/repositories/user_repository.py` | 新增 `get_login_candidates_by_email`（0/1 行，list 与 `get_by_username` 同构，下游零分叉） |
| 登录主字段校验（上限对齐注册邮箱容量） | Schema | `platform_core/schemas/auth.py` | `LoginRequest.username` max_length 50→100（users.email=String(100)，signup 收 100；纯放宽，旧输入全兼容） |
| 未知标识=错密码同句（GWT-83.2） | Router（既有） | `backend/app/api/v1/auth.py` | 两条路径同走 `None` → 同一 `AuthenticationException("用户名或密码错误")`/`AUTH_FAILED`；UI 句 `用户名或密码不正确。核对后再登录。` 由 admin `Login.tsx COPY_CREDENTIALS` 既有映射渲染 |
| 到期不同句（GWT-83.5） | Service（既有 FR-08） | `backend/services/auth_service.py` | 密码命中后 `assert_tenant_active` → `AUTH_TENANT_EXPIRED`，未改 |
| 注册成功屏「登录时请填写注册邮箱」 | official 页面 | `frontend/official/src/pages/Register.tsx` | 成功句加提示；负责人标识优先展示注册邮箱 |
| signup 响应 owner.email 透出（既有） | 类型 | `frontend/official/src/services/signup.ts` | `owner.email?: string`（后端 snapshot 本就返回，前端类型补声明） |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象（返回 dict）☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/repositories/user_repository.py` | 修改 | 新增 `get_login_candidates_by_email`（deleted_at IS NULL） |
| `backend/services/auth_service.py` | 修改 | `authenticate` 标识分支 + docstring；既有停用过滤/消歧/FR-08 逻辑零改动 |
| `platform_core/schemas/auth.py` | 修改 | `LoginRequest.username` max_length 100（纯放宽） |
| `backend/tests/test_auth_service.py` | 修改 | 新增 `TestAuthenticateEmailIdentifier`（4 用例） |
| `backend/tests/test_auth_login_tenant.py` | 修改 | 种子加跨租户同名 owner；新增 3 集成用例；限流清零名单加邮箱标识 |
| `backend/tests/test_saas_signup_expiry.py` | 修改 | 新增 GWT-83.5 用例；补 login_fail 计数清零 fixture（见 §8） |
| `frontend/official/src/services/signup.ts` | 修改 | `owner.email?: string` |
| `frontend/official/src/pages/Register.tsx` | 修改 | 成功句「登录时请填写注册邮箱」；负责人标识 email 优先、短名回退 |
| `frontend/official/src/pages/Register.test.tsx` | 修改 | GWT-04.1 断言更新；新增 GWT-83.3 两条 |

**与票里「会改哪些文件」一致**：☐ 有偏差。偏差说明：(a) `platform_core/schemas/auth.py` 不在票内清单——注册侧收 51–100 字符邮箱而登录字段上限 50 会令 GWT-83.1 对这类邮箱必假（422 而非登录），按契约「主字段填注册邮箱」补齐容量，属 Schema 层字段校验职责，纯放宽；(b) 票内列出的 `frontend/admin/src/pages/Login.tsx` placeholder「注册邮箱或用户名」**未做**——packet 明示「不动登录页视觉重构（无此票）」且 success_checks 无 admin 项，见 §8 给 pm/前端。

**未触碰「不许改的文件」**：☑ 确认（FR-08 到期句、`users` DDL 均未动；未做任何迁移）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 标识解析候选读取 | 否 | 单读路径，无写 |

### 幂等

N/A——查询路径，无写操作（登录失败计数为既有 Redis 限流，非本票改动）。

### 并发控制

N/A——无状态写。email 全局 UNIQUE 由 `users.email` 既有约束保证（候选至多 1 行）。

### 外部依赖

N/A——本票未新增外部依赖。Redis 限流 fail-open 语义既有（`test_auth_rate_limit_failopen.py` 覆盖）。

### 解析决策（本票核心）

- 判据 `"@" in identifier`（contract §7.6 既定，不做邮箱正则再验——错拼邮箱与未知标识同走 401 同句，正是 GWT-83.2 要的防枚举）。
- email 路径 `strip().lower()`：signup（`admin_email.strip().lower()`）与 `validate_email` 均小写落库；username 路径仅 `strip()`，原消歧行为不变（既有单测 `assert_awaited_once_with("alice")` 仍绿）。
- 软删行：email 路径在 Repository 过滤 `deleted_at IS NULL`（与 `get_by_username` 登录口径一致）；查重/占用场景继续走 `get_by_email`/`exists_by_email`（含软删行，语义未动）。

## 4. ORM 与 DBML 对齐

无 DDL 改动（票明确「不动 DDL」）。N/A ☑ 未自行加字段/改类型。

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `authenticate` 既有 `logger.info(f"尝试验证用户: {username}")`（R10），标识解析分支不打新日志（失败路径既有 warning 不泄露候选数） |
| 事件 | `login_failed`/`login_succeeded` 既有埋点未动（`reason=credential|locked|expired`） |

**日志脱敏核对**：☑ 无密码 ☑ 无 token（标识可含邮箱，与 signup 服务既有日志口径一致）

## 6. 自测证据

> 命令与退出码原样粘贴。红阶段输出为当时终端记录（pytest 语义退出码 1；首条命令当时经 `tail` 管道未单独捕退出码，前端红阶段 exit 原样可见）。

### 红阶段（tdd：先写测试）

```
$ uv run pytest -x -q backend/tests/test_auth_service.py backend/tests/test_auth_login_tenant.py backend/tests/test_saas_signup_expiry.py
>       assert result is not None
E       assert None is not None
FAILED backend/tests/test_auth_service.py::TestAuthenticateEmailIdentifier::test_email_identifier_uses_email_lookup
1 failed, 7 passed in 11.31s
```

```
$ CI=1 npm test --prefix frontend/official -- --testPathPattern=Register.test
    expect(copy).toHaveTextContent('登录时请填写注册邮箱')
Test Suites: 1 failed, 1 total
Tests:       3 failed, 8 passed, 11 total
exit: 1
```

### 绿阶段（实现后）

```
$ uv run pytest -q backend/tests/test_auth_service.py backend/tests/test_auth_login_tenant.py backend/tests/test_saas_signup_expiry.py
....................................                                     [100%]
36 passed in 77.66s (0:01:17)
exit: 0
```

```
$ CI=1 npm test --prefix frontend/official -- --testPathPattern=Register.test
Test Suites: 1 passed, 1 total
Tests:       11 passed, 11 total
exit: 0
```

```
$ uv run pytest -x -q backend/tests
1374 passed, 36 skipped, 7 warnings in 193.50s (0:03:13)
exit: 0
```

```
$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0

$ uv run ruff check backend platform_core scripts
All checks passed!
exit: 0

$ npm run build --prefix /Users/xuyun/auto_agents/frontend/official
  (CRA production build 成功输出，尾部见 deploy 提示)
exit: 0
```

**环境备注（复现性）**：登录失败限流计数落本机 Redis（5 次/15 分钟跨轮次存活）。首次全量跑曾因历史轮次残留计数出现 `RATE_LIMITED` 假失败（`test_product_events.py::fail-a` 等），清 `login_fail:*` 后全量即上述 1374 全绿；`test_saas_signup_expiry.py` 已按 `test_auth_login_tenant.py` 同款 fixture 逐轮清零（本票顺带修）；`test_product_events.py` 的同类缺口见 §8。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-83.1 邮箱+正确密码进本企业 | `test_email_login_enters_own_tenant_not_other`（前半）· 单测 `test_email_identifier_uses_email_lookup` | ✅ |
| GWT-83.2 未知标识=错密码同句 | `test_unknown_email_and_wrong_password_same_sentence`（同 code=AUTH_FAILED、message 全等）· 单测 unknown/wrong-pw | ✅ |
| GWT-83.3 成功屏写明「登录时请填写注册邮箱」 | `GWT-83.3 success screen names the registered email…` · `GWT-83.3 fallback without email…`（短名回退不暗示只能短名） | ✅ |
| GWT-83.4 进 A 不进 B | `test_email_login_enters_own_tenant_not_other`（A/B 对称断言 tenant_id） | ✅ |
| GWT-83.5 到期不同句 | `test_disabled_tenant_email_login_uses_expiry_sentence`（AUTH_TENANT_EXPIRED ≠ 凭证句） | ✅ |
| 既有登录不回退 | `test_auth_login_tenant.py` 全部 9 条 + `test_saas_signup_expiry.py` 既有用例（GWT-04.x/GWT-08.x）全绿 | ✅ |
| 软删不登录（email 路径口径） | `test_soft_deleted_user_email_login_rejected` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（纯读路径，无多步写） | |
| 幂等 | ➖ N/A（无写操作） | |
| 并发写 | ➖ N/A（无状态写；email 全局 UNIQUE 既有约束保证单候选） | |
| 外部依赖失败 | ➖ N/A（未新增外部依赖；Redis 限流 fail-open 已有 `test_auth_rate_limit_failopen.py`） | |

## 7. NFR 验证

票内无 NFR 条目。N/A。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | (1) 反复跑全量须先清本机 `login_fail:*` Redis 计数（或等 15 分钟窗口过期），否则 `test_product_events.py::fail-a`/`locked-a` 等会 429 假失败——该文件无计数清零 fixture，属既有缺口；(2) `scripts/check-layering.py` 在本仓库不存在，分层由 `tools/check/arch.sh` 覆盖（通过）。 |
| `/frontend` + pm | 票（v1.2 归档版）曾列 admin `Login.tsx` placeholder 改「注册邮箱或用户名」，本轮 packet 收窄为「backend + official 成功屏一行」未做；邮箱登录后端已可用，登录页字段 label/placeholder 仍为「用户名」，是否补一句 copy 归前端票决断。 |
| `/architect` | `LoginRequest.username` max_length 50→100 为本票放宽（对齐 `users.email` String(100) 与 signup 容量），契约未写长度，如需收回请在契约补长度条款。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（36/11/1374 全过，非「大部分通过」）
- [x] 契约落位表已核对，分层无违规（arch.sh 0 违规）
- [x] ORM 与 DBML 一致，未自行加字段（零 DDL）
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用（email 路径复用既有 `asyncio.to_thread` 验密）
- [x] 无 `except: pass`
- [x] 日志已脱敏
- [x] 事务里无外部调用 / 幂等未用先查后插 / 条件更新 N/A（纯读）
- [x] 外部依赖 N/A（未新增）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 邮箱+正确密码进本企业；短名成功未被算作邮箱路径完成（email 断言走 `tenant_id` + email 字面量双证）
- [x] 发现的上游问题已回报（§8），未自行绕过
- [ ] 票状态更新为 done（归 state.yaml 所有者/编排者，本 hat 不改）
