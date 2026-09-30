<!-- manager 落盘：2026-09-28，reviewer（G-fresh）最终交付原文逐字提取自其交付记录；packet 见 ../packets/ -->

# F7 测试·验收·发布：G-fresh 审查报告（第二轮，仅出报告）

## Snapshot
- HEAD：82259f301c060dbf411424ec8775f29944e313e1（工作区只新增了 docs/ops/）
- 审查切片：对 explore_roots 执行 `git ls-files -s` 得到的 sha256 为 cb168f98ca3ce886e6a95f4dbd7d95a9f8a55234fdc0cfa5ee4c4acb06c88b12（manager 计算，这里原样照抄）
- 审查员：sdlc-workflow:reviewer（G-fresh，只读）；packet：`packets/2026-09-27-2310-review-reviewer-F7-test-accept-release.md`
- 工作方式：静态阅读，加上检查 evidence/ 里的执行记录（mysql-fidelity-full.txt、pytest.txt、ui-runtime-summary.md、devdb-readonly.txt），并查看了截图 admin_billing_checkout-1440 和 admin_usage-1440。我没有执行任何命令，也没有独立复现。标 **[未验证]** 的条目，文末给出需要 manager 执行的命令。
- 第一轮的 R3 QA-3/QA-4、R5 QA-12、R6 QA-2/QA-8/QA-10 已报告过的问题，这里不再重复。本报告只补充新证据，或做更正、升级。

**摘要**：共 8 条发现，没有 blocker；major 6 条（QA-1 到 QA-6），minor 2 条（QA-7、QA-8）。

最关键的一条是：7 个未进 CI 的保真测试已在本机真实 MySQL 上跑过，但**测试本身写错了**。它们先升到 head 再往回降，而 head 之下有一个不可降级的合并迁移 048。所以不能照第一轮方案直接把它们加进 CI，否则 CI 会立刻变红，要先修测试。

同一个根因还带出一个发布问题：数据库实际能回滚到的最低版本是 048，不是文档里写的 037。

验收和发布两段几乎都是空白：
- 没有任何基于运行中构建的旅程验收记录；
- e2e 全部用桩，也不在 CI 里；
- 没有版本号演进、tag、CHANGELOG、CD 和环境晋级。

---

## 风险驱动覆盖矩阵（功能域 × 测试层）

图例：有 = 有测试且证据可信；弱 = 有测试但覆盖或可信度不足；无 = 没有；红 = 有测试但当前失败。

| 功能域（module-inventory.md） | 单元/服务 | API 集成（TestClient） | MySQL 保真 | 契约（OpenAPI golden / codegen） | e2e | 运行中构建的人工验收 |
|---|---|---|---|---|---|---|
| 认证/会话 | 有（test_auth_service、test_auth_utils） | 有 | 有（test_auth_login_tenant 已进 CI，ci.yml:100） | 有（test_openapi_routes_golden、ci.yml:195-198） | 弱（全桩，smoke.spec.ts:18-77） | 弱（只有超管视角） |
| 租户/成员/RBAC | 弱（rbac_service 47%，见 pytest.txt:240；tenant_admin 51%，见 :255） | 有 | 有（saas_members、rbac_deep、admin_users_crud 已进 CI） | 有 | 弱（桩，只有 members 页） | **无**（没有租户负责人视角） |
| 计费/结账/支付回调 | 弱（payment_notify_service 58%，见 :213；wechat 50%，见 :212） | 弱（外部回调入口 payment_gateways.py 30%，见 :116） | 无 | 有 | **无** | **无**（超管进结账页即 400 死路，见 QA-4） |
| 爬虫任务/调度/结果 | 有（consumer 74%） | 有 | 弱（t42 真库轮从未执行，见 QA-3） | 有 | 无 | 弱（只有超管页面加载） |
| 能力市场/官网漏斗 | 有 | 有 | 无 | 有 | **无**（official 没有 e2e） | 弱（只有页面加载，没有订阅/安装旅程） |
| LLM/中转/LiteLLM | 有 | 有 | 无 | 有 | 无 | 无（开关默认全关） |
| 迁移/Schema | — | — | 基线有（ci.yml:97）；**往返测试红**（QA-1）；DDL 演练死测试（QA-3） | — | — | — |
| 部署/发布 | — | — | — | — | — | 只有镜像构建和 compose 语法校验（ci.yml:218-228）；没有启动后冒烟、回滚演练和发布记录（QA-5） |

---

## FINDINGS

