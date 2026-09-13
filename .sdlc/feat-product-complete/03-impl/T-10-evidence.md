# 实现证据 · T-10 渠道组页 Base URL/三步用法/用量；官网 0 次可买中转

> 票：contract §11 Wave C `T-10`｜FR 锚点：FR-60（GWT-60.1/60.2/60.4/60.9/60.11）+ GWT-60.7 句 + GWT-84.1（渠道组屏，FR-84 族）｜角色：/frontend（lane=ui）｜日期：2026-09-11
> 依据：spec v1.5 FR-60；edge-states「屏：渠道组 `/relay`」六态 + §0.5 明文只一次；contract §7.4（QA-08 读模型、60.9 不验收互否）；T-07/T-08 成果（空态句/找管理员句信封 message 单一来源；签发=网关 Key、明文一次）。companion=tdd：首轮输出含真实现缺陷（明文残留隐藏 DOM），红绿双输出见 §6。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 签发成功态（GWT-60.1）：明文一次+可复制；同屏 Base URL 与三步「复制 Base URL → 粘贴令牌 → 发一条请求」 | 页组件 | `pages/RelayGroups.tsx` + `components/relay/RelayUsage.tsx` | 签发弹窗内嵌 `RelayUsage`（同一屏）；复制 toast「已复制渠道组令牌」（edge-states §0.5 动词=产品名）；弹窗 `destroyOnHidden`——关闭后明文卸载，不留隐藏 DOM |
| Base URL 来源=配置（PUBLIC_BASE_URL 系），禁止硬编码/出站地址冒充 | 构建配置 | `RelayUsage.tsx` + `types/env.d.ts` | `REACT_APP_RELAY_PUBLIC_BASE_URL`，缺省 `http://127.0.0.1:4000` 对齐 `config/default/litellm.yml` `LITELLM.BASE_URL`（ADR-0019 决策 2 同值语义）；测试钉用法区零 `/api/v1`、全页零 `master` |
| 再进页只见前缀+状态（GWT-60.11） | 页组件 | `RelayGroups.tsx` 令牌表 | 表列只有 `key_prefix…` + 状态 Tag（已签发/已吊销/已过期）；明文只存在于签发响应一次性弹窗 |
| 用量数字区（GWT-60.2）：只读可见，数字来自接口本地列（QA-08） | 页组件 | 令牌表「累计用量（tokens）」列 | 渲染 `used_tokens`（本地缓存列，列表不打网关）；null → 「—」+ Tooltip「用量暂不可用」，不画成 0；控件显隐不影响本列 |
| 无令牌空态（GWT-60.4）：冻结句 + 有权者签发 + 经办 60.7 句，非空表 | 页组件 + service | `services/relay.ts` `fetchRelayPage` 透传信封 message | 空态句 = 后端 `MSG_TOKENS_EMPTY` 信封 message 单一来源（T-07 §8 下游约定，勿造第二套）；无组态「还没有渠道组。创建后才能签发令牌。」+ 负责人「创建渠道组」 |
| 经办能看不能签（GWT-60.7） | 页组件 | 写权判据 `tenant_role ∈ {owner, admin}` | 与后端 `relay_service._ISSUER_ROLES` 同口径；旁注句 = groups GET 信封 message（`MSG_CANNOT_ISSUE`）；控件隐藏（edge-states §0.4 藏+旁注，不是点了再失败） |
| 失败≠空（GWT-84.1 渠道组屏） | 页组件 | react-query `isError` 分支 | 「渠道组加载失败。检查网络后重试。」+ 可点重试；不渲染表格故无「暂无数据」；刷新经 react-query 保留旧数据（用量不闪 0） |
| 签发失败可见（60.5 族）| 页组件 | issue mutation `onError` | 内联 Alert（信封 message，如 502 `RELAY_GATEWAY_UNAVAILABLE` 的「平台网关暂时不可用…」）+ 弹窗不关 + 无假成功；离线「网络不可用，没有产生令牌。」 |
| 用法区空态仍渲染 | 页组件 | 底部「调用平台网关（用法）」Card | 空态句「按**下方**用法」→ 用法区在令牌区之下，空态/无权都在场 |
| 超管无企业（GWT-82.4 保持） | 页组件 | `TenantSpaceOnly` 早退 | T-15 成果保持，本票未改判据 |
| 官网 0 次「当前可买中转」（GWT-60.9 收窄口径） | official 测试 | `pages/Pricing.test.tsx` 新例 | 定价页渠道组句保持企业档预告形态（允许，不冻互否）；断言零「当前可买」/「可买中转」；本票不新增互否句、不代选 Q-AGPL/Q-PRICE |
| v2 GWT-70.4 旧句不挡本页 | 测试 | `RelayGroups.test.tsx` | 全页零「我的中转令牌」「直连平台网关」；产品名「渠道组令牌 / 签发令牌」 |

