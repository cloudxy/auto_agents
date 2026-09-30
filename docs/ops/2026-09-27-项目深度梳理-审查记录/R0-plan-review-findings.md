# Findings — R0-plan-review（汇总改进方案的独立复核）

## Snapshot（manager 计算 sha256）
- 067f207f…8a1c  docs/ops/2026-09-27-项目深度梳理与改进方案.md（被审对象，修订前版本）
- 7 份切片 findings：R1 41c7b36a… · R2 bbe321f9… · R3 5e7bb3c5… · R4 cf3deafc… · R5 4fb4988b… · R6 7a348b01… · R7 6ada2b6c…
- evidence：verify-R1-repro ab1ca5ac… · verify-R2-repro a71337b8… · verify-dynamic ae105673… · verify-manager 6ae4c2d9… · verify-manager-2 a22c965b… · verify-R7 7fab192b… · pip-audit b3f92feb… · db-gates df504589… · arch eef90589…
- 代码快照 HEAD 82259f3；reviewer: sdlc-workflow:reviewer（G-fresh，只读）；packet: ../packets/2026-09-27-2000-review-reviewer-R0-plan-review.md
- 方式：静态检查（完整读方案；Grep 定位 7 份 findings 的 QA 标题/严重度/Q-*；读全部 9 份 evidence；在 explore_roots 抽查 `admin.py` 守卫、`department.py`、`capabilities.ts` FormData 调用、`Dockerfile`、`test_newapi_services.py` skip 标记）；未执行命令、未复现。

**摘要**：12 条（0 blocker / 6 major / 6 minor）。**Verdict：修正后可交付**——6 条 major 均为文字与排期层面修正，无需重审切片。

