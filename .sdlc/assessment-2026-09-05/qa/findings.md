# QA 测试体系评估报告 — auto_agents（2026-09-05）

评估人：SDLC 测试工程师（只读评估）。数据来源：`uv run pytest -q --collect-only`（784 用例）、路由清单（`create_app()` 实际注册 155 条）、全量 grep 对照、6-8 个测试文件深读、git fix 提交抽样 6 个。未修改任何代码。

## 一、总体判断

**后端测试体系底子扎实（784 用例、service 层覆盖广、无 assert True、有显式回归文件），但存在三个结构性盲区：API 层 36% 端点零 HTTP 测试、CI 的 MySQL 保真通道只覆盖 3/87 个测试文件（约 96% 用例永远只在 SQLite 上验证）、全局 admin 兜底鉴权使"忘加 RBAC 守卫"类缺陷在测试里必然全绿。** 分层策略本身正确（service 层为主、db_client 真库接线、E2E 只在特性级豁免），抽查的用例质量整体高于平均水准（test_saas_members.py 是范本级），但弱断言面（9 个无断言 + 28 个仅断言状态码）与高危类缺陷（方言 500、越权 403）无回归沉淀，构成"覆盖率数字好看、死角仍在"的典型风险画像。

### 量化覆盖缺口

| 维度 | 数字 | 说明 |
|---|---|---|
| 业务路由总数 | 151 | 155 - 4 框架路由（docs/openapi.json/redoc/oauth2-redirect，豁免） |
| 无 HTTP 层测试的端点 | **≥55 / 151（36.4%）** | 静态前缀 grep + 常量拼接人工复核；spiders 模块占大头 |
| spiders 模块 API 缺口 | **31 / 34（91%）** | 仅 `GET registry`、`GET tasks`、`POST tasks/{id}/control` 有 HTTP 测试；`POST /spiders/run`（核心提交入口）、schedules/templates/definitions/alert-rules 全部 CRUD、results/export、nodes、files、proxy-health 均无 HTTP 层测试（部分有 service 层测试兜底） |
| service 层覆盖 | 36/40 模块有对应测试 | 仅 capability_service / spider_service 无直接 import（部分经 API 层间接覆盖） |
| 弱断言用例 | **37 / 784（4.7%）** | 9 个无任何断言（靠"不抛异常即通过"）+ 28 个仅断言 status_code |
| fix 提交回归沉淀率 | 3 / 6（50%） | 抽查 6 个，3 个无测试沉淀，且均为高危类别 |
| CI MySQL 真库验证 | **3 / 87 测试文件** | ci.yml 保真通道只跑 mysql_fidelity/db_fixtures/alembic_baseline 三个基建文件 |
| 前端页面覆盖 | admin 3/25 页面（12%），official 1/5 | 测试文件 7 个（含 2 个 App 冒烟 + 1 个 hook） |

## 二、FINDINGS（按严重度排序）

### F1. spiders 模块 34 个 HTTP 端点仅 3 个被测，POST /spiders/run 零 HTTP 覆盖 — major
证据：`backend/tests` 全量 grep 仅命中 `/api/v1/spiders/registry`（6 处）、`/api/v1/spiders/tasks`（2 处）、`/api/v1/spiders/tasks/1/control`（1 处）；`POST /api/v1/spiders/run`、`POST /templates/{id}/run`、schedules/templates/definitions/alert-rules 的 CRUD HTTP 端点无任何请求级测试。service 层有 test_spider_task_flow.py / test_spider_datacenter_crud.py 兜底业务逻辑，但参数校验、错误映射、鉴权接线（HTTP 层）完全未验证。
建议：优先补 `POST /spiders/run`（含非法 spider_name、缺 URL、超限参数的负向用例）与 schedules CRUD 的 API 层往返；其余 CRUD 可按 pairwise 裁剪补 happy + 1 条负向。

### F2. conftest 全局 override get_current_user：无凭据即 admin，RBAC 守卫缺失在测试中不可见 — major
证据：`backend/tests/conftest.py:75-93`（`_override_current_user` 无凭据返回 `CurrentUser(id=1, role="admin")`）；仅 8 个测试文件（test_saas_members/test_newapi_api/test_rbac_audit 等）显式带真实 JWT 测 401/403（全库 403/401 断言仅 14 处）。历史缺陷 `789165e fix(saas): 运营管理 403——admin 归位 default 租户 owner` 恰属此类且**无回归用例**（git show 该 commit 无测试文件变更）。任何新端点漏加守卫，默认测试全绿。
建议：为每个写操作端点补一条"低权限角色直接调接口返回 403"的最小负向用例（三类越权中的第三类——绕过前端直调）；789165e 补一条复现用例进回归集。

