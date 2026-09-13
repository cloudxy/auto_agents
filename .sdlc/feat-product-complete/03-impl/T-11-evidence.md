# 实现证据 · T-11 值班页看得见伪装；空态不第三套

> 票：contract §11 T-11｜FR 锚点：FR-61（GWT-61.1 / 61.2 / 61.3）｜角色：/frontend（admin）｜日期：2026-09-12
> 依赖：T-31/32/33 已重排 NewApiOps（三 tab 上提、总览三问、探针表 VERDICT_TAG「伪装」词在）；本票接其上，只做伪装可见性验收 + 探针 tab 计数缺口，不动三 tab 结构、不动探针引擎。

## 1. 契约落位表（实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| GWT-61.1 总览可见伪装 | 组件（已落，验收） | `components/newapi/OverviewChannels.tsx` + `Overview3q.tsx` | T-32 已落：Q2 渠道行 spoofed 置顶 + 行内「伪装」Tag + 卡片 extra 计数「伪装: N」（`latest_batch_verdicts`）；本票核对现有呈现，不改 |
| GWT-61.1 探针 tab 行内「伪装」可见 | 组件（已落，验收） | `components/newapi/ProbeResults.tsx` | 判定列 VERDICT_TAG.spoofed → 红 Tag「伪装」（T-33 前已有） |
| GWT-61.1 探针 tab 最新批次伪装计数（缺则补） | 组件（本票补） | `components/newapi/ProbeResults.tsx` | **缺口确认→补**：筛选行尾新增「最新批次 `<batch_id>` +『伪装 N 条』」徽标；数据源 `overview.latest_batch_verdicts.spoofed`（后端探针引擎落库口径回传，无新端点）；文案入 `newapiShared.ts` 冻结常量 |
| GWT-61.1 渠道保持可用（不自动关） | 行为断言 | `pages/NewApiOps.test.tsx` | 断言：页面无「自动禁用/人工禁用」态；Q2 区无「禁用」动作按钮；操作列为值班动作「立即探测」（结构上 OverviewChannels 本就无禁用列/禁用按钮——探针判伪装不触发关闭） |
| GWT-61.2 只出现已冻空态句 | 断言（已落句，验收） | `pages/NewApiOps.test.tsx` | 71.3（网关挂了）/71.2（还没配）为 T-18/T-32 已冻句；本票补「无第三套」断言：总览+探针 tab 走查，禁句「暂无渠道」与组件默认「暂无数据」均不出现；探针 tab 本地空 = 已冻 `DUTY_LOCAL_PROBE_EMPTY`，Q3 空 = 已冻 `EVENTS_24H_EMPTY` |
| GWT-61.3 租户直打 404 同形 | 路由守卫（已落）+ 断言补一例 | `App.tsx` `MainLayout` + `App.layout.test.tsx` | 守卫 T-15/T-29 已落（`isPlatformWritePath('/newapi')` + 非 `is_platform_admin` → 缺页同形 404）；既有用例只盖「租户打 /users」与「未登录打 /newapi」，本票补**已登录租户直打 /newapi** 一例（同形：404 文案 + 返回工作台 + 无侧栏 + 无值班页内容 + 无权限中转） |
| 夹具 | 纯前端 mock | `pages/NewApiOps.test.tsx` | 探针结果 mock 最新批次 `verdict='spoofed'`；overview mock 回传 `latest_batch_id` + `latest_batch_verdicts.spoofed=1`（查询端点已回传 verdict，无需后端夹具支持） |

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/components/newapi/ProbeResults.tsx` | 修改 | +最新批次伪装计数徽标（react-query 共享键取 overview）；113→141 行 |
| `frontend/admin/src/components/newapi/newapiShared.ts` | 修改 | +冻结常量 `PROBE_LATEST_BATCH_LABEL` / `PROBE_SPOOF_SUMMARY`；94→99 行 |
| `frontend/admin/src/pages/NewApiOps.test.tsx` | 修改 | +GWT-61.1 / GWT-61.2 两用例（TDD：61.1 红轮见 §5） |
| `frontend/admin/src/App.layout.test.tsx` | 修改 | +GWT-61.3 已登录租户直打 /newapi 同形 404 一例 |

与票表一致（纯前端，4 文件）。未触碰「不许改的文件」：确认——三 tab 结构（NewApiOps.tsx/PageHeaderTabs）、探针引擎、Overview3q/OverviewChannels/EventsList 均未动。

## 3. 关键实现决策

- **计数数据源选 overview 而非本地切片**：探针表分页/过滤下，本地 `items.filter(...)` 计数会被分页截断误导；`overview.latest_batch_verdicts.spoofed` 是后端对最新批次的权威计数。取数用 `useQuery({ queryKey: ['newapi','overview'] })` —— 与 Overview3q **同一查询键**，总览已载时探针 tab 零额外网络请求；页面「刷新」（invalidate `['newapi']`）两处同刷，口径一致。
- **静默降级，不新增空态句（GWT-61.2 纪律）**：overview 查询失败或 `latest_batch_id` 为 null（尚无批次）时徽标整体不渲染——不出现加载/失败/空态新句；探针表本体（行内「伪装」Tag）不受影响。
- **文案入 `newapiShared` 冻结常量**：「最新批次」「伪装 N 条」与 `VERDICT_TAG`/`PROBING_TEXT` 同库，不在组件里散写第二套说法。
- **TDD 红绿范围**：GWT-61.1 的计数徽标是真缺口 → 红轮（`findByTestId('probe-latest-batch')` 超时）→ 补实现 → 绿。GWT-61.2/61.3 是票面明示的「验收断言补一例」（行为已由 T-32/T-29 落），无可红处，直接绿。
- **「渠道保持可用」断言口径**：UI 的「已禁用」态即 `STATUS_TAG` 的「自动禁用/人工禁用」文案（本页 Q2 表无状态列，结构上不可能出现）；自动关闭动作以「Q2 区内无『禁用』按钮」断言，操作列仅有「立即探测/配置」。

## 4. 自测证据（命令与退出码原样粘贴）

红轮（计数徽标缺失，GWT-61.1 失败于 `findByTestId('probe-latest-batch')`）：

```
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest src/pages/NewApiOps --maxWorkers=2
  ✕ GWT-61.1 spoofed latest batch is visible on the duty page; channel stays usable (no auto-disable) (21188 ms)
