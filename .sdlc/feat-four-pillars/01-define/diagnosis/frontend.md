# 前端诊断 · feat-four-pillars（定义帽 / frontend）

| 字段 | 值 |
|------|----|
| 角色 | frontend（只读诊断，不实现产品 UI） |
| 泳道 | L4 · `feat-four-pillars` |
| 对照 | `01-define/spec.md` v1（Wave 0/1 冻结）· `power-market-design.md` D1–D21 Accepted |
| 范围 | `frontend/admin/src/` · `frontend/official/src/` · `frontend/shared/` |
| 拒绝 | 不定 tokens（→ designer）· 不写 API/schema（→ backend）· 不做放行判决（→ qc） |
| 本轮核实 | `bash scripts/check-frontend.sh` **exit 0**；`frontend/admin` Jest **5 suites / 13 passed**；`frontend/official` Jest **2 suites / 3 passed**。未跑 `npm run build`（定义帽无前端实现；`sdlc.config.yaml` build 闸门留实现帽） |

**一句话结论：** 双前端能演示「采集工作台 + 企业开通 + 中转值班页 + P6 四类目录」，但 **对照冻结 FR，Wave 0 的诚实/收权/激活链全部未履约，Wave 1 商店面与治理台零开工**。官网仍是采集产品页 + 双广场；后台仍是四 Tab 扫描器；`requireAdmin` 把租户 `role=admin` 当成平台超管；数据层大半 `useEffect+fetch`；埋点客户端不存在。技能广场的搜索/XSS 纯文本是唯一必须迁走、不能直接删的浏览面。

---

## 0. 相对上一版诊断的变化（本轮复核）

代码面与上一份诊断 **基本同构**（Power Market 字段 `listing_state` / `installable` / `btn:market:*` 前端 **零命中**）。新增的是 **spec 冻结 FR 对照** 与本轮闸门/测试指纹。纠正两点旧述：

| 旧述 | 本轮 |
|------|------|
| Hero 示意数字未标注 | 有脚注「\* 示意数据，非实时统计」，但 **128,000+ / 12 节点 / 3.2 亿条仍渲染** → 仍不满足 FR-02（「不出现」这类绝对规模） |
| `check-frontend.sh` 只启用 F-2/5/6 | 现启用 **F-2/3/4/5/6/7**，本轮 exit 0。F-4 只禁 `#1890ff`，新硬编码 `#1677ff` 漏网 |
| 未跑 Jest | 本轮双端测试全绿（见上）；**无** Capabilities / Register / NewApiOps / Pricing 用例 |

---

## 1. 现状地图

### 1.1 官网 `frontend/official`（9113）

路由源：[`frontend/official/src/App.tsx`](frontend/official/src/App.tsx)。壳：[`SiteLayout.tsx`](frontend/official/src/components/layout/SiteLayout.tsx)。**无登录态、无 ErrorBoundary、无 `useQuery` 消费方**（`index.tsx` 挂了 `QueryClientProvider`，全站 0 处 `useQuery`）。

| 路由 | 文件 | 现状 | 冻结 FR |
|------|------|------|---------|
| `/` | `Home.tsx` + `components/home/*` | Slogan「AI 驱动的智能数据采集系统」；Hero 示意大数；Features 五张采集卡含 **CSV/Excel**；`SkillsSection` 链 `/skills` | FR-01、FR-02、FR-03、FR-17、Q-VOICE |
| `/skills` | `SkillsSquare.tsx` | 搜索 + 分类 + 卡片键盘 + 详情 Modal；**`GET /public/skills`**；`?q=` 深链；SKILL.md 纯文本（有 XSS 测试） | FR-17：应到达 `/capabilities?type=skill`；新 UI 不得再调 deprecated 接口 |
| `/capabilities` | `pages/Capabilities.tsx` | 四 Tab 卡片；无搜索/详情/分页；错误 **catch→空列表** | FR-17…19、FR-28 |
| `/register` | `Register.tsx` | `POST /public/tenant/signup`；成功 **双重 unwrap**；主按钮「再注册一家」 | FR-04 **现网 bug** |
| `/pricing` | `Pricing.tsx` | 三档；专业「联系升级」/企业「联系销售」**仍 `navigate('/register')`**；卖工单/渠道组/私有技能库 | FR-01、FR-05、Q-PRICE |
| `*` | `NotFound.tsx` | 有 | 无详情 404 语义（alias 未命中） |

