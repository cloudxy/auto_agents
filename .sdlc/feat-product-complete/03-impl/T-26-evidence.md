# 实现证据 · T-26 基座保护：种子 admin 不可删 + 平台租户三名守卫

> 票：contract §11 T-26（FR-94 GWT-94.1…94.5；db-spec §16.2）｜角色：/backend｜日期：2026-09-11
> 与 T-24 同域（user_service.py）串行施工——本票在 T-24 落地后开工，零冲突。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 种子 admin 不可删（判定在既有两守卫之前） | Service | `backend/services/user_service.py` `delete_user` | 身份=(platform 租户, username='admin') 平台超管行（set_admin_account 口径）；句「平台初始账号不可删除。」（GWT-94.1） |
| 平台租户不可改名（GWT-94.2） | Service（tenant 写服务单点） | `backend/services/tenant_admin_service.py` `patch_tenant` | slug 守卫不加列（db-spec §16.2）；句「平台租户不可修改名称。」 |
| 平台租户不可停用（GWT-94.3） | Service（同上单点） | 同上 | PATCH status 对 platform 拒绝；句「平台租户不可停用。」；配额/到期编辑不在三名保护内 |
| 不可删除（GWT-94.4 前置冻结） | 无端点 | `app.routes` 核对 | 企业删除本波无端点（测试机械断言无 DELETE /admin/tenants）；将来删除入口落地前必须先排除 platform |
| 越权 404 同形（GWT-94.5） | Router 既有守卫 | `backend/app/api/v1/admin.py`（`require_platform_admin_or_404`） | 既有守卫核对（测试钉住），零改动 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/user_service.py` | 修改 | `delete_user` 种子 admin 守卫（+`SEED_ADMIN_USERNAME`/`PLATFORM_TENANT_SLUG` 常量；其余改动属 T-24） |
| `backend/services/tenant_admin_service.py` | 修改 | `patch_tenant` platform 三名守卫（+`PLATFORM_TENANT_SLUG` 常量） |
| `backend/app/api/v1/admin.py` | 修改 | 仅 docstring（「种子 admin 不可删」）；路由零新增（T-24 部分见彼票） |
| `backend/tests/test_t26_base_protection.py` | 新增 | GWT 9 例（红→绿） |

**与票里「会改哪些文件」一致**：☑ 是（user_service.delete_user 守卫 + tenant 写服务单点）

**未触碰「不许改的文件」**：☑ 确认（未做恢复 UI=T-25、企业编辑=T-27/28、未给 tenants 加列、未开删除端点）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 守卫判定 + 写入 | 单条写路径，守卫在 mutation 前 | 拒绝时零写入（异常路径无 commit） |

### 幂等 / 并发控制 / 外部依赖

➖ N/A：三守卫均为纯拒绝分支（无状态流转、无并发窗口、无外部调用）。守卫精度：status 仅对白名单值且**与现值不同**才拒（同值 PATCH=no-op 放行）；name 仅在提交值 ≠ 现值时拒；quota/expires_at 编辑不受三名保护（运营台对平台租户调配额是 FR-102 依赖，测试钉住）。

### 关键决策记录

- **种子 admin 身份不按全局 username 判**：跨租户可存在业务租户自建 "admin"（test 钉住可删）；身份=platform 租户 + username=admin + is_platform_admin（与 `backend/scripts/set_admin_account.py` 的精确取行同口径）。platform 租户行缺失（未跑 024）时守卫不误伤（跳过判定，由既有守卫兜底）。
- **守卫顺序**：种子守卫在「不能删自己/最后一个超管」之前（票面「判定在前」）——GWT-94.1 的 Given（第二超管在场）下由种子句拒绝，不落到「最后超管」计数逻辑。
- **三名保护收口在 `patch_tenant` 单点**：企业管理页（T-27 将接入）与运营台同走该服务，两处同真相（contract §7.9）；本票防御性覆盖 `name` 键（现无改名端点，T-27 落地时免二次施工）。

## 4. ORM 与 DBML 对齐

☑ 本票零 schema 改动（slug 守卫不加列，db-spec §16.2「零迁移、零回填」）；042 相关对齐见 T-24 证据 §4。

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `delete_user`/`patch_tenant` 既有入口 logger（R10），守卫拒绝经统一处理器 warning（含 request_id） |
| 错误日志上下文 | 拒绝句即用户可见句（中文、无内部码——X-QUOTA 面） |

**日志脱敏核对**：☑ 无密码 ☑ 无 token

## 6. 自测证据

> 命令与退出码**原样粘贴**。红=守卫缺失基线（tdd），绿=守卫落地后。

```
$ uv run pytest -q backend/tests/test_t26_base_protection.py      # 红（守卫前）
3 failed, 6 passed in 8.57s
exit: 1

