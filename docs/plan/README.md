# Auto Agents 平台演进总方案（v2 · 合并版）

> **本文档是 `docs/plan/` 下的方案总入口**。由 v1 三份方案（技能管理中心 / LLM 多平台模型管理 / SaaS 平台演进）+ 总览 README 于 2026-08-31 深度架构整理后合并重写而成；v1 仅存在于工作区且已随合并删除（`docs/*` 此前默认不入库，本次经 .gitignore 白名单调整首次入库）。
> 基线：`feature/project-structure` @ `cf2ab0a`（含 skills-library 首次入库 + 前端端口统一 9112/9113 + 审计第 10 章）。
> 背景诊断：[`docs/architecture-audit-2026-08.md`](../architecture-audit-2026-08.md)（四轮审计 + §10 复核，本方案与其结论一脉相承并在其上修正）。
> **实施状态：E0 + A(P1-P5) + B(M1-M4) + SaaS S1-S5 已全部落地（工单 01-43 全 resolved，至 `474089e`）。**
> **下一轮整理：[`architecture-review-2026-09.md`](./architecture-review-2026-09.md)**——全栈架构评审与 7 个深化候选（含 SaaS 接线 P0 断点 / 权限单真相源 / 管理闭环缺口清单），**待审核**。
> **第三批（进行中）：[`capability-hub-p6.md`](./capability-hub-p6.md)**——能力资产中心（skill/plugin/expert/expert_team 四类资产 + MCP 工具桥验证，ADR-0001），两轮拷问 12 决策已锁；与修复线（评审候选 1/2/3）并行，工单 44-59 见 `.scratch/platform-v3/`。

---

## 1. 定案速览（2026-08-31 两轮拷问锁定，推翻需重议）

| # | 决策 | 取值 |
|---|---|---|
| D1 | 技能数据真相源 | **混合**：内容（SKILL.md/SOURCE.md/CHANGELOG.md）以 `skills-library/skills/<name>/` 文件为准；治理数据（分类/评分/状态/同类/来源）以主库 DB 为准；治理变更**写回 meta.yaml** 作 git 快照 |
| D2 | 技能网络收集 | **分阶段**：一期 URL 导入；二期市场采集爬虫 + 候选审核队列（P5） |
| D3 | 技能租户归属 | **平台级统一库**：全租户共享只读，`tenant_id` 预留恒 NULL，S4 前不启用 |
| D4 | 本地 8765 后台 | **退役**：代码保留标注 deprecated，主 admin 为唯一治理写入口 |
| D5 | 问题清单落点 | 内嵌本方案 §3（不另建文档、不再扩写审计） |
| D6 | 工程基座 | 新增 **Phase E0**（测试基座 / Alembic 修复 / 前端测试清理 / 门禁口径），与 A-P1a、B-M1 并行起步；**A-P2 与 S1 必须等 E0.1 就绪，S1 另需 E0.2** |
| D7 | 测试 DB 策略 | **SQLite 优先 + MySQL 保真开关**：DB 级测试默认 SQLite（create_all + 事务隔离，本地零 Docker）；方言敏感与迁移测试走 `MYSQL_FIDELITY=1` 切真实 MySQL（CI 用 service container 承接） |
| D8 | 文件形态 | 四份文档融合为本文件；阶段代号沿用 P/M/S，新增 E0 |
| D9 | 用量表 4 列化 | 归 **S1**（tenant_id 语义就绪时一次改对）；B-M4 明确不做该迁移，只铺 model_tier/priority/health 数据位 |
| D10 | A×B 依赖 | A 全程可独立起步：P2 评分先用激活供应商默认模型（现有 openai 兼容路径零依赖）；`SCORING.MODEL` 非空指定与多协议评分 = **能力开关**，B-M2/M3 落地后生效（未就绪时启动告警并回退默认模型） |
| D11 | 验收形态 | 每阶段验收分两层：**可自动化验收**（pytest 用例清单 + seam 声明，进 CI）与**手动冒烟清单**（真实凭据 / 浏览器操作，不进 CI） |
| D12 | 导入与展示安全 | zip-slip 防护 / 大小上限 / SKILL.md 评分注入边界 / 官网渲染 sanitize = **必做验收项**（P3/P4），不是附注 |

---

## 2. 现有系统功能地图（已实现，截至 `cf2ab0a`）

| 域 | 已有能力 | 入口 |
|---|---|---|
| **智能爬虫** | 注册表、任务生命周期（优先级队列三档）、结果回流（去重/死信/重投/pending 对账）、定时调度（重试退避/静默时段）、代理池健康评分、UA 轮换反爬、webhook 终态回调 | `backend/app/api/v1/spiders/` + `scrapy/` |
| **AI 采集规划** | LLM 规划 selectors → 试采 → 质量评判 → 自动修复迭代 → 注册爬虫；token 预算熔断 + 用量落库 | `backend/app/api/v1/ai.py` + `backend/services/ai_planner/` |
| **LLM 供应商管理** | 多供应商注册表、单激活热切换、Fernet 密钥加密、连通测试——**仅 OpenAI 兼容协议、单模型**（方案 B 要打破的限制） | `backend/app/api/v1/llm_providers.py` |
| **new-api 中转站管控** | 渠道额度调度（CRUD→Redis hash→调度器生效）、渠道真伪探针（10 维行为指纹）、只读总览；渠道数据不落库 | `backend/app/api/v1/newapi.py` + `backend/services/newapi_*.py` |
| **平台基座** | JWT 认证 + 三角色 RBAC、审计日志、统一异常信封、Dynaconf 多层配置、check-arch 12 红线门禁、admin（13 页面）/official（单页静态官网）双前端、6 个 lifespan 常驻组件 | `backend/app/` + `platform_core/` + `frontend/` |
| **skills-library** | 本地子系统（已入 git）：meta.yaml 治理元数据、4 维评分 rubric、本地 8765 后台（无鉴权）、claude-code(symlink)/codex(拼接) 两适配器、1 个占位示例 skill | `skills-library/` |