导航仍并列「技能广场」「能力广场」（`NAV_LINKS`）。无 `/login`、无 `/capabilities/:type/:slug`、无「我的安装」。Header「管理后台」外链 `REACT_APP_ADMIN_URL`。

### 1.2 后台 `frontend/admin`（9112）

路由源：[`App.tsx`](frontend/admin/src/App.tsx)（lazy + 路由级 `ErrorBoundary` + 404）。菜单五组：[`menuConfig.tsx`](frontend/admin/src/config/menuConfig.tsx)。守卫：[`ProtectedRoute.tsx`](frontend/admin/src/components/ProtectedRoute.tsx) 只认登录 + `role==='admin' \|\| is_admin`。

| 路由 | 权限壳 | 备注 |
|------|--------|------|
| `/login` | 公开 | placeholder 当 label；**无「去企业注册」**（FR-04.3） |
| `/dashboard` | 登录 | `useEffect` 拉 `/admin/stats`；零任务三步引导 **第 1 步链 `/llm`** |
| `/spiders/tasks` · `/logs` · `/nodes` | 登录 | 任务列表 / 日志抽屉 / 节点 = react-query 示范 |
| `/ai` | 登录 | 向导轮询 query，结果 **复制进 `plan` state** |
| `/data` | 登录 | 导出硬顶 100 条 CSV；注释写死；无 xlsx 按钮（实现侧对，官网页不对） |
| `/capabilities` | 登录 | 四 Tab；菜单叶 **「资产目录」**；插件验证 **未走 `usePermission`** |
| `/members` · `/usage` | 登录 + `tenantOnly` | 成员 422 占用已产品化（有测试）；用量 Alert **泄漏 `QUOTA_EXCEEDED`** |
| `/platform-ops` `/enterprise` `/rbac` `/llm` `/newapi` `/users` `/settings` | `requireAdmin` | **租户公司管理员可进**（FR-06/07） |
| `/enterprise` `/rbac` | 有路由无菜单 | 幽灵页 |
| `/unauthorized` · `*` | — | 有 |

**不存在：** `/capabilities/:type/:nameOrSlug`、源 Tab、listing 开关、租户「我的安装」、计费/发票、官网会话。

---

## 2. Wave 0 冻结 FR · 前端对照

> 只列界面能单独证伪的项。配额入队/密钥跟踪属 backend/sre，这里只写用户可见面。

| FR | 用户可见要求 | 今日前端 | 判 |
|----|----------------|----------|----|
| **FR-01** 承诺可走完或标预告 | 定价/首页「现在就能用」必须可走完；工单/渠道组/私有库不得当可买 | 定价三档功能列表无预告标；企业档写「中转站渠道组分配」「私有技能库」；Features 写 Excel | **不满足** |
| **FR-02** 不展示虚构规模 | 不出现 128,000+ / 12 节点 / 3.2 亿条 | `Home.tsx` `HERO_STATS` 原样渲染；仅 12px 脚注「示意数据」 | **不满足**（脚注 ≠ 不出现） |
| **FR-03** 导出格式诚实 | 选项只列会生成的格式；写明单次最多 100 条 | 数据中心：**CSV 按钮 + 文案「前 100 条」**（相对诚实）；结果抽屉 csv/json。官网 Features：**「CSV / Excel 一键导出」** | 后台部分满足；**官网不满足** |
| **FR-04** 注册成功能去登录 | 成功页主按钮「登录管理后台」 | 成功解包失败见 §5.1；主按钮 `href="/register"` + reload「再注册一家」；文案却写「即可登录开始第一次采集」。登录页无回官网注册 | **不满足（P0 现网）** |
| **FR-05** 付费 CTA ≠ 免费注册 | 专业/企业主按钮不得进同一注册表 | 三档 `cta.href` 全是 `'/register'`，只是 label 不同 | **不满足** |
| **FR-06** 目录写仅平台超管 | 扫描/验证/上架对租户拒绝；按钮隐藏或禁用+说明 | 插件「扫描/验证」、专家扫描、组建专家团：**无 `usePermission('btn:plugin:verify' \| 'btn:market:*')`**。路由 `/capabilities` 任何登录者可进。租户 admin 因 `requireAdmin` 过宽，连 `/users` `/settings` 也能进 | **不满足** |
| **FR-07** 渠道/平台 LLM 写仅超管 | 租户提交改额度必须拒绝；只读若关闭则进页即拒 | `/newapi` `/llm` 包在 `requireAdmin`。`LoginResponse` **无 `is_platform_admin`**（`UserItem` 才有）。租户 `role=admin` 与平台超管同一壳 | **不满足** |
| **FR-08** 只见本租户任务 | 空态是「还没有采集任务」+ 新增，不是别人的数据 | 任务列表有 Empty；隔离靠后端。前端无跨租户 ID 探测 UI | 空态可接受；越权不在前端测 |
| **FR-11** 候选不进「我的结果」 | 数据中心看不到市场候选 | 数据中心打 `/spiders/results`；候选在 Skills 内层 Tab。前端未把候选混进结果表 | **表面满足**（数据面靠后端） |
| **FR-12** 将满/超限有下一步，不露内部码 | 70% 警告；满额文案 +「去结果库 / 申请提升」；禁止 `QUOTA_EXCEEDED` | 用量：Progress 颜色分 70/90，**无将满文案、无主按钮**。页顶 Alert **明文 `429 QUOTA_EXCEEDED`**。任务创建失败不按 code 分支 | **不满足** |
| **FR-13** 不暴露本机路径 | 公开/管理详情无 file_path | 技能 Drawer 展示 SKILL.md / source_url / source_type，未见 `file_path` 列 | **目前未展示**；Wave 1 详情不得把 `origin_ref` 当路径渲染 |
| **FR-15** 获客漏斗事件 | `official_page_viewed` / `official_cta_clicked` / signup / login / task_* / export / quota_exceeded | 双前端 **零** `gtag` / `trackEvent` / 自建 beacon | **不满足** |
| **FR-16** 时区口径写在页上 | Asia/Shanghai；「近 7 日」与「本月」不得混窗 | Dashboard「近 7 日采集结果」绑 `stats.total_results`（字段名像全量）；成功率无窗。用量「本月」无时区。`toLocaleString('zh-CN')` 无显式 timeZone | **不满足** |

