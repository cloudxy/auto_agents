# 前端实现证据 · T-03 注册成功主按钮去登录；企业名非空

> 票：`.sdlc/feat-four-pillars-v2/02-shape/tickets/T-03.md`｜FR 锚点：FR-04｜角色：/frontend｜日期：2026-09-08
> 上游：`02-shape/design-tokens.json` · `02-shape/flows/register-login.md` · `02-shape/edge-states.md` · `01-define/spec.md` FR-04
> 泳道：L4

未埋 `tenant_signup_succeeded`（T-12）。未改 Home/Pricing/Features、Data.tsx、Usage.tsx、`llm_client`。未加 chat UI。未代选六问。

## 1. 组件树

```
<Register>                      官网 /register：表单提交 + 同路由成功屏
  ├─ 表单                       企业名 / 管理员邮箱 / 密码（字段未删）
  │   └─ 内联 Alert             失败：注册未完成 / 离线 / SIGNUP_INCOMPLETE
  └─ 成功 Alert                 主链「登录管理后台」；次钮「再注册一家」
<Login>                         后台 /login：from 回跳 + 页脚企业注册
  ├─ 内联 Alert                 凭证 / 到期码 / 网络 / 会话过期
  └─ <a>企业注册                官网 /register
```

| 组件 | 类型 | 复用 | 提取理由 |
|---|---|---|---|
| `<Register>` | 页面 | 仅官网 | 第一次出现，不抽共用库 |
| `<Login>` | 页面 | 仅后台 | 既有页改文案与回链 |

## 2. 状态归属表

| 状态 | 放在哪 | 理由 |
|---|---|---|
| 开通结果 | `Register` `useState` | 同路由成功屏，非服务端列表 |
| 表单错误句 | 组件内 `useState` | 提交失败内联，保留输入 |
| 登录回跳 `from` | **URL query**（兼 location.state） | 成功屏外链带 `from=/dashboard`；只接受站内相对 path |
| 当前用户 | 后台 `useAuthStore` | 全应用共享 |
| 提交中 | 按钮 loading | 局部操作 |

自检：

- [x] 无 `useEffect + fetch` 手写数据获取（提交为显式 mutate）
- [x] 服务端开通结果只在成功屏展示，未再剥一层 `.data`（P-FE-04）
- [x] 无派生状态被单独存储
- [x] `from` 在 URL 查询参数里（登录回链）

## 3. 数据层

| 项 | 内容 |
|---|---|
| queryKey 设计 | 无列表查询。开通 `POST /public/tenant/signup`（`tenantSignup` 只 unwrap 一次） |
| 变更后失效范围 | 无 react-query 列表 |
| 乐观更新 | 无 |
| 竞态验证 | Jest：成功 mock 一次 payload；失败不进成功屏 ☐ 已实测（Jest） |

## 4. 六态实现与实测

> 注册 / 注册成功 / 后台登录，对照 `edge-states.md`。

| 态 | 实现 | 怎么造出来的 | 实测 |
|---|---|---|---|
| **加载（首次）** | 提交钮「创建中…」/「登录中…」 | 代码路径；非列表骨架 | ☐ 无 Slow 3G |
| **加载（刷新）** | ➖ 表单提交非列表刷新 | — | ➖ |
| **空（初始）** | ➖ 空表单是初始 | — | ➖ |
| **空（筛选后）** | ➖ | — | ➖ |
| **错误** | 「注册未完成：{原因}。改正后再次创建企业。」；占用码通用句 | Jest mock 422 / SIGNUP_INCOMPLETE | ✅ |
| **权限** | 已有企业成员：`SIGNUP_INCOMPLETE`，不泄露其它企业 | Jest + pytest viewer Bearer | ✅ |
| **离线** | 「创建企业失败：网络不可用…」；登录「登录请求失败…」+「重试」 | `navigator.onLine=false` | ✅ Jest |
| **边界** | 成功文案企业名/用户名非空书名号；`from` 拒绝 `https://` 与 `//` | Jest | ✅ |

### 错误码分支覆盖

| 契约错误码 | 前端处理 | 实测 |
|---|---|---|
| `SIGNUP_INCOMPLETE` | 「注册未完成，请检查填写内容」（不包一层原因、不点名企业） | ✅ |
| `VALIDATION_ERROR` | 「注册未完成：{message}。改正后再次创建企业。」 | ✅ |
| `AUTH_FAILED` / 401 | 「用户名或密码不正确。核对后再登录。」 | ✅ |
| `TENANT_EXPIRED` / `TENANT_DISABLED` | 「企业已到期或停用，请联系平台。」（现网 login 尚未发此码） | ☐ 映射在代码，无后端夹具 |
| `RATE_LIMITED` / 429 | 「尝试过多，请稍后再登录。」 | ☐ 代码路径 |
| 网络 / 无 response | 注册离线句 / 登录网络句 + 重试 | ✅ |
| 5xx + `request_id` | 注册未完成句后附「错误编号 {trace_id}」 | ☐ 代码路径 |
| **default** | 注册包原因；登录回退网络句 | ✅ |

