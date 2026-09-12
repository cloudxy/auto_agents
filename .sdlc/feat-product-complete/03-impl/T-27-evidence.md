# 实现证据 · T-27 企业管理增强 API：改名/停用/再启用收口 + 平台默认租户显式化

> 票：contract §11 T-27（spec FR-95 GWT-95.1/95.2/95.4/95.5/95.6/95.7 后端半 + §0.4 命名收口）｜角色：/backend｜日期：2026-09-11
> 在 T-26 落地后施工（平台租户守卫已在 `patch_tenant` 单点，本票在其上扩，零回退）。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| `PATCH /admin/tenants/{id}` 扩 `name`（95.1） | Service（tenant 写服务单点） | `backend/services/tenant_admin_service.py` `patch_tenant` | 路由既有端点零新增（body 透传）；同名提交=no-op 放行 |
| 改名冲突域（既有名∪「平台租户」∪AutoAgents） | Service | 同上 + 模块级 `_assert_name_available` | 应用层精确判等（跨 SQLite/MySQL 排序规则一致）；拒绝句「企业名称不可用: {name}」（400 中文） |
| 名称 ≥2 字符校验 | Service | 同上 | 与 `create_tenant_minimal` 同口径（422） |
| 平台租户改名→T-26 守卫句保持（95.2 前半/94.2） | Service（零改动） | 同上 `patch_tenant` slug 守卫 | T-26 既有；测试零回退见 §6 |
| `GET /admin/tenants` 行带 `is_platform_default`（95.3） | Service | `list_tenants` | slug=platform 推导，零 DDL；企业管理页与运营台同读本端点=两读面同一真相 |
| 无企业归属挂平台租户（95.4） | Service | `backend/services/user_service.py` `create_user` | None/0（前端「（平台账户，不挂公司）」选项值）→ platform 租户；响应 `tenant_name`="平台租户" |
| 停用/再启用（95.2/95.7 后端半） | Service（零改动） | `patch_tenant` status 白名单 | 既有 active/expired/disabled 透传保持；测试钉住双向 |
| 列表失败信封（95.5 后端半） | 统一异常处理器（零改动） | `platform_core/exceptions/handlers.py` | AppException→{success:false,code,message,data非list}；前端失败句可判别 ≠ 空表（FR-84 同句式前提） |
| 越权 404 同形（95.6） | Router 既有守卫（零改动） | `backend/app/api/v1/admin.py` `require_platform_admin_or_404` | /enterprise 租户 404 语义不变（QA-02/ADR-0021 v2）；测试钉住 name/status 两动作 |

**分层依赖核对**：☑ Router 未 import ORM ☑ Service 未返回 ORM 对象 ☑ Repository 未调 Service ☑ ORM 与 Schema 互不 import（ruff + arch.sh 佐证）

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `backend/services/tenant_admin_service.py` | 修改 | `RESERVED_TENANT_NAMES` 常量 + `_assert_name_available`（冲突域）+ `list_tenants` 行带 `is_platform_default` + `patch_tenant` 常规企业改名分支（elif 接在平台守卫后） |
| `backend/services/user_service.py` | 修改 | `create_user`：`tenant_id is None or == 0` → platform 租户（+3 行注释） |
| `backend/app/api/v1/admin.py` | 修改 | 仅 `patch_tenant` docstring（本票路由零新增） |
| `platform_core/schemas/auth.py` | 修改 | 仅 `AdminUserCreateRequest.tenant_id` 注释（过期句修正：NULL 不挂租户 → 统一挂 platform） |
| `backend/tests/test_t27_tenant_admin_enhance.py` | 新增 | 11 例（红 7 + 既有行为钉住 4；GWT 逐条对应见 §6） |

**与票里「会改哪些文件」一致**：☑ 是（tenant 写服务单点扩字段 + user_service 建号路径核对；零 DDL、零新端点）

**未触碰「不许改的文件」**：☑ 确认（未做 T-28 UI；未动 T-24 恢复；未回退 T-26 测试；未改任何 GWT/schema 字段）

