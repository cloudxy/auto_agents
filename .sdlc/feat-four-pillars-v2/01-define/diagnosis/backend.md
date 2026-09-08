# 定义帽 · Backend 诊断（feat-four-pillars-v2）

| 字段 | 值 |
|------|----|
| 角色 | backend（只读诊断，不实现 API、不改业务代码、不写迁移、不改验收） |
| 日期 | 2026-09-08 |
| 泳道 | L4 |
| 特征 | `feat-four-pillars-v2`（supersedes `feat-four-pillars`；旧塑形/票 **不是** 现行合同） |
| 输入 | `01-define/diagnosis/INPUTS.md` 书单；旧 `feat-four-pillars/01-define/diagnosis/backend.md`；`CONTEXT.md`；`project_rule.md`；`backend/app/api/` + `backend/services/`；旧 `02-shape/contract.md` v2.1 与 ADR-0013/14/15/17 **仅作约束备忘** |
| 宪法 | `.claude/rules/project_rule.md` + `sdlc.config.yaml`；契约回 architect / 表结构回 dba / 验收口径回 pm |
| 路径更正 | 调用方写 `backend/app/deps.py`——现网是 `backend/app/api/deps.py` |

---

## 0. 结论（给 PM / architect 的三句）

1. **P0 泄漏/越权仍在，无一处被修。** 租户 `users.role=admin` 仍等于平台写面；`POST /capabilities/scan-plugins|verify|scan-experts|teams` 仍是 `require_login`（viewer 可扫并可拉起 stdio MCP）；`/newapi/*` 写与平台 LLM activate 仍是 `require_admin`。调度/模板/AI 试采入队仍不传 `tenant_id`。`check_llm_tokens_month` 仍只出现在测试。候选仍计入结果配额。管理详情仍回 `file_path`。
2. **Power Market 代码仍是 0。** 全仓 `POWER_MARKET` / `listing_state`（除 `CONTEXT.md` 词条）/ `capability_sources` / `capability_installs` / `resolve_origin_path` / `backend/services/power_market/` / `config/default/power_market.yml`：**0 命中**。能力面停在 P6 四类目录。
3. **全新方案必须吸收的不是旧票号，是现网硬约束：** `require_admin ≠ 超管`、`before_flush` 只断言不回填、`spider_results.tenant_id` NOT NULL、D14/D16/D5、套餐闸与 provider Redis 两本账、市场表未落地前禁止写市场 Router、收守卫必须同 PR 改 `test_b1c`。旧 `feat-four-pillars` 塑形可当约束清单，**不得复制为 v2 现行合同**。

Wave 0 后端仍能与 schema PR1 **并行**（收权、入队、LLM 闸、候选谓词、去 `file_path`、上海月）。Wave 1 市场 API **必须等 dba 表**。现网最危险的仍不是「缺商店」，是 **公司管理员被当成平台超管** + **入队丢租户撞断言/NOT NULL**。

---

## 0.1 相对 2026-09-07 旧 backend 诊断的 delta

旧稿结论 **全部仍成立**（本帽按文件复核，不是抄旧文）。仅下列变化：

| 项 | 旧稿 | 2026-09-08 现网 |
|----|------|-----------------|
| 登录投影 `is_platform_admin` | architect/frontend 说前端快照无此字段 | **后端已出**：`auth.py` 登录信封带 `is_platform_admin`（`schemas/auth.py` `UserResponse` 亦有）。前端是否消费属 frontend 帽 |
| R12 白名单 | 6 个门面消费者 | `external_api/v1/public.py` **已不再** import 门面，但 `check-arch.sh` 白名单仍列它（白名单滞后，不是泄漏修复） |
| 公开资产类型 | 四类 | `CONTEXT.md` 已是五类平级（skill/plugin/command/agent/team）；公开 API 仍 `skill/plugin/expert/expert_team` |
| 登录到期 | 空心测试 | **未变**：`test_expired_tenant_login_rejected` 仍不打 `POST /login` |
| Alembic 头 | 027 | **仍是** `027_spider_tasks_status_varchar.py` |
| 额外写面（旧稿点到未单列） | RBAC/配置被 `require_admin` 扫过 | 本帽升为约束：`PUT /configs/{key}`、`/rbac/*` 写、`_ROLE_PERMISSIONS[admin]` 含 `menu:newapi`/`menu:llm`/`menu:platform-ops`——与 FR-06/07 **同类**，旧冻结 FR 未点名 |

---

## 1. 现状地图：代码 ↔ 四支柱

路由聚合仍是 `backend/app/api/v1/__init__.py`：auth / spiders / admin / rbac / configs / ai / llm / newapi / skills / public / members / tenants/me / tenant_signup / capabilities。**没有** `tenants/me/installs`、**没有** `/capabilities/sources*`。v2 仅 health。外部面 `/external/v1` = 平台共享 API Key。

