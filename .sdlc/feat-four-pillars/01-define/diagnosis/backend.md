# 定义帽 · Backend 诊断（feat-four-pillars）· 刷新

| 字段 | 值 |
|------|----|
| 角色 | backend（只读诊断，不实现 API） |
| 日期 | 2026-09-07 |
| 泳道 | L4 |
| 刷新相对 | 同路径上一稿（设计 D 线对照）→ **对齐冻结 `spec.md` Wave 0/1 FR + ADR-0014** |
| 输入 | `01-define/spec.md` v1 冻结集；`power-market-design.md`（Accepted）；`CONTEXT.md`；`backend/app/` + `backend/services/` + `backend/tests/`；`02-shape/adr-0014`；`.sdlc/_lessons.md` |
| 宪法 | `.claude/rules/project_rule.md` + `sdlc.config.yaml`；契约回 architect / 表结构回 dba / 验收口径回 pm；本帽不改合同、不写迁移、不写测试 |

---

## 0. 结论（给 PM / architect 的一句话）

Wave 0 后端能开工、且 **不依赖 Power Market schema**：收平台写守卫（FR-06/07）、入队全路径带 `tenant_id`（FR-09）、`llm_chat` 前接 `check_llm_tokens_month`（FR-10）、候选不进租户结果账（FR-11）、配额文案/时区（FR-12/16）、管理详情去掉 `file_path`（FR-13）。Wave 1 市场 API **代码为零**（`listing_state` / `capability_sources` / `resolve_origin_path` / `POWER_MARKET` 全仓 0 命中），必须等 dba PR1 + architect 契约。现网最危险的不是「缺商店」，是 **租户 `role=admin` 被当成平台超管**（scan-plugins 连 `viewer` 都能跑 MCP），以及 **调度/模板/AI 试采入队不传租户**——HTTP 租户态会撞 `before_flush` 断言，后台调度会撞 `spider_tasks.tenant_id` NOT NULL。

---

## 1. 现状地图：代码 ↔ 四支柱 ↔ 冻结 FR

路由聚合仍是 `backend/app/api/v1/__init__.py`：auth / spiders / admin / rbac / configs / ai / llm / newapi / skills / public / members / tenants/me / tenant_signup / capabilities。**没有** `tenants/me/installs`、**没有** `/capabilities/sources*`。v2 仅 health。外部面 `/external/v1` = 平台共享 API Key。

| 支柱 | 已落地（入口） | 缺口 | 冻结 FR |
|------|----------------|------|---------|
| 智能采集 | `/api/v1/spiders/*`；`/ai/plans*`；`GET/POST /skills/candidates*`；consumer 回流；`GET /spiders/nodes` 心跳 | 调度/模板/AI 入队丢租户；入队不看 Worker 是否在线；导出任务级无 100 条帽（数据中心列表有） | W0：FR-03/08/09；W4 stub：FR-70–72 |
| SaaS | `tenant_isolation.py` + middleware；`/admin/tenants*`（`require_platform_admin`）；`/members`；`/tenants/me/usage*`；`QuotaService` 三检查点；注册 `/public/tenant/signup` | LLM 套餐闸未接线；用量 UTC 月；到期登录未拒；按钮码不执法；埋点 0 | W0：FR-04/08–12/15/16；W2 stub：FR-50 |
| 中转站 | `/api/v1/newapi/{overview,events,probe-results,channels*}`；ChannelScheduler / Probe；Redis `newapi:channel:cfg:{id}` | 守卫 `require_admin`；渠道 Redis 无租户前缀；LiteLLM 仅 pycache | W0：FR-07；W3 stub：FR-60/61 |
| Power Market | P6：`/capabilities` 四类 + `/public/capabilities` + plugin scan/verify + MCP stdio | **无** Source / listing / installs / aliases / 适配器 / `power_market.yml` | W1：FR-17–31（D1–D21） |

机械红线（本树，backend 视角）：`backend/app/api/` **零** `from platform_core.models`（R7 过）。服务层不 import `backend.app.api`。B2（backend ⇏ scrapy）成立。`redis_client().method` 生产代码已清（R11）；仅 `test_saas_members.py` 同步测境直调。

---

## 2. Wave 0 FR 对照（本帽主交付；可与 PR1 并行的后端工作）