### QA-1 保真迁移往返测试的设计与合并迁移 048 不兼容：本机真库 5 个失败、1 个错误，照原方案加进 CI 会立刻变红
- Dimension: 3 / 2 / 5 | Severity: **major** | 工作量: S | 核验方式: 已记录执行 + 静态
- **现象**：`mysql-fidelity-full.txt:1` 显示 `..sFF.F..FFE.`，`:343-351` 为 `5 failed, 6 passed, 1 skipped, 1 error`，`exit=1`。4 个失败都卡在 `048_merge_030_047.py:23: NotImplementedError`（`:146`、`:211`、`:276`、`:341`），第 5 个失败（t24）是断言信息不匹配（`:12-17`，见下文）。
- **触发条件**：设置 `MYSQL_FIDELITY=1`，运行 `test_t24_migration_042.py`、`test_t35_migration_043.py`、`test_outbound_migration_041.py`、`test_db_behavior_loop.py`。
- **根因**：
  - 这些测试都先升到 head 再降到老版本：`test_t24_migration_042.py:60` 升 head，`:103/:109` 降到 041；`test_t35_migration_043.py:63` 升 head，`:126` 降到 042；`test_outbound_migration_041.py:48` 升 head，`:59` 降到 040；`test_db_behavior_loop.py:129/151` 升 head，`:143/:167` 降到 base。
  - 2026-09-14 引入的合并迁移 048（`048_merge_030_047.py:13` 声明 `down_revision=("030","047")`）在 `:22-25` 无条件抛异常。从那以后，任何降到 048 以下的操作都会失败。
  - 测试的原意是只验证被测迁移本身。例如 t24 的 docstring 写的是「041 → 042 → 041 → 042」（`:54`），但代码写成了 `head`。
  - 对照：`test_t14_migration_046.py:96-113` 把版本钉在 `"045"`/`"046"`，同一轮全部通过。
- **附带问题 1（断言空转）**：`test_t24_migration_042.py:102` 写的是 `pytest.raises(RuntimeError, match="同名多行")`。`NotImplementedError` 是 `RuntimeError` 的子类，所以这个断言接住了**另一个异常**，然后只在消息匹配上失败（`mysql-fidelity-full.txt:14-17`）。即使消息碰巧匹配，这个断言也证明不了「impossible-down 守卫」生效了。
- **附带问题 2（性能证据失真）**：`test_db_behavior_loop.py` 的 EXPLAIN 断言在 `:139-142` 和 `:162-165`，降级到 base 在后面的 `:143`/`:167`。从 traceback 形态推断（**[未验证]**，见命令 1），索引断言大概率已通过，测试却在收尾降级时报红。这说明「复合索引生效」这条性能证据目前既不能算绿，也不能算红。
- **后果**：
  - 第一轮 R3 QA-3 和改进方案 T2 建议「6 个保真测试进 CI（S）」。照做的话 CI 会马上变红，团队很可能又把它们移出 CI 或整条通道降级。
  - 041/042/043 的回滚代码（按 db-spec §16.1 设计的 impossible-down 守卫）在任何环境都跑不到，等于死代码。
- **修复方案**：
  1. 往返测试一律钉版本：t24 改为 `upgrade("042") → downgrade("041") → upgrade("042")`，t35 用 043/042，outbound 用 041/040；
  2. `test_db_behavior_loop` 删掉 `downgrade(base)`，schema 已由 fixture 整库删除；
  3. t24 改成精确断言异常类型（`assert type(exc.value) is RuntimeError`，或给迁移定义专用异常类）；
  4. 以上修复后，再按 `-m mysql_fidelity` 加入 CI（选择方式见 QA-3）。
- **应补的测试或验收**：CI 保真步骤 `pytest -m mysql_fidelity backend/tests` 全绿；新增一条元测试，要求迁移往返测试文件里不出现 `upgrade(cfg, "head")` 后跟具体版本号的降级（可以用 AST 检查）。

### QA-2 数据库实际回滚下限是 048，不是文档写的 037；发布没有成文的前滚/回滚边界，也没有「迁移先于代码」的执行位置
- Dimension: 6 / 8 / 1 | Severity: **major** | 工作量: S（代码）+ S（文档） | 核验方式: 已记录执行 + 静态；降到 047/030 的行为 **[未验证]**
- **现象**：`048_merge_030_047.py:23-24` 的报错写着「请指定单一父修订。生产禁止 downgrade past 037」，`test_alembic_baseline.py:136-141` 的 skip 理由也把边界写成 037。但执行记录显示，从 050 往回降，一到 048 就失败（`mysql-fidelity-full.txt:78-82`）。
- **根因**：Alembic 在任何离开 048 的降级中都会调用 048 的 `downgrade()`，而这个函数无条件抛异常。报错里「指定单一父修订」的建议很可能无效：按 Alembic 语义推断，降到 047 或 030 同样要经过 048（**[未验证]**，见命令 2）。合并迁移本身没有 DDL（`:8`「本修订无 DDL」），标准写法应该是 `pass`。
- **同时存在的问题**：
  - Dockerfile 和 docker-compose.yml 里都没有迁移步骤（在 docker-compose.yml 中 grep `alembic|migrat` 无结果）；
  - 迁移只能手工执行 `scripts/db/migrate.sh:5`（`alembic upgrade head`，README.md:400）；
  - 所以「先迁移、再上新代码」的顺序全凭人记。
