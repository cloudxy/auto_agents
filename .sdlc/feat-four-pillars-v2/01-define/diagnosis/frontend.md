# 前端诊断 · feat-four-pillars-v2（定义帽 / frontend）

| 字段 | 值 |
|------|----|
| 角色 | frontend（只读复审，不实现产品 UI、不定 tokens、不写 API） |
| 泳道 | L4 · `feat-four-pillars-v2`（supersedes `feat-four-pillars`；旧诊断/票/合同只作输入） |
| 对照 | Power Market 设计 **Accepted D1–D29**（含 2026-09-07b 五类平级）· 审查 **0 open** · 旧 spec v1.4 FR-01…36 · 旧 `01-define/diagnosis/frontend.md` |
| 范围 | `frontend/admin/src/` · `frontend/official/src/` · `frontend/shared/` |
| 拒绝 | 不定 tokens（→ designer）· 不写 API/schema（→ backend）· 不做放行判决（→ qc） |
| 本轮核实 | `bash scripts/check-frontend.sh` **exit 0**（F-2/3/4/5/6/7）。`frontend/official` Jest **2 suites / 3 passed**。`frontend/admin` Jest **全量 12 passed + 1 timeout**（`Members.test`「reset password」20s 悬崖；单测 18.5s 过）。未跑 `npm run build`（定义帽无前端实现） |

**一句话结论：** 双前端仍是 P6 采集工作台 + 四类目录雏形；对照已过审商店面/治理台合同，**五类、七 Tab、上架三态、订阅、预告、智能体词表全部零落地**。旧诊断的 Wave 0 诚实/收权裂缝全部仍在，且多了一条会红的门：admin Jest 在并行负载下已不再稳定全绿。全新方案若再抄旧 M16「六 Tab / 四类 / 专家」，会把已废句写进现行合同。

---

## 0. 相对旧 frontend 诊断：仍真 / 已废 / 本轮新发现

旧文件：`.sdlc/feat-four-pillars/01-define/diagnosis/frontend.md`。代码面与那份 **基本同构**（`listing_state` / `installable` / `btn:market:*` / `coming_soon` 前端 **零命中**）。不得整份复制为 v2 合同。

| 类别 | 条目 |
|------|------|
| **仍真（须吸收）** | 双广场；Hero `128,000+` / `12 节点` / `3.2 亿条` + 脚注≠删除；Features「CSV / Excel」；定价三档全进 `/register`；Register 双重 unwrap + 主按钮「再注册一家」；Login 无企业注册链、placeholder 当 label；`requireAdmin` 把租户 `role=admin` 当平台超管；插件扫描/验证无 `usePermission`；Usage 明文 `QUOTA_EXCEEDED`；商店/治理 `useEffect+fetch`；失败 catch→空；SkillsSquare XSS 纯文本是唯一必须迁走的浏览回归；官方 `QueryClientProvider` 挂了 0 处 `useQuery`；shared `main=dist` 与源码漂移 |
| **已废（禁止再写进新方案）** | 治理台目标「**最多 6 Tab** / 六 Tab（源+目录+插件+技能+专家+团）」——审查写明修订已废 6 上限，**顶栏 7 个：源+目录+五类**，砍「命令」Tab 即违 D26/FR-36。产品类型「专家 / `expert` / `expert_team`」对外已废，现行是 **智能体 `agent` / 专家团 `team` + 命令 `command`**。订插件带 bundled、unlist 连坐子卡、unlist 后不可用：D24/D25/D23 已否 |
| **本轮新发现** | ① admin 全量 Jest **不再稳定 13/13**：`Members.test.tsx` 重置密码用例并行下 20s timeout，单跑 18.5s 过（P-FE-07 悬崖）。② `AdminLayout` 优先 `/auth/menus` 动态树，**只改 `menuConfig.tsx` 叶名不够**。③ FR-07 直打中转必须与 **NotFound 同形**，今日壳是 `/unauthorized` 道歉 403——旧诊断写了 `requireAdmin` 过宽，未把「禁止道歉页」写成实现约束。④ Dashboard 零任务第 1 步链 `/llm`：T-04 允许租户自有供应商页，FR-07 只对 `/newapi` 404；新方案必须拆这两条，不能把 `/llm` 一并 404 否则引导空转 |

---

## 1. 现状地图（2026-09-08 读码）

### 1.1 官网 `frontend/official`（9113）

路由：[`App.tsx`](frontend/official/src/App.tsx)。壳：[`SiteLayout.tsx`](frontend/official/src/components/layout/SiteLayout.tsx)。**无登录态、无 ErrorBoundary、无 `useQuery` 消费方**（[`index.tsx`](frontend/official/src/index.tsx) 挂了 `QueryClientProvider`）。client 工厂注释正确：只传 `baseURL`，不注入 token。