| FR | 后端现状 | 判定 | 改哪里（实现阶段，本帽不动手） |
|----|----------|------|--------------------------------|
| FR-04 注册后能登录 | `TenantSignupService.signup` 建 tenant+owner（`role=admin`,`tenant_role=owner`）；`test_signup_creates_tenant_and_owner` 随即 `POST /auth/login` 200。响应只有 `{tenant, owner}`，无 `login_url` | **能力已通**；出口 URL 是官网前端。不阻塞 | 无需后端改合同；前端成功页主按钮 |
| FR-06 平台目录写仅超管 | `POST /capabilities/scan-plugins` / `verify` / `scan-experts` / `teams` = **`require_login`**（`capabilities.py`）。`POST /skills/scan` 等 = **`require_admin`**（租户公司管理员 `users.role=admin` 放行）。`require_platform_admin` 已存在且用于 `/admin/tenants*`，市场写路径 **没用** | **泄漏** | 写路径改 `require_platform_admin`；**同 PR 改** `test_b1c_capabilities_coverage.py`（今日契约：viewer 可 scan） |
| FR-07 渠道窗口 + 平台 LLM 写仅超管 | `newapi.py` 文件头写明全部 `require_admin`。`llm_providers.py` 写操作（含 **activate**）`require_admin`。审计已有 `newapi.channel_config.set/clear`、`llm.provider.activate` | **泄漏**（与 FR-06 同构） | 写路径 `require_platform_admin`。BYOK 租户自有供应商是否仍 `require_admin` **回 architect**（平台行 vs 租户行） |
| FR-08 只看见本租户任务/结果/成员 | SpiderTask/Result/Schedule/Definition + AiPlan 走 `TenantMixin`；请求中间件 `tenant_scope` 读注入有效。成员 API `require_tenant_manager` + 显式 `tenant_id`。外部 `/external/v1/data/{spider}` **无租户**（平台 Key） | 请求路径 **大体成立**；外部 Key 与丢租户入队会破 | 入队修 FR-09；外部 Key 绑定是 FR-52（本波不做） |
| FR-09 定时/模板/AI 试采属本租户并计配额 | 唯一正确入口：`POST /spiders/run` 传 `user.tenant_id`。`SpiderService.enqueue` **签名无 `tenant_id`**。调度 `_fire` 有 `schedule.tenant_id` 不传入。`create_task_from_template` 不传。AI 试采 `orchestrator` 调门面 enqueue。`QuotaService.check_task_concurrency` 仅 `tenant_id is not None` | **必修，Wave 0** | 见 §8.1。门面至少转发 `tenant_id`；调度用 `schedule.tenant_id`；模板/AI 用 `user.tenant_id` 或 plan 行 |
| FR-10 月度 LLM 套餐挡住真调用 | `check_llm_tokens_month` **仅** `test_saas_quota.py` / `test_saas_byok.py`。`llm_chat` 熔断读 **全局** `LLM.MAX_TOKENS_BUDGET` + Redis 月用量（`{dim}\|total` 写入 **不含 tenant**）。规划/试采修复/技能评分都走 `llm_chat` | **失败**（ADR-0014 已点名备选 D） | `llm_chat` 调用前 `QuotaService.check_llm_tokens_month`；月键用 **Asia/Shanghai**；用户文案走 FR-12，不要把 provider 预算耗尽映射成 `QUOTA_EXCEEDED`（ADR-0014） |
| FR-11 市场候选不计租户结果配额、不进「我的结果」 | 候选 = `spider_results.source=marketplace`。`check_result_storage` **按租户 COUNT 全表**，不排除 marketplace。`search_results` 无 `source` 过滤。`list_candidates` 内存滤 pending。016 种子定义在 017 被回填到 `default` 租户；租户经办 `POST /spiders/run` 跑 harvester → 候选进该租户账 | **失败** | 计数/列表排除 `source=marketplace`（或独立表——回 architect V4）。配额 SQL 与数据中心查询必须同一谓词 |
| FR-12 将满/超限文案，不露内部码 | `QuotaExceededException(code="QUOTA_EXCEEDED", status_code=429)`；handler 把 `code` 放进信封。文案是「联系平台管理员提升套餐」，**不是** FR-12「去结果库 / 申请提升配额」。用量 API **不算 70–89% 警告**。`GET /tenants/me/usage` = `require_tenant_manager`：超管无 `tenant_role` → 403，不是「用量属于企业空间」 | **部分**（有拒绝、文案/码/空态不对） | 文案对齐 FR-12；`code` 是否对前端隐藏回 architect（前端 `Usage.tsx` 已写出 `429 QUOTA_EXCEEDED`）。用量 payload 加 `percent`/`warn` 或声明纯前端算 |
| FR-13 不暴露本机路径 | 公开技能：`PublicSkillResponse` 无 `file_path`（`test_public_fields_whitelist_enforced`）。公开能力：`_PUBLIC_ASSET_FIELDS` 无路径。**管理** `GET /capabilities/{type}/{name}` **返回 `file_path`**（`capabilities.py`）。`SkillDetailResponse.file_path` 管理详情默认带出 | **管理面泄漏** | 管理白名单删 `file_path`；读正文改 `resolve_origin_path`（Wave 1 / D15）。Wave 0 先删响应字段即可 |
| FR-14 密钥 | LLM 列表 `api_key_masked`；启动期拒 Webhook/LLM 占位符（`create_app._validate_runtime_secrets`）。仓库跟踪的生成配置不在 backend 树 | 后端 API **已掩码**；git 跟踪文件归 sre | 渠道页若回显 new-api token 需再核 `ChannelConfigInfo`（本帽未见明文 Key 出协议） |
| FR-15 埋点 | `official_page_viewed` / `quota_exceeded` / `task_run_submitted` 等 **全仓 0 命中** | **缺口** | 事件表或日志管道回 architect；失败不得挡主路径。本帽不选存储 |
| FR-16 时区 | `tenant_usage.py`：`datetime.utcnow().strftime("%Y-%m")`。`quota_service` 月前缀 `like year_month-%`。LLM Redis `_today()` = `date.fromtimestamp(time.time())`（机器本地/UTC，不是上海业务日） | **失败** | 统一 Asia/Shanghai 业务日；页面时区标注是前端 |
| FR-03 导出 | `GET /results/{task_id}/export` 仅 `csv\|json`，**流式全量**无 100 条帽。数据中心列表 `page_size le=100`。无 xlsx（pattern 已拒） | 格式 **已对齐**（无 xlsx）；条数帽是列表不是导出 | 产品「单次最多 100 条」若指导出，须在 Service 截断并回合同；若只指列表，pm 改口 |
| （无 FR）到期登录 | `expire_overdue_tenants` 置 `expired`。`AuthService.authenticate` **不读** `tenants.status`。`test_expired_tenant_login_rejected` **没有** `POST /login`，只断言 status 列 | **登录仍可过** | 是否纳入 Wave 0 回 pm（spec 未冻这条；与 miner/草稿互殴，以代码为准） |