| 支柱 | 已落地（入口） | 缺口 |
|------|----------------|------|
| 智能采集 | `/api/v1/spiders/*`；`/ai/plans*`；`GET/POST /skills/candidates*`；consumer 回流；`GET /spiders/nodes` 心跳 | 调度/模板/AI 入队丢租户；入队不看 Worker；导出任务级无 100 条帽（数据中心列表有 `le=100`） |
| SaaS | `tenant_isolation.py` + middleware；`/admin/tenants*`（`require_platform_admin`）；`/members`；`/tenants/me/usage*`；`QuotaService` 三检查点；注册 `/public/tenant/signup` | LLM 套餐闸未接线；用量 UTC 月；到期登录未拒；按钮码不执法；埋点 0；`_ROLE_PERMISSIONS` 把中转菜单给租户 admin |
| 中转站 | `/api/v1/newapi/{overview,events,probe-results,channels*}`；ChannelScheduler / Probe；Redis `newapi:channel:cfg:{id}` | 守卫 `require_admin`；渠道 Redis 无租户前缀；LiteLLM 仅 `services/litellm/__pycache__` |
| Power Market | P6：`/capabilities` 四类 + `/public/capabilities` + plugin scan/verify + MCP stdio | **无** Source / listing / installs / aliases / 适配器 / `power_market.yml` |

机械红线（本树，backend 视角，本帽未改代码故未跑闸门，按 grep）：

- `backend/app/api/` **零** `from platform_core.models`（R7 过）。
- 服务层不 import `backend.app.api`。B2（backend ⇏ scrapy）成立。
- `redis_client().method` 生产代码 **0 命中**（R11 过）。
- R12 门面仍被 `schedule_service` / `ai_planner/__init__` / `admin.py` / `external_api/v1/webhooks.py` / `tasks/consumer.py` 引用；`enqueue` **仍不转发 `tenant_id`**。

---

## 2. P0 泄漏 / 越权（仍在）

### 2.1 角色双轨（根因，未变）

`backend/app/api/deps.py`：

| 守卫 | 含义 | 误用后果 |
|------|------|----------|
| `require_admin` = `require_role("admin")`（L116） | `users.role==admin` | 租户公司管理员 = 平台写 |
| `require_platform_admin`（L119–125） | `is_platform_admin` | 设计/旧 FR 要的市场与渠道写路径；**今日几乎只用于** `/admin/tenants*` |
| `require_tenant_manager` | `tenant_role in (owner, admin)` | 成员/用量 |
| `require_login` | 任意角色 | 今日 scan-plugins/verify（连 viewer） |
| `require_permission` | **不存在**（全仓 0） | `btn:market:*` 无法 Depends |

`PERMISSION_CATALOG`（`rbac.py`）只有 `btn:skill:edit` / `btn:skill:admin`，无 `btn:market:*` / `btn:plugin:verify`。

### 2.2 今日被打穿的平台写面（逐条仍在）

| 路径 | 守卫 | 证据 |
|------|------|------|
| `POST /capabilities/scan-plugins` | `require_login` | `capabilities.py:58-60` |
| `POST /capabilities/plugins/{name}/verify` | `require_login` | `capabilities.py:82-85`（stdio MCP `call_tool` 抽样） |
| `POST /capabilities/scan-experts` | `require_login` | `capabilities.py:101-104` |
| `POST /capabilities/teams` | `require_login` | `capabilities.py:125-128` |
| `POST /skills/scan`、import-url、sync-adapters、candidates 写 | `require_admin` | `skills.py:41-43` 等 |
| `PUT/DELETE /newapi/channels/{id}/config` | `require_admin` | `newapi.py` 文件头 L10 + L96-119 |
| `PUT /llm/providers/{id}/activate` 及供应商 CRUD/test | `require_admin` | `llm_providers.py` 文件头 L9 + 写端点 |
| `PUT /configs/{key}` | `require_admin` | `configs.py:43` |
| `/rbac/*` 写（角色/权限/菜单/部门） | `require_admin` | `rbac.py` 全部写端点 |
| `_ROLE_PERMISSIONS["admin"]` | 投影 | `auth.py:108-114` 含 `menu:newapi` / `menu:llm` / `menu:platform-ops` |

`test_b1c_capabilities_coverage.py:4-6,96-97` 把「viewer 亦可 scan/verify」写成契约——收紧守卫必红，须与实现同 PR。

### 2.3 本机路径泄漏（FR-13，仍在）