- [x] 未用 `message` 做占用/越权分支（用 `code === SIGNUP_INCOMPLETE`）
- [x] `default` 分支存在

### 交互态

| 态 | 实现 | 实测 |
|---|---|---|
| hover | antd primary / default | ☐ 无真机 |
| focus | 成功后焦点落到「登录管理后台」；失败 `scrollToField` | ☐ Jest 未测焦点 |
| active | 原生按钮 | ☐ |
| disabled | 提交中 disabled +「创建中…」 | ☐ 代码 |

- [x] 异步操作：按钮 loading + disabled
- [x] 操作失败后保留用户输入（Jest 断言企业名仍在）

## 5. 九维自查

| 维 | 检查 | 结果 |
|---|---|---|
| ① 间距 | 沿用既有卡片宽 420/400、padding 24；未新造一套 spacing 文件 | ⚠ 布局数字与现网 Register/Login 同档 |
| ② 颜色 | 官网 `--color-surface*` / `--color-text-*`；后台 `index.css` 语义变量；去掉紫渐变 | ✅ |
| ③ 字体 | antd Title/Text | ✅ |
| ④ 圆角 | Card 默认 | ✅ |
| ⑤ 图标 | `@ant-design/icons` Check/User/Lock | ✅ |
| ⑥ 交互态 | loading / disabled / 内联错误 | ✅ 代码 |
| ⑦ 状态完整性 | 注册错误/权限/离线/边界；成功无独立错误态 | ✅ Jest；真机未做 |
| ⑧ 响应式 | 单列卡片 | ☐ 未 375/768 实测 |
| ⑨ 可访问性 | 见下节 | ⚠ 键盘走查未做 |

**硬编码扫描**：

```
$ rg -n '#[0-9a-fA-F]{3,8}|rgb' frontend/official/src/pages/Register.tsx frontend/admin/src/pages/Login.tsx
```

Register.tsx：无 hex。Login.tsx：仅 `var(--token, #fallback)`，fallback 与 `design-tokens.json` primitive.gray / ink 一致；定义在 `frontend/admin/src/index.css` `:root`。

**缺失的 token**：无新 token 需求。后台原先无 surface 变量，本票在 `index.css` 补语义层，未在业务页写死紫渐变。

## 6. a11y 核对

- [x] 交互元素用语义标签（Button / `<a>` / Form）
- [x] Tab 顺序：企业名 → 邮箱 → 密码 → 创建企业；成功屏主钮 → 次钮；登录 用户名 → 密码 → 登录 → 企业注册
- [x] Enter 提交（htmlType=submit）
- [x] 焦点：成功屏 `focus()` 主钮；失败 `scrollToField`
- [ ] 弹窗：本票无 Modal
- [x] 表单 label（企业名/管理员邮箱/密码；登录保留 placeholder 以兼容 `App.test`）
- [x] 错误 `role="alert"`
- [x] 图标在有文案的按钮内，未单独纯图标
- [x] 成功 `aria-live="polite"`
- [x] 对比度：textPrimary/textSecondary on surface（token 合同已审）
- [x] 不只靠颜色（Alert showIcon）

**键盘走查**：☐ 无真机；Jest 点击路径已覆盖主/次钮

两字按钮 `autoInsertSpace={false}`（「登录」）。

## 7. 响应式

| 断点 | 来源 | 实测 | 表格/宽内容处理 |
|---|---|---|---|
| 375 | 单列 Card | ☐ | 成功企业名 `ellipsis` + tooltip |
| 768 | 同 | ☐ | |
| 1440 | 居中卡片 | ☐ | |

- [ ] 断点值来自 tokens，未自定义 — 本票无新断点
- [x] 主/次按钮为 antd 控件（触摸目标随组件）
- [x] 超长企业名截断展示，提交仍走完整值（maxLength 128 对齐后端）

## 8. 性能

| 项 | 措施 | 数字 |
|---|---|---|
| 路由懒加载 | 既有 `React.lazy` Register / Login | official gzip main 148.68 kB |
| 首屏包大小 | CRA 分包 | 见构建日志 |
| 长列表 | ➖ 表单页 | |
| 重渲染 | 无列表轮询 | |