Wave 0 前端最小切片（给塑形，不在本期做）：删 Hero 大数与 Excel 卖点；定价 CTA 拆出口；Register 解包 + 去登录；Login 回链注册；`ProtectedRoute` 改平台超管字段；插件验证/扫描/中转写按钮按权限码隐藏；Usage 换 FR-12 词表；埋点 SDK 位。**不要在 Wave 0 画商店面。**

---

## 3. Wave 1 冻结 FR · Power Market 缺口

设计把现有 hub **升级**为市场。实现停在 P6。词表冻结：对用户说「能力市场」，禁用「技能广场 / 能力广场 / 资产目录」。

### 3.1 管理端治理台 — [`pages/Capabilities.tsx`](frontend/admin/src/pages/Capabilities.tsx)

| 设计 v1（顶栏 ≤ 6 Tab） | 今日 | FR |
|-------------------------|------|----|
| **源**：登记/启用/同步/`last_sync_at`/`last_hash`/jobs | 无 UI、无 `services` 方法 | FR-25 |
| **目录**：listing/status/tier/source/origin；行内开关；alias；许可 override | 无独立目录 Tab；`AssetRow` 无 `listing_state` / `license` / `source_name` | FR-22、FR-23 |
| **插件**：版本、license、health、bundled、验证、上架；enable-host **PR8 再画** | `PluginTab`：扫描 + 验证；文案「插件经 MCP 验证后方可分发」；验证按钮无权限码 | FR-06、FR-26 |
| **技能**：origin/source/listing 列；内层矩阵/候选；文案「市场入站」 | `Skills` 内嵌；候选仍「来源：skill_harvester…source=marketplace」 | FR-11、FR-27 |
| **专家 / 专家团** + listing | 扫描/组建/导出 | FR-24 |
| 插件详情 Drawer；`dev-team` 不可上架提示 | 行内只有「验证」 | FR-22 / D20 |
| 菜单「能力市场」；`btn:market:*` | 菜单「资产目录」`menu:skills` | FR-22 |

Tab 在组件 `useState`，**不在 URL**。内层 `Skills` 再套 Tabs → 双层 Tab。

`services/capabilities.ts` 仅：`GET /capabilities`、`POST scan-plugins`、`POST plugins/{name}/verify`、`POST scan-experts`、`POST teams`。无 sources / listing / aliases / license-override / components / installs。

专家团导出：`window.open('/api/v1/capabilities/teams/{name}/export')` **不带 Bearer、不走 `REACT_APP_API_BASE_URL`**。

技能矫正成功文案假设写回 `meta.yaml`；第三方 `writable=0` 后需展示 `written_back: false, reason: "third_party_source"`（D5 / FR-27）。状态筛 **没有 `blacklist`**。