- 公开技能：`PublicSkillResponse` 无 `file_path`（仍对）。
- 公开能力：`_PUBLIC_ASSET_FIELDS` 无路径（仍对）。
- **管理** `GET /capabilities/{type}/{name}` **仍返回 `file_path`**（`capabilities.py:193`）。
- `SkillDetailResponse.file_path` 管理详情默认带出（`platform_core/schemas/skill.py:77`）；Router `_read_skill_files` 读盘（`skills.py:221,290`）。

### 2.4 到期登录（仍可过）

- `TenantExpiryService` **未挂** `create_app` lifespan（`backend/app/__init__.py` lifespan 有 consumer/scheduler/LLM flush/newapi，**无** expiry）。
- `AuthService.authenticate` **不读** `tenants.status`（`auth_service.py:44-96`）。
- `test_expired_tenant_login_rejected` 只断言 status 列 = `expired`，**没有** `POST /login`（`test_saas_signup_expiry.py:62-91`）。测试名撒谎。

旧 spec 未冻这条；v2 是否纳入 Wave 0 **回 pm**。代码事实：过期仍可登录。

### 2.5 外部 Key（GWT-08.4 类）

空名单拒绝已在：`validate_api_key` 无配置 → False（`webhooks.py:106-108`）。`query_public_results` **仍无 `tenant_id` 参数**（`spider_query_service.py:91-114`；`external_api/v1/public.py:69-75`）。平台共享钥匙按爬虫名拉数 = 跨租户出口。租户自助钥匙是下一波；**无绑定则拒绝** 是旧合同已写的 Wave 0 约束，现网未做绑定维。

---

## 3. 入队丢 `tenant_id`（FR-09，仍在）

`SpiderTaskService.enqueue(..., tenant_id=None)`（`spider_task_service.py:152-204`）：

1. `if tenant_id is not None` 才打并发配额 → **跳过**。
2. `repo.create(..., tenant_id=None)`。
3. `before_flush`（`tenant_context.py:120-132`）：**只断言不回填**。HTTP 租户态（ContextVar 会随 `asyncio.create_task` copy）→ `ValueError`。
4. 无上下文（调度器）→ 断言跳过 → MySQL **IntegrityError**（017 `spider_tasks.tenant_id` NOT NULL）。
5. Redis 消息 `tenant_id` 取自参数，不是 flush 后的行。

| 路径 | 传 tenant_id？ | 证据 |
|------|----------------|------|
| `POST /spiders/run` | **是**，`user.tenant_id` | `spiders/tasks.py:64-67` |
| `POST /templates/{id}/run` | **否**（Router 有 `user` 不往下传） | `templates.py:87`；`create_task_from_template` `spider_registry_service.py:372-376` |
| 调度 `_fire` | **否**（`schedule.tenant_id` 因 TenantMixin 存在但闲置） | `schedule_service.py:274-275` 走门面 |
| AI 试采 | **否**（门面签名无该参数） | `orchestrator.py:214-216`；`spider_service.py:78-79` |
| `AiPlan` create | **否** | `orchestrator.py:63-66` `repo.create` 无 `tenant_id`；`AiPlan` 有 `TenantMixin` → 租户态同一断言 |
| `test_saas_wiring.py::test_enqueue_carries_tenant_and_quota_rejects` | 只测 Service **显式传入** | 不测门面/调度 |

`background_session` 可按锚派生 scope（`test_background_session.py`）——调度入队应走这条或显式传 `schedule.tenant_id`，而不是裸门面。

**新方案硬约束：** 修入队时 **门面必须转发** `tenant_id`；本波 **不拆** R12 门面（旧 contract 已知债）。禁止用「Mixin 回填」绕过——P-BE-03 / `before_flush` 明文禁止。

---

## 4. 配额 / LLM（FR-10/11/12/16，仍失败）

### 4.1 月度套餐闸未接线

`QuotaService.check_llm_tokens_month` **仅** `test_saas_quota.py` / `test_saas_byok.py`。生产 `llm_chat`（`llm_client.py:253-334`）熔断读 **全局** `LLM.MAX_TOKENS_BUDGET` + Redis 月用量。

`record_usage` 月字段写入仍是 `{dim}|total`（`llm_usage_service.py:102`），**不含 tenant**。`get_month_used` 读才尝试 `{tkey}|{dim}|total` 再 fallback 旧三段（L120-122）——即使用上 Redis 熔断也不是租户套餐。

接线点只有一处：`llm_chat` 入口。规划/试采修复/技能评分全部走它。

ADR-0014（旧，作约束备忘）：套餐未尽而 provider 预算尽 → **不得** 映射 `QUOTA_EXCEEDED`。用户看见的是套餐文案（FR-12）；provider 账是内部成本。

### 4.2 候选占配额 / 进「我的结果」（FR-11）