Test Suites: 1 failed, 1 total
Tests:       1 failed, 12 passed, 13 total
exit: 1
```

绿轮（定向 NewApiOps，票面 success check）：

```
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest src/pages/NewApiOps --maxWorkers=2
PASS src/pages/NewApiOps.test.tsx (83.073 s)
  ✓ GWT-61.1 spoofed latest batch is visible on the duty page; channel stays usable (no auto-disable) (13296 ms)
  ✓ GWT-61.2 gateway down / unregistered models: only frozen empty sentences, no third empty-state family (2704 ms)
Test Suites: 1 passed, 1 total
Tests:       13 passed, 13 total
Snapshots:   0 total
Time:        83.415 s, estimated 92 s
exit: 0
```

GWT-61.3 守卫文件（App.layout，含既有 4 例回归）：

```
$ cd /Users/xuyun/auto_agents/frontend/admin && CI=true npx jest src/App.layout --maxWorkers=2
  ✓ GWT-96.1 cross-group menu click keeps the same sider instance and expansion (61 ms)
  ✓ GWT-96.2 in-group leaf switch keeps the same sider instance and expansion (116 ms)
  ✓ tenant company admin direct hit on merged /users is same 404 shell without sidebar (1193 ms)
  ✓ unauthenticated direct hit on merged /newapi stays 404 shell, no login redirect (15 ms)
  ✓ GWT-61.3 authenticated tenant direct hit on /newapi is the same missing-page 404 shell (845 ms)
