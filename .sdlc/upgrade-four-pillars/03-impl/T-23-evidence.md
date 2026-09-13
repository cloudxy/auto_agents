# 实现证据 · T-23 全部访客/租户可见面禁「当前可买」机械钉

> 票：contract.md T-23｜FR 锚点：FR-U24｜角色：/frontend｜日期：2026-09-12
> 上游：`01-define/spec.md` v1.2 FR-U24 · `02-shape/edge-states.md` §0 · `02-shape/contract.md` T-23
> 泳道：ui｜未做支付 notify｜Hero 仍锁采集（T-06）

Q-AGPL 收费故事未选定期间，访客/租户可见面（含注释选用句）不得出现「当前可买」四字。机械钉 = 非测试源码全树扫描 + homepage/pricing/checkout/relay/capabilities 渲染负向断言。支付通道能收款 ≠ 本问已答。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| GWT-U24.1 未登录页 | 官网源码+渲染 | `frontend/official/src/frU24CopyScan.test.tsx` | Home / Features / Pricing / Capabilities |
| GWT-U24.2 支付成功后定价 | 定价静态页 | `Pricing.tsx` | 无 `payment_succeeded` / `/billing/notify` 分支 |
| GWT-U24.3 改定价入口 | 后台导航/源码 | `menuConfig.tsx` + admin 扫描 | 无「编辑定价」「改定价文案」 |
| GWT-U24.4 租户可见页 | 后台源码+渲染 | `frontend/admin/src/frU24CopyScan.test.tsx` | Checkout / Relay / Capabilities / Usage / 导航 |
| 业务规则 | 展示层禁四字 | official+admin+shared 非测试 src | 注释禁句改为「FR-U24 四字」 |
| 数据读写 | ➖ N/A | | 本票不写单、不接 notify |
| 幂等 | ➖ N/A | | 只读护栏 |

**分层依赖核对**：☑ 未改 backend Router/ORM/Schema ☑ official 未 import admin ☑ 未实现支付 notify ☑ 未改 Hero 第一句

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/official/src/frU24CopyScan.test.tsx` | 新增 | 官网全树扫描 + Home/Pricing/Capabilities 渲染 |
| `frontend/admin/src/frU24CopyScan.test.tsx` | 新增 | 后台全树扫描 + Checkout/Relay/TenantShelf 渲染 |
| `frontend/shared/src/constants/quota.ts` | 修改 | 注释去掉该四字（改为 FR-U24 四字） |
| `frontend/admin/src/constants/collectCopy.ts` | 修改 | 同上 |
| `frontend/admin/src/pages/Usage.tsx` | 修改 | 同上 |
| `frontend/official/src/components/home/FeaturesSection.test.tsx` | 修改 | 测试头注释误写四字 →「当前可导出」 |
| `.sdlc/upgrade-four-pillars/03-impl/T-23-evidence.md` | 新增 | 本文件 |

**与票里「会改哪些文件」一致**：☑ 是（frontend/official + frontend/admin src；机械钉测试）

**未触碰「不许改的文件」**：☑ 确认（未做 notify；未改 GWT / schema / tokens；未改 `HERO_FIRST_SENTENCE`）

## 3. 关键实现决策

非测试 `.ts/.tsx` 出现该四字即失败（含注释）。测试文件只允许负向断言/扫描针。渲染覆盖 homepage、pricing、checkout、relay、capabilities。定价/结账源码禁止 `payment_succeeded` 与 `/billing/notify`——本票不接通道通知。

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 无写路径 | ➖ N/A | 文案护栏；不建单 |

**事务提交后的操作失败怎么办**：➖ N/A

### 幂等

| 项 | 内容 |
|---|---|
| 幂等键来源 | ➖ N/A（无新建写） |
| 保证方式 | ➖ N/A |
| 重复请求返回 | ➖ N/A |

☑ 未使用「先查后插」

### 并发控制

| 场景 | 方式 | `rows == 0` 如何处理 |
|---|---|---|
| 无条件更新 | — | — |

☑ 本票无条件更新

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 | 对方幂等 |
|---|---|---|---|---|
| 公开列表 / 结账预览 / 渠道组读 | 测里 `retry: false` | 既有页内重试 | 空态/失败句，不含四字 | 读 |

## 4. ORM 与 DBML 对齐

☑ 未改 ORM / 迁移 / schema.dbml

结构核对输出：

```
$ 本票无 SHOW CREATE TABLE
N/A — UI-only；未自行加字段/改类型
```

**未自行加字段/改类型**：☑ 确认

## 5. 可观测性

| 项 | 实现 |
|---|---|
| 入口日志 | 无新后端入口 |
| trace_id | ➖ |
| 错误日志上下文 | ➖ |
| 慢操作耗时 | ➖ |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址 ☑ 无商户密钥

## 6. 自测证据

> 命令与退出码**原样粘贴**。「测试通过」「基本完成」不算证据。

```
$ cd /Users/xuyun/auto_agents/frontend/official && npm test -- --watchAll=false src/frU24CopyScan.test.tsx

> official@0.1.0 test
> jest --maxWorkers=2 --watchAll=false src/frU24CopyScan.test.tsx

PASS src/frU24CopyScan.test.tsx (7.894 s)
  ✓ GWT-U24 mechanical nail: homepage/pricing/capabilities source+render have no 当前可买 (1465 ms)

Test Suites: 1 passed, 1 total
Tests:       1 passed, 1 total
Snapshots:   0 total
Time:        8.38 s
Ran all test suites matching /src\/frU24CopyScan.test.tsx/i.
exit: 0
```

```
$ cd /Users/xuyun/auto_agents/frontend/admin && npm test -- --watchAll=false src/frU24CopyScan.test.tsx

