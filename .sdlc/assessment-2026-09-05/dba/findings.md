# DBA 数据层健康评估报告 — auto_agents（2026-09-05）

评估人：SDLC DBA（只读评估，未修改任何代码/迁移）
范围：`backend/alembic/versions`（28 个迁移，链至 023）+ `platform_core/models` + `backend/repositories|services` + Redis 键构造点。

## 静态分析限制声明

本机尝试经 `platform_core.db.get_manager()` 连接开发库失败（`async_engines` 为空，Docker MySQL 未运行），**未取得 EXPLAIN 证据**。全部结论基于迁移文件、ORM 模型与 repository/service 代码的静态比对。凡涉及实际执行计划的判断（如索引命中）均已标注为静态推断，上线前应在真库补 `EXPLAIN` 验证。租户行级隔离的读侧注入（`platform_core/tenant_context.py` `with_loader_criteria` 官方配方）意味着 repository 中未显式带 `tenant_id` 的查询在租户态会被自动注入，下文涉及时已考虑该机制。

## 总体判断

**中上健康，方向正确、细节有债。** 迁移链 001→023 单线完整无分叉；头部（001-005）全部为加法变更（新表/带默认值加列），无一步到位破坏操作；017/019 的批量改造显式标注 expand-contract 意图（先加可空列→回填→收紧 NOT NULL，孤儿清理前置于 FK）；Redis 键治理（命名/TTL/失效路径）整体是本次评估的正面样板，LLM cooldown（292ca81）三件套齐全。主要债务集中在四处：**① 登录路径未跟上租户化（正确性 bug）；② 软删表唯一键与 NULL 租户唯一性两类"唯一键语义"漏洞（影响 6+ 张表）；③ 索引存在系统性冗余与低基数堆砌（约 13+ 个无访问模式支撑的索引）；④ 023 的 downgrade 不完全可逆**。均可在后续常规迁移中偿还，无需要停机的结构性返工。

---

## FINDINGS（按严重度排序，共 12 条）

### F-01【高】登录查询无租户维度，多租户同名用户登录即抛异常
- 证据：`backend/repositories/user_repository.py:18-23`（`get_by_username` 仅 `WHERE username=?`，`scalar_one_or_none()`）；`backend/services/auth_service.py:53`（登录入口调用）。登录发生在携带 Bearer token 之前，`tenant_context` 中间件不注入作用域，查询裸跑。
- 后果：迁移 017 后 username 唯一性为 `(tenant_id, username)`。两个租户各有用户 "alice" 时，`scalar_one_or_none` 收到多行将抛 `MultipleResultsFound` → 登录接口 500。单租户阶段无感，第二个同名用户注册后即刻引爆。
- 建议：登录按 `(username)` 先查候选集，`tenant_id` 非唯一时要求携带租户标识（登录页选租户 / 邮箱登录），或在注册侧强制 username 全局唯一并回改 017 的唯一键语义（需 expand-contract）。

### F-02【高】迁移 023 的 downgrade 不回滚 roles 数据变更（幽灵权限残留）
- 证据：`backend/alembic/versions/023_saas_menus_permissions.py:130-137`（upgrade 对 `roles.permissions` 执行 `JSON_ARRAY_APPEND` 追加 menu:rbac / menu:enterprise）；`023:140-142`（downgrade 仅 drop menus/permissions 两表）。
- 后果：`downgrade 023` 后 roles 表 admin 角色仍带着 menu:rbac / menu:enterprise 权限码，而 permissions 注册表已被删——权限判定引用不存在的码，"写了 down"不等于"可回滚"。
- 建议：downgrade 补 `UPDATE roles SET permissions = JSON_REMOVE(...)` 或按 022 种子全量重置 admin 权限数组；迁移评审清单中加入"upgrade 动过的每张表 downgrade 都要还原"。

