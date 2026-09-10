# ADR-0017：平台写面 = is_platform_admin；租户 admin ≠ 超管

> 状态：**accepted**
> 日期：2026-09-08｜决策者：/architect｜相关：FR-06 / FR-07 / FR-17；PIT-2

## 背景

`require_admin = require_role("admin")` 放行 **租户公司管理员**。能力写面甚至 `require_login`（viewer 可扫）。前端 `ProtectedRoute` 认 `role==='admin' \|\| is_admin`。渠道 API 全部 `require_admin`。结果：商店越严、中转越松。`require_platform_admin` 已存在且 `/admin/tenants*` 在用。

**触发这个决策的约束**：

| 约束 | 来源 |
|---|---|
| 扫描/验证/渠道窗口/平台模型/源与上架仅超管 | FR-06 |
| 租户直打渠道页与「页面不存在」同形，不是道歉 403 | FR-07.3 |
| `/llm` 不整页 404；本企业供应商可写 | FR-07；GWT-06.5 |
| 空缓存不得全开写面也不得整站空白 | FR-17 |
| 改守卫必须同 PR 改测试 | PIT-2 |

## 决策

平台专属写与读（扫描/验证、渠道值班、平台级供应商、源登记、上架开关、许可放行、产品事实查询面）：`Depends(require_platform_admin)`。租户公司管理员做成失败时 **目录/额度/配置一行不变**，并留越权审计。

租户壳：导航隐藏中转管控 / 平台运营 / 源与上架写。直打这些地址：**与未登录打一个不存在页相同**（无渠道列表、无密钥、无「抱歉您没有权限」）。实现：同一 404 模板/JSON，不走 403 业务信封。

`/llm`：租户可管理 **本企业**行；平台行写控件不出现；激活平台级供应商拒绝且平台行不变（GWT-06.6 / **73.3**）。**本企业供应商写与测试连接 = `require_operator`（admin+operator）；只读仍拒。** 落地票 **T-17**（同 PR 改现网 `/llm` 测试合同：作废 `test_create_endpoint_rejects_operator` 金标）。T-05 只验 `/llm` 不整页 404 与企业负责人保存，禁止把 operator 403 写成写面完成态。

**露出（SH-11，T-17 同 PR，挡 GWT-73.4「点」）：** 去掉 `frontend/admin/src/App.tsx` `/llm` 的 `ProtectedRoute requireAdmin`（或改成经办可进：`role===operator` 或持 `menu:llm`）。`/newapi` **仍** `requireAdmin`。`roles` 表 operator 行 / `_ROLE_PERMISSIONS["operator"]` / Alembic `022` `_SEED_ROLES` operator **加 `menu:llm`**（**仍不加 `menu:newapi`**）。022 已 applied 的库同 PR 数据回填 UPDATE `roles.permissions` JSON，禁止改表结构。同 PR 改 `LlmProviders.test.tsx`：经办看得到本企业行保存/测试，只读仍无。平台级行继续 73.3。

登录投影增加 `is_platform_admin`（expand：旧客户端缺字段当 false）。前端菜单用该布尔，不用 `role==='admin'` 开平台叶。权限缓存未就绪：显示「权限加载中」或保留读叶，**不得**露出平台写。

Wave 0 不交付完整 `require_permission` 矩阵引擎。

## 备选与否决理由

### 备选 A：只收市场写面，中转仍 `require_admin`

**否决理由**：护栏「非超管改渠道或平台 LLM 成功 = 0」会失败。中转是今日最松的写面。

### 备选 B：租户直打返回道歉 403

**否决理由**：GWT-07.3 钉死与页面不存在同形，避免存在性泄漏。

### 备选 C：`/llm` 整页当不存在

**否决理由**：BYOK 是租户能力（FR-73 / GWT-06.5）。

### 备选 D：先做完整权限码表再收权

**否决理由**：超 appetite。现有 `is_platform_admin` 足够冻 FR-06/07。

### 备选 E：改 Depends 不改 `test_b1c`

**否决理由**：PIT-2：viewer 扫描 200 是成功合同，CI 必红且会诱使回滚守卫。

