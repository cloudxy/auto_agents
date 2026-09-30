# Findings — R3-data-layer（ORM 模型、Pydantic 契约与迁移）

## Snapshot
- HEAD: 82259f301c060dbf411424ec8775f29944e313e1（工作区干净）
- slice: `git ls-files -s` over explore_roots(platform_core/models platform_core/schemas backend/alembic backend/repositories tools/check scripts/db) + inputs → sha256 de92c5e6c771…（153 条），由 manager 计算
- reviewer: sdlc-workflow:reviewer（G-fresh，只读）；packet: ../packets/2026-09-27-1830-review-reviewer-R3-data-layer.md
- 方式：静态审查 + evidence/ 已记录执行；reviewer 未执行命令，运行时判断标「待验证」。
- 覆盖面：已读 packet 全部 inputs；models 中 mixins、base、user、billing、llm_token_usage、spider_task、spider_result 全文及其余模型 grep；迁移链全部 revision/down_revision；028、048 全文；scripts/db 3 个文件。仅 grep 未逐行审：其余迁移正文、capability/skill 模型全文、`backend/repositories` 具体仓储类、schemas 各子模块。

**摘要**：12 条（major 5 / minor 7，无 blocker）。两大问题：① 新人初始化拿到的库不对——`init_project.sh` → `bootstrap.sh` 用 create_all 建表后直接 `stamp head`，跳过迁移链种子数据与后续结构变更；② 迁移门禁一半是空的——DBML lint 零输入放行、结构漂移只比列名、6 个迁移往返测试文件不在 CI 保真通道里、从未执行。

---

## FINDINGS

### QA-1 `bootstrap.sh` 用 create_all + `stamp head` 建库，跳过迁移种子与后续结构变更；「是否已迁移」正则永远匹配不到当前数字版本号
- Dimension: 1 / 8 / 9 | Severity: **major** | 工作量: S
- Evidence：`scripts/db/bootstrap.sh:34-35` 先执行 `init_tables.py`（`Base.metadata.create_all`，`scripts/db/init_tables.py:28`）；`bootstrap.sh:38-43` 仅当 `alembic current` 输出匹配 `[0-9a-f]{12}` 时 `upgrade head`，否则一律 `stamp head`。当前 head 为 `"050"`（`backend/alembic/versions/050_asset_featured_examples.py:16`），全链只有 007→008 间 4 个旧版本是 12 位 hex。`init_project.sh:122-125` 新人初始化走此路径。被跳过的种子：租户（`017_saas_tenant_foundation.py:51`、`024_users_tenant_not_null.py:38`）、角色（`022_saas_roles_departments.py:61`）、权限与菜单（`023_saas_menus_permissions.py:100,116`）、套餐（`029_billing_cost_retention.py:88,98`、`040_billing_and_relay_sku.py:135,145`、`047_w2_channel_null_pro_quota.py:37`）、内置爬虫定义（`005_add_spider_definitions.py:52`、`007_add_flow_generic_definition.py:39`）。
- 后果：全新库 `alembic current` 为空 → stamp → 库里无 platform/default 租户、角色、权限、菜单、套餐、内置爬虫定义，且表结构为 ORM 形态而非迁移形态（如 tenant_id 可空，见 QA-2）。已有库（假设停在 045）：create_all 不给已存在表补列，却被 stamp 到 050 → 046–050 DDL 被静默跳过，后续启动/查询才暴露。`test_alembic_baseline.py:116-133` 的「幂等」测试只比列名，覆盖不到种子行。
- Suggestion：`bootstrap.sh` 只做「建库 + `alembic upgrade head`」（脚本第 3 行注释已说明 002a 补齐基线，可直接迁移）；create_all + stamp 移到显式 `--adopt-legacy` 分支并要求 `alembic_version` 为空；「是否已迁移」改为判断 `alembic current` 输出非空，不依赖 hex 正则。