### F-03【高】软删表唯一键未携带删除标记，删后无法重建同名记录（6 张表）
- 证据：软删表与唯一键并存的组合——
  - `spider_definitions`：019 加 deleted_at + `uq_spider_definitions_tenant_name`（017）；模型 `platform_core/models/spider_definition.py:13,22`
  - `llm_providers`：`uq_llm_providers_tenant_name`（017）+ 019 软删
  - `spider_task_templates`：`uq_task_templates_tenant_name`（017）+ 019 软删
  - `capability_assets`：`uq_asset_type_name`（018）+ 019 软删
  - `departments`：`uq_departments_tenant_name`（022:75）+ deleted_at（022:71）
  - `tenants`：`uq_tenants_slug`（017）+ 019 软删
- 后果：软删 `deleted_at` 置位后行仍在，唯一键继续占坑——删除"研发部"后无法新建同名"研发部"（除非先 restore 或物理清尸），与软删的产品语义直接冲突。
- 建议：expand-contract 逐步改造唯一键为 `(tenant_id, name, deleted_at)`（MySQL 唯一索引多 NULL 可共存的特性在此恰好是特性而非缺陷），或统一改为 `deleted_at` 以删除时间戳填充 NOT NULL DEFAULT '1970-01-01' 的方案；departments 最先暴露（组织改名/重组高频）。

### F-04【中高】唯一键首列 tenant_id 可空，NULL 行绕过唯一性（users/llm_providers/tags/workflow_definitions）
- 证据：`uq_users_tenant_username`（017，users.tenant_id nullable=平台超管 NULL）；`uq_llm_providers_tenant_name`（017，平台公共行 NULL）；`uq_tags_tenant_name`（020:34，tenant_id nullable）；`uq_workflow_definitions_tenant_name`（020:124，tenant_id nullable）。
- 后果：MySQL 唯一索引中 `NULL != NULL`，任意多条 `(NULL, '同名')` 可并存。users 侧两个 NULL 租户同名"平台超管"可重复插入，叠加 F-01 放大登录歧义；llm_providers 侧两条 NULL 同名平台公共 provider 可重复（数据落两份）。
- 建议：平台级行用哨兵租户 `tenant_id = 0` 代替 NULL（expand-contract：加约束前先回填），或将唯一性下沉应用层显式声明；至少在 db-spec 中写明"NULL 行唯一性由谁保证"。

### F-05【中】系统性冗余索引：单列索引被唯一键/复合索引最左前缀覆盖（约 8 处）
- 证据：
  - `017`：`ix_tenants_slug` 与 `uq_tenants_slug` 同列——唯一约束本身即索引，纯重复
  - `020`：`tags` ix_tenant_id 被 uq(tenant_id,name) 前缀覆盖；`workflow_definitions` ix_tenant_id 被 uq(tenant_id,name) 覆盖；`archive_records` ix_tenant_id 被 (tenant_id,archived_at) 覆盖；`notifications` ix_tenant_id 被 inbox(tenant_id,user_id,is_read,created_at) 覆盖；`workflow_instances` ix_tenant_id 被 (tenant_id,status,created_at) 覆盖
  - `017+019`：spider_tasks 同时存在 ix_spider_tasks_tenant_id（017）、ix_spider_tasks_tenant_status（019）——前者是后者前缀
- 后果：每个冗余索引都是纯写放大（INSERT/UPDATE 维护双份 B+ 树），读侧收益为零。
- 建议：新增迁移批量 drop 上述单列索引（加法变更直接 up/down 成对）；约定"建复合索引前先查是否已覆盖既有单列前缀"。

### F-06【中】低基数单列索引无访问模式支撑：12 张表的 deleted_at + spider_tasks.priority（约 13 个索引）
- 证据：`019:46-49` 对 SOFT_DELETE_TABLES 全部 12 张表各建 `ix_{t}_deleted_at`；`006` 建 `ix_spider_tasks_priority`（priority 基数=3）。访问侧：`platform_core/repository.py` 的软删过滤是 `deleted_at IS NULL` 叠加其他条件（无以 deleted_at 单列为入口的模式）；`spider_task_repository.py:26-44` 的过滤组合是 status/priority/spider_name，且队列调度走 Redis key（`queues.py:29`）不走该索引。
- 后果：deleted_at 几乎全 NULL（选择性≈0），优化器基本不会选它；priority 单列同理。13 个索引只贡献写放大。这与"每个索引必须能指到一个访问模式"的红线相悖——它们是"以防万一"索引。
- 建议：下个迁移删除 `ix_*_deleted_at`（若未来出现"回收站按删除时间排序"模式，届时建 `(tenant_id, deleted_at)` 复合）；`ix_spider_tasks_priority` 已被真实低频管理页过滤使用，可保留但标注频次，或并入 `(tenant_id, status, priority)`。