| 路由 | 文件 | 现状 | 合同 |
|------|------|------|------|
| `/` | `Home.tsx` + `components/home/*` | Slogan「AI 驱动的智能数据采集系统」；`HERO_STATS` 原样；Features 卖 Excel；`SkillsSection` 标题「技能广场」、失败 `catch→[]`、硬跳 `/skills?q=` | FR-01/02/03/17；GWT-01.4；Q-VOICE：不得新写四柱 Hero |
| `/skills` | `SkillsSquare.tsx` | 搜索 + 分类 + 卡片键盘 + Modal；**`GET /public/skills`**；`?q=` 深链；`<pre data-testid="skill-md">` 纯文本（有 XSS 测试） | FR-17：应到达 `/capabilities?type=skill`；新 UI 不得再调 deprecated 接口；FR-32 测试必须先迁再删 |
| `/capabilities` | `pages/Capabilities.tsx` | **四 Tab**：技能 / 插件 / **专家 `expert`** / **专家团 `expert_team`**；无搜索/详情/分页/URL；卡片不可点；`catch→空列表`「暂无已发布X」 | D22/FR-17…19/28/33：五类筛选 + 智能体，不是第四个「专家」店 |
| `/register` | `Register.tsx` | `POST /public/tenant/signup`；成功 **再剥一层 `.data`**；主按钮 `href="/register"`「再注册一家」 | FR-04 **现网 bug** |
| `/pricing` | `Pricing.tsx` | 三档 `cta.href` 全 `'/register'`；企业档「中转站渠道组」「私有技能库」「工单支持」无预告标 | FR-01、FR-05；Q-PRICE 未关，只冻「不得写成可买」 |
| `*` | `NotFound.tsx` | 有 | 无详情 404 语义（alias 未命中、未上架同 404） |

导航 `NAV_LINKS` 仍并列「技能广场」「能力广场」。无 `/login`、无 `/capabilities/:type/:nameOrSlug`、无「我的安装」。Header「管理后台」外链 `REACT_APP_ADMIN_URL`。

公开类型常量仍钉四类：

```21:27:frontend/shared/src/constants/tiers.ts
/** 资产类型 → 中文标签（skill/plugin/expert/expert_team） */
export const ASSET_TYPE_LABELS: Record<string, string> = {
  skill: '技能',
  plugin: '插件',
  expert: '专家',
  expert_team: '专家团',
}
```

`PublicAsset` 仅 type/name/title/description/category/tier/score，**无** `listing_state` / `installable` / `license` / `source_name` / `health_status` / `origin_local_name` / `host_compat`。`schema.d.ts` 仍是 P6：`/public/capabilities` 列表、无详情、无 installs。

### 1.2 后台 `frontend/admin`（9112）

路由：[`App.tsx`](frontend/admin/src/App.tsx)（lazy + 路由级 `ErrorBoundary` + 404）。菜单五组：[`menuConfig.tsx`](frontend/admin/src/config/menuConfig.tsx)。守卫：[`ProtectedRoute.tsx`](frontend/admin/src/components/ProtectedRoute.tsx) 只认登录 + `role==='admin' \|\| is_admin`。

**租户菜单 vs 平台菜单（今日实际）：**

| 组 | 叶子 | 谁看得见 | 直打 URL |
|----|------|----------|----------|
| 概览 | 仪表盘 | 登录 | 登录即可 |
| 概览 | 用量看板 `tenantOnly` | 有 `tenant_id` 的登录者；纯超管（`tenant_id` NULL）菜单隐藏 | 路由未加 `requireAdmin`，超管深链仍进页 |
| 数据工厂 | 任务 / 日志 / 节点 / AI / 数据中心 | 登录 | 登录即可 |
| 能力资产 | **「资产目录」** `/capabilities` | 任意登录（`menu:skills`） | **无平台超管壳**；扫描/验证按钮对租户可见可点 |
| 运营管理 | 成员 `tenantOnly` | 租户绑定 | 页内角色 |
| 运营管理 | 平台运营台 / 日志中心 | `requireAdmin` → **租户公司管理员可进** | `/unauthorized`（道歉 403） |
| 系统管理 | LLM / **中转站管控** / 用户 / 设置 | 同上，租户 admin 可进 | 同上，**不是 NotFound** |
| 幽灵 | `/enterprise` `/rbac` | 无菜单；`requireAdmin` | 深链可进 |

`LoginResponse`（[`auth.ts`](frontend/admin/src/services/auth.ts)）有 `tenant_id` / `tenant_role` / `is_admin` / `role`，**无 `is_platform_admin`**。该字段只出现在用户列表 `UserItem`（[`users.ts`](frontend/admin/src/services/users.ts)）。

`AdminLayout`：Sider **无 collapsed / breakpoint**（NFR-07 不要求密铺）。菜单真相源是 `useQuery(['dynamic-menus'])` → `/auth/menus`；空/失败才回退 `menuConfig`。**叶名「能力市场」、中转叶对租户隐藏，若只改前端静态树、后端 menus 种子仍发旧 label/旧可见性，上线后用户看不到改动。**

**不存在：** `/capabilities/:type/:nameOrSlug`、源 Tab、目录 listing 开关、命令 Tab、智能体（仍叫专家）、租户「我的安装」、计费页、官网会话。

治理台今日四 Tab + 技能内再套三层：

```31:36:frontend/admin/src/pages/Capabilities.tsx
      <Tabs activeKey={tab} onChange={setTab} items={[
        { key: 'skills', label: '技能', children: <Skills /> },
        { key: 'plugins', label: '插件', children: <PluginTab /> },
        { key: 'experts', label: '专家', children: <ExpertTab /> },
        { key: 'teams', label: '专家团', children: <TeamTab /> },
      ]} />
```

`Skills` 内层再 `技能库 / 适配器矩阵 / 候选审核`（深度 3，每天一次任务超 2 层）。Tab 全在 `useState`，不在 URL。`listAssets('expert'|'expert_team')`、`scanExperts`、组建专家团文案、空态「放入 AGENT.md」——后端 expand-contract 写路径拒绝旧枚举后，**这些调用会 400，前端无测试。**

插件空态仍教用户往 `capability-library/plugins/` 放包（与 D1 指针根冲突）。文案「插件经 MCP 验证后方可分发」把验证=上架绑在一起（FR-26 已拆；无 MCP → unknown 允许 listed）。

