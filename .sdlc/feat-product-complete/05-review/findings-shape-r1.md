# G-新上下文审查报告（shape r1，归档）

> 审查对象：feat-product-complete · 2026-09-11 · shape G-fresh r1
> 结果：fail · blocker 3 · major 6 · minor 1
> 原因：审查时 spec 已是 v1.3（Wave A FR-93…105），contract/tickets 仍按 v1.2 的 15 FR。

## Snapshot

- path: 02-shape/contract.md
  sha256: 2572b6360e9388e1c1c5c98a340f87e146ab8b4f55c1a7d5a9b627904477ee5a
- path: 01-define/spec.md（审查时）
  sha256: 9d394667651359ae7a880bb7434ab59989f0b083915c9bf3123dd4499b7ebb96

## FINDINGS（摘要，全文见审查子代理回传）

### QA-01 Wave A FR-93…105 与 GWT-92.8/92.9 缺票 — blocker
### QA-02 T-15/ADR-0021 把 /enterprise 焊成超管也不开，与 FR-95 互否 — blocker
### QA-03 GWT-93.5 软删标识释放，users UNIQUE 未建模 — blocker
### QA-04 GWT-60.3 与 ADR-0019「下一次打开页」两套 Then — major
### QA-05 httpx 200 夹具可空心勾 60.3 — major
### QA-06 Wave A 导入/恢复/平台入队无 [SEC-n] — major
### QA-07 GWT-82.4 超管无企业空间 vs FR-102 平台租户 — major
### QA-08 list_tokens 每行打网关 vs P95 100ms — major
### QA-09 GWT-51.5/51.9 双 Then vs 六态隐藏 — major
### QA-10 Q-C-REG 未进 contract 开放问题表 — minor

HATADVANCE stay shape until spec v1.3 define G-fresh + contract 扩展。