---

## 3. 分层违约（Router → Service → Repository → ORM）

爬虫子域仍是合格样板：`spiders/*.py` → `Spider*Service` → `backend/repositories/spider_*_repository.py`。

### 3.1 Service 跳过 Repository

| 服务 | 文件 | 数据访问 |
|------|------|----------|
| `CapabilityService` | `capability_service.py` | `select(CapabilityAsset)`，无 repo；`list_assets` **无入口 `logger.info`**（R10） |
| `PluginService` | `plugin_service.py` | `select(CapabilityAsset/CapabilityPlugin/SkillJob)`；`scan_plugins` 无入口 info 日志 |
| `ExpertService` / `TeamService` | `expert_service.py` | 同上 |
| `QuotaService` | `quota_service.py` | `select(Tenant/SpiderTask/SpiderResult/LlmTokenUsage)` |
| `SkillService` | `skill_service.py` | 列表走 `SkillRepository`；**scan / correct_meta / candidates 直写 ORM** |
| `RbacService` | `rbac_service.py` | 直写 Role/Permission/Menu/Department |

Wave 1 若沿用 PluginService 风格，源同步事务与 listing 短事务会继续散落。建议市场域 **新建** `capability_source_repository` / `capability_asset_repository`（回 architect 分层合同，本帽不发明表）。

### 3.2 Service 返回 ORM，Router 手写投影

