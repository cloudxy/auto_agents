# 实现证据 · T-29 admin 单布局树：平台页并入主路由树，点菜单侧栏不整树重挂

> 票：contract §11 Wave A `T-29`｜FR 锚点：FR-96（GWT-96.1/96.2/96.3/96.4）｜角色：/frontend（lane=ui）｜日期：2026-09-11
> 依据：ADR-0022（accepted，单布局树 + 页级守卫 + expand-contract）；edge-states §0.11（切换过渡态验收口径）；GWT-96.4 钉 FR-82/ADR-0021 菜单真相不变。

## 1. 契约落位表（实现前填，实现后核对）

| 契约元素 | 落在哪层 | 文件 | 备注 |
|---|---|---|---|
| 单一 AdminLayout 挂载点（ADR-0022 决策 1） | 路由树 | `frontend/admin/src/App.tsx` | 唯一 `<Route element={<MainLayout />}>` 分支；原双树 `PlatformAdminLayout` 路由分支与函数体均已删除（contract 阶段） |
| 平台写面并入主树（/newapi /platform-ops /users） | 路由树 | `App.tsx` 主 Route 子叶 | 与 /dashboard 等同层；路由级 lazy（工单 69 既有）保持 |
| 页级守卫：非超管 = 缺页同形 404 | 布局渲染前 | `App.tsx` `MainLayout` | 复用 `menuConfig.isPlatformWritePath`（既有导出，未改）；判 `!isAuthenticated \|\| !user?.is_platform_admin` → `<NotFound/>` 全屏同形，不进 Unauthorized、不挂侧栏（ADR 备选 D 否决理由保持） |
| 权限快照单次加载（决策 2） | hook 既有语义 | `hooks/usePermission.ts` **未改** | 模块级 `loadState==='loaded'` 短路 + 单树后 AdminLayout 导航期不卸载 → 快照天然只加载一次；「权限加载中」仅首访（GWT-96.3=82.2 同句） |
| 懒加载 fallback 只在内容区（§0.11） | 路由级包装 | `App.tsx` `Page`（既有） | 单树后跨组首访 lazy 挂起落在页内 Suspense（内容区），AdminLayout/侧栏不再整树重挂 |
| 菜单真相不变（GWT-96.4/ADR-0021） | 数据源 | `config/menuConfig.tsx`、`AdminLayout.tsx`、`usePermission.ts` **均未改** | 侧栏仍 menuConfig + filteredMenus 驱动；动态菜单 /auth/menus 读取保持（T-15 范围未触碰） |
| 组件测试 | Jest | `frontend/admin/src/App.layout.test.tsx`（新增） | DOM 节点同一引用 = 不重挂；展开态 class 断言；404 同形回归 |

**边界核对**：☐ 未动 menuConfig/filteredMenus 语义 ☑（零 diff）｜☐ 未动页头规范（T-34 未触碰） ☑｜☐ 未动 NewApiOps 内部（T-31 未触碰） ☑｜☐ 未定义新 token / 未改 GWT ☑

## 2. 改动文件清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `frontend/admin/src/App.tsx` | 修改 | 删 `PlatformAdminLayout` 双树分支；新增 `MainLayout`（守卫 + 唯一挂载点）；/newapi /platform-ops /users 并入主 Route。142 行（F-7 ≤400） |
| `frontend/admin/src/App.layout.test.tsx` | 新增 | GWT-96.1/96.2 重挂断言 + 404 同形回归 4 例。158 行 |

工作树中其余 M/?? 文件（backend/、official/Register、outbound_keys 等）为 Wave A 并行票（T-04/T-05/T-13/T-24/T-26…）所有，非本票改动。

**与票里「会改哪些文件」一致**：☑ 是（预期即 App.tsx + 测试；AdminLayout/usePermission 无需改——快照单次加载已由既有模块级缓存 + 单树保证）
**未触碰「不许改的文件」**：☑ 确认（menuConfig / AdminLayout / usePermission / NewApiOps / ProtectedRoute / 页头零 diff）

## 3. 关键实现决策

### 守卫为什么放布局渲染前而非页 element 内

