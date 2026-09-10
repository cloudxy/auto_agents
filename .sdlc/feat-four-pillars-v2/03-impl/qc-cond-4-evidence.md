# 实现证据 · QC cond 4 / GWT-01.1 定价免费档三条数字与用量页相同

> 票：QC condition 4｜FR 锚点：FR-01 / GWT-01.1｜角色：/frontend｜日期：2026-09-10
> 上游：`04-verify/coverage.md` §5 ❌ 缺口；`quota_service.DEFAULT_QUOTA`；`Pricing.tsx` / `Usage.tsx`
> 泳道：L4 ui
> 禁：支付（Q-PRICE）、代答六问、Wave 2/3、改 GWT

覆盖矩阵缺口：Pricing.test 只钉文案；Usage 默认夹具 `result_storage:100` / `llm_tokens_month:100`，Then「与用量页相同」无对照。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 免费档三数 5 / 10000 / 200000 | shared 常量 | `frontend/shared/src/constants/quota.ts` | 与 backend `DEFAULT_QUOTA` 同数；非 API |
| 定价免费档文案 | 官网页 | `frontend/official/src/pages/Pricing.tsx` | 读 `FREE_TIER_FEATURE_COPY` |
| 用量上限展示 | 用量页（未改渲染） | `frontend/admin/src/pages/Usage.tsx` | 仍 `limit.toLocaleString()` 来自 API |
| Then 对照 | Jest 对 | `Pricing.test.tsx` + `Usage.test.tsx` | 字面量三句仍在 Pricing.test |

**分层依赖核对**：☑ 未 import ORM ☑ 未改 schema / GWT / design tokens ☑ admin 未引 official（F-5，走 shared）☑ 无支付流

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/shared/src/constants/quota.ts` | 新增 | `DEFAULT_QUOTA` + `FREE_TIER_FEATURE_COPY` |
| `frontend/shared/src/index.ts` | 修改 | 导出上两项 |
| `frontend/official/src/pages/Pricing.tsx` | 修改 | 免费档三条改读共享文案 |
| `frontend/official/src/pages/Pricing.test.tsx` | 修改 | 仍钉三句字面量；精确行无「预告」 |
| `frontend/admin/src/pages/Usage.test.tsx` | 修改 | 具名 DEFAULT_QUOTA 对照；将满/满额仍 100/100 |
| `.sdlc/feat-four-pillars-v2/03-impl/qc-cond-4-evidence.md` | 新增 | 本文件 |

**与票里「会改哪些文件」一致**：☑ 是（shared 常量 + 对测；未改 Usage 产品渲染）

**未触碰「不许改的文件」**：☑ 确认（未改 GWT、未做支付、未改 backend `DEFAULT_QUOTA`、未 Wave 2/3）

## 3. 关键实现决策

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 无写库 | ➖ N/A | 静态文案 + Jest 夹具 |

☑ 无「先查后插」☑ 无条件更新 ☑ 无新外部依赖

数字单源：`DEFAULT_QUOTA`。定价文案 `toLocaleString('en-US')` 钉 `10,000`；用量页仍无 locale 参数（与产品一致）。将满/满额夹具不得改成免费档上限，否则 12.2/12.6/12.7 失真。

## 4. ORM 与 DBML 对齐

➖ N/A 本票不加列。☑ 未自行加字段/改类型

## 5. 可观测性 / 九维

未改数据获取（Usage 仍既有 fetch；定价仍静态）。无新 hex / 无新 token。六态未扩：定价静态闭集 A；用量加载/空/满额既有。未做支付 CTA。

## 6. 自测证据

> 命令与退出码**原样粘贴**。TDD：先红后绿。

### 6.1 Red（夹具仍 100/100，断言 10,000）

```
$ CI=true npm test --prefix frontend/admin -- --runInBand --watchAll=false --testPathPattern='Usage.test' --testNamePattern='DEFAULT_QUOTA'
FAIL src/pages/Usage.test.tsx
  ✕ Usage page with DEFAULT_QUOTA (5 / 10000 / 200000) shows the same three numbers as Pricing 免费档 (250 ms)

    Expected substring: "10,000"
    Received string:    "…任务并发0/ 5 个运行中0%结果存储0/ 100 条结果0%LLM Token（本月）0/ 100 tokens0%…"

      165 |   expect(copy).toContain('10,000')
          |                ^

Test Suites: 1 failed, 1 total
Tests:       1 failed, 5 skipped, 6 total
```

exit: 1

根因：默认 `overview()` quota 为 `result_storage:100` / `llm_tokens_month:100`，不是免费档 10000 / 200000。

### 6.2 Green

```
$ npm run build -w @auto-agents/frontend-shared
> tsc -p tsconfig.json
```

exit: 0

```
$ CI=true npm test --prefix frontend/official -- --runInBand --watchAll=false --testPathPattern='Pricing.test'
PASS src/pages/Pricing.test.tsx
  ✓ test_no_direct_gateway_or_relay_token_copy (266 ms)
  ✓ free-tier primary CTA goes to register (162 ms)
  ✓ paid-tier primary CTA does not go to register (443 ms)
  ✓ closed-set B items are preview not currently buyable (31 ms)
  ✓ members and usage boards are current on free tier (GWT-01.10 copy) (24 ms)
  ✓ test_no_accuracy_or_certification_copy (26 ms)
  ✓ pricing source has no session branch (GWT-01.3) (370 ms)