`list_assets` / `get_asset` 返回 `CapabilityAsset`。Router 拼 dict，管理详情送出 `file_path`。公开面另一套 `_PUBLIC_ASSET_FIELDS`。技能列表 `SkillResponse.model_validate(r)` 仍是 ORM 出 Service。`listing_state` 一旦加上，三处投影会裂。

### 3.3 Router 掺业务

| 位置 | 问题 |
|------|------|
| `public_skills.public_list_skills` | `list_skills(status=None)` 后再内存滤 `PUBLISHED_STATUSES`；`total=len(published)` = **当前页过滤后条数**，不是库内发布态总数 |
| `public_skills.public_list_capabilities` | 写死 `status="stable"`，**丢掉 recommended**（FR-18 / D9） |
| `capabilities` 写路径 | 鉴权即业务范围：任意登录可写平台目录 |
| `skills._read_skill_files` | Router 读盘；D15 要求 Service `resolve_origin_path` |
| `SkillService.list_candidates` | 全表拉 marketplace 再内存切片；tenant_scope 下租户只能看见本租户候选（平台供给被切碎） |

### 3.4 过渡门面未清（R12 白名单）

`backend/services/spider_service.py` 仍被 `schedule_service.py`、`ai_planner/orchestrator.py`、`admin.py`、`external_api/v1/webhooks.py`、`tasks/consumer.py` 引用。`enqueue` **不转发 `tenant_id`**——不是风格债，是 FR-09 根因。

### 3.5 R10 logger 名

大量服务 `get_logger("api")`（`schedule_service` / `llm_client` / `channel_config_service` / `llm_usage_service` / `spider_task_service` 等），与 `service.<domain>` 约定不一致。配额/市场新代码不要再叫 `"api"`。

### 3.6 失踪源文件

`backend/app/api/v1/__pycache__` 残留 `api_keys` / `billing` / `litellm_admin`；`backend/services/litellm/` **只有 pycache**。ADR-0014：**LiteLLM 替换不进本特征**。实现时当退役残骸清，不当合同。

---

## 4. Power Market：相对设计 / Wave 1 FR 的端点缺口

`listing_state` / `resolve_origin_path` / `POWER_MARKET` / `capability_sources` / `capability_installs`：**全仓 grep 零命中**。`config/default/power_market.yml` 不存在。`backend/config_consts.py` 无对应常量。

### 4.1 管理 API（FR-22/23/25/26）

| 设计路径 | 设计守卫 | 现状 |
|----------|----------|------|
| `GET/POST/PATCH /sources*`、`POST .../sync` | platform_admin + `btn:market:*` | **缺失**；`type=url` 422 无实现 |
| `PATCH /{type}/{name}/listing` | 同上 | **缺失** |
| `PATCH .../license-override` | 仅 platform_admin | **缺失** |
| `PUT .../aliases` | platform_admin + list | **缺失** |
| `GET /plugins/{name}/components` | login | **缺失**（bundled 只在 JSON） |
| `POST /scan-plugins` | 应收紧 | **存在，`require_login`** |
| `POST /plugins/{name}/verify` | 应收紧 | **存在，`require_login`** |
| `POST .../enable-host` | PR8 / D21 snippet | **缺失** |
| `GET /capabilities` listing/source/origin/q | login | 列表在；**无** listing/source；`q` 只 `name LIKE`（FR-19 短名搜要 `origin_local_name`/`title`） |
| `GET /{type}/{name}` 去 `file_path` | login | **仍返回 `file_path`** |

后端 **没有** `require_permission("btn:…")`。`PERMISSION_CATALOG`（`rbac.py`）只有 `btn:skill:edit` / `btn:skill:admin`，无 `btn:market:*` / `btn:plugin:verify`。D14 按钮码半段不存在。FR-06 用户可见行为只需超管拒绝；按钮码是否做 FastAPI Depends **仍回 architect**。

`test_b1c_capabilities_coverage.py` 把「viewer 亦可 scan/verify」写成契约——收紧守卫必红，须与实现同 PR（qa 已点名）。

### 4.2 租户安装（FR-20/21/29）

`/api/v1/tenants/me` 今日只有 `usage` / `usage/by-member`（`require_tenant_manager`）。设计 `GET/POST/PATCH/DELETE /tenants/me/installs` 全部缺失。表 `capability_installs` **禁止**进豁免清单。FR-20.3：超管无企业空间 403——实现时不要给超管开后门「模拟租户」除非 pm 另开 FR。