- **后果**：任何包含 049/050 及以后迁移的发布，数据库只能退到 048；越过 048 只能前滚修复。这件事没有写在任何地方。值班人员按报错提示去「指定父修订」只会再失败一次。
- **修复方案**：
  1. 048 的 `downgrade()` 改为 `pass`，并新增保真用例「head → 047 → head」「head → 030 → head」来确定真实下限；
  2. 在 R6 QA-10 要求新建的 `docs/ops/deploy.md` 里，写明迁移策略：expand/contract 两阶段、真实回滚下限、前滚修复流程、迁移用独立一次性容器或 job 在新代码上线前执行；
  3. 回滚下限写进 `tools/check/db_migrations.sh`（与 R3 QA-4 的 SM-7 改造合并），不要只留在 skip 理由里。
- **应补的测试或验收**：上述两条往返用例；发布演练记录（dev 环境 upgrade → 回滚到上一个镜像 → 验证 N-1 代码能在新 schema 上运行）。

### QA-3 保真测试清单靠手工维护：t42 真库轮不带 marker、从未被选中执行；DDL 演练是死测试，却被 ADR-0002 当作排期依据
- Dimension: 3 / 6 | Severity: **major** | 工作量: S | 核验方式: 已记录执行 + 静态
- 这条补充并更正第一轮 R3 QA-3。
- **现象与根因**：
  - `ci.yml:93-102` 手写了 8 个文件。`test_t42_fidelity_queue_depth.py:31-36` 用自己的 `_FIDELITY` 加 `skipif` 做开关，**没有打 `mysql_fidelity` marker**。所以即使按 R3 的建议改成 `-m mysql_fidelity` 选择，也选不到它。
  - 这个文件的 docstring 写明它是评审裁定「IMPL-QA-5：qa 真库轮直验 notifications 行 + user_id FK」的唯一落点（`:3-5`）。manager 这轮跑的是「7 files not in CI + test_alembic_baseline」（`mysql-fidelity.txt:1`），也没有覆盖它。也就是说，这条评审裁定要求的验证从来没有发生过。
  - `test_saas_ddl_drill.py:22` 使用了 `alembic_db_url` fixture，但没有导入（对照 `test_t24_migration_042.py:13` 有导入），执行结果是 `fixture 'alembic_db_url' not found`（`mysql-fidelity-full.txt:3-10`）。它的 docstring 却说「结论以本测试在保真通道上的记录为准（排期依据）… 见 ADR-0002」（`:3-4`）。按当前代码，ADR-0002 的依据不可能来自这个测试。
  - `test_explain_indexes.py:7` 有 marker，但不在 CI 清单里；执行输出没有逐文件结果，所以本轮是否跑到它 **[未验证]**（命令 3）。
- **后果**：「有真库测试」的说法和实际执行对不上；新加的真库测试只要忘了 marker 或忘了改 ci.yml 就会被静默跳过。
- **修复方案**：
  1. 所有真库测试统一使用 `pytestmark = pytest.mark.mysql_fidelity`，在 conftest 里用 `pytest_collection_modifyitems` 按开关统一跳过，删掉各文件自带的 `_FIDELITY` 和 `skipif`；
  2. CI 改为 `pytest -m mysql_fidelity`，同时加 `--strict-markers`；
  3. 加一条元测试：凡是引用了 `MYSQL_FIDELITY` 或 `mysql_fidelity_enabled` 的测试文件必须带 marker；
  4. 修好 ddl_drill 的 fixture 导入，并对照 ADR-0002 重新产出一次记录，或在 ADR 里注明当时的依据来源。
- **应补的测试或验收**：上述元测试；CI 日志加 `-rA`，列出保真通道的逐项结果。

