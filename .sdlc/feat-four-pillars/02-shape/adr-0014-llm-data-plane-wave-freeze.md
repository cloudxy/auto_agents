# ADR-0014：本波冻结 LLM 数据面——规划走供应商表，中转旁路，验证器不变成运行时

> 状态：**accepted**
> 日期：2026-09-07｜决策者：/architect｜相关：FR-10 FR-07、NFR-04、开放问题 Q-LLM（**不代选长期网关**）
> 本文件 **整份替换** stale ADR-0014。长期网关选择仍开放。

## 背景

仓库里同时存在三条叙事：`llm_providers` + `llm_common`（规划器真用）；new-api 外挂巡检（与规划器零引用）；测试注释写「newapi 将被 LiteLLM 替换」但源码路由未挂（仅 pycache）。`mcp_bridge` 模块头宣称「平台 LLM 工具面二期」。若市场验证器或中转在本波再接成第四条调用链，三个月后无法拆。

Q-LLM（LiteLLM vs new-api vs 继续现状）是操作者问题，本 ADR **不选择长期网关**，只冻结 Wave 0/1 行为，避免默许第四条链。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 套餐 tokens 必须挡住真调用 | FR-10 |
| 平台 LLM 供应商写仅超管 | FR-07 |
| 不执行未信任第三方 hooks | NFR-04 |
| 操作者未选长期网关 | spec Q-LLM |

## 决策

Wave 0/1：

1. 规划 / 试采修复 / 技能评分 **只**经 `llm_chat` → `llm_providers`（既有叶子）。
2. 在该单点调用 **之前** 执行 `QuotaService.check_llm_tokens_month`（**Asia/Shanghai 自然月**）。
3. new-api **保持旁路运维面**：调度/探针/额度窗口。规划器不得 import `NewapiApiClient`。
4. `mcp_bridge` **仅**验证抽样 `tools/call`。禁止把 `call_tool` 扩成平台 Agent 运行时。
5. LiteLLM 替换 **不进本特征**（源码未挂路由，测试叙事视为另一特征）。

长期「中转是否成为规划 backend」留给 Q-LLM 关闭后的新 ADR。

## 备选与否决理由

### 备选 A：本波让规划 backend 可以是 new-api 渠道

**否决理由**：这是 Q-LLM 本身。未关闭前做成「已选定解法」违反 spec §9。规划器今日零引用 NEWAPI，接线不可逆。

### 备选 B：市场验证器同时当 LLM 工具面

**否决理由**：验证白名单内 `node/npx/python/uvx` 已是代码执行面。再对租户流量开放等于第四条 LLM 链 + 任意工具执行。NFR-04 listed ≠ trusted。

### 备选 C：本波切换 LiteLLM

**否决理由**：路由文件不在树内（仅 pycache 残骸）。替换是另一特征，测试里的「将被替换」不是本波范围。

### 备选 D：继续只用 provider 内存/Redis 预算，不接租户套餐

**否决理由**：FR-10 明确「只挡测试接口、不挡真实对话视为失败」。`check_llm_tokens_month` 今日仅测试调用。

## 证据

`backend/services/ai_planner/llm_client.py`：`llm_chat` 熔断读 `LLM.MAX_TOKENS_BUDGET`（约 287–289 行），`record_usage` 会带 `current_tenant_id()`，但 **不**调 `QuotaService.check_llm_tokens_month`。生产引用该检查函数 = 0（仅 `test_saas_quota.py` / `test_saas_byok.py`）。`skill_scoring_service.py` import `llm_chat`。

## 代价与风险

| 代价 | 缓解措施 |
|---|---|
| 中转与规划继续两本账 | Wave 0 定价不混写（FR-01/Q-RELAY）；值班路径只收权 |
| Redis 预算与套餐闸双闸 | 先套餐闸（产品数字）；provider 预算保留作成本熔断，不替代套餐 |
| Q-LLM 关闭后可能重接 | 本 ADR 写明复审条件，不把旁路写成永恒 |
| Redis 月度 field 历史无 tenant | dba P1 记债；本波执法走 `llm_token_usage` 表 |

套餐闸与 Redis 预算同时存在：用户看到的是套餐文案（FR-12）；provider 预算耗尽是内部熔断，对用户仍映射为「本月 LLM Token 已达上限」若套餐已尽，否则保留现有 BusinessException——**本波若套餐未尽而 provider 预算尽，文案不得出现 QUOTA_EXCEEDED 字样**，沿用现「预算已耗尽」业务消息。不在本波统一两本账（那是 Q-LLM）。

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/backend` | `llm_chat` 前套餐检查；禁止 market 调 call_tool 除 verify |
| `/qa` | A 额度尽、B 仍有：A 的规划被拒且不扣 B |
| `/sre` | 不把 new-api 当规划依赖探活 |

## 后续复审条件

操作者关闭 Q-LLM；或需要 MCP 工具面给规划器。必须新 ADR，禁止在市场票里顺手接线。

---

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-07 | proposed → accepted | 塑形 v2 采纳；Q-LLM 仍 open |
