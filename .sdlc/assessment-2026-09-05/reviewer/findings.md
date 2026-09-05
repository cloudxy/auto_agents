# G-新上下文独立审查报告（2026-09-05）

## 审查范围

- **主审工件**：当前未提交工作区 diff（9 文件，+149/-10）——backend/app/api/v1/members.py、backend/services/member_service.py、backend/tests/test_saas_members.py、frontend/admin/src/pages/Members.tsx、frontend/admin/src/pages/Spiders.tsx、frontend/admin/src/services/members.ts、platform_core/logger.py、run.py、run_backend.py
- **辅审工件**：最近 5 提交（HEAD=bea13b5）中被触及热点现状——members API / member_service / logger；另核对 platform_core/tenant_context.py、platform_core/models/{user,notification,operation_log,mixins}.py、backend/app/api/_helpers.py、platform_core/exceptions/、config/default/log.yml、scripts/check-arch.sh、frontend/shared/src/utils/errors.ts、frontend/admin/src/index.tsx、.venv 内 uvicorn config/_subprocess 源码
- **上游对照**：未提供 PRD/契约/覆盖矩阵 → **仅审自洽性**（对照文件内可见的 docstring 契约、前端文案、宪法红线），不审符合性
- **宪法**：.claude/rules/project_rule.md（12 红线 + 3 边界）
- **审查者复跑证据**（本人执行，退出码原样）：
  - `uv run pytest -q backend/tests/test_saas_members.py` → `8 passed in 5.72s`（退出码 0）
  - `uv run pytest -q backend/tests` → `773 passed, 11 skipped, 8 warnings in 45.21s`（退出码 0；11 个 skip 全部为 MYSQL_FIDELITY 显式说明，非静默跳过）
  - `bash scripts/check-arch.sh` → 13 红线 + 3 边界全 ✓，EXIT=0
  - `npx tsc --noEmit`（frontend/admin）→ 无输出，TSC_EXIT=0
- **范围外备注**：工作区存在未跟踪文件 sdlc.config.yaml（不属本 diff，未审）

## FINDINGS

### F-01 破坏性新端点 DELETE /members/{id} 零跨租户与 404 用例，且 User 不在隔离钩子自动过滤范围内
- 维度：3 证据有效性（兼 4 安全）
- 严重度：major
- 证据：
  - `backend/tests/test_saas_members.py:112-140` —— 新增 3 个用例仅覆盖：正常删除、owner 守卫（422）、自删守卫（422）；无跨租户越权、无 404（不存在 id）、无 viewer/operator 对 DELETE 的 403 用例（`test_viewer_cannot_manage` 只 POST）
  - `backend/tests/test_saas_r13_overwrite.py:73-100` —— R13 越权套件只覆盖 tasks/definitions/providers/registry，不含 members
  - `platform_core/models/user.py:8` —— `class User(SoftDeleteMixin, Base)` **未继承 TenantMixin**；`platform_core/tenant_context.py:136` 的 `with_loader_criteria(TenantMixin, ...)` 对 User 实体不注入任何条件 → `backend/services/member_service.py:118-120` 手写的 `User.tenant_id == tenant_id` 是该端点唯一租户防线，却无回归测试固化
- 建议：补两条用例（种子第二租户）：(a) B 租户 owner DELETE A 租户成员 → 断言 404 且 A 列表不变；(b) DELETE 不存在 id → 断言 404。另补 viewer token DELETE → 断言 403。

### F-02 「删除后审计保留」声明与租户审计视图实现矛盾
- 维度：6 契约一致性（兼 1 标准符合）
- 严重度：major
- 证据：
  - `backend/services/member_service.py:115` —— "operation_log.actor_id 为普通列（无 FK），审计留痕不因删号丢失"
  - `frontend/admin/src/pages/Members.tsx:130` —— Popconfirm 文案"账号与收件箱将被移除，**操作审计保留**；不可恢复。"
  - `backend/app/api/v1/members.py:120` —— 租户审计视图 `join(User, User.id == OperationLog.actor_id)` 为 **INNER JOIN**：成员被物理删除后，该成员作为 actor 的全部 operation_logs 行从 `/members/audit` 视图消失（`operation_log.actor_name` 冗余列存在却未用于租户收口）；平台侧 /admin/audit-logs 不受影响
- 对照：被删成员（如离职 admin）的历史操作在本租户审计页不可再查——与两处工件声明的"保留"相悖。
- 建议：审计租户收口改为不依赖 users 行存在（写审计时在 operation_logs 落 tenant_id，或用 actor 登记快照收口）；若维持现状，同步修正 member_service.py:115 与 Members.tsx:130 文案为"平台审计保留，本租户视图不再展示被删成员的操作"。

### F-03 并发删除同一成员未处理 rows==0（先查后删竞态 → 500）
- 维度：8 边界
- 严重度：minor
- 证据：`backend/services/member_service.py:118-129` —— SELECT 通过后 `session.delete(user)`；两个并发 DELETE 均通过 SELECT 后，后提交方 flush 时 DELETE 0 行命中 → SQLAlchemy StaleDataError → 兜底 500（而非 404/409），且删除结果对客户端语义不确定
- 建议：改用 `delete(User).where(User.tenant_id==…, User.id==…)` 语句并检查 `rowcount`，为 0 时抛 NotFoundException；或捕获 StaleDataError 转 404。