**分层核对**：☑ 未实现任何后端 API（本帽 refuse）｜☑ 未定义 token / 未改 GWT｜☑ 未动 menuConfig/侧栏（T-15 域）｜☑ 未动 NewApiOps（T-31 域）｜☑ 未动 T-17 其他点名屏（仅渠道组屏内联失败态，票面允许的最小衔接）｜☑ 五组/FR-91 零施工

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/pages/RelayGroups.tsx` | 修改（重写） | 六态 + 用法区 + 明文一次弹窗 + react-query 读模型。280 行（F-7 ≤400） |
| `frontend/admin/src/components/relay/RelayUsage.tsx` | 新增 | Base URL + 三步用法子件（页脚卡与签发弹窗同一屏复用）。41 行 |
| `frontend/admin/src/services/relay.ts` | 修改 | `fetchRelayPage` 读模型（组+令牌+信封 message）；`used_tokens: number \| null`；删无消费方的 `listRelayGroups`/`listRelayTokens`（grep 零引用） |
| `frontend/admin/src/types/env.d.ts` | 修改 | `REACT_APP_RELAY_PUBLIC_BASE_URL?: string` 声明 |
| `frontend/admin/src/pages/RelayGroups.test.tsx` | 修改（重写） | GWT-60.1/60.2/60.4/60.7/60.11 + 84.1 + 签发失败/离线/用量未知 共 10 例 |
| `frontend/official/src/pages/Pricing.test.tsx` | 修改 | 新增 `test_no_currently_buyable_relay_copy_gwt_60_9`（官网侧唯一改动——Pricing.tsx 本体零 diff，现网本就 0 次） |

**与票里「会改哪些文件」一致**：☑ 是（admin 渠道组页及子件 + official 渠道句核对）
**未触碰「不许改的文件」**：☑ 确认（未动 NewApiOps/页头/T-17 其他屏/backend/config yml；工作树其余 M 为 Wave 并行票所有）

## 3. 关键实现决策

### Base URL 为什么走 `REACT_APP_RELAY_PUBLIC_BASE_URL` 而非页内常量或后端接口

ADR-0019 决策 2：`Base URL = LITELLM.PUBLIC_BASE_URL（若配）否则 LITELLM.BASE_URL`——是**后端 Dynaconf 概念**，前端无法直读。当前无接口可取（T-08 §8：`PUBLIC_BASE_URL` 尚未引入配置；T-09 未开工），本帽 refuse 实现后端 API。故取构建配置通道 `REACT_APP_RELAY_PUBLIC_BASE_URL`（PUBLIC_BASE_URL 系命名，部署用 `AUTO_AGENTS_LITELLM__PUBLIC_BASE_URL` 同值覆盖两侧），缺省 `http://127.0.0.1:4000` 与 `litellm.yml` 缺省同值——与 `REACT_APP_API_BASE_URL`/`REACT_APP_OFFICIAL_URL` 既有先例同形（env + 本机缺省）。T-09 落地接口后可一 行切到接口真相（消费点只在 `RelayUsage.tsx` 一处）。

