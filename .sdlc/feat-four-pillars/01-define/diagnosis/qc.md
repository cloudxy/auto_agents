# QC 覆盖完整性诊断 · feat-four-pillars

> 角色：`/qc`｜日期：2026-09-07｜性质：**覆盖缺口诊断，不是放行意见**
> 决策对象：当前产品 + 本特征已落盘工件。**不是** ship/block 发布闸。
> 上游：`01-define/spec.md` · `user-story.md` · `metrics-blueprint.md` · `05-review/findings.md` · `state.yaml` · `sdlc.config.yaml` · `.sdlc/_lessons.md` · `01-define/diagnosis/*` · 标 stale 的 `02-shape/`
> 拒绝：修代码 · 重审缺陷 · 写用例 · 写 `05-review/release-opinion.md`
> 编排器未粘贴 `check-matrix.py` 输出；本文件按「无矩阵文件 = 全空洞」机械核对，不代跑脚本。

---

## 0. 结论先行

| 项 | 内容 |
|---|---|
| **覆盖核对结论** | **Block** |
| 一句话 | 定义帽 G-fresh 已失败；没有 `coverage.md`、没有 `edge-states.md`、没有实现票文件；blocker QA-02 与 10 条 major 仍 open。现网 997 条 pytest **不是**本特征 FR 的覆盖。 |
| 这不是放行 | `hats_done: []`，`current_hat: 定义`。本文件只回答「五类覆盖现在有没有格子」。 |

**不得把 `02-shape/` 当覆盖证据。** `state.yaml.stale_artifacts` 已点名：`contract.md` + ADR-0010…0014 是中断的 architect 半成品。`tickets/` 与 `contracts/` 目录为空；`contract.md` 还指向磁盘上不存在的 ADR-0015…0018 与 8 份契约文件。

---

## 1. 五类覆盖完整性核对

### ① FR/NFR 清单 ↔ 覆盖矩阵

`04-verify/coverage.md`：**不存在**（全仓库该特征树零命中）。`check-matrix.py` 输出：**未提供**。矩阵文件缺失时，脚本会把 spec 里每条 `FR-n` / `NFR-n` 都判空洞。

| 项 | 数量 | 明细 |
|---|---|---|
| PRD 冻结 FR（Wave 0） | 16 | FR-01 … FR-16 |
| PRD 冻结 FR（Wave 1） | 15 | FR-17 … FR-31 |
| PRD stub FR（有 GWT） | 7 | FR-50, FR-51, FR-60, FR-61, FR-70, FR-71, FR-72 |
| PRD 编号但无 GWT | 2 | FR-52 `[scope reduced]`；FR-73 `[dropped]` |
| **矩阵出现的 FR** | **0** | — |
| **缺失** | **全部** | 上表每一条都无矩阵行 |
| PRD NFR | 10 | NFR-01 … NFR-10；NFR-09 已声明 N/A |
| 矩阵出现 / N/A | 0 / 0 | NFR-09 的 N/A **也没写进矩阵**（空格子 ≠ 已声明 N/A） |

GWT 粗计：冻结集 31 条 × 各 ≥3 = **≥93** 格；加上 stub 7×3 = **≥114** 条用户可见验收。矩阵里一行都没有。

`01-define/diagnosis/qa.md` §8 只有 D# / 支柱大纲，且自陈「定义帽尚无 spec.md FR 编号」——那是审查前的诊断草稿，**不能**代替 `coverage.md`。

**现网测试 ≠ 本特征矩阵。** QA 诊断（仓库当时）：后端 103 文件 / 997 条 pytest；前端 Jest 7 文件 / 15 条；E2E 无（`sdlc.config.yaml` `e2e: null`）。Power Market 设计 D1–D21：**专用用例 0**。`listing_state` / `capability_sources` / `capability_installs` / `capability_aliases` 仓库零命中。现网套件锁的是 **P6 旧契约**（viewer 可扫目录、公开只 `stable`、无 MCP → degraded），与冻结 FR-06/18/26 **互斥**。把 997 条绿当成本特征覆盖 = 空洞声明。

