# 实现证据 · T-21 定价专业/企业主按钮进结账；免费仍注册

> 票：`02-shape/contract.md` §10 T-21｜FR 锚点：FR-U35 FR-U24｜角色：/frontend｜日期：2026-09-12
> 上游：T-16 结账路由 · T-25 屏 2 锁句「去结账」
> 泳道：ui｜作废「预告不可购买」mailto｜禁 FR-U24 四字｜官网无会话分支（GWT-01.3）

专业/企业 CTA 一律「去结账」。免费档仍「免费注册」→ `/register`。不写「当前可买」。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 专业档主按钮 | 官网 Pricing | `frontend/official/src/pages/Pricing.tsx` | href → admin `/billing/checkout?product=plan_pro` |
| 企业档主按钮 | 同上 | 同上 | `product=plan_enterprise`；无 `plan_ent` |
| 免费档 | 同上 | 「免费注册」`/register` | GWT-U35.4 |
| 访客先登录再回结账 | admin Login `from` | `pages/Login.tsx` | 保留 `search`（product=） |
| 经办/只读 | 后台 Pricing | 按下进屏 10；按钮字仍「去结账」 | 不建单 |
| 买方已登录 | 后台 `/pricing` | navigate 结账 | 无免费注册（已有企业） |
| FR-U24 | 扫描+渲染 | official/admin `frU24CopyScan` | 无四字；无 mailto 弹窗 |

**分层依赖核对**：☑ 官网无 `useAuthStore` ☑ 未改 Hero 第一句 ☑ 未写「当前可买」

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/official/src/pages/Pricing.tsx` | 修改 | CTA「去结账」；去掉预告 Tag / mailto |
| `frontend/official/src/pages/Pricing.test.tsx` | 修改 | U35.1/4/5 |
| `frontend/official/src/pages/Pricing.beacon.test.tsx` | 修改 | 仍分格 pricing_pro / enterprise |
| `frontend/admin/src/pages/Pricing.tsx` | 新增 | 买方结账 / 经办屏 10 |
| `frontend/admin/src/pages/Pricing.test.tsx` | 新增 | U35.1/3/5 |
| `frontend/admin/src/App.tsx` | 修改 | 路由 `/pricing` |
| `frontend/admin/src/pages/Login.tsx` | 修改 | `from` 带 query |
| `frontend/admin/src/pages/Login.test.tsx` | 修改 | GWT-U35.2 product=plan_pro |
| `frontend/admin/src/services/api.ts` | 修改 | 401 回跳带 search |
| `frontend/shared/src/constants/quota.ts` | 修改 | 注释：主按钮去结账 |
| `.sdlc/upgrade-four-pillars/03-impl/T-21-evidence.md` | 新增 | 本文件 |

**未触碰「不许改的文件」**：☑ Hero `HERO_FIRST_SENTENCE` 未改；无 notify。

## 3. 关键实现决策

官网定价无登录态分支：付费档始终写「去结账」，角色闸在结账 GET（经办 → `ORDER_ROLE_NOT_ALLOWED` 屏 10）。访客点链接进 admin checkout，ProtectedRoute → `/login?from=…product=plan_pro`。

## 4. ORM 与 DBML 对齐

☑ 未改。

## 5. 可观测性

beacon 仍 `pricing_pro` / `pricing_enterprise` / `register_free` 分格。

## 6. 自测证据

```
$ cd /Users/xuyun/auto_agents/frontend/official && npm test -- --watchAll=false --silent src/pages/Pricing.test.tsx src/pages/Pricing.beacon.test.tsx src/frU24CopyScan.test.tsx

PASS src/frU24CopyScan.test.tsx
PASS src/pages/Pricing.test.tsx
PASS src/pages/Pricing.beacon.test.tsx
Test Suites: 3 passed, 3 total
Tests:       13 passed, 13 total
OFFICIAL_EXIT:0
```

```
$ cd /Users/xuyun/auto_agents/frontend/admin && npm test -- --watchAll=false --silent src/pages/Pricing.test.tsx src/pages/Login.test.tsx src/frU24CopyScan.test.tsx

PASS src/pages/Pricing.test.tsx
PASS src/frU24CopyScan.test.tsx
PASS src/pages/Login.test.tsx (6.574 s)
Test Suites: 3 passed, 3 total
Tests:       12 passed, 12 total
ADMIN_EXIT:0
```

```
$ rg -n '当前可买' frontend/official/src frontend/admin/src frontend/shared/src --glob '!*.test.*' --glob '!*.spec.*'
(no matches)
RG_EXIT:1
```

```
$ bash tools/check/frontend.sh
✓ 前端工程门禁通过
FRONTEND_SH_EXIT:0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-U35.1 专业档 | official/admin Pricing `product=plan_pro` | ✅ 不到注册 |
| GWT-U35.2 访客 | Login `from=/billing/checkout?product=plan_pro` | ✅ |
| GWT-U35.3 只读/经办 | admin Pricing operator → 联系管理员 | ✅ 按钮字仍「去结账」 |
| GWT-U35.4 免费 | official 「免费注册」`/register` | ✅ |
| GWT-U35.5 企业档 | `product=plan_enterprise` | ✅ 无 plan_ent 商品码 |
| GWT-U24 | frU24 扫描 + Pricing 渲染 | ✅ 无「当前可买」 |
| GWT-01.3 | official Pricing 无 session 分支 | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A |
| 幂等 | — | ➖ N/A（定价不建单） |
| 并发写 | — | ➖ N/A |
| 外部依赖失败 | 离线点去结账拦截 | ✅ 官网 `warnOffline` |

## 7. NFR

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-07 | 主 CTA ≥44px | official Pricing touch target | jsdom |
| FR-U24 | 0 次「当前可买」 | rg exit 1 + Jest | 源码 |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 官网付费 CTA 是跨源链到 `http://localhost:9112/billing/checkout?product=`。企业档功能列表含「中转站渠道组分配」但不写「开通即送中转」。 |
| `/qa` | Hero 仍可有「尚未开通购买」（T-06 屏 1，本票未改 Home）。定价页已去掉该副标题。 |

## 9. 交票自检

- [x] 命令 + 退出码原样
- [x] 自测全绿
- [x] 未改 GWT / schema / tokens / Hero 第一句
- [x] 无「当前可买」；无「预告不可购买」主按钮
