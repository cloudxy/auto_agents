# ADR-0018：分发 = 商店上架；验证 ≠ 启用到宿主（supersedes ADR-0001 该行）

> 状态：**accepted**
> 日期：2026-09-07｜决策者：/architect｜相关：FR-26、D6/D10/D21、spec §9.2 QA-10
> 本文件是塑形 v2 **新建**。它 **supersede** CONTEXT.md / ADR-0001 中「未经平台验证（verify）不得分发」这一行的产品语义，不是删除 ADR-0001 全文。

## 背景

今日 CONTEXT：「插件未经 verify 不得分发」。实现：无 MCP → `health_status=degraded`；Admin 文案「插件经 MCP 验证后方可分发」。Kimi 托管插件多数无 `mcpServers`，若坚持「未 verify 不得 listed」，整个 Kimi 源无法上架。

设计与 spec 已冻：listed ≠ trusted ≠ enabled ≠ 已订阅。无 MCP 的包验证=`unknown` 仍可上架。含 MCP 的包须验证通过后方可 **启用到宿主**。Wave 1 **不交付**「启用到宿主」按钮（FR-26）。

旧测试钉 `degraded`。不写 ADR，实现会在「遵守 CONTEXT」与「遵守 D6/FR-26」之间来回改。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 上架是产品闸，不要求 MCP healthy | D6 / FR-26.2 |
| 订阅 ≠ 已在宿主运行 | D10 / FR-26.1 |
| 不代写 ZCode 配置 | D21 |
| 不执行未信任第三方 hooks | NFR-04 |
| 无 MCP 允许 listed | 设计 ADR-0001 修订表 |

## 决策

| 概念 | 规则 |
|---|---|
| listing（分发到商店） | 产品上架。**不**要求 MCP healthy。无 MCP ⇒ `unknown` + 允许 listed |
| enable-host / 「分发到可执行宿主」 | 声明了 `mcp_servers` ⇒ 必须 `healthy`；无 MCP ⇒ `unknown` 即可。**Wave 1 不交付该按钮与 API** |
| `degraded` | **仅**「声明了 MCP 但探测不完整/失败」 |
| `down` | 连接失败 |
| `unknown` | 未声明 MCP，或尚未跑 verify |
| 租户订阅 | 看 listing=listed ∩ 治理 ∩ 许可；**不**看 health |

Admin 文案改为：「含 MCP 的插件须验证通过后方可启用到宿主；上架是独立闸门。」Wave 1 详情不得写「已在你的宿主里运行」。生产 `HOST_PROJECTION.ENABLED=false`。

## 备选与否决理由

### 备选 A：继续「未经 verify 不得 listed」

**否决理由**：Kimi 16 个托管插件多数无 MCP，会整源不可上架。与 D6/FR-26.2 冲突。spec §9.2 已冻分发=上架。

### 备选 B：Wave 1 做完整 enable-host（设计 PR8 原文）

**否决理由**：FR-26 / GWT-26.1 明确无该主按钮。D21 禁止写 ZCode config。做了就变成「平台代启用」，与「安装到本机是说明」两动词冲突。

### 备选 C：上架前强制跑 verify，无 MCP 也标 healthy

**否决理由**：把「没东西可探测」标成健康，商店会显示虚假担保（F-05 / NFR-04）。`unknown` 是诚实态。

## 证据

`plugin_service` 无 MCP → `degraded`（backend 诊断 4.5）。设计 §ADR-0001 修订表与 spec QA-10 已对齐。Wave 1 无 `POST enable-host` 路由（全库 0 命中）。

## 代价与风险

| 代价 | 缓解措施 |
|---|---|
| CONTEXT 与代码文案短期双源 | PR9 改 CONTEXT 该行，指向本 ADR |
| 旧测试钉 degraded | 与健康枚举变更同 PR 改 `test_b1c` / `test_mcp_bridge` |
| 访客可能把「已上架」当成「官方担保可跑」 | 详情禁止「已在宿主运行」；NFR-04 验证抽样不是担保 |

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/backend` | verify 无 MCP → unknown；listing 不看 health |
| `/frontend` | 去掉「验证后方可分发」；折叠安装说明 |
| `/qa` | GWT-26.2：unknown 可上架；无启用到宿主按钮 |
| `/ops` | PR9 改 CONTEXT |

## 后续复审条件

若产品要做「启用到宿主」按钮（完整设计 PR8），新 ADR 描述投影与权限；不得静默在市场票里加路由。若操作者要恢复「未 verify 不得上架」，走变更流程重开 D6。

---

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-07 | proposed → accepted | 塑形 v2；supersede CONTEXT/ADR-0001 分发行 |