### 4.3 公开 API（FR-17/18/19/28/31）

| 设计 / FR-18 | 现状 `public_skills.py` |
|--------------|-------------------------|
| SQL：listing ∈ {listed, coming_soon} ∩ status ∈ {stable, recommended} ∩ 许可闸 | 仅 `status="stable"`；无 listing、无 license |
| 白名单含 `listing_state`、`installable` | `_PUBLIC_ASSET_FIELDS` 无 |
| `GET /public/capabilities/{type}/{name_or_slug}` | **整条缺失** |
| `GET /public/skills` deprecated → type=skill | 仍独立查 `skills` 表；分页 total 错误 |
| IP 限流 | 有；`await get_async_redis()` + fail-open；**INCR 与 EXPIRE 非原子**（进程崩溃可留无 TTL 键，dba 已记） |

### 4.4 D5 / FR-27 — 第三方只写 DB

`SkillService.scan_library`（`skill_service.py`）：`dir_names` 只有 `LIBRARY_ROOT/skills/*`；库内不在目录的 name 一律 `sync_state=missing`。D4 提升后的 `mattpocock-skills__code-review` **必然被标 missing**。

写盘无 `writable` 守卫：`_write_back_meta` / `_append_changelog` / `correct_meta` / `export_meta`（API 守卫 **`require_operator`**，比 scan 更宽）。第三方无 `meta.yaml` 时写回失败仅记 job，仍尝试写源树。

### 4.5 D16 扫描回退（实现硬约束）

`PluginService.scan_plugins(root=None)` 钉死 `SKILLS.LIBRARY_ROOT/plugins`。**碰巧等于 D16 回退**。差距：HTTP 不接受 `root=`；无 `POWER_MARKET.ENABLED`；`iterdir` 含 symlink、不跳过 `.` 开头、无 `relative_to(source_root)` 逃逸检查；无 Kimi `kimi.plugin.json`；bundled 一层目录名不入 `skills` 表、不折叠 hash。无 MCP → `health_status=degraded`（设计/FR-26：`unknown`，允许 listed）。`test_b1c` / `test_mcp_bridge` 依赖今日语义——切源不得破坏这批夹具。

MCP 桥：模块头写 stdio/HTTP，实现 **仅 stdio**。白名单 node/npx/python3/python/uvx/uv。ADR-0014：Wave 0/1 **禁止**把 `call_tool` 扩成平台 Agent 运行时。

无 `backend/services/power_market/` 包。

### 4.6 ORM / 豁免（给 dba，backend 视角）

`TENANT_EXEMPT_TABLES` 含 `skills` 三表，**不含** `capability_assets`（**有 tenant_id 列**、不 inherit TenantMixin）。`do_orm_execute` 对 UPDATE/DELETE：有列未豁免 → `WHERE tenant_id = <当前>`。租户态 `upsert_skill_asset` 的 Core UPDATE **0 行命中**（SELECT 因无 Mixin 不过滤，读路径「看起来正常」）。设计迁移步骤 4 要求补豁免；`capability_installs` 不得豁免。

`before_flush` **只断言不回填**：新行 `tenant_id` 必须调用方写入。这是 FR-09 与「调度丢租户」叠加后的具体爆炸点。

---

## 5. 租户 / 超管守卫

### 5.1 已做对的

- JWT 快照 `CurrentUser`（ADR-0007；`test_rbac_audit.py::test_current_user_ok`）。
- `TenantContextMiddleware`：`is_platform_admin` 经 DB 复核才 `platform_scope`；撤销立即降级。
- `/admin/tenants*` = `require_platform_admin`。
- 成员 API 用 `tenant_role in (owner, admin)`，超管不进该域。
- 公开技能详情未发布 404（存在性同构）。
- 024：`users.tenant_id` NOT NULL（`test_users_null_tenant_contract.py::test_null_tenant_user_rejected`）。

### 5.2 角色双轨（FR-06/07 根因）

| 守卫 | 含义 | 误用后果 |
|------|------|----------|
| `require_admin` | `users.role==admin` | 租户公司管理员 = 平台写 |
| `require_platform_admin` | `is_platform_admin` | 设计/FR 要的市场与渠道写路径 |
| `require_tenant_manager` | `tenant_role in (owner, admin)` | 成员/用量 |
| `require_login` | 任意角色 | 今日 scan-plugins/verify（连 viewer） |

