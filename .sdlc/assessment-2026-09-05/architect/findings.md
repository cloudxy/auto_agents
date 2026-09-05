# 架构现状测绘（第 0 步）—— auto_agents

> 日期：2026-09-05 ｜ 性质：只读评估，未改动任何代码 ｜ 方法：sdlc-workflow/architect 第 0 步（边界 / 约束 / 债）

## 总体判断

骨架质量高于同类项目平均水平：分层主干（api → service → repository）大体单向，`spider_service` 是 98 行的薄组合门面而非大杂烩，platform_core 对 backend/scrapy 无 import 级反向依赖，B2（scrapy ⇏ backend）实测干净，docs/adr/ 有 5 份 ADR，backend/tests 约 90 个测试文件覆盖了多数 service。**但边界质量结论是：宏观单向成立，微观有 6 处实质穿透，且边界强制设施本身有假阴性**——R7 正则匹配不到 `from platform_core.models.<子模块> import` 形式，API 层直连 ORM 实际存在 8+ 处而检查报绿；R9 用运行时 `import backend.app` 判环，捕获不了靠「文件末尾 import + PEP 562 惰性门面 + 函数内延迟 import」掩盖的 service 循环依赖（ai_planner / skills / llm_provider 三角）。最大的结构性债不在分层，而在 **service 网状依赖**与**事务所有权分裂**（18 个 service 内 commit，同时 4+ 个 API 文件路由层 commit）。门禁可信度是第一优先级：检查脚本的漏检会系统性放大所有其他边界的腐烂速度。

「本次不动什么」：本次为测绘，不动任何代码；后续任何改造工单应先修 R7 正则再谈其他边界治理，且不应顺带重构 ai_planner 兼容层（其 docstring 声明的晚绑定语义被 3 个测试文件的 patch 路径依赖）。

## FINDINGS（按严重度排序，blocker 0 / major 6 / minor 6）

### 1. R7 门禁正则漏检：API 层直连 ORM 实际存在而检查报绿
- **严重度**：major
- **证据**：`scripts/check-arch.sh:71-72` 正则为 `from.*\.models import`，匹配不到带子模块的写法。实测违规（均存活于「全绿」状态）：模块级 `backend/app/api/v1/rbac.py:17-18`、`skills.py:21`、`public_skills.py:21`、`backend/app/api/deps.py:21`；函数内延迟 `members.py:115-116`、`auth.py:126/146/188`。
- **为什么是问题**：宪法红线的机械检查存在假阴性，「全绿」不可信，所有依赖该门禁的边界结论都被牵连；且团队已形成「函数内 import 即可绕过」的隐性习惯。
- **建议**：正则改为 `from platform_core\.models(\.| import)` 并去掉行首锚定的绕过空间（或直接用 ruff 的 banned-api / import-linter）；修复后存量 8 处逐个下沉到 service。

### 2. service 层循环依赖环，靠语法手段在运行时打破
- **严重度**：major
- **证据**：`ai_planner_service.py:22` import ai_planner 包，而包内 `llm_client.py:419`、`orchestrator.py:381`、`state.py:153`、`url_guard.py:160` 在文件末尾反向 `import ... ai_planner_service as _facade`（PEP 562 惰性门面）；`skill_service.py:414` ⇄ `skill_import_service.py:287` 互相函数内延迟 import；`llm_provider_service.py:64/72/312/399` 反向触达 ai_planner 域（cooldown clear / facade fallback）。
- **为什么是问题**：模块依赖图有环 = 无法独立测试与独立演进，改动传染；环被文件末尾 import + 惰性 `__getattr__` 掩盖后，R9（`import backend.app` 不报错即绿）永远检不出来，新人极难理解初始化顺序约束（ai_planner_service.py 用 20 行 docstring 解释这套魔法本身就是证词）。
- **建议**：抽公共下沉层（cooldown / 配置解析 / llm_chat 已是事实共享概念，应成为被依赖的叶子模块），门面只做 re-export 不回引；补一条 ast 级（非运行时）环检测进 check-arch。

### 3. 事务所有权分裂：service 内 commit 与路由层 commit 两种模式并存
- **严重度**：major
- **证据**：service 内 commit：18 个文件（`grep -l "commit()" backend/services` 含 spider_task_service、auth_service、schedule_service 等）；同时路由层 commit：`skills.py`（9 处）、`llm_providers.py`（2 处）、`rbac.py`（8 处）、`members.py`（未提交变更新增 `await session.commit(); await record_audit(...)`）。`backend/app/api/deps.py:34` 注释自认坑：「后续路由若发生 session.commit()，ORM 对象属性会全部过期」。
- **为什么是问题**：同一仓库两套口径，每个新端点都要猜；审计写入（record_audit）与业务写库是否同事务没有统一答案，隔离性语义因文件而异；deps 里的属性过期坑就是该分裂已造成的实际返工证据。
- **建议**：ADR 定死唯一所有权（推荐：service 拥有事务与审计，路由只组装参数），存量按域迁移，不搞一次性大改。

