# QC 覆盖缺口诊断 · feat-four-pillars-v2

> 角色：`/qc`｜日期：2026-09-08｜性质：**覆盖缺口诊断，不是放行意见**
> 决策对象：旧程序 `.sdlc/feat-four-pillars/` + grok-files 方案书，作为 v2 **输入**。**不是** ship/block 发布闸。
> 上游：`01-define/diagnosis/INPUTS.md` 书单 · 旧 `spec.md` v1.4 · 旧 `contract.md` v2.1 · 旧票 T-01…T-16 · 旧 `05-review/findings.md` · 旧 `state.yaml` · grok-files 方案/诊断 · `sdlc.config.yaml`
> 拒绝：修代码 · 重审缺陷定级 · 写用例 · 写 `06-deliver/release-opinion.md` · 把旧 `02-shape/` 复制成 v2 合同
> 编排器未粘贴 `check-matrix.py` 输出；无 `04-verify/coverage.md` 时按「全空洞」机械核对，不代跑脚本。
> G-fresh：不读 producer `memory/*.md`；本文件不是 memory。

---

## 0. 结论先行

| 项 | 内容 |
|---|---|
| **覆盖核对结论** | **Block**（定义帽缺口，不是发布放行） |
| 一句话 | 旧定义帽独立审查从未过闸（最后一次 G-fresh = v1.2 上 QA-29 major 仍开；v1.3/v1.4 是 producer 自批），却把 `contract.md` v2.1 + 票表 T-01…T-36 + grok-files「规范副本」当成现行合同。Wave 1 的 FR-17…36 没有一张票文件；FR-34/35/36 连票表都没有行。 |
| 这不是放行 | v2 `state.yaml`：`current_hat: 定义`，`hats_done: []`，`tickets: []`，`gates: []`。本文件只回答「旧方案哪些格子是空的、哪些句子互相否定、新方案必须先解开什么」。 |

**不得把旧 `02-shape/`、grok-files `four-pillars-plan.md`、旧诊断 README 里的「现行合同」四字，当作 v2 已塑形。** 旧 `state.yaml` 自己写着：`status: superseded`，`hats_done: []`，`G-fresh 未过`，`塑形稿已存在但不得当作过闸`。

---

## 1. 未过闸却被当成合同（先列事实，再列格子）

这是本轮 qc 相对旧 qc.md（2026-09-07，当时票目录还空）的增量：后来票文件与契约落了盘，**闸仍没过**，身份却被改成合同。

### 1.1 闸门事实（指纹，不是声称）

| 闸 | 旧 `state.yaml` 记录 | 独立审查账本 | 被当成合同的动作 |
|---|---|---|---|
| G-fresh 第 1 轮 | 已被后续 gates 覆盖；旧 qc 记 `at: 2026-09-07T15:45:43`，blocker 2 / major 11 | `findings.md`「上一轮」QA-01…19 | producer 出 v1.1 |
| G-fresh 第 2 轮 | `fresh-context` **fail** · `at: 2026-09-07T16:50:00` · major 5（QA-20…24） | 正文仍把 QA-20…28 标 open（历史层） | producer 出 v1.2 |
| G-fresh 第 3 轮 | `fresh-context-r3` **fail** · `at: 2026-09-07T17:00:00` · major 1（QA-29） | **最后一次独立审查**：PM v1.2 **不通过** | producer 出 v1.3 自称关闭 QA-29/30；**未跑第 4 轮** |
| spec v1.4 | 无对应 G-fresh | findings 头仍写「现行 PRD **v1.3**」 | 加 FR-33…36；architect 出 contract **v2.1**「对齐 v1.4」 |
| `check-sdlc.sh --require` | `sdlc` **pass** · exit 0 · `at: 2026-09-07T16:40:00` | 特征树无 `coverage.md` | 绿闸被当成「程序可塑形」 |
| test / lint / build / migration | `result: null` + reason | 无本特征运行时指纹 | 与「方案已齐」无关，但也不能当 FR 覆盖 |
| 定义帽推进 | `current_hat: 定义` · `hats_done: []` | 插件铁律：G-fresh fail **不得**把定义写入 `hats_done`，也不得把 `current_hat` 推到塑形 | 在 **不改 current_hat** 的前提下写满 `02-shape/`，绕开 HATADVANCE |

插件 `orchestrator-gates.md`：**三次**定义/塑形 G-fresh fail → **停，报系统性，不得再自动派 producer。** 旧程序至少三轮 fail 后仍产出 v1.3、v1.4、contract v2.1、ADR-0010…0018、契约 9 份、票文件 16 张。这是系统性缺口，不是漏改一处文案。

`review_findings[].status: fixed` 在旧 `state.yaml` 里覆盖 QA-01…QA-30，其中 QA-29/30 注明「未经第 4 轮独立审查」。插件原文：**producer `status: fixed` 不是闸。**

### 1.2 哪些工件被写成了「合同」