专家团导出：`window.open('/api/v1/capabilities/teams/{name}/export')` **不带 Bearer、不走 `REACT_APP_API_BASE_URL`**。

---

## 2. Wave 0 冻结 FR · 前端对照

只列界面能单独证伪的项。

| FR | 用户可见要求 | 今日前端 | 判 |
|----|----------------|----------|----|
| **FR-01** | 现在就能用的承诺可走完；工单/渠道组/私有库不得当可买 | 定价无预告标；企业档三条空头；Features 写 Excel | **不满足** |
| **FR-02** | 不出现 128,000+ / 12 节点 / 3.2 亿条 | `HERO_STATS` 原样 + 12px「示意数据」 | **不满足**（脚注 ≠ 不出现） |
| **FR-03** | 选项只列会生成的格式；写明单次最多 100 条 | 数据中心 CSV +「前 100 条」相对诚实；官网仍「CSV / Excel 一键导出」 | 后台部分满足；**官网不满足** |
| **FR-04** | 成功主按钮「登录管理后台」；登录页回官网注册 | 双重 unwrap →「企业「」注册成功」；主按钮再注册；Login 无回链 | **不满足（P0 现网）** |
| **FR-05** | 专业/企业主按钮不得进同一注册表 | 三档 `navigate('/register')`，只是 label 不同 | **不满足** |
| **FR-06** | 扫描/验证/上架对租户拒绝；按钮隐藏或禁用+说明 | 验证/扫描无 `usePermission('btn:plugin:verify'\|'btn:market:*')`。`/capabilities` 任何登录者可进 | **不满足** |
| **FR-07** | 写权仅超管；渠道页导航隐藏；直打 **同 404**（不是道歉 403） | `/newapi` `/llm` `/platform-ops` 包在 `requireAdmin`；租户 admin 过壳；直打 → `Unauthorized` 403 文案 | **不满足**（壳过宽 + 错态页） |
| **FR-08** | 空态「还没有采集任务」+ 新增 | 任务列表有 Empty；隔离靠后端 | 空态可接受 |
| **FR-11** | 数据中心看不到市场候选 | 打 `/spiders/results`；候选在 Skills 内层 | **表面满足** |
| **FR-12** | 70% 警告；满额下一步；禁 `QUOTA_EXCEEDED` | Progress 70/90 变色；**无将满文案、无 CTA**；页顶 Alert 明文内部码 | **不满足** |
| **FR-13** | 详情无 `file_path` | 技能 Drawer 未见该列 | **目前未展示**；Wave 1 不得把 `origin_ref` 当路径渲染 |
| **FR-15** | 漏斗事件 | 双前端零 `gtag` / `trackEvent` / beacon | **不满足** |
| **FR-16** | 页上写 Asia/Shanghai；近 7 日 ≠ 本月 | Dashboard「近 7 日」绑 `total_results`；用量「本月」无时区；`toLocaleString('zh-CN')` 无 timeZone | **不满足** |

Wave 0 前端最小切片（给塑形，不在本期做）：删 Hero 大数与 Excel 卖点；定价空头标预告或删除（出口形态等 Q-PRICE）；Register 解包一次 + 去登录；Login 回链注册（**保留 placeholder 或同步改 `App.test.tsx`**）；`ProtectedRoute` 改平台超管字段；`/newapi` 非超管渲染 **NotFound 而非 Unauthorized**；插件验证/扫描按权限码隐藏；Usage 换 FR-12 词表；Dashboard 第 1 步不得把租户送进平台渠道页；埋点 SDK 位失败不挡主路径。**不要在 Wave 0 画商店面。**

---

## 3. Wave 1 · 已过审 Power Market UI 合同 vs P6

设计 Goals 4–5 + Amendment D/E + FR-17…36。实现停在 P6。对用户说「能力市场」，禁用「技能广场 / 能力广场 / 资产目录」。

### 3.1 官网商店面（设计 E 替换四 Tab）