**为什么阻塞：** 没有映射就不能证明「谁测哪条 FR」。矩阵证明的是「有格子」，现在连格子都没有。

**以后要能进 verify/qc 放行，必须为真：**

1. 存在 `04-verify/coverage.md`（或等价 `trace-matrix.md`），每条 FR/NFR 至少一行，空洞显式 ❌/⚠️/➖ 且第 5 节展开。
2. 编排器跑 `skills/qa/scripts/check-matrix.py coverage.md spec.md`，空洞数 = 0（含 FR-52/FR-73/NFR-09 的显式豁免行）。
3. 反向：每个新用例能指回 FR/GWT；现网旧用例标「旧契约 / 将改写」，不得标 ✅ 覆盖 FR-17…31。

---

### ② FR 清单 ↔ 设计工件（有 UI 的 FR 要有 edge-states）

独立 `edge-states.md`：**不存在**（frontend 诊断原文：「设计矩阵尚未作为独立 `edge-states.md` 交付」）。

有界面的冻结 FR（非穷尽，但够判跳过设计帽）：

| 簇 | FR | 用户可见面 | edge-states |
|---|---|---|---|
| 官网诚实 / 注册 / 定价 | FR-01, 02, 04, 05 | 首页、定价、注册成功 | 无 |
| 导出 | FR-03 | 结果/数据中心 | 无 |
| 治理写面 | FR-06, 07 | 扫描/验证、渠道、平台 LLM | 无 |
| 租户任务/用量 | FR-08…12, 16 | 任务列表、用量、仪表盘 | 无 |
| 公开详情不泄漏 | FR-13 | 公开详情 404 vs 路径 | 无 |
| 密钥掩码 | FR-14 | 设置/渠道页 | 无 |
| 能力市场商店+治理 | FR-17…31 | 列表/搜索/详情/订阅/安装/源/六态 | 无 |

`diagnosis/designer.md` §4 是 **现网六态走查**（商店/技能/治理/采集/中转/注册），不是设计帽交付的逐屏合同。技能模板要求：加载/空（本来没有 vs 筛选空）/错误（含兜底）/权限（隐藏 vs 禁用）/边界/离线，空格必须给理由。现网表本身大量 ❌（失败装空、无离线、无 coming_soon）。

`02-shape/` 无 `edge-states.md`、无 `flow.md`、无 tokens。T-16「商店面/治理台 IA 与词表」只存在于 **stale** `contract.md` 表格，没有票文件。

**为什么阻塞：** 缺 `edge-states.md` = 设计阶段被跳过。六态若由 frontend 在实现时自编，QA 没有异常态的唯一来源。

**以后必须为真：** 设计帽对 Wave 0 官网+用量+权限拒绝面、Wave 1 商店/治理/安装，交付独立 `edge-states.md`；每条有 UI 的冻结 FR 在该文件「FR 覆盖核对」表有行。诊断稿 §4.2 文案合同可以作输入，不能当已交付。

---

### ③ FR 清单 ↔ 实现票

| 源 | 事实 |
|---|---|
| `state.yaml` `tickets:` | `[]` |
| `02-shape/tickets/` | 空目录 |
| `02-shape/contracts/` | 空目录 |
| 实现证据 `03-impl/` | 不存在 |

stale `contract.md` §10 **表格**写了 T-01…T-32，Wave 0 粗覆盖 FR-01…16，Wave 1 粗覆盖 FR-17…31。那不是票：

- 没有票文件、没有验收 GWT 引用、没有 `state.yaml` 登记。
- 同文件还引用不存在的 `contracts/*.md` 与 ADR-0015…0018（磁盘只有 ADR-0010…0014）。
- NFR-01…08、NFR-04 安全、NFR-05 权限在拆票表里几乎只靠 T-15（NFR-10）捎带。
- stub FR-50/51/60/61/70–72 正确未进冻结拆票，但冻结集本身也没有可执行票。

**为什么阻塞：** 「每个人以为别人会拆票」。没有实现票就不能进实现帽，更不能把 stale 方案当已塑形。