| 位置 | 原句（身份声明） | 闸门对照 |
|---|---|---|
| 旧 `01-define/diagnosis/README.md` L23 | 「**现行合同：** `../spec.md` v1.4 · `../../02-shape/contract.md` v2.1 · … · 方案书副本 `four-pillars-plan.md`」 | 定义帽 G-fresh 未过；`hats_done` 空 |
| 旧 `contract.md` 头 | 「上游：PRD **v1.4**（冻结 **FR-01…FR-36**）」；「本文件 **替换** `state.yaml.stale_artifacts` 中的塑形半成品」 | `stale_artifacts: []` 被清空 = 半成品转正，不是审查通过 |
| 旧 `state.yaml` `tickets:` | 登记 T-01…T-16，`status: todo`，`evidence: 02-shape/tickets/T-nn.md` | 票文件存在 ≠ 塑形帽过闸；Wave 1 票号 T-17…T-36 **未登记** |
| grok-files `four-pillars-plan.md` L3 | 「规范副本：与仓库 `contract.md` v2.1 同步」 | 仓库外副本把未过闸方案做成第二权威源 |
| 旧 `state.yaml` `appetite` | `Wave0 3.5pw; Wave1 11pw (architect)` | 定义帽未关就把方案帽 Effort **写进进度源** |
| 旧 contract §0 | 「本轮允许进入实现的冻结 FR：… FR-17…**32**」 | 与头上的 FR-01…**36**、spec 冻结集互相否定（见 §3） |

**判定：** 旧方案的「合同」身份来自文件头和诊断 README，不是来自 G-fresh pass。v2 若复制这些文件，就是把未过闸物再签一次。

---

## 2. 五类覆盖完整性核对

### ① FR/NFR 清单 ↔ 覆盖矩阵

`feat-four-pillars/04-verify/`：**不存在**。`feat-four-pillars-v2/` 无 `coverage.md`。`check-matrix.py` 输出：**未提供**。无矩阵文件 = spec 里每条 `FR-n` / `NFR-n` 都是空格子。

| 项 | 数量 | 明细 |
|---|---|---|
| 旧 PRD 冻结 FR（Wave 0） | 16 | FR-01 … FR-16 |
| 旧 PRD 冻结 FR（Wave 1） | 20 | FR-17 … FR-36（v1.4 才加 33…36） |
| 旧 PRD stub（有 GWT） | 7 | FR-50、51、60、61、70、71、72 |
| 编号但无完整实现承诺 | 2 | FR-52 `[scope reduced]`；FR-73 `[dropped]` |
| **矩阵出现的 FR** | **0** | — |
| **缺失** | **全部** | 上表每一条都无矩阵行 |
| 旧 PRD NFR | 10 | NFR-01 … NFR-10；NFR-09 已声明 N/A |
| 矩阵出现 / N/A | 0 / 0 | NFR-09 的 N/A **也没写进矩阵**（空格子 ≠ 已声明 N/A） |

GWT 粗计：冻结 36 条 × 各 ≥3 = **≥108** 格用户可见验收；加上 stub ≥21。矩阵一行都没有。

旧 `diagnosis/qa.md`（及 grok-files `feat-four-pillars-qa-diagnosis.md`）自陈定义未关、**本波不交付矩阵**。那是缺口清单，**不能**代替 `coverage.md`。

**现网测试 ≠ 本特征矩阵。** 旧 qa：pytest 约 103 文件 / ≥1000 条；Jest 7 文件 / 16 条；E2E 无（`sdlc.config.yaml` `e2e: null`）。Power Market 用户可见行为专用用例 **0**。`listing_state` / `capability_sources` / `capability_installs` / `capability_aliases` 当时零命中。现网套件锁的是 **P6 旧契约**（viewer 可扫目录、公开只 `stable`、无 MCP → `degraded`），与冻结 FR-06/18/26 **互斥**。把仓库绿当成本特征覆盖 = 空洞声明。

空心绿（pitfalls 已核实，不新找缺陷）：

- `test_spider_contract`：`"backend" not in [str(m) for m in ()]`，空元组恒真。
- `test_explain_assertion_framework`：对模拟 dict 断言，不是真实 EXPLAIN。
- grok-files / 旧 backend：`test_expired_tenant_login_rejected` **没有** `POST /login`。

**为什么阻塞：** 没有映射就不能证明「谁测哪条 FR」。矩阵证明的是「有格子」，现在连格子都没有。`check-sdlc` 在无 `coverage.md` 时 **整段跳过 MATRIX**（PIT-QC-02），exit 0 不能当覆盖完整。

**v2 以后要能进 verify/qc 放行，必须为真：**

1. 存在 `04-verify/coverage.md`（或等价 `trace-matrix.md`），每条冻结 FR/NFR 至少一行；空洞显式 ❌/⚠️/➖ 且展开。
2. 编排器跑 `check-matrix.py`，空洞数 = 0（含 stub / NFR-09 / 范围外的显式豁免行）。
3. 反向：每个新用例能指回 FR/GWT；现网旧用例标「旧契约 / 将改写」，不得标 ✅ 覆盖 Wave 1。