今日被租户 admin（及 viewer，目录扫描）打穿的平台写面：

- `POST /capabilities/scan-plugins|scan-experts`、`POST /teams`、`POST /plugins/{name}/verify`
- `POST /skills/scan`、`import-url`、`sync-adapters`、candidates approve/reject（`require_admin`）
- `PUT /newapi/channels/{id}/config` 及 DELETE
- `PUT /llm/providers/{id}/activate` 及供应商 CRUD
- `PUT /configs/{key}`
- 爬虫定义/调度/删任务（定义表有 `tenant_id`，相对可接受；渠道 Redis **无租户前缀** 不可接受）

### 5.3 后台任务无 tenant_scope

`SpiderTaskConsumer`、`SpiderScheduler` 不进 `platform_scope`。无上下文 = 不过滤不断言。跨租户回流必要，但 **入队必须显式写 `tenant_id`**。Mixin 不回填；017 已 NOT NULL。

`background_session` 可按锚派生 scope（`test_background_session.py`）——调度入队应走这条，而不是裸 `SpiderService.enqueue`。

### 5.4 到期租户

`tenant_expiry_service` 置 `expired`。登录路径不查该列。测试名 `test_expired_tenant_login_rejected` 空心（无 login 断言）。**代码事实：过期仍可登录。**

---

## 6. Redis：同步 / 异步 / 键

R11：生产 `redis_client().method` 已清。`get_async_redis()` 是 **同步工厂**，返回 `redis.asyncio.Redis`。

两种都合法：

- `await get_async_redis().incr(key)` — spider_task / channel_config / health
- `redis = await get_async_redis()` — public_skills / tenant_signup（工厂本身不可 await，靠 `Redis.__await__` = `initialize()`）
- `redis = get_async_redis()` 再 `await redis.*` — auth / quota `_cached_count` / llm_usage

**风格不统一**。市场/配额新代码固定：`redis = get_async_redis()`（不 await 工厂）。

键：队列在 `platform_core/queues.py`。中转 `newapi:channel:cfg:` / `newapi:scheduler:state:`（无租户）。公开限流 `SKILL_PUBLIC_RATE_PREFIX`。配额 `quota:count:` TTL 60s。LLM 日明细四段 `tenant|dim|model|metric`；**月度预算写入仍是 `{dim}|total`**（`llm_usage_service.py` `hincrby(monthly, f"{dim}|total")`），读才尝试 tenant 字段再 fallback——FR-10 即使用上 Redis 熔断也不是租户套餐。

`channel_scheduler_service` 独立 engine 读 `NEWAPI.DB_DSN`（R1 合规）。

---

## 7. new-api 中转站（FR-07 / FR-61）

分层尚可：Router → Overview/ChannelConfig → repository + Redis。远程失败 overview **HTTP 200 + available=false**。配置写 Redis，下轮生效。审计有。

| 项 | 说明 |
|----|------|
| 守卫 | 全部 `require_admin`；租户 admin 可改 **平台级** 渠道额度 |
| 配额 | 渠道窗口 ≠ `tenants.quota`；API 层未关联（定价不得混写，FR-01） |
| 探针伪装 | 今日不自动下线（FR-61 冻结保持） |
| LiteLLM | ADR-0014：不进本特征 |

---

## 8. SaaS 配额与入队（FR-09/10/11）

### 8.1 入队丢租户的精确爆炸点

`SpiderTaskService.enqueue(..., tenant_id=None)`：

1. `if tenant_id is not None` 才打并发配额 → **跳过**。
2. `repo.create(..., tenant_id=None)`。
3. `before_flush`：若在 **tenant_scope**（HTTP 模板/AI 试采，`asyncio.create_task` 会 copy ContextVar）→ **`ValueError` 租户写入断言**（不回填）。
4. 若在 **无上下文**（调度器）→ 断言跳过 → MySQL **IntegrityError**（017 NOT NULL）。
5. Redis 消息 `tenant_id` 取自参数，不是 flush 后的行 → 即便有人改 mixin 回填，回流仍丢租户。

调用方：