### 3.2 官网商店面 — [`pages/Capabilities.tsx`](frontend/official/src/pages/Capabilities.tsx)

```tsx
useEffect(() => {
  listPublic(type).then((d) => setItems(d.items || [])).catch(() => setItems([]))
    .finally(() => setLoading(false))
}, [type])
```

| 设计 / FR | 今日 |
|-----------|------|
| 导航只留「能力市场」（FR-17） | 「技能广场」+「能力广场」 |
| `/skills` → `/capabilities?type=skill` | 独立页，打 **deprecated** `/public/skills` |
| 搜索 + 类型 + 分类 + 宿主；短名命中（FR-19） | 无搜索；Tab 不写 URL；无 `host_compat` |
| coming_soon 预告、无安装按钮（FR-18/20） | 无 `listing_state`；`PublicAsset` 只有 type/name/title/description/category/tier/score |
| `/capabilities/:type/:nameOrSlug`（FR-19） | 无详情路由；卡片不可点、无键盘 |
| 登录订阅 +「我的安装」（FR-20/21） | 官网 **零鉴权**；无 session、无 installs client |
| 失败不得装空（FR-28） | catch →「暂无已发布 X」 |
| 下架后安装保留（FR-29） | 无安装面 |
| 市场埋点（FR-30） | 无 |
| 第一方已发布在闸门打开后仍可见（FR-31） | 公开列表仍只吃后端今日闸（stable）；前端无 listing 样式 |

[`SkillsSection.tsx`](frontend/official/src/components/home/SkillsSection.tsx) 链 `/skills`，卡片 `window.location.href` 硬跳。失败同样当空（QA-09）。

`frontend/shared/src/types/skills.ts` 的 `PublicAsset` 未含 `listing_state` / `installable` / `license` / `source_name` / `health_status` / `origin_local_name`。`schema.d.ts` 仍是 P6：`/public/capabilities` 列表、无 `/{type}/{name}`、无 `/tenants/me/installs`、无 `/capabilities/sources`。

官网 [`SkillsSquare.tsx`](frontend/official/src/pages/SkillsSquare.tsx) 是商店面里 **唯一接近完整** 的浏览体验（`?q=`、卡片 `role="button"`、纯文本防 XSS、有测试）。退役必须把这些迁到 `/capabilities`，**禁止直接删**（spec T-27、QA-05）。

---

## 4. 其余两柱（采集执行面 / 中转站）

### 4.1 智能采集（相对成熟；Wave 4 stub）

| 能力 | 数据层 | 六态 / 缺口 |
|------|--------|-------------|
| 任务列表 + 未终态 3s 轮询 | **react-query**（示范） | 筛选空/初始空未分；筛选/分页 **不在 URL** |
| 日志抽屉终态停轮询 | react-query 2s | 空日志有 Empty |
| 节点心跳 | react-query 15s | 空=「暂无在线节点…心跳 10s」；**提交任务前不拦无 Worker**（FR-71 属 Wave 4） |
| 结果抽屉 | useEffect | 切任务防闪空；store 失败静默；导出 csv/json |
| 数据中心 | useEffect | 导出 100 条有文案；筛选不在 URL |
| AI 向导 | query 结果 **setPlan** | 向导三步清晰；试采未通过的上线拒绝靠后端 |
| `SpiderLogs` | 日志 query；任务下拉 useEffect **只 50 条** | 无任务错误被吞 |
| Dashboard 零任务引导 | — | 四柱里最好的空态邀请；但第 1 步把租户送去平台 LLM 页 |

采集域不要挤进 Wave 0/1 商店面，除非诚实改口（Excel、大数）。

### 4.2 中转站（管控面可用，权限与词表落后）

[`NewApiOps.tsx`](frontend/admin/src/pages/NewApiOps.tsx) + Probe/Events。已有：渠道总览、管理面不可达降级 Alert、额度配置写入、探针 verdict、事件时间线。文件头仍写「全只读无写操作」——**注释腐坏**（已有配置 Modal）。

- 全部 `useState+useEffect`，没用 react-query；Tab/渠道 ID 不在 URL。
- `message.error('获取…失败')` **未走 `apiErrorMessage`**（F-2 只扫 instanceof 写法，漏检字面量）。
- 路由 `requireAdmin` → 租户 admin 可能改窗口额度（FR-07）。
- verdict Tag 仍写 `original 正品`（词表允许「正品」，英文枚举可藏）。
- 定价企业档「渠道组」无对应租户 UI（Q-RELAY；Wave 0 先删空头）。

---

## 5. 状态与数据层