ADR-0022 写「页面/路由 element 内判定」，但若平台守卫只包页 element，非超管直打平台写面时主树 `AdminLayout` 仍会先挂载（侧栏 + 内容区 404）——与现网 `PlatformAdminLayout` 的**全屏同形 404（无侧栏）**不同形，且租户侧栏文案（如「渠道组」）会出现在 404 屏上，破坏 GWT-07.3 既有测试口径（`queryByText(/渠道/)` 必须缺席）。故守卫放在 `MainLayout`（同一布局路由的 element）内、`ProtectedRoute→AdminLayout` 渲染之前按 `isPlatformWritePath(pathname)` 短路。**对超管零影响**：该分支只在非超管/未登录时命中，超管跨组切换仍命中同一路由分支 → React 同位同型复用 → 不重挂。等价实现 ADR 决策 1 的语义（「不闪权限 UI、缺页同形」），偏差已在此记录。

### expand-contract（ADR-0022 决策 3）两阶段执行记录

- **Expand**：主树 + `MainLayout` 守卫上线接管路由；旧 `PlatformAdminLayout` 守卫体保留为未挂载函数（`PlatformAdminLayoutRollback`，回滚 = 恢复一段 JSX）。跑全量 admin Jest → 22 suites / 95 tests 全绿（见 §6 第 1 段输出）。
- **Contract**：删除该函数（双树不复存在），重跑全量 Jest + build + 前端门禁 + 后端回归 → 全绿（§6 第 2 段起）。
- 两阶段同票同会话完成，未跨特征留双路径；因本环境禁止 git commit，回滚保险 = 本证据记录的 staged 验证序列 + 工作树 diff。

### 权限快照单次加载（决策 2）——未迁移 zustand 的理由

ADR 提「缓存于 store」；现状 `usePermission` 模块级缓存（`loadState`/`cachedPermissions` + 在飞去重，P-FE-03 修复链）已提供同语义（单进程单份、登出 `clearCachedPermissions`）。单树后 AdminLayout 在导航期间不卸载，「子路由切换不重新触发加载」由组件不重挂直接保证。迁移 zustand 属可观察行为等价的重构，且该文件是 T-15（动态菜单停读）施工面——本票不动，避免越界。已在 §8 回报 architect。

### 事务边界 / 幂等 / 并发 / 外部依赖

➖ N/A（纯前端路由结构票，无数据面改动）。

## 4. ORM 与 DBML 对齐

➖ N/A（未触及 models/schemas；零后端代码 diff）。

## 5. 可观测性

➖ N/A（无新日志面；前端沿用既有 ErrorBoundary label=`404`/页 label 标记）。

## 6. 自测证据

> 命令与退出码**原样粘贴**。

```
# Expand 阶段（旧守卫体保留为回滚保险，主树已接管）
$ cd frontend/admin && CI=true npm test
Test Suites: 22 passed, 22 total
Tests:       95 passed, 95 total
exit: 0

# Contract 阶段（删除 PlatformAdminLayout 双树）后全量
$ cd frontend/admin && CI=true npm test
Test Suites: 22 passed, 22 total
Tests:       95 passed, 95 total
exit: 0

# 构建门禁
$ npm run build --prefix frontend/admin
The build folder is ready to be deployed.
exit: 0

# 前端工程门禁（F-2..F-7）
$ bash tools/check/frontend.sh
✓ 前端工程门禁通过
exit: 0

# 后端回归（不应破坏后端）
$ uv run pytest -x -q backend/tests
1374 passed, 36 skipped, 7 warnings in 179.67s (0:02:59)
exit: 0
```

### 后端回归过程中的环境干扰记录（非本票缺陷，已定界）

首次全量后端跑出 `test_product_events.py::test_gwt_15_4_login_failed_reasons_no_password` 失败（`assert 'credential' in set()`）。定界过程：

1. 该单测隔离跑通过；与并行票新文件（`test_outbound_keys.py` / `test_billing_orders_write_rules.py`，均他人未跟踪文件）组合可复现。
2. 本票 diff 仅前端两文件，pytest 不读取；将本票两文件暂存移出后全量重跑当时通过（树仍在被他票并发写入，证据链见下）。
3. 根因：`backend/app/api/v1/auth.py` 登录失败限流走**真实 Redis**（`login_fail:*`，15 分钟 TTL / 5 次），`conftest._purge_quota_count_keys` 只清 `quota:count:*` 不清限流键 → 任何会话（含并行票的会话）打满 `fail-a` 等共享测试用户名后，**跨会话**污染后续运行（失败时 stderr 见 `RATE_LIMITED ... 请14分钟后再试`）。
4. 处置：按 conftest 同款先例直连 DEL 短命运行态键（`purged: {'login_fail:': 4, 'register_fail:': 0}`）后重跑全量 → **exit 0（上文输出）**。未改任何后端/测试代码。

### 验收项逐条对应