### 空态句/找管理员句：信封 message 单一来源，不在前端复制一套判据

T-07 §8 给前端的约定：tokens GET 空列表 message 即空态句、groups GET 对无权者 message 即找管理员句。`fetchRelayPage` 透传两条 message；页面渲染 `tokensMessage`（空态 Alert 文案）与 `groupsMessage`（旁注），仅留同文兜底常量（后端 router 已保证非空场景必带，兜底为防御性同文，非第二套文案）。写控件显隐仍由 `tenant_role` 判（与后端 `_ISSUER_ROLES` 同口径）——显隐是体验，后端独立拒（T-07 已落）。

### 明文一次的 DOM 语义：弹窗 `destroyOnHidden`

只把明文存 state、关闭置 null 仍不够——antd Modal 默认关闭后子树留在隐藏 DOM，明文可被查 DOM 找回。签发成功弹窗加 `destroyOnHidden`：关闭即卸载内容。该缺陷由 gwt_60_11 用例抓出（首轮红，见 §6），组件修复后转绿。

### react-query 读模型（替代手写 loading/error 双 useState）

`useQuery(['relay-page'])` 一次拉组+令牌：首载 `isPending` 走表格 loading；刷新保留旧数据（edge-states「刷新保留旧用量数字，避免 0 闪一下」由 react-query 数据驻留天然满足）；`isError` 走失败句+重试。签发/吊销/建组/启停为 `useMutation` + `invalidateQueries`。无 setInterval、无手写 loading 布尔。

### 事务边界 / 幂等 / 并发 / 外部依赖

➖ N/A（纯前端呈现票；网关调用、签发序贯、幂等均在 T-08/T-09 后端域）。

## 4. ORM 与 DBML 对齐

➖ N/A（零后端/模型改动；消费的 `RelayTokenOut` 字段与 041 既有列一致，未新增字段诉求）。

## 5. 可观测性

➖ N/A（前端无新日志面；明文不出现在任何日志/事件——后端 T-08 已保证，前端仅在签发响应一次性渲染）。

## 6. 自测证据（命令 + 退出码原样粘贴）