对照技能 `state-and-data.md`：服务端数据进 react-query；筛选项进 URL。

### 5.1 P0 现网：注册双重 unwrap（FR-04）

```24:30:frontend/official/src/pages/Register.tsx
      const result = await tenantSignup(values)
        .then((r) => (r as unknown as { data: SignupResult }).data)
```

`tenantSignup` 已 `unwrap<SignupResult>`。拦截器返回信封，service 再剥 `data`。页面再取 `.data` → `done.tenant.name` / `done.owner.username` 为 `undefined`。用户看到「企业「」注册成功」。同类 bug 曾在 Members/skills 修过（commit `e497004`），官网注册漏网。**无 Register 测试。**

### 5.2 react-query 实际覆盖（admin）

仅：`AdminLayout` 动态菜单、`Spiders` 任务列表、`LogDrawer`、`SpiderLogs` 日志、`Nodes`、`useAiPlanFlow` 两处轮询。

**未覆盖：** Dashboard、Data、Capabilities 全家、Skills / Matrix / Candidates、Members、Usage、PlatformOps、Enterprise、Rbac、Users、Settings、LogCenter 审计、LlmProviders、NewApiOps 全家、ResultDrawer、File/Schedule/Alert/Template、**official 全站**。

`useAiPlanFlow`：`useQuery` 拉到 `freshPlan` 后 `setPlan(freshPlan)`，再以 `plan` 为真相——竞态窗口回到手写时代。

### 5.3 URL 作为状态容器

| 应进 URL（FR-17/19 商店面为 P0） | 今日 |
|----------------------------------|------|
| 官网市场 type/q/category/host/page | Capabilities Tab 纯 state；SkillsSquare 仅 `?q=` |
| 后台 capabilities 顶 Tab | `useState('skills')` |
| 技能库 filters/page | `useState` |
| 爬虫任务筛选/分页 | `useState`（Wave 0 可不做） |
| 中转站 Tab + channel_id | `useState` |

### 5.4 权限缓存 vs 平台写面（FR-06/07 交火）

[`usePermission.ts`](frontend/admin/src/hooks/usePermission.ts)：模块级 `cachedPermissions`。F5 后 persist 恢复登录、缓存归零 → 挂载补拉（有测试）。后端不可达时 **空缓存展示全量菜单**（`bea13b5`，有测试），只递归滤 `tenantOnly`（`fdeedfe` / F-T10-1，有测试）。

注释写明「菜单可见性是 UI 优化，安全防线在 API」。**前端路由守卫与此叠加后不是优化：** `requireAdmin` 用 `role==='admin'`，租户公司管理员直达 `/newapi` `/llm` `/platform-ops`。Wave 0 必须同时改：(1) 登录载荷平台超管字段；(2) `ProtectedRoute`；(3) 市场/中转/LLM **写按钮** `usePermission`；(4) 空缓存兜底不得把平台写入口当「全开」。

`useAuthStore` persist 注释承认 rememberMe 关页后 token 仍在 localStorage（技能 gotcha；本波可不清，但市场写面收权后更危险）。

### 5.5 其它

- **错误当空：** 官网 Capabilities / SkillsSquare / SkillsSection `catch → setItems([])`。断网、5xx、限流与「暂无已发布」不可分（FR-28）。
- **分页截断：** admin `listAssets(..., page_size: 50)` + `pagination={false}`；official 同 50；SkillsSquare `PAGE_SIZE=60` 无翻页。
- **分类侧面：** SkillsSquare 计数来自 **当前结果集**，搜完再筛丢类目。
- **shared dist 过期：** `package.json` `"main": "dist/index.js"`。本轮核对：`src/index.ts` 已不导出 `queryViewState`，**`dist/index.js` 仍 `export { queryViewState } from './query/state'`**，且 `src/query/` 已不存在。改 shared 源码后必须 `npm run build -w @auto-agents/frontend-shared`。
- **F-2 漏检：** 18 处 `message.error('固定中文')` 不含 instanceof，门禁放行，用户看不到后端 `message` / `request_id`。

---

## 6. Public vs Admin API 使用