**以后必须为真：** G-fresh 通过后再派 architect **重写**方案（不得在 stale 半成品上续写）。每条冻结 FR 至少一张实现票文件；`state.yaml.tickets` 非空；契约文件真实存在；被引用的 ADR 都在磁盘上。

---

### ④ Findings 处置状态

来源：`05-review/findings.md` + `state.yaml.review_findings`。本角色不重审、不定级。

| 编号 | 严重度 | 一句话 | 状态 |
|---|---|---|---|
| QA-01 | blocker | state appetite 8h vs 程序波次 | **fixed**（state 已改按波） |
| QA-02 | blocker | FR-15 GWT 缺 WACT 排除字段 / `login_failed` | **open** |
| QA-03 | major | 宿主不匹配时用户结果未冻 | **open** |
| QA-04 | major | 只读成员能否订阅自相矛盾 | **open** |
| QA-05 | major | 第三方正文无 XSS 验收格 | **open** |
| QA-06 | major | 可见性矩阵丢「测试中」 | **open** |
| QA-07 | major | FR-07 租户读渠道绑未关的 Q-RELAY | **open** |
| QA-08 | major | AGPL 不在操作者必答表 | **open** |
| QA-09 | major | 首页技能失败装空未进 Wave 0 | **open** |
| QA-10 | major | 「未知即可上架」vs CONTEXT 未验证不得分发 | **open** |
| QA-11 | major | spec §6 与 metrics-blueprint 护栏不一致 | **open** |
| QA-12 | major | 平台出站 Key 跨租户拉数未进 FR/范围外 | **open** |
| QA-13 | major | `open_questions: []` vs 六问 | **fixed**（六问已写入 state） |
| QA-14 | minor | spec §2 vs user-story Confirmation | **open** |
| QA-15 | minor | 若干「越权」GWT 不测授权 | **open** |
| QA-16 | minor | 配额 ≥90% 有态无 GWT | **open** |
| QA-17 | minor | 后台 IA 重组未分诊 | **open** |
| QA-18 | minor | FR-26.2 把 PR8 enable-host 冻进 Wave 1 | **open** |
| QA-19 | minor | 别名与存活目录名冲突未冻 | **open** |

| 严重度 | 总数 | fixed | waived | **open** |
|---|---|---|---|---|
| blocker | 2 | 1 | **0** | **1（QA-02）** |
| major | 11 | 1 | 0 | **10** |
| minor | 6 | 0 | 0 | **6** |

无一条 waived（无理由+批准人）。blocker 不允许 waived。

G-fresh 指纹仍记 blocker=2（审查当时 QA-01 未改 state）。编排器事后改了 appetite / 六问，**未重跑** G-fresh。QA-02 仍 open → 定义帽质量闸按 findings 原文仍不通过。

**为什么阻塞：** 北极星「能判定」无法从冻结 GWT 落地（QA-02）；10 条 major 会让 Wave 0/1 冻结集在权限、XSS、可见性、密钥后门上带着洞交给 architect。

**以后必须为真：** QA-02 关闭（GWT 补字段或蓝图删断言）后重跑 G-fresh；major 全部 fixed 或有理由+批准人的 waived；minor 同样；修复后闸门指纹更新到新 commit。

---

### ⑤ 闸门指纹

| 闸门 | 命令 | 退出码 | 通过/失败/跳过 | 指纹 |
|---|---|---|---|---|
| sdlc | `bash …/check-sdlc.sh --require .sdlc/feat-four-pillars` | 0 | 通过 | `at: 2026-09-07T16:20:00` |
| test | `uv run pytest -x -q backend/tests` | — | **跳过** | reason：定义帽无代码 |
| lint | `bash scripts/check-arch.sh` | — | **跳过** | reason：塑形/实现再跑 |
| build | 双前端 `npm run build` | — | **跳过** | reason：定义帽无前端实现 |
| migration | `bash scripts/check-db-migrations.sh` | — | **跳过** | reason：无 schema 落地 |
| e2e | null | — | **未配置** | `e2e_reason` 已写；verify 帽补 curl/浏览器 |
| fresh-context | reviewer | fail | **失败** | `at: 2026-09-07T15:45:43`；findings_total 19；blocker 2 / major 11 / minor 6 |