审计修复进度：P0 ×4 全修 ✅；P1 ×13 已修 12（唯 P1-12 LLM 故障转移 = B-M4）；4.2 中转站调度接线 ✅（10.2-F 已核对：未拆分，S1 前小任务见 §7.3）；易用性 U1 ✅；SaaS 多租户零落地。**工程基座 E0 六项已全部落地（2026-08-31）。**全部实施完毕（2026-09-01）**：E0+A(P1-P5)+B(M1-M4)+SaaS S1-S5 工单 01-43 全 resolved（第二批 P5+S1-S5 = 工单 28-43），后端自动化测试 703 passed、双前端 test+build 绿、check-arch 13 红线全绿。**

**平台级基础设施定位（不租户化）**：new-api 中转站渠道、skills 域新表、system_configs、channel_events/channel_probe_results、operation_logs（跨租户平台审计）。

---

## 3. 架构问题与修正清单（v2 深度整理产出）

> 每条问题标注**修正落点**；v1 方案的设计缺陷在此修正后直接以修正版进入 §5-§7，不再重复。

### 3.1 横切问题（v1 三份方案均未覆盖）

| # | 问题 | 证据 | 修正落点 |
|---|---|---|---|
| T1 | **测试基座撑不起任何方案的验收**：conftest 仅 2 个 fixture，无 DB fixture/工厂/事务隔离，546 测试全 mock。S1 越权套件、S1 迁移回滚、A 评分流水线、B 适配器回归都需要真实 SQLAlchemy 事件链 | `backend/tests/conftest.py:40-43` | E0.1 |
| T2 | **Alembic 链不完整**：`spider_tasks`、`system_configs` 两表从未有迁移，靠 `create_all` bootstrap + `stamp head` 兜底——审计 10.2-G 的"downgrade 可用"在此基线上不成立 | `scripts/init_db_sync.py:41`、versions/ 17 文件无此二表 | E0.2 |
| T3 | **前端零测试且模板已腐坏**：双前端 `App.test.tsx` 断言不存在的 "learn react" 链接（必失败），CI 只 build 不 test | `frontend/{admin,official}/src/App.test.tsx`、ci.yml:81-91 | E0.3 |
| T4 | **租户写侧防线漏点**：`before_flush` 只拦 `session.new`（ORM insert）；仓内 7 处 Service 裸 `session.execute`（如 `ai_planner/state.py:113-125` Core `update(AiPlan)` 批量语句）不走 flush；裸 `text()` SQL 连 `do_orm_execute` 也绕开 | 见 E0.6 清查清单 | E0.6 清查 + S1 消化 |
| T5 | **口径漂移**：check-arch 实为 12 红线，CI/pre-commit hook 名写 "10 rules"；pre-commit INSTALL_PYTHON 指向旧路径 `/Users/xuyun/Projects/...`（仓库已迁移，本地门禁可能静默失效） | ci.yml:60、.pre-commit-config.yaml | E0.4 / E0.5 |
| T6 | **审计 10.2-F 未闭环**（newapi 渠道 `enabled` 与额度语义是否拆分，停在"⚠️ 验收时核对"） | 审计 §10.2-F | E0.6 |

### 3.2 方案 A（技能中心）v1 稿缺陷 → 修正

| # | 缺陷 | 修正 |
|---|---|---|
| A-1 | P1 切片过大（表+迁移+扫描+页面+矫正+写回+退役+文档 8 件事一阶段） | 重切 **P1a（数据+扫描+API）/ P1b（矫正写回）/ P1c（admin 页+退役+文档）** 三个 vertical slice |
| A-2 | 前提缺失：skills-library 未入 git，D1"写回进 git 可审计"地基不存在 | 已由 commit `cf2ab0a` 首次入库解决；P1b 验收含 `git diff` 冒烟 |
| A-3 | **评分预算挤占**：评分复用 `llm_chat` 则挤占 AI 规划的 `LLM.MAX_TOKENS_BUDGET` 熔断额度，互相熔断 | 计量 dim 独立为 `skill_scoring`；预算独立键 `SKILLS.SCORING.MAX_TOKENS_BUDGET`；`llm_chat` 加可选 `usage_dim`/`budget_override` 参数（openai 路径行为不变）——P2 设计约束 |
| A-4 | status 枚举断裂：v1 六态 vs 现状三态（active/experimental/deprecated），迁移映射缺失 | 映射定案：`active→testing`、`experimental→experimental`、`deprecated→deprecated`；blacklist 仅用于市场采集的拉黑记录（P5 前不出现） |
| A-5 | 路由遮蔽：`GET /skills/compare`、`/skills/categories`、`/skills/jobs` 会被 `/skills/{name}` 吞掉 | 路由注册顺序约束写入 P1a 设计 + 专项测试用例 |
| A-6 | URL 导入安全空白：zip-slip / 大小上限 / 恶意 SKILL.md 的 prompt 注入与分发污染 | P3 必做验收：成员路径规范化拒绝绝对路径与 `..`、zip ≤20MB、单文件 ≤2MB、总文件 ≤100、深度 ≤3；评分 prompt 将 SKILL.md 声明为不可信数据（P2） |
| A-7 | 官网 SKILL.md 渲染未提 sanitize | P4 必做验收：XSS payload 转义测试 |
| A-8 | check-update 移植 urllib 违背 `httpx + trust_env=False` 约定 | P3 实现约束：统一 httpx |
| A-9 | `ai_suggested_score` 在 8765 现状无写入路径（纯人工占位） | P2 落地真实 AI 写入（这正是本方案的价值点），rubric.md"AI 仅建议"原则不变 |

### 3.3 方案 B（LLM 多平台）v1 稿缺陷 → 修正

| # | 缺陷 | 修正 |
|---|---|---|
| B-1 | M1 验收"curl 三平台真实 key"不可回归 | 验收分层（D11）：自动化层用 httpx MockTransport 三协议全矩阵；真实 key 只进冒烟清单 |
| B-2 | 用量表 4 列化与 C-S1 双重认领 | 归 S1（D9），B-M4 删除该范围 |
| B-3 | PLATFORM_PRESETS 含 `http://localhost:11434/v1`，check-arch R1 正则未预检 | M1 验收加"check-arch 退出码 0"预检项；若 R1 误报则调整其正则豁免本地回环预设 |

### 3.4 方案 C（SaaS）v1 稿缺陷 → 修正