| 调用方 | 端点 | 对错 |
|--------|------|------|
| official Capabilities | `GET /public/capabilities` | 对（D19 公开前缀） |
| official SkillsSquare / SkillsSection / Home | `GET /public/skills`、`GET /public/skills/{name}` | **错**（新 UI 不得调用；应 `type=skill`） |
| official Register | `POST /public/tenant/signup` | 对 |
| official 其它 | 无鉴权 client，无 `/tenants/me/*` | 安装 API 无法接 |
| admin Capabilities | `GET /capabilities` | 对（治理列表） |
| admin Skills | `/skills*` | 对；市场列应来自 asset join |
| admin 插件验证/扫描 | `POST …/scan-plugins` · `…/verify` | 端点对，守卫未收到前端权限码 |
| admin 专家团导出 | 浏览器直开 `/api/v1/.../export` | **错**：丢 token、丢 baseURL |
| admin 用量/成员 | `/tenants/me/usage` · `/members` | 对 |
| admin 中转站 | `/newapi/*` | 对（平台管控）；权限壳过宽 |
| admin 仪表盘 | `/admin/stats` | 对；租户能否看平台合计取决于后端，前端未标「本企业 / 平台合计」 |

`frontend/shared` 工厂注释正确：admin 注入 token，official 不注入。D10 把订阅放官网就必须给 official **有限鉴权**（或跳后台带 `returnUrl`），否则会把租户安装打到公开 client 上。

---

## 7. 六态与边界

设计矩阵尚未作为独立 `edge-states.md` 交付；按下表按屏走查。Wave 1 商店面以 FR-28 词表为准。

| 态 | 商店面 `/capabilities` | 技能广场 `/skills` | 治理台 | 采集任务 | 中转站 | 注册/定价 |
|----|------------------------|--------------------|--------|----------|--------|-----------|
| 加载 | 居中 Spin，无骨架 | 同 | Table `loading` | query isLoading | Table loading | 按钮 loading |
| 刷新保旧 | 无 | 无 | 整表 loading | query 保旧较好 | `showSpin=false` | — |
| 初始空 | 「暂无已发布 X」无 CTA | 「暂无已发布技能」 | 插件/专家有放入目录提示 | Dashboard 有三步；任务页未对齐 FR-70 文案 | 「暂无渠道」 | — |
| 筛选空 | 无筛选 | **与初始空同一句** | 技能筛选空不区分 | 不区分 | 渠道 ID 过滤不区分 | — |
| 错误 | **当空** | **当空** | toast | toast；无 trace_id | toast 硬编码串 | toast |
| 权限 | 无（公开） | 无 | 验证不藏按钮；技能只读 Alert | 按钮隐藏 | 整页 requireAdmin | — |
| 离线 | 无 | 无 | 无 | 无 | 无 | 无 |
| 边界 | 无分页；长标题 ellipsis 部分有 | Modal 正文 pre-wrap | 无虚拟滚动 | 结果分页 20 | 表横向 scroll | 定价硬编码色 |
| coming_soon / 不可装 | 无 | 无 | 无 | — | — | — |
| 429 / 限流 | 当空 | 当空 | 未按 code | 未按 QUOTA | 未按 code | 注册限流靠后端，前端无专案 |

权限纪律（spec §3.2）：发现性动作禁用+说明；危险/平台专属对租户 **隐藏**。插件「验证」对无权限用户仍可点。市场 listing 无 `btn:market:list` 必须隐藏，禁止道歉式 403。

---

## 8. 无障碍与九维（诊断视角）

**已做：** SiteLayout `nav aria-label`、图标 `aria-hidden`；SkillsSquare 卡片 `role="button" tabIndex={0}` + Enter/Space；Register/定价部分 Form.Item label；antd 自带焦点；技能广场 XSS 测试。

**缺口：**

- 无 skip link；AdminLayout / SiteLayout 均无。
- 官网 `Home.tsx` 在 SiteLayout `<main>` 里再包 `<main>`（landmark 重复）——本轮 grep 仍两处。
- Login 用 placeholder 代替 label（技能禁止）。
- 官网 Capabilities 卡片不可键盘、无 `aria-label`、无点击。
- 纯图标按钮多数无 `aria-label`；无 `aria-live`。
- 登录渐变 `#667eea → #764ba2`、定价硬编码色、Hero 浅字深底——对比度未测。
- `EnterpriseManagement` 公司切换仍是原生 `<select>`（文件内 antd `Select` 与原生并存）。
- Drawer 仍 `width=`（antd v6 倾向 `size`）。
- 色盲：状态只靠 Tag 颜色。