### QA-4 没有基于运行中构建的验收流程和记录：唯一的 e2e 全桩、只覆盖租户视角、不在 CI；人工运行证据只有超管视角，两者没有交集；「真实后端 × 租户负责人」旅程从未走通
- Dimension: 9 / 3 | Severity: **major** | 工作量: M–L | 核验方式: 静态 + 截图 + 已记录执行
- **现象**：
  - e2e 只有一条用例（`smoke.spec.ts:79`），拦截了全部 `/api/v1/**`（`:18-77`），身份是租户负责人且非超管（`:29-35`）；official 没有任何 e2e。
  - **更正并确认 R5 QA-12 的待验证项**：CI 的 frontend-build 任务（`ci.yml:161-216`）没有任何 e2e/playwright 步骤，所以 e2e 不在 CI 里运行。
  - manager 的运行期记录只有「平台超管」视角（`ui-runtime-summary.md:3`，packet 也写明没有租户负责人截图）。
  - Glob `**/*{验收,accept,acceptance,release}*.md` 除 docs/claims.md 外没有结果；`.sdlc/**/state.yaml` 也没有结果。没有任何发布或功能的验收记录。
- **运行期缺陷样本（截图已核实）**：
  - 超管在 `/usage` 能看到「去结账」按钮（admin_usage-1440.png）；
  - 点进 `/billing/checkout` 后，页面发出 `GET /api/v1/billing/checkout?product=plan_pro`，返回 **400**（`ui-runtime-summary.md:49`）；
  - 页面只剩一行「超管不能代企业支付」，其余空白（admin_billing_checkout-1440.png）。
  - 业务规则本身没错，问题在于入口按钮把超管引向一条注定失败的死路，还发出了一次必然失败的请求。按身份划分的页面验收可以直接发现这类问题，而 Checkout.test.tsx 这类整体 mock 服务层的单测发现不了。
- **侧面证据**：本地开发库的 product_events 里没有注册、结账、支付类事件（`devdb-readonly.txt:36-50`），orders 只有 1 行（`:53`）。付费转化这条核心变现路径，连本地都没有被完整走过。
- **后果**：「官网注册 → 登录 → 定价 → 结账 → 支付回调 → 订阅生效 → 配额变化」这条变现路径，以及「首个采集任务 → 看到结果」这个价值兑现时刻，都没有运行期证据。发布是否可交付无法判断。
- **修复方案**：
  1. 定义 5 条旅程：J-1 自助注册到首个任务出结果；J-2 定价、结账、沙箱支付、订阅生效、配额变化；J-3 市场订阅和安装；J-4 超管管理租户；J-5 中转 token 调用到用量入账。
  2. 在 Playwright 里新增一个 `live` project，对接真实后端（compose 起 mysql/redis/backend，前端用 `serve -s build`）。用已有的内部夹具租户接口 `POST /api/v1/admin/internal-fixture-tenants`（`module-inventory.md:26`）做种子，产生的事件会带 `is_internal_fixture` 标记，不会污染指标。
  3. 桩模式的 smoke 保留在 PR 门禁里。
  4. 每次发布产出一份 `docs/releases/<version>/acceptance.md`：旅程、构建 sha、身份、截图或 trace、结论、签字人。
  5. 前端对超管隐藏或禁用「去结账」按钮，并去掉那次必然失败的请求。
- **应补的测试或验收**：J-1 到 J-5 的 live e2e；「身份 × 页面」可达性快照（匿名 / viewer / operator / 负责人 / 超管）。

### QA-5 发布在仓库里不是一个可识别的事件：没有版本演进、tag、CHANGELOG、CD 和环境晋级；CI 构建的镜像构建完就丢弃
- Dimension: 1 / 7 / 8 | Severity: **major** | 工作量: M | 核验方式: 静态
- **现象**：
  - 版本号三处都固定为 0.1.0：`pyproject.toml:3`、`package.json:3`、`frontend/admin/package.json:3`；
  - 没有 CHANGELOG（Glob 无结果）；
  - `.git/refs/tags/` 为空，也不存在 `.git/packed-refs`，即仓库一个 tag 都没有；
  - `.github/workflows/` 下只有 ci.yml，没有 release 或 deploy 工作流；
  - `ci.yml:228` 执行 `docker build ... -t auto-agents-backend .`，既不打 sha 或版本 tag，也不推送；
  - `config/prod/` 有 6 个 yml，但没有任何流水线以 `APP_ENV=prod` 或 dev 部署过。
- **与第一轮的关系**：R6 QA-10 只指出 deploy.md 文档缺失；这里指出的是**机制**缺失。
- **后果**：无法回答「线上跑的是哪个版本」；回滚没有可以指向的上一个制品；事故没法和变更对应起来；「日志即证据」原则在发布这一环断了。
- **修复方案**：
  1. 版本号只保留一个来源（git tag 或构建参数 `APP_VERSION`），并在 `/api/v1/health/deep` 和前端页脚输出；
  2. 近期提交已基本采用约定式格式（例如 `chore(agents):`、`docs(agents):`），可以接 release-please 或 git-cliff 自动生成 CHANGELOG；
  3. 新增 `release.yml`：推送 `v*` tag 时构建并推送 `<registry>/backend:<sha>` 和 `:vX.Y.Z`，先跑一次性迁移 job，再滚动上线；dev 环境自动部署，prod 走 GitHub Environments 人工审批；上线后跑冒烟（deep）；
  4. 回滚方式为切回上一个镜像 tag，数据库部分遵守 QA-2 的边界。