### F3. CI MySQL 保真通道只跑 3 个基建文件，约 96% 用例仅在 SQLite 验证，且方言缺陷 NULLS LAST 无回归用例 — major
证据：`.github/workflows/ci.yml:62-71`（保真子集 = test_mysql_fidelity.py + test_db_fixtures.py + test_alembic_baseline.py）；test_mysql_fidelity.py 自述只做"通道冒烟"（方言名、写读往返、建表清单）。生产缺陷 `0e0aaf8 fix(db): 资产目录 500——去除 MySQL 不支持的 NULLS LAST 语法` 修复后 `grep -rn nullslast backend/tests backend/app platform_core` **零命中**——同类排序语义缺陷无任何防线。另 `platform_core/models/skill.py:11`、`capability.py:7` 使用 MySQL 方言 JSON 列，SQLite 下 create_all 退化为普通列。`test_saas_members.py:58-60` 注释明确承认"SQLite 隐式 RETURNING 掩盖 MySQL 的 MissingGreenlet"。
建议：① 为排序/NULL 语义、JSON 列、隐式 RETURNING 依赖处补标注"需真库验证"的用例并入保真子集；② 保真子集逐步扩容（先含 saas/skills/spider 的 repository 密集文件）。

### F4. admin/rbac/configs/newapi/capabilities 的 20+ 端点无 HTTP 测试（部分无任何层测试） — major
证据：无 HTTP 测试清单（grep 复核）：`GET /admin/stats`、`GET /admin/audit-logs`、`GET|PUT /admin/notify-config`；rbac departments 全 CRUD 5 端点 + `GET /rbac/menus/tree`；`GET /configs/`、`PUT /configs/{key}`（configs 仅 test_config_service.py 纯 service 层）；`GET /newapi/channels`、`PUT|DELETE /newapi/channels/{id}/config`（渠道配置面 API 层缺）；capabilities 的 scan-plugins/scan-experts/teams CRUD/plugins verify 7 端点；`GET /tenants/me/usage`；`GET /api/v2/health/{db,storage}`；external 的 `GET /external/v1/public/stats`、`spider/results/{task_id}`、`POST /external/v1/webhooks/spider/callback`（webhook 仅有签名函数单测 test_webhook_signature.py，回调端点本身无请求级测试）。
建议：按风险排序补：webhook callback（幂等已有 service 层用例，补 HTTP 层签名拒绝路径）→ notify-config（PUT 配置变更）→ rbac departments → 其余。

### F5. 37 个弱断言用例（9 无断言 + 28 仅状态码） — major
证据：无断言 9 个（形态="不抛异常即通过"）：`test_spider_task_flow.py::test_webhook_skipped_without_url`（未断言 webhook 未被调用）、`test_webhook_secret_guard.py::test_guard_passes_with_real_secret`、`test_auth_rate_limit_failopen.py` 3 个、`test_ai_planner.py::test_force_fail_status_swallows_new_session_failure` 等。仅状态码 28 个：如 `test_admin_users_crud.py::test_create_user_duplicate_username_rejected`（只断 400，未断错误码/无副作用）、`test_external_api.py` 401 系列 7 个（未断 error code 与响应体）。
建议：无断言的 9 个补行为断言（mock.assert_not_called / 状态未变）；401/403 类至少补 `code` 字段断言；重复类操作补"第二条未创建"的副作用断言。

### F6. 高危缺陷类别无回归沉淀（方言 500、越权 403、前端侧边栏） — major
证据：抽查 6 个 fix 提交：带测试 3 个（efb7c39→test_llm_models_fetch.py、8256ef2→usePermission.test.tsx、4c1ee49→test_llm_protocol.py）；**无测试 3 个：0e0aaf8（MySQL NULLS LAST 500）、789165e（越权 403）、bea13b5（侧边栏反复消失）**。回归集意识存在（test_backend_fixes_regression.py 21 用例、test_r5_r7_fixes.py），但沉淀是选择性的且高危类别恰好缺席。
建议：立即为 3 个未沉淀缺陷补复现用例；在 CI 或 pre-push 增加"fix 提交必须含测试变更"的提醒钩子（软门禁）。

