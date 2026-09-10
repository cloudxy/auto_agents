# 实现证据 · T-06 到期/停用拒绝登录与后续写

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-06.md`｜FR 锚点：FR-08｜角色：/backend｜日期：2026-09-08
> 上游：`01-define/spec.md` FR-08 · X-EXPIRED
> 泳道：L4

未改套餐闸（T-09 / `llm_client.py`）。未改候选谓词（T-08）。未改 enqueue 路径（T-07）。未改 admin App/menu（T-05）。未改 official Register。未代选六问。执法点 = 登录颁发 + 已颁发会话后续守卫（中间件 + `get_current_user`），禁止只挡登录。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径/方法/状态码 | Router | `backend/app/api/v1/auth.py` | POST `/auth/login` 仍 401；到期不颁发 token |
| 字段校验（类型/范围/枚举） | Schema | 未改 | 本票不改请求体 |
| 跨字段参数约束 | Schema | 未改 | |
| 权限判定（数据范围） | Service + Middleware + deps | `assert_tenant_active`；`TenantContextMiddleware._guard_tenant_active`；`get_current_user` | 平台超管跳过 |
| 业务规则/状态流转 | Service | `tenant_expiry_service.py` + `auth_service.authenticate` | 密码命中后再查 `expired`/`disabled` |
| 数据读写 | 既有 `tenants.status` | 无 schema 变更 | 巡检仍 `expire_overdue_tenants` |
| 错误码映射 | 统一异常处理器 + 中间件信封 | `AuthenticationException(code=AUTH_TENANT_EXPIRED)` | 禁止渲染成 `AUTH_FAILED` 密码句 |
| 幂等 | N/A | | 本票无新建写 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import ☑ 中间件只调 Service，不 import Tenant

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/tenant_expiry_service.py` | 修改 | `AUTH_TENANT_EXPIRED` / 文案 / `assert_tenant_active` |
| `backend/services/auth_service.py` | 修改 | 密码命中后查企业状态；到期抛独立码 |
| `backend/app/api/deps.py` | 修改 | `get_current_user` 后续请求守卫 |
| `backend/app/middleware/tenant_context.py` | 修改 | Bearer 后续请求 fail-closed；信封与登录同码同句 |
| `backend/tests/conftest.py` | 修改 | 测试鉴权 override 同源守卫 |
| `backend/tests/test_saas_signup_expiry.py` | 修改 | 08.1–08.4 夹具 |
| `frontend/admin/src/pages/Login.tsx` | 修改 | 映射 `AUTH_TENANT_EXPIRED`；文案与 GWT 同句（无句号） |
| `.sdlc/feat-four-pillars-v2/02-shape/tickets/T-06.md` | 修改 | 状态 done |

**与票里「会改哪些文件」一致**：☑ 是（票未列死路径；闸命令活路径 `bash tools/check/arch.sh`）

**未触碰「不许改的文件」**：☑ 确认（未改 `frontend/admin/src/App.tsx` / `menuConfig.tsx` / spider enqueue 服务 / `llm_client.py` 配额 / T-08 谓词 / official Register）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 登录读用户 + 读租户 status | 同一请求 session | 只读；拒绝路径不 commit |
| 后续请求中间件读 tenants | 独立短事务（identity_session_factory） | 与 F-01 平台态复核同范式；在 `tenant_scope` 之前 |

**事务提交后的操作失败怎么办**：无提交后动作。拒绝直接抛/回 401。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | N/A |
| 保证方式 | N/A |
| 重复请求返回 | N/A |

☑ 未使用「先查后插」（本票无新建业务写）

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 无本票条件更新 | — | — |

☑ 本票无条件更新（到期巡检 `expire_overdue_tenants` 既有 `rowcount` 日志，本票未改其语义）

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 读 `tenants.status` | 既有 session | 无 | 查无租户 / 复核异常 fail-closed | 读 |

## 4. ORM 与 DBML 对齐

☑ 未改 ORM 字段/类型/索引/唯一约束/外键。执法走既有 `tenants.status`（`active`/`expired`/`disabled`）。

结构核对输出：

```
$ 本票无 DDL / 无 autogenerate
（登录与写守卫读 tenants.status；巡检仍 expire_overdue_tenants）
```

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `assert_tenant_active` 记 tenant_id（无密码）；拒绝记 status |
| trace_id | 登录路径走统一异常处理器 `request_id`；中间件拒绝信封 `request_id=None`（与既有 `_reject` 同形） |
| 错误日志上下文 | `AUTH_TENANT_EXPIRED` + tenant_id；不含密码 |
| 慢操作耗时 | 未新增外部调用 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址