> admin@0.1.0 test
> jest --maxWorkers=2 --watchAll=false src/frU24CopyScan.test.tsx

PASS src/frU24CopyScan.test.tsx (7.57 s)
  ✓ GWT-U24 mechanical nail: checkout/relay/capabilities source+render have no 当前可买 (1232 ms)

Test Suites: 1 passed, 1 total
Tests:       1 passed, 1 total
Snapshots:   0 total
Time:        8.061 s
Ran all test suites matching /src\/frU24CopyScan.test.tsx/i.
exit: 0
```

```
$ cd /Users/xuyun/auto_agents/frontend/official && npm test -- --watchAll=false src/frU24CopyScan.test.tsx src/pages/Home.test.tsx src/pages/Pricing.test.tsx src/pages/Capabilities.test.tsx src/components/home/FeaturesSection.test.tsx src/App.test.tsx

PASS src/frU24CopyScan.test.tsx (12.836 s)
PASS src/pages/Pricing.test.tsx (7.799 s)
PASS src/App.test.tsx
PASS src/pages/Home.test.tsx (8.321 s)
PASS src/components/home/FeaturesSection.test.tsx
PASS src/pages/Capabilities.test.tsx (80.517 s)

Test Suites: 6 passed, 6 total
Tests:       46 passed, 46 total
Snapshots:   0 total
Time:        81.953 s
exit: 0
```

```
$ cd /Users/xuyun/auto_agents/frontend/admin && npm test -- --watchAll=false src/frU24CopyScan.test.tsx src/pages/Checkout.test.tsx src/pages/RelayGroups.test.tsx src/pages/market/TenantShelf.test.tsx src/pages/Usage.test.tsx src/utils/collectBlock.test.ts

PASS src/pages/Usage.test.tsx (70.025 s)
PASS src/pages/market/TenantShelf.test.tsx (60.961 s)
PASS src/frU24CopyScan.test.tsx
PASS src/pages/Checkout.test.tsx
PASS src/utils/collectBlock.test.ts
PASS src/pages/RelayGroups.test.tsx (155.392 s)

Test Suites: 6 passed, 6 total
Tests:       36 passed, 36 total
Snapshots:   0 total
Time:        156.735 s
exit: 0
```

```
$ cd /Users/xuyun/auto_agents && bash tools/check/frontend.sh
前端工程门禁（F-2/F-3/F-4/F-5/F-6/F-7 已启用；F-1 批次 2 已由 service 归一承接）
==============================================================
✓ 前端工程门禁通过
exit: 0
```

```
$ rg -n '当前可买' frontend/official/src frontend/admin/src --glob '!*.test.*' --glob '!*.spec.*'
(no matches)
exit: 1
```

非测试源码 0 命中「当前可买」（rg 无匹配 exit 1 即为本钉通过）。`frontend/shared/src` 同步 0 命中（Jest official 扫描器覆盖）。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-U24.1 正常 | official `frU24CopyScan` 全树+Home/Pricing/Capabilities 渲染；既有 Home/App 负向断言 | ✅ |
| GWT-U24.2 边界 | Pricing 源码无 `payment_succeeded`/`/billing/notify`；静态页不随支付成功改文案 | ✅ |
| GWT-U24.3 越权 | admin 扫描 SURFACES（含 `menuConfig`）无「编辑定价」「改定价文案」 | ✅ |
| GWT-U24.4 边界 | admin `frU24CopyScan` 全树+Checkout/Relay/TenantShelf 渲染；Usage/导航纳入 SURFACES | ✅ |
| T-06 Hero | `HERO_FIRST_SENTENCE === '粘贴链接即可出数。'` | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（无多步写） |
| 幂等 | — | ➖ N/A（无新建写） |
| 并发写 | — | ➖ N/A（无并发写） |
| 外部依赖失败 | 精选/货架/结账/渠道组读失败或空态仍禁四字 | ✅ 扫描含失败句常量；渲染走空态 mock |

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-U06 / FR-U24 | 所有访客/租户可见面 0 次该四字 | Jest 源码扫描 + 五面渲染 + rg 非测试源 0 命中 | jsdom / 源码 |
| NFR-U09 | 本轮仅中文 | 未引入英文可买句 | 源码 |

九维（本票触及）：未改视觉 token；未新开交互控件。护栏是文案负向，不是新屏。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 机械钉：`frontend/official/src/frU24CopyScan.test.tsx` 与 `frontend/admin/src/frU24CopyScan.test.tsx`。针=`当前可买`。排除 `*.test.*`。rg 非测试源须 0 命中（exit 1）。Hero 仍 `data-testid=hero-first-sentence`。结账仍 N1 空态「收款通道未开通」。 |
| `/frontend` | T-19 不得在结账写该四字或接 notify。T-21 定价 CTA 改「去结账」时仍禁该四字。T-20 渠道组页同样。 |
| `/architect` | 无新错误码。本票不撰写 OSS 收费故事，不关 Q-AGPL。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（不是「大部分通过」）
- [x] 契约落位表已核对，分层无违规
- [x] ORM 与 DBML 一致，未自行加字段
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] async 上下文无同步阻塞调用
- [x] 无 `except: pass`（吞异常）
- [x] 日志已脱敏
- [x] 事务里无外部调用
- [x] 幂等未用「先查后插」
- [x] 条件更新的 `rows == 0` 已处理（无条件更新）
- [x] 外部依赖四件套齐全（超时/重试/降级/幂等前提）— 读路径沿用既有 retry:false + 空态
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 无 `tickets/T-23.md`（shape 不写票文件）；本证据即交票物
- [x] 未实现支付 notify；Hero 仍采集
