# 整治后全量重审（G-新上下文独立审查者 · 2026-09-05）

## 审查范围

- **变更集**：`git diff bea13b5..HEAD`（12 提交 c1b302a→f294fd1，109 文件 +4410/-1106，工单 T1-T11）
- **上游对照**：`.sdlc/assessment-2026-09-05/00-summary.md`（17 问题清单）；各工单自述（.scratch/p0-p1-2026-09/issues/T*.md）**仅作处置线索、不作为 fixed 证据**，fixed 判定一律落到代码/测试/可复现命令
- **宪法**：`.claude/rules/project_rule.md`（R1-R13 + B1-B3）
- **审查者自跑的确定性命令与退出码**：
  - `uv run pytest -q backend/tests` → **834 passed / 12 skipped，EXIT=0**（49.0s；12 skip 逐一列出理由：11×MYSQL_FIDELITY + 1×方言回归标注 CI 通道，全部有解释）
  - `bash scripts/check-arch.sh`（干净树）→ **EXIT=0**（13 红线 + 3 边界全绿）
  - R7 拦截实验：构造 `backend/app/api/v1/_tmp_r7_probe.py`（子模块 from-import / 多级 / 裸 import 三形式）→ **EXIT=3，三条全部命中**，探针已删
  - `bash scripts/check-db-migrations.sh`（干净树）→ **EXIT=0**；SM-5 拦截实验：构造违规迁移（add_column NOT NULL 无 server_default）→ **EXIT=1 命中**，探针已删
  - 路由覆盖清点：create_app() 提取全部路由 × 测试目录全路径正则匹配 → **业务路由 144，无 HTTP 层测试痕迹 55 条（38%）**（清点脚本见审查过程，路径参数段按 `[^"']+` 归一）
  - `npx jest Members.test.tsx usePermission.test.tsx` → **6 passed，EXIT=0**（含 1 条 test.failing 缺陷钉）
- **限制声明**：MySQL 真库演练（T5/T9 的 up→down→up 记录）为工单留痕，本机未复跑（无 MySQL 环境）；本报告对其只做「留痕完整性」判定，不做行为判定。

## FINDINGS

### F-01 平台超管撤销后，存量 token 在 TTL 内仍持有 platform_scope（行级隔离全开）
- 维度：4 安全
- 严重度：major
- 证据：`backend/app/middleware/tenant_context.py:47-49` —— `if payload.get("is_platform_admin"): with platform_scope()`，只信 JWT claim，不重查 DB；而 `backend/app/api/deps.py:90` 的 `is_platform_admin=bool(user.is_platform_admin)` 从 DB 快照重算（守卫层 403 立即生效）。两源不一致窗口 = token TTL。
- 对照：`deps.py:82-83` 注释宣称「权限字段一律从 DB 行快照重算（禁用/降级立即生效）」——该声明对守卫成立、对**隔离作用域**不成立：被撤销超管（账号仍 active、role 为 viewer/operator 可过 require_login/require_operator）的在途 token 请求仍以 platform_scope 执行，依赖自动注入过滤的端点（R13 套件 `test_platform_scope_sees_all` 即证明该 scope 下跨租户全可见）暴露他租户数据。
- 建议：中间件进入 platform_scope 前用 user_id 复核 DB 行（一次主键直查，代价可接受）；或把 scope 判定挪进 get_current_user 之后的依赖层，让「DB 快照重算」成为唯一权限源。

### F-02 members 软删 422 口径：FE 创建侧未处理，同名重建静默失败
- 维度：6 契约一致性
- 严重度：major
- 证据：`backend/services/member_service.py:64-73` —— 同名（含软删占位行，username 永久占用口径）与同邮箱 raise `ValidationException`（422，`platform_core/exceptions/business.py:60`）；`frontend/admin/src/pages/Members.tsx:48-55` `onCreate` 无 try/catch，`onReset`（:77-83）同型；`frontend/shared/src/api/client.ts` 拦截器只处理 401，无全局错误提示。
- 对照：T4 声称「Members 删除软删口径对齐」——删除侧（onDelete + Popconfirm 文案）确实对齐且有测试（Members.test.tsx:29-37），但软删口径的**直接下游场景**（删后同名重建 → 422）在 FE 走 unhandled rejection：用户点「创建」无任何反馈。
- 建议：onCreate/onReset 补 `try/catch + apiErrorMessage`（同文件 onDelete:85-93 已有正确范式可抄）。