- 候选 = `spider_results.source=marketplace`（`skill_harvester.py`；`SkillService.list_candidates`）。
- `check_result_storage` COUNT **不排除** marketplace（`quota_service.py:104-109`）。
- `search_results` / 数据中心 **无** `source` 过滤（`spider_query_service.py:192-217`）。
- `list_candidates` 全表拉 marketplace 再内存切片（`skill_service.py:437-455`）；租户态只能看见本租户候选。

旧 ADR-0013（备忘，非 v2 合同）：**禁止** 候选行 `tenant_id` NULL（与 017 冲突）；Wave 0/1 不新建候选表，用谓词。v2 若改独立表须 pm+architect+dba 一起重开。

### 4.3 文案 / 时区

- `QuotaExceededException(code="QUOTA_EXCEEDED", status_code=429)`；文案「联系平台管理员提升套餐」，不是「去结果库 / 申请提升配额」。
- 用量 API **不算** 70–89% 警告，无 `percent`/`warn_level`/`timezone`。
- `GET /tenants/me/usage` = `require_tenant_manager`：超管无 `tenant_role` → 403，不是「用量属于企业空间」。
- `tenant_usage.py:26`：`datetime.utcnow().strftime("%Y-%m")`。
- `llm_usage_service._today()` = `date.fromtimestamp(time.time())`（机器本地/UTC，不是 Asia/Shanghai）。

### 4.4 导出（FR-03）

`export_results` 仅 `csv|json`，**流式全量无 100 条帽**（`spider_query_service.py:138-157`）。数据中心列表 `page_size le=100`。无 xlsx。旧契约曾把 100 条写进 **导出**；现网未做。v2 须 pm 再冻一次，backend 不代选。

---

## 5. Power Market：仍 0 命中

本帽 grep（py/yml/yaml + 源码标识符）：

| 标识 | 命中 |
|------|------|
| `POWER_MARKET` | **0** |
| `listing_state` | 仅 `CONTEXT.md` 词条 |
| `capability_sources` / `capability_installs` / `capability_aliases` / `resolve_origin_path` | **0** |
| `config/default/power_market.yml` | **不存在**（`config/default/` 无此文件） |
| `backend/services/power_market/` | **不存在** |
| `backend/config_consts.py` 对应常量 | **无** |

### 5.1 管理 API 缺口（对照旧市场契约，仅作缺口清单）

| 设计路径 | 现状 |
|----------|------|
| `GET/POST/PATCH /sources*`、`POST .../sync` | **缺失**；`type=url` 422 无实现 |
| `PATCH /{type}/{name}/listing` | **缺失** |
| `PATCH .../license-override` | **缺失** |
| `PUT .../aliases` | **缺失** |
| `GET /plugins/{name}/components` | **缺失** |
| `POST /scan-plugins` / `verify` | **存在，`require_login`** |
| `POST .../enable-host` | **缺失**（D21 本就不代写宿主） |
| `GET /capabilities` listing/source/origin/q | 列表在；无 listing/source；`q` 只 `name LIKE`（`capability_service.py:44-46`） |
| `GET /{type}/{name}` 去 `file_path` | **仍返回** |

### 5.2 租户安装 / 公开面

- `/api/v1/tenants/me` 只有 `usage` / `usage/by-member`。`/tenants/me/installs` **整组缺失**。
- 公开：`GET /public/capabilities` 写死 `status="stable"`，丢掉 recommended，无 listing、无许可（`public_skills.py:173-175`）。类型枚举仍四类旧名。
- `GET /public/capabilities/{type}/{name_or_slug}` **整条缺失**。
- `GET /public/skills` 仍独立查 `skills` 表；`list_skills(status=None)` 后再内存滤发布态，`total=len(published)` = **当前页过滤后条数**。
- IP 限流：`await get_async_redis()` + fail-open；**INCR 与 EXPIRE 非原子**（`public_skills.py:79-83`）。

### 5.3 D5 / D16 扫描（实现硬约束，代码碰巧部分等于回退）

`PluginService.scan_plugins(root=None)` 钉死 `SKILLS.LIBRARY_ROOT/plugins`（`plugin_service.py:46-52`）。**碰巧等于 D16 回退**。差距：HTTP 不接受 `root=`；无 `POWER_MARKET.ENABLED`；`iterdir` 含 symlink、不跳过 `.` 开头、无 `relative_to` 逃逸检查；无 Kimi `kimi.plugin.json`；bundled 一层目录名不入 `skills` 表。

无 MCP → `health_status=degraded`（`plugin_service.py:191-192`）。设计/旧 FR-26：`unknown`，允许 listed。`test_b1c` / `test_mcp_bridge` 依赖今日语义——切源不得破坏这批夹具；改 unknown 是 breaking，须同改测试。