- **应补的测试或验收**：发布检查清单（见文末闭环方案 G4）；每次发布的 release 记录。
- 部署目标的选择见 Q-1，版本方案见 Q-2。

### QA-6 功能开关没有发布策略：prod 配置不覆盖任何开关，测试默认打开能力市场，也没有开关清单、owner 和到期日
- Dimension: 7 / 8 | Severity: **major**（取决于 Q-4 的答案，可能降为 minor） | 工作量: S–M | 核验方式: 静态
- **现象**：
  - 默认配置里有 20 多个 ENABLED 类开关（`module-inventory.md:267-291`）；
  - 在 `config/prod/*.yml` 里 grep `ENABLED` 无结果，只有 `settings.yml:3 DEBUG: false`，所以 prod 全部继承默认值：能力市场 `POWER_MARKET.ENABLED: false`（`power_market.yml:3`）、LiteLLM、中转调度和探针全关；
  - 测试通过 autouse fixture 默认**打开**能力市场（`conftest.py:468-477`）；
  - 本地开发库有大量市场事件（`devdb-readonly.txt:38-48`）。
- **后果**：被测试和被走查过的配置，与 prod 实际生效的配置不一致。「四柱」之一的能力市场在 prod 默认是关的，是否要开、谁来开、什么时候开，都没有成文。已有的运行时开关接口 `GET/PUT /api/v1/admin/power-market`（`module-inventory.md:17-18`）是否持久化、重启后是否保留 **[未验证]**。
- **修复方案**：
  1. 新建 `docs/ops/feature-flags.md` 或 `config/flags.yml` 注册表，每个开关写明 owner、默认值、各环境取值、上线条件、到期或删除日期；
  2. 在 arch.sh 里加一条规则：出现未登记的 `ENABLED` 键就判红；
  3. 发布检查清单里加一项「本次发布的开关取值 diff」；
  4. 按 prod 配置跑一轮冒烟（`APP_ENV=prod` 加测试口令），验证默认关闭路径可用。
- **应补的测试或验收**：参数化冒烟（`POWER_MARKET.ENABLED` 取 on 和 off），分别验证官网市场页与公共 API 的降级表现。

### QA-7 风险驱动覆盖缺口：钱进来的入口和权限核心模块覆盖率最低
- Dimension: 3 / 4 | Severity: minor（作为 P1-2 的补充，精确到文件和分支；只要涉及支付回调就按 major 排期） | 工作量: M | 核验方式: 已记录执行
- **现象**（`pytest.txt`）：
  - 外部支付回调入口 `backend/app/external_api/v1/payment_gateways.py` 覆盖率 **30%**（`:116`），整个仓库只有 4 个端点测试（`test_payment_gateways_notify_endpoints.py`）；
  - `wechat_gateway.py` 50%（`:212`）；
  - `payment_notify_service.py` 58%（`:213`）；
  - `rbac_service.py` 47%（`:240`）；
  - `tenant_admin_service.py` 51%（`:255`）；
  - `user_service.py` 56%（`:259`）；
  - 应用启动和生命周期 `backend/app/__init__.py` 28%（`:73`），后台消费者和调度器的启动只能靠运行期冒烟验证。
- **后果**：支付回调的签名错误、金额不一致、重复通知幂等、未知订单、渠道禁用等分支是否正确，没有测试证据。这正是最容易造成资金或权益错误、又最难事后修复的地方。
- **修复方案**：为回调入口补一张分支表（签名无效 → 拒绝且不改订单；金额不符 → 拒绝并告警；同一通知重复 N 次 → 只履约一次；并发重复通知 → 在保真库上验证行锁或唯一约束），覆盖率下限按文件设置：支付和 RBAC 不低于 80%，与改进方案 P1-2 对齐。应用启动路径由 QA-4 的 live 冒烟覆盖。
- **应补的测试或验收**：上述分支用例，其中「并发重复通知」放进保真通道。