---

### ② FR 清单 ↔ 设计工件（有 UI 的 FR 要有 edge-states）

独立 `edge-states.md`：**旧程序没有，v2 也还没有。** 旧 frontend 诊断原文：「设计矩阵尚未作为独立 `edge-states.md` 交付」。`02-shape/` 无 `edge-states.md`、无 `flow.md`、无 tokens。

有界面的冻结 FR（非穷尽，够判设计帽未交合同）：

| 簇 | FR | 用户可见面 | edge-states |
|---|---|---|---|
| 官网诚实 / 注册 / 定价 | FR-01、02、04、05 | 首页、定价、注册成功 | 无 |
| 导出 | FR-03 | 结果/数据中心 | 无 |
| 治理写面 / 渠道隐藏 | FR-06、07 | 扫描/验证、渠道 404 | 无 |
| 租户任务/用量 | FR-08…12、16 | 任务、用量、仪表盘 | 无 |
| 公开详情不泄漏 | FR-13 | 公开 404 vs 路径 | 无 |
| 密钥掩码 | FR-14 | 设置页 | 无 |
| 能力市场商店+治理 | FR-17…36 | 列表/搜索/详情/订阅/安装/五类/六态 | 无 |

合同表里的 **T-17「商店面/治理台 IA 与词表」没有票文件**。有 UI 的 Wave 1 被写成「设计师 2 天」，磁盘上零设计交付。

**为什么阻塞：** 缺 `edge-states.md` = 设计阶段被跳过。六态若由 frontend 在实现时自编，QA 没有异常态的唯一来源。

**v2 必须为真：** 设计帽对 Wave 0 官网+用量+权限拒绝面、Wave 1 商店/治理/安装，交付独立 `edge-states.md`；每条有 UI 的冻结 FR 在该文件有行。诊断稿里的现网六态走查可以作输入，不能当已交付。

---

### ③ FR 清单 ↔ 实现票

**票号命名空间已经撞车**（见 §4 G-SYS-04）。下表「票」= `02-shape/tickets/T-nn.md` 文件，不是 spec 分诊表里的 T-01…T-32。

| 源 | 事实 |
|---|---|
| 旧 `state.yaml` `tickets:` | 仅 T-01…T-16，全 `todo` |
| `02-shape/tickets/` | **16 个文件**（T-01.md … T-16.md）= Wave 0 |
| `02-shape/contract.md` §10 | **表格**写了 T-17…T-36（Wave 1），**没有对应文件** |
| v2 `state.yaml` `tickets:` | `[]` |

Wave 0 文件票 ↔ 冻结 FR（机械，不评票质量）：

| FR | 有票文件？ | 文件 |
|---|---|---|
| FR-01、02、04、05 | 是 | T-09 |
| FR-03 | 是 | T-10 |
| FR-06 | 是（部分：扫描/验证，上架留给 Wave 1） | T-01、T-02、T-04 |
| FR-07 | 是 | T-03、T-04 |
| FR-08 | 是 | T-05、T-07、T-16 |
| FR-09 | 是 | T-05 |
| FR-10 | 是 | T-06 |
| FR-11 | 是 | T-07 |
| FR-12、16 | 是 | T-08 |
| FR-13 | 是 | T-11 |
| FR-14 | 是 | T-12 |
| FR-15 | 是 | T-13、T-14 |
| GWT-08.4 | 是 | T-16 |

Wave 1 冻结 FR ↔ 票：

| FR | 合同表有行？ | 票文件？ | 备注 |
|---|---|---|---|
| FR-17…32 | 有（T-17…T-36 散落） | **无** | 表不是票 |
| **FR-33** | 仅 T-33 表行（Admin 五类） | **无** | 商店筛选 GWT-33.* 无票 |
| **FR-34** | **无** | **无** | 订/卸不级联；契约目录 grep 零命中 |
| **FR-35** | **无** | **无** | 未上架≠停用；GWT-35.1 还要求智能体运行时 |
| **FR-36** | **无**（T-33 文案「含命令」捎带） | **无** | 命令独立卡片 |
| FR-50…73 stub | 正确未进实现票 | — | 矩阵仍缺 ➖ 行 |

NFR ↔ 票文件：

| NFR | 票文件 |
|---|---|
| NFR-01 性能 ≤2s | **无**。合同用「距主键点查有数量级余量」代替测量 |
| NFR-02 分页/100 条 | 部分：T-10 导出；分页只在契约正文 |
| NFR-03 失败不装空 | 无文件；挂 FR-28 表行 |
| NFR-04 安全 | 拆到 T-11/12/16；无单独行 |
| NFR-05 权限 | 拆到 T-02/03/04；租户安装在 **无文件的** T-27 |
| NFR-06 许可/AGPL | 许可在无文件的 T-24；AGPL 仍开放 |
| NFR-07 旧地址到达 | 无文件的 T-30 |
| NFR-08 可观测 | T-13/14；市场事件在无文件的 T-35 |
| NFR-09 国际化 | 声明 N/A，**矩阵无行** |
| NFR-10 可维护/B4 | T-15 |