### F-03 零 HTTP 覆盖路由数未收敛：55→55（36%→38%），「盲区换血」而非「盲区治理」
- 维度：3 证据有效性（整改承诺 vs 实效）
- 严重度：major
- 证据：审查者全量清点（命令与退出码见审查范围）：业务路由 144 条，无任何 HTTP 层测试痕迹 **55 条（38%）**；原报告为 151 条中 ≥55（36%）。T10 覆盖了原盲区中最高危 5 组（POST /spiders/run 含 401/403/422/副作用、tasks store 404、admin/audit-logs、admin/notify-config、webhook 回调 HMAC 三态），但 rbac/departments 4 端点、configs 2 端点、spiders alert-rules/schedules/templates 13 端点、newapi channels 3 端点、capabilities 7 端点等仍全裸。
- 对照：T10.md §8 自认「本票切片仅 6 端点 + run 入口」（留痕诚实）；但对外若引用「36% 盲区已治理」即为失实——分母缩小（rbac 收口删并路由）还使比例微升。
- 建议：后续切片按破坏性排序（departments DELETE / alert-rules DELETE / templates DELETE / configs PUT 优先）；在 T10.md 顶部补一行整治前后对照数字，防口径漂移。

### F-04 POST /admin/tenants 守卫弱于同组端点：租户 admin 可自行创建租户
- 维度：4 安全（权限边界）
- 严重度：minor
- 证据：`backend/app/api/v1/admin.py:148-151` —— `create_tenant_minimal` 守卫为 `require_admin`（role 层，租户内 role=admin 的用户可过）；同文件 `list_tenants`（:138）与 `patch_tenant`（:168）均为 `require_platform_admin`。租户管理员可无限创建空租户（无平台确认步骤）。存量守卫（bea13b5 同款），本次重构把该端点内联逻辑迁入 TenantAdminService 但未对齐守卫，无工件声明该弱化有意。
- 建议：对齐 require_platform_admin，或在该端点注释声明「租户 admin 自助建司」的产品决策。

### F-05 迁移 024 上线即存量平台超管 token 全部 401，部署影响未声明
- 维度：6 契约一致性（部署清单）
- 严重度：minor
- 证据：`backend/app/middleware/tenant_context.py:51-56`（无租户归属的非平台超管 token 直接 401）+ 024 之前签发的平台超管 token 形态（无 `is_platform_admin` claim / `tenant_id=NULL`）——两相结合，024 后在途超管 token 必落 401 分支。`024_users_tenant_not_null.py` 的 docstring 与 T5.md 均未声明「上线 = 存量超管强制重新登录」。
- 建议：024 注释或 deploy.md 发布清单补一行（安全收紧的预期代价，操作侧只需重登）。

### F-06 中间件 scope（claim tenant_id）与鉴权快照（DB tenant_id）在用户迁移租户后不一致
- 维度：6 契约一致性
- 严重度：minor
- 证据：`backend/app/middleware/tenant_context.py:62`（scope 用 JWT claim）vs `backend/app/api/deps.py:88`（CurrentUser.tenant_id 用 DB 值，`tenant_id if user.tenant_id == tenant_id else user.tenant_id` 恒等式写法实际取 DB）。用户被 update_user 改挂新租户后 token TTL 内：自动注入按旧租户、service 显式 where 按新租户 → 同语句 AND 两租户恒空（读空/写失配）。方向是更严格（非越权），表现为功能异常。
- 建议：中间件解析 claim 后与 DB 快照对齐一次；或 deps.py:88 恒等式简化为 `user.tenant_id` 并加注释（当前写法绕但语义恰好安全）。

### F-07 迁移 025 核心语义（删后可重建同名）无自动化回归钉
- 维度：3 证据有效性
- 严重度：minor
- 证据：`backend/tests/` 全目录 grep `alive_flag|删后重建|recreate` 零命中；CI 保真通道跑的 `test_alembic_baseline.py` 只做 head→base 的 DDL 对拍，不覆盖行为断言。T9.md §3 有真实 MySQL 演练记录（删后重建 ✓，留痕完整），但属一次性人工证据。5 表 ORM 均为 `Column(SmallInteger, Computed(...))`（如 `platform_core/models/department.py:28`），SQLAlchemy 视为服务端生成、INSERT 不会试图写入——ORM 侧无坑；SQLite（create_all 同构）也支持生成列 + 唯一索引 NULL 不判重，补测试成本低。
- 建议：在 SQLite 通道加一条数据行为用例：同租户建 A → 软删 → 重建同名 A 成功 → 再软删再重建（多次删建），断言无 IntegrityError。

### F-08 LoginRequest 新增 tenant_slug 预留字段（未消费），契约面超前于功能
- 维度：1 标准符合（范围）
- 严重度：minor
- 证据：`platform_core/schemas/auth.py:19-20` + `backend/app/api/v1/auth.py:64-66`（「暂不消费，仅观测流量」）。有兼容用例钉住（test_auth_login_tenant.py:122-130），但未来消费时（带 slug 精确查询）将与「缺省密码消歧」形成双语义，未留 ADR。
- 建议：接受现状（有注释+用例），消费时补 ADR 即可；本条仅记录。

