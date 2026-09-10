# 产品分诊备忘 · feat-four-pillars-v2

> 作者：/pm｜日期：2026-09-08｜性质：**分诊备忘，不是合同**
> 合同：`../spec.md` v1 · `../user-story.md` · `../metrics-blueprint.md`
> 输入：本目录 `INPUTS.md` 全书单 + 2026-09-08 全角色诊断。旧 `.sdlc/feat-four-pillars/` 与 grok-files **只作输入**。
> 分诊 ID：**DMD-nn**。禁止 T-nn（与旧实现票 / 旧 spec 分诊三套号撞车，qc G-SYS-04）。

本文件回答：哪些是真需求、互否句怎么解开、旧方案哪句可吸收。RICE / FR / GWT 在 spec，不在这里重复当第二合同。

---

## 0. 程序身份

| 项 | 结论 |
|---|---|
| 这是旧 spec 的 v1.5 吗 | **否。** 全新 PRD。旧定义帽 G-fresh 从未过闸；`02-shape/` 与 grok-files `four-pillars-plan.md` 不是现行合同 |
| D1–D29 | **不重开** |
| 七问 | **不代选** |
| 北极星 | WACT（采集出数）。拒绝 grok-files WAU 三选一与 TTFV 回退 |
| 治理台 | **七叶**，禁止六 Tab / 专家作冻结 IA |
| 出数环 | **进 Wave 0**，不得整段 stub |
| 数仓 / 模型 / 评估集 | 实现面 **N/A** |
| 泳道 | L4。appetite 按波人周，无日历 |

---

## 1. 互否句（X-*）— 备忘指针

完整冻结句在 spec §0.2。此处只记 **为什么选这一边**。

| ID | 选哪边 | 为什么（产品） |
|---|---|---|
| X-EXPIRED | 到期拒绝进 Wave 0 | 权限/一致性不砍。现网空心测试在说谎。不选「沿用现网」 |
| X-QUOTA | 用户可见禁内部码 | 用量页今天已经在违反护栏。信封码不是用户 oracle |
| X-HOST | Wave 1 无 enable-host 按钮 | D21 已决；grok-files 总稿内部已互否 |
| X-TAB | 七叶 | 审查废 6 上限；砍命令违 D26 |
| X-SLICE | 不发令牌、不写「三入口一账单」 | 绑 Q-RELAY/Q-VOICE，禁止代选 |
| X-FR36 | 五类/命令/不级联/unlist≠停用 **进冻结集** | 旧 contract 头/身互否；v2 一张清单 |
| X-FR35 | 解析可观测，不靠执行引擎 | 站内执行是范围外；不可测 GWT 不进冻结 |
| X-QVOICE | FR-01 不写首句 | 绑定句不得假装已选题 |
| X-QPRICE | 只冻「未履约≠当前可买」 | 「不履约」不是已选答案 |
| X-WAVE5 | 波次 0–3；仓不是 Wave 5 | 避免两套波号 |
| X-APPETITE | 只进人周 | 禁止混日历 |
| X-LISTING | 上架独立；未知可上架 | CONTEXT 已改；代码/测试未跟 |
| X-IA | 做壳可见差，不做五组重排 | 权限不砍；整组 IA 下一轮 |

---

## 2. 分诊表（DMD）

无来源不进。本期无工单/访谈/埋点。证据 = 对外承诺、Accepted 设计、现网可证伪。