$ uv run pytest -q backend/tests/test_t26_base_protection.py      # 绿
9 passed in 6.59s
exit: 0

$ uv run pytest -x -q backend/tests
1414 passed, 37 skipped, 7 warnings in 523.15s (0:08:43)
exit: 0

$ bash tools/check/arch.sh
✓ 架构合规检查通过（13 红线 + 4 边界 + FR-14 发布物密钥，全部通过）
exit: 0

$ bash tools/check/db_migrations.sh
✓ 迁移破坏性变更检测通过
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| 94.1 种子 admin 不可删（第二超管在场） | `test_seed_admin_undeletable_even_with_second_platform_admin`（行未软删库级断言） | ✅ |
| 94.2 平台租户不可改名 | `test_platform_tenant_rename_rejected`（名称保持库级断言） | ✅ |
| 94.3 平台租户不可停用 | `test_platform_tenant_disable_rejected_login_unaffected`（status 保持 + `assert_tenant_active` 登录门不受影响） | ✅ |
| 94.4 无删除企业入口 | `test_no_tenant_delete_endpoint`（app.routes 机械断言） | ✅ |
| 94.5 越权 404 同形 | `test_tenant_direct_patch_platform_is_404_shape`（404 + "Not Found" 同形、platform 不变） | ✅ |
| 守卫精度 | `test_same_name_admin_in_business_tenant_still_deletable`（跨租户同名不误伤）/ `test_platform_tenant_quota_edit_still_allowed` / `test_regular_tenant_status_edit_unaffected` / `test_existing_delete_guards_still_hold`（既有两守卫并存） | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（拒绝分支零写入，无多步写） | |
| 幂等 | ➖ N/A（拒绝分支无重复语义） | |
| 并发写 | ➖ N/A（守卫为读判定+拒绝） | |
| 外部依赖失败 | ➖ N/A（无外部依赖） |

## 7. NFR 验证

票面无专属 NFR 行；NFR-05 权限矩阵面（越权 404 同形、租户不可见平台页）由 94.5 用例覆盖。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/frontend`（T-28） | 平台租户行后端永远 status=active、name=「平台租户」；改名/停用控件对 platform 提交会收到 400 中文句（「平台租户不可修改名称。」/「平台租户不可停用。」）——UI 可按 slug=platform 隐藏入口，后端守卫兜底。 |
| `/qa` | ① 三句拒绝文案为字面断言（测试钉住），改文案需同步测试；② 种子 admin 守卫依赖 platform 租户种子（024）——环境未跑迁移时守卫不生效（跳过判定），活体回归需先 `alembic upgrade head`；③ 运营台对**常规企业**停用/启用不受影响（回归用例在档）。 |
| `/architect` | 无契约歧义。注：T-27 企业改名端点接入时走 `TenantAdminService` 单点即可继承 94.2 守卫（防御性 `name` 键已就位）。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（含全量 1414 passed）
- [x] 契约落位表已核对，分层无违规
- [x] 零 schema 改动（slug 守卫）
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 四类易漏测试标 N/A 并给理由
- [x] 发现的上游问题已回报（无新项）