### QA-2 ORM 模型与迁移链漂移缺少机械检测，现有对拍只比列名；租户列可空性已实际漂移
- Dimension: 3 / 4 / 6 | Severity: **major** | 工作量: M
- Evidence：`backend/alembic/env.py:52-58,69-73` `context.configure` 无 `compare_type` / `compare_server_default`；CI、tools、scripts 中搜不到 `alembic check`。`backend/tests/test_alembic_baseline.py:84-88,109-113` 只比表名集合与逐表列名集合（不比类型、可空、默认值、索引、唯一约束）。`platform_core/models/mixins.py:16-20` 自认「create_all 与迁移链的此差异为已知豁免（基线对拍口径=列集）」。已发生漂移：`TenantMixin.tenant_id` 模型可空（`mixins.py:23`），迁移层已收紧或以 NOT NULL 建表（`017_saas_tenant_foundation.py:80`、`020:73`、`022:69`、`035:39`、`041:30`、`045:28`、`046:159`），模型里只有 `User` 覆盖为 `nullable=False`（`user.py:42`）。
- 后果：默认测试走 SQLite + create_all（`backend/tests/conftest.py:379,386-390`），1954 用例验证的是「非生产形态」schema：tenant_id=NULL 写入在测试通过、在生产 IntegrityError。带 tenant 唯一键的表（如 `billing.py:41` `uq_tenant_subscriptions_tenant`）在 create_all 环境下可有多行 NULL，且被 `tenant_context.py:165` `col == tenant_id` 过滤掉成为不可见孤儿行。QA-1 路径建的开发环境同样如此。
- Suggestion：`env.py` 加 `compare_type=True, compare_server_default=True`；CI MySQL 保真通道加 `alembic upgrade head && alembic check`（Alembic ≥1.9，项目 ≥1.18 满足），有差异即失败；模型与迁移对齐——租户表显式 `tenant_id nullable=False`（仅 llm_providers 保留可空），或反过来让 Mixin 默认 NOT NULL、单独豁免 llm_providers；基线对拍扩展到可空、类型、索引、唯一约束。

### QA-3 迁移往返测试有 6 个文件在任何自动化流程里都不执行；本次实跑记录也未覆盖迁移链
- Dimension: 3 | Severity: **major** | 工作量: S
- Evidence：CI 保真通道只列 8 个文件（`.github/workflows/ci.yml:93-102`）。以下标记 `mysql_fidelity`、未设 `MYSQL_FIDELITY` 时自 skip，且不在 CI 清单：`test_t24_migration_042.py:15-21`、`test_t35_migration_043.py:15-28`、`test_t14_migration_046.py:16-35`、`test_outbound_migration_041.py:13-19`、`test_db_behavior_loop.py:13-21`、`test_saas_ddl_drill.py:13-19`。CI 默认 pytest 任务不设 `MYSQL_FIDELITY`（`ci.yml:69-75`）→ 两条 CI 任务都不执行它们。本次 `evidence/pytest.txt:1` 同样没开 `MYSQL_FIDELITY`（`1954 passed, 41 skipped`，`pytest.txt:364`），连 `test_alembic_baseline.py` 在本快照也是 skip。全链 downgrade 已知不可用：`test_alembic_baseline.py:136-141` 显式 skip（errno 1553，注「生产禁止 downgrade past 037」）。
- 后果：041/042/043/046 的 up→down→up 验证只写未跑，只证明「测试存在」；本快照下迁移链正确性为**未验证**。
- Suggestion：6 个文件加入 `ci.yml:93-102`，或改按 `-m mysql_fidelity` 选择以免新增文件再漏；downgrade 边界（037）写进门禁（见 QA-4），而非只留在 skip 原因里。