### F-07【中】roles.permissions 用 JSON 数组承载 RBAC 判定数据（该建表的结构存了 JSON）
- 证据：`022:50`（permissions JSON NOT NULL）；`backend/app/api/v1/auth.py:131,192`（权限判定读 JSON）；`023:130-137`（以 `JSON_CONTAINS` 做 UPDATE 过滤）；模型 `platform_core/models/role.py`。
- 后果：违背"JSON 只放不参与查询的弹性属性"。权限码集合是结构化判定数据：按权限反查角色、权限矩阵审计、api:* 级权限扩展都要 JSON 遍历/CONTAINS，无法索引。当前角色表行数极小无性能实害，但模型正确性成本已显现（023 不得不写 JSON_CONTAINS 防重）。
- 建议：规划 `role_permissions(role_id, permission_code)` 关联表（M:N，本来就该有名字的实体），roles.permissions 保留为过渡读投影；随 023 的 permissions 注册表一起构成标准 RBAC 五表。

### F-08【中】spider_tasks.status 用 MySQL ENUM 且全库无状态流转定义
- 证据：`002a_baseline_spider_tasks_and_system_configs.py`（status 为 `sa.Enum(...)` DDL 级 ENUM）；`platform_core/models/spider_task.py`（同 Enum）；`spider_task_repository.py:63-71`（count_by_status 硬编码四状态字典）。
- 后果：加一个 "cancelled"/"timeout" 状态值就要 ALTER TABLE DDL（ENUM 改值锁表）；状态合法流转（pending→running→completed/failed，retry 回环）无集中定义与流转图，非法流转靠代码零散判断，QA 无从做状态覆盖测试。
- 建议：新表一律 `VARCHAR(20)` + 应用层枚举；spider_tasks.status 存量表暂不必改，但应在 db-spec 补状态流转图（pending→running→{completed|failed}，failed→pending[retry_count<max]）。

### F-09【中】019 的 down 在真实数据下跑不通；孤儿清理为不可逆物理销毁
- 证据：`019:59-60`（upgrade 将 spider_task_templates.created_by Integer→String(64)，语义从用户 ID 改为用户名）；`019:125-126`（downgrade 将 String(64)→Integer——一旦业务写入过任意用户名如 'zhangsan'，回滚即报错/截断，down 实际不可执行）；`019:64-79`（五组孤儿 DELETE，无归档无备份，down 无法还原）。
- 后果：应急回滚场景下 019 是"纸面可逆"；孤儿数据一旦误判（例如 FK 目标表被延迟写入）即永久丢失。
- 建议：改类型回滚路径补数据校验（非数字置 NULL 再转）；破坏性清理先 INSERT 到归档表（项目已有 `archive_records` 表，021）再 DELETE；交付前执行一次真实 `upgrade→downgrade→upgrade` 并贴退出码（方法论要求，当前未见证据）。

### F-10【低】时间字段 timezone 语义在模型层混用（约半数表无 tz 声明）
- 证据：带 `timezone=True`：spider_task.py 全表、019 deleted_at（mixins.py:26）、020/021 新表；无 tz：users/roles/departments/menus/permissions（022/023）、001-016 大部分 created_at。
- 后果：MySQL 侧都会落成 DATETIME（`timezone=True` 不改变 DDL），实害在驱动解析与跨表比较语义不一致——同一事务里 spider_tasks.created_at（tz-aware）与 users.created_at（naive）比较需隐式转换，DST/迁移时区时会错位。时区约定未见于任何 db-spec。
- 建议：定死一条写进项目数据契约（建议：全库 naive-UTC，展示层转换，func.now() 已是 DB 时钟），模型层统一去掉/统一加上 timezone=True；新增表用代码生成模板保证一致。

