# QA 测试体系二轮评估 — auto_agents（2026-09-06）

评估人：SDLC 测试工程师（只读）。数据来源：全量 pytest 实测（`--durations=60`，1087 passed / 12 skipped / **92.03s**，本机 arm64）、全部 12 个 b1x+t10 清剿文件 AST 函数级断言统计、全库 566 个测试函数薄用例扫描、conftest/stubs/CI workflow 深读、前端 7 个测试文件抽样、git 增速台账。未修改任何代码/测试。

## 一、总体判断

**一轮清剿把"路由零覆盖"这个数量问题解决了，二轮的主要矛盾已转移为两个质量问题：① 清剿用例是"接线验证"级而非"契约验证"级——206 个 b1x/t10 函数中 52 个（25.2%）为薄用例，且 401/403 断言口径在 b1a/b1b（带 code 字段）与 b1c/t10（仅 status_code）之间漂移；② 时长经济学亮红灯——92s 基线 + 约 0.2s/用例的清剿型边际成本下，按 +200 用例/周增速，2-4 周内必破 3 分钟红线，而最大单块瓶颈（auth 域 bcrypt + 每用例建库 ≈ 30-40s）与 xdist 解耦方案均已就绪待执行。**

抽查 12 个清剿文件的全部正面路径用例质量高于上轮基线：assert 密度 3.0/用例（628 断言/206 用例），b1b 三文件副作用查库断言达 8-18 处/文件，schedules 校验参数化 5 组等价类（缺字段/空串/cron 4 段/超长/非法分钟位），多处"缺陷修复→用例转正"注释（F-B1b-01/02 可追溯）。这不是空心矩阵——是**头尾不均**：b1b 口径已达范本级，b1c_newapi（0 处副作用断言）与 external_api（401 系列上轮点名至今未收敛）拖后腿。非功能面：EXPLAIN 断言框架已建成但停滞在 1 个试点查询，026/027 索引治理的人工证据（key_len 87）未回填自动化；性能基准/并发压测/内存防护四项空白经评估均为"明确不建"或"延期建"（理由见 F7），唯一该投入的是 EXPLAIN 扩容与虚拟时钟注入。

## 二、FINDINGS（按严重度排序）

### R2-F1. 清剿面薄用例 52/206（25.2%），401/403 断言口径在文件族间漂移 — major
证据：AST 函数级扫描（口径：零断言，或全部断言仅为 status_code 且无 body/副作用/mock 断言）——b1x+t10 共 206 函数中 52 个薄，其中 43 个为单断言 401/403/404 用例。漂移实例：b1a_admin `test_list_tenants_anonymous_401` 断言 `code == "AUTH_FAILED"`，而同型用例 b1c_capabilities 9 个、b1c_spiders 22 个、b1c_newapi 5 个仅断 status_code；external_api 401 系列 6 个（上轮 F5 点名项）至今未收敛。b1c_newapi_channels 全文件 13 用例 0 处副作用断言（对照 b1b_schedules 18 处）。全库口径：566 函数中薄 91 个（16.1%），真零断言 3 个（test_b1_rate_limiter 的 3 个实为 pytest.raises 有效断言，非空心）。
建议：① 统一 401/403 断言为「status_code + code 字段」两件套；② 用 b1b 已示范的 `request.getfixturevalue` 角色矩阵参数化模式合并同型用例——43 个单断言用例可压缩为每路由族 1 个参数化用例 × N 方法，用例数反降而断言密度上升；③ b1c_newapi 补 1 条落库副作用用例（channels 配置写后回读）。