`SkillService.scan_library`：`dir_names` 只有 `LIBRARY_ROOT/skills/*`；库内不在目录的 name 一律 `sync_state=missing`（`skill_service.py:150-153`）。D4 提升后的 `mattpocock-skills__code-review` **必然被标 missing**。

写盘无 `writable` 守卫：`_write_back_meta` / `_append_changelog` / `correct_meta`（`skill_service.py:617+`）。API 守卫 `require_operator`（比 scan 更宽）。第三方无 `meta.yaml` 时写回失败仅记 job，仍尝试写源树。

MCP 桥：模块头写 stdio/HTTP，实现 **仅 stdio**。白名单 node/npx/python3/python/uvx/uv。**禁止**把 `call_tool` 扩成平台 Agent 运行时（ADR-0014 备忘）。

### 5.4 ORM / 豁免（给 dba）

`TENANT_EXEMPT_TABLES` 含 `skills` 三表，**不含** `capability_assets`（`tenant_isolation.py:30-53`）。模型注释自称「豁免白名单」（`capability.py:46`），代码没登。

`do_orm_execute` 对 UPDATE/DELETE：有列未豁免 → `WHERE tenant_id = <当前>`。租户态 `upsert_skill_asset` 的 ORM UPDATE **0 行命中**（SELECT 因无 Mixin 不过滤，读路径「看起来正常」）。`upsert_skill_asset` 走 ORM setattr + flush（`capability_service.py:82-86`），不是 Core，但同一注入。

`capability_installs` **不得**进豁免（表尚未存在；v2 schema 时写进合同）。

`skills.source_type` VARCHAR(16)；`marketplace_crawled` **19 字符**——MySQL 截断/报错。SQLite 测试看不见。

---

## 6. 分层违约（Router → Service → Repository）

爬虫子域仍是合格样板：`spiders/*.py` → `Spider*Service` → `backend/repositories/spider_*_repository.py`。

### 6.1 Service 跳过 Repository

| 服务 | 数据访问 |
|------|----------|
| `CapabilityService` | `select(CapabilityAsset)`，无 repo；`list_assets` **无入口 `logger.info`**（R10） |
| `PluginService` / `ExpertService` / `TeamService` | 直写 ORM |
| `QuotaService` | `select(Tenant/SpiderTask/SpiderResult/LlmTokenUsage)` |
| `SkillService` | 列表走 `SkillRepository`；scan / correct_meta / candidates 直写 ORM |
| `RbacService` | 直写 Role/Permission/Menu/Department |

Wave 1 若沿用 PluginService 风格，源同步事务与 listing 短事务会继续散落。市场域 **新建** repository（回 architect 分层合同，本帽不发明表）。

### 6.2 Service 返回 ORM，Router 手写投影

`list_assets` / `get_asset` 返回 `CapabilityAsset`。Router 拼 dict，管理详情送出 `file_path`。公开面另一套 `_PUBLIC_ASSET_FIELDS`。`listing_state` 一旦加上，三处投影会裂。P-BE-01：禁止把活 ORM 传出 Service 再读。

### 6.3 Router 掺业务

- `public_list_skills` 内存滤发布态 + 错误 total。
- `public_list_capabilities` 写死 `stable`。
- `capabilities` 写路径鉴权即业务范围。
- `skills._read_skill_files` Router 读盘。

### 6.4 过渡门面 / 残骸

- `spider_service.py` 门面 `enqueue` 不转发 `tenant_id`——FR-09 根因，不是风格债。
- `backend/services/litellm/` **只有 pycache**；`api/v1/__pycache__` 残留 `api_keys` / `billing` / `litellm_admin`。LiteLLM **不进本特征**。实现时当退役残骸清，不当合同。
- `billing_service.pyc` 同属幽灵，勿当计费已落地。

### 6.5 R10 logger 名

大量服务 `get_logger("api")`（`schedule_service` / `llm_client` / `llm_usage_service` / `orchestrator` 等）。配额/市场新代码用 `service.<domain>`。

---

## 7. Redis / 中转站

R11 生产已清。`get_async_redis()` 是 **同步工厂**。市场/配额新代码固定：`redis = get_async_redis()`（不 await 工厂），再 `await redis.*`（P-BE-02）。

键：中转 `newapi:channel:cfg:` / `newapi:scheduler:state:`（无租户）。公开限流 `SKILL_PUBLIC_RATE_PREFIX`。配额 `quota:count:` TTL 60s。LLM 日明细四段含 tenant；**月度写入无 tenant**。

中转分层尚可：Router → Overview/ChannelConfig → repository + Redis。远程失败 overview **HTTP 200 + available=false**。`ChannelConfigInfo` **无明文 Key 字段**（仅额度窗口）。渠道窗口 ≠ `tenants.quota`（定价不得混写）。探针伪装今日不自动下线——产品定位未关前不要改行为。