### QA-8 跳过、重试和提前终止都在掩盖失败面
- Dimension: 3 | Severity: minor | 工作量: S | 核验方式: 静态 + 已记录执行
- **现象**：
  - 41 个 skipped（`pytest.txt:364`）没有分类，也没有上报；
  - 永久跳过的死测试：`test_newapi_services.py:157,250,395`；
  - 已知缺陷以 skip 形式存在（`test_alembic_baseline.py:136-141`），没有工单和到期日；
  - CI 主测试加了 `-x`（`ci.yml:75`），第一处失败就停，失败面被截断；
  - Playwright 在 CI 下 `retries: 1` 且 `trace: 'on-first-retry'`（`playwright.config.ts:10,14`），flaky 用例会被记为通过；
  - jest `testTimeout: 120000`（`admin/package.json:96`），CI 注释自认前端测试要跑 20–30 分钟（`ci.yml:164`），都是慢测试和潜在 flaky 的信号。
- **修复方案**：
  1. CI 加 `-rs` 输出跳过原因；维护跳过白名单（原因、owner、到期日），出现白名单外的新 skip 就判红；
  2. 删掉 3 个死测试；
  3. 用缺陷形式存在的 skip 改为 `xfail(strict=True, reason=<工单>)`；
  4. CI 去掉 `-x`；
  5. Playwright 在 CI 统计 flaky，如果版本支持 `failOnFlakyTests` 就开启；
  6. jest 输出最慢的 20 个用例，作为治理基线。

---

## Dimensions checked
1. 标准符合：有问题。发布、验收能力缺失（QA-4、QA-5）；真库验证裁定 IMPL-QA-5 没有落地（QA-3）；prod 开关与测试配置不一致（QA-6）。
2. 标准质量：有问题。没有 GWT 输入，按「测试断言本身是否可证伪」来判断：t24 捕获了错误的异常类型（QA-1）；DDL 演练测试无法运行（QA-3）。
3. 证据有效性：有问题。保真测试执行记录显示 5 个失败、1 个错误（QA-1）；EXPLAIN 证据失真；e2e 全桩且不在 CI（QA-4）；41 个 skip、`-x`、重试都在掩盖失败（QA-8）。执行记录本身的命令和退出码是原样记录的，这一点合格。
4. 安全：有问题。没有新增安全门禁类发现（依赖审计、授权矩阵第一轮已报）；支付回调的签名和幂等分支覆盖不足（QA-7）。
5. 性能：有问题。索引 EXPLAIN 验证因测试收尾失败而无效（QA-1）；前端测试 20–30 分钟（QA-8）。运行时查询性能不在本切片，不适用。
6. 契约一致性：有问题。回滚下限文档写 037、实际是 048（QA-2）；R5 QA-12 关于「e2e 是否在 CI」的疑问已确认为否（QA-4）；ADR-0002 与 DDL 演练测试不一致（QA-3）。
7. 合规：有问题。「配置即代码」：prod 开关取值没有版本化的决定（QA-6）；「日志即证据」：发布没有记录（QA-5）。机械红线第一轮已检查，本切片没有新增。
8. 边界：有问题。越过 048 的回滚（QA-2）；超管进结账死路（QA-4）；开关的开关两种状态（QA-6）；重复或并发支付通知（QA-7）。
9. 产品价值与体验：有问题。构建已经存在，按「最终审查」档位判断：官网 8 个页面、后台 26 个页面都能加载，没有页面级错误（`ui-runtime-summary.md:5-12,38-60`，只有 antd 废弃告警），这一点值得肯定。但注册到首个结果、定价到支付到生效这两条核心价值路径没有任何运行期走查；没有租户负责人视角的截图；超管的结账入口是死路（QA-4）。设计 QA 和增长宣称的核验没有记录（claims 锚点测试缺失已在 R7-11 报告）。

## Strengths
1. 保真通道的隔离和防误伤设计扎实：每个测试建独立 schema；重定向后先断言库名，失败即中止，防止跑到真实库（`test_alembic_baseline.py:27-66`，`:58`）。
2. 存在正确的迁移往返写法可以直接照抄：`test_t14_migration_046.py:96-113` 钉住 045/046，在同一轮真库执行中通过。
3. 跳过语义诚实：外网夹具不可达时明确写「skip ≠ GWT-18.1 pass」（`test_spider_min_loop.py:44-56`），不把跳过记成绿。
4. 契约防漂移链路完整：OpenAPI 路由 golden 测试（`test_openapi_routes_golden.py`）加上 CI 里 dump 和 codegen 后再构建前端（`ci.yml:195-201`）；前端单测基础比较广（admin 约 55 个测试文件、official 15 个；方案记录 391 加 90 条全过）。
5. 已经具备暗发布的基础设施：LiteLLM 有影子或只读对比器开关（`module-inventory.md:280-283`，并有 `test_litellm_shadow.py`），能力市场有运行时开关接口（`module-inventory.md:17-18`），可以直接作为分阶段发布的抓手。

