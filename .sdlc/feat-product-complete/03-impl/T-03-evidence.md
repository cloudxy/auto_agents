# 实现证据 · T-03 用量/定价一套真相 + 我的订单 UI

> 票：contract §11 T-03（UI 面）｜FR 锚点：FR-50（GWT-50.1/50.6/50.12/50.13 + GWT-50.3/4 前端半）｜角色：/frontend（lane: ui）｜日期：2026-09-12
> 依赖：T-01（写规则 + 稳定 code `ORDER_ROLE_NOT_ALLOWED`/`ORDER_ONLINE_UNAVAILABLE`/`ORDER_PENDING_EXISTS`/`ORDER_FREE_PLAN`）与 T-02（读模型 `plan_name`/`amount_yuan`）均已落
> 口径：spawn packet 决议「我的订单」= **用量页内 Tab**（最小侵入，非 `/orders` 独立路由）；**官网侧零改动**（Q-PRICE 红线）

## 1. 契约落位表（UI 面）

| 契约元素 | 落在哪 | 文件 | 备注 |
|---|---|---|---|
| 满额动词统一骨架「提交升级申请」（GWT-50.12） | 组件常量 + 按钮 | `admin/src/pages/Usage.tsx` | channel=offline 走既有 `createOrder`（service 内 `{plan_id, channel:'offline'}`）；购买形「提交升级订单」零出现 |
| token/并发满同一申请入口（GWT-50.6） | full-state Alert | 同上 | `needApply = tokenFull || taskFull`；并发满标题「已达任务并发上限」 |
| 满额不到注册（GWT-50.1） | CTA href | 同上 | 存储满→`/data`（既有）；无任何 `/register` 链接；禁句「没有下一步/尚未开通」 |
| 经办/只读找管理员 | 写面判定 + code 映射 | 同上 | `canOrder = tenant_role ∈ {owner, admin}`（RelayGroups/LlmProviders 同款写法）；旁注「请联系企业管理员」；`ORDER_ROLE_NOT_ALLOWED`/`FORBIDDEN` → 同句，**无内码渲染** |
| 「已有待确认的升级申请」+ 次链 | 提交流 catch | 同上 | `ORDER_PENDING_EXISTS` → toast + inline Alert +「去我的订单」按钮切 Tab |
| 「本波不提供自助改套餐或支付」并存 | 联系 Modal | 同上 | 既有「申请提升配额」Modal 原样保留，与「提交升级申请」同屏 |
| 「我的订单」Tab（GWT-50.3 UI 面） | 页内 Tabs | `Usage.tsx` + `MyOrders.tsx`（新组件） | listMyOrders 渲染；读面无角色门槛（只读也能看） |
| 列表=档位名/状态中文/金额元 | Table 列 | `MyOrders.tsx` | pending→「待确认收款」、paid→「已确认」；金额直渲染 `amount_yuan`（T-02 读模型），**不做分→元心算**；缺字段画「—」 |
| 空态钉句（GWT-50.4 前端半） | `LoadEmpty` | `MyOrders.tsx` | 「还没有升级申请。」+ 说明 + 次链 去用量（页内切 Tab）/ 看定价（官网 `/pricing`，`REACT_APP_OFFICIAL_URL`）；禁「暂无数据」 |
| 失败≠空（FR-84 族） | `LoadFailure` + react-query | `MyOrders.tsx` | 「订单列表加载失败。检查网络后重试。」+ 可点重试（refetch 真拉） |
| 三数字一套真相（GWT-50.13/QA-23） | shared 常量单源 | `shared/src/constants/quota.ts` | 新增 `PRO_TIER_QUOTA`（50 / 200,000 / 5,000,000）+ `PRO_TIER_FEATURE_COPY`（deriv 规则与 `FREE_TIER_FEATURE_COPY` 同款）；dist 已重建 |
| 读模型类型 | service 类型 | `admin/src/services/billing.ts` | `OrderRow` += `plan_name?`/`amount_yuan?`/`tenant_name?`（T-02 §8 对齐） |