### QA-4 两个 DB 门禁存在空心断言与规则覆盖漏洞
- Dimension: 3 / 8 | Severity: **major** | 工作量: M
- `db_ir.sh` 零输入即放行：仓库无任何 `*.dbml`，`tools/check/db_ir.sh:19-27` 直接 exit 0；`evidence/db-gates.txt:1-3`「无 DBML 文件，跳过」+ `exit=0`；CI 任务名仍叫 "DBML IR lint"（`ci.yml:155-156`），绿灯下零检查。
- `db_migrations.sh` 规则漏洞：

  | 规则 | 位置 | 漏洞 |
  |---|---|---|
  | SM-7 可回滚 | `:133-135` | 只检查 `def downgrade` 后 3 行内 `pass$`；`raise NotImplementedError` 能过（`048_merge_030_047.py:22-25`）；已知 downgrade 过 037 必败（QA-3），门禁照绿 |
  | SM-6 大表锁 | `:125-130` | 只匹配 `alter_table\|alter_column` 且只列 3 张表；漏 `add_column`/`create_index`/`create_foreign_key`/`create_unique_constraint`（如 `spider_results` 上 `a1b2c3d4e5f6_…:25`、`ce5210dedbd4_…:25`、`028_api_keys_and_fetched_at.py:31-35`）；`spider_tasks`、`product_events`、`llm_token_usage` 不在大表清单 |
  | SM-1 破坏性变更 | `:75` | 只看 `drop_table/drop_column`；`drop_index`、`drop_constraint`、对存量表 `alter_column(nullable=False)` 不检查（如 `017:80`、`024_users_tenant_not_null.py:70`） |
  | SM-3 / SM-8 | `:81,138` | 单行 grep；多行 `alter_column` 与不带 `sa.text` 的字符串 `op.execute`（如 `023:100` f-string INSERT）不命中 |
  | 拓扑 | 无 | 缺「单 head」「编号单调」检查；039 已分叉两子（`028_…:12` 与 `040_…:17` 都 revise 039），直到 048 才手工合并 |

- Suggestion：`db_ir`——无 DBML 时若本次改动涉及迁移或模型即判失败，或改为直接遍历 `Base.metadata` lint（created_at/updated_at、软删表唯一键含 alive_flag、租户表 tenant_id NOT NULL、外键列有索引）。`db_migrations`——SM-7 改 AST（downgrade 体为 pass 或 raise 都报告，允许 `SM-EXEMPT` 注明理由）；SM-6 改 AST（所有 `op.*` 首参落在大表清单即命中，清单移到配置）；SM-1 补 `drop_index`/`drop_constraint`/`nullable=False` 的 `alter_column`；新增 `alembic heads` 恰好 1 个检查（需 python 环境，可放保真任务）。

### QA-5 全库时间基准不统一：tz 标注无效，写入端混用服务器时间、本地 naive 与 UTC aware
- Dimension: 1 / 8 | Severity: **major**（行为影响取决于部署时区，待验证） | 工作量: M
- Evidence：模型大量用 `DateTime(timezone=True)`，但 MySQL DATETIME 不存时区、标注无效；同表混用 naive `DateTime`（`user.py:50` vs `user.py:51-52`；`llm_token_usage.py:37-38` naive、`spider_task.py:43-46` tz）。引擎未设会话 `time_zone`（`platform_core/db.py:68-94`），`docker-compose.yml` 无 TZ / `default-time-zone`。写入/比较端混用：服务器 `func.now()`（`consumer.py:271` started_at、`repository.py:75`、各模型 `server_default`）；本地 naive `datetime.now()`（`backend/tasks/consumer.py:480,515` stale cutoff、`schedule_service.py:56,239`、`alert_service.py:120,185,240`）；UTC aware（`retention_service.py:72,78` 与 created_at 比较、`billing_service.py:276,396,430,458`、`tenant_expiry_service.py:23`）。
- 后果（推演未复现）：宿主机 CST、MySQL 容器 UTC 时，`consumer.py:480/515` cutoff = UTC 当前 +2h → `find_stale_running` 把所有 running 当候选（6 小时宽限失效，只剩 Redis 活跃集合一道保护），`find_stale_pending` 可能把刚建的 pending 立即重投（重复采集）；`retention_service` 清理边界偏移一个时区差。反之宿主 UTC、MySQL CST 则回收延迟 8 小时。
- Suggestion：约定「数据库存 UTC naive」；pymysql/aiomysql 连接设 `init_command="SET time_zone='+00:00'"`，alembic 同步；提供统一 `utcnow()` 替换 `datetime.now()`；ruff 启用 `DTZ`；模型 `timezone=True` 改为统一注释约定。

