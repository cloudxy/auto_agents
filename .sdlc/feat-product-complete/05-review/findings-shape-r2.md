# G-新上下文审查报告

> 审查对象：feat-product-complete · 审查时间：2026-09-11 · 审查者：sdlc-reviewer（无记忆子代理）
> 阶段：shape G-fresh r2（contract v2 + ADR×5 + db-spec/schema.dbml + edge-states v2 对照 spec v1.5）· 结果：**pass（附条件）**
> 前序：define r6 报告已归档 findings-define-r6.md；shape r1 报告在 findings-shape-r1.md。

## Snapshot

各文件 sha256 由管理窗补算（reviewer 配置无 shell，未编造）。对象：02-shape/{contract.md v2, adr-0019/0020/0021(修订)/0022/0023(新), db-spec.md v2, schema.dbml v2, edge-states.md v2} + 01-define/spec.md v1.5。

## 核对结论（摘要）

- **FR→票全覆盖**：28 FR（C5+U10+A13）逐条有票（T-01..T-42）；FR-91 无票；92.8/92.9 落 T-24/T-35；无巨票；同文件冲突串行已注明（T-24×T-26、T-31→32→33、T-29→T-34、T-07×T-08）；appetite 校正 46-62 人日 ≈ 9-12.5 人周 < 21 停判线。
- **shape-r1 十条**：QA-01..10 全部核实已关（含 ADR-0021 v2 和解、ADR-0019 v2 单 Then、§7.4 真实 chat 夹具口径、SEC-11..14、Q-C-REG 入 §18）。
- **QA-20..24 注记**：T-09（20/21）、T-21（22）、T-03（23）、T-02（24）全在。
- **QA-40 幽灵项**：零建设，全文仅禁令出现。
- **db-spec**：alive_flag 生成列方案正确（MySQL 8 + 025 先例）；042/043 expand-contract；asset_import 两表 TENANT_EXEMPT 登记；EXPLAIN 原始输出诚实。
- **edge-states**：六态矩阵齐；FR-84 句式无第二套；X-QUOTA 零内码；页头规范六页；GWT 锚可回对。

## FINDINGS

### SHAPE-QA-01 陈旧票文件 T-01..T-23 滞留盘上（v1.2 时代），与 contract v2 状态互斥，含已被封死的 httpx 夹具
- 维度 3 | **major** | 证据：tickets/T-01.md:4（上游 spec v1.2）、T-09.md:6（QA-21 裸 200 夹具）、T-15.md:52（82.4 短句缺 FR-102 互锁）
- **处置（管理窗，已闭合）**：`02-shape/tickets/` 整体归档为 `02-shape/tickets-v1.2-stale-archived/`；本特征实施以 contract §11 票表为唯一票源（不重建票文件，仓库先例 feat-four-pillars-v2 同构）；实现包按票注入验收注记。

### SHAPE-QA-02 db-spec §12 把网关 spend 拉取写进 list_tokens 读路径，与 contract §7.4/ADR-0019 v2 冲突
- 维度 5+6 | **major** | 证据：db-spec.md:689、:751
- **处置（已闭合）**：dba 微修 v2.1（:689/:747 改写为「触发点=令牌详情/显式刷新；列表渲染只读本地列，禁止每行打网关」；旧短语 grep 零残留）。

### SHAPE-QA-03 edge-states 给经办保留 LLM 供应商行既有写权，spec v1.5 矩阵经办行只列「看」
- 维度 6+8 | minor | 证据：edge-states.md:902 vs spec.md:832
- **处置（管理窗裁决）**：spec 权限矩阵口径=**本特征权限增量**（FR-97 只改「设默认」归属），未列出的既有写面沿用现状；落 T-30 实现注记，不动文件。

### SHAPE-QA-04 T-36 验收注记缺 100.7/100.8 UI 锚
- 维度 2+6 | minor | 证据：contract.md:613 vs edge-states.md:1230/1243
- **处置**：随 T-36 实现包注入「100.7 失败原因逐条呈现、100.8 跳过标记（edge-states 导入向导）」。

### SHAPE-QA-05 edge-states 把 GWT-105.3 复述成「类型选择器不出现死类型」，杠杆错位
- 维度 2 | minor | 证据：edge-states.md:754 vs spec.md:700
- **处置**：随 T-42 实现包注入正确口径（所有可选类型均为活规则；选择器无需隐藏类型；验收=配了规则且命中条件成立→触发）。

### SHAPE-QA-06 queue_depth 命中记录 notifications.user_id 未钉
- 维度 6 | minor | 证据：db-spec.md:855 vs schema.dbml:392
- **处置（已闭合）**：dba v2.1 §16.6（默认=规则创建者；软删解析不出→不落命中行；未读徽标副作用一句）。

### SHAPE-QA-07 两组同文件并行未钉串行（T-12×T-18 提交弹窗/toast 面；T-11×T-31 NewApiOps.tsx）
- 维度 8 | minor | 证据：contract.md:579/590/578/608
- **处置（管理窗编排约束）**：T-12 与 T-18 不同批（先 T-12 后 T-18 或同作者）；T-11 在 T-31 结构定型后施工。另补：T-29×T-15 同动 App.tsx/AdminLayout → T-15 在 T-29 后。

## 已查维度

| # | 维度 | 结果 |
|---|---|---|
| 1 | 标准符合 | ✅ 28 FR 全票/FR-91 无票/零代选/零范围蔓延 |
| 2 | 标准质量 | ✅ 单 Then 纪律保持 |
| 3 | 证据有效性 | ⚠️ SHAPE-QA-01（已闭合） |
| 4 | 安全 | ✅ SEC-11..14/沙箱/DSN 封死 |
| 5 | 性能 | ⚠️ SHAPE-QA-02（已闭合） |
| 6 | 契约一致性 | ⚠️ SHAPE-QA-03/04/06（处置如上） |
| 7 | 合规 | ✅ 宪法红线逐条过 |
| 8 | 边界 | ⚠️ SHAPE-QA-07（编排约束已记） |

## 总计

blocker 0｜major 2（SHAPE-QA-01/02，附条件已全部闭合）｜minor 5（SHAPE-QA-03..07，处置完毕）

**结论：pass。shape 收口，进入 implement。**