定义帽对 test/lint/build/migration 的 **null + reason** 形式合格（不是静默跳过）。但：

- G-script 绿 **不能**当覆盖完整：`check-sdlc.sh` 仅在 **已有** `coverage.md` 时扫 MATRIX；没有该文件则整段跳过，exit 0。本特征正好是这条路径（见 pitfalls）。
- 现网 pytest 从未作为本特征闸门跑过（无本特征 commit 的 test 指纹）。
- G-fresh 失败且未在 QA-01/13 修复后重跑。

**以后必须为真（真正要放行时）：** 决策 commit = 各闸门 commit；test/lint/build/migration 有命令+退出码+时间戳；G-fresh 为 pass；e2e 继续 N/A 须在 verify 有 curl/浏览器路径证据；修复后必须重跑，禁止沿用定义帽的 sdlc pass。

---

## 2. 角色参与完整性（对照 state 邀请表）

| 角色 | 声明 | 实际工件 | 判定 |
|---|---|---|---|
| `/pm` | 定义 | `spec.md` `user-story.md` `metrics-blueprint.md` | ✅ 有 PRD；G-fresh 未过 |
| `/ops` … `/algo` | 诊断 | `01-define/diagnosis/<role>.md` | ✅ 诊断齐；不是方案/票 |
| `/architect` | 诊断 + 过早塑形 | `diagnosis/architect.md` + **stale** `02-shape/` | ⚠️ 半成品，不可当方案 |
| `/designer` | 诊断 | `diagnosis/designer.md`；**无 edge-states.md** | ❌ 设计帽未交六态合同 |
| `/dba` | 诊断 | `diagnosis/dba.md`；无 db-spec / 迁移 | ➖ 定义帽可；塑形后必须有 |
| `/qa` | 诊断 | `diagnosis/qa.md`；无 coverage.md / test-report | ❌ 相对覆盖核对 |
| `/sre` | 诊断 | `diagnosis/sre.md`；无 release-checklist | ➖ 放行前必须有 |
| `/qc` | 本文件 | 覆盖诊断，**不是** release-opinion | ✅ 本轮职责 |

`/algo` `/miner` `/warehouse`：诊断已交；数仓/评估集 PRD 标下一轮 → 本程序 N/A 成立，但 FR-15/30 事件仍必须有矩阵行。

---

## 3. 跨工件一致性抽查（不重做 reviewer）

| 项 | 抽查 | 结果 |
|---|---|---|
| 进度 vs PRD | state appetite 已按波；六问已写入 | QA-01/13 文件现状 fixed |
| 北极星 vs FR-15 | 蓝图要 `task_completed` 含候选标记、`login_failed`；GWT-15.1 没有 | **QA-02 open**（覆盖根洞） |
| 护栏清单 | spec §6 第五条 vs 蓝图第五条 | **QA-11 open** |
| 故事 Confirmation | spec §2 vs `user-story.md` | **QA-14 open** |
| 方案 vs 磁盘 | contract 引用 ADR-0015…18、`contracts/*.md` | **文件不存在**（stale 内自洽失败） |
| 现网用例 vs 冻结 FR | D1–D21 零专用用例；旧用例锁互斥契约 | 实现时会假绿/假红 |

---

## 4. 现网产品覆盖（相对冻结 FR，不是放行）

只引用 `/qa` 已写事实，不新找缺陷。

| 支柱 | 现网回归 | 相对本特征 |
|---|---|---|
| 采集 | 厚（planner/任务/导出） | 无「候选 → listing」；harvester 无 D7 unlisted |
| SaaS | 隔离/成员强 | 无 installs 表/API；豁免清单无 `capability_assets` |
| 中转 | 管控面厚 | 守卫 `require_admin` ≠ FR-07 平台超管 |
| 市场 | P6 扫描/验证/公开三闸 | 与 FR-18 可见性、FR-20 订阅、FR-25 源 **正交且冲突** |

