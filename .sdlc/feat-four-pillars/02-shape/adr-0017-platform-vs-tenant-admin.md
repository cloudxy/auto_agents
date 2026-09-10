# ADR-0017：平台写面用 `is_platform_admin`；租户 admin 不再等于平台超管

> 状态：**accepted**
> 日期：2026-09-07｜决策者：/architect｜相关：FR-06 FR-07、NFR-05、D14、`contract.md` §1.5
> 本文件是塑形 v2 **新建**。

## 背景

角色双轨已经存在：`users.role`（admin/operator/viewer）与 `is_platform_admin` + `tenant_role`。`require_admin = require_role("admin")` 让 **租户公司管理员** 通过中转写、平台 LLM 写、技能扫描写。`capabilities.py` 更宽：`require_login`，viewer 可扫目录并拉起 MCP。前端 `ProtectedRoute requireAdmin` 认 `role==='admin' \|\| is_admin`，登录投影 **无** `is_platform_admin`。

测试把宽守卫当成成功合同（`test_b1c` viewer scan 200）。spec §9.2 已冻：Wave 0 收紧中转/LLM 写权，不止市场。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 平台目录写仅超管 | FR-06 |
| 渠道窗口与平台 LLM 写仅超管 | FR-07 |
| 租户渠道页隐藏，直打同 404 | GWT-07.3 |
| 租户 BYOK 仍要能管自己的供应商 | 既有 llm_providers Mixin 可空平台行 |
| 不改 JWT 协议 | 身份快照已有 `is_platform_admin` |

## 决策

1. 平台目录写、渠道窗口写、平台 LLM 供应商写（含激活平台行）、源/上架/许可放行：**`require_platform_admin`**。
2. 租户公司管理员保持：成员、本企业配额申请出口、经办能做的采集/订阅。
3. 租户 **自有** LLM 供应商行（`llm_providers.tenant_id = 当前租户`）的 CRUD/激活：仍由租户经理（`require_tenant_manager`）执行，**不是**平台超管专属。平台行（`tenant_id` NULL）的写 = 仅超管。
4. 前端：登录响应投影 `is_platform_admin`。渠道/中转路由对非超管 **同 404**（导航不出现，直打不是道歉式 403）。`/llm` 对租户保留 **自有供应商** 面；平台供应商写控件隐藏。
5. 同 PR 改测试合同：viewer/租户 admin 扫描 → 403；租户 admin 改渠道额度 → 拒绝且额度不变。

## 备选与否决理由

### 备选 A：只收市场写，中转/LLM 仍 `require_admin`

**否决理由**：spec 已关旧 Q-AUTH，选「不止市场」。否则市场严、中转松，护栏「非超管改渠道成功次数=0」失败。

### 备选 B：租户完全不能进 `/llm`

**否决理由**：BYOK 是已兑卖点（定价免费档写「平台公共 LLM」、专业档写 BYOK）。FR-07 冻结的是 **平台** 供应商。一刀切会误伤租户自有行。

### 备选 C：新做 RBAC 按钮码 Depends，Wave 0 才收权

**否决理由**：今日无 `require_permission`。FR-06/07 用户可见行为是超管拒绝，不依赖按钮码表。`btn:market:*` 随 Wave 1 PR4 种子；Wave 0 不阻塞于权限矩阵大迁移。

### 备选 D：渠道页对租户道歉式 403

**否决理由**：GWT-07.3 明确与「页面不存在」相同，禁止道歉式 403。词表 §3.2：平台专属对租户隐藏。

## 证据

`deps.py:116` `require_admin = require_role("admin")`；`require_platform_admin` 已存在（119–125 行）。`newapi.py` 文件头「全部 require_admin」。`capabilities.py` scan-plugins `Depends(require_login)`。`ProtectedRoute.tsx:22`。`frontend/admin/src/services/auth.ts` `is_admin` 无 `is_platform_admin`。

## 代价与风险

| 代价 | 缓解措施 |
|---|---|
| `test_b1c` 等会红 | 与实现同 PR 改合同，禁止先合代码后改测试 |
| `/llm` 页要拆「平台行 vs 租户行」 | 列表已有 tenant 维；UI 按 `is_platform_admin` 藏激活平台行 |
| 超管无企业空间不能订阅 | FR-20.3 已冻；不要给超管开「模拟租户」后门 |

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/backend` | T-02 T-03 改 Depends；平台 vs 租户 LLM 行分流 |
| `/frontend` | T-04 登录字段、菜单隐藏、直打 404 |
| `/qa` | 真 JWT；禁止用 admin_client 冒充超管测渠道 |

## 后续复审条件

若引入完整 `require_permission("btn:…")` 后端执法，新 ADR 描述与本决策的关系——按钮码是加严，不能把超管守卫改回 `require_admin`。

---

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-07 | proposed → accepted | 塑形 v2 新建 |