```
# 红：实现后首轮（真实现缺陷：明文残留隐藏 DOM + 两处测试选择器问题）
$ cd frontend/admin && CI=true npx jest --watchAll=false --maxWorkers=2 src/pages/RelayGroups.test.tsx
  ✕ gwt_60_1: issue shows plaintext once with base url and three steps on same screen (17605 ms)
    → Found multiple elements by: [data-testid="relay-usage"]（页脚卡与弹窗各一份，测试未限定弹窗内）
  ✕ gwt_60_11: after closing plaintext modal only prefix and status remain (45591 ms)
    → 明文仍留在文档——**组件缺陷**：Modal 未加 destroyOnHidden，关闭后子树残留隐藏 DOM
  ✕ gwt_84_1: load failure shows retry sentence, not an empty table (18893 ms)
    → 「重 试」两字间空格未匹配（antd CJK letter-spacing）
Tests:       3 failed, 7 passed, 10 total
exit: 1
处置：60.11 = 组件修复（RelayGroups.tsx 签发弹窗加 destroyOnHidden）；60.1/84.1 = 测试选择器修复（限定 .ant-modal 内 / /重\s*试/ 正则）。未改断言语义。

# 绿：修复后同命令
$ cd frontend/admin && CI=true npx jest --watchAll=false --maxWorkers=2 src/pages/RelayGroups.test.tsx
  ✓ shows tenant groups copy and not platform channel controls (845 ms)
  ✓ gwt_60_1: issue shows plaintext once with base url and three steps on same screen (19708 ms)
  ✓ gwt_60_11: after closing plaintext modal only prefix and status remain (48045 ms)
  ✓ gwt_60_2: viewer sees usage number and cannot-issue note (13470 ms)
  ✓ gwt_60_4: no tokens empty sentence with issue entry; usage area still rendered (15062 ms)
  ✓ gwt_60_7: operator sees usage/base url without write controls, not an empty table (9107 ms)
  ✓ gwt_84_1: load failure shows retry sentence, not an empty table (4665 ms)
  ✓ issue failure stays visible inline and modal stays open, no fake success (25026 ms)
  ✓ issue offline shows offline sentence and no plaintext (25237 ms)
  ✓ usage unknown renders placeholder not zero (2573 ms)
Test Suites: 1 passed, 1 total
Tests:       10 passed, 10 total
exit: 0

# official：官网 60.9 收窄口径（Pricing.tsx 零 diff，回归钉住 0 次）
$ cd frontend/official && CI=true npx jest --watchAll=false --maxWorkers=2 src/pages/Pricing.test.tsx
  ✓ test_no_direct_gateway_or_relay_token_copy (776 ms)
  ✓ free-tier primary CTA goes to register (464 ms)
  ✓ NFR-07 Pricing primary CTAs have 44px touch target (567 ms)
  ✓ paid-tier primary CTA does not go to register (1255 ms)
  ✓ closed-set B items are preview not currently buyable (91 ms)
  ✓ members and usage boards are current on free tier (GWT-01.10 copy) (81 ms)
  ✓ test_no_accuracy_or_certification_copy (93 ms)
  ✓ test_no_currently_buyable_relay_copy_gwt_60_9 (86 ms)
  ✓ pricing source has no session branch (GWT-01.3) (1170 ms)
Test Suites: 1 passed, 1 total
Tests:       9 passed, 9 total
exit: 0

# 构建（票面 success_checks）
$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/admin
The build folder is ready to be deployed.
exit: 0

$ cd /Users/xuyun/auto_agents && npm run build --prefix frontend/official
The build folder is ready to be deployed.
exit: 0

# 前端工程门禁（F-2..F-7，含 .tsx ≤400）
$ bash /Users/xuyun/auto_agents/tools/check/frontend.sh
✓ 前端工程门禁通过
exit: 0
```

### 全量 admin Jest（票面 success_checks）

见 §6 末尾补录（后台跑批）。注：前台 600s 上限内全量被 SIGTERM 截断（Wave 并行会话争用机器，T-15 §6 已记录同源漂移），故转后台以 `--maxWorkers=2` 完整跑批。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-60.1 签发并给用法 | `gwt_60_1`：明文一次在场+可复制；弹窗内 Base URL + 「复制 Base URL → 粘贴令牌 → 发一条请求」同屏；用法区零 `/api/v1`（出站地址不冒充）；全页零 `master` | ✅ |
| GWT-60.2 用量会走（只读可见） | `gwt_60_2`：viewer 见 `1,200`、找管理员句在场、无任何写控件 | ✅ |
| GWT-60.4 无令牌空态 | `gwt_60_4`：冻结句（信封 message）+ 签发入口（工具栏+空态动作）+ 无组句 + 用法区仍在场 + 零「暂无数据」 | ✅ |
| GWT-60.7 经办签发（票面 60.7 句） | `gwt_60_7`：operator 见 Base URL/用法/用量/名单，无签发/吊销/建组控件，旁注「当前账号不能签发，请联系企业管理员」，非空表 | ✅ |
| GWT-60.9 官网 0 次可买中转 | official `test_no_currently_buyable_relay_copy_gwt_60_9`：零「当前可买」/「可买中转」，渠道组句保持预告形态；**不验收互否**（票面收窄口径） | ✅ |
| GWT-60.11 再进页不见明文 | `gwt_60_11`：关闭弹窗后列表只见 `sk-AbCd…` 前缀 + 「已签发」，明文从文档消失（destroyOnHidden） | ✅ |
| GWT-84.1 失败≠空（渠道组屏） | `gwt_84_1`：失败句 + 重试；零「暂无数据」/空态句冒充 | ✅ |
| 60.5 族签发失败可见 | `issue failure...`：502 信封句内联、弹窗不关、无明文无假成功；`issue offline...`：离线句 + 弹窗不关 | ✅ |
| 70.4 旧句不挡本页 | `shows tenant groups copy...`：零「我的中转令牌」/「直连平台网关」；产品名「渠道组令牌」 | ✅ |
| 边界·用量未知 | `usage unknown renders placeholder not zero`：`—` + 暂不可知 Tooltip，不画 0 | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（无数据面写） | |
| 幂等 | ➖ N/A（签发/吊销幂等在 T-08 后端；前端无重复提交新增面——按钮 confirmLoading） | |
| 并发写 | ➖ N/A | |
| 外部依赖失败 | `issue failure`（网关 502 信封）+ `issue offline`（断网）+ `gwt_84_1`（列表加载失败） | ✅ |

