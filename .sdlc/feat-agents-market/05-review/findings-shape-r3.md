# Findings · shape G-fresh r3（2026-09-15，最新快照）

## Snapshot
- 02-shape/contract.md = b35a3a3150499efe6f1080214bcebe840cdb5c6ab4ae6054e22942aa3d46c2a0（v1.2）
- 02-shape/edge-states.md = 6d347382c405b178912e6f5b5712d978b8a23ebcc5c2fcad40ea6e2a0a7169d4（v1.1）
- 02-shape/db-spec.md = 826ec32e7eb0c03f7ed0bafe361634760ae022e7b64ed854f9be8fdc4fcb02bb
- 02-shape/schema.dbml = 2e1eb82c8027aef67ace4bd442fb9adfd89525c3f7ac0e70092233bc4a6d6564

## Verdict: **PASS**（0 major 未豁免；3 minor 留下游）

## 判定摘要
- QA-7R 修复核实（谓词 file_path NOT LIKE '.agents/%' 四要素齐 + 独立读码复核 + 18 行候选集算术闭合：首轮清 ~22 孤儿、plugin 复活 6、对账 166=磁盘 166）。
- QA-9（dry_run 四方一致）、QA-10（§7.7 全态 + 三处逐字句一致）、QA-11（5pw 口径算术复核）全过。
- v1.1→v1.2 / edge v1→v1.1 无新 major 矛盾。

## 遗留 minor（不阻塞，下游知悉）
- QA-12：edge-states §5.4/:517 OQ-D1 仍写「默认期望/开放」（contract AD-5c 已裁定豁免）——designer 下一轮触碰时一行同步。
- QA-13：contract 引 edge-states 行号漂移——下游以内容锚点为准，contract 下轮触碰改内容锚点。
- QA-14：谓词对 NULL file_path 的 SQL 语义（NOT LIKE 对 NULL 得 NULL → 不排除 → 入候选可清）——manager 裁定「NULL 视为可清」，T-03 夹具补断言。

## Manager 批复
- effort 双弹性组合后余 0.25pw 溢出：接受（appetite 为 manager 建议值，未触 7.5pw 停线）。

## 归档
findings-define-r1/r2/r3.md、findings-shape-r1/r2.md
