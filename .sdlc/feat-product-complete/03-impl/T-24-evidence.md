# 实现证据 · T-24 用户已删筛选 + 恢复端点 + 占用判定/释放语义 + user_restored

> 票：contract §11 T-24（FR-93 GWT-93.1…93.9 + GWT-92.8；db-spec §16.1）｜角色：/backend｜日期：2026-09-11

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| `GET /admin/users?status=active\|deleted`（默认 active，93.2 保持） | Router | `backend/app/api/v1/admin.py` | Query pattern 白名单，非法值 422 |
| `POST /admin/users/{id}/restore`（仅平台超管） | Router | 同上 | `require_platform_admin_or_404`（GWT-93.6 直打 404 同形） |
| 状态筛选/恢复业务规则 | Service | `backend/services/user_service.py` | `list_users(status=…)` / `restore_user` |
| 恢复写入（条件 UPDATE） | Service→ORM update | 同上 | 单条 `UPDATE … WHERE id=? AND deleted_at IS NOT NULL`（db-spec §16.1） |
| 在册占用判/查重 | Repository | `backend/repositories/user_repository.py` | `exists_username_in_tenant`/`get_by_email`/`exists_by_email` 均在册口径 |
| 已删除标记字段 | Schema | `platform_core/schemas/auth.py` | `UserResponse.deleted_at`（非空=已删，GWT-93.1） |
| 唯一键在册化 | 迁移 + ORM | `backend/alembic/versions/042_users_alive_flag_unique_keys.py` + `platform_core/models/user.py` | alive_flag VIRTUAL 生成列 + 两新键，撤旧两键与 ix_users_email |
| `user_restored` 事件 | Service（提交后） | `user_service.restore_user` → `product_event_service.emit_product_event` | 独立短会话，失败不挡主路径（GWT-92.8） |
| 错误码映射 | 统一异常处理器 | `BusinessException` → 400 + 中文 message | 占用句「用户名或邮箱已被现有用户占用」（GWT-93.4/93.8 同句） |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象（UserResponse 固化快照，ADR-0007 D2）☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/alembic/versions/042_users_alive_flag_unique_keys.py` | 新增 | 唯一键在册化迁移（down_revision="041"） |
| `platform_core/models/user.py` | 修改 | alive_flag 生成列 + 两新 UniqueConstraint；email 列撤 unique/index（capability_assets 同款写法，db-spec §8 L219） |
| `backend/repositories/user_repository.py` | 修改 | `get_by_email`/`exists_username_in_tenant` 改在册口径（+多已删行 MultipleResultsFound 红线防护）；docstring 同步 |
| `backend/services/user_service.py` | 修改 | `list_users` status 筛选；`restore_user` 新增；`create_user` 查重注释 + IntegrityError→400 兜底 |
| `backend/services/member_service.py` | 修改 | `create_member` 查重 `.limit(1)`（042 后同标识可「一活一删」多行，防 MultipleResultsFound 500；**语义不变**——租户自助路径仍含软删行判重，`test_deleted_member_not_operable_or_reusable` 钉住） |
| `backend/services/auth_service.py` | 修改 | 仅注释（注册查重口径说明改在册；authenticate 改动属 T-16 在途，非本票） |
| `backend/app/api/v1/admin.py` | 修改 | list status 参数 + restore 端点 + delete docstring |
| `backend/tests/test_t24_user_restore.py` | 新增 | GWT 13 例（红→绿） |
| `backend/tests/test_t24_migration_042.py` | 新增 | 迁移 up→down→up + 在册语义 + impossible-down（mysql_fidelity） |

**与票里「会改哪些文件」一致**：☑ 是（user_service / user_repository / 迁移 / admin 路由 / ORM 对齐均在票面；member_service 的 limit(1) 是 042 多行护栏，见 §3）

**未触碰「不许改的文件」**：☑ 确认（未动恢复 UI=T-25、企业编辑=T-27/28、未物理删除任何已删行）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 占用预检（username 同租户在册 / email 全局在册）+ 恢复 UPDATE | 是（同一 session，commit 前完成） | 防「判定通过→并发新建→恢复覆盖」（SEC-12）；正确性另由 042 唯一键兜底 |
| 恢复 commit + `user_restored` 上报 | 否 | 事件走独立短会话（`emit_product_event` 既有通道），失败仅 warning 不回滚恢复 |

**事务提交后的操作失败怎么办**：事件至少一次语义，失败记日志（可接受——`emit_product_event` 内建吞异常 + warning）。

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 恢复=行自身主键 + `deleted_at IS NOT NULL` 条件 |
| 保证方式 | 条件 UPDATE rowcount（=1 真恢复 / =0 no-op）+ 042 唯一键兜底并发占名 |
| 重复请求返回 | 200 + 当前状态快照；**不**二次上报事件（GWT-93.9） |

☑ 未使用「先查后插」（预检只为文案，正确性=约束）

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 恢复×恢复 | 条件 UPDATE `WHERE deleted_at IS NOT NULL` | rowcount=0 → 判定被并发恢复抢先 → no-op、不重复事件 |
| 恢复×新建占名 | DB 唯一键（042 尾列 alive_flag） | UPDATE 撞键 IntegrityError → rollback → 中文占用句（`test_restore_db_constraint_fallback_same_sentence` 桩预检直证） |
| 新建×恢复先落 | `create_user` flush 撞键 → rollback → 400 占用句 | db-spec §16.1「创建侧优雅报错」 |

☑ 所有条件更新的返回行数都有处理

### 外部依赖

无新增外部依赖（事件走库内 product_events 表）。

### 关键决策记录

- **042 单迁移 expand→contract**：放松方向（新键行子集严格小于旧键，025 先例）；`ix_users_email` 撤后 down 不恢复（026 口径）→ **down→up 重放时该索引不在场，DROP 按在场性条件执行**（迁移测试第一轮红：`Can't DROP 'ix_users_email'`，修复=information_schema 条件撤；legacy email 唯一键名按 STATISTICS 定位、不硬编码）。
- **member_service 只加 `.limit(1)` 不改语义**：租户自助路径「含软删行判重」是既有钉住行为（`test_deleted_member_not_operable_or_reusable` 422）；超管路径（用户管理）才走释放语义——两口径并存由 DB 同一约束承载（已删行 NULL 脱离唯一，应用层各自判）。
- **`get_by_email` 改在册过滤**：042 后同 email 可多行（1 在册 + N 已删），`scalar_one_or_none` 会 500（db-spec §16 红线）；同时天然实现 GWT-93.7 的 email 释放查重。