### F-04 members 模块 docstring 对隔离机制归因失实
- 维度：7 规范（宪法对照）
- 严重度：minor
- 证据：`backend/app/api/v1/members.py:4` —— "跨租户不可见经 users.tenant_id 行级过滤（**中间件 + 隔离钩子**）天然成立"；但 `platform_core/models/user.py:8` User 未继承 TenantMixin，`platform_core/tenant_context.py:124-136` 钩子仅对 TenantMixin 生效——对 User 查询不注入条件（当前实现靠 `member_service.py:78/103/118` 手写条件成立）
- 建议：修正 docstring 为"服务层显式 tenant_id 过滤"；或评估让 User 继承 TenantMixin 以获得钩子级兜底（与 F-01 联动）。

### F-05 「收件箱随账号清理」与 member.delete 审计写入均无用例固化
- 维度：3 证据有效性
- 严重度：minor
- 证据：`backend/services/member_service.py:113、128`（声明+实现）；`backend/tests/test_saas_members.py:112-117` 仅断言 `deleted is True` 与列表不可见，未断言 Notification 行清除，也未断言审计出现 action=member.delete
- 建议：删除用例预插一条该 user 的 Notification，删后断言行数为 0；并断言 `/members/audit` 含 `member.delete`。

### F-06 R7 门禁正则存在子模块导入盲区，members API 现状即在盲区内（辅审·预存系统性）
- 维度：7 规范
- 严重度：minor
- 证据：`scripts/check-arch.sh:71-72` —— R7 正则 `from.*\.models import` 只匹配包级导入；实际 API 层以子模块形式导入 ORM：`backend/app/api/deps.py:21`、`backend/app/api/v1/members.py:115-116`、`auth.py:126/146/188`、`rbac.py:17-18/62/97` 等均为 `from platform_core.models.<子模块> import …`，门禁报告 ✓（宪法 `project_rule.md:47` 明令"API 层禁止直接 import ORM 模型"）。本 diff 未新增违规（delete 端点未 import ORM）。
- 建议：正则改为 `from[[:space:]].*\.models(\.[a-z_]+)?[[:space:]]+import` 并清理存量导入；作为确定性门禁的盲区上报，不由审查者改判。

### F-07 run_backend 日志接管仅在主进程生效，--reload 子进程 uvicorn 日志无落点
- 维度：7 规范
- 严重度：minor
- 证据：`run_backend.py:99-118`（InterceptHandler 挂在 main() 进程 stdlib logger 上）；`.venv/.../uvicorn/_subprocess.py:76` —— reload 子进程仅重跑 `config.configure_logging()`：`log_config=None` 不重建 StreamHandler（僵死风险不复发），但 InterceptHandler 不跨进程传递 → 子进程 INFO 级 access/error 日志无 handler 消费（仅 WARNING+ 经 lastResort 落 stderr）。--reload 为显式开启路径（`run_backend.py:51`）
- 建议：将接管封装为可重入函数（如经 create_app 触发），或改用 uvicorn `log_config` dict 工厂注入 handler，使子进程重建后仍指向 loguru。

## 已查维度

| # | 维度 | 结论 |
|---|------|------|
| 1 | 标准符合（仅自洽性，无 PRD） | ⚠️ 见 F-02（diff 内可见契约：owner/自身不可删、收件箱清理、created_at 回填、react-query 首拉、日志接管均逐项核对有落点；唯"审计保留"声明与实现矛盾） |
| 2 | 标准质量 | ➖ 无上游 PRD/契约工件可审，声明此限制（GWT 可测性/契约六项无从对照；仅指出：删除端点无幂等策略与错误码契约文档，属无契约工件可审） |
| 3 | 证据有效性 | ⚠️ 见 F-01、F-05。测试非空心（断言具体：deleted is True、列表不含 id、422 状态码）；本人复跑命令+退出码全绿且 skip 均有显式理由 |
| 4 | 安全 | ⚠️ 关联 F-01/F-04。已核：租户过滤显式存在（4 处查询均带 tenant_id）、权限守卫 require_tenant_manager、ORM 参数化无注入、无密钥/敏感信息进日志（删除仅记 tenant/member/actor id）、无新增依赖、notification 批删经钩子再收窄租户 |
| 5 | 性能 | ✅ 无发现（无 N+1；删除为单条批量 DELETE + 单行 DELETE；refresh 为单次回读，必要且有注释） |
| 6 | 契约一致性 | ⚠️ 见 F-02。已核对齐项：前端 deleteMember ↔ DELETE /members/{id} ↔ ok 信封；404/422 经 `platform_core/exceptions/handlers.py:27-36` 返回 message，`frontend/shared/src/utils/errors.ts` 优先读 `data.message`，前端 catch 有 fallback（无 default 白屏路径）；tsc EXIT=0 |
| 7 | 规范（宪法逐条） | ⚠️ 见 F-04、F-06、F-07。check-arch 13 红线+3 边界本人复跑 EXIT=0；diff 新增代码 R10 入口 logger 存在（member_service.py:117）；R11 不涉及（无 redis 改动）；logger.py configure 修复与 LOG_FORMAT（config/default/log.yml:4 引用 {extra[request_id]}）及中间件 contextualize（backend/app/middleware/request_id.py:26）自洽 |
| 8 | 边界 | ⚠️ 见 F-03。已核：空/超长输入经路径参数 int 类型与查询过滤兜底（负数/乱串 → 404 或 422）；重复删除 → 404 幂等语义可接受；唯一 FK 依赖（notifications.user_id）已处理，全仓 grep 确认无其他指向 users 的外键 |

## 统计

blocker: 0 | major: 2 | minor: 5