> 注：共享工作树中同文件含 T-24/T-26 等他票改动（git diff 为累计）；本票切片以本表为准。

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 冲突判定 + 改名写入 | 同一 service 方法（单条 UPDATE） | 判定在 mutation 前；拒绝路径零 commit（无半写） |
| 显式名查重（应用层集合判等）与写入 | 同 session | 小表管理面在册判重，不依赖 name 唯一索引（slug 才是唯一键——identity 稳定，改名不动 slug） |

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | 业务自然键：同名 PATCH = no-op 放行（新名==现名跳过判定与写入） |
| 保证方式 | 判等前置 + 单 UPDATE；slug 不参与改名（relay/gateway alias 引用不受改名影响） |
| 重复请求返回 | 200（与既有 quota/status PATCH 同口径） |

☐ 未使用「先查后插」（本票无插入路径；改名查重是拒绝语义非幂等键）

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 改名撞名竞态（两超管并发改同名） | 应用层判重 + 单 UPDATE | 竞态窗口内可能双写同名——name 非唯一键且管理面单写者（平台超管），契约未要求唯一索引（db-spec §「扩保护与编辑语义」零 DDL）；不擅自加约束（需变更回 /dba） |
| status 流转 | 既有白名单透传 | 非法值静默忽略（白名单外不动，既有测试钉住） |

### 外部依赖

➖ N/A（纯 DB 读写，无外部调用、无 Redis、无事件上报——票面无 `tenant_renamed` 事件要求，未自创事件）。

### 关键决策记录

- **冲突判等在应用层精确比对**：MySQL utf8mb4 排序规则对 `name` 列可能大小写不敏感，SQL 判等跨方言漂移；取既有名集合在 Python 精确判等，SQLite（测试）与 MySQL（生产）同语义。保留名同样精确匹配（"AutoAgents" 全形；不发明大小写折叠规则）。
- **「平台租户」保留名与既有名双保险**：platform 行在库时既有名判重即拦；platform 行缺失（未跑 024）时保留名集合仍拦（与 T-26 种子守卫同防御口径）。
- **0→platform 映射**：前端 Users.tsx 现状在客户端把选项值 0 归一为 null（`!payload.tenant_id → null`），后端此前只认 None。本票把 0 显式纳入同一映射——直打 API 传 0 不再 422「租户不存在: 0」，归属统一显示「平台租户」（行为不变、归属清晰）。仅建号路径（票面口径）；update_user 未扩。
- **95.5 信封钉法**：失败 ≠ 空表的可判别性 = data 非列表 + success:false + code（DatabaseException→500 信封）；失败句/重试按钮是 T-28 UI 面。
- **两读面同一真相**：企业管理页（enterprise.ts）与运营台（platformOps.ts）同消费 `GET /admin/tenants`——同显由端点唯一性结构性保证，测试断言改名后列表即库即同显。

## 4. ORM 与 DBML 对齐

☑ 本票零 schema 改动（`is_platform_default` 为响应推导字段，非列；改名/停用均既有列）。未自行加字段/改类型。

```
$ bash tools/check/db_migrations.sh
✓ 迁移破坏性变更检测通过
exit: 0
```

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | `patch_tenant`/`list_tenants`/`create_user` 既有入口 logger.info（R10）；`fields=sorted(body.keys())` 只记键名不记值 |
| 错误日志上下文 | 冲突拒绝经统一处理器 warning（含 request_id + code）；句即用户可见中文句 |

**日志脱敏核对**：☑ 无密码 ☑ 无 token（改名/列表路径无敏感载荷）

## 6. 自测证据

> 命令与退出码**原样粘贴**。红=实现前（tdd：新行为各格真红；既有行为钉住格本就绿）。共享工作树，全量前已定向。