| 路径 | 传 tenant_id？ |
|------|----------------|
| `POST /spiders/run` | 是，`user.tenant_id` |
| `POST /templates/{id}/run` | 否（Router 有 `user` 不往下传） |
| 调度 `_fire` | 否（`schedule.tenant_id` 闲置） |
| AI 试采 | 否（门面无该参数） |
| `test_saas_wiring.py::test_enqueue_carries_tenant_and_quota_rejects` | 只测 **Service 显式传入** 的快乐路径，不测门面/调度 |

### 8.2 LLM 两本账（ADR-0014）

| 账 | 谁读 | 谁写 | 用户该看见？ |
|----|------|------|--------------|
| 套餐 `tenants.quota.llm_tokens_month` | `QuotaService.check_llm_tokens_month`（**未接线**） | 用量 flush → `llm_token_usage` | FR-10/12 **是** |
| Provider Redis `LLM.MAX_TOKENS_BUDGET` | `llm_chat` 熔断 | `record_usage` 月字段无 tenant | 内部成本；套餐未尽时 **不得** 报 `QUOTA_EXCEEDED` |

`skill_scoring_service` / `skill_service` / 规划 / 修复全部 `llm_chat`。接线点只有一处：`llm_chat` 入口。

### 8.3 用量看板

`GET /tenants/me/usage` 只读，不执法。默认免费档与 017 种子一致：`task_concurrency=5, result_storage=10000, llm_tokens_month=200000`。无套餐名字段（FR-50 要「看得出免费档」——可从缺省数字推断，但 payload 无 `plan`）。

---

## 9. 智能采集 · Spider APIs

| 子域 | 读守卫 | 写守卫 |
|------|--------|--------|
| 任务 | login | operator 入队/控制；admin 删除 |
| 结果 | login | admin 删除；export 流 csv/json |
| 定义/节点/文件/代理 | login / operator(proxy) | admin CRUD 定义 |
| 调度/告警 | login | admin |
| 模板 | login | operator |

相邻：

- `POST /ai/plans` + 规划/试采（operator）；试采走门面 **无 tenant**。`create_plan` 不显式写 `tenant_id`——HTTP 下靠调用方在 create 前填？`repo.create` 未见 tenant 参数 → **同一断言**。需在实现时给 AiPlan 写入 `user.tenant_id`。
- 技能候选：`skill_harvester` → `source=marketplace` → `/skills/candidates*`。approve 走 import-url。无 listing 列时转正只能停在 skills 三表。
- 外部 Key 无租户（FR-52 下一轮）。
- 定义唯一 `(tenant_id, name)`；scrapy 进程内全局文件。同名登记 ≠ 独立代码。产品边界，回 architect。
- `GET /spiders/nodes` 心跳列表存在。**入队不检查在线 Worker**（FR-71 是 Wave 4 stub，Wave 0 不要顺手做）。
- 注册上线：`POST /ai/plans/{id}/register` 已要求最近试采通过 + admin（FR-72 部分已有）。

`POST /spiders/run` 是唯一正确传 `tenant_id` 的入队入口。

---

## 10. 合同问题（本帽拒绝静默改）

回 **architect**：

1. FR-18 公开闸（stable\|recommended + listing + 许可）vs 今日只 `stable`——breaking，须同改 `test_b1c` / `test_skill_public_api`。
2. 无 MCP `degraded` → `unknown`（FR-26）breaking。
3. `require_permission(btn:market:*)` 是否 FastAPI Depends？FR-06/07 用户可见只需超管；D14 按钮码未落 deps。
4. 租户 BYOK 供应商写：收成 `require_platform_admin` 会误伤租户自有 Key。合同要拆「平台行」vs「本租户行」。
5. Service 返回 ORM vs DTO：市场新字段继续手写 dict 会裂。
6. FR-12：信封是否继续带 `code=QUOTA_EXCEEDED`（前端已依赖）vs 用户文案不得出现该字样。
7. FR-11：marketplace 继续住 `spider_results` 加谓词，还是独立表（architect V4）。
8. FR-03：100 条帽是导出还是仅列表。
9. `GET /public/skills` 分页 total：随 deprecated 转调修还是 Wave 0 先修。

回 **dba**：

1. `capability_assets` 等豁免；`capability_installs` 不豁免。
2. PR1 列/表 autogenerate，禁手写 SQL。
3. `skill_jobs.source_id`；`skills.source_type` 放宽（`marketplace_crawled` 超 VARCHAR(16)）。
4. LLM 月度 Redis field 补 tenant（expand 双写）。
5. 公开限流 INCR+EXPIRE 原子化。