### QA-6 结果表热索引与租户注入后的查询路径不匹配，且有冗余索引
- Dimension: 5 | Severity: minor（无实测慢查询，需 EXPLAIN） | 工作量: S–M
- Evidence：每条 SELECT 被自动注入 `tenant_id = ?`（`platform_core/tenant_context.py:160-168`），但结果列表热索引 `(spider_name, created_at)` 不含 tenant_id（`platform_core/models/spider_result.py:15`）；冗余索引：主键上 `index=True`（`spider_result.py:22`、`spider_task.py:33`），`spider_name` 单列索引（`spider_result.py:25`）被复合索引最左前缀覆盖；追加型大表 `spider_results` 主键 `Integer`（`spider_result.py:22`），而 `channel_probe_result` 已用 BigInteger。
- 后果：租户多了后「某租户某爬虫按时间倒序」要么 filesort 要么回表过滤；INT 主键 21 亿上限。
- Suggestion：保真库对结果列表 SQL 做 EXPLAIN；确认后新增 `(tenant_id, spider_name, created_at)`（ESR 顺序）并删多余单列索引（按 QA-4 标注 online DDL）；评估 `spider_results.id` 扩 BIGINT（大表变更走 pt-osc / gh-ost）。

### QA-7 `BaseRepository` 写语义存在边界缺口
- Dimension: 4 / 8 | Severity: minor | 工作量: S
- Evidence 与后果：`update()` 不排除软删行，写完用 `get_by_id` 读回得 None（`platform_core/repository.py:62-66`）→ 已删行被改、调用方按 404 处理；`update(**kwargs)` 接受任意列含 `tenant_id/deleted_at/id/alive_flag`——`do_orm_execute` 只追加 `WHERE tenant_id=当前租户`（`tenant_context.py:143-150`），`SET tenant_id=其他租户` 可把行搬到别的租户，`before_flush` 断言只查 `session.new`（`tenant_context.py:125-132`）；现有调用方直接透传 dict（`alert_service.py:67`、`spider_registry_service.py:476`），当前 payload 来自 schema、**尚未发现**可利用路径，但这一层缺兜底；`get_all` 用 offset 分页无 ORDER BY（`repository.py:41-46`），MySQL 上翻页不确定；`delete()` 允许对软删表物理删除（`repository.py:92-96`）。
- Suggestion：`update` 追加 `deleted_at IS NULL`；受保护列黑名单拒绝 `id/tenant_id/deleted_at/created_at/alive_flag`；`get_all` 默认 `order_by(model.id)`；软删表调用 `delete` 报错或改名 `hard_delete`。

### QA-8 JSON 存储与状态字段契约不收敛
- Dimension: 6 | Severity: minor | 工作量: M
- Evidence：同一「配额」概念 `Tenant.quota` 用 JSON 列（`tenant.py:20`）、`Plan.quota_json` 用 Text（`billing.py:28`）；多处 JSON 存 Text（`spider_task.py:37`、`spider_schedule.py:23`、`task_template.py:24`、`alert_rule.py:18`、`operation_log.py:16`、`spider_result.py:31`）；方言专用 `mysql.JSON`（`skill.py:11`、`capability.py:10`）与通用 JSON 混用；`SpiderTask.status` 无 `nullable=False` 与 `server_default`（`spider_task.py:35-36`），Pydantic `status: str` 不约束（`platform_core/schemas/spider.py:15,37,90`），同文件 `priority` 有 pattern（`:38,45`）。
- 后果：非法状态值与结构不一致 JSON 能入库；序列化逻辑分散在各 service（如 `alert_service.py:63-66`）。
- Suggestion：schema 层 status 加 `Literal`；status 列改 `NOT NULL server_default='pending'`；新表一律 JSON 列，存量 Text→JSON 仅在触碰相关表时按 expand-contract 推进。