| # | 缺陷 | 修正 |
|---|---|---|
| C-1 | "9 张业务表"黑盒口径（全库 14 张表，未列清单） | §7-S1 逐表清单：**租户化 9 张** = spider_tasks / spider_results / spider_schedules / spider_definitions / spider_task_templates / ai_plans / llm_providers / alert_rules / llm_token_usage；**users 特殊**（+tenant_id/tenant_role/is_platform_admin，username 唯一键改 4.2-B 口径）；**豁免** = tenants / system_configs / channel_events / channel_probe_results / operation_logs / skills 域三表 |
| C-2 | "admin 页面无需大改"过于乐观 | S1/S2 明确页面分化：Users 页归平台超管；租户 admin 获独立成员管理页；`menuConfig`/`usePermission` 按 `is_platform_admin` 分叉 |
| C-3 | JWT claims 原则缺失：现状 claims 中 `role` 根本不被消费（`deps.py:61-67` 只用 user_id 从 DB 重算）——好设计但未成文 | S1 设计原则定案：**claims 只承身份（user_id/tenant_id），权限一律登录时 DB 快照重算**；与 S2"被禁用 token 短窗失效"验收自洽 |
| C-4 | 10.2-F 停在"待核对" | 收编 E0.6 |

### 3.5 方案间冲突 → 修正

| 冲突 | 修正 |
|---|---|
| 用量表 4 列化：B-M4 与 S1 重复认领 | D9：归 S1 |
| A-P2 依赖 B-M2/M3，v1 路线图却称"A/B 互不依赖" | D10：A 独立起步 + 能力开关降级；路线图（§8）标注真实依赖边 |

---

## 4. Phase E0：工程基座（新增，与 A-P1a / B-M1 并行起步）

> 六个独立小项，互不阻塞，可穿插完成。**E0.1 是 A-P2 与 S1 的硬前置；E0.2 是 S1 的硬前置。**

### E0.1 测试基座（D7 策略）

**内容**
- `backend/tests/conftest.py` v2 新增 fixture：
  - `db_engine` / `db_session`：默认 SQLite in-memory（`create_all` 建表 + 每测试回滚/重建隔离）；`MYSQL_FIDELITY=1` 时切真实 MySQL（读 `config/local/mysql.yml` 同款连接串约定，测试库独立 schema，每会话建删）；
  - 轻量模型工厂：自写 builder 函数（不引入 factory_boy 等新依赖），覆盖 user / spider_task / llm_provider / spider_definition；
  - `FakeRedis` 沿用 `stubs.py` 扩展（已有 strings+hashes+Lua 语义）。
- API 层测试经 `dependency_overrides` 注入 `db_session`；Service 层测试直接吃 fixture。
- CI：`python-lint-test` job 增加一个 `MYSQL_FIDELITY=1` 的迁移/方言测试步骤（GitHub Actions MySQL service container）。

**Seam**：repository 公共方法、service 公共方法、API 端点（TestClient）。

**自动化验收**
- `test_conftest_isolation`：两个测试写入同名行互不可见；
- `test_factory_builders`：工厂产出的行可 flush 且满足约束；
- `MYSQL_FIDELITY=1` 下 `test_alembic_upgrade_downgrade`（依赖 E0.2，见下）；
- 存量 546 测试零回归（`uv run pytest -x -q backend/tests` 退出码 0，本地无 Docker）。

### E0.2 Alembic 基线修复

**内容**：补 `spider_tasks`、`system_configs` 基线迁移（对齐 `create_all` 现状）；`bootstrap-db.sh` 退化为兼容路径（新环境直接 `alembic upgrade head` 可成功）。

**自动化验收**：`MYSQL_FIDELITY=1` 下——空库 `upgrade head` 成功且表集合 == `create_all` 表集合（自动对比）；`downgrade base` 干净（无残留表）。

### E0.3 前端腐坏测试清理

**内容**：删除双前端 "learn react" 模板测试；admin 补最小 smoke（Login 页渲染 + App 路由壳）；CI `frontend-build` job 增加 `npm test -- --watchAll=false`（两前端）。

**自动化验收**：本地与 CI `npm test -- --watchAll=false` 退出码 0。

### E0.4 门禁口径统一

**内容**：ci.yml 与 .pre-commit-config.yaml 中 "10 rules/10 条红线" 措辞统一为 12 红线 + 3 边界。

**自动化验收**：`grep -rn "10 rules\|10 条红线" .github .pre-commit-config.yaml scripts/` 零命中。

### E0.5 pre-commit 路径修复

**内容**：`uv run pre-commit install --hook-type pre-commit --hook-type pre-push` 重装（INSTALL_PYTHON 指向现路径）。

**冒烟验收**：`uv run pre-commit run --all-files` 退出码 0；故意提交一个 ruff 违规文件被拦截。

### E0.6 裸语句清查 + 10.2-F 闭环

**内容**
- 清查 7 处 Service 裸 `session.execute`（`config_service.py:17-35`、`alert_service.py:122-147`、`ai_planner/state.py:69-125` 等），产出三分类清单：①Core ORM 语句（`do_orm_execute` 可拦，S1 登记）②`text()` 裸 SQL（改走 ORM 或列平台级豁免）③外部库语句（channel_scheduler 对 new-api 库，豁免）。清单写进本文件 §7-S1 附录；
- 核对审计 10.2-F：`newapi:channel:cfg` 的字段语义是否已拆分"渠道启用"与"额度受管"两个维度，未拆分则列 S1 前小任务。

**自动化验收**：清单落档（本文件修订）；10.2-F 结论回写审计文档一行状态。

---

## 5. 方案 A：技能管理中心（skills-library 主平台化）

> 目标：`skills-library/` 从独立本地子系统升级为平台级技能管理中心——主后端统一治理、admin 全功能管理、官网技能广场；技能建一次、全 agent 共用；AI 自动打分 + 人工矫正、同类区分、分类调用。
> 架构与数据流沿用 v1 设计（内容真相源=文件、治理真相源=DB、meta.yaml 写回快照），此处只写阶段切片与验收。

### 5.1 数据模型（P1a 落地）

三表 + Alembic 迁移（进迁移链，不 create_all）：

