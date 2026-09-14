# Domain Docs

How agents should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root（域词汇表）
- **`docs/adr/`**：只读与当前改动相关的 ADR
- 宣称对账：`docs/claims.md`

If a listed file does not exist, **proceed silently**. Don't flag absence; don't suggest creating docs up front. New glossary terms go into `CONTEXT.md` when a decision actually lands.

## File structure

Single-context repo:

```
/
├── CONTEXT.md
├── docs/adr/
├── docs/claims.md
├── docs/agents/          # 本文件；issue-tracker / triage 约定
├── backend/  scrapy/  platform_core/
├── frontend/{admin,official,shared}/
└── capability-library/
```

已执行计划不入库、不在此挂索引。工单在 `.scratch/<feature>/`（见 `issue-tracker.md`）。

## Use the glossary's vocabulary

When output names a domain concept (issue title, refactor, hypothesis, test name), use the term as defined in `CONTEXT.md`. Don't invent synonyms the glossary already named.

If the concept isn't in the glossary yet: either you're inventing language (reconsider) or it's a real gap (add a row to `CONTEXT.md` when the decision is settled).

## Flag ADR conflicts

If output contradicts an existing ADR, surface it rather than silently overriding:

> _Contradicts ADR-0007 (transaction ownership), but worth reopening because…_