## Improvement themes
- **T1 让保真层可信**（QA-1、QA-3）。目标：所有真库测试按 marker 自动选中、全绿并在 CI 执行；往返测试钉版本；没有死测试。顺序：钉版本并修正异常断言（S）→ 修 ddl_drill 导入（S）→ marker 统一加元测试（S）→ CI 改 `-m mysql_fidelity -rA`（S）。
- **T2 回滚边界成文并机械化**（QA-2）。目标：真实回滚下限经过实测并写进 deploy.md 和迁移门禁；上线顺序固定为「迁移 job → 新代码」。顺序：048 降级改为 `pass` 并补往返用例（S）→ deploy.md 的迁移策略章节（S）→ db_migrations 门禁加入下限检查（S）。
- **T3 运行中构建的旅程验收**（QA-4、QA-7）。目标：J-1 到 J-5 的 live e2e 在 main 和夜间跑；每次发布一份验收记录；支付回调分支全覆盖。顺序：定义旅程和身份（S）→ compose 化的 live 环境加夹具租户（M）→ 先做 J-2 和 J-1（M）→ 支付回调分支（M）→ 其余旅程（M）。
- **T4 让发布成为可识别事件**（QA-5、QA-6）。目标：每次发布有 tag、CHANGELOG、带版本的镜像、迁移 job、dev 自动部署、prod 审批、上线后冒烟和记录；有开关注册表。顺序：版本来源与 `/health/deep` 输出版本（S）→ release.yml 的构建推送部分（M）→ 迁移 job 和 dev 自动部署（M）→ prod 审批加回滚剧本（M）→ 开关注册表加门禁（S）。
- **T5 测试卫生**（QA-8）。目标：跳过有白名单、flaky 有统计、CI 能看到完整失败面。顺序：`-rs` 并去掉 `-x`（S）→ 删死测试并把缺陷型 skip 改成 xfail（S）→ Playwright flaky 策略（S）。

---

## 最小可行的「测试 → 验收 → 发布」闭环与门禁

| 门禁 | 触发 | 必须全部通过 | 产物 |
|---|---|---|---|
| **G1 PR 门禁**（阻断） | 每个 PR | ruff；pytest 带 `--cov`（R6 QA-2）且不加 `-x`、带 `-rs`；`pytest -m mysql_fidelity -rA`（QA-1、QA-3 修复后）；OpenAPI golden 和 codegen；前端单测和构建；桩模式 e2e smoke；arch 和 db 门禁 | junit、coverage.xml |
| **G2 集成门禁**（阻断合入 main 或打 tag） | 合入 main、夜间 | compose 启动 mysql、redis 和 backend → 空库 `alembic upgrade head` → `smoke.sh` 改探 `/health/deep`（R6 QA-8）→ live Playwright 跑 J-1、J-2（逐步扩到 J-5），用夹具租户 | Playwright trace 和截图 |
| **G3 验收** | 发布候选 | G2 产物自动汇总进 `docs/releases/<ver>/acceptance.md`；本次改动涉及的旅程由 pm 或设计做一次人工走查（按身份截图）；claims 锚点核验；开关取值 diff（QA-6） | 签字的验收记录 |
| **G4 发布** | 推送 `v*` tag | 生成 CHANGELOG → 构建并推送 `:sha` 和 `:vX.Y.Z` 镜像 → 迁移 job（只允许 expand；contract 延后一个版本）→ dev 自动部署 → prod 人工审批 → 上线后跑 deep 冒烟加一个鉴权读接口 | release 记录（版本、sha、迁移区间、开关、签字人） |
| **G5 回滚与观察** | 上线后 30 分钟 | 健康检查和错误率观察；回滚 = 切回上一个镜像 tag；数据库只前滚修复，且不越过实测下限（QA-2） | 事故或回滚记录 |

落地顺序：先做 G1 的保真修复（S），然后 G4 的最小版本（版本号、tag、推送镜像、迁移 job，M），然后 G2 的 J-2 和 J-1（M），最后 G3 模板（S）和 G5 剧本（S）。

---

## 待确认问题

- **Q-1（战略，待确认）部署目标与 CD 范围**。A：单机 docker compose，由 GitHub Actions 通过 SSH 或自托管 runner 部署；B：现阶段只构建并推送带版本的镜像，部署手工执行但必须有发布记录；C：暂不建 prod，先做 dev 自动部署。**推荐 B，再过渡到 A**：compose 已有生产化注释，B 的成本最低，而且马上能得到可回滚的制品。
- **Q-2（战略，待确认）版本方案**。A：SemVer 0.x 配合 release-please；B：CalVer（YYYY.MM.N）。**推荐 A**：提交已基本是约定式格式，可以直接自动生成 CHANGELOG。
- **Q-3（战略，待确认）live e2e 的频率与成本**。A：每个 PR 都跑；B：PR 只跑桩模式 smoke，live 旅程在合入 main、夜间和打 tag 前跑。**推荐 B**：前端任务已经要 20–30 分钟（`ci.yml:164`）。
- **Q-4（战略，待确认）能力市场在 prod 的开关决定和验收签字人**。能力市场是否随下一个版本在 prod 开启？发布验收由谁签字（pm、设计、operator 单人）？推荐由 operator 明确给出答复并写进开关注册表和验收模板；在此之前按「prod 默认关」如实记录。