| # | 维 | 诊断 |
|---|----|------|
| 1 | Spacing | 大量内联 `padding: 64` / `marginBottom: 12` |
| 2 | Color | admin 经 `BRAND_TOKENS`；official `--site-*` 有，但 Capabilities `#f7f9fc`、SkillsSection 链 `#1677ff`、Pricing/Login/Features 硬编码。F-4 只拦 `#1890ff` |
| 3 | Font | 跟 antd |
| 4 | Radius/shadow | 内联 `borderRadius: 8/9`、Login `boxShadow` |
| 5 | Icons | 基本 `@ant-design/icons`；定价用 `✓` |
| 6 | Interaction | 提交按钮部分 loading；市场卡片无动作 |
| 7 | 六态 | §7；商店面/注册成功态不合格 |
| 8 | Responsive | SkillsSquare sider `breakpoint="lg"`；Capabilities `auto-fill`；AdminLayout **无折叠 Sider**（375 不可用）。NFR-07 不要求后台密铺 |
| 9 | a11y | 见上 |

测试缺口：无 Capabilities（双端）、无 Register 解包、无 NewApiOps、无 Pricing CTA、无 ProtectedRoute 租户 admin 越权。现有 16 条 Jest 只钉登录重定向、技能列表、成员 422、LLM 只读、权限缓存、技能广场 XSS。

---

## 9. 缺失页 / 组件矩阵（给塑形拆票；锚 FR）

| ID | 波 | 表面 | 缺失物 | 锚点 | FR |
|----|----|------|--------|------|-----|
| M1 | W0 | 官网 | 删 Hero 绝对规模；Features 去掉 Excel 或改口 CSV | `Home.tsx` · `FeaturesSection.tsx` | FR-02、FR-03 |
| M2 | W0 | 官网 | 定价空头标预告或删除；专业/企业 CTA 离开 `/register` | `Pricing.tsx` | FR-01、FR-05 |
| M3 | W0 | 官网 | 注册成功解包一次；主按钮去后台登录 | `Register.tsx` | FR-04 |
| M4 | W0 | 后台 | Login 增加「企业注册」链；placeholder→label | `Login.tsx` | FR-04.3 |
| M5 | W0 | 后台 | `ProtectedRoute` 区分 platform_admin；中转/LLM/运营写按钮收权 | `ProtectedRoute.tsx` · `LoginResponse` | FR-06、FR-07 |
| M6 | W0 | 后台 | 插件验证/扫描走 `usePermission`；无码则隐藏 | `Capabilities.tsx` PluginTab | FR-06 |
| M7 | W0 | 后台 | Usage 换 FR-12 词表；去掉 `QUOTA_EXCEEDED`；将满/满额 CTA | `Usage.tsx` | FR-12 |
| M8 | W0 | 双端 | 漏斗事件客户端（失败不挡主路径） | 无 | FR-15 |
| M9 | W0 | 后台 | 仪表盘/用量标明 Asia/Shanghai 与时间窗 | `Dashboard.tsx` · `Usage.tsx` | FR-16 |
| M10 | W1 | 官网 | `/skills` 重定向；导航合并「能力市场」 | `App.tsx` · `SiteLayout.tsx` | FR-17 |
| M11 | W1 | 官网 | 商店面：搜索/类型/分类/host、预告卡、分页、URL、错误≠空 | `pages/Capabilities.tsx` | FR-18、FR-19、FR-28 |
| M12 | W1 | 官网 | 详情 `/capabilities/:type/:nameOrSlug`；SKILL.md **纯文本**（迁测试） | 新页 | FR-19、QA-05 |
| M13 | W1 | 官网 | 订阅 + 未登录回跳 +「我的安装」 | 无；需会话方案 | FR-20、FR-21 |
| M14 | W1 | 官网 | `SkillsSection` 改链市场；退役或薄封装 SkillsSquare | `SkillsSection.tsx` | FR-17 |
| M15 | W1 | shared | `PublicAsset` 扩 listing/installable/license/source/origin_local_name | `shared/src/types/skills.ts` | FR-18 |
| M16 | W1 | 后台 | 菜单「能力市场」；六 Tab（源+目录+插件+技能+专家+团） | `menuConfig.tsx` · `Capabilities.tsx` | FR-22…25 |
| M17 | W1 | 后台 | 源 CRUD/同步/jobs | 新组件 | FR-25 |
| M18 | W1 | 后台 | listing / alias / override / `dev-team` 422「已合并，不可上架」 | 目录/Drawer | FR-22、FR-23 |
| M19 | W1 | 后台 | Skills 列 origin/source/listing；候选「市场入站」；第三方写回文案 | `Skills.tsx` · `SkillsCandidates.tsx` | FR-27 |
| M20 | W1 | 后台 | 专家团导出走 api client + token | `Capabilities.tsx` TeamTab | — |
| M21 | W1 | 双端 | 市场列表改 react-query；筛选项进 URL | 多文件 | FR-19、NFR-01 |
| M22 | W1 | 双端 | 市场埋点 | 无 | FR-30 |
| M23 | — | 后台 | enable-host **不要**在本期画 | — | FR-26 / PR8 |
| M24 | W2+ | — | 计费/发票/支付页 | 无 | Q-BILL；Non-Goal |
| M25 | W4 | 后台 | 无 Worker 提交拦截 | `Spiders.tsx` · `Nodes.tsx` | FR-71 |