**9 维自检（lane）**：间距/色/字/圆角沿用 antd 默认与页内既有内联样式（本页既有风格，无新硬编码色）；图标用 Alert `showIcon`；交互态=申请按钮 `loading`（提交中…族）；状态完备=空/加载（Skeleton）/错误/权限/边界（多行重名、缺 plan_name/amount_yuan→「—」）已覆盖；响应式=Col span=8 三卡既有布局未动；a11y=语义按钮 + Alert role=alert（LoadState 既有）。

## 2. 改动文件清单（本会话）

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/shared/src/constants/quota.ts` | 修改 | +`PRO_TIER_QUOTA`/`PRO_TIER_FEATURE_COPY`（GWT-50.13 单源） |
| `frontend/shared/src/index.ts` | 修改 | barrel 导出新常量 |
| `frontend/shared/dist/*`（gitignore 产物） | 重建 | `npm run build -w @auto-agents/frontend-shared` exit 0（P-FE-01） |
| `frontend/admin/src/services/billing.ts` | 修改 | `OrderRow` 三可选字段（纯类型，无运行时改动） |
| `frontend/admin/src/pages/Usage.tsx` | 修改 | Tabs（用量/我的订单）+ 骨架动词 + code 映射 + 并发满入口 + 只读旁注（291 行 ≤ 400，F-7） |
| `frontend/admin/src/pages/MyOrders.tsx` | 新增 | 我的订单组件（react-query + LoadState，85 行） |
| `frontend/admin/src/pages/Usage.test.tsx` | 修改 | harness 升级（真 store + QueryClientProvider + antd message mock）+ 9 个 T-03 用例 |
| `frontend/admin/src/pages/MyOrders.test.tsx` | 新增 | 3 用例（列表元金额/空态钉句/失败重试） |

**与归档票（tickets-v1.2-stale-archived/T-03.md）的偏差**：☑ 有偏差——①「我的订单」按 spawn packet 决议落用量页内 Tab，未加 `/orders` 路由与 `menuConfig` 叶（packet：「选用量页内 Tab/区块，最小侵入」）；② 官网 `Pricing.tsx`/`Pricing.test.tsx` 零改动（packet：「官网侧零改动（Q-PRICE 红线）」，归档票的官网修改段作废）；③ `App.tsx`/`menuConfig.tsx` 未动（无新路由）。

**未触碰「不许改的文件」**：☑ 确认——`backend/services/billing_service.py`、`RelayGroups.tsx`、`AdminLayout.tsx` 未动；本会话 `frontend/official/` 零文件改动（工作树中 official 的既有改动属并行泳道，非本票）。

## 3. 关键实现决策

| 决策 | 内容 | 理由 |
|---|---|---|
| 我的订单入口形态 | 页内 Tabs（`usage`/`orders`），MyOrders 懒挂载（rc-tabs 默认懒渲染） | packet 最小侵入决议；orders 查询仅在首次激活 Tab 时发起，不影响既有用量面测试 |
| 写面判定 | `tenant_role ∈ {owner, admin}`，前端隐藏按钮；catch 兜底映射 `ORDER_ROLE_NOT_ALLOWED`→「请联系企业管理员」 | edge-states 权限表（经办/只读无按钮+旁注）；lane 纪律：前端权限是体验优化，后端 T-01 独立校验仍兜底 |
| toast 全部纯字符串 | message.success/warning/error 传 string | antd 6 toast 不进 RTL 容器，测试钉 `toHaveBeenCalledWith`（Members.test 同款）；「去我的订单」次链用 inline Alert 的 action 按钮承载 |
| 三数字单源 | shared 新常量 + 测试钉字面 + 夹具从 `PRO_TIER_FEATURE_COPY` 解析（`quotaFromTierCopy`，泛化自 GWT-01.1 的 `quotaFromPricingCopy`） | 官网冻结下能做到的最大同源：专业档数字与官网 Pricing 字面（'50 个并发任务'/'200,000 条结果存储'/'500 万 LLM tokens/月'）由独立 oracle 钉死，漂移即红；QA-23 Given=夹具企业已按专业档执法（usage mock 用 pro 配额），**非确认履约** |
| 金额渲染 | `amount_yuan.toLocaleString() + ' 元'`，缺省「—」 | 渲染读模型字段，不做分→元换算（不心算分）；测试断言不出现 `29900` |
| 错误映射 | code 表驱动（T-01 四码 + FORBIDDEN），未列码走 `apiErrorMessage`（后端信封 message 兜底） | edge-states §0.3；禁渲染 code 字面（测试断言无 `ORDER_PENDING_EXISTS`/`ORDER_ROLE_NOT_ALLOWED`/`FORBIDDEN`/`QUOTA_EXCEEDED`/裸 429） |

## 4. 自测证据（命令与退出码原样粘贴）

### TDD 红（对旧实现 + MyOrders 桩跑新测试；既有 6 例保持绿= harness 行为中性）

```
$ cd frontend/admin && CI=true npx jest src/pages/Usage src/pages/MyOrders --maxWorkers=2
Test Suites: 2 failed, 2 total
Tests:       10 failed, 7 passed, 17 total
Snapshots:   0 total
Time:        72.229 s
exit: 1
```

红失败 10 例全部为断言失败（非导入/夹具错误）：MyOrders 3 例（桩不渲染）、GWT-50.12/50.6/50.7（动词/并发满入口/旁注缺失）、提交流 3 例（旧实现无 toast 钉句/次链/新 code 映射）、GWT-50.3 Tab（无 Tabs）。7 绿 = 既有 6 例 + GWT-50.13（该例夹具数字由 mock 提供、旧页面本就渲染 quota 上限，故旧实现即绿；其价值在常量钉字面 + 夹具单源化，绿轮 17/17 复核）。

### TDD 绿（packet success-check 原命令）

```
$ cd frontend/admin && CI=true npx jest src/pages/Usage src/pages/MyOrders --maxWorkers=2
Test Suites: 2 passed, 2 total
Tests:       17 passed, 17 total
Snapshots:   0 total
Time:        60.628 s
Ran all test suites matching /src\/pages\/Usage|src\/pages\/MyOrders/i.
exit: 0
```

（中途一轮 3 failed 均为测试侧查询修正：两行同档位名「专业档」需 `findAllByText`；提交流用例漏喂 `listMyOrders` 夹具。实现未改。）

### 构建

```
$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/admin
The build folder is ready to be deployed.
exit: 0

$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/official
（官网零改动不变量：shared dist 增导出后官网构建仍绿）
The build folder is ready to be deployed.
exit: 0

$ cd /Users/xuyun/auto_agents && npm run build -w @auto-agents/frontend-shared
exit: 0
```

### 门禁与回归

```
$ cd /Users/xuyun/auto_agents && bash tools/check/frontend.sh
✓ 前端工程门禁通过
exit: 0

$ cd frontend/admin && CI=true npx jest src/pages/PlatformOps src/pages/ProductEvents --maxWorkers=2
Test Suites: 2 passed, 2 total
Tests:       7 passed, 7 total
exit: 0
```

（admin build 内嵌 eslint：build 绿即触碰文件 lint 绿；antd v6 用 Alert `title`/无废弃 prop。）

### 验收项逐条对应

| GWT / 验收点 | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-50.1 存储满→去结果库、不到注册、无否定骨架句 | `storage full CTA goes to results not register (GWT-50.1)` | ✅（href `/data`；无 `/register`；无「没有下一步/尚未开通」；存储满无申请入口） |
| GWT-50.6 并发满→「已达任务并发上限」+ 同一申请入口 | `GWT-50.6 task concurrency full shows 已达任务并发上限 with same offline entry` | ✅（owner 可点「提交升级申请」；无 `/register`） |
| GWT-50.12 后台动词=骨架「提交升级申请」 | `GWT-50.12 token full (owner) shows skeleton verb…` | ✅（「提交升级订单」零出现；无内码；「本波不提供自助改套餐或支付」与申请入口同屏并存） |
| GWT-50.13（QA-23）三数字同一套 | `GWT-50.13 (QA-23) pro-tier fixture enforces the same three numbers…` | ✅（`PRO_TIER_FEATURE_COPY` 钉独立 oracle 50/200,000/500 万；夹具=专业档执法；页面印 `/ 50 个运行中`+`200,000`+`5,000,000`；不验确认履约） |
| GWT-50.3 我的订单（档位名/状态中文/金额元） | `MyOrders › GWT-50.3 renders plan name, zh status and yuan amount…` | ✅（「待确认收款」/「已确认」/「299 元」×2；不出现 29900；不写履约句） |
| GWT-50.3 只读也能看（读面） | `GWT-50.3 readonly viewer can open 我的订单 tab (read surface)` | ✅（viewer 开 Tab 见列表） |
| GWT-50.4 空态钉句 | `MyOrders › GWT-50.4 empty orders show pinned copy…` | ✅（「还没有升级申请。」+ 说明 + 去用量/看定价；禁「暂无数据」） |
| FR-84 失败≠空 | `MyOrders › FR-84 order list failure…` | ✅（失败句+重试真拉，`toHaveBeenCalledTimes(2)`） |
| GWT-50.2/50.15 提交成功 toast + 单 pending | `owner submits offline upgrade order…` / `ORDER_PENDING_EXISTS maps to pinned copy…` | ✅（`createOrder(2)`；toast 钉句；次链「去我的订单」切 Tab；无 code 字面） |
| GWT-50.7 经办/只读找管理员 | `GWT-50.7 operator full sees contact-admin note…` + `ORDER_ROLE_NOT_ALLOWED …maps to contact-admin` | ✅（无申请按钮+旁注；后端 code 映射兜底无 FORBIDDEN 字面） |
| 既有回归（T-09 面） | 前 6 例（只读/网关/将满/平台超管/满额 CTA/免费档三数字 GWT-01.1） | ✅（17/17 内） |

## 5. NFR 验证

票内无 NFR 行。定向套件 60.6s（maxWorkers=2），符合 admin 满载经验值。➖

## 6. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | ① Tab 懒挂载：用量加载失败/平台超管早退分支下「我的订单」Tab 不可达（packet 最小侵入的既知耦合；独立 `/orders` 路由是归档票备选）。②「看定价」链接走 `REACT_APP_OFFICIAL_URL`（默认 http://localhost:9113）——真环境需配该 env。③ shared dist 需重建后官方/管理端才见 `PRO_TIER_*`（CI npm ci + build:shared 已覆盖）。④ 提交申请的 channel=offline 在 service 层写死（`createOrder`），页面测不到它——真环境联调确认。 |
| `/architect` / `/pm` | ① 官网 Pricing 专业档三条仍是页内字面（Q-PRICE 冻结）；跨应用真正 import 单源需要一次官网侧改动（把 `PLANS` 专业档 features 改读 `PRO_TIER_FEATURE_COPY`）——本波禁改，留待 Q-PRICE 裁决时一并做，当前靠测试钉字面相等。② T-01 §8 已提 `PATCH /tenants/me/usage/quota` 的 FORBIDDEN 口径未裁决；本票 UI 只兜了 `POST /billing/orders` 面。 |
| `/qc` | Usage.test harness 从 mock store 换成真 `useAuthStore.setState`（PlatformOps.test 同款），6 个既有用例断言未动（红轮即证）。 |

## 7. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样；红→绿双输出）
- [x] 自测全绿（定向 17/17；回归 7/7；双端 build exit 0；frontend.sh 门禁 exit 0）
- [x] 契约落位表已核对（UI 面；无后端/ORM 触碰——事务/幂等/ORM 节 N/A：纯前端票）
- [x] 未改 GWT/schema/tokens；未代选 Q-PRICE（官网零改动、未撤 ¥299、未写「当前可买」、未改官网动词）
- [x] `.tsx` ≤ 400 行（Usage 291 / MyOrders 85）；数据获取 react-query（无 setInterval/手动 loading；用量面沿用既有 useState 模式未重写——票外）
- [x] 无硬编码连接串/密钥（OFFICIAL_URL/CONTACT_MAIL 走 env + 既有 fallback 同款）
- [x] 用户可见处无内部码（测试断言 QUOTA_EXCEEDED/FORBIDDEN/429/ORDER_* 字面零出现）
- [x] 发现的上游问题已回报（§6：quota 端点口径、官网单源化待 Q-PRICE、Tab 耦合）
