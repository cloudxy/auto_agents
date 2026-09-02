# docs/plan · 方案索引

> **已执行方案已清理**（v2 总方案 E0+A(P1-P5)+B(M1-M4)+SaaS S1-S5、架构审计报告 2026-08、跨 Agent 记忆统一方案）——完整内容见 git 历史 `@50558b9`（清理前最后一个完整版本）。
> 惯例：方案执行完毕并通过验证后，从工作区清理，git 历史即档案；词汇沉淀于根级 `CONTEXT.md`，不可逆决策沉淀于 `docs/adr/`。

## 现行方案（未执行）

| 文档 | 主题 | 状态 | 工单 |
|---|---|---|---|
| [architecture-review-2026-09.md](./architecture-review-2026-09.md) | 全栈架构评审 · 7 个深化候选（SaaS 接线 P0 / 权限单真相源 / 管理闭环缺口等） | 待审核（候选 1/2/3 已排入 R 线） | `.scratch/platform-v3/` 44-50 |
| [capability-hub-p6.md](./capability-hub-p6.md) | 能力资产中心：skill / plugin / expert / expert_team 四类资产 + MCP 工具桥验证（ADR-0001） | 待终审 | `.scratch/platform-v3/` 51-59 |
| [db-design-pipeline.md](./db-design-pipeline.md) | 数据库设计流水线：AI 产出目标态 / 工具产出路径与行为判决（ADR-0002） | 待终审 | `.scratch/platform-v3/` 60-63 |

## 执行记录速览

- **第一批（工单 01-27）**：E0 工程基座 + A 技能中心 P1-P4 + B LLM 多平台 M1-M4 —— 全 resolved（2026-08-31/09-01）
- **第二批（工单 28-43）**：A-P5 市场采集 + SaaS S1-S5 —— 全 resolved（2026-09-01，后端 703 tests）
- **第三批（工单 44-63，进行中）**：R 修复线 + C 能力资产中心线 + D 数据库设计流水线线