## FINDINGS
- **QA-1（major，维度 1/3）** §0 把 B4（Python 依赖漏洞）列为 blocker，来源 R6 QA-1 是 major，未写升级理由；§0 与 §1.1 的「4 个 blocker」口径不同（§0 的 B1 合并了 R1 QA-1/QA-2，恰好凑成 4）；pip-audit 只证明装了漏洞版本，不证明可达可利用，「已复现」措辞过度。修正：补升级理由并改合计为 5，或把 B4 移到「本周同时处理的高优先 major」；§0 改为「已确认存在漏洞版本（可利用性未评估）」。
- **QA-2（major，维度 3/6）** 「45 个漏洞」是重复行计数：`pip-audit.txt:5-49` 共 45 行，按 (包, ID) 去重为 27 个不同公告（anyio 2、cryptography 4、protego 1、pyasn1 3、pydantic-settings 1、pyjwt 5、python-multipart 3、scrapy 2、starlette 5、twisted 1）；pip-audit 输出无严重度列，「高危及以上 45 个」指标无数据源；`scrapy PYSEC-2017-83` 无修复版本，`--strict` 的 security job 会永远红。修正：改为「45 条记录 / 27 个公告 / 10 个包」；指标改为不同公告数 27 → 0（带过期日期的忽略清单除外）；按严重度跟踪需另接 OSV/GHSA；P0-4 把 PYSEC-2017-83 写进忽略清单并给理由。
- **QA-3（major，维度 6/9 战略决定）** R3 标为「待确认」的 Q-R3-1（软删唯一键）被写成运营性默认（方案 §6 末），与 D4（`spider_results` 唯一键语义）重叠，P3 又写「逐表确认」——三处矛盾；且 P0-2 ①「INSERT IGNORE、按实际插入行数计数」正是 D4 选项 (a) 原文，事实上先落实了 D4-A。修正：从运营默认删除并入 §6（新增 D14 或并入 D4）；P0-2 注明「止血期临时采用 D4-A 计数口径，D4 定后对齐」；P3 同步。
- **QA-4（major，维度 1/3）** 4 条来源 major 在 P0/P1/P2 无去处：R1 QA-5（配额 60 秒缓存 check-then-act，可突破计费边界，仅在 §7 出现）；R2 QA-13（async 内同步扫描与无超时子进程可卡死事件循环，方案完全缺失，且 ruff ASYNC 看不到）；R4 QA-9（导出器把上游明文 Key 写进工作树，方案完全缺失）；R5 QA-12（前端 HTTP 契约零测试、e2e 桩全放行，只在 S1 表与 P0-3 ② 出现）。顺带 minor：R2 QA-20 指出 R11 也空心，S1 表只写了 R10。修正：R1-5 进 P1（与 P1-3 ③ 原子占位合并）；R2-13 进 P1（`to_thread` + 子进程超时，与冻结事故关联）；R4-9 进 P0-7 或 P1-8；R5-12 进 P1-1 并写明做法；R11 加入 S1。
- **QA-5（major，维度 1/2/9）** P0 实际入选违反自身定义（「已复现或代码确认」）：P0-6、P0-9、P0-7 ②④ 均为 📖；P0-6 可利用前提（平台密钥是否交给过租户）仍未验证，R2 QA-7 自述今天重放是空操作；P0-5（新建 net_guard + 接 3 处 + 换正则引擎）与 P0-6（新建租户密钥体系）是新能力而非热修，与「P0 只做最小止血」矛盾；P0 总量约 5–20 人日压在第 1 周却无人力假设；P1/P2 无完成标准与负责人。修正：P0-6、P0-9 补到 🔍 或降 P1 首批；P0-5 拆分（P0 只留交付 webhook 设置/发送时拒私网的最小守卫，统一 net_guard 与爬虫中间件进 P1）；§5 写人力假设；每个 P0 补一行完成标准。
- **QA-6（major，维度 1/4，修正成本低）** P2-1 把 Node 20 EOL 的目标定为 Node 22，来源是「22 或 24」；按 Node.js 发布计划（外部事实，reviewer 未核实）Node 22 于 2027-04-30 EOL，Node 24 于 2028-04-30 EOL——半年多后再造同一问题。修正：目标改 Node 24 LTS；若必须 22 写明理由并登记 2027-04 前的二次升级。
- **QA-7（minor，维度 3/6）** R2 自报 `1/13/6` 与其 QA 标题不符（实为 blocker 1、major 11〔QA-2~11、13〕、minor 8〔QA-12、14~20〕），方案照抄，合计应为 `4/56/58`；「15 项空心门禁」无清单口径——其中租户槽测试、前端单测、e2e 是测试不是门禁，又漏了 R11（R2-20）、F-5、claims 锚点测试（R7-11）。修正：R2 行改 `1/11/8`、合计 `4/56/58`；S1 拆「门禁 / 测试」两类并补齐，指标改「门禁 N 项、测试 M 项」。
- **QA-8（minor，维度 6）** §0「B1 的彻底修复依赖 D1」与 §6（D1 阻塞 P0-9，而 P0-9 来自 R1-3、不属于 B1）和 §8（P0-1 不依赖任何待决项）矛盾。修正：改为「P0-9 依赖 D1；B1 热修不依赖任何决策」。
- **QA-9（minor，维度 6/9）** 「本季度」排在「第 2 个月」之后，但今天 2026-09-27，Q3 只剩 3 天。修正：统一为相对时间或绝对日期（如 2026 Q4）。
- **QA-10（minor，维度 3）** 部分 ✅/🔍 措辞超出证据：B1 复现只记录状态码、未断言返回数据属于租户 B 与新行 tenant_id=B，身份来自测试夹具而非 `/public/tenant/signup`；S5 把 `.grok/*` 一并标 ✅，但 `verify-R7.txt` 只证实了 `.claude/*`、`.github/*`、`.agents/*`（`.codex/skills/x` 反而未被忽略）；「7 个迁移保真测试从未执行」实为「不在 CI 清单」，且 `test_explain_indexes.py`、`test_db_behavior_loop.py` 不是迁移测试；P0-5「🔍 未找到任何现有校验」的 grep 命令原文未记录。修正：B1 补数据断言或改标记；S5 去 `.grok` 或补记录；改措辞；补命令原文。
- **QA-11（minor，维度 4/7）** P0-2 ① 推荐 `INSERT IGNORE`，MySQL 的 IGNORE 会把截断、非法值、NOT NULL、外键等错误降级成 warning（MySQL 语义，reviewer 未实测）；且 `spider_results` 唯一键不含 alive_flag，被软删的行会让相同内容永远静默进不来——违反「数据质量先于数量」。修正：固定用 `on_duplicate_key_update(id=id)`（只对唯一键冲突生效）并记录重复计数，删掉 INSERT IGNORE 选项，注明与 QA-3 / D4 关联。
- **QA-12（minor/疑问，维度 1/9）** 运营默认「根 Dockerfile 去掉前端构建阶段」后，前端生产交付路径无交代：`Dockerfile:43-44` 把产物拷到 `/app/frontend-dist/`，仓库内无任何消费者（搜 `frontend-dist|FRONTEND_DIST|StaticFiles` 只命中 Dockerfile）。修正：在 P1-8 或 P2-1 补「前端生产托管方式」，若属部署拓扑选择则进 §6。