回 **pm**（验收不可达则停）：

1. `test_b1c` viewer 可 scan 与 FR-06.3 403 互斥——必须改验收/用例，不能留双金标。
2. 到期登录拒绝：无冻结 FR；测试名撒谎。做不做进 Wave 0。
3. FR-15 埋点存储选型未写（本帽不选）。
4. 调度入队无 tenant：**已冻进 FR-09**，不是「另开票」。

---

## 11. 建议实现顺序（诊断建议，非开工）

**Wave 0（无新表也可做）：**

1. 入队全路径 `tenant_id`（门面转发 + 调度 `schedule.tenant_id` + 模板/AI `user.tenant_id`）；AiPlan create 同样写入。配额检查自然跟上。
2. `llm_chat` 前 `check_llm_tokens_month`（上海月）；保留 provider Redis 熔断但映射 ADR-0014 文案。
3. 结果 COUNT / 数据中心列表排除 `source=marketplace`（或按合同改表）。
4. 平台写面：scan-plugins/verify/scan-experts/teams/newapi 写/平台 LLM activate → `require_platform_admin`；**同 PR 改 test_b1c**。BYOK 行除外待合同。
5. 管理详情去掉 `file_path`；配额文案对齐 FR-12；用量月用上海时区。
6. 豁免表登记 `capability_assets`（dba 清单，一行代码，不进市场 Router）。

**Wave 1（schema PR1 之后）：** D16 回退保持 → 源适配器 + `resolve_origin_path` → listing/许可/公开 SQL → installs。禁止在 schema 前写市场 Router。

**明确不做（本特征 / ADR-0014）：** LiteLLM 恢复、MCP 工具面、代写 `~/.zcode`、xlsx、模板商店、外部 Key 绑租户。

---

## 12. 自检（本帽）

- [x] 未改业务代码、未写迁移、未改前端、未改验收文案、未实现 API
- [x] 分层 / 守卫 / Redis / MCP / 配额 / 中转 / 爬虫均引用了具体文件
- [x] D5 / D14 / D15 / D16 与 FR-06…16 / FR-17…31 有现状对照
- [x] 合同歧义已标回 architect / dba / pm
- [x] 上一稿结论仍成立；新增：到期登录空心测试、before_flush 不回填、LLM 月 Redis 无 tenant、FR-11 候选占配额、用量 UTC
- [ ] 实现证据：不适用（诊断帽）

---

## open_questions

1. `require_permission(btn:market:*)` 是否做 FastAPI 依赖，还是 Wave 0 只改 `require_platform_admin`、按钮码仍前端隐藏？（影响 D14 与 rbac 种子。）
2. 租户 BYOK 的 `POST/PUT /llm/providers` 在 FR-07 收权后如何保留？（平台行超管写 / 本租户行 tenant admin 写？）
3. `capability_assets` 租户 UPDATE 0 行是否已在手工运营出现？`upsert_skill_asset` 在 scan 里、scan 今日是 admin——租户 admin 扫技能就会踩。豁免紧急度 = Wave 0。
4. 调度器入队无 `tenant_id`：本地 MySQL 是否已有 IntegrityError 日志，还是调度未在租户化环境打开？（FR-09 不论日志都要修。）
5. 到期 `tenants.status=expired` 登录是否 Wave 0 必修？代码与测试名不一致。
6. FR-12 信封 `code` 字段对前端是否契约？改文案是否允许同时改 code。
7. FR-03 的 100 条是导出截断还是仅列表分页。
8. FR-15 事件写哪（新表 / 现 `operation_logs` / 日志）——回 architect，backend 不选仓。
9. git 适配器 `CACHE_DIR` 多实例抢 clone：文件锁还是「只读已 clone 树」？设计未写并发。
10. 平台超管无 `tenant_id` 时 installs 403（FR-20.3 已冻）：运营如何自测商店——只用真实租户账号，还是要「模拟租户」FR。
11. `GET /public/skills` 错误 total：Wave 0 修还是随 FR-17 弃用转调。
12. 公开限流 INCR/EXPIRE 非原子：是否塞进 Wave 0 卫生，还是跟市场公开面一起修。
