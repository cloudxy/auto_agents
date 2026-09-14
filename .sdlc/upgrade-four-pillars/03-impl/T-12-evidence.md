# 实现证据 · T-12 权限未知态：加载中，不是空白也不是全开写面

> 票：contract.md T-12｜FR 锚点：FR-U15｜角色：/frontend｜日期：2026-09-12
> 上游：`01-define/spec.md` v1.2 FR-U15 · `02-shape/edge-states.md` 屏 5/21 · T-09 `require_platform_admin_or_404`
> 泳道：ui｜未做结账 / 未写「当前可买」

权限缓存未就绪：「权限加载中」或保留读叶；不得整站空白；不得露出平台 RBAC / 上架 / 值班写。租户公司管理员导航隐藏这些写面；直打 `/rbac`、上架治理写面子路由、`/newapi` = 与「页面不存在或已被移除」同形，无「抱歉您没有权限」。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 未知态读叶 + 加载旁注 | 壳 | `usePermission.ts` + `AdminLayout.tsx` | 空缓存 strip 平台写叶；旁注「权限加载中」 |
| 平台写面直打 404 | 路由 | `App.tsx` MainLayout | `/newapi` `/platform-ops` `/users` `/rbac` `/enterprise` |
| 上架治理直打 404 | 路由 `*` + 壳差 | `/capabilities/sources` 无子路由；租户 `/capabilities` 是货架 | 同 NotFound 模板 |
| 超管 RBAC 可达 | 路由 | `/rbac` + `RbacManagement.tsx` | GWT-U15.1 |
| 拒绝同形 | NotFound | `pages/NotFound.tsx` | 「页面不存在或已被移除」+「返回工作台」 |

**分层依赖核对**：☑ 未改 backend 守卫 ☑ 未把租户 `/capabilities` 整页 404（那是货架）

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/pages/Capabilities.tsx` | 修改 | 租户不再看到七叶上架写（T-10 壳差，堵住未知态漏上架） |
| `frontend/admin/src/App.menu.test.tsx` | 修改 | GWT-U15.2/U15.3：加载中、`/newapi`、listing sources 404、货架非 404 |
| `frontend/admin/src/hooks/usePermission.test.tsx` | 修改 | 未知/已加载均无 RBAC/上架治理/值班写叶 |
| `.sdlc/upgrade-four-pillars/03-impl/T-12-evidence.md` | 新增 | 本文件 |

既有：`usePermission` 未知态 `stripPlatformWrite`；MainLayout 非超管直打平台写/组织幽灵 = NotFound。本票钉测试并堵住 `/capabilities` 七叶对租户的上架泄漏。

**未触碰「不许改的文件」**：☑ 确认（未改 GWT / schema / tokens；未做 checkout）

## 3. 关键实现决策

未知 ≠ 无权限滤光 ≠ 全开写面（P-FE-03）。`is_platform_admin` 来自登录用户，权限码来自 `/auth/permissions`。未知时平台写叶剥离；租户打开能力市场走货架不是七叶。404 与未登录缺页同一 NotFound，不用 Unauthorized「抱歉，您没有权限访问该页面。」

### 事务 / 幂等 / 并发

☑ 本票无写路径。

### 外部依赖

| 依赖 | 超时 | 重试 | 降级 |
|---|---|---|---|
| GET `/auth/permissions` | 挂载补拉、in-flight 去重 | 失败保留读叶 | 「权限暂时刷新失败，已保留上次菜单。」 |

## 4. ORM 与 DBML 对齐

☑ 未改。

## 5. 可观测性

壳不展示权限码原文。☑ 无密码/token。

## 6. 自测证据

```
$ cd /Users/xuyun/auto_agents/frontend/admin && npm test -- --watchAll=false src/pages/market/TenantShelf.test.tsx src/pages/market/PowerMarketSwitch.test.tsx src/components/SubscribeModal.test.tsx src/pages/Capabilities.governance.test.tsx src/pages/Capabilities.subscribe.test.tsx src/pages/Capabilities.command.test.tsx src/pages/Capabilities.import.test.tsx src/hooks/usePermission.test.tsx src/App.menu.test.tsx

PASS src/App.menu.test.tsx
PASS src/hooks/usePermission.test.tsx
Test Suites: 9 passed, 9 total
Tests:       65 passed, 65 total
exit: 0
```

GWT-U15 钉在 `App.menu.test.tsx`：

- `GWT-82.2` / `GWT-U15.2 permissions unknown keeps read leaves, not blank, not platform writes` → 「权限加载中」；有 AutoAgents 壳与能力市场读叶；无源/目录 tab；无中转站管控/平台运营台/用户管理；无「抱歉」
- `GWT-82.3 tenant company admin direct hit on /rbac` → 「页面不存在或已被移除」；无「抱歉」
- `GWT-U15.3 tenant company admin /newapi is same 404 shell, no 抱歉`
- `GWT-U15.3 tenant company admin listing sources is same 404 shell, no 抱歉`
- `GWT-U15.3 tenant company admin /capabilities is shelf not 404`
- `platform super admin still reaches /enterprise and /rbac` → GWT-U15.1 超管可见矩阵页

```
$ cd /Users/xuyun/auto_agents && bash tools/check/frontend.sh
✓ 前端工程门禁通过
exit: 0
```

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-U15.1 超管 RBAC | `platform super admin still reaches /enterprise and /rbac` | ✅ 「角色权限菜单管理」 |
| GWT-U15.2 未知态 | `GWT-U15.2 permissions unknown…` + `GWT-82.2` + usePermission 空缓存 | ✅ 加载中/读叶；无 RBAC/上架/值班写 |
| GWT-U15.3 租户直打 404 | `/rbac` `/newapi` `/capabilities/sources` 同形；无「抱歉您没有权限」 | ✅ |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | — | ➖ N/A（无多步写） |
| 幂等 | 重复直打仍 404 同形 | ✅ |
| 并发写 | — | ➖ N/A |
| 外部依赖失败 | 权限拉取失败保留读叶、不露平台写 | ✅ usePermission 空缓存/补拉失败 |

## 7. NFR

| NFR | 要求 | 实测 |
|---|---|---|
| NFR-U05 权限三态 | 未知≠空白≠全开写；拒绝=404 同形 | Jest |

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | 未知：侧栏旁注「权限加载中」。404 锁句「页面不存在或已被移除」+「返回工作台」。禁止「抱歉您没有权限」。租户 `/capabilities` 必须是货架。listing 直打用 `/capabilities/sources`。 |
| `/frontend` | 不要用 Unauthorized 403 页承接平台写面。 |
| `/architect` | 前端 404 与 T-09 HTTP 404 同形产品句；plugin verify 仍 403 不在本票。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿
- [x] 未做 checkout
- [x] 未改 GWT / schema / tokens
- [x] 四类易漏已覆盖或标 N/A