```
$ uv run pytest -q backend/tests/test_t27_tenant_admin_enhance.py      # 红（实现前）
7 failed, 4 passed in 2.95s
exit: 1
（红因核对：改名未生效/冲突未拒绝×4、列表无 is_platform_default、tenant_id=0 → 422「租户不存在: 0」；
  4 绿 = 95.4 空归属/95.5 信封/95.6 越权/95.7 双向——既有行为钉住，票面预期「现状已如此，核对+测试钉住」）

$ uv run pytest -q backend/tests/test_t27_tenant_admin_enhance.py      # 绿（实现后）
11 passed in 3.42s
exit: 0

$ uv run pytest -q backend/tests/test_t26_base_protection.py backend/tests/test_b1a_admin_coverage.py backend/tests/test_r5_r7_fixes.py backend/tests/test_admin_users_crud.py
30 passed in 4.97s
exit: 0
（T-26 守卫零回退 + admin/users 相邻面）

$ uv run pytest -q backend/tests/test_saas_signup_expiry.py backend/tests/test_saas_rbac_deep.py backend/tests/test_saas_quota.py backend/tests/test_saas_r13_overwrite.py
38 passed in 10.47s
exit: 0
（租户域相邻套件）

$ uv run ruff check backend platform_core scripts
All checks passed!
exit: 0

$ uv run pytest -x -q backend/tests
1460 passed, 37 skipped, 7 warnings in 156.60s (0:02:36)
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
| 95.1 改名成功·两读面同显·他企不受影响 | `test_gwt_95_1_rename_success_both_surfaces_same_truth`（库级+列表双断言） | ✅ |
| 95.1 尾句·重名冲突拒绝中文 | `test_gwt_95_1_rename_conflict_with_existing_name_rejected`（句字面断言） | ✅ |
| 95.1 尾句·保留名（平台租户/AutoAgents） | `test_gwt_95_1_rename_conflict_with_reserved_names`（参数化两支） | ✅ |
| 95.1 边界·名称长度 | `test_gwt_95_1_rename_too_short_rejected`（422） | ✅ |
| 95.2 前半·平台租户改名→T-26 句保持 | `test_t26_base_protection.py::test_platform_tenant_rename_rejected`（零回退） | ✅ |
| 95.3 后端半·is_platform_default + 无 AutoAgents 名 | `test_gwt_95_3_list_marks_platform_default` | ✅ |
| 95.4·空 tenant_id → platform（钉住） | `test_gwt_95_4_user_without_tenant_lands_on_platform`（tenant_name=「平台租户」） | ✅ |
| 95.4·0 → platform（显式化） | `test_gwt_95_4_user_with_zero_tenant_maps_to_platform` | ✅ |
| 95.5 后端半·失败信封形态 | `test_gwt_95_5_list_failure_envelope_shape`（data 非列表） | ✅ |
| 95.6·越权 404 同形（编辑+停用） | `test_gwt_95_6_tenant_admin_direct_patch_404_shape`（名称与状态不变） | ✅ |
| 95.2/95.7 后端半·停用⇄再启用 UPDATE 成功 | `test_gwt_95_7_disable_then_reenable_roundtrip`（库级+列表同显） | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（单 UPDATE + 前置拒绝，拒绝路径零 commit；无多步写） | |
| 幂等 | 同名 PATCH no-op（并入 95.1 成功用例的判定前置；契约未列独立 GWT） | ✅ |
| 并发写 | ➖ N/A（管理面单写者；name 非唯一键为 db-spec 既有口径，见 §3） | |
| 外部依赖失败 | ➖ N/A（无外部依赖） | |

## 7. NFR 验证

票面无专属 NFR 行；NFR-05 权限矩阵面（越权 404 同形）由 95.6 用例覆盖。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/frontend`（T-28） | ① 列表行新增 `is_platform_default: bool`（slug=platform 推导）——「默认归属」标注直接消费；② 改名冲突 400 句=「企业名称不可用: {name}」（字面，测试钉住）；③ 建号归属 Select 的 0 选项后端已显式接（0/None 都挂平台租户，`tenant_name` 返回「平台租户」）；④ 停用/再启用仍走 PATCH status（disabled/active），平台租户行后端恒 active+「平台租户」名（T-26 守卫兜底）。 |
| `/qa` | ① 三处中文句为字面断言（冲突句/两句 T-26 守卫句），改文案需同步测试；② 冲突判等为**精确匹配**（"AutoAgents"≠"autoagents"），大小写折叠未冻——若需折叠属 GWT 变更，回 /pm；③ 并发改名同名竞态窗口存在（name 无唯一索引，db-spec 零 DDL 口径），管理面单写者下未视为缺陷。 |
| `/architect` | 无契约歧义。注：contract §7.9「无归属新用户默认挂平台租户」在 API 面的语义 = tenant_id None/0 二形同映射（前端归一 + 后端显式），已按票面「行为不变归属清晰」落。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（定向 11/11 + 相邻 68 + 全量 1460 passed）
- [x] 契约落位表已核对，分层无违规（ruff + arch.sh）
- [x] 零 schema 改动（is_platform_default 为推导字段）
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`
- [x] 日志已脱敏（fields 只记键名）
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」（无插入路径）
- [x] 条件更新 `rows == 0` 已处理（N/A：单 UPDATE 经 ORM flush，无裸条件更新）
- [x] 外部依赖四件套 N/A（无外部依赖）
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报（无新项；大小写折叠口径预防性提示给 /qa//architect）