### F-09 API 层 commit 3 处豁免无机械门禁，存在回潮通道
- 维度：7 规范
- 严重度：minor
- 证据：残留 3 处 = `backend/app/api/v1/tenant_signup.py:67`、`admin.py:157`、`admin.py:173`，ADR-0007「范围例外」明确留痕（tenant 域红线禁改，处置合规）；但 ADR 自认「check-arch 暂无对应机械检查」——后续新路由 commit 无门禁拦截，豁免清单也不会自动清零。
- 建议：加 R14（`grep -n "await session.commit()" backend/app/api/` 白名单=这 3 处）成本低收益高；tenant 域收口工单落地后清零。

### F-10 before_flush 断言不覆盖 session.dirty 的跨租户改归属
- 维度：4 安全（隔离模型缝隙）
- 严重度：minor
- 证据：`platform_core/tenant_context.py:125` `for obj in session.new` —— 只断言 INSERT；ORM 属性式 `user.tenant_id = X` 赋值走 flush 的 UPDATE（非 do_orm_execute 路径），既无断言也无注入。当前无触发路径（update_user 的 tenant_id 修改受管理面守卫 + 查询自动过滤双保险；实测 834 passed 无回归），属防线声明（「写侧断言」）与实现（仅 INSERT 侧）的缝隙。
- 建议：tenant_context.py 注释把「写侧断言」收窄为「新行归属断言」，或补 dirty 检查（对象租户从 A 改 B 且非平台态时拒绝）。

## 已查维度

1. 标准符合（17 问题逐条对照代码）—— ⚠️ 见 F-03/F-08（承诺实效差距、预留字段）
2. 标准质量（工单 GWT 可测性抽查 T3/T5/T9/T10）—— ✅ 无发现（验收标准均带命令+退出码形态；T9 演练记录含对拍数字）
3. 证据有效性 —— ⚠️ 见 F-03/F-07（覆盖数字未收敛、025 无自动钉）；正面：T3 reload 复现记录带真实 PID/日志；conftest 收紧为真实机制（匿名 401 默认 + 特权 opt-in + autouse 归位，test_notify_config_anonymous_401 的 docstring 证明作者理解共享 TestClient 陷阱）
4. 安全 —— ⚠️ 见 F-01/F-04/F-10；登录消歧（哑哈希时序对齐、多中不泄露候选数）、软删拦登录、伪造租户 token 401、HMAC 防重放三态均有测试；R11 无违规
5. 性能 —— ✅ 无发现（新增 service 无循环查库；member 删除为单事务两条语句；025 生成列 VIRTUAL 为 INSTANT/INPLACE，量级评估留痕）
6. 契约一致性 —— ⚠️ 见 F-02/F-05/F-06；健康检查三处对齐成立（`/api/v1/health/deep` ↔ Dockerfile HEALTHCHECK ↔ compose healthcheck ↔ watchdog probe 同打 503 语义端点，test_health_api.py 三分支断言）；members 删除侧 FE/BE 对齐且有测试
7. 规范（宪法逐条）—— ⚠️ 见 F-09；R1-R13/B1-B3 全绿（check-arch EXIT=0 + R7/SM-5 拦截实验通过）；B1 收口实证：platform_core/tenant_context.py 零业务表名（grep 验证，注册机制 + R13 双向校验真跑 create_app）
8. 边界 —— ✅ 无发现（024 去重按目标组键分组正确、回填子查询缺租户时 fail-loud；delete_member rowcount==0→404 有竞态用例；notify-config 拒绝路径零写入有副作用断言；watchdog dry-run/只告警缺省/无探测工具降级均有处置）

## 17 问题处置核对表