### 备选 F：`/llm` 写与 test 保持 `require_admin`（经办 403）

**否决理由**：GWT-73.4 When = 经办点测试连接；FR-73 正文「企业负责人/经办仍能保存本企业供应商」。现网 `test_create_endpoint_rejects_operator` 会把 403 钉成完成态。T-17 同 PR 改测试合同。平台级行仍走 GWT-06.6 / 73.3，不借本条放行。

### 备选 G：只改 `/llm` API 守卫；前端 `/llm` 仍 `ProtectedRoute requireAdmin`；operator 无 `menu:llm`

**否决理由**：GWT-73.4 When = 经办**点**测试连接。HTTP 200 仍勾不了「点」（SH-11）。现网 `App.tsx` `/llm` 包在 `requireAdmin`；`_ROLE_PERMISSIONS["operator"]` 与 Alembic `022` 种子均无 `menu:llm`（仅 admin 有，且 admin 同时有 `menu:newapi`）。T-17 同 PR：去掉 `/llm` 的 `requireAdmin`（或改成经办可进）；给 operator 加 `menu:llm`（仍不加 `menu:newapi`）；改 `LlmProviders.test.tsx`。平台级行继续 73.3。

## 证据

```
读码：backend/app/api/deps.py require_admin vs require_platform_admin
读码：capabilities.py require_login；newapi.py 全部 require_admin
读码：test_b1c_capabilities_coverage.py「viewer 亦放行」
前端 LoginResponse 无 is_platform_admin（诊断 2026-09-08）
读码：frontend/admin/src/App.tsx path="llm" 包 ProtectedRoute requireAdmin（经办直达被拦）
读码：auth.py _ROLE_PERMISSIONS operator 无 menu:llm；admin 有 menu:llm + menu:newapi
读码：alembic/versions/022_saas_roles_departments.py _SEED_ROLES operator 同缺 menu:llm
读码：LlmProviders.test.tsx 只钉 viewer「仅管理员可管理供应商」；无经办保存/测试格
```

## 代价与风险

| 代价 | 缓解 |
|---|---|
| 大批 b1c 测试同 PR 改 oracle | 票 T-04/T-05 强制测试与守卫同交；`/llm` 写与 test 的 operator 合同在 T-17 同 PR |
| 404 同形实现细节易漂成 403 | 契约钉字节级/模板级对照用例 |

## 影响范围

| 谁 | 需要做什么 |
|---|---|
| `/backend` | 守卫替换 + 越权审计 + `/llm` 行级拆分；T-17 本企业写与 test=`require_operator`；operator 加 `menu:llm`（`_ROLE_PERMISSIONS` + 022 种子 + `roles` 表回填；不加 `menu:newapi`） |
| `/frontend` | 投影字段；空缓存；租户无中转叶；T-17 去掉 `/llm` `ProtectedRoute requireAdmin`（或经办可进）；同 PR 改 `LlmProviders.test.tsx`：经办见本企业行保存/测试，只读仍无 |
| `/qa` | 公司管理员扫描/改窗口/直打渠道；GWT-73.4 经办**点**测本企业行；viewer 写 `/llm` 仍拒；平台级行 73.3 |

## 后续复审条件

需要细粒度 permission 码（多超管分工）时另开特征。不得借此重排后台五组 IA（X-IA）。

## 变更历史

| 日期 | 状态变化 | 说明 |
|---|---|---|
| 2026-09-08 | proposed → accepted | v2 重写 |
| 2026-09-08 | accepted（补） | SH-09：本企业供应商写与测试连接=`require_operator`；只读仍拒；平台级行仍 GWT-06.6 / 73.3；落地 T-17 同 PR 改 `/llm` 测试合同 |
| 2026-09-08 | accepted（补） | SH-11：T-17 同 PR 去掉 `/llm` `ProtectedRoute requireAdmin`（或经办可进）；operator 加 `menu:llm`（022 / `_ROLE_PERMISSIONS` / `roles`；不加 `menu:newapi`）；平台级行仍 73.3；改 `LlmProviders.test.tsx`；否决备选 G |
