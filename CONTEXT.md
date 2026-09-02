# CONTEXT.md — 项目域词汇表（glossary）

> 工程技能（grilling / domain-modeling）的共享语言。输出命名域概念时用此表词汇；新概念随决策落定入此。
> 创建：2026-09-02（能力资产中心两轮拷问定案时首次建立）。

## 能力资产域（capability hub）

| 术语 | 含义 |
|---|---|
| **能力资产**（capability asset） | 平台级公共资产的四类统称：技能 / 插件 / 专家 / 专家团。统一目录（capability_assets）治理，`tenant_id` 恒 NULL（平台级豁免）。 |
| **技能**（skill） | 原子工具能力（"让 AI 能做某件事"）。形态：SKILL.md（frontmatter+正文）+ meta.yaml 治理快照。WorkBuddy 语义对齐。 |
| **插件**（plugin） | 打包分发单位：`plugin.json`（name/version/author/license）+ skills[] + mcp_servers + hooks + commands。对齐 zcode / Claude Code 插件格式。**未经平台验证（verify）不得分发**（ADR-0001）。 |
| **专家**（expert） | 人设 + 方法论 + 工具链的 Agent 型资产。canonical 格式 = Claude Code subagent（frontmatter name/description/tools + 正文 system prompt）。可捆绑技能[]与 MCP 引用。一期资产+导出，二期平台内召唤执行。 |
| **专家团**（expert team） | Team 型资产：团长专家（拆解/整合）+ 成员专家[] + 协作流程。一期定义与导出；执行引擎（团长拆解→并行→整合）二期。 |
| **MCP 工具桥**（MCP tool bridge） | 平台消费插件的运行时：MCP client（官方 Python SDK，stdio/HTTP）→ tools/list 登记 + tools/call 调用。双重用途：插件验证基座 + 平台 LLM 工具面。 |
| **插件验证**（plugin verification） | 分发前的平台自证伪管线：安装→连接→tools/list→抽样 tools/call→health_status/verify_detail 落库。模式同 LLM 探测/渠道探针。 |
| **候选**（candidate） | 市场采集产出的待审条目（spider_results.source=marketplace），人工闸门（approve/reject）后转正式资产。 |
| **适配器**（adapter） | 把资产分发到外部工具的安装脚本（capability-library/adapters/）：技能安装 / 插件安装 / 专家导出（如 `~/.claude/agents/*.md`）。 |

## 既有域（速览）

| 术语 | 含义 |
|---|---|
| 中转站（relay） | 外部 new-api 实例的外挂管控面（渠道额度调度/真伪探针），平台级基础设施。 |
| 租户（tenant） | SaaS 隔离单元；行级隔离经 tenant_context 事件钩子（tenant_scope / platform_scope）。 |
| 配额（quota） | tenants.quota 三类：任务并发 / 结果存储 / LLM token 月度；超限 429 QUOTA_EXCEEDED。 |
| 资产评分（asset scoring） | 四维 rubric（completeness/doc_quality/maintenance/real_world_effect）AI 建议 + 人工终评（人工权威）；tier S/A/B/C 派生。按资产类型可配维度集。 |