```sql
CREATE TABLE skills (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(128) NOT NULL UNIQUE,          -- 目录名，全局唯一（唯一取值源=目录名）
  title VARCHAR(256) DEFAULT '',              -- SKILL.md frontmatter 显示名
  description TEXT,
  category VARCHAR(64) NOT NULL DEFAULT 'uncategorized',
  industries JSON,
  status VARCHAR(16) NOT NULL DEFAULT 'experimental',
    -- experimental/testing/stable/recommended/deprecated/blacklist（存量映射见 3.2-A-4）
  source_type VARCHAR(16) NOT NULL DEFAULT 'self_built',   -- self_built/network_imported/marketplace_crawled
  source_url VARCHAR(512) DEFAULT '', source_author VARCHAR(128) DEFAULT '',
  imported_at DATETIME NULL, content_hash CHAR(64) DEFAULT '',
  score DECIMAL(3,1) NULL,                    -- 人工终评（NULL=未复核，AI 永不写）
  ai_suggested_score DECIMAL(3,1) NULL,
  rubric_human JSON, rubric_ai JSON,          -- {completeness, doc_quality, maintenance, real_world_effect}
  tier VARCHAR(2) NULL,                       -- 派生：S≥8.5 / A≥7.0 / B≥5.0 / C<5.0（人工分优先，缺省 AI 分）
  reviewed_by VARCHAR(64) NULL, reviewed_at DATETIME NULL, review_notes TEXT,
  similar_to JSON,
  file_path VARCHAR(512) NOT NULL,
  sync_state VARCHAR(16) NOT NULL DEFAULT 'ok',   -- ok/hash_changed/missing/parse_error
  tenant_id INT NULL,                         -- D3：恒 NULL，进 S1 豁免白名单
  raw_meta JSON,
  created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,
  KEY idx_skills_category (category), KEY idx_skills_status (status), KEY idx_skills_score (score)
);
CREATE TABLE skill_reviews (                  -- AI 与人工评审全留痕
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  skill_id INT NOT NULL, reviewer_type VARCHAR(8) NOT NULL,  -- ai/human
  reviewer VARCHAR(64) NOT NULL, score DECIMAL(3,1), rubric JSON, notes TEXT,
  content_hash CHAR(64), prompt_version VARCHAR(8),
  created_at DATETIME NOT NULL, KEY idx_skill_reviews_skill (skill_id)
);
CREATE TABLE skill_jobs (                     -- 扫描/评分批/导入 运行记录（轻量，不做通用 job 框架）
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  job_type VARCHAR(16) NOT NULL, status VARCHAR(16) NOT NULL,
  total INT DEFAULT 0, succeeded INT DEFAULT 0, failed INT DEFAULT 0,
  detail JSON, started_at DATETIME, finished_at DATETIME
);
```

- name 取值源定案：**目录名唯一**；frontmatter/meta 的 name 仅作 title 候选（消除现状三源歧义，`build_index.py:95` 的优先级链不再沿用）；
- meta.yaml ↔ DB 字段映射与写回规则沿用 v1（DB 权威 → 原子写回 tmp+rename → CHANGELOG 追加；写回失败不回滚 DB，记 skill_jobs 告警，提供手动补导出端点）；
- Redis 键进 `platform_core/queues.py`：`skill:score_queue`（list）、`skill:scorer:lock`、`skill:scan:lock`；
- 新配置 `config/default/skills.yml`（全非敏感，R1 合规）：`LIBRARY_ROOT / SCAN_ON_STARTUP / SCORING{ENABLED,MODEL,MAX_CONCURRENCY,PROMPT_VERSION,MAX_TOKENS_BUDGET} / PUBLIC_API{ENABLED,RATE_LIMIT_PER_MIN} / ADAPTER_SYNC.ENABLED`。

### 5.2 API（管理端挂 `/api/v1/skills`，公开端挂 `/api/v1/public/skills`）

**路由注册顺序约束（A-5）**：静态段 `scan / compare / categories / jobs / manifests / sync-adapters / import-url` 必须先于 `/{name}` 注册；专项用例锁死。

| 端点 | 权限 | 说明 |
|---|---|---|
| `GET /skills` | viewer | 筛选 q/category/industries/status/tier/source_type + sort + `PaginatedResponse` |
| `GET /skills/{name}` | viewer | 治理字段 + SKILL.md 正文只读 + meta 原文 + 最近 reviews + 启用矩阵 |
| `POST /skills/scan` | admin | 全量/增量扫描：新入库 / hash 变化置 hash_changed 并入评分队列 / 丢失置 missing |
| `POST /skills/import-url` | admin | URL 导入（P3） |
| `PUT /skills/{name}/meta` | operator | 人工矫正（P1b） |
| `POST /skills/{name}/rescore` | operator | 手动触发 AI 重评（P2） |
| `GET /skills/{name}/reviews` | viewer | 评分历史 |
| `GET /skills/compare?names=a,b,c` | viewer | N 列并排四维（AI/人工两套） |
| `GET /skills/{name}/check-update` | operator | 只读拉 source.url 哈希比对，不自动覆盖（P3，httpx 实现） |
| `GET/PUT /skills/manifests` | admin | 启用矩阵直读直写 yaml（无 DB 镜像） |
| `POST /skills/sync-adapters` | admin | subprocess 执行 sync.sh（受 ADAPTER_SYNC.ENABLED 约束） |
| `GET/POST/DELETE /skills/categories` | admin | 受控枚举 |
| `GET /skills/jobs` | admin | 任务记录 |
| `GET /public/skills`、`GET /public/skills/{name}` | 无鉴权 | 仅 status∈{stable,recommended}；字段白名单（name/title/description/category/industries/tier/score/status/source_url/source_author/updated_at + SKILL.md 正文）；按 IP 限流（Redis 原子计数）；不复用 external_api Key 体系 |

Service 划分：`skill_service`（CRUD/扫描/写回/tier 派生）、`skill_scoring_service`（评分 worker，lifespan 第 7 个常驻组件）、`skill_import_service`（URL 导入）、`skill_public_service`（白名单投影+限流）。Repository：`skill_repository` + `skill_review_repository`（继承 BaseRepository）。全部写操作走 `record_audit`。

### 5.3 阶段切片与验收

#### P1a 数据底座与扫描入库（后端，可与 E0/B-M1 并行）