| # | 原问题 | 处置 | 证据（提交 + 钉） |
|---|---|---|---|
| P0-1a | 登录无租户维度（同名 500） | **fixed** | c406075：`user_repository.py:18` 返回 list + `auth_service.py:74-82` 密码消歧；钉 = test_auth_login_tenant.py 6 用例（含双中 401、文案不泄露候选数） |
| P0-1b | NULL 租户绕过唯一键 | **fixed** | 024 回填+NOT NULL+`(tenant_id,username)` 唯一键；钉 = test_users_null_tenant_contract.py 3 用例 + test_register_creates_default_tenant_user |
| P0-1c | User 未挂隔离钩子 + R13 无 members | **fixed** | `user.py:8` 继承 TenantMixin；R13 套件补 members/admin_users/伪造 token/NULL token 拒绝（test_saas_r13_overwrite.py 130-199） |
| P0-2a | R7 正则假阴性 | **fixed** | 7504ab9 正则真化（含 external_api）；**审查者构造违规探针实证 exit 3 三形式全拦** |
| P0-2b | 迁移门禁管道丢计数 + 未进 CI | **fixed** | 85c84bc report_lines 主 shell 计数 + ci.yml 增 db-migration-gate job；**SM-5 探针实证 exit 1** |
| P0-3 | members 票（跨租户/审计矛盾/并发/注释/收件箱） | **fixed**（遗留 F-02） | 7504ab9+c406075+e88cef6：软删保审计（JOIN 不滤 deleted_at，`member_service.py:177-184`）+ 17 用例库级断言；FE 删除文案对齐 Members.test.tsx |
| P0-4 | --reload 启动路径 exit 1 | **fixed** | c1b302a 工厂字符串 + `create_app_for_reload` 子进程重初始化（run_backend.py:76-94,139-150）；证据 = T3.md 真实进程复现/热重载触发记录（无自动化回归钉，轻微） |
| P1-1 | service 循环依赖三组 | **fixed** | 20b9521 llm_common 下沉 + TYPE_CHECKING 单向（skill_service.py:26）+ seam；审查者 grep import 图无环 |
| P1-2 | 事务所有权分裂 | **fixed（3 处 ADR 豁免）** | 1b1d4ce：API commit 38→3；ADR-0007 D1-D5 + test_transaction_ownership.py；豁免留痕（见 F-09） |
| P1-3 | API 跳层直连 repository | **fixed** | grep skills/public_skills/external public 零 repository import；SpiderQueryService 等薄读方法承接 |
| P1-4 | 基建穿透业务表名 | **fixed** | 2ef52dd：`tenant_isolation.py` 唯一事实源 + 注册机制 + R13 双向校验（真跑 create_app，组装断线即红） |
| P1-5 | 迁移健康三件 | **fixed（025 无自动钉，F-07）** | 3cda226：023 down JSON_REMOVE 对称 / 019 down 孤儿归档还原 + 020 MySQL 1553 附带修 / 025 生成列 5 表；T9.md 真库 up→down→up 演练记录；CI test_alembic_baseline head→base |
| P1-6 | 测试三大盲区 | **partial** | conftest 兜底收紧 fixed（匿名 401 默认，69 用例迁移，834 passed）；CI 保真 3→8 文件 fixed；**36% 零覆盖未收敛**（55→55/38%，F-03；T10 §8 自认） |
| P1-7 | 交付成熟度 | **partial** | 深探测/compose 加固/看门狗/回滚手册 fixed（df5db02 + docs/ops/deploy.md 173 行）；**监控告警 0 条 = open（接口预留）**——T11.md §5 自认「按票范围」，列入 incident 复盘改进项；product-review 风险排序未列监控（其视角声明为「商业短板」，非隐瞒） |
| P2-1 | dba：冗余索引/JSON RBAC/ENUM/时区 | **open** | 无对应提交与工单 |
| P2-2 | run_backend 日志接管落位编排脚本 | **partial** | T3 顺手解决一半（工厂为 import string，reload 子进程不再依赖父进程接管）；仍未迁 platform_core/logger |
| P2-3 | 前端页面测试覆盖 / E2E 豁免 | **partial** | usePermission 4 用例 + test.failing 钉（jest 6 passed 实证）；25 页面覆盖面未扩 |

**计数：fixed 12 / partial 4 / open 1**（P2-1 完全 open；P1-6、P1-7、P2-2、P2-3 partial）

## 三个整改承诺的核验结论

1. **「门禁全绿恢复可信」——成立（本审查者独立实证）**：R7 构造 3 形式违规文件 exit 3 全拦；SM-5 构造违规迁移 exit 1 拦截；迁移门禁已进 CI（db-migration-gate job）；干净树 check-arch / check-db-migrations / pytest 三道 exit 0。
2. **「36% 零覆盖」——未兑现收敛**：实测 55/144（38%）vs 整治前 55/151（36%）。最高危入口（POST /spiders/run）确已补齐（含 401/403/422/副作用断言），但盲区总量零下降，工单自认「切片仅 6 端点」。
3. **「监控告警 0 条」——如实**：T11 只交付接口预留（watchdog webhook 动作 + 告警五步 runbook），工单 §5 明确声明「完整监控栈不在本票」并挂 incident 复盘改进项；product-review 风险排序为「产品/商业视角」且已声明口径，未把预留包装成落地。

## 统计

blocker: 0 | major: 3（F-01/F-02/F-03）| minor: 7（F-04…F-10）
17 问题处置：fixed 12 / partial 4 / open 1