| ID | 说法 | 类型 | 证据 | 处置 |
|---|---|---|---|---|
| DMD-01 | 官网只卖采集、定价卖四柱 | 真 | ops S-01 | spec FR-01；首句 Q-VOICE |
| DMD-02 | 卖 Excel | 真 | P-01；测例拒 xlsx | FR-03；xlsx 下一轮 |
| DMD-03 | Hero 大数 | 真 | S-03 | FR-02 |
| DMD-04 | Actor 店 | 伪解法 | S-04 无原声 | 真问题=出数 → FR-18；店下一轮 |
| DMD-05 | 注册断链 | 真 | S-05；Register 双剥 | FR-04 |
| DMD-06 | 出站无企业维 | 真 | S-06；query 无租户 | FR-13 |
| DMD-07 | 定价空头 | 真 | S-07 | 不变式；Q-PRICE |
| DMD-08 | 配额内部码 | 真 | Usage Alert | FR-12 |
| DMD-09 | 中转零曝光 | 真定位 | S-09 | 空头先删；Q-RELAY |
| DMD-10 | AGPL | 约束 | S-11 | Q-AGPL |
| DMD-11 | 双广场 / 四类专家 | 真 | S-12；S-V2-01 | FR-30 |
| DMD-12 | 丢掉 recommended | 真 | S-13；双金标 | FR-33 |
| DMD-13 | 一期订阅 | 真（D10） | 设计；无「我想装」原声 | Wave 1；不得写成用户强烈要求 |
| DMD-14 | 租户 admin=超管 | 真 | backend/qa | FR-06/07 必做 |
| DMD-15 | 入队/回流丢企业 | 真 | data-collector 全链 | FR-09/10 **不得降波** |
| DMD-16 | 候选占配额 | 真 | quota COUNT | FR-11 |
| DMD-17 | Key 在 git | 真 | sre 7 处 | FR-14 |
| DMD-18 | 无事件 | 真 | analyst 0 命中 | FR-15/43 |
| DMD-19 | 到期仍可登录 | 真 | miner/backend | FR-08（推翻旧「不新开」） |
| DMD-20 | Worker/零条目 | 真 | sre T1；IdleAutoClose | FR-18/19 进 Wave 0（推翻 Wave 4 stub） |
| DMD-21 | 专家团执行 | 二期 | CONTEXT | 不做 |
| DMD-22 | 支付/门户/分成 | 伪本期 | Non-Goals | Q-BILL 仅支付破例 |
| DMD-23 | 后台整组 IA | 真不整组进 | designer P0 vs 旧 T-31 | 可见差做；五组重排下一轮 |
| DMD-24 | 数仓/模型/评估集 | 真不可测 | warehouse/miner/algo | **N/A**；事件仍要 |
| DMD-25 | 六 Tab / 礼包 / unlist=停用 / enable-host | 过期 | D22–D29 | 七叶、不礼包、展示≠停用、无按钮 |
| DMD-26 | XSS 纯文本 | 已有 | SkillsSquare 测 | 先迁再删 |
| DMD-27 | LLM 闸未接线 | 真 | check 仅测试 | FR-12 |
| DMD-28 | 空缓存菜单全开 | 真 | frontend P-FE | FR-17 |
| DMD-29 | 首页失败装空 | 真 | designer F10 | FR-01.4 Wave 0 |
| DMD-30 | 官方认证 | 伪 | F-02 | 不做 |
| DMD-31 | 本机插件盘点 | 一次性 | 设计 n 小 | 定身份规则，不当 Reach |
| DMD-32 | 文档漂移 README | 一次性 | ops 转出 | 不进 FR |
| DMD-33 | 采集控制面任务/CSV | 已有 | README | 保留；补权限与出数环 |
| DMD-34 | grok WAU 三选一 | 伪口径 | analyst 否决 | 不进蓝图 |
| DMD-35 | 头修订 030 / 四张市场表 | 过期事实 | dba 头=027；五表 | 不写进产品 FR |
| DMD-36 | viewer 可扫金标 | 真冲突 | test_b1c | 改验收随 FR-06；同变更改旧用例 |

**伪需求未进 PRD：** 「用户都要 Power Market」「必须做 Actor 店」「上 AI 评分」「第四宿主市场」。

---

## 3. 从旧方案 / grok-files 吸收 vs 丢掉

### 吸收（不变式）