**Seam**：`/api/v1/skills` 端点（TestClient + SQLite db_session）；扫描服务吃 `tmp_path` 造的技能目录。

**自动化用例**
- `test_scan_imports_new_skill_directory`（frontmatter 解析 → 入库，name=目录名）
- `test_scan_detects_content_hash_change`（改 SKILL.md → sync_state=hash_changed + 入评分队列标记）
- `test_scan_marks_missing_directory`、`test_scan_marks_parse_error`
- `test_list_skills_filters_and_pagination`、`test_get_skill_detail_404`
- `test_static_routes_not_shadowed_by_name`（compare/categories/jobs 不被 /{name} 吞）
- `test_migration_upgradable_from_head_minus_one`（MYSQL_FIDELITY）

**冒烟**：curl `POST /skills/scan` 对真实 skills-library 跑一次，返回 jobs 记录。

#### P1b 人工矫正与 meta 写回

**Seam**：`skill_service` 公共方法（SQLite + tmp_path 技能目录）。

**自动化用例**
- `test_correct_meta_writes_db_then_meta_yaml_and_changelog`（同事务语义：DB 落库 → 文件写回 → CHANGELOG 追加）
- `test_meta_writeback_failure_keeps_db_and_records_job`（文件只读 → DB 不回滚、skill_jobs 告警）
- `test_tier_derivation_boundaries`（8.5/7.0/5.0 边界；人工分优先于 AI 分；未评=NULL）
- `test_human_review_recorded_in_skill_reviews`（reviewer=当前用户）
- `test_ai_never_writes_authoritative_score`（评分服务落库后 score/rubric_human 不变）

**冒烟**：admin 外观下一次矫正 → `git diff skills-library/skills/*/meta.yaml` 可见写回、CHANGELOG 增行。

#### P1c admin 技能中心页 + 8765 退役 + 文档修订

**内容**：`pages/Skills.tsx`（技能库列表 + 详情 Drawer + 矫正 Modal，范式对齐 `NewApiOps.tsx`）+ `services/skills.ts` + 4 处注册（App.tsx 路由 / menuConfig / usePermission / AdminLayout PAGE_TITLES）；skills-library README 增"主平台集成"章节、8765 标注 deprecated；AGENTS.md Skill 路由表定位改"治理并入主 API v1/skills"。

**自动化验收**：`npm run build` + `npm test -- --watchAll=false` 退出码 0。**冒烟**：浏览器完成一次列表→详情→矫正闭环。

#### P2 AI 自动打分 + 待复核工作台（前置：E0.1）

**设计约束（修正项）**
- 评分 dim=`skill_scoring`、独立预算 `SKILLS.SCORING.MAX_TOKENS_BUDGET`（A-3：不挤占 AI 规划熔断额度）；`llm_chat` 加可选 `usage_dim`/`budget_override`，openai 路径行为不变；
- Prompt：SKILL.md 全文 + rubric.md 四维标准；**SKILL.md 声明为不可信数据**（A-6：指令边界——内容仅作评估素材，输出仅限结构化 JSON）；输出过 Pydantic 模型校验（维度 1-10、rationale 必填），非法重试 1 次后记失败；
- 模型：默认激活供应商默认模型（零依赖 B）；`SCORING.MODEL` 非空时若 B-M2 未就绪 → 启动告警 + 回退默认（D10 能力开关）；
- 触发：导入成功 / hash 变化 / 手动 rescore；定期重评不做（P5 再议）；
- Worker：Redis 队列 `skill:score_queue` + 分布式锁 + lifespan 常驻（`asyncio.create_task` 范式）；前端"待复核"Tab = `ai_suggested_score IS NOT NULL AND score IS NULL`。

**Seam**：`skill_scoring_service` 循环（FakeRedis + mock llm_chat）；评分结果 Pydantic 模型。

**自动化用例**
- `test_score_queue_consumed_and_review_recorded`（reviewer_type=ai、content_hash、prompt_version）
- `test_invalid_llm_json_retries_once_then_fails`
- `test_scoring_usage_recorded_under_skill_scoring_dim`
- `test_scoring_budget_independent_from_planner_budget`（评分超独立预算不影响规划熔断状态）
- `test_ai_score_does_not_overwrite_human`

**冒烟**：导入 1 个真实 skill → 自动出四维分与理由 → 用量出现在 llm_token_usage（dim=skill_scoring）→ 人工矫正落库且 meta.yaml 同步。

#### P3 URL 导入 + 适配器矩阵（前置：P2）

**安全必做（A-6，验收项）**：zip 成员路径规范化（拒绝绝对路径与 `..` 即 zip-slip）、zip ≤20MB、单文件 ≤2MB、总文件 ≤100、深度 ≤3；GitHub 子目录走 API 列目录递归（跳过 .git）；name 冲突 422 + 同类目相似名候选提示。check-update 统一 httpx（A-8，`trust_env=False`）。

**Seam**：`skill_import_service`（httpx MockTransport）。

**自动化用例**
- `test_zip_slip_rejected`、`test_zip_size_limit_rejected`、`test_file_count_limit_rejected`
- `test_github_subdir_import_parses_frontmatter`
- `test_name_conflict_returns_422`
- `test_manifests_roundtrip_preserves_format`（`- name` 行格式与注释头）
- `test_check_update_uses_httpx_trust_env_false`

**冒烟**：从 GitHub 导入一个外部 skill 全流程（拉取→落盘→入库→自动评分→待复核）；矩阵勾选 → sync.sh 执行 → `~/.claude/skills/` 出现新 symlink。

#### P4 官网技能广场（前置：P1c）

**三道闸 + sanitize**：字段白名单 / 仅发布态（stable+recommended，D12；不设独立 published 开关——定案）/ 按 IP 限流；SKILL.md 渲染前过 sanitize。

**Seam**：公开端点（TestClient + FakeRedis）。

**自动化用例**
- `test_public_list_only_published_status`
- `test_public_fields_whitelist_enforced`（schema 层断言无 review_notes/sync_state/file_path/raw_meta）
- `test_public_rate_limit_429`
- `test_skill_md_rendering_escapes_xss_payload`

