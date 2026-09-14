# 实现证据 · T-11 商店详情 `<script>` 纯文本钉死本页

> 票：contract.md T-11｜FR 锚点：FR-U13｜角色：/frontend｜日期：2026-09-12
> 上游：`01-define/spec.md` v1.2 FR-U13 · `02-shape/edge-states.md` 屏 4 · `02-shape/contract.md` T-11 / [SEC-5]
> 泳道：ui｜未做结账 / 未写「当前可买」

商店详情（总开关打开后访客/经办实际打开的那页）把不可信 SKILL.md / `body_md` 当 **React 文本子节点** 渲染。`<script>alert(1)</script>` 与 `<img onerror>` 作为字符可见；页上无因该正文产生的 `script`/`img` 节点，`window.alert` 不被调用。禁止 Markdown/HTML 执行。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 路径/方法/状态码 | 官网路由 `/capabilities/:type/:slug` | `frontend/official/src/pages/CapabilityDetail.tsx` | 404 → 商店不存在句，不渲染正文 |
| 字段校验（类型/范围/枚举） | ➖ N/A | | 只读展示 |
| 跨字段参数约束 | ➖ N/A | | |
| 权限判定（数据范围） | 公开详情；未上架走 404 | 同上 + `NotFound.tsx` | GWT-U13.3：不渲染该正文 |
| 业务规则/状态流转 | 展示组件 | `SkillMdBlock` + `pickUntrustedBody` | 非空 → `<pre data-testid="skill-md">` 文本节点；空 →「暂无说明」 |
| 数据读写 | `useQuery` 读公开详情 | `getPublicAsset` | 正文不经 HTML/Markdown |
| 错误码映射 | 404 vs 其它失败 | `isStoreNotFound` | 404 同官网不存在句；其它「能力详情加载失败」+「重试」 |
| 幂等 | ➖ N/A | | 只读页 |

**分层依赖核对**：☑ 未改 backend Router/ORM/Schema ☑ official 未 import admin ☑ 未新建结账/checkout 页

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/official/src/pages/CapabilityDetail.tsx` | 修改 | `SkillMdBlock`：不可信正文 React 文本；空态「暂无说明」 |
| `frontend/official/src/pages/CapabilityDetail.css` | 修改 | 空态句 token 色 |
| `frontend/official/src/pages/CapabilityDetail.test.tsx` | 修改 | GWT-U13.1/2/3；payload=`<script>alert(1)</script>` + img onerror |
| `frontend/admin/src/pages/Skills.tsx` | 修改 | 治理 Drawer SKILL.md `data-testid="skill-md"` 文本节点；antd v6 `title`/`size`/`destroyOnHidden`（P-FE-08 触及即改） |
| `frontend/admin/src/pages/Skills.test.tsx` | 修改 | 治理详情同一 XSS 钉 |
| `.sdlc/upgrade-four-pillars/03-impl/T-11-evidence.md` | 新增 | 本文件 |

**与票里「会改哪些文件」一致**：☑ 是（`frontend/official` CapabilityDetail + 测试；admin 仅因其渲染 SKILL.md）

**未触碰「不许改的文件」**：☑ 确认（未做 checkout / 未写「当前可买」；未改 GWT / schema / tokens）

## 3. 关键实现决策

不可信正文只进 `{text}` 文本子节点，不进 `dangerouslySetInnerHTML`、不进 Markdown。空正文不渲染 `<pre>`，锁句「暂无说明」（GWT-U13.2 / 屏 4 空）。未上架/黑名单走官网 404，正文区不出现。治理 Skills Drawer 同一钉，避免只验收广场/旧页。

### 事务边界

| 操作组 | 是否同事务 | 理由 |
|---|---|---|
| 无写路径 | ➖ N/A | 公开详情只读 |

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
| `GET` 公开能力详情 | react-query `retry: false`（本页） | 区块「重试」 | 失败句；404 不渲染正文 | 读 |

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
| 入口日志 | 官网无新 service 写 |
| trace_id | 失败不展示 code/堆栈（锁句） |
| 错误日志上下文 | ➖ 无新后端入口 |
| 慢操作时耗 | ➖ |

**日志脱敏核对**：☑ 无密码 ☑ 无 token ☑ 无完整手机号/身份证 ☑ 无卡号 ☑ 无完整地址 ☑ 无商户密钥

## 6. 自测证据

> 命令与退出码**原样粘贴**。「测试通过」「基本完成」不算证据。

```
$ cd /Users/xuyun/auto_agents/frontend/official && npm test -- --watchAll=false src/pages/CapabilityDetail.test.tsx

> official@0.1.0 test
> jest --maxWorkers=2 --watchAll=false src/pages/CapabilityDetail.test.tsx