停止说谎；公司管理员 ≠ 超管；候选不计成果/WACT；上架≠验证≠订阅≠启用宿主；五类词表；订插件不带礼包；展示≠停用；出站无绑定则拒绝；渠道对租户 404 同形；密钥页不与 404 抢 oracle；WACT 唯一；事件名沿用 v1.2；host_compat NULL vs []；只读拒订。

### 丢掉

- 旧 FR 编号当现行冻结集
- Wave 4 出数 stub / 「本程序不改 compose」
- 治理台 6 Tab
- 「本波不新开到期登录」
- grok 第一可卖切片含发令牌、五波、日历一周、QUOTA 用户码、enable-host 当 Wave 1、WAU 三选一、ODS 表清单
- 把旧 contract v2.1 写成 v2 已塑形

### 相对旧 spec 的产品改判（本备忘要写清，避免被看成「漏抄」）

| 旧 | v2 |
|---|---|
| 出数在 Wave 4 stub | Wave 0 FR-18/19 |
| 到期登录不新开 FR | FR-08 |
| 后台不改菜单分组（连可见差一起降级） | 可见差必做；整组重排仍下一轮 |
| FR-70 工人空态后置 | 工人空态与编排验收进诚实波 |
| 评估集空目录可并行 Wave 0 | **不要**空 jsonl 票 |

---

## 4. 角色诊断我采信的产品约束

| 角色 | 采信 | 不采信为合同 |
|---|---|---|
| ops | M-01…M-15；七问不代选；禁止双北极星 | 把信号当用户投票 |
| designer | F1–F12 必须覆盖；七叶；F8 已订残留；D-SESSION 建议 | 四柱并列 Hero |
| architect | KEEP 拓扑/三层/候选 NOT NULL；OVERTURN 8h/NULL/六 Tab；Wave 1 11–14 人周 | 旧票号；6 Tab 合同句 |
| dba | 占位企业默认 platform；listed_at 默认保留；事件至少一次 | 表结构/DDL |
| backend | require_admin≠超管；门面必须转发企业；LLM 闸接线 | API 形状 |
| frontend | 七 Tab；NotFound 同形；XSS 先迁；动态菜单双源 | tokens hex |
| sre | Worker 必须出现在联调验收；密钥离树 | compose YAML |
| data-collector | 回流必须回查任务企业；零条目收尾；C 路径不是爬虫 | 新开 spider |
| analyst | v1.2 为底；拒绝 grok 回退 | 用任务表验收 WACT |
| warehouse/miner/algo | N/A 施工 | 任何效果百分数 |
| qa | 旧用例与冻结 FR 互斥，必须同变更改写 | 现网 1050 绿 = 覆盖 |
| qc | 未过闸当合同；X-*；票号分家 | 本文件当放行 |

Effort：Wave 0 在 architect 3–4 上 **+2–3**（出数环）。合计冻结集约 **16–21 人周**，不是 14.5 抄旧合同。

---

## 5. 开放问题（与 spec §9 同一张表）

操作者七问 **全部待确认：** Q-VOICE / Q-PRICE / Q-RELAY / Q-MARKET-USER / Q-BILL / Q-LLM / Q-AGPL。

另：Q-OPS-DUTY（商店值班人名）、Q-OPS-COLLECT（是否主动收样本）。

PM 已代冻且不再问的：到期登录、七叶、无 enable-host、用户可见禁码、解析不靠执行、占位企业、listed_at、事件至少一次、会话落后台、首页失败进 Wave 0、导出 100 条、公开非法类型失败、WACT 唯一。

---

## 6. 我做了什么 / 没做什么

| | |
|---|---|
| **做了** | 全新 spec/故事/蓝图；解开 X-*；DMD 分诊；出数环进 Wave 0；度量以 v1.2 为底 |
| **没做** | 代选七问；写表/接口/用例/日历；把旧 02-shape 转正；建仓/评估集 |

---

## 7. 自检

- [x] 无来源需求未进
- [x] 解法与问题分开
- [x] 七问句子未假装已选
- [x] 分诊不用 T-nn
- [x] 不是合同（合同在 `../spec.md`）