---

## 10. 实现约束（给后续 frontend 帽，不在本期做）

- Tokens 用 `BRAND_TOKENS` / `--site-*`，禁止新硬编码 hex；F-4 补 `#1677ff` 黑名单是门禁债，不是本波产品。
- 列表/轮询一律 react-query；禁止 `setInterval`。
- 官网新代码只打 `/public/capabilities`；`/public/skills` 仅兼容层。
- 市场写按钮一律 `usePermission('btn:market:*' \| 'btn:plugin:verify')`，禁止 `isAdmin` / `requireAdmin` 硬编码（D14）。
- enable-host 按钮冻结到 PR8。
- `dev-team` listing 失败展示「已合并，不可上架」，不要当通用 422。
- SKILL.md / persona 继续纯文本，禁止 markdown 注入（迁 `data-testid="skill-md"`）。
- 改 shared 源码后必须重建 dist（见 pitfalls）。
- 词表：能力市场 / 未上架 / 已上架 / 预告 / 订阅 vs 安装到本机 两动词。
- Q-VOICE 关闭前 **不得新写并列四柱 Hero**；Wave 0 只删空头。

---

## 11. 九维 / 门禁自检（本诊断交付）

- [x] 未实现产品 UI、未改业务代码
- [x] 未定义 tokens、未写 API
- [x] 双应用路由/页面已对照设计与 **冻结 FR**
- [x] 状态归属与 public/admin API 已列
- [x] 六态与 a11y 已按屏走查（静态）
- [x] 采集 / SaaS / 中转站 / Power Market 均覆盖
- [x] `check-frontend.sh` exit 0（本轮）
- [x] admin Jest 13 passed；official Jest 3 passed（本轮）
- [ ] 未跑 `npm run build`（定义帽；verify 帽补）

---

## open_questions

1. **租户安装放哪？** 官网零鉴权。选项：(A) 官网加登录/JWT；(B) 订阅跳 `ADMIN_URL/capabilities?install=`；(C) 一期商店面只浏览，安装只在后台。D10/PR6 写官网按钮，与当前 official client 冲突。阻塞 FR-20/21。
2. **平台超管判定字段？** `LoginResponse` 无 `is_platform_admin`。市场/中转写 UI 用 `tenant_id==null && role==admin` 还是等登录载荷加字段？阻塞 FR-06/07。
3. **空缓存菜单全开是否保留？** `bea13b5` 为防侧边栏消失。与 FR-06 同时成立时，兜底必须 **排除** 平台写入口（中转/LLM/运营/用户/设置），不能全开。需和 backend 权限码种子对齐。
4. **Q-PRICE / Q-BILL** 未关：定价空头是撤文案还是改出口？前端 Wave 0 只能做「不得把未履约写成可买」——具体替代 CTA 等操作者。
5. **Q-VOICE** 未关：Hero 只允许删空头，不能擅自改成「四柱平台」或「能力市场」。
6. **Q-RELAY** 未关：中转站对租户 admin 是进页即拒，还是只读？Wave 0 只冻写权。
7. **SkillsSquare 退役：** 301 后是否保留薄封装？XSS 用例 `data-testid="skill-md"` 迁到详情页哪一票？（QA-05）
8. **coming_soon / 许可黑名单 / 预告卡** 视觉是否等 designer edge-states，还是 Tag 最小实现？
9. **采集筛选 URL 化** 是否挤进本 feature？建议 **不进 Wave 0/1**，避免与商店面 URL 状态抢票。
10. **公开失败是否保证 `request_id` 进信封？** 前端 FR-28 要展示 trace 才能报障；`apiErrorMessage` 今日不读 `request_id`。
11. **Register 双解包** 是否允许作为 Wave 0 FR-04 的第一刀（不改市场范围）？建议 **是**——否则激活漏斗基线仍是 0。
12. **埋点 SDK 选型** 不是本角色决定；前端只要求事件名与 spec FR-15/30 字段可从页面发出。失败不得挡注册/浏览。