### 4. API 层绕过 service 直连 repository（跳层）
- **严重度**：major
- **证据**：`backend/app/api/v1/skills.py:16`、`public_skills.py:17`、`backend/app/external_api/v1/public.py:15-16` 直接 import repository；且 public.py 同时 import `SpiderService` 门面——同一文件两种调用风格混用。
- **为什么是问题**：跳层后租户过滤、审计、缓存等 service 层横切策略对这几个端点全部失效，行为与其他路由不一致；skills 域恰又是租户豁免表，绕行风险叠加。
- **建议**：为这三个文件补薄 service 或把 repository 访问收敛到既有 SkillService / SpiderQueryService；R 系检查增加 api→repository 禁止规则。

### 5. platform_core 硬编码业务表名（基建泄漏业务语义）
- **严重度**：major
- **证据**：`platform_core/tenant_context.py` 的 `TENANT_EXEMPT_TABLES` 含 `skills/skill_reviews/skill_jobs`（注释自认「skills 域 D3 平台级统一库」）与 `llm_provider_models`。tenant_context 双文件实为分工（`platform_core/tenant_context.py`=作用域原语+ORM 事件钩子，`backend/app/middleware/tenant_context.py`=JWT 解析中间件），非重复实现——但豁免白名单落在了基建侧。
- **为什么是问题**：B1（platform_core 只依赖 config）在 import 层面合规，语义层面被穿透：新增一个平台级业务表必须改 platform_core，业务变更理由进入基建的变更理由，违反「变更理由单一」判据。
- **建议**：豁免表清单改为配置（config 驱动）或由 models 侧 mixin/声明携带（如 `__tenant_exempt__` 类属性），platform_core 只读机制不持名单。

### 6. 未提交变更：uvicorn→loguru 日志接管内嵌于编排入口
- **严重度**：major
- **证据**：`run_backend.py`（未提交 diff +32 行）：`_UvicornToLoguru` handler 类定义在编排脚本内，清空 uvicorn.access/error handlers、`log_config=None`。同批 `platform_core/logger.py`（+3 行 loguru 默认 extra，修复 KeyError，低风险、方向正确）与 `run.py`（排水线程 BrokenPipe 防僵死，合理）。docker-compose 与 Dockerfile 均走 `run_backend.py`，单入口成立，无双路径分叉。
- **为什么是问题**：日志基建逻辑落在编排脚本而非 platform_core/logger——换任何启动方式（`uv run uvicorn backend.app:app`、gunicorn、未来 reload 变体）接管即静默失效回到同步写 stdout；handler 不可单测、不可被 scrapy 侧复用；接管依赖 `logging.getLogger("uvicorn")` 的内部结构，属对第三方实现细节的脆弱耦合。
- **建议**：把 `intercept_uvicorn_logging()` 迁入 platform_core/logger.py（与 init_log 同处），run_backend 只调用；补一条「接管后 uvicorn.access 无自有 handler」的断言测试。

### 7. 应用工厂与模块级单例并存
- **严重度**：minor
- **证据**：`backend/app/__init__.py:248` 模块级 `app = create_app()`，run_backend.py:78-79 又 `from backend.app import create_app; app = create_app()`。
- **为什么是问题**：import 即实例化，`import backend.app`（R9 检查自己就在做）每次触发完整装配路径；两份 app 实例并存使 lifespan/中间件时序 reasoning 变复杂。
- **建议**：保留工厂，单例交给入口（或 uvicorn factory 模式 `backend.app:create_app`）。

### 8. create_app lifespan 手工装配 9 个后台组件，无注册表
- **严重度**：minor
- **证据**：`backend/app/__init__.py:75-209` 约 135 行，每个组件 start+stop 各一套 try/except 样板（consumer/scheduler/proxy_health/llm_usage_flush/skill_scoring/llm_health_patrol/newapi_scheduler/newapi_probe/启动对账）。
- **为什么是问题**：新增后台组件要改两处且复制样板；启停顺序隐含在代码顺序里，无显式声明。
- **建议**：组件注册表（name → start/stop/开关）+ 统一启停循环，lifespan 缩到 20 行内。