合同自己写「票文件：`02-shape/tickets/T-nn.md`」，然后 Wave 1 只有表。这是「每个人以为别人会拆票」的第二形态：Wave 0 有文件，Wave 1 用表格冒充。

**为什么阻塞：** 冻结集宣称 FR-01…36 可进实现；可执行票停在 FR-16。v1.4 的四条新 FR 没有实现锚。把 contract v2.1 当 v2 输入可以，当 v2 合同不行。

**v2 必须为真：** 定义帽 G-fresh 通过后再派 architect **重写**方案（不得在旧 v2.1 上续写转正）。每条冻结 FR 至少一张实现票**文件**；`state.yaml.tickets` 与磁盘一致；被引用的 ADR/契约都在磁盘上；票号与 spec 分诊 ID 分命名空间。

---

### ④ Findings 处置状态

来源：旧 `05-review/findings.md`（独立审查）+ 旧 `state.yaml.review_findings`（producer 簿记）。本角色不重审、不定级。

**独立审查最后一次（第 3 轮，PM v1.2）：不通过。**

| 编号 | 严重度 | 一句话 | 独立审查 | state.yaml 簿记 |
|---|---|---|---|---|
| QA-01 … QA-19 | blocker/major/minor | 第 2 轮已独立核为 fixed | fixed | fixed |
| QA-20 … QA-28 | major/minor | 第 3 轮独立核为 fixed | fixed | fixed |
| **QA-29** | **major** | GWT-14.3 渠道页掩码 vs 隐藏+404 互否 | **open**（待第 4 轮核 v1.3） | **fixed**（注明未第 4 轮） |
| **QA-30** | minor | 柱 A「凭什么说改善了」未排除候选 | **open**（待第 4 轮核 v1.3） | **fixed**（注明未第 4 轮） |
| FR-33…36 | — | v1.4 新增，**从未进 findings** | **无 ID** | 无 |

按独立审查口径（qc 认这个，不认 changelog「关闭 QA-29」）：

| 严重度 | 独立审查 open | producer 自称 |
|---|---|---|
| blocker | 0 | 0 |
| **major** | **1（QA-29）** | 0 |
| minor | 1（QA-30） | 0 |

无一条 waived（无理由+批准人）。blocker 不允许 waived。major 未独立关闭 = 定义帽质量闸 **仍 fail**。

v1.4 的 FR-33…36 不在任何 finding 里：不是「已修」，是「没审」。覆盖上等价于一批 **未过闸的冻结 FR**。

**为什么阻塞：** 密钥页 oracle（QA-29）与北极星口径（QA-30）在独立审查里仍开；五类平级四条 FR 零审查。architect 已按「已关」写进 T-12 验收和 contract v2.1。这是把未过闸物写进实现合同。

**v2 必须为真：** 新 spec 冻结后 **独立** G-fresh；QA-29 类互否句在 PRD 内只留一个 oracle；v1.4 增量要么重审要么明确降出冻结集。producer 变更记录不算过闸。

---

### ⑤ 闸门指纹

| 闸门 | 命令 | 退出码 | 通过/失败/跳过 | 指纹 |
|---|---|---|---|---|
| sdlc（旧程序） | `bash …/check-sdlc.sh --require .sdlc/feat-four-pillars` | 0 | 通过 | `at: 2026-09-07T16:40:00` |
| test | `uv run pytest -x -q backend/tests` | — | 跳过 | reason：塑形/定义无运行时代码 |
| lint | `bash scripts/check-arch.sh` | — | 跳过 | reason：未改运行时 |
| build | 双前端 `npm run build` | — | 跳过 | reason：无前端实现 |
| migration | `bash scripts/check-db-migrations.sh` | — | 跳过 | reason：表未落地 |
| e2e | null | — | 未配置 | `e2e_reason` 已写 |
| G-fresh r2 | reviewer | fail | **失败** | `at: 2026-09-07T16:50:00`；major 5 |
| G-fresh r3 | reviewer | fail | **失败** | `at: 2026-09-07T17:00:00`；major 1 |
| v2 全部闸 | — | — | **未跑** | `gates: []` |

定义帽对 test/lint/build/migration 的 **null + reason** 形式合格（不是静默跳过）。但：

- G-script 绿 **不能**当覆盖完整（无 `coverage.md` → MATRIX 整段跳过）。
- 现网 pytest 从未作为本特征闸门跑过。
- G-fresh 失败后 **未**在 v1.3/v1.4 上重跑。
- HATADVANCE 靠 `current_hat` 仍停在「定义」而没响——**塑形目录照样写满**。这是门禁盲区，不是门禁通过。

**v2 真正要放行时必须为真：** 决策 commit = 各闸门 commit；G-fresh 为 pass；test/lint/build/migration 有命令+退出码+时间戳；e2e 继续 N/A 须在 verify 有 curl/浏览器路径；修复后必须重跑。