`channel_scheduler_service` 独立 engine 读 `NEWAPI.DB_DSN`（R1 合规）。

---

## 8. 智能采集 · Spider APIs（守卫地图，未变）

| 子域 | 读守卫 | 写守卫 |
|------|--------|--------|
| 任务 | login | operator 入队/控制；admin 删除 |
| 结果 | login | admin 删除；export 流 csv/json |
| 定义/节点/文件/代理 | login / operator(proxy) | admin CRUD 定义 |
| 调度/告警 | login | admin |
| 模板 | login | operator |

- 入队 **不检查** 在线 Worker（Wave 4 stub，Wave 0 不要顺手做）。
- `POST /ai/plans/{id}/register` 已要求最近试采通过 + admin。
- 定义唯一 `(tenant_id, name)`；scrapy 进程内全局文件。同名登记 ≠ 独立代码。
- consumer 回流 `tenant_id=msg.get("tenant_id")`（`consumer.py:671`）——消息没带则 NULL/IntegrityError，与入队丢租户同一爆炸链。`check_result_storage` 在回流路径会调（L694），但谓词含候选。

---

## 9. 全新方案必须吸收的后端约束

下列是 **现网 + 已 Accepted 设计 + 宪法** 的硬约束。v2 spec/contract **不得写反**；旧票号可作废，约束不行。

### 9.1 鉴权 / 隔离

1. `require_admin` **永远不是** 平台超管。平台目录写 / 渠道窗口写 / 平台 LLM 行写 → `require_platform_admin`。
2. 租户 BYOK（`llm_providers.tenant_id = 当前租户`）CRUD/激活必须留下给 `require_tenant_manager`；一刀切收成超管会误伤已兑卖点。`activate_exclusive` 已按租户域互斥（`llm_provider_repository.py:39-60`）——API 守卫还没跟上。
3. `before_flush` **只断言不回填**。新行 `tenant_id` 必须调用方写入。禁止「NULL = 平台候选/平台任务」。
4. 非超管无 `tenant_id` → 401，不是 `platform_scope`（P-BE-03；迁移 024）。
5. 超管无企业空间：installs **403**（旧 FR-20.3）。不要开「模拟租户」后门除非 pm 另开 FR。
6. `capability_assets`（及平台目录子表）必须进 `TENANT_EXEMPT_TABLES`；`capability_installs` **禁止**豁免、必须 TenantMixin。豁免清单只活在 `backend/app/tenant_isolation.py`（B1：`platform_core` 不写业务表名）。
7. 登录信封 **已有** `is_platform_admin`——v2 不要当缺口重做后端；缺的是前端执法与 `_ROLE_PERMISSIONS` 不再把 `menu:newapi` 发给租户 admin。
8. 渠道页对租户：直打与「页面不存在」同构，**不是**道歉式 403（旧 GWT-07.3）。后端 404 vs 403 须与 frontend 一起冻。
9. Wave 0 用户可见收权 **不依赖** `require_permission(btn:…)`（今日无此 Depends）。按钮码可随 Wave 1 种子；不能把超管守卫改回 `require_admin`。
10. 收 scan/verify 必须 **同 PR** 改 `test_b1c`（今日金标与超管拒绝互斥）。

### 9.2 入队 / 配额 / LLM

11. 所有产任务路径把 `tenant_id` 传入 `SpiderTaskService.enqueue`；门面 **转发**，本波不删除门面。
12. `spider_results.tenant_id` / `spider_tasks.tenant_id` **NOT NULL**（017）。禁止放宽；禁止平台候选 NULL 行。
13. 市场候选若仍住 `spider_results`：COUNT / 数据中心 / 导出 / 「我的结果」同一谓词 `source <> 'marketplace'`（或等价）。超管候选列表 SQL 分页，禁止全表进 Python。
14. `llm_chat` 调用模型 **之前** `check_llm_tokens_month`；`year_month` = **Asia/Shanghai**，禁止 `datetime.utcnow()`。
15. 两本账：套餐闸 = 用户可见 `QUOTA_EXCEEDED` 文案；provider Redis `MAX_TOKENS_BUDGET` 保留作成本熔断。套餐未尽而 provider 尽 → **不得**出现 `QUOTA_EXCEEDED` 字样。
16. 月度 Redis field 历史无 tenant：执法走 `llm_token_usage` 表；Redis 演进交 dba，不挡套餐闸。
17. 无租户上下文（平台内部）跳过套餐闸，与并发闸对称。
18. consumer 只信消息体 `tenant_id`，Mixin 不会救回流。