### R2-F2. 92s 基线 + 当前增速，3 分钟红线 2-4 周内必破；瓶颈归因明确但未治理 — major
证据：实测 92.03s（1087 passed / 12 skipped）。瓶颈归因（top5，实测+归因）：① **auth 密码哈希域 ≈28s（30%）**——test_auth_login_tenant 6 用例 setup 各 2.0s+（autouse seeded+清 Redis 双 asyncio.run 冷启动）+ test_auth_service 5×0.77-1.54s call + test_auth_utils 0.86/0.90s call，特征与 bcrypt cost 12 吻合；② **db_engine 每用例建库+create_all 分摊 ≈25-40s**——function 级 tmp_path SQLite × 1087 次，top60 中散布 0.19-0.72s setup；③ test_llm_failover 3 用例 6.1s（3.01/2.01/1.00s，无 sleep 命中，疑似真实网络超时路径）；④ test_saas_members 删除系列 8×0.4s；⑤ 清剿 b1x 系 setup 散布。增速：上轮台账 784→1087 为单日冲刺不可持续，按 +200 用例/周、清剿型边际 0.15-0.3s/用例 = 每周 +30~60s → **约 2-4 周后 92s+60~180s 触及 180s 红线**（若新用例含 bcrypt 类则更快）。
建议：① bcrypt 测试因子注入（settings 可配 cost=4，仅 local/test env）——单项预期 -20s；② llm_failover 重试等待注入虚拟时钟/monkeypatch sleep——预期 -5s；③ 两者落地后引入 xdist `-n 4`（前置条件见 R2-F4），预期 92s→30s 内，买回 ≥3 个月增速余量；④ 在 pyproject 固化「单文件 >15s 告警」的时长预算意识（先手工监控即可，不建工具）。

### R2-F3. EXPLAIN 断言框架建成后停滞在 1 个试点，026/027 迁移人工证据未回填自动化 — major
证据：`test_db_behavior_loop.py`（D 线 62）已建成 EXPLAIN 断言框架（access type ≠ ALL 判定函数 + 自证用例 + spider_results 复合索引 1 个真库试点，跑 MYSQL_FIDELITY 通道）；但 026_index_governance.py 注释自述"真库 EXPLAIN 证据见 B3.md——key_len 87 前缀命中"——**本轮 T9/B3 演练产生的关键索引证据仍以人工 markdown 存续，无自动断言守护**。迁移 027（ENUM→VARCHAR）同类无断言。若未来重构删改 `(tenant_id, status, priority)` 复合索引，现有测试全绿（SQLite 不走 MySQL 优化器）。
建议：026 删改的每个关键索引补 1 条 EXPLAIN 断言（每条约 10 行，框架现成，进 fidelity 通道 8 文件口径）；把「迁移文件内 EXPLAIN 证据必须同步存在对应自动断言」写入 db-design skill 自检清单。这是上轮 F3（保真通道）结论的自然延续：通道已扩容，缺的是往里放什么——放"索引语义"而非"表能建"。

### R2-F4. xdist 就绪度中高：隔离底子好，但 test_auth_login_tenant 直连本机 Redis 是唯一硬雷 — minor
证据：就绪面——db_engine 为 function 级 `tmp_path/test.db` 独立 SQLite 文件 + NullPool（conftest.py:231-249）；monkeypatch 全部 function 级；FakeRedis 进程内（stubs.py，语义并集桩）；session 级 app/dependency_overrides 在 xdist 下每 worker 独立实例化；tmp_path 天然 worker 隔离。风险面——① `test_auth_login_tenant.py:64-87`：autouse fixture 直连**本机真实 Redis** 清登录失败计数键（`REGISTER_ATTEMPT_PREFIX testclient` 等 5 键），注释自述"5 次/900s 跨轮次存活"——多 worker 共享键空间时 A worker 清零后 B worker 继续累计 → 429 误报抖动，且无 Redis 的环境下行为依赖 fail-open 语义（测试环境隐依赖）；② settings.set 恢复靠 b1c_skills_jobs 手写 4 处 try/finally（纪律非强制，worker 内泄漏风险同现状）。
建议：开 xdist 前仅两个动作：该文件 Redis 依赖 stub 化（或键前缀加 worker id）；提供统一 `override_setting` fixture 替代手写 try/finally。完成后即可 `-n 4` 灰度（配合 R2-F2）。