---

## 3. 角色互相否定的句子

只收录 **两份已落盘工件各写死一句、且不能同时为真** 的对。不重审对错，不代选。v2 的 `/pm` 必须在冻结前解开；解开前 architect 不得把任一侧写进合同。

### 3.1 产品合同内部自否

| ID | 句子 A | 句子 B | 覆盖后果 |
|---|---|---|---|
| X-FR36 | `contract.md` 头：「冻结 **FR-01…FR-36**」 | 同文件 §0：「本轮允许进入实现的冻结 FR：… FR-17…**32**」；§2.1：「FR-01…**32** 均有归属」 | v1.4 四条 FR 在「冻结」与「不进实现」之间。T-33 只捎 FR-33；FR-34/35/36 无票无契约字段 |
| X-QVOICE | spec §9：「与该问题绑定的 FR **不得**当作已选定解法进方案帽」；Q-VOICE 阻塞「FR-01 首屏那一句」 | T-09 验收把 GWT-01.* 整段写成可做；US-W0-01 又把「写死对外第一句」标范围外 | FR-01 有票无稳定 Then。矩阵若标 ✅ 是假覆盖 |
| X-QPRICE | spec：Q-PRICE 阻塞 FR-01.2 / FR-05「预告 vs 删除 vs 做出来」 | T-09：「空头三项：删除或标预告，不履约」——把「不履约」写成已选 | 定价 CTA 的 oracle 分叉；Jest 写不出唯一断言 |
| X-FINDINGS | `findings.md`：「第 3 轮 **不通过**。QA-29 **open**。producer 声称 v1.3 已关——待第 4 轮」 | spec 变更记录 v1.3：「关闭 QA-29、QA-30」；`state.yaml` 两条 status=fixed | 同一 ID 既开又关。覆盖账本不能用 state 的 fixed 计数 |

### 3.2 跨角色互否（旧诊断 / grok-files / spec / contract）

| ID | 句子 A | 句子 B | 谁必须先答 |
|---|---|---|---|
| X-EXPIRED | grok-files 方案 `four-pillars-diagnosis-and-plan.md` W0-3：「`authenticate` 拒绝 `expired/disabled`」；同文件 QC 放行清单：「过期租户登录 403」。backend/miner：过期仍可登录，空心测试。ops/BE 标 P0 | spec §1 需求来源：「本波不新开 FR；沿用现网」。contract 范围外表：「miner vs 非 pm 草稿互殴；spec 未冻 \| **不进 Wave 0 票**」 | `/pm`（是否进冻结集）。qc 不代选 |
| X-QUOTA | grok-files 同稿 W0-4：「超配额 LLM 429 **`QUOTA_EXCEEDED`**」 | spec FR-12 / T-08 / frontend 诊断：用户可见文案 **禁止** `QUOTA_EXCEEDED` / `429` 字样 | `/pm` 钉用户可见 oracle；`/architect` 钉信封 `code` 是否对前端隐藏 |
| X-HOST | grok-files 同稿：「操作者本机：**enable-host 投影**（Grok symlink + snippet）」；Wave 1 PR8：「enable-host；Grok symlink-only」 | spec FR-26 / GWT-26.1：Wave 1 **无**「启用到宿主」按钮。contract：PR8 **缩水**，不挂 `POST enable-host`。frontend 诊断 M23：本期不要画该按钮。同稿 PR5 又写「无 enable-host 按钮」——**一份 grok 稿内部已经互否** | `/pm` 冻结 Wave 1 动词；不得把设计 PR8 原文与缩水方案同时当合同 |
| X-TAB | grok-files DES / 旧 frontend M16：「管理端 **六 Tab**（源 / 目录 / 插件 / 技能 / **专家** / 专家团）」 | spec FR-33 / §9.2：「**五类平级**：技能 / 插件 / 命令 / 智能体 / 专家团。对外不说『专家』」。contract T-33：「Admin **五类**治理台（含命令/智能体）」 | `/designer` 交一张 IA；`/pm` 确认词表。六 Tab 方案与五类冻结不能同时进 v2 |
| X-SLICE | grok-files PM：「第一可卖切片 … **(c) 超管能给租户发中转站令牌**」；对外一句话已写成「三个入口，一个账单」 | spec Q-RELAY / Q-VOICE **待确认**，禁止代选；Wave 0 不发令牌、不新造租户渠道屏；contract 明确不代选七问 | 操作者关 Q-VOICE / Q-RELAY。grok-files PM 建议句 **不是** 已冻结 Hero |
| X-WAVE5 | grok-files：「正确切法：一个程序，**五波**」；「数据中心 … 本程序 **Wave 5** 才碰」 | spec 波次止于 Wave 0–4；数仓/评估集标「下一轮」，不是本程序波号。warehouse 诊断：Wave 5 之前不要建仓 | `/pm` 波次表。v2 不得同时有「五波程序」和「四波+下一轮」 |
| X-APPETITE | grok-files Q4：「W0 **一周内**；W1 **2–3 周**」（日历） | spec：Wave 0 **2–4 人周**、Wave 1 **8–16 人周**。contract：**3.5 + 11 人周**。旧 state 已改写成 architect 数字 | `/pm` 进度源只进人周或只进日历，禁止混用后写入 `appetite` |
| X-LISTING | CONTEXT / 旧 UI：「插件经 MCP 验证后方可分发」；`test_b1c` 无 MCP=`degraded` | spec §9.2 / ADR-0018：分发=上架；无 MCP → `unknown` **可上架**；CONTEXT 该行由方案帽 superseded | 新 spec 必须点名 superseded 的权威文件；旧用例必须标将改写，否则 Wave 1 假红 |
| X-IA | 旧 designer：后台 IA 重组（中转升组、幽灵路由）为 **P0** | spec 分诊 **T-31**：「范围外 / 下一轮。本程序不改菜单分组」。contract：`/designer` 菜单重组 **跳过** | `/pm` 已选范围外。v2 若再把 designer P0 写进 Wave 0 就是否定 spec。覆盖上 T-31 需要矩阵 ➖ |
| X-FR35 | spec GWT-35.1 Then：「已订 A 的租户使用 A **Then A 仍能解析并调用 S**」（S 未上架） | spec 范围外：「专家团站内执行 **不做**」。algo/architect：不把市场做成 Agent 运行时 | 一条冻结 GWT 依赖本程序明确不做的执行面 → **不可测**。要么改 GWT，要么把运行时切进范围，要么矩阵标 ⚠️ 并写清不可验收 |

