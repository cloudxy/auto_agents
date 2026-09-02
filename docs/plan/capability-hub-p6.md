# 能力资产中心（P6）方案 · Capability Hub

> 定位：把"技能管理中心"升级为**能力资产中心**——skill / plugin / expert / expert_team 四类资产的统一治理、验证、分发与展示。
> 标杆对照：WorkBuddy（专家=人设+方法论+工具链；专家团=团长拆解→并行→整合）、zcode/Claude Code 插件（打包分发单位）、MiniMax 插件市场（业界正走向统一插件规范）。
> 基线：`474089e`（43 工单全落地）+ [`architecture-review-2026-09.md`](./architecture-review-2026-09.md)（评审候选）。
> 状态：**待终审**——两轮拷问 12 项决策已锁，拆票见 `.scratch/platform-v3/`。

---

## 1. 产品原则与十二项定案

**核心原则（ADR-0001）**：平台不能自行验证的插件，不得分发给用户——MCP 工具桥既是运行能力，更是**验证基座**（安装→连接→tools/list→抽样调用→健康落库，模式同 LLM 探测/渠道探针）。

| # | 决策 | 取值（两轮拷问锁定） |
|---|---|---|
| D1 | 资产建模 | **统一目录层**：`capability_assets`（name/type/status/tier/评分/来源/similar_to）+ 类型化细节表；治理字段全部上移 asset 层 |
| D2 | 插件运行语义 | 治理+分发 **+ 平台消费（MCP 工具桥）**；hooks/commands 只登记不执行 |
| D3 | 专家执行位置 | 一期 (a) 资产+导出（adapters 分发）；二期 (b) 平台内召唤对话 + (c) 专家团编排（团长 LLM 拆解→并行→整合，复用 asyncio 范式与 LLM 解析器） |
| D4 | 专家 canonical 格式 | Claude Code subagent 格式（frontmatter name/description/tools + 正文 system prompt）；WorkBuddy 概念（方法论/工具链）映射其上 |
| D5 | 目录泛化 | `skills-library/` → `capability-library/`（git mv 保历史；下分 skills/plugins/experts/teams；LIBRARY_ROOT/adapters/manifests/sync.sh 一次改齐） |
| D6 | 市场采集 | **本期完成**四类资产同构：采集→候选→审核管线（harvester 扩插件源/专家源） |
| D7 | 排期 | 与修复线（评审候选 1 SaaS 接线 P0 / 候选 2 权限 / 候选 3 🐞）**并行**，双线拆票（`.scratch/platform-v3/`） |
| D8 | 管理面/官网 | admin 技能中心→**能力中心**（四类 Tab）；官网 技能广场→**能力广场**（四类 tab） |
| D9 | 平台消费深度 | **MCP 工具桥**：MCP client（官方 Python SDK，stdio/HTTP）→ tools/list 登记 + tools/call 可调，桥到平台 LLM 工具面；hooks 执行属安全悬崖（沙箱/签名体系），本期坚决不做 |
| D10 | 存量并入 | skills 三表**原地保留**为 skill 细节；迁移回填 asset 行（type=skill）；评分历史泛化（reviews 挂 asset_id）；meta.yaml 写回零破坏 |
| D11 | 评分 rubric | 四维默认，按资产类型可配维度集 |
| D12 | 工单目录 | `.scratch/platform-v3/`（编号续 44-59，双线） |

---

## 2. 能力资产模型

```
能力资产中心（capability hub）
├── skill        原子能力（现有 skills 域整体降为 skill 细节：SKILL.md + meta.yaml + 评分/矫正/矩阵）
├── plugin       打包单位：plugin.json + skills[] + mcp_servers + hooks + commands
│                （对齐 zcode/Claude Code 插件格式；平台经 MCP 工具桥验证后分发）
├── expert       人设 + 方法论 + 技能捆绑[] + 可选 MCP 引用
│                （canonical = subagent 格式；导出 ~/.claude/agents/*.md / codex profile）
└── expert_team  团长专家 + 成员专家[] + 协作流程（一期定义与导出；执行引擎二期）
公共底座（全部复用/泛化自现有 skill 域）：
  评分治理（rubric 按类型）/ 状态机（六态+blacklist）/ 市场采集→候选→审核 /
  官网广场（四类 tab）/ 适配器矩阵（技能安装 → 插件安装/专家导出扩列）/ AI similar 建议
```

与 WorkBuddy 概念映射：Skill=工具能力 ✓；专家=Agent 型（人设+方法论+工具链）✓；专家团=Team 型 ✓；MCP=工具链（我们经插件承载）✓。

## 3. 数据模型（sketch，DDL 细节留实施拷问）