## 6. 自测证据

> 命令与退出码**原样粘贴**。「测试通过」「基本完成」不算证据。

```
$ uv run pytest -x -q backend/tests/test_saas_signup_expiry.py
.........                                                                [100%]
9 passed in 5.32s
exit: 0

$ bash tools/check/arch.sh
架构合规检查（13 条红线 + 3 条边界）
======================================
✓ R1: 硬编码连接串
✓ R2: 明文 password
✓ R3: scrapy → backend 反向依赖
✓ R4: scrapy 使用 SQLAlchemy
✓ R5: DOWNLOAD_DELAY 已配置
✓ R6: USER_AGENT 配置存在
✓ R7: API 层 import models
✓ R8: models 反向 import schemas
✓ R9: 无循环 import
✓ R10: service 方法入口缺 logger
✓ R11: backend 同步 redis_client() 直调（阻塞事件循环）
✓ R12: spider_service 门面白名单外 import（应直接依赖子 Service）
✓ R13: 租户过滤收口（安装点/裸语句/豁免清单同步）

--- 核心代码边界 ---
✓ B1: platform_core → backend/scrapy 反向依赖
✓ B2: backend → scrapy 直接依赖
✓ B3: config → 业务模块反向依赖

--- 发布物密钥（FR-14）---
✓ FR-14: config.gen.yaml 不在跟踪树
✓ FR-14: 跟踪的 deploy/config 无上游 Key 样例模式

✓ 架构合规检查通过（13 红线 + 3 边界 + FR-14 发布物密钥，全部通过）
exit: 0
```

旁路（非本票闸，防 authenticate 回归）：`uv run pytest -x -q backend/tests/test_auth_service.py backend/tests/test_auth_login_tenant.py backend/tests/test_r5_r7_fixes.py` → 21 passed，exit 0。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-08.1 正常 | `test_expired_tenant_login_rejected`（expired + 文案 ≠ `用户名或密码错误`；内部码 `AUTH_TENANT_EXPIRED`）；`test_disabled_tenant_login_rejected` | ✅ |
| GWT-08.2 边界 | `test_preissued_session_writes_refused_after_expiry`（先登录再置 expired；`POST /spiders/run` 与 `POST /ai/plans` 拒绝；任务数与 `llm_token_usage` 不变） | ✅ |
| GWT-08.3 越权 | `test_expired_tenant_login_rejected` 后半：`aliveowner` 200 且有 `access_token` | ✅ |
| GWT-08.4 空态 | `test_platform_placeholder_marketplace_not_in_tenant_results`（平台 `source=marketplace` 标题 `plat-mkt` 不进租户 `/spiders/results`；本企业 `mine-row` 可见） | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（本票只读守卫 + 拒绝写，无多步写） |
| 幂等 | — | ➖ N/A（无新建业务写） |
| 并发写 | — | ➖ N/A（无条件更新） |
| 外部依赖失败 | 中间件复核异常 fail-closed `_reject` | ✅ 代码路径；夹具走明确 expired/disabled 行 |

## 7. NFR 验证（票里有 NFR 时填）

本票无独立 NFR 数字闸。权限：到期/停用不得继续用产品（NFR-05 矩阵的企业状态列）。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 观察点：登录 401 `code=AUTH_TENANT_EXPIRED`、`message=企业已到期或停用，请联系平台`，信封无 `access_token`。凭证错误仍 `AUTH_FAILED` / `用户名或密码错误`。后续写：持过期前 Bearer 打 `POST /api/v1/spiders/run` 或 `POST /api/v1/ai/plans` 同码同句，任务表与 `llm_token_usage` 不增。08.4 观察点 = 租户 Bearer 的 `GET /api/v1/spiders/results`。 |
| `/frontend` | 后台 Login 已映射 `AUTH_TENANT_EXPIRED`（兼 `TENANT_EXPIRED` / `TENANT_DISABLED`），文案无句号，且必须写在泛 401→凭证句之前。 |
| `/architect` | 用户可见码用 `AUTH_TENANT_EXPIRED`（票允许内部码）。expired 与 disabled 同一句，未再拆 `TENANT_DISABLED` 作为必发码。08.4 靠 tenant_scope 隔离占位企业行，未把 T-08 `source <> marketplace` 谓词提前进本票。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（不是「大部分通过」）
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`（吞异常）
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」
- [x] 条件更新的 `rows == 0` 已处理（N/A）
- [x] 外部依赖四件套齐全或标 N/A
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 票状态已更新为 done