### 3.3 旧 qc 与后写塑形之间的否定

旧 `01-define/diagnosis/qc.md`（2026-09-07）：「不得把 `02-shape/` 当覆盖证据」；当时 `stale_artifacts` 点名 contract + ADR。

之后：票文件补了 T-01…16，ADR-0015…0018 落盘，`stale_artifacts` 被清空，诊断 README 改称「现行合同」。

**这不是旧 qc 过时，是闸仍 fail 的情况下把 stale 标成了合同。** v2 诊断 README 已改口「不是现行合同」——必须保持；禁止再把旧 README L23 抄进 v2。

---

## 4. 系统性缺口（v2 必须先解开，否则下一顶帽子会假覆盖）

| ID | 缺口 | 若复制旧方案会发生什么 | 解开的最小条件 |
|---|---|---|---|
| **G-SYS-01** | **闸门身份 ≠ 文件身份**。HATADVANCE 只看 `current_hat`，不看 `02-shape/` 是否已写满 | 定义未关也能得到「齐套方案」；qc 会在 verify 才发现合同是自批的 | v2 禁止在 G-fresh pass 前把任何 `02-shape/` 称为合同；grok-files 副本降为输入 |
| **G-SYS-02** | **三轮 G-fresh fail 未停**。插件：三次 → 系统性停止 | v2 若从 v1.4/contract v2.1 续写，等于第四次在 fail 上叠加 | 新程序从定义重开；旧 findings 作输入不继承 `status: fixed` |
| **G-SYS-03** | **producer 自批当关闭**。changelog / `review_findings.fixed` 代替第 4 轮 | QA-29 类互否会进票验收清单（T-12 已按「已拆 GWT-14.3/14.4」写） | 独立 reviewer 对 **将冻结的那一版** spec 再跑；自批句从覆盖账本删除 |
| **G-SYS-04** | **三个 T- 空间**：spec 分诊 T-01…T-32；实现票 T-01…T-36；grok-files W0-1… / PR1–PR9 | 「T-16」在 spec 是治理台真问题，在票是出站 Key，在旧 qc 曾是商店 IA | v2 分诊用 `DMD-nn` 或保留表格但不叫 T-；实现票单独编号；设计 PR 号只作对照 |
| **G-SYS-05** | **v1.4 词汇同步 ≠ 覆盖同步**。五类平级进了 spec/故事/契约头，没进票文件、没进 G-fresh、没进 §2.1 归属表 | 商店会按四类/「专家」交付，或按五类交付但无 GWT 所有者 | 冻结集要么含 FR-33…36 且每条有票+审查，要么显式降波；禁止「changelog 已对齐」 |
| **G-SYS-06** | **开放问题与冻结 FR 绑在同一条 GWT**。Q-VOICE↔FR-01.1；Q-PRICE↔FR-01.2/05；Q-RELAY↔定价空头/FR-60 | T-09 会在未选题下改官网，矩阵无法写 Then | 操作者先答，或 PM 把绑定句从冻结 GWT 拆出，只留「未履约不得写成当前可买」不变式 |
| **G-SYS-07** | **互否句未关闭就拆票**（§3 全表） | 实现帽各抄各的：过期登录、QUOTA 码、enable-host、六 Tab、中转令牌 | 新 spec 对每条 X-* 只保留一句；另一句进范围外或开放问题 |
| **G-SYS-08** | **无矩阵 / 无 edge-states / 无 check-matrix 粘贴** | 任何人都可以指着 16 张 Wave 0 票说「FR 有主」 | 定义帽不要求矩阵文件；但 **不得**用票表或现网 1000 条 pytest 代替。塑形后、verify 前必须有矩阵 |
| **G-SYS-09** | **现网套件与冻结 FR 互斥**。viewer 可扫、公开只 stable、假登录拒绝测试 | 实现改对了 CI 红；改错了继续绿 | 新方案必须把「将改写的旧用例」列成票验收，而不是另开一套平行测试 |
| **G-SYS-10** | **NFR-01 把测量交给方案帽，方案帽用数量级余量关掉** | 性能格子永远 ⚠️ 却看起来有归属 | 要么给可感 ≤2s 一条可跑的浏览器/curl 断言，要么矩阵 ⚠️ + 仪器责任人，禁止「余量」当 ✅ |
| **G-SYS-11** | **不可测冻结 GWT**（GWT-35.1 运行时；Q-VOICE 首屏句） | 矩阵会填 File:Line 到无关测试 | PM 改 GWT 或降出冻结；qa 不得发明执行面 |
| **G-SYS-12** | **权威源分裂**。仓库 spec、仓库 contract、grok-files 规范副本、grok-files 五波总稿、Power Market 设计 PR8 原文 | agent 会就近抄一份 | v2 只承认特征树内一份 spec；grok-files 全部标「输入/历史」；设计 D 决策可引用，PR 切片不可直接当票 |