### R2-F5. 非功能四项空白评估：一项该建（已列入 F3），三项明确不建 — minor
证据与决策：
- **慢查询回归 → 该建，形态即 EXPLAIN 断言**（F3）：断言访问路径（结构性、零抖动）而非耗时（CI 共享 runner 上耗时断言必然假红）。
- **性能基准（pytest-benchmark 类）→ 明确不建**：当前无 API p95 SLO（监控栈 0 落地，上轮重审已确认）；SQLite tmp 库上的微基准数字无生产参照系；建了只会产出无法归因的绿色数字。
- **并发压测（locust/k6）→ 延期建，触发条件 = SaaS 计费上线**：生产负载模型未知，压测无基线可比；并发正确性已由 17 个幂等/锁用例覆盖（spider repeat_callback、ai_planner concurrent_claim、flush_retry 不双扣）。
- **内存泄漏防护 → 不建**：进程守护由 T11 看门狗 + compose 承担，测试级 tracemalloc 断言 ROI 低且易误报。
- 时间冻结（上轮 F8 遗留）→ 仍未引入 freezegun（grep 零命中），test_saas_signup_expiry 仍用真实 utcnow 构造过期；`datetime.utcnow()` DeprecationWarning 在本轮实测输出中已现（Python 3.13 将移除），随 freezegun 一起换时区安全写法。

### R2-F6. 前端：0 快照、CI 有门禁为好面；admin 页面覆盖 3/25 停滞，E2E 引入缺触发器定义 — minor
证据：admin 测试文件 5 个 = App 冒烟 + usePermission hook + 3 页面（LlmProviders/Members/Skills）/25 页面（12%）；official 2/5（App + SkillsSquare，较上轮 +1）。快照断言 0 个（`toMatchSnapshot` 全库零命中）——7 个文件全部为 testing-library 行为断言（Members.test 的 422 软删冲突用例断言了文案+表单保留+api.post 调用次数，是前端范本）；official SkillsSquare 含 XSS payload 转义安全测试。CI frontend-build job 内 `npm test -w admin/official` 双包有门禁（非仅 build）。Playwright 全仓无。
建议：admin 高危 10 页（登录、租户/成员/角色管理、LLM provider、spider 运行面板、配置）按 Members.test 模板补齐，成本约 0.5 天/页；**E2E playwright 暂不引入**——理由：旅程状态机已被 1087 后端用例覆盖，E2E 增量仅在前后端接线（路由挂载/auth 跳转），而页面组件测试单价低 1-2 个数量级。定义触发器：F-02 类「前后端口径不一致」缺陷再现 ≥2 个，或 admin 页面测试 ≥10 页后接线缺陷仍频 → 引入且只做 2-3 条冒烟旅程（登录→建租户→配 LLM key→发起爬虫）。

### R2-F7. 契约测试：schemathesis 明确不引入；用 20 行 OpenAPI 路由清单 golden 测试替代 — minor
证据：本项目 OpenAPI 已是前端类型 codegen 的单一事实源（CI 内 `dump_openapi.py` + `npm run codegen:api`）——"schema 与实现漂移"已被前端构建层部分守护，这是与常规项目最大的差异点，直接引入 schemathesis 的边际收益被此管线吃掉一半。schemathesis 的剩余增量（畸形参数 500 长尾探测）已被 b1x 清剿的 401/403/404/422 矩阵覆盖主干；全量 fuzz 需 DB 状态管理（stateful 测试对 tmp SQLite 复杂）且误报 triage 成本高。
建议：不引入 schemathesis。改为在 `backend/tests` 加一个「路由清单 golden」测试：从 `app.openapi()` 读 path×method×状态码集合与 golden 文件比对，**新路由必须显式更新清单才能过测试**——把上轮"55 条路由零覆盖"的发现成本从人工 grep 降为零（新路由一提交即红），成本约 20 行。变异测试（mutmut 类）同样明确不建：对 628 断言跑突变 = 数百次全量 × 92s，ROI 劣于先收敛 91 个薄用例（薄用例本身就是存活突变的高发位）。