## 4. ORM 与 DBML 对齐

☑ 字段名 ☑ 类型 ☑ 可空性 ☑ 默认值 ☑ 索引 ☑ 唯一约束（`uq_users_tenant_username_alive`/`uq_users_email_alive`，db-spec §8/§16.1）——全部与 db-spec 对齐（alive_flag SMALLINT VIRTUAL 生成列，capability_assets 同款）

结构核对输出（隔离库真实 MySQL，迁移链全量跑至 042 后）：

```
PRIMARY unique id / email unique email / uq_users_tenant_username unique tenant_id,username
ix_users_username nonunique / ix_users_email nonunique        ← 041 态
-- 042 upgrade 后断言（test_t24_migration_042）：
uq_users_tenant_username_alive == [tenant_id, username, alive_flag]
uq_users_email_alive == [email, alive_flag]
'uq_users_tenant_username' not in uniques；'email' not in uniques
'ix_users_email' not in plain；'ix_users_username' in plain（保留，db-spec §8）
```

**未自行加字段/改类型**：☑ 确认（alive_flag 与两键名均为 db-spec §16.1 原文）

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `list_users`（status 入参）/`restore_user`（id+actor）入口 logger.info；恢复成功/ no-op 分支各自记 |
| 错误日志上下文 | 占用冲突经统一处理器记 warning（含 request_id） |
| 慢操作耗时 | 既有请求中间件口径，无新增慢路径 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 事件 props 仅 restored_user_id（`test_…emits_event` 断言无 password 字样）

## 6. 自测证据

> 命令与退出码**原样粘贴**。红=实现前基线（tdd 伴随），绿=实现后。