---

## 5. 角色参与完整性（对照邀请表，相对 **覆盖** 不是相对文采）

| 角色 | 旧程序实际工件 | 判定 |
|---|---|---|
| `/pm` | spec v1.4、user-story、metrics-blueprint | ⚠️ 有 PRD；G-fresh 未过；v1.4 未独立审 |
| `/ops`…`/algo` | `01-define/diagnosis/<role>.md` + grok-files 若干副本 | ✅ 诊断齐；**不是**方案/票 |
| `/architect` | 诊断 + **未过闸** `02-shape/` 全套 | ❌ 半成品被写成合同 |
| `/designer` | 诊断；**无** `edge-states.md`；T-17 无文件 | ❌ 设计帽未交六态合同 |
| `/dba` | 诊断；T-01 有文件；Wave 1 db-spec（T-18）无文件 | ➖ 定义帽可；塑形后必须有 db-spec/迁移 |
| `/qa` | 诊断（缺口清单）；无 coverage.md / test-report | ❌ 相对覆盖核对 |
| `/sre` | 诊断；无 release-checklist；Worker/密钥 P0 大部分不进 Wave 0 票 | ➖ 放行前必须有 checklist；P0 降波要 PM 书面范围，不是静默 |
| `/qc` | 旧覆盖诊断 + **本文件** | ✅ 本轮职责；不是 release-opinion |

`/algo` `/miner` `/warehouse`：旧诊断已交；数仓/评估集 PRD 标下一轮 → 本程序 N/A 可成立，但 FR-15/30 事件仍必须有矩阵行。

---

## 6. 跨工件一致性抽查（不重做 reviewer）

| 项 | 抽查 | 结果 |
|---|---|---|
| 进度 vs 闸 | `current_hat=定义`，`hats_done=[]`，G-fresh fail，同时 `02-shape` 齐套、`stale_artifacts=[]` | **未过闸当合同** |
| findings vs state | QA-29 独立 open vs state fixed | **簿记假关闭** |
| spec 冻结 vs contract 实现集 | FR-01…36 vs FR-01…32 | **X-FR36** |
| spec 分诊 T-* vs 票 T-* | 两套 T-01…T-16 含义不同 | **G-SYS-04** |
| 契约头 vs 契约正文 vs 票 | `market-public-api.md` 头写 FR-33…36；正文无 FR-34/35/36 字段；票表无这三号 | 头衔覆盖 |
| 北极星 | 蓝图/spec v1.3 自称对齐排除候选；第 4 轮未跑 | QA-30 覆盖上仍 open |
| 现网用例 vs 冻结 FR | D1–D29 零专用用例；旧用例锁互斥契约 | 实现时假绿/假红 |
| grok-files 总稿 vs spec | 五波、过期登录必修、QUOTA_EXCEEDED、enable-host、中转令牌 | 与冻结集多处互否（§3.2） |

---

## 7. 最小闭环（v2 定义帽能往下走；不是「顺便改」）

