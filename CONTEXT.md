# CONTEXT.md — 项目域词汇表（glossary）

> 工程技能（grilling / domain-modeling）的共享语言。输出命名域概念时用此表词汇；新概念随决策落定入此。
> 创建：2026-09-02（能力资产中心两轮拷问定案时首次建立）。
> 词汇修订：2026-09-08（中转站 = 平台 LLM 网关 LiteLLM Proxy；new-api 退役运行时）。2026-09-07b：Power Market D22–D29。权威产品设计：`/Users/xuyun/Documents/grok-files/power-market-design.md`。

## 能力资产域（capability hub / Power Market）

| 术语 | 含义 |
|---|---|
| **能力资产**（capability asset） | 平台级公共资产的 **五类平级** 统称：技能 / 插件 / 命令 / 智能体 / 专家团。统一目录（`capability_assets`）治理，`tenant_id` 恒 NULL（平台级豁免）。公开 API `asset_type` ∈ `skill` / `plugin` / `command` / `agent` / `team`。 |
| **技能**（skill） | 原子工具能力（"让 AI 能做某件事"）。形态：SKILL.md（frontmatter+正文）+ 可选 meta.yaml 治理快照。可独立上架、独立订阅。 |
| **插件**（plugin） | 磁盘上的打包单位：清单 + 其下的 skill / command / 智能体合集，以及 mcp_servers / hooks。对齐 zcode / Claude Code / Grok（根级 `plugin.json` 或 `.zcode-plugin/` / `.claude-plugin/` / `.grok-plugin/`）。**订阅插件不会带上子卡片。** 含 MCP 的包须验证通过后方可 enable-host；**上架是独立闸门**（ADR-0001 修订）。仓库内指针农场是 `.agents/plugins/<name>`（指向 `~/.zcode/local-plugins/<name>`）；`.grok/plugins` / `.claude/plugins` 只链启用子集，`capability-library/plugins` 链整农场。禁止复制内容。 |
| **命令**（command） | 斜杠命令。形态：`commands/*.md`（或清单声明的 command 文件）。**独立上架、独立订阅**，不是插件 JSON 里的附属字段。 |
| **智能体**（agent） | 人设 + 方法论 + 工具链。canonical = Claude Code subagent（`agents/*.md`：frontmatter name/description/tools + 正文 system prompt）。产品文案不再说「专家」。库表仍名 `capability_experts`（表名≠产品名词）。可引用技能；引用解析 **不看** 该技能是否上架。一期资产+导出，二期平台内召唤执行。 |
| **专家团**（team） | 团长智能体 + 成员智能体[] + 协作流程。公开 `asset_type=team`（库内旧值 `expert_team` 回填）。一期定义与导出；执行引擎二期。 |
| **上架 / 展示**（listing） | `listing_state`：未上架 / 已上架 / 预告。**未上架 = 商店列表、搜索、预告都没有，也不能从商店新订。** 不等于停用。 |
| **停用**（runtime stop） | 黑名单或软删：公开当不存在，运行时引用也跳过。与「未上架」不是同一闸。 |
| **合集边**（component） | `capability_components`：出处与运行时引用（插件→子资产、智能体→技能、专家团→智能体）。**不是**安装礼包。 |
| **MCP 工具桥**（MCP tool bridge） | 平台消费插件的运行时：MCP client（官方 Python SDK，stdio/HTTP）→ tools/list 登记 + tools/call 调用。双重用途：插件验证基座 + 平台 LLM 工具面。 |
| **插件验证**（plugin verification） | 含 MCP 时：安装→连接→tools/list→抽样 tools/call→health 落库。无 MCP → `unknown`，允许上架，不代替 enable-host。 |
| **候选**（candidate） | 市场采集产出的待审条目（spider_results.source=marketplace），人工闸门（approve/reject）后转正式资产。 |
| **适配器**（adapter） | 入站：索引外部树。出站：把已治理资产投影到宿主（技能安装 / 插件 symlink / 智能体导出如 `~/.claude/agents/*.md`）。开发工作区里：`.grok/plugins` / `.claude/plugins` 是启用子集；`capability-library/plugins` 是整农场扫描入口。 |

## 仓库协作层（开发者工作区，不是产品运行时）