### F-11【低】Redis 键命名两处无域前缀；一个配置 hash 无 TTL（有失效路径、容量有界）
- 证据：`platform_core/queues.py:93,95`（`login_fail:` / `register_fail:` 裸顶级，其余键均为 `域:实体:标识` 三段式）；`backend/services/channel_config_service.py:122-144`（`newapi:channel:cfg:{id}` hash 无 TTL，但写侧 hset + 显式 delete 失效路径齐全，键数=渠道数上界）。
- 后果：SCAN/监控按域聚合时这两个前缀成为孤儿；cfg hash 无 TTL 属可接受的"配置非缓存"，但未显式声明。
- 建议：下个触碰窗口改名 `auth:login_fail:` / `auth:register_fail:`（改名需双写一版）；在 queues.py 注释为 cfg hash 声明"永不过期 + 容量=渠道数"即可豁免 TTL 红线。

### F-12【正面】访问模式驱动的索引与 Redis 键治理有据可查，可作为团队基准
- 证据：
  - 迁移 012 专建 `spider_results.created_at` 索引 ↔ `spider_result_repository.py:109-119` daily_result_counts 按日聚合；019 建 `(spider_name, created_at)` ↔ `query_by_spider`（repository:131-187）等值+范围+排序，符合 ESR；`a1b2c3d4e5f6` 建 content_hash 索引 ↔ `find_by_content_hash`（repository:121-129）
  - keyword `LIKE '%kw%'` 前导通配无法走索引，repository:14-18/177-181 显式做了 200 行检索窗口护栏——明白数据库边界在哪
  - LLM cooldown（292ca81，`backend/services/ai_planner/_cooldown.py`）：键 `llm:cooldown:{provider_id}:{model_id}` 三段式、INCR+EXPIRE pipeline 原子、TTL 可配、成功即 clear 的失效路径、Redis 故障 fail-open 显式声明——命名/TTL/失效三件套齐全
  - `llm:usage:d:` 聚合用 rename 原子认领防丢增量，聚合后 delete（llm_usage_service.py:180-242）；task_results/task_log_offset/quota 均带显式 TTL
- 建议：将上述模式固化进 `.agents/skills/new-model` 的索引注释规范（每个索引写服务的访问模式），cooldown 键设计作为 Redis 键模板收录。

---

## 抽查明细（迁移 up/down 成对率，最近 6 个）

| 迁移 | up/down 成对 | 破坏性变更处理 | 备注 |
|---|---|---|---|
| 023 | 部分（F-02） | 无 DDL 破坏 | 种子 f-string 拼接（常量，低风险）；id 用 Integer 非 BIGINT |
| 022 | 完整 | 无 | roles 无 tenant_id（全局角色，若需租户自定义角色是缺口，观察项）；departments 唯一键见 F-03 |
| 021 | 完整 | 无（纯新增+种子） | system_caches 带 expires_at，DB 缓存有 TTL 意识 |
| 020 | 完整 | 无（纯新增） | 冗余索引见 F-05 |
| 019 | 成对但跑不通（F-09） | expand-contract 意识到位（先可空→回填→收紧；孤儿清理前置 FK） | 12 个 deleted_at 索引见 F-06 |
| 018 | 完整（4 表逆序 drop + 列回滚） | 无（新增+回填幂等 NOT EXISTS） | downgrade 缺 skill_reviews.asset_id 的 drop_index（add_column index=True 自动建的索引在 drop_column 时 MySQL 会连带删除，可接受） |

头部 001-005：全部加法变更（新表、带 server_default 的加列），无删列/改型/加非空一步到位，链起点干净。002a 基线修复（spider_tasks 基线表插在 003 前）属事后补基线，down 成对，无分叉。

## 后续建议优先级

1. **立即**（正确性）：F-01 登录租户维度、F-02 补 023 down
2. **本迭代**（数据语义）：F-03 软删唯一键（先 departments/spider_definitions）、F-04 NULL 租户哨兵值
3. **下个清理窗口**：F-05/F-06 冗余与低价值索引批量下线（一个加法迁移搞定）
4. **规划项**：F-07 role_permissions 关联表、F-08 状态流转图入 db-spec、F-10 时区契约成文
5. 上真库后：对 `get_by_username`、`list_tasks(status)`、`find_by_content_hash`、`query_by_spider` 四条 Top 查询补 EXPLAIN 证据