### F7. 9 个无断言用例中的 fail-open 语义依赖注释而非断言 — minor
证据：`test_auth_rate_limit_failopen.py::test_login_check_redis_error_fail_open` 等 3 个（Redis 故障时放行）以"不抛即通过"验证；fail-open 是安全敏感行为（限流失效），应有显式断言（如放行结果/计数器未写）。
建议：改为断言返回值 + FakeRedis 计数器状态。

### F8. 无时间冻结设施，expiry 类用例用真实时钟构造 — minor
证据：`grep -rln "freezegun|freeze_time|random.seed" backend/tests` 零命中；`test_saas_signup_expiry.py:67` 用 `datetime.utcnow() - timedelta(days=1)` 构造过期（不冻结时钟，"恰好过期/未过期"的界上边界无覆盖，午夜执行存在理论抖动）。
建议：引入 freezegun（或手工注入 clock）覆盖 `expires_at == now` 界上用例；随机数据统一固定种子。

### F9. 并发/幂等用例集中于 spider 与 ai_planner，auth/llm/admin 模块为零 — minor
证据：幂等/并发命名用例约 17 个，全部分布在 test_spider_*（repeat_callback_idempotent、never_spawns_twice）、test_ai_planner.py:464（concurrent_claim_conflict）、test_backend_fixes_regression.py:409（flush_retry 不双扣）。LLM provider 创建（唯一名约束）、admin 租户创建、token 签发均无并发用例。
建议：为 DB 唯一键竞争面（duplicate key on concurrent create）各补 1 条；token 签发补时间窗用例。

### F10. E2E 豁免理由在特性级成立，但项目级零浏览器 E2E 且无关键旅程验证 — minor
证据：`.sdlc/feat-llm-cooldown/state.yaml:14`：`{name: e2e, result: null, reason: 后端内部机制，无 UI 路径}`——就 cooldown 单特性而言理由成立（无 UI 路径）。但全仓库无任何 Playwright/Cypress；登录→建租户→建成员→配 LLM Key→发起爬虫的跨系统主干旅程无端到端验证；前端 admin 25 页面仅 3 页有组件测试。
建议：豁免维持特性级即可，但应补 1-3 条关键旅程 E2E（登录 + 建 LLM provider + 跑一次爬虫），数量控制在个位数。

### F11. 测试间共享全局 app + dependency_overrides 状态，曾有污染史，且未配置并行 — minor
证据：`conftest.py:209-216` autouse `_reset_get_async_db` 注释明言"防 test_ai_planner 直设 lambda 不清理"——测试互相污染已发生过一次并被加固；session 级 app + client fixture 意味着任何测试残留 override 会泄漏到后续测试；pyproject/ci 无 xdist 配置（串行执行，784 用例规模下反馈速度受限）。
建议：保持现加固；若引入 xdist，需先审计 session 级 fixture 的进程隔离安全性。

### F12.（正面基准）test_saas_members.py 与 test_exception_handlers.py 的用例质量可作为库内标准 — info
证据：test_saas_members.py:71-76（viewer 越权 403）、:120-140（owner 保护 + 自删保护）、:116-117（删除后列表副作用断言）、:58-60（created_at 回填口径固化防方言回归）；test_exception_handlers.py 用最小 app 隔离验证响应格式。factories.py 自增序号工厂与 stubs.py 唯一权威桩（含与 scrapy/utils 命名冲突的规避说明）均为良好实践。
建议：新用例以这两个文件为模板；将"副作用断言 + 真实 JWT 链路"写入 .agents/skills/verify 的自检清单。

## 三、附：覆盖矩阵空洞标注（按 SKILL 口径）

- ❌ 缺口：F1/F4 所列 ≥55 端点（HTTP 层）；9 无断言 + 28 弱断言用例
- ⚠️ 未覆盖（有原因，需动作）：MySQL 方言语义（CI 通道存在但只跑基建冒烟）→ 转扩容保真子集
- ➖ N/A：docs/openapi.json/redoc 4 框架路由；feat-llm-cooldown 的特性级 E2E 豁免（理由成立）
- ✅ 良好面：service 层 36/40 模块覆盖；spider/ai_planner 状态机与幂等用例充分；webhook 签名算法与 Scrapy 侧交叉验证（test_webhook_signature.py:26-29）；异常处理体系 7 用例格式断言具体
