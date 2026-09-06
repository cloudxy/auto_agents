# QC 深层审查报告（/Users/xuyun/auto_agents，2026-09-06）

> 注：qc 角色子代理为只读工具面（Read/Glob/Grep），本文件由编排器代为落盘，内容为该子代理交付原文，未改动。

## 总体判断

该仓库门禁体系表面完备度高（5 阶段 CI + pre-commit + 4 个门禁脚本 + 约 1030 个后端用例），后端核心测试抽样质量真实偏高（真库副作用断言、租户隔离读写注入、alembic 与 create_all 双源对拍、方言回归均有实证）。但以"明天签字对外放行"的口径衡量，放行依据在四个维度上不成立：**证据维度单一**（唯一信号是全绿，无覆盖率/类型/安全/e2e/启动演练）、**环境保真双层弱化**（默认通道 SQLite+FakeRedis+全 mock session，MySQL 保真通道是手工白名单且有测试永久 skip）、**可追溯链断裂**（测试与门禁脚本大量引用的工单/ADR 存在于被 gitignore 的本地目录）、**静态防线刻意极弱**（lint 仅 E9+F401，无类型检查/安全扫描/依赖审计，且 grep 型门禁自身无测试、已自证发生过两次假绿）。结论：**有条件放行**——内部使用/灰度可放行；对外放行前必须补齐问题 1/2/3/5 所列机制。

## 深层次问题清单（按严重度排序）

### 1. MySQL/Redis 保真是 opt-in 白名单而非默认通道，部分保真测试在 CI 永久 skip
**严重度：高**

**证据**：`backend/tests/conftest.py:247` 默认引擎 `sqlite+aiosqlite`；`conftest.py:45-56` 全局兜底 mock session（`execute` 恒返回 None/空列表）。`.github/workflows/ci.yml:78-87` MySQL 保真通道为硬编码 8 文件清单（约 39 用例），主通道约 996 用例运行在 SQLite/FakeRedis/mock 上。`test_saas_ddl_drill.py:19`、`test_db_behavior_loop.py:21` 带 fidelity 门控但不在 CI 8 文件清单内——主 run skip、保真通道不跑，**CI 上从未执行过**。`stubs.py:56-75`：FakeRedis `set(ex=)` 接受参数但不实现 TTL，`expire()` 不真过期——限流/分布式锁/LLM 冷却类测试在"永不过期"的 Redis 上验证。门控习语三种并存且不同源（pytestmark / skipif / fixture 内 skip），marker 与 CI 文件清单无机械关联。

**为什么深层**：MySQL 方言、Redis TTL/原子性、连接池行为只在白名单内验证；新增测试默认落入弱通道，进保真通道需人工改 CI 清单——保真覆盖占比必然持续下降；skip 静默无预算告警，"写了但从不跑"的测试资产不可见。

**解决方案**：① CI 保真通道改 `uv run pytest -q -m mysql_fidelity backend/tests`（marker 单一事实源），补齐 marker、统一习语；② CI 加 Redis service 容器，Redis 类测试连真 Redis，FakeRedis 退役或仅保留故障注入用途；③ CI 摘要强制输出 skip 清单，skip 超基线（>5%）即红。

### 2. 放行证据不完备：全绿是唯一信号，零覆盖率度量、无变更覆盖门禁
**严重度：高**

**证据**：`pyproject.toml:14-20` dev 依赖无 pytest-cov；`ci.yml` 五 job 无 coverage 步骤；jest 无 coverageThreshold；无 diff-cover。

**为什么深层**：用例数量不等于覆盖充分性；没有度量，回归防线覆盖萎缩不可见。CI 绿只证明"已写的测试都过"，不证明"该测的被测了"。

**解决方案**：① CI 加 `--cov=backend --cov=platform_core --cov-report=xml`，jest 加 `--coverage`，报告归档 artifact；② PR 引入 diff-cover（变更行覆盖 <70% 即红）；③ 放行附"覆盖率 + skip 清单 + 变更文件→测试映射"三件证据。

### 3. 静态防线刻意极弱且盲区同向叠加：无类型检查、无安全扫描、无依赖审计
**严重度：高**

**证据**：ruff `select = ["E9", "F401"]`；无 dependabot/codeql/mypy/bandit/pip-audit/npm audit；`check-arch.sh:114-116` 自认 R11 盲区；R2 明文密码正则只匹配双引号。

**为什么深层**：mock 密集测试 + 无类型检查 → None 传播/AttributeError 只有"恰好有真库测试"才被抓——各防线盲区同向（都押注"测试恰好覆盖"）。依赖供应链零已知漏洞防线。

**解决方案**：① `pip-audit`、`npm audit --audit-level=high`、dependabot（weekly）进 CI；② ruff 分三批启用规则组，PR 先对 diff 生效；③ mypy 渐进基线从 services 契约层起步。