Test Suites: 1 passed, 1 total
Tests:       7 passed, 7 total
```

exit: 0

```
$ CI=true npm test --prefix frontend/admin -- --runInBand --watchAll=false --testPathPattern='Usage.test'
PASS src/pages/Usage.test.tsx
  ✓ test_readonly_usage_no_plan_edit_gateway_failure_not_quota (242 ms)
  ✓ near limit warning has no internal codes (73 ms)
  ✓ token full CTA does not go to register (291 ms)
  ✓ platform admin without tenant sees enterprise-space copy not empty usage (GWT-16.3) (16 ms)
  ✓ storage full CTA goes to results not register (189 ms)
  ✓ Usage page with DEFAULT_QUOTA (5 / 10000 / 200000) shows the same three numbers as Pricing 免费档 (80 ms)

Test Suites: 1 passed, 1 total
Tests:       6 passed, 6 total
```

exit: 0

```
$ npm run build --prefix frontend/official
Creating an optimized production build...
Compiled successfully.
```

exit: 0

```
$ npm run build --prefix frontend/admin
Creating an optimized production build...
Compiled with warnings.
（既有 unused-vars：LogDrawer / EnterpriseManagement / LlmProviders / Nodes / RbacManagement / SpiderLogs / auth.ts；非本票文件）
```

exit: 0

```
$ bash tools/check/frontend.sh
前端工程门禁（F-2/F-3/F-4/F-5/F-6/F-7 已启用；F-1 批次 2 已由 service 归一承接）
==============================================================
✓ 前端工程门禁通过
```

exit: 0

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-01.1 正常 | `Pricing.test` 钉 GWT 字面 `5 个并发任务` / `10,000 条结果存储` / `20 万 LLM tokens/月`，并 `FREE_TIER_FEATURE_COPY ===` 这三句；精确行无「预告」 | ✅ |
| GWT-01.1 对照 | `Usage page with Pricing FREE_TIER_FEATURE_COPY (5 / 10,000 / 20 万) shows the same three numbers as GWT-01.1`：mock 从 copy 解析；Usage 钉 GWT Given `5` / `10,000` / `200,000`；无「预告」。禁止 `mock(DEFAULT_QUOTA); expect(DEFAULT_QUOTA)` | ✅ |
| Q-PRICE / 支付 | 未做 | ➖ 禁 |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（无写） |
| 幂等 | — | ➖ N/A（静态文案） |
| 并发写 | — | ➖ N/A |
| 外部依赖失败 | 既有 Usage 网关失败 ≠ 套餐满 | ✅ 未改 |

## 7. NFR 验证

➖ 本票无新 NFR。NFR-07 44px 不在本缺口。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | GWT-01.1 对测：Pricing 与 Usage 均钉 GWT 字面；Usage mock 从 `FREE_TIER_FEATURE_COPY` 解析。将满/满额仍 100/100。 |
| `/qc` | 证据本文件；coverage 01.1 原 ❌ 可由 qa 改映射。未改 coverage.md。 |
| `/backend` | 前端 `DEFAULT_QUOTA` 是拷贝，改 `quota_service` 不会自动同步。 |
| `/architect` | Register.tsx 仍手写「5 并发 / 10000 条 / 20 万」，未接共享常量（本票未扩）。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（红 + 绿命令 + 退出码原样）
- [x] 自测全绿（Pricing 7 / Usage 6 / 双 build / shared tsc / check-frontend）
- [x] 未改 GWT、schema、design tokens
- [x] 无支付流、未代选六问、未 Wave 2/3
- [x] admin 未引 official
- [x] 日志/密钥/连接串未硬编码

## Debug record

Rework round 2+（C35-QA-01）。G-fresh FAIL：具名对照是 `DEFAULT_QUOTA` 自指。

### Reproduce（空心绿：不 import Pricing / FREE_TIER_FEATURE_COPY 仍 PASS）

```
$ rg -n 'FREE_TIER_FEATURE_COPY|from .*Pricing' frontend/admin/src/pages/Usage.test.tsx
# 无 FREE_TIER_FEATURE_COPY / Pricing 命中；仅 import DEFAULT_QUOTA

$ CI=true npm test --prefix frontend/admin -- --runInBand --watchAll=false --testPathPattern='Usage.test' --testNamePattern='DEFAULT_QUOTA'
PASS src/pages/Usage.test.tsx
  ✓ Usage page with DEFAULT_QUOTA (5 / 10000 / 200000) shows the same three numbers as Pricing 免费档 (225 ms)
  ○ skipped test_readonly_usage_no_plan_edit_gateway_failure_not_quota
  ○ skipped near limit warning has no internal codes
  ○ skipped token full CTA does not go to register
  ○ skipped platform admin without tenant sees enterprise-space copy not empty usage (GWT-16.3)
  ○ skipped storage full CTA goes to results not register