**前端**：`SkillsSection`（首页，精选 tier=S/A）+ `/skills` 独立页（分类/搜索/详情）+ `services/skills.ts`（复用 official 既有 axios 实例）+ 补 ConfigProvider zhCN。**验收**：build + test 绿。**冒烟**：未登录浏览器浏览发布态技能；未发布技能 404。

#### P5 二期（维持 v1：市场采集爬虫 + 候选审核流 + similar AI 辅助候选 + maintenance 定期重评）

`skill_harvester` spider（TaskAwareRedisSpider 基类）→ `spider:item_queue` 回流 → admin 候选 Tab → 一键转 import-url 正式管线；blacklist 状态仅在此期出现。验收：采集→候选→审核→入库自动化跑通。

---

## 6. 方案 B：LLM 多平台模型管理（cc-switch 域升级）

> 目标：打破"仅 OpenAI 兼容"限制——主流平台自由添加、按平台自动拉取模型列表、勾选添加多模型、填完 Key 即测连通；为故障转移（M4）铺底座。协议映射、预设平台注册表、前端向导流设计沿用 v1 §2-§5，此处记录要点与修正。

### 6.1 要点（沿用 v1）

- **协议适配层** `backend/services/llm_protocol/`：`LlmProtocolAdapter` Protocol（list_models / build_chat / parse_chat / is_chat_model），三协议 = openai_compatible / anthropic / google_gemini；全部 `trust_env=False`；错误只回状态码+reason（脱敏沿用）；base_url 校验复用 `_validate_base_url` + `LLM.PROVIDER_BLOCK_PRIVATE_URL`；
- **预设平台** `config/default/llm.yml` 增 `PLATFORM_PRESETS`（12 预设 + 自定义入口，公开 URL 非敏感；含 Ollama/vLLM 本地预设——B-3 的 R1 预检在 M1 验收）；`is_chat_model` 启发式过滤（embedding/tts/whisper/rerank/image/audio/moderation/guard），前端可关；
- **数据模型**：新子表 `llm_provider_models`（model_id/alias/model_tier(strong|basic)/priority/is_default/enabled/health_status/last_checked_at/last_latency_ms；`uq(provider_id, model_id)`；FK 级联删除）；父表 `model` 列保留为默认模型冗余快照，子表 is_default 变更同事务刷新父行；`LlmRuntimeConfig` 增可选 `protocol` 字段（M3 才消费）；消费路径第一阶段零改动；
- **API**：`POST /llm/providers/models/probe`（保存前拉模型，key 不落库不写日志不回显）、`POST /llm/providers/models/probe-test`（保存前 1-token 连通测试）、`POST /llm/providers/{id}/models/fetch`（new/existing/vanished 三分类 diff）、`GET/PUT /llm/providers/{id}/models`（全量替换，is_default 至多一行）、`POST /llm/providers/{id}/models/{model_id}/test`（1-token，结果落 health_status/last_latency_ms/last_checked_at）、`GET /llm/providers/platform-presets`；现有 `{id}/test` 保留等价"测默认模型"；全部 require_admin + 审计；
- **前端**：新建表单向导流（选平台→填 Key→拉模型（mode="tags" 支持手填兜底）→勾选→定默认→测连通→保存）；模型管理 Drawer（diff 三区/tier/priority/enabled/健康 Tag/行内测试）；列表"模型"列多 Tag（默认金色 +N）。

### 6.2 阶段与验收

#### M1 协议适配层 + 探测端点（可与 E0/A-P1a 并行）

**Seam**：三适配器公共方法（httpx MockTransport 全矩阵）；probe/probe-test/platform-presets 端点（TestClient + mock 适配器外呼）。

**自动化用例**
- `test_openai_list_models_parses` / `test_anthropic_list_models_headers_and_prefix` / `test_gemini_filters_generate_content_and_strips_prefix`
- `test_chat_build_url_and_payload_per_protocol`（三协议 × build_chat/parse_chat）
- `test_error_response_masks_body`（只回状态码+reason）
- `test_probe_does_not_persist_or_log_api_key`（无 DB 新行 + 日志捕获断言）
- `test_provider_type_schema_accepts_three_protocols`（Literal 扩展后旧值回归）
- `test_check_arch_exit_zero_with_presets`（B-3 预检）

**冒烟**：真实 key 对 OpenAI/Anthropic/Gemini 各拉一次模型列表 + 一次 probe-test（不进 CI）。

#### M2 多模型数据模型 + 前端（前置：M1）

**自动化用例**
- `test_put_models_full_replace_semantics`、`test_multiple_default_returns_422`
- `test_default_change_syncs_parent_model_column`（同事务）
- `test_fetch_diff_three_way_classification`
- `test_model_test_writes_health_status`（200→healthy / 401→down / 超时→degraded）
- `test_delete_provider_cascades_models`

**冒烟**：从 Anthropic 平台走完"选平台→填 key→拉模型→勾选→测连通→保存"全流程；默认模型变更后 `GET /llm/providers/active` 的 model 同步。

#### M3 消费面协议分发（前置：M2）

**自动化用例**
- `test_llm_client_routes_by_protocol`（anthropic/gemini 经适配器；openai_compatible 路径字节级不变）
- `test_usage_normalized_for_anthropic_and_gemini`（usage.input_tokens/output_tokens → prompt/completion 入计量）
- **回归**：`test_ai_planner.py` 零改动全绿（v1 目标保留）。

**冒烟**：激活 Anthropic 模型 → AI 采集规划端到端跑一次；技能评分（若 P2 已交付）多协议可用（D10 开关生效）。

#### M4 故障转移 + 周期巡检（可与 S1 并行；**不含用量表迁移**，D9）

**内容**：priority 候选链自动切换、周期健康巡检后台组件（默认 30min 可配置，定案）、跨级降质（strong→basic）告警、熔断 fail-closed（Redis 不可达即拒绝 LLM 调用，与登录限流 fail-open 方向相反——docstring 并列写明）。

**验收**：审计 4.1.6 验收标准 + 10.2-D/E 修订项；自动化用例覆盖候选链切换、降质告警、fail-closed 行为。

---

## 7. 方案 C：SaaS 多租户演进