| 术语 | 含义 |
|---|---|
| **开发协作中枢** | `.agents/`：本仓库写代码时加载的项目 skill 与第三方插件指针。契约见 `.agents/README.md`。 |
| **产品目录** | `capability-library/`：能力市场扫描/治理的内容树。与中枢分开，不要把产品目录当成 IDE 技能库。 |
| **Grok/Claude 启用子集** | `sdlc-workflow` / `dev-team` / `drama-skills` / `oh-story`。`superpowers` / `mattpocock-skills` 只留在农场给扫描（已含于 `dev-team`）。 |

## 数据库设计域（D 线）

| 术语 | 含义 |
|---|---|
| **数据契约 Spec**（db spec） | S0 产物：实体/关系/业务唯一键 + **访问模式**（Top-N 查询与频率）+ 容量预估 + 一致性边界 + 保留策略。索引由此推导，不由 LLM 脑补。 |
| **访问模式**（access pattern） | 业务真实的查询清单与频率——索引设计的唯一合法输入（ADR-0002）。 |
| **DBML IR** | S1 中间表示（*.dbml，holistics/dbml 标准，pydbml 解析）：可 lint / 可 diff / 可渲染 ER 图。 |
| **行为验证环**（behavior verification loop） | S4：真实 MySQL 上逐迁移 upgrade/downgrade + EXPLAIN access type 断言 + 约束注入（唯一键/FK/NOT NULL 拒脏）。demo 与工业标准的分水岭。 |
| **expand-contract** | 破坏性变更（drop/rename/类型收窄）的安全迁移法：先扩展（新旧并存）→ 迁数据 → 后收缩；lint 强制拆分。 |
| **目标态 / 路径**（target state / path） | ADR-0002 分工：AI 产出目标态（Spec/DBML/ORM），确定性工具产出路径（autogenerate 迁移）与判决（EXPLAIN/约束注入）。 |

## 计费 / LLM 接入

| 术语 | 含义 |
|---|---|
| **计费**（billing） | 套餐下单 + 平台超管人工确认收款；无支付宝/微信网关。渠道 `offline` / `alipay` / `wechat` 只是下单标记。 |
| **LiteLLM sidecar** | compose profile `litellm`，不进主 venv。`LITELLM.ENABLED` / `PROXY.ROUTE_INTERNAL` / `ADMIN.ENABLED` **默认关**。 |
| **交付 webhook** | 任务终态回调租户 URL；租户 opt-in（`PUT /tenants/me/delivery-webhook`），默认关。 |

## 前端 / 契约门禁

| 术语 | 含义 |
|---|---|
| **OpenAPI golden** | `backend/tests/openapi_routes_golden.txt`。增删 HTTP 路由必须改此文件，否则 `test_openapi_routes_golden.py` 红。 |
| **admin Playwright 冒烟** | 登录 → 仪表盘 → 用量 → 成员。先 `CI= npm run build -w admin`，再 `CI=1 npm run e2e -w admin`。端口 / `NO_PROXY` / 记住我见 `.claude/memory/playwright-admin-e2e.md`。 |

## 既有域（速览）

| 术语 | 含义 |
|---|---|
| 中转站（relay） | 平台 LLM 网关（**LiteLLM Proxy**）+ 本平台值班编排（渠道额度窗口 / 真伪探针）。new-api 为 **已退役运行时**，不与 LiteLLM 长期双通道并存。租户渠道组 / 虚拟令牌仍待产品拍板，不发给租户。 |
| 渠道 | 用户文案可仍叫「渠道」；值班列表来自网关侧模型/部署，不是 new-api channel。 |
| 令牌（平台路径） | 网关虚拟钥匙，**不发给租户**，直至租户中转 SKU 另开需求。 |
| 租户（tenant） | SaaS 隔离单元；行级隔离经 tenant_context 事件钩子（tenant_scope / platform_scope）。 |
| 配额（quota） | tenants.quota 三类：任务并发 / 结果存储 / LLM token 月度。内部业务码可以是 `QUOTA_EXCEEDED`；**用户可见文案不得渲染该码或裸 429**。 |
| 资产评分（asset scoring） | 四维 rubric（completeness/doc_quality/maintenance/real_world_effect）AI 建议 + 人工终评（人工权威）；tier S/A/B/C 派生。按资产类型可配维度集。 |