### QA-9 MySQL 连接串三处各自拼接、行为不一致，并有无效配置键
- Dimension: 1 / 7 | Severity: minor | 工作量: S
- Evidence：`scripts/db/init_tables.py:21-25` 拼 URL 不 `quote_plus` 密码、忽略 CHARSET；`backend/alembic/env.py:25-30` 与 `platform_core/db.py:60-69` 各自拼接；`config/prod/mysql.yml:7` `PASSWORD`、`:10` `COLLATION` 从未被读取（`db.py:40-44` 只读环境变量、只用 CHARSET）；生产代码按测试框架分支 `db.py:16` `_IN_PYTEST = "pytest" in sys.modules`。
- 后果：密码含 `@ : /` 时 bootstrap 失败而应用正常；配置文件给人「可在此配排序规则」的错觉。
- Suggestion：抽 `platform_core.db.build_mysql_url(key, driver)` 三处统一；COLLATION 经 `init_command` 生效或删除；`_IN_PYTEST` 改显式配置项（如 `DB.POOL_MODE`）。

### QA-10 迁移文件编号与实际执行顺序不一致
- Dimension: 6 | Severity: minor | 工作量: S
- Evidence：数字与 hash 版本混用——`ce5210dedbd4`、`8551b2c539b2`、手写 `a1b2c3d4e5f6`、`e7a6f5a12bc9` 夹在 007 与 008 之间（`008_…:21` revise `e7a6f5a12bc9`）；002a 事后插入（`003_…:21`）；031 revise 027（`031_add_product_events.py:18`）；028–030 实际在 039 之后执行（`028_…:12`），经 048 合并。
- 后果：看文件名推断顺序会出错，QA-1 的 hex 正则即此类误判。
- Suggestion：后续版本号统一补零单调编号，`down_revision` 指向当前唯一 head（配合 QA-4 单 head 检查）；`versions/README` 记录实际执行链或由 CI 输出 `alembic history`。

### QA-11 模型与 schema 聚合入口有重复和缺漏
- Dimension: 6 | Severity: minor | 工作量: S
- Evidence：`platform_core/models/__init__.py:45` 与 `:55` 重复 import billing；`__all__` 在 `:65` 与 `:73` 重复列出 `Plan / TenantSubscription / Order`；`platform_core/schemas/__init__.py` 自称「统一参数接收器」，但未导出 skill、llm_provider、api_key、outbound、audit、litellm 等 schema 模块（`pytest.txt:318-335` 覆盖率清单可见它们存在）。
- Suggestion：删重复；补全导出或把 docstring 改为「常用子集」。

### QA-12（问题）部分软删表唯一键未带 alive_flag，是有意保留还是遗漏？
- Dimension: 8 | Severity: minor / 待确认
- Evidence：`Skill` 带 `SoftDeleteMixin`（`skill.py:18`），`name` `unique=True`（`skill.py:24`）；`Tenant` 带软删（`tenant.py:9`），`slug` `unique=True`（`tenant.py:16`）；`SpiderResult` 带软删，唯一键 `(tenant_id, spider_name, content_hash)`（`spider_result.py:16-19`）。对照 User、TaskTemplate、Department、SpiderDefinition、LlmProvider、Capability* 都用 alive_flag 模式。
- 后果：软删后同名技能无法重新导入、租户 slug 无法复用、被删采集结果阻止相同内容再入库（去重命中看不见的行）。
- Suggestion：若有意保留（墓碑占位）在模型 docstring 写明；否则按 025/042 方式加 alive_flag。

---