> 目标：单团队工具 → 面向企业的多租户 SaaS。技术架构（共享库+tenant_id 行级隔离、双侧收口、约束清查、迁移工程）沿用审计 §8/§10 修订结论与 v1 §3 的 7 项决策，此处记录修正后的决策与逐表清单。

### 7.1 修正后决策（在 v1 7 项之上增补）

1. **逐表清单（C-1）**：租户化 9 张 = spider_tasks / spider_results / spider_schedules / spider_definitions / spider_task_templates / ai_plans / llm_providers / alert_rules / llm_token_usage；users 特殊（+tenant_id/tenant_role/is_platform_admin，唯一键按 10.2-B 改造）；豁免白名单 = tenants / system_configs / channel_events / channel_probe_results / operation_logs / skills / skill_reviews / skill_jobs；
2. **claims 原则（C-3）**：JWT claims 只承身份（user_id/tenant_id），权限（role/tenant_role/is_platform_admin）一律登录时 DB 快照重算（延续现状 `deps.py` 模式并成文）；
3. **裸语句消化（T4）**：S1 动工前按 E0.6 清单——`text()` 裸 SQL 改 ORM 或列豁免；Core ORM 语句登记由 `do_orm_execute` 兜底；`consumer.py` 的 `add_all` 写入路径加 tenant_id 非空断言（真实 flush 验证）；
4. **用量表 4 列（D9）**：`llm_token_usage` 唯一键一次改 4 列 `(tenant_id, provider_name, model, stat_date)` + `idx_tenant_date`，默认租户回填同批完成；Redis 键 `llm:usage:{tenant}:{provider}:{model}:{date}`；
5. **页面分化（C-2）**：Users 页归平台超管；租户 admin 用 S2 成员管理页；`menuConfig`/`usePermission` 按 `is_platform_admin` 分叉（S1 预埋、S2 生效）；
6. 其余沿用 v1：双侧收口（TenantMixin+before_flush 写侧 / do_orm_execute 读侧）、4 表唯一约束清查、`activate_exclusive` 收窄租户内、降级语义两方向（限流 fail-open / 熔断 fail-closed）、迁移工程（spider_results DDL 实测定排期、主键区间分批回填、downgrade 双向测试）、新增 R13 红线（业务查询必须经租户过滤收口）。

### 7.2 阶段与验收（依赖见 §8）

| 阶段 | 内容 | 前置 | 验收 |
|---|---|---|---|
| **S1 租户基座** | tenants 表 + users 租户化 + 9 表 tenant_id 回填 + 双侧隔离 + 约束清查 + 用量表 4 列 + JWT/两级 RBAC + 租户上下文中间件 + R13 + 裸语句消化 | **E0.1 + E0.2** + 批次1 ✅ + 路由守卫 ✅ + 大表 DDL 实测 | **越权测试套件全绿**（A 租户 token 访问 B 租户资源全 403/404，覆盖全部 9 资源类）；Core update 专项（state.py 批量语句在租户上下文外被注入条件或拒绝）；迁移 upgrade/downgrade 双向（MYSQL_FIDELITY）；升级零感知（默认租户承接存量） |
| **S2 子账号管理** | 成员 CRUD / 角色分配 / 禁用 / 重置密码 + 租户成员管理页 + 页面分叉生效 | S1 | 租户 admin 自助管理；被禁用 token 短窗内失效（配合 claims 原则） |
| **S3 配额与用量** | 任务并发 / 结果存储 / LLM token 三类配额 + 用量看板（租户/成员双维度）+ 超限业务码 | S1 + B(M1-M3) | 超配额被拒且文案可行动；看板双维度 |
| **S4 能力租户化** | llm_providers 租户自带 Key + 平台公共供应商兜底（token 配额约束）+ 套餐→渠道组分配（远期）；**评估点：租户私有技能** | S3 + B(M4) | 租户各自配 Key 各自计量；平台成本可控 |
| **S5 商业化闭环** | 官网企业注册/定价 + 自助开通 + 到期停用降级 + 平台运营台 | S1-S4 | 企业从官网浏览到跑通第一个采集任务全程无人工 |

### 7.3 S1 前置附录：裸语句三分类清单（E0.6 产出，2026-08-31）

全仓 Service 层 `session.execute` 清查结果（repository 层的 ORM execute 属正常范式，不计入）：

| 位置 | 语句形态 | 分类 | S1 处置 |
|---|---|---|---|
| `backend/services/alert_service.py:127,147` | `select(SpiderTask)` Core ORM | A：`do_orm_execute` 可拦 | 直接纳入租户过滤，无需改造 |
| `backend/services/config_service.py:17,26` | `select(SystemConfig)` Core ORM | A | 纳入；system_configs 为平台级豁免表，拦截后白名单放行 |
| `backend/services/ai_planner/state.py:69` | `select(SpiderTask)` 标量列（独立 session） | A | 纳入；租户上下文缺失时的拒绝策略随 S1 全局规则 |
| `backend/services/ai_planner/state.py:120` | `update(AiPlan)` Core ORM（`synchronize_session=False`，启动对账） | A | `do_orm_execute` 对 ORM-enabled update 注入 tenant 条件；**S1 专项测试用例** |
| `backend/services/channel_scheduler_service.py:427,437` | `text(sql)` 对 new-api **外部库**（独立 engine） | C：外部库豁免 | 登记豁免 + 代码注释明示 |
| `backend/app/api/v1/health.py:34` | `text("SELECT 1")` 主库探测 | C：探测语句（无业务表） | 豁免（无租户语义） |

**结论**：主库上不存在 text() 裸 SQL 业务语句——S1 无"B 类（需改 ORM）"改造项；6 处 Core ORM 语句（alert ×2 / config ×2 / state ×2）全部可由 `do_orm_execute` 收口。`consumer.py` 的 `add_all` 写入路径（before_flush 主防线的最大风险点）不属裸语句问题，已由 §7.1-3 覆盖。