### 9.3 Power Market / 扫描 / MCP

19. **不**另起 `/market` 微服务。市场落既有单体 + `backend/services/power_market/` 子包。
20. **不**合并 `skills` 三表与 `capability_assets`（双写继续；禁止第三份）。
21. `power_market` **禁止** import `spider_*` 内部；候选审核留在 SkillService 端口。
22. 源索引 **不是** 爬虫（R3/R4/B2）：不要让 scrapy 写目录表。
23. D16：`POWER_MARKET.ENABLED` 默认 **false**；关或 SOURCES 空 → 今日 `LIBRARY_ROOT/plugins` 遍历，**不**插入 `library_plugins` 源行。`test_b1c` / `test_mcp_bridge` 夹具必须继续绿。
24. D5：`writable=0` 禁止 `_write_back_meta` / `correct_meta` / changelog 写源树；`scan_library` missing 只扫第一方行。
25. D14：写面 `require_platform_admin`，**禁止** `require_admin`。
26. `type=url` 保留枚举、POST **422**，无适配器。
27. `UNLISTABLE_PACKAGES` 含 `dev-team`；sync 不得标 listed。
28. `AUTO_AGENTS_POWER_MARKET_SOURCES` = JSON 数组字符串，`json.loads` 后 **整表替换** yml，禁止与 Dynaconf list 按下标 merge。
29. 静态前缀路由必须注册在 `GET /{asset_type}/{name}` 之前（`capabilities.py` 文件头已有此约束）。
30. 公开类型须对齐 CONTEXT 五类（`command` / `agent` / `team`），不要继续只认 `expert` / `expert_team` 除非 pm 冻别名映射。
31. `mcp_bridge.call_tool` **仅**验证抽样。NFR-04 listed ≠ trusted ≠ enabled。
32. 不代写 `~/.zcode` / 宿主 `config.json`（D21）。
33. 无 MCP → 目标态 `unknown`（可上架）vs 今日 `degraded`：breaking，须同改测试。
34. Feature flag 打开前 **禁止**写市场 Router；schema PR1 之前禁止 listing/installs 端点。

### 9.4 宪法 / 实现纪律

35. API **禁止** import ORM（R7）。Service 出 DTO。commit 前捕获 `int(obj.id)`（P-BE-01）。
36. async 禁止 `redis_client().` 链式直调（R11）。
37. 新手写 Alembic SQL；autogenerate + expand-contract（ADR-0002）。Alembic 头今日 = **027**（设计稿「030_*」过期）。
38. 新 logger：`service.<domain>`，不要 `"api"`。
39. LiteLLM 替换 / 恢复路由 **不进本特征**。
40. 不把 `backend/services` 一次性搬成 `domains/`。
41. 不改 Scrapy 管道、Redis 队列协议、Worker 调度（采集执行面下一波）。
42. 闸门：`uv run pytest -x -q backend/tests`；`bash scripts/check-arch.sh`；数据契约再加 `bash scripts/check-db-migrations.sh`。市场新测必须进 `backend/tests`（前端 Jest 不在 test 闸）。
43. CI MySQL 子集 **不含** `test_b1c` / `test_skill_public_api`——唯一键/许可闸/VARCHAR 截断在 SQLite 假绿。`marketplace_crawled` 19 vs VARCHAR(16) 是现网定时炸弹。
44. 适配器 `uri` 禁止硬编码 `/Users`（R1 / check-arch）。
45. git `CACHE_DIR` 多实例抢 clone：设计未写锁；实现前 architect 要钉「文件锁 vs 只读已 clone 树」。

### 9.5 明确不做（防回流）

LiteLLM 当规划 backend；MCP 工具面；代写宿主配置；xlsx；模板商店；外部 Key 绑租户自助（下一波）；支付/发票；开发者门户/分成；专家团站内执行；平行市场服务；候选表（除非 pm 重开）；把 `platform_core` 写上业务表名。

---

## 10. 合同问题（本帽拒绝静默改）

回 **architect**（v2 塑形时回答，不要假设旧 ADR 已生效）：

1. `require_permission(btn:market:*)` 是否 FastAPI Depends？Wave 0 是否只改 `require_platform_admin`？
2. 租户 BYOK 的 `/llm/providers` 在收权后如何拆「平台行 vs 本租户行」？
3. Service 返回 ORM vs DTO：市场新字段继续手写 dict 会裂。
4. FR-12：信封是否继续带 `code=QUOTA_EXCEEDED`（前端已依赖）vs 用户文案不得出现该字样。
5. FR-11：marketplace 继续住 `spider_results` 加谓词，还是独立表。
6. 渠道直打：后端 404 还是前端藏 + 后端 403。
7. `_ROLE_PERMISSIONS` / RBAC 写 / `PUT /configs` 是否纳入「平台写面」收权，还是另开 FR。
8. 公开五类枚举与旧 `expert_team` 回填映射谁写。
9. git 适配器并发。
10. 公开限流 INCR/EXPIRE 原子化是否 Wave 0 卫生。