| 合同 | 今日 | 缺口 |
|------|------|------|
| 导航只留「能力市场」`/capabilities`（D19 / FR-17） | 「技能广场」+「能力广场」 | M10 |
| `/skills` → 市场且筛技能 | 独立页，deprecated `/public/skills` | 301/路由重定向；首页 `SkillsSection` 仍链 `/skills` |
| 筛选：五类或全部 + 搜索 name/title/**origin_local_name** + 分类 + 宿主；筛选项进 URL（FR-19） | 无搜索；Tab 不写 URL；无 host | 短名命中否则搜 `code-review` 找不到 `mattpocock-skills__code-review` |
| 卡片中文标签：技能 / 插件 / 命令 / **智能体** / 专家团（FR-33） | 专家 / `expert` | 旧 `expert` URL 不得再开第三套店（GWT-33.3：映射到智能体或 404） |
| listed →「订阅」；coming_soon →「预告」无按钮；unlisted 不出现、详情 404（D17/D23） | 无 `listing_state`；卡片死的 | 预告卡 / 不可装 |
| 详情 `/capabilities/:type/:nameOrSlug`；出处链父插件 **仅当父 listed**，否则纯文本署名 | 无详情路由 | 避免 L1 把 unlisted 父插件带出商店 |
| 登录订阅 +「我的安装」按五类分组；卸一行不影响其它行（FR-20/21/34） | 零鉴权；无 installs client | **会话方案未决**（见 open_questions） |
| 失败不得装空（FR-28 词表） | catch →「暂无已发布」 | 与筛选空、目录空三词必须拆开 |
| SKILL.md 纯文本（FR-32） | 只在 SkillsSquare | 迁 `data-testid="skill-md"`，禁止 markdown |
| 第一方已发布闸门打开后可见（FR-31） | 公开列表只吃后端今日闸 | 前端不要再客户端滤 `stable` 把 recommended 藏掉 |
| 市场埋点 FR-30 | 无 | 失败不挡浏览 |

### 3.2 管理端治理台（设计 D：七 Tab）

入口 `/capabilities`，菜单叶 **「能力市场」**（权限码 `menu:skills` 可留）。顶栏：

| Tab | 合同内容 | 今日 |
|-----|----------|------|
| 源 | 登记 / 同步 / jobs / `last_sync_at` / `last_hash` | 无 UI、无 service |
| 目录 | **五类**筛选 + listing 开关 + alias + 许可 override；「出处插件」只展示不是批量上架 | 无独立目录 Tab；`AssetRow` 无 listing/license/source |
| 插件 | 版本、license、health、**子资产计数链到目录过滤**、验证；上架只改插件行 | 扫描 + 验证；无权限码；无合集计数 |
| 技能 | 现 Skills + origin/source/listing；矩阵/候选仍在内；候选文案「市场入站」 | 内嵌 Skills；候选仍 harvester 口径；无 listing 列；状态筛 **无 blacklist** |
| **命令** | slash 名、出处插件、listing | **整 Tab 不存在** |
| 智能体 | 原专家 Tab **改名**；listing；只读 uses_skill | 仍「专家」；`listAssets('expert')` |
| 专家团 | listing；成员为智能体名 | 组建/导出；导出丢 token |

插件 Drawer：每行「在目录中打开」「单独上架」；**没有**「上架全部子资产」。`dev-team` 插件行 listing 控件「已合并，不可上架」（422 专用句）；**子行不继承这句**（D20+D25）。enable-host **PR8 再画**（D21 / FR-26）。

`services/capabilities.ts` 仅：`GET /capabilities`、`POST scan-plugins`、`POST plugins/{name}/verify`、`POST scan-experts`、`POST teams`。无 sources / listing / aliases / license-override / components / installs。

---

## 4. 代码级裂缝（实现帽会踩的）

### 4.1 P0 现网：注册双重 unwrap（P-FE-04）

```24:30:frontend/official/src/pages/Register.tsx
      const result = await tenantSignup(values)
        .then((r) => (r as unknown as { data: SignupResult }).data)
```

`tenantSignup` 已 `unwrap<SignupResult>`。拦截器返回信封，service 再剥 `data`。页面再取 `.data` → `done.tenant.name` / `done.owner.username` 为 `undefined`。用户看到「企业「」注册成功」。Members/skills 同类 bug 已修（`e497004`），官网漏网。**无 Register 测试。**

### 4.2 权限壳三层不一致（FR-06/07 交火）

1. **路由：** `requireAdmin` = `role==='admin' \|\| is_admin` → 租户公司管理员 = 平台超管。
2. **菜单：** `usePermission` 空缓存（F5 后 / 后端不可达）展示 **全量菜单**（`bea13b5`），只递归滤 `tenantOnly`（用量/成员）。**中转/LLM/运营/用户/设置在兜底里全开。** 注释写「菜单是 UI 优化，安全在 API」——叠上过宽路由守卫后就不是优化。
3. **动态菜单：** `/auth/menus` 覆盖静态树。前端藏叶、后端仍下发 = 用户仍看见。
4. **按钮：** 技能矫正走 `btn:skill:edit` / `btn:skill:admin`（对）；插件验证/扫描/专家扫描/组建团 **不走权限码**。
5. **越权页：** `Navigate to="/unauthorized"` 渲染 403「抱歉，您没有权限」= 道歉式 403。GWT-07.3 / 旧 T-04：渠道直打必须与 **页面不存在** 相同（无渠道数据）。Wave 0 改守卫时若只换 `is_platform_admin` 仍跳 Unauthorized，**FR-07 仍然失败**。

`useAuthStore` persist 在 rememberMe 关页后 token 仍在 localStorage（技能 gotcha）。市场写面收权后更危险，logout 已 `clearCachedPermissions`。

### 4.3 数据层

react-query 实际覆盖（admin）：`AdminLayout` 动态菜单、`Spiders` 任务列表、`LogDrawer`、`SpiderLogs` 日志、`Nodes`、`useAiPlanFlow` 两处轮询。

**未覆盖：** Dashboard、Data、Capabilities 全家、Skills / Matrix / Candidates、Members、Usage、PlatformOps、Enterprise、Rbac、Users、Settings、LogCenter、LlmProviders、NewApiOps、ResultDrawer、File/Schedule/Alert/Template、**official 全站**。

`useAiPlanFlow`：`useQuery` 拉到 `freshPlan` 后 `setPlan(freshPlan)`，真相回到手写 state。

失败当空：官网 Capabilities / SkillsSquare / SkillsSection。断网、5xx、限流与「暂无已发布」不可分（FR-28 / GWT-01.4）。

分页截断：admin `page_size: 50` + `pagination={false}`；official 同 50；SkillsSquare `PAGE_SIZE=60` 无翻页。

URL 未承载：官网市场 type/q/category/host/page；后台 capabilities 顶 Tab；技能筛选；中转 Tab + channel_id。采集筛选 URL 化 **不要挤进 Wave 0/1**。

### 4.4 Public vs Admin API

| 调用方 | 端点 | 对错 |
|--------|------|------|
| official Capabilities | `GET /public/capabilities` | 对（D19 公开前缀）；**type=expert 错** |
| official SkillsSquare / SkillsSection / Home | `GET /public/skills` | **错**（新 UI 不得调用） |
| official Register | `POST /public/tenant/signup` | 对 |
| official 其它 | 无鉴权 client，无 `/tenants/me/*` | 安装 API 接不上 |
| admin Capabilities | `GET /capabilities` | 对（治理列表） |
| admin 插件验证/扫描 | `POST …/scan-plugins` · `…/verify` | 端点对，前端无权限码 |
| admin 专家团导出 | 浏览器直开 `/api/v1/.../export` | **错**：丢 token、丢 baseURL |
| admin 用量/成员 | `/tenants/me/usage` · `/members` | 对 |
| admin 中转 | `/newapi/*` | 对；壳过宽 |
| admin 仪表盘 | `/admin/stats` | 未标「本企业 / 平台合计」 |

D10 把订阅放官网就必须给 official **有限鉴权**（或跳后台带 `returnUrl`）。把租户安装打到公开 client 会直接失败或把 JWT 漏进无 token 工厂。

### 4.5 共享包与门禁债

- **P-FE-01：** `frontend/shared` `"main": "dist/index.js"`。本轮：`src/index.ts` 已不导出 `queryViewState`，**`dist/index.js` 仍 `export { queryViewState } from './query/state'`**。改 shared 源码后必须 `npm run build -w @auto-agents/frontend-shared`。
- **F-4** 只禁 `#1890ff`；`#1677ff` / Login `#667eea→#764ba2` / 定价硬编码色漏网。新代码用 `BRAND_TOKENS` / `--site-*`，不要等门禁。
- **F-2** 只扫 `instanceof` / `String(e)` 写法；字面量 `message.error('固定中文')` 放行，用户看不到后端 `message`。
- **F-7** `.tsx ≤ 400` 行已启用。今日最大：`RbacManagement` 374、`NewApiOps` 358、`Data` 326、`Capabilities` 199、`Skills` 251。把七 Tab 塞进单文件 **会红 F-7**。必须按 Tab 拆文件。
- **F-3** 无手写 `setInterval`（本轮门禁过）。新轮询必须 `refetchInterval`。
- `apiErrorMessage` **不读 `request_id`**。FR-28 失败态要展示 trace 才能报障。
- antd v6：`Alert message` 仍多处（Usage / Dashboard / Skills 只读提示）；测试 stderr 已打 deprecation（P-FE-08）。新代码用 `title` / `description` / Drawer `size`。

### 4.6 采集 / 中转（本程序不要挤进商店票）

采集相对成熟：任务列表 react-query 3s 终态停；数据中心导出 100 条有文案。Dashboard 零任务引导是最好的空态，但第 1 步链 `/llm`。

中转：[`NewApiOps.tsx`](frontend/admin/src/pages/NewApiOps.tsx) 文件头仍写「全只读无写操作」——**注释腐坏**（已有配置 Modal）。全 `useState+useEffect`；Tab 不在 URL。`requireAdmin` 让租户 admin 可能改窗口额度。

---

## 5. 会红的测试（新方案必须先改测试再改行为）

宪法 `test` 闸 **不含** Jest；CI `frontend-build` job 会跑。E2E=`null`。现网 **7 文件 / 16 条 `test()`**，对准 P6 登录壳/技能列表/成员 422/LLM 只读/权限缓存/技能广场 XSS，**不是** FR/GWT。

### 5.1 本轮指纹（会红的已经在红）

| 套件 | 结果 | 含义 |
|------|------|------|
| `check-frontend.sh` | exit 0 | 改色值 `#1890ff`、手写 `setInterval`、单文件 >400、应用互引、信封双定义 → 门禁红 |
| official Jest | **3 passed**（~12.5s） | SkillsSquare 点击有 `act()` 警告，仍绿 |
| admin 全量 Jest | **12 passed + 1 failed**（~83s） | `Members.test.tsx`「reset password failure」**Exceeded timeout of 20000 ms** |
| 同用例单跑 | **passed 18568 ms** | 卡在 20s 悬崖（P-FE-07：antd Modal + jsdom 并行）。新方案再加 Modal 交互而不提 timeout / 抽慢路径，全量套件会更红 |

旧诊断「admin 13 passed」**本轮不能当闸门事实**。Members 422 占用两条仍是必须保住的回归（P-FE-05）；重置密码这条是 flake 悬崖，不是产品 FR。

### 5.2 一改产品行为就会红的现网用例

| 用例 | 锚 | 何种改动会红 | 正确做法 |
|------|----|----------------|----------|
| `admin/src/App.test.tsx` `findByPlaceholderText('用户名'/'密码')` | 未登录 → `/login` | FR-04.3 / a11y 把 placeholder 改成 label 并删 placeholder | **同票改测试**；或 label+保留 placeholder。禁止只改 Login |
| `usePermission.test.tsx`「补拉失败：菜单全量兜底」断言 **系统管理** | `bea13b5` | FR-06/07 空缓存兜底排除中转/LLM/运营/用户/设置 | **先改测试 oracle**：空缓存 ≠ 全开写面；仍要有仪表盘/数据工厂，不得全滤光（侧边栏消失链） |
| 同上 `ADMIN_PERMS` 含 `menu:skills` 不含市场码 | 权限种子 | 若改权限码名而不改测试数组 | 叶名可改「能力市场」，**码可留 `menu:skills`**（designer 已允许） |
| `SkillsSquare.test.tsx` mock `listPublicSkills` + `data-testid="skill-md"` | FR-32 / QA-05 / P-FE-06 | 删 `/skills` 页或改 mock 到 capabilities 而不迁 XSS | **先把 XSS 用例迁到市场详情，再删广场**。MemoryRouter 直挂组件，只做 301 不会红这条——删文件会红 |
| `Skills.test.tsx`「当前角色只读」/ 双评分列 | 技能 Tab | 拆走 Skills 或改只读 Alert 文案 | 保持导出或改测试；矫正列仍按 `btn:skill:edit` 隐藏 |
| `LlmProviders.test.tsx`「仅管理员可管理供应商」+ 无「新建供应商」 | 默认 viewer 只读 | 拆租户自有供应商 vs 平台行后文案/按钮变化 | 测例不走路由。改页复制同票改测试。**不要**为了 FR-07 把 `/llm` 整页 404 而本测仍 mount 旧壳 |
| official `App.test.tsx` 根路由至少 1 个 `h2` | smoke | 仅当 Home 删光所有 h2（Features `SectionTitle` 仍在则过） | Wave 0 删 Hero 数字通常不红；不要误删 Features 标题当「诚实」 |

### 5.3 今日零覆盖、合并后若无新测会「假绿」的行为

无 Capabilities（双端）、无 Register 解包、无 Pricing CTA、无 ProtectedRoute 租户 admin 越权、无 NewApiOps、无「专家」标签、无 `listing_state`、无订阅/我的安装、无 `/newapi` 直打 404。

后端 expand-contract 拒绝 `expert` 写路径后，admin `listAssets('expert')` / official Tab `expert` **运行时红、Jest 仍绿**。新方案必须把类型枚举测试加在前端（五类中文、旧 `expert` URL 映射），不能只靠 pytest。

`SkillsSquare` 列表测 mock 的是 `/public/skills`。市场页改 `listPublicAssets` 后这条 **必须改 mock**，否则会红或测错层。

---

## 6. 六态（商店/治理按合同词表；设计 edge-states.md 尚未作为独立交付）

FR-28 词表（实现不得发明同义句）：

| 态 | 合同句 | 今日商店 `/capabilities` | 今日 `/skills` |
|----|--------|--------------------------|----------------|
| 加载 | 骨架（合同）/ 今日居中 Spin | Spin，无骨架 | 同 |
| 目录空 | 「还没有上架的能力」+「通过审核的技能和插件会出现在这里」 | 「暂无已发布X」无 CTA | 「暂无已发布技能」 |
| 筛选空 | 「没有符合条件的能力」+「清除筛选」 | 无筛选 | **与目录空同一句** |
| 失败 | 「市场列表加载失败」+「检查网络后重试」 | **当空** | **当空** |
| 预告 | 可见、无订阅按钮、旁注尚未上架 | 无 | 无 |
| 未登录点订阅 | 先登录，回来尚未订；不是道歉 403 | 无按钮 | 无 |
| 离线 | 无 | 无 | 无 |
| coming_soon / 不可装 | 无 | 无 | 无 |

权限纪律（spec §3.2）：发现性动作禁用+说明；危险/平台专属对租户 **隐藏**。插件「验证」对无权限用户仍可点。listing 无 `btn:market:list` 必须隐藏，禁止道歉式 403。

治理台：Table `loading`；插件/专家空态是工程师路径提示；验证不藏按钮；无离线。采集任务 react-query 保旧较好。中转有管理面不可达降级 Alert（超管向）。

---

## 7. 全新方案必须吸收的前端约束

塑形/实现票不得违反。不是开放问题。

1. **IA 目标是七 Tab 不是六 Tab。** 源 + 目录 + 技能 + 插件 + 命令 + 智能体 + 专家团。审查：不要为旧「最多 6」砍命令。
2. **对外五类枚举** `skill \| plugin \| command \| agent \| team`。UI 禁用「专家」作类型名。旧 `expert` / `expert_team` 一个发布周期映射到智能体/团或 404，禁止第三套平行店。
3. **T-31：不改后台五组分组，不修幽灵 `/enterprise` `/rbac`。** 允许：叶名「资产目录」→「能力市场」；中转/平台运营叶对租户隐藏；加「我的安装」叶（FR-21，租户）。禁止：中转升组、重排五组。
4. **GWT-07.3：租户直打 `/newapi` = NotFound 同形**（无渠道数据），不是 `Unauthorized`。`/llm` 按 T-04：**不要**整页 404；藏平台行写控件，可留租户自有供应商。Dashboard 引导必须跟这条拆分对齐。
5. **空缓存菜单兜底必须排除平台写入口**（中转/LLM/运营/用户/设置），同时不得再全滤光（F5 侧边栏消失）。会红现网「全量兜底」测试，同票改 oracle。
6. **写按钮一律 `usePermission('btn:market:*' \| 'btn:plugin:verify')`**，禁止 `isAdmin` / `requireAdmin` 硬编码（D14）。登录载荷需要平台超管字段（或明确 `tenant_id==null && role==admin` 的产品定义——见 open_questions）。
7. **官网新代码只打 `/public/capabilities`。** `/public/skills` 仅兼容层。首页精选失败走 GWT-01.4 词表，禁止 `catch→[]`。
8. **SKILL.md / persona 继续文本节点**（`pre` + `data-testid="skill-md"`）。退役广场前 XSS 用例必须已在详情页绿。禁止 markdown/HTML。
9. **信封只 unwrap 一次**（P-FE-04）。抄 Register 会再破。
10. **列表/轮询 react-query**；禁止 `setInterval`；市场筛选项进 URL（`replace: true` 防抖）。
11. **订/卸只作用于这一行**（FR-34）。文案禁止「安装此插件将获得全部技能」。Drawer 禁止「上架全部子资产」。
12. **出处链接仅当父插件 listed**；否则纯文本署名。
13. **`dev-team` listing 失败展示「已合并，不可上架」**，不要当通用 422。子行不继承。
14. **enable-host 按钮冻结到 PR8。** Wave 1 只折叠「订阅 ≠ 已在宿主运行」说明（D21）。
15. **改 `frontend/shared/src` 后必须重建 dist。** `PublicAsset` / `ASSET_TYPE_LABELS` 扩五类与 listing 字段是商店面前置。
16. **F-7：治理台按 Tab 拆文件**，禁止把七 Tab 堆进 `Capabilities.tsx`。
17. **Tokens：** `BRAND_TOKENS` / `--site-*`，禁止新硬编码 hex。
18. **Q-VOICE 关闭前不得新写并列四柱 Hero。** Wave 0 只删空头。
19. **Q-PRICE / Q-BILL 关闭前：** 专业/企业主按钮不得进 `/register`；不得发明支付页。替代出口等操作者。
20. **动态菜单与静态树双源：** 叶可见性/文案必须同时改 `/auth/menus` 种子（backend 票）或文档化「menus 空才回退」。只改 `menuConfig.tsx` 会在有动态菜单的环境里看不见。
21. **`pageTitleFor` 只认精确叶子 path。** 新详情路由 `/capabilities/:type/:slug` 会显示「后台管理」，同票扩展匹配。
22. **Jest：** 保持 `transformIgnorePatterns` 含 `@ant-design|antd|rc-|@rc-component|@auto-agents`；setupTests MessageChannel stub（不要 worker_threads）。新 Modal 测试按 20s 悬崖加宽或串行。
23. **埋点失败不得挡注册/浏览。** 事件名跟 FR-15/30；SDK 选型不是本角色决定。
24. **采集筛选 URL 化、xlsx、计费页、专家团执行、代写宿主配置：不进本程序前端范围。**

---

## 8. 缺失页 / 组件矩阵（给塑形拆票；锚 FR）

| ID | 波 | 表面 | 缺失物 | 锚点 | FR |
|----|----|------|--------|------|-----|
| M1 | W0 | 官网 | 删 Hero 绝对规模；Features 去掉 Excel 或改口 CSV | `Home.tsx` · `FeaturesSection.tsx` | FR-02、FR-03 |
| M2 | W0 | 官网 | 定价空头标预告或删除；专业/企业 CTA 离开 `/register` | `Pricing.tsx` | FR-01、FR-05 |
| M3 | W0 | 官网 | 注册成功解包一次；主按钮去后台登录；Jest 锁 CTA | `Register.tsx` | FR-04 |
| M4 | W0 | 后台 | Login「企业注册」链；placeholder 策略与 `App.test` 同票 | `Login.tsx` | FR-04.3 |
| M5 | W0 | 后台 | `ProtectedRoute` 区分 platform_admin；`/newapi` 非超管 → NotFound；`/llm` 藏平台写、不整页 404 | `ProtectedRoute.tsx` · `App.tsx` · `LoginResponse` | FR-06、FR-07 |
| M6 | W0 | 后台 | 插件验证/扫描/专家扫描/组建团：无码则隐藏 | `Capabilities.tsx` | FR-06 |
| M6b | W0 | 后台 | 空缓存兜底排除平台写叶；改 `usePermission.test` oracle | `usePermission.ts` | FR-06/07 · P-FE-03 |
| M7 | W0 | 后台 | Usage 换 FR-12 词表；去掉 `QUOTA_EXCEEDED`；将满/满额 CTA | `Usage.tsx` | FR-12 |
| M8 | W0 | 双端 | 漏斗事件客户端（失败不挡） | 无 | FR-15 |
| M9 | W0 | 后台 | 仪表盘/用量标明 Asia/Shanghai 与时间窗；零任务引导不链平台渠道 | `Dashboard.tsx` · `Usage.tsx` | FR-16、FR-07 |
| M10 | W1 | 官网 | `/skills` 重定向；导航合并「能力市场」 | `App.tsx` · `SiteLayout.tsx` | FR-17 |
| M11 | W1 | 官网 | 商店面：五类筛选/搜索/host、预告卡、分页、URL、错误≠空 | `pages/Capabilities.tsx` | FR-18、FR-19、FR-28、FR-33 |
| M12 | W1 | 官网 | 详情 `/:type/:nameOrSlug`；SKILL.md 纯文本（**先迁 XSS 测试**） | 新页 | FR-19、FR-32、QA-05 |
| M13 | W1 | 官网/后台 | 订阅 + 未登录回跳 +「我的安装」五类分组；卸一行不连坐 | 无；需会话方案 | FR-20、FR-21、FR-34、FR-35 |
| M14 | W1 | 官网 | `SkillsSection` 改链市场；失败态 GWT-01.4 | `SkillsSection.tsx` | FR-17、GWT-01.4 |
| M15 | W1 | shared | `PublicAsset` + `ASSET_TYPE_LABELS` 扩五类与 listing/installable/license/origin_local_name/host_compat；重建 dist | `shared/src/types/skills.ts` · `constants/tiers.ts` | FR-18、FR-33 |
| M16 | W1 | 后台 | 菜单叶「能力市场」；**七 Tab**（含命令、智能体改名）；按文件拆分（F-7） | `menuConfig.tsx` · `Capabilities.tsx` + 新 Tab 文件 | FR-22…25、FR-33、FR-36 |
| M17 | W1 | 后台 | 源 CRUD/同步/jobs | 新组件 | FR-25 |
| M18 | W1 | 后台 | listing / alias / override / `dev-team` 专用 422 | 目录/Drawer | FR-22、FR-23 |
| M19 | W1 | 后台 | Skills 列 origin/source/listing；候选「市场入站」；第三方 `written_back: false` | `Skills.tsx` · `SkillsCandidates.tsx` | FR-27 |
| M20 | W1 | 后台 | 专家团导出走 api client + token | TeamTab | — |
| M21 | W1 | 双端 | 市场列表 react-query；筛选项进 URL | 多文件 | FR-19、NFR-01 |
| M22 | W1 | 双端 | 市场埋点 | 无 | FR-30 |
| M23 | — | 后台 | enable-host **不要**在本期画 | — | FR-26 / PR8 |
| M24 | W2+ | — | 计费/发票/支付页 | 无 | Q-BILL；Non-Goal |
| M25 | W4 | 后台 | 无 Worker 提交拦截 | `Spiders.tsx` · `Nodes.tsx` | FR-71 |
| M26 | W0 | 测试 | Members 重置密码 20s 悬崖：加宽 timeout 或抽慢路径，避免全量套件假红 | `Members.test.tsx` | P-FE-07（门禁债，非产品 FR） |

---

## 9. 九维 / 门禁自检（本诊断交付）

| # | 维 | 诊断 |
|---|----|------|
| 1 | Spacing | 大量内联 `padding: 64` / `marginBottom: 12` |
| 2 | Color | admin 经 `BRAND_TOKENS`；official `--site-*` 有，但 Capabilities `#f7f9fc`、SkillsSection `#1677ff`、Pricing/Login/Features 硬编码。F-4 只拦 `#1890ff` |
| 3 | Font | 跟 antd |
| 4 | Radius/shadow | 内联 `borderRadius: 8/9`、Login `boxShadow` |
| 5 | Icons | 基本 `@ant-design/icons`；定价用 `✓` |
| 6 | Interaction | 提交按钮部分 loading；市场卡片无动作、无键盘 |
| 7 | 六态 | §6；商店面/注册成功态不合格 |
| 8 | Responsive | SkillsSquare sider `breakpoint="lg"`；AdminLayout 无折叠 Sider。NFR-07 不要求后台密铺 |
| 9 | a11y | 官网 `Home` 在 SiteLayout `<main>` 里再包 `<main>`；Login placeholder 当 label；无 skip link；无 `aria-live` |

- [x] 未实现产品 UI、未改业务代码
- [x] 未定义 tokens、未写 API
- [x] 双应用路由/权限壳/租户菜单 vs 平台菜单已对照 **D22–D29 + FR-01…36**
- [x] 旧诊断已废句（六 Tab / 四类 / 专家）已标出，禁止抄进新方案
- [x] 会红的测试已按文件列出
- [x] `check-frontend.sh` exit 0（本轮）
- [x] official Jest 3 passed；admin 全量 12+1 timeout（本轮，见 §5.1）
- [ ] 未跑 `npm run build`（定义帽；verify 帽补）

---

## open_questions

1. **租户安装放哪？** 官网零鉴权。选项：(A) 官网加登录/JWT；(B) 订阅跳 `ADMIN_URL/capabilities?install=`；(C) 一期商店面只浏览，安装只在后台。D10/设计 E 写官网按钮，与当前 official client 冲突。阻塞 FR-20/21。Q-MARKET-USER 未关会改变 CTA 主次，但不重开 D10。
2. **平台超管判定字段？** `LoginResponse` 无 `is_platform_admin`。市场/中转写 UI 用 `tenant_id==null && role==admin` 还是等登录载荷加字段？阻塞 FR-06/07。必须与 backend 登录合同同票。
3. **空缓存菜单全开是否保留「读叶」？** 兜底必须排除平台 **写** 入口。读叶（仪表盘/采集）是否仍全开，需和 backend 权限码种子对齐。改动会红 `usePermission.test`「系统管理」断言。
4. **`/llm` 对租户的产品形态？** 旧 T-04：保留自有供应商、藏平台行。FR-07 404 只点名渠道/中转。Dashboard 今日把新租户送去 `/llm`。新方案不得把两条合成「所有 requireAdmin 页都 404」。
5. **动态菜单 vs `menuConfig` 谁赢？** 有 `/auth/menus` 数据时静态叶名/隐藏无效。menus 种子是否本程序 backend 票？前端单独改 IA 会在联调环境「没改」。
6. **Q-PRICE / Q-BILL** 未关：定价空头是撤文案还是改出口？前端 Wave 0 只能做「不得把未履约写成可买」。
7. **Q-VOICE** 未关：Hero 只允许删空头，不能擅自改成「四柱平台」或「能力市场」。
8. **Q-RELAY** 未关：中转站对租户 **读** 已冻为隐藏+404；不要新造租户只读渠道屏。
9. **SkillsSquare 退役形态：** 301 后是否保留薄封装？XSS 用例迁到详情页哪一票？（必须先绿后删）
10. **coming_soon / 许可黑名单 / 预告卡** 视觉是否等 designer edge-states，还是 Tag 最小实现？
11. **公开失败是否保证 `request_id` 进信封？** 前端 FR-28 要展示 trace；今日 `apiErrorMessage` 不读该字段。
12. **Register 双解包** 是否允许作为 Wave 0 FR-04 的第一刀（不改市场范围）？建议 **是**——否则激活漏斗基线仍是 0。
13. **埋点 SDK 选型** 不是本角色决定；只要求事件名可从页面发出，失败不挡主路径。
14. **admin Jest 20s 悬崖** 是否单独开测试债票（M26），还是挂在第一条触碰 Members 的票里？不修则 CI `frontend-build` 会间歇红，与产品 FR 无关却挡验证帽。