Test Suites: 1 passed, 1 total
Tests:       5 skipped, 1 passed, 6 total
```

exit: 0

当时 `:159-173` 为 `overview(..., { ...DEFAULT_QUOTA })` 再 `expect(copy).toContain(DEFAULT_QUOTA.*.toLocaleString())`。定价文案不参与断言，Then「与用量页相同」未测到。

### Eliminated hypotheses

- H1 用量页渲染与 GWT 不符 → 读 `Usage.tsx` `limit.toLocaleString()`；DEFAULT_QUOTA 喂入时已是 `/ 5 个运行中` / `10,000` / `200,000`。产品 Then 成立，闸失败在 oracle。
- H2 将满/满额夹具已被改成免费档上限 → `overview` 默认仍 `result_storage:100` / `llm_tokens_month:100`；12.2/12.6/12.7 具名用例未改。
- H3 Pricing.test 已与 Usage 共享 Then → `Pricing.test.tsx` 钉三句字面但未 import `FREE_TIER_FEATURE_COPY`，与 Usage 无对照。
- H4 必须改 Usage 产品渲染才能过 Then → 否；100/100 mock 下新 oracle 红在 `10,000`，喂入定价解析数后绿。未改 `Usage.tsx`。

### root_cause

Named GWT-01.1 test mocked `{...DEFAULT_QUOTA}` and expected `DEFAULT_QUOTA.*.toLocaleString()`, so Pricing/`FREE_TIER_FEATURE_COPY` drift could not fail the Then.

### Fix

- `Usage.test.tsx`：import `FREE_TIER_FEATURE_COPY`；GWT Given 字面 `5` / `10,000` / `20 万` / `200,000` 作独立 oracle；mock 从 copy 解析（`万`×10000）；Usage 钉 `/ 5 个运行中` + `10,000` + `200,000`。删除 `DEFAULT_QUOTA` 往返。将满/满额默认 100/100 不动。
- `Pricing.test.tsx`：同一 GWT 三句钉 `FREE_TIER_FEATURE_COPY` 与渲染文案。
- 未改 `Usage.tsx` / GWT / 支付 / Register.tsx。

### Red（新 oracle + 默认 100/100 mock）

```
$ CI=true npm test --prefix frontend/admin -- --runInBand --watchAll=false --testPathPattern='Usage.test' --testNamePattern='GWT-01.1'
FAIL src/pages/Usage.test.tsx
  ✕ Usage page with Pricing FREE_TIER_FEATURE_COPY (5 / 10,000 / 20 万) shows the same three numbers as GWT-01.1 (223 ms)

    Expected substring: "10,000"
    Received string:    "…任务并发0/ 5 个运行中0%结果存储0/ 100 条结果0%LLM Token（本月）0/ 100 tokens0%…"

      180 |   expect(copy).toContain(GWT_01_1.storage)
          |                ^

Test Suites: 1 failed, 1 total
Tests:       1 failed, 5 skipped, 6 total
```

exit: 1

### Re-run（green）

```
$ CI=true npm test --prefix frontend/admin -- --runInBand --watchAll=false --testPathPattern='Usage.test'
PASS src/pages/Usage.test.tsx
  ✓ test_readonly_usage_no_plan_edit_gateway_failure_not_quota (239 ms)
  ✓ near limit warning has no internal codes (76 ms)
  ✓ token full CTA does not go to register (288 ms)
  ✓ platform admin without tenant sees enterprise-space copy not empty usage (GWT-16.3) (16 ms)
  ✓ storage full CTA goes to results not register (186 ms)
  ✓ Usage page with Pricing FREE_TIER_FEATURE_COPY (5 / 10,000 / 20 万) shows the same three numbers as GWT-01.1 (88 ms)

Test Suites: 1 passed, 1 total
Tests:       6 passed, 6 total
```

exit: 0

```
$ CI=true npm test --prefix frontend/official -- --runInBand --watchAll=false --testPathPattern='Pricing.test'
PASS src/pages/Pricing.test.tsx
  ✓ test_no_direct_gateway_or_relay_token_copy (250 ms)
  ✓ free-tier primary CTA goes to register (153 ms)
  ✓ paid-tier primary CTA does not go to register (418 ms)
  ✓ closed-set B items are preview not currently buyable (28 ms)
  ✓ members and usage boards are current on free tier (GWT-01.10 copy) (26 ms)
  ✓ test_no_accuracy_or_certification_copy (25 ms)
  ✓ pricing source has no session branch (GWT-01.3) (366 ms)

Test Suites: 1 passed, 1 total
Tests:       7 passed, 7 total
```

exit: 0