**10.2-F 核对结论（未拆分，列 S1 前置小任务）**：现行 `ChannelConfigInfo.limit_quota`（`ge=0`，0=显式关闭该渠道调度）正是审计 10.2-F 警告的语义混载——全局 `DEFAULT_WINDOW_QUOTA: 0` 意为"不启用全局默认"，两个 0 含义冲突（读取侧 `channel_scheduler_service.py:447-473` 以 if/elif 区分，代码自洽但对外契约歧义）。S1 前小任务：schema 增 `enabled: bool`（默认 true）、`limit_quota` 收紧 `ge=1`、读取侧兼容旧 hash（无 enabled 键视为 true）、前端配置弹窗加开关，旧 `limit_quota=0` 语义保留一个版本的兼容读取并在 channel_events 记 deprecation。


### 7.4 S1-6 DDL 实测记录（2026-09-01，保真通道）

压测表 drill_results（6000 行 × 200B payload，MySQL 8 本地）：

| 操作 | 耗时 |
|---|---|
| ADD COLUMN tenant_id INT NULL | 0.015s |
| CREATE INDEX (tenant_id) | 0.013s |
| 分批回填（LIMIT 5000/批 × 2 批） | 0.083s |

分批回填模板验证可用（NULL 清零断言）。结论：**当前数据量级下加列/索引/回填均为亚秒级**——
spider_results 大表 DDL 无需停机窗口（10.2-G 的排期门槛已解除）；
数据量增长至百万行级时再复跑 `test_saas_ddl_drill`（耗时随行数线性）。

---

## 8. 合并实施路线图（依赖修正版）

```
并行起步（三路互不依赖）
├── E0 工程基座（E0.1-E0.6 六个独立小项穿插）
├── A-P1a 技能数据底座 ──► A-P1b ──► A-P1c ──► A-P4 官网
└── B-M1 协议适配 ──► B-M2 多模型 ──► B-M3 消费面分发
        │                   │             │
        │                   └── A-P2 能力开关生效（SCORING.MODEL 指定模型）
        │                                 └── A-P2 多协议评分生效
        │
        │  E0.1 就绪 ──────────► A-P2 评分流水线（默认模型，零依赖 B）
        │
        ▼
S1 租户基座（前置：E0.1 + E0.2 + 大表 DDL 实测；用量表 4 列在此做）
        ▼
S2 子账号 ──► S3 配额用量 ──► S4 能力租户化 ──► S5 商业化闭环
   ▲
   插拔项：B-M4 故障转移+巡检（可与 S1 并行，不含用量表迁移）
           A-P5 市场采集（建议 A + S1 之后）
```

**里程碑用户价值**：A+P4 落地即可对外展示技能广场；B+M1-M2 落地即解除"仅 OpenAI"限制；E0 落地后全仓测试可信度质变；S5 落地完成 SaaS 商业闭环。

**对现有模块的改造清单**（v1 保留 + 修正）：skills-library 治理移交主后端（A）；AGENTS.md/README 定位修订（A-P1c）；`schemas/llm_provider.py` 白名单三协议（B-M1）；`LlmProviders.tsx` 向导流+Drawer（B-M2）；`llm_client.py` 协议路由 + `usage_dim` 参数（B-M3 / A-P2）；lifespan 第 7 常驻组件 SkillScoringService（A-P2）；platform_core 全业务模型 TenantMixin（C-S1）；official 新增 `/skills` 与 S5 注册页（A-P4 / C-S5）。

**明确不动**：智能爬虫核心闭环、new-api 中转站平台级定位、`.agents/skills/`（开发协作 skill）、asyncio+分布式锁自写任务范式（不引入 celery 类框架）。

---

## 9. 横切约束与 TDD 交付约定

**架构红线**：新模块过 check-arch R1-R12 + B1-B3（敏感项不落 yml / 异步 Redis 走 get_async_redis / API 不碰 ORM / scrapy 不 import backend）；S1 时新增 R13。数据契约改动必跑 `bash scripts/check-arch.sh`。

**键名契约**：skills 域 Redis 键（`skill:score_queue` 等）集中入 `platform_core/queues.py`；SaaS 用量键带 tenant 段。

**TDD 纪律（D11，每阶段适用）**
1. 本文 §4-§7 各阶段的 **Seam 声明即预确认 seam**——测试只写在声明过的 seam 上（API 端点 / Service 公共方法 / 适配器接口），不测私有方法、不 mock 内部协作者、断言走公共接口可见行为；
2. **red → green**：每阶段首个用例先失败再实现；一个 slice 一个循环，不批量预写测试；
3. 期望值来自独立事实源（rubric 评分样例、协议响应样例报文、边界字面量），禁止同源重算式断言；
4. 自动化验收进 CI（pytest / npm test / check-arch / MYSQL_FIDELITY 迁移项）；真实凭据与浏览器操作只进冒烟清单，交付时贴 `/verify` 输出。

**每阶段交付自检**（`/verify`）：`uv run pytest -x -q backend/tests` 退出码 0；契约改动 `bash scripts/check-arch.sh` 退出码 0；前端 `npm run build` + `npm test -- --watchAll=false` 退出码 0。

---

## 10. 开放决策点（实施前需确认，已收敛至 5 项）

1. **S1 默认租户 slug 与存量承接命名**（S1 排期前定）；
2. **S3/S5 套餐档位与配额数值**（`tenants.quota` JSON 结构 S1 定，数值 S3 定）；
3. **S4 是否启用租户私有技能**（启用则 skills 唯一键 `(tenant_id,name)` 与公开 API 过滤同步调整）；
4. **官网企业注册合规要求**（实名/协议，S5 前调研）；
5. **Azure OpenAI 是否纳入协议清单**（M4 视需求再议）。

> v1 遗留开放问题已定案：官网展示门槛=stable+recommended 不设独立开关；官网只展示人工终评（无人工分显示"评审中"）；无 /models 平台以手填兜底（不加快捷模板）；probe 端点暂不加频率限制（admin-only 已收窄）；M4 巡检周期默认 30min 可配置；重评默认 hash 变化+手动（定期复核 P5 再议）；ADAPTER_SYNC 仅 admin 可触发且仅本地部署启用。

---

*版本：v2 合并版 · 2026-08-31 重写（基线 `cf2ab0a`）· E0+A(P1-P5)+B(M1-M4) 落地（至 `fb463e6`）· 次日 SaaS S1-S5+P5 落地（至 `ae93547`，工单 01-43 全 resolved）· 由 v1 三方案 + README 融合，融合过程含三路代码探索复核与两轮决策拷问 · 修订时更新本行*