回 **dba**：

1. `capability_assets` 等豁免；`capability_installs` 不豁免。
2. PR1 列/表 autogenerate，禁手写 SQL；头在 027 之后。
3. `skill_jobs.source_id`；`skills.source_type` 放宽（`marketplace_crawled` 超 VARCHAR(16)）。
4. LLM 月度 Redis field 补 tenant（expand 双写）——不挡 FR-10。
5. 公开限流原子化。
6. 平台占位租户：超管触发的 marketplace 入站 FK 目标（若沿用 ADR-0013 语义）。

回 **pm**（验收不可达则停）：

1. `test_b1c` viewer 可 scan 与「租户 admin 扫描 403」互斥——必须改验收/用例，不能留双金标。
2. 到期登录拒绝：无冻结 FR；测试名撒谎。做不做进 Wave 0。
3. FR-15 埋点存储选型未写（本帽不选）。
4. 调度入队无 tenant：**必须**进诚实/隔离波，不是「另开票」。
5. FR-03 的 100 条是导出截断还是仅列表分页。
6. 无 MCP `degraded` → `unknown` 是否本程序 breaking。
7. RBAC/系统配置写面是否与中转/市场同一波收。

---

## 11. 建议实现顺序（诊断建议，非开工、非 v2 合同）

**无新表也可做（诚实/收权波）：**

1. 入队全路径 `tenant_id`（门面转发 + 调度 `schedule.tenant_id` + 模板/AI `user.tenant_id` / plan 行）；AiPlan create 同样写入。
2. `llm_chat` 前 `check_llm_tokens_month`（上海月）；保留 provider 熔断但映射两本文案。
3. 结果 COUNT / 数据中心 / 导出排除 `source=marketplace`（或按新合同改表）。
4. 平台写面 → `require_platform_admin`；**同 PR 改 test_b1c**。BYOK 行除外待合同。顺手评估 RBAC/configs/`_ROLE_PERMISSIONS`。
5. 管理详情去掉 `file_path`；配额文案；用量月用上海时区。
6. 豁免表登记 `capability_assets`（dba 清单，一行代码，不进市场 Router）。

**schema 之后：** D16 回退保持 → 源适配器 + `resolve_origin_path` → listing/许可/公开 SQL → installs。禁止在 schema 前写市场 Router。

---

## 12. 自检（本帽）

- [x] 未改业务代码、未写迁移、未改前端、未改验收文案、未实现 API
- [x] 分层 / 守卫 / Redis / MCP / 配额 / 中转 / 爬虫均引用了具体文件
- [x] 旧诊断 P0 逐条复核：仍在
- [x] `POWER_MARKET` 等标识符 0 命中已用 grep 复核
- [x] 全新方案必须吸收的约束已单列，并标明旧合同 ≠ 现行合同
- [x] 合同歧义已标回 architect / dba / pm
- [ ] 实现证据：不适用（诊断帽）
- [ ] `pytest` / `check-arch.sh`：本帽不改代码，未跑；现网红线按 grep 陈述

---

## open_questions

1. `require_permission(btn:market:*)` 是否做 FastAPI 依赖，还是收权波只改 `require_platform_admin`？
2. 租户 BYOK 的 `POST/PUT /llm/providers` 在平台写面收权后如何保留？
3. `capability_assets` 租户 UPDATE 0 行是否已在手工运营出现？`upsert_skill_asset` 在 scan 里——租户 admin 扫技能就会踩。豁免紧急度 = 收权波。
4. 调度器入队无 `tenant_id`：本地 MySQL 是否已有 IntegrityError 日志？（不论日志都要修。）
5. 到期 `tenants.status=expired` 登录是否本程序必修？
6. FR-12 信封 `code` 字段对前端是否契约？
7. FR-03 的 100 条是导出截断还是仅列表分页。
8. FR-15 事件写哪——回 architect，backend 不选仓。
9. git 适配器 `CACHE_DIR` 多实例：文件锁还是只读已 clone 树？
10. 平台超管无 `tenant_id` 时 installs 403：运营如何自测商店。
11. `GET /public/skills` 错误 total：收权波修还是随公开面弃用转调。
12. 公开限流 INCR/EXPIRE 非原子：收权波卫生还是跟市场公开面一起。
13. `/rbac` 写与 `PUT /configs` 是否与 FR-06/07 同波收成超管。
14. 公开资产类型四名 vs CONTEXT 五类：谁写映射、谁改 API。