路由三件套：☑ 懒加载 ☑ 后台 ErrorBoundary ☑ 404 兜底（既有；本票未改 App 路由表）

## 9. 自测证据

> 命令与退出码**原样粘贴**。

```
$ npm run build --prefix frontend/official
> official@0.1.0 build
> react-scripts build

Creating an optimized production build...
Compiled successfully.

File sizes after gzip:

  148.68 kB  build/static/js/main.6a73b557.js
  ...
The build folder is ready to be deployed.
exit: 0
```

```
$ npm test --prefix frontend/official -- --watchAll=false
PASS src/pages/Register.test.tsx
PASS src/pages/Home.test.tsx
PASS src/pages/Pricing.test.tsx
PASS src/pages/SkillsSquare.test.tsx
PASS src/components/home/FeaturesSection.test.tsx
PASS src/App.test.tsx
Test Suites: 6 passed, 6 total
Tests:       20 passed, 20 total
exit: 0
```

```
$ npm test --prefix frontend/admin -- --testPathPattern='Login.test|App.test' --watchAll=false
PASS src/App.test.tsx
PASS src/pages/Login.test.tsx
Test Suites: 2 passed, 2 total
Tests:       8 passed, 8 total
exit: 0
```

```
$ uv run pytest -x -q backend/tests/test_saas_signup_expiry.py backend/tests/test_b1_rate_limiter.py
..................                                                       [100%]
18 passed, 1 warning in 2.84s
exit: 0
```

```
$ bash tools/check/frontend.sh
前端工程门禁（F-2/F-3/F-4/F-5/F-6/F-7 已启用；F-1 批次 2 已由 service 归一承接）
==============================================================
✓ 前端工程门禁通过
exit: 0
```

```
$ bash tools/check/arch.sh
...
❌ R10: service 方法入口缺 logger
backend/services/quota_service.py:52: def build_usage_alerts(
共 1 处违规
exit: 1
```

R10 在 `quota_service.build_usage_alerts`（`logger.debug` 非 `info`），**非本票改动**（T-09 用量面）。本票改动的 `tenant_signup_service.signup` 有入口 `logger.info`。未为绿闸去改 T-09 文件。

### 验收项对应

| GWT | 覆盖方式 | 结果 |
|---|---|---|
| GWT-04.1 | Register Jest：成功文案含企业名+负责人；主链 `{ADMIN}/login?from=/dashboard`；Login Jest：`from=/spiders/tasks` 回跳 | ✅ |
| GWT-04.2 | Register Jest 失败无成功屏；pytest 弱密码不落租户、不可登录 | ✅ |
| GWT-04.3 | 次钮才「再注册一家」；Login 页脚「没有账号？企业注册」→ `http://localhost:9113/register` | ✅ |
| GWT-04.4 | pytest：viewer Bearer 提交不改 Victim Co、不建 Hijack、通用 `SIGNUP_INCOMPLETE`；前端占用失败不渲染「已注册/加入企业」 | ✅ |

## 10. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 官网 `/register` 成功主按钮外链后台登录；失败留表单。后台 `/login?from=` 只认站内 path。占用失败码 `SIGNUP_INCOMPLETE`。Jest mock `tenantSignup` / `auth.login`。未做真机键盘。 |
| `/designer` | 成功屏用 Alert+双钮，无独立路由。登录去掉紫渐变。 |
| `/architect` | 公开 signup 增加可选 Bearer → `actor_tenant_id`；只 INSERT。错误码 `SIGNUP_INCOMPLETE`。 |
| `/backend` | FR-08：`authenticate` 仍对到期租户走凭证失败；Login 已按 `TENANT_EXPIRED`/`TENANT_DISABLED` 分句，现网发不出则到期仍显示凭证句。本票不代做到期执法。 |

## 11. 交票自检

- [x] 九维自查已填（真机项标明未做）
- [x] 六态：错误/权限/离线/边界有 Jest 或 pytest；加载/键盘真机未做
- [x] 错误码：占用走 code 分支 + default
- [x] 业务色走 token；Login 仅 var fallback
- [x] 无手写 `useEffect + fetch`
- [x] `from` 在 URL
- [x] a11y 基线；键盘走查未做
- [ ] 每个断点实测
- [x] 指定闸 `npm run build --prefix frontend/official` exit 0；相关单测 exit 0
- [x] 路由三件套沿用既有
- [x] FR-08 码缺口回报 backend，未假装到期句已接通
- [ ] 票状态仍由编排改 done（本角色不改 GWT 文件）