## Dimensions checked
1. 标准符合 ⚠️ — QA-1、5、9；bootstrap 自称「幂等」，实际与迁移链事实源冲突。
2. 标准质量 ➖ — review-only，无 FR/GWT；测试断言质量问题归维度 3。
3. 证据有效性 ⚠️ — QA-2、3、4：db_ir 零输入放行、对拍只比列名、6 个迁移测试从未执行、本快照实跑未覆盖迁移链。
4. 安全 ⚠️ — QA-2（create_all 环境租户列可空）、QA-7（跨租户改 tenant_id 缺兜底）；未发现注入（迁移 f-string SQL 取值均为常量）；无硬编码密钥（`arch.txt:4-5` R1/R2 通过）。
5. 性能 ⚠️ — QA-6（需 EXPLAIN）；`get_all` 默认 limit=100，无无界查询。
6. 契约一致性 ⚠️ — QA-8、10、11。
7. 宪法合规 ✅ — `arch.txt:4-26` R1–R13、B1–B4 全过（已记录执行）；核对 R8：`platform_core/models/__init__.py` 未 import schemas；配置即代码有无效键（QA-9）。
8. 边界 ⚠️ — QA-5（时区）、QA-7（软删与更新）、QA-12（软删与唯一）。
9. 产品价值与体验 ⚠️ — 无 UI，按可运行性与运维行为：新人初始化得到缺种子数据的库（QA-1）；任务超时回收受时区影响（QA-5）。截图类证据不适用。

## Strengths（改进时应保留）
1. 软删与唯一共存的 alive_flag 生成列模式：`CASE WHEN deleted_at IS NULL THEN 1 ELSE NULL END` 进唯一键，已在 users、task_templates、departments、spider_definitions、llm_providers、capability_* 等至少 9 张表落地（`user.py:30-32,53-55`、`capability.py:102,224-226,268,295-296`），附迁移出处（025/042）。
2. 金额一律整数分：`price_cents`/`amount_cents` Integer、`cost_cents` BigInteger（`billing.py:26,66`、`llm_token_usage.py:36`），无 Float 金额。
3. 租户隔离集中在 ORM 事件层：SELECT 走 `with_loader_criteria`，UPDATE/DELETE 追加 WHERE，新行 before_flush 断言（`tenant_context.py:120-169`），R13 为绿（`arch.txt:16`）。
4. 门禁脚本修过假绿缺陷且有文档：heredoc `report_lines` 解决管道子 shell 丢计数、退出码截断在 255 防取模归零、SM-5 用 AST 识别 `sa.Column(nullable=False)`（`db_migrations.sh:7-17,94-122,151`、`db_ir.sh:7-11`）。
5. 真实 MySQL 保真通道 + 细致的数据库行为防护：CI 挂 mysql:8 跑 fresh upgrade 与 create_all 对拍（`ci.yml:77-102`、`test_alembic_baseline.py:93-113`）；读路径 READ ONLY 挂载与复位失败时 invalidate 连接（`db.py:239-273`）；索引治理有取舍理由（`mixins.py:16-20,32-34`、`026_index_governance.py:72-90`）。