空心绿（已读源码，见 pitfalls）：

- `backend/tests/test_skill_harvester.py::test_spider_contract`：`"backend" not in [str(m) for m in ()]`，空元组恒真。
- `backend/tests/test_db_behavior_loop.py::test_explain_assertion_framework`：对模拟 dict 断言 `type != ALL`，不是真实 EXPLAIN。

方言：CI 主跑 SQLite；MySQL 保真 8 文件不含能力域。Wave 1 的生成列 / `JSON_CONTAINS(host_compat)` / 许可 `COALESCE` **今日测不出**。矩阵将来若只映射 SQLite 用例，对 NFR-05/FR-18 仍是无效覆盖。

---

## 5. 最小闭环（定义帽能往下走；不是「顺便改」）

| # | 必须真 | 为什么阻塞覆盖 | 指派 |
|---|---|---|---|
| 1 | 关闭 QA-02（FR-15 GWT 或蓝图二选一对齐） | 北极星无法验收 → 覆盖目标无定义 | `/pm` |
| 2 | 关闭或书面 waive 剩余 10 条 major | 冻结集带着权限/XSS/可见性/后门洞 | `/pm`（waiver 批准人不是 qc） |
| 3 | 重跑 G-fresh 为 pass | 现指纹仍 fail；QA-01 修复未重跑 | 编排器 |
| 4 | 通过后再塑形；作废或重写 stale `02-shape/` | 半成品会造成假覆盖 | `/architect` |
| 5 | 设计帽交付 `edge-states.md` | UI FR 无异常态合同 | `/designer` |
| 6 | 票文件 + 非空 `tickets:`；契约文件落盘 | FR↔票为 0 | `/architect` |
| 7 | verify 帽交付 `coverage.md`，check-matrix 空洞 0 | FR↔矩阵为 0 | `/qa` + 编排器跑脚本 |

Wave 2–4 stub、Q-VOICE 等开放问题：**不**要求本轮实现，但矩阵里必须有 ➖ 行+理由，否则仍是空格子。

---

## 6. 开放问题（覆盖视角）

| ID | 问题 | 覆盖影响 | 状态 |
|---|---|---|---|
| Q-VOICE | 对外第一句 | FR-01 首屏；北极星核心动作 | 待确认 |
| Q-PRICE | 撤文案 vs 履约 | FR-01.2 / FR-05 分支 | 待确认 |
| Q-RELAY | 中转 SKU | FR-60；QA-07 把读权绑在这 | 待确认 |
| Q-MARKET-USER | 市场主用户 | CTA 主次 | 待确认 |
| Q-BILL | 支付 vs 联系 | Wave 2；FR-50 出口 | 待确认 |
| Q-LLM | LiteLLM vs new-api | 本 PRD 不选；ADR-0014 stale | 待确认 |
| （QA-08）Q-AGPL | 不在 §9.1 | NFR-06 无法验收 | 待 `/pm` 加问或写死 |

编排器未粘贴 check-matrix 输出：若后续补跑，应以脚本打印的空洞列表为准，覆盖本文件的「全空洞」推断。

---

## 7. 我做了什么 / 没做什么

| | |
|---|---|
| **做了** | 按五类覆盖核对现网+特征工件；登记 findings 状态；核对闸门指纹；标 stale 方案不可用；写出以后放行必须为真的条件 |
| **没做** | 重做 reviewer 八维 · 修代码 · 写用例 · 改判 G-fresh · 写 release-opinion |
| 是否本轮产出者 | **否**（诊断 qc，不是实现者） |

---

## 8. 自检

- [x] 五类覆盖逐项走过
- [x] 每条 finding 有 status（fixed/open；无伪 waived）
- [x] 闸门指纹：有的写了命令+退出码+时间；跳过的有 reason
- [x] 结论是 **Block**，不是「风险可控」
- [x] 未把 997 条现网绿当成 FR 覆盖
- [x] 未把 stale `02-shape/` 当已塑形
- [x] 未执行 `check-matrix.py`（编排器职责）
- [x] 未写 release-opinion
