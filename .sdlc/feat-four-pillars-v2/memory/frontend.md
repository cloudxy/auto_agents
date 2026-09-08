# frontend memory · feat-four-pillars-v2

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**).
> Cap **2200 characters**. Frozen snapshot: next spawn sees this; do not treat it as live mid-turn.

## Last

- Date: 2026-09-08
- Hat: sdlc-workflow:frontend（定义帽只读诊断，未改 UI）
- Outputs: `.sdlc/feat-four-pillars-v2/01-define/diagnosis/frontend.md`

## Facts

- 代码仍停在 P6：官网双广场（`/skills` + `/capabilities` 四 Tab `expert`/`expert_team`）；后台 `Capabilities` 四 Tab、菜单叶「资产目录」；`listing_state` / `btn:market:*` / `coming_soon` 前端 0 命中。`is_platform_admin` 只在 Users 列表。
- `Register.tsx` 在 `tenantSignup` 已 unwrap 后再剥 `.data`（P-FE-04）。`ProtectedRoute.requireAdmin` = `role==='admin' || is_admin`。空缓存菜单兜底露出系统管理（bea13b5）。`AdminLayout` 优先 `/auth/menus`，只改 `menuConfig` 不够。
- 已过审 UI 合同：五类 `skill|plugin|command|agent|team`；治理台 **7 Tab**（源+目录+五类），禁止抄旧「六 Tab」；智能体不是专家；订插件不带礼包；租户直打 `/newapi` = NotFound 不是 Unauthorized；`/llm` 不要整页 404。
- 本轮闸门：`check-frontend.sh` exit 0。official Jest 3 passed。admin 全量 12 passed + Members「reset password」20s timeout（单跑 18.5s 过，P-FE-07 悬崖）。shared `dist` 仍 export `queryViewState`，`src/index.ts` 已无。
- official：`QueryClientProvider` 挂了，0 处 `useQuery`；无鉴权 client；三处 catch→空。

## Open (mine)

- 租户安装面：官网 JWT vs 跳 admin returnUrl vs 一期只逛（堵 FR-20/21）。
- 超管字段：登录加 `is_platform_admin` vs `tenant_id==null`。
- 空缓存兜底排除写叶会红 `usePermission.test`「系统管理」。
- `/llm` 租户自有供应商 vs Dashboard 链 `/llm` vs 渠道 404，不得合成。

## Do not re-litigate

- D22–D29 五类 / 7 Tab / 智能体 / D24 无礼包 / D20 只禁插件行。
- T-31：不重组五组、不修幽灵 `/enterprise` `/rbac`。
- enable-host 冻 PR8。Q-VOICE 禁止新写四柱 Hero。