## Improvement themes
- **T1 迁移链成为唯一 schema 事实源**（QA-1、2、9、10）— 目标：任何环境只经 `alembic upgrade head` 建库；create_all 只用于单测；ORM 与迁移在类型/可空/索引/约束零差异，由 `alembic check` 机械保证。顺序：修 bootstrap（S）→ 统一连接串工具（S）→ env.py 启用 compare + 模型对齐 tenant_id 可空性（M）→ CI 保真通道加 `alembic check`（S）→ 版本号规范（S）。
- **T2 DB 门禁去空心化**（QA-3、4）— 目标：每个绿灯对应真实被检查对象；迁移往返测试全在 CI 执行；单 head / 可回滚 / 大表锁检查基于 AST。顺序：6 个保真测试进 CI（S）→ 单 head + SM-7 覆盖 raise（S）→ 扩 SM-6/SM-1（S–M）→ db_ir 改为基于 `Base.metadata` lint（M）。
- **T3 统一时间基准**（QA-5）— 目标：DB 存 UTC；会话固定 `time_zone='+00:00'`；应用只用 `utcnow()`；ruff DTZ 卡新增 naive。顺序：验证各环境时区 → 加 `init_command` → 替换 consumer/schedule/alert 的 `datetime.now()` → 启用 DTZ → 评估存量偏移、必要时回填。
- **T4 Repository 与租户写路径加固**（QA-7、12）— 目标：基类写方法默认对软删与受保护列安全；分页确定；软删唯一键策略逐表明确。顺序：update 软删过滤 + 受保护列黑名单（S）→ `get_all` order_by（S）→ 明确 QA-12 三表意图后再改（S–M）。
- **T5 存储类型与契约收敛**（QA-6、8、11）— 目标：状态值 schema 层 Literal + DB 层 NOT NULL；新表原生 JSON；热查询索引以 tenant_id 打头并经 EXPLAIN 验证。顺序：Literal + `__init__` 清理（S）→ EXPLAIN 后调 spider_results 索引、走 online DDL（M）→ Text→JSON 随业务逐表推进（M）。

## 需 manager 代跑的验证（reviewer 未执行）
1. QA-3 / 迁移链：`MYSQL_FIDELITY=1 MYSQL_FIDELITY_HOST=127.0.0.1 MYSQL_FIDELITY_USER=root MYSQL_FIDELITY_PASSWORD=<pwd> uv run pytest -q backend/tests/test_alembic_baseline.py backend/tests/test_t24_migration_042.py backend/tests/test_t35_migration_043.py backend/tests/test_t14_migration_046.py backend/tests/test_outbound_migration_041.py backend/tests/test_db_behavior_loop.py backend/tests/test_saas_ddl_drill.py`
2. QA-4 / QA-10：`cd backend && uv run alembic heads && uv run alembic history -r 037:head`（预期单 head `050`）
3. QA-2：保真库 `upgrade head` 后 `cd backend && uv run alembic check`（预期报差异）
4. QA-1：空库执行 `bash scripts/db/bootstrap.sh` 后 `SELECT COUNT(*) FROM tenants/roles/menus/plans`（预期均 0），再 `SHOW CREATE TABLE spider_tasks` 确认 tenant_id 可空
5. QA-5：docker mysql 内 `SELECT @@global.time_zone, @@session.time_zone, @@system_time_zone, NOW(), UTC_TIMESTAMP();` + 宿主机 `date`
6. QA-6：保真库对结果列表 SQL（带 tenant_id、spider_name、按 created_at 倒序）EXPLAIN

## Decisions
- 无（review-only，不推进 feature 状态）。

## Open questions
- **Q-R3-1（待确认）** `skills.name`、`tenants.slug`、`spider_results` 去重键软删后是否有意保留占位？(a) 有意保留、docstring 写明；(b) 改 alive_flag。建议 tenants.slug 选 (a)（防租户标识复用），skills 与 spider_results 选 (b)。
- **Q-R3-2（待确认）** 生产与开发环境时间基准以什么为准？建议统一 UTC（已按运营默认写进 T3）。
- 执行层面默认：按「全链 downgrade 只保证到 037」既有约束（`test_alembic_baseline.py:136-141`）提门禁建议，不要求恢复全链可回滚。

## Product-delta rows
- 无（产品层未建立）。

## Lesson rows（静态核实）
1. 判断迁移状态不能依赖版本号格式：本仓库混用数字与 hex 版本，`[0-9a-f]{12}` 类正则会静默走错分支（`bootstrap.sh:39`）。
2. 「测试文件存在且带 skip 标记」≠「被执行」：`mysql_fidelity` 测试必须出现在 CI 显式清单（`ci.yml:93-102`）或按 marker 选择，否则两条 CI 任务都会跳过。
