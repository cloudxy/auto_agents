# Findings · shape G-fresh r1（2026-09-15，最新快照）

## Snapshot
- 02-shape/contract.md = 984a63d5bbb7fc91d9d5fa1e317077b9a0c5af7812fea51150538834fb31dfa6
- 02-shape/db-spec.md = 0e68dbb50fc503dc709e15fb808bb4a4343929a5e2f6c3b44e5f4e07c8ce9078
- 02-shape/schema.dbml = 2e1eb82c8027aef67ace4bd442fb9adfd89525c3f7ac0e70092233bc4a6d6564
- 02-shape/edge-states.md = c3dc8c858e1cc5191b3478e298d8df8d858c9fbe1bd53315596fd626af7fc2ec

## Verdict: **FAIL**（4 major 未豁免）

## QA-1 [major] OQ-D1 裁定未落实：预览豁免 listed 过滤三处口径不一致
- contract.md:78（AD-5c 仅跳闸）vs :152（API #8 无预览分支）vs edge-states.md:241/488（踢回 architect）；代码证实闸与 listed 是两道检查（service.py:237 vs :241）。
- 修复：AD-5c 增「preview=True 时 detail/media 跳过 listed 过滤（租户/匿名仍 404）」；API #8 错误列加预览分支；T-04 测试清单补「管理员可见 unlisted + 提醒标签」「租户/匿名不变」断言。

## QA-2 [major] T-15（prune 治理面按钮）未入票表/覆盖矩阵
- 票表仅 T-00..T-14（contract.md:181-196），FR-02 行仅 T-03（:204）。
- 修复：增 T-15（lane=ui，依赖 T-03，二次确认弹窗用 edge-states.md:489 句式「将下线 {n} 个无磁盘来源的资产」）；§8 FR-02 补 T-15；effort 段同步。

## QA-3 [major] AD-6 仍携带 MySQL 非法语法 DESC NULLS LAST
- contract.md:83 vs db-spec.md:306（已明示必须 COALESCE(cnt,0) DESC）。
- 修复：AD-6 改 COALESCE 并引用 db-spec §9。

## QA-4 [major] GWT-03.6/03.7/03.8 无票锚
- 15 票 GWT 锚列均无这三条（spec v1.1 QA-2 专门补的验收句）；OQ-D1 豁免落地后 03.7 成为必须显式回归的负向用例。
- 修复：03.7/03.8 写入 T-04 测试清单（点名）；03.6 锚入 T-08 或 T-11 验证列。

## QA-5 [minor] 事件锚点指错文件
- contract.md:40 emit_product_event 实际在 product_event_service.py:74（market_events.py 只是常量+封装）。修复：锚点改正。

## QA-6 [minor] featured 列型散文口径不一（tinyint vs smallint）
- contract.md:162「tinyint(1)」+ db-spec.md:63/68 自相矛盾；迁移/DBML/实测三方=smallint。修复：统一 smallint。

## QA-7 [minor] AD-3 prune 的 expert 遗留排除无判别谓词
- contract.md:62；物理为 agent 型且无磁盘源的 expert 遗留行会被误剪（候选集 18 行 agent 型 ∩ source_id NULL）。
- 修复：指明谓词（排除存在 capability_experts 侧行/detail_id 非空的 agent 行）+ test_prune_missing.py 负向断言。

## QA-8 [minor] 目录导入未要求相对路径穿越清洗
- contract.md:66-73 webkitRelativePath 直接用于判型/落盘，未拒绝 `..`/绝对路径/反斜杠。
- 修复：hub_import 判型/落盘前拒绝含非法分量的路径段（入跳过清单）。

## 处置
architect 返工修 QA-1..QA-5 + QA-7 + QA-8（全部 contract 侧）；dba 同步修 QA-6（db-spec 措辞）。edge-states.md 无 major 无需改。修复后出新快照重审。