PASS src/pages/CapabilityDetail.test.tsx
  ✓ GWT-U13.1 skill body is text: <script>alert(1)</script> visible, no script/img from body (110 ms)
  ✓ GWT-U13.2 empty skill_md shows 暂无说明 and does not execute script (29 ms)
  ✓ GWT-32.5 unlisted parent origin is plain text, not a store link (24 ms)
  ✓ listed parent origin renders a store link when href is present (23 ms)
  ✓ GWT-U13.3 unlisted GET is store-missing copy, body not rendered, no script (212 ms)
  ✓ load failure shows retry copy, not empty success (127 ms)
  ✓ offline failure uses offline copy (21 ms)
  ✓ coming_soon has preview mark, no subscribe, no gift-pack or enable-host copy (25 ms)
  ✓ listed detail offers 登录后订阅 and no gift-pack copy (36 ms)
  ✓ login-after-subscribe CTA href has subscribeType and subscribeName, not from=/capabilities/ (35 ms)
  ✓ hides 登录后订阅 when REACT_APP_ADMIN_URL is unset (25 ms)
  ✓ GWT-39.1 command detail shows slash, body as text, subscribe, not plugin JSON (51 ms)

Test Suites: 1 passed, 1 total
Tests:       12 passed, 12 total
Snapshots:   0 total
Time:        3.742 s
Ran all test suites matching /src\/pages\/CapabilityDetail.test.tsx/i.
exit: 0
```

```
$ cd /Users/xuyun/auto_agents/frontend/admin && npm test -- --watchAll=false src/pages/Skills.test.tsx

PASS src/pages/Skills.test.tsx (6.088 s)
  ✓ renders skill list with dual score columns (941 ms)
  ✓ readonly mode hides correction column and shows hint (851 ms)
  ✓ GWT-U13.1 admin SKILL.md is text: <script>alert(1)</script> visible, no script/img (889 ms)

Test Suites: 1 passed, 1 total
Tests:       3 passed, 3 total
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
$ rg -n '当前可买' frontend/official/src --glob '!*.test.*'
(no matches)
exit: 1
```

```
$ rg -n 'dangerouslySetInnerHTML|ReactMarkdown|remark-gfm|rehype' frontend/official/src/pages/CapabilityDetail.tsx frontend/admin/src/pages/Skills.tsx
(no matches)
exit: 1
```

非测试官网源码 0 命中「当前可买」。触及的详情页无 HTML/Markdown 渲染器。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-U13.1 正常 | `GWT-U13.1 skill body is text: <script>alert(1)</script> visible, no script/img from body`；admin `GWT-U13.1 admin SKILL.md is text…` | ✅ 字符可见；无 script/img；alert 未调用 |
| GWT-U13.2 空态 | `GWT-U13.2 empty skill_md shows 暂无说明 and does not execute script` | ✅ 「暂无说明」；无 `skill-md` pre；无 script |
| GWT-U13.3 越权 | `GWT-U13.3 unlisted GET is store-missing copy, body not rendered, no script` | ✅ 官网 404 句；不渲染正文；404 HTML 内 XSS 不进 DOM |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（无多步写） |
| 幂等 | — | ➖ N/A（无新建写） |
| 并发写 | — | ➖ N/A（无并发写） |
| 外部依赖失败 | `load failure shows retry copy, not empty success`；GWT-U13.3 404 | ✅ 失败不装成功详情；404 不渲染不可信正文 |

## 7. NFR 验证（票里有 NFR 时填）

| NFR | 要求 | 实测 | 环境 |
|---|---|---|---|
| NFR-U04 / FR-U13 / [SEC-5] | SKILL.md 纯文本，禁止 HTML 执行 | Jest：payload 作 textContent；innerHTML 为 `&lt;script&gt;`；无 script/img 节点 | jsdom |
| NFR-U06 / FR-U24（本页） | 详情不写「当前可买」 | GWT-U13.1 断言 + official 非测试源 rg 0 | jsdom / 源码 |
| 屏 4 离线 | 失败锁句 | `offline failure uses offline copy` | jsdom |

九维（本票触及）：正文 `pre` 用 token 字号/色/圆角/焦点环（既有 `.capability-detail__body`）；空态 secondary token。不改 Markdown、不重画全页。交互：正文区 `tabIndex={0}` 可聚焦滚动。未做 checkout。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 官网 `data-testid="skill-md"`（非空）/ `skill-md-empty`（「暂无说明」）。XSS fixture：`<script>alert(1)</script> <img src=x onerror=alert(1)>`。未上架 mock 404。治理 Skills 点行标题打开 Drawer，同一 `skill-md`。 |
| `/frontend` | T-19 结账不得改本页渲染器。T-23 全站「当前可买」机械钉仍待做；本页已断言无该四字。 |
| `/architect` | 无新错误码。未上架/黑名单依赖后端 404；前端不渲染失败信封里的 HTML。 |

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
- [x] 外部依赖四件套齐全（超时/重试/降级/幂等前提）— 详情读：retry false + 区块降级
- [x] 四类易漏测试已覆盖或标 N/A 并给理由
- [x] 发现的上游问题已回报，未自行绕过
- [x] 无 `tickets/T-11.md`（shape 不写票文件）；本证据即交票物
- [x] 未写「当前可买」；未建 checkout