## 7. NFR 验证

| NFR | 要求（spec §8 NFR 映射） | 实测 | 环境 |
|---|---|---|---|
| NFR-06（contract §12 → T-10） | 渠道组用法可跟随（Base URL/三步/用量呈现不崩） | 三步+Base URL 在空态/弹窗同屏渲染；用量列 null 边界有兜底 | jsdom（admin/official Jest） |
| 可用性（edge-states 渠道组屏六态） | 空/加载/错误/权限/边界/离线齐 | §1 落位表逐态有实现与用例 | 同上 |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | ① 组件级 60.1/60.2/60.4/60.7/60.11 已绿；**60.2 用量 ≥1 与 60.3/60.5 真网关联调归 T-09 后的真环境回归**（本票数字来自 mock 接口本地列）。② 用法区 Base URL 读构建 env：真环境需部署侧给 `REACT_APP_RELAY_PUBLIC_BASE_URL`（或保持缺省=本机 LiteLLM），夹具 URL 必须租户网络可达（contract §14 sre 风险行）。③ 经办/只读角色建议活体过一遍（jsdom 只 mock tenant_role）。 |
| `/backend`（T-09） | 若落 `LITELLM.PUBLIC_BASE_URL` 接口（如 GET /relay/usage 或 configs 面），`RelayUsage.tsx` 是唯一消费点，可一行切换；前端读模型 `fetchRelayPage` 已透传信封 message，新增字段向后兼容。 |
| `/architect` | 无契约歧义。注：Base URL 暂走构建 env（本票 §3 决策），与 ADR-0019 决策 2 的后端配置语义同值对齐——若要求「接口单一来源」请开后续票给 T-09 联动。 |
| `/sre` | 部署 admin 时设 `REACT_APP_RELAY_PUBLIC_BASE_URL` 指向租户可达的 LiteLLM 入口（勿用 docker 内网地址）；与 `AUTO_AGENTS_LITELLM__PUBLIC_BASE_URL`（后端侧，待引入）同值。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（红/绿双输出 + 构建/门禁 + 退出码原样）
- [x] 自测全绿（本票 10 例 + official 9 例 + 两 app build + frontend.sh；全量 admin 见补录）
- [x] 契约落位表已核对；未改 GWT/未实现后端 API/未动菜单真相
- [x] ORM/DBML N/A（未触及）
- [x] 无硬编码连接串/密钥（Base URL 走 env + 配置同值缺省；无 master/明文落日志）
- [x] 业务 .tsx ≤ 400 行（页 280 / 子件 41 / service 70）
- [x] 数据获取 react-query（useQuery+useMutation），无 setInterval/手写 loading
- [x] antd v6 弃用项未新增（Alert 用 `title`、Modal 用 `destroyOnHidden`，P-FE-08）
- [x] 信封 unwrap 恰一次（P-FE-04：service 层 unwrap，页面读 message 不再剥 .data）
- [x] 上游问题已回报（Base URL 接口缺失 → §8 backend/sre），未自行绕过后端域