Test Suites: 1 passed, 1 total
Tests:       5 passed, 5 total
Time:        5.757 s
exit: 0
```

构建（票面 success check；CRA 常规 bundle 体积 warning，非错误）：

```
$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/admin
Compiled with warnings.
The build folder is ready to be deployed.
exit: 0
```

工程门禁 + 业务文件 lint：

```
$ cd /Users/xuyun/auto_agents && bash tools/check/frontend.sh
✓ 前端工程门禁通过
exit: 0

$ cd /Users/xuyun/auto_agents/frontend/admin && npx eslint src/components/newapi/ProbeResults.tsx src/components/newapi/newapiShared.ts
（无输出）
exit: 0
```

（测试文件跑 `npx eslint` 会报既有 testing-library 规则告警——该规则集不在 CI/gate 执行路径，且本票新增断言沿用文件内既有 `closest('tr')` 模式；按红线「Match existing codebase style」未改。）

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-61.1 总览/探针 tab 能看见该次伪装（计数徽标或行上 Tag）+ 渠道不自动关 | `GWT-61.1 spoofed latest batch is visible…`（总览行 Tag + 「伪装: 1」计数 + 探针 tab 行内 Tag + 「伪装 1 条」徽标 + 无禁用态/无禁用动作 + 立即探测在） | ✅ |
| GWT-61.2 只出现已冻空态句，无第三套 | `GWT-61.2 gateway down / unregistered models…`（71.3 在/71.2 不在/Q3 已冻句 + 探针 tab 本地已冻句 + 「暂无渠道」「暂无数据」双 tab 不出现）；未登记模型侧另有既有 `GWT-71.2 reachable zero models is empty not load failure` | ✅ |
| GWT-61.3 租户无入口直打 404 同形 | `GWT-61.3 authenticated tenant direct hit on /newapi…`（App.layout.test.tsx，守卫 `MainLayout` 真路径） | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（纯前端，无多步写） |
| 幂等 | — | ➖ N/A（只读展示 + 共享查询缓存） |
| 并发写 | — | ➖ N/A |
| 外部依赖失败 | GWT-61.2 overview 无批次→徽标不渲染（静默降级）；既有 GWT-98.4 区级失败用例未回归破坏 | ✅ |

## 5. 9 维自检（本票增量）

1. 间距：复用既有 `Space marginBottom:16` 行内布局，无新魔数主布局；2. 颜色：徽标 `color={VERDICT_TAG.spoofed.color}`（token 复用，无硬编码 hex）；3. 字体：`Text code fontSize 12` 同既有批次列；4. 圆角/阴影：antd Tag 默认；5. 图标：无新增（徽标为文字 Tag）；6. 交互态：Tooltip 悬停见完整批次 id（截断场景）；7. 状态完备：overview 失败/无批次→徽标静默不渲染（GWT-61.2 纪律）；8. 响应式：`Space wrap` 随窄屏折行；9. a11y：徽标为语义 Tag 文本（「伪装 N 条」可读），批次 id code 样式可复制。

NFR：`.tsx ≤ 400 行` —— ProbeResults 141 / newapiShared 99 / NewApiOps.tsx 167（未动）；F-7 gate 绿。

## 6. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qc` | 探针 tab 计数徽标数据源 = `/newapi/overview` 的 `latest_batch_verdicts.spoofed`（与总览卡片 extra 同源同刷）；mock 口径见 §1 夹具行。观察项（非本票范围）：EventsList 表零行时用 antd 默认「暂无数据」（工单 80 既有行为，GWT-61.2 断言未走查事件 tab 空态）——若 pm 要给事件本地空态冻句，需 spec 增补后另票。 |
| `/architect` | 无契约歧义；未新增端点/字段。 |
| `/qa` | 61.2/61.3 为验收断言补例（行为 T-32/T-29 已落）；真环境需重验点：overview 与探针切片的批次一致性（手动探测完成后徽标随共享缓存刷新）。 |