## 需要 manager 执行的验证命令
1. QA-1 确认 EXPLAIN 用例的失败行：`MYSQL_FIDELITY=1 MYSQL_FIDELITY_HOST=127.0.0.1 MYSQL_FIDELITY_USER=root MYSQL_FIDELITY_PASSWORD=<pwd> uv run pytest -q -rA --tb=long backend/tests/test_db_behavior_loop.py`。预期失败行是 `:143` 或 `:167` 的降级到 base，而不是 `:139` 或 `:162` 的断言。
2. QA-2 实测回滚下限：在一次性保真 schema 上写一个临时测试（重定向方式照抄 `test_alembic_baseline.py:27-66`），依次执行 `command.upgrade(cfg,"head"); command.downgrade(cfg,"047")` 和 `command.downgrade(cfg,"030")`，记录异常类型；然后把 048 的 `downgrade()` 临时改为 `pass` 再跑一次。跑完删除临时测试，并还原工作区。
3. QA-3：`MYSQL_FIDELITY=1 ... uv run pytest -q -rA backend/tests/test_explain_indexes.py backend/tests/test_t42_fidelity_queue_depth.py`；再执行 `MYSQL_FIDELITY=1 uv run pytest --collect-only -q -m mysql_fidelity backend/tests | grep -c t42`，预期输出 0，证明按 marker 选择会漏掉它。
4. QA-4：用租户负责人身份走一遍：官网 `/register` 自助注册 → admin 登录（不勾「记住我」，只点菜单导航）→ `/pricing` → `/billing/checkout`，逐步截图并记录 `/api/` 返回码；之后只读查询 `product_events` 新增的事件。
5. QA-5：`git tag -l | wc -l`；`git log --oneline | wc -l`。
6. QA-7：`uv run pytest -q --cov=backend.app.external_api.v1.payment_gateways --cov=backend.services.payment_notify_service --cov-report=term-missing backend/tests/test_payment_gateways.py backend/tests/test_payment_gateways_notify_endpoints.py backend/tests/test_fr_u33_notify.py`
7. QA-8：`uv run pytest -q -rs backend/tests 2>&1 | grep SKIPPED | sed 's/:[0-9]*:/:/' | sort | uniq -c`

---

## Return
- **输出路径**：请 manager 把本报告保存到 `/Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/F7-test-accept-release/05-review/findings.md`，之后运行 success_check：`python3 /Users/xuyun/.zcode/local-plugins/sdlc-workflow/scripts/workflow.py check-task --role reviewer --stage review --task G-fresh --root /Users/xuyun/auto_agents/.sdlc/_review/2026-09-27-project-audit-r2/F7-test-accept-release`。
- **摘要**：8 条（major 6、minor 2，没有 blocker）。核心结论：保真测试要先修再进 CI；数据库回滚下限实为 048；验收与发布机制整体缺失。文中给出了 G1 到 G5 的最小闭环方案。
- **Decisions**：我没有替 owner 做任何决定。报告写法上的取舍：QA-6 暂定 major，Q-4 回答后可能下调；QA-7 暂定 minor，但支付回调部分建议按 major 排期；QA-2 中降到 047 或 030 的行为标为 [未验证]。
- **Open questions**：Q-1 到 Q-4（全部为战略问题，待确认，见上文）。没有按默认值替你决定的运营类问题。
- **Product-delta**：无（产品层 docs/product 尚未建立，不适用）。
- **Lessons**（已被记录执行或静态证据证实）：
  1. 迁移往返测试必须钉住被测版本（升到 X、降到 X-1），不能先升到 head。一旦链上出现不可降级的合并迁移，基于 head 的往返测试会全部失效（`mysql-fidelity-full.txt` 与 `test_t14_migration_046.py` 的对照）。
  2. `pytest.raises(RuntimeError)` 也会捕获 `NotImplementedError`（子类），断言要写精确的异常类型（`test_t24_migration_042.py:102`）。
  3. 用自定义环境变量加 `skipif` 做开关、不打 marker 的真库测试，会逃过按 marker 的选择（`test_t42_fidelity_queue_depth.py:31-36`）。
