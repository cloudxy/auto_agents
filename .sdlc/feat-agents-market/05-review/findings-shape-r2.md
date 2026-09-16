# Findings · shape G-fresh r2（2026-09-15，最新快照）

## Snapshot
- 02-shape/contract.md = 675a2ba6a00fdfdb37c2cfa41fe3d271847b360f46cd58e61e29e9cb1cff2066（v1.1）
- 02-shape/db-spec.md = 826ec32e7eb0c03f7ed0bafe361634760ae022e7b64ed854f9be8fdc4fcb02bb
- schema.dbml / edge-states.md 未变（2e1eb82c / c3dc8c85）

## Verdict: **FAIL**（QA-7R 新 major 未豁免）

## r1 findings 处置判定
- QA-1/2/3/4/5/6/8 全部核实修复（行号+代码证据见 r2 评审全文）。
- QA-7 按方落实但引入 QA-7R（下）。

## QA-7R [major] expert 谓词过度排除：豁免全部 agents_hub agent 行
- contract.md:62 谓词 `EXISTS(capability_experts 侧行)` —— agents_hub.py:148-157 对每个同步 agent 行都建侧行，谓词实际把 18/18 hub agent 行（及未来全部）排除出 prune 候选；真正要保护的 expert 遗留行（无磁盘源）当前为空集。FR-02 复用场景（磁盘改名/移除）下 18 agent 行永久不可清 → 对账差恒 18、北极星不可达、T-03 负向断言以错误理由固化缺陷。
- 修复（manager 采纳 reviewer 方案）：谓词收窄 `asset_type='agent' AND EXISTS(…) AND file_path NOT LIKE '.agents/%'`（hub 行 file_path 恒 .agents/ 前缀，agents_hub_scan.py:46-54/:230）；T-03 夹具改 legacy 形态行验证「仍 live」+ 正向断言 hub 来源 agent 孤儿被 prune；同款 file_path 判别式同步写进 OQ-2 回退方案（:220）保持口径一致。

## QA-9 [minor] T-15 确认句 {n} 无执行前数据源
- contract.md:197 需执行前计数 vs API #2（:146）仅 POST。
- 修复（manager 裁定）：API #2 增 `dry_run=true` 查询参数，响应同构返回 pruned 预览（不落库）；T-15 弹窗打开时先 dry_run 取 {n}。

## QA-10 [minor] edge-states.md 对 T-15 失同步（manager 加票所致，designer 修）
- :473「FR-02 无 UI 票」/:489 OQ-D2 开放 与 contract T-15 事实矛盾；屏 4 无 prune 弹窗六态（loading/失败/零失源/确认句/取消/成功 toast）。
- 修复：designer 增补 FR-02 行 + 屏 4 prune 弹窗六态 + 失败文案。

## QA-11 [minor] effort 段 appetite 基数 5.5pw 无出处（spec=3-5pw）
- 修复：按 5pw 口径重述（超 0.75pw）+ 弹性组合说明（T-11 缩减/T-09 并入）。

## 处置
architect 返工 r2（第二轮，附 debug_protocol）：QA-7R + QA-9 + QA-11 + OQ-2 口径同步。designer 并行小修 QA-10（一轮，直接修）。修复后新快照重审。