```
$ uv run pytest -q backend/tests/test_t24_user_restore.py        # 红（实现前）
12 failed, 1 passed in 11.33s
exit: 1

$ uv run pytest -q backend/tests/test_t24_user_restore.py        # 绿
13 passed in 19.59s
exit: 0

$ MYSQL_FIDELITY=1 MYSQL_FIDELITY_USER=root MYSQL_FIDELITY_PASSWORD=*** \
  uv run pytest -q backend/tests/test_t24_migration_042.py       # 迁移 up→down→up（隔离 schema）
1 passed in 8.59s
exit: 0
（第一轮红：1 failed in 87.19s —— down→up 重放撞 ix_users_email 缺失，见 §3 修复）

$ uv run pytest -q backend/tests/test_admin_users_crud.py backend/tests/test_saas_members.py \
  backend/tests/test_user_service.py backend/tests/test_users_null_tenant_contract.py \
  backend/tests/test_auth_service.py backend/tests/test_repository_soft_delete.py \
  backend/tests/test_saas_r13_overwrite.py backend/tests/test_saas_isolation.py
75 passed in 76.58s (0:01:16)                                    # 既有用户/租户测试零回退
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

$ uv run ruff check backend platform_core scripts
All checks passed!
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| 93.1 筛已删+标记 | `test_deleted_filter_lists_only_deleted_with_marker`（含空态） | ✅ |
| 93.2 默认视图保持 | `test_default_list_excludes_deleted` | ✅ |
| 93.3 恢复成功 | `test_restore_success_returns_to_default_list_and_emits_event` | ✅ |
| 93.4 占用冲突（username/email 各拆格） | `test_restore_conflict_by_username_keeps_both_intact` / `…_by_email` | ✅ |
| 93.5 username 释放 | `test_create_reuses_released_username_in_same_tenant` | ✅ |
| 93.6 越权 404 同形 | `test_tenant_direct_restore_is_404_shape`（+参数白名单 `…_rejects_unknown_status`） | ✅ |
| 93.7 email 释放 | `test_create_reuses_released_email_globally` | ✅ |
| 93.8 再恢复同句 | `test_re_restore_after_release_conflicts_with_same_sentence` | ✅ |
| 93.9 重复恢复 no-op | `test_repeat_restore_is_noop_without_second_event`（+`…_missing_user_400`） | ✅ |
| 92.8 user_restored | `test_restore_success_…emits_event`（tenant_id/actor/props.restored_user_id/无敏感字段） | ✅ |
| DB 兜底（1062 同句） | `test_restore_db_constraint_fallback_same_sentence` + 迁移测试 MySQL 1062 直证 | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | `test_restore_db_constraint_fallback_same_sentence`（回滚后双方行不变） | ✅ |
| 幂等 | `test_repeat_restore_is_noop_without_second_event` | ✅ |
| 并发写 | 同上 DB 兜底用例（预检桩绕过=并发窗口模拟）+ 迁移测试 1062 | ✅ |
| 外部依赖失败 | ➖ N/A（唯一外部性=product_events 库内写入，`emit_product_event` 既有吞异常路径，T-22 面已钉） |

## 7. NFR 验证

票面无专属 NFR 行（NFR-05 权限面=恢复仅平台超管已测；NFR-04 恢复面无上传/文件，归 T-35）。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/frontend`（T-25） | ① 列表筛选参数 `GET /api/v1/admin/users?status=deleted`（默认 active）；② 已删标记=行内 `deleted_at` 非空；③ 恢复 `POST /api/v1/admin/users/{id}/restore` 返回 200+用户快照，冲突 400 message=「用户名或邮箱已被现有用户占用」（X-QUOTA：无内码）；④ 重复恢复也 200（幂等，UI 可直接刷新回默认列表）。 |
| `/qa` | ① 迁移 042 已在隔离 MySQL 8.0.42 验证 up→down→up 与 impossible-down；**本机开发库（head 039）尚未升级**，联调前需 `alembic upgrade head`；② 租户自助成员路径（/members）仍「含软删行判重」（既有钉住行为），与超管释放口径并存——活体回归时不要把成员路径同名重建当缺陷；③ 登录/查找路径保持 deleted_at IS NULL 过滤（红线，db-spec §16）。 |
| `/architect` | 观察项：`GET /admin/users` 既有守卫=require_admin（租户管理员可 200 本租户行，`test_saas_r13_overwrite` 钉住的历史行为），页面不存在同形在前端路由层（T-29）实现；本票新增**动作面**（restore）已按 GWT-93.6 用 404 同形。若要列表 API 也收紧为 404 同形，需先裁决既有钉住测试——未自行改。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（1414 passed / 37 skipped，exit 0）
- [x] 契约落位表已核对，分层无违规（arch.sh R7/R10 通过）
- [x] ORM 与 db-spec 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用（R11 通过）
- [x] 无 `except: pass`（IntegrityError 分支显式回滚+抛业务异常）
- [x] 日志已脱敏
- [x] 事务里无外部调用（事件在 commit 后）
- [x] 幂等未用「先查后插」
- [x] 条件更新的 `rows == 0` 已处理（no-op 分支）
- [x] 外部依赖四件套（➖ N/A，库内写入）
- [x] 四类易漏测试已覆盖
- [x] 发现的上游问题已回报（§8 /architect 观察项）
- [x] 禁止物理删除已删行——全程仅 UPDATE deleted_at