## Dimensions checked
1. 标准符合 ⚠️ — QA-1、4、12；方案结构完整，但 4 条 major 无去处。
2. 标准质量 ⚠️ — QA-5；P0 只有部分项写了负向测试，P1/P2 无完成标准与负责人；本交付物无 GWT（➖）。
3. 证据有效性 ⚠️ — QA-2、7、10；B2、B3、Dynaconf、F821 更正、guard_meta 证伪都有记录执行或源码支撑，✏️ 用得对（如 F821 8 处确在 `test_newapi_services.py:157` `@pytest.mark.skip` 类内）。
4. 安全 ⚠️ — QA-4（R4-9 凭据外泄、R1-5 计费绕过被丢）、QA-11；方案本身未泄露密钥；P0-1 列的 7 个端点与 `admin.py:136,232,243,261,283,295,320` 的 `require_admin` 逐一对得上。
5. 性能 ⚠️ — QA-4（R2-13 事件循环阻塞未排期）。
6. 契约一致性 ⚠️ — QA-3、7、8、9。
7. 宪法合规 ⚠️ — QA-11（数据质量先于数量）；其余红线引用与 `arch.txt` 一致。
8. 边界 ✅ — P0-1/P0-2 覆盖跨租户、批内重复、重复消息边界；未验证边界已列 §7。
9. 产品价值与体验 ⚠️ — 对 operator 的价值链路清楚（一页结论、13 个决策 + 推荐、依赖排序），但 QA-5、9、3 直接影响 operator 能否放心「按推荐」批；无 UI/截图（➖）。

## Strengths（修改时保留）
每条结论都有可信度标记；manager 主动证伪并更正了 3 个切片的共同误判（F821 不是运行时 NameError），发现并重跑了被污染的 Dynaconf 探针；P0-4 的修复版本与 `pip-audit.txt` 逐项一致；§7 未验证清单诚实；D1–D13 与来源 Q-* 的推荐一一对应。

## Verdict
**修正后可交付**。

## Open questions
- **Q-R0-1（战略，待确认）** `tenants.slug`、`skills.name` 软删后能否复用，以及 `spider_results` 唯一键形态，是否并入 §6 由 operator 决定？A 并入 D4 并新增 D14（推荐）；B 维持运营默认但在 §6 明示并取得 operator 确认。
- 运营性默认：报告内所有「修正」按「文字修正，不重审切片」处理。

## 需 manager 补跑的核实
1. `pip-audit` 按 ID 去重计数确认 27。
2. B1 复现补断言：`GET /rbac/departments?tenant_id=B` 返回的是 B 的部门；`POST` 后新行 `tenant_id == B`。
3. `git check-ignore -v .grok/x`。

## Lesson rows（静态核实）
1. 切片自报的严重度合计不一定可信（R2 自报 1/13/6，按标题实为 1/11/8），汇总前要按 QA 标题重新统计。
2. pip-audit 会把同一公告在多条依赖路径上重复列出，报数前要按 ID 去重，且输出无严重度字段。

---

## Manager 处置（2026-09-27）
- 补跑 1：✅ 去重后 27 个公告 / 45 条记录 / 10 个包（`evidence/verify-R7.txt` 末尾）。
- 补跑 2：✅ 改走真实 `/public/tenant/signup` → `/auth/login` 链路重跑，数据归属已断言（A 看到 B 的部门、注入行 tenant_id=B、审计日志含 B 的用户名与部门名、`PUT /admin/notify-config` 200）（`evidence/verify-R1-repro-v2.txt`）。
- 补跑 3：✅ `.grok/x` 被 `.gitignore:73` 忽略；`.codex/skills/x` 未被忽略。
- 另补 🔍：P0-9（`/auth/register` → default 租户、tenant_role=viewer、role 缺省 operator）与 P0-6（交付 webhook 与内部回调同密钥同构造）逐行确认（`evidence/verify-manager-3.txt`）。
- QA-1..QA-12 全部按修正建议改入方案修订版；Q-R0-1 按推荐 A 的形式并入 §6（D4 扩展 + 新增 D14），仍为待确认。