### R2-F8.（正面基准）b1b 系列用例质量达范本级，应固化为清剿模板 — info
证据：test_b1b_schedules（17 用例 66 断言）——每条 422 校验参数化用例附「零落库」查库断言（拒绝路径副作用双断言）；PATCH 非法 cron 断言「原表达式未被破坏」；DELETE 后同时断库空 + 列表 total==0 双视角；文件头声明断言口径与 schema 出处（platform_core/schemas/spider.py + 统一异常体系）。test_b1a_admin 的 slug 撞名用例断言「库内恰三行 + 互异 + 默认 active」。B5 修复的 4 个缺陷均有"用例由锁定 X 翻转为 Y"的可追溯注释。
建议：把「拒绝路径 = 状态码 + code 字段 + 零落库」三件套、「写路径 = 响应回显 + 查库副作用」双断言写入 .agents/skills/verify 自检清单；后续新增路由测试以 b1b_schedules 为模板（替代上轮建议的 test_saas_members，后者偏租户域特化）。

### R2-F9. 12 skipped 全部为 mysql_fidelity 标记基建，fidelity 通道"标记面"与"清单面"双轨易漂移 — info
证据：本地 12 skipped = 6 个文件内 `pytest.mark.mysql_fidelity` 用例（mysql_fidelity/alembic_baseline/t10_fix_regressions/saas_ddl_drill/db_behavior_loop）；CI 通道按**文件清单**跑 8 个文件（ci.yml 硬编码路径）——两套口径：标记面含 saas_ddl_drill 但 CI 清单未含；清单含 saas_members/auth_login_tenant/admin_users_crud/saas_rbac_deep 但这 4 个未打标记（本地以 SQLite 全速跑）。双轨目前一致靠人工维护，扩容时（F3）易漏。
建议：CI 改为 `pytest -q -m mysql_fidelity backend/tests`（按标记收集）或反之全清单化，二选一收敛为单轨；扩容 EXPLAIN 断言前先收敛，避免新资产进错通道。

## 三、投资方向排序（3-5 项，按 ROI）

| # | 方向 | 成本 | 收益 | 前置 |
|---|------|------|------|------|
| 1 | 时长治理：bcrypt 测试因子 + llm_failover 虚拟时钟 → xdist -n 4 灰度 | 1-2 天 | 92s→<30s，买回 3 个月增速余量 | R2-F4 两动作（Redis stub 化 + settings fixture） |
| 2 | 薄用例收敛 91→<30：401/403 角色矩阵参数化 + code 字段统一 + external_api 补断言 | 1 天 | 消除口径漂移；用例数反降约 30-40 个 | 无 |
| 3 | OpenAPI 路由清单 golden 测试 | 0.5 天 | 新路由静默裸奔在提交时即红（防 55 路由问题复发） | 无 |
| 4 | EXPLAIN 断言扩容（026/027 索引语义回填）+ fidelity 通道单轨化 | 1 天 | 索引回归自动化；通道防漂移 | 无 |
| 5 | admin 高危 10 页组件测试（Members 模板） | 5 天 | 页面覆盖 12%→40%，E2E 触发器挂钩 | 无 |

## 四、边界与遗留

- 本评估的薄用例判定为机械口径（AST 断言形态），不覆盖"断言存在但弱"（如仅断 `"value" in resp.text`），实际薄弱面略大于 91。
- test_llm_failover 3s 归因（真实超时路径）为推断，未逐行验证 `_patch` 内部实现。
- 未评估 scrapy/ 侧测试（test_scrapy_* 6 文件在收集范围内但未深读）；上轮亦未覆盖，保持一致。
- 上轮 F2（RBAC 守卫兜底）本轮观察到清剿用例已系统性补 401/403 矩阵（b1x 全覆盖），该项确认收敛，不再单列 finding。