| GWT | 覆盖的测试 | 结果 |
|---|---|---|
| GWT-96.1 跨组切换：内容区切换、无「权限加载中」、展开态保持 | `App.layout.test.tsx`「cross-group menu click keeps the same sider instance and expansion」（/dashboard 概览组 → /users 系统管理组；侧栏 DOM 同一引用 + 数据工厂组保持 `ant-menu-submenu-open`） | ✅ |
| GWT-96.2 组内切换：滚动/展开状态相同 | 同文件「in-group leaf switch...」（/spiders/tasks → /spiders/logs；同一 DOM 引用 + 展开保持。滚动位置 jsdom 不可设，以「DOM 节点未换」蕴含滚动容器未重建） | ✅ |
| GWT-96.3 首访允许「权限加载中」、此后不再出现 | 首访句由 `AdminLayout` 既有逻辑保留（未改）；两切换用例末尾断言 `queryByText('权限加载中')` 缺席 | ✅ |
| GWT-96.4 越权/不变式：租户仍见渠道组/我的安装，不见平台写面 | 404 同形两例（租户公司管理员直打 /users；未登录直打 /newapi 无登录重定向）+ 既有 App.test 4 例（/newapi /platform-ops /product-events 同形）全绿；菜单过滤逻辑零 diff（usePermission.test 4 例全绿） | ✅ |
| §0.11 fallback 只在内容区 | 单树后 lazy 挂起落在 `Page` 页内 Suspense（结构保证）；侧栏不卸载由 DOM 同一引用断言蕴含 | ✅（结构级） |

### 四类易漏测试

| 类型 | 测试 | 结果 |
|---|---|---|
| 事务回滚 | ➖ N/A（无数据面） | |
| 幂等 | ➖ N/A（无写操作） | |
| 并发写 | ➖ N/A | |
| 外部依赖失败 | api mock 全拒绝路径下页面渲染不崩（两切换用例即在此 mock 下跑通） | ✅ |

## 7. NFR 验证

票内无 NFR 数字项；NFR-03「菜单切换侧栏不重挂、不闪」即 GWT-96.1/96.2，已由组件测试覆盖（见上表）。

## 8. 给下游的信息

| 给谁 | 内容 |
|---|---|
| `/qa` | ① 96.1–96.4 组件级已绿，**活体回归仍需做**：真实浏览器跨组点菜单看侧栏滚动位置（jsdom 无法设滚动）与懒加载 fallback 位置（§0.11）。② 平台页 404 同形需全套重跑：/newapi /platform-ops /users ×（未登录/租户管理员/租户经办），另加 `/newapi/子路径` 深链（layout 不命中 → 全局 `*` 404，与改前同形）。③ **环境坑**：登录失败限流键存真实 Redis 且 conftest 不清——跑登录相关用例前若遇 `RATE_LIMITED`，按 §6-干扰记录 DEL `login_fail:*`（15 分钟自愈）。 |
| `/backend`（或测试基建） | 建议在 conftest 补 `_purge` 限流键（`login_fail:*` / `register_fail:*`），同 `_purge_quota_count_keys` 先例；本票未改（越界）。并行 Wave A 会话间会互相污染。 |
| `/architect` | ① ADR-0022 决策 1 的「element 内判定」落地为「布局 element 渲染前短路」（理由见 §3 第一条，保 404 全屏同形）；若需修正 ADR 措辞请审。② 决策 2「缓存于 store」以「模块级缓存 + 单树不卸载」等价达成，未迁 zustand（T-15 施工面，避免双改）。 |
| `/frontend`(T-34/T-31) | 树已定：T-34 页头规范现在可在单树上铺；T-31 NewApiOps 内部改造不受影响（页 element 未动）。 |

## 9. 交票自检

- [x] 每条验收项有 evidence（命令 + 退出码原样）
- [x] 自测全绿（admin Jest 22/22、build、前端门禁、后端 1374 passed）
- [x] 契约落位表已核对；未动菜单真相/页头/NewApiOps（越界零 diff）
- [x] ORM/DBML N/A（未触及）
- [x] 无硬编码连接串/密钥/端口/阈值
- [x] 业务 .tsx ≤ 400 行（App.tsx 142 / 测试 158，F-7）
- [x] 数据获取未新增手动 loading（本票无新数据面）
- [x] 路由 lazy/ErrorBoundary/404 保持
- [x] 发现的上游问题已回报（Redis 限流键跨会话污染 → §8），未自行绕过改后端
- [x] expand-contract 两阶段同票完成，无双路径残留