| # | 必须真 | 为什么阻塞覆盖 | 指派 |
|---|---|---|---|
| 1 | **不要**把旧 `contract.md` v2.1 / 票表 T-17…36 / grok-files `four-pillars-plan.md` 标成 v2 合同 | 未过闸物会变成下一顶帽子的输入权威 | 编排器 + `/pm` |
| 2 | 解开 §3 互否表（至少 X-EXPIRED、X-QUOTA、X-HOST、X-TAB、X-SLICE、X-FR36、X-FR35、X-QVOICE/X-QPRICE） | 否则新 spec 会把两句都冻进去 | `/pm`（操作者七问）；qc 不代选 |
| 3 | 新冻结集给出 **一张** FR 清单；FR-33…36 进或不进必须显式 | 现在同时「冻结」和「不进实现」 | `/pm` |
| 4 | 票号与分诊 ID 分家 | 否则 FR↔票核对无法机械做 | `/pm` 定规则，`/architect` 执行 |
| 5 | 独立 G-fresh 打在 **将冻结的 spec 版本** 上；producer 自批作废 | 三轮 fail + 自批是系统性停机条件 | 编排器派 reviewer |
| 6 | 设计帽交付 `edge-states.md`（有 UI 的冻结 FR） | 六态无合同 | `/designer` |
| 7 | 塑形后：每条冻结 FR 一张票**文件**；磁盘 = `state.yaml.tickets` | 表不是票 | `/architect` |
| 8 | verify 帽交付 `coverage.md`，编排器跑 check-matrix 空洞 0 | FR↔矩阵为 0 | `/qa` + 编排器 |

Wave 2–4 stub、七问未关：**不**要求本轮实现，但矩阵必须有 ➖ 行+理由，否则仍是空格子。

**不在最小闭环里（夹带禁止）：** 不要求本文件重写方案；不要求补测现网 1000 条；不要求 qc 改判 G-fresh。

---

## 8. 开放问题（覆盖视角）

操作者七问（旧 spec §9.1，v2 仍未写入 `open_questions`）：

| ID | 问题 | 覆盖影响 | 状态 |
|---|---|---|---|
| Q-VOICE | 对外第一句 | FR-01 首屏；北极星核心动作；X-QVOICE / X-SLICE | 待确认 |
| Q-PRICE | 撤文案 vs 履约 | FR-01.2 / FR-05；T-09 Then | 待确认 |
| Q-RELAY | 中转 SKU | FR-60；定价空头；X-SLICE 令牌 | 待确认 |
| Q-MARKET-USER | 市场主用户 | CTA 主次 | 待确认 |
| Q-BILL | 支付 vs 联系 | Wave 2；FR-50 出口 | 待确认 |
| Q-LLM | LiteLLM vs new-api | 本 PRD 不选；不得写进覆盖 ✅ | 待确认 |
| Q-AGPL | 对外收费故事 | NFR-06；Q-RELAY 收费分支 | 待确认 |

覆盖额外问（不是代选产品，是格子无法闭合）：

| ID | 问题 | 覆盖影响 | 谁答 |
|---|---|---|---|
| Q-EXPIRED | 到期登录拒绝是否进本程序冻结 FR | 无 FR 则矩阵要 ➖；有 FR 则与 miner/backend P0 对齐 | `/pm` |
| Q-ENABLE-HOST | Wave 1 是否存在 enable-host API/按钮 | FR-26 与设计 PR8、grok-files 总稿 | `/pm` |
| Q-TAB | 治理台六 Tab vs 五类平级 | FR-33 / T-17 / T-33 | `/pm`+`/designer` |
| Q-QUOTA-CODE | 用户可见禁码 vs API `code=QUOTA_EXCEEDED` | FR-12 前后端口径 | `/pm`+`/architect` |
| Q-FR35-RUNTIME | GWT-35.1「智能体调用未上架技能」如何观测 | 无执行面则 GWT 不可测 | `/pm` |
| Q-NORTH-STAR | WACT 是否在 Q-VOICE 前锁采集出数 | FR-15 矩阵与市场订阅指标会抢北极星 | `/pm`+`/analyst` |

编排器未粘贴 check-matrix 输出：若后续补跑，应以脚本打印的空洞列表为准，覆盖本文件的「全空洞」推断。

---

## 9. 我做了什么 / 没做什么

| | |
|---|---|
| **做了** | 按五类覆盖核对旧冻结 FR-01…36、旧票 T-01…16、旧 G-fresh、grok-files 方案书；列出未过闸当合同的句子；列出角色互否句；列出 v2 必须先解的系统性缺口 |
| **没做** | 重做 reviewer 八维 · 修代码 · 写用例 · 改判 G-fresh · 写 release-opinion · 代选七问 · 把旧方案改成新方案 |
| 是否本轮产出者 | **否**（诊断 qc，不是 spec/contract 作者） |

---

## 10. 自检

- [x] 五类覆盖逐项走过
- [x] 每条独立审查 finding 有 status；producer 自批单独标出，不当 fixed
- [x] 闸门指纹：有的写了命令+退出码+时间；跳过的有 reason
- [x] 结论是 **Block**（覆盖缺口），不是「风险可控」，也不是放行
- [x] 未把现网 pytest 绿当成 FR 覆盖
- [x] 未把旧 `02-shape/` / grok-files 规范副本当 v2 已塑形
- [x] 未执行 `check-matrix.py`（编排器职责）
- [x] 未写 `06-deliver/release-opinion.md`
- [x] 未写 `memory/qc.md`
- [x] 未改业务文件