```
capability_assets            —— 统一目录（治理真相源，四类共用）
  id, asset_type('skill'|'plugin'|'expert'|'expert_team'),
  name, title, description, category, industries,
  status(六态+blacklist), source_type, source_url/author/imported_at,
  content_hash, score/ai_suggested_score/rubric_human/ai, tier,
  reviewed_by/at/notes, similar_to(同类型内), file_path, sync_state,
  tenant_id(NULL 预留，平台级公共资产，进豁免白名单), raw_meta, timestamps
  UNIQUE(asset_type, name)

capability_plugins（插件细节）
  asset_id FK, version, author, license, manifest(plugin.json 原文),
  skills[](内嵌技能名/资产引用), mcp_servers JSON(登记), hooks JSON(登记不执行),
  commands JSON(登记), health_status, last_verified_at, verify_detail JSON

capability_experts（专家细节，subagent canonical）
  asset_id FK, persona_md(正文=system prompt), tools[](frontmatter),
  skills[](捆绑的技能资产), mcp_refs[], model_pref

capability_teams（专家团定义，一期无执行态）
  asset_id FK, leader_expert_id, members[](expert 资产), workflow_md(协作流程)

泛化改造：skill_reviews 加 asset_id（存量回填，四类共用）；
         skill_jobs 语义升级 capability_jobs（job_type 已通用）；
         skills 三表保留为 skill 细节（评分字段读 asset 层，meta 写回逻辑复用）
```

## 4. API 面（增量）

| 端点 | 说明 |
|---|---|
| `GET /capabilities`（admin） | 统一列表：type/category/status/tier 筛选 + 分页（替代 /skills 读路径，旧端点保留兼容） |
| `GET /capabilities/{type}/{name}` | 统一详情：治理字段 + 类型化细节投影 |
| `POST /capabilities/scan` | 扫描 capability-library 四子目录（plugin 解析 plugin.json；expert 解析 subagent frontmatter） |
| `POST /capabilities/plugins/{name}/verify` | **插件验证管线**：MCP 连接→tools/list→抽样 tools/call→health_status/verify_detail 落库（未验证 plugin 默认不分发——ADR-0001） |
| `GET /public/capabilities?type=` | 官网能力广场（白名单按类型投影） |
| 候选审核 / similar-suggest / rescore / manifests | 全部按 asset_type 泛化复用 |

## 5. MCP 工具桥（平台消费，D9）

- 依赖：`uv add --package auto-agents-backend mcp`（官方 Python SDK，asyncio 原生）；
- `backend/services/mcp_bridge.py`：connect（stdio/HTTP）→ tools/list 登记 → tools/call；
- 双重用途：① 验证管线（上表 verify 端点）；② 平台 LLM 工具面——专家（二期召唤执行）/AI 规划器可调插件带的工具；
- 安全边界：stdio 命令白名单（配置允许的可执行文件）、全程超时、不 shell、hooks/commands 只登记不执行（D2/D9）。

## 6. 阶段切片（P6 线，工单 51-59；修复线 44-50 见 spec）

| 工单 | 内容 | Blocked by |
|---|---|---|
| 51 C1 | 目录泛化 git mv + LIBRARY_ROOT/adapters/manifests/sync 改齐 | — |
| 52 C2 | capability_assets 契约 + 迁移 018 + skills 回填 + reviews 泛化 + GET /capabilities | — |
| 53 C3 | 插件资产域（细节表+manifest 解析+扫描+CRUD） | 52 |
| 54 C4 | MCP 工具桥 + 插件验证管线（健康落库+安全白名单） | 53 |
| 55 C5 | 专家资产域（subagent canonical+细节表+扫描+CRUD+导出 adapters） | 52 |
| 56 C6 | 专家团定义层（team 细节表+CRUD+导出） | 55 |
| 57 C7 | 采集管线四类同构（harvester 扩源：zcode marketplace/awesome-claude-plugins/MiniMax 页/专家源；候选审核泛化） | 55 |
| 58 C8 | 治理泛化（rubric 按类型 + similar/状态机泛化） | 52 |
| 59 C9 | admin 能力中心（四类 Tab）+ 官网能力广场（四类 tab + 公开 API 白名单按类型） | 56 |

二期预留（不拆票）：C10 平台内召唤专家（对话）+ C11 专家团编排引擎（团长拆解→并行→整合）。

## 7. 并行修复线（工单 44-50，源自架构评审）

44 R1 BackgroundSession 后台会话深模块 → 45 R2 任务链路接线（enqueue/consumer 带 tenant_id）→ … → 50 R7 租户禁用 bug。详见 `.scratch/platform-v3/spec.md`。

**并行安全性**：能力资产为平台级公共资产（tenant_id 恒 NULL，进豁免白名单），与 SaaS 接线修复无表级冲突；前端双线各改各页。

---

*生成：2026-09-02 · 两轮拷问 12 决策锁定 · 词汇入根级 `CONTEXT.md`，验证原则入 `docs/adr/0001`*