### 4. 可追溯性断链：需求/工单/ADR 全在被 gitignore 的目录，修复→回归沉淀无机制强制
**严重度：高**

**证据**：`.gitignore:77-79` 忽略 `.scratch/` 与 `docs/`；而测试与门禁脚本引用"qa findings F1/F4""工单 04""ADR-0002"等工件均不入库；回归沉淀仅靠命名自觉，无拦截机制。

**为什么深层**：放行者无法验证"这条测试在验证哪条验收标准"；换人/换机后回归用例退化为无语义断言。

**解决方案**：① 验收与决策工件入库（取消 docs/ 一刀切 ignore 或迁至受控目录）；② PR 模板加"根因 + 回归用例"必填，CI 校验 fix/bug 类 PR 必须触及 backend/tests；③ 建立验收标准→测试用例 ID 映射清单。

### 5. 部署路径从未端到端演练：docker 阶段只验证"能 build"，不验证"能启动、能连库、能跑迁移"
**严重度：中**

**证据**：`ci.yml:165-175` 仅 `docker compose config --quiet` 与 `docker build`；唯一启动验证是 check-arch.sh 里顺手 `create_app()`（stderr 被吞）；`alembic upgrade head` 只在 fidelity 测试内部演练。

**为什么深层**：配置装配、DB 连接、迁移执行、健康检查全部推迟到首次真实部署——"CI 全绿但部署起不来"是最典型发布事故形态。

**解决方案**：docker-validate job 加冒烟段（`docker compose up -d backend mysql redis` → 轮询 /health 断言 200 → down --volumes）；空库 `alembic upgrade head` 作为独立 gate。

### 6. 测试隔离建立在共享可变状态上，已有真实事故且治标未治本
**严重度：中**

**证据**：`conftest.py:128-138` session 级 app + autouse 复位；`conftest.py:293-317` 注释自证 llm_client 经 DBManager 绕过 override 直连真库且"会发起真实付费调用"；当前 `_reset_db_manager` 是每测试复位，生产代码仍可触达。

**为什么深层**：隔离保证="每个写 overrides 的人记得复原"，一个新 fixture 忘记清理即复现偶发假绿/假红；测试进程可触达真实付费 API 是成本与数据安全事故面。

**解决方案**：① pytest-socket 禁外连 + LLM base_url 注入死端口（结构保证）；② dependency_overrides 改每测试函数级 app 克隆或快照/还原插件钩子。

### 7. 门禁脚本自身零测试，grep 型规则的假绿是已复发的模式而非个案
**严重度：中**

**证据**：`check-db-migrations.sh:7-17` 自证修复过两类假绿；`check-arch.sh:100-108` R10 只扫 `backend/services/*.py` 单层——14 个子包文件（ai_planner/7、llm_protocol/3、llm_common/2、litellm/3）整体逃过 R10 扫描；SM-7 只识别 downgrade 定义后 3 行内的 pass。

**为什么深层**：门禁脚本是全仓库唯一不被任何测试覆盖的关键代码；同类假绿已发生两轮，未修的同类缺陷此刻仍在产出"绿=通过"假信号——门禁可信度问题比业务缺陷更深层，因为它污染所有其他证据。

**解决方案**：① 每个 check-*.sh 建黄金样例测试（违规+干净 fixture 各 ≥1 组，断言退出码）入 CI；② grep 规则逐步迁 Python AST；③ 扫描范围统一 `git ls-files`/`find -mindepth` 消灭单层 glob 盲区。

### 8. 前端测试金字塔缺失：admin 26 页仅 3 页有测试，无任何 e2e
**严重度：中**

**证据**：仅 Members/Skills/LlmProviders 有 .test.tsx；official 5 页 2 文件；无 playwright/cypress；jest 无覆盖率门槛。

**为什么深层**：admin 是对外运营后台，RBAC/租户切换/配额高敏交互的前端层几乎无自动化防线；后端测试再强也验证不了前端漏传参数/漏渲染错误态。

**解决方案**：① 高频写操作页补最小交互测试；② jest 加 coverage artifact；③ Playwright 一条 e2e 主干道（登录→切租户→核心写操作）入 CI 可选 job。

### 9. CI 运行细节弱化信号质量：-x 首败即停、无并发取消、无 job 超时
**严重度：低**

**证据**：`ci.yml:60` `pytest -x -q`；无 concurrency group；无 timeout-minutes。

**解决方案**：`--maxfail=10 --tb=short`；workflow 加 concurrency 与显式超时。

## 放行结论与门禁指纹

**结论：有条件放行。** 内部使用/灰度发布可放行（后端核心链路测试质量真实、迁移对拍与租户隔离防线扎实）；对外公开放行暂不成立，前置条件为问题 2（覆盖率）、1（保真 marker 化+消除永久 skip）、3（依赖审计）、5（compose 冒烟）四项落地。

**门禁指纹（只读静态审查，执行状态以最近 CI run 为准）**：test / lint / build / migration / arch 五类同 CI 定义。