### 9. 跨 service 引用私有成员
- **严重度**：minor
- **证据**：`channel_config_service.py:170` 引 `channel_scheduler_service._main_async_session`；`newapi_overview_service.py:23` 引 `newapi_api._map_channel`（模块级公开 import 的下划线函数）。
- **为什么是问题**：私有名跨模块 = 封装漏了，被引用方重构签名时调用方静默崩（无契约、无测试保障该边）。
- **建议**：提为公开函数或下沉到共享模块。

### 10. 逻辑集中点：consumer 815 行 / spider_task_service 707 行 / skill_service 617 行
- **严重度**：minor（三者均有测试覆盖，故不升 major）
- **证据**：`wc -l` 排序：`backend/tasks/consumer.py` 815（全仓最大）、`spider_task_service.py` 707、`skill_service.py` 617、`channel_scheduler_service.py` 515、`channel_probe_service.py` 475。skill_service 单文件承担 tier 派生 + 扫描入库 + 矫正写回 + LLM 相似建议 + capability 回填触发（docstring 自述「后续工单在本模块生长」），变更理由不单一。
- **为什么是问题**：数据闭环逻辑分散于 consumer（编排）与 spider_task_service（业务）两处，改任务流要同时懂两个大文件；skills 域是全仓最高频演进区，617 行只会继续涨。
- **建议**：按能力切（scan / correct / suggest / catalog 各自模块），consumer 只留队列消费与重试骨架。

### 11. capability_service 零直接测试引用
- **严重度**：minor
- **证据**：`grep -rn "capability_service\|CapabilityService" backend/tests` 为空；`test_capability_catalog.py` 经 SkillService 间接覆盖扫描回填路径，`capability_service.py` 自身的读写分支（NotFoundException、列映射 `_SKILL_TO_ASSET` 17 列同步）无直接用例。
- **为什么是问题**：`_SKILL_TO_ASSET` 是 skills 表 ↔ capability_assets 表的隐式契约，加列时无测试兜底，静默漏回填。
- **建议**：补列映射守恒测试（skills 列变动时该映射必须显式更新）。

### 12. 文档与代码布局漂移
- **严重度**：minor
- **证据**：AGENTS.md 模块地图将 services/repositories 描述为 backend/app 的组成；实际在 `backend/services`、`backend/repositories`、`backend/tasks`、`backend/utils`（backend/ 顶层，与 app 包平级）。
- **为什么是问题**：新人按文档找代码找不到；`backend/app`（应用包）与 `backend/*`（业务包）的双层布局本身可行，但未被告知。
- **建议**：更新 AGENTS.md 模块地图一行即可，布局不必动。

## 附：模块依赖图中的异常边

1. **环边（3 组）**：`ai_planner_service ⇄ ai_planner 包`（4 文件末尾反向 import）；`skill_service ⇄ skill_import_service`（函数内延迟）；`llm_provider_service ⇄ ai_planner`（cooldown clear + facade fallback，双向触达）。
2. **跳层边**：`api/v1/skills、api/v1/public_skills、external_api/v1/public → repositories`（绕过 service）。
3. **漏检穿透边**：`api/{deps,rbac,auth,members,skills,public_skills} → platform_core.models`（R7 正则盲区，见 F1）。
4. **语义泄漏边**：`platform_core/tenant_context → 业务表名清单`（skills/llm 域知识进基建，见 F5）。
5. **基建外置边**：`run_backend（编排）→ platform_core.logger 之外自成日志接管`，并耦合 uvicorn logging 内部结构（见 F6）。
6. **风格混用边**：`external_api/v1/public → SpiderService 门面 + 直连 repository` 并存（见 F4）。

正常边确认：api → service → repository 主干成立；`spider_service`（98 行）为薄组合门面，query/registry/task 三 service 各自独立可测，健康；backend ⇏ scrapy（B2）实测无违规；scrapy ⇏ backend（R3）干净；config 无反向依赖（B3）。

## 约束清单（改造时的「不能动」）

- uv workspace 单 .venv、uv.lock 必须提交（AGENTS.md 环境红线）。
- 13 红线 + 3 边界（.claude/rules/project_rule.md），check-arch 为提交门禁——但见 F1 的漏检。
- 对外契约：/api/v1、/api/v2、/external/v1 路由形态、alembic 30 个迁移链、capability-library 资产格式、Scrapy 侧 Redis 队列协议（backend ⇄ scrapy 仅经队列）。
- 既有 ADR：docs/adr/0001–0005（插件先验证后分发 / AI 产目标态工具产路径 / 前端 workspace 共享 / 36 表软删 / SaaS 治理单源）——任何改造不得无 ADR 推翻。
- ai_planner 门面的 patch 路径被 3 个测试文件依赖（其 docstring 声明），重构兼容层须连测试一起改。
